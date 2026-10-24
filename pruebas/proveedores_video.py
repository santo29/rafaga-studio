"""Kling y Seedance (videos de pago) dentro del estudio, sin red ni claves: claves, rotación, animar, escenas que
hablan, costos, el MCP que pregunta antes de gastar y la interfaz. Sus módulos (motor/kling.py, motor/seedance.py)
se sustituyen por falsos con el mismo contrato: python -m pruebas.proveedores_video"""
import asyncio
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
import httpx  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

import motor  # noqa: E402
from motor import claves, desde_prompt, director, ia, nubes, video  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
tmp = Path(tempfile.mkdtemp(prefix="rafaga-video-pago-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
nubes.USO = tmp / "uso_nubes.json"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64  # pasa seguro.es_video
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def falla(funcion, *args, error=ValueError, **kw):
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


def esperar(condicion, plazo=10):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def no_autorizada(url):
    peticion = httpx.Request("GET", url)
    return httpx.HTTPStatusError("401", request=peticion, response=httpx.Response(401, request=peticion))


# ---------- Los módulos falsos, con el contrato de motor/kling.py y motor/seedance.py ----------
def modulo_falso(nombre: str, consola: str, modelos: list[dict]):
    m = types.ModuleType(f"motor.{nombre.lower()}")
    m.NOMBRE, m.CONSOLA, m.SEGUNDOS_CLIP, m.SEGUNDOS_VOZ, m.MODELOS = nombre, consola, 5, 8, modelos
    m.llamadas, m.valida, m.falla, m.hecho_con = [], {}, None, modelos[0]["id"]

    def validar(clave):
        m.llamadas.append(("validar", clave))
        if isinstance(m.valida, Exception):
            raise m.valida
        return dict(m.valida)

    def estimar(info, segundos, voz=False):
        campo = "voz" if voz else "mudo"
        ids = [x["id"] for x in modelos]
        desde = info.get("modelo_voz" if voz else "modelo_video")
        resto = modelos[ids.index(desde) if desde in ids else 0:]
        return max(x[campo] or 0 for x in resto) * segundos

    def animar(info, imagen, prompt, destino, segundos=5):
        m.llamadas.append(("animar", info.get("modelo_video"), Path(imagen), prompt, Path(destino), segundos))
        if m.falla:
            raise m.falla
        Path(destino).write_bytes(MP4)
        return m.hecho_con

    def hablar(info, imagen, prompt, destino, segundos=8):
        m.llamadas.append(("hablar", info.get("modelo_voz"), imagen, prompt, Path(destino), segundos))
        if m.falla:
            raise m.falla
        Path(destino).write_bytes(MP4)
        return m.hecho_con
    m.validar, m.estimar, m.animar, m.hablar = validar, estimar, animar, hablar
    return m


kling = modulo_falso("Kling", "https://kling.ai/dev/api-key",
                     [{"id": "kling-a", "mudo": 0.1, "voz": 0.2}, {"id": "kling-b", "mudo": 0.05, "voz": None}])
seedance = modulo_falso("Seedance", "https://console.example/ark/apiKey",
                        [{"id": "sd-a", "mudo": 0.2, "voz": 0.25}, {"id": "sd-b", "mudo": 0.03, "voz": None}])
for _nombre, _falso in (("kling", kling), ("seedance", seedance)):
    sys.modules[f"motor.{_nombre}"] = _falso
    setattr(motor, _nombre, _falso)
assert claves.modulo_video("kling") is kling and claves.modulo_video("seedance") is seedance

# ---------- Claves: Seedance por su formato exacto; Kling (sin formato conocido) solo con su botón ----------
ARK = "ark-0a1b2c3d-4e5f-6789-abcd-ef0123456789-AbC9z"
UUID = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
assert claves.candidatos(ARK) == ["seedance"]
for ajena in (UUID, UUID.upper(), f"ark-{UUID}", f"ark-{UUID}-AbC9zz", f"ark-{UUID.upper()}-AbC9z"):
    assert claves.candidatos(ajena) == [], ajena  # un UUID cualquiera nunca se manda a Kling ni a Seedance
assert "Kling o Seedance" in falla(claves.detectar, UUID) and not kling.llamadas and not seedance.llamadas

seedance.valida = {}
info = claves.detectar(ARK)  # la reconoce sola y la prueba solo en Seedance
assert seedance.llamadas == [("validar", ARK)] and not kling.llamadas
assert info["proveedor"] == "seedance" and info["usos"] == ["video", "video_voz"]
assert info["modelo_video"] == "sd-a" and info["modelo_voz"] == "sd-a"  # lo mejor de su catálogo

KLING = "KlingClave_0123456789abcdef"
kling.valida = {"base": "https://api-singapore.klingai.com", "proveedor": "otro"}  # lo de su módulo no pisa lo nuestro
info = claves.detectar(f"  {KLING}\n", "kling")
assert kling.llamadas == [("validar", KLING)] and info["base"] == "https://api-singapore.klingai.com"
assert info["proveedor"] == "kling" and info["clave"] == KLING and info["modelo_video"] == "kling-a"
assert info["modelo_voz"] == "kling-a"  # el primero que habla
kling.llamadas.clear()
# Con su botón no se le manda una clave que parece de otro servicio, ni texto pegado
for ajena, motivo in (("AIzaSyXXXXXXXXXXXXXXXX", "otro servicio"), ("sk_live_" + "a" * 24, "otro servicio"),
                      ("sk-ant-api03-xxxxxxxx", "otro servicio"), (ARK, "otro servicio"),
                      (f"{KLING} {KLING}", "sin espacios"), ("corta", "sin espacios")):
    assert motivo in falla(claves.detectar, ajena, "kling"), ajena
assert not kling.llamadas
falla(claves.detectar, KLING, "gemini")  # por aquí solo van Kling y Seedance
kling.valida = no_autorizada("https://api-singapore.klingai.com/tasks?task_ids=0")
assert "no funcionó" in falla(claves.detectar, KLING, "kling")
kling.valida = httpx.ConnectError("sin red")
assert "No hay conexión" in falla(claves.detectar, KLING, "kling")
peticion = httpx.Request("GET", "https://api-singapore.klingai.com/tasks")
kling.valida = httpx.HTTPStatusError("503", request=peticion, response=httpx.Response(503, request=peticion))
assert "503" in falla(claves.detectar, KLING, "kling")
kling.valida = {"base": "https://api-singapore.klingai.com"}
# Antes de que llegue su módulo (otra rama), un aviso claro en vez de un error raro
delattr(motor, "kling")
sys.modules["motor.kling"] = None
try:
    assert "todavía no trae Kling" in falla(claves.detectar, KLING, "kling")
finally:
    sys.modules["motor.kling"] = kling
    motor.kling = kling

# ---------- Solo eligiéndolos: Automático nunca los usa, y elegidos no tienen respaldo ----------
claves.guardar({"proveedor": "modal", "clave": "ak-a as-b", "usos": ["video"]})
claves.guardar(claves.detectar(KLING, "kling"))
claves.guardar(claves.detectar(ARK))
assert "kling" not in nubes.orden("video") and "seedance" not in nubes.orden("video")
assert {"kling", "seedance"} <= set(claves.opciones("video")) and {"kling", "seedance"} <= set(claves.opciones("video_voz"))
assert claves.para("video_voz") is None  # sin Gemini, Automático no tiene quien haga escenas que hablan
assert ia.video_de_pago() is None and not desde_prompt.con_voz_propia()
claves.elegir_por_defecto("video", "kling")
assert nubes.orden("video") == ["kling"] and ia.video_de_pago() == "kling"  # sin respaldo: nunca se paga dos veces
claves.elegir_por_defecto("video_voz", "seedance")
assert claves.para("video_voz")["proveedor"] == "seedance" and desde_prompt.proveedor_voz() == "seedance"
# Ya cobrado: rotar no prueba la siguiente opción (pagaría otra vez) y la nota de gasto lo cuenta
probadas = []
claves.guardar({"proveedor": "cloudflare", "clave": f"{'a' * 32} {'T' * 40}", "usos": ["imagen"]})
assert nubes.orden("imagen")[:2] == ["cloudflare", "huggingface"]
falla(nubes.rotar, "imagen", {"cloudflare": lambda: (_ for _ in ()).throw(ia.Cobrado("no llegó")),
                              "huggingface": lambda: probadas.append("huggingface")}, error=ia.Cobrado)
assert not probadas
claves.borrar("cloudflare")

# ---------- Animar una escena con Kling: su clip de 5 s, y el modelo que funcionó se guarda ----------
foto = tmp / "escena.png"
foto.write_bytes(PNG)
kling.hecho_con = "kling-b"  # la cuenta no tenía kling-a: su módulo lo saltó sin pagar
clip = ia.video_desde_imagen(foto, "a cat dancing", "9:16", 7.3, tmp / "clip.mp4")
assert clip == tmp / "clip.mp4" and clip.read_bytes() == MP4
_, modelo, imagen, prompt, destino, segundos = kling.llamadas[-1]
assert modelo == "kling-a" and imagen == foto and "a cat dancing" in prompt and segundos == kling.SEGUNDOS_CLIP
assert claves.cargar()["kling"]["modelo_video"] == "kling-b"  # la próxima vez empieza por el que funcionó
ia.video_desde_imagen(foto, "otra", "9:16", 3, tmp / "clip2.mp4")
assert kling.llamadas[-1][1] == "kling-b"
assert abs(ia.precio_video("kling") - 0.05 * 5) < 1e-9  # desde kling-b: sus respaldos (ninguno) no son más caros
kling.falla = ia.Cobrado("la descarga se cortó")
assert "se cortó" in falla(ia.video_desde_imagen, foto, "x", "9:16", 3, tmp / "c3.mp4", error=ia.Cobrado)
kling.falla = RuntimeError("Kling: no te queda saldo")
assert "no te queda saldo" in falla(ia.video_desde_imagen, foto, "x", "9:16", 3, tmp / "c4.mp4", error=RuntimeError)
kling.falla = None

# ---------- Escenas que hablan con Seedance (elegido); Gemini sigue siendo el de Automático ----------
seedance.llamadas.clear()
seedance.hecho_con = "sd-a"
hablado = ia.video_hablado('Una manzana dice: "Hola"', "9:16", tmp / "voz.mp4", foto)
assert hablado == tmp / "voz.mp4" and seedance.llamadas[-1][2] == foto and seedance.llamadas[-1][5] == 8
assert '"Hola"' in seedance.llamadas[-1][3]
assert abs(ia.precio_video("seedance", voz=True) - 0.25 * 8) < 1e-9
escenas, costo = desde_prompt.costo_hablado(40)
assert escenas == 5 and abs(costo - 5 * 0.25 * 8) < 1e-9
assert desde_prompt.con_voz_propia()
claves.elegir_por_defecto("video_voz", "auto")
falla(ia.video_hablado, "x", "9:16", tmp / "voz2.mp4", error=ia.SinClave)  # Automático: Gemini, nunca Seedance
assert len(seedance.llamadas) == 1
assert "Kling o Seedance" in falla(desde_prompt.generar, "", guion={"titulo": "t", "descripcion": "d", "hashtags": [],
                                   "estilo_visual": "e", "escenas": [{"narracion": "n", "imagen": "i"}]},
                                   animado=True, error=ia.SinClave)
assert abs(ia.precio_video("gemini", voz=True) - 10 * ia.PRECIO_OMNI) < 1e-9 and ia.precio_video("huggingface") == 0
claves.elegir_por_defecto("video_voz", "seedance")

# ---------- Montar: tope de clips de pago por trabajo, nota de gasto y nada se paga dos veces ----------
reales = desde_prompt.narrar, video.duracion, video.escena_de_clip, video.escena_de_imagen, video.unir
desde_prompt.narrar = lambda texto, voz, destino: []
video.duracion = lambda p: 1.0
video.escena_de_clip = lambda clip, audio, formato, palabras, escena: escena
video.escena_de_imagen = lambda img, audio, formato, palabras, escena, i: escena
video.unir = lambda partes, destino: destino


def dibujar(prompt, ancho, alto, destino):  # como en serie: lo que ya está dibujado no se vuelve a pedir
    if not destino.is_file():
        destino.write_bytes(PNG)
    return destino


guion = {"estilo_visual": "cartoon", "escenas": [{"narracion": f"n{i}", "imagen": f"scene {i}"} for i in range(20)]}
try:
    kling.llamadas.clear()
    carpeta, notas = tmp / "trabajo", []
    carpeta.mkdir()
    desde_prompt.montar(guion, carpeta, "9:16", "es-DO-EmilioNeural", lambda *a: None, crear_imagen=dibujar,
                        notas=notas)
    assert len(kling.llamadas) == desde_prompt.MAX_CLIPS_PAGO == 15  # el resto, zoom suave
    assert any("tope de gasto" in n for n in notas)
    assert f"Kling hizo 15 clip(s) de video: hasta unos US${15 * 0.25:.2f}" in " ".join(notas), notas
    # Reintento en la misma carpeta: las 15 ya animadas desde esa misma imagen no se pagan otra vez (solo las 5 que
    # quedaron con zoom, en este trabajo nuevo)
    notas.clear()
    desde_prompt.montar(guion, carpeta, "9:16", "es-DO-EmilioNeural", lambda *a: None, crear_imagen=dibujar,
                        notas=notas)
    assert len(kling.llamadas) == 20 and {ll[3].split(",")[0] for ll in kling.llamadas[15:]} == {
        f"scene {i}" for i in range(15, 20)} and any("Kling hizo 5 clip(s)" in n for n in notas), notas
    # Un plano redibujado (más nuevo que su clip viejo) sí se anima de nuevo: es otra imagen
    os.utime(carpeta / "video_final_imagen_03.png", (time.time() + 60, time.time() + 60))
    desde_prompt.montar(guion, carpeta, "9:16", "es-DO-EmilioNeural", lambda *a: None, crear_imagen=dibujar)
    assert len(kling.llamadas) == 21 and kling.llamadas[-1][3].startswith("scene 3,")
    # Varios montajes de un mismo trabajo (anuncios: uno por variante) comparten el tope; lo cobrado sin llegar cuenta
    kling.llamadas.clear()
    pagados, notas = {"clips": 0}, []
    for k in range(2):
        (tmp / f"anuncio{k}").mkdir()
        desde_prompt.montar({**guion, "escenas": guion["escenas"][:10]}, tmp / f"anuncio{k}", "9:16",
                            "es-DO-EmilioNeural", lambda *a: None, crear_imagen=dibujar, notas=notas,
                            pagados=pagados, nombre="base")
    assert len(kling.llamadas) == 15 and pagados["clips"] == 15
    kling.llamadas.clear()
    kling.falla = ia.Cobrado("se cortó la descarga")
    notas, carpeta = [], tmp / "cobrado"
    carpeta.mkdir()
    desde_prompt.montar({**guion, "escenas": guion["escenas"][:3]}, carpeta, "9:16", "es-DO-EmilioNeural",
                        lambda *a: None, crear_imagen=dibujar, notas=notas)
    assert len(kling.llamadas) == 1 and any("Kling hizo 1 clip(s)" in n for n in notas), notas  # y no reintenta
    kling.falla = None
finally:
    desde_prompt.narrar, video.duracion, video.escena_de_clip, video.escena_de_imagen, video.unir = reales

# ---------- El costo que pregunta el Director (y el MCP): animar con Kling y hablar con Seedance ----------
precio_clip = ia.precio_video("kling")
assert f"US${10 * precio_clip:.2f}" in director.costo("crear_video", {"prompt": "x", "segundos": 45})  # 10 escenas
assert f"US${precio_clip:.2f}" in director.costo("crear_video", {"imagen": "a.png", "solo_animar": True})
assert f"US${15 * precio_clip:.2f}" in director.costo("crear_episodio", {"planos": 40})  # tope por trabajo
assert f"US${15 * precio_clip:.2f}" in director.costo("crear_episodio", {"planos": 3, "numero": 2})  # rehacer
assert f"US${15 * precio_clip:.2f}" in director.costo("crear_anuncios", {"variantes": 6, "segundos": 90})
assert director.costo("crear_serie", {}) is None and director.costo("crear_cancion", {"idea": "x"}) is None
animado = director.costo("crear_video", {"prompt": "x", "segundos": 16, "animado": True})
assert f"US${2 * 0.25 * 8 + 2 * precio_clip:.2f}" in animado, animado  # 2 escenas que hablan y, por lo alto, animadas
assert "DE PAGO" in director.INSTRUCCIONES and "US$1 por cada 8 s" not in director.INSTRUCCIONES

# ---------- MCP: lo que cuesta no se hace sin confirmar_gasto=true ----------
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

import mcp_server  # noqa: E402

hechos = []
generar_real, animar_real = desde_prompt.generar, desde_prompt.animar_imagen
desde_prompt.generar = lambda *a, **k: hechos.append(k) or {"tipo": "video", "resultados": []}
desde_prompt.animar_imagen = lambda *a, **k: hechos.append(a) or {"tipo": "animacion", "resultados": []}
try:
    error = falla(mcp_server.crear_video, "un gato", error=ToolError)
    assert "confirmar_gasto=true" in error and f"US${10 * precio_clip:.2f}" in error and not hechos, error
    assert "US$" in falla(mcp_server.crear_video, "x", "9:16", 45, "es-DO-EmilioNeural", str(foto), True,
                          error=ToolError) and not hechos  # también con los argumentos por posición
    json.loads(mcp_server.crear_video("un gato", confirmar_gasto=True))
    assert len(hechos) == 1
    try:  # como llega de un agente de verdad: por el protocolo
        asyncio.run(mcp_server.mcp.call_tool("crear_video", {"prompt": "un gato"}))
        raise AssertionError("debió pedir confirmación")
    except ToolError as e:
        assert "confirmar_gasto=true" in str(e)
    asyncio.run(mcp_server.mcp.call_tool("crear_video", {"prompt": "un gato", "confirmar_gasto": True}))
    assert len(hechos) == 2
    asyncio.run(mcp_server.mcp.call_tool("crear_video", {"prompt": "x", "imagen": str(foto), "solo_animar": True,
                                                         "confirmar_gasto": True}))
    assert len(hechos) == 3
    # Lo gratis va directo; guardar en la memoria también se le pregunta al usuario
    assert "proveedores" in json.loads(mcp_server.listar_opciones())
    assert "memoria" in falla(mcp_server.recordar_preferencia, "general", "títulos cortos", error=ToolError)
    herramientas_mcp = {h.name: h for h in asyncio.run(mcp_server.mcp.list_tools())}
    assert all("confirmar_gasto" in h.input_schema["properties"] for h in herramientas_mcp.values())
    assert "confirmar_gasto" not in str(director.catalogo())  # el Director de la app pregunta por su cuenta
    claves.elegir_por_defecto("video", "auto")  # animar gratis: el MCP no pregunta nada
    json.loads(mcp_server.crear_video("un gato"))
    assert len(hechos) == 4
    claves.elegir_por_defecto("video", "kling")
finally:
    desde_prompt.generar, desde_prompt.animar_imagen = generar_real, animar_real

# ---------- La interfaz ----------
from PySide6.QtGui import QDesktopServices  # noqa: E402

from motor import musica  # noqa: E402
from ui.paginas import claves as pagina_claves  # noqa: E402
from ui.paginas import inicio  # noqa: E402
from ui.paginas.crear import PaginaCrear  # noqa: E402

# Claves de IA: sus filas, su botón «Conectar» (clave oculta, otro hilo) y el selector «Escenas que hablan»
claves.borrar("kling")
pagina = pagina_claves.PaginaClaves()
assert set(pagina.botones_pago) == {"kling", "seedance"} and "video_voz" in pagina.selectores
assert pagina.selectores["video_voz"].itemText(0) == "Automático (Gemini, si está conectada)"
pedidas, abiertas = [], []
dialogo_real, abrir_real = QInputDialog.getText, QDesktopServices.openUrl
QInputDialog.getText = lambda *a: pedidas.append(a) or (f" {KLING} ", True)
QDesktopServices.openUrl = lambda url: abiertas.append(url.toString())
try:
    kling.llamadas.clear()
    pagina.botones_pago["kling"].click()
    esperar(lambda: "kling" in claves.cargar())
    assert pedidas[0][3] == pagina_claves.QLineEdit.Password and kling.llamadas == [("validar", KLING)]
    esperar(lambda: not pagina.tarea.isRunning())
    assert "kling" in [pagina.selectores["video"].itemData(i) for i in range(pagina.selectores["video"].count())]
    pagina._abrir_consola(None, "seedance")
    assert abiertas == [seedance.CONSOLA]
finally:
    QInputDialog.getText, QDesktopServices.openUrl = dialogo_real, abrir_real
claves.elegir_por_defecto("video", "kling")
precio_clip = ia.precio_video("kling")  # conectada otra vez: empieza por su mejor modelo (y el más caro)
assert abs(precio_clip - 0.1 * 5) < 1e-9

# Crear: la casilla dice quién hace las escenas que hablan, y todo trabajo que anima con Kling pregunta antes
crear = PaginaCrear()
assert "Seedance" in crear.animado.text() and "Gemini" not in crear.animado.text()
preguntas, respuesta = [], [QMessageBox.No]
pregunta_real = QMessageBox.question
QMessageBox.question = lambda padre, titulo, texto, *a: preguntas.append(texto) or respuesta[0]
try:
    assert crear.lanzar(crear.iniciar, desde_prompt.animar_imagen, imagen=str(foto), prompt="x") is False
    assert crear.tarea is None and "1 escena(s) con Kling" in preguntas[-1]
    assert f"US${precio_clip:.2f}" in preguntas[-1]
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45}) is False
    assert f"hasta 10 escena(s) con Kling: hasta unos US${10 * precio_clip:.2f}" in preguntas[-1]
    antes = len(preguntas)
    assert crear._pagar_video(musica.crear, {"idea": "x"})  # no anima escenas: ni se pregunta
    respuesta[0] = QMessageBox.Yes
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45}) and len(preguntas) == antes + 1
    claves.elegir_por_defecto("video", "auto")
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45}) and len(preguntas) == antes + 1  # gratis
    claves.elegir_por_defecto("video", "kling")
finally:
    QMessageBox.question = pregunta_real

# Inicio: el video con IA dice que es Kling, y lo pagado no cuenta como «uso gratis»
nubes.USO.write_text(json.dumps({"fecha": time.strftime("%Y-%m-%d"), "kling": 4, "huggingface": 1}), encoding="utf-8")
ind = {i["titulo"]: i for i in inicio.indicadores()}
assert ind["Video con IA"]["valor"] == "Kling (de pago)" and not ind["Video con IA"]["conectar"]
assert ind["Uso gratis de hoy"]["valor"] == "1 creaciones" and "Kling" not in ind["Uso gratis de hoy"]["detalle"]
print("Pruebas de Kling y Seedance pasadas.")
