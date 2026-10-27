"""Dibujos animados: una serie capítulo por capítulo, con personajes que se mantienen iguales.

Cada serie vive en datos/series/<nombre>/:
- serie.json: título, sinopsis, estilo visual, formato, voz del narrador y personajes (nombre, apariencia fija en
  inglés, personalidad y voz). La lámina de cada personaje está en personajes/<id>.png.
- episodios/<NN>/: guion.json, episodio.json, los planos y el video del capítulo.

Para que los personajes no cambien, cada plano repite su apariencia fija y, si la IA de imágenes sabe editar con
referencia, parte de su lámina. Cada plano se oye con la voz de quien habla. El capítulo queda además como proyecto
del editor de video, para retocarlo a mano, y sus cuadros se pueden sacar para OpenToonz, Pencil2D o Krita."""
import json
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Callable

from . import desde_prompt, diseno, edicion, ia, memoria, seguro, video
from .idioma import IDIOMAS, actual, t, texto_de_error

CARPETA = Path(__file__).resolve().parent.parent / "datos" / "series"
MAX_PERSONAJES, MAX_PLANOS, MAX_EPISODIOS = 6, 40, 200
LAMINA = (832, 1248)  # cuerpo entero, de pie
MUJERES = {"Ramona", "Dalia", "Elvira", "Ava", "Francisca", "Denise"}  # las voces de desde_prompt.VOCES que son de mujer
ESTILOS = {
    t("Anime 90s (estilo samurái)"): "90s anime cel animation style, bold ink lines, dramatic cel shading, cinematic "
                                     "composition, high contrast",
    t("Anime moderno"): "modern anime style, vibrant colors, detailed painted backgrounds, dynamic lighting",
    t("Cartoon 2D"): "2D cartoon style, clean thick outlines, flat bright colors, expressive characters",
    t("Animación 3D (tipo Pixar)"): "3D animated movie style, stylized expressive characters, soft cinematic lighting",
    t("Cine realista"): "cinematic film still, realistic, dramatic lighting, shallow depth of field",
    t("Cómic"): "comic book art style, bold ink outlines, halftone shading, vivid colors",
}
# Programas libres para retocar los cuadros a mano (dónde los deja su instalador en Windows)
PROGRAMAS = {
    "OpenToonz": (r"%ProgramFiles%\OpenToonz\OpenToonz.exe", "opentoonz", "https://opentoonz.github.io/"),
    "Pencil2D": (r"%ProgramFiles%\Pencil2D\pencil2d.exe", "pencil2d", "https://www.pencil2d.org/"),
    "Krita": (r"%ProgramFiles%\Krita (x64)\bin\krita.exe", "krita", "https://krita.org/"),
}

ESQUEMA_SERIE = {"type": "object", "properties": {
    "titulo": {"type": "string"}, "sinopsis": {"type": "string"},
    "personajes": {"type": "array", "items": {"type": "object", "properties": {
        "nombre": {"type": "string"}, "descripcion": {"type": "string"}, "personalidad": {"type": "string"},
        "genero": {"type": "string"}}, "required": ["nombre", "descripcion", "personalidad", "genero"],
        "additionalProperties": False}}},
    "required": ["titulo", "sinopsis", "personajes"], "additionalProperties": False}

ESQUEMA_EPISODIO = {"type": "object", "properties": {
    "titulo": {"type": "string"}, "resumen": {"type": "string"},
    "planos": {"type": "array", "items": {"type": "object", "properties": {
        "descripcion": {"type": "string"}, "personajes": {"type": "array", "items": {"type": "string"}},
        "habla": {"type": "string"}, "texto": {"type": "string"}},
        "required": ["descripcion", "personajes", "habla", "texto"], "additionalProperties": False}}},
    "required": ["titulo", "resumen", "planos"], "additionalProperties": False}

# La misma regla en todas las instrucciones de la app (contrato D del plan)
FALTAS = ia.FALTAS  # la regla común de faltas de ortografía (una sola, en ia.py)
ESTADOS = ("listo", "incompleto", "sin_dibujos")  # de un capítulo, según cuántos planos tienen su dibujo

