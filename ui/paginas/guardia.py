"""Página «Ráfaga Guardia»: el escudo con el estado de seguridad de la app, la revisión, el historial de lo que se frenó,
el bloqueo y lo que protege y lo que no. Vigila datos/guardia.json (también lo que escribe el servidor MCP, que es otro
proceso) y avisa con una notificación de Windows de cada evento «alta». Las reglas deciden (motor/guardia.py); la IA
solo explica."""
import time
import traceback

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from motor import guardia, recursos
from motor.idioma import t
from ui.comun import boton, etiqueta, Tarea, tarjeta
from ui.iconos import icono, poner

COLORES = {"ok": "#3DDC97", "aviso": "#FFB454", "peligro": "#FF4D8D"}
ESCUDOS = {"ok": "shield-check", "aviso": "shield-alert", "peligro": "shield-x"}
TITULOS = {"ok": t("Todo en orden"), "aviso": t("Revisa esto"), "peligro": t("En peligro")}
BLOQUEADO = t("Bloqueado")  # en vez del título del estado: «en peligro» sin bloqueo no debe decir «bloqueado»
DESCRIPCIONES = {"ok": t("Ráfaga Guardia vigila la app, tus claves y tu dinero. No hay nada que revisar."),
                 "aviso": t("Hay avisos o eventos nuevos: léelos abajo. Si todo está bien, pulsa «Revisar ahora»."),
                 "peligro": t("Hay algo en peligro o un evento grave sin revisar: léelo abajo.")}
GRAVEDAD = {"alta": ("#FF4D8D", t("Alta")), "media": ("#FFB454", t("Media")), "baja": ("#A9A9B6", t("Baja"))}
ORIGENES = {"app": t("la app"), "mcp": t("un agente MCP"), "director": t("el Director")}
MARCAS = {"ok": ("circle-check", "#3DDC97"), "aviso": ("triangle-alert", "#FFB454"),
          "peligro": ("octagon-alert", "#FF4D8D")}
PROTEGE = [t("Tus claves de IA: cifradas con tu cuenta de Windows y nunca enviadas a otro servicio."),
           t("Tu dinero: nada de pago se hace sin tu «Sí»; con el bloqueo no empieza ningún video, imagen, "
             "canción ni voz de pago."),
           t("Tus archivos y tu red: ni carpetas de red, ni tu red local, ni archivos que fingen ser otra cosa."),
           t("El código de la app: si otro programa lo cambia después de instalarla, se bloquea y te avisa."),
           t("Los agentes conectados por MCP: si insisten después de tus «No», se bloquean.")]
NO_PROTEGE = [t("Tu PC entero: no es un antivirus. Ten Windows al día y su antivirus encendido."),
              t("Un programa malicioso hecho a medida que ya controla tu cuenta de Windows: puede cambiar el código y "
                "también el manifiesto con el que se compara."),
              t("Un agente que maneja tu ratón y tu teclado (no solo el MCP): podría pulsar «Sí» por ti."),
              t("Lo que pasa dentro de los servicios de IA de fuera: depende de ellos.")]
MAX_VISIBLES = 40  # el historial guarda 500; en pantalla, los más nuevos

ESTILO_GUARDIA = """
#seccion { font-size: 19px; font-weight: 700; color: #FFFFFF; }
#estado_titulo { font-size: 30px; font-weight: 800; }
#cuenta { font-size: 44px; font-weight: 800; color: #FFFFFF; }
#meta { color: #8D8D9A; font-size: 13px; }
#evento { background: transparent; border: none; border-top: 1px solid rgba(255, 255, 255, 0.06); }
#explicacion { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.16),
                                           stop:1 rgba(124, 92, 255, 0.07));
               border: 1px solid rgba(150, 125, 255, 0.28); border-top-color: rgba(210, 198, 255, 0.40);
               border-radius: 10px; padding: 10px 12px; color: #DCD6FF; font-size: 15px; }
"""


def _rgba(color: str, alfa: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alfa})"


def _estilo_chip(color: str) -> str:
    return (f"color: {color}; background: {_rgba(color, 0.13)}; border: 1px solid {_rgba(color, 0.45)};"
            f" border-top-color: {_rgba(color, 0.70)}; border-radius: 11px; padding: 2px 10px;"
            " font-size: 13px; font-weight: 700;")


