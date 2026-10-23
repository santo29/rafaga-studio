"""Estudio de diseño: el modelo (un dict JSON, versión 1), su validación, la carpeta de cada diseño, el dibujo con Qt
y la exportación. Sin ventanas: lo usan el editor y el MCP.

Un diseño puede venir de la IA o de un archivo ajeno: todo pasa por validar(), que da una copia limpia o un ValueError
en español. Las imágenes son solo nombres simples dentro de <carpeta del diseño>/imagenes/.

Para el editor visual: escena() pone primero el fondo (items con data(0) None: no son capas) y luego un ItemCapa por
capa, en el orden de diseno["capas"] (el último, encima).
- La capa de un item: item.data(0) es su id → next(c for c in diseno["capas"] if c["id"] == item.data(0)).
- Geometría: pos() = (x, y), la caja local es QRectF(0, 0, ancho, alto) y gira alrededor de su centro
  (transformOriginPoint). Arrastrar el item solo cambia pos(): al soltar, copia pos() a capa["x"] y capa["y"].
- Cualquier otro cambio (tamaño con las asas, rotación, color, texto…): escríbelo en el dict de la capa, con valores
  válidos (ante la duda, pásalo por validar), y llama a item.aplicar(capa), que lo vuelve a leer todo y repinta.
- El texto es un QGraphicsTextItem hijo (item.texto), siempre con setPlainText; su contorno, otro hijo por debajo.
  La sombra es un efecto de la capa entera (item.graphicsEffect()).
- Para que se puedan mover y elegir: item.setFlags(ItemIsMovable | ItemIsSelectable). Las asas las dibuja el editor.

Formas: "linea" es un trazo horizontal por el centro de la caja, del color de `relleno` y de grosor `grosor_borde`.
El texto que no cabe en su caja se recorta (si se saliera, una sombra lo pintaría entero aparte: GB de memoria).

Topes para que un diseño ajeno no cuelgue el editor ni llene la memoria (los aplica validar()):
- Se RECORTAN sin error (ajustar_capa, que el editor puede llamar antes de validar): cada capa mide como mucho
  FACTOR_CAPA (2) veces el lienzo de ancho y de alto, y el grosor_contorno de un texto, como mucho su tamano ×
  FRACCION_CONTORNO (1/4). Recortar y no fallar: los diseños guardados antes siguen abriéndose.
- Dan ValueError: más de MAX_IMAGENES (12) imágenes contando la del fondo; más de MAX_LETRAS_CONTORNO (2000)
  caracteres en los textos con contorno (contorno y grosor_contorno > 0), sumando todos; y más de MAX_PIXELES_EMOJI
  (16 millones) de emojis: en un texto, cada emoji (con repeticiones) cuenta tamano²; una capa emoji cuenta
  min(ancho × alto, caracteres × min(ancho, alto)²); con una fuente de emojis cuenta TODO el texto (hasta ♡ sale en
  color); y más de MAX_SOMBRAS (12) textos con sombra. Una sombra que al pintarse pasaría de MAX_PIXELES_SOMBRA
  (p. ej. exportando a mucha escala) se omite en ese pintado.
"""
import json
import math
import os
import re
import shutil
import tempfile
import time
import unicodedata
import uuid
from functools import cache, lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QMarginsF, QPointF, QRect, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QImageReader, QLinearGradient,
                           QPageSize, QPainter, QPainterPath, QPdfWriter, QPen, QTextCharFormat, QTextCursor,
                           QTextOption)
from PySide6.QtSvg import QSvgGenerator, QSvgRenderer
from PySide6.QtWidgets import (QApplication, QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsScene,
                               QGraphicsTextItem)

from . import recursos, seguro
from .idioma import t

CARPETA = Path(__file__).resolve().parent.parent / "datos" / "disenos"
TAMANOS = {"post": (1080, 1080, t("Post cuadrado")), "historia": (1080, 1920, t("Historia / Reel")),
           "vertical": (1080, 1350, t("Post vertical 4:5")), "miniatura": (1280, 720, t("Miniatura de YouTube")),
           "portada": (1500, 500, t("Portada / banner")), "flyer": (1240, 1754, t("Flyer A4")),
           "logo": (1000, 1000, t("Logo")), "tarjeta": (1050, 600, t("Tarjeta de presentación"))}
