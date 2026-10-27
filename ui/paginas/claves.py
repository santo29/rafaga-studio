"""Página «Claves de IA»: conectar claves, comprobar que funcionan, ver en qué se va el dinero (la actividad de la IA),
elegir proveedor por defecto y la nube Modal."""
import time

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from motor import actividad, claves, nube
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje, mensaje_error, Tarea, tarjeta
from ui.paginas.guardia import _estilo_chip  # la misma pastilla de vidrio que la gravedad de Ráfaga Guardia

# Lo que dice cada estado comprobado junto a su servicio, y su color: verde funciona, ámbar espera o revisa, rojo no
# funciona hasta que hagas algo (recargar o cambiar la clave)
ESTADOS = {"ok": (t("Funciona"), "#3DDC97"), "sin_saldo": (t("Sin saldo"), "#FF4D8D"),
           "clave": (t("Clave no válida"), "#FF4D8D"), "sin_cuota": (t("Sin cuota ahora"), "#FFB454"),
           "sin_conexion": (t("Sin conexión"), "#FFB454"), "error": (t("Falló al comprobar"), "#FFB454"),
           "comprobando": (t("Comprobando…"), "#A9A9B6"), "conectada": (t("Conectada"), "#A9A9B6")}
MAX_ACTIVIDAD = 50  # las últimas llamadas a la IA que se ven (actividad.json guarda más)
# La tabla de la actividad, como las listas de la app: fondo oscuro, sin rejilla y la cabecera discreta
ESTILO_TABLA = """
QTableWidget { background: #0F0F13; border: 1px solid #24242C; border-radius: 10px; padding: 4px;
               gridline-color: transparent; selection-background-color: rgba(124, 92, 255, 0.30); font-size: 14px; }
QTableWidget::item { padding: 4px 8px; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section { background: transparent; color: #8D8D9A; border: none; border-bottom: 1px solid #24242C;
                       padding: 6px 8px; font-size: 13px; font-weight: 600; }
"""


USOS_UI = {"texto": t("Guiones y selección de clips"), "diseno": t("IA que diseña"), "imagen": t("Imágenes"),
           "video": t("Animar escenas con IA de video"), "video_voz": t("Escenas que hablan"),
           "transcripcion": t("Transcripción"), "musica": t("Música")}


NOMBRES_PROVEEDOR = {"auto": t("Automático (la mejor conectada)"), "pollinations": t("Pollinations (gratis)"),
                     "pc": t("Este PC (gratis, más lento)"), "ninguno": t("No usar (zoom suave sobre la imagen)"),
                     "huggingface": t("Hugging Face (gratis; Space público de la comunidad)"), "openai": "OpenAI",
                     "anthropic": "Claude (Anthropic)", "modal": t("Mi nube Modal (US$30 gratis al mes)"),
                     "elevenlabs": "ElevenLabs", "gemini": "Gemini (Google)",
                     "cloudflare": t("Cloudflare (gratis cada día)"), "groq": t("Groq (gratis)"),
                     "kling": t("Kling (de pago)"), "seedance": t("Seedance (de pago)")}


