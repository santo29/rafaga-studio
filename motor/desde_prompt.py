"""Crea un video completo a partir de un prompt: guion con IA, imágenes, voz, subtítulos y montaje."""
import asyncio
import json
import re
import shutil
import time
from pathlib import Path
from typing import Callable

import edge_tts

from . import claves, ia, memoria, seguro, video
from .idioma import actual, dinero, IDIOMAS, porcentaje, t, texto_de_error
from .shorts import PROYECTOS

# Voces gratuitas de Microsoft Edge. ponytail: no es un modelo abierto; cambiar por Kokoro/Piper si se quiere 100% local.
# El nombre es lo que se ve (traducido); el id de Edge es lo que se usa.
VOCES = {
    t("Emilio (Rep. Dominicana)"): "es-DO-EmilioNeural",
    t("Ramona (Rep. Dominicana)"): "es-DO-RamonaNeural",
    # Las del Caribe, justo después: en una serie, cuando se acaban las dominicanas, suenan más cerca que las otras
    t("Víctor (Puerto Rico)"): "es-PR-VictorNeural",
    t("Karina (Puerto Rico)"): "es-PR-KarinaNeural",
    t("Manuel (Cuba)"): "es-CU-ManuelNeural",
    t("Belkys (Cuba)"): "es-CU-BelkysNeural",
    t("Jorge (México)"): "es-MX-JorgeNeural",
    t("Dalia (México)"): "es-MX-DaliaNeural",
    t("Álvaro (España)"): "es-ES-AlvaroNeural",
    t("Elvira (España)"): "es-ES-ElviraNeural",
    t("Andrew (inglés)"): "en-US-AndrewNeural",
    t("Ava (inglés)"): "en-US-AvaNeural",
    t("Francisca (portugués · Brasil)"): "pt-BR-FranciscaNeural",
    t("Antonio (portugués · Brasil)"): "pt-BR-AntonioNeural",
    t("Denise (francés · Francia)"): "fr-FR-DeniseNeural",
    t("Henri (francés · Francia)"): "fr-FR-HenriNeural",
}


def voz_por_defecto() -> str:
    """La primera voz gratis en el idioma de la app (en español, la de República Dominicana)."""
    return next((v for v in VOCES.values() if v.startswith(f"{actual()}-")), "es-DO-EmilioNeural")

# Opcionales (los guiones de fuera, por el MCP, siguen valiendo sin ellos): brief (lo primero que escribe la IA: el
# plan antes de las escenas), entendido, y en cada escena movimiento (cámara y acción, para la IA de video) y
# texto_pantalla (lo que se lee en pantalla)
ESCENA = {"type": "object",
          "properties": {"narracion": {"type": "string"}, "imagen": {"type": "string"},
                         "movimiento": {"type": "string"}, "texto_pantalla": {"type": "string"}},
          "required": ["narracion", "imagen"], "additionalProperties": False}
ESQUEMA = {
    "type": "object",
    "properties": {
        "brief": {"type": "string"},
        "titulo": {"type": "string"}, "descripcion": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "estilo_visual": {"type": "string"},
        "entendido": {"type": "string"},
        "escenas": {"type": "array", "items": ESCENA},
    },
    "required": ["titulo", "descripcion", "hashtags", "estilo_visual", "escenas"],
    "additionalProperties": False,
}

# Regla común (la misma en Diseño, Director, Dibujos animados y aquí): el pedido puede traer faltas de ortografía.
FALTAS = ia.FALTAS  # la regla común de faltas de ortografía (una sola, en ia.py)

# Cómo se escribe cada escena para la IA de video (aquí y en Anuncios)
MOVIMIENTO = """- movimiento (en inglés, una línea): primero el movimiento de cámara (slow dolly in, dolly out, orbit,
  tracking shot, crane up, pan, handheld, static macro…), después lo que hace el sujeto y por último el entorno y la
  velocidad («slow dolly in; the chef flips the patty, cheese melts, steam rises»). Un solo movimiento de cámara.
- texto_pantalla: el texto que se lee en pantalla en esa escena, corto, o "" si no lleva. El que pidió el usuario va
  palabra por palabra, en su escena."""

INSTRUCCIONES = """Eres director creativo y guionista de una productora de videos para YouTube, TikTok, Instagram y
Facebook. Primero entiendes el pedido como un profesional y luego escribes el plan de rodaje, escena por escena.
- """ + FALTAS + """
- brief (lo primero, de 3 a 6 líneas cortas): objetivo, público, plataforma y formato, gancho, estilo visual y luz,
  sonido (voz, música, sonidos) y texto en pantalla o llamada a la acción. Lo que el usuario no dijo lo decides tú
  con criterio profesional: nunca preguntes.
- entendido: una frase corta, en el idioma del usuario, con lo que entendiste del pedido (sin empezar por «Entendí»).
- Lo que el usuario escribió manda: si numera escenas o planos, haz exactamente esas, en su orden y con lo que pasa
  en cada una; si da tiempos, respétalos; si pide un texto en pantalla, va tal cual en «texto_pantalla» de su escena
  (no lo pases a la narración).
- Sin estructura suya: la primera escena es un gancho que atrapa en 3 segundos y la última cierra con fuerza o
  invita a seguir.
- narracion: 1 o 2 frases (lo que dice la voz). Si pide el video sin voz o sin narración, "" en todas. Si no pide voz
  pero sí música, sonidos o texto en pantalla, la narración es mínima ("" en las escenas que no la necesitan) y no
  hace falta llegar a las palabras de narración del pedido: esas son para cuando todas las escenas hablan.
- imagen: el primer fotograma de la escena, en inglés, muy visual y concreto (sujeto, lugar, encuadre, lente y luz),
  sin texto escrito dentro de la imagen.
""" + MOVIMIENTO + """
- La IA de imágenes y la de video leen cada escena SOLA, sin ver las demás: nunca escribas «the same…», «he», «she»
  ni «it»; nombra y describe siempre lo que sale.
- Si el pedido es un personaje que habla (una fruta, un animal, una calavera, un objeto, una mascota…), la narración la
  dice ESE personaje en primera persona, y la imagen lo muestra hablando a cámara. Nunca una persona que habla de él.
- Describe al protagonista con las mismas palabras en todas las escenas, para que se vea igual en todo el video.
- estilo_visual: un estilo común para todas las imágenes, en inglés, que encaje con el pedido: dibujo animado o
  animación 3D para personajes fantásticos o que hablan, foto de cine para temas reales. Si el usuario pide un estilo,
  ese manda. No mezcles «photo/photorealistic» con «cartoon/3D/Pixar».
- Narración, título, descripción y hashtags en el idioma que pida el usuario (por defecto: """ + IDIOMAS[actual()] + ")."


