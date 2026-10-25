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

Como en Photoshop: cada capa tiene su modo de fusión (`fusion`, de FUSIONES), y una capa imagen, sus AJUSTES (brillo,
contraste y saturación de -100 a 100, y desenfoque, un radio en px del diseño; 0 = sin cambio). El PDF y el SVG no
tienen modos de fusión: hasta la última capa que no es «normal» salen como una imagen, y lo de encima en vectores.

Topes para que un diseño ajeno no cuelgue el editor ni llene la memoria (los aplica validar()):
- Se RECORTAN sin error (ajustar_capa, que el editor puede llamar antes de validar): cada capa mide como mucho
  FACTOR_CAPA (2) veces el lienzo de ancho y de alto, y el grosor_contorno de un texto, como mucho su tamano ×
  FRACCION_CONTORNO (1/4). Recortar y no fallar: los diseños guardados antes siguen abriéndose.
- Dan ValueError: más de MAX_IMAGENES (12) imágenes contando la del fondo; más de MAX_LETRAS_CONTORNO (2000)
  caracteres en los textos con contorno (contorno y grosor_contorno > 0), sumando todos; y más de MAX_PIXELES_EMOJI
  (16 millones) de emojis: en un texto, cada emoji (con repeticiones) cuenta tamano²; una capa emoji cuenta
  min(ancho × alto, caracteres × min(ancho, alto)²); con una fuente de emojis cuenta TODO el texto (hasta ♡ sale en
  color); más de MAX_SOMBRAS (12) textos con sombra, y más de MAX_FUSIONES (12) capas con fusión (como una sombra,
  cada una se pinta aparte como imagen). Una sombra que al pintarse pasaría de MAX_PIXELES_SOMBRA (p. ej. exportando a
  mucha escala) se omite en ese pintado.
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

from PySide6.QtCore import QByteArray, QMarginsF, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QImageReader, QLinearGradient,
                           QPageSize, QPainter, QPainterPath, QPdfWriter, QPen, QTextCharFormat, QTextCursor,
                           QTextOption, QTransform)
from PySide6.QtSvg import QSvgGenerator, QSvgRenderer
from PySide6.QtWidgets import (QApplication, QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsTextItem)

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
MAX_FUSIONES = 12  # cada capa con fusión, también
_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
# Nombres que Windows abre como dispositivos aunque lleven extensión (leer «CON.png» se quedaría esperando la consola)
_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
_ALINEACION = {"izquierda": Qt.AlignLeft, "centro": Qt.AlignHCenter, "derecha": Qt.AlignRight}
FUSIONES = {"normal": QPainter.CompositionMode_SourceOver, "multiplicar": QPainter.CompositionMode_Multiply,
            "trama": QPainter.CompositionMode_Screen, "superponer": QPainter.CompositionMode_Overlay,
            "aclarar": QPainter.CompositionMode_Lighten, "oscurecer": QPainter.CompositionMode_Darken}
AJUSTES = ("brillo", "contraste", "saturacion", "desenfoque")  # los de una capa imagen, en el orden de ajustar_imagen


# ---------- Validación ----------

