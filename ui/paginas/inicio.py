"""Página «Inicio»: el panel con el que abre la app. Accesos a cada herramienta, lo último que hiciste, qué IA usa el
estudio ahora mismo y los videos de ejemplo hechos con Ráfaga Studio."""
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QDateTime, QLocale, Qt, QTimer
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from motor import claves, edicion, idioma, nubes, seguro, serie, shorts
from motor.idioma import t
from ui.comun import boton, etiqueta, Reproductor, tarjeta, ver_imagen
from ui.iconos import icono
from ui.paginas import director as pagina_director
from ui.paginas.claves import NOMBRES_PROVEEDOR

ESTILO_INICIO = """
#portada { font-size: 34px; font-weight: 800; color: #FFFFFF; }
#seccion { font-size: 19px; font-weight: 700; color: #FFFFFF; padding-top: 6px; }
#acceso { background: #17171D; border: 1px solid #24242C; border-radius: 14px; text-align: left; }
#acceso:hover, #acceso:focus { background: #1C1A28; border: 1px solid #7C5CFF; }
#acceso:pressed { background: #241E3A; }
#acceso_titulo { font-size: 17px; font-weight: 700; color: #FFFFFF; }
#acceso QLabel#sub { font-size: 14px; }
#indicador { font-size: 17px; font-weight: 700; color: #FFFFFF; }
#ejemplo { background: transparent; border: none; border-radius: 10px; padding: 6px; font-size: 14px; }
#ejemplo:hover { background: #20202A; }
"""

# Accesos rápidos: (icono, color, nombre, frase, página del menú a la que lleva; sin traducir, como PAGINA del Director)
ACCESOS = [
    ("bot", "#B79CFF", t("Director IA"), t("Pídelo con tus palabras y la IA hace todo el trabajo"), "Director IA"),
    ("sparkles", "#FF4D8D", t("Crear video"), t("De una idea a un video con guion, voz e imágenes"), "Crear con IA"),
    ("zap", "#FFB454", t("Shorts mágicos"), t("Los mejores momentos de un video largo, listos para subir"),
     "Shorts mágicos"),
    ("megaphone", "#00E5FF", t("Anuncios"), t("Anuncios para tu negocio en un par de minutos"), "Anuncios"),
    ("palette", "#7CFFB2", t("Diseño"), t("Miniaturas, posts y portadas con tu marca"), "Diseño"),
    ("film", "#FF8A5C", t("Serie animada"), t("Tus personajes de siempre en capítulos nuevos"), "Serie animada"),
    ("scissors", "#5CA8FF", t("Editor de video"), t("Corta, une, subtitula y exporta como un profesional"),
     "Editor de video"),
    ("music", "#F472B6", t("Música"), t("Canciones y videos musicales con IA"), "Música"),
]
# Lo reciente: el icono y el nombre de cada tipo (el «tipo» de proyecto.json, o «edicion» y «serie»)
TIPOS = {"shorts": ("zap", "Shorts"), "anuncio": ("megaphone", t("Anuncios")), "musica": ("music", t("Música")),
         "videomusical": ("clapperboard", t("Video musical")), "cabina": ("mic", t("Cabina")),
         "separacion": ("scissors", t("Separación")), "animacion": ("image", t("Animación")),
         "edicion": ("scissors", t("Editor de video")), "serie": ("film", t("Serie animada"))}
