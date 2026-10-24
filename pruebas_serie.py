"""Pruebas de la serie animada, sin red ni claves: python pruebas_serie.py"""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from motor import claves, desde_prompt, diseno, edicion, herramientas, ia, serie, video  # noqa: E402

diseno.asegurar_qt()
app = QApplication.instance()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-serie-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # sin claves: nunca las del usuario
claves.elegir_por_defecto("video", "ninguno")  # nada de animar con IA (sería red)
serie.CARPETA, edicion.CARPETA = tmp / "series", tmp / "ediciones"


def falla(funcion, *args, error=ValueError, **kw):
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {funcion.__name__}{args!r:.200}")


# La IA, las imágenes y las voces, falsas
pedidos, imagenes, voces = [], [], []


def pensar(instrucciones, pedido, esquema):
    pedidos.append((instrucciones, pedido))
    if esquema is serie.ESQUEMA_SERIE:
        return {"titulo": "La IA eligió", "sinopsis": "Un guerrero busca a los traidores.", "personajes": [
            {"nombre": "Kaito", "descripcion": "young swordsman, blue haori", "personalidad": "Callado", "genero": "hombre"},
            {"nombre": "Yara", "descripcion": "archer, red scarf", "personalidad": "Valiente", "genero": "mujer"},
            {"nombre": "Brutus", "descripcion": "giant, iron mask", "personalidad": "Cruel", "genero": "hombre"},
            {"nombre": "Sobra", "descripcion": "x", "personalidad": "x", "genero": "otro"}]}
    return {"titulo": f"Capítulo de prueba {len(pedidos)}", "resumen": "Kaito encuentra a Yara.", "planos": [
        {"descripcion": "storm over a field", "personajes": [], "habla": "Narrador", "texto": "Llega la tormenta."},
        {"descripcion": "Kaito draws his sword", "personajes": ["kaito"], "habla": "Kaito", "texto": "Ya vienen."},
        {"descripcion": "Yara aims", "personajes": ["Yara", "Nadie"], "habla": "Yara", "texto": "Estoy lista."},
        {"descripcion": "extra", "personajes": [], "habla": "", "texto": "Sobra."}]}


