"""Página «Música»: canciones con IA y su video musical."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QSpinBox, QTextEdit

from motor import musica, seguro, video_musical
from motor.idioma import t
from ui.comun import archivo_valido, boton, etiqueta, mensaje, PaginaTrabajo, SelectorFormato, tarjeta


class PaginaMusica(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Estudio de música"), t("Describe la canción. La IA escribe la letra y produce la canción "
                                                   "con voz o solo la pista, en cualquier género."))
        self.idea = QTextEdit()
        self.idea.setPlaceholderText(t("Ej: un dembow de calle sobre salir el viernes con los panas, coro pegajoso"))
        self.idea.setFixedHeight(90)
        self.genero = QComboBox()
        self.genero.setEditable(True)  # se puede escribir cualquier otro género
        self.generos = {t(g): g for g in musica.GENEROS}  # se ve traducido; al motor va la clave
        self.genero.addItems(self.generos)
        self.voz = QComboBox()
        self.voz.addItems([t("Canción con voz y letra"), t("Solo pista (instrumental)")])
        self.segundos = QSpinBox()
        self.segundos.setRange(30, 300)
        self.segundos.setValue(150)
        self.segundos.setSuffix(f" {t('segundos')}")
        fila = QHBoxLayout()
        fila.addWidget(self.genero, 2)
        fila.addWidget(self.voz, 1)
        fila.addWidget(self.segundos)
        self.iniciar = boton(f"🎵  {t('Crear canción')}", "principal")
        self.iniciar.clicked.connect(self._iniciar)
        self.form_lay.addWidget(self.idea)
        self.form_lay.addLayout(fila)
        self.form_lay.addWidget(etiqueta(t("Necesita una clave de música: ElevenLabs (plan de pago) o Gemini "
                                           "(Lyria 3.5, ~$0.08 por canción)."), "sub"))
        self.form_lay.addWidget(self.iniciar, 0, Qt.AlignRight)

        # Video musical: de la canción recién creada o de cualquier canción del PC.
        clip, clip_lay = tarjeta()
        clip_lay.addWidget(etiqueta(f"🎬  {t('Video musical')}", "sub"))
        clip_lay.addWidget(etiqueta(t("Escenas que van con la canción, ondas que se mueven con el sonido y la letra "
                                      "estilo karaoke. Con tu nube Modal, las primeras escenas se animan de verdad. "
                                      "Para sincronizar la letra, la canción se escucha con tu IA de transcripción "
                                      "(Groq u OpenAI si las conectaste; si no, en tu PC).")))
        fila_archivo = QHBoxLayout()
        self.cancion = QLineEdit()
        self.cancion.setPlaceholderText(t("Canción (se llena sola al crear una, o elige un archivo)"))
        examinar = boton(t("Elegir canción…"))
        examinar.clicked.connect(self._elegir_cancion)
        fila_archivo.addWidget(self.cancion, 1)
        fila_archivo.addWidget(examinar)
        self.idea_video = QLineEdit()
        self.idea_video.setPlaceholderText(t("Idea para el video (opcional). Ej: discoteca de los 90 con luces de "
                                             "neón"))
        self.formato_video = SelectorFormato()
        self.hacer_video = boton(f"🎬  {t('Hacer video musical')}", "principal")
        self.hacer_video.clicked.connect(self._video)
        clip_lay.addLayout(fila_archivo)
        clip_lay.addWidget(self.idea_video)
        clip_lay.addWidget(self.formato_video)
        clip_lay.addWidget(self.hacer_video, 0, Qt.AlignRight)
        self.lay.insertWidget(3, clip)
        self.ultima = {}

    def _genero(self):
        texto = self.genero.currentText()
        return self.generos.get(texto, texto)

    def _iniciar(self):
        idea = self.idea.toPlainText().strip()
        if not idea:
            return mensaje(self, t("Falta la idea"), t("Describe la canción que quieres."))
        if self.lanzar(self.iniciar, musica.crear, idea=idea, genero=self._genero(),
                       con_voz=self.voz.currentIndex() == 0, segundos=self.segundos.value()):
            self.tarea.listo.connect(self._cancion_lista)

    def _cancion_lista(self, proyecto):
        r = proyecto["resultados"][0]
        self.ultima = {"titulo": r["titulo"], "genero": proyecto.get("genero", ""),
                       "letra": (Path(proyecto["carpeta"]) / "letra.txt").read_text(encoding="utf-8")}
        self.cancion.setText(r["archivo"])

    def _elegir_cancion(self):
        ruta, _ = QFileDialog.getOpenFileName(self, t("Canción"), "",
                                              t("Audio ({tipos})", tipos="*.mp3 *.wav *.m4a *.ogg *.flac"))
        if ruta:
            self.cancion.setText(ruta)
            self.ultima = {}  # una canción de fuera no trae letra: se saca escuchándola

    def _video(self):
        ruta = self.cancion.text().strip()
        if not archivo_valido(self, ruta, seguro.AUDIOS, t("canción")):
            return
        self.lanzar(self.hacer_video, video_musical.crear, cancion=ruta, formato=self.formato_video.valor(),
                    idea=self.idea_video.text(), titulo=self.ultima.get("titulo", ""),
                    letra=self.ultima.get("letra", ""), genero=self.ultima.get("genero", self._genero()))
