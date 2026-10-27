"""Página «Inicio»: el panel con el que abre la app. Arriba, «¿Qué creamos hoy?» con la caja donde se escribe la idea
y se elige dónde crearla; luego lo mejor hecho con el estudio en un carrusel que pasa solo, las herramientas, qué IA
usa el estudio ahora, lo último que hiciste y todos los ejemplos en mosaico."""
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QDateTime, QEvent, QLocale, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QTextCursor
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QPlainTextEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from motor import claves, edicion, idioma, nubes, seguro, serie, shorts
from motor.idioma import t
from ui.comun import boton, etiqueta, REFLEJO, seccion, Segmentos, tarjeta, ver_imagen, ver_video
from ui import legal
from ui.iconos import icono
from ui.paginas import director as pagina_director
from ui.paginas.claves import NOMBRES_PROVEEDOR

ESTILO_INICIO = """
#portada { font-size: 46px; font-weight: 800; color: #FFFFFF; }
#lema { font-size: 17px; color: #A9A9B6; }
#seccion { font-size: 24px; font-weight: 800; color: #FFFFFF; }
#acceso { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.07),
                                      stop:1 rgba(255, 255, 255, 0.025));
          border: 1px solid rgba(255, 255, 255, 0.08); border-top-color: rgba(255, 255, 255, 0.18); border-radius: 18px;
          text-align: left; }
#acceso:hover, #acceso:focus { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.20),
                                                                 stop:1 rgba(124, 92, 255, 0.06));
                               border: 1px solid rgba(124, 92, 255, 0.70); border-top-color: rgba(205, 190, 255, 0.85); }
#acceso:focus { border-left-color: rgba(61, 245, 255, 0.70); border-right-color: rgba(61, 245, 255, 0.70);
                border-bottom-color: rgba(61, 245, 255, 0.70); }
#acceso:pressed { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0, 0, 0, 0.25),
                                              stop:1 rgba(124, 92, 255, 0.14));
                  border-top-color: rgba(0, 0, 0, 0.40); border-bottom-color: rgba(205, 190, 255, 0.60); }
#acceso_titulo { font-size: 17px; font-weight: 700; color: #FFFFFF; }
#acceso QLabel#sub { font-size: 14px; }
#indicador { font-size: 18px; font-weight: 700; color: #FFFFFF; }
#chip { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(150, 125, 255, 0.30),
                                    stop:1 rgba(124, 92, 255, 0.08));
        border: 1px solid rgba(150, 125, 255, 0.30); border-top-color: rgba(222, 212, 255, 0.50); border-radius: 12px; }
#nuevo { font-size: 11px; font-weight: 800; color: #FFFFFF; padding: 1px 8px; border-radius: 9px;
         background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(124, 92, 255, 0.92), stop:1 rgba(214, 52, 112, 0.92));
         border: 1px solid rgba(255, 255, 255, 0.30); }
#novedad { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.09),
                                       stop:1 rgba(255, 255, 255, 0.03));
           border: 1px solid rgba(255, 255, 255, 0.10); border-top-color: rgba(255, 255, 255, 0.24); border-radius: 14px; }
#novedad:hover, #novedad:focus { border-color: rgba(150, 125, 255, 0.60); border-top-color: rgba(214, 202, 255, 0.80); }
#novedad:focus { border-bottom-color: rgba(61, 245, 255, 0.75); }
#idea_caja { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(28, 24, 44, 0.95), stop:1 rgba(13, 12, 18, 0.95));
             border: 1px solid rgba(150, 125, 255, 0.34); border-top-color: rgba(222, 212, 255, 0.55); border-radius: 22px; }
#idea_caja QPlainTextEdit { background: transparent; border: none; font-size: 18px; padding: 0;
                            selection-background-color: rgba(124, 92, 255, 0.50); }
#destino { background: rgba(124, 92, 255, 0.15); border: 1px solid rgba(150, 125, 255, 0.32); border-radius: 14px; }
#destino QLabel { color: #D3C8FF; font-size: 13px; }
#idea_chip { color: #DCDCE6; font-size: 13px; padding: 5px 12px; border-radius: 14px; text-align: left;
             background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
             border-top-color: rgba(255, 255, 255, 0.22); }
#idea_chip:hover { background: rgba(124, 92, 255, 0.22); border-color: rgba(205, 190, 255, 0.60); color: #FFFFFF; }
#idea_chip:focus { border: 1px solid #3DF5FF; }
#pildora { color: #FFFFFF; font-size: 12px; font-weight: 700; padding: 4px 11px; border-radius: 12px;
           background: rgba(15, 15, 19, 0.55); border: 1px solid rgba(255, 255, 255, 0.24); }
#destacado_titulo { font-size: 30px; font-weight: 800; color: #FFFFFF; }
#destacado_frase { font-size: 16px; color: #DCDCE6; }
#flecha { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.10),
                                     stop:1 rgba(255, 255, 255, 0.03));
          border: 1px solid rgba(255, 255, 255, 0.12); border-top-color: rgba(255, 255, 255, 0.30); border-radius: 19px; }
#flecha:hover { background: rgba(124, 92, 255, 0.50); border-color: rgba(205, 190, 255, 0.75); }
#flecha:focus { border: 2px solid #3DF5FF; }
#punto { background: rgba(255, 255, 255, 0.26); border: none; border-radius: 4px; }
#punto:hover { background: rgba(255, 255, 255, 0.50); }
#punto:checked { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8C6CFF, stop:1 #FF4D8D); }
"""
# El reflejo de arriba, como las tarjetas de ESTILO: esta hoja gana siempre a la de la app, así que va aquí (después de
# «background:», que lo borraría); al pasar el ratón se cambia solo «background-color» y al pulsar se va a propósito
ESTILO_INICIO += f"#acceso, #novedad {{ {REFLEJO} }}"

