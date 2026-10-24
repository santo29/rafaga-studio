"""Página «Publicar»: programa los videos de Mis proyectos en YouTube, que los publica solo a la hora elegida aunque el
PC esté apagado. TikTok, Instagram y Facebook, más adelante."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDateTimeEdit, QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QProgressBar,
                               QTextEdit, QVBoxLayout, QWidget)

from motor import claves, publicar, seguro, shorts
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje, mensaje_error, Tarea, tarjeta

GUIA = t("Una sola vez, unos 15 minutos y gratis:\n"
         "1. En Google Cloud crea un proyecto y activa «YouTube Data API v3».\n"
         "2. En «Pantalla de consentimiento de OAuth» elige «Externo» y añade el permiso youtube.upload.\n"
         "3. En «Credenciales» crea un «ID de cliente de OAuth» de tipo «App de escritorio» y descarga su JSON.\n"
         "4. Pulsa «Publicar app» para pasarla a «En producción»: en Testing el permiso caduca a los 7 días.\n"
         "5. Pulsa «Conectar YouTube», elige ese JSON y acepta en el navegador (si dice que la app no está "
         "verificada: Avanzado → Continuar; es tu propia app).\n"
         "Haz la primera prueba con un video corto: con el proyecto sin verificar, YouTube podría dejarlo en privado.")
PROXIMAMENTE = [("TikTok", t("Hará falta un servicio intermediario: TikTok solo deja publicar en público a las apps "
                             "que pasan su auditoría.")),
                ("Instagram", t("Hará falta tu app de Meta o un intermediario: Instagram no acepta una hora futura y "
                                "algo tiene que publicar a esa hora.")),
                ("Facebook", t("Hará falta crear tu app en developers.facebook.com; las Páginas programan solas, como "
                               "YouTube."))]


class PaginaPublicar(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(etiqueta(t("Publicar"), "titulo"))
        lay.addWidget(etiqueta(t("Programa tus videos: se suben ya a YouTube como privados y YouTube los publica solo a "
                                 "la hora que elijas, aunque apagues el PC."), "sub"))
        cuenta, cuenta_lay = tarjeta()
        fila = QHBoxLayout()
        nombre = etiqueta("YouTube")
        nombre.setStyleSheet("font-weight: 700;")
        self.estado = etiqueta("")
        consola = boton(t("Abrir Google Cloud ↗"))
        consola.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://console.cloud.google.com/apis/library/"
                                                                      "youtube.googleapis.com")))
        self.conectar = boton(t("Conectar YouTube"), "principal")
        self.conectar.clicked.connect(self._conectar)
        for w, estira in ((nombre, 0), (self.estado, 1), (consola, 0), (self.conectar, 0)):
            fila.addWidget(w, estira)
        cuenta_lay.addLayout(fila)
        cuenta_lay.addWidget(etiqueta(GUIA, "sub"))
        lay.addWidget(cuenta)

        form, form_lay = tarjeta()
        form_lay.addWidget(etiqueta(t("Video de Mis proyectos"), "sub"))
        self.videos = QListWidget()
        self.videos.setMaximumHeight(150)
        self.videos.currentRowChanged.connect(self._elegir)
        self.titulo = QLineEdit()
        self.titulo.setMaxLength(100)  # el máximo de YouTube
        self.titulo.setPlaceholderText(t("Título (hasta 100 caracteres)"))
        self.descripcion = QTextEdit()
        self.descripcion.setAcceptRichText(False)
        self.descripcion.setFixedHeight(90)
        self.descripcion.setPlaceholderText(t("Descripción"))
        self.hashtags = QLineEdit()
        self.hashtags.setPlaceholderText(t("#hashtags separados por espacios"))
        self.hora = QDateTimeEdit()
        self.hora.setCalendarPopup(True)
        self.hora.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.programar = boton(f"📅  {t('Programar en YouTube')}", "principal")
        self.programar.clicked.connect(self._programar)
        abajo = QHBoxLayout()
        abajo.addWidget(etiqueta(t("Sale el")))
        abajo.addWidget(self.hora)
        abajo.addStretch()
        abajo.addWidget(self.programar)
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.hide()
        self.aviso = etiqueta("", "sub")
        for w in (self.videos, self.titulo, self.descripcion, self.hashtags):
            form_lay.addWidget(w)
        form_lay.addLayout(abajo)
        form_lay.addWidget(self.progreso)
        form_lay.addWidget(self.aviso)
        lay.addWidget(form)

        lay.addWidget(etiqueta(t("Programado"), "sub"))
        self.programados = QListWidget()
        self.programados.setMaximumHeight(150)
        lay.addWidget(self.programados)
        pronto, pronto_lay = tarjeta()
        pronto_lay.addWidget(etiqueta(t("Próximamente"), "sub"))
        for red, frase in PROXIMAMENTE:
            linea = QHBoxLayout()
            nombre = etiqueta(red)
            nombre.setStyleSheet("font-weight: 700;")
            nombre.setFixedWidth(110)
            linea.addWidget(nombre)
            linea.addWidget(etiqueta(frase, "sub"), 1)
            pronto_lay.addLayout(linea)
        lay.addWidget(pronto)
        lay.addStretch()
        self.items, self.tarea = [], None

    def showEvent(self, e):
        self.recargar()
        super().showEvent(e)

    def recargar(self):
        conectado = "youtube" in claves.cargar()
        self.estado.setText(f"✓ {t('Conectado')}" if conectado else t("No conectada"))
        self.estado.setStyleSheet("color: #3DDC97; font-weight: 700;" if conectado else "color: #8D8D9A;")
        # solo videos: las canciones y los diseños de Mis proyectos no se suben a YouTube
        self.items = [r for p in shorts.proyectos() for r in p["resultados"] if isinstance(r, dict)
                      and Path(str(r.get("archivo", ""))).suffix.lower() in seguro.VIDEOS]
        self.videos.clear()
        self.videos.addItems([str(r.get("titulo") or Path(r["archivo"]).stem)[:90] for r in self.items])
        self.programados.clear()
        for h in publicar.historial():
            try:
                hora = datetime.fromisoformat(h["hora"]).astimezone().strftime("%d/%m/%Y %H:%M")
            except (KeyError, TypeError, ValueError):
                hora = "?"
            self.programados.addItem(f"{hora}  ·  YouTube  ·  {str(h.get('titulo', ''))[:70]}  ·  "
                                     f"youtu.be/{h.get('id', '')}")
        minimo = QDateTime.currentDateTime().addSecs(16 * 60)
        self.hora.setMinimumDateTime(minimo)
        if self.hora.dateTime() <= minimo:
            self.hora.setDateTime(QDateTime.currentDateTime().addSecs(3600))

    def _elegir(self, fila):
        if fila < 0:
            return
        r = self.items[fila]
        self.titulo.setText(str(r.get("titulo") or ""))
        self.descripcion.setPlainText(str(r.get("descripcion") or ""))
        self.hashtags.setText(" ".join(h if h.startswith("#") else f"#{h}" for h in r.get("hashtags") or []
                                       if isinstance(h, str)))

    def _ocupado(self) -> bool:
        if self.tarea and self.tarea.isRunning():  # soltar un hilo que corre tumba la app cuando termina
            mensaje(self, t("Estoy trabajando"), t("Espera a que termine el trabajo actual."))
            return True
        return False

    def _conectar(self):
        if self._ocupado():
            return
        ruta, _ = QFileDialog.getOpenFileName(self, t("Elige tu client_secret.json"), "", "JSON (*.json)")
        if not ruta:
            return
        self.conectar.setEnabled(False)
        self.conectar.setText(t("Esperando al navegador…"))
        self.tarea = Tarea(publicar.conectar, cliente=ruta)
        self.tarea.listo.connect(lambda _: (self.recargar(), mensaje(self, t("YouTube conectado"), t(
            "Listo: ya puedes programar videos en tu canal."))))
        self.tarea.fallo.connect(lambda e: mensaje_error(self, t("No se pudo conectar YouTube"), e))
        self.tarea.finished.connect(lambda: (self.conectar.setEnabled(True), self.conectar.setText(
            t("Conectar YouTube"))))
        self.tarea.start()

    def _programar(self):
        fila = self.videos.currentRow()
        if fila < 0:
            return mensaje(self, t("Falta el video"), t("Elige un video de la lista."))
        if self._ocupado():
            return
        hashtags = self.hashtags.text().split()
        descripcion = "\n\n".join(x for x in (self.descripcion.toPlainText().strip(), " ".join(hashtags)) if x)
        self.programar.setEnabled(False)
        self.progreso.setValue(0)
        self.progreso.show()
        self.tarea = Tarea(publicar.programar, archivo=self.items[fila]["archivo"], titulo=self.titulo.text(),
                           descripcion=descripcion, etiquetas=hashtags, red="youtube",
                           fecha_hora=self.hora.dateTime().toString(Qt.ISODate))
        self.tarea.progreso.connect(lambda texto, f: (self.aviso.setText(texto), self.progreso.setValue(int(f * 100))))
        self.tarea.listo.connect(lambda _: (self.recargar(), mensaje(self, t("Programado"), t(
            "YouTube lo publicará solo a esa hora. Hasta entonces queda como privado en tu canal."))))
        self.tarea.fallo.connect(lambda e: mensaje_error(self, t("No se pudo programar"), e))
        self.tarea.finished.connect(lambda: (self.programar.setEnabled(True), self.progreso.hide(),
                                             self.aviso.setText("")))
        self.tarea.start()
