"""Línea de tiempo del editor de video, como la de CapCut: un QWidget que se pinta solo, con la regla de segundos, el
cursor y las pistas Video (clips con miniatura y el rombo de su transición), Capas (textos, stickers y tus grabaciones
de cámara, en violeta y con miniatura: se recortan como un audio), Audio (con su forma de onda) y Subtítulos.
Ratón: clic elige; arrastrar mueve (un clip cambia de orden; una capa o un audio, de inicio); arrastrar un borde
recorta; clic o arrastre en la regla o en un hueco mueve el cursor; la rueda o el deslizador hacen zoom. El imán pega
lo que se arrastra a los bordes de lo demás y al cursor.

No cambia el proyecto: al soltar un arrastre emite `cambio` con un proyecto nuevo validado (un solo «deshacer»).
Las miniaturas y las formas de onda las hace motor/render_edicion en un hilo aparte (Hilo): mientras, se ve el color."""
import importlib
import traceback
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSlider, QWidget

from motor import edicion
from motor.idioma import t

REGLA, VIDEO, CAPA, AUDIO, SUBS, HUECO = 26, 58, 26, 38, 24, 6  # alturas en píxeles
IZQ, BORDE, IMAN, UMBRAL = 12, 6, 8, 4  # px: margen, zona para recortar, alcance del imán, lo que hay que mover para arrastrar
COLORES = {"clips": "#2F5D8A", "capas": "#9A5B2E", "audios": "#1F6F5C", "video": "#5B3FA0"}  # video: tu cara
FALTA = "#B23B3B"  # un clip, capa de video o audio cuyo archivo se movió o se borró


def render():
    """motor/render_edicion, o None si aún no está (lo escribe otra parte del equipo) o falla al cargar: la interfaz
    sigue funcionando sin miniaturas ni vista previa. import_module mira antes sys.modules (las pruebas lo cambian)."""
    try:
        return importlib.import_module("motor.render_edicion")
    except Exception:  # también un archivo a medio escribir (SyntaxError…)
        return None


def reloj(segundos: float) -> str:
    return f"{int(segundos // 60)}:{segundos % 60:04.1f}"


def nombre(clave: str, e: dict) -> str:
    """Nombre corto de un clip, una capa o un audio, en texto plano."""
    if clave in ("clips", "audios") or _es_video(clave, e):
        archivo = Path(e["archivo"]).name
        texto = t("Falta: {archivo}", archivo=archivo) if e.get("falta") else \
            f"🎥 {archivo}" if _es_video(clave, e) else archivo
    else:
        texto = {"texto": t("Texto · {contenido}", contenido=e.get("texto", "")),
                 "icono": t("Sticker · {nombre}", nombre=e.get("nombre", "")),
                 "emoji": e.get("texto", ""), "imagen": t("Imagen")}.get(e["tipo"], "")
    return " ".join(texto.split())[:60]


def _es_video(clave: str, e: dict) -> bool:
    """Una capa de video (tu cara): se recorta como un audio (cambia su tramo del archivo) y lleva miniatura."""
    return clave == "capas" and e["tipo"] == "video"


def _carriles(tramos: list[tuple[float, float]]) -> tuple[list[int], int]:
    """La fila de cada tramo para que no se pisen (la primera donde cabe) y cuántas filas hacen falta."""
    finales, filas = [], []
    for inicio, fin in tramos:
        i = next((k for k, f in enumerate(finales) if f <= inicio + 1e-6), len(finales))
        if i == len(finales):
            finales.append(fin)
        else:
            finales[i] = fin
        filas.append(i)
    return filas, len(finales)


class Hilo(QObject):
    """Un hilo aparte para lo lento (ffmpeg): hace los pedidos de uno en uno (el PC del usuario tiene 2 núcleos) y
    entrega el resultado con `hecho` en el hilo de la ventana."""
    hecho = Signal(object, object)  # clave del pedido, resultado (None si falló)

    def __init__(self):
        super().__init__()
        self._pool = ThreadPoolExecutor(1)

    def pedir(self, clave, funcion, *args):
        def trabajo():
            try:
                resultado = funcion(*args)
            except Exception:  # una miniatura que falla no es motivo para molestar: se ve el color
                traceback.print_exc()
                resultado = None
            try:
                self.hecho.emit(clave, resultado)
            except RuntimeError:  # la ventana ya se cerró
                pass
        self._pool.submit(trabajo)


