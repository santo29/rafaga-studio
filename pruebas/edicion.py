"""Pruebas del modelo del editor de video (motor/edicion.py) y de los videos en motor/seguro.py, sin red ni claves:
python -m pruebas.edicion"""
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from motor import edicion, seguro, video  # noqa: E402


def falla(funcion, *args):
    """Lo hostil se rechaza con un ValueError claro: ni revienta con otro error ni pasa."""
    try:
        funcion(*args)
    except ValueError:
        return
    raise AssertionError(f"debió rechazar {args!r:.300}")


def cerca(a, b):
    return abs(a - b) < 1e-6


def clip(**c):
    return {"tipo": "video", "archivo": r"C:\videos\a.mp4", "desde": 0, "hasta": 4, **c}


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    edicion.CARPETA = d / "ediciones"  # nada de tocar datos/ de verdad

    # ---------- Medios de prueba (ffmpeg lavfi, 1–2 s, pequeños) ----------
    def hacer(nombre, segundos, *salida):
        destino = d / nombre
        video.ffmpeg("-f", "lavfi", "-i", f"testsrc2=s=160x90:r=30:d={segundos}",
                     "-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}", *salida, "-shortest", destino)
        return destino
    h264 = ("-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac")
    videos = {n: hacer(n, 2, *h264) for n in ("clip.mp4", "clip.mov", "clip.mkv", "clip.ts")}
    videos["clip.avi"] = hacer("clip.avi", 1, "-c:v", "mpeg4", "-c:a", "pcm_s16le")
    videos["camara.mts"] = hacer("camara.mts", 1, *h264, "-f", "mpegts", "-mpegts_m2ts_mode", "1")
    video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=3", d / "musica.wav")
    video.ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", d / "foto.png")
    secreto = d / "claves.json"
    secreto.write_text('{"openai": "sk-SECRETO"}', encoding="utf-8")

    # ---------- seguro: videos de verdad pasan, disfrazados no ----------
    assert videos["camara.mts"].read_bytes()[4:5] == b"G"  # el .mts de prueba lleva la marca de tiempo delante
    for nombre, ruta in videos.items():
        assert seguro.archivo_medio(str(ruta), seguro.VIDEOS, "video") == ruta.resolve(), nombre
    for nombre, contenido in (("disfrazado.mp4", secreto.read_bytes()), ("texto.ts", b"GET /x\n" * 200),
                              ("una_g.mts", b"\x00\x00\x00\x00G" + b"\x00" * 600),  # una sola sincronía no basta
                              ("riff.avi", b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 600)):  # un WAV no es un AVI
        (d / nombre).write_bytes(contenido)
        falla(seguro.archivo_medio, str(d / nombre), seguro.VIDEOS)
    for malo in (r"\\atacante.example\s\v.mp4", "//atacante.example/s/v.mp4", r"\\?\UNC\srv\s\v.mp4",
                 str(d / "no_existe.mp4"), str(secreto), str(d / "foto.png"), ""):
        falla(seguro.archivo_medio, malo, seguro.VIDEOS)
    # Lo de antes sigue igual: un MP4 vale como audio, un video no es una imagen, un WAV no es un video
    assert seguro.archivo_medio(str(videos["clip.mp4"]), seguro.AUDIOS) == videos["clip.mp4"].resolve()
    falla(seguro.archivo_medio, str(videos["clip.mp4"]), seguro.IMAGENES)
    (d / "musica.mp4").write_bytes((d / "musica.wav").read_bytes())
    falla(seguro.archivo_medio, str(d / "musica.mp4"), seguro.VIDEOS)
    assert not seguro.es_video(videos["clip.ts"].read_bytes()[:16])  # con 16 bytes (ia.py) no da error, solo «no»
    # Tope: 8 GB solo cuando se piden videos; el mismo .mp4 pedido como audio sigue con el tope general
    original = seguro.TAMANO_MAXIMO, seguro.TAMANO_VIDEO
    seguro.TAMANO_MAXIMO, seguro.TAMANO_VIDEO = 1000, 10 ** 9
    try:
        assert seguro.archivo_medio(str(videos["clip.mp4"]), seguro.VIDEOS | seguro.AUDIOS)
        falla(seguro.archivo_medio, str(videos["clip.mp4"]), seguro.AUDIOS)
        falla(seguro.archivo_medio, str(d / "musica.wav"), seguro.VIDEOS | seguro.AUDIOS)
        seguro.TAMANO_VIDEO = 1000
        falla(seguro.archivo_medio, str(videos["clip.mp4"]), seguro.VIDEOS)
    finally:
        seguro.TAMANO_MAXIMO, seguro.TAMANO_VIDEO = original

    # ---------- Un proyecto con varios clips, transiciones, fotos, capas y audios: tiempos exactos ----------
    base = {
        "nombre": "Prueba", "formato": "16:9", "fps": 25, "ajuste": "difuminar", "fondo": "#112233", "extra": "x",
        "clips": [clip(id="A", transicion="fundido", duracion_transicion=1, duracion_archivo=10, onclick="x"),
                  clip(id="B", archivo="C:/videos/b.mov", desde=2, hasta=8, velocidad=2),
                  {"id": "C", "tipo": "imagen", "archivo": r"C:\fotos\c.png", "hasta": 2, "transicion": "disolver",
                   "duracion_transicion": 0.5, "movimiento": "acercar"},
                  clip(id="D", hasta=3, transicion="zoom", movimiento="acercar")],
        "capas": [{"id": "t1", "tipo": "texto", "texto": "Hola", "inicio": 2, "duracion": 3, "entrada": "fundido"},
                  {"id": "e1", "tipo": "emoji", "texto": "🔥", "inicio": 9, "duracion": 1, "ancho": 5000}],
        "audios": [{"id": "a1", "archivo": r"C:\musica\m.mp3", "inicio": 1, "desde": 0, "hasta": 5, "volumen": 0.8,
                    "entrada": 1, "salida": 2}],
        "subtitulos": {"activos": True, "palabras": [{"palabra": "Hola", "inicio": 0.5, "fin": 0.9}]}}
    p = edicion.validar(base)
    assert "extra" not in p and "onclick" not in p["clips"][0] and p["fps"] == 25 and p["fondo"] == "#112233"
    assert edicion.validar(p) == p and edicion.validar(json.loads(json.dumps(p))) == p  # estable al guardar
    assert edicion.tiempos(p) == [(0, 4), (3, 6), (6, 8), (7.5, 10.5)], edicion.tiempos(p)
    assert cerca(edicion.duracion_clip(p["clips"][1]), 3) and cerca(edicion.duracion_total(p), 10.5)
    assert p["clips"][-1]["transicion"] == "ninguna"  # el último no tiene a quién pasar
    assert p["clips"][3]["movimiento"] == "ninguno" and p["clips"][2]["movimiento"] == "acercar"  # solo fotos
    assert p["clips"][2]["desde"] == 0 and p["clips"][2]["velocidad"] == 1 and "duracion_archivo" not in p["clips"][2]
    assert p["clips"][1]["duracion_archivo"] == 8  # si falta, vale «hasta»: no se puede alargar a ciegas
    assert p["capas"][1]["ancho"] == 2 * 1920  # capa recortada al doble del formato, como en diseño
    assert edicion.clip_en(p, 0) == (0, 0) and edicion.clip_en(p, 2) == (0, 2)
    assert edicion.clip_en(p, 3.5) == (1, 3)  # en la transición, el clip que entra (B va a velocidad 2)
    assert edicion.clip_en(p, 7.6) == (3, 0.1) and edicion.clip_en(p, 6.5) == (2, 0.5)
    for fuera in (-1, 10.5, 99, float("nan")):
        assert edicion.clip_en(p, fuera) is None, fuera
    assert [c["id"] for c in edicion.capas_en(p, 2)] == ["t1"] and edicion.capas_en(p, 5) == []
    assert edicion.capas_en(p, 4.99)[0]["texto"] == "Hola" and edicion.capas_en(p, 1.99) == []
    edicion.capas_en(p, 2)[0]["texto"] = "cambiado"
    assert p["capas"][0]["texto"] == "Hola"  # son copias: no tocan el proyecto (ni la pila de deshacer)
    con_audio = edicion.validar({**base, "audios": [{**base["audios"][0], "inicio": 9, "hasta": 3}]})
    assert cerca(edicion.duracion_total(con_audio), 12)  # lo que acaba más tarde de las tres pistas
    # Ajustes y efecto nuevos: con su valor por defecto (los proyectos de antes se abren igual) y redondeados
    assert {k: p["clips"][0][k] for k in ("temperatura", "vineta", "nitidez", "efecto", "intensidad")} == {
        "temperatura": 0, "vineta": 0, "nitidez": 0, "efecto": "ninguno", "intensidad": 60}
    assert p["subtitulos"]["estilo"] == "clasico"
    nuevo_clip = edicion.validar({"clips": [clip(filtro="nocturno", transicion="radial", efecto="brillo_rafaga",
                                                 intensidad=33.4, temperatura=-100, vineta=100, nitidez=12.6), clip()],
                                  "subtitulos": {"estilo": "karaoke"}})
    assert {k: nuevo_clip["clips"][0][k] for k in ("filtro", "transicion", "efecto", "intensidad", "temperatura",
                                                   "vineta", "nitidez")} == {
        "filtro": "nocturno", "transicion": "radial", "efecto": "brillo_rafaga", "intensidad": 33, "temperatura": -100,
        "vineta": 100, "nitidez": 13}
    assert nuevo_clip["subtitulos"]["estilo"] == "karaoke"

    # ---------- Plantillas: filtro, efecto, transición, subtítulos y sus textos, sin tocar los medios ----------
    antes = copy.deepcopy(p)
    fin = edicion.tiempos(p)[-1][1]
    for clave, plantilla in edicion.PLANTILLAS.items():
        assert plantilla["nombre"] and plantilla["descripcion"], clave
        q = edicion.aplicar_plantilla(p, clave)
        assert p == antes and edicion.validar(q) == q
        assert all((c["filtro"], c["efecto"], c["intensidad"]) == (plantilla["filtro"], plantilla["efecto"],
                                                                   plantilla["intensidad"]) for c in q["clips"])
        assert [c["transicion"] for c in q["clips"]] == [plantilla["transicion"]] * 3 + ["ninguna"], clave
        assert q["subtitulos"]["estilo"] == plantilla["estilo"] and q["subtitulos"]["activos"]
        assert q["subtitulos"]["palabras"] == p["subtitulos"]["palabras"] and q["audios"] == p["audios"]
        assert [(c["id"], c["archivo"], c["desde"], c["hasta"]) for c in q["clips"]] == [
            (c["id"], c["archivo"], c["desde"], c["hasta"]) for c in p["clips"]]
        assert [c["id"] for c in q["capas"]] == ["t1", "e1", "plantilla-titulo"] + (
            ["plantilla-cierre"] if clave == "anuncio" else []), q["capas"]
        titulo = q["capas"][2]
        assert titulo["texto"] == "Prueba" and titulo["inicio"] == 0 and titulo["tipo"] == "texto"
        assert edicion.aplicar_plantilla(q, clave) == q  # dos veces: no duplica sus capas
        assert edicion.duracion_total(q) == edicion.duracion_total(edicion.validar(
            {**q, "capas": p["capas"]}))  # sus textos no alargan el video
    cierre = edicion.aplicar_plantilla(p, "anuncio")["capas"][-1]
    assert cerca(cierre["inicio"] + cierre["duracion"], edicion.tiempos(edicion.aplicar_plantilla(p, "anuncio"))[-1][1])
    otra = edicion.aplicar_plantilla(edicion.aplicar_plantilla(p, "anuncio"), "vlog")  # cambia de plantilla: sin cierre
    assert [c["id"] for c in otra["capas"]] == ["t1", "e1", "plantilla-titulo"]
    assert otra["clips"][0]["filtro"] == "dorado"
    assert fin == edicion.tiempos(p)[-1][1]
    for malo in ("no_existe", None, ["vlog"], "VLOG"):
        falla(edicion.aplicar_plantilla, p, malo)
    falla(edicion.aplicar_plantilla, edicion.nuevo(), "vlog")  # sin clips: un error claro
    # Un clip que acaba a mitad de milésima (2.414 s a 2.3x = 1.049565 s): sus textos no pasan del final
    raro = edicion.validar({"clips": [{"tipo": "video", "archivo": "C:\\x\\a.mp4", "hasta": 2.414, "velocidad": 2.3,
                                       "duracion_archivo": 10}]})
    for clave in edicion.PLANTILLAS:
        q = edicion.aplicar_plantilla(raro, clave)
        assert edicion.duracion_total(q) == edicion.duracion_total(raro), clave
    try:
        edicion.aplicar_plantilla(edicion.nuevo(), "vlog")
    except ValueError as e:
        assert "clip" in str(e), e

    # Transiciones más largas que el clip: se recortan a la mitad del más corto, o se quitan si no caben
    t = edicion.validar({"clips": [clip(transicion="barrido", duracion_transicion=2, hasta=3), clip(hasta=8),
                                   clip(transicion="circulo", duracion_transicion=2, hasta=0.3), clip()]})
    assert t["clips"][0]["duracion_transicion"] == 1.5 and t["clips"][2]["transicion"] == "ninguna"
    assert edicion.tiempos(t)[1] == (1.5, 9.5)

    # ---------- Operaciones: devuelven un proyecto nuevo y no tocan el que reciben ----------
    antes = copy.deepcopy(p)
    q = edicion.dividir(p, 5)  # en B (3–6): 2 s de línea de tiempo = 4 s de archivo a velocidad 2
    assert p == antes
    b1, b2 = q["clips"][1], q["clips"][2]
    assert (b1["desde"], b1["hasta"], b1["transicion"]) == (2, 6, "ninguna") and (b2["desde"], b2["hasta"]) == (6, 8)
    assert len({b1["id"], b2["id"], "A", "B", "C", "D"}) == 6  # ids nuevos
    assert edicion.tiempos(q) == [(0, 4), (3, 5), (5, 6), (6, 8), (7.5, 10.5)]
    f = edicion.dividir(p, 7)  # una foto (6–8): el segundo trozo empieza en 0 y conserva la transición
    assert [(c["desde"], c["hasta"]) for c in f["clips"][2:4]] == [(0, 1), (0, 1)]
    assert f["clips"][2]["transicion"] == "ninguna" and f["clips"][3]["transicion"] == "disolver"
    assert f["clips"][3]["duracion_transicion"] == 0.5 and cerca(edicion.duracion_total(f), 10.5)
    for malo in (3.05, 5.97, 20, -1, float("nan"), "5", None):  # pegado al borde, fuera de la pista, no es un número
        falla(edicion.dividir, p, malo)

    r = edicion.recortar(p, "A", 1, 3)
    assert (r["clips"][0]["desde"], r["clips"][0]["hasta"]) == (1, 3) and r["clips"][0]["duracion_transicion"] == 1
    assert edicion.tiempos(r)[:2] == [(0, 2), (1, 4)]
    assert edicion.recortar(p, "A", -5, 50)["clips"][0]["hasta"] == 10  # ajustado al archivo (duracion_archivo)
    assert edicion.recortar(p, "C", 1, 6)["clips"][2]["hasta"] == 5  # foto: lo que dura
    a = edicion.recortar(p, "a1", 2, 5)["audios"][0]
    assert (a["inicio"], a["desde"], a["hasta"]) == (3, 2, 5)  # el sonido sigue en el mismo sitio
    for args in (("A", 3, 1), ("A", 2, 2.05), ("no_existe", 0, 1), ("t1", 0, 1), ("A", float("inf"), 1)):
        falla(edicion.recortar, p, *args)
    assert p == antes

    m = edicion.mover_clip(p, "D", 0)
    assert [c["id"] for c in m["clips"]] == ["D", "A", "B", "C"] and m["clips"][-1]["transicion"] == "ninguna"
    assert [c["id"] for c in edicion.mover_clip(p, "A", 99)["clips"]] == ["B", "C", "D", "A"]
    assert [c["id"] for c in edicion.mover_clip(p, "D", -3)["clips"]][0] == "D"
    for args in (("D", True), ("D", 1.5), ("t1", 0), ("x", 0)):
        falla(edicion.mover_clip, p, *args)

    for elemento, clave in (("B", "clips"), ("t1", "capas"), ("a1", "audios")):
        sin = edicion.borrar(p, elemento)
        assert elemento not in [e["id"] for e in sin[clave]] and len(sin[clave]) == len(p[clave]) - 1
    assert edicion.tiempos(edicion.borrar(p, "B")) == [(0, 4), (3, 5), (4.5, 7.5)]
    falla(edicion.borrar, p, "no_existe")
    assert p == antes

    # ---------- JSON hostil ----------
    falla(edicion.validar, [])
    falla(edicion.validar, {"version": 2})
    inicio = time.monotonic()
    falla(edicion.validar, {"clips": [clip()] * 100_000})
    falla(edicion.validar, {"capas": [{"tipo": "texto"}] * 101})
    falla(edicion.validar, {"audios": [base["audios"][0]] * 51})
    assert time.monotonic() - inicio < 1, "los topes se miran antes de recorrer"
    assert len(edicion.validar({"clips": [clip(hasta=1)] * 300})["clips"]) == 300
    for archivo in (r"\\atacante.example\s\v.mp4", "//atacante.example/s/v.mp4", r"\\?\UNC\srv\s\v.mp4",
                    r"\\?\C:\v.mp4", "/\\srv\\s\\v.mp4", "v.mp4", r"videos\v.mp4", r"C:v.mp4",
                    r"..\..\datos\claves.mp4", r"C:\x\..\..\datos\claves.mp4", r"C:\x\v.mp4:oculto",
                    r"C:\x\CON.mp4", r"C:\x\nul.mp4", r"C:\x\claves.json", r"C:\x\foto.png", "C:\\x\\v\x00.mp4",
                    "C:\\x\\v\n.mp4", "C:\\x\\" + "a" * 2000 + ".mp4", "", 123, None, ["C:\\x\\v.mp4"]):
        falla(edicion.validar, {"clips": [clip(archivo=archivo)]})
    for campo, malo in (("velocidad", 0), ("velocidad", -1), ("velocidad", 1e308), ("velocidad", 4.5),
                        ("velocidad", float("nan")), ("velocidad", "2"), ("velocidad", True), ("volumen", 3),
                        ("volumen", -0.1), ("brillo", 101), ("saturacion", float("-inf")), ("silencio", 1),
                        ("filtro", "colorchannelmixer=1"), ("transicion", "xfade;rm"), ("duracion_transicion", 5),
                        ("duracion_transicion", 0.1), ("movimiento", "girar"), ("tipo", "audio"), ("tipo", []),
                        ("desde", -1), ("hasta", float("inf")), ("hasta", None), ("duracion_archivo", 3),
                        ("temperatura", 101), ("temperatura", -100.6), ("temperatura", "5"), ("vineta", -1),
                        ("vineta", 100.6), ("nitidez", float("nan")), ("nitidez", True), ("efecto", "glitch;movie=x"),
                        ("efecto", None), ("efecto", "GLITCH"), ("intensidad", 101), ("intensidad", -1),
                        ("intensidad", [60]), ("filtro", "nocturno2"), ("transicion", "fadeblack")):
        falla(edicion.validar, {"clips": [clip(**{campo: malo})]})
    for malo in ({"hasta": 0}, {"desde": 4, "hasta": 4}, {"desde": 5}, {"hasta": 0.05}):  # sin tramo o casi nada
        falla(edicion.validar, {"clips": [clip(**malo)]})
    falla(edicion.validar, {"clips": ["no soy un clip"]})
    falla(edicion.validar, {"clips": [clip(hasta=3700, duracion_archivo=3700)]})  # más de 60 minutos
    falla(edicion.validar, {"clips": [clip(hasta=2000, duracion_archivo=4000)] * 2})
    for campo, malo in (("formato", "21:9"), ("fps", 29.97), ("fps", True), ("fps", "30"), ("ajuste", "estirar"),
                        ("fondo", "red"), ("nombre", "x" * 121), ("nombre", 5), ("clips", {}), ("capas", "x"),
                        ("subtitulos", []), ("subtitulos", {"palabras": {}}), ("subtitulos", {"activos": "sí"}),
                        ("subtitulos", {"estilo": "comic"}), ("subtitulos", {"estilo": 3}),
                        ("subtitulos", {"estilo": None})):
        falla(edicion.validar, {campo: malo})
    for capa in ({"tipo": "forma"}, {"tipo": "texto", "inicio": float("nan")}, {"tipo": "texto", "duracion": 0},
                 {"tipo": "texto", "entrada": "explotar"}, {"tipo": "texto", "salida": "deslizar"},
                 {"tipo": "imagen", "archivo": r"..\..\claves.png"}, {"tipo": "imagen", "archivo": r"C:\x\a.png"},
                 {"tipo": "texto", "color": "rojo"}, {"tipo": "texto", "inicio": 3599, "duracion": 2}, "capa"):
        falla(edicion.validar, {"capas": [capa]})
    falla(edicion.validar, {"capas": [{"tipo": "imagen", "archivo": "a.png"}] * 13})  # los topes de diseño
    falla(edicion.validar, {"capas": [{"tipo": "texto", "sombra": True}] * 13})
    for audio in ({"archivo": r"\\srv\s\m.mp3", "hasta": 1}, {"archivo": r"C:\x\m.exe", "hasta": 1},
                  {"archivo": r"C:\x\m.mp3", "hasta": 1, "entrada": 11}, {"archivo": r"C:\x\m.mp3", "hasta": 1,
                                                                         "tipo": "ruido"},
                  {"archivo": r"C:\x\m.mp3", "hasta": 1, "volumen": float("nan")}, {"archivo": r"C:\x\m.mp3"}):
        falla(edicion.validar, {"audios": [audio]})
    for palabras in ([{"palabra": 5, "inicio": 0, "fin": 1}], [{"palabra": "a", "inicio": 2, "fin": 1}],
                     [{"palabra": "a" * 101, "inicio": 0, "fin": 1}], ["hola"],
                     [{"palabra": "a", "inicio": 0, "fin": 1}] * 20_001):
        falla(edicion.validar, {"subtitulos": {"palabras": palabras}})
    inicio = time.monotonic()
    edicion.validar({"subtitulos": {"palabras": [{"palabra": "a", "inicio": 0, "fin": 1}] * 20_000}})
    assert time.monotonic() - inicio < 2
    # Ids repetidos o raros entre clips, capas y audios se cambian: borrar no se equivoca de elemento
    rep = edicion.validar({"clips": [clip(id="x"), clip(id="x"), clip(id="../a")],
                           "capas": [{"id": "x", "tipo": "texto"}], "audios": [{**base["audios"][0], "id": "x"}]})
    ids = [e["id"] for e in rep["clips"] + rep["capas"] + rep["audios"]]
    assert len(set(ids)) == 5 and ids[0] == "x"

    # ---------- Carpetas, guardar, abrir y listar ----------
    carpeta = edicion.nueva_carpeta("Mi vídeo ñandú")
    assert carpeta.parent == edicion.CARPETA and carpeta.name.endswith("-mi-video-nandu"), carpeta
    assert (carpeta / "imagenes").is_dir() and (carpeta / "cache").is_dir()
    assert edicion.nueva_carpeta("../../..\\x").parent == edicion.CARPETA
    with ThreadPoolExecutor(8) as hilos:  # el MCP crea proyectos en paralelo: mismo nombre a la vez, ninguno falla
        a_la_vez = list(hilos.map(edicion.nueva_carpeta, ["A la vez"] * 40))
    assert len(set(a_la_vez)) == 40 and all((c / "cache").is_dir() for c in a_la_vez)

    # anadir_medio: mide con ffmpeg, valida el contenido y no toca el proyecto que recibe
    vacio = edicion.nuevo("Real")
    real = edicion.anadir_medio(vacio, str(videos["clip.mp4"]))
    assert vacio["clips"] == [] and len(real["clips"]) == 1
    c = real["clips"][0]
    assert c["tipo"] == "video" and abs(c["hasta"] - 2) < 0.1 and c["hasta"] <= c["duracion_archivo"]
    assert c["archivo"] == str(videos["clip.mp4"].resolve())
    real = edicion.anadir_medio(real, str(d / "foto.png"))
    assert real["clips"][1]["tipo"] == "imagen" and real["clips"][1]["hasta"] == edicion.IMAGEN
    real = edicion.anadir_medio(real, str(videos["camara.mts"]))
    real = edicion.anadir_medio(real, str(d / "musica.wav"))
    assert real["audios"][0]["inicio"] == 0 and abs(real["audios"][0]["hasta"] - 3) < 0.1
    assert len(real["clips"]) == 3
    for malo in (str(d / "disfrazado.mp4"), str(secreto), r"\\atacante.example\s\v.mp4", str(d / "virus.exe"),
                 "datos/claves.json", str(d / "no_existe.mp4"), "", str(d / "musica.mp4")):
        falla(edicion.anadir_medio, real, malo)
    lleno = edicion.validar({"clips": [{"tipo": "imagen", "archivo": str(d / "foto.png"), "hasta": 3599}]})
    casi = edicion.anadir_medio(lleno, str(videos["clip.mp4"]))  # entra recortado a lo que cabe en 60 min
    assert casi["clips"][1]["hasta"] == 1 and edicion.duracion_total(casi) == 3600
    falla(edicion.anadir_medio, casi, str(d / "foto.png"))

    # Una canción en .mp4/.webm sin imagen (o con portada) entra como audio: como clip, el render no podría montarla.
    # Un .mkv solo de sonido se rechaza claro, y «Importar música» (audio=True) siempre da un audio
    video.ffmpeg("-f", "lavfi", "-i", "sine=duration=2", "-c:a", "aac", d / "cancion.mp4")
    video.ffmpeg("-f", "lavfi", "-i", "sine=duration=2", "-c:a", "libopus", d / "cancion.webm")
    video.ffmpeg("-f", "lavfi", "-i", "sine=duration=2", "-c:a", "aac", d / "cancion.mkv")
    video.ffmpeg("-f", "lavfi", "-i", "sine=duration=2", "-i", d / "foto.png", "-map", "0", "-map", "1", "-c:a", "aac",
                 "-c:v", "mjpeg", "-disposition:v:0", "attached_pic", d / "portada.mp4")
    for nombre in ("cancion.mp4", "cancion.webm", "portada.mp4"):
        q = edicion.anadir_medio(vacio, str(d / nombre))
        assert q["clips"] == [] and abs(q["audios"][0]["hasta"] - 2) < 0.1, nombre
    falla(edicion.anadir_medio, vacio, str(d / "cancion.mkv"))
    q = edicion.anadir_medio(vacio, str(videos["clip.mp4"]), audio=True)
    assert q["clips"] == [] and q["audios"][0]["archivo"] == str(videos["clip.mp4"].resolve())
    assert video.medir(videos["clip.mkv"])[1] and edicion.anadir_medio(vacio, str(videos["clip.mkv"]))["clips"]

    # Un .webm grabado en el navegador (escrito a una tubería: sin duración en la cabecera) se mide recorriéndolo
    with open(d / "navegador.webm", "wb") as f:
        subprocess.run([video.FFMPEG, "-hide_banner", "-loglevel", "error", *video.solo_medios([
            "-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=2", "-f", "lavfi", "-i", "sine=duration=2", "-c:v", "libvpx",
            "-deadline", "realtime", "-c:a", "libopus", "-f", "webm", "pipe:1"])], stdout=f, check=True)
    assert "Duration: N/A" in video._leer_ffmpeg("-i", d / "navegador.webm")
    q = edicion.anadir_medio(vacio, str(d / "navegador.webm"))
    assert q["clips"][0]["tipo"] == "video" and abs(q["clips"][0]["duracion_archivo"] - 2) < 0.1, q["clips"]

    # Subtítulos: el borde y la sombra encogen con el video como las letras (la vista previa a 640 no los engorda)
    video.subtitulos_ass([{"palabra": "Hola", "inicio": 0, "fin": 1}, {"palabra": "mundo", "inicio": 1, "fin": 2}],
                         "9:16", d / "s.ass")
    oscuros = []
    for tam, reducir in (("360x640", ""), ("1080x1920", ",scale=360:640")):
        video.ffmpeg("-f", "lavfi", "-i", f"color=c=white:s={tam}", "-vf", f"ass=s.ass{reducir},format=gray",
                     "-frames:v", "1", "-f", "rawvideo", "s.gray", cwd=d)
        oscuros.append(sum(b < 128 for b in (d / "s.gray").read_bytes()))  # borde y sombra sobre blanco
    assert 0.8 < oscuros[0] / oscuros[1] < 1.25, oscuros
    # Estilos: «clasico» sale byte a byte como antes de que hubiera estilos (huellas del .ass de entonces); cada estilo
    # da un .ass que ffmpeg dibuja, con lo del usuario escapado
    pal = [{"palabra": "hola", "inicio": 0.0, "fin": 0.4}, {"palabra": "a {x}", "inicio": 0.5, "fin": 0.6},
           {"palabra": "todos.", "inicio": 0.7, "fin": 1.2}, {"palabra": "Ñandú", "inicio": 1.5, "fin": 1.9}]
    for formato, huella in (("9:16", "352c37d48f50bd728fc731e97dd818d0987f15468d9d1f504a81aa3bb01a19fe"),
                            ("16:9", "24030d88eedac7329f3f9bf9de322551fd3af12f4498f7e86c9a715ca0173bdb")):
        for estilo in ({}, {"estilo": "clasico"}):
            hecho = video.subtitulos_ass(pal, formato, d / "c.ass", **estilo).read_bytes()
            assert hashlib.sha256(hecho).hexdigest() == huella, (formato, estilo)
    assert set(edicion.ESTILOS_SUBTITULOS) == {"clasico", "caja", "neon", "karaoke", "minimal", "impacto"}
    textos = set()
    for estilo in edicion.ESTILOS_SUBTITULOS:
        texto = video.subtitulos_ass(pal, "9:16", d / "e.ass", estilo=estilo).read_text(encoding="utf-8")
        assert texto.startswith("[Script Info]") and texto.count("\nStyle: Base,") == 1, estilo
        assert texto.count("\nDialogue: ") >= 2 and "{x}" not in texto and "(X)" in texto.upper(), estilo
        textos.add(texto)
        video.ffmpeg("-f", "lavfi", "-i", "color=c=white:s=360x640:r=10:d=1", "-vf", "ass=e.ass,format=gray",
                     "-ss", "0.25", "-frames:v", "1", "-f", "rawvideo", "e.gray", cwd=d)
        assert sum(b < 200 for b in (d / "e.gray").read_bytes()) > 200, estilo  # se ve algo escrito
    assert len(textos) == len(edicion.ESTILOS_SUBTITULOS)
    assert "\\kf50}HOLA" in video.subtitulos_ass(pal, "9:16", d / "k.ass", estilo="karaoke").read_text(encoding="utf-8")
    # Un grupo no junta dos frases: se corta tras el punto o tras un silencio, aunque quepa otra palabra
    frases = [{"palabra": p, "inicio": a, "fin": b} for p, a, b in (
        ("de", 0, 0.2), ("verdad.", 0.2, 0.5), ("¿Cansado", 0.5, 0.9), ("y", 0.9, 1.0), ("sin", 2.0, 2.2))]
    texto = video.subtitulos_ass(frases, "16:9", d / "f.ass", estilo="karaoke").read_text(encoding="utf-8")
    assert [re.sub(r"\{[^}]*\}", "", linea.split(",,")[-1]) for linea in texto.splitlines()
            if linea.startswith("Dialogue")] == ["DE VERDAD.", "¿CANSADO Y", "SIN"], texto

    archivo = edicion.guardar(real, carpeta)
    assert archivo == carpeta / "proyecto.json" and edicion.abrir(carpeta) == real
    falla(edicion.guardar, real, r"\\atacante.example\s\proyecto")
    falla(edicion.abrir, r"\\atacante.example\s\proyecto")
    falla(edicion.abrir, d / "no_existe")
    (carpeta / "miniatura.png").write_bytes((d / "foto.png").read_bytes())
    assert edicion.listar() == [{"nombre": "Real", "carpeta": str(carpeta),
                                 "miniatura": str((carpeta / "miniatura.png").resolve())}]

    # Un archivo movido o borrado (USB quitado) no impide abrir: se marca «falta» y se vuelve a enlazar de una vez
    for origen, copia in ((videos["clip.mp4"], "perdido.mp4"), (d / "musica.wav", "perdida.wav")):
        shutil.copy(origen, d / copia)
    mio = edicion.dividir(edicion.anadir_medio(edicion.nuevo("Perdidos"), str(d / "perdido.mp4")), 1)
    mio = edicion.anadir_medio(edicion.anadir_medio(mio, str(d / "foto.png")), str(d / "perdida.wav"))
    mio = edicion.anadir_medio(mio, str(d / "perdido.mp4"), audio=True)  # el mismo video, también como música
    perdidos = edicion.nueva_carpeta("perdidos")
    edicion.guardar(edicion.validar({**mio, "capas": [{"tipo": "texto", "texto": "Mis textos"}]}), perdidos)
    (d / "movido").mkdir()
    (d / "perdido.mp4").rename(d / "movido" / "perdido.mp4")
    (d / "perdida.wav").unlink()
    abierto = edicion.abrir(perdidos)
    assert [c.get("falta") for c in abierto["clips"]] == [True, True, None] and abierto["audios"][0]["falta"] is True
    assert abierto["capas"][0]["texto"] == "Mis textos" and edicion.validar(abierto) == abierto
    falla(edicion.validar, {"clips": [clip(falta="sí")]})
    nueva = str((d / "movido" / "perdido.mp4").resolve())
    arreglado = edicion.reenlazar(abierto, abierto["clips"][1]["id"], nueva)  # los dos trozos del clip dividido
    assert [c.get("falta") for c in arreglado["clips"]] == [None] * 3 and arreglado["audios"][0]["falta"]
    assert [c["archivo"] for c in arreglado["clips"][:2]] == [nueva] * 2 and abierto["clips"][0]["falta"]
    assert arreglado["audios"][1]["archivo"] == nueva and "falta" not in arreglado["audios"][1]  # su audio también
    corto = hacer("corto.mp4", 1, *h264)
    for elemento, ruta in ((abierto["clips"][0], d / "foto.png"), (abierto["clips"][0], d / "cancion.mp4"),
                           (abierto["clips"][1], corto), (abierto["audios"][0], d / "foto.png"),
                           (abierto["capas"][0], videos["clip.mp4"]), (abierto["clips"][0], d / "no_existe.mp4")):
        falla(edicion.reenlazar, abierto, elemento["id"], str(ruta))  # otro tipo, sin imagen, más corto, una capa…
    assert "falta" not in edicion.reenlazar(abierto, abierto["audios"][0]["id"], str(d / "musica.wav"))["audios"][0]
    shutil.copy(d / "musica.wav", d / "perdida.wav")  # el USB vuelve: al abrir ya no falta
    assert "falta" not in edicion.abrir(perdidos)["audios"][0]
    (d / "perdida.wav").write_bytes(b"")  # vacío (copia o sincronización a medias): falta, no impide abrir
    assert edicion.abrir(perdidos)["audios"][0]["falta"] is True

    # Un proyecto ajeno: JSON roto, NaN, enorme o con archivos que no son lo que dicen no se abre
    ajeno = edicion.nueva_carpeta("ajeno")
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    (d / "secreto.mp4").write_bytes(secreto.read_bytes())
    for texto in ('{"clips": [', "[" * 100_000, '{"fps": NaN}', '{"fps": Infinity}', b"\xff\xfe{}", "",
                  json.dumps({**datos, "clips": [{**datos["clips"][0], "archivo": str(d / "secreto.mp4")}]}),
                  json.dumps({**datos, "audios": [{**datos["audios"][0], "archivo": str(d / "secreto.mp4")}]}),
                  json.dumps({**datos, "clips": [{**datos["clips"][0], "archivo": r"\\srv\s\v.mp4"}]}),
                  json.dumps({**datos, "clips": [datos["clips"][0]] * 100_000})):
        (ajeno / "proyecto.json").write_bytes(texto if isinstance(texto, bytes) else texto.encode("utf-8"))
        falla(edicion.abrir, ajeno)
    with open(ajeno / "proyecto.json", "w", encoding="utf-8") as f:  # más de 8 MB aunque sea JSON válido
        f.write('{"nombre": "' + "x" * (9 * 1024 ** 2) + '"}')
    falla(edicion.abrir, ajeno)
    assert sorted(x["nombre"] for x in edicion.listar()) == ["Perdidos", "Real"]  # el roto no impide ver los demás

    # ---------- Capas de video (Grabarte): tu cara encima del video ----------
    def cara(**c):
        return {"tipo": "video", "archivo": r"C:\grabaciones\yo.mp4", "desde": 1, "hasta": 4, "duracion_archivo": 5,
                "inicio": 2, "x": 700, "y": 1400, "ancho": 300, "alto": 300, **c}
    p = edicion.validar({"capas": [cara(onclick="x", rotacion=45)], "otra": 1})
    capa = p["capas"][0]
    assert capa["duracion"] == 3 and "onclick" not in capa and "rotacion" not in capa  # lo que sobra se quita
    assert (capa["forma"], capa["borde"], capa["grosor_borde"], capa["volumen"], capa["silencio"]) == (
        "circulo", edicion.BORDE, 0, 1, False)  # lo que falta, por defecto
    assert edicion.validar(p) == p and edicion.validar(json.loads(json.dumps(p))) == p
    assert cerca(edicion.duracion_total(p), 5) and [c["id"] for c in edicion.capas_en(p, 4.9)] == [capa["id"]]
    assert edicion.validar({"capas": [cara(duracion=99)]})["capas"][0]["duracion"] == 3  # siempre hasta - desde
    assert edicion.validar({"capas": [cara(ancho=9000)]})["capas"][0]["ancho"] == 2 * 1080  # tope de las capas
    assert edicion.validar({"capas": [cara(falta=True)]})["capas"][0]["falta"] is True
    for malo in (cara(forma="estrella"), cara(grosor_borde=201), cara(volumen=3), cara(borde="rojo"),
                 cara(archivo=r"\\atacante.example\s\yo.mp4"), cara(archivo="yo.mp4"), cara(archivo=r"C:\yo.png"),
                 cara(archivo=r"C:\a\..\yo.mp4"), cara(hasta=6), cara(desde=4, hasta=4.05), cara(silencio="no"),
                 cara(inicio=3599), cara(x=float("nan")), cara(falta="sí"), {**cara(), "archivo": None}):
        falla(edicion.validar, {"capas": [malo]})
    falla(edicion.validar, {"capas": [cara()] * (edicion.MAX_VIDEOS + 1)})
    # «Bajar la música» viene puesta en los videos nuevos; un proyecto de antes (sin la clave) suena como siempre
    assert edicion.nuevo()["bajar_musica"] is True and edicion.validar({})["bajar_musica"] is False
    assert edicion.validar({"bajar_musica": False})["bajar_musica"] is False
    assert edicion.validar(edicion.nuevo())["bajar_musica"] is True  # guardado y vuelto a abrir, se queda
    falla(edicion.validar, {"bajar_musica": "sí"})

    # Disposiciones de un clic: dentro del cuadro en los cuatro formatos, esquinas del 28 % del lado corto
    for formato, (ancho, alto) in video.FORMATOS.items():
        cajas = {cual: edicion.disposicion(formato, cual, "redondeado", "#FF4D8D") for cual in edicion.DISPOSICIONES}
        for cual, caja in cajas.items():
            assert 0 <= caja["x"] and 0 <= caja["y"] and caja["x"] + caja["ancho"] <= ancho, (formato, cual, caja)
            assert caja["y"] + caja["alto"] <= alto and caja["borde"] == "#FF4D8D", (formato, cual, caja)
            edicion.validar({"formato": formato, "capas": [cara(inicio=0, **caja)]})  # todas valen tal cual
        corto = min(ancho, alto)
        esquinas = [cajas[c] for c in ("sup_izq", "sup_der", "inf_izq", "inf_der")]
        assert all(c["ancho"] == c["alto"] == round(corto * 0.28) and c["forma"] == "redondeado" and c["grosor_borde"]
                   for c in esquinas)
        assert len({(c["x"], c["y"]) for c in esquinas}) == 4
        assert esquinas[0]["x"] == esquinas[2]["x"] < esquinas[1]["x"] and esquinas[0]["y"] < esquinas[2]["y"]
        assert cajas["completa"] == {"x": 0, "y": 0, "ancho": ancho, "alto": alto, "forma": "rectangulo",
                                     "borde": "#FF4D8D", "grosor_borde": 0}
        mitad = cajas["dividida"]
        if ancho > alto:  # 16:9: lado a lado (a la derecha)
            assert (mitad["x"], mitad["y"], mitad["ancho"], mitad["alto"]) == (ancho // 2, 0, ancho // 2, alto)
        else:  # 9:16, 1:1 y 4:5: arriba y abajo
            assert (mitad["x"], mitad["y"], mitad["ancho"], mitad["alto"]) == (0, alto // 2, ancho, alto // 2)
        # Y el video principal va a la otra mitad (a la izquierda o arriba); movida o de otro tamaño, ya no se divide
        libre = edicion.otra_mitad(formato, {"tipo": "video", **mitad})
        assert libre == ({"x": 0, "y": 0, "ancho": ancho // 2, "alto": alto} if ancho > alto else
                         {"x": 0, "y": 0, "ancho": ancho, "alto": alto // 2}), (formato, libre)
        assert edicion.otra_mitad(formato, {"tipo": "video", **mitad, "x": mitad["x"] + 1}) is None
        assert edicion.otra_mitad(formato, {"tipo": "video", **esquinas[0]}) is None
    assert edicion.disposicion("9:16", "inf_der")["y"] < 1920 - 302 - 100  # lejos de los textos de abajo de TikTok
    for malo in (("21:9", "inf_der"), ("9:16", "centro"), ("9:16", "inf_der", "estrella"), ("9:16", "completa",
                                                                                              "circulo", "azul")):
        falla(edicion.disposicion, *malo)

    # Una grabación al proyecto: con imagen, capa de video en su sitio; solo voz, un audio «voz»
    voz = d / "voz.m4a"
    video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=1.5", "-c:a", "aac", voz)
    base = edicion.anadir_medio(edicion.nuevo(formato="16:9"), str(videos["clip.mp4"]))
    q = edicion.anadir_grabacion(base, str(videos["clip.mp4"]), 0.5, "sup_izq", "circulo", "#00E5FF")
    capa = q["capas"][-1]
    assert capa["tipo"] == "video" and capa["archivo"] == str(videos["clip.mp4"].resolve()) and capa["inicio"] == 0.5
    assert abs(capa["hasta"] - 2) < 0.05 and capa["desde"] == 0 and capa["borde"] == "#00E5FF"
    assert {k: capa[k] for k in ("x", "y", "ancho", "alto", "forma")} == {
        k: edicion.disposicion("16:9", "sup_izq")[k] for k in ("x", "y", "ancho", "alto", "forma")}
    assert base == edicion.validar(base) and not base["capas"]  # no toca el que recibe
    q = edicion.anadir_grabacion(q, str(voz), 1)
    assert q["audios"][-1]["tipo"] == "voz" and q["audios"][-1]["inicio"] == 1 and len(q["capas"]) == 1
    # `desde`: lo grabado antes de que arrancara el video del editor no se usa (la capa empieza igual en `inicio`)
    recortada = edicion.anadir_grabacion(base, str(videos["clip.mp4"]), 0.5, desde=0.8)["capas"][-1]
    assert (recortada["desde"], recortada["inicio"]) == (0.8, 0.5) and cerca(recortada["hasta"], capa["hasta"])
    assert cerca(recortada["duracion"], capa["hasta"] - 0.8)
    voz_recortada = edicion.anadir_grabacion(base, str(voz), 1, desde=0.3)["audios"][-1]
    assert voz_recortada["desde"] == 0.3 and cerca(voz_recortada["hasta"], 1.5)
    casi = edicion.anadir_grabacion(base, str(videos["clip.mp4"]), 0, desde=99)["capas"][-1]  # nunca todo el archivo
    assert edicion.MIN_CLIP <= casi["hasta"] - casi["desde"] < edicion.MIN_CLIP + 0.003, casi
    assert abs(casi["hasta"] - capa["hasta"]) < 0.002, casi
    falla(edicion.anadir_grabacion, base, str(videos["clip.mp4"]), 0, "inf_der", "circulo", edicion.BORDE, -1)
    tarde = edicion.anadir_grabacion(base, str(videos["clip.mp4"]), edicion.MAX_DURACION - 1)
    assert cerca(tarde["capas"][-1]["hasta"], 1) and cerca(edicion.duracion_total(tarde), edicion.MAX_DURACION)
    for malo in (str(secreto), r"\\atacante.example\s\yo.mp4", str(d / "foto.png"), str(d / "no_existe.mp4")):
        falla(edicion.anadir_grabacion, base, malo, 0)
    falla(edicion.anadir_grabacion, base, str(videos["clip.mp4"]), edicion.MAX_DURACION)  # no cabe
    falla(edicion.anadir_grabacion, base, str(videos["clip.mp4"]), 0, "centro")
    # Recortar la capa: se queda en su sitio de la línea de tiempo (como un audio); borrarla
    recortada = edicion.recortar(q, capa["id"], 0.5, 1.5)
    nueva = recortada["capas"][-1]
    assert (nueva["desde"], nueva["hasta"], nueva["inicio"], nueva["duracion"]) == (0.5, 1.5, 1, 1)
    falla(edicion.recortar, edicion.validar({**q, "capas": q["capas"] + [{"tipo": "texto", "id": "t9"}]}), "t9", 0, 1)
    assert not edicion.borrar(q, capa["id"])["capas"]
    # Un archivo de cámara que ya no está: «falta» al abrir, volver a enlazar lo arregla
    shutil.copy(videos["clip.mp4"], d / "mi_cara.mp4")
    con_cara = edicion.anadir_grabacion(edicion.nuevo("Con cara"), str(d / "mi_cara.mp4"), 0)
    guardada = edicion.nueva_carpeta("con cara")
    edicion.guardar(con_cara, guardada)
    (d / "mi_cara.mp4").unlink()
    abierta = edicion.abrir(guardada)
    assert abierta["capas"][0]["falta"] is True
    arreglada = edicion.reenlazar(abierta, abierta["capas"][0]["id"], str(videos["clip.mp4"]))
    assert "falta" not in arreglada["capas"][0]
    assert arreglada["capas"][0]["archivo"] == str(videos["clip.mp4"].resolve())
    falla(edicion.reenlazar, abierta, abierta["capas"][0]["id"], str(voz))  # sin imagen no vale para una cámara

    # ---------- Recuperar lo que no se guardó ----------
    shutil.rmtree(edicion.CARPETA)
    assert edicion.sin_guardar() == []
    # La copia automática se escribe y se abre aparte de proyecto.json
    guardada = edicion.nueva_carpeta("con copia")
    edicion.guardar(base, guardada)
    assert edicion.sin_guardar() == []  # guardado y sin copia: nada que recuperar
    cambiado = {**base, "nombre": "Con copia"}
    assert edicion.guardar(cambiado, guardada, edicion.AUTOGUARDADO).name == edicion.AUTOGUARDADO
    os.utime(guardada / "proyecto.json", (time.time() - 60,) * 2)
    assert edicion.abrir(guardada, edicion.AUTOGUARDADO)["nombre"] == "Con copia"
    assert edicion.abrir(guardada)["nombre"] == base["nombre"]
    [h] = edicion.sin_guardar()
    assert (h["carpeta"], h["nombre"], h["copia"]) == (guardada, "Con copia", True)
    os.utime(guardada / edicion.AUTOGUARDADO, (time.time() - 120,) * 2)  # guardado después: la copia ya no vale
    assert edicion.sin_guardar() == []
    (guardada / edicion.AUTOGUARDADO).write_text("{roto", encoding="utf-8")
    os.utime(guardada / edicion.AUTOGUARDADO, None)
    assert edicion.sin_guardar() == []  # una copia rota no se ofrece: lo guardado sigue ahí
    # Un video que se cerró sin guardar antes de que hubiera copia (como el del usuario): sus grabaciones y voces
    perdido = edicion.nueva_carpeta("mi video")
    (perdido / "grabaciones").mkdir()
    (perdido / "voces").mkdir()
    toma1, toma2 = perdido / "grabaciones" / "grabacion-1.mp4", perdido / "grabaciones" / "grabacion-2.m4a"
    shutil.copy(videos["clip.mp4"], toma1)
    shutil.copy(voz, toma2)
    shutil.copy(voz, perdido / "voces" / "voz-1.m4a")
    (perdido / "voces" / "vacia.mp3").write_bytes(b"")  # una a medias no cuenta
    (perdido / "grabaciones" / "notas.txt").write_text("x", encoding="utf-8")  # ni lo que no es audio o video
    for n, f in enumerate((toma1, toma2, perdido / "voces" / "voz-1.m4a")):
        os.utime(f, (time.time() - 30 + n,) * 2)
    [h] = edicion.sin_guardar()
    assert (h["carpeta"], h["nombre"], h["copia"], h["grabaciones"], h["voces"], h["fotos"]) == \
        (perdido, "mi video", False, 2, 1, 0)
    # Las fotos encima del video sí se copian a imagenes/: también vuelven, centradas y sin deformar
    shutil.copy(d / "foto.png", perdido / "imagenes" / "imagen-1.png")
    (perdido / "imagenes" / "imagen-2.png").write_bytes(b"no es una foto")
    os.utime(perdido / "imagenes" / "imagen-1.png", (time.time() - 40,) * 2)
    assert edicion.sin_guardar()[0]["fotos"] == 2
    r = edicion.recuperar(perdido)
    p = r["proyecto"]
    assert len(r["errores"]) == 1 and r["errores"][0].startswith("imagen-2.png: ")
    (perdido / "imagenes" / "imagen-2.png").unlink()
    assert p["nombre"] == "mi video (recuperado)" and p["formato"] == "9:16"
    cara, foto = p["capas"]
    assert (foto["tipo"], foto["archivo"], foto["inicio"], foto["duracion"]) == ("imagen", "imagen-1.png", 0,
                                                                               edicion.IMAGEN)
    ancho, alto = video.FORMATOS["9:16"]
    assert foto["ancho"] == foto["alto"] == round(ancho * 0.6) and foto["x"] == round((ancho - foto["ancho"]) / 2)
    assert foto["y"] == round((alto - foto["alto"]) / 2)
    assert cara["tipo"] == "video" and cara["archivo"] == str(toma1.resolve()) and cara["inicio"] == 0
    assert [(a["tipo"], a["archivo"]) for a in p["audios"]] == [("voz", str(toma2.resolve())),
                                                                ("voz", str((perdido / "voces" / "voz-1.m4a").resolve()))]
    a1, a2 = p["audios"]
    assert a1["inicio"] == 0 and cerca(a2["inicio"], a1["hasta"] - a1["desde"])  # una detrás de otra, sin pisarse
    # Una grabación rota no tumba el resto: se dice cuál y por qué
    (perdido / "grabaciones" / "grabacion-3.mp4").write_bytes(b"no es un video")
    r = edicion.recuperar(perdido)
    assert len(r["errores"]) == 1 and r["errores"][0].startswith("grabacion-3.mp4: ")
    assert len(r["proyecto"]["capas"]) == 2 and len(r["proyecto"]["audios"]) == 2
    # Descartado a propósito: no se vuelve a ofrecer (y nada se borra)
    (perdido / edicion.NO_RECUPERAR).touch()
    assert edicion.sin_guardar() == [] and toma1.is_file()
    # ... pero esa marca vale solo para lo que había entonces: una voz nueva (días después, otro cierre de golpe), sí
    os.utime(perdido / edicion.NO_RECUPERAR, (time.time() - 10,) * 2)
    shutil.copy(voz, perdido / "voces" / "voz-2.m4a")
    os.utime(perdido / "voces" / "voz-2.m4a", (time.time() - 5,) * 2)
    [h] = edicion.sin_guardar()
    assert h["carpeta"] == perdido and h["voces"] == 2
    # Y una copia automática más nueva que la marca, también (la de antes, no)
    marcada = edicion.nueva_carpeta("marcada")
    edicion.guardar(base, marcada)
    edicion.guardar({**base, "nombre": "Marcada"}, marcada, edicion.AUTOGUARDADO)
    (marcada / edicion.NO_RECUPERAR).touch()
    for archivo, hace in (("proyecto.json", 60), (edicion.AUTOGUARDADO, 30), (edicion.NO_RECUPERAR, 20)):
        os.utime(marcada / archivo, (time.time() - hace,) * 2)
    assert [h["carpeta"] for h in edicion.sin_guardar()] == [perdido]
    edicion.guardar({**base, "nombre": "Marcada"}, marcada, edicion.AUTOGUARDADO)
    assert [(h["carpeta"], h["copia"]) for h in edicion.sin_guardar()] == [(marcada, True), (perdido, False)]
    falla(edicion.recuperar, r"\\atacante.example\s\video")

print("Pruebas del editor de video (modelo) pasadas.")
