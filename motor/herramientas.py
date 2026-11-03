"""Las herramientas del estudio que puede usar una IA: el servidor MCP (Claude u otro agente desde fuera) y el Director
(dentro de la app). Una sola lista para los dos: cada función recibe datos simples y devuelve JSON en texto.

Las rutas pasan por `ruta()`: el MCP la cambia para que las relativas sean de la carpeta del agente.
El progreso (`aviso`) va por hilo: el Director lo pone para ver cómo avanza cada herramienta en la app."""
import inspect
import json
import re
import threading
from pathlib import Path

from . import (anuncios, cabina, claves, desde_prompt, diseno_ia, ia, memoria, musica, nichos, publicar, roles,
               seguro, serie, shorts, video, video_musical)
from .idioma import t

_hilo = threading.local()
MAX_DESCRIPCION = 1500  # lo que se publica con programar_publicacion: cabe entero en la pregunta al usuario


def ruta(r: str) -> str:
    return r


def _aviso():
    return getattr(_hilo, "aviso", None) or (lambda texto, f: None)


def _json(datos) -> str:
    return json.dumps(datos, ensure_ascii=False)


# El modelo de video de UN trabajo (el selector «Modelo de video» de la app): va al final de la ayuda de cada
# herramienta que anima escenas. Empieza por su nombre: el Director no lo ve (lo pone el código, ver director._usar)
AYUDA_MODELO = """modelo_video (opcional): con qué IA se animan las escenas, solo en este trabajo (no cambia
«Claves de IA»): auto (lo elegido en «Claves de IA»; de fábrica, la nube Modal del usuario si la conectó y si no, el
Space público de Hugging Face), ninguno (sin animar: fotos con movimiento),
huggingface (gratis, cupo diario), modal (la nube del usuario, gratis con su crédito), pollinations, kling o seedance
(de pago: la app pregunta antes el costo) o gemini (Gemini Omni, de pago: solo escenas que hablan, con animado true en
crear_video). Solo valen los conectados: ver "modelos_video" en listar_opciones."""


def validar_modelo(modelo_video, habla: bool = False) -> str:
    """claves.validar_modelo_video y, además, Gemini Omni solo donde hace algo: las escenas que hablan (habla:
    crear_video con animado true). Si no, se haría con Automático sin decirlo. El MCP lo llama también antes de
    preguntar el costo."""
    modelo = claves.validar_modelo_video(modelo_video)
    if modelo == "gemini" and not habla:
        raise ValueError(t("Gemini Omni solo hace escenas que hablan: úsalo en crear_video con animado true."))
    return modelo


def _voz(voz: str) -> str:
    """La voz de un trabajo: vacía, la que dejó fija el usuario o la de su idioma. Antes de gastar en imágenes: la
    narración fallaría al final."""
    voz = voz or desde_prompt.voz_inicial()
    if voz not in desde_prompt.voces().values():
        raise ValueError(t("Voz desconocida ({voz!r:.40}); valen {voces}.", voz=voz,
                           voces=", ".join(desde_prompt.voces().values())))
    return voz


