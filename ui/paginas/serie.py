"""Página «Serie animada»: creas tu serie con sus personajes y después sus capítulos, uno tras otro."""
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QSpinBox, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from motor import serie
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje, mensaje_error, PaginaTrabajo, SelectorFormato, Tarea


def _caja():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    return w, lay


class PaginaSerie(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Serie animada"), t("Tu propia serie de dibujos animados: la IA inventa los personajes y "
                                               "escribe cada capítulo, y las imágenes, el movimiento y las voces salen "
                                               "solos. Los personajes se mantienen iguales en todos los capítulos."))
        fila = QHBoxLayout()
        self.series = QComboBox()
        self.series.currentIndexChanged.connect(self._elegir)
        fila.addWidget(etiqueta(t("Serie")))
        fila.addWidget(self.series, 1)
        self.form_lay.addLayout(fila)

        # Serie nueva
        self.nueva, lay = _caja()
        self.titulo = QLineEdit()
        self.titulo.setPlaceholderText(t("Título (opcional: si no, lo elige la IA)"))
        self.idea = QTextEdit()
        self.idea.setPlaceholderText(t("Ej: Un samurái caribeño busca a los siete guerreros que traicionaron a su clan; "
                                       "tono épico, con tormentas y rayos morados"))
        self.idea.setFixedHeight(90)
        self.estilo = QComboBox()
        self.estilo.addItems(list(serie.ESTILOS))
        self.cuantos = QSpinBox()
        self.cuantos.setRange(1, serie.MAX_PERSONAJES)
        self.cuantos.setValue(3)
        self.cuantos.setSuffix(f" {t('personajes')}")
        self.formato = SelectorFormato()
        for b in self.formato.grupo.buttons():  # una serie se ve en horizontal; se puede cambiar
            b.setChecked(b.property("formato") == "16:9")
        opciones = QHBoxLayout()
        opciones.addWidget(etiqueta(t("Estilo")))
        opciones.addWidget(self.estilo, 1)
        opciones.addWidget(self.cuantos)
        self.crear_btn = boton(f"✨  {t('Crear serie y personajes')}", "principal")
        self.crear_btn.clicked.connect(self._crear_serie)
        for w in (self.titulo, self.idea):
            lay.addWidget(w)
        lay.addLayout(opciones)
        lay.addWidget(self.formato)
        lay.addWidget(self.crear_btn, 0, Qt.AlignRight)
        self.form_lay.addWidget(self.nueva)

        # Serie elegida: personajes, capítulo nuevo y capítulos hechos
        self.elegida, lay = _caja()
        self.sinopsis = etiqueta("", "sub")
        lay.addWidget(self.sinopsis)
        lay.addWidget(etiqueta(t("Personajes (clic en uno para cambiar su imagen: tu dibujo o un fotograma de tu "
                                 "video)"), "sub"))
        self.fila_personajes = QHBoxLayout()
        lay.addLayout(self.fila_personajes)
        self.idea_capitulo = QTextEdit()
        self.idea_capitulo.setPlaceholderText(t("Qué pasa en este capítulo (vacío: la IA sigue la historia)"))
        self.idea_capitulo.setFixedHeight(70)
        self.planos = QSpinBox()
        self.planos.setRange(3, serie.MAX_PLANOS)
        self.planos.setValue(12)
        self.planos.setSuffix(f" {t('planos')}")
        self.capitulo_btn = boton(f"🎬  {t('Crear capítulo')}", "principal")
        self.capitulo_btn.clicked.connect(self._crear_capitulo)
        nuevo = QHBoxLayout()
        nuevo.addWidget(self.planos)
        nuevo.addStretch()
        nuevo.addWidget(self.capitulo_btn)
        lay.addWidget(self.idea_capitulo)
        lay.addLayout(nuevo)
        lay.addWidget(etiqueta(t("Capítulos"), "sub"))
        self.capitulos = QListWidget()
        self.capitulos.setMaximumHeight(150)
        self.capitulos.currentRowChanged.connect(self._ver_capitulo)
        lay.addWidget(self.capitulos)
        acciones = QHBoxLayout()
        self.rehacer_btn = boton(t("Rehacer capítulo"))
        self.rehacer_btn.setToolTip(t("Con el mismo guion; reusa las imágenes que ya salieron (útil si se acabó la "
                                      "cuota gratis a mitad)"))
        self.rehacer_btn.clicked.connect(self._rehacer)
        self.cuadros_btn = boton(t("Sacar cuadros para retocar"))
        self.cuadros_btn.setToolTip(t("Cada plano en imágenes PNG (12 por segundo), para OpenToonz, Pencil2D o Krita"))
        self.cuadros_btn.clicked.connect(self._cuadros)
        for w in (self.rehacer_btn, self.cuadros_btn):
            acciones.addWidget(w)
        instalados = serie.programas()
        for nombre, ruta in instalados.items():
            b = boton(t("Abrir en {programa}", programa=nombre))
            b.clicked.connect(lambda _, r=ruta: self._abrir_programa(r))
            acciones.addWidget(b)
        acciones.addStretch()
        lay.addLayout(acciones)
        if not instalados:
            descargas = QHBoxLayout()
            descargas.addWidget(etiqueta(t("Para retocar a mano, instala gratis:"), "sub"))
            for nombre, (_, _, web) in serie.PROGRAMAS.items():
                b = boton(f"{nombre} ↗")
                b.clicked.connect(lambda _, w=web: QDesktopServices.openUrl(QUrl(w)))
                descargas.addWidget(b)
            descargas.addStretch()
            lay.addLayout(descargas)
        self.form_lay.addWidget(self.elegida)
        self.tarea_cuadros = None
        self.recargar()

    # ---------- Series ----------

    def recargar(self, elegir: str = ""):
        """Vuelve a leer las series (tras crear una o un capítulo) y deja elegida `elegir` o la que estaba."""
        actual = elegir or (self.series.currentData() or {}).get("nombre", "")
        self.series.blockSignals(True)
        self.series.clear()
        self.series.addItem(f"➕  {t('Nueva serie')}", None)
        for s in serie.listar():
            self.series.addItem(s["titulo"], s)
            if s["nombre"] == actual:
                self.series.setCurrentIndex(self.series.count() - 1)
        self.series.blockSignals(False)
        self._elegir()

    def _elegir(self, *_):
        s = self.series.currentData()
        self.nueva.setVisible(s is None)
        self.elegida.setVisible(s is not None)
        if s is None:
            return
        self.sinopsis.setText(s["sinopsis"])
        while self.fila_personajes.count():
            w = self.fila_personajes.takeAt(0).widget()
            if w:
                w.deleteLater()
        for p in s["personajes"]:
            b = QToolButton()
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(QIcon(QPixmap(p["lamina"])) if p["lamina"] else QIcon())
            b.setIconSize(QSize(80, 120))
            b.setText(p["nombre"])
            b.setToolTip(p["personalidad"])
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QToolButton { background: #0F0F13; border: 1px solid #2C2C36; border-radius: 10px; "
                            "padding: 6px; font-size: 14px; } QToolButton:hover { border: 1px solid #7C5CFF; }")
            b.clicked.connect(lambda _, nombre=p["nombre"]: self._cambiar_lamina(nombre))
            self.fila_personajes.addWidget(b)
        self.fila_personajes.addStretch()
        self.capitulos.clear()
        for e in s["episodios"]:
            self.capitulos.addItem(t("Capítulo {n}: {titulo}", n=e["numero"], titulo=e["titulo"]))
        self.rehacer_btn.setEnabled(bool(s["episodios"]))
        self.cuadros_btn.setEnabled(bool(s["episodios"]) and not self._sacando())

    def _sacando(self) -> bool:
        return bool(self.tarea_cuadros and self.tarea_cuadros.isRunning())

    def _crear_serie(self):
        if not (self.idea.toPlainText().strip() or self.titulo.text().strip()):
            return mensaje(self, t("Falta la idea"), t("Cuéntame de qué trata la serie."))
        if self.lanzar(self.crear_btn, serie.crear_serie, titulo=self.titulo.text(), idea=self.idea.toPlainText(),
                       estilo=self.estilo.currentText(), personajes=self.cuantos.value(), formato=self.formato.valor()):
            self.tarea.listo.connect(lambda r: (self.reproductor.hide(), self.recargar(r["nombre"])))

    def _cambiar_lamina(self, personaje: str):
        ruta, _ = QFileDialog.getOpenFileName(self, t("Imagen de {nombre}", nombre=personaje), "",
                                              t("Imágenes o videos ({tipos})",
                                                tipos="*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.webm"))
        if not ruta:
            return
        try:
            serie.cambiar_lamina(self.series.currentData()["nombre"], personaje, ruta)
        except (ValueError, RuntimeError) as e:
            return mensaje_error(self, t("Revisa el archivo"), e)
        self.recargar()

    # ---------- Capítulos ----------

    def _capitulo(self) -> dict | None:
        s, fila = self.series.currentData(), self.capitulos.currentRow()
        return s["episodios"][fila] if s and 0 <= fila < len(s["episodios"]) else None

    def _crear_capitulo(self, numero: int = 0):
        s = self.series.currentData()
        if self.lanzar(self.capitulo_btn, serie.crear_episodio, serie=s["nombre"],
                       idea=self.idea_capitulo.toPlainText(), planos=self.planos.value(), numero=numero):
            self.tarea.listo.connect(lambda _: self.recargar())

    def _rehacer(self):
        if self._capitulo():
            self._crear_capitulo(self._capitulo()["numero"])

    def _ver_capitulo(self, _fila):
        e = self._capitulo()
        if e and Path(e["video"]).is_file():
            self.reproductor.show()
            self.reproductor.mostrar({"formato": self.series.currentData()["formato"], "resultados": [{
                "archivo": e["video"], "titulo": e["titulo"], "descripcion": e["resumen"], "hashtags": []}]})

    def _cuadros(self):
        e = self._capitulo()
        if self._sacando():  # soltar el hilo que corre tumba la app (y dos a la vez se pisan la carpeta)
            return
        if not e:
            return mensaje(self, t("Elige un capítulo"), t("Elige en la lista el capítulo que quieres retocar."))
        self.cuadros_btn.setEnabled(False)
        self.estado.setText(t("Sacando los cuadros de cada plano…"))
        self.tarea_cuadros = Tarea(lambda episodio, aviso: {"carpeta": serie.exportar_cuadros(episodio)},
                                   episodio=e["carpeta"])
        self.tarea_cuadros.listo.connect(lambda r: (self.estado.setText(t("Listo: cada plano está en su carpeta.")),
                                                    os.startfile(r["carpeta"])))
        self.tarea_cuadros.fallo.connect(lambda error: (self.estado.setText(""),
                                                        mensaje_error(self, t("No se pudo terminar"), error)))
        self.tarea_cuadros.finished.connect(lambda: self.cuadros_btn.setEnabled(True))
        self.tarea_cuadros.start()

    def _abrir_programa(self, ruta: str):
        subprocess.Popen([ruta])  # ruta de serie.programas(): el programa instalado, nunca algo del usuario o de la IA
        e = self._capitulo()
        if e:  # y la carpeta de los cuadros, para importarlos como secuencia de imágenes
            cuadros = Path(e["carpeta"]) / "cuadros"
            os.startfile(cuadros if cuadros.is_dir() else e["carpeta"])
