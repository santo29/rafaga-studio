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

# Al final de cada video que hace el estudio: H.264 estándar, yuv420p en rango limitado («tv») y BT.709 dicho en el
# archivo (ffmpeg pasa al MP4 los datos de color del fotograma). Una imagen JPEG (rango completo, BT.601) daba
# «yuvj420p(pc, bt470bg)»: en el reproductor de la app y en Windows se veía negro, y móviles y redes no siempre lo leen
COLOR = ("scale=out_range=tv:out_color_matrix=bt709,format=yuv420p,"
         "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709")


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


def titulo_cancion(archivo: Path) -> str:
    """El título de verdad de una canción, no «cancion» (el nombre del archivo): el del proyecto del estudio que la
    hizo (también desde la voz o la pista separadas, unas carpetas más abajo), la 1.ª línea de su letra.txt o la
    etiqueta «title» del archivo. Si no hay, el nombre del archivo sin guiones bajos."""
    import json
    archivo = Path(archivo)
    for carpeta in list(archivo.parents)[:5]:
        try:
            titulo = json.loads((carpeta / "proyecto.json").read_text(encoding="utf-8")).get("titulo")
        except (OSError, ValueError, AttributeError):
            titulo = None
        if not titulo and (carpeta / "letra.txt").is_file():
            titulo = (carpeta / "letra.txt").read_text(encoding="utf-8").split("\n", 1)[0]
        if isinstance(titulo, str) and titulo.strip():
            return " ".join(titulo.split())[:80]
    try:
        etiqueta = re.search(r"(?m)^\s+title\s*:\s*(.+?)\s*$", _leer_ffmpeg("-i", archivo))
    except OSError:
        etiqueta = None
    return etiqueta[1][:80] if etiqueta else archivo.stem.replace("_", " ").strip()


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


def _estilo_ass(fuente, tam, letra, antes, contorno, fondo, negrita, borde, grosor, sombra, alineacion, margen) -> str:
    """La línea «Style: Base» de un .ass. Colores &HAABBGGRR (AA 00 = opaco); borde 1 = contorno, 3 = caja."""
    return (f"Style: Base,{fuente},{tam},{letra},{antes},{contorno},{fondo},{negrita},0,0,0,100,100,0,0,{borde},"
            f"{grosor},{sombra},{alineacion},60,60,{margen},1")


def _grupos(palabras: list[dict], por_grupo: int) -> list[list[dict]]:
    """Grupos de por_grupo palabras como mucho, sin juntar dos frases: se corta tras un punto o un silencio."""
    grupos = []
    for p in palabras:
        if grupos and len(ultimo := grupos[-1]) < por_grupo and p["inicio"] - ultimo[-1]["fin"] <= 0.6 \
                and not ultimo[-1]["palabra"].rstrip().endswith((".", "?", "!", "…")):
            ultimo.append(p)
        else:
            grupos.append([p])
    return grupos


