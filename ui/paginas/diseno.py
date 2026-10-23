"""Página «Diseño»: editor por capas (tipo Canva) para posts, historias, miniaturas, flyers y logos, y la IA que diseña
en capas editables. El diseño es el dict de motor/diseno.py: cada cambio se escribe ahí y el lienzo lo repinta."""
import copy
import os
import re
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, QStandardPaths, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QImageIOHandler, QImageReader, QKeySequence, QPainter,
                           QPen, QPixmap, QPolygonF, QShortcut)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGraphicsItem, QGraphicsView, QHBoxLayout, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QProgressBar, QScrollArea, QSpinBox, QTextEdit,
                               QVBoxLayout, QWidget)

from motor import diseno, marca, recursos, seguro
from motor.idioma import t
from ui.comun import archivo_valido, boton, etiqueta, mensaje, mensaje_error, resumen_avisos, Tarea, tarjeta

FORMAS = {"rectangulo": t("Rectángulo"), "elipse": t("Elipse"), "linea": t("Línea")}
TIPOS_IA = {"anuncio": t("Anuncio"), "post": t("Post"), "historia": t("Historia / Reel"),
            "miniatura": t("Miniatura de YouTube"), "flyer": t("Flyer"), "logo": t("Logo"),
            "tarjeta": t("Tarjeta de presentación"), "marca_personal": t("Marca personal")}
FORMATOS = {"png": "PNG (*.png)", "jpg": "JPG (*.jpg)", "pdf": "PDF (*.pdf)", "svg": "SVG (*.svg)"}
FILTRO_IMAGENES = t("Imágenes ({tipos})", tipos=" ".join("*" + e for e in sorted(seguro.IMAGENES)))
# ESTILO no pinta diálogos ni menús: con Windows en modo claro saldrían claros con el texto claro de la app
OSCURO = ("QDialog, QMenu { background: #17171D; } QMenu { border: 1px solid #2C2C36; padding: 4px; }"
          "QMenu::item { padding: 8px 18px; border-radius: 6px; } QMenu::item:selected { background: #2A2340; }")
