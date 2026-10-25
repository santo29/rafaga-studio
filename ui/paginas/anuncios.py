"""Página «Anuncios»: variantes de anuncio en video desde la foto del producto."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout

from motor import anuncios
from motor.idioma import t
from ui.comun import boton, mensaje, PaginaTrabajo, SelectorFormato, SelectorVoz


class PaginaAnuncios(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Anuncios realistas"), t("Sube la foto de tu producto o de tu negocio. La IA crea varias "
                                                    "versiones con ganchos distintos (para pruebas A/B) y las monta "
                                                    "con voz y subtítulos; tu producto real sale en las escenas donde "
                                                    "aparece. Con Claude conectado, antes investiga qué anuncios están "
                                                    "funcionando."))
        fila_foto = QHBoxLayout()
        self.foto = None
        self.vista = QLabel(t("Sin foto"))
        self.vista.setFixedSize(120, 120)
        self.vista.setAlignment(Qt.AlignCenter)
        self.vista.setStyleSheet("background:#0F0F13;border:1px dashed #3C3C48;border-radius:10px;color:#8D8D9A;")
        elegir = boton(f"📷  {t('Elegir foto del producto')}")
        elegir.clicked.connect(self._elegir_foto)
        datos = QVBoxLayout()
        self.producto = QLineEdit()
        self.producto.setPlaceholderText(t("Producto o servicio (ej.: Crema reafirmante Aloe+, Barbería Los Panas)"))
        self.detalles = QLineEdit()
        self.detalles.setPlaceholderText(t("Qué hace, beneficios, precio"))
        self.publico = QLineEdit()
        self.publico.setPlaceholderText(t("Público (ej.: mujeres 25-45 en RD que cuidan su piel)"))
        self.oferta = QLineEdit()
        self.oferta.setPlaceholderText(t("Oferta y acción (ej.: 2x1 hoy, escríbenos por WhatsApp)"))
        for w in (self.producto, self.detalles, self.publico, self.oferta):
            datos.addWidget(w)
        columna = QVBoxLayout()
        columna.addWidget(self.vista)
        columna.addWidget(elegir)
        fila_foto.addLayout(columna)
        fila_foto.addLayout(datos, 1)
        self.estilo = QComboBox()
        for estilo in anuncios.ESTILOS:  # se ve traducido; la clave va en el dato
            self.estilo.addItem(t(estilo), estilo)
        self.formato = SelectorFormato()
        self.voz = SelectorVoz()
        # La voz encoge si no hay sitio para su nombre más largo (las de ElevenLabs también cuentan): así el estilo se
        # lee entero y la fila no se sale de la ventana
        self.voz.setMinimumWidth(160)
        self.variantes = QSpinBox()
        self.variantes.setRange(1, 6)
        self.variantes.setValue(3)
        self.variantes.setSuffix(f" {t('versiones')}")
        self.segundos = QSpinBox()
        self.segundos.setRange(10, 90)
        self.segundos.setValue(25)
        self.segundos.setSuffix(" s")
        fila = QHBoxLayout()
        for w in (self.estilo, self.voz, self.variantes, self.segundos):
            fila.addWidget(w)
        self.iniciar = boton(f"🚀  {t('Crear anuncios')}", "principal")
        self.iniciar.clicked.connect(self._iniciar)
        self.form_lay.addLayout(fila_foto)
        self.form_lay.addWidget(self.formato)
        self.form_lay.addLayout(fila)
        self.form_lay.addWidget(self.iniciar, 0, Qt.AlignRight)

    def _elegir_foto(self):
        ruta, _ = QFileDialog.getOpenFileName(self, t("Foto del producto"), "",
                                              t("Imágenes ({tipos})", tipos="*.png *.jpg *.jpeg *.webp"))
        if ruta:
            self.foto = ruta
            self.vista.setPixmap(QPixmap(ruta).scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _iniciar(self):
        if not self.foto or not self.producto.text().strip():
            return mensaje(self, t("Faltan datos"), t("Elige la foto del producto y escribe su nombre."))
        self.lanzar(self.iniciar, anuncios.crear, foto=self.foto, producto=self.producto.text(),
                    detalles=self.detalles.text(), publico=self.publico.text(), oferta=self.oferta.text(),
                    estilo=self.estilo.currentData(), formato=self.formato.valor(), voz=self.voz.currentData(),
                    variantes=self.variantes.value(), segundos=self.segundos.value())
