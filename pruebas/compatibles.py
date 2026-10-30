"""Videos que se ven en todas partes y shorts sin voz, sin red (las IA son falsas). Cada video que hace el estudio sale
en H.264 estándar (yuv420p, rango «tv», BT.709) aunque la imagen sea un JPEG: salía «yuvj420p(pc, bt470bg)» y el
reproductor de la app lo enseñaba en negro. Las imágenes, con la extensión de su formato. El reproductor dice por qué
no puede reproducir un archivo. La narración que escribe el usuario va tal cual y a su tiempo. Cada short de un video
sin voz lleva su propio título, sin una nota «/100» que ahí no significa nada. python -m pruebas.compatibles"""
import base64
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from motor import claves, desde_prompt, edicion, ia, idioma, memoria, nubes, render_edicion, shorts, video  # noqa: E402
from ui.comun import Reproductor  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
tmp = Path(tempfile.mkdtemp(prefix="rafaga-compatibles-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
memoria.ARCHIVO, edicion.CARPETA = tmp / "memoria.json", tmp / "ediciones"


def hacer(nombre, *args) -> Path:
    video.ffmpeg(*args, tmp / nombre)
    return tmp / nombre


def color(archivo: Path) -> str:
    """Lo que dice ffmpeg -i (como ffprobe) del color del video: p. ej. «yuv420p(tv, bt709, progressive)»."""
    return re.search(r"Video: h264 .*?, (\w+\(.*?\))", video._leer_ffmpeg("-i", archivo))[1]


def media(archivo: Path, segundo: float = 0.5) -> np.ndarray:
    """El color medio (RGB) del fotograma de ese segundo, descodificado como lo haría un reproductor."""
    w, h = map(int, re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", video._leer_ffmpeg("-i", archivo)).groups())
    datos = subprocess.run([video.FFMPEG, "-v", "error", "-ss", str(segundo), "-i", str(archivo), "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(datos, np.uint8).reshape(h, w, 3).mean(axis=(0, 1))


# ---------- 1. Cada video, estándar aunque la imagen sea JPEG (como video_final_imagen_00.png del dueño) ----------
AZUL = (40, 60, 80)  # oscuro: con el rango mal dicho se ve más oscuro o más claro de lo que es
jpeg = hacer("escena.png", "-f", "lavfi", "-i", "color=c=0x283C50:s=576x1024", "-frames:v", "1", "-c:v", "mjpeg",
             "-f", "image2")
assert jpeg.read_bytes()[:3] == b"\xff\xd8\xff"  # JPEG con nombre .png: lo que daban las IA de imágenes
voz = hacer("voz.wav", "-f", "lavfi", "-i", "sine=frequency=300:duration=1")
clip_pc = hacer("clip_pc.mp4", "-f", "lavfi", "-i", "color=c=0x283C50:s=320x568:r=30:d=1", "-c:v", "libx264",
                "-pix_fmt", "yuvj420p")
assert color(clip_pc).startswith("yuvj420p(pc"), color(clip_pc)  # un clip de IA en rango completo
partes = [video.escena_de_imagen(jpeg, voz, "9:16", [], tmp / "escena_0.mp4", 0),
          video.escena_de_clip(clip_pc, voz, "9:16", [], tmp / "escena_1.mp4")]
montado = video.unir(partes, tmp / "montado.mp4")  # sin volver a codificar: vale lo de cada escena
mudo = video.segmento_mudo(jpeg, 1.0, "9:16", tmp / "mudo.mp4", 1)
hechos = [*partes, montado, mudo, video.segmento_mudo(jpeg, 1.0, "9:16", tmp / "mudo_clip.mp4", 0, clip_pc),
          video.cierre(montado, "OFERTA", "9:16", tmp / "anuncio.mp4", producto=jpeg),
          video.recortar(clip_pc, 0, 1, "9:16", "recortar", [], tmp / "short.mp4"),
          video.con_cancion(mudo, voz, "9:16", [], tmp / "musical.mp4")]
p = edicion.anadir_medio(edicion.nuevo("Foto"), str(jpeg))  # el editor de video, con una foto JPEG
p["clips"][0]["hasta"] = 1
hechos.append(render_edicion.exportar(p, edicion.nueva_carpeta("Foto"), tmp / "exportado.mp4", "720p"))
for hecho in hechos:
    assert color(hecho).startswith("yuv420p(tv, bt709"), f"{hecho.name}: {color(hecho)}"
for hecho in (partes[0], montado, mudo, hechos[-1]):  # y el color es el de la imagen (sin oscurecer ni aclarar)
    assert abs(media(hecho) - AZUL).max() < 6, (hecho.name, media(hecho))
assert abs(media(partes[1]) - AZUL).max() < 6, media(partes[1])  # también desde el clip de rango completo
print("Videos estándar (yuv420p, tv, BT.709) desde JPEG pasados.")

# ---------- 2. Cada imagen con la extensión de su formato ----------
datos_jpeg = jpeg.read_bytes()
png = ia.guardar_imagen(datos_jpeg, tmp / "convertida.png")
assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and QImage(str(png)).size().toTuple() == (576, 1024)
assert ia.guardar_imagen(png.read_bytes(), tmp / "igual.png").read_bytes() == png.read_bytes()  # ya lo era: igual
assert ia.guardar_imagen(datos_jpeg, tmp / "foto.jpg").read_bytes() == datos_jpeg
assert ia.guardar_imagen(png.read_bytes(), tmp / "a.jpg").read_bytes()[:3] == b"\xff\xd8\xff"
try:
    ia.guardar_imagen(b"\xff\xd8\xffroto", tmp / "rota.png")
    raise AssertionError("debió fallar")
except RuntimeError:
    assert not (tmp / "rota.png").exists()
# Lo que da la IA de imágenes (Pollinations da JPEG) llega a la escena como PNG de verdad
rotar_real = nubes.rotar
nubes.rotar = lambda uso, tareas, que_fue=None: (datos_jpeg, "pollinations")
try:
    hecha = ia.imagen("una cocina", 576, 1024, tmp / "video_final_imagen_00.png")
    assert hecha.read_bytes()[:4] == b"\x89PNG"
finally:
    nubes.rotar = rotar_real
print("Imágenes con la extensión de su formato pasadas.")

# ---------- 3. La narración que escribe el usuario, tal cual; y la duración, la pedida ----------
# El pedido del dueño (recortado): cinco «Guion / Voz en Off» entre comillas; «Narración: alegre» no es texto a decir
LINEAS = ["¿Quieres impresionar a todos con una cena de restaurante? Hoy preparamos una clásica y crujiente Pechuga "
          "Cordon Bleu.",
          "Abrimos la pechuga en libro, rellenamos con una generosa loncha de jamón y queso suizo derretible, y la "
          "enrollamos con firmeza.",
          "Pasamos el rollo por harina, luego por huevo batido, y aseguramos una costra perfecta cubriéndolo con pan "
          "rallado.",
          "Llevamos a sartén con aceite caliente hasta que quede dorada, crujiente y doradita por fuera.",
          "Cortamos al medio y... ¡mira ese queso fundido! Y mas rico todavia."]
ETIQUETAS = ["Guion / Voz en Off: \"{}\"", "**Guion / Voz en Off:** \"{}\"", "Narración: «{}»", "- Voz en off: “{}”",
             "Voice-over (Sarah): \"{}\""]  # las formas de escribirlo (comillas rectas, españolas, inglesas)
PEDIDO = ("Detalles Generales del Video\nDuración: 30 segundos\nNarración: alegre y cercana\n"
          "Estructura y Guion del Video (Segundo a Segundo)\n"
          + "".join(f"Escena {i}: paso {i} (0:00 - 0:05)\n{forma.format(x)}\nImagen a generar (Prompt de video):\n"
                    f"Macro cinematic shot number {i}.\n" for i, (forma, x) in enumerate(zip(ETIQUETAS, LINEAS), 1)))
assert desde_prompt.narracion_del_usuario(PEDIDO) == LINEAS, desde_prompt.narracion_del_usuario(PEDIDO)
assert desde_prompt.narracion_del_usuario("Un video de gatos.\nNarración: divertida\nVoz en off: masculina") == []
# Con un número delante, una acotación detrás o comillas simples: antes esa línea se perdía sin decir nada
assert desde_prompt.narracion_del_usuario("1. Voz en off: \"Hola (bajito).\" (tono alegre)\n2) Voice-over: 'It's "
                                          "here.'\nNarración: \"Fin.\"") == ["Hola (bajito).", "It's here.", "Fin."]
assert desde_prompt.palabras_por_segundo("eleven:abc") == 2.6 and desde_prompt.palabras_por_segundo("es-DO-x") == 2.0

# La velocidad de la voz llega a Edge («+20%») y a ElevenLabs (voice_settings.speed); 1 no cambia nada
comunicados, mandados = [], []


class EdgeFalso:
    def __init__(self, texto, voz, **opciones):
        comunicados.append(opciones)

    async def stream(self):
        return
        yield


reales = desde_prompt.edge_tts.Communicate, ia.httpx.post
desde_prompt.edge_tts.Communicate = EdgeFalso
ia.httpx.post = lambda url, **k: mandados.append(k["json"]) or ia.httpx.Response(200, json={"audio_base64": ""})
try:
    desde_prompt.narrar("Hola", "es-DO-EmilioNeural", tmp / "v.mp3", 1.2)
    desde_prompt.narrar("Hola", "es-DO-EmilioNeural", tmp / "v.mp3")
    assert [c["rate"] for c in comunicados] == ["+20%", "+0%"], comunicados
    claves.guardar({"proveedor": "elevenlabs", "clave": "sk_prueba", "usos": ["voz"]})
    desde_prompt.narrar("Hola", "eleven:sarah", tmp / "v.mp3", 1.15)
    desde_prompt.narrar("Hola", "eleven:sarah", tmp / "v.mp3")
    assert mandados[0]["voice_settings"] == {"speed": 1.15} and "voice_settings" not in mandados[1], mandados
finally:
    desde_prompt.edge_tts.Communicate, ia.httpx.post = reales
    claves.borrar("elevenlabs")

pedidos, largo, velocidades = [], [31.0], []
# La IA lo resume (como pasó: 82 palabras quedaron en 62) y en 4 escenas en vez de 5
RESUMIDO = {"titulo": "Pechuga Cordon Bleu", "descripcion": "d", "hashtags": ["#receta"], "estilo_visual": "photo",
            "escenas": [{"narracion": "¿Quieres impresionar con una cena?", "imagen": f"plano {i}"} for i in range(4)]}
reales = (ia.texto_json, ia.imagen, ia.video_desde_imagen, desde_prompt.narrar, video.duracion,
          video.escena_de_imagen, video.unir, desde_prompt.PROYECTOS)
ia.texto_json = lambda instrucciones, pedido, esquema, *a, **k: pedidos.append(pedido) or json.loads(json.dumps(RESUMIDO))
ia.imagen = lambda prompt, w, h, d, *a, **k: d
ia.video_desde_imagen = lambda *a, **k: None
desde_prompt.narrar = lambda texto, voz, destino, velocidad=1.0: velocidades.append(velocidad) or []
video.duracion = lambda archivo: largo[0]
video.escena_de_imagen = lambda img, audio, f, palabras, escena, i: escena
video.unir = lambda partes, d: d
reales_animado = desde_prompt.proveedor_voz, desde_prompt.clips_hablados
try:
    desde_prompt.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    r = desde_prompt.generar(PEDIDO, segundos=30, voz="eleven:sarah")
    guion = json.loads((Path(r["carpeta"]) / "guion.json").read_text(encoding="utf-8"))
    assert [e["narracion"] for e in guion["escenas"]] == LINEAS, guion  # ni resumida ni «corregida» («mas»)
    assert [e["imagen"] for e in guion["escenas"]] == ["plano 0", "plano 0", "plano 1", "plano 2", "plano 3"]
    assert "La narración ya la escribió el usuario" in pedidos[-1] and all(x in pedidos[-1] for x in LINEAS)
    assert "5 escenas (una por cada línea" in pedidos[-1] and "palabras de narración" not in pedidos[-1]
    assert not any("se acortó" in a or "Tu narración" in a for a in r["avisos"]), r["avisos"]  # 31 s de 30: bien
    assert velocidades == [1.0] * 5, velocidades  # con ElevenLabs (2,6 palabras/s) cabe: la voz, a su ritmo
    # Con Edge (la gratis, 2 palabras/s) sus 84 palabras serían unos 43 s: la voz va un 20 % más rápida
    largo[0], velocidades[:] = 41.0, []  # y aun así no cabe: se dice, sin tocar su texto
    desde_prompt.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    r = desde_prompt.generar(PEDIDO, segundos=30)
    assert velocidades == [1.2] * 5, velocidades
    assert "Tu narración no cabía en los 30 s pedidos: la voz va un 20 % más rápida." in r["avisos"], r["avisos"]
    assert any("Tu narración se usó tal cual la escribiste: el video dura 41 s y pediste 30 s." == a
               for a in r["avisos"]), r["avisos"]
    # Animado: cada escena es un clip de pago de 8 s; a 30 s caben 4 y se dice qué línea se quitó y cuál es larga
    desde_prompt.proveedor_voz, desde_prompt.clips_hablados = lambda: "gemini", lambda *a, **k: {}
    desde_prompt.PROYECTOS, velocidades[:] = Path(tempfile.mkdtemp(dir=tmp)), []
    r = desde_prompt.generar(PEDIDO, segundos=30, animado=True)
    guion = json.loads((Path(r["carpeta"]) / "guion.json").read_text(encoding="utf-8"))
    assert [e["narracion"] for e in guion["escenas"]] == LINEAS[:3] + LINEAS[4:], guion
    assert "Tu narración tiene 5 líneas y en este video caben 4 escenas: se quitaron las líneas del medio que " \
           "sobraban." in r["avisos"], r["avisos"]
    largas = [a for a in r["avisos"] if a.startswith("La línea ")]
    assert largas == ["La línea 2 de tu narración tiene 21 palabras: en una escena animada de 8 s puede no caber "
                      "entera."], r["avisos"]
    assert not any("tal cual" in a or "más rápida" in a for a in r["avisos"]) and velocidades == [1.0] * 4, r["avisos"]
    # Sin narración escrita: la IA escribe para la voz elegida (ElevenLabs habla más rápido que Edge)
    desde_prompt.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    desde_prompt.generar("Un video de gatos", segundos=30, voz="eleven:sarah")
    assert "(~78 palabras de narración), unas 5 escenas" in pedidos[-1], pedidos[-1]
    desde_prompt.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    desde_prompt.generar("Un video de gatos", segundos=30)
    assert "(~60 palabras de narración), unas 5 escenas" in pedidos[-1], pedidos[-1]
finally:
    (ia.texto_json, ia.imagen, ia.video_desde_imagen, desde_prompt.narrar, video.duracion, video.escena_de_imagen,
     video.unir, desde_prompt.PROYECTOS) = reales
    desde_prompt.proveedor_voz, desde_prompt.clips_hablados = reales_animado
print("Narración del usuario tal cual y duración pedida pasadas.")

# ---------- 4. Shorts de un video sin voz: un título para cada uno y sin «/100» ----------
TITULO = "No cocines pechugas de pollo hasta que veas esta receta! Una receta de cena sencilla y deliciosa!"
cocina = hacer("cocina.mp4", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=10:d=30,drawbox=x=0:y=0:w=iw:h=ih:"
               "color=white:t=fill:enable='lt(mod(t,6),3)'", "-f", "lavfi", "-i", "sine=duration=30",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest")
vistos, recortes = [], []


def claude(c, instrucciones, pedido, esquema, rapido=False):
    """Claude falso: ve los fotogramas (y repasa la ortografía sin cambiar nada)."""
    if instrucciones == ia.ORTOGRAFIA:
        return {"textos": json.loads(pedido)["textos"]}
    assert instrucciones.startswith(shorts.INSTRUCCIONES_SIN_VOZ) and esquema is shorts.ESQUEMA_SIN_VOZ
    vistos.append((c["proveedor"], pedido))
    momentos = sum(b["type"] == "text" and b["text"].startswith("Momento") for b in pedido)
    return {"momentos": [{"titulo": f"Paso {n}: se dora el pollo", "descripcion": f"Lo que pasa en el paso {n}.",
                          "hashtags": ["#pollo", f"#paso{n}"]} for n in range(1, momentos + 1)]}


reales = shorts.descargar, video.recortar, ia.transcribir, ia._pedir, ia.texto_json, shorts.PROYECTOS
shorts.descargar = lambda url, carpeta, progreso: (cocina, TITULO)
video.recortar = lambda original, ini, fin, formato, modo, palabras, destino: recortes.append(palabras) or destino
ia.transcribir = lambda audio, progreso=None: []
ia._pedir = claude
try:
    claves.guardar({"proveedor": "anthropic", "clave": "sk-ant-prueba", "usos": ["texto"]})
    claves.elegir_por_defecto("texto", "anthropic")
    shorts.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    r = shorts.generar("https://www.youtube.com/watch?v=OYVojP3fg2s", cantidad=3, dur_min=5, dur_max=10)
    res = r["resultados"]
    assert len(res) == 3 and [c["titulo"] for c in res] == [f"Paso {n}: se dora el pollo" for n in (1, 2, 3)], res
    assert all("puntuacion" not in c and c["hashtags"][0] == "#pollo" and c["descripcion"] for c in res), res
    assert "(primero, los que más tienen)" in r["avisos"][0] and len(r["avisos"]) == 1, r["avisos"]
    imagenes = [b for b in vistos[0][1] if b["type"] == "image"]
    assert len(imagenes) == 9 and TITULO in vistos[0][1][0]["text"]  # 3 fotogramas de cada momento, y el título
    assert all(base64.b64decode(b["source"]["data"])[:3] == b"\xff\xd8\xff" for b in imagenes)
    assert QImage.fromData(base64.b64decode(imagenes[0]["source"]["data"])).width() <= 512
    # Claude sin saldo: los shorts salen igual, numerados en el orden de la lista y de sus archivos (short_01.mp4 es
    # el «Momento 1»), con el tema del video en vez de su título tal cual, y se dice por qué
    ia._pedir = lambda c, instrucciones, *a, **k: claude(c, instrucciones, *a, **k) \
        if instrucciones == ia.ORTOGRAFIA else (_ for _ in ()).throw(ia.SinServicio("402: sin saldo"))
    ia.texto_json = lambda instrucciones, pedido, esquema, *a, **k: {
        "descripcion": "Pechugas de pollo para una cena sencilla.", "hashtags": ["#pollo", "#receta", "#cena"],
        "tema": "Pechugas de pollo jugosas"}
    shorts.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    r = shorts.generar("https://www.youtube.com/watch?v=OYVojP3fg2s", cantidad=3, dur_min=5, dur_max=10)
    assert any("Claude no pudo ver los momentos (402: sin saldo)" in a for a in r["avisos"]), r["avisos"]
    res = r["resultados"]
    assert [c["titulo"] for c in res] == [f"Momento {n} de 3: Pechugas de pollo jugosas" for n in (1, 2, 3)], res
    assert [Path(c["archivo"]).name for c in res] == ["short_01.mp4", "short_02.mp4", "short_03.mp4"]
    assert all(c["descripcion"] == "Pechugas de pollo para una cena sencilla." and c["hashtags"] ==
               ["#pollo", "#receta", "#cena"] and "puntuacion" not in c for c in res)
    # Gemini también ve imágenes (por su API compatible con OpenAI): los fotogramas van como «image_url»
    claves.borrar("anthropic")
    claves.guardar({"proveedor": "gemini", "clave": "AIza-prueba", "usos": ["texto"]})
    claves.elegir_por_defecto("texto", "gemini")
    ia._pedir = claude
    shorts.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    r = shorts.generar("https://www.youtube.com/watch?v=OYVojP3fg2s", cantidad=3, dur_min=5, dur_max=10)
    assert [c["titulo"] for c in r["resultados"]] == [f"Paso {n}: se dora el pollo" for n in (1, 2, 3)], r
    proveedor, pedido = vistos[-1]
    partes = [b for b in pedido if b["type"] == "image_url"]
    assert proveedor == "gemini" and len(partes) == 9 and not any(b["type"] == "image" for b in pedido), pedido[:2]
    assert all(b["image_url"]["url"].startswith("data:image/jpeg;base64,") and base64.b64decode(
        b["image_url"]["url"].split(",", 1)[1])[:3] == b"\xff\xd8\xff" for b in partes)
    # Sin ninguna IA que responda: numerados, y la descripción es el título del video
    claves.borrar("gemini")
    ia.texto_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin red"))
    shorts.PROYECTOS = Path(tempfile.mkdtemp(dir=tmp))
    r = shorts.generar("https://www.youtube.com/watch?v=OYVojP3fg2s", cantidad=2, dur_min=5, dur_max=10)
    assert len({c["titulo"] for c in r["resultados"]}) == 2 and all(c["descripcion"] == TITULO and
                                                                 c["hashtags"] == [] for c in r["resultados"])
    assert len(vistos) == 2 and all(p == [] for p in recortes)  # se ve solo con quien puede; sin voz, sin subtítulos
finally:
    shorts.descargar, video.recortar, ia.transcribir, ia._pedir, ia.texto_json, shorts.PROYECTOS = reales
print("Shorts sin voz con su propio título pasados.")

# ---------- 5. El reproductor: sin «/100» en los shorts sin voz, y el error en lugar de la pantalla negra ----------
rep = Reproductor()
rep.sonido.setMuted(True)  # el dueño usa el PC mientras corren las pruebas: sin pitidos
CORTES = {"es": "Muchos cambios de escena", "en": idioma._textos("en")["Muchos cambios de escena"]}
for app_en, motivo in (("es", "es"), ("es", "en"), ("en", "es")):  # el motivo se guardó en el idioma de entonces
    os.environ["RAFAGA_IDIOMA"] = app_en
    idioma.actual.cache_clear()
    rep.mostrar({"formato": "9:16", "resultados": [
        {"archivo": str(montado), "titulo": "Paso 1", "descripcion": "", "hashtags": [], "inicio": 269.2, "fin": 327.0},
        {"archivo": str(montado), "titulo": "Con voz", "descripcion": "", "hashtags": [], "inicio": 12, "fin": 40,
         "puntuacion": 87},
        # como el proyecto del dueño: «11/100» y una hora en el título que no era la del tramo
        {"archivo": str(montado), "titulo": "Guardado antes · 5:03", "descripcion": "", "hashtags": [], "inicio": 12,
         "fin": 65.4, "puntuacion": 11, "motivo": CORTES[motivo]}]})
    assert rep.lista.item(0).text() == "1. Paso 1  ·  4:29  ·  58s", rep.lista.item(0).text()
    assert rep.lista.item(1).text() == "2. Con voz  ·  0:12  ·  28s  ·  87/100", rep.lista.item(1).text()
    assert rep.lista.item(2).text() == "3. Guardado antes  ·  0:12  ·  53s", (app_en, motivo, rep.lista.item(2).text())
rep.lista.setCurrentRow(2)
assert rep.info.toPlainText().startswith("Guardado antes\n"), rep.info.toPlainText()  # lo que se copia, igual
os.environ["RAFAGA_IDIOMA"] = "es"
idioma.actual.cache_clear()


def esperar(condicion, segundos=15):
    hasta = time.time() + segundos
    while not condicion() and time.time() < hasta:
        app.processEvents()
        time.sleep(0.02)
    return condicion()


assert not esperar(lambda: rep.vista.currentWidget() is rep.sin_video, 2)  # el video bueno se reproduce
# Un video de antes, en rango completo (yuvj420p): Qt lo descodifica sin error, pero se avisa debajo, sin taparlo
ANTERIOR = "Este video es de una versión anterior y en algunos equipos se ve negro aquí"
rep.mostrar({"avisos": ["Aviso del proyecto"], "resultados": [
    {"archivo": str(clip_pc), "titulo": "x", "descripcion": "", "hashtags": []},
    {"archivo": str(montado), "titulo": "y", "descripcion": "", "hashtags": []}]})
assert esperar(lambda: ANTERIOR in rep.avisos_txt.text()), rep.avisos_txt.text()
assert "Aviso del proyecto" in rep.avisos_txt.text() and rep.vista.currentWidget() is rep.pantalla
rep.lista.setCurrentRow(1)  # uno nuevo (rango «tv»): sin el aviso, aunque llegue algún cuadro del anterior
assert esperar(lambda: rep.player.position() > 300) and esperar(lambda: ANTERIOR not in rep.avisos_txt.text(), 1)
assert rep.avisos_txt.text() == "⚠️ Aviso del proyecto", rep.avisos_txt.text()
rep.lista.setCurrentRow(0)  # y otra vez el de antes, con el nuevo aún sonando
assert esperar(lambda: ANTERIOR in rep.avisos_txt.text()), rep.avisos_txt.text()
roto = tmp / "roto.mp4"
roto.write_bytes(b"esto no es un video" * 100)
for archivo, causa, carpeta in ((roto, "no entiende su formato", True),
                                (tmp / "borrado.mp4", "quizá se movió o se borró", False)):
    rep.mostrar({"resultados": [{"archivo": str(archivo), "titulo": "x", "descripcion": "", "hashtags": []}]})
    assert esperar(lambda: rep.vista.currentWidget() is rep.sin_video), archivo
    assert rep.sin_video.text().startswith("No se puede reproducir este video aquí") and causa in rep.sin_video.text(), \
        rep.sin_video.text()
    # si se borró, abrir la carpeta no lo reproduce: no se manda allí
    assert ("Prueba a abrirlo desde «Abrir carpeta»." in rep.sin_video.text()) == carpeta, rep.sin_video.text()
    rep._alternar()  # ▶ con el error a la vista: ni reproduce ni pasa a «Pausar»
    assert "Pausar" not in rep.play.text() and rep.player.playbackState() != rep.player.PlaybackState.PlayingState
rep.mostrar({"resultados": [{"archivo": str(montado), "titulo": "x", "descripcion": "", "hashtags": []}]})
assert rep.vista.currentWidget() is rep.pantalla  # otro resultado: vuelve la pantalla
rep.player.stop()
print("Reproductor: orden explicado y error a la vista pasados.")
