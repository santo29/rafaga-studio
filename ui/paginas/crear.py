"""Página «Crear con IA»: video completo desde un pedido (con foto de partida opcional), o una foto convertida en
video con un movimiento de cámara con nombre (como en Higgsfield)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QSpinBox, QTextEdit, QWidget

from motor import claves, desde_prompt, ia, nube, nubes, seguro, serie
from motor.idioma import dinero, t
from ui.comun import (archivo_valido, boton, campo_archivo, etiqueta, mensaje, PaginaTrabajo, SelectorFormato,
                      SelectorModelo, SelectorVoz)


class PaginaCrear(PaginaTrabajo):
    def __init__(self):
        super().__init__(t("Crear video con IA"), t("Describe el video que quieres. La IA escribe el guion, crea las "
                                                    "imágenes, pone la voz y los subtítulos."))
        self.prompt = QTextEdit()
        self.prompt.setPlaceholderText(t("Ej.: 5 datos impactantes sobre el océano profundo, tono misterioso"))
        self.prompt.setFixedHeight(100)
        # Con qué modelo se hace ESTE video (como en CapCut), justo debajo del pedido
        self.modelo = SelectorModelo("crear")
        self.modelo.cambio.connect(self._modelo_elegido)
        fila_modelo = QHBoxLayout()
        fila_modelo.addWidget(etiqueta(t("Modelo de video"), "sub"))
        fila_modelo.addWidget(self.modelo)
        fila_modelo.addStretch()
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
                                               t("Imágenes ({tipos})", tipos="*.png *.jpg *.jpeg *.webp"),
                                               self._foto_elegida)
        self.miniatura = QLabel()  # la foto elegida, a la vista (antes solo su ruta, cortada)
        self.miniatura.setFixedSize(56, 56)
        self.miniatura.setAlignment(Qt.AlignCenter)
        self.miniatura.hide()
        fila_foto.insertWidget(0, self.miniatura)
        self.imagen.textChanged.connect(self._ver_foto)
        self.modo = QComboBox()
        self.modo.addItems([t("Video completo con voz y subtítulos"), t("Foto a video: animar la imagen (clip corto, "
                                                                        "sin voz)")])
        self.modo.currentIndexChanged.connect(self._modo_elegido)
        fila_foto.addWidget(self.modo)
        # Foto a video: un movimiento de cámara con nombre y, al lado, con qué se hace y lo que cuesta
        self.fila_camara = QWidget()
        fila_camara = QHBoxLayout(self.fila_camara)
        fila_camara.setContentsMargins(0, 0, 0, 0)
        self.camara = QComboBox()
        self.camara.setAccessibleName(t("Movimiento de cámara"))
        for clave, (nombre, _) in ia.CAMARAS.items():
            self.camara.addItem(nombre, clave)
        self.costo_foto = etiqueta("", "sub")
        fila_camara.addWidget(etiqueta(t("Movimiento de cámara")))
        fila_camara.addWidget(self.camara)
        fila_camara.addWidget(self.costo_foto, 1)
        self.fila_camara.hide()
        self.form_lay.addWidget(self.prompt)
        self.form_lay.addLayout(fila_modelo)
        self.form_lay.addWidget(etiqueta(t("Formato"), "sub"))
        self.form_lay.addWidget(self.formato)
        self.form_lay.addLayout(fila_foto)
        self.form_lay.addWidget(self.fila_camara)
        self.form_lay.addWidget(etiqueta(t("Privacidad: con «Automático», sin tu nube Modal las imágenes se animan en "
                                           "un Space público de Hugging Face. Para que no salgan de tu cuenta, conecta "
                                           "y elige «Mi nube Modal» en «Claves de IA»."), "sub"))
        self.form_lay.addLayout(fila)
        self.animado = QCheckBox()
        self._texto_animado()
        with claves.por_trabajo(self.modelo.valor()):  # con el modelo recordado, como al elegirlo (_modelo_elegido)
            self.animado.setChecked(self.modelo.valor() not in claves.VIDEO_GRATIS and desde_prompt.con_voz_propia())
        self.animado.setToolTip(t("Cada escena es un video de IA con voz y labios sincronizados. Sin marcar: imágenes "
                                  "animadas con narración (gratis)."))
        self.form_lay.addWidget(self.animado)
        self.form_lay.addWidget(self.iniciar, 0, Qt.AlignRight)

    def _texto_animado(self):
        """La casilla dice quién hace las escenas que hablan y lo más que cuesta cada una (se elige en Claves de IA, o
        con el modelo de video de este trabajo: Kling, Seedance o Gemini Omni)."""
        with claves.por_trabajo(self.modelo.valor()):
            quien = desde_prompt.proveedor_voz() or "gemini"
            try:
                nombre, costo = ia.nombre_video(quien), ia.precio_video(quien, voz=True)
            except ImportError:  # eligió Kling o Seedance y esta versión todavía no los trae
                nombre, costo = quien.capitalize(), 0.0
        self.animado.setText(t("🎬 Video animado con IA: los personajes hablan con su propia voz ({proveedor}, de pago: "
                               "hasta unos {costo} por escena de 8 s)", proveedor=nombre, costo=dinero(costo)))

    def showEvent(self, evento):  # lo eligió en Claves de IA después de abrir la app
        self.modelo.recargar()  # antes que la casilla: si se quitó la clave del modelo recordado, ya es Automático
        self._texto_animado()
        self._costo_foto()
        super().showEvent(evento)

    def _modelo_elegido(self, modelo: str):
        """Gemini Omni hace escenas que hablan: la casilla se marca (sigue preguntando el costo antes). Uno gratis
        (o Sin animar) la desmarca: quien elige gratis no espera que hable con una IA de pago."""
        if modelo == "gemini" or modelo in claves.VIDEO_GRATIS:
            self.animado.setChecked(modelo == "gemini")
        self._texto_animado()
        self._costo_foto()

    def _ver_foto(self, ruta: str):
        foto = QPixmap(ruta.strip()) if ruta.strip() else QPixmap()
        self.miniatura.setPixmap(foto.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                 if not foto.isNull() else QPixmap())
        self.miniatura.setVisible(not foto.isNull())

    def _foto_elegida(self, _ruta: str):
        if not self.prompt.toPlainText().strip():  # una foto sin pedido: lo que se quiere es que se mueva
            self.modo.setCurrentIndex(1)

    def _modo_elegido(self):
        foto = self.modo.currentIndex() == 1
        self.fila_camara.setVisible(foto)
        self.animado.setVisible(not foto)  # un clip de la foto, sin voz: nada que hable
        self.prompt.setPlaceholderText(t("Qué se mueve en la foto (opcional). Ej.: sube el vapor y el queso se derrite")
                                       if foto else t("Ej.: 5 datos impactantes sobre el océano profundo, tono "
                                                      "misterioso"))
        self._costo_foto()

    def _costo_foto(self):
        """Con qué se animará la foto y lo que cuesta, antes de pulsar (lo de pago se pregunta igual al empezar)."""
        modelo = self.modelo.valor()
        with claves.por_trabajo(modelo):
            pago, primero = ia.video_de_pago(un_clip=True), next(iter(nubes.orden("video")), "")
        self.costo_foto.setText(
            t("«Sin animar» no anima nada: elige otro modelo de video.") if modelo == "ninguno" else
            t("Hasta unos {costo} con {proveedor} (se pregunta antes de empezar).",
              costo=dinero(ia.precio_video(pago)), proveedor=ia.nombre_video(pago)) if pago else
            t("Con tu nube Modal: unos {costo} de tu crédito (quedan {n} de {m} este mes).",
              costo=dinero(nube.PRECIO_CLIP), n=max(nube.limite() - nube.usados_mes(), 0), m=nube.limite())
            if primero == "modal" else
            t("Gratis con el Space público de Hugging Face: tu foto se sube ahí.") if primero == "huggingface" else
            t("Con Pollinations: usa el saldo de tu cuenta."))

    def _iniciar(self):
        texto = self.prompt.toPlainText().strip()
        imagen = self.imagen.text().strip()
        foto_a_video = bool(imagen) and self.modo.currentIndex() == 1
        if not texto and not foto_a_video:  # a una foto le basta su movimiento de cámara
            return mensaje(self, t("Falta el pedido"), t("Escribe qué video quieres crear."))
        if imagen and not archivo_valido(self, imagen, seguro.IMAGENES, t("imagen")):
            return
        modelo = self.modelo.valor()  # solo para este trabajo: «Claves de IA» no cambia
        if foto_a_video:
            if modelo == "ninguno":
                return mensaje(self, t("Elige un modelo de video"),
                               t("«Sin animar» no anima nada: para animar solo la imagen, elige otro modelo de video."))
            # El pedido (o uno suave) y la cámara elegida: ia.direccion_video pone la cámara delante para la IA
            pedido = f"{texto or t('Que cobre vida con un movimiento suave y natural')}. " \
                     f"{ia.CAMARAS[self.camara.currentData()][1]}."
            return self.lanzar(self.iniciar, desde_prompt.animar_imagen, modelo_video=modelo, imagen=imagen,
                               prompt=pedido, formato=self.formato.valor())
        # Animado es de pago: lanzar pregunta antes cuánto, junto con lo que cueste animar (ver _pagar_video)
        self.lanzar(self.iniciar, desde_prompt.generar, modelo_video=modelo, prompt=texto, formato=self.formato.valor(),
                    segundos=self.segundos.value(), voz=self.voz.currentData(), imagen=imagen,
                    animado=self.animado.isChecked(), estilo=self.estilo.currentData())
