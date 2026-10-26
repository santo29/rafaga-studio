"""Pruebas del render del editor de video (motor/render_edicion.py), sin red ni claves:
python -m pruebas.render_edicion"""
import os
import re
import subprocess
import tempfile
import threading
import time
import types
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from motor import claves, desde_prompt, diseno, edicion, ia, video  # noqa: E402
from motor import render_edicion as render  # noqa: E402

diseno.asegurar_qt()


def falla(funcion, *args, **kw):
    """Lo hostil se rechaza con un ValueError claro: ni revienta con otro error ni pasa."""
    try:
        funcion(*args, **kw)
    except ValueError:
        return
    raise AssertionError(f"debió rechazar {args!r:.300}")


def ffmpeg_salida(*args) -> subprocess.CompletedProcess:
    return subprocess.run([video.FFMPEG, "-hide_banner", *video.solo_medios([str(a) for a in args])],
                          capture_output=True)


def info(archivo) -> tuple[int, int, int]:
    """(ancho, alto, fotogramas) del video, contando los fotogramas sin decodificar."""
    texto = ffmpeg_salida("-i", archivo, "-map", "0:v", "-c", "copy", "-f", "null", "-").stderr.decode("utf-8",
                                                                                                     "replace")
    w, h = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", texto).groups()
    return int(w), int(h), int(re.findall(r"frame=\s*(\d+)", texto)[-1])


def cuadros(archivo) -> int:
    """Los fotogramas que salen al decodificarlo (sin los que el MP4 marca como descartados)."""
    texto = ffmpeg_salida("-i", archivo, "-map", "0:v", "-f", "null", "-").stderr.decode("utf-8", "replace")
    return int(re.findall(r"frame=\s*(\d+)", texto)[-1])


def blanco_y_pitido(archivo) -> tuple[int, float]:
    """El primer fotograma blanco y el segundo en que empieza el pitido (de marca.mp4 y sus variantes)."""
    datos = ffmpeg_salida("-i", archivo, "-vf", "scale=32:32", "-f", "rawvideo", "-pix_fmt", "gray", "-").stdout
    brillo = np.frombuffer(datos, np.uint8).reshape(-1, 32 * 32).mean(axis=1)
    return int(np.argmax(brillo > 200)), float(np.argmax(np.abs(sonido(archivo)) > 0.3) / 48000)


def sonido(archivo) -> np.ndarray:
    """Las muestras mono a 48 kHz."""
    return np.frombuffer(ffmpeg_salida("-i", archivo, "-map", "0:a", "-ac", "1", "-ar", "48000", "-f", "f32le",
                                       "-").stdout, np.float32)


def cuadro(archivo, n: int) -> np.ndarray:
    """El fotograma n (exacto, contando desde 0) como RGB."""
    w, h, _ = info(archivo)
    datos = ffmpeg_salida("-i", archivo, "-vf", f"select=eq(n\\,{n})", "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-").stdout
    return np.frombuffer(datos, np.uint8).reshape(h, w, 3).astype(int)


def de_qimage(q: QImage) -> np.ndarray:
    q = q.convertToFormat(QImage.Format_RGB888)
    filas = np.frombuffer(q.constBits(), np.uint8, q.sizeInBytes()).reshape(q.height(), q.bytesPerLine())
    return filas[:, :q.width() * 3].reshape(q.height(), q.width(), 3).astype(int)


def reducir(imagen: np.ndarray, w: int, h: int) -> np.ndarray:
    """Media por bloques: compara dos tamaños sin depender de cómo escala cada uno."""
    fy, fx = imagen.shape[0] // h, imagen.shape[1] // w
    return imagen[:h * fy, :w * fx].reshape(h, fy, w, fx, 3).mean(axis=(1, 3))


