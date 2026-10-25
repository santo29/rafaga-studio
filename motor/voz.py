"""Asistente de voz del Director: escucha SOLO mientras lo activas (botón del micro o Ctrl+Espacio) y se para solo
cuando terminas de hablar. Entiende con Whisper en este PC (gratis; tu voz no sale de aquí, aunque tengas Groq u
OpenAI conectados) y contesta con las voces gratis de Edge. Sin ElevenLabs ni servicios de pago."""
import math
import re
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from . import desde_prompt, ia
from .idioma import actual, t

SR = 16000  # lo que usa Whisper
BLOQUE = 0.05  # segundos por trozo del micrófono
SILENCIO = 1.2  # callado este rato después de hablar: terminó la frase
MAXIMO = 30  # nadie dicta un pedido más largo: se para igual
SIN_VOZ = 8  # si en este rato no dijo nada, se deja de escuchar
CARPETA = Path(tempfile.gettempdir()) / "rafaga-voz"


def _con_voz(niveles: list[float]) -> list[int]:
    """Los trozos que suenan a voz. El umbral sale del ruido de la sala (los momentos más callados), así funciona
    igual con ventilador que sin él."""
    umbral = max(0.012, 3 * float(np.percentile(niveles, 10)))
    return [i for i, v in enumerate(niveles) if v > umbral]


def hubo_voz(niveles: list[float]) -> bool:
    return len(niveles) * BLOQUE >= 0.5 and len(_con_voz(niveles)) * BLOQUE >= 0.25


def hay_que_parar(niveles: list[float]) -> bool:
    """Con el volumen de cada trozo: ¿ya terminó de hablar?"""
    segundos = len(niveles) * BLOQUE
    if segundos >= MAXIMO:
        return True
    if segundos < 0.5:
        return False
    if not hubo_voz(niveles):  # todavía nada que parezca voz
        return segundos >= SIN_VOZ
    return (len(niveles) - 1 - _con_voz(niveles)[-1]) * BLOQUE >= SILENCIO


def escuchar(detener: threading.Event, nivel=lambda v: None, dispositivo=None) -> np.ndarray:
    """Graba el micrófono hasta que terminas de hablar (o hasta `detener`). nivel(0..1) es el volumen, para la luz.
    Si no se oyó ninguna voz, devuelve audio vacío: Whisper se inventa frases con el silencio."""
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
    return np.concatenate(trozos) if trozos and hubo_voz(niveles) else np.zeros(0, np.float32)


def entender(audio: np.ndarray) -> str:
    """Lo que dijo, en texto («» si no se entendió nada). Siempre en este PC."""
    if len(audio) < SR * 0.3:
        return ""
    import soundfile as sf
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "voz.wav"
        sf.write(str(wav), audio, SR)
        palabras = ia.transcribir(wav, idioma=actual(), en_pc=True)
    return " ".join(p["palabra"] for p in palabras).strip()


# Un sí claro es corto y solo dice que sí: «dale un segundo», «ok, espérate» o «sí, pero ¿cuánto?» no lo son
SI_CLARO = re.compile(r"[\s¡]*(s[ií]|claro|dale|hazlo|adelante|acepto|yes|sim|oui)"
                      r"([\s,]+(s[ií]|claro|dale|hazlo|adelante|por favor))*[\s.!,]*")
SI = {"si", "sí", "claro", "dale", "hazlo", "vale", "ok", "okay", "adelante", "acepto", "yes", "yeah", "sure", "sim",
      "oui"}
NO = {"no", "nop", "nope", "cancela", "cancelar", "para", "espera", "espérate", "esperate", "aguanta", "momento",
      "déjame", "dejame", "pensar", "pensarlo", "nunca", "non", "não", "nao"}


def si_o_no(texto: str) -> bool | None:
    """La respuesta a «¿Lo hago?»: True solo con un sí claro, False con un no (o un «espera») sin ningún sí, y None
    si no está clara. Sin un sí claro no se gasta."""
    texto = str(texto).lower()
    if SI_CLARO.fullmatch(texto):
        return True
    palabras = set(re.findall(r"\w+", texto))
    return False if palabras & NO and not palabras & SI else None


_RUTA = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\|…)(?:[^\n«»\"\\/]*[\\/])+([^\\/\n«»\"]+?\.[A-Za-z0-9]{2,4})"
                   r"(?=[\s«»\".,;:)]|$)")
_DOLARES = re.compile(r"US\$\s?(\d+)[.,](\d\d)|(\d+)[.,](\d\d)\s?\$\s?US")


def para_decir(texto: str) -> str:
    """Lo que se lee en voz alta de una pregunta o respuesta del Director: de una ruta, solo el nombre del archivo
    (se leía «C dos puntos barra Users barra…» entero), y los dólares como se dicen («unos 36 centavos de dólar», no
    «U S dólar cero punto treinta y seis»). En la ventana sigue todo tal cual."""
    def dolares(m):
        usd = int(m[1] or m[3]) + int(m[2] or m[4]) / 100
        if usd < 1:
            return t("{n} centavos de dólar", n=round(usd * 100))
        return t("un dólar") if usd == 1 else t("{n} dólares", n=math.ceil(usd))  # por lo alto, como la ventana
    return _DOLARES.sub(dolares, _RUTA.sub(lambda m: m[1], str(texto)))


def hablar(texto: str) -> Path:
    """La respuesta en voz alta (MP3 con la voz gratis del idioma de la app)."""
    texto = para_decir(texto)
    CARPETA.mkdir(exist_ok=True)
    for viejo in CARPETA.glob("respuesta-*.mp3"):  # las de antes; la que suena ahora puede estar abierta
        try:
            viejo.unlink()
        except OSError:
            pass
    destino = CARPETA / f"respuesta-{time.time_ns()}.mp3"
    desde_prompt.narrar(str(texto)[:1500], desde_prompt.voz_por_defecto(), destino)
    return destino
