"""«Descargar» y «Guardado en» en cada sección que crea archivos (ui/comun: descargar y AccionesResultado), sin red,
claves, cámara ni micrófono. El dueño: unas secciones no tenían «Descargar» y otras guardaban sin decir dónde. Tras un
trabajo de mentira, cada página enseña dónde quedó lo hecho con «Abrir carpeta», y «Descargar» copia el archivo
elegido (cada short, cada anuncio, cada canción…) donde se pide, sin pisar otro sin preguntar.
python -m pruebas.descargas"""
import json
import os
import shutil
import tempfile
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtCore import QPoint, QStandardPaths  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtMultimedia import QMediaPlayer  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QMessageBox, QPushButton, QScrollArea  # noqa: E402

from motor import actividad, cabina, claves, diseno, edicion, marca, memoria, nichos, serie, shorts  # noqa: E402
from motor.guardia import RAIZ  # noqa: E402
from pruebas import camara_falsa  # noqa: E402
from ui.comun import ESTILO, carpeta_para, descargar, nombre_libre, Reproductor, ver_video  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
diseno.asegurar_qt()
camara_falsa.usar()  # el Editor trae «Grabarte»: nunca la cámara ni el micrófono de este PC
tmp = Path(tempfile.mkdtemp(prefix="rafaga-descargas-"))
claves.ARCHIVO, claves.AJUSTES, claves.CONEXIONES = tmp / "claves.json", tmp / "ajustes.json", tmp / "conexiones.json"
actividad.ARCHIVO, memoria.ARCHIVO, marca.ARCHIVO, marca.CARPETA_LOGO = (tmp / "actividad.json", tmp / "memoria.json",
                                                                         tmp / "marca.json", tmp / "marca")
diseno.CARPETA, edicion.CARPETA, serie.CARPETA = tmp / "disenos", tmp / "ediciones", tmp / "series"
shorts.PROYECTOS = nichos.PROYECTOS = cabina.PROYECTOS = tmp / "datos" / "proyectos"
bajadas = tmp / "bajadas"
bajadas.mkdir()

# Sin ventanas ni Explorador: cada aviso se apunta (y se pulsa su «Abrir carpeta»), cada diálogo de guardar contesta
# con lo de `destinos`, y el reproductor no carga los videos de mentira
avisos, abiertas, destinos, pedidos, preguntas = [], [], [], [], []
pulsar_abrir = [True]


def _aviso(caja):
    avisos.append((caja.windowTitle(), caja.text()))
    abrir = [b for b in caja.buttons() if b.text() == "Abrir carpeta"]
    if abrir and pulsar_abrir[0]:
        abrir[0].click()
    return QMessageBox.Ok


QMessageBox.exec = _aviso
QMessageBox.question = staticmethod(lambda padre, titulo, texto, *a: preguntas.append(texto) or respuesta[0])
respuesta = [QMessageBox.Yes]
os.startfile = abiertas.append
QFileDialog.getSaveFileName = staticmethod(lambda padre, titulo, sugerido, filtro: (pedidos.append((sugerido, filtro)),
                                                                                  (destinos.pop(0), ""))[1])
QMediaPlayer.setSource = QMediaPlayer.play = lambda *a: None


def esperar(listo, segundos=10):
    import time
    fin = time.monotonic() + segundos
    while not listo():
        assert time.monotonic() < fin, "no terminó a tiempo"
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def bajar(acciones, nombre: str) -> Path:
    """Pulsa «Descargar» de esas acciones y devuelve la copia hecha en bajadas/."""
    destinos.append(str(bajadas / nombre))
    acciones.descargar.click()
    return bajadas / nombre


def visibles(acciones, carpeta) -> None:
    """La línea de dónde quedó, con «Abrir carpeta» (que abre esa carpeta) y «Descargar», a la vista."""
    assert acciones.isVisibleTo(acciones.window()), "las acciones no se ven"
    assert acciones.donde.text() == f"Guardado en: {carpeta}", acciones.donde.text()
    assert not acciones.abrir.isHidden() and not acciones.descargar.isHidden()
    acciones.abrir.click()
    assert abiertas[-1] == Path(carpeta), abiertas


