"""Página «Diseño»: estudio por capas con la disposición de los programas de diseño (archivo arriba, herramientas a la
izquierda, lienzo con zoom en el centro, propiedades y capas a la derecha, barra de estado abajo) y la IA, que entiende
el pedido (pregunta si duda), diseña en capas editables o dibuja una ilustración como capa nueva. El diseño es el dict
de motor/diseno.py: cada cambio se escribe ahí y el lienzo lo repinta."""
import copy
import html
import os
import re
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, QStandardPaths, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QImageIOHandler, QImageReader, QKeySequence, QPainter,
                           QPen, QPixmap, QPolygonF, QShortcut)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGraphicsItem, QGraphicsView,
                               QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QProgressBar, QScrollArea, QSizePolicy, QSlider, QSpinBox, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from motor import claves, diseno, ia, marca, recursos, seguro
from motor.idioma import dinero, t
from ui.comun import archivo_valido, boton, etiqueta, mensaje, mensaje_error, REFLEJO_FINO, resumen_avisos, Tarea
from ui.iconos import COLOR, icono

FORMAS = {"rectangulo": t("Rectángulo"), "elipse": t("Elipse"), "linea": t("Línea")}
FUSIONES = {"normal": t("Normal"), "multiplicar": t("Multiplicar"), "trama": t("Trama"),  # las de diseno.FUSIONES
            "superponer": t("Superponer"), "aclarar": t("Aclarar"), "oscurecer": t("Oscurecer")}
# «auto»: la pieza la elige la IA al entender el pedido (motor/diseno_ia.entender); el resto, las claves de sus TIPOS
TIPOS_IA = {"auto": t("Automático"), "ilustracion": t("Ilustración"), "estampado": t("Estampado (camiseta, sticker)"),
            "anuncio": t("Anuncio"), "post": t("Post"), "historia": t("Historia / Reel"),
            "miniatura": t("Miniatura de YouTube"), "flyer": t("Flyer"), "logo": t("Logo"),
            "tarjeta": t("Tarjeta de presentación"), "marca_personal": t("Marca personal"),
            "presentacion": t("Presentación (diapositiva)")}
ESTILOS_IA = {"auto": t("Automático"), "vector": t("Vector plano"), "sticker": t("Sticker"), "tatuaje": t("Tatuaje"),
              "poster": t("Póster"), "grabado": t("Grabado"), "render3d": t("Render 3D"),
              "neon_oscuro": t("Neón oscuro"), "animado3d": t("Animado 3D"), "urbano": t("Urbano"),
              "foto": t("Foto realista")}  # las claves de diseno_ia.ESTILOS
# Las calidades de cada modelo de ia.PRECIO_IMAGEN_GEMINI: 2K y 4K solo con Gemini (ver _calidades)
CALIDADES = {"1K": t("Normal (1K)"), "2K": t("Alta (2K)"), "4K": t("Máxima (4K)")}
# Pedidos de ejemplo (portadas de arte digital) con el estilo que les va
IDEAS = [(t("Pareja zombi con gorras y luces neón verde y morado, portada de álbum"), "neon_oscuro"),
         (t("Dos esqueletos con capucha y alas sosteniendo la Tierra, cielo con rayos"), "render3d"),
         (t("Esqueleto urbano con gorra roja y humo, luna llena"), "urbano")]
FORMATOS = {"png": "PNG (*.png)", "jpg": "JPG (*.jpg)", "pdf": "PDF (*.pdf)", "svg": "SVG (*.svg)"}
# PNG y JPG; PDF y SVG salen en vectores. Los de texto son los tamaños fijos de diseno.TAMANOS_EXPORTAR, con nombre
# corto: el combo no tiene ancho fijo (la portada de música se explica en su ayuda)
ESCALAS = {1: "1x", 2: "2x", 4: "4x", "4k": t("4K (3840 px)"), "portada": t("Portada 3000×3000")}
FILTRO_IMAGENES = t("Imágenes ({tipos})", tipos=" ".join("*" + e for e in sorted(seguro.IMAGENES)))
# ESTILO no pinta diálogos ni menús: con Windows en modo claro saldrían claros con el texto claro de la app
OSCURO = ("QDialog, QMenu { background: #17171D; } QMenu { border: 1px solid #2C2C36; padding: 4px; }"
          "QMenu::item { padding: 8px 18px; border-radius: 6px; } QMenu::item:selected { background: qlineargradient("
          "x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.42), stop:1 rgba(124, 92, 255, 0.20)); }")
LIMITE = 20000  # el rango de x/y que admite motor/diseno.validar
ZOOM_MIN, ZOOM_MAX = 0.05, 8
ALINEAR = {"izquierda": ("align-start-vertical", t("Alinear a la izquierda")),
           "centro_h": ("align-center-vertical", t("Centrar en horizontal")),
           "derecha": ("align-end-vertical", t("Alinear a la derecha")),
           "arriba": ("align-start-horizontal", t("Alinear arriba")),
           "centro_v": ("align-center-horizontal", t("Centrar en vertical")),
           "abajo": ("align-end-horizontal", t("Alinear abajo"))}
# Solo esta página: letra de 13 px y controles de unos 28 px, para que el lienzo se lleve casi toda la pantalla
COMPACTO = """
* { font-size: 13px; }
QLineEdit, QComboBox, QSpinBox, QTextEdit { padding: 3px 6px; border-radius: 5px; min-height: 20px; }
QSpinBox QLineEdit { padding: 0; border: none; min-height: 0; background: transparent; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QSpinBox::up-arrow, QSpinBox::down-arrow { image: none; }
QComboBox { padding-right: 22px; }
QComboBox::drop-down { width: 20px; }
QComboBox QAbstractItemView::item { min-height: 24px; }
#secundario { padding: 4px 10px; border-radius: 6px; }
#principal { padding: 4px 16px; border-radius: 6px; }
#herr, #panel, QScrollArea#lateral { background: #17171D; }
#barra_sup, #barra_ia { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1C1C24, stop:1 #15151B); }
#barra_sup { border-bottom: 1px solid #24242C; }
#barra_ia { border-top: 1px solid #24242C; }
#herr { border-right: 1px solid #24242C; }
QScrollArea#lateral { border-left: 1px solid #24242C; }
#herr QToolButton { border: 1px solid transparent; border-radius: 8px; padding: 5px; }
#panel QToolButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.08),
                                                 stop:1 rgba(255, 255, 255, 0.03));
                     border: 1px solid rgba(255, 255, 255, 0.08); border-top-color: rgba(255, 255, 255, 0.16);
                     border-radius: 5px; padding: 4px; }
#herr QToolButton:hover, #panel QToolButton:hover, #barra_estado QToolButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.12), stop:1 rgba(255, 255, 255, 0.05));
    border-color: rgba(255, 255, 255, 0.08); border-top-color: rgba(255, 255, 255, 0.18); }
#herr QToolButton:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(168, 146, 255, 0.55),
                                                        stop:1 rgba(118, 86, 250, 0.20));
                            border-color: rgba(150, 125, 255, 0.45); border-top-color: rgba(225, 215, 255, 0.60); }
#seccion { color: #FFFFFF; font-weight: 700; padding-top: 4px; }
#barra_estado { background: #111116; border-top: 1px solid #24242C; }
#barra_estado QLabel, #barra_estado QToolButton { color: #9A9AA8; font-size: 12px; }
#barra_estado QToolButton { border: none; border-radius: 4px; padding: 1px 6px; }
QListWidget { padding: 2px; border-radius: 6px; }
QListWidget::item { padding: 4px 6px; border-radius: 5px; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px; }
QProgressBar { height: 8px; font-size: 10px; }
"""
# El reflejo fino en los botones bajos de esta página. Esta hoja gana a la de la app sea cual sea la especificidad: el
# reflejo se quita aquí también al pulsar o desactivar (en ESTILO lo quita el atajo «background:» de esos estados)
COMPACTO += f"""
#principal, #secundario, #herr QToolButton:checked {{ {REFLEJO_FINO} }}
#principal:pressed, #principal:disabled, #secundario:pressed, #secundario:disabled {{ background-image: none; }}
"""


