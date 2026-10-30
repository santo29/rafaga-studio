"""Página «Cabina de grabación»: grabar, afinar, mezclar, masterizar y separar voz y pista."""
import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QSlider

from motor import cabina, seguro
from motor.idioma import t
from ui.comun import (AccionesResultado, archivo_valido, boton, campo_archivo, etiqueta, mensaje, mensaje_error,
                      PaginaTrabajo, Tarea, tarjeta)


AUDIO = t("Audio ({tipos})", tipos="*.mp3 *.wav *.m4a *.ogg *.flac")


class PaginaCabina(PaginaTrabajo):
    """Estudio de grabación: grabar sobre la pista, afinar, mezclar, masterizar y separar voz/pista."""
    def __init__(self):
        super().__init__(t("Cabina de grabación"), t("Graba tu voz sobre la pista y la IA hace el trabajo del "
                                                     "ingeniero: afina, limpia, comprime, ecualiza, pone delay y "
                                                     "reverb a tempo, mezcla y masteriza. Todo en tu PC, gratis: tu "
                                                     "voz no sale de aquí."))
        self.form_lay.addWidget(etiqueta(t("1 · Pista"), "sub"))
        fila, self.pista = campo_archivo(t("La pista (beat) sobre la que vas a cantar"), AUDIO)
        self.form_lay.addLayout(fila)

        self.form_lay.addWidget(etiqueta(t("2 · Graba tu voz (usa auriculares para que la pista no se cuele en el "
                                           "micro)"), "sub"))
        fila = QHBoxLayout()
        self.micro = QComboBox()
        self._cargar_micros()
        self.grabar_btn = boton(f"🔴  {t('Grabar')}", "principal")
        self.grabar_btn.clicked.connect(self._grabar)
        self.parar_btn = boton(f"⏹  {t('Parar')}")
        self.parar_btn.setEnabled(False)
        self.parar_btn.clicked.connect(lambda: self.detener.set())
        fila.addWidget(self.micro, 1)
        fila.addWidget(self.grabar_btn)
        fila.addWidget(self.parar_btn)
        self.form_lay.addLayout(fila)
        fila, self.voz = campo_archivo(t("La voz grabada (se llena sola al grabar, o elige una toma)"), AUDIO)
        self.form_lay.addLayout(fila)
        self.toma = AccionesResultado("secundario")  # la toma recién grabada: dónde quedó y descargarla
        # Solo mientras el campo tiene esa toma: con otra elegida, «Descargar» copiaría una que no es la que se ve
        self.voz.textChanged.connect(lambda s: self.toma.setVisible(self.toma.archivo is not None
                                                                    and str(self.toma.archivo) == s))
        self.form_lay.addWidget(self.toma)

        self.form_lay.addWidget(etiqueta(t("3 · Producir"), "sub"))
        fila = QHBoxLayout()
        self.estilo = QComboBox()
        for estilo in cabina.PRESETS:  # se ve traducido; la clave va en el dato
            self.estilo.addItem(t(estilo), estilo)
        self.afinacion = QSlider(Qt.Horizontal)
        self.afinacion.setRange(0, 100)
        self.afinacion.setValue(60)
        self.texto_afinacion = etiqueta(t("Afinación {v}%", v=60))
        self.texto_afinacion.setFixedWidth(120)
        self.afinacion.valueChanged.connect(lambda v: self.texto_afinacion.setText(t("Afinación {v}%", v=v)))
        fila.addWidget(self.estilo, 1)
        fila.addWidget(self.texto_afinacion)
        fila.addWidget(self.afinacion, 1)
        self.form_lay.addLayout(fila)
        fila, self.referencia = campo_archivo(t("Canción de referencia para el master (opcional: suena como esta)"),
                                              AUDIO)
        self.form_lay.addLayout(fila)
        self.titulo_cancion = QLineEdit()
        self.titulo_cancion.setPlaceholderText(t("Título de la canción"))
        self.producir = boton(f"🎚️  {t('Producir canción')}", "principal")
        self.producir.clicked.connect(self._producir)
        fila = QHBoxLayout()
        fila.addWidget(self.titulo_cancion, 1)
        fila.addWidget(self.producir)
        self.form_lay.addLayout(fila)

        separar_caja, separar_lay = tarjeta()
        separar_lay.addWidget(etiqueta(f"✂️  {t('Separar voz y pista de cualquier canción (voz a capela + instrumental)')}",
                                       "sub"))
        fila, self.para_separar = campo_archivo(t("Canción a separar"), AUDIO)
        self.separar_btn = boton(t("Separar"))
        self.separar_btn.clicked.connect(self._separar)
        fila.addWidget(self.separar_btn)
        separar_lay.addLayout(fila)
        separar_lay.addWidget(etiqueta(t("Se hace en tu PC (tarda unos minutos): tu canción no sale de aquí."), "sub"))
        self.lay.insertWidget(3, separar_caja)
        self.detener = threading.Event()

    def _cargar_micros(self):
        try:
            import sounddevice as sd
            entradas = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
                        if d["max_input_channels"] > 0 and d["hostapi"] == sd.default.hostapi]
        except Exception:  # sin tarjeta de sonido o sin permisos de micrófono
            entradas = []
        self.micro.addItem(t("Micrófono por defecto"), None)
        for i, nombre in entradas:
            self.micro.addItem(f"🎤 {nombre}", i)

    def _grabar(self):
        pista = archivo_valido(self, self.pista.text().strip(), seguro.AUDIOS, t("pista"))
        if not pista:
            return
        tomas = cabina.PROYECTOS.parent / "grabaciones"
        tomas.mkdir(parents=True, exist_ok=True)
        destino = tomas / time.strftime("toma_%Y%m%d-%H%M%S.wav")
        pista_wav = tomas / "pista_para_grabar.wav"
        if self.tarea and self.tarea.isRunning():  # soltar un hilo que corre tumba la app (ver PaginaTrabajo.lanzar)
            return mensaje(self, t("Estoy trabajando"), t("Espera a que termine el trabajo actual."))
        self.detener.clear()
        self.parar_btn.setEnabled(True)

        def grabar(aviso):
            cabina.a_wav(pista, pista_wav)
            cabina.grabar(pista_wav, destino, self.detener, self.micro.currentData(), aviso)
            return {"archivo": str(destino)}
        self.grabar_btn.setEnabled(False)
        self.progreso.show()
        self.tarea = Tarea(grabar)
        self.tarea.progreso.connect(lambda t, f: (self.estado.setText(t), self.progreso.setValue(int(f * 100))))
        self.tarea.listo.connect(lambda r: (self.voz.setText(r["archivo"]), self.estado.setText(
            f"✅ {t('Toma guardada. Ahora pulsa «Producir canción».')}")))
        self.tarea.listo.connect(lambda r: self.toma.mostrar(r["archivo"]))
        self.tarea.fallo.connect(lambda e: mensaje_error(self, t("No se pudo grabar"), e))
        self.tarea.finished.connect(lambda: (self.grabar_btn.setEnabled(True), self.parar_btn.setEnabled(False),
                                             self.progreso.hide()))
        self.tarea.start()

    def _producir(self):
        pista, voz = self.pista.text().strip(), self.voz.text().strip()
        if not (archivo_valido(self, pista, seguro.AUDIOS, t("pista"))
                and archivo_valido(self, voz, seguro.AUDIOS, t("voz"))):
            return
        self.lanzar(self.producir, cabina.sesion, pista=pista, voz=voz, estilo=self.estilo.currentData(),
                    fuerza_afinacion=self.afinacion.value() / 100, referencia=self.referencia.text().strip(),
                    titulo=self.titulo_cancion.text().strip() or t("Mi canción"))

    def _separar(self):
        cancion = self.para_separar.text().strip()
        if not archivo_valido(self, cancion, seguro.AUDIOS, t("canción")):
            return
        if self.lanzar(self.separar_btn, cabina.separar_cancion, cancion=cancion):
            self.tarea.listo.connect(self._usar_separada)

    def _usar_separada(self, p):
        """Una canción de fuera (Suno u otra app) queda lista para «Producir canción»: mezcla y master. Sin pisar el
        trabajo en curso: voz y pista solo si las dos están vacías (siempre de una misma canción); el título, igual."""
        if not (self.voz.text().strip() or self.pista.text().strip()):
            self.voz.setText(p["resultados"][0]["archivo"])
            self.pista.setText(p["resultados"][1]["archivo"])
        if not self.titulo_cancion.text().strip():
            self.titulo_cancion.setText(p["titulo"])