def crear_video(prompt: str, formato: str = "9:16", segundos: int = 45, voz: str = "",
                imagen: str = "", solo_animar: bool = False, guion: dict | None = None,
                animado: bool = False, modelo_video: str = "auto") -> str:
    """Crea un video completo desde un pedido: la IA escribe la narración y hace imágenes, voz, subtítulos y montaje.
    animado: true = cada escena es un video de IA con su propia voz: los personajes hablan con los labios
    sincronizados (una fruta que habla, un anuncio con actor…). Lo hace la IA que el usuario eligió para las escenas
    que hablan (Gemini, Kling o Seedance) y es DE PAGO: unos US$1-2 por escena de 8 s según cuál (una escena cada
    ~8 s, tope de 15 por video). Úsalo solo si el usuario aceptó ese costo. Por defecto false: imágenes animadas con
    narración (gratis, salvo que el usuario haya elegido una IA de video de pago para animarlas).
    formato: 9:16, 16:9, 1:1 o 4:5. voz: déjala vacía salvo que el usuario pida una concreta o el video en otro idioma (si
    tiene ElevenLabs y no dejó una voz fija, el estudio le pregunta si la quiere gratis o de ElevenLabs): el id de una de estas: {voces} (o una
    de ElevenLabs de listar_opciones). Con animado, lo poco que se narre va con una voz gratis.
    imagen: ruta de una foto de partida (la 1ª escena es esa foto y las demás mantienen su sujeto).
    solo_animar: con imagen, solo la anima según el pedido (clip corto sin voz). Para animarla, la imagen se sube
    a la IA de video: en Automático, a la nube Modal del usuario si la conectó y si no, a un Space público y gratis de
    Hugging Face (con «No usar» en Claves de IA, nunca al Space: sin Modal, falla sin subir nada); si eligió Kling o
    Seedance (de pago), únicamente a esa. Pollinations no anima fotos (no la ve).
    Devuelve la ruta del video y el texto para publicar. Tarda varios minutos.

    guion (opcional): si tú escribes el guion, pásalo y no se usa la IA de texto de la app. Forma:
    {"titulo", "descripcion", "hashtags": [..], "estilo_visual": estilo común de las imágenes en inglés,
    "escenas": [{"narracion": 1-2 frases que dice la voz ("" sin voz), "imagen": el primer fotograma en inglés sin
    texto, "movimiento" (opcional): en inglés, el movimiento de cámara y luego la acción, "texto_pantalla"
    (opcional): lo que se lee en pantalla}]}. Unas segundos/6 escenas (segundos/8 y como mucho 18 palabras por escena
    si va animado), o las que numere el prompt (ESCENA 1, 2…); si sobran, se quitan las del medio y se conserva la
    última."""
    segundos = max(15, min(int(segundos), 600))  # los mismos rangos que la app: nada de trabajos gigantes
    # antes de gastar nada. Nunca se fuerza animado: la ventana de costo del MCP se calculó con lo que pidió el agente
    modelo_video = validar_modelo(modelo_video, habla=animado is True and not (imagen and solo_animar))
    if imagen and solo_animar:
        if modelo_video == "ninguno":
            raise ValueError(t("«Sin animar» no anima nada: para animar solo la imagen, elige otro modelo de video."))
        with claves.por_trabajo(modelo_video):
            return _json(desde_prompt.animar_imagen(ruta(imagen), prompt, formato, aviso=_aviso()))
    voz = _voz(voz)
    with claves.por_trabajo(modelo_video):
        return _json(desde_prompt.generar(prompt, formato, segundos, voz, ruta(imagen), aviso=_aviso(), guion=guion,
                                          animado=animado))


crear_video.__doc__ = crear_video.__doc__.replace("{voces}", ", ".join(desde_prompt.VOCES.values()))


def sacar_shorts(url: str, formato: str = "9:16", modo: str = "recortar", cantidad: int = 5,
                 duracion_max: int = 60) -> str:
    """Saca los mejores shorts de un video largo a partir de su enlace (YouTube, Facebook, TikTok…).
    modo: 'recortar' (llena la pantalla) o 'difuminar' (video completo con fondo borroso).
    Devuelve las rutas de los shorts con título, descripción y hashtags. Tarda varios minutos."""
    cantidad, duracion_max = max(1, min(int(cantidad), 20)), max(15, min(int(duracion_max), 180))
    return _json(shorts.generar(url, formato, modo, cantidad, min(20, duracion_max), duracion_max, aviso=_aviso()))


