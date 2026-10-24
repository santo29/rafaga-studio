"""Las herramientas del estudio que puede usar una IA: el servidor MCP (Claude u otro agente desde fuera) y el Director
(dentro de la app). Una sola lista para los dos: cada función recibe datos simples y devuelve JSON en texto.

Las rutas pasan por `ruta()`: el MCP la cambia para que las relativas sean de la carpeta del agente.
El progreso (`aviso`) va por hilo: el Director lo pone para ver cómo avanza cada herramienta en la app."""
import json
import threading
from pathlib import Path

from . import (anuncios, cabina, claves, desde_prompt, diseno_ia, musica, nichos, seguro, serie, shorts, video,
               video_musical)
from .idioma import t

_hilo = threading.local()


def ruta(r: str) -> str:
    return r


def _aviso():
    return getattr(_hilo, "aviso", None) or (lambda texto, f: None)


def _json(datos) -> str:
    return json.dumps(datos, ensure_ascii=False)


def crear_video(prompt: str, formato: str = "9:16", segundos: int = 45, voz: str = "es-DO-EmilioNeural",
                imagen: str = "", solo_animar: bool = False, guion: dict | None = None,
                animado: bool | None = None) -> str:
    """Crea un video completo desde un pedido: guion con IA, imágenes, voz, subtítulos y montaje.
    animado: cada escena es un video de IA con su propia voz: los personajes hablan con los labios sincronizados
    (una fruta que habla, un anuncio con actor…). Usa Gemini y es de pago: ~US$0,80-1 por escena de 8 s, con
    tope de 15 escenas animadas por video. Sin decirlo, se usa si el usuario conectó Gemini. False = imágenes
    con narración (gratis). Con animado, una escena cada ~8 s y como mucho 18 palabras de narración por escena.
    guion (opcional): si tú escribes el guion, pásalo y no se usa la IA de texto de la app. Forma:
    {"titulo", "descripcion", "hashtags": [..], "estilo_visual": estilo común de las imágenes en inglés,
    "escenas": [{"narracion": 1-2 frases que dice la voz, "imagen": descripción visual en inglés sin texto}]}.
    Unas segundos/6 escenas (sobran las de más).
    formato: 9:16, 16:9, 1:1 o 4:5. voz: una de las voces de la lista (ver listar_opciones).
    imagen: ruta de una foto de partida (la 1ª escena es esa foto y las demás mantienen su sujeto).
    solo_animar: con imagen, solo la anima según el pedido (clip corto sin voz). Para animarla, la imagen se sube
    a la IA de video: en Automático, primero a un Space público y gratis de Hugging Face; solo si el usuario eligió
    «Mi nube Modal» en Claves de IA, únicamente a su nube.
    Devuelve la ruta del video y el texto para publicar. Tarda varios minutos."""
    segundos = max(15, min(int(segundos), 600))  # los mismos rangos que la app: nada de trabajos gigantes
    if imagen and solo_animar:
        return _json(desde_prompt.animar_imagen(ruta(imagen), prompt, formato, aviso=_aviso()))
    return _json(desde_prompt.generar(prompt, formato, segundos, voz, ruta(imagen), aviso=_aviso(), guion=guion,
                                      animado=animado))


def sacar_shorts(url: str, formato: str = "9:16", modo: str = "recortar", cantidad: int = 5,
                 duracion_max: int = 60) -> str:
    """Saca los mejores shorts de un video largo a partir de su enlace (YouTube, Facebook, TikTok…).
    modo: 'recortar' (llena la pantalla) o 'difuminar' (video completo con fondo borroso).
    Devuelve las rutas de los shorts con título, descripción y hashtags. Tarda varios minutos."""
    cantidad, duracion_max = max(1, min(int(cantidad), 20)), max(15, min(int(duracion_max), 180))
    return _json(shorts.generar(url, formato, modo, cantidad, min(20, duracion_max), duracion_max, aviso=_aviso()))


def investigar_nichos(tema: str = "", pais: str = "Latinoamérica") -> str:
    """Investiga nichos virales (YouTube con datos reales + web en vivo si la IA es Claude).
    Devuelve nichos con potencial, pruebas, monetización e ideas de video con su prompt."""
    return _json(nichos.investigar(tema, pais=pais, aviso=_aviso()))


def crear_anuncios(foto: str, producto: str, detalles: str = "", publico: str = "", oferta: str = "",
                   estilo: str = "UGC testimonio (persona real con el móvil)", formato: str = "9:16",
                   variantes: int = 3, segundos: int = 25) -> str:
    """Crea varios anuncios en video realistas (pruebas A/B) a partir de la ruta de una foto del producto."""
    variantes, segundos = max(1, min(int(variantes), 6)), max(10, min(int(segundos), 90))
    return _json(anuncios.crear(ruta(foto), producto, detalles, publico, oferta, estilo, formato,
                                variantes=variantes, segundos=segundos, aviso=_aviso()))


