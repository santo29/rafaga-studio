"""Pruebas de la página «Inicio» (ui/paginas/inicio.py) sin red ni claves de verdad: python -m pruebas.inicio"""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtCore import QEvent, QPoint, QPropertyAnimation, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QLabel, QMenu, QMessageBox, QPushButton,  # noqa: E402
                               QWidget)

from motor import claves, diseno, edicion, marca, nubes, serie, shorts  # noqa: E402
from ui.comun import ESTILO, Rotulo  # noqa: E402
from ui.paginas import director as pagina_director  # noqa: E402
from ui.paginas import inicio  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
REALES = pagina_director.EJEMPLOS  # los ejemplos de verdad, antes de cambiarlos por los de la carpeta temporal


def esperar(condicion, plazo=10):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def fecha(texto):
    return time.mktime(time.strptime(texto, "%Y%m%d-%H%M%S"))


def video(carpeta, datos):
    (shorts.PROYECTOS / carpeta).mkdir(parents=True)
    (shorts.PROYECTOS / carpeta / "proyecto.json").write_text(
        datos if isinstance(datos, str) else json.dumps(datos), encoding="utf-8")


def tarjeta(pagina, titulo):
    return next(b for b in pagina.findChildren(QPushButton) if b.accessibleName() == titulo)


def conectar(pagina):
    return [b for b in pagina.findChildren(QPushButton) if b.text() == "Conectar"]


def ventana_de_video(padre):
    """La ventana con el reproductor que abrió ver_video (la última visible)."""
    abiertas = [v for v in padre.findChildren(QDialog) if v.isVisible() and hasattr(v, "reproductor")]
    return abiertas[-1] if abiertas else None


def cerrar_videos(padre):
    for v in padre.findChildren(QDialog):
        if hasattr(v, "reproductor"):  # soltar el video falso: cargando al salir, Qt podía caerse
            v.reproductor.player.stop()
            v.reproductor.player.setSource(QUrl())
            v.close()
    app.sendPostedEvents(None, QEvent.DeferredDelete)


def moviendose(lista):
    return [b.accessibleName() for b in lista if pagina_director.corriendo(b)]


# ---------- Los ejemplos de verdad: sin los videos hechos pegando fotos ni la portada de presentación ----------
reales = [e["id"] for e in pagina_director.ejemplos()] + [d["id"] for d in pagina_director.disenos()]
for quitado in ("lugares-rd", "anuncio-cafe", "presentacion-rafaga"):
    assert quitado not in reales and not list(REALES.glob(f"{quitado}.*")), quitado
