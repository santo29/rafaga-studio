"""Render del editor de video (motor/edicion): fotogramas para la vista previa, miniaturas y formas de onda para la
línea de tiempo, la vista previa reproducible y el MP4 final. Sin ventanas: lo llama la interfaz desde un hilo de
trabajo (ui.comun.Tarea); nada de esto debe correr en el hilo de la ventana.

Cómo sale un video (vista_previa y exportar van por el mismo camino; solo cambian el tamaño y la calidad):
1. Cada clip se normaliza a un «tramo» A/V (tamaño, fps, encaje, movimiento, filtro, ajustes, velocidad, volumen) que se
   guarda en cache/ con el hash de lo que lo define: cambiar un texto, una transición o un audio no lo rehace. Cada
   transición se hace aparte como un «paso» (xfade + acrossfade de la cola de un tramo y la cabeza del siguiente).
2. Un solo ffmpeg corta y pega tramos y pasos, pone las capas (cada una, un PNG transparente pintado con
   diseno.ItemCapa), los subtítulos (video.subtitulos_ass) y mezcla los audios (adelay, afade, volume y amix sin
   normalizar). Sale con progreso real (-progress de ffmpeg).
Los tiempos se pasan a fotogramas desde la línea de tiempo (edicion.tiempos), no clip a clip: 300 clips no acumulan
desfase. Entradas de capa: «fundido» (aparece poco a poco), «deslizar» (entra desde la izquierda), «aparecer» (crece
desde la mitad con un fundido rápido); salida «fundido», se apaga. Cada una dura _ANIMACION s (o la mitad de la capa).
En cache/ solo quedan los tramos, pasos, capas y vista previa del último render de cada tamaño (los tramos y pasos de
exportar, casi sin pérdida, se borran al acabar) y los proxies de sus clips: lo demás se borra.
Un clip o audio con «falta» (su archivo no estaba al abrir el proyecto) no hace fallar nada: el clip se ve del color de
fondo y en silencio durante su tramo, y el audio no suena.
Proxies: miniatura() encarga, para los videos más grandes que la vista previa, una copia ligera (_proxy) que se hace en
un hilo aparte con prioridad baja; fotograma() la usa en cuanto está (saltar en un 4K HEVC o en una grabación de
pantalla con un fotograma clave cada 8 s cuesta 1–2 s por fotograma; en el proxy, ~0,15 s).
"""
import atexit
import hashlib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter
from PySide6.QtWidgets import QGraphicsScene

from . import diseno, edicion, seguro, video
from .idioma import t

VERSION = 3  # súbela si cambia cómo se hace un tramo o una capa: la caché vieja deja de valer
_R = 48000  # Hz del audio de trabajo: a 24, 25, 30 y 60 fps cada fotograma son muestras enteras
_ANIMACION = 0.4
_ZOOM = 0.15  # acercar/alejar de las fotos: del 100 % al 115 % a lo largo del clip
_XFADE = {"fundido": "fade", "disolver": "dissolve", "deslizar_izq": "slideleft", "deslizar_der": "slideright",
          "deslizar_arriba": "slideup", "barrido": "wipeleft", "circulo": "circleopen", "zoom": "zoomin",
          "pixelado": "pixelize"}
_FILTROS = {"byn": "hue=s=0", "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
            # Sombras, medios y luces: con solo rs/gs/bs (las sombras) casi no se notaba
            "calido": "colorbalance=rs=.12:gs=.04:bs=-.12:rm=.12:gm=.04:bm=-.12:rh=.06:bh=-.06",
            "frio": "colorbalance=rs=-.12:bs=.12:rm=-.12:bm=.12:rh=-.06:bh=.06",
            "vintage": "curves=preset=vintage", "vivo": "eq=saturation=1.5:contrast=1.1", "vineta": "vignette=PI/4",
            "desenfoque": "boxblur={r}:2"}
# (preset, crf) del tramo y del video final. Los tramos de exportar casi sin pérdida: luego se codifican otra vez
_CALIDAD = {False: (("ultrafast", 26), ("ultrafast", 28)), True: (("ultrafast", 16), ("veryfast", 20))}


# ---------- Utilidades ----------

