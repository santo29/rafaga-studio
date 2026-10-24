"""Examen del Director con la IA de verdad: python -m pruebas.examen_director

GASTA llamadas a la IA (Gemini, una por pedido) y por eso NO va en «python -m pruebas». Le pide al Director pedidos
típicos, escritos como los escribe la gente (con faltas), y mira SOLO su primer paso: qué herramienta elige y sus
argumentos clave. Ninguna herramienta se ejecuta (nada caro): el Director se para justo antes de usarla. Imprime la
nota (aciertos/total) y los fallos. Usa tu clave de Gemini para el texto solo en este proceso: tus ajustes no cambian,
y tu memoria del estudio no se lee ni se toca."""
import inspect
import json
import os
import sys
import tempfile
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")
from motor import claves, director, herramientas, memoria  # noqa: E402

PAUSA = 5  # segundos entre pedidos: la cuota gratis de Gemini admite pocas llamadas por minuto
MANANA = (date.today() + timedelta(days=1)).isoformat()
MANZANA = "C:/Users/Yo/Videos/manzana.mp4"
CANCION = "C:/Users/Yo/Music/mi tema.mp3"
CLIPS = ["C:/Users/Yo/Videos/playa1.mp4", "C:/Users/Yo/Videos/playa2.mp4"]


def _n(texto) -> str:
    """Minúsculas y sin tildes, para comparar como lo escribiría cualquiera."""
    texto = texto if isinstance(texto, str) else json.dumps(texto, ensure_ascii=False)
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def contiene(*trozos):
    return lambda v: all(_n(x) in _n(v) for x in trozos)


def uno_de(*valores):
    return lambda v: v in valores


def es_ruta(*rutas):
    """Esos archivos, en ese orden (con / o \\, como los escriba la IA)."""
    return lambda v: [director._norma(x) for x in (v if isinstance(v, list) else [v])] == [director._norma(r) for r in rutas]


def manana_a_las_6(v) -> bool:
    return str(v).startswith(MANANA) and str(v)[11:16] in ("06:00", "18:00")


