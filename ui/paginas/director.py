"""Página «Director IA»: pides el trabajo por escrito o con la voz y la IA usa todo el estudio para hacerlo.
Arriba, los videos de ejemplo hechos con Ráfaga Studio (carpeta ejemplos/)."""
import html
import json
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QIcon, QMovie, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QScrollArea, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from motor import claves, director, memoria, roles, voz
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje_error, Reproductor, Tarea, tarjeta, ver_imagen
from ui.iconos import icono, poner

EJEMPLOS = Path(__file__).resolve().parent.parent.parent / "ejemplos"
# ponytail: medido en un portátil de 4 hilos (3 GIF pequeños cuestan poco); en PCs potentes o con GPU se puede subir a 6
MAX_VIVAS = 3
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
    """Los diseños de ejemplo de ejemplos/disenos.json que tienen su imagen ({id}.jpg)."""
    try:
        lista = json.loads((EJEMPLOS / "disenos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in lista if isinstance(e, dict) and (EJEMPLOS / f"{e.get('id')}.jpg").is_file()]


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


def tarjeta_ejemplo(e: dict, al_pulsar, usar_pedido=None) -> QToolButton:
    """Un ejemplo (video o diseño) con su miniatura y su título, para las galerías del Director y de Inicio. Si hay
    ejemplos/{id}.gif, se mueve cuando animar() lo deja; con usar_pedido(pedido), el clic derecho lo ofrece."""
    imagen = QPixmap(str(EJEMPLOS / f"{e['id']}.jpg"))
    alto = 176 if imagen.height() > imagen.width() else 135
    b = QToolButton()
    b.setObjectName("ejemplo")
    b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    b.foto = QIcon(imagen)
    b.setIcon(b.foto)
    b.setIconSize(QSize(round(alto * imagen.width() / max(1, imagen.height())), alto))
    b.setText(str(e.get("titulo", ""))[:60])
    pedido = str(e.get("pedido") or "")
    b.setToolTip(t("Pedido: «{pedido}»", pedido=pedido[:300]))
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet("QToolButton { background: transparent; border: none; border-radius: 10px; padding: 6px;"
                    " font-size: 14px; } QToolButton:hover { background: #20202A; }")
    b.clicked.connect(lambda _=False: al_pulsar())
    if usar_pedido and pedido:  # el «Recrear» de las galerías de IA: la galería es el punto de partida
        b.setToolTip(f"{b.toolTip()}\n{t('Clic derecho: «Usar este pedido» en el Director')}")
        # su propio menú: con addAction, el QToolButton pintaría una flechita y un clic lento abriría el menú
        menu = QMenu(b)
        menu.addAction(t("Usar este pedido")).triggered.connect(lambda: usar_pedido(pedido))
        b.setContextMenuPolicy(Qt.CustomContextMenu)
        b.customContextMenuRequested.connect(lambda punto: menu.exec(b.mapToGlobal(punto)))
    # Un GIF pequeño con QMovie, no el MP4: 3 MP4 de 720p a la vez gastaban casi un núcleo de un portátil de 4 hilos
    gif = EJEMPLOS / f"{e['id']}.gif"
    b.gif = gif if gif.is_file() else None  # sin GIF (los diseños): se queda la miniatura fija
    b.peli = None  # su QMovie, solo mientras se mueve (ver arrancar)
    return b


def arrancar(b):
    """Mueve la tarjeta. Su QMovie se crea aquí y se borra al pararla: abierto, Windows no deja reemplazar el GIF
    (ejemplos/crear.py) y su decodificador ocupa memoria."""
    if not b.peli:
        b.peli = peli = QMovie(str(b.gif), parent=b)
        peli.frameChanged.connect(lambda _: b.setIcon(QIcon(peli.currentPixmap())))
        # roto: la miniatura, sin reintentar (un archivo que no es GIF avisa dos veces)
        peli.error.connect(lambda _: (setattr(b, "gif", None), b.peli and parar(b)))
    b.peli.start()


def parar(b):
    b.peli.stop()
    b.peli.deleteLater()
    b.peli = None
    b.setIcon(b.foto)  # el JPG tiene mejor color que el cuadro del GIF


def animar(tarjetas: list, limite: int = MAX_VIVAS):
    """Mueve las tarjetas con GIF que se ven (como mucho «limite») y la que está bajo el ratón; las demás, quietas con
    su JPG. Nada se mueve con la casilla apagada, la ventana sin foco o la página oculta (visibleRegion vacía)."""
    si = accion_animar().isChecked()
    vistas = [b for b in tarjetas if si and b.gif and b.window().isActiveWindow() and not b.visibleRegion().isEmpty()]
    vivas = [b for b in vistas if b.underMouse()] + [b for b in vistas if not b.underMouse()][:limite]
    for b in tarjetas:
        if b in vivas and not (b.peli and b.peli.state() == QMovie.Running):
            arrancar(b)
        elif b.peli and b not in vivas:
            parar(b)


def vigilar(padre, tarjetas: list, limite: int = MAX_VIVAS):
    """Revisa cada 400 ms qué tarjetas se mueven: así cuenta desplazarse, cambiar de página o de ventana sin engancharse
    a cada cosa. El reloj muere con «padre»."""
    reloj = QTimer(padre)
    reloj.timeout.connect(lambda: animar(tarjetas, limite))
    reloj.start(400)


class Carrusel(QScrollArea):
    """Fila que se desplaza de lado si no cabe (así la página no se sale por la derecha a 1366 px): con las flechas
    de su cabecera, animado, y con la rueda del ratón."""

    def __init__(self, contenido: QWidget):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.setFixedHeight(230)
        self.setWidget(contenido)
        self.animacion = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self.animacion.setDuration(350)
        self.animacion.setEasingCurve(QEasingCurve.OutCubic)

    def mover(self, sentido: int):
        """Una pantalla a la derecha (1) o a la izquierda (-1)."""
        barra = self.horizontalScrollBar()
        self.animacion.stop()
        self.animacion.setStartValue(barra.value())
        self.animacion.setEndValue(max(0, min(barra.maximum(), barra.value() + sentido * barra.pageStep())))
        self.animacion.start()

    def wheelEvent(self, e):
        """La rueda mueve la fila de lado; en el borde, la página sigue bajando como siempre."""
        self.animacion.stop()
        barra, giro = self.horizontalScrollBar(), e.angleDelta()
        antes = barra.value()
        barra.setValue(antes - (giro.x() if abs(giro.x()) > abs(giro.y()) else giro.y()))
        if barra.value() == antes:
            e.ignore()


def fila_ejemplos(lista: list[dict], abrir, titulo: str = "", usar_pedido=None) -> QWidget:
    """Una fila de ejemplos con su título y las flechas ‹ › (solo si no cabe entera). Sus tarjetas, en .tarjetas."""
    contenido = QWidget()
    fila = QHBoxLayout(contenido)
    fila.setContentsMargins(0, 0, 0, 0)
    caja = QWidget()
    caja.tarjetas = [tarjeta_ejemplo(e, lambda e=e: abrir(e), usar_pedido) for e in lista]
    for b in caja.tarjetas:
        fila.addWidget(b)
    fila.addStretch()
    caja.carrusel = Carrusel(contenido)
    lay = QVBoxLayout(caja)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
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
    """«Ver todo», la vista aérea del carrusel: todos los ejemplos en rejilla, con filtros por fila. Aquí solo se
    mueve el que está bajo el ratón, así nunca hay muchos GIF a la vez. Elegir uno cierra la ventana."""
    ventana = QDialog(padre)
    ventana.setAttribute(Qt.WA_DeleteOnClose)  # sus GIF no se quedan en memoria
    ventana.setWindowTitle(t("Hecho con Ráfaga Studio"))
    ventana.resize(1100, 680)
    lay = QVBoxLayout(ventana)
    filtros = QHBoxLayout()
    grupo = QButtonGroup(ventana)
    for i, nombre in enumerate([t("Todo"), *(titulo for titulo, _, _ in filas)]):
        chip = QPushButton(nombre)
        chip.setObjectName("formato")
        chip.setCheckable(True)
        chip.setChecked(i == 0)
        grupo.addButton(chip, i)
        filtros.addWidget(chip)
    filtros.addStretch()
    filtros.addWidget(casilla_animar())
    lay.addLayout(filtros)
    if usar_pedido:
        lay.addWidget(etiqueta(t("Clic derecho: «Usar este pedido» en el Director"), "sub"))
    contenido = QWidget()
    columna = QVBoxLayout(contenido)
    secciones, tarjetas = [], []
    for titulo, lista, abrir in filas:
        seccion = QWidget()
        rejilla = QGridLayout(seccion)
        rejilla.addWidget(etiqueta(titulo, "sub"), 0, 0, 1, 3)
        for n, e in enumerate(lista):
            b = tarjeta_ejemplo(e, lambda e=e, abrir=abrir: (ventana.close(), abrir(e)),
                                usar_pedido and (lambda p: (ventana.close(), usar_pedido(p))))
            rejilla.addWidget(b, 1 + n // 3, n % 3)
            tarjetas.append(b)
        secciones.append(seccion)
        columna.addWidget(seccion)
    columna.addStretch()
    grupo.idClicked.connect(lambda i: [s.setVisible(i in (0, n + 1)) for n, s in enumerate(secciones)])
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(contenido)
    lay.addWidget(area, 1)
    vigilar(ventana, tarjetas, 0)
    ventana.show()
    return ventana


def galeria_ejemplos(padre, ver_video, usar_pedido=None, seccion=False) -> QWidget:
    """Los ejemplos hechos con el estudio: una fila de videos (ver_video(e) los reproduce) y otra de diseños (se
    abren en grande), con «Ver todo» y la casilla «Animar vistas previas». En Inicio (seccion) va sin marco y con
    título de sección. Sin ejemplos, no se ve. Sus tarjetas, en .tarjetas."""
    if seccion:
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 12, 0, 0)
    else:
        caja, lay = tarjeta()
    cabecera = QHBoxLayout()
    cabecera.addWidget(etiqueta(t("Hecho con Ráfaga Studio"), "seccion" if seccion else "sub"), 1)
    cabecera.addWidget(casilla_animar())
    todo = boton(t("Ver todo"))
    cabecera.addWidget(todo)
    lay.addLayout(cabecera)
    filas = [f for f in ((t("Videos"), ejemplos(), ver_video),
                         (t("Diseños"), disenos(),
                          lambda d: ver_imagen(padre, EJEMPLOS / f"{d['id']}.jpg", str(d.get("titulo", ""))))) if f[1]]
    caja.tarjetas = []
    for titulo, lista, abrir in filas:
        fila = fila_ejemplos(lista, abrir, titulo, usar_pedido)
        caja.tarjetas += fila.tarjetas
        lay.addWidget(fila)
    todo.clicked.connect(lambda: ver_todo(padre, filas, usar_pedido))
    vigilar(caja, caja.tarjetas)  # MAX_VIVAS para toda la galería (las dos filas): es la página entera
    caja.setVisible(bool(filas))
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
    entendiendo = Signal()
    texto = Signal(str)
    fallo = Signal(str)

    def __init__(self):
        super().__init__()
        self.detener = threading.Event()
        self.cerrando = False  # la app se cierra: lo grabado no se transcribe ni se manda

    def run(self):
        try:
            audio = voz.escuchar(self.detener, self.nivel.emit)
            if self.cerrando:
                return
            self.entendiendo.emit()
            self.texto.emit(voz.entender(audio))
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
        self.pedido.setPlaceholderText(t("Ej: Hazme un anuncio de 20 segundos para mi barbería y un post para Instagram"))
        self.pedido.returnPressed.connect(self.enviar)
        self.micro = boton(f"🎙️  {t('Hablar')}")
        self.micro.setToolTip(t("Habla y suelta: escucha solo mientras está activo (Ctrl+Espacio)"))
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
        return galeria_ejemplos(self, self.ver_ejemplo, self.usar_pedido)

    def usar_pedido(self, pedido: str):
        """«Usar este pedido» de un ejemplo: queda escrito para cambiarlo y pulsar «Hacer». No se envía solo: un
        trabajo puede gastar cuota o dinero, y eso lo decide el usuario."""
        self.pedido.setText(pedido)
        self.pedido.setFocus()
        # setFocus no desplaza la página, y la galería deja el campo debajo, fuera de la pantalla
        area = self.parentWidget().parentWidget() if self.parentWidget() else None  # app.py la pone en un QScrollArea
        if isinstance(area, QScrollArea):
            QTimer.singleShot(0, lambda: area.ensureWidgetVisible(self.pedido))

    def ver_ejemplo(self, e: dict):
        guion = e.get("guion") or {}
        self.reproductor.show()
        self.reproductor.mostrar({"formato": e.get("formato", "9:16"), "resultados": [{
            "archivo": str(EJEMPLOS / f"{e['id']}.mp4"), "titulo": str(e.get("titulo", "")),
            "descripcion": str(guion.get("descripcion", "")), "hashtags": list(guion.get("hashtags", []))}]})

    # ---------- Conversación ----------

    def _decir(self, quien: str, texto: str):
        color = "#7C5CFF" if quien == "Director" else "#FF4D8D"
        cuerpo = html.escape(str(texto)).replace("\n", "<br>")  # lo que dice la IA nunca se interpreta como HTML
        self.chat.append(f"<p><b style='color:{color}'>{html.escape(quien)}</b><br>{cuerpo}</p>")
        self.dicho = str(texto)

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
        self._decir("Director", pregunta.removeprefix(self.dicho).strip() or pregunta)  # el plan ya está en el chat
        self.caja = caja = QMessageBox(QMessageBox.Question, t("¿Lo hago?"), pregunta,
                                       QMessageBox.Yes | QMessageBox.No, self)
        caja.setTextFormat(Qt.PlainText)  # parte del texto lo escribió la IA: nunca se interpreta como HTML
        caja.setDefaultButton(QMessageBox.No)  # un Enter por despiste no gasta
        caja.finished.connect(lambda _: self._contestar(
            caja.clickedButton() is not None and caja.standardButton(caja.clickedButton()) == QMessageBox.Yes))
        caja.open()
        if self.por_voz:
            self.intentos = 3
            self._leer_en_voz(pregunta)  # al terminar de decirla (_fin_de_voz), o si no pudo, escucha la respuesta

    def _escuchar_respuesta(self):
        if not self.caja or (self.escucha and self.escucha.isRunning()):
            return
        self.escucha = Escucha()
        self.escucha.nivel.connect(lambda v: self.brillo and self.brillo.oir(v))
        self.escucha.texto.connect(self._respuesta_oida)
        self.escucha.fallo.connect(
            lambda _: self.estado.setText(t("No pude usar el micrófono: contesta en la ventana.")))
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
            self.escucha.detener.set()
            return
        if self.ocupado():
            return mensaje_error(self, t("Estoy trabajando"), t("Espera a que termine el trabajo actual."))
        self._soltar_lectura()  # la respuesta hablada que se estaba preparando ya no suena: ahora hablas tú
        self.escucha = Escucha()
        self.escucha.nivel.connect(lambda v: self.brillo and self.brillo.oir(v))
        self.escucha.entendiendo.connect(lambda: (self.estado.setText(t("Entendiendo lo que dijiste…")),
                                                  self.brillo and self.brillo.poner("pensando")))
        self.escucha.texto.connect(self._oido)
        self.escucha.fallo.connect(lambda e: (self.brillo and self.brillo.poner(None), self._volver_micro(),
                                              mensaje_error(self, t("No pude usar el micrófono"), e)))
        self.escucha.start()
        poner(self.micro, f"⏹  {t('Parar')}")
        self.estado.setText(t("Te escucho… habla y haz una pausa al terminar."))
        if self.brillo:
            self.brillo.poner("escuchando")

    def _volver_micro(self):
        poner(self.micro, f"🎙️  {t('Hablar')}")
        self.estado.setText("")

    def _oido(self, texto: str):
        self._volver_micro()
        if not texto:
            if self.brillo:
                self.brillo.poner(None)
            self.estado.setText(t("No te entendí. Pulsa «Hablar» e inténtalo otra vez."))
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
