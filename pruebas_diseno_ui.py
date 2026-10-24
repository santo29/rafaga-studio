"""Pruebas de la página «Diseño» (ui/paginas/diseno.py) sin ventana, red ni claves: python pruebas_diseno_ui.py"""
import copy
import os
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QStandardPaths, Qt, QUrl  # noqa: E402
from PySide6.QtGui import (QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage, QMouseEvent,  # noqa: E402
                           QPainter)
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton  # noqa: E402

from motor import claves, diseno, marca  # noqa: E402
from ui.comun import ESTILO  # noqa: E402
import ui.paginas.diseno as pd  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
avisos, abiertas = [], []
QMessageBox.exec = lambda caja: avisos.append(caja.text()) or QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
os.startfile = abiertas.append  # que «Abrir carpeta» no abra el Explorador


def esperar(condicion, plazo=10):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def capa(id_):
    return next(c for c in p.diseno["capas"] if c["id"] == id_)


def item(id_):
    return next(i for i in p._items() if i.data(0) == id_)


def elegir(id_):
    p.escena.clearSelection()
    item(id_).setSelected(True)


def raton(tipo, punto, boton=Qt.LeftButton, botones=Qt.LeftButton):
    """Un evento de ratón de verdad en el lienzo, en un punto del diseño."""
    pos = QPointF(p.vista.mapFromScene(punto))
    QApplication.sendEvent(p.vista.viewport(), QMouseEvent(tipo, pos, p.vista.viewport().mapToGlobal(pos), boton,
                                                           botones, Qt.NoModifier))


def arrastrar(desde, hasta):
    raton(QEvent.MouseButtonPress, desde)
    raton(QEvent.MouseMove, QPointF((desde.x() + hasta.x()) / 2, (desde.y() + hasta.y()) / 2), Qt.NoButton)
    raton(QEvent.MouseMove, hasta, Qt.NoButton)
    raton(QEvent.MouseButtonRelease, hasta, botones=Qt.NoButton)