# Cada caso: el pedido (y lo que ya pasó en la conversación), las herramientas que valen como primer paso con lo que
# deben llevar sus argumentos ("*": todos juntos; "" = preguntarle al usuario), y una respuesta buena de ejemplo (la
# usa la prueba sin red para comprobar el examen).
CASOS = [
    {"pedido": "hazme un dibujito animao de un gato pirata",
     "valen": {"crear_serie": {"*": contiene("gato", "pirata"), "estilo": "Cartoon 2D"}},
     "ejemplo": ("crear_serie", {"titulo": "El gato pirata", "idea": "un gato pirata"})},
    {"pedido": "calavera gotica pa una camiseta",
     "valen": {"crear_diseno": {"tipo": "estampado", "pedido": contiene("calavera")}},
     "ejemplo": ("crear_diseno", {"pedido": "calavera gótica para una camiseta", "tipo": "estampado"})},
    {"pedido": "una canción de dembow sobre Punta Cana",
     "valen": {"crear_cancion": {"genero": contiene("dembow"), "idea": contiene("punta cana")}},
     "ejemplo": ("crear_cancion", {"idea": "una canción sobre Punta Cana", "genero": "Dembow moderno"})},
    {"pedido": "programa el video de la manzana pa mañana a las 6",
     "historial": [{"rol": "usuario", "texto": "hazme un video de una manzana que habla"},
                   {"rol": "director", "texto": "Listo: tu video de la manzana está en «Crear con IA».",
                    "hecho": f"Hecho: crear_video → {MANZANA}"}],
     "valen": {"programar_publicacion": {"archivo": es_ruta(MANZANA), "fecha_hora": manana_a_las_6}, "": {}},
     "ejemplo": ("programar_publicacion", {"archivo": MANZANA, "titulo": "La manzana que habla",
                                           "descripcion": "#manzana", "fecha_hora": f"{MANANA}T18:00"})},
    {"pedido": "un anuncio de mi barbería",  # sin foto: o la pide o hace una pieza gráfica
     "valen": {"": {}, "crear_diseno": {"pedido": contiene("barber")}},
     "ejemplo": ("", {})},
    {"pedido": "hazme un video de una manzana que abla de comer sano",
     "valen": {"crear_video": {"prompt": contiene("manzana"), "animado": False}},  # lo de pago, solo si lo pide
     "ejemplo": ("crear_video", {"prompt": "una manzana que habla de comer sano"})},
    {"pedido": "sacame unos shorts de este video https://youtu.be/dQw4w9WgXcQ",
     "valen": {"sacar_shorts": {"url": "https://youtu.be/dQw4w9WgXcQ"}},
     "ejemplo": ("sacar_shorts", {"url": "https://youtu.be/dQw4w9WgXcQ"})},
    {"pedido": "investiga nichos virales de recetas dominicanas pa tiktok",
     "valen": {"investigar_nichos": {"tema": lambda v: "receta" in _n(v) and "tiktok" not in _n(v),
                                     "redes": contiene("tiktok")}},
     "ejemplo": ("investigar_nichos", {"tema": "recetas dominicanas", "redes": "TikTok"})},
    {"pedido": "un logo pa mi pizeria Don Mario",
     "valen": {"crear_diseno": {"tipo": uno_de("logo", "auto"), "pedido": contiene("don mario")}},
     "ejemplo": ("crear_diseno", {"pedido": "logo para mi pizzería Don Mario", "tipo": "logo"})},
    {"pedido": "un flayer pa una fiesta de cumpleaños el sabado a las 8",
     "valen": {"crear_diseno": {"tipo": uno_de("flyer", "auto"), "pedido": contiene("cumplea", "8")}},
     "ejemplo": ("crear_diseno", {"pedido": "flyer para una fiesta de cumpleaños el sábado a las 8", "tipo": "flyer"})},
    {"pedido": "una miniatura de youtube pa mi video de pesca en samana",
     "valen": {"crear_diseno": {"tipo": uno_de("miniatura", "auto"), "pedido": contiene("pesca")}},
     "ejemplo": ("crear_diseno", {"pedido": "miniatura de YouTube de mi video de pesca en Samaná",
                                  "tipo": "miniatura"})},
    {"pedido": "una bachata triste sin voz",
     "valen": {"crear_cancion": {"genero": contiene("bachata"), "con_voz": False}},
     "ejemplo": ("crear_cancion", {"idea": "una bachata triste", "genero": "Bachata", "con_voz": False})},
    {"pedido": "separa la voz de esta cancion", "adjuntos": [CANCION],
     "valen": {"separar_voz_y_pista": {"cancion": es_ruta(CANCION)}},
     "ejemplo": ("separar_voz_y_pista", {"cancion": CANCION})},
    {"pedido": "hazle un video musical a mi cancion", "adjuntos": [CANCION],
     "valen": {"crear_video_musical": {"cancion": es_ruta(CANCION)}},
     "ejemplo": ("crear_video_musical", {"cancion": CANCION})},
    {"pedido": "une estos videos y ponle esta musica", "adjuntos": [*CLIPS, CANCION],
     "valen": {"editar_video": {"medios": es_ruta(*CLIPS), "musica": es_ruta(CANCION)}},
     "ejemplo": ("editar_video", {"medios": CLIPS, "musica": CANCION})},
    {"pedido": "recuerda que me gustan los titulos cortos",
     "valen": {"recordar_preferencia": {"preferencia": contiene("titulos", "cortos")}},
     "ejemplo": ("recordar_preferencia", {"departamento": "general", "preferencia": "títulos cortos"})},
    {"pedido": "otro capitulo de la serie del gato pirata",
     "historial": [{"rol": "usuario", "texto": "hazme un dibujito animado de un gato pirata"},
                   {"rol": "director", "texto": "Listo: la serie «El gato pirata» y su primer capítulo.",
                    "hecho": "Hecho: crear_serie\nHecho: crear_episodio → C:/Users/Yo/series/El gato pirata/1.mp4"}],
     "valen": {"crear_episodio": {"serie_nombre": contiene("gato")}, "listar_series": {}},
     "ejemplo": ("crear_episodio", {"serie_nombre": "El gato pirata"})},
    {"pedido": "un post pa instagram de mi tienda de ropa con 20% de descuento",
     "valen": {"crear_diseno": {"tipo": uno_de("post", "auto"), "pedido": contiene("20%")}},
     "ejemplo": ("crear_diseno", {"pedido": "post de Instagram de mi tienda de ropa con 20% de descuento",
                                  "tipo": "post"})},
    {"pedido": "hazme una caricatura de un perro bombero pa tiktok",
     "valen": {"crear_serie": {"*": contiene("perro", "bombero"), "formato": "9:16"}},
     "ejemplo": ("crear_serie", {"titulo": "El perro bombero", "idea": "un perro bombero", "formato": "9:16"})},
    {"pedido": "dame ideas de videos virales de fitnes",
     "valen": {"investigar_nichos": {"tema": contiene("fitn")}},
     "ejemplo": ("investigar_nichos", {"tema": "fitness"})},
]


