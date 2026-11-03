"""Página «Dibujos animados»: creas tu serie con sus personajes y después sus capítulos, plano a plano."""
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QScrollArea, QSpinBox, QTextEdit, QToolButton, QVBoxLayout, QWidget)

from motor import claves, desde_prompt, ia, nubes, serie
from motor.idioma import t
from ui.comun import (AccionesResultado, aviso_guardado, boton, descargar, etiqueta, mensaje, mensaje_error,
                      PaginaTrabajo, SelectorFormato, Tarea)

PLANO = QSize(240, 135)  # la viñeta de cada plano en el guion gráfico


def _caja():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    return w, lay


def _vaciar(lay):
    while lay.count():
        w = lay.takeAt(0).widget()
        if w:
            w.deleteLater()


class PaginaSerie(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Dibujos animados"), t("Tu serie de dibujos animados: la IA inventa los personajes y escribe "
                                                  "cada capítulo plano a plano. Revisa el guion gráfico y rehaz el plano "
                                                  "que no te guste."))
        # Lo que de verdad saldrá con la IA conectada hoy: no se promete lo que no se cumple
        self.iguales, self.movimiento = etiqueta(""), etiqueta("")
        indicadores = QHBoxLayout()
        for w in (self.iguales, self.movimiento):  # fichas de vidrio, como las tarjetas (#tarjeta de ESTILO)
            w.setWordWrap(False)
            w.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.08), "
                            "stop:1 rgba(255, 255, 255, 0.03)); border: 1px solid rgba(255, 255, 255, 0.08); "
                            "border-top-color: rgba(255, 255, 255, 0.18); border-radius: 8px; padding: 4px 10px; "
                            "font-size: 14px;")
            indicadores.addWidget(w)
        indicadores.addStretch()
        self.lay.insertLayout(2, indicadores)
        self._indicadores()
        fila = QHBoxLayout()
        self.series = QComboBox()
        self.series.currentIndexChanged.connect(self._elegir)
        fila.addWidget(etiqueta(t("Serie")))
        fila.addWidget(self.series, 1)
        self.form_lay.addLayout(fila)
        # El halo de «Crear serie» y «Crear capítulo» necesita sitio en su caja (ver _Halo de ui.comun): sus cajas
        # llevan 16 px a la derecha y abajo, que se quitan del margen de la tarjeta para que todo siga alineado
        sitio = 16
        izq, arriba, der, abajo = self.form_lay.getContentsMargins()
        self.form_lay.setContentsMargins(izq, arriba, der - sitio, abajo - sitio)
        fila.setContentsMargins(0, 0, sitio, 0)

        # Serie nueva
        self.nueva, lay = _caja()
        lay.setContentsMargins(0, 0, sitio, sitio)
        self.titulo = QLineEdit()
        self.titulo.setPlaceholderText(t("Título (opcional: si no, lo elige la IA)"))
        self.idea = QTextEdit()
        self.idea.setPlaceholderText(t("Ej.: Un gato pirata miedoso y su loro sabelotodo buscan tesoros en islas raras; "
                                       "para niños, divertido"))
        self.idea.setFixedHeight(90)
        self.estilo = QComboBox()
        self.estilo.addItems(list(serie.ESTILOS))
        self.estilo.setCurrentText(t("Cartoon 2D"))
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
        lay.setContentsMargins(0, 0, sitio, sitio)
        self.sinopsis = etiqueta("", "sub")
        lay.addWidget(self.sinopsis)
        lay.addWidget(etiqueta(t("Personajes (clic en uno para cambiar su imagen: tu dibujo o un fotograma de tu "
                                 "video)"), "sub"))
        self.fila_personajes = QHBoxLayout()
        lay.addLayout(self.fila_personajes)
        self.carpeta_serie = AccionesResultado()  # dónde están sus láminas y capítulos
        lay.addWidget(self.carpeta_serie)
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
        self.capitulos.setIconSize(QSize(64, 36))
        self.capitulos.currentRowChanged.connect(self._ver_capitulo)
        lay.addWidget(self.capitulos)
        acciones = QHBoxLayout()
        self.rehacer_btn = boton(f"✨  {t('Dibujar lo que falta')}")
        self.rehacer_btn.setToolTip(t("Dibuja los planos que no salieron (p. ej. si se acabó la cuota gratis) y vuelve "
                                      "a montar el video; lo que ya salió se queda igual"))
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

        # Capítulo elegido: su guion gráfico (una tira de planos) y, debajo, su video; en una pantalla de alto
        self.estudio, lay = _caja()
        lay.addWidget(etiqueta(t("Guion gráfico"), "sub"))
        tira = QWidget()
        self.tablero = QHBoxLayout(tira)
        self.tablero.setContentsMargins(0, 0, 0, 0)
        self.tablero.setSpacing(6)
        self.tira = QScrollArea()
        self.tira.setWidgetResizable(True)
        self.tira.setFrameShape(QFrame.NoFrame)
        self.tira.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tira.setWidget(tira)
        lay.addWidget(self.tira)
        self.lay.removeWidget(self.reproductor)
        lay.addWidget(self.reproductor)
        self.reproductor.lista.hide()  # un solo resultado (el capítulo): ni lista ni texto, para que quepa
        self.reproductor.info.hide()
        self.reproductor.pantalla.setMinimumHeight(250)
        self.lay.insertWidget(self.lay.indexOf(self.estado) + 1, self.estudio)
        self.estudio.hide()
        self.capitulo_elegido = ""
        self.tarea_cuadros = None
        self.recargar()

    def showEvent(self, e):
        self._indicadores()  # las claves se pueden conectar en otra página
        super().showEvent(e)

    def _indicadores(self):
        iguales = ia.puede_referencia()
        self.iguales.setText(t("Personajes iguales: {valor}", valor=t("Sí") if iguales
                               else t("Aproximado (elige Gemini o conecta Pollinations)")))
        self.iguales.setToolTip("" if iguales else t(
            "Tu IA de imágenes no parte de la lámina: cada plano vuelve a dibujar a los personajes con su descripción, "
            "y pueden cambiar un poco. Con Pollinations (gratis) u OpenAI salen iguales."))
        con_ia = claves.ajustes().get("video", "auto") != "ninguno" and bool(nubes.orden("video"))  # como Inicio
        self.movimiento.setText(t("Movimiento: {valor}", valor=t("IA de video") if con_ia else t("Zoom suave")))
        self.movimiento.setToolTip("" if con_ia else t(
            "Cada plano es su dibujo con un zoom suave. Para animarlos, elige una IA de video en «Claves de IA»."))

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
            self.estudio.hide()
            return
        self.sinopsis.setText(s["sinopsis"])
        self.carpeta_serie.mostrar(carpeta=s["carpeta"])
        _vaciar(self.fila_personajes)
        for p in s["personajes"]:
            caja, lay = _caja()
            b = QToolButton()
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(QIcon(QPixmap(p["lamina"])) if p["lamina"] else QIcon())
            b.setIconSize(QSize(80, 120))
            b.setText(p["nombre"])
            b.setToolTip(p["personalidad"])
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QToolButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "  # vidrio, como #acceso
                            "stop:0 rgba(255, 255, 255, 0.08), stop:1 rgba(255, 255, 255, 0.03)); "
                            "border: 1px solid rgba(255, 255, 255, 0.08); border-top-color: rgba(255, 255, 255, 0.18); "
                            "border-radius: 10px; padding: 6px; font-size: 14px; } QToolButton:hover { "
                            "border-color: rgba(124, 92, 255, 0.70); border-top-color: rgba(205, 190, 255, 0.85); }")
            b.clicked.connect(lambda _, nombre=p["nombre"]: self._cambiar_lamina(nombre))
            lay.addWidget(b, 0, Qt.AlignHCenter)  # sobre su botón, más ancho que la lámina
            if p["lamina"]:
                bajar = boton(f"⬇  {t('Descargar')}")
                bajar.setToolTip(t("Guardar una copia donde quieras"))
                bajar.clicked.connect(lambda _, p=p: descargar(self, p["lamina"], p["nombre"]))
                lay.addWidget(bajar)
            else:  # no salió al crear la serie (p. ej. sin cuota): se puede volver a pedir
                dibujar = boton(f"✨  {t('Dibujar con IA')}")
                dibujar.clicked.connect(lambda _, nombre=p["nombre"]: self._dibujar_lamina(nombre))
                lay.addWidget(dibujar)
            lay.addStretch()
            self.fila_personajes.addWidget(caja)
        self.fila_personajes.addStretch()
        estados = {"sin_dibujos": t("Sin dibujos"), "incompleto": t("Faltan dibujos")}
        self.capitulos.blockSignals(True)  # el capítulo que estaba elegido se vuelve a elegir una sola vez, abajo
        self.capitulos.clear()
        for e in s["episodios"]:
            texto = t("Capítulo {n}: {titulo}", n=e["numero"], titulo=e["titulo"])
            self.capitulos.addItem(QListWidgetItem(QIcon(e["miniatura"]), texto + (
                f"  ·  {estados[e['estado']]}" if e["estado"] in estados else "")))
        self.capitulos.setCurrentRow(next((n for n, e in enumerate(s["episodios"])
                                           if e["carpeta"] == self.capitulo_elegido), -1))
        self.capitulos.blockSignals(False)
        self._ver_capitulo()
        self.cuadros_btn.setEnabled(bool(s["episodios"]) and not self._sacando())

    def _sacando(self) -> bool:
        return bool(self.tarea_cuadros and self.tarea_cuadros.isRunning())

    def _crear_serie(self):
        if not (self.idea.toPlainText().strip() or self.titulo.text().strip()):
            return mensaje(self, t("Falta la idea"), t("Cuéntame de qué trata la serie."))
        if self.lanzar(self.crear_btn, serie.crear_serie, titulo=self.titulo.text(), idea=self.idea.toPlainText(),
                       estilo=self.estilo.currentText(), personajes=self.cuantos.value(), formato=self.formato.valor(),
                       voz=desde_prompt.voz_inicial()):
            self.tarea.listo.connect(lambda r: (self.reproductor.hide(), self.recargar(r["nombre"])))

    def _dibujar_lamina(self, personaje: str):
        self._trabajo(serie.dibujar_lamina, serie=self.series.currentData()["nombre"], personaje=personaje)

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

    def _trabajo(self, funcion, **datos):
        """Un trabajo del estudio; al acabar, bien o mal, se vuelve a leer la serie y el capítulo sigue elegido."""
        self.reproductor.player.setSource(QUrl())  # el video del capítulo se va a reescribir: que nadie lo tenga abierto
        if self.lanzar(self.capitulo_btn, funcion, **datos):  # un botón fijo: los del guion gráfico se rehacen
            self.tarea.listo.connect(self._hecho)
            self.tarea.fallo.connect(self._fallo)
        else:  # dijo que no al costo: su capítulo sigue a la vista
            self._ver_capitulo()

    def _hecho(self, r: dict):
        if r.get("tipo") == "episodio":
            self.capitulo_elegido = r["carpeta"]
        self.recargar()

    def _fallo(self, _):
        """El capítulo nuevo que quedó «Sin dibujos» se elige: el error pide pulsar ahí «Dibujar lo que falta»."""
        antes = {e["carpeta"] for e in (self.series.currentData() or {}).get("episodios", [])}
        self.recargar()
        nuevos = [n for n, e in enumerate((self.series.currentData() or {}).get("episodios", []))
                  if e["carpeta"] not in antes]
        if nuevos:
            self.capitulos.setCurrentRow(nuevos[-1])

    def _crear_capitulo(self, numero: int = 0):
        self._trabajo(serie.crear_episodio, serie=self.series.currentData()["nombre"],
                      idea=self.idea_capitulo.toPlainText(), planos=self.planos.value(), numero=numero)

    def _rehacer(self):
        if self._capitulo():
            self._crear_capitulo(self._capitulo()["numero"])

    def _rehacer_plano(self, i: int):
        if self._capitulo():
            self._trabajo(serie.rehacer_plano, episodio=self._capitulo()["carpeta"], i=i)

    def _ver_capitulo(self, *_):
        """El guion gráfico y el video del capítulo elegido, a la vista sin tener que bajar a buscarlos."""
        e = self._capitulo()
        self.capitulo_elegido = e["carpeta"] if e else ""
        self.estudio.setVisible(bool(e))
        self.rehacer_btn.setEnabled(False)
        if not e:
            return
        _vaciar(self.tablero)
        planos, alto = serie.guion_grafico(e["carpeta"]), 0
        for i, p in enumerate(planos):
            vineta = self._vineta(i, p)
            self.tablero.addWidget(vineta)
            alto = max(alto, vineta.sizeHint().height())  # la tira todavía no las cuenta: Qt las muestra después
        self.tablero.addStretch()
        self.tira.setFixedHeight(alto + self.tira.horizontalScrollBar().sizeHint().height())
        self.rehacer_btn.setEnabled(any(not p["imagen"] for p in planos))
        hay_video = Path(e["video"]).is_file()  # «Sin dibujos»: no hay video
        self.reproductor.setVisible(hay_video)
        if hay_video:
            self.reproductor.mostrar({"formato": self.series.currentData()["formato"], "resultados": [{
                "archivo": e["video"], "titulo": e["titulo"], "descripcion": e["resumen"], "hashtags": []}]})
        area = self.parentWidget().parentWidget() if self.parentWidget() else None  # app.py la pone en un QScrollArea
        if isinstance(area, QScrollArea):
            QTimer.singleShot(0, lambda: area.ensureWidgetVisible(self.estudio, 0, 10))

    def _vineta(self, i: int, p: dict) -> QFrame:
        """Un plano del guion gráfico: su dibujo, quién habla, qué dice y el botón para rehacerlo."""
        caja = QFrame()
        caja.setObjectName("tarjeta")
        caja.setStyleSheet("QLabel { font-size: 13px; }")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(5, 5, 5, 5)  # 4 viñetas caben a lo ancho en un portátil de 1366 px
        lay.setSpacing(4)
        dibujo = QLabel(t("Sin dibujo"))
        dibujo.setFixedSize(PLANO)
        dibujo.setAlignment(Qt.AlignCenter)
        dibujo.setStyleSheet("background: #0F0F13; border-radius: 6px; color: #8D8D9A;")
        if p["imagen"]:
            dibujo.setPixmap(QPixmap(p["imagen"]).scaled(PLANO, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        dibujo.setToolTip(p["descripcion"])
        lay.addWidget(dibujo)
        lay.addWidget(etiqueta(t("Plano {n} · Habla: {quien}", n=i + 1, quien=p["habla"] or t("Narrador"))))
        texto = etiqueta(p["texto"] if len(p["texto"]) <= 90 else p["texto"][:89] + "…", "sub")
        texto.setFixedSize(PLANO.width(), 36)  # dos líneas: todas las viñetas del mismo alto
        texto.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        texto.setToolTip(p["texto"])
        lay.addWidget(texto)
        rehacer = boton(f"✨  {t('Rehacer plano')}")
        rehacer.setToolTip(t("Lo vuelve a dibujar y monta otra vez el video (gasta 1 imagen)"))
        rehacer.clicked.connect(lambda _, i=i: self._rehacer_plano(i))
        lay.addWidget(rehacer)
        return caja

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
        # Se dice dónde quedaron, con «Abrir carpeta» (antes se abría el Explorador solo, sin decir nada)
        self.tarea_cuadros.listo.connect(lambda r: (self.estado.setText(t("Listo: cada plano está en su carpeta.")),
                                                    aviso_guardado(self, t("Cuadros listos"), r["carpeta"])))
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
