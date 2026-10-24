"""La IA diseña en capas editables: pide el diseño a la IA de texto (en porcentajes del lienzo), lo pasa a píxeles,
lo limpia, genera las fotos con la IA de imágenes, lo guarda en su carpeta y exporta una vista previa PNG."""
import math
from fractions import Fraction
from typing import Callable

from PySide6.QtGui import QColor, QFont, QTextDocument, QTextOption

from . import diseno, ia, marca, recursos
from .idioma import actual, IDIOMAS, t

MAX_CAPAS, MAX_FOTOS = 14, 2  # el gasto (cada foto es una imagen de IA) y el tiempo no los decide la IA
_PALETA = ["#0F0F13", "#FF4D8D"]  # sin marca: fondo y acento
_SIN_TEXTO = ", no text, no letters, no logos, no watermark"  # los modelos de imagen meten letras inventadas

# tipo: (tamaño de diseno.TAMANOS, pistas de diseño)
TIPOS = {
    "anuncio": ("vertical", "Anuncio para Meta o TikTok: foto protagonista del producto o servicio, titular de 2 a 5 "
                            "palabras con el beneficio, la oferta o el precio dentro de una forma de color, y una "
                            "llamada a la acción corta («Pide ya», «Escríbenos») en un botón."),
    "post": ("post", "Post cuadrado para redes: una sola idea, un titular grande y como mucho una frase de apoyo. "
                     "Foto o fondo con personalidad."),
    "historia": ("historia", "Historia o Reel vertical: deja libre y de 0 a 12 y de 85 a 100 (ahí la app pone sus "
                             "botones). Titular grande en el centro-alto y llamada a la acción abajo (por encima de "
                             "y 85)."),
    "miniatura": ("miniatura", "Miniatura de YouTube: se ve en pequeño. 2 a 5 palabras ENORMES con sombra, contraste "
                               "máximo, una foto expresiva a un lado y nada de texto pequeño."),
    "flyer": ("flyer", "Flyer A4 para imprimir: titular arriba, una foto grande, 3 o 4 datos clave (fecha, lugar, "
                       "precio) con iconos y el contacto abajo. Márgenes del 6 %."),
    "logo": ("logo", "Logo: sin fotos. Un icono o una forma simple y el nombre de la marca con una buena fuente, "
                     "centrado y con mucho aire. Fondo liso."),
    "tarjeta": ("tarjeta", "Tarjeta de presentación horizontal: sin fotos. Nombre grande, cargo o servicio, y 2 o 3 "
                           "datos de contacto con iconos (phone, mail, map-pin, globe). Fondo liso o degradado suave."),
    "marca_personal": ("post", "Post de marca personal que presenta a la persona: foto retrato, nombre grande, a qué "
                               "se dedica en una línea y una frase con su propuesta de valor."),
    "presentacion": ("miniatura", "Diapositiva de presentación 16:9 (como PowerPoint o Keynote): un título grande, un "
                                  "subtítulo corto, una foto o un icono grande a un lado, mucho aire y todo alineado a "
                                  "una misma rejilla. Nada de párrafos."),
}

_N, _T, _B = {"type": "number"}, {"type": "string"}, {"type": "boolean"}
_CAPA = {"tipo": {"type": "string", "enum": ["texto", "imagen", "forma", "icono", "emoji"]},
         "x": _N, "y": _N, "ancho": _N, "alto": _N, "texto": _T, "fuente": _T, "tamano": _N, "color": _T,
         "negrita": _B, "alineacion": {"type": "string", "enum": ["izquierda", "centro", "derecha"]}, "sombra": _B,
         "forma": {"type": "string", "enum": ["rectangulo", "elipse", "linea"]}, "redondeo": _N, "opacidad": _N,
         "icono": _T, "prompt_imagen": _T}
