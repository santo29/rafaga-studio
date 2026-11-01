"""Página «Director IA»: un chat a página completa (como el de Claude) donde pides el trabajo por escrito o con la voz y
la IA usa todo el estudio para hacerlo; lo hecho sale en el chat, listo para descargar. Sin mensajes, la portada con los
ejemplos hechos con Ráfaga Studio (carpeta ejemplos/). Aquí vive también la galería de ejemplos que usan el Director e
Inicio: la pieza pintada con su video, el mosaico y la fila que se desplaza."""
import atexit
import json
import os
import re
import threading
import traceback
from itertools import count, zip_longest
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QObject, QPropertyAnimation, QRect, QRectF, QSize, Qt, QThread, QThreadPool,
                            QTimer, QUrl, Signal, Slot)
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QImage, QImageReader, QKeySequence,
                           QLinearGradient, QMovie, QPainter, QPainterPath, QPen, QRadialGradient, QShortcut,
                           QTextCursor)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (QAbstractButton, QApplication, QBoxLayout, QCheckBox, QDialog, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPlainTextEdit, QProgressBar, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from motor import claves, diseno, director, herramientas, ia, idioma, memoria, roles, seguro, voz
from motor.idioma import t
from motor.video import ffmpeg
from ui.comun import (boton, descargar, etiqueta, mensaje, mensaje_error, Reproductor, se_puede_abrir, seccion,
                      Segmentos, SelectorModelo, Tarea, tarjeta, ver_imagen, ver_video, VisorImagen)
from ui.iconos import icono, poner

EJEMPLOS = Path(__file__).resolve().parent.parent.parent / "ejemplos"
DATOS = EJEMPLOS.parent / "datos"
CONVERSACION = DATOS / "director.json"  # la conversación con el Director, para seguirla al abrir la app otra vez
MAX_GUARDADOS = 100  # mensajes que se guardan (los de antes se olvidan)
ANCHO_CHAT = 900  # la columna del chat y la caja del pedido: a 1920 px, líneas de 1600 px no se leían
ARCHIVOS = "\n\nArchivos que te doy: "  # lo que sigue en el pedido es la lista JSON de adjuntos (la burbuja no lo enseña)
# Lo que se puede adjuntar sin elegir «Todos los archivos»: lo que usan las herramientas y los textos de un encargo
# (su texto va en el pedido, ver texto_adjunto; un PDF no, que leerlo pediría otra dependencia)
TIPOS_ADJUNTOS = "*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.webm *.mp3 *.wav *.m4a *.txt *.md"
TEXTOS = {".txt", ".md"}
# Lo que la memoria del estudio no guarda (una clave larga, un número de tarjeta) y no es parte de una ruta: así
# director.json no lo deja escrito y los archivos de la conversación («sigue con ese video») siguen valiendo
_SECRETO = re.compile(rf"(?<![\\/.])(?:{memoria._TOKEN.pattern}|{memoria._TARJETA.pattern})(?![\w\\/-]|\.\w)")
ICONOS_TIPO = {"imagen": "image", "diseno": "palette", "video": "clapperboard", "audio": "music", "serie": "rabbit",
               "archivo": "file-text"}
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


def del_idioma(ruta: Path) -> Path:
    """En otro idioma que no sea el español, la versión en inglés de un archivo de ejemplo ({id}-en.mp4, .gif o .jpg)
    si la hay: el video de presentación y el anuncio llevan voz y letras en pantalla."""
    ingles = ruta.with_name(f"{ruta.stem}-en{ruta.suffix}")
    return ingles if idioma.actual() != "es" and ingles.is_file() else ruta


def foto(e: dict) -> Path | None:
    """La imagen fija de un ejemplo: ejemplos/{id}.jpg (o su versión en inglés, ver del_idioma) o, si la trae,
    «imagen», una ruta dentro de la app (Rafa, la mascota, vive en assets/ con su marca). Una ruta que se sale de la app
    no vale (None)."""
    if not e.get("imagen"):
        return del_idioma(EJEMPLOS / f"{e.get('id')}.jpg")
    raiz = EJEMPLOS.parent.resolve()
    ruta = (raiz / str(e["imagen"])).resolve()
    return ruta if ruta.is_relative_to(raiz) else None


def video(e: dict) -> Path:
    """El MP4 de un ejemplo (o su versión en inglés, ver del_idioma)."""
    return del_idioma(EJEMPLOS / f"{e['id']}.mp4")


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
        gif, mp4 = (del_idioma(EJEMPLOS / f"{self.e['id']}.gif"), video(self.e)) if e else (None, None)
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


def galeria_ejemplos(padre, ver_video, usar_pedido=None, seccion_de_inicio=False, alto=170) -> QWidget:
    """Los ejemplos hechos con el estudio, videos y diseños intercalados (un video se ve con ver_video(e); un diseño,
    en grande), con «Ver todo» y la casilla «Animar vistas previas». En Inicio es un mosaico con su cabecera de
    sección; en el Director, una fila de piezas de «alto» px que se desplaza de lado. Sin ejemplos, no se ve. Sus
    piezas, en .tarjetas: quien la pone las vigila con vigilar(), junto con las demás de su página."""
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
        fila = fila_ejemplos(piezas, alto)
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


# ---------- El chat: lo que se guarda, sus tarjetas y sus mensajes ----------

TIPOS_TARJETA = ("imagen", "diseno", "video", "audio", "serie")
FORMATOS = ("9:16", "16:9", "1:1", "4:5")


def _tipo(archivo: str) -> str | None:
    """Qué es un resultado: "diseno" (una imagen con su diseno.json al lado: se edita por capas), "imagen", "video" o
    "audio"; None si no es nada de eso."""
    sufijo = Path(archivo).suffix.lower()
    if sufijo in seguro.IMAGENES:
        return "diseno" if (Path(archivo).parent / "diseno.json").is_file() else "imagen"
    return "video" if sufijo in seguro.VIDEOS else "audio" if sufijo in seguro.AUDIOS else None


def _textos(valor, maximo: int, largo: int = 600) -> list[str]:
    """Solo los textos de una lista (lo demás fuera), como mucho «maximo» y recortados."""
    return [v[:largo] for v in valor if isinstance(v, str)][:maximo] if isinstance(valor, list) else []


def tarjetas_de(r: dict) -> list[dict]:
    """Las tarjetas del chat de lo que hizo el Director: una por archivo y sin repetir (programar_publicacion devuelve
    otra vez el video que sube), con su tipo; la serie va en sus videos o, si creó una sin video, en su tarjeta. Nunca
    una ruta de red: abrirla mandaría tu usuario de Windows a ese servidor."""
    serie, tarjetas, vistos = serie_de_pasos(r.get("pasos") or []), [], set()
    for x in r.get("resultados") or []:
        archivo = str(x.get("archivo") or "")
        if archivo in vistos or seguro.es_ruta_de_red(archivo) or not (tipo := _tipo(archivo)):
            continue
        vistos.add(archivo)
        tarjetas.append({"tipo": tipo, "archivo": archivo, "titulo": str(x.get("titulo") or Path(archivo).stem),
                         "formato": str(r.get("formato") or ""), "descripcion": str(x.get("descripcion") or ""),
                         "hashtags": _textos(x.get("hashtags"), 30, 100),
                         **({"serie": serie} if serie and tipo == "video" else {})})
    if serie and not any(x["tipo"] == "video" for x in tarjetas):
        tarjetas.append({"tipo": "serie", "archivo": "", "titulo": serie, "serie": serie})
    return tarjetas


def portada(archivo) -> Path:
    """La foto de la tarjeta de un video: «<nombre>_portada.jpg» a su lado (ver con_portadas)."""
    archivo = Path(archivo)
    return archivo.with_name(f"{archivo.stem}_portada.jpg")


def con_portadas(r: dict) -> dict:
    """En el hilo del trabajo: la portada de cada video para su tarjeta del chat, una vez, con ffmpeg (como las láminas
    de serie.py). Solo dentro de datos/: junto a un video tuyo de otra carpeta no se deja nada. Si no sale (un video
    de menos de 1 s), la tarjeta lleva el icono del video."""
    for x in r.get("resultados") or []:
        archivo = str(x.get("archivo") or "")
        if (Path(archivo).suffix.lower() in seguro.VIDEOS and not seguro.es_ruta_de_red(archivo)
                and Path(archivo).is_file() and Path(archivo).resolve().is_relative_to(DATOS.resolve())
                and not portada(archivo).is_file()):
            try:
                ffmpeg("-ss", "1", "-i", archivo, "-frames:v", "1", "-vf", "scale='min(720,iw)':-2", portada(archivo))
            except Exception:  # sin portada no se pierde nada: no tumba el trabajo
                traceback.print_exc()
    return r


def tapar(texto: str) -> str:
    """El texto con sus claves y números de tarjeta cambiados por «•••», para guardarlo en el disco.
    ponytail: una contraseña corta no tiene formato y se queda; para taparla haría falta preguntar al escribirla."""
    return _SECRETO.sub("•••", texto)


def texto_adjunto(ruta: str) -> str:
    """Lo que dice un .txt o .md adjunto (el principio), para que el Director lea el encargo y no solo su nombre. De
    una carpeta de red o de otro tipo, nada."""
    if Path(ruta).suffix.lower() not in TEXTOS or seguro.es_ruta_de_red(ruta):
        return ""
    try:
        with open(ruta, encoding="utf-8-sig", errors="replace") as f:
            return f"\n\nTexto de {Path(ruta).name}:\n{f.read(3000)}"
    except OSError:
        return ""


def cargar_conversacion(archivo) -> list[dict]:
    """La conversación guardada (ver PaginaDirector._guardar), sin fiarse del archivo, que se puede tocar a mano: roto,
    de más de 2 MB o con tipos raros da una conversación vacía, y de cada mensaje solo queda lo que la página sabe
    enseñar. Nunca una ruta de red en una tarjeta ni en un adjunto (verla mandaría tu usuario de Windows a ese
    servidor)."""
    try:
        if Path(archivo).stat().st_size > 2_000_000:
            return []
        mensajes = json.loads(Path(archivo).read_text(encoding="utf-8"))["mensajes"]
    except (OSError, ValueError, RecursionError, TypeError, KeyError):
        return []
    limpios = []
    for m in mensajes[-MAX_GUARDADOS:] if isinstance(mensajes, list) else []:
        if not isinstance(m, dict) or m.get("rol") not in ("usuario", "director") or not isinstance(m.get("texto"), str):
            continue
        limpio = {"rol": m["rol"], "texto": m["texto"][:6000]}
        if isinstance(m.get("hecho"), str):
            limpio["hecho"] = m["hecho"][:6000]
        for clave, maximo in (("plan", 20), ("hechas", 10), ("fallidas", 10)):
            if valor := _textos(m.get(clave), maximo):
                limpio[clave] = valor
        if adjuntos := [r for r in _textos(m.get("adjuntos"), 20, 1000) if not seguro.es_ruta_de_red(r)]:
            limpio["adjuntos"] = adjuntos
        resultados = []
        for x in m.get("resultados") if isinstance(m.get("resultados"), list) else []:
            if not (isinstance(x, dict) and x.get("tipo") in TIPOS_TARJETA and isinstance(x.get("archivo"), str)
                    and isinstance(x.get("titulo"), str)) or seguro.es_ruta_de_red(x["archivo"]):
                continue
            serie = x.get("serie") if isinstance(x.get("serie"), str) else ""
            if (x["tipo"] == "serie" and not (serie and x["archivo"] == "")) or (x["tipo"] != "serie" and Path(
                    x["archivo"]).suffix.lower() not in seguro.IMAGENES | seguro.VIDEOS | seguro.AUDIOS):
                continue
            resultados.append({"tipo": x["tipo"], "archivo": x["archivo"][:1000], "titulo": x["titulo"][:300],
                               "formato": x.get("formato") if x.get("formato") in FORMATOS else "",
                               "descripcion": str(x.get("descripcion") or "")[:3000],
                               "hashtags": _textos(x.get("hashtags"), 30, 100), **({"serie": serie} if serie else {})})
        if resultados:
            limpio["resultados"] = resultados[:30]
        limpios.append(limpio)
    return limpios


def _centrada(w: QWidget) -> QHBoxLayout:
    """Una fila con w centrado y tan ancho como le dejen su maximumWidth (sin esto, Qt lo pega a la izquierda; con
    AlignHCenter, lo encoge a su sizeHint)."""
    fila = QHBoxLayout()
    fila.addStretch()
    fila.addWidget(w, 100)
    fila.addStretch()
    return fila


def _texto(texto: str, nombre: str, seleccionable: bool = False) -> QLabel:
    """Un texto del chat, siempre plano (lo escribe la IA o viene de un archivo: nunca se lee como HTML), con su
    emoji si lo lleva (etiqueta() lo quita)."""
    l = QLabel(str(texto))
    l.setTextFormat(Qt.PlainText)
    l.setWordWrap(True)
    l.setObjectName(nombre)
    if seleccionable:
        l.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return l


def _hacer_miniatura(numero, clave, ruta, ancho, alto, radio, dpr):
    """En un hilo del pool: la foto de una miniatura del chat, leída ya pequeña y sin guardarla en _FOTOS (cien
    resultados guardados, leídos a LADO px, ocuparían cientos de MB)."""
    try:
        lector = QImageReader(str(ruta))
        lector.setAutoTransform(True)
        tam = lector.size()
        if tam.isValid():
            lector.setScaledSize(tam.scaled(ancho, alto, Qt.KeepAspectRatioByExpanding))
        lista = _preparar(lector.read(), ancho, alto, 1.0, radio, dpr)
    except Exception:  # una foto rara: sale el icono de su tipo
        traceback.print_exc()
        lista = QImage()
    _el_puente().capas.emit(numero, clave, QImage(), lista)


class Miniatura(Pieza):
    """La foto pequeña de un adjunto o de lo hecho, en el chat: una Pieza (esquinas redondas, su canto, Tab, Intro y
    clic) cuya foto se lee en el pool ya a su tamaño (ver _hacer_miniatura). Sin foto, el icono de su tipo."""
    RADIO = 12

    def __init__(self, ruta, titulo: str, tipo: str, alto: int):
        super().__init__(None, leyenda=False, vacio=(ICONOS_TIPO[tipo], "#B79CFF"))
        self.ruta = Path(ruta) if ruta else None
        self.proporcion = _proporcion(self.ruta) if self.ruta else 1.0
        self.setFixedSize(round(alto * min(max(self.proporcion, 0.75), 1.78)), alto)
        self.setAccessibleName(titulo)
        self.setToolTip(titulo)

    def preparar(self):
        clave = self._clave()
        if self.ruta is None or self.width() < 2 or clave == self._pedida or (self._capas and self._capas[0] == clave):
            return
        self._pedida = clave
        _el_puente()
        dpr = self.devicePixelRatioF()
        datos = (self.numero, clave, self.ruta, round(self.width() * dpr), round(self.height() * dpr), self.RADIO * dpr,
                 dpr)
        QThreadPool.globalInstance().start(lambda: _hacer_miniatura(*datos))


def en_grande(padre, x: dict):
    """Lo hecho o adjuntado, en grande: una imagen en el visor (Descargar, Editar en Diseño…) y un video o un audio en
    su reproductor, con sonido. Otro archivo (un texto, un PDF) solo va al pedido."""
    sufijo = Path(x["archivo"]).suffix.lower()
    if sufijo in seguro.IMAGENES:
        return ver_imagen(padre, x["archivo"], x["titulo"])
    if sufijo in seguro.VIDEOS | seguro.AUDIOS:
        return ver_video(padre, {"formato": x.get("formato") or "9:16", "resultados": [
            {"archivo": x["archivo"], "titulo": x["titulo"], "descripcion": x.get("descripcion", ""),
             "hashtags": x.get("hashtags", [])}]})
    return None


def tipo_adjunto(ruta: str) -> str:
    sufijo = Path(ruta).suffix.lower()
    return ("imagen" if sufijo in seguro.IMAGENES else "video" if sufijo in seguro.VIDEOS else
            "audio" if sufijo in seguro.AUDIOS else "archivo")


def ficha(padre, ruta: str, alto: int, quitar=None) -> QFrame:
    """Un archivo adjunto: su miniatura (o el icono de su tipo) y su nombre; pulsarla lo ve en grande. Con quitar(), la
    «×» que lo saca del pedido. De una carpeta de red no se lee nada (Windows mandaría tu usuario a ese servidor)."""
    caja = QFrame()
    caja.setObjectName("adjunto")
    fila = QHBoxLayout(caja)
    fila.setContentsMargins(4, 4, 4 if quitar else 10, 4)
    fila.setSpacing(8)
    tipo, nombre, de_red = tipo_adjunto(ruta), Path(ruta).name, seguro.es_ruta_de_red(ruta)
    vista = Miniatura(ruta if tipo == "imagen" and not de_red else None, nombre, tipo, alto)
    if tipo == "archivo" or de_red:
        vista.setFocusPolicy(Qt.NoFocus)
        vista.setCursor(Qt.ArrowCursor)
    else:
        vista.clicked.connect(lambda: en_grande(padre, {"archivo": ruta, "titulo": nombre}))
    texto = _texto(vista.fontMetrics().elidedText(nombre, Qt.ElideMiddle, 170), "sub")
    texto.setWordWrap(False)
    texto.setToolTip(ruta)
    fila.addWidget(vista)
    fila.addWidget(texto)
    if quitar:
        x = boton("", "quitar")
        x.setIcon(icono("x"))
        x.setToolTip(t("Quitar {nombre}", nombre=nombre))  # su nombre accesible sale de aquí (ver boton)
        x.clicked.connect(quitar)
        fila.addWidget(x)
    return caja


class CampoPedido(QPlainTextEdit):
    """El pedido: Intro lo manda (Mayúsculas+Intro, otra línea), Tab sale del campo y crece solo de 1 a 6 líneas (luego
    se desplaza). Un pedido largo pegado o traído de Inicio se ve entero, con sus escenas en líneas. Un archivo soltado
    o pegado (Ctrl+V) se adjunta (soltados) en vez de escribirse como «file:///…»."""
    enviar = Signal()
    soltados = Signal(list)
    LINEAS = 6

    def __init__(self):
        super().__init__()
        self.setTabChangesFocus(True)  # si no, el Tab se escribe y el teclado queda atrapado aquí
        self.document().documentLayout().documentSizeChanged.connect(self._crecer)
        self._crecer()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not e.modifiers() & Qt.ShiftModifier:
            return self.enviar.emit()
        super().keyPressEvent(e)

    def canInsertFromMimeData(self, m) -> bool:
        return m.hasUrls() or super().canInsertFromMimeData(m)

    def insertFromMimeData(self, m):
        if rutas := [u.toLocalFile() for u in m.urls() if u.isLocalFile()]:
            return self.soltados.emit(rutas)
        super().insertFromMimeData(m)  # un enlace web o un texto: se escribe

    def text(self) -> str:  # como el campo de una línea de antes: lo usan app.py, la voz y las pruebas
        return self.toPlainText()

    def setText(self, texto: str):
        self.setPlainText(texto)
        self.moveCursor(QTextCursor.End)

    def showEvent(self, e):
        self._crecer()  # ya con la letra de la hoja de estilo
        super().showEvent(e)

    def _crecer(self, *_):
        # En un QPlainTextEdit, el alto del documento son sus líneas (con las que parte al ancho del campo)
        lineas = max(1, round(self.document().size().height()))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if lineas > self.LINEAS else Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(min(self.LINEAS, lineas) * self.fontMetrics().lineSpacing() + self.contentsMargins().top()
                            + self.contentsMargins().bottom() + round(2 * self.document().documentMargin()) + 2)


class Mensaje(QWidget):
    """Un mensaje del chat, en texto plano. El tuyo va a la derecha, en su burbuja, con lo que adjuntaste; el del
    Director, a la izquierda y sin caja (como en Claude): lo que va diciendo, en qué paso está mientras trabaja y, al
    terminar, lo hecho y sus tarjetas."""

    def __init__(self, quien: str, tuyo: bool = False):
        super().__init__()
        self.quien, self.tuyo, self.lineas, self.plan, self.trabajo = quien, tuyo, [], [], None
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        self.caja = QFrame()
        self.dentro = QVBoxLayout(self.caja)
        self.dentro.setSpacing(8)
        if tuyo:
            self.caja.setObjectName("burbuja_tu")
            self.dentro.setContentsMargins(16, 10, 16, 12)
            fila.addStretch()
        else:
            self.dentro.setContentsMargins(0, 0, 0, 0)
            self.dentro.addWidget(_texto(t("Director"), "nombre_director"))
        fila.addWidget(self.caja, 0 if tuyo else 1)
        self.setAccessibleName(quien)

    def anadir(self, w: QWidget, linea: str = "") -> QWidget:
        """Un trozo más, en el orden en que llega; mientras trabaja, encima de la línea del paso."""
        self.dentro.insertWidget(self.dentro.indexOf(self.trabajo) if self.trabajo else self.dentro.count(), w)
        if linea:
            self.lineas.append(linea)
        return w

    def parrafo(self, texto: str) -> QWidget:
        return self.anadir(_texto(texto, "texto_tu" if self.tuyo else "texto_director", True), texto)

    def linea(self, nombre: str, color: str, texto: str) -> QWidget:
        """Una línea con su icono: nada depende solo del color."""
        caja = QWidget()
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(6)
        dibujo = QLabel()
        dibujo.setPixmap(icono(nombre, color).pixmap(16, 16))
        fila.addWidget(dibujo, 0, Qt.AlignTop)
        fila.addWidget(_texto(texto, "paso"), 1)
        return self.anadir(caja, texto)

    def adjuntos(self, rutas: list[str], padre):
        caja = QWidget()
        rejilla = QGridLayout(caja)
        rejilla.setContentsMargins(0, 0, 0, 0)
        rejilla.setSpacing(6)
        for i, ruta in enumerate(rutas):
            rejilla.addWidget(ficha(padre, ruta, 64), i // 2, i % 2)
        self.anadir(caja, "\n".join(Path(r).name for r in rutas))

    def trabajando(self):
        """La línea de lo que hace ahora, con su barra fina: cambia sin añadir líneas (no llena el chat)."""
        self.trabajo = QWidget()
        lay = QGridLayout(self.trabajo)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setHorizontalSpacing(6)
        lay.setVerticalSpacing(4)
        dibujo = QLabel()
        dibujo.setPixmap(icono("loader-circle", "#B79CFF").pixmap(16, 16))
        self.ahora, self.detalle_txt = _texto(t("Pensando…"), "paso_actual"), _texto("", "paso")
        self.barra = QProgressBar()
        self.barra.setObjectName("barra_fina")
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(4)
        lay.addWidget(dibujo, 0, 0, Qt.AlignTop)
        lay.addWidget(self.ahora, 0, 1)
        lay.addWidget(self.detalle_txt, 1, 1)
        lay.addWidget(self.barra, 2, 0, 1, 2)
        lay.setColumnStretch(1, 1)
        self.dentro.addWidget(self.trabajo)

    def paso(self, nombre: str):
        """La herramienta que empieza (en negrita); su progreso va debajo, en gris."""
        if self.trabajo:
            self.ahora.setText(nombre)
            self.detalle_txt.setText("")

    def detalle(self, texto: str, fraccion: float):
        if self.trabajo:
            self.detalle_txt.setText(texto)
            self.barra.setValue(int(fraccion * 100))

    def parar(self):
        if self.trabajo:
            self.dentro.removeWidget(self.trabajo)
            self.trabajo.deleteLater()
            self.trabajo = None

    def terminar(self, m: dict, pagina):
        """Lo que queda del trabajo, igual al acabar que al abrir la app otra vez: qué hizo (y qué no salió), su
        respuesta (si no repite lo último que dijo) y las tarjetas de lo hecho."""
        self.parar()
        if m.get("hechas"):
            self.linea("circle-check", "#7CFFB2", t("Hecho: {lista}", lista=", ".join(map(herramientas.nombre,
                                                                                            m["hechas"]))))
        if m.get("fallidas"):
            self.linea("triangle-alert", "#FFB454", t("No salió: {lista}", lista=", ".join(map(herramientas.nombre,
                                                                                                m["fallidas"]))))
        if m["texto"] not in self.plan[-1:]:
            self.parrafo(m["texto"])
        for x in m.get("resultados", []):
            self.anadir(TarjetaResultado(x, pagina), x["titulo"])

    def texto_plano(self) -> str:
        return "\n".join([self.quien, *self.lineas])

    def acomodar(self, ancho: int):
        """Al cambiar el ancho de la columna: la burbuja mide lo que su texto, hasta el 72 % (con wordWrap, QLabel pedía
        su mínimo y partía «ahora anímala, que salga el humo» en tres líneas); cada tarjeta, de lado o no."""
        if self.tuyo:
            tope = int(ancho * 0.72)
            self.caja.setMaximumWidth(tope)
            for l in self.caja.findChildren(QLabel, "texto_tu"):
                l.ensurePolished()
                largo = max((l.fontMetrics().horizontalAdvance(x) for x in l.text().splitlines()), default=0)
                l.setMinimumWidth(min(largo + 4, tope - 32))
        for x in self.findChildren(TarjetaResultado):
            x.acomodar(ancho)


class TarjetaResultado(QFrame):
    """Lo hecho, en el chat: su miniatura (pulsarla lo ve en grande), qué es y dónde quedó, y lo que se hace con ello:
    Descargar, Editar en Diseño o Editar, Animar, Abrir en Dibujos animados y Abrir carpeta. Si el archivo ya no está,
    lo dice y sus botones se apagan."""
    ALTO = 150

    def __init__(self, x: dict, pagina):
        super().__init__()
        self.setObjectName("tarjeta")
        tipo, titulo = x["tipo"], x["titulo"]
        archivo = Path(x["archivo"]) if x["archivo"] else None
        existe = archivo is not None and archivo.is_file()
        activa = existe or (tipo == "serie" and pagina.abrir_serie is not None)
        foto = archivo if tipo in ("imagen", "diseno") else portada(archivo) if tipo == "video" else None
        self.miniatura = Miniatura(foto if existe and foto and foto.is_file() else None, titulo, tipo, self.ALTO)
        self.miniatura.setToolTip(t("Ver en grande") if tipo != "serie" else "")
        self.miniatura.clicked.connect(lambda: pagina.abrir_serie(x["serie"]) if tipo == "serie" else
                                       en_grande(pagina, x))
        self.miniatura.setEnabled(activa)
        partes = [{"imagen": t("Imagen"), "diseno": t("Diseño"), "video": t("Video"), "audio": t("Audio"),
                   "serie": t("Dibujos animados")}[tipo]]
        if tipo in ("imagen", "diseno") and existe and (tam := QImageReader(str(archivo)).size()).isValid():
            partes.append(f"{tam.width()} × {tam.height()}")
        elif tipo == "video" and x.get("formato"):
            partes.append(x["formato"])
        textos = QVBoxLayout()
        textos.setSpacing(4)
        textos.addWidget(_texto(titulo, "resultado_titulo", True))
        textos.addWidget(_texto(" · ".join(partes) if existe or tipo == "serie" else t("Ya no está en tu PC"),
                                "resultado_meta"))
        if existe and se_puede_abrir(archivo.parent):  # dónde quedó, a la vista y copiable (un ejemplo no se enseña)
            textos.addWidget(_texto(t("Guardado en: {carpeta}", carpeta=archivo.parent), "resultado_meta", True))
        textos.addStretch()
        self.botones = QWidget()
        fila = QHBoxLayout(self.botones)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)

        def accion(texto, funcion, ayuda=""):
            b = boton(texto)
            b.setToolTip(ayuda)
            b.clicked.connect(lambda _=False: funcion())
            b.setEnabled(activa)
            fila.addWidget(b)
        if tipo != "serie":
            accion(f"⬇  {t('Descargar')}", lambda: descargar(pagina, archivo, titulo), t("Guardar una copia donde quieras"))
        if tipo == "diseno" and pagina.abrir_diseno:
            accion(f"🎨  {t('Editar en Diseño')}", lambda: pagina.abrir_diseno(archivo.parent),
                   t("Cambiar sus textos, colores y capas en la página Diseño"))
        elif tipo == "imagen" and VisorImagen.al_disenar:  # por la clase: guardado en ella, no se ata a nada
            accion(f"🎨  {t('Editar en Diseño')}", lambda: VisorImagen.al_disenar(str(archivo), titulo),
                   t("Ponerla en un diseño nuevo para añadirle textos y formas"))
        if tipo in ("imagen", "diseno"):
            accion(f"🎬  {t('Animar')}", lambda: pagina._animar(str(archivo)),
                   t("Que el Director la anime aquí mismo (si cuesta, te lo pregunta antes)"))
        if tipo == "video" and Reproductor.al_editar:
            accion(f"✂️  {t('Editar')}", lambda: Reproductor.al_editar(str(archivo), x.get("formato") or "9:16"),
                   t("Abrir este resultado en el editor de video"))
        if x.get("serie") and pagina.abrir_serie:
            accion(f"🐰  {t('Abrir en {programa}', programa=t('Dibujos animados'))}",
                   lambda: pagina.abrir_serie(x["serie"]))
        if archivo and se_puede_abrir(archivo.parent):
            accion("📂", lambda: os.startfile(archivo.parent), t("Abrir carpeta"))
        fila.addStretch()
        self.lay = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.lay.setContentsMargins(12, 12, 12, 12)
        self.lay.setSpacing(14)
        self.lay.addWidget(self.miniatura, 0, Qt.AlignTop | Qt.AlignLeft)
        derecha = QVBoxLayout()
        derecha.setSpacing(10)
        derecha.addLayout(textos, 1)
        derecha.addWidget(self.botones)
        self.lay.addLayout(derecha, 1)

    def acomodar(self, ancho: int):
        """De lado si caben la miniatura y los botones en la columna; si no (una ventana estrecha, el francés), la
        miniatura arriba: los botones nunca se cortan."""
        de_lado = ancho - self.miniatura.width() - 38 >= self.botones.sizeHint().width()
        self.lay.setDirection(QBoxLayout.LeftToRight if de_lado else QBoxLayout.TopToBottom)


class Conversacion(QScrollArea):
    """El chat: una columna centrada de ANCHO_CHAT px como mucho, con la portada (sin mensajes) y los mensajes. Se
    desplaza sola (la página nunca: la caja del pedido siempre se ve) y baja con cada mensaje nuevo o lo que crece, salvo
    si subiste a leer."""

    def __init__(self, portada_: QWidget):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        dentro = QWidget()
        centro = QVBoxLayout(dentro)
        centro.setContentsMargins(0, 0, 0, 0)
        self.columna = QWidget()
        self.columna.setMaximumWidth(ANCHO_CHAT)
        centro.addLayout(_centrada(self.columna))
        self.lay = QVBoxLayout(self.columna)
        self.lay.setContentsMargins(0, 8, 0, 16)
        self.lay.setSpacing(18)
        self.portada = portada_
        self.lay.addWidget(portada_)
        self.lay.addStretch()
        self.setWidget(dentro)
        barra, self._abajo = self.verticalScrollBar(), True
        barra.valueChanged.connect(lambda v: setattr(self, "_abajo", v >= barra.maximum() - 80))
        barra.rangeChanged.connect(lambda _, maximo: self._abajo and barra.setValue(maximo))

    def sizeHint(self):
        # Ocupa lo que sobra (stretch), sin pedir alto: el QScrollArea de app.py mide la página con heightForWidth, que
        # suma los sizeHint, y con un pedido largo la página crecía más que la ventana y se desplazaba
        return QSize(super().sizeHint().width(), 100)

    def mensajes(self) -> list[Mensaje]:
        return [w for i in range(self.lay.count()) if isinstance(w := self.lay.itemAt(i).widget(), Mensaje)]

    def anadir(self, m: Mensaje) -> Mensaje:
        self.lay.insertWidget(self.lay.count() - 1, m)
        m.acomodar(min(ANCHO_CHAT, self.viewport().width()))
        self._abajo = True  # lo nuevo se ve
        return m

    def vaciar(self):
        for m in self.mensajes():
            self.lay.removeWidget(m)
            m.hide()
            m.deleteLater()

    def toPlainText(self) -> str:
        """«Quién» y lo que dijo, mensaje por mensaje (con los adjuntos, lo hecho y los títulos de sus tarjetas)."""
        return "\n".join(m.texto_plano() for m in self.mensajes())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # La portada llena el alto (centrada); si no cabe, su contenido manda y se desplaza
        self.portada.setMinimumHeight(max(self.viewport().height() - 24, self.portada.layout().minimumSize().height()))
        for m in self.mensajes():
            m.acomodar(min(ANCHO_CHAT, self.viewport().width()))


ESTILO_DIRECTOR = """
#barra_chat #secundario { padding: 6px 12px; font-size: 14px; border-radius: 9px; }
#titulo_chat { font-size: 18px; font-weight: 700; color: #FFFFFF; }
#vacio_titulo { font-size: 30px; font-weight: 800; color: #FFFFFF; }
#vacio_lema { font-size: 15px; color: #A9A9B6; }
#compositor { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(28, 24, 44, 0.95), stop:1 rgba(13, 12, 18, 0.95));
              border: 1px solid rgba(150, 125, 255, 0.34); border-top-color: rgba(222, 212, 255, 0.55); border-radius: 22px; }
#compositor QPlainTextEdit { background: transparent; border: none; font-size: 16px; padding: 0;
                             selection-background-color: rgba(124, 92, 255, 0.50); }
#pista { color: #8D8D9A; font-size: 13px; }
#burbuja_tu { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.30),
                                          stop:1 rgba(124, 92, 255, 0.16));
              border: 1px solid rgba(150, 125, 255, 0.30); border-top-color: rgba(222, 212, 255, 0.45);
              border-radius: 18px; border-bottom-right-radius: 6px; }
#burbuja_tu QLabel { color: #FFFFFF; font-size: 15px; background: transparent; }
#nombre_director { color: #B79CFF; font-size: 13px; font-weight: 600; }
#texto_director { font-size: 15px; color: #ECECF1; }
#paso { color: #A9A9B6; font-size: 13px; }
#paso_actual { color: #ECECF1; font-size: 13px; font-weight: 600; }
#resultado_titulo { font-size: 16px; font-weight: 700; color: #FFFFFF; }
#resultado_meta { font-size: 13px; color: #8D8D9A; }
#tarjeta #secundario { padding: 6px 12px; font-size: 14px; border-radius: 9px; }
#barra_fina { background: rgba(255, 255, 255, 0.06); border: none; border-radius: 2px; }
#barra_fina::chunk { border-radius: 2px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7C5CFF, stop:1 #FF4D8D); }
#adjunto { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
           border-top-color: rgba(255, 255, 255, 0.22); border-radius: 12px; }
#adjunto QLabel { color: #DCDCE6; font-size: 13px; background: transparent; }
#quitar { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 4px; }
#quitar:hover { background: rgba(255, 77, 141, 0.22); border-color: rgba(255, 77, 141, 0.45); }
#quitar:focus { border-color: #3DF5FF; }
"""


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
        self.tarea = self.escucha = self.lectura = None
        self.bloque = None  # el mensaje del Director del trabajo en marcha: ahí se escribe lo que va haciendo
        # Dónde se guarda la conversación: nada hasta restaurar(), que llama app.py (las pruebas no tocan tus datos)
        self.archivo = None
        self._viejas = []  # lecturas en voz que ya no interesan pero siguen corriendo (soltarlas tumbaría la app)
        self.por_voz = False  # el pedido llegó hablando: la luz sigue mientras trabaja y contesta
        # La pregunta de costo abierta (su ventana), su respuesta y el aviso al hilo del Director, que espera
        self.caja, self.respuesta, self.contestada, self.intentos = None, False, threading.Event(), 0
        self.cerrada = False  # la app se cierra: lo que cueste dinero ya no se pregunta, se deja sin hacer
        self.preguntar.connect(self._preguntar)
        self.plan.connect(self._plan)
        self.usando.connect(lambda nombre: self.bloque and self.bloque.paso(herramientas.nombre(nombre)))
        self.setStyleSheet(ESTILO_DIRECTOR)
        # Un chat a página completa: arriba su barra, el chat ocupa lo que sobra y la caja del pedido va siempre abajo,
        # a la vista (antes la galería se comía la mitad y, a 1280×720, el pedido quedaba bajo el borde)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 12, 24, 10)
        lay.setSpacing(8)
        lay.addWidget(self._barra())
        self.chat = Conversacion(self._portada())
        lay.addWidget(self.chat, 1)
        lay.addLayout(_centrada(self._compositor()))
        pista = etiqueta(t("Intro envía · Mayús+Intro, otra línea · Ctrl+Espacio para hablar"), "pista")
        pista.setAlignment(Qt.AlignHCenter)
        lay.addWidget(pista)

        self.altavoz = QMediaPlayer(self)
        self.salida = QAudioOutput(self)
        self.altavoz.setAudioOutput(self.salida)
        self.altavoz.playbackStateChanged.connect(self._fin_de_voz)
        # un MP3 que no se puede reproducir solo da error, sin cambiar de estado: la luz se quedaba encendida y la
        # pregunta «¿Lo hago?» nunca pasaba a escuchar la respuesta
        self.altavoz.errorOccurred.connect(lambda *_: self._fin_de_voz(QMediaPlayer.StoppedState))

    def _barra(self) -> QWidget:
        barra = QWidget()
        barra.setObjectName("barra_chat")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        fila.addWidget(etiqueta(t("Director IA"), "titulo_chat"))
        self.lenta = boton(f"🔑  {t('IA gratis lenta')}")  # sin IA de texto conectada (ver consejo_claves)
        self.lenta.setIcon(icono("key-round", "#FFB454"))
        self.lenta.setStyleSheet("color: #FFB454;")
        self.lenta.hide()
        fila.addWidget(self.lenta)
        fila.addStretch()
        self.nueva = boton(t("Nueva conversación"))
        self.nueva.setIcon(icono("square-pen"))
        self.nueva.setToolTip(t("Empieza de cero. Lo que hiciste sigue en «Mis proyectos»."))
        self.nueva.clicked.connect(self.nueva_conversacion)
        recuerdos = boton(f"🧠  {t('Memoria del estudio')}")
        recuerdos.setToolTip(t("Lo que el Director recuerda de tus gustos: verlo y borrarlo"))
        recuerdos.clicked.connect(lambda: ver_memoria(self))
        fila.addWidget(self.nueva)
        fila.addWidget(recuerdos)
        return barra

    def _portada(self) -> QWidget:
        """Lo que se ve sin mensajes: «¿Qué creamos hoy?» y los ejemplos. Se va con el primer mensaje y solo vuelve
        con «Nueva conversación»."""
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addStretch(2)
        for w in (etiqueta(t("¿Qué creamos hoy?"), "vacio_titulo"),
                  etiqueta(t("Pídemelo como a tu equipo: yo escribo, dibujo, animo, diseño y hago la música. Lo hecho "
                             "sale aquí mismo, listo para descargar."), "vacio_lema")):
            w.setAlignment(Qt.AlignHCenter)
            lay.addWidget(w)
        lay.addSpacing(6)
        self.galeria = galeria_ejemplos(self, self.ver_ejemplo, self.usar_pedido, alto=110)
        self.vigia = vigilar(self, self.galeria.tarjetas)
        lay.addWidget(self.galeria)
        lay.addStretch(3)
        return caja

    def _compositor(self) -> QFrame:
        """La caja del pedido, como la de Inicio: los adjuntos con su miniatura y su «×», el pedido (crece con lo que
        escribes) y, debajo, adjuntar, el modelo de video, los avisos de la voz, «Responder en voz alta», «Hablar» y
        «Hacer»."""
        caja = QFrame()
        caja.setObjectName("compositor")
        caja.setMaximumWidth(ANCHO_CHAT)
        dentro = QVBoxLayout(caja)
        dentro.setContentsMargins(18, 12, 12, 10)
        dentro.setSpacing(8)
        self.caja_adjuntos = QWidget()
        # ponytail: en una fila; con muchos adjuntos los últimos quedan cortados a la derecha (no ensanchan la página)
        self.caja_adjuntos.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.fila_adjuntos = QHBoxLayout(self.caja_adjuntos)
        self.fila_adjuntos.setContentsMargins(0, 0, 0, 0)
        self.fila_adjuntos.setSpacing(8)
        self.caja_adjuntos.hide()
        dentro.addWidget(self.caja_adjuntos)
        self.pedido = CampoPedido()
        self.pedido.setPlaceholderText(t("Ej.: Hazme un anuncio de 20 segundos para mi barbería y un post para Instagram"))
        self.pedido.setAccessibleName(t("Pedido para el Director"))
        self.pedido.enviar.connect(self.enviar)
        self.pedido.soltados.connect(self._sumar)
        dentro.addWidget(self.pedido)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        adjuntar = boton("📎")
        adjuntar.setToolTip(t("Adjuntar fotos, videos, audios o textos para el trabajo"))
        adjuntar.clicked.connect(self._adjuntar)
        # Con qué modelo se hace el video de este pedido (como en CapCut); Automático: lo de «Claves de IA»
        self.modelo = SelectorModelo("director")
        self.estado = etiqueta("", "sub")  # los avisos de la voz y «Espera…»: aquí siempre se ven
        self.estado.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.en_voz = boton("")
        self.en_voz.setCheckable(True)
        self.en_voz.setChecked(True)
        self.en_voz.setIcon(icono("volume-2"))
        self.en_voz.toggled.connect(lambda si: self.en_voz.setIcon(icono("volume-2" if si else "volume-x")))
        nota = t("Solo te escucha cuando pulsas «Hablar» o Ctrl+Espacio, y se para cuando terminas. Tu voz se entiende "
                 "en este PC.")
        self.en_voz.setToolTip(f"{t('Responder en voz alta')}\n{nota}")
        self.en_voz.setAccessibleName(t("Responder en voz alta"))  # después de la ayuda: si no, la tomaría entera
        self.micro = boton(f"🎙️  {t('Hablar')}")
        self.micro.setToolTip(t("Pulsa y habla: te escucha hasta que terminas (Ctrl+Espacio)"))
        self.micro.clicked.connect(self.alternar_voz)
        self.enviar_btn = boton(f"✨  {t('Hacer')}", "principal")
        self.enviar_btn.clicked.connect(self.enviar)
        for w, estira in ((adjuntar, 0), (self.modelo, 0), (self.estado, 1), (self.en_voz, 0), (self.micro, 0),
                          (self.enviar_btn, 0)):
            fila.addWidget(w, estira)
        dentro.addLayout(fila)
        return caja

    def consejo_claves(self, ir_a_claves):
        """Sin IA de texto conectada: funciona con la gratis sin clave, pero tarda (1 respuesta cada 30 s). La
        pastilla de arriba lo dice y lleva a «Claves de IA»."""
        consejo = t("Consejo: ahora pienso con la IA gratis sin clave, que es lenta. Conecta Groq o Gemini (gratis) en "
                    "«Claves de IA» y trabajaré mucho más rápido y mejor.")
        self.lenta.setToolTip(consejo)
        self.lenta.setAccessibleDescription(consejo)
        self.lenta.clicked.connect(ir_a_claves)
        self.lenta.show()

    # ---------- Ejemplos y portada ----------

    def showEvent(self, e):
        if not self.chat.portada.isHidden():  # sin portada no hay galería que mover
            self.vigia.start()
        super().showEvent(e)

    def hideEvent(self, e):
        """Oculta, su vigilancia no recorre las piezas cada 400 ms para nada y ningún GIF se queda abierto."""
        self.vigia.stop()
        quietas(self.galeria.tarjetas)
        super().hideEvent(e)

    def _cerrar_portada(self):
        """Con el primer mensaje, la portada (y su galería) se va y el chat ocupa la página."""
        self.vigia.stop()
        quietas(self.galeria.tarjetas)
        self.chat.portada.hide()

    def usar_pedido(self, pedido: str):
        """«Usar este pedido» de un ejemplo: queda escrito para cambiarlo y pulsar «Hacer». No se envía solo: un
        trabajo puede gastar cuota o dinero, y eso lo decide el usuario."""
        self.pedido.setText(pedido)
        self.pedido.setFocus()

    def ver_ejemplo(self, e: dict):
        return ver_video(self, proyecto_ejemplo(e))

    # ---------- Conversación ----------

    def _decir(self, quien: str, texto: str):
        """Un mensaje suelto (los avisos de la voz): «Director» a la izquierda; el de otro, a la derecha."""
        self._cerrar_portada()
        m = Mensaje(t("Director")) if quien == "Director" else Mensaje(quien, tuyo=True)
        m.parrafo(str(texto))
        self.chat.anadir(m)

    def _plan(self, texto: str):
        """Lo que dice el Director mientras trabaja (su plan, un aviso antes de empezar, la pregunta de lo que cuesta):
        en el mensaje del trabajo, en el orden en que llega."""
        if self.bloque:
            self.bloque.parrafo(texto)
            self.bloque.plan.append(texto)
        else:
            self._decir("Director", texto)

    def _pintar(self, m: dict) -> Mensaje:
        """Un mensaje del historial en el chat: el tuyo con sus adjuntos; el del Director con lo que dijo, lo que hizo
        y sus tarjetas."""
        if m["rol"] == "usuario":
            b = Mensaje(t("Tú"), tuyo=True)
            b.parrafo(m["texto"].split(ARCHIVOS, 1)[0])  # la lista de rutas es para la IA
            if m.get("adjuntos"):
                b.adjuntos(m["adjuntos"], self)
        else:
            b = Mensaje(t("Director"))
            for texto in m.get("plan", []):
                b.parrafo(texto)
            b.plan = list(m.get("plan", []))
            b.terminar(m, self)
        return self.chat.anadir(b)

    def _adjuntar(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, t("Adjuntar archivos"), "",
            f"{t('Fotos, videos, audios y textos ({tipos})', tipos=TIPOS_ADJUNTOS)};;{t('Todos los archivos')} (*)")
        self._sumar(rutas)

    def _sumar(self, rutas: list[str]):
        """Adjunta los elegidos, soltados o pegados (sin repetir)."""
        self.adjuntos += [r for r in dict.fromkeys(rutas) if r not in self.adjuntos]
        self._fichas()

    def _fichas(self):
        """Los adjuntos del pedido, encima del campo: cada uno con su miniatura y su «×»."""
        while (item := self.fila_adjuntos.takeAt(0)) is not None:
            if item.widget():
                item.widget().deleteLater()
        for ruta in self.adjuntos:
            self.fila_adjuntos.addWidget(ficha(self, ruta, 40, lambda _=False, r=ruta: self._quitar(r)))
        self.fila_adjuntos.addStretch()
        self.caja_adjuntos.setVisible(bool(self.adjuntos))

    def _quitar(self, ruta: str):
        self.adjuntos.remove(ruta)
        self._fichas()
        self.pedido.setFocus()

    def ocupado(self) -> bool:
        return bool(self.tarea and self.tarea.isRunning())

    def _avisar(self, texto: str):
        """Un aviso corto junto a «Hacer», 3 s."""
        self.estado.setText(texto)
        QTimer.singleShot(3000, lambda: self.estado.text() == texto and self.estado.setText(""))

    def enviar(self, por_voz: bool = False):
        texto = self.pedido.text().strip()
        if not texto:
            return
        if self.ocupado():  # el campo sigue activo para ir escribiendo lo siguiente
            return self._avisar(t("Espera a que termine el trabajo actual."))
        self.por_voz = por_voz
        adjuntos, self.adjuntos = self.adjuntos, []
        self._fichas()
        self.pedido.clear()
        # La lista va antes de los textos adjuntos: si el pedido se recorta, se recorta el texto y no una ruta
        pedido = texto + (f"{ARCHIVOS}{json.dumps(adjuntos, ensure_ascii=False)}" if adjuntos else "") + "".join(
            map(texto_adjunto, adjuntos))
        usuario = {"rol": "usuario", "texto": pedido, **({"adjuntos": adjuntos} if adjuntos else {})}
        self._cerrar_portada()
        self._pintar(usuario)
        self.bloque = self.chat.anadir(Mensaje(t("Director")))
        self.bloque.trabajando()
        self.enviar_btn.setEnabled(False)
        self.nueva.setEnabled(False)
        if self.brillo and por_voz:
            self.brillo.poner("pensando")
        # La portada de los videos, en el hilo del trabajo; director.dirigir se busca al llamarla (las pruebas la
        # cambian)
        self.tarea = Tarea(lambda **datos: con_portadas(director.dirigir(**datos)), pedido=pedido,
                           historial=list(self.historial), al_usar=self.usando.emit, confirmar=self._confirmar,
                           al_decir=self.plan.emit, modelo_video=self.modelo.valor(), adjuntos=adjuntos)
        self.historial.append(usuario)
        self._guardar()
        self.tarea.progreso.connect(self.bloque.detalle)
        self.tarea.listo.connect(self._listo)
        self.tarea.fallo.connect(self._fallo)
        self.tarea.finished.connect(self._fin_de_tarea)
        self.tarea.start()

    def _terminar(self, m: dict):
        """Cierra el mensaje del trabajo con lo que queda de él y lo guarda en la conversación."""
        if self.bloque is None:
            self._cerrar_portada()
            self.bloque = self.chat.anadir(Mensaje(t("Director")))
        if self.bloque.plan:
            m["plan"] = list(self.bloque.plan)
        self.bloque.terminar(m, self)
        self.bloque = None  # cerrado: lo siguiente va en otro mensaje
        self.historial.append(m)
        self._guardar()

    def _listo(self, r: dict):
        pasos = r.get("pasos") or []
        fallo = [str(p.get("resultado", "")).startswith("ERROR") for p in pasos]
        hechas = list(dict.fromkeys(p["herramienta"] for p, f in zip(pasos, fallo) if not f))
        fallidas = list(dict.fromkeys(p["herramienta"] for p, f in zip(pasos, fallo) if f))
        # con lo hecho y sus archivos: «sigue» o «cámbiale la música» se refieren a eso
        m = {"rol": "director", "texto": r["mensaje"]}
        for clave, valor in (("hecho", r.get("resumen")), ("hechas", hechas), ("fallidas", fallidas),
                             ("resultados", tarjetas_de(r))):
            if valor:
                m[clave] = valor
        self._terminar(m)
        if self.en_voz.isChecked() and self.por_voz:
            self._leer_en_voz(r["mensaje"])

    def _fallo(self, error: str):
        self._terminar({"rol": "director", "texto": t("No pude terminar: {error}", error=error)})
        if self.en_voz.isChecked() and self.por_voz:
            self._leer_en_voz(t("No pude terminar. Te dejé el motivo en el chat."))

    # ---------- Guardar la conversación ----------

    def _guardar(self):
        """Los últimos MAX_GUARDADOS mensajes, en datos/director.json (de una vez: un corte de luz no lo deja a
        medias), con las claves y las tarjetas tapadas (ver tapar). Si no se puede escribir, se sigue igual."""
        del self.historial[:-MAX_GUARDADOS]
        if self.archivo is None:
            return
        mensajes = [{**m, "texto": tapar(m["texto"]), **({"plan": list(map(tapar, m["plan"]))} if "plan" in m else {})}
                    for m in self.historial]
        try:
            diseno.escribir_json(self.archivo, {"version": 1, "mensajes": mensajes})
        except OSError:
            traceback.print_exc()

    def restaurar(self, archivo=CONVERSACION):
        """Al abrir la app: la conversación de la última vez, con sus tarjetas, y desde ahora se guarda ahí."""
        self.archivo = Path(archivo)
        self.historial = cargar_conversacion(self.archivo)
        for m in self.historial:
            self._pintar(m)
        if self.historial:
            self._cerrar_portada()

    def nueva_conversacion(self):
        """Empieza de cero (lo hecho sigue en su carpeta y en «Mis proyectos»): vuelve la portada y se borra lo
        guardado. Mientras trabaja no se puede."""
        if self.ocupado():
            return
        self.chat.vaciar()
        self.historial.clear()
        self.adjuntos.clear()
        self._fichas()
        self.bloque = None
        self.chat.portada.show()
        if self.isVisible():
            self.vigia.start()
        if self.archivo:
            try:
                self.archivo.unlink(missing_ok=True)
            except OSError:
                traceback.print_exc()
        self.pedido.setFocus()

    def _animar(self, ruta: str):
        """«Animar» de una tarjeta: se le pide al Director con la imagen adjunta. Se envía sin preguntar (el clic ya
        es la decisión); si cuesta dinero, el Director pregunta antes con su precio. Lo que estabas escribiendo y
        adjuntando se queda en la caja."""
        if self.ocupado():
            return self._avisar(t("Espera a que termine el trabajo actual."))
        borrador, extra = self.pedido.text(), self.adjuntos
        self.adjuntos = [ruta]
        self.pedido.setText(t("Anima esta imagen."))
        self.enviar()
        self.pedido.setText(borrador)
        self.adjuntos = extra
        self._fichas()

    def _fin_de_tarea(self):
        if self.bloque:
            self.bloque.parar()
            self.bloque = None
        self.enviar_btn.setEnabled(True)
        self.nueva.setEnabled(True)
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
        self._plan(pregunta.split("\n\n", 1)[0])
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
