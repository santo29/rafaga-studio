"""Función mágica: pega el enlace de un video largo y saca los mejores shorts."""
import json
import re
import time
from pathlib import Path
from typing import Callable

import yt_dlp

from . import claves, ia, memoria, seguro, video
from .idioma import t

PROYECTOS = Path(__file__).resolve().parent.parent / "datos" / "proyectos"

ESQUEMA = {
    "type": "object",
    "properties": {"clips": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "inicio": {"type": "number"}, "fin": {"type": "number"},
            "titulo": {"type": "string"}, "descripcion": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "puntuacion": {"type": "integer"}, "motivo": {"type": "string"},
        },
        "required": ["inicio", "fin", "titulo", "descripcion", "hashtags", "puntuacion", "motivo"],
        "additionalProperties": False,
    }}},
    "required": ["clips"],
    "additionalProperties": False,
}

INSTRUCCIONES = """Eres editor experto en contenido viral para Shorts, TikTok y Reels.
Recibes la transcripción de un video largo con marcas de tiempo en segundos.
Elige los momentos que funcionarían solos como short: gancho fuerte en los primeros 3 segundos,
una idea completa (no cortes a mitad de frase), emoción, sorpresa, humor o un dato valioso.
Usa los tiempos exactos de la transcripción para inicio y fin. Puntúa cada clip de 0 a 100 según su potencial viral.
Cada clip dura entre el mínimo y el máximo pedidos, empieza al principio de una frase y termina al final de otra, y no
se solapa con otro clip.
Escribe título, descripción y hashtags en el mismo idioma del video."""


def proyectos() -> list[dict]:
    """Los proyectos guardados, del más nuevo al más viejo. Un proyecto.json roto o incompleto se salta."""
    lista = []
    for archivo in sorted(PROYECTOS.glob("*/proyecto.json"), reverse=True):
        try:
            p = json.loads(archivo.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if isinstance(p, dict) and isinstance(p.get("resultados"), list):
            lista.append(p)
    return lista


def _lineas(palabras: list[dict]) -> str:
    """Agrupa las palabras en frases con su tiempo, para que la IA las lea."""
    lineas, actual = [], []
    for p in palabras:
        actual.append(p)
        if p["palabra"][-1:] in ".?!" or p["fin"] - actual[0]["inicio"] > 12:
            lineas.append(f"[{actual[0]['inicio']:.1f}-{p['fin']:.1f}] " + " ".join(x["palabra"] for x in actual))
            actual = []
    if actual:
        lineas.append(f"[{actual[0]['inicio']:.1f}-{actual[-1]['fin']:.1f}] " + " ".join(x["palabra"] for x in actual))
    return "\n".join(lineas)


def _ajustar(clip: dict, palabras: list[dict], total: float) -> dict:
    """Pega el inicio y el fin al borde de palabra más cercano, para no cortar sílabas."""
    ini = min(palabras, key=lambda p: abs(p["inicio"] - clip["inicio"]))["inicio"]
    fin = min(palabras, key=lambda p: abs(p["fin"] - clip["fin"]))["fin"]
    return {**clip, "inicio": max(ini - 0.15, 0), "fin": min(fin + 0.35, total)}


def _a_medida(clip: dict, dur_min: float, dur_max: float) -> bool:
    return dur_min * 0.8 <= clip["fin"] - clip["inicio"] <= dur_max * 1.2


def _elegir(clips: list[dict], cantidad: int, dur_min: float, dur_max: float) -> list[dict]:
    """Los mejores clips que duran lo pedido (con margen) y no repiten el mismo momento (solape de más de la mitad
    del más corto). Si ninguno dura lo pedido, se usan igual (generar lo avisa): mejor eso que no sacar nada tras
    descargar y transcribir."""
    clips = [c for c in clips if _a_medida(c, dur_min, dur_max)] or clips
    elegidos = []
    for c in sorted(clips, key=lambda c: c["puntuacion"], reverse=True):
        if all(min(c["fin"], o["fin"]) - max(c["inicio"], o["inicio"])
               <= 0.5 * min(c["fin"] - c["inicio"], o["fin"] - o["inicio"]) for o in elegidos):
            elegidos.append(c)
    return elegidos[:cantidad]


LIMITE_DESCARGA = 4 * 1024 ** 3  # 4 GB: protege el disco


# Lista de sitios PERMITIDOS (no «todos menos el genérico»): algunos extractores de yt-dlp aceptan cualquier
# dirección (p. ej. Mediasite) y servirían para pedir páginas de la red local. Estos solo aceptan su propio sitio.
SITIOS = re.compile(r"^(Youtube|TikTok|Facebook|Instagram|Vimeo|Twitter|Twitch|Dailymotion|Reddit|Kick|Soundcloud)",
                    re.IGNORECASE)


def _extractores() -> list:
    from yt_dlp.extractor import gen_extractor_classes
    return [ie for ie in gen_extractor_classes() if SITIOS.match(ie.ie_key())]


def _tiene_extractor(url: str) -> bool:
    return any(ie.suitable(url) for ie in _extractores())


def _seguir_enlace_compartido(url: str) -> str:
    """Los enlaces de «Compartir» (fb.watch, facebook.com/share/…, instagram.com/share/…) solo redirigen al video.
    Se siguen aquí, paso a paso y comprobando que cada salto va a un sitio público, porque el extractor genérico de
    yt-dlp (que lo hacía solo) está desactivado: también serviría para pedir páginas de la red local."""
    from urllib.parse import urlsplit
    for _ in range(6):
        if _tiene_extractor(url):
            return url
        siguiente = seguro.redireccion(url)  # http(s) y conexión solo a una IP pública, en CADA salto
        if not siguiente:
            break
        url = siguiente
    if not _tiene_extractor(url):
        raise RuntimeError(t("Ese enlace no es de un sitio de video conocido (YouTube, TikTok, Facebook, Instagram, "
                             "Vimeo…)."))
    if urlsplit(url).scheme not in ("http", "https"):
        raise RuntimeError(t("Ese enlace no lleva a una página web."))
    return url


def descargar(url: str, carpeta: Path, progreso: Callable[[float], None] = lambda f: None) -> tuple[Path, str]:
    def gancho(d):
        if d.get("downloaded_bytes", 0) > LIMITE_DESCARGA:  # tope real: también en streams sin tamaño conocido
            raise yt_dlp.utils.DownloadError(t("el video pasa de 4 GB"))
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if d.get("status") == "downloading" and total:
            progreso(d.get("downloaded_bytes", 0) / total)
    def filtro(info, *, incomplete=False):  # antes de bajar nada: nada de directos ni videos larguísimos
        if info.get("is_live") or (info.get("duration") or 0) > 4 * 3600:
            return t("Solo se aceptan videos grabados de hasta 4 horas (no directos).")
        return None

    opciones = {
        # Solo los sitios de SITIOS (ver arriba): nada que pueda pedir páginas de la red local ni archivos sueltos.
        "allowed_extractors": [re.escape(ie.IE_NAME.lower()) for ie in _extractores()],
        "match_filter": filtro,
        "max_filesize": LIMITE_DESCARGA,
        "progress_hooks": [gancho],
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(carpeta / "original.%(ext)s"),
        "ffmpeg_location": video.FFMPEG,
        "noplaylist": True, "quiet": True, "no_warnings": True,
        # YouTube exige un motor JS (en este PC, Node). Sus scripts vienen del paquete yt-dlp-ejs (fijado en
        # requirements.lock), no de GitHub en cada descarga: nada de código bajado sin control en tiempo de uso.
        "js_runtimes": {"deno": {}, "node": {}},
    }
    url = _seguir_enlace_compartido(url)
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(t("No se pudo descargar ese enlace (solo sitios conocidos como YouTube, TikTok, Facebook o "
                             "Vimeo): {error}", error=str(e).replace("ERROR: ", "")[:300]))
    archivo = next(carpeta.glob("original.*"), None)
    if archivo is None:  # el filtro lo rechazó o pasaba del tamaño máximo: yt-dlp no avisa con un error
        raise RuntimeError(t("No se descargó el video: solo se aceptan videos grabados (no directos) de hasta 4 horas "
                             "y 4 GB."))
    return archivo, (info or {}).get("title", t("video"))


def generar(url: str, formato: str = "9:16", modo: str = "recortar", cantidad: int = 5,
            dur_min: int = 20, dur_max: int = 60, aviso: Callable[[str, float], None] = lambda t, f: None,
            enfoque: str = "") -> dict:
    """enfoque: qué momentos busca el usuario (p. ej. «los consejos de dinero»); vacío = los más virales."""
    url = seguro.enlace_web(url)  # el host se comprueba en cada salto (ver _seguir_enlace_compartido)
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-shorts")
    carpeta.mkdir(parents=True)

    aviso(t("Descargando el video…"), 0.02)
    original, titulo = descargar(url, carpeta,
                                 lambda f: aviso(t("Descargando el video… {p:.0%}", p=f), 0.02 + 0.12 * f))
    total = video.duracion(original)

    aviso(t("Sacando el audio…"), 0.15)
    audio = carpeta / "audio.mp3"
    video.ffmpeg("-i", original, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", audio)

    transcribiendo = t("Transcribiendo en la nube…") if (claves.para("transcripcion") or {}).get("clave") else \
        t("Transcribiendo en tu PC (lento; con Groq gratis es mucho más rápido)…")
    aviso(transcribiendo, 0.2)
    palabras = ia.transcribir(audio, progreso=lambda f: aviso(f"{transcribiendo} {f:.0%}", 0.2 + 0.3 * f))
    if not palabras:
        raise RuntimeError(t("No se encontró voz en el video."))
    (carpeta / "transcripcion.json").write_text(json.dumps(palabras, ensure_ascii=False), encoding="utf-8")

    aviso(t("La IA está eligiendo los mejores momentos…"), 0.5)
    pedido = (f"Título del video: {titulo}\nDuración total: {total:.0f} s\n"
              f"Quiero {cantidad} clips de entre {dur_min} y {dur_max} segundos, del mejor al peor.\n"
              + (f"El usuario busca: {enfoque.strip()[:300]}. Elige SOLO momentos de eso.\n" if enfoque.strip() else "")
              + f"\nTranscripción:\n{_lineas(palabras)}")
    clips = ia.texto_json(INSTRUCCIONES, pedido + memoria.para("edicion"), ESQUEMA)["clips"]
    clips = [_ajustar(c, palabras, total) for c in clips if 0 <= c["inicio"] < c["fin"] <= total + 1]
    clips = _elegir(clips, cantidad, dur_min, dur_max)
    avisos = [] if not clips or _a_medida(clips[0], dur_min, dur_max) else [
        t("Ningún momento del video duraba entre {minimo} y {maximo} s: estos shorts tienen otra duración.",
          minimo=dur_min, maximo=dur_max)]

    for i, c in enumerate(clips, 1):
        aviso(t("Montando short {n} de {total}…", n=i, total=len(clips)), 0.55 + 0.43 * (i - 1) / max(len(clips), 1))
        c["archivo"] = str(video.recortar(original, c["inicio"], c["fin"], formato, modo, palabras,
                                          carpeta / f"short_{i:02d}.mp4"))

    proyecto = {"tipo": "shorts", "url": url, "titulo": titulo, "formato": formato,
                "carpeta": str(carpeta), "resultados": clips, "avisos": avisos}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto
