"""La luz del asistente de voz: colores que dan la vuelta al borde de la ventana mientras escucha, piensa o habla,
como si la voz recorriera el estudio entero. Late con tu voz. No tapa nada ni recibe clics."""
import math
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QPainter, QPen, QRegion
from PySide6.QtWidgets import QWidget

COLORES = {
    "escuchando": ("#00E5FF", "#2979FF", "#7C5CFF", "#00FFC6", "#00E5FF"),
    "pensando": ("#7C5CFF", "#FF4D8D", "#FFB454", "#7C5CFF"),
    "hablando": ("#FF4D8D", "#FFB454", "#00E5FF", "#7C5CFF", "#FF4D8D"),
}
GROSOR = 30  # lo más ancho del halo: solo esa franja se vuelve a pintar en cada cuadro


class Brillo(QWidget):
    def __init__(self, ventana: QWidget):
        super().__init__(ventana)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.estado, self.angulo, self.nivel, self.fuerza, self.apagando = None, 0.0, 0.0, 0.0, True
        self.reloj = QTimer(self)
        self.reloj.setInterval(33)  # ~30 cuadros por segundo
        self.reloj.timeout.connect(self._paso)
        ventana.installEventFilter(self)
        self.setGeometry(ventana.rect())
        self.hide()

    def eventFilter(self, objeto, evento):
        if evento.type() == QEvent.Resize:
            self.setGeometry(objeto.rect())
        return False

    def poner(self, estado: str | None) -> None:
        """«escuchando», «pensando», «hablando» o None (se apaga suave)."""
        self.apagando = estado not in COLORES
        if not self.apagando:
            self.estado = estado
            self.show()
            self.raise_()
        self.reloj.start()

    def oir(self, nivel: float) -> None:
        """El volumen de la voz (0..1): el halo crece con él."""
        self.nivel = max(self.nivel, min(max(float(nivel), 0.0), 1.0))

    def _paso(self):
        self.angulo = (self.angulo - 4) % 360  # gira en el sentido de las agujas del reloj
        self.fuerza += ((0.0 if self.apagando else 1.0) - self.fuerza) * 0.15
        self.nivel *= 0.85  # sube con la voz al instante y baja suave
        if self.estado == "hablando":  # la voz del Director no se mide: late a ritmo de habla
            self.nivel = max(self.nivel, 0.35 + 0.3 * abs(math.sin(time.monotonic() * 7)))
        if self.apagando and self.fuerza < 0.02:
            self.reloj.stop()
            self.estado = None
            self.hide()
            return
        borde = QRegion(self.rect())
        self.update(borde.subtracted(QRegion(self.rect().adjusted(GROSOR, GROSOR, -GROSOR, -GROSOR))))

    def paintEvent(self, _):
        if not self.estado:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        degradado = QConicalGradient(QPointF(self.width() / 2, self.height() / 2), self.angulo)
        colores = COLORES[self.estado]
        for i, color in enumerate(colores):
            degradado.setColorAt(i / (len(colores) - 1), QColor(color))
        energia = 0.55 + 0.45 * self.nivel
        for ancho, opacidad in ((GROSOR, 0.08), (20, 0.14), (12, 0.25), (6, 0.5), (2.5, 1.0)):  # halo de fuera adentro
            ancho *= energia if ancho > 3 else 1
            p.setOpacity(opacidad * self.fuerza)
            p.setPen(QPen(QBrush(degradado), ancho))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(ancho / 2, ancho / 2, -ancho / 2, -ancho / 2), 12, 12)
