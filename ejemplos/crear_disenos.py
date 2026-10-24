"""Vuelve a crear los diseños de ejemplo con el propio Ráfaga Studio: python ejemplos/crear_disenos.py [id …]

Los diseños de disenos.json los hizo el Director (Claude) en capas editables, en % del lienzo, como los que pide la IA
diseñadora. El estudio de diseño genera las fotos, encaja los textos y lo dibuja todo. Aquí queda cada uno en JPG."""
import json
import os
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA.parent))
os.chdir(CARPETA.parent)
from motor import diseno_ia, nubes, video  # noqa: E402

# Los ejemplos son la muestra de calidad: nunca la opción sin clave de baja resolución y con marca de agua
nubes.ORDEN["imagen"] = [p for p in nubes.ORDEN["imagen"] if p != "gratis_sin_clave"]

pedidos, pendientes = sys.argv[1:], False
for e in json.loads((CARPETA / "disenos.json").read_text(encoding="utf-8")):
    if pedidos and e["id"] not in pedidos:
        continue
    r = diseno_ia.crear("", e["tipo"], False, lambda texto, f: print(f"{f:4.0%} {texto}"), propuesta=e["propuesta"])
    if r["avisos"]:  # una foto que no salió: no sirve de muestra
        print(f"PENDIENTE {e['id']}: " + " | ".join(r["avisos"]))
        pendientes = True
        continue
    video.ffmpeg("-i", r["archivo"], "-q:v", "3", CARPETA / f"{e['id']}.jpg")
    print(f"Listo: ejemplos/{e['id']}.jpg ({r['carpeta']})")
sys.exit(1 if pendientes else 0)
