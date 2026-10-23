"""Editor de video tipo CapCut: el modelo del proyecto (un dict JSON, versión 1), su validación, su carpeta y las
operaciones de la línea de tiempo. Sin ventanas: lo usan la interfaz, el render y el MCP.

Un proyecto puede venir de un archivo ajeno: todo pasa por validar(), que da una copia limpia o un ValueError en
español diciendo qué y dónde. Todas las operaciones devuelven un proyecto NUEVO validado (no tocan el que reciben):
el deshacer es una pila de copias. Las funciones de consulta (tiempos, clip_en, capas_en…) esperan uno ya validado.

Reglas que aplica validar() además de tipos y rangos:
- Los archivos de clips y audios son rutas ABSOLUTAS de este PC (C:\\…), sin «..», sin rutas de red y con la
  extensión de su tipo. validar() NO toca el disco: abrir() y anadir_medio() pasan cada archivo por
  seguro.archivo_medio, y quien lo use (render) debe hacer lo mismo antes de dárselo a ffmpeg.
- Clips de video y audios llevan «duracion_archivo» (lo que dura el archivo, medido al añadirlo): «hasta» no pasa de
  ahí. Si falta, vale «hasta». Las fotos no lo llevan, siempre tienen desde=0 y velocidad=1; el movimiento
  (acercar/alejar) es solo para fotos.
- Un clip o audio cuyo archivo no estaba al abrir (movido, borrado, USB quitado) lleva «falta»: True (si no, no lleva
  la clave): el render pone el fondo y silencio en su sitio y reenlazar() lo arregla.
- Se RECORTA sin error la transición que pase de la mitad del clip más corto de los dos (si quedaría por debajo de
  0.2 s, pasa a «ninguna»); la del último clip siempre es «ninguna». Así recortar o mover nunca deja un proyecto roto.
- Ids únicos entre clips, capas y audios (borrar busca en los tres): los repetidos o raros se cambian por uno nuevo.
- La duración total es lo que acaba más tarde de las tres pistas (como CapCut: donde no hay clip se ve `fondo`).
"""
import json
import math
import re
import time
import unicodedata
import uuid
from pathlib import Path

from . import diseno, seguro, video
from .idioma import t

CARPETA = Path(__file__).resolve().parent.parent / "datos" / "ediciones"
FILTROS = {"ninguno": t("Ninguno"), "byn": t("Blanco y negro"), "sepia": t("Sepia"), "calido": t("Cálido"),
           "frio": t("Frío"), "vintage": t("Vintage"), "vivo": t("Vivo"), "vineta": t("Viñeta"),
           "desenfoque": t("Desenfoque"), "cine": t("Cine"), "caribe": t("Caribe"), "noir": t("Noir"),
           "dorado": t("Hora dorada"), "neon": t("Neón"), "pastel": t("Pastel"), "retro": t("Retro 70"),
           "nocturno": t("Noche azul")}
TRANSICIONES = {"ninguna": t("Ninguna"), "fundido": t("Fundido"), "disolver": t("Disolver"),
                "deslizar_izq": t("Deslizar a la izquierda"), "deslizar_der": t("Deslizar a la derecha"),
                "deslizar_arriba": t("Deslizar hacia arriba"), "barrido": t("Barrido"), "circulo": t("Círculo"),
                "zoom": t("Zoom"), "pixelado": t("Pixelado"), "desvanecer_negro": t("Desvanecer a negro"),
                "desvanecer_blanco": t("Desvanecer a blanco"), "radial": t("Radial"),
                "abrir_vertical": t("Abrir en vertical"), "deslizar_abajo": t("Deslizar hacia abajo"),
                "difuminar": t("Difuminar"), "cortes": t("Cortes"), "aplastar": t("Aplastar")}
# Los de «al ritmo» siguen los golpes de la primera pista de música (sin música, 120 BPM); ver render_edicion._efecto
EFECTOS = {"ninguno": t("Ninguno"), "zoom_ritmo": t("Zoom al ritmo"), "flash_ritmo": t("Destello al ritmo"),
           "rayos": t("Rayos de energía"), "pulso": t("Latido"), "temblor": t("Temblor de cámara"),
           "glitch": t("Glitch"), "vhs": t("VHS"), "espejo": t("Espejo"),
           "desenfoque_entrada": t("Entrada desenfocada"), "brillo_rafaga": t("Brillo Ráfaga")}
ESTILOS_SUBTITULOS = {"clasico": t("Clásico (amarillo)"), "caja": t("Caja negra"), "neon": t("Neón"),
                      "karaoke": t("Karaoke Ráfaga"), "minimal": t("Minimal"),
                      "impacto": t("Impacto (grande al centro)")}