def cerca(a: QPointF, b: QPointF, margen=4):
    return abs(a.x() - b.x()) <= margen and abs(a.y() - b.y()) <= margen


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    diseno.CARPETA = d / "disenos"  # nada de tocar datos/ de verdad
    marca.ARCHIVO, marca.CARPETA_LOGO = d / "marca.json", d / "marca"
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"  # la Ventana no lee las claves de verdad
    foto = QImage(400, 200, QImage.Format_RGB32)
    foto.fill(QColor("#FF0000"))
    pintor = QPainter(foto)
    pintor.fillRect(200, 0, 200, 200, QColor("#0000FF"))
    pintor.end()
    ruta_foto = d / "foto.png"
    assert foto.save(str(ruta_foto))
    secreto = d / "claves.png"  # un archivo privado con nombre de foto
    secreto.write_text('{"openai": "sk-SECRETO"}', encoding="utf-8")

    p = pd.PaginaDiseno()
    p.resize(1280, 1000)
    p.show()
    app.processEvents()
    assert p.diseno["capas"] == [] and p.carpeta is None and not p.deshacer_btn.isEnabled()
    assert not diseno.CARPETA.exists()  # abrir la página no crea carpetas vacías

    # ---------- Añadir cada tipo de capa ----------
    p.anadir_texto()
    for forma in pd.FORMAS:
        p.anadir_forma(forma)
    p.anadir_icono("pizza")
    p.anadir_emoji("🍕")
    p.anadir_imagen(str(ruta_foto))
    assert [c["tipo"] for c in p.diseno["capas"]] == ["texto", "forma", "forma", "forma", "icono", "emoji", "imagen"]
    assert [c["forma"] for c in p.diseno["capas"][1:4]] == ["rectangulo", "elipse", "linea"]
    foto_capa = p.diseno["capas"][-1]
    assert p.carpeta and (p.carpeta / "imagenes" / foto_capa["archivo"]).is_file()  # la carpeta nace con la imagen
    assert (foto_capa["ancho"], foto_capa["alto"]) == (648, 324)  # cabe en el lienzo sin deformarse
    assert p.diseno["capas"][0]["color"] == "#111111"  # texto oscuro sobre el fondo blanco
    assert len(p._items()) == p.capas.count() == 7 and len({c["id"] for c in p.diseno["capas"]}) == 7
    assert p.elegido()[1] is foto_capa and p.capas.currentRow() == 0  # la nueva queda elegida y arriba en la lista
    # Soltar una foto en el lienzo la pone donde se suelta
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(ruta_foto))])
    for evento in (QDragEnterEvent, QDragMoveEvent):  # el lienzo acepta el arrastre (la escena sola lo rechazaría)
        arrastre = evento(QPoint(50, 50), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(p.vista.viewport(), arrastre)
        assert arrastre.isAccepted(), evento
    p.vista.dropEvent(QDropEvent(QPointF(p.vista.mapFromScene(QPointF(300, 800))), Qt.CopyAction, datos,
                                 Qt.LeftButton, Qt.NoModifier))
    soltada = p.diseno["capas"][-1]
    assert soltada["tipo"] == "imagen" and cerca(QPointF(soltada["x"] + soltada["ancho"] / 2,
                                                         soltada["y"] + soltada["alto"] / 2), QPointF(300, 800))
    # Lo hostil no entra: un archivo de claves llamado .png, una ruta de red y algo que no es imagen
    for malo in (str(secreto), r"\\atacante.example\s\a.png", "//atacante.example/s/a.png", str(d / "no.png"),
                 "datos/claves.json"):
        antes = len(avisos)
        p.anadir_imagen(malo)
        assert len(avisos) == antes + 1, malo
    datos.setUrls([QUrl.fromLocalFile(str(secreto))])
    p.vista.dropEvent(QDropEvent(QPointF(10, 10), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier))
    assert len(p.diseno["capas"]) == 8 and len(list((p.carpeta / "imagenes").glob("*"))) == 2

    # ---------- Selección sincronizada: lista ↔ lienzo ----------
    texto_id, rect_id, emoji_id = (p.diseno["capas"][i]["id"] for i in (0, 1, 5))
    filas = [p.capas.item(i).data(Qt.UserRole) for i in range(p.capas.count())]
    assert filas == [c["id"] for c in reversed(p.diseno["capas"])]
    p.capas.setCurrentRow(filas.index(texto_id))
    assert p.elegido()[1]["id"] == texto_id and [i.data(0) for i in p.escena.selectedItems()] == [texto_id]
    elegir(emoji_id)
    assert p.capas.currentItem().data(Qt.UserRole) == emoji_id
    assert p.w["texto"].isVisibleTo(p) and p.w["relleno"].isHidden() and p.w["tamano"].isHidden()  # lo del emoji

    # ---------- Propiedades ----------
    elegir(texto_id)
    assert not p.w["fuente"].isHidden() and p.w["relleno"].isHidden() and p.w["texto"].toPlainText() == "Escribe aquí"
    p.w["texto"].setPlainText("<b>PIZZA</b> 2x1")
    assert capa(texto_id)["texto"] == item(texto_id).texto.toPlainText() == "<b>PIZZA</b> 2x1"  # texto plano
    assert p.capas.currentItem().text() == "Texto · <b>PIZZA</b> 2x1"
    pila = len(p.deshacer_pila)
    for x in (10, 20, 30):
        p.w["x"].setValue(x)
    assert capa(texto_id)["x"] == 30 and item(texto_id).pos().x() == 30 and len(p.deshacer_pila) == pila + 1
    p.w["opacidad"].setValue(50)
    p.w["grosor_contorno"].setValue(3)
    p.w["alineacion"].setCurrentIndex(p.w["alineacion"].findData("derecha"))
    p.w["fuente"].setCurrentIndex(p.w["fuente"].findData("Bebas Neue"))
    p.w["negrita"].setChecked(False)
    pd.pedir_color = lambda *a: "#ff0000"
    p._elegir_color("color")
    c = capa(texto_id)
    assert (c["opacidad"], c["grosor_contorno"], c["contorno"], c["alineacion"], c["fuente"], c["negrita"], c["color"]) == \
        (0.5, 3, "#000000", "derecha", "Bebas Neue", False, "#FF0000"), c
    assert item(texto_id)._contorno.isVisible() and abs(item(texto_id).opacity() - 0.5) < 1e-6
    elegir(rect_id)
    assert p.w["texto"].isHidden() and not p.w["relleno"].isHidden() and p.w["x"].value() == capa(rect_id)["x"]
    p._elegir_color("relleno")
    assert capa(rect_id)["relleno"] == "#FF0000" and p.w["relleno"].text() == "#FF0000"

    # ---------- Mover y cambiar el tamaño con el ratón ----------
    p.w["ancho"].setValue(200)
    p.w["alto"].setValue(200)
    p.w["x"].setValue(50)
    p.w["y"].setValue(50)
    pila = len(p.deshacer_pila)
    arrastrar(QPointF(150, 150), QPointF(250, 200))  # arrastrar la capa la mueve
    assert cerca(QPointF(capa(rect_id)["x"], capa(rect_id)["y"]), QPointF(150, 100)), capa(rect_id)
    assert item(rect_id).pos() == QPointF(capa(rect_id)["x"], capa(rect_id)["y"]) and len(p.deshacer_pila) == pila + 1
    assert p.w["x"].value() == capa(rect_id)["x"]  # las propiedades siguen al lienzo
    x0, y0 = capa(rect_id)["x"], capa(rect_id)["y"]
    arrastrar(QPointF(x0 + 200, y0 + 200), QPointF(x0 + 300, y0 + 250))  # el asa de abajo a la derecha
    c = capa(rect_id)
    assert (c["x"], c["y"]) == (x0, y0) and abs(c["ancho"] - 300) <= 4 and abs(c["alto"] - 250) <= 4, c
    assert len(p.deshacer_pila) == pila + 2  # todo el gesto del asa es un solo «deshacer»
    # Girada 90°: al tirar de un asa, la esquina opuesta no se mueve
    p.w["rotacion"].setValue(90)
    ancho, alto = c["ancho"], c["alto"]
    fija = item(rect_id).mapToScene(QPointF(0, 0))
    asa = item(rect_id).mapToScene(QPointF(ancho, alto))
    arrastrar(asa, asa + QPointF(-60, 40))  # girada, eso es +40 de ancho y +60 de alto
    assert cerca(item(rect_id).mapToScene(QPointF(0, 0)), fija), (item(rect_id).mapToScene(QPointF(0, 0)), fija)
    assert abs(c["ancho"] - ancho - 40) <= 4 and abs(c["alto"] - alto - 60) <= 4, c
    p.w["rotacion"].setValue(0)
    # Un clic en el fondo suelta la capa
    arrastrar(QPointF(1060, 20), QPointF(1060, 20))
    assert p.elegido() == (None, None) and p.capas.currentRow() == -1 and p.w["x"].isHidden()

    # ---------- Deshacer y rehacer ----------
    elegir(rect_id)
    antes = copy.deepcopy(p.diseno)
    p.borrar_capa()
    assert rect_id not in [c["id"] for c in p.diseno["capas"]] and len(p._items()) == 7
    p.deshacer()
    assert p.diseno == antes and len(p._items()) == 8
    p.rehacer()
    assert rect_id not in [c["id"] for c in p.diseno["capas"]] and not p.rehacer_btn.isEnabled()
    p.deshacer()
    assert p.diseno == antes and p.rehacer_btn.isEnabled()
    # Capas: subir, bajar, duplicar
    elegir(texto_id)
    p.mover_capa(1)
    assert p.diseno["capas"][1]["id"] == texto_id and p.elegido()[1]["id"] == texto_id
    p.mover_capa(-1)
    pila = len(p.deshacer_pila)
    p.mover_capa(-1)  # ya está abajo del todo: no hace nada ni gasta un «deshacer»
    assert p.diseno["capas"][0]["id"] == texto_id and len(p.deshacer_pila) == pila
    p.duplicar_capa()
    copia = p.diseno["capas"][-1]
    assert copia["id"] != texto_id and copia["texto"] == "<b>PIZZA</b> 2x1" and copia["x"] == capa(texto_id)["x"] + 30
    p.deshacer()
    elegir(texto_id)
    for _ in range(60):
        p.mover_capa(1 if p.diseno["capas"][0]["id"] == texto_id else -1)
    assert len(p.deshacer_pila) == 50  # como mucho 50 copias

    # ---------- Fondo ----------
    p.poner_fondo({"tipo": "degradado", "colores": ["#000000", "#FFFFFF"]})
    assert p.diseno["fondo"] == {"tipo": "degradado", "colores": ["#000000", "#FFFFFF"], "imagen": ""}
    colores = iter(["#112233", "#445566"])
    pd.pedir_color = lambda *a: next(colores)
    p.fondo_degradado()
    assert p.diseno["fondo"]["colores"] == ["#112233", "#445566"]
    pd.pedir_color = lambda *a: "#0f0f13"
    p.fondo_color()
    assert p.diseno["fondo"] == {"tipo": "color", "colores": ["#0F0F13"], "imagen": ""} and p._tinta() == "#FFFFFF"
    p._pedir_imagen = lambda *a: str(ruta_foto)
    p.fondo_imagen()
    assert p.diseno["fondo"]["tipo"] == "imagen" and (p.carpeta / "imagenes" / p.diseno["fondo"]["imagen"]).is_file()
    p._pedir_imagen = lambda *a: str(secreto)
    antes = copy.deepcopy(p.diseno)
    p.fondo_imagen()
    assert p.diseno == antes

    # ---------- Guardar y abrir ----------
    p.nombre.setText("Anuncio pizzería")
    p.nombre.textEdited.emit("Anuncio pizzería")
    p.guardar()
    carpeta = p.carpeta
    assert (carpeta / "diseno.json").is_file() and diseno.abrir(carpeta) == p.diseno and not p.sucio
    guardado = copy.deepcopy(p.diseno)
    p.nuevo("historia")
    assert (p.diseno["ancho"], p.diseno["alto"]) == (1080, 1920) and p.diseno["capas"] == [] and p.carpeta is None
    assert not p.deshacer_pila and p.nombre.text() == "Mi diseño"
    rejilla = pd.Cuadricula(p, "Abrir", pd.disenos_guardados, celda=170)
    assert [rejilla.rejilla.item(i).data(Qt.UserRole) for i in range(rejilla.rejilla.count())] == [str(carpeta)]
    assert rejilla.rejilla.item(0).text() == "Anuncio pizzería" and not rejilla.rejilla.item(0).icon().isNull()
    rejilla._elegir(rejilla.rejilla.item(0))
    p.abrir(rejilla.valor)
    assert p.diseno == guardado and p.carpeta == carpeta and len(p._items()) == len(guardado["capas"])
    assert p.nombre.text() == "Anuncio pizzería"
    for malo in (d / "no_existe", r"\\atacante.example\s\diseno"):
        antes = len(avisos)
        p.abrir(malo)
        assert len(avisos) == antes + 1 and p.diseno == guardado

    # ---------- Exportar ----------
    for formato in pd.FORMATOS:
        hecho = p.exportar(d / "salida" / f"anuncio.{formato}", formato)
        assert hecho.is_file() and hecho.stat().st_size > 1000, formato
    png = QImage(str(d / "salida" / "anuncio.png"))
    assert (png.width(), png.height()) == (1080, 1080)
    assert p.exportar(r"\\atacante.example\s\x.png") is None  # a la red no
    p.abrir_carpeta()
    assert abiertas == [d / "salida"]
    imagenes = Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation))
    assert pd.carpeta_exportar() == imagenes / "Ráfaga Studio"

    # ---------- Buscadores de iconos y emojis ----------
    buscador = pd.Cuadricula(p, "Iconos", pd.iconos)
    buscador.buscar.setText("pizza")
    assert buscador.rejilla.item(0).data(Qt.UserRole) == "pizza" and not buscador.rejilla.item(0).icon().isNull()
    buscador._elegir(buscador.rejilla.item(0))
    p.anadir_icono(buscador.valor)
    assert p.diseno["capas"][-1]["nombre"] == "pizza"
    buscador.buscar.setText("../claves")
    assert buscador.rejilla.count() == 0
    buscador = pd.Cuadricula(p, "Emojis", pd.emojis)
    assert buscador.rejilla.count() == 160
    buscador.buscar.setText("pizza")
    assert "🍕" in [buscador.rejilla.item(i).data(Qt.UserRole) for i in range(buscador.rejilla.count())]

    # Máximo de capas: la 81 no entra
    while len(p.diseno["capas"]) < diseno.MAX_CAPAS:
        p.diseno["capas"].append({**p.diseno["capas"][-1], "id": f"relleno{len(p.diseno['capas'])}"})
    antes = len(avisos)
    p.anadir_emoji("🔥")
    assert len(p.diseno["capas"]) == diseno.MAX_CAPAS and len(avisos) == antes + 1

    # ---------- Mi marca ----------
    dialogo = pd.DialogoMarca(p)
    dialogo.nombre.setText("Pizzería Don Juan")
    dialogo.colores.setText("#ff4d8d, #0F0F13")
    dialogo.titulo.setCurrentText("Bebas Neue")
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(ruta_foto), ""))
    dialogo._elegir_logo()
    dialogo.guardar()
    guardada = marca.cargar()
    assert (guardada["nombre"], guardada["colores"], guardada["fuente_titulo"]) == \
        ("Pizzería Don Juan", ["#FF4D8D", "#0F0F13"], "Bebas Neue") and marca.ruta_logo().is_file()
    dialogo = pd.DialogoMarca(p)
    assert dialogo.colores.text() == "#FF4D8D #0F0F13" and dialogo.logo.text() == guardada["logo"]
    dialogo.colores.setText("rojo")
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(secreto), ""))
    antes = len(avisos)
    dialogo._elegir_logo()
    dialogo.guardar()
    assert len(avisos) == antes + 2 and marca.cargar() == guardada  # lo que no vale no se guarda
    p.nuevo("post")
    assert p.diseno["fondo"]["colores"] == ["#FF4D8D"]  # el diseño nuevo sale con el color de la marca

    # ---------- Diseñar con IA (simulada) ----------
    p.pedido.setText("anuncio de pizza 2x1")
    sys.modules["motor.diseno_ia"] = None  # aún no está: la página avisa y sigue funcionando
    antes = len(avisos)
    p.disenar_con_ia()
    assert len(avisos) == antes + 1 and "todavía no" in avisos[-1] and p.tarea is None
    pedidos = []

    def crear(pedido, tipo="post", usar_marca=True, aviso=lambda t, f: None):
        pedidos.append((pedido, tipo, usar_marca))
        aviso("Diseñando…", 0.5)
        if pedido == "falla":
            raise RuntimeError("No hay IA de texto conectada.")
        destino = diseno.nueva_carpeta("IA")
        diseno.escribir_json(destino / "diseno.json", diseno.validar(
            {"nombre": "Pizza IA", "capas": [{"tipo": "texto", "texto": "PIZZA 2x1"}, {"tipo": "emoji"}]}))
        return {"tipo": "diseno", "carpeta": str(destino), "archivo": "", "diseno": {}, "avisos": ["una foto falló"],
                "titulo": "", "descripcion": ""}
    sys.modules["motor.diseno_ia"] = types.SimpleNamespace(crear=crear)
    p.tipo_ia.setCurrentIndex(p.tipo_ia.findData("historia"))
    p.usar_marca.setChecked(False)
    p.disenar_con_ia()
    assert not p.disenar.isEnabled()
    esperar(lambda: p.disenar.isEnabled() and p.diseno["nombre"] == "Pizza IA")
    assert pedidos == [("anuncio de pizza 2x1", "historia", False)]
    assert [c["texto"] for c in p.diseno["capas"]] == ["PIZZA 2x1", "⭐"] and len(p._items()) == 2
    assert p.carpeta.parent == diseno.CARPETA and "una foto falló" in avisos[-1] and p.progreso.isHidden()
    p.pedido.setText("falla")
    p.disenar_con_ia()
    esperar(lambda: p.disenar.isEnabled() and "No hay IA" in avisos[-1])
    assert p.diseno["nombre"] == "Pizza IA"  # un fallo no toca lo que hay en el lienzo
    # Lo editado mientras la IA trabajaba no se pisa: la pregunta va al terminar, no al empezar
    p.anadir_texto()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    p.pedido.setText("anuncio de pizza 2x1")
    antes = copy.deepcopy(p.diseno)
    p.disenar_con_ia()
    esperar(lambda: p.disenar.isEnabled() and len(pedidos) == 3)
    assert p.diseno == antes and "quedó guardado" in p.estado.text()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

    # ---------- Hallazgos de la revisión ----------
    p.nuevo("post")
    p.anadir_texto()
    texto_id = p.diseno["capas"][0]["id"]
    p.nombre.setText("Promo martes")
    p.nombre.textEdited.emit("Promo martes")
    p.deshacer()  # deshace el nombre, no el texto de antes
    assert p.diseno["nombre"] == p.nombre.text() == "Mi diseño" and len(p.diseno["capas"]) == 1
    p.rehacer()
    assert p.diseno["nombre"] == p.nombre.text() == "Promo martes"
    # La caja de texto crece con el texto: lo que sobresaldría no se podría elegir ni arrastrar
    elegir(texto_id)
    p.w["texto"].setPlainText("Pizza 2x1 todos los martes y jueves en tu local favorito")
    t = item(texto_id).texto
    alto_texto = t.boundingRect().height() - 2 * t.document().documentMargin()
    assert alto_texto > 300 and capa(texto_id)["alto"] >= alto_texto - 1 and p.w["alto"].value() == capa(texto_id)["alto"]
    # En una línea (caja de 20 de alto) las asas se solapan: el asa de abajo también cambia el ancho
    p.anadir_forma("linea")
    linea = p.diseno["capas"][-1]
    ancho, esquina = linea["ancho"], QPointF(linea["x"] + linea["ancho"], linea["y"] + linea["alto"])
    arrastrar(esquina, esquina + QPointF(100, 0))
    assert abs(capa(linea["id"])["ancho"] - ancho - 100) <= 4 and abs(capa(linea["id"])["alto"] - 20) <= 1, capa(linea["id"])
    # Topes del núcleo: el tamaño se recorta a 2 veces el lienzo (también con el asa, sin mover la esquina fija)
    c = capa(linea["id"])
    x0, y0, derecha = c["x"], c["y"], c["x"] + c["ancho"]
    arrastrar(QPointF(x0, y0), QPointF(x0 - 9000, y0))  # el asa de arriba a la izquierda: la derecha queda fija
    # ±2 px: el ratón va en píxeles de pantalla y el lienzo se ve reducido (cada píxel de pantalla son varios del diseño)
    assert c["ancho"] == 2160 and abs(c["x"] + c["ancho"] - derecha) <= 2 and abs(c["y"] - y0) <= 2, (c, derecha, y0)
    elegir(texto_id)
    p.w["ancho"].setValue(20000)
    p.w["grosor_contorno"].setValue(200)  # el contorno, como mucho la cuarta parte de la letra
    c = capa(texto_id)
    assert c["ancho"] == p.w["ancho"].value() == 2160 and c["grosor_contorno"] == p.w["grosor_contorno"].value() == 27
    # Lo que no se puede recortar (demasiados emojis grandes) avisa y deja el diseño y el campo como estaban
    p.w["grosor_contorno"].setValue(0)
    p.w["tamano"].setValue(2000)
    antes = copy.deepcopy(p.diseno)
    p.w["texto"].setPlainText("🍕" * 5)
    assert p.diseno == antes and "⚠️" in p.estado.text() and p.w["texto"].toPlainText() == antes["capas"][0]["texto"]
    # Una foto de móvil girada en el EXIF entra de pie, como la pinta el núcleo
    girada = d / "girada.jpg"
    assert foto.save(str(girada))  # 400×200
    exif = b"Exif\0\0MM\0\x2a\0\0\0\x08" + b"\0\x01" + b"\x01\x12\0\x03\0\0\0\x01\0\x06\0\0" + b"\0\0\0\0"  # orientación 6
    jpg = girada.read_bytes()
    girada.write_bytes(jpg[:2] + b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif + jpg[2:])
    p.anadir_imagen(str(girada))
    assert (p.diseno["capas"][-1]["ancho"], p.diseno["capas"][-1]["alto"]) == (324, 648), p.diseno["capas"][-1]
    # Como mucho 12 imágenes contando el fondo: la 13.ª, como capa o como fondo, avisa sin tocar el diseño
    p.diseno = diseno.validar({**p.diseno, "capas": p.diseno["capas"] + [p.diseno["capas"][-1]] * 11})
    p._dibujar()
    antes, n = copy.deepcopy(p.diseno), len(avisos)
    p.anadir_imagen(str(ruta_foto))
    p._pedir_imagen = lambda *a: str(ruta_foto)
    p.fondo_imagen()
    assert p.diseno == antes and len(avisos) == n + 2 and "12 imágenes" in avisos[-1]

    # ---------- La ventana completa, con la página después de «Crear con IA» ----------
    import app as aplicacion
    ventana = aplicacion.Ventana()
    i = next(i for i, pagina in enumerate(ventana.orden) if isinstance(pagina, pd.PaginaDiseno))
    assert ventana.orden[i - 1] is ventana.crear and "Diseño" in ventana.grupo.buttons()[i].text()
    # Abre en Inicio y el Director va después; sin claves, el Director (funciona con la IA gratis) aconseja conectar
    # una y lleva a «Claves de IA»
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.inicio) == 0
    assert ventana.orden.index(ventana.director) == 1 and ventana.grupo.buttons()[0].text() == "Inicio"
    assert "Conecta Groq o Gemini" in ventana.director.chat.toPlainText()
    next(b for b in ventana.director.findChildren(QPushButton) if b.text() == "Ir a Claves de IA").click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.claves)
    ventana.ir_a(i)
    assert ventana.paginas.currentIndex() == i and ventana.grupo.buttons()[i].isChecked()
    ventana.diseno.sucio = True  # un diseño sin guardar: cerrar pregunta, y «No» deja la ventana abierta
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    assert not ventana.close()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    assert ventana.close()
print("Pruebas de la página de diseño pasadas.")