# Las herramientas, en el orden del menú: (icono, color, nombre, frase, página del menú a la que lleva, sin traducir
# como PAGINA del Director; ejemplos para su vista, el primero que exista; si trae algo nuevo). Sus vistas no repiten
# las primeras piezas del carrusel (Crear video enseña la manzana, su video con voz); Shorts mágicos no tiene
# aún un short vertical de muestra: lleva su dibujo
ACCESOS = [
    ("bot", "#B79CFF", t("Director IA"), t("Pídelo con tus palabras y la IA hace todo el trabajo"), "Director IA",
     ("mascota-rafa",), False),
    ("sparkles", "#FF4D8D", t("Crear video"), t("De una idea a un video con guion, voz e imágenes, ahora también con "
                                                "Kling y Seedance"), "Crear con IA", ("manzana-habla",), True),
    ("palette", "#7CFFB2", t("Diseño"), t("Miniaturas, posts, flyers y logos con tu marca"),
     "Diseño", ("estampado-calavera-neon", "flyer-noche-neon"), False),
    ("rabbit", "#FF8A5C", t("Dibujos animados"), t("Crea tus personajes y capítulos de caricatura"),
     "Dibujos animados", ("rafa-y-la-ciudad", "miniatura-leyenda", "leyenda-rafaga"), False),
    ("scissors", "#5CA8FF", t("Editor de video"), t("Corta, une, subtitula, grábate hablando encima y exporta en 4K"),
     "Editor de video", ("presentacion-app",), True),
    ("zap", "#FFB454", t("Shorts mágicos"), t("Los mejores momentos de un video largo, listos para subir"),
     "Shorts mágicos", (), False),
    ("megaphone", "#00E5FF", t("Anuncios"), t("Anuncios para tu negocio en un par de minutos"), "Anuncios",
     ("anuncio-cafe-brisa-alta", "anuncio-rafaga"), False),
    ("music", "#F472B6", t("Música"), t("Canciones y videos musicales con IA"), "Música", ("portada-alto-voltaje",),
     False),
]
# Ideas de ejemplo dentro de la caja, como las opciones de la de Pollo AI: (nombre corto, opción del selector, la idea
# que dejan escrita). No empiezan nada: solo rellenan la caja
IDEAS = [
    (t("Tráiler de anime"), "video",
     t("El tráiler de una serie anime: un guerrero caribeño que busca a los siete que lo traicionaron")),
    (t("Anuncio de café"), "diseno",
     t("Un anuncio para Instagram de mi café de montaña, con la taza humeante y el botón «Pídelo hoy»")),
    (t("Canción de dembow"), "musica", t("Una canción de dembow alegre sobre salir con los amigos el viernes")),
    (t("Dibujos animados"), "director",
     t("Una serie animada de tres capítulos sobre una niña y su perro en Santo Domingo")),
]
# El selector de la caja de arriba: (clave, nombre, icono, página del menú donde se escribe la idea, sin traducir)
MODOS = [("video", t("Video"), "clapperboard", "Crear con IA"), ("imagen", t("Imagen"), "image", "Diseño"),
         ("diseno", t("Diseño"), "palette", "Diseño"), ("musica", t("Música"), "music", "Música"),
         ("director", t("Director"), "bot", "Director IA")]
# «Lo que puedes crear»: lo mejor del estudio, en este orden. Solo movimiento de verdad (los videos hechos pegando
# fotos no salen) y las mejores piezas de diseño. (id del ejemplo, etiqueta, título, frase); sin su archivo, no sale.
DESTACADOS = [
    ("manzana-habla", t("Video con voz"), t("La manzana que habla"),
     t("Una frase bastó: guion, escenas, su propia voz y los labios sincronizados")),
    ("leyenda-ia", t("Movimiento con IA"), t("La leyenda de Ráfaga"),
     t("El viento, el mar y la espada se mueven de verdad")),
    ("baile-merengue", t("Movimiento con IA"), t("Merengue en la calle"),
     t("Ella gira, la falda vuela y las palmeras se mecen: movimiento real hecho con IA")),
    ("anuncio-rafaga", t("Anuncio"), t("Tu PC. Tu estudio."), t("El anuncio de Ráfaga Studio, hecho con Ráfaga Studio")),
    ("leyenda-rafaga", t("Tráiler de anime"), t("Un anime con personajes propios"),
     t("Un guerrero caribeño, siete traidores y una isla en plena tormenta")),
    ("mascota-rafa", t("Diseño en 4K"), t("Rafa, la mascota del estudio"),
     t("Dibujado con el diseñador de Ráfaga Studio")),
    ("portada-alto-voltaje", t("Portada de álbum"), t("Alto Voltaje"), t("Neón morado y cian para un disco de dembow")),
    ("flyer-noche-neon", t("Flyer"), t("Noche Neón"), t("Fecha, hora y lugar, listo para compartir")),
    ("miniatura-capitulo-2", t("Miniatura de YouTube"), t("La leyenda de Ráfaga, capítulo 2"),
     t("Una miniatura que da ganas de hacer clic")),
    ("logo-barberia-el-rey", t("Logo"), t("Barbería El Rey"), t("Corona dorada y tijeras: elegante y oscuro")),
    ("estampado-calavera-neon", t("Estampado"), t("Calavera neón"), t("Listo para imprimir en una camiseta negra")),
    ("anuncio-cafe-brisa-alta", t("Anuncio de producto"), t("Café Brisa Alta"),
     t("Un anuncio de producto listo para Instagram")),
]
# Lo reciente: el icono y el nombre de cada tipo (el «tipo» de proyecto.json, o «edicion» y «serie»)
TIPOS = {"shorts": ("zap", "Shorts"), "anuncio": ("megaphone", t("Anuncios")), "musica": ("music", t("Música")),
         "videomusical": ("clapperboard", t("Video musical")), "cabina": ("mic", t("Cabina")),
         "separacion": ("scissors", t("Separación")), "animacion": ("image", t("Animación")),
         "edicion": ("scissors", t("Editor de video")), "serie": ("rabbit", t("Dibujos animados"))}
# Qué conviene conectar para cada uso: mientras no haya ninguna de estas claves, su indicador ofrece «Conectar»
CONVIENE = {"texto": ("anthropic", "gemini", "groq", "openai"), "imagen": ("cloudflare",),
            "video": ("modal",)}  # Hugging Face no: su token no da más cuota de animar (nubes.llamar_space)
ANCHO_MAX = 1440  # en pantallas anchas el contenido no se estira más: se centra