# Plano (capas de un solo tipo de objeto) y estricto: es lo que mejor sale a las IA pequeñas y gratis. De cada capa
# solo es obligatoria la caja: las IA pequeñas no mandan los campos que su tipo no usa, y ia.texto_json quitaría la
# capa (o rechazaría la respuesta entera) aunque _convertir ya sabe trabajar sin ellos.
ESQUEMA = {
    "type": "object",
    "properties": {"titulo": _T, "descripcion": _T, "fondo_colores": {"type": "array", "items": _T},
                   "fondo_prompt_imagen": _T,
                   "capas": {"type": "array", "items": {"type": "object", "properties": _CAPA,
                                                        "required": ["tipo", "x", "y", "ancho", "alto"],
                                                        "additionalProperties": False}}},
    "required": ["titulo", "descripcion", "fondo_colores", "fondo_prompt_imagen", "capas"],
    "additionalProperties": False,
}

INSTRUCCIONES = """Eres un diseñador gráfico senior (nivel Canva / Adobe Express). Diseñas la pieza que pide el
usuario en capas editables, con criterio profesional.

Medidas en PORCENTAJE del lienzo: todos los números (x, y, ancho, alto, tamano) van de 0 a 100; nunca píxeles.
x y ancho son % del ancho del lienzo; y y alto, % del alto. (x, y) es la esquina de arriba a la izquierda de la caja.
tamano (de un texto) = alto de la letra en % del alto del lienzo.
Las capas se pintan en orden: la primera queda al fondo y la última, encima. Las formas y fotos que van detrás de un
texto van ANTES que ese texto; los textos, al final.

Reglas de diseño:
- Márgenes: nada importante a menos del 5 % del borde. Alinea las cajas entre sí (mismo x, o centradas).
- Jerarquía clara: un titular grande (tamano 7 a 14), como mucho una frase de apoyo (tamano 3 a 5) y algún dato
  pequeño (tamano 2 a 3). El alto de la caja de un texto es al menos tamano × 1,3 × número de líneas.
- Poco texto: titular de 2 a 6 palabras, nada de párrafos, sin faltas de ortografía.
- Como mucho 2 fuentes, de la lista que te dan: una para títulos y otra para textos.
- Contraste: texto claro sobre fondo oscuro o al revés. Encima de una foto, pon debajo del texto una forma oscura con
  opacidad 40 a 60, o activa la sombra del texto.
- Colores en formato #RRGGBB, de 2 a 4 en toda la pieza.
- Fotos: capa «imagen» con prompt_imagen en inglés, fotográfico y concreto, SIN texto, letras ni logos dentro de la
  foto. Como mucho 2 fotos contando la de fondo. Para una foto de fondo usa fondo_prompt_imagen (y deja un color de
  respaldo en fondo_colores).
- Iconos de Lucide por su nombre en inglés, por ejemplo: phone, mail, map-pin, globe, clock, calendar, star, heart,
  check, gift, tag, truck, shopping-cart, sparkles, zap, award, percent, message-circle, utensils, coffee.
- Formas: botones (rectangulo con redondeo 50), bandas de color, círculos detrás de un precio, líneas separadoras.
  redondeo = % del lado corto de la caja (50 = píldora o círculo).
- opacidad solo en las formas (100 = sin transparencia); textos, iconos y fotos salen siempre al 100.
- Como mucho 12 capas. Si te sobran, quita decoración; nunca el titular ni la llamada a la acción.

Cada capa lleva tipo, x, y, ancho y alto, y además los campos de su tipo:
- texto: texto, fuente, tamano, color, negrita, alineacion, sombra.   - imagen: prompt_imagen, redondeo.
- forma: forma, color (el relleno), redondeo, opacidad.   - icono: icono, color.   - emoji: texto (un solo emoji).
Ejemplo de capa de texto: {"tipo": "texto", "x": 10, "y": 8, "ancho": 80, "alto": 15, "texto": "PIZZA 2x1",
"fuente": "Bebas Neue", "tamano": 10, "color": "#FFFFFF", "negrita": true, "alineacion": "centro", "sombra": true}
fondo_colores: 1 color liso, o 2 o 3 para un degradado de arriba a abajo. fondo_prompt_imagen: "" si no hay foto de
fondo. titulo: nombre corto del diseño. descripcion: texto breve para publicarlo (o para qué sirve, si es un logo o
una tarjeta). Textos en el idioma del pedido (por defecto: """ + IDIOMAS[actual()] + "); prompt_imagen siempre en inglés."


