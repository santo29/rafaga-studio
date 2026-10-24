"""Crea un video completo a partir de un prompt: guion con IA, imágenes, voz, subtítulos y montaje."""
import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Callable

import edge_tts

from . import claves, ia, memoria, seguro, video
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
        "entendido": {"type": "string"},  # opcional: los guiones de fuera (MCP) siguen valiendo sin él
        "escenas": {"type": "array", "items": {
            "type": "object",
            "properties": {"narracion": {"type": "string"}, "imagen": {"type": "string"}},
            "required": ["narracion", "imagen"], "additionalProperties": False,
        }},
    },
    "required": ["titulo", "descripcion", "hashtags", "estilo_visual", "escenas"],
    "additionalProperties": False,
}

# Regla común (la misma en Diseño, Director, Dibujos animados y aquí): el pedido puede traer faltas de ortografía.
FALTAS = ia.FALTAS  # la regla común de faltas de ortografía (una sola, en ia.py)

INSTRUCCIONES = """Eres guionista de videos virales para YouTube, TikTok, Instagram y Facebook.
Con el pedido del usuario escribe un guion narrado dividido en escenas.
- """ + FALTAS + """
- entendido: una frase corta, en el idioma del usuario, con lo que entendiste del pedido.
- La primera escena es un gancho que atrapa en 3 segundos. La última cierra con fuerza o invita a seguir.
- Cada escena: 1 o 2 frases de narración (lo que dice la voz) y una descripción de la imagen.
- La descripción de imagen va en inglés, muy visual y concreta, sin texto escrito dentro de la imagen.
- La IA de imágenes lee cada descripción SOLA, sin ver las demás: nunca escribas «the same…», «he», «she» ni «it»;
  nombra y describe siempre lo que sale.
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
MAX_CLIPS_PAGO = 15  # con Kling o Seedance para animar, clips de pago por trabajo como mucho: el resto, zoom suave


def proveedor_voz() -> str | None:
    """Quién hace las escenas que hablan («Escenas que hablan» en Claves de IA): Gemini en Automático; Kling o
    Seedance solo si el usuario los eligió. None si no hay ninguno conectado."""
    return (claves.para("video_voz") or {}).get("proveedor")


def costo_hablado(segundos: int) -> tuple[int, float]:
    """Cuántas escenas irán animadas con voz y lo más que costarán (US$) con quien las hace (ver ia.precio_video)."""
    escenas = min(MAX_HABLADAS, max(1, round(segundos / SEGUNDOS_HABLADO)))
    return escenas, escenas * ia.precio_video(proveedor_voz() or "gemini", voz=True)


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
    # Lo de pago se fija al empezar (es lo que se preguntó): elegir otro en Claves de IA a mitad del trabajo no paga
    # nada que no se haya preguntado; vale para el trabajo siguiente
    pago, quien = ia.video_de_pago(), proveedor_voz()
    if animado and not quien:  # se avisa antes de gastar nada
        raise ia.SinClave(t("Para videos animados con voz conecta Gemini, Kling o Seedance en «Claves de IA» (Kling y "
                            "Seedance, elígelos en «Escenas que hablan»), o desmarca «Video animado con IA»."))
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
            f"unas {escenas_aprox} escenas. Formato {formato}.{con_foto}{hablado}{idioma_de(voz)}"
            + (f"\nEstilo visual obligatorio: {estilo}" if estilo else "") + memoria.para("video")), ESQUEMA)
    # La IA decide cuántas escenas devuelve: se recorta a lo pedido, para que nadie pueda disparar el gasto en
    # imágenes y voces (p. ej. con un pedido que diga «haz 300 escenas»). Animadas, cada una se paga: ni una de más.
    # Se quitan las del medio: la última es el cierre o la llamada a la acción.
    escenas, tope, notas = guion["escenas"], escenas_aprox + (0 if animado else 2), []
    if not escenas:
        raise ValueError(t("El guion no tiene ninguna escena."))
    if estilo:  # lo impone el código: la IA a veces lo mezcla con otro
        guion["estilo_visual"] = estilo
    if guion.get("entendido"):  # se ve mientras trabaja, antes de gastar imágenes y voz
        notas.append(t("La IA entendió: {x}", x=guion["entendido"]))
        aviso(notas[-1], 0.05)
    if len(escenas) > tope:
        guion["escenas"] = escenas[:tope - 1] + escenas[-1:]
        notas.append(t("El guion traía {n} escenas y se usaron {tope} (las del medio que sobraban se quitaron).",
                       n=len(escenas), tope=tope))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-video")
    carpeta.mkdir(parents=True)
    for e in guion["escenas"]:  # y cada narración a 1-2 frases: la voz de pago se cobra por carácter
        e["narracion"] = e["narracion"][:400]
    (carpeta / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    crear_imagen = foto = None
    if imagen:
        foto = Path(shutil.copy(imagen, carpeta / f"referencia{Path(imagen).suffix.lower()}"))

        def crear_imagen(p, w, h, destino):  # 1ª escena: la foto tal cual; las demás, con el mismo sujeto
            if destino.name == "video_final_imagen_00.png":  # por su número (con animado, la 1ª puede no pasar aquí)
                return Path(shutil.copy(foto, destino))
            return ia.imagen_con_producto(p, foto, w, h, destino, realista=False)  # el estilo ya va dentro de p
    cobrados = set()  # escenas que hablan cobradas sin llegar: montar no las paga otra vez con un clip mudo
    hablados = clips_hablados(guion, carpeta, formato, aviso, foto, notas, crear_imagen, quien, cobrados) \
        if animado else {}
    dibujar = crear_imagen or ia.imagen
    try:  # la imagen que ya hizo clips_hablados (el primer fotograma de Kling) no se pide otra vez
        final = montar(guion, carpeta, formato, voz, aviso, respaldo=foto, notas=notas, hablados=hablados,
                       crear_imagen=lambda p, w, h, d: d if d.is_file() else dibujar(p, w, h, d),
                       desde=0.7 if animado else 0.1, pago=pago, sin_pago=cobrados)
    except Exception as error:
        relanzar_con_gasto(error, notas, carpeta)
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
    pago, clip = ia.video_de_pago(), None
    aviso(t("Animando la imagen con {proveedor}…", proveedor=ia.nombre_video(pago)) if pago
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
    proyecto = {"tipo": "animacion", "prompt": prompt, "formato": formato, "carpeta": str(carpeta),
                "titulo": prompt[:60], "resultados": [{"archivo": str(final), "titulo": prompt[:60],
                                                         "descripcion": prompt, "hashtags": []}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto


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

    def uno(i: int, e: dict) -> Path:
        ref = referencia  # Gemini: la foto es solo el sujeto que debe mantener; Kling y Seedance: la 1ª escena
        if (quien == "kling" or (quien == "seedance" and referencia)) and not (referencia and i == 0):
            ref = carpeta / f"video_final_imagen_{i:02d}.png"  # arrancan en la imagen de SU escena
            if not ref.is_file():  # un reintento la reutiliza
                ref = (crear_imagen or ia.imagen)(f"{e['imagen']}, {guion['estilo_visual']}", *video.FORMATOS[formato],
                                                  ref)
        return ia.video_hablado(prompt_hablado(e, guion), formato, carpeta / f"video_final_hablado_{i:02d}.mp4", ref,
                                quien)
    if len(guion["escenas"]) > n:
        notas.append(t("Solo las primeras {n} escenas van animadas con voz (tope de gasto por video); las demás van "
                       "con imagen y narración.", n=n))
    # Las escenas que ya están hechas en la carpeta (un reintento de ejemplos/crear.py) no se vuelven a pagar
    # (nombre propio: «video_final_escena_XX» también lo usa la escena de respaldo con imagen y narración)
    hechos = {i: p for i in range(n) if (p := carpeta / f"video_final_hablada_{i:02d}.mp4").is_file()}
    aviso(t("Creando {n} escena(s) animadas con voz…", n=n - len(hechos)), 0.08)
    with ThreadPoolExecutor(3) as grupo:
        trabajos = {grupo.submit(uno, i, e): i for i, e in enumerate(guion["escenas"][:n]) if i not in hechos}
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
                fallos[i] = str(error).strip() or type(error).__name__
            aviso(t("Escenas animadas con voz: {hechas} de {total}", hechas=len(hechos) + len(fallos), total=n),
                  0.08 + 0.6 * (len(hechos) + len(fallos)) / n)
    if fallos:  # una sola nota: si falla la clave, fallan todas por lo mismo
        notas.append(t("Las escenas {lista} no salieron animadas con voz ({causa}). Se hicieron con imagen y "
                       "narración.", lista=", ".join(str(i + 1) for i in sorted(fallos)),
                       causa=" ".join(fallos[min(fallos)].split())[:300]))
    if pagados:  # Gemini cobra los segundos que salen; Kling y Seedance, los que se piden (por lo alto)
        costo = ia.precio_video(quien, segundos, voz=True) if quien == "gemini" else \
            pagados * ia.precio_video(quien, voz=True)
        notas.append(t("{proveedor} hizo {n} escena(s) animadas con voz: {segundos} s de video, unos US${costo} según "
                       "su precio.", proveedor=ia.nombre_video(quien), n=pagados, segundos=round(segundos),
                       costo=f"{costo:.2f}"))
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
    gasto = " ".join(n for n in notas if "US$" in n or "$ US" in n)  # «$ US»: las notas en francés
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
           sin_pago=frozenset()) -> Path:
    """Convierte un guion (escenas con narración e imagen) en un video terminado.
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
                causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
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
