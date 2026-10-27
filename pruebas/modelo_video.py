"""El selector «Modelo de video» (Director y Crear con IA, como en CapCut) y modelo_video del MCP, sin red ni claves de
verdad: solo lo conectado y con su precio, Automático por defecto, lo de pago pregunta antes su costo y llega al
trabajo, lo gratis no pregunta, un «sin saldo» recordado se ve y no deja empezar, y «Claves de IA» nunca cambia.
python -m pruebas.modelo_video"""
import asyncio
import json
import os
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from motor import claves, desde_prompt, director, ia, memoria, nube, nubes  # noqa: E402
from ui import comun  # noqa: E402
from ui.paginas import crear as pagina_crear  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
tmp = Path(tempfile.mkdtemp(prefix="rafaga-modelo-video-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
nubes.USO, nube.USO, memoria.ARCHIVO = tmp / "uso_nubes.json", tmp / "uso_nube.json", tmp / "memoria.json"


def esperar(condicion, plazo=10):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def falla(funcion, *args, error=ValueError, **kw) -> str:
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


def elegir(selector, modelo):
    """Como el usuario: abre la lista y pulsa ese modelo."""
    selector.recargar()
    next(a for a in selector.menu().actions() if a.data() == modelo).trigger()


# Conectados: Kling (de pago), Gemini (Omni) y Modal. Ni Seedance ni Pollinations: no salen
claves.guardar({"proveedor": "kling", "clave": "clave-kling-de-prueba", "usos": ["video", "video_voz"],
                "modelo_video": "kling-3.0", "base": "https://api-singapore.klingai.com"})
claves.guardar({"proveedor": "gemini", "clave": "AIzaSyPRUEBA0000000000000000000000000", "usos": ["texto", "musica"]})
claves.guardar({"proveedor": "modal", "clave": "ak-AAA111 as-BBB222", "usos": ["video"]})

# ---------- La lista: Automático, Sin animar y solo lo conectado, con su precio ----------
precio = ia.precio_video("kling")  # el mismo número que la pregunta de costo
assert abs(precio - 0.112 * 5) < 1e-9  # Kling 3.0 puede pasar a 3.0 Turbo: lo más que cuesta un clip
lista = claves.modelos_video()
ids, nombres = [m["id"] for m in lista], {m["id"]: m["nombre"] for m in lista}
assert ids == ["auto", "ninguno", "huggingface", "modal", "kling", "gemini"], ids
assert nombres["auto"] == "Automático (el estudio elige: gratis primero)"
assert nombres["ninguno"] == "Sin animar (fotos con movimiento, gratis)"
assert nombres["huggingface"] == "Hugging Face · gratis, cupo diario"
assert nombres["modal"] == "Mi nube Modal · gratis, quedan 3 de 3 hoy"
assert nombres["kling"] == f"Kling 3.0 · hasta US${precio:.2f} por clip", nombres["kling"]
assert nombres["gemini"] == "Gemini Omni · US$0.10 por segundo, habla"
assert not any(m["estado"] for m in lista)
nube.USO.write_text(json.dumps({"fecha": time.strftime("%Y-%m-%d"), "clips": 1}), encoding="utf-8")
assert claves.nombre_modelo_video("modal") == "Mi nube Modal · gratis, quedan 2 de 3 hoy"
assert claves.nombre_modelo("seedance-1-0-pro-fast-251015") == "Seedance 1.0 Pro Fast"
assert claves.nombre_modelo("dreamina-seedance-2-0-mini-260615") == "Seedance 2.0 Mini"
assert claves.nombre_modelo("kling-3.0-turbo") == "Kling 3.0 Turbo"
# Seedance 1.0 Pro Fast: 5 s × US$0.023 = 0.115, que redondeado dice 0.11; lo más que cuesta se dice hacia arriba
claves.guardar({"proveedor": "seedance", "clave": "ark-prueba", "usos": ["video", "video_voz"],
                "modelo_video": "seedance-1-0-pro-fast-251015"})
assert claves.nombre_modelo_video("seedance") == "Seedance 1.0 Pro Fast · hasta US$0.12 por clip"
claves.borrar("seedance")

# ---------- Solo para un trabajo, en su hilo: «Claves de IA» no cambia ----------
with claves.por_trabajo("kling"):
    assert ia.video_de_pago() == "kling" and nubes.orden("video") == ["kling"]
    assert desde_prompt.proveedor_voz() == "kling"  # sus escenas que hablan, también con Kling
    otro_hilo = []
    hilo = threading.Thread(target=lambda: otro_hilo.append(ia.video_de_pago()))
    hilo.start()
    hilo.join()
    assert otro_hilo == [None]  # otro trabajo a la vez (el MCP, otra página) sigue con lo suyo
    claves.elegir_por_defecto("limite_nube_diario", 3)  # guardar otro ajuste a mitad no guarda el modelo del trabajo
assert ia.video_de_pago() is None and "video" not in claves._guardados() and "video_voz" not in claves._guardados()
with claves.por_trabajo("gemini"):  # Omni: solo las escenas que hablan; lo mudo, lo de «Claves de IA»
    assert desde_prompt.proveedor_voz() == "gemini" and ia.video_de_pago() is None
with claves.por_trabajo("modal"):
    assert nubes.orden("video") == ["modal"]  # elegida tu nube: nunca se suben por detrás a un Space público
with claves.por_trabajo("ninguno"):
    assert ia.video_desde_imagen(tmp / "x.png", "x", "9:16", 5, tmp / "x.mp4") is None
for raro in ("auto", None, "sora", ["kling"], 3):  # lo que no es un modelo: lo de «Claves de IA»
    with claves.por_trabajo(raro):
        assert claves.ajustes() == claves._guardados()

# ---------- El selector: Automático por defecto, recordado por página, y «Conectar más modelos…» ----------
abiertas = []
comun.SelectorModelo.ir_a_claves = lambda: abiertas.append("claves")
sel = comun.SelectorModelo("director")
acciones = [a for a in sel.menu().actions() if a.isCheckable()]
assert sel.valor() == "auto" and sel.text() == "Automático" and sel.property("icono") == "clapperboard"
assert [a.data() for a in acciones] == ids and acciones[0].isChecked() and not any(a.isChecked() for a in acciones[1:])
assert [a.text() for a in acciones][4] == nombres["kling"]
conectar = [a for a in sel.menu().actions() if not a.isCheckable() and not a.isSeparator()]
assert [a.text() for a in conectar] == ["Conectar más modelos…"]
conectar[0].trigger()
assert abiertas == ["claves"]
cambios = []
sel.cambio.connect(cambios.append)
elegir(sel, "kling")
assert sel.valor() == "kling" and cambios == ["kling"] and sel.text() == "Kling 3.0"
assert nombres["kling"] in sel.toolTip()
assert claves._guardados()["modelo_video_director"] == "kling" and "video" not in claves._guardados()
assert comun.SelectorModelo("director").valor() == "kling"  # recordado en ajustes.json
assert comun.SelectorModelo("crear").valor() == "auto"  # cada página lo suyo
claves.elegir_por_defecto("modelo_video_crear", "pollinations")  # uno que ya no está conectado: Automático
assert comun.SelectorModelo("crear").valor() == "auto"
claves.elegir_por_defecto("modelo_video_crear", "auto")

# ---------- Un «sin saldo» recordado: se ve junto al modelo y el trabajo ni empieza (ni pregunta) ----------
claves.recordar("kling", 402, "Account balance not enough")
assert next(m for m in claves.modelos_video() if m["id"] == "kling")["estado"] == "sin_saldo"
sel.recargar()
assert next(a for a in sel.menu().actions() if a.data() == "kling").text() == f"{nombres['kling']}  ·  Sin saldo"
assert sel.text() == "Kling 3.0 · Sin saldo"
crear = pagina_crear.PaginaCrear()
errores, preguntas, respuesta, hechos = [], [], [QMessageBox.No], []
error_real, pregunta_real, generar_real = comun.mensaje_error, QMessageBox.question, desde_prompt.generar
mensaje_real, texto_real = pagina_crear.mensaje, ia.texto_json
comun.mensaje_error = lambda *a: errores.append(a)
QMessageBox.question = lambda padre, titulo, texto, *a: preguntas.append(texto) or respuesta[0]
pagina_crear.mensaje = lambda *a: errores.append(a)


def generar_falso(*a, **k):
    """Lo que ve el trabajo en su hilo: quién anima, en qué orden, quién habla y lo guardado en «Claves de IA»."""
    hechos.append({**k, "pago": ia.video_de_pago(), "orden": nubes.orden("video"),
                   "voz_de": desde_prompt.proveedor_voz(), "video": claves.ajustes().get("video", "auto"),
                   "guardado": claves._guardados().get("video", "auto")})
    return {"tipo": "video", "resultados": []}


desde_prompt.generar = generar_falso
try:
    assert crear.modelo.valor() == "auto" and crear.animado.isChecked()  # Gemini conectada: escenas que hablan
    crear.prompt.setPlainText("un gato que baila")
    crear.animado.setChecked(False)
    elegir(crear.modelo, "kling")
    crear._iniciar()
    assert crear.tarea is None and not preguntas and errores[-1][1] == "No se puede empezar", errores
    assert errores[-1][2].startswith("No se puede animar con Kling, el modelo de video elegido: Kling no tiene "
                                     "saldo"), errores[-1][2]
    assert "O elige otro modelo de video. No se cobró nada." in errores[-1][2]
    claves.recordar("kling", 200)  # recargó: vuelve a funcionar
    assert not next(m for m in claves.modelos_video() if m["id"] == "kling")["estado"]

    # ---------- De pago: la misma pregunta de costo de siempre y, con el sí, el trabajo anima con Kling ----------
    crear._iniciar()
    assert crear.tarea is None and len(preguntas) == 1 and not hechos
    assert f"Escenas que se animarán con Kling: hasta 10, por unos US${10 * precio:.2f}" in preguntas[-1], preguntas
    respuesta[0] = QMessageBox.Yes
    crear._iniciar()
    esperar(lambda: hechos and not crear.tarea.isRunning())
    assert len(preguntas) == 2 and hechos[-1]["pago"] == "kling" and hechos[-1]["orden"] == ["kling"]
    assert hechos[-1]["guardado"] == "auto" and hechos[-1]["animado"] is False
    assert hechos[-1]["prompt"] == "un gato que baila"
    assert ia.video_de_pago() is None and "video" not in claves._guardados()  # fuera del trabajo, lo de siempre

    # Gemini Omni: marca «Video animado con IA» (dice Gemini y su precio) y pregunta lo de las escenas que hablan
    elegir(crear.modelo, "gemini")
    assert crear.animado.isChecked() and "(Gemini, de pago" in crear.animado.text()
    with claves.por_trabajo("gemini"):
        escenas, costo = desde_prompt.costo_hablado(45)
    crear._iniciar()
    esperar(lambda: len(hechos) == 2 and not crear.tarea.isRunning())
    assert len(preguntas) == 3 and f"Escenas animadas con voz en Gemini: {escenas}, hasta unos US${costo:.2f}" in \
        preguntas[-1], preguntas[-1]
    assert hechos[-1]["voz_de"] == "gemini" and hechos[-1]["animado"] is True and hechos[-1]["pago"] is None
    elegir(crear.modelo, "kling")
    assert "(Kling, de pago" in crear.animado.text()  # las escenas que hablan, también con el modelo elegido

    # ---------- Gratis: nunca pregunta (lo que habla, de pago, se desmarca) y el trabajo usa lo elegido ----------
    for modelo, primero in (("modal", "modal"), ("huggingface", "huggingface")):
        crear.animado.setChecked(True)
        elegir(crear.modelo, modelo)
        assert not crear.animado.isChecked()
        crear._iniciar()
        esperar(lambda n=len(hechos): len(hechos) == n + 1 and not crear.tarea.isRunning())
        assert len(preguntas) == 3 and hechos[-1]["orden"][0] == primero and hechos[-1]["pago"] is None, hechos[-1]
    crear.animado.setChecked(True)
    elegir(crear.modelo, "ninguno")
    assert not crear.animado.isChecked()  # Sin animar: nada que hable
    otra = pagina_crear.PaginaCrear()
    assert otra.modelo.valor() == "ninguno" and not otra.animado.isChecked()  # recordado: la página nueva, igual
    crear._iniciar()
    esperar(lambda: len(hechos) == 5 and not crear.tarea.isRunning())
    assert len(preguntas) == 3 and hechos[-1]["video"] == "ninguno" and hechos[-1]["guardado"] == "auto"
    crear.imagen.setText(str(Path(__file__).resolve().parent.parent / "assets" / "icono.png"))
    crear.modo.setCurrentIndex(1)  # solo animar la imagen con «Sin animar»: se dice, sin empezar nada
    crear._iniciar()
    assert errores[-1][1] == "Elige un modelo de video" and len(hechos) == 5
    crear.imagen.setText("")
    crear.modo.setCurrentIndex(0)

    # ---------- El Director: usa el modelo del selector (nunca el que escriba la IA) y lo dice en el chat ----------
    def pasos(*lista):
        vistos = []

        def pensar(*a, **k):
            vistos.append(a)
            return dict(lista[min(len(vistos), len(lista)) - 1])
        return pensar
    VIDEO = {"mensaje": "Hago tu video.", "herramienta": "crear_video",
             "argumentos": json.dumps({"prompt": "un gato que baila", "modelo_video": "seedance"})}
    FIN = {"mensaje": "¡Listo!", "herramienta": "", "argumentos": "{}"}
    assert "modelo_video" not in director.catalogo()  # la IA ni lo ve: lo elige el usuario
    ia.texto_json = pasos(VIDEO, FIN)
    dichos, pedidas = [], []
    r = director.dirigir("un video de un gato que baila", confirmar=lambda p: pedidas.append(p) or True,
                         al_decir=dichos.append, modelo_video="kling")
    assert f"Para el video usaré: {nombres['kling']}." in dichos, dichos
    assert pedidas and pedidas[0].startswith(f"Esto cuesta unos US${10 * precio:.2f}"), pedidas
    assert r["pasos"][0]["argumentos"]["modelo_video"] == "kling" and hechos[-1]["pago"] == "kling"
    # Con Automático en el selector, la IA no puede elegir uno de pago: va gratis y sin preguntar
    ia.texto_json = pasos({**VIDEO, "argumentos": json.dumps({"prompt": "x", "modelo_video": "kling"})}, FIN)
    dichos, pedidas, n = [], [], len(hechos)
    director.dirigir("otro video", confirmar=lambda p: pedidas.append(p) or True, al_decir=dichos.append)
    assert len(hechos) == n + 1 and hechos[-1]["pago"] is None and not pedidas
    assert f"Para el video usaré: {nombres['auto']}." in dichos, dichos
    # Gemini Omni elegido: las escenas que hablan (de pago, con su pregunta)
    ia.texto_json = pasos({**VIDEO, "argumentos": json.dumps({"prompt": "una manzana que habla"})}, FIN)
    pedidas = []
    r = director.dirigir("una manzana que habla", confirmar=lambda p: pedidas.append(p) or True,
                         modelo_video="gemini")
    assert r["pasos"][0]["argumentos"]["animado"] is True and hechos[-1]["voz_de"] == "gemini" and pedidas
    # Lo que diga que no, no se hace
    ia.texto_json = pasos(VIDEO, FIN)
    n = len(hechos)
    r = director.dirigir("otro", confirmar=lambda p: False, modelo_video="kling")
    assert len(hechos) == n and "no lo aceptó" in r["pasos"][0]["resultado"]
    # Uno que ya no está conectado (se quitó su clave con el chat abierto): Automático, como su selector al abrirlo
    ia.texto_json = pasos(VIDEO, FIN)
    dichos = []
    director.dirigir("otro", confirmar=lambda p: False, al_decir=dichos.append, modelo_video="seedance")
    assert len(hechos) == n + 1 and hechos[-1]["pago"] is None and f"Para el video usaré: {nombres['auto']}." in dichos
finally:
    comun.mensaje_error, QMessageBox.question, desde_prompt.generar = error_real, pregunta_real, generar_real
    pagina_crear.mensaje, ia.texto_json = mensaje_real, texto_real

# ---------- MCP: modelo_video validado, lo de pago con el sí de la ventana, lo gratis directo ----------
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

import mcp_server  # noqa: E402
from motor import guardia  # noqa: E402

guardia.INSISTENCIA = 10 ** 6  # aquí se dice «No» a propósito: la regla que bloquea al agente tiene su prueba
ventanas, contesta, hechos = [], [False], []
preguntar_real, mcp_server._preguntar = mcp_server._preguntar, lambda texto: ventanas.append(texto) or contesta[0]
desde_prompt.generar = generar_falso
try:
    assert "Modelo de video desconocido ('sora')" in falla(mcp_server.crear_video, "un gato", modelo_video="sora",
                                                           error=ToolError)
    assert "Seedance no está conectado" in falla(mcp_server.crear_video, "un gato", modelo_video="seedance",
                                                 error=ToolError)
    assert "Sin animar" in falla(mcp_server.crear_video, "x", imagen="x.png", solo_animar=True,
                                 modelo_video="ninguno", error=ToolError)
    assert not ventanas and not hechos  # nada se preguntó ni se hizo
    assert "no lo aceptó" in falla(mcp_server.crear_video, "un gato", modelo_video="kling", error=ToolError)
    assert f"Esto cuesta unos US${10 * precio:.2f}" in ventanas[-1] and not hechos
    contesta[0] = True
    json.loads(mcp_server.crear_video("un gato", modelo_video="kling"))
    assert len(ventanas) == 2 and hechos[-1]["pago"] == "kling" and hechos[-1]["guardado"] == "auto"
    json.loads(mcp_server.crear_video("un gato", modelo_video="modal"))  # gratis: sin ventana
    json.loads(mcp_server.crear_video("un gato"))  # sin modelo_video: Automático
    assert len(ventanas) == 2 and hechos[-2]["orden"] == ["modal"] and hechos[-1]["pago"] is None
    esquemas = {h.name: h for h in asyncio.run(mcp_server.mcp.list_tools())}
    for nombre in ("crear_video", "crear_anuncios", "crear_episodio", "crear_video_musical"):
        assert esquemas[nombre].input_schema["properties"]["modelo_video"]["default"] == "auto", nombre
        assert "modelo_video (opcional)" in esquemas[nombre].description and "listar_opciones" in \
            esquemas[nombre].description
    assert [m["id"] for m in json.loads(mcp_server.listar_opciones())["modelos_video"]] == ids
finally:
    mcp_server._preguntar, desde_prompt.generar = preguntar_real, generar_real

# Quitar la clave: el modelo recordado vuelve a Automático (y «Claves de IA» sigue igual)
claves.borrar("kling")
assert "modelo_video_director" not in claves._guardados() and comun.SelectorModelo("director").valor() == "auto"
assert "kling" not in [m["id"] for m in claves.modelos_video()]
print("Pruebas del selector «Modelo de video» pasadas.")
