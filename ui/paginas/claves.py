"""Página «Claves de IA»: conectar claves, elegir proveedor por defecto y la nube Modal."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
                               QListWidgetItem, QSpinBox, QVBoxLayout, QWidget)

from motor import claves, nube
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje, mensaje_error, Tarea, tarjeta


USOS_UI = {"texto": t("Guiones y elegir clips"), "diseno": t("IA que diseña"), "imagen": t("Imágenes"),
           "video": t("Animar escenas con IA de video"), "video_voz": t("Escenas que hablan"),
           "transcripcion": t("Transcripción"), "musica": t("Música")}


NOMBRES_PROVEEDOR = {"auto": t("Automático (la mejor conectada)"), "pollinations": t("Pollinations (gratis)"),
                     "pc": t("Este PC (gratis, más lento)"), "ninguno": t("No usar (zoom suave sobre la imagen)"),
                     "huggingface": t("Hugging Face (gratis; Space público de la comunidad)"), "openai": "OpenAI",
                     "anthropic": "Claude (Anthropic)", "modal": t("Mi nube Modal ($30 gratis al mes)"),
                     "elevenlabs": "ElevenLabs", "gemini": "Gemini (Google)",
                     "cloudflare": t("Cloudflare (gratis diario)"), "groq": t("Groq (gratis)"),
                     "kling": t("Kling (de pago)"), "seedance": t("Seedance (de pago)")}


# Cada servicio que se puede conectar: para qué sirve, cuánto cuesta y dónde se saca la clave (de lo gratis a lo de pago)
SERVICIOS = [
    ("groq", "Groq", t("Guiones con IA y transcripción rápida"), t("Gratis"), "https://console.groq.com/keys"),
    ("gemini", "Gemini (Google)", t("Guiones con IA; imágenes Nano Banana (si las eliges), videos animados con voz y música con Lyria"),
     t("Gratis (imágenes, video y música de pago)"),
     "https://aistudio.google.com/app/apikey"),
    ("cloudflare", "Cloudflare Workers AI", t("Imágenes, ~100 al día. Pega el ID de cuenta y el token juntos"),
     t("Gratis"), "https://dash.cloudflare.com/profile/api-tokens"),
    ("pollinations", "Pollinations", t("Imágenes y guiones sin marca de agua"), t("Gratis"),
     "https://enter.pollinations.ai"),
    ("huggingface", "Hugging Face", t("Más cuota para animar fotos e imágenes"), t("Gratis"),
     "https://huggingface.co/settings/tokens"),
    ("modal", "Modal", t("Tu nube de video con IA. Pega las dos partes del token (ak-… as-…)"),
     t("$1/mes; $30 con tarjeta"), "https://modal.com/settings/tokens"),
    ("elevenlabs", "ElevenLabs", t("Voces realistas y música"), t("Plan gratis pequeño"),
     "https://elevenlabs.io/app/settings/api-keys"),
    ("anthropic", "Claude (Anthropic)", t("Los mejores guiones e investigación en internet"), t("De pago"),
     "https://console.anthropic.com/settings/keys"),
    ("openai", "OpenAI", t("Guiones, imágenes y transcripción"), t("De pago"), "https://platform.openai.com/api-keys"),
    ("openrouter", "OpenRouter", t("Muchos modelos con una sola clave"), t("De pago (algunos gratis)"),
     "https://openrouter.ai/keys"),
    ("deepseek", "DeepSeek", t("Guiones con IA"), t("De pago, barato"), "https://platform.deepseek.com/api_keys"),
    ("xai", "xAI (Grok)", t("Guiones con IA"), t("De pago"), "https://console.x.ai"),
    ("replicate", "Replicate", t("Imágenes"), t("De pago"), "https://replicate.com/account/api-tokens"),
    # Sin formato de clave reconocible: se conectan con su botón. El enlace (CONSOLA) lo da su módulo
    ("kling", "Kling", t("Animar escenas y escenas que hablan con su propio audio"),
     t("De pago (~US$0,04-0,16 por segundo)"), None),
    ("seedance", "Seedance (BytePlus)", t("Animar escenas y escenas que hablan con su propio audio"),
     t("De pago (~US$0,02-0,24 por segundo)"), None),
]


class PaginaClaves(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(etiqueta(t("Claves de IA"), "titulo"))
        lay.addWidget(etiqueta(t("Un solo cuadro para todas: pega UNA clave cada vez y pulsa «Conectar». Ráfaga "
                                 "Studio detecta sola de qué servicio es, la comprueba y la suma a la lista de abajo. "
                                 "Puedes conectar varias (por ejemplo Groq, Cloudflare y Modal): cada una se usa para "
                                 "lo suyo. Las claves se guardan cifradas y solo en este PC."), "sub"))
        caja, caja_lay = tarjeta()
        fila = QHBoxLayout()
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText(
            t("Pega aquí una clave (sk-ant-…, gsk_…, AIza…, hf_…, sk_…, o el token de Modal)"))
        self.entrada.setEchoMode(QLineEdit.Password)
        self.entrada.returnPressed.connect(self._conectar)
        mostrar = QCheckBox(t("Ver lo que pegué"))  # para comprobar que se pegó entera, sin espacios ni texto de más
        mostrar.toggled.connect(lambda si: self.entrada.setEchoMode(QLineEdit.Normal if si else QLineEdit.Password))
        self.conectar = boton(t("Conectar"), "principal")
        self.conectar.clicked.connect(self._conectar)
        fila.addWidget(self.entrada, 1)
        fila.addWidget(mostrar)
        fila.addWidget(self.conectar)
        caja_lay.addLayout(fila)
        lay.addWidget(caja)
        # Todos los servicios a la vista, con su estado y dónde se saca cada clave
        servicios, servicios_lay = tarjeta()
        servicios_lay.addWidget(etiqueta(t("Servicios que puedes conectar"), "sub"))
        servicios_lay.addWidget(etiqueta(t("Kling y Seedance son de pago: se conectan con su botón «Conectar», y antes "
                                           "de cada trabajo que los usa la app te dice lo que puede costar."), "sub"))
        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(16)
        self.estados, self.botones_pago = {}, {}
        for n, (clave, nombre, para, precio, web) in enumerate(SERVICIOS):
            titulo = etiqueta(nombre)
            titulo.setStyleSheet("font-weight: 700;")
            estado = etiqueta("")
            conseguir = boton(t("Conseguir clave ↗"))
            conseguir.clicked.connect(lambda _, w=web, c=clave: self._abrir_consola(w, c))
            for columna, w in enumerate((titulo, etiqueta(para, "sub"), etiqueta(precio, "sub"), estado, conseguir)):
                rejilla.addWidget(w, n, columna)
            if clave in claves.VIDEO_DE_PAGO:  # su clave no se reconoce sola: se dice de quién es
                self.botones_pago[clave] = boton(t("Conectar"))
                self.botones_pago[clave].clicked.connect(lambda _, c=clave, s=nombre: self._conectar(c, s))
                rejilla.addWidget(self.botones_pago[clave], n, 5)
            self.estados[clave] = estado
        rejilla.setColumnStretch(1, 1)
        servicios_lay.addLayout(rejilla)
        lay.addWidget(servicios)
        self.lista = QListWidget()
        self.lista.setWordWrap(True)  # los avisos largos se leen enteros, sin barra de desplazamiento horizontal
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        quitar = boton(t("Quitar clave seleccionada"))
        quitar.clicked.connect(self._quitar)
        lay.addWidget(self.lista, 1)
        lay.addWidget(quitar, 0, Qt.AlignLeft)
        # Qué proveedor usa el software por defecto en cada tarea.
        defecto, defecto_lay = tarjeta()
        defecto_lay.addWidget(etiqueta(t("IA que usa Ráfaga Studio por defecto"), "sub"))
        self.selectores = {}
        for uso, nombre in USOS_UI.items():
            fila = QHBoxLayout()
            combo = QComboBox()
            combo.currentIndexChanged.connect(lambda _, u=uso, c=combo: c.currentData() and
                                              claves.elegir_por_defecto(u, c.currentData()))
            texto = etiqueta(nombre)
            texto.setFixedWidth(230)
            fila.addWidget(texto)
            fila.addWidget(combo, 1)
            defecto_lay.addLayout(fila)
            self.selectores[uso] = combo
            if uso == "diseno":
                self.nota_diseno = etiqueta(t("Claude o ChatGPT diseñan mejor: conecta su clave."), "sub")
                defecto_lay.addWidget(self.nota_diseno)
        lay.addWidget(defecto)
        # Nube de video en Modal: instalar el motor una vez y fijar el tope diario para no pasar del crédito gratis.
        nube_caja, nube_lay = tarjeta()
        nube_lay.addWidget(etiqueta(f"☁️  {t('Mi nube de video (Modal)')}", "sub"))
        nube_lay.addWidget(etiqueta(t("Crea una cuenta en modal.com, crea un token en Settings → API tokens (ak-… y "
                                      "as-…), pégalo arriba juntos y pulsa «Instalar motor». Plan Starter: $1 al mes "
                                      "sin tarjeta; $30 gratis al mes si añades un método de pago (pon un límite de "
                                      "uso de $30 en Usage & billing para no pagar nada). Cada clip de 5 s cuesta "
                                      "~$0.20–0.35.")))
        fila = QHBoxLayout()
        self.limite = QSpinBox()
        self.limite.setRange(0, 50)
        self.limite.setValue(nube.limite())
        self.limite.setPrefix(t("Máximo "))
        self.limite.setSuffix(t(" clips al día"))
        self.limite.valueChanged.connect(lambda v: claves.elegir_por_defecto("limite_nube_diario", v))
        self.uso_nube = etiqueta("", "sub")
        self.instalar = boton(t("Instalar motor en Modal"))
        self.instalar.clicked.connect(self._instalar_nube)
        fila.addWidget(self.limite)
        fila.addWidget(self.uso_nube, 1)
        fila.addWidget(self.instalar)
        nube_lay.addLayout(fila)
        lay.addWidget(nube_caja)
        self.tarea = None
        self._refrescar()

    def _instalar_nube(self):
        self.instalar.setEnabled(False)
        self.instalar.setText(t("Instalando (varios minutos)…"))
        self.tarea = Tarea(lambda aviso: {"salida": nube.instalar()})
        self.tarea.listo.connect(lambda r: mensaje(
            self, t("Motor instalado"), t("El motor de video ya está en tu nube de Modal. Elige «Mi nube Modal» en "
                                          "«Animar escenas con IA de video».")))
        self.tarea.fallo.connect(lambda e: mensaje_error(self, t("No se pudo instalar"), e))
        self.tarea.finished.connect(lambda: (self.instalar.setEnabled(True),
                                             self.instalar.setText(t("Instalar motor en Modal"))))
        self.tarea.start()

    def _refrescar(self):
        self.lista.clear()
        for archivo in claves.apartadas():
            self.lista.addItem("⚠️  " + t("No se pudo leer un archivo de claves y se apartó (cifrado) en "
                                          "datos/{archivo}. Vuelve a conectar tus claves; puedes borrar ese archivo.",
                                          archivo=archivo.name))
        for c in claves.publico():
            modelos = " · ".join(f"{u}: {c.get('modelo_' + u)}" for u in c["usos"] if c.get("modelo_" + u))
            item = QListWidgetItem(f"✅  {c['proveedor'].upper()}   {c['clave']}\n      {modelos}")
            item.setData(Qt.UserRole, c["proveedor"])
            self.lista.addItem(item)
        if not self.lista.count():
            self.lista.addItem(t("Sin claves todavía: casi todo funciona en modo gratis sin clave, pero más lento y "
                                 "simple (guiones con IA básica, ~1 imagen por hora, 2 min de GPU al día). La música "
                                 "con IA sí necesita clave (ElevenLabs o Gemini).\n"
                                 "Para más calidad y velocidad, conecta claves gratis: Groq (console.groq.com), "
                                 "Cloudflare (imágenes) y Hugging Face (animar fotos)."))
        conectadas = claves.cargar()
        for clave, estado in self.estados.items():
            estado.setText(f"✓ {t('Conectada')}" if clave in conectadas else t("No conectada"))
            estado.setStyleSheet("color: #3DDC97; font-weight: 700;" if clave in conectadas else "color: #8D8D9A;")
        self.uso_nube.setText(t("Hoy: {n} de {m} clips", n=nube.usados_hoy(), m=nube.limite())
                              if "modal" in conectadas else t("Sin conectar"))
        self.nota_diseno.setVisible(not {"anthropic", "openai"} & conectadas.keys())
        actual = claves.ajustes()
        for uso, combo in self.selectores.items():
            combo.blockSignals(True)
            combo.clear()
            for p in claves.opciones(uso):
                nombre = NOMBRES_PROVEEDOR.get(p, p.capitalize())
                if uso == "video" and p == "auto":  # que se sepa adónde va la foto antes de elegir
                    nombre = t("Automático (gratis primero: Space público de Hugging Face)")
                elif uso == "diseno" and p == "auto":
                    nombre = t("La misma que escribe los guiones")
                elif uso == "video_voz" and p == "auto":  # Kling y Seedance cobran: solo eligiéndolos
                    nombre = t("Automático (Gemini, si está conectada)")
                combo.addItem(nombre, p)
            combo.setCurrentIndex(max(combo.findData(actual.get(uso, "auto")), 0))
            combo.blockSignals(False)

    def _abrir_consola(self, web, proveedor):
        """La página donde se saca la clave; la de Kling y Seedance la da su módulo (CONSOLA)."""
        try:
            web = web or claves.modulo_video(proveedor).CONSOLA
        except ImportError:
            return mensaje_error(self, t("Todavía no disponible"), t("Esta versión de Ráfaga Studio todavía no trae "
                                                                     "{proveedor}: actualízala.",
                                                                     proveedor=proveedor.capitalize()))
        QDesktopServices.openUrl(QUrl(web))

    def _conectar(self, proveedor=None, servicio=""):
        """Comprueba la clave en otro hilo (la ventana no se congela). Con proveedor (Kling o Seedance), la clave se
        pide en una ventana aparte, oculta, y se prueba solo con ese servicio."""
        if self.tarea and self.tarea.isRunning():  # soltar un hilo que corre tumba la app
            return
        if proveedor:
            clave, ok = QInputDialog.getText(self, t("Conectar {servicio}", servicio=servicio),
                                             t("Pega tu clave de API de {servicio}:", servicio=servicio),
                                             QLineEdit.Password)
            clave = clave.strip() if ok else ""
        else:
            clave = self.entrada.text().strip()
        if not clave:
            return
        self.conectar.setEnabled(False)
        self.conectar.setText(t("Comprobando…"))
        self.tarea = Tarea(lambda clave, aviso: claves.detectar(clave, proveedor or None), clave=clave)
        self.tarea.listo.connect(self._conectada)
        self.tarea.fallo.connect(lambda e: mensaje_error(self, t("Clave no válida"), e))
        self.tarea.finished.connect(lambda: (self.conectar.setEnabled(True), self.conectar.setText(t("Conectar"))))
        self.tarea.start()

    def _conectada(self, info):
        claves.guardar(info)
        self.entrada.clear()
        self._refrescar()

    def _quitar(self):
        item = self.lista.currentItem()
        if item and item.data(Qt.UserRole):
            claves.borrar(item.data(Qt.UserRole))
            self._refrescar()
