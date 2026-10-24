"""Llamadas a IA usando la clave que el usuario haya conectado (ver claves.py)."""
import base64
import json
import math
import re
import threading
import time
import urllib.parse
from fractions import Fraction
from typing import Callable
from pathlib import Path

import httpx

from . import claves, seguro
from .idioma import t

VIDEO_MAXIMO = 300 * 1024 ** 2  # un clip de IA de 5 s pesa unos pocos MB
ESPACIO_IMAGEN = "black-forest-labs/FLUX.1-schnell"  # imágenes gratis sin clave y con calidad (el oficial de FLUX)


def _ruta_url(texto: str) -> str:
    """El texto como trozo de la ruta de una URL: con «/» escapado, y sin quedarse en «.» o «..» solos (el cliente
    los normaliza a otra ruta del mismo servidor, y la petición lleva la clave)."""
    return urllib.parse.quote(texto if texto.strip(".") else f"imagen {texto}", safe="")


def _imagen_real(datos: bytes) -> bytes:
    """Lo que devuelve un servicio de imágenes se comprueba antes de usarlo: si no es una imagen, se prueba otro."""
    if not seguro._es_imagen(datos[:16]):
        raise RuntimeError(t("no devolvió una imagen"))
    return datos


def _clip_real(datos: bytes, destino: Path) -> Path:
    if not seguro.es_video(datos[:16]):
        raise RuntimeError(t("no devolvió un video"))
    destino.write_bytes(datos)
    return destino


class SinClave(Exception):
    pass


# La regla común de faltas de ortografía: va igual en las instrucciones de todas las IA que leen pedidos
FALTAS = ("El pedido lo escribe una persona que puede tener faltas (b/v, s/c/z, ll/y, h que falta, letras cambiadas). "
          "Entiende qué quiso decir: si una palabra tal cual no encaja con el resto del pedido, usa la parecida que sí "
          "encaja (p. ej. «abla» → habla). Nunca cambies el tema. Si dos lecturas son igual de probables, dilo.")


def _json_de(texto: str, esquema: dict | None = None) -> dict:
    """Saca el objeto JSON de una respuesta que puede traer texto, ejemplos o ```json alrededor.
    Si viene roto (comillas sin escapar, comas que faltan, cortado al final), lo repara.
    Con varios objetos en el texto (un ejemplo de formato, la respuesta, sus trozos de dentro) se queda con el que
    cumple `esquema`; sin esquema, con el más grande que se pudo leer tal cual."""
    import itertools
    import re

    import json_repair  # las IA pequeñas rompen el JSON en respuestas largas
    # Con texto hostil (miles de «{» o «[» sin cerrar) buscar y reparar cuesta tiempo cuadrático: se mira como mucho
    # 200 KB y 3000 llaves, y no se repara si hay más de 3000 aperturas (una respuesta normal de 100 KB tiene ~1400).
    texto, reparaciones, candidatos = texto[:200_000], 0, []
    reparable = texto.count("{") + texto.count("[") <= 3000
    for m in itertools.islice(re.finditer(r"\{", texto), 3000):
        try:
            datos, fin = json.JSONDecoder().raw_decode(texto, m.start())
            exacto = True
        except (ValueError, RecursionError):  # RecursionError: anidamiento muy profundo
            if not reparable or reparaciones == 3:
                continue
            reparaciones += 1
            try:
                datos = json_repair.loads(texto[m.start():])
            except RecursionError:
                continue
            fin, exacto = len(texto), False
            if isinstance(datos, list):  # varios trozos seguidos: el primero que sea un objeto
                datos = next((d for d in datos if isinstance(d, dict)), None)
        if isinstance(datos, dict) and datos:
            valido = esquema is None or _validar(datos, esquema) is not None
            # Mejor: cumple lo pedido, se leyó sin reparar y abarca más texto (el objeto de fuera, no uno de dentro).
            candidatos.append(((not valido, not exacto, -(fin - m.start())), datos))
    if not candidatos:
        raise ValueError(t("la IA no devolvió JSON") if "{" not in texto
                         else t("la IA devolvió un JSON que no se puede reparar"))
    return min(candidatos, key=lambda c: c[0])[1]


def _normalizar(datos, esquema: dict):
    """Arregla lo que las IA hacen a menudo y no es un error de verdad: números escritos como texto ("8"), un número
    donde va texto y una lista de etiquetas escrita como un solo texto ("#a #b")."""
    tipo = esquema.get("type")
    if tipo in ("integer", "number") and isinstance(datos, str):
        try:
            numero = float(datos.strip().replace(",", "."))
            return int(numero) if tipo == "integer" or numero.is_integer() else numero
        except (ValueError, OverflowError):  # "texto" o "inf": no es un número usable
            return datos
    if tipo == "string" and isinstance(datos, (int, float)) and not isinstance(datos, bool):
        return str(datos)
    if tipo == "string" and isinstance(datos, (dict, list)):  # p. ej. los argumentos del Director como objeto
        return json.dumps(datos, ensure_ascii=False)
    if tipo == "array" and isinstance(datos, str) and esquema.get("items", {}).get("type") == "string":
        import re
        return [p for p in re.split(r"[\s,]+", datos) if p]
    if tipo == "object" and isinstance(datos, dict):
        # Un campo opcional en null (los modelos pequeños lo hacen) es como si no viniera: no tumba la respuesta
        return {k: _normalizar(v, esquema.get("properties", {}).get(k, {})) for k, v in datos.items()
                if v is not None or k in esquema.get("required", [])}
    if tipo == "array" and isinstance(datos, list):
        return [_normalizar(d, esquema.get("items", {})) for d in datos]
    return datos


def _validar(datos: dict, esquema: dict) -> dict | None:
    """La respuesta lista para usar, o None si no cumple el esquema ni quedándose solo con lo completo."""
    datos = _normalizar(datos, esquema)
    if not _faltan(datos, esquema):
        return datos
    podado, ok = _podar(datos, esquema)
    return podado if ok and not _faltan(podado, esquema) else None


