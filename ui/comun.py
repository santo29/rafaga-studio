"""Piezas comunes de la interfaz: estilo, mensajes, botones, tareas en segundo plano y el reproductor."""
import os
import traceback
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QProxyStyle, QPushButton,
                               QSlider, QStyle, QStyleFactory, QTextEdit, QVBoxLayout, QWidget)

from motor import desde_prompt, seguro
from motor.idioma import t
from ui.iconos import COLOR, icono, poner, separar


ESTILO = """
* { font-family: 'Segoe UI'; color: #ECECF1; font-size: 16px; }
QMainWindow, #contenido, QScrollArea, QScrollArea > QWidget > QWidget { background: #0F0F13; }
#barra { background: #17171D; border-right: 1px solid #24242C; }
#marca { font-size: 22px; font-weight: 800; color: #FFFFFF; padding-left: 4px; }
#nav { text-align: left; padding: 6px 16px; border: none; border-radius: 10px; background: transparent; color: #B4B4C0;
       font-size: 17px; }
#nav:hover { background: #20202A; color: #FFFFFF; }
#nav:checked { background: #2A2340; color: #FFFFFF; }
#titulo { font-size: 28px; font-weight: 700; }
#sub { color: #8D8D9A; }
#tarjeta { background: #17171D; border: 1px solid #24242C; border-radius: 14px; }
QLineEdit, QTextEdit, QComboBox, QSpinBox { background: #0F0F13; border: 1px solid #2C2C36; border-radius: 10px; padding: 10px; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #7C5CFF; }
QComboBox { padding-right: 30px; }
QComboBox:hover { border: 1px solid #3C3C48; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox QAbstractItemView { background: #17171D; color: #ECECF1; border: 1px solid #2C2C36;
                              padding: 4px; outline: none; selection-background-color: #2A2340; selection-color: #FFFFFF; }
QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 8px; }
QComboBox QAbstractItemView::item:hover { background: #2A2340; }
QSpinBox::up-button, QSpinBox::down-button { width: 22px; border: none; background: #20202A; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #2C2C36; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: #2C2C36; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QAbstractScrollArea::corner { background: transparent; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: #17171D; color: #ECECF1; border: 1px solid #2C2C36; }
QMenu { background: #17171D; border: 1px solid #2C2C36; padding: 4px; }
QMenu::item { padding: 8px 18px; border-radius: 6px; }
QMenu::item:selected { background: #2A2340; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #3C3C48; border-radius: 5px; background: #0F0F13; }
QCheckBox::indicator:checked { background: #7C5CFF; border: 1px solid #7C5CFF; }
#formato { background: #0F0F13; border: 1px solid #2C2C36; border-radius: 10px; padding: 10px 14px; color: #A9A9B6; }
#formato:checked { border: 2px solid #7C5CFF; color: #FFFFFF; background: #1C1830; }
#principal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7C5CFF, stop:1 #FF4D8D);
             border: none; border-radius: 10px; padding: 12px 22px; font-weight: 700; color: white; }
#principal:disabled { background: #2C2C36; color: #777; }
#secundario { background: #20202A; border: 1px solid #2C2C36; border-radius: 10px; padding: 9px 16px; }
#secundario:hover { background: #2A2A36; }
QProgressBar { background: #0F0F13; border: 1px solid #2C2C36; border-radius: 6px; height: 10px; text-align: center; font-size: 12px; }
QProgressBar::chunk { background: #7C5CFF; border-radius: 6px; }
QListWidget { background: #0F0F13; border: 1px solid #24242C; border-radius: 10px; padding: 6px; }
QListWidget::item { padding: 10px; border-radius: 8px; }
QListWidget::item:selected { background: #2A2340; }
QSlider::groove:horizontal { height: 4px; background: #2C2C36; }
QSlider::handle:horizontal { background: #FFFFFF; width: 12px; margin: -5px 0; border-radius: 6px; }
QSlider::sub-page:horizontal { background: #7C5CFF; }
QDialog { background: #17171D; }
QMessageBox QLabel#qt_msgbox_label { min-width: 360px; font-size: 15px; padding: 4px 6px; }
QDialog QPushButton { background: #20202A; border: 1px solid #2C2C36; border-radius: 9px; padding: 8px 22px;
                      min-width: 80px; font-weight: 600; }
QDialog QPushButton:hover { background: #2A2A36; border: 1px solid #3C3C48; }
QDialog QPushButton:default { background: #7C5CFF; border: 1px solid #7C5CFF; color: #FFFFFF; }
QDialog QPushButton:default:hover { background: #8E72FF; }
"""
# Al dar estilo a ::drop-down y a los botones de los números, Qt deja de pintar sus flechas: se ponen a mano
_ASSETS = (Path(__file__).resolve().parent.parent / "assets").as_posix()
ESTILO += f"""
QComboBox::down-arrow {{ image: url("{_ASSETS}/flecha-abajo.svg"); width: 14px; height: 14px; }}
QAbstractSpinBox::up-arrow {{ image: url("{_ASSETS}/flecha-arriba.svg"); width: 12px; height: 12px; }}
QAbstractSpinBox::down-arrow {{ image: url("{_ASSETS}/flecha-abajo.svg"); width: 12px; height: 12px; }}
"""


class EstiloApp(QProxyStyle):
    """Fusion con los iconos de la app en las ventanas de aviso (en vez de los genéricos del sistema)."""
    AVISOS = {QStyle.SP_MessageBoxInformation: ("circle-check", "#7C5CFF"),
              QStyle.SP_MessageBoxWarning: ("triangle-alert", "#FFB454"),
              QStyle.SP_MessageBoxCritical: ("circle-x", "#FF4D8D"),
              QStyle.SP_MessageBoxQuestion: ("circle-help", "#7C5CFF")}

    def __init__(self):
        super().__init__(QStyleFactory.create("Fusion"))

    def standardIcon(self, cual, opcion=None, widget=None):
        if cual in self.AVISOS:
            return icono(*self.AVISOS[cual])
        return super().standardIcon(cual, opcion, widget)


NOMBRES_FORMATO = {"9:16": "9:16  TikTok · Shorts · Reels", "16:9": "16:9  YouTube",
                   "1:1": f"1:1  {t('Cuadrado')}", "4:5": f"4:5  {t('Feed')}"}


class Tarea(QThread):
    """Corre el motor en segundo plano para que la ventana no se congele."""
    progreso = Signal(str, float)
    listo = Signal(dict)
    fallo = Signal(str)

    def __init__(self, funcion, **datos):
        super().__init__()
        self.funcion, self.datos = funcion, datos

    def run(self):
        try:
            self.listo.emit(self.funcion(**self.datos, aviso=lambda t, f: self.progreso.emit(t, f)))
        except Exception as e:  # el error se muestra al usuario, no debe tumbar la app
            traceback.print_exc()
            self.fallo.emit(str(e).strip() or t("Error inesperado ({tipo}). Inténtalo de nuevo.",
                                                tipo=type(e).__name__))


def mensaje(padre, titulo, texto, icono=QMessageBox.Information):
    """Ventana de mensaje en texto plano: un error o un título de YouTube no puede meter HTML ni enlaces."""
    caja = QMessageBox(icono, titulo, str(texto), QMessageBox.Ok, padre)
    caja.setTextFormat(Qt.PlainText)
    return caja.exec()


def mensaje_error(padre, titulo, texto):
    return mensaje(padre, titulo, texto, QMessageBox.Warning)


def archivo_valido(padre, ruta: str, tipos: set[str], que: str) -> Path | None:
    """La ruta real si es una imagen/audio válido; si no, avisa y da None. Misma frontera que el motor: nada de
    comprobar la ruta antes (con una carpeta de red, eso ya conectaría con ese servidor)."""
    try:
        return seguro.archivo_medio(ruta, tipos, que)
    except ValueError as e:
        mensaje_error(padre, t("Revisa el archivo"), e)
        return None


def etiqueta(texto, nombre=None):
    l = QLabel(separar(texto)[1])  # un título con emoji delante («✨  Diseñar con IA») sale sin él: estilo sobrio
    l.setTextFormat(Qt.PlainText)  # títulos, errores y avisos vienen de fuera: nunca se interpretan como HTML
    l.setWordWrap(True)
    if nombre:
        l.setObjectName(nombre)
    return l


def boton(texto, nombre="secundario"):
    """Botón con estilo. Si el texto empieza por un emoji conocido («📂  Abrir»), sale un icono de línea en su lugar."""
    b = QPushButton()
    b.setObjectName(nombre)
    b.setCursor(Qt.PointingHandCursor)
    b.setIconSize(QSize(22, 22) if nombre == "nav" else QSize(18, 18))
    poner(b, texto, "#FFFFFF" if nombre == "principal" else COLOR)
    return b


def tarjeta():
    f = QFrame()
    f.setObjectName("tarjeta")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 20, 20, 20)
    lay.setSpacing(12)
    return f, lay


class SelectorFormato(QWidget):
    """Botones de formato como en CapCut."""
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.grupo = QButtonGroup(self)
        for clave, nombre in NOMBRES_FORMATO.items():
            b = QPushButton(nombre)
            b.setObjectName("formato")
            b.setCheckable(True)
            b.setProperty("formato", clave)
            b.setChecked(clave == "9:16")
            self.grupo.addButton(b)
            lay.addWidget(b)
        lay.addStretch()

    def valor(self):
        return self.grupo.checkedButton().property("formato")


class SelectorVoz(QComboBox):
    """Voces gratis + las de ElevenLabs. Se recarga al abrirse por si se conectó ElevenLabs después. Sin elegir, sale
    una voz en el idioma de la app."""
    def __init__(self):
        super().__init__()
        self._cargar()

    def _cargar(self):
        actual = self.currentData() or desde_prompt.voz_por_defecto()
        self.clear()
        for nombre, voz in desde_prompt.voces().items():
            self.addItem(nombre, voz)
        self.setCurrentIndex(max(self.findData(actual), 0))

    def showPopup(self):
        self._cargar()
        super().showPopup()


def resumen_avisos(avisos: list[str], maximo: int = 5) -> str:
    """Avisos cortos y sin direcciones web largas, para que quepan en pantalla (el detalle está en proyecto.json)."""
    import re
    lineas = [f"⚠️ {re.sub(r'https?://\S+', '…', a)[:220]}" for a in avisos[:maximo]]
    if len(avisos) > maximo:
        lineas.append(t("… y {n} aviso(s) más (todos en proyecto.json, en la carpeta del proyecto).",
                         n=len(avisos) - maximo))
    return "\n".join(lineas)


class Reproductor(QFrame):
    """Vista previa de los videos generados, con su título, descripción y hashtags."""
    # Lo pone app.py: al_editar(archivo, formato) abre el resultado en el editor de video (las páginas no se conocen)
    al_editar = None

    def __init__(self):
        super().__init__()
        self.setObjectName("tarjeta")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        self.lista = QListWidget()
        self.lista.setMaximumHeight(170)
        self.pantalla = QVideoWidget()
        self.pantalla.setMinimumHeight(360)
        self.pantalla.setStyleSheet("background: black; border-radius: 10px;")
        self.player = QMediaPlayer(self)
        self.sonido = QAudioOutput(self)
        self.player.setAudioOutput(self.sonido)
        self.player.setVideoOutput(self.pantalla)
        self.barra = QSlider(Qt.Horizontal)
        self.barra.sliderMoved.connect(self.player.setPosition)
        self.player.durationChanged.connect(lambda d: self.barra.setRange(0, d))
        self.player.positionChanged.connect(self.barra.setValue)
        self.play = boton(f"▶  {t('Reproducir')}")
        self.play.clicked.connect(self._alternar)
        self.info = QTextEdit()  # solo el texto para publicar: lo que copia el botón
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(130)
        self.avisos_txt = etiqueta("")  # avisos técnicos aparte, para que nunca se copien a una publicación
        self.avisos_txt.setStyleSheet("color: #FFB454;")
        self.avisos_txt.hide()
        copiar, abrir = boton(t("Copiar texto para publicar")), boton(t("Abrir carpeta"))
        copiar.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.info.toPlainText()))
        abrir.clicked.connect(self._abrir_carpeta)
        self.editar = boton(f"✂️  {t('Editar')}")
        self.editar.setToolTip(t("Abrir este resultado en el editor de video"))
        self.editar.clicked.connect(self._editar)
        self.editar.setVisible(Reproductor.al_editar is not None)
        self.formato = "9:16"
        fila = QHBoxLayout()
        for w in (self.play, self.editar, copiar, abrir):
            fila.addWidget(w)
        fila.addStretch()
        lay.addWidget(etiqueta(t("Resultados"), "sub"))
        lay.addWidget(self.lista)
        lay.addWidget(self.pantalla, 1)
        lay.addWidget(self.barra)
        lay.addLayout(fila)
        lay.addWidget(self.avisos_txt)
        lay.addWidget(self.info)
        self.lista.currentRowChanged.connect(self._elegir)
        self.resultados = []

    def mostrar(self, proyecto):
        self.resultados, self.formato = proyecto["resultados"], proyecto.get("formato", "9:16")
        avisos = proyecto.get("avisos") or []
        self.avisos_txt.setText(resumen_avisos(avisos))
        self.avisos_txt.setVisible(bool(avisos))
        self.lista.clear()
        for i, r in enumerate(self.resultados, 1):
            extra = f"  ·  {r['fin'] - r['inicio']:.0f}s  ·  {r['puntuacion']}/100" if "puntuacion" in r else ""
            # t(): la Cabina guarda sus títulos en español; los demás (de la IA o del usuario) quedan igual
            self.lista.addItem(QListWidgetItem(f"{i}. {t(r['titulo'])}{extra}"))
        if self.resultados:
            self.lista.setCurrentRow(0)

    def _elegir(self, fila):
        if fila < 0:
            return
        r = self.resultados[fila]
        self.player.setSource(QUrl.fromLocalFile(r["archivo"]))
        self.info.setPlainText(f"{t(r['titulo'])}\n\n{r['descripcion']}\n\n" + " ".join(
            h if h.startswith("#") else f"#{h}" for h in r["hashtags"]))
        self.player.play()
        poner(self.play, f"⏸  {t('Pausar')}")

    def _alternar(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            poner(self.play, f"▶  {t('Reproducir')}")
        else:
            self.player.play()
            poner(self.play, f"⏸  {t('Pausar')}")

    def _abrir_carpeta(self):
        fila = self.lista.currentRow()
        if fila >= 0:
            os.startfile(os.path.dirname(self.resultados[fila]["archivo"]))

    def _editar(self):
        fila = self.lista.currentRow()
        if fila >= 0 and Reproductor.al_editar:  # por la clase: guardado en ella, Python lo ataría a esta instancia
            self.player.pause()
            poner(self.play, f"▶  {t('Reproducir')}")
            Reproductor.al_editar(self.resultados[fila]["archivo"], self.formato)


class PaginaTrabajo(QWidget):
    """Base de las páginas que lanzan un trabajo: formulario arriba, progreso y resultados abajo."""
    def __init__(self, titulo, subtitulo):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(32, 28, 32, 28)
        self.lay.setSpacing(14)
        self.lay.addWidget(etiqueta(titulo, "titulo"))
        self.lay.addWidget(etiqueta(subtitulo, "sub"))
        self.form, self.form_lay = tarjeta()
        self.lay.addWidget(self.form)
        self.estado = etiqueta("", "sub")
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.hide()
        self.lay.addWidget(self.progreso)
        self.lay.addWidget(self.estado)
        self.reproductor = Reproductor()
        self.reproductor.hide()
        self.lay.addWidget(self.reproductor, 1)
        self.lay.addStretch()
        self.tarea = None

    def lanzar(self, boton_iniciar, funcion, **datos) -> bool:
        """False si ya hay un trabajo en marcha: soltar un hilo que corre tumba la app cuando termina."""
        if self.tarea and self.tarea.isRunning():
            mensaje(self, t("Estoy trabajando"), t("Espera a que termine el trabajo actual."))
            return False
        boton_iniciar.setEnabled(False)
        self.progreso.show()
        self.progreso.setValue(0)
        self.tarea = Tarea(funcion, **datos)
        self.tarea.progreso.connect(lambda t, f: (self.estado.setText(t), self.progreso.setValue(int(f * 100))))
        self.tarea.listo.connect(lambda p: (self.reproductor.show(), self.reproductor.mostrar(p), p.get("avisos") and
                                            mensaje(self, t("Terminado con avisos"),
                                                                    resumen_avisos(p["avisos"]))))
        self.tarea.fallo.connect(lambda e: (self.estado.setText(""), mensaje_error(self, t("No se pudo terminar"), e)))
        self.tarea.finished.connect(lambda: (boton_iniciar.setEnabled(True), self.progreso.hide()))
        self.tarea.start()
        return True


def ver_imagen(padre, ruta, titulo: str):
    """Una imagen (p. ej. un diseño de ejemplo) en grande, en una ventana con el estilo de la app."""
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QDialog
    ventana = QDialog(padre)
    ventana.setWindowTitle(titulo)
    lay = QVBoxLayout(ventana)
    lay.setContentsMargins(16, 16, 16, 16)
    imagen = QLabel()
    imagen.setPixmap(QPixmap(str(ruta)).scaled(QSize(960, 720), Qt.KeepAspectRatio, Qt.SmoothTransformation))
    imagen.setAlignment(Qt.AlignCenter)
    lay.addWidget(imagen)
    cerrar = boton(t("Cerrar"))
    cerrar.clicked.connect(ventana.accept)
    lay.addWidget(cerrar, 0, Qt.AlignRight)
    ventana.setAttribute(Qt.WA_DeleteOnClose)  # al cerrarla se libera
    ventana.open()  # sin bloquear: la app sigue viva detrás
    return ventana


def campo_archivo(texto, filtro, al_elegir=None):
    """Una caja de texto con botón «Elegir…» para escoger un archivo."""
    fila = QHBoxLayout()
    campo = QLineEdit()
    campo.setPlaceholderText(texto)
    elegir = boton(t("Elegir…"))

    def abrir():
        ruta, _ = QFileDialog.getOpenFileName(campo, texto, "", filtro)
        if ruta:
            campo.setText(ruta)
            if al_elegir:
                al_elegir(ruta)
    elegir.clicked.connect(abrir)
    fila.addWidget(campo, 1)
    fila.addWidget(elegir)
    return fila, campo