def carpeta_exportar() -> Path:
    """Imágenes del usuario / Ráfaga Studio: lo exportado queda junto a sus fotos, no escondido dentro de la app."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)) / "Ráfaga Studio"


def fuentes() -> dict[str, str]:
    """Las fuentes para elegir: primero las de assets/fuentes, que salen igual en cualquier PC; luego las del sistema
    sin las privadas ni las de símbolos o de sistema (Wingdings, Segoe MDL2 Assets…), que pintan iconos o rayas."""
    sistema = [f for f in QFontDatabase.families() if not QFontDatabase.isPrivateFamily(f)
               and QFontDatabase.WritingSystem.Latin in QFontDatabase.writingSystems(f)
               and not re.search(r"MDL2 Assets|Fixedsys", f)]
    return {f: f for f in recursos.fuentes() + sistema}


def pedir_color(padre, inicial: str, titulo: str = t("Elige un color")) -> str | None:
    dialogo = QColorDialog(QColor(inicial or "#000000"), padre)
    dialogo.setWindowTitle(titulo)
    dialogo.setStyleSheet(OSCURO)
    return dialogo.selectedColor().name() if dialogo.exec() else None


def elegir_opcion(padre, pregunta: str, opciones: list[str]) -> str | None:
    """La IA duda (p. ej. «¿calavera o carabela?»): el usuario elige una lectura, o None si cancela."""
    caja = QMessageBox(QMessageBox.Question, t("¿Qué quisiste decir?"), pregunta, parent=padre)
    caja.setTextFormat(Qt.PlainText)  # lo escribe la IA
    botones = {caja.addButton(o.replace("&", "&&"), QMessageBox.AcceptRole): o for o in opciones[:3]}
    caja.addButton(QMessageBox.Cancel)
    caja.exec()
    return botones.get(caja.clickedButton())


def pedir_ilustracion(padre) -> tuple[str, str] | None:
    """Descripción y estilo de la ilustración que la IA dibujará como capa nueva; None si se cancela."""
    dialogo = QDialog(padre)
    dialogo.setWindowTitle(t("Generar con IA"))
    dialogo.setStyleSheet(OSCURO)
    dialogo.setMinimumWidth(480)
    descripcion, estilo = QLineEdit(), _combo(ESTILOS_IA)
    descripcion.setMaxLength(1000)
    descripcion.setPlaceholderText(t("Ej.: calavera gótica con rosas"))
    botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    botones.accepted.connect(dialogo.accept)
    botones.rejected.connect(dialogo.reject)
    form = QFormLayout(dialogo)
    form.addRow(t("Qué dibujar"), descripcion)
    form.addRow(t("Estilo"), estilo)
    form.addRow(botones)
    texto = descripcion.text().strip() if dialogo.exec() else ""
    return (texto, estilo.currentData()) if texto else None


def pedir_cambio(padre) -> str | None:
    """Lo que la IA cambiará en la imagen elegida («ponle gorra roja y humo verde»); None si se cancela."""
    dialogo = QDialog(padre)
    dialogo.setWindowTitle(t("Editar con IA"))
    dialogo.setStyleSheet(OSCURO)
    dialogo.setMinimumWidth(480)
    cambio = QLineEdit()
    cambio.setMaxLength(1000)
    cambio.setPlaceholderText(t("Ej.: ponle gorra roja y humo verde"))
    botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    botones.accepted.connect(dialogo.accept)
    botones.rejected.connect(dialogo.reject)
    form = QFormLayout(dialogo)
    form.addRow(t("Qué cambiar"), cambio)
    form.addRow(_rotulo(t("Lo demás de la imagen se queda igual.")))
    form.addRow(botones)
    return (cambio.text().strip() if dialogo.exec() else "") or None


def alineado(capa: dict, como: str, ancho: int, alto: int) -> dict:
    """La x o la y que pegan la caja de la capa a un borde o al centro de una mesa de ancho × alto."""
    return {"izquierda": {"x": 0}, "centro_h": {"x": round((ancho - capa["ancho"]) / 2)},
            "derecha": {"x": ancho - capa["ancho"]}, "arriba": {"y": 0},
            "centro_v": {"y": round((alto - capa["alto"]) / 2)}, "abajo": {"y": alto - capa["alto"]}}[como]


def _sin_fondo(ruta: Path, destino: Path) -> dict:
    """{"ruta"} con el fondo ya quitado, o {"no_liso": el aviso} si sin IA no se puede."""
    try:
        return {"ruta": str(diseno.quitar_fondo(ruta, destino))}
    except diseno.FondoNoLiso as e:
        return {"no_liso": str(e)}


def _combo(opciones: dict) -> QComboBox:
    c = QComboBox()
    # Que no pida el ancho de su opción más larga (una fuente de nombre largo): la fila o el panel se cortarían
    c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(8)
    for valor, texto in opciones.items():
        c.addItem(texto, valor)
    c.view().setMinimumWidth(c.view().sizeHintForColumn(0) + 24)  # la lista desplegada, sí, con los nombres enteros
    return c


def _rotulo(texto: str, clase=QLabel) -> QLabel:
    r = clase(texto)
    r.setTextFormat(Qt.PlainText)
    r.setObjectName("sub")
    return r


class Estado(QLabel):
    """La barra de estado corta los avisos largos: el texto entero sale al pasar el ratón."""
    def setText(self, texto):
        super().setText(texto)
        # Escapado: puede traer lo que escribió la IA o el usuario, y un tooltip con «<» se pintaría como HTML
        self.setToolTip(f"<p>{html.escape(texto)}</p>" if texto else "")


def _barra(nombre: str, widgets, margenes=(8, 4, 8, 4)) -> QFrame:
    """Una barra en fila con su fondo (nombre para la hoja de estilo); None deja un hueco que estira."""
    barra = QFrame()
    barra.setObjectName(nombre)
    lay = QHBoxLayout(barra)
    lay.setContentsMargins(*margenes)
    lay.setSpacing(6)
    for w in widgets:
        lay.addStretch() if w is None else lay.addWidget(w)
    return barra


def _botonera(botones) -> QWidget:
    """Fila de botones de solo icono, con su nombre al pasar el ratón."""
    fila = QWidget()
    lay = QHBoxLayout(fila)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    for nombre, ayuda, accion in botones:
        b = QToolButton()
        b.setIcon(icono(nombre))
        b.setIconSize(QSize(16, 16))
        b.setToolTip(ayuda)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(accion)
        lay.addWidget(b)
    lay.addStretch()
    return fila


def _elemento(texto: str, valor, icono: QIcon | None = None) -> QListWidgetItem:
    item = QListWidgetItem(icono or QIcon(), texto)  # las listas pintan texto plano: un nombre no puede meter HTML
    item.setData(Qt.UserRole, valor)
    return item


def iconos(texto: str) -> list[QListWidgetItem]:
    elementos = []
    for nombre in recursos.buscar_iconos(texto, 120):
        dibujo = QPixmap(48, 48)
        dibujo.fill(Qt.transparent)
        p = QPainter(dibujo)
        QSvgRenderer(QByteArray(recursos.svg_icono(nombre, "#ECECF1"))).render(p)
        p.end()
        elementos.append(_elemento(nombre, nombre, QIcon(dibujo)))
    return elementos


def emojis(texto: str) -> list[QListWidgetItem]:
    fuente = QFont()
    fuente.setFamilies(recursos.FUENTE_EMOJI)
    fuente.setPixelSize(30)
    elementos = [_elemento(e, e) for e in recursos.buscar_emojis(texto, 160)]
    for e in elementos:
        e.setFont(fuente)
    return elementos


def disenos_guardados(texto: str) -> list[QListWidgetItem]:
    return [_elemento(d["nombre"], d["carpeta"], QIcon(d["miniatura"])) for d in diseno.listar()
            if texto.lower() in d["nombre"].lower()]


def _nombre_capa(capa: dict) -> str:
    nombre = {"texto": t("Texto · {contenido}", contenido=capa.get("texto")), "imagen": t("Imagen"),
              "forma": t("Forma · {forma}", forma=FORMAS.get(capa.get("forma"))),
              "icono": t("Icono · {nombre}", nombre=capa.get("nombre")),
              "emoji": t("Emoji · {emoji}", emoji=capa.get("texto"))}[capa["tipo"]]
    return " ".join(nombre.split())[:40]


def _pintar_color(b, color: str) -> None:
    b.setText(color or t("Sin color"))
    letra = "#111111" if color and QColor(color).lightness() > 140 else "#FFFFFF"
    b.setStyleSheet(f"background: {color or '#20202A'}; color: {letra};")  # color ya validado: #RRGGBB o ""


def _menu(b, opciones) -> None:
    menu = QMenu(b)
    menu.setStyleSheet(OSCURO)
    for texto, accion in opciones:
        menu.addAction(texto).triggered.connect(lambda _=False, a=accion: a())
    b.setMenu(menu)


class Cuadricula(QDialog):
    """Rejilla con buscador para elegir un icono, un emoji o un diseño guardado: lo elegido queda en self.valor."""
    def __init__(self, padre, titulo, elementos, celda=76, pista=t("Buscar en inglés: pizza, phone, heart…")):
        super().__init__(padre)
        self.setWindowTitle(titulo)
        self.setStyleSheet(OSCURO)
        self.resize(720, 560)
        self.elementos, self.valor = elementos, None
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText(pista)
        self.rejilla = QListWidget()
        self.rejilla.setViewMode(QListView.IconMode)
        self.rejilla.setResizeMode(QListView.Adjust)
        self.rejilla.setMovement(QListView.Static)
        self.rejilla.setWordWrap(True)
        self.rejilla.setIconSize(QSize(celda - 28, celda - 28))
        self.rejilla.setGridSize(QSize(celda + 20, celda + 14))
        self.rejilla.itemActivated.connect(self._elegir)
        self.buscar.textChanged.connect(self._llenar)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(lambda: self.rejilla.currentItem() and self._elegir(self.rejilla.currentItem()))
        botones.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        for w in (self.buscar, self.rejilla, botones):
            lay.addWidget(w)
        self._llenar("")

    def _llenar(self, texto):
        self.rejilla.clear()
        for item in self.elementos(texto.strip()):
            self.rejilla.addItem(item)

    def _elegir(self, item):
        self.valor = item.data(Qt.UserRole)
        self.accept()


class DialogoMarca(QDialog):
    """La marca (nombre, eslogan, logo, colores, fuentes y tono) que usan la IA y los diseños nuevos."""
    def __init__(self, padre=None):
        super().__init__(padre)
        self.setWindowTitle(t("Mi marca"))
        self.setStyleSheet(OSCURO)
        self.setMinimumWidth(560)
        self.marca = m = marca.cargar()
        self.nombre, self.eslogan, self.tono = QLineEdit(m["nombre"]), QLineEdit(m["eslogan"]), QLineEdit(m["tono"])
        for campo, maximo in ((self.nombre, 120), (self.eslogan, 300), (self.tono, 500)):
            campo.setMaxLength(maximo)
        self.tono.setPlaceholderText(t("Ej.: cercano y divertido"))
        self.colores = QLineEdit(" ".join(m["colores"]))
        self.colores.setPlaceholderText(t("#FF4D8D #0F0F13 … (hasta 8; el primero es el fondo de los diseños nuevos)"))
        mas = boton(t("+ Color…"))
        mas.clicked.connect(self._anadir_color)
        self.logo = etiqueta(m["logo"] or t("Sin logo"), "sub")
        elegir = boton(t("Elegir logo…"))
        elegir.clicked.connect(self._elegir_logo)
        self.titulo, self.texto = QComboBox(), QComboBox()
        for combo, actual in ((self.titulo, m["fuente_titulo"]), (self.texto, m["fuente_texto"])):
            combo.addItems(list(dict.fromkeys(recursos.fuentes() + [actual])))
            combo.setCurrentText(actual)
        guardar = boton(t("Guardar"), "principal")
        guardar.clicked.connect(self.guardar)
        form = QFormLayout(self)
        form.addRow(t("Nombre"), self.nombre)
        form.addRow(t("Eslogan"), self.eslogan)
        for texto, *widgets in ((t("Logo"), self.logo, elegir), (t("Colores"), self.colores, mas)):
            fila = QHBoxLayout()
            for w in widgets:
                fila.addWidget(w, 1 if w is not widgets[-1] else 0)
            form.addRow(texto, fila)
        form.addRow(t("Fuente de títulos"), self.titulo)
        form.addRow(t("Fuente de textos"), self.texto)
        form.addRow(t("Tono"), self.tono)
        form.addRow(guardar)

    def _anadir_color(self):
        color = pedir_color(self, "#7C5CFF")
        if color:
            self.colores.setText(f"{self.colores.text()} {color}".strip())

    def _elegir_logo(self):
        ruta, _ = QFileDialog.getOpenFileName(self, t("Logo"), "", FILTRO_IMAGENES)
        if ruta:
            try:
                self.marca["logo"] = marca.poner_logo(ruta)  # valida (local y de verdad una imagen) y lo copia
            except ValueError as e:
                return mensaje_error(self, t("Revisa el logo"), e)
            self.logo.setText(self.marca["logo"])

    def guardar(self):
        try:
            marca.guardar({**self.marca, "nombre": self.nombre.text(), "eslogan": self.eslogan.text(),
                           "tono": self.tono.text(), "colores": self.colores.text().replace(",", " ").split(),
                           "fuente_titulo": self.titulo.currentText(), "fuente_texto": self.texto.currentText()})
        except ValueError as e:
            return mensaje_error(self, t("Revisa tu marca"), e)
        self.accept()


class Lienzo(QGraphicsView):
    """El diseño a la vista: arrastrar mueve, las asas de las esquinas cambian el tamaño y se pueden soltar fotos.
    Ctrl+rueda acerca o aleja bajo el ratón, la barra espaciadora (o poner_mano) desplaza la vista y las flechas mueven
    la capa elegida. En modo «Ajustar» la mesa entera se ve siempre, también al cambiar el tamaño de la ventana."""
    zoom_cambiado = Signal()

    def __init__(self, pagina):
        super().__init__()
        self.pagina, self._asa, self.ajustar, self.mano_fija, self._gesto = pagina, None, True, False, object()
        self.con_zoom = False  # Ctrl+rueda: solo donde hay cómo volver a «Ajustar» (Diseño; el editor de video no)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)  # las asas sobresalen de la capa: así no dejan rastro
        self.setBackgroundBrush(QColor("#0B0B0F"))
        self.setFrameShape(QFrame.NoFrame)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMinimumSize(320, 240)
        self.viewport().setMouseTracking(True)  # para cambiar el cursor encima de las asas

    def encajar(self):
        """Modo «Ajustar»: la mesa entera a la vista, con un poco de aire."""
        self.ajustar = True
        r = self.scene().sceneRect()  # la mesa: la vista tiene margen alrededor (ver PaginaDiseno._dibujar)
        m = max(r.width(), r.height()) * 0.04
        self.fitInView(r.adjusted(-m, -m, m, m), Qt.KeepAspectRatio)
        self.zoom_cambiado.emit()

    def zoom(self, nivel: float):
        """Zoom fijo (1 = 100 %, un píxel del diseño por píxel de pantalla), del 5 al 800 %."""
        self.ajustar = False
        f = max(ZOOM_MIN, min(ZOOM_MAX, nivel)) / self.transform().m11()
        self.scale(f, f)
        self.zoom_cambiado.emit()

    def poner_mano(self, si: bool):
        """La mano mueve la vista y no las capas (sin interacción, la escena no se queda el arrastre)."""
        self.setDragMode(QGraphicsView.ScrollHandDrag if si else QGraphicsView.NoDrag)
        self.setInteractive(not si)

    def _mano(self) -> bool:
        return self.dragMode() == QGraphicsView.ScrollHandDrag

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.ajustar:
            self.encajar()

    def wheelEvent(self, e):
        if self.con_zoom and e.modifiers() & Qt.ControlModifier:
            e.accept()
            return self.zoom(self.transform().m11() * 1.2 ** (e.angleDelta().y() / 120))
        if self.ajustar:  # en «Ajustar» la mesa se queda entera a la vista: la rueda no la saca
            return e.accept()
        super().wheelEvent(e)

    def _esquinas(self) -> list[QPointF]:
        item, capa = self.pagina.elegido()
        if capa is None:
            return []
        a, h = capa["ancho"], capa["alto"]
        return [item.mapToScene(QPointF(x, y)) for x, y in ((0, 0), (a, 0), (a, h), (0, h))]

    def _lado(self) -> float:
        return 12 / max(self.transform().m11(), 1e-6)  # 12 px de pantalla a cualquier zoom

    def _asa_en(self, e) -> int | None:
        """La esquina (0-3) de la capa elegida más cercana al ratón, o None. La más cercana y no la primera: en una
        capa fina (una línea) las asas se solapan."""
        punto, lado = self.mapToScene(e.position().toPoint()), self._lado()
        d, i = min(((max(abs(q.x() - punto.x()), abs(q.y() - punto.y())), i) for i, q in enumerate(self._esquinas())),
                   default=(lado + 1, None))
        return i if d <= lado else None

    def drawForeground(self, p, rect):
        esquinas = self._esquinas()
        if not esquinas:
            return
        p.setPen(QPen(QColor("#7C5CFF"), 0))  # grosor 0: una línea de 1 px a cualquier zoom
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF(esquinas))
        p.setBrush(QColor("#FFFFFF"))
        lado = self._lado()
        for q in esquinas:
            p.drawRect(QRectF(q.x() - lado / 2, q.y() - lado / 2, lado, lado))

    def mousePressEvent(self, e):
        i = self._asa_en(e) if e.button() == Qt.LeftButton and not self._mano() else None
        if i is None:
            return super().mousePressEvent(e)
        item, _ = self.pagina.elegido()
        # La esquina opuesta queda fija; object() marca este gesto para que todo él sea un solo «deshacer»
        self._asa = (item.sceneTransform(), item.mapFromScene(self._esquinas()[(i + 2) % 4]), object())

    def mouseMoveEvent(self, e):
        if not self._asa:
            if not self._mano():
                i = self._asa_en(e)
                self.viewport().setCursor(Qt.ArrowCursor if i is None else
                                          Qt.SizeFDiagCursor if i % 2 == 0 else Qt.SizeBDiagCursor)
            return super().mouseMoveEvent(e)
        transformacion, fijo, gesto = self._asa
        q = transformacion.inverted()[0].map(self.mapToScene(e.position().toPoint())) - fijo
        # El tope del núcleo (FACTOR_CAPA veces el lienzo), aplicado aquí: recortada luego, la esquina fija se movería
        tope_x, tope_y = (diseno.FACTOR_CAPA * self.pagina.diseno[k] for k in ("ancho", "alto"))
        q = QPointF(max(-tope_x, min(tope_x, q.x())), max(-tope_y, min(tope_y, q.y())))
        caja = QRectF(fijo, fijo + q).normalized()
        if caja.width() >= 5 and caja.height() >= 5:
            centro = transformacion.map(caja.center())  # gira alrededor de su centro: así la esquina fija no se mueve
            self.pagina._cambiar(gesto, x=round(centro.x() - caja.width() / 2), y=round(centro.y() - caja.height() / 2),
                                 ancho=round(caja.width()), alto=round(caja.height()))

    def mouseReleaseEvent(self, e):
        if self._asa:
            self._asa = None
            return
        super().mouseReleaseEvent(e)
        self.pagina.guardar_posiciones()

    def keyPressEvent(self, e):
        _, capa = self.pagina.elegido()
        paso = 10 if e.modifiers() & Qt.ShiftModifier else 1
        flechas = {Qt.Key_Left: (-paso, 0), Qt.Key_Right: (paso, 0), Qt.Key_Up: (0, -paso), Qt.Key_Down: (0, paso)}
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            return self.poner_mano(True)
        if capa and e.key() in flechas:  # cada pulsación, un «deshacer»; mantenerla pulsada (repeticiones), uno solo
            if not e.isAutoRepeat():
                self._gesto = object()
            return self.pagina._cambiar(self._gesto, x=capa["x"] + flechas[e.key()][0],
                                        y=capa["y"] + flechas[e.key()][1])
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and capa:
            return self.pagina.borrar_capa()
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self.poner_mano(self.mano_fija)
        super().keyReleaseEvent(e)

    def dragEnterEvent(self, e):
        e.setAccepted(e.mimeData().hasUrls())

    dragMoveEvent = dragEnterEvent  # sin esto la escena rechaza el arrastre (ninguna capa acepta soltar)

    def dropEvent(self, e):
        punto = self.mapToScene(e.position().toPoint())
        for url in e.mimeData().urls():
            if url.isLocalFile():  # \\servidor\… también es «local» para Qt: lo para archivo_valido
                self.pagina.anadir_imagen(url.toLocalFile(), punto)
        e.acceptProposedAction()


class PaginaDiseno(QWidget):
    def __init__(self):
        super().__init__()
        diseno.asegurar_qt()  # registra las fuentes incluidas antes de llenar la lista de fuentes
        self.diseno, self.carpeta, self.escena, self.tarea, self.exportado = diseno.nuevo(), None, None, None, None
        self.deshacer_pila, self.rehacer_pila, self._ultima, self.sucio, self._cargando = [], [], None, False, False
        self._anterior = None  # ver _lanzar
        self.setStyleSheet(COMPACTO)
        self.vista = Lienzo(self)
        self.vista.setBackgroundBrush(QColor("#2A2A30"))  # el tablero alrededor de la mesa, distinto de ella
        self.vista.con_zoom = True
        # Sin barras: la vista tiene margen alrededor de la mesa (para el zoom y la mano) y se verían siempre
        self.vista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.vista.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._herramientas())
        cuerpo.addWidget(self.vista, 1)
        cuerpo.addWidget(self._paneles())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._barra_archivo())
        lay.addLayout(cuerpo, 1)
        lay.addWidget(self._barra_ia())  # a todo lo ancho: el pedido tiene sitio en cualquier idioma
        lay.addWidget(self._barra_estado())
        self.vista.zoom_cambiado.connect(self._al_zoom)
        for tecla, accion in ((QKeySequence.Undo, self.deshacer), (QKeySequence.Redo, self.rehacer),
                              ("Ctrl+0", self.vista.encajar), ("Ctrl+1", lambda: self.vista.zoom(1)),
                              ("Ctrl+K", self.pedido.setFocus), ("Ctrl+Shift+G", self.editar_con_ia),
                              ("Ctrl+Shift+B", self.quitar_fondo)):
            self._atajo(tecla, accion)
        self._dibujar()

    # ---------- Construcción ----------

    def _atajo(self, tecla, accion, padre=None):
        atajo = QShortcut(QKeySequence(tecla), padre or self)
        atajo.setContext(Qt.WidgetWithChildrenShortcut)  # solo con esta página (o el padre) delante
        atajo.activated.connect(accion)

    def _barra_archivo(self):
        """Arriba, en una sola fila: archivo, nombre, deshacer y exportar."""
        nuevo, abrir, guardar = boton(f"📄  {t('Nuevo')}"), boton(f"📂  {t('Abrir')}"), boton(f"💾  {t('Guardar')}")
        _menu(nuevo, [(f"{nombre}  ·  {a}×{h}", lambda c=clave: self._descartar_ok() and self.nuevo(c))
                      for clave, (a, h, nombre) in diseno.TAMANOS.items()])
        abrir.clicked.connect(lambda: self._descartar_ok() and self._cuadricula(
            t("Abrir un diseño"), disenos_guardados, self.abrir, celda=170, pista=t("Buscar por nombre")))
        guardar.clicked.connect(self.guardar)
        self.nombre = QLineEdit()
        self.nombre.setMaxLength(120)
        self.nombre.setMaximumWidth(320)
        self.nombre.setPlaceholderText(t("Nombre del diseño"))
        self.nombre.textEdited.connect(self._renombrar)
        self.deshacer_btn, self.rehacer_btn = boton("↶"), boton("↷")
        self.deshacer_btn.setToolTip(t("Deshacer (Ctrl+Z)"))
        self.rehacer_btn.setToolTip(t("Rehacer (Ctrl+Y)"))
        self.deshacer_btn.clicked.connect(self.deshacer)
        self.rehacer_btn.clicked.connect(self.rehacer)
        self.escala = _combo(ESCALAS)
        self.escala.setToolTip(t("Tamaño del PNG o JPG exportado: 2x y 4x, para imprimir o para pantallas grandes; "
                                 "4K, 3840 px de lado largo; Portada, la de música (3000×3000)"))
        exportar, carpeta = boton(f"⬇  {t('Exportar')}", "principal"), boton("📁")
        carpeta.setToolTip(t("Abrir la carpeta de lo exportado"))
        exportar.clicked.connect(self._pedir_exportar)
        carpeta.clicked.connect(self.abrir_carpeta)
        return _barra("barra_sup", [nuevo, abrir, guardar, self.nombre, self.deshacer_btn, self.rehacer_btn, None,
                                    self.escala, exportar, carpeta])

    def _herramientas(self):
        """La columna de herramientas: Selección y Mano se quedan puestas; las demás añaden una capa al momento."""
        columna = QFrame()
        columna.setObjectName("herr")
        columna.setFixedWidth(44)
        lay = QVBoxLayout(columna)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(2)
        self.seleccion = self._herramienta("mouse-pointer-2", t("Selección"), "V", lambda: self._modo(False))
        self.mano = self._herramienta("hand", t("Mano: mueve la vista (o mantén la barra espaciadora)"), "H",
                                      lambda: self._modo(True))
        grupo = QButtonGroup(self)
        for b in (self.seleccion, self.mano):
            b.setCheckable(True)
            grupo.addButton(b)
            lay.addWidget(b)
        self.seleccion.setChecked(True)
        lay.addSpacing(8)
        imagen = [(t("Desde un archivo…"), self._imagen_de_archivo), (t("Generar con IA…"), self.generar_ilustracion),
                  (t("Editar con IA la elegida…"), self.editar_con_ia), (t("Quitar el fondo de la elegida"),
                                                                        self.quitar_fondo)]
        fondo = [(t("Color liso…"), self.fondo_color), (t("Degradado…"), self.fondo_degradado),
                 (t("Imagen…"), self.fondo_imagen)]
        for b in (self._herramienta("type", t("Texto"), "T", self.anadir_texto),
                  self._herramienta("square", t("Rectángulo"), "M", lambda: self.anadir_forma("rectangulo")),
                  self._herramienta("circle", t("Elipse"), "L", lambda: self.anadir_forma("elipse")),
                  self._herramienta("minus", t("Línea"), "\\", lambda: self.anadir_forma("linea")),
                  self._herramienta("image", t("Imagen (mantén pulsado para generarla con IA)"), "Ctrl+Shift+P",
                                    self._imagen_de_archivo, imagen),
                  self._herramienta("shapes", t("Icono"), "I", lambda: self._cuadricula(
                      t("Elige un icono"), iconos, self.anadir_icono)),
                  self._herramienta("smile", t("Emoji"), "E", lambda: self._cuadricula(
                      t("Elige un emoji"), emojis, self.anadir_emoji, celda=56)),
                  self._herramienta("paint-bucket", t("Fondo"), "B", None, fondo),
                  self._herramienta("sparkles", t("Generar con IA…"), "G", self.generar_ilustracion, color="#B9A6FF")):
            lay.addWidget(b)
        lay.addStretch()
        return columna

    def _herramienta(self, nombre, ayuda, tecla, accion, menu=None, color=COLOR):
        """Botón de la columna con su atajo de teclado; con menú y sin acción, el clic abre el menú."""
        b = QToolButton()
        b.setIcon(icono(nombre, color))
        b.setIconSize(QSize(20, 20))
        b.setToolTip(f"{ayuda}  ({QKeySequence(tecla).toString(QKeySequence.NativeText)})")
        b.setCursor(Qt.PointingHandCursor)
        if menu:
            _menu(b, menu)
            b.setPopupMode(QToolButton.DelayedPopup if accion else QToolButton.InstantPopup)
        if accion:
            b.clicked.connect(accion)
        # Las de una letra, solo con el lienzo activo (como en Illustrator): un desplegable o la lista de capas con el
        # foco dejan pasar las letras y añadirían una capa
        self._atajo(tecla, accion or b.showMenu, self.vista if len(tecla) == 1 else None)
        return b

    def _modo(self, mano: bool):
        (self.mano if mano else self.seleccion).setChecked(True)
        self.vista.mano_fija = mano
        self.vista.poner_mano(mano)

    def _barra_ia(self):
        """Bajo el lienzo: qué quieres, ideas y Diseñar; debajo, tipo de pieza, estilo, calidad y marca."""
        chispa = QLabel()
        chispa.setPixmap(icono("sparkles", "#B9A6FF").pixmap(18, 18))
        self.pedido = QLineEdit()
        self.pedido.setMaxLength(2000)
        self.pedido.setPlaceholderText(t("Ej.: calavera gótica para camiseta, logo de mi barbería…"))
        self.pedido.setToolTip(t("Pídeselo a la IA (Ctrl+K)"))
        self.pedido.returnPressed.connect(self.disenar_con_ia)
        self.tipo_ia, self.estilo_ia, self.calidad = _combo(TIPOS_IA), _combo(ESTILOS_IA), _combo(CALIDADES)
        self._calidades()
        ideas = boton("💡")  # solo el icono: el pedido necesita el ancho
        ideas.setToolTip(t("Ideas"))
        _menu(ideas, [(texto, lambda texto=texto, estilo=estilo: (
            self.pedido.setText(texto), self.estilo_ia.setCurrentIndex(self.estilo_ia.findData(estilo))))
            for texto, estilo in IDEAS])
        self.usar_marca = QCheckBox(t("Usar mi marca"))
        self.usar_marca.setChecked(True)
        mi_marca = boton(t("Mi marca…"))
        mi_marca.clicked.connect(lambda: DialogoMarca(self).exec())
        self.disenar = boton(f"✨  {t('Diseñar')}", "principal")
        self.disenar.clicked.connect(self.disenar_con_ia)
        # En dos filas: en una, el pedido se quedaba sin sitio (y la página con scroll) en pantallas de 1280 px
        filas = QFrame()
        filas.setObjectName("barra_ia")
        lay = QVBoxLayout(filas)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)
        lay.addWidget(_barra("", [chispa, self.pedido, ideas, self.disenar], (0, 0, 0, 0)))
        lay.addWidget(_barra("", [_rotulo(t("Tipo")), self.tipo_ia, _rotulo(t("Estilo")), self.estilo_ia,
                                  _rotulo(t("Calidad")), self.calidad, self.usar_marca, mi_marca, None], (0, 0, 0, 0)))
        return filas

    def showEvent(self, e):
        self._calidades()  # Gemini se puede elegir en «Claves de IA» con esta página ya abierta
        super().showEvent(e)

    def _calidades(self):
        """2K y 4K solo con Gemini: las demás IA de imágenes dan su tamaño de siempre."""
        gemini = (claves.para("imagen") or {}).get("proveedor") == "gemini"
        for i in range(1, self.calidad.count()):
            self.calidad.model().item(i).setEnabled(gemini)
        if not gemini:
            self.calidad.setCurrentIndex(0)
        self.calidad.setToolTip(t("Resolución de las fotos de la IA: 2K y 4K cuestan más (se avisa antes)") if gemini
                                else t("Elige Gemini en «Claves de IA» para 2K y 4K"))

    def _calidad(self, fotos: int) -> str | None:
        """La calidad elegida; 2K y 4K, solo si el usuario acepta su costo aproximado. None si no lo acepta."""
        calidad = self.calidad.currentData()
        precio = ia.precio_imagen_gemini((claves.para("imagen") or {}).get("clave", ""), calidad)
        if calidad == "1K" or QMessageBox.question(self, CALIDADES[calidad], t(
                "Calidad {calidad} con Gemini: fotos de la IA, hasta {fotos}, a unos {precio} cada una; en total, "
                "hasta unos {costo} según el precio de Google. ¿Seguir?", calidad=calidad, fotos=fotos,
                precio=dinero(precio), costo=dinero(fotos * precio))) == QMessageBox.Yes:
            return calidad
        self.estado.setText(t("Cancelado: no se gastó ninguna imagen."))
        return None

    def _barra_estado(self):
        """Abajo: zoom, tamaño de la mesa, capa elegida y lo que está pasando."""
        self.zoom_btn = QToolButton()
        self.zoom_btn.setPopupMode(QToolButton.InstantPopup)
        self.zoom_btn.setToolTip(t("Zoom: Ctrl+rueda del ratón · Ctrl+0 ajustar · Ctrl+1 al 100 %"))
        _menu(self.zoom_btn, [(t("Ajustar a la ventana"), self.vista.encajar)] +
              [(f"{n} %", lambda n=n: self.vista.zoom(n / 100)) for n in (25, 50, 100, 200, 400)])
        self.mesa, self.capa_txt, self.estado = _rotulo(""), _rotulo(""), _rotulo("", Estado)
        self.estado.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # un aviso largo se corta, no ensancha
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.setFixedWidth(160)
        self.progreso.hide()
        barra = _barra("barra_estado", [self.zoom_btn, self.mesa, self.capa_txt, self.estado, self.progreso],
                       (6, 2, 10, 2))
        barra.layout().setSpacing(14)
        barra.layout().setStretchFactor(self.estado, 1)
        return barra

    def _paneles(self):
        panel = QWidget()
        panel.setObjectName("panel")
        col = QVBoxLayout(panel)
        col.setContentsMargins(10, 6, 10, 8)
        col.setSpacing(6)
        self.titulo_props = etiqueta("", "seccion")
        self.form = QFormLayout()
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)  # una fila que no cabe al lado de su nombre va debajo
        self.form.setVerticalSpacing(6)
        col.addWidget(self.titulo_props)
        col.addLayout(self.form)
        self.w, self.filas = {}, []
        self._fila(t("Posición"), "X", self._numero("x", -LIMITE, LIMITE), "Y", self._numero("y", -LIMITE, LIMITE))
        self._fila(t("Tamaño"), t("Ancho"), self._numero("ancho", 1, 20000), t("Alto"), self._numero("alto", 1, 20000))
        self._fila(t("Giro"), self._numero("rotacion", -360, 360, "°"))
        self._fila(t("Opacidad"), self._numero("opacidad", 0, 100, " %"))
        self._fila(t("Fusión"), self._opciones("fusion", FUSIONES))
        texto = self.w["texto"] = QTextEdit()
        texto.setAcceptRichText(False)  # pegar desde una web mete solo el texto
        texto.setFixedHeight(60)
        texto.textChanged.connect(lambda: self._cambiar("texto", texto=texto.toPlainText()[:2000]))
        self._fila(t("Texto"), texto)
        self._fila(t("Fuente"), self._opciones("fuente", fuentes()))
        self._fila(t("Tamaño de letra"), self._numero("tamano", 1, 2000, " px"))
        self._fila(t("Color"), self._color("color"))
        self._fila(t("Estilo"), self._casilla("negrita", t("Negrita")), self._casilla("cursiva", t("Cursiva")),
                   self._casilla("sombra", t("Sombra")))
        self._fila(t("Alineación"), self._opciones("alineacion", {"izquierda": t("Izquierda"), "centro": t("Centro"),
                                                                  "derecha": t("Derecha")}))
        self._fila(t("Contorno"), self._color("contorno"), self._numero("grosor_contorno", 0, 200, " px"))
        self._fila(t("Forma"), self._opciones("forma", FORMAS))
        self._fila(t("Relleno"), self._color("relleno"))
        self._fila(t("Borde"), self._color("borde"), self._numero("grosor_borde", 0, 200, " px"))
        self._fila(t("Esquinas"), self._numero("redondeo", 0, 10000, " px"))
        self._fila(t("Ajuste"), self._opciones("ajuste", {"cubrir": t("Cubrir la caja"),
                                                          "contener": t("Imagen entera")}))
        sin_ajustes = QToolButton()
        sin_ajustes.setIcon(icono("rotate-ccw"))
        sin_ajustes.setToolTip(t("Quitar los ajustes de la imagen"))
        sin_ajustes.clicked.connect(lambda: self._cambiar(object(), **dict.fromkeys(diseno.AJUSTES, 0)))
        self._fila(t("Brillo"), self._deslizador("brillo", -100, 100), sin_ajustes)
        self._fila(t("Contraste"), self._deslizador("contraste", -100, 100))
        self._fila(t("Saturación"), self._deslizador("saturacion", -100, 100))
        self._fila(t("Desenfoque"), self._deslizador("desenfoque", 0, 100))
        editar, quitar = boton(f"✨ {t('Editar con IA…')}"), boton(f"✂ {t('Quitar fondo')}")
        for b, ayuda, tecla, accion in ((editar, t("Cambia lo que pidas y deja el resto igual"), "Ctrl+Shift+G",
                                         self.editar_con_ia),
                                        (quitar, t("Si el fondo es liso, gratis en tu PC; si no, con IA"),
                                         "Ctrl+Shift+B", self.quitar_fondo)):
            b.setToolTip(f"{ayuda}  ({QKeySequence(tecla).toString(QKeySequence.NativeText)})")
            b.clicked.connect(accion)
        self._fila(t("Imagen"), editar, campos=["archivo"])
        self._fila("", quitar, campos=["archivo"])
        col.addWidget(etiqueta(t("Alinear al lienzo"), "seccion"))
        col.addWidget(_botonera([(nombre, ayuda, lambda _=False, c=c: self.alinear(c))
                                 for c, (nombre, ayuda) in ALINEAR.items()]))
        col.addWidget(etiqueta(t("Capas (la de arriba se ve encima)"), "seccion"))
        self.capas = QListWidget()
        self.capas.setMinimumHeight(150)
        self.capas.currentRowChanged.connect(self._elegir_de_lista)
        col.addWidget(self.capas, 1)
        col.addWidget(_botonera([("arrow-up", t("Subir"), lambda: self.mover_capa(1)),
                                 ("arrow-down", t("Bajar"), lambda: self.mover_capa(-1)),
                                 ("copy", t("Duplicar"), self.duplicar_capa), ("trash-2", t("Borrar"), self.borrar_capa)]))
        # Con su propia barra: así el panel (alto con un texto elegido) no estira la página y el lienzo cabe sin bajar
        desplazable = QScrollArea()
        desplazable.setObjectName("lateral")
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(panel)
        desplazable.setFixedWidth(290)
        return desplazable

    def _fila(self, texto, *widgets, campos=None):
        """Una fila de propiedades; los textos sueltos son rótulos (X, Y…) delante de su campo. Se ve con las capas que
        tienen alguno de sus campos (o de `campos`, si son botones)."""
        fila = QWidget()
        lay = QHBoxLayout(fila)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            lay.addWidget(_rotulo(w) if isinstance(w, str) else w)
        self.form.addRow(texto, fila)
        self.filas.append((fila, campos or [c for c, w in self.w.items() if w in widgets]))

    def _numero(self, campo, minimo, maximo, sufijo=""):
        n = self.w[campo] = QSpinBox()
        n.setRange(minimo, maximo)
        n.setSuffix(sufijo)
        n.valueChanged.connect(lambda v: self._cambiar(campo, **{campo: v / 100 if campo == "opacidad" else v}))
        return n

    def _deslizador(self, campo, minimo, maximo):
        d = self.w[campo] = QSlider(Qt.Horizontal)
        d.setRange(minimo, maximo)
        d.valueChanged.connect(lambda v: (d.setToolTip(str(v)), self._cambiar(campo, **{campo: v})))
        return d

    def _casilla(self, campo, texto):
        c = self.w[campo] = QCheckBox(texto)
        c.toggled.connect(lambda v: self._cambiar(campo, **{campo: v}))
        return c

    def _opciones(self, campo, opciones):
        c = self.w[campo] = _combo(opciones)
        c.currentIndexChanged.connect(lambda _: self._cambiar(campo, **{campo: c.currentData()}))
        return c

    def _color(self, campo):
        b = self.w[campo] = boton("")
        b.clicked.connect(lambda: self._elegir_color(campo))
        return b

    # ---------- Lienzo, selección y propiedades ----------

    def _dibujar(self, elegir=None):
        """Vuelve a montar el lienzo y la lista de capas desde el dict (al abrir, añadir, borrar, deshacer…)."""
        if self.escena:
            self.escena.blockSignals(True)  # la escena vieja se destruye: que no avise de cambios de selección
        escena = diseno.escena(self.diseno, self.carpeta or diseno.CARPETA)
        centro = self.vista.mapToScene(self.vista.viewport().rect().center())
        self.vista.setScene(escena)
        a, h = self.diseno["ancho"], self.diseno["alto"]
        self.vista.setSceneRect(-a, -h, 3 * a, 3 * h)  # margen: sin él, el zoom bajo el ratón y la mano topan con la mesa
        self.escena = escena
        for item in self._items():
            item.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
            item.setSelected(item.data(0) == elegir)
        escena.selectionChanged.connect(self._al_elegir)
        if self.vista.ajustar:
            self.vista.encajar()
        else:
            self.vista.centerOn(centro)  # con zoom, añadir o deshacer no mueve la vista
        if self.nombre.text() != self.diseno["nombre"]:
            self.nombre.setText(self.diseno["nombre"])
        self.mesa.setText(t("Lienzo: {ancho} × {alto} px", ancho=self.diseno["ancho"], alto=self.diseno["alto"]))
        self._cargando = True
        self.capas.clear()
        for capa in reversed(self.diseno["capas"]):  # arriba, la que se ve encima
            self.capas.addItem(_elemento(_nombre_capa(capa), capa["id"]))
        self._cargando = False
        self._al_elegir()
        self.deshacer_btn.setEnabled(bool(self.deshacer_pila))
        self.rehacer_btn.setEnabled(bool(self.rehacer_pila))

    def _al_zoom(self):
        z = round(self.vista.transform().m11() * 100)
        self.zoom_btn.setText(t("Ajustar · {zoom} %", zoom=z) if self.vista.ajustar else f"{z} %")

    def _items(self):
        return [i for i in self.escena.items() if isinstance(i, diseno.ItemCapa) and i.data(0) is not None]

    def elegido(self):
        """(item, capa del dict) de la capa elegida en el lienzo, o (None, None)."""
        for item in self.escena.selectedItems():
            capa = next((c for c in self.diseno["capas"] if c["id"] == item.data(0)), None)
            if capa:
                return item, capa
        return None, None

    def _al_elegir(self):
        """Lo elegido en el lienzo se marca en la lista de capas y llena las propiedades."""
        _, capa = self.elegido()
        ids = [self.capas.item(i).data(Qt.UserRole) for i in range(self.capas.count())]
        self._cargando = True
        self.capas.setCurrentRow(ids.index(capa["id"]) if capa else -1)
        self._cargando = False
        self._mostrar_propiedades()
        self.vista.viewport().update()  # las asas

    def _elegir_de_lista(self, fila):
        if self._cargando or fila < 0:
            return
        elegida = self.capas.item(fila).data(Qt.UserRole)
        for item in self._items():
            item.setSelected(item.data(0) == elegida)

    def _mostrar_propiedades(self):
        _, capa = self.elegido()
        self._cargando = True
        self.titulo_props.setText(t("Propiedades · {capa}", capa=_nombre_capa(capa)) if capa else
                                  t("Elige una capa en el lienzo o en la lista para cambiarla"))
        self.capa_txt.setText(t("Capa: {capa}", capa=_nombre_capa(capa)) if capa else t("Sin capa elegida"))
        for fila, campos in self.filas:
            self.form.setRowVisible(fila, bool(capa) and any(c in capa for c in campos))
        for campo, w in self.w.items():
            v = capa.get(campo) if capa else None
            w.setVisible(v is not None)
            if v is None:
                continue
            if isinstance(w, (QSpinBox, QSlider)):
                w.setValue(round(v * 100 if campo == "opacidad" else v))
            elif isinstance(w, QCheckBox):
                w.setChecked(v)
            elif isinstance(w, QComboBox):
                if w.findData(v) < 0:  # una fuente que no está en este PC (la puso la IA o viene de otro PC)
                    w.addItem(v, v)
                w.setCurrentIndex(w.findData(v))
            elif isinstance(w, QTextEdit):
                if w.toPlainText() != v:  # reponerlo mientras se escribe movería el cursor al principio
                    w.setPlainText(v)
            else:
                _pintar_color(w, v)
        self._cargando = False

    def _cambiar(self, clave, **campos):
        """Cambia la capa elegida (validada) y la repinta. Cambios seguidos con la misma clave (el mismo campo, el
        mismo gesto con un asa) son un solo «deshacer»."""
        item, capa = self.elegido()
        if self._cargando or capa is None:
            return
        nueva = {**capa, **campos}
        for color, grosor in (("contorno", "grosor_contorno"), ("borde", "grosor_borde")):
            if nueva.get(grosor) and not nueva.get(color):
                nueva[color] = "#000000"  # con grosor y sin color no se vería nada
        capas = self.diseno["capas"]
        i = capas.index(capa)
        try:  # con el diseño entero: los topes (tamaño según el lienzo, imágenes, emojis) dependen de todo él
            nueva = diseno.validar({**self.diseno, "capas": capas[:i] + [nueva] + capas[i + 1:]})["capas"][i]
        except ValueError as e:
            self._mostrar_propiedades()  # el campo vuelve a lo que de verdad tiene la capa
            return self.estado.setText(f"⚠️ {e}")
        if nueva == capa:
            return self._mostrar_propiedades()  # si se recortó a lo que ya tenía, el campo enseña el valor recortado
        self._recordar((capa["id"], clave))
        capa.update(nueva)
        item.aplicar(capa)
        if capa["tipo"] == "texto" and clave != "alto":  # crece con el texto (lo que sobresale no se podría elegir);
            # el alto tecleado se respeta. Desde el alto pedido (asa) o el de antes de este cambio: teclear 5, 50, 500
            # en el ancho no deja la caja gigante
            base = nueva["alto"] if "alto" in campos else next(
                (c["alto"] for c in self.deshacer_pila[-1]["capas"] if c["id"] == capa["id"]), capa["alto"])
            letras = round(item.texto.boundingRect().height() - 2 * item.texto.document().documentMargin())
            alto = min(max(base, letras), diseno.FACTOR_CAPA * self.diseno["alto"])
            if alto != capa["alto"]:
                ancla = item.mapToScene(QPointF(0, 0))  # girada, crecer la movería: su esquina de arriba queda fija
                capa["alto"] = alto
                item.aplicar(capa)
                movida = ancla - item.mapToScene(QPointF(0, 0))
                capa.update(x=round(capa["x"] + movida.x()), y=round(capa["y"] + movida.y()))
                item.aplicar(capa)
        self._mostrar_propiedades()
        if self.capas.currentItem():
            self.capas.currentItem().setText(_nombre_capa(capa))

    def alinear(self, como):
        """Pega la capa elegida a un borde o al centro de la mesa (un «deshacer» por clic)."""
        _, capa = self.elegido()
        if capa:
            self._cambiar(object(), **alineado(capa, como, self.diseno["ancho"], self.diseno["alto"]))

    def _elegir_color(self, campo):
        _, capa = self.elegido()
        color = capa and pedir_color(self, capa[campo])
        if color:
            self._cambiar(campo, **{campo: color})

    def guardar_posiciones(self):
        """Tras arrastrar: copia al dict la posición de las capas movidas (un solo «deshacer» por arrastre)."""
        movidas = [(item, capa) for item in self._items() for capa in self.diseno["capas"]
                   if capa["id"] == item.data(0) and item.pos() != QPointF(capa["x"], capa["y"])]
        if not movidas:
            return
        self._recordar()
        for item, capa in movidas:
            capa.update(x=max(-LIMITE, min(LIMITE, round(item.pos().x()))),
                        y=max(-LIMITE, min(LIMITE, round(item.pos().y()))))
            item.aplicar(capa)
        self._mostrar_propiedades()

    # ---------- Deshacer ----------

    def _recordar(self, clave=None):
        """Guarda una copia para deshacer (máx. 50) antes de un cambio."""
        if clave is None or clave != self._ultima:
            self.deshacer_pila = (self.deshacer_pila + [copy.deepcopy(self.diseno)])[-50:]
            self.rehacer_pila.clear()
        self._ultima, self.sucio = clave, True
        self.deshacer_btn.setEnabled(True)
        self.rehacer_btn.setEnabled(False)

    def deshacer(self):
        self._historial(self.deshacer_pila, self.rehacer_pila)

    def rehacer(self):
        self._historial(self.rehacer_pila, self.deshacer_pila)

    def _historial(self, desde, hacia):
        if desde:
            hacia.append(self.diseno)
            _, capa = self.elegido()
            self.diseno, self._ultima, self.sucio = desde.pop(), None, True
            self._dibujar(capa and capa["id"])

    # ---------- Capas ----------

    def _caja(self, ancho, alto, centro=None):
        """Caja de ese tamaño centrada en el punto (o en el lienzo)."""
        c = centro or QPointF(self.diseno["ancho"] / 2, self.diseno["alto"] / 2)
        return {"x": round(c.x() - ancho / 2), "y": round(c.y() - alto / 2), "ancho": round(ancho), "alto": round(alto)}

    def _tinta(self):
        """Blanco o casi negro: lo que mejor se lea sobre el fondo."""
        return "#111111" if QColor(self.diseno["fondo"]["colores"][0]).lightness() > 140 else "#FFFFFF"

    def _lado(self):
        return min(self.diseno["ancho"], self.diseno["alto"])

    def _con_capa(self, capa) -> dict | None:
        """El diseño con la capa añadida encima (validado), o None si no cabe (ya avisado)."""
        if len(self.diseno["capas"]) >= diseno.MAX_CAPAS:
            mensaje(self, t("Demasiadas capas"), t("Un diseño puede tener hasta {n} capas.", n=diseno.MAX_CAPAS))
            return None
        try:  # validar el diseño entero también le da a la capa nueva un id que no choca con otro
            return diseno.validar({**self.diseno, "capas": self.diseno["capas"] + [capa]})
        except ValueError as e:
            mensaje_error(self, t("No se pudo añadir"), e)

    def anadir(self, capa) -> bool:
        """Añade la capa encima de todo y la deja elegida. Lo que falte toma su valor por defecto. False si no cupo."""
        limpio = self._con_capa(capa)
        if limpio:
            self._recordar()
            self.diseno = limpio
            self._dibujar(limpio["capas"][-1]["id"])
        return bool(limpio)

    def anadir_texto(self):
        tamano = max(12, round(self._lado() / 10))
        self.anadir({"tipo": "texto", "texto": t("Escribe aquí"),
                     **self._caja(self.diseno["ancho"] * 0.8, tamano * 1.8),
                     "tamano": tamano, "fuente": marca.cargar()["fuente_titulo"], "negrita": True,
                     "alineacion": "centro", "color": self._tinta()})

    def anadir_forma(self, forma):
        lado = self._lado() * 0.4
        caja = self._caja(lado * 1.5, 20) if forma == "linea" else self._caja(lado, lado)
        self.anadir({"tipo": "forma", "forma": forma, **caja, "grosor_borde": 6 if forma == "linea" else 0})

    def anadir_icono(self, nombre):
        self.anadir({"tipo": "icono", "nombre": nombre, "color": self._tinta(), **self._caja(self._lado() / 5,
                                                                                               self._lado() / 5)})

    def anadir_emoji(self, emoji):
        self.anadir({"tipo": "emoji", "texto": emoji, **self._caja(self._lado() / 5, self._lado() / 5)})

    def anadir_imagen(self, ruta, centro=None) -> bool:
        nombre = self._importar(ruta)
        if not nombre:
            return False
        lector = QImageReader(str(self.carpeta / "imagenes" / nombre))
        tam = lector.size()
        # El núcleo pinta con setAutoTransform(True), pero size() no aplica el giro del EXIF (fotos de móvil)
        if lector.transformation() & QImageIOHandler.TransformationRotate90:
            tam.transpose()
        del lector  # suelta el archivo: Windows no deja borrarlo abierto si luego no cabe
        ancho, alto = (1, 1) if tam.isEmpty() else (tam.width(), tam.height())
        escala = min(self.diseno["ancho"] * 0.6 / ancho, self.diseno["alto"] * 0.6 / alto)  # cabe y no se deforma
        if self.anadir({"tipo": "imagen", "archivo": nombre, **self._caja(max(1, ancho * escala),
                                                                          max(1, alto * escala), centro)}):
            return True
        (self.carpeta / "imagenes" / nombre).unlink(missing_ok=True)  # no cupo: que no quede una copia que nada usa
        return False

    def _imagen_de_archivo(self):
        ruta = self._pedir_imagen()
        if ruta:
            self.anadir_imagen(ruta)

    def _importar(self, ruta) -> str | None:
        """Copia la imagen (validada) a la carpeta del diseño y da su nombre; None si no vale (ya se avisó)."""
        real = archivo_valido(self, ruta, seguro.IMAGENES, "imagen")
        if real:
            try:
                return diseno.importar_imagen(str(real), self._carpeta())
            except (ValueError, OSError) as e:
                mensaje_error(self, t("No se pudo usar la imagen"), e)

    def _pedir_imagen(self, titulo=t("Elige una imagen")):
        ruta, _ = QFileDialog.getOpenFileName(self, titulo, QStandardPaths.writableLocation(
            QStandardPaths.PicturesLocation), FILTRO_IMAGENES)
        return ruta

    def _cuadricula(self, titulo, elementos, al_elegir, **opciones):
        dialogo = Cuadricula(self, titulo, elementos, **opciones)
        if dialogo.exec() and dialogo.valor:
            al_elegir(dialogo.valor)

    def mover_capa(self, paso):
        """paso 1: una capa más arriba (se pinta después); -1: más abajo."""
        _, capa = self.elegido()
        capas = self.diseno["capas"]
        i = capas.index(capa) if capa else -1
        if capa is None or not 0 <= i + paso < len(capas):
            return
        self._recordar()
        capas[i], capas[i + paso] = capas[i + paso], capas[i]
        self._dibujar(capa["id"])

    def duplicar_capa(self):
        _, capa = self.elegido()
        if capa:
            self.anadir({**capa, "id": "", "x": capa["x"] + 30, "y": capa["y"] + 30})

    def borrar_capa(self):
        _, capa = self.elegido()
        if capa:
            self._recordar()
            self.diseno["capas"].remove(capa)
            self._dibujar()

    # ---------- Fondo ----------

    def poner_fondo(self, fondo):
        try:  # con el diseño entero: una foto de fondo cuenta para el tope de imágenes
            limpio = diseno.validar({**self.diseno, "fondo": fondo})["fondo"]
        except ValueError as e:
            return mensaje_error(self, t("No se pudo poner el fondo"), e)
        self._recordar()
        self.diseno["fondo"] = limpio
        _, capa = self.elegido()
        self._dibujar(capa and capa["id"])

    def fondo_color(self):
        color = pedir_color(self, self.diseno["fondo"]["colores"][0], t("Color de fondo"))
        if color:
            self.poner_fondo({"tipo": "color", "colores": [color]})

    def fondo_degradado(self):
        colores = self.diseno["fondo"]["colores"]
        arriba = pedir_color(self, colores[0], t("Color de arriba"))
        abajo = arriba and pedir_color(self, colores[-1], t("Color de abajo"))
        if abajo:
            self.poner_fondo({"tipo": "degradado", "colores": [arriba, abajo]})

    def fondo_imagen(self):
        nombre = (ruta := self._pedir_imagen(t("Imagen de fondo"))) and self._importar(ruta)
        if nombre:  # el color queda debajo, de respaldo
            self.poner_fondo({"tipo": "imagen", "colores": self.diseno["fondo"]["colores"][:1], "imagen": nombre})

    # ---------- Archivo ----------

    def _carpeta(self) -> Path:
        """La carpeta del diseño; se crea la primera vez que hace falta (al guardar o al meter una imagen)."""
        if self.carpeta is None:
            self.carpeta = diseno.nueva_carpeta(self.diseno["nombre"])
        return self.carpeta

    def _empezar(self, nuevo, carpeta):
        diseno._leer_imagen.cache_clear()  # las fotos del diseño anterior (hasta 64 MB cada una) no se quedan en memoria
        self.diseno, self.carpeta = nuevo, carpeta
        self.deshacer_pila, self.rehacer_pila, self._ultima, self.sucio = [], [], None, False
        self.vista.ajustar = True  # otro diseño (quizá de otro tamaño): entero a la vista
        self._dibujar()

    def _descartar_ok(self):
        return not self.sucio or QMessageBox.question(
            self, t("Cambios sin guardar"),
            t("El diseño tiene cambios sin guardar. ¿Seguir sin guardarlos?")) == QMessageBox.Yes

    def _renombrar(self, nombre):
        self._recordar("nombre")  # sin copia, deshacer otro cambio devolvería el nombre viejo; toda la escritura es uno
        self.diseno["nombre"] = nombre

    def nuevo(self, tamano):
        self._empezar(diseno.nuevo(tamano, t("Mi diseño")), None)

    def abrir(self, carpeta):
        try:
            abierto = diseno.abrir(Path(carpeta))  # lo valida todo: puede venir de la IA o de otro PC
        except ValueError as e:
            return mensaje_error(self, t("No se pudo abrir el diseño"), e)
        self._empezar(abierto, Path(carpeta))

    def guardar(self):
        try:
            diseno.guardar(self.diseno, self._carpeta())
        except (ValueError, OSError) as e:
            return mensaje_error(self, t("No se pudo guardar"), e)
        self.sucio = False
        self.estado.setText(f"💾 {t('Guardado en {carpeta}', carpeta=self.carpeta)}")

    def _pedir_exportar(self):
        carpeta = carpeta_exportar()
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = re.sub(r'[\\/:*?"<>|\s]+', " ", self.diseno["nombre"]).strip() or t("Mi diseño")
        ruta, filtro = QFileDialog.getSaveFileName(self, t("Exportar diseño"), str(carpeta / f"{nombre}.png"),
                                                   ";;".join(FORMATOS.values()))
        if ruta:
            extension = {"jpeg": "jpg"}.get(Path(ruta).suffix.lower()[1:], Path(ruta).suffix.lower()[1:])
            self.exportar(Path(ruta), extension if extension in FORMATOS else
                          next((f for f, t in FORMATOS.items() if t == filtro), "png"))

    def exportar(self, destino, formato="png"):
        """Exporta a la escala elegida arriba (1x, 2x, 4x, 4K o portada de música)."""
        try:
            hecho = diseno.exportar(self.diseno, self.carpeta or diseno.CARPETA, destino, formato,
                                    self.escala.currentData())
        except (ValueError, RuntimeError, OSError) as e:
            mensaje_error(self, t("No se pudo exportar"), e)
            return None
        self.exportado = hecho
        self.estado.setText(f"✅ {t('Exportado: {archivo}', archivo=hecho)}")
        return hecho

    def abrir_carpeta(self):
        """La carpeta de lo último exportado (por defecto, Imágenes / Ráfaga Studio)."""
        carpeta = self.exportado.parent if self.exportado else carpeta_exportar()
        carpeta.mkdir(parents=True, exist_ok=True)
        os.startfile(carpeta)

    # ---------- IA ----------

    def _ia(self):
        """motor/diseno_ia, o None (ya avisado). Se importa aquí y no arriba: si falta, el resto del editor funciona."""
        try:
            from motor import diseno_ia
            return diseno_ia
        except ImportError:
            mensaje_error(self, t("Aún no disponible"), t("La IA diseñadora todavía no está instalada en esta versión "
                                                          "de Ráfaga Studio."))

    def _libre(self) -> bool:
        if self.tarea and self.tarea.isRunning():
            mensaje(self, t("Estoy trabajando"), t("Espera a que termine el trabajo actual."))
            return False
        return True

    def _lanzar(self, funcion, al_terminar, prefijo="", error=t("La IA no pudo diseñar")):
        """Corre funcion(aviso) en segundo plano con su progreso abajo. La tarea anterior se guarda también: esta se
        puede lanzar desde su «listo», con su hilo aún cerrándose, y soltarla tumbaría la app."""
        self.disenar.setEnabled(False)
        self.progreso.setValue(0)
        self.progreso.show()
        self._anterior, self.tarea = self.tarea, Tarea(funcion)
        tarea = self.tarea
        tarea.progreso.connect(lambda texto, f: (self.estado.setText(prefijo + texto),
                                                 self.progreso.setValue(int(f * 100))))
        tarea.listo.connect(al_terminar)
        tarea.fallo.connect(lambda e: (self.estado.setText(""), mensaje_error(self, error, e)))
        tarea.finished.connect(lambda: tarea is self.tarea and (self.disenar.setEnabled(True), self.progreso.hide()))
        tarea.start()

    def disenar_con_ia(self):
        """Primero la IA entiende el pedido (sin gastar imágenes) y pregunta si duda; luego diseña."""
        pedido = self.pedido.text().strip()
        if not pedido:
            return mensaje(self, t("Falta el pedido"), t("Escribe qué diseño quieres."))
        diseno_ia = self._ia()
        if diseno_ia and self._libre() and (calidad := self._calidad(diseno_ia.MAX_FOTOS)):
            tipo, estilo, usar_marca = self.tipo_ia.currentData(), self.estilo_ia.currentData(), self.usar_marca.isChecked()
            self.estado.setText(t("Entendiendo el pedido…"))
            self._lanzar(lambda aviso: diseno_ia.entender(pedido, tipo),
                         lambda r: self._crear_con_ia(diseno_ia, pedido, tipo, estilo, usar_marca, r, calidad))

    def _crear_con_ia(self, diseno_ia, pedido, tipo, estilo, usar_marca, r, calidad):
        entendido = str(r.get("entendido") or pedido)
        if not r.get("seguro", True):
            entendido = elegir_opcion(self, str(r.get("pregunta") or ""), [str(o) for o in r.get("opciones") or
                                                                            [entendido]])
            if not entendido:
                return self.estado.setText(t("Cancelado: no se gastó ninguna imagen."))
        # La pieza que eligió el usuario; en «Automático», la que entendió la IA
        tipo = next(c for c in (tipo, r.get("tipo"), "ilustracion", "post") if c in diseno_ia.TIPOS)
        if estilo == "auto" and r.get("estilo") in diseno_ia.ESTILOS:
            estilo = r["estilo"]
        entendi = t("Entendí: {pedido}", pedido=entendido)
        self.estado.setText(entendi)
        self._lanzar(lambda aviso: diseno_ia.crear(pedido=entendido, tipo=tipo, usar_marca=usar_marca, aviso=aviso,
                                                   calidad=calidad, estilo=estilo),
                     self._diseno_listo, f"{entendi} · ")

    def _diseno_listo(self, resultado):
        # Se pregunta al terminar y no al empezar: mientras la IA trabajaba se pudo seguir editando
        if self._descartar_ok():
            self.abrir(resultado["carpeta"])  # se vuelve a leer y validar: lo hizo la IA
            self.estado.setText(f"✨ {t('Listo: cada capa se puede mover y cambiar.')}")
        else:
            guardado = t("El diseño de la IA quedó guardado en {carpeta}: ábrelo con «Abrir».",
                         carpeta=resultado["carpeta"])
            self.estado.setText(f"✨ {guardado}")
            mensaje(self, t("Diseño con IA"), guardado)  # la barra de estado lo cortaría y hay que leerlo entero
        if resultado.get("avisos"):
            mensaje(self, t("Terminado con avisos"), resumen_avisos(resultado["avisos"]))

    def generar_ilustracion(self):
        """«Generar con IA…»: la IA dibuja una ilustración y entra como capa nueva; el diseño abierto se queda."""
        diseno_ia = self._ia()
        # Antes de gastar una imagen de la IA: ¿cabe otra capa de imagen? (topes de capas e imágenes)
        cabe = diseno_ia and self._libre() and self._con_capa({"tipo": "imagen", "archivo": "ilustracion.png"})
        pedido = cabe and pedir_ilustracion(self)
        if pedido and (calidad := self._calidad(1)):
            destino = Path(tempfile.gettempdir()) / f"rafaga-ilustracion-{uuid.uuid4().hex}.png"
            self.estado.setText(t("Dibujando con IA…"))
            self._lanzar(lambda aviso: {"ruta": str(diseno_ia.ilustracion(*pedido, destino, calidad))},
                         self._ilustracion_lista)

    def _ilustracion_lista(self, resultado):
        ruta = Path(resultado["ruta"])
        if self.anadir_imagen(str(ruta)):  # se copia (validada) a la carpeta del diseño
            ruta.unlink(missing_ok=True)
            self.estado.setText(f"✨ {t('Ilustración añadida como capa nueva.')}")
        else:  # mientras dibujaba se llenó el diseño (ya avisado): la ilustración no se pierde
            aviso = t("La ilustración no se añadió; quedó guardada en {ruta}", ruta=ruta)
            self.estado.setText(f"⚠️ {aviso}")
            mensaje(self, t("Generar con IA"), aviso)

    # ---------- Editar la imagen de una capa (un «deshacer»; la nueva queda en la carpeta del diseño) ----------

    def _foto(self):
        """(capa, ruta de su archivo) de la capa imagen elegida, o None (ya avisado)."""
        _, capa = self.elegido()
        if not capa or capa["tipo"] != "imagen":
            mensaje(self, t("Elige una imagen"), t("Elige primero una capa de imagen en el lienzo o en la lista."))
            return None
        ruta = self.carpeta and diseno.ruta_imagen(self.carpeta, capa["archivo"])
        if not ruta:
            mensaje_error(self, t("Falta la imagen"), t("No encuentro el archivo de esta capa en la carpeta del "
                                                        "diseño."))
            return None
        return capa, ruta

    def _costo_ia(self, que: str) -> str | None:
        """La calidad para la IA de imágenes (la de abajo: 2K y 4K solo con Gemini), si el usuario acepta lo que cuesta
        hacer `que`; None si no (ya avisado)."""
        c, calidad = claves.para("imagen") or {}, self.calidad.currentData()
        if c.get("proveedor") == "gemini":
            costo = t("unos {precio} con Gemini (calidad {calidad}, según el precio de Google)", calidad=calidad,
                      precio=dinero(ia.precio_imagen_gemini(c['clave'], calidad)))
        elif c.get("proveedor") == "openai":
            costo = t("unos {precio} con OpenAI (calidad media, según el precio de OpenAI)",
                      precio=dinero(ia.PRECIO_EDITAR_OPENAI))
        else:
            costo = t("una imagen del saldo (pollen) de tu cuenta de Pollinations")
        if QMessageBox.question(self, t("Antes de gastar"), t("{que}\n\nCuesta {costo}. ¿Seguir?", que=que,
                                                                 costo=costo)) == QMessageBox.Yes:
            return calidad
        self.estado.setText(t("Cancelado: no se gastó ninguna imagen."))
        return None

    def editar_con_ia(self):
        """«Editar con IA» (como el relleno generativo de Photoshop): la IA cambia en la imagen elegida solo lo que se
        le pide y deja el resto igual."""
        foto = self._libre() and self._foto()
        if not foto:
            return
        if not ia.puede_referencia():
            return mensaje(self, t("Editar con IA"), ia.SIN_REFERENCIA)
        capa, ruta = foto
        cambio = pedir_cambio(self)
        calidad = cambio and self._costo_ia(t("La IA cambiará en la imagen: «{cambio}», y dejará el resto igual.",
                                              cambio=cambio))
        if calidad:
            self.estado.setText(t("Editando con IA…"))
            self._lanzar(lambda aviso: {"ruta": str(ia.editar_imagen(ruta, cambio, self._temporal(), calidad))},
                         lambda r: self._imagen_editada(capa["id"], r["ruta"], t("Imagen editada con IA.")),
                         error=t("La IA no pudo editar la imagen"))

    def quitar_fondo(self):
        """Quita el fondo liso de la imagen elegida, gratis y en este PC (en segundo plano: una 4K tarda unos
        segundos); si no es liso, ofrece hacerlo con IA."""
        foto = self._libre() and self._foto()
        if not foto:
            return
        capa, ruta = foto
        self.estado.setText(t("Quitando el fondo…"))
        self._lanzar(lambda aviso: _sin_fondo(ruta, self._temporal()), lambda r: self._fondo_quitado(capa, ruta, r),
                     error=t("No se pudo quitar el fondo"))

    def _fondo_quitado(self, capa, ruta, r):
        if "ruta" in r:
            return self._imagen_editada(capa["id"], r["ruta"], t("Fondo quitado: la imagen ya es transparente."))
        self.estado.setText("")
        if not ia.puede_referencia():
            return mensaje(self, t("Quitar fondo"), f"{r['no_liso']}\n\n{ia.SIN_REFERENCIA}")
        diseno_ia = self._ia()
        calidad = diseno_ia and self._costo_ia(t("{error} La IA puede ponerle un fondo verde liso, que luego se "
                                                 "quita aquí.", error=r["no_liso"]))
        if calidad:
            self.estado.setText(t("Quitando el fondo con IA…"))
            self._lanzar(lambda aviso: {"ruta": str(diseno_ia.quitar_fondo_con_ia(ruta, self._temporal(), calidad))},
                         lambda r: self._imagen_editada(capa["id"], r["ruta"], t("Fondo quitado con IA.")),
                         error=t("No se pudo quitar el fondo"))

    @staticmethod
    def _temporal() -> Path:
        return Path(tempfile.gettempdir()) / f"rafaga-edicion-{uuid.uuid4().hex}.png"

    def _imagen_editada(self, capa_id, ruta, hecho):
        """Pone la imagen nueva (validada y copiada a la carpeta del diseño) en la capa, como un paso que se deshace:
        la de antes se queda en la carpeta."""
        ruta = Path(ruta)
        capa = next((c for c in self.diseno["capas"] if c["id"] == capa_id and c["tipo"] == "imagen"), None)
        nombre = capa and self._importar(str(ruta))
        if not nombre:  # mientras trabajaba se borró la capa o se abrió otro diseño: la imagen no se pierde
            aviso = t("La imagen nueva no se puso en ninguna capa; quedó guardada en {ruta}", ruta=ruta)
            self.estado.setText(f"⚠️ {aviso}")
            return mensaje(self, t("Editar imagen"), aviso)
        ruta.unlink(missing_ok=True)
        self._recordar()
        capa["archivo"] = nombre
        self._dibujar(capa_id)
        self.estado.setText(f"✨ {hecho}")