_TIPOS = {"string": str, "integer": (int, float), "number": (int, float), "boolean": bool,
          "array": list, "object": dict}


def _faltan(datos, esquema: dict, ruta: str = "") -> list[str]:
    """Campos obligatorios que no vinieron, vienen vacíos (null) o con el tipo equivocado, también dentro de listas."""
    tipo = esquema.get("type")
    if tipo in _TIPOS and (datos is None or isinstance(datos, bool) != (tipo == "boolean")
                           or not isinstance(datos, _TIPOS[tipo])):
        return [ruta.rstrip(".") or t("raíz")]
    if tipo == "object":
        faltan = [f"{ruta}{k}" for k in esquema.get("required", []) if k not in datos]
        for k, sub in esquema.get("properties", {}).items():
            if k in datos:
                faltan += _faltan(datos[k], sub, f"{ruta}{k}.")
        return faltan
    if tipo == "array":
        return [f for d in datos for f in _faltan(d, esquema.get("items", {}), ruta)]
    return []


def _podar(datos, esquema: dict) -> tuple:
    """Quita de las listas los elementos incompletos (la IA gratis a veces deja campos sin rellenar en respuestas
    largas): mejor 3 nichos buenos que ninguno. Devuelve (datos, ok); ok=False si una lista que traía elementos
    se queda vacía. Un elemento cuya lista interior se vacía se quita entero, sin tirar a sus hermanos."""
    if esquema.get("type") == "object" and isinstance(datos, dict):
        resultado, ok = {}, True
        for k, v in datos.items():
            resultado[k], ok_k = _podar(v, esquema.get("properties", {}).get(k, {}))
            ok = ok and ok_k
        return resultado, ok
    if esquema.get("type") == "array" and isinstance(datos, list):
        items, completos = esquema.get("items", {}), []
        for d in datos:
            podado, ok_d = _podar(d, items)
            if ok_d and not _faltan(podado, items):
                completos.append(podado)
        return completos, not (datos and not completos)
    return datos, True


def de_fuera(datos, esquema: dict, que: str) -> dict:
    """Un guion (o una biblia) que escribió el agente que maneja el estudio (p. ej. Claude por el MCP) en vez de la IA
    de texto conectada: se comprueba igual que lo que devuelve la IA. Vale como objeto o como texto JSON."""
    if isinstance(datos, str):
        try:
            datos = json.loads(datos)
        except ValueError:
            raise ValueError(t("{que} no es un JSON válido.", que=que)) from None
    valido = _validar(datos, esquema) if isinstance(datos, dict) else None
    if valido is None:
        faltan = ", ".join(_faltan(_normalizar(datos, esquema), esquema)[:8]) if isinstance(datos, dict) else t("raíz")
        raise ValueError(t("{que} no tiene la forma pedida: faltan o están mal {campos}.", que=que, campos=faltan))
    return valido


def _ejemplo(esquema: dict):
    """La forma de la respuesta con valores de muestra. A la IA gratis se le enseña esto y no el esquema técnico:
    con el esquema, a veces lo copia tal cual en vez de rellenarlo."""
    tipo = esquema.get("type")
    if tipo == "object":
        return {k: _ejemplo(v) for k, v in esquema.get("properties", {}).items()}
    if tipo == "array":
        return [_ejemplo(esquema.get("items", {}))]
    if esquema.get("enum"):
        return " | ".join(map(str, esquema["enum"]))  # una de estas opciones
    return {"integer": 0, "number": 0, "boolean": False}.get(tipo, "...")


def _sin_rellenar(datos) -> bool:
    """Si la respuesta conserva algún valor de muestra de _ejemplo (copió la forma en vez de responder)."""
    if isinstance(datos, dict):
        return any(map(_sin_rellenar, datos.values()))
    if isinstance(datos, list):
        return any(map(_sin_rellenar, datos))
    return datos == "..."


def _texto_gratis(instrucciones: str, pedido: str, esquema: dict) -> dict:
    """IA de texto gratis y sin clave (GPT-OSS 20B en Pollinations).
    ponytail: límite de 1 respuesta cada 30 s por conexión y menos calidad; con Groq/Gemini (gratis) va mejor."""
    mensajes = [{"role": "system", "content": f"{instrucciones}\n\nResponde SOLO con un objeto JSON válido, sin "
                                              f"texto antes ni después, con esta forma (cambia cada valor de muestra "
                                              f"por el de verdad; donde hay opciones con «|», elige una; las listas "
                                              f"llevan los elementos que hagan falta):\n"
                                              f"{json.dumps(_ejemplo(esquema), ensure_ascii=False)}\n"
                                              "Tu respuesta tiene un límite corto de longitud: escribe textos breves "
                                              "para que el JSON quede completo."},
                {"role": "user", "content": pedido}]
    problema = None
    for intento in range(4):
        if intento:
            time.sleep(32)  # respetar el límite gratis de 1 respuesta cada 30 s
        try:
            # Sin cuenta, cada respuesta se corta en ~1500 tokens: con razonamiento bajo queda sitio para el JSON.
            # La semilla cambia en cada intento porque el servicio devuelve la misma respuesta guardada si se repite.
            r = httpx.post("https://text.pollinations.ai/openai", timeout=300,
                           json={"model": "openai", "messages": mensajes, "reasoning_effort": "low", "private": True,
                                 "seed": int(time.time() * 1000) % 2_000_000_000})
        except httpx.HTTPError as e:  # corte de red o el servicio no contesta: se repite
            problema = t("sin conexión con el servicio gratis ({error})", error=type(e).__name__)
            continue
        if r.status_code in (402, 429) or r.status_code >= 500:  # límite gratis o caída pasajera
            problema = t("el servicio gratis respondió {codigo}", codigo=r.status_code)
            continue
        if r.status_code >= 400:
            problema = t("el servicio gratis rechazó el pedido ({codigo})", codigo=r.status_code)
            break  # un 4xx no se arregla repitiendo
        try:
            opcion = r.json()["choices"][0]
            contenido = (opcion.get("message") or {}).get("content") or ""
            if not contenido.strip():  # pasa a veces con respuestas largas: se repite
                problema = t("respuesta vacía ({motivo})", motivo=opcion.get("finish_reason") or t("sin motivo"))
                continue
            datos = _json_de(contenido, esquema)
            valido = _validar(datos, esquema)  # se queda con los elementos completos, si queda alguno
            if valido is not None and not _sin_rellenar(valido):
                return valido
            faltan = ", ".join(_faltan(_normalizar(datos, esquema), esquema)[:5])
            problema = (t("devolvió el ejemplo sin rellenar") if valido is not None
                        else t("faltan o están mal: {campos}", campos=faltan))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            problema = t("respuesta no válida: {error}", error=e)
    raise RuntimeError(t("La IA gratis sin clave no dio una respuesta válida ({problema}). Conecta Groq o Gemini "
                         "(gratis) en «Claves de IA» para más calidad.", problema=problema))


