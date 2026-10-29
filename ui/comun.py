"""Piezas comunes de la interfaz: estilo, mensajes, botones, tareas en segundo plano y el reproductor."""
import os
import re
import shutil
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, QStandardPaths, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QActionGroup, QBrush, QColor, QFont, QFontMetrics, QGuiApplication, QImage, QKeySequence,
                           QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QProgressBar, QProxyStyle, QPushButton, QScrollArea, QSizePolicy, QSlider, QStyle,
                               QStyleFactory, QTextEdit, QVBoxLayout, QWidget)

from motor import claves, desde_prompt, guardia, ia, seguro
from motor.idioma import dinero, t, texto_de_error
from ui.iconos import COLOR, icono, poner, separar


# Vidrio 3D con los colores de la marca. QSS no tiene box-shadow ni desenfoque de fondo: el volumen sale de degradados
# rgba (arriba más claro), un borde de arriba más brillante (el reflejo) y uno de abajo más oscuro. Al pulsar se hunde:
# el reflejo pasa abajo. Los bordes miden lo mismo en todos los estados para que nada salte al pasar el ratón.
# Para que el vidrio se note tiene que haber algo detrás: una luz violeta de ambiente en el fondo de las páginas.
# El foco (solo con el teclado: los botones son Qt.TabFocus) pinta los lados y el borde de abajo, nunca el reflejo
# de arriba; va después de :checked y antes de :pressed para que al pulsar se vea el hundido.
ESTILO = """
* { font-family: 'Segoe UI'; color: #ECECF1; font-size: 16px; }
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #0F0F13; }
#contenido { background: qradialgradient(cx:0.82, cy:0, radius:1.05, fx:0.82, fy:0, stop:0 #2A1D52,
                                         stop:0.45 #17142A, stop:1 #0F0F13); }
QScrollArea#pagina, QScrollArea#pagina > QWidget, QScrollArea#pagina > QWidget > QWidget { background: transparent; }
#barra { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A1A22, stop:1 #131318);
         border-right: 1px solid rgba(255, 255, 255, 0.06); }
#marca { font-size: 22px; font-weight: 800; color: #FFFFFF; padding-left: 4px; }
#nav { text-align: left; padding: 4px 15px; border: 1px solid transparent; border-radius: 12px; background: transparent;
       color: #B4B4C0; font-size: 17px; }
#nav:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.08),
                                         stop:1 rgba(255, 255, 255, 0.03));
             border-color: rgba(255, 255, 255, 0.06); border-top-color: rgba(255, 255, 255, 0.12); color: #FFFFFF; }
#nav:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(168, 146, 255, 0.62),
                                           stop:0.55 rgba(124, 92, 255, 0.38), stop:1 rgba(118, 86, 250, 0.26));
               border-color: rgba(150, 125, 255, 0.40); border-top-color: rgba(225, 215, 255, 0.60); color: #FFFFFF; }
#nav:focus { border-left-color: rgba(61, 245, 255, 0.55); border-right-color: rgba(61, 245, 255, 0.55);
             border-bottom-color: rgba(61, 245, 255, 0.55); }
#nav:pressed { background: rgba(124, 92, 255, 0.18); border-top-color: rgba(0, 0, 0, 0.30);
               border-bottom-color: rgba(200, 185, 255, 0.45); }
#titulo { font-size: 28px; font-weight: 700; }
#sub { color: #8D8D9A; }
#tarjeta { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.07),
                                       stop:1 rgba(255, 255, 255, 0.025));
           border: 1px solid rgba(255, 255, 255, 0.08); border-top-color: rgba(255, 255, 255, 0.18); border-radius: 16px; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateTimeEdit { background: #0F0F13; border: 1px solid #2C2C36; border-radius: 10px; padding: 10px; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateTimeEdit { border-top-color: #23232B; border-bottom-color: #383844; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateTimeEdit:focus { border: 1px solid #7C5CFF; }
QDateTimeEdit::drop-down { border: none; width: 28px; }
QCalendarWidget QAbstractItemView { background: #17171D; alternate-background-color: #20202A;
                                    selection-background-color: #7C5CFF; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #20202A; }
QComboBox { padding-right: 30px; }
QComboBox:hover { border: 1px solid #3C3C48; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox QAbstractItemView { background: #17171D; color: #ECECF1; border: 1px solid #2C2C36;
                              padding: 4px; outline: none; selection-background-color: rgba(124, 92, 255, 0.34);
                              selection-color: #FFFFFF; }
QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 8px; }
QComboBox QAbstractItemView::item:hover, QMenu::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.42), stop:1 rgba(124, 92, 255, 0.20)); }
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
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #3C3C48; border-radius: 5px; background: #0F0F13; }
QCheckBox::indicator:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #9A80FF, stop:1 #6A4BF0);
                               border: 1px solid #7C5CFF; border-top-color: #C9BBFF; }
#formato { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.07),
                                       stop:1 rgba(255, 255, 255, 0.02));
           border: 1px solid rgba(255, 255, 255, 0.09); border-top-color: rgba(255, 255, 255, 0.17); border-radius: 10px;
           padding: 10px 14px; color: #A9A9B6; }
#formato:hover { color: #FFFFFF; border-color: rgba(150, 125, 255, 0.45); border-top-color: rgba(210, 198, 255, 0.55); }
#formato:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.55),
                                               stop:0.55 rgba(124, 92, 255, 0.34), stop:1 rgba(124, 92, 255, 0.24));
                   border-color: rgba(150, 125, 255, 0.55); border-top-color: rgba(230, 222, 255, 0.70); color: #FFFFFF; }
#formato:focus { border-left-color: rgba(61, 245, 255, 0.70); border-right-color: rgba(61, 245, 255, 0.70);
                 border-bottom-color: rgba(61, 245, 255, 0.70); }
/* Un grupo de opciones (Segmentos) es UNA pieza: una cápsula de vidrio con la elegida en relieve. La elegida es vidrio
   claro y casi neutro; el color es la luz violeta que Segmentos pinta debajo y que se ve a través */
#segmentos { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.075),
                                         stop:1 rgba(255, 255, 255, 0.025));
             border: 1px solid rgba(255, 255, 255, 0.08); border-top-color: rgba(255, 255, 255, 0.17); border-radius: 22px; }
#segmentos #formato { background: transparent; border: 1px solid transparent; border-radius: 17px; padding: 7px 16px; }
#segmentos #formato:hover { background: rgba(255, 255, 255, 0.06); color: #FFFFFF; }
#segmentos #formato:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.20),
                                                          stop:1 rgba(255, 255, 255, 0.07));
                              border-color: rgba(255, 255, 255, 0.16); border-top-color: rgba(255, 255, 255, 0.60);
                              border-bottom-color: rgba(255, 255, 255, 0.10); color: #FFFFFF; }
#segmentos #formato:focus { border-left-color: rgba(61, 245, 255, 0.70); border-right-color: rgba(61, 245, 255, 0.70);
                            border-bottom-color: rgba(61, 245, 255, 0.70); }
/* El botón de la acción principal: violeta→rosa de la marca, un tono más hondo para que el texto blanco pase AA
   (también al pasar el ratón: #7656FA y #D63470 siguen por encima de 4.5:1) */
#principal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6C4BF5, stop:1 #C92A66);
             border: 1px solid rgba(255, 255, 255, 0.14); border-top-color: rgba(255, 255, 255, 0.45);
             border-bottom-color: rgba(0, 0, 0, 0.35); border-radius: 12px; padding: 11px 22px; font-weight: 700;
             color: #FFFFFF; }
#principal:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7656FA, stop:1 #D63470);
                   border-color: rgba(255, 255, 255, 0.24); border-top-color: rgba(255, 255, 255, 0.75); }
#principal:focus { border-left-color: #3DF5FF; border-right-color: #3DF5FF; border-bottom-color: #3DF5FF; }
#principal:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5A3CDB, stop:1 #AE225B);
                     border-top-color: rgba(0, 0, 0, 0.40); border-bottom-color: rgba(255, 255, 255, 0.30); }
#principal:disabled { background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.08); color: #8D8D9A; }
#secundario { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.10),
                                          stop:1 rgba(255, 255, 255, 0.04));
              border: 1px solid rgba(255, 255, 255, 0.09); border-top-color: rgba(255, 255, 255, 0.20);
              border-bottom-color: rgba(0, 0, 0, 0.30); border-radius: 10px; padding: 9px 16px; }
#secundario:hover { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.15),
                                                stop:1 rgba(255, 255, 255, 0.06));
                    border-color: rgba(150, 125, 255, 0.45); border-top-color: rgba(210, 198, 255, 0.60); }
#secundario:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.52),
                                                  stop:1 rgba(124, 92, 255, 0.22));
                      border-color: rgba(150, 125, 255, 0.50); border-top-color: rgba(225, 215, 255, 0.65); }
#secundario:focus { border-left-color: rgba(61, 245, 255, 0.70); border-right-color: rgba(61, 245, 255, 0.70);
                    border-bottom-color: rgba(61, 245, 255, 0.70); }
#secundario:pressed { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0, 0, 0, 0.22),
                                                  stop:1 rgba(255, 255, 255, 0.07));
                      border-top-color: rgba(0, 0, 0, 0.40); border-bottom-color: rgba(255, 255, 255, 0.16); }
#secundario:disabled { background: rgba(255, 255, 255, 0.03); border-color: rgba(255, 255, 255, 0.05); color: #6E6E7A; }
QProgressBar { background: #0F0F13; border: 1px solid #2C2C36; border-radius: 6px; height: 10px; text-align: center; font-size: 12px; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #9A80FF, stop:1 #6A4BF0);
                      border-radius: 6px; }
QListWidget { background: #0F0F13; border: 1px solid #24242C; border-radius: 10px; padding: 6px; }
QListWidget::item { padding: 10px; border-radius: 8px; }
QListWidget::item:selected { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.42),
                                                         stop:1 rgba(124, 92, 255, 0.20)); }
QSlider::groove:horizontal { height: 4px; background: #2C2C36; }
QSlider::handle:horizontal { background: #FFFFFF; width: 12px; margin: -5px 0; border-radius: 6px; }
QSlider::sub-page:horizontal { background: #7C5CFF; }
QDialog { background: #17171D; }
QMessageBox QLabel#qt_msgbox_label { min-width: 360px; font-size: 15px; padding: 4px 6px; }
QDialog QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.10),
                                                  stop:1 rgba(255, 255, 255, 0.04));
                      border: 1px solid rgba(255, 255, 255, 0.10); border-top-color: rgba(255, 255, 255, 0.22);
                      border-radius: 10px; padding: 8px 22px; min-width: 80px; font-weight: 600; }
QDialog QPushButton:hover { border-color: rgba(150, 125, 255, 0.50); border-top-color: rgba(210, 198, 255, 0.65); }
QDialog QPushButton:default { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6A4AEC, stop:1 #5338D2);
                              border: 1px solid #7C5CFF; border-top-color: #C9BBFF; border-bottom-color: #3F2AA6;
                              color: #FFFFFF; }
QDialog QPushButton:default:hover { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7656F5,
                                                                      stop:1 #6044E3); }
/* el botón por defecto tiene el foco al abrirse: el anillo va en los lados y abajo, el reflejo de arriba se queda */
QDialog QPushButton:focus { border-left-color: rgba(61, 245, 255, 0.75); border-right-color: rgba(61, 245, 255, 0.75);
                            border-bottom-color: rgba(61, 245, 255, 0.75); }
QDialog QPushButton:pressed { background: rgba(0, 0, 0, 0.20); border-top-color: rgba(0, 0, 0, 0.40);
                              border-bottom-color: rgba(255, 255, 255, 0.16); }
QDialog QPushButton:default:pressed { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4A31B8, stop:1 #5338D2);
                                      border-top-color: #2A1C70; border-bottom-color: #C9BBFF; }
"""
# Al dar estilo a ::drop-down y a los botones de los números, Qt deja de pintar sus flechas: se ponen a mano
_ASSETS = (Path(__file__).resolve().parent.parent / "assets").as_posix()
ESTILO += f"""
QComboBox::down-arrow {{ image: url("{_ASSETS}/flecha-abajo.svg"); width: 14px; height: 14px; }}
QAbstractSpinBox::up-arrow {{ image: url("{_ASSETS}/flecha-arriba.svg"); width: 12px; height: 12px; }}
QAbstractSpinBox::down-arrow {{ image: url("{_ASSETS}/flecha-abajo.svg"); width: 12px; height: 12px; }}
"""
# El reflejo de arriba del vidrio: QSS no deja dos fondos en una regla, así que va como imagen encima del degradado.
# El atajo «background:» de un estado lo borra: al pasar el ratón se cambia solo «background-color» para conservarlo,
# y al pulsar o desactivado se usa el atajo a propósito (el botón se hunde o se apaga). QSS no escala la imagen: en
# las piezas bajas (menú, barras de Diseño, pestañas) va la fina, de 8 px, para que sea un canto de luz y no media cara.
REFLEJO = f'background-image: url("{_ASSETS}/brillo.svg"); background-repeat: repeat-x; background-position: top;'
REFLEJO_FINO = REFLEJO.replace("brillo.svg", "brillo-fino.svg")
ESTILO += f"""
#principal, #secundario, #secundario:checked, #tarjeta, #formato:checked, #segmentos #formato:checked,
QDialog QPushButton, QDialog QPushButton:default {{ {REFLEJO} }}
#nav:checked {{ {REFLEJO_FINO} }}
#nav:checked:pressed, #secundario:checked:disabled {{ background-image: none; }}
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


NOMBRES_FORMATO = {"9:16": "9:16 · TikTok, Shorts, Reels", "16:9": "16:9 · YouTube",
                   "1:1": f"1:1 · {t('Cuadrado')}", "4:5": f"4:5 · {t('Publicación')}"}


class Tarea(QThread):
    """Corre el motor en segundo plano para que la ventana no se congele."""
    progreso = Signal(str, float)
    listo = Signal(dict)
    fallo = Signal(str)
    modelo_video = None  # el del selector «Modelo de video», solo para este trabajo (claves.por_trabajo, en su hilo)

    def __init__(self, funcion, **datos):
        super().__init__()
        self.funcion, self.datos = funcion, datos
        self.error = None  # la excepción de `fallo`, por si la página necesita más que su texto (p. ej. su título)

    def run(self):
        try:
            with claves.por_trabajo(self.modelo_video):
                self.listo.emit(self.funcion(**self.datos, aviso=lambda t, f: self.progreso.emit(t, f)))
        except Exception as e:  # el error se muestra al usuario, no debe tumbar la app (el detalle, en la consola)
            traceback.print_exc()
            self.error = e
            self.fallo.emit(texto_de_error(e))


def mensaje(padre, titulo, texto, icono=QMessageBox.Information, botones=()):
    """Ventana de mensaje en texto plano: un error o un título de YouTube no puede meter HTML ni enlaces.
    botones: [(texto, función)] además de «Aceptar» (p. ej. abrir los ajustes de sonido de Windows)."""
    caja = QMessageBox(icono, titulo, str(texto), QMessageBox.Ok, padre)
    caja.setTextFormat(Qt.PlainText)
    for nombre, funcion in botones:
        caja.addButton(nombre, QMessageBox.ActionRole).clicked.connect(funcion)
    return caja.exec()


class AvisosLegibles(QObject):
    """Filtro de la app: en un PC con la pantalla al 150 %, QMessageBox dejó un aviso en una sola línea cortada a mitad
    de palabra. Al mostrarse cada aviso, si su texto no cabe, se parte en líneas y la ventana crece hasta que se lee."""

    def eventFilter(self, objeto, evento):
        if evento.type() == QEvent.Show and isinstance(objeto, QMessageBox):
            QTimer.singleShot(0, lambda: que_quepa(objeto))  # después de que Qt calcule su tamaño
        return False


def que_quepa(caja: QMessageBox):
    etiqueta = caja.findChild(QLabel, "qt_msgbox_label")
    if etiqueta is None or not etiqueta.text():
        return
    medidas = etiqueta.fontMetrics()
    ancho_texto = max(medidas.horizontalAdvance(linea) for linea in etiqueta.text().splitlines() or [""])
    alto_necesario = etiqueta.heightForWidth(etiqueta.width()) if etiqueta.wordWrap() else etiqueta.height()
    if (not etiqueta.wordWrap() and ancho_texto <= etiqueta.contentsRect().width()) or \
            (etiqueta.wordWrap() and alto_necesario <= etiqueta.height()):
        return  # se lee entero
    etiqueta.setWordWrap(False)
    entero = etiqueta.sizeHint().width()  # lo que Qt mide para el renglón entero, con el relleno
    etiqueta.setWordWrap(True)
    # Un ancho mínimo y no uno fijo: Qt vuelve a medir el aviso (updateSize) con el ancho mínimo de la etiqueta y, si
    # le cabía en la ventana, le quitaba el salto de línea y quedaba cortado otra vez (pasó al animar una imagen)
    etiqueta.setMinimumWidth(min(max(etiqueta.width(), entero), 520))
    caja.setMinimumSize(0, 0)
    caja.setMaximumSize(16777215, 16777215)
    caja.setFixedSize(caja.sizeHint().expandedTo(QSize(caja.width(), 0)))


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


def resplandor(w, color="#7C5CFF", alfa=130, radio=24, bajada=4):
    """El halo de color bajo una pieza de vidrio (QSS no tiene box-shadow). Cuesta al pintar y un widget solo admite
    uno: va en el botón principal, nunca en listas (la opción elegida de Segmentos lleva su luz pintada)."""
    luz = QGraphicsDropShadowEffect(w)  # con padre: sin él, Python lo borra y el halo desaparece
    c = QColor(color)
    c.setAlpha(alfa)
    luz.setColor(c)
    luz.setBlurRadius(radio)
    luz.setOffset(0, bajada)
    w.setGraphicsEffect(luz)


class _Halo(QObject):
    """El halo del botón principal, solo si está activo (con un trabajo en marcha parecería que se puede pulsar) y si
    su padre le deja sitio: un widget no pinta fuera de su padre y el halo saldría cortado en seco. Por eso no lo
    llevan los de las barras de Diseño («Diseñar», «Exportar»: barras de 30-38 px), a propósito. Con el ratón encima
    se aviva, para que se note que se puede pulsar."""
    SITIO = 16  # px libres alrededor que necesita el halo de boton()
    ALFA, ALFA_ENCIMA = 130, 200

    def eventFilter(self, b, e):
        if e.type() in (QEvent.Enter, QEvent.Leave) and b.graphicsEffect():
            c = b.graphicsEffect().color()
            c.setAlpha(self.ALFA_ENCIMA if e.type() == QEvent.Enter else self.ALFA)
            b.graphicsEffect().setColor(c)
        elif e.type() in (QEvent.EnabledChange, QEvent.Show, QEvent.Move, QEvent.Resize) and b.graphicsEffect():
            padre, s = b.parentWidget(), self.SITIO
            # ponytail: se mira al moverse o cambiar de tamaño el botón; si solo encoge el padre, no se vuelve a mirar
            cabe = padre is not None and padre.rect().adjusted(s, s // 2, -s, -s).contains(b.geometry())
            b.graphicsEffect().setEnabled(b.isEnabled() and cabe)
        return False


_HALO = _Halo()


class _NombreAccesible(QObject):
    """Un botón que solo lleva un icono o un símbolo (↶, ↷, 📁) toma el nombre de su ayuda para el lector de pantalla:
    sin esto decía «↶» o «carpeta abierta»."""
    def eventFilter(self, b, e):
        if e.type() == QEvent.ToolTipChange and not any(c.isalpha() for c in b.text()):
            b.setAccessibleName(b.toolTip().split(" (")[0])  # «Deshacer (Ctrl+Z)» → «Deshacer»
        return False


_ACCESIBLE = _NombreAccesible()


def boton(texto, nombre="secundario"):
    """Botón con estilo. Si el texto empieza por un emoji conocido («📂  Abrir»), sale un icono de línea en su lugar."""
    b = QPushButton()
    b.installEventFilter(_ACCESIBLE)
    b.setObjectName(nombre)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.TabFocus)  # el anillo del foco, solo con el teclado: un clic no lo deja puesto sobre el vidrio
    b.setIconSize(QSize(22, 22) if nombre == "nav" else QSize(18, 18))
    poner(b, texto, "#FFFFFF" if nombre == "principal" else COLOR)
    if nombre == "principal":
        resplandor(b, "#B04BC8", _Halo.ALFA, 24, 5)  # el violeta y el rosa del degradado, mezclados
        b.installEventFilter(_HALO)
    return b


def tarjeta():
    f = QFrame()
    f.setObjectName("tarjeta")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 20, 20, 20)
    lay.setSpacing(12)
    return f, lay


class Rotulo(QWidget):
    """El rótulo fino en mayúsculas, con el degradado de la marca (violeta, rosa, cian), que va sobre el título de una
    sección, como en Pollo AI. QSS no pinta texto en degradado: se dibuja aquí."""
    def __init__(self, texto: str):
        super().__init__()
        self.texto = texto.upper()
        self.setAccessibleName(texto)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def letra(self) -> QFont:
        # La hoja de estilo de la app pisa setFont: la letra se arma al pintar
        f = QFont(self.font())
        f.setPixelSize(15)
        f.setWeight(QFont.Normal)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3.5)
        return f

    def sizeHint(self):
        m = QFontMetrics(self.letra())
        return QSize(m.horizontalAdvance(self.texto) + 4, m.height() + 2)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.letra())
        ancho = p.fontMetrics().horizontalAdvance(self.texto)
        degradado = QLinearGradient(0, 0, max(ancho, 1), 0)
        for donde, color in ((0, "#C2AEFF"), (0.55, "#FF6FA3"), (1, "#5CF6FF")):
            degradado.setColorAt(donde, QColor(color))
        p.setPen(QPen(QBrush(degradado), 1))
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self.texto)


def seccion(rotulo: str, titulo: str, *extras) -> QWidget:
    """La cabecera de una sección: el rótulo en degradado, debajo su título en negrita (#seccion) y, a la derecha, sus
    botones o casillas."""
    caja = QWidget()
    fila = QHBoxLayout(caja)
    fila.setContentsMargins(0, 0, 0, 0)
    fila.setSpacing(12)
    textos = QVBoxLayout()
    textos.setSpacing(4)
    textos.addWidget(Rotulo(rotulo))
    textos.addWidget(etiqueta(titulo, "seccion"))
    fila.addLayout(textos, 1)
    if extras:  # juntos y centrados entre sí (una casilla es más baja que un botón), y el grupo, abajo
        derecha = QWidget()
        botones = QHBoxLayout(derecha)
        botones.setContentsMargins(0, 0, 0, 0)
        botones.setSpacing(12)
        for w in extras:
            botones.addWidget(w, 0, Qt.AlignVCenter)
        fila.addWidget(derecha, 0, Qt.AlignBottom)
    return caja


class Segmentos(QWidget):
    """Un grupo de opciones como UNA pieza de vidrio: la cápsula (#segmentos) con la elegida en relieve y, debajo de
    ella, la luz de la marca, que se ve a través del vidrio y se derrama bajo la cápsula. Se pinta aquí, en el padre
    de la cápsula, con margen abajo: QSS no tiene box-shadow y un widget no puede pintar fuera de su padre."""
    LUZ = 12  # px bajo la cápsula por los que se derrama la luz (la elipse se apaga justo antes del borde)

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)  # si sobra alto, no se estira la cápsula
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, self.LUZ)
        self.capsula = QFrame()
        self.capsula.setObjectName("segmentos")
        self.capsula.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.fila = QHBoxLayout(self.capsula)
        self.fila.setContentsMargins(4, 4, 4, 4)
        self.fila.setSpacing(4)
        lay.addWidget(self.capsula)
        lay.addStretch()
        self.grupo = QButtonGroup(self)
        self.grupo.buttonToggled.connect(lambda *_: self.update())  # la luz sigue a la elegida, también desde el código

    def opcion(self, texto, id_=-1):
        b = QPushButton(texto)
        b.setObjectName("formato")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.TabFocus)  # como boton(): el anillo del foco, solo con el teclado
        self.grupo.addButton(b, id_)
        self.fila.addWidget(b)
        return b

    def paintEvent(self, e):
        b = self.grupo.checkedButton()
        if b is None or b.width() == 0:  # sin elegida o aún sin colocar: no hay luz que pintar
            return
        r = QRectF(b.geometry().translated(self.capsula.pos()))
        ancho, alto = r.width() * 0.62, self.height() - r.bottom() - 1  # alto: hasta el borde de abajo, sin cortarse
        luz = QRadialGradient(0, 0, ancho)
        luz.setColorAt(0, QColor(180, 140, 255, 235))
        luz.setColorAt(0.45, QColor(124, 92, 255, 125))
        luz.setColorAt(1, QColor(124, 92, 255, 0))
        p = QPainter(self)
        p.translate(r.center().x(), r.bottom())
        p.scale(1, alto / ancho)  # una elipse ancha y baja, centrada en el borde de abajo de la elegida
        p.fillRect(QRectF(-ancho, -ancho, 2 * ancho, 2 * ancho), luz)


class SelectorFormato(Segmentos):
    """Botones de formato como en CapCut."""
    def __init__(self):
        super().__init__()
        for clave, nombre in NOMBRES_FORMATO.items():
            b = self.opcion(nombre)
            b.setProperty("formato", clave)
            b.setChecked(clave == "9:16")

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


# La pastilla del selector de modelo: una cápsula de vidrio (#secundario) con la flecha de los desplegables de la app
PASTILLA = f"""
QPushButton {{ border-radius: 19px; padding: 8px 36px 8px 14px; }}
QPushButton::menu-indicator {{ image: url("{_ASSETS}/flecha-abajo.svg"); width: 12px; height: 12px;
                               subcontrol-origin: padding; subcontrol-position: center right; right: 14px; }}
"""


class SelectorModelo(QPushButton):
    """«Modelo de video», como en CapCut: una pastilla junto al pedido con el modelo que hará el video de ESTE trabajo.
    Primero Automático (lo de «Claves de IA», gratis primero), Sin animar y solo lo conectado, cada uno con su precio
    y, si su servicio no atiende, su último estado comprobado. Lo elegido se recuerda por página en ajustes.json (nunca
    cambia «Claves de IA»); si ese modelo ya no está conectado, vuelve a Automático."""
    cambio = Signal(str)
    ir_a_claves = None  # app.py: «Conectar más modelos…» abre «Claves de IA»

    def __init__(self, pagina: str):
        super().__init__()
        self.clave = f"modelo_video_{pagina}"
        self.setObjectName("secundario")
        self.setStyleSheet(PASTILLA)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)  # como boton(): el anillo del foco, solo con el teclado
        self.setIconSize(QSize(18, 18))
        self.setAccessibleName(t("Modelo de video"))
        self.setMenu(QMenu(self))
        self.menu().aboutToShow.connect(self.recargar)
        self.grupo = QActionGroup(self)
        self.grupo.triggered.connect(self._elegido)
        self.recargar()

    def valor(self) -> str:
        return self._valor

    def recargar(self):
        """Lo que hay ahora (una clave conectada o quitada, el cupo de Modal, un «sin saldo»): al abrir la lista y al
        volver a la página."""
        from ui.paginas.claves import ESTADOS  # aquí: esa página importa este módulo
        self.modelos = claves.modelos_video()
        guardado = claves.ajustes().get(self.clave, "auto")
        self._valor = guardado if guardado in [m["id"] for m in self.modelos] else "auto"
        menu = self.menu()
        menu.clear()
        for m in self.modelos:
            accion = menu.addAction(m["nombre"] + (f"  ·  {ESTADOS[m['estado']][0]}" if m["estado"] in ESTADOS else ""))
            accion.setCheckable(True)
            accion.setChecked(m["id"] == self._valor)
            accion.setData(m["id"])
            self.grupo.addAction(accion)
        if SelectorModelo.ir_a_claves:
            menu.addSeparator()
            menu.addAction(t("Conectar más modelos…")).triggered.connect(lambda: SelectorModelo.ir_a_claves())
        self._pintar()

    def _pintar(self):
        from ui.paginas.claves import ESTADOS
        m = next(m for m in self.modelos if m["id"] == self._valor)
        estado = ESTADOS[m["estado"]][0] if m["estado"] in ESTADOS else ""
        # En la pastilla, lo corto («Kling 3.0»); entero, en la lista y al pasar el ratón
        poner(self, f"🎬  {m['nombre'].split(' · ')[0].split(' (')[0]}" + (f" · {estado}" if estado else ""))
        self.setToolTip(t("Modelo de video de este trabajo: {modelo}", modelo=m["nombre"])
                        + (f" · {estado}" if estado else ""))

    def _elegido(self, accion):
        self._valor = accion.data()
        claves.elegir_por_defecto(self.clave, self._valor)
        self._pintar()  # la lista se rehace al abrirla otra vez: no dentro de la señal de una de sus acciones
        self.cambio.emit(self._valor)

    def showEvent(self, e):
        self.recargar()
        super().showEvent(e)


def resumen_avisos(avisos: list[str], maximo: int = 5) -> str:
    """Avisos cortos y sin direcciones web largas, para que quepan en pantalla (el detalle está en proyecto.json)."""
    lineas = [f"⚠️ {re.sub(r'https?://\S+', '…', a)[:220]}" for a in avisos[:maximo]]
    if len(avisos) > maximo:
        lineas.append(t("… y más avisos ({n}), todos en la carpeta del proyecto.", n=len(avisos) - maximo))
    return "\n".join(lineas)


def carpeta_para(sufijo: str) -> Path:
    """La carpeta del usuario para ese tipo de archivo: Videos, Imágenes o Música; lo demás, Descargas."""
    sufijo = sufijo.lower()
    lugar = (QStandardPaths.MoviesLocation if sufijo in seguro.VIDEOS else  # antes que AUDIOS: un .mp4 es video
             QStandardPaths.PicturesLocation if sufijo in seguro.IMAGENES else
             QStandardPaths.MusicLocation if sufijo in seguro.AUDIOS else QStandardPaths.DownloadLocation)
    return Path(QStandardPaths.writableLocation(lugar)
                or QStandardPaths.writableLocation(QStandardPaths.DownloadLocation))


def nombre_libre(carpeta: Path, nombre: str, sufijo: str) -> Path:
    """<carpeta>/<nombre><sufijo> sin pisar otro: «<nombre> (2)<sufijo>»… El nombre, sin lo que Windows no admite."""
    limpio = re.sub(r'[\\/:*?"<>|\s]+', " ", nombre).strip(" .")[:80] or "Ráfaga Studio"
    ruta, n = Path(carpeta) / f"{limpio}{sufijo}", 2
    while ruta.exists():
        ruta, n = Path(carpeta) / f"{limpio} ({n}){sufijo}", n + 1
    return ruta


def se_puede_abrir(ruta) -> bool:
    """Si su carpeta se puede enseñar: un ejemplo vive entre los archivos del programa (ejemplos/, assets/) y ahí no
    se manda a nadie a borrar; lo del usuario (datos/ o fuera del programa), sí."""
    raiz, ruta = guardia.RAIZ.resolve(), Path(ruta).resolve()
    return not ruta.is_relative_to(raiz) or ruta.is_relative_to(raiz / "datos")


def aviso_guardado(padre, titulo: str, ruta):
    """Dónde quedó lo que se acaba de guardar, con «Abrir carpeta»: nada se guarda sin que el usuario sepa dónde."""
    ruta = Path(ruta)
    carpeta = ruta if ruta.is_dir() else ruta.parent
    return mensaje(padre, titulo, t("Guardado en {carpeta}", carpeta=ruta),
                   botones=[(t("Abrir carpeta"), lambda: os.startfile(carpeta))])


def _guardar_imagen(origen: Path, destino: Path, jpg: bool) -> bool:
    imagen = QImage(str(origen))
    if jpg and imagen.hasAlphaChannel():  # el JPG no tiene transparencia: salía negra
        opaca = QImage(imagen.size(), QImage.Format_RGB32)
        opaca.fill(Qt.white)
        pintor = QPainter(opaca)
        pintor.drawImage(0, 0, imagen)
        pintor.end()
        imagen = opaca
    return imagen.save(str(destino), "JPG" if jpg else "PNG", 95)  # la calidad solo cuenta en JPG


def descargar(padre, archivo, titulo: str = "") -> Path | None:
    """«Descargar»: una copia del resultado donde elija el usuario. Por defecto en Videos, Imágenes, Música o Descargas
    según el tipo y con un nombre libre; nunca pisa otro archivo sin preguntar. Una imagen, en PNG o JPG. Al acabar,
    dónde quedó y «Abrir carpeta». Devuelve la copia, o None si se canceló o no se pudo."""
    origen = Path(archivo)
    sufijo = origen.suffix.lower()
    imagen = sufijo in seguro.IMAGENES
    validos = (".png", ".jpg", ".jpeg") if imagen else (sufijo,)
    if seguro.es_ruta_de_red(str(origen)):  # leerlo ya conectaría por SMB con ese servidor
        mensaje_error(padre, t("No se pudo descargar"), t(
            "{que}: tiene que ser un archivo de este PC, no de una carpeta de red (cópialo a tu PC o ábrelo desde una "
            "unidad con letra, como Z:): {ruta}", que=t("archivo").capitalize(), ruta=origen))
        return None
    sugerido = nombre_libre(carpeta_para(sufijo), titulo or origen.stem, validos[0])
    filtro = "PNG (*.png);;JPG (*.jpg *.jpeg)" if imagen else f"{sufijo[1:].upper()} (*{sufijo})"
    ruta, _ = QFileDialog.getSaveFileName(padre, t("Descargar"), str(sugerido), filtro)  # pregunta antes de pisar
    if not ruta:
        return None
    destino = Path(ruta)
    if destino.suffix.lower() not in validos:  # sin extensión o con otra: la suya, y por esa el diálogo no preguntó
        destino = destino.with_name(destino.name + validos[0])
        pregunta = t("Ya hay un archivo «{nombre}» en esa carpeta. ¿Reemplazarlo?", nombre=destino.name)
        if destino.exists() and QMessageBox.question(padre, t("Reemplazar archivo"), pregunta) != QMessageBox.Yes:
            return None
    # A un archivo aparte y luego en su sitio: si falla a medias (disco lleno), el que había no se pierde
    parcial = destino.with_name(destino.name + ".parcial")
    QGuiApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        # ponytail: se copia en el hilo de la ventana (un video de cientos de MB la para unos segundos); si molesta,
        # a una Tarea
        listo = _guardar_imagen(origen, parcial, destino.suffix.lower() != ".png") if imagen else \
            shutil.copyfile(origen, parcial)
        if listo:
            os.replace(parcial, destino)
    except OSError:
        listo = False
    finally:
        QGuiApplication.restoreOverrideCursor()
    if not listo:
        parcial.unlink(missing_ok=True)
        mensaje_error(padre, t("No se pudo descargar"), t("No se pudo guardar en {ruta}.", ruta=destino))
        return None
    aviso_guardado(padre, t("Descargado"), destino)
    return destino


class AccionesResultado(QWidget):
    """Lo que se hace con un resultado, igual en cada sección que crea archivos: «Descargar» una copia donde se quiera
    y, a la vista, «Guardado en: <carpeta>» con «Abrir carpeta». Antes unas secciones no tenían «Descargar» y nadie
    sabía en qué carpeta quedaba lo hecho."""

    def __init__(self, estilo: str = "principal"):
        """estilo: «secundario» donde lo hecho es un paso intermedio (la toma de la Cabina) y la acción principal
        es otra: tres botones de color en una tarjeta no dejan ver cuál toca."""
        super().__init__()
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        self.descargar = boton(f"⬇  {t('Descargar')}", estilo)
        self.descargar.setToolTip(t("Guardar una copia donde quieras"))
        self.descargar.clicked.connect(lambda: descargar(self, self.archivo, self.titulo))
        self.donde = etiqueta("", "sub")
        self.donde.setTextInteractionFlags(Qt.TextSelectableByMouse)  # la ruta se puede copiar
        self.abrir = boton(f"📂  {t('Abrir carpeta')}")
        self.abrir.clicked.connect(lambda: os.startfile(self.carpeta))
        fila.addWidget(self.descargar)
        fila.addWidget(self.donde, 1)
        fila.addWidget(self.abrir)
        self.archivo, self.titulo, self.carpeta = None, "", None
        self.hide()

    def mostrar(self, archivo=None, titulo: str = "", carpeta=None):
        """archivo: lo que copia «Descargar» (su carpeta es la que se enseña). Sin archivo, solo la carpeta."""
        self.archivo, self.titulo = archivo and Path(archivo), titulo
        self.carpeta = Path(carpeta) if carpeta else self.archivo.parent
        visible = se_puede_abrir(self.carpeta)
        self.donde.setText(t("Guardado en: {carpeta}", carpeta=self.carpeta) if visible else "")
        self.abrir.setVisible(visible)
        self.descargar.setVisible(self.archivo is not None)
        self.show()


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
        copiar = boton(t("Copiar texto para publicar"))
        copiar.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.info.toPlainText()))
        # Descargar y dónde quedó, justo bajo la lista: debajo del video quedaban fuera de la vista al terminar
        self.acciones = AccionesResultado()
        self.editar = boton(f"✂️  {t('Editar')}")
        self.editar.setToolTip(t("Abrir este resultado en el editor de video"))
        self.editar.clicked.connect(self._editar)
        self.editar.setVisible(Reproductor.al_editar is not None)
        self.formato = "9:16"
        fila = QHBoxLayout()
        for w in (self.play, self.editar, copiar):
            fila.addWidget(w)
        fila.addStretch()
        lay.addWidget(etiqueta(t("Resultados"), "sub"))
        lay.addWidget(self.lista)
        lay.addWidget(self.acciones)
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
        self.lista.blockSignals(True)  # al vaciarse pasa por filas de antes, que no existen en los resultados nuevos
        self.lista.clear()
        self.lista.blockSignals(False)
        for i, r in enumerate(self.resultados, 1):
            extra = f"  ·  {r['fin'] - r['inicio']:.0f}s  ·  {r['puntuacion']}/100" if "puntuacion" in r else ""
            # t(): la Cabina guarda sus títulos en español; los demás (de la IA o del usuario) quedan igual
            self.lista.addItem(QListWidgetItem(f"{i}. {t(r['titulo'])}{extra}"))
        if self.resultados:
            self.lista.setCurrentRow(0)
        else:
            self.acciones.hide()

    def _elegir(self, fila):
        if fila < 0:
            return
        r = self.resultados[fila]
        self.acciones.mostrar(r["archivo"], t(r["titulo"]))  # cada short, anuncio o canción, el suyo
        self.player.setSource(QUrl.fromLocalFile(r["archivo"]))
        # sin_markdown: los proyectos de antes guardan la descripción con el Markdown de la IA
        titulo, descripcion = ia.sin_markdown(t(r["titulo"]), "linea"), ia.sin_markdown(r["descripcion"])
        self.info.setPlainText(f"{titulo}\n\n{descripcion}\n\n" + " ".join(map(ia.hashtag, r["hashtags"])))
        self.player.play()
        poner(self.play, f"⏸  {t('Pausar')}")

    def _alternar(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            poner(self.play, f"▶  {t('Reproducir')}")
        else:
            self.player.play()
            poner(self.play, f"⏸  {t('Pausar')}")

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
        # Lo que hay que saber antes de que empiece (un servicio sin saldo y cuál lo hace en su lugar): se queda a la
        # vista mientras trabaja, no se lo lleva el siguiente aviso de progreso
        self.antes = etiqueta("")
        self.antes.setStyleSheet("color: #FFB454;")
        self.antes.hide()
        self.lay.addWidget(self.antes)
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
        # Una canción o un video pueden tardar minutos sin avisar nada nuevo: el reloj enseña que sigue trabajando.
        self.reloj = QTimer(self, interval=1000)
        self.reloj.timeout.connect(self._contar)
        self._texto, self._inicio = "", 0.0

    def _avanzar(self, texto, fraccion):
        self._texto = texto
        self.progreso.setValue(int(fraccion * 100))
        self._contar()

    def _contar(self):
        s = round(time.monotonic() - self._inicio)  # el temporizador salta unos ms antes: int() iba un segundo atrás
        self.estado.setText(f"{self._texto}  {s // 60}:{s % 60:02d}".strip())

    def _ver_estado(self):  # el progreso va debajo de todas las tarjetas: en un portátil quedaba fuera de la vista
        area = self.parentWidget()
        while area and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area:
            area.ensureWidgetVisible(self.estado)

    @staticmethod
    def _herramienta(funcion) -> str | None:
        """La herramienta del Director que hace lo mismo que `funcion`: de ella se sabe qué IA usa (director.usos)."""
        from motor import anuncios, musica, serie, shorts, video_musical
        return {desde_prompt.generar: "crear_video", anuncios.crear: "crear_anuncios", musica.crear: "crear_cancion",
                serie.crear_serie: "crear_serie", serie.crear_episodio: "crear_episodio", shorts.generar: "sacar_shorts",
                video_musical.crear: "crear_video_musical"}.get(funcion)

    def _pagar_video(self, funcion, datos) -> bool:
        """Si el trabajo usa video de pago (escenas que hablan, o Kling o Seedance para animar, elegidos en Claves de
        IA), lo pregunta antes con lo más que puede costar, todo en una sola pregunta. True si se puede seguir."""
        from motor import director, ia, serie
        pago = ia.video_de_pago()
        unico = funcion in (desde_prompt.animar_imagen, serie.rehacer_plano)  # un solo clip
        nombre = self._herramienta(funcion)  # las que no animan escenas (canción, shorts…) cuentan 0 clips
        clips = (1 if unico else director.clips(nombre, datos)) if pago and (unico or nombre) else 0
        mudos = clips * ia.precio_video(pago) if clips else 0.0
        if funcion is desde_prompt.generar and datos.get("animado") is True:  # escenas que hablan (de pago)
            escenas, costo = desde_prompt.costo_hablado(datos.get("segundos", 45))
            quien = ia.nombre_video(desde_prompt.proveedor_voz() or "gemini")
            titulo = t("Video animado con voz")
            if clips:  # el clip mudo de las que no salgan con voz, por lo alto: una sola cifra, como el Director
                texto = t("Escenas animadas con voz en {proveedor}: {n}. Las que no salgan con voz se animarán con "
                          "{video}: hasta unos {costo} en total según sus precios. ¿Seguir?",
                          n=escenas, proveedor=quien, video=ia.nombre_video(pago), costo=dinero(costo + mudos))
            else:
                texto = t("Escenas animadas con voz en {proveedor}: {n}, hasta unos {costo} según su precio. ¿Seguir?",
                          n=escenas, proveedor=quien, costo=dinero(costo))
        elif clips:
            titulo, texto = t("IA de video de pago"), t(
                "Escenas que se animarán con {proveedor}: hasta {n}, por unos {costo} como mucho según su precio. "
                "¿Seguir?", n=clips, proveedor=ia.nombre_video(pago), costo=dinero(mudos))
        else:
            return True
        if guardia.bloqueado():  # Ráfaga Guardia bloqueó el estudio: ningún video de pago empieza
            mensaje_error(self, t("Ráfaga Guardia"), guardia.mensaje_bloqueo())
            return False
        return QMessageBox.question(self, titulo, texto) == QMessageBox.Yes

    def lanzar(self, boton_iniciar, funcion, *, modelo_video=None, **datos) -> bool:
        """False si ya hay un trabajo en marcha (soltar un hilo que corre tumba la app cuando termina) o si el usuario
        no aceptó lo que cuesta. modelo_video: el del selector «Modelo de video», solo para este trabajo (también en
        lo que se comprueba y se pregunta antes)."""
        if self.tarea and self.tarea.isRunning():
            mensaje(self, t("Estoy trabajando"), t("Espera a que termine el trabajo actual."))
            return False
        # Con lo último comprobado de cada servicio (Claves de IA): lo de pago que no puede salir ni empieza (ni se
        # pregunta su costo) y lo que pasará a otro servicio se dice antes
        from motor import director
        usos = director.usos(nombre, datos) if (nombre := self._herramienta(funcion)) else []
        with claves.por_trabajo(modelo_video):
            # Animar solo la imagen no es una herramienta (usos vacío) pero sí anima: el modelo elegido sin saldo, se
            # dice. antes_de, con usos: el «zoom suave» de las escenas no aplica a un solo clip
            if no_se_puede := claves.impide(usos or (["video"] if funcion is desde_prompt.animar_imagen else [])):
                mensaje_error(self, t("No se puede empezar"), no_se_puede)
                return False
            if not self._pagar_video(funcion, datos):
                return False
            avisos = claves.antes_de(usos)
        self.antes.setText("\n".join(f"⚠️ {a}" for a in avisos))
        self.antes.setVisible(bool(avisos))
        boton_iniciar.setEnabled(False)
        self.progreso.show()
        self.progreso.setValue(0)
        self.tarea = Tarea(funcion, **datos)
        self.tarea.modelo_video = modelo_video
        self._texto, self._inicio = "", time.monotonic()
        self.tarea.progreso.connect(self._avanzar)
        for fin in (self.tarea.listo, self.tarea.fallo):  # lo primero: el reloj no pisa lo que se escriba al acabar
            fin.connect(self.reloj.stop)
        self.tarea.listo.connect(lambda p: (self.reproductor.show(), self.reproductor.mostrar(p), p.get("avisos") and
                                            mensaje(self, t("Terminado con avisos"),
                                                                    resumen_avisos(p["avisos"]))))
        self.tarea.fallo.connect(lambda e: (self.estado.setText(""), mensaje_error(self, t("No se pudo terminar"), e)))
        self.tarea.finished.connect(lambda: (boton_iniciar.setEnabled(True), self.progreso.hide()))
        self.reloj.start()
        self.tarea.start()
        QTimer.singleShot(0, self._ver_estado)  # cuando la barra ya ocupa su sitio
        return True


class VisorImagen(QDialog):
    """Una imagen o un diseño en grande (un ejemplo, lo que hizo el Director), con lo que se hace con ella: descargarla,
    editarla en Diseño, animarla y ver su carpeta. Antes solo tenía «Cerrar» y no había cómo bajarla."""
    # Los pone app.py, como Reproductor.al_editar (las páginas no se conocen): al_disenar(ruta) la abre en Diseño y
    # al_animar(ruta) la deja en Crear con IA. Sin ellos (p. ej. en una prueba), esos dos botones no salen
    al_disenar = None
    al_animar = None

    def __init__(self, padre, ruta, titulo: str):
        super().__init__(padre)
        self.ruta = Path(ruta)
        self.setWindowTitle(titulo)
        self.setAttribute(Qt.WA_DeleteOnClose)  # al cerrarla se libera
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        imagen = QLabel()
        # Con sus botones debajo, cabe en la pantalla (1280×720 al 150 %): a 720 px de alto la ventana se salía
        pantalla = (padre.screen() if padre else QGuiApplication.primaryScreen()).availableGeometry()
        caja = QSize(min(960, pantalla.width() - 80), min(720, pantalla.height() - 190))
        imagen.setPixmap(QPixmap(str(ruta)).scaled(caja, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        imagen.setAlignment(Qt.AlignCenter)
        lay.addWidget(imagen)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        self.descargar = boton(f"⬇  {t('Descargar')}", "principal")
        self.descargar.setToolTip(t("Guardar una copia en PNG o JPG donde quieras (Ctrl+S)"))
        self.descargar.setShortcut(QKeySequence.Save)
        self.descargar.setDefault(True)  # Intro descarga
        self.descargar.clicked.connect(lambda: descargar(self, self.ruta, self.windowTitle()))
        self.disenar = boton(f"🎨  {t('Editar en Diseño')}")
        # Un diseño guardado se abre con sus capas; una imagen suelta (un ejemplo) entra entera en uno nuevo
        self.disenar.setToolTip(t("Cambiar sus textos, colores y capas en la página Diseño")
                                if (self.ruta.parent / "diseno.json").is_file()
                                else t("Ponerla en un diseño nuevo para añadirle textos y formas"))
        self.disenar.clicked.connect(lambda: self._llevar(VisorImagen.al_disenar, titulo))
        self.animar = boton(f"🎬  {t('Animar')}")
        self.animar.setToolTip(t("Convertirla en un clip de video en Crear con IA (antes de empezar ves lo que cuesta)"))
        self.animar.clicked.connect(lambda: self._llevar(VisorImagen.al_animar))
        carpeta, cerrar = boton(f"📂  {t('Abrir carpeta')}"), boton(t("Cerrar"))
        carpeta.clicked.connect(lambda: os.startfile(self.ruta.parent))
        cerrar.clicked.connect(self.accept)
        for b in (self.descargar, self.disenar, self.animar, carpeta):
            fila.addWidget(b)
        fila.addStretch()
        fila.addWidget(cerrar)
        lay.addLayout(fila)
        self.disenar.setVisible(VisorImagen.al_disenar is not None)  # por la clase: si no, Python la ataría a self
        self.animar.setVisible(VisorImagen.al_animar is not None)
        carpeta.setVisible(se_puede_abrir(self.ruta))

    def _llevar(self, a_donde, *datos):
        """A otra página de la app (que no empieza nada sola): se cierra para que se vea."""
        self.accept()
        a_donde(str(self.ruta), *datos)


def ver_imagen(padre, ruta, titulo: str):
    """Una imagen en grande, en el visor de la app (VisorImagen), sin bloquear: la app sigue viva detrás."""
    ventana = VisorImagen(padre, ruta, titulo)
    ventana.open()
    return ventana


def ver_video(padre, proyecto: dict):
    """Un video (un ejemplo de la galería o uno reciente) en su ventana, con el reproductor de la app y sonido: se ve
    donde se pulsó, sin bajar la página. Al cerrarla, se para y se libera."""
    from PySide6.QtWidgets import QDialog
    ventana = QDialog(padre)
    ventana.setWindowTitle(t(proyecto["resultados"][0]["titulo"]) or "Ráfaga Studio")
    ventana.setAttribute(Qt.WA_DeleteOnClose)
    lay = QVBoxLayout(ventana)
    lay.setContentsMargins(12, 12, 12, 12)
    ventana.reproductor = Reproductor()
    ventana.reproductor.lista.setVisible(len(proyecto["resultados"]) > 1)  # con uno solo, la lista sobra
    # Con «Descargar» y «Guardado en» (dos líneas si la ruta es larga) no cabía en 1280×720 con la barra de tareas
    ventana.reproductor.pantalla.setMinimumHeight(300)
    lay.addWidget(ventana.reproductor)
    ventana.reproductor.mostrar(proyecto)
    ventana.finished.connect(ventana.reproductor.player.stop)
    ventana.resize(900, 640)  # cabe en 1280×720 con la barra de tareas
    ventana.open()
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
