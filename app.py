"""Ráfaga Studio: app de escritorio. Crea videos con IA y saca shorts de videos largos."""
import math
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QProcess, Qt, QTimer, QTranslator
from PySide6.QtGui import QColor, QFont, QIcon, QImageReader, QKeySequence, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QButtonGroup, QComboBox, QFrame,
                               QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from motor import claves, diseno_ia, guardia, idioma
from motor.idioma import t
from ui import iconos, legal
from ui.brillo import Brillo
from ui.comun import (AvisosLegibles, boton, ESTILO, EstiloApp, etiqueta, NOMBRES_FORMATO, Reproductor,
                      SelectorModelo, VisorImagen)
from ui.linea_tiempo import render
from ui.paginas.anuncios import PaginaAnuncios
from ui.paginas.cabina import PaginaCabina
from ui.paginas.claves import PaginaClaves
from ui.paginas.crear import PaginaCrear
from ui.paginas.director import PAGINA, PaginaDirector
from ui.paginas.diseno import PaginaDiseno
from ui.paginas.edicion import PaginaEdicion
from ui.paginas.guardia import BLOQUEADO, COLORES, ESCUDOS, PaginaGuardia, TITULOS
from ui.paginas.inicio import PaginaInicio
from ui.paginas.mcp import PaginaMCP
from ui.paginas.musica import PaginaMusica
from ui.paginas.nichos import PaginaNichos
from ui.paginas.proyectos import PaginaProyectos
from ui.paginas.publicar import PaginaPublicar
from ui.paginas.serie import PaginaSerie
from ui.paginas.shorts import PaginaShorts

# Siempre desde la carpeta de la app, la arranque quien la arranque: yt-dlp busca node/deno primero en la carpeta de
# trabajo, y un «deno.cmd» en otra carpeta (p. ej. Descargas) se ejecutaría.
os.chdir(Path(__file__).resolve().parent)
ICONO = Path(__file__).resolve().parent / "assets" / "icono.ico"


def _sin_ventana(popen=subprocess.Popen.__init__):
    """La app corre con pythonw, sin consola: cada programa de consola que lanzaba (ffmpeg, yt-dlp, demucs…) abría una
    ventana negra encima del estudio. Así va para todos a la vez, también los que lanzan las librerías."""
    def __init__(self, *args, creationflags=0, **kwargs):
        popen(self, *args, creationflags=creationflags | subprocess.CREATE_NO_WINDOW, **kwargs)
    return __init__