def color(v) -> str:
    if not isinstance(v, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        raise ValueError(t("color no válido («{v:.40}»): tiene que ser #RRGGBB", v=str(v)))
    return v.upper()


def nombre_imagen(v) -> str:
    """Solo el nombre de una imagen de la carpeta imagenes/: sin carpetas, «..», rutas absolutas ni de red."""
    if (not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\.[A-Za-z]{3,4}", v)
            or Path(v).suffix.lower() not in seguro.IMAGENES or v.split(".")[0].lower() in _RESERVADOS):
        raise ValueError(t("archivo de imagen no válido («{v:.60}»): tiene que ser una imagen de la carpeta del "
                           "diseño", v=str(v)))
    return v


def nombre_fuente(v) -> str:
    # Qt escribe la familia tal cual en el font-family del SVG exportado: unas comillas abrirían un <script>
    if not isinstance(v, str) or not re.fullmatch(r"[\w .-]{1,100}", v):
        raise ValueError(t("nombre de fuente no válido («{v:.40}»)", v=str(v)))
    return v


def _num(v, minimo, maximo):
    # NaN e infinito no pasan la comparación; True es un int para Python, pero aquí no es un número
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not minimo <= v <= maximo:
        raise ValueError(t("tiene que ser un número entre {minimo} y {maximo} (llegó «{v:.40}»)", minimo=minimo,
                           maximo=maximo, v=str(v)))
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
            raise ValueError(t("vale {opciones} (llegó «{v:.40}»)", opciones=", ".join(opciones), v=str(v)))
        return v
    return regla


def _si_no(v):
    if not isinstance(v, bool):
        raise ValueError(t("tiene que ser sí o no"))
    return v


def _color_o_nada(v):
    return "" if v == "" else color(v)


def _icono(v):
    if not isinstance(v, str) or v not in recursos.iconos():
        raise ValueError(t("no existe el icono «{v:.40}»", v=str(v)))
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
    "archivo": nombre_imagen, "nombre": _icono, "fusion": _una(*FUSIONES),
    "brillo": lambda v: _num(v, -100, 100), "contraste": lambda v: _num(v, -100, 100),
    "saturacion": lambda v: _num(v, -100, 100), "desenfoque": lambda v: _num(v, 0, 100),
}
_COMUNES = {"x": 0, "y": 0, "ancho": 300, "alto": 300, "rotacion": 0, "opacidad": 1, "fusion": "normal"}
CAPAS = {  # lo propio de cada tipo de capa, con su valor por defecto
    "texto": {"texto": t("Texto"), "fuente": "Montserrat", "tamano": 64, "color": "#FFFFFF", "negrita": False,
              "cursiva": False, "alineacion": "izquierda", "contorno": "", "grosor_contorno": 0, "sombra": False},
    "imagen": {"archivo": "", "ajuste": "cubrir", "redondeo": 0, **dict.fromkeys(AJUSTES, 0)},
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
    if sum(c["fusion"] != "normal" for c in d["capas"]) > MAX_FUSIONES:
        raise ValueError(t("Un diseño puede tener hasta {n} capas con fusión: pon alguna en «Normal».", n=MAX_FUSIONES))
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


def ruta_imagen(carpeta: Path, nombre: str) -> Path | None:
    """La ruta real de una imagen de imagenes/, o None si falta, no es una imagen o es un enlace que apunta fuera de
    la carpeta (un diseño de otro PC no saca así un archivo privado: ni al lienzo ni a una IA)."""
    imagenes = Path(carpeta) / "imagenes"
    try:
        ruta = seguro.archivo_medio(str(imagenes / nombre), seguro.IMAGENES, "imagen")
        return ruta if ruta.parent == imagenes.resolve() else None
    except (ValueError, OSError):
        return None


def _imagen(carpeta: Path, nombre: str) -> QImage | None:
    """La imagen de imagenes/ ya leída, o None (ver ruta_imagen)."""
    ruta = ruta_imagen(carpeta, nombre)
    if ruta is None:
        return None
    try:
        imagen = _leer_imagen(str(ruta), ruta.stat().st_mtime_ns)
    except OSError:
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


class _Efecto(QGraphicsDropShadowEffect):
    """La sombra de un texto (tamano: el de su letra; 0, sin sombra) y el modo de fusión de la capa: la capa ya pintada
    entera se funde con lo de debajo, así un texto no se funde con su propio contorno. Qt pone el desenfoque y el
    desplazamiento de la sombra en píxeles de pantalla: se escalan con el zoom para que mida lo mismo en el lienzo que
    en el PNG o el PDF."""

    def __init__(self, tamano: float, fusion: str):
        super().__init__()
        self.tamano, self.modo = tamano, FUSIONES[fusion]
        self.setColor(QColor(0, 0, 0, 150))
        self.setBlurRadius(0)
        self.setOffset(0, 0)

    def draw(self, p: QPainter) -> None:
        if self.tamano:
            t = p.worldTransform()
            z = math.hypot(t.m11(), t.m12())  # la escala, aunque la capa esté girada
            self.setBlurRadius(self.tamano / 6 * z)  # con el mismo valor, Qt no repinta: no hay bucle
            self.setOffset(0, self.tamano / 20 * z)
        p.save()  # el modo no se queda puesto para las capas de encima
        p.setCompositionMode(self.modo)
        r = self.sourceBoundingRect(Qt.DeviceCoordinates)
        if r.width() * r.height() > MAX_PIXELES_SOMBRA:  # a mucha escala serían GB: sin sombra y fundida trazo a trazo
            self.drawSource(p)
        elif self.tamano:
            super().draw(p)
        else:
            origen = QPoint()
            imagen = self.sourcePixmap(Qt.DeviceCoordinates, origen)  # PySide6 escribe en `origen` dónde va
            p.setWorldTransform(QTransform())
            p.setOpacity(1)  # la de la capa ya va en la imagen: si no, contaría dos veces
            p.drawPixmap(origen, imagen)
        p.restore()


class ItemCapa(QGraphicsItem):
    """Una capa en la escena. Cómo la usa el editor: ver el docstring del módulo."""

    def __init__(self, capa: dict, carpeta: Path):
        super().__init__()
        self.carpeta, self.texto, self._ajustada = Path(carpeta), None, (None, None)
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
        # En la capa entera: la sombra la hacen el texto y su contorno juntos
        sombra = c["tamano"] if c["tipo"] == "texto" and c["sombra"] else 0
        self.setGraphicsEffect(_Efecto(sombra, c["fusion"]) if sombra or c["fusion"] != "normal" else None)
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
        dibujo = destino
        if any(c[k] for k in AJUSTES):
            ajustada = self._con_ajustes(p, imagen, origen, destino, c)
            if ajustada is None:  # no se ve nada de ella
                return
            imagen, origen, dibujo = ajustada
        r = min(c["redondeo"], destino.width() / 2, destino.height() / 2)
        camino = QPainterPath()
        camino.addRoundedRect(destino, r, r)
        p.setClipPath(camino, Qt.IntersectClip)
        p.drawImage(dibujo, imagen, origen)

    def _con_ajustes(self, p: QPainter, imagen: QImage, origen: QRectF, destino: QRectF,
                     c: dict) -> tuple[QImage, QRectF, QRectF] | None:
        """Solo el trozo de `origen` que se ve (con zoom, el resto de la foto no se calcula), con los ajustes de la capa
        y a los píxeles con que se va a ver, también en pantallas HiDPI (sin pasar de los de la foto): así el lienzo no
        va lento. Da (imagen, su rectángulo, dónde va en la capa), o None si no se ve nada. En caché hasta que cambien
        la imagen, lo que se ve, el zoom o los ajustes."""
        # De la capa a la foto; lo que se ve lleva un margen para que el desenfoque no cambie en el borde de la vista
        a_foto = QTransform.fromTranslate(origen.x(), origen.y()).scale(
            origen.width() / destino.width(), origen.height() / destino.height()).translate(-destino.x(), -destino.y())
        m = 2 * c["desenfoque"]
        visible = p.worldTransform().inverted()[0].mapRect(QRectF(p.window())).adjusted(-m, -m, m, m) & destino
        trozo = a_foto.mapRect(visible).toAlignedRect() & origen.toAlignedRect()
        if trozo.isEmpty():
            return None
        dibujo = a_foto.inverted()[0].mapRect(QRectF(trozo))  # justo donde van esos píxeles: nada se mueve
        t = p.deviceTransform()  # la del mundo, con la escala de la pantalla (HiDPI)
        f = min(math.hypot(t.m11(), t.m12()) * dibujo.width() / trozo.width(), 1,
                4096 / max(trozo.width(), trozo.height()))
        ancho, alto = max(1, round(trozo.width() * f)), max(1, round(trozo.height() * f))
        ajustes = tuple(c[k] for k in AJUSTES)
        clave = (imagen.cacheKey(), trozo.getRect(), ancho, alto, ajustes)
        if self._ajustada[0] != clave:
            pequena = imagen.copy(trozo).scaled(ancho, alto, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            # El desenfoque va en px del diseño: en los de este trozo, a su escala
            self._ajustada = clave, ajustar_imagen(pequena, *ajustes[:3], ajustes[3] * ancho / dibujo.width())
        return self._ajustada[1], QRectF(self._ajustada[1].rect()), dibujo


def _suavizar(a):
    """Cada píxel, la media de los 3 × 3 de su alrededor (con el borde repetido)."""
    import numpy as np
    for eje in (0, 1):
        b = np.moveaxis(a, eje, 0)
        c = b.copy()
        c[1:] += b[:-1]
        c[:-1] += b[1:]
        c[0] += b[0]
        c[-1] += b[-1]
        a = np.moveaxis(c, 0, eje) / 3
    return a


def ajustar_imagen(imagen: QImage, brillo: float = 0, contraste: float = 0, saturacion: float = 0,
                   radio: float = 0) -> QImage:
    """La imagen con brillo, contraste y saturación (de -100 a 100; 0 = igual) y desenfoque (radio en píxeles de esta
    imagen), como los ajustes de Photoshop. Sale premultiplicada: el desenfoque no oscurece los bordes transparentes."""
    import numpy as np
    w, h = imagen.width(), imagen.height()
    if radio > 2.8:  # tan desenfocada no tiene detalle: se desenfoca en pequeño (mucho más rápido) y se amplía
        f = 2.8 / radio
        pequena = imagen.scaled(max(1, round(w * f)), max(1, round(h * f)), Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation)
        return ajustar_imagen(pequena, brillo, contraste, saturacion, 2.8).scaled(w, h, Qt.IgnoreAspectRatio,
                                                                                  Qt.SmoothTransformation)
    origen = imagen.convertToFormat(QImage.Format_RGBA8888)
    a = np.frombuffer(origen.constBits(), np.uint8).reshape(h, origen.bytesPerLine())[:, :4 * w]
    a = a.reshape(h, w, 4).astype(np.float32)
    alfa = a[..., 3].copy()  # las cuentas van con los 4 canales (más rápido) y la transparencia se repone después
    if brillo or contraste or saturacion:
        factor = 2 ** (contraste / 50)  # de ¼ a ×4 alrededor del gris medio
        a *= factor
        a += 127.5 * (1 - factor) + brillo * 1.275
        if saturacion:  # gris + (color − gris) × s
            gris = a @ np.array([0.299, 0.587, 0.114, 0], np.float32)
            a *= 1 + saturacion / 100
            a -= (gris * (saturacion / 100))[..., None]
        np.clip(a, 0, 255, out=a)
    a *= (alfa / 255)[..., None]
    a[..., 3] = alfa
    # Cada pasada de 3 × 3 desenfoca un poco más: hasta 3, que son casi un desenfoque gaussiano de ese radio
    for _ in range(0 if radio < 0.5 else min(3, max(1, round((radio / 1.63) ** 2)))):
        a = _suavizar(a)
    datos = np.ascontiguousarray(np.clip(a + 0.5, 0, 255).astype(np.uint8))
    return QImage(datos.data, w, h, 4 * w, QImage.Format_RGBA8888_Premultiplied).copy()


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
        s.addItem(ItemCapa({**_COMUNES, **CAPAS["imagen"], "id": None, "tipo": "imagen", "ancho": d["ancho"],
                            "alto": d["alto"], "archivo": fondo["imagen"]}, carpeta))
    for capa in d["capas"]:
        s.addItem(ItemCapa(capa, carpeta))
    return s


def _pintar(s: QGraphicsScene, dispositivo, origen: QRectF) -> None:
    p = QPainter(dispositivo)
    if not p.isActive():
        raise RuntimeError(t("No se pudo escribir el archivo exportado (¿carpeta sin permiso o archivo abierto?)."))
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    destino = QRectF(0, 0, dispositivo.width(), dispositivo.height())
    if not isinstance(dispositivo, QImage):  # el PDF y el SVG
        _aplanar(s, p, destino, origen)
    s.render(p, destino, origen, Qt.IgnoreAspectRatio)
    p.end()


def _aplanar(s: QGraphicsScene, p: QPainter, destino: QRectF, origen: QRectF) -> None:
    """El PDF y el SVG no tienen modos de fusión: hasta la última capa con fusión se pintan como una imagen (al doble,
    300 ppp en el PDF, como sus sombras) y se esconden; lo de encima queda para pintarse en vectores."""
    # El fondo, la foto de fondo y las capas, de abajo arriba. Ni items(Qt.AscendingOrder) ni parentItem(): con
    # PySide6 dejan la escena sin pintar después
    items = [i for i in reversed(s.items()) if isinstance(i, (QGraphicsRectItem, ItemCapa))]
    ultima = max((n for n, i in enumerate(items) if isinstance(i, ItemCapa) and i._capa["fusion"] != "normal"),
                 default=None)
    if ultima is None:
        return
    for i in items[ultima + 1:]:
        i.hide()
    escala = min(2, math.sqrt(40_000_000 / (origen.width() * origen.height())))  # el tope de exportar
    plano = QImage(max(1, round(origen.width() * escala)), max(1, round(origen.height() * escala)),
                   QImage.Format_ARGB32_Premultiplied)
    plano.fill(Qt.transparent)
    _pintar(s, plano, origen)
    for n, i in enumerate(items):
        i.setVisible(n > ultima)
    p.drawImage(destino, plano)


# Tamaños fijos para exportar en vez de una escala: (lado largo en px, solo el cuadrado del centro)
TAMANOS_EXPORTAR = {"4k": (3840, False), "portada": (3000, True)}  # portada: la que piden Apple Music y DistroKid


def exportar(diseno: dict, carpeta: Path, destino: Path, formato: str = "png", escala: float | str = 1.0) -> Path:
    """Dibuja el diseño con la misma escena que el editor (lo que ves es lo que sale). PNG y JPG salen de
    ancho×escala por alto×escala píxeles; PDF y SVG, en vectores (la escala no cuenta). escala también puede ser una
    clave de TAMANOS_EXPORTAR: «4k» (lado largo de 3840 px) o «portada» (3000×3000 con el centro del diseño)."""
    if formato not in FORMATOS:
        raise ValueError(t("Formato no admitido ({formato!r:.20}); valen {formatos}.", formato=formato,
                           formatos=", ".join(FORMATOS)))
    lado, cuadrado = TAMANOS_EXPORTAR.get(escala, (0, False)) if isinstance(escala, str) else (0, False)
    if not lado:
        escala = _campo(lambda v: _num(v, 0.05, 4), escala, t("La escala"))
    destino = _local(destino)
    if destino.suffix.lower() not in {f".{formato}", ".jpeg" if formato == "jpg" else f".{formato}"}:
        destino = destino.with_name(f"{destino.name}.{formato}")  # se añade: «Oferta 3.99» no pierde el «.99»
    s = escena(diseno, carpeta)
    origen = s.sceneRect()
    if cuadrado:  # un diseño que no es cuadrado pierde los lados (o arriba y abajo), como una foto en «cubrir»
        corto = min(origen.width(), origen.height())
        origen = QRectF(origen.center().x() - corto / 2, origen.center().y() - corto / 2, corto, corto)
    if lado:  # un tamaño de salida fijo (como mucho 3840×3840): la escala sale de él y no tiene tope
        escala = lado / max(origen.width(), origen.height())
    ancho, alto = max(1, round(origen.width() * escala)), max(1, round(origen.height() * escala))
    if ancho * alto > 40_000_000:
        raise ValueError(t("La imagen saldría demasiado grande: baja la escala."))
    destino.parent.mkdir(parents=True, exist_ok=True)
    if formato in ("png", "jpg"):
        imagen = QImage(ancho, alto, QImage.Format_ARGB32_Premultiplied)
        imagen.fill(Qt.white if formato == "jpg" else Qt.transparent)
        _pintar(s, imagen, origen)
        if not imagen.save(str(destino), formato.upper(), 92 if formato == "jpg" else -1):
            raise RuntimeError(t("No se pudo guardar la imagen en {destino}.", destino=destino))
    elif formato == "pdf":
        pdf = QPdfWriter(str(destino))
        # La página va a 150 ppp (el flyer, 1240×1754, sale en A4 exacto) pero se dibuja a 300: lo que Qt pasa a
        # imagen (los textos con sombra) no sale pixelado al imprimir
        pdf.setResolution(300)
        pdf.setPageSize(QPageSize(QSizeF(origen.width() / 150, origen.height() / 150), QPageSize.Inch, "",
                                  QPageSize.ExactMatch))
        pdf.setPageMargins(QMarginsF(0, 0, 0, 0))
        _pintar(s, pdf, origen)
    else:
        svg = QSvgGenerator(QSvgGenerator.SvgVersion.Svg11)  # el Tiny 1.2 de por defecto no lleva clip-path (esquinas)
        svg.setResolution(96)  # la de los navegadores: un diseño de 1080 px mide 1080 px, no 1440
        svg.setFileName(str(destino))
        svg.setSize(QSize(int(origen.width()), int(origen.height())))
        svg.setViewBox(QRect(0, 0, int(origen.width()), int(origen.height())))
        _pintar(s, svg, origen)
    return destino


# ---------- Quitar el fondo ----------

class FondoNoLiso(ValueError):
    """La imagen no tiene un fondo de un solo color: sin IA no se puede quitar bien."""


def _crecer(marca, dentro, veces: int):
    """La marca extendida a sus vecinos (arriba, abajo y a los lados) que están `dentro` (None: a todos), hasta que no
    crece más o tras `veces` pasos. Con números, cada píxel se queda con el mayor de su alrededor."""
    import numpy as np
    for _ in range(veces):
        nueva = marca.copy()
        np.maximum(nueva[1:], marca[:-1], out=nueva[1:])
        np.maximum(nueva[:-1], marca[1:], out=nueva[:-1])
        np.maximum(nueva[:, 1:], marca[:, :-1], out=nueva[:, 1:])
        np.maximum(nueva[:, :-1], marca[:, 1:], out=nueva[:, :-1])
        if dentro is not None:
            nueva &= dentro
        if np.array_equal(nueva, marca):
            break
        marca = nueva
    return marca


def quitar_fondo(origen: Path, destino: Path, tolerancia: float = 60, fondo=None) -> Path:
    """Quita el fondo liso de una imagen (como las ilustraciones que pide la IA «isolated on plain solid background»),
    gratis y en el PC, y la guarda en `destino` como PNG con transparencia. El fondo es el color del borde: se quita lo
    que se le parece (a menos de `tolerancia` en distancia RGB) y llega al borde sin cruzar el dibujo, así lo de dentro
    del mismo color (unos ojos blancos sobre fondo blanco) se queda. El filo sale suave y sin el halo del fondo.
    FondoNoLiso si el borde no es de un solo color (una foto). fondo: el color (R, G, B) si ya se sabe (el verde que se
    pidió a la IA); entonces basta con que llegue al borde (un retrato toca abajo y los lados). Tarda unos segundos con
    una 4K: quien la llama la corre en segundo plano.
    ponytail: un fondo con viñeta muy marcada (el centro a más de `tolerancia` del borde) deja una mancha: con IA."""
    import numpy as np
    imagen = _leer_imagen(str(origen), Path(origen).stat().st_mtime_ns).convertToFormat(QImage.Format_RGBA8888)
    if imagen.isNull():
        raise ValueError(t("No se pudo leer la imagen."))
    w, h = imagen.width(), imagen.height()
    a = np.frombuffer(imagen.constBits(), np.uint8).reshape(h, imagen.bytesPerLine())[:, :4 * w].reshape(h, w, 4)
    if np.mean(np.concatenate([a[0, :, 3], a[-1, :, 3], a[:, 0, 3], a[:, -1, 3]]) < 128) > 0.5:
        raise ValueError(t("Esta imagen ya no tiene fondo: su borde es transparente."))
    try:
        borde = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])[:, :3].astype(np.float32)
        if fondo is None:
            fondo = np.median(borde, axis=0)
            if np.mean(np.linalg.norm(borde - fondo, axis=1) < tolerancia) < 0.7:
                raise FondoNoLiso(t("El fondo de esta imagen no es liso (de un solo color): sin IA no se puede quitar "
                                    "bien."))
        else:  # el tono que de verdad trae el borde, aunque el dibujo tape parte de él
            junto = np.linalg.norm(borde - fondo, axis=1) < 2 * tolerancia
            fondo = np.median(borde[junto], axis=0) if junto.any() else np.asarray(fondo, np.float32)
        # Canal a canal y en float32: con la imagen entera en float64 una 4K pedía unos 2 GB
        canales = [(a[..., k], f) for k, f in enumerate(fondo)]
        cerca = sum((c - f) ** 2 for c, f in canales) < tolerancia ** 2
        # Lo que llega al borde se busca en pequeño, que es rápido: un bloque cuenta solo si es todo fondo, así una raya
        # fina del dibujo no deja pasar; luego se termina píxel a píxel hasta el filo
        paso = max(1, math.ceil(max(w, h) / 512))
        filas, columnas = -(-h // paso), -(-w // paso)
        bloques = np.pad(cerca, ((0, filas * paso - h), (0, columnas * paso - w)), constant_values=True)
        bloques = bloques.reshape(filas, paso, columnas, paso).all(axis=(1, 3))
        semilla = np.zeros_like(bloques)
        semilla[[0, -1]] = bloques[[0, -1]]
        semilla[:, [0, -1]] |= bloques[:, [0, -1]]
        fuera = np.repeat(np.repeat(_crecer(semilla, bloques, 4 * (filas + columnas)), paso, 0), paso, 1)[:h, :w]
        fuera = _crecer(fuera, cerca, 2 * paso)
        if not fuera.any():
            raise FondoNoLiso(t("No encuentro el fondo en el borde de la imagen."))
        # Lo que se aparta del fondo hacia el blanco o el negro, en el canal que más (sin el ruido de menos del 4 %)
        mezcla = np.zeros((h, w), np.float32)
        for c, f in canales:
            d = c - f
            np.maximum(mezcla, np.maximum(d / max(255 - f, 1), -d / max(f, 1)), out=mezcla)
        np.clip((mezcla - 0.04) / 0.96, 0, 1, out=mezcla)
        # El fondo, transparente del todo; en el filo (a los dos lados), cada píxel es alfa × dibujo + (1 − alfa) ×
        # fondo. La opacidad: lo que se aparta del fondo comparado con lo que se aparta el dibujo de al lado (un dibujo
        # color piel sobre blanco se aparta poco y es opaco); el color, el del dibujo sin el del fondo (sin halo)
        # Del ancho del suavizado (≈1 px por cada 1024): más ancho, se mete por dentro de un contorno fino y vuelve
        # translúcido el relleno claro que hay detrás
        lado = max(1, round(max(w, h) / 1024))
        filo = _crecer(fuera, None, lado) & _crecer(~fuera, None, lado)
        vecino = _crecer(np.where(fuera, np.float32(0), mezcla), None, 2 * lado)
        alfa = np.minimum(mezcla[filo] / np.maximum(vecino[filo], 1e-3), 1)[:, None]
        datos = a.copy()
        datos[fuera, 3] = 0
        pixeles = a[filo]
        color = np.clip((pixeles[:, :3] - (1 - alfa) * fondo) / np.maximum(alfa, 1e-3), 0, 255)
        datos[filo] = np.hstack([color, alfa * pixeles[:, 3:]]).round()
    except MemoryError:
        raise RuntimeError(t("No hay memoria libre para quitar el fondo de una imagen tan grande: cierra otros "
                             "programas y vuelve a probar.")) from None
    if not QImage(datos.data, w, h, 4 * w, QImage.Format_RGBA8888).save(str(destino), "PNG"):
        raise RuntimeError(t("No se pudo guardar la imagen en {destino}.", destino=destino))
    return Path(destino)