def _hash(*partes) -> str:
    return hashlib.sha1(json.dumps(partes, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _huella(ruta: Path) -> tuple:
    st = ruta.stat()  # si el archivo cambia, cambia la clave de su caché
    return str(ruta), st.st_size, st.st_mtime_ns


def _cache(carpeta) -> Path:
    cache = diseno._local(carpeta) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _a_disco(destino: Path, hacer) -> Path:
    """hacer(temporal) escribe el archivo y se le cambia el nombre al final: otro render nunca lee uno a medias."""
    temporal = destino.with_name(f"tmp-{uuid.uuid4().hex[:8]}-{destino.name}")
    try:
        hacer(temporal)
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return destino


def _limpiar(cache: Path, patron: str, usados: set) -> None:
    for archivo in cache.glob(patron):
        if archivo.name not in usados:
            try:
                archivo.unlink()
            except OSError:
                pass  # lo está leyendo otro render (Windows no deja borrarlo): se irá la próxima vez


def _tamano(formato: str, alto: int) -> tuple[int, int]:
    ancho_f, alto_f = video.FORMATOS[formato]
    h = min(alto, alto_f) // 2 * 2  # pares: yuv420p
    return round(ancho_f * h / alto_f / 2) * 2, h


def _liso(w: int, h: int, color: str) -> QImage:
    imagen = QImage(w, h, QImage.Format_RGB32)
    imagen.fill(QColor(color))
    return imagen


def _marcos(p: dict) -> list[tuple[int, int]]:
    """(primer fotograma, fin) de cada clip, redondeando los tiempos de la línea de tiempo."""
    return [(round(a * p["fps"]), round(b * p["fps"])) for a, b in edicion.tiempos(p)]


def _cuadros_tramo(c: dict, fps: int) -> int:
    # Uno de más: según dónde caiga el clip, redondear le da un fotograma más o menos; el montaje corta lo que sobra
    return round(edicion.duracion_clip(c) * fps) + 1


@lru_cache(maxsize=512)
def _cabecera(ruta: str, _huella_archivo: tuple) -> str:
    """Lo que dice `ffmpeg -i` del archivo: dónde empieza y sus pistas."""
    return subprocess.run([video.FFMPEG, "-hide_banner", "-format_whitelist", video.MEDIOS, "-i", ruta],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stderr


def _tiene_audio(ruta: str, huella: tuple) -> str:
    """"" si no tiene sonido; si no, lo que hay que poner antes de pasarlo a estéreo."""
    linea = re.search(r"Stream #\S+.*: Audio:.*", _cabecera(ruta, huella))
    # ffmpeg pasa un mono a estéreo a -3 dB por lado: una voz mono sonaría más baja que el volumen pedido
    return "" if not linea else "pan=stereo|c0=c0|c1=c0," if ", mono," in linea[0] else "anull,"


def _correr(args: list, cwd: Path, segundos: float, avance=lambda f: None) -> None:
    """ffmpeg con progreso real: -progress manda out_time_us a medida que codifica."""
    orden = [video.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
             *video.solo_medios([str(a) for a in args])]
    if len(subprocess.list2cmdline(orden)) > 32_000:  # el límite de Windows (50 audios de rutas larguísimas)
        raise ValueError(t("Hay demasiados audios (o sus carpetas tienen nombres muy largos) para montar el video: "
                           "quita alguno o muévelos a una carpeta más corta."))
    with tempfile.TemporaryFile() as errores:  # a un archivo: un pipe lleno sin leer colgaría ffmpeg
        proceso = subprocess.Popen(orden, cwd=cwd, stdout=subprocess.PIPE, stderr=errores, text=True,
                                   encoding="utf-8", errors="replace")
        _procesos.add(proceso)
        if _cerrando.is_set():  # cancelar() ya pasó por _procesos sin verlo
            proceso.kill()
        try:
            for linea in proceso.stdout:
                if linea.startswith("out_time_us=") and linea[12:].strip().isdigit():
                    avance(min(int(linea[12:]) / 1e6 / max(segundos, 0.001), 1.0))
            fallo = proceso.wait()
        finally:
            _procesos.discard(proceso)
        if fallo:
            errores.seek(0)
            # El principio: ffmpeg dice primero la causa y luego todo lo que se paró por ella
            raise RuntimeError(t("ffmpeg falló: {error}",
                                 error=errores.read().decode("utf-8", "replace").strip()[:800]))


# ---------- La imagen de cada clip ----------

def _foto(real: Path, cache: Path) -> Path:
    """La foto derecha (con el giro que el móvil guarda en el EXIF y ffmpeg no aplica), en JPG y como mucho de 4096 px:
    una de 50 MP haría lento cada fotograma."""
    destino = cache / f"foto-{_hash(VERSION, _huella(real))}.jpg"
    if destino.is_file():
        return destino

    def hacer(temporal):
        lector = QImageReader(str(real))
        lector.setAutoTransform(True)
        imagen = lector.read()
        if imagen.isNull():
            raise ValueError(t("No se pudo leer la foto {nombre}: {error}", nombre=real.name,
                               error=lector.errorString()))
        if max(imagen.width(), imagen.height()) > 4096:
            imagen = imagen.scaled(4096, 4096, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lienzo = QImage(imagen.size(), QImage.Format_RGB32)
        lienzo.fill(Qt.black)  # lo transparente de un PNG, en negro (como lo vería ffmpeg)
        p = QPainter(lienzo)
        p.drawImage(0, 0, imagen)
        p.end()
        if not lienzo.save(str(temporal), "JPG", 95):
            raise RuntimeError(t("No se pudo preparar la foto {nombre}.", nombre=real.name))
    return _a_disco(destino, hacer)


def _entrada(c: dict, cache: Path) -> Path:
    """El archivo del clip, validado justo antes de dárselo a ffmpeg (el proyecto puede venir de fuera)."""
    if c["tipo"] == "video":
        real = seguro.archivo_medio(c["archivo"], seguro.VIDEOS, t("clip"))
        # Un .mp4 o .webm de solo sonido como clip: lo guardaban las versiones de antes al importar una canción
        if (not re.search(r"Stream #\S+.*: Video:(?!.*attached pic)", _cabecera(str(real), _huella(real)))
                and _tiene_audio(str(real), _huella(real))):
            raise ValueError(t("{nombre} no tiene imagen, solo sonido: bórralo de la pista de video e impórtalo en la "
                               "pestaña Audio con «Importar música o sonido».", nombre=real.name))
        return real
    return _foto(seguro.archivo_medio(c["archivo"], seguro.IMAGENES, t("clip")), cache)


def _salto(entrada, t: float) -> tuple[list, float]:
    """Lo que va antes de -i para empezar a leer en t (nada en 0) y los segundos que se leen de más antes de t (hay que
    restarlos a los tiempos). -noaccurate_seek: ffmpeg entrega desde el fotograma clave, con tiempos negativos, y
    fps:start_time=0 se queda con el que se ve en t; -ss a secas tiraba el que empezó antes de t (en un video de tasa
    variable, toda una pantalla quieta). En .ts, 10 s antes: ffmpeg cae en cualquier paquete y decodifica desde el
    fotograma clave siguiente (después del último, ninguno)."""
    m = min(t, 10.0) if "Input #0, mpegts" in _cabecera(str(entrada), _huella(Path(entrada))) else 0.0
    return (["-noaccurate_seek", "-ss", f"{t - m:.6f}"] if t > m else []), m


_PROXY = 640  # lado corto del proxy: el alto de la vista previa
_proxies = queue.Queue()  # (video, proxy) por hacer
_en_curso = []  # [ffmpeg, temporal] del proxy que se está haciendo: se para al cerrar la app
_procesos = set()  # los ffmpeg de _correr en marcha: cancelar() los para
_cerrando = threading.Event()  # al salir: ni uno más (su ffmpeg seguiría solo, escribiendo un tmp-…)


def _proxy(entrada: Path, cache: Path) -> Path:
    """Dónde va (o está) la copia ligera del video: lado corto de 640, un fotograma clave cada 15 y los mismos
    tiempos que el original (con su sonido, para que empiece donde él: -ss cuenta desde la primera pista)."""
    return cache / f"proxy-{_hash(VERSION, _huella(entrada))}.mp4"


def _hacer_proxy(entrada: Path, temporal: Path) -> None:
    proceso = subprocess.Popen(
        [video.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *video.solo_medios([
            "-i", str(entrada), "-map", "0:v:0", "-map", "0:a:0?", "-vf",
            f"scale=w='if(gt(iw,ih),-2,min({_PROXY},iw))':h='if(gt(iw,ih),min({_PROXY},ih),-2)'",
            # Los tiempos de cada fotograma, tal cual: con la base de tiempo de 1/fps, una imagen que empieza en 0.3 s
            # a 25 fps pasaba a 0.32
            "-fps_mode", "passthrough", "-enc_time_base:v", "-1", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "28", "-g", "15",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k", "-ac", "1", str(temporal)])],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))  # con lo que le sobra al PC
    _en_curso[:] = [proceso, temporal]
    if _cerrando.is_set():  # _parar_proxy ya miró _en_curso sin verlo
        proceso.kill()
    inicio = re.search(r"start: (-?[\d.]+)", "" if proceso.wait() else _cabecera(str(temporal), ()))
    if not inicio or abs(float(inicio[1])) > 0.001:  # una pista que empieza antes que imagen y sonido: no valdría
        raise RuntimeError("No se pudo hacer el proxy.")


def _hacer_proxies() -> None:
    while True:
        entrada, destino = _proxies.get()
        try:
            if not _cerrando.is_set() and not destino.is_file():
                _a_disco(destino, lambda temporal: _hacer_proxy(entrada, temporal))
        except Exception:
            pass  # sin proxy, fotograma() usa el original: más lento, pero sale bien
        finally:
            _en_curso.clear()
            _proxies.task_done()


def _parar_proxy() -> None:
    _cerrando.set()  # antes de mirar _en_curso: o el hilo ve la señal o aquí se ve su proceso
    hecho = list(_en_curso)
    if hecho:
        hecho[0].kill()
        hecho[0].wait()
        try:  # el hilo del proxy puede estar borrándolo a la vez (Windows da PermissionError): no debe cortar cancelar()
            hecho[1].unlink(missing_ok=True)
        except OSError:
            pass


atexit.register(_parar_proxy)
threading.Thread(target=_hacer_proxies, daemon=True).start()


def _encajar(ajuste: str, w: int, h: int) -> str:
    """video.filtro_formato a cualquier tamaño (la vista previa va en pequeño: escalar primero a 1080p y luego bajar
    costaría 5 veces más en un i3) y con el desenfoque del fondo a escala."""
    if ajuste == "difuminar":
        return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"boxblur={max(2, round(25 * min(w, h) / 1080))}:5[fondo];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[frente];"
                f"[fondo][frente]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def _aspecto(c: dict, w: int, h: int, fps: int, ajuste: str, d: int, j0: int = 0) -> str:
    """Encaje, movimiento, filtro y ajustes de un clip: los mismos en el tramo y en el fotograma (lo que ves es lo que
    sale). d: fotogramas que saca el zoom de una foto; j0: el fotograma del clip por el que empieza."""
    if c["movimiento"] != "ninguno":  # solo fotos (lo asegura edicion.validar)
        z = f"{_ZOOM}*min(1,(on+{j0})/{max(1, round(edicion.duracion_clip(c) * fps))})"
        z = f"1+{z}" if c["movimiento"] == "acercar" else f"{1 + _ZOOM}-{z}"
        # Al doble de tamaño: zoompan corta en píxeles enteros y, a tamaño final, la foto tiembla
        partes = [_encajar(ajuste, 2 * w, 2 * h),
                  f"zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={d}:s={w}x{h}:fps={fps}"]
    else:
        partes = [_encajar(ajuste, w, h)]
    if c["filtro"] != "ninguno":
        partes.append(_FILTROS[c["filtro"]].format(r=max(1, round(min(w, h) / 60))))
    if c["brillo"] or c["contraste"] or c["saturacion"]:
        partes.append(f"eq=brightness={c['brillo'] / 300:.4f}:contrast={1 + c['contraste'] / 200:.4f}:"
                      f"saturation={1 + c['saturacion'] / 100:.4f}")
    return ",".join(partes)


def _atempo(v: float) -> str:
    if v == 1:
        return "anull"  # atempo=1 no es neutro: adelanta el sonido ~20 ms
    partes, retraso = [], 0.0
    while v < 0.5:  # atempo no baja de 0.5 de una vez
        partes.append("atempo=0.5")
        retraso = (retraso + 0.02) / 0.5
        v /= 0.5
    retraso = (retraso + 0.02) / v  # cada atempo adelanta ~20 ms de lo que le entra: se devuelve con adelay
    return ",".join(partes + [f"atempo={v:.6g}", f"adelay={retraso * 1000:.1f}:all=1"])


_SIN_TRAMO = ("id", "transicion", "duracion_transicion")  # no cambian el tramo: se aplican al montar
# Todos los tramos con los mismos datos de color (una foto JPG viene en rango completo; un móvil, en BT.709 o sin
# decir): van seguidos en una sola entrada y, si cambian a mitad, ffmpeg reinicia el montaje y se pierden fotogramas
_COLOR = ("scale=out_range=tv:out_color_matrix=bt709,format=yuv420p,"
          "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709")


def _salida_tramo(final: bool) -> list:
    preset, crf = _CALIDAD[final][0]
    return ["-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le"]


def _tramo(c: dict, cache: Path, w: int, h: int, fps: int, ajuste: str, final: bool, avance,
           fondo: str = "#000000") -> Path:
    """El clip normalizado (H.264 + PCM en .mov), del caché si ya estaba hecho con estos mismos parámetros. Si su
    archivo falta, el color de fondo y silencio."""
    falta = c.get("falta", False)
    entrada = None if falta else _entrada(c, cache)
    n = _cuadros_tramo(c, fps)
    preset, crf = _CALIDAD[final][0]
    datos = {k: v for k, v in c.items() if k not in _SIN_TRAMO}
    destino = cache / (f"tramo-{'exp' if final else 'vista'}{h}-"
                       f"{_hash(VERSION, fondo if falta else _huella(entrada), datos, w, h, fps, ajuste, preset, crf)}"
                       ".mov")
    if destino.is_file():
        return destino
    muestras = n * _R // fps
    if falta:
        entradas, imagen = ["-f", "lavfi", "-i", f"color=c=0x{fondo[1:]}:s={w}x{h}:r={fps}"], "null"
    elif c["tipo"] == "video":
        # Sin -ss en 0: si la imagen empieza después que el sonido, saltar a 0 tiraría el sonido de antes. Los PTS sin
        # restar el primero: lo de antes de «desde» queda en negativo (ver _salto). Sin -t: con -noaccurate_seek cuenta
        # desde el fotograma clave y cortaba el final del clip; ffmpeg para igual al acabar los trim del grafo
        salto, m = _salto(entrada, c["desde"])
        entradas = [*salto, "-i", entrada]
        imagen = f"setpts=(PTS-{m:.6f}/TB)/{c['velocidad']},fps={fps}:start_time=0," \
                 f"{_aspecto(c, w, h, fps, ajuste, 1)},tpad=stop=-1:stop_mode=clone"
    else:
        entradas = ["-framerate", fps, "-i", entrada]
        imagen = _aspecto(c, w, h, fps, ajuste, n)
        if c["movimiento"] == "ninguno":  # la foto se filtra una vez y se repite
            imagen += f",loop=loop={n - 1}:size=1,setpts=N/({fps}*TB)"
    grafo = [f"[0:v]{imagen},fps={fps},trim=end_frame={n},{_COLOR}[v]"]
    sonido = (not falta and c["tipo"] == "video" and not c["silencio"] and c["volumen"]
              and _tiene_audio(str(entrada), _huella(entrada)))
    if sonido:
        # first_pts=0: lo de antes de «desde» (en negativo) se corta
        grafo.append(f"[0:a]asetpts=PTS-{m:.6f}/TB,aresample=async=1:first_pts=0,{_atempo(c['velocidad'])},"
                     f"volume={c['volumen']},{sonido}"
                     f"aformat=sample_fmts=s16:sample_rates={_R}:channel_layouts=stereo,apad,"
                     f"atrim=end_sample={muestras}[a]")
    else:
        entradas += ["-f", "lavfi", "-i", f"anullsrc=r={_R}:cl=stereo"]
        grafo.append(f"[1:a]atrim=end_sample={muestras}[a]")
    _a_disco(destino, lambda temporal: _correr(
        [*entradas, "-filter_complex", ";".join(grafo), *_salida_tramo(final), temporal.name], cache, n / fps, avance))
    return destino


def _paso(a: Path, fin_a: int, b: Path, solape: int, transicion: str, cache: Path, h: int, fps: int,
          final: bool) -> Path:
    """La transición ya hecha, como un tramo más de `solape` fotogramas: xfade de los últimos de `a` (que se ve hasta
    su fotograma fin_a) con los primeros de `b`, y acrossfade del sonido. Hecha aparte y no en el montaje: con
    muchos xfade dentro del montaje, ffmpeg decodificaba el video entero por adelantado (GB de memoria)."""
    preset, crf = _CALIDAD[final][0]
    destino = cache / (f"paso-{'exp' if final else 'vista'}{h}-"
                       f"{_hash(VERSION, a.name, fin_a, b.name, solape, transicion, fps, preset, crf)}.mov")
    if destino.is_file():
        return destino
    desde, muestras = fin_a - solape, solape * _R // fps
    grafo = (f"[0:v]trim=end_frame={solape},setpts=PTS-STARTPTS,fps={fps}:eof_action=pass[x];"
             f"[2:v]trim=end_frame={solape},setpts=PTS-STARTPTS,fps={fps}:eof_action=pass[y];"
             f"[x][y]xfade=transition={_XFADE[transicion]}:duration={solape / fps:.6f}:offset=0,{_COLOR}[v];"
             f"[1:a]atrim=start_sample={desde * _R // fps}:end_sample={fin_a * _R // fps},asetpts=PTS-STARTPTS[p];"
             f"[2:a]atrim=end_sample={muestras},asetpts=PTS-STARTPTS[q];"
             f"[p][q]acrossfade=ns={muestras}:c1=tri:c2=tri[a]")
    # La imagen de `a` con -ss (medio fotograma antes: sale justo el fotograma `desde`); su sonido, entero y cortado a
    # la muestra con atrim (decodificar PCM no cuesta nada)
    _a_disco(destino, lambda temporal: _correr(
        ["-ss", f"{max(0.0, (desde - 0.5) / fps):.6f}", "-i", a.name, "-i", a.name, "-i", b.name,
         "-filter_complex", grafo, *_salida_tramo(final), temporal.name], cache, solape / fps))
    return destino


# ---------- Capas y subtítulos ----------

_SIN_CAPA = ("id", "inicio", "duracion", "entrada", "salida")  # no cambian el dibujo: se aplican al montar


def _capa_png(capa: dict, carpeta: Path, cache: Path, w: int, h: int, escala: float) -> tuple | None:
    """La capa sola, en su sitio, en un PNG transparente del tamaño del video (todos iguales: van seguidos en una sola
    entrada de ffmpeg), pintada con la misma pieza que el editor de diseño. Devuelve (png, x, y, ancho, alto): la caja
    de la capa (girada y recortada al cuadro) en píxeles de salida, o None si no se ve."""
    diseno.asegurar_qt()
    escena = QGraphicsScene()  # sin fondo: lo que no es la capa queda transparente
    escena.addItem(diseno.ItemCapa(capa, carpeta))
    caja = escena.itemsBoundingRect()
    x0, y0 = max(0, math.floor(caja.left() * escala)), max(0, math.floor(caja.top() * escala))
    x1, y1 = min(w, math.ceil(caja.right() * escala)), min(h, math.ceil(caja.bottom() * escala))
    if x1 <= x0 or y1 <= y0:
        return None
    imagen_capa = Path(carpeta) / "imagenes" / capa["archivo"] if capa["tipo"] == "imagen" else None
    huella = _huella(imagen_capa) if imagen_capa and imagen_capa.is_file() else None
    datos = {k: v for k, v in capa.items() if k not in _SIN_CAPA}
    destino = cache / f"capa-{h}-{_hash(VERSION, datos, huella, w, h)}.png"
    if not destino.is_file():
        def hacer(temporal):
            imagen = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
            imagen.fill(Qt.transparent)
            p = QPainter(imagen)
            p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
            escena.render(p, QRectF(0, 0, w, h), QRectF(0, 0, w / escala, h / escala), Qt.IgnoreAspectRatio)
            p.end()
            if not imagen.save(str(temporal), "PNG"):
                raise RuntimeError(t("No se pudo preparar una capa del video."))
        _a_disco(destino, hacer)
    return destino, x0, y0, x1 - x0, y1 - y0


def _subtitulos(palabras: list, formato: str, cache: Path) -> Path:
    destino = cache / f"subs-{_hash(VERSION, palabras, formato)}.ass"  # solo hex: va tal cual dentro del filtro
    if not destino.is_file():
        _a_disco(destino, lambda temporal: video.subtitulos_ass(palabras, formato, temporal))
    return destino


def _fundido(tipo: str, st: float, d: float) -> list[str]:
    """El fade de una capa. Si la vista previa empieza a mitad del fundido, lo que queda (fade no admite st < 0)."""
    d += min(0.0, st)
    return [f"fade=t={tipo}:st={max(0.0, st):.6f}:d={d:.6f}:alpha=1"] if d > 0 else []


# ---------- Montaje ----------

def _render(p: dict, carpeta: Path, destino: Path | None, alto: int, final: bool, aviso,
            solo_audio: bool = False, desde: float = 0, segundos: float | None = None) -> Path:
    """Tramos + un ffmpeg que lo monta todo (ver el docstring del módulo). destino None: vista previa en cache/ (si ya
    existe la de este mismo proyecto, se devuelve tal cual). solo_audio: la mezcla en MP3 mono (para transcribir).
    desde/segundos: solo ese trozo de la línea de tiempo (el video sale empezando en 0)."""
    cache, fps = _cache(carpeta), p["fps"]
    w, h = _tamano(p["formato"], alto)
    marcos, entero = _marcos(p), round(edicion.duracion_total(p) * fps)
    if not entero:
        raise ValueError(t("El video está vacío: añade un clip, un audio o un texto."))
    d0 = min(round(desde * fps), entero - 1)  # lo que sale: los fotogramas [d0, d1) de la línea de tiempo
    d1 = entero if segundos is None else min(entero, d0 + max(1, round(segundos * fps)))
    total = d1 - d0
    que = t("Juntando el sonido") if solo_audio else t("Exportando") if final else t("Montando la vista previa")
    entradas, grafo, usados, listas = [], [], set(), {}
    sello = uuid.uuid4().hex[:8]  # las listas de este render: otro a la vez no las pisa

    # 1. Un tramo por clip y un «paso» por transición (ver _paso), en el orden en que se ven. El progreso de esta
    # parte va de 0 a 0.5, repartido por lo que dura cada clip.
    hechos, por_hacer, tramos = 0.0, sum(edicion.duracion_clip(c) for c in p["clips"]) or 1, []
    piezas = []  # (archivo, fotogramas que trae, desde, hasta): lo que se ve de cada tramo y paso, en orden
    for i, c in enumerate(p["clips"]):
        aviso(t("Preparando clip {n} de {total}…", n=i + 1, total=len(p["clips"])), 0.5 * hechos / por_hacer)
        base = 0.5 * hechos / por_hacer
        parte = 0.5 * edicion.duracion_clip(c) / por_hacer
        tramos.append(_tramo(c, cache, w, h, fps, p["ajuste"], final,
                             lambda f, base=base, parte=parte, i=i: aviso(
                                 f"{t('Preparando clip {n} de {total}…', n=i + 1, total=len(p['clips']))} {f:.0%}",
                                 base + parte * f),
                             p["fondo"]))
        if c["tipo"] == "video" and not c.get("falta"):
            usados.add(_proxy(_entrada(c, cache), cache).name)
        hechos += edicion.duracion_clip(c)
        largo = marcos[i][1] - marcos[i][0]
        entra = marcos[i - 1][1] - marcos[i][0] if i and p["clips"][i - 1]["transicion"] != "ninguna" else 0
        sale = marcos[i][1] - marcos[i + 1][0] if c["transicion"] != "ninguna" else 0  # el último nunca tiene
        if entra:
            piezas.append((_paso(tramos[-2], marcos[i - 1][1] - marcos[i - 1][0], tramos[-1], entra,
                                 p["clips"][i - 1]["transicion"], cache, h, fps, final), entra, 0, entra))
        if largo - entra - sale > 0:  # lo que se solapa ya va en los pasos; lo que el tramo trae de más, sin usar
            piezas.append((tramos[-1], _cuadros_tramo(c, fps), entra, largo - sale))
    usados.update(f.name for f in tramos)
    usados.update(f.name for f, *_ in piezas)
    for tipo in ("tramo", "paso"):
        _limpiar(cache, f"{tipo}-{'exp' if final else 'vista'}{h}-*.mov", usados)
    _limpiar(cache, "proxy-*.mp4", usados)

    # 2. La pista principal: todo seguido en UNA entrada (el concat de ffmpeg, que les pasa la lista MEDIOS: 300
    # entradas sueltas pasarían del largo de orden que deja Windows y abrirían 300 decodificadores), cortada en trozos
    # con split + trim (por número de fotograma y de muestra: exacto) y vuelta a pegar con un solo concat. Solo lo
    # que cae en [d0, d1): desde el archivo donde está d0, y lo de antes en él se salta con -ss (al µs: cae justo en
    # su fotograma y su muestra) en vez de decodificarlo. Ese va aparte: -ss en el concat saltaba al archivo siguiente.
    fila, trozos, inicio, pos, salto = [], [], 0, 0, 0
    for archivo, cuadros, a, b in piezas:
        a2, b2 = a + max(0, d0 - pos), b - max(0, pos + b - a - d1)
        pos += b - a
        if a2 < b2:
            salto = salto if fila else a2
            fila.append(archivo)
            trozos.append((inicio + a2 - salto, inicio + b2 - salto))
            inicio += cuadros
    v = a = None
    if trozos:
        if salto:
            entradas.append(["-ss", f"{salto / fps:.6f}", "-i", fila[0].name])
        if fila[bool(salto):]:
            listas[f"lista-{sello}-clips.txt"] = "".join(f"file {f.name}\n" for f in fila[bool(salto):])
            entradas.append(["-f", "concat", "-i", f"lista-{sello}-clips.txt"])
        fv, fa = "0:v", "0:a"
        if len(entradas) == 2:  # solo en una vista previa desde el cursor (con imagen)
            grafo.append("[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[todo][todoa]")
            fv, fa = "todo", "todoa"
        k = len(trozos)
        if not solo_audio:
            grafo.append(f"[{fv}]split={k}" + "".join(f"[s{j}]" for j in range(k)))
            # setpts: concat quiere cada trozo empezando en 0. Después, los tiempos por número de fotograma: concat da
            # duración 0 a un trozo de un solo fotograma y el siguiente se le montaba encima (el fps de después tiraba
            # uno). fps (eof_action=pass: si no, tira el último fotograma): concat pierde la velocidad de fotogramas
            grafo += [f"[s{j}]trim=start_frame={d}:end_frame={e},setpts=PTS-STARTPTS[v{j}]"
                      for j, (d, e) in enumerate(trozos)]
            grafo.append("".join(f"[v{j}]" for j in range(k)) +
                         f"concat=n={k}:v=1:a=0,setpts=N/({fps}*TB),fps={fps}:eof_action=pass[pv]")
        grafo.append(f"[{fa}]asplit={k}" + "".join(f"[t{j}]" for j in range(k)))
        grafo += [f"[t{j}]atrim=start_sample={d * _R // fps}:end_sample={e * _R // fps},asetpts=PTS-STARTPTS[a{j}]"
                  for j, (d, e) in enumerate(trozos)]
        grafo.append("".join(f"[a{j}]" for j in range(k)) + f"concat=n={k}:v=0:a=1[pa]")
        v, a = "pv", "pa"
    fondo = "0x" + p["fondo"][1:]
    if not trozos:  # solo capas o audios (o ya después del último clip): el fondo de color
        entradas += [["-f", "lavfi", "-i", f"color=c={fondo}:s={w}x{h}:r={fps}:d={total / fps + 1:.6f}"],
                     ["-f", "lavfi", "-i", f"anullsrc=r={_R}:cl=stereo"]]
        v, a = f"{len(entradas) - 2}:v", f"{len(entradas) - 1}:a"
    # Donde ya no hay clips pero sigue una capa o un audio, se ve el fondo (como CapCut)
    if not solo_audio:
        relleno = total - sum(e - d for d, e in trozos)
        grafo.append(f"[{v}]tpad=stop={max(0, relleno)}:stop_mode=add:color={fondo},trim=end_frame={total},"
                     "setpts=PTS-STARTPTS[o]")
    grafo.append(f"[{a}]apad,atrim=end_sample={total * _R // fps}[pista]")

    # 3. Capas: sus PNG, seguidos en otra entrada concat; cada una se recorta a su caja, se repite en memoria (loop)
    # desde su inicio y se pone encima con overlay
    visibles, escala = [], h / video.FORMATOS[p["formato"]][1]
    for capa in [] if solo_audio else p["capas"]:
        ini, fin = round(capa["inicio"] * fps), min(entero, round((capa["inicio"] + capa["duracion"]) * fps))
        hecho = _capa_png(capa, carpeta, cache, w, h, escala) if fin > ini else None
        if hecho:
            usados.add(hecho[0].name)
            if fin > d0 and ini < d1:
                visibles.append((capa, ini, fin, *hecho))
    if visibles:
        listas[f"lista-{sello}-capas.txt"] = "".join(f"file {png.name}\n" for _, _, _, png, *_ in visibles)
        entradas.append(["-f", "concat", "-i", f"lista-{sello}-capas.txt"])
        grafo.append(f"[{len(entradas) - 1}:v]split={len(visibles)}" + "".join(f"[p{j}]" for j in range(len(visibles))))
    ultimo = "o"
    for j, (capa, ini, fin, png, x, y, cw, ch) in enumerate(visibles):
        dura = min(_ANIMACION, (fin - ini) / fps / 2)
        t0, t1 = (ini - d0) / fps, (fin - d0) / fps  # en una ventana pueden caer antes de 0: la animación sigue bien
        ve, deja = max(ini, d0) - d0, min(fin, d1) - d0
        cadena = [f"[p{j}]trim=start_frame={j}:end_frame={j + 1},crop={cw}:{ch}:{x}:{y},format=yuva420p,"
                  f"loop=loop=-1:size=1,trim=end_frame={deja - ve},setpts=(N+{ve})/({fps}*TB)"]
        px, py = str(x), str(y)
        if capa["entrada"] == "fundido":
            cadena += _fundido("in", t0, dura)
        elif capa["entrada"] == "aparecer":
            crece = f"min(1,0.5+0.5*(t-{t0:.6f})/{dura:.6f})"
            cadena += [f"scale=w='max(2,trunc(iw*{crece}/2)*2)':h='max(2,trunc(ih*{crece}/2)*2)':eval=frame",
                       *_fundido("in", t0, dura / 2)]
            px, py = f"'{x + cw / 2}-overlay_w/2'", f"'{y + ch / 2}-overlay_h/2'"
        elif capa["entrada"] == "deslizar":  # desde fuera por la izquierda, frenando al llegar
            px = f"'{x}-{x + cw}*pow(1-min(1,max(0,(t-{t0:.6f})/{dura:.6f})),2)'"
        if capa["salida"] == "fundido":
            cadena += _fundido("out", t1 - dura, dura)
        grafo.append(",".join(cadena) + f"[c{j}]")
        grafo.append(f"[{ultimo}][c{j}]overlay=x={px}:y={py}:eof_action=pass[o{j}]")
        ultimo = f"o{j}"
    if not solo_audio:
        corrido = d0 / fps
        palabras = [{**pal, "inicio": max(0, pal["inicio"] - corrido), "fin": pal["fin"] - corrido}
                    for pal in p["subtitulos"]["palabras"] if pal["fin"] > corrido]
        if p["subtitulos"]["activos"] and palabras:
            grafo.append(f"[{ultimo}]subtitles={_subtitulos(palabras, p['formato'], cache).name}[s]")
            ultimo = "s"
        grafo.append(f"[{ultimo}]format=yuv420p[vfin]")
        _limpiar(cache, f"capa-{h}-*.png", usados)

    # 4. Audios: cada uno a su sitio de la línea de tiempo, con su volumen y fundidos, sumados sin bajar el volumen
    mezcla, huellas, s0 = ["pista"], [], d0 * _R // fps  # s0: la muestra donde empieza lo que sale
    for j, au in enumerate(p["audios"]):
        if au.get("falta"):  # su archivo no está: no suena (la interfaz lo marca para volver a enlazarlo)
            continue
        real = seguro.archivo_medio(au["archivo"], seguro.AUDIOS, t("Audio {n}", n=j + 1))
        huellas.append(_huella(real))
        sonido = _tiene_audio(str(real), huellas[-1])
        corte = max(0, s0 - round(au["inicio"] * _R)) / _R  # lo que ya sonó antes de la ventana
        largo = au["hasta"] - au["desde"] - corte
        if not sonido or largo <= 0:
            continue
        entradas.append(["-ss", f"{au['desde'] + corte:.6f}", "-t", f"{largo:.6f}", "-i", real])
        cadena = [f"[{len(entradas) - 1}:a]asetpts=PTS-STARTPTS,{sonido}aformat=sample_rates={_R}:"
                  f"channel_layouts=stereo,volume={au['volumen']}"]
        if au["entrada"] > corte:
            cadena.append(f"afade=t=in:d={au['entrada'] - corte}")
        if au["salida"]:
            cadena.append(f"afade=t=out:st={max(0.0, largo - au['salida']):.6f}:d={au['salida']}")
        cadena.append(f"adelay={max(0, round(au['inicio'] * _R) - s0)}S:all=1")
        grafo.append(",".join(cadena) + f"[m{j}]")
        mezcla.append(f"m{j}")
    if len(mezcla) > 1:
        grafo.append("".join(f"[{m}]" for m in mezcla) + f"amix=inputs={len(mezcla)}:normalize=0:duration=first[afin]")
    else:
        grafo.append("[pista]anull[afin]")

    args = [x for e in entradas for x in e]
    if destino is None:
        clave = _hash(VERSION, str(args).replace(sello, ""), grafo, list(listas.values()), huellas, w, h)
        destino = cache / f"vista-{clave}.mp4"
        _limpiar(cache, "vista-*.mp4", {destino.name})
        if destino.is_file():
            aviso(t("Vista previa lista."), 1.0)
            return destino
    # El grafo va en un archivo (-/filter_complex: el -filter_complex_script de antes, ya obsoleto en ffmpeg 7.1):
    # Windows no deja órdenes de más de 32 000 caracteres
    script = cache / f"grafo-{sello}.txt"
    script.write_text(";\n".join(grafo), encoding="utf-8")
    for nombre, texto in listas.items():
        (cache / nombre).write_text(texto, encoding="utf-8")
    if solo_audio:
        salida = ["-map", "[afin]", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k"]
    else:
        (preset, crf), sonido = _CALIDAD[final][1], "192k" if final else "128k"
        # -r: sin él, a 25 y 60 fps el MP4 marcaba el último fotograma como descartado (se perdía)
        salida = ["-map", "[vfin]", "-map", "[afin]", "-r", fps, "-c:v", "libx264", "-preset", preset, "-crf", crf,
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", sonido, "-movflags", "+faststart",
                  *([] if final else ["-g", fps])]  # vista previa: un fotograma clave por segundo, para saltar rápido
    aviso(f"{que}…", 0.5)
    try:
        _a_disco(destino, lambda temporal: _correr(
            [*args, "-/filter_complex", script.name, *salida, temporal.resolve()], cache, total / fps,
            lambda f: aviso(f"{que}… {f:.0%}", 0.5 + 0.5 * f)))
    finally:
        for nombre in (script.name, *listas):
            (cache / nombre).unlink(missing_ok=True)
    aviso(t("¡Listo!"), 1.0)
    return destino


# ---------- Lo que usa la interfaz ----------

def fotograma(proyecto: dict, carpeta: Path, momento: float, alto_max: int = 640) -> QImage:
    """El fondo del video en `momento` (el clip bajo él con su encaje, movimiento, filtro y ajustes; en una transición,
    el clip que entra) SIN capas ni subtítulos: los pinta la interfaz encima. Un solo fotograma con ffmpeg, en caché."""
    p = edicion.validar(proyecto)
    momento = diseno._campo(edicion._num(0, edicion.MAX_DURACION, 6), momento, t("El momento del video"))
    alto_max = int(diseno._campo(edicion._num(16, 4320, 0), alto_max, t("El alto de la imagen")))
    fps, (w, h) = p["fps"], _tamano(p["formato"], alto_max)
    # El fotograma que se ve, como en el video montado (validar redondea `momento` a 6 decimales: 10/30 sería el 9)
    cuadro = int(momento * fps + 1e-3)
    for c, (a, b) in reversed(list(zip(p["clips"], _marcos(p)))):
        if a <= cuadro < b:
            if c.get("falta"):  # su archivo no está: el fondo, como en el video montado
                break
            cache = _cache(carpeta)
            entrada = _entrada(c, cache)
            proxy = _proxy(entrada, cache) if c["tipo"] == "video" and h <= _PROXY else None
            entrada = proxy if proxy and proxy.is_file() else entrada
            datos = json.dumps({k: v for k, v in c.items() if k not in _SIN_TRAMO}, sort_keys=True)
            imagen = _cuadro(str(entrada), _huella(entrada), datos, p["ajuste"], fps, w, h, cuadro - a)
            return imagen if imagen is not None else _liso(w, h, p["fondo"])
    return _liso(w, h, p["fondo"])


@lru_cache(maxsize=32)
def _cuadro(entrada: str, _huella_archivo: tuple, datos: str, ajuste: str, fps: int, w: int, h: int,
            j: int) -> QImage | None:
    """El fotograma j del clip (de 0), con la misma cadena que su tramo. None si el archivo se acaba antes."""
    c = json.loads(datos)
    if c["tipo"] == "video":
        # La misma cadena que el tramo, saltando a j: fps:start_time=0 da el que se ve ahí aunque empezara mucho antes.
        # Los 2e-4: que los empates de redondeo caigan como en el tramo
        salto, m = _salto(entrada, max(0.0, c["desde"] + (j / fps - 2e-4) * c["velocidad"]))
        args = [*salto, "-i", entrada, "-vf", f"setpts=(PTS-{m:.6f}/TB)/{c['velocidad']},fps={fps}:start_time=0,"
                f"{_aspecto(c, w, h, fps, ajuste, 1)}", "-frames:v", "1"]
    else:
        args = ["-i", entrada, "-vf", _aspecto(c, w, h, fps, ajuste, 1, j), "-frames:v", "1"]
    r = subprocess.run([video.FFMPEG, "-hide_banner", "-loglevel", "error",
                        *video.solo_medios([*args, "-an", "-sn", "-f", "rawvideo", "-pix_fmt", "bgr0", "-"])],
                       capture_output=True)
    if r.returncode:
        raise RuntimeError(t("ffmpeg falló: {error}", error=r.stderr.decode("utf-8", "replace").strip()[:800]))
    if len(r.stdout) < w * h * 4:
        return None
    return QImage(r.stdout[:w * h * 4], w, h, 4 * w, QImage.Format_RGB32).copy()  # copy: los bytes no viven más


def miniatura(clip: dict, carpeta: Path, alto: int = 72) -> QImage:
    """Miniatura del clip para la línea de tiempo (el original, sin filtros), guardada en cache/. De paso encarga el
    proxy de un video más grande que la vista previa (ver _proxy): se hace aparte y fotograma() lo usa al estar."""
    c = edicion.validar({"clips": [clip]})["clips"][0]
    alto = int(diseno._campo(edicion._num(8, 720, 0), alto, t("El alto de la miniatura")))
    cache = _cache(carpeta)
    entrada = _entrada(c, cache)
    if c["tipo"] == "video" and not _proxy(entrada, cache).is_file():
        tam = re.search(r"Stream #\S+.*: Video: .*?, (\d{2,5})x(\d{2,5})", _cabecera(str(entrada), _huella(entrada)))
        if tam and min(map(int, tam.groups())) > _PROXY:
            _proxies.put((entrada, _proxy(entrada, cache)))
    # A una foto no se le pone -ss: aunque sea 0, ffmpeg tira su único fotograma
    salto, m = _salto(entrada, c["desde"] + min(1.0, (c["hasta"] - c["desde"]) / 2)) if c["tipo"] == "video" else \
        ([], 0)
    destino = cache / f"mini-{_hash(VERSION, _huella(entrada), salto, alto)}.png"
    if not destino.is_file():
        _a_disco(destino, lambda temporal: video.ffmpeg(
            *salto, "-i", entrada, "-frames:v", "1", "-vf", f"setpts=PTS-{m:.6f}/TB,trim=start=0,scale=-2:{alto}",
            temporal.name, cwd=cache))
    return QImage(str(destino), "PNG")  # «PNG» a la fuerza: un archivo cambiado en cache/ no se abre como SVG


def forma_de_onda(archivo: str, carpeta: Path, ancho: int, alto: int) -> QImage:
    """La forma de onda de todo el archivo (blanca sobre transparente), guardada en cache/. Vacía si no tiene sonido."""
    ancho = int(diseno._campo(edicion._num(1, 20000, 0), ancho, t("El ancho de la forma de onda")))
    alto = int(diseno._campo(edicion._num(1, 1000, 0), alto, t("El alto de la forma de onda")))
    real = seguro.archivo_medio(archivo, seguro.AUDIOS | seguro.VIDEOS, t("audio"))
    cache = _cache(carpeta)
    destino = cache / f"onda-{_hash(VERSION, _huella(real), ancho, alto)}.png"
    if not destino.is_file():
        if not _tiene_audio(str(real), _huella(real)):
            vacia = QImage(ancho, alto, QImage.Format_ARGB32)
            vacia.fill(Qt.transparent)
            return vacia
        _a_disco(destino, lambda temporal: video.ffmpeg(
            "-i", real, "-filter_complex",
            f"[0:a:0]aformat=channel_layouts=mono,showwavespic=s={ancho}x{alto}:colors=0xFFFFFF:scale=sqrt",
            "-frames:v", "1", temporal.name, cwd=cache))
    return QImage(str(destino), "PNG")


def vista_previa(proyecto: dict, carpeta: Path, aviso=lambda t, f: None, desde: float = 0,
                 segundos: float | None = None) -> Path:
    """El video en pequeño (640 de alto como mucho, rápido) con capas, audios y subtítulos, para reproducirlo.
    Reutiliza los tramos ya hechos y, si nada cambió, la vista previa anterior. desde/segundos: solo ese trozo de la
    línea de tiempo (el archivo empieza en 0 = `desde`): con el cursor lejos en un video largo, ▶ no monta todo."""
    desde = diseno._campo(edicion._num(0, edicion.MAX_DURACION, 6), desde, t("El inicio de la vista previa"))
    if segundos is not None:
        segundos = diseno._campo(edicion._num(0.01, edicion.MAX_DURACION, 6), segundos,
                                 t("Lo que dura la vista previa"))
    return _render(edicion.validar(proyecto), carpeta, None, 640, False, aviso, desde=desde, segundos=segundos)


def exportar(proyecto: dict, carpeta: Path, destino: Path, calidad: str = "1080p", aviso=lambda t, f: None) -> Path:
    """MP4 H.264 + AAC listo para subir: «1080p» es el tamaño de video.FORMATOS y «720p», sus 2/3."""
    p = edicion.validar(proyecto)
    if calidad not in ("720p", "1080p"):
        raise ValueError(t("Calidad desconocida ({calidad!r:.20}); valen 720p y 1080p.", calidad=calidad))
    destino = diseno._local(destino)
    if destino.suffix.lower() != ".mp4":
        destino = destino.with_name(f"{destino.name}.mp4")
    destino.parent.mkdir(parents=True, exist_ok=True)
    alto = video.FORMATOS[p["formato"]][1]
    alto = alto if calidad == "1080p" else alto * 2 // 3
    # Los tramos casi sin pérdida ocupan ~3,6 MB por segundo a 1080p: mejor avisar ya que fallar al cabo de mucho rato
    hace_falta = sum(map(edicion.duracion_clip, p["clips"])) * (4 if calidad == "1080p" else 2) * 1.2 * 1024 ** 2
    if shutil.disk_usage(_cache(carpeta)).free < hace_falta:
        cuanto = f"{hace_falta / 1024 ** 3:.1f} GB" if hace_falta >= 1024 ** 3 else f"{hace_falta / 1024 ** 2:.0f} MB"
        raise ValueError(t("Hacen falta unos {cuanto} libres en el disco para exportar: libera espacio y vuelve a "
                           "intentarlo.", cuanto=cuanto))
    hecho = _render(p, carpeta, destino, alto, True, aviso)
    # Los tramos de exportar van casi sin pérdida: una hora de video serían decenas de GB en cache/
    _limpiar(_cache(carpeta), f"*-exp{_tamano(p['formato'], alto)[1]}-*.mov", set())
    return hecho


def cancelar() -> None:
    """Para todo lo que hace ffmpeg (al cerrar la app a mitad de algo): lo que estaba en marcha falla sin dejar restos
    y no empieza nada más."""
    _parar_proxy()  # marca _cerrando antes de mirar _procesos: ver _correr
    for proceso in list(_procesos):
        proceso.kill()


def subtitulos_automaticos(proyecto: dict, carpeta: Path, aviso=lambda t, f: None) -> list[dict]:
    """Mezcla el sonido de la línea de tiempo, lo transcribe (ia.transcribir) y devuelve las palabras en tiempos de la
    línea de tiempo, listas para proyecto["subtitulos"]["palabras"]."""
    from . import claves, ia
    p = edicion.validar(proyecto)
    audio = _cache(carpeta) / f"audio-{uuid.uuid4().hex[:8]}.mp3"
    _render(p, carpeta, audio, 640, False, lambda t, f: aviso(t, 0.3 * f), solo_audio=True)
    donde = t("Transcribiendo en la nube…") if (claves.para("transcripcion") or {}).get("clave") else \
        t("Transcribiendo en tu PC (lento; con Groq gratis es mucho más rápido)…")
    aviso(donde, 0.3)
    try:
        palabras = ia.transcribir(audio, progreso=lambda f: aviso(f"{donde} {f:.0%}", 0.3 + 0.7 * f))
    finally:
        audio.unlink(missing_ok=True)
        audio.with_name(audio.stem + "_ligero.mp3").unlink(missing_ok=True)  # el que hace transcribir para la nube
    total, limpias = edicion.duracion_total(p), []
    for w in palabras[:edicion.MAX_PALABRAS]:
        texto = str(w.get("palabra", "")).strip()[:100]
        try:
            inicio = min(max(float(w["inicio"]), 0.0), total)
            fin = min(max(float(w["fin"]), inicio), total)
        except (KeyError, TypeError, ValueError):
            continue
        if texto and math.isfinite(inicio) and math.isfinite(fin):
            limpias.append({"palabra": texto, "inicio": round(inicio, 3), "fin": round(fin, 3)})
    aviso(t("¡Listo!"), 1.0)
    return limpias


def voz_ia(texto: str, voz: str, carpeta: Path) -> Path:
    """Narra el texto con una voz de desde_prompt.voces() (su nombre o su id) a un MP3 en <carpeta>/voces/, listo para
    edicion.anadir_medio."""
    from . import desde_prompt
    texto = diseno._campo(diseno._texto(5000), texto, t("El texto de la voz")).strip()  # ElevenLabs cobra por letra
    if not texto:
        raise ValueError(t("Escribe lo que tiene que decir la voz."))
    voces = desde_prompt.voces()
    voz = voces.get(diseno._campo(diseno._texto(200), voz, t("La voz")), voz)
    # Solo voces de la lista: el id de ElevenLabs va dentro de la dirección de su API
    if voz not in voces.values():
        raise ValueError(t("Esa voz no existe: elige una de la lista."))
    destino = diseno._local(carpeta) / "voces" / f"voz-{uuid.uuid4().hex[:8]}.mp3"
    destino.parent.mkdir(parents=True, exist_ok=True)
    desde_prompt.narrar(texto, voz, destino)
    if not destino.is_file() or not destino.stat().st_size:
        destino.unlink(missing_ok=True)
        raise RuntimeError(t("No se pudo crear la voz: inténtalo de nuevo."))
    return destino
