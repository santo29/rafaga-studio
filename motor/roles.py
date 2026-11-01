"""Los departamentos del estudio, como en una empresa de servicios: cada uno con su manual corto (qué hace, con qué
herramientas y sus reglas de calidad). El Director lo lee para elegir bien y la memoria del estudio guarda las
preferencias del usuario por departamento (memoria.py)."""
from .idioma import t

GENERAL = "general"  # lo que vale para todo el estudio («mi marca es X»): no es un departamento con herramientas

DEPARTAMENTOS = {
    "video": {
        "nombre": t("Guion y video"),
        "hace": "videos narrados o de un personaje que habla, desde un pedido o una foto",
        "herramientas": ["crear_video"],
        "reglas": "las escenas, tiempos y textos en pantalla que escribió el usuario, tal cual; gancho en los 3 "
                  "primeros segundos; frases cortas que suenan bien en voz alta; si habla un personaje, en primera "
                  "persona; 9:16 para TikTok, Reels y Shorts, 16:9 para YouTube"},
    "diseno": {
        "nombre": t("Diseño gráfico"),
        "hace": "posts, flyers, logos, miniaturas, tarjetas, presentaciones, ilustraciones, fotos realistas y "
                "estampados en capas editables",
        "herramientas": ["crear_diseno"],
        "reglas": "un mensaje claro por pieza; los textos exactos del usuario; precios y contactos solo si los dio; "
                  "su marca si la tiene; un estampado es el dibujo, sin textos de venta"},
    "musica_voz": {
        "nombre": t("Música y voz"),
        "hace": "canciones y pistas, videos musicales, producir una voz grabada sobre una pista y separar voz e "
                "instrumental",
        "herramientas": ["crear_cancion", "crear_video_musical", "producir_cancion", "separar_voz_y_pista"],
        "reglas": "el género de la lista que pidió; letra original en el idioma del pedido, sin copiar canciones ni "
                  "imitar artistas reales; coro fácil de recordar"},
    "dibujos": {
        "nombre": t("Dibujos animados"),
        "hace": "series con personajes originales y sus capítulos",
        "herramientas": ["crear_serie", "crear_episodio", "listar_series"],
        "reglas": "personajes originales, nunca de otras marcas; los mismos personajes en cada capítulo; «Cartoon "
                  "2D» si no pidió otro estilo"},
    "anuncios": {
        "nombre": t("Anuncios"),
        "hace": "anuncios en video (pruebas A/B) con la foto real del producto",
        "herramientas": ["crear_anuncios"],
        "reglas": "con la foto real que dio (sin foto, un anuncio gráfico con crear_diseno); gancho, beneficio, "
                  "prueba y llamada a la acción; nunca ofertas ni precios inventados"},
    "edicion": {
        "nombre": t("Edición"),
        "hace": "unir fotos y videos con música y subtítulos, y sacar shorts de un video largo",
        "herramientas": ["editar_video", "sacar_shorts", "listar_proyectos"],
        "reglas": "solo archivos del usuario o del estudio y enlaces que escribió él; el orden que pidió"},
    "publicacion": {
        "nombre": t("Publicación"),
        "hace": "programar videos en YouTube",
        "herramientas": ["programar_publicacion"],
        "reglas": "solo si el usuario lo pidió; título y descripción de ese video; hora futura"},
    "nichos": {
        "nombre": t("Investigación de nichos"),
        "hace": "nichos virales, tendencias e ideas de video con datos reales",
        "herramientas": ["investigar_nichos"],
        "reglas": "el tema solo, sin red ni país; datos reales, nada inventado"},
}


def nombre(departamento: str) -> str:
    return t("Todo el estudio") if departamento == GENERAL else DEPARTAMENTOS[departamento]["nombre"]


def manual() -> str:
    """Cada departamento en una línea, para las instrucciones del Director."""
    return "\n".join(f"- {clave} ({d['nombre']}): {d['hace']}. Herramientas: {', '.join(d['herramientas'])}. "
                     f"Calidad: {d['reglas']}." for clave, d in DEPARTAMENTOS.items())