n_proyecto = [0]


def proyecto(tipo: str, nombres: list[str], titulo: str) -> dict:
    """Lo que devuelve un trabajo del motor: su carpeta en datos/proyectos con un archivo por resultado."""
    n_proyecto[0] += 1
    carpeta = shorts.PROYECTOS / f"20261029-1200{n_proyecto[0]:02d}-{tipo}"
    carpeta.mkdir(parents=True)
    resultados = []
    for i, nombre in enumerate(nombres, 1):
        (carpeta / nombre).write_bytes(f"{tipo}-{nombre}-".encode() * 2000)
        resultados.append({"archivo": str(carpeta / nombre), "titulo": f"{titulo} {i}", "descripcion": "",
                           "hashtags": []})
    p = {"tipo": tipo, "titulo": titulo, "carpeta": str(carpeta), "formato": "9:16", "resultados": resultados}
    (carpeta / "proyecto.json").write_text(json.dumps(p), encoding="utf-8")
    return p


def tras_trabajo(pagina, boton, p: dict):
    """Un trabajo de mentira por el camino de verdad (PaginaTrabajo.lanzar), hasta que acaba."""
    assert pagina.lanzar(boton, lambda aviso: p)
    esperar(lambda: not pagina.tarea.isRunning() and boton.isEnabled())