# Lo que pone cada plantilla (ver aplicar_plantilla). La interfaz usa «nombre» y «descripcion»
PLANTILLAS = {
    "short_viral": {"nombre": t("Short viral"), "descripcion": t("Colores vivos, zoom al ritmo y subtítulos grandes."),
                    "filtro": "vivo", "efecto": "zoom_ritmo", "intensidad": 70, "transicion": "zoom",
                    "duracion_transicion": 0.3, "color": "#FFE14D", "estilo": "impacto"},
    "anuncio": {"nombre": t("Anuncio"), "descripcion": t("Brillo Ráfaga, título y cierre con llamada a la acción."),
                "filtro": "caribe", "efecto": "brillo_rafaga", "intensidad": 60, "transicion": "deslizar_izq",
                "duracion_transicion": 0.4, "color": "#FFFFFF", "estilo": "caja"},
    "video_musical": {"nombre": t("Video musical"), "descripcion": t("Neón, destellos al ritmo y letra en karaoke."),
                      "filtro": "neon", "efecto": "flash_ritmo", "intensidad": 70, "transicion": "desvanecer_blanco",
                      "duracion_transicion": 0.3, "color": "#FF4D8D", "estilo": "karaoke"},
    "cinematico": {"nombre": t("Cinemático"), "descripcion": t("Tonos de cine, entradas suaves y fundidos a negro."),
                   "filtro": "cine", "efecto": "desenfoque_entrada", "intensidad": 50,
                   "transicion": "desvanecer_negro", "duracion_transicion": 0.8, "color": "#F5F0E6",
                   "estilo": "minimal"},
    "vlog": {"nombre": t("Vlog"), "descripcion": t("Luz de hora dorada, un latido suave y transiciones limpias."),
             "filtro": "dorado", "efecto": "pulso", "intensidad": 35, "transicion": "disolver",
             "duracion_transicion": 0.5, "color": "#FFD089", "estilo": "clasico"},
}
ENTRADAS = {"ninguna": t("Ninguna"), "fundido": t("Fundido"), "deslizar": t("Deslizar"), "aparecer": t("Aparecer")}
SALIDAS = {"ninguna": t("Ninguna"), "fundido": t("Fundido")}
MOVIMIENTOS = {"ninguno": t("Ninguno"), "acercar": t("Acercar"), "alejar": t("Alejar")}
TIPOS_AUDIO = {"musica": t("Música"), "voz": t("Voz"), "efecto": t("Efecto")}
FPS = (24, 25, 30, 60)
MAX_CLIPS, MAX_CAPAS, MAX_AUDIOS, MAX_PALABRAS = 300, 100, 50, 20_000  # 60 min hablando rápido: ~12 000 palabras
MAX_DURACION, MIN_CLIP, IMAGEN = 3600, 0.1, 3  # segundos: total, lo mínimo de un clip, lo que dura una foto nueva
_T = 86_400  # «desde»/«hasta» dentro de un archivo: hasta 24 h (se puede usar un trozo de una grabación larga)
_MAX_JSON = 8 * 1024 ** 2
_TIPOS = {"video": seguro.VIDEOS, "imagen": seguro.IMAGENES}
_TIPOS_CAPA = ("texto", "icono", "emoji", "imagen")


# ---------- Validación ----------

def _num(minimo, maximo, decimales=3):
    def regla(v):
        # NaN e infinito no pasan la comparación; True es un int para Python, pero aquí no es un número
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not minimo <= v <= maximo:
            raise ValueError(t("tiene que ser un número entre {minimo} y {maximo} (llegó {v!r:.40})", minimo=minimo,
                               maximo=maximo, v=v))
        v = round(float(v), decimales)
        return int(v) if v.is_integer() else v
    return regla


def _fps(v):
    if isinstance(v, bool) or v not in FPS:
        raise ValueError(t("vale 24, 25, 30 o 60 (llegó {v!r:.40})", v=v))
    return int(v)


def _ruta(tipos):
    def regla(v):
        # Sin «:» de más (un «a.mp4:x» abriría un flujo oculto de otro archivo), comodines ni caracteres de control
        if (not isinstance(v, str) or not re.fullmatch(r'[A-Za-z]:[\\/][^:*?"<>|\x00-\x1f]{1,1000}', v)
                or ".." in re.split(r"[\\/]", v) or Path(v).suffix.lower() not in tipos
                or Path(v).name.split(".")[0].lower() in diseno._RESERVADOS):
            raise ValueError(t("tiene que ser la ruta completa de un archivo de este PC (C:\\…) de tipo {tipos} "
                               "(llegó {v!r:.80})", tipos=", ".join(sorted(tipos)), v=v))
        return v
    return regla


