"""Página «Crear con IA»: video completo desde un pedido (con foto de partida opcional)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QSpinBox, QTextEdit

from motor import desde_prompt, ia, seguro, serie
from motor.idioma import dinero, t
from ui.comun import (archivo_valido, boton, campo_archivo, etiqueta, mensaje, PaginaTrabajo, SelectorFormato,
                      SelectorVoz)


class PaginaCrear(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Crear video con IA"), t("Describe el video que quieres. La IA escribe el guion, crea las "
                                                    "imágenes, pone la voz y los subtítulos."))
        self.prompt = QTextEdit()
        self.prompt.setPlaceholderText(t("Ej.: 5 datos impactantes sobre el océano profundo, tono misterioso"))
        self.prompt.setFixedHeight(100)
        self.formato = SelectorFormato()
        self.voz = SelectorVoz()
        self.segundos = QSpinBox()
        self.segundos.setRange(15, 600)
        self.segundos.setValue(45)
        self.segundos.setSuffix(f" {t('segundos')}")
        self.estilo = QComboBox()  # el de las series: así se puede pedir dibujo animado
        self.estilo.addItem(t("Automático"), "")
        for nombre in serie.ESTILOS:
            self.estilo.addItem(nombre, nombre)
        fila = QHBoxLayout()
        fila.addWidget(etiqueta(t("Estilo")))
        fila.addWidget(self.estilo)
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
                                           "video» en «No usar» en «Claves de IA»."), "sub"))
        self.form_lay.addLayout(fila)
        self.animado = QCheckBox()
        self._texto_animado()
        self.animado.setChecked(desde_prompt.con_voz_propia())
        self.animado.setToolTip(t("Cada escena es un video de IA con voz y labios sincronizados. Sin marcar: imágenes "
                                  "animadas con narración (gratis)."))
        self.form_lay.addWidget(self.animado)
        self.form_lay.addWidget(self.iniciar, 0, Qt.AlignRight)

    def _texto_animado(self):
        """La casilla dice quién hace las escenas que hablan y lo más que cuesta cada una (se elige en Claves de IA)."""
        quien = desde_prompt.proveedor_voz() or "gemini"
        try:
            nombre, costo = ia.nombre_video(quien), ia.precio_video(quien, voz=True)
        except ImportError:  # eligió Kling o Seedance y esta versión todavía no los trae
            nombre, costo = quien.capitalize(), 0.0
        self.animado.setText(t("🎬 Video animado con IA: los personajes hablan con su propia voz ({proveedor}, de pago: "
                               "hasta unos {costo} por escena de 8 s)", proveedor=nombre, costo=dinero(costo)))

    def showEvent(self, evento):  # lo eligió en Claves de IA después de abrir la app
        self._texto_animado()
        super().showEvent(evento)

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
        # Animado es de pago: lanzar pregunta antes cuánto, junto con lo que cueste animar (ver _pagar_video)
        self.lanzar(self.iniciar, desde_prompt.generar, prompt=texto, formato=self.formato.valor(),
                    segundos=self.segundos.value(), voz=self.voz.currentData(), imagen=imagen,
                    animado=self.animado.isChecked(), estilo=self.estilo.currentData())