def investigar_nichos(tema: str = "", pais: str = "Latinoamérica",
                      redes: str = "YouTube, TikTok, Instagram y Facebook") -> str:
    """Investiga nichos virales (YouTube con datos reales + web en vivo si la IA es Claude).
    tema: solo el tema (p. ej. «recetas dominicanas»), sin red ni país: esos van en redes y pais.
    Devuelve nichos con potencial, pruebas, monetización e ideas de video con su prompt."""
    return _json(nichos.investigar(tema, redes=redes, pais=pais, aviso=_aviso()))


def crear_anuncios(foto: str, producto: str = "", detalles: str = "", publico: str = "", oferta: str = "",
                   estilo: str = "UGC testimonio (persona real con el móvil)", formato: str = "9:16",
                   variantes: int = 3, segundos: int = 25, modelo_video: str = "auto", voz: str = "") -> str:
    """Crea varios anuncios en video realistas (pruebas A/B) a partir de la ruta de una foto del producto o del
    negocio. producto: qué se anuncia; vacío, la IA lo saca de la foto (si la IA de texto no ve fotos, responde que
    hay que decirlo). estilo: uno de {estilos}. voz: como en crear_video, vacía salvo que el usuario pida una."""
    variantes, segundos = max(1, min(int(variantes), 6)), max(10, min(int(segundos), 90))
    voz = _voz(voz)
    with claves.por_trabajo(validar_modelo(modelo_video)):
        return _json(anuncios.crear(ruta(foto), producto, detalles, publico, oferta, estilo, formato, voz=voz,
                                    variantes=variantes, segundos=segundos, aviso=_aviso()))


crear_anuncios.__doc__ = crear_anuncios.__doc__.replace("{estilos}", "; ".join(anuncios.ESTILOS))


def crear_cancion(idea: str, genero: str = "", con_voz: bool = True, segundos: int = 150) -> str:
    """Escribe y produce una canción o pista. genero: uno de {generos}; vacío: la IA lo elige según la idea."""
    segundos = max(30, min(int(segundos), 300))
    return _json(musica.crear(idea, genero, con_voz, segundos, aviso=_aviso()))


crear_cancion.__doc__ = crear_cancion.__doc__.replace("{generos}", "; ".join(musica.GENEROS))


def crear_video_musical(cancion: str, formato: str = "9:16", idea: str = "", letra: str = "", genero: str = "",
                        titulo: str = "", modelo_video: str = "auto") -> str:
    """Hace el video musical de una canción (ruta del audio): escenas que van con la música, ondas que se mueven
    con el sonido y la letra estilo karaoke. Pasa la letra si la tienes: el karaoke muestra la letra escrita, con los
    tiempos de lo que se oye. titulo: el de la canción (vacío: el de su proyecto o el de sus etiquetas).
    Para sincronizar, la canción se sube a la IA de transcripción conectada (Groq u OpenAI); sin ellas se hace en el PC."""
    with claves.por_trabajo(validar_modelo(modelo_video)):
        return _json(video_musical.crear(ruta(cancion), titulo=str(titulo or "")[:80], letra=letra, genero=genero,
                                         formato=formato, idea=idea, aviso=_aviso()))


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