INSTRUCCIONES_SERIE = """Eres creador de series animadas. Con la idea del usuario crea la biblia de una serie ORIGINAL.
- titulo: corto y con gancho. sinopsis: 3 o 4 frases con el mundo, el conflicto y el tono.
- personajes: los que pide el usuario. Para cada uno:
  - nombre: original y fácil de recordar.
  - descripcion: su apariencia FIJA, en inglés, muy concreta (edad, cuerpo, cara, pelo, ropa, colores, accesorios,
    arma u objeto propio), de 50 a 80 palabras, para dibujarlo siempre igual. Sin nombres de obras ni de autores.
  - personalidad: 1 o 2 frases.
  - genero: hombre, mujer u otro.
- Si la idea se inspira en una obra que existe, toma su tono y su género, nunca sus personajes, nombres ni diseños.
- Título, sinopsis, nombres y personalidades en {idioma}.
""" + FALTAS

INSTRUCCIONES_EPISODIO = """Eres guionista y director de storyboard de una serie animada. Escribe el capítulo {numero}.
Serie: {titulo}
Sinopsis: {sinopsis}
Personajes (usa SOLO estos nombres, escritos igual):
{personajes}
Lo que pasó en los capítulos anteriores:
{antes}

Divide el capítulo en planos, como un storyboard. Cada plano:
- descripcion: lo que se ve, en inglés y muy visual: lugar, acción, tipo de plano y cámara, luz. Nombra a los
  personajes que salen. NO describas la ropa ni el aspecto de los personajes (se añaden solos); estilo de la serie:
  {estilo}. Sin texto escrito en la imagen.
- personajes: los nombres de los que salen en el plano (puede estar vacío).
- habla: el nombre del personaje que habla en ese plano, o "Narrador".
- texto: lo que dice, 1 o 2 frases cortas, en {idioma}.
Empieza con un gancho, mantén la continuidad con lo anterior y termina dejando ganas del siguiente capítulo.
titulo y resumen (2 o 3 frases) en {idioma}.
""" + FALTAS


# ---------- Leer y guardar ----------

def _slug(texto: str) -> str:
    limpio = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", limpio).strip("-")[:40] or "serie"


def _texto(valor, maximo: int) -> str:
    return str(valor if isinstance(valor, (str, int, float)) else "").strip()[:maximo]


def _voz(valor, defecto: str) -> str:
    """Solo voces de la lista: un serie.json tocado a mano no puede meter otra cosa (va dentro de la API de voz)."""
    return valor if valor in desde_prompt.voces().values() else defecto


def _limpia(datos) -> dict:
    """serie.json validado: lo que falta toma su valor por defecto y lo raro se quita (el archivo se puede editar)."""
    if not isinstance(datos, dict):
        raise ValueError(t("El archivo de la serie está dañado."))
    narrador = _voz(datos.get("narrador"), desde_prompt.voz_por_defecto())
    crudos = [p for p in datos.get("personajes") if isinstance(p, dict) and _texto(p.get("nombre"), 60)] \
        if isinstance(datos.get("personajes"), list) else []
    # Cada uno conserva su id (su lámina es personajes/<id>.png): si se reordena la lista a mano, no se cruzan
    usados = {p["id"] for p in crudos if isinstance(p.get("id"), str) and re.fullmatch(r"p\d{1,2}", p["id"])}
    libres = (f"p{n}" for n in range(1, 100) if f"p{n}" not in usados)
    personajes, vistos = [], set()
    for p in crudos[:MAX_PERSONAJES]:
        id_ = p.get("id") if p.get("id") in usados and p.get("id") not in vistos else next(libres)
        vistos.add(id_)
        personajes.append({"id": id_, "nombre": _texto(p.get("nombre"), 60),
                           "descripcion": _texto(p.get("descripcion"), 800),
                           "personalidad": _texto(p.get("personalidad"), 400), "voz": _voz(p.get("voz"), narrador)})
    formato = datos.get("formato")
    return {"titulo": _texto(datos.get("titulo"), 80) or t("Mi serie"), "sinopsis": _texto(datos.get("sinopsis"), 1500),
            "idea": _texto(datos.get("idea"), 2000), "estilo": _texto(datos.get("estilo"), 300) or next(iter(ESTILOS.values())),
            "formato": formato if isinstance(formato, str) and formato in video.FORMATOS else "16:9",
            "narrador": narrador, "personajes": personajes}


