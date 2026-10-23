"""Llamadas a IA usando la clave que el usuario haya conectado (ver claves.py)."""
import base64
import json
import time
import urllib.parse
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
    if tipo == "array" and isinstance(datos, str) and esquema.get("items", {}).get("type") == "string":
        import re
        return [p for p in re.split(r"[\s,]+", datos) if p]
    if tipo == "object" and isinstance(datos, dict):
        return {k: _normalizar(v, esquema.get("properties", {}).get(k, {})) for k, v in datos.items()}
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


def _texto_gratis(instrucciones: str, pedido: str, esquema: dict) -> dict:
    """IA de texto gratis y sin clave (GPT-OSS 20B en Pollinations).
    ponytail: límite de 1 respuesta cada 30 s por conexión y menos calidad; con Groq/Gemini (gratis) va mejor."""
    mensajes = [{"role": "system", "content": f"{instrucciones}\n\nResponde SOLO con un objeto JSON válido, sin "
                                              f"texto antes ni después, que cumpla este esquema:\n"
                                              f"{json.dumps(esquema, ensure_ascii=False)}\n"
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
            if valido is not None:
                return valido
            problema = t("faltan o están mal: {campos}",
                         campos=", ".join(_faltan(_normalizar(datos, esquema), esquema)[:5]))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            problema = t("respuesta no válida: {error}", error=e)
    raise RuntimeError(t("La IA gratis sin clave no dio una respuesta válida ({problema}). Conecta Groq o Gemini "
                         "(gratis) en «Claves de IA» para más calidad.", problema=problema))


def texto_json(instrucciones: str, pedido: str, esquema: dict) -> dict:
    """Pide a la IA de texto una respuesta JSON que cumpla `esquema`.
    Sin ninguna clave de texto conectada usa la IA gratis sin clave (más simple, pero funciona)."""
    c = claves.para("texto")
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


def imagen_con_producto(prompt: str, foto: Path, ancho: int, alto: int, destino: Path) -> Path:
    """Escena realista con el producto real de la foto. Usa edición con referencia si la IA de imágenes la tiene;
    si no, crea el fondo y coloca encima la foto del producto."""
    c = claves.para("imagen")
    vertical, horizontal = alto > ancho, ancho > alto
    size = "1024x1536" if vertical else "1536x1024" if horizontal else "1024x1024"
    # Sirve igual para productos que para personas, personajes o lugares de la foto de referencia.
    pedido = (f"{prompt}. Keep the subject from the reference image identical (same face, shape, colors, "
              "label and logo). Photorealistic.")
    if c and c.get("clave") and c["proveedor"] in ("openai", "pollinations"):
        base = "https://api.openai.com/v1" if c["proveedor"] == "openai" else "https://gen.pollinations.ai/v1"
        modelo = c["modelo_imagen"] if c["proveedor"] == "openai" else "black-forest-labs/flux.1-kontext-pro"
        with open(foto, "rb") as f:
            r = httpx.post(f"{base}/images/edits", timeout=300, headers={"Authorization": f"Bearer {c['clave']}"},
                           files={"image": (foto.name, f, "image/png" if foto.suffix.lower() == ".png" else "image/jpeg")},
                           data={"model": modelo, "prompt": pedido, "size": size, "n": "1",
                                 **({"private": "true"} if c["proveedor"] == "pollinations" else {})})
        r.raise_for_status()
        d = r.json()["data"][0]
        destino.write_bytes(_imagen_real(base64.b64decode(d["b64_json"]) if d.get("b64_json")
                                         else seguro.descargar(d["url"])))
        return destino
    # ponytail: sin edición con referencia el producto se pega encima del fondo; queda menos natural.
    from .video import ffmpeg
    fondo = imagen(f"{prompt}, empty space in the center for a product, no product", ancho, alto,
                   destino.with_name(destino.stem + "_fondo.png"))
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


def imagen(prompt: str, ancho: int, alto: int, destino: Path) -> Path:
    """Genera una imagen y la guarda en `destino`, probando primero lo gratis (ver nubes.ORDEN["imagen"])."""
    from . import nubes
    todas = claves.cargar()
    vertical, horizontal = alto > ancho, ancho > alto
    semilla = int(time.time()) % 2_000_000_000

    def cloudflare():
        # 10.000 "neuronas" gratis al día: ~100 imágenes FLUX schnell. Sale cuadrada; el montaje la recorta al formato.
        cuenta, token = cloudflare_partes(todas["cloudflare"]["clave"])
        r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/black-forest-labs/"
                       "flux-1-schnell", headers={"Authorization": f"Bearer {token}"}, timeout=300,
                       json={"prompt": prompt[:2048], "steps": 8, "seed": semilla})
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
              "openai": openai, "gratis_sin_clave": lambda: pollinations(con_clave=False)}
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


def video_desde_imagen(imagen_png: Path, prompt: str, formato: str, segundos: float, destino: Path) -> Path | None:
    """Anima una imagen con IA de video, probando primero lo gratis (ver nubes.ORDEN; Hugging Face va incluso sin
    clave). None solo si el usuario eligió «No usar» IA de video."""
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

    resultado, _ = nubes.rotar("video", {
        "huggingface": huggingface,
        "modal": lambda: nube.animar(imagen_png, movimiento, formato, segundos, destino),
        "pollinations": pollinations,
    })
    return resultado


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


def transcribir(audio: Path, idioma: str | None = None, pista: str | None = None, cancion: bool = False,
                progreso=lambda f: None) -> list[dict]:
    """Devuelve las palabras con tiempos: [{'palabra', 'inicio', 'fin'}].
    Usa Groq/OpenAI si hay clave (rápido); si no, Whisper local en el PC (lento pero gratis)."""
    c = claves.para("transcripcion")
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
    modelo = WhisperModel("small", device="cpu", compute_type="int8")
    # `pista` (p. ej. la letra) ayuda a Whisper a acertar palabras cantadas o con jerga.
    muestras = np.frombuffer(crudo, np.float32)
    segmentos, _ = modelo.transcribe(muestras, language=idioma, initial_prompt=pista,
                                     word_timestamps=True, vad_filter=not cancion)  # el filtro de voz corta lo cantado
    total, palabras = len(muestras) / 16000, []
    for s in segmentos:  # se va transcribiendo por trozos: se informa cuánto lleva
        palabras += [{"palabra": w.word.strip(), "inicio": w.start, "fin": w.end} for w in s.words]
        progreso(min(s.end / total, 1))
    return palabras
