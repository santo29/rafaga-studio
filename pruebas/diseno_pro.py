"""Pruebas de Diseño Pro sin red ni claves: la IA que diseña, «Editar con IA», los ajustes y modos de fusión por capa
y «Quitar fondo». python -m pruebas.diseno_pro"""
import base64
import os
import re
import tempfile
import time
import tracemalloc
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")  # los textos que se comprueban están en español
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QShortcut  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea, QToolButton  # noqa: E402

from motor import claves, diseno, diseno_ia, ia, marca  # noqa: E402
from ui.comun import ESTILO  # noqa: E402
import ui.paginas.claves as pc  # noqa: E402
import ui.paginas.diseno as pd  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
diseno.asegurar_qt()
avisos, preguntas = [], []
QMessageBox.exec = lambda caja: avisos.append(caja.text()) or QMessageBox.Ok  # sin ventana no hay quien pulse
QMessageBox.question = staticmethod(lambda padre, titulo, texto, *a: preguntas.append(texto) or QMessageBox.Yes)


def parecido(color: QColor, hex_: str, margen: int = 12) -> bool:
    otro = QColor(hex_)
    return max(abs(color.red() - otro.red()), abs(color.green() - otro.green()),
               abs(color.blue() - otro.blue())) <= margen


def falla(funcion, *args, error=ValueError):
    try:
        funcion(*args)
    except error as e:
        return e
    raise AssertionError(f"debió fallar con {error.__name__}: {args!r:.200}")


def esperar(condicion, plazo=15):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def ilustracion(ruta: Path, fondo="#0F0F13", ancho=600, alto=400, color="#FFFFFF"):
    """Como las que pide la app: un círculo sobre fondo liso, con un punto del color del fondo dentro."""
    imagen = QImage(ancho, alto, QImage.Format_RGB32)
    imagen.fill(QColor(fondo))
    p = QPainter(imagen)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(ancho / 2, alto / 2), alto * 0.375, alto * 0.375)
    p.setBrush(QColor(fondo))
    p.drawEllipse(QPointF(ancho / 2, alto / 2), alto * 0.075, alto * 0.075)
    p.end()
    assert imagen.save(str(ruta))
    return ruta


