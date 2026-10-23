"""Página «Crear con IA»: video completo desde un pedido (con foto de partida opcional)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSpinBox, QTextEdit

from motor import desde_prompt, seguro
from motor.idioma import t
from ui.comun import (archivo_valido, boton, campo_archivo, etiqueta, mensaje, PaginaTrabajo, SelectorFormato,
                      SelectorVoz)


class PaginaCrear(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Crear video con IA"), t("Describe el video que quieres. La IA escribe el guion, crea las "
                                                    "imágenes, pone la voz y los subtítulos."))
        self.prompt = QTextEdit()
        self.prompt.setPlaceholderText(t("Ej: 5 datos impactantes sobre el océano profundo, tono misterioso"))
        self.prompt.setFixedHeight(100)
        self.formato = SelectorFormato()
        self.voz = SelectorVoz()
        self.segundos = QSpinBox()
        self.segundos.setRange(15, 600)
        self.segundos.setValue(45)
        self.segundos.setSuffix(f" {t('segundos')}")
        fila = QHBoxLayout()
        fila.addWidget(etiqueta(t("Voz")))
        fila.addWidget(self.voz, 1)
        fila.addWidget(etiqueta(t("Duración")))
        fila.addWidget(self.segundos)
        self.iniciar = boton(f"✨  {t('Generar video')}", "principal")
        self.iniciar.clicked.connect(self._iniciar)
        fila_foto, self.imagen = campo_archivo(t("Imagen de partida (opcional): tu foto, producto o personaje"),
                                               t("Imágenes ({tipos})", tipos="*.png *.jpg *.jpeg *.webp"))
        self.modo = QComboBox()
        self.modo.addItems([t("Video completo con voz y subtítulos"), t("Solo animar la imagen (clip corto, sin voz)")])
        fila_foto.addWidget(self.modo)
        for w in (self.prompt, etiqueta(t("Formato"), "sub"), self.formato):
            self.form_lay.addWidget(w)
        self.form_lay.addLayout(fila_foto)
        self.form_lay.addWidget(etiqueta(t("Privacidad: para animar con IA gratis, las imágenes se suben a un Space "
                                           "público de Hugging Face. Si no quieres, pon «Animar escenas con IA de "
                                           "video» en «No usar» en Claves de IA."), "sub"))
        self.form_lay.addLayout(fila)
        self.form_lay.addWidget(self.iniciar, 0, Qt.AlignRight)

    def _iniciar(self):
        texto = self.prompt.toPlainText().strip()
        imagen = self.imagen.text().strip()
        if not texto:
            return mensaje(self, t("Falta el pedido"), t("Escribe qué video quieres crear."))
        if imagen and not archivo_valido(self, imagen, seguro.IMAGENES, t("imagen")):
            return
        if imagen and self.modo.currentIndex() == 1:
            return self.lanzar(self.iniciar, desde_prompt.animar_imagen, imagen=imagen, prompt=texto,
                               formato=self.formato.valor())
        self.lanzar(self.iniciar, desde_prompt.generar, prompt=texto, formato=self.formato.valor(),
                    segundos=self.segundos.value(), voz=self.voz.currentData(), imagen=imagen)