def dibujar(prompt, ancho, alto, destino):
    imagenes.append(prompt)
    imagen = QImage(ancho // 8, alto // 8, QImage.Format_RGB32)
    imagen.fill(QColor("#7C5CFF"))
    imagen.save(str(destino))
    return destino


def narrar(texto, voz, destino):
    voces.append(voz)
    video.ffmpeg("-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "1", "-c:a", "libmp3lame", destino)
    return [{"palabra": p, "inicio": i * 0.2, "fin": i * 0.2 + 0.2} for i, p in enumerate(texto.split()[:5])]


ia.texto_json, ia.imagen, desde_prompt.narrar = pensar, dibujar, narrar

# ---------- La serie: biblia, voces y láminas ----------
falla(serie.crear_serie, "", "  ")
falla(serie.crear_serie, "X", "idea", formato="3:2")
s = serie.crear_serie("", "Samurái caribeño", "Anime 90s (estilo samurái)", personajes=3)
assert s["titulo"] == "La IA eligió" and [p["nombre"] for p in s["personajes"]] == ["Kaito", "Yara", "Brutus"]
assert "Personajes: 3" in pedidos[-1][1] and "nunca sus personajes" in pedidos[-1][0]  # originales, no copias
assert all(p["lamina"] and Path(p["lamina"]).is_file() for p in s["personajes"])
assert all("character reference sheet" in i and "90s anime" in i for i in imagenes)
voz = {p["nombre"]: p["voz"] for p in s["personajes"]}
assert voz["Yara"] in ("es-DO-RamonaNeural", "es-MX-DaliaNeural", "es-ES-ElviraNeural")  # mujer, en español
assert voz["Kaito"] != voz["Brutus"] and "Ramona" not in voz["Kaito"]  # cada hombre con su voz de hombre
datos = json.loads((Path(s["carpeta"]) / "serie.json").read_text(encoding="utf-8"))
assert datos["formato"] == "16:9" and datos["estilo"].startswith("90s anime")
assert serie.crear_serie("Mi serie", "x", "watercolor storybook style", 1)["titulo"] == "Mi serie"  # estilo propio
assert [x["titulo"] for x in serie.listar()] == ["Mi serie", "La IA eligió"]

# ---------- Capítulos: siguen la historia, cada personaje con su voz y su descripción fija ----------
imagenes.clear()
e1 = serie.crear_episodio("La IA eligió", "Kaito conoce a Yara", planos=3)
assert e1["titulo"] == "La IA eligió · Capítulo 1" and Path(e1["resultados"][0]["archivo"]).is_file()
assert len(imagenes) == len(voces) == 3  # tope de planos: el 4º no se hace
assert voces == [datos["narrador"], voz["Kaito"], voz["Yara"]]
assert "Kaito: young swordsman, blue haori" in imagenes[1] and "Yara: archer, red scarf" in imagenes[2]
assert "Nadie" not in imagenes[2] and imagenes[0].endswith(datos["estilo"])
assert abs(video.duracion(Path(e1["resultados"][0]["archivo"])) - 3 * 1.25) < 0.4  # 1 s de voz + 0,25 s por plano
proyecto = edicion.abrir(Path(e1["edicion"]))  # queda en el editor para retocarlo a mano
assert len(proyecto["clips"]) == 3 and proyecto["formato"] == "16:9"
voces.clear()
e2 = serie.crear_episodio(Path(s["carpeta"]).name, planos=12)
assert "Capítulo 1: Capítulo de prueba" in pedidos[-1][0] and "sigue la historia" in pedidos[-1][1]
assert e2["titulo"].endswith("Capítulo 2") and [e["numero"] for e in serie.listar()[1]["episodios"]] == [1, 2]
# Rehacer el 1: el mismo guion y sin volver a pedir las imágenes que ya salieron
antes, imagenes_antes = len(pedidos), len(imagenes)
(Path(e1["carpeta"]) / "video_final_imagen_01.png").unlink()
serie.crear_episodio("La IA eligió", numero=1)
assert len(pedidos) == antes and len(imagenes) == imagenes_antes + 1
falla(serie.crear_episodio, "No existe")
falla(serie.crear_episodio, "La IA eligió", numero=-3)
(Path(e1["carpeta"]) / "guion.json").write_text("[1, 2", encoding="utf-8")
falla(serie.crear_episodio, "La IA eligió", numero=1)

# ---------- Láminas propias (tu dibujo o un fotograma de tu video) ----------
mi_video = tmp / "samurai.mp4"
video.ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=3", "-pix_fmt", "yuv420p", mi_video)
destino = Path(serie.cambiar_lamina("La IA eligió", "Kaito", str(mi_video)))
assert destino.read_bytes()[:4] == b"\x89PNG" and QImage(str(destino)).width() == 320
falla(serie.cambiar_lamina, "La IA eligió", "Nadie", str(mi_video))
falla(serie.cambiar_lamina, "La IA eligió", "Kaito", "datos/claves.json")
falla(serie.cambiar_lamina, "La IA eligió", "Kaito", r"\\atacante.example\s\a.png")

# ---------- Cuadros para OpenToonz / Pencil2D / Krita ----------
cuadros = Path(serie.exportar_cuadros(e2["carpeta"], fps=4))
planos = sorted(cuadros.iterdir())
assert [p.name for p in planos] == [f"plano_{i:02d}" for i in range(4)] and len(list(planos[0].glob("*.png"))) >= 3
falla(serie.exportar_cuadros, str(tmp))  # solo carpetas de capítulos
falla(serie.exportar_cuadros, r"\\atacante.example\s\ep")
assert isinstance(serie.programas(), dict)

# ---------- Serie tocada a mano: lo raro se ignora ----------
archivo = Path(s["carpeta"]) / "serie.json"
raro = json.loads(archivo.read_text(encoding="utf-8"))
raro["personajes"][0]["voz"] = "eleven:../../hack"
raro["formato"] = "99:1"
raro["personajes"].append("no soy un personaje")
archivo.write_text(json.dumps(raro), encoding="utf-8")
leida = next(x for x in serie.listar() if x["titulo"] == "La IA eligió")
assert leida["formato"] == "16:9" and leida["personajes"][0]["voz"] == raro["narrador"] and len(leida["personajes"]) == 3
# Reordenar los personajes a mano no cruza las láminas: cada uno conserva su id
raro["personajes"] = [raro["personajes"][2], raro["personajes"][0], raro["personajes"][1]]
archivo.write_text(json.dumps(raro), encoding="utf-8")
leida = next(x for x in serie.listar() if x["titulo"] == "La IA eligió")
assert [Path(p["lamina"]).name for p in leida["personajes"]] == ["p3.png", "p1.png", "p2.png"]
# Tipos raros en serie.json o episodio.json: se ignoran, nunca impiden abrir la app
for cambio in ({"formato": ["16:9"]}, {"personajes": 3}, {"personajes": [{"nombre": "A", "id": "p1"},
                                                                         {"nombre": "B", "id": "p1"}]}):
    archivo.write_text(json.dumps({**raro, **cambio}), encoding="utf-8")
    leida = next(x for x in serie.listar() if x["titulo"] == "La IA eligió")
    laminas = [p["lamina"] for p in leida["personajes"] if p["lamina"]]
    assert len(laminas) == len(set(laminas))  # un id repetido no hace que dos personajes compartan lámina
archivo.write_text(json.dumps(raro), encoding="utf-8")
(Path(e2["carpeta"]) / "episodio.json").write_text("[]", encoding="utf-8")
assert [e["numero"] for e in next(x for x in serie.listar() if x["titulo"] == "La IA eligió")["episodios"]] == [1]
diseno.escribir_json(Path(e2["carpeta"]) / "episodio.json", {"numero": 2, "titulo": "Dos", "resumen": "r"})

# ---------- El Director y el MCP la pueden usar ----------
for nombre in ("crear_serie", "crear_episodio", "listar_series"):
    assert nombre in herramientas.TODAS
assert json.loads(herramientas.listar_series())[0]["titulo"] == "Mi serie"
r = json.loads(herramientas.crear_episodio("Mi serie", "", 3))
assert Path(r["resultados"][0]["archivo"]).is_file()

# ---------- Guiones que escribe el agente (Claude por el MCP): se usan tal cual, sin la IA de texto ----------
desde_prompt.PROYECTOS = tmp / "proyectos"
mio = {"titulo": "Mi short", "descripcion": "d", "hashtags": ["#a"], "estilo_visual": "cinematic",
       "escenas": [{"narracion": "Hola.", "imagen": "a beach"}, {"narracion": "Adiós.", "imagen": "a sunset"}]}
antes = len(pedidos)
r = desde_prompt.generar("", "9:16", 15, "es-DO-EmilioNeural", guion=mio)
assert len(pedidos) == antes and r["titulo"] == "Mi short" and Path(r["resultados"][0]["archivo"]).is_file()
r = json.loads(herramientas.crear_video("", segundos=15, guion=json.dumps(mio)))  # también como texto JSON
assert r["titulo"] == "Mi short" and len(pedidos) == antes
for malo in ({"titulo": "x"}, {**mio, "escenas": []}, "no es json", ["lista"]):
    hechos = len(list(desde_prompt.PROYECTOS.iterdir()))
    falla(desde_prompt.generar, "", guion=malo)
    assert len(list(desde_prompt.PROYECTOS.iterdir())) == hechos  # se rechaza antes de crear nada
biblia = {"titulo": "Escrita por Claude", "sinopsis": "s", "personajes": [
    {"nombre": f"P{i}", "descripcion": "d", "personalidad": "p", "genero": "mujer"} for i in range(9)]}
s2 = serie.crear_serie("", "", biblia=biblia)
assert len(pedidos) == antes and s2["titulo"] == "Escrita por Claude"
assert len(s2["personajes"]) == serie.MAX_PERSONAJES  # el tope de siempre, aunque mande más
falla(serie.crear_serie, "", "", biblia={"titulo": "sin personajes"})
cap = {"titulo": "Uno", "resumen": "r", "planos": [
    {"descripcion": "P0 runs", "personajes": ["P0"], "habla": "P0", "texto": "¡Vamos!"}]}
e = serie.crear_episodio("Escrita por Claude", guion=cap)
assert len(pedidos) == antes and e["titulo"].endswith("Capítulo 1")
assert json.loads((Path(e["carpeta"]) / "guion.json").read_text(encoding="utf-8"))["titulo"] == "Uno"
imagenes.clear()
serie.crear_episodio("Escrita por Claude", numero=1, guion={**cap, "titulo": "Uno bis"})  # reescribe el 1
assert len(imagenes) == 1  # guion nuevo: imagen nueva (no la del guion anterior)
falla(serie.crear_episodio, "Escrita por Claude", guion={"planos": "no"})

# ---------- Video animado con voz (Gemini Omni), sin red ----------
assert claves.elegir_modelo_video_voz(["models/gemini-2.5-pro", "models/veo-3.1"]) is None
assert claves.elegir_modelo_video_voz(["models/gemini-omni-1.1-flash", "models/gemini-omni-2-flash",
                                       "models/gemini-omni-flash-preview"]) == "gemini-omni-2-flash"
# Solo Flash estable (el de precio conocido: el costo que se avisa es el real), y 1.10 es más nuevo que 1.9
assert claves.elegir_modelo_video_voz(["gemini-omni-2.0-flash", "gemini-omni-2.0-pro"]) == "gemini-omni-2.0-flash"
assert claves.elegir_modelo_video_voz(["gemini-omni-2.0-pro-preview", "gemini-omni-2.0-pro"]) is None
assert claves.elegir_modelo_video_voz(["gemini-omni-1.9-flash", "gemini-omni-1.10-flash"]) == "gemini-omni-1.10-flash"


class Respuesta:
    def __init__(self, datos, codigo=200):
        self.datos, self.status_code, self.is_error = datos, codigo, codigo >= 400
        self.text = json.dumps(datos)

    def json(self):
        return self.datos

    def raise_for_status(self):
        pass


red, bajadas = [], []
uri, estado_omni, rechazo = f"{ia.API_GEMINI}/files/abc-123:download?alt=media", "ACTIVE", None


def get(url, **k):
    red.append(("GET", url, k))
    if url.endswith("/models"):
        return Respuesta({"models": [{"name": f"models/{m}"} for m in (
            "gemini-flash-latest", "gemini-omni-1.1-flash", "gemini-omni-1.5-pro", "gemma-4")]})
    return Respuesta({"state": estado_omni})


def post(url, **k):
    red.append(("POST", url, k))
    if rechazo:
        return Respuesta(rechazo, 400)
    return Respuesta({"id": "int-7", "outputs": [{"type": "text", "text": "ok"}, {"type": "video", "uri": uri}]})


def bajar(url, cabeceras, **k):
    bajadas.append((url, cabeceras))
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


http_real = ia.httpx.get, ia.httpx.post, ia.httpx.delete, claves.cargar, ia.seguro.descargar
ia.httpx.get, ia.httpx.post, ia.seguro.descargar = get, post, bajar
ia.httpx.delete = lambda url, **k: red.append(("DELETE", url, k))
claves.cargar = lambda: {"gemini": {"clave": "AIzaPrueba"}}
try:
    foto = tmp / "foto.png"
    dibujar("", 64, 64, foto)
    clip = ia.video_hablado("una manzana dice hola", "1:1", tmp / "omni.mp4", foto)
    assert clip.is_file() and red[0][1].endswith("/models")  # se pregunta qué modelos tiene la clave
    cuerpo = red[1][2]["json"]
    assert red[1][1] == f"{ia.API_GEMINI}/interactions" and cuerpo["model"] == "gemini-omni-1.1-flash"  # Pro no
    assert cuerpo["store"] and cuerpo["response_format"]["aspect_ratio"] == "16:9"  # 1:1 sale de 16:9 recortado
    assert cuerpo["input"][0]["type"] == "image" and cuerpo["input"][0]["mime_type"] == "image/png"
    assert bajadas == [(f"{ia.API_GEMINI}/files/abc-123:download?alt=media", {"x-goog-api-key": "AIzaPrueba"})]
    borrados = [u for m, u, _ in red if m == "DELETE"]  # ni el video ni la petición (con la foto) se quedan en Google
    assert borrados == [f"{ia.API_GEMINI}/files/abc-123", f"{ia.API_GEMINI}/interactions/int-7"]
    red.clear()
    ia.video_hablado("otra", "9:16", tmp / "omni2.mp4")
    assert not any(u.endswith("/models") for _, u, _ in red)  # el modelo se pregunta una vez por sesión
    assert red[0][2]["json"]["input"] == "otra" and red[0][2]["json"]["response_format"]["aspect_ratio"] == "9:16"
    red.clear()
    estado_omni = "FAILED"  # Google lo hizo y no se pudo bajar: se cobra igual, y lo guardado también se borra
    assert falla(ia.video_hablado, "x", "9:16", tmp / "omni4.mp4", error=ia.Cobrado)
    assert len([u for m, u, _ in red if m == "DELETE"]) == 2
    estado_omni, rechazo = "ACTIVE", {"error": {"message": "billing not enabled"}}
    assert "billing not enabled" in falla(ia.video_hablado, "x", "9:16", tmp / "omni5.mp4", error=RuntimeError)
    rechazo = None
    uri = "https://ladron.example/files/abc:download"  # la clave nunca viaja a una dirección de la respuesta
    bajadas.clear()
    assert "inesperada" in falla(ia.video_hablado, "x", "9:16", tmp / "omni3.mp4", error=RuntimeError)
    assert not bajadas
finally:
    ia.httpx.get, ia.httpx.post, ia.httpx.delete, claves.cargar, ia.seguro.descargar = http_real
assert not desde_prompt.con_voz_propia()  # sin clave de Gemini: imágenes con narración, como siempre
hechos = len(list(desde_prompt.PROYECTOS.iterdir()))
falla(desde_prompt.generar, "", guion=mio, animado=True, error=ia.SinClave)
assert len(list(desde_prompt.PROYECTOS.iterdir())) == hechos  # se avisa antes de crear (y gastar) nada

pedidos_omni = []


def omni(prompt, formato, destino, referencia=None):
    pedidos_omni.append(prompt)
    if "sunset" in prompt:
        raise ia.Cobrado("se cortó la descarga")  # Google lo hizo (y lo cobró) pero no llegó
    video.ffmpeg("-f", "lavfi", "-i", "testsrc=s=360x640:d=3:r=24", "-f", "lavfi", "-i", "sine=f=440:d=3",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", destino)
    return destino


omni_real, transcribir_real, animar_real = ia.video_hablado, ia.transcribir, ia.video_desde_imagen
ia.video_hablado, ia.video_desde_imagen = omni, lambda *a, **k: None  # la escena que falla: sin animar (sería red)
ia.transcribir = lambda audio, idioma=None, pista=None, **k: [{"palabra": "Hola.", "inicio": 0.2, "fin": 1.0}]
claves.cargar = lambda: {"gemini": {"clave": "AIzaPrueba"}}
try:
    assert not desde_prompt.con_voz_propia()  # la IA de video en «No usar»: tampoco con voz
    claves.elegir_por_defecto("video", "auto")
    assert desde_prompt.con_voz_propia()  # con Gemini conectado, la casilla de Crear sale marcada (y avisa del costo)
    # Lo de pago solo pedido de verdad: sin decirlo, o con «"false"» o «1» que escriba una IA, va lo gratis
    for valor in (None, "false", 1):
        r = desde_prompt.generar("", "9:16", 16, guion=mio, **({} if valor is None else {"animado": valor}))
        assert not pedidos_omni and Path(r["resultados"][0]["archivo"]).is_file()
    json.loads(herramientas.crear_video("", segundos=15, guion=json.dumps(mio)))
    assert not pedidos_omni  # tampoco desde el Director o un agente MCP que no lo pida
    hechos = len(list(desde_prompt.PROYECTOS.iterdir()))
    falla(desde_prompt.generar, "", "3:4", 16, guion=mio, animado=True)  # formato raro: antes de pagar nada
    assert not pedidos_omni and len(list(desde_prompt.PROYECTOS.iterdir())) == hechos
    # Sobran escenas: se quitan las del medio y se conserva el cierre (la última)
    largo = {**mio, "escenas": mio["escenas"][:1] + [{"narracion": "Sobra.", "imagen": "extra"}] * 3
             + mio["escenas"][1:]}
    antes = len(voces)
    r = desde_prompt.generar("", "9:16", 16, guion=largo, animado=True)
    assert len(pedidos_omni) == 2 and "a sunset" in pedidos_omni[1]  # 16 s = 2 escenas de 8 s: ni una de más
    assert '"Hola."' in pedidos_omni[0] and "lip sync" in pedidos_omni[0] and "a beach" in pedidos_omni[0]
    assert len(voces) == antes + 1  # solo la escena que falló lleva narración
    final = Path(r["resultados"][0]["archivo"])
    assert final.is_file() and 2.8 < video.duracion(final) < 3.5  # el clip de 3 s se corta al acabar de hablar
    assert any("se usaron 2" in a for a in r["avisos"])
    assert any("2" in a and "se cortó la descarga" in a for a in r["avisos"])
    assert any("2 escena(s)" in a and "US$" in a for a in r["avisos"])  # la que se cobró sin llegar también cuenta
    # Reintentar en la misma carpeta (ejemplos/crear.py): las escenas ya hechas no se vuelven a pagar
    pedidos_omni.clear()
    desde_prompt.clips_hablados(json.loads((Path(r["carpeta"]) / "guion.json").read_text(encoding="utf-8")),
                                Path(r["carpeta"]), "9:16", lambda *a: None, None, [])
    assert len(pedidos_omni) == 1 and "a sunset" in pedidos_omni[0]
    # Si el montaje falla después de pagar, el gasto no se pierde de vista
    pedidos_omni.clear()
    montar_real = desde_prompt.montar
    desde_prompt.montar = lambda *a, **k: (_ for _ in ()).throw(OSError("disco lleno"))
    try:
        error = falla(desde_prompt.generar, "", "9:16", 16, guion=mio, animado=True, error=RuntimeError)
        assert "disco lleno" in error and "US$" in error
    finally:
        desde_prompt.montar = montar_real
    escenas, costo = desde_prompt.costo_hablado(600)
    assert escenas == desde_prompt.MAX_HABLADAS and abs(costo - escenas) < 1e-6  # tope: ~US$1 por escena
finally:
    ia.video_hablado, ia.transcribir, ia.video_desde_imagen = omni_real, transcribir_real, animar_real
    claves.cargar = http_real[3]
    claves.elegir_por_defecto("video", "ninguno")

# ---------- La página ----------
from ui.paginas.serie import PaginaSerie  # noqa: E402

pagina = PaginaSerie()
pagina.resize(1100, 1000)
pagina.show()
assert pagina.series.count() == 4 and pagina.series.currentData() is None and pagina.nueva.isVisible()
la_ia = next(i for i in range(1, 4) if pagina.series.itemData(i)["titulo"] == "La IA eligió")
pagina.series.setCurrentIndex(la_ia)
assert pagina.elegida.isVisible() and not pagina.nueva.isVisible()
assert pagina.capitulos.count() == 2 and pagina.fila_personajes.count() == 4  # 3 personajes y el espacio
pagina.capitulos.setCurrentRow(0)
assert pagina.reproductor.isVisible() and pagina.reproductor.resultados[0]["archivo"].endswith("video_final.mp4")
pagina.reproductor.player.stop()
pagina.recargar()
assert pagina.series.currentIndex() == la_ia  # recargar no pierde la serie elegida
pagina.grab()
# Mientras saca cuadros, el botón no vuelve a activarse ni un segundo clic suelta el hilo (eso tumbaba la app)
import threading  # noqa: E402

from ui.comun import Tarea  # noqa: E402

soltar = threading.Event()
pagina.tarea_cuadros = enmarcha = Tarea(lambda aviso: soltar.wait(5) and {"carpeta": str(tmp)})
enmarcha.start()
pagina.recargar()
assert not pagina.cuadros_btn.isEnabled()
pagina.capitulos.setCurrentRow(0)
pagina._cuadros()
assert pagina.tarea_cuadros is enmarcha
pagina.reproductor.player.stop()
soltar.set()
enmarcha.wait(5000)
print("Pruebas de la serie animada pasadas.")
