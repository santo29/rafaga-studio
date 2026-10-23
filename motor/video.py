"""Motor de video: formatos tipo CapCut, subtítulos animados y llamadas a ffmpeg."""
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from .idioma import t

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

FORMATOS = {
    "9:16": (1080, 1920),   # Shorts, TikTok, Reels
    "16:9": (1920, 1080),   # YouTube
    "1:1": (1080, 1080),    # Feed cuadrado
    "4:5": (1080, 1350),    # Feed Instagram/Facebook
}


# Formatos que ffmpeg puede abrir como entrada: solo audio, video e imagen. Sin esta lista, un archivo que por dentro
# es un manifiesto de streaming (DASH), aunque empiece como un MP3 de verdad, hace que ffmpeg pida las URLs que trae,
# también las de tu red local. (-protocol_whitelist no lo frena: lo probamos.)
MEDIOS = ("mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,mp3,wav,flac,ogg,aac,aiff,asf,flv,mpegts,avi,mpeg,"
          "image2,png_pipe,jpeg_pipe,webp_pipe,bmp_pipe")


def solo_medios(args: list[str]) -> list[str]:
    """Pone delante de cada -i la lista MEDIOS (más el formato que se fuerce con -f, p. ej. lavfi o concat)."""
    salida, forzado = [], None
    for i, a in enumerate(args):
        if a == "-i":
            salida += ["-format_whitelist", f"{forzado},{MEDIOS}" if forzado else MEDIOS]
            forzado = None
        elif a == "-f" and i + 1 < len(args):
            forzado = args[i + 1]
        salida.append(a)
    return salida


def ffmpeg(*args, cwd: Path | None = None) -> None:
    r = subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *solo_medios([str(a) for a in args])],
                       cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(t("ffmpeg falló: {error}", error=r.stderr.strip()[-800:]))


def _leer_ffmpeg(*args) -> str:
    """Lo que ffmpeg cuenta (en stderr) al abrir el archivo con esos argumentos."""
    return subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-format_whitelist", MEDIOS, *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stderr


def medir(archivo: Path) -> tuple[float, bool]:
    """(segundos que dura, si trae imagen). La portada de una canción (attached pic) no cuenta como imagen."""
    salida = _leer_ffmpeg("-i", archivo)
    hallado = re.findall(r"Duration: (\d+):(\d+):([\d.]+)", salida)[:1]
    if not hallado and "Duration: N/A" in salida:
        # Sin duración en la cabecera (un .webm grabado en el navegador): se recorre entero sin descodificar
        hallado = re.findall(r"time=(\d+):(\d+):([\d.]+)", _leer_ffmpeg("-i", archivo, "-c", "copy", "-f", "null", "-"))
    if not hallado:
        raise RuntimeError(t("No se pudo leer {nombre}: no es un audio o video válido.", nombre=Path(archivo).name))
    h, m, s = hallado[-1]
    return (int(h) * 3600 + int(m) * 60 + float(s),
            re.search(r"Stream #\S+.*: Video:(?!.*attached pic)", salida) is not None)


def duracion(archivo: Path) -> float:
    return medir(archivo)[0]


def filtro_formato(formato: str, modo: str) -> str:
    """Encaja el video en el formato. modo 'recortar' llena la pantalla; 'difuminar' muestra todo con fondo borroso."""
    w, h = FORMATOS[formato]
    if modo == "difuminar":
        return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=25:5[fondo];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[frente];"
                f"[fondo][frente]overlay=(W-w)/2:(H-h)/2,setsar=1")
    # ponytail: recorte centrado. Si el que habla está a un lado, se corta; seguir caras (OpenCV) cuando haga falta.
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def _t(seg: float) -> str:
    seg = max(seg, 0)
    return f"{int(seg // 3600)}:{int(seg % 3600 // 60):02d}:{seg % 60:05.2f}"


def _texto_ass(texto: str) -> str:
    """Texto de la IA o del usuario dentro de un .ass: sin saltos de línea ni llaves (no puede añadir líneas ni
    etiquetas al archivo) y sin «<» (si pareciera un manifiesto DASH, ffmpeg no abriría el .ass)."""
    return re.sub(r"[\r\n]+", " ", texto).replace("{", "(").replace("}", ")").replace("<", "‹")