def _num(v, minimo: float, maximo: float, defecto: float) -> float:
    """El número de la IA dentro de su rango; NaN, infinito, texto o nada dan el valor por defecto."""
    try:
        v = float(v)
    except (TypeError, ValueError, OverflowError):
        v = defecto
    return min(max(v if math.isfinite(v) else defecto, minimo), maximo)


def _txt(v, maximo: int) -> str:
    return v.strip()[:maximo] if isinstance(v, str) else ""


def _color(v, defecto: str) -> str:
    """#RRGGBB; también entiende «red» o «#fff». Lo que no es un color da el valor por defecto."""
    c = QColor(v) if isinstance(v, str) and len(v) <= 30 else QColor()
    return c.name().upper() if c.isValid() else defecto


def _luz(color: str) -> float:
    c = QColor(color)
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def _icono(v, iconos: set) -> str:
    """El icono pedido si existe; si no, el más parecido por nombre o etiquetas; "" si no hay ninguno."""
    nombre = "-".join(_txt(v, 60).lower().split())
    if not nombre or nombre in iconos:
        return nombre
    return (recursos.buscar_iconos(nombre, 1) or [""])[0]


def _de_pixeles(c: dict, ancho: int, alto: int) -> dict:
    """La capa con sus medidas de píxeles pasadas a %; lo que no es un número queda NaN (toma su valor por defecto)."""
    return {**c, **{k: _num(c.get(k), -math.inf, math.inf, math.nan) * 100 / (ancho if k in ("x", "ancho") else alto)
                    for k in ("x", "y", "ancho", "alto", "tamano")}}


def _caja(c: dict, ancho_lienzo: int, alto_lienzo: int) -> dict:
    """La caja en píxeles, siempre dentro del lienzo: las IA a veces la sacan fuera o dan medidas imposibles. Un texto
    mide al menos 1/8 del ancho: en una caja estrechísima saldría una letra por línea (con más, los datos en fila de
    un flyer se pisarían)."""
    ancho = max(ancho_lienzo // 8 if c.get("tipo") == "texto" else 1,
                round(_num(c.get("ancho"), 1, 100, 80) * ancho_lienzo / 100))
    alto = max(1, round(_num(c.get("alto"), 1, 100, 20) * alto_lienzo / 100))
    opacidad = _num(c.get("opacidad"), 0, 100, 100) if c.get("tipo") == "forma" else 100  # solo para las formas
    return {"x": min(round(_num(c.get("x"), 0, 100, 10) * ancho_lienzo / 100), ancho_lienzo - ancho),
            "y": min(round(_num(c.get("y"), 0, 100, 10) * alto_lienzo / 100), alto_lienzo - alto),
            "ancho": ancho, "alto": alto,
            "opacidad": 1 if opacidad < 5 else round(opacidad / 100, 2)}  # un 0 es «campo sin usar», no invisible