def crear_diseno(pedido: str, tipo: str = "auto", usar_marca: bool = True, propuesta: dict | None = None,
                 estilo: str = "auto", calidad: str = "1K") -> str:
    """Diseña una pieza gráfica en capas editables: textos, formas, iconos, emojis e ilustraciones o fotos.
    tipo: auto (la IA lo elige según el pedido), anuncio, post, historia, miniatura, flyer, logo, tarjeta,
    marca_personal, presentacion (diapositiva 16:9), ilustracion (un dibujo grande, sin textos salvo que los pida),
    foto (una foto realista que llena todo el lienzo: algo real, p. ej. una mariposa real en un jardín) o estampado
    (camiseta, taza o sticker: el dibujo es la pieza, sin textos de venta).
    estilo del dibujo: auto, vector, sticker, tatuaje, poster, grabado, render3d (render 3D), neon_oscuro (arte
    digital oscuro con neón y humo, p. ej. portadas de álbum), animado3d (personaje 3D de película animada), urbano
    (calle, gorras, grafiti, humo) o foto (foto solo para un producto, lugar o persona real).
    usar_marca: usa el nombre, los colores, las fuentes y el logo guardados en «Mi marca» de la app.
    calidad de las fotos: 1K, 2K o 4K (2K y 4K solo con Gemini elegido para imágenes, y cuestan más).
    Primero la IA entiende el pedido (también con faltas). Si tiene dos lecturas igual de probables, no gasta nada y
    devuelve {"pregunta", "opciones"}: házsela al usuario y vuelve a llamar con lo que elija. Si no, "entendido" dice
    qué entendió. El diseño lo piensa la IA de texto conectada y los dibujos se generan con la IA de imágenes
    conectada (primero lo gratis). Devuelve la carpeta del diseño (se abre y se edita en la página «Diseño» de la
    app), la vista previa PNG y los avisos.
    Los datos reales (precios, webs, teléfonos, @) tienen que venir en pedido: los que no estén ahí ni en la marca se
    cambian por huecos ([Precio], [Web]…) aunque los traiga el diseño, porque las IA se los inventan.

    propuesta (opcional): si tú diseñas, pásalo y no se usa la IA de texto de la app. Medidas en % del lienzo (0-100):
    {"titulo", "descripcion", "fondo_colores": ["#RRGGBB", ...], "fondo_prompt_imagen": foto de fondo en inglés o "",
    "capas": [{"tipo": texto|imagen|forma|icono|emoji, "x", "y", "ancho", "alto", y según el tipo: "texto", "fuente",
    "tamano" (alto de letra en % del alto), "color", "negrita", "alineacion" (izquierda|centro|derecha), "sombra",
    "forma" (rectangulo|elipse|linea), "redondeo", "opacidad" (0-100), "icono" (nombre Lucide), "prompt_imagen"}]}."""
    # antes de gastar nada en entender el pedido (el Director no pasa por la validación de tipos del MCP)
    if tipo != "auto" and (not isinstance(tipo, str) or tipo not in diseno_ia.TIPOS):
        raise ValueError(t("Tipo de diseño desconocido ({tipo!r:.30}); valen {tipos}.", tipo=tipo,
                           tipos=", ".join(diseno_ia.TIPOS)))
    if not isinstance(estilo, str) or estilo not in diseno_ia.ESTILOS:
        raise ValueError(t("Estilo desconocido ({estilo!r:.30}); valen {estilos}.", estilo=estilo,
                           estilos=", ".join(diseno_ia.ESTILOS)))
    if not isinstance(calidad, str) or calidad not in ia.PRECIO_IMAGEN_GEMINI[ia.IMAGEN_GEMINI]:
        raise ValueError(t("Calidad desconocida ({calidad!r:.20}); valen 1K, 2K o 4K.", calidad=calidad))
    if tipo == "ilustracion" and diseno_ia.pide_foto(pedido):  # el Director (una IA pequeña) la pide para toda imagen
        tipo, estilo = "foto", "foto"  # y un «vector» suyo la dejaba en dibujo
    delante = {}
    if propuesta is None and str(pedido or "").strip():
        e = diseno_ia.entender(pedido, tipo)
        if not e.get("seguro", True):
            return _json({"pregunta": e.get("pregunta", ""), "opciones": e.get("opciones", [])})
        pedido = e.get("entendido") or pedido
        tipo = e.get("tipo", tipo) if tipo == "auto" else tipo
        estilo = e.get("estilo", estilo) if estilo == "auto" else estilo
        delante = {"entendido": pedido}  # primero: el Director ve el resultado recortado y debe saber qué se entendió
    tipo = "post" if tipo == "auto" else tipo
    return _json({**delante, **diseno_ia.crear(pedido, tipo, bool(usar_marca), aviso=_aviso(), propuesta=propuesta,
                                               calidad=calidad, estilo=estilo)})


