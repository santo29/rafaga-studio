"""Voz gratis o ElevenLabs, sin red ni claves de verdad: el estudio pregunta antes de narrar en las páginas, el Director y
el MCP; sin ElevenLabs disponible no pregunta y narra gratis; la voz fija manda; lo de pago dice su costo una sola vez.
python -m pruebas.voz_elegida"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"  # nada de red: ni por descuido
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from motor import anuncios, claves, desde_prompt, director, guardia, herramientas, ia, marca, memoria, serie  # noqa: E402
from ui import comun  # noqa: E402
from ui.paginas import claves as pagina_claves, crear as pagina_crear, diseno as pagina_diseno, serie as pagina_serie  # noqa: E402
import mcp_server  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
tmp = Path(tempfile.mkdtemp(prefix="rafaga-voz-elegida-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
claves.CONEXIONES, memoria.ARCHIVO, marca.ARCHIVO = tmp / "conexiones.json", tmp / "memoria.json", tmp / "marca.json"
serie.CARPETA = tmp / "series"
GRATIS, BELLA, ROGER = "es-DO-EmilioNeural", "eleven:bella", "eleven:roger"
ELEVEN = {"proveedor": "elevenlabs", "clave": "sk_" + "a1" * 24, "usos": ["voz", "musica"], "modelo_voz": "m",
          "voces": [{"id": "bella", "nombre": "Bella", "acento": "", "genero": "female"},
                    {"id": "roger", "nombre": "Roger", "acento": "", "genero": "male"},
                    {"id": "sarah", "nombre": "Sarah", "acento": "", "genero": "female"}]}


def sin_fija():
    a = claves._guardados()
    a.pop("voz_preferida", None)
    a.pop("voz_eleven", None)
    claves._reemplazar(claves.AJUSTES, json.dumps(a))


def estado(proveedor, que):
    """Un estado recién comprobado («sin_saldo»…) o ninguno."""
    todos = claves.estados()
    todos.pop(proveedor, None)
    if que:
        todos[proveedor] = {"estado": que, "detalle": "", "paso": "", "fecha": time.strftime("%Y-%m-%d %H:%M:%S")}
    claves.CONEXIONES.write_text(json.dumps(todos), encoding="utf-8")


def falla(funcion, *args, error=ValueError, **kw) -> str:
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


# ---------- Sin ElevenLabs: ni se pregunta ni se ofrece ----------
assert desde_prompt.voces_eleven() == {} and not desde_prompt.toca_preguntar_voz(GRATIS) and desde_prompt.voz_eleven() == ""
assert desde_prompt.voz_inicial() == GRATIS  # sin fija, la del idioma de la app

claves.guardar(ELEVEN)
assert set(desde_prompt.voces_eleven().values()) == {BELLA, ROGER, "eleven:sarah"}
assert desde_prompt.voz_eleven() == BELLA  # la primera de la cuenta
claves.elegir_por_defecto("voz_eleven", ROGER)
assert desde_prompt.voz_eleven() == ROGER  # la última elegida
claves.elegir_por_defecto("voz_eleven", "eleven:ya-no-esta")
assert desde_prompt.voz_eleven() == BELLA

# ---------- Cuándo toca preguntar ----------
assert desde_prompt.toca_preguntar_voz(GRATIS) and desde_prompt.toca_preguntar_voz(BELLA)  # sin fija, siempre
claves.elegir_por_defecto("voz_preferida", GRATIS)
assert not desde_prompt.toca_preguntar_voz(GRATIS)
assert desde_prompt.toca_preguntar_voz(BELLA)  # dejó una gratis: pagar se pregunta
claves.elegir_por_defecto("voz_preferida", BELLA)
assert not desde_prompt.toca_preguntar_voz(ROGER) and not desde_prompt.toca_preguntar_voz(GRATIS)  # la cambió a mano
assert desde_prompt.toca_preguntar_voz(GRATIS, de_la_ia=True)  # la IA no le quita la que dejó fija
claves.elegir_por_defecto("voz_preferida", "eleven:ya-no-esta")
assert desde_prompt.voz_preferida() == "" and desde_prompt.toca_preguntar_voz(GRATIS)  # la borró de su cuenta
sin_fija()

# Sin saldo o con el estudio bloqueado no se ofrece: la narración fallaría al final, con las imágenes ya pagadas
estado("elevenlabs", "sin_saldo")
assert desde_prompt.voces_eleven() == {} and not desde_prompt.toca_preguntar_voz(GRATIS)
assert claves.antes_de(["voz"]) == ["ElevenLabs no tiene saldo: la narración irá con la voz gratis."]
claves.elegir_por_defecto("voz_preferida", GRATIS)
assert claves.antes_de(["voz"]) == []  # dejó fija una gratis: no echa de menos ElevenLabs
sin_fija()
estado("elevenlabs", "")
assert claves.antes_de(["voz"]) == []
bloqueado_real = guardia.bloqueado
guardia.bloqueado = lambda: True
assert desde_prompt.voces_eleven() == {}
guardia.bloqueado = bloqueado_real

# ---------- Qué trabajos narran y lo que cuesta su voz ----------
assert director.narra("crear_video", {"prompt": "un gato"}) and director.narra("crear_anuncios", {})
assert director.narra("crear_serie", {})
assert not director.narra("crear_video", {"prompt": "un gato", "animado": True})  # hablan con la voz de su IA de video
assert not director.narra("crear_video", {"imagen": "a.png", "solo_animar": True, "prompt": "x"})
assert not director.narra("crear_video", {"prompt": "un gato sin narración"})
assert not director.narra("crear_video", {"prompt": "x", "guion": {"escenas": [{"narracion": ""}]}})
assert director.narra("crear_video", {"prompt": "x", "guion": {"escenas": [{"narracion": "Hola"}]}})
assert not director.narra("producir_cancion", {"voz": "toma.wav"})  # «voz» es un archivo: nada que elegir
assert not director.narra("crear_diseno", {})


def cerca(a, b):
    return abs(a - b) < 1e-9


assert cerca(director.costo_voz("crear_video", {"prompt": "x", "segundos": 30, "voz": BELLA}), 30 * 16 / 1000 * 0.30)
assert director.costo_voz("crear_video", {"prompt": "x", "segundos": 30, "voz": GRATIS}) == 0
assert cerca(director.costo_voz("crear_video", {"prompt": "x", "segundos": 30}, BELLA), 0.144)  # la voz que se ofrece
assert cerca(director.costo_voz("crear_anuncios", {"variantes": 2, "segundos": 20, "voz": BELLA}), 40 * 16 / 1000 * 0.30)
assert cerca(director.costo_voz("crear_serie", {"voz": BELLA}), 12 * 400 / 1000 * 0.30)  # lo más que cuesta un capítulo normal
assert director.costo_voz("crear_video", {"prompt": "video sin narración", "voz": BELLA}) == 0
assert director.costo_voz("crear_video", {"imagen": "a", "solo_animar": True, "voz": BELLA}) == 0
# Animado: lo poco que se narre va gratis (elegir_voz), así que no cuesta voz
assert director.costo_voz("crear_video", {"prompt": "x", "segundos": 30, "animado": True, "voz": BELLA}) == 0
# Lo que ya viene escrito se cobra tal cual, con el tope de cada escena
largo = {"prompt": "x", "segundos": 15, "voz": BELLA, "guion": {"escenas": [{"narracion": "a" * 300}] * 5}}
assert cerca(director.costo_voz("crear_video", largo), 1500 / 1000 * 0.30)
largo["guion"] = {"escenas": [{"narracion": "a" * 900}]}
assert cerca(director.costo_voz("crear_video", largo), 400 / 1000 * 0.30)
# Las escenas numeradas no se acortan al tiempo: cuentan por lo que narra cada una
numeradas = "\n".join(f"ESCENA {n}: algo pasa" for n in range(1, 11))
assert cerca(director.costo_voz("crear_video", {"prompt": numeradas, "segundos": 15, "voz": BELLA}), 1200 / 1000 * 0.30)
assert "hasta unos" in director.texto_costo_voz("crear_serie", {"voz": BELLA})
assert "por capítulo" in director.texto_costo_voz("crear_serie", {"voz": BELLA})
# Lo que escribe la IA no pasa de lo que se preguntó
escenas_ia = [{"narracion": "palabra " * 100}, {"narracion": "palabra " * 100}, {"narracion": ""}]
assert not desde_prompt.al_presupuesto([{"narracion": "palabra " * 100}], 100, GRATIS)  # gratis: no se toca
assert desde_prompt.al_presupuesto(escenas_ia, 480, BELLA) and sum(len(e["narracion"]) for e in escenas_ia) <= 480
assert escenas_ia[2]["narracion"] == "" and not desde_prompt.al_presupuesto(escenas_ia, 480, BELLA)
# Primero se quitan frases enteras: un exceso pequeño no deja todas las escenas cortadas
escenas_ia = [{"narracion": "Primera frase aquí. Segunda frase larga de esta escena."}, {"narracion": "Otra escena corta."}]
assert desde_prompt.al_presupuesto(escenas_ia, 45, BELLA)
assert escenas_ia == [{"narracion": "Primera frase aquí."}, {"narracion": "Otra escena corta."}], escenas_ia
escenas_ia = [{"narracion": "a"}, {"narracion": "b"}]  # imposible de cumplir: no se queda dando vueltas
desde_prompt.al_presupuesto(escenas_ia, 0, BELLA)
assert director.texto_costo_voz("crear_video", {"prompt": "x", "segundos": 30, "voz": BELLA}) == "unos US$0.14"
# Y entra en la pregunta de costo, como lo demás de pago; una serie no paga al crearla, sino en cada capítulo
assert director.costo("crear_video", {"prompt": "x", "segundos": 30, "voz": BELLA}) == "Esto cuesta unos US$0.14. ¿Lo hago?"
assert director.costo("crear_video", {"prompt": "x", "segundos": 30, "voz": GRATIS}) is None
assert director.costo("crear_serie", {"titulo": "x", "voz": BELLA}) is None

# ---------- El Director: la voz la decide el usuario, no la IA ----------
hechos, preguntas, avisos_dichos = [], [], []
real_video, real_anuncios = herramientas.TODAS["crear_video"], herramientas.TODAS["crear_anuncios"]


def video_falso(prompt="", formato="9:16", segundos=45, voz="", imagen="", solo_animar=False, guion=None, animado=False):
    hechos.append(voz)
    return '{"ok": true}'


def usar(args, respuesta, herramienta="crear_video"):
    hechos.clear(), preguntas.clear(), avisos_dichos.clear()
    if herramienta == "crear_video":
        herramientas.TODAS["crear_video"] = video_falso
    try:
        return director._usar(herramienta, args, lambda *a: None, lambda n: None, "un gato", "foto.png",
                              lambda p: preguntas.append(p) or respuesta, avisos_dichos.extend)
    finally:
        herramientas.TODAS["crear_video"] = real_video


claves.borrar("elevenlabs")
args, r = usar({"prompt": "un gato"}, True)  # sin ElevenLabs: ni una pregunta, gratis
assert r == '{"ok": true}' and not preguntas and "voz" not in args and hechos == [""], (args, r, preguntas)
args, r = usar({"prompt": "un gato", "voz": "es-MX-JorgeNeural"}, True)
assert not preguntas and hechos == ["es-MX-JorgeNeural"]  # la gratis que pidió
claves.guardar(ELEVEN)

args, r = usar({"prompt": "un gato", "segundos": 30}, True)  # dice que sí: ElevenLabs, y no se le pregunta otra vez
assert len(preguntas) == 1 and hechos == [BELLA], preguntas
assert "«ElevenLabs · Bella»" in preguntas[0] and "unos US$0.14" in preguntas[0] and "«Emilio (Rep. Dominicana)»" in preguntas[0]
assert "Claves de IA" in preguntas[0]
args, r = usar({"prompt": "un gato", "segundos": 30}, False)  # dice que no: gratis, y el trabajo sigue
assert len(preguntas) == 1 and hechos == [GRATIS] and r == '{"ok": true}', (preguntas, r)
args, r = usar({"prompt": "un gato", "voz": "es-MX-JorgeNeural"}, False)  # la gratis que eligió la IA se respeta
assert hechos == ["es-MX-JorgeNeural"] and "Jorge" in preguntas[0]
args, r = usar({"prompt": "un gato", "voz": ROGER}, True)  # la de ElevenLabs que eligió la IA es la que se ofrece
assert hechos == [ROGER] and "Roger" in preguntas[0]
args, r = usar({"prompt": "un gato", "voz": ROGER}, False)
assert hechos == [GRATIS], hechos  # sin su sí no se paga aunque la IA la eligiera
# Una voz que no es texto no tumba al Director: la herramienta dirá que no vale
for rara in (["x"], {"a": 1}, 7):
    args, r = usar({"prompt": "un gato", "voz": rara}, True)
    assert not preguntas and hechos == [rara], (rara, r)
    assert "Voz desconocida" in falla(real_video, "un gato", voz=rara)
args, r = usar({"prompt": "un gato", "voz": "eleven:../../hack"}, True)
assert not preguntas and hechos == ["eleven:../../hack"]  # no existe: ni se pregunta (la herramienta real la rechaza)
assert "Voz desconocida" in falla(real_video, "un gato", voz="eleven:../../hack")
# Sin narración o con escenas que hablan: no hay nada que elegir, y si la IA o la fija eran de pago, gratis
args, r = usar({"prompt": "un gato sin narración"}, True)
assert not preguntas
args, r = usar({"prompt": "un gato sin narración", "voz": BELLA}, True)
assert not preguntas and hechos == [GRATIS]
args, r = usar({"prompt": "un gato", "animado": True, "voz": BELLA}, True)
assert hechos == [GRATIS] and not any("ElevenLabs" in p for p in preguntas), preguntas
claves.elegir_por_defecto("voz_preferida", BELLA)
args, r = usar({"prompt": "un gato", "animado": True}, True)
assert hechos == [GRATIS] and not any("ElevenLabs" in p for p in preguntas), preguntas
sin_fija()

# Con otro gasto, la voz aceptada entra en la cifra total de la segunda pregunta
costo_real = director.costo
real_pago = ia.video_de_pago
ia.video_de_pago = lambda un_clip=False: "kling"
precio_real, ia.precio_video = ia.precio_video, lambda p, voz=False: 0.5
try:
    args, r = usar({"prompt": "un gato", "segundos": 30}, True)
    assert len(preguntas) == 2 and preguntas[1].startswith("Esto cuesta unos US$") and hechos == [BELLA], preguntas
    con_voz = float(preguntas[1].split("US$")[1].split(".")[0] + "." + preguntas[1].split("US$")[1].split(".")[1])
    args, r = usar({"prompt": "un gato", "segundos": 30}, False)
    assert len(preguntas) == 2 and hechos == []  # gratis la voz, pero no aceptó el otro gasto: no se hace nada
    sola = float(preguntas[1].split("US$")[1].split(".")[0] + "." + preguntas[1].split("US$")[1].split(".")[1])
    assert cerca(round(con_voz - sola, 2), 0.14), (con_voz, sola)
finally:
    ia.video_de_pago, ia.precio_video = real_pago, precio_real

# En el Director de verdad, un «No» a ElevenLabs no cancela el trabajo aunque haya otro gasto: es «la gratis»
pasos = iter([{"mensaje": "", "herramienta": "crear_video", "argumentos": json.dumps({"prompt": "un gato", "segundos": 30})},
              {"mensaje": "Listo", "herramienta": "", "argumentos": "{}"}])
texto_real, real_pago, precio_real = ia.texto_json, ia.video_de_pago, ia.precio_video
ia.texto_json = lambda *a, **k: next(pasos)
ia.video_de_pago, ia.precio_video = lambda un_clip=False: "kling", lambda p, voz=False: 0.5
herramientas.TODAS["crear_video"] = video_falso
hechos.clear(), preguntas.clear()
try:
    r = director.dirigir("hazme un video de un gato", confirmar=lambda p: preguntas.append(p) or "ElevenLabs" not in p)
    assert len(preguntas) == 2 and "ElevenLabs" in preguntas[0] and preguntas[1].startswith("Esto cuesta"), preguntas
    assert hechos == [GRATIS], (hechos, r)  # se hizo, con la gratis
finally:
    ia.texto_json, ia.video_de_pago, ia.precio_video = texto_real, real_pago, precio_real
    herramientas.TODAS["crear_video"] = real_video

# Voz fija: no se pregunta cuál. La de ElevenLabs sigue diciendo su costo: es dinero
claves.elegir_por_defecto("voz_preferida", GRATIS)
args, r = usar({"prompt": "un gato"}, True)
assert not preguntas and hechos == [GRATIS]
claves.elegir_por_defecto("voz_preferida", "es-MX-JorgeNeural")
args, r = usar({"prompt": "un gato"}, True)
assert not preguntas and hechos == ["es-MX-JorgeNeural"]
args, r = usar({"prompt": "un gato", "voz": BELLA}, False)  # la IA quiere pagar y él dejó una gratis
assert len(preguntas) == 1 and hechos == ["es-MX-JorgeNeural"]
claves.elegir_por_defecto("voz_preferida", BELLA)
args, r = usar({"prompt": "un gato", "segundos": 30}, True)
assert preguntas == ["Esto cuesta unos US$0.14. ¿Lo hago?"] and hechos == [BELLA], preguntas
args, r = usar({"prompt": "un gato", "segundos": 30}, False)
assert r.startswith("ERROR") and not hechos  # «No» al costo: no se hace (no hay gratis que él haya elegido)
args, r = usar({"prompt": "un gato", "voz": GRATIS, "segundos": 30}, True)  # la IA puso una gratis: gana la que dejó
assert hechos == [BELLA] and len(preguntas) == 1 and "Bella" in preguntas[0], (hechos, preguntas)
sin_fija()

# Sin saldo: ni se ofrece; se avisa y se narra gratis, también si la IA o la fija eran de ElevenLabs
estado("elevenlabs", "sin_saldo")
args, r = usar({"prompt": "un gato"}, True)
assert not preguntas and "voz" not in args and avisos_dichos == ["ElevenLabs no tiene saldo: la narración irá con la voz gratis."]
args, r = usar({"prompt": "un gato", "voz": BELLA}, True)
assert not preguntas and hechos == [GRATIS]
claves.elegir_por_defecto("voz_preferida", BELLA)
args, r = usar({"prompt": "un gato"}, True)
assert not preguntas and hechos == [GRATIS]
sin_fija()
estado("elevenlabs", "")

# Los anuncios también preguntan, y su voz llega al trabajo (antes siempre era Ramona)
hechos_anuncio, crear_real = [], anuncios.crear
anuncios.crear = lambda foto, producto, *a, **k: hechos_anuncio.append(k["voz"]) or {"resultados": []}
try:
    args, r = usar({"foto": "foto.png", "producto": "x", "variantes": 1, "segundos": 20}, True, "crear_anuncios")
    assert len(preguntas) == 1 and "unos US$0.10" in preguntas[0] and hechos_anuncio == [BELLA], (preguntas, r)
    args, r = usar({"foto": "foto.png", "producto": "x"}, False, "crear_anuncios")
    assert hechos_anuncio[-1] == GRATIS
    assert herramientas.crear_anuncios("foto.png", "x") and hechos_anuncio[-1] == GRATIS  # sin decir voz, la del idioma
    assert "Voz desconocida" in falla(herramientas.crear_anuncios, "foto.png", "x", voz="eleven:nada")
finally:
    anuncios.crear = crear_real
# La IA de los anuncios tampoco elige una voz de pago escena por escena
from motor import anuncios as _a  # noqa: E402
assert 'e.pop("voz", None)' in Path(_a.__file__).read_text(encoding="utf-8")
# Si la IA elegida no atiende, las fotos no se van a otra: a las demás, solo el texto
llegaron, pedir_real = [], ia._pedir
claves.guardar({"proveedor": "gemini", "clave": "AIza" + "a" * 35, "usos": ["texto"]})
claves.guardar({"proveedor": "groq", "clave": "gsk_" + "a" * 40, "usos": ["texto"]})


def pedir_falso(c, instrucciones, pedido, esquema, rapido=False):
    llegaron.append((c["proveedor"], pedido))
    if len(llegaron) == 1:
        raise ia.SinServicio("sin saldo")
    return {"ok": True}


ia._pedir = pedir_falso
con_foto = [{"type": "text", "text": "Hola"}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "x"}}]
# El permiso se dio para esa IA: si no atiende, no se prueba otra (colocar_voz reparte las frases y lo dice)
assert "sin saldo" in falla(ia.texto_json, "i", con_foto, {"type": "object"}, solo_elegida=True, error=ia.SinServicio)
assert [p for p, _ in llegaron] == ["gemini"] and llegaron[0][1] == con_foto, llegaron
llegaron.clear()
ia.texto_json("i", con_foto, {"type": "object"})  # lo de siempre, sin ese permiso de por medio
assert llegaron[1][1] == con_foto
ia._pedir = pedir_real
claves.borrar("gemini")
claves.borrar("groq")

# Las imágenes y la canción de pago también se preguntan desde las páginas, con la cifra del Director
dichas, real_si_cuesta, real_error = [], comun.si_cuesta, comun.mensaje_error
comun.si_cuesta = lambda padre, titulo, texto: dichas.append(texto) or False
comun.mensaje_error = lambda padre, titulo, texto: dichas.append(texto)
contenido = comun.PaginaTrabajo._pagar_contenido
assert contenido(None, None, "crear_video", {"prompt": "un gato", "segundos": 45}) is True and not dichas  # gratis: nada
assert contenido(None, serie.rehacer_plano, None, {}) is True and not dichas
claves.guardar({"proveedor": "openai", "clave": "sk-" + "a" * 40, "usos": ["texto", "imagen"], "modelo_texto": "m"})
claves.elegir_por_defecto("imagen", "openai")
assert contenido(None, None, "crear_video", {"prompt": "un gato", "segundos": 45}) is False  # sin su sí, ni empieza
assert "US$" in dichas[-1]
assert director.costo_contenido("crear_anuncios", {"variantes": 3}) > 0
for una in (serie.rehacer_plano, serie.dibujar_lamina):  # rehacer también dibuja una imagen de pago
    dichas.clear()
    assert contenido(None, una, None, {}) is False and "US$0.25" in dichas[0], dichas
real_bloqueado = guardia.bloqueado
guardia.bloqueado = lambda: {"motivo": "x"}
dichas.clear()
assert contenido(None, None, "crear_video", {"prompt": "un gato"}) is False and "bloqueado" in dichas[0], dichas
guardia.bloqueado = real_bloqueado
claves.elegir_por_defecto("imagen", "auto")
claves.borrar("openai")
assert contenido(None, None, "crear_cancion", {"idea": "x"}) is False  # ELEVEN conectada: la canción cuesta
assert contenido(None, None, None, {}) is True  # lo que no es una herramienta no cuenta
# Diseño sin elegir calidad también cobra si la IA de imágenes es de pago
real_pregunta = pagina_diseno.QMessageBox.question
vistas = []
pagina_diseno.QMessageBox.question = lambda *a: vistas.append(a[2]) or pagina_diseno.QMessageBox.No
hoja = SimpleNamespace(calidad=SimpleNamespace(currentData=lambda: "1K"), estado=SimpleNamespace(setText=lambda x: None))
assert pagina_diseno.PaginaDiseno._calidad(hoja, 5) == "1K" and not vistas  # gratis: nada
claves.guardar({"proveedor": "openai", "clave": "sk-" + "a" * 40, "usos": ["texto", "imagen"], "modelo_texto": "m"})
claves.elegir_por_defecto("imagen", "openai")
assert pagina_diseno.PaginaDiseno._calidad(hoja, 5) is None and "US$1.25" in vistas[0], vistas
pagina_diseno.QMessageBox.question = real_pregunta
claves.elegir_por_defecto("imagen", "auto")
claves.borrar("openai")
comun.si_cuesta, comun.mensaje_error = real_si_cuesta, real_error
# Si el montaje falla con la voz ya pagada, el error dice cuánto y dónde: reintentar lo pagaría otra vez
hoja_gasto = tmp / "gasto"
hoja_gasto.mkdir()
(hoja_gasto / "video_final_voz_00.json").write_text(json.dumps({"para": ["a" * 1000, BELLA, 1.0], "palabras": []}), encoding="utf-8")
gasto = falla(desde_prompt.relanzar_con_gasto, ValueError("disco lleno"), [], hoja_gasto, error=RuntimeError)
assert "disco lleno" in gasto and "US$0.30" in gasto and str(hoja_gasto) in gasto
assert "sin gasto" in falla(desde_prompt.relanzar_con_gasto, ValueError("sin gasto"), [], tmp / "no-hay")
# El prompt del Director ya no le deja elegir la voz
assert "público, música) lo decides tú" in director.INSTRUCCIONES and 'deja "voz" vacía' in director.INSTRUCCIONES
# Las herramientas dicen al agente que la deje vacía
assert "déjala vacía" in herramientas.crear_video.__doc__ and "voz" in herramientas.crear_serie.__doc__

# ---------- Por el MCP: la misma pregunta, en su ventana; con «No» se narra gratis ----------
generados, ventanas, generar_real, preguntar_real = [], [], desde_prompt.generar, mcp_server._preguntar
desde_prompt.generar = lambda prompt, formato, segundos, voz, *a, **k: generados.append(voz) or {"resultados": []}
try:
    claves.borrar("elevenlabs")
    mcp_server._preguntar = lambda texto: ventanas.append(texto) or True
    mcp_server.crear_video("un gato")
    assert not ventanas and generados == [GRATIS]  # sin ElevenLabs, como siempre
    claves.guardar(ELEVEN)
    mcp_server.crear_video("un gato", segundos=30)
    assert generados[-1] == BELLA and len(ventanas) == 1, ventanas  # una sola ventana
    assert ventanas[0].startswith("Un agente conectado por MCP quiere crear un video.") and "unos US$0.14" in ventanas[0]
    ventanas.clear()
    mcp_server._preguntar = lambda texto: ventanas.append(texto) or False
    mcp_server.crear_video("un gato", "9:16", 30)  # un «No» a la voz no es un «No» al trabajo: ni error ni Guardia
    assert generados[-1] == GRATIS and len(ventanas) == 1
    ventanas.clear()
    mcp_server.crear_video("un gato", voz=ROGER)  # el agente no se la queda sin el sí del usuario
    assert generados[-1] == GRATIS and "Roger" in ventanas[0]
    ventanas.clear()
    mcp_server.crear_video("x", guion={"titulo": "t", "descripcion": "d", "hashtags": [], "estilo_visual": "s",
                                       "escenas": [{"narracion": "", "imagen": "a"}]})
    assert not ventanas  # su guion no narra nada
    # Con «sin narración» y un guion narrado: sin ventana y sin voz de pago, ni aunque la pida
    mcp_server.crear_video("video sin narración", voz=BELLA, guion={"escenas": [{"narracion": "Hola", "imagen": "a"}]})
    assert not ventanas and generados[-1] == GRATIS
    claves.elegir_por_defecto("voz_preferida", BELLA)
    assert "no se hizo" in falla(mcp_server.crear_video, "un gato", error=ToolError)  # fija y de pago: «No» al costo
    assert "Esto cuesta" in ventanas[-1] and generados[-1] == GRATIS
    sin_fija()
finally:
    desde_prompt.generar, mcp_server._preguntar = generar_real, preguntar_real

# ---------- Un guion no elige una voz de pago escena por escena ----------
capturado, montar_real, proyectos_real = {}, desde_prompt.montar, desde_prompt.PROYECTOS
desde_prompt.PROYECTOS = tmp / "proyectos"  # nunca los del usuario
desde_prompt.montar = lambda guion, carpeta, formato, voz, *a, **k: capturado.update(guion=guion, voz=voz) or (tmp / "v.mp4")
try:
    claves.elegir_por_defecto("voz_preferida", GRATIS)
    (tmp / "v.mp4").write_bytes(b"x")
    try:
        desde_prompt.generar("x", voz=GRATIS, guion={"titulo": "t", "descripcion": "d", "hashtags": [], "estilo_visual": "s",
                                                     "escenas": [{"narracion": "Hola", "imagen": "a", "voz": BELLA}]})
    except Exception:  # noqa: BLE001  lo que pasa tras montar no importa aquí
        pass
    assert capturado["voz"] == GRATIS and "voz" not in capturado["guion"]["escenas"][0]
    # Con «sin narración» en el pedido, tampoco se narra el guion que trae
    (tmp / "v.mp4").write_bytes(b"x")
    desde_prompt.PROYECTOS = tmp / "proyectos2"  # cada trabajo, su carpeta con la hora: dos en el mismo segundo chocarían
    desde_prompt.generar("video sin narración", voz=GRATIS, guion={
        "titulo": "t", "descripcion": "d", "hashtags": [], "estilo_visual": "s", "escenas": [{"narracion": "Hola", "imagen": "a"}]})
except Exception:  # noqa: BLE001
    pass
finally:
    desde_prompt.montar, desde_prompt.PROYECTOS = montar_real, proyectos_real
assert capturado["guion"]["escenas"][0]["narracion"] == "", capturado
sin_fija()

# ---------- Montar: no paga dos veces la misma voz, y sin saldo a mitad sigue con la gratis ----------
hoja = tmp / "montar"
hoja.mkdir()
cobros, narrar_real = [], desde_prompt.narrar


def narrar_falso(texto, voz, destino, velocidad=1.0):
    cobros.append((texto, voz))
    if voz == BELLA and texto == "Sin saldo aquí":
        raise RuntimeError("sin saldo")
    Path(destino).write_bytes(b"audio")
    return [{"palabra": "hola", "inicio": 0, "fin": 1}]


desde_prompt.narrar = narrar_falso
audio = hoja / "video_final_voz_00.mp3"
assert desde_prompt._narrar_pagada("Hola", BELLA, audio) == [{"palabra": "hola", "inicio": 0, "fin": 1}] and len(cobros) == 1
assert desde_prompt._narrar_pagada("Hola", BELLA, audio) == [{"palabra": "hola", "inicio": 0, "fin": 1}] and len(cobros) == 1
desde_prompt._narrar_pagada("Otro texto", BELLA, audio)  # otro texto u otra voz: se narra
desde_prompt._narrar_pagada("Otro texto", ROGER, audio)
assert len(cobros) == 3
audio.with_suffix(".json").write_text("roto", encoding="utf-8")
assert desde_prompt.ya_narrada("Otro texto", ROGER, audio) is None  # un archivo roto: se narra otra vez
gratis_audio = hoja / "gratis.mp3"
desde_prompt._narrar_pagada("Hola", GRATIS, gratis_audio)
desde_prompt._narrar_pagada("Hola", GRATIS, gratis_audio)
assert not gratis_audio.with_suffix(".json").exists()  # lo gratis no se guarda: como siempre
desde_prompt.narrar = narrar_real

# ---------- La ventana de la voz en las páginas ----------
ventana = comun.VentanaVoz(None, GRATIS, "unos US$0.14")
assert ventana.usar_gratis.isDefault() and not ventana.usar_eleven.autoDefault()  # un Enter por despiste no gasta
assert all(not desde_prompt.es_eleven(ventana.gratis.itemData(i)) for i in range(ventana.gratis.count()))
assert ventana.eleven.count() == 3 and all(desde_prompt.es_eleven(ventana.eleven.itemData(i)) for i in range(3))
assert "unos US$0.14" in ventana.usar_eleven.text()
assert ventana.gratis.currentData() == GRATIS and ventana.eleven.currentData() == BELLA
ventana.usar_gratis.click()
assert ventana.elegida == GRATIS
ventana = comun.VentanaVoz(None, GRATIS, "x")
ventana.eleven.setCurrentIndex(ventana.eleven.findData(ROGER))
ventana.usar_eleven.click()
assert ventana.elegida == ROGER
ventana = comun.VentanaVoz(None, ROGER, "x")  # ya la tenía elegida en la página: en su lista, y Enter sigue siendo gratis
assert ventana.eleven.currentData() == ROGER and ventana.gratis.currentData() == GRATIS and ventana.usar_gratis.isDefault()
ventana = comun.VentanaVoz(None, "es-MX-JorgeNeural", "x")
assert ventana.gratis.currentData() == "es-MX-JorgeNeural"
# El costo puede depender de la voz (lo ya pagado con ella): el botón dice el de la que se elige
ventana = comun.VentanaVoz(None, GRATIS, lambda voz: f"costo de {voz}")
assert ventana.usar_eleven.text().endswith(f"costo de {BELLA}")
ventana.eleven.setCurrentIndex(ventana.eleven.findData(ROGER))
assert ventana.usar_eleven.text().endswith(f"costo de {ROGER}")
claves.elegir_por_defecto("voz_eleven", ROGER)
ventana = comun.VentanaVoz(None, GRATIS, "x")
assert ventana.eleven.currentData() == ROGER  # la última de ElevenLabs que eligió
sin_fija()

contestar = {}


def exec_falso(self):
    """Como el usuario: marca lo pedido en `contestar` y pulsa Seguir o Cancelar."""
    contestar["vista"] = contestar.get("vista", 0) + 1
    if contestar.get("cancela"):
        return 0
    self.recordar.setChecked(bool(contestar.get("recordar")))
    if contestar.get("eleven"):
        self.eleven.setCurrentIndex(self.eleven.findData(contestar["eleven"]))
    self.elegida = (self.eleven if contestar.get("eleven") else self.gratis).currentData()
    return 1


exec_real, comun.VentanaVoz.exec = comun.VentanaVoz.exec, exec_falso
assert comun.elegir_voz(None, GRATIS, "x") == GRATIS and contestar["vista"] == 1
contestar.update(cancela=True)
assert comun.elegir_voz(None, GRATIS, "x") is None
contestar.clear()
contestar.update(eleven=ROGER)
assert comun.elegir_voz(None, GRATIS, "x") == ROGER and claves.ajustes().get("voz_eleven") == ROGER
assert not desde_prompt.voz_preferida()  # sin «Usar siempre», la próxima vuelve a preguntar
contestar.update(recordar=True, vista=0)
assert comun.elegir_voz(None, GRATIS, "x") == ROGER and desde_prompt.voz_preferida() == ROGER and contestar["vista"] == 1
# Fija de ElevenLabs: no se pregunta cuál, pero sí lo que cuesta. Con «No» por defecto: un Enter no gasta
costos, question_real = [], QMessageBox.question


def pregunta_costo(padre, titulo, texto, botones, defecto):
    assert defecto == QMessageBox.No
    costos.append(texto)
    return contestar.get("costo", QMessageBox.Yes)


QMessageBox.question = pregunta_costo
assert comun.elegir_voz(None, ROGER, "unos US$0.14") == ROGER and contestar["vista"] == 1
assert costos == ["Narrar con «ElevenLabs · Roger» cuesta unos US$0.14. ¿Seguir?"], costos
contestar.update(costo=QMessageBox.No)
assert comun.elegir_voz(None, ROGER, "x") is None  # sin su sí no se paga
assert comun.elegir_voz(None, GRATIS, "x") == GRATIS and contestar["vista"] == 1  # la cambió a mano: gratis, sin pregunta
QMessageBox.question = question_real
contestar.pop("costo")
sin_fija()
contestar.clear()
contestar.update(recordar=True)  # también se puede dejar fija la gratis
assert comun.elegir_voz(None, GRATIS, "x") == GRATIS and desde_prompt.voz_preferida() == GRATIS
assert comun.elegir_voz(None, GRATIS, "x") == GRATIS and contestar["vista"] == 1
contestar.update(recordar=False, eleven=BELLA)
assert comun.elegir_voz(None, BELLA, "x") == BELLA and contestar["vista"] == 2  # pagar se pregunta
sin_fija()
estado("elevenlabs", "sin_saldo")  # sin saldo: no se pregunta y pasa a la gratis
contestar.clear()
assert comun.elegir_voz(None, BELLA, "x") == GRATIS and not contestar
estado("elevenlabs", "")

# El selector sigue la voz fija hasta que se elija otra a mano
selector = comun.SelectorVoz()
assert selector.currentData() == GRATIS and selector.findData(BELLA) >= 0
claves.elegir_por_defecto("voz_preferida", BELLA)
selector._cargar()
assert selector.currentData() == BELLA
# Poner la del trabajo no la deja pegada: la fija sigue mandando
selector.poner("es-MX-JorgeNeural")
assert selector.currentData() == "es-MX-JorgeNeural"
selector._cargar()
assert selector.currentData() == BELLA
# La que elige a mano en la lista, sí se respeta
selector.setCurrentIndex(selector.findData("es-MX-JorgeNeural"))
selector.activated.emit(selector.currentIndex())
selector._cargar()
assert selector.currentData() == "es-MX-JorgeNeural"
# Si la que eligió ya no está (quitó ElevenLabs), la fija o la de su idioma, no la primera de la lista
sin_fija()
selector.setCurrentIndex(selector.findData(ROGER))
selector.activated.emit(selector.currentIndex())
claves.borrar("elevenlabs")
selector._cargar()
assert selector.currentData() == desde_prompt.voz_por_defecto()
claves.guardar(ELEVEN)

# Crear con IA: la pregunta sale antes de empezar, cancelar no hace nada y la voz elegida llega al trabajo
datos_trabajo, generar_real = [], desde_prompt.generar


def generar_falso(aviso=None, **k):
    datos_trabajo.append(k)
    return {"tipo": "video", "formato": "9:16", "carpeta": str(tmp), "resultados": []}


def esperar(pagina):
    fin = time.monotonic() + 10
    while pagina.tarea and pagina.tarea.isRunning() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


desde_prompt.generar = generar_falso
crear = pagina_crear.PaginaCrear()
crear.prompt.setPlainText("un gato")
crear.segundos.setValue(30)
try:
    contestar.clear()
    contestar.update(cancela=True)
    crear._iniciar()
    assert contestar["vista"] == 1 and crear.tarea is None and not datos_trabajo
    contestar.clear()
    contestar.update(eleven=ROGER)
    crear._iniciar()
    esperar(crear)
    assert datos_trabajo[-1]["voz"] == ROGER and crear.voz.currentData() == ROGER and contestar["vista"] == 1
    # Y la siguiente vez no queda pegada: al volver a la página sale la gratis (un Enter no gasta)
    crear.voz._cargar()
    assert crear.voz.currentData() == GRATIS
    assert "Voz de ElevenLabs: unos US$0.14 de tu cuenta." in crear.antes.text(), crear.antes.text()
    # Escenas que hablan: su voz es la de su IA de video, no se pregunta
    contestar.clear()
    crear.animado.setChecked(True)
    pagar_real, crear._pagar_video = crear._pagar_video, lambda f, d: True
    crear._iniciar()
    esperar(crear)
    crear._pagar_video = pagar_real
    assert not contestar and desde_prompt.es_eleven(datos_trabajo[-1]["voz"]) is False
    crear.animado.setChecked(False)
    # Sin narración: tampoco
    contestar.clear()
    crear.prompt.setPlainText("un gato sin narración")
    crear._iniciar()
    esperar(crear)
    assert not contestar
finally:
    desde_prompt.generar = generar_real

# ---------- Las series: el narrador y sus personajes; cada capítulo pregunta su costo ----------
ids = []
BIBLIA = {"titulo": "Los Panas", "sinopsis": "s", "personajes": [
    {"nombre": "Kaito", "descripcion": "swordsman", "personalidad": "Callado", "genero": "hombre"},
    {"nombre": "Yara", "descripcion": "archer", "personalidad": "Valiente", "genero": "mujer"},
    {"nombre": "Luz", "descripcion": "mage", "personalidad": "Lista", "genero": "mujer"}]}


def dibujar(prompt, ancho, alto, destino):
    imagen = QImage(8, 8, QImage.Format_RGB32)
    imagen.fill(QColor("#7C5CFF"))
    imagen.save(str(destino))
    return destino


imagen_real, ia.imagen = ia.imagen, dibujar
try:
    r = serie.crear_serie("Los Panas", "", biblia=BIBLIA, voz=BELLA)
    _, datos = serie._abrir(r["nombre"])
    assert datos["narrador"] == BELLA
    voces_de = {p["nombre"]: p["voz"] for p in datos["personajes"]}
    assert voces_de == {"Kaito": ROGER, "Yara": "eleven:sarah", "Luz": "eleven:sarah"}, voces_de  # Bella es la narradora
    assert serie.usa_eleven(r["nombre"]) and not serie.usa_eleven("no existe")
    # El capítulo de esa serie: su costo se pregunta, y sin saldo ni empieza
    costo_cap = director.costo("crear_episodio", {"serie_nombre": r["nombre"], "planos": 12})
    assert costo_cap == "Esto cuesta unos US$1.44. ¿Lo hago?", costo_cap  # el máximo: 12 planos de 400 letras
    # Con su guion, lo que trae
    assert director.costo_voz("crear_episodio", {"serie_nombre": r["nombre"], "guion": {"planos": [
        {"descripcion": "a", "personajes": [], "habla": "Narrador", "texto": "x" * 100}]}}) == 100 / 1000 * 0.30
    # Rehacer uno ya escrito: solo lo que falte por narrar. Lo ya pagado no se paga otra vez
    carpeta_serie, _ = serie._abrir(r["nombre"])
    ep_uno = carpeta_serie / "episodios" / "01"
    ep_uno.mkdir(parents=True)
    guion_uno = {"titulo": "T", "resumen": "R", "planos": [
        {"descripcion": "a", "personajes": [], "habla": "Narrador", "texto": "Uno dos tres"},
        {"descripcion": "b", "personajes": [], "habla": "Narrador", "texto": "Cuatro cinco"}]}
    (ep_uno / "guion.json").write_text(json.dumps(guion_uno), encoding="utf-8")
    (ep_uno / "episodio.json").write_text("{}", encoding="utf-8")
    uno = {"serie_nombre": r["nombre"], "numero": 1}
    assert serie.letras_capitulo(r["nombre"], 12, 1) == len("Uno dos tres") + len("Cuatro cinco")
    audio = ep_uno / "video_final_voz_00.mp3"
    audio.write_bytes(b"x")
    audio.with_suffix(".json").write_text(json.dumps({"para": ["Uno dos tres", BELLA, 1.0], "palabras": []}), encoding="utf-8")
    assert serie.letras_capitulo(r["nombre"], 12, 1) == len("Cuatro cinco")
    assert serie.letras_plano(str(ep_uno), 0) == 0 and serie.letras_plano(str(ep_uno), 1) == len("Cuatro cinco")
    assert serie.letras_plano(str(ep_uno), 99) == 0 and director.costo_voz("crear_episodio", uno) > 0
    audio2 = ep_uno / "video_final_voz_01.mp3"
    audio2.write_bytes(b"x")
    audio2.with_suffix(".json").write_text(json.dumps({"para": ["Cuatro cinco", BELLA, 1.0], "palabras": []}), encoding="utf-8")
    assert director.costo("crear_episodio", uno) is None  # ya está todo pagado
    assert "voz_eleven" not in director.usos("crear_episodio", uno)
    assert "voz_eleven" in director.usos("crear_episodio", {"serie_nombre": r["nombre"]})
    assert director.impide("crear_episodio", {"serie_nombre": r["nombre"]}) is None
    estado("elevenlabs", "sin_saldo")
    assert "No se puede hacer el capítulo con sus voces" in director.impide("crear_episodio", {"serie_nombre": r["nombre"]})
    estado("elevenlabs", "")
    # Una serie con voces gratis: como siempre, y su capítulo no cuesta voz
    gratis = serie.crear_serie("Gratis", "", biblia=BIBLIA, voz="es-MX-JorgeNeural")
    _, datos = serie._abrir(gratis["nombre"])
    assert datos["narrador"] == "es-MX-JorgeNeural" and not any(desde_prompt.es_eleven(p["voz"]) for p in datos["personajes"])
    assert not serie.usa_eleven(gratis["nombre"]) and director.costo("crear_episodio", {"serie_nombre": gratis["nombre"]}) is None
    assert "voz_eleven" not in director.usos("crear_episodio", {"serie_nombre": gratis["nombre"]})
    # Una cuenta conectada antes de guardar el género: se lee una vez, sin añadir voces que la serie no reconocería
    sin_genero = {**ELEVEN, "voces": [{k: v for k, v in x.items() if k != "genero"} for x in ELEVEN["voces"]]}
    claves.guardar(sin_genero)
    leer_real = claves.voces_elevenlabs
    claves.voces_elevenlabs = lambda clave: [*ELEVEN["voces"], {"id": "nueva", "nombre": "Nueva", "genero": "male"}]
    personajes = [{"nombre": "A"}, {"nombre": "B"}]
    serie._asignar_eleven(personajes, ["hombre", "mujer"], BELLA)
    assert [p["voz"] for p in personajes] == [ROGER, "eleven:sarah"], personajes
    claves.voces_elevenlabs = lambda clave: (_ for _ in ()).throw(RuntimeError("sin red"))  # sin red, igual sale
    personajes = [{"nombre": "A"}]
    serie._asignar_eleven(personajes, ["hombre"], BELLA)
    assert personajes[0]["voz"] in (ROGER, "eleven:sarah")
    claves.voces_elevenlabs = leer_real
    claves.guardar(ELEVEN)

    # La página: pregunta al crear la serie y la voz llega; el capítulo con ElevenLabs pregunta su costo
    pagina = pagina_serie.PaginaSerie()
    contestar.clear()
    contestar.update(eleven=ROGER)
    pagina.idea.setPlainText("Un pana y su perro")
    crear_real, serie.crear_serie = serie.crear_serie, lambda aviso=None, **k: ids.append(k) or {
        "nombre": r["nombre"], "tipo": "serie", "resultados": []}
    pagina._crear_serie()
    esperar(pagina)
    serie.crear_serie = crear_real
    assert ids[-1]["voz"] == ROGER and contestar["vista"] == 1, ids
    preguntas_cap, question_real = [], QMessageBox.question
    QMessageBox.question = lambda padre, titulo, texto, botones, defecto: preguntas_cap.append((texto, defecto)) or QMessageBox.No
    episodio = serie.crear_episodio
    assert not pagina._voz_del_trabajo(episodio, "crear_episodio", {"serie": r["nombre"], "planos": 12})
    assert preguntas_cap == [("Esto se narra con voces de ElevenLabs: hasta unos US$1.44. ¿Seguir?", QMessageBox.No)], preguntas_cap
    preguntas_cap.clear()
    assert pagina._voz_del_trabajo(episodio, "crear_episodio", {"serie": gratis["nombre"], "planos": 12}) and not preguntas_cap
    # Rehacer un plano: si su voz ya está pagada no pregunta; si hay que narrarla, sí
    audio2.unlink()
    assert not pagina._voz_del_trabajo(serie.rehacer_plano, None, {"episodio": str(ep_uno), "i": 1})
    assert "hasta unos US$0.00" in preguntas_cap[-1][0], preguntas_cap
    preguntas_cap.clear()
    assert pagina._voz_del_trabajo(serie.rehacer_plano, None, {"episodio": str(ep_uno), "i": 0}) and not preguntas_cap
    QMessageBox.question = question_real
    # El idioma: el de su narrador, para el guion y para las voces de sus personajes
    capturas = []
    texto_real, ia.texto_json = ia.texto_json, lambda instrucciones, *a, **k: capturas.append(instrucciones) or BIBLIA
    ingles = serie.crear_serie("Friends", "x", voz="en-US-AndrewNeural")
    ia.texto_json = texto_real
    _, datos = serie._abrir(ingles["nombre"])
    assert "English" in capturas[0] and all(p["voz"].startswith("en-") for p in datos["personajes"]), datos["personajes"]
finally:
    ia.imagen = imagen_real
    comun.VentanaVoz.exec = exec_real
sin_fija()

# ---------- «Claves de IA»: dejar una voz fija o volver a preguntar ----------
pagina = pagina_claves.PaginaClaves()
pagina._refrescar()
# La rueda baja la página: no deja una voz fija sin querer
QApplication.sendEvent(pagina.voz_fija, QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                                                    Qt.NoModifier, Qt.NoScrollPhase, False))
assert pagina.voz_fija.currentData() == "" and "voz_preferida" not in claves.ajustes()
# Lo que dejó fijo en otra ventana se ve al volver a la página, y ahí se puede quitar
claves.elegir_por_defecto("voz_preferida", ROGER)
pagina._refrescar()
assert pagina.voz_fija.currentData() == ROGER and "Roger" in pagina.voz_fija.toolTip()
pagina.voz_fija.setCurrentIndex(0)
assert desde_prompt.voz_preferida() == ""
assert pagina.voz_fija.currentData() == "" and pagina.voz_fija.findData(BELLA) > 0 and pagina.voz_fija.findData(GRATIS) > 0
pagina.voz_fija.setCurrentIndex(pagina.voz_fija.findData(BELLA))
assert desde_prompt.voz_preferida() == BELLA
pagina._refrescar()
assert pagina.voz_fija.currentData() == BELLA  # y sigue tras volver a pintarse
pagina.voz_fija.setCurrentIndex(0)
assert desde_prompt.voz_preferida() == "" and claves.ajustes().get("voz_preferida") == ""
claves.elegir_por_defecto("voz_preferida", BELLA)
claves.borrar("elevenlabs")  # al quitar la clave, su voz deja de valer: vuelve a la gratis, sin romper nada
assert desde_prompt.voz_preferida() == "" and desde_prompt.voz_inicial() == GRATIS
pagina._refrescar()
assert pagina.voz_fija.currentData() == "" and pagina.voz_fija.findData(BELLA) == -1

print("Pruebas de la voz elegida pasadas.")
sys.stdout.flush()
os._exit(0)  # como visor y descargas: al cerrar, el reproductor de las páginas tumba Qt sin ventana de verdad