def idioma_de(voz: str) -> str:
    """La línea del pedido que dice en qué idioma narrar según la voz elegida (vacía si no se sabe, p. ej. ElevenLabs):
    si no, una voz inglesa leería un guion en español."""
    codigo = voz.split("-")[0]
    return f"\nIdioma de la narración: {IDIOMAS[codigo]}" if codigo in IDIOMAS else ""


def idioma_codigo(voz: str) -> str:
    """El idioma de lo que dice la voz elegida (el de la app si no se sabe, p. ej. con ElevenLabs)."""
    codigo = voz.split("-")[0]
    return codigo if codigo in IDIOMAS else actual()


# Lo que dice la voz gratis, por lo bajo (Emilio, de Edge, va a 2,12: 79 palabras en 37,3 s), y el pedido a la IA usa
# la misma cuenta: con 2,5, un guion de 38,6 s pasaba por uno de menos de 33 y no se acortaba
PALABRAS_POR_SEGUNDO = 2.0
# Las de ElevenLabs hablan más rápido (Sarah dijo 62 palabras en 22,3 s: 2,8): con 2,0 un video de 30 s salía de 23,6
PALABRAS_POR_SEGUNDO_ELEVEN = 2.6


def palabras_por_segundo(voz: str) -> float:
    return PALABRAS_POR_SEGUNDO_ELEVEN if voz.startswith("eleven:") else PALABRAS_POR_SEGUNDO


# La narración que el usuario ya escribió en su pedido («Guion / Voz en Off: "…"», «Narración: «…»», «Voice-over:
# "…"»), una línea por escena: va tal cual, ni la IA la reescribe ni se acorta. Entre comillas: «Narración: alegre»
# dice cómo narrar, no lo que se dice. Con un número delante («1. Voz en off: …») o una acotación detrás
# («"Hola." (tono alegre)»): si no, esa línea se perdía sin decir nada y el video salía con una escena menos.
# ponytail: solo con las comillas en la misma línea que la etiqueta; si van debajo, la IA escribe el guion como siempre
_NARRACION = re.compile(r"(?im)^[ \t>*•\d.)-]*(?:gui[oó]n[ \t]*/[ \t]*)?(?:voz en off|narraci[oó]n|narrador|"
                        r"locuci[oó]n|voice[- ]?over|narration|narrator|voix off|narrateur|narra[cç][aã]o|"
                        r"locu[cç][aã]o)(?:[ \t]*\([^)\n]*\))?[ \t*]*:[ \t*]*[\"“«'‘](.+?)[\"”»'’]"
                        r"(?:[ \t]*\([^)\n]*\))?[ \t*]*$")


def narracion_del_usuario(prompt: str) -> list[str]:
    return [x.strip() for x in _NARRACION.findall(prompt) if x.strip()]


# Las escenas que el usuario numeró en su pedido («ESCENA 1 (0-4 segundos):», «Scene 2:», «PLANO 3 -»), también
# seguidas en una sola línea, como las escribe el Director: esas se hacen (pasó: pidió 6 y el código pidió a la IA
# «unas 4 escenas»). Con un separador tras el número: «Toma 2 huevos», «Cena 2 x 1» o «Shot 1 of the city» no son
# escenas («cena» sí lo es en portugués). Y los segundos que le dio a cada una, si los dio («(0-4 segundos)», «(5 s)»)
_ESCENA = re.compile(r"(?im)\b(?:escena|scene|sc[eè]ne|cena|plano|toma|shot)\s*(\d{1,3})(?=\s*[:.()\-–—]|\s*$)"
                     r"(?:\s*\(\s*(?:(\d{1,3}(?:[.,]\d+)?)\s*(?:-|–|—|a|to|à)\s*)?(\d{1,3}(?:[.,]\d+)?)\s*"
                     r"(?:s|seg|sec)\w*\s*\))?")
# El video sin narración, dicho así en el pedido: va vacía (lo impone el código, no la IA). «Sin voz en off» no: un
# personaje puede hablar; eso lo decide la IA
_SIN_VOZ = re.compile(r"(?i)\b(?:sin|no|without|sem|sans)\s+(?:narraci[oó]n|locuci[oó]n|narration|narra[cç][aã]o|"
                      r"locu[cç][aã]o)\b")
# El pedido nombra un estilo («estilo Pixar 3D», «anime», «cinematográfico», «hiperrealista»): ese manda sobre el del
# menú de Crear (pasó: pidió Pixar 3D y salió anime, el que estaba elegido en el menú)
_ESTILO = re.compile(r"(?i)\b(?:estilo|style|pixar|disney|ghibli|anime|manga|cartoon|caricatura|dibujos? animados?|"
                     r"desenhos? animados?|dessins? anim[eé]s?|3d|2d|(?:hiper|hyper|foto|photo)?r[eé]alis\w*|cine\w*|"
                     r"c[oó]mic\w*|acuarela|aquarela|watercolou?r|ilustra\w*|illustra\w*|stop[- ]?motion)\b")
# Música pedida: el video de Crear no la lleva, y se dice
_MUSICA = re.compile(r"(?i)(?<!sin )(?<!sem )(?<!sans )(?<!no )(?<!without )\b(?:m[uú]sica|music|musique)\b")


def _numeradas(prompt: str) -> dict[str, float]:
    """{número de escena: los segundos que le dio el usuario (0 si no dio)}, en su orden. Vacío si numeró menos de
    dos: una sola «Escena 1:» no es una lista de escenas."""
    escenas = {}
    for n, desde, hasta in _ESCENA.findall(prompt or ""):
        if n not in escenas:  # la primera vez: el encabezado (luego puede nombrarla, «como en la escena 1.»)
            a, b = (float(x.replace(",", ".")) if x else 0.0 for x in (desde, hasta))
            escenas[n] = min(max(b - a, 1.0), 30.0) if b > a else 0.0
    return escenas if len(escenas) > 1 else {}


def escenas_pedidas(prompt: str) -> int:
    """Cuántas escenas numeró el usuario en su pedido (0 si no numeró al menos dos)."""
    return len(_numeradas(prompt))


def sin_voz(prompt: str) -> bool:
    """Si pidió el video sin narración (y no la escribió él): sin voz y sin escenas que hablan."""
    return bool(_SIN_VOZ.search(prompt or "")) and not narracion_del_usuario(prompt or "")


def al_tiempo(escenas: list[dict], segundos: float, ritmo: float = PALABRAS_POR_SEGUNDO) -> bool:
    """Acorta un guion cuya narración dura más de lo pedido (con un 10 % de margen): primero deja en su primera frase
    las narraciones de dos frases (las del medio antes que el gancho y el cierre, la más larga primero); luego quita
    escenas del medio, mientras queden más de 3. Devuelve si cambió algo. ritmo: palabras_por_segundo de la voz."""
    def dura():  # + los 0,25 s de cada escena (escena_de_imagen)
        return sum(len(e["narracion"].split()) for e in escenas) / ritmo + 0.25 * len(escenas)
    cambio = False
    while dura() > segundos * 1.1:
        dos = [e for e in escenas if len(re.split(r"(?<=[.!?…])\s+", e["narracion"].strip())) > 1]
        if dos:
            e = max(dos, key=lambda e: (e is not escenas[0] and e is not escenas[-1], len(e["narracion"])))
            e["narracion"] = re.split(r"(?<=[.!?…])\s+", e["narracion"].strip())[0]
        elif len(escenas) > 3:
            escenas.pop(len(escenas) // 2)
        else:
            break
        cambio = True
    return cambio


def voces() -> dict[str, str]:
    """Todas las voces disponibles: las gratis de Edge y las de la cuenta de ElevenLabs si está conectada."""
    eleven = (claves.cargar().get("elevenlabs") or {}).get("voces", [])
    return {**VOCES, **{f"ElevenLabs · {v['nombre']}" + (f" ({v['acento']})" if v["acento"] else ""):
                        f"eleven:{v['id']}" for v in eleven}}


def narrar(texto: str, voz: str, destino: Path, velocidad: float = 1.0) -> list[dict]:
    """Genera la voz y devuelve los tiempos por palabra. voz = id de Edge o 'eleven:<voice_id>'. velocidad: 1 = la
    normal; 1.2 = un 20 % más rápida (lo más que admite ElevenLabs)."""
    # El único paso de texto a voz (videos, anuncios, serie, el Director hablando y la voz del editor): sin esto se
    # oía «asterisco», «almohadilla» o la URL entera, y salía igual en los subtítulos quemados
    texto = ia.sin_markdown(texto, "voz")
    if voz.startswith("eleven:"):
        return ia.voz_elevenlabs(texto, voz.removeprefix("eleven:"), destino, velocidad)
    return con_signos(asyncio.run(_voz(texto, voz, destino, velocidad)), texto)


def _nucleo(palabra: str) -> str:
    return re.sub(r"^\W+|\W+$", "", palabra).lower()


def con_signos(palabras: list[dict], texto: str) -> list[dict]:
    """Edge da cada palabra sin sus signos («Cuál» de «¿Cuál…?»): se le ponen los del texto, para que los subtítulos
    lleven el «¿» y el «¡» y se corten donde acaba cada frase."""
    trozos, k, salida = texto.split(), 0, []
    for p in palabras:
        for j in range(k, min(k + 3, len(trozos))):  # cerca: una palabra que Edge lee distinto no descoloca las demás
            if _nucleo(trozos[j]) == _nucleo(p["palabra"]) != "":
                p, k = {**p, "palabra": trozos[j]}, j + 1
                break
        salida.append(p)
    return salida


# Lo que la IA de imágenes no conoce y dibuja mal (pasó: la güira salió como una espátula, la tambora como un djembé,
# la bandera con un cuartel mal y un billete de dólar en un puesto de yaniqueques): cuando la escena lo nombra, la
# descripción exacta va con el pedido de la imagen.
PESOS = "any money shown is Dominican peso banknotes (colorful RD$ bills), never US dollars"
GLOSARIO = (
    (r"g[uü]iras?", "the Dominican güira is a hand-held metal scraper: a cylinder of perforated, finely ridged "
                    "stainless steel with a handle on top, played by scraping it with a wire-bristle fork (not a "
                    "spatula, not a cheese grater)"),
    (r"tamboras?", "the Dominican tambora is a small two-headed barrel drum lying horizontally on the player's lap, "
                   "struck on one side with a wooden stick and on the other with the bare hand (not a djembe, not a "
                   "conga)"),
    (r"bandera dominicana|bandera de (la )?rep[uú]blica dominicana|dominican (republic )?flag",
     "the flag of the Dominican Republic: a centered white cross divides it into four rectangles, ultramarine blue at "
     "top left and bottom right, vermilion red at top right and bottom left, with the national coat of arms in the "
     "center of the cross"),
    (r"pesos? dominicanos?|dominican pesos?|rd\$[\d.,]*", PESOS),  # con su cifra: el «5» de «RD$500» es \w
    (r"yaniqueques?|johnny ?cakes?", "yaniqueques are large thin golden crispy fried dough discs, sold by Dominican "
                                     "beach vendors stacked in a glass box or a basket"),
    (r"colmados?", "a Dominican colmado is a small corner grocery open to the street, shelves packed with goods, a "
                   "counter behind a metal grille, beer coolers, plastic chairs and music outside"),
    (r"motoconchos?|motoconchistas?", "a Dominican motoconcho is a motorcycle taxi: a small 125cc street motorcycle "
                                      "whose driver carries a passenger on the back seat"),
    (r"mang[uú]", "Dominican mangú is mashed green plantains topped with pickled red onions, served with fried "
                  "salami, fried cheese and eggs"),
    (r"guaguas?", "a Dominican guagua is a crowded, colorful public minibus"),
)


def con_glosario(prompt: str, *textos: str) -> str:
    """El pedido de la imagen con la descripción exacta de lo dominicano que nombran el pedido o la narración."""
    leido = " ".join((prompt, *textos)).lower()
    extras = [d for patron, d in GLOSARIO if re.search(rf"(?<!\w)(?:{patron})(?!\w)", leido)]
    # El dinero, solo en una escena dominicana: en un video de otro país, sus billetes son los suyos
    if PESOS not in extras and (extras or re.search(r"dominican|santo domingo", leido)) and \
            re.search(r"(?<!\w)(?:billetes?|dinero|money|cash|banknotes?|bills?)(?!\w)", leido):
        extras.append(PESOS)
    extras = [d for d in extras if d not in prompt]
    return ". ".join([prompt, *extras]) if extras else prompt


async def _voz(texto: str, voz: str, destino: Path, velocidad: float = 1.0) -> list[dict]:
    palabras = []
    with open(destino, "wb") as f:
        async for trozo in edge_tts.Communicate(texto, voz, rate=f"{round((velocidad - 1) * 100):+d}%",
                                                boundary="WordBoundary").stream():
            if trozo["type"] == "audio":
                f.write(trozo["data"])
            elif trozo["type"] == "WordBoundary":
                ini = trozo["offset"] / 1e7  # viene en unidades de 100 ns
                palabras.append({"palabra": trozo["text"], "inicio": ini, "fin": ini + trozo["duration"] / 1e7})
    return palabras


SEGUNDOS_HABLADO = 8  # lo que dura cada escena animada con voz (Omni hace clips de 3 a 10 s)
MAX_HABLADAS = 15  # tope de gasto por video (~US$12): las escenas de más se hacen con imagen y narración
MAX_CLIPS_PAGO = 15  # con Kling o Seedance para animar, clips de pago por trabajo como mucho: el resto, zoom suave
SEGUNDOS_SIN_VOZ = 3  # lo que dura una escena sin narración (montar): lo justo para leer su texto en pantalla


def proveedor_voz() -> str | None:
    """Quién hace las escenas que hablan («Escenas que hablan» en Claves de IA): Gemini en Automático; Kling o
    Seedance solo si el usuario los eligió. None si no hay ninguno conectado."""
    return (claves.para("video_voz") or {}).get("proveedor")


def costo_hablado(segundos: int, prompt: str = "") -> tuple[int, float]:
    """Cuántas escenas irán animadas con voz y lo más que costarán (US$) con quien las hace (ver ia.precio_video).
    Con las escenas que numeró el usuario en su pedido (prompt), esas: generar hace las mismas. Si lo pidió sin
    narración, ninguna (no se pregunta lo que no se va a pagar)."""
    escenas = 0 if sin_voz(prompt) else min(MAX_HABLADAS, escenas_maximas(segundos, prompt, True))
    return escenas, escenas * ia.precio_video(proveedor_voz() or "gemini", voz=True)


def escenas_maximas(segundos: int, prompt: str = "", animado: bool = False) -> int:
    """Cuántas escenas (y así imágenes) hará generar como mucho: las que numeró el usuario (hasta MAX_HABLADAS) o,
    si no numeró, según los segundos. La usan costo_hablado y director.FOTOS: se pregunta lo que se hará."""
    pedidas = min(escenas_pedidas(prompt), MAX_HABLADAS)
    if animado and not sin_voz(prompt):
        return pedidas or max(1, round(segundos / SEGUNDOS_HABLADO))
    return pedidas or max(3, round(segundos / 6)) + 2


def con_voz_propia() -> bool:
    """Si la casilla «Video animado con IA» de Crear sale marcada: hay quien haga escenas que hablan y la IA de video
    no está apagada. Solo la pantalla, que avisa del costo: el motor nunca gasta sin que se lo pidan (animado=True)."""
    return proveedor_voz() is not None and claves.ajustes().get("video") != "ninguno"


def prompt_hablado(escena: dict, guion: dict) -> str:
    """Lo que se pide a la IA de video con voz para una escena: la imagen, el estilo y la frase que se dice."""
    return (f"{escena['imagen']}. Visual style: {guion['estilo_visual']}. A short clip of about {SEGUNDOS_HABLADO} "
            f"seconds. This line is spoken clearly, word for word, in its own language: \"{escena['narracion']}\". "
            "If a character is on screen, that character says it to the camera with natural lip sync; otherwise a "
            "narrator says it as a voice-over. Soft ambient sound, no music over the voice. No on-screen text, no "
            "captions, no subtitles.")


def generar(prompt: str, formato: str = "9:16", segundos: int = 45, voz: str = "es-DO-EmilioNeural",
            imagen: str = "", aviso: Callable[[str, float], None] = lambda t, f: None, guion: dict | None = None,
            animado: bool = False, estilo: str = "") -> dict:
    """Video completo desde un pedido. Con `imagen`, la primera escena es esa foto y las demás mantienen su sujeto.
    guion: el guion ya escrito (con la forma de ESQUEMA) por quien maneja el estudio; entonces no se usa la IA de texto.
    animado: cada escena es un video de IA con su propia voz (los personajes hablan con los labios sincronizados).
    Es de pago (ver costo_hablado): solo con True; las escenas que fallen se hacen con imagen y narración.
    estilo: un nombre de serie.ESTILOS (o un estilo en inglés); vacío = lo elige la IA."""
    from . import serie  # aquí: serie importa este módulo
    estilo = serie.ESTILOS.get(estilo, estilo)
    if imagen:
        imagen = str(seguro.archivo_medio(imagen, seguro.IMAGENES, t("imagen")))
    if formato not in video.FORMATOS:  # antes de gastar: un formato raro tumbaría el montaje ya pagado
        raise ValueError(t("Formato no válido: usa 9:16, 16:9, 1:1 o 4:5."))
    animado = animado is True  # «"false"» o «1» de una IA no son un sí: lo de pago, solo pedido de verdad
    if guion is not None:  # se comprueba antes de crear nada
        guion = ia.de_fuera(guion, ESQUEMA, t("El guion"))
    de_la_ia = guion is None
    # La narración que trae el pedido manda (pasó: un «Guion / Voz en Off» de 82 palabras salió resumido en 62)
    lineas, ritmo = narracion_del_usuario(prompt) if de_la_ia else [], palabras_por_segundo(voz)
    # Lo que el usuario escribió manda (pasó: pidió 6 escenas sin voz y salieron 4 narradas): sus escenas numeradas
    # y, si lo pidió sin narración, sin voz. Sin nada que decir, ni escenas que hablan (se pagarían por nada)
    pedidas, mudo = escenas_pedidas(prompt) if de_la_ia else 0, de_la_ia and sin_voz(prompt)
    callado, animado, notas = animado and mudo, animado and not mudo, []
    if callado:  # al empezar, antes de gastar nada: costo_hablado no las contó, ni se preguntaron
        notas.append(t("Pediste el video sin narración: las escenas no hablan y no se paga por ellas."))
        aviso(notas[-1], 0.02)
    # Lo de pago se fija al empezar (es lo que se preguntó): elegir otro en Claves de IA a mitad del trabajo no paga
    # nada que no se haya preguntado; vale para el trabajo siguiente
    pago, quien = ia.video_de_pago(), proveedor_voz()
    if animado and not quien:  # se avisa antes de gastar nada
        raise ia.SinClave(t("Para videos animados con voz conecta Gemini, Kling o Seedance en «Claves de IA» (Kling y "
                            "Seedance, elígelos en «Escenas que hablan»), o desmarca «Video animado con IA»."))
    base = max(1, round(segundos / SEGUNDOS_HABLADO)) if animado else max(3, round(segundos / 6))
    # Las que numeró, todas, animadas o no (hasta el tope de gasto): las que cuenta escenas_maximas, lo que se preguntó
    escenas_aprox = min(pedidas, MAX_HABLADAS) if pedidas else base
    # El estilo del menú manda, salvo que el pedido nombre otro (ese lo elige la IA, como dicen las INSTRUCCIONES)
    estilo_propio = de_la_ia and bool(_ESTILO.search(prompt))
    if guion is None:
        aviso(t("La IA está escribiendo el guion…"), 0.03)
        con_foto = ("\nEl usuario dio una foto de partida (va con el pedido): la primera escena ES esa foto. En las "
                    "demás, cuando aparezca su protagonista (persona, producto, lugar o personaje), descríbelo como "
                    "en la foto y escribe «the subject from the reference image».") if imagen else ""
        hablado = (f"\nCada escena será un video de IA de {SEGUNDOS_HABLADO} segundos con su propio sonido: como "
                   f"mucho 18 palabras de narración por escena.") if animado and not lineas else ""
        palabras = "" if mudo else f" (~{int(segundos * ritmo)} palabras de narración)"
        cuanto = (f", {len(lineas)} escenas (una por cada línea de narración del usuario)" if lineas else
                  f"{palabras}, {escenas_aprox} escenas: las que numeró el usuario, en su orden" if pedidas else
                  f"{palabras}, unas {escenas_aprox} escenas")
        propia = ("\nLa narración ya la escribió el usuario: copia cada línea en «narracion» tal cual, palabra por "
                  "palabra (sin acortarla, resumirla ni cambiarla), una escena por línea y en este orden:\n"
                  + "\n".join(f"{i}. {x}" for i, x in enumerate(lineas, 1))) if lineas else ""
        sin_narrar = ("\nSin narración: «narracion» vacía en todas las escenas; lo que se lee va en «texto_pantalla»."
                      if mudo else "")
        guion = ia.texto_json(INSTRUCCIONES, ia.con_fotos(
            f"Pedido: {prompt}\nDuración: unos {segundos} segundos{cuanto}. Formato {formato}."
            f"{propia}{sin_narrar}{con_foto}{hablado}{idioma_de(voz)}"
            + (f"\nEstilo elegido en el menú (úsalo salvo que el pedido nombre otro estilo): {estilo}" if estilo
               else "") + memoria.para("video")
            + memoria.recientes(), [imagen] if imagen else []), ESQUEMA)
    # La IA decide cuántas escenas devuelve: se recorta a lo pedido, para que nadie pueda disparar el gasto en
    # imágenes y voces (p. ej. con un pedido que diga «haz 300 escenas»). Animadas, cada una se paga: ni una de más.
    # Se quitan las del medio: la última es el cierre o la llamada a la acción. Las que numeró el usuario, justas.
    escenas, tope = guion["escenas"], escenas_aprox + (0 if animado or pedidas else 2)
    if not escenas:
        raise ValueError(t("El guion no tiene ninguna escena."))
    if lineas:  # cada línea en su escena y tal cual, aunque la IA devuelva otro número de escenas o la reescriba
        guion["escenas"] = escenas = [{**escenas[i * len(escenas) // len(lineas)], "narracion": x}
                                      for i, x in enumerate(lineas)]
    if mudo:  # sin voz aunque la IA escriba alguna frase
        for e in escenas:
            e["narracion"] = ""
    if estilo and not estilo_propio:  # lo impone el código: la IA a veces lo mezcla con otro
        guion["estilo_visual"] = estilo
    if guion.get("entendido"):  # se ve mientras trabaja, antes de gastar imágenes y voz
        # sin un «Entendí:» de la IA delante: salía «La IA entendió: Entendí: un gato que habla»
        entendido = re.sub(r"^\s*entend[ií]\w*\s*(que\s+)?[:,.]?\s*", "", guion["entendido"], flags=re.I)
        notas.append(t("La IA entendió: {x}", x=entendido or guion["entendido"]))
        aviso(notas[-1], 0.05)
    if len(escenas) > tope:
        guion["escenas"] = escenas[:tope - 1] + escenas[-1:]
        notas.append(t("Tu narración tiene {n} líneas y en este video caben {tope} escenas: se quitaron las líneas del "
                       "medio que sobraban.", n=len(escenas), tope=tope) if lineas else
                     # las suyas pasan del tope de gasto: cuáles se quitaron (las del medio; la última es el cierre)
                     t("Numeraste {n} escenas y en un video caben {tope} como mucho: se quitaron las escenas {lista}.",
                       n=pedidas, tope=tope, lista=", ".join(str(k) for k in range(tope, len(escenas))))
                     if pedidas > tope else
                     t("El guion traía {n} escenas y se usaron {tope} (las del medio que sobraban se quitaron).",
                       n=len(escenas), tope=tope))
    tiempos = list(_numeradas(prompt).values()) if de_la_ia else []
    if len(tiempos) == len(guion["escenas"]):  # una por cada escena suya: la que va sin voz dura lo que le dio
        for e, s in zip(guion["escenas"], tiempos):
            if s:
                e["segundos"] = s
    elif mudo:  # sin voz y sin sus tiempos: los segundos pedidos, repartidos (si no, 6 escenas mudas eran 18 s)
        for e in guion["escenas"]:
            e["segundos"] = round(segundos / len(guion["escenas"]), 1)
    if de_la_ia and _MUSICA.search(prompt):
        notas.append(t("Pediste música y este video no la lleva: ponla en el Editor de video con «Importar música o "
                       "sonido»."))
    if animado and lineas:  # sin el tope de 18 palabras: cada escena sigue siendo un clip de pago de SEGUNDOS_HABLADO s
        dichas = {e["narracion"] for e in guion["escenas"]}
        notas += [t("La línea {n} de tu narración tiene {palabras} palabras: en una escena animada de {s} s puede no "
                    "caber entera.", n=n, palabras=len(x.split()), s=SEGUNDOS_HABLADO)
                  for n, x in enumerate(lineas, 1) if x in dichas and len(x.split()) > 18]
    # La narración del usuario no se acorta: si no cabe en lo pedido, la voz va un poco más rápida (un 20 % como mucho)
    velocidad, pausas = 1.0, 0.25 * len(guion["escenas"])  # los 0,25 s de cada escena, como en al_tiempo
    if lineas and not animado:
        habla = sum(len(e["narracion"].split()) for e in guion["escenas"]) / ritmo
        if habla + pausas > segundos * 1.15:  # el margen del aviso «tal cual» de abajo: el ritmo es aproximado
            velocidad = round(min(1.2, habla / max(segundos - pausas, 1)), 2)
            notas.append(t("Tu narración no cabía en los {segundos} s pedidos: la voz va un {p} más rápida.",
                           segundos=segundos, p=porcentaje(velocidad - 1)))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-video")
    carpeta.mkdir(parents=True)
    for e in guion["escenas"]:  # y cada narración a 1-2 frases: la voz de pago se cobra por carácter
        # Solo palabras, una sola vez: guion.json, el clip de pago que habla y la pista de Whisper llevan el mismo texto
        e["narracion"] = ia.recortar(ia.sin_markdown(e["narracion"], "voz"), 400)
    # La IA escribe más de lo pedido (30 s salían 38,6 s): se acorta antes de narrar. Un guion de fuera o la
    # narración que escribió el usuario, tal cual.
    if de_la_ia and not lineas and not animado and not pedidas and al_tiempo(guion["escenas"], segundos, ritmo):
        notas.append(t("La narración pasaba de los {segundos} s pedidos: se acortó el guion para que quepa.",
                       segundos=segundos))
    # La ortografía, antes de narrar: lo que se dice es lo que sale en los subtítulos y lo que se publica. Un guion
    # de fuera, tal cual: al agente se le prometió que con su guion no se usa la IA de texto de la app. La narración
    # del usuario tampoco se toca: es suya
    if de_la_ia:
        ia.repasar([guion, *guion["escenas"]],
                   ("titulo", "descripcion", "hashtags", "texto_pantalla") + (() if lineas else ("narracion",)),
                   idioma_codigo(voz), notas)
    (carpeta / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    crear_imagen = foto = None
    if imagen:
        foto = Path(shutil.copy(imagen, carpeta / f"referencia{Path(imagen).suffix.lower()}"))

        def crear_imagen(p, w, h, destino):  # 1ª escena: la foto tal cual; las demás, con el mismo sujeto
            if destino.name == "video_final_imagen_00.png":  # por su número (con animado, la 1ª puede no pasar aquí)
                return ia.guardar_imagen(foto.read_bytes(), destino)  # un PNG de verdad, aunque la foto sea JPG
            # el estilo ya va dentro de p; si la edición con la foto falla, la escena sale igual y se dice
            return ia.imagen_con_producto(p, foto, w, h, destino, realista=False, avisos=notas)
    cobrados = set()  # escenas que hablan cobradas sin llegar: montar no las paga otra vez con un clip mudo
    hablados = clips_hablados(guion, carpeta, formato, aviso, foto, notas, crear_imagen, quien, cobrados) \
        if animado else {}
    dibujar = crear_imagen or ia.imagen
    try:  # la imagen que ya hizo clips_hablados (el primer fotograma de Kling) no se pide otra vez
        final = montar(guion, carpeta, formato, voz, aviso, respaldo=foto, notas=notas, hablados=hablados,
                       crear_imagen=lambda p, w, h, d: d if d.is_file() else dibujar(p, w, h, d),
                       desde=0.7 if animado else 0.1, pago=pago, sin_pago=cobrados, velocidad=velocidad)
    except Exception as error:
        relanzar_con_gasto(error, notas, carpeta)
    # su texto no se acortó (si el tope quitó alguna línea, ya se dijo: no se usó «tal cual»)
    if lineas and len(guion["escenas"]) == len(lineas) and abs((dura := video.duracion(final)) - segundos) > \
            0.15 * segundos:
        notas.append(t("Tu narración se usó tal cual la escribiste: el video dura {real} s y pediste {segundos} s.",
                       real=round(dura), segundos=segundos))
    proyecto = {"tipo": "video", "prompt": prompt, "formato": formato, "carpeta": str(carpeta),
                "titulo": guion["titulo"], "avisos": notas,
                "resultados": [{"archivo": str(final), "titulo": guion["titulo"],
                                "descripcion": guion["descripcion"], "hashtags": guion["hashtags"]}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo! Hay avisos ({n}): los ves debajo del video.", n=len(notas)) if notas else t("¡Listo!"), 1.0)
    return proyecto


def animar_imagen(imagen: str, prompt: str, formato: str = "9:16", segundos: float = 5,
                  aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """Solo anima una imagen siguiendo el pedido (clip corto, sin voz). Prueba primero la cuota gratis de video."""
    imagen = str(seguro.archivo_medio(imagen, seguro.IMAGENES, t("imagen")))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-animacion")
    carpeta.mkdir(parents=True)
    foto = Path(shutil.copy(imagen, carpeta / f"imagen{Path(imagen).suffix.lower()}"))
    from . import nubes
    pago, clip = ia.video_de_pago(), None
    # Quién lo hace de verdad: con Modal (crédito) elegido decía «gratis primero»; lo gratis va primero solo si es
    # Hugging Face el primero que se prueba
    primero = next(iter(nubes.orden("video")), "huggingface")
    quien = ia.nombre_video(pago) if pago else None if primero == "huggingface" else nubes.NOMBRES.get(primero, primero)
    aviso(t("Animando la imagen con {proveedor}…", proveedor=quien) if quien
          else t("Animando la imagen con IA de video (gratis primero)…"), 0.1)
    try:
        clip = ia.video_desde_imagen(foto, prompt, formato, segundos, carpeta / "clip_ia.mp4", pago)
        if not clip:  # solo pasa si el usuario puso la IA de video en «No usar» (Hugging Face va sin clave)
            raise ia.SinClave(t("En «Claves de IA», «Animar escenas con IA de video» está en «No usar». Ponlo en "
                                "«Automático» para animar: Hugging Face funciona gratis, incluso sin clave."))
        aviso(t("Ajustando al formato…"), 0.9)
        final = video.segmento_mudo(foto, video.duracion(clip), formato, carpeta / "animacion.mp4", 0, clip)
    except Exception as error:  # el clip de pago que se cobró (llegara o no) se dice antes de reintentar
        relanzar_con_gasto(error, [ia.nota_pago(pago, 1)] if pago and (clip or isinstance(error, ia.Cobrado))
                           else [], carpeta)
    titulo = titulo_corto(prompt) or t("Animación")
    proyecto = {"tipo": "animacion", "prompt": prompt, "formato": formato, "carpeta": str(carpeta),
                "titulo": titulo, "resultados": [{"archivo": str(final), "titulo": titulo, "descripcion": prompt,
                                                  "hashtags": []}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto


def titulo_corto(texto: str, largo: int = 50) -> str:
    """Un título corto y limpio sacado de un pedido: su primera frase u oración, sin cortar una palabra a medias
    (con prompt[:60] salía «…bajo el brazo de él con »)."""
    primera = re.split(r"[.,;:\n]|(?<=[!?])", ia.sin_markdown(texto, "linea"), maxsplit=1)[0].strip()
    # el «¿» nunca se queda sin su «?» (salía «¿Qué pasa en el malecón»), tampoco cortado en una coma
    primera += "".join(cierra for abre, cierra in ("¿?", "¡!") if abre in primera and cierra not in primera)
    return ia.recortar(primera[:1].upper() + primera[1:], largo)


def clips_hablados(guion: dict, carpeta: Path, formato: str, aviso: Callable[[str, float], None],
                   referencia: Path | None, notas: list, crear_imagen: Callable | None = None,
                   quien: str | None = None, cobrados: set | None = None) -> dict[int, Path]:
    """Cada escena como video de IA con su propia voz, 3 a la vez (cada uno tarda ~30 s). Devuelve {escena: video de
    la escena ya terminado}; las que fallan no están y montar() las hace con imagen y narración.
    crear_imagen: como en montar. Kling arranca en la imagen de su escena (Seedance también si hay foto; sin ella, sale
    solo del texto): se hace aquí, con el nombre que montar ya busca. quien: quien las hace, fijado al empezar el
    trabajo (lo que se preguntó). cobrados: se le añaden las escenas cobradas sin llegar (montar no las paga otra vez)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    n, fallos, pagados, segundos = min(len(guion["escenas"]), MAX_HABLADAS), {}, 0, 0.0
    quien = quien or proveedor_voz() or "gemini"
    sin_saldo = []  # el servicio dijo que no tiene saldo: las escenas que faltan ni se piden (fallarían igual)

    def uno(i: int, e: dict) -> Path:
        if sin_saldo:
            raise sin_saldo[0]
        ref = referencia  # Gemini: la foto es solo el sujeto que debe mantener; Kling y Seedance: la 1ª escena
        if (quien == "kling" or (quien == "seedance" and referencia)) and not (referencia and i == 0):
            ref = carpeta / f"video_final_imagen_{i:02d}.png"  # arrancan en la imagen de SU escena
            if not ref.is_file():  # un reintento la reutiliza
                try:
                    ref = (crear_imagen or ia.imagen)(f"{con_glosario(e['imagen'], e['narracion'])}, "
                                                      f"{guion['estilo_visual']}", *video.FORMATOS[formato], ref)
                except ia.Cobrado as error:  # se cobró la imagen, no el video (ni se pidió): no cuenta como clip
                    raise RuntimeError(str(error)) from error
        try:
            return ia.video_hablado(prompt_hablado(e, guion), formato, carpeta / f"video_final_hablado_{i:02d}.mp4",
                                    ref, quien)
        except ia.SinSaldo as error:  # aquí, en el hilo: la escena que va detrás en este hilo ya no lo pide
            sin_saldo.append(error)
            raise
    if len(guion["escenas"]) > n:
        notas.append(t("Solo las primeras {n} escenas van animadas con voz (tope de gasto por video); las demás van "
                       "con imagen y narración.", n=n))
    # Las escenas que ya están hechas en la carpeta (un reintento de ejemplos/crear.py) no se vuelven a pagar
    # (nombre propio: «video_final_escena_XX» también lo usa la escena de respaldo con imagen y narración)
    hechos = {i: p for i in range(n) if (p := carpeta / f"video_final_hablada_{i:02d}.mp4").is_file()}
    # Una escena sin nada que decir no se paga como escena que habla (y Omni le inventaría una voz): la hace montar,
    # por su camino sin voz
    pedir = [i for i, e in enumerate(guion["escenas"][:n]) if i not in hechos and e["narracion"].strip()]
    aviso(t("Creando las escenas animadas con voz ({n})…", n=len(pedir)), 0.08)
    with ThreadPoolExecutor(3) as grupo:
        trabajos = {grupo.submit(uno, i, guion["escenas"][i]): i for i in pedir}
        for listo in as_completed(trabajos):  # los avisos, desde este hilo
            i = trabajos[listo]
            try:
                clip = listo.result()
                pagados, segundos = pagados + 1, segundos + video.duracion(clip)
                aviso(t("Escena {n} de {total}: subtítulos…", n=i + 1, total=n), 0.08 + 0.6 * len(hechos) / n)
                # Mientras el servicio hace las demás, aquí se ponen los subtítulos de esta.
                hechos[i] = escena_hablada(clip, guion["escenas"][i]["narracion"], formato,
                                           carpeta / f"video_final_hablada_{i:02d}.mp4")
            except Exception as error:  # sin saldo, filtro de seguridad, servicio caído…
                if isinstance(error, ia.Cobrado):  # lo hizo pero no se pudo bajar: se cobra igual
                    pagados, segundos = pagados + 1, segundos + SEGUNDOS_HABLADO
                    if cobrados is not None:
                        cobrados.add(i)
                fallos[i] = texto_de_error(error)  # el de httpx, en claro (venía en inglés con un enlace)
            aviso(t("Escenas animadas con voz: {hechas} de {total}", hechas=len(hechos) + len(fallos), total=n),
                  0.08 + 0.6 * (len(hechos) + len(fallos)) / n)
    if fallos:  # una sola nota: si falla la clave, fallan todas por lo mismo
        notas.append(t("Las escenas {lista} no salieron animadas con voz ({causa}). Se hicieron con imagen y "
                       "narración.", lista=", ".join(str(i + 1) for i in sorted(fallos)),
                       causa=" ".join(fallos[min(fallos)].split())[:300]))
    if pagados:  # Gemini cobra los segundos que salen; Kling y Seedance, los que se piden (por lo alto)
        costo = ia.precio_video(quien, segundos, voz=True) if quien == "gemini" else \
            pagados * ia.precio_video(quien, voz=True)
        notas.append(t("{proveedor} hizo escenas animadas con voz ({n}): {segundos} s de video, unos {costo} según "
                       "su precio.", proveedor=ia.nombre_video(quien), n=pagados, segundos=round(segundos),
                       costo=dinero(costo)))
    return hechos


def escena_hablada(clip: Path, texto: str, formato: str, destino: Path) -> Path:
    """Escena desde un video de IA que ya trae su voz: subtítulos con los tiempos reales y se corta cuando acaba de
    hablar (Omni hace clips de hasta 10 s aunque la frase dure menos)."""
    voz = destino.with_name(destino.stem + "_voz.wav")
    video.ffmpeg("-i", clip.resolve(), "-vn", "-ac", "1", "-ar", "16000", voz.name, cwd=destino.parent)
    try:
        palabras = ia.transcribir(voz, pista=texto)
    except Exception:  # sin subtítulos antes que sin escena
        palabras = []
    # escena_de_clip alarga 0,25 s repitiendo el clip desde el principio: se corta antes, sin comerse la voz
    largo = video.duracion(clip)
    if palabras:
        ultima = min(palabras[-1]["fin"], largo)
        fin = max(ultima, min(largo - 0.25, ultima + 0.6))
    else:
        fin = largo - 0.25
    audio = destino.with_name(destino.stem + "_audio.m4a")
    video.ffmpeg("-i", clip.resolve(), "-vn", "-t", fin, "-c:a", "aac", audio.name, cwd=destino.parent)
    return video.escena_de_clip(clip, audio, formato, palabras, destino)


def relanzar_con_gasto(error: Exception, notas: list, carpeta: Path):
    """Relanza el error de un trabajo con lo ya pagado (sus notas de gasto) y su carpeta: reintentar lo pagaría otra
    vez. Si no se pagó nada, el error tal cual."""
    gasto = " ".join(n for n in notas if "$" in n)  # «US$0.50», «US$ 0,50» o «0,50 $ US» (ver idioma.dinero)
    if not gasto:
        raise error
    raise RuntimeError(f"{error} · {gasto} · {carpeta}") from error


def _ya_animada(clip: Path, imagen) -> bool:
    """Si el clip ya se hizo desde esta misma imagen (un reintento, «Dibujar lo que falta»): no se paga otra vez. Una
    imagen redibujada después (rehacer un plano) es más nueva que su clip viejo y se anima de nuevo."""
    try:
        with open(clip, "rb") as f:
            return seguro.es_video(f.read(16)) and clip.stat().st_mtime >= Path(imagen).stat().st_mtime
    except OSError:
        return False


def montar(guion: dict, carpeta: Path, formato: str, voz: str, aviso: Callable[[str, float], None],
           nombre: str = "video_final", crear_imagen: Callable | None = None, desde: float = 0.1,
           hasta: float = 0.97, respaldo: Path | None = None, notas: list | None = None,
           hablados: dict[int, Path] | None = None, pagados: dict | None = None, pago: str | None = None,
           sin_pago=frozenset(), velocidad: float = 1.0) -> Path:
    """Convierte un guion (escenas con narración e imagen) en un video terminado.
    velocidad: la de la voz (1.2 = un 20 % más rápida), para que la narración del usuario quepa en lo pedido.
    crear_imagen(prompt, ancho, alto, destino) permite cambiar cómo se hacen las imágenes (p. ej. con el producto).
    respaldo: imagen que existe y se usa si falla una imagen y todavía no hay ninguna buena (p. ej. la foto).
    notas: si se pasa una lista, se le añade lo que salió distinto (imágenes que fallaron y por qué) y lo gastado.
    hablados: {escena: video} ya hechos con su propia voz y subtítulos (clips_hablados): se ponen tal cual.
    pagados: {"clips": n} compartido por los montajes de un mismo trabajo (anuncios: uno por variante), para que el
    tope de clips de pago (MAX_CLIPS_PAGO) sea del trabajo entero.
    pago: el video de pago (Kling o Seedance) fijado al empezar el trabajo, ia.video_de_pago(): lo que se preguntó.
    None = ninguno, aunque el usuario lo elija a mitad del trabajo. sin_pago: escenas ya cobradas (las que hablan y
    no llegaron): no se pagan otra vez con un clip mudo."""
    ancho, alto = video.FORMATOS[formato]
    crear_imagen = crear_imagen or ia.imagen
    partes, n = [], len(guion["escenas"])
    animar_ia = True  # se apaga solo si la IA de video falla una vez, para no esperar en cada escena
    pagados, mios, k_gasto = {"clips": 0} if pagados is None else pagados, 0, None
    ultima = respaldo  # la última imagen que sí existe: se repite cuando una falla
    de_donde = t("la foto de respaldo")  # qué es `ultima`, para que el aviso diga la verdad
    for i, e in enumerate(guion["escenas"]):
        paso = desde + (hasta - desde) * i / n
        if i in (hablados or {}):
            partes.append(hablados[i])
            if (hecha := carpeta / f"{nombre}_imagen_{i:02d}.png").is_file():  # si falla la siguiente, se repite esta
                ultima, de_donde = hecha, t("la imagen anterior")
            continue
        aviso(t("Escena {n} de {total}: voz…", n=i + 1, total=n), paso)
        audio = carpeta / f"{nombre}_voz_{i:02d}.mp3"
        if e["narracion"].strip():
            # una serie: cada personaje con su voz. La velocidad, solo si cambia: narrar se llama como siempre
            palabras = narrar(e["narracion"], e.get("voz") or voz, audio, *([velocidad] if velocidad != 1 else []))
        else:  # un plano sin voz (su texto en pantalla, o la música): silencio, y nadie narra un texto vacío. Dura
            # lo que le dio el usuario («ESCENA 2 (4-9 s)», ver generar), con tope: el guion puede venir de fuera
            dura = e.get("segundos")
            dura = min(dura, 30) if isinstance(dura, (int, float)) and dura >= 1 else SEGUNDOS_SIN_VOZ
            video.ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", dura, audio.name, cwd=carpeta)
            palabras = []
        paso_imagen = paso + 0.3 * (hasta - desde) / n
        aviso(t("Escena {n} de {total}: imagen…", n=i + 1, total=n), paso_imagen)
        # Solo se anima con IA una imagen recién creada: repetir la anterior, la foto o el fondo de color sería
        # gastar cuota o crédito en lo mismo otra vez.
        nueva = False
        try:
            img = ultima = crear_imagen(f"{con_glosario(e['imagen'], e['narracion'])}, {guion['estilo_visual']}",
                                        ancho, alto, carpeta / f"{nombre}_imagen_{i:02d}.png")
            # La foto de respaldo devuelta (anuncios: la del producto sola, si no salió la escena) no es nueva: con
            # video de pago se cobraba un clip por cada escena que la repetía
            nueva = img != respaldo
            de_donde = t("la imagen anterior") if nueva else t("la foto de respaldo")
        except Exception as error:
            if ultima is None:  # ni una imagen todavía: fondo de color para que el video salga igual
                ultima, de_donde = video.fondo(formato, carpeta / f"{nombre}_fondo.png", i), t("un fondo de color")
            causa = texto_de_error(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
            nota = t("La imagen de la escena {n} no salió ({causa}). Se usó {origen}.", n=i + 1, causa=causa,
                     origen=de_donde)
            aviso(nota, paso_imagen)
            if notas is not None:
                notas.append(nota)
            img = ultima
        aviso(t("Escena {n} de {total}: animando…", n=i + 1, total=n), paso + 0.6 * (hasta - desde) / n)
        escena, clip_ia = carpeta / f"{nombre}_escena_{i:02d}.mp4", carpeta / f"{nombre}_clip_ia_{i:02d}.mp4"
        clip, cobrado = None, False
        if nueva and _ya_animada(clip_ia, img):
            clip = clip_ia
        elif animar_ia and nueva and pago and pagados["clips"] >= MAX_CLIPS_PAGO:
            animar_ia = False
            nota = t("Ya van {n} escenas animadas con {proveedor} en este trabajo (el tope de gasto): las demás van con "
                     "zoom suave.", n=MAX_CLIPS_PAGO, proveedor=ia.nombre_video(pago))
            aviso(nota, paso + 0.6 * (hasta - desde) / n)
            if notas is not None:
                notas.append(nota)
        elif animar_ia and nueva and not (pago and i in sin_pago):
            try:
                clip = ia.video_desde_imagen(img, e["imagen"], formato, video.duracion(audio), clip_ia, pago)
            except Exception as error:  # cuota gratis agotada o servicio caído: se sigue con zoom suave
                cobrado = isinstance(error, ia.Cobrado)  # lo hizo pero no llegó: se paga igual
                causa = texto_de_error(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
                nota = t("La IA de video no respondió en la escena {n} ({causa}). El resto va con zoom suave.",
                         n=i + 1, causa=causa)
                aviso(nota, paso + 0.6 * (hasta - desde) / n)
                if notas is not None:
                    notas.append(nota)
                animar_ia = False
            if pago and (clip or cobrado):  # la nota de gasto, al día: si el trabajo falla luego, no se pierde
                pagados["clips"], mios = pagados["clips"] + 1, mios + 1
                if notas is not None:
                    if k_gasto is None:
                        k_gasto = len(notas)
                        notas.append("")
                    notas[k_gasto] = ia.nota_pago(pago, mios)
        partes.append(video.escena_de_clip(clip, audio, formato, palabras, escena) if clip
                      else video.escena_de_imagen(img, audio, formato, palabras, escena, i))
    aviso(t("Uniendo escenas…"), hasta)
    return video.unir(partes, carpeta / f"{nombre}.mp4")