class _Primero(BaseException):
    """Para al Director justo antes de usar su primera herramienta (BaseException: _usar no la toma por un fallo)."""


def pedido_de(caso: dict) -> str:
    """Como lo manda la página del Director, con los adjuntos."""
    adjuntos = caso.get("adjuntos")
    return caso["pedido"] + (f"\n\nArchivos que te doy: {json.dumps(adjuntos, ensure_ascii=False)}" if adjuntos else "")


def primer_paso(caso: dict) -> tuple[str, dict | str, str]:
    """(herramienta, argumentos, mensaje) del primer paso; ("", {}, mensaje) si pregunta o termina sin herramientas."""
    visto, mensajes = {}, []

    def parar(nombre, argumentos, *_, **__):
        visto.update(nombre=nombre, argumentos=argumentos)
        raise _Primero
    real, director._usar = director._usar, parar
    try:
        r = director.dirigir(pedido_de(caso), caso.get("historial", ()), aviso=lambda texto, f: mensajes.append(texto))
        return "", {}, r["mensaje"]
    except _Primero:
        argumentos = visto["argumentos"]
        try:
            argumentos = json.loads(argumentos or "{}") if isinstance(argumentos, str) else argumentos
        except ValueError:
            pass  # se queda el texto: revisar() lo cuenta como fallo
        return visto["nombre"], argumentos, mensajes[-1] if mensajes else ""
    finally:
        director._usar = real


def revisar(caso: dict, nombre: str, argumentos) -> list[str]:
    """Lo que está mal en ese primer paso ([] si está bien)."""
    if nombre not in caso["valen"]:
        return [f"usó {nombre or '(ninguna: preguntó o terminó)'}; valían {', '.join(n or 'preguntar' for n in caso['valen'])}"]
    if not nombre:
        return []
    if not isinstance(argumentos, dict):
        return [f"argumentos que no son un objeto JSON: {str(argumentos)[:200]}"]
    try:  # los que no tiene o le faltan, como los rechazaría el Director; y los de por defecto, como los usaría
        dados = inspect.signature(herramientas.TODAS[nombre]).bind(**argumentos)
    except TypeError as e:
        return [f"argumentos no válidos: {e}"]
    dados.apply_defaults()
    problemas = []
    for campo, esperado in caso["valen"][nombre].items():
        valor = argumentos if campo == "*" else dados.arguments.get(campo)
        if not (esperado(valor) if callable(esperado) else valor == esperado):
            problemas.append(f"{campo} = {json.dumps(valor, ensure_ascii=False)[:200]}")
    return problemas


def examinar(casos=CASOS, escribir=print) -> tuple[int, list[str]]:
    """(aciertos, fallos explicados). Cada pedido empieza de cero (con su historial, si lo trae)."""
    aciertos, fallos = 0, []
    for i, caso in enumerate(casos):
        if i and PAUSA:
            time.sleep(PAUSA)
        try:
            nombre, argumentos, mensaje = primer_paso(caso)
            problemas = revisar(caso, nombre, argumentos)
        except Exception as e:  # la IA no respondió o respondió algo roto: cuenta como fallo y se sigue
            nombre, mensaje, problemas = "", "", [f"error: {str(e).strip() or type(e).__name__}"]
        aciertos += not problemas
        escribir(f"{'OK   ' if not problemas else 'FALLO'} {caso['pedido']} → {nombre or '(pregunta)'}")
        if problemas:
            fallos.append(f"«{caso['pedido']}» → {nombre or '(pregunta)'}: {'; '.join(problemas)}"
                          + (f"\n    dijo: {mensaje[:300]}" if mensaje else ""))
    return aciertos, fallos


if __name__ == "__main__":
    reales = claves.ajustes
    claves.ajustes = lambda: {**reales(), "texto": "gemini"}  # solo en este proceso: tus ajustes no cambian
    if (claves.para("texto") or {}).get("proveedor") != "gemini":
        sys.exit("Conecta una clave de Gemini en «Claves de IA»: el examen usa Gemini para el texto.")
    memoria.ARCHIVO = Path(tempfile.mkdtemp(prefix="rafaga-examen-")) / "memoria.json"  # sin tus preferencias
    aciertos, fallos = examinar()
    print(f"\nNota: {aciertos}/{len(CASOS)}")
    for fallo in fallos:
        print(f"- {fallo}")