# Qué conviene conectar para cada uso: mientras no haya ninguna de estas claves, su indicador ofrece «Conectar»
CONVIENE = {"texto": ("anthropic", "gemini", "groq", "openai"), "imagen": ("cloudflare",),
            "video": ("huggingface", "modal")}


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
    hoy = {k: v for k, v in nubes.resumen_hoy().items() if isinstance(v, int) and v > 0}  # el archivo se puede tocar
    return [
        {"icono": "message-square-text", "titulo": t("IA de texto"), "conectar": falta["texto"],
         "valor": NOMBRES_PROVEEDOR.get(texto["proveedor"], str(texto["proveedor"]).capitalize()) if texto
         else t("IA gratis sin clave (lenta)"),
         "detalle": t("Conecta Gemini, Claude o Groq: guiones más rápidos y mejores") if falta["texto"]
         else str((texto or {}).get("modelo_texto") or "")[:60]},
        {"icono": "image", "titulo": t("Imágenes"), "conectar": falta["imagen"],
         "valor": nubes.NOMBRES.get(imagen, imagen),
         "detalle": t("Conecta Cloudflare (gratis): unas 100 imágenes buenas al día") if falta["imagen"] else ""},
        {"icono": "clapperboard", "titulo": t("Video con IA"), "conectar": falta["video"],
         "valor": NOMBRES_PROVEEDOR["ninguno"] if video == "ninguno" else nubes.NOMBRES.get(video, video),
         "detalle": t("Conecta Hugging Face o Modal para animar más escenas cada día") if falta["video"] else ""},
        {"icono": "gauge", "titulo": t("Uso gratis de hoy"), "conectar": False,
         "valor": t("{n} creaciones", n=sum(hoy.values())) if hoy else t("Aún nada hoy"),
         "detalle": "  ·  ".join(f"{nubes.NOMBRES.get(k, k)}: {v}" for k, v in hoy.items())[:200]},
    ]


def _saludo() -> str:
    hora = time.localtime().tm_hour
    return t("¡Buenos días!") if 5 <= hora < 12 else t("¡Buenas tardes!") if 12 <= hora < 20 else t("¡Buenas noches!")


def _pulsable(nombre_icono, color, titulo, texto, al_pulsar) -> QPushButton:
    """Tarjeta pulsable con su icono de línea, título y una frase; se ilumina al pasar el ratón (ver ESTILO_INICIO)."""
    b = QPushButton()
    b.setObjectName("acceso")
    b.setCursor(Qt.PointingHandCursor)
    b.setAccessibleName(titulo)
    b.setAccessibleDescription(texto)
    b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)  # un botón es de alto fijo: cortaría el texto largo
    lay = QVBoxLayout(b)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(6)
    dibujo = QLabel()
    dibujo.setPixmap(icono(nombre_icono, color).pixmap(28, 28))
    for w in (dibujo, etiqueta(titulo, "acceso_titulo"), etiqueta(texto, "sub")):
        w.setAttribute(Qt.WA_TransparentForMouseEvents)  # el clic y el hover son de la tarjeta entera
        lay.addWidget(w)
    lay.addStretch()
    b.clicked.connect(al_pulsar)
    return b


