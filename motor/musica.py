"""Estudio de música: la IA escribe la letra y produce la canción o la pista, de cualquier género."""
import base64
import json
import re
import time
from typing import Callable

import httpx

from . import claves, guardia, ia, memoria
from .idioma import t
from .shorts import PROYECTOS

# Descripción musical en inglés: los modelos de música la entienden mejor. Nada de samples: composición original.
PRECIO = {"gemini": 0.08, "elevenlabs": 0.45}  # US$ por canción, aprox. y por lo alto (ElevenLabs: ~0,30-0,45)
GENEROS = {
    "Dembow clásico (riddim jamaiquino 90s)": (
        "classic old-school Dominican dembow built like the 1990s Jamaican dancehall riddims from before the "
        "Fever Pitch era (Poco Man Jam / Dem Bow, Fish Market, Pepperseed style), fully original, no samples: "
        "112 BPM, the signature dembow drum pattern (boom-ch-boom-chick), raw MPC drums, dry snare rolls, timbal and "
        "conga fills, deep 808 sub bass, simple minor-key synth stabs, horn hits, call-and-response hype chants, "
        "street energy, raw lo-fi mix"),
    "Dembow moderno": "modern Dominican dembow, 125 BPM, hard 808s, fast hi-hats, aggressive synth leads, party energy",
    "Reggaetón": "reggaeton, dembow rhythm 95 BPM, warm pads, perreo, catchy hook, polished modern mix",
    "Dancehall jamaiquino": "Jamaican dancehall riddim, 100 BPM, digital riddim, heavy bass, patois-style chants",
    "Bachata": "Dominican bachata, requinto guitar arpeggios, bongos, güira, romantic, 128 BPM",
    "Merengue típico": "merengue típico, accordion, tambora, güira, fast and festive, 150 BPM",
    "Salsa": "salsa dura, piano montuno, brass section, congas and timbales, clave 2-3",
    "Trap latino": "Latin trap, 140 BPM half-time, dark 808s, rolling hi-hats, melodic autotuned vocals",
    "Hip hop / rap": "boom bap hip hop, 90 BPM, dusty drums, vinyl samples feel, punchy bass",
    "Pop": "modern pop, catchy chorus, bright synths, radio-ready mix",
    "Afrobeat": "afrobeats, 105 BPM, log drums, shakers, groovy bass, sunny vibe",
    "Corridos tumbados": "corridos tumbados, requinto guitar, tololoche bass, trap influence",
    "Cristiana / adoración": "worship ballad, piano and pads, building to an uplifting anthem",
    "Lo-fi para videos": "lo-fi hip hop, mellow keys, vinyl crackle, relaxed, loopable background",
    "Épica / cinemática": "epic cinematic trailer music, orchestra, huge drums, rising tension",
}

ESQUEMA = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "estilo": {"type": "string"},
        "letra": {"type": "string"},
        "descripcion": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["titulo", "estilo", "letra", "descripcion", "hashtags"],
    "additionalProperties": False,
}

INSTRUCCIONES = """Eres compositor y productor musical de éxitos. Escribe canciones originales listas para grabar.
- letra: con etiquetas de sección en inglés entre corchetes ([Intro], [Verse 1], [Chorus], [Bridge], [Outro]).
  Coro pegajoso y repetible, frases cortas con rima y flow. Si el género es dembow o dancehall, usa jerga
  dominicana real y coros de calle de llamada y respuesta. Nada de contenido de odio ni nombres de artistas reales.
- Letra en el idioma de la idea o en el que pida el usuario.
- estilo: descripción de producción en inglés (instrumentos, BPM, ambiente, voz) basada en el estilo dado.
- titulo, descripcion y hashtags para publicar la canción. hashtags: el del género pedido y otros del tema; nunca
  de otro género.
- """ + ia.FALTAS