def texto_json(instrucciones: str, pedido: str, esquema: dict, uso: str = "texto") -> dict:
    """Pide a la IA de texto una respuesta JSON que cumpla `esquema`. uso: «texto», o «diseno» para la IA que diseña
    (claves.para). Sin ninguna clave de texto conectada usa la IA gratis sin clave (más simple, pero funciona)."""
    c = claves.para(uso)
    if not c or not c.get("clave"):
        return _texto_gratis(instrucciones, pedido, esquema)
    if c["proveedor"] == "anthropic":
        import anthropic
        cliente = anthropic.Anthropic(api_key=c["clave"])
        with cliente.messages.stream(
            model=c["modelo_texto"], max_tokens=32000, system=instrucciones,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": esquema}},
            messages=[{"role": "user", "content": pedido}],
        ) as s:
            r = s.get_final_message()
        if r.stop_reason == "refusal":
            raise RuntimeError(t("Claude rechazó el pedido."))
        return json.loads(next(b.text for b in r.content if b.type == "text"))

    from openai import OpenAI
    cliente = OpenAI(api_key=c["clave"], base_url=claves.OPENAI_COMPAT[c["proveedor"]])
    # El modo json_object funciona en todos los compatibles; el esquema va en las instrucciones.
    mensajes = [{"role": "system", "content": f"{instrucciones}\n\nResponde SOLO con JSON que cumpla este esquema:\n"
                                              f"{json.dumps(esquema)}"},
                {"role": "user", "content": pedido}]
    for _ in range(2):  # si la respuesta llega cortada o incompleta, se pide una vez más
        r = cliente.chat.completions.create(model=c["modelo_texto"], response_format={"type": "json_object"},
                                            messages=mensajes,
                                            # Pollinations: que no salga en su feed público
                                            extra_body={"private": True} if c["proveedor"] == "pollinations" else None)
        try:
            valido = _validar(_json_de(r.choices[0].message.content or "", esquema), esquema)
        except ValueError:
            valido = None
        if valido is not None:
            return valido
    raise RuntimeError(t("La IA de texto ({proveedor}) respondió incompleto dos veces. Inténtalo de nuevo o "
                         "elige otra IA de texto en «Claves de IA».", proveedor=c["proveedor"]))


def puede_referencia() -> bool:
    """Si la IA de imágenes conectada sabe editar a partir de una imagen de referencia (mantener a alguien igual)."""
    c = claves.para("imagen")
    return bool(c and c.get("clave") and c["proveedor"] in ("openai", "pollinations", "gemini"))


SIN_REFERENCIA = t("Para editar con IA hace falta una IA de imágenes que edite fotos: conecta Gemini, OpenAI o "
                   "Pollinations (con su clave) en «Claves de IA» y elígela en «Imágenes».")
# US$ por edición con OpenAI en calidad media: la imagen de 1536 px (0,063 con gpt-image-1) más la foto que se le manda,
# redondeado hacia arriba para que el aviso de costo no se quede corto
PRECIO_EDITAR_OPENAI = 0.08


def _con_referencia(pedido: str, foto: Path, ancho: int, alto: int, destino: Path, calidad: str = "1K") -> Path:
    """La IA de imágenes conectada (con referencia: ver puede_referencia) hace `pedido` a partir de la foto."""
    c = claves.para("imagen")
    if c["proveedor"] == "gemini":
        destino.write_bytes(_imagen_gemini(c, pedido, ancho, alto, foto, calidad=calidad))
        return destino
    size = "1024x1536" if alto > ancho else "1536x1024" if ancho > alto else "1024x1024"
    base = "https://api.openai.com/v1" if c["proveedor"] == "openai" else "https://gen.pollinations.ai/v1"
    modelo = c["modelo_imagen"] if c["proveedor"] == "openai" else "black-forest-labs/flux.1-kontext-pro"
    # OpenAI, en calidad fija: con «auto» podía salir en alta, sin precio conocido (ver PRECIO_EDITAR_OPENAI)
    extra = {"quality": "medium"} if c["proveedor"] == "openai" else {"private": "true"}
    with open(foto, "rb") as f:
        r = httpx.post(f"{base}/images/edits", timeout=300, headers={"Authorization": f"Bearer {c['clave']}"},
                       files={"image": (foto.name, f, "image/png" if foto.suffix.lower() == ".png" else "image/jpeg")},
                       data={"model": modelo, "prompt": pedido, "size": size, "n": "1", **extra})
    r.raise_for_status()
    d = r.json()["data"][0]
    destino.write_bytes(_imagen_real(base64.b64decode(d["b64_json"]) if d.get("b64_json")
                                     else seguro.descargar(d["url"])))
    return destino


