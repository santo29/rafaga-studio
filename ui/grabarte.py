"""Panel «🎥 Grabarte» del editor de video: grábate hablando encima del video (tu cara en una esquina, a pantalla
completa o en media pantalla) o solo tu voz, mientras el video suena desde el cursor; o importa una grabación de tu
cara. La toma entra en el cursor (una capa de video o un audio «voz»), en un solo «deshacer».

Privacidad: la cámara y el micrófono se usan solo en este PC, solo con este panel abierto y solo cuando tú los
enciendes o grabas (el micrófono, solo mientras grabas). Al cambiar de herramienta o de página se apagan; si estabas
grabando, se para y se guarda lo grabado. Las tomas van a grabaciones/ dentro de la carpeta del proyecto.

Estados (self.estado): "apagada" → (Encender) "vista" → (Grabar) "preparando" (el editor monta la vista previa del
video desde el cursor) → "cuenta" (3, 2, 1) → "grabando" → (Detener, un error, el disco casi lleno, el final de los 60
minutos, la cámara o el micro desenchufados, salir del panel) "guardando" → la toma se le entrega a la página y vuelve
a "vista" (o a "apagada" en solo voz).

Las piezas de Qt Multimedia salen de los atributos de la clase (Camara, Microfono, Sesion, Grabador, Dispositivos): las
pruebas las cambian por unas simuladas. Construir el panel no abre la cámara ni el micrófono (listar los dispositivos,
sí: Windows no los enciende por eso)."""
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QRectF, QSize, QSizeF, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QTransform
from PySide6.QtMultimedia import (QAudioInput, QCamera, QMediaCaptureSession, QMediaDevices, QMediaFormat,
                                  QMediaRecorder)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGraphicsScene, QGraphicsView,
                               QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget)

from motor import edicion, seguro, video
from motor.idioma import t
from ui import iconos
from ui.comun import Segmentos, boton, etiqueta, mensaje, mensaje_error

LIBRE_MINIMO, LIBRE_PARAR = 500 * 1024 ** 2, 200 * 1024 ** 2  # bytes libres para empezar a grabar y para seguir
CUENTA = 3  # segundos de la cuenta atrás
VISTA = QSize(246, 138)  # la vista de la cámara (16:9): cabe en la tarjeta de herramientas con su barra de desplazar
ICONOS_FORMA = {"circulo": "circle", "redondeado": "squircle", "rectangulo": "square"}
ESTILO_PANEL = ("#grabarte #segmentos #formato { padding: 6px 9px; } "
                "#disposicion { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 4px; "
                "background: rgba(255, 255, 255, 0.04); color: #B4B4C0; font-size: 11px; } "
                "#disposicion:hover { border-color: rgba(150, 125, 255, 0.45); color: #FFFFFF; } "
                "#disposicion:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                "stop:0 rgba(150, 125, 255, 0.42), stop:1 rgba(124, 92, 255, 0.20)); "
                "border-color: rgba(150, 125, 255, 0.70); color: #FFFFFF; } "
                "#grabando { color: #FF4D8D; font-weight: 700; }")
_CONSENTIMIENTO = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def permiso_denegado(que: str) -> bool:
    """Si la privacidad de Windows no deja usar la cámara (que="webcam") o el micrófono ("microphone") a esta app: el
    interruptor del equipo (HKLM), el de las apps y el de las apps de escritorio (HKCU). Solo lee el registro; si no
    se puede leer (u otro sistema), False: si de verdad está bloqueado, lo dice el error de la cámara."""
    try:
        import winreg
    except ImportError:
        return False
    for raiz, ruta in ((winreg.HKEY_LOCAL_MACHINE, que), (winreg.HKEY_CURRENT_USER, que),
                       (winreg.HKEY_CURRENT_USER, que + r"\NonPackaged")):
        try:
            with winreg.OpenKey(raiz, f"{_CONSENTIMIENTO}\\{ruta}") as clave:
                if str(winreg.QueryValueEx(clave, "Value")[0]).strip().lower() == "deny":
                    return True
        except OSError:
            continue
    return False


def aviso_privacidad(que: str) -> str:
    """Dónde se activa en Windows lo que falta (que: "webcam" o "microphone"). Windows 10 llama de otra forma a la
    página y a sus interruptores que Windows 11 (compilación 22000 o más)."""
    win10 = sys.platform == "win32" and sys.getwindowsversion().build < 22000
    if que == "webcam" and win10:
        return t("Windows no deja a Ráfaga Studio usar la cámara. Actívala en Configuración → Privacidad → Cámara "
                 "(«Permitir el acceso a la cámara en este dispositivo» y «Permitir que las aplicaciones de escritorio "
                 "accedan a la cámara») y vuelve a intentarlo.")
    if win10:
        return t("Windows no deja a Ráfaga Studio usar el micrófono. Actívalo en Configuración → Privacidad → Micrófono "
                 "(«Permitir el acceso al micrófono en este dispositivo» y «Permitir que las aplicaciones de escritorio "
                 "accedan al micrófono») y vuelve a intentarlo.")
    if que == "webcam":
        return t("Windows no deja a Ráfaga Studio usar la cámara. Actívala en Configuración → Privacidad y seguridad → "
                 "Cámara («Acceso a la cámara» y «Permitir que las aplicaciones de escritorio accedan a la cámara») y "
                 "vuelve a intentarlo.")
    return t("Windows no deja a Ráfaga Studio usar el micrófono. Actívalo en Configuración → Privacidad y seguridad → "
             "Micrófono («Acceso al micrófono» y «Permitir que las aplicaciones de escritorio accedan al micrófono») "
             "y vuelve a intentarlo.")


