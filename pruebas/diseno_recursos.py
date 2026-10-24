"""Pruebas de motor/recursos.py (iconos, fuentes, emojis), sin internet: python -m pruebas.diseno_recursos"""
import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray, Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from motor import recursos  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication([])

# Iconos: los de Lucide, ordenados y con nombres seguros
nombres = recursos.iconos()
assert len(nombres) > 1000 and nombres == sorted(nombres)
assert {"pizza", "shopping-cart", "phone"} <= set(nombres)

# El SVG sale con el color y el grosor pedidos, y Qt lo pinta de ese color
svg = recursos.svg_icono("pizza", "#FF0000", 3)
assert b"currentColor" not in svg and b'stroke="#FF0000"' in svg and b'stroke-width="3"' in svg, svg[:300]
assert b'stroke-width="2"' not in svg
render = QSvgRenderer(QByteArray(svg))
assert render.isValid()
img = QImage(48, 48, QImage.Format_ARGB32)
img.fill(Qt.transparent)
pintor = QPainter(img)
render.render(pintor)
pintor.end()
pixeles = [img.pixelColor(x, y) for x in range(48) for y in range(48)]
assert any(c.alpha() > 200 and c.red() > 200 and c.green() < 60 and c.blue() < 60 for c in pixeles)
assert b'stroke-width="1.5"' in recursos.svg_icono("phone", "#00aa00", 1.5)

# Nombres, colores y grosores malos (pueden venir de la IA o de un diseño ajeno): ValueError, sin tocar el disco
for malo in ("../claves", "..\\claves", "Pizza", "pizza.svg", "pizza\n", "no-existe-zzz", "", " pizza", None, 5,
             "/etc/passwd", "C:\\Windows\\win.ini", "etiquetas", "LICENSE"):
    try:
        recursos.svg_icono(malo)
        raise AssertionError(f"debió rechazar el icono {malo!r}")
    except ValueError:
        pass
for malo in ("red", "#FFF", "#GGGGGG", "#FFFFFF\n", "#FFFFFF\"/><script>", "", None, 0xFFFFFF, "FFFFFF"):
    try:
        recursos.svg_icono("pizza", malo)
        raise AssertionError(f"debió rechazar el color {malo!r}")
    except ValueError:
        pass
for malo in (float("nan"), float("inf"), -1, 0, 11, "2", True, None):
    try:
        recursos.svg_icono("pizza", "#FFFFFF", malo)
        raise AssertionError(f"debió rechazar el grosor {malo!r}")
    except ValueError:
        pass

# Búsqueda de iconos: por nombre (exacto primero), varias palabras, por etiqueta y con límite
assert recursos.buscar_iconos("pizza")[0] == "pizza"
assert recursos.buscar_iconos("Shopping Cart")[0] == "shopping-cart"
assert "accessibility" in recursos.buscar_iconos("wheelchair")  # solo por etiqueta
assert recursos.buscar_iconos("zzzqqqxx") == []
assert recursos.buscar_iconos("") == nombres[:60] and len(recursos.buscar_iconos("arrow", 5)) == 5

# Fuentes: las 14 familias OFL (8 de marketing y 6 góticas o decorativas), y Qt las registra de verdad
familias = recursos.fuentes()
assert familias == sorted(["Montserrat", "Poppins", "Bebas Neue", "Anton", "Oswald", "Playfair Display", "Pacifico",
                           "Lora", "Pirata One", "Grenze Gotisch", "Metal Mania", "New Rocker", "Creepster",
                           "Cinzel Decorative"]), familias
archivos = recursos.archivos_fuentes()
leeme = (recursos.RAIZ_ASSETS / "LEEME.md").read_text(encoding="utf-8")
registradas = set()
for archivo in archivos:
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() in leeme, f"{archivo.name}: el hash no es el de LEEME.md"
    id_fuente = QFontDatabase.addApplicationFont(str(archivo))
    assert id_fuente >= 0, f"Qt no pudo registrar {archivo.name}"
    registradas |= set(QFontDatabase.applicationFontFamilies(id_fuente))
assert set(familias) <= registradas, set(familias) - registradas
for familia in familias:
    assert QFontInfo(QFont(familia)).family() == familia, familia
assert "Bold" in QFontDatabase.styles("Montserrat") and "Bold Italic" in QFontDatabase.styles("Poppins")
assert "Bold" in QFontDatabase.styles("Cinzel Decorative")
assert (recursos.RAIZ_ASSETS / "fuentes" / "OFL.txt").is_file() and (recursos.RAIZ_ASSETS / "iconos" / "LICENSE").is_file()
ofl = (recursos.RAIZ_ASSETS / "fuentes" / "OFL.txt").read_text(encoding="utf-8")
assert all(f"===== {f} =====" in ofl for f in familias), [f for f in familias if f"===== {f} =====" not in ofl]

# Emojis: de unicodedata, con nombre, sin los cuadraditos de tono de piel
lista = recursos.emojis()
assert ("🍕", "slice of pizza") in lista and all(n for _, n in lista)
assert {"⚡", "❤", "✨", "⭐", "😀", "🔥"} <= {e for e, _ in lista}
assert not any(n.startswith("emoji modifier") for _, n in lista)
assert not {"🌣", "🎔", "🖎", "🤀"} & {e for e, _ in lista}  # símbolos en blanco y negro que no son emoji
assert {"🟢", "🆕", "🅿", "🀄", "🫶"} <= {e for e, _ in lista} and len(lista) == len(dict(lista))
assert recursos.buscar_emojis("pizza") == ["🍕"]
assert "🔥" in recursos.buscar_emojis("FIRE") and "❤" in recursos.buscar_emojis("heart")
assert "sun" in dict(lista)[recursos.buscar_emojis("sun")[0]].split()  # el sol antes que el girasol (sunflower)
assert len(recursos.buscar_emojis("", 10)) == 10 and recursos.buscar_emojis("zzzqqq") == []
assert recursos.FUENTE_EMOJI[0] == "Segoe UI Emoji"

print("Pruebas de recursos de diseño pasadas.")
