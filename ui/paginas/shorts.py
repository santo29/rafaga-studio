"""Página «Shorts mágicos»: los mejores momentos de un video largo a partir de su enlace."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QSpinBox

from motor import shorts
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje, PaginaTrabajo, SelectorFormato


class PaginaShorts(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Shorts mágicos"), t("Pega el enlace de un video largo (YouTube, Facebook, TikTok, Vimeo…). "
                                                "La IA encuentra los mejores momentos y los convierte en shorts con "
                                                "subtítulos."))
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.enfoque = QLineEdit()
        self.enfoque.setPlaceholderText(t("Qué buscar (opcional): momentos graciosos, consejos de dinero…"))
        self.formato = SelectorFormato()
        self.modo = QComboBox()
        self.modo.addItems([t("Recortar para llenar"), t("Entero, con fondo borroso")])  # como en el editor
        self.cantidad = QSpinBox()
        self.cantidad.setRange(1, 20)
        self.cantidad.setValue(5)
        self.cantidad.setSuffix(" shorts")
        self.dur_max = QSpinBox()
        self.dur_max.setRange(15, 180)
        self.dur_max.setValue(60)
        self.dur_max.setPrefix(f"{t('hasta')} ")
        self.dur_max.setSuffix(" s")
        fila = QHBoxLayout()
        for w in (self.modo, self.cantidad, self.dur_max):
            fila.addWidget(w)
        self.iniciar = boton(f"⚡  {t('Sacar shorts')}", "principal")
        self.iniciar.clicked.connect(self._iniciar)
        for w in (self.url, self.enfoque, etiqueta(t("Formato"), "sub"), self.formato):
            self.form_lay.addWidget(w)
        self.form_lay.addLayout(fila)
        self.form_lay.addWidget(etiqueta(t("Usa videos tuyos o con permiso del autor: las redes no pagan por "
                                           "contenido ajeno."), "sub"))
        self.form_lay.addWidget(self.iniciar, 0, Qt.AlignRight)

    def _iniciar(self):
        url = self.url.text().strip()
        if not url.startswith("http"):
            return mensaje(self, t("Falta el enlace"), t("Pega el enlace del video largo."))
        self.lanzar(self.iniciar, shorts.generar, url=url, formato=self.formato.valor(),
                    modo="difuminar" if self.modo.currentIndex() else "recortar",
                    cantidad=self.cantidad.value(), dur_min=min(20, self.dur_max.value()), dur_max=self.dur_max.value(),
                    enfoque=self.enfoque.text().strip())
