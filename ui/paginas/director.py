"""Página «Director IA»: pides el trabajo por escrito o con la voz y la IA usa todo el estudio para hacerlo.
Arriba, los ejemplos hechos con Ráfaga Studio (carpeta ejemplos/). Aquí vive también la galería de ejemplos que usan
el Director e Inicio: la pieza pintada con su video, el mosaico y la fila que se desplaza."""
import atexit
import html
import json
import threading
import traceback
from itertools import zip_longest
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QObject, QPropertyAnimation, QRectF, QSize, Qt, QThread, QThreadPool, QTimer,
                            QUrl, Signal, Slot)
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QImage, QImageReader, QKeySequence,
                           QLinearGradient, QMovie, QPainter, QPainterPath, QPen, QShortcut)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QScrollArea,
                               QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

from motor import claves, director, ia, idioma, memoria, roles, voz
from motor.idioma import t
from ui.comun import (boton, etiqueta, mensaje, mensaje_error, Reproductor, seccion, Segmentos, Tarea, tarjeta,
                      ver_imagen)
from ui.iconos import icono, poner

EJEMPLOS = Path(__file__).resolve().parent.parent.parent / "ejemplos"
# Piezas que se mueven a la vez en una página (GIF o el MP4 de la elegida del carrusel): cada una es un decodificador.
# ponytail: medido en un portátil de 4 hilos (3 GIF pequeños cuestan poco); en PCs potentes o con GPU se puede subir a 6
MAX_VIVAS = 3
LADO = 720  # las fotos se leen a lo más de este lado: un diseño de 1080×1350 entero ocupa 6 MB de memoria
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


def _imagen(ruta) -> QImage:
    """La foto, leída al pintarla por primera vez (así Inicio abre rápido) y reducida a LADO. Rota o sin archivo, una
    QImage nula: sale el dibujo de relleno."""
    clave = str(ruta)
    if clave not in _FOTOS:
        lector = QImageReader(clave)
        lector.setAutoTransform(True)
        tam = lector.size()
        if tam.isValid() and max(tam.width(), tam.height()) > LADO:
            lector.setScaledSize(tam.scaled(LADO, LADO, Qt.KeepAspectRatio))
        _FOTOS[clave] = lector.read()
    return _FOTOS[clave]


def _proporcion(ruta) -> float:
    """Ancho entre alto de la foto, leyendo solo su cabecera (16:9 si no se puede leer)."""
    clave = str(ruta)
    if clave not in _PROPORCIONES:
        tam = QImageReader(clave).size()
        _PROPORCIONES[clave] = tam.width() / tam.height() if tam.isValid() and tam.height() else 16 / 9
    return _PROPORCIONES[clave]


def _cubrir(p: QPainter, destino: QRectF, imagen: QImage):
    """La imagen recortada para llenar destino sin deformarse; si sobra alto, se corta más abajo que arriba (las caras
    suelen ir arriba)."""
    escala = max(destino.width() / imagen.width(), destino.height() / imagen.height())
    w, h = destino.width() / escala, destino.height() / escala
    p.drawImage(destino, imagen, QRectF((imagen.width() - w) / 2, (imagen.height() - h) * 0.4, w, h))


class _Puente(QObject):
    """Trae al hilo de la ventana los cuadros de MP4 convertidos en otro hilo."""
    cuadro = Signal(object, int, QImage)  # (id de la pieza: no cabe en un int de 32 bits; su vuelta; el cuadro)

    @Slot(object, int, QImage)
    def recibir(self, clave, vuelta, imagen):
        b = _CON_VIDEO.get(clave)
        if b is not None and b.vuelta == vuelta:  # de una reproducción anterior (parada o reiniciada): no vale
            b.convirtiendo = False
            if not imagen.isNull():
                b.cuadro = imagen
                b.update()


_puente = None
_CON_VIDEO = {}  # id(pieza) → la pieza, mientras reproduce su MP4


def _el_puente() -> _Puente:
    global _puente
    if _puente is None:
        _puente = _Puente(QApplication.instance())  # vive con la app: un cuadro tardío nunca llega a un objeto borrado
        _puente.cuadro.connect(_puente.recibir)  # emitido desde el hilo del pool: llega en cola al de la ventana
        atexit.register(lambda: QThreadPool.globalInstance().waitForDone(2000))  # ningún cuadro a medias al salir
    return _puente


def _convertir(cuadro, clave, vuelta, ancho):
    """En un hilo del pool: pasar un cuadro de 720p a imagen tarda unos 18 ms y, en el hilo de la ventana, trababa el
    carrusel (medido: a 30 cuadros por segundo ocupaba más de la mitad del hilo)."""
    try:
        imagen = cuadro.toImage()
        if imagen.width() > ancho > 0:
            imagen = imagen.scaledToWidth(ancho, Qt.SmoothTransformation)
    except Exception:  # un cuadro raro se salta; no tumba nada
        imagen = QImage()
    _el_puente().cuadro.emit(clave, vuelta, imagen)


def _llega(b, cuadro):
    """Un cuadro nuevo del MP4: si el anterior aún se convierte, este se salta (mejor que acumularlos)."""
    if b.convirtiendo or not cuadro.isValid():
        return
    b.convirtiendo = True
    ancho, clave, vuelta = round(b.width() * b.devicePixelRatioF()), id(b), b.vuelta
    QThreadPool.globalInstance().start(lambda: _convertir(cuadro, clave, vuelta, ancho))


class Pieza(QAbstractButton):
    """Un ejemplo pintado a sangre en una tarjeta de esquinas redondas: su foto (o su GIF, o su MP4 mudo si es la
    elegida del carrusel) recortada a la tarjeta, el canto de luz del vidrio y, sobre un degradado oscuro, su título.
    La misma pieza para todas las galerías: el carrusel y las herramientas de Inicio, su mosaico, el de «Ver todo» y la
    fila del Director. leyenda: True (el degradado siempre; los textos los pone quien la usa), "encima" (su título solo
    con el ratón o el foco) o False. Sin foto, un degradado con el icono de «vacio»."""
    RADIO = 16

    def __init__(self, e: dict | None, leyenda="encima", vacio=("sparkles", "#B79CFF")):
        super().__init__()
        self.e, self.leyenda, self.vacio = e or {}, leyenda, vacio
        self.ruta = foto(self.e) if e else None
        self.proporcion = _proporcion(self.ruta) if self.ruta else 16 / 9
        gif, mp4 = (EJEMPLOS / f"{self.e['id']}.gif", video(self.e)) if e else (None, None)
        self.gif = gif if gif and gif.is_file() else None
        self.video = mp4 if mp4 and mp4.is_file() else None
        self.vivo = "gif"  # lo que puede hacer ahora: "gif", "video" (la elegida del carrusel) o None (quieta)
        self.dueno = None  # el botón que la lleva dentro (una herramienta): su ratón también la mueve
        self.contener = False  # en el carrusel, lo vertical o cuadrado va entero, a la derecha, sobre su foto borrosa
        self.apagada = False  # en el carrusel, las que no son la elegida, un poco más oscuras
        self.alto_por_ancho = None  # si se da, su alto sigue a su ancho (las vistas de las herramientas)
        self.insignia = ""  # una pastilla en la esquina («NUEVO»); pintada: con un layout dentro, Qt no usaría
        # heightForWidth de la pieza sino el del layout
        self.peli = self.jugador = self.sumidero = self.cuadro = self._borrosa = None
        self.vuelta, self.convirtiendo = 0, False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)  # como boton(): el anillo del foco, solo con el teclado
        self.setAccessibleName(str(self.e.get("titulo", "")))

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

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):  # como un enlace: Intro también la abre (Espacio ya lo hace)
            return self.click()
        super().keyPressEvent(e)

    def caja(self) -> QRectF | None:
        """Dónde va la foto entera cuando se contiene (carrusel); None si va a sangre."""
        if not (self.contener and self.proporcion < 1.3):
            return None
        margen = round(self.height() * 0.06)
        alto = self.height() - 2 * margen
        ancho = min(alto * self.proporcion, self.width() * 0.5)
        alto = ancho / self.proporcion
        return QRectF(self.width() - margen - ancho, (self.height() - alto) / 2, ancho, alto)

    def _borrosa_de(self, fija: QImage) -> QImage:
        """La foto desenfocada para el fondo (reducirla a 24 px y estirarla con suavizado sale casi gratis)."""
        if self._borrosa is None:
            self._borrosa = fija.scaledToWidth(24, Qt.SmoothTransformation).scaled(
                480, round(480 / max(self.proporcion, 0.1)), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return self._borrosa

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        forma = QPainterPath()
        forma.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), self.RADIO, self.RADIO)
        p.setClipPath(forma)
        p.fillRect(r, QColor("#17171D"))
        fija = _imagen(self.ruta) if self.ruta else QImage()
        imagen = self.cuadro if self.cuadro is not None else fija
        caja = self.caja()
        if imagen.isNull():
            self._pintar_vacio(p, r)
        elif caja is not None:
            _cubrir(p, r, self._borrosa_de(fija if not fija.isNull() else imagen))
            p.fillRect(r, QColor(14, 11, 24, 150))
            for n in range(1, 7):  # sombra suave bajo la foto: QSS no tiene box-shadow
                sombra = QPainterPath()
                sombra.addRoundedRect(caja.adjusted(-n * 2, -n + 2, n * 2, n * 3), 14 + n, 14 + n)
                p.fillPath(sombra, QColor(0, 0, 0, 16))
            marco = QPainterPath()
            marco.addRoundedRect(caja, 12, 12)
            p.save()
            p.setClipPath(marco, Qt.IntersectClip)
            _cubrir(p, caja, imagen)
            p.restore()
            p.setPen(QPen(QColor(255, 255, 255, 46), 1))
            p.drawPath(marco)
        else:
            _cubrir(p, r, imagen)
        encima = self.encima() or self.hasFocus()
        if self.leyenda is True or (self.leyenda == "encima" and encima):
            self._pintar_leyenda(p, r)
        if self.apagada:
            p.fillRect(r, QColor(10, 10, 14, 105))
        if self.insignia:
            self._pintar_insignia(p)
        p.setClipping(False)
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
        p.drawPath(forma)

    def _pintar_vacio(self, p, r):
        nombre, color = self.vacio
        luz = QLinearGradient(r.topLeft(), r.bottomRight())
        c = QColor(color)
        c.setAlpha(80)
        luz.setColorAt(0, c)
        luz.setColorAt(1, QColor(23, 23, 29, 0))
        p.fillRect(r, luz)
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
        caja = QRectF(10, 10, p.fontMetrics().horizontalAdvance(self.insignia) + 18, 20)
        fondo = QLinearGradient(caja.topLeft(), caja.topRight())
        fondo.setColorAt(0, QColor(124, 92, 255, 235))
        fondo.setColorAt(1, QColor(214, 52, 112, 235))
        p.setBrush(fondo)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.drawRoundedRect(caja, 10, 10)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(caja, Qt.AlignCenter, self.insignia)
        p.restore()

    def _pintar_leyenda(self, p, r):
        alto = min(r.height(), max(110, r.height() * 0.62))
        sombra = QLinearGradient(0, r.bottom() - alto, 0, r.bottom())
        sombra.setColorAt(0, QColor(8, 8, 12, 0))
        sombra.setColorAt(0.5, QColor(8, 8, 12, 165))  # oscuro de verdad: los videos traen sus subtítulos abajo
        sombra.setColorAt(1, QColor(8, 8, 12, 246))
        p.fillRect(QRectF(r.left(), r.bottom() - alto, r.width(), alto), sombra)
        titulo = self.accessibleName()
        if self.leyenda == "encima" and titulo:  # el título solo se pinta aquí; en el carrusel van sus etiquetas
            letra = QFont(self.font())
            letra.setPixelSize(14)
            letra.setWeight(QFont.DemiBold)
            p.setFont(letra)
            p.setPen(QColor("#FFFFFF"))
            linea = p.fontMetrics().elidedText(titulo, Qt.ElideRight, round(r.width() - 24))
            p.drawText(QRectF(12, r.bottom() - 34, r.width() - 24, 24), Qt.AlignLeft | Qt.AlignVCenter, linea)