def _es_permiso(texto: str) -> bool:
    """Si un error de la cámara o del grabador suena a permiso denegado (E_ACCESSDENIED de Windows)."""
    texto = str(texto).lower()
    return any(p in texto for p in ("denied", "permission", "privacy", "0x80070005", "acceso", "access is"))


def _libre(carpeta: Path) -> int:
    try:
        return shutil.disk_usage(carpeta).free
    except OSError:
        return 0


def _tamano(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GB" if n >= 1024 ** 3 else f"{n / 1024 ** 2:.0f} MB"


class _Rotulo(QLabel):
    """El texto de una casilla, en varias líneas si no cabe; pulsarlo la marca o desmarca, como el de QCheckBox."""
    def __init__(self, texto, casilla):
        super().__init__(texto)
        self.casilla = casilla
        self.setWordWrap(True)
        self.setTextFormat(Qt.PlainText)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if self.casilla.isEnabled():
            self.casilla.toggle()


def casilla(texto: str) -> tuple[QWidget, QCheckBox]:
    """(fila, casilla): el texto de QCheckBox no se parte en líneas y en francés no cabría en el panel."""
    fila, caja = QWidget(), QCheckBox()
    caja.setAccessibleName(texto)  # el lector de pantalla la nombra aunque su texto vaya aparte
    lay = QHBoxLayout(fila)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(caja, 0, Qt.AlignTop)
    lay.addWidget(_Rotulo(texto, caja), 1)
    return fila, caja


def icono_disposicion(formato: str, cual: str, forma: str) -> QIcon:
    """La miniatura de una disposición: el cuadro del video (de su formato) y dónde va tu cara, en violeta."""
    lado = 56
    ancho, alto = video.FORMATOS[formato]
    k = (lado - 4) / max(ancho, alto)
    marco = QRectF((lado - ancho * k) / 2, (lado - alto * k) / 2, ancho * k, alto * k)
    caja = edicion.disposicion(formato, cual, forma if cual not in ("completa", "dividida") else "rectangulo")
    pip = QRectF(marco.x() + caja["x"] * k, marco.y() + caja["y"] * k, caja["ancho"] * k, caja["alto"] * k)
    imagen = QPixmap(lado, lado)
    imagen.fill(Qt.transparent)
    p = QPainter(imagen)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.setBrush(QColor("#1C1C24"))
    p.drawRoundedRect(marco, 3, 3)
    luz = QLinearGradient(pip.topLeft(), pip.bottomRight())
    luz.setColorAt(0, QColor("#9A80FF"))
    luz.setColorAt(1, QColor("#FF4D8D"))
    p.setPen(Qt.NoPen)
    p.fillPath(edicion.forma_video(caja["forma"], pip), luz)
    p.end()
    return QIcon(imagen)


class PanelGrabarte(QWidget):
    """El panel de la herramienta «Grabarte». `pagina` es la del editor (ui/paginas/edicion.PaginaEdicion): le pide la
    carpeta, el cursor, montar y reproducir el video mientras grabas, y le entrega cada toma (toma_lista)."""
    Camara, Microfono, Sesion, Grabador, Dispositivos = QCamera, QAudioInput, QMediaCaptureSession, QMediaRecorder, \
        QMediaDevices
    ESPERA = 10_000  # ms que espera al cerrar la app a que el grabador cierre el archivo

    def __init__(self, pagina):
        super().__init__()
        # _forma: la de las esquinas (círculo, redondeada o recta); pantalla completa y dividida van siempre rectas
        self.pagina, self.estado, self._formato, self._forma, self._dibujadas = pagina, "apagada", None, "circulo", None
        self.sesion = self.camara = self.micro = self.grabador = None
        self._ruta, self._inicio, self._previa, self._cuenta, self._empezo = None, 0.0, None, 0, 0.0
        self._apagar_luego, self._esperando, self._despertar = False, False, None
        # _retraso: lo grabado antes de que arrancara el video del editor (None: aún no se sabe), que la toma no usa.
        # _pedido: el testigo del último «Grabar» (el montaje de un intento cancelado no vale para el siguiente).
        # _elegida: hay una capa de video elegida (los mosaicos y la forma la cambian a ella)
        self._retraso, self._pedido, self._elegida = 0.0, None, False
        self.setObjectName("grabarte")
        self.setStyleSheet(ESTILO_PANEL)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(8)
        self.modo = Segmentos()
        for i, texto in enumerate((t("Cámara y voz"), t("Solo voz"))):
            self.modo.opcion(texto, i).setChecked(i == 0)
        self.modo.grupo.idClicked.connect(self._al_cambiar_modo)
        self.camaras, self.micros = QComboBox(), QComboBox()
        self.camaras.setToolTip(t("Cámara"))
        self.micros.setToolTip(t("Micrófono"))
        for combo in (self.camaras, self.micros):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10)
        self.camaras.currentIndexChanged.connect(self._otra_camara)
        self.dispositivos = self.Dispositivos()
        self.dispositivos.videoInputsChanged.connect(self._cambio_dispositivos)
        self.dispositivos.audioInputsChanged.connect(self._cambio_dispositivos)
        self._llenar()
        lay.addWidget(self.modo)
        lay.addWidget(self.camaras)
        lay.addWidget(self.micros)
        lay.addWidget(self._vista())
        self.grabar_btn, self.encender_btn = boton(f"🔴  {t('Grabar')}", "principal"), \
            boton(f"📷  {t('Encender cámara')}")
        self.grabar_btn.clicked.connect(self.grabar)
        self.grabar_btn.setToolTip(t("Cuenta 3, 2, 1 y graba mientras el video suena desde el cursor"))
        self.encender_btn.clicked.connect(self.encender)
        self.tiempo = etiqueta("", "grabando")
        self.tiempo.hide()
        silenciar, self.silenciar = casilla(t("Silenciar el video mientras grabas"))
        self.silenciar.setChecked(True)
        bajar, self.bajar = casilla(t("Bajar la música cuando hablas"))
        self.bajar.setChecked(True)
        self.bajar.toggled.connect(lambda v: self.pagina.poner_bajar_musica(v))
        # Lo de cada toma (grabar y dónde va tu cara) arriba, a la vista; las casillas de una vez, al final
        for w in (self.tiempo, self.grabar_btn, self.encender_btn, etiqueta(t("Dónde va tu cara"), "sub")):
            lay.addWidget(w)
        # A qué va el clic: los mosaicos y las formas cambian la grabación elegida si hay una; si no, la próxima toma
        self.destino = etiqueta("", "sub")
        lay.addWidget(self.destino)
        lay.addWidget(self._disposiciones())
        self.forma = Segmentos()
        for i, (clave, nombre_icono) in enumerate(ICONOS_FORMA.items()):
            b = self.forma.opcion("", i)
            b.setIcon(iconos.icono(nombre_icono))
            b.setToolTip(edicion.FORMAS_VIDEO[clave])
            b.setAccessibleName(edicion.FORMAS_VIDEO[clave])  # solo lleva icono: el lector de pantalla dice cuál es
            b.setChecked(clave == "circulo")
        self.forma.grupo.idClicked.connect(self._elegir_forma)
        lay.addWidget(self.forma)
        self.importar_btn = boton(f"📥  {t('Importar grabación')}")
        self.importar_btn.setToolTip(t("Un video de tu cara que ya tengas: entra en el cursor con la disposición "
                                       "elegida"))
        self.importar_btn.clicked.connect(self.importar)
        for w in (self.importar_btn, silenciar,
                  etiqueta(t("Usa auriculares si quieres oír el video mientras hablas: así no hay eco."), "sub"),
                  bajar):
            lay.addWidget(w)
        lay.addWidget(etiqueta(t("La cámara y el micrófono se usan solo en tu PC y solo con este panel abierto. Tus "
                                 "grabaciones se guardan en la carpeta del proyecto (grabaciones)."), "sub"))
        lay.addStretch()
        self._reloj = QTimer(self)
        self._reloj.setInterval(1000)
        self._reloj.timeout.connect(self._tic)
        self._plazo = QTimer(self)  # un grabador que no confirma el cierre no deja el panel colgado en «guardando»
        self._plazo.setSingleShot(True)
        self._plazo.timeout.connect(self._terminar)
        self.marcar(None, pagina.proyecto)

    # ---------- Construcción ----------

    def _vista(self):
        """La imagen de la cámara (en espejo, como un espejo de verdad; lo grabado va derecho) con la cuenta atrás
        encima. Apagada, un aviso."""
        self.escena = QGraphicsScene(self)
        self.escena.setSceneRect(QRectF(0, 0, VISTA.width(), VISTA.height()))
        self.escena.setBackgroundBrush(QColor("#0B0B0F"))
        self.imagen = QGraphicsVideoItem()
        self.imagen.setSize(QSizeF(VISTA))
        self.imagen.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
        self.imagen.setTransform(QTransform.fromScale(-1, 1).translate(-VISTA.width(), 0))
        self.escena.addItem(self.imagen)
        self.apagada = self.escena.addText("")
        self.apagada.setDefaultTextColor(QColor("#8D8D9A"))
        self.apagada.setTextWidth(VISTA.width() - 24)
        self.numero = self.escena.addSimpleText("")
        letra = QFont(self.font())
        letra.setPixelSize(72)
        letra.setBold(True)
        self.numero.setFont(letra)
        self.numero.setBrush(QColor("#FFFFFF"))
        self.numero.setPen(QPen(QColor("#7C5CFF"), 2))
        self.ver = QGraphicsView(self.escena)
        self.ver.setFixedSize(VISTA + QSize(2, 2))
        self.ver.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ver.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ver.setFrameShape(QFrame.NoFrame)
        self.ver.setRenderHint(QPainter.Antialiasing)
        return self.ver

    def _disposiciones(self):
        """Las seis disposiciones, en miniatura: un clic la aplica a la grabación elegida (o a la próxima toma)."""
        caja = QWidget()
        rejilla = QGridLayout(caja)
        rejilla.setContentsMargins(0, 0, 0, 0)
        rejilla.setSpacing(6)
        self.tiles = {}
        cortos = {"completa": t("Completa"), "dividida": t("Dividida")}
        for i, cual in enumerate(("sup_izq", "sup_der", "completa", "inf_izq", "inf_der", "dividida")):
            b = self.tiles[cual] = QToolButton()
            b.setObjectName("disposicion")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(44, 44))
            b.setText(cortos.get(cual, ""))
            b.setToolTip(edicion.DISPOSICIONES[cual])
            b.setAccessibleName(edicion.DISPOSICIONES[cual])  # las esquinas no llevan texto: sin esto, «botón» a secas
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumSize(78, 66)
            b.clicked.connect(lambda _=False, c=cual: self.pagina.aplicar_disposicion(c, self._forma))
            rejilla.addWidget(b, i // 3, i % 3)
        self.tiles["inf_der"].setChecked(True)
        self.mosaicos = caja
        return caja

    def _llenar(self):
        """Las cámaras y los micrófonos de este PC (listarlos no los enciende), sin perder los elegidos."""
        for combo, lista, nada in ((self.camaras, self.Dispositivos.videoInputs(), t("No hay ninguna cámara")),
                                   (self.micros, self.Dispositivos.audioInputs(), t("No hay ningún micrófono"))):
            antes = combo.currentData().id() if combo.currentData() is not None else None
            combo.blockSignals(True)
            combo.clear()
            for d in lista:
                combo.addItem(d.description(), d)
            if not lista:
                combo.addItem(nada, None)
            ids = [d.id() for d in lista]
            defecto = next((i for i, d in enumerate(lista) if d.isDefault()), 0)
            combo.setCurrentIndex(ids.index(antes) if antes in ids else defecto)
            combo.setEnabled(bool(lista))
            combo.blockSignals(False)

    # ---------- Lo que usa la página ----------

    def disposicion(self) -> tuple[str, str]:
        """(disposición, forma de las esquinas) elegidas: las de la próxima toma."""
        return next((c for c, b in self.tiles.items() if b.isChecked()), "inf_der"), self._forma

    def _elegir_forma(self, i):
        self._forma = list(ICONOS_FORMA)[i]
        self._dibujar()
        self.pagina.aplicar_forma(self._forma)

    def _dibujar(self):
        """Las miniaturas de las disposiciones, en el formato del video y con la forma de las esquinas."""
        if (self._formato, self._forma) != self._dibujadas:
            self._dibujadas = self._formato, self._forma
            for cual, b in self.tiles.items():
                b.setIcon(icono_disposicion(self._formato, cual, self._forma))

    def marcar(self, capa: dict | None, proyecto: dict) -> None:
        """Enseña lo del proyecto: las miniaturas en su formato, la disposición y la forma de la capa de video elegida
        (si lo es) y «Bajar la música». No cambia nada del proyecto."""
        self._formato, self._elegida = proyecto["formato"], capa is not None
        self.destino.setText(t("Cambia la grabación elegida") if capa is not None else t("Para tu próxima grabación"))
        self.destino.setToolTip(t("Haz clic en el fondo del video para soltarla: entonces vale para tu próxima "
                                  "grabación.") if capa is not None else "")
        if capa is not None:
            igual = [c for c in self.tiles if all(capa[k] == edicion.disposicion(
                proyecto["formato"], c, capa["forma"], capa["borde"])[k] for k in ("x", "y", "ancho", "alto"))]
            if igual:
                self.tiles[igual[0]].setChecked(True)
            if not set(igual) & {"completa", "dividida"}:  # esas van rectas siempre: no cambian la de las esquinas
                self._forma = capa["forma"]
            self.forma.grupo.button(list(ICONOS_FORMA).index(capa["forma"])).setChecked(True)
        self._dibujar()
        self.bajar.blockSignals(True)
        self.bajar.setChecked(proyecto["bajar_musica"])
        self.bajar.blockSignals(False)
        self._pintar_estado()  # en solo voz, los mosaicos se activan solo con una grabación elegida

    def ocupado(self) -> bool:
        return self.estado in ("preparando", "cuenta", "grabando", "guardando")

    def apagar(self, esperar: bool = False) -> None:
        """Al salir del panel o de la página y al cerrar: la cámara y el micrófono se apagan. Si estabas grabando, se
        para y se guarda la toma; esperar=True (al cerrar la app): espera aquí a que el archivo quede cerrado y la toma
        entra en el video antes de seguir."""
        if self.estado in ("preparando", "cuenta"):
            self._cancelar()
        if self.estado in ("grabando", "guardando"):
            self._apagar_luego, self._esperando = True, esperar or self._esperando
            if self.estado == "grabando":
                self.detener()
            elif self.camara is not None:  # ya guardando («Detener» y luego saliste): la cámara se apaga ya igual
                self._soltar_camara()
                self._pintar_estado()
            if esperar and self.estado == "guardando":
                bucle = QEventLoop()
                self._despertar = bucle.quit
                QTimer.singleShot(self.ESPERA, bucle.quit)  # un grabador que no contesta no deja la app sin cerrar
                bucle.exec()
                self._despertar = None
            return
        self._apagar_camara()

    # ---------- Cámara ----------

    def encender(self) -> bool:
        """«Encender cámara» (o «Apagar» si ya está encendida). True si queda encendida."""
        if self.estado == "vista":
            self._apagar_camara()
            return False
        if self.estado != "apagada":
            return self.camara is not None
        dispositivo = self.camaras.currentData()
        if dispositivo is None:
            mensaje_error(self, t("Sin cámara"), t("No encuentro ninguna cámara. Conecta una (o revisa que esté "
                                                   "activada) o elige «Solo voz»."))
            return False
        if permiso_denegado("webcam"):
            mensaje_error(self, t("Permiso de cámara"), aviso_privacidad("webcam"))
            return False
        self._sesion()
        self.camara = self.Camara(dispositivo)
        formatos = [f for f in dispositivo.videoFormats()
                    if f.maxFrameRate() >= 24 and 0 < f.resolution().height() <= 1080]
        if formatos:  # cerca de 720p a 30 fps: buena cara sin cargar el PC del usuario
            self.camara.setCameraFormat(min(formatos, key=lambda f: (abs(f.resolution().height() - 720),
                                                                      abs(f.maxFrameRate() - 30))))
        self.camara.errorOccurred.connect(self._error_camara)
        self.sesion.setCamera(self.camara)
        self.camara.start()
        self.estado = "vista"
        self._pintar_estado()
        return True

    def _sesion(self):
        if self.sesion is None:
            self.sesion = self.Sesion(self)
            self.sesion.setVideoOutput(self.imagen)

    def _apagar_camara(self):
        if self.ocupado():
            return
        self._soltar_camara()
        self.estado = "apagada"
        self._pintar_estado()

    def _soltar_camara(self):
        if self.camara is not None:
            camara, self.camara = self.camara, None
            camara.stop()
            if self.sesion is not None:
                self.sesion.setCamera(None)
            camara.deleteLater()

    def _otra_camara(self):
        if self.estado == "vista":  # otra cámara elegida con la vista encendida: se cambia
            self._apagar_camara()
            self.encender()

    def _error_camara(self, _error=None, texto=""):
        """La cámara falló: sin permiso, ocupada por otra app o desconectada. Si grababas, se guarda lo grabado."""
        detalle = texto or (self.camara.errorString() if self.camara is not None else "")
        if permiso_denegado("webcam") or _es_permiso(detalle):
            aviso = aviso_privacidad("webcam")
        else:  # el detalle de Windows o Qt viene en inglés: a la consola, no a la ventana
            print(f"Cámara: {detalle}", file=sys.stderr)
            aviso = t("No se pudo usar la cámara: puede que otra app la esté usando (Zoom, Teams, el navegador…) o que "
                      "se haya desconectado. Cierra esa app o vuelve a conectar la cámara y prueba otra vez.")
        if self.estado == "grabando":
            self._apagar_luego = True
            self.detener()
        elif self.estado in ("preparando", "cuenta"):
            self._cancelar()
        if not self.ocupado():
            self._apagar_camara()
        mensaje_error(self, t("Problema con la cámara"), aviso)

    def _cambio_dispositivos(self):
        """Se enchufó o desenchufó algo: las listas al día y, si lo que se usaba ya no está, se para (y se guarda)."""
        en_uso = {d.id() for d, usado in ((self.camaras.currentData(), self.camara is not None),
                                          (self.micros.currentData(), self.micro is not None))
                  if usado and d is not None}
        self._llenar()
        self._pintar_estado()
        quedan = {d.id() for d in (*self.Dispositivos.videoInputs(), *self.Dispositivos.audioInputs())}
        if en_uso <= quedan:
            return
        if self.estado == "grabando":
            self._apagar_luego = True
            self.detener()
            mensaje_error(self, t("Se desconectó"), t("Se desconectó la cámara o el micrófono: paré la grabación y "
                                                       "guardé lo grabado hasta ahora."))
        else:
            if self.estado in ("preparando", "cuenta"):
                self._cancelar()
            self._apagar_camara()

    def _al_cambiar_modo(self, _i):
        if self.ocupado():
            return
        if self._solo_voz():
            self._apagar_camara()
        self._pintar_estado()

    def _solo_voz(self) -> bool:
        return self.modo.grupo.checkedId() == 1

    # ---------- Grabar ----------

    def grabar(self):
        """«Grabar»: comprueba todo, enciende la cámara si hace falta, monta el video desde el cursor, cuenta 3, 2, 1 y
        graba. Pulsado otra vez («Detener»), para."""
        if self.ocupado():
            return self.detener()
        if self.micros.currentData() is None and self._solo_voz():
            return mensaje_error(self, t("Sin micrófono"), t("No encuentro ningún micrófono. Conecta uno para grabar "
                                                              "tu voz."))
        if self.micros.currentData() is not None and permiso_denegado("microphone"):
            return mensaje_error(self, t("Permiso de micrófono"), aviso_privacidad("microphone"))
        if self.pagina.cursor >= edicion.MAX_DURACION - 1:
            return mensaje_error(self, t("Sin sitio"), t("El cursor está al final de los {minutos} minutos del "
                                                          "video: muévelo antes de grabar.",
                                                          minutos=edicion.MAX_DURACION // 60))
        # Antes de encender nada: con el tope lleno la toma no entraría, y lo sabrías después de hablarla entera
        if not self._solo_voz() and sum(c["tipo"] == "video" for c in self.pagina.proyecto["capas"]) >= \
                edicion.MAX_VIDEOS:
            return mensaje_error(self, t("Sin sitio"), t("Este video ya tiene {n} grabaciones encima: borra una o "
                                                          "graba con «Solo voz».", n=edicion.MAX_VIDEOS))
        carpeta = self.pagina._carpeta() / "grabaciones"
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return mensaje_error(self, t("No se pudo grabar"), e)
        if _libre(carpeta) < LIBRE_MINIMO:
            return mensaje_error(self, t("Poco espacio"), t(
                "Queda poco espacio en el disco ({libre}): libera al menos {minimo} antes de grabar.",
                libre=_tamano(_libre(carpeta)), minimo=_tamano(LIBRE_MINIMO)))
        if not self._solo_voz() and self.estado == "apagada" and not self.encender():
            return
        if self.micros.currentData() is None:
            mensaje(self, t("Sin micrófono"), t("No encuentro ningún micrófono: se grabará tu imagen sin sonido."))
        self._ruta = carpeta / time.strftime(f"grabacion-%Y%m%d-%H%M%S.{'m4a' if self._solo_voz() else 'mp4'}")
        n = 1
        while self._ruta.exists():  # dos tomas en el mismo segundo
            n += 1
            self._ruta = self._ruta.with_stem(f"{self._ruta.stem.split('_')[0]}_{n}")
        # La toma va donde empieza el video que suena (el cursor de ahora, aunque se mueva mientras se monta).
        # Cada «Grabar» lleva su testigo: el montaje de un intento ya cancelado no vale para el siguiente
        self.estado, self._inicio, self._pedido = "preparando", self.pagina.cursor, object()
        self._pintar_estado()
        self.pagina.preparar_grabacion(lambda archivo, pedido=self._pedido: pedido is self._pedido
                                       and self._preparado(archivo))

    def _preparado(self, archivo):
        """El video desde el cursor ya está montado (None: no hay nada que reproducir; False: falló). Se abre ya en el
        reproductor del editor, quieto: al empezar a grabar solo falta darle a play."""
        if self.estado != "preparando":
            return  # se canceló mientras tanto
        if archivo is False:
            return self._cancelar()
        self._previa, self._cuenta = archivo, CUENTA
        if archivo:
            self.pagina.precargar(archivo)
        self.estado = "cuenta"
        self._pintar_estado()
        self._reloj.start()

    def _tic(self):
        if self.estado == "cuenta":
            self._cuenta -= 1
            if self._cuenta <= 0:
                return self._empezar()
            return self._pintar_estado()
        if self.estado != "grabando":
            return self._reloj.stop()
        pos = self.pagina.player.position()
        if self._retraso is None and pos >= 200:
            # El video del editor tarda en abrir y arrancar (más con el PC cargado): lo grabado antes sobra. Con el
            # reloj y no con grabador.duration(), que llega tarde (el codificador retiene fotogramas); el segundo 0 del
            # archivo cae a unas centésimas de _empezo
            self._retraso = max(0.0, time.monotonic() - self._empezo - pos / 1000)
        segundos = self._segundos()
        self._pintar_estado()
        if _libre(self._ruta.parent) < LIBRE_PARAR:
            self.detener()
            mensaje_error(self, t("Disco casi lleno"), t("El disco se está llenando: paré la grabación y guardé lo "
                                                          "grabado hasta ahora."))
        elif self._inicio + segundos >= edicion.MAX_DURACION - 1:
            self.detener()
            mensaje_error(self, t("Grabación parada"), t("La grabación llegó al final de los {minutos} minutos del "
                                                          "video: la paré y la guardé.",
                                                          minutos=edicion.MAX_DURACION // 60))

    def _segundos(self) -> float:
        ms = self.grabador.duration() if self.grabador is not None else 0
        return ms / 1000 if ms else (time.monotonic() - self._empezo if self._empezo else 0.0)

    def _empezar(self):
        """El fin de la cuenta atrás: el micrófono entra en la sesión y empieza la grabación (MPEG-4: H.264 + AAC; solo
        voz, .m4a). El video suena en cuanto el grabador de verdad graba (así tu voz y el video van a la par)."""
        self._sesion()
        dispositivo = self.micros.currentData()
        if dispositivo is not None:
            self.micro = self.Microfono(self)
            self.micro.setDevice(dispositivo)
            self.sesion.setAudioInput(self.micro)
        self.grabador = self.Grabador(self)
        formato = QMediaFormat(QMediaFormat.FileFormat.Mpeg4Audio)
        if not self._solo_voz():
            formato = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
            formato.setVideoCodec(QMediaFormat.VideoCodec.H264)
        formato.setAudioCodec(QMediaFormat.AudioCodec.AAC)
        self.grabador.setMediaFormat(formato)
        self.grabador.setQuality(QMediaRecorder.Quality.HighQuality)
        self.grabador.setOutputLocation(QUrl.fromLocalFile(str(self._ruta)))
        self.grabador.recorderStateChanged.connect(self._estado_grabador)
        self.grabador.errorOccurred.connect(self._error_grabador)
        self.sesion.setRecorder(self.grabador)
        self.estado, self._empezo, self._retraso = "grabando", 0.0, 0.0
        self._pintar_estado()
        self.grabador.record()

    def _estado_grabador(self, estado):
        if estado == QMediaRecorder.RecorderState.RecordingState and self.estado == "grabando" and not self._empezo:
            self._empezo = time.monotonic()
            self.pagina.reproducir_grabando(self._previa, self._inicio, self.silenciar.isChecked())
            self._retraso = None if self._previa else 0.0  # None: hasta que el video del editor arranque (_tic)
        elif estado == QMediaRecorder.RecorderState.StoppedState and self.estado in ("grabando", "guardando"):
            self._terminar()

    def _error_grabador(self, error=None, texto=""):
        detalle = texto or (self.grabador.errorString() if self.grabador is not None else "")
        usa = ("microphone",) if self._solo_voz() else ("webcam", "microphone")
        if error == QMediaRecorder.Error.OutOfSpaceError:
            aviso = t("El disco se llenó: guardé lo grabado hasta ahí. Libera espacio para seguir grabando.")
        elif error == QMediaRecorder.Error.LocationNotWritable:
            aviso = t("No puedo escribir en la carpeta del proyecto: revisa que no sea de solo lectura.")
        elif _es_permiso(detalle) or any(map(permiso_denegado, usa)):
            aviso = aviso_privacidad(next((q for q in usa if permiso_denegado(q)), usa[0]))
        else:
            aviso = t("La grabación falló: {detalle}", detalle=detalle or "—")
        if self.estado in ("grabando", "guardando"):
            if self.grabador is not None and self.grabador.recorderState() != QMediaRecorder.RecorderState.StoppedState:
                self.detener()
            else:
                self._terminar()
        mensaje_error(self, t("No se pudo grabar"), aviso)

    def detener(self):
        """«Detener»: para la grabación y el video (o cancela la cuenta atrás). La toma se entrega al quedar cerrada."""
        if self.estado in ("preparando", "cuenta"):
            return self._cancelar()
        if self.estado != "grabando":
            return
        self.estado = "guardando"
        self._pintar_estado()
        self.pagina.fin_grabacion()
        self._plazo.start(self.ESPERA)  # antes de stop(): puede avisar ahí mismo
        self.grabador.stop()
        if self._apagar_luego and self.estado == "guardando":
            # Saliste del panel o de la página: la cámara se apaga ya, sin esperar a que el archivo quede cerrado (tras
            # stop() el grabador ya no necesita sus fotogramas)
            self._soltar_camara()
            self._pintar_estado()

    def _cancelar(self):
        self._reloj.stop()
        self.estado = "vista" if self.camara is not None else "apagada"
        self.pagina.fin_grabacion()
        self._pintar_estado()

    def _terminar(self):
        """El grabador ya cerró el archivo (o no lo confirmó en ESPERA ms: _plazo): el micrófono sale de la sesión y la
        toma va al video (si grabó algo)."""
        if self.estado not in ("grabando", "guardando"):
            return
        self._reloj.stop()
        self._plazo.stop()
        self.pagina.fin_grabacion()
        grabador, self.grabador = self.grabador, None
        if self.sesion is not None:
            self.sesion.setRecorder(None)
            self.sesion.setAudioInput(None)
        if self.micro is not None:
            self.micro.deleteLater()
            self.micro = None
        ruta = Path(grabador.actualLocation().toLocalFile() or self._ruta) if grabador is not None else self._ruta
        if grabador is not None:  # lo que diga después ya no es de esta toma (ni de la siguiente)
            grabador.recorderStateChanged.disconnect(self._estado_grabador)
            grabador.errorOccurred.disconnect(self._error_grabador)
            # Uno que aún no confirmó el cierre se deja vivir (es hijo del panel): borrarlo a medias podría cortarlo
            if grabador.recorderState() == QMediaRecorder.RecorderState.StoppedState:
                grabador.deleteLater()
        self.estado = "vista" if self.camara is not None else "apagada"
        if self._apagar_luego:
            self._apagar_luego = False
            self._apagar_camara()
        self._pintar_estado()
        esperar, self._esperando = self._esperando, False
        try:
            hay = ruta.is_file() and ruta.stat().st_size > 0
        except OSError:
            hay = False
        if hay:
            self.pagina.toma_lista(str(ruta), self._inicio, en_hilo=not esperar, desde=self._retraso or 0.0)
        if self._despertar:
            self._despertar()

    # ---------- Importar ----------

    def importar(self):
        ruta = QFileDialog.getOpenFileName(
            self, t("Importar grabación"), QStandardPaths.writableLocation(QStandardPaths.MoviesLocation),
            t("Videos y audios ({extensiones})", extensiones=" ".join(
                f"*{e}" for e in sorted(seguro.VIDEOS | seguro.AUDIOS))))[0]
        if ruta:
            self.pagina.toma_lista(ruta, self.pagina.cursor)

    # ---------- Pintar el estado ----------

    def _pintar_estado(self):
        e, voz = self.estado, self._solo_voz()
        hay_camara = self.camaras.currentData() is not None
        self.encender_btn.setEnabled(e in ("apagada", "vista") and not voz and hay_camara)
        encendida = self.camara is not None  # también mientras cuenta o graba: el botón no dice «Encender» entonces
        iconos.poner(self.encender_btn, f"📷  {t('Apagar cámara') if encendida else t('Encender cámara')}")
        # Antes de grabar (montando el video o en la cuenta atrás) aún no se graba nada: «Cancelar», no «Detener»
        iconos.poner(self.grabar_btn, f"⏹  {t('Cancelar')}" if e in ("preparando", "cuenta") else
                     f"⏹  {t('Detener')}" if self.ocupado() else f"🔴  {t('Grabar')}", "#FFFFFF")
        self.grabar_btn.setEnabled(e != "guardando")
        for w in (self.modo, self.camaras, self.micros, self.importar_btn):
            w.setEnabled(not self.ocupado() and (w is not self.camaras or hay_camara and not voz)
                         and (w is not self.micros or self.micros.currentData() is not None))
        # En solo voz no hay cara que colocar: los mosaicos y la forma, solo para una grabación ya elegida
        for w in (self.mosaicos, self.forma):
            w.setEnabled(not voz or self._elegida)
        self.imagen.setVisible(self.camara is not None)
        textos = {"apagada": t("Solo voz: se grabará el micrófono.") if voz else
                  t("La cámara está apagada. Pulsa «Encender cámara» o «Grabar».") if hay_camara else
                  t("No encuentro ninguna cámara. Conecta una (o revisa que esté activada) o elige «Solo voz».")}
        self.apagada.setPlainText(textos.get(e, "") if self.camara is None else "")
        self.apagada.setPos(12, (VISTA.height() - self.apagada.boundingRect().height()) / 2)
        self.numero.setText(str(self._cuenta) if e == "cuenta" else "")
        caja = self.numero.boundingRect()
        self.numero.setPos((VISTA.width() - caja.width()) / 2, (VISTA.height() - caja.height()) / 2)
        if e == "grabando":
            s = int(self._segundos())
            self.tiempo.setText(f"● {t('Grabando')}  {s // 60}:{s % 60:02d}")
        elif e == "cuenta":
            self.tiempo.setText(t("Empieza en {n}…", n=self._cuenta))
        elif e == "guardando":
            self.tiempo.setText(t("Guardando la grabación…"))
        elif e == "preparando":  # aquí y no encima de la cámara, donde no se lee (el progreso, arriba en el editor)
            self.tiempo.setText(t("Preparando el video…"))
        self.tiempo.setVisible(e in ("grabando", "cuenta", "guardando", "preparando"))