def _encajar(capa: dict, minimo: float, alto_lienzo: int) -> None:
    """Baja la letra (hasta `minimo`) hasta que el texto quepa en su caja y, si ni así cabe, agranda la caja (desde su
    centro y dentro del lienzo): las IA calculan mal y el editor recorta lo que se sale. Mide como el editor: un
    QTextDocument que parte las palabras en cualquier punto."""
    doc, opcion, fuente = QTextDocument(), QTextOption(), QFont(capa["fuente"])
    opcion.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(opcion)
    doc.setDocumentMargin(0)
    doc.setTextWidth(capa["ancho"])
    fuente.setBold(capa["negrita"])
    minimo = round(minimo, 1)
    capa["tamano"] = max(capa["tamano"], minimo)  # más pequeña no se lee (y menos en una miniatura)
    while True:
        fuente.setPixelSize(max(1, round(capa["tamano"])))
        doc.setDefaultFont(fuente)
        doc.setPlainText(capa["texto"])
        alto = doc.size().height()
        if ((alto <= capa["alto"] and doc.idealWidth() <= capa["ancho"])
                or (capa["tamano"] <= minimo and alto <= alto_lienzo) or capa["tamano"] <= 1):
            break
        # Por debajo del mínimo solo si ni así cabe en el lienzo (p. ej. muchos saltos de línea)
        capa["tamano"] = max(minimo if capa["tamano"] > minimo else 1, round(capa["tamano"] * 0.9, 1))
    # La caja, justa a las letras (el editor centra el texto y agranda la caja si crece): si no, su caja de sobra
    # pisaría la de otro texto (un botón) y se separarían textos que no se tocan
    alto = min(alto_lienzo, math.ceil(alto))
    capa["y"] = min(max(0, round(capa["y"] + (capa["alto"] - alto) / 2)), alto_lienzo - alto)
    capa["alto"] = alto


def _cortan(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["ancho"] and b["x"] < a["x"] + a["ancho"]
            and a["y"] < b["y"] + b["alto"] and b["y"] < a["y"] + a["alto"])


def _detras(debajo: list[dict], c: dict, fondo: dict, alto: int) -> str:
    """El color que queda detrás del centro de la capa: el de la última forma que lo cubre o el del fondo a esa
    altura; "" si es una foto."""
    cx, cy = c["x"] + c["ancho"] / 2, c["y"] + c["alto"] / 2
    for f in reversed(debajo):
        if (f["tipo"] in ("forma", "imagen") and f.get("forma") != "linea"
                and f["x"] <= cx <= f["x"] + f["ancho"] and f["y"] <= cy <= f["y"] + f["alto"]):
            return f.get("relleno", "")
    colores = fondo["colores"]
    return "" if fondo["tipo"] == "imagen" else colores[min(len(colores) - 1, round(cy / alto * (len(colores) - 1)))]


def _contraste(capas: list[dict], fondo: dict, alto: int) -> None:
    """Que cada texto e icono se lea sobre lo que tiene detrás. Se repite tras las fotos: si una falla, lo que iba
    encima de ella queda sobre otro color."""
    for n, c in enumerate(capas):
        if c["tipo"] in ("texto", "icono"):
            detras = _detras(capas[:n], c, fondo, alto)
            if not detras and c["tipo"] == "texto":
                c["sombra"] = True  # encima de una foto, la sombra lo despega
            elif detras and abs(_luz(c["color"]) - _luz(detras)) < 60:  # del color de lo que tiene detrás: no se vería
                c["color"] = "#111111" if _luz(detras) > 150 else "#FFFFFF"
    for c in [c for c in capas if c.get("sombra")][diseno.MAX_SOMBRAS:]:  # tope del núcleo (exportar sería lento)
        c["sombra"] = False