def crear_cancion(idea: str, genero: str = "Dembow clásico (riddim jamaiquino 90s)", con_voz: bool = True,
                  segundos: int = 150) -> str:
    """Escribe y produce una canción o pista de cualquier género (ver listar_opciones para los géneros)."""
    segundos = max(30, min(int(segundos), 300))
    return _json(musica.crear(idea, genero, con_voz, segundos, aviso=_aviso()))


def crear_video_musical(cancion: str, formato: str = "9:16", idea: str = "", letra: str = "", genero: str = "") -> str:
    """Hace el video musical de una canción (ruta del audio): escenas que van con la música, ondas que se mueven
    con el sonido y la letra estilo karaoke. Pasa la letra si la tienes: mejora la sincronización.
    Para sincronizar, la canción se sube a la IA de transcripción conectada (Groq u OpenAI); sin ellas se hace en el PC."""
    return _json(video_musical.crear(ruta(cancion), letra=letra, genero=genero, formato=formato, idea=idea,
                                     aviso=_aviso()))


def producir_cancion(pista: str, voz: str, estilo: str = "Dembow / urbano (seco y al frente)",
                     afinacion: float = 0.6, referencia: str = "", titulo: str = "Mi canción") -> str:
    """Cabina: de una pista y una voz grabada (rutas de audio) a canción terminada. Detecta tempo y tonalidad,
    afina (0 natural – 1 robot), aplica la cadena de voz del estilo, mezcla con sidechain y masteriza
    (copiando el sonido de `referencia` si se da)."""
    afinacion = max(0.0, min(float(afinacion), 1.0))
    return _json(cabina.sesion(ruta(pista), ruta(voz), estilo, afinacion, ruta(referencia), titulo, aviso=_aviso()))


def separar_voz_y_pista(cancion: str) -> str:
    """Separa una canción en voz (acapella) e instrumental, en este PC (la canción no sale de aquí).
    `cancion` debe ser un archivo de audio local."""
    return _json(cabina.separar_cancion(ruta(cancion), aviso=_aviso()))


def crear_diseno(pedido: str, tipo: str = "post", usar_marca: bool = True, propuesta: dict | None = None) -> str:
    """Diseña una pieza gráfica en capas editables (como en Canva): textos, formas, iconos, emojis y fotos.
    tipo: anuncio, post, historia, miniatura, flyer, logo, tarjeta, marca_personal o presentacion (diapositiva 16:9).
    propuesta (opcional): si tú diseñas, pásalo y no se usa la IA de texto de la app. Medidas en % del lienzo (0-100):
    {"titulo", "descripcion", "fondo_colores": ["#RRGGBB", ...], "fondo_prompt_imagen": foto de fondo en inglés o "",
    "capas": [{"tipo": texto|imagen|forma|icono|emoji, "x", "y", "ancho", "alto", y según el tipo: "texto", "fuente",
    "tamano" (alto de letra en % del alto), "color", "negrita", "alineacion" (izquierda|centro|derecha), "sombra",
    "forma" (rectangulo|elipse|linea), "redondeo", "opacidad", "icono" (nombre Lucide), "prompt_imagen"}]}.
    usar_marca: usa el nombre, los colores, las fuentes y el logo guardados en «Mi marca» de la app.
    El diseño lo piensa la IA de texto conectada y las fotos se generan con la IA de imágenes conectada (primero
    lo gratis). Devuelve la carpeta del diseño (se abre y se edita en la página «Diseño» de la app), la vista
    previa PNG y los avisos."""
    return _json(diseno_ia.crear(pedido, tipo, bool(usar_marca), aviso=_aviso(), propuesta=propuesta))


def editar_video(medios: list[str], nombre: str = "Mi video", formato: str = "9:16", musica: str = "",
                 subtitulos: bool = False, calidad: str = "1080p") -> str:
    """Editor de video: une fotos y videos (rutas, en ese orden) en un proyecto del editor, con música de fondo
    (ruta de un audio, opcional; se corta donde acaba el video) y subtítulos automáticos si se piden, y lo exporta a
    MP4 (calidad 720p o 1080p). El proyecto queda guardado: se abre y se retoca a mano en la página «Editor de video»
    de la app. Sirve para unir los videos que hayan hecho otras herramientas."""
    from . import edicion, render_edicion
    if not isinstance(medios, list) or not medios:
        raise ValueError(t("Pasa al menos una foto o un video."))
    p = edicion.nuevo(str(nombre or "")[:80] or t("Mi video"), formato)
    for m in medios[:edicion.MAX_CLIPS]:
        p = edicion.anadir_medio(p, ruta(str(m)))
    if musica:
        p = edicion.anadir_medio(p, ruta(musica), audio=True)
        fondo = p["audios"][-1]
        fondo["hasta"] = min(fondo["hasta"], fondo["desde"] + edicion.tiempos(p)[-1][1])
        p = edicion.validar(p)
    carpeta = edicion.nueva_carpeta(p["nombre"])
    if subtitulos:
        p["subtitulos"] = {"activos": True, "palabras": render_edicion.subtitulos_automaticos(p, carpeta, _aviso())}
    edicion.guardar(p, carpeta)
    archivo = render_edicion.exportar(p, carpeta, carpeta / "video.mp4", calidad, _aviso())
    return _json({"tipo": "edicion", "formato": p["formato"], "carpeta": str(carpeta), "titulo": p["nombre"],
                  "resultados": [{"archivo": str(archivo), "titulo": p["nombre"], "descripcion": "", "hashtags": []}]})


