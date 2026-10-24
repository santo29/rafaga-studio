"""El estudio inteligente, sin red ni claves: departamentos, memoria del estudio, costo antes de gastar (con ventana y
con la voz), órdenes de voz de varios pasos y el examen del Director con una IA falsa: python -m pruebas.estudio"""
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtWidgets import QApplication, QListWidget, QMessageBox, QPushButton  # noqa: E402

from motor import claves, desde_prompt, diseno, diseno_ia, director, herramientas, ia, memoria, roles, voz  # noqa: E402

diseno.asegurar_qt()
app = QApplication.instance()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-estudio-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # sin claves: nunca las del usuario
memoria.ARCHIVO = tmp / "memoria.json"  # ni su memoria
RAIZ = Path(__file__).resolve().parent.parent


def esperar(listo, segundos=10):
    fin = time.time() + segundos
    while not listo():
        assert time.time() < fin, "no llegó a tiempo"
        app.processEvents()
        time.sleep(0.01)


# ---------- Departamentos: cada herramienta que trabaja es de uno, y el Director los lee ----------
suyas = [h for d in roles.DEPARTAMENTOS.values() for h in d["herramientas"]]
assert len(suyas) == len(set(suyas)) and set(suyas) <= set(herramientas.TODAS)
assert set(herramientas.TODAS) - set(suyas) == {"listar_opciones", "recordar_preferencia"}
manual = roles.manual()
assert all(f"- {d} (" in manual for d in roles.DEPARTAMENTOS) and "Calidad:" in manual
assert len(roles.DEPARTAMENTOS) == 8 and roles.nombre("general") == "Todo el estudio"
assert all(d in herramientas.recordar_preferencia.__doc__ for d in roles.DEPARTAMENTOS)

# ---------- Memoria del estudio ----------
assert memoria.cargar() == {} and memoria.para("diseno") == ""
memoria.recordar("diseno", "  sin   Montserrat ")
memoria.recordar("general", "mi marca es Ráfaga")
memoria.recordar("diseno", "títulos cortos")
memoria.recordar("diseno", "SIN MONTSERRAT")  # repetida: no se duplica, pasa al final con lo último que dijo
assert memoria.cargar() == {"diseno": ["títulos cortos", "SIN MONTSERRAT"], "general": ["mi marca es Ráfaga"]}
linea = memoria.para("diseno")
assert linea.startswith("\n") and "mi marca es Ráfaga; títulos cortos; SIN MONTSERRAT" in linea
assert "MONTSERRAT" not in memoria.para("musica_voz") and "Ráfaga" in memoria.para("musica_voz")
for i in range(memoria.MAX_POR_DEPARTAMENTO + 3):  # con tope: la más vieja se olvida
    memoria.recordar("nichos", f"idea {i}")
assert len(memoria.cargar()["nichos"]) == memoria.MAX_POR_DEPARTAMENTO and memoria.cargar()["nichos"][-1] == "idea 22"
memoria.olvidar("nichos", "idea 22")
assert "idea 22" not in memoria.cargar()["nichos"]
# Nunca datos sensibles, ni departamentos inventados, ni textos vacíos o enormes
for malo in ("mi contraseña es hola123", "tarjeta de crédito 4111 1111 1111 1111", "4111111111111111",
             "sk-ant-api03-abc", "usa la clave AIzaSyD3xQwErTy12345678", "mi clave de Gemini es esta", "token ghp_x",
             "My password is x", "IBAN ES9121000418450200051332"):
    try:
        memoria.recordar("general", malo)
        raise AssertionError(f"debió rechazar {malo!r}")
    except ValueError as e:
        assert "No guardo" in str(e), e
for departamento, texto in (("ventas", "x"), (["diseno"], "x"), ("diseno", ""), ("diseno", "x" * 201)):
    try:
        memoria.recordar(departamento, texto)
        raise AssertionError(f"debió rechazar {departamento!r}")
    except ValueError:
        pass
for bueno in ("tarjetas de presentación con fondo negro", "mi WhatsApp es 809-555-1234", "palabras clave cortas"):
    memoria.recordar("diseno", bueno)
memoria.ARCHIVO.write_text('{"diseno": "no es lista", "inventado": ["x"], "general": ["ok", 3]}', encoding="utf-8")
assert memoria.cargar() == {"general": ["ok"]}  # tocado a mano: lo que no vale se ignora
memoria.ARCHIVO.write_text("{roto", encoding="utf-8")
assert memoria.cargar() == {}

# Cada especialista añade su línea a lo que manda a su IA
for archivo, departamento in (("desde_prompt", "video"), ("diseno_ia", "diseno"), ("musica", "musica_voz"),
                              ("video_musical", "musica_voz"), ("serie", "dibujos"), ("anuncios", "anuncios"),
                              ("nichos", "nichos"), ("shorts", "edicion")):
    assert f'memoria.para("{departamento}")' in (RAIZ / "motor" / f"{archivo}.py").read_text(encoding="utf-8"), archivo
memoria.recordar("video", "siempre con un chiste al final")


class Basta(Exception):
    pass


pedidos = []
_pensar = ia.texto_json


def anotar(instrucciones, pedido, esquema):
    pedidos.append((instrucciones, pedido))
    raise Basta


ia.texto_json = anotar
try:
    try:
        desde_prompt.generar("un perrito que baila")
    except Basta:
        pass
    assert "siempre con un chiste al final" in pedidos[-1][1]
finally:
    ia.texto_json = _pensar

# La herramienta del Director (y del MCP): gratis, sin preguntar; lo sensible vuelve como error que la IA lee
_, res = director._usar("recordar_preferencia", '{"departamento": "musica_voz", "preferencia": "coros cortos"}',
                        lambda *a: None, lambda n: None, "", "")
assert json.loads(res) == {"guardada": "coros cortos", "memoria": ["coros cortos"]}
_, res = director._usar("recordar_preferencia", '{"departamento": "general", "preferencia": "mi pin es 1234"}',
                        lambda *a: None, lambda n: None, "", "")
assert res.startswith("ERROR") and "No guardo" in res

# ---------- Costo antes de gastar: lo decide el código ----------
gratis = [("crear_diseno", {"pedido": "x"}), ("crear_video", {"prompt": "x"}), ("crear_cancion", {"idea": "x"}),
          ("investigar_nichos", {}), ("crear_video", {"prompt": "x", "animado": True}),  # sin clave de Gemini: falla
          ("editar_video", {"medios": ["a.mp4"]}), ("recordar_preferencia", {})]  # antes de gastar
assert all(director.costo(n, a) is None for n, a in gratis)
pregunta = director.costo("programar_publicacion", {"titulo": "Mi video", "fecha_hora": "2026-10-25T18:00"})
assert "YouTube" in pregunta and "«Mi video»" in pregunta and "2026-10-25 18:00" in pregunta
_para, _cargar = claves.para, claves.cargar
try:
    claves.cargar = lambda: {"gemini": {"proveedor": "gemini", "clave": "AIzaPrueba"}}
    claves.para = lambda uso: {"proveedor": "gemini", "clave": "AIzaPrueba"} if uso in ("musica", "imagen") else None
    animado = director.costo("crear_video", {"prompt": "x", "animado": True, "segundos": 45})
    assert "US$6.00" in animado, animado  # 6 escenas de 8 s a ~US$1, más las imágenes no: van animadas
    assert director.costo("crear_video", {"prompt": "x", "animado": "true"}) != animado  # «"true"» no es un sí
    assert "US$0.08" in director.costo("crear_cancion", {"idea": "dembow"})
    precio = max(p["1K"] for p in ia.PRECIO_IMAGEN_GEMINI.values())  # modelo aún sin elegir: el más caro
    assert f"US${2 * precio:.2f}" in director.costo("crear_diseno", {"pedido": "x"})
    assert f"US${2 * max(p['4K'] for p in ia.PRECIO_IMAGEN_GEMINI.values()):.2f}" in director.costo(
        "crear_diseno", {"pedido": "x", "calidad": "4K"})
    for nombre in ("crear_video_musical", "crear_serie", "crear_episodio", "crear_anuncios"):
        assert "US$" in director.costo(nombre, {}), nombre  # con Gemini para imágenes, cada foto se paga
    assert director.costo("crear_video", {"segundos": "mucho", "personajes": None}).startswith("Esto cuesta")
    assert director.costo("crear_video", {"imagen": "a.png", "solo_animar": True}) is None  # solo anima: sin fotos
    claves.para = lambda uso: {"proveedor": "elevenlabs", "clave": "sk_x"} if uso == "musica" else None
    assert "US$0.45" in director.costo("crear_cancion", {"idea": "x"})  # el precio alto: nunca se queda corto
finally:
    claves.para, claves.cargar = _para, _cargar
try:
    herramientas.crear_diseno("x", calidad="8K")
    raise AssertionError("debió rechazar la calidad")
except ValueError as e:
    assert "1K, 2K o 4K" in str(e)
_crear, _entender = diseno_ia.crear, diseno_ia.entender
diseno_ia.entender = lambda pedido, tipo="auto": {"seguro": True, "entendido": pedido}
diseno_ia.crear = lambda pedido, tipo, usar_marca=True, aviso=None, propuesta=None, estilo="auto", calidad="1K": {
    "calidad": calidad}
try:
    assert json.loads(herramientas.crear_diseno("x", calidad="4K"))["calidad"] == "4K"  # llega a las fotos
finally:
    diseno_ia.crear, diseno_ia.entender = _crear, _entender

# ---------- El Director se detiene antes de gastar y pregunta; lo gratis lo hace directo ----------
hechos = []


def cancion_falsa(idea: str, genero: str = "", con_voz: bool = True, segundos: int = 150) -> str:
    hechos.append(("crear_cancion", idea))
    return json.dumps({"resultados": [{"archivo": "C:/x/cancion.mp3", "titulo": "Punta Cana"}]})


def videoclip_falso(cancion: str, formato: str = "9:16", idea: str = "", letra: str = "", genero: str = "") -> str:
    hechos.append(("crear_video_musical", cancion))
    return json.dumps({"resultados": [{"archivo": "C:/x/videoclip.mp4", "titulo": "Punta Cana"}]})


def guion(*pasos):
    vistos = []

    def pensar(instrucciones, pedido, esquema):
        vistos.append((instrucciones, pedido))
        return dict(pasos[min(len(vistos), len(pasos)) - 1])
    return pensar, vistos


CANCION = {"mensaje": "Primero hago la canción y luego su video musical.", "herramienta": "crear_cancion",
           "argumentos": '{"idea": "dembow de Punta Cana", "genero": "Dembow moderno"}'}
VIDEOCLIP = {"mensaje": "Ahora el video musical.", "herramienta": "crear_video_musical",
             "argumentos": '{"cancion": "C:/x/cancion.mp3"}'}
