"""Investigador de nichos virales: datos reales de YouTube + investigación web en vivo + análisis de la IA."""
import json
import queue
import threading
import time
from datetime import datetime
from typing import Callable

import yt_dlp

from . import claves, ia, memoria
from .idioma import actual, IDIOMAS, t, texto_de_error
from .shorts import PROYECTOS

# Plazos (s): ningún paso puede dejar la investigación esperando sin fin. Lo que no llega a tiempo se deja y se dice.
# Antes iba todo seguido: 3 búsquedas × (la búsqueda + 12 videos pedidos uno a uno) eran 1,5 a 3 min solo de YouTube.
PLAZO_BUSQUEDA = 45  # las tres búsquedas de YouTube, a la vez (cada una tarda unos 3 s)
PLAZO_FECHAS = 20  # las fechas exactas (unos 5 s cada una); el que no llega se queda con la fecha aproximada
PLAZO_WEB = 150  # la investigación en internet (Claude), que va a la vez que YouTube: luego se sigue con lo que haya
CON_FECHA = 8  # de los videos de las tres búsquedas, a cuántos de los más vistos se les pide la fecha exacta
YDL = {"quiet": True, "no_warnings": True, "socket_timeout": 15}  # yt-dlp no espera sin fin a un servidor callado
FECHAS = PROYECTOS.parent / "nichos" / "fechas.json"  # caché: la fecha de subida de un video no cambia
VIGENCIA_FECHAS, MAX_FECHAS = 30 * 86400, 5000

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


def _a_tiempo(tareas: dict, plazo: float, hilos: int = 6) -> dict:
    """Corre las tareas ({nombre: función}), `hilos` a la vez, y devuelve {nombre: resultado} de las que acabaron antes
    de `plazo` segundos: una que falla o tarda más se deja, sin frenar a las demás. En hilos daemon: Python espera a los
    de un ThreadPoolExecutor, también al cerrar la app, y uno colgado la colgaba."""
    cola, hechas, cerrojo = queue.SimpleQueue(), {}, threading.Lock()
    for tarea in tareas.items():
        cola.put(tarea)

    def obrero():
        while True:
            try:
                nombre, funcion = cola.get_nowait()
            except queue.Empty:
                return
            try:
                resultado = funcion()
            except Exception:  # noqa: BLE001  la que falla se queda sin dato, como la que tarda
                continue
            with cerrojo:
                hechas[nombre] = resultado
    fin = time.monotonic() + plazo
    obreros = [threading.Thread(target=obrero, daemon=True) for _ in range(min(hilos, len(tareas)))]
    for o in obreros:
        o.start()
    for o in obreros:
        o.join(max(0.0, fin - time.monotonic()))
    with cerrojo:  # las que siguen después del plazo ya no cuentan
        return dict(hechas)


def _fecha(video_id: str) -> str | None:
    """Fecha de subida exacta (AAAAMMDD): hay que pedir el video entero (unos 5 s)."""
    opciones = {**YDL, "skip_download": True,
                "js_runtimes": {"deno": {}, "node": {}}}  # scripts de yt-dlp-ejs (ver shorts.py), no de GitHub
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False).get("upload_date")
    except Exception:  # video privado o bloqueado: se queda sin fecha
        return None


def _buscar(consulta: str, cantidad: int = 40) -> list[dict]:
    """Los videos de una búsqueda, sin entrar en cada uno (unos 3 s). Con «approximate_date», yt-dlp da la fecha que
    enseña YouTube («hace 3 días»): basta para las vistas por día sin pedir los videos uno a uno."""
    opciones = {**YDL, "extract_flat": True, "extractor_args": {"youtubetab": {"approximate_date": [""]}}}
    with yt_dlp.YoutubeDL(opciones) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch{cantidad}:{consulta}", download=False)
        except Exception:  # una búsqueda que falla no debe tumbar la investigación
            return []
    # Solo videos: fuera canales y listas (sus ids no tienen 11 caracteres).
    return [e for e in info.get("entries") or [] if e and len(e.get("id", "")) == 11 and e.get("view_count")]


def _fechas_guardadas() -> dict:
    """{id: [AAAAMMDD, cuándo se guardó]} de la caché, sin las que pasaron de VIGENCIA_FECHAS."""
    try:
        datos = json.loads(FECHAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ahora = time.time()
    return {i: v for i, v in datos.items() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)
            and isinstance(v[1], (int, float)) and ahora - v[1] < VIGENCIA_FECHAS} if isinstance(datos, dict) else {}