def subtitulos_ass(palabras: list[dict], formato: str, destino: Path, por_grupo: int = 3,
                   estilo: str = "clasico") -> Path:
    """Subtítulos estilo CapCut: grupos de pocas palabras, grandes, con la palabra que suena resaltada. estilo: una
    clave de edicion.ESTILOS_SUBTITULOS («clasico», la palabra en amarillo con un salto, es el de siempre)."""
    w, h = FORMATOS[formato]
    tam = int(min(w, h) * 0.085)
    abajo, grosor = int(h * 0.22), max(tam // 12, 3)
    # (estilo base, la palabra que suena, cómo vuelven las demás, en mayúsculas). «karaoke» y «minimal» van por grupo
    estilos = {
        "clasico": (_estilo_ass("Arial Black", tam, "&H00FFFFFF", "&H00FFFFFF", "&H00000000", "&H64000000", 1, 1,
                                grosor, 2, 2, abajo),
                    "{\\c&H00FFFF&\\fscx125\\fscy125\\t(0,120,\\fscx100\\fscy100)}", "{\\c&HFFFFFF&\\fscx100\\fscy100}",
                    True),
        # La caja es del color del contorno, un poco transparente
        "caja": (_estilo_ass("Arial Black", int(tam * 0.85), "&H00FFFFFF", "&H00FFFFFF", "&H33000000", "&H00000000",
                             1, 3, max(tam // 6, 4), 0, 2, abajo), "{\\c&H4DE1FF&}", "{\\c&HFFFFFF&}", True),
        # Contorno rosa difuminado (\blur): brilla; la palabra que suena, cian con brillo violeta
        "neon": (_estilo_ass("Arial Black", tam, "&H00FFFFFF", "&H00FFFFFF", "&H008D4DFF", "&H00000000", 1, 1,
                             max(tam // 9, 4), 0, 2, abajo),
                 "{\\c&HFFE500&\\3c&HFF5C7C&}", "{\\c&HFFFFFF&\\3c&H8D4DFF&}", True),
        # \kf: cada palabra se va llenando de violeta (PrimaryColour) mientras suena; antes, blanca (SecondaryColour)
        "karaoke": (_estilo_ass("Arial Black", tam, "&H00FF5C7C", "&H00FFFFFF", "&H00000000", "&H64000000", 1, 1,
                                grosor, 2, 2, abajo), "", "", True),
        "minimal": (_estilo_ass("Arial", int(tam * 0.6), "&H00FFFFFF", "&H00FFFFFF", "&H00000000", "&H80000000", 0, 1,
                                max(tam // 30, 1), 1, 2, int(h * 0.1)), "", "", False),
        # Una palabra cada vez, enorme y en el centro, con un «pop» (entra pequeña, se pasa un poco y se asienta)
        "impacto": (_estilo_ass("Arial Black", int(min(w, h) * 0.16), "&H00FFFFFF", "&H00FFFFFF", "&H00000000",
                                "&H64000000", 1, 1, max(tam // 6, 4), 3, 5, 0),
                    "{\\fscx60\\fscy60\\t(0,90,\\fscx112\\fscy112)\\t(90,160,\\fscx100\\fscy100)}", "", True),
    }
    base, activa, normal, mayusculas = estilos[estilo]
    por_grupo = 1 if estilo == "impacto" else por_grupo
    lineas = [
        # ScaledBorderAndShadow: el borde y la sombra encogen con el video (vista previa a 640) como las letras
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        base,
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    brillo = "{\\blur5}" if estilo == "neon" else ""
    for grupo in _grupos(palabras, por_grupo):
        letras = [_texto_ass(p["palabra"].upper() if mayusculas else p["palabra"]) for p in grupo]
        if estilo in ("karaoke", "minimal"):  # una sola línea por grupo
            if estilo == "karaoke":  # cada palabra se llena hasta que empieza la siguiente (\kf va en centésimas)
                hasta = [p["inicio"] for p in grupo[1:]] + [grupo[-1]["fin"]]
                letras = [f"{{\\kf{round((fin - p['inicio']) * 100)}}}{palabra}"
                          for p, palabra, fin in zip(grupo, letras, hasta)]
            lineas.append(f"Dialogue: 0,{_t(grupo[0]['inicio'])},{_t(grupo[-1]['fin'])},Base,,0,0,0,,"
                          f"{' '.join(letras)}")
            continue
        for j, actual in enumerate(grupo):
            fin = grupo[j + 1]["inicio"] if j + 1 < len(grupo) else actual["fin"]
            texto = " ".join(activa + palabra + normal if k == j else palabra for k, palabra in enumerate(letras))
            lineas.append(f"Dialogue: 0,{_t(actual['inicio'])},{_t(fin)},Base,,0,0,0,,{brillo}{texto}")
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
           "-vf", f"{filtro_formato(formato, modo)},ass={ass.name},{COLOR}",
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
                  f"setsar=1,ass={ass.name},{COLOR}",
           "-t", seg, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", destino.name, cwd=destino.parent)
    return destino


def escena_de_clip(clip: Path, audio: Path, formato: str, palabras: list[dict], destino: Path) -> Path:
    """Una escena a partir de un clip de IA: se repite hasta cubrir la voz, se ajusta al formato y lleva subtítulos."""
    seg = duracion(audio) + 0.25
    ass = subtitulos_ass(palabras, formato, destino.with_suffix(".ass"))
    ffmpeg("-stream_loop", "-1", "-i", clip.resolve(), "-i", audio.resolve(), "-map", "0:v", "-map", "1:a",
           "-vf", f"{filtro_formato(formato, 'recortar')},fps=30,ass={ass.name},{COLOR}",
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
    ffmpeg(*entrada, "-vf", f"{filtro},{COLOR}", "-t", segundos, "-an", "-c:v", "libx264", "-preset", "veryfast",
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
    # Del primer al último golpe: el tempo de librosa va a escalones (~5 BPM) y, con él, los golpes se iban corriendo
    # (120 BPM salía 117,45: a los 10 s, un cuarto de golpe tarde)
    bpm = (60 * (len(golpes) - 1) / float(golpes[-1] - golpes[0]) if len(golpes) > 1 and golpes[-1] > golpes[0]
           else float(np.atleast_1d(tempo)[0]) or 100.0)
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
           f"ass={ass.name},{COLOR}[v]",
           "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", destino.name, cwd=destino.parent)
    return destino


def cierre(video_in: Path, texto: str, formato: str, destino: Path, segundos: float = 3.0,
           producto: Path | None = None) -> Path:
    """Cierre de anuncio: cuando acaba la narración, el último fotograma se queda unos segundos, oscurecido, y entra
    la oferta en grande, con un salto, sobre la foto real del producto si se da. Va DESPUÉS de la voz: encima de los
    últimos segundos, el subtítulo de la narración salía gris debajo de la oferta (texto doble)."""
    w, h = FORMATOS[formato]
    inicio = duracion(video_in)
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
    desde = f"enable='gte(t,{inicio:.2f})'"
    grafo = (f"[0:v]tpad=stop_mode=clone:stop_duration={segundos},"
             f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.55:t=fill:{desde}[fondo]")
    if producto:  # la foto, bajo la oferta (que va arriba), hasta el 62 % del ancho y el 42 % del alto
        grafo += (f";[1:v]scale={int(w * 0.62)}:{int(h * 0.42)}:force_original_aspect_ratio=decrease[foto];"
                  f"[fondo][foto]overlay=(W-w)/2:(H-h)*0.6:{desde}[con_foto]")
    ffmpeg("-i", video_in.resolve(), *(["-i", producto.resolve()] if producto else []), "-filter_complex",
           f"{grafo};[{'con_foto' if producto else 'fondo'}]ass={ass.name},{COLOR}[v];[0:a]apad=pad_dur={segundos}[a]",
           "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", destino.name, cwd=destino.parent)
    return destino


def unir(partes: list[Path], destino: Path) -> Path:
    lista = destino.with_suffix(".txt")
    lista.write_text("".join(f"file '{p.name}'\n" for p in partes), encoding="utf-8")
    ffmpeg("-f", "concat", "-safe", "0", "-i", lista.name, "-c", "copy", "-movflags", "+faststart",
           destino.name, cwd=destino.parent)
    return destino
