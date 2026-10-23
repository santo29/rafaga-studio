"""Pruebas de la IA diseñadora (motor/diseno_ia.py y la herramienta MCP crear_diseno), sin red ni claves: la IA de
texto y la de imágenes se sustituyen. python pruebas_diseno_ia.py"""
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
respuesta, pedidos, fotos = {}, [], []
imagen_real = ia.imagen


def texto_json(instrucciones, pedido, esquema):
    assert esquema is diseno_ia.ESQUEMA and "PORCENTAJE" in instrucciones
    pedidos.append(pedido)
    return copy.deepcopy(respuesta)


def imagen(prompt, ancho, alto, destino):
    fotos.append((prompt, ancho, alto))
    if "FALLA" in prompt:
        raise RuntimeError("Ninguna opción pudo hacerlo.\ncuota agotada")
    foto = QImage(ancho, alto, QImage.Format_RGB32)
    foto.fill(QColor("#00AA00"))
    assert foto.save(str(destino))
    return destino


ia.texto_json, ia.imagen = texto_json, imagen


def capa(**campos):
    """Una capa como la manda la IA: todos los campos, los que no usa en «vacío»."""
    return {"tipo": "texto", "x": 10, "y": 10, "ancho": 80, "alto": 20, "texto": "", "fuente": "", "tamano": 0,
            "color": "", "negrita": False, "alineacion": "centro", "sombra": False, "forma": "rectangulo",
            "redondeo": 0, "opacidad": 100, "icono": "", "prompt_imagen": "", **campos}


def crear(capas, tipo="post", usar_marca=True, **arriba):
    respuesta.clear()
    respuesta.update({"titulo": "Prueba", "descripcion": "Texto para publicar", "fondo_colores": ["#0F0F13"],
                      "fondo_prompt_imagen": "", "capas": capas, **arriba})
    pedidos.clear()
    fotos.clear()
    return diseno_ia.crear("Anuncio de pizza 2x1", tipo, usar_marca)


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
                                "marca_personal"}

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
    r = crear(flyer, "flyer", usar_marca=False)
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
    assert len(r["avisos"]) == 2 and all("cuota agotada" in a and "Ninguna opción" not in a for a in r["avisos"])
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

    def rotar(uso, tareas, *_):
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
    ia.texto_json = lambda *a: ["no", "es", "un", "objeto"]
    falla(diseno_ia.crear, "x", error=RuntimeError)
    ia.texto_json = texto_json
    for tipo in ("video", "", None, ["post"], "POST"):
        falla(diseno_ia.crear, "pizza", tipo)
    for pedido in ("", "   ", None):
        falla(diseno_ia.crear, pedido)
    assert set(diseno.CARPETA.iterdir()) == antes

    # ---------- La herramienta MCP ----------
    import mcp_server  # noqa: E402
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
    assert len(herramientas) == 11 and all(hasattr(getattr(mcp_server, h), "__wrapped__") for h in herramientas)
    assert set(herramientas["crear_diseno"].input_schema["properties"]) == {"pedido", "tipo", "usar_marca"}
    assert "Diseña una pieza" in herramientas["crear_diseno"].description  # el envoltorio no se come la descripción
assert "crear_diseno" in conexion_mcp.probar()  # el servidor arranca y la lista
print("Pruebas de la IA diseñadora pasadas.")