def _id(v, ids: set) -> str:
    if not isinstance(v, str) or not diseno._ID.fullmatch(v) or v in ids:
        v = uuid.uuid4().hex[:8]  # la interfaz encuentra cada elemento por su id: tiene que ser único
    ids.add(v)
    return v


_CLIP = {"desde": 0, "velocidad": 1, "volumen": 1, "silencio": False, "filtro": "ninguno", "brillo": 0,
         "contraste": 0, "saturacion": 0, "movimiento": "ninguno", "transicion": "ninguna",
         "duracion_transicion": 0.5, "temperatura": 0, "vineta": 0, "nitidez": 0, "efecto": "ninguno",
         "intensidad": 60}
_REGLAS_CLIP = {"desde": _num(0, _T), "hasta": _num(0, _T), "velocidad": _num(0.25, 4, 2),
                "volumen": _num(0, 2, 2), "silencio": diseno._si_no, "filtro": diseno._una(*FILTROS),
                "brillo": _num(-100, 100, 0), "contraste": _num(-100, 100, 0), "saturacion": _num(-100, 100, 0),
                "movimiento": diseno._una(*MOVIMIENTOS), "transicion": diseno._una(*TRANSICIONES),
                "duracion_transicion": _num(0.2, 2), "temperatura": _num(-100, 100, 0), "vineta": _num(0, 100, 0),
                "nitidez": _num(0, 100, 0), "efecto": diseno._una(*EFECTOS), "intensidad": _num(0, 100, 0)}
_CAPA = {"inicio": 0, "duracion": 3, "entrada": "ninguna", "salida": "ninguna"}
_REGLAS_CAPA = {"inicio": _num(0, MAX_DURACION), "duracion": _num(MIN_CLIP, MAX_DURACION),
                "entrada": diseno._una(*ENTRADAS), "salida": diseno._una(*SALIDAS)}
_AUDIO = {"tipo": "musica", "inicio": 0, "desde": 0, "volumen": 1, "entrada": 0, "salida": 0}
_REGLAS_AUDIO = {"tipo": diseno._una(*TIPOS_AUDIO), "archivo": _ruta(seguro.AUDIOS), "inicio": _num(0, MAX_DURACION),
                 "desde": _num(0, _T), "hasta": _num(0, _T), "volumen": _num(0, 2, 2), "entrada": _num(0, 10, 2),
                 "salida": _num(0, 10, 2)}
_PALABRA, _SEGUNDO = diseno._texto(100), _num(0, MAX_DURACION)


def _campos(e: dict, reglas: dict, defectos: dict, que: str) -> dict:
    return {k: diseno._campo(regla, e.get(k, defectos.get(k)), f"{que}, «{k}»") for k, regla in reglas.items()}


def _tramo(r: dict, e: dict, que: str) -> dict:
    """El tramo del archivo: con un mínimo en la línea de tiempo y sin pasar del final del archivo. Y la marca «falta»."""
    if diseno._campo(diseno._si_no, e.get("falta", False), f"{que}, «falta»"):
        r["falta"] = True
    if (r["hasta"] - r["desde"]) / r.get("velocidad", 1) < MIN_CLIP:
        raise ValueError(t("{que}: dura demasiado poco (mínimo {minimo} s) o «hasta» no va después de «desde».",
                           que=que, minimo=MIN_CLIP))
    if r["tipo"] != "imagen":
        r["duracion_archivo"] = diseno._campo(_num(0, _T), e.get("duracion_archivo", r["hasta"]),
                                              f"{que}, «duracion_archivo»")
        if r["hasta"] > r["duracion_archivo"] + 0.001:
            raise ValueError(t("{que}: el tramo pasa del final del archivo ({duracion} s).", que=que,
                               duracion=r["duracion_archivo"]))
    return r


def _clip(c, n: int, ids: set) -> dict:
    que = t("Clip {n}", n=n)
    if not isinstance(c, dict):
        raise ValueError(t("{que}: no es válido.", que=que))
    tipo = diseno._campo(diseno._una(*_TIPOS), c.get("tipo"), f"{que}, «tipo»")
    r = {"id": _id(c.get("id"), ids), "tipo": tipo,
         "archivo": diseno._campo(_ruta(_TIPOS[tipo]), c.get("archivo"), f"{que}, «archivo»"),
         **_campos(c, _REGLAS_CLIP, _CLIP, que)}
    if tipo == "imagen":
        r.update(desde=0, velocidad=1)  # una foto no tiene tramo ni velocidad: dura lo que diga «hasta»
    else:
        r["movimiento"] = "ninguno"
    return _tramo(r, c, que)