VOLUMEN_FONDO = 0.3  # la música de fondo, a -10 dB: al 100 % tapaba la voz del video y la suma llegaba a 0 dBFS


def musica_de_fondo(fondo: dict, largo: float) -> list[dict]:
    """La música de fondo de editar_video: baja (VOLUMEN_FONDO), cortada donde acaba el video y, si es más corta que
    él, repetida con un fundido en cada vuelta (acababa 3,6 s antes y quedaba un silencio de golpe). Termina siempre
    con un fundido de salida."""
    trozo = fondo["hasta"] - fondo["desde"]
    vueltas, inicio = [], 0.0
    while inicio < largo - 0.5 and trozo > 1 and len(vueltas) < 40:  # tope: el editor admite 50 audios
        vuelta = {**fondo, "inicio": inicio, "volumen": VOLUMEN_FONDO, "entrada": 1.0 if vueltas else 0.0,
                  "salida": 1.0}
        vuelta["hasta"] = min(fondo["hasta"], fondo["desde"] + largo - inicio)
        vueltas.append(vuelta)
        inicio += trozo
    vueltas = vueltas or [{**fondo, "volumen": VOLUMEN_FONDO, "hasta": min(fondo["hasta"], fondo["desde"] + largo)}]
    vueltas[-1]["salida"] = min(2.0, (vueltas[-1]["hasta"] - vueltas[-1]["desde"]) / 2)
    for i, v in enumerate(vueltas[1:], 1):  # cada vuelta con su propio id: el editor los distingue por él
        v["id"] = f"{fondo.get('id', 'musica')}-{i}"
    return vueltas


def editar_video(medios: list[str], nombre: str = "Mi video", formato: str = "9:16", musica: str = "",
                 subtitulos: bool = False, calidad: str = "1080p") -> str:
    """Editor de video: une fotos y videos (rutas, en ese orden) en un proyecto del editor, con música de fondo
    (ruta de un audio, opcional; se corta donde acaba el video) y subtítulos automáticos si se piden, y lo exporta a
    MP4 (calidad 720p, 1080p o 4K: 3840×2160 en 16:9 y 2160×3840 en 9:16, más nítido pero varias veces más lento).
    El proyecto queda guardado: se abre y se retoca a mano en la página «Editor de video» de la app. Sirve para unir
    los videos que hayan hecho otras herramientas."""
    from . import edicion, render_edicion
    if not isinstance(medios, list) or not medios:
        raise ValueError(t("Pasa al menos una foto o un video."))
    p = edicion.nuevo(str(nombre or "")[:80] or t("Mi video"), formato)
    for m in medios[:edicion.MAX_CLIPS]:
        p = edicion.anadir_medio(p, ruta(str(m)))
    if musica:
        p = edicion.anadir_medio(p, ruta(musica), audio=True)
        p["audios"] = musica_de_fondo(p["audios"][-1], edicion.tiempos(p)[-1][1])
        p = edicion.validar(p)
    carpeta = edicion.nueva_carpeta(p["nombre"])
    if subtitulos:
        p["subtitulos"] = {"activos": True, "palabras": render_edicion.subtitulos_automaticos(p, carpeta, _aviso())}
    edicion.guardar(p, carpeta)
    archivo = render_edicion.exportar(p, carpeta, carpeta / "video.mp4", calidad, _aviso())
    return _json({"tipo": "edicion", "formato": p["formato"], "carpeta": str(carpeta), "titulo": p["nombre"],
                  "resultados": [{"archivo": str(archivo), "titulo": p["nombre"], "descripcion": "", "hashtags": []}]})