def _chip(gravedad: str) -> QLabel:
    """La gravedad como una pastilla de vidrio de su color."""
    color, nombre = GRAVEDAD[gravedad]
    chip = QLabel(nombre)
    chip.setAlignment(Qt.AlignCenter)
    chip.setMinimumWidth(74)
    chip.setStyleSheet(_estilo_chip(color))
    return chip


def _vaciar(lista):
    """Quita las filas de una lista. Se esconden ya: deleteLater solo las borra en la próxima vuelta del bucle de Qt y,
    mientras, se verían debajo de las nuevas."""
    while lista.count():
        w = lista.takeAt(0).widget()
        if w:
            w.hide()
            w.deleteLater()


def _icono_fijo(nombre: str, color: str, lado: int = 20) -> QLabel:
    marca = QLabel()
    marca.setPixmap(icono(nombre, color).pixmap(lado, lado))
    marca.setFixedSize(lado + 4, lado + 4)
    marca.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
    return marca


class Escudo(QWidget):
    """El escudo grande del estado: un disco de vidrio con la luz del color del estado detrás (QSS no tiene box-shadow
    ni desenfoque: la luz se pinta aquí, como la de Segmentos)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(156, 156)
        self.estado = "ok"

    def poner(self, estado: str):
        self.estado = estado
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color, centro = QColor(COLORES[self.estado]), QPointF(self.width() / 2, self.height() / 2 + 4)
        luz = QRadialGradient(centro, self.width() / 2)
        for parada, alfa in ((0, 120), (0.55, 55), (1, 0)):
            c = QColor(color)
            c.setAlpha(alfa)
            luz.setColorAt(parada, c)
        p.fillRect(self.rect(), luz)
        disco = QRectF(centro.x() - 52, centro.y() - 56, 104, 104)
        vidrio = QLinearGradient(disco.topLeft(), disco.bottomLeft())
        vidrio.setColorAt(0, QColor(255, 255, 255, 52))
        vidrio.setColorAt(1, QColor(255, 255, 255, 12))
        p.setBrush(vidrio)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawEllipse(disco)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1.4))  # el reflejo de arriba, como el borde claro del vidrio
        p.drawArc(disco.adjusted(1.5, 1.5, -1.5, -1.5), 40 * 16, 100 * 16)
        QSvgRenderer(QByteArray(recursos.svg_icono(ESCUDOS[self.estado], COLORES[self.estado], 1.7))).render(
            p, disco.adjusted(24, 24, -24, -24))


class PaginaGuardia(QWidget):
    """El estado de seguridad de la app y lo que hizo Ráfaga Guardia. Solo aquí se puede desbloquear el estudio."""
    estado_cambiado = Signal(str)  # app.py pinta con él el escudo del menú
    abrir = Signal()  # la notificación pulsada: app.py trae esta página delante

    def __init__(self):
        super().__init__()
        self.setStyleSheet(ESTILO_GUARDIA)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(etiqueta(t("Ráfaga Guardia"), "titulo"))
        lay.addWidget(etiqueta(t("Vigila Ráfaga Studio: detecta lo que intenta atacar la app, lo frena y te avisa. Las "
                                 "reglas deciden; la IA solo te lo explica."), "sub"))

        portada, portada_lay = tarjeta()
        fila = QHBoxLayout()
        fila.setSpacing(22)
        self.escudo = Escudo()
        fila.addWidget(self.escudo, 0, Qt.AlignTop)
        columna = QVBoxLayout()
        columna.setSpacing(8)
        self.titulo_estado = etiqueta("", "estado_titulo")
        self.texto_estado = etiqueta("", "sub")
        columna.addStretch()
        columna.addWidget(self.titulo_estado)
        columna.addWidget(self.texto_estado)
        botones = QHBoxLayout()
        botones.setContentsMargins(0, 8, 0, 0)
        botones.setSpacing(10)
        self.revisar = boton(f"🔎  {t('Revisar ahora')}", "principal")
        self.revisar.clicked.connect(lambda: self.revisar_ahora())
        self.bloqueo = boton("")
        self.bloqueo.clicked.connect(self._alternar_bloqueo)
        botones.addWidget(self.revisar)
        botones.addWidget(self.bloqueo)
        botones.addStretch()
        columna.addLayout(botones)
        self.hora = etiqueta("", "meta")
        columna.addWidget(self.hora)
        columna.addStretch()
        fila.addLayout(columna, 1)
        resumen = QVBoxLayout()  # lo que frenó en el último día: que se vea que trabaja
        resumen.setSpacing(4)
        self.cuenta = etiqueta("0", "cuenta")
        self.cuenta.setAlignment(Qt.AlignRight)
        resumen.addWidget(self.cuenta)
        texto_cuenta = etiqueta(t("eventos en las últimas 24 horas"), "meta")
        texto_cuenta.setAlignment(Qt.AlignRight)
        resumen.addWidget(texto_cuenta)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.addStretch()
        self.chips = {}
        for gravedad in GRAVEDAD:
            self.chips[gravedad] = _chip(gravedad)
            chips.addWidget(self.chips[gravedad])
        resumen.addLayout(chips)
        resumen.addStretch()
        fila.addLayout(resumen)
        portada_lay.addLayout(fila)
        lay.addWidget(portada)

        comprobaciones, comp_lay = tarjeta()
        comp_lay.addWidget(etiqueta(t("Comprobaciones"), "seccion"))
        self.lista_resultados = QVBoxLayout()
        self.lista_resultados.setSpacing(10)
        comp_lay.addLayout(self.lista_resultados)
        lay.addWidget(comprobaciones)

        historial, hist_lay = tarjeta()
        cabecera = QHBoxLayout()
        cabecera.addWidget(etiqueta(t("Historial"), "seccion"), 1)
        self.borrar = boton(f"🗑  {t('Borrar historial')}")
        self.borrar.clicked.connect(self._borrar)
        cabecera.addWidget(self.borrar)
        hist_lay.addLayout(cabecera)
        self.lista_eventos = QVBoxLayout()
        self.lista_eventos.setSpacing(0)
        hist_lay.addLayout(self.lista_eventos)
        lay.addWidget(historial)

        # Lo honesto: qué protege y qué no (Ráfaga Guardia cuida la app y lo que guarda, no el PC entero)
        nota, nota_lay = tarjeta()
        nota_lay.addWidget(etiqueta(t("Qué protege y qué no"), "seccion"))
        columnas = QHBoxLayout()
        columnas.setSpacing(28)
        for titulo, textos, marca, color in ((t("Protege"), PROTEGE, "circle-check", "#3DDC97"),
                                             (t("No protege"), NO_PROTEGE, "circle-minus", "#A9A9B6")):
            columna_lay = QVBoxLayout()
            columna_lay.setSpacing(10)
            cabeza = etiqueta(titulo)
            cabeza.setStyleSheet(f"color: {color}; font-weight: 700;")
            columna_lay.addWidget(cabeza)
            for texto in textos:
                linea = QHBoxLayout()
                linea.setSpacing(8)
                linea.addWidget(_icono_fijo(marca, color, 18), 0, Qt.AlignTop)
                linea.addWidget(etiqueta(texto), 1)
                columna_lay.addLayout(linea)
            columna_lay.addStretch()
            columnas.addLayout(columna_lay, 1)
        nota_lay.addLayout(columnas)
        nota_lay.addWidget(etiqueta(t("Las reglas deciden y bloquean; la IA solo explica y nunca hace nada por su "
                                      "cuenta. Todo se apunta en tu PC, en datos/guardia.json."), "meta"))
        lay.addWidget(nota)
        lay.addStretch()

        self.resultados, self.estado, self.tarea, self.hora_revision, self._repetir = [], None, None, "", False
        self._eventos, self._bloqueo, self._vistos, self._firma, self._bandeja = [], None, None, None, None
        self._explicaciones, self._hilos = {}, {}  # id del evento → texto de la IA y su Tarea
        fuente = QFont("Segoe UI")  # la de las pastillas (_estilo_chip): todas tan anchas como la más larga del idioma
        fuente.setPixelSize(13)
        fuente.setBold(True)
        self.ancho_chip = max(74, *(QFontMetrics(fuente).horizontalAdvance(n) + 26 for _, n in GRAVEDAD.values()))
        self.reloj = QTimer(self, interval=1500)
        self.reloj.timeout.connect(self._comprobar_cambios)
        self.reloj.start()
        self._comprobar_cambios()
        self.revisar_ahora(inicio=True)  # una revisión al abrir la app, en segundo plano

    # ---------- Revisar ----------

    def revisar_ahora(self, inicio: bool = False):
        """La revisión completa en segundo plano (nunca congela la ventana; si falla, se dice y la app sigue). Pulsada
        por la persona, además da por vistos los eventos de hasta ahora."""
        if not inicio:
            guardia.marcar_visto()
        if self.tarea and self.tarea.isRunning():
            self._repetir = True  # la que va ya no ve lo de ahora (p. ej. el bloqueo): otra al terminar
            return
        self.revisar.setEnabled(False)
        self.hora.setText(t("Revisando…"))
        self.tarea = Tarea(lambda aviso: {"resultados": guardia.revisar()})
        self.tarea.listo.connect(self._revisado)
        self.tarea.fallo.connect(lambda e: self._revisado({"resultados": [
            {"estado": "aviso", "texto": t("No se pudo revisar: {error}", error=e)}]}))
        self.tarea.finished.connect(self._terminada)
        self.tarea.start()

    def _terminada(self):
        self.revisar.setEnabled(True)
        if self._repetir:
            self._repetir = False
            self.tarea.wait()  # «finished» llega justo antes de que el hilo acabe del todo
            self.revisar_ahora(inicio=True)

    def _revisado(self, r):
        self.resultados = r.get("resultados") or []
        self.hora_revision = time.strftime("%H:%M")
        self._pintar_resultados()
        self._firma = None  # la revisión pudo apuntar un evento (el código cambió): se recarga ya
        self._comprobar_cambios()

    def _pintar_resultados(self):
        _vaciar(self.lista_resultados)
        for resultado in self.resultados:
            fila = QWidget()
            fila_lay = QHBoxLayout(fila)
            fila_lay.setContentsMargins(0, 0, 0, 0)
            fila_lay.setSpacing(10)
            fila_lay.addWidget(_icono_fijo(*MARCAS.get(resultado.get("estado"), MARCAS["aviso"])), 0, Qt.AlignTop)
            fila_lay.addWidget(etiqueta(str(resultado.get("texto", ""))), 1)
            self.lista_resultados.addWidget(fila)

    # ---------- Vigilar el historial ----------

    def _comprobar_cambios(self):
        """Cada 1,5 s: si guardia.json cambió (también si lo cambió el MCP, en otro proceso), se recarga. Basta mirar
        su fecha y tamaño: el reemplazo atómico los cambia. ponytail: un reloj y no QFileSystemWatcher, que pierde el
        archivo en cada reemplazo atómico."""
        try:
            datos = guardia.ARCHIVO.stat()
            firma = (datos.st_mtime_ns, datos.st_size)
            open(guardia.ARCHIVO, "rb").close()  # otro programa que lo abre en exclusiva no le cambia fecha ni tamaño
        except FileNotFoundError:
            firma = ()
        except OSError:
            firma = ("ilegible",)  # guardia.bloqueado() falla cerrado: que la página lo enseñe
        if firma == self._firma:
            return
        self._firma = firma
        try:
            self._recargar()
        except Exception:  # un historial raro nunca tumba la app: se ve lo que se pueda
            traceback.print_exc()

    def _recargar(self):
        eventos, bloqueo = guardia.eventos(), guardia.bloqueado()
        if bloqueo and bloqueo.get("ilegible") and self._bloqueo:
            bloqueo = self._bloqueo  # mientras no se puede leer, se recuerda el bloqueo de verdad que había
        # El último bloqueo o desbloqueo del historial (va del más nuevo al más viejo): con la app abierta dos veces,
        # la otra copia desbloqueó desde su página (guardia.desbloquear lo apunta) y no es un ataque
        ultimo = next((e["tipo"] for e in eventos if e["tipo"] in ("bloqueo", "desbloqueo")), None)
        if self._bloqueo and not self._bloqueo.get("ilegible") and not bloqueo and ultimo != "desbloqueo":
            # Solo se desbloquea en esta página: quitarlo editando o rompiendo guardia.json no vale, se vuelve a poner
            # y se avisa
            guardia.registrar("bloqueo_quitado", "alta", t("Alguien quitó el bloqueo desde fuera de esta página: se "
                                                           "volvió a poner. Solo se desbloquea aquí."), "app")
            guardia.bloquear(self._bloqueo.get("motivo") or t("sin motivo"))
            eventos, bloqueo = guardia.eventos(), guardia.bloqueado()
        self._bloqueo = bloqueo
        if self._vistos is None:  # al abrir la app no se notifica lo de antes: el escudo ya lo enseña
            self._vistos = {e["id"] for e in eventos}
        for evento in eventos[::-1]:
            if evento["id"] not in self._vistos:
                self._vistos.add(evento["id"])
                if evento["gravedad"] == "alta":
                    self._notificar(evento)
        self._eventos = eventos
        # Se bloqueó o desbloqueó: la línea del bloqueo (la última de revisar) al día, sin revisar todo otra vez
        # (otra revisión volvería a apuntar y a notificar la misma integridad «alta»)
        if self.resultados and self.resultados[-1].get("bloqueo"):
            linea = guardia.linea_bloqueo(bloqueo)
            if linea != self.resultados[-1]:
                self.resultados[-1] = linea
                self._pintar_resultados()
        self._pintar()

    def _notificar(self, evento):
        """Una notificación de Windows con el icono de la app. La bandeja se crea al primer aviso, y solo si existe."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self._bandeja is None:
            self._bandeja = QSystemTrayIcon(QApplication.windowIcon(), self)
            self._bandeja.setToolTip("Ráfaga Studio")
            self._bandeja.messageClicked.connect(self.abrir.emit)
            self._bandeja.activated.connect(lambda _: self.abrir.emit())
            self._bandeja.show()
        self._bandeja.showMessage(t("Ráfaga Guardia"), evento["detalle"], QApplication.windowIcon(), 10_000)

    # ---------- Pintar ----------

    def _pintar(self):
        estado = guardia.estado(self.resultados)
        color = COLORES[estado]
        self.escudo.poner(estado)
        self.titulo_estado.setText(BLOQUEADO if self._bloqueo else TITULOS[estado])
        self.titulo_estado.setStyleSheet(f"color: {color};")
        self.texto_estado.setText(t("Bloqueado: {motivo}", motivo=self._bloqueo["motivo"]) + "\n" + t(
            "No empieza ningún video, imagen, canción ni voz de pago, ni se publica, ni se guarda en la memoria, ni "
            "funciona el MCP hasta que lo desbloquees aquí.") if self._bloqueo else DESCRIPCIONES[estado])
        poner(self.bloqueo, f"🔓  {t('Desbloquear')}" if self._bloqueo else f"🔒  {t('Bloquear ahora')}")
        if self.hora_revision and not (self.tarea and self.tarea.isRunning()):
            self.hora.setText(t("Última revisión: {hora}", hora=self.hora_revision))
        hace_un_dia = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400))
        recientes = [e for e in self._eventos if e["fecha"] >= hace_un_dia]
        self.cuenta.setText(str(sum(e["veces"] for e in recientes)))
        for gravedad, chip in self.chips.items():
            n = sum(e["veces"] for e in recientes if e["gravedad"] == gravedad)
            chip.setText(f"{GRAVEDAD[gravedad][1]}  {n}")
            chip.setStyleSheet(_estilo_chip(GRAVEDAD[gravedad][0] if n else "#6E6E7A"))  # sin ninguno, apagada
        self._pintar_eventos()
        if estado != self.estado:
            self.estado = estado
            self.estado_cambiado.emit(estado)

    def _pintar_eventos(self):
        _vaciar(self.lista_eventos)
        self.borrar.setEnabled(bool(self._eventos))
        if not self._eventos:
            vacio = etiqueta(t("Sin eventos. Cuando Ráfaga Guardia frene algo, lo verás aquí."), "sub")
            vacio.setContentsMargins(0, 6, 0, 4)
            self.lista_eventos.addWidget(vacio)
            return
        for evento in self._eventos[:MAX_VISIBLES]:
            self.lista_eventos.addWidget(self._fila(evento))
        if len(self._eventos) > MAX_VISIBLES:
            mas = etiqueta(t("… y {n} evento(s) más antiguos.", n=len(self._eventos) - MAX_VISIBLES), "meta")
            mas.setContentsMargins(0, 8, 0, 0)
            self.lista_eventos.addWidget(mas)

    def _fila(self, evento) -> QFrame:
        fila = QFrame()
        fila.setObjectName("evento")
        lay = QVBoxLayout(fila)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(8)
        arriba = QHBoxLayout()
        arriba.setSpacing(14)
        chip = _chip(evento["gravedad"])
        chip.setFixedWidth(self.ancho_chip)  # todas igual de anchas: los textos de las filas quedan alineados
        arriba.addWidget(chip, 0, Qt.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(etiqueta(evento["detalle"]))  # texto plano: guardia.json podría traer cualquier cosa
        veces = f"  ·  ×{evento['veces']}" if evento["veces"] > 1 else ""
        textos.addWidget(etiqueta(f"{evento['fecha'][:16]}  ·  {ORIGENES.get(evento['origen'], evento['origen'])}"
                                  f"{veces}", "meta"))
        arriba.addLayout(textos, 1)
        explicar = boton(f"✨  {t('Explicar con IA')}")
        hilo = self._hilos.get(evento["id"])
        explicar.setEnabled(not (hilo and hilo.isRunning()))
        explicar.clicked.connect(lambda: self._explicar(evento))
        arriba.addWidget(explicar, 0, Qt.AlignTop)
        lay.addLayout(arriba)
        if evento["id"] in self._explicaciones:
            caja = QHBoxLayout()
            caja.addSpacing(chip.width() + arriba.spacing())  # alineada con el texto del evento
            caja.addWidget(etiqueta(self._explicaciones[evento["id"]], "explicacion"), 1)  # de la IA: solo se lee
            lay.addLayout(caja)
        return fila

    # ---------- Acciones ----------

    def _explicar(self, evento):
        """La IA de texto explica el evento con palabras sencillas. Recibe solo el evento ya limpio; lo que conteste se
        enseña como texto y nada más."""
        self._explicaciones[evento["id"]] = t("Preguntando a la IA…")
        tarea = Tarea(lambda aviso: {"texto": guardia.explicar(evento)})
        tarea.listo.connect(lambda r: self._explicado(evento["id"], r["texto"]))
        tarea.fallo.connect(lambda e: self._explicado(evento["id"], t("No se pudo explicar: {error}", error=e)))
        self._hilos[evento["id"]] = tarea
        tarea.start()
        self._pintar_eventos()

    def _explicado(self, id_, texto):
        self._explicaciones[id_] = texto
        self._hilos[id_].wait(1000)  # ya acabó (emite al final de run): así el botón se reactiva al repintar
        self._pintar_eventos()

    def _alternar_bloqueo(self):
        if guardia.bloqueado():
            pregunta = QMessageBox.question(
                self, t("Desbloquear"), t("¿Desbloquear Ráfaga Studio? Vuelven a funcionar el video, las "
                                          "imágenes, la música y la voz de pago, publicar, la memoria y el MCP. Si el "
                                          "código de la app sigue cambiado, se bloqueará otra vez enseguida."),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if pregunta != QMessageBox.Yes:
                return
            self._bloqueo = None  # lo quita esta página, la única que puede: no es un desbloqueo de fuera
            guardia.desbloquear()
            self.revisar_ahora(inicio=True)  # si el código sigue cambiado, se vuelve a bloquear enseguida
        else:
            guardia.bloquear(t("lo bloqueaste tú desde Ráfaga Guardia"))
        self._firma = None
        self._comprobar_cambios()

    def _borrar(self):
        if QMessageBox.question(self, t("Borrar historial"), t("¿Borrar el historial de Ráfaga Guardia? Si el estudio "
                                                               "está bloqueado, sigue bloqueado."),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        guardia.borrar_historial()
        self._explicaciones.clear()
        self._firma = None
        self._comprobar_cambios()

    def cerrar(self):
        """Al cerrar la app: un hilo vivo al salir la tumbaría. La revisión es rápida; una explicación de la IA puede
        tardar, pero tiene su propio plazo."""
        self.reloj.stop()
        for hilo in (self.tarea, *self._hilos.values()):
            if hilo:
                hilo.blockSignals(True)
                hilo.wait(5_000)  # ponytail: una IA que no contesta en 5 s se abandona; el cierre sigue