class LineaTiempo(QWidget):
    elegido = Signal(str)          # id del clip, capa o audio elegido ("" = ninguno)
    cursor_movido = Signal(float)  # segundos, al hacer clic o arrastrar en la regla o en un hueco
    cambio = Signal(object)        # proyecto nuevo (validado) al soltar un arrastre
    aviso = Signal(str)            # un arrastre que no se pudo aplicar

    def __init__(self):
        super().__init__()
        self.proyecto, self.carpeta, self.cursor, self.seleccion = edicion.nuevo(), None, 0.0, ""
        self.escala = 40.0  # píxeles por segundo
        self._arrastre, self._imagenes = None, {}
        self.hilo = Hilo()
        self.hilo.hecho.connect(self._imagen_lista)
        self.deslizador = QSlider(Qt.Horizontal)
        self.deslizador.setRange(4, 400)
        self.deslizador.setValue(40)
        self.deslizador.setFixedWidth(160)
        self.deslizador.setToolTip(t("Zoom de la línea de tiempo (también con la rueda del ratón)"))
        self.deslizador.valueChanged.connect(self._zoom)
        self.setMouseTracking(True)  # para el puntero de recortar encima de los bordes
        self._medir()

    # ---------- Lo que usa la página ----------

    def poner(self, proyecto: dict, carpeta) -> None:
        self.proyecto, self.carpeta = proyecto, carpeta
        self._medir()
        self.update()

    def poner_cursor(self, t: float) -> None:
        self.cursor = max(0.0, t)
        self.update()

    def x_de(self, t: float) -> float:
        return IZQ + t * self.escala

    def caja(self, id_: str) -> QRectF | None:
        """El rectángulo del clip, la capa o el audio en la línea de tiempo."""
        return next((c for c, _, _, e in self._cajas() if e["id"] == id_), None)

    # ---------- Geometría ----------

    def _medir(self):
        p = self.proyecto
        self._tiempos = edicion.tiempos(p)
        self._fila_capa, capas = _carriles([self._base("capas", 0, c) for c in p["capas"]])
        self._fila_audio, audios = _carriles([self._base("audios", 0, a) for a in p["audios"]])
        self._y_capas = REGLA + HUECO + VIDEO + HUECO
        self._y_audios = self._y_capas + max(capas, 1) * CAPA + HUECO  # una fila vacía también se ve: es la pista
        self._y_subs = self._y_audios + max(audios, 1) * AUDIO + HUECO
        # Ordenadas por inicio para pintar solo las que se ven (bisect). El margen alcanza a la más larga que empezó
        # antes de lo visible, +1 s porque una palabra cortísima se pinta con 2 px
        self._palabras = sorted(p["subtitulos"]["palabras"], key=lambda w: w["inicio"])
        self._inicios = [w["inicio"] for w in self._palabras]
        self._margen = max((w["fin"] - w["inicio"] for w in self._palabras), default=0) + 1
        ancho = self.x_de(edicion.duracion_total(p) + 10)
        self.setMinimumSize(int(ancho), self._y_subs + SUBS + HUECO)

    def _base(self, clave: str, i: int, e: dict) -> tuple[float, float]:
        """(inicio, fin) del elemento en la línea de tiempo, sin contar el arrastre."""
        if clave == "clips":
            return self._tiempos[i]
        if clave == "capas":
            return e["inicio"], e["inicio"] + e["duracion"]
        return e["inicio"], e["inicio"] + e["hasta"] - e["desde"]

    def _cajas(self) -> list[tuple[QRectF, str, int, dict]]:
        """(rectángulo, clave, índice, elemento) de cada clip, capa y audio tal como se pintan (con el arrastre)."""
        a, cajas = self._arrastre, []
        for clave in ("clips", "capas", "audios"):
            for i, e in enumerate(self.proyecto[clave]):
                inicio, fin = self._base(clave, i, e)
                if a and a.get("activo") and a["e"] is e:
                    inicio += a["dt"] if a["modo"] != "der" else 0
                    fin += a["dt"] if a["modo"] != "izq" else 0
                if clave == "clips":
                    y, alto = REGLA + HUECO, VIDEO
                elif clave == "capas":
                    y, alto = self._y_capas + self._fila_capa[i] * CAPA, CAPA - 3
                else:
                    y, alto = self._y_audios + self._fila_audio[i] * AUDIO, AUDIO - 3
                cajas.append((QRectF(self.x_de(inicio), y, max((fin - inicio) * self.escala, 3), alto), clave, i, e))
        return cajas

    def _marcas(self) -> list[tuple[QPointF, int]]:
        """El centro del rombo de cada transición (donde se solapan el clip i y el siguiente) y el índice i."""
        y = REGLA + HUECO + VIDEO / 2
        return [(QPointF(self.x_de((self._tiempos[i + 1][0] + self._tiempos[i][1]) / 2), y), i)
                for i, c in enumerate(self.proyecto["clips"][:-1]) if c["transicion"] != "ninguna"]

    def _en(self, pos: QPointF):
        """(clave, índice, elemento, modo) bajo el ratón; modo «izq»/«der» en un borde, «mover» dentro y «transicion»
        en un rombo. None en un hueco."""
        for centro, i in self._marcas():
            if abs(pos.x() - centro.x()) + abs(pos.y() - centro.y()) <= 9:
                return "clips", i, self.proyecto["clips"][i], "transicion"
        for caja, clave, i, e in reversed(self._cajas()):  # lo de encima primero
            if caja.contains(pos):
                modo = ("izq" if pos.x() - caja.left() <= BORDE else "der" if caja.right() - pos.x() <= BORDE
                        else "mover")
                return clave, i, e, modo
        return None

    # ---------- Imágenes (en el hilo) ----------

    def _imagen(self, clave, modulo, funcion: str, *args) -> QImage | None:
        """La imagen ya hecha o None; la primera vez la pide al hilo."""
        if clave not in self._imagenes and self.carpeta is not None and hasattr(modulo, funcion):
            self._imagenes[clave] = None  # pedida: no se vuelve a pedir (tampoco si falla)
            self.hilo.pedir(clave, getattr(modulo, funcion), *args)
        return self._imagenes.get(clave)

    def _imagen_lista(self, clave, imagen):
        self._imagenes[clave] = imagen if isinstance(imagen, QImage) and not imagen.isNull() else None
        self.update()

    # ---------- Pintar ----------

    def paintEvent(self, evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        letra = QFont(self.font())
        letra.setPixelSize(11)
        p.setFont(letra)
        zona = QRectF(evento.rect())
        p.fillRect(zona, QColor("#101015"))
        for y, alto in ((REGLA + HUECO, VIDEO), (self._y_capas, self._y_audios - HUECO - self._y_capas),
                        (self._y_audios, self._y_subs - HUECO - self._y_audios), (self._y_subs, SUBS)):
            p.fillRect(QRectF(zona.left(), y, zona.width(), alto), QColor("#17171D"))
        self._pintar_regla(p, zona)
        r = render()
        arrastrado = self._arrastre["e"] if self._arrastre and self._arrastre.get("activo") else None
        for caja, clave, _, e in sorted(self._cajas(), key=lambda c: c[3] is arrastrado):  # lo arrastrado, encima
            if caja.intersects(zona):
                self._pintar_elemento(p, zona, caja, clave, e, r)
        p.setPen(QPen(QColor("#FFFFFF"), 1.5))
        p.setBrush(QColor("#7C5CFF"))
        for c, _ in self._marcas():
            p.drawPolygon(QPolygonF([c + QPointF(0, -8), c + QPointF(8, 0), c + QPointF(0, 8), c + QPointF(-8, 0)]))
        self._pintar_subtitulos(p, zona)
        x = self.x_de(self.cursor)
        p.setPen(QPen(QColor("#FF4D8D"), 2))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        p.setBrush(QColor("#FF4D8D"))
        p.drawPolygon(QPolygonF([QPointF(x - 6, 0), QPointF(x + 6, 0), QPointF(x, 9)]))
        p.end()

    def _pintar_regla(self, p, zona):
        paso = next((s for s in (0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600) if s * self.escala >= 70), 900)
        p.setPen(QColor("#6E6E7A"))
        n = max(0, int((zona.left() - IZQ) / self.escala / paso) - 1)
        while (x := self.x_de(n * paso)) <= zona.right() + 60:
            t = n * paso
            p.drawLine(QPointF(x, REGLA - 7), QPointF(x, REGLA))
            p.drawText(QPointF(x + 3, REGLA - 9), reloj(t) if paso < 1 else f"{int(t // 60)}:{round(t % 60):02d}")
            n += 1

    def _pintar_elemento(self, p, zona, caja, clave, e, r):
        p.save()
        p.setClipRect(caja)
        p.fillRect(caja, QColor(FALTA if e.get("falta") else COLORES["video" if _es_video(clave, e) else clave]))
        if e.get("falta"):
            r = None  # el archivo no está: ni miniatura ni onda que sacar
        if r and (clave == "clips" or _es_video(clave, e)):
            mini = self._imagen(("mini", e["archivo"], e["desde"]), r, "miniatura", dict(e), self.carpeta, 72)
            if mini:  # repetida a lo largo del clip, solo en lo que se ve (un clip de 60 min serían miles)
                paso = mini.width() * caja.height() / mini.height()
                x = caja.left() + max(0.0, (zona.left() - caja.left()) // paso * paso)
                while x < min(caja.right(), zona.right()):
                    p.drawImage(QRectF(x, caja.top(), paso, caja.height()), mini)
                    x += paso
        elif r and clave == "audios":
            onda = self._imagen(("onda", e["archivo"]), r, "forma_de_onda", e["archivo"], self.carpeta, 1200, 48)
            if onda:  # la del archivo entero: se pinta solo el tramo que suena
                total = max(e["duracion_archivo"], 0.001)
                x0, x1 = e["desde"] / total * onda.width(), e["hasta"] / total * onda.width()
                p.drawImage(caja.adjusted(0, 14, 0, 0), onda, QRectF(x0, 0, max(x1 - x0, 1), onda.height()))
        p.fillRect(QRectF(caja.left(), caja.top(), caja.width(), 15), QColor(0, 0, 0, 100))
        p.setPen(QColor("#FFFFFF"))
        p.drawText(caja.adjusted(4, 0, -4, 0), Qt.AlignLeft | Qt.AlignTop, QFontMetrics(p.font()).elidedText(
            nombre(clave, e), Qt.ElideRight, max(0, int(caja.width()) - 8)))
        p.restore()
        elegido = e["id"] == self.seleccion
        p.setPen(QPen(QColor("#FFFFFF" if elegido else "#0B0B0F"), 2 if elegido else 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(caja.adjusted(1, 1, -1, -1), 4, 4)
        if elegido:  # las asas para recortar
            p.setBrush(QColor("#FFFFFF"))
            for x in (caja.left() + 2, caja.right() - 5):
                p.drawRoundedRect(QRectF(x, caja.top() + caja.height() / 4, 3, caja.height() / 2), 1, 1)

    def _pintar_subtitulos(self, p, zona):
        s = self.proyecto["subtitulos"]
        fondo, medida = QColor("#4B3B8F" if s["activos"] else "#2C2C36"), QFontMetrics(p.font())
        p.setPen(QColor("#ECECF1"))
        t0, t1 = (zona.left() - IZQ) / self.escala, (zona.right() - IZQ) / self.escala
        # Solo las que se ven: recorrer las 20 000 de un video de 60 min en cada repintado daba tirones al reproducir
        for w in self._palabras[bisect_left(self._inicios, t0 - self._margen):bisect_right(self._inicios, t1)]:
            caja = QRectF(self.x_de(w["inicio"]), self._y_subs, max((w["fin"] - w["inicio"]) * self.escala, 2), SUBS)
            if caja.right() >= zona.left() and caja.left() <= zona.right():
                p.fillRect(caja.adjusted(0, 0, -1, 0), fondo)
                p.drawText(caja.adjusted(2, 0, -2, 0), Qt.AlignVCenter | Qt.AlignLeft,
                           medida.elidedText(w["palabra"], Qt.ElideRight, max(0, int(caja.width()) - 4)))

    # ---------- Ratón ----------

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        pos = ev.position()
        hallado = self._en(pos) if pos.y() > REGLA else None
        if hallado is None:
            if pos.y() > REGLA:
                self._elegir("")
            self._arrastre = {"cursor": True}
            return self._mover_cursor(pos.x())
        clave, i, e, modo = hallado
        self._elegir(e["id"])
        self._arrastre = None if modo == "transicion" else {"clave": clave, "i": i, "e": e, "modo": modo,
                                                             "x0": pos.x(), "dt": 0.0, "activo": False}

    def mouseMoveEvent(self, ev):
        pos, a = ev.position(), self._arrastre
        if a is None:
            hallado = self._en(pos) if pos.y() > REGLA else None
            self.setCursor(Qt.SizeHorCursor if hallado and hallado[3] in ("izq", "der") else Qt.ArrowCursor)
            return
        if a.get("cursor"):
            return self._mover_cursor(pos.x())
        if not a["activo"] and abs(pos.x() - a["x0"]) < UMBRAL:  # un clic con pulso tembloroso no mueve nada
            return
        a["activo"] = True
        a["dt"] = self._ajustar(a, (pos.x() - a["x0"]) / self.escala)
        self.update()

    def mouseReleaseEvent(self, ev):
        a, self._arrastre = self._arrastre, None
        if a and a.get("activo") and a["dt"]:
            try:
                self.cambio.emit(self._soltar(a))
            except ValueError as e:
                self.aviso.emit(str(e))
        self.update()

    def wheelEvent(self, ev):
        self.deslizador.setValue(round(self.escala * (1.25 if ev.angleDelta().y() > 0 else 0.8)))
        ev.accept()

    def _zoom(self, valor):
        self.escala = float(valor)
        self._medir()
        self.update()

    def _elegir(self, id_):
        if id_ != self.seleccion:
            self.seleccion = id_
            self.elegido.emit(id_)
            self.update()

    def _mover_cursor(self, x):
        self.cursor = min(max(0.0, (x - IZQ) / self.escala), edicion.duracion_total(self.proyecto))
        self.cursor_movido.emit(self.cursor)
        self.update()

    def _imanes(self, excepto: dict) -> list[float]:
        """Adónde se pega lo que se arrastra: el cursor, el 0 y los bordes de todo lo demás."""
        puntos = [self.cursor, 0.0]
        for clave in ("clips", "capas", "audios"):
            for i, e in enumerate(self.proyecto[clave]):
                if e is not excepto:
                    puntos += self._base(clave, i, e)
        return puntos

    def _ajustar(self, a: dict, dt: float) -> float:
        """El desplazamiento (s) con el imán y dentro de lo posible: ni antes del 0, ni fuera del archivo, ni más corto
        que el mínimo de un clip."""
        clave, e, modo = a["clave"], a["e"], a["modo"]
        inicio, fin = self._base(clave, a["i"], e)
        if not (clave == "clips" and modo == "mover"):  # un clip que cambia de orden no se pega a nada
            bordes = [inicio] * (modo != "der") + [fin] * (modo != "izq")
            pegar = min((m - b - dt for b in bordes for m in self._imanes(e)), key=abs)
            if abs(pegar) * self.escala <= IMAN:
                dt += pegar
        minimo, v = edicion.MIN_CLIP + 0.01, e.get("velocidad", 1)  # con margen: el redondeo a ms no lo deja corto
        tramo = clave == "audios" or _es_video(clave, e)  # se recorta su trozo del archivo
        if modo == "izq":
            dt = min(dt, fin - inicio - minimo)
            if tramo:
                dt = max(dt, -e["desde"], -e["inicio"])
            elif clave == "capas":
                dt = max(dt, -inicio)
            elif e["tipo"] == "video":
                dt = max(dt, -e["desde"] / v)
        elif modo == "der":
            dt = max(dt, minimo - (fin - inicio))
            if tramo:
                dt = min(dt, e["duracion_archivo"] - e["hasta"])
            elif clave == "clips" and e["tipo"] == "video":
                dt = min(dt, (e["duracion_archivo"] - e["hasta"]) / v)
        elif clave != "clips":
            dt = max(dt, -inicio)
        return dt

    def _soltar(self, a: dict) -> dict:
        """El proyecto nuevo tras el arrastre."""
        p, clave, e, modo, dt = self.proyecto, a["clave"], a["e"], a["modo"], a["dt"]
        if clave == "clips" and modo == "mover":  # va delante de los clips cuyo centro queda a su derecha
            inicio, fin = self._tiempos[a["i"]]
            centro = (inicio + fin) / 2 + dt
            otros = [(x + y) / 2 for k, (x, y) in enumerate(self._tiempos) if k != a["i"]]
            return edicion.mover_clip(p, e["id"], sum(c < centro for c in otros))
        if clave in ("clips", "audios") or _es_video(clave, e):
            v = e.get("velocidad", 1)
            desde = e["desde"] + (dt * v if modo == "izq" else 0)
            hasta = e["hasta"] + (dt * v if modo == "der" else 0)
            if e["tipo"] == "imagen":  # una foto empieza siempre en 0: lo que cambia es lo que dura
                desde, hasta = 0, hasta - desde
            if modo != "mover":
                return edicion.recortar(p, e["id"], desde, hasta)
        cambio = {"inicio": max(0.0, e["inicio"] + dt)} if modo != "der" else {}
        if clave == "capas" and modo != "mover":
            cambio["duracion"] = e["duracion"] + (dt if modo == "der" else -dt)
        return edicion.validar({**p, clave: [{**x, **cambio} if x is e else x for x in p[clave]]})