def crear_serie(titulo: str, idea: str, estilo: str = "Cartoon 2D", personajes: int = 3,
                formato: str = "16:9", biblia: dict | None = None, voz: str = "") -> str:
    """Dibujos animados (serie animada): crea la serie (título, sinopsis) y sus personajes ORIGINALES, cada uno con
    su apariencia fija, su voz y su lámina dibujada. estilo: uno de la lista (Cartoon 2D, Anime 90s (estilo
    samurái), Anime moderno, Animación 3D (tipo Pixar), Cine realista, Cómic) o una descripción propia en inglés.
    personajes: de 1 a 6. Después se hacen los capítulos con crear_episodio. voz: la del narrador, como en crear_video,
    vacía salvo que el usuario pida una; si es de ElevenLabs, los personajes también usan voces de ElevenLabs.

    biblia (opcional): si tú la escribes, no se usa la IA de texto de la app. Forma: {"titulo", "sinopsis",
    "personajes": [{"nombre", "descripcion": apariencia FIJA y concreta en inglés (50-80 palabras), "personalidad",
    "genero": hombre o mujer}]}."""
    return _json(serie.crear_serie(titulo, idea, estilo, personajes, formato, aviso=_aviso(), biblia=biblia,
                                   voz=_voz(voz)))


def crear_episodio(serie_nombre: str, idea: str = "", planos: int = 12, numero: int = 0,
                   guion: dict | None = None, modelo_video: str = "auto") -> str:
    """Dibujos animados (serie animada): escribe y hace en video el capítulo siguiente de una serie (su título o
    nombre, ver listar_series), con los mismos personajes y siguiendo la historia. idea: qué pasa en este capítulo
    (vacío: la IA sigue la historia). planos: de 3 a 40 (unos 5 s cada uno). numero: para rehacer un capítulo que
    ya existe con lo que ya tiene escrito (p. ej. si se acabó la cuota de imágenes a mitad). Tarda varios minutos.

    guion (opcional): si tú lo escribes, no se usa la IA de texto de la app. Forma: {"titulo", "resumen",
    "planos": [{"descripcion": lo que se ve en inglés (lugar, acción, cámara; sin texto), "personajes": [nombres
    que salen], "habla": nombre de quien habla o "Narrador", "texto": lo que dice, 1-2 frases}]}."""
    with claves.por_trabajo(validar_modelo(modelo_video)):
        return _json(serie.crear_episodio(serie_nombre, idea, planos, numero, aviso=_aviso(), guion=guion))


def programar_publicacion(archivo: str, titulo: str, descripcion: str, fecha_hora: str, red: str = "youtube") -> str:
    """Programa un video (ruta de un video local) para que se publique solo a esa hora, aunque el PC esté apagado: se
    sube ya a YouTube como privado con su hora de salida y marcado como hecho con IA. Publica en el canal del
    usuario: úsalo solo si él lo pidió. fecha_hora: ISO 8601, AAAA-MM-DDTHH:MM (sin zona = hora de este PC),
    al menos 15 min en el futuro. red: por ahora solo youtube (se conecta una vez en la página «Publicar» de la app).
    Los #hashtags de la descripción van también como etiquetas. La descripción, hasta {maximo} caracteres."""
    descripcion = str(descripcion or "")[:MAX_DESCRIPCION]  # lo mismo que vio el usuario en la pregunta (director.costo)
    etiquetas = re.findall(r"#(\w+)", descripcion)
    return _json(publicar.programar(ruta(archivo), titulo, descripcion, etiquetas, fecha_hora, red, aviso=_aviso()))


programar_publicacion.__doc__ = programar_publicacion.__doc__.replace("{maximo}", str(MAX_DESCRIPCION))


def recordar_preferencia(departamento: str, preferencia: str) -> str:
    """Memoria del estudio: guarda una preferencia duradera del usuario («títulos cortos», «sin Montserrat», «mi
    marca es X») para que su departamento la siga en todos los trabajos. Úsala cuando corrige algo o dice cómo lo
    quiere siempre. departamento: general (todo el estudio) o uno de {departamentos}. Nunca claves, contraseñas,
    tarjetas ni números de cuenta (se rechazan). El usuario las ve y las borra en «Memoria del estudio»."""
    return _json({"guardada": " ".join(str(preferencia).split()),
                  "memoria": memoria.recordar(departamento, preferencia).get(departamento, [])})