FORMATOS = ("png", "jpg", "pdf", "svg")
MAX_CAPAS = 80
FACTOR_CAPA, FRACCION_CONTORNO = 2, 0.25  # topes: ver el docstring del módulo
MAX_IMAGENES, MAX_LETRAS_CONTORNO, MAX_PIXELES_EMOJI = 12, 2000, 16_000_000
MAX_SOMBRAS, MAX_PIXELES_SOMBRA = 12, 16_000_000  # cada sombra se pinta aparte como imagen (en el PDF, a 300 ppp)
_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
# Nombres que Windows abre como dispositivos aunque lleven extensión (leer «CON.png» se quedaría esperando la consola)
_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
_ALINEACION = {"izquierda": Qt.AlignLeft, "centro": Qt.AlignHCenter, "derecha": Qt.AlignRight}


# ---------- Validación ----------

def color(v) -> str:
    if not isinstance(v, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        raise ValueError(t("color no válido ({v!r:.40}): tiene que ser #RRGGBB", v=v))
    return v.upper()


def nombre_imagen(v) -> str:
    """Solo el nombre de una imagen de la carpeta imagenes/: sin carpetas, «..», rutas absolutas ni de red."""
    if (not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\.[A-Za-z]{3,4}", v)
            or Path(v).suffix.lower() not in seguro.IMAGENES or v.split(".")[0].lower() in _RESERVADOS):
        raise ValueError(t("archivo de imagen no válido ({v!r:.60}): tiene que ser una imagen de la carpeta del diseño",
                           v=v))
    return v


def nombre_fuente(v) -> str:
    # Qt escribe la familia tal cual en el font-family del SVG exportado: unas comillas abrirían un <script>
    if not isinstance(v, str) or not re.fullmatch(r"[\w .-]{1,100}", v):
        raise ValueError(t("nombre de fuente no válido ({v!r:.40})", v=v))
    return v


def _num(v, minimo, maximo):
    # NaN e infinito no pasan la comparación; True es un int para Python, pero aquí no es un número
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not minimo <= v <= maximo:
        raise ValueError(t("tiene que ser un número entre {minimo} y {maximo} (llegó {v!r:.40})", minimo=minimo,
                           maximo=maximo, v=v))
    v = round(float(v), 2)
    return int(v) if v.is_integer() else v


def _texto(maximo):
    def regla(v):
        if not isinstance(v, str) or len(v) > maximo:
            raise ValueError(t("tiene que ser un texto de hasta {maximo} caracteres", maximo=maximo))
        return v
    return regla


def _una(*opciones):
    def regla(v):
        if v not in opciones:
            raise ValueError(t("vale {opciones} (llegó {v!r:.40})", opciones=", ".join(opciones), v=v))
        return v
    return regla


def _si_no(v):
    if not isinstance(v, bool):
        raise ValueError(t("tiene que ser true o false"))
    return v


def _color_o_nada(v):
    return "" if v == "" else color(v)


def _icono(v):
    if not isinstance(v, str) or v not in recursos.iconos():
        raise ValueError(t("no existe el icono {v!r:.40}", v=v))
    return v


_REGLAS = {
    "x": lambda v: _num(v, -20000, 20000), "y": lambda v: _num(v, -20000, 20000),
    "ancho": lambda v: _num(v, 1, 20000), "alto": lambda v: _num(v, 1, 20000),
    "rotacion": lambda v: _num(v, -360, 360), "opacidad": lambda v: _num(v, 0, 1),
    "texto": _texto(2000), "fuente": nombre_fuente, "tamano": lambda v: _num(v, 1, 2000),
    "color": color, "relleno": color, "contorno": _color_o_nada, "borde": _color_o_nada,
    "grosor_contorno": lambda v: _num(v, 0, 200), "grosor_borde": lambda v: _num(v, 0, 200),
    "negrita": _si_no, "cursiva": _si_no, "sombra": _si_no,
    "alineacion": _una(*_ALINEACION), "ajuste": _una("cubrir", "contener"),
    "forma": _una("rectangulo", "elipse", "linea"), "redondeo": lambda v: _num(v, 0, 10000),
    "archivo": nombre_imagen, "nombre": _icono,
}
_COMUNES = {"x": 0, "y": 0, "ancho": 300, "alto": 300, "rotacion": 0, "opacidad": 1}
CAPAS = {  # lo propio de cada tipo de capa, con su valor por defecto
    "texto": {"texto": t("Texto"), "fuente": "Montserrat", "tamano": 64, "color": "#FFFFFF", "negrita": False,
              "cursiva": False, "alineacion": "izquierda", "contorno": "", "grosor_contorno": 0, "sombra": False},
    "imagen": {"archivo": "", "ajuste": "cubrir", "redondeo": 0},
    "forma": {"forma": "rectangulo", "relleno": "#7C5CFF", "borde": "", "grosor_borde": 0, "redondeo": 0},
    "icono": {"nombre": "star", "color": "#FFFFFF"},
    "emoji": {"texto": "⭐"},
}


def _campo(regla, v, que: str):
    try:
        return regla(v)
    except ValueError as e:
        raise ValueError(f"{que}: {e}.") from None


def _capa(c, n: int, ids: set) -> dict:
    tipo = c.get("tipo") if isinstance(c, dict) else None
    if not isinstance(tipo, str) or tipo not in CAPAS:
        raise ValueError(t("Capa {n}: tipo de capa desconocido ({tipo!r:.40}); valen {tipos}.", n=n, tipo=tipo,
                           tipos=", ".join(CAPAS)))
    capa_id = c.get("id")
    if not isinstance(capa_id, str) or not _ID.fullmatch(capa_id) or capa_id in ids:
        capa_id = uuid.uuid4().hex[:8]  # el editor encuentra cada capa por su id: tiene que ser único
    ids.add(capa_id)
    return {"id": capa_id, "tipo": tipo,
            **{k: _campo(_REGLAS[k], c.get(k, defecto), t("Capa {n} ({tipo}), «{campo}»", n=n, tipo=tipo, campo=k))
               for k, defecto in {**_COMUNES, **CAPAS[tipo]}.items()}}


def _fondo(f) -> dict:
    if not isinstance(f, dict):
        raise ValueError(t("El fondo del diseño no es válido."))
    tipo = _campo(_una("color", "degradado", "imagen"), f.get("tipo", "color"), t("El tipo de fondo"))
    colores = f.get("colores", ["#FFFFFF"])
    if not isinstance(colores, list) or not (2 if tipo == "degradado" else 1) <= len(colores) <= 3:
        raise ValueError(t("El fondo necesita de 1 a 3 colores (2 o 3 si es un degradado)."))
    imagen = f.get("imagen", "")
    if tipo == "imagen" or imagen != "":
        imagen = _campo(nombre_imagen, imagen, t("La imagen de fondo"))
    return {"tipo": tipo, "colores": [_campo(color, c, t("Un color del fondo")) for c in colores], "imagen": imagen}


def ajustar_capa(capa: dict, diseno: dict) -> dict:
    """Copia de la capa con el tamaño y el contorno recortados a los topes del lienzo de `diseno` (ver el docstring del
    módulo). No valida nada más ni lanza error: lo que no sea un número lo rechaza luego validar()."""
    c = dict(capa)
    try:
        for lado in ("ancho", "alto"):
            c[lado] = min(c[lado], FACTOR_CAPA * diseno.get(lado, 1080))
        if c["tipo"] == "texto":  # Qt traza el contorno letra a letra: uno enorme tarda minutos en pintarse
            c["grosor_contorno"] = _num(min(c["grosor_contorno"], c["tamano"] * FRACCION_CONTORNO), 0, 200)
    except (KeyError, TypeError, ValueError):
        pass
    return c


@cache
def _emojis() -> frozenset[str]:
    return frozenset(e for e, _ in recursos.emojis())


def _pixeles_emoji(c: dict) -> float:
    # Qt guarda cada emoji en color, al tamaño en que lo pinta, en una caché que no suelta
    if c["tipo"] == "texto":
        emojis = _emojis()
        # Con repeticiones: una bandera o un tono de piel son otro dibujo hecho con caracteres ya contados. Con una
        # fuente de emojis cuenta todo: hasta ♡ o ☚ salen en color
        todo = "emoji" in c["fuente"].lower()
        return sum(todo or ch in emojis or ch >= "\U0001F000" for ch in c["texto"]) * c["tamano"] ** 2
    if c["tipo"] == "emoji":  # todo su texto se encoge hasta caber en la caja
        return min(c["ancho"] * c["alto"], len(c["texto"]) * min(c["ancho"], c["alto"]) ** 2)
    return 0


def validar(diseno: dict) -> dict:
    """Copia limpia y segura del diseño: lo que falta toma su valor por defecto, lo que sobra se quita y lo que no vale
    da ValueError diciendo qué capa y qué campo. Aplica los topes del docstring del módulo."""
    if not isinstance(diseno, dict):
        raise ValueError(t("El diseño no es válido: tiene que ser un objeto JSON."))
    if diseno.get("version", 1) != 1:
        raise ValueError(t("El diseño es de una versión que no conozco ({version!r:.20}).",
                           version=diseno.get("version")))
    capas = diseno.get("capas", [])
    if not isinstance(capas, list) or len(capas) > MAX_CAPAS:
        raise ValueError(t("El diseño tiene que traer una lista de hasta {n} capas.", n=MAX_CAPAS))
    ids = set()
    d = {"version": 1, "nombre": _campo(_texto(120), diseno.get("nombre", t("Mi diseño")), t("El nombre del diseño")),
         "ancho": int(_campo(lambda v: _num(v, 16, 5000), diseno.get("ancho", 1080), t("El ancho del lienzo"))),
         "alto": int(_campo(lambda v: _num(v, 16, 5000), diseno.get("alto", 1080), t("El alto del lienzo"))),
         "fondo": _fondo(diseno.get("fondo", {}))}
    d["capas"] = [ajustar_capa(_capa(c, n, ids), d) for n, c in enumerate(capas, 1)]
    # Cada capa de imagen guarda su foto decodificada (hasta 64 MB): sin tope, unos GB
    if sum(c["tipo"] == "imagen" for c in d["capas"]) + (d["fondo"]["tipo"] == "imagen") > MAX_IMAGENES:
        raise ValueError(t("Un diseño puede tener hasta {n} imágenes, contando la del fondo.", n=MAX_IMAGENES))
    if sum(len(c["texto"]) for c in d["capas"]
           if c["tipo"] == "texto" and c["contorno"] and c["grosor_contorno"]) > MAX_LETRAS_CONTORNO:
        raise ValueError(t("Los textos con contorno pueden sumar hasta {n} letras: quita el contorno de alguno o "
                           "acórtalos.", n=MAX_LETRAS_CONTORNO))
    if sum(map(_pixeles_emoji, d["capas"])) > MAX_PIXELES_EMOJI:
        raise ValueError(t("Demasiados emojis grandes en el diseño: hazlos más pequeños o quita alguno."))
    if sum(c["tipo"] == "texto" and c["sombra"] for c in d["capas"]) > MAX_SOMBRAS:
        raise ValueError(t("Un diseño puede tener hasta {n} textos con sombra: quítasela a alguno.", n=MAX_SOMBRAS))
    return d


# ---------- Carpetas y archivos ----------

def _local(ruta) -> Path:
    # Antes de tocar el disco: abrir una ruta de red ya conecta por SMB y manda la huella de la contraseña
    if seguro.es_ruta_de_red(str(ruta)):
        raise ValueError(t("Tiene que ser una carpeta de este PC, no de la red: {ruta}", ruta=ruta))
    return Path(ruta)


def escribir_json(archivo: Path, datos: dict) -> None:
    """Escritura atómica (temporal + os.replace): un corte de luz no deja el archivo a medias."""
    archivo.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=archivo.parent, prefix=f"{archivo.stem}-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(temporal, archivo)


def nuevo(tamano: str = "post", nombre: str = t("Mi diseño")) -> dict:
    """Diseño vacío del tamaño pedido, con el primer color de la marca de fondo (blanco si no hay marca)."""
    from . import marca  # aquí y no arriba: marca usa los validadores de este módulo
    if not isinstance(tamano, str) or tamano not in TAMANOS:
        raise ValueError(t("Tamaño desconocido ({tamano!r:.20}); valen {tamanos}.", tamano=tamano,
                           tamanos=", ".join(TAMANOS)))
    ancho, alto, _ = TAMANOS[tamano]
    return validar({"nombre": nombre, "ancho": ancho, "alto": alto, "capas": [],
                    "fondo": {"tipo": "color", "colores": marca.cargar()["colores"][:1] or ["#FFFFFF"]}})


def nueva_carpeta(nombre: str) -> Path:
    limpio = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode().lower()
    limpio = re.sub(r"[^a-z0-9]+", "-", limpio).strip("-")[:40] or "diseno"
    base = CARPETA / f"{time.strftime('%Y%m%d-%H%M%S')}-{limpio}"
    CARPETA.mkdir(parents=True, exist_ok=True)
    carpeta, n = base, 1
    while True:
        try:
            carpeta.mkdir()  # atómico: si otro hilo (el MCP en paralelo) la creó a la vez, se prueba otro nombre
            break
        except FileExistsError:
            n += 1
            carpeta = base.with_name(f"{base.name}-{n}")
    (carpeta / "imagenes").mkdir()
    return carpeta


def guardar(diseno: dict, carpeta: Path) -> Path:
    """Valida y escribe diseno.json (atómico) y una miniatura para la lista de diseños."""
    limpio, carpeta = validar(diseno), _local(carpeta)
    archivo = carpeta / "diseno.json"
    escribir_json(archivo, limpio)
    try:
        exportar(limpio, carpeta, carpeta / "miniatura.png", "png", min(1, 360 / max(limpio["ancho"], limpio["alto"])))
    except RuntimeError:
        pass  # sin miniatura la lista enseña solo el nombre: no es motivo para dar el guardado por fallido
    return archivo


def abrir(carpeta: Path) -> dict:
    archivo = _local(carpeta) / "diseno.json"
    try:
        if archivo.stat().st_size > 2 * 1024 ** 2:  # 80 capas de 2000 caracteres caben de sobra
            raise ValueError("demasiado grande")
        datos = json.loads(archivo.read_text(encoding="utf-8-sig"))
    except OSError:
        raise ValueError(t("No encuentro el diseño en {carpeta}.", carpeta=carpeta)) from None
    except (ValueError, RecursionError):  # JSON roto, que no es UTF-8 o anidado sin fin
        raise ValueError(t("El archivo del diseño está dañado, es demasiado grande o no es un diseño.")) from None
    return validar(datos)


def importar_imagen(ruta: str, carpeta: Path) -> str:
    """Copia la imagen (local y de verdad una imagen) a imagenes/ del diseño y devuelve el nombre para la capa."""
    origen = seguro.archivo_medio(ruta, seguro.IMAGENES, t("imagen"))
    destino = _local(carpeta) / "imagenes" / f"imagen-{uuid.uuid4().hex[:8]}{origen.suffix.lower()}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return destino.name


def listar() -> list[dict]:
    """Diseños guardados que se pueden abrir, del último que se tocó al más viejo:
    {"nombre", "carpeta", "miniatura" ("" si no hay)}."""
    disenos = []
    for archivo in CARPETA.glob("*/diseno.json"):
        try:
            nombre, fecha = abrir(archivo.parent)["nombre"], archivo.stat().st_mtime
        except (OSError, ValueError):
            continue  # uno roto no impide ver los demás
        try:  # Qt la abriría como SVG o PDF si lo es, y un SVG puede pedir \\servidor\...: solo una imagen de verdad
            miniatura = str(seguro.archivo_medio(str(archivo.with_name("miniatura.png")), {".png"}, "miniatura"))
        except ValueError:
            miniatura = ""
        disenos.append((fecha, {"nombre": nombre or archivo.parent.name, "carpeta": str(archivo.parent),
                                "miniatura": miniatura}))
    return [d for _, d in sorted(disenos, key=lambda t: t[0], reverse=True)]


# ---------- Dibujo ----------

_app = None  # la QApplication propia del MCP: si nadie la guarda, Python la destruye


def asegurar_qt() -> None:
    """Crea una QApplication sin ventana si no hay ninguna (el MCP) y registra las fuentes de assets/fuentes."""
    global _app
    if QApplication.instance() is None:
        _app = QApplication(["rafaga", "-platform", "offscreen"])
    _registrar_fuentes()


@cache
def _registrar_fuentes() -> None:
    archivos = recursos.archivos_fuentes()
    # Sin ventana (el MCP) Qt no ve las fuentes del sistema y los emojis saldrían como cuadraditos
    if QApplication.platformName() == "offscreen":
        archivos.append(Path(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguiemj.ttf"))
    for archivo in archivos:
        if archivo.is_file():
            QFontDatabase.addApplicationFont(str(archivo))


def _imagen(carpeta: Path, nombre: str) -> QImage | None:
    """La imagen de imagenes/, o None si falta, no es una imagen o es un enlace que apunta fuera de la carpeta."""
    imagenes = Path(carpeta) / "imagenes"
    try:
        ruta = seguro.archivo_medio(str(imagenes / nombre), seguro.IMAGENES, "imagen")
        if ruta.parent != imagenes.resolve():
            return None
        imagen = _leer_imagen(str(ruta), ruta.stat().st_mtime_ns)
    except (ValueError, OSError):
        return None
    return None if imagen.isNull() else imagen


@lru_cache(maxsize=MAX_IMAGENES)
def _leer_imagen(ruta: str, _fecha: int) -> QImage:
    """Validada antes por _imagen; con la fecha en la clave, si el archivo cambia se vuelve a leer. En caché porque el
    editor rehace la escena en cada acción, y así las capas con la misma foto comparten una sola copia."""
    lector = QImageReader(ruta)
    lector.setAutoTransform(True)  # las fotos de móvil guardan el giro en el EXIF: sin esto salen tumbadas
    imagen = lector.read()
    # Una foto de 50 MP haría lento cada repintado del editor; 4096 px dan para exportar al doble sin perder nada
    if max(imagen.width(), imagen.height()) > 4096:
        imagen = imagen.scaled(4096, 4096, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return imagen


class _Sombra(QGraphicsDropShadowEffect):
    """Qt pone el desenfoque y el desplazamiento en píxeles de pantalla: se escalan con el zoom para que la sombra
    mida lo mismo en el lienzo que en el PNG o el PDF."""

    def __init__(self, tamano: float):
        super().__init__()
        self.tamano = tamano
        self.setColor(QColor(0, 0, 0, 150))

    def draw(self, p: QPainter) -> None:
        t = p.worldTransform()
        z = math.hypot(t.m11(), t.m12())  # la escala, aunque la capa esté girada
        self.setBlurRadius(self.tamano / 6 * z)  # con el mismo valor, Qt no repinta: no hay bucle
        self.setOffset(0, self.tamano / 20 * z)
        r = self.sourceBoundingRect(Qt.DeviceCoordinates)
        if r.width() * r.height() > MAX_PIXELES_SOMBRA:  # a mucha escala serían GB: ese pintado va sin sombra
            return self.drawSource(p)
        super().draw(p)


class ItemCapa(QGraphicsItem):
    """Una capa en la escena. Cómo la usa el editor: ver el docstring del módulo."""

    def __init__(self, capa: dict, carpeta: Path):
        super().__init__()
        self.carpeta, self.texto = Path(carpeta), None
        self._archivo = self._icono = self._imagen = self._svg = self._contorno = None
        # El texto no sale de su caja: la sombra pinta la capa entera aparte, y un texto desbordado serían GB
        self.setFlag(QGraphicsItem.ItemClipsChildrenToShape)
        self.aplicar(capa)

    def aplicar(self, capa: dict) -> None:
        """Vuelve a leer la capa entera (geometría y contenido) y repinta."""
        self.prepareGeometryChange()
        self._capa = c = dict(capa)
        self.setData(0, c["id"])
        self.setPos(c["x"], c["y"])
        self.setTransformOriginPoint(c["ancho"] / 2, c["alto"] / 2)
        self.setRotation(c["rotacion"])
        self.setOpacity(c["opacidad"])
        if c["tipo"] == "imagen" and c["archivo"] != self._archivo:
            self._archivo, self._imagen = c["archivo"], _imagen(self.carpeta, c["archivo"])
        elif c["tipo"] == "icono" and (c["nombre"], c["color"]) != self._icono:
            self._icono, self._svg = (c["nombre"], c["color"]), QSvgRenderer(
                QByteArray(recursos.svg_icono(c["nombre"], c["color"])))
            self._svg.setAspectRatioMode(Qt.KeepAspectRatio)
        elif c["tipo"] == "texto":
            self._poner_texto(c)
        self.update()

    def _poner_texto(self, c: dict) -> None:
        if self.texto is None:
            # El contorno va en una copia del texto por debajo, con el trazo al doble: las fuentes variables tienen
            # contornos que se solapan y, trazados encima, se verían rayas dentro de las letras.
            self._contorno, self.texto = QGraphicsTextItem(self), QGraphicsTextItem(self)
        fuente = QFont(c["fuente"])
        fuente.setPixelSize(max(1, round(c["tamano"])))
        fuente.setBold(c["negrita"])
        fuente.setItalic(c["cursiva"])
        opcion = QTextOption(_ALINEACION[c["alineacion"]])
        opcion.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        # Qt recorta el texto a su caja: el margen deja sitio al contorno y a las letras que sobresalen (cursivas)
        m = c["tamano"] / 4 + 2 * c["grosor_contorno"]
        for t in (self._contorno, self.texto):
            t.document().setDocumentMargin(m)
            t.setFont(fuente)
            t.document().setDefaultTextOption(opcion)
            t.setPlainText(c["texto"])  # nunca setHtml: el texto viene de la IA o de un archivo ajeno
            t.setTextWidth(c["ancho"] + 2 * m)
            alto = t.boundingRect().height() - 2 * m
            t.setPos(-m, max(0.0, (c["alto"] - alto) / 2) - m)  # centrado en la caja
        self.texto.setDefaultTextColor(QColor(c["color"]))
        self._contorno.setVisible(bool(c["contorno"] and c["grosor_contorno"]))
        if self._contorno.isVisible():
            self._contorno.setDefaultTextColor(QColor(c["contorno"]))
            formato = QTextCharFormat()
            formato.setTextOutline(QPen(QColor(c["contorno"]), 2 * c["grosor_contorno"], Qt.SolidLine, Qt.RoundCap,
                                        Qt.RoundJoin))
            cursor = QTextCursor(self._contorno.document())
            cursor.select(QTextCursor.Document)
            cursor.mergeCharFormat(formato)
        # En la capa entera: la sombra la hacen el texto y su contorno juntos
        self.setGraphicsEffect(_Sombra(c["tamano"]) if c["sombra"] else None)

    def boundingRect(self) -> QRectF:
        c = self._capa
        if c["tipo"] == "texto":  # el mismo margen que el del texto: no recorta el contorno ni las cursivas
            m = c["tamano"] / 4 + 2 * c["grosor_contorno"]
        else:
            m = c.get("grosor_borde", 0) / 2  # el trazo de una línea sobresale de la caja
        return QRectF(-m, -m, c["ancho"] + 2 * m, c["alto"] + 2 * m)

    def paint(self, p: QPainter, opcion=None, widget=None) -> None:
        c, caja = self._capa, QRectF(0, 0, self._capa["ancho"], self._capa["alto"])
        p.save()
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        if c["tipo"] == "forma":
            self._pintar_forma(p, c, caja)
        elif c["tipo"] == "imagen":
            self._pintar_imagen(p, c, caja)
        elif c["tipo"] == "icono":
            self._svg.render(p, caja)
        elif c["tipo"] == "emoji":
            fuente = QFont()
            fuente.setFamilies(recursos.FUENTE_EMOJI)
            fuente.setPixelSize(100)
            medida = QFontMetricsF(fuente).size(0, c["texto"])
            ajuste = min(caja.width() / max(medida.width(), 1), caja.height() / max(medida.height(), 1))
            fuente.setPixelSize(max(1, int(100 * ajuste)))
            p.setFont(fuente)
            p.drawText(caja, Qt.AlignCenter, c["texto"])
        p.restore()

    @staticmethod
    def _pintar_forma(p: QPainter, c: dict, caja: QRectF) -> None:
        grosor = c["grosor_borde"]
        if c["forma"] == "linea":
            p.setPen(QPen(QColor(c["relleno"]), max(1, grosor)))
            p.drawLine(QPointF(0, caja.height() / 2), QPointF(caja.width(), caja.height() / 2))
            return
        p.setPen(QPen(QColor(c["borde"]), grosor) if c["borde"] and grosor else Qt.NoPen)
        p.setBrush(QColor(c["relleno"]))
        caja = caja.adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2)  # el borde va por dentro de la caja
        if c["forma"] == "elipse":
            p.drawEllipse(caja)
        else:
            r = min(c["redondeo"], caja.width() / 2, caja.height() / 2)
            p.drawRoundedRect(caja, r, r)

    def _pintar_imagen(self, p: QPainter, c: dict, caja: QRectF) -> None:
        imagen = self._imagen
        if imagen is None:  # falta el archivo: se ve el hueco en vez de romper el diseño entero
            p.fillRect(caja, QColor(128, 128, 128, 90))
            return
        destino, origen = QRectF(caja), QRectF(imagen.rect())
        proporcion = (imagen.width() / imagen.height()) / (caja.width() / caja.height())
        if c["ajuste"] == "cubrir":  # llena la caja y recorta lo que sobra, centrado
            if proporcion > 1:
                origen.setWidth(origen.width() / proporcion)
            else:
                origen.setHeight(origen.height() * proporcion)
            origen.moveCenter(QRectF(imagen.rect()).center())
        else:  # contener: la imagen entera, centrada en la caja
            if proporcion > 1:
                destino.setHeight(destino.height() / proporcion)
            else:
                destino.setWidth(destino.width() * proporcion)
            destino.moveCenter(caja.center())
        r = min(c["redondeo"], destino.width() / 2, destino.height() / 2)
        camino = QPainterPath()
        camino.addRoundedRect(destino, r, r)
        p.setClipPath(camino, Qt.IntersectClip)
        p.drawImage(destino, imagen, origen)


def escena(diseno: dict, carpeta: Path) -> QGraphicsScene:
    """La escena del diseño (validado aquí): el fondo y un ItemCapa por capa. La usan el editor y exportar()."""
    asegurar_qt()
    d = validar(diseno)
    s = QGraphicsScene(0, 0, d["ancho"], d["alto"])
    fondo = d["fondo"]
    brocha = QColor(fondo["colores"][0])
    if fondo["tipo"] == "degradado":
        brocha = QLinearGradient(0, 0, 0, d["alto"])
        for i, c in enumerate(fondo["colores"]):
            brocha.setColorAt(i / (len(fondo["colores"]) - 1), QColor(c))
    s.addRect(s.sceneRect(), Qt.NoPen, brocha)
    if fondo["tipo"] == "imagen":  # encima del color, que queda de respaldo si la imagen falta
        s.addItem(ItemCapa({"id": None, "tipo": "imagen", "x": 0, "y": 0, "ancho": d["ancho"], "alto": d["alto"],
                            "rotacion": 0, "opacidad": 1, "archivo": fondo["imagen"], "ajuste": "cubrir",
                            "redondeo": 0}, carpeta))
    for capa in d["capas"]:
        s.addItem(ItemCapa(capa, carpeta))
    return s


def _pintar(s: QGraphicsScene, dispositivo) -> None:
    p = QPainter(dispositivo)
    if not p.isActive():
        raise RuntimeError(t("No se pudo escribir el archivo exportado (¿carpeta sin permiso o archivo abierto?)."))
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    s.render(p, QRectF(0, 0, dispositivo.width(), dispositivo.height()), s.sceneRect(), Qt.IgnoreAspectRatio)
    p.end()


def exportar(diseno: dict, carpeta: Path, destino: Path, formato: str = "png", escala: float = 1.0) -> Path:
    """Dibuja el diseño con la misma escena que el editor (lo que ves es lo que sale). PNG y JPG salen de
    ancho×escala por alto×escala píxeles; PDF y SVG, en vectores (la escala no cuenta)."""
    if formato not in FORMATOS:
        raise ValueError(t("Formato no admitido ({formato!r:.20}); valen {formatos}.", formato=formato,
                           formatos=", ".join(FORMATOS)))
    escala = _campo(lambda v: _num(v, 0.05, 4), escala, t("La escala"))
    destino = _local(destino)
    if destino.suffix.lower() not in {f".{formato}", ".jpeg" if formato == "jpg" else f".{formato}"}:
        destino = destino.with_name(f"{destino.name}.{formato}")  # se añade: «Oferta 3.99» no pierde el «.99»
    s = escena(diseno, carpeta)
    ancho, alto = max(1, round(s.width() * escala)), max(1, round(s.height() * escala))
    if ancho * alto > 40_000_000:
        raise ValueError(t("La imagen saldría demasiado grande: baja la escala."))
    destino.parent.mkdir(parents=True, exist_ok=True)
    if formato in ("png", "jpg"):
        imagen = QImage(ancho, alto, QImage.Format_ARGB32_Premultiplied)
        imagen.fill(Qt.white if formato == "jpg" else Qt.transparent)
        _pintar(s, imagen)
        if not imagen.save(str(destino), formato.upper(), 92 if formato == "jpg" else -1):
            raise RuntimeError(t("No se pudo guardar la imagen en {destino}.", destino=destino))
    elif formato == "pdf":
        pdf = QPdfWriter(str(destino))
        # La página va a 150 ppp (el flyer, 1240×1754, sale en A4 exacto) pero se dibuja a 300: lo que Qt pasa a
        # imagen (los textos con sombra) no sale pixelado al imprimir
        pdf.setResolution(300)
        pdf.setPageSize(QPageSize(QSizeF(s.width() / 150, s.height() / 150), QPageSize.Inch, "",
                                  QPageSize.ExactMatch))
        pdf.setPageMargins(QMarginsF(0, 0, 0, 0))
        _pintar(s, pdf)
    else:
        svg = QSvgGenerator(QSvgGenerator.SvgVersion.Svg11)  # el Tiny 1.2 de por defecto no lleva clip-path (esquinas)
        svg.setResolution(96)  # la de los navegadores: un diseño de 1080 px mide 1080 px, no 1440
        svg.setFileName(str(destino))
        svg.setSize(QSize(int(s.width()), int(s.height())))
        svg.setViewBox(QRect(0, 0, int(s.width()), int(s.height())))
        _pintar(s, svg)
    return destino
