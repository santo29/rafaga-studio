"""El cerebro del estudio: la IA de texto VE las fotos que se le dan, el Director actúa sin interrogar, el guion respeta
la estructura del usuario (escenas numeradas, sin narración, texto en pantalla), la memoria (marca y últimos trabajos)
y el repaso de ortografía nunca pasa a una IA de pago. Sin red ni claves de verdad: python -m pruebas.cerebro"""
import base64
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from motor import (anuncios, claves, desde_prompt, director, diseno, herramientas, ia, marca, memoria,  # noqa: E402
                   shorts, video)

diseno.asegurar_qt()
app = QApplication.instance()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-cerebro-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
memoria.ARCHIVO, marca.ARCHIVO = tmp / "memoria.json", tmp / "marca.json"
shorts.PROYECTOS = desde_prompt.PROYECTOS = anuncios.PROYECTOS = tmp / "proyectos"
CLAUDE = {"proveedor": "anthropic", "clave": "sk-ant-prueba", "usos": ["texto"]}
GROQ = {"proveedor": "groq", "clave": "gsk_prueba", "usos": ["texto"]}
OPENAI = {"proveedor": "openai", "clave": "sk-prueba", "usos": ["texto"], "modelo_texto": "gpt-5"}


def conectar(*infos):
    for archivo in (claves.ARCHIVO, claves.AJUSTES, claves.CONEXIONES):
        archivo.unlink(missing_ok=True)
    for info in infos:
        claves.guardar(info)


def foto(nombre="hamburguesa.png", w=1600, h=900) -> Path:
    imagen = QImage(w, h, QImage.Format_RGB32)
    imagen.fill(QColor("#C8102E"))
    assert imagen.save(str(tmp / nombre))
    return tmp / nombre


def imagenes(pedido) -> list[dict]:
    return [b for b in pedido if b.get("type") in ("image", "image_url")] if isinstance(pedido, list) else []


FOTO = foto()

# ---------- 1. Visión: las fotos van como imagen a la IA que las ve; a las demás, solo el texto ----------
conectar()
assert ia.con_fotos("pedido", [FOTO]) == "pedido"  # sin IA de texto conectada (la gratis no ve fotos)
conectar(GROQ)
assert ia.con_fotos("pedido", [FOTO]) == "pedido"  # Groq no ve fotos
conectar(CLAUDE)
pedido = ia.con_fotos("pedido", [FOTO, tmp / "no_existe.png", tmp / "video.mp4", "\\\\servidor\\c\\x.png"])
assert isinstance(pedido, list) and pedido[0] == {"type": "text", "text": "pedido"}, pedido
bloque = imagenes(pedido)
assert len(bloque) == 1 and bloque[0]["source"]["media_type"] == "image/jpeg", pedido  # lo que no es foto, fuera
jpeg = QImage.fromData(base64.b64decode(bloque[0]["source"]["data"]))
assert (jpeg.width(), jpeg.height()) == (768, 432), jpeg.size()  # pequeña: unos 800 tokens, no 2.000
muchas = [foto(f"f{i}.png", 64, 64) for i in range(6)]
assert len(imagenes(ia.con_fotos("x", muchas))) == ia.MAX_FOTOS_VISTAS
# Cada IA, en su forma: Claude «image», OpenAI y Gemini «image_url», Groq y la gratis solo el texto
assert ia._para(CLAUDE, pedido) is pedido
abierta = ia._para(OPENAI, pedido)
assert abierta[-1]["type"] == "image_url" and abierta[-1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
assert ia._para(GROQ, pedido) == "pedido\n\nFoto hamburguesa.png:" and ia._para({}, "solo") == "solo"

# Claude no atiende: la siguiente (Groq) recibe el texto, sin fotos que no puede leer
recibidos = []
texto_con_real = ia._texto_con


def falso(c, instrucciones, pedido, esquema, rapido=False):
    recibidos.append((c["proveedor"], pedido))
    if c["proveedor"] == "anthropic":
        raise ia.SinServicio("529 overloaded")
    return {"ok": "sí"}


ia._texto_con = falso
try:
    conectar(CLAUDE, GROQ)
    esquema = {"type": "object", "properties": {"ok": {"type": "string"}}, "required": ["ok"]}
    assert ia.texto_json("i", ia.con_fotos("mira esto", [FOTO]), esquema) == {"ok": "sí"}
    assert [p for p, _ in recibidos] == ["anthropic", "groq"], recibidos
    assert imagenes(recibidos[0][1]) and recibidos[1][1] == "mira esto\n\nFoto hamburguesa.png:", recibidos
finally:
    ia._texto_con = texto_con_real

# ---------- 2. Ortografía: si Groq (gratis) no atiende, sin repaso; nunca se paga a Claude por él ----------
usadas = []


def corrector(c, instrucciones, pedido, esquema, rapido=False):
    usadas.append(c["proveedor"])
    if c["proveedor"] == "groq":
        raise ia.SinServicio("401 Invalid API Key")
    return {"textos": json.loads(pedido)["textos"]}


ia._texto_con = corrector
try:
    conectar(CLAUDE, GROQ)
    claves.elegir_por_defecto("texto", "anthropic")
    notas = []
    assert ia.ortografia(["Miren que bien"], "es", notas) == ["Miren que bien"]
    assert usadas == ["groq"] and notas and "Groq" in notas[0], (usadas, notas)  # se pidió a Groq y no a Claude
    # Groq ya se sabe caducado: ni se le pide a él ni a Claude, y se dice
    claves.recordar("groq", 401, "Invalid API Key")
    usadas.clear()
    notas = []
    assert ia.ortografia(["Miren que bien"], "es", notas) == ["Miren que bien"] and usadas == [], usadas
    assert notas and notas[0].startswith("No se pudo repasar la ortografía (Groq:"), notas
    # Sin Groq, la elegida (no hay otra gratis que la sustituya)
    conectar(CLAUDE)
    assert ia.ortografia(["Hola"], "es") == ["Hola"] and usadas == ["anthropic"], usadas
finally:
    ia._texto_con = texto_con_real

# ---------- 3. El Director: «foto + versión de anuncio» va directo a crear_anuncios con la foto, sin preguntar ----
vistos, preguntas, hechos = [], [], []


def director_falso(c, instrucciones, pedido, esquema, rapido=False):
    vistos.append((instrucciones, pedido))
    if len(vistos) > 1:  # el segundo paso: ya está hecho
        return {"mensaje": "Listo: tus anuncios están en «Anuncios».", "herramienta": "", "argumentos": "{}"}
    if not imagenes(pedido):  # sin ver la foto, una IA preguntaría qué es
        return {"mensaje": "¿Qué producto es?", "herramienta": "", "argumentos": "{}"}
    return {"mensaje": "Hago tres anuncios con tu hamburguesa.", "herramienta": "crear_anuncios",
            "argumentos": json.dumps({"foto": str(FOTO), "producto": "Hamburguesa doble"})}


crear_real = anuncios.crear
anuncios.crear = lambda foto, producto, *a, **k: hechos.append((foto, producto)) or {"resultados": []}
ia._texto_con = director_falso
try:
    conectar(CLAUDE)
    r = director.dirigir("hazme una versión de anuncio", adjuntos=[str(FOTO)], confirmar=preguntas.append)
    assert hechos == [(str(FOTO), "Hamburguesa doble")] and preguntas == [], (hechos, preguntas)
    assert r["pasos"][0]["herramienta"] == "crear_anuncios" and not r["pasos"][0]["resultado"].startswith("ERROR")
    # La foto la vio en el primer paso (una vez: cada foto se paga en cada paso), y su ruta va en el pedido
    assert imagenes(vistos[0][1]) and isinstance(vistos[1][1], str), vistos
    assert f"Archivos que te doy: {json.dumps([str(FOTO)], ensure_ascii=False)}" in vistos[0][1][0]["text"]
    # Las reglas: actuar con lo que supone, no interrogar
    assert "si el pedido se entiende, lo haces ya" in vistos[0][0] and "Nunca preguntes lo que se ve" in vistos[0][0]
    assert "solo lo imprescindible: la foto" not in director.INSTRUCCIONES
    # La página ya puso la ruta en el pedido: no se repite
    vistos.clear()
    pedido_pagina = f"hazme una versión de anuncio\n\nArchivos que te doy: {json.dumps([str(FOTO)])}"
    director.dirigir(pedido_pagina, adjuntos=[str(FOTO)])
    assert vistos[0][1][0]["text"].count("Archivos que te doy") == 1
    # Con Groq (no ve fotos): el pedido va en texto, con la ruta
    conectar(GROQ)
    vistos.clear()
    director.dirigir("hazme una versión de anuncio", adjuntos=[str(FOTO)])
    assert isinstance(vistos[0][1], str) and str(FOTO).replace("\\", "\\\\") in vistos[0][1], vistos[0][1]
finally:
    ia._texto_con, anuncios.crear = texto_con_real, crear_real
assert "producto" in herramientas.crear_anuncios.__doc__ and \
    herramientas.inspect.signature(herramientas.crear_anuncios).parameters["producto"].default == ""

# ---------- 4. Memoria: la marca y los últimos trabajos llegan al Director y a los especialistas ----------
conectar()
marca.guardar({**marca.POR_DEFECTO, "nombre": "Santo La Para", "tono": "cercano", "colores": ["#C8102E"]})
memoria.recordar("general", "títulos cortos")
proyecto = tmp / "proyectos" / "20261030-081357-video"
proyecto.mkdir(parents=True)
(proyecto / "proyecto.json").write_text(json.dumps({"tipo": "video", "titulo": "La hamburguesa artesanal",
                                                    "prompt": "Crea un video publicitario de una hamburguesa",
                                                    "resultados": []}), encoding="utf-8")
assert "Santo La Para" in memoria.para("video") and "títulos cortos" in memoria.para("video")
assert "Santo La Para" not in memoria.para("diseno")  # Diseño la usa con su casilla «usar mi marca»
instrucciones_vistas = []
pensar_real = ia.texto_json
ia.texto_json = lambda instrucciones, contenido, esquema, **k: instrucciones_vistas.append((instrucciones, contenido)) \
    or {"mensaje": "Hola.", "herramienta": "", "argumentos": "{}"}
try:
    # La conversación guardada de otra sesión: lo que no tenga la forma de un mensaje se salta, no rompe
    historial = [{"rol": "usuario", "texto": "hola"}, {"rol": "director"}, "basura", None,
                 {"rol": "director", "texto": "Hola, ¿qué hacemos?", "hecho": "Hecho: crear_video → C:/v.mp4"}]
    assert director.dirigir("otro como el de la hamburguesa", historial)["mensaje"] == "Hola."
    instrucciones, contenido = instrucciones_vistas[-1]
    assert "Santo La Para" in instrucciones and "La hamburguesa artesanal" in instrucciones
    assert "títulos cortos" in instrucciones and "Hola, ¿qué hacemos?" in contenido
finally:
    ia.texto_json = pensar_real

# ---------- 5. El guion: escenas numeradas, sin narración y el texto en pantalla, como los pidió ----------
HAMBURGUESA = """Video publicitario de una hamburguesa artesanal, 30 segundos.
ESCENA 1 (0-4 segundos): INGREDIENTES
ESCENA 2 (4-9 segundos): PREPARACIÓN
ESCENA 3 (9-14 segundos): COCCIÓN
ESCENA 4 (14-20 segundos): MONTAJE
ESCENA 5 (20-25 segundos): PRESENTACIÓN
ESCENA 6 (25-30 segundos): ANUNCIO FINAL con el texto "EL SABOR QUE TE HACE VOLVER"
Sonidos ASMR de cocina, música moderna. Sin narración."""
assert desde_prompt.escenas_pedidas(HAMBURGUESA) == 6 and desde_prompt.sin_voz(HAMBURGUESA)
assert desde_prompt.escenas_pedidas("Scene 1: a fox\nScene 2: a river\n- PLANO 3: el bosque") == 3
assert desde_prompt.escenas_pedidas("en la escena 2 quiero un perro") == 0
assert not desde_prompt.sin_voz("un video de playa con música sin voz y una manzana que habla")
assert desde_prompt.sin_voz("a fox video, no narration") and not desde_prompt.sin_voz("sin voz en off, habla el gato")
# Lo que se pregunta antes de pagar escenas que hablan cuenta las mismas escenas que se harán
assert desde_prompt.costo_hablado(30, HAMBURGUESA)[0] == 6 and desde_prompt.costo_hablado(30)[0] == 4
assert director.FOTOS["crear_video"]({"prompt": HAMBURGUESA, "segundos": 30, "animado": True}) == 6

guiones, montados = [], []
escena = {"narracion": "La IA escribió esto igual.", "imagen": "fresh burger ingredients on a wooden table",
          "movimiento": "slow dolly in; the chef flips the patty, cheese melts, steam rises", "texto_pantalla": ""}
respuesta = {"brief": "Objetivo: antojo. Público: jóvenes. 9:16. Sin voz: ASMR y música.", "titulo": "La hamburguesa",
             "descripcion": "d", "hashtags": ["#hamburguesa"], "estilo_visual": "hyperrealistic food commercial",
             "entendido": "un anuncio de hamburguesa sin voz en 6 escenas",
             "escenas": [{**escena} for _ in range(7)]}  # la IA devolvió una de más
respuesta["escenas"][-1]["texto_pantalla"] = "EL SABOR QUE TE HACE VOLVER"
reales = ia.texto_json, desde_prompt.montar, ia.ortografia
ia.texto_json = lambda instrucciones, pedido, esquema, **k: guiones.append((instrucciones, pedido)) or \
    json.loads(json.dumps(respuesta))
desde_prompt.montar = lambda guion, carpeta, *a, **k: montados.append(guion) or carpeta / "video_final.mp4"


def generar(*a, **k):
    """Cada video en su carpeta de proyectos: dos en el mismo segundo tendrían el mismo nombre."""
    desde_prompt.PROYECTOS = Path(tempfile.mkdtemp(prefix="videos-", dir=tmp))
    return desde_prompt.generar(*a, **k)


try:
    conectar()
    r = generar(HAMBURGUESA, segundos=30)
    guardado = json.loads((Path(r["carpeta"]) / "guion.json").read_text(encoding="utf-8"))
    assert len(guardado["escenas"]) == 6, len(guardado["escenas"])  # las 6 suyas, ni 4 ni 7
    assert all(e["narracion"] == "" for e in guardado["escenas"])  # sin narración: lo impone el código
    assert guardado["escenas"][-1]["texto_pantalla"] == "EL SABOR QUE TE HACE VOLVER"
    assert all("texto_pantalla" in e and e["movimiento"].startswith("slow dolly in") for e in guardado["escenas"])
    assert guardado["brief"].startswith("Objetivo") and montados[-1]["escenas"] == guardado["escenas"]
    instrucciones, pedido = guiones[-1]
    assert "6 escenas: las que numeró el usuario" in pedido and "Sin narración" in pedido
    assert "palabras de narración" not in pedido and "unas 5 escenas" not in pedido
    assert "texto_pantalla" in instrucciones and "movimiento" in instrucciones and "brief" in instrucciones
    assert "Santo La Para" in pedido and "La hamburguesa artesanal" in pedido  # su marca y sus últimos trabajos
    # Animado y sin narración: ninguna escena que habla (se pagarían por nada), ni hace falta quien las haga
    r = generar(HAMBURGUESA, segundos=30, animado=True)
    assert any("sin narración" in a for a in r["avisos"]), r["avisos"]
    # Sin estructura suya, lo de siempre: narrado y unas segundos/6 escenas
    respuesta["escenas"] = [{"narracion": "Hola.", "imagen": "a fox"}] * 4  # un guion sin los campos nuevos vale
    r = generar("un zorro que baila", segundos=30)
    assert "unas 5 escenas" in guiones[-1][1] and "~60 palabras de narración" in guiones[-1][1]
    assert json.loads((Path(r["carpeta"]) / "guion.json").read_text(encoding="utf-8"))["escenas"][0]["narracion"] \
        == "Hola."
    # La foto de partida, con Claude: la ve (no solo su nombre)
    conectar(CLAUDE)
    ia.ortografia = lambda textos, *a, **k: list(textos)
    generar("un video de mi hamburguesa", imagen=str(FOTO), segundos=30)
    assert imagenes(guiones[-1][1]) and "foto de partida" in guiones[-1][1][0]["text"]
finally:
    ia.texto_json, desde_prompt.montar, ia.ortografia = reales
# Una escena sin narración se monta igual: silencio en vez de voz (sin red: no llama a la voz)
mudo = tmp / "muda.mp3"
assert desde_prompt.narrar("", "es-DO-EmilioNeural", mudo) == []
assert abs(video.duracion(mudo) - desde_prompt.SEGUNDOS_MUDA) < 0.3, video.duracion(mudo)

# ---------- 6. Anuncios con solo la foto: la IA que la ve dice qué se anuncia ----------
consultas, planes = [], []
plan = {"variantes": [{"angulo": "antojo", "gancho": "g", "titulo": "t", "texto_anuncio": "x", "hashtags": [],
                       "estilo_visual": "UGC", "escenas": [{"narracion": "Mira.", "imagen": "The product on a table",
                                                            "movimiento": "orbit; steam rises",
                                                            "texto_pantalla": "PÍDELA HOY"}] * 3}]}


def pensar(instrucciones, pedido, esquema, **k):
    assert imagenes(pedido), "la IA de los anuncios tiene que ver la foto"
    if esquema is anuncios.ESQUEMA_FOTO:
        return {"producto": "Hamburguesa doble", "detalles": "con queso cheddar"}
    planes.append(pedido[0]["text"])
    return json.loads(json.dumps(plan))


reales = ia.texto_json, ia.investigar_web, anuncios.montar, video.cierre, ia.ortografia
ia.texto_json, ia.investigar_web = pensar, lambda pregunta: consultas.append(pregunta)
anuncios.montar = lambda v, carpeta, *a, **k: carpeta / "anuncio.mp4"
video.cierre = lambda montado, texto, formato, destino, producto=None: destino
ia.ortografia = lambda textos, *a, **k: list(textos)
try:
    conectar(CLAUDE)
    r = anuncios.crear(str(FOTO), variantes=1, segundos=15)
    assert r["titulo"] == "Anuncios · Hamburguesa doble" and r["producto"] == "Hamburguesa doble", r["titulo"]
    assert "Hamburguesa doble" in consultas[0] and "Producto: Hamburguesa doble" in planes[0]
finally:
    ia.texto_json, ia.investigar_web, anuncios.montar, video.cierre, ia.ortografia = reales

# La página de Anuncios pide solo la foto
from ui.paginas.anuncios import PaginaAnuncios  # noqa: E402

pagina, lanzados = PaginaAnuncios(), []
pagina.lanzar = lambda boton, funcion, **datos: lanzados.append(datos)
pagina.foto = str(FOTO)
pagina._iniciar()
assert lanzados and lanzados[0]["foto"] == str(FOTO) and lanzados[0]["producto"] == "", lanzados
print("Pruebas del cerebro pasadas.")
