"""Asistente de voz del Director: escucha SOLO mientras lo activas (botón del micro o Ctrl+Espacio) y se para solo
cuando terminas de hablar. Entiende con Whisper en este PC (gratis; tu voz no sale de aquí, aunque tengas Groq u
OpenAI conectados) y contesta con las voces gratis de Edge. Sin ElevenLabs ni servicios de pago."""
import math
import os
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
# Silenciado o bloqueado en Windows, el micro da ceros. Se avisa a los SIN_VOZ s, cuando si no se diría «No te escuché»:
# algunos micros vivos también dan silencio digital mientras nadie habla, y avisar antes sería una falsa alarma
MUDO, SIN_SONIDO = 1e-4, SIN_VOZ
CARPETA = Path(tempfile.gettempdir()) / "rafaga-voz"


def _con_voz(niveles: list[float]) -> list[int]:
    """Los trozos que suenan a voz. El umbral sale del ruido de la sala (los momentos más callados), así funciona
    igual con ventilador que sin él. El mínimo es bajo: una voz que llega bajita al micro de un portátil (-30 dBFS de
    pico, trozos de hasta 0.011, medido con voz de Edge) con el 0.012 de antes nunca se oía, ni un «sí» corto."""
    # y con tu voz: el ruido de la sala que queda 15 dB por debajo de ti no cuenta como voz (si no, no paraba hasta los
    # 30 s); p90 y no el máximo, para que un clic suelto no lo suba
    umbral = max(0.003, 2.5 * float(np.percentile(niveles, 10)), 0.15 * float(np.percentile(niveles, 90)))
    return [i for i, v in enumerate(niveles) if v > umbral]


def hubo_voz(niveles: list[float]) -> bool:
    # 0.15 s de voz: un «sí» corto suena unos 0.25 s, y un clic de teclado solo 0.05
    return len(niveles) * BLOQUE >= 0.5 and len(_con_voz(niveles)) * BLOQUE >= 0.15


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
    Si no se oyó ninguna voz, devuelve audio vacío: Whisper se inventa frases con el silencio. Si no llega ningún
    sonido (micro silenciado o bloqueado en Windows: el audio llega en ceros), lo dice en vez de esperar callado."""
    import sounddevice as sd
    if silenciado():  # Windows lo dice al momento: no hace falta esperar 8 s de ceros para saberlo
        raise MicroSilenciado(SILENCIADO())
    trozos, niveles, tamano = [], [], int(SR * BLOQUE)
    try:
        micro = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=tamano, device=dispositivo)
    except (sd.PortAudioError, ValueError) as e:  # sin micrófono o desactivado: que se entienda, no «device -1»
        raise RuntimeError(t("No encuentro un micrófono que funcione: conéctalo o actívalo en Windows ({error}).",
                             error=e)) from e
    with micro:
        while not detener.is_set():
            datos, _ = micro.read(tamano)
            trozos.append(datos[:, 0].copy())
            niveles.append(float(np.sqrt(np.mean(np.square(datos)))))
            nivel(min(float(np.sqrt(niveles[-1])) * 2.5, 1.0))  # con raíz, la luz late también con un micro bajo
            if len(niveles) * BLOQUE >= SIN_SONIDO and max(niveles) < MUDO:
                raise MicroSilenciado(SILENCIADO())
            if hay_que_parar(niveles):
                break
    return np.concatenate(trozos) if trozos and hubo_voz(niveles) else np.zeros(0, np.float32)


class MicroSilenciado(RuntimeError):
    """El micrófono de Windows está silenciado o bloqueado: la ventana ofrece abrir los ajustes de sonido."""


def SILENCIADO() -> str:  # noqa: N802 (una función y no una constante: el texto sale en el idioma de ese momento)
    return t("No me llega sonido del micrófono: está silenciado o bloqueado en Windows. Actívalo (tecla del micrófono "
             "del portátil, o Configuración › Sonido › Entrada y Privacidad › Micrófono) y pulsa «Hablar» otra vez.")


def silenciado() -> bool | None:
    """Si Windows tiene silenciado el micrófono por defecto (Core Audio, solo lectura: no graba ni cambia nada). None
    si no se puede saber (otro sistema o un fallo): entonces decide lo que llega del micrófono, como antes."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import POINTER, byref, c_int, c_void_p, wintypes

    class Guid(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    def guid(texto):
        g = Guid()
        ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p("{" + texto + "}"), byref(g))
        return g

    def metodo(objeto, indice, *tipos):  # el método `indice` de la tabla virtual del objeto COM
        tabla = ctypes.cast(objeto, POINTER(POINTER(c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *tipos)(tabla[indice])

    ole32, objetos = ctypes.oledll.ole32, []
    try:
        ole32.CoInitialize(None)  # en el hilo que escucha COM aún no está iniciado
        enumerador, dispositivo, volumen, mudo = c_void_p(), c_void_p(), c_void_p(), wintypes.BOOL()
        ole32.CoCreateInstance(byref(guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 23,
                               byref(guid("A95664D2-9614-4F35-A746-DE8DB63617E6")), byref(enumerador))
        objetos.append(enumerador)
        metodo(enumerador, 4, c_int, c_int, POINTER(c_void_p))(enumerador, 1, 0, byref(dispositivo))  # captura, consola
        objetos.append(dispositivo)
        metodo(dispositivo, 3, POINTER(Guid), wintypes.DWORD, c_void_p, POINTER(c_void_p))(
            dispositivo, byref(guid("5CDF2C82-841E-4546-9722-0CF74078229A")), 23, None, byref(volumen))
        objetos.append(volumen)
        metodo(volumen, 15, POINTER(wintypes.BOOL))(volumen, byref(mudo))  # IAudioEndpointVolume::GetMute
        return bool(mudo.value)
    except (OSError, ValueError):  # sin micrófono, o Core Audio que no responde: no se sabe
        return None
    finally:
        for objeto in reversed(objetos):
            if objeto:
                ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(
                    ctypes.cast(objeto, POINTER(POINTER(c_void_p))).contents[2])(objeto)  # Release
        ole32.CoUninitialize()


def preparar():
    """Va cargando Whisper mientras hablas (no toca el micrófono): al terminar de hablar ya está listo, y si es la
    primera vez, la descarga empieza antes. En un portátil de 4 hilos, cargarlo cuesta ~4 s de los ~17 s de la primera
    orden; transcribir, ~8 s."""
    threading.Thread(target=ia.whisper, daemon=True).start()


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
