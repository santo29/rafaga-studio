"""Pruebas de la IA diseñadora (motor/diseno_ia.py y la herramienta MCP crear_diseno), sin red ni claves: la IA de
texto y la de imágenes se sustituyen. python -m pruebas.diseno_ia"""
import asyncio
import copy
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import httpx  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402

from motor import claves, conexion_mcp, diseno, diseno_ia, ia, marca, nubes, recursos, seguro  # noqa: E402

diseno.asegurar_qt()
respuesta, pedidos, fotos, calidades = {}, [], [], []
imagen_real = ia.imagen


def texto_json(instrucciones, pedido, esquema, uso="texto", rapido=False):
    assert esquema is diseno_ia.ESQUEMA and "PORCENTAJE" in instrucciones
    assert uso == "diseno"  # la «IA que diseña» de Claves de IA, no la de los guiones
    assert rapido == ("Pieza: foto." in pedido)  # los diseños piensan antes; una foto es solo su prompt
    pedidos.append(pedido)
    return copy.deepcopy(respuesta)


CUENTA = "0123456789abcdef0123456789abcdef"  # el ID de la cuenta de Cloudflare va en la URL de sus errores


def imagen(prompt, ancho, alto, destino, calidad="1K"):
    fotos.append((prompt, ancho, alto))
    calidades.append(calidad)
    if "FALLA429" in prompt:
        raise RuntimeError("Ninguna opción pudo hacerlo.\nCloudflare: Client error '429 Too Many Requests' for url "
                           f"'https://api.cloudflare.com/client/v4/accounts/{CUENTA}/ai/run/@cf/flux' — {CUENTA}")
    if "FALLA" in prompt:
        raise RuntimeError("Ninguna opción pudo hacerlo.\nservicio caído")
    foto = QImage(ancho, alto, QImage.Format_RGB32)
    foto.fill(QColor("#00AA00"))
    if "HUMO" in prompt:  # humo claro que llega al borde de abajo, como en el arte oscuro con neón
        foto.fill(QColor("#06041A"))
        for y in range(alto * 3 // 4, alto):
            for x in range(ancho):
                foto.setPixelColor(x, y, QColor("#5A4A8C"))
    assert foto.save(str(destino))
    return destino


ia.texto_json, ia.imagen = texto_json, imagen


def capa(**campos):
    """Una capa como la manda la IA: todos los campos, los que no usa en «vacío»."""
    return {"tipo": "texto", "x": 10, "y": 10, "ancho": 80, "alto": 20, "texto": "", "fuente": "", "tamano": 0,
            "color": "", "negrita": False, "alineacion": "centro", "sombra": False, "forma": "rectangulo",
            "redondeo": 0, "opacidad": 100, "icono": "", "prompt_imagen": "", **campos}


def crear(capas, tipo="post", usar_marca=True, pedido="Anuncio de pizza 2x1", estilo="auto", **arriba):
    respuesta.clear()
    respuesta.update({"titulo": "Prueba", "descripcion": "Texto para publicar", "fondo_colores": ["#0F0F13"],
                      "fondo_prompt_imagen": "", "capas": capas, **arriba})
    pedidos.clear()
    fotos.clear()
    return diseno_ia.crear(pedido, tipo, usar_marca, estilo=estilo)


def dentro(r):
    d = r["diseno"]
    for c in d["capas"]:
        assert 0 <= c["x"] and c["x"] + c["ancho"] <= d["ancho"] and 0 <= c["y"] and c["y"] + c["alto"] <= d["alto"], c


def falla(funcion, *args, error=ValueError):
    try:
        funcion(*args)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar con {error.__name__}: {args!r:.200}")


def textos(r):
    return [c for c in r["diseno"]["capas"] if c["tipo"] == "texto"]


def cabe(r):
    """Cada texto cabe en su caja, medido con el texto del editor (el que se dibuja y se exporta)."""
    for c in textos(r):
        item = diseno.ItemCapa(c, Path(r["carpeta"]))  # guardado: si no, Qt borra el texto hijo
        alto = item.texto.boundingRect().height() - c["tamano"] / 2
        assert alto <= c["alto"] + 0.5, (c["texto"][:20], alto, c["alto"])


# ---------- El esquema: plano y estricto ----------
def estricto(e):
    if e.get("type") == "object":
        assert e["additionalProperties"] is False and set(e["required"]) <= set(e["properties"]), e
        for sub in e["properties"].values():
            estricto(sub)
    elif e.get("type") == "array":
        estricto(e["items"])


estricto(diseno_ia.ESQUEMA)
items = diseno_ia.ESQUEMA["properties"]["capas"]["items"]
campos_capa = items["properties"]
assert set(diseno_ia.ESQUEMA["required"]) == set(diseno_ia.ESQUEMA["properties"])
assert items["required"] == ["tipo", "x", "y", "ancho", "alto"]  # de una capa, solo la caja es obligatoria
assert all(p["type"] in ("string", "number", "boolean") for p in campos_capa.values())  # plano: nada anidado
assert set(capa()) == set(campos_capa)
# Las IA pequeñas no mandan los campos que su tipo no usa: la respuesta vale igual (antes se rechazaba entera y la
# IA gratis repetía 4 veces); una capa sin caja sí se quita
corta = ia._validar({"titulo": "x", "descripcion": "", "fondo_colores": ["#000000"], "fondo_prompt_imagen": "",
                     "capas": [{"tipo": "texto", "x": 10, "y": 10, "ancho": 80, "alto": 20, "texto": "Hola"},
                               {"tipo": "icono", "x": 5, "y": 5, "ancho": 8, "alto": 8, "icono": "phone"},
                               {"tipo": "texto", "texto": "sin caja"}]}, diseno_ia.ESQUEMA)
assert corta is not None and [c["tipo"] for c in corta["capas"]] == ["texto", "icono"]
assert "PORCENTAJE" in diseno_ia.INSTRUCCIONES and "nunca píxeles" in diseno_ia.INSTRUCCIONES
assert all(t in diseno.TAMANOS for t, _ in diseno_ia.TIPOS.values())
assert set(diseno_ia.TIPOS) == {"anuncio", "post", "historia", "miniatura", "flyer", "logo", "tarjeta",
                                "marca_personal", "presentacion", "ilustracion", "foto", "estampado"}
# Diseño gráfico y no fotos: ni «nivel Canva» ni «fotográfico»; la regla común de faltas y la de no inventar datos
assert set(diseno_ia.ESTILOS) == {"auto", "vector", "sticker", "tatuaje", "poster", "grabado", "render3d",
                                  "neon_oscuro", "animado3d", "urbano", "foto"}
assert diseno_ia.ESTILOS["auto"] == "" and all(v for k, v in diseno_ia.ESTILOS.items() if k != "auto")
assert not any(p in v for k, v in diseno_ia.ESTILOS.items() if k != "foto" for p in ("photo", "realistic"))
# Los estilos 3D y de arte digital: luz volumétrica, sin marcas (Pixar, Octane, Unreal) y los oscuros sin sangre
assert all("volumetric" in diseno_ia.ESTILOS[e] for e in ("render3d", "neon_oscuro", "urbano"))
assert not any(m in v.lower() for v in diseno_ia.ESTILOS.values() for m in ("pixar", "disney", "octane", "unreal"))
assert all(diseno_ia.ESTILOS[e].endswith("no gore") for e in ("neon_oscuro", "urbano"))
assert all(e in diseno_ia.INSTRUCCIONES_ENTENDER for e in diseno_ia.ESTILOS if e != "auto")  # la IA los conoce
for instrucciones in (diseno_ia.INSTRUCCIONES, diseno_ia.INSTRUCCIONES_ENTENDER):
    assert diseno_ia.FALTAS in instrucciones and "«abla» → habla" in instrucciones
assert "Canva" not in diseno_ia.INSTRUCCIONES and "fotográfico" not in diseno_ia.INSTRUCCIONES
assert "No inventes datos" in diseno_ia.INSTRUCCIONES and "[Precio]" in diseno_ia.INSTRUCCIONES
assert "foto protagonista" not in diseno_ia.TIPOS["anuncio"][1] and "sin fotos" not in diseno_ia.TIPOS["logo"][1]
estricto(diseno_ia.ESQUEMA_ENTENDER)
assert diseno_ia.ESQUEMA_ENTENDER["properties"]["tipo"]["enum"] == list(diseno_ia.TIPOS)
assert "auto" not in diseno_ia.ESQUEMA_ENTENDER["properties"]["estilo"]["enum"]

# ---------- Ningún dato inventado: precios, %, webs, @, teléfonos y correos que no trae el pedido ----------
sin_inventos = diseno_ia._sin_inventos
assert sin_inventos("Entrada 15 € · www.x.com · +34 600 123 456", "Concierto gótico") == \
    "Entrada [Precio] · [Web] · [Teléfono]"
assert sin_inventos("PIZZA 2x1", "pizza 2x1") == "PIZZA 2x1"
assert sin_inventos("Pieza artesanal con 30% OFF", "calavera") == "Pieza artesanal con [Precio] OFF"
assert sin_inventos("100% algodón", "camiseta") == "100% algodón"  # no es una oferta
assert sin_inventos("Escríbenos: hola@bar.com o @bar_santo", "bar") == "Escríbenos: [Contacto] o [Contacto]"
assert sin_inventos("santolapara.com · RD$500 · $5 · 12,50€ · 3 euros", "x") == \
    "[Web] · [Precio] · [Precio] · [Precio] · [Precio]"
assert sin_inventos("Llama al (809) 555-1234", "x") == "Llama al [Teléfono]"
# Lo que sí trae el pedido se queda, aunque lo escriba distinto (espacios, www, guiones)
assert sin_inventos("Entrada 15 € · www.x.com · 809-555-1234", "entrada 15€, web x.com, tel 809 555 1234") == \
    "Entrada 15 € · www.x.com · 809-555-1234"
assert sin_inventos("Sábado 20 a las 21:00 · 2026 · 1.500.000 likes", "x") == \
    "Sábado 20 a las 21:00 · 2026 · 1.500.000 likes"  # fechas, horas y cifras sueltas no son datos de contacto
# Horarios y miles con puntos tampoco son teléfonos; un teléfono con puntos sí
assert sin_inventos("Abierto 10.00 - 22.00", "pizzeria abierta de 10 a 22") == "Abierto 10.00 - 22.00"
assert sin_inventos("Más de 15.000.000 de vistas", "canal de youtube") == "Más de 15.000.000 de vistas"
assert sin_inventos("Llama al 809.555.1234", "x") == "Llama al [Teléfono]"
# Precios y teléfonos del pedido escritos de otra forma: se comparan sus cifras
assert sin_inventos("Pizza grande RD$500", "pizza grande a 500 pesos") == "Pizza grande RD$500"
assert sin_inventos("Entrada 15 €", "flyer fiesta, entrada 15 euros") == "Entrada 15 €"
assert sin_inventos("Entrada €15", "entrada 15€") == "Entrada €15"
assert sin_inventos("Total RD$1,500.00", "1500 pesos") == "Total RD$1,500.00"
assert sin_inventos("WhatsApp +1 809 555 1234", "whatsapp 809 555 1234") == "WhatsApp +1 809 555 1234"
assert sin_inventos("Tel. +34 600 123 456", "tel 600123456") == "Tel. +34 600 123 456"
# ...pero otras cifras siguen siendo inventos
assert sin_inventos("Pizza RD$5000 · 30% OFF", "pizza a 500 pesos") == "Pizza [Precio] · [Precio] OFF"
assert sin_inventos("WhatsApp 829 555 1234", "whatsapp 809 555 1234") == "WhatsApp [Teléfono]"

# Solo se quitan las palabras de estilo fotográfico, no el motivo (una fotógrafa, un estudio de fotos)
prompt_de = diseno_ia._prompt
assert prompt_de("a female photographer with a camera", "vector").startswith("a female photographer with a camera, ")
assert prompt_de("photography studio emblem, photographer silhouette", "auto", True, "#FFFFFF") == \
    "studio emblem, photographer silhouette, isolated on plain solid background #FFFFFF" + diseno_ia._SIN_TEXTO
assert prompt_de("photo-realistic skull, ultra-realistic photos", "vector") == \
    "skull, " + diseno_ia.ESTILOS["vector"] + diseno_ia._SIN_TEXTO

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    diseno.CARPETA = d / "disenos"  # nada de tocar datos/ de verdad
    marca.ARCHIVO, marca.CARPETA_LOGO = d / "marca.json", d / "marca"
    logo_png = d / "logo.png"
    logo = QImage(200, 200, QImage.Format_RGB32)
    logo.fill(QColor("#0000FF"))
    assert logo.save(str(logo_png))
    mia = {"nombre": "Pizzería Don Juan", "eslogan": "La mejor del barrio", "logo": marca.poner_logo(str(logo_png)),
           "colores": ["#123456", "#ABCDEF"], "fuente_titulo": "Bebas Neue", "fuente_texto": "Lora", "tono": "cercano"}
    marca.guardar(mia)

    # ---------- Respuesta buena ----------
    buena = [capa(tipo="imagen", x=0, y=40, ancho=100, alto=60, prompt_imagen="pepperoni pizza on a wooden table"),
             capa(tipo="forma", x=5, y=5, ancho=90, alto=30, color="#000000", opacidad=50, redondeo=10),
             capa(texto="PIZZA 2x1", x=10, y=8, ancho=80, alto=15, fuente="Bebas Neue", tamano=10, color="#FFFFFF",
                  negrita=True, sombra=True),
             capa(tipo="icono", x=5, y=85, ancho=8, alto=8, icono="phone", color="#FF4D8D"),
             capa(tipo="emoji", x=85, y=5, ancho=10, alto=10, texto="🍕"),
             capa(tipo="forma", forma="linea", x=10, y=36, ancho=80, alto=2, color="#FFFFFF")]
    assert ia._validar({"titulo": "x", "descripcion": "", "fondo_colores": ["#000000"], "fondo_prompt_imagen": "",
                        "capas": copy.deepcopy(buena)}, diseno_ia.ESQUEMA) is not None  # la IA gratis la acepta
    avisos_vistos = []
    respuesta.update({"titulo": "Pizza 2x1", "descripcion": "¡Ven hoy!", "fondo_colores": ["#0F0F13"],
                      "fondo_prompt_imagen": "", "capas": buena})
    r = diseno_ia.crear("Anuncio de pizza 2x1", "post", True, aviso=lambda t, f: avisos_vistos.append((t, f)))
    carpeta = Path(r["carpeta"])
    assert r["tipo"] == "diseno" and carpeta.parent == diseno.CARPETA and r["avisos"] == []
    assert (r["titulo"], r["descripcion"]) == ("Pizza 2x1", "¡Ven hoy!") and r["diseno"]["nombre"] == "Pizza 2x1"
    assert avisos_vistos[-1] == ("¡Listo!", 1.0) and all(0 <= f <= 1 for _, f in avisos_vistos)
    assert diseno.abrir(carpeta) == r["diseno"]  # guardado, y se abre con el editor
    assert (carpeta / "miniatura.png").is_file()
    vista = QImage(r["archivo"])
    assert Path(r["archivo"]) == carpeta / "vista_previa.png" and (vista.width(), vista.height()) == (1080, 1080)
    assert vista.pixelColor(540, 1000).green() > 120 and vista.pixelColor(540, 1000).red() < 60  # la foto verde
    capas = r["diseno"]["capas"]
    # Textos, iconos y emojis encima; formas y fotos con su orden (la línea iba después del texto)
    assert [c["tipo"] for c in capas] == ["imagen", "forma", "forma", "texto", "icono", "emoji", "imagen"]
    foto, caja, linea, titulo, icono, emoji, logo_capa = capas
    assert (foto["x"], foto["y"], foto["ancho"], foto["alto"]) == (0, 432, 1080, 648)
    assert fotos == [("pepperoni pizza on a wooden table" + diseno_ia._SIN_TEXTO, 1080, 648)]  # al tamaño de su caja
    assert "no text" in fotos[0][0] and (carpeta / "imagenes" / foto["archivo"]).is_file()
    assert caja["opacidad"] == 0.5 and caja["redondeo"] == 32 and caja["relleno"] == "#000000"
    assert titulo["fuente"] == "Bebas Neue" and titulo["sombra"] and titulo["color"] == "#FFFFFF"
    assert 50 < titulo["tamano"] <= 108 and titulo["alineacion"] == "centro"
    assert (icono["nombre"], icono["color"]) == ("phone", "#FF4D8D") and emoji["texto"] == "🍕"
    assert linea["forma"] == "linea" and linea["grosor_borde"] >= 2
    # El logo de la marca, abajo a la derecha y copiado dentro del diseño
    assert logo_capa["ajuste"] == "contener" and (carpeta / "imagenes" / logo_capa["archivo"]).is_file()
    assert (logo_capa["x"], logo_capa["y"], logo_capa["ancho"]) == (886, 886, 151)
    assert vista.pixelColor(960, 960).blue() > 200  # el logo azul se ve en la vista previa
    # El pedido lleva la marca, la zona del logo y el lienzo en % (nada de píxeles, que la IA copiaría) y las fuentes
    assert all(t in pedidos[0] for t in ("Pizzería Don Juan", "#123456", "Bebas Neue", "x 82 a 100 e y 82 a 100",
                                          "cuadrado, proporción 1:1", "alto = ancho × 1.00", "unas 15 letras",
                                          "Playfair Display", "Pedido: Anuncio de pizza 2x1"))
    assert "px" not in pedidos[0] and "1080" not in pedidos[0]
    dentro(r)
    cabe(r)
    jpg = diseno.exportar(r["diseno"], carpeta, d / "exportado.jpg", "jpg")
    assert QImage(str(jpg)).width() == 1080

    # Cada tipo sale con el tamaño de su lienzo; sin marca no va la marca ni el logo
    for tipo, (tamano, _) in diseno_ia.TIPOS.items():
        r = crear([capa(texto="Hola")], tipo, usar_marca=False)
        ancho, alto, _ = diseno.TAMANOS[tamano]
        assert (r["diseno"]["ancho"], r["diseno"]["alto"]) == (ancho, alto), tipo
        assert QImage(r["archivo"]).height() == alto and "Pizzería" not in pedidos[0]
        assert [c["tipo"] for c in r["diseno"]["capas"]] == ["texto"]
        assert r["diseno"]["capas"][0]["fuente"] == "Poppins"  # sin marca: las fuentes por defecto
    assert len(crear([capa(texto="Logo")], "logo")["diseno"]["capas"]) == 1  # a un logo no se le pone el logo

    # ---------- Capas fuera del lienzo y números imposibles ----------
    r = crear([capa(texto="Arriba", x=150, y=-20, ancho=300, alto=0),
               capa(tipo="forma", x=-50, y=95, ancho=30, alto=30, color="#FF0000"),
               capa(tipo="icono", icono="star", x=float("nan"), y="abc", ancho=float("inf"), alto=None),
               capa(tipo="emoji", texto="🔥", x=10 ** 400, y=-10 ** 400, ancho=[5], alto={"a": 1}, opacidad=0),
               capa(tipo="forma", x=99, y=99, ancho=50, alto=50, redondeo=1e9, opacidad=float("nan"))], "historia")
    dentro(r)
    forma, esquina, arriba, estrella, fuego, logo_capa = r["diseno"]["capas"]
    assert (arriba["x"], arriba["y"], arriba["ancho"]) == (0, 0, 1080) and arriba["alto"] >= 1
    assert (forma["x"], forma["y"], forma["ancho"], forma["alto"]) == (0, 1344, 324, 576)
    assert fuego["opacidad"] == 1 and esquina["opacidad"] == 1  # un 0 es «sin usar», no una capa invisible
    assert esquina["redondeo"] == 270  # 50 % del lado corto como mucho
    assert diseno.abrir(Path(r["carpeta"])) == r["diseno"]
    # En una historia el logo queda por encima del 15 % de abajo (los botones de la app), y el pedido lo dice en %
    assert logo_capa["y"] + logo_capa["alto"] <= 1920 * 0.85 and logo_capa["x"] == 886
    assert "x 82 a 100 e y 75 a 85" in pedidos[0] and "vertical, proporción 9:16" in pedidos[0]

    # ---------- Iconos, fuentes y tipos que no existen ----------
    r = crear([capa(tipo="icono", icono="no-existe-zzz"), capa(tipo="icono", icono="../claves"),
               capa(tipo="icono", icono=""), capa(tipo="icono", icono=None), capa(tipo="icono", icono="PHONE"),
               capa(tipo="icono", icono="Shopping Cart"), capa(tipo="icono", icono="telephone"),
               capa(texto="Negrita", fuente="Comic Sans MS", negrita=True), capa(texto="Normal", fuente="Arial"),
               capa(texto="Minúsculas", fuente="montserrat"), capa(texto="Ruta", fuente="../../fuente.ttf"),
               capa(tipo="video", texto="x"), capa(tipo=None), "hola", None, 5, capa(texto=""), capa(texto=None),
               capa(tipo="imagen", prompt_imagen=""), capa(tipo="emoji", texto="")])
    capas = r["diseno"]["capas"]
    nombres = [c["nombre"] for c in capas if c["tipo"] == "icono"]
    assert nombres[:2] == ["phone", "shopping-cart"] and len(nombres) <= 3
    assert all(n in recursos.iconos() for n in nombres) and fotos == []
    assert [c["fuente"] for c in capas if c["tipo"] == "texto"] == ["Bebas Neue", "Lora", "Montserrat", "Lora"]
    assert len(capas) == len(nombres) + 4 + 1  # + el logo de la marca

    # ---------- Colores raros ----------
    r = crear([capa(texto="A", color="nope", y=0, alto=15), capa(texto="B", color="yellow", y=20, alto=15),
               capa(texto="C", color="#fff", y=40, alto=15), capa(texto="D", color='#FFFFFF"/><script>', y=60, alto=15),
               capa(texto="E", color=None, y=80, alto=15),  # las formas, a un lado: el contraste se mide con el fondo
               capa(tipo="forma", color="rgb(1,2)", x=90, ancho=10),
               capa(tipo="forma", color=["#000000"], x=90, ancho=10),
               capa(tipo="icono", icono="star", color=12345)],
              fondo_colores=["azulito", '#FFFFFF"/><script>', 7])
    d1 = r["diseno"]
    assert d1["fondo"] == {"tipo": "color", "colores": ["#123456"], "imagen": ""}  # el color de la marca
    assert [c["color"] for c in d1["capas"] if c["tipo"] == "texto"] == ["#FFFFFF", "#FFFF00", "#FFFFFF", "#FFFFFF",
                                                                          "#FFFFFF"]  # contraste con el fondo oscuro
    assert [c["relleno"] for c in d1["capas"] if c["tipo"] == "forma"] == ["#ABCDEF", "#ABCDEF"]  # el acento
    assert d1["capas"][7]["color"] == "#FFFFFF"
    claro = crear([capa(texto="Sobre blanco", color="x")], fondo_colores=["#FAFAFA", "#EEEEEE", "#DDDDDD", "#000000"])
    assert claro["diseno"]["fondo"]["tipo"] == "degradado" and len(claro["diseno"]["fondo"]["colores"]) == 3
    assert claro["diseno"]["capas"][0]["color"] == "#111111"
    assert crear([capa(texto="x")], fondo_colores="no es lista")["diseno"]["fondo"]["colores"] == ["#123456"]
    assert crear([capa(texto="x")], usar_marca=False, fondo_colores=[])["diseno"]["fondo"]["colores"] == ["#0F0F13"]

    # ---------- 200 capas: se recorta (el gasto no lo decide la IA) ----------
    r = crear([capa(tipo="imagen", prompt_imagen=f"photo {i}") for i in range(100)]
              + [capa(texto=f"T{i}") for i in range(100)])
    assert len(fotos) == diseno_ia.MAX_FOTOS == 2 and len(r["diseno"]["capas"]) == 2 + 1  # 2 fotos + el logo
    r = crear([capa(texto=f"T{i}", y=7 * (i % 14), alto=6) for i in range(200)], usar_marca=False)
    assert [c["texto"] for c in r["diseno"]["capas"]] == [f"T{i}" for i in range(diseno_ia.MAX_CAPAS)]
    # El recorte quita primero la decoración del final, no el titular ni el contacto (que van al final para quedar
    # encima); y las fotos de más que la IA manda delante no gastan sitio
    flyer = [capa(tipo="imagen", prompt_imagen="salsa dancers", x=0, y=20, ancho=100, alto=30),
             capa(tipo="forma", y=0, alto=18, ancho=100, x=0), capa(tipo="forma", y=95, alto=5, ancho=100, x=0),
             capa(tipo="forma", y=3, alto=1, ancho=100, x=0), capa(tipo="forma", forma="linea", y=85, alto=1),
             capa(tipo="emoji", texto="💃", x=85, y=20, ancho=10, alto=6)]
    for i, (icono, dato) in enumerate((("calendar", "Sábado 20"), ("map-pin", "Club Caribe"), ("tag", "RD$500"),
                                       ("clock", "10 p. m."))):
        flyer += [capa(tipo="icono", icono=icono, x=8, y=52 + 8 * i, ancho=6, alto=5),
                  capa(texto=dato, x=16, y=52 + 8 * i, ancho=70, alto=6)]
    flyer += [capa(texto="NOCHE DE SALSA", y=4, alto=12), capa(texto="Reserva: 809-555-1234", y=88, alto=6)]
    assert len(flyer) == 16
    # Los datos vienen en el pedido: se quedan (sin ellos serían [Precio] y [Teléfono])
    r = crear(flyer, "flyer", usar_marca=False, pedido="Flyer noche de salsa, entrada RD$500, reservas 809-555-1234")
    assert len(r["diseno"]["capas"]) == diseno_ia.MAX_CAPAS
    assert {"NOCHE DE SALSA", "Reserva: 809-555-1234", "Sábado 20", "10 p. m."} <= {c["texto"] for c in textos(r)}
    r = crear([capa(tipo="imagen", prompt_imagen=f"photo {i}") for i in range(20)] + [capa(texto="TITULAR")],
              usar_marca=False)
    assert [c["tipo"] for c in r["diseno"]["capas"]] == ["imagen", "imagen", "texto"]
    r = crear([capa(tipo="imagen", prompt_imagen=f"photo {i}") for i in range(5)], fondo_prompt_imagen="beach")
    assert len(fotos) == 2 and fotos[0][1:] == (1080, 1080) and r["diseno"]["fondo"]["tipo"] == "imagen"
    assert len([c for c in r["diseno"]["capas"] if c["tipo"] == "imagen"]) == 2  # 1 foto + el logo

    # ---------- Textos gigantes ----------
    r = crear([capa(texto="PIZZA GIGANTE " * 1000, x=10, y=10, ancho=80, alto=20, tamano=30),
               capa(texto="A" * 5000, x=10, y=50, ancho=20, alto=5, tamano=30),
               capa(tipo="emoji", texto="🍕" * 100), capa(tipo="imagen", prompt_imagen="z" * 10_000)],
              titulo="x" * 5000, descripcion="y" * 10_000)
    foto, gigante, palabra, emojis = r["diseno"]["capas"][:4]
    assert len(gigante["texto"]) <= 200 and len(palabra["texto"]) <= 200 and len(emojis["texto"]) <= 8
    assert len(r["titulo"]) == 120 and len(r["descripcion"]) == 1000 and len(fotos[0][0]) <= 600 + 60
    assert gigante["tamano"] < 324 and palabra["tamano"] == 1080 / 45  # bajó hasta caber, o hasta el mínimo
    assert palabra["ancho"] == 216 and palabra["alto"] > 54  # el 20 % que pidió; ni a la mínima cabía: creció
    dentro(r)
    cabe(r)  # medido como el editor, que parte las palabras en cualquier punto
    assert diseno.abrir(Path(r["carpeta"])) == r["diseno"]
    # Un texto largo en una caja de 1 % en la esquina: queda dentro del lienzo y cabe en su caja
    for tipo, y, ancho, alto in (("historia", 99, 1, 1), ("post", 95, 25, 5), ("miniatura", 50, 30, 10)):
        r = crear([capa(texto="Pizza artesanal con masa madre y tomate de la huerta " * 4, x=99, y=y, ancho=ancho,
                        alto=alto)], tipo, usar_marca=False)
        dentro(r)
        cabe(r)
        lienzo = r["diseno"]
        assert textos(r)[0]["tamano"] >= round(min(lienzo["ancho"], lienzo["alto"]) / 45, 1)  # legible

    # ---------- Imágenes que fallan ----------
    r = crear([capa(texto="Sigue"), capa(tipo="imagen", prompt_imagen="FALLA capa")], fondo_prompt_imagen="FALLA fondo")
    assert r["diseno"]["fondo"] == {"tipo": "degradado", "colores": ["#123456", "#ABCDEF"], "imagen": ""}
    assert [c["tipo"] for c in r["diseno"]["capas"]] == ["texto", "imagen"]  # la foto se quitó; queda el logo
    assert len(r["avisos"]) == 2 and all("servicio caído" in a and "Ninguna opción" not in a for a in r["avisos"])
    assert "fondo" in r["avisos"][0] and "Se quitó esa capa" in r["avisos"][1]
    assert diseno.abrir(Path(r["carpeta"])) == r["diseno"] and Path(r["archivo"]).is_file()
    r = crear([capa(tipo="imagen", prompt_imagen="pizza")], fondo_prompt_imagen="FALLA fondo", usar_marca=False)
    assert r["diseno"]["fondo"]["colores"] == ["#0F0F13", "#FF4D8D"] and len(r["avisos"]) == 1
    assert (Path(r["carpeta"]) / "imagenes" / r["diseno"]["capas"][0]["archivo"]).is_file()

    # Un logo de marca roto no impide el diseño: se avisa
    marca.ruta_logo().write_text("no es una imagen", encoding="utf-8")
    r = crear([capa(texto="Sin logo")])
    assert len(r["diseno"]["capas"]) == 1 and "logo" in r["avisos"][0]

    # ---------- Una forma opaca puesta después del texto no lo tapa ----------
    r = crear([capa(texto="PIZZA 2x1", y=40, alto=20, tamano=12, color="#FFFFFF", negrita=True),
               capa(tipo="forma", x=0, y=0, ancho=100, alto=100, color="#FF4D8D")], usar_marca=False)
    assert [c["tipo"] for c in r["diseno"]["capas"]] == ["forma", "texto"]
    vista, t = QImage(r["archivo"]), textos(r)[0]
    assert any(QColor(vista.pixel(x, y)).lightness() > 240 for x in range(t["x"], t["x"] + t["ancho"], 3)
               for y in range(t["y"], t["y"] + t["alto"], 3))  # el titular blanco se ve

    # ---------- La IA respondió en píxeles en vez de porcentajes ----------
    r = crear([capa(texto="PIZZA 2x1", x=90, y=120, ancho=900, alto=220, tamano=110, fuente="Bebas Neue"),
               capa(tipo="forma", x=340, y=800, ancho=400, alto=120, redondeo=50),
               capa(tipo="icono", icono="phone", x=900, y=900, ancho=100, alto=100)], usar_marca=False)
    forma, titulo, icono = r["diseno"]["capas"]
    # La caja queda justa a las letras, centrada donde la puso la IA
    assert (titulo["x"], titulo["ancho"], round(titulo["y"] + titulo["alto"] / 2)) == (90, 900, 230)
    assert titulo["alto"] <= 220
    assert 50 < titulo["tamano"] <= 110 and (icono["x"], icono["y"], icono["ancho"]) == (900, 900, 100)
    assert (forma["x"], forma["y"], forma["ancho"], forma["alto"]) == (340, 800, 400, 120)

    # ---------- Texto invisible: del color de lo que tiene detrás, o casi transparente ----------
    r = crear([capa(texto="Oscuro", color="#0F0F13", y=5, alto=10, opacidad=6),
               capa(tipo="forma", x=0, y=40, ancho=100, alto=30, color="#FFFFFF"),
               capa(texto="Blanco", color="#FFFFFF", y=45, alto=10), capa(texto="Rosa", color="#FF4D8D", y=80, alto=10),
               capa(tipo="icono", icono="star", color="#FFFFFF", x=40, y=58, ancho=10, alto=10)], usar_marca=False)
    oscuro, blanco, rosa = textos(r)
    assert (oscuro["color"], blanco["color"], rosa["color"]) == ("#FFFFFF", "#111111", "#FF4D8D")
    assert oscuro["opacidad"] == 1 and r["diseno"]["capas"][-1]["color"] == "#111111"  # el icono, sobre blanco
    r = crear([capa(texto="Sobre la foto", color="#FFFFFF")], usar_marca=False, fondo_prompt_imagen="beach at night")
    assert textos(r)[0]["sombra"] and textos(r)[0]["color"] == "#FFFFFF"  # sobre una foto: la sombra lo despega
    r = crear([capa(texto="Abajo", color="#FFFFFF", y=85, alto=10)], usar_marca=False,
              fondo_colores=["#000000", "#FAFAFA"])
    assert textos(r)[0]["color"] == "#111111"  # el degradado ya es claro a esa altura

    # ---------- Dos textos montados se separan; si no caben, se quita uno y se avisa ----------
    r = crear([capa(texto="PIZZA 2x1", y=40, alto=20), capa(texto="SOLO HOY", y=42, alto=20)], usar_marca=False)
    pizza, hoy = textos(r)
    assert not diseno_ia._cortan(pizza, hoy) and hoy["y"] >= pizza["y"] + pizza["alto"] and r["avisos"] == []
    # Letras enormes (30 % del alto): tres textos no caben uno debajo de otro
    r = crear([capa(texto=t, y=y, alto=45, tamano=30) for t, y in (("Uno", 0), ("Dos", 10), ("Tres", 20))],
              usar_marca=False)
    assert [c["texto"] for c in textos(r)] == ["Uno", "Dos"] and "«Tres»" in r["avisos"][0]
    dentro(r)

    # ---------- Emojis grandes: no rompen el tope de diseno.validar ----------
    r = crear([capa(tipo="emoji", texto="🍕🍔🌮🍟🍩🍪🎂🍰", x=0, y=0, ancho=100, alto=100) for _ in range(14)],
              usar_marca=False)
    assert 0 < len(r["diseno"]["capas"]) < 14 and "emojis" in r["avisos"][-1]
    assert sum(map(diseno._pixeles_emoji, r["diseno"]["capas"])) <= diseno.MAX_PIXELES_EMOJI

    # ---------- El pedido no se manda entero si es enorme (gasto de la IA de texto) ----------
    respuesta["capas"] = [capa(texto="Hola")]
    diseno_ia.crear("p" * 300_000, "post", False)
    assert f"Pedido: {'p' * 2000}\n" in pedidos[-1] and len(pedidos[-1]) < 2000 + 2000

    # ---------- Un prompt con «../» no cambia la dirección de Pollinations (la petición lleva la clave) ----------
    urls, originales = [], (claves.cargar, nubes.rotar, seguro.descargar)

    def descargar(url, cabeceras=None, **_):
        urls.append(url)
        raise RuntimeError("sin red")

    def rotar(uso, tareas, *_, **__):  # que_fue: el modelo y el precio para la actividad de la IA
        for proveedor in ("pollinations", "gratis_sin_clave"):
            falla(tareas[proveedor], error=RuntimeError)
        raise RuntimeError("Ninguna opción pudo hacerlo.")

    claves.cargar = lambda: {"pollinations": {"clave": "clave-falsa", "modelo_imagen": "zimage"}}
    nubes.rotar, seguro.descargar = rotar, descargar
    try:
        falla(imagen_real, "../../account/profile", 64, 64, d / "x.png", error=RuntimeError)
    finally:
        claves.cargar, nubes.rotar, seguro.descargar = originales
    assert len(urls) == 2
    for url in urls:
        ruta = httpx.URL(url).raw_path
        assert ruta.startswith((b"/image/..%2F..%2Faccount", b"/prompt/..%2F..%2Faccount")), ruta
    for solo_puntos in ("..", "."):  # «..» solo también llevaría a la raíz del servidor
        assert httpx.URL("https://gen.pollinations.ai/image/" + ia._ruta_url(solo_puntos)).raw_path.startswith(
            b"/image/imagen")

    # ---------- Lo que no se puede crear: error claro y sin carpeta a medias ----------
    antes = set(diseno.CARPETA.iterdir())
    falla(crear, [capa(texto=""), "x", capa(tipo="icono", icono="no-existe-zzz")], error=RuntimeError)
    falla(crear, [], error=RuntimeError)
    ia.texto_json = lambda *a, **k: ["no", "es", "un", "objeto"]
    falla(diseno_ia.crear, "x", error=RuntimeError)
    ia.texto_json = texto_json
    for tipo in ("video", "", None, ["post"], "POST"):
        falla(diseno_ia.crear, "pizza", tipo)
    for pedido in ("", "   ", None):
        falla(diseno_ia.crear, pedido)
    assert set(diseno.CARPETA.iterdir()) == antes

    # Un diseño hecho por el agente (Claude por el MCP): se usa tal cual, sin la IA de texto, con las mismas reglas
    guardado = ia.texto_json
    ia.texto_json = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía usar la IA"))
    try:
        hecho = diseno_ia.crear("", "presentacion", False, propuesta={
            "titulo": "Ráfaga", "descripcion": "d", "fondo_colores": ["#0F0F13"], "fondo_prompt_imagen": "",
            "capas": [{"tipo": "texto", "x": 8, "y": 30, "ancho": 84, "alto": 20, "texto": "Ráfaga Studio",
                       "tamano": 12, "color": "#FFFFFF"}]})
        assert hecho["diseno"]["ancho"] == 1280 and Path(hecho["archivo"]).is_file()
        falla(lambda: diseno_ia.crear("", "post", propuesta={"titulo": "sin capas"}))
        falla(lambda: diseno_ia.crear("", "post", propuesta="no es json"))
    finally:
        ia.texto_json = guardado

    # ---------- Estilo: ilustraciones enteras y cuadradas, sin palabras de foto ----------
    r = crear([capa(tipo="imagen", prompt_imagen="gothic skull, realistic detailed photography", x=10, y=20, ancho=80,
                    alto=40), capa(texto="CALAVERA", y=70, alto=15)], usar_marca=False, pedido="calavera gótica",
              estilo="vector")
    prompt = fotos[0][0]
    assert diseno_ia.ESTILOS["vector"] in prompt and prompt.endswith(diseno_ia._SIN_TEXTO) and "gothic skull" in prompt
    assert "photo" not in prompt.lower() and "realistic" not in prompt.lower()
    assert "isolated on plain solid background #0F0F13" in prompt  # el color del lienzo: no queda un recuadro
    ilus = r["diseno"]["capas"][0]
    assert ilus["ajuste"] == "contener" and ilus["ancho"] == ilus["alto"] == 432 and fotos[0][1:] == (432, 432)
    assert (ilus["x"], ilus["y"]) == (324, 216)  # cuadrada desde el centro de la caja que pidió la IA
    assert "Estilo de las imágenes: vector" in pedidos[0]
    # Foto: realista, y llena su caja como antes
    r = crear([capa(tipo="imagen", prompt_imagen="pepperoni pizza", x=0, y=40, ancho=100, alto=60)], usar_marca=False,
              estilo="foto")
    assert fotos == [("pepperoni pizza, " + diseno_ia.ESTILOS["foto"] + diseno_ia._SIN_TEXTO, 1080, 648)]
    assert r["diseno"]["capas"][0]["ajuste"] == "cubrir"
    # Ilustración, estampado y logo: ilustración entera aunque el estilo sea automático, y sin el logo de la marca
    for tipo in ("ilustracion", "estampado", "logo"):
        r = crear([capa(tipo="imagen", prompt_imagen="skull photo", x=5, y=10, ancho=90, alto=70)], tipo,
                  pedido="calavera gótica")
        ilus = r["diseno"]["capas"][0]
        assert [c["tipo"] for c in r["diseno"]["capas"]] == ["imagen"] and r["avisos"] == [], tipo
        assert ilus["ajuste"] == "contener" and ilus["ancho"] == ilus["alto"], tipo
        assert fotos[0][0] == "skull, isolated on plain solid background #0F0F13" + diseno_ia._SIN_TEXTO
    # Sobre un degradado, el color que tendrá detrás (el de su altura), no el de arriba; sobre una foto, ninguno
    crear([capa(tipo="imagen", prompt_imagen="skull", x=30, y=30, ancho=40, alto=40)], "ilustracion", False,
          estilo="vector", fondo_colores=["#000000", "#FF0000"])
    assert "isolated on plain solid background #800000" in fotos[0][0]
    crear([capa(tipo="imagen", prompt_imagen="skull", x=30, y=30, ancho=40, alto=40)], "ilustracion", False,
          fondo_prompt_imagen="dark brick wall")
    assert len(fotos) == 2 and "isolated" not in fotos[1][0] and fotos[1][0].startswith("skull")
    # Con el borde liso, el dibujo queda igual; con humo hasta el borde, se funde con el fondo y no se ve el cuadrado
    r = crear([capa(tipo="imagen", prompt_imagen="skull", x=30, y=30, ancho=40, alto=40)], "ilustracion", False)
    liso = QImage(str(diseno.ruta_imagen(Path(r["carpeta"]), r["diseno"]["capas"][0]["archivo"])))
    assert not liso.hasAlphaChannel() and r["diseno"]["fondo"]["colores"] == ["#00AA00"]
    r = crear([capa(tipo="imagen", prompt_imagen="HUMO robot", x=5, y=5, ancho=90, alto=90)], "ilustracion", False,
              estilo="neon_oscuro")
    humo = QImage(str(diseno.ruta_imagen(Path(r["carpeta"]), r["diseno"]["capas"][0]["archivo"])))
    lado = humo.width()
    assert r["diseno"]["fondo"]["colores"] == ["#06041A"]
    assert humo.pixelColor(lado // 2, lado - 1).alpha() < 20 and humo.pixelColor(0, lado // 2).alpha() < 20
    assert humo.pixelColor(lado // 2, lado * 7 // 8).alpha() == 255  # el dibujo, entero
    assert humo.pixelColor(lado // 2, lado // 2).name() == "#06041a" and humo.pixelColor(lado // 2, lado // 2).alpha() == 255
    antes = set(diseno.CARPETA.iterdir())
    for estilo in ("VECTOR", "", None, "acuarela", ["vector"]):
        assert "Estilo desconocido" in falla(lambda: diseno_ia.crear("pizza", "post", estilo=estilo))
    assert set(diseno.CARPETA.iterdir()) == antes

    # ---------- Datos inventados por la IA: huecos en el diseño y en la descripción ----------
    r = crear([capa(texto="Entrada 15 € · www.x.com · +34 600 123 456", y=40, alto=20),
               capa(texto="PIZZA 2x1", y=70, alto=15)], usar_marca=False, pedido="pizza 2x1",
              descripcion="Ven, solo 9,99 € en santolapara.com")
    assert [c["texto"] for c in textos(r)] == ["Entrada [Precio] · [Web] · [Teléfono]", "PIZZA 2x1"]
    assert r["descripcion"] == "Ven, solo [Precio] en [Web]"
    # En una propuesta también (el Director de la app la escribe él mismo): los datos reales vienen en el pedido
    propuesta = {"titulo": "x", "descripcion": "Solo hoy: 30% OFF", "fondo_colores": ["#0F0F13"],
                 "fondo_prompt_imagen": "", "capas": [{"tipo": "texto", "x": 8, "y": 30, "ancho": 84, "alto": 20,
                                                       "texto": "Entrada 15 € · www.x.com · 30% OFF"}]}
    hecho = diseno_ia.crear("", "post", False, propuesta=propuesta)
    assert textos(hecho)[0]["texto"] == "Entrada [Precio] · [Web] · [Precio] OFF"
    assert hecho["descripcion"] == "Solo hoy: [Precio] OFF"
    hecho = diseno_ia.crear("fiesta, entrada 15 euros, web x.com", "post", False, propuesta=propuesta)
    assert textos(hecho)[0]["texto"] == "Entrada 15 € · www.x.com · [Precio] OFF"

    # ---------- Cuota de imágenes agotada (429): se va la foto y su marco, y no se enseña la URL ----------
    r = crear([capa(tipo="forma", x=5, y=25, ancho=90, alto=50, color="#5A3A1A"),
               capa(tipo="imagen", prompt_imagen="FALLA429 skull", x=8, y=28, ancho=84, alto=44),
               capa(tipo="forma", x=5, y=85, ancho=40, alto=8, redondeo=50),
               capa(texto="CALAVERA", y=5, alto=15)], usar_marca=False)
    assert [c["tipo"] for c in r["diseno"]["capas"]] == ["forma", "texto"]  # el botón de abajo se queda
    assert r["diseno"]["capas"][0]["y"] == round(1080 * 0.85)
    assert len(r["avisos"]) == 1 and "cuota gratis" in r["avisos"][0]
    assert "http" not in r["avisos"][0] and CUENTA not in r["avisos"][0]
    # Una foto a lienzo completo que falla: se va ella sola; la banda y el botón que iban encima se quedan
    r = crear([capa(tipo="imagen", prompt_imagen="FALLA429 pizza", x=0, y=0, ancho=100, alto=100),
               capa(tipo="forma", x=0, y=60, ancho=100, alto=24, color="#000000", opacidad=50),
               capa(tipo="forma", x=25, y=86, ancho=50, alto=8, color="#FF4D8D", redondeo=50),
               capa(texto="PIZZA 2x1", y=64, alto=14), capa(texto="Pide ya", x=25, y=86, ancho=50, alto=8)],
              usar_marca=False)
    assert [c["tipo"] for c in r["diseno"]["capas"]] == ["forma", "forma", "texto", "texto"]
    # nubes ya resume la cuota agotada («se acabó la cuota gratis de hoy»): se reconoce y no se repite
    cuota = diseno_ia._causa(RuntimeError("Ninguna opción pudo hacerlo.\nCloudflare: se acabó la cuota gratis de hoy"))
    assert cuota == "se acabó la cuota gratis de imágenes de hoy"
    otro = diseno_ia._causa(RuntimeError(f"Ninguna opción pudo hacerlo.\nReplicate: 500 for url "
                                         f"'https://api.replicate.com/v1/{CUENTA}'\nOpenAI: sin clave"))
    assert "http" not in otro and CUENTA not in otro and "sin clave" in otro and "Ninguna opción" not in otro

    # ---------- «Generar con IA» del editor: una ilustración suelta ----------
    destino = d / "generada.png"
    fotos.clear()
    assert diseno_ia.ilustracion("calavera con rosas", "sticker", destino) == destino and destino.is_file()
    assert fotos == [("calavera con rosas, " + diseno_ia.ESTILOS["sticker"] + diseno_ia._SIN_TEXTO, 1024, 1024)]
    diseno_ia.ilustracion("  a cat photo ", "auto", str(destino), "4K")
    assert fotos[-1][0] == "a cat photo" + diseno_ia._SIN_TEXTO  # automático: tal cual lo pidió
    assert calidades[-2:] == ["1K", "4K"]  # la calidad elegida llega a la IA de imágenes
    error = falla(diseno_ia.ilustracion, "FALLA429 calavera", "vector", destino, error=RuntimeError)
    assert "cuota gratis" in error and "http" not in error and CUENTA not in error
    falla(diseno_ia.ilustracion, "   ", "vector", destino)
    falla(diseno_ia.ilustracion, "calavera", "acuarela", destino)

    # ---------- Entender el pedido (faltas incluidas) antes de gastar imágenes ----------
    llamadas = []

    def entiende(contesta):
        def falsa(instrucciones, pedido, esquema, uso="texto", rapido=False):
            assert esquema is diseno_ia.ESQUEMA_ENTENDER and diseno_ia.FALTAS in instrucciones and uso == "diseno"
            assert rapido is True  # entender no necesita que el modelo piense antes (ia._sin_razonar)
            llamadas.append(pedido)
            if isinstance(contesta, Exception):
                raise contesta
            return copy.deepcopy(contesta)
        return falsa

    guardado = ia.texto_json
    fotos.clear()
    try:
        ia.texto_json = entiende({"entendido": "una carabela gótica", "seguro": False,
                                  "pregunta": "¿Calavera (cráneo) o carabela (barco)?",
                                  "opciones": ["una calavera gótica", "una carabela gótica (barco)", " ", "otra",
                                               "y otra"], "tipo": "flyer", "estilo": "tatuaje"})
        assert diseno_ia.entender("una carabela gótica") == {
            "entendido": "una carabela gótica", "seguro": False, "pregunta": "¿Calavera (cráneo) o carabela (barco)?",
            "opciones": ["una calavera gótica", "una carabela gótica (barco)", "otra"], "tipo": "flyer",
            "estilo": "tatuaje"}
        assert llamadas == ["Pedido: una carabela gótica"]
        # El tipo que eligió el usuario manda, y la IA lo sabe
        assert diseno_ia.entender("una carabela gótica", "logo")["tipo"] == "logo"
        assert "Pieza elegida por el usuario: logo" in llamadas[-1]
        ia.texto_json = entiende({"entendido": "logo para mi barbería", "seguro": True, "pregunta": "",
                                  "opciones": [], "tipo": "logo", "estilo": "vector"})
        assert diseno_ia.entender("logo para mi barvería") == {
            "entendido": "logo para mi barbería", "seguro": True, "pregunta": "", "opciones": [], "tipo": "logo",
            "estilo": "vector"}
        # Respuestas raras: tipo o estilo que no existen; «no seguro» sin opciones no tiene nada que preguntar
        ia.texto_json = entiende({"entendido": "", "seguro": False, "pregunta": "¿?", "opciones": "no es lista",
                                  "tipo": ["post"], "estilo": "acuarela"})
        e = diseno_ia.entender("pizza")
        assert (e["entendido"], e["seguro"], e["opciones"], e["tipo"], e["estilo"]) == (
            "pizza", True, [], "ilustracion", "auto")
        # Si la IA de texto falla, no bloquea: el pedido intacto
        ia.texto_json = entiende(RuntimeError("sin IA de texto"))
        assert diseno_ia.entender("calavera gótica") == {"entendido": "calavera gótica", "seguro": True,
                                                         "pregunta": "", "opciones": [], "tipo": "ilustracion",
                                                         "estilo": "auto"}
        assert diseno_ia.entender("calavera gótica", "estampado")["tipo"] == "estampado"
        ia.texto_json = entiende(["no", "es", "un", "objeto"])
        assert diseno_ia.entender("x")["seguro"] is True
        # Una foto de algo real: la IA pequeña lo toma por un dibujo suelto (pasó: «una mariposa» salió un sticker
        # vectorial), pero si el pedido dice foto, real o realista sale foto. Los dibujos, stickers y logos, dibujos
        ia.texto_json = entiende({"entendido": "", "seguro": True, "pregunta": "", "opciones": [],
                                  "tipo": "ilustracion", "estilo": "vector"})
        for pedido, tipo, estilo in (("una mariposa real en un jardín", "foto", "foto"),
                                     ("Foto realista de un perro en la playa", "foto", "foto"),
                                     ("a realistic photo of a red apple", "foto", "foto"),
                                     ("uma borboleta de verdade num jardim", "foto", "foto"),
                                     ("una imagen de una mariposa", "ilustracion", "vector"),
                                     ("dibujo de una mariposa real", "ilustracion", "vector"),
                                     ("un sticker de una mariposa realista", "ilustracion", "vector")):
            e = diseno_ia.entender(pedido)
            assert (e["tipo"], e["estilo"]) == (tipo, estilo), (pedido, e)
        assert diseno_ia.entender("una mariposa real", "ilustracion")["tipo"] == "ilustracion"  # la eligió el usuario
        ia.texto_json = entiende({"entendido": "", "seguro": True, "pregunta": "", "opciones": [], "tipo": "post",
                                  "estilo": "vector"})
        assert diseno_ia.entender("post para la Barbería El Real")["tipo"] == "post"  # otra pieza: la de la IA
        ia.texto_json = entiende({"entendido": "", "seguro": True, "pregunta": "", "opciones": [], "tipo": "foto",
                                  "estilo": "vector"})
        assert diseno_ia.entender("un colibrí en una flor")["estilo"] == "foto"  # una foto nunca es vectorial
        ia.texto_json = entiende(RuntimeError("sin IA de texto"))  # sin IA de texto, también
        assert diseno_ia.entender("una mariposa real en un jardín")["tipo"] == "foto"
    finally:
        ia.texto_json = guardado
    for pedido in ("", "   ", None):
        falla(diseno_ia.entender, pedido)
    for tipo in ("video", "", None, "AUTO", ["post"]):
        falla(diseno_ia.entender, "pizza", tipo)
    assert fotos == []  # entender nunca gasta imágenes

    # ---------- La foto real llena el lienzo: nada de un motivo suelto sobre un fondo liso ----------
    def esquinas(r):
        vista = QImage(r["archivo"])
        return {vista.pixelColor(x, y).name() for x in (2, vista.width() - 3) for y in (2, vista.height() - 3)}

    # Aunque la IA la ponga en una capa centrada sobre un color (como el sticker de la mariposa), sale a sangre
    r = crear([capa(tipo="imagen", x=10, y=10, ancho=80, alto=80, prompt_imagen="a monarch butterfly on a flower")],
              tipo="foto", pedido="una mariposa real en un jardín", fondo_colores=["#F3FFF9"])
    d = r["diseno"]
    assert d["fondo"]["tipo"] == "imagen" and not [c for c in d["capas"] if c["tipo"] == "imagen"], d
    assert fotos == [(fotos[0][0], 1080, 1080)] and fotos[0][0].startswith("a monarch butterfly on a flower")
    assert "professional photography" in fotos[0][0] and "isolated" not in fotos[0][0]  # foto, no un recorte
    assert esquinas(r) == {"#00aa00"}  # las cuatro esquinas son la foto, no el #F3FFF9 de detrás
    # La IA la manda como foto de fondo (lo que pide su pista) y sin capas: una foto sola también es un diseño
    r = crear([], tipo="foto", pedido="foto realista de un perro en la playa",
              fondo_prompt_imagen="a golden retriever running on a beach at sunset")
    assert r["diseno"]["capas"] == [] and esquinas(r) == {"#00aa00"} and len(fotos) == 1
    assert "foto (Foto realista)" in diseno_ia.INSTRUCCIONES_ENTENDER  # la IA que entiende el pedido la conoce
    # Si la foto no sale, no queda un diseño vacío: el motivo, en claro, y ni su carpeta
    antes = set(diseno.CARPETA.glob("*"))
    try:
        crear([], tipo="foto", pedido="una mariposa real", fondo_prompt_imagen="FALLA a butterfly")
        raise AssertionError("debió fallar sin la foto")
    except RuntimeError as e:
        error = str(e)
    assert "La foto de fondo no salió (servicio caído)" in error and set(diseno.CARPETA.glob("*")) == antes, error

    # ---------- Fuentes góticas: solo las que hay instaladas ----------
    fuentes_reales = recursos.fuentes
    recursos.fuentes = lambda: sorted(set(fuentes_reales()) | {"Pirata One"})
    try:
        crear([capa(texto="x")], usar_marca=False)
    finally:
        recursos.fuentes = fuentes_reales
    linea = next(l for l in pedidos[0].splitlines() if l.startswith("Para títulos góticos"))
    assert "Pirata One" in linea
    crear([capa(texto="x")], usar_marca=False)
    assert ("Para títulos góticos" in pedidos[0]) == any(f in recursos.fuentes() for f in diseno_ia._DECORATIVAS)

    # ---------- La marca no se impone: solo lo que el usuario rellenó ----------
    marca.guardar({"nombre": "santo la para"})
    crear([capa(texto="Calavera")], "flyer", pedido="calavera gótica")
    linea = next(l for l in pedidos[0].splitlines() if l.startswith("Marca del usuario"))
    assert linea.startswith("Marca del usuario: nombre: santo la para.") and "nunca como «X PRESENTA»" in linea
    assert "Montserrat" not in linea and "Poppins" not in linea and "respétala" not in pedidos[0]
    marca.guardar({"nombre": "", "fuente_titulo": "Anton"})
    crear([capa(texto="x")])
    linea = next(l for l in pedidos[0].splitlines() if l.startswith("Marca del usuario"))
    assert linea == "Marca del usuario: fuente de títulos: Anton."  # la que cambió; la de textos no
    marca.guardar({})
    crear([capa(texto="x")])
    assert "Marca del usuario" not in pedidos[0] and "Elige tú los colores" in pedidos[0]

    # ---------- La herramienta MCP ----------
    import mcp_server  # noqa: E402
    mcp_server._preguntar = lambda texto: False  # nunca una ventana de verdad en las pruebas: nada de pago se hace
    respuesta.update({"capas": [capa(texto="Juan Pérez"), capa(tipo="icono", icono="mail")]})
    r = json.loads(mcp_server.crear_diseno("Tarjeta de Juan", "tarjeta", False))
    assert r["tipo"] == "diseno" and Path(r["archivo"]).is_file() and r["diseno"]["ancho"] == 1050
    assert diseno.abrir(Path(r["carpeta"])) == r["diseno"]
    # El agente recibe el porqué de un fallo esperado (el SDK esconde el texto de cualquier otra excepción)
    from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError  # noqa: E402
    assert "Tipo de diseño desconocido" in falla(mcp_server.crear_diseno, "pizza", "video", error=ToolError)
    assert "Escribe qué diseño" in falla(mcp_server.crear_diseno, "   ", error=ToolError)
    try:
        asyncio.run(mcp_server.mcp.call_tool("crear_diseno", {"pedido": "pizza", "tipo": "video"}))
        raise AssertionError("debió fallar")
    except ToolError as e:
        assert not isinstance(e, UnexpectedToolError) and "valen anuncio, post" in str(e)
    falla(mcp_server.crear_video, "x", "9:16", "no es un número", error=ToolError)  # y en todas las herramientas
    herramientas = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert len(herramientas) == 17 and all(hasattr(getattr(mcp_server, h), "__wrapped__") for h in herramientas)
    assert set(herramientas["crear_diseno"].input_schema["properties"]) == {"pedido", "tipo", "usar_marca", "propuesta",
                                                                            "estilo", "calidad"}
    assert "Diseña una pieza" in herramientas["crear_diseno"].description  # el envoltorio no se come la descripción
assert "crear_diseno" in conexion_mcp.probar()  # el servidor arranca y la lista

# ---------- Integración: la guarda de datos inventados y la causa de una imagen que no sale ----------
for texto, pedido, queda in (
        ("30% OFF en todo", "flyer fiesta del 30 de octubre", "[Precio] OFF en todo"),  # una fecha no es un precio
        ("Entrada 20 €", "flyer fiesta el sábado 20 de octubre", "Entrada [Precio]"),
        ("Combo RD$2", "pizza 2x1 los martes", "Combo [Precio]"),
        ("Pizza RD$500", "pizza a 500", "Pizza RD$500"),  # «a 500» sí es un precio
        ("Tel. 600.123.456", "tienda de ropa", "Tel. [Teléfono]"),  # un móvil con puntos no son miles
        ("Llama al 809 555 1234", "llama al 555 1234", "Llama al [Teléfono]"),  # código de área que no dio
        ("Llama al 809 555 1234", "llama al +1 809-555-1234", "Llama al 809 555 1234"),
        ("Más de 15.000.000 de vistas", "canal de youtube", "Más de 15.000.000 de vistas")):
    assert diseno_ia._sin_inventos(texto, pedido) == queda, (texto, diseno_ia._sin_inventos(texto, pedido))
sin_red = RuntimeError(f"{ia.t('Ninguna opción pudo hacerlo.')}\n{nubes.NOMBRES['huggingface']}: getaddrinfo failed")
assert "getaddrinfo" in diseno_ia._causa(sin_red)  # sin internet no es «se acabó la cuota»

# ---------- Imágenes con Gemini (de pago): solo si el usuario lo elige ----------
import base64  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="rafaga-gemini-"))
diseno.CARPETA = tmp / "disenos"
sin_nano = ["models/gemini-2.5-flash-image", "models/gemini-3.1-flash-image", "models/gemini-3-pro-image",
            "models/gemini-3.1-flash-lite-image", "models/gemini-3.2-flash-image-preview", "models/nano-banana-pro-preview"]
assert claves.elegir_modelo_imagen_gemini(sin_nano) == "gemini-3.1-flash-image"
# Nano Banana (mejor y más barato) antes que Flash Image, en su versión estable más alta; Pro, Lite y preview no
assert claves.elegir_modelo_imagen_gemini(sin_nano + ["models/gemini-nano-banana-2.1", "models/gemini-nano-banana-2",
                                                      "models/gemini-nano-banana-2.9-preview",
                                                      "models/gemini-nano-banana-pro-3"]) == "gemini-nano-banana-2.1"
assert claves.elegir_modelo_imagen_gemini(["gemini-nano-banana-2.9", "gemini-nano-banana-2.10"]) == "gemini-nano-banana-2.10"
assert claves.elegir_modelo_imagen_gemini(["gemini-3-pro-image", "gemini-2.5-flash"]) is None
# Precio por modelo: el que elige elegir_modelo_imagen_gemini (Nano Banana o el Flash Image de respaldo)
assert set(ia.PRECIO_IMAGEN_GEMINI) == {ia.IMAGEN_GEMINI, "gemini-3.1-flash-image"} == {
    claves.elegir_modelo_imagen_gemini(sin_nano), ia.IMAGEN_GEMINI}
assert ia.IMAGEN_GEMINI == "gemini-nano-banana-2.1"
assert all(p["1K"] < p["2K"] < p["4K"] for p in ia.PRECIO_IMAGEN_GEMINI.values())
# El aviso de costo usa el modelo ya elegido para la clave; si aún no se sabe (o su precio no), el más caro conocido
flash, nano = ia.PRECIO_IMAGEN_GEMINI["gemini-3.1-flash-image"], ia.PRECIO_IMAGEN_GEMINI[ia.IMAGEN_GEMINI]
assert all(ia.precio_imagen_gemini("AIzaNueva", c) == flash[c] > nano[c] for c in nano)
for elegido, precios in ((ia.IMAGEN_GEMINI, nano), ("gemini-3.1-flash-image", flash), ("gemini-nano-banana-2.10", flash)):
    ia._elegidos[("AIzaNueva", claves.elegir_modelo_imagen_gemini)] = elegido
    assert ia.precio_imagen_gemini("AIzaNueva", "2K") == precios["2K"], elegido
cargar_real, ajustes_real, post_real, uso_real = claves.cargar, claves.ajustes, ia.httpx.post, nubes.USO
nubes.USO = tmp / "uso.json"  # el contador de hoy, fuera de datos/
claves.cargar = lambda: {"gemini": {"proveedor": "gemini", "clave": "AIzaPrueba"},
                         "cloudflare": {"proveedor": "cloudflare", "clave": f"{CUENTA} token"}}
try:
    claves.ajustes = lambda: {}
    assert "gemini" not in nubes.orden("imagen") and "gemini" in claves.opciones("imagen")  # se ofrece, no se usa solo
    assert not ia.puede_referencia()
    claves.ajustes = lambda: {"imagen": "gemini"}
    assert nubes.orden("imagen")[0] == "gemini" and ia.puede_referencia()
    png = QImage(8, 8, QImage.Format_RGB32)
    png.fill(QColor("#123456"))
    hecho = tmp / "gemini.png"
    png.save(str(hecho))
    pedidos_gemini = []

    class Contesta:
        def __init__(self, cuerpo):
            self.status_code, self.is_error, self.cuerpo, self.text = 200, False, cuerpo, ""

        def json(self):
            return self.cuerpo

        def raise_for_status(self):
            pass

    def post_gemini(url, **k):
        pedidos_gemini.append((url, k["json"]))
        datos = base64.b64encode(hecho.read_bytes()).decode()
        return Contesta({"candidates": [{"content": {"parts": [{"text": "aquí va"},
                                                               {"inlineData": {"mimeType": "image/png", "data": datos}}]}}]})
    ia.httpx.post = post_gemini
    ia._elegidos[("AIzaPrueba", claves.elegir_modelo_imagen_gemini)] = "gemini-3.1-flash-image"  # sin preguntar a la red
    salida = ia._imagen_gemini(claves.cargar()["gemini"], "gothic skull", 1080, 1920, hecho)
    assert salida == hecho.read_bytes()
    url, cuerpo = pedidos_gemini[-1]
    assert url.endswith("/models/gemini-3.1-flash-image:generateContent")
    assert cuerpo["generationConfig"]["imageConfig"] == {"aspectRatio": "9:16", "imageSize": "1K"}
    assert cuerpo["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"  # la referencia va primero
    # La proporción más cercana de las 10 que acepta: un post 4:5 o un flyer A4 ya no salen de un 9:16
    for ancho, alto, relacion in ((1080, 1350, "4:5"), (1240, 1754, "2:3"), (1080, 1080, "1:1"), (1500, 500, "21:9"),
                                  (1280, 720, "16:9"), (1050, 600, "16:9"), (1000, 1300, "3:4"), (64, 64000, "9:16")):
        ia._imagen_gemini(claves.cargar()["gemini"], "x", ancho, alto)
        assert pedidos_gemini[-1][1]["generationConfig"]["imageConfig"]["aspectRatio"] == relacion, (ancho, alto)
    # ia.imagen pasa la calidad solo a Gemini, que la manda como imageSize
    imagen_real("gothic skull", 1080, 1350, tmp / "4k.png", calidad="4K")
    assert pedidos_gemini[-1][1]["generationConfig"]["imageConfig"] == {"aspectRatio": "4:5", "imageSize": "4K"}
    claves.ajustes = lambda: {"imagen": "cloudflare"}
    ia.httpx.post = lambda url, **k: Contesta({"result": {"image": base64.b64encode(hecho.read_bytes()).decode()}})
    n = len(pedidos_gemini)
    assert imagen_real("skull", 1024, 1024, tmp / "cf.png", calidad="4K").read_bytes() == hecho.read_bytes()
    assert len(pedidos_gemini) == n  # las demás la ignoran
finally:
    claves.cargar, claves.ajustes, ia.httpx.post, nubes.USO = cargar_real, ajustes_real, post_real, uso_real

# La ilustración sobre el fondo liso: el fondo toma el color de su borde y no se ve el recuadro
def dibujo_morado(prompt, ancho, alto, destino, calidad="1K"):
    calidades.append(calidad)
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagen = QImage(64, 64, QImage.Format_RGB32)
    imagen.fill(QColor("#2a1b3d"))
    imagen.save(str(destino))
    return destino


imagen_real, texto_real = ia.imagen, ia.texto_json
ia.imagen = dibujo_morado
ia.texto_json = lambda *a, **k: {"titulo": "Calavera", "descripcion": "d", "fondo_colores": ["#000000"],
                                 "fondo_prompt_imagen": "", "capas": [
                                     {"tipo": "imagen", "x": 20, "y": 20, "ancho": 60, "alto": 60,
                                      "prompt_imagen": "gothic skull"}]}
try:
    calidades.clear()
    r = diseno_ia.crear("calavera gótica", "ilustracion", False, estilo="tatuaje", calidad="2K")
    assert r["diseno"]["fondo"]["colores"] == ["#2A1B3D"], r["diseno"]["fondo"]
    assert calidades == ["2K"]  # cada foto del diseño, con la calidad elegida
finally:
    ia.imagen, ia.texto_json = imagen_real, texto_real
print("Pruebas de la IA diseñadora pasadas.")
