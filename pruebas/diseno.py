"""Pruebas del estudio de diseño (motor/diseno.py y motor/marca.py), sin red ni claves: python -m pruebas.diseno"""
import copy
import json
import os
import re
import struct
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QGraphicsItem  # noqa: E402

from motor import diseno, marca  # noqa: E402

diseno.asegurar_qt()


def falla(funcion, *args):
    """Lo hostil se rechaza con un ValueError claro: ni revienta con otro error ni pasa."""
    try:
        funcion(*args)
    except ValueError:
        return
    raise AssertionError(f"debió rechazar {args!r:.300}")


def parecido(color: QColor, hex_: str, margen: int = 40) -> bool:
    otro = QColor(hex_)
    return all(abs(a - b) <= margen for a, b in ((color.red(), otro.red()), (color.green(), otro.green()),
                                                (color.blue(), otro.blue())))


def hay_color(imagen: QImage, hex_: str, x0: int, y0: int, x1: int, y1: int) -> bool:
    return any(parecido(imagen.pixelColor(x, y), hex_, 60) for x in range(x0, x1, 2) for y in range(y0, y1, 2))


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    diseno.CARPETA = d / "disenos"  # nada de tocar datos/ de verdad
    marca.ARCHIVO, marca.CARPETA_LOGO = d / "marca.json", d / "marca"

    # Foto de prueba: mitad izquierda roja y derecha azul (para ver cómo recortan «cubrir» y «contener»)
    foto = QImage(400, 200, QImage.Format_RGB32)
    foto.fill(QColor("#FF0000"))
    pintor = QPainter(foto)
    pintor.fillRect(200, 0, 200, 200, QColor("#0000FF"))
    pintor.end()
    ruta_foto = d / "foto.png"
    assert foto.save(str(ruta_foto))
    secreto = d / "claves.png"  # un archivo privado con nombre de foto
    secreto.write_text('{"openai": "sk-SECRETO"}', encoding="utf-8")

    # ---------- Carpeta e imágenes ----------
    carpeta = diseno.nueva_carpeta("Anuncio pizzería")
    assert carpeta.parent == diseno.CARPETA and carpeta.name.endswith("-anuncio-pizzeria"), carpeta
    assert (carpeta / "imagenes").is_dir()
    assert diseno.nueva_carpeta("Anuncio pizzería") != carpeta  # mismo nombre en el mismo segundo: otra carpeta
    assert diseno.nueva_carpeta("../../..\\x").parent == diseno.CARPETA  # el nombre no saca la carpeta de su sitio
    with ThreadPoolExecutor(8) as hilos:  # el MCP crea diseños en paralelo: mismo nombre a la vez, ninguno falla
        a_la_vez = list(hilos.map(diseno.nueva_carpeta, ["A la vez"] * 40))
    assert len(set(a_la_vez)) == 40 and all((c / "imagenes").is_dir() for c in a_la_vez)
    nombre_foto = diseno.importar_imagen(str(ruta_foto), carpeta)
    assert (carpeta / "imagenes" / nombre_foto).read_bytes() == ruta_foto.read_bytes()
    assert diseno.nombre_imagen(nombre_foto) == nombre_foto
    for malo in (str(secreto), "datos/claves.json", r"\\atacante.example\s\a.png", "//atacante.example/s/a.png",
                 str(d / "no_existe.png"), ""):
        falla(diseno.importar_imagen, malo, carpeta)
    falla(diseno.importar_imagen, str(ruta_foto), r"\\atacante.example\s\diseno")

    # ---------- Un diseño con todas las capas ----------
    original = {
        "version": 1, "nombre": "Anuncio pizzería", "ancho": 1080, "alto": 1080, "extra": "se quita",
        "fondo": {"tipo": "degradado", "colores": ["#000000", "#ffffff"], "imagen": ""},
        "capas": [
            {"id": "foto", "tipo": "imagen", "x": 0, "y": 0, "ancho": 200, "alto": 200, "archivo": nombre_foto,
             "ajuste": "cubrir", "redondeo": 0, "onclick": "se quita"},
            {"id": "foto2", "tipo": "imagen", "x": 300, "y": 0, "ancho": 200, "alto": 200, "archivo": nombre_foto,
             "ajuste": "contener", "redondeo": 30},
            {"id": "caja", "tipo": "forma", "forma": "rectangulo", "x": 600, "y": 0, "ancho": 200, "alto": 200,
             "relleno": "#00FF00", "borde": "#FFFFFF", "grosor_borde": 4, "redondeo": 20},
            {"id": "circulo", "tipo": "forma", "forma": "elipse", "x": 850, "y": 0, "ancho": 200, "alto": 200,
             "relleno": "#FF00FF"},
            {"id": "raya", "tipo": "forma", "forma": "linea", "x": 0, "y": 300, "ancho": 1080, "alto": 20,
             "relleno": "#00FFFF", "grosor_borde": 10},
            {"id": "titulo", "tipo": "texto", "x": 90, "y": 400, "ancho": 900, "alto": 220,
             "texto": "<b>PIZZA</b> 2x1 <script>alert(1)</script>", "fuente": "Montserrat", "tamano": 90,
             "color": "#FFFF00", "negrita": True, "alineacion": "centro", "contorno": "#000000",
             "grosor_contorno": 3, "sombra": True},
            {"id": "tel", "tipo": "icono", "nombre": "phone", "x": 60, "y": 700, "ancho": 160, "alto": 160,
             "color": "#FF0000", "rotacion": 15, "opacidad": 0.9},
            {"id": "emo", "tipo": "emoji", "texto": "🍕", "x": 900, "y": 700, "ancho": 120, "alto": 120},
        ]}
    antes = copy.deepcopy(original)
    limpio = diseno.validar(original)
    assert original == antes  # validar no toca lo que le pasan
    assert "extra" not in limpio and "onclick" not in limpio["capas"][0]
    assert [c["id"] for c in limpio["capas"]] == ["foto", "foto2", "caja", "circulo", "raya", "titulo", "tel", "emo"]
    assert limpio["fondo"]["colores"] == ["#000000", "#FFFFFF"]
    texto = limpio["capas"][5]
    assert texto["cursiva"] is False and texto["opacidad"] == 1 and texto["rotacion"] == 0  # lo que falta, por defecto
    assert diseno.validar(limpio) == limpio  # validar dos veces da lo mismo
    assert diseno.validar({}) == {"version": 1, "nombre": "Mi diseño", "ancho": 1080, "alto": 1080,
                                  "fondo": {"tipo": "color", "colores": ["#FFFFFF"], "imagen": ""}, "capas": []}
    # ids que faltan, que no valen o repetidos se cambian por otros únicos (el editor busca las capas por id)
    ids = [c["id"] for c in diseno.validar({"capas": [{"tipo": "emoji", "id": "a"}, {"tipo": "emoji", "id": "a"},
                                                       {"tipo": "emoji"}, {"tipo": "emoji", "id": "../x"}]})["capas"]]
    assert ids[0] == "a" and len(set(ids)) == 4 and "../x" not in ids
    assert len(diseno.validar({"capas": [{"tipo": "emoji"}] * 80})["capas"]) == 80  # el máximo sí vale
    assert diseno.validar({"capas": [{"tipo": "texto", "texto": "x" * 2000}]})["capas"][0]["texto"] == "x" * 2000

    # ---------- Topes contra diseños que cuelgan el editor o llenan la memoria ----------
    # Capa de más del doble del lienzo y contorno de más de 1/4 de la letra: se recortan (lo de antes sigue abriéndose)
    grande = diseno.validar({"ancho": 1240, "alto": 1754, "capas": [
        {"tipo": "forma", "ancho": 20000, "alto": 3000},
        {"tipo": "texto", "tamano": 20, "contorno": "#000000", "grosor_contorno": 200}]})["capas"]
    assert (grande[0]["ancho"], grande[0]["alto"]) == (2480, 3000) and grande[1]["grosor_contorno"] == 5
    assert diseno.validar({"ancho": 1240, "alto": 1754, "capas": grande})["capas"] == grande  # idempotente
    # ajustar_capa (la del editor) recorta sin lanzar error, aunque haya valores que luego rechazará validar
    assert diseno.ajustar_capa({"tipo": "forma", "ancho": 9000, "alto": "x"}, {"ancho": 1080}) == \
        {"tipo": "forma", "ancho": 2160, "alto": "x"}
    foto_capa = {"tipo": "imagen", "archivo": nombre_foto}
    assert len(diseno.validar({"capas": [foto_capa] * diseno.MAX_IMAGENES})["capas"]) == 12
    falla(diseno.validar, {"fondo": {"tipo": "imagen", "colores": ["#000000"], "imagen": nombre_foto},
                           "capas": [foto_capa] * 12})  # 13 contando la del fondo
    con_contorno = {"tipo": "texto", "texto": "x" * 1001, "contorno": "#000000", "grosor_contorno": 2}
    falla(diseno.validar, {"capas": [con_contorno] * 2})  # 2002 letras con contorno
    assert diseno.validar({"capas": [{**con_contorno, "contorno": ""}] * 2})  # sin contorno no cuentan
    emoji_grande = {"tipo": "emoji", "texto": "🍕", "ancho": 2160, "alto": 2160}  # 4,67 M píxeles cada uno
    assert diseno.validar({"capas": [emoji_grande] * 3})
    falla(diseno.validar, {"capas": [emoji_grande] * 4})
    falla(diseno.validar, {"capas": [{"tipo": "texto", "texto": "🇪🇸🇫🇷🇮🇹", "tamano": 2000}]})  # banderas también

    # ---------- JSON hostil: todo da ValueError ----------
    def con(capa):
        return {"ancho": 1080, "alto": 1080, "capas": [capa]}
    for archivo in ("../claves.json", "../x.png", "..\\..\\datos\\x.png", "..", "C:\\Windows\\x.png", "C:x.png",
                    "/etc/x.png", r"\\srv\s\a.png", "//srv/s/a.png", r"\\?\UNC\srv\s\a.png", "imagenes/a.png",
                    "a.png\n", "a.png ", " a.png", "CON.png", "nul.jpg", "LPT1.bmp", "", ".png", "a.exe", "a.svg",
                    "a.png.exe", "a..png", "a.png/..", "ñandú.png", "x" * 200 + ".png", None, 5, ["a.png"]):
        falla(diseno.validar, con({"tipo": "imagen", "archivo": archivo}))
        falla(diseno.validar, {"fondo": {"tipo": "imagen", "colores": ["#000000"], "imagen": archivo}})
    for campo, malo in (("x", float("nan")), ("x", float("inf")), ("y", -float("inf")), ("y", 1e308), ("x", 10 ** 400),
                        ("x", -10 ** 400), ("ancho", -5), ("ancho", 0), ("alto", 1e9), ("rotacion", 1e9),
                        ("opacidad", 2), ("opacidad", -0.1), ("opacidad", float("nan")), ("tamano", 0),
                        ("tamano", 1e6), ("grosor_contorno", -1), ("grosor_contorno", 1e9), ("x", "12"), ("x", True),
                        ("x", None), ("x", [1]), ("x", {"a": 1})):
        falla(diseno.validar, con({"tipo": "texto", campo: malo}))
    for malo in ("red", "#FFF", "#GGGGGG", "#FFFFFF\n", " #FFFFFF", '#FFFFFF"/><script>', "", None, 0xFFFFFF,
                 "FFFFFF", "rgb(0,0,0)", "#FFFFFFFF", ["#FFFFFF"]):
        falla(diseno.validar, con({"tipo": "texto", "color": malo}))
        falla(diseno.validar, con({"tipo": "forma", "relleno": malo}))
        falla(diseno.validar, {"fondo": {"tipo": "color", "colores": [malo]}})
        if malo != "":
            falla(diseno.validar, con({"tipo": "forma", "borde": malo}))
    assert diseno.validar(con({"tipo": "texto", "contorno": ""}))["capas"][0]["contorno"] == ""
    for malo in ("no-existe-zzz", "../claves", "..\\claves", "Pizza", "pizza.svg", "pizza\n", "", None, 5,
                 "LICENSE", "etiquetas", "/etc/passwd"):
        falla(diseno.validar, con({"tipo": "icono", "nombre": malo}))
    for malo in ("script", "TEXTO", "", None, 5, ["texto"], {"a": 1}):
        falla(diseno.validar, con({"tipo": malo}))
    for campo, malo in (("alineacion", "justify"), ("ajuste", "stretch"), ("forma", "triangulo"), ("negrita", "yes"),
                        ("negrita", 1), ("sombra", None), ("texto", "x" * 2001), ("texto", None), ("texto", 5),
                        ("fuente", "x" * 101), ("alineacion", ["centro"])):
        tipo = {"ajuste": "imagen", "forma": "forma"}.get(campo, "texto")
        falla(diseno.validar, con({"tipo": tipo, "archivo": nombre_foto, campo: malo}))
    # Qt escribe la fuente sin escapar en el font-family del SVG: con comillas saldría un <script> de verdad
    for malo in ('x"/><script>console.log(1)</script><text a="', "Arial'", "a<b", "a;b", "", "a\nb", None, 5):
        falla(diseno.validar, con({"tipo": "texto", "fuente": malo}))
    for malo in ([], "diseño", None, 5, {"capas": "no"}, {"capas": {"0": {}}}, {"capas": [{"tipo": "emoji"}] * 81},
                 {"capas": [{"tipo": "emoji"}] * 10_000}, {"capas": ["hola"]}, {"capas": [None]}, {"version": 2},
                 {"version": "1"}, {"ancho": 0}, {"ancho": 100_000}, {"alto": float("nan")}, {"fondo": "rojo"},
                 {"fondo": {"tipo": "degradado", "colores": ["#000000"]}}, {"fondo": {"colores": []}},
                 {"fondo": {"colores": ["#000000"] * 4}}, {"fondo": {"tipo": "video"}}, {"nombre": "x" * 121},
                 {"nombre": None}):
        falla(diseno.validar, malo)

    # Archivos diseno.json hostiles o rotos: abrir da ValueError (nunca otro error)
    for contenido in ('{"ancho": NaN}', '{"ancho": Infinity}', '{"ancho": 1' + "0" * 400 + "}", "[" * 100_000,
                      "no es json", '{"capas": [' + ",".join(['{"tipo": "emoji"}'] * 10_000) + "]}", "[]",
                      '{"capas": [{"tipo": "imagen", "archivo": "../../claves.json"}]}', " " * (3 * 1024 ** 2)):
        malo = diseno.nueva_carpeta("malo")
        (malo / "diseno.json").write_text(contenido, encoding="utf-8")
        falla(diseno.abrir, malo)
    (malo / "diseno.json").write_bytes(b"\xff\xfe\x00basura")
    falla(diseno.abrir, malo)
    falla(diseno.abrir, d / "no_existe")
    falla(diseno.abrir, r"\\atacante.example\s\diseno")

    # ---------- Guardar, abrir y listar ----------
    archivo = diseno.guardar(original, carpeta)
    assert archivo == carpeta / "diseno.json" and diseno.abrir(carpeta) == limpio
    assert not list(carpeta.glob("*.tmp"))  # la escritura atómica no deja temporales
    miniatura = QImage(str(carpeta / "miniatura.png"))
    assert max(miniatura.width(), miniatura.height()) <= 360 and not miniatura.isNull()
    falla(diseno.guardar, {"capas": "no"}, carpeta)
    falla(diseno.guardar, limpio, r"\\atacante.example\s\diseno")
    assert diseno.abrir(carpeta) == limpio  # un guardado que falla no estropea el que había
    chico = diseno.nueva_carpeta("chico")
    diseno.guardar({"ancho": 16, "alto": 16}, chico)  # el lienzo más pequeño también tiene miniatura
    assert QImage(str(chico / "miniatura.png")).width() == 16
    os.utime(chico / "diseno.json", (0, 0))
    otra = diseno.nueva_carpeta("Otro")
    diseno.guardar(diseno.nuevo("historia", "Otro"), otra)
    os.utime(otra / "diseno.json", (1, 1))  # el «otro» es más viejo
    lista = diseno.listar()
    assert [x["carpeta"] for x in lista] == [str(carpeta), str(otra), str(chico)], lista  # las rotas no salen
    assert lista[0]["nombre"] == "Anuncio pizzería" and lista[0]["miniatura"] == str(carpeta / "miniatura.png")
    # Una miniatura.png ajena que en realidad es un SVG (Qt la abriría como tal y leería lo que pida): no se ofrece
    ajena = diseno.nueva_carpeta("ajena")
    diseno.guardar({"nombre": "Ajena"}, ajena)
    (ajena / "miniatura.png").write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="C:/x.png"/></svg>',
                                         encoding="utf-8")
    assert next(x for x in diseno.listar() if x["carpeta"] == str(ajena))["miniatura"] == ""

    # ---------- La escena: un item por capa, en orden, con su id ----------
    editable = copy.deepcopy(limpio)  # lo que el editor tendría abierto
    s = diseno.escena(editable, carpeta)
    items = [i for i in s.items(Qt.AscendingOrder) if i.data(0) is not None]
    assert [i.data(0) for i in items] == [c["id"] for c in editable["capas"]]
    assert s.sceneRect().width() == 1080 and s.sceneRect().height() == 1080
    titulo = next(i for i in items if i.data(0) == "titulo")
    assert titulo.texto.toPlainText() == "<b>PIZZA</b> 2x1 <script>alert(1)</script>"  # texto plano, nunca HTML
    assert titulo.graphicsEffect() is not None and titulo._contorno.isVisible()
    assert titulo.texto.textWidth() - 2 * titulo.texto.document().documentMargin() == 900  # salta de línea al ancho
    assert titulo.flags() & QGraphicsItem.ItemClipsChildrenToShape  # el texto desbordado no llega a la sombra
    # La sombra se escala con el zoom: dibujada a la mitad, desenfoque y desplazamiento a la mitad (90/6 y 90/20)
    diseno._pintar(s, QImage(540, 540, QImage.Format_ARGB32_Premultiplied))
    assert (titulo.graphicsEffect().blurRadius(), titulo.graphicsEffect().yOffset()) == (7.5, 2.25)
    tel = next(i for i in items if i.data(0) == "tel")
    assert tel.pos() == QPointF(60, 700) and tel.rotation() == 15 and abs(tel.opacity() - 0.9) < 1e-6
    assert tel.sceneBoundingRect().center() == QPointF(140, 780)  # gira alrededor de su centro
    # Lo que hará el editor: buscar la capa por el id del item, cambiarla y aplicarla
    caja = next(i for i in items if i.data(0) == "caja")
    capa = next(c for c in editable["capas"] if c["id"] == caja.data(0))
    capa.update(x=10, y=20, ancho=50, alto=60, rotacion=90)
    caja.aplicar(capa)
    assert caja.pos() == QPointF(10, 20) and caja.rotation() == 90 and caja.transformOriginPoint() == QPointF(25, 30)
    assert caja.sceneBoundingRect().center() == QPointF(35, 50)
    titulo.aplicar({**texto, "texto": "otro", "contorno": "", "sombra": False, "alineacion": "derecha"})
    assert titulo.texto.toPlainText() == "otro" and titulo.graphicsEffect() is None
    assert not titulo._contorno.isVisible()
    # Una imagen que no pasó por validar con «../» no se carga aunque exista fuera de imagenes/
    (carpeta / "fuera.png").write_bytes(ruta_foto.read_bytes())
    foto_item = items[0]
    foto_item.aplicar({**limpio["capas"][0], "archivo": "../fuera.png"})
    assert foto_item._imagen is None
    foto_item.aplicar({**limpio["capas"][0], "archivo": nombre_foto})
    assert foto_item._imagen is not None
    assert foto_item._imagen.cacheKey() == items[1]._imagen.cacheKey()  # la misma foto se decodifica una vez
    # Foto de móvil con el giro en el EXIF (Orientation = 6): sale de pie (200×400), no tumbada
    foto.save(str(d / "movil.jpg"), "JPG", 95)
    exif = (b"Exif\x00\x00MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">HHHIHH", 1, 0x0112, 3, 1, 6, 0)
            + b"\x00" * 4)
    crudo = (d / "movil.jpg").read_bytes()
    (d / "movil.jpg").write_bytes(crudo[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + crudo[2:])
    girada = diseno._imagen(carpeta, diseno.importar_imagen(str(d / "movil.jpg"), carpeta))
    assert (girada.width(), girada.height()) == (200, 400)

    # ---------- Exportar los 4 formatos ----------
    png = diseno.exportar(limpio, carpeta, d / "salida" / "anuncio.png")
    imagen = QImage(str(png))
    assert png.is_file() and (imagen.width(), imagen.height()) == (1080, 1080)
    assert len({imagen.pixel(x, y) for x in range(0, 1080, 20) for y in range(0, 1080, 20)}) > 50  # no está vacía
    # «cubrir» recorta el centro de la foto; «contener» la deja entera
    assert parecido(imagen.pixelColor(50, 100), "#FF0000") and parecido(imagen.pixelColor(150, 100), "#0000FF")
    assert parecido(imagen.pixelColor(350, 100), "#FF0000") and parecido(imagen.pixelColor(450, 100), "#0000FF")
    assert parecido(imagen.pixelColor(400, 20), "#000000")  # contener deja ver el fondo arriba y abajo
    assert parecido(imagen.pixelColor(700, 100), "#00FF00") and parecido(imagen.pixelColor(950, 100), "#FF00FF")
    assert parecido(imagen.pixelColor(540, 310), "#00FFFF") and not parecido(imagen.pixelColor(540, 330), "#00FFFF")
    assert parecido(imagen.pixelColor(540, 3), "#000000") and parecido(imagen.pixelColor(540, 1077), "#FFFFFF")
    assert hay_color(imagen, "#FFFF00", 90, 400, 990, 620)  # el título amarillo
    assert hay_color(imagen, "#FF0000", 60, 700, 220, 860)  # el icono rojo
    # El emoji sale en color también sin ventana (el fondo ahí es gris, sin saturación)
    assert any(imagen.pixelColor(x, y).saturation() > 120 for x in range(900, 1020, 3) for y in range(700, 820, 3))
    pequena = QImage(str(diseno.exportar(limpio, carpeta, d / "salida" / "chica.png", "png", 0.5)))
    assert (pequena.width(), pequena.height()) == (540, 540)
    jpg = diseno.exportar(limpio, carpeta, d / "salida" / "anuncio", "jpg", 2)
    assert jpg.suffix == ".jpg" and (QImage(str(jpg)).width(), QImage(str(jpg)).height()) == (2160, 2160)
    # La extensión se añade: «Oferta 3.99 euros» no se queda en «Oferta 3.png»
    assert diseno.exportar(limpio, carpeta, d / "salida" / "Oferta 3.99 euros").name == "Oferta 3.99 euros.png"
    pdf = diseno.exportar(limpio, carpeta, d / "salida" / "anuncio.pdf", "pdf")
    assert pdf.read_bytes().startswith(b"%PDF") and pdf.stat().st_size > 2000
    # Página de 1080/150 pulgadas (518 pt), pero el título con sombra va como imagen a 300 ppp (~1950 px, no ~975)
    assert b"/MediaBox [0 0 518" in pdf.read_bytes()
    assert max(map(int, re.findall(rb"/Width (\d+)", pdf.read_bytes()))) > 1500
    svg = diseno.exportar(limpio, carpeta, d / "salida" / "anuncio.txt", "svg")
    contenido = svg.read_bytes()
    assert svg.suffix == ".svg" and b"<svg" in contenido and b"<image" in contenido
    assert b"<script" not in contenido and b"<b>" not in contenido  # el texto no se cuela como código en el SVG
    # SVG 1.1: lleva las esquinas redondeadas de la foto, y a 96 ppp mide 1080 px (285,75 mm) y no 1440
    assert b"<clipPath" in contenido and b'width="285.75mm"' in contenido
    for formato in ("gif", "exe", "", None, "PNG"):
        falla(diseno.exportar, limpio, carpeta, d / "x.png", formato)
    for escala in (0, -1, 100, float("nan"), float("inf"), "2", True):
        falla(diseno.exportar, limpio, carpeta, d / "x.png", "png", escala)
    falla(diseno.exportar, {"ancho": 5000, "alto": 5000}, carpeta, d / "x.png", "png", 4)  # 400 MP: no
    falla(diseno.exportar, limpio, carpeta, r"\\atacante.example\s\x.png")
    falla(diseno.exportar, {"capas": [{"tipo": "nada"}]}, carpeta, d / "x.png")
    # Un diseño con imagen que no existe, fondo de imagen y emoji se dibuja igual (sin romperse)
    raro = {"fondo": {"tipo": "imagen", "colores": ["#123456"], "imagen": nombre_foto},
            "capas": [{"tipo": "imagen", "archivo": "no-esta.png"}, {"tipo": "emoji", "texto": "🍕🔥"}]}
    fondo_img = QImage(str(diseno.exportar(raro, carpeta, d / "raro.png")))
    assert parecido(fondo_img.pixelColor(100, 540), "#FF0000") and parecido(fondo_img.pixelColor(980, 540), "#0000FF")
    sin_fondo = QImage(str(diseno.exportar({**raro, "fondo": {**raro["fondo"], "imagen": "no-esta.png"}}, carpeta,
                                            d / "raro2.png")))
    assert parecido(sin_fondo.pixelColor(1000, 1000), "#123456")  # sin la imagen queda el color de respaldo

    # ---------- Marca ----------
    assert marca.cargar() == marca.POR_DEFECTO  # sin archivo: valores por defecto
    marca.cargar()["colores"].append("#000000")
    assert marca.cargar()["colores"] == []  # cada carga es una copia nueva
    nuevo = diseno.nuevo("historia", "Historia")
    assert (nuevo["ancho"], nuevo["alto"]) == (1080, 1920) and nuevo["fondo"]["colores"] == ["#FFFFFF"]
    for malo in ("gigante", None, ["post"]):
        falla(diseno.nuevo, malo)
    mia = {"nombre": "Pizzería Don Juan", "eslogan": "La mejor del barrio", "logo": "",
           "colores": ["#ff4d8d", "#0F0F13"], "fuente_titulo": "Bebas Neue", "fuente_texto": "Lora", "tono": "cercano"}
    marca.guardar(mia)
    assert marca.cargar() == {**mia, "colores": ["#FF4D8D", "#0F0F13"]}
    assert not list(d.glob("*.tmp")) and marca.ruta_logo() is None
    assert diseno.nuevo()["fondo"]["colores"] == ["#FF4D8D"]  # el diseño nuevo sale con el color de la marca
    for campo, malo in (("colores", ["red"]), ("colores", "#FFFFFF"), ("colores", ["#000000"] * 9),
                        ("logo", "../x.png"), ("logo", r"C:\x.png"), ("logo", None), ("nombre", "x" * 121), ("tono", 5),
                        ("fuente_titulo", None), ("fuente_titulo", 'x"/><script>'), ("fuente_texto", "a<b")):
        falla(marca.guardar, {**mia, campo: malo})
    falla(marca.guardar, "marca")
    assert marca.cargar()["nombre"] == "Pizzería Don Juan"  # lo rechazado no se escribió
    logo = marca.poner_logo(str(ruta_foto))
    assert (marca.CARPETA_LOGO / logo).read_bytes() == ruta_foto.read_bytes()
    marca.guardar({**mia, "logo": logo})
    assert marca.ruta_logo() == marca.CARPETA_LOGO / logo
    assert diseno.importar_imagen(str(marca.ruta_logo()), carpeta)  # la IA pone el logo en un diseño así
    for malo in (str(secreto), "datos/claves.json", r"\\atacante.example\s\logo.png", ""):
        falla(marca.poner_logo, malo)
    # Archivo de marca roto o tocado a mano: se queda con lo que vale y lo demás, por defecto
    marca.ARCHIVO.write_text(json.dumps({"nombre": "Hola", "colores": ["red"], "logo": "../../claves.json",
                                         "tono": 5, "eslogan": "Ok", "fuente_titulo": 'x"/><script>'}),
                             encoding="utf-8")
    assert marca.cargar() == {**marca.POR_DEFECTO, "nombre": "Hola", "eslogan": "Ok"}
    for roto in ("{", "[]", "5", '"x"', "[" * 100_000):
        marca.ARCHIVO.write_text(roto, encoding="utf-8")
        assert marca.cargar() == marca.POR_DEFECTO, roto
print("Pruebas del estudio de diseño pasadas.")
