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
- Si el pedido es un personaje que habla (una fruta, un animal, un objeto, una mascota…), la narración la dice ESE
  personaje en primera persona, y la imagen lo muestra hablando a cámara. Nunca una persona que habla de él.
- Describe al protagonista con las mismas palabras en todas las escenas, para que se vea igual en todo el video.
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


SEGUNDOS_HABLADO = 8  # lo que dura cada escena animada con voz (Omni hace clips de 3 a 10 s)
MAX_HABLADAS = 15  # tope de gasto por video (~US$12): las escenas de más se hacen con imagen y narración


def costo_hablado(segundos: int) -> tuple[int, float]:
    """Cuántas escenas irán animadas con voz y cuánto costarán más o menos (US$; Omni cobra por segundo y sus clips
    pueden durar hasta 10 s)."""
    escenas = min(MAX_HABLADAS, max(1, round(segundos / SEGUNDOS_HABLADO)))
    return escenas, escenas * 10 * ia.PRECIO_OMNI


def con_voz_propia() -> bool:
    """Si «Crear video» hace por defecto escenas animadas con voz: hay clave de Gemini y la IA de video no está apagada."""
    return "gemini" in claves.cargar() and claves.ajustes().get("video") != "ninguno"


def prompt_hablado(escena: dict, guion: dict) -> str:
    """Lo que se pide a la IA de video con voz para una escena: la imagen, el estilo y la frase que se dice."""
    return (f"{escena['imagen']}. Visual style: {guion['estilo_visual']}. A short clip of about {SEGUNDOS_HABLADO} "
            f"seconds. This line is spoken clearly, word for word, in its own language: \"{escena['narracion']}\". "
            "If a character is on screen, that character says it to the camera with natural lip sync; otherwise a "
            "narrator says it as a voice-over. Soft ambient sound, no music over the voice. No on-screen text, no "
            "captions, no subtitles.")


def generar(prompt: str, formato: str = "9:16", segundos: int = 45, voz: str = "es-DO-EmilioNeural",
            imagen: str = "", aviso: Callable[[str, float], None] = lambda t, f: None, guion: dict | None = None,
            animado: bool | None = None) -> dict:
    """Video completo desde un pedido. Con `imagen`, la primera escena es esa foto y las demás mantienen su sujeto.
    guion: el guion ya escrito (con la forma de ESQUEMA) por quien maneja el estudio; entonces no se usa la IA de texto.
    animado: cada escena es un video de IA con su propia voz (los personajes hablan con los labios sincronizados).
    Es de pago (Gemini, ~US$0,10 por segundo). None = sí cuando con_voz_propia(); las escenas que fallen se hacen
    con imagen y narración."""
    if imagen:
        imagen = str(seguro.archivo_medio(imagen, seguro.IMAGENES, t("imagen")))
    if animado is None:
        animado = con_voz_propia()
    elif animado and "gemini" not in claves.cargar():  # se avisa antes de gastar nada
        raise ia.SinClave(t("Para videos animados con voz conecta tu clave de Gemini en «Claves de IA», o desmarca "
                            "«Video animado con IA»."))
    escenas_aprox = max(1, round(segundos / SEGUNDOS_HABLADO)) if animado else max(3, round(segundos / 6))
    if guion is not None:  # se comprueba antes de crear nada
        guion = ia.de_fuera(guion, ESQUEMA, t("El guion"))
    if guion is None:
        aviso(t("La IA está escribiendo el guion…"), 0.03)
        con_foto = ("\nEl usuario dio una imagen de referencia: la primera escena ES esa imagen. En las demás, cuando "
                    "aparezca su protagonista (persona, producto, lugar o personaje) escribe «the subject from the "
                    "reference image» en la descripción.") if imagen else ""
        hablado = (f"\nCada escena será un video de IA de {SEGUNDOS_HABLADO} segundos con su propio sonido: como "
                   f"mucho 18 palabras de narración por escena.") if animado else ""
        guion = ia.texto_json(INSTRUCCIONES, (
            f"Pedido: {prompt}\nDuración: unos {segundos} segundos (~{int(segundos * 2.5)} palabras de narración), "
            f"unas {escenas_aprox} escenas. Formato {formato}.{con_foto}{hablado}"), ESQUEMA)
    # La IA decide cuántas escenas devuelve: se recorta a lo pedido, para que nadie pueda disparar el gasto en
    # imágenes y voces (p. ej. con un pedido que diga «haz 300 escenas»). Animadas, cada una se paga: ni una de más.
    guion["escenas"] = guion["escenas"][:escenas_aprox + (0 if animado else 2)]
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
    hablados = clips_hablados(guion, carpeta, formato, aviso, foto, notas) if animado else {}
    final = montar(guion, carpeta, formato, voz, aviso, crear_imagen=crear_imagen, respaldo=foto, notas=notas,
                   hablados=hablados, desde=0.7 if hablados else 0.1)
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


