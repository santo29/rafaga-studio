"""Prueba de verdad, con tus claves conectadas: ejecuta cada función con los servicios reales y dice qué funciona.
Uso: .venv\\Scripts\\python prueba_real.py   (gasta poco: casi todo va por las opciones gratis)."""
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from motor import cabina, claves, desde_prompt, ia, nichos, nubes, shorts, video

TMP = Path(tempfile.mkdtemp())
resultados = []


def paso(nombre, funcion):
    print(f"\n▶ {nombre}…", flush=True)
    try:
        detalle = funcion()
        resultados.append((nombre, "✅", detalle or ""))
    except Exception as e:  # cada paso es independiente: se anota el fallo y se sigue
        traceback.print_exc()
        resultados.append((nombre, "❌", str(e)[:160]))


def texto():
    r = ia.texto_json("Responde en español.", "Di un saludo dominicano corto.",
                      {"type": "object", "properties": {"saludo": {"type": "string"}}, "required": ["saludo"],
                       "additionalProperties": False})
    return f"{(claves.para('texto') or {}).get('proveedor', 'IA gratis sin clave')}: {r['saludo']}"


def imagen():
    ia.imagen("a tropical beach at sunset, cinematic photo", 1080, 1920, TMP / "img.png")
    return f"{(TMP / 'img.png').stat().st_size // 1024} KB · hoy: {nubes.resumen_hoy()}"


def transcripcion():
    desde_prompt.narrar("Hola, esto es una prueba de Ráfaga Studio.", "es-DO-EmilioNeural", TMP / "voz.mp3")
    return " ".join(p["palabra"] for p in ia.transcribir(TMP / "voz.mp3"))


def video_ia():
    if not (TMP / "img.png").exists():  # si falló el paso de imagen, se prueba igual el video con el fondo de la marca
        video.fondo("9:16", TMP / "img.png")
    clip = ia.video_desde_imagen(TMP / "img.png", "waves moving, sun glowing", "9:16", 3, TMP / "clip.mp4")
    if not clip:
        raise RuntimeError("no hay ninguna IA de video conectada (Hugging Face o Modal)")
    return f"{video.duracion(clip):.1f}s · hoy: {nubes.resumen_hoy()}"


def video_completo():
    r = desde_prompt.generar("3 datos curiosos sobre República Dominicana", "9:16", 15)
    return r["resultados"][0]["archivo"]


def shorts_enlace():
    r = shorts.generar("https://www.youtube.com/watch?v=jNQXAC9IVRw", cantidad=1, dur_min=5, dur_max=15)
    return r["resultados"][0]["archivo"]


def separacion():
    r = cabina.separar_cancion(str(TMP / "voz.mp3"))
    return r["resultados"][0]["descripcion"]


def investigacion():
    r = nichos.investigar("curiosidades")
    return f"{len(r['nichos'])} nichos · web en vivo: {r['con_web']}"


print("Claves conectadas:", ", ".join(claves.cargar()) or "ninguna")
paso("Texto (guiones)", texto)
paso("Imagen", imagen)
paso("Transcripción", transcripcion)
paso("Video IA (animar imagen)", video_ia)
paso("Video completo desde prompt", video_completo)
paso("Shorts desde enlace", shorts_enlace)
paso("Separar voz y pista", separacion)
paso("Nichos virales", investigacion)

print("\n========== RESULTADO ==========")
for nombre, estado, detalle in resultados:
    print(f"{estado} {nombre}: {detalle}")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if all(e == "✅" for _, e, _ in resultados) else 1)
