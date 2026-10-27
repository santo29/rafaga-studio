"""Página «Director IA»: pides el trabajo por escrito o con la voz y la IA usa todo el estudio para hacerlo.
Arriba, los ejemplos hechos con Ráfaga Studio (carpeta ejemplos/). Aquí vive también la galería de ejemplos que usan
el Director e Inicio: la pieza pintada con su video, el mosaico y la fila que se desplaza."""
import atexit
import html
import json
import threading
import traceback
from itertools import count, zip_longest
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QObject, QPropertyAnimation, QRect, QRectF, QSize, Qt, QThread, QThreadPool,
                            QTimer, QUrl, Signal, Slot)
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QImage, QImageReader, QKeySequence,
                           QLinearGradient, QMovie, QPainter, QPainterPath, QPen, QRadialGradient, QShortcut)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QScrollArea,
                               QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

from motor import claves, director, ia, idioma, memoria, roles, voz
from motor.idioma import t
from ui.comun import (boton, etiqueta, mensaje, mensaje_error, Reproductor, seccion, Segmentos, SelectorModelo, Tarea,
                      tarjeta, ver_imagen)
from ui.iconos import icono, poner

EJEMPLOS = Path(__file__).resolve().parent.parent.parent / "ejemplos"
# Piezas que se mueven a la vez en una página (GIF o el MP4 de la elegida del carrusel): cada una es un decodificador.
# ponytail: medido en un portátil de 4 hilos (3 GIF pequeños cuestan poco); en PCs potentes o con GPU se puede subir a 6
MAX_VIVAS = 3
# Las fotos se leen a lo más de este lado: una tarjeta del carrusel mide 1148 px al 150 % y con 720 se veían blandas.
# Todas las de los ejemplos juntas ocupan unos 40 MB
LADO = 1280
# En el carrusel y las herramientas, de un video se ve solo lo de arriba: sus subtítulos quemados van del 72 al 80 % del
# alto y quedaban debajo del título y los botones de la tarjeta (texto sobre texto)
RECORTE_SUBTITULOS = 0.68
_animar = None  # la casilla «Animar vistas previas», compartida por toda la app (ver accion_animar)
# Qué página usa cada herramienta (su nombre en el menú): la app la ilumina mientras el Director trabaja en ella
PAGINA = {"crear_video": "Crear con IA", "sacar_shorts": "Shorts mágicos", "crear_anuncios": "Anuncios",
          "crear_cancion": "Música", "crear_video_musical": "Música", "producir_cancion": "Cabina de grabación",
          "separar_voz_y_pista": "Cabina de grabación", "crear_diseno": "Diseño", "editar_video": "Editor de video",
          "investigar_nichos": "Nichos virales", "listar_proyectos": "Mis proyectos", "listar_opciones": "Claves de IA",
          "crear_serie": "Dibujos animados", "crear_episodio": "Dibujos animados", "listar_series": "Dibujos animados",
          "programar_publicacion": "Publicar", "recordar_preferencia": "Director IA"}
IMAGENES = (".png", ".jpg", ".jpeg")  # resultados que no son video: el reproductor no los enseña


def ejemplos() -> list[dict]:
    """Los ejemplos de ejemplos/ejemplos.json que tienen su video ({id}.mp4) y su miniatura ({id}.jpg)."""
    try:
        lista = json.loads((EJEMPLOS / "ejemplos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in lista if isinstance(e, dict) and (EJEMPLOS / f"{e.get('id')}.mp4").is_file()
            and (EJEMPLOS / f"{e.get('id')}.jpg").is_file()]


def disenos() -> list[dict]:
    """Los diseños de ejemplo de ejemplos/disenos.json que tienen su imagen (ver foto)."""
    try:
        lista = json.loads((EJEMPLOS / "disenos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in lista if isinstance(e, dict) and (ruta := foto(e)) and ruta.is_file()]


def foto(e: dict) -> Path | None:
    """La imagen fija de un ejemplo: ejemplos/{id}.jpg o, si la trae, «imagen», una ruta dentro de la app (Rafa, la
    mascota, vive en assets/ con su marca). Una ruta que se sale de la app no vale (None)."""
    if not e.get("imagen"):
        return EJEMPLOS / f"{e.get('id')}.jpg"
    raiz = EJEMPLOS.parent.resolve()
    ruta = (raiz / str(e["imagen"])).resolve()
    return ruta if ruta.is_relative_to(raiz) else None


def video(e: dict) -> Path:
    """El MP4 de un ejemplo: en otro idioma que no sea el español, su versión en inglés ({id}-en.mp4) si la hay."""
    ingles = EJEMPLOS / f"{e['id']}-en.mp4"
    return ingles if idioma.actual() != "es" and ingles.is_file() else EJEMPLOS / f"{e['id']}.mp4"


def proyecto_ejemplo(e: dict) -> dict:
    """Un video de ejemplo con los campos que espera el Reproductor."""
    guion = e.get("guion") or {}
    return {"formato": e.get("formato", "9:16"), "resultados": [{
        "archivo": str(video(e)), "titulo": str(e.get("titulo", "")),
        "descripcion": str(guion.get("descripcion", "")), "hashtags": list(guion.get("hashtags", []))}]}


def accion_animar() -> QAction:
    """Si las vistas previas se mueven (casilla «Animar vistas previas»; se apaga por accesibilidad o batería). Es una
    sola acción para toda la app: así las casillas de Inicio, del Director y de «Ver todo» dicen siempre lo mismo.
    Se guarda en ajustes.json."""
    global _animar
    if _animar is None:
        _animar = QAction(QApplication.instance())
        _animar.setCheckable(True)
        _animar.setChecked(claves.ajustes().get("animar_vistas") != "no")
        _animar.toggled.connect(lambda si: claves.elegir_por_defecto("animar_vistas", "si" if si else "no"))
    return _animar


def casilla_animar() -> QCheckBox:
    casilla = QCheckBox(t("Animar vistas previas"))
    casilla.setToolTip(t("Apágalo si prefieres menos movimiento o quieres ahorrar batería"))
    casilla.setChecked(accion_animar().isChecked())
    casilla.toggled.connect(accion_animar().setChecked)
    accion_animar().toggled.connect(casilla.setChecked)  # Qt lo desconecta solo cuando la casilla se destruye
    return casilla


_FOTOS: dict[str, QImage] = {}  # cada foto se lee una vez: la usan varias galerías a la vez (carrusel, mosaico…)
_PROPORCIONES: dict[str, float] = {}


def _leer(clave: str) -> QImage:
    lector = QImageReader(clave)
    lector.setAutoTransform(True)
    tam = lector.size()
    if tam.isValid() and max(tam.width(), tam.height()) > LADO:
        lector.setScaledSize(tam.scaled(LADO, LADO, Qt.KeepAspectRatio))
    return lector.read()


def _imagen(ruta) -> QImage:
    """La foto, leída una vez y reducida a LADO. Se lee en un hilo del pool (ver _hacer_capas), así Inicio abre rápido
    y nada se traba al aparecer una pieza. Rota o sin archivo, una QImage nula: sale el dibujo de relleno."""
    clave = str(ruta)
    imagen = _FOTOS.get(clave)
    if imagen is None:  # desde varios hilos a la vez: la primera que llega se queda
        imagen = _FOTOS.setdefault(clave, _leer(clave))
    return imagen


def _proporcion(ruta) -> float:
    """Ancho entre alto de la foto, leyendo solo su cabecera (16:9 si no se puede leer)."""
    clave = str(ruta)
    if clave not in _PROPORCIONES:
        tam = QImageReader(clave).size()
        _PROPORCIONES[clave] = tam.width() / tam.height() if tam.isValid() and tam.height() else 16 / 9
    return _PROPORCIONES[clave]


def _preparar(fuente: QImage, ancho: int, alto: int, alto_util: float = 1.0, radio: float = 0, dpr: float = 1,
              foco: float = 0.4, sombra: bool = False) -> QImage:
    """La imagen recortada para llenar ancho×alto (píxeles de pantalla) sin deformarse, ya a su tamaño y con las
    esquinas redondas: pintarla luego es copiarla, sin escalar ni recortar, y así el carrusel se desliza sin tirones.
    Con alto_util < 1 solo cuenta lo de arriba (deja fuera los subtítulos quemados de los videos). Si sobra alto, se
    corta según foco: 0 deja lo de arriba, 1 lo de abajo (0,4 por defecto: las caras suelen ir arriba). Con sombra,
    lleva ya el degradado oscuro de abajo (el de las tarjetas del carrusel): pintarlo en cada cuadro costaba otro
    milisegundo del hilo de la ventana. Vale en cualquier hilo."""
    if fuente.isNull() or ancho < 1 or alto < 1:
        return QImage()
    util = max(1.0, fuente.height() * alto_util)
    escala = max(ancho / fuente.width(), alto / util)
    w, h = min(fuente.width(), ancho / escala), min(util, alto / escala)
    recorte = QRect(round((fuente.width() - w) / 2), round((util - h) * foco), max(1, round(w)), max(1, round(h)))
    lista = fuente.copy(recorte).scaled(ancho, alto, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    salida = QImage(ancho, alto, QImage.Format_ARGB32_Premultiplied)
    salida.fill(Qt.transparent)
    p = QPainter(salida)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(lista))  # la foto como relleno de la forma redonda: los bordes salen suavizados
    p.drawRoundedRect(QRectF(0, 0, ancho, alto), radio, radio)
    if sombra:
        _sombra(p, QRectF(0, 0, ancho, alto), 110 * dpr)
    p.end()
    salida.setDevicePixelRatio(dpr)
    return salida


def _sombra(p: QPainter, r: QRectF, minimo: float, forma: QPainterPath | None = None):
    """El degradado oscuro de abajo, sobre el que van los textos. Sin forma, solo donde ya hay imagen (sus esquinas
    redondas siguen transparentes)."""
    alto = min(r.height(), max(minimo, r.height() * 0.62))
    sombra = QLinearGradient(0, r.bottom() - alto, 0, r.bottom())
    sombra.setColorAt(0, QColor(8, 8, 12, 0))
    sombra.setColorAt(0.5, QColor(8, 8, 12, 165))  # oscuro de verdad: los textos van encima
    sombra.setColorAt(1, QColor(8, 8, 12, 246))
    if forma is not None:
        p.fillPath(forma, sombra)
    else:
        p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        p.fillRect(QRectF(r.left(), r.bottom() - alto, r.width(), alto), sombra)


def _fondo(fija: QImage, ancho: int, alto: int, radio: float, caja: QRectF, dpr: float) -> QImage:
    """Lo de debajo de la foto que va entera (el carrusel, en píxeles de pantalla): la misma foto muy desenfocada,
    oscurecida, con la luz violeta y rosa de la marca detrás y una sombra suave. Así se lee como el vidrio de la app y
    no como una mancha marrón. Vale en cualquier hilo."""
    salida = QImage(ancho, alto, QImage.Format_ARGB32_Premultiplied)
    salida.fill(Qt.transparent)
    p = QPainter(salida)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    forma = QPainterPath()
    forma.addRoundedRect(QRectF(0.5, 0.5, ancho - 1, alto - 1), radio, radio)
    p.setClipPath(forma)
    p.fillRect(salida.rect(), QColor("#17171D"))
    if not fija.isNull():  # reducirla a 24 px y volver a agrandarla con suavizado: un desenfoque casi gratis
        borrosa = fija.scaledToWidth(24, Qt.SmoothTransformation).scaledToWidth(240, Qt.SmoothTransformation)
        p.drawImage(0, 0, _preparar(borrosa, ancho, alto))
    p.fillRect(salida.rect(), QColor(14, 11, 24, 205))
    luz = QRadialGradient(caja.center(), max(caja.width(), caja.height()) * 0.95)
    luz.setColorAt(0, QColor(124, 92, 255, 110))
    luz.setColorAt(0.55, QColor(255, 77, 141, 42))
    luz.setColorAt(1, QColor(124, 92, 255, 0))
    p.fillRect(salida.rect(), luz)
    for n in range(1, 7):  # sombra suave bajo la foto: QSS no tiene box-shadow
        sombra = QPainterPath()
        k = n * dpr
        sombra.addRoundedRect(caja.adjusted(-2 * k, -k + 2 * dpr, 2 * k, 3 * k), (12 + n) * dpr, (12 + n) * dpr)
        p.fillPath(sombra, QColor(0, 0, 0, 16))
    p.end()
    salida.setDevicePixelRatio(dpr)
    return salida


def _hacer_capas(numero, clave, ruta, ancho, alto, caja, alto_util, radio, radio_caja, dpr, foco, sombra):
    """En un hilo del pool: la foto lista para su sitio y, si va entera, su fondo. Leer y escalar una foto de 1080 px
    tarda 20-40 ms: en el hilo de la ventana trababa el carrusel cada vez que aparecía una pieza."""
    try:
        fija = _imagen(ruta)
        if caja is None:
            fondo, lista = QImage(), _preparar(fija, ancho, alto, alto_util, radio, dpr, foco, sombra)
        else:
            fondo = _fondo(fija, ancho, alto, radio, QRectF(caja), dpr)
            lista = _preparar(fija, caja.width(), caja.height(), alto_util, radio_caja, dpr, foco)
    except Exception:  # una foto rara: sale el dibujo de relleno, no tumba nada
        traceback.print_exc()
        fondo, lista = QImage(), QImage()
    _el_puente().capas.emit(numero, clave, fondo, lista)


class _Puente(QObject):
    """Trae al hilo de la ventana lo que se prepara en los hilos del pool: los cuadros de los MP4 y las capas de cada
    pieza. Las piezas van por su número (nunca se repite, a diferencia de id()): una ya borrada no recibe nada."""
    cuadro = Signal(object, int, QImage)  # (número de la pieza, su vuelta, el cuadro listo)
    capas = Signal(object, object, QImage, QImage)  # (número de la pieza, para qué tamaño, su fondo, su foto lista)

    @Slot(object, int, QImage)
    def recibir(self, numero, vuelta, imagen):
        b = _CON_VIDEO.get(numero)
        if b is not None and b.vuelta == vuelta:  # de una reproducción anterior (parada o reiniciada): no vale
            b.convirtiendo = False
            if not imagen.isNull():
                b.cuadro = imagen
                b.update(b.destino().toAlignedRect())  # solo su foto: el resto de la tarjeta no cambia

    @Slot(object, object, QImage, QImage)
    def recibir_capas(self, numero, clave, fondo, lista):
        b = _PIEZAS.get(numero)
        if b is not None and b._pedida == clave:
            b._pedida = None
            b._capas = (clave, fondo, lista)
            b.update()


_puente = None
_CON_VIDEO = {}  # número de la pieza → la pieza, mientras reproduce su MP4
_PIEZAS = {}  # número de la pieza → la pieza, mientras vive (se quita al borrarla)
_NUMEROS = count()


def _el_puente() -> _Puente:
    global _puente
    if _puente is None:
        _puente = _Puente(QApplication.instance())  # vive con la app: lo que llega tarde nunca va a un objeto borrado
        _puente.cuadro.connect(_puente.recibir)  # emitidas desde los hilos del pool: llegan en cola al de la ventana
        _puente.capas.connect(_puente.recibir_capas)
        atexit.register(lambda: QThreadPool.globalInstance().waitForDone(2000))  # nada a medias al salir
    return _puente


def _convertir(cuadro, numero, vuelta, destino: QRect, alto_util, radio, dpr, foco, sombra):
    """En un hilo del pool: pasar un cuadro de 720p a imagen y dejarlo a su tamaño tarda 15-25 ms; en el hilo de la
    ventana trababa el carrusel (medido: a 30 cuadros por segundo ocupaba más de la mitad del hilo)."""
    try:
        imagen = _preparar(cuadro.toImage(), destino.width(), destino.height(), alto_util, radio, dpr, foco, sombra)
    except Exception:  # un cuadro raro se salta; no tumba nada
        imagen = QImage()
    _el_puente().cuadro.emit(numero, vuelta, imagen)


def _llega(b, cuadro):
    """Un cuadro nuevo del MP4: si el anterior aún se prepara, este se salta (mejor que acumularlos)."""
    if b.convirtiendo or not cuadro.isValid():
        return
    b.convirtiendo = True
    datos = (b.numero, b.vuelta, b.destino_d(), b.alto_util, b.radio_destino(), b.devicePixelRatioF(), b.foco,
             b.sombra())
    QThreadPool.globalInstance().start(lambda: _convertir(cuadro, *datos))


class _Lienzo:
    """Lo que tienen en común Pieza (se pulsa) y Vista (solo se ve, dentro del botón de una herramienta): un ejemplo
    pintado a sangre en una tarjeta de esquinas redondas. Su foto (o su GIF, o su MP4 mudo si es la elegida del
    carrusel) recortada a la tarjeta, el canto de luz del vidrio y, sobre un degradado oscuro, su título. leyenda:
    True (el degradado siempre; los textos los pone quien la usa), "encima" (su título solo con el ratón o el foco) o
    False. Sin foto, un degradado con el icono de «vacio».

    Se pinta en tres capas: el fondo y la foto (con su degradado, si lo lleva siempre) se preparan en un hilo del pool
    a su tamaño exacto (ver _hacer_capas) y al pintar solo se copian; encima va lo que cambia con el ratón, el foco o
    el carrusel (el título al pasar el ratón, el canto y «apagada»)."""
    RADIO = 16
    INSIGNIA_DERECHA = False  # la pastilla («NUEVO»), arriba a la izquierda o a la derecha

    def _empezar(self, e: dict | None, leyenda, vacio):
        self.e, self.leyenda, self.vacio = e or {}, leyenda, vacio
        self.ruta = foto(self.e) if e else None
        self.proporcion = _proporcion(self.ruta) if self.ruta else 16 / 9
        gif, mp4 = (EJEMPLOS / f"{self.e['id']}.gif", video(self.e)) if e else (None, None)
        self.gif = gif if gif and gif.is_file() else None
        self.video = mp4 if mp4 and mp4.is_file() else None
        self.es_video = self.video is not None  # aunque su MP4 falle luego: su sitio en la tarjeta no cambia
        # De un video se ve solo lo de arriba, sin la franja de sus subtítulos quemados (ver RECORTE_SUBTITULOS): en
        # las galerías, el título de la tarjeta y la leyenda van encima. El video entero se ve al abrirlo
        self.alto_util = RECORTE_SUBTITULOS if self.es_video else 1.0
        try:  # a qué altura está lo importante si hay que recortar alto (la cara de la manzana va abajo)
            self.foco = min(1.0, max(0.0, float(self.e.get("foco", 0.4))))
        except (TypeError, ValueError):
            self.foco = 0.4
        self.vivo = "gif"  # lo que puede hacer ahora: "gif", "video" (la elegida del carrusel) o None (quieta)
        self.dueno = None  # el botón que la lleva dentro (una herramienta): su ratón también la mueve
        self.contener = False  # en el carrusel, lo vertical o cuadrado y los diseños van enteros, a la derecha
        self.apagada = False  # en el carrusel, las que no son la elegida, un poco más oscuras
        self.alto_por_ancho = None  # si se da, su alto sigue a su ancho (las vistas de las herramientas)
        self.insignia = ""  # una pastilla en la esquina («NUEVO»); pintada: con un layout dentro, Qt no usaría
        # heightForWidth de la pieza sino el del layout
        self.peli = self.jugador = self.sumidero = self.cuadro = None
        self.vuelta, self.convirtiendo = 0, False
        self.numero = next(_NUMEROS)
        _PIEZAS[self.numero] = self
        self.destroyed.connect(lambda *_, n=self.numero: (_PIEZAS.pop(n, None), _CON_VIDEO.pop(n, None)))
        self._capas, self._pedida = None, None  # (para qué tamaño, fondo, foto lista) y lo pedido al pool
        # Al cambiar de tamaño se espera a que pare (arrastrar el borde de la ventana pediría decenas de capas)
        self._reloj_capas = QTimer(self)
        self._reloj_capas.setSingleShot(True)
        self._reloj_capas.setInterval(60)
        self._reloj_capas.timeout.connect(self.preparar)

    def fuente(self) -> Path | None:
        """Lo que se movería ahora (el MP4 o el GIF), o None si se queda quieta."""
        if self.vivo == "video" and self.video:
            return self.video
        return self.gif if self.vivo else None

    def encima(self) -> bool:
        return self.underMouse() or bool(self.dueno and self.dueno.underMouse())

    def sizeHint(self):
        return QSize(320, 180)

    def hasHeightForWidth(self):
        return self.alto_por_ancho is not None

    def heightForWidth(self, ancho):
        return round(ancho * self.alto_por_ancho) if self.alto_por_ancho else -1

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._capas is None:
            self.preparar()  # la primera vez, enseguida
        else:
            self._reloj_capas.start()

    def caja(self) -> QRectF | None:
        """Dónde va la foto entera (carrusel); None si va a sangre. Los diseños van siempre enteros: traen su propia
        tipografía y el título de la tarjeta caería encima de la suya. Un video, solo si es vertical o cuadrado."""
        if not (self.contener and (self.proporcion < 1.3 or not self.es_video)):
            return None
        visible = self.proporcion / self.alto_util  # lo que se ve de un video recortado es menos alto
        margen = round(self.height() * 0.06)
        alto = self.height() - 2 * margen
        # a la izquierda quedan como mínimo 380 px para el título y los dos botones (a 1280 px se cortaba «Usar este
        # pedido» al lado de una miniatura de 16:9)
        ancho = max(1, min(alto * visible, self.width() * 0.5, self.width() - 2 * margen - 380))
        alto = ancho / visible
        return QRectF(self.width() - margen - ancho, (self.height() - alto) / 2, ancho, alto)

    def destino_d(self) -> QRect:
        """Dónde va la foto (o el cuadro que se mueve), en píxeles de pantalla."""
        dpr, caja = self.devicePixelRatioF(), self.caja()
        if caja is None:
            return QRect(0, 0, round(self.width() * dpr), round(self.height() * dpr))
        return QRect(round(caja.x() * dpr), round(caja.y() * dpr), round(caja.width() * dpr),
                     round(caja.height() * dpr))

    def destino(self) -> QRectF:
        dpr, d = self.devicePixelRatioF(), self.destino_d()
        return QRectF(d.x() / dpr, d.y() / dpr, d.width() / dpr, d.height() / dpr)

    def sombra(self) -> bool:
        """Si su foto lleva ya el degradado de abajo (las del carrusel a sangre: sus textos van encima)."""
        return self.leyenda is True and self.caja() is None

    def radio_destino(self) -> float:
        return (12 if self.caja() is not None else self.RADIO) * self.devicePixelRatioF()

    def _clave(self):
        return (self.destino_d().getRect(), self.width(), self.height(), self.devicePixelRatioF(), self.alto_util,
                self.foco)

    def preparar(self):
        """Pide al pool su foto y su fondo al tamaño de ahora, si no los tiene ya o pedidos (ver _hacer_capas)."""
        clave = self._clave()
        if self.ruta is None or self.width() < 2 or clave == self._pedida or (self._capas and self._capas[0] == clave):
            return
        self._pedida = clave
        _el_puente()
        dpr, d = self.devicePixelRatioF(), self.destino_d()
        datos = (self.numero, clave, self.ruta, round(self.width() * dpr), round(self.height() * dpr),
                 None if self.caja() is None else d, self.alto_util, self.RADIO * dpr, self.radio_destino(), dpr,
                 self.foco, self.sombra())
        QThreadPool.globalInstance().start(lambda: _hacer_capas(*datos))

    def soltar(self):
        """Suelta su foto preparada (la del carrusel ocupa unos 3 MB al 150 %): se vuelve a preparar al verse."""
        self._capas, self._pedida = None, None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        forma = QPainterPath()
        forma.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), self.RADIO, self.RADIO)
        capas = self._capas
        if capas is None or capas[0] != self._clave():
            self.preparar() if capas is None else self._reloj_capas.start()
        caja, destino = self.caja(), self.destino()
        imagen = self.cuadro if self.cuadro is not None else capas[2] if capas is not None else None
        hay_imagen = imagen is not None and not imagen.isNull()
        if capas is not None and not capas[1].isNull():
            p.drawImage(r, capas[1])  # el fondo (si va entera): a su tamaño, o estirado un momento si cambió
        elif caja is not None or not hay_imagen:  # a sangre, la foto lo tapa entero
            p.fillPath(forma, QColor("#17171D"))
        if hay_imagen:
            p.drawImage(destino, imagen)
        elif self.ruta is None or (capas is not None and self.cuadro is None):
            self._pintar_vacio(p, r, forma)  # sin foto o rota (mientras se prepara, solo el vidrio oscuro)
        if caja is not None:  # el canto fino de la foto entera
            marco = QPainterPath()
            marco.addRoundedRect(destino, 12, 12)
            p.setPen(QPen(QColor(255, 255, 255, 46), 1))
            p.drawPath(marco)
        encima = self.encima() or self.hasFocus()
        # Con la foto entera no hay degradado (su fondo ya es oscuro y oscurecía la foto); a sangre, va en la foto
        if (self.sombra() and not hay_imagen) or (self.leyenda == "encima" and encima):
            self._pintar_leyenda(p, r, forma)
        if self.apagada:
            p.fillPath(forma, QColor(10, 10, 14, 105))
        if self.insignia:
            self._pintar_insignia(p)
        canto = QLinearGradient(0, 0, 0, r.height())  # el reflejo de arriba del vidrio, más claro que los lados
        if self.hasFocus():
            canto.setColorAt(0, QColor("#3DF5FF"))
            canto.setColorAt(1, QColor("#3DF5FF"))
        elif encima:
            canto.setColorAt(0, QColor(214, 202, 255, 235))
            canto.setColorAt(1, QColor(124, 92, 255, 190))
        else:
            canto.setColorAt(0, QColor(255, 255, 255, 64))
            canto.setColorAt(1, QColor(255, 255, 255, 16))
        p.setPen(QPen(QBrush(canto), 2 if self.hasFocus() else 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(forma)

    def _pintar_vacio(self, p, r, forma):
        """Sin foto: la luz del color de la herramienta sobre el vidrio oscuro y su icono en el centro."""
        nombre, color = self.vacio
        luz = QRadialGradient(r.center().x(), r.top() + r.height() * 0.45, max(r.width(), r.height()) * 0.7)
        c = QColor(color)
        c.setAlpha(95)
        luz.setColorAt(0, c)
        c.setAlpha(28)
        luz.setColorAt(0.55, c)
        luz.setColorAt(1, QColor(23, 23, 29, 0))
        p.fillPath(forma, luz)
        lado = round(min(64, r.height() * 0.4))
        p.drawPixmap(round(r.center().x() - lado / 2), round(r.center().y() - lado / 2),
                     icono(nombre, color).pixmap(lado, lado))

    def _pintar_insignia(self, p):
        """La pastilla de vidrio con el violeta y el rosa de la marca, arriba a la izquierda."""
        p.save()  # su relleno no se queda puesto para el canto de la pieza
        letra = QFont(self.font())
        letra.setPixelSize(11)
        letra.setWeight(QFont.ExtraBold)
        letra.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        p.setFont(letra)
        ancho = p.fontMetrics().horizontalAdvance(self.insignia) + 18
        caja = QRectF(self.width() - 10 - ancho if self.INSIGNIA_DERECHA else 10, 10, ancho, 20)
        fondo = QLinearGradient(caja.topLeft(), caja.topRight())
        fondo.setColorAt(0, QColor(124, 92, 255, 235))
        fondo.setColorAt(1, QColor(214, 52, 112, 235))
        p.setBrush(fondo)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.drawRoundedRect(caja, 10, 10)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(caja, Qt.AlignCenter, self.insignia)
        p.restore()

    def _pintar_leyenda(self, p, r, forma):
        _sombra(p, r, 110, forma)
        titulo = self.accessibleName()
        if self.leyenda == "encima" and titulo:  # el título solo se pinta aquí; en el carrusel van sus etiquetas
            letra = QFont(self.font())
            letra.setPixelSize(14)
            letra.setWeight(QFont.DemiBold)
            p.setFont(letra)
            p.setPen(QColor("#FFFFFF"))
            linea = p.fontMetrics().elidedText(titulo, Qt.ElideRight, round(r.width() - 24))
            p.drawText(QRectF(12, r.bottom() - 34, r.width() - 24, 24), Qt.AlignLeft | Qt.AlignVCenter, linea)


class Pieza(_Lienzo, QAbstractButton):
    """Un ejemplo que se pulsa (ver _Lienzo). La misma pieza para todas las galerías: el carrusel de Inicio, su
    mosaico, el de «Ver todo» y la fila del Director."""

    def __init__(self, e: dict | None, leyenda="encima", vacio=("sparkles", "#B79CFF")):
        super().__init__()
        self._empezar(e, leyenda, vacio)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)  # como boton(): el anillo del foco, solo con el teclado
        self.setAccessibleName(str(self.e.get("titulo", "")))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):  # como un enlace: Intro también la abre (Espacio ya lo hace)
            return self.click()
        super().keyPressEvent(e)


class Vista(_Lienzo, QWidget):
    """Lo hecho con una herramienta, arriba de su tarjeta en Inicio (ver _Lienzo). No es un botón: va dentro del de la
    herramienta, que es el que se pulsa, toma el foco y se nombra (un lector de pantalla anunciaba un botón vacío
    dentro de otro). Su «NUEVO», arriba a la derecha: a la izquierda tapaba el título de los diseños."""
    INSIGNIA_DERECHA = True

    def __init__(self, e: dict | None, vacio=("sparkles", "#B79CFF")):
        super().__init__()
        self._empezar(e, False, vacio)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # el clic y el ratón son de la tarjeta entera


def corriendo(b) -> bool:
    return bool(b.jugador) or bool(b.peli and b.peli.state() == QMovie.Running)


def _cuadro_gif(b):
    """Un cuadro nuevo del GIF, ya a su tamaño (son pequeños: se preparan aquí mismo)."""
    if b.peli is None:
        return
    d = b.destino_d()
    b.cuadro = _preparar(b.peli.currentImage(), d.width(), d.height(), b.alto_util, b.radio_destino(),
                         b.devicePixelRatioF(), b.foco, b.sombra())
    b.update(b.destino().toAlignedRect())


def arrancar(b):
    """Mueve la pieza: su MP4 mudo si es la elegida del carrusel (en grande, el GIF se veía borroso y a saltos), si no
    su GIF. El decodificador se crea aquí y se borra al pararla: abierto, Windows no deja reemplazar el archivo
    (ejemplos/crear.py) y ocupa memoria."""
    if b.vivo == "video" and b.video:
        _el_puente()
        b.vuelta, b.convirtiendo = b.vuelta + 1, False
        b.jugador, b.sumidero = QMediaPlayer(b), QVideoSink(b)  # sin salida de audio: mudo
        b.jugador.setVideoSink(b.sumidero)
        b.jugador.setLoops(QMediaPlayer.Infinite)
        _CON_VIDEO[b.numero] = b
        b.sumidero.videoFrameChanged.connect(lambda cuadro: _llega(b, cuadro))
        # roto o sin poder leerse: se queda con su GIF o su foto, sin reintentar
        b.jugador.errorOccurred.connect(lambda *_: (setattr(b, "video", None), b.jugador and parar(b)))
        b.jugador.setSource(QUrl.fromLocalFile(str(b.video)))
        b.jugador.play()
        return
    if not b.peli:
        b.peli = peli = QMovie(str(b.gif), parent=b)
        peli.frameChanged.connect(lambda _: _cuadro_gif(b))
        # roto: la foto fija, sin reintentar (un archivo que no es GIF avisa dos veces)
        peli.error.connect(lambda _: (setattr(b, "gif", None), b.peli and parar(b)))
    b.peli.start()


def parar(b):
    if b.peli:
        b.peli.stop()
        b.peli.deleteLater()
        b.peli = None
    if b.jugador:
        _CON_VIDEO.pop(b.numero, None)
        b.jugador.stop()
        b.jugador.deleteLater()
        b.sumidero.deleteLater()
        b.jugador = b.sumidero = None
    b.cuadro = None  # vuelve la foto fija: el JPG tiene mejor color que el cuadro del GIF
    b.update()


def animar(piezas: list, limite: int = MAX_VIVAS):
    """Mueve las piezas que se ven, como mucho «limite» (la que está bajo el ratón, siempre): primero la del ratón,
    luego la elegida del carrusel y luego las demás en orden; las otras, quietas con su foto. Nada se mueve con la
    casilla apagada, la ventana sin foco o la página oculta (visibleRegion vacía)."""
    si = accion_animar().isChecked()
    vistas = [b for b in piezas if si and b.fuente() and b.window().isActiveWindow() and not b.visibleRegion().isEmpty()]
    encima = [b for b in vistas if b.encima()]
    resto = [b for b in vistas if b not in encima]
    vivas = (encima + [b for b in resto if b.vivo == "video"] + [b for b in resto if b.vivo != "video"])
    vivas = vivas[:max(limite, len(encima))]
    for b in piezas:
        if b in vivas and not corriendo(b):
            arrancar(b)
        elif b not in vivas and (b.peli or b.jugador):
            parar(b)


def quietas(piezas: list):
    """Para todas (la página se oculta): ni un decodificador abierto mientras no se ven."""
    for b in piezas:
        if b.peli or b.jugador:
            parar(b)


def vigilar(padre, piezas: list, limite: int = MAX_VIVAS, espera=None) -> QTimer:
    """Revisa cada 400 ms qué piezas se mueven: así cuenta desplazarse, cambiar de página o de ventana sin engancharse
    a cada cosa. Una sola vigilancia por página, para que el límite sea de la página entera. Mientras espera() diga
    que sí (el carrusel se desliza), no toca nada. El reloj muere con «padre»; quien lo pone lo para al ocultarse la
    página (y lo vuelve a poner al verse)."""
    reloj = QTimer(padre)
    reloj.timeout.connect(lambda: None if espera and espera() else animar(piezas, limite))
    reloj.start(400)
    return reloj


def calentar():
    """Abre un reproductor y lo suelta, una vez, con la app recién abierta y quieta: el primero carga FFmpeg y
    congelaba la ventana unos 100 ms (y hasta 600 ms con su primer MP4) justo cuando el carrusel empezaba."""
    global _caliente
    if _caliente:
        return
    _caliente = True
    QMediaPlayer(QApplication.instance()).deleteLater()


_caliente = False


def pieza_ejemplo(e: dict, al_pulsar, usar_pedido=None, **opciones) -> Pieza:
    """Un ejemplo (video o diseño) para las galerías; con usar_pedido(pedido), el clic derecho lo ofrece."""
    b = Pieza(e, **opciones)
    pedido = str(e.get("pedido") or "")
    b.setToolTip(t("Pedido: «{pedido}»", pedido=pedido[:300]) if pedido else "")
    b.clicked.connect(lambda _=False: al_pulsar())
    if usar_pedido and pedido:  # el «Recrear» de las galerías de IA: la galería es el punto de partida
        b.setToolTip(f"{b.toolTip()}\n{t('Clic derecho: «Usar este pedido» en el Director')}")
        menu = QMenu(b)
        menu.addAction(t("Usar este pedido")).triggered.connect(lambda: usar_pedido(pedido))
        b.setContextMenuPolicy(Qt.CustomContextMenu)
        b.customContextMenuRequested.connect(lambda punto: menu.exec(b.mapToGlobal(punto)))
    return b


class Mosaico(QWidget):
    """Galería en columnas del mismo ancho, con huecos finos y cada pieza a su proporción (como la de Higgsfield). Se
    coloca a mano: una rejilla dejaba huecos grandes entre piezas de distinto alto. Su alto sigue a su ancho. Las
    piezas ocultas (los filtros de «Ver todo») no ocupan sitio."""
    HUECO = 6

    def __init__(self, piezas: list, ancho_min: int = 230, columnas_max: int = 6):
        super().__init__()
        self.piezas, self.ancho_min, self.columnas_max = piezas, ancho_min, columnas_max
        for b in piezas:
            b.setParent(self)
        politica = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        politica.setHeightForWidth(True)
        self.setSizePolicy(politica)

    def _colocar(self, ancho: int, mover=False) -> int:
        """Reparte las piezas en columnas y devuelve el alto que ocupa todo. Como mucho una columna por cada 3
        piezas: con pocas (los «Videos» de «Ver todo») quedaban columnas vacías al lado de una sola pieza. Se reparten
        de la más alta a la más baja, cada una a la columna más corta, y dentro de cada columna van en su orden: así
        las columnas acaban casi a la vez (en orden, a 1280 px, una quedaba 240 px más corta que otra)."""
        visibles = [b for b in self.piezas if not b.isHidden()]
        if not visibles:
            return 0
        columnas = max(2, min(self.columnas_max, (ancho + self.HUECO) // (self.ancho_min + self.HUECO),
                              -(-len(visibles) // 3)))
        col = (ancho - self.HUECO * (columnas - 1)) / columnas
        alto = {b: col / min(max(b.proporcion, 0.75), 1.9) for b in visibles}  # ni tiras larguísimas ni rendijas
        altos, de = [0.0] * columnas, [[] for _ in range(columnas)]
        for b in sorted(visibles, key=lambda b: -alto[b]):  # sorted es estable: a igual alto, su orden
            c = altos.index(min(altos))
            de[c].append(b)
            altos[c] += alto[b] + self.HUECO
        if mover:
            for c, lista in enumerate(de):
                y = 0.0
                for b in sorted(lista, key=visibles.index):
                    b.setGeometry(round(c * (col + self.HUECO)), round(y), round(col), round(alto[b]))
                    y += alto[b] + self.HUECO
        return max(0, round(max(altos) - self.HUECO))

    def recolocar(self):
        """Tras ocultar o enseñar piezas: su alto cambia y cada una va a su nuevo sitio."""
        self.updateGeometry()
        self._colocar(self.width(), mover=True)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, ancho):
        return self._colocar(ancho)

    def sizeHint(self):
        return QSize(2 * self.ancho_min, self._colocar(2 * self.ancho_min))

    def minimumSizeHint(self):
        return QSize(2 * self.ancho_min, 0)

    def resizeEvent(self, e):
        self._colocar(self.width(), mover=True)
        super().resizeEvent(e)


class Carrusel(QScrollArea):
    """Fila que se desplaza de lado si no cabe (así la página no se sale por la derecha a 1366 px): con las flechas
    de su cabecera, animado, y con la rueda del ratón."""

    def __init__(self, contenido: QWidget, alto: int = 230):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.setFixedHeight(alto)
        self.setWidget(contenido)
        self.animacion = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self.animacion.setDuration(350)
        self.animacion.setEasingCurve(QEasingCurve.OutCubic)

    def deslizar(self, valor: int):
        """Se desliza hasta esa posición (sin salirse)."""
        barra = self.horizontalScrollBar()
        self.animacion.stop()
        self.animacion.setStartValue(barra.value())
        self.animacion.setEndValue(max(0, min(barra.maximum(), valor)))
        self.animacion.start()

    def mover(self, sentido: int):
        """Una pantalla a la derecha (1) o a la izquierda (-1)."""
        barra = self.horizontalScrollBar()
        self.deslizar(barra.value() + sentido * barra.pageStep())

    def wheelEvent(self, e):
        """La rueda mueve la fila de lado; en el borde, la página sigue bajando como siempre."""
        self.animacion.stop()
        barra, giro = self.horizontalScrollBar(), e.angleDelta()
        antes = barra.value()
        barra.setValue(antes - (giro.x() if abs(giro.x()) > abs(giro.y()) else giro.y()))
        if barra.value() == antes:
            e.ignore()


def fila_ejemplos(piezas: list, alto: int = 170) -> QWidget:
    """Una fila de piezas del mismo alto, cada una a su proporción, que se desplaza de lado. Sus piezas, en .tarjetas;
    sus flechas ‹ › (solo se ven si no cabe entera), en .flechas: van en la cabecera de quien la pone, junto a sus
    botones (en una línea propia ocupaban sitio y quedaban sueltas)."""
    contenido = QWidget()
    fila = QHBoxLayout(contenido)
    fila.setContentsMargins(0, 0, 0, 0)
    fila.setSpacing(8)
    caja = QWidget()
    caja.tarjetas = piezas
    for b in piezas:  # lo vertical, como mucho 3:4: a 9:16 era una tira de 95 px
        b.setFixedSize(round(alto * min(max(b.proporcion, 0.75), 1.78)), alto)
        fila.addWidget(b)
    fila.addStretch()
    caja.carrusel = Carrusel(contenido, alto + 14)  # y la barra fina de abajo
    lay = QVBoxLayout(caja)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(caja.carrusel)
    caja.flechas = []
    for nombre, sentido, texto in (("chevron-left", -1, t("Ver anteriores")),
                                   ("chevron-right", 1, t("Ver siguientes"))):
        flecha = boton("")
        flecha.setIcon(icono(nombre))
        flecha.setToolTip(texto)
        flecha.setAccessibleName(texto)
        flecha.setStyleSheet("padding: 4px 10px;")
        flecha.hide()
        flecha.clicked.connect(lambda _=False, s=sentido: caja.carrusel.mover(s))
        caja.carrusel.horizontalScrollBar().rangeChanged.connect(lambda _, maximo, f=flecha: f.setVisible(maximo > 0))
        caja.flechas.append(flecha)
    return caja


def _intercalar(filas: list) -> list:
    """(ejemplo, abrir, n.º de su fila) de todas las filas, intercalados: un video, un diseño… así el mosaico no es un
    bloque de videos y luego otro de diseños."""
    return [x for grupo in zip_longest(*([(e, abrir, n) for e in lista] for n, (_, lista, abrir) in enumerate(filas)))
            for x in grupo if x]


def ver_todo(padre, filas: list, usar_pedido=None) -> QDialog:
    """«Ver todo», la vista aérea de la galería: todos los ejemplos en un mosaico, con filtros por tipo que ocultan los
    demás. Aquí solo se mueve el que está bajo el ratón, así nunca hay muchos GIF a la vez. Elegir uno cierra la
    ventana."""
    ventana = QDialog(padre)
    ventana.setAttribute(Qt.WA_DeleteOnClose)  # sus GIF no se quedan en memoria
    ventana.setWindowTitle(t("Hecho con Ráfaga Studio"))
    ventana.resize(1100, 680)
    lay = QVBoxLayout(ventana)
    filtros = Segmentos()  # la misma cápsula de vidrio que el selector de formato
    for i, nombre in enumerate([t("Todo"), *(titulo for titulo, _, _ in filas)]):
        filtros.opcion(nombre, i).setChecked(i == 0)
    filtros.layout().addWidget(casilla_animar())  # a la altura de la cápsula, no de su luz
    lay.addWidget(filtros)
    if usar_pedido:
        lay.addWidget(etiqueta(t("Clic derecho: «Usar este pedido» en el Director"), "sub"))
    piezas = []
    for e, abrir, n in _intercalar(filas):
        b = pieza_ejemplo(e, lambda e=e, abrir=abrir: (ventana.close(), abrir(e)),
                          usar_pedido and (lambda p: (ventana.close(), usar_pedido(p))))
        b.fila = n
        piezas.append(b)
    mosaico = Mosaico(piezas, 200)

    def filtrar(i):
        for b in piezas:
            b.setVisible(i == 0 or b.fila == i - 1)
        mosaico.recolocar()
    filtros.grupo.idClicked.connect(filtrar)
    contenido = QWidget()
    columna = QVBoxLayout(contenido)
    columna.setContentsMargins(0, 0, 0, 0)
    columna.addWidget(mosaico)
    columna.addStretch()
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(contenido)
    lay.addWidget(area, 1)
    vigilar(ventana, piezas, 0)
    area.setFocus()  # al abrir, el foco en la rejilla: no en «Todo», que saldría con el anillo cian sin usar el teclado
    ventana.show()
    return ventana


def galeria_ejemplos(padre, ver_video, usar_pedido=None, seccion_de_inicio=False) -> QWidget:
    """Los ejemplos hechos con el estudio, videos y diseños intercalados (un video se ve con ver_video(e); un diseño,
    en grande), con «Ver todo» y la casilla «Animar vistas previas». En Inicio es un mosaico con su cabecera de
    sección; en el Director, una fila que se desplaza de lado. Sin ejemplos, no se ve. Sus piezas, en .tarjetas: quien
    la pone las vigila con vigilar(), junto con las demás de su página."""
    filas = [f for f in ((t("Videos"), ejemplos(), ver_video),
                         (t("Diseños"), disenos(),
                          lambda d: ver_imagen(padre, foto(d), str(d.get("titulo", ""))))) if f[1]]
    todo = boton(t("Ver todo"))
    todo.clicked.connect(lambda: ver_todo(padre, filas, usar_pedido))
    casilla = casilla_animar()
    piezas = [pieza_ejemplo(e, lambda e=e, abrir=abrir: abrir(e), usar_pedido) for e, abrir, _ in _intercalar(filas)]
    if seccion_de_inicio:
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.addWidget(seccion(t("Hecho con Ráfaga Studio"), t("Ideas reales para empezar: pásales el ratón y mira"),
                              casilla, todo))
        lay.addWidget(Mosaico(piezas, columnas_max=4))  # a 1920 px, 6 columnas dejaban un hueco de 300 px debajo
    else:
        caja, lay = tarjeta()
        fila = fila_ejemplos(piezas)
        cabecera = QHBoxLayout()
        cabecera.setSpacing(10)
        cabecera.addWidget(etiqueta(t("Hecho con Ráfaga Studio"), "sub"), 1, Qt.AlignVCenter)
        for w in (*fila.flechas, casilla, todo):
            cabecera.addWidget(w, 0, Qt.AlignVCenter)
        lay.addLayout(cabecera)
        lay.addWidget(fila)
    caja.tarjetas = piezas
    caja.setVisible(bool(piezas))
    return caja


def serie_de_pasos(pasos: list[dict]) -> str:
    """La serie (nombre de su carpeta) que creó o continuó el Director en su último paso de serie; '' si ninguna."""
    for p in reversed(pasos):
        if p.get("herramienta") in ("crear_serie", "crear_episodio"):
            try:
                carpeta = Path(json.loads(p["resultado"])["carpeta"])
            except (ValueError, TypeError, KeyError):
                continue  # ese paso falló («ERROR: …»): no dejó serie
            # el capítulo está en series/<serie>/episodios/NN
            return (carpeta if p["herramienta"] == "crear_serie" else carpeta.parent.parent).name
    return ""


def ver_memoria(padre) -> QDialog:
    """«Memoria del estudio»: lo que el Director recordó de tus gustos, por departamento, para verlo y borrarlo."""
    ventana = QDialog(padre)
    ventana.setAttribute(Qt.WA_DeleteOnClose)
    ventana.setWindowTitle(t("Memoria del estudio"))
    ventana.resize(640, 420)
    lay = QVBoxLayout(ventana)
    lay.addWidget(etiqueta(t("Lo que el Director recuerda de tus gustos, por departamento. Se guarda en este PC y va "
                             "dentro de los pedidos a tu IA. Para añadir algo, díselo: «recuerda que…»."), "sub"))
    lista = QListWidget()
    lay.addWidget(lista, 1)
    fila = QHBoxLayout()
    borrar = boton(f"🗑  {t('Borrar')}")
    fila.addWidget(borrar)
    fila.addStretch()
    cerrar = boton(t("Cerrar"))
    cerrar.clicked.connect(ventana.close)
    fila.addWidget(cerrar)
    lay.addLayout(fila)

    def llenar():
        lista.clear()
        for departamento, preferencias in memoria.cargar().items():
            for p in preferencias:  # QListWidgetItem es texto plano: lo que dijo la IA nunca se lee como HTML
                item = QListWidgetItem(f"{roles.nombre(departamento)}: {p}")
                item.setData(Qt.UserRole, (departamento, p))
                lista.addItem(item)
        if not lista.count():
            lista.addItem(t("Todavía no recuerda nada."))
        borrar.setEnabled(bool(lista.item(0).data(Qt.UserRole)))
        lista.setCurrentRow(0)

    def quitar():
        item = lista.currentItem()
        if item and item.data(Qt.UserRole):
            memoria.olvidar(*item.data(Qt.UserRole))
            llenar()
    borrar.clicked.connect(quitar)
    llenar()
    ventana.show()
    return ventana


class Escucha(QThread):
    """Graba hasta que terminas de hablar y lo pasa a texto, sin congelar la ventana."""
    nivel = Signal(float)
    entendiendo = Signal(bool)  # si Whisper ya está en el PC (si no, primero se descarga)
    texto = Signal(str)
    fallo = Signal(str)

    def __init__(self):
        super().__init__()
        self.detener = threading.Event()
        self.cerrando = False  # la app se cierra (o se abandonó): lo grabado no se transcribe ni se manda
        self.oyendo = True  # False en cuanto deja de grabar y se pone a entender

    def run(self):
        try:
            voz.preparar()
            audio = voz.escuchar(self.detener, self.nivel.emit)
            self.oyendo = False
            if self.cerrando:
                return
            if len(audio):  # sin voz no hay nada que entender: «No te escuché» sale enseguida
                self.entendiendo.emit(ia.whisper_descargado())
            texto = voz.entender(audio)
            if not self.cerrando:
                self.texto.emit(texto)
        except Exception as e:  # sin micrófono, sin permiso…: se avisa, no se cae la app
            traceback.print_exc()
            self.fallo.emit(str(e).strip() or type(e).__name__)


class PaginaDirector(QWidget):
    usando = Signal(str)  # la herramienta que empieza a usar el Director (desde su hilo)
    termino = Signal()
    preguntar = Signal(str)  # el Director pide permiso antes de gastar o publicar (desde su hilo)
    plan = Signal(str)  # lo que va a hacer, dicho en el chat antes de empezar (desde su hilo)

    def __init__(self, brillo=None, abrir_diseno=None, abrir_serie=None):
        """abrir_diseno(carpeta) y abrir_serie(nombre) llevan lo hecho a su página: las páginas no se conocen, lo une
        app.py."""
        super().__init__()
        self.brillo, self.historial, self.adjuntos = brillo, [], []
        self.abrir_diseno, self.abrir_serie = abrir_diseno, abrir_serie
        self.diseno_hecho, self.serie_hecha = None, ""
        self.tarea = self.escucha = self.lectura = None
        self._viejas = []  # lecturas en voz que ya no interesan pero siguen corriendo (soltarlas tumbaría la app)
        self.por_voz = False  # el pedido llegó hablando: la luz sigue mientras trabaja y contesta
        # La pregunta de costo abierta (su ventana), su respuesta y el aviso al hilo del Director, que espera
        self.caja, self.respuesta, self.contestada, self.intentos = None, False, threading.Event(), 0
        self.cerrada = False  # la app se cierra: lo que cueste dinero ya no se pregunta, se deja sin hacer
        self.preguntar.connect(self._preguntar)
        self.plan.connect(lambda texto: self._decir("Director", texto))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(etiqueta(t("Director IA"), "titulo"))
        lay.addWidget(etiqueta(t("Pídeme el trabajo como se lo pedirías a tu equipo. Yo uso todo el estudio (guiones, "
                                 "imágenes, video, diseño, música y edición) y te entrego el resultado."), "sub"))
        lay.addWidget(self._galeria())

        caja, caja_lay = tarjeta()
        self.chat = QTextBrowser()
        self.chat.setOpenLinks(False)
        self.chat.setMinimumHeight(240)
        caja_lay.addWidget(self.chat, 1)
        self.adjuntos_txt = etiqueta("", "sub")
        self.adjuntos_txt.hide()
        caja_lay.addWidget(self.adjuntos_txt)
        fila = QHBoxLayout()
        adjuntar = boton("📎")
        adjuntar.setToolTip(t("Adjuntar fotos, videos o audios para el trabajo"))
        adjuntar.clicked.connect(self._adjuntar)
        self.pedido = QLineEdit()
        self.pedido.setPlaceholderText(t("Ej.: Hazme un anuncio de 20 segundos para mi barbería y un post para Instagram"))
        self.pedido.returnPressed.connect(self.enviar)
        # Con qué modelo se hace el video de este pedido (como en CapCut); Automático: lo de «Claves de IA»
        self.modelo = SelectorModelo("director")
        self.micro = boton(f"🎙️  {t('Hablar')}")
        self.micro.setToolTip(t("Pulsa y habla: te escucha hasta que terminas (Ctrl+Espacio)"))
        self.micro.clicked.connect(self.alternar_voz)
        self.enviar_btn = boton(f"✨  {t('Hacer')}", "principal")
        self.enviar_btn.clicked.connect(self.enviar)
        for w, estira in ((adjuntar, 0), (self.pedido, 1), (self.modelo, 0), (self.micro, 0), (self.enviar_btn, 0)):
            fila.addWidget(w, estira)
        caja_lay.addLayout(fila)
        self.en_voz = QCheckBox(t("Responder en voz alta"))
        self.en_voz.setChecked(True)
        nota = QHBoxLayout()
        nota.addWidget(self.en_voz)
        nota.addWidget(etiqueta(t("Solo te escucha cuando pulsas «Hablar» o Ctrl+Espacio, y se para cuando terminas. "
                                  "Tu voz se entiende en este PC."), "sub"), 1)
        recuerdos = boton(f"🧠  {t('Memoria del estudio')}")
        recuerdos.setToolTip(t("Lo que el Director recuerda de tus gustos: verlo y borrarlo"))
        recuerdos.clicked.connect(lambda: ver_memoria(self))
        nota.addWidget(recuerdos)
        caja_lay.addLayout(nota)
        lay.addWidget(caja, 1)

        self.estado = etiqueta("", "sub")
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.hide()
        lay.addWidget(self.progreso)
        lay.addWidget(self.estado)
        acciones = QHBoxLayout()
        self.ir_diseno = boton(f"🎨  {t('Abrir en {programa}', programa=t('Diseño'))}")
        # varios diseños en un trabajo: el botón los ofrece uno por uno en su menú, y el clic no abre además el último
        self.menu_disenos = QMenu(self.ir_diseno)
        self.ir_diseno.clicked.connect(lambda: None if self.ir_diseno.menu() else self.abrir_diseno(self.diseno_hecho))
        self.ir_serie = boton(f"🐰  {t('Abrir en {programa}', programa=t('Dibujos animados'))}")
        self.ir_serie.clicked.connect(lambda: self.abrir_serie(self.serie_hecha))
        for b in (self.ir_diseno, self.ir_serie):
            b.hide()
            acciones.addWidget(b)
        acciones.addStretch()
        lay.addLayout(acciones)
        self.reproductor = Reproductor()
        self.reproductor.hide()
        lay.addWidget(self.reproductor, 1)

        self.altavoz = QMediaPlayer(self)
        self.salida = QAudioOutput(self)
        self.altavoz.setAudioOutput(self.salida)
        self.altavoz.playbackStateChanged.connect(self._fin_de_voz)
        # un MP3 que no se puede reproducir solo da error, sin cambiar de estado: la luz se quedaba encendida y la
        # pregunta «¿Lo hago?» nunca pasaba a escuchar la respuesta
        self.altavoz.errorOccurred.connect(lambda *_: self._fin_de_voz(QMediaPlayer.StoppedState))
        self._decir("Director", t("¡Hola! Soy tu Director. Dime qué quieres crear hoy: un video, un anuncio, un "
                                  "diseño, una canción… y me encargo de todo."))

    def consejo_claves(self, ir_a_claves):
        """Sin IA de texto conectada: funciona con la gratis sin clave, pero tarda (1 respuesta cada 30 s)."""
        self._decir("Director", t("Consejo: ahora pienso con la IA gratis sin clave, que es lenta. Conecta Groq o "
                                  "Gemini (gratis) en «Claves de IA» y trabajaré mucho más rápido y mejor."))
        ir = boton(f"🔑  {t('Ir a Claves de IA')}")
        ir.clicked.connect(ir_a_claves)
        self.layout().insertWidget(2, ir, 0, Qt.AlignLeft)

    # ---------- Ejemplos ----------

    def _galeria(self):
        self.galeria = galeria_ejemplos(self, self.ver_ejemplo, self.usar_pedido)
        self.vigia = vigilar(self, self.galeria.tarjetas)
        return self.galeria

    def showEvent(self, e):
        self.vigia.start()
        super().showEvent(e)

    def hideEvent(self, e):
        """Oculta, su vigilancia no recorre las piezas cada 400 ms para nada y ningún GIF se queda abierto."""
        self.vigia.stop()
        quietas(self.galeria.tarjetas)
        super().hideEvent(e)

    def usar_pedido(self, pedido: str):
        """«Usar este pedido» de un ejemplo: queda escrito para cambiarlo y pulsar «Hacer». No se envía solo: un
        trabajo puede gastar cuota o dinero, y eso lo decide el usuario."""
        self.pedido.setText(pedido)
        self.pedido.setFocus()
        self._a_la_vista(self.pedido)  # setFocus no desplaza la página

    def _a_la_vista(self, widget):
        """Desplaza la página hasta el widget: la galería deja el chat y el estado debajo, fuera de la pantalla (a
        1280×720 con 150 %, ningún aviso de la voz se veía: solo la luz)."""
        area = self.parentWidget().parentWidget() if self.parentWidget() else None  # app.py la pone en un QScrollArea

        def bajar():
            # El campo entero y un poco de aire: ensureWidgetVisible se conforma con que se vea el cursor de un campo
            # de texto, y el campo podía quedar cortado por abajo
            self.layout().activate()  # recién enseñada (venir de Inicio), su sitio puede no estar puesto aún
            centro = widget.mapTo(area.widget(), widget.rect().center())
            area.ensureVisible(centro.x(), centro.y(), 0, widget.height() // 2 + 24)
        if isinstance(area, QScrollArea):
            QTimer.singleShot(0, bajar)

    def ver_ejemplo(self, e: dict):
        self.reproductor.show()
        self.reproductor.mostrar(proyecto_ejemplo(e))

    # ---------- Conversación ----------

    def _decir(self, quien: str, texto: str):
        color = "#7C5CFF" if quien == "Director" else "#FF4D8D"
        cuerpo = html.escape(str(texto)).replace("\n", "<br>")  # lo que dice la IA nunca se interpreta como HTML
        self.chat.append(f"<p><b style='color:{color}'>{html.escape(quien)}</b><br>{cuerpo}</p>")

    def _adjuntar(self):
        rutas, _ = QFileDialog.getOpenFileNames(self, t("Adjuntar archivos"), "", t("Fotos, videos y audios ({tipos})",
                                                tipos="*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.webm *.mp3 *.wav *.m4a"))
        self.adjuntos += [r for r in rutas if r not in self.adjuntos]
        self.adjuntos_txt.setText(t("Adjuntos: {nombres}", nombres=", ".join(Path(r).name for r in self.adjuntos)))
        self.adjuntos_txt.setVisible(bool(self.adjuntos))

    def ocupado(self) -> bool:
        return bool(self.tarea and self.tarea.isRunning())

    def enviar(self, por_voz: bool = False):
        texto = self.pedido.text().strip()
        if not texto or self.ocupado():
            return
        self.por_voz = por_voz
        self.pedido.clear()
        self._decir(t("Tú"), texto + (f"\n📎 {', '.join(Path(r).name for r in self.adjuntos)}" if self.adjuntos else ""))
        pedido = texto + (f"\n\nArchivos que te doy: {json.dumps(self.adjuntos, ensure_ascii=False)}"
                          if self.adjuntos else "")
        self.adjuntos = []
        self.adjuntos_txt.hide()
        self.enviar_btn.setEnabled(False)
        self.progreso.show()
        self.progreso.setValue(0)
        if self.brillo and por_voz:
            self.brillo.poner("pensando")
        self.tarea = Tarea(director.dirigir, pedido=pedido, historial=list(self.historial), al_usar=self.usando.emit,
                           confirmar=self._confirmar, al_decir=self.plan.emit, modelo_video=self.modelo.valor())
        self.historial.append({"rol": "usuario", "texto": pedido})
        self.tarea.progreso.connect(lambda txt, f: (self.estado.setText(txt), self.progreso.setValue(int(f * 100))))
        self.tarea.listo.connect(self._listo)
        self.tarea.fallo.connect(self._fallo)
        self.tarea.finished.connect(self._fin_de_tarea)
        self.tarea.start()

    def _listo(self, r: dict):
        self._decir("Director", r["mensaje"])
        # con lo hecho y sus archivos: «sigue» o «cámbiale la música» se refieren a eso
        self.historial.append({"rol": "director", "texto": r["mensaje"],
                               **({"hecho": r["resumen"]} if r.get("resumen") else {})})
        imagenes = [x for x in r["resultados"] if Path(x["archivo"]).suffix.lower() in IMAGENES]
        videos = [x for x in r["resultados"] if x not in imagenes]
        if videos:
            self.reproductor.show()
            self.reproductor.mostrar({**r, "resultados": videos})
        elif imagenes:  # solo diseños: el video del trabajo anterior no se queda debajo como si fuera lo nuevo
            self.reproductor.player.stop()
            self.reproductor.hide()
        for x in imagenes:  # cada diseño se ve en grande y se sigue editando en su página
            ver_imagen(self, x["archivo"], x["titulo"])
        hechos = [x for x in imagenes if (Path(x["archivo"]).parent / "diseno.json").is_file()]
        self.diseno_hecho = Path(hechos[-1]["archivo"]).parent if hechos else None
        self.menu_disenos.clear()
        for x in hechos:  # «&&»: un «&» del título no se toma como atajo de teclado
            self.menu_disenos.addAction(x["titulo"].replace("&", "&&")).triggered.connect(
                lambda _=False, c=Path(x["archivo"]).parent: self.abrir_diseno(c))
        self.ir_diseno.setMenu(self.menu_disenos if len(hechos) > 1 else None)
        self.serie_hecha = serie_de_pasos(r.get("pasos", []))
        self.ir_diseno.setVisible(bool(hechos and self.abrir_diseno))
        self.ir_serie.setVisible(bool(self.serie_hecha and self.abrir_serie))
        if self.en_voz.isChecked() and self.por_voz:
            self._leer_en_voz(r["mensaje"])

    def _fallo(self, error: str):
        self._decir("Director", t("No pude terminar: {error}", error=error))
        if self.en_voz.isChecked() and self.por_voz:
            self._leer_en_voz(t("No pude terminar. Te dejé el motivo en el chat."))

    def _fin_de_tarea(self):
        self.enviar_btn.setEnabled(True)
        self.progreso.hide()
        self.estado.setText("")
        self.termino.emit()
        if self.brillo and not (self.lectura and self.lectura.isRunning()) and \
                self.altavoz.playbackState() != QMediaPlayer.PlayingState:
            self.brillo.poner(None)

    # ---------- Permiso antes de gastar o publicar ----------

    def _confirmar(self, pregunta: str) -> bool:
        """En el hilo del Director: la app pregunta y el trabajo espera la respuesta. Sin un sí, no se hace."""
        self.contestada.clear()
        self.respuesta = False
        if self.cerrada:
            return False
        self.preguntar.emit(pregunta)
        self.contestada.wait()
        return self.respuesta

    def _preguntar(self, pregunta: str):
        """La pregunta con su costo, en el chat y en una ventana con «Sí» y «No». Si el pedido llegó hablando, también
        en voz alta, y luego escucha «sí» o «no»."""
        # En el chat, solo la pregunta del código (va primero; lo de la IA va detrás): el plan ya está en el chat
        self._decir("Director", pregunta.split("\n\n", 1)[0])
        self.caja = caja = QMessageBox(QMessageBox.Question, t("¿Lo hago?"), pregunta,
                                       QMessageBox.Yes | QMessageBox.No, self)
        caja.setTextFormat(Qt.PlainText)  # parte del texto lo escribió la IA: nunca se interpreta como HTML
        caja.setDefaultButton(QMessageBox.No)  # un Enter por despiste no gasta
        caja.finished.connect(lambda _: self._contestar(
            caja.clickedButton() is not None and caja.standardButton(caja.clickedButton()) == QMessageBox.Yes))
        # con esta ventana delante, el Ctrl+Espacio de la ventana principal no llega (ni se puede pulsar «Hablar»)
        atajo = QShortcut(QKeySequence("Ctrl+Space"), caja)
        atajo.setAutoRepeat(False)
        atajo.activated.connect(self.alternar_voz)
        caja.open()
        if self.por_voz:
            self.intentos = 3
            self._leer_en_voz(pregunta)  # al terminar de decirla (_fin_de_voz), o si no pudo, escucha la respuesta

    def _escuchar_respuesta(self):
        if not self.caja or (self.escucha and self.escucha.isRunning()):
            return
        self.escucha = self._nueva_escucha()
        self.escucha.texto.connect(self._respuesta_oida)
        self.escucha.fallo.connect(lambda _: (self.estado.setText(t("No pude usar el micrófono: contesta en la ventana.")),
                                              self.brillo and self.brillo.poner(None)))
        self.escucha.start()
        self.estado.setText(t("Te escucho: di «sí» o «no»."))
        if self.brillo:
            self.brillo.poner("escuchando")

    def _respuesta_oida(self, texto: str):
        self.escucha.wait()  # ya dijo lo que oyó: que termine antes de volver a escuchar
        if not self.caja:
            return
        si = voz.si_o_no(texto)
        if si is not None:  # como un clic en su botón: la ventana se cierra y el Director sigue
            self.caja.button(QMessageBox.Yes if si else QMessageBox.No).click()
            return
        self.intentos -= 1
        if self.intentos > 0:
            self._leer_en_voz(t("No te entendí. Di «sí» o «no»."))
        else:
            self.estado.setText(t("No te entendí: contesta en la ventana."))

    def _contestar(self, si: bool):
        self.caja = None
        if self.escucha and self.escucha.isRunning():  # contestó con un clic: lo que siga oyendo ya no cuenta
            self.escucha.cerrando = True
            self.escucha.detener.set()
        self._soltar_lectura()
        self.altavoz.stop()
        if self.brillo and self.por_voz:
            self.brillo.poner("pensando")
        self.respuesta = si
        self.contestada.set()

    # ---------- Voz ----------

    def alternar_voz(self):
        """Empieza a escuchar; si ya escucha, para y entiende lo dicho hasta ahí; si está hablando, se calla. Mientras
        pregunta «¿Lo hago?», sirve para contestar con la voz (y no corta la respuesta que ya escucha)."""
        if self.altavoz.playbackState() == QMediaPlayer.PlayingState:
            self.altavoz.stop()
        if self.caja:
            self._soltar_lectura()  # la pregunta que aún se preparaba no suena encima de su respuesta
            self.intentos = max(self.intentos, 1)
            return self._escuchar_respuesta()
        if self.escucha and self.escucha.isRunning():
            if not self.escucha.oyendo:  # ya está entendiendo (con ruido de fondo puede tardar un minuto): se abandona
                return self._abandonar_escucha()
            self.escucha.detener.set()
            return
        if self.ocupado():
            return mensaje_error(self, t("Estoy trabajando"), t("Espera a que termine el trabajo actual."))
        self._soltar_lectura()  # la respuesta hablada que se estaba preparando ya no suena: ahora hablas tú
        self.escucha = self._nueva_escucha()
        self.escucha.texto.connect(self._oido)
        self.escucha.fallo.connect(self._micro_fallo)
        self.escucha.start()
        poner(self.micro, f"⏹  {t('Parar')}")
        self.estado.setText(t("Te escucho… habla y haz una pausa al terminar."))
        self._a_la_vista(self.estado)  # con Ctrl+Espacio desde otra página, la de arriba es la galería
        if self.brillo:
            self.brillo.poner("escuchando")

    def _micro_fallo(self, error: str):
        """El micrófono no sirvió: se dice también en voz alta (si no, parecía que el asistente no respondía) y, si
        Windows lo tiene silenciado, la ventana lleva a sus ajustes de sonido."""
        if self.brillo:
            self.brillo.poner(None)
        self._volver_micro()
        if self.en_voz.isChecked():
            self._leer_en_voz(error)
        botones = ([(t("Abrir ajustes de sonido"), lambda: QDesktopServices.openUrl(QUrl("ms-settings:sound")))]
                   if error == voz.SILENCIADO() else [])
        mensaje(self, t("No pude usar el micrófono"), error, QMessageBox.Warning, botones)

    def _nueva_escucha(self) -> Escucha:
        """Un hilo que escucha, con la luz que late con tu voz y el aviso mientras entiende."""
        escucha = Escucha()
        escucha.nivel.connect(lambda v: self.brillo and self.brillo.oir(v))
        escucha.entendiendo.connect(self._entendiendo)
        return escucha

    def _entendiendo(self, descargado: bool):
        # la primera vez, Whisper se descarga (~460 MB, minutos): sin decirlo parecía que no respondía
        self.estado.setText(t("Entendiendo lo que dijiste…") if descargado else
                            t("Descargando el reconocimiento de voz (unos 460 MB, solo la primera vez)…"))
        if self.brillo:
            self.brillo.poner("pensando")

    def _abandonar_escucha(self):
        """Whisper termina en segundo plano, pero lo que entienda ya no llega al Director."""
        hilo, self.escucha = self.escucha, None
        hilo.cerrando = True
        try:
            hilo.fallo.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._viejas.append(hilo)
        hilo.finished.connect(lambda: hilo in self._viejas and self._viejas.remove(hilo))
        if self.brillo:
            self.brillo.poner(None)
        self._volver_micro()

    def _volver_micro(self):
        poner(self.micro, f"🎙️  {t('Hablar')}")
        self.estado.setText("")

    def _oido(self, texto: str):
        self._volver_micro()
        if not texto:  # en el chat y en voz alta: el estado de abajo se pierde de vista y la luz sola no dice nada
            if self.brillo:
                self.brillo.poner(None)
            aviso = t("No te escuché bien. Habla cerca del micrófono (o súbele el volumen en Windows) y pulsa "
                      "«Hablar» otra vez.")
            self._decir("Director", aviso)
            if self.en_voz.isChecked():
                self._leer_en_voz(aviso)
            return
        self.pedido.setText(texto)
        self.enviar(por_voz=True)

    def _soltar_lectura(self):
        """Deja terminar la lectura en voz que esté en marcha sin que su audio suene después."""
        hilo, self.lectura = self.lectura, None
        if hilo and hilo.isRunning():
            hilo.listo.disconnect()
            self._viejas.append(hilo)
            hilo.finished.connect(lambda: hilo in self._viejas and self._viejas.remove(hilo))

    def _leer_en_voz(self, texto: str):
        self._soltar_lectura()
        self.lectura = Tarea(lambda texto, aviso: {"archivo": str(voz.hablar(texto))}, texto=texto)
        self.lectura.listo.connect(lambda r: (self.altavoz.setSource(QUrl.fromLocalFile(r["archivo"])),
                                              self.altavoz.play()))
        self.lectura.fallo.connect(lambda _: (self.brillo and self.brillo.poner(None),
                                              self.caja and self._escuchar_respuesta()))  # la pregunta, sin voz
        self.lectura.start()

    def _fin_de_voz(self, estado):
        if self.brillo:
            self.brillo.poner("hablando" if estado == QMediaPlayer.PlayingState else
                              "escuchando" if self.escucha and self.escucha.isRunning() else
                              "pensando" if self.ocupado() and self.por_voz else None)
        if estado == QMediaPlayer.StoppedState and self.caja and self.por_voz:  # terminó de decir la pregunta
            self._escuchar_respuesta()

    def cerrar(self):
        """Al cerrar la app: deja de escuchar y de hablar, y nada de lo que termine después hace nada."""
        self.altavoz.stop()
        hilos = [h for h in (self.escucha, self.lectura, self.tarea, *self._viejas) if h]
        for hilo in hilos:
            hilo.blockSignals(True)
        if self.escucha and self.escucha.isRunning():
            self.escucha.cerrando = True
            self.escucha.detener.set()
        self.cerrada, self.respuesta = True, False  # el Director esperaba un sí para gastar: se va sin hacerlo
        self.contestada.set()
        for hilo in hilos:
            hilo.wait(10_000)  # ponytail: una herramienta del Director a medias no se puede parar; pasado esto se cierra