class PaginaInicio(QWidget):
    def __init__(self, ir, abrir_edicion, abrir_serie):
        """ir(nombre del menú, sin traducir) cambia de página; abrir_edicion(carpeta) y abrir_serie(nombre) abren lo
        reciente en su página. Las páginas no se conocen: lo une app.py."""
        super().__init__()
        self.ir, self.abrir_edicion, self.abrir_serie = ir, abrir_edicion, abrir_serie
        self.recientes = []
        self.setStyleSheet(ESTILO_INICIO)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        self.saludo = etiqueta(_saludo(), "sub")
        lay.addWidget(self.saludo)
        lay.addWidget(etiqueta(t("¿Qué creamos hoy?"), "portada"))
        lay.addWidget(etiqueta(t("Todo tu estudio de video con IA en un solo lugar. Elige por dónde empezar o sigue "
                                 "con lo último que hiciste."), "sub"))
        lay.addSpacing(8)
        accesos = self._rejilla(4)
        for n, (nombre_icono, color, nombre, frase, pagina) in enumerate(ACCESOS):
            accesos.addWidget(_pulsable(nombre_icono, color, nombre, frase, lambda _, p=pagina: self.ir(p)), n // 4, n % 4)
        lay.addLayout(accesos)
        lay.addSpacing(12)
        lay.addWidget(etiqueta(t("Tu estudio hoy"), "seccion"))
        self.estudio = self._rejilla(4)
        lay.addLayout(self.estudio)
        lay.addSpacing(12)
        lay.addWidget(etiqueta(t("Continuar donde lo dejaste"), "seccion"))
        self.ultimos = self._rejilla(3)
        lay.addLayout(self.ultimos)
        self.vacio = etiqueta(t("Aún no hay nada por aquí. Crea tu primer video con uno de los accesos de arriba y lo "
                                "verás aquí."), "sub")
        lay.addWidget(self.vacio)
        self.galeria = self._galeria()
        lay.addWidget(self.galeria)
        self.reproductor = Reproductor()
        self.reproductor.hide()
        lay.addWidget(self.reproductor)
        lay.addStretch()

    @staticmethod
    def _rejilla(columnas: int) -> QGridLayout:
        """Rejilla de columnas iguales, aunque una fila no se llene."""
        rejilla = QGridLayout()
        rejilla.setSpacing(14)
        for c in range(columnas):
            rejilla.setColumnStretch(c, 1)
        return rejilla

    def showEvent(self, e):
        self.recargar()  # al volver a Inicio sale lo recién hecho y las claves recién conectadas
        super().showEvent(e)

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
            self.ultimos.addWidget(_pulsable(nombre_icono, "#B79CFF", t(r["titulo"]),
                                             f"{nombre_tipo}  ·  {cuando}" if cuando else nombre_tipo,
                                             lambda _, r=r: self._abrir(r)), n // 3, n % 3)
        self.vacio.setVisible(not self.recientes)

    def _indicador(self, i: dict):
        caja, lay = tarjeta()
        fila = QHBoxLayout()
        dibujo = QLabel()
        dibujo.setPixmap(icono(i["icono"]).pixmap(20, 20))
        fila.addWidget(dibujo)
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
        """Lo reciente, donde toca: el video aquí mismo, la edición en el editor y la serie en su página."""
        {"ver": self._ver, "editar": self.abrir_edicion, "serie": self.abrir_serie}[r["accion"]](r["dato"])

    def _ver(self, proyecto: dict):
        """Reproduce aquí, en el reproductor de abajo, y baja hasta él."""
        self.reproductor.show()
        self.reproductor.mostrar(proyecto)
        area = self.parentWidget().parentWidget() if self.parentWidget() else None  # app.py la pone en un QScrollArea
        if isinstance(area, QScrollArea):
            QTimer.singleShot(0, lambda: area.ensureWidgetVisible(self.reproductor))

    # ---------- Ejemplos ----------

    def _galeria(self):
        """Los ejemplos (ejemplos/): los videos se ven aquí y los diseños se abren en grande. Sin ejemplos, no sale."""
        caja = QWidget()
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.addWidget(etiqueta(t("Hecho con Ráfaga Studio"), "seccion"))
        videos, disenos = pagina_director.ejemplos(), pagina_director.disenos()
        for lista, abrir in ((videos, self._ver_ejemplo),
                             (disenos, lambda d: ver_imagen(self, pagina_director.EJEMPLOS / f"{d['id']}.jpg",
                                                            str(d.get("titulo", ""))))):
            fila = QHBoxLayout()
            for e in lista:
                fila.addWidget(pagina_director.tarjeta_ejemplo(e, lambda e=e, abrir=abrir: abrir(e)))
            fila.addStretch()
            lay.addLayout(fila)
        caja.setVisible(bool(videos or disenos))
        return caja

    def _ver_ejemplo(self, e: dict):
        guion = e.get("guion") or {}
        self._ver({"formato": e.get("formato", "9:16"), "resultados": [{
            "archivo": str(pagina_director.EJEMPLOS / f"{e['id']}.mp4"), "titulo": str(e.get("titulo", "")),
            "descripcion": str(guion.get("descripcion", "")), "hashtags": list(guion.get("hashtags", []))}]})