def _lista(funcion) -> list:
    """Lo que devuelva la lista de un módulo; si revienta por un archivo raro, nada: Inicio no puede romperse por eso."""
    try:
        return funcion()
    except Exception:
        traceback.print_exc()
        return []


def _fecha_carpeta(carpeta) -> float:
    """Fecha de un video por el nombre de su carpeta (AAAAMMDD-HHMMSS-…). Sin tocar el disco: la ruta viene del
    proyecto.json y podría ser una carpeta de red."""
    try:
        return time.mktime(time.strptime(Path(str(carpeta)).name[:15], "%Y%m%d-%H%M%S"))
    except (ValueError, OverflowError):
        return 0.0


def _tocado(*rutas) -> float:
    """La última vez que se tocó alguna de estas rutas (las de la lista de cada módulo, de este PC); 0 si ninguna."""
    fechas = [0.0]
    for ruta in rutas:
        try:
            fechas.append(Path(ruta).stat().st_mtime)
        except (OSError, ValueError):
            pass
    return max(fechas)


def _resultados(p: dict) -> list[dict]:
    """Los videos de un proyecto con los campos que espera el Reproductor. Lo que no es de este PC o viene mal, fuera."""
    limpios = []
    for r in p["resultados"]:
        archivo = r.get("archivo") if isinstance(r, dict) else None
        # is_file detrás: una ruta de red no se toca nunca (Windows mandaría tu usuario a ese servidor)
        if (isinstance(archivo, str) and archivo.strip() and not seguro.es_ruta_de_red(archivo)
                and Path(archivo).is_file()):  # un video borrado no sale (el reproductor quedaría en negro)
            hashtags = r.get("hashtags") if isinstance(r.get("hashtags"), list) else []
            limpios.append({"archivo": archivo, "titulo": str(r.get("titulo") or "")[:200],
                            "descripcion": str(r.get("descripcion") or ""),
                            "hashtags": [h for h in hashtags if isinstance(h, str)]})
    return limpios


def recientes(maximo: int = 6) -> list[dict]:
    """Lo último que se tocó (videos, ediciones y series), del más nuevo al más viejo; lo roto se salta. Cada uno:
    {"tipo", "titulo", "fecha", "accion": "ver" | "editar" | "serie", "dato": lo que necesita esa acción}."""
    lista = []
    for p in _lista(shorts.proyectos):
        resultados = _resultados(p)
        if resultados:
            tipo = p.get("tipo") if isinstance(p.get("tipo"), str) else ""
            lista.append({"tipo": tipo, "titulo": str(p.get("titulo") or resultados[0]["titulo"])[:120],
                          "fecha": _fecha_carpeta(p.get("carpeta")), "accion": "ver",
                          "dato": {"formato": str(p.get("formato") or "9:16"), "resultados": resultados}})
    for e in _lista(lambda: edicion.listar(maximo)):  # solo valida los más nuevos: con muchos, Inicio se congelaba
        lista.append({"tipo": "edicion", "titulo": e["nombre"], "fecha": _tocado(Path(e["carpeta"]) / "proyecto.json"),
                      "accion": "editar", "dato": e["carpeta"]})
    for s in _lista(serie.listar):
        lista.append({"tipo": "serie", "titulo": s["titulo"], "accion": "serie", "dato": s["nombre"],
                      "fecha": _tocado(Path(s["carpeta"]) / "serie.json", *(e["carpeta"] for e in s["episodios"]))})
    return sorted(lista, key=lambda r: r["fecha"], reverse=True)[:maximo]


def indicadores() -> list[dict]:
    """Qué IA usa ahora el estudio para cada cosa y el uso de hoy: {"icono", "titulo", "valor", "detalle",
    "conectar"} («conectar»: falta una clave que ayudaría; el detalle dice cuál)."""
    conectadas = claves.cargar()
    falta = {uso: not any(p in conectadas for p in utiles) for uso, utiles in CONVIENE.items()}
    texto = claves.para("texto")
    video = claves.ajustes().get("video", "auto")
    video = video if video == "ninguno" else (nubes.orden("video") or ["ninguno"])[0]
    imagen = nubes.orden("imagen")[0]
    de_pago = {p for lista in claves.SOLO_ELIGIENDO.values() for p in lista}  # lo pagado no es «uso gratis»
    hoy = {k: v for k, v in nubes.resumen_hoy().items()
           if isinstance(v, int) and v > 0 and k not in de_pago}  # el archivo se puede tocar
    return [
        {"icono": "message-square-text", "titulo": t("IA de texto"), "conectar": falta["texto"],
         "valor": NOMBRES_PROVEEDOR.get(texto["proveedor"], str(texto["proveedor"]).capitalize()) if texto
         else t("IA gratis sin clave (lenta)"),
         "detalle": t("Conecta Gemini, Claude o Groq: guiones más rápidos y mejores") if falta["texto"]
         else str((texto or {}).get("modelo_texto") or "")[:60]},
        {"icono": "image", "titulo": t("Imágenes"), "conectar": falta["imagen"],
         "valor": nubes.NOMBRES.get(imagen, imagen),
         "detalle": t("Conecta Cloudflare (gratis): unas 100 imágenes buenas al día") if falta["imagen"] else ""},
        {"icono": "clapperboard", "titulo": t("Video con IA"), "conectar": falta["video"] and video not in de_pago,
         "valor": NOMBRES_PROVEEDOR["ninguno"] if video == "ninguno" else nubes.NOMBRES.get(video, video),
         "detalle": t("Cada escena animada se paga: la app te dice el costo antes de cada trabajo") if video in de_pago
         else t("Conecta Modal para seguir animando cuando se acabe la cuota gratis del día") if falta["video"] else ""},
        {"icono": "gauge", "titulo": t("Uso gratis de hoy"), "conectar": False,
         "valor": t("{n} creaciones", n=sum(hoy.values())) if hoy else t("Aún nada hoy"),
         "detalle": "  ·  ".join(f"{nubes.NOMBRES.get(k, k)}: {v}" for k, v in hoy.items())[:200]},
    ]