FIN = {"mensaje": "¡Listo! Tu canción y su video están en Música.", "herramienta": "", "argumentos": "{}"}
originales = dict(herramientas.TODAS)
herramientas.TODAS.update(crear_cancion=cancion_falsa, crear_video_musical=videoclip_falso)
_para = claves.para
claves.para = lambda uso: {"proveedor": "gemini", "clave": "AIzaPrueba"} if uso == "musica" else None
try:
    ia.texto_json, vistos = guion(CANCION, CANCION, FIN)
    preguntas, dichos = [], []
    r = director.dirigir("una canción de dembow sobre Punta Cana", confirmar=lambda p: preguntas.append(p) or False,
                         al_decir=dichos.append)
    assert not hechos and len(preguntas) == 1  # dijo que no: no se hizo, y la segunda vez no se le pregunta
    assert preguntas[0].startswith("Primero hago la canción") and "US$0.08" in preguntas[0]
    assert dichos == ["Primero hago la canción y luego su video musical."]  # el plan, antes de empezar
    assert all("no lo aceptó" in p["resultado"] for p in r["pasos"]) and "no lo aceptó" in vistos[1][1]
    # Sin quien conteste (el MCP o un error de la app), lo de pago no se hace nunca
    ia.texto_json, _ = guion(CANCION, FIN)
    director.dirigir("una canción")
    assert not hechos
    # Dijo que sí: se hace, y lo gratis que sigue va directo
    ia.texto_json, vistos = guion(CANCION, VIDEOCLIP, FIN)
    preguntas.clear()
    r = director.dirigir("canción y video", confirmar=lambda p: preguntas.append(p) or True)
    assert [h[0] for h in hechos] == ["crear_cancion", "crear_video_musical"] and len(preguntas) == 1
    assert "Departamentos del estudio" in vistos[0][0] and "musica_voz (Música y voz)" in vistos[0][0]
    assert "coros cortos" in vistos[0][0]  # el Director ve lo que recuerda del usuario
    assert all(f"- {nombre}(" in vistos[0][0] for nombre in herramientas.TODAS)

    # ---------- Por voz: la orden llega al Director con todas las herramientas y encadena pasos ----------
    from ui.paginas.director import PaginaDirector, ver_memoria  # noqa: E402

    _hablar, _escuchar, _entender = voz.hablar, voz.escuchar, voz.entender
    oido = ["sí, dale"]
    voz.hablar = lambda texto: (_ for _ in ()).throw(RuntimeError("sin red en las pruebas"))
    voz.escuchar = lambda detener, nivel=None, dispositivo=None: np.ones(voz.SR, np.float32)
    voz.entender = lambda audio: oido[0]
    errores, _gancho = [], sys.excepthook  # un fallo dentro de un slot de Qt solo se imprime: aquí se cuenta
    sys.excepthook = lambda *e: errores.append(e)
    try:
        pagina = PaginaDirector()
        pagina.resize(1100, 900)
        pagina.show()
        hechos.clear()
        ia.texto_json, vistos = guion(CANCION, VIDEOCLIP, FIN)
        pagina._oido("hazme una canción de dembow de Punta Cana y su video musical")  # lo que entendió Whisper
        esperar(lambda: not pagina.ocupado() and pagina.enviar_btn.isEnabled())
        assert [h[0] for h in hechos] == ["crear_cancion", "crear_video_musical"], hechos
        assert hechos[1][1] == "C:/x/cancion.mp3"  # el segundo paso usa lo que hizo el primero
        assert all(f"- {nombre}(" in vistos[0][0] for nombre in herramientas.TODAS)
        chat = pagina.chat.toPlainText()
        assert chat.index("Primero hago la canción") < chat.index("US$0.08") < chat.index("¡Listo!")
        assert chat.count("Primero hago la canción") == 1  # el plan en el chat; la pregunta no lo repite
        assert pagina.caja is None and pagina.historial[-1]["texto"].startswith("¡Listo!")
        # Dijo «no» con la voz: no se gasta
        hechos.clear()
        oido[0] = "no, mejor no"
        ia.texto_json, vistos = guion(CANCION, FIN)
        pagina._oido("una canción de dembow")
        esperar(lambda: not pagina.ocupado() and pagina.enviar_btn.isEnabled())
        assert not hechos and "no lo aceptó" in vistos[1][1]
        # No se le entiende: pregunta otra vez y al final deja la ventana; un clic en «No» basta
        oido[0] = "eh, mmm, a ver"
        ia.texto_json, _ = guion(CANCION, FIN)
        pagina._oido("una canción")
        esperar(lambda: pagina.caja is not None and "contesta en la ventana" in pagina.estado.text())
        pagina.caja.button(QMessageBox.No).click()
        esperar(lambda: not pagina.ocupado() and pagina.enviar_btn.isEnabled())
        assert not hechos
        # Por escrito: solo la ventana (sin voz); «Sí» lo hace
        ia.texto_json, _ = guion(CANCION, FIN)
        pagina.pedido.setText("una canción")
        pagina.enviar()
        esperar(lambda: pagina.caja is not None)
        assert pagina.caja.defaultButton().text() == pagina.caja.button(QMessageBox.No).text()  # Enter no gasta
        assert not (pagina.escucha and pagina.escucha.isRunning())
        pagina.caja.button(QMessageBox.Yes).click()
        esperar(lambda: not pagina.ocupado() and pagina.enviar_btn.isEnabled())
        assert hechos == [("crear_cancion", "dembow de Punta Cana")]
        # Tras un trabajo con 2 resultados, uno con 1: la lista del reproductor no pide una fila que ya no existe
        assert not errores and pagina.reproductor.lista.count() == 1, errores

        # ---------- «Memoria del estudio»: verla y borrarla ----------
        assert any(b.text() == "Memoria del estudio" for b in pagina.findChildren(QPushButton))
        ventana = ver_memoria(pagina)
        lista = ventana.findChild(QListWidget)
        textos = [lista.item(i).text() for i in range(lista.count())]
        assert "Música y voz: coros cortos" in textos and "Guion y video: siempre con un chiste al final" in textos
        lista.setCurrentRow(textos.index("Música y voz: coros cortos"))
        next(b for b in ventana.findChildren(QPushButton) if b.text() == "Borrar").click()
        assert "musica_voz" not in memoria.cargar() and lista.count() == len(textos) - 1
        memoria.ARCHIVO.unlink()
        ventana.close()
        ventana = ver_memoria(pagina)
        lista = ventana.findChild(QListWidget)
        assert lista.count() == 1 and not next(b for b in ventana.findChildren(QPushButton) if b.text() == "Borrar") \
            .isEnabled()
        ventana.close()

        # Si la app se cierra mientras pregunta, el Director sigue sin gastar y termina
        hechos.clear()
        ia.texto_json, _ = guion(CANCION, FIN)
        pagina.pedido.setText("una canción")
        pagina.enviar()
        esperar(lambda: pagina.caja is not None)
        tarea = pagina.tarea
        pagina.cerrar()
        assert tarea.wait(5000) and not hechos
    finally:
        voz.hablar, voz.escuchar, voz.entender = _hablar, _escuchar, _entender
        sys.excepthook = _gancho
