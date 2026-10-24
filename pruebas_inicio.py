"""Pruebas de la página «Inicio» (ui/paginas/inicio.py) sin red ni claves de verdad: python pruebas_inicio.py"""
import json
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QToolButton  # noqa: E402

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
    assert navegado == ["Director IA", "Crear con IA", "Shorts mágicos", "Anuncios", "Diseño", "Serie animada",
                        "Editor de video", "Música"]

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
    con_video.reproductor.player.stop()

    # ---------- La ventana: abre en Inicio y sus accesos llevan a la página de verdad ----------
    import app as aplicacion
    ventana = aplicacion.Ventana()
    assert ventana.orden[0] is ventana.inicio and ventana.paginas.currentIndex() == 0
    assert ventana.grupo.buttons()[0].text() == "Inicio" and ventana.grupo.buttons()[0].isChecked()
    ventana.inicio.recargar()
    for _, _, nombre, _, menu in inicio.ACCESOS:
        tarjeta(ventana.inicio, nombre).click()
        i = ventana.paginas.currentIndex()
        assert ventana.grupo.buttons()[i].text() == menu and ventana.grupo.buttons()[i].isChecked(), menu
    conectar(ventana.inicio)[0].click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.claves)
    tarjeta(ventana.inicio, "Mi serie").click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.serie)
    assert ventana.serie.series.currentData()["nombre"] == "20261021-090000-mi-serie"
    tarjeta(ventana.inicio, "Mi edición").click()
    assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.edicion)
    esperar(lambda: not ventana.edicion.tareas and ventana.edicion.proyecto["nombre"] == "Mi edición")
    assert ventana.close()
print("Pruebas de la página de inicio pasadas.")