# Cada servicio que se puede conectar: para qué sirve, cuánto cuesta y dónde se saca la clave (de lo gratis a lo de pago)
SERVICIOS = [
    ("groq", "Groq", t("Guiones con IA y transcripción rápida"), t("Gratis"), "https://console.groq.com/keys"),
    ("gemini", "Gemini (Google)", t("Guiones con IA; imágenes Nano Banana (si las eliges), videos animados con voz y música con Lyria"),
     t("Gratis (imágenes, video y música de pago)"),
     "https://aistudio.google.com/app/apikey"),
    ("cloudflare", "Cloudflare Workers AI", t("Imágenes, unas 100 al día. Pega juntos el ID de cuenta y el token"),
     t("Gratis"), "https://dash.cloudflare.com/profile/api-tokens"),
    ("pollinations", "Pollinations", t("Imágenes y guiones sin marca de agua"), t("Gratis"),
     "https://enter.pollinations.ai"),
    ("huggingface", "Hugging Face", t("Más cuota para animar fotos e imágenes"), t("Gratis"),
     "https://huggingface.co/settings/tokens"),
    ("modal", "Modal", t("Tu nube de video con IA. Pega las dos partes del token (ak-… as-…)"),
     t("Gratis: US$1 al mes; US$30 con tarjeta"), "https://modal.com/settings/tokens"),
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
     t("De pago (unos US$0.04 a 0.13 por segundo)"), None),
    ("seedance", "Seedance (BytePlus)", t("Animar escenas y escenas que hablan con su propio audio"),
     t("De pago (unos US$0.02 a 0.24 por segundo)"), None),
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
        # Comprobar: si cada servicio conectado funciona de verdad, si le queda saldo o cuota y si su clave vale
        cabeza = QHBoxLayout()
        cabeza.addWidget(etiqueta(t("Servicios que puedes conectar"), "sub"), 1)
        self.comprobado = etiqueta("", "sub")
        self.comprobado.setWordWrap(False)
        cabeza.addWidget(self.comprobado)
        self.comprobar = boton(t("Comprobar conexiones"))
        self.comprobar.setToolTip(t("Pregunta a cada servicio conectado si funciona, si le queda saldo o cuota y si su "
                                    "clave vale. Es gratis, salvo en Gemini: menos de una milésima de centavo."))
        self.comprobar.clicked.connect(lambda: self.comprobar_ahora())
        cabeza.addWidget(self.comprobar)
        servicios_lay.addLayout(cabeza)
        servicios_lay.addWidget(etiqueta(t("Kling y Seedance son de pago: se conectan con su botón «Conectar», y antes "
                                           "de cada trabajo que los usa la app te dice lo que puede costar."), "sub"))
        # Qué hacer con cada servicio que no atiende (recargar, otra clave…), arriba: se ve sin bajar por la lista
        self.pasos = etiqueta("")
        self.pasos.setStyleSheet("color: #FFB454;")
        servicios_lay.addWidget(self.pasos)
        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(16)
        self.estados, self.botones_pago = {}, {}
        for n, (clave, nombre, para, precio, web) in enumerate(SERVICIOS):
            titulo = etiqueta(nombre)
            titulo.setStyleSheet("font-weight: 700;")
            estado = QLabel()  # una pastilla de su color, del ancho de su texto (no de la columna)
            estado.setAlignment(Qt.AlignCenter)
            conseguir = boton(t("Conseguir clave ↗"))
            conseguir.clicked.connect(lambda _, w=web, c=clave: self._abrir_consola(w, c))
            for columna, w in enumerate((titulo, etiqueta(para, "sub"), etiqueta(precio, "sub"))):
                rejilla.addWidget(w, n, columna)
            rejilla.addWidget(estado, n, 3, Qt.AlignLeft | Qt.AlignVCenter)
            botones = QVBoxLayout()  # uno encima del otro: una columna más dejaba la descripción en 120 px a 1280 px
            botones.addWidget(conseguir)
            if clave in claves.VIDEO_DE_PAGO:  # su clave no se reconoce sola: se dice de quién es
                self.botones_pago[clave] = boton(t("Conectar"))
                self.botones_pago[clave].clicked.connect(lambda _, c=clave, s=nombre: self._conectar(c, s))
                botones.addWidget(self.botones_pago[clave])
            rejilla.addLayout(botones, n, 4)
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
        # Actividad de la IA: adónde se va el dinero de cada servicio (pasó: el dueño no sabía en qué se le fueron los
        # US$5 de Gemini). La apunta motor/actividad.py en cada llamada, desde la app y desde el MCP
        uso_ia, uso_lay = tarjeta()
        uso_lay.addWidget(etiqueta(t("Actividad de la IA"), "sub"))
        uso_lay.addWidget(etiqueta(t("Cada vez que el estudio usa una IA queda aquí: para qué, con qué servicio, lo que "
                                     "cuesta como mucho y cómo salió. Es una estimación por lo alto con los precios del "
                                     "estudio: lo exacto está en la web de cada servicio."), "sub"))
        self.gasto = etiqueta("")
        uso_lay.addWidget(self.gasto)
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels([t("Cuándo"), t("Tarea"), t("Qué"), t("Servicio"), t("Costo"),
                                              t("Resultado")])
        self.tabla.setStyleSheet(ESTILO_TABLA)
        self.tabla.verticalHeader().hide()
        self.tabla.setShowGrid(False)
        self.tabla.setWordWrap(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setFocusPolicy(Qt.NoFocus)
        self.tabla.setMinimumHeight(320)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(5, QHeaderView.Stretch)  # el resultado ocupa lo que quede (entero, al pasar)
        cabecera.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        uso_lay.addWidget(self.tabla)
        self.sin_actividad = etiqueta(t("Todavía no hay llamadas a la IA."), "sub")
        uso_lay.addWidget(self.sin_actividad)
        lay.addWidget(uso_ia)
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
        # Apagado de fábrica: con él, la app ya no puede impedir que un enlace llegue a tu red local (seguro.es_fake_ip).
        # El aviso va debajo: una casilla no parte su texto en líneas y, entero, la página no cabía en 1280 px
        fake_ip = QCheckBox(t("Uso un proxy «fake-ip» (Clash…): permitir descargas a través de él."))
        fake_ip.setChecked(claves.ajustes().get("proxy_fake_ip") is True)
        fake_ip.toggled.connect(lambda v: claves.elegir_por_defecto("proxy_fake_ip", v))
        defecto_lay.addWidget(fake_ip)
        defecto_lay.addWidget(etiqueta(t("Con esto la app ya no puede impedir que un enlace llegue a tu red local."),
                                       "sub"))
        lay.addWidget(defecto)
        # Nube de video en Modal: instalar el motor una vez y fijar el tope diario para no pasar del crédito gratis.
        nube_caja, nube_lay = tarjeta()
        nube_lay.addWidget(etiqueta(f"☁️  {t('Mi nube de video (Modal)')}", "sub"))
        nube_lay.addWidget(etiqueta(t("Crea una cuenta en modal.com, crea un token en Settings → API tokens (ak-… y "
                                      "as-…), pega las dos partes juntas arriba y pulsa «Instalar motor». Plan "
                                      "Starter: US$1 de crédito gratis al mes sin tarjeta, o US$30 gratis al mes si "
                                      "añades un método de pago (pon un límite de uso de US$30 en Usage & billing "
                                      "para no pagar nada). Cada clip de 5 s cuesta unos US$0.20 a 0.35.")))
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
        self.tarea = self.revision = None  # conectar o instalar, y la comprobación de conexiones (van a la vez)
        self._refrescar()

    def showEvent(self, evento):  # lo apuntado mientras se trabajaba en otra página
        self._pintar_estados()
        self._pintar_actividad()
        super().showEvent(evento)

    def comprobar_ahora(self, al_abrir: bool = False):
        """Comprueba en otro hilo cada servicio conectado (claves.comprobar). al_abrir: la de cuando se abre la app;
        si falla, no salta ninguna ventana (se ve en su pastilla y se puede repetir con el botón)."""
        if (self.revision and self.revision.isRunning()) or not claves.cargar():
            return
        self.comprobar.setEnabled(False)
        self.comprobar.setText(t("Comprobando…"))
        self._pintar_estados(comprobando=True)
        self.revision = Tarea(lambda aviso: {"estados": claves.comprobar()})
        if not al_abrir:
            self.revision.fallo.connect(lambda e: mensaje_error(self, t("No se pudo comprobar"), e))
        self.revision.finished.connect(self._comprobado)
        self.revision.start()

    def _comprobado(self):
        self.comprobar.setEnabled(True)
        self.comprobar.setText(t("Comprobar conexiones"))
        self._pintar_estados()
        self._pintar_actividad()  # la comprobación de Gemini es un pedido de verdad: también sale ahí

    def cerrar(self):
        """Al cerrar la app: un hilo vivo al salir la tumbaría. Cada servicio tiene 20 s de plazo; pasado un rato, se
        cierra igual."""
        if self.revision:
            self.revision.blockSignals(True)
            self.revision.wait(5_000)

    def _pintar_estados(self, comprobando: bool = False):
        """La pastilla de cada servicio (Funciona, Sin saldo, Clave no válida…), con el detalle y qué hacer al pasar
        el ratón; debajo, qué hacer con los que no atienden; arriba, cuándo se comprobó."""
        conectadas, estados = claves.cargar(), claves.estados()
        pasos, fechas = [], []
        for proveedor, pastilla in self.estados.items():
            e = estados.get(proveedor) or {}
            if proveedor not in conectadas:
                pastilla.setText(t("No conectada"))
                pastilla.setStyleSheet("color: #8D8D9A;")
                pastilla.setToolTip("")
                continue
            texto, color = ESTADOS["comprobando" if comprobando else e.get("estado", "conectada")]
            pastilla.setText(texto)
            pastilla.setStyleSheet(_estilo_chip(color))
            pastilla.setToolTip("\n".join(d for d in (e.get("detalle"), e.get("paso"), claves._cuando(e)) if d) if e
                                else t("Pulsa «Comprobar conexiones» para saber si funciona."))
            if e:
                fechas.append(e["fecha"])
            if e.get("estado", "ok") != "ok" and e.get("paso"):
                pasos.append(f"⚠️ {claves.frase(proveedor, e['estado'])}. {e['paso']}")
        self.pasos.setText("\n".join(pasos))
        self.pasos.setVisible(bool(pasos))
        ultima = claves._cuando({"fecha": max(fechas)}) if fechas else ""
        self.comprobado.setText(ultima[:1].upper() + ultima[1:])

    def _pintar_actividad(self):
        """Lo gastado hoy y este mes por servicio, y las últimas llamadas a la IA (de la más nueva a la más vieja)."""
        gasto = actividad.gasto()

        def importes(por_servicio: dict) -> str:
            if not por_servicio:
                return t("nada de pago")
            partes = [f"{actividad.nombre_servicio(p)} {actividad.texto_costo(usd)}"
                      for p, usd in sorted(por_servicio.items(), key=lambda x: -x[1])]
            total = t("total {costo}", costo=actividad.texto_costo(sum(por_servicio.values())))
            return " · ".join(partes) + (f" ({total})" if len(partes) > 1 else "")
        self.gasto.setText(t("Gasto estimado de hoy: {importes}", importes=importes(gasto["hoy"])) + "\n"
                           + t("Este mes: {importes}", importes=importes(gasto["mes"])))
        llamadas = actividad.ultimas(MAX_ACTIVIDAD)
        hoy = time.strftime("%Y-%m-%d")
        self.tabla.setRowCount(len(llamadas))
        for fila, l in enumerate(llamadas):
            fecha, fallo = l["fecha"], l["resultado"] != "ok"
            tarea = actividad.nombre_tarea(l["tarea"])
            celdas = (fecha[11:16] if fecha[:10] == hoy else f"{fecha[8:10]}/{fecha[5:7]} {fecha[11:16]}",
                      f"{t('Agente MCP')} · {tarea}" if l["origen"] == "mcp" else tarea,
                      actividad.nombre_que(l["que"]), actividad.nombre_servicio(l["proveedor"]),
                      t("no se cobró") if fallo and not l["costo"] else actividad.texto_costo(l["costo"]),
                      actividad.texto_resultado(l))
            for columna, texto in enumerate(celdas):
                celda = QTableWidgetItem(texto)
                celda.setToolTip(f"{texto}\n{l['modelo']}" if columna == 3 and l["modelo"] else texto)
                if columna == 5:
                    celda.setForeground(QColor("#FFB454" if fallo else "#3DDC97"))
                self.tabla.setItem(fila, columna, celda)
        self.tabla.setVisible(bool(llamadas))
        self.sin_actividad.setVisible(not llamadas)

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
            self.lista.addItem("⚠️ " + t("No se pudo leer un archivo de claves: se guardó aparte, cifrado, en la "
                                         "carpeta de datos de la app ({archivo}). No lo borres: si sus claves se "
                                         "pueden leer, la app las recupera sola. Mientras, vuelve a conectar las que "
                                         "necesites.", archivo=archivo.name))
        for c in claves.publico():
            modelos = " · ".join(f"{USOS_UI.get(u, u)}: {c.get('modelo_' + u)}" for u in c["usos"]
                                 if c.get("modelo_" + u))
            item = QListWidgetItem(f"✅ {claves.nombre(c['proveedor'])} · {c['clave']}" + (f"\n{modelos}" if modelos else ""))
            item.setData(Qt.UserRole, c["proveedor"])
            self.lista.addItem(item)
        if not self.lista.count():
            self.lista.addItem(t("Sin claves todavía: casi todo funciona en modo gratis sin clave, pero más lento y "
                                 "simple (guiones con IA básica, una imagen por hora y unos minutos de animación al día). La música "
                                 "con IA sí necesita clave (ElevenLabs o Gemini).\n"
                                 "Para más calidad y velocidad, conecta claves gratis: Groq (console.groq.com), "
                                 "Cloudflare (imágenes) y Hugging Face (animar fotos)."))
        conectadas = claves.cargar()
        self._pintar_estados()
        self._pintar_actividad()
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
        botones = [self.conectar] + ([self.botones_pago[proveedor]] if proveedor else [])  # el de su fila, a la vista
        for b in botones:
            b.setEnabled(False)
            b.setText(t("Comprobando…"))
        self.tarea = Tarea(lambda clave, aviso: claves.detectar(clave, proveedor or None), clave=clave)
        self.tarea.listo.connect(lambda info: self._conectada(info, limpiar=not proveedor))
        self.tarea.fallo.connect(lambda e: mensaje_error(self, t("Clave no válida"), e))
        self.tarea.finished.connect(lambda: [(b.setEnabled(True), b.setText(t("Conectar"))) for b in botones])
        self.tarea.start()

    def _conectada(self, info, limpiar=True):
        claves.guardar(info)
        if limpiar:  # la de Kling o Seedance se pegó en su ventana: lo que haya en el cuadro de arriba se queda
            self.entrada.clear()
        self._refrescar()

    def _quitar(self):
        item = self.lista.currentItem()
        if item and item.data(Qt.UserRole):
            claves.borrar(item.data(Qt.UserRole))
            self._refrescar()