if sys.platform == "win32":
    subprocess.Popen.__init__ = _sin_ventana()


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ráfaga Studio")
        self.resize(1280, 860)
        raiz = QWidget()
        lay = QHBoxLayout(raiz)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        barra = QFrame()
        barra.setObjectName("barra")
        barra.setFixedWidth(250)
        nav = QVBoxLayout(barra)
        nav.setContentsMargins(10, 0, 10, 16)
        marca = QHBoxLayout()  # el icono de la app junto al nombre (no un emoji)
        marca.setContentsMargins(14, 18, 0, 22)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ICONO.with_suffix(".png"))).scaled(30, 30, Qt.KeepAspectRatio,
                                                                      Qt.SmoothTransformation))
        marca.addWidget(logo)
        marca.addWidget(etiqueta("Ráfaga Studio", "marca"), 1)
        nav.addLayout(marca)
        self.paginas = QStackedWidget()
        self.paginas.setObjectName("contenido")
        self.grupo = QButtonGroup(self)
        Reproductor.al_editar = self._editar_video  # antes de crear las páginas: así sale su botón «✂️ Editar»
        VisorImagen.al_disenar, VisorImagen.al_animar = self._disenar_imagen, self._animar_imagen
        self.crear, self.claves, self.diseno, self.edicion = PaginaCrear(), PaginaClaves(), PaginaDiseno(), PaginaEdicion()
        self.director = PaginaDirector(abrir_diseno=self._abrir_diseno, abrir_serie=self._abrir_serie)
        self.serie = PaginaSerie()
        self.guardia = PaginaGuardia()  # revisa la app en segundo plano al abrirla
        self.musica = PaginaMusica()
        self.inicio = PaginaInicio(self._ir_pagina, self._abrir_edicion, self._abrir_serie, self._usar_pedido,
                                   self._pedir)
        # Lo más buscado arriba: a 728 px de alto, Diseño y Dibujos animados se ven sin desplazar el menú
        paginas = [(f"🏠  {t('Inicio')}", self.inicio),
                   (f"🤖  {t('Director IA')}", self.director), (f"✨  {t('Crear con IA')}", self.crear),
                   (f"🎨  {t('Diseño')}", self.diseno), (f"🐰  {t('Dibujos animados')}", self.serie),
                   (f"✂️  {t('Editor de video')}", self.edicion),
                   (f"⚡  {t('Shorts mágicos')}", PaginaShorts()), (f"🚀  {t('Anuncios')}", PaginaAnuncios()),
                   (f"🎵  {t('Música')}", self.musica),
                   (f"🎙️  {t('Cabina de grabación')}", PaginaCabina()),
                   (f"🔎  {t('Nichos virales')}", PaginaNichos(self._crear_desde_idea)),
                   (f"🎬  {t('Mis proyectos')}", PaginaProyectos()), (f"📅  {t('Publicar')}", PaginaPublicar()),
                   (f"🔑  {t('Claves de IA')}", self.claves),
                   (f"🔌  {t('Conexión MCP')}", PaginaMCP()), (f"🛡️  {t('Ráfaga Guardia')}", self.guardia)]
        self.orden = [p for _, p in paginas]  # para ir a una página sin contar posiciones
        # «Conectar más modelos…» del selector «Modelo de video» (Director y Crear) lleva a «Claves de IA»
        SelectorModelo.ir_a_claves = lambda: self.ir_a(self.orden.index(self.claves))
        # El menú se desplaza solo si no cabe: así la ventana entra en pantallas de portátil (768 px de alto)
        menu = QWidget()
        botones = QVBoxLayout(menu)
        botones.setContentsMargins(0, 0, 0, 0)
        botones.setSpacing(2)  # junto con el padding de #nav: los 16 botones caben a 728 px de alto sin desplazar
        desplaza_menu = QScrollArea()
        desplaza_menu.setWidgetResizable(True)
        desplaza_menu.setFrameShape(QFrame.NoFrame)
        desplaza_menu.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplaza_menu.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        desplaza_menu.setWidget(menu)
        nav.addWidget(desplaza_menu, 1)
        for i, (nombre, pagina) in enumerate(paginas):
            b = boton(nombre, "nav")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _, i=i: self.ir_a(i))
            self.grupo.addButton(b)
            botones.addWidget(b)
            # Cada página con su barra de desplazamiento, para pantallas pequeñas.
            desplazable = QScrollArea()
            desplazable.setObjectName("pagina")  # transparente: deja ver la luz de ambiente de #contenido (ESTILO)
            desplazable.setWidgetResizable(True)
            desplazable.setFrameShape(QFrame.NoFrame)
            desplazable.setWidget(pagina)
            self.paginas.addWidget(desplazable)
        botones.addStretch()
        # El escudo de Ráfaga Guardia, el último del menú, lleva el color de su estado (verde, ámbar, rojo)
        self.escudo = self.grupo.buttons()[-1]
        self.guardia.estado_cambiado.connect(self._escudo)
        self.guardia.abrir.connect(self._abrir_guardia)
        self._escudo(self.guardia.estado or "ok")
        nav.addWidget(self._selector_idioma())
        privacidad = boton(f"⚖️  {t('Privacidad y legal')}", "nav")
        privacidad.clicked.connect(lambda: legal.acerca_de(self))
        nav.addWidget(privacidad)
        lay.addWidget(barra)
        lay.addWidget(self.paginas, 1)
        self.setCentralWidget(raiz)
        # La luz del asistente de voz recorre el borde de toda la ventana; y el menú se ilumina en la página que usa
        self.director.brillo = Brillo(raiz)
        self.director.usando.connect(self._iluminar)
        self.director.termino.connect(lambda: self._iluminar(None))
        hablar = QShortcut(QKeySequence("Ctrl+Space"), self)
        hablar.setAutoRepeat(False)  # mantenerlo pulsado mientras hablas lo encendía y apagaba (Windows repite la tecla)
        hablar.activated.connect(lambda: (self.ir_a(self.orden.index(self.director)), self.director.alternar_voz()))
        for campo in raiz.findChildren(QAbstractSpinBox):  # Qt ignora el padding izquierdo de ESTILO en estos campos
            campo.lineEdit().setTextMargins(6, 0, 0, 0)
        if not claves.para("texto"):  # el Director funciona igual (con la IA gratis sin clave), pero lento: se avisa
            self.director.consejo_claves(lambda: self.ir_a(self.orden.index(self.claves)))

    def ir_a(self, i):
        self.paginas.setCurrentIndex(i)
        self.grupo.buttons()[i].setChecked(True)

    def _escudo(self, estado):
        """El escudo de Ráfaga Guardia en el menú, del color de su estado."""
        self.escudo.setIcon(iconos.icono(ESCUDOS[estado], COLORES[estado]))
        self.escudo.setProperty("icono", ESCUDOS[estado])  # como poner(): qué icono lleva
        self.escudo.setToolTip(f"{t('Ráfaga Guardia')}: {BLOQUEADO if guardia.bloqueado() else TITULOS[estado]}")

    def _abrir_guardia(self):
        """La notificación de Ráfaga Guardia pulsada: la ventana delante, en su página."""
        self.ir_a(self.orden.index(self.guardia))
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _ir_pagina(self, nombre):
        """Va a la página del menú con ese nombre (sin traducir, como en PAGINA del Director)."""
        self.ir_a(next(i for i, b in enumerate(self.grupo.buttons()) if b.text() == t(nombre)))

    def _abrir_edicion(self, carpeta):
        """Abre en el editor un video guardado (desde Inicio), si no se pierden cambios sin guardar."""
        if self.edicion._descartar_ok():
            self.edicion.abrir(carpeta)
            self.ir_a(self.orden.index(self.edicion))

    def _abrir_diseno(self, carpeta):
        """Abre en Diseño un diseño guardado (desde el Director), si no se pierden cambios sin guardar."""
        if self.diseno._descartar_ok():
            self.diseno.abrir(carpeta)
            self.ir_a(self.orden.index(self.diseno))

    def _disenar_imagen(self, ruta, titulo=""):
        """«Editar en Diseño» del visor: un diseño guardado (lo que hizo el Director) se abre tal cual; una imagen
        suelta (un ejemplo) entra en un diseño nuevo, con su título."""
        if (Path(ruta).parent / "diseno.json").is_file():
            return self._abrir_diseno(Path(ruta).parent)
        if self.diseno._descartar_ok():
            self.diseno.desde_imagen(ruta, titulo)
            self.ir_a(self.orden.index(self.diseno))

    def _animar_imagen(self, ruta):
        """«Animar» del visor: Crear con IA con la imagen, «Solo animar la imagen» y el formato que más se le parece,
        escrito y sin empezar (si anima una IA de pago, «Generar video» pregunta antes lo que cuesta). Un pedido que
        el usuario ya escribió ahí no se pisa sin preguntar."""
        crear, tam = self.crear, QImageReader(ruta).size()
        sugerido, escrito = t("Que cobre vida con un movimiento suave y natural"), crear.prompt.toPlainText().strip()
        if escrito and escrito != sugerido and QMessageBox.question(
                self, t("Animar la imagen"), t("En Crear con IA ya hay un pedido escrito. ¿Cambiarlo por el de animar "
                                               "esta imagen?")) != QMessageBox.Yes:
            return
        forma = tam.width() / tam.height() if not tam.isEmpty() else 1
        proporciones = {f: int(f.split(":")[0]) / int(f.split(":")[1]) for f in NOMBRES_FORMATO}
        elegido = min(proporciones, key=lambda f: abs(math.log(proporciones[f] / forma)))  # un cuadrado no se recorta
        next(b for b in crear.formato.grupo.buttons() if b.property("formato") == elegido).setChecked(True)
        crear.imagen.setText(ruta)
        crear.modo.setCurrentIndex(1)
        crear.prompt.setPlainText(sugerido)
        self.ir_a(self.orden.index(crear))
        if crear.modelo.valor() == "ninguno":  # «Sin animar» recordado no anima: Automático, que llegue listo
            next(a for a in crear.modelo.menu().actions() if a.data() == "auto").trigger()
        crear.prompt.setFocus()
        crear.prompt.selectAll()  # escribir encima cambia el movimiento

    def _abrir_serie(self, nombre):
        """Abre la página de la serie con esa serie elegida (desde Inicio o el Director)."""
        self.serie.recargar(nombre)
        self.ir_a(self.orden.index(self.serie))

    def _iluminar(self, herramienta):
        """Brilla el botón del menú de la página que está usando el Director (None: se apagan todos)."""
        nombre = t(PAGINA[herramienta]) if herramienta in PAGINA else None
        for b in self.grupo.buttons():
            if b.text() == nombre:
                luz = QGraphicsDropShadowEffect(b)
                luz.setColor(QColor("#00E5FF"))
                luz.setBlurRadius(28)
                luz.setOffset(0, 0)
                b.setGraphicsEffect(luz)
            else:
                b.setGraphicsEffect(None)

    def _selector_idioma(self):
        """Idioma de la app: automático (el del PC o el del país, ver motor/idioma.py) o uno fijo. Se aplica al reiniciar."""
        combo = QComboBox()
        combo.setToolTip(t("Idioma de la app"))
        combo.addItem(iconos.icono("languages"), t("{idioma} (auto)", idioma=idioma.IDIOMAS[idioma.actual()]), "auto")
        for codigo, nombre in idioma.IDIOMAS.items():
            combo.addItem(iconos.icono("languages"), nombre, codigo)
        combo.setCurrentIndex(combo.findData(idioma.elegido()))
        combo.currentIndexChanged.connect(lambda _: self._cambiar_idioma(combo.currentData()))
        return combo

    def _cambiar_idioma(self, codigo):
        idioma.elegir(codigo)
        reiniciar = QMessageBox.question(self, t("Idioma"), t("El idioma cambia al reiniciar la app. ¿Reiniciar ahora?"))
        if reiniciar == QMessageBox.Yes and self.close():  # close() pregunta antes si hay algo sin guardar
            # -s -E como el acceso directo: el reinicio no lee las librerías de la cuenta ni un PYTHONPATH ajeno
            QProcess.startDetached(sys.executable, ["-s", "-E", str(Path(__file__).resolve())],
                                   str(Path(__file__).resolve().parent))

    def closeEvent(self, e):
        # Grabándote en el editor: la toma se para, se guarda y entra en el video antes de preguntar si guardarlo
        self.edicion.parar_grabacion()
        # Primero lo que está trabajando y después lo que no se guardó: un «No» aquí tras «No guardar» dejaba la app
        # abierta con los cambios a la vista, pero ya dados por guardados y sin su copia automática
        if self.director.ocupado() and QMessageBox.question(
                self, t("Está trabajando"), t("El Director está haciendo un trabajo. Si cierras, se pierde lo que "
                                              "lleva. ¿Cerrar igual?")) != QMessageBox.Yes:
            return e.ignore()
        # cerrar a medias dejaría ffmpeg exportando solo y un «tmp-…mp4» en Videos
        if self.edicion.tareas and QMessageBox.question(
                self, t("Está trabajando"), t("El editor de video está exportando o preparando algo. ¿Cancelarlo y "
                                              "cerrar?")) != QMessageBox.Yes:
            return e.ignore()
        # un diseño o un video sin guardar se perdería al cerrar
        if not (self.diseno._descartar_ok() and self.edicion._descartar_ok()):
            return e.ignore()
        if self.director.ocupado() and hasattr(r := render(), "cancelar"):
            r.cancelar()  # el ffmpeg del editor que esté usando el Director: así su trabajo termina enseguida
        self.director.cerrar()
        if self.edicion.tareas:
            for tarea in self.edicion.tareas:
                tarea.blockSignals(True)  # que no salga «No se pudo terminar» al cerrar
            if hasattr(r := render(), "cancelar"):  # las pruebas lo cambian por uno simulado
                r.cancelar()  # mata sus ffmpeg: el trabajo termina enseguida con un error que nadie ve
            for tarea in self.edicion.tareas:
                tarea.wait(10_000)  # ponytail: Whisper en el PC no se puede parar; pasado este rato se cierra igual
            self.edicion.tareas.clear()
        self.edicion._limpiar(self.edicion.carpeta)
        self.guardia.cerrar()

    def _editar_video(self, archivo, formato):
        if self.edicion.editar_video(archivo, formato):
            self.ir_a(self.orden.index(self.edicion))

    def _crear_desde_idea(self, prompt):
        self.crear.prompt.setPlainText(prompt)
        self.ir_a(self.orden.index(self.crear))

    def _usar_pedido(self, pedido):
        """«Usar este pedido» de un ejemplo de Inicio: al Director, escrito y listo para cambiarlo."""
        self.director.usar_pedido(pedido)
        self.ir_a(self.orden.index(self.director))

    def _pedir(self, modo, texto):
        """La idea escrita arriba en Inicio, en la página que la hace: escrita y sin empezar (empezar puede gastar cuota
        o dinero, y eso lo decide el usuario allí)."""
        if modo in ("imagen", "diseno"):
            # Sus campos son de una línea: un salto de línea llegaba tal cual (se veía pegado). Pasan a espacios, y como
            # mucho las 2000 letras que admite el pedido de Diseño. El del Director crece: sus escenas siguen en líneas
            texto = " ".join(texto.split())[:2000]
        if modo == "director":
            return self._usar_pedido(texto)
        if modo == "video":
            campo, pagina = self.crear.prompt, self.crear
            campo.setPlainText(texto)
        elif modo == "musica":
            campo, pagina = self.musica.idea, self.musica
            campo.setPlainText(texto)
        else:  # «Imagen» o «Diseño»: al pedido de la IA de Diseño; «Imagen», como ilustración o, si pide una foto, foto
            campo, pagina = self.diseno.pedido, self.diseno
            campo.setText(texto)
            tipos = self.diseno.tipo_ia
            imagen = "foto" if diseno_ia.pide_foto(texto) else "ilustracion"
            tipos.setCurrentIndex(max(0, tipos.findData(imagen if modo == "imagen" else "auto")))
        self.ir_a(self.orden.index(pagina))
        campo.setFocus()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(EstiloApp())  # Fusion: el estilo nativo de Windows ignora el tema oscuro en las listas desplegables
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(ESTILO)
    avisos_legibles = AvisosLegibles(app)  # con el zoom de Windows, ningún aviso sale cortado
    app.installEventFilter(avisos_legibles)
    # Enlaces en violeta claro (unos 7,5:1 sobre el fondo): el azul de serie (#0000FF) apenas se leía sobre #0F0F13.
    # Vale para toda la app: documentos legales, chat del Director y cualquier setMarkdown
    paleta = app.palette()
    paleta.setColor(QPalette.Link, QColor("#A892FF"))
    app.setPalette(paleta)
    app.setWindowIcon(QIcon(str(ICONO)))
    # Los botones de los diálogos de Qt (Sí/No, Aceptar/Cancelar) en el idioma de la app; sin esto salen en inglés
    traductor = QTranslator()
    if traductor.load(f"qtbase_{'pt_BR' if idioma.actual() == 'pt' else idioma.actual()}",
                      QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(traductor)
    if legal.pendiente() and not legal.aviso_inicial():  # el aviso de privacidad y los términos, al primer uso
        sys.exit(0)
    # yt-dlp (y yt-dlp-ejs, su parte para YouTube: tienen que subir juntos) se actualiza solo y en segundo plano
    # (YouTube cambia a menudo). Solo versiones ya compiladas (nada de ejecutar código de instalación), publicadas hace
    # 7 días o más (si una sale maliciosa, da tiempo a retirarla) y sin dependencias nuevas sin fijar (--no-deps).
    # Riesgo aceptado y escrito en SECURITY.md: lo demás va fijado con su hash en requirements.lock.
    QProcess.startDetached(str(Path(sys.executable).with_name("pythonw.exe")),
                           ["-s", "-E", "-m", "pip", "install", "--isolated", "-q", "-U", "--no-deps",
                            "--disable-pip-version-check", "--only-binary", ":all:",
                            "--uploaded-prior-to", "P7D", "yt-dlp", "yt-dlp-ejs"])
    ventana = Ventana()
    ventana.show()
    # La conversación de la última vez (aquí y no en la ventana: las pruebas no la leen), con la ventana ya abierta:
    # rehacer 100 mensajes con sus tarjetas tarda más de un segundo
    QTimer.singleShot(0, ventana.director.restaurar)
    # Cada servicio conectado, comprobado en segundo plano al abrir (aquí y no en la ventana: las pruebas la crean sin
    # red): así un trabajo avisa ANTES de empezar si Gemini se quedó sin saldo, y «Claves de IA» enseña su estado
    ventana.claves.comprobar_ahora(al_abrir=True)
    sys.exit(app.exec())