def editar_imagen(foto: Path, instruccion: str, destino: Path, calidad: str = "1K") -> Path:
    """Como el relleno generativo de Photoshop: la IA de imágenes cambia en la foto solo lo que pide `instruccion`
    («ponle gorra roja y humo verde») y deja el resto igual. Necesita una IA que edite con referencia
    (puede_referencia: Gemini, OpenAI o Pollinations); si no, SinClave. calidad: la de Gemini (1K, 2K o 4K)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QImageReader
    instruccion = " ".join(str(instruccion or "").split())[:1000]
    if not instruccion:
        raise ValueError(t("Escribe qué quieres cambiar en la imagen."))
    if not puede_referencia():
        raise SinClave(SIN_REFERENCIA)
    lector = QImageReader(str(foto))
    lector.setAutoTransform(True)  # la foto de móvil, derecha
    imagen = lector.read()
    if imagen.isNull():
        raise ValueError(t("No se pudo leer la imagen."))
    # En PNG (lo aceptan las tres) y de 2048 px como mucho: Gemini no admite pedidos de más de 20 MB
    if max(imagen.width(), imagen.height()) > 2048:
        imagen = imagen.scaled(2048, 2048, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    original = destino.with_name(f"{destino.stem}-original.png")
    if not imagen.save(str(original), "PNG"):
        raise RuntimeError(t("No se pudo preparar la imagen."))
    try:
        _con_referencia(f"Edit this image: {instruccion}. Change only that and keep everything else exactly the same "
                        "(composition, framing, subject, faces, colors, lighting and style).", original,
                        imagen.width(), imagen.height(), destino, calidad)
    finally:
        original.unlink(missing_ok=True)
    # La IA solo da ciertas proporciones (OpenAI, 2:3, 3:2 o 1:1): recortada al centro a la de la foto, la capa no
    # cambia de encuadre
    hecha, proporcion = QImage(str(destino)), imagen.width() / imagen.height()
    w, h = hecha.width(), hecha.height()
    ancho, alto = min(w, round(h * proporcion)), min(h, round(w / proporcion))
    if not hecha.isNull() and (ancho, alto) != (w, h):
        if not hecha.copy((w - ancho) // 2, (h - alto) // 2, ancho, alto).save(str(destino), "PNG"):
            raise RuntimeError(t("No se pudo guardar la imagen en {destino}.", destino=destino))
    return destino


def imagen_con_producto(prompt: str, foto: Path, ancho: int, alto: int, destino: Path, realista: bool = True) -> Path:
    """Escena con el producto real de la foto. Usa edición con referencia si la IA de imágenes la tiene;
    si no, crea el fondo y coloca encima la foto del producto. realista=False: para dibujos (no fuerza foto)."""
    # Sirve igual para productos que para personas, personajes o lugares de la foto de referencia.
    pedido = (f"{prompt}. Keep the subject from the reference image identical (same face, shape, colors, "
              "label and logo)." + (" Photorealistic." if realista else ""))
    if puede_referencia():
        return _con_referencia(pedido, foto, ancho, alto, destino)
    # ponytail: sin edición con referencia el producto se pega encima del fondo; queda menos natural.
    from .video import ffmpeg
    # Pedir «the product» y a la vez «no product» se contradecía: el hueco va en la propia escena
    escena = re.sub("the product|the subject from the reference image", "an empty spot", prompt, flags=re.IGNORECASE)
    fondo = imagen(f"{escena}, empty space in the center", ancho, alto, destino.with_name(destino.stem + "_fondo.png"))
    ffmpeg("-i", fondo, "-i", foto, "-filter_complex",
           f"[0]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto}[f];"
           f"[1]scale={int(ancho * 0.6)}:-1[p];[f][p]overlay=(W-w)/2:(H-h)*0.62", "-frames:v", "1", destino)
    return destino


def investigar_web(pregunta: str) -> str | None:
    """Investigación en vivo en internet con Claude (búsqueda web). None si la IA de texto no es Claude."""
    c = claves.para("texto")
    if not c or c.get("proveedor") != "anthropic":
        return None
    import anthropic
    cliente = anthropic.Anthropic(api_key=c["clave"])
    mensajes = [{"role": "user", "content": pregunta}]
    for _ in range(6):  # la búsqueda puede pausar el turno; se retoma hasta 5 veces
        r = cliente.messages.create(
            model=c["modelo_texto"], max_tokens=16000, output_config={"effort": "medium"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}], messages=mensajes)
        if r.stop_reason != "pause_turn":
            break
        mensajes = [*mensajes, {"role": "assistant", "content": r.content}]
    return "\n".join(b.text for b in r.content if b.type == "text")


def imagen(prompt: str, ancho: int, alto: int, destino: Path, calidad: str = "1K") -> Path:
    """Genera una imagen y la guarda en `destino`, probando primero lo gratis (ver nubes.ORDEN["imagen"]).
    calidad (1K, 2K o 4K, ver PRECIO_IMAGEN_GEMINI): solo la usa Gemini; las demás IA dan su tamaño de siempre."""
    from . import nubes
    todas = claves.cargar()
    vertical, horizontal = alto > ancho, ancho > alto
    semilla = int(time.time()) % 2_000_000_000

    def cloudflare():
        # 10.000 "neuronas" gratis al día: ~100 imágenes FLUX schnell. Sale cuadrada; el montaje la recorta al formato.
        cuenta, token = cloudflare_partes(todas["cloudflare"]["clave"])
        r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/black-forest-labs/"
                       "flux-1-schnell", headers={"Authorization": f"Bearer {token}"}, timeout=300,
                       # sin «seed»: desde 2026 Cloudflare rechaza (400) cualquier campo que no sea prompt o steps
                       json={"prompt": prompt[:2048], "steps": 8})
        r.raise_for_status()
        return base64.b64decode(r.json()["result"]["image"])

    def pollinations(con_clave: bool = True):
        # Con clave (cuenta gratis): Z-Image Turbo en alta calidad. Sin clave: FLUX en baja resolución y con marca.
        if con_clave:
            c = todas["pollinations"]
            url = (f"https://gen.pollinations.ai/image/{_ruta_url(prompt)}"
                   f"?width={ancho // 16 * 16}&height={alto // 16 * 16}"
                   f"&model={urllib.parse.quote(c['modelo_imagen'], safe='')}&seed={semilla}&private=true")
            cabeceras = {"Authorization": f"Bearer {c['clave']}"}
        else:
            url = (f"https://image.pollinations.ai/prompt/{_ruta_url(prompt)}"
                   f"?width={ancho}&height={alto}&nologo=true&private=true&model=flux&seed={semilla}")
            cabeceras = {}
        return seguro.descargar(url, cabeceras)

    def huggingface():
        c = todas.get("huggingface")
        if not c:  # sin token: el Space gratis de FLUX schnell (cuota anónima de ZeroGPU; el prompt llega a un Space público)
            escala = min(1, 1280 / max(ancho, alto))  # lado largo de 1280: rápido y gasta poca cuota; el montaje escala
            salida = nubes.llamar_space(ESPACIO_IMAGEN, prompt[:2000], semilla, False, int(ancho * escala) // 16 * 16,
                                        int(alto * escala) // 16 * 16, 4, api_name="/infer")
            return nubes.archivo_del_space(salida[0] if isinstance(salida, (list, tuple)) else salida)
        r = httpx.post(f"https://router.huggingface.co/hf-inference/models/{c['modelo_imagen']}", timeout=300,
                       headers={"Authorization": f"Bearer {c['clave']}"},
                       json={"inputs": prompt, "parameters": {"width": ancho // 16 * 16, "height": alto // 16 * 16}})
        r.raise_for_status()
        return r.content

    def replicate():
        c = todas["replicate"]
        relacion = "9:16" if vertical else "16:9" if horizontal else "1:1"
        r = httpx.post(f"https://api.replicate.com/v1/models/{c['modelo_imagen']}/predictions", timeout=300,
                       headers={"Authorization": f"Bearer {c['clave']}", "Prefer": "wait"},
                       json={"input": {"prompt": prompt, "aspect_ratio": relacion, "output_format": "png"}})
        r.raise_for_status()
        p = r.json()
        while p["status"] not in ("succeeded", "failed", "canceled"):
            if not str(p["urls"]["get"]).startswith("https://api.replicate.com/"):  # la clave solo va a Replicate
                raise RuntimeError(t("Replicate devolvió una dirección inesperada"))
            time.sleep(2)
            p = httpx.get(p["urls"]["get"], headers={"Authorization": f"Bearer {c['clave']}"}, timeout=60).json()
        if p["status"] != "succeeded":
            raise RuntimeError(t("Replicate falló: {error}", error=p.get("error")))
        salida = p["output"][0] if isinstance(p["output"], list) else p["output"]
        return seguro.descargar(salida)

    def openai():
        c = todas["openai"]
        size = "1024x1536" if vertical else "1536x1024" if horizontal else "1024x1024"
        r = httpx.post("https://api.openai.com/v1/images/generations", timeout=300,
                       headers={"Authorization": f"Bearer {c['clave']}"},
                       json={"model": c["modelo_imagen"], "prompt": prompt, "size": size, "n": 1})
        r.raise_for_status()
        d = r.json()["data"][0]
        return base64.b64decode(d["b64_json"]) if d.get("b64_json") else seguro.descargar(d["url"])

    tareas = {"cloudflare": cloudflare, "pollinations": pollinations, "huggingface": huggingface, "replicate": replicate,
              "openai": openai, "gemini": lambda: _imagen_gemini(todas["gemini"], prompt, ancho, alto,
                                                                  calidad=calidad),
              "gratis_sin_clave": lambda: pollinations(con_clave=False)}
    tareas ={p: (lambda f=f: _imagen_real(f())) for p, f in tareas.items()}
    datos, _ = nubes.rotar("imagen", tareas)
    destino.write_bytes(datos)
    return destino


def cloudflare_partes(clave: str) -> tuple[str, str]:
    """La clave de Cloudflare se pega como «ID_de_cuenta token» (el ID son 32 caracteres hexadecimales)."""
    import re
    cuenta = re.search(r"\b[0-9a-f]{32}\b", clave).group()
    token = next(p for p in re.split(r"[\s:;,]+", clave) if p and p != cuenta)
    return cuenta, token


def video_desde_imagen(imagen_png: Path, prompt: str, formato: str, segundos: float, destino: Path,
                       pago: str | None = None) -> Path | None:
    """Anima una imagen con IA de video, probando primero lo gratis (ver nubes.ORDEN; Hugging Face va incluso sin
    clave). None solo si el usuario eligió «No usar» IA de video.
    pago: el video de pago (video_de_pago) que se preguntó al empezar el trabajo; solo ese se puede usar. Si el
    usuario elige otro a mitad del trabajo, esa escena no se paga (falla y va con zoom suave): vale para el siguiente."""
    from . import nube, nubes
    if claves.ajustes().get("video") == "ninguno":
        return None
    todas = claves.cargar()
    movimiento = f"{prompt}, cinematic motion, smooth camera movement"

    def huggingface():
        from gradio_client import handle_file
        # Cuota gratis diaria de GPU (ZeroGPU), anónima: el token nunca se manda a Spaces de terceros. Clips de ~5 s.
        salida, _ = nubes.llamar_space(claves.MODELO_VIDEO["huggingface"], handle_file(str(imagen_png)), movimiento,
                                       duration_seconds=min(max(segundos, 2), 5), api_name="/generate_video")
        return _clip_real(nubes.archivo_del_space(salida), destino)

    def pollinations():
        c = todas["pollinations"]
        relacion = "9:16" if formato in ("9:16", "4:5") else "16:9"
        url = (f"https://gen.pollinations.ai/video/{_ruta_url(prompt)}"
               f"?model={urllib.parse.quote(c['modelo_video'], safe='')}&duration={min(max(round(segundos), 2), 5)}"
               f"&aspectRatio={relacion}&audio=false&private=true")
        return _clip_real(seguro.descargar(url, {"Authorization": f"Bearer {c['clave']}"}, tope=VIDEO_MAXIMO, plazo=900),
                          destino)

    def de_pago(proveedor):  # Kling o Seedance (solo si el usuario lo eligió): clip mudo que el montaje repite
        modulo = claves.modulo_video(proveedor)
        _recordar_modelo(proveedor, "modelo_video",
                         modulo.animar(todas[proveedor], imagen_png, movimiento, destino, modulo.SEGUNDOS_CLIP))
        return destino

    resultado, _ = nubes.rotar("video", {
        "huggingface": huggingface,
        "modal": lambda: nube.animar(imagen_png, movimiento, formato, segundos, destino),
        "pollinations": pollinations,
        **{p: lambda p=p: de_pago(p) for p in claves.VIDEO_DE_PAGO if p == pago},  # solo el que se preguntó
    })
    return resultado


API_GEMINI = "https://generativelanguage.googleapis.com/v1beta"
OMNI = "gemini-omni-1.1-flash"  # si la API no dice cuál hay. Sustituye a Veo, que Google apagó el 22-10-2026
PRECIO_OMNI = 0.10  # US$ por segundo de video 720p según Google (sin cuota gratis)
PRECIO_IMAGEN = {"openai": 0.25, "replicate": 0.01}  # US$ por imagen, por lo alto (gpt-image en alta; FLUX schnell)
PRECIO_TRANSCRIPCION = 0.006  # US$ por minuto con la Whisper API de OpenAI (Groq y el PC: gratis)
MINUTOS_NUBE = 105  # lo más largo que transcribir() sube a la nube (25 MB a 32 kbps); lo que pasa, en el PC
IMAGEN_GEMINI = "gemini-nano-banana-2.1"  # Nano Banana 2.1, si la API no dice cuál hay
# US$ por imagen según el modelo y su calidad (imageSize), según Google el 22-10-2026 (sin cuota gratis): el Flash
# Image de respaldo (claves sin Nano Banana) cuesta casi el doble
PRECIO_IMAGEN_GEMINI = {IMAGEN_GEMINI: {"1K": 0.0336, "2K": 0.0504, "4K": 0.113},
                        "gemini-3.1-flash-image": {"1K": 0.067, "2K": 0.101, "4K": 0.151}}
PROPORCIONES_GEMINI = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")  # las que acepta
_elegidos = {}  # modelo elegido por clave y por uso, una vez por sesión
_cerrojo_modelos = threading.Lock()  # clips_hablados hace 3 videos a la vez y cada uno puede guardar su modelo


def video_de_pago() -> str | None:
    """Kling o Seedance si el usuario lo eligió para animar escenas y su clave está conectada (nubes.orden lo usa
    entonces solo a él): cada escena animada se paga. None si la animación es gratis o está apagada."""
    elegido = claves.ajustes().get("video")
    return elegido if elegido in claves.SOLO_ELIGIENDO["video"] and elegido in claves.cargar() else None


def nombre_video(proveedor: str) -> str:
    """El nombre del servicio de video de pago en las preguntas de costo y las notas de gasto."""
    return claves.modulo_video(proveedor).NOMBRE if proveedor in claves.VIDEO_DE_PAGO else "Gemini"


def precio_video(proveedor: str, segundos: float | None = None, voz: bool = False) -> float:
    """Lo más que cuesta un clip de video de pago (US$), el mismo número en todas las preguntas y notas de gasto.
    Kling y Seedance: lo calcula su módulo con la clave (sus respaldos pueden ser más caros); sin segundos, un clip
    como los pide el estudio. Gemini Omni (solo con voz): PRECIO_OMNI por segundo, y sus clips duran hasta 10 s."""
    if proveedor in claves.VIDEO_DE_PAGO:
        modulo = claves.modulo_video(proveedor)
        segundos = segundos or (modulo.SEGUNDOS_VOZ if voz else modulo.SEGUNDOS_CLIP)
        return modulo.estimar(claves.cargar().get(proveedor) or {}, segundos, voz)
    return (segundos or 10) * PRECIO_OMNI if proveedor == "gemini" and voz else 0.0


def nota_pago(proveedor: str, clips: int) -> str:
    """La nota de gasto de un trabajo: cuántos clips mudos hizo el servicio de pago y lo más que costaron."""
    return t("{proveedor} hizo {n} clip(s) de video: hasta unos US${costo} según su precio.",
             proveedor=nombre_video(proveedor), n=clips, costo=f"{clips * precio_video(proveedor):.2f}")


def _recordar_modelo(proveedor: str, campo: str, modelo: str) -> None:
    """Guarda con la clave el modelo que acaba de funcionar: la próxima vez se empieza por él, sin perder tiempo con
    los que la cuenta no puede usar. Nunca tumba el clip ya pagado (p. ej. claves.json abierto por otro proceso)."""
    try:
        with _cerrojo_modelos:
            info = claves.cargar().get(proveedor)
            if info and modelo and info.get(campo) != modelo:
                claves.guardar({**info, campo: modelo})
    except Exception:  # es solo para empezar antes la próxima vez
        pass


def _modelo_de_la_clave(clave: str, elegir: Callable[[list[str]], str | None], defecto: str) -> str:
    """Pregunta a la API qué modelos tiene la clave de Gemini y se queda con el que elige `elegir`."""
    if (clave, elegir) not in _elegidos:
        try:
            r = httpx.get(f"{API_GEMINI}/models", params={"pageSize": 1000}, headers={"x-goog-api-key": clave},
                          timeout=30)
            r.raise_for_status()
            _elegidos[clave, elegir] = elegir([m["name"] for m in r.json().get("models", [])]) or defecto
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return defecto  # sin red ahora: no se guarda, se pregunta otra vez la próxima
    return _elegidos[clave, elegir]


def modelo_video_voz(clave: str) -> str:
    return _modelo_de_la_clave(clave, claves.elegir_modelo_video_voz, OMNI)


def modelo_imagen_gemini(clave: str) -> str:
    return _modelo_de_la_clave(clave, claves.elegir_modelo_imagen_gemini, IMAGEN_GEMINI)


def precio_imagen_gemini(clave: str, calidad: str) -> float:
    """US$ por imagen con el modelo ya elegido para esa clave; si aún no se sabe (o no se conoce su precio), el más
    caro de los conocidos: el aviso de costo nunca se queda corto. No pregunta a la red."""
    precios = PRECIO_IMAGEN_GEMINI.get(_elegidos.get((clave, claves.elegir_modelo_imagen_gemini)))
    return precios[calidad] if precios else max(p[calidad] for p in PRECIO_IMAGEN_GEMINI.values())


def _imagen_gemini(c: dict, prompt: str, ancho: int, alto: int, referencia: Path | None = None,
                   calidad: str = "1K") -> bytes:
    """Una imagen con Gemini (Nano Banana, de pago): solo si el usuario lo eligió para las imágenes. Con
    `referencia`, la edita manteniendo igual a quien sale en ella. calidad: 1K, 2K o 4K (PRECIO_IMAGEN_GEMINI)."""
    partes = [{"text": prompt}]
    if referencia:
        tipo = {".png": "image/png", ".webp": "image/webp"}.get(referencia.suffix.lower(), "image/jpeg")
        partes.insert(0, {"inline_data": {"mime_type": tipo, "data": base64.b64encode(referencia.read_bytes()).decode()}})
    # La más cercana de las que acepta: un post 4:5 ya no sale recortado de un 9:16
    relacion = min(PROPORCIONES_GEMINI, key=lambda r: abs(math.log(ancho / alto / Fraction(r.replace(":", "/")))))
    r = httpx.post(f"{API_GEMINI}/models/{modelo_imagen_gemini(c['clave'])}:generateContent", timeout=300,
                   headers={"x-goog-api-key": c["clave"]}, json={
                       "contents": [{"parts": partes}],
                       "generationConfig": {"responseModalities": ["IMAGE"],
                                            "imageConfig": {"aspectRatio": relacion, "imageSize": calidad}}})
    if r.is_error:  # el motivo exacto (filtro, sin facturación, clave): el cuerpo no trae la clave
        raise RuntimeError(t("Gemini respondió {codigo}: {detalle}", codigo=r.status_code,
                             detalle=" ".join(r.text.split())[:300]))
    for parte in ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts", []):
        datos = parte.get("inlineData") or parte.get("inline_data") or {}
        if datos.get("data"):
            return _imagen_real(base64.b64decode(datos["data"]))
    raise RuntimeError(t("Gemini no devolvió ninguna imagen"))


def _bloque_video(nodo):
    """El primer bloque {"type": "video", ...} de la respuesta, esté donde esté."""
    if isinstance(nodo, dict):
        if nodo.get("type") == "video" and (nodo.get("uri") or nodo.get("data")):
            return nodo
        nodo = list(nodo.values())
    if isinstance(nodo, list):
        return next((b for b in map(_bloque_video, nodo) if b), None)
    return None


class Cobrado(RuntimeError):
    """Un video que el servicio de pago ya hizo (y puede haber cobrado) pero que no se pudo traer: la nota de gasto
    también lo cuenta, y nunca se prueba otra opción que lo pagaría dos veces (ver nubes.rotar)."""


def _borrar(url: str, cabecera: dict) -> None:
    try:
        httpx.delete(url, headers=cabecera, timeout=30)
    except httpx.HTTPError:  # no tumba un video ya hecho; si queda, Google lo borra solo (ver PRIVACIDAD.md)
        pass


def video_hablado(prompt: str, formato: str, destino: Path, referencia: Path | None = None,
                  quien: str | None = None) -> Path:
    """Un video de IA con su propio sonido: los personajes hablan con los labios sincronizados (de pago). Lo hace la
    IA elegida en «Escenas que hablan»: Gemini Omni (en Automático), Kling o Seedance.
    referencia: imagen del sujeto (tu foto o producto) que el video debe mantener; con Kling y Seedance, su primer
    fotograma. quien: el que se fijó (y se preguntó) al empezar el trabajo; sin él, el elegido ahora. Así, cambiar
    «Escenas que hablan» a mitad de un trabajo nunca paga con otro servicio."""
    quien = quien or (claves.para("video_voz") or {}).get("proveedor")
    if quien in claves.VIDEO_DE_PAGO:
        elegido = claves.cargar().get(quien)
        if not elegido:  # quitó la clave a mitad del trabajo
            raise SinClave(t("Para videos animados con voz conecta Gemini, Kling o Seedance en «Claves de IA» (Kling y "
                             "Seedance, elígelos en «Escenas que hablan»), o desmarca «Video animado con IA»."))
        modulo = claves.modulo_video(quien)
        _recordar_modelo(quien, "modelo_voz", modulo.hablar(elegido, referencia, prompt, destino, modulo.SEGUNDOS_VOZ))
        return destino
    c = claves.cargar().get("gemini")
    if not c:
        raise SinClave(t("Conecta tu clave de Gemini en «Claves de IA» para hacer videos animados con voz."))
    cabecera = {"x-goog-api-key": c["clave"]}
    entrada = prompt
    if referencia:
        tipo = {".png": "image/png", ".webp": "image/webp"}.get(referencia.suffix.lower(), "image/jpeg")
        entrada = [{"type": "image", "data": base64.b64encode(referencia.read_bytes()).decode(), "mime_type": tipo},
                   {"type": "text", "text": prompt}]
    r = httpx.post(f"{API_GEMINI}/interactions", headers=cabecera, timeout=900, json={
        "model": modelo_video_voz(c["clave"]), "input": entrada, "background": False, "stream": False,
        "store": True,  # sin esto Omni responde 400 («store=true is required»): lo guardado se borra en el finally
        "response_format": {"type": "video", "aspect_ratio": "16:9" if formato in ("16:9", "1:1") else "9:16",
                            "resolution": "720p", "delivery": "uri"}})
    if r.is_error:  # el motivo exacto (filtro de seguridad, sin facturación, clave): el cuerpo no trae la clave
        raise RuntimeError(t("Gemini respondió {codigo}: {detalle}", codigo=r.status_code,
                             detalle=" ".join(r.text.split())[:300]))
    respuesta = r.json()
    interaccion, archivo = str(respuesta.get("id", "")).removeprefix("interactions/"), None
    try:
        bloque = _bloque_video(respuesta)
        if not bloque:  # p. ej. lo frenó su filtro de seguridad: se dice lo que contestó
            raise RuntimeError(t("Gemini no devolvió ningún video: {detalle}",
                                 detalle=json.dumps(respuesta, ensure_ascii=False)[:300]))
        try:
            if bloque.get("data"):
                return _clip_real(base64.b64decode(bloque["data"]), destino)
            # La clave solo viaja a la API de Gemini, nunca a una dirección que venga en la respuesta.
            m = re.fullmatch(re.escape(API_GEMINI) + r"/files/([\w-]+)(?::download)?(?:\?.*)?", bloque["uri"])
            if not m:
                raise RuntimeError(t("Gemini devolvió una dirección inesperada"))
            archivo = f"{API_GEMINI}/files/{m[1]}"
            estado = None
            for _ in range(120):  # el video tarda un poco en quedar listo para bajar
                try:
                    estado = httpx.get(archivo, headers=cabecera, timeout=30).json().get("state")
                except (httpx.HTTPError, ValueError):  # un corte de red de un momento: se vuelve a mirar
                    estado = "PROCESSING"
                if estado != "PROCESSING":
                    break
                time.sleep(5)
            if estado in ("FAILED", "PROCESSING"):
                raise RuntimeError(t("Gemini no pudo terminar el video"))
            return _clip_real(seguro.descargar(f"{archivo}:download?alt=media", cabecera, tope=VIDEO_MAXIMO,
                                               plazo=300), destino)
        except Exception as error:  # Google ya lo hizo, y lo cobra
            raise Cobrado(str(error) or type(error).__name__) from error
    finally:  # lo guardado en Google (el pedido, la foto y el video) no se queda allí, salga bien o mal
        if archivo:
            _borrar(archivo, cabecera)
        if re.fullmatch(r"[\w-]+", interaccion):
            _borrar(f"{API_GEMINI}/interactions/{interaccion}", cabecera)


def voz_elevenlabs(texto: str, voice_id: str, destino: Path) -> list[dict]:
    """Narra con ElevenLabs y devuelve los tiempos por palabra (vienen por letra y se agrupan)."""
    c = claves.cargar().get("elevenlabs")
    if not c:
        raise SinClave(t("Conecta tu clave de ElevenLabs para usar sus voces."))
    r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
                   params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": c["clave"]}, timeout=300,
                   json={"text": texto, "model_id": c.get("modelo_voz", "eleven_multilingual_v2")})
    r.raise_for_status()
    d = r.json()
    destino.write_bytes(base64.b64decode(d["audio_base64"]))
    a = d.get("alignment") or {}
    palabras, actual = [], None
    for letra, ini, fin in zip(a.get("characters", []), a.get("character_start_times_seconds", []),
                               a.get("character_end_times_seconds", [])):
        if letra.isspace():
            actual = None
            continue
        if actual is None:
            actual = {"palabra": "", "inicio": ini, "fin": fin}
            palabras.append(actual)
        actual["palabra"] += letra
        actual["fin"] = fin
    return palabras


_WHISPER = {}


def transcribir(audio: Path, idioma: str | None = None, pista: str | None = None, cancion: bool = False,
                progreso=lambda f: None, en_pc: bool = False) -> list[dict]:
    """Devuelve las palabras con tiempos: [{'palabra', 'inicio', 'fin'}].
    Usa Groq/OpenAI si hay clave (rápido); si no, Whisper local en el PC (lento pero gratis).
    en_pc: siempre en el PC, aunque haya clave (la voz del usuario para el Director no sale de aquí)."""
    c = None if en_pc else claves.para("transcripcion")
    limite_api = 24 * 1024 * 1024  # Groq y OpenAI rechazan archivos de más de 25 MB
    if c and c.get("clave") and audio.stat().st_size > limite_api:
        from .video import ffmpeg
        ligero = audio.with_name(audio.stem + "_ligero.mp3")
        ffmpeg("-i", audio.resolve(), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", ligero.name,
               cwd=audio.parent)  # 32 kbps: hasta ~1 h 45 min caben en 25 MB
        audio = ligero
    # ponytail: audios de más de ~1 h 45 min no caben ni comprimidos: se transcriben en el PC (lento). Trocear si hace falta.
    if c and c.get("clave") and audio.stat().st_size <= limite_api:
        base = claves.OPENAI_COMPAT[c["proveedor"]]
        with open(audio, "rb") as f:
            r = httpx.post(f"{base}/audio/transcriptions", timeout=900,
                           headers={"Authorization": f"Bearer {c['clave']}"},
                           files={"file": (audio.name, f)},
                           data={"model": c["modelo_transcripcion"], "response_format": "verbose_json",
                                 "timestamp_granularities[]": "word", **({"language": idioma} if idioma else {}),
                                 **({"prompt": pista[:800]} if pista else {})})
        r.raise_for_status()
        return [{"palabra": w["word"].strip(), "inicio": w["start"], "fin": w["end"]} for w in r.json()["words"]]

    import subprocess

    import numpy as np
    from faster_whisper import WhisperModel

    from .video import FFMPEG, MEDIOS
    # Se decodifica con ffmpeg: la librería 'av' que trae faster-whisper choca con versiones nuevas.
    crudo = subprocess.run([FFMPEG, "-format_whitelist", MEDIOS, "-i", str(audio),
                            "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    if "small" not in _WHISPER:  # cargarlo tarda: se reutiliza en cada escena y en cada orden de voz
        _WHISPER["small"] = WhisperModel("small", device="cpu", compute_type="int8")
    modelo = _WHISPER["small"]
    # `pista` (p. ej. la letra) ayuda a Whisper a acertar palabras cantadas o con jerga.
    muestras = np.frombuffer(crudo, np.float32)
    segmentos, _ = modelo.transcribe(muestras, language=idioma, initial_prompt=pista,
                                     word_timestamps=True, vad_filter=not cancion)  # el filtro de voz corta lo cantado
    total, palabras = len(muestras) / 16000, []
    for s in segmentos:  # se va transcribiendo por trozos: se informa cuánto lleva
        palabras += [{"palabra": w.word.strip(), "inicio": w.start, "fin": w.end} for w in s.words]
        progreso(min(s.end / total, 1))
    return palabras