def _capa(c, n: int, ids: set, ancho: int, alto: int) -> dict:
    tipo = c.get("tipo") if isinstance(c, dict) else None
    if tipo not in _TIPOS_CAPA:
        raise ValueError(t("Capa {n}: tipo de capa desconocido ({tipo!r:.40}); valen {tipos}.", n=n, tipo=tipo,
                           tipos=", ".join(_TIPOS_CAPA)))
    base = diseno.ajustar_capa(diseno._capa(c, n, ids), {"ancho": ancho, "alto": alto})
    return {**base, **_campos(c, _REGLAS_CAPA, _CAPA, t("Capa {n} ({tipo})", n=n, tipo=tipo))}


def _audio(a, n: int, ids: set) -> dict:
    que = t("Audio {n}", n=n)
    if not isinstance(a, dict):
        raise ValueError(t("{que}: no es válido.", que=que))
    return _tramo({"id": _id(a.get("id"), ids), **_campos(a, _REGLAS_AUDIO, _AUDIO, que)}, a, que)


def _palabra(w) -> dict:
    if not isinstance(w, dict):
        raise ValueError(t("no es válida"))
    r = {"palabra": _PALABRA(w.get("palabra")), "inicio": _SEGUNDO(w.get("inicio")), "fin": _SEGUNDO(w.get("fin"))}
    if r["fin"] < r["inicio"]:
        raise ValueError(t("termina antes de empezar"))
    return r


def _subtitulos(s) -> dict:
    if not isinstance(s, dict) or not isinstance(s.get("palabras", []), list):
        raise ValueError(t("Los subtítulos no son válidos."))
    if len(s.get("palabras", [])) > MAX_PALABRAS:
        raise ValueError(t("Los subtítulos pueden tener hasta {n} palabras.", n=MAX_PALABRAS))
    palabras = []
    for n, w in enumerate(s.get("palabras", []), 1):
        try:
            palabras.append(_palabra(w))
        except ValueError as e:
            raise ValueError(t("Subtítulos, palabra {n}: {error}.", n=n, error=e)) from None
    return {"activos": diseno._campo(diseno._si_no, s.get("activos", False), t("Subtítulos, «activos»")),
            "estilo": diseno._campo(diseno._una(*ESTILOS_SUBTITULOS), s.get("estilo", "clasico"),
                                    t("Subtítulos, «estilo»")),
            "palabras": palabras}


def _transiciones(clips: list[dict]) -> None:
    for a, b in zip(clips, clips[1:]):
        if a["transicion"] != "ninguna":
            mitad = math.floor(min(duracion_clip(a), duracion_clip(b)) * 500) / 1000  # la mitad, al ms por abajo
            if mitad < 0.2:
                a["transicion"] = "ninguna"
            else:
                a["duracion_transicion"] = min(a["duracion_transicion"], mitad)
    if clips:
        clips[-1]["transicion"] = "ninguna"  # no hay clip siguiente al que pasar


