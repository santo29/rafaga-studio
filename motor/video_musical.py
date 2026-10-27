"""Video musical: escenas que van con la canción, ondas que se mueven con el sonido y la letra estilo karaoke."""
import json
import math
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from . import claves, ia, memoria, seguro, video
from .desde_prompt import con_glosario, relanzar_con_gasto
from .idioma import actual, IDIOMAS, porcentaje, t
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


def _nucleo(palabra: str) -> str:
    """Una palabra para comparar lo escrito con lo oído: sin tildes, signos ni mayúsculas."""
    import unicodedata
    return re.sub(r"\W", "", unicodedata.normalize("NFKD", palabra).encode("ascii", "ignore").decode().lower())


def _repartir(escritas: list[str], ini: float, fin: float) -> list[dict]:
    """Palabras escritas repartidas en un tramo de tiempo, cada una según lo larga que es."""
    pesos = [max(len(p), 1) for p in escritas]
    paso, salida, t0 = (fin - ini) / sum(pesos), [], ini
    for p, peso in zip(escritas, pesos):
        salida.append({"palabra": p, "inicio": t0, "fin": t0 + paso * peso})
        t0 += paso * peso
    return salida


def alinear(escritas: list[str], oidas: list[dict]) -> list[dict]:
    """La letra ESCRITA con los tiempos de lo que oyó Whisper: se alinean las dos listas de palabras (como un diff);
    lo que coincide toma su tiempo, lo que Whisper oyó mal («SUVIMOS», «VAI LA») se cambia por lo escrito en ese mismo
    tramo, lo que no oyó se reparte en el hueco entre sus vecinas y lo que oyó sin estar escrito no sale. Un coro que
    se canta más veces de las que está escrito se vuelve a buscar en la letra."""
    if not escritas or not oidas:
        return []
    a, b = [_nucleo(p) for p in escritas], [_nucleo(p["palabra"]) for p in oidas]
    salida = []  # sin tiempo todavía (None): las que no se oyeron
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            salida += [{**oidas[j], "palabra": escritas[i]} for i, j in zip(range(i1, i2), range(j1, j2))]
        elif op == "replace" and i2 - i1 == j2 - j1:  # una por una
            salida += [{**oidas[j], "palabra": escritas[i]} for i, j in zip(range(i1, i2), range(j1, j2))]
        elif op == "replace":
            salida += _repartir(escritas[i1:i2], oidas[j1]["inicio"], oidas[j2 - 1]["fin"])
        elif op == "delete":
            salida += [{"palabra": p, "inicio": None, "fin": None} for p in escritas[i1:i2]]
        elif j2 - j1 >= 4:  # «insert»: un trozo oído que no está en su sitio de la letra (un coro repetido)
            trozo = SequenceMatcher(None, a, b[j1:j2], autojunk=False).get_matching_blocks()[:-1]
            if sum(m.size for m in trozo) >= (j2 - j1) / 2:
                desde, hasta = trozo[0].a, trozo[-1].a + trozo[-1].size
                salida += alinear(escritas[desde:hasta], oidas[j1:j2])
    # Las que no se oyeron, repartidas en el hueco entre la anterior y la siguiente que sí tienen tiempo
    i = 0
    while i < len(salida):
        if salida[i]["inicio"] is not None:
            i += 1
            continue
        k = i
        while k < len(salida) and salida[k]["inicio"] is None:
            k += 1
        n = k - i
        ini = salida[i - 1]["fin"] if i else None
        fin = salida[k]["inicio"] if k < len(salida) else None
        if ini is None and fin is None:  # nada de lo oído encajó en ninguna parte
            return []
        ini = ini if ini is not None else max(0.0, fin - 0.4 * n)
        fin = fin if fin is not None else ini + 0.4 * n
        salida[i:k] = _repartir([p["palabra"] for p in salida[i:k]], ini, max(fin, ini))
        i = k
    return salida


