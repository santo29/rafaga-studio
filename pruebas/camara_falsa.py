"""Cámara, micrófono y grabador simulados para «Grabarte» (ui/grabarte.py): las pruebas y las capturas de pantalla
NUNCA abren la cámara ni el micrófono de este PC. usar() los pone en el panel; el grabador simulado «graba» al parar un
video generado con ffmpeg (lavfi: una cara de colores y un tono), o solo el tono si es una toma de voz."""
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QMediaRecorder

from motor import video

GRABANDO, PARADO = QMediaRecorder.RecorderState.RecordingState, QMediaRecorder.RecorderState.StoppedState


class Dispositivo:
    def __init__(self, nombre: str, id_: bytes, defecto: bool = False):
        self.nombre, self.id_, self.defecto = nombre, id_, defecto

    def description(self):
        return self.nombre

    def id(self):
        return self.id_

    def isDefault(self):
        return self.defecto

    def videoFormats(self):
        return []


class Dispositivos(QObject):
    videoInputsChanged, audioInputsChanged = Signal(), Signal()
    camaras = [Dispositivo("Cámara de prueba", b"camara-1", True)]
    micros = [Dispositivo("Micrófono de prueba", b"micro-1", True)]
    vivos = []  # las instancias que creó el panel: por ellas se avisa de que algo se enchufó o se quitó

    def __init__(self, *_):
        super().__init__()
        Dispositivos.vivos.append(self)

    @staticmethod
    def videoInputs():
        return list(Dispositivos.camaras)

    @staticmethod
    def audioInputs():
        return list(Dispositivos.micros)

    @classmethod
    def cambio(cls, camaras=None, micros=None):
        """Enchufa o quita: las listas nuevas y el aviso, como Windows."""
        if camaras is not None:
            cls.camaras = camaras
        if micros is not None:
            cls.micros = micros
        for d in cls.vivos:
            d.videoInputsChanged.emit()
            d.audioInputsChanged.emit()


class Camara(QObject):
    errorOccurred, activeChanged = Signal(object, str), Signal(bool)
    creadas = []

    def __init__(self, dispositivo, *_):
        super().__init__()
        self.dispositivo, self.activa, self.formato = dispositivo, False, None
        Camara.creadas.append(self)

    def start(self):
        self.activa = True
        self.activeChanged.emit(True)

    def stop(self):
        self.activa = False
        self.activeChanged.emit(False)

    def setCameraFormat(self, formato):
        self.formato = formato

    def errorString(self):
        return ""


class Microfono(QObject):
    creados = []

    def __init__(self, *_):
        super().__init__()
        self.dispositivo = None
        Microfono.creados.append(self)

    def setDevice(self, dispositivo):
        self.dispositivo = dispositivo


class Sesion(QObject):
    def __init__(self, *_):
        super().__init__()
        self.camara = self.micro = self.grabador = self.salida = None

    def setCamera(self, camara):
        self.camara = camara

    def setAudioInput(self, micro):
        self.micro = micro

    def setRecorder(self, grabador):
        self.grabador = grabador

    def setVideoOutput(self, salida):
        self.salida = salida


class Grabador(QObject):
    recorderStateChanged, errorOccurred = Signal(object), Signal(object, str)
    creados = []
    segundos = 2  # lo que dura lo «grabado»
    fallo = None  # (error, texto) con el que falla record(), sin llegar a grabar
    responde = True  # False: stop() no avisa nunca (un grabador colgado)

    def __init__(self, *_):
        super().__init__()
        self.estado, self.salida, self.formato, self.calidad = PARADO, QUrl(), None, None
        Grabador.creados.append(self)

    def setMediaFormat(self, formato):
        self.formato = formato

    def setQuality(self, calidad):
        self.calidad = calidad

    def setOutputLocation(self, url):
        self.salida = url

    def actualLocation(self):
        return self.salida

    def recorderState(self):
        return self.estado

    def duration(self):
        return self.segundos * 1000 if self.estado == GRABANDO else 0

    def errorString(self):
        return (Grabador.fallo or (None, ""))[1]

    def record(self):
        if Grabador.fallo:
            return self.errorOccurred.emit(*Grabador.fallo)
        self.estado = GRABANDO
        self.recorderStateChanged.emit(GRABANDO)

    def stop(self):
        if self.estado != GRABANDO:
            return
        destino = Path(self.salida.toLocalFile())
        s = self.segundos
        if destino.suffix == ".m4a":
            video.ffmpeg("-f", "lavfi", "-i", f"sine=frequency=300:duration={s}", "-c:a", "aac", destino)
        else:  # una «cara»: un círculo de color sobre fondo, que se mueve, con un tono
            video.ffmpeg("-f", "lavfi", "-i", f"testsrc2=s=320x180:r=30:d={s}", "-f", "lavfi", "-i",
                         f"sine=frequency=300:duration={s}", "-c:v", "libx264", "-preset", "ultrafast",
                         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", destino)
        self.estado = PARADO
        if self.responde:
            self.recorderStateChanged.emit(PARADO)


def usar() -> None:
    """El panel Grabarte con todo esto en vez de la cámara y el micrófono de verdad."""
    from ui.grabarte import PanelGrabarte
    PanelGrabarte.Camara, PanelGrabarte.Microfono, PanelGrabarte.Sesion = Camara, Microfono, Sesion
    PanelGrabarte.Grabador, PanelGrabarte.Dispositivos = Grabador, Dispositivos