def _elevenlabs(c: dict, estilo: str, letra: str | None, segundos: int) -> bytes:
    prompt = estilo if letra is None else f"{estilo}\n\nLyrics:\n{letra}"
    r = httpx.post("https://api.elevenlabs.io/v1/music", params={"output_format": "mp3_48000_192"},  # el de los modelos v2
                   headers={"xi-api-key": c["clave"]}, timeout=900,
                   json={"prompt": prompt[:4000], "music_length_ms": segundos * 1000, "model_id": c["modelo_musica"],
                         "force_instrumental": letra is None})
    if r.status_code in (401, 402, 403):
        detalle = ia.motivo(r)
        if "permission" in detalle:  # una clave creada sin el permiso de música, aunque el plan sí lo tenga
            raise RuntimeError(t("Tu clave de ElevenLabs no tiene permiso para crear música: en ElevenLabs, edita la "
                                 "clave y activa «Music». ({detalle})", detalle=detalle))
        raise RuntimeError(t("ElevenLabs no dejó crear la música ({codigo}): {detalle}", codigo=r.status_code,
                             detalle=detalle))
    r.raise_for_status()
    return r.content


class SinPlanGemini(RuntimeError):
    """Gemini rechazó Lyria (403 o 429) sin cobrar nada: en automático se puede probar con ElevenLabs."""


def _gemini(c: dict, estilo: str, letra: str | None, segundos: int) -> bytes:
    pedido = (f"{estilo}. Duration about {segundos} seconds."
              + ("\nInstrumental only, no vocals." if letra is None else f"\n\nLyrics:\n{letra}"))
    r = httpx.post("https://generativelanguage.googleapis.com/v1beta/interactions", timeout=900,
                   headers={"x-goog-api-key": c["clave"]}, json={"model": c["modelo_musica"], "input": pedido})
    if r.status_code in (403, 429):  # Lyria no tiene plan gratis: sin facturación, Google responde así
        raise SinPlanGemini(t("Lyria no está en el plan gratis de Gemini ({codigo}): activa la facturación en Google "
                              "AI Studio o elige ElevenLabs en «Claves de IA» → «Música». ({detalle})",
                              codigo=r.status_code, detalle=ia.motivo(r)))
    r.raise_for_status()

    def buscar(nodo):  # el audio viene en base64 dentro de un bloque {"type": "audio", "data": …}
        if isinstance(nodo, dict):
            if nodo.get("type") == "audio" and nodo.get("data"):
                return nodo["data"]
            nodo = list(nodo.values())
        if isinstance(nodo, list):
            return next((d for d in map(buscar, nodo) if d), None)
    datos = buscar(r.json())
    if not datos:
        raise RuntimeError(t("Gemini no devolvió audio."))
    return base64.b64decode(datos)