def clips_hablados(guion: dict, carpeta: Path, formato: str, aviso: Callable[[str, float], None],
                   referencia: Path | None, notas: list) -> dict[int, Path]:
    """Cada escena como video de IA con su propia voz, 3 a la vez (cada uno tarda ~30 s). Devuelve {escena: video de
    la escena ya terminado}; las que fallan no están y montar() las hace con imagen y narración."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    n, hechos, fallos, pagados, segundos = min(len(guion["escenas"]), MAX_HABLADAS), {}, {}, 0, 0.0
    if len(guion["escenas"]) > n:
        notas.append(t("Solo las primeras {n} escenas van animadas con voz (tope de gasto por video); las demás van "
                       "con imagen y narración.", n=n))
    aviso(t("Creando {n} escena(s) animadas con voz…", n=n), 0.08)
    with ThreadPoolExecutor(3) as grupo:
        trabajos = {grupo.submit(ia.video_hablado, prompt_hablado(e, guion), formato,
                                 carpeta / f"video_final_hablado_{i:02d}.mp4", referencia): i
                    for i, e in enumerate(guion["escenas"][:n])}
        for listo in as_completed(trabajos):  # los avisos, desde este hilo
            i = trabajos[listo]
            try:
                clip = listo.result()
                pagados, segundos = pagados + 1, segundos + video.duracion(clip)
                aviso(t("Escena {n} de {total}: subtítulos…", n=i + 1, total=n), 0.08 + 0.6 * len(hechos) / n)
                # Mientras Google hace las demás, aquí se ponen los subtítulos de esta.
                hechos[i] = escena_hablada(clip, guion["escenas"][i]["narracion"], formato,
                                           carpeta / f"video_final_escena_{i:02d}.mp4")
            except Exception as error:  # sin saldo, filtro de seguridad, servicio caído…
                fallos[i] = str(error).strip() or type(error).__name__
            aviso(t("Escenas animadas con voz: {hechas} de {total}", hechas=len(hechos) + len(fallos), total=n),
                  0.08 + 0.6 * (len(hechos) + len(fallos)) / n)
    if fallos:  # una sola nota: si falla la clave, fallan todas por lo mismo
        notas.append(t("Las escenas {lista} no salieron animadas con voz ({causa}). Se hicieron con imagen y "
                       "narración.", lista=", ".join(str(i + 1) for i in sorted(fallos)),
                       causa=" ".join(fallos[min(fallos)].split())[:300]))
    if pagados:
        notas.append(t("Gemini hizo {n} escena(s) animadas con voz: {segundos} s de video, unos US${costo} según el "
                       "precio de Google.", n=pagados, segundos=round(segundos),
                       costo=f"{segundos * ia.PRECIO_OMNI:.2f}"))
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
    largo = video.duracion(clip)
    fin = min(largo, palabras[-1]["fin"] + 0.6) if palabras else largo
    audio = destino.with_name(destino.stem + "_audio.m4a")
    video.ffmpeg("-i", clip.resolve(), "-vn", "-t", fin, "-c:a", "aac", audio.name, cwd=destino.parent)
    return video.escena_de_clip(clip, audio, formato, palabras, destino)


def montar(guion: dict, carpeta: Path, formato: str, voz: str, aviso: Callable[[str, float], None],
           nombre: str = "video_final", crear_imagen: Callable | None = None, desde: float = 0.1,
           hasta: float = 0.97, respaldo: Path | None = None, notas: list | None = None,
           hablados: dict[int, Path] | None = None) -> Path:
    """Convierte un guion (escenas con narración e imagen) en un video terminado.
    crear_imagen(prompt, ancho, alto, destino) permite cambiar cómo se hacen las imágenes (p. ej. con el producto).
    respaldo: imagen que existe y se usa si falla una imagen y todavía no hay ninguna buena (p. ej. la foto).
    notas: si se pasa una lista, se le añade lo que salió distinto (imágenes que fallaron y por qué).
    hablados: {escena: video} ya hechos con su propia voz y subtítulos (clips_hablados): se ponen tal cual."""
    ancho, alto = video.FORMATOS[formato]
    crear_imagen = crear_imagen or ia.imagen
    partes, n = [], len(guion["escenas"])
    animar_ia = True  # se apaga solo si la IA de video falla una vez, para no esperar en cada escena
    ultima = respaldo  # la última imagen que sí existe: se repite cuando una falla
    de_donde = t("la foto de respaldo")  # qué es `ultima`, para que el aviso diga la verdad
    for i, e in enumerate(guion["escenas"]):
        paso = desde + (hasta - desde) * i / n
        if i in (hablados or {}):
            partes.append(hablados[i])
            continue
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