LIMITE = 20000  # el rango de x/y que admite motor/diseno.validar


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
        self.tono.setPlaceholderText(t("Ej: cercano y divertido"))
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
    """El diseño a la vista: arrastrar mueve, las asas de las esquinas cambian el tamaño y se pueden soltar fotos."""
    def __init__(self, pagina):
        super().__init__()
        self.pagina, self._asa = pagina, None
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)  # las asas sobresalen de la capa: así no dejan rastro
        self.setBackgroundBrush(QColor("#0B0B0F"))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumSize(420, 400)
        self.viewport().setMouseTracking(True)  # para cambiar el cursor encima de las asas

    def encajar(self):
        r = self.sceneRect()
        m = max(r.width(), r.height()) * 0.04
        self.fitInView(r.adjusted(-m, -m, m, m), Qt.KeepAspectRatio)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.encajar()

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
        i = self._asa_en(e) if e.button() == Qt.LeftButton else None
        if i is None:
            return super().mousePressEvent(e)
        item, _ = self.pagina.elegido()
        # La esquina opuesta queda fija; object() marca este gesto para que todo él sea un solo «deshacer»
        self._asa = (item.sceneTransform(), item.mapFromScene(self._esquinas()[(i + 2) % 4]), object())

    def mouseMoveEvent(self, e):
        if not self._asa:
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
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.pagina.elegido()[1]:
            return self.pagina.borrar_capa()
        super().keyPressEvent(e)

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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(etiqueta(t("Estudio de diseño"), "titulo"))
        lay.addWidget(etiqueta(t("Posts, historias, miniaturas, flyers y logos por capas, como en Canva: pídeselo a "
                                 "la IA o hazlo tú. Arrastra para mover; las esquinas cambian el tamaño."), "sub"))
        lay.addWidget(self._zona_ia())
        lay.addLayout(self._herramientas())
        self.estado = etiqueta("", "sub")
        lay.addWidget(self.estado)
        cuerpo = QHBoxLayout()
        self.vista = Lienzo(self)
        cuerpo.addWidget(self.vista, 1)
        cuerpo.addWidget(self._paneles())
        lay.addLayout(cuerpo, 1)
        for tecla, accion in ((QKeySequence.Undo, self.deshacer), (QKeySequence.Redo, self.rehacer)):
            atajo = QShortcut(tecla, self)
            atajo.setContext(Qt.WidgetWithChildrenShortcut)  # solo con esta página delante
            atajo.activated.connect(accion)
        self._dibujar()

    # ---------- Construcción ----------

    def _zona_ia(self):
        caja, lay = tarjeta()
        titulo = etiqueta(f"✨  {t('Diseñar con IA')}", "sub")
        titulo.setWordWrap(False)
        self.pedido = QLineEdit()
        self.pedido.setPlaceholderText(t("Qué quieres. Ej: anuncio de mi pizzería, 2x1 los martes, con foto de pizza"))
        self.pedido.returnPressed.connect(self.disenar_con_ia)
        self.tipo_ia = QComboBox()
        for clave, nombre in TIPOS_IA.items():
            self.tipo_ia.addItem(nombre, clave)
        self.usar_marca = QCheckBox(t("Usar mi marca"))
        self.usar_marca.setChecked(True)
        mi_marca = boton(t("Mi marca…"))
        mi_marca.clicked.connect(lambda: DialogoMarca(self).exec())
        self.disenar = boton(f"✨  {t('Diseñar con IA')}", "principal")
        self.disenar.clicked.connect(self.disenar_con_ia)
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.hide()
        # El pedido con su título en una fila, para que tenga sitio en cualquier idioma; las opciones, debajo
        arriba, abajo = QHBoxLayout(), QHBoxLayout()
        arriba.addWidget(titulo)
        arriba.addWidget(self.pedido, 1)
        for w in (self.tipo_ia, self.usar_marca, mi_marca):
            abajo.addWidget(w)
        abajo.addStretch()
        abajo.addWidget(self.disenar)
        lay.addLayout(arriba)
        lay.addLayout(abajo)
        lay.addWidget(self.progreso)
        return caja

    def _herramientas(self):
        nuevo, abrir, guardar = boton(f"📄  {t('Nuevo')}"), boton(f"📂  {t('Abrir')}"), boton(f"💾  {t('Guardar')}")
        _menu(nuevo, [(f"{nombre}  ·  {a}×{h}", lambda c=clave: self._descartar_ok() and self.nuevo(c))
                      for clave, (a, h, nombre) in diseno.TAMANOS.items()])
        abrir.clicked.connect(lambda: self._descartar_ok() and self._cuadricula(
            t("Abrir un diseño"), disenos_guardados, self.abrir, celda=170, pista=t("Buscar por nombre")))
        guardar.clicked.connect(self.guardar)
        self.nombre = QLineEdit()
        self.nombre.setMaxLength(120)
        self.nombre.setPlaceholderText(t("Nombre del diseño"))
        self.nombre.textEdited.connect(self._renombrar)
        self.deshacer_btn, self.rehacer_btn = boton("↶"), boton("↷")  # solo el icono: la barra cabe en 1280 px
        self.deshacer_btn.setToolTip(t("Deshacer (Ctrl+Z)"))
        self.rehacer_btn.setToolTip(t("Rehacer (Ctrl+Y)"))
        self.deshacer_btn.clicked.connect(self.deshacer)
        self.rehacer_btn.clicked.connect(self.rehacer)
        exportar, carpeta = boton(f"⬇  {t('Exportar')}", "principal"), boton("📁")
        carpeta.setToolTip(t("Abrir la carpeta de lo exportado"))
        exportar.clicked.connect(self._pedir_exportar)
        carpeta.clicked.connect(self.abrir_carpeta)
        texto, forma, imagen, icono, emoji, fondo = (
            boton(f"➕  {t('Texto')}"), boton(f"➕  {t('Forma')}"), boton(f"➕  {t('Imagen')}"),
            boton(f"➕  {t('Icono')}"), boton(f"➕  {t('Emoji')}"), boton(f"🎨  {t('Fondo')}"))
        texto.clicked.connect(self.anadir_texto)
        _menu(forma, [(nombre, lambda f=f: self.anadir_forma(f)) for f, nombre in FORMAS.items()])
        imagen.clicked.connect(lambda: (ruta := self._pedir_imagen()) and self.anadir_imagen(ruta))
        icono.clicked.connect(lambda: self._cuadricula(t("Elige un icono"), iconos, self.anadir_icono))
        emoji.clicked.connect(lambda: self._cuadricula(t("Elige un emoji"), emojis, self.anadir_emoji, celda=56))
        _menu(fondo, [(t("Color liso…"), self.fondo_color), (t("Degradado…"), self.fondo_degradado),
                      (t("Imagen…"), self.fondo_imagen)])
        arriba, abajo = QHBoxLayout(), QHBoxLayout()
        for w in (nuevo, abrir, guardar, self.nombre, self.deshacer_btn, self.rehacer_btn, exportar, carpeta):
            arriba.addWidget(w, 1 if w is self.nombre else 0)
        for w in (texto, forma, imagen, icono, emoji, fondo):
            abajo.addWidget(w)
        abajo.addWidget(etiqueta(t("También puedes arrastrar fotos al lienzo."), "sub"), 1)
        lay = QVBoxLayout()
        lay.addLayout(arriba)
        lay.addLayout(abajo)
        return lay

    def _paneles(self):
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        props, props_lay = tarjeta()
        self.titulo_props = etiqueta("", "sub")
        self.form = QFormLayout()
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)  # una fila que no cabe al lado de su nombre va debajo
        props_lay.addWidget(self.titulo_props)
        props_lay.addLayout(self.form)
        self.w, self.filas = {}, []
        self._fila(t("Posición"), self._numero("x", -LIMITE, LIMITE), self._numero("y", -LIMITE, LIMITE))
        self._fila(t("Tamaño"), self._numero("ancho", 1, 20000), self._numero("alto", 1, 20000))
        self._fila(t("Giro"), self._numero("rotacion", -360, 360, "°"), self._numero("opacidad", 0, 100, " %"))
        texto = self.w["texto"] = QTextEdit()
        texto.setAcceptRichText(False)  # pegar desde una web mete solo el texto
        texto.setFixedHeight(64)
        texto.textChanged.connect(lambda: self._cambiar("texto", texto=texto.toPlainText()[:2000]))
        self._fila(t("Texto"), texto)
        self._fila(t("Fuente"), self._opciones("fuente", fuentes()))
        self._fila(t("Letra"), self._numero("tamano", 1, 2000, " px"))
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
        capas, capas_lay = tarjeta()
        capas_lay.addWidget(etiqueta(t("Capas (la de arriba se ve encima)"), "sub"))
        self.capas = QListWidget()
        self.capas.setMinimumHeight(170)
        self.capas.currentRowChanged.connect(self._elegir_de_lista)
        fila = QHBoxLayout()
        for texto_b, ayuda, accion in (("▲", t("Subir"), lambda: self.mover_capa(1)),
                                       ("▼", t("Bajar"), lambda: self.mover_capa(-1)),
                                       ("📋", t("Duplicar"), self.duplicar_capa),  # solo el icono: cabe en
                                       ("🗑", t("Borrar"), self.borrar_capa)):     # cualquier idioma
            b = boton(texto_b)
            b.setToolTip(ayuda)
            b.clicked.connect(accion)
            fila.addWidget(b)
        capas_lay.addWidget(self.capas, 1)
        capas_lay.addLayout(fila)
        col.addWidget(props)
        col.addWidget(capas, 1)
        # Con su propia barra: así el panel (alto con un texto elegido) no estira la página y el lienzo cabe sin bajar
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(panel)
        desplazable.setFixedWidth(356)
        return desplazable

    def _fila(self, texto, *widgets):
        fila = QWidget()
        lay = QHBoxLayout(fila)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            lay.addWidget(w)
        self.form.addRow(texto, fila)
        self.filas.append((fila, [c for c, w in self.w.items() if w in widgets]))

    def _numero(self, campo, minimo, maximo, sufijo=""):
        n = self.w[campo] = QSpinBox()
        n.setRange(minimo, maximo)
        n.setSuffix(sufijo)
        n.valueChanged.connect(lambda v: self._cambiar(campo, **{campo: v / 100 if campo == "opacidad" else v}))
        return n

    def _casilla(self, campo, texto):
        c = self.w[campo] = QCheckBox(texto)
        c.toggled.connect(lambda v: self._cambiar(campo, **{campo: v}))
        return c

    def _opciones(self, campo, opciones):
        c = self.w[campo] = QComboBox()
        # Que no pida el ancho de su opción más larga (una fuente de nombre largo): el panel se cortaría por la derecha
        c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        c.setMinimumContentsLength(8)
        for valor, texto in opciones.items():
            c.addItem(texto, valor)
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
        self.vista.setScene(escena)
        self.escena = escena
        for item in self._items():
            item.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
            item.setSelected(item.data(0) == elegir)
        escena.selectionChanged.connect(self._al_elegir)
        self.vista.encajar()
        if self.nombre.text() != self.diseno["nombre"]:
            self.nombre.setText(self.diseno["nombre"])
        self._cargando = True
        self.capas.clear()
        for capa in reversed(self.diseno["capas"]):  # arriba, la que se ve encima
            self.capas.addItem(_elemento(_nombre_capa(capa), capa["id"]))
        self._cargando = False
        self._al_elegir()
        self.deshacer_btn.setEnabled(bool(self.deshacer_pila))
        self.rehacer_btn.setEnabled(bool(self.rehacer_pila))

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
        for fila, campos in self.filas:
            self.form.setRowVisible(fila, bool(capa) and any(c in capa for c in campos))
        for campo, w in self.w.items():
            v = capa.get(campo) if capa else None
            w.setVisible(v is not None)
            if v is None:
                continue
            if isinstance(w, QSpinBox):
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

    def anadir(self, capa):
        """Añade la capa encima de todo y la deja elegida. Lo que falte toma su valor por defecto."""
        if len(self.diseno["capas"]) >= diseno.MAX_CAPAS:
            return mensaje(self, t("Demasiadas capas"), t("Un diseño puede tener hasta {n} capas.", n=diseno.MAX_CAPAS))
        try:  # validar el diseño entero también le da a la capa nueva un id que no choca con otro
            limpio = diseno.validar({**self.diseno, "capas": self.diseno["capas"] + [capa]})
        except ValueError as e:
            return mensaje_error(self, t("No se pudo añadir"), e)
        self._recordar()
        self.diseno = limpio
        self._dibujar(limpio["capas"][-1]["id"])

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

    def anadir_imagen(self, ruta, centro=None):
        nombre = self._importar(ruta)
        if not nombre:
            return
        lector = QImageReader(str(self.carpeta / "imagenes" / nombre))
        tam = lector.size()
        # El núcleo pinta con setAutoTransform(True), pero size() no aplica el giro del EXIF (fotos de móvil)
        if lector.transformation() & QImageIOHandler.TransformationRotate90:
            tam.transpose()
        ancho, alto = (1, 1) if tam.isEmpty() else (tam.width(), tam.height())
        escala = min(self.diseno["ancho"] * 0.6 / ancho, self.diseno["alto"] * 0.6 / alto)  # cabe y no se deforma
        self.anadir({"tipo": "imagen", "archivo": nombre, **self._caja(max(1, ancho * escala), max(1, alto * escala),
                                                                       centro)})

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
        try:
            hecho = diseno.exportar(self.diseno, self.carpeta or diseno.CARPETA, destino, formato)
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

    def disenar_con_ia(self):
        pedido = self.pedido.text().strip()
        if not pedido:
            return mensaje(self, t("Falta el pedido"), t("Escribe qué diseño quieres."))
        try:
            from motor import diseno_ia  # aquí y no arriba: si esta parte aún no está, el resto del editor funciona
        except ImportError:
            return mensaje_error(self, t("Aún no disponible"), t("La IA diseñadora todavía no está instalada en "
                                                                 "esta versión de Ráfaga Studio."))
        self.disenar.setEnabled(False)
        self.progreso.setValue(0)
        self.progreso.show()
        self.tarea = Tarea(diseno_ia.crear, pedido=pedido, tipo=self.tipo_ia.currentData(),
                           usar_marca=self.usar_marca.isChecked())
        self.tarea.progreso.connect(lambda t, f: (self.estado.setText(t), self.progreso.setValue(int(f * 100))))
        self.tarea.listo.connect(self._diseno_listo)
        self.tarea.fallo.connect(lambda e: (self.estado.setText(""),
                                            mensaje_error(self, t("La IA no pudo diseñar"), e)))
        self.tarea.finished.connect(lambda: (self.disenar.setEnabled(True), self.progreso.hide()))
        self.tarea.start()

    def _diseno_listo(self, resultado):
        # Se pregunta al terminar y no al empezar: mientras la IA trabajaba se pudo seguir editando
        if self._descartar_ok():
            self.abrir(resultado["carpeta"])  # se vuelve a leer y validar: lo hizo la IA
            self.estado.setText(f"✨ {t('Listo: cada capa se puede mover y cambiar.')}")
        else:
            self.estado.setText("✨ " + t("El diseño de la IA quedó guardado en {carpeta}: ábrelo con «Abrir».",
                                          carpeta=resultado["carpeta"]))
        if resultado.get("avisos"):
            mensaje(self, t("Terminado con avisos"), resumen_avisos(resultado["avisos"]))
