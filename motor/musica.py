"""Estudio de música: la IA escribe la letra y produce la canción o la pista, de cualquier género."""
import base64
import json
import time
from typing import Callable

import httpx

from . import claves, ia
from .idioma import t
from .shorts import PROYECTOS

# Descripción musical en inglés: los modelos de música la entienden mejor. Nada de samples: composición original.
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
- titulo, descripcion y hashtags para publicar la canción."""


def _elevenlabs(c: dict, estilo: str, letra: str | None, segundos: int) -> bytes:
    prompt = estilo if letra is None else f"{estilo}\n\nLyrics:\n{letra}"
    r = httpx.post("https://api.elevenlabs.io/v1/music", params={"output_format": "mp3_44100_128"},
                   headers={"xi-api-key": c["clave"]}, timeout=900,
                   json={"prompt": prompt[:4000], "music_length_ms": segundos * 1000, "model_id": c["modelo_musica"],
                         "force_instrumental": letra is None})
    if r.status_code in (401, 402, 403):
        raise RuntimeError(t("ElevenLabs no permite música con este plan (la API de música es solo para planes de "
                             "pago)."))
    r.raise_for_status()
    return r.content


def _gemini(c: dict, estilo: str, letra: str | None, segundos: int) -> bytes:
    pedido = (f"{estilo}. Duration about {segundos} seconds."
              + ("\nInstrumental only, no vocals." if letra is None else f"\n\nLyrics:\n{letra}"))
    r = httpx.post("https://generativelanguage.googleapis.com/v1beta/interactions", timeout=900,
                   headers={"x-goog-api-key": c["clave"]}, json={"model": c["modelo_musica"], "input": pedido})
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
        raise ia.SinClave(t("Conecta una clave de música: ElevenLabs (plan de pago) o Gemini (Lyria, ~$0.08 por "
                            "canción)."))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-musica")
    carpeta.mkdir(parents=True)
    estilo_base = GENEROS.get(genero, genero)

    aviso(t("La IA está escribiendo la canción…") if con_voz else t("La IA está diseñando la pista…"), 0.05)
    # Para una pista instrumental no se pide letra: así no hay un campo vacío o null que la validación rechace.
    esquema = ESQUEMA if con_voz else {**ESQUEMA, "required": [k for k in ESQUEMA["required"] if k != "letra"],
                                       "properties": {k: v for k, v in ESQUEMA["properties"].items() if k != "letra"}}
    cancion = ia.texto_json(INSTRUCCIONES, (
        f"Idea: {idea}\nGénero y producción: {estilo_base or 'elígelo tú según la idea'}\nDuración: unos {segundos} segundos.\n"
        + ("Con voz y letra." if con_voz else "Solo pista instrumental, sin letra.")), esquema)
    letra = (cancion.get("letra") or "") if con_voz else ""

    aviso(t("Produciendo con {proveedor} (puede tardar unos minutos)…", proveedor=c["proveedor"].capitalize()), 0.3)
    producir = _elevenlabs if c["proveedor"] == "elevenlabs" else _gemini
    audio = carpeta / "cancion.mp3"
    estilo = ". ".join(e for e in (estilo_base, cancion["estilo"]) if e)
    audio.write_bytes(producir(c, estilo, letra if con_voz else None, segundos))
    (carpeta / "letra.txt").write_text(f"{cancion['titulo']}\n\n{letra}", encoding="utf-8")

    proyecto = {"tipo": "musica", "formato": "audio", "carpeta": str(carpeta), "titulo": cancion["titulo"],
                "genero": genero, "resultados": [{
                    "archivo": str(audio), "titulo": cancion["titulo"], "hashtags": cancion["hashtags"],
                    "descripcion": cancion["descripcion"] + (f"\n\n{letra}" if con_voz else "")}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto
