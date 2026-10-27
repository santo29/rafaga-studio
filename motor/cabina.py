"""Cabina de grabación con IA: grabar sobre la pista, separar voz y pista, afinar, mezclar y masterizar."""
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from . import seguro, video
from .idioma import t
from .shorts import PROYECTOS

SR = 44100
NOTAS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAYOR, MENOR = [0, 2, 4, 5, 7, 9, 11], [0, 2, 3, 5, 7, 8, 10]

# Cómo suena la voz en cada estilo (lo que haría un ingeniero de mezcla).
PRESETS = {
    "Dembow / urbano (seco y al frente)": {"reverb": 0.10, "sala": 0.25, "delay": 0.10, "comp": 6.0, "presencia": 4.0,
                                           "brillo": 3.0, "saturacion": 3.0, "voz_db": 1.5, "lufs": -8.5},
    "Reggaetón / trap (moderno)": {"reverb": 0.15, "sala": 0.35, "delay": 0.15, "comp": 5.0, "presencia": 3.5,
                                   "brillo": 3.5, "saturacion": 2.0, "voz_db": 1.0, "lufs": -9.0},
    "Bachata / balada (amplio)": {"reverb": 0.30, "sala": 0.60, "delay": 0.12, "comp": 3.5, "presencia": 2.5,
                                  "brillo": 2.0, "saturacion": 0.5, "voz_db": 0.5, "lufs": -11.0},
    "Rap / hip hop (crudo)": {"reverb": 0.06, "sala": 0.20, "delay": 0.05, "comp": 5.0, "presencia": 3.0,
                              "brillo": 2.0, "saturacion": 4.0, "voz_db": 2.0, "lufs": -9.0},
    "Natural (poco efecto)": {"reverb": 0.08, "sala": 0.30, "delay": 0.0, "comp": 2.5, "presencia": 1.5,
                              "brillo": 1.0, "saturacion": 0.0, "voz_db": 0.0, "lufs": -12.0},
}


def a_wav(origen: Path, destino: Path) -> Path:
    """Cualquier audio (mp3, m4a…) a WAV estéreo 44.1 kHz para trabajar sin pérdidas."""
    # Máximo 15 min (~320 MB en memoria): una canción cabe de sobra y un archivo enorme no tumba el PC.
    video.ffmpeg("-i", origen.resolve(), "-t", 900, "-ac", "2", "-ar", SR, "-c:a", "pcm_f32le", destino.name,
                 cwd=destino.parent)
    return destino


def leer(archivo: Path) -> np.ndarray:
    datos, sr = sf.read(str(archivo), dtype="float32", always_2d=True)
    assert sr == SR, f"{archivo.name} no está a {SR} Hz"
    return datos.T  # (canales, muestras), el formato de pedalboard


def escribir(archivo: Path, audio: np.ndarray) -> Path:
    sf.write(str(archivo), audio.T, SR, subtype="FLOAT")
    return archivo


# ---------- Grabación ----------

def grabar(pista: Path, destino: Path, detener: threading.Event, dispositivo_entrada=None,
           aviso: Callable[[str, float], None] = lambda t, f: None) -> Path:
    """Reproduce la pista por los audífonos y graba el micrófono a la vez. Corrige el retraso de la tarjeta de sonido."""
    import sounddevice as sd
    beat = leer(pista).T  # (muestras, canales)
    grabado, pos = [], [0]
    total = len(beat)

    def callback(entrada, salida, cuadros, _tiempo, _estado):
        trozo = beat[pos[0]:pos[0] + cuadros]
        salida[:len(trozo)] = trozo
        salida[len(trozo):] = 0
        grabado.append(entrada[:, 0].copy())
        pos[0] += cuadros
        if pos[0] >= total or detener.is_set():
            raise sd.CallbackStop

    with sd.Stream(samplerate=SR, channels=(1, 2), dtype="float32", callback=callback,
                   device=(dispositivo_entrada, None)) as flujo:
        retraso = flujo.latency[0] + flujo.latency[1]
        while flujo.active:
            aviso(f"🔴 {t('Grabando… {s:.1f} s de {total:.0f} s', s=pos[0] / SR, total=total / SR)}",
                  min(pos[0] / total, 1))
            time.sleep(0.2)
    voz = np.concatenate(grabado) if grabado else np.zeros(1, np.float32)
    voz = voz[int(retraso * SR):]  # lo grabado llega tarde por la latencia de entrada + salida
    return escribir(destino, np.stack([voz, voz]))


# ---------- Análisis de la pista ----------

def analizar(pista: Path) -> dict:
    """Tempo (BPM) y tonalidad de la pista, para sincronizar el delay y afinar en la escala correcta."""
    import librosa
    y = leer(pista).mean(axis=0)
    tempo, _ = librosa.beat.beat_track(y=y, sr=SR)
    croma = librosa.feature.chroma_cqt(y=y, sr=SR).mean(axis=1)
    # Perfiles de Krumhansl: cuánto "pesa" cada grado en una escala mayor o menor.
    perfil_mayor = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    perfil_menor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    candidatos = [(np.corrcoef(croma, np.roll(p, t))[0, 1], t, modo)
                  for t in range(12) for p, modo in ((perfil_mayor, "mayor"), (perfil_menor, "menor"))]
    _, tonica, modo = max(candidatos)
    return {"bpm": round(float(np.atleast_1d(tempo)[0]), 1), "tonica": tonica, "modo": modo,
            "tono": t("{nota} mayor", nota=NOTAS[tonica]) if modo == "mayor" else t("{nota} menor", nota=NOTAS[tonica])}


# ---------- Afinación (tipo Auto-Tune) ----------

def afinar(voz: np.ndarray, tonica: int, modo: str, fuerza: float = 0.8) -> np.ndarray:
    """Lleva cada nota cantada a la nota más cercana de la escala. fuerza 0 = natural, 1 = efecto robot."""
    import librosa
    import psola
    if fuerza <= 0:
        return voz
    mono = voz.mean(axis=0)
    fmin, fmax = librosa.note_to_hz("C2"), librosa.note_to_hz("C6")
    f0, sonora, _ = librosa.pyin(mono, fmin=fmin, fmax=fmax, sr=SR, frame_length=2048)
    escala = np.array([(tonica + g) % 12 for g in (MAYOR if modo == "mayor" else MENOR)])
    midi = librosa.hz_to_midi(f0)
    def a_escala(m):
        if np.isnan(m):
            return m
        candidatas = np.array([o * 12 + n for o in range(1, 9) for n in escala])
        return candidatas[np.argmin(np.abs(candidatas - m))]
    objetivo = np.array([a_escala(m) for m in midi])
    objetivo = midi + (objetivo - midi) * fuerza
    objetivo_hz = np.where(sonora, librosa.midi_to_hz(objetivo), np.nan)
    corregida = psola.vocode(mono, SR, target_pitch=objetivo_hz, fmin=fmin, fmax=fmax)
    return np.stack([corregida, corregida]).astype(np.float32)


# ---------- Mezcla y master ----------

def procesar_voz(voz: np.ndarray, preset: dict, bpm: float) -> np.ndarray:
    from pedalboard import (Compressor, Delay, Distortion, Gain, HighpassFilter, HighShelfFilter, NoiseGate,
                            PeakFilter, Pedalboard, Reverb)
    corchea_con_punto = 60 / max(bpm, 60) * 0.75  # delay a tempo con la pista
    cadena = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=90),            # fuera el retumbe del micrófono
        NoiseGate(threshold_db=-45, ratio=4, release_ms=120),
        PeakFilter(cutoff_frequency_hz=300, gain_db=-2.5, q=1.0),  # menos "caja" o voz de cuarto
        Compressor(threshold_db=-20, ratio=preset["comp"], attack_ms=5, release_ms=80),
        PeakFilter(cutoff_frequency_hz=3200, gain_db=preset["presencia"], q=0.9),  # voz al frente
        HighShelfFilter(cutoff_frequency_hz=9000, gain_db=preset["brillo"]),
        Distortion(drive_db=preset["saturacion"]),
        PeakFilter(cutoff_frequency_hz=6500, gain_db=-2.0, q=3.0),  # ponytail: suaviza las "s"; no es un de-esser real
        Delay(delay_seconds=corchea_con_punto, feedback=0.25, mix=preset["delay"]),
        Reverb(room_size=preset["sala"], wet_level=preset["reverb"], dry_level=1.0, width=0.9),
        Gain(gain_db=preset["voz_db"]),
    ])
    return cadena(voz, SR)


def _envolvente(audio: np.ndarray, ventana: int = 2048) -> np.ndarray:
    energia = np.convolve(np.abs(audio.mean(axis=0)), np.ones(ventana) / ventana, mode="same")
    return energia / (energia.max() + 1e-9)


def mezclar(voz: np.ndarray, pista: np.ndarray) -> np.ndarray:
    """Junta voz y pista. Cuando entra la voz la pista baja hasta 3 dB (sidechain), para que la voz se entienda."""
    largo = max(voz.shape[1], pista.shape[1])
    voz = np.pad(voz, ((0, 0), (0, largo - voz.shape[1])))
    pista = np.pad(pista, ((0, 0), (0, largo - pista.shape[1])))
    bajada = 1 - (1 - 10 ** (-3 / 20)) * np.clip(_envolvente(voz) * 3, 0, 1)
    mezcla = pista * bajada + voz
    return mezcla / max(np.abs(mezcla).max() / 0.9, 1)  # deja margen para el master


