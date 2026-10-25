"""Página «✂️ Editor de video»: edición a mano como en CapCut. Arriba, la barra de herramientas (medios, audio,
grabarte, texto, stickers, efectos, transiciones, subtítulos, filtros, ajustes, plantillas y avatar IA) y, a la
izquierda, el panel de la elegida; en el centro, la vista previa (el fotograma del video con las capas encima, que se
mueven y cambian de tamaño como en el editor de diseño; las capas de video, con su fotograma en el cursor); a la
derecha, las propiedades de lo elegido; abajo, a todo lo ancho, la línea de tiempo (ui/linea_tiempo.py). «Grabarte»
(ui/grabarte.py) graba tu cara o tu voz mientras el video suena y la pone en el cursor.

El proyecto es el dict de motor/edicion.py y nunca se cambia por dentro: cada cambio hace uno nuevo validado, así el
deshacer es una pila de proyectos. Lo lento (medir archivos, fotogramas, vista previa, exportar, subtítulos, voz) va
en hilos; motor/render_edicion se carga al usarlo y, si aún no está, el editor sigue funcionando con un aviso."""
import os
import re
import shutil
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QIcon, QImage, QKeySequence, QPainter, QPixmap, QShortcut, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGraphicsItem, QGraphicsScene, QHBoxLayout, QLabel,
                               QLineEdit,
                               QListView, QListWidget, QMessageBox, QProgressBar, QScrollArea, QSlider, QSplitter,
                               QStackedWidget, QTextEdit, QToolButton, QVBoxLayout, QWidget)

from motor import diseno, edicion, marca, seguro, video
from motor.idioma import t
from ui.comun import (archivo_valido, boton, etiqueta, mensaje, mensaje_error, NOMBRES_FORMATO, REFLEJO_FINO,
                      SelectorVoz, Tarea, tarjeta)
from ui import iconos
from ui.grabarte import PanelGrabarte, casilla
from ui.linea_tiempo import Hilo, LineaTiempo, nombre, reloj, render
import ui.paginas.diseno as pd

AUN_NO = t("La vista previa y la exportación de video aún no están instaladas en esta versión de Ráfaga Studio. "
           "Puedes seguir editando y guardar el proyecto.")
FILTRO_MEDIOS = t("Videos, fotos y audios ({extensiones})",
                  extensiones=" ".join(f"*{e}" for e in sorted(seguro.VIDEOS | seguro.IMAGENES | seguro.AUDIOS)))
FILTRO_AUDIOS = t("Audios ({extensiones})", extensiones=" ".join("*" + e for e in sorted(seguro.AUDIOS)))
OCULTOS = {"imagen": {"velocidad", "volumen", "silencio"}, "video": {"movimiento"}}  # lo que no aplica a ese clip
PREVIA = 60  # segundos que monta ▶ desde el cursor: un video largo entero tardaría mucho en el PC del usuario
ESTILOS_TEXTO = {  # puntos de partida; luego todo se cambia en Propiedades
    "Texto simple": {"negrita": False},
    "Título con contorno": {"escala": 1.5, "contorno": "#000000", "grosor_contorno": 8},
    "Con sombra": {"sombra": True},
    "Amarillo viral": {"escala": 1.2, "color": "#FFE600", "contorno": "#000000", "grosor_contorno": 6},
    "Neón rosa": {"color": "#FF4D8D", "contorno": "#FFFFFF", "grosor_contorno": 3},
}
# ESTILO (ui.comun) no pinta estas piezas: sin esto saldrían claras con el texto claro de la app
ESTILO_PAGINA = ("QDoubleSpinBox { background: #0F0F13; border: 1px solid #2C2C36; border-radius: 8px; padding: 6px; }"
                 "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 18px; border: none; "
                 "background: #20202A; } QSplitter::handle { background: #24242C; height: 4px; }"
                 # las pestañas de herramientas, como el menú: la elegida es una pastilla de vidrio violeta
                 "#herramienta { border: 1px solid transparent; border-radius: 10px; padding: 5px 3px; font-size: 12px; "
                 "color: #B4B4C0; background: transparent; } #herramienta:hover { color: #FFFFFF; "
                 "background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.06); }"
                 "#herramienta:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                 "stop:0 rgba(168, 146, 255, 0.55), stop:0.55 rgba(124, 92, 255, 0.30), stop:1 rgba(118, 86, 250, 0.18)); "
                 "border-color: rgba(150, 125, 255, 0.45); border-top-color: rgba(225, 215, 255, 0.60); color: #FFFFFF; "
                 f"font-weight: 700; {REFLEJO_FINO} }} #herramienta:focus {{ border-left-color: rgba(61, 245, 255, 0.55); "
                 "border-right-color: rgba(61, 245, 255, 0.55); border-bottom-color: rgba(61, 245, 255, 0.55); }"
                 # las fichas de la rejilla y las plantillas, de vidrio como las tarjetas; la elegida, en violeta
                 "#rejilla { font-size: 13px; } #rejilla::item { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                 "stop:0 rgba(255, 255, 255, 0.07), stop:1 rgba(255, 255, 255, 0.025)); border: 1px solid "
                 "rgba(255, 255, 255, 0.08); border-top-color: rgba(255, 255, 255, 0.16); border-radius: 8px; margin: 3px; "
                 "padding: 2px; }"
                 "#rejilla::item:selected { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                 "stop:0 rgba(150, 125, 255, 0.42), stop:1 rgba(124, 92, 255, 0.20)); border: 1px solid "
                 "rgba(150, 125, 255, 0.70); border-top-color: rgba(225, 215, 255, 0.75); color: #FFFFFF; }"
                 "#plantilla { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.07), "
                 "stop:1 rgba(255, 255, 255, 0.025)); border: 1px solid rgba(255, 255, 255, 0.08); "
                 "border-top-color: rgba(255, 255, 255, 0.16); border-radius: 10px; }"
                 "#plantilla_nombre { font-weight: 700; color: #FFFFFF; }"
                 "QSlider::sub-page:horizontal:disabled { background: #3C3C48; }"  # sin clip elegido se ve apagado
                 "QSlider::handle:horizontal:disabled { background: #5A5A66; } #secundario:disabled { color: #5A5A66; }"
                 # los paneles que se desplazan van dentro de la tarjeta: sin esto saldrían con el fondo de la página
                 "#desplazable, #desplazable > QWidget > QWidget { background: transparent; }")
VIOLETA = "#D2C6FF"  # la herramienta elegida: violeta claro, que se lea sobre su pastilla de vidrio violeta
AJUSTES = {"brillo": (-100, 100), "contraste": (-100, 100), "saturacion": (-100, 100), "temperatura": (-100, 100),
           "vineta": (0, 100), "nitidez": (0, 100)}  # campo del clip: (mínimo, máximo); «Restablecer» los pone a 0


def carpeta_videos() -> Path:
    """Videos del usuario / Ráfaga Studio: lo exportado queda con sus videos, no escondido dentro de la app."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)) / "Ráfaga Studio"


def destino_libre(nombre_video: str) -> Path:
    """<Videos>/Ráfaga Studio/<nombre>.mp4 sin pisar otro: «<nombre> (2).mp4»…"""
    limpio = re.sub(r'[\\/:*?"<>|\s]+', " ", nombre_video).strip(" .")[:80] or "video"
    if limpio.split(".")[0].lower() in diseno._RESERVADOS:  # «CON.mp4» Windows lo abre como la consola
        limpio = f"video {limpio}"
    destino, n = carpeta_videos() / f"{limpio}.mp4", 1
    while destino.exists():
        n += 1
        destino = destino.with_name(f"{limpio} ({n}).mp4")
    return destino


def _medir(rutas, aviso, audio=False):
    """En un hilo: valida y mide cada archivo con edicion.anadir_medio (ffmpeg), sin tocar el proyecto abierto (se
    sigue editando mientras); la página añade lo que entró al terminar. audio=True: todo como pista de audio."""
    nuevos, errores = [], []
    for n, ruta in enumerate(rutas):
        aviso(t("Importando {n} de {total}…", n=n + 1, total=len(rutas)), n / len(rutas))
        try:
            q = edicion.anadir_medio(edicion.nuevo(), ruta, audio)
        except ValueError as e:
            errores.append(str(e))
            continue
        nuevos.append(["clips", q["clips"][0]] if q["clips"] else ["audios", q["audios"][0]])
    return {"nuevos": nuevos, "errores": errores}


def _leer_foto(ruta, carpeta, aviso):
    """En un hilo: copia la foto a imagenes/ y la lee (una de 50 MP tarda más de un segundo); el lienzo la encuentra
    luego ya leída en la caché de diseno._leer_imagen."""
    archivo = diseno.importar_imagen(ruta, carpeta)
    imagen = diseno._imagen(carpeta, archivo)
    if imagen is None:
        raise ValueError(t("No se pudo leer la imagen."))
    return {"archivo": archivo, "ancho": imagen.width(), "alto": imagen.height()}  # ya girada según el EXIF


def _abrir(carpeta, aviso):
    """En un hilo: el proyecto validado (puede venir de otro PC) y sus fotos ya leídas en la caché."""
    proyecto = edicion.abrir(Path(carpeta))
    diseno._leer_imagen.cache_clear()  # las del proyecto anterior no se quedan en memoria
    for c in proyecto["capas"]:
        if c["tipo"] == "imagen":
            diseno._imagen(Path(carpeta), c["archivo"])
    return {"proyecto": proyecto}


def _musica(proyecto) -> list[dict]:
    """[la primera pista de música] (la que marca el ritmo de los efectos «al ritmo»), o [] si no hay."""
    return [a for a in proyecto["audios"] if a["tipo"] == "musica"][:1]


def _color_marca() -> str:
    """El primer color de tu marca (Diseño → Mi marca) para el borde de tu cámara; sin colores, el violeta de Ráfaga."""
    try:
        return diseno.color((marca.cargar().get("colores") or [edicion.BORDE])[0])
    except (ValueError, OSError, AttributeError):
        return edicion.BORDE


class ItemVideo(diseno.ItemCapa):
    """Una capa de video (tu cara) en el lienzo: su fotograma en el cursor (`imagen`, lo pide la página) dentro de su
    forma y con su borde, pintado como en el video montado (edicion.pintar_video). Se mueve y cambia de tamaño como las
    demás capas (pd.Lienzo)."""
    def __init__(self, capa, carpeta):
        self.imagen = None
        super().__init__(capa, carpeta)

    def aplicar(self, capa):
        self.prepareGeometryChange()
        self._capa = dict(capa)
        self.setData(0, capa["id"])
        self.setPos(capa["x"], capa["y"])
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, self._capa["ancho"], self._capa["alto"])

    def paint(self, p, opcion=None, widget=None):
        edicion.pintar_video(p, self._capa, self.boundingRect(), self.imagen)


def _propiedades() -> dict:
    """Los campos de Propiedades por grupo: (texto de la fila, [(campo, tipo de control, *datos)])."""
    def numero(campo, minimo, maximo, sufijo="", factor=1, decimales=0):
        return campo, "num", minimo, maximo, sufijo, factor, decimales
    return {
        "proyecto": [(t("Nombre"), [("nombre", "linea")]), (t("Formato"), [("formato", "opc", NOMBRES_FORMATO)]),
                     (t("Encaje"), [("ajuste", "opc", {"recortar": t("Recortar para llenar"),
                                                       "difuminar": t("Entero, con fondo borroso")})]),
                     (t("Fotogramas"), [("fps", "opc", {f: t("{n} por segundo", n=f) for f in edicion.FPS})]),
                     (t("Fondo"), [("fondo", "color")])],
        "clips": [(t("Velocidad"), [numero("velocidad", 0.25, 4, " ×", 1, 2)]),
                  (t("Volumen"), [numero("volumen", 0, 2, " %", 100), ("silencio", "si", t("Silenciar"))]),
                  (t("Filtro"), [("filtro", "opc", edicion.FILTROS)]), (t("Brillo"), [numero("brillo", -100, 100)]),
                  (t("Contraste"), [numero("contraste", -100, 100)]),
                  (t("Saturación"), [numero("saturacion", -100, 100)]),
                  (t("Movimiento"), [("movimiento", "opc", edicion.MOVIMIENTOS)]),
                  (t("Transición"), [("transicion", "opc", edicion.TRANSICIONES)]),
                  (t("Dura"), [numero("duracion_transicion", 0.2, 2, " s", 1, 1)])],
        "capas": [(t("Posición"), [numero("x", -pd.LIMITE, pd.LIMITE), numero("y", -pd.LIMITE, pd.LIMITE)]),
                  (t("Tamaño"), [numero("ancho", 1, 20000), numero("alto", 1, 20000)]),
                  (t("Forma"), [("forma", "opc", edicion.FORMAS_VIDEO)]),  # las de las capas de video (tu cara)
                  (t("Borde"), [("borde", "color"), numero("grosor_borde", 0, 200, " px")]),
                  (t("Volumen"), [numero("volumen", 0, 2, " %", 100), ("silencio", "si", t("Silenciar"))]),
                  (t("Giro"), [numero("rotacion", -360, 360, "°"), numero("opacidad", 0, 1, " %", 100)]),
                  (t("Texto"), [("texto", "texto")]),
                  (t("Fuente"), [("fuente", "opc", pd.fuentes())]),
                  (t("Letra"), [numero("tamano", 1, 2000, " px")]), (t("Color"), [("color", "color")]),
                  (t("Estilo"), [("negrita", "si", t("Negrita")), ("cursiva", "si", t("Cursiva")),
                                 ("sombra", "si", t("Sombra"))]),
                  (t("Alineación"), [("alineacion", "opc", {"izquierda": t("Izquierda"), "centro": t("Centro"),
                                                            "derecha": t("Derecha")})]),
                  (t("Contorno"), [("contorno", "color"), numero("grosor_contorno", 0, 200, " px")]),
                  (t("Ajuste"), [("ajuste", "opc", {"cubrir": t("Cubrir la caja"), "contener": t("Imagen entera")})]),
                  (t("Esquinas"), [numero("redondeo", 0, 10000, " px")]),
                  (t("Aparece en"), [numero("inicio", 0, edicion.MAX_DURACION, " s", 1, 2)]),
                  (t("Dura"), [numero("duracion", edicion.MIN_CLIP, edicion.MAX_DURACION, " s", 1, 2)]),
                  (t("Entrada"), [("entrada", "opc", edicion.ENTRADAS)]),
                  (t("Salida"), [("salida", "opc", edicion.SALIDAS)])],
        "audios": [(t("Tipo"), [("tipo", "opc", edicion.TIPOS_AUDIO)]),
                   (t("Volumen"), [numero("volumen", 0, 2, " %", 100)]),
                   (t("Fundido de entrada"), [numero("entrada", 0, 10, " s", 1, 1)]),
                   (t("Fundido de salida"), [numero("salida", 0, 10, " s", 1, 1)])],
    }


class Vista(pd.Lienzo):
    """El lienzo del editor de diseño (mover y asas) con el fotograma del video debajo; soltar archivos los importa."""
    def __init__(self, pagina):
        super().__init__(pagina)
        self.setMinimumSize(300, 240)

    def dropEvent(self, e):
        # \\servidor\… también es «local» para Qt: lo para seguro.archivo_medio al medirlo
        self.pagina.importar([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        e.acceptProposedAction()


class PaginaEdicion(QWidget):
    def __init__(self):
        super().__init__()
        diseno.asegurar_qt()  # las fuentes incluidas, antes de llenar la lista de fuentes
        self.proyecto, self.carpeta, self.sel, self.cursor = edicion.nuevo(), None, "", 0.0
        self.deshacer_pila, self.rehacer_pila, self._ultima, self.sucio, self._cargando = [], [], None, False, False
        self.tareas, self._previa, self._exportado, self._fuente_foto = set(), None, None, None
        self._siguiente = None  # grabando: (proyecto, desde, archivo) del trozo de video que va detrás del que suena
        self._sin_guardar = set()  # carpetas de videos descartados sin guardar: _limpiar las borra
        self._foto_en_curso = self._foto_pendiente = False
        self._fotos_pip, self._pips_pedidos = {}, set()  # fotogramas de las capas de video: hechos y pedidos al hilo
        self.setAcceptDrops(True)
        self.setStyleSheet(ESTILO_PAGINA)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)
        lay.addWidget(etiqueta(t("Editor de video"), "titulo"))
        lay.addLayout(self._barra())
        arriba = QWidget()
        col = QVBoxLayout(arriba)
        col.setContentsMargins(0, 0, 0, 0)
        herramientas, panel = self._herramientas()
        fila = QHBoxLayout()
        fila.addWidget(panel)
        fila.addWidget(self._centro(), 1)
        fila.addWidget(self._panel_propiedades())
        col.addWidget(herramientas)
        col.addLayout(fila, 1)
        partes = QSplitter(Qt.Vertical)
        partes.addWidget(arriba)
        partes.addWidget(self._linea())
        partes.setStretchFactor(0, 3)
        partes.setStretchFactor(1, 2)
        lay.addWidget(partes, 1)
        for tecla, accion in ((QKeySequence.Undo, self.deshacer), (QKeySequence.Redo, self.rehacer),
                              (QKeySequence.Delete, self._suprimir)):
            atajo = QShortcut(tecla, self)
            atajo.setContext(Qt.WidgetWithChildrenShortcut)  # solo con esta página delante
            atajo.activated.connect(accion)
        self.hilo = Hilo()
        self.hilo.hecho.connect(self._foto_lista)
        self._espera = QTimer(self)  # al arrastrar el cursor, un fotograma cuando se para un momento, no uno por píxel
        self._espera.setSingleShot(True)
        self._espera.setInterval(120)
        self._espera.timeout.connect(self._pedir_fotograma)
        self._ir_pestana(0)
        self._refrescar()
        self._limpiar()  # lo que quedó a medio borrar al cerrar la última vez

    # ---------- Construcción ----------

    def _barra(self):
        nuevo, abrir, guardar = boton(f"📄  {t('Nuevo')}"), boton(f"📂  {t('Abrir')}"), boton(f"💾  {t('Guardar')}")
        nuevo.clicked.connect(lambda: self._descartar_ok() and self._empezar(edicion.nuevo(), None))
        abrir.clicked.connect(self.pedir_abrir)
        guardar.clicked.connect(self.guardar)
        self.deshacer_btn, self.rehacer_btn = boton("↶"), boton("↷")  # solo el icono: la barra cabe en 1280 px
        self.deshacer_btn.setToolTip(t("Deshacer (Ctrl+Z)"))
        self.rehacer_btn.setToolTip(t("Rehacer (Ctrl+Y)"))
        self.deshacer_btn.clicked.connect(self.deshacer)
        self.rehacer_btn.clicked.connect(self.rehacer)
        self.estado = etiqueta("", "sub")
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.setFixedWidth(120)
        self.progreso.hide()
        self._ultimo_aviso = ""
        self.calidad = QComboBox()
        self.calidad.setToolTip(t("Calidad al exportar: 720p pesa menos"))
        self.calidad.addItem("1080p", "1080p")
        self.calidad.addItem("720p", "720p")
        self.exportar_btn, carpeta = boton(f"⬇  {t('Exportar')}", "principal"), boton("📁")
        carpeta.setToolTip(t("Abrir la carpeta de lo exportado"))
        self.exportar_btn.clicked.connect(self.exportar)
        carpeta.clicked.connect(self.abrir_carpeta)
        fila = QHBoxLayout()
        for w in (nuevo, abrir, guardar, self.deshacer_btn, self.rehacer_btn, self.estado, self.progreso, self.calidad,
                  self.exportar_btn, carpeta):
            fila.addWidget(w, 1 if w is self.estado else 0)
        return fila

    def _herramientas(self):
        """(barra, panel): la barra de herramientas como en CapCut (icono encima, nombre debajo; la elegida en violeta)
        y la tarjeta de la izquierda con el panel de la herramienta elegida."""
        caja, lay = tarjeta()
        lay.setContentsMargins(10, 10, 10, 10)
        caja.setFixedWidth(290)
        barra = QWidget()
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(2)
        self.pestanas, self.paneles, self.listas, self.deslizadores = QButtonGroup(self), QStackedWidget(), {}, {}
        self.herramientas = {}
        for i, (clave, nombre_icono, texto, panel) in enumerate((
                ("medios", "folder-open", t("Medios"), self._panel_medios()),
                ("audio", "music", t("Audio"), self._desplazable(self._panel_audio())),
                ("grabarte", "video", t("Grabarte"), self._desplazable(self._panel_grabarte())),
                ("texto", "type", t("Texto"), self._panel_texto()),
                ("stickers", "sticker", t("Stickers"), self._panel_stickers()),
                ("efectos", "wand-sparkles", t("Efectos"), self._panel_lista(
                    edicion.EFECTOS, "efecto", self._deslizador("intensidad", t("Intensidad"), 0, 100))),
                ("transiciones", "blend", t("Transiciones"), self._panel_lista(edicion.TRANSICIONES, "transicion")),
                ("subtitulos", "captions", t("Subtítulos"), self._desplazable(self._panel_subtitulos())),
                ("filtros", "aperture", t("Filtros"), self._panel_lista(edicion.FILTROS, "filtro")),
                ("ajustes", "sliders-horizontal", t("Ajustes"), self._desplazable(self._panel_ajustes())),
                ("plantillas", "layout-template", t("Plantillas"), self._desplazable(self._panel_plantillas())),
                ("avatar", "scan-face", t("Avatar IA"), self._panel_avatar()))):
            b = self.herramientas[clave] = QToolButton()
            b.setText(texto)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            icono = QIcon()  # gris y, la elegida, violeta
            icono.addPixmap(iconos.icono(nombre_icono, "#B4B4C0").pixmap(48, 48), QIcon.Normal, QIcon.Off)
            icono.addPixmap(iconos.icono(nombre_icono, VIOLETA).pixmap(48, 48), QIcon.Normal, QIcon.On)
            b.setIcon(icono)
            b.setIconSize(QSize(22, 22))
            b.setObjectName("herramienta")
            b.setCheckable(True)
            b.setMinimumWidth(62)
            b.setCursor(Qt.PointingHandCursor)
            self.pestanas.addButton(b, i)
            fila.addWidget(b)
            self.paneles.addWidget(panel)
        fila.addStretch()
        self.pestanas.idClicked.connect(self._ir_pestana)
        self.titulo_pestana = etiqueta("", "sub")
        lay.addWidget(self.titulo_pestana)
        lay.addWidget(self.paneles, 1)
        return barra, caja

    @staticmethod
    def _panel(*widgets, estirar=True):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            lay.addWidget(w)
        if estirar:
            lay.addStretch()
        return panel

    @staticmethod
    def _desplazable(panel):
        """El panel con barra de desplazamiento: si la ventana es baja, lo de abajo no queda cortado."""
        caja = QScrollArea()
        caja.setObjectName("desplazable")
        caja.setWidgetResizable(True)
        caja.setFrameShape(QFrame.NoFrame)
        caja.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        caja.setWidget(panel)
        return caja

    def _deslizador(self, campo, texto, minimo, maximo):
        """«Nombre ··· valor» y su deslizador, que cambia ese campo del clip elegido (arrastrarlo es un solo
        «deshacer»: _cambiar junta los cambios seguidos del mismo campo)."""
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(2)
        arriba, valor = QHBoxLayout(), etiqueta("", "sub")
        valor.setWordWrap(False)
        arriba.addWidget(etiqueta(texto), 1)
        arriba.addWidget(valor)
        d = self.deslizadores[campo] = QSlider(Qt.Horizontal)
        d.setRange(minimo, maximo)
        d.valueChanged.connect(lambda v: (valor.setText(str(v)), self._cambiar(campo, **{campo: v})))
        valor.setText(str(d.value()))
        lay.addLayout(arriba)
        lay.addWidget(d)
        return caja

    def _panel_medios(self):
        importar, foto = boton(f"➕  {t('Importar')}"), boton(f"🖼️  {t('Foto encima del video')}")
        importar.setToolTip(t("Videos, fotos y música de tu PC: van al final de la línea de tiempo"))
        importar.clicked.connect(lambda: self.importar(QFileDialog.getOpenFileNames(
            self, t("Importar"), QStandardPaths.writableLocation(QStandardPaths.MoviesLocation), FILTRO_MEDIOS)[0]))
        foto.clicked.connect(lambda: (ruta := QFileDialog.getOpenFileName(
            self, t("Foto encima del video"), QStandardPaths.writableLocation(QStandardPaths.PicturesLocation),
            pd.FILTRO_IMAGENES)[0]) and self.anadir_imagen(ruta))
        return self._panel(importar, foto, etiqueta(t(
            "También puedes arrastrar videos, fotos y música aquí o a la vista previa. Los videos no se copian: "
            "no los muevas de carpeta mientras los uses."), "sub"))

    def _panel_texto(self):
        self.textos = QListWidget()
        for texto in ESTILOS_TEXTO:  # se ve traducido; la clave va en el dato
            self.textos.addItem(pd._elemento(t(texto), texto))
        self.textos.itemClicked.connect(lambda item: self.anadir_texto(ESTILOS_TEXTO[item.data(Qt.UserRole)]))
        return self._panel(etiqueta(t("Elige un estilo: el texto aparece en el cursor."), "sub"), self.textos,
                           estirar=False)

    def _panel_stickers(self):
        self.buscar_sticker = QLineEdit()
        self.buscar_sticker.setPlaceholderText(t("Buscar en inglés: fire, heart, star…"))
        self.buscar_sticker.textChanged.connect(lambda t: self._llenar_stickers(t.strip()))
        self.stickers = QListWidget()
        self.stickers.setViewMode(QListView.IconMode)
        self.stickers.setResizeMode(QListView.Adjust)
        self.stickers.setMovement(QListView.Static)
        self.stickers.setIconSize(QSize(36, 36))
        self.stickers.setGridSize(QSize(52, 52))
        self.stickers.itemClicked.connect(self.anadir_sticker)
        return self._panel(self.buscar_sticker, self.stickers, estirar=False)

    def _panel_audio(self):
        musica = boton(f"➕  {t('Importar música o sonido')}")
        musica.clicked.connect(lambda: self.importar(QFileDialog.getOpenFileNames(  # un .mp4 o .webm aquí es sonido
            self, t("Importar audio"), QStandardPaths.writableLocation(QStandardPaths.MusicLocation),
            FILTRO_AUDIOS)[0], audio=True))
        self.texto_voz = QTextEdit()
        self.texto_voz.setAcceptRichText(False)
        self.texto_voz.setPlaceholderText(t("Escribe lo que dirá la voz…"))
        self.texto_voz.setFixedHeight(90)
        self.voz = SelectorVoz()
        self.voz_btn = boton(f"🎙️  {t('Voz IA')}")
        self.voz_btn.clicked.connect(self.voz_ia)
        fila, self.bajar_musica = casilla(t("Bajar la música cuando hablas"))
        fila.setToolTip(t("Mientras suena una voz (tu grabación o una voz IA), la música baja sola y luego vuelve"))
        self.bajar_musica.toggled.connect(self.poner_bajar_musica)
        return self._panel(musica, etiqueta(t("Voz IA: se añade en el cursor."), "sub"), self.texto_voz, self.voz,
                           self.voz_btn, fila)

    def _panel_grabarte(self):
        self.grabarte = PanelGrabarte(self)
        return self.grabarte

    def _panel_lista(self, opciones: dict, campo: str, *debajo):
        """Las opciones de un campo del clip (filtro, efecto o transición) que se aplican al clip elegido. Filtros y
        efectos van en cuadrícula, como botones con su nombre; las transiciones, en lista. `debajo`: más controles."""
        lista = self.listas[campo] = QListWidget()
        if campo != "transicion":
            lista.setObjectName("rejilla")
            lista.setViewMode(QListView.IconMode)
            lista.setResizeMode(QListView.Adjust)
            lista.setMovement(QListView.Static)
            lista.setWordWrap(True)  # «Temblor de cámara» en dos líneas, no cortado
            lista.setGridSize(QSize(118, 58))
        for clave, texto in opciones.items():
            item = pd._elemento(texto, clave)
            if campo != "transicion":
                item.setTextAlignment(Qt.AlignCenter)
                item.setSizeHint(QSize(110, 52))  # caben dos líneas
            lista.addItem(item)
        lista.itemClicked.connect(lambda item: self._a_clip(campo, item.data(Qt.UserRole)))
        ayuda = {"filtro": t("Elige un clip en la línea de tiempo y luego un filtro."),
                 "efecto": t("Elige un clip y luego un efecto. Los «al ritmo» siguen los golpes de la música (sin "
                             "música, 120 por minuto)."),
                 "transicion": t("Elige un clip: la transición va de ese clip al siguiente.")}[campo]
        return self._panel(etiqueta(ayuda, "sub"), lista, *debajo, estirar=False)

    def _panel_subtitulos(self):
        self.subs_btn = boton(f"✨  {t('Subtítulos automáticos')}", "principal")
        self.subs_btn.clicked.connect(self.subtitulos_automaticos)
        self.subs_estilo = QComboBox()
        for clave, texto in edicion.ESTILOS_SUBTITULOS.items():
            self.subs_estilo.addItem(texto, clave)
        self.subs_estilo.currentIndexChanged.connect(lambda _: self._cargando or self._poner_subtitulos(
            {**self.proyecto["subtitulos"], "estilo": self.subs_estilo.currentData()}))
        self.subs_activos = QCheckBox(t("Mostrar subtítulos en el video"))
        self.subs_activos.toggled.connect(lambda v: self._cargando or self._poner_subtitulos(
            {**self.proyecto["subtitulos"], "activos": v}))
        quitar = boton(t("Quitar subtítulos"))  # el estilo elegido se queda para los siguientes
        quitar.clicked.connect(lambda: self._poner_subtitulos({**self.proyecto["subtitulos"], "activos": False,
                                                               "palabras": []}))
        return self._panel(etiqueta(t("Escucha la voz del video y pone cada palabra en su momento. Con una clave de "
                                      "Groq u OpenAI es rápido; si no, se hace en tu PC (gratis, más lento)."), "sub"),
                           self.subs_btn, etiqueta(t("Estilo"), "sub"), self.subs_estilo, self.subs_activos, quitar)

    def _panel_ajustes(self):
        """Brillo, contraste, saturación, temperatura, viñeta y nitidez del clip elegido, y «Restablecer»."""
        nombres = {"brillo": t("Brillo"), "contraste": t("Contraste"), "saturacion": t("Saturación"),
                   "temperatura": t("Temperatura"), "vineta": t("Viñeta"), "nitidez": t("Nitidez")}
        self.restablecer = boton(t("Restablecer"))
        self.restablecer.setIcon(iconos.icono("rotate-ccw"))
        self.restablecer.setToolTip(t("Pone los ajustes del clip a 0"))
        self.restablecer.clicked.connect(lambda: self._cambiar("restablecer", **dict.fromkeys(AJUSTES, 0)))
        return self._panel(etiqueta(t("Elige un clip en la línea de tiempo y mueve los ajustes."), "sub"),
                           *(self._deslizador(campo, nombres[campo], *rango) for campo, rango in AJUSTES.items()),
                           self.restablecer)

    def _panel_plantillas(self):
        """Una tarjeta por plantilla de motor/edicion: su nombre, para qué sirve y «Aplicar»."""
        self.plantillas, tarjetas = {}, []
        for clave, plantilla in edicion.PLANTILLAS.items():
            caja = QFrame()
            caja.setObjectName("plantilla")
            lay = QVBoxLayout(caja)
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(4)
            aplicar = self.plantillas[clave] = boton(t("Aplicar"))
            aplicar.clicked.connect(lambda _=False, c=clave: self.aplicar_plantilla(c))
            for w in (etiqueta(plantilla["nombre"], "plantilla_nombre"), etiqueta(plantilla["descripcion"], "sub"),
                      aplicar):
                lay.addWidget(w)
            tarjetas.append(caja)
        return self._panel(etiqueta(t("Ponen en todo el video un filtro, un efecto, transiciones, el estilo de los "
                                      "subtítulos y un título. Tus videos y fotos no se tocan."), "sub"), *tarjetas)

    def _panel_avatar(self):
        """«Avatar IA», dicho con honestidad: todavía no está, y por qué."""
        crear = self.avatar_btn = boton(t("Crear mi avatar"))
        crear.setIcon(iconos.icono("scan-face", "#5A5A66"))
        crear.setEnabled(False)
        return self._panel(etiqueta(t("Próximamente: una foto tuya que habla con tu voz. Necesita una GPU en la nube "
                                      "(Modal o Hugging Face)."), "sub"), crear)

    def _centro(self):
        self.escena = QGraphicsScene(self)
        self.fondo = self.escena.addRect(QRectF(), Qt.NoPen, QColor("#000000"))
        self.foto = self.escena.addPixmap(QPixmap())
        self.foto.hide()
        self.vista = Vista(self)
        self.vista.setScene(self.escena)
        self.escena.selectionChanged.connect(self._al_elegir_en_vista)
        self.pantalla = QVideoWidget()
        self.player, self.sonido = QMediaPlayer(self), QAudioOutput(self)
        self.player.setAudioOutput(self.sonido)
        self.player.setVideoOutput(self.pantalla)
        self.player.positionChanged.connect(self._al_reproducir)
        self.player.mediaStatusChanged.connect(self._estado_video)
        self.centro = QStackedWidget()
        self.centro.addWidget(self.vista)
        self.centro.addWidget(self.pantalla)
        return self.centro

    def _panel_propiedades(self):
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 6, 0)
        self.titulo_props = etiqueta("", "sub")
        col.addWidget(self.titulo_props)
        self.reenlazar_btn = boton(f"🔗  {t('Volver a enlazar…')}", "principal")
        self.reenlazar_btn.setToolTip(t("No encuentro este archivo (se movió o se borró): dime dónde está ahora"))
        self.reenlazar_btn.clicked.connect(self.reenlazar)
        col.addWidget(self.reenlazar_btn)
        self.w, self.filas, self.grupos = {}, [], {}
        for grupo, filas in _propiedades().items():
            caja = QWidget()
            form = QFormLayout(caja)
            form.setContentsMargins(0, 0, 0, 0)
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)  # una fila que no cabe al lado de su nombre va debajo
            for texto, campos in filas:
                fila = QWidget()
                f = QHBoxLayout(fila)
                f.setContentsMargins(0, 0, 0, 0)
                for campo, *spec in campos:
                    f.addWidget(self._control(grupo, campo, *spec))
                form.addRow(texto, fila)
                self.filas.append((grupo, form, fila, [c for c, *_ in campos]))
            self.grupos[grupo] = caja
            col.addWidget(caja)
        col.addStretch()
        desplazable = QScrollArea()
        desplazable.setObjectName("desplazable")  # transparente, sobre la luz de ambiente como el resto de la página
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(panel)
        desplazable.setFixedWidth(340)  # cabe «9:16  TikTok · Shorts · Reels» junto a su nombre en todos los idiomas
        return desplazable

    def _control(self, grupo, campo, tipo, *datos):
        def cambiar(v):
            self._cambiar(campo, **{campo: v})
        if tipo == "num":
            minimo, maximo, sufijo, factor, decimales = datos
            w = QDoubleSpinBox()
            w.setRange(minimo * factor, maximo * factor)
            w.setDecimals(decimales)
            w.setSingleStep(1 if decimales == 0 else 0.1)
            w.setSuffix(sufijo)
            w.factor = factor  # volumen y opacidad se ven en %; en el proyecto van de 0 a 1 (o 2)
            w.valueChanged.connect(lambda v: cambiar(round(v / factor, 4)))
        elif tipo == "opc":
            w = QComboBox()
            # La lista de fuentes no pide el ancho de la más larga (no cabría en el panel); las demás sí, y si no caben
            # junto a su nombre, la fila pasa debajo (WrapLongRows): así su texto nunca sale cortado
            if len(datos[0]) > 20:
                w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                w.setMinimumContentsLength(8)
            for valor, texto in datos[0].items():
                w.addItem(texto, valor)
            w.currentIndexChanged.connect(lambda _: cambiar(w.currentData()))
        elif tipo == "si":
            w = QCheckBox(datos[0])
            w.toggled.connect(cambiar)
        elif tipo == "color":
            w = boton("")
            w.clicked.connect(lambda: (color := pd.pedir_color(self, self._seleccion()[1][campo])) and cambiar(color))
        elif tipo == "texto":
            w = QTextEdit()
            w.setAcceptRichText(False)  # pegar desde una web mete solo el texto
            w.setFixedHeight(64)
            w.textChanged.connect(lambda: cambiar(w.toPlainText()[:2000]))
        else:
            w = QLineEdit()
            w.setMaxLength(120)
            w.textEdited.connect(cambiar)
        self.w[(grupo, campo)] = w
        return w

    def _linea(self):
        caja, lay = tarjeta()
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        self.linea = LineaTiempo()
        self.linea.elegido.connect(self._elegir)
        self.linea.cursor_movido.connect(self._al_mover_cursor)
        self.linea.cambio.connect(self._aplicar)
        self.linea.aviso.connect(lambda t: self.estado.setText(f"⚠️ {t}"))
        fila = QHBoxLayout()
        for texto, ayuda, accion in ((f"✂️  {t('Dividir')}", t("Parte el clip en el cursor"), self.dividir),
                                     (f"🗑  {t('Borrar')}", t("Quita lo elegido (Supr)"), self.borrar),
                                     (f"📋  {t('Duplicar')}", t("Copia lo elegido justo detrás"), self.duplicar)):
            b = boton(texto)
            b.setToolTip(ayuda)
            b.clicked.connect(accion)
            fila.addWidget(b)
        fila.addStretch()
        self.play_btn = boton("▶")
        self.play_btn.setToolTip(t("Reproducir la vista previa desde el cursor"))
        self.play_btn.clicked.connect(self.reproducir)
        self.reloj_txt = etiqueta("", "sub")
        self.reloj_txt.setWordWrap(False)
        for w in (self.play_btn, self.reloj_txt):
            fila.addWidget(w)
        fila.addStretch()
        lupa = QLabel()
        lupa.setPixmap(iconos.icono("zoom-in", "#8D8D9A").pixmap(18, 18))
        lupa.setToolTip(t("Zoom de la línea de tiempo"))
        fila.addWidget(lupa)
        fila.addWidget(self.linea.deslizador)
        self.scroll_linea = QScrollArea()
        self.scroll_linea.setWidgetResizable(True)
        self.scroll_linea.setFrameShape(QFrame.NoFrame)
        self.scroll_linea.setWidget(self.linea)
        self.scroll_linea.setMinimumHeight(170)
        lay.addLayout(fila)
        lay.addWidget(self.scroll_linea, 1)
        return caja

    # ---------- Estado y repintado ----------

    @property
    def diseno(self) -> dict:
        """El tamaño del video en píxeles (donde viven las capas): lo que lee pd.Lienzo para las asas."""
        ancho, alto = video.FORMATOS[self.proyecto["formato"]]
        return {"ancho": ancho, "alto": alto}

    def _seleccion(self) -> tuple[str, dict]:
        """(grupo, elemento) de lo elegido: "clips", "capas" o "audios"; si no hay nada, ("proyecto", proyecto)."""
        for grupo in ("clips", "capas", "audios"):
            for e in self.proyecto[grupo]:
                if e["id"] == self.sel:
                    return grupo, e
        return "proyecto", self.proyecto

    def _items(self):
        return [i for i in self.escena.items(Qt.AscendingOrder)
                if isinstance(i, diseno.ItemCapa) and i.data(0) is not None]

    def elegido(self):
        """(item, capa) de la capa elegida si se ve en el lienzo; si no, (None, None). Lo usa pd.Lienzo."""
        grupo, e = self._seleccion()
        item = next((i for i in self._items() if i.data(0) == self.sel), None) if grupo == "capas" else None
        return (item, e) if item else (None, None)

    def _refrescar(self):
        """Todo a la vista desde self.proyecto: línea de tiempo, lienzo, propiedades y (si cambió) el fotograma."""
        p = self.proyecto
        if self._seleccion()[0] == "proyecto":
            self.sel = ""  # lo elegido ya no existe (borrado, deshecho…)
        self.cursor = min(self.cursor, edicion.duracion_total(p))
        self.linea.seleccion, self.linea.cursor = self.sel, self.cursor
        self.linea.poner(p, self.carpeta)
        self._montar_vista()
        self._mostrar_propiedades()
        self.deshacer_btn.setEnabled(bool(self.deshacer_pila))
        self.rehacer_btn.setEnabled(bool(self.rehacer_pila))
        self._poner_reloj()
        fuente = (p["clips"], p["formato"], p["ajuste"], p["fondo"], p["fps"], _musica(p),  # lo que cambia el fotograma
                  [(c["inicio"], c["duracion"]) for c in p["capas"] if edicion.otra_mitad(p["formato"], c)])
        if fuente != self._fuente_foto:
            self._fuente_foto = fuente
            self._espera.start()

    def _poner_reloj(self):
        self.reloj_txt.setText(f"{reloj(self.cursor)} / {reloj(edicion.duracion_total(self.proyecto))}")

    def _montar_vista(self):
        """El lienzo al tamaño del video y las capas que se ven en el cursor, editables. Los items solo se rehacen si
        cambia qué capas se ven; si no, se les aplican los cambios."""
        ancho, alto = self.diseno["ancho"], self.diseno["alto"]
        caja = QRectF(0, 0, ancho, alto)
        if self.escena.sceneRect() != caja:
            self.escena.setSceneRect(caja)
            self.fondo.setRect(caja)
            self.foto.hide()  # era de otro formato
            self.vista.encajar()
        self.fondo.setBrush(QColor(self.proyecto["fondo"]))
        visibles, items = edicion.capas_en(self.proyecto, self.cursor), self._items()
        self.escena.blockSignals(True)  # rehacer items no es que el usuario elija otra cosa
        if [i.data(0) for i in items] == [c["id"] for c in visibles]:
            for item, capa in zip(items, visibles):
                item.aplicar(capa)
        else:
            for item in items:
                self.escena.removeItem(item)
            for capa in visibles:
                clase = ItemVideo if capa["tipo"] == "video" else diseno.ItemCapa
                item = clase(capa, self.carpeta or edicion.CARPETA)
                item.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
                self.escena.addItem(item)
        pedir = False
        for item in self._items():
            item.setSelected(item.data(0) == self.sel)
            if isinstance(item, ItemVideo):  # su fotograma en el cursor, si ya está hecho; si no, se pide
                clave = self._clave_pip(item._capa)
                item.imagen = self._fotos_pip.get(clave)
                hecho = clave in self._fotos_pip or clave in self._pips_pedidos
                pedir |= not hecho and not item._capa.get("falta")
                item.update()
        self.escena.blockSignals(False)
        self.vista.viewport().update()  # las asas
        if pedir:
            self._espera.start()

    def _mostrar_propiedades(self):
        grupo, e = self._seleccion()
        self._cargando = True
        self.titulo_props.setText({"proyecto": t("Propiedades · Proyecto"), "clips": t("Propiedades · Clip"),
                                   "capas": t("Propiedades · Capa"), "audios": t("Propiedades · Audio")}[grupo]
                                  + (f" · {nombre(grupo, e)}" if grupo != "proyecto" else ""))
        self.reenlazar_btn.setVisible(bool(e.get("falta")))
        video_elegido = grupo == "capas" and e["tipo"] == "video"
        # lo que dura una capa de video es su tramo: se cambia recortándola en la línea de tiempo
        ocultos = OCULTOS.get(e.get("tipo"), set()) if grupo == "clips" else {"duracion"} if video_elegido else set()
        if grupo == "clips" and e["transicion"] == "ninguna":
            ocultos = ocultos | {"duracion_transicion"}
        for g, caja in self.grupos.items():
            caja.setVisible(g == grupo)
        for g, form, fila, campos in self.filas:
            if g == grupo:
                form.setRowVisible(fila, any(c in e and c not in ocultos for c in campos))
        for (g, campo), w in self.w.items():
            if g != grupo:
                continue
            w.setVisible(campo in e and campo not in ocultos)
            if campo not in e:
                continue
            v = e[campo]
            if isinstance(w, QDoubleSpinBox):
                w.setValue(v * w.factor)
            elif isinstance(w, QCheckBox):
                w.setChecked(v)
            elif isinstance(w, QComboBox):
                if w.findData(v) < 0:  # una fuente que no está en este PC (el proyecto viene de otro)
                    w.addItem(str(v), v)
                w.setCurrentIndex(w.findData(v))
            elif isinstance(w, (QTextEdit, QLineEdit)):
                if (w.toPlainText() if isinstance(w, QTextEdit) else w.text()) != v:  # reponerlo movería el cursor
                    w.setPlainText(v) if isinstance(w, QTextEdit) else w.setText(v)
            else:
                pd._pintar_color(w, v)
        self._marcar_paneles(e if grupo == "clips" else None)
        self.grabarte.marcar(e if video_elegido else None, self.proyecto)
        self.bajar_musica.setChecked(self.proyecto["bajar_musica"])
        self._cargando = False

    def _marcar_paneles(self, clip):
        """Los paneles de la izquierda enseñan lo del clip elegido (filtro, efecto, transición y ajustes) y los
        subtítulos del proyecto. Sin clip, sus deslizadores se apagan. Va con _cargando puesto: no cambia nada."""
        for campo, lista in self.listas.items():
            claves = [lista.item(i).data(Qt.UserRole) for i in range(lista.count())]
            lista.setCurrentRow(claves.index(clip[campo]) if clip else -1)
            if not clip:
                lista.clearSelection()
        for campo, d in self.deslizadores.items():
            d.setEnabled(clip is not None)
            d.setValue(round((clip or edicion._CLIP)[campo]))
        self.restablecer.setEnabled(clip is not None)
        s = self.proyecto["subtitulos"]
        self.subs_activos.setChecked(s["activos"])
        self.subs_estilo.setCurrentIndex(self.subs_estilo.findData(s["estilo"]))

    # ---------- Elegir y cambiar ----------

    def _elegir(self, id_):
        self.sel = id_
        self.linea.seleccion = id_
        self.linea.update()
        self.escena.blockSignals(True)
        for item in self._items():
            item.setSelected(item.data(0) == id_)
        self.escena.blockSignals(False)
        self._mostrar_propiedades()
        self.vista.viewport().update()

    def _al_elegir_en_vista(self):
        ids = [i.data(0) for i in self.escena.selectedItems() if i.data(0) is not None]
        if ids:
            self._elegir(ids[0])
        elif self._seleccion()[0] == "capas":  # clic en el fondo del lienzo: suelta la capa
            self._elegir("")

    def _cambiar(self, clave, **campos):
        """Cambia lo elegido (o el proyecto si no hay nada elegido), validado. Cambios seguidos del mismo campo del
        mismo elemento, o del mismo gesto con un asa, son un solo «deshacer»."""
        if self._cargando:
            return
        grupo, e = self._seleccion()
        p = self.proyecto
        if grupo == "proyecto":
            nuevo = {**p, **campos}
        else:
            cambiado = {**e, **campos}
            if cambiado.get("grosor_contorno") and not cambiado.get("contorno"):
                cambiado["contorno"] = "#000000"  # con grosor y sin color no se vería nada
            nuevo = {**p, grupo: [cambiado if x is e else x for x in p[grupo]]}
        try:
            limpio = edicion.validar(nuevo)
        except ValueError as error:
            self._mostrar_propiedades()  # el campo vuelve a lo que de verdad tiene
            return self.estado.setText(f"⚠️ {error}")
        if limpio == p:
            return self._mostrar_propiedades()  # si se recortó a lo que ya tenía, el campo enseña el valor recortado
        self._aplicar(limpio, (self.sel, clave))
        if grupo == "capas" and e["tipo"] == "texto" and clave != "alto":
            self._crecer_texto(clave)

    def _crecer_texto(self, clave):
        """La caja de un texto crece con él: lo que sobresale no se vería ni se podría elegir."""
        item, capa = self.elegido()
        if item and item.texto:
            letras = round(item.texto.boundingRect().height() - 2 * item.texto.document().documentMargin())
            alto = min(letras, diseno.FACTOR_CAPA * self.diseno["alto"])
            if alto > capa["alto"]:
                self._cambiar(clave, alto=alto)

    def _a_clip(self, campo, valor):
        """Un filtro, un efecto o una transición de los paneles de la izquierda, al clip elegido."""
        grupo, e = self._seleccion()
        if grupo != "clips":
            self._mostrar_propiedades()  # el panel no se queda marcando lo que no se aplicó
            return mensaje(self, t("Elige un clip"), t("Haz clic en un clip de la línea de tiempo y vuelve a elegir."))
        if campo == "transicion" and e is self.proyecto["clips"][-1] and valor != "ninguna":
            self._mostrar_propiedades()
            return self.estado.setText(f"⚠️ {t('La transición va hacia el clip siguiente: el último no tiene.')}")
        self._cambiar(campo, **{campo: valor})

    def aplicar_plantilla(self, clave):
        """Una plantilla (motor/edicion.aplicar_plantilla) en todo el video, en un solo «deshacer»."""
        try:
            nuevo = edicion.aplicar_plantilla(self.proyecto, clave)
        except ValueError as e:
            return mensaje(self, t("No se pudo aplicar la plantilla"), e)
        self._aplicar(nuevo)

    def guardar_posiciones(self):
        """Tras arrastrar capas en el lienzo: su posición nueva, en un solo «deshacer». Lo llama pd.Lienzo."""
        pos = {i.data(0): i.pos() for i in self._items()}
        capas = [{**c, "x": max(-pd.LIMITE, min(pd.LIMITE, round(pos[c["id"]].x()))),
                  "y": max(-pd.LIMITE, min(pd.LIMITE, round(pos[c["id"]].y())))}
                 if c["id"] in pos and pos[c["id"]] != QPointF(c["x"], c["y"]) else c for c in self.proyecto["capas"]]
        if capas != self.proyecto["capas"]:
            self._operar(lambda p: edicion.validar({**p, "capas": capas}))

    def _aplicar(self, nuevo, clave=None):
        """Pone un proyecto nuevo (ya validado) guardando el anterior para deshacer, y lo repinta."""
        if nuevo == self.proyecto:
            return
        self._recordar(clave)
        self.proyecto = nuevo
        self._refrescar()

    def _operar(self, funcion, *args):
        """Una operación de motor/edicion sobre el proyecto; si no se puede, lo dice arriba sin tocar nada."""
        try:
            nuevo = funcion(self.proyecto, *args)
        except ValueError as e:
            self.estado.setText(f"⚠️ {e}")
            return self._montar_vista()  # p. ej. una capa arrastrada a un sitio imposible vuelve a su sitio
        self._aplicar(nuevo)
        return nuevo

    # ---------- Deshacer ----------

    def _recordar(self, clave=None):
        """Guarda el proyecto actual para deshacer (máx. 50). No hace falta copiarlo: nunca se cambia por dentro."""
        if clave is None or clave != self._ultima:
            self.deshacer_pila = (self.deshacer_pila + [self.proyecto])[-50:]
            self.rehacer_pila.clear()
        self._ultima, self.sucio = clave, True

    def deshacer(self):
        self._historial(self.deshacer_pila, self.rehacer_pila)

    def rehacer(self):
        self._historial(self.rehacer_pila, self.deshacer_pila)

    def _historial(self, desde, hacia):
        if desde:
            hacia.append(self.proyecto)
            self.proyecto, self._ultima, self.sucio = desde.pop(), None, True
            self._refrescar()

    # ---------- Línea de tiempo ----------

    def dividir(self):
        self._operar(edicion.dividir, self.cursor)

    def borrar(self):
        if self.sel:
            self._operar(edicion.borrar, self.sel)

    borrar_capa = borrar  # lo llama pd.Lienzo con Retroceso

    def _suprimir(self):
        if not isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit, QAbstractSpinBox)):  # ahí Supr borra letras
            self.borrar()

    def duplicar(self):
        """Una copia de lo elegido justo detrás: un clip, el siguiente; una capa o un audio, al acabar el original."""
        grupo, e = self._seleccion()
        if grupo == "proyecto":
            return
        lista = list(self.proyecto[grupo])
        i = next(k for k, x in enumerate(lista) if x is e)
        copia = {**e, "id": None}  # validar le da un id nuevo
        if grupo != "clips":
            copia["inicio"] = self.linea._base(grupo, i, e)[1]
        lista.insert(i + 1, copia)
        if self._operar(lambda p: edicion.validar({**p, grupo: lista})):
            self._elegir(self.proyecto[grupo][i + 1]["id"])

    def _al_mover_cursor(self, t):
        if self.grabarte.ocupado():  # un clic en la regla para el video: también la grabación, no solo la vista
            self.grabarte.detener()
        self.parar()
        self.cursor = t
        self.linea.poner_cursor(t)
        self._poner_reloj()
        self._montar_vista()
        self._espera.start()

    # ---------- Vista previa ----------

    def _clave_pip(self, capa) -> tuple:
        """Qué fotograma de su archivo enseña una capa de video en el cursor (el mismo que sale al montar)."""
        fps = self.proyecto["fps"]
        j = int((self.cursor - capa["inicio"]) * fps + 1e-3)
        return "pip", capa["archivo"], round(capa["desde"] + j / fps, 4), fps

    def _pedir_pips(self):
        """El fotograma en el cursor de cada capa de video que se ve, en el hilo (cada uno, una vez)."""
        r = render()
        if not hasattr(r, "fotograma_capa"):
            return  # se ve su forma en vidrio oscuro
        for capa in edicion.capas_en(self.proyecto, self.cursor):
            if capa["tipo"] == "video" and not capa.get("falta"):
                clave = self._clave_pip(capa)
                if clave not in self._fotos_pip and clave not in self._pips_pedidos:
                    self._pips_pedidos.add(clave)
                    self.hilo.pedir(clave, r.fotograma_capa, capa, self._carpeta(), self.cursor, self.proyecto["fps"])

    def _pedir_fotograma(self):
        """El fondo del video en el cursor, hecho en el hilo; uno a la vez y siempre el del último sitio pedido. Y el
        de las capas de video."""
        self._pedir_pips()
        r = render()
        if edicion.clip_en(self.proyecto, self.cursor) is None or not hasattr(r, "fotograma"):
            if r is None and self.proyecto["clips"]:
                self.estado.setText(t("La vista previa del video aún no está disponible en esta versión: se ven el "
                                      "fondo y las capas."))
            return self.foto.hide()  # donde no hay clip se ve el color de fondo
        if self._foto_en_curso:
            self._foto_pendiente = True
            return
        self._foto_en_curso = True
        # Sin capas (las pinta el lienzo, editables), voces ni subtítulos: el fotograma no los necesita. La música sí:
        # marca el ritmo de los efectos «al ritmo» (sin ella irían a 120 por minuto y no saldría lo que se exporta).
        # Las de video también: en «pantalla dividida» el fondo va a la otra mitad (render_edicion.fotograma)
        solo_clips = {**self.proyecto, "capas": [c for c in self.proyecto["capas"] if c["tipo"] == "video"],
                      "audios": _musica(self.proyecto),
                      "subtitulos": {"activos": False, "palabras": []}}
        self.hilo.pedir("foto", r.fotograma, solo_clips, self._carpeta(), self.cursor)

    def _foto_lista(self, clave, imagen):
        if isinstance(clave, tuple):  # el de una capa de video (None si falló: se queda en vidrio oscuro)
            self._pips_pedidos.discard(clave)
            self._fotos_pip[clave] = imagen if isinstance(imagen, QImage) and not imagen.isNull() else None
            while len(self._fotos_pip) > 24:  # los últimos: ir y volver con el cursor no los rehace
                del self._fotos_pip[next(iter(self._fotos_pip))]
            return self._montar_vista()
        self._foto_en_curso = False
        hecha = isinstance(imagen, QImage) and not imagen.isNull()
        if hecha:
            self.foto.setPixmap(QPixmap.fromImage(imagen))  # viene en baja resolución: se estira al lienzo
            self.foto.setTransform(QTransform.fromScale(self.diseno["ancho"] / imagen.width(),
                                                        self.diseno["alto"] / imagen.height()))
        self.foto.setVisible(hecha)  # si falló, mejor el fondo que el fotograma de otro sitio
        if self._foto_pendiente:
            self._foto_pendiente = False
            self._pedir_fotograma()

    def reproducir(self):
        """▶: la vista previa (baja resolución, con todo) de PREVIA segundos desde el cursor. Se rehace solo si el
        proyecto cambió o el cursor salió de ese trozo (pausar y seguir no la vuelve a montar)."""
        if self.grabarte.ocupado():  # grabándote, ⏸ es «Detener»: parar solo el video dejaría la grabación siguiendo
            return self.grabarte.detener()
        if self.centro.currentWidget() is self.pantalla:
            return self.parar()
        total = edicion.duracion_total(self.proyecto)
        if total == 0:
            return mensaje(self, t("Nada que reproducir"), t("Añade algún video, foto o audio."))
        if self.cursor >= total:  # en el final, otra vez desde el principio (y el reproductor también, desde 0)
            self.cursor = 0.0
            self.linea.poner_cursor(0.0)
        desde = self.cursor
        # con menos de 1 s por delante en el trozo hecho, mejor montar el siguiente
        if self._previa and self._previa[0] == self.proyecto and 0 <= desde - self._previa[1] < PREVIA - 1:
            return self._ver(self._previa[2], self._previa[1])
        r = render()
        if not hasattr(r, "vista_previa"):
            return mensaje_error(self, t("Aún no disponible"), AUN_NO)
        proyecto = self.proyecto
        self.estado.setText(t("Preparando vista previa…"))
        self._trabajo(lambda aviso, **k: {"archivo": str(r.vista_previa(aviso=aviso, **k))},
                      lambda res: self._previa_lista(proyecto, desde, res["archivo"]), self.play_btn,
                      proyecto=proyecto, carpeta=self._carpeta(), desde=desde, segundos=PREVIA)

    def _previa_lista(self, proyecto, desde, archivo):
        self._previa = (proyecto, desde, archivo)
        self._ver(archivo, desde)

    def _ver(self, archivo, base):
        """Reproduce la vista previa que empieza en el segundo `base` de la línea de tiempo, desde el cursor."""
        self.estado.setText("")
        self.centro.setCurrentWidget(self.pantalla)
        self._base, self._desde = base, int(max(0, self.cursor - base) * 1000)
        if self.player.source() != QUrl.fromLocalFile(archivo):  # ya abierto (precargar, pausa y seguir): no otra vez
            self.player.setSource(QUrl.fromLocalFile(archivo))
        self.player.play()
        if self.player.position() != self._desde:  # si ya estaba cargado; si no, al cargarse (_estado_video)
            self.player.setPosition(self._desde)
        iconos.poner(self.play_btn, "⏸")

    def precargar(self, archivo):
        """Durante la cuenta atrás: el video que sonará al grabar, abierto y quieto en su principio. Así, cuando empieza
        la grabación, solo falta play() (abrirlo entonces retrasaba el video unas décimas respecto a tu voz)."""
        self.player.setSource(QUrl.fromLocalFile(archivo))
        self.player.pause()
        self.player.setPosition(0)

    def _estado_video(self, estado):
        if estado == QMediaPlayer.LoadedMedia and self.centro.currentWidget() is self.pantalla:
            self.player.setPosition(self._desde)
        elif estado == QMediaPlayer.EndOfMedia:
            sig = self._siguiente if self.grabarte.estado == "grabando" else None
            if sig and sig[0] == self.proyecto and abs(sig[1] - self._base - PREVIA) < 1e-6:
                self.cursor, self._previa = sig[1], sig  # grabando: el trozo siguiente del video, ya montado
                self._ver(sig[2], sig[1])
                return self._siguiente_tramo(sig[1] + PREVIA)
            # ponytail: si el trozo siguiente no llegó a tiempo, la vista se queda quieta y la grabación sigue; al
            # empezar cada trozo el video puede pararse unas décimas (no se vuelve a cuadrar con tu voz)
            self.parar()

    def parar(self):
        if self.centro.currentWidget() is self.vista:
            return
        self.player.pause()
        self.centro.setCurrentWidget(self.vista)
        iconos.poner(self.play_btn, "▶")
        self._montar_vista()
        self._espera.start()

    def _al_reproducir(self, ms):
        if self.centro.currentWidget() is self.pantalla:  # el cursor avanza con el video
            self.cursor = min(self._base + ms / 1000, edicion.duracion_total(self.proyecto))
            self.linea.poner_cursor(self.cursor)
            self._poner_reloj()
            self.scroll_linea.ensureVisible(int(self.linea.x_de(self.cursor)), 0, 80, 0)

    # ---------- Añadir ----------

    def importar(self, rutas, tipo_audio="musica", audio=False):
        """Videos y fotos, al final de la pista principal; audios (o todo, con audio=True), en el cursor. Se validan y
        miden en un hilo."""
        rutas = [str(r) for r in rutas if str(r).strip()][:edicion.MAX_CLIPS]
        if rutas:
            self._trabajo(_medir, lambda r: self._importados(r, tipo_audio), rutas=rutas, audio=audio)

    def _importados(self, resultado, tipo_audio):
        if resultado["errores"]:
            mensaje_error(self, t("Algunos archivos no entraron"), "\n\n".join(resultado["errores"][:5]))
        nuevos = resultado["nuevos"]
        if not nuevos:
            return
        p = self.proyecto
        clips = [{**e, "id": None} for clave, e in nuevos if clave == "clips"]  # validar les da ids nuevos
        audios = [{**e, "id": None, "tipo": tipo_audio, "inicio": round(self.cursor, 3)}
                  for clave, e in nuevos if clave == "audios"]
        try:
            limpio = edicion.validar({**p, "clips": p["clips"] + clips, "audios": p["audios"] + audios})
        except ValueError as e:
            return mensaje_error(self, t("No se pudo añadir"), e)
        self._carpeta()  # la caché de miniaturas, ondas y vista previa va dentro
        self._aplicar(limpio)
        self._elegir((limpio["clips"] if clips else limpio["audios"])[-1]["id"])

    def anadir_capa(self, capa):
        """Una capa nueva en el cursor, de 3 s, encima de todas y elegida."""
        p = self.proyecto
        if len(p["capas"]) >= edicion.MAX_CAPAS:
            return mensaje(self, t("Demasiadas capas"), t("Un video puede tener hasta {n} capas.", n=edicion.MAX_CAPAS))
        try:  # validar el proyecto entero también le da a la capa un id que no choca con otro
            limpio = edicion.validar({**p, "capas": p["capas"] + [{"inicio": round(self.cursor, 3), "duracion": 3,
                                                                   **capa}]})
        except ValueError as e:
            return mensaje_error(self, t("No se pudo añadir"), e)
        self._aplicar(limpio)
        self._elegir(limpio["capas"][-1]["id"])

    def _caja(self, ancho, alto):
        """Caja de ese tamaño centrada en el video."""
        return {"x": round((self.diseno["ancho"] - ancho) / 2), "y": round((self.diseno["alto"] - alto) / 2),
                "ancho": round(ancho), "alto": round(alto)}

    def _lado(self):
        return min(self.diseno["ancho"], self.diseno["alto"])

    def anadir_texto(self, estilo: dict):
        tamano = round(self._lado() / 12 * estilo.get("escala", 1))
        self.anadir_capa({"tipo": "texto", "texto": t("Escribe aquí"),
                          **self._caja(self.diseno["ancho"] * 0.8, tamano * 1.8),
                          "tamano": tamano, "fuente": marca.cargar()["fuente_titulo"], "negrita": True,
                          "alineacion": "centro", "color": "#FFFFFF",
                          **{k: v for k, v in estilo.items() if k != "escala"}})

    def anadir_sticker(self, item):
        lado, valor = self._lado() / 4, item.data(Qt.UserRole)
        if item.data(Qt.UserRole + 1) == "icono":
            self.anadir_capa({"tipo": "icono", "nombre": valor, "color": "#FFFFFF", **self._caja(lado, lado)})
        else:
            self.anadir_capa({"tipo": "emoji", "texto": valor, **self._caja(lado, lado)})

    def anadir_imagen(self, ruta):
        """Una foto como capa encima del video (copiada a imagenes/ del proyecto, como en el editor de diseño). Se copia
        y se lee en el hilo: leer una foto grande congelaba la ventana."""
        real = archivo_valido(self, ruta, seguro.IMAGENES, t("imagen"))
        if real:
            carpeta = self._carpeta()
            # si mientras tanto se abrió otro video, la foto no es suya
            self._trabajo(_leer_foto, lambda r: carpeta == self.carpeta and self._foto_importada(r),
                          ruta=str(real), carpeta=carpeta)

    def _foto_importada(self, r):
        escala = min(self.diseno["ancho"] * 0.6 / r["ancho"], self.diseno["alto"] * 0.6 / r["alto"])  # sin deformar
        self.anadir_capa({"tipo": "imagen", "archivo": r["archivo"], **self._caja(max(1, r["ancho"] * escala),
                                                                                 max(1, r["alto"] * escala))})

    def _llenar_stickers(self, texto=""):
        self.stickers.clear()
        for tipo, elementos in (("emoji", pd.emojis(texto)), ("icono", pd.iconos(texto))):
            for item in elementos:
                item.setData(Qt.UserRole + 1, tipo)
                if tipo == "icono":  # el nombre en inglés no cabe bajo el dibujo: va de ayuda al pasar el ratón
                    item.setToolTip(item.text())
                    item.setText("")
                self.stickers.addItem(item)

    def _ir_pestana(self, i):
        if not self.paneles.widget(i).isAncestorOf(self.grabarte):
            self.grabarte.apagar()  # fuera de «Grabarte», la cámara y el micrófono se apagan (y lo grabado se guarda)
        self.pestanas.button(i).setChecked(True)
        self.paneles.setCurrentIndex(i)
        self.titulo_pestana.setText(self.pestanas.button(i).text())
        if self.paneles.currentWidget().isAncestorOf(self.stickers) and not self.stickers.count():
            self._llenar_stickers()  # al abrirla y no al arrancar: dibujar 120 iconos tarda

    def voz_ia(self):
        texto = self.texto_voz.toPlainText().strip()
        if not texto:
            return mensaje(self, t("Falta el texto"), t("Escribe lo que dirá la voz."))
        r = render()
        if not hasattr(r, "voz_ia"):
            return mensaje_error(self, t("Aún no disponible"), AUN_NO)
        self._trabajo(lambda aviso, **k: _medir([str(r.voz_ia(**k))], aviso),
                      lambda res: self._importados(res, "voz"), self.voz_btn,
                      texto=texto[:5000], voz=self.voz.currentData(), carpeta=self._carpeta())

    # ---------- Subtítulos ----------

    def subtitulos_automaticos(self):
        r = render()
        if not hasattr(r, "subtitulos_automaticos"):
            return mensaje_error(self, t("Aún no disponible"), AUN_NO)
        if not self.proyecto["clips"] and not self.proyecto["audios"]:
            return mensaje(self, t("Falta la voz"), t("Añade un video o un audio con voz primero."))
        self._trabajo(lambda aviso, **k: {"palabras": r.subtitulos_automaticos(aviso=aviso, **k)},
                      lambda res: self._poner_subtitulos({**self.proyecto["subtitulos"], "activos": True,
                                                          "palabras": res["palabras"]}),  # con el estilo elegido
                      self.subs_btn, proyecto=self.proyecto, carpeta=self._carpeta())

    def _poner_subtitulos(self, subtitulos):
        if self._operar(lambda p: edicion.validar({**p, "subtitulos": subtitulos})) is None:
            self._mostrar_propiedades()  # la casilla vuelve a lo que tiene el proyecto

    # ---------- Grabarte (lo que usa ui/grabarte.PanelGrabarte) ----------

    def poner_bajar_musica(self, si):
        """«Bajar la música cuando hablas» (en Audio y en Grabarte: las dos casillas enseñan lo mismo)."""
        if not self._cargando:
            self._operar(lambda p: edicion.validar({**p, "bajar_musica": bool(si)}))

    def _video_elegido(self) -> dict | None:
        grupo, e = self._seleccion()
        return e if grupo == "capas" and e["tipo"] == "video" else None

    def aplicar_disposicion(self, cual, forma):
        """Una disposición de Grabarte a la capa de video elegida, en un clic y un «deshacer» (sin ninguna elegida,
        queda para la próxima toma). Se queda su color de borde y, en las esquinas, el grosor que le pusiste."""
        e = self._video_elegido()
        if e:
            caja = edicion.disposicion(self.proyecto["formato"], cual, forma, e["borde"])
            if e["grosor_borde"] and caja["grosor_borde"]:
                caja["grosor_borde"] = e["grosor_borde"]
            self._cambiar(object(), **caja)

    def aplicar_forma(self, forma):
        if self._video_elegido():
            self._cambiar(object(), forma=forma)

    def preparar_grabacion(self, listo):
        """Antes de grabarte: los primeros PREVIA segundos del video desde el cursor, montados para que suenen mientras
        hablas (como ▶: montarlo todo hasta el final tardaba minutos en un video largo; el resto se monta mientras
        grabas, _siguiente_tramo). listo(archivo); listo(None) si desde ahí no hay nada que reproducir (se graba
        igual); listo(False) si falló."""
        self.parar()
        r = render()
        if self.cursor >= edicion.duracion_total(self.proyecto) or not hasattr(r, "vista_previa"):
            return listo(None)
        self.estado.setText(t("Preparando el video para grabarte…"))
        self._trabajo(lambda aviso, **k: {"archivo": str(r.vista_previa(aviso=aviso, **k))},
                      lambda res: listo(res["archivo"]), self.play_btn, al_fallar=lambda _e: listo(False),
                      proyecto=self.proyecto, carpeta=self._carpeta(), desde=self.cursor, segundos=PREVIA)

    def reproducir_grabando(self, archivo, desde, silenciar):
        """Empezó la grabación: el video suena desde `desde` (sin sonido si lo pediste: con altavoces se colaría en el
        micrófono) y se monta el trozo siguiente."""
        self.sonido.setMuted(bool(silenciar))
        if archivo:
            self.cursor, self._previa = desde, (self.proyecto, desde, archivo)
            self._ver(archivo, desde)
            self._siguiente_tramo(desde + PREVIA)

    def _siguiente_tramo(self, desde):
        """Grabando, el video se monta de PREVIA en PREVIA, como ▶: el trozo siguiente mientras suena este (lo pone
        _estado_video al acabar el que suena)."""
        self._siguiente = None
        r = render()
        if desde >= edicion.duracion_total(self.proyecto) or not hasattr(r, "vista_previa"):
            return
        proyecto = self.proyecto
        self._trabajo(lambda aviso, **k: {"archivo": str(r.vista_previa(aviso=aviso, **k))},
                      lambda res: setattr(self, "_siguiente", (proyecto, desde, res["archivo"])),
                      proyecto=proyecto, carpeta=self._carpeta(), desde=desde, segundos=PREVIA)

    def fin_grabacion(self):
        self._siguiente = None
        self.sonido.setMuted(False)
        self.parar()

    def toma_lista(self, ruta, inicio, en_hilo=True, desde=0.0):
        """Una grabación (de Grabarte o importada) al video en el segundo `inicio`, con la disposición y la forma
        elegidas en el panel y el borde del color de tu marca: una capa de video o, si es solo voz, un audio «voz».
        `desde`: lo que sobra al principio del archivo (lo grabado antes de que arrancara el video). Se mide en el hilo
        (en_hilo=False: aquí mismo, al cerrar la app) y entra en un solo «deshacer»."""
        cual, forma = self.grabarte.disposicion()
        formato, carpeta = self.proyecto["formato"], self.carpeta
        datos = {"ruta": str(ruta), "inicio": round(min(max(0.0, inicio), edicion.MAX_DURACION), 3), "cual": cual,
                 "forma": forma, "borde": _color_marca(), "desde": round(max(0.0, desde), 3)}

        def medir(aviso=None, **k):
            try:
                q = edicion.anadir_grabacion(edicion.nuevo(formato=formato), **k)
            except (ValueError, OSError) as error:  # lo dice poner, con dónde quedó tu grabación
                return {"error": str(error)}
            return {"nuevo": ("capas", q["capas"][-1]) if q["capas"] else ("audios", q["audios"][-1])}

        def no_entro(error):
            # Una toma de Grabarte no se pierde: sigue en grabaciones/ y se puede volver a meter
            tuya = carpeta is not None and Path(ruta).parent == carpeta / "grabaciones"
            mensaje_error(self, t("No se pudo añadir la grabación"), f"{error}\n\n" + t(
                "El archivo sigue en {ruta}: cuando haya sitio, añádelo con «Importar grabación».", ruta=ruta)
                          if tuya else error)

        def poner(r):
            if carpeta is not None and self.carpeta != carpeta:  # mientras se medía se abrió otro video
                return self.estado.setText(f"⚠️ {t('La grabación es de otro video: está en {ruta}', ruta=ruta)}")
            if "error" in r:
                return no_entro(r["error"])
            clave, e = r["nuevo"]
            p = self.proyecto
            try:
                limpio = edicion.validar({**p, clave: p[clave] + [{**e, "id": None}]})  # validar le da un id nuevo
            except ValueError as error:
                return no_entro(error)
            self._carpeta()
            self._aplicar(limpio)
            self._elegir(limpio[clave][-1]["id"])
        if en_hilo:
            return self._trabajo(medir, poner, **datos)
        poner(medir(**datos))

    def parar_grabacion(self):
        """Al cerrar la app: si estás grabando, se para, se guarda y entra en el video (luego se pregunta si
        guardarlo)."""
        self.grabarte.apagar(esperar=True)

    def hideEvent(self, e):
        if not e.spontaneous():  # otra página del menú (minimizar la ventana no cuenta): cámara y micrófono, apagados
            self.grabarte.apagar()
        super().hideEvent(e)

    # ---------- Trabajos en segundo plano ----------

    def _trabajo(self, funcion, al_terminar, boton_tarea=None, al_fallar=None, **datos):
        """Lo lento en un hilo (ui.comun.Tarea), con el progreso arriba; su resultado (un dict) va a al_terminar y, si
        falla, el error se enseña y va a al_fallar."""
        tarea = Tarea(funcion, **datos)
        self.tareas.add(tarea)  # si nadie la guarda, Python la destruiría a medias
        if boton_tarea:
            boton_tarea.setEnabled(False)
        self.progreso.setValue(0)
        self.progreso.show()
        tarea.progreso.connect(self._avance)
        tarea.listo.connect(al_terminar)
        tarea.fallo.connect(lambda e: (self.estado.setText(""), mensaje_error(self, t("No se pudo terminar"), e),
                                       al_fallar and al_fallar(e)))
        tarea.finished.connect(lambda: self._fin_tarea(tarea, boton_tarea))
        tarea.start()

    def _avance(self, texto, fraccion):
        self._ultimo_aviso = texto
        self.estado.setText(texto)
        self.progreso.setValue(int(fraccion * 100))

    def _fin_tarea(self, tarea, boton_tarea):
        tarea.wait()
        self.tareas.discard(tarea)
        if boton_tarea:
            boton_tarea.setEnabled(True)
        self.progreso.setVisible(bool(self.tareas))
        if not self.tareas and self.estado.text() == self._ultimo_aviso:  # «Importando 3 de 3…» ya no es verdad
            self.estado.setText("")
        self._limpiar()

    # ---------- Archivo ----------

    def _carpeta(self) -> Path:
        """La carpeta del proyecto; se crea la primera vez que hace falta (al meter un medio o guardar)."""
        if self.carpeta is None:
            self.carpeta = edicion.nueva_carpeta(self.proyecto["nombre"])
            self.linea.carpeta = self.carpeta
        return self.carpeta

    def _empezar(self, proyecto, carpeta):
        self.grabarte.apagar(esperar=True)  # una toma a medias se guarda antes de cambiar de video
        self.parar()
        self._limpiar(self.carpeta)
        if carpeta is None:  # al abrir, _abrir ya vació la caché y dejó leídas las fotos del proyecto nuevo
            diseno._leer_imagen.cache_clear()  # las fotos del proyecto anterior no se quedan en memoria
        self.proyecto, self.carpeta, self.sel, self.cursor = proyecto, carpeta, "", 0.0
        self.deshacer_pila, self.rehacer_pila, self._ultima, self.sucio, self._previa = [], [], None, False, None
        self._siguiente = None
        self._refrescar()

    def _limpiar(self, carpeta=None):
        """Borra la carpeta de un video que nunca se guardó (su caché ocupa ~0,5 MB por segundo de video y no sale en
        «Abrir»), en cuanto ningún trabajo la usa. Quien la descarta ya confirmó perder los cambios."""
        if carpeta:
            self.player.setSource(QUrl())  # con la vista previa abierta en el reproductor, Windows no deja borrarla
            self._sin_guardar.add(carpeta)
        if not self.tareas:
            # + lo que dejó un borrado a medias: sin imagenes/ (nueva_carpeta siempre la crea) porque rmtree sí la
            # borró, pero una miniatura o un proxy tenía abierto un archivo de cache/ o la volvió a crear
            for c in self._sin_guardar | {c for c in edicion.CARPETA.glob("*/") if not (c / "imagenes").exists()}:
                if c.parent == edicion.CARPETA and not (c / "proyecto.json").exists():  # solo las que hizo _carpeta
                    # Tus grabaciones no se borran nunca solas: de un video así solo se va la caché
                    shutil.rmtree(c / "cache" if any((c / "grabaciones").glob("*")) else c, ignore_errors=True)
            self._sin_guardar.clear()

    def _descartar_ok(self):
        """Antes de Nuevo, Abrir, Editar o cerrar: si el video tiene cambios, se pregunta. Una toma a medias se para y
        entra en el video ANTES de preguntar (así cuenta como cambio y no se descarta sin aviso)."""
        if self.grabarte.ocupado():
            self.grabarte.apagar(esperar=True)
        if not self.sucio:
            return True
        texto = t("El video tiene cambios sin guardar. ¿Seguir sin guardarlos?")
        grabaciones = self.carpeta / "grabaciones" if self.carpeta else None
        if grabaciones and any(grabaciones.glob("*")):  # sin guardar, esa carpeta no sale en «Abrir»
            texto += "\n\n" + t("Tus grabaciones se quedan en {carpeta}.", carpeta=grabaciones)
        return QMessageBox.question(self, t("Cambios sin guardar"), texto) == QMessageBox.Yes

    def editar_video(self, ruta, formato="9:16") -> bool:
        """«✂️ Editar» de un resultado: un proyecto nuevo con ese archivo. False si no se quieren perder los cambios."""
        if not self._descartar_ok():
            return False
        self._empezar(edicion.nuevo(formato=formato if formato in video.FORMATOS else "9:16"), None)
        self.importar([ruta])
        return True

    def guardar(self):
        try:
            edicion.guardar(self.proyecto, self._carpeta())
            self._miniatura().save(str(self.carpeta / "miniatura.png"))
        except (ValueError, OSError) as e:
            return mensaje_error(self, t("No se pudo guardar"), e)
        self.sucio = False
        self.estado.setText(f"💾 {t('Guardado en {carpeta}', carpeta=self.carpeta)}")

    def _miniatura(self) -> QImage:
        """Lo que se ve en el lienzo, pequeño, para la lista de «Abrir»."""
        caja = self.escena.sceneRect()
        k = 320 / max(caja.width(), caja.height())
        imagen = QImage(round(caja.width() * k), round(caja.height() * k), QImage.Format_ARGB32_Premultiplied)
        imagen.fill(Qt.black)
        p = QPainter(imagen)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.escena.render(p, QRectF(imagen.rect()), caja)
        p.end()
        return imagen

    def pedir_abrir(self):
        if self._descartar_ok():  # la lista lee todos los proyectos del disco: en el hilo
            self._trabajo(lambda aviso: {"lista": edicion.listar()}, self._elegir_proyecto)

    def _elegir_proyecto(self, resultado):
        lista = resultado["lista"]
        if not lista:
            return mensaje(self, t("Sin proyectos"), t("Aún no has guardado ningún video: usa «💾 Guardar»."))
        dialogo = pd.Cuadricula(self, t("Abrir un video"), lambda buscado: [
            pd._elemento(d["nombre"], d["carpeta"], QIcon(d["miniatura"])) for d in lista
            if buscado.lower() in d["nombre"].lower()], celda=170, pista=t("Buscar por nombre"))
        if dialogo.exec() and dialogo.valor:
            self.abrir(dialogo.valor)

    def abrir(self, carpeta):
        """Lee y valida el proyecto (y cada archivo que usa) en el hilo: puede venir de otro PC."""
        self._trabajo(_abrir, lambda r: self._abierto(r["proyecto"], Path(carpeta)), carpeta=str(carpeta))

    def _abierto(self, proyecto, carpeta):
        self._empezar(proyecto, carpeta)
        self._avisar_faltan()

    def _avisar_faltan(self) -> int:
        """Avisa arriba de los archivos del video que no encuentro (o quita el aviso si ya no falta ninguno)."""
        faltan = len({e["archivo"] for e in edicion._medios(self.proyecto) if e.get("falta")})
        aviso = t("No encuentro {n} archivo(s) del video (se movieron o se borraron): están en rojo; elige uno y "
                  "pulsa «Volver a enlazar…».", n=faltan)
        self.estado.setText(f"⚠️ {aviso}" if faltan else "")
        return faltan

    def reenlazar(self):
        """«Volver a enlazar…» del clip o audio elegido cuyo archivo falta. Se comprueba y mide en el hilo."""
        _, e = self._seleccion()
        # No se abre en la carpeta vieja: la ruta viene del proyecto (puede ser ajena) y podría ser de red
        ruta = QFileDialog.getOpenFileName(self, t("¿Dónde está ahora «{archivo}»?", archivo=Path(e["archivo"]).name),
                                           QStandardPaths.writableLocation(QStandardPaths.MoviesLocation),
                                           FILTRO_MEDIOS)[0]
        if not ruta:
            return
        proyecto = self.proyecto  # si se edita mientras tanto, su resultado ya no vale
        self._trabajo(lambda aviso, **k: {"proyecto": edicion.reenlazar(**k)},
                      lambda r: (self._aplicar(r["proyecto"]), self._avisar_faltan()) if self.proyecto is proyecto
                      else self.estado.setText(
                          f"⚠️ {t('El video cambió mientras se comprobaba el archivo: vuelve a enlazarlo.')}"),
                      self.reenlazar_btn, proyecto=proyecto, id_elemento=e["id"], ruta=ruta)

    def exportar(self):
        r = render()
        if not hasattr(r, "exportar"):
            return mensaje_error(self, t("Aún no disponible"), AUN_NO)
        if edicion.duracion_total(self.proyecto) == 0:
            return mensaje(self, t("Nada que exportar"), t("Añade algún video, foto o audio."))
        # ▶ borra el aviso de arriba: sin esto se sube un video con huecos del color de fondo sin darse cuenta
        faltan = self._avisar_faltan()
        if faltan and QMessageBox.question(
                self, t("Faltan archivos"), t("No encuentro {n} archivo(s) del video (están en rojo): esos trozos "
                                              "saldrán con el color de fondo y en silencio. ¿Exportar igual?",
                                              n=faltan)) != QMessageBox.Yes:
            return
        destino = destino_libre(self.proyecto["nombre"])
        destino.parent.mkdir(parents=True, exist_ok=True)
        self.estado.setText(t("Exportando…"))
        self._trabajo(lambda aviso, **k: {"archivo": str(r.exportar(aviso=aviso, **k))}, self._exportado_listo,
                      self.exportar_btn, proyecto=self.proyecto, carpeta=self._carpeta(), destino=destino,
                      calidad=self.calidad.currentData())

    def _exportado_listo(self, resultado):
        self._exportado = Path(resultado["archivo"])
        self.estado.setText(f"✅ {t('Exportado: {archivo}', archivo=self._exportado)}")

    def abrir_carpeta(self):
        """La carpeta de lo último exportado (por defecto, Videos / Ráfaga Studio)."""
        carpeta = self._exportado.parent if self._exportado else carpeta_videos()
        carpeta.mkdir(parents=True, exist_ok=True)
        os.startfile(carpeta)

    # ---------- Soltar archivos en la página ----------

    def dragEnterEvent(self, e):
        e.setAccepted(e.mimeData().hasUrls())

    def dropEvent(self, e):
        self.importar([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        e.acceptProposedAction()
