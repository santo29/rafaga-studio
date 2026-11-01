"""El acabado de estudio de los videos que hace el estudio, con ffmpeg de verdad sobre entradas pequeñas y sin red:
un clip de IA más corto que su escena no vuelve a empezar (va más lento y se queda en su último cuadro), las escenas
se funden, el sonido sale a -14 LUFS en estéreo, la música baja bajo la voz y lleva el video donde no hay voz, y el
texto en pantalla se ve (no se dice). python -m pruebas.acabado"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from motor import desde_prompt, ia, marca, video  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="rafaga-acabado-"))
marca.ARCHIVO = tmp / "marca.json"  # nunca la marca del usuario


def hacer(nombre, *args) -> Path:
    video.ffmpeg(*args, tmp / nombre)
    return tmp / nombre


def cuadro(archivo: Path, segundo: float) -> np.ndarray:
    """El fotograma de ese segundo en RGB, como lo vería un reproductor."""
    w, h = map(int, re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", video._leer_ffmpeg("-i", archivo)).groups())
    datos = subprocess.run([video.FFMPEG, "-v", "error", "-ss", str(segundo), "-i", str(archivo), "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(datos, np.uint8).reshape(h, w, 3).astype(float)


def sonido(archivo: Path) -> np.ndarray:
    return np.frombuffer(subprocess.run([video.FFMPEG, "-v", "error", "-i", str(archivo), "-f", "f32le", "-ac", "1",
                                         "-ar", "48000", "-"], capture_output=True).stdout, np.float32)


def sonoridad(archivo: Path) -> dict:
    medida = video._leer_ffmpeg("-i", archivo, "-vn", "-af", "loudnorm=print_format=json", "-f", "null", "-")
    return json.loads(medida[medida.rindex("{"):medida.rindex("}") + 1])


def estandar(archivo: Path) -> None:
    datos = video._leer_ffmpeg("-i", archivo)
    assert re.search(r"Video: h264 .*?, yuv420p\(tv, bt709", datos), datos
    assert "48000 Hz, stereo" in datos, datos


# ---------- 1. Un clip de IA más corto que su escena: más lento y quieto al final, nunca vuelve a empezar ----------
# Se aclara con el tiempo (de negro a blanco en 2 s): si volviera a empezar, se vería oscuro otra vez
clip = hacer("clip.mp4", "-f", "lavfi", "-i", "color=c=gray:s=320x568:r=30:d=2,geq=lum='255*T/2':cb=128:cr=128",
             "-c:v", "libx264", "-pix_fmt", "yuv420p")
voz = hacer("voz.wav", "-f", "lavfi", "-i", "sine=frequency=300:duration=3.6,volume=0.05")
ultimo = cuadro(clip, 1.95).mean()
for hecho, dura in ((video.escena_de_clip(clip, voz, "9:16", [], tmp / "escena_clip.mp4"), 3.85),
                    (video.segmento_mudo(clip, 3.85, "9:16", tmp / "mudo_clip.mp4", 0, clip), 3.85)):
    assert abs(video.duracion(hecho) - dura) < 0.08, (hecho.name, video.duracion(hecho))
    brillo = [cuadro(hecho, s / 4).mean() for s in range(int(dura * 4))]
    assert all(b2 >= b1 - 2 for b1, b2 in zip(brillo, brillo[1:])), (hecho.name, brillo)  # nunca vuelve a oscurecer
    assert brillo[0] < 40 and abs(brillo[-1] - ultimo) < 4, (hecho.name, brillo, ultimo)  # acaba en su último cuadro
    assert abs(brillo[-1] - brillo[-2]) < 1, brillo  # 1,5× más lento llega a 3 s: lo demás, quieto
    assert re.search(r"yuv420p\(tv, bt709", video._leer_ffmpeg("-i", hecho))
print("Clips sin volver a empezar pasados.")

# ---------- 2. El acabado: fundido, look, texto en pantalla, -14 LUFS, estéreo ----------
rojo = hacer("rojo.png", "-f", "lavfi", "-i", "color=c=0xC02020:s=576x1024", "-frames:v", "1")
azul = hacer("azul.png", "-f", "lavfi", "-i", "color=c=0x2020C0:s=576x1024", "-frames:v", "1")
voz_a = hacer("voz_a.wav", "-f", "lavfi", "-i", "sine=frequency=300:duration=1.5,volume=0.25")
voz_b = hacer("voz_b.wav", "-f", "lavfi", "-i", "sine=frequency=500:duration=1.5,volume=0.25")
partes = [video.escena_de_imagen(rojo, voz_a, "9:16", [], tmp / "e0.mp4", 0),
          video.escena_de_imagen(azul, voz_b, "9:16", [], tmp / "e1.mp4", 1)]
largos = [video.duracion(p) for p in partes]
LEMA = "EL SABOR QUE TE HACE VOLVER"
final = video.unir(partes, tmp / "final.mp4", "9:16", ["", LEMA], "dorado")
estandar(final)
assert abs(video.duracion(final) - (sum(largos) - video.CRUCE)) < 0.08, (video.duracion(final), largos)
corte = largos[0] - video.CRUCE  # donde empieza la 2.ª escena (y el fundido)
a, medio, b = (cuadro(final, s).mean(axis=(0, 1)) for s in (corte - 0.4, corte + video.CRUCE / 2, corte + 0.6))
assert a[0] > 120 > a[2] and b[2] > 120 > b[0], (a, b)
assert a[0] - 25 > medio[0] > b[0] + 25 and b[2] - 25 > medio[2] > a[2] + 25, (a, medio, b)  # mitad y mitad: fundido
dorado = cuadro(tmp / "e0.mp4", 0.5).mean(axis=(0, 1))
assert a[0] - dorado[0] > 5 or dorado[2] - a[2] > 5, (a, dorado)  # el look «dorado» calienta el rojo
# El lema, en pantalla en la 2.ª escena (arriba, en blanco), y no en la 1.ª
ass = (tmp / "final_textos.ass").read_text(encoding="utf-8")
dialogos = [linea for linea in ass.splitlines() if linea.startswith("Dialogue")]
assert len(dialogos) == 1 and dialogos[0].endswith(LEMA) and "Style: Base,Arial Black" in ass, ass
blancos = [(cuadro(final, s)[:700].min(axis=2) > 200).sum() for s in (corte - 0.4, corte + 0.6)]
assert blancos[0] == 0 and blancos[1] > 500, blancos
m = sonoridad(final)
assert abs(float(m["input_i"]) + 14) <= 1.5 and float(m["input_tp"]) <= -0.5, m
assert abs(float(sonoridad(partes[0])["input_i"]) + 14) > 5  # antes de acabarlo estaba muy por debajo
# La voz de cada escena, entera y en su sitio: la 1.ª suena hasta el fundido y la 2.ª, desde que empieza su escena
pcm = sonido(final)
assert all(np.abs(pcm[int(x * 48000):int((x + 0.2) * 48000)]).max() > 0.05 for x in (corte - 0.25, corte + 0.05))
# Con colores de marca: caja de su color y la letra que mejor se lee (amarillo: negra)
marca.guardar({**marca.POR_DEFECTO, "colores": ["#FFD400"]})
video._titulos_ass([LEMA], [0], [2], "9:16", tmp / "marca.ass")
assert ",&H00000000,&H00000000,&H0000D4FF," in (tmp / "marca.ass").read_text(encoding="utf-8")
marca.ARCHIVO.unlink()
print("Acabado (fundido, look, texto en pantalla, -14 LUFS, estéreo) pasado.")

# ---------- 3. La música: baja bajo la voz y, donde no hay voz, lleva el video ----------
voz_alta = hacer("voz_alta.wav", "-f", "lavfi", "-i", "sine=frequency=300:duration=1.5,volume=2.4")  # como Edge
silencio = hacer("silencio.wav", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3")
musica = hacer("musica.wav", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1,volume=4")  # corta: se repite
partes = [video.escena_de_imagen(rojo, voz_alta, "9:16", [], tmp / "m0.mp4", 0),
          video.escena_de_imagen(azul, silencio, "9:16", [], tmp / "m1.mp4", 1)]
final = video.unir(partes, tmp / "con_musica.mp4", "9:16", ["", ""], "", musica)
estandar(final)
pcm, corte = sonido(final), video.duracion(partes[0]) - video.CRUCE


def banda(desde: float, hz: int) -> float:
    trozo = pcm[int(desde * 48000):int((desde + 0.5) * 48000)]
    espectro = np.abs(np.fft.rfft(trozo * np.hanning(len(trozo))))
    return espectro[int(hz / 2) - 20:int(hz / 2) + 20].max()  # 0,5 s: 2 Hz por punto


bajo_la_voz, sola = banda(0.6, 1000), banda(corte + 1.2, 1000)  # sola: pasado el «release» del compresor
assert banda(0.6, 300) > bajo_la_voz and sola > 3 * bajo_la_voz, (bajo_la_voz, sola)
assert abs(float(sonoridad(final)["input_i"]) + 14) <= 1.5
print("Música bajo la voz y sola donde no hay voz pasada.")

# ---------- 4. montar: el movimiento a la IA de video, el porqué de las escenas quietas y lo de cada escena ----------
reales = desde_prompt.narrar, ia.video_desde_imagen, video.escena_de_imagen, video.escena_de_clip, video.unir
pedidos, unidos, narradas = [], [], []
desde_prompt.narrar = lambda texto, v, destino: narradas.append(texto) or shutil.copy(voz_a, destino) and []
ia.video_desde_imagen = lambda img, prompt, f, s, destino, pago: pedidos.append(prompt) or (
    clip if "dolly" in prompt else None)
video.escena_de_imagen = lambda img, audio, f, palabras, escena, i: escena
video.escena_de_clip = lambda c, audio, f, palabras, escena: escena
video.unir = lambda partes, destino, *a: unidos.append(a) or destino
guion = {"estilo_visual": "cinematic food photography, warm light", "escenas": [
    {"narracion": "Mira esta hamburguesa.", "imagen": "a cheeseburger on a board",
     "movimiento": "slow dolly in; the cheese melts, steam rises", "texto_pantalla": ""},
    {"narracion": "Recién hecha.", "imagen": "a chef at the grill"},  # sin los campos nuevos: sigue valiendo
    {"narracion": "", "imagen": "the burger logo on black", "texto_pantalla": LEMA}]}
try:
    notas, carpeta = [], tmp / "montar"
    carpeta.mkdir()
    desde_prompt.montar(guion, carpeta, "9:16", "es-DO-EmilioNeural", lambda *x: None,
                        crear_imagen=lambda p, w, h, d: d.write_bytes(b"\x89PNG") and d, notas=notas)
finally:
    desde_prompt.narrar, ia.video_desde_imagen, video.escena_de_imagen, video.escena_de_clip, video.unir = reales
assert pedidos == ["slow dolly in; the cheese melts, steam rises", "a chef at the grill",
                   "the burger logo on black"], pedidos
assert narradas == ["Mira esta hamburguesa.", "Recién hecha."], narradas  # el texto en pantalla no se dice
assert abs(video.duracion(carpeta / "video_final_voz_02.mp3") - desde_prompt.SEGUNDOS_SIN_VOZ) < 0.1
assert notas == ["Sin movimiento real en 2 de 3 escenas: van con su imagen y un zoom suave."], notas
assert unidos == [("9:16", ["", "", LEMA], "dorado", None)], unidos
assert video.look_de("3D Pixar cartoon, food") == "" and video.look_de("documentary photo") == "cine"
print("Montar con movimiento, texto en pantalla y escenas quietas dichas pasado.")