def en_area(pagina) -> QScrollArea:
    """Como en la app: la página en su QScrollArea, del tamaño que le queda en la pantalla del dueño (1280×720 al
    150 %, menos el menú, la barra de título y la de tareas)."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(pagina)
    area.resize(1030, 650)
    area.show()
    return area


def a_la_vista(area: QScrollArea, acciones) -> None:
    """Al terminar, la página bajó sola hasta «Descargar / Guardado en»: quedaba bajo el borde."""
    y = acciones.mapTo(area.viewport(), QPoint(0, 0)).y()
    assert 0 <= y and y + acciones.height() <= area.viewport().height(), (y, acciones.height(),
                                                                           area.viewport().height())


# ---------- descargar(): dónde, con qué nombre, sin pisar y sin perder nada ----------
lugares = {".mp4": QStandardPaths.MoviesLocation, ".webm": QStandardPaths.MoviesLocation,
           ".MP3": QStandardPaths.MusicLocation, ".wav": QStandardPaths.MusicLocation,
           ".png": QStandardPaths.PicturesLocation, ".jpg": QStandardPaths.PicturesLocation,
           ".txt": QStandardPaths.DownloadLocation, ".json": QStandardPaths.DownloadLocation}
for sufijo, lugar in lugares.items():
    assert carpeta_para(sufijo) == Path(QStandardPaths.writableLocation(lugar)), sufijo
(bajadas / "Mi short.mp4").write_bytes(b"1")
assert nombre_libre(bajadas, "Mi short", ".mp4").name == "Mi short (2).mp4"
(bajadas / "Mi short (2).mp4").write_bytes(b"2")
assert nombre_libre(bajadas, "Mi short", ".mp4").name == "Mi short (3).mp4"
assert nombre_libre(bajadas, 'Receta: a\\b/c "rica"?', ".mp4").name == "Receta a b c rica.mp4"
assert nombre_libre(bajadas, "aux", ".mp4").name == "Ráfaga Studio aux.mp4"  # Windows lo toma por un dispositivo
assert nombre_libre(bajadas, "Receta · 4:29", ".mp4").name == "Receta · 4.29.mp4"  # la duración, como 4.29

origen = Path(proyecto("shorts", ["short_01.mp4"], "Receta")["resultados"][0]["archivo"])
copia = bajadas / "receta.mp4"
destinos.append(str(copia))
assert descargar(None, origen, "Receta: pollo · 4:29") == copia
assert copia.read_bytes() == origen.read_bytes() and origen.is_file()  # una copia: el original se queda
assert pedidos[-1] == (str(nombre_libre(carpeta_para(".mp4"), "Receta: pollo · 4:29", ".mp4")), "MP4 (*.mp4)"), pedidos
assert Path(pedidos[-1][0]).name.startswith("Receta pollo · 4.29")
assert avisos[-1] == ("Descargado", f"Guardado en {copia}") and abiertas[-1] == bajadas
assert not list(bajadas.glob("*.parcial"))
# Escrito sin extensión: lleva la suya y, si ya hay uno con ese nombre, se pregunta antes de pisarlo
copia.write_bytes(b"lo del usuario")
for contesta, queda in ((QMessageBox.No, b"lo del usuario"), (QMessageBox.Yes, origen.read_bytes())):
    respuesta[0], antes = contesta, len(avisos)
    destinos.append(str(bajadas / "receta"))
    assert descargar(None, origen) == (copia if contesta == QMessageBox.Yes else None)
    assert preguntas[-1] == "Ya hay un archivo «receta.mp4» en esa carpeta. ¿Reemplazarlo?"
    assert copia.read_bytes() == queda and len(avisos) == antes + (contesta == QMessageBox.Yes)
respuesta[0] = QMessageBox.Yes
# Cancelado: nada se guarda ni se avisa
antes = len(avisos)
destinos.append("")
assert descargar(None, origen) is None and len(avisos) == antes
# Donde no se puede: lo dice en claro y no deja medio archivo
destinos.append(str(tmp / "no-existe" / "x.mp4"))
assert descargar(None, origen) is None and avisos[-1] == ("No se pudo descargar",
                                                          f"No se pudo guardar en {tmp / 'no-existe' / 'x.mp4'}.")
# El resultado ya no está (se movió desde el Explorador): lo dice, sin culpar al destino ni abrir el diálogo
antes = len(pedidos)
borrado = origen.with_name("borrado.mp4")
assert descargar(None, borrado) is None and len(pedidos) == antes
assert avisos[-1] == ("No se pudo descargar", f"Ya no está en su carpeta (¿se movió o se borró?): {borrado}")
# Si la copia falla a medias (disco lleno), lo que había en el destino no se pierde ni queda medio archivo
copia.write_bytes(b"lo del usuario")
destinos.append(str(copia))
copiar_de_verdad = shutil.copyfile


def copia_a_medias(de, a):
    Path(a).write_bytes(b"medio vide")
    raise OSError(28, "No queda espacio en el disco")


shutil.copyfile = copia_a_medias
try:
    assert descargar(None, origen) is None and copia.read_bytes() == b"lo del usuario"
finally:
    shutil.copyfile = copiar_de_verdad
assert avisos[-1] == ("No se pudo descargar", f"No se pudo guardar en {copia}.")
assert not list(bajadas.glob("*.parcial"))
# Un resultado en una carpeta de red no se lee (conectaría por SMB): ni se abre el diálogo
antes = len(pedidos)
assert descargar(None, r"\\atacante.example\s\video.mp4") is None and len(pedidos) == antes
assert "carpeta de red" in avisos[-1][1]

# ---------- El reproductor de cada página: «Descargar» y dónde quedó, justo bajo la lista ----------
from ui.paginas.anuncios import PaginaAnuncios  # noqa: E402
from ui.paginas.cabina import PaginaCabina  # noqa: E402
from ui.paginas.crear import PaginaCrear  # noqa: E402
from ui.paginas.musica import PaginaMusica  # noqa: E402
from ui.paginas.nichos import PaginaNichos  # noqa: E402
from ui.paginas.proyectos import PaginaProyectos  # noqa: E402
from ui.paginas.shorts import PaginaShorts  # noqa: E402

r = Reproductor()
botones = [b.text() for b in r.findChildren(QPushButton)]
assert botones.count("Abrir carpeta") == 1 and "Descargar" in botones, botones  # «Abrir carpeta» pasó a las acciones
lay = r.layout()
assert lay.indexOf(r.lista) + 1 == lay.indexOf(r.acciones) == lay.indexOf(r.pantalla) - 1  # entre lista y video
assert r.acciones.isHidden()  # sin resultados, nada que descargar

# Crear con IA: un video
crear = PaginaCrear()
area = en_area(crear)
p = proyecto("video", ["video_final.mp4"], "Pechuga Cordon Bleu")
tras_trabajo(crear, crear.iniciar, p)
a_la_vista(area, crear.reproductor.acciones)
visibles(crear.reproductor.acciones, p["carpeta"])
hecho = bajar(crear.reproductor.acciones, "pechuga.mp4")
assert hecho.read_bytes() == Path(p["resultados"][0]["archivo"]).read_bytes()
assert Path(pedidos[-1][0]).parent == carpeta_para(".mp4") and "Pechuga Cordon Bleu 1" in pedidos[-1][0]
area.close()

# Shorts mágicos (cada short), Anuncios (cada versión): «Descargar» copia el elegido en la lista
for Pagina, tipo, nombres in ((PaginaShorts, "shorts", ["short_01.mp4", "short_02.mp4", "short_03.mp4"]),
                              (PaginaAnuncios, "anuncio", ["anuncio_1.mp4", "anuncio_2.mp4"])):
    pagina = Pagina()
    area = en_area(pagina)
    p = proyecto(tipo, nombres, tipo.capitalize())
    tras_trabajo(pagina, pagina.iniciar, p)
    a_la_vista(area, pagina.reproductor.acciones)
    visibles(pagina.reproductor.acciones, p["carpeta"])
    for fila, nombre in enumerate(nombres):
        pagina.reproductor.lista.setCurrentRow(fila)
        hecho = bajar(pagina.reproductor.acciones, f"{tipo}-{fila}.mp4")
        assert hecho.read_bytes() == (Path(p["carpeta"]) / nombre).read_bytes(), (tipo, fila)
        assert f"{tipo.capitalize()} {fila + 1}" in pedidos[-1][0], pedidos[-1]
    area.close()

# Música: la canción (a Música por defecto) y su video musical
musica = PaginaMusica()
musica.show()
p = proyecto("musica", ["cancion.mp3"], "Viernes con los panas")
tras_trabajo(musica, musica.iniciar, p)
visibles(musica.reproductor.acciones, p["carpeta"])
assert bajar(musica.reproductor.acciones, "cancion.mp3").read_bytes() == Path(p["resultados"][0]["archivo"]).read_bytes()
assert Path(pedidos[-1][0]).parent == carpeta_para(".mp3") and pedidos[-1][1] == "MP3 (*.mp3)"
p = proyecto("videomusical", ["video_musical.mp4"], "Viernes con los panas")
tras_trabajo(musica, musica.hacer_video, p)
visibles(musica.reproductor.acciones, p["carpeta"])
assert bajar(musica.reproductor.acciones, "clip.mp4").read_bytes() == Path(p["resultados"][0]["archivo"]).read_bytes()
musica.close()

# Cabina: la toma recién grabada (sin micrófono: la grabación es de mentira), la canción producida y la separación
pista = tmp / "beat.wav"
with wave.open(str(pista), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(8000)
    w.writeframes(b"\x00\x00" * 800)
cabina.a_wav = lambda origen, destino: None
cabina.grabar = lambda pista_wav, destino, detener, micro, aviso: Path(destino).write_bytes(b"RIFF toma de mentira")
cab = PaginaCabina()
cab.show()
assert cab.toma.isHidden()  # sin toma, nada que enseñar
cab.pista.setText(str(pista))
cab._grabar()
esperar(lambda: not cab.tarea.isRunning() and cab.grabar_btn.isEnabled())
grabaciones = shorts.PROYECTOS.parent / "grabaciones"
visibles(cab.toma, grabaciones)
toma = Path(cab.voz.text())
assert toma.parent == grabaciones and bajar(cab.toma, "toma.wav").read_bytes() == toma.read_bytes()
# Con otra toma elegida, la fila se va: «Descargar» copiaría la grabada, no la que se ve; vuelve con la grabada
cab.voz.setText(str(pista))
assert cab.toma.isHidden()
cab.voz.setText(str(toma))
assert not cab.toma.isHidden()
p = proyecto("cabina", ["cancion_master.wav"], "Mi canción")
tras_trabajo(cab, cab.producir, p)
visibles(cab.reproductor.acciones, p["carpeta"])
p = proyecto("separacion", ["voz.wav", "pista.wav"], "Separada")
tras_trabajo(cab, cab.separar_btn, p)
cab.reproductor.lista.setCurrentRow(1)
assert bajar(cab.reproductor.acciones, "pista.wav").read_bytes() == Path(p["resultados"][1]["archivo"]).read_bytes()
cab.close()

# Mis proyectos: cada proyecto guardado, con su carpeta y su archivo
mis = PaginaProyectos()
mis.show()
assert mis.lista.count() == n_proyecto[0]
mis.lista.setCurrentRow(0)  # el más nuevo: la separación
visibles(mis.reproductor.acciones, p["carpeta"])
assert bajar(mis.reproductor.acciones, "de-mis-proyectos.wav").read_bytes() == \
    Path(p["resultados"][0]["archivo"]).read_bytes()
mis.close()

# Un ejemplo de la galería (vive entre los archivos del programa): se descarga, pero no se manda a su carpeta
ejemplo = RAIZ / "ejemplos" / "anuncio-rafaga.mp4"
ventana = ver_video(None, {"resultados": [{"archivo": str(ejemplo), "titulo": "Anuncio", "descripcion": "",
                                           "hashtags": []}]})
acciones = ventana.reproductor.acciones
assert acciones.donde.text() == "" and acciones.abrir.isHidden() and not acciones.descargar.isHidden()
assert bajar(acciones, "ejemplo.mp4").read_bytes() == ejemplo.read_bytes()
ventana.close()

# ---------- Nichos: el informe se guarda también en texto, se dice dónde y se descarga ----------
falso = {"resumen": "Las recetas rápidas explotan esta semana.", "tema": "cocina", "nichos": [
    {"nombre": "Recetas de 1 minuto", "potencial": 88, "competencia": "media", "por_que_es_viral": "Se ven enteras",
     "pruebas": "3 videos con 1M", "redes": ["TikTok"], "formato": "9:16", "monetizacion": "Afiliados",
     "hashtags": ["recetas"], "ideas": [{"titulo": "Pollo en 60 s", "gancho": "No lo cocines así", "prompt": "x"}]}]}
nichos.investigar = lambda tema, pais, aviso: falso
pagina = PaginaNichos(lambda pedido: None)
pagina.show()
assert pagina.acciones.isHidden()
pagina._iniciar()
esperar(lambda: not pagina.tarea.isRunning() and pagina.iniciar.isEnabled())
carpeta_nichos = shorts.PROYECTOS.parent / "nichos"
visibles(pagina.acciones, carpeta_nichos)
informe = pagina.acciones.archivo
texto = informe.read_text(encoding="utf-8")
assert informe.parent == carpeta_nichos and informe.suffix == ".txt"
assert all(x in texto for x in ("Las recetas rápidas", "Recetas de 1 minuto", "Pollo en 60 s", "No lo cocines así"))
assert "{" not in texto and "**" not in texto  # texto para leer: ni JSON ni Markdown
assert bajar(pagina.acciones, "nichos.txt").read_text(encoding="utf-8") == texto
assert pedidos[-1] == (str(nombre_libre(carpeta_para(".txt"), "Nichos virales cocina", ".txt")), "TXT (*.txt)")
pagina.close()

# ---------- Dibujos animados: el capítulo, las láminas de los personajes, la carpeta de la serie y los cuadros ----------
from ui.paginas.serie import PaginaSerie  # noqa: E402

carpeta_serie = tmp / "series" / "gato-pirata"
ep = carpeta_serie / "episodios" / "01"
ep.mkdir(parents=True)
(ep / "video_final.mp4").write_bytes(b"capitulo" * 1000)
(carpeta_serie / "personajes").mkdir()
lamina = carpeta_serie / "personajes" / "kaito.png"
dibujo = QImage(300, 450, QImage.Format_RGB32)
dibujo.fill(QColor("#3A6FD8"))
assert dibujo.save(str(lamina))
serie.listar = lambda: [{
    "tipo": "serie", "nombre": "gato-pirata", "carpeta": str(carpeta_serie), "titulo": "Gato pirata",
    "sinopsis": "Un gato pirata miedoso.", "formato": "16:9",
    "personajes": [{"nombre": "Kaito", "personalidad": "Callado", "voz": "", "lamina": str(lamina)},
                   {"nombre": "Yara", "personalidad": "Valiente", "voz": "", "lamina": ""}],
    "episodios": [{"numero": 1, "titulo": "El mapa", "carpeta": str(ep), "video": str(ep / "video_final.mp4"),
                   "miniatura": "", "estado": "listo", "resumen": "Encuentran un mapa."}]}]
serie.guion_grafico = lambda episodio: []
sp = PaginaSerie()
sp.resize(1100, 1000)
sp.show()
sp.series.setCurrentIndex(1)
app.processEvents()
assert sp.carpeta_serie.donde.text() == f"Guardado en: {carpeta_serie}" and sp.carpeta_serie.descargar.isHidden()
sp.carpeta_serie.abrir.click()
assert abiertas[-1] == carpeta_serie
# Cada lámina, su «Descargar» (en Imágenes, con el nombre del personaje); la que falta, su «Dibujar con IA»
por_personaje = {}
for i in range(sp.fila_personajes.count() - 1):
    caja = sp.fila_personajes.itemAt(i).widget()
    por_personaje[i] = [b.text() for b in caja.findChildren(QPushButton)]
assert por_personaje == {0: ["Descargar"], 1: ["Dibujar con IA"]}, por_personaje
destinos.append(str(bajadas / "kaito.png"))
next(b for b in sp.fila_personajes.itemAt(0).widget().findChildren(QPushButton)).click()
assert QImage(str(bajadas / "kaito.png")).size() == dibujo.size()
assert pedidos[-1][0] == str(nombre_libre(carpeta_para(".png"), "Kaito", ".png"))
sp.capitulos.setCurrentRow(0)
app.processEvents()
visibles(sp.reproductor.acciones, ep)
assert bajar(sp.reproductor.acciones, "capitulo.mp4").read_bytes() == (ep / "video_final.mp4").read_bytes()
# Los cuadros para retocar: al acabar se dice dónde quedaron, con «Abrir carpeta» (antes se abría el Explorador solo)
cuadros = ep / "cuadros"
cuadros.mkdir()
serie.exportar_cuadros = lambda episodio, fps=12: str(cuadros)
pulsar_abrir[0], abiertas_antes = False, len(abiertas)
sp._cuadros()
esperar(lambda: not sp.tarea_cuadros.isRunning() and sp.cuadros_btn.isEnabled())
assert avisos[-1] == ("Cuadros listos", f"Guardado en {cuadros}") and len(abiertas) == abiertas_antes
pulsar_abrir[0] = True
sp.close()

# ---------- Diseño y Editor de video: al exportar, dónde quedó y «Abrir carpeta» ----------
import ui.paginas.diseno as pd  # noqa: E402
import ui.paginas.edicion as pe  # noqa: E402

pd.carpeta_exportar = lambda: tmp / "Imagenes"  # el diálogo se abre ahí: que no cree nada en las Imágenes del PC
dp = pd.PaginaDiseno()
destinos.append(str(bajadas / "flyer.png"))
dp._pedir_exportar()
assert (bajadas / "flyer.png").is_file() and avisos[-1] == ("Diseño exportado", f"Guardado en {bajadas / 'flyer.png'}")
assert abiertas[-1] == bajadas
antes = len(avisos)
destinos.append("")  # cancelado: ni se exporta ni se avisa
dp._pedir_exportar()
assert len(avisos) == antes
ed = pe.PaginaEdicion()
video = tmp / "Videos" / "Ráfaga Studio" / "Mi viaje.mp4"
ed._exportado_listo({"archivo": str(video)})  # lo que deja el trabajo de exportar al acabar
assert avisos[-1] == ("Video exportado", f"Guardado en {video}") and abiertas[-1] == video.parent
print("Pruebas de Descargar y «Guardado en» pasadas.", flush=True)
os._exit(0)  # sin esperar los hilos de fondo de las páginas
