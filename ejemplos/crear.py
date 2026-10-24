"""Vuelve a crear los videos de ejemplo con el propio Ráfaga Studio: python ejemplos/crear.py [id …]

Los guiones de ejemplos.json los escribió el Director (Claude). Las imágenes (la IA de imágenes conectada; sin claves,
FLUX gratis en Hugging Face), la voz, los subtítulos, el movimiento y el montaje los hace el motor, igual que con
cualquier pedido. Aquí queda una copia ligera (720p) de cada video, su miniatura y un GIF corto para el README."""
import json
import os
import shutil
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA.parent))
os.chdir(CARPETA.parent)
from motor import claves, desde_prompt, ia, nubes, video  # noqa: E402
from motor.shorts import PROYECTOS  # noqa: E402

ajustes_reales = claves.ajustes

# Los ejemplos son la muestra de calidad: nunca la opción sin clave de baja resolución y con marca de agua
nubes.ORDEN["imagen"] = [p for p in nubes.ORDEN["imagen"] if p != "gratis_sin_clave"]

pedidos, pendientes = sys.argv[1:], False
for e in json.loads((CARPETA / "ejemplos.json").read_text(encoding="utf-8")):
    if pedidos and e["id"] not in pedidos:
        continue
    trabajo = PROYECTOS / f"ejemplo-{e['id']}"
    trabajo.mkdir(parents=True, exist_ok=True)
    # Las imágenes de otro ejemplo, si ya se hicieron (si no, se generan con su descripción como las demás)
    origen = PROYECTOS / f"ejemplo-{e.get('reusa', {}).get('de', '')}"
    for i, n in enumerate(e.get("reusa", {}).get("imagenes", [])):
        de, a = origen / f"video_final_imagen_{n:02d}.png", trabajo / f"video_final_imagen_{i:02d}.png"
        if de.is_file() and not a.is_file():
            shutil.copy(de, a)
    # «animar»: cada escena se anima con la IA de video de tu nube Modal (solo en este ejemplo; tus ajustes no cambian)
    claves.ajustes = (lambda: {**ajustes_reales(), "video": "modal"}) if e.get("animar") else ajustes_reales
    notas, hablados = [], {}
    if e.get("animado"):  # cada escena, un video de IA con su propia voz (Gemini, de pago: ~US$1 por escena)
        gasto = []
        hablados = desde_prompt.clips_hablados(e["guion"], trabajo, e["formato"],
                                               lambda texto, f: print(f"{f:4.0%} {texto}"), None, gasto)
        print(" | ".join(gasto))
        if len(hablados) < len(e["guion"]["escenas"]):
            notas.append("faltan escenas animadas con voz")
    # Las imágenes que ya salieron se guardan: si la cuota gratis se acaba a mitad, la próxima vez sigue donde iba
    final = desde_prompt.montar(e["guion"], trabajo, e["formato"], e["voz"], lambda texto, f: print(f"{f:4.0%} {texto}"),
                                crear_imagen=lambda p, w, h, destino: destino if destino.is_file() else
                                ia.imagen(p, w, h, destino), notas=notas, hablados=hablados)
    if e.get("cierre"):
        final = video.cierre(final, e["cierre"], e["formato"], trabajo / "con_cierre.mp4")
    if notas:  # un ejemplo con imágenes repetidas no sirve de muestra: se vuelve a intentar otro día
        print(f"PENDIENTE {e['id']}: " + " | ".join(notas))
        pendientes = True
        continue
    escala = "scale=-2:1280" if e["formato"] in ("9:16", "4:5") else "scale=1280:-2"
    video.ffmpeg("-i", final, "-vf", escala, "-c:v", "libx264", "-preset", "slow", "-crf", "27", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", CARPETA / f"{e['id']}.mp4")
    video.ffmpeg("-ss", "2.5", "-i", final, "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4",
                 CARPETA / f"{e['id']}.jpg")
    video.ffmpeg("-t", "6", "-i", final, "-filter_complex",
                 "fps=8,scale=240:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse",
                 CARPETA / f"{e['id']}.gif")
    print(f"Listo: ejemplos/{e['id']}.mp4")
sys.exit(1 if pendientes else 0)