assert {"manzana-habla", "leyenda-rafaga", "leyenda-ia", "mascota-rafa"} <= set(reales), reales
# Rafa vive en assets/ (con su marca); una ruta que se sale de la app no vale
assert pagina_director.foto({"id": "mascota-rafa", "imagen": "assets/mascota.jpg"}).is_file()
assert pagina_director.foto({"id": "x", "imagen": "../../Windows/win.ini"}) is None
# El anuncio de la marca está en la lista, pero mientras no estén sus archivos no sale (como cualquier ejemplo)
assert "anuncio-rafaga" in [e["id"] for e in json.loads((REALES / "ejemplos.json").read_text(encoding="utf-8"))]
assert ("anuncio-rafaga" in reales) == (REALES / "anuncio-rafaga.mp4").is_file()
# Cada destacado y cada vista de herramienta nombra un ejemplo de verdad o uno que se espera (el anuncio, los diseños
# nuevos): sin su archivo, no sale
assert len({i for i, *_ in inicio.DESTACADOS}) == len(inicio.DESTACADOS)

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    shorts.PROYECTOS, edicion.CARPETA, serie.CARPETA = d / "proyectos", d / "ediciones", d / "series"
    claves.ARCHIVO, claves.AJUSTES, nubes.USO = d / "claves.json", d / "ajustes.json", d / "uso.json"
    diseno.CARPETA, marca.ARCHIVO, marca.CARPETA_LOGO = d / "disenos", d / "marca.json", d / "marca"
    pagina_director.EJEMPLOS = d / "app" / "ejemplos"

    # ---------- Sin nada: se construye con las herramientas, sin recientes y sin ejemplos ----------
    navegado, editadas, series, pedidas = [], [], [], []
    pagina = inicio.PaginaInicio(navegado.append, editadas.append, series.append, None,
                                 lambda modo, texto: pedidas.append((modo, texto)))
    pagina.recargar()
    assert pagina.recientes == [] and not pagina.vacio.isHidden() and pagina.galeria.isHidden()
    assert pagina.bloque_destacados.isHidden() and pagina.destacados.piezas == []
    # Cada herramienta lleva a su página del menú; sin ejemplos, su vista es el dibujo de relleno con su icono
    for _, _, nombre, _, menu, _, _ in inicio.ACCESOS:
        tarjeta(pagina, nombre).click()
    assert navegado == ["Director IA", "Crear con IA", "Diseño", "Dibujos animados", "Editor de video",
                        "Shorts mágicos", "Anuncios", "Música"]  # el orden del menú
    assert "Crea tus personajes y capítulos de caricatura" in [a[3] for a in inicio.ACCESOS]
    assert len(pagina.vistas) == 8 and all(v.ruta is None and v.fuente() is None for v in pagina.vistas)
    assert [a[2] for a in inicio.ACCESOS if a[6]] == ["Crear video", "Diseño", "Editor de video"]  # lo nuevo
    assert [v.insignia for v in pagina.vistas].count("NUEVO") == 3
    assert tarjeta(pagina, "Editor de video").accessibleDescription().startswith("Nuevo.")
    pagina.resize(1100, 2600)
    assert not pagina.grab().isNull()  # se pinta sin ningún archivo de ejemplo
    # Las secciones llevan su rótulo fino en degradado (y su nombre para el lector de pantalla)
    assert [r.accessibleName() for r in pagina.findChildren(Rotulo)] == [
        "Lo que puedes crear", "Herramientas", "Tu estudio hoy", "Tus proyectos", "Hecho con Ráfaga Studio"]
    # La novedad de arriba lleva a Ráfaga Guardia
    navegado.clear()
    tarjeta(pagina, "Nuevo: Ráfaga Guardia cuida tu estudio mientras creas").click()
    assert navegado == ["Ráfaga Guardia"]

    # ---------- Arriba: la idea va a la página de la opción elegida, escrita y sin empezar nada ----------
    assert [b.text() for b in pagina.modos.grupo.buttons()] == ["Video", "Imagen", "Diseño", "Música", "Director"]
    assert pagina.destino.text() == "Se abre en Crear con IA"
    pagina.crear.click()  # vacía: no manda nada
    assert pedidas == []
    for n, modo in enumerate(("video", "imagen", "diseno", "musica", "director")):
        pagina.modos.grupo.button(n).click()
        pagina.idea.setPlainText(f"  idea {modo}  ")
        pagina.crear.click()
        assert pedidas[-1] == (modo, f"idea {modo}") and pagina.idea.toPlainText() == ""
    assert pagina.destino.text() == "Se abre en Director IA"
    # Intro la manda; Mayúsculas+Intro, otra línea
    pagina.idea.setPlainText("con intro")
    app.sendEvent(pagina.idea, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert pedidas[-1] == ("director", "con intro")
    pagina.idea.setPlainText("una")
    app.sendEvent(pagina.idea, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ShiftModifier, "\r"))
    assert len(pedidas) == 6 and pagina.idea.toPlainText() != "una"
    assert pagina.idea.tabChangesFocus()  # el Tab no se queda atrapado en la caja
    pagina.idea.clear()

    # ---------- Indicadores sin claves: la IA gratis lenta y «Conectar» donde falta algo útil ----------
    ind = {i["titulo"]: i for i in inicio.indicadores()}
    assert ind["IA de texto"]["valor"] == "IA gratis sin clave (lenta)" and ind["IA de texto"]["conectar"]
    assert ind["Imágenes"]["conectar"] and "Cloudflare" in ind["Imágenes"]["detalle"]
    assert ind["Video con IA"]["conectar"]
    assert ind["Uso gratis de hoy"]["valor"] == "Aún nada hoy" and not ind["Uso gratis de hoy"]["conectar"]
    assert len(conectar(pagina)) == 3
    navegado.clear()
    conectar(pagina)[0].click()
    assert navegado == ["Claves de IA"]

    # ---------- Indicadores con claves (guardadas en la carpeta temporal) ----------
    claves.guardar({"proveedor": "gemini", "clave": "AIza-prueba", "usos": ["texto", "musica"],
                    "modelo_texto": "gemini-prueba"})
    claves.guardar({"proveedor": "cloudflare", "clave": "a b", "usos": ["imagen"], "modelo_imagen": "flux"})
    claves.elegir_por_defecto("video", "ninguno")
    # Un contador tocado a mano: lo que no es un número no cuenta
    nubes.USO.write_text(json.dumps({"fecha": time.strftime("%Y-%m-%d"), "cloudflare": 2, "raro": "mucho",
                                     "huggingface": 1}), encoding="utf-8")
    ind = {i["titulo"]: i for i in inicio.indicadores()}
    assert ind["IA de texto"]["valor"] == "Gemini (Google)" and ind["IA de texto"]["detalle"] == "gemini-prueba"
    assert not ind["IA de texto"]["conectar"]
    assert ind["Imágenes"]["valor"] == nubes.NOMBRES["cloudflare"] and not ind["Imágenes"]["conectar"]
    assert ind["Video con IA"]["valor"] == "No usar (zoom suave sobre la imagen)" and ind["Video con IA"]["conectar"]
    assert ind["Uso gratis de hoy"]["valor"] == "3 creaciones" and "raro" not in ind["Uso gratis de hoy"]["detalle"]
    pagina.recargar()
    assert len(conectar(pagina)) == 1  # los de antes se quitaron al recargar

    # ---------- Recientes: videos, ediciones y series juntos, por fecha, y lo roto se salta ----------
    def resultado(titulo, existe=True):
        if existe:
            (d / f"{titulo}.mp4").write_bytes(b"video")
        return {"archivo": str(d / f"{titulo}.mp4"), "titulo": titulo, "descripcion": "D", "hashtags": ["#a", 3]}
    # Un video que ya se borró no sale (el reproductor quedaría en negro sin avisar)
    video("20261023-030000-video", {"titulo": "Borrado", "carpeta": "x", "resultados": [resultado("Borrado", False)]})
    video("20261020-100000-video", {"tipo": "video", "titulo": "Video viejo", "formato": "9:16",
                                    "carpeta": str(shorts.PROYECTOS / "20261020-100000-video"),
                                    "resultados": [resultado("Video viejo")]})
    video("20261022-120000-shorts", {"tipo": "shorts", "titulo": "Shorts nuevos", "formato": "16:9",
                                     "carpeta": str(shorts.PROYECTOS / "20261022-120000-shorts"),
                                     "resultados": [resultado("Uno"), resultado("Dos")]})
    video("20261023-000000-video", "{roto")
    # Resultados que no se pueden reproducir (de una carpeta de red, sin archivo, de otro tipo): el proyecto no sale
    video("20261023-010000-video", {"titulo": "Trampa", "carpeta": "x", "resultados": [
        {"archivo": "\\\\atacante.example\\s\\robo.mp4", "titulo": "Robo"}, 5, {"titulo": "Sin archivo"}]})
    # Campos raros (tipo que no es texto, carpeta que no es una ruta): sale, sin fecha, al final
    video("20261023-020000-video", {"tipo": ["x"], "titulo": "Raro", "carpeta": {"a": 1},
                                    "resultados": [resultado("Raro")]})
    carpeta_edicion = edicion.nueva_carpeta("Mi edición")
    edicion.guardar(edicion.nuevo("Mi edición"), carpeta_edicion)
    os.utime(carpeta_edicion / "proyecto.json", (fecha("20261022-080000"),) * 2)
    (edicion.CARPETA / "rota").mkdir()
    (edicion.CARPETA / "rota" / "proyecto.json").write_text("{roto", encoding="utf-8")
    (serie.CARPETA / "20261021-090000-mi-serie").mkdir(parents=True)
    (serie.CARPETA / "20261021-090000-mi-serie" / "serie.json").write_text(json.dumps({"titulo": "Mi serie"}),
                                                                            encoding="utf-8")
    os.utime(serie.CARPETA / "20261021-090000-mi-serie" / "serie.json", (fecha("20261021-090000"),) * 2)
    (serie.CARPETA / "rota").mkdir()
    (serie.CARPETA / "rota" / "serie.json").write_text("[1, 2]", encoding="utf-8")

    lista = inicio.recientes()
    assert [r["titulo"] for r in lista] == ["Shorts nuevos", "Mi edición", "Mi serie", "Video viejo", "Raro"], lista
    assert [r["accion"] for r in lista] == ["ver", "editar", "serie", "ver", "ver"]
    assert lista[0]["dato"]["formato"] == "16:9" and lista[0]["dato"]["resultados"][0]["hashtags"] == ["#a"]
    assert [r["titulo"] for r in inicio.recientes(maximo=2)] == ["Shorts nuevos", "Mi edición"]
    # Como mucho 6, aunque haya más
    for n in range(4):
        video(f"20261019-10000{n}-video", {"titulo": f"Extra {n}", "carpeta": f"20261019-10000{n}-video",
                                          "resultados": [resultado(f"Extra {n}")]})
    assert len(inicio.recientes()) == 6
    # Si la lista de un módulo revienta, las demás siguen saliendo (su traza sale en la consola: es lo esperado)
    original, serie.listar = serie.listar, lambda: 1 / 0
    assert "Mi serie" not in [r["titulo"] for r in inicio.recientes()] and inicio.recientes()[0]["titulo"] == "Shorts nuevos"
    serie.listar = original

    pagina.recargar()
    assert pagina.vacio.isHidden() and len(pagina.recientes) == 6
    tarjeta(pagina, "Mi edición").click()
    assert editadas == [str(carpeta_edicion)]
    tarjeta(pagina, "Mi serie").click()
    assert series == ["20261021-090000-mi-serie"]
    tarjeta(pagina, "Shorts nuevos").click()  # el video, en su ventana: no hay que bajar la página para verlo
    visto = ventana_de_video(pagina)
    assert visto.reproductor.lista.count() == 2 and visto.reproductor.formato == "16:9"
    cerrar_videos(pagina)

    # ---------- Con ejemplos: el carrusel solo con los destacados, el mosaico con todos ----------
    ej = pagina_director.EJEMPLOS
    ej.mkdir(parents=True)
    (d / "app" / "assets").mkdir()
    foto = QImage(90, 160, QImage.Format_RGB32)
    foto.fill(QColor("#7C5CFF"))
    ancha = QImage(160, 90, QImage.Format_RGB32)
    ancha.fill(QColor("#FF4D8D"))
    # Un GIF de 1x1 en bucle hecho a mano (no hay Pillow)
    gif = bytes.fromhex("47494638396101000100800000000000ffffff21ff0b4e45545343415045322e30030100000021f904000a00"
                        "00002c00000000010001000002024401003b")
    videos = [{"id": "manzana-habla", "titulo": "Manzana", "pedido": "Una manzana que habla", "formato": "9:16",
               "guion": {"descripcion": "Desc", "hashtags": ["#x"]}},
              {"id": "leyenda-ia", "titulo": "Anime IA", "pedido": "Dos escenas del anime", "formato": "16:9"},
              {"id": "leyenda-rafaga", "titulo": "Tráiler"},  # sin pedido: no ofrece «Usar este pedido»
              {"id": "otro-video", "titulo": "Otro"},  # no es destacado: solo en el mosaico
              {"id": "anuncio-rafaga", "titulo": "Sin archivos"}]  # sin MP4 ni JPG: no sale en ningún sitio
    disenos = [{"id": "mascota-rafa", "titulo": "Rafa", "pedido": "La mascota", "imagen": "assets/mascota.jpg"},
               {"id": "portada-alto-voltaje", "titulo": "Portada"},
               {"id": "roto", "titulo": "Roto"},  # su JPG no es una imagen: sale el dibujo de relleno
               {"id": "sin-foto", "titulo": "Sin foto"}]
    (ej / "ejemplos.json").write_text(json.dumps(videos), encoding="utf-8")
    (ej / "disenos.json").write_text(json.dumps(disenos), encoding="utf-8")
    for e in videos[:4]:
        (ej / f"{e['id']}.mp4").write_bytes(b"\0" * 64)
        assert (foto if e["id"] == "manzana-habla" else ancha).save(str(ej / f"{e['id']}.jpg"))
        (ej / f"{e['id']}.gif").write_bytes(gif)
    shutil.copy(REALES / "leyenda-ia.mp4", ej / "leyenda-ia.mp4")  # uno de verdad: el carrusel lo reproduce nítido
    assert foto.save(str(d / "app" / "assets" / "mascota.jpg")) and ancha.save(str(ej / "portada-alto-voltaje.jpg"))
    (ej / "roto.jpg").write_bytes(b"no es una imagen")
    (ej / "presentacion-app.jpg").write_bytes(b"")  # la vista del editor: una foto suelta, aunque esté vacía
    assert [e["id"] for e in pagina_director.ejemplos()] == ["manzana-habla", "leyenda-ia", "leyenda-rafaga",
                                                              "otro-video"]
    assert [e["id"] for e in pagina_director.disenos()] == ["mascota-rafa", "portada-alto-voltaje", "roto"]
    pedidos = []
    viva = inicio.PaginaInicio(navegado.append, editadas.append, series.append, pedidos.append)
    car = viva.destacados
    assert not viva.bloque_destacados.isHidden()
    assert [b.e["id"] for b in car.piezas] == ["manzana-habla", "leyenda-ia", "leyenda-rafaga", "mascota-rafa",
                                               "portada-alto-voltaje"]  # en el orden de DESTACADOS
    assert [b.accessibleName() for b in car.piezas][:2] == ["La manzana que habla", "La leyenda de Ráfaga"]
    assert all(isinstance(b, pagina_director.Pieza) and b.contener for b in car.piezas)
    # Las herramientas muestran algo hecho con ellas (el primero que exista); sin nada, su dibujo
    vistas = {a[2]: v for a, v in zip(inicio.ACCESOS, viva.vistas)}
    assert vistas["Crear video"].e["id"] == "manzana-habla" and vistas["Música"].e["id"] == "portada-alto-voltaje"
    assert vistas["Editor de video"].e == {"id": "presentacion-app"} and vistas["Anuncios"].e == {}
    # El mosaico: videos y diseños intercalados, con su título solo al pasar el ratón (o con el foco)
    mosaico = viva.galeria.tarjetas
    assert [b.e["id"] for b in mosaico] == ["manzana-habla", "mascota-rafa", "leyenda-ia", "portada-alto-voltaje",
                                            "leyenda-rafaga", "roto", "otro-video"]
    assert all(b.leyenda == "encima" for b in mosaico)
    assert [b.gif is not None for b in mosaico] == [True, False, True, False, True, False, True]
    viva.resize(1106, 3200)
    viva.show()
    viva.activateWindow()
    esperar(viva.isActiveWindow)
    app.processEvents()
    # Columnas del mismo ancho y huecos finos; cada pieza, a su proporción
    columnas = {b.x() for b in mosaico}
    assert len({b.width() for b in mosaico}) <= 2 and len(columnas) >= 4, columnas  # ±1 px de redondeo
    manzana = mosaico[0]
    assert abs(manzana.height() - manzana.width() * 16 / 9) < 3
    assert manzana.parentWidget().height() == manzana.parentWidget().heightForWidth(manzana.parentWidget().width())
    roto = mosaico[5]
    assert roto.ruta.name == "roto.jpg" and pagina_director._imagen(roto.ruta).isNull()
    assert not roto.grab().isNull()  # se pinta con su dibujo de relleno
    # Ni Inicio ni el Director se salen por la derecha a 1366 px (el visor de la página mide 1106)
    assert viva.minimumSizeHint().width() <= 1106, viva.minimumSizeHint()
    director_ancho = pagina_director.PaginaDirector()
    assert director_ancho.minimumSizeHint().width() <= 1106, director_ancho.minimumSizeHint()
    # El Director usa las mismas piezas, en una fila del mismo alto que se desplaza
    del_director = director_ancho.findChildren(pagina_director.Pieza)
    assert len(del_director) == 7 and len({b.height() for b in del_director}) == 1
    del director_ancho

    # ---------- El carrusel pasa solo, se para con el ratón, oculto o con menos movimiento ----------
    viva.activateWindow()  # crear otra página le quitó el foco a la ventana
    esperar(viva.isActiveWindow)
    assert car.ancho == round(car.width() * 0.8)  # la siguiente asoma por la derecha
    assert car.piezas[0].vivo == "video" and all(b.vivo is None and b.apagada for b in car.piezas[1:])
    car.reloj.timeout.emit()  # el reloj de verdad tarda 6 s: se adelanta a mano
    assert car.actual == 1 and car.piezas[1].vivo == "video" and car.piezas[0].vivo is None
    assert [p.isChecked() for p in car.puntos] == [False, True, False, False, False]
    assert car.puntos[1].width() > car.puntos[0].width()
    esperar(lambda: car.pista.animacion.state() == QPropertyAnimation.Stopped)
    barra = car.pista.horizontalScrollBar()
    assert barra.value() == car.ancho + car.HUECO == car.piezas[1].x(), (  # deslizado hasta la segunda
        barra.value(), barra.maximum(), car.ancho, car.piezas[1].x(), car.width())
    car.setAttribute(Qt.WA_UnderMouse, True)  # el ratón encima: se queda
    car.reloj.timeout.emit()
    assert car.actual == 1
    car.setAttribute(Qt.WA_UnderMouse, False)
    car.piezas[1].setFocus()  # el foco del teclado dentro: también se queda
    car.reloj.timeout.emit()
    assert car.actual == 1
    # Con las flechas del teclado se pasa de una a otra (y el carrusel la sigue)
    app.sendEvent(car.piezas[1], QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    assert car.actual == 2 and car.piezas[2].hasFocus()
    car.piezas[2].clearFocus()
    car.flechas[0].click()
    assert car.actual == 1
    car.puntos[4].click()
    assert car.actual == 4
    car.reloj.timeout.emit()  # al final da la vuelta
    assert car.actual == 0
    pagina_director.accion_animar().setChecked(False)  # menos movimiento: no pasa solo y salta sin deslizarse
    car.reloj.timeout.emit()
    assert car.actual == 0
    car.flechas[1].click()
    assert car.actual == 1 and car.pista.animacion.state() == QPropertyAnimation.Stopped
    assert car.pista.horizontalScrollBar().value() == car.ancho + car.HUECO
    pagina_director.accion_animar().setChecked(True)
    car.ir(0, False)
    # Abrir una pieza: el video en su ventana; un diseño, en grande; «Usar este pedido», al Director
    car.piezas[0].click()
    visto = ventana_de_video(viva)
    assert visto.reproductor.resultados[0]["archivo"].endswith("manzana-habla.mp4")
    assert "#x" in visto.reproductor.info.toPlainText() and visto.reproductor.lista.isHidden()
    cerrar_videos(viva)
    botones = [b.text() for b in car.piezas[3].findChildren(QPushButton)]
    assert botones == ["Ver en grande", "Usar este pedido"], botones
    car.piezas[3].findChildren(QPushButton)[1].click()
    assert pedidos == ["La mascota"]
    assert [b.text() for b in car.piezas[2].findChildren(QPushButton)] == ["Ver video"]  # sin pedido
    car.piezas[4].click()
    imagen = [v for v in viva.findChildren(QDialog) if v.isVisible()][-1]
    assert imagen.windowTitle() == "Portada" and not imagen.findChild(QLabel).pixmap().isNull()
    imagen.close()
    viva.activateWindow()  # cerrar la ventana de la imagen no siempre le devuelve el foco (sin pantalla)
    esperar(viva.isActiveWindow)

    # ---------- Lo que se mueve: como mucho MAX_VIVAS en toda la página, y nada si no se ve ----------
    piezas = car.piezas + viva.vistas + mosaico
    pagina_director.animar(piezas)
    assert len(moviendose(piezas)) <= pagina_director.MAX_VIVAS
    car.ir(1, False)  # la elegida reproduce su MP4 (uno de verdad): sus cuadros llegan desde otro hilo
    pagina_director.animar(piezas)
    elegida = car.piezas[1]
    assert elegida.jugador is not None and moviendose(piezas)[0] == "La leyenda de Ráfaga"
    assert len(moviendose(piezas)) == pagina_director.MAX_VIVAS
    esperar(lambda: elegida.cuadro is not None and elegida.cuadro.width() > 0)
    assert elegida.cuadro.width() <= max(1, round(elegida.width() * elegida.devicePixelRatioF()))
    # Al pasar a otra, la de antes suelta su reproductor (y su archivo)
    car.ir(2, False)
    pagina_director.animar(piezas)
    assert elegida.jugador is None and elegida.cuadro is None
    # Un MP4 roto: se queda con su GIF, sin reintentar el video
    falsa = car.piezas[2]
    esperar(lambda: falsa.video is None)  # su MP4 de 64 bytes vacíos no se puede leer: lo deja
    pagina_director.animar(piezas)
    assert falsa.peli is not None and falsa.jugador is None
    # El ratón sobre una herramienta mueve su vista (aunque ya hubiera MAX_VIVAS)
    boton_crear = tarjeta(viva, "Crear video")
    boton_crear.setAttribute(Qt.WA_UnderMouse, True)
    pagina_director.animar(piezas)
    assert "manzana-habla" in [b.e.get("id") for b in piezas if pagina_director.corriendo(b) and b in viva.vistas]
    boton_crear.setAttribute(Qt.WA_UnderMouse, False)
    # Otra ventana delante: todo quieto, y el carrusel no pasa
    delante = QWidget()
    delante.show()
    delante.activateWindow()
    esperar(lambda: not viva.isActiveWindow())
    pagina_director.animar(piezas)
    assert moviendose(piezas) == []
    antes = car.actual
    car.reloj.timeout.emit()
    assert car.actual == antes
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    delante.close()
    viva.activateWindow()
    esperar(viva.isActiveWindow)
    # La casilla «Animar vistas previas»: apaga todo, se guarda y las demás casillas de la app la siguen
    otro_director = pagina_director.PaginaDirector()
    casillas = [p.findChildren(QCheckBox, options=Qt.FindChildrenRecursively) for p in (viva.galeria, otro_director)]
    casilla, casilla_director = (next(c for c in lista if c.text() == "Animar vistas previas") for lista in casillas)
    assert casilla.isChecked() and casilla_director.isChecked()
    casilla.setChecked(False)
    assert not casilla_director.isChecked() and claves.ajustes()["animar_vistas"] == "no"
    pagina_director.animar(piezas)
    assert moviendose(piezas) == []
    pagina_director._animar = None  # como al abrir la app otra vez: se lee de ajustes.json
    assert not pagina_director.accion_animar().isChecked()
    del otro_director
    pagina_director.accion_animar().setChecked(True)
    assert claves.ajustes()["animar_vistas"] == "si"
    # «Usar este pedido» (clic derecho) en el mosaico: lleva su pedido; sin pedido no se ofrece
    assert [a.text() for a in mosaico[0].findChild(QMenu).actions()] == ["Usar este pedido"]
    assert "Clic derecho" in mosaico[0].toolTip()
    assert mosaico[4].findChild(QMenu) is None and "Clic derecho" not in mosaico[4].toolTip()
    mosaico[0].findChild(QMenu).actions()[0].trigger()
    assert pedidos[-1] == "Una manzana que habla"

    # ---------- «Ver todo»: el mosaico con filtros; solo se mueve el del ratón y elegir uno cierra la ventana ----------
    def abrir_todo():
        next(b for b in viva.galeria.findChildren(QPushButton) if b.text() == "Ver todo").click()
        ventana_todo = [v for v in viva.findChildren(QDialog) if v.isVisible()][-1]
        ventana_todo.activateWindow()
        esperar(ventana_todo.isActiveWindow)
        return ventana_todo, ventana_todo.findChildren(pagina_director.Pieza)
    todo, rejilla = abrir_todo()
    assert todo.windowTitle() == "Hecho con Ráfaga Studio" and len(rejilla) == 7
    chips = [b for b in todo.findChildren(QPushButton) if b.objectName() == "formato"]
    assert [c.text() for c in chips] == ["Todo", "Videos", "Diseños"]
    chips[2].click()
    assert [b.accessibleName() for b in rejilla if b.isVisibleTo(todo)] == ["Rafa", "Portada", "Roto"]
    chips[0].click()
    assert len([b for b in rejilla if b.isVisibleTo(todo)]) == 7
    pagina_director.animar(piezas)
    pagina_director.animar(rejilla, 0)
    assert moviendose(piezas) == [] and moviendose(rejilla) == []  # Inicio, detrás: quieto
    rejilla[2].setAttribute(Qt.WA_UnderMouse, True)
    pagina_director.animar(rejilla, 0)
    assert moviendose(rejilla) == ["Tráiler"]
    rejilla[1].click()
    esperar(lambda: not todo.isVisible())
    assert ventana_de_video(viva).reproductor.lista.item(0).text() == "1. Anime IA"
    cerrar_videos(viva)
    todo, rejilla = abrir_todo()
    rejilla[0].findChild(QMenu).actions()[0].trigger()
    esperar(lambda: not todo.isVisible())
    assert pedidos[-1] == "Una manzana que habla"
    viva.close()
    # De qué serie habla lo que hizo el Director: la creada, o la del capítulo (series/<serie>/episodios/NN)
    serie_de = pagina_director.serie_de_pasos
    assert serie_de([{"herramienta": "crear_episodio",
                      "resultado": json.dumps({"carpeta": str(d / "series" / "una" / "episodios" / "01")})},
                     {"herramienta": "crear_video", "resultado": json.dumps({"carpeta": "x"})}]) == "una"
    assert serie_de([{"herramienta": "crear_serie", "resultado": json.dumps({"carpeta": str(d / "otra")})}]) == "otra"
    assert serie_de([{"herramienta": "crear_serie", "resultado": "ERROR: cuota"},
                     {"herramienta": "crear_episodio", "resultado": "[1]"}]) == "" and serie_de([]) == ""


    # ---------- Lo legal: el aviso al primer uso (y si cambia), los documentos y la marca ----------
    from PySide6.QtWidgets import QTextBrowser  # noqa: E402

    from ui import legal  # noqa: E402
    legal.ARCHIVO = d / "legal.json"
    assert legal.pendiente()
    respuesta = [QDialog.Rejected]
    _exec, QDialog.exec = QDialog.exec, lambda self: respuesta[0]
    try:
        assert legal.aviso_inicial() is False and legal.pendiente()  # «Salir»: no queda aceptado
        respuesta[0] = QDialog.Accepted
        assert legal.aviso_inicial() is True and not legal.pendiente()
    finally:
        QDialog.exec = _exec
    legal.VERSION = str(int(legal.VERSION) + 1)  # si cambian el aviso o los términos, se vuelve a mostrar
    assert legal.pendiente()
    legal.ARCHIVO.write_text("[1, 2", encoding="utf-8")
    assert legal.pendiente()  # roto: se vuelve a pedir, nunca se da por aceptado
    # Con una ventana de padre, como en la app: sin padre, Python las destruía al salir después que Qt y se caía
    padre = QDialog()
    for archivo in legal.DOCUMENTOS:
        doc = legal.ver_documento(padre, archivo)
        texto = doc.findChild(QTextBrowser).toPlainText()
        # Markdown de verdad (también LICENSE): sin `comillas`, ** ni ## a la vista
        assert len(texto) > 200 and not any(m in texto for m in ("`", "**", "## ", "](")), archivo
        doc.close()
    # Un enlace a otro documento legal lo abre en su ventana; uno de GitHub no navega a ningún sitio
    doc = legal.ver_documento(padre, "PRIVACIDAD.md")
    antes = len(padre.findChildren(QDialog))
    doc.findChild(QTextBrowser).anchorClicked.emit(QUrl("SECURITY.md#contacto"))
    doc.findChild(QTextBrowser).anchorClicked.emit(QUrl("../../issues"))
    assert len(padre.findChildren(QDialog)) == antes + 1
    assert padre.findChildren(QDialog)[-1].windowTitle() == "Política de seguridad"
    acerca = legal.acerca_de(padre)
    assert any("Santo Montilla" in w.text() for w in acerca.findChildren(QLabel))
    acerca.close()
    del doc, acerca, padre  # se destruyen ya, con Qt vivo
    assert "Santo Montilla" in legal.marca() and "Santo Montilla" in open(
        Path(inicio.__file__).resolve().parent.parent.parent / "LICENSE", encoding="utf-8").read()

    # ---------- La ventana: abre en Inicio y sus accesos llevan a la página de verdad ----------
    import app as aplicacion
    ventana = aplicacion.Ventana()
    assert ventana.orden[0] is ventana.inicio and ventana.paginas.currentIndex() == 0
    assert ventana.grupo.buttons()[0].text() == "Inicio" and ventana.grupo.buttons()[0].isChecked()
    # Lo más buscado arriba, y cada página que usa el Director es un botón del menú
    menu = [b.text() for b in ventana.grupo.buttons()]
    assert menu == ["Inicio", "Director IA", "Crear con IA", "Diseño", "Dibujos animados", "Editor de video",
                    "Shorts mágicos", "Anuncios", "Música", "Cabina de grabación", "Nichos virales", "Mis proyectos",
                    "Publicar", "Claves de IA", "Conexión MCP", "Ráfaga Guardia"], menu
    assert set(pagina_director.PAGINA.values()) <= set(menu)
    assert ventana.grupo.buttons()[4].property("icono") == "rabbit"
    ventana._iluminar("crear_serie")
    assert [b.text() for b in ventana.grupo.buttons() if b.graphicsEffect()] == ["Dibujos animados"]
    ventana._iluminar(None)
    ventana.inicio.recargar()
    for _, _, nombre, _, menu, _, _ in inicio.ACCESOS:
        tarjeta(ventana.inicio, nombre).click()
        i = ventana.paginas.currentIndex()
        assert ventana.grupo.buttons()[i].text() == menu and ventana.grupo.buttons()[i].isChecked(), menu
    conectar(ventana.inicio)[0].click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.claves)
    tarjeta(ventana.inicio, "Nuevo: Ráfaga Guardia cuida tu estudio mientras creas").click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.guardia)
    # La idea de arriba, en la página de cada opción: escrita, con el foco y sin empezar nada (gastar lo decide el
    # usuario allí)
    ventana.resize(1366, 728)
    ventana.show()
    ventana.activateWindow()
    esperar(ventana.isActiveWindow)
    portada = ventana.inicio
    for n, (pagina_de, campo, tipo) in enumerate([
            (ventana.crear, lambda: ventana.crear.prompt.toPlainText(), None),
            (ventana.diseno, lambda: ventana.diseno.pedido.text(), "ilustracion"),
            (ventana.diseno, lambda: ventana.diseno.pedido.text(), "auto"),
            (ventana.musica, lambda: ventana.musica.idea.toPlainText(), None),
            (ventana.director, lambda: ventana.director.pedido.text(), None)]):
        ventana.ir_a(0)
        portada.modos.grupo.button(n).click()
        portada.idea.setPlainText(f"Mi idea {n}")
        portada.crear.click()
        assert ventana.paginas.currentIndex() == ventana.orden.index(pagina_de), n
        assert campo() == f"Mi idea {n}" and portada.idea.toPlainText() == ""
        if tipo:
            assert ventana.diseno.tipo_ia.currentData() == tipo
    esperar(lambda: ventana.director.pedido.hasFocus())
    assert not (ventana.crear.tarea or ventana.musica.tarea or ventana.diseno.tarea or ventana.director.ocupado())
    ventana.director.pedido.clear()
    # «Usar este pedido» desde Inicio: al Director, escrito y sin enviar (gastar lo decide el usuario); e Inicio, ya
    # oculto, se queda quieto y su carrusel no pasa
    ventana.ir_a(0)
    de_inicio = portada.destacados.piezas + portada.vistas + portada.galeria.tarjetas
    mosaico_ventana = portada.galeria.tarjetas
    ventana.paginas.currentWidget().ensureWidgetVisible(mosaico_ventana[0])
    app.processEvents()
    pagina_director.animar(de_inicio)
    assert 0 < len(moviendose(de_inicio)) <= pagina_director.MAX_VIVAS
    mosaico_ventana[1].findChild(QMenu).actions()[0].trigger()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.director)
    assert ventana.director.pedido.text() == "La mascota" and not ventana.director.ocupado()
    pagina_director.animar(de_inicio)
    assert moviendose(de_inicio) == []
    antes = portada.destacados.actual
    portada.destacados.reloj.timeout.emit()
    assert portada.destacados.actual == antes
    # Y la página baja hasta el campo: setFocus no la desplaza, y la galería lo dejaba debajo, fuera de la pantalla.
    # Igual desde la galería del propio Director
    area = ventana.paginas.currentWidget()

    def se_ve(campo):
        y = campo.mapTo(area.viewport(), QPoint(0, 0)).y()
        return 0 <= y and y + campo.height() <= area.viewport().height()

    esperar(lambda: se_ve(ventana.director.pedido))
    area.verticalScrollBar().setValue(0)
    assert not se_ve(ventana.director.pedido)
    del_director = ventana.director.findChildren(pagina_director.Pieza)
    del_director[2].findChild(QMenu).actions()[0].trigger()
    esperar(lambda: se_ve(ventana.director.pedido))
    assert ventana.director.pedido.text() == "Dos escenas del anime"

    # ---------- Lo que entrega el Director, en su página: un diseño no va al reproductor de video ----------
    carpeta_diseno = diseno.CARPETA / "20261024-120000-cartel"
    hecho = diseno.nuevo("post", "Cartel")
    diseno.guardar(hecho, carpeta_diseno)
    png = diseno.exportar(hecho, carpeta_diseno, carpeta_diseno / "vista_previa.png")
    director_ui, mostrados = ventana.director, []
    director_ui.reproductor.mostrar = mostrados.append
    director_ui._listo({"mensaje": "Listo", "pasos": [], "formato": "9:16", "resultados": [
        {"archivo": str(png), "titulo": "Cartel", "descripcion": "", "hashtags": []}]})
    assert mostrados == [] and director_ui.ir_serie.isHidden()
    assert not director_ui.ir_diseno.isHidden() and director_ui.ir_diseno.text() == "Abrir en Diseño"
    visor = director_ui.findChildren(QDialog)[-1]  # la imagen, en grande
    assert visor.windowTitle() == "Cartel" and not visor.findChild(QLabel).pixmap().isNull()
    visor.close()
    director_ui.ir_diseno.click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.diseno)
    assert ventana.diseno.carpeta == carpeta_diseno and ventana.diseno.diseno["nombre"] == "Cartel"
    # Un video y una imagen que no es un diseño: el video al reproductor, y sin «Abrir en Diseño»
    suelta = d / "suelta.png"
    assert foto.save(str(suelta))
    director_ui._listo({"mensaje": "Listo", "pasos": [], "formato": "16:9", "resultados": [
        {"archivo": str(d / "Uno.mp4"), "titulo": "Uno", "descripcion": "", "hashtags": []},
        {"archivo": str(suelta), "titulo": "Suelta", "descripcion": "", "hashtags": []}]})
    assert [x["titulo"] for x in mostrados[-1]["resultados"]] == ["Uno"] and director_ui.ir_diseno.isHidden()
    director_ui.findChildren(QDialog)[-1].close()
    # Después, un trabajo que solo da un diseño: el video del pedido anterior no se queda debajo
    assert not director_ui.reproductor.isHidden()
    director_ui._listo({"mensaje": "Listo", "pasos": [], "formato": "9:16", "resultados": [
        {"archivo": str(png), "titulo": "Cartel", "descripcion": "", "hashtags": []}]})
    assert director_ui.reproductor.isHidden() and len(mostrados) == 1 and director_ui.ir_diseno.menu() is None
    director_ui.findChildren(QDialog)[-1].close()
    # Dos diseños en un trabajo («un post y un flyer»): se ven los dos y cada uno se abre desde el menú del botón
    carpeta_flyer = diseno.CARPETA / "20261024-120100-flyer"
    flyer = diseno.nuevo("flyer", "Flyer")
    diseno.guardar(flyer, carpeta_flyer)
    png_flyer = diseno.exportar(flyer, carpeta_flyer, carpeta_flyer / "vista_previa.png")
    director_ui._listo({"mensaje": "Listo", "pasos": [], "formato": "9:16", "resultados": [
        {"archivo": str(png), "titulo": "Cartel", "descripcion": "", "hashtags": []},
        {"archivo": str(png_flyer), "titulo": "Flyer", "descripcion": "", "hashtags": []}]})
    visores = [v for v in director_ui.findChildren(QDialog) if v.isVisible()]
    assert [v.windowTitle() for v in visores] == ["Cartel", "Flyer"]
    for v in visores:
        v.close()
    assert not director_ui.ir_diseno.isHidden()
    assert [a.text() for a in director_ui.ir_diseno.menu().actions()] == ["Cartel", "Flyer"]
    ventana.ir_a(0)
    director_ui.ir_diseno.click()  # con menú, el clic solo lo despliega: no abre el último por su cuenta
    assert ventana.paginas.currentIndex() == 0
    for accion, carpeta in zip(director_ui.ir_diseno.menu().actions(), (carpeta_diseno, carpeta_flyer)):
        ventana.ir_a(0)
        accion.trigger()
        assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.diseno)
        assert ventana.diseno.carpeta == carpeta, carpeta
    director_ui.ir_diseno.menu().close()
    # Una serie: «Abrir en Dibujos animados» la deja elegida en su página
    director_ui._listo({"mensaje": "Listo", "formato": "16:9", "resultados": [], "pasos": [
        {"herramienta": "crear_serie", "argumentos": {},
         "resultado": json.dumps({"carpeta": str(serie.CARPETA / "20261021-090000-mi-serie")})}]})
    assert director_ui.ir_diseno.isHidden() and not director_ui.ir_serie.isHidden()
    assert director_ui.ir_serie.text() == "Abrir en Dibujos animados"
    assert ventana.serie.series.currentData() is None
    director_ui.ir_serie.click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.serie)
    assert ventana.serie.series.currentData()["nombre"] == "20261021-090000-mi-serie"
    ventana.serie.recargar("x")  # otra vez sin elegir: el acceso de Inicio tiene que elegirla él
    assert ventana.serie.series.currentData() is None

    tarjeta(ventana.inicio, "Mi serie").click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.serie)
    assert ventana.serie.series.currentData()["nombre"] == "20261021-090000-mi-serie"
    tarjeta(ventana.inicio, "Mi edición").click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.edicion)
    esperar(lambda: not ventana.edicion.tareas and ventana.edicion.proyecto["nombre"] == "Mi edición")
    assert ventana.close()