def _youtube(consultas: list[str], avisar: Callable[[str, float], None]) -> list[dict]:
    """Videos de varias búsquedas de YouTube a la vez, sin repetir, con sus vistas por día. La fecha exacta, solo de los
    CON_FECHA más vistos cuya fecha aproximada es gruesa («hace 1 año»; «hace 3 días» ya vale), de la caché o pedida
    en PLAZO_FECHAS como mucho; el resto, con la aproximada."""
    listas = _a_tiempo({c: (lambda c=c: _buscar(c)) for c in consultas}, PLAZO_BUSQUEDA)
    videos, hoy = {}, time.time()
    for consulta in consultas:
        for e in listas.get(consulta, []):
            videos.setdefault(e["id"], e)
    guardadas = _fechas_guardadas()
    gruesas = [e for e in videos.values() if hoy - (e.get("timestamp") or 0) > 7 * 86400]
    faltan = [e["id"] for e in sorted(gruesas, key=lambda e: e["view_count"], reverse=True)[:CON_FECHA]
              if e["id"] not in guardadas]
    if faltan:
        avisar(t("YouTube: fecha de los videos más vistos…"), 0.2)
        nuevas = _a_tiempo({i: (lambda i=i: _fecha(i)) for i in faltan}, PLAZO_FECHAS)
        guardadas.update({i: [f, hoy] for i, f in nuevas.items() if f})
        try:  # las más recientes; sin caché, la próxima vez solo tarda más
            FECHAS.parent.mkdir(parents=True, exist_ok=True)
            claves._reemplazar(FECHAS, json.dumps(dict(sorted(guardadas.items(), key=lambda x: x[1][1])[-MAX_FECHAS:])))
        except OSError:
            pass
    salida = []
    for e in videos.values():
        fecha = (guardadas.get(e["id"]) or [None])[0]
        subido = datetime.strptime(fecha, "%Y%m%d").timestamp() if fecha else e.get("timestamp")
        dias = max((hoy - subido) / 86400, 1) if subido else None
        salida.append({"titulo": e.get("title"), "canal": e.get("channel") or e.get("uploader"),
                       "vistas": e["view_count"], "dias": round(dias) if dias else None,
                       "vistas_por_dia": round(e["view_count"] / dias) if dias else None,
                       "segundos": e.get("duration"), "short": (e.get("duration") or 999) <= 60})
    # Lo que explota ahora primero (más vistas por día); luego el resto por vistas.
    salida.sort(key=lambda v: (v["vistas_por_dia"] or 0, v["vistas"]), reverse=True)
    return salida