def validar(proyecto: dict) -> dict:
    """Copia limpia y segura del proyecto: lo que falta toma su valor por defecto, lo que sobra se quita y lo que no
    vale da ValueError diciendo qué y dónde. Aplica las reglas del docstring del módulo."""
    if not isinstance(proyecto, dict):
        raise ValueError(t("El proyecto no es válido: tiene que ser un objeto JSON."))
    if proyecto.get("version", 1) != 1:
        raise ValueError(t("El proyecto es de una versión que no conozco ({version!r:.20}).",
                           version=proyecto.get("version")))
    for clave, tope in (("clips", MAX_CLIPS), ("capas", MAX_CAPAS), ("audios", MAX_AUDIOS)):
        lista = proyecto.get(clave, [])  # se cuenta ANTES de recorrer: 100 000 clips no cuelgan nada
        if not isinstance(lista, list) or len(lista) > tope:
            raise ValueError(t("El proyecto tiene que traer una lista de hasta {tope} {clave}.", tope=tope,
                               clave=clave))
    formato = diseno._campo(diseno._una(*video.FORMATOS), proyecto.get("formato", "9:16"), t("El formato"))
    ancho, alto = video.FORMATOS[formato]
    ids = set()
    p = {"version": 1,
         "nombre": diseno._campo(diseno._texto(120), proyecto.get("nombre", t("Mi video")), t("El nombre")),
         "formato": formato, "fps": diseno._campo(_fps, proyecto.get("fps", 30), t("Los fps")),
         "ajuste": diseno._campo(diseno._una("recortar", "difuminar"), proyecto.get("ajuste", "recortar"),
                                 t("El ajuste")),
         "fondo": diseno._campo(diseno.color, proyecto.get("fondo", "#000000"), t("El fondo")),
         "clips": [_clip(c, n, ids) for n, c in enumerate(proyecto.get("clips", []), 1)],
         "capas": [_capa(c, n, ids, ancho, alto) for n, c in enumerate(proyecto.get("capas", []), 1)],
         "audios": [_audio(a, n, ids) for n, a in enumerate(proyecto.get("audios", []), 1)],
         "subtitulos": _subtitulos(proyecto.get("subtitulos", {}))}
    _transiciones(p["clips"])
    capas = p["capas"]  # los mismos topes que un diseño (ver motor/diseno): la vista previa las pinta a la vez
    if sum(c["tipo"] == "imagen" for c in capas) > diseno.MAX_IMAGENES:
        raise ValueError(t("Un video puede tener hasta {n} capas de imagen.", n=diseno.MAX_IMAGENES))
    if sum(len(c["texto"]) for c in capas
           if c["tipo"] == "texto" and c["contorno"] and c["grosor_contorno"]) > diseno.MAX_LETRAS_CONTORNO:
        raise ValueError(t("Los textos con contorno pueden sumar hasta {n} letras: quita el contorno de alguno o "
                           "acórtalos.", n=diseno.MAX_LETRAS_CONTORNO))
    if sum(map(diseno._pixeles_emoji, capas)) > diseno.MAX_PIXELES_EMOJI:
        raise ValueError(t("Demasiados emojis grandes en el video: hazlos más pequeños o quita alguno."))
    if sum(c["tipo"] == "texto" and c["sombra"] for c in capas) > diseno.MAX_SOMBRAS:
        raise ValueError(t("Un video puede tener hasta {n} textos con sombra: quítasela a alguno.",
                           n=diseno.MAX_SOMBRAS))
    if duracion_total(p) > MAX_DURACION:
        raise ValueError(t("El video pasaría de {minutos} minutos: acorta o quita algún clip, capa o audio.",
                           minutos=MAX_DURACION // 60))
    return p


def nuevo(nombre: str = t("Mi video"), formato: str = "9:16") -> dict:
    return validar({"nombre": nombre, "formato": formato})


# ---------- Tiempos ----------

def duracion_clip(clip: dict) -> float:
    """Lo que dura el clip en la línea de tiempo."""
    return (clip["hasta"] - clip["desde"]) / clip["velocidad"]


def tiempos(proyecto: dict) -> list[tuple[float, float]]:
    """(inicio, fin) de cada clip en la línea de tiempo. Con transición, el siguiente empieza antes de que acabe."""
    salida, inicio = [], 0.0
    for c in proyecto["clips"]:
        fin = inicio + duracion_clip(c)
        salida.append((round(inicio, 6), round(fin, 6)))
        inicio = fin - (c["duracion_transicion"] if c["transicion"] != "ninguna" else 0)
    return salida


def duracion_total(proyecto: dict) -> float:
    fines = [fin for _, fin in tiempos(proyecto)[-1:]]
    fines += [c["inicio"] + c["duracion"] for c in proyecto["capas"]]
    fines += [a["inicio"] + a["hasta"] - a["desde"] for a in proyecto["audios"]]
    return round(max(fines, default=0.0), 6)


def clip_en(proyecto: dict, t: float) -> tuple[int, float] | None:
    """Índice del clip que se ve en t y el segundo DENTRO de su archivo. En una transición, el clip que entra.
    Fuera de la pista (también justo en su final) devuelve None."""
    for i, (inicio, fin) in reversed(list(enumerate(tiempos(proyecto)))):
        if inicio <= t < fin:
            c = proyecto["clips"][i]
            return i, round(c["desde"] + (t - inicio) * c["velocidad"], 6)
    return None


def capas_en(proyecto: dict, t: float) -> list[dict]:
    """Copias de las capas visibles en t, en orden de pintado."""
    return [dict(c) for c in proyecto["capas"] if c["inicio"] <= t < c["inicio"] + c["duracion"]]


# ---------- Operaciones (todas devuelven un proyecto nuevo validado) ----------

def _buscar(p: dict, id_elemento: str, claves=("clips", "capas", "audios")) -> dict:
    for clave in claves:
        for e in p[clave]:
            if e["id"] == id_elemento:
                return e
    raise ValueError(t("No encuentro ese elemento en el proyecto."))


def _abajo(segundos: float) -> float:
    return math.floor(segundos * 1000) / 1000  # al ms por abajo: nunca pasa del archivo ni de los 60 minutos


def _medir(real: str) -> tuple[float, bool]:
    """(lo que dura, hasta 24 h; si trae imagen), con ffmpeg."""
    try:
        largo, imagen = video.medir(Path(real))
    except RuntimeError as e:
        raise ValueError(str(e)) from None
    return min(largo, _T), imagen


def anadir_medio(proyecto: dict, ruta: str, audio: bool = False) -> dict:
    """Video o foto: un clip al final de la pista principal (si no cabe entero en los 60 minutos, recortado). Audio:
    una pista de música desde el segundo 0; también un .mp4/.webm sin imagen (una canción bajada de YouTube) y, con
    audio=True («Importar música»), cualquier audio aunque traiga imagen. El elemento creado es el último de
    p["clips"] o de p["audios"]."""
    p = validar(proyecto)
    sufijo = Path(str(ruta or "")).suffix.lower()
    # La familia la decide la extensión (un .mp4 es un video aunque también valga como audio); sin extensión conocida,
    # archivo_medio dice cuáles valen
    tipos = seguro.AUDIOS if audio else next(
        (t for t in (seguro.IMAGENES, seguro.VIDEOS, seguro.AUDIOS) if sufijo in t),
        seguro.IMAGENES | seguro.VIDEOS | seguro.AUDIOS)
    real = str(seguro.archivo_medio(ruta, tipos, t("archivo")))
    if tipos is not seguro.IMAGENES:
        largo, imagen = _medir(real)
        if tipos is seguro.VIDEOS and not imagen:  # sin pista de imagen, el render no podría montar el clip
            if sufijo not in seguro.AUDIOS:
                raise ValueError(t("{nombre} no tiene imagen, solo sonido: para usarlo como audio, guárdalo como "
                                   ".mp3, .m4a o .wav.", nombre=Path(real).name))
            tipos = seguro.AUDIOS
    hueco = MAX_DURACION - (tiempos(p)[-1][1] if p["clips"] else 0)
    if tipos is not seguro.AUDIOS and hueco < MIN_CLIP:
        raise ValueError(t("El video ya llega a {minutos} minutos: no cabe nada más.", minutos=MAX_DURACION // 60))
    if tipos is seguro.IMAGENES:
        p["clips"].append({"tipo": "imagen", "archivo": real, "hasta": _abajo(min(IMAGEN, hueco))})
    elif tipos is seguro.VIDEOS:
        p["clips"].append({"tipo": "video", "archivo": real, "hasta": _abajo(min(largo, hueco)),
                           "duracion_archivo": largo})
    else:
        p["audios"].append({"tipo": "musica", "archivo": real, "hasta": _abajo(min(largo, MAX_DURACION)),
                            "duracion_archivo": largo})
    return validar(p)


def _vale(ruta: str, tipos: set) -> bool:
    try:
        return bool(seguro.archivo_medio(ruta, tipos))
    except ValueError:
        return False


def reenlazar(proyecto: dict, id_elemento: str, ruta: str) -> dict:
    """«Volver a enlazar»: el clip o audio `id_elemento` y los demás que usaban su archivo (los trozos de un clip
    dividido; ese video usado también como pista de audio, o al revés, si el nuevo les vale) pasan a usar `ruta` y
    pierden «falta». Tiene que ser lo mismo (un video con imagen, una foto o un audio) y durar al menos lo que se usa."""
    p = validar(proyecto)
    e = _buscar(p, id_elemento, ("clips", "audios"))
    tipos = _TIPOS.get(e["tipo"], seguro.AUDIOS)  # los audios llevan «musica», «voz» o «efecto»
    real = str(seguro.archivo_medio(ruta, tipos, t("archivo")))
    nuevo = {"archivo": real}
    if tipos is not seguro.IMAGENES:
        nuevo["duracion_archivo"], imagen = _medir(real)
        if tipos is seguro.VIDEOS and not imagen:
            raise ValueError(t("{nombre} no tiene imagen, solo sonido: elige el video de este clip.",
                               nombre=Path(real).name))
    viejo = e["archivo"]
    for x in p["clips"] + p["audios"]:
        suyos = _TIPOS.get(x["tipo"], seguro.AUDIOS)
        # el de otro tipo, solo si el nuevo le vale: un .mov no es audio y un audio de más de 2 GB no abriría
        if x["archivo"] == viejo and (suyos is tipos or _vale(real, suyos) and (x["tipo"] != "video" or imagen)):
            x.pop("falta", None)
            x.update(nuevo)
    return validar(p)


def dividir(proyecto: dict, momento: float) -> dict:
    """Parte el clip que se ve en `momento` (en una transición, el que entra) en dos, con ids nuevos. El primero se
    queda sin transición; el segundo, con la que tenía el clip."""
    p = validar(proyecto)
    momento = diseno._campo(_num(0, MAX_DURACION), momento, t("El punto de corte"))
    hallado = clip_en(p, momento)
    if hallado is None:
        raise ValueError(t("No hay ningún clip en ese punto de la línea de tiempo."))
    i, corte = hallado
    a = p["clips"][i]
    corte = round(corte, 3)
    b = dict(a, desde=corte)
    if a["tipo"] == "imagen":  # las fotos siempre empiezan en 0: el segundo trozo dura lo que sobra
        b.update(desde=0, hasta=round(a["hasta"] - corte, 3))
    a.update(hasta=corte, transicion="ninguna")
    if min(duracion_clip(a), duracion_clip(b)) < MIN_CLIP:
        raise ValueError(t("Ese punto está demasiado cerca del borde del clip: mueve el cursor un poco."))
    a["id"] = b["id"] = None  # validar les da ids nuevos
    p["clips"].insert(i + 1, b)
    return validar(p)


def recortar(proyecto: dict, id_clip: str, desde: float, hasta: float) -> dict:
    """Nuevo tramo (segundos dentro del archivo) de un clip o de un audio, ajustado al principio y al final del archivo.
    En una foto, hasta - desde es lo que dura. Un audio sigue sonando en el mismo sitio de la línea de tiempo."""
    p = validar(proyecto)
    desde = max(0.0, diseno._campo(_num(-_T, _T), desde, t("El inicio del recorte")))
    hasta = diseno._campo(_num(-_T, _T), hasta, t("El final del recorte"))
    e = _buscar(p, id_clip, ("clips", "audios"))
    if e["tipo"] == "imagen":
        e["hasta"] = hasta - desde
    else:
        if "inicio" in e:  # audio: quitar sonido del principio no lo mueve en la línea de tiempo
            e["inicio"] = max(0.0, e["inicio"] + desde - e["desde"])
        e.update(desde=desde, hasta=min(hasta, e["duracion_archivo"]))
    return validar(p)


def mover_clip(proyecto: dict, id_clip: str, posicion: int) -> dict:
    """Lleva el clip a esa posición de la pista principal (0 = el primero; fuera de rango, al extremo)."""
    p = validar(proyecto)
    if isinstance(posicion, bool) or not isinstance(posicion, int):
        raise ValueError(t("La posición tiene que ser un número entero."))
    clip = _buscar(p, id_clip, ("clips",))
    p["clips"].remove(clip)
    p["clips"].insert(max(0, min(posicion, len(p["clips"]))), clip)
    return validar(p)


def borrar(proyecto: dict, id_elemento: str) -> dict:
    """Quita el clip, la capa o el audio con ese id (la imagen de una capa se queda en imagenes/: deshacer la usa)."""
    p = validar(proyecto)
    e = _buscar(p, id_elemento)
    for clave in ("clips", "capas", "audios"):
        p[clave] = [x for x in p[clave] if x is not e]
    return validar(p)


def aplicar_plantilla(proyecto: dict, clave: str) -> dict:
    """Aplica la plantilla `clave` de PLANTILLAS: filtro, efecto y transición en todos los clips, el estilo de los
    subtítulos (y los activa) y sus textos: un título al empezar y, en «anuncio», un cierre con llamada a la acción al
    final. Sus capas llevan un id «plantilla-…»: al aplicar otra se quitan antes. Los medios del usuario no se tocan."""
    p = validar(proyecto)
    if not isinstance(clave, str) or clave not in PLANTILLAS:
        raise ValueError(t("Esa plantilla no existe ({clave!r:.40}).", clave=clave))
    if not p["clips"]:
        raise ValueError(t("Añade al menos un clip (video o foto) antes de aplicar una plantilla."))
    plantilla = PLANTILLAS[clave]
    for c in p["clips"]:
        c.update({k: plantilla[k] for k in ("filtro", "efecto", "intensidad", "transicion", "duracion_transicion")})
    p["subtitulos"].update(estilo=plantilla["estilo"], activos=True)
    p["capas"] = [c for c in p["capas"] if not c["id"].startswith("plantilla-")]
    p = validar(p)  # con las transiciones ya recortadas: así se sabe dónde acaban los clips
    fin = math.floor(tiempos(p)[-1][1] * 1000) / 1000  # al ms por abajo: sus textos (redondeados) nunca alargan el video
    ancho, alto = video.FORMATOS[p["formato"]]
    tam = round(min(ancho, alto) * 0.09)

    def texto(id_capa, letras, y, inicio, duracion, color):
        return {"id": id_capa, "tipo": "texto", "texto": letras, "x": round(ancho * 0.06), "y": round(y),
                "ancho": round(ancho * 0.88), "alto": tam * 3, "tamano": tam, "color": color, "negrita": True,
                "alineacion": "centro", "contorno": "#000000", "grosor_contorno": max(2, tam // 12),
                "inicio": round(inicio, 3), "duracion": round(duracion, 3), "entrada": "aparecer", "salida": "fundido"}
    p["capas"].append(texto("plantilla-titulo", p["nombre"].strip() or t("Tu título"), alto * 0.1, 0, min(2.5, fin),
                            plantilla["color"]))
    if clave == "anuncio":
        cierre = min(3, fin)
        p["capas"].append(texto("plantilla-cierre", t("¡Pídelo ya! Enlace en la bio"), alto * 0.42, fin - cierre,
                                cierre, "#FFFFFF"))
    return validar(p)


# ---------- Carpetas y archivos ----------

def nueva_carpeta(nombre: str) -> Path:
    """datos/ediciones/<fecha>-<nombre>/ con imagenes/ (capas de imagen) y cache/ (lo que hace el render)."""
    limpio = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode().lower()
    limpio = re.sub(r"[^a-z0-9]+", "-", limpio).strip("-")[:40] or "video"
    base = CARPETA / f"{time.strftime('%Y%m%d-%H%M%S')}-{limpio}"
    CARPETA.mkdir(parents=True, exist_ok=True)
    carpeta, n = base, 1
    while True:
        try:
            carpeta.mkdir()  # atómico: si otro hilo (el MCP en paralelo) la creó a la vez, se prueba otro nombre
            break
        except FileExistsError:
            n += 1
            carpeta = base.with_name(f"{base.name}-{n}")
    (carpeta / "imagenes").mkdir()
    (carpeta / "cache").mkdir()
    return carpeta


def guardar(proyecto: dict, carpeta: Path) -> Path:
    """Valida y escribe proyecto.json (atómico). La miniatura de la lista (miniatura.png) la pone la interfaz."""
    limpio, carpeta = validar(proyecto), diseno._local(carpeta)
    archivo = carpeta / "proyecto.json"
    diseno.escribir_json(archivo, limpio)
    return archivo


def _leer(carpeta: Path) -> dict:
    archivo = diseno._local(carpeta) / "proyecto.json"
    try:
        if archivo.stat().st_size > _MAX_JSON:
            raise ValueError("demasiado grande")
        datos = json.loads(archivo.read_text(encoding="utf-8-sig"))
    except OSError:
        raise ValueError(t("No encuentro el proyecto en {carpeta}.", carpeta=carpeta)) from None
    except (ValueError, RecursionError):  # JSON roto, que no es UTF-8 o anidado sin fin
        raise ValueError(t("El archivo del proyecto está dañado, es demasiado grande o no es un proyecto de "
                           "video.")) from None
    return validar(datos)


def abrir(carpeta: Path) -> dict:
    """El proyecto validado, con cada archivo de clip y audio comprobado (local y es lo que dice ser). Si ya no está
    (movido, borrado, USB quitado) no falla: lo marca «falta» para volver a enlazarlo (reenlazar)."""
    p = _leer(carpeta)
    for clave, que in (("clips", t("clip")), ("audios", t("audio"))):
        for n, e in enumerate(p[clave], 1):
            e.pop("falta", None)  # se mira cada vez: el USB puede haber vuelto
            tipos = _TIPOS.get(e["tipo"], seguro.AUDIOS)
            try:
                e["archivo"] = str(seguro.archivo_medio(e["archivo"], tipos, f"{que} {n}"))
            except ValueError:
                # ruta ya validada (local, sin red): está, pero no es lo que dice; vacío (copia a medias) cuenta como falta
                if Path(e["archivo"]).is_file() and Path(e["archivo"]).stat().st_size:
                    raise
                e["falta"] = True
    return validar(p)


def listar(maximo: int | None = None) -> list[dict]:
    """Proyectos guardados, del último que se tocó al más viejo: {"nombre", "carpeta", "miniatura" ("" si no hay)}.
    No comprueba los archivos de los clips (eso lo hace abrir): la lista sale rápido aunque falte alguno.
    maximo: solo los más nuevos (se validan solo esos: con decenas de proyectos grandes, validarlos todos tarda)."""
    proyectos = []
    archivos = []
    for archivo in CARPETA.glob("*/proyecto.json"):
        try:
            archivos.append((archivo.stat().st_mtime, archivo))
        except OSError:
            continue
    for fecha, archivo in sorted(archivos, key=lambda a: a[0], reverse=True):
        if maximo is not None and len(proyectos) >= maximo:
            break
        try:
            nombre = _leer(archivo.parent)["nombre"]
        except (OSError, ValueError):
            continue  # uno roto no impide ver los demás
        try:  # Qt la abriría como SVG si lo fuera, y un SVG puede pedir \\servidor\...: solo una imagen de verdad
            miniatura = str(seguro.archivo_medio(str(archivo.with_name("miniatura.png")), {".png"}, "miniatura"))
        except ValueError:
            miniatura = ""
        proyectos.append((fecha, {"nombre": nombre or archivo.parent.name, "carpeta": str(archivo.parent),
                                  "miniatura": miniatura}))
    return [p for _, p in sorted(proyectos, key=lambda t: t[0], reverse=True)]