def masterizar(mezcla: Path, destino: Path, preset: dict, referencia: Path | None = None) -> Path:
    """Con referencia, copia el sonido (volumen, brillo, graves) de una canción que te guste. Sin ella, master por estilo."""
    if referencia:
        import matchering as mg
        mg.process(target=str(mezcla), reference=str(referencia), results=[mg.pcm24(str(destino))])
        return destino
    from pedalboard import Compressor, Gain, Limiter, LowShelfFilter, Pedalboard
    audio = leer(mezcla)
    rms_db = 20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-9)
    # ponytail: volumen por RMS como aproximación a LUFS; para medir LUFS de verdad usar pyloudnorm.
    subir = preset["lufs"] - rms_db
    cadena = Pedalboard([LowShelfFilter(cutoff_frequency_hz=80, gain_db=1.0),
                         Compressor(threshold_db=-14, ratio=2.0, attack_ms=20, release_ms=150),
                         Gain(gain_db=subir), Limiter(threshold_db=-1.5, release_ms=80)])
    salida = cadena(audio, SR)
    # El limitador deja escapar picos y el MP3 suma algo más: techo duro a -1.5 dBFS para que nunca distorsione.
    return escribir(destino, salida * min(1.0, 0.84 / (np.abs(salida).max() + 1e-9)))


# ---------- Separación de voz y pista ----------

def separar(cancion: Path, carpeta: Path, aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """Saca la voz y la pista de una canción. Prueba primero la nube gratis y, si no, lo hace en este PC."""
    from . import nubes
    return nubes.separar(cancion, carpeta, aviso)


# ---------- Sesión completa ----------

def sesion(pista: str, voz: str, estilo: str = "Dembow / urbano (seco y al frente)", fuerza_afinacion: float = 0.6,
           referencia: str = "", titulo: str = t("Mi canción"),
           aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """De pista + voz grabada a canción terminada (mezclada y masterizada), con cada parte por separado."""
    pista = str(seguro.archivo_medio(pista, seguro.AUDIOS, t("pista")))
    voz = str(seguro.archivo_medio(voz, seguro.AUDIOS, t("voz")))
    if referencia:
        referencia = str(seguro.archivo_medio(referencia, seguro.AUDIOS, t("canción de referencia")))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-cabina")
    carpeta.mkdir(parents=True)
    aviso(t("Preparando audio…"), 0.03)
    pista_wav = a_wav(Path(pista), carpeta / "pista.wav")
    voz_wav = a_wav(Path(voz), carpeta / "voz_cruda.wav")
    preset = PRESETS.get(estilo, PRESETS["Natural (poco efecto)"])

    aviso(t("Escuchando la pista (tempo y tonalidad)…"), 0.1)
    info = analizar(pista_wav)
    aviso(t("Pista a {bpm} BPM en {tono}. Afinando la voz…", bpm=info["bpm"], tono=info["tono"]), 0.25)
    voz_audio = afinar(leer(voz_wav), info["tonica"], info["modo"], fuerza_afinacion)
    aviso(t("Cadena de voz: limpieza, compresión, ecualización, delay y reverb…"), 0.55)
    voz_lista = escribir(carpeta / "voz_procesada.wav", procesar_voz(voz_audio, preset, info["bpm"]))
    aviso(t("Mezclando con la pista…"), 0.7)
    mezcla = escribir(carpeta / "mezcla.wav", mezclar(leer(voz_lista), leer(pista_wav)))
    aviso(t("Masterizando…"), 0.82)
    ref = a_wav(Path(referencia), carpeta / "referencia.wav") if referencia else None
    master = masterizar(mezcla, carpeta / "master.wav", preset, ref)
    final = carpeta / "cancion_final.mp3"
    video.ffmpeg("-i", master.name, "-c:a", "libmp3lame", "-b:a", "320k", final.name, cwd=carpeta)

    proyecto = {"tipo": "cabina", "formato": "audio", "carpeta": str(carpeta), "titulo": titulo, "analisis": info,
                "resultados": [{"archivo": str(final), "titulo": titulo, "hashtags": [],
                                "descripcion": t("{bpm} BPM · {tono} · {estilo}", bpm=info["bpm"],
                                                 tono=info["tono"], estilo=t(estilo))}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto


def separar_cancion(cancion: str, aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """Proyecto que deja la voz (acapella) y la pista (instrumental) de cualquier canción."""
    cancion = str(seguro.archivo_medio(cancion, seguro.AUDIOS, t("canción")))
    carpeta = PROYECTOS / time.strftime("%Y%m%d-%H%M%S-separacion")
    carpeta.mkdir(parents=True)
    original = Path(shutil.copy(cancion, carpeta / f"original{Path(cancion).suffix.lower()}"))
    partes = separar(original, carpeta, aviso)
    # Los títulos van en español y se traducen al mostrarlos (ui/comun.Reproductor): si se cambia el idioma de la
    # app, un proyecto viejo también sale en el nuevo (sus traducciones están en idiomas/*.json)
    proyecto = {"tipo": "separacion", "formato": "audio", "carpeta": str(carpeta),
                "titulo": video.titulo_cancion(Path(cancion)),  # el de la canción, no «cancion» (su archivo)
                "resultados": [{"archivo": str(partes["voz"]), "titulo": "Voz (a capela)",
                                "descripcion": partes["donde"], "hashtags": []},
                               {"archivo": str(partes["pista"]), "titulo": "Pista (instrumental)",
                                "descripcion": partes["donde"], "hashtags": []}]}
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso(t("¡Listo!"), 1.0)
    return proyecto