def crear(cancion: str, titulo: str = "", letra: str = "", genero: str = "", formato: str = "9:16",
          idea: str = "", aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    cancion = str(seguro.archivo_medio(cancion, seguro.AUDIOS, t("canción")))
    pago = ia.video_de_pago()  # fijado al empezar: lo que se preguntó (ver desde_prompt.montar)
    if video.duracion(Path(cancion)) > 900:  # como la Cabina: un audio de horas daría escenas de horas
        raise ValueError(t("Canción: dura más de 15 minutos; córtala antes de hacer el video musical."))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-videomusical")
    carpeta.mkdir(parents=True)
    # Se copia cortando a 15 min de verdad (la duración de la cabecera puede mentir: un WebM de horas que dice 10 s).
    # En WAV, que admite cualquier audio de entrada (también un WAV llamado .mp3).
    audio = carpeta / "cancion.wav"
    video.ffmpeg("-i", Path(cancion), "-t", 900, audio.name, cwd=carpeta)
    titulo = titulo or video.titulo_cancion(Path(cancion))  # el de verdad, no «cancion» (el nombre del archivo)
    total = video.duracion(audio)

    # Se dice dónde se escucha: con Groq/OpenAI conectados, la canción (y la letra) se sube a ese servicio.
    nube = claves.para("transcripcion") or {}
    servicio = ("OpenAI" if nube.get("proveedor") == "openai" else "Groq") if nube.get("clave") else ""
    aviso(t("Escuchando la canción en {servicio} para sincronizar la letra…", servicio=servicio) if servicio
          else t("Escuchando la canción en tu PC para sincronizar la letra…"), 0.03)
    palabras = ia.transcribir(audio, pista=letra or None, cancion=True, progreso=lambda f: aviso(
        t("Escuchando la canción en {servicio}… {p}", servicio=servicio, p=porcentaje(f)) if servicio
        else t("Escuchando la canción en tu PC… {p}", p=porcentaje(f)), 0.03 + 0.15 * f))

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
    # Con la letra, el karaoke enseña lo ESCRITO (con su ortografía repasada, línea a línea para no mover palabras)
    # en los tiempos de lo oído: Whisper oía «SUVIMOS AL MALECÓN» y «VAI LA» y eso salía en pantalla
    lineas, notas = [x for x in ia.sin_acotaciones(letra).splitlines() if x.strip()], []
    if lineas and _nucleo(lineas[0]) == _nucleo(titulo):  # la letra.txt del estudio empieza por el título
        lineas = lineas[1:]
    escritas = [p for x in ia.ortografia(lineas, notas=notas) for p in x.split()] if lineas else []
    # Solo si se parece a lo que suena: una ruta («letra.txt») o solo el coro sustituían toda la canción
    if escritas and SequenceMatcher(None, [_nucleo(p) for p in escritas], [_nucleo(p["palabra"]) for p in palabras],
                                    autojunk=False).ratio() >= 0.4:
        palabras = alinear(escritas, palabras)
    elif escritas and palabras:
        notas.append(t("La letra que diste no coincide con lo que se oye: el karaoke usa lo que se oye."))
    ia.repasar([plan], ("descripcion", "hashtags"), notas=notas)

    partes, animar_ia, ultima, de_donde = [], True, None, ""
    pagados = 0  # con Kling o Seedance, cada escena animada se paga (hasta MAX_ESCENAS)
    try:
        for i, descripcion in enumerate(escenas):
            paso = 0.25 + 0.6 * i / n
            aviso(t("Escena {n} de {total}: imagen…", n=i + 1, total=n), paso)
            nueva = False  # solo se anima una imagen recién creada: repetir una sería gastar cuota en lo mismo
            try:
                img = ultima = ia.imagen(f"{con_glosario(descripcion)}, {plan['estilo_visual']}", ancho, alto,
                                         carpeta / f"imagen_{i:02d}.png")
                nueva, de_donde = True, t("la imagen anterior")
            except Exception as error:
                if ultima is None:  # ni una imagen todavía: fondo de color para que el videoclip salga igual
                    ultima, de_donde = video.fondo(formato, carpeta / "fondo.png", i), t("un fondo de color")
                causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
                notas.append(t("La imagen de la escena {n} no salió ({causa}). Se usó {origen}.", n=i + 1,
                               causa=causa, origen=de_donde))
                aviso(notas[-1], paso)
                img = ultima  # se repite la última imagen que sí existe para no parar el video
            clip, cobrado = None, False
            if animar_ia and nueva:
                try:
                    aviso(t("Escena {n} de {total}: animando…", n=i + 1, total=n), paso + 0.3 / n)
                    clip = ia.video_desde_imagen(img, descripcion, formato, tramo,
                                                 carpeta / f"clip_ia_{i:02d}.mp4", pago)
                except Exception as error:  # cupo de la nube agotado o servicio caído: el resto con zoom suave
                    cobrado = isinstance(error, ia.Cobrado)  # lo hizo pero no llegó: se paga igual
                    causa = str(error).replace(t("Ninguna opción pudo hacerlo.") + "\n", "").replace("\n", " · ")
                    notas.append(t("La IA de video no respondió en la escena {n} ({causa}). El resto va con zoom "
                                   "suave.", n=i + 1, causa=causa))
                    aviso(notas[-1], paso + 0.3 / n)
                    animar_ia = False
                pagados += bool(pago and (clip or cobrado))
            segundos = tramo + (1 if i == n - 1 else 0)  # el último sobra un poco: nunca acaba antes que la canción
            partes.append(video.segmento_mudo(img, segundos, formato, carpeta / f"tramo_{i:02d}.mp4", i, clip))

        if pagados:
            notas.append(ia.nota_pago(pago, pagados))
        aviso(t("Uniendo escenas…"), 0.88)
        visual = video.unir(partes, carpeta / "visual.mp4")
        aviso(t("Poniendo la canción, las ondas y la letra…"), 0.93)
        final = video.con_cancion(visual, audio, formato, palabras, carpeta / "video_musical.mp4")
    except Exception as error:  # los clips de pago ya hechos se dicen: reintentar los pagaría otra vez
        relanzar_con_gasto(error, [ia.nota_pago(pago, pagados)] if pagados else [], carpeta)

    proyecto = {"tipo": "videomusical", "formato": formato, "carpeta": str(carpeta), "titulo": titulo,
                "avisos": notas, "resultados": [{"archivo": str(final), "titulo": titulo,
                                                 "descripcion": plan["descripcion"], "hashtags": plan["hashtags"]}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo! Hay avisos ({n}): los ves debajo del video.", n=len(notas)) if notas else t("¡Listo!"), 1.0)
    return proyecto