def crear_serie(titulo: str, idea: str, estilo: str = "Anime 90s (estilo samurái)", personajes: int = 3,
                formato: str = "16:9", biblia: dict | None = None) -> str:
    """Serie animada: crea la serie (título, sinopsis) y sus personajes ORIGINALES, cada uno con su apariencia fija,
    su voz y su lámina dibujada. estilo: uno de la lista (Anime 90s (estilo samurái), Anime moderno, Cartoon 2D,
    Animación 3D (tipo Pixar), Cine realista, Cómic) o una descripción propia en inglés. personajes: de 1 a 6.
    biblia (opcional): si tú la escribes, no se usa la IA de texto de la app. Forma: {"titulo", "sinopsis",
    "personajes": [{"nombre", "descripcion": apariencia FIJA y concreta en inglés (50-80 palabras), "personalidad",
    "genero": hombre o mujer}]}. Después se hacen los capítulos con crear_episodio."""
    return _json(serie.crear_serie(titulo, idea, estilo, personajes, formato, aviso=_aviso(), biblia=biblia))


def crear_episodio(serie_nombre: str, idea: str = "", planos: int = 12, numero: int = 0,
                   guion: dict | None = None) -> str:
    """Serie animada: escribe y hace en video el capítulo siguiente de una serie (su título o nombre, ver
    listar_series), con los mismos personajes y siguiendo la historia. idea: qué pasa en este capítulo (vacío: la IA
    sigue la historia). planos: de 3 a 40 (unos 5 s cada uno). numero: para rehacer un capítulo que ya existe con su
    mismo guion (p. ej. si se acabó la cuota de imágenes a mitad). guion (opcional): si tú lo escribes, no se usa la
    IA de texto de la app. Forma: {"titulo", "resumen", "planos": [{"descripcion": lo que se ve en inglés (lugar,
    acción, cámara; sin texto), "personajes": [nombres que salen], "habla": nombre de quien habla o "Narrador",
    "texto": lo que dice, 1-2 frases}]}. Tarda varios minutos."""
    return _json(serie.crear_episodio(serie_nombre, idea, planos, numero, aviso=_aviso(), guion=guion))


def listar_series() -> str:
    """Las series animadas creadas, con sus personajes y capítulos."""
    return _json(serie.listar())


def listar_proyectos() -> str:
    """Lista los proyectos ya creados, del más nuevo al más viejo."""
    return _json(shorts.proyectos())


def listar_opciones() -> str:
    """Formatos, voces y proveedores de IA conectados (sin mostrar las claves)."""
    return _json({"formatos": list(video.FORMATOS), "voces": desde_prompt.voces(),
                  "generos_musica": list(musica.GENEROS), "estilos_anuncio": list(anuncios.ESTILOS),
                  "estilos_cabina": list(cabina.PRESETS),
                  "proveedores": claves.publico(), "por_defecto": claves.ajustes()})


TODAS = {f.__name__: f for f in (crear_video, sacar_shorts, investigar_nichos, crear_anuncios, crear_cancion,
                                 crear_video_musical, producir_cancion, separar_voz_y_pista, crear_diseno,
                                 editar_video, crear_serie, crear_episodio, listar_series, listar_proyectos,
                                 listar_opciones)}


def resultados(respuesta: str) -> list[dict]:
    """Los videos y audios que dejó una herramienta (para verlos en la app): todo {"archivo", "titulo"} de su JSON."""
    try:
        datos = json.loads(respuesta)
    except (TypeError, ValueError):
        return []
    hallados, pendientes = [], [datos]
    while pendientes:
        d = pendientes.pop()
        if isinstance(d, dict):
            # nunca una ruta de red: el reproductor la abriría y Windows mandaría tu usuario a ese servidor
            if (isinstance(d.get("archivo"), str) and isinstance(d.get("titulo"), str) and Path(d["archivo"]).suffix
                    and not seguro.es_ruta_de_red(d["archivo"])):
                hallados.append({"archivo": d["archivo"], "titulo": d["titulo"],
                                 "descripcion": str(d.get("descripcion") or ""),
                                 "hashtags": [str(h) for h in d.get("hashtags") or [] if isinstance(h, str)]})
            pendientes += list(d.values())
        elif isinstance(d, list):
            pendientes += d
    return hallados[::-1]
