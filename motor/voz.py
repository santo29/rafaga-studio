"""Asistente de voz del Director: escucha SOLO mientras lo activas (botón del micro o Ctrl+Espacio) y se para solo
cuando terminas de hablar. Entiende con Whisper en este PC (gratis; tu voz no sale de aquí, salvo que hayas elegido
Groq u OpenAI para transcribir) y contesta con las voces gratis de Edge. Sin ElevenLabs ni servicios de pago."""
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from . import desde_prompt, ia
from .idioma import actual

SR = 16000  # lo que usa Whisper
BLOQUE = 0.05  # segundos por trozo del micrófono
SILENCIO = 1.2  # callado este rato después de hablar: terminó la frase
MAXIMO = 30  # nadie dicta un pedido más largo: se para igual
SIN_VOZ = 8  # si en este rato no dijo nada, se deja de escuchar
CARPETA = Path(tempfile.gettempdir()) / "rafaga-voz"


def hay_que_parar(niveles: list[float]) -> bool:
    """Con el volumen de cada trozo: ¿ya terminó de hablar? El umbral sale del ruido de la sala (los momentos más
    callados), así funciona igual con ventilador que sin él."""
    segundos = len(niveles) * BLOQUE
    if segundos >= MAXIMO:
        return True
    if segundos < 0.5:
        return False
    umbral = max(0.012, 3 * float(np.percentile(niveles, 10)))
    voz = [i for i, v in enumerate(niveles) if v > umbral]
    if len(voz) * BLOQUE < 0.25:  # todavía nada que parezca voz
        return segundos >= SIN_VOZ
    return (len(niveles) - 1 - voz[-1]) * BLOQUE >= SILENCIO


def escuchar(detener: threading.Event, nivel=lambda v: None, dispositivo=None) -> np.ndarray:
    """Graba el micrófono hasta que terminas de hablar (o hasta `detener`). nivel(0..1) es el volumen, para la luz."""
    import sounddevice as sd
    trozos, niveles, tamano = [], [], int(SR * BLOQUE)
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=tamano, device=dispositivo) as micro:
        while not detener.is_set():
            datos, _ = micro.read(tamano)
            trozos.append(datos[:, 0].copy())
            niveles.append(float(np.sqrt(np.mean(np.square(datos)))))
            nivel(min(niveles[-1] * 8, 1.0))
            if hay_que_parar(niveles):
                break
    return np.concatenate(trozos) if trozos else np.zeros(0, np.float32)


def entender(audio: np.ndarray) -> str:
    """Lo que dijo, en texto («» si no se entendió nada)."""
    if len(audio) < SR * 0.3:
        return ""
    import soundfile as sf
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "voz.wav"
        sf.write(str(wav), audio, SR)
        palabras = ia.transcribir(wav, idioma=actual())
    return " ".join(p["palabra"] for p in palabras).strip()


def hablar(texto: str) -> Path:
    """La respuesta en voz alta (MP3 con la voz gratis del idioma de la app)."""
    CARPETA.mkdir(exist_ok=True)
    for viejo in CARPETA.glob("respuesta-*.mp3"):  # las de antes; la que suena ahora puede estar abierta
        try:
            viejo.unlink()
        except OSError:
            pass
    destino = CARPETA / f"respuesta-{time.time_ns()}.mp3"
    desde_prompt.narrar(str(texto)[:1500], desde_prompt.voz_por_defecto(), destino)
    return destino