recordar_preferencia.__doc__ = recordar_preferencia.__doc__.replace("{departamentos}", ", ".join(roles.DEPARTAMENTOS))


def listar_series() -> str:
    """Las series de dibujos animados creadas, con sus personajes y capítulos."""
    return _json(serie.listar())


def listar_proyectos() -> str:
    """Lista los proyectos ya creados, del más nuevo al más viejo."""
    return _json(shorts.proyectos())


def listar_opciones() -> str:
    """Formatos, voces y proveedores de IA conectados (sin mostrar las claves)."""
    # solo los de IA: la cuenta de YouTube no sale de este PC (ni a la IA del Director ni al agente MCP). Y sin trozos
    # de la clave ni la región: la IA no los necesita y el resultado viaja a su proveedor (también al gratis)
    return _json({"formatos": list(video.FORMATOS), "voces": desde_prompt.voces(),
                  "generos_musica": list(musica.GENEROS), "estilos_anuncio": list(anuncios.ESTILOS),
                  "estilos_cabina": list(cabina.PRESETS),
                  "proveedores": [{k: v for k, v in c.items() if k not in ("clave", "base")}
                                  for c in claves.publico() if c["proveedor"] in claves.USOS],
                  # sin lo recordado del selector de cada página: no es lo del estudio y un agente lo leería así
                  "por_defecto": {k: v for k, v in claves.ajustes().items() if not k.startswith("modelo_video_")},
                  # lo que vale en modelo_video ahora (lo conectado), con su precio y su estado si no atiende
                  "modelos_video": claves.modelos_video()})


for _f in (crear_video, crear_anuncios, crear_video_musical, crear_episodio):  # las que animan escenas
    # Sin sangría las dos partes: desde Python 3.13 la ayuda ya llega sin ella, y así cada párrafo empieza por su nombre
    _f.__doc__ = f"{inspect.cleandoc(_f.__doc__)}\n\n{AYUDA_MODELO}"

TODAS = {f.__name__: f for f in (crear_video, sacar_shorts, investigar_nichos, crear_anuncios, crear_cancion,
                                 crear_video_musical, producir_cancion, separar_voz_y_pista, crear_diseno,
                                 editar_video, crear_serie, crear_episodio, listar_series, listar_proyectos,
                                 listar_opciones, programar_publicacion, recordar_preferencia)}
# Lo que hace cada herramienta dicho para el usuario: en las ventanas del MCP, el historial de Ráfaga Guardia y el
# progreso del Director se leía «crear_video» o «recordar_preferencia»
NOMBRES = {"crear_video": t("crear un video"), "sacar_shorts": t("sacar shorts de un video"),
           "investigar_nichos": t("investigar nichos virales"), "crear_anuncios": t("crear anuncios"),
           "crear_cancion": t("crear una canción"), "crear_video_musical": t("hacer un video musical"),
           "producir_cancion": t("producir una canción en la cabina"),
           "separar_voz_y_pista": t("separar la voz y la pista de una canción"), "crear_diseno": t("crear un diseño"),
           "editar_video": t("montar un video en el editor"), "crear_serie": t("crear una serie de dibujos animados"),
           "crear_episodio": t("hacer un capítulo de una serie"), "listar_series": t("ver tus series"),
           "listar_proyectos": t("ver tus proyectos"), "listar_opciones": t("ver las opciones del estudio"),
           "programar_publicacion": t("programar una publicación en YouTube"),
           "recordar_preferencia": t("guardar algo en la memoria del estudio")}


def nombre(herramienta: str) -> str:
    return NOMBRES.get(herramienta, herramienta)


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