def _convertir(r: dict, ancho: int, alto: int, fuente_titulo: str, fuente_texto: str, paleta: list[str],
               avisos: list[str]) -> dict:
    """La respuesta de la IA (en %) como diseño del contrato (en píxeles), con todo lo raro ya corregido. Las fotos
    llevan su prompt_imagen (validar lo quita al final). Lo que tiene que quitar lo apunta en avisos."""
    fuentes = {f.lower(): f for f in recursos.fuentes()}
    iconos = set(recursos.iconos())
    colores = r.get("fondo_colores") if isinstance(r.get("fondo_colores"), list) else []
    colores = [c for c in (_color(v, "") for v in colores[:3]) if c] or paleta[:1]
    fondo = {"tipo": "degradado" if len(colores) > 1 else "color", "colores": colores, "imagen": ""}
    fotos = 0
    if prompt := _txt(r.get("fondo_prompt_imagen"), 600):
        fondo, fotos = {"tipo": "imagen", "colores": colores[:1], "imagen": "fondo.png", "prompt_imagen": prompt}, 1
    color_texto = "#111111" if fondo["tipo"] != "imagen" and _luz(colores[0]) > 150 else "#FFFFFF"
    # 100 como mucho por el tiempo de CPU; el recorte a MAX_CAPAS va después, para no perder el titular del final
    lista = [c for c in (r.get("capas") if isinstance(r.get("capas"), list) else [])[:100] if isinstance(c, dict)]
    # Las IA pequeñas a veces responden en píxeles: si en la mayoría de las capas algo pasa de 100, todo va en píxeles
    en_pixeles = sum(any(_num(c.get(k), 0, math.inf, 0) > 100 for k in ("x", "y", "ancho", "alto")) for c in lista)
    if en_pixeles > len(lista) / 2 or any(_num(c.get(k), 0, math.inf, 0) > 300 for c in lista
                                          for k in ("x", "y", "ancho", "alto")):
        lista = [_de_pixeles(c, ancho, alto) for c in lista]
    capas = []
    for c in lista:
        tipo, texto, caja = c.get("tipo"), _txt(c.get("texto"), 200), _caja(c, ancho, alto)
        redondeo = round(_num(c.get("redondeo"), 0, 50, 0) * min(caja["ancho"], caja["alto"]) / 100)
        if tipo == "texto" and texto:
            negrita = c.get("negrita") is True
            capa = {"texto": texto, "fuente": fuentes.get(_txt(c.get("fuente"), 100).lower())
                    or (fuente_titulo if negrita else fuente_texto),
                    "tamano": round(_num(c.get("tamano"), 1, 30, 6) * alto / 100, 1),
                    "color": _color(c.get("color"), color_texto), "negrita": negrita,
                    "alineacion": c["alineacion"] if c.get("alineacion") in ("izquierda", "centro", "derecha")
                    else "centro", "sombra": c.get("sombra") is True}
        elif tipo == "imagen" and (prompt := _txt(c.get("prompt_imagen"), 600)) and fotos < MAX_FOTOS:
            fotos += 1
            capa = {"archivo": f"foto-{fotos}.png", "ajuste": "cubrir", "redondeo": redondeo, "prompt_imagen": prompt}
        elif tipo == "forma":
            forma = c["forma"] if c.get("forma") in ("rectangulo", "elipse", "linea") else "rectangulo"
            capa = {"forma": forma, "relleno": _color(c.get("color"), paleta[1]), "redondeo": redondeo,
                    "grosor_borde": max(2, round(min(ancho, alto) / 250)) if forma == "linea" else 0}
        elif tipo == "icono" and (nombre := _icono(c.get("icono"), iconos)):
            capa = {"nombre": nombre, "color": _color(c.get("color"), color_texto)}
        elif tipo == "emoji" and texto:
            capa = {"texto": texto[:8]}
        else:
            continue
        capas.append({"tipo": tipo, **caja, **capa})
    while len(capas) > MAX_CAPAS:  # sobra decoración: se quita del final, y un texto (titular, contacto) lo último
        del capas[next((i for i in reversed(range(len(capas))) if capas[i]["tipo"] != "texto"), -1)]
    # Textos, iconos y emojis encima, sin cambiar el orden entre ellas: una forma opaca puesta después taparía el texto
    capas.sort(key=lambda c: c["tipo"] in ("texto", "icono", "emoji"))
    textos = []
    for capa in [c for c in capas if c["tipo"] == "texto"]:
        _encajar(capa, min(ancho, alto) / 45, alto)
        while otra := next((t for t in textos if _cortan(capa, t)), None):  # montados no se leen: se baja
            capa["y"] = otra["y"] + otra["alto"] + round(alto / 100)
        if capa["y"] + capa["alto"] <= alto:
            textos.append(capa)
        else:
            capas = [c for c in capas if c is not capa]
            avisos.append(t("El texto «{frase}» no cabía sin tapar otro texto. Se quitó.", frase=capa["texto"][:40]))
    _contraste(capas, fondo, alto)
    glifos = 0
    for c in list(capas):  # con demasiados emojis grandes diseno.validar rechazaría el diseño entero
        peso = diseno._pixeles_emoji(c)
        if glifos + peso > diseno.MAX_PIXELES_EMOJI:
            capas = [x for x in capas if x is not c]
            avisos.append(t("«{frase}» llevaba demasiados emojis grandes. Se quitó.", frase=c["texto"][:40]))
        else:
            glifos += peso
    return {"nombre": _txt(r.get("titulo"), 120) or t("Diseño con IA"), "ancho": ancho, "alto": alto, "fondo": fondo,
            "capas": capas}


def crear(pedido: str, tipo: str = "post", usar_marca: bool = True,
          aviso: Callable[[str, float], None] = lambda t, f: None, propuesta: dict | None = None) -> dict:
    """Diseño completo y editable desde un pedido: lo guarda en su carpeta y exporta una vista previa PNG.
    propuesta: el diseño ya hecho (forma de ESQUEMA, en %) por quien maneja el estudio; entonces no se usa la IA de
    texto (las fotos sí se generan, y el diseño pasa por las mismas comprobaciones)."""
    pedido = str(pedido or "").strip()[:2000]  # da para cualquier pieza; más solo gasta tokens de la IA de texto
    if propuesta is not None:  # se comprueba antes de crear nada
        propuesta = ia.de_fuera(propuesta, ESQUEMA, t("El diseño"))
    elif not pedido:
        raise ValueError(t("Escribe qué diseño quieres."))
    if not isinstance(tipo, str) or tipo not in TIPOS:
        raise ValueError(t("Tipo de diseño desconocido ({tipo!r:.30}); valen {tipos}.", tipo=tipo,
                           tipos=", ".join(TIPOS)))
    diseno.asegurar_qt()  # medir los textos necesita Qt y las fuentes de assets/ registradas
    tamano, pistas = TIPOS[tipo]
    ancho, alto, _ = diseno.TAMANOS[tamano]
    m, fuentes = marca.cargar(), recursos.fuentes()
    fuente_titulo, fuente_texto = (m[k] if usar_marca and m[k] in fuentes else marca.POR_DEFECTO[k]
                                   for k in ("fuente_titulo", "fuente_texto"))
    paleta = (m["colores"] if usar_marca else []) + _PALETA
    logo = marca.ruta_logo() if usar_marca and tipo != "logo" else None
    lado, margen = round(min(ancho, alto) * 0.14), round(min(ancho, alto) * 0.04)
    # En una historia, por encima del 15 % de abajo, donde la app pone sus botones
    logo_x, logo_y = ancho - lado - margen, (round(alto * 0.85) if tipo == "historia" else alto) - lado - margen

    # Nada de píxeles en el pedido: la IA los copiaría en vez de usar %
    proporcion = Fraction(ancho, alto).limit_denominator(20)
    lineas = [f"Pedido: {pedido}", f"Pieza: {tipo.replace('_', ' ')}. {pistas}",
              f"Lienzo {'cuadrado' if ancho == alto else 'vertical' if alto > ancho else 'horizontal'}, proporción "
              f"{proporcion.numerator}:{proporcion.denominator}. Para que un círculo, un cuadrado o un emoji salgan "
              f"proporcionados, alto = ancho × {ancho / alto:.2f}. Con ancho 80 y tamano 10 caben unas "
              f"{80 * ancho / (10 * alto * 0.55):.0f} letras por línea.",
              f"Fuentes que puedes usar: {', '.join(fuentes)}."]
    if usar_marca:
        datos = [f"{que}: {valor}" for que, valor in (("nombre", m["nombre"]), ("eslogan", m["eslogan"]),
                                                       ("colores", ", ".join(m["colores"])), ("tono", m["tono"]))
                 if valor] + [f"fuente de títulos {fuente_titulo} y de textos {fuente_texto}"]
        lineas.append(f"Marca del usuario (respétala): {'; '.join(datos)}.")
    else:
        lineas.append("Elige tú los colores y las fuentes (de la lista) que mejor vayan con el pedido.")
    if logo:
        lineas.append(f"Su logo se añade solo abajo a la derecha: deja libre la zona de x {100 * logo_x / ancho:.0f} a "
                      f"100 e y {100 * logo_y / alto:.0f} a {100 * (logo_y + lado + margen) / alto:.0f}, y no dibujes "
                      "otro logo.")

    if propuesta is None:
        aviso(t("La IA está diseñando…"), 0.05)
    r = propuesta if propuesta is not None else ia.texto_json(INSTRUCCIONES, "\n".join(lineas), ESQUEMA)
    r = r if isinstance(r, dict) else {}
    avisos = []
    d = _convertir(r, ancho, alto, fuente_titulo, fuente_texto, paleta, avisos)
    if not d["capas"]:
        raise RuntimeError(t("La IA no devolvió ninguna capa que se pueda usar. Inténtalo de nuevo o cambia el "
                             "pedido."))

    carpeta = diseno.nueva_carpeta(d["nombre"])
    fotos = ([d["fondo"]] if d["fondo"]["tipo"] == "imagen" else []) + [c for c in d["capas"] if c["tipo"] == "imagen"]
    for n, foto in enumerate(fotos, 1):
        paso = 0.2 + 0.65 * (n - 1) / len(fotos)
        aviso(t("Foto {n} de {total}…", n=n, total=len(fotos)), paso)
        es_fondo = foto is d["fondo"]
        try:
            # Al tamaño de su caja; los servicios no hacen imágenes de menos de 64 px
            ia.imagen(foto["prompt_imagen"] + _SIN_TEXTO, max(64, ancho if es_fondo else foto["ancho"]),
                      max(64, alto if es_fondo else foto["alto"]),
                      carpeta / "imagenes" / (foto["imagen"] if es_fondo else foto["archivo"]))
        except Exception as error:  # cuota agotada o servicio caído: el diseño sale igual, sin esa foto
            causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
            if es_fondo:
                d["fondo"] = {"tipo": "degradado", "colores": paleta[:2], "imagen": ""}
                nota = t("La foto de fondo no salió ({causa}). Se usó un degradado de color.", causa=causa)
            else:
                d["capas"] = [c for c in d["capas"] if c is not foto]
                nota = t("La foto {n} no salió ({causa}). Se quitó esa capa.", n=n, causa=causa)
            avisos.append(nota)
            aviso(nota, paso)
    _contraste(d["capas"], d["fondo"], alto)
    if logo:
        try:
            d["capas"].append({"tipo": "imagen", "archivo": diseno.importar_imagen(str(logo), carpeta),
                               "ajuste": "contener", "x": logo_x, "y": logo_y, "ancho": lado, "alto": lado})
        except ValueError as e:
            avisos.append(t("No se pudo poner el logo de la marca ({error}).", error=e))

    aviso(t("Guardando el diseño y la vista previa…"), 0.9)
    d = diseno.validar(d)
    diseno.guardar(d, carpeta)
    png = diseno.exportar(d, carpeta, carpeta / "vista_previa.png")
    aviso(t("¡Listo! Con {n} aviso(s).", n=len(avisos)) if avisos else t("¡Listo!"), 1.0)
    return {"tipo": "diseno", "carpeta": str(carpeta), "archivo": str(png), "diseno": d, "avisos": avisos,
            "titulo": d["nombre"], "descripcion": _txt(r.get("descripcion"), 1000)}