def rojo(imagen: np.ndarray) -> np.ndarray:
    return (imagen[..., 0] > 150) & (imagen[..., 1] < 90) & (imagen[..., 2] < 90)


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    edicion.CARPETA = d / "ediciones"  # nada de tocar datos/ de verdad
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"  # ni se leen ni se tocan las claves
    carpeta = edicion.nueva_carpeta("pruebas")

    # ---------- Medios de prueba (ffmpeg lavfi, 1–3 s, 360p) ----------
    def hacer(nombre, *args):
        video.ffmpeg(*args, d / nombre)
        return d / nombre
    h264 = ("-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest")
    prueba = hacer("prueba.mp4", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3", "-f", "lavfi", "-i",
                   "sine=frequency=440:duration=3", *h264)
    # Negro hasta el segundo 1 y blanco después; el pitido empieza a la vez (exacto a la muestra)
    marca = hacer("marca.mp4", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=2,drawbox=c=white:t=fill:"
                  "enable='gte(t,1)'", "-f", "lavfi", "-i",
                  "aevalsrc='if(gte(t,1),0.8*sin(2*PI*1000*t),0)':s=48000:d=2", *h264)
    musica = hacer("musica.wav", "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*660*t)':s=48000:d=3")
    foto = hacer("foto.png", "-f", "lavfi", "-i", "testsrc2=s=480x360", "-frames:v", "1")
    hacer("roja.png", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1")
    (carpeta / "imagenes" / "roja.png").write_bytes((d / "roja.png").read_bytes())

    def proyecto(*medios, **datos):
        p = edicion.nuevo()
        for m in medios:
            p = edicion.anadir_medio(p, str(m))
        return {**p, **datos}

    def clips(p, *cambios):
        for c, cambio in zip(p["clips"], cambios):
            c.update(cambio)
        return edicion.validar(p)

    # ---------- Duración exacta: sin y con transiciones, con velocidades y fotos ----------
    p = clips(proyecto(prueba, prueba, foto), {"hasta": 2}, {"desde": 0.5, "hasta": 2.5, "velocidad": 2},
              {"hasta": 1.5})
    t0 = time.perf_counter()
    avisos = []
    vista = render.vista_previa(p, carpeta, lambda t, f: avisos.append(f))
    tiempo_vista = time.perf_counter() - t0
    assert info(vista) == (360, 640, 135), info(vista)  # 2 + 1 + 1.5 = 4.5 s a 30 fps
    assert abs(len(sonido(vista)) / 48000 - 4.5) < 0.03, len(sonido(vista)) / 48000
    assert avisos == sorted(avisos) and avisos[-1] == 1.0, avisos  # el progreso solo avanza
    p = clips(p, {"transicion": "fundido", "duracion_transicion": 0.5},
              {"transicion": "zoom", "duracion_transicion": 0.3})
    vista = render.vista_previa(p, carpeta)
    assert info(vista)[2] == 111, info(vista)  # 4.5 - 0.5 - 0.3 = 3.7 s
    assert abs(len(sonido(vista)) / 48000 - 3.7) < 0.03
    # Exportar: 720p (2/3 de 1080×1920), a 25 fps y con un clip a cámara lenta
    p = clips(proyecto(prueba, foto, fps=25), {"hasta": 1, "velocidad": 0.5, "transicion": "circulo",
                                               "duracion_transicion": 0.4}, {"hasta": 1})
    avisos = []
    t0 = time.perf_counter()
    hecho = render.exportar(p, carpeta, d / "exportado", "720p", lambda t, f: avisos.append((t, f)))
    tiempo_export = time.perf_counter() - t0
    assert hecho == d / "exportado.mp4" and info(hecho) == (720, 1280, 65), info(hecho)  # 2 + 1 - 0.4 = 2.6 s
    assert cuadros(hecho) == 65, cuadros(hecho)  # a 25 y 60 fps el MP4 marcaba el último como descartado
    assert cuadros(render.vista_previa(clips(proyecto(prueba, foto, fps=60), {"hasta": 1.37, "transicion": "zoom",
                                                                            "duracion_transicion": 0.37}, {"hasta": 1}),
                                       carpeta)) == 120
    assert abs(len(sonido(hecho)) / 48000 - 2.6) < 0.03
    assert any("Exportando… " in t for t, _ in avisos), avisos  # progreso real de -progress
    # Ni restos a medias ni los tramos de exportar (casi sin pérdida: pesan mucho)
    assert not [f for patron in ("tmp-*", "grafo-*", "lista-*", "*-exp*.mov")
                for f in (carpeta / "cache").glob(patron)]

    # ---------- A/V sincronizados tras una transición y a velocidad 2 ----------
    # El clip 2 entra en 1.1 s (transición de 0.4); su marca (segundo 1 del archivo, a velocidad 2) cae en 1.6 s
    p = clips(proyecto(prueba, marca), {"hasta": 1.5, "transicion": "fundido", "duracion_transicion": 0.4},
              {"velocidad": 2})
    vista = render.vista_previa(p, carpeta)
    blanco = next(n for n in range(45, 60) if cuadro(vista, n).mean() > 128)
    muestras = sonido(vista)
    pitido = (np.argmax(np.abs(muestras[int(1.5 * 48000):]) > 0.2) + int(1.5 * 48000)) / 48000
    assert blanco == 48, blanco
    assert abs(pitido - 1.6) < 0.03 and abs(pitido - blanco / 30) < 0.04, (pitido, blanco)

    # ---------- Exacto en los casos difíciles ----------
    gris = hacer("gris.mp4", "-f", "lavfi", "-i", "color=c=gray:s=640x360:r=30:d=1", *h264[:6])  # sin sonido
    # Clips cortos entre dos transiciones (fotos de 0.5 s con fundidos): concat perdía los trozos de un fotograma
    p = clips(proyecto(*[gris] * 8, marca),
              *[{"hasta": 0.47, "transicion": "fundido", "duracion_transicion": 0.21}] * 8)
    vista = render.vista_previa(p, carpeta)
    blanco, pitido = blanco_y_pitido(vista)
    assert cuadros(vista) == round(edicion.duracion_total(p) * 30) == 122 and blanco == 92, (cuadros(vista), blanco)
    assert abs(pitido - blanco / 30) < 0.005, (pitido, blanco)
    # A 0.25x desde un punto que cae a mitad de un fotograma: la imagen se adelantaba 2 fotogramas y el sonido
    # (atempo) unos 90 ms
    blanco, pitido = blanco_y_pitido(render.vista_previa(clips(proyecto(gris, marca), {}, {
        "desde": 0.75, "hasta": 1.25, "velocidad": 0.25}), carpeta))
    # 1 s de gris + 0.25 s a 0.25x. El sonido, a un fotograma como mucho: estirado 4 veces, el pitido entra suave
    assert blanco == 60 and abs(pitido - 2) < 0.04, (blanco, pitido)
    # Imagen que empieza 0.3 s después que el sonido (grabaciones de pantalla, .ts), con un pitido en 0.1 s: -ss 0
    # tiraba ese sonido y STARTPTS adelantaba la imagen
    tarde = d / "tarde.mp4"
    video.ffmpeg("-itsoffset", "0.3", "-i", marca, "-f", "lavfi", "-i", "aevalsrc='0.8*sin(2*PI*1000*t)*between(t,0.1,"
                 "0.2)':s=48000:d=2", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", tarde)
    blanco, pitido = blanco_y_pitido(render.vista_previa(clips(proyecto(tarde), {"hasta": 2}), carpeta))
    assert blanco == 39 and abs(pitido - 0.1) < 0.005, (blanco, pitido)  # como en el original: 1.3 s y 0.1 s
    # A velocidad 1, sonido mono de 44.1 kHz: atempo=1 lo adelantaba 22 ms y el mono sonaba 3 dB más bajo
    marca44 = hacer("marca44.mp4", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=2,drawbox=c=white:t=fill:"
                    "enable='gte(t,1)'", "-f", "lavfi", "-i",
                    "aevalsrc='if(gte(t,1),0.8*sin(2*PI*1000*t),0)':s=44100:d=2:c=mono", *h264)
    vista = render.vista_previa(clips(proyecto(marca44, fps=25), {}), carpeta)
    blanco, pitido = blanco_y_pitido(vista)
    assert blanco == 25 and abs(pitido - 1) < 0.005, (blanco, pitido)
    lados = np.frombuffer(ffmpeg_salida("-i", vista, "-map", "0:a", "-f", "f32le", "-").stdout, np.float32)
    assert np.abs(np.abs(lados.reshape(-1, 2)).max(axis=0) - 0.8).max() < 0.05, np.abs(lados.reshape(-1, 2)).max(0)

    # ---------- Cálido y Frío se notan ----------
    hacer("gris.png", "-f", "lavfi", "-i", "color=c=0x808080:s=320x320", "-frames:v", "1")
    tinte = {}
    for filtro in ("ninguno", "calido", "frio"):
        f = de_qimage(render.fotograma(clips(proyecto(d / "gris.png"), {"filtro": filtro}), carpeta, 0.5))
        tinte[filtro] = f[..., 0].mean() - f[..., 2].mean()  # rojo menos azul
    assert tinte["calido"] > tinte["ninguno"] + 15 and tinte["frio"] < tinte["ninguno"] - 15, tinte

    # ---------- Filtros, ajustes, efectos y transiciones nuevos (a 160 de alto: rápido) ----------
    carpeta_fx = edicion.nueva_carpeta("efectos")  # aparte: lo de abajo cuenta los tramos de `carpeta`

    def montado(p, alto=160):
        """(sus fotogramas en RGB, (ancho, alto, fotogramas)) del video montado por el camino de la vista previa."""
        hecho = render._render(edicion.validar(p), carpeta_fx, d / "montado.mp4", alto, False, lambda t, f: None)
        w, h, n = info(hecho)
        datos = ffmpeg_salida("-i", hecho, "-f", "rawvideo", "-pix_fmt", "rgb24", "-").stdout
        return np.frombuffer(datos, np.uint8).reshape(-1, h, w, 3).astype(int), (w, h, n)

    def sin_cambiar(p, **campos):
        return edicion.validar({**p, "clips": [{**c, **campos} for c in p["clips"]]})
    assert set(edicion.FILTROS) == {"ninguno", *render._FILTROS}
    assert set(edicion.TRANSICIONES) == {"ninguna", *render._XFADE}
    # Cada filtro nuevo y cada ajuste (temperatura, viñeta, nitidez) se nota y no cambia tamaño ni fotogramas
    cambios = [{"filtro": f} for f in ("cine", "caribe", "noir", "dorado", "neon", "pastel", "retro", "nocturno")]
    cambios += [{"temperatura": 80}, {"temperatura": -80}, {"vineta": 100}, {"nitidez": 100}]
    p = clips(proyecto(*[foto] * len(cambios)), *[{"hasta": 1, **cambio} for cambio in cambios])
    con, tam = montado(p)
    sin, _ = montado(sin_cambiar(p, filtro="ninguno", temperatura=0, vineta=0, nitidez=0))
    assert tam == (90, 160, 30 * len(cambios)) and len(con) == len(sin) == tam[2], (tam, len(con))
    for i, cambio in enumerate(cambios):
        assert np.abs(con[30 * i + 15] - sin[30 * i + 15]).mean() > 1.5, cambio
    tinte = [(f[..., 0] - f[..., 2]).mean() for f in (con[8 * 30 + 15], sin[8 * 30 + 15], con[9 * 30 + 15])]
    assert tinte[0] > tinte[1] + 10 > tinte[2] + 20, tinte  # temperatura: + más cálido, - más frío
    # Las transiciones nuevas: 9 clips de 1 s con 8 transiciones de 0.3 s
    nuevas = ["desvanecer_negro", "desvanecer_blanco", "radial", "abrir_vertical", "deslizar_abajo", "difuminar",
              "cortes", "aplastar"]
    p = clips(proyecto(*[prueba, foto] * 4, prueba), *[{"hasta": 1, "transicion": x, "duracion_transicion": 0.3}
                                                       for x in nuevas], {"hasta": 1})
    _, tam = montado(p)
    assert tam == (90, 160, 270 - 8 * 9), tam

    # Efectos: tamaño y fotogramas de siempre, se notan, fotograma() da lo mismo que el montaje y los de «al ritmo»
    # siguen los golpes de la primera pista de música (analizada una sola vez: la de mentira cuenta las llamadas)
    llamadas = []

    def ritmo_falso(cancion):
        llamadas.append(Path(cancion).name)
        return 80.0, 0.25  # un golpe cada 0.75 s; el primero, a 0.25 s de la canción
    ritmo_real, video.ritmo = video.ritmo, ritmo_falso
    try:
        efectos = [e for e in edicion.EFECTOS if e != "ninguno"]
        p = clips(proyecto(*[prueba] * len(efectos), musica),
                  *[{"hasta": 1, "efecto": e, "intensidad": 100} for e in efectos])
        p["audios"][0]["inicio"] = 0.5  # golpes en 0, 0.75, 1.5, 2.25… de la línea de tiempo
        p["audios"].insert(0, {"tipo": "voz", "archivo": str(marca), "hasta": 1, "duracion_archivo": 2})
        p = edicion.validar(p)
        con, tam = montado(p)
        assert tam == (90, 160, 30 * len(efectos)) and len(con) == tam[2], tam
        assert llamadas == ["musica.wav"], llamadas  # la voz no cuenta: la primera pista de música
        sin, _ = montado(sin_cambiar(p, efecto="ninguno"))
        for i, e in enumerate(efectos):
            diferencia = np.abs(con[30 * i:30 * i + 30] - sin[30 * i:30 * i + 30]).mean(axis=(1, 2, 3))
            assert diferencia.max() > 4, (e, diferencia.round(1))
        # El destello, en el clip de 1 a 2 s: su golpe cae en 1.5 s (el fotograma 15 del clip), no en 0 ni en 0.75
        f0 = 30 * efectos.index("flash_ritmo")
        assert f0 == 30
        luz = con[f0:f0 + 30].mean(axis=(1, 2, 3)) - sin[f0:f0 + 30].mean(axis=(1, 2, 3))
        assert luz.argmax() == 15 and luz[15] > 30 and luz[14] < 3 and luz[0] < 15, luz.round(1)
        for i, e in enumerate(efectos):
            for n in (30 * i + 2, 30 * i + 15):
                f = de_qimage(render.fotograma(p, carpeta_fx, n / 30, 160))
                # Con el de antes, el suyo y el de después: el suyo es el que más se parece (sin el ruido del H.264)
                diferencias = [np.abs(reducir(f, 45, 80) - reducir(con[m], 45, 80)).mean() for m in (n - 1, n, n + 1)]
                assert f.shape == con[n].shape and min(diferencias) == diferencias[1] < 4, (e, n, diferencias)
        assert llamadas == ["musica.wav"] and len(list((carpeta_fx / "cache").glob("ritmo2-*.json"))) == 1
        render._render(p, carpeta_fx, d / "montado.mp4", 160, False, lambda t, f: None)  # todo de la caché
        assert llamadas == ["musica.wav"], llamadas
        # Sin música: 120 BPM desde 0 (golpes en 0 y 0.5 s del clip)
        p = clips(proyecto(prueba), {"hasta": 1, "efecto": "flash_ritmo", "intensidad": 100})
        luz = montado(p)[0].mean(axis=(1, 2, 3)) - montado(sin_cambiar(p, efecto="ninguno"))[0].mean(axis=(1, 2, 3))
        assert luz[0] > 30 and luz[15] > 30 and luz[14] < 3, luz.round(1)
    finally:
        video.ritmo = ritmo_real
    # Arreglos de la revisión:
    # - Una foto quieta con un efecto: fotograma() da el del montaje (sin -framerate salía un fotograma desfasado)
    p = clips(proyecto(foto), {"hasta": 1, "efecto": "flash_ritmo", "intensidad": 100})
    con, _ = montado(p)
    for n in (1, 15, 16):  # junto a los golpes (0 y 0.5 s, sin música): ahí cada fotograma es distinto
        f = de_qimage(render.fotograma(p, carpeta_fx, n / 30, 160))
        diferencias = [np.abs(reducir(f, 45, 80) - reducir(con[m], 45, 80)).mean() for m in (n - 1, n, n + 1)]
        assert min(diferencias) == diferencias[1] < 6, (n, diferencias)  # el suyo, no el de al lado
    # - El Brillo Ráfaga se pinta una vez: cambiar la intensidad no repinta, y un juego a medias se completa
    for intensidad in (60, 90):
        montado(clips(proyecto(prueba), {"hasta": 1, "efecto": "brillo_rafaga", "intensidad": intensidad}))
    pngs = sorted((carpeta_fx / "cache").glob("brillo-*.png"))
    assert len(pngs) == render._VUELTA * 30, len(pngs)
    pngs[3].unlink()
    patron, k = render._brillo(carpeta_fx / "cache", "9:16", 160, 30)
    assert all((carpeta_fx / "cache" / (patron % i)).is_file() for i in range(k))
    # - El ritmo de la caché es el mismo que el recién analizado (si no, el 2.º render rehacía tramos)
    ritmo_real, video.ritmo = video.ritmo, lambda cancion: (117.123456789, 0.987654321)
    try:
        p = clips(proyecto(prueba, musica), {"hasta": 1})
        carpeta_ritmo = d / "ritmo"
        (carpeta_ritmo / "cache").mkdir(parents=True)
        primero = render._ritmo(p, carpeta_ritmo / "cache")
        assert render._ritmo(p, carpeta_ritmo / "cache") == primero
    finally:
        video.ritmo = ritmo_real
    # - El tempo sale de los golpes, no de los escalones de librosa: un bombo a 120 BPM da ~120, no 117,45
    import soundfile  # noqa: E402
    golpes = np.zeros(22050 * 20, np.float32)
    for i in range(0, len(golpes), 22050 // 2):
        golpes[i:i + 600] = np.sin(np.arange(600) * 0.3) * np.linspace(1, 0, 600)
    soundfile.write(str(d / "bombo.wav"), golpes, 22050)
    bpm, _ = video.ritmo(d / "bombo.wav")
    assert abs(bpm - 120) < 0.5, bpm
    # Subtítulos: el render usa el estilo del proyecto
    p = clips(proyecto(foto, subtitulos={"activos": True, "estilo": "karaoke", "palabras": [
        {"palabra": "hola", "inicio": 0.1, "fin": 0.8}]}), {"hasta": 1})
    montado(p)
    assert any("\\kf70}HOLA" in f.read_text(encoding="utf-8") for f in (carpeta_fx / "cache").glob("subs-*.ass"))

    # ---------- fotograma() da el que se ve en el montaje, también desde el proxy ----------
    # Fuente de 25 fps (en un proyecto de 30) cuyo brillo es el número de fotograma; 1280x720: más grande que la
    # vista previa, así que miniatura() le encarga un proxy
    def numero(imagen):
        return round((16 + 219 * imagen[..., 1].mean() / 255) / 8)
    indices = hacer("indices.mp4", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=1.2,geq=lum='8*N':cb=128:"
                    "cr=128,scale=1280:720", "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0",
                    "-pix_fmt", "yuv420p")
    p = clips(proyecto(indices, formato="16:9"), {"desde": 0.33, "hasta": 0.93})
    montaje = [numero(cuadro(render.vista_previa(p, carpeta), n)) for n in range(2, 18)]
    def vistos():
        return [numero(de_qimage(render.fotograma(p, carpeta, n / 30))) for n in range(2, 18)]
    assert vistos() == montaje, (vistos(), montaje)  # -ss justo en t daba el fotograma siguiente
    assert not list((carpeta / "cache").glob("proxy-*"))
    render.miniatura(p["clips"][0], carpeta)
    render._proxies.join()  # se hace en otro hilo
    proxy = next((carpeta / "cache").glob("proxy-*.mp4"))
    assert info(proxy)[:2] == (1138, 640) and vistos() == montaje, info(proxy)
    original = proxy.read_bytes()
    video.ffmpeg("-f", "lavfi", "-i", "color=c=red:s=1138x640:r=25:d=1.2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 proxy)  # si fotograma() usa el proxy, ahora sale rojo
    assert rojo(de_qimage(render.fotograma(p, carpeta, 0.2))).mean() > 0.9
    proxy.write_bytes(original)
    render.miniatura(clips(proyecto(prueba), {})["clips"][0], carpeta)  # 640x360: no hace falta
    render._proxies.join()
    assert len(list((carpeta / "cache").glob("proxy-*"))) == 1

    # ---------- Tasa de fotogramas variable (pantalla quieta de un móvil): un solo fotograma rojo de 1 a 3 s ----------
    # La vista parada salía negra en lo quieto y, dividido en 1.5 s, el montaje adelantaba la imagen 1.5 s
    vfr = hacer("vfr.mp4", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=1", "-f", "lavfi", "-i",
                "color=c=red:s=640x360:r=30:d=2", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=1",
                "-filter_complex", "[0][1][2]concat=n=3,mpdecimate=hi=1:lo=1:frac=1:max=0", "-fps_mode", "vfr",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p")
    p = edicion.dividir(clips(proyecto(vfr, formato="16:9"), {}), 1.5)
    vista = render.vista_previa(p, carpeta)
    # 115: el final del segundo trozo (un -t contado desde el fotograma clave lo cortaba y repetía el rojo)
    assert all(rojo(cuadro(vista, n)).mean() > 0.9 and rojo(de_qimage(render.fotograma(p, carpeta, n / 30))).mean()
               > 0.9 for n in (40, 50, 85)) and rojo(cuadro(vista, 115)).mean() < 0.5

    # ---------- .ts con fotogramas clave cada 250 (OBS): «desde» después del último ya no deja el clip sin imagen ----------
    ts = hacer("obs.ts", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=11,geq=lum='8*mod(N,30)':cb=128:cr=128",
               "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-g", "250", "-f", "mpegts")
    p = clips(proyecto(ts, formato="16:9"), {"desde": 9.5, "hasta": 10.5})  # el último fotograma clave: 8.33 s
    vista = render.vista_previa(p, carpeta)
    assert ([numero(cuadro(vista, n)) for n in (0, 9)] == [15, 24] ==  # el fotograma 285 % 30 del archivo, y 294
            [numero(de_qimage(render.fotograma(p, carpeta, n / 30))) for n in (0, 9)]
            and render.miniatura(p["clips"][0], carpeta).height() == 72)

    # ---------- Vista previa de un trozo (▶ desde el cursor): igual que ese trozo de la entera ----------
    texto = {"tipo": "texto", "texto": "Hola", "x": 100, "y": 200, "ancho": 800, "alto": 300, "tamano": 120,
             "inicio": 0.5, "duracion": 3, "entrada": "fundido", "salida": "fundido"}
    p = clips(proyecto(prueba, marca, musica, capas=[texto], subtitulos={"activos": True, "palabras": [
        {"palabra": "hola", "inicio": 1.2, "fin": 1.6}]}), {"hasta": 1.5, "transicion": "disolver",
                                                             "duracion_transicion": 0.4})
    p["audios"][0].update(inicio=0.2, desde=0.5, hasta=2.5, volumen=0.2)
    p = edicion.validar(p)
    entera = d / "entera.mp4"  # copiada: la caché solo guarda la última vista previa
    entera.write_bytes(render.vista_previa(p, carpeta).read_bytes())
    assert not list((carpeta / "cache").glob("proxy-*"))  # el proxy de un clip que ya no está, borrado
    trozo = render.vista_previa(p, carpeta, desde=1.2, segundos=1)  # empieza a mitad de la transición
    assert cuadros(trozo) == 30 and abs(len(sonido(trozo)) / 48000 - 1) < 0.03, (cuadros(trozo), len(sonido(trozo)))
    for n in (0, 5, 13, 29):
        diferencia = np.abs(reducir(cuadro(trozo, n), 90, 160) - reducir(cuadro(entera, 36 + n), 90, 160)).mean()
        assert diferencia < 5, (n, diferencia)  # un fotograma de más o de menos da más de 10
    blanco, pitido = blanco_y_pitido(trozo)  # el segundo clip entra en 1.1 s y su marca está en su segundo 1
    assert blanco == 63 - 36 and abs(pitido - (2.1 - 1.2)) < 0.003, (blanco, pitido)
    fuerza = [np.sqrt((s[:len(s) // 480 * 480].reshape(-1, 480) ** 2).mean(axis=1))  # cada 10 ms
              for s in (sonido(trozo), sonido(entera)[int(1.2 * 48000):int(2.2 * 48000)])]
    assert np.abs(fuerza[0] - fuerza[1]).max() < 0.05, np.abs(fuerza[0] - fuerza[1]).max()
    # Después del último clip (en 3.1 s) solo sigue el texto, hasta 3.5 s
    assert cuadros(render.vista_previa(p, carpeta, desde=3.2)) == 9
    falla(render.vista_previa, p, carpeta, desde=-1)
    falla(render.vista_previa, p, carpeta, segundos=0)

    # ---------- Exportar sin espacio en el disco: avisa antes de empezar ----------
    libre = render.shutil.disk_usage
    render.shutil.disk_usage = lambda ruta: libre(ruta)._replace(free=10 ** 6)
    aviso = ""
    try:
        render.exportar(p, carpeta, d / "lleno.mp4")
    except ValueError as e:
        aviso = str(e)
    finally:
        render.shutil.disk_usage = libre
    assert re.search(r"unos \d+ MB", aviso) and not (d / "lleno.mp4").exists(), aviso  # decía «unos 0.0 GB»

    # ---------- Medios que faltan: el clip, color de fondo y silencio; el audio, no suena ----------
    p = clips(proyecto(prueba, prueba, fondo="#336699"), {"hasta": 1, "transicion": "fundido",
                                                          "duracion_transicion": 0.4}, {"hasta": 1})
    p["clips"].insert(1, {"tipo": "video", "archivo": str(d / "no_esta.mp4"), "hasta": 1, "duracion_archivo": 2,
                          "falta": True})
    p["audios"].append({"archivo": str(d / "no_esta.mp3"), "hasta": 1, "falta": True})
    p = edicion.validar(p)
    vista = render.vista_previa(p, carpeta)
    assert cuadros(vista) == 78, cuadros(vista)  # 1 + 1 + 1 - 0.4 = 2.6 s
    assert np.abs(cuadro(vista, 40) - [0x33, 0x66, 0x99]).max() < 6, cuadro(vista, 40)[0, 0]
    assert np.abs(sonido(vista)[int(1.05 * 48000):int(1.55 * 48000)]).max() < 0.01  # el clip de 1.0 a 1.6 s
    assert np.abs(sonido(vista)[:int(0.5 * 48000)]).max() > 0.1
    assert (de_qimage(render.fotograma(p, carpeta, 1.3)) == [0x33, 0x66, 0x99]).all()
    # Un .mp4 de solo sonido como clip de video (lo guardaban versiones de antes): un ValueError claro, no el de ffmpeg
    p["clips"].append({"tipo": "video", "archivo": str(hacer("sonido.mp4", "-f", "lavfi", "-i", "sine=duration=1",
                                                              "-c:a", "aac")), "hasta": 1, "duracion_archivo": 1})
    falla(render.vista_previa, edicion.validar(p), carpeta)

    # ---------- Sin clips: fondo, música en su sitio y capas solo en su tramo ----------
    capa = {"tipo": "imagen", "archivo": "roja.png", "ajuste": "cubrir"}
    p = edicion.validar({
        "fondo": "#000000",
        "audios": [{"archivo": str(musica), "inicio": 1.25, "desde": 0.5, "hasta": 1.5, "duracion_archivo": 3}],
        "capas": [{**capa, "x": 0, "y": 0, "ancho": 540, "alto": 540, "inicio": 1, "duracion": 1},
                  {**capa, "x": 540, "y": 1200, "ancho": 540, "alto": 540, "inicio": 0.5, "duracion": 2,
                   "entrada": "deslizar"}]})
    vista = render.vista_previa(p, carpeta)
    assert info(vista)[2] == 75, info(vista)  # lo que acaba más tarde: la segunda capa, en 2.5 s
    suena = np.flatnonzero(np.abs(sonido(vista)) > 0.05) / 48000
    assert abs(suena[0] - 1.25) < 0.005 and abs(suena[-1] - 2.25) < 0.005, (suena[0], suena[-1])
    for n, visible in ((15, False), (29, False), (30, True), (55, True), (60, False), (70, False)):
        assert rojo(cuadro(vista, n)[10:170, 10:170]).mean() > 0.95 if visible else \
            not rojo(cuadro(vista, n)[:200, :200]).any(), n
    deslizando = np.flatnonzero(rojo(cuadro(vista, 18)[400:580]).any(axis=0))  # 0.1 s después de entrar
    quieta = np.flatnonzero(rojo(cuadro(vista, 45)[400:580]).any(axis=0))
    assert deslizando.max() < 175 and (quieta.min(), quieta.max()) == (180, 359), (deslizando, quieta)

    # ---------- El fotograma de la vista previa es el del video montado ----------
    p = clips(proyecto(prueba, foto, ajuste="difuminar"),
              {"desde": 0.3, "hasta": 2.7, "velocidad": 1.5, "filtro": "sepia", "brillo": 20, "contraste": 10},
              {"hasta": 1.5, "movimiento": "acercar", "filtro": "vineta", "saturacion": -40})
    vista = render.vista_previa(p, carpeta)
    exportado = render.exportar(p, carpeta, d / "comparar.mp4", "720p")
    for n in (10, 40, 60, 90):  # clip, clip, foto al principio del zoom, foto casi al final
        t0 = time.perf_counter()
        f = de_qimage(render.fotograma(p, carpeta, n / 30))
        frio = time.perf_counter() - t0
        t0 = time.perf_counter()
        render.fotograma(p, carpeta, n / 30 + 0.01)  # mismo fotograma: de la caché
        caliente = time.perf_counter() - t0
        assert f.shape == (640, 360, 3) and frio < 2 and caliente < 0.1, (f.shape, frio, caliente)
        de_vista = np.abs(reducir(f, 90, 160) - reducir(cuadro(vista, n), 90, 160)).mean()
        de_export = np.abs(reducir(f, 90, 160) - reducir(cuadro(exportado, n), 90, 160)).mean()
        assert de_vista < 3 and de_export < 3, (n, de_vista, de_export)
    assert (de_qimage(render.fotograma(p, carpeta, 99)) == [0, 0, 0]).all()  # después del último clip: el fondo

    # ---------- La caché: cambiar un texto no vuelve a codificar los clips ----------
    texto = {"tipo": "texto", "texto": "Hola", "x": 100, "y": 200, "ancho": 800, "alto": 300, "tamano": 120,
             "inicio": 0.2, "duracion": 1.5, "entrada": "aparecer", "salida": "fundido"}
    p = clips(proyecto(prueba, prueba, capas=[texto], subtitulos={"activos": True, "palabras": [
        {"palabra": "hola {\\b1}", "inicio": 0.5, "fin": 1}]}), {"hasta": 1.5, "transicion": "disolver"},
        {"hasta": 1.5, "filtro": "byn"})
    t0 = time.perf_counter()
    primera = render.vista_previa(p, carpeta)
    tiempo_primera = time.perf_counter() - t0
    def hechos(patron):
        return {f.name: f.stat().st_mtime_ns for f in (carpeta / "cache").glob(patron)}
    tramos, pasos = hechos("tramo-vista*.mov"), hechos("paso-vista*.mov")
    assert len(tramos) == 2 and len(pasos) == 1, (tramos, pasos)  # los de los proyectos anteriores ya se borraron
    t0 = time.perf_counter()
    assert render.vista_previa(p, carpeta) == primera and time.perf_counter() - t0 < 1  # nada cambió: la misma
    p["capas"][0]["texto"] = "Adiós ' ; [x] , \\ : %"  # lo que rompería un filtro de ffmpeg va dentro de un PNG
    t0 = time.perf_counter()
    segunda = render.vista_previa(p, carpeta)
    tiempo_segunda = time.perf_counter() - t0
    assert segunda != primera and segunda.is_file() and not primera.exists()
    assert hechos("tramo-vista*.mov") == tramos and hechos("paso-vista*.mov") == pasos  # ni clips ni transiciones
    p["clips"][0]["transicion"] = "pixelado"  # otra transición: solo se rehace su paso
    render.vista_previa(p, carpeta)
    assert hechos("tramo-vista*.mov") == tramos and len(hechos("paso-vista*.mov").keys() - pasos.keys()) == 1
    p["clips"][1]["filtro"] = "sepia"  # esto sí cambia un tramo: se hace uno y el viejo se borra
    render.vista_previa(p, carpeta)
    nuevos = {f.name for f in (carpeta / "cache").glob("tramo-vista*.mov")}
    assert len(nuevos) == 2 and len(nuevos & set(tramos)) == 1, nuevos

    # ---------- Miniaturas y formas de onda (caché en disco) ----------
    mini = render.miniatura(p["clips"][0], carpeta)
    assert (mini.width(), mini.height()) == (128, 72), mini.size()
    assert render.miniatura(p["clips"][0], carpeta, 40).height() == 40
    assert render.miniatura({"tipo": "imagen", "archivo": str(foto), "hasta": 2}, carpeta).height() == 72
    t0 = time.perf_counter()
    onda = render.forma_de_onda(str(musica), carpeta, 300, 40)
    assert (onda.width(), onda.height()) == (300, 40) and onda.pixelColor(150, 20).alpha() > 0
    assert onda.pixelColor(150, 0).alpha() == 0  # una onda de 0.5: no llega arriba
    assert len(list((carpeta / "cache").glob("onda-*.png"))) == 1
    t0 = time.perf_counter()
    assert render.forma_de_onda(str(musica), carpeta, 300, 40).size() == onda.size() and time.perf_counter() - t0 < 0.2
    hacer("muda.mp4", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=1", "-c:v", "libx264", "-preset", "ultrafast")
    muda = render.forma_de_onda(str(d / "muda.mp4"), carpeta, 100, 20)
    assert muda.width() == 100 and muda.pixelColor(50, 10).alpha() == 0  # sin sonido: vacía, sin error

    # ---------- Subtítulos automáticos (la transcripción, de mentira: sin red ni Whisper) ----------
    oido = {}

    def transcribir_falso(audio, progreso=lambda f: None, **_):
        oido["duracion"] = video.duracion(audio)
        progreso(1.0)
        return [{"palabra": " hola ", "inicio": 0.5, "fin": 0.9}, {"palabra": "", "inicio": 1, "fin": 1.2},
                {"palabra": "fuera", "inicio": 2.9, "fin": 9.0}, {"palabra": "rara", "inicio": "x", "fin": 1}]
    real, ia.transcribir = ia.transcribir, transcribir_falso
    avisos = []
    try:
        palabras = render.subtitulos_automaticos(p, carpeta, lambda t, f: avisos.append(t))
    finally:
        ia.transcribir = real
    assert abs(oido["duracion"] - edicion.duracion_total(p)) < 0.1, oido  # la mezcla de toda la línea de tiempo
    total = edicion.duracion_total(p)  # lo que se sale del video se queda en su final
    assert palabras == [{"palabra": "hola", "inicio": 0.5, "fin": 0.9},
                        {"palabra": "fuera", "inicio": total, "fin": total}], palabras
    assert any("en tu PC" in t for t in avisos) and not list((carpeta / "cache").glob("audio-*"))
    edicion.validar({**p, "subtitulos": {"activos": True, "palabras": palabras}})  # se pueden guardar tal cual

    # ---------- Voz IA (la voz, de mentira) ----------
    narrar = desde_prompt.narrar
    desde_prompt.narrar = lambda texto, voz, destino: destino.write_bytes(b"ID3" + b"\x00" * 100)
    try:
        voz = render.voz_ia("Hola a todos", "Jorge (México)", carpeta)
        assert voz.parent == carpeta / "voces" and voz.suffix == ".mp3" and voz.is_file()
        assert render.voz_ia("Hola", "es-DO-EmilioNeural", carpeta) != voz
        falla(render.voz_ia, "Hola", "eleven:../../v1/user", carpeta)  # una voz que no está en la lista
        falla(render.voz_ia, "Hola", {"x": 1}, carpeta)
        falla(render.voz_ia, "   ", "es-DO-EmilioNeural", carpeta)
        falla(render.voz_ia, "x" * 5001, "es-DO-EmilioNeural", carpeta)
        falla(render.voz_ia, "Hola", "es-DO-EmilioNeural", r"\\atacante.example\s")
    finally:
        desde_prompt.narrar = narrar

    # ---------- Grabarte: tu cara en un círculo con borde, a su hora y con su sonido ----------
    def tono(archivo, f, a, b) -> float:
        """Amplitud del tono de f Hz entre los segundos a y b (mono, 48 kHz)."""
        x = sonido(archivo)[int(a * 48000):int(b * 48000)]
        return float(2 * abs(np.mean(x * np.exp(-2j * np.pi * f * np.arange(len(x)) / 48000))))
    gris3 = hacer("gris3.mp4", "-f", "lavfi", "-i", "color=c=gray:s=640x360:r=30:d=3", *h264[:6])  # sin sonido
    verde = hacer("verde.mp4", "-f", "lavfi", "-i", "color=c=0x00FF00:s=320x240:r=30:d=1.5", "-f", "lavfi", "-i",
                  "aevalsrc='0.5*sin(2*PI*1000*t)':s=48000:d=1.5", *h264)
    g = edicion.anadir_grabacion({**proyecto(gris3), "formato": "16:9"}, str(verde), 1.0, "sup_der", "circulo")
    g["capas"][0].update(borde="#FF0000", grosor_borde=30)
    g = edicion.validar(g)
    capa = g["capas"][0]
    vista = render.vista_previa(g, carpeta)
    k = 640 / 1080  # vista previa: 1138×640
    cx, cy, r = (capa["x"] + capa["ancho"] / 2) * k, (capa["y"] + capa["alto"] / 2) * k, capa["ancho"] / 2 * k
    dentro, en_borde = cuadro(vista, 45), [int(v) for v in (cx, cy - r + 6)]  # en 1.5 s
    assert dentro[int(cy), int(cx), 1] > 200 and dentro[int(cy), int(cx), 0] < 90, dentro[int(cy), int(cx)]  # verde
    rojo_borde = dentro[en_borde[1], en_borde[0]]
    assert rojo_borde[0] > 180 and rojo_borde[1] < 90, rojo_borde  # el borde, por dentro del círculo
    esquina = dentro[int(cy - r + 3), int(cx - r + 3)]  # dentro de la caja pero fuera del círculo: transparente
    assert abs(esquina - 128).max() < 25, esquina
    for n in (15, 81):  # antes de 1 s y después de 2.5 s, solo el fondo gris
        assert abs(cuadro(vista, n)[int(cy), int(cx)] - 128).max() < 25, n
    assert tono(vista, 1000, 1.1, 2.4) > 0.3  # su sonido, mezclado a su hora
    assert tono(vista, 1000, 0.1, 0.9) < 0.01 and tono(vista, 1000, 2.6, 2.95) < 0.01
    # Lo que se ve en el lienzo del editor (el fotograma del fondo + edicion.pintar_video) es lo que sale
    cara = render.fotograma_capa(capa, carpeta, 1.5, 30)
    assert (cara.width(), cara.height()) == (320, 240) and de_qimage(cara)[120, 160, 1] > 200  # entera, sin recortar
    lienzo = render.fotograma(g, carpeta, 1.5).convertToFormat(QImage.Format_RGB32)
    pintor = QPainter(lienzo)
    pintor.scale(k, k)  # en píxeles del video, como el lienzo
    edicion.pintar_video(pintor, capa, QRectF(capa["x"], capa["y"], capa["ancho"], capa["alto"]), cara)
    pintor.end()
    # Por bloques de 8×8: el canto del borde puede caer un píxel más allá (la caja del video va a píxeles pares)
    diferencia = np.abs(reducir(de_qimage(lienzo), 142, 80) - reducir(dentro, 142, 80))
    assert diferencia.mean() < 4 and np.percentile(diferencia, 99) < 30, (diferencia.mean(), diferencia.max())
    assert render.fotograma_capa(capa, carpeta, 0.5, 30) is None and render.fotograma_capa(capa, carpeta, 2.5) is None
    assert render.fotograma_capa({**capa, "falta": True}, carpeta, 1.5) is None
    falla(render.fotograma_capa, {**capa, "archivo": str(d / "claves.json.mp4")}, carpeta, 1.5)
    falla(render.fotograma_capa, {**capa, "archivo": r"\\atacante.example\s\v.mp4"}, carpeta, 1.5)
    falla(render.fotograma_capa, capa, carpeta, 1.5, 29)
    # Sin borde, redondeada y a pantalla completa también montan (la máscara y el borde van en cache/pip-*)
    for cambio in ({"grosor_borde": 0}, {"forma": "redondeado"}, edicion.disposicion("16:9", "completa")):
        assert info(render.vista_previa(edicion.validar({**g, "capas": [{**capa, **cambio}]}), carpeta))[:2] == (
            1138, 640)
    assert {f.name.split("-")[2] for f in (carpeta / "cache").glob("pip-640-*.png")} <= {"mascara", "borde"}
    # Al exportar: los tramos casi sin pérdida de la cámara también se borran
    exportado = render.exportar(g, carpeta, d / "con_cara.mp4", "720p")
    assert info(exportado)[:2] == (1280, 720) and not list((carpeta / "cache").glob("*-exp*.mov"))
    assert tono(exportado, 1000, 1.1, 2.4) > 0.3

    # Una webcam de tasa variable (falta 1 de cada 7 fotogramas; sus tiempos lo dicen): el blanco y el pitido del
    # segundo 4 de la grabación salen a la vez y en su sitio. Contando fotogramas, la imagen llegaría 0.6 s antes
    vfr = hacer("vfr.mp4", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=30:d=6,drawbox=c=white:t=fill:"
                "enable='gte(t,4)'", "-f", "lavfi", "-i", "aevalsrc='if(gte(t,4),0.8*sin(2*PI*1000*t),0)':s=48000:d=6",
                "-vf", "select='not(eq(mod(n\\,7)\\,3))'", "-fps_mode", "vfr", *h264)
    assert cuadros(vfr) < 160, cuadros(vfr)  # de verdad le faltan fotogramas
    g = edicion.anadir_grabacion(edicion.nuevo(formato="16:9"), str(vfr), 0.5, "completa")
    blanco, pitido = blanco_y_pitido(render.vista_previa(g, carpeta))
    assert abs(blanco - 135) <= 1 and abs(pitido - 4.5) < 0.02 and abs(pitido - blanco / 30) < 0.04, (blanco, pitido)

    # ---------- Bajar la música cuando hablas: baja bajo la voz y vuelve después (hasta el final) ----------
    hacer("tono.wav", "-f", "lavfi", "-i", "aevalsrc='0.3*sin(2*PI*330*t)':s=48000:d=6")
    hacer("habla.wav", "-f", "lavfi", "-i", "aevalsrc='0.3*sin(2*PI*1000*t)':s=48000:d=1.5")
    g = edicion.anadir_grabacion(edicion.anadir_medio(edicion.nuevo(), str(d / "tono.wav")), str(d / "habla.wav"), 2)
    assert [a["tipo"] for a in g["audios"]] == ["musica", "voz"] and g["bajar_musica"]
    con = d / "con_bajar.mp4"  # copiada: cada vista previa nueva borra la anterior de cache/
    con.write_bytes(render.vista_previa(g, carpeta).read_bytes())
    sin_bajar = render.vista_previa({**g, "bajar_musica": False}, carpeta)
    antes, debajo, despues = tono(con, 330, 0.5, 1.5), tono(con, 330, 2.4, 3.4), tono(con, 330, 4.8, 5.6)
    assert debajo < antes / 2.5, (antes, debajo)  # más de 8 dB más baja
    assert abs(despues - antes) < 0.05 * antes and tono(con, 330, 5.8, 5.97) > 0.9 * antes, (antes, despues)
    assert abs(tono(sin_bajar, 330, 2.4, 3.4) - antes) < 0.05 * antes  # sin la opción, la música no cambia
    assert abs(tono(con, 1000, 2.4, 3.4) - tono(sin_bajar, 1000, 2.4, 3.4)) < 0.02  # la voz, igual
    # El sonido de tu grabación también la baja
    g = edicion.anadir_grabacion(edicion.anadir_medio(edicion.nuevo(), str(d / "tono.wav")), str(verde), 2)
    con = render.vista_previa(g, carpeta)
    assert tono(con, 330, 2.4, 3.3) < tono(con, 330, 0.5, 1.5) / 2.5 and tono(con, 1000, 2.4, 3.3) > 0.3
    # Y los subtítulos automáticos la oyen: va en la mezcla que se transcribe
    oido = {}

    def transcribir_cara(audio, progreso=lambda f: None, **_):
        oido["tono"], oido["silencio"] = tono(audio, 1000, 2.2, 3.3), tono(audio, 1000, 0.3, 1.5)
        return [{"palabra": "hola", "inicio": 2.2, "fin": 2.6}]
    real, ia.transcribir = ia.transcribir, transcribir_cara
    try:
        assert render.subtitulos_automaticos(g, carpeta) == [{"palabra": "hola", "inicio": 2.2, "fin": 2.6}]
    finally:
        ia.transcribir = real
    assert oido["tono"] > 0.2 and oido["silencio"] < 0.01, oido

    # ---------- La caché de una grabación: una vista previa que no ve la capa no borra su tramo ni su proxy ----------
    cara720 = hacer("cara720.mp4", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=2", "-f", "lavfi", "-i",
                    "sine=frequency=500:duration=2", *h264)
    g = edicion.anadir_grabacion(proyecto(prueba, prueba), str(cara720), 0, "inf_der")  # 6 s de clips; la toma, 0–2
    capa = g["capas"][0]
    render.miniatura(capa, carpeta)  # la de la línea de tiempo encarga su proxy (720p: más que la vista previa)
    proxy = render._proxy(Path(capa["archivo"]), carpeta / "cache")
    fin = time.monotonic() + 60
    while not proxy.is_file() and time.monotonic() < fin:
        time.sleep(0.05)
    assert proxy.is_file()
    render.vista_previa(g, carpeta)
    tramos = {f.name for f in (carpeta / "cache").glob("tramo-vista640-*.mov")}
    render.vista_previa(g, carpeta, desde=4)  # ▶ (o «Grabar») después de la toma
    assert {f.name for f in (carpeta / "cache").glob("tramo-vista640-*.mov")} == tramos and proxy.is_file()
    render.vista_previa({**g, "capas": []}, carpeta)  # sin la capa, su tramo y su proxy sí se limpian
    assert len(list((carpeta / "cache").glob("tramo-vista640-*.mov"))) == len(tramos) - 1 and not proxy.is_file()

    # ---------- «Pantalla dividida»: el video principal pasa a la otra mitad, entero y centrado ----------
    for formato, (ancho, alto) in video.FORMATOS.items():
        sw, sh = ancho // 3 // 2 * 2, alto // 3 // 2 * 2  # un disco blanco en el centro del video principal
        disco = hacer(f"disco{sw}x{sh}.mp4", "-f", "lavfi", "-i", f"nullsrc=s={sw}x{sh}:r=30:d=4,geq=lum='if(lt("
                      f"hypot(X-W/2,Y-H/2),{min(sw, sh) // 8}),235,16)':cb=128:cr=128", *h264[:6])
        g = edicion.anadir_grabacion({**proyecto(disco), "formato": formato}, str(verde), 1.0, "dividida")
        vista = render.vista_previa(g, carpeta)
        libre, k = edicion.otra_mitad(formato, g["capas"][0]), info(vista)[1] / alto
        x1, y1 = round(libre["ancho"] * k), round(libre["alto"] * k)  # la mitad libre: (0, 0)–(x1, y1)
        antes, durante = cuadro(vista, 15), cuadro(vista, 45)  # a 0,5 s sin la capa; a 1,5 s con ella
        blanco_antes, blanco = (antes > 180).all(axis=2), (durante > 180).all(axis=2)
        ys, xs = np.nonzero(blanco)
        assert blanco.sum() >= 0.95 * blanco_antes.sum() and xs.max() < x1 and ys.max() < y1, formato  # entero
        assert abs(xs.mean() - x1 / 2) < 3 and abs(ys.mean() - y1 / 2) < 3, (formato, xs.mean(), ys.mean())
        assert np.abs(cuadro(vista, 90) - antes).mean() < 2, formato  # al acabar la capa, otra vez a todo el cuadro
        # El lienzo del editor (render.fotograma con las capas de video) enseña lo mismo en esa mitad
        foto = de_qimage(render.fotograma(g, carpeta, 1.5))
        bw, bh = x1 // 8, y1 // 8
        diferencia = np.abs(reducir(foto[:y1, :x1], bw, bh) - reducir(durante[:y1, :x1], bw, bh))
        assert foto.shape == durante.shape and diferencia.mean() < 6, (formato, diferencia.mean())
        assert (de_qimage(render.fotograma(g, carpeta, 0.5)) > 180).all(axis=2).sum() > 0.9 * blanco_antes.sum()

    # ---------- Exportar mira el disco también por las grabaciones (sus tramos casi sin pérdida) ----------
    solo_cara = edicion.anadir_grabacion(edicion.nuevo(formato="16:9"), str(verde), 0, "completa")  # sin clips
    uso_real = render.shutil.disk_usage
    render.shutil.disk_usage = lambda _ruta: types.SimpleNamespace(free=3 * 1024 ** 2)  # 3 MB libres
    try:  # 1,5 s a pantalla completa en 720p: hacen falta ~3,6 MB
        falla(render.exportar, solo_cara, carpeta, d / "no_cabe.mp4", "720p")
    finally:
        render.shutil.disk_usage = uso_real
    assert not (d / "no_cabe.mp4").exists()

    # ---------- Exportar en 4K: el doble de cada lado, con el texto pintado a ese tamaño (nítido, no ampliado), la
    # cámara y los subtítulos a escala y la vista previa igual de pequeña ----------
    assert render._tamano("16:9", 2160) == (3840, 2160) and render._tamano("9:16", 3840) == (2160, 3840)
    assert render._tamano("16:9", 10 ** 6) == (3840, 2160)  # nunca más que 4K
    g = edicion.anadir_grabacion({**proyecto(gris), "formato": "16:9"}, str(verde), 0, "sup_der", "circulo")
    g["clips"][0]["hasta"] = 0.5
    g["capas"][0].update(hasta=0.5, borde="#FF0000", grosor_borde=30)
    g["capas"].append({"tipo": "texto", "texto": "Hola", "x": 100, "y": 200, "ancho": 800, "alto": 300,
                       "tamano": 160, "negrita": True, "inicio": 0, "duracion": 0.5})
    g = edicion.validar({**g, "subtitulos": {"activos": True, "palabras": [
        {"palabra": "hola", "inicio": 0, "fin": 0.5}]}})
    # Lo que pide el disco, a escala: con sitio para 1080p pero no para 4K (sus tramos ocupan 6 veces más)
    uso_real = render.shutil.disk_usage
    render.shutil.disk_usage = lambda ruta: uso_real(ruta)._replace(free=2 * 4 * 1.2 * 1024 ** 2 * (0.5 + 0.5 * (
        g["capas"][0]["ancho"] * g["capas"][0]["alto"]) / (1920 * 1080)))
    try:
        e1 = render.exportar(g, carpeta, d / "1080p.mp4")
        falla(render.exportar, g, carpeta, d / "4k.mp4", "4K")
    finally:
        render.shutil.disk_usage = uso_real
    t0 = time.perf_counter()
    e4 = render.exportar(g, carpeta, d / "4k.mp4", "4K")
    tiempo_4k = time.perf_counter() - t0
    assert info(e4) == (3840, 2160, 15) and info(e1) == (1920, 1080, 15), (info(e4), info(e1))
    assert not list((carpeta / "cache").glob("*-exp*.mov"))
    assert info(render.vista_previa(g, carpeta))[:2] == (1138, 640)  # la vista previa no cambia
    f1, f4 = cuadro(e1, 7), cuadro(e4, 7)

    def letras(f, k):  # lo blanco del texto, en su caja (en píxeles del video: k por píxel del diseño)
        return (f[200 * k:500 * k, 100 * k:900 * k] > 200).all(axis=2)

    def salto(f, k):  # lo que cambia de media un píxel al de al lado en los bordes del texto: nítido, de golpe
        cambios = np.abs(np.diff(f[200 * k:500 * k, 100 * k:900 * k].mean(axis=2), axis=1))
        return cambios[cambios > 8].mean()
    assert 3.6 < letras(f4, 2).sum() / letras(f1, 1).sum() < 4.4, (letras(f4, 2).sum(), letras(f1, 1).sum())
    # El de 1080p ampliado (lo que daría escalar el video) tiene cada borde el doble de ancho: el salto, la mitad
    ampliado = np.frombuffer(ffmpeg_salida("-i", e1, "-vf", "select=eq(n\\,7),scale=3840:2160", "-frames:v", "1",
                                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-").stdout,
                             np.uint8).reshape(2160, 3840, 3).astype(int)
    assert salto(f4, 2) > 0.85 * salto(f1, 1) and salto(f4, 2) > 1.5 * salto(ampliado, 2), (
        salto(f4, 2), salto(f1, 1), salto(ampliado, 2))
    capa = g["capas"][0]  # la cámara: verde en el centro, borde rojo, en su sitio a doble tamaño
    cx, cy, r = capa["x"] + capa["ancho"] / 2, capa["y"] + capa["alto"] / 2, capa["ancho"] / 2
    assert f4[int(2 * cy), int(2 * cx), 1] > 200 and f4[int(2 * cy), int(2 * cx), 0] < 90, f4[int(2 * cy), int(2 * cx)]
    assert f4[int(2 * (cy - r) + 12), int(2 * cx), 0] > 180 and f4[int(2 * (cy - r) + 12), int(2 * cx), 1] < 90
    assert abs(f4[int(2 * (cy - r) + 6), int(2 * (cx - r) + 6)] - 128).max() < 25  # fuera del círculo, el fondo

    def subtitulo(f):  # la caja de la palabra que suena (amarilla)
        ys, xs = np.nonzero((f[..., 0] > 200) & (f[..., 1] > 200) & (f[..., 2] < 80))
        return np.array([xs.min(), ys.min(), xs.max(), ys.max()])
    assert np.abs(subtitulo(f4) - 2 * subtitulo(f1)).max() <= 5, (subtitulo(f4), subtitulo(f1))

    # ---------- Lo hostil se rechaza antes de llegar a ffmpeg ----------
    secreto = d / "claves.mp4"
    secreto.write_text('{"openai": "sk-SECRETO"}', encoding="utf-8")
    malo = clips(proyecto(prueba), {})
    malo["clips"][0]["archivo"] = str(secreto)  # validar no toca el disco: lo para archivo_medio al usarlo
    falla(render.fotograma, malo, carpeta, 0.5)
    falla(render.vista_previa, malo, carpeta)
    falla(render.miniatura, malo["clips"][0], carpeta)
    falla(render.fotograma, {**p, "clips": [{**p["clips"][0], "brillo": "0:enable=1"}]}, carpeta, 0.5)
    falla(render.fotograma, {**p, "clips": [{**p["clips"][0], "archivo": r"\\atacante.example\s\v.mp4"}]}, carpeta, 0)
    falla(render.fotograma, p, carpeta, float("nan"))
    falla(render.fotograma, p, r"\\atacante.example\s", 0.5)
    falla(render.exportar, p, carpeta, r"\\atacante.example\s\video.mp4")
    for calidad in ("4k", "8K", "2160p", ["4K"], None):
        falla(render.exportar, p, carpeta, d / "x.mp4", calidad)
    falla(render.forma_de_onda, r"\\atacante.example\s\a.mp3", carpeta, 100, 20)
    falla(render.forma_de_onda, str(secreto), carpeta, 100, 20)
    falla(render.forma_de_onda, str(musica), carpeta, 10 ** 9, 20)
    falla(render.vista_previa, edicion.nuevo(), carpeta)  # vacío

    # ---------- Al cerrar la app: ni un proxy más (su ffmpeg seguía solo y dejaba un tmp-…) ----------
    otra = edicion.nueva_carpeta("cerrar")
    grande = hacer("grande0.mp4", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=4", "-c:v", "libx264",
                   "-preset", "ultrafast")
    for i in (1, 2):
        (d / f"grande{i}.mp4").write_bytes(grande.read_bytes())
    for i in range(3):
        render._proxies.put((d / f"grande{i}.mp4", render._proxy(d / f"grande{i}.mp4", render._cache(otra))))
    while not render._en_curso:
        time.sleep(0.01)
    render._parar_proxy()  # lo que hace atexit
    render._proxies.join()
    assert not list((otra / "cache").glob("*proxy-*")), list((otra / "cache").glob("*"))
    render._cerrando.clear()

    # ---------- cancelar() (cerrar la app a mitad de una exportación): para ffmpeg y no deja restos ----------
    errores, p = [], clips(proyecto(prueba), {})

    def exportar_hasta_cancelar():
        try:
            render.exportar(p, otra, d / "cancelado.mp4")
        except Exception as e:  # noqa: BLE001  lo que haya dado: lo comprueba el assert
            errores.append(e)
    hilo = threading.Thread(target=exportar_hasta_cancelar)
    hilo.start()
    while not render._procesos and hilo.is_alive():
        time.sleep(0.01)
    t0 = time.perf_counter()
    render.cancelar()
    hilo.join()
    assert errores and time.perf_counter() - t0 < 2 and not (d / "cancelado.mp4").exists() and not list(
        (otra / "cache").glob("tmp-*")), (errores, time.perf_counter() - t0)

print(f"Pruebas del render del editor pasadas (vista previa {tiempo_vista:.1f} s, exportar {tiempo_export:.1f} s, "
      f"0,5 s en 4K {tiempo_4k:.1f} s, primera vista con capas {tiempo_primera:.1f} s y tras cambiar un texto "
      f"{tiempo_segunda:.1f} s).")