def subtitulos_ass(palabras: list[dict], formato: str, destino: Path, por_grupo: int = 3) -> Path:
    """Subtítulos estilo CapCut: grupos de pocas palabras, grandes, con la palabra que suena en amarillo."""
    w, h = FORMATOS[formato]
    tam = int(min(w, h) * 0.085)
    lineas = [
        # ScaledBorderAndShadow: el borde y la sombra encogen con el video (vista previa a 640) como las letras
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Base,Arial Black,{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,"
        f"{max(tam // 12, 3)},2,2,60,60,{int(h * 0.22)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for i in range(0, len(palabras), por_grupo):
        grupo = palabras[i:i + por_grupo]
        for j, actual in enumerate(grupo):
            fin = grupo[j + 1]["inicio"] if j + 1 < len(grupo) else actual["fin"]
            # La palabra que suena: amarilla y con un salto (crece al 125% y vuelve en 0.12 s).
            activa = "{\\c&H00FFFF&\\fscx125\\fscy125\\t(0,120,\\fscx100\\fscy100)}"
            texto = " ".join((activa + _texto_ass(p["palabra"].upper()) + "{\\c&HFFFFFF&\\fscx100\\fscy100}")
                             if k == j else _texto_ass(p["palabra"].upper()) for k, p in enumerate(grupo))
            lineas.append(f"Dialogue: 0,{_t(actual['inicio'])},{_t(fin)},Base,,0,0,0,,{texto}")
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino


def recortar(origen: Path, inicio: float, fin: float, formato: str, modo: str,
             palabras: list[dict], destino: Path) -> Path:
    """Saca el tramo [inicio, fin] del video, lo pasa al formato y le quema subtítulos."""
    tramo = [{**p, "inicio": p["inicio"] - inicio, "fin": p["fin"] - inicio}
             for p in palabras if p["inicio"] >= inicio and p["fin"] <= fin]
    ass = subtitulos_ass(tramo, formato, destino.with_suffix(".ass"))
    # ffmpeg en Windows se lía con rutas absolutas dentro de un filtro: se usa el nombre relativo con cwd.
    ffmpeg("-ss", inicio, "-to", fin, "-i", origen.resolve(),
           "-vf", f"{filtro_formato(formato, modo)},subtitles={ass.name}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", destino.name, cwd=destino.parent)
    return destino


def fondo(formato: str, destino: Path, indice: int = 0) -> Path:
    """Fondo degradado con los colores de la marca: último recurso si no se pudo crear ninguna imagen."""
    w, h = FORMATOS[formato]
    ffmpeg("-f", "lavfi", "-i", f"gradients=s={w}x{h}:c0=0x7C5CFF:c1=0xFF4D8D:c2=0x0F0F13:n=3:type=radial:seed={indice}",
           "-frames:v", "1", "-vf", "vignette", destino.name, cwd=destino.parent)
    return destino


def escena_de_imagen(imagen: Path, audio: Path, formato: str, palabras: list[dict],
                     destino: Path, indice: int) -> Path:
    """Una escena: imagen con zoom lento (efecto Ken Burns) + voz + subtítulos."""
    w, h = FORMATOS[formato]
    seg = duracion(audio) + 0.25
    cuadros = int(seg * 30)
    # Alterna acercar y alejar para que no todas las escenas se vean iguales.
    zoom = "min(1.0+0.0007*on,1.18)" if indice % 2 == 0 else "max(1.18-0.0007*on,1.0)"
    ass = subtitulos_ass(palabras, formato, destino.with_suffix(".ass"))
    ffmpeg("-loop", "1", "-i", imagen.resolve(), "-i", audio.resolve(),
           "-vf", f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                  f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={cuadros}:s={w}x{h}:fps=30,"
                  f"setsar=1,subtitles={ass.name}",
           "-t", seg, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", destino.name, cwd=destino.parent)
    return destino


def escena_de_clip(clip: Path, audio: Path, formato: str, palabras: list[dict], destino: Path) -> Path:
    """Una escena a partir de un clip de IA: se repite hasta cubrir la voz, se ajusta al formato y lleva subtítulos."""
    seg = duracion(audio) + 0.25
    ass = subtitulos_ass(palabras, formato, destino.with_suffix(".ass"))
    ffmpeg("-stream_loop", "-1", "-i", clip.resolve(), "-i", audio.resolve(), "-map", "0:v", "-map", "1:a",
           "-vf", f"{filtro_formato(formato, 'recortar')},fps=30,subtitles={ass.name}",
           "-t", seg, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", destino.name, cwd=destino.parent)
    return destino


def segmento_mudo(imagen: Path, segundos: float, formato: str, destino: Path, indice: int,
                  clip: Path | None = None) -> Path:
    """Tramo de video sin sonido: el clip de IA repetido o la imagen con zoom suave. Para videos musicales."""
    w, h = FORMATOS[formato]
    if clip:
        entrada = ["-stream_loop", "-1", "-i", clip.resolve()]
        filtro = f"{filtro_formato(formato, 'recortar')},fps=30"
    else:
        zoom = "min(1.0+0.0007*on,1.18)" if indice % 2 == 0 else "max(1.18-0.0007*on,1.0)"
        entrada = ["-loop", "1", "-i", imagen.resolve()]
        filtro = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                  f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(segundos * 30)}:s={w}x{h}:fps=30,"
                  "setsar=1")
    ffmpeg(*entrada, "-vf", filtro, "-t", segundos, "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", destino.name, cwd=destino.parent)
    return destino


def ritmo(cancion: Path) -> tuple[float, float]:
    """Tempo (BPM) y momento del primer golpe de la canción."""
    import librosa
    # Se decodifica con ffmpeg (y su lista MEDIOS): librosa solo lee WAV/MP3/OGG/FLAC y fallaba con M4A, WMA o WEBM.
    # Con los primeros 5 minutos basta para el tempo y el primer golpe.
    sr = 22050
    y = np.frombuffer(subprocess.run([FFMPEG, "-v", "error", "-format_whitelist", MEDIOS, "-i", str(cancion), "-t", "300",
                                      "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                                     capture_output=True, check=True).stdout, np.float32)
    tempo, golpes = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bpm = float(np.atleast_1d(tempo)[0]) or 100.0
    return bpm, float(golpes[0]) if len(golpes) else 0.0


def con_cancion(visual: Path, cancion: Path, formato: str, palabras: list[dict], destino: Path) -> Path:
    """Pone la canción al video: zoom y destello en cada golpe del beat, ondas que se mueven con el sonido
    y la letra estilo karaoke."""
    w, h = FORMATOS[formato]
    alto_ondas = int(h * 0.10)
    ass = subtitulos_ass(palabras, formato, destino.with_suffix(".ass"))
    bpm, inicio = ritmo(cancion)
    # Pulso: vale 1 en cada golpe y se apaga en ~0.15 s. Las canciones de este estilo tienen tempo fijo.
    def pulso(t):
        return f"if(gte({t},{inicio:.3f}),exp(-14*mod({t}-{inicio:.3f},{60 / bpm:.4f})),0)"
    # zoompan con d=1 hace un zoom por cuadro sin cambiar el tamaño de salida.
    latido = (f"zoompan=z='1+0.035*{pulso('in_time')}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
              f"s={w}x{h}:fps=30,eq=brightness='0.05*{pulso('t')}':eval=frame")
    ffmpeg("-i", visual.resolve(), "-i", cancion.resolve(), "-filter_complex",
           f"[0:v]{latido}[base];"
           f"[1:a]showwaves=s={w}x{alto_ondas}:mode=cline:rate=30:colors=0xFFFFFF@0.85|0xFF4D8D@0.85,"
           f"format=rgba[ondas];[base][ondas]overlay=0:{h - alto_ondas - int(h * 0.04)}:shortest=1,"
           f"subtitles={ass.name}[v]",
           "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", destino.name, cwd=destino.parent)
    return destino


def cierre(video_in: Path, texto: str, formato: str, destino: Path, segundos: float = 3.0) -> Path:
    """Cierre de anuncio: en los últimos segundos oscurece el fondo y entra la oferta en grande, con un salto."""
    w, h = FORMATOS[formato]
    inicio = max(duracion(video_in) - segundos, 0)
    tam = int(min(w, h) * 0.11)
    lineas = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
              "[V4+ Styles]",
              "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
              "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
              "MarginL, MarginR, MarginV, Encoding",
              f"Style: Oferta,Arial Black,{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,"
              f"{max(tam // 10, 4)},3,8,70,70,{int(h * 0.12)},1",  # arriba, para no tapar el producto
              "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
              # Entra pequeña, crece al 108% y se asienta: el «pop» de los anuncios.
              f"Dialogue: 0,{_t(inicio)},{_t(inicio + segundos + 1)},Oferta,,0,0,0,,"
              "{\\fad(150,0)\\fscx40\\fscy40\\t(0,220,\\fscx108\\fscy108)\\t(220,380,\\fscx100\\fscy100)}"
              + "\\N".join(_texto_ass(linea) for linea in texto.upper().split("\n"))]
    ass = destino.with_suffix(".ass")
    ass.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    ffmpeg("-i", video_in.resolve(), "-vf",
           f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.5:t=fill:enable='gte(t,{inicio:.2f})',subtitles={ass.name}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
           "-movflags", "+faststart", destino.name, cwd=destino.parent)
    return destino


def unir(partes: list[Path], destino: Path) -> Path:
    lista = destino.with_suffix(".txt")
    lista.write_text("".join(f"file '{p.name}'\n" for p in partes), encoding="utf-8")
    ffmpeg("-f", "concat", "-safe", "0", "-i", lista.name, "-c", "copy", "-movflags", "+faststart",
           destino.name, cwd=destino.parent)
    return destino
