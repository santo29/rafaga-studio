"""Investigador de nichos virales: datos reales de YouTube + investigación web en vivo + análisis de la IA."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

import yt_dlp

from . import claves, ia, memoria
from .idioma import actual, IDIOMAS, t
from .shorts import PROYECTOS

ESQUEMA = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string"},
        "nichos": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "potencial": {"type": "integer"},
                "competencia": {"type": "string", "enum": ["baja", "media", "alta"]},
                "por_que_es_viral": {"type": "string"},
                "redes": {"type": "array", "items": {"type": "string"}},
                "formato": {"type": "string"},
                "monetizacion": {"type": "string"},
                "pruebas": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "ideas": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"titulo": {"type": "string"}, "gancho": {"type": "string"},
                                   "prompt": {"type": "string"}},
                    "required": ["titulo", "gancho", "prompt"], "additionalProperties": False}},
            },
            "required": ["nombre", "potencial", "competencia", "por_que_es_viral", "redes", "formato",
                         "monetizacion", "pruebas", "hashtags", "ideas"],
            "additionalProperties": False}},
    },
    "required": ["resumen", "nichos"],
    "additionalProperties": False,
}

INSTRUCCIONES = """Eres el mejor estratega de contenido viral del mundo: conoces YouTube, TikTok, Instagram y Facebook.
Con los datos reales que te paso, encuentra nichos con mucha demanda y poca competencia que una persona pueda
producir con videos hechos por IA (narración, imágenes, animación, subtítulos), sin salir en cámara.
Basa cada nicho en pruebas de los datos (cita vistas, vistas por día o tendencias concretas) y dilo en "pruebas".
Puntúa el potencial de 0 a 100. En monetizacion: RPM aproximado, afiliados o productos posibles.
Para cada nicho da 5 ideas de video (o las que se pidan) listas para producir: título, gancho de los primeros 3 segundos y un
"prompt" completo para que el generador de videos lo cree. Responde en este idioma: """ + IDIOMAS[actual()] + ".\n" + ia.FALTAS


def _fecha(video_id: str) -> str | None:
    """Fecha de subida (AAAAMMDD). La búsqueda rápida no la trae, hay que pedirla video a video."""
    opciones = {"quiet": True, "no_warnings": True, "skip_download": True,
                "js_runtimes": {"deno": {}, "node": {}}}  # scripts de yt-dlp-ejs (fijado), no de GitHub
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False).get("upload_date")
    except Exception:  # video privado o bloqueado: se queda sin fecha
        return None


def _youtube(consulta: str, cantidad: int = 40, con_fecha: int = 12) -> list[dict]:
    """Videos de YouTube para una búsqueda. A los `con_fecha` más vistos se les calcula las vistas por día."""
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch{cantidad}:{consulta}", download=False)
        except Exception:  # una búsqueda que falla no debe tumbar la investigación
            return []
    # Solo videos: fuera canales y listas (sus ids no tienen 11 caracteres).
    videos = [e for e in info.get("entries") or [] if e and len(e.get("id", "")) == 11 and e.get("view_count")]
    videos.sort(key=lambda e: e["view_count"], reverse=True)
    with ThreadPoolExecutor(6) as hilos:
        fechas = dict(zip((e["id"] for e in videos[:con_fecha]), hilos.map(_fecha, [e["id"] for e in videos[:con_fecha]])))
    hoy = time.time()
    salida = []
    for e in videos:
        fecha = fechas.get(e["id"])
        dias = max((hoy - datetime.strptime(fecha, "%Y%m%d").timestamp()) / 86400, 1) if fecha else None
        salida.append({"titulo": e.get("title"), "canal": e.get("channel") or e.get("uploader"),
                       "vistas": e["view_count"], "dias": round(dias) if dias else None,
                       "vistas_por_dia": round(e["view_count"] / dias) if dias else None,
                       "segundos": e.get("duration"), "short": (e.get("duration") or 999) <= 60})
    # Lo que explota ahora primero (más vistas por día); luego el resto por vistas.
    salida.sort(key=lambda v: (v["vistas_por_dia"] or 0, v["vistas"]), reverse=True)
    return salida


def investigar(tema: str = "", redes: str = "YouTube, TikTok, Instagram y Facebook", pais: str = "Latinoamérica",
               aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    semilla = tema.strip() or t("videos virales")  # en el idioma de la app: así YouTube trae lo de su público
    aviso(t("Buscando videos en YouTube…"), 0.05)
    datos = []
    for i, consulta in enumerate([semilla, f"{semilla} shorts", f"{semilla} {time.strftime('%Y')}"]):
        aviso(t("YouTube: «{consulta}»…", consulta=consulta), 0.05 + 0.1 * i)
        datos += _youtube(consulta)
    vistos, unicos = set(), []
    for v in sorted(datos, key=lambda v: (v["vistas_por_dia"] or 0, v["vistas"]), reverse=True):
        if v["titulo"] not in vistos:
            vistos.add(v["titulo"])
            unicos.append(v)

    aviso(t("Investigando tendencias en internet (TikTok, Instagram, Facebook)…"), 0.4)
    web = ia.investigar_web(
        f"Investiga en internet qué nichos y formatos de video se están haciendo virales AHORA ({time.strftime('%B %Y')}) "
        f"en {redes}, para el público de {pais}, relacionados con: {semilla}. Busca tendencias, hashtags en auge, "
        "sonidos o formatos que estén explotando, y nichos con poca competencia. Da datos concretos y fuentes.")

    aviso(t("La IA está analizando los nichos…"), 0.7)
    con_clave = bool((claves.para("texto") or {}).get("clave"))
    pedido = (f"Tema o semilla: {semilla}\nRedes: {redes}\nPúblico: {pais}\nFecha: {time.strftime('%Y-%m-%d')}\n\n"
              f"Videos de YouTube (datos reales). Vistas por día alto en un video de pocos días = está explotando ahora.\n"
              + "\n".join(f"- {v['titulo']} | {v['canal']} | {v['vistas']:,} vistas"
                          + (f" | {v['vistas_por_dia']:,}/día, subido hace {v['dias']} días" if v["vistas_por_dia"] else "")
                          + (" | SHORT" if v["short"] else "") for v in unicos[:90 if con_clave else 40])
              + (f"\n\nInvestigación web en vivo:\n{web}" if web else
                 "\n\n(Sin investigación web: conecta una clave de Claude para analizar también TikTok, Instagram y "
                 "Facebook en vivo. Indícalo en el resumen.)")
              # La IA gratis sin clave es pequeña: con menos que escribir no se deja campos vacíos.
              + ("\n\nDame 5 nichos." if con_clave else
                 "\n\nDame 2 nichos, con 2 ideas cada uno. Todo breve: prompts de máximo 30 palabras."))
    resultado = ia.texto_json(INSTRUCCIONES, pedido + memoria.para("nichos"), ESQUEMA)
    resultado["nichos"].sort(key=lambda n: n["potencial"], reverse=True)

    carpeta = PROYECTOS.parent / "nichos"
    carpeta.mkdir(parents=True, exist_ok=True)
    resultado.update({"tema": semilla, "fecha": time.strftime("%Y-%m-%d %H:%M"), "con_web": bool(web)})
    (carpeta / time.strftime("%Y%m%d-%H%M%S.json")).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return resultado
