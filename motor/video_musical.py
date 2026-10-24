"""Video musical: escenas que van con la canción, ondas que se mueven con el sonido y la letra estilo karaoke."""
import json
import math
import time
from pathlib import Path
from typing import Callable

from . import claves, ia, memoria, seguro, video
from .idioma import actual, IDIOMAS, t
from .shorts import PROYECTOS

MAX_ESCENAS = 14  # cada escena es una imagen de IA (de pago con Gemini): el gasto no lo decide la duración

ESQUEMA = {
    "type": "object",
    "properties": {
        "estilo_visual": {"type": "string"},
        "escenas": {"type": "array", "items": {"type": "string"}},
        "descripcion": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["estilo_visual", "escenas", "descripcion", "hashtags"],
    "additionalProperties": False,
}

INSTRUCCIONES = """Eres director de videoclips. Diseña las escenas visuales de un video musical que vaya con la canción.
- escenas: una descripción de imagen en inglés por escena, en orden, siguiendo la historia y la energía de la letra
  (intro más calmada, coro con más energía: luces, baile, multitud). Lugares y gente que encajen con el género
  (p. ej. dembow: discoteca con luces de neón, colmado de barrio de noche, calle con bocinas, gente bailando).
- Nada de texto escrito dentro de las imágenes. Sin caras de artistas reales.
- estilo_visual: un estilo común en inglés (ej. "neon-lit night club, cinematic, high contrast, film grain").
- descripcion y hashtags para publicar el video, en este idioma: """ + IDIOMAS[actual()] + "."


def crear(cancion: str, titulo: str = "", letra: str = "", genero: str = "", formato: str = "9:16",
          idea: str = "", aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    cancion = str(seguro.archivo_medio(cancion, seguro.AUDIOS, t("canción")))
    if video.duracion(Path(cancion)) > 900:  # como la Cabina: un audio de horas daría escenas de horas
        raise ValueError(t("Canción: dura más de 15 minutos; córtala antes de hacer el video musical."))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-videomusical")
    carpeta.mkdir(parents=True)
    # Se copia cortando a 15 min de verdad (la duración de la cabecera puede mentir: un WebM de horas que dice 10 s).
    # En WAV, que admite cualquier audio de entrada (también un WAV llamado .mp3).
    audio = carpeta / "cancion.wav"
    video.ffmpeg("-i", Path(cancion), "-t", 900, audio.name, cwd=carpeta)
    titulo = titulo or Path(cancion).stem
    total = video.duracion(audio)

    # Se dice dónde se escucha: con Groq/OpenAI conectados, la canción (y la letra) se sube a ese servicio.
    nube = claves.para("transcripcion") or {}
    servicio = ("OpenAI" if nube.get("proveedor") == "openai" else "Groq") if nube.get("clave") else ""
    aviso(t("Escuchando la canción en {servicio} para sincronizar la letra…", servicio=servicio) if servicio
          else t("Escuchando la canción en tu PC para sincronizar la letra…"), 0.03)
    palabras = ia.transcribir(audio, pista=letra or None, cancion=True, progreso=lambda f: aviso(
        t("Escuchando la canción en {servicio}… {p:.0%}", servicio=servicio, p=f) if servicio
        else t("Escuchando la canción en tu PC… {p:.0%}", p=f), 0.03 + 0.15 * f))

    # Una escena cada ~8 s, con tope para no gastar demasiadas imágenes.
    n = max(2, min(MAX_ESCENAS, math.ceil(total / 8)))
    aviso(t("La IA está dirigiendo el videoclip…"), 0.2)
    letra_oida = " ".join(p["palabra"] for p in palabras)
    plan = ia.texto_json(INSTRUCCIONES, (
        f"Canción: {titulo}\nGénero: {genero or 'no indicado'}\nDuración: {total:.0f} s\nIdea del usuario: {idea or '—'}\n"
        f"Letra:\n{letra or letra_oida or '(instrumental)'}\n\nDame exactamente {n} escenas." + memoria.para("musica_voz")),
        ESQUEMA)
    escenas = (plan["escenas"] or ["dancing crowd under club lights"])[:n]
    n = len(escenas)
    tramo = total / n
    ancho, alto = video.FORMATOS[formato]

    partes, animar_ia, ultima, notas, de_donde = [], True, None, [], ""
    for i, descripcion in enumerate(escenas):
        paso = 0.25 + 0.6 * i / n
        aviso(t("Escena {n} de {total}: imagen…", n=i + 1, total=n), paso)
        nueva = False  # solo se anima una imagen recién creada: repetir una sería gastar cuota en lo mismo
        try:
            img = ultima = ia.imagen(f"{descripcion}, {plan['estilo_visual']}", ancho, alto,
                                     carpeta / f"imagen_{i:02d}.png")
            nueva, de_donde = True, t("la imagen anterior")
        except Exception as error:
            if ultima is None:  # ni una imagen todavía: fondo de color para que el videoclip salga igual
                ultima, de_donde = video.fondo(formato, carpeta / "fondo.png", i), t("un fondo de color")
            causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
            notas.append(t("La imagen de la escena {n} no salió ({causa}). Se usó {origen}.", n=i + 1, causa=causa,
                           origen=de_donde))
            aviso(notas[-1], paso)
            img = ultima  # se repite la última imagen que sí existe para no parar el video
        clip = None
        if animar_ia and nueva:
            try:
                aviso(t("Escena {n} de {total}: animando…", n=i + 1, total=n), paso + 0.3 / n)
                clip = ia.video_desde_imagen(img, descripcion, formato, tramo, carpeta / f"clip_ia_{i:02d}.mp4")
            except Exception as error:  # cupo de la nube agotado o servicio caído: el resto con zoom suave
                causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
                notas.append(t("La IA de video no respondió en la escena {n} ({causa}). El resto va con zoom suave.",
                               n=i + 1, causa=causa))
                aviso(notas[-1], paso + 0.3 / n)
                animar_ia = False
        segundos = tramo + (1 if i == n - 1 else 0)  # el último sobra un poco: el video nunca acaba antes que la canción
        partes.append(video.segmento_mudo(img, segundos, formato, carpeta / f"tramo_{i:02d}.mp4", i, clip))

    aviso(t("Uniendo escenas…"), 0.88)
    visual = video.unir(partes, carpeta / "visual.mp4")
    aviso(t("Poniendo la canción, las ondas y la letra…"), 0.93)
    final = video.con_cancion(visual, audio, formato, palabras, carpeta / "video_musical.mp4")

    proyecto = {"tipo": "videomusical", "formato": formato, "carpeta": str(carpeta), "titulo": titulo,
                "avisos": notas, "resultados": [{"archivo": str(final), "titulo": titulo,
                                                 "descripcion": plan["descripcion"], "hashtags": plan["hashtags"]}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo! Con {n} aviso(s): los ves debajo del video.", n=len(notas)) if notas else t("¡Listo!"), 1.0)
    return proyecto