def plano(colores, ancho=200, alto=200) -> QImage:
    """Una imagen con franjas verticales de esos colores."""
    imagen = QImage(ancho, alto, QImage.Format_RGB32)
    p = QPainter(imagen)
    for n, c in enumerate(colores):
        p.fillRect(round(n * ancho / len(colores)), 0, round(ancho / len(colores)) + 1, alto, QColor(c))
    p.end()
    return imagen


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    diseno.CARPETA = d / "disenos"  # nada de tocar datos/ de verdad
    marca.ARCHIVO, marca.CARPETA_LOGO = d / "marca.json", d / "marca"
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"  # ni se leen ni se tocan las claves
    carpeta = diseno.nueva_carpeta("Pro")

    # ---------- Campos nuevos: con su valor por defecto (los diseños viejos siguen igual) y validados ----------
    viejo = diseno.validar({"capas": [{"tipo": "imagen", "archivo": "a.png"}, {"tipo": "texto"}]})
    assert {k: viejo["capas"][0][k] for k in ("fusion", *diseno.AJUSTES)} == {
        "fusion": "normal", "brillo": 0, "contraste": 0, "saturacion": 0, "desenfoque": 0}
    assert viejo["capas"][1]["fusion"] == "normal" and "brillo" not in viejo["capas"][1]  # ajustes: solo las imágenes
    for campo, malo in (("fusion", "xor"), ("fusion", ""), ("fusion", None), ("brillo", 101), ("brillo", True),
                        ("contraste", -101), ("saturacion", float("nan")), ("desenfoque", -1), ("desenfoque", 101),
                        ("desenfoque", "5")):
        falla(diseno.validar, {"capas": [{"tipo": "imagen", "archivo": "a.png", campo: malo}]})
    assert set(diseno.FUSIONES) == set(pd.FUSIONES)  # lo que ofrece la pantalla es lo que pinta el motor
    # Cada capa con fusión se pinta aparte como imagen (80 a lienzo completo: 2 s por repintado): tienen tope
    fundidas = [{"tipo": "forma", "fusion": "multiplicar"}] * diseno.MAX_FUSIONES + [{"tipo": "forma"}] * 20
    assert len(diseno.validar({"capas": fundidas})["capas"]) == diseno.MAX_FUSIONES + 20
    e = falla(diseno.validar, {"capas": fundidas + [{"tipo": "texto", "fusion": "trama"}]})
    assert f"hasta {diseno.MAX_FUSIONES} capas con fusión" in str(e)

    # ---------- Ajustes de imagen (numpy) ----------
    gris = plano(["#808080"])
    assert parecido(diseno.ajustar_imagen(gris, brillo=100).pixelColor(5, 5), "#FFFFFF", 2)
    assert parecido(diseno.ajustar_imagen(gris, brillo=-100).pixelColor(5, 5), "#000000", 2)
    assert parecido(diseno.ajustar_imagen(gris).pixelColor(5, 5), "#808080", 1)  # 0 = sin cambio
    rojo = plano(["#C83232"])
    assert parecido(diseno.ajustar_imagen(rojo, saturacion=-100).pixelColor(5, 5), "#5F5F5F", 2)  # gris de su luz
    mas = diseno.ajustar_imagen(rojo, contraste=50).pixelColor(5, 5)
    assert mas.red() > 0xC8 and mas.green() < 0x32  # más contraste: lo claro más claro y lo oscuro más oscuro
    menos = diseno.ajustar_imagen(rojo, contraste=-100).pixelColor(5, 5)
    assert 0x80 < menos.red() < 0xC8 and 0x32 < menos.green() < 0x80
    # Desenfoque: el borde entre dos colores se mezcla, y los lados no se oscurecen (borde repetido)
    for radio in (1, 2, 8, 40):  # pequeño: a su tamaño; grande: en pequeño y ampliado
        borroso = diseno.ajustar_imagen(plano(["#FF0000", "#0000FF"]), radio=radio)
        assert borroso.size().toTuple() == (200, 200)
        centro = borroso.pixelColor(100, 100)
        assert centro.red() > 40 and centro.blue() > 40, (radio, centro.name())
        assert parecido(borroso.pixelColor(0, 100), "#FF0000", 30)
        assert parecido(borroso.pixelColor(199, 5), "#0000FF", 30)
    assert parecido(diseno.ajustar_imagen(plano(["#FF0000", "#0000FF"]), radio=1).pixelColor(20, 100), "#FF0000", 1)
    # Lo transparente no mete su color (negro) en el borde desenfocado
    suelto = QImage(100, 100, QImage.Format_ARGB32)
    suelto.fill(Qt.transparent)
    pintor = QPainter(suelto)
    pintor.fillRect(25, 25, 50, 50, QColor("#FFFFFF"))
    pintor.end()
    filo = diseno.ajustar_imagen(suelto, radio=6).pixelColor(25, 50)
    assert 0 < filo.alpha() < 255 and parecido(filo, "#FFFFFF", 3), filo.getRgb()

    # ---------- Una capa imagen con ajustes, en el lienzo y en lo exportado ----------
    foto = carpeta / "imagenes" / "foto.png"
    assert plano(["#FF0000", "#0000FF"], 400, 200).save(str(foto))
    con_ajustes = {"ancho": 400, "alto": 200, "fondo": {"tipo": "color", "colores": ["#FFFFFF"]},
                   "capas": [{"tipo": "imagen", "archivo": "foto.png", "x": 0, "y": 0, "ancho": 400, "alto": 200,
                              "brillo": 50}]}
    png = QImage(str(diseno.exportar(con_ajustes, carpeta, d / "brillo.png")))
    assert png.pixelColor(50, 100).green() > 40 and png.pixelColor(50, 100).red() == 255  # el rojo, más claro
    borrosa = {**con_ajustes, "capas": [{**con_ajustes["capas"][0], "brillo": 0, "desenfoque": 30}]}
    png = QImage(str(diseno.exportar(borrosa, carpeta, d / "borroso.png", "png", 2)))
    assert png.size().toTuple() == (800, 400)
    assert png.pixelColor(400, 200).red() > 40 and png.pixelColor(400, 200).blue() > 40  # mezclados en el medio
    # El lienzo repinta a menudo: con la misma escala y los mismos ajustes, la imagen ajustada no se rehace
    escena = diseno.escena(con_ajustes, carpeta)
    item = next(i for i in escena.items() if isinstance(i, diseno.ItemCapa) and i.data(0))
    lienzo = QImage(200, 100, QImage.Format_ARGB32_Premultiplied)
    for _ in range(2):
        p = QPainter(lienzo)
        escena.render(p)
        p.end()
        if _ == 0:
            hecha = item._ajustada[1]
            assert hecha.width() <= 200  # a los píxeles con que se ve (la mitad), no a los de la foto
    assert item._ajustada[1] is hecha
    item.aplicar({**item._capa, "brillo": 20})
    p = QPainter(lienzo)
    escena.render(p)
    p.end()
    assert item._ajustada[1] is not hecha
    # Con zoom, solo se calcula el trozo que se ve (antes, la foto entera en cada tick: 640 ms con zoom 4), en su sitio
    assert plano(["#FF0000", "#0000FF"], 2000, 1000).save(str(carpeta / "imagenes" / "grande.png"))

    def vista(tamano=(200, 100), dpr=1, origen=QRectF(175, 80, 50, 25), **ajustes):
        """El diseño con la foto de 2000 px pintado en una imagen de `tamano` px (por defecto, el centro con zoom ×4)
        y la imagen ajustada que calculó la capa."""
        capa = {**con_ajustes["capas"][0], "archivo": "grande.png", "brillo": 0, **ajustes}
        escena = diseno.escena({**con_ajustes, "capas": [capa]}, carpeta)
        imagen = QImage(*tamano, QImage.Format_ARGB32_Premultiplied)
        imagen.setDevicePixelRatio(dpr)
        imagen.fill(Qt.white)
        p = QPainter(imagen)
        escena.render(p, QRectF(0, 0, tamano[0] / dpr, tamano[1] / dpr), origen)
        p.end()
        return imagen, next(i for i in escena.items() if i.data(0))._ajustada[1]

    def raya(imagen):  # la primera columna que ya no es roja
        return next(x for x in range(imagen.width()) if imagen.pixelColor(x, imagen.height() // 2).red() < 128)
    normal, _ = vista()
    con_brillo, ajustada = vista(brillo=1)
    assert ajustada.width() <= 210 and ajustada.height() <= 110, ajustada.size()  # no 1600 × 800
    assert 95 <= raya(normal) <= 105 and abs(raya(con_brillo) - raya(normal)) <= 1
    # En una pantalla al 200 % (HiDPI), a sus píxeles reales: no a la mitad y ampliada (borrosa)
    _, ajustada = vista((800, 400), 2, QRectF(0, 0, 400, 200), brillo=1)
    assert ajustada.size().toTuple() == (800, 400), ajustada.size()

    # ---------- Modos de fusión, en el PNG, el JPG, el PDF y el SVG ----------
    def con_fusion(fusion, encima=True, opacidad=1):
        capas = [{"tipo": "forma", "x": 50, "y": 50, "ancho": 100, "alto": 100, "relleno": "#00FF00",
                  "fusion": fusion, "opacidad": opacidad}]
        if encima:  # una capa normal por encima de la que se funde: no se funde
            capas.append({"tipo": "forma", "x": 0, "y": 0, "ancho": 40, "alto": 40, "relleno": "#00FF00"})
        return {"ancho": 200, "alto": 200, "fondo": {"tipo": "color", "colores": ["#FF0000"]}, "capas": capas}

    for fusion, esperado in (("normal", "#00FF00"), ("multiplicar", "#000000"), ("trama", "#FFFF00"),
                             ("aclarar", "#FFFF00"), ("oscurecer", "#000000"), ("superponer", "#FF0000")):
        for formato in ("png", "jpg"):
            hecho = QImage(str(diseno.exportar(con_fusion(fusion), carpeta, d / f"f-{fusion}.{formato}", formato)))
            centro = hecho.pixelColor(100, 100)
            assert parecido(centro, esperado, 20), (fusion, formato, centro.name())
            assert parecido(hecho.pixelColor(20, 20), "#00FF00", 20)  # la de encima, normal
            assert parecido(hecho.pixelColor(190, 190), "#FF0000", 20)
    a_medias = QImage(str(diseno.exportar(con_fusion("multiplicar", opacidad=0.5), carpeta, d / "medias.png")))
    assert parecido(a_medias.pixelColor(100, 100), "#800000", 20)  # la opacidad cuenta también al fundir

    def pdf_a_imagen(ruta):
        doc = QPdfDocument()
        doc.load(str(ruta))
        return doc.render(0, doc.pagePointSize(0).toSize() * 2)

    def svg_a_imagen(ruta):
        imagen = QImage(200, 200, QImage.Format_ARGB32)
        imagen.fill(Qt.white)
        p = QPainter(imagen)
        QSvgRenderer(str(ruta)).render(p)
        p.end()
        return imagen

    for formato, a_imagen in (("pdf", pdf_a_imagen), ("svg", svg_a_imagen)):
        normal = diseno.exportar(con_fusion("normal"), carpeta, d / f"normal.{formato}", formato)
        fundido = diseno.exportar(con_fusion("multiplicar"), carpeta, d / f"fundido.{formato}", formato)
        imagen = a_imagen(fundido)
        w, h = imagen.width(), imagen.height()
        assert parecido(imagen.pixelColor(w // 2, h // 2), "#000000", 20), formato
        assert parecido(imagen.pixelColor(w // 10, h // 10), "#00FF00", 20)  # lo de encima, en vectores
        assert parecido(imagen.pixelColor(w - 3, h - 3), "#FF0000", 20)
        # Sin fusión, todo en vectores (sin imagen dentro); con fusión, la parte de abajo va como imagen
        sin, con = normal.read_bytes(), fundido.read_bytes()
        if formato == "pdf":
            assert b"/Subtype /Image" not in sin and b"/Subtype /Image" in con
            assert b"/Width 400" in con  # al doble del diseño: a 300 ppp, como las sombras
        else:
            assert b"<image" not in sin and b"<image" in con and (b"<path" in con or b"<rect" in con)
        assert parecido(a_imagen(normal).pixelColor(w // 2, h // 2), "#00FF00", 20)

    # ---------- Quitar fondo (gratis, en el PC) ----------
    sin_fondo = diseno.quitar_fondo(ilustracion(d / "ilu.png"), d / "sin_fondo.png")
    hecha = QImage(str(sin_fondo))
    assert hecha.hasAlphaChannel() and hecha.size().toTuple() == (600, 400)
    assert hecha.pixelColor(3, 3).alpha() == 0 and hecha.pixelColor(596, 396).alpha() == 0  # el fondo, fuera
    assert hecha.pixelColor(300, 120).alpha() == 255 and parecido(hecha.pixelColor(300, 120), "#FFFFFF", 2)
    assert hecha.pixelColor(300, 200).alpha() == 255  # el punto del color del fondo, dentro del dibujo, se queda
    filo = [hecha.pixelColor(x, 200) for x in range(140, 160)]  # el borde del círculo: suave y sin halo oscuro
    assert any(0 < c.alpha() < 255 for c in filo), [c.alpha() for c in filo]
    assert all(c.lightness() > 200 for c in filo if c.alpha() > 30), [c.name() for c in filo]
    # Una ilustración grande (sobre fondo claro) también, deprisa y sin llenar la memoria (antes, 2 GB con una 4K)
    inicio = time.monotonic()
    tracemalloc.start()
    grande = QImage(str(diseno.quitar_fondo(ilustracion(d / "grande.jpg", "#F4F1EA", 2048, 2048, "#7C5CFF"),
                                            d / "grande.png")))
    pico = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert grande.pixelColor(10, 10).alpha() == 0 and grande.pixelColor(1024, 500).alpha() == 255
    assert time.monotonic() - inicio < 30 and pico < 200 * 1024 ** 2, pico
    # Sin memoria para tanto: un aviso claro, no un error vacío
    crecer_real, diseno._crecer = diseno._crecer, lambda *a: (_ for _ in ()).throw(MemoryError())
    try:
        e = falla(diseno.quitar_fondo, d / "ilu.png", d / "x.png", error=RuntimeError)
    finally:
        diseno._crecer = crecer_real
    assert "memoria" in str(e) and not (d / "x.png").exists()
    # Un dibujo claro sobre blanco (o uno oscuro sobre negro) no pierde opacidad ni color en su filo
    for color, fondo in (("#FFE0B0", "#FFFFFF"), ("#F2D16B", "#FFFFFF"), ("#303030", "#000000")):
        claro = QImage(1024, 1024, QImage.Format_RGB32)
        claro.fill(QColor(fondo))
        pintor = QPainter(claro)
        pintor.fillRect(256, 256, 512, 512, QColor(color))  # sin suavizar: el filo es de un píxel
        pintor.end()
        assert claro.save(str(d / "claro.png"))
        hecha = QImage(str(diseno.quitar_fondo(d / "claro.png", d / "claro_sin.png")))
        assert hecha.pixelColor(250, 512).alpha() == 0 and hecha.pixelColor(255, 512).alpha() == 0
        dentro = [hecha.pixelColor(x, 512) for x in range(256, 270)]
        assert all(c.alpha() == 255 and parecido(c, color, 2) for c in dentro), (color, [c.alpha() for c in dentro])
    # Una foto (fondo de varios colores): aviso claro, no un recorte malo; sin fondo ya: tampoco
    assert plano(["#FF0000", "#00FF00", "#0000FF"]).save(str(d / "foto3.png"))
    e = falla(diseno.quitar_fondo, d / "foto3.png", d / "x.png", error=diseno.FondoNoLiso)
    assert "no es liso" in str(e) and not (d / "x.png").exists()
    e = falla(diseno.quitar_fondo, sin_fondo, d / "x.png")
    assert not isinstance(e, diseno.FondoNoLiso) and "ya no tiene fondo" in str(e)
    assert diseno.ruta_imagen(carpeta, "foto.png") == foto.resolve() and diseno.ruta_imagen(carpeta, "no.png") is None

    # ---------- La IA que diseña: una de las de texto; en «auto», la misma que escribe los guiones ----------
    assert claves.para("diseno") is None and claves.opciones("diseno") == ["auto"]  # sin claves: la IA gratis
    claves.guardar({"proveedor": "groq", "clave": "gsk_x", "usos": ["texto"]})
    claves.guardar({"proveedor": "anthropic", "clave": "sk-ant-x", "usos": ["texto"]})
    claves.guardar({"proveedor": "cloudflare", "clave": "c t", "usos": ["imagen"]})
    assert claves.opciones("diseno") == ["auto", "anthropic", "groq"]  # solo IA de texto
    claves.elegir_por_defecto("texto", "groq")
    assert claves.para("diseno")["proveedor"] == "groq"  # «auto»: la de los guiones, también si se eligió una
    claves.elegir_por_defecto("diseno", "anthropic")
    assert claves.para("diseno")["proveedor"] == "anthropic" and claves.para("texto")["proveedor"] == "groq"
    claves.borrar("anthropic")
    assert "diseno" not in claves.ajustes() and claves.para("diseno")["proveedor"] == "groq"  # vuelve a «auto»
    usos, gratis_real, para_real = [], ia._texto_gratis, claves.para
    ia._texto_gratis = lambda instrucciones, pedido, esquema: {"ok": True}
    claves.para = lambda uso: usos.append(uso)  # sin clave: se va a lo gratis
    try:
        assert ia.texto_json("i", "p", {"type": "object"}, uso="diseno") == {"ok": True}
        ia.texto_json("i", "p", {"type": "object"})
        assert usos == ["diseno", "texto"]
    finally:
        ia._texto_gratis, claves.para = gratis_real, para_real

    # ---------- Editar con IA (ia.editar_imagen), sin red ----------
    class Contesta:
        def __init__(self, cuerpo):
            self.status_code, self.is_error, self.cuerpo, self.text = 200, False, cuerpo, ""

        def json(self):
            return self.cuerpo

        def raise_for_status(self):
            pass

    hecha_ia = d / "hecha_ia.png"
    assert plano(["#00AA00"], 64, 32).save(str(hecha_ia))
    pedidos = []

    def post(url, **k):
        enviada = (k["json"]["contents"][0]["parts"][0]["inline_data"]["data"] if "json" in k
                   else k["files"]["image"][1].read())
        pedidos.append((url, k.get("json") or k.get("data"), enviada))
        datos = base64.b64encode(hecha_ia.read_bytes()).decode()
        return Contesta({"candidates": [{"content": {"parts": [{"inlineData": {"data": datos}}]}}]} if "json" in k
                        else {"data": [{"b64_json": datos}]})

    grande_foto = d / "grande_foto.jpg"
    assert plano(["#FF0000", "#0000FF"], 3000, 1500).save(str(grande_foto))
    post_real, para_real = ia.httpx.post, claves.para
    try:
        claves.para = lambda uso: None  # sin IA de imágenes con referencia
        e = falla(ia.editar_imagen, grande_foto, "ponle gorra roja", d / "e.png", error=ia.SinClave)
        assert str(e) == ia.SIN_REFERENCIA and "Gemini, OpenAI o Pollinations" in str(e)
        ia.httpx.post = post
        claves.para = lambda uso: {"proveedor": "gemini", "clave": "AIzaPrueba"}
        ia._elegidos[("AIzaPrueba", claves.elegir_modelo_imagen_gemini)] = ia.IMAGEN_GEMINI  # sin preguntar a la red
        for vacia in ("", "   ", None):
            falla(ia.editar_imagen, grande_foto, vacia, d / "e.png")
        assert pedidos == []
        assert ia.editar_imagen(grande_foto, "  ponle gorra roja\n y humo verde ", d / "e.png", "2K") == d / "e.png"
        url, cuerpo, enviada = pedidos[-1]
        assert url.endswith(f"/models/{ia.IMAGEN_GEMINI}:generateContent")
        texto = cuerpo["contents"][0]["parts"][1]["text"]
        assert "ponle gorra roja y humo verde" in texto and "keep everything else exactly the same" in texto
        assert cuerpo["generationConfig"]["imageConfig"] == {"aspectRatio": "16:9", "imageSize": "2K"}
        assert cuerpo["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"
        mandada = QImage.fromData(base64.b64decode(enviada))
        assert mandada.size().toTuple() == (2048, 1024)  # en PNG y como mucho 2048 px (el tope de Gemini es 20 MB)
        assert (d / "e.png").read_bytes() == hecha_ia.read_bytes() and not list(d.glob("e-original*"))
        claves.para = lambda uso: {"proveedor": "openai", "clave": "sk-x", "modelo_imagen": "gpt-image-1"}
        ia.editar_imagen(grande_foto, "ponle gorra", d / "o.png")
        url, datos, enviada = pedidos[-1]
        assert url == "https://api.openai.com/v1/images/edits" and datos["size"] == "1536x1024"
        assert "ponle gorra" in datos["prompt"] and enviada.startswith(b"\x89PNG")
        assert datos["quality"] == "medium"  # fija: con «auto» podía salir en alta, sin precio conocido
        # Vuelve en 2:3 (lo que da OpenAI a una foto vertical): se recorta al centro a la 4:5 de la foto, así la capa
        # no cambia de encuadre
        assert plano(["#00AA00"], 64, 96).save(str(hecha_ia))
        assert plano(["#FF0000"], 800, 1000).save(str(d / "vertical.png"))
        assert QImage(str(ia.editar_imagen(d / "vertical.png", "ponle gorra", d / "v.png"))).size().toTuple() == (64, 80)
        assert pedidos[-1][1]["size"] == "1024x1536"
        # Quitar el fondo con IA: le pide un fondo verde puro y luego lo quita aquí
        verde = d / "verde.png"
        ilustracion(verde, "#00FF00")
        editadas = []

        def editar_falso(foto_, instruccion, destino, calidad="1K"):
            editadas.append((foto_, instruccion, calidad))
            Path(destino).write_bytes(verde.read_bytes())
            return Path(destino)
        editar_real, ia.editar_imagen = ia.editar_imagen, editar_falso
        try:
            hecho = QImage(str(diseno_ia.quitar_fondo_con_ia(grande_foto, d / "con_ia.png", "2K")))
            assert editadas == [(grande_foto, diseno_ia.FONDO_VERDE, "2K")] and "#00FF00" in diseno_ia.FONDO_VERDE
            assert hecho.pixelColor(3, 3).alpha() == 0 and hecho.pixelColor(300, 120).alpha() == 255
            # Un busto (lo normal en las fotos): la cabeza y los hombros tocan abajo y los lados, así que menos del 70 %
            # del borde es verde. Ya se sabe que el fondo es verde: se quita igual
            retrato = QImage(800, 1000, QImage.Format_RGB32)
            retrato.fill(QColor("#00FF00"))
            pintor = QPainter(retrato)
            pintor.setRenderHint(QPainter.Antialiasing)
            pintor.setPen(Qt.NoPen)
            pintor.setBrush(QColor("#C68642"))
            pintor.drawEllipse(QPointF(400, 380), 170, 220)
            pintor.setBrush(QColor("#2B4C7E"))
            pintor.drawRoundedRect(QRectF(-10, 640, 820, 500), 160, 160)
            pintor.end()
            assert retrato.save(str(verde))
            falla(diseno.quitar_fondo, verde, d / "x.png", error=diseno.FondoNoLiso)  # sin saber el color, no
            hecho = QImage(str(diseno_ia.quitar_fondo_con_ia(grande_foto, d / "busto.png")))
            assert hecho.pixelColor(5, 5).alpha() == 0 and hecho.pixelColor(795, 600).alpha() == 0
            assert hecho.pixelColor(400, 380).alpha() == 255 and hecho.pixelColor(400, 990).alpha() == 255
            assert hecho.pixelColor(3, 990).alpha() == 255  # el hombro que toca el borde se queda
            # Si aun así no se puede (la IA no puso el verde), se dice dónde quedó la imagen ya pagada, y no «sin IA»
            assert plano(["#FF0000", "#00AAFF", "#0000FF"]).save(str(verde))
            e = falla(diseno_ia.quitar_fondo_con_ia, grande_foto, d / "pagada.png", error=RuntimeError)
            assert "ya pagada" in str(e) and str(d / "pagada.png") in str(e) and "sin IA" not in str(e)
            assert QImage(str(d / "pagada.png")).size().toTuple() == (200, 200)
        finally:
            ia.editar_imagen = editar_real
    finally:
        ia.httpx.post, claves.para = post_real, para_real
        ia._elegidos.clear()

    # ---------- La página «Claves de IA»: el selector «IA que diseña» ----------
    claves.ARCHIVO, claves.AJUSTES = d / "claves2.json", d / "ajustes2.json"
    pagina_claves = pc.PaginaClaves()
    combo = pagina_claves.selectores["diseno"]
    assert [combo.itemData(i) for i in range(combo.count())] == ["auto"]
    assert combo.itemText(0) == "La misma que escribe los guiones" and not pagina_claves.nota_diseno.isHidden()
    assert "Claude o ChatGPT diseñan mejor" in pagina_claves.nota_diseno.text()
    claves.guardar({"proveedor": "openai", "clave": "sk-x", "usos": ["texto", "imagen"]})
    claves.guardar({"proveedor": "groq", "clave": "gsk_x", "usos": ["texto"]})
    pagina_claves._refrescar()
    assert [combo.itemData(i) for i in range(combo.count())] == ["auto", "openai", "groq"]
    assert pagina_claves.nota_diseno.isHidden()  # con ChatGPT conectado, la nota sobra
    combo.setCurrentIndex(combo.findData("openai"))
    assert claves.ajustes()["diseno"] == "openai" and claves.para("diseno")["proveedor"] == "openai"
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"

    # ---------- La página «Diseño»: fusión, ajustes, Editar con IA y Quitar fondo ----------
    claves.ARCHIVO, claves.AJUSTES = d / "vacias.json", d / "ajustes_vacios.json"  # sin IA de imágenes
    p = pd.PaginaDiseno()
    p.resize(1280, 900)
    p.show()
    app.processEvents()
    p.anadir_texto()
    texto_id = p.diseno["capas"][-1]["id"]
    assert p.anadir_imagen(str(ilustracion(d / "para_capa.png")))
    capa = p.diseno["capas"][-1]
    original = capa["archivo"]
    fila = {nombre: next(f for f, campos in p.filas if campos == [nombre] or nombre in campos)
            for nombre in ("fusion", "brillo", "desenfoque", "archivo")}
    assert all(p.form.isRowVisible(f) for f in fila.values())  # imagen elegida: sus ajustes y sus botones
    panel = p.findChild(QScrollArea, "lateral")
    assert panel.widget().minimumSizeHint().width() <= panel.width(), panel.widget().minimumSizeHint()
    # Fusión: un «deshacer»
    p.w["fusion"].setCurrentIndex(p.w["fusion"].findData("multiplicar"))
    assert capa["fusion"] == "multiplicar" and isinstance(p.elegido()[0].graphicsEffect(), diseno._Efecto)
    p.deshacer()
    capa = p.diseno["capas"][-1]
    assert capa["fusion"] == "normal" and p.elegido()[0].graphicsEffect() is None
    # Ajustes: arrastrar el deslizador es un solo «deshacer»; el botón los quita todos de una vez
    pila = len(p.deshacer_pila)
    for v in (10, 20, 35):
        p.w["brillo"].setValue(v)
    p.w["desenfoque"].setValue(4)
    capa = p.diseno["capas"][-1]
    assert (capa["brillo"], capa["desenfoque"]) == (35, 4) and len(p.deshacer_pila) == pila + 2
    assert p.w["brillo"].toolTip() == "35"
    next(b for b in p.findChildren(QToolButton) if b.toolTip() == "Quitar los ajustes de la imagen").click()
    assert all(capa[k] == 0 for k in diseno.AJUSTES) and p.w["brillo"].value() == 0
    p.deshacer()
    assert p.diseno["capas"][-1]["brillo"] == 35 and p.w["brillo"].value() == 35
    # Un texto no tiene ajustes de imagen ni sus botones, pero sí fusión
    p.escena.clearSelection()
    next(i for i in p._items() if i.data(0) == texto_id).setSelected(True)
    assert p.form.isRowVisible(fila["fusion"]) and not p.form.isRowVisible(fila["brillo"])
    assert not p.form.isRowVisible(fila["archivo"])
    n = len(avisos)
    p.editar_con_ia()
    p.quitar_fondo()
    assert len(avisos) == n + 2 and all("capa de imagen" in a for a in avisos[n:])

    def elegir_imagen():
        p.escena.clearSelection()
        p._items()[0].setSelected(True)  # la imagen es la de arriba
        assert p.elegido()[1]["tipo"] == "imagen"

    # Editar con IA sin IA que edite fotos: dice qué conectar, sin preguntar nada ni gastar
    elegir_imagen()
    pedir_real, n, m = pd.pedir_cambio, len(avisos), len(preguntas)
    pd.pedir_cambio = lambda padre: (_ for _ in ()).throw(AssertionError("no debía preguntar"))
    p.editar_con_ia()
    assert avisos[n:] == [ia.SIN_REFERENCIA] and len(preguntas) == m
    # Con Gemini: el costo antes de gastar; con «No», no se gasta nada
    editadas = []

    def editar_falso(foto_, instruccion, destino, calidad="1K"):
        editadas.append((Path(foto_).name, instruccion, calidad))
        assert plano(["#FFAA00"], 300, 200).save(str(destino))
        return Path(destino)
    referencia_real, editar_real, para_real = pd.ia.puede_referencia, pd.ia.editar_imagen, pd.claves.para
    pd.ia.puede_referencia, pd.ia.editar_imagen = lambda: True, editar_falso
    pd.claves.para = lambda uso: {"proveedor": "gemini", "clave": "AIzaPrueba"}
    pd.pedir_cambio = lambda padre: "ponle gorra roja"
    QMessageBox.question = staticmethod(lambda padre, titulo, texto, *a: preguntas.append(texto) or QMessageBox.No)
    p.editar_con_ia()
    assert editadas == [] and "Cancelado" in p.estado.text()
    assert "ponle gorra roja" in preguntas[-1] and "US$0.07" in preguntas[-1], preguntas[-1]  # el precio más alto
    pd.claves.para = lambda uso: {"proveedor": "openai", "clave": "sk-x"}  # OpenAI: también con su importe
    p.editar_con_ia()
    assert editadas == [] and "US$0.08 con OpenAI (calidad media" in preguntas[-1], preguntas[-1]
    pd.claves.para = lambda uso: {"proveedor": "gemini", "clave": "AIzaPrueba"}
    QMessageBox.question = staticmethod(lambda padre, titulo, texto, *a: preguntas.append(texto) or QMessageBox.Yes)
    pila = len(p.deshacer_pila)
    p.editar_con_ia()
    esperar(lambda: p.disenar.isEnabled() and p.diseno["capas"][-1]["archivo"] != original)
    capa = p.diseno["capas"][-1]
    assert editadas == [(original, "ponle gorra roja", "1K")] and "editada" in p.estado.text()
    assert parecido(QImage(str(p.carpeta / "imagenes" / capa["archivo"])).pixelColor(5, 5), "#FFAA00", 2)
    assert len(p.deshacer_pila) == pila + 1 and p.elegido()[1] is capa  # un paso, y la capa sigue elegida
    editada = capa["archivo"]
    p.deshacer()
    assert p.diseno["capas"][-1]["archivo"] == original and (p.carpeta / "imagenes" / original).is_file()
    p.rehacer()
    assert p.diseno["capas"][-1]["archivo"] == editada
    p.deshacer()
    # Si la capa se borra mientras la IA trabaja, la imagen no se pierde: se dice dónde quedó
    elegir_imagen()
    p.editar_con_ia()
    p.borrar_capa()
    n = len(avisos)
    esperar(lambda: p.disenar.isEnabled() and len(avisos) > n)
    assert "quedó guardada en" in avisos[-1]
    Path(re.search(r"guardada en (.+)$", avisos[-1])[1]).unlink()
    p.deshacer()
    assert any(QKeySequence(a.key()) == QKeySequence("Ctrl+Shift+G") for a in p.findChildren(QShortcut))
    assert any(QKeySequence(a.key()) == QKeySequence("Ctrl+Shift+B") for a in p.findChildren(QShortcut))

    # Quitar fondo: liso, gratis y en segundo plano, que con una 4K tarda unos segundos (un «deshacer»)
    elegir_imagen()
    pila = len(p.deshacer_pila)
    p.quitar_fondo()
    assert not p.disenar.isEnabled() and p.diseno["capas"][-1]["archivo"] == original  # la ventana no se congela
    esperar(lambda: p.disenar.isEnabled())
    capa = p.diseno["capas"][-1]
    sin = QImage(str(p.carpeta / "imagenes" / capa["archivo"]))
    assert capa["archivo"] != original and sin.hasAlphaChannel() and sin.pixelColor(2, 2).alpha() == 0
    assert len(p.deshacer_pila) == pila + 1 and "transparente" in p.estado.text()
    p.deshacer()
    assert p.diseno["capas"][-1]["archivo"] == original
    # Una foto: con IA (le pide un fondo verde y lo quita), avisando antes del costo
    elegir_imagen()
    assert p.anadir_imagen(str(d / "foto3.png"))
    foto_id, archivo_foto = p.diseno["capas"][-1]["id"], p.diseno["capas"][-1]["archivo"]
    con_ia = []
    quitar_real = diseno_ia.quitar_fondo_con_ia

    def quitar_falso(foto_, destino, calidad="1K"):
        con_ia.append(calidad)
        return diseno.quitar_fondo(ilustracion(Path(destino), "#00FF00"), destino)
    diseno_ia.quitar_fondo_con_ia = quitar_falso
    m = len(preguntas)
    p.quitar_fondo()
    esperar(lambda: len(preguntas) > m)
    assert "no es liso" in preguntas[m] and "verde" in preguntas[m] and "US$" in preguntas[m]
    esperar(lambda: p.disenar.isEnabled() and con_ia)
    assert next(c for c in p.diseno["capas"] if c["id"] == foto_id)["archivo"] != archivo_foto
    # Sin IA que edite fotos: lo dice, con lo que hay que conectar
    pd.ia.puede_referencia = lambda: False
    p.deshacer()
    elegir_imagen()
    n = len(avisos)
    p.quitar_fondo()
    esperar(lambda: p.disenar.isEnabled() and len(avisos) > n)
    assert "no es liso" in avisos[-1] and ia.SIN_REFERENCIA in avisos[-1] and len(con_ia) == 1
    diseno_ia.quitar_fondo_con_ia = quitar_real
    pd.ia.puede_referencia, pd.ia.editar_imagen, pd.claves.para, pd.pedir_cambio = (referencia_real, editar_real,
                                                                                     para_real, pedir_real)
    p.sucio = False

    # ---------- Sigue cabiendo a 1366, 1280 y 1152 px de ancho, con una imagen elegida ----------
    import app as aplicacion
    ventana = aplicacion.Ventana()
    ventana.ir_a(ventana.orden.index(ventana.diseno))
    ventana.diseno.anadir_imagen(str(d / "ilu.png"))
    ventana.show()
    for ancho in (1366, 1280, 1152):
        ventana.resize(ancho, 728)
        app.processEvents()
        assert ventana.paginas.currentWidget().horizontalScrollBar().maximum() == 0, ancho
        lateral = ventana.diseno.findChild(QScrollArea, "lateral")
        assert lateral.widget().minimumSizeHint().width() <= lateral.width(), ancho
    ventana.diseno.sucio = False
    assert ventana.close()
# Quitar fondo: un dibujo claro con contorno oscuro fino (lo típico de un dibujo animado) no queda con un anillo
# translúcido por dentro del contorno, a ningún tamaño
carpeta_fondo = Path(tempfile.mkdtemp(prefix="rafaga-fondo-"))
for lado_img, grosor in ((1024, 2), (2048, 3), (4096, 6)):
    dibujo = QImage(lado_img, lado_img, QImage.Format_RGB32)
    dibujo.fill(QColor("#FFFFFF"))
    pintor = QPainter(dibujo)
    c = lado_img // 4
    pintor.fillRect(c, c, lado_img // 2, lado_img // 2, QColor("#1A1A1A"))
    pintor.fillRect(c + grosor, c + grosor, lado_img // 2 - 2 * grosor, lado_img // 2 - 2 * grosor, QColor("#FFE0B0"))
    pintor.end()
    dibujo.save(str(carpeta_fondo / "o.png"))
    diseno.quitar_fondo(carpeta_fondo / "o.png", carpeta_fondo / "s.png")
    sin_fondo = QImage(str(carpeta_fondo / "s.png")).convertToFormat(QImage.Format_ARGB32)
    for k in range(4):  # justo dentro del contorno: el relleno, opaco y de su color
        punto = sin_fondo.pixelColor(c + grosor + 1 + k, lado_img // 2)
        assert punto.alpha() == 255 and punto.name() == "#ffe0b0", (lado_img, k, punto.name(), punto.alpha())
    assert sin_fondo.pixelColor(5, 5).alpha() == 0
print("Pruebas de Diseño Pro pasadas.")