finally:
    ia.texto_json, claves.para = _pensar, _para
    herramientas.TODAS.clear()
    herramientas.TODAS.update(originales)

# ---------- «¿Lo hago?» contestado con la voz ----------
assert voz.si_o_no("Sí.") is True and voz.si_o_no("dale, hazlo") is True and voz.si_o_no("Yes") is True
assert voz.si_o_no("No.") is False and voz.si_o_no("cancela") is False and voz.si_o_no("não") is False
assert voz.si_o_no("si no cuesta mucho") is None and voz.si_o_no("") is None and voz.si_o_no("mmm") is None

# ---------- El examen del Director, comprobado con una IA falsa (el de verdad gasta: no va aquí) ----------
from pruebas import examen_director as examen  # noqa: E402

assert 15 <= len(examen.CASOS) <= 20 and all(c["ejemplo"][0] in c["valen"] for c in examen.CASOS)
examen.PAUSA = 0
real = director._usar


def respuesta_de(contenido, cual):
    caso = next(c for c in examen.CASOS if f"Pedido actual: {examen.pedido_de(c)}\n" in contenido)
    nombre, argumentos = cual(caso)
    return {"mensaje": "Voy.", "herramienta": nombre, "argumentos": json.dumps(argumentos, ensure_ascii=False)}


try:
    ia.texto_json = lambda instrucciones, contenido, esquema: respuesta_de(contenido, lambda c: c["ejemplo"])
    aciertos, fallos = examen.examinar(escribir=lambda texto: None)
    assert aciertos == len(examen.CASOS) and not fallos, fallos
    # Mal elegido o con los argumentos mal: cada caso lo nota y lo explica
    ia.texto_json = lambda instrucciones, contenido, esquema: respuesta_de(contenido, lambda c: ("listar_proyectos", {}))
    aciertos, fallos = examen.examinar(escribir=lambda texto: None)
    assert aciertos == 0 and len(fallos) == len(examen.CASOS) and "usó listar_proyectos" in fallos[0]
    malo = ("crear_diseno", {"pedido": "otra cosa", "tipo": "logo"})
    assert examen.revisar(examen.CASOS[1], *malo) == ['tipo = "logo"', 'pedido = "otra cosa"']
    assert "argumentos no válidos" in examen.revisar(examen.CASOS[1], "crear_diseno", {"color": "rojo"})[0]
    ia.texto_json = lambda *a: (_ for _ in ()).throw(RuntimeError("cuota agotada"))
    aciertos, fallos = examen.examinar(examen.CASOS[:1], escribir=lambda texto: None)
    assert aciertos == 0 and "cuota agotada" in fallos[0]
    assert director._usar is real  # nada se quedó interceptado
finally:
    ia.texto_json = _pensar
assert re.search(r"pruebas\.examen_director|\"examen_director\"", (RAIZ / "pruebas" / "__main__.py").read_text(
    encoding="utf-8")) is None  # gasta llamadas: nunca en las pruebas de siempre
print("Pruebas del estudio inteligente pasadas.")
