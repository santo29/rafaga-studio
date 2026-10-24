"""Pruebas de la página «Inicio» (ui/paginas/inicio.py) sin red ni claves de verdad: python -m pruebas.inicio"""
import json
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QToolButton  # noqa: E402

from motor import claves, diseno, edicion, marca, nubes, serie, shorts  # noqa: E402
from ui.comun import ESTILO  # noqa: E402
from ui.paginas import director as pagina_director  # noqa: E402
from ui.paginas import inicio  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»


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


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    shorts.PROYECTOS, edicion.CARPETA, serie.CARPETA = d / "proyectos", d / "ediciones", d / "series"
    claves.ARCHIVO, claves.AJUSTES, nubes.USO = d / "claves.json", d / "ajustes.json", d / "uso.json"
    diseno.CARPETA, marca.ARCHIVO, marca.CARPETA_LOGO = d / "disenos", d / "marca.json", d / "marca"
    pagina_director.EJEMPLOS = d / "ejemplos"

    # ---------- Sin nada: se construye, con los 8 accesos, sin recientes y sin ejemplos ----------
    navegado, editadas, series = [], [], []
    pagina = inicio.PaginaInicio(navegado.append, editadas.append, series.append)
    pagina.recargar()
    assert pagina.recientes == [] and not pagina.vacio.isHidden() and pagina.galeria.isHidden()
    assert pagina.reproductor.isHidden()
    # Cada acceso lleva a su página del menú
    for _, _, nombre, _, menu in inicio.ACCESOS:
        tarjeta(pagina, nombre).click()
    assert navegado == ["Director IA", "Crear con IA", "Diseño", "Dibujos animados", "Editor de video",
                        "Shorts mágicos", "Anuncios", "Música"]  # el orden del menú
    assert "Crea tus personajes y capítulos de caricatura" in [a[3] for a in inicio.ACCESOS]

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
    tarjeta(pagina, "Shorts nuevos").click()
    assert not pagina.reproductor.isHidden() and pagina.reproductor.lista.count() == 2
    assert pagina.reproductor.formato == "16:9"

    # ---------- Ejemplos: si los hay, salen y se ven en el reproductor de Inicio ----------
    pagina_director.EJEMPLOS.mkdir()
    (pagina_director.EJEMPLOS / "ejemplos.json").write_text(json.dumps([
        {"id": "demo", "titulo": "Demo", "formato": "9:16", "guion": {"descripcion": "Desc", "hashtags": ["#x"]}},
        {"id": "sin-video", "titulo": "Sin video"}]), encoding="utf-8")
    (pagina_director.EJEMPLOS / "demo.mp4").write_bytes(b"\0" * 64)
    foto = QImage(90, 160, QImage.Format_RGB32)
    foto.fill(QColor("#7C5CFF"))
    for nombre in ("demo", "sin-video"):
        assert foto.save(str(pagina_director.EJEMPLOS / f"{nombre}.jpg"))
    con_ejemplos = inicio.PaginaInicio(navegado.append, editadas.append, series.append)
    assert not con_ejemplos.galeria.isHidden()
    ejemplos = con_ejemplos.galeria.findChildren(QToolButton)
    assert [b.text() for b in ejemplos] == ["Demo"]
    ejemplos[0].click()
    assert not con_ejemplos.reproductor.isHidden() and con_ejemplos.reproductor.lista.item(0).text() == "1. Demo"
    assert "#x" in con_ejemplos.reproductor.info.toPlainText()
    # El video de presentación de la app, arriba del todo: sale solo si existe y se ve en el reproductor de Inicio
    presentacion = "Conoce Ráfaga Studio en un minuto"
    assert not any(b.accessibleName() == presentacion for b in con_ejemplos.findChildren(QPushButton))
    (pagina_director.EJEMPLOS / "presentacion-app.mp4").write_bytes(b"\0" * 64)
    assert foto.save(str(pagina_director.EJEMPLOS / "presentacion-app.jpg"))
    con_video = inicio.PaginaInicio(navegado.append, editadas.append, series.append)
    tarjeta(con_video, presentacion).click()
    assert con_video.reproductor.resultados[0]["archivo"].endswith("presentacion-app.mp4")
    for pagina_video in (con_ejemplos, con_video):  # soltar los videos falsos: cargando al salir, Qt podía caerse
        pagina_video.reproductor.player.stop()
        pagina_video.reproductor.player.setSource(QUrl())
    del con_video, pagina_video
    # Con muchos ejemplos de título largo, cada fila se desplaza de lado: ni Inicio ni el Director se salen por la
    # derecha a 1366 px (el visor de la página mide 1106)
    muchos = [{"id": f"largo-{n}", "titulo": f"Ejemplo {n} con un título bastante largo para la tarjeta"}
              for n in range(8)]
    (pagina_director.EJEMPLOS / "ejemplos.json").write_text(json.dumps(muchos), encoding="utf-8")
    (pagina_director.EJEMPLOS / "disenos.json").write_text(json.dumps(muchos), encoding="utf-8")
    for e in muchos:
        (pagina_director.EJEMPLOS / f"{e['id']}.mp4").write_bytes(b"\0" * 64)
        assert foto.save(str(pagina_director.EJEMPLOS / f"{e['id']}.jpg"))
    ancha = inicio.PaginaInicio(navegado.append, editadas.append, series.append)
    assert len(ancha.galeria.findChildren(QToolButton)) == 16
    assert ancha.minimumSizeHint().width() <= 1106, ancha.minimumSizeHint()
    director_ancho = pagina_director.PaginaDirector()
    assert director_ancho.minimumSizeHint().width() <= 1106, director_ancho.minimumSizeHint()
    del ancha, director_ancho
    # De qué serie habla lo que hizo el Director: la creada, o la del capítulo (series/<serie>/episodios/NN)
    serie_de = pagina_director.serie_de_pasos
    assert serie_de([{"herramienta": "crear_episodio",
                      "resultado": json.dumps({"carpeta": str(d / "series" / "una" / "episodios" / "01")})},
                     {"herramienta": "crear_video", "resultado": json.dumps({"carpeta": "x"})}]) == "una"
    assert serie_de([{"herramienta": "crear_serie", "resultado": json.dumps({"carpeta": str(d / "otra")})}]) == "otra"
    assert serie_de([{"herramienta": "crear_serie", "resultado": "ERROR: cuota"},
                     {"herramienta": "crear_episodio", "resultado": "[1]"}]) == "" and serie_de([]) == ""

    # ---------- Lo legal: el aviso al primer uso (y si cambia), los documentos y la marca ----------
    from PySide6.QtWidgets import QDialog, QTextBrowser  # noqa: E402

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
        assert len(doc.findChild(QTextBrowser).toPlainText()) > 200, archivo
        doc.close()
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
                    "Claves de IA", "Conexión MCP"], menu
    assert set(pagina_director.PAGINA.values()) <= set(menu)
    assert ventana.grupo.buttons()[4].property("icono") == "rabbit"
    ventana._iluminar("crear_serie")
    assert [b.text() for b in ventana.grupo.buttons() if b.graphicsEffect()] == ["Dibujos animados"]
    ventana._iluminar(None)
    ventana.inicio.recargar()
    for _, _, nombre, _, menu in inicio.ACCESOS:
        tarjeta(ventana.inicio, nombre).click()
        i = ventana.paginas.currentIndex()
        assert ventana.grupo.buttons()[i].text() == menu and ventana.grupo.buttons()[i].isChecked(), menu
    conectar(ventana.inicio)[0].click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.claves)

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
print("Pruebas de la página de inicio pasadas.")