def _saludo() -> str:
    hora = time.localtime().tm_hour
    return t("¡Buenos días!") if 5 <= hora < 12 else t("¡Buenas tardes!") if 12 <= hora < 20 else t("¡Buenas noches!")


def _chip(nombre_icono, color="#C9B8FF", lado=40) -> QLabel:
    """El icono dentro de su cuadrito de vidrio violeta."""
    chip = QLabel()
    chip.setObjectName("chip")
    chip.setFixedSize(lado, lado)
    chip.setAlignment(Qt.AlignCenter)
    chip.setPixmap(icono(nombre_icono, color).pixmap(lado // 2, lado // 2))
    return chip


def _transparentes(*widgets):
    for w in widgets:
        w.setAttribute(Qt.WA_TransparentForMouseEvents)  # el clic y el hover son de la tarjeta entera


def _tarjeta_boton(nombre: str, frase: str) -> QPushButton:
    """Una tarjeta pulsable de vidrio (#acceso) que se ilumina al pasar el ratón (ver ESTILO_INICIO)."""
    b = QPushButton()
    b.setObjectName("acceso")
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.TabFocus)  # como boton(): al volver a Inicio no se queda iluminada la que se pulsó
    b.setAccessibleName(nombre)
    b.setAccessibleDescription(frase)
    b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)  # un botón es de alto fijo: cortaría el texto largo
    return b


def _pulsable(nombre_icono, color, titulo, texto, al_pulsar) -> QPushButton:
    """Lo reciente: su icono en el cuadrito, el título y de qué tipo es y cuándo."""
    b = _tarjeta_boton(titulo, texto)
    fila = QHBoxLayout(b)
    fila.setContentsMargins(16, 14, 16, 14)
    fila.setSpacing(14)
    textos = QVBoxLayout()
    textos.setSpacing(2)
    chip, nombre, sub = _chip(nombre_icono, color), etiqueta(titulo, "acceso_titulo"), etiqueta(texto, "sub")
    _transparentes(chip, nombre, sub)
    textos.addWidget(nombre)
    textos.addWidget(sub)
    fila.addWidget(chip, 0, Qt.AlignTop)
    fila.addLayout(textos, 1)
    b.clicked.connect(al_pulsar)
    return b


class _Portada(QWidget):
    """La cabecera de Inicio, con la luz de la marca detrás de la caja de la idea (la de Pollo AI es naranja; la
    nuestra, violeta y rosa)."""
    caja = None

    def paintEvent(self, _):
        if self.caja is None:
            return
        c = QRectF(self.caja.geometry())
        ancho, alto = c.width() * 0.62, c.height() * 1.25
        luz = QRadialGradient(0, 0, ancho)
        luz.setColorAt(0, QColor(124, 92, 255, 105))
        luz.setColorAt(0.5, QColor(214, 52, 112, 38))
        luz.setColorAt(1, QColor(124, 92, 255, 0))
        p = QPainter(self)
        p.translate(QPointF(c.center().x(), c.top() + c.height() * 0.15))
        p.scale(1, alto / ancho)  # una elipse ancha y baja que asoma por arriba y por los lados de la caja
        p.fillRect(QRectF(-ancho, -ancho, 2 * ancho, 2 * ancho), luz)


class _Idea(QPlainTextEdit):
    """La caja de la idea: Intro la manda (Mayúsculas+Intro, otra línea) y Tab sale de ella, como en un formulario."""
    enviar = Signal()

    def __init__(self):
        super().__init__()
        self.setTabChangesFocus(True)  # si no, el Tab se escribe y el teclado queda atrapado aquí

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not e.modifiers() & Qt.ShiftModifier:
            return self.enviar.emit()
        super().keyPressEvent(e)