def _abrir(serie: str) -> tuple[Path, dict]:
    """(carpeta, datos) de una serie por el nombre de su carpeta o por su título."""
    buscada = str(serie or "").strip()
    for archivo in sorted(CARPETA.glob("*/serie.json")):
        try:
            datos = _limpia(json.loads(archivo.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, AttributeError):  # un archivo tocado a mano
            continue
        if buscada in (archivo.parent.name, datos["titulo"]) or buscada.lower() == datos["titulo"].lower():
            return archivo.parent, datos
    raise ValueError(t("No encuentro la serie «{serie}». Créala primero o elige una de la lista.", serie=buscada[:80]))


def lamina(carpeta: Path, personaje: dict) -> Path:
    return carpeta / "personajes" / f"{personaje['id']}.png"


def _imagen(ep: Path, i: int) -> Path:
    return ep / f"video_final_imagen_{i:02d}.png"  # el nombre que le da desde_prompt.montar


def _leer_guion(ep: Path, numero) -> dict:
    try:
        guion = json.loads((ep / "guion.json").read_text(encoding="utf-8"))
        if not isinstance(guion, dict) or not isinstance(guion.get("planos"), list):
            raise ValueError
    except (OSError, ValueError):
        raise ValueError(t("El guion del capítulo {n} está dañado.", n=numero)) from None
    return guion


def _planos(guion: dict) -> list[dict]:
    """Los planos que se montan (los que son planos de verdad): el índice de cada uno es el de su imagen y su escena."""
    return [p for p in guion["planos"] if isinstance(p, dict)][:MAX_PLANOS]


def _capitulo(episodio: str) -> Path:
    """La carpeta de un capítulo de una serie: nunca otra ruta que llegue de fuera."""
    ep = diseno._local(episodio).resolve()
    if CARPETA.resolve() not in ep.parents or not (ep / "episodio.json").is_file():
        raise ValueError(t("Eso no es un capítulo de una serie."))
    return ep


def _estado(ep: Path, planos: int) -> str:
    """Uno de ESTADOS, contando los dibujos que hay de verdad (también en los capítulos de antes de guardarlo)."""
    dibujos = sum(_imagen(ep, i).is_file() for i in range(planos))
    if not planos:  # guion ilegible: sin planos no hay nada que dé el capítulo por bueno
        return "sin_dibujos"
    return "listo" if dibujos == planos else "incompleto" if dibujos else "sin_dibujos"


def _episodios(carpeta: Path) -> list[dict]:
    lista = []
    for archivo in sorted((carpeta / "episodios").glob("*/episodio.json")):
        try:
            e = json.loads(archivo.read_text(encoding="utf-8"))
            try:
                planos = len(_planos(_leer_guion(archivo.parent, archivo.parent.name)))
            except ValueError:
                planos = 0
            miniatura = min(archivo.parent.glob("video_final_imagen_*.png"), default="")
            lista.append({"numero": int(archivo.parent.name), "titulo": _texto(e.get("titulo"), 120),
                          "resumen": _texto(e.get("resumen"), 1000), "carpeta": str(archivo.parent),
                          "video": str(archivo.parent / "video_final.mp4"), "estado": _estado(archivo.parent, planos),
                          "planos": planos, "miniatura": str(miniatura)})
        except (OSError, ValueError, TypeError, AttributeError):
            continue  # uno roto no impide ver los demás
    return lista


def guion_grafico(episodio: str) -> list[dict]:
    """El guion gráfico de un capítulo: lo que se ve, quién habla, qué dice y su dibujo ("" si no salió)."""
    ep = _capitulo(episodio)
    try:
        lista = _planos(_leer_guion(ep, ep.name))
    except ValueError:
        return []
    return [{"descripcion": _texto(p.get("descripcion"), 1000), "habla": _texto(p.get("habla"), 60),
             "texto": _texto(p.get("texto"), 400), "imagen": str(_imagen(ep, i)) if _imagen(ep, i).is_file() else ""}
            for i, p in enumerate(lista)]


def resumen(carpeta: Path, datos: dict) -> dict:
    return {"tipo": "serie", "nombre": carpeta.name, "carpeta": str(carpeta), "titulo": datos["titulo"],
            "sinopsis": datos["sinopsis"], "formato": datos["formato"],
            "personajes": [{"nombre": p["nombre"], "personalidad": p["personalidad"], "voz": p["voz"],
                            "lamina": str(lamina(carpeta, p)) if lamina(carpeta, p).is_file() else ""}
                           for p in datos["personajes"]],
            "episodios": _episodios(carpeta)}


def listar() -> list[dict]:
    """Las series creadas, de la más nueva a la más vieja."""
    series = []
    for archivo in sorted(CARPETA.glob("*/serie.json"), reverse=True):
        try:
            series.append(resumen(archivo.parent, _limpia(json.loads(archivo.read_text(encoding="utf-8")))))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return series


# ---------- Crear ----------

def _asignar_voces(personajes: list[dict], generos: list[str]) -> None:
    """Una voz distinta para cada uno mientras haya, de mujer o de hombre según el personaje y en el idioma de la app."""
    propias = [v for v in desde_prompt.VOCES.values() if v.startswith(f"{actual()}-")] or list(desde_prompt.VOCES.values())
    usadas = {True: 0, False: 0}
    for p, genero in zip(personajes, generos):
        mujer = genero.strip().lower().startswith(("mujer", "woman", "female", "f"))
        opciones = [v for v in propias if (v.split("-")[2].removesuffix("Neural") in MUJERES) == mujer] or propias
        p["voz"] = opciones[usadas[mujer] % len(opciones)]
        usadas[mujer] += 1


def crear_serie(titulo: str, idea: str, estilo: str = "", personajes: int = 3, formato: str = "16:9",
                aviso: Callable[[str, float], None] = lambda t, f: None, biblia: dict | None = None) -> dict:
    """La biblia de la serie (con la IA de texto) y la lámina de cada personaje (con la IA de imágenes).
    biblia: ya escrita (forma de ESQUEMA_SERIE) por quien maneja el estudio; entonces no se usa la IA de texto."""
    titulo, idea = _texto(titulo, 80), _texto(idea, 2000)
    if biblia is not None:
        biblia = ia.de_fuera(biblia, ESQUEMA_SERIE, t("La biblia de la serie"))
    elif not titulo and not idea:
        raise ValueError(t("Cuéntame de qué trata la serie."))
    if formato not in video.FORMATOS:
        raise ValueError(t("Formato desconocido: {formato!r:.20}.", formato=formato))
    cuantos = max(1, min(int(personajes), MAX_PERSONAJES))
    # el nombre del estilo en cualquier idioma de la app (el MCP lo manda en español)
    estilo = ESTILOS.get(estilo) or ESTILOS.get(t(str(estilo))) or _texto(estilo, 300)
    if biblia is None:
        aviso(t("La IA está creando la serie y sus personajes…"), 0.05)
        # con el estilo, la apariencia que escribe encaja con el dibujo (un gato de caricatura no es uno de cine)
        biblia = ia.texto_json(INSTRUCCIONES_SERIE.replace("{idioma}", IDIOMAS[actual()]),
                               f"Título: {titulo or '(elígelo tú)'}\nIdea: {idea or titulo}\nPersonajes: {cuantos}"
                               + (f"\nEstilo de dibujo: {estilo}" if estilo else "") + memoria.para("dibujos"),
                               ESQUEMA_SERIE)
    else:
        cuantos = MAX_PERSONAJES  # los que escribió el agente, con el tope de siempre
    crudos = [p for p in biblia["personajes"] if _texto(p.get("nombre"), 60)][:cuantos]
    if not crudos:
        raise RuntimeError(t("La IA no inventó ningún personaje. Inténtalo de nuevo."))
    datos = _limpia({"titulo": titulo or biblia["titulo"], "sinopsis": biblia["sinopsis"], "idea": idea,
                     "estilo": estilo, "formato": formato, "personajes": crudos})
    _asignar_voces(datos["personajes"], [str(p.get("genero", "")) for p in crudos])
    CARPETA.mkdir(parents=True, exist_ok=True)
    base = CARPETA / f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(datos['titulo'])}"
    carpeta, n = base, 1
    while carpeta.exists():
        n += 1
        carpeta = base.with_name(f"{base.name}-{n}")
    (carpeta / "personajes").mkdir(parents=True)
    diseno.escribir_json(carpeta / "serie.json", datos)
    avisos, faltan = [], []
    for i, p in enumerate(datos["personajes"]):
        aviso(t("Dibujando a {nombre}…", nombre=p["nombre"]), 0.2 + 0.75 * i / len(datos["personajes"]))
        try:
            ia.imagen(_prompt_lamina(p, datos["estilo"]), *LAMINA, lamina(carpeta, p))
        except Exception as e:  # sin cuota hoy: la serie queda creada y la lámina se dibuja o se elige después
            faltan.append(p["nombre"])
            avisos.append(t("No salió la lámina de {nombre} ({causa}).", nombre=p["nombre"],
                            causa=texto_de_error(e).replace("\n", " · ")[:300]))
    aviso(t("¡Listo!"), 1.0)
    return {**resumen(carpeta, datos), "avisos": avisos, "faltan_laminas": faltan, "resultados": []}