def crear(idea: str, genero: str, con_voz: bool = True, segundos: int = 150,
          aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    c = claves.para("musica")
    if not c or not c.get("clave"):
        raise ia.SinClave(t("Conecta una clave de música: Gemini (Lyria, unos US$0.08 por canción, con la "
                            "facturación activada) o ElevenLabs (plan de pago)."))
    guardia.sin_bloqueo()  # las canciones son de pago (Lyria o ElevenLabs): con el estudio bloqueado no empieza
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-musica")
    carpeta.mkdir(parents=True)
    estilo_base = GENEROS.get(genero, genero)

    aviso(t("La IA está escribiendo la canción…") if con_voz else t("La IA está diseñando la pista…"), 0.05)
    # Para una pista instrumental no se pide letra: así no hay un campo vacío o null que la validación rechace.
    esquema = ESQUEMA if con_voz else {**ESQUEMA, "required": [k for k in ESQUEMA["required"] if k != "letra"],
                                       "properties": {k: v for k, v in ESQUEMA["properties"].items() if k != "letra"}}
    cancion = ia.texto_json(INSTRUCCIONES, (
        f"Idea: {idea}\nGénero y producción: {estilo_base or 'elígelo tú según la idea'}\nDuración: unos {segundos} segundos.\n"
        + ("Con voz y letra." if con_voz else "Solo pista instrumental, sin letra.") + memoria.para("musica_voz")),
        esquema)
    # Sin el «•» que pone sin_markdown a una lista: la letra va tal cual al modelo de música y a letra.txt
    letra = re.sub(r"(?m)^• ", "", cancion.get("letra") or "") if con_voz else ""
    # Antes de producir: si el audio falla (plan, cuota, red), la letra que ya escribió la IA no se pierde.
    archivo_letra = carpeta / "letra.txt"
    archivo_letra.write_text(f"{cancion['titulo']}\n\n{letra}", encoding="utf-8")

    aviso(t("Produciendo con {proveedor} (puede tardar unos minutos)…", proveedor=claves.nombre(c["proveedor"])), 0.3)
    audio = carpeta / "cancion.mp3"
    estilo = ". ".join(e for e in (estilo_base, cancion["estilo"]) if e)
    avisos = []

    def producir(c):
        con = _elevenlabs if c["proveedor"] == "elevenlabs" else _gemini
        return con(c, estilo, letra if con_voz else None, segundos)
    try:
        try:
            datos = producir(c)
        except SinPlanGemini as de_gemini:  # Gemini no cobró: en automático, sale con ElevenLabs si hay clave
            respaldo = claves.cargar().get("elevenlabs")
            if not respaldo or claves.ajustes().get("musica", "auto") != "auto":
                raise
            avisos.append(t("Gemini no dejó usar Lyria (necesita la facturación de Gemini activada en Google AI "
                            "Studio): esta canción se hizo con tu clave de ElevenLabs."))
            aviso(t("Produciendo con {proveedor} (puede tardar unos minutos)…", proveedor=claves.nombre("elevenlabs")),
                  0.3)
            try:
                datos = producir(respaldo)
            except Exception as de_eleven:  # si los dos fallan, los dos motivos: el de Gemini es el que se arregla
                raise RuntimeError(f"{de_gemini}\n\n{de_eleven}") from de_eleven
        audio.write_bytes(datos)
    except Exception as e:
        if not con_voz:
            raise
        raise RuntimeError(t("{error}\n\nTu letra no se perdió: está en {archivo}",
                             error=str(e).strip() or type(e).__name__, archivo=archivo_letra)) from e

    # En el texto para publicar, la letra sin las marcas para el modelo de música: ni [Intro], [Chorus]… ni las
    # acotaciones en inglés («(Shout: ¡Wepa!)», «(Fade out with tambora…)»), y con la ortografía repasada línea a línea
    publicar = {"titulo": cancion["titulo"], "descripcion": cancion["descripcion"], "hashtags": cancion["hashtags"],
                "lineas": ia.sin_acotaciones(letra).split("\n")}
    if genero in GENEROS:  # el hashtag del género, primero: la IA ponía otros que no son («#MúsicaRomántica»)
        propio = "#" + "".join(p[:1].upper() + p[1:] for p in re.findall(r"\w+", re.split(r"[(/]", genero)[0]))
        publicar["hashtags"] = [propio] + [h for h in publicar["hashtags"] if ia.hashtag(h).lower() != propio.lower()]
    ia.repasar([publicar], ("titulo", "descripcion", "hashtags", "lineas"), notas=avisos)
    para_publicar = "\n".join(publicar["lineas"]).strip()
    proyecto = {"tipo": "musica", "formato": "audio", "carpeta": str(carpeta), "titulo": publicar["titulo"],
                "genero": genero, "avisos": avisos, "resultados": [{
                    "archivo": str(audio), "titulo": publicar["titulo"], "hashtags": publicar["hashtags"],
                    "descripcion": publicar["descripcion"] + (f"\n\n{para_publicar}" if para_publicar else "")}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto
