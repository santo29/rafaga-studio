"""Crea un video completo a partir de un prompt: guion con IA, imágenes, voz, subtítulos y montaje."""
import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Callable

import edge_tts

from . import claves, ia, seguro, video
from .idioma import actual, IDIOMAS, t
from .shorts import PROYECTOS

# Voces gratuitas de Microsoft Edge. ponytail: no es un modelo abierto; cambiar por Kokoro/Piper si se quiere 100% local.
# El nombre es lo que se ve (traducido); el id de Edge es lo que se usa.
VOCES = {
    t("Emilio (Rep. Dominicana)"): "es-DO-EmilioNeural",
    t("Ramona (Rep. Dominicana)"): "es-DO-RamonaNeural",
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

ESQUEMA = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"}, "descripcion": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "estilo_visual": {"type": "string"},
        "escenas": {"type": "array", "items": {
            "type": "object",
            "properties": {"narracion": {"type": "string"}, "imagen": {"type": "string"}},
            "required": ["narracion", "imagen"], "additionalProperties": False,
        }},
    },
    "required": ["titulo", "descripcion", "hashtags", "estilo_visual", "escenas"],
    "additionalProperties": False,
}

INSTRUCCIONES = """Eres guionista de videos virales para YouTube, TikTok, Instagram y Facebook.
Con el pedido del usuario escribe un guion narrado dividido en escenas.
- La primera escena es un gancho que atrapa en 3 segundos. La última cierra con fuerza o invita a seguir.
- Cada escena: 1 o 2 frases de narración (lo que dice la voz) y una descripción de la imagen.
- La descripción de imagen va en inglés, muy visual y concreta, sin texto escrito dentro de la imagen.
- estilo_visual: un estilo común para todas las imágenes (ej. "cinematic photo, dramatic lighting"), en inglés.
- Narración, título, descripción y hashtags en el idioma que pida el usuario (por defecto: """ + IDIOMAS[actual()] + ")."


def voces() -> dict[str, str]:
    """Todas las voces disponibles: las gratis de Edge y las de la cuenta de ElevenLabs si está conectada."""
    eleven = (claves.cargar().get("elevenlabs") or {}).get("voces", [])
    return {**VOCES, **{f"ElevenLabs · {v['nombre']}" + (f" ({v['acento']})" if v["acento"] else ""):
                        f"eleven:{v['id']}" for v in eleven}}


def narrar(texto: str, voz: str, destino: Path) -> list[dict]:
    """Genera la voz y devuelve los tiempos por palabra. voz = id de Edge o 'eleven:<voice_id>'."""
    if voz.startswith("eleven:"):
        return ia.voz_elevenlabs(texto, voz.removeprefix("eleven:"), destino)
    return asyncio.run(_voz(texto, voz, destino))


async def _voz(texto: str, voz: str, destino: Path) -> list[dict]:
    palabras = []
    with open(destino, "wb") as f:
        async for trozo in edge_tts.Communicate(texto, voz, boundary="WordBoundary").stream():
            if trozo["type"] == "audio":
                f.write(trozo["data"])
            elif trozo["type"] == "WordBoundary":
                ini = trozo["offset"] / 1e7  # viene en unidades de 100 ns
                palabras.append({"palabra": trozo["text"], "inicio": ini, "fin": ini + trozo["duration"] / 1e7})
    return palabras


def generar(prompt: str, formato: str = "9:16", segundos: int = 45, voz: str = "es-DO-EmilioNeural",
            imagen: str = "", aviso: Callable[[str, float], None] = lambda t, f: None, guion: dict | None = None) -> dict:
    """Video completo desde un pedido. Con `imagen`, la primera escena es esa foto y las demás mantienen su sujeto.
    guion: el guion ya escrito (con la forma de ESQUEMA) por quien maneja el estudio; entonces no se usa la IA de texto."""
    if imagen:
        imagen = str(seguro.archivo_medio(imagen, seguro.IMAGENES, t("imagen")))
    escenas_aprox = max(3, round(segundos / 6))
    if guion is not None:  # se comprueba antes de crear nada
        guion = ia.de_fuera(guion, ESQUEMA, t("El guion"))
    if guion is None:
        aviso(t("La IA está escribiendo el guion…"), 0.03)
        con_foto = ("\nEl usuario dio una imagen de referencia: la primera escena ES esa imagen. En las demás, cuando "
                    "aparezca su protagonista (persona, producto, lugar o personaje) escribe «the subject from the "
                    "reference image» en la descripción.") if imagen else ""
        guion = ia.texto_json(INSTRUCCIONES, (
            f"Pedido: {prompt}\nDuración: unos {segundos} segundos (~{int(segundos * 2.5)} palabras de narración), "
            f"unas {escenas_aprox} escenas. Formato {formato}.{con_foto}"), ESQUEMA)
    # La IA decide cuántas escenas devuelve: se recorta a lo pedido, para que nadie pueda disparar el gasto en
    # imágenes y voces (p. ej. con un pedido que diga «haz 300 escenas»).
    guion["escenas"] = guion["escenas"][:escenas_aprox + 2]
    if not guion["escenas"]:
        raise ValueError(t("El guion no tiene ninguna escena."))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-video")
    carpeta.mkdir(parents=True)
    for e in guion["escenas"]:  # y cada narración a 1-2 frases: la voz de pago se cobra por carácter
        e["narracion"] = e["narracion"][:400]
    (carpeta / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    crear_imagen = foto = None
    if imagen:
        foto = Path(shutil.copy(imagen, carpeta / f"referencia{Path(imagen).suffix.lower()}"))
        hechas = []

        def crear_imagen(p, w, h, destino):  # 1ª escena: la foto tal cual; las demás, con el mismo sujeto
            hechas.append(destino)
            if len(hechas) == 1:
                return Path(shutil.copy(foto, destino))
            return ia.imagen_con_producto(p, foto, w, h, destino)
    notas = []
    final = montar(guion, carpeta, formato, voz, aviso, crear_imagen=crear_imagen, respaldo=foto, notas=notas)
    proyecto = {"tipo": "video", "prompt": prompt, "formato": formato, "carpeta": str(carpeta),
                "titulo": guion["titulo"], "avisos": notas,
                "resultados": [{"archivo": str(final), "titulo": guion["titulo"],
                                "descripcion": guion["descripcion"], "hashtags": guion["hashtags"]}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo! Con {n} aviso(s): los ves debajo del video.", n=len(notas)) if notas else t("¡Listo!"), 1.0)
    return proyecto


def animar_imagen(imagen: str, prompt: str, formato: str = "9:16", segundos: float = 5,
                  aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """Solo anima una imagen siguiendo el pedido (clip corto, sin voz). Prueba primero la cuota gratis de video."""
    imagen = str(seguro.archivo_medio(imagen, seguro.IMAGENES, t("imagen")))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-animacion")
    carpeta.mkdir(parents=True)
    foto = Path(shutil.copy(imagen, carpeta / f"imagen{Path(imagen).suffix.lower()}"))
    aviso(t("Animando la imagen con IA de video (gratis primero)…"), 0.1)
    clip = ia.video_desde_imagen(foto, prompt, formato, segundos, carpeta / "clip_ia.mp4")
    if not clip:  # solo pasa si el usuario puso la IA de video en «No usar» (Hugging Face va sin clave)
        raise ia.SinClave(t("En «Claves de IA», «Animar escenas con IA de video» está en «No usar». Ponlo en "
                            "«Automático» para animar: Hugging Face funciona gratis, incluso sin clave."))
    aviso(t("Ajustando al formato…"), 0.9)
    final = video.segmento_mudo(foto, video.duracion(clip), formato, carpeta / "animacion.mp4", 0, clip)
    proyecto = {"tipo": "animacion", "prompt": prompt, "formato": formato, "carpeta": str(carpeta),
                "titulo": prompt[:60], "resultados": [{"archivo": str(final), "titulo": prompt[:60],
                                                         "descripcion": prompt, "hashtags": []}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto


def montar(guion: dict, carpeta: Path, formato: str, voz: str, aviso: Callable[[str, float], None],
           nombre: str = "video_final", crear_imagen: Callable | None = None, desde: float = 0.1,
           hasta: float = 0.97, respaldo: Path | None = None, notas: list | None = None) -> Path:
    """Convierte un guion (escenas con narración e imagen) en un video terminado.
    crear_imagen(prompt, ancho, alto, destino) permite cambiar cómo se hacen las imágenes (p. ej. con el producto).
    respaldo: imagen que existe y se usa si falla una imagen y todavía no hay ninguna buena (p. ej. la foto).
    notas: si se pasa una lista, se le añade lo que salió distinto (imágenes que fallaron y por qué)."""
    ancho, alto = video.FORMATOS[formato]
    crear_imagen = crear_imagen or ia.imagen
    partes, n = [], len(guion["escenas"])
    animar_ia = True  # se apaga solo si la IA de video falla una vez, para no esperar en cada escena
    ultima = respaldo  # la última imagen que sí existe: se repite cuando una falla
    de_donde = t("la foto de respaldo")  # qué es `ultima`, para que el aviso diga la verdad
    for i, e in enumerate(guion["escenas"]):
        paso = desde + (hasta - desde) * i / n
        aviso(t("Escena {n} de {total}: voz…", n=i + 1, total=n), paso)
        audio = carpeta / f"{nombre}_voz_{i:02d}.mp3"
        palabras = narrar(e["narracion"], e.get("voz") or voz, audio)  # una serie: cada personaje con su voz
        paso_imagen = paso + 0.3 * (hasta - desde) / n
        aviso(t("Escena {n} de {total}: imagen…", n=i + 1, total=n), paso_imagen)
        # Solo se anima con IA una imagen recién creada: repetir la anterior, la foto o el fondo de color sería
        # gastar cuota o crédito en lo mismo otra vez.
        nueva = False
        try:
            img = ultima = crear_imagen(f"{e['imagen']}, {guion['estilo_visual']}", ancho, alto,
                                        carpeta / f"{nombre}_imagen_{i:02d}.png")
            nueva, de_donde = True, t("la imagen anterior")
        except Exception as error:
            if ultima is None:  # ni una imagen todavía: fondo de color para que el video salga igual
                ultima, de_donde = video.fondo(formato, carpeta / f"{nombre}_fondo.png", i), t("un fondo de color")
            causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
            nota = t("La imagen de la escena {n} no salió ({causa}). Se usó {origen}.", n=i + 1, causa=causa,
                     origen=de_donde)
            aviso(nota, paso_imagen)
            if notas is not None:
                notas.append(nota)
            img = ultima
        aviso(t("Escena {n} de {total}: animando…", n=i + 1, total=n), paso + 0.6 * (hasta - desde) / n)
        escena = carpeta / f"{nombre}_escena_{i:02d}.mp4"
        clip = None
        if animar_ia and nueva:
            try:
                clip = ia.video_desde_imagen(img, e["imagen"], formato, video.duracion(audio),
                                             carpeta / f"{nombre}_clip_ia_{i:02d}.mp4")
            except Exception as error:  # cuota gratis agotada o servicio caído: se sigue con zoom suave
                causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
                nota = t("La IA de video no respondió en la escena {n} ({causa}). El resto va con zoom suave.",
                         n=i + 1, causa=causa)
                aviso(nota, paso + 0.6 * (hasta - desde) / n)
                if notas is not None:
                    notas.append(nota)
                animar_ia = False
        partes.append(video.escena_de_clip(clip, audio, formato, palabras, escena) if clip
                      else video.escena_de_imagen(img, audio, formato, palabras, escena, i))
    aviso(t("Uniendo escenas…"), hasta)
    return video.unir(partes, carpeta / f"{nombre}.mp4")