def investigar(tema: str = "", redes: str = "YouTube, TikTok, Instagram y Facebook", pais: str = "Latinoamérica",
               aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    inicio = time.monotonic()

    def avisar(texto: str, fraccion: float) -> None:  # con el tiempo que lleva: se ve que avanza y no está parado
        aviso(f"{texto} · {round(time.monotonic() - inicio)} s", fraccion)

    semilla = tema.strip() or t("videos virales")  # en el idioma de la app: así YouTube trae lo de su público
    # La web (Claude) y YouTube no dependen una de otra: van a la vez. La web, con su plazo y en un hilo daemon
    web = {}

    def buscar_web():
        try:
            web["texto"] = ia.investigar_web(
                f"Investiga en internet qué nichos y formatos de video se están haciendo virales AHORA "
                f"({time.strftime('%B %Y')}) en {redes}, para el público de {pais}, relacionados con: {semilla}. Busca "
                "tendencias, hashtags en auge, sonidos o formatos que estén explotando, y nichos con poca competencia. "
                "Da datos concretos y fuentes, en un resumen breve (unas 400 palabras).", plazo=PLAZO_WEB)
        except Exception as e:  # noqa: BLE001  sin la web, el análisis sigue con YouTube (y se dice)
            web["error"] = e
        web["segundos"] = time.monotonic() - inicio
    hilo_web = threading.Thread(target=buscar_web, daemon=True)
    hilo_web.start()
    avisar(t("Buscando videos en YouTube…"), 0.05)
    vistos, unicos = set(), []
    for v in _youtube([semilla, f"{semilla} shorts", f"{semilla} {time.strftime('%Y')}"], avisar):
        if v["titulo"] not in vistos:
            vistos.add(v["titulo"])
            unicos.append(v)
    de_youtube = time.monotonic() - inicio

    limite = inicio + PLAZO_WEB * 1.1  # un 10 % más: lo que tarda en cortarse sola al llegar a su plazo
    while hilo_web.is_alive() and time.monotonic() < limite:
        avisar(t("Investigando tendencias en internet (TikTok, Instagram, Facebook)…"),
               0.3 + 0.35 * min((time.monotonic() - inicio) / PLAZO_WEB, 1))
        hilo_web.join(max(0.0, min(5.0, limite - time.monotonic())))
    texto_web, notas = web.get("texto"), []
    if hilo_web.is_alive():
        notas.append(t("La investigación en internet tardó demasiado: el análisis siguió solo con YouTube."))
    elif web.get("error"):
        notas.append(t("La investigación en internet falló ({causa}): el análisis siguió solo con YouTube.",
                       causa=texto_de_error(web["error"])))
    elif texto_web and web["segundos"] >= PLAZO_WEB:
        notas.append(t("La investigación en internet llegó a su tiempo máximo: se usó lo que alcanzó a encontrar."))
    for nota in notas:
        avisar(nota, 0.65)

    con_clave = bool((claves.para("texto") or {}).get("clave"))
    con_claude = (claves.para("texto") or {}).get("proveedor") == "anthropic"
    pedido = (f"Tema o semilla: {semilla}\nRedes: {redes}\nPúblico: {pais}\nFecha: {time.strftime('%Y-%m-%d')}\n\n"
              f"Videos de YouTube (datos reales). Vistas por día alto en un video de pocos días = está explotando ahora.\n"
              + "\n".join(f"- {v['titulo']} | {v['canal']} | {v['vistas']:,} vistas"
                          + (f" | {v['vistas_por_dia']:,}/día, subido hace {v['dias']} días" if v["vistas_por_dia"] else "")
                          + (" | SHORT" if v["short"] else "") for v in unicos[:90 if con_clave else 40])
              + (f"\n\nInvestigación web en vivo:\n{texto_web}" if texto_web else
                 "\n\n(Sin investigación web esta vez: no terminó a tiempo o falló. Analiza con los datos de YouTube e "
                 "indícalo en el resumen.)" if con_claude else
                 "\n\n(Sin investigación web: conecta una clave de Claude para analizar también TikTok, Instagram y "
                 "Facebook en vivo. Indícalo en el resumen.)")
              # La IA gratis sin clave es pequeña: con menos que escribir no se deja campos vacíos.
              + ("\n\nDame 5 nichos." if con_clave else
                 "\n\nDame 2 nichos, con 2 ideas cada uno. Todo breve: prompts de máximo 30 palabras."))
    listo = threading.Event()

    def reloj():  # el análisis tarda uno o dos minutos: el tiempo que lleva, cada 5 s
        while not listo.wait(5):
            avisar(t("La IA está analizando los nichos…"), 0.7)
    avisar(t("La IA está analizando los nichos…"), 0.7)
    hilo_reloj = threading.Thread(target=reloj, daemon=True)
    hilo_reloj.start()
    antes = time.monotonic()
    try:
        resultado = ia.texto_json(INSTRUCCIONES, pedido + memoria.para("nichos"), ESQUEMA)
    finally:
        listo.set()
        hilo_reloj.join(1)  # su último aviso no puede llegar después del «¡Listo!»
    resultado["nichos"].sort(key=lambda n: n["potencial"], reverse=True)
    print(f"[Ráfaga] Nichos en {time.monotonic() - inicio:.0f} s: YouTube {de_youtube:.0f} s, web "
          + (f"{web['segundos']:.0f} s (a la vez)" if "segundos" in web else "sin terminar")
          + f", análisis {time.monotonic() - antes:.0f} s", flush=True)

    carpeta = PROYECTOS.parent / "nichos"
    carpeta.mkdir(parents=True, exist_ok=True)
    resultado.update({"tema": semilla, "fecha": time.strftime("%Y-%m-%d %H:%M"), "con_web": bool(texto_web),
                      **({"avisos": notas} if notas else {})})
    (carpeta / time.strftime("%Y%m%d-%H%M%S.json")).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return resultado
