"""Llamadas a IA usando la clave que el usuario haya conectado (ver claves.py)."""
import base64
import contextlib
import contextvars
import json
import math
import re
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from fractions import Fraction
from typing import Callable
from pathlib import Path

import httpx

from . import actividad, claves, guardia, seguro
from .idioma import dinero, t, texto_de_error

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


def guardar_imagen(datos: bytes, destino: Path) -> Path:
    """La imagen en `destino` con el formato que dice su nombre: Pollinations, Gemini o el Space gratis dan JPEG o
    WEBP aunque se guarde como .png (otros programas lo abren mal). Si no coincide, se convierte (de pie, como en el
    móvil); un nombre de otro tipo se guarda tal cual."""
    firma = {".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}.get(destino.suffix.lower(), b"")
    if datos.startswith(firma):
        destino.write_bytes(datos)
        return destino
    from PySide6.QtCore import QBuffer
    from PySide6.QtGui import QImageReader
    memoria = QBuffer()  # en una variable: el lector no lo mantiene vivo
    memoria.setData(datos)
    lector = QImageReader(memoria)
    lector.setAutoTransform(True)
    if not lector.read().save(str(destino)):  # una imagen que no se pudo leer (nula) tampoco se guarda
        raise RuntimeError(t("No se pudo guardar la imagen en {destino}.", destino=destino))
    return destino


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
# La regla común de texto plano: lo que escribe la IA se enseña, se dice en voz alta y se publica tal cual
TEXTO_PLANO = ("Escribe cada texto como texto normal, sin Markdown: nada de **negritas**, # títulos, listas con * o -, "
               "`código`, tablas ni [enlaces](url); si hace falta una lista, un punto por línea. Lo que dice una voz "
               "(narración, diálogos), solo palabras: sin emojis, hashtags ni enlaces.")

_ETIQUETA = re.compile(r"</?(?:b|i|u|s|em|strong|p|span|div|h[1-6]|ul|ol|li|a|code|pre|font|small|sup|sub|del|ins|"
                       r"mark|blockquote|hr|table|thead|tbody|tr|td|th)\b[^>\n]*>", re.I)
_BLOQUE = re.compile(r"^[ \t]*```.*(?:\n|$)", re.M)  # la línea entera de un ```: no deja un hueco
_TITULO = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.M)
_CITA = re.compile(r"^[ \t]*>[ \t]?", re.M)
_RAYA = re.compile(r"^[ \t]*([-*_])([ \t]*\1){2,}[ \t]*$", re.M)  # --- *** ___
_LISTA = re.compile(r"^[ \t]*[*+\-•][ \t]+", re.M)
_TABLA_SEP = re.compile(r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$", re.M)
_TABLA = re.compile(r"^[ \t]*\|(.*)\|[ \t]*$", re.M)
_ENLACE = re.compile(r"!?\[([^\]\n]+)\]\((\S+?)\)")  # solo [texto](url): los huecos [Precio] y el [Chorus] se quedan
_MARCAS = [(re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"), r"\1"), (re.compile(r"__(?=\S)(.+?)(?<=\S)__"), r"\1"),
           (re.compile(r"~~(?=\S)(.+?)(?<=\S)~~"), r"\1"), (re.compile(r"`([^`\n]+)`"), r"\1"),
           # *cursiva* y _cursiva_ sin tocar «5 * 3» ni los nombres_con_guion_bajo
           (re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])"), r"\1"),
           (re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])"), r"\1")]
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")  # emojis y sus uniones


def sin_markdown(texto, para: str = "texto") -> str:
    """El texto que escribió una IA, listo para enseñarlo, decirlo o publicarlo: sin Markdown (**, #, listas con * o -,
    `código`, tablas, [enlaces](url)), sin entidades HTML (&amp;), etiquetas (<br>) ni «\\n» escritos como texto.
    para: «texto» (chat, descripciones: guarda los saltos de línea; listas con «•»; enlaces «texto: url»),
    «linea» (títulos y etiquetas: una sola línea) o «voz» (lo que lee la voz y sale en los subtítulos: solo palabras,
    sin enlaces, emojis ni símbolos; cada línea, una frase). Las «comillas», ¿?, ¡!, el ·, los [Chorus] de una letra,
    los huecos [Precio] y (salvo en «voz») los #hashtags y emojis se quedan."""
    import html
    s = str(texto or "").replace("\\r", "").replace("\\n", "\n").replace("\\t", " ").replace("\r", "")
    s = html.unescape(re.sub(r"<br\s*/?>", "\n", s, flags=re.I))
    s = _ETIQUETA.sub("", s)  # <b>, <p>… que algunas IA mezclan (un «<3» o un «<video>» escrito a mano se quedan)
    s = _BLOQUE.sub("", s)
    s = _TABLA_SEP.sub("", s)
    s = _TABLA.sub(lambda m: " · ".join(c.strip() for c in m[1].split("|") if c.strip()), s)
    s = _RAYA.sub("", s)
    s = _TITULO.sub("", s)
    s = _CITA.sub("", s)
    s = _LISTA.sub("" if para in ("voz", "linea") else "• ", s)
    s = _ENLACE.sub(lambda m: m[1] if para == "voz" or m[1] == m[2] else f"{m[1]}: {m[2]}", s)
    for patron, cambio in _MARCAS:
        s = patron.sub(cambio, s)
    s = re.sub(r"\\([\\*_#`~\[\]()>|-])", r"\1", s)  # \* \# escapados de Markdown
    if para == "voz":
        s = re.sub(r"https?://\S+|www\.\S+", "", s)
        s = _EMOJI.sub("", s)
        s = re.sub(r"#(\w)", r"\1", s)
        s = re.sub(r"[*_~`#|\\^•<>]", " ", s)
        # cada línea, una frase: la voz hace la pausa y los subtítulos no juntan dos frases
        s = " ".join(l if l[-1] in ".!?…:;,»\"" else l + "." for l in (" ".join(x.split()) for x in s.split("\n")) if l)
    elif para == "linea":
        s = " ".join(s.split())
    else:
        s = re.sub(r"\n{3,}", "\n\n", "\n".join(l.rstrip() for l in s.split("\n")))
    return s.strip()


def _limpio(datos):
    """Cada texto de una respuesta de la IA, sin Markdown (ver sin_markdown). Un texto que es JSON escrito como texto
    (los «argumentos» del Director) se deja tal cual: limpiarlo lo rompería."""
    if isinstance(datos, dict):
        return {k: _limpio(v) for k, v in datos.items()}
    if isinstance(datos, list):
        return [_limpio(d) for d in datos]
    if isinstance(datos, str):
        if datos.lstrip()[:1] in ("{", "["):
            try:
                json.loads(datos)
                return datos
            except ValueError:
                pass
        return sin_markdown(datos)
    return datos


def recortar(texto: str, largo: int) -> str:
    """Como mucho `largo` letras, cortado en el último espacio y con «…»: nunca a mitad de palabra."""
    texto = str(texto or "").strip()
    if len(texto) <= largo:
        return texto
    corte = texto[:max(largo - 1, 1)]
    if not (corte[-1].isspace() or texto[len(corte)].isspace()) and " " in corte.strip():
        corte = corte.rsplit(None, 1)[0]  # sin la palabra que quedaba a medias
    return corte.rstrip(" ,;:") + "…"


def hashtag(texto: str) -> str:
    """Un hashtag que funciona: «comida dominicana» → #comidadominicana, «**#viral**» → #viral (respeta tildes y ñ)."""
    return "#" + "".join(re.findall(r"\w+", str(texto)))


# Las marcas de sección ([Chorus]) y las acotaciones para el modelo de música: una línea entera entre paréntesis, o un
# paréntesis que empieza con una indicación en inglés («(Shout: ¡Wepa!)», «(Fade out with tambora…)»)
_SECCION = re.compile(r"(?m)^[ \t]*\[[^\]\n]+\][ \t]*$")
_ACOTACION = re.compile(r"(?im)^[ \t]*\([^()\n]*\)[ \t]*$|[ \t]*\((?:shout|spoken|whisper|fade|repeat|x ?\d|"
                        r"instrumental|ad[- ]?libs?|echo|sound|music|laugh|yell|scream|backing|harmony|crowd|beat|"
                        r"break|pause|intro|outro|chorus|verse|bridge|hook)\b[^()\n]*\)")


def sin_acotaciones(letra: str) -> str:
    """La letra como se lee y se publica: sin [Chorus] ni acotaciones como «(Shout: …)» o «(Fade out …)», que son
    solo para el modelo de música (se publicaban y salían en el karaoke)."""
    return re.sub(r"\n{3,}", "\n\n", _ACOTACION.sub("", _SECCION.sub("", str(letra or "")))).strip()


def _mensaje_de(nodo) -> str | None:
    """El primer texto de una respuesta JSON de error: su «message» (o «detail», «error»…), también dentro de listas."""
    if isinstance(nodo, str):
        return nodo.strip() or None
    if isinstance(nodo, dict):
        for k in ("message", "msg", "detail", "error_description", "error", "errors"):
            if (encontrado := _mensaje_de(nodo.get(k))) is not None:
                return encontrado
        return next((e for e in map(_mensaje_de, nodo.values()) if e), None)
    if isinstance(nodo, list):
        return next((e for e in map(_mensaje_de, nodo) if e), None)
    return None


def motivo(r: httpx.Response) -> str:
    """El porqué de un error de un servicio, en una línea y corta: su «message» y no el JSON entero con códigos
    internos; si la respuesta no es JSON (p. ej. una página de error 502), su texto sin etiquetas."""
    try:
        texto = _mensaje_de(json.loads(r.text))
    except ValueError:
        texto = None
    if texto is None:
        import html
        texto = html.unescape(re.sub(r"<[^>]*>", " ", r.text or ""))
    return recortar(" ".join(texto.split()), 300) or str(r.status_code)


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
        raise ValueError(t("La IA respondió algo que no se entiende."))
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
    if tipo == "string" and isinstance(datos, list) and all(isinstance(d, (str, int, float)) for d in datos):
        # una lista donde va un texto («Por qué es viral: ["Mucho público", …]»): un punto por línea, no JSON
        return "\n".join(f"• {d}" for d in datos)
    if tipo == "string" and isinstance(datos, (dict, list)):  # p. ej. los argumentos del Director como objeto
        return json.dumps(datos, ensure_ascii=False)
    if tipo == "array" and isinstance(datos, str) and esquema.get("items", {}).get("type") == "string":
        # Por comas; por espacios solo si todo son #hashtags: «Instagram Reels, YouTube Shorts» no se parte en cuatro
        trozos = []
        for parte in re.split(r"\s*,\s*", datos.strip()):
            palabras = parte.split()
            trozos += palabras if palabras and all(p.startswith("#") for p in palabras) else [parte] if parte else []
        return trozos
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
    return _limpio(valido)  # lo escribe un agente de fuera: el mismo texto plano que lo de la IA de la app


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
            # tope de tamaño y de tiempo total: es un servicio abierto, sin cuenta (ver seguro.pedir)
            r = seguro.pedir("POST", "https://text.pollinations.ai/openai", plazo=300,
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
                actividad.anotar("texto", "gratis_sin_clave", "openai")
                return valido
            faltan = ", ".join(_faltan(_normalizar(datos, esquema), esquema)[:5])
            problema = (t("devolvió el ejemplo sin rellenar") if valido is not None
                        else t("faltan o están mal: {campos}", campos=faltan))
        except (ValueError, KeyError, IndexError, TypeError):  # el detalle (en inglés, de Python) va a la consola
            traceback.print_exc()
            problema = t("respuesta no válida")
    actividad.anotar("texto", "gratis_sin_clave", "openai", error=problema)
    raise RuntimeError(t("La IA gratis sin clave no dio una respuesta válida ({problema}). Conecta Groq o Gemini "
                         "(gratis) en «Claves de IA» para más calidad.", problema=problema))


VEN_IMAGENES = ("anthropic", "openai", "gemini")  # las IA de texto que ven fotos (Gemini, por su API compatible)
MAX_FOTOS_VISTAS, LADO_FOTO_VISTA = 4, 768  # unos 800 tokens por foto con Claude: céntimos de dólar


def ve_fotos(uso: str = "texto") -> bool:
    """Si la IA de texto elegida ve las fotos que se le dan (con_fotos); si no, solo lee su nombre."""
    c = claves.para(uso) or {}
    return bool(c.get("clave")) and c.get("proveedor") in VEN_IMAGENES


def con_fotos(texto: str, rutas, uso: str = "texto") -> str | list:
    """El pedido con las fotos que dio el usuario, para que la IA de texto las VEA y no solo su nombre (pasó: con
    «hazme una versión de anuncio» y una foto, Claude solo veía «IMG_2041.jpg» y preguntaba qué era): el texto y hasta
    MAX_FOTOS_VISTAS fotos en JPEG pequeño, si la IA elegida ve imágenes (VEN_IMAGENES). Si no, o no hay ninguna foto
    (un video, un audio, un archivo que no está), el texto tal cual. Si al final responde otra IA que no las ve,
    recibe solo el texto (_para)."""
    if not ve_fotos(uso):
        return texto
    from PySide6.QtCore import QBuffer, QIODevice, Qt
    from PySide6.QtGui import QImageReader
    bloques = []
    for ruta in rutas or ():
        if len(bloques) == 2 * MAX_FOTOS_VISTAS:
            break
        try:  # una carpeta de red ni se toca (seguro.archivo_medio)
            lector = QImageReader(str(seguro.archivo_medio(ruta, seguro.IMAGENES, t("imagen"))))
        except ValueError:
            continue
        lector.setAutoTransform(True)  # la foto del móvil, derecha
        imagen, jpeg = lector.read(), QBuffer()
        jpeg.open(QIODevice.WriteOnly)
        if imagen.isNull() or not imagen.scaled(LADO_FOTO_VISTA, LADO_FOTO_VISTA, Qt.KeepAspectRatio,
                                                Qt.SmoothTransformation).save(jpeg, "JPEG", 85):
            continue
        bloques += [{"type": "text", "text": f"Foto {Path(ruta).name}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.b64encode(bytes(jpeg.data())).decode()}}]
    return [{"type": "text", "text": texto}, *bloques] if bloques else texto


def _para(c: dict, pedido):
    """El pedido como lo entiende esa IA: las fotos (con_fotos) como bloque «image» para Claude o «image_url» para
    OpenAI y Gemini; a una que no ve imágenes (Groq, la gratis), solo los textos."""
    if isinstance(pedido, str):
        return pedido
    if c.get("proveedor") not in VEN_IMAGENES:
        return "\n\n".join(b["text"] for b in pedido if b.get("type") == "text")
    if c["proveedor"] == "anthropic":
        return pedido
    return [{"type": "image_url", "image_url": {"url": f"data:{b['source']['media_type']};base64,"
                                                      f"{b['source']['data']}"}} if b.get("type") == "image" else b
            for b in pedido]


def texto_json(instrucciones: str, pedido: str | list, esquema: dict, uso: str = "texto",
               rapido: bool = False, solo_elegida: bool = False) -> dict:
    """Pide a la IA de texto una respuesta JSON que cumpla `esquema`. uso: «texto», o «diseno» para la IA que diseña
    (claves.para). Sin ninguna clave de texto conectada usa la IA gratis sin clave (más simple, pero funciona).
    Cada texto de la respuesta llega sin Markdown (ver _limpio): se enseña, se dice y se publica tal cual.
    rapido: para lo que no necesita que el modelo piense antes (cada paso del Director, entender un pedido); ver
    _sin_razonar. Los guiones y los diseños van sin él, con toda su calidad. pedido: un texto, o el de con_fotos.
    solo_elegida: si esa IA no atiende, no se prueba otra: el usuario dio el permiso para ella."""
    instrucciones = f"{instrucciones}\n\n{TEXTO_PLANO}"
    c = claves.para(uso)
    if not c or not c.get("clave"):
        return _limpio(_texto_gratis(instrucciones, _para({}, pedido), esquema))
    try:
        return _pedir(c, instrucciones, pedido, esquema, rapido)
    except SinServicio as fallo:
        primero = fallo
    if solo_elegida:
        _no_atendio(c, primero, "")
        raise primero
    # Sin saldo, sin cuota, clave caducada o el servicio caído (pasó: Gemini sin saldo prepago dejaba todo el estudio
    # sin IA de texto aunque Groq, gratis, estaba conectado): se prueban las demás IA de texto conectadas y, al final,
    # la gratis sin clave. Ese pedido no se cobró, así que no se paga dos veces. Cada una que no atiende queda en la
    # actividad de la IA con la que se probó después («pasó a Groq»).
    todas = claves.cargar()
    resto = [p for p in claves.PREFERENCIA[uso]
             if p != c["proveedor"] and p in todas and "texto" in claves.USOS.get(p, [])]
    # Demasiado grande para una gratis: no pasa sin aviso a una de pago (ni se apunta como «sin cuota»: no avisaría nadie)
    if getattr(primero, "codigo", 0) == 413 and c["proveedor"] not in PRECIO_TEXTO:
        resto = [p for p in resto if p not in PRECIO_TEXTO]
    cola = [c["proveedor"], *resto, "gratis_sin_clave"]
    _no_atendio(c, primero, cola[1])
    for i, otro in enumerate(resto, 1):
        try:
            resultado = _pedir(todas[otro], instrucciones, pedido, esquema, rapido)
        except SinServicio as fallo:
            _no_atendio(todas[otro], fallo, cola[i + 1])
            continue
        print(f"[Ráfaga] {claves.nombre(c['proveedor'])}: {getattr(primero, 'corto', primero)} Se usó "
              f"{claves.nombre(otro)}.", file=sys.stderr, flush=True)
        return resultado
    try:
        return _limpio(_texto_gratis(instrucciones, _para({}, pedido), esquema))
    except Exception:  # noqa: BLE001  ni la gratis: el motivo que se enseña es el de la IA elegida
        raise primero from None


class SinServicio(RuntimeError):
    """La IA de texto no atendió (401, 402, 403, 429 o 5xx): ese pedido no se cobró y se puede probar otra. También
    Gemini al dibujar, con cualquier error: los anuncios pegan entonces la foto sobre una escena (no se paga dos veces)."""


_SIN_SERVICIO = {401, 402, 403, 413, 429}  # 413: un pedido más grande que el límite por minuto de Groq gratis: no se cobró
# US$ por millón de tokens (entrada, salida) de la IA de texto, por lo alto, para el gasto estimado de «Actividad de la
# IA» (un guion cuesta céntimos: no se pregunta). Groq y Pollinations van con su plan gratis. Gemini, lo que cobra con
# la facturación activada (con su cuota gratis no cuesta nada, pero no se puede saber cuál usa la clave).
# Claude, por modelo (los dos que se eligen en «Claves de IA»: claves.MODELOS_CLAUDE); «anthropic», el de fábrica.
PRECIO_TEXTO = {"anthropic": (4.0, 20.0), "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0),
                "openai": (2.5, 15.0), "gemini": (0.5, 3.0), "openrouter": (3.0, 15.0), "xai": (3.0, 15.0),
                "deepseek": (0.6, 2.5)}
LEER_CACHE_CLAUDE = 0.20  # US$ por millón de tokens leídos de la caché (Opus 5.5 y Sonnet 5.5); escribirla, 1,25 × entrada
BUSQUEDA_WEB = 0.01  # US$ por búsqueda web de Claude (US$10 las mil)


def costo_texto(proveedor: str, entrada, salida) -> float:
    """Lo que cuesta como mucho un pedido de texto con esos tokens (0 si es gratis)."""
    precio_entrada, precio_salida = PRECIO_TEXTO.get(proveedor, (0.0, 0.0))
    try:
        return (float(entrada or 0) * precio_entrada + float(salida or 0) * precio_salida) / 1_000_000
    except (TypeError, ValueError):
        return 0.0


def _no_atendio(c: dict, fallo: "SinServicio", siguiente: str) -> None:
    actividad.anotar("texto", c["proveedor"], c.get("modelo_texto") or "", error=getattr(fallo, "corto", fallo),
                     paso_a=siguiente)


SALTO = 3600  # s: lo que se salta una IA sin saldo o con la clave mal antes de volver a probarla (pudo recargar)


def _saltado(c: dict) -> SinServicio | None:
    """El fallo, sin pedirle nada, de una IA que ya se sabe que no atiende: sin saldo o con la clave mal, comprobado
    hace menos de SALTO (pasó: cada paso del Director esperaba 1-3 s el 402 de Gemini antes de ir a Groq).
    Se le vuelve a pedir pasado SALTO, cuando «Comprobar conexiones» dice que ya atiende o al conectar otra clave
    suya. Sin cuota no se salta: suele ser el límite por minuto y pasa enseguida. Tampoco un 403 que no habla de la
    clave (p. ej. la moderación de OpenRouter): la clave sí vale."""
    malo = claves._vigente(c["proveedor"], claves.BLOQUEA, SALTO)
    if not malo:
        return None
    detalle = str(malo.get("detalle", ""))
    if malo["estado"] == "clave" and detalle.startswith("403") and not re.search(r"key|token", detalle, re.I):
        return None
    problema = claves.frase(c["proveedor"], malo["estado"])
    fallo = SinServicio(f"{problema}. {claves.paso(c['proveedor'], malo['estado'])}")
    fallo.corto = t("No se le pidió: {problema} ({cuando}).", problema=problema, cuando=claves._cuando(malo))
    return fallo


def _pedir(c: dict, instrucciones: str, pedido: str | list, esquema: dict, rapido: bool = False) -> dict:
    """_texto_con, salvo que ya se sepa que esa IA no atiende (_saltado): entonces falla sin esperar a su servicio.
    Las fotos del pedido, como las ve esa IA (_para)."""
    if fallo := _saltado(c):
        raise fallo
    return _texto_con(c, instrucciones, _para(c, pedido), esquema, rapido)


def _sin_razonar(proveedor: str, modelo: str) -> dict:
    """Lo que apaga (o deja al mínimo) el razonamiento escondido de un modelo que piensa antes de responder, para lo
    que no lo necesita: esos tokens son lo que más tarda y gastan el límite de tokens por minuto de la cuenta gratis de
    Groq (al pasarlo, la respuesta espera). {} si no se sabe cómo: algo que el modelo no admite da 400."""
    if proveedor != "groq":
        return {}
    if "qwen3" in modelo.lower():
        return {"reasoning_effort": "none"}
    return {"reasoning_effort": "low"} if "gpt-oss" in modelo.lower() else {}


def _error_texto(c: dict, codigo: int, detalle: str) -> RuntimeError:
    """El error de un servicio de texto que respondió `codigo`, en claro. SinServicio si no atendió (se prueba otra IA
    y lo apunta texto_json, que sabe cuál); si no, queda apuntado aquí. El estado del servicio se pone al día."""
    claves.recordar(c["proveedor"], codigo, detalle)
    # Claude sin saldo y Gemini con la clave mal responden 400 («credit balance is too low», «API key not valid»): no
    # cobran y otra IA sí puede; un 400 de verdad (el pedido está mal) no se repite con otra
    no_atiende = codigo in _SIN_SERVICIO or codigo >= 500 or claves.clasificar(codigo, detalle) in claves.BLOQUEA
    clase = SinServicio if no_atiende else RuntimeError
    error = clase(t("La IA de texto ({proveedor}) respondió {codigo}: {detalle}", proveedor=claves.nombre(c["proveedor"]),
                    codigo=codigo, detalle=detalle))
    error.corto, error.codigo = f"{codigo}: {detalle}", codigo
    if clase is RuntimeError:
        actividad.anotar("texto", c["proveedor"], c.get("modelo_texto") or "", error=error.corto)
    return error


# Los pedidos dentro de `with charla():` son turnos de conversación (el Director): ver _texto_con
_CHARLA = contextvars.ContextVar("charla_claude", default=False)
PLAZO_CLAUDE = 120  # s sin recibir nada de Claude (en streaming llega algo cada pocos segundos): la conexión se cayó


@contextlib.contextmanager
def charla():
    """Los pedidos de dentro son turnos de una conversación: con Claude piensan poco y guardan sus instrucciones en caché."""
    marca = _CHARLA.set(True)
    try:
        yield
    finally:
        _CHARLA.reset(marca)


def _claude(c: dict):
    """El cliente de Claude con plazos: el de fábrica espera 10 min por intento y lo repite dos veces (30 min sin
    noticias: así se vio el investigador de nichos «colgado»)."""
    import anthropic
    return anthropic.Anthropic(api_key=c["clave"], timeout=anthropic.Timeout(PLAZO_CLAUDE, connect=15.0))


def _error_claude(c: dict, e) -> RuntimeError:
    """_error_texto de un anthropic.APIStatusError. Uno a mitad del stream (p. ej. «overloaded») llega con el 200 del
    principio y su cuerpo ya leído en e.body: e.response.text no se puede leer ahí (salía httpx2.ResponseNotRead, en
    inglés, sin apuntar y sin probar otra IA). Se toma como 529: no atendió."""
    detalle = _mensaje_de(e.body) if isinstance(e.body, dict) else None
    return _error_texto(c, e.status_code if e.status_code >= 400 else 529,
                        recortar(" ".join(detalle.split()), 300) if detalle else motivo(e.response))


def _costo_claude(modelo: str, uso, largo: float = 0, busquedas: int = 0) -> float:
    """Lo que costó un pedido a Claude con los tokens que dice su respuesta: la entrada, la que se escribió en caché
    (1,25 × entrada) y la que se leyó de ella, la salida y cada búsqueda web. Sin `uso`, la entrada se estima (`largo`)."""
    entrada, salida = PRECIO_TEXTO.get(modelo, PRECIO_TEXTO["anthropic"])

    def tokens(campo, otro=0):
        return float(getattr(uso, campo, otro) or 0)
    return (tokens("input_tokens", largo) * entrada + tokens("cache_creation_input_tokens") * entrada * 1.25
            + tokens("cache_read_input_tokens") * LEER_CACHE_CLAUDE + tokens("output_tokens") * salida) / 1_000_000 \
        + busquedas * BUSQUEDA_WEB


def _texto_con(c: dict, instrucciones: str, pedido: str, esquema: dict, rapido: bool = False) -> dict:
    """Un pedido JSON a la IA de texto `c` (Claude, o cualquiera compatible con OpenAI). Cada respuesta queda en la
    actividad de la IA con lo que costó (sus tokens). rapido: sin razonamiento escondido (_sin_razonar)."""
    nombre, modelo = claves.nombre(c["proveedor"]), c.get("modelo_texto") or ""
    largo = (len(instrucciones) + len(pedido) + len(json.dumps(esquema))) / 3  # tokens, si el servicio no los dice
    if c["proveedor"] == "anthropic":
        import anthropic
        # Lo rápido (un paso del Director, entender un pedido) y el repaso de ortografía: piensa poco y responde en
        # segundos. Los guiones y los análisis, «medium» (el de fábrica de Opus 5.5; Sonnet 5.5 traería «high», más lento).
        charla = _CHARLA.get()
        rapido = rapido or charla or esquema == _ESQUEMA_ORTOGRAFIA  # por contenido: una copia también es rápida
        try:
            with _claude(c).messages.stream(
                # En streaming un tope alto no cuesta si no se usa, y lo que piensa también cuenta en él
                model=modelo, max_tokens=16000 if rapido else 64000,
                # El Director manda las mismas instrucciones (largas) en cada paso: en caché cuestan y tardan menos desde
                # el segundo. En un pedido suelto no se recupera lo que cuesta escribirla (1,25 ×): ahí no se pide
                system=[{"type": "text", "text": instrucciones, "cache_control": {"type": "ephemeral"}}] if charla
                else instrucciones,
                output_config={"effort": "low" if rapido else "medium",
                               "format": {"type": "json_schema", "schema": esquema}},
                messages=[{"role": "user", "content": pedido}],
            ) as s:
                r = s.get_final_message()
        except anthropic.APIStatusError as e:  # sin esto se veía «Error code: 401 - {'error': {…}, 'request_id': …}»
            raise _error_claude(c, e) from None
        except Exception as e:  # sin conexión, cortado…: también se apunta
            actividad.anotar("texto", c["proveedor"], modelo, error=e)
            raise
        actividad.anotar("texto", c["proveedor"], modelo, _costo_claude(modelo, getattr(r, "usage", None), largo),
                         {"refusal": t("Claude rechazó el pedido."),
                          "max_tokens": t("respondió incompleto")}.get(r.stop_reason))
        if r.stop_reason == "refusal":
            raise RuntimeError(t("Claude rechazó el pedido."))
        if r.stop_reason == "max_tokens":  # el JSON llega cortado: json.loads fallaba en inglés, ya pagado
            raise RuntimeError(t("Claude respondió incompleto (se quedó sin espacio para terminar). "
                                 "Inténtalo de nuevo."))
        claves.recordar(c["proveedor"], 200)
        return _limpio(json.loads(next(b.text for b in r.content if b.type == "text")))

    from openai import APIStatusError, OpenAI
    cliente = OpenAI(api_key=c["clave"], base_url=claves.OPENAI_COMPAT[c["proveedor"]])
    # El modo json_object funciona en todos los compatibles; el esquema va en las instrucciones.
    mensajes = [{"role": "system", "content": f"{instrucciones}\n\nResponde SOLO con JSON que cumpla este esquema:\n"
                                              f"{json.dumps(esquema)}"},
                {"role": "user", "content": pedido}]
    sin_razonar = _sin_razonar(c["proveedor"], modelo) if rapido else {}
    respuestas = 0
    while respuestas < 2:  # si la respuesta llega cortada o incompleta, se pide una vez más
        try:
            r = cliente.chat.completions.create(model=c["modelo_texto"], response_format={"type": "json_object"},
                                                messages=mensajes,
                                                # Pollinations: que no salga en su feed público
                                                extra_body={**({"private": True} if c["proveedor"] == "pollinations"
                                                               else {}), **sin_razonar} or None)
        except APIStatusError as e:  # un diccionario de Python crudo, en inglés: se dice solo el motivo
            # Un modelo que no deja apagarlo: otra vez, como siempre (no cuenta como intento: no respondió nada)
            if sin_razonar and e.status_code == 400:
                sin_razonar = {}
                continue
            raise _error_texto(c, e.status_code, motivo(e.response)) from None
        except Exception as e:  # sin conexión, cortado…: también se apunta
            actividad.anotar("texto", c["proveedor"], modelo, error=e)
            raise
        respuestas += 1
        contenido = r.choices[0].message.content or ""
        try:
            valido = _validar(_json_de(contenido, esquema), esquema)
        except ValueError:
            valido = None
        uso = getattr(r, "usage", None)  # una respuesta incompleta también se cobra
        actividad.anotar("texto", c["proveedor"], modelo,
                         costo_texto(c["proveedor"], getattr(uso, "prompt_tokens", largo),
                                     getattr(uso, "completion_tokens", len(contenido) / 3)),
                         None if valido is not None else t("respondió incompleto"))
        if valido is not None:
            claves.recordar(c["proveedor"], 200)
            return _limpio(valido)
        sin_razonar = {}  # sin pensar pudo dejarlo a medias: la otra vez, con toda su calidad
    raise RuntimeError(t("La IA de texto ({proveedor}) respondió incompleto dos veces. Inténtalo de nuevo o "
                         "elige otra IA de texto en «Claves de IA».", proveedor=nombre))


# ---------- Ortografía: un repaso antes de quemar un texto en el video o publicarlo ----------

ORTOGRAFIA = (
    "Eres corrector de ortografía. Recibes textos ya escritos que van a salir dentro de un video o a publicarse. "
    "Corrige SOLO la ortografía: tildes, eñes, los signos ¿ y ¡, letras cambiadas y palabras mal escritas o de otro "
    "idioma por error (p. ej. «Fusel este aroma» → «Huele este aroma», «el malecón es nostro» → «el malecón es "
    "nuestro», «Rafa no doubles» → «Rafa no dobles», «Pesadelos» → «Pesadillas», «Miren que bien» → «Miren qué bien»). "
    "No cambies nada más: ni el estilo, ni el orden, ni el sentido. Cada texto corregido tiene EXACTAMENTE las mismas "
    "palabras que el original, una por una. Un hashtag sigue siendo una sola palabra con su #. Las marcas, los nombres "
    "propios y las palabras en inglés puestas a propósito se quedan como están. Respeta el habla y la jerga a "
    "propósito (pa', to', vamo', klk, tiguere, dique): no son faltas. Devuelve los mismos textos, en el mismo "
    "orden y la misma cantidad.")
_ESQUEMA_ORTOGRAFIA = {"type": "object", "properties": {"textos": {"type": "array", "items": {"type": "string"}}},
                       "required": ["textos"], "additionalProperties": False}
# Si ninguna IA responde: palabras que en español casi nunca van sin su tilde o su eñe (la IA de texto las deja así a
# veces: «sueno», «pequenos», «mas»). Las que cambian de sentido según la frase (si/sí, que/qué, esta/está) no.
_TILDES = {p.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
           .replace("ñ", "n"): p for p in (
    "más además jamás atrás detrás quizás también después así aquí allí ahí allá acá según algún ningún común "
    "fácil difícil rápido rápida rápidos rápidas música músicas número números último última últimos únicos único "
    "única análisis auténtico auténtica auténticos teléfono página páginas económico económica increíble increíbles "
    "día días tecnología energía compañía café inglés país países corazón razón jóvenes éxito éxitos cámara útil "
    "típico típica típicos típicas clásico clásica república había tenía podía vivía sueño sueños pequeño "
    "pequeña pequeños pequeñas año años mañana mañanas español española españoles España niño niña niños niñas señor "
    "señora dueño dueña diseño diseños montaña compañero compañera baño cumpleaños otoño").split()}
_SIN_TILDE = re.compile(r"(?<!\w)[A-Za-z]+(?!\w)")


def _tildes(texto: str) -> str:
    """Las tildes y eñes que faltan en las palabras de _TILDES y en las acabadas en -cion/-sion, con sus mayúsculas."""
    def poner(m):
        palabra = m[0]
        baja = palabra.lower()
        # -cion/-sion siempre llevan tilde en español («ss» no: eso es inglés, como «passion»)
        nueva = _TILDES.get(baja) or (baja[:-3] + "ión" if len(baja) > 5 and baja.endswith(("cion", "sion"))
                                      and "ss" not in baja else None)
        if not nueva:
            return palabra
        # Con mayúscula a mitad de frase es un nombre (Nina, Montana): se deja. Tras un # no: es un hashtag
        antes = texto[:m.start()].rstrip(" \t")[-1:]
        if palabra[0].isupper() and not palabra.isupper() and antes and antes not in ".!?…¿¡#«\"“:\n":
            return palabra
        # Las mayúsculas, letra por letra (la tilde o la eñe ocupa la misma letra): «#CineDeCienciaFiccion» salía
        # «#Cinedecienciaficción»
        return "".join(n.upper() if o.isupper() else n for o, n in zip(palabra, nueva))
    return _SIN_TILDE.sub(poner, texto)


def _nucleos(texto: str) -> list[str]:
    """Las palabras de un texto sin tildes, signos ni mayúsculas, para comparar un texto con su corrección."""
    import unicodedata
    planas = (unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode().lower() for p in texto.split())
    return [n for n in (re.sub(r"\W", "", p) for p in planas) if n]


def _misma_frase(original: str, corregido) -> bool:
    """Si la corrección solo arregla la ortografía: las mismas palabras (una por una, parecidas) y un hashtag sigue
    siendo un hashtag. Si la IA reescribe, resume o traduce, no vale (los subtítulos perderían sus tiempos)."""
    from difflib import SequenceMatcher
    if not isinstance(corregido, str) or original.lstrip().startswith("#") != corregido.lstrip().startswith("#"):
        return False
    a, b = _nucleos(original), _nucleos(corregido)
    return len(a) == len(b) and all(x == y or SequenceMatcher(None, x, y).ratio() >= 0.5 for x, y in zip(a, b))


def ortografia(textos: list[str], idioma: str | None = None, notas: list | None = None) -> list[str]:
    """Los mismos textos con la ortografía corregida y nada más (ver ORTOGRAFIA). Lo pide a Groq si está conectado
    (gratis) o a la IA de texto elegida, una sola vez; la corrección de un texto que cambia sus palabras no se usa. Los
    que la IA no corrigió (sin IA que responda, o una corrección rechazada), en español, llevan las tildes y eñes que
    faltan en las palabras más comunes (_tildes); los que sí, tal cual: «sabia» o «Cafe Brisa» pueden ir así a
    propósito. idioma: código de idioma.IDIOMAS (por defecto, el de la app). notas: si se pasa una lista, se le añade
    el aviso de que no se pudo repasar (si no, el texto con faltas salía en el video sin que nadie lo supiera)."""
    from .idioma import IDIOMAS, actual
    idioma = idioma if idioma in IDIOMAS else actual()
    corregidos, por_ia = list(textos), set()
    pendientes = [i for i, x in enumerate(textos) if isinstance(x, str) and x.strip()]
    groq = claves.cargar().get("groq") or {}
    # ponytail: un solo intento; la gratis sin clave no, porque espera 30 s entre pedidos. Con Groq (gratis)
    # conectado, solo Groq: si no atiende, el texto sigue sin repaso y se dice, nunca se paga a la elegida (pasó: con
    # la clave de Groq caducada, cada repaso iba a Claude). Sin Groq, la elegida. A la que no tiene saldo o tiene la
    # clave mal ni se le pide (_pedir): queda en la actividad y en el aviso
    c = groq if groq.get("clave") else claves.para("texto")
    if pendientes and c and c.get("clave"):
        try:
            pedido = json.dumps({"idioma": IDIOMAS[idioma], "textos": [textos[i] for i in pendientes]},
                                ensure_ascii=False)
            nuevos = _pedir(c, ORTOGRAFIA, pedido, _ESQUEMA_ORTOGRAFIA)["textos"]
            if len(nuevos) == len(pendientes):
                for i, nuevo in zip(pendientes, nuevos):
                    if _misma_frase(textos[i], nuevo):
                        corregidos[i] = nuevo.strip()
                        por_ia.add(i)
        except Exception as error:  # noqa: BLE001  sin repaso antes que sin video: el texto sale como vino
            if isinstance(error, SinServicio):  # _texto_con deja apuntar el «no atendió» a quien llama
                _no_atendio(c, error, "")
            from . import nubes
            causa = f"{claves.nombre(c['proveedor'])}: {nubes._causa(error, c['proveedor'])}"
            print(f"[Ráfaga] Sin repaso de ortografía ({causa})", file=sys.stderr, flush=True)
            nota = t("No se pudo repasar la ortografía ({causa}).", causa=causa)
            if notas is not None and nota not in notas:  # una vez por trabajo, aunque se repase en dos pedidos
                notas.append(nota)
    return [_tildes(x) if idioma == "es" and isinstance(x, str) and i not in por_ia else x
            for i, x in enumerate(corregidos)]


def repasar(objetos: list[dict], campos: tuple[str, ...], idioma: str | None = None,
            notas: list | None = None) -> None:
    """Repasa la ortografía (ver ortografia) de esos campos de varios diccionarios, en su sitio y en un solo pedido.
    Un campo puede ser un texto o una lista de textos (los hashtags); los que no están se saltan. notas: como en
    ortografia."""
    sitios = []
    for o in objetos:
        for campo in campos:
            valor = o.get(campo)
            if isinstance(valor, str):
                sitios.append((o, campo, None))
            elif isinstance(valor, list):
                sitios += [(o, campo, i) for i, x in enumerate(valor) if isinstance(x, str)]
    nuevos = ortografia([o[c] if i is None else o[c][i] for o, c, i in sitios], idioma, notas)
    for (o, c, i), nuevo in zip(sitios, nuevos):
        if i is None:
            o[c] = nuevo
        else:
            o[c][i] = nuevo


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
    """La IA de imágenes conectada (con referencia: ver puede_referencia) hace `pedido` a partir de la foto. Queda en la
    actividad de la IA, y un error del servicio se cuenta en claro (su código y su «message»): salía el texto de httpx
    en inglés con un enlace a mozilla.org (pasó con Pollinations sin saldo, 402). Lo que falle después de que OpenAI o
    Gemini (de pago) respondieron bien ya se cobró: sale como Cobrado, y nadie prueba otra imagen que se pagaría dos
    veces (ver imagen_con_producto)."""
    c = claves.para("imagen")
    gemini = c["proveedor"] == "gemini"
    modelo = c.get("modelo_imagen") if c["proveedor"] == "openai" else "black-forest-labs/flux.1-kontext-pro"

    def precio() -> float:  # al final: el de Gemini depende del modelo que eligió al pedir
        return precio_imagen_gemini(c["clave"], calidad) if gemini else \
            PRECIO_EDITAR_OPENAI if c["proveedor"] == "openai" else 0.0
    respondio = False  # un servicio de pago ya respondió bien (y cobró)
    try:
        if gemini:
            datos = _imagen_gemini(c, pedido, ancho, alto, foto, calidad=calidad, cobrado=True)
            respondio = True
            guardar_imagen(datos, destino)
            actividad.anotar("imagen", "gemini", _modelo_gemini_usado(c["clave"]), precio())
            return destino
        if c["proveedor"] == "openai":
            guardia.sin_bloqueo()  # de pago: con el estudio bloqueado no empieza
        size = "1024x1536" if alto > ancho else "1536x1024" if ancho > alto else "1024x1024"
        base = "https://api.openai.com/v1" if c["proveedor"] == "openai" else "https://gen.pollinations.ai/v1"
        # OpenAI, en calidad fija: con «auto» podía salir en alta, sin precio conocido (ver PRECIO_EDITAR_OPENAI)
        extra = {"quality": "medium"} if c["proveedor"] == "openai" else {"private": "true"}
        with open(foto, "rb") as f:
            r = httpx.post(f"{base}/images/edits", timeout=300, headers={"Authorization": f"Bearer {c['clave']}"},
                           files={"image": (foto.name, f, "image/png" if foto.suffix.lower() == ".png" else "image/jpeg")},
                           data={"model": modelo, "prompt": pedido, "size": size, "n": "1", **extra})
        if r.is_error:
            if claves.clasificar(r.status_code, motivo(r)) == "sin_saldo":  # la escena siguiente ya no lo espera
                claves.recordar(c["proveedor"], r.status_code, motivo(r))
            raise RuntimeError(t("{servicio} respondió {codigo}: {detalle}", servicio=claves.nombre(c["proveedor"]),
                                 codigo=r.status_code, detalle=motivo(r)))
        respondio = c["proveedor"] == "openai"
        d = r.json()["data"][0]
        guardar_imagen(_imagen_real(base64.b64decode(d["b64_json"]) if d.get("b64_json")
                                    else seguro.descargar(d["url"])), destino)
    except Exception as e:
        cobrado = respondio or isinstance(e, Cobrado)
        actividad.anotar("imagen", c["proveedor"], _modelo_gemini_usado(c["clave"]) if gemini else modelo,
                         precio() if cobrado else 0.0, error=e)
        if cobrado and not isinstance(e, Cobrado):
            raise Cobrado(texto_de_error(e)) from e
        raise
    actividad.anotar("imagen", c["proveedor"], modelo, precio())
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


def imagen_con_producto(prompt: str, foto: Path, ancho: int, alto: int, destino: Path, realista: bool = True,
                        avisos: list | None = None, respaldo: bool = True) -> Path:
    """Escena con el producto real de la foto. Usa edición con referencia si la IA de imágenes la tiene (salvo si ya
    dijo «sin saldo»: claves.recordar) y, si no sale, Cloudflare FLUX.2 (gratis) la redibuja con el producto de la
    foto; solo si tampoco, crea el fondo y coloca encima la foto del producto. realista=False: para dibujos (no fuerza
    foto). Si la edición con referencia falla (sin saldo, servicio caído), la escena se hace igual (fondo y foto
    encima) en vez de quedarse sin imagen y repetir la anterior; se dice en `avisos`, una vez. respaldo=False: el error
    sube (los dibujos animados se dibujan entonces sin su lámina: ver serie._dibujar). Si la edición ya se cobró
    (Cobrado), no hay respaldo: la otra imagen se pagaría dos veces."""
    # Sirve igual para productos que para personas, personajes o lugares de la foto de referencia.
    pedido = (f"{prompt}. Keep the subject from the reference image identical (same face, shape, colors, "
              "label and logo)." + (" Photorealistic." if realista else ""))
    intentos, errores = [], []
    if puede_referencia():
        elegida = (claves.para("imagen") or {}).get("proveedor")
        if malo := claves._vigente(elegida, claves.BLOQUEA):  # cada escena esperaba su 402
            errores.append(RuntimeError(claves.frase(elegida, malo["estado"])))
        else:
            intentos.append(lambda: _con_referencia(pedido, foto, ancho, alto, destino))
    if "cloudflare" in claves.cargar():
        intentos.append(lambda: _referencia_cloudflare(pedido, foto, ancho, alto, destino))
    for intento in intentos:
        try:
            return intento()
        except Cobrado:  # ya se pagó: otra imagen lo pagaría dos veces
            raise
        except Exception as error:
            errores.append(error)
    if errores and not respaldo:
        raise errores[0]
    hecha = pegar_producto(prompt, foto, ancho, alto, destino)  # la nota, solo si el respaldo salió
    if errores:
        nota = t("La edición con la imagen de referencia falló ({causa}): la escena se hizo con la foto encima de "
                 "un fondo nuevo.", causa=texto_de_error(errores[0]))
        if avisos is not None and nota not in avisos:  # con 5 escenas que fallan igual, una sola nota
            avisos.append(nota)
    return hecha


FLUX2 = "flux-2-klein-4b"  # con fotos de referencia; ~110 de las 10.000 neuronas gratis al día
LADO_REFERENCIA_FLUX2 = 496  # Cloudflare: cada foto de referencia, de menos de 512×512


def _referencia_cloudflare(pedido: str, foto: Path, ancho: int, alto: int, destino: Path) -> Path:
    """Cloudflare FLUX.2 [klein] (gratis, de la cuota diaria) dibuja `pedido` con el sujeto de la foto dentro de la
    escena, en vez de pegarlo encima. En la actividad de la IA, como las demás imágenes."""
    from PySide6.QtCore import QBuffer, Qt
    from PySide6.QtGui import QImageReader
    lector = QImageReader(str(foto))
    lector.setAutoTransform(True)  # la foto de móvil, derecha
    imagen = lector.read()
    if imagen.isNull():
        raise ValueError(t("No se pudo leer la imagen."))
    memoria = QBuffer()
    memoria.open(QBuffer.WriteOnly)
    imagen.scaled(LADO_REFERENCIA_FLUX2, LADO_REFERENCIA_FLUX2, Qt.KeepAspectRatio,
                  Qt.SmoothTransformation).save(memoria, "PNG")
    escala = min(1, 1920 / max(ancho, alto))  # su tamaño va de 256 a 1920 px por lado
    w, h = (max(256, int(lado * escala)) // 16 * 16 for lado in (ancho, alto))
    try:
        cuenta, token = cloudflare_partes(claves.cargar()["cloudflare"]["clave"])
        r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/black-forest-labs/{FLUX2}",
                       timeout=300, headers={"Authorization": f"Bearer {token}"},
                       data={"prompt": pedido[:2048], "width": str(w), "height": str(h)},
                       files={"input_image_0": ("referencia.png", bytes(memoria.data()), "image/png")})
        if r.is_error:  # su código y su «message», sin la URL (lleva el ID de la cuenta)
            raise RuntimeError(t("{servicio} respondió {codigo}: {detalle}", servicio="Cloudflare",
                                 codigo=r.status_code, detalle=motivo(r)))
        guardar_imagen(_imagen_real(base64.b64decode(r.json()["result"]["image"])), destino)
    except Exception as e:
        actividad.anotar("imagen", "cloudflare", FLUX2, error=e)
        raise
    actividad.anotar("imagen", "cloudflare", FLUX2)
    return destino


def pegar_producto(prompt: str, foto: Path, ancho: int, alto: int, destino: Path) -> Path:
    """La escena sin el producto (con la IA de imágenes de siempre) y la foto real pegada encima, en el centro."""
    # ponytail: sin edición con referencia el producto se pega encima del fondo; queda menos natural.
    from .video import ffmpeg
    # Pedir «the product» y a la vez «no product» se contradecía: el hueco va en la propia escena
    escena = re.sub("the product|the subject from the reference image", "an empty spot", prompt, flags=re.IGNORECASE)
    fondo = imagen(f"{escena}, empty space in the center", ancho, alto, destino.with_name(destino.stem + "_fondo.png"))
    ffmpeg("-i", fondo, "-i", foto, "-filter_complex",
           f"[0]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto}[f];"
           f"[1]scale={int(ancho * 0.6)}:-1[p];[f][p]overlay=(W-w)/2:(H-h)*0.62", "-frames:v", "1", destino)
    return destino


def investigar_web(pregunta: str, plazo: float = 300) -> str | None:
    """Investigación en vivo en internet con Claude (búsqueda web). None si la IA de texto no es Claude.
    Como mucho `plazo` segundos (y lo que tarda en cerrarse la conexión): al cumplirse se corta y devuelve lo que ya
    escribió (o None si nada). Es un paso intermedio (lo analiza otra IA después): esfuerzo «low» y hasta 5 búsquedas,
    que busque menos y lo junte antes."""
    c = claves.para("texto")
    if not c or c.get("proveedor") != "anthropic":
        return None
    import anthropic
    modelo, cliente, vencido = c.get("modelo_texto") or "", _claude(c), threading.Event()

    def cortar():
        vencido.set()
        cliente.close()
    # El plazo de verdad: mirar el reloj con cada evento no bastaba (los «ping» no llegan al bucle y, mientras Claude
    # piensa o busca, no llega nada). Cerrar el cliente corta la espera aunque no llegue nada, también la de cabeceras
    reloj = threading.Timer(plazo, cortar)
    reloj.daemon = True
    reloj.start()
    mensajes, r = [{"role": "user", "content": pregunta}], None
    try:
        # La búsqueda puede pausar el turno; se retoma hasta 5 veces, nunca pasado el plazo: otra ronda reenviaría (y
        # pagaría como entrada) todo lo encontrado para cortarse enseguida
        for _ in range(6):
            if vencido.is_set():
                break
            parcial, cortado = None, False
            try:
                with cliente.messages.stream(
                        model=modelo, max_tokens=16000, output_config={"effort": "low"},
                        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
                        messages=mensajes) as s:
                    for _evento in s:
                        parcial = s.current_message_snapshot  # lo escrito hasta ahora: lo que queda si se corta
                    r = s.get_final_message()
            except anthropic.APIStatusError as e:  # en claro («respondió 400: Your credit balance is too low»)
                error = _error_claude(c, e)
                if isinstance(error, SinServicio):  # _error_texto deja apuntar esos a quien llama
                    actividad.anotar("texto", "anthropic", modelo, error=error.corto)
                raise error from None
            except Exception as e:
                if not vencido.is_set():  # sin conexión…; el corte del plazo, en cambio, no es un fallo
                    actividad.anotar("texto", "anthropic", modelo, error=e)
                    raise
                cortado = True
            hecho = parcial if cortado else r
            uso = getattr(hecho, "usage", None)  # cada búsqueda web cuesta aparte: va en la misma línea
            # Cortado, el uso es el del principio: las búsquedas se cuentan en el contenido y la salida (que llega al
            # final) queda por lo bajo. ponytail: se apunta solo la de hasta el principio
            busquedas = (getattr(getattr(uso, "server_tool_use", None), "web_search_requests", 0)
                         or sum(b.type == "server_tool_use" and b.name == "web_search"
                                for b in getattr(hecho, "content", None) or []))
            actividad.anotar("texto", "anthropic", modelo, _costo_claude(modelo, uso, busquedas=busquedas),
                             t("Se cortó: tardó más de {segundos} s.", segundos=round(plazo)) if cortado
                             else t("Claude rechazó el pedido.") if r.stop_reason == "refusal" else None)
            if cortado:
                r = parcial or r  # sin nada nuevo, lo de la ronda anterior
                break
            if r.stop_reason != "pause_turn":
                break
            mensajes = [*mensajes, {"role": "assistant", "content": r.content}]
    finally:
        reloj.cancel()
    return ("\n".join(b.text for b in r.content if b.type == "text") or None) if r else None


# Lo que el filtro de Cloudflare toma por «NSFW» en pedidos inocentes (comida, dibujos): fuera en su único reintento
# («hot» sí, salvo en comidas: sin él, «hot dog» quedaba «dog»)
_DUDOSAS = re.compile(r"\b(?:juicy|moist|wet|dripping|oozing|stretchy|creamy|thick|tender|pink|flesh\w*|skin\w*|naked|"
                      r"nude|bare|sexy|seductive|sensual|hot(?![ -]?(?:dogs?|sauces?|wings?|pot|chocolate|cocoa|soup|"
                      r"tea|coffee|peppers?|chil[il]\w*)\b)|steamy|curvy|busty|lick\w*|suck\w*|kiss\w*|"
                      r"bod(?:y|ies))\b", re.I)


def _neutro(prompt: str) -> str:
    """El mismo pedido dicho neutro, para reintentar tras un falso «NSFW» de Cloudflare."""
    return "Family-friendly, safe for work image. " + " ".join(_DUDOSAS.sub("", prompt).split())


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
        for pedido in (prompt, _neutro(prompt)):
            r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/black-forest-labs/"
                           "flux-1-schnell", headers={"Authorization": f"Bearer {token}"}, timeout=300,
                           # sin «seed»: desde 2026 Cloudflare rechaza (400) cualquier campo que no sea prompt o steps
                           json={"prompt": pedido[:2048], "steps": 8})
            # Su filtro ve «NSFW» en comida y dibujos inocentes («juicy… pink ham… stretchy»): una vez, dicho neutro
            if not (r.status_code == 400 and "nsfw" in r.text.lower()):
                break
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
        # El Space oficial de FLUX schnell, sin token (cuota anónima de ZeroGPU; el prompt llega a un Space público).
        # Con el token iba a hf-inference, que ya no sirve ese modelo (410 Gone)
        escala = min(1, 1280 / max(ancho, alto))  # lado largo de 1280: rápido y gasta poca cuota; el montaje escala
        salida = nubes.llamar_space(ESPACIO_IMAGEN, prompt[:2000], semilla, False, int(ancho * escala) // 16 * 16,
                                    int(alto * escala) // 16 * 16, 4, api_name="/infer")
        return nubes.archivo_del_space(salida[0] if isinstance(salida, (list, tuple)) else salida)

    def replicate():
        guardia.sin_bloqueo()  # de pago: bloqueado, rotar pasa a la siguiente opción (la gratis)
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
        guardia.sin_bloqueo()  # de pago: bloqueado, rotar pasa a la siguiente opción (la gratis)
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

    def que_fue(p):  # el modelo y lo que cuesta, para la actividad de la IA
        if p == "gemini":
            return _modelo_gemini_usado(todas["gemini"]["clave"]), precio_imagen_gemini(todas["gemini"]["clave"], calidad)
        modelo = {"cloudflare": "flux-1-schnell", "gratis_sin_clave": "flux", "huggingface": ESPACIO_IMAGEN}.get(p) \
            or (todas.get(p) or {}).get("modelo_imagen") or ""
        return modelo, PRECIO_IMAGEN.get(p, 0.0)
    datos, _ = nubes.rotar("imagen", tareas, que_fue=que_fue)
    return guardar_imagen(datos, destino)


def cloudflare_partes(clave: str) -> tuple[str, str]:
    """La clave de Cloudflare se pega como «ID_de_cuenta token» (el ID son 32 caracteres hexadecimales)."""
    import re
    cuenta = re.search(r"\b[0-9a-f]{32}\b", clave).group()
    token = next(p for p in re.split(r"[\s:;,]+", clave) if p and p != cuenta)
    return cuenta, token


# Un movimiento de cámara dicho como lo entiende Wan 2.2 (y Kling, Seedance, Omni), AL EMPEZAR la frase: «the patty
# sizzles in the pan» o «el pan se tuesta» son lo que pasa, no la cámara (se perdían)
_CAMARA = re.compile(r"(?:(?:the|camera|slow(?:ly)?|smooth(?:ly)?|gentle|gently|quick(?:ly)?|fast|subtle|steady|very|"
                     r"cinematic)[\s:,]+)*(?:dolly|push(?:es|ing)?[ -]in|pull(?:s|ing)?[ -](?:back|out)|zoom\w*|"
                     r"pan(?:s|ning)?\s+(?:left|right|across|up|down|over|from|to)|tilt(?:s|ing)?\s+(?:up|down)|"
                     r"orbit\w*|(?:crane|jib)(?:\s+(?:shot|up|down)|s?\s+(?:up|down))|tracking|"
                     r"truck(?:s|ing)?\s+(?:left|right)|arc(?:s|ing)?\s+(?:shot|around|left|right)|hand-?held|static|"
                     r"locked[ -]off|macro|(?:drone|aerial)\s+(?:shot|view)|fpv)\b", re.I)
# Los movimientos con nombre para animar una foto (como los de Higgsfield): el nombre, y cómo se le pide a la IA
CAMARAS = {"acercar": (t("Acercar"), "Slow dolly in toward the subject"),
           "alejar": (t("Alejar"), "Slow dolly out, pulling back to reveal the scene"),
           "orbita": (t("Órbita"), "Smooth orbit around the subject"),
           "paneo": (t("Paneo"), "Slow pan from left to right across the scene"),
           "grua": (t("Grúa"), "Crane shot rising up over the subject"),
           "mano": (t("Cámara en mano"), "Handheld camera with subtle natural shake, following the subject")}


def direccion_video(prompt: str) -> str:
    """Lo que se pide a la IA de video: la cámara primero y una sola por plano, luego lo que hace el sujeto y el
    ambiente (la línea «movimiento» de cada escena ya viene así). Sin cámara (p. ej. lo que muestra la imagen), un
    acercamiento lento: antes iba la descripción quieta de la imagen con «cinematic motion» al final, y salía casi
    quieta."""
    frases = [f.strip(" ,") for f in re.split(r"[.;\n]+", str(prompt)) if f.strip(" ,")]
    camara = next((f for f in frases if _CAMARA.match(f)), CAMARAS["acercar"][1])
    return "; ".join([camara, *(f for f in frases if not _CAMARA.match(f))]) + \
        ". One continuous shot with smooth, natural motion; the subject keeps its exact look."


def orden_foto() -> list[str]:
    """Quién anima UNA foto que pidió mover el usuario (Solo animar): los de las escenas (nubes.orden), salvo
    Pollinations, que hace el clip solo con el texto y no ve la foto (elegido, no hay nadie). Con «No usar» guardado,
    nubes.orden no la sube al Space público: solo tu nube Modal. Vacío: foto_sin_animar() dice por qué."""
    from . import nubes
    if claves.ajustes().get("video") == "pollinations":
        return []
    return [p for p in nubes.orden("video") if p != "pollinations"]


def foto_sin_animar() -> str:
    """Por qué nadie anima la foto (orden_foto() vacío), dicho para el usuario."""
    if claves.ajustes().get("video") == "pollinations":
        return t("Pollinations hace el clip solo con el texto, sin tu foto: para animarla, elige otro modelo de video.")
    return t("Para animar tu foto, elige «Hugging Face» (gratis: se sube a su Space público) o conecta tu nube Modal "
             "(privada). Con «No usar» en «Claves de IA», el estudio no la sube a un Space público por su cuenta.")


def video_desde_imagen(imagen_png: Path, prompt: str, formato: str, segundos: float, destino: Path,
                       pago: str | None = None, forzar: bool = False) -> Path | None:
    """Anima una imagen con IA de video: tu nube Modal primero si la tienes y, si no, lo gratis (ver nubes.ORDEN;
    Hugging Face va incluso sin clave). prompt: la línea «movimiento» de la escena (o lo que muestra la imagen), que
    direccion_video ordena. None solo si el usuario eligió «No usar» IA de video.
    pago: el video de pago (video_de_pago) que se preguntó al empezar el trabajo; solo ese se puede usar. Si el
    usuario elige otro a mitad del trabajo, esa escena no se paga (falla y va con zoom suave): vale para el siguiente.
    Gemini Omni (solo con una foto, video_de_pago(un_clip=True)): sin respaldo, un fallo nunca se paga dos veces.
    forzar: el usuario pidió animar ESTA imagen (Solo animar): «No usar» guardado no la deja quieta, pero entonces solo
    la mueve tu nube Modal (nubes.orden: nunca el Space público); Pollinations nunca, que no ve la foto (orden_foto).
    SinClave si no hay quien."""
    from . import nube, nubes
    if not forzar and claves.ajustes().get("video") == "ninguno":
        return None
    todas = claves.cargar()
    movimiento = direccion_video(prompt)
    if pago == "gemini":  # su propio sonido de ambiente; el montaje lo deja mudo
        return video_hablado(f"Animate this exact image as the first frame. {movimiento} No dialogue, no voice-over, "
                             "no music: only natural ambient sound.", formato, destino, imagen_png, "gemini")
    if forzar and not orden_foto():  # antes de subir nada
        raise SinClave(foto_sin_animar())

    def huggingface():
        from gradio_client import handle_file
        # Cuota gratis diaria de GPU (ZeroGPU), anónima: el token nunca se manda a Spaces de terceros. Clips de ~5 s.
        salida, _ = nubes.llamar_space(claves.MODELO_VIDEO["huggingface"], handle_file(str(imagen_png)), movimiento,
                                       duration_seconds=min(max(segundos, 2), 5), api_name="/generate_video")
        return _clip_real(nubes.archivo_del_space(salida), destino)

    def pollinations():
        c = todas["pollinations"]
        relacion = "9:16" if formato in ("9:16", "4:5") else "16:9"
        url = (f"https://gen.pollinations.ai/video/{_ruta_url(movimiento)}"
               f"?model={urllib.parse.quote(c['modelo_video'], safe='')}&duration={min(max(round(segundos), 2), 5)}"
               f"&aspectRatio={relacion}&audio=false&private=true")
        return _clip_real(seguro.descargar(url, {"Authorization": f"Bearer {c['clave']}"}, tope=VIDEO_MAXIMO, plazo=900),
                          destino)

    def de_pago(proveedor):  # Kling o Seedance (solo si el usuario lo eligió): clip mudo que el montaje repite
        modulo = claves.modulo_video(proveedor)
        try:
            _recordar_modelo(proveedor, "modelo_video",
                             modulo.animar(todas[proveedor], imagen_png, movimiento, destino, modulo.SEGUNDOS_CLIP))
        except SinSaldo as e:  # el trabajo siguiente ya avisa antes de empezar (claves.impide)
            claves.recordar(proveedor, 402, str(e))
            raise
        return destino

    def que_fue(p):  # el modelo y lo que cuesta como mucho, para la actividad de la IA
        if p in claves.VIDEO_DE_PAGO:
            return (claves.cargar().get(p) or {}).get("modelo_video") or "", precio_video(p)
        return (todas.get(p) or {}).get("modelo_video") or claves.MODELO_VIDEO.get(p, ""), \
            nube.PRECIO_CLIP if p == "modal" else 0.0

    resultado, _ = nubes.rotar("video", {
        "huggingface": huggingface,
        "modal": lambda: nube.animar(imagen_png, movimiento, formato, segundos, destino),
        **({} if forzar else {"pollinations": pollinations}),  # sin la foto: con forzar, su clip no sería esa foto
        **{p: lambda p=p: de_pago(p) for p in claves.VIDEO_DE_PAGO if p == pago},  # solo el que se preguntó
    }, que_fue=que_fue)
    return resultado


ESPACIO_AVATAR = "Wan-AI/Wan2.2-S2V"  # el oficial de Wan (Alibaba): sube foto y voz a Alibaba Cloud y las guarda 24 h
MAX_AVATAR_SPACE = 18  # segundos: el Space acepta menos de 20
ESPERA_AVATAR_SPACE = 900  # Alibaba dice que su tarea tarda unos 5-10 min: con la espera de siempre (5) no llegaba


def avatar(foto: Path, audio: Path, formato: str, destino: Path, space: bool = False) -> Path:
    """Tu foto habla con tu voz (un MP4 con la voz dentro). En tu nube Modal (nube.avatar: del crédito gratis, 1 clip
    del cupo del mes) o, solo si lo marcas esa vez (space=True), gratis en el Space oficial de Wan. Solo se prueba el
    elegido: tu cara y tu voz nunca van por detrás a un Space público, y lo de pago nunca entra si falla lo gratis."""
    from . import nube, nubes, video

    def huggingface():
        from gradio_client import handle_file

        from . import render_edicion
        error = nube.voz_larga(video.medir(audio)[0], MAX_AVATAR_SPACE)
        if error:
            raise ValueError(error)
        # Al Space público (lo ve su dueño) va una copia hecha de nuevo solo con los píxeles y con nombre neutro: ni el
        # EXIF (el GPS de una foto de móvil) ni el nombre del archivo. Sin token (llamar_space): el Space llama a la
        # API de Alibaba con la clave de su dueño
        with tempfile.TemporaryDirectory() as carpeta:
            limpia = render_edicion._foto(Path(foto), Path(carpeta))
            salida = nubes.llamar_space(ESPACIO_AVATAR, handle_file(str(limpia)), handle_file(str(audio)), "480P",
                                        api_name="/predict", espera=ESPERA_AVATAR_SPACE)
        return _clip_real(nubes.archivo_del_space(salida), destino)

    def que_fue(p):  # el modelo y lo que cuesta, para la actividad de la IA
        return ("EchoMimicV3-Flash", nube.PRECIO_AVATAR) if p == "modal" else (ESPACIO_AVATAR, 0.0)
    tareas = {"huggingface": huggingface} if space else {"modal": lambda: nube.avatar(foto, audio, formato, destino)}
    return nubes.rotar("avatar", tareas, que_fue=que_fue)[0]


API_GEMINI = "https://generativelanguage.googleapis.com/v1beta"
OMNI = "gemini-omni-1.1-flash"  # si la API no dice cuál hay. Sustituye a Veo, que Google apagó el 22-10-2026
PRECIO_OMNI = 0.10  # US$ por segundo de video 720p según Google (sin cuota gratis)
PRECIO_IMAGEN = {"openai": 0.25, "replicate": 0.01}  # US$ por imagen, por lo alto (gpt-image en alta; FLUX schnell)
PRECIO_TRANSCRIPCION = 0.006  # US$ por minuto con la Whisper API de OpenAI (Groq y el PC: gratis)
# US$ por cada 1000 letras narradas con ElevenLabs, por lo alto (lo que cuestan las letras de más de su plan Creator):
# solo para el gasto estimado de «Actividad de la IA»
PRECIO_VOZ_ELEVENLABS = 0.30
MINUTOS_NUBE = 105  # lo más largo que transcribir() sube a la nube (25 MB a 32 kbps); lo que pasa, en el PC
IMAGEN_GEMINI = "gemini-nano-banana-2.1"  # Nano Banana 2.1, si la API no dice cuál hay
# US$ por imagen según el modelo y su calidad (imageSize), según Google el 22-10-2026 (sin cuota gratis): el Flash
# Image de respaldo (claves sin Nano Banana) cuesta casi el doble
PRECIO_IMAGEN_GEMINI = {IMAGEN_GEMINI: {"1K": 0.0336, "2K": 0.0504, "4K": 0.113},
                        "gemini-3.1-flash-image": {"1K": 0.067, "2K": 0.101, "4K": 0.151}}
PROPORCIONES_GEMINI = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")  # las que acepta
_elegidos = {}  # modelo elegido por clave y por uso, una vez por sesión
_cerrojo_modelos = threading.Lock()  # clips_hablados hace 3 videos a la vez y cada uno puede guardar su modelo


def video_de_pago(un_clip: bool = False) -> str | None:
    """Kling o Seedance si el usuario lo eligió para animar escenas y su clave está conectada (nubes.orden lo usa
    entonces solo a él): cada escena animada se paga. None si la animación es gratis o está apagada.
    un_clip: UNA foto que el usuario pidió animar (Solo animar). Con Gemini Omni elegido en «Modelo de video» de ese
    trabajo, la anima Gemini (de pago, con su pregunta); en un video entero Gemini solo hace lo que habla."""
    if un_clip and getattr(claves._trabajo, "ajustes", {}).get("video_voz") == "gemini" and "gemini" in claves.cargar():
        return "gemini"
    elegido = claves.ajustes().get("video")
    return elegido if elegido in claves.SOLO_ELIGIENDO["video"] and elegido in claves.cargar() else None


def nombre_video(proveedor: str) -> str:
    """El nombre del servicio de video de pago en las preguntas de costo y las notas de gasto."""
    return claves.modulo_video(proveedor).NOMBRE if proveedor in claves.VIDEO_DE_PAGO else "Gemini"


def precio_video(proveedor: str, segundos: float | None = None, voz: bool = False) -> float:
    """Lo más que cuesta un clip de video de pago (US$), el mismo número en todas las preguntas y notas de gasto.
    Kling y Seedance: lo calcula su módulo con la clave (sus respaldos pueden ser más caros); sin segundos, un clip
    como los pide el estudio. Gemini Omni (hable o anime una foto): PRECIO_OMNI por segundo, y sus clips duran hasta
    10 s."""
    if proveedor in claves.VIDEO_DE_PAGO:
        modulo = claves.modulo_video(proveedor)
        segundos = segundos or (modulo.SEGUNDOS_VOZ if voz else modulo.SEGUNDOS_CLIP)
        return modulo.estimar(claves.cargar().get(proveedor) or {}, segundos, voz)
    return (segundos or 10) * PRECIO_OMNI if proveedor == "gemini" else 0.0


def nota_pago(proveedor: str, clips: int) -> str:
    """La nota de gasto de un trabajo: cuántos clips mudos hizo el servicio de pago y lo más que costaron."""
    return t("{proveedor} hizo clips de video ({n}): hasta unos {costo} según su precio.",
             proveedor=nombre_video(proveedor), n=clips, costo=dinero(clips * precio_video(proveedor)))


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


def _modelo_gemini_usado(clave: str) -> str:
    """El modelo de imágenes de Gemini ya elegido para esa clave (para la actividad), sin preguntar a la red."""
    return _elegidos.get((clave, claves.elegir_modelo_imagen_gemini), IMAGEN_GEMINI)


def precio_imagen_gemini(clave: str, calidad: str) -> float:
    """US$ por imagen con el modelo ya elegido para esa clave; si aún no se sabe (o no se conoce su precio), el más
    caro de los conocidos: el aviso de costo nunca se queda corto. No pregunta a la red."""
    precios = PRECIO_IMAGEN_GEMINI.get(_elegidos.get((clave, claves.elegir_modelo_imagen_gemini)))
    return precios[calidad] if precios else max(p[calidad] for p in PRECIO_IMAGEN_GEMINI.values())


def _imagen_gemini(c: dict, prompt: str, ancho: int, alto: int, referencia: Path | None = None,
                   calidad: str = "1K", cobrado: bool = False) -> bytes:
    """Una imagen con Gemini (Nano Banana, de pago): solo si el usuario lo eligió para las imágenes. Con
    `referencia`, la edita manteniendo igual a quien sale en ella. calidad: 1K, 2K o 4K (PRECIO_IMAGEN_GEMINI).
    cobrado=True: lo que falle después de que Gemini respondió bien sale como Cobrado (ver _con_referencia). En la
    rotación de ia.imagen no: tras Gemini solo quedan opciones gratis."""
    guardia.sin_bloqueo()  # de pago: con el estudio bloqueado no empieza
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
    if r.is_error:  # el motivo exacto (filtro, sin facturación, clave): el cuerpo no trae la clave. No se cobró
        if r.status_code == 402:  # sin saldo prepago: vale para todo Gemini, también su texto
            claves.recordar("gemini", 402, motivo(r))
        raise SinServicio(t("Gemini respondió {codigo}: {detalle}", codigo=r.status_code, detalle=motivo(r)))
    try:
        for parte in ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts", []):
            datos = parte.get("inlineData") or parte.get("inline_data") or {}
            if datos.get("data"):
                return _imagen_real(base64.b64decode(datos["data"]))
        raise RuntimeError(t("Gemini no devolvió ninguna imagen"))
    except Exception as error:
        if not cobrado:
            raise
        raise Cobrado(texto_de_error(error)) from error


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
    «Escenas que hablan» a mitad de un trabajo nunca paga con otro servicio.
    Cada clip queda en la actividad de la IA con lo más que cuesta (también el que se cobró y no llegó). Sin saldo,
    SinSaldo: no se cobró nada y los demás clips del trabajo ni se piden (clips_hablados)."""
    guardia.sin_bloqueo()  # de pago: con el estudio bloqueado no empieza
    quien = quien or (claves.para("video_voz") or {}).get("proveedor")

    def modelo():
        if quien in claves.VIDEO_DE_PAGO:
            return (claves.cargar().get(quien) or {}).get("modelo_voz") or ""
        return _elegidos.get(((claves.cargar().get("gemini") or {}).get("clave"), claves.elegir_modelo_video_voz), OMNI)
    try:
        hecho = _video_hablado(prompt, formato, destino, referencia, quien)
    except SinClave:  # no llegó a pedir nada
        raise
    except SinSaldo as e:
        claves.recordar(quien or "gemini", 402, str(e))
        actividad.anotar("video", quien or "gemini", modelo(), error=e)
        raise
    except Exception as e:  # el que se cobró sin llegar (Cobrado) cuenta en el gasto
        actividad.anotar("video", quien or "gemini", modelo(), precio_video(quien or "gemini", voz=True)
                         if isinstance(e, Cobrado) else 0.0, error=e)
        raise
    segundos = None
    if (quien or "gemini") == "gemini":  # Google cobra los segundos que salen: un clip de 8 s no se apunta como de 10
        from . import video
        with contextlib.suppress(Exception):
            segundos = video.duracion(hecho)
    actividad.anotar("video", quien or "gemini", modelo(), precio_video(quien or "gemini", segundos, voz=True))
    return hecho


class SinSaldo(RuntimeError):
    """El servicio de pago no tiene saldo: no hizo nada ni cobró. Los demás pedidos del mismo trabajo fallarían igual:
    no se piden."""


def _video_hablado(prompt: str, formato: str, destino: Path, referencia: Path | None, quien: str | None) -> Path:
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
    detalle = motivo(r) if r.is_error else ""
    if claves.clasificar(r.status_code, detalle) == "sin_saldo" and re.search(r"\bspend", detalle, re.I):
        # El tope de gasto mensual del proyecto llega como 429: no es «espera un rato», y cada escena lo repetía
        raise SinSaldo(t("Gemini llegó al tope de gasto mensual de tu proyecto: no hizo el video y no se cobró nada. "
                         "Súbelo en AI Studio (aistudio.google.com → tu proyecto → Spend) o espera al mes que viene."))
    if r.status_code == 402:  # sin saldo prepago (pasó): dicho claro, con lo que cuesta, y sin cobrar nada
        raise SinSaldo(t("Gemini no tiene saldo: no hizo el video que habla y no se cobró nada. Cada escena que habla "
                         "cuesta hasta unos {costo}. Recarga en AI Studio: aistudio.google.com → tu proyecto → Billing, "
                         "o desmarca «Video animado con IA». ({detalle})", costo=dinero(precio_video("gemini", voz=True)),
                         detalle=motivo(r)))
    if r.is_error:  # el motivo exacto (filtro de seguridad, sin facturación, clave): el cuerpo no trae la clave
        raise RuntimeError(t("Gemini respondió {codigo}: {detalle}", codigo=r.status_code,
                             detalle=motivo(r)))
    respuesta = r.json()
    interaccion, archivo = str(respuesta.get("id", "")).removeprefix("interactions/"), None
    try:
        bloque = _bloque_video(respuesta)
        if not bloque:  # p. ej. lo frenó su filtro de seguridad: se dice lo que contestó
            raise RuntimeError(t("Gemini no devolvió ningún video: {detalle}",
                                 detalle=recortar(_mensaje_de(respuesta) or t("sin motivo"), 300)))
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
        except Exception as error:  # Google ya lo hizo, y lo cobra (el motivo en claro: no el texto de httpx)
            raise Cobrado(texto_de_error(error)) from error
    finally:  # lo guardado en Google (el pedido, la foto y el video) no se queda allí, salga bien o mal
        if archivo:
            _borrar(archivo, cabecera)
        if re.fullmatch(r"[\w-]+", interaccion):
            _borrar(f"{API_GEMINI}/interactions/{interaccion}", cabecera)


def voz_elevenlabs(texto: str, voice_id: str, destino: Path, velocidad: float = 1.0) -> list[dict]:
    """Narra con ElevenLabs y devuelve los tiempos por palabra (vienen por letra y se agrupan). velocidad: de 0,7 a
    1,2 (su rango); solo se manda si cambia, para no tocar los ajustes que la voz tiene guardados."""
    c = claves.cargar().get("elevenlabs")
    if not c:
        raise SinClave(t("Conecta tu clave de ElevenLabs para usar sus voces."))
    guardia.sin_bloqueo()  # de pago (ElevenLabs cobra por letra): con el estudio bloqueado no empieza
    modelo = c.get("modelo_voz", "eleven_multilingual_v2")
    try:
        r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
                       params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": c["clave"]}, timeout=300,
                       json={"text": texto, "model_id": modelo,
                             **({"voice_settings": {"speed": velocidad}} if velocidad != 1 else {})})
        if r.is_error:  # su motivo en claro (p. ej. «quota_exceeded»), no el texto de httpx en inglés
            raise RuntimeError(t("{servicio} respondió {codigo}: {detalle}", servicio="ElevenLabs",
                                 codigo=r.status_code, detalle=motivo(r)))
        d = r.json()
        destino.write_bytes(base64.b64decode(d["audio_base64"]))
    except Exception as e:
        actividad.anotar("voz", "elevenlabs", modelo, error=e)
        raise
    actividad.anotar("voz", "elevenlabs", modelo, len(texto) / 1000 * PRECIO_VOZ_ELEVENLABS)
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


_WHISPER, _CARGANDO_WHISPER = {}, threading.Lock()
# revisión fija: un cambio en la rama «main» del repositorio no entra solo en el PC
WHISPER_REPO, WHISPER_REVISION = "Systran/faster-whisper-small", "536b0662742c02347bc0e980a01041f333bce120"


def whisper():
    """El Whisper del PC, cargado una sola vez: cargarlo tarda (~4 s; la primera vez descarga ~460 MB). Se reutiliza
    en cada escena y en cada orden de voz, y el Director lo va cargando mientras hablas (dos hilos no lo cargan doble)."""
    with _CARGANDO_WHISPER:
        if "small" not in _WHISPER:
            from faster_whisper import WhisperModel
            _WHISPER["small"] = WhisperModel("small", device="cpu", compute_type="int8", revision=WHISPER_REVISION)
    return _WHISPER["small"]


def whisper_descargado() -> bool:
    """Si el modelo ya está en este PC (sin preguntar a internet): si no, la primera orden de voz espera la descarga."""
    if "small" in _WHISPER:
        return True
    from huggingface_hub import try_to_load_from_cache
    return isinstance(try_to_load_from_cache(WHISPER_REPO, "model.bin", revision=WHISPER_REVISION), str)


def transcribir(audio: Path, idioma: str | None = None, pista: str | None = None, cancion: bool = False,
                progreso=lambda f: None, en_pc: bool = False) -> list[dict]:
    """Devuelve las palabras con tiempos: [{'palabra', 'inicio', 'fin'}].
    Usa Groq/OpenAI si hay clave (rápido); si no, Whisper local en el PC (lento pero gratis).
    en_pc: siempre en el PC, aunque haya clave (la voz del usuario para el Director no sale de aquí)."""
    c = None if en_pc else claves.para("transcripcion")
    if c and c.get("proveedor") == "openai" and guardia.bloqueado():
        c = None  # de pago (PRECIO_TRANSCRIPCION): bloqueado, se transcribe gratis en el PC (Groq sigue: es gratis)
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
        try:
            with open(audio, "rb") as f:
                r = httpx.post(f"{base}/audio/transcriptions", timeout=900,
                               headers={"Authorization": f"Bearer {c['clave']}"},
                               files={"file": (audio.name, f)},
                               data={"model": c["modelo_transcripcion"], "response_format": "verbose_json",
                                     "timestamp_granularities[]": "word", **({"language": idioma} if idioma else {}),
                                     **({"prompt": pista[:800]} if pista else {})})
            r.raise_for_status()
            datos = r.json()
            palabras = [{"palabra": w["word"].strip(), "inicio": w["start"], "fin": w["end"]} for w in datos["words"]]
        except Exception as e:
            actividad.anotar("transcripcion", c["proveedor"], c.get("modelo_transcripcion") or "", error=e)
            raise
        # OpenAI cobra por minuto (Groq, gratis): con la duración que dice la respuesta, o lo más que se sube
        minutos = datos.get("duration") / 60 if isinstance(datos.get("duration"), (int, float)) else MINUTOS_NUBE
        actividad.anotar("transcripcion", c["proveedor"], c.get("modelo_transcripcion") or "",
                         minutos * PRECIO_TRANSCRIPCION if c["proveedor"] == "openai" else 0.0)
        return palabras

    import subprocess

    import numpy as np

    from .video import FFMPEG, MEDIOS
    # Se decodifica con ffmpeg: la librería 'av' que trae faster-whisper choca con versiones nuevas.
    crudo = subprocess.run([FFMPEG, "-format_whitelist", MEDIOS, "-i", str(audio),
                            "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    modelo = whisper()
    # `pista` (p. ej. la letra) ayuda a Whisper a acertar palabras cantadas o con jerga.
    muestras = np.frombuffer(crudo, np.float32)
    segmentos, _ = modelo.transcribe(muestras, language=idioma, initial_prompt=pista,
                                     word_timestamps=True, vad_filter=not cancion)  # el filtro de voz corta lo cantado
    total, palabras = len(muestras) / 16000, []
    for s in segmentos:  # se va transcribiendo por trozos: se informa cuánto lleva
        palabras += [{"palabra": w.word.strip(), "inicio": w.start, "fin": w.end} for w in s.words]
        progreso(min(s.end / total, 1))
    progreso(1)  # el último trozo con voz acaba antes que el audio: el progreso se quedaba en el 56 %
    return palabras