class _Ideas(QWidget):
    """Las ideas de ejemplo de la caja, en fila: las que no caben se esconden (a 1280 px, o en francés, no caben
    todas y la caja no puede crecer más que la página)."""
    HUECO = 8

    def __init__(self, botones: list):
        super().__init__()
        self.botones = botones
        for b in botones:
            b.setParent(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        anchos = [b.sizeHint().width() for b in self.botones]
        return QSize(sum(anchos) + self.HUECO * max(0, len(anchos) - 1),
                     max((b.sizeHint().height() for b in self.botones), default=0))

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def resizeEvent(self, e):
        x, cabe = 0, True
        for b in self.botones:
            tam = b.sizeHint()
            cabe = cabe and x + tam.width() <= self.width()  # en orden: si una no cabe, tampoco las de detrás
            b.setVisible(cabe)
            if cabe:
                b.setGeometry(x, (self.height() - tam.height()) // 2, tam.width(), tam.height())
                x += tam.width() + self.HUECO
        super().resizeEvent(e)


class Destacados(QWidget):
    """«Lo que puedes crear»: un carrusel grande que pasa solo de una pieza a la siguiente (cada PASO ms, deslizándose),
    con la siguiente asomando a la derecha, flechas y puntos. Se para con el ratón encima, con el foco del teclado
    dentro, con la página oculta o la ventana sin foco, y con «Animar vistas previas» apagada (menos movimiento:
    entonces tampoco se desliza, salta). La elegida reproduce su MP4 mudo cuando termina de deslizarse; las demás,
    quietas y un poco más oscuras. De los videos se ve solo lo de arriba (sin sus subtítulos quemados: el título de la
    tarjeta va encima) y los diseños van enteros a la derecha, porque traen su propia tipografía."""
    PASO = 6000
    HUECO = 16

    def __init__(self, piezas: list):
        super().__init__()
        self.piezas, self.actual, self.ancho = piezas, 0, 0
        contenido = QWidget()
        fila = QHBoxLayout(contenido)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(self.HUECO)
        for b in piezas:
            b.contener = True
            b.installEventFilter(self)
            fila.addWidget(b)
        self.pista = pagina_director.Carrusel(contenido, 380)
        self.pista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # se mueve con las flechas y los puntos
        self.pista.wheelEvent = lambda e: e.ignore()  # la rueda baja la página: el carrusel no la atrapa
        self.pista.animacion.setDuration(550)
        # Al cambiar de tamaño, la fila crece después (en su layout): hasta entonces la barra no llega a la pieza
        self.pista.horizontalScrollBar().rangeChanged.connect(lambda *_: self._colocar())
        self.pista.animacion.finished.connect(self._colocar)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.addWidget(self.pista)
        # Debajo: ‹ los puntos ›. Encima de las tarjetas, las flechas tapaban los títulos de dos líneas
        abajo = QHBoxLayout()
        abajo.setSpacing(7)
        abajo.addStretch()
        self.flechas, self.puntos = [], []
        for nombre, sentido, texto in (("chevron-left", -1, t("Anterior")), ("chevron-right", 1, t("Siguiente"))):
            flecha = QPushButton()
            flecha.setObjectName("flecha")
            flecha.setIcon(icono(nombre))
            flecha.setIconSize(QSize(20, 20))
            flecha.setFixedSize(40, 40)
            flecha.setCursor(Qt.PointingHandCursor)
            flecha.setFocusPolicy(Qt.TabFocus)
            flecha.setToolTip(texto)
            flecha.setAccessibleName(texto)
            flecha.clicked.connect(lambda _=False, s=sentido: self.ir(self.actual + s))
            self.flechas.append(flecha)
        abajo.addWidget(self.flechas[0])
        abajo.addSpacing(10)
        for n, b in enumerate(piezas):
            punto = QPushButton()
            punto.setObjectName("punto")
            punto.setCheckable(True)
            punto.setFixedSize(8, 8)
            punto.setCursor(Qt.PointingHandCursor)
            punto.setFocusPolicy(Qt.NoFocus)  # con el teclado se pasa por las flechas y las propias tarjetas
            punto.setAccessibleName(t("Ver «{titulo}»", titulo=b.accessibleName()))
            punto.clicked.connect(lambda _=False, n=n: self.ir(n))
            self.puntos.append(punto)
            abajo.addWidget(punto)
        abajo.addSpacing(10)
        abajo.addWidget(self.flechas[1])
        abajo.addStretch()
        lay.addLayout(abajo)
        for w in self.flechas + self.puntos:
            w.setVisible(len(piezas) > 1)
        self.reloj = QTimer(self)
        self.reloj.setInterval(self.PASO)
        self.reloj.timeout.connect(self._tic)
        self.reloj.start()
        self._marcar()

    def showEvent(self, e):
        self.reloj.start()  # el primer paso cuenta desde que se ve, no desde que se armó la página
        super().showEvent(e)

    def hideEvent(self, e):
        self.reloj.stop()  # oculto (otra página del menú), su reloj no sigue andando
        super().hideEvent(e)

    def deslizando(self) -> bool:
        return self.pista.animacion.state() == QPropertyAnimation.Running

    def quieto(self) -> bool:
        """Si el carrusel no debe pasar solo ahora."""
        foco = QApplication.focusWidget()
        return (len(self.piezas) < 2 or not pagina_director.accion_animar().isChecked() or self.underMouse()
                or self.visibleRegion().isEmpty() or not self.window().isActiveWindow()
                or (foco is not None and self.isAncestorOf(foco)))

    def _tic(self):
        if not self.quieto():
            self.ir(self.actual + 1)

    def ir(self, n: int, animado: bool = True):
        """A la pieza n (da la vuelta al final), deslizándose salvo con «Animar vistas previas» apagada."""
        if not self.piezas:
            return
        antes = self.piezas[self.actual]
        if n % len(self.piezas) != self.actual and antes.jugador:
            antes.jugador.pause()  # deja de mandar cuadros mientras se desliza; la vigilancia la cierra después
        self.actual = n % len(self.piezas)
        x = self.actual * (self.ancho + self.HUECO)
        if animado and pagina_director.accion_animar().isChecked():
            self.pista.deslizar(x)
        else:
            self.pista.animacion.stop()
            self.pista.horizontalScrollBar().setValue(x)
        self.reloj.start()  # el siguiente paso cuenta desde aquí: un clic no queda pisado por el reloj enseguida
        self._marcar()

    def _colocar(self):
        """Sin deslizarse, en la pieza elegida (si no se está deslizando ya hacia ella); quieta ya, puede abrir su
        video."""
        if not self.deslizando():
            self.pista.horizontalScrollBar().setValue(self.actual * (self.ancho + self.HUECO))
            if self.piezas:
                elegida = self.piezas[self.actual]
                elegida.vivo = "video"
                if elegida.jugador:  # se volvió a ella antes de que la vigilancia la cerrara: sigue donde iba
                    elegida.jugador.play()

    def _marcar(self):
        """La elegida, encendida y con su punto largo. Su MP4 se abre al terminar de deslizarse (_colocar): abrirlo
        cuesta 100-200 ms del hilo de la ventana y, a mitad del deslizamiento, daba un tirón."""
        quieta = not self.deslizando()
        for n, (b, punto) in enumerate(zip(self.piezas, self.puntos)):
            elegida = n == self.actual
            b.vivo = "video" if elegida and quieta else None
            if b.apagada == elegida:
                b.apagada = not elegida
                b.update()
            punto.setChecked(elegida)
            punto.setFixedWidth(26 if elegida else 8)

    def eventFilter(self, b, e):
        if b in self.piezas:
            if e.type() == QEvent.FocusIn:  # con Tab se llega a una tarjeta: el carrusel va a ella
                self.ir(self.piezas.index(b))
            elif e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Left, Qt.Key_Right):
                self.piezas[(self.piezas.index(b) + (1 if e.key() == Qt.Key_Right else -1)) % len(self.piezas)].setFocus()
                return True
        return False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        ancho = self.width()
        self.ancho = ancho if len(self.piezas) < 2 else round(ancho * 0.8)  # la siguiente asoma por la derecha
        alto = max(300, min(470, round(self.ancho * 0.5)))
        self.pista.setFixedHeight(alto)
        for b in self.piezas:
            b.setFixedSize(self.ancho, alto)
            caja = b.caja()  # el texto, a la izquierda de la foto que va entera
            margen = round(alto * 0.07)
            derecha = round(self.ancho - caja.left() + margen) if caja is not None else round(self.ancho * 0.3)
            b.layout().setContentsMargins(margen, margen, derecha, margen)
        self.pista.animacion.stop()
        self._colocar()


class PaginaInicio(QWidget):
    def __init__(self, ir, abrir_edicion, abrir_serie, usar_pedido=None, pedir=None):
        """ir(nombre del menú, sin traducir) cambia de página; abrir_edicion(carpeta) y abrir_serie(nombre) abren lo
        reciente en su página; usar_pedido(pedido) lleva el de un ejemplo al Director; pedir(modo, texto) lleva lo
        escrito arriba a su página, escrito y sin empezar. Las páginas no se conocen: lo une app.py."""
        super().__init__()
        self.ir, self.abrir_edicion, self.abrir_serie, self.pedir = ir, abrir_edicion, abrir_serie, pedir
        self.recientes = []
        self.setStyleSheet(ESTILO_INICIO)
        self.lay = lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 28)
        lay.setSpacing(16)
        lay.addWidget(self._portada())
        hechos = {e["id"]: (e, self._ver_ejemplo) for e in pagina_director.ejemplos()}
        hechos |= {d["id"]: (d, self._ver_diseno) for d in pagina_director.disenos()}
        self.destacados = Destacados([self._destacada(*hechos[i], *textos, usar_pedido)
                                      for i, *textos in DESTACADOS if i in hechos])
        self.bloque_destacados = self._bloque(seccion(t("Lo que puedes crear"),
                                                      t("Lo mejor que ha salido del estudio, hecho de verdad con él")),
                                              self.destacados)
        self.bloque_destacados.setVisible(bool(self.destacados.piezas))
        lay.addWidget(self.bloque_destacados)
        herramientas = self._rejilla(4)
        self.vistas = []
        for n, (nombre_icono, color, nombre, frase, pagina, ids, nuevo) in enumerate(ACCESOS):
            # un ejemplo de la galería o, si no lo es (el video de presentación, hecho con el editor), su foto suelta
            ejemplo = next((hechos[i][0] if i in hechos else {"id": i} for i in ids
                            if i in hechos or (pagina_director.EJEMPLOS / f"{i}.jpg").is_file()), None)
            herramientas.addWidget(self._herramienta(nombre_icono, color, nombre, frase, ejemplo,
                                                     bool(ejemplo) and ejemplo["id"] in hechos, nuevo,
                                                     lambda _, p=pagina: self.ir(p)), n // 4, n % 4)
        lay.addWidget(self._bloque(seccion(t("Herramientas"), t("Todo tu estudio creativo en un solo lugar")),
                                   herramientas))
        self.estudio = self._rejilla(4)
        lay.addWidget(self._bloque(seccion(t("Tu estudio hoy"), t("Qué IA trabaja para ti ahora mismo")),
                                   self.estudio))
        self.ultimos = self._rejilla(3)
        self.vacio = etiqueta(t("Aún no hay nada por aquí. Escribe tu idea arriba o elige una herramienta y lo verás "
                                "aquí."), "sub")
        lay.addWidget(self._bloque(seccion(t("Tus proyectos"), t("Continuar donde lo dejaste")), self.ultimos,
                                   self.vacio))
        self.galeria = pagina_director.galeria_ejemplos(self, self._ver_ejemplo, usar_pedido, seccion_de_inicio=True)
        lay.addSpacing(30)
        lay.addWidget(self.galeria)
        lay.addStretch()
        lay.addWidget(etiqueta(f"{legal.marca()}  ·  {t('Tus proyectos se guardan en tu PC.')}", "sub"))
        # Una sola cuenta de decodificadores para toda la página: como mucho MAX_VIVAS se mueven a la vez. Mientras el
        # carrusel se desliza no se abre ni se cierra ninguno (cada uno cuesta su rato del hilo de la ventana)
        self.piezas = self.destacados.piezas + self.vistas + self.galeria.tarjetas
        self.vigia = pagina_director.vigilar(self, self.piezas, espera=self.destacados.deslizando)
        QTimer.singleShot(300, pagina_director.calentar)

    @staticmethod
    def _bloque(*partes) -> QWidget:
        """Una sección (su cabecera y lo que lleva), con aire arriba para separarla de la anterior."""
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 30, 0, 0)
        lay.setSpacing(16)
        for parte in partes:
            (lay.addLayout if isinstance(parte, QGridLayout) else lay.addWidget)(parte)
        return caja

    @staticmethod
    def _rejilla(columnas: int) -> QGridLayout:
        """Rejilla de columnas iguales, aunque una fila no se llene."""
        rejilla = QGridLayout()
        rejilla.setSpacing(14)
        for c in range(columnas):
            rejilla.setColumnStretch(c, 1)
        return rejilla

    def resizeEvent(self, e):
        margen = max(32, (self.width() - ANCHO_MAX) // 2)  # en pantallas anchas, centrado
        if self.lay.contentsMargins().left() != margen:
            self.lay.setContentsMargins(margen, 12, margen, 28)
        super().resizeEvent(e)

    # ---------- Arriba: ¿Qué creamos hoy? ----------

    def _portada(self) -> QWidget:
        """Compacta: a 1280×720 tiene que asomar casi media tarjeta del carrusel sin bajar la página."""
        portada = _Portada()
        lay = QVBoxLayout(portada)
        lay.setContentsMargins(0, 6, 0, 4)
        lay.setSpacing(10)
        # La novedad, como el aviso de arriba de Pollo AI: lleva a Ráfaga Guardia
        novedad = QPushButton()
        novedad.setObjectName("novedad")
        novedad.setCursor(Qt.PointingHandCursor)
        novedad.setFocusPolicy(Qt.TabFocus)
        texto_novedad = t("Ráfaga Guardia cuida tu estudio mientras creas")
        novedad.setAccessibleName(f"{t('Nuevo')}: {texto_novedad}")
        fila = QHBoxLayout(novedad)
        fila.setSizeConstraint(QLayout.SetMinimumSize)  # el ancho de un botón no cuenta su fila: sin esto se encogía
        fila.setContentsMargins(6, 6, 14, 6)
        fila.setSpacing(8)
        pildora, escudo, texto = etiqueta(t("Nuevo"), "nuevo"), QLabel(), etiqueta(texto_novedad)
        pildora.setText(pildora.text().upper())
        escudo.setPixmap(icono("shield-check", "#7CFFB2").pixmap(16, 16))
        texto.setWordWrap(False)
        texto.setStyleSheet("font-size: 14px; color: #DCDCE6;")
        flecha = QLabel()
        flecha.setPixmap(icono("chevron-right", "#A9A9B6").pixmap(14, 14))
        for w in (pildora, escudo, texto, flecha):
            _transparentes(w)
            fila.addWidget(w)
        novedad.clicked.connect(lambda: self.ir("Ráfaga Guardia"))
        lay.addWidget(novedad, 0, Qt.AlignHCenter)
        self.saludo = etiqueta(_saludo(), "lema")
        titulo = etiqueta(t("¿Qué creamos hoy?"), "portada")
        lema = etiqueta(t("Video, imágenes, diseño y música con IA, en tu PC. Escribe tu idea y elige dónde crearla."),
                        "lema")
        for w in (self.saludo, titulo, lema):
            w.setAlignment(Qt.AlignHCenter)
            lay.addWidget(w)
        self.modos = Segmentos()
        self.modos.layout().insertStretch(0)  # centrado (su luz se pinta debajo de la elegida igual)
        for n, (_, nombre, _, _) in enumerate(MODOS):
            self.modos.opcion(nombre, n).setChecked(n == 0)
        self.modos.grupo.idClicked.connect(lambda _: self._modo())
        lay.addWidget(self.modos)
        caja = QFrame()
        caja.setObjectName("idea_caja")
        caja.setMaximumWidth(880)
        dentro = QVBoxLayout(caja)
        dentro.setContentsMargins(24, 16, 18, 14)
        dentro.setSpacing(8)
        self.idea = _Idea()
        self.idea.setPlaceholderText(t("Describe tu idea…"))
        self.idea.setAccessibleName(t("Describe tu idea"))
        self.idea.setFixedHeight(52)
        self.idea.enviar.connect(self._crear)
        dentro.addWidget(self.idea)
        abajo = QHBoxLayout()
        abajo.setSpacing(12)
        destino = QFrame()
        destino.setObjectName("destino")
        en_destino = QHBoxLayout(destino)
        en_destino.setContentsMargins(10, 4, 12, 4)
        en_destino.setSpacing(6)
        self.destino_icono, self.destino = QLabel(), QLabel()
        en_destino.addWidget(self.destino_icono)
        en_destino.addWidget(self.destino)
        abajo.addWidget(destino)
        # Las ideas de ejemplo llenan la caja como las opciones de la de Pollo AI; «se escribe allí y tú decides»
        # pasa al botón (su ayuda y su descripción)
        chips = []
        for nombre, modo, idea in IDEAS:
            chip = QPushButton(nombre)
            chip.setObjectName("idea_chip")
            chip.setIcon(icono(next(m[2] for m in MODOS if m[0] == modo), "#C9B8FF"))
            chip.setIconSize(QSize(14, 14))
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFocusPolicy(Qt.TabFocus)
            chip.setToolTip(idea)
            chip.setAccessibleName(t("Idea: {nombre}", nombre=nombre))
            chip.setAccessibleDescription(idea)
            chip.clicked.connect(lambda _=False, modo=modo, idea=idea: self._poner_idea(modo, idea))
            chips.append(chip)
        self.ideas = _Ideas(chips)
        abajo.addWidget(self.ideas, 1)
        self.crear = boton(f"✨  {t('Crear')}", "principal")
        aviso = t("Se escribe allí y tú decides cuándo empezar")
        self.crear.setToolTip(f"{t('Lleva tu idea a su página (Intro)')}\n{aviso}")
        self.crear.setAccessibleDescription(aviso)
        self.crear.clicked.connect(self._crear)
        abajo.addWidget(self.crear)
        dentro.addLayout(abajo)
        centro = QHBoxLayout()
        centro.addWidget(caja)
        lay.addLayout(centro)
        portada.caja = caja
        self._modo()
        return portada

    def _modo(self):
        """El chip de la caja dice a qué página va la idea con la opción elegida."""
        _, _, nombre_icono, pagina = MODOS[self.modos.grupo.checkedId()]
        self.destino_icono.setPixmap(icono(nombre_icono, "#D3C8FF").pixmap(15, 15))
        self.destino.setText(t("Se abre en {pagina}", pagina=t(pagina)))

    def _poner_idea(self, modo: str, idea: str):
        """Una idea de ejemplo: la deja escrita en la caja, con su opción elegida, para cambiarla y pulsar «Crear»."""
        self.modos.grupo.button(next(n for n, m in enumerate(MODOS) if m[0] == modo)).setChecked(True)
        self._modo()
        self.idea.setPlainText(idea)
        self.idea.moveCursor(QTextCursor.End)
        self.idea.setFocus()

    def _crear(self):
        """Lleva lo escrito a la página de la opción elegida, escrito y sin empezar: un trabajo puede gastar cuota o
        dinero, y eso lo decide el usuario en esa página (primero lo gratis)."""
        texto = self.idea.toPlainText().strip()
        if not texto:
            return self.idea.setFocus()
        if self.pedir:
            self.idea.clear()
            self.pedir(MODOS[self.modos.grupo.checkedId()][0], texto)

    # ---------- Lo que puedes crear y las herramientas ----------

    def _destacada(self, e: dict, abrir, etiqueta_tipo: str, titulo: str, frase: str, usar_pedido) -> QWidget:
        """Una pieza del carrusel: su video (o su diseño) a sangre o entero a la derecha, y encima, abajo a la
        izquierda, su tipo, su título, su frase y sus botones."""
        b = pagina_director.Pieza(e, leyenda=True)
        b.setAccessibleName(titulo)
        b.setAccessibleDescription(frase)
        b.clicked.connect(lambda: abrir(e))
        lay = QVBoxLayout(b)
        lay.setSpacing(6)
        tipo = etiqueta(etiqueta_tipo.upper(), "pildora")
        tipo.setWordWrap(False)
        nombre, linea = etiqueta(titulo, "destacado_titulo"), etiqueta(frase, "destacado_frase")
        _transparentes(tipo, nombre, linea)
        lay.addWidget(tipo, 0, Qt.AlignLeft)
        lay.addStretch()
        lay.addWidget(nombre)
        lay.addWidget(linea)
        lay.addSpacing(8)
        botones = QHBoxLayout()
        botones.setSpacing(10)
        ver = boton(f"▶  {t('Ver video')}" if b.video else f"🔍  {t('Ver en grande')}")
        ver.clicked.connect(lambda: abrir(e))
        botones.addWidget(ver)
        if usar_pedido and e.get("pedido"):
            usar = boton(f"✨  {t('Usar este pedido')}")
            usar.setToolTip(t("Lo deja escrito en el Director para que lo cambies"))
            usar.clicked.connect(lambda: usar_pedido(str(e["pedido"])))
            botones.addWidget(usar)
        botones.addStretch()
        lay.addLayout(botones)
        return b

    def _herramienta(self, nombre_icono, color, nombre, frase, ejemplo, de_galeria, nuevo, al_pulsar) -> QPushButton:
        """Una herramienta: arriba, algo hecho con ella (se mueve con el ratón encima); su icono, su nombre, «NUEVO» si
        trae algo nuevo y una frase. Una foto suelta que no es de la galería (de_galeria False: la del editor) se
        queda quieta: su GIF es el montaje de fotos con la galería vieja."""
        b = _tarjeta_boton(nombre, frase)
        lay = QVBoxLayout(b)
        lay.setContentsMargins(8, 8, 8, 14)
        lay.setSpacing(8)
        vista = pagina_director.Vista(ejemplo, vacio=(nombre_icono, color))
        vista.setAccessibleName(nombre)
        vista.RADIO = 12
        vista.dueno, vista.alto_por_ancho = b, 9 / 16
        if not de_galeria:  # quieta y entera: es una foto suelta, no un video
            vista.gif = vista.video = None
            vista.es_video, vista.alto_util = False, 1.0
        politica = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        politica.setHeightForWidth(True)
        vista.setSizePolicy(politica)
        self.vistas.append(vista)
        fila = QHBoxLayout()
        fila.setContentsMargins(8, 2, 8, 0)
        fila.setSpacing(8)
        dibujo = QLabel()
        dibujo.setPixmap(icono(nombre_icono, color).pixmap(20, 20))
        titulo = etiqueta(nombre, "acceso_titulo")
        titulo.setWordWrap(False)
        fila.addWidget(dibujo)
        fila.addWidget(titulo)
        partes = [vista, dibujo, titulo]
        if nuevo:  # en la esquina de su vista, como en Higgsfield: junto al nombre no cabía a 1280 px
            vista.insignia = t("Nuevo").upper()
            b.setAccessibleDescription(f"{t('Nuevo')}. {frase}")
        fila.addStretch()
        texto = etiqueta(frase, "sub")
        texto.setContentsMargins(8, 0, 8, 0)
        _transparentes(*partes, texto)
        lay.addWidget(vista)
        lay.addLayout(fila)
        lay.addWidget(texto)
        lay.addStretch()
        b.clicked.connect(al_pulsar)
        return b

    # ---------- Tu estudio hoy y lo reciente ----------

    def showEvent(self, e):
        self.recargar()  # al volver a Inicio sale lo recién hecho y las claves recién conectadas
        self.vigia.start()
        super().showEvent(e)

    def hideEvent(self, e):
        """En otra página del menú: su vigilancia no recorre las piezas cada 400 ms y ningún video se queda abierto."""
        self.vigia.stop()
        pagina_director.quietas(self.piezas)
        super().hideEvent(e)

    def recargar(self):
        """Vuelve a leer lo reciente y qué IA está conectada."""
        self.saludo.setText(_saludo())
        for rejilla in (self.estudio, self.ultimos):
            while (item := rejilla.takeAt(0)) is not None:
                item.widget().setParent(None)
        for n, i in enumerate(indicadores()):
            self.estudio.addWidget(self._indicador(i), 0, n)
        # ponytail: se lee en el hilo de la ventana (de las ediciones solo se validan las más nuevas: ~0,4 s con
        # decenas de proyectos grandes); con cientos de videos y series convendría una Tarea
        self.recientes = recientes()
        for n, r in enumerate(self.recientes):
            nombre_icono, nombre_tipo = TIPOS.get(r["tipo"], ("sparkles", t("Video")))
            cuando = QLocale(idioma.actual()).toString(QDateTime.fromSecsSinceEpoch(int(r["fecha"])),
                                                       QLocale.ShortFormat) if r["fecha"] else ""
            self.ultimos.addWidget(_pulsable(nombre_icono, "#C9B8FF", t(r["titulo"]),
                                             f"{nombre_tipo}  ·  {cuando}" if cuando else nombre_tipo,
                                             lambda _, r=r: self._abrir(r)), n // 3, n % 3)
        self.vacio.setVisible(not self.recientes)

    def _indicador(self, i: dict):
        caja, lay = tarjeta()
        fila = QHBoxLayout()
        fila.setSpacing(12)
        fila.addWidget(_chip(i["icono"], lado=36))
        fila.addWidget(etiqueta(i["titulo"], "sub"), 1)
        lay.addLayout(fila)
        lay.addWidget(etiqueta(i["valor"], "indicador"))
        if i["detalle"]:
            lay.addWidget(etiqueta(i["detalle"], "sub"))
        lay.addStretch()
        if i["conectar"]:
            conectar = boton(f"🔑  {t('Conectar')}")
            conectar.clicked.connect(lambda: self.ir("Claves de IA"))
            lay.addWidget(conectar, 0, Qt.AlignLeft)
        return caja

    def _abrir(self, r: dict):
        """Lo reciente, donde toca: el video en su ventana, la edición en el editor y la serie en su página."""
        {"ver": lambda dato: ver_video(self, dato), "editar": self.abrir_edicion,
         "serie": self.abrir_serie}[r["accion"]](r["dato"])

    # ---------- Ejemplos ----------

    def _ver_ejemplo(self, e: dict):
        return ver_video(self, pagina_director.proyecto_ejemplo(e))

    def _ver_diseno(self, d: dict):
        return ver_imagen(self, pagina_director.foto(d), str(d.get("titulo", "")))
