"""Página «Director IA»: pides el trabajo por escrito o con la voz y la IA usa todo el estudio para hacerlo.
Arriba, los videos de ejemplo hechos con Ráfaga Studio (carpeta ejemplos/)."""
import html
import json
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QMenu, QProgressBar,
                               QScrollArea, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from motor import director, voz
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje_error, Reproductor, Tarea, tarjeta, ver_imagen
from ui.iconos import poner

EJEMPLOS = Path(__file__).resolve().parent.parent.parent / "ejemplos"
# Qué página usa cada herramienta (su nombre en el menú): la app la ilumina mientras el Director trabaja en ella
PAGINA = {"crear_video": "Crear con IA", "sacar_shorts": "Shorts mágicos", "crear_anuncios": "Anuncios",
          "crear_cancion": "Música", "crear_video_musical": "Música", "producir_cancion": "Cabina de grabación",
          "separar_voz_y_pista": "Cabina de grabación", "crear_diseno": "Diseño", "editar_video": "Editor de video",
          "investigar_nichos": "Nichos virales", "listar_proyectos": "Mis proyectos", "listar_opciones": "Claves de IA",
          "crear_serie": "Dibujos animados", "crear_episodio": "Dibujos animados", "listar_series": "Dibujos animados"}
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


def tarjeta_ejemplo(e: dict, al_pulsar) -> QToolButton:
    """Un ejemplo (video o diseño) con su miniatura y su título, para las galerías del Director y de Inicio."""
    imagen = QPixmap(str(EJEMPLOS / f"{e['id']}.jpg"))
    alto = 176 if imagen.height() > imagen.width() else 135
    b = QToolButton()
    b.setObjectName("ejemplo")
    b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    b.setIcon(QIcon(imagen))
    b.setIconSize(QSize(round(alto * imagen.width() / max(1, imagen.height())), alto))
    b.setText(str(e.get("titulo", ""))[:60])
    b.setToolTip(t("Pedido: «{pedido}»", pedido=str(e.get("pedido", ""))[:300]))
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet("QToolButton { background: transparent; border: none; border-radius: 10px; padding: 6px;"
                    " font-size: 14px; } QToolButton:hover { background: #20202A; }")
    b.clicked.connect(lambda _=False: al_pulsar())
    return b


def fila_ejemplos(lista: list[dict], abrir) -> QScrollArea:
    """Una fila de ejemplos que se desplaza de lado si no cabe: así la página no se sale por la derecha a 1366 px."""
    contenido = QWidget()
    fila = QHBoxLayout(contenido)
    fila.setContentsMargins(0, 0, 0, 0)
    for e in lista:
        fila.addWidget(tarjeta_ejemplo(e, lambda e=e: abrir(e)))
    fila.addStretch()
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
    area.setFixedHeight(230)
    area.setWidget(contenido)
    return area


def galeria_ejemplos(padre, ver_video) -> QWidget:
    """Los ejemplos hechos con el estudio: una fila de videos (ver_video(e) los reproduce) y otra de diseños (se
    abren en grande). Sin ejemplos, no se ve."""
    caja, lay = tarjeta()
    lay.addWidget(etiqueta(t("Hecho con Ráfaga Studio"), "sub"))
    for lista, abrir in ((ejemplos(), ver_video),
                         (disenos(), lambda d: ver_imagen(padre, EJEMPLOS / f"{d['id']}.jpg", str(d.get("titulo", ""))))):
        if lista:
            lay.addWidget(fila_ejemplos(lista, abrir))
    caja.setVisible(bool(ejemplos() or disenos()))
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
        return galeria_ejemplos(self, self.ver_ejemplo)

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
        self.tarea = Tarea(director.dirigir, pedido=pedido, historial=list(self.historial), al_usar=self.usando.emit)
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

    # ---------- Voz ----------

    def alternar_voz(self):
        """Empieza a escuchar; si ya escucha, para y entiende lo dicho hasta ahí; si está hablando, se calla."""
        if self.altavoz.playbackState() == QMediaPlayer.PlayingState:
            self.altavoz.stop()
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
        self.lectura.fallo.connect(lambda _: self.brillo and self.brillo.poner(None))
        self.lectura.start()

    def _fin_de_voz(self, estado):
        if self.brillo:
            self.brillo.poner("hablando" if estado == QMediaPlayer.PlayingState else
                              "escuchando" if self.escucha and self.escucha.isRunning() else
                              "pensando" if self.ocupado() and self.por_voz else None)

    def cerrar(self):
        """Al cerrar la app: deja de escuchar y de hablar, y nada de lo que termine después hace nada."""
        self.altavoz.stop()
        hilos = [h for h in (self.escucha, self.lectura, self.tarea, *self._viejas) if h]
        for hilo in hilos:
            hilo.blockSignals(True)
        if self.escucha and self.escucha.isRunning():
            self.escucha.cerrando = True
            self.escucha.detener.set()
        for hilo in hilos:
            hilo.wait(10_000)  # ponytail: una herramienta del Director a medias no se puede parar; pasado esto se cierra