def _prompt_lamina(p: dict, estilo: str) -> str:
    return (f"character reference sheet of {p['nombre']}: {p['descripcion']}. Full body, front view, standing, "
            f"neutral pose, plain light grey background, single character only, centered, no text, no letters, {estilo}")


def _personaje(datos: dict, personaje: str) -> dict:
    p = next((x for x in datos["personajes"] if personaje in (x["id"], x["nombre"])), None)
    if p is None:
        raise ValueError(t("Esa serie no tiene el personaje «{nombre}».", nombre=str(personaje)[:60]))
    return p


def dibujar_lamina(serie: str, personaje: str, aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """Dibuja con la IA la lámina de un personaje (la que no salió al crear la serie, o una nueva versión)."""
    carpeta, datos = _abrir(serie)
    p = _personaje(datos, personaje)
    aviso(t("Dibujando a {nombre}…", nombre=p["nombre"]), 0.1)
    lamina(carpeta, p).parent.mkdir(exist_ok=True)
    ia.imagen(_prompt_lamina(p, datos["estilo"]), *LAMINA, lamina(carpeta, p))
    aviso(t("¡Listo!"), 1.0)
    return {**resumen(carpeta, datos), "resultados": []}


def cambiar_lamina(serie: str, personaje: str, archivo: str) -> str:
    """La lámina de un personaje desde tu imagen o un fotograma de tu video (p. ej. de un capítulo que ya tenías)."""
    carpeta, datos = _abrir(serie)
    p = _personaje(datos, personaje)
    real = seguro.archivo_medio(archivo, seguro.IMAGENES | seguro.VIDEOS, t("imagen del personaje"))
    momento = video.duracion(real) / 3 if real.suffix.lower() in seguro.VIDEOS - seguro.IMAGENES else 0
    destino = lamina(carpeta, p)
    destino.parent.mkdir(exist_ok=True)
    video.ffmpeg("-ss", f"{momento:.2f}", "-i", real, "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", destino)
    return str(destino)


def _escenas(datos: dict, guion: dict) -> list[dict]:
    """Cada plano como escena de desde_prompt.montar: su voz y su dibujo, con la apariencia fija de quien sale."""
    nombres = {p["nombre"].lower(): p for p in datos["personajes"]}
    # Las imágenes salen cuadradas y se recortan a 16:9: que nadie quede con la cabeza o los pies fuera
    encuadre = ", characters fully inside the central band, no text" if datos["formato"] == "16:9" else ", no text"
    escenas = []
    for plano in _planos(guion):
        salen = [nombres[n.lower()] for n in plano.get("personajes", []) if isinstance(n, str) and n.lower() in nombres]
        habla = nombres.get(str(plano.get("habla", "")).lower())
        fijas = "; ".join(f"{p['nombre']}: {p['descripcion']}" for p in salen)
        escenas.append({"narracion": _texto(plano.get("texto"), 400) or "…",
                        "imagen": _texto(plano.get("descripcion"), 1000) + (f". Characters: {fijas}" if fijas else "")
                        + encuadre, "voz": habla["voz"] if habla else datos["narrador"],
                        "ref": salen[0] if salen else None})
    return escenas


def _dibujar(carpeta: Path, escena: dict, prompt: str, ancho: int, alto: int, destino: Path,
             sin_lamina: dict | None = None, plano: int = 0) -> Path:
    """El dibujo de un plano, con la lámina de quien sale como referencia si la IA de imágenes sabe editar.
    sin_lamina: si se pasa y la edición con lámina falla, el plano se dibuja igual sin ella con la IA de imágenes normal
    (gratis primero) y se apunta ahí el motivo y el plano; los planos siguientes ya no la intentan. Pasó: Pollinations
    Kontext sin saldo (402) en el plano 6 dejaba ese plano con el dibujo del 5, sin el personaje que habla."""
    ref = escena["ref"]
    con_lamina = bool(ref and lamina(carpeta, ref).is_file() and ia.puede_referencia())
    if con_lamina and not (sin_lamina or {}).get("motivo"):
        try:
            return ia.imagen_con_producto(prompt, lamina(carpeta, ref), ancho, alto, destino, realista=False,
                                          respaldo=False)
        except Exception as error:
            if sin_lamina is None or isinstance(error, ia.Cobrado):  # Cobrado: otro dibujo se pagaría dos veces
                raise
            sin_lamina["motivo"] = texto_de_error(error)
    hecho = ia.imagen(prompt, ancho, alto, destino)
    if con_lamina and sin_lamina is not None:
        sin_lamina.setdefault("planos", []).append(plano)
    return hecho


def _edicion(ep: Path, nombre: str) -> Path:
    """La carpeta del editor del capítulo: al rehacerlo se pone al día la misma (no se llena Mis proyectos de copias),
    salvo que la retocaras a mano después: entonces va a otra y tu retoque se queda."""
    try:
        ed = diseno._local(json.loads((ep / "episodio.json").read_text(encoding="utf-8"))["edicion"]).resolve()
        if ed.parent == edicion.CARPETA.resolve() and \
                (ed / "proyecto.json").stat().st_mtime <= (ep / "episodio.json").stat().st_mtime:
            return ed
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return edicion.nueva_carpeta(nombre)


def crear_episodio(serie: str, idea: str = "", planos: int = 12, numero: int = 0,
                   aviso: Callable[[str, float], None] = lambda t, f: None, guion: dict | None = None,
                   dibujar: bool = True) -> dict:
    """Escribe el capítulo siguiente (o rehace el `numero` que ya existe, con su mismo guion y las imágenes que ya
    salieron) y lo convierte en video: imagen, animación y voz de cada plano. Queda también como proyecto del editor.
    Si no sale ningún dibujo no hay video: el guion queda guardado (estado «sin_dibujos») y se avisa con un error.
    guion: ya escrito (forma de ESQUEMA_EPISODIO) por quien maneja el estudio; entonces no se usa la IA de texto.
    dibujar=False: al rehacer no pide ningún dibujo; solo vuelve a montar los planos que no tienen escena."""
    escrito = ia.de_fuera(guion, ESQUEMA_EPISODIO, t("El guion del capítulo")) if guion is not None else None
    pago = ia.video_de_pago()  # fijado al empezar: lo que se preguntó (ver desde_prompt.montar)
    carpeta, datos = _abrir(serie)
    planos = max(3, min(int(planos), MAX_PLANOS))
    anteriores = _episodios(carpeta)
    numero = int(numero or 0)
    if numero < 0 or numero > MAX_EPISODIOS:
        raise ValueError(t("El número de capítulo va de 1 a {n}.", n=MAX_EPISODIOS))
    ep = carpeta / "episodios" / f"{numero:02d}" if numero else None
    rehacer = bool(ep and (ep / "guion.json").is_file() and escrito is None)
    if rehacer:
        guion = _leer_guion(ep, numero)
    else:
        numero = numero or max([e["numero"] for e in anteriores] + [0]) + 1
        ep = carpeta / "episodios" / f"{numero:02d}"
        if escrito is not None:
            guion = escrito
        else:
            aviso(t("La IA está escribiendo el capítulo {n}…", n=numero), 0.03)
            lista = "\n".join(f"- {p['nombre']}: {p['personalidad']}" for p in datos["personajes"])
            antes = "\n".join(f"Capítulo {e['numero']}: {e['titulo']}. {e['resumen']}" for e in anteriores[-10:])
            instrucciones = INSTRUCCIONES_EPISODIO
            for clave, valor in (("{numero}", str(numero)), ("{titulo}", datos["titulo"]),
                                 ("{sinopsis}", datos["sinopsis"]), ("{personajes}", lista),
                                 ("{antes}", antes or "(es el primero)"), ("{idioma}", IDIOMAS[actual()]),
                                 ("{estilo}", datos["estilo"])):
                instrucciones = instrucciones.replace(clave, valor)
            guion = ia.texto_json(instrucciones, f"Idea para este capítulo: {_texto(idea, 2000) or 'sigue la historia'}"
                                                 f"\nPlanos: unos {planos}." + memoria.para("dibujos"), ESQUEMA_EPISODIO)
        guion["planos"] = guion["planos"][:planos]  # nadie decide por su cuenta cuánto se gasta en imágenes y voces
        if not guion["planos"]:
            raise RuntimeError(t("La IA no escribió ningún plano. Inténtalo de nuevo."))
        ep.mkdir(parents=True, exist_ok=True)
        for vieja in ep.glob("video_final_imagen_*.png"):  # un guion nuevo pide imágenes nuevas (si no, se reusarían)
            vieja.unlink()
        diseno.escribir_json(ep / "guion.json", guion)
    escenas = _escenas(datos, guion)
    if not escenas:
        raise ValueError(t("El guion del capítulo {n} está dañado.", n=numero))
    # Al rehacer, el plano que ya tenía su dibujo se queda como está (ni se vuelve a narrar ni a montar); sin dibujar,
    # también los que no lo tienen: esos son de «Dibujar lo que falta»
    hechas = {i: ep / f"video_final_escena_{i:02d}.mp4" for i in range(len(escenas))
              if rehacer and (_imagen(ep, i).is_file() or not dibujar)
              and (ep / f"video_final_escena_{i:02d}.mp4").is_file()}

    sin_lamina = {}  # si la edición con lámina deja de funcionar a mitad: el motivo y los planos dibujados sin ella

    def crear_imagen(prompt, ancho, alto, destino):
        if destino.is_file():  # al rehacer el capítulo, lo que ya salió no se vuelve a pedir
            return destino
        if not dibujar:
            raise RuntimeError(t("se dibuja con «Dibujar lo que falta»"))
        i = int(destino.stem.rsplit("_", 1)[1])
        return _dibujar(carpeta, escenas[i], prompt, ancho, alto, destino, sin_lamina, i + 1)
    notas = []
    try:
        final = desde_prompt.montar({"escenas": escenas, "estilo_visual": datos["estilo"]}, ep, datos["formato"],
                                    datos["narrador"], aviso, crear_imagen=crear_imagen, notas=notas, hablados=hechas,
                                    pago=pago)
    except Exception as error:  # lo ya pagado no se pierde de vista (al rehacer, lo ya animado no se paga otra vez)
        desde_prompt.relanzar_con_gasto(error, notas, ep)
    if sin_lamina.get("planos"):  # una sola nota, en claro: el motivo es el mismo para todos
        notas.append(t("Planos dibujados sin la lámina de referencia porque la edición falló ({causa}): {lista}. Los "
                       "personajes pueden verse algo distintos; rehazlos cuando vuelva a funcionar.",
                       causa=sin_lamina["motivo"], lista=", ".join(map(str, sin_lamina["planos"]))))
    dibujos = sum(_imagen(ep, i).is_file() for i in range(len(escenas)))
    estado = _estado(ep, len(escenas))
    capitulo = {"numero": numero, "titulo": _texto(guion.get("titulo"), 120),
                "resumen": _texto(guion.get("resumen"), 1000), "estado": estado, "avisos": notas}
    if estado == "sin_dibujos":  # un video de manchas de color no es un capítulo: queda el guion para dibujarlo luego
        final.unlink(missing_ok=True)
        diseno.escribir_json(ep / "episodio.json", capitulo)
        raise RuntimeError(t("No salió ningún dibujo: seguramente se acabó la cuota gratis de imágenes de hoy. El guion "
                             "quedó guardado; pulsa «Dibujar lo que falta» más tarde o conecta Pollinations gratis en "
                             "«Claves de IA»."))
    if estado == "incompleto":
        notas.append(t("Faltan {n} dibujos: pulsa «Dibujar lo que falta» para hacerlos.", n=len(escenas) - dibujos))
    nombre = f"{datos['titulo']} · {t('Capítulo {n}', n=numero)}"
    proyecto = edicion.nuevo(nombre[:80], datos["formato"])
    for i in range(len(escenas)):  # para retocarlo a mano: cada plano es un clip en el editor de video
        proyecto = edicion.anadir_medio(proyecto, str(ep / f"video_final_escena_{i:02d}.mp4"))
    ed = _edicion(ep, proyecto["nombre"])
    edicion.guardar(proyecto, ed)
    diseno.escribir_json(ep / "episodio.json", {**capitulo, "edicion": str(ed)})
    aviso(t("¡Listo!"), 1.0)
    return {"tipo": "episodio", "formato": datos["formato"], "carpeta": str(ep), "edicion": str(ed),
            "titulo": nombre, "avisos": notas, "estado": estado,
            "resultados": [{"archivo": str(final), "titulo": f"{nombre}: {_texto(guion.get('titulo'), 120)}",
                            "descripcion": _texto(guion.get("resumen"), 1000), "hashtags": []}]}


# ---------- Retocar ----------

def rehacer_plano(episodio: str, i: int, descripcion: str | None = None, texto: str | None = None,
                  aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    """Vuelve a dibujar el plano `i` (desde 0) de un capítulo, si se pasa con otra descripción (en inglés) u otro
    texto, y monta otra vez el video: los demás planos se quedan como están. Gasta 1 imagen, aunque falten otras."""
    ep = _capitulo(episodio)
    carpeta, datos = _abrir(ep.parent.parent.name)
    guion = _leer_guion(ep, ep.name)
    lista, i = _planos(guion), int(i)
    if not 0 <= i < len(lista):
        raise ValueError(t("Ese capítulo no tiene el plano {n}.", n=i + 1))
    if descripcion:
        lista[i]["descripcion"] = _texto(descripcion, 1000)
    if texto:
        lista[i]["texto"] = _texto(texto, 400)
    # Primero el dibujo nuevo, aparte: sin cuota, el plano bueno (y su guion) se quedan como estaban
    escena, nuevo = _escenas(datos, guion)[i], ep / "plano_nuevo.png"
    aviso(t("Escena {n} de {total}: imagen…", n=i + 1, total=len(lista)), 0.05)
    try:  # el mismo prompt que le pondría desde_prompt.montar
        _dibujar(carpeta, escena, f"{escena['imagen']}, {datos['estilo']}", *video.FORMATOS[datos["formato"]], nuevo)
    except Exception as e:
        nuevo.unlink(missing_ok=True)
        raise RuntimeError(t("El plano {n} no se pudo dibujar ({causa}). Se quedó como estaba.", n=i + 1,
                             causa=texto_de_error(e).replace("\n", " · ")[:300])) from None
    diseno.escribir_json(ep / "guion.json", guion)
    os.replace(nuevo, _imagen(ep, i))
    (ep / f"video_final_escena_{i:02d}.mp4").unlink(missing_ok=True)
    return crear_episodio(carpeta.name, numero=int(ep.name), aviso=aviso, dibujar=False)


def exportar_cuadros(episodio: str, fps: int = 12) -> str:
    """Los cuadros de cada plano en PNG (cuadros/plano_NN/0001.png…), a 12 por segundo como la animación a mano:
    se importan como secuencia de imágenes en OpenToonz, Pencil2D o Krita."""
    ep = _capitulo(episodio)
    fps = max(1, min(int(fps), 30))
    planos = sorted(ep.glob("video_final_escena_*.mp4"))
    cuadros = sum(video.duracion(p) for p in planos) * fps
    if shutil.disk_usage(ep).free < cuadros * 2 * 1024 ** 2:  # un PNG de 1280 px pesa hasta ~2 MB
        raise ValueError(t("Hacen falta unos {mb} MB libres en el disco para sacar los cuadros.",
                           mb=int(cuadros * 2)))
    salida = ep / "cuadros"
    shutil.rmtree(salida, ignore_errors=True)
    for i, plano in enumerate(planos):
        carpeta = salida / f"plano_{i:02d}"
        carpeta.mkdir(parents=True)
        video.ffmpeg("-i", plano, "-vf", f"fps={fps},scale='min(1280,iw)':-2", carpeta / "%04d.png")
    return str(salida)


def programas() -> dict[str, str]:
    """Los programas libres de animación que están instalados: {nombre: ruta}."""
    hallados = {}
    for nombre, (ruta, orden, _) in PROGRAMAS.items():
        ruta = os.path.expandvars(ruta)
        encontrada = ruta if os.path.isfile(ruta) else shutil.which(orden)
        if encontrada:
            hallados[nombre] = encontrada
    return hallados