def corriendo(b) -> bool:
    return bool(b.jugador) or bool(b.peli and b.peli.state() == QMovie.Running)


def arrancar(b):
    """Mueve la pieza: su MP4 mudo si es la elegida del carrusel (en grande, el GIF de 240 px se veía borroso y a
    saltos), si no su GIF. El decodificador se crea aquí y se borra al pararla: abierto, Windows no deja reemplazar el
    archivo (ejemplos/crear.py) y ocupa memoria."""
    if b.vivo == "video" and b.video:
        _el_puente()
        b.vuelta, b.convirtiendo = b.vuelta + 1, False
        b.jugador, b.sumidero = QMediaPlayer(b), QVideoSink(b)  # sin salida de audio: mudo
        b.jugador.setVideoSink(b.sumidero)
        b.jugador.setLoops(QMediaPlayer.Infinite)
        _CON_VIDEO[id(b)] = b
        b.sumidero.videoFrameChanged.connect(lambda cuadro: _llega(b, cuadro))
        # roto o sin poder leerse: se queda con su GIF o su foto, sin reintentar
        b.jugador.errorOccurred.connect(lambda *_: (setattr(b, "video", None), b.jugador and parar(b)))
        b.jugador.setSource(QUrl.fromLocalFile(str(b.video)))
        b.jugador.play()
        return
    if not b.peli:
        b.peli = peli = QMovie(str(b.gif), parent=b)
        peli.frameChanged.connect(lambda _: (setattr(b, "cuadro", peli.currentImage()), b.update()))
        # roto: la foto fija, sin reintentar (un archivo que no es GIF avisa dos veces)
        peli.error.connect(lambda _: (setattr(b, "gif", None), b.peli and parar(b)))
    b.peli.start()


def parar(b):
    if b.peli:
        b.peli.stop()
        b.peli.deleteLater()
        b.peli = None
    if b.jugador:
        _CON_VIDEO.pop(id(b), None)
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


def vigilar(padre, piezas: list, limite: int = MAX_VIVAS):
    """Revisa cada 400 ms qué piezas se mueven: así cuenta desplazarse, cambiar de página o de ventana sin engancharse
    a cada cosa. Una sola vigilancia por página, para que el límite sea de la página entera. El reloj muere con
    «padre»."""
    reloj = QTimer(padre)
    reloj.timeout.connect(lambda: animar(piezas, limite))
    reloj.start(400)
    return reloj


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
    coloca a mano: una rejilla dejaba huecos grandes entre piezas de distinto alto. Su alto sigue a su ancho."""
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
        """Cada pieza a la columna más corta; devuelve el alto que ocupa todo."""
        columnas = max(2, min(self.columnas_max, (ancho + self.HUECO) // (self.ancho_min + self.HUECO)))
        col = (ancho - self.HUECO * (columnas - 1)) / columnas
        altos = [0.0] * columnas
        for b in self.piezas:
            c = altos.index(min(altos))
            alto = col / min(max(b.proporcion, 0.56), 1.9)  # ni tiras larguísimas ni rendijas
            if mover:
                b.setGeometry(round(c * (col + self.HUECO)), round(altos[c]), round(col), round(alto))
            altos[c] += alto + self.HUECO
        return max(0, round(max(altos) - self.HUECO))

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


def fila_ejemplos(piezas: list, titulo: str = "", alto: int = 170) -> QWidget:
    """Una fila de piezas del mismo alto, cada una a su proporción, con su título y las flechas ‹ › (solo si no cabe
    entera). Sus piezas, en .tarjetas."""
    contenido = QWidget()
    fila = QHBoxLayout(contenido)
    fila.setContentsMargins(0, 0, 0, 0)
    fila.setSpacing(8)
    caja = QWidget()
    caja.tarjetas = piezas
    for b in piezas:
        b.setFixedSize(round(alto * min(max(b.proporcion, 0.56), 1.78)), alto)
        fila.addWidget(b)
    fila.addStretch()
    caja.carrusel = Carrusel(contenido, alto + 14)  # y la barra fina de abajo
    lay = QVBoxLayout(caja)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    cabecera = QHBoxLayout()
    cabecera.addWidget(etiqueta(titulo, "sub"), 1)
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
        cabecera.addWidget(flecha)
    lay.addLayout(cabecera)
    lay.addWidget(caja.carrusel)
    return caja


def ver_todo(padre, filas: list, usar_pedido=None) -> QDialog:
    """«Ver todo», la vista aérea de la galería: todos los ejemplos en mosaico, con filtros por tipo. Aquí solo se
    mueve el que está bajo el ratón, así nunca hay muchos GIF a la vez. Elegir uno cierra la ventana."""
    ventana = QDialog(padre)
    ventana.setAttribute(Qt.WA_DeleteOnClose)  # sus GIF no se quedan en memoria
    ventana.setWindowTitle(t("Hecho con Ráfaga Studio"))
    ventana.resize(1100, 680)
    lay = QVBoxLayout(ventana)
    filtros = Segmentos()  # la misma cápsula de vidrio que el selector de formato
    for i, nombre in enumerate([t("Todo"), *(titulo for titulo, _, _ in filas)]):
        filtros.opcion(nombre, i).setChecked(i == 0)
    filtros.layout().addWidget(casilla_animar())  # a la altura de la cápsula, no de su luz
    grupo = filtros.grupo
    lay.addWidget(filtros)
    if usar_pedido:
        lay.addWidget(etiqueta(t("Clic derecho: «Usar este pedido» en el Director"), "sub"))
    contenido = QWidget()
    columna = QVBoxLayout(contenido)
    columna.setSpacing(10)
    secciones, piezas = [], []
    for titulo, lista, abrir in filas:
        parte = QWidget()
        col = QVBoxLayout(parte)
        col.setContentsMargins(0, 0, 0, 10)
        col.addWidget(etiqueta(titulo, "sub"))
        de_esta = [pieza_ejemplo(e, lambda e=e, abrir=abrir: (ventana.close(), abrir(e)),
                                 usar_pedido and (lambda p: (ventana.close(), usar_pedido(p)))) for e in lista]
        col.addWidget(Mosaico(de_esta, 200))
        piezas += de_esta
        secciones.append(parte)
        columna.addWidget(parte)
    columna.addStretch()
    grupo.idClicked.connect(lambda i: [s.setVisible(i in (0, n + 1)) for n, s in enumerate(secciones)])
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
    # Intercalados: un video, un diseño… así el mosaico no es un bloque de videos y luego otro de diseños
    pares = [(e, abrir) for _, lista, abrir in filas for e in lista]
    if len(filas) == 2:
        pares = [x for par in zip_longest(*([(e, f[2]) for e in f[1]] for f in filas)) for x in par if x]
    piezas = [pieza_ejemplo(e, lambda e=e, abrir=abrir: abrir(e), usar_pedido) for e, abrir in pares]
    if seccion_de_inicio:
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.addWidget(seccion(t("Hecho con Ráfaga Studio"), t("Ideas reales para empezar: pásales el ratón y mira"),
                              casilla, todo))
        lay.addWidget(Mosaico(piezas))
    else:
        caja, lay = tarjeta()
        cabecera = QHBoxLayout()
        cabecera.addWidget(etiqueta(t("Hecho con Ráfaga Studio"), "sub"), 1)
        cabecera.addWidget(casilla)
        cabecera.addWidget(todo)
        lay.addLayout(cabecera)
        lay.addWidget(fila_ejemplos(piezas))
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
        self.micro = boton(f"🎙️  {t('Hablar')}")
        self.micro.setToolTip(t("Pulsa y habla: te escucha hasta que terminas (Ctrl+Espacio)"))
        self.micro.clicked.connect(self.alternar_voz)
        self.enviar_btn = boton(f"✨  {t('Hacer')}", "principal")
        self.enviar_btn.clicked.connect(self.enviar)
        for w, estira in ((adjuntar, 0), (self.pedido, 1), (self.micro, 0), (self.enviar_btn, 0)):
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
        galeria = galeria_ejemplos(self, self.ver_ejemplo, self.usar_pedido)
        vigilar(self, galeria.tarjetas)
        return galeria

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
        if isinstance(area, QScrollArea):
            QTimer.singleShot(0, lambda: area.ensureWidgetVisible(widget))

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
                           confirmar=self._confirmar, al_decir=self.plan.emit)
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
        botones = [(t("Abrir ajustes de sonido"), lambda: QDesktopServices.openUrl(QUrl("ms-settings:sound")))]             if error == voz.SILENCIADO() else []
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