# El vidrio: el halo del botón principal se apaga si está desactivado o pegado al borde de su padre (saldría cortado)
# y se aviva con el ratón encima; el anillo del foco solo llega con el teclado; el selector de formato no se estira en
# alto, la opción elegida se ve distinta de las otras y la luz de debajo la sigue, también si se cambia desde el código.
from PySide6.QtWidgets import QVBoxLayout  # noqa: E402

from ui.comun import _Halo, boton, SelectorFormato  # noqa: E402

padre = QWidget()
padre.resize(300, 100)
principal = boton("Hacer", "principal")
principal.setParent(padre)
principal.setGeometry(30, 20, 200, 40)
padre.show()
app.processEvents()
assert principal.graphicsEffect().isEnabled()
principal.setEnabled(False)
assert not principal.graphicsEffect().isEnabled()
principal.setEnabled(True)
assert principal.graphicsEffect().isEnabled()
app.sendEvent(principal, QEvent(QEvent.Enter))
assert principal.graphicsEffect().color().alpha() == _Halo.ALFA_ENCIMA
app.sendEvent(principal, QEvent(QEvent.Leave))
assert principal.graphicsEffect().color().alpha() == _Halo.ALFA
principal.setGeometry(100, 60, 200, 40)  # toca los bordes de abajo y de la derecha
app.processEvents()
assert not principal.graphicsEffect().isEnabled()
assert principal.focusPolicy() == Qt.TabFocus  # un clic no deja el anillo cian sobre el reflejo
padre.close()
caja = QWidget()
QVBoxLayout(caja).addWidget(selector := SelectorFormato())
caja.resize(900, 240)  # mucho más alto que el selector: la cápsula no debe estirarse
caja.show()
app.processEvents()
assert selector.capsula.height() == selector.capsula.sizeHint().height()
# ninguna toma el foco con un clic (Qt deja el Tab solo en la elegida: las flechas cambian de opción)
assert [b.focusPolicy() for b in selector.grupo.buttons()] == [Qt.TabFocus] + [Qt.NoFocus] * 3
elegida, otra = selector.grupo.buttons()[:2]
assert selector.valor() == "9:16" and not any(b.graphicsEffect() for b in selector.grupo.buttons())


def color(b, y, x=8):  # x=8: en el margen izquierdo de la opción, sin letras; x e y relativos a la opción
    return caja.grab().toImage().pixelColor(b.mapTo(caja, QPoint(x, y)))


bajo = selector.capsula.height() - elegida.y() + 2  # 2 px por debajo de la cápsula: solo llega la luz
assert color(elegida, elegida.height() // 2) != color(otra, otra.height() // 2)  # la elegida no es transparente
assert color(elegida, bajo, elegida.width() // 2) != color(otra, bajo, otra.width() // 2)
antes = color(otra, bajo, otra.width() // 2)
otra.setChecked(True)
app.processEvents()
assert color(otra, bajo, otra.width() // 2) != antes and selector.valor() == "16:9"  # la luz se fue con la elegida
caja.close()
print("Pruebas de la página de inicio pasadas.")
