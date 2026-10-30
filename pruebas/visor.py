"""El visor de una imagen en grande (ui/comun.VisorImagen), sin red: antes solo tenía «Cerrar». Descargar en PNG o JPG
donde se elija, editarla en Diseño (el diseño guardado o, si es una imagen suelta, uno nuevo con ella), animarla en
Crear con IA sin que empiece nada y abrir su carpeta. python -m pruebas.visor"""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtCore import QStandardPaths, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox, QPushButton  # noqa: E402

import shiboken6  # noqa: E402

from motor import actividad, claves, diseno, marca, memoria  # noqa: E402
from ui.comun import ESTILO, nombre_libre, VisorImagen, ver_imagen  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
diseno.asegurar_qt()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-visor-"))
claves.ARCHIVO, claves.AJUSTES, claves.CONEXIONES = tmp / "claves.json", tmp / "ajustes.json", tmp / "conexiones.json"
actividad.ARCHIVO, memoria.ARCHIVO, diseno.CARPETA = tmp / "actividad.json", tmp / "memoria.json", tmp / "disenos"
marca.ARCHIVO, marca.CARPETA_LOGO = tmp / "marca.json", tmp / "marca"
avisos, abiertas, destinos, sugeridos = [], [], [], []
QMessageBox.exec = lambda caja: avisos.append(caja.text()) or QMessageBox.Ok  # sin ventana no hay quien pulse
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
os.startfile = abiertas.append  # que «Abrir carpeta» no abra el Explorador
QFileDialog.getSaveFileName = staticmethod(lambda padre, titulo, sugerido, filtro: (sugeridos.append(sugerido),
                                                                                  (destinos.pop(0), ""))[1])

# Un diseño guardado como el que hizo el Director (la mariposa, 1080×1080) y una imagen suelta vertical (un ejemplo)
carpeta = diseno.nueva_carpeta("Mariposa Vectorial")
mariposa = diseno.validar({**diseno.nuevo("post", "Mariposa Vectorial"),
                           "fondo": {"tipo": "color", "colores": ["#F3FFF9"]}})
diseno.guardar(mariposa, carpeta)
vista = diseno.exportar(mariposa, carpeta, carpeta / "vista_previa.png")
suelta = tmp / "ejemplo.jpg"
foto = QImage(1080, 1350, QImage.Format_RGB32)
foto.fill(QColor("#1E6B2A"))
assert foto.save(str(suelta))


def botones(visor) -> dict:
    return {b.text().strip(): b for b in visor.findChildren(QPushButton)}


def cerrado(visor) -> bool:
    return not shiboken6.isValid(visor) or not visor.isVisible()  # al cerrarse se libera (WA_DeleteOnClose)


def visibles(visor) -> list[str]:
    return [b.text().strip() for b in visor.findChildren(QPushButton) if b.isVisibleTo(visor)]


# ---------- Sin la app alrededor: descargar, abrir su carpeta y cerrar ----------
VisorImagen.al_disenar = VisorImagen.al_animar = None
visor = ver_imagen(None, vista, "Mariposa Vectorial")
app.processEvents()
assert visor.isVisible() and not visor.findChild(QLabel).pixmap().isNull()
assert visibles(visor) == ["Descargar", "Abrir carpeta", "Cerrar"], visibles(visor)
b = botones(visor)
# Con el teclado: cada botón con Tab, Intro descarga y Ctrl+S también; Esc cierra (QDialog)
assert all(x.focusPolicy() == Qt.TabFocus for x in b.values())
assert b["Descargar"].isDefault() and b["Descargar"].shortcut() == QKeySequence(QKeySequence.Save)
assert all(x.toolTip() for x in (b["Descargar"], b["Editar en Diseño"], b["Animar"]))
# Dónde está, a la vista como en cada sección
assert f"Guardado en: {carpeta}" in [x.text() for x in visor.findChildren(QLabel)]
# Con esa línea y sus botones, cabe en la pantalla (en un portátil de 1280×720 se salía por abajo)
assert visor.sizeHint().height() <= visor.screen().availableGeometry().height(), visor.sizeHint()
# Descargar: por defecto en Imágenes con el nombre del diseño (sin pisar otro); en PNG, en JPG o sin extensión (PNG)
for nombre, cabecera in (("bajada.png", b"\x89PNG"), ("bajada.jpg", b"\xff\xd8\xff"), ("sin-extension", b"\x89PNG")):
    destinos.append(str(tmp / nombre))
    b["Descargar"].click()
    hecho = tmp / (nombre if "." in nombre else f"{nombre}.png")
    assert hecho.read_bytes()[:len(cabecera)] == cabecera, nombre
    assert QImage(str(hecho)).size() == QImage(str(vista)).size()
    assert avisos[-1] == f"Guardado en {hecho}", avisos
assert sugeridos[0] == str(nombre_libre(Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)),
                                        "Mariposa Vectorial", ".png")), sugeridos
assert Path(sugeridos[0]).stem.startswith("Mariposa Vectorial"), sugeridos
antes = len(avisos)
destinos.append("")  # cancelado: nada se guarda ni se avisa
b["Descargar"].click()
assert len(avisos) == antes
destinos.append(str(tmp / "no-existe" / "x.png"))  # donde no se puede: lo dice en claro
b["Descargar"].click()
assert avisos[-1].startswith("No se pudo guardar en"), avisos
b["Abrir carpeta"].click()
assert abiertas == [carpeta]
b["Cerrar"].click()
app.processEvents()
assert cerrado(visor)
# En JPG, lo transparente sale blanco (salía negro): el JPG no tiene transparencia
con_alfa = tmp / "con-alfa.png"
recorte = QImage(200, 100, QImage.Format_ARGB32)
recorte.fill(Qt.transparent)
recorte.setPixelColor(100, 50, QColor("#FF0000"))
assert recorte.save(str(con_alfa))
visor = ver_imagen(None, con_alfa, "Recorte")
destinos.append(str(tmp / "recorte.jpg"))
botones(visor)["Descargar"].click()
bajada = QImage(str(tmp / "recorte.jpg"))
assert bajada.pixelColor(2, 2).name() == "#ffffff" and bajada.size() == recorte.size(), bajada.pixelColor(2, 2).name()
destinos.append(str(tmp / "recorte.png"))  # en PNG, la transparencia se queda
botones(visor)["Descargar"].click()
assert QImage(str(tmp / "recorte.png")).pixelColor(2, 2).alpha() == 0
visor.close()
# Un ejemplo de la galería vive entre los archivos del programa: sin «Abrir carpeta» (ahí no se manda a borrar)
visor = ver_imagen(None, Path(__file__).resolve().parent.parent / "ejemplos" / "anuncio-rafaga.jpg", "Ejemplo")
assert visibles(visor) == ["Descargar", "Cerrar"], visibles(visor)
assert not any(x.text().startswith("Guardado en") for x in visor.findChildren(QLabel))
visor.close()

# ---------- En la app: editar en Diseño y animar llevan a su página sin empezar nada ----------
import app as aplicacion  # noqa: E402

# Sin consola (pythonw), cada ffmpeg o yt-dlp abría una ventana negra encima del estudio: la app se la quita a todos
if os.name == "nt":
    import subprocess  # noqa: E402
    vistos = []
    aplicacion._sin_ventana(lambda yo, *a, **k: vistos.append(k["creationflags"]))(
        None, ["x"], creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    assert vistos == [subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW], vistos
    assert subprocess.Popen.__init__.__qualname__.startswith("_sin_ventana"), subprocess.Popen.__init__

ventana = aplicacion.Ventana()
ventana.resize(1280, 720)
ventana.show()
assert VisorImagen.al_disenar is not None and VisorImagen.al_animar is not None
visor = ver_imagen(ventana, vista, "Mariposa Vectorial")
app.processEvents()
assert visibles(visor) == ["Descargar", "Editar en Diseño", "Animar", "Abrir carpeta", "Cerrar"], visibles(visor)
assert botones(visor)["Editar en Diseño"].toolTip() == "Cambiar sus textos, colores y capas en la página Diseño"
botones(visor)["Editar en Diseño"].click()  # un diseño guardado se abre tal cual
app.processEvents()
assert cerrado(visor) and ventana.paginas.currentIndex() == ventana.orden.index(ventana.diseno)
assert ventana.diseno.carpeta == carpeta and ventana.diseno.diseno["nombre"] == "Mariposa Vectorial"
# Una imagen suelta (un ejemplo de la galería) entra en un diseño nuevo de su forma, llenándolo
visor = ver_imagen(ventana, suelta, "Flyer de ejemplo")
# Entra como una sola imagen: la ayuda no promete cambiar sus textos, y el diseño lleva el título del ejemplo
assert botones(visor)["Editar en Diseño"].toolTip() == "Ponerla en un diseño nuevo para añadirle textos y formas"
botones(visor)["Editar en Diseño"].click()
nuevo = ventana.diseno.diseno
assert ventana.diseno.carpeta not in (None, carpeta) and (nuevo["ancho"], nuevo["alto"]) == (1080, 1350), nuevo
assert nuevo["nombre"] == "Flyer de ejemplo", nuevo["nombre"]
capa = nuevo["capas"][0]
assert (capa["tipo"], capa["x"], capa["y"], capa["ancho"], capa["alto"], capa["ajuste"]) == (
    "imagen", 0, 0, 1080, 1350, "cubrir"), capa
assert (ventana.diseno.carpeta / "imagenes" / capa["archivo"]).is_file()  # copiada: el ejemplo no se toca
# Animar: Crear con IA con la imagen, «Solo animar la imagen» y su formato; escrito y sin empezar (el costo, si lo
# hay, lo pregunta «Generar video»)
crear = ventana.crear
for imagen, formato in ((vista, "1:1"), (suelta, "4:5")):
    visor = ver_imagen(ventana, imagen, "x")
    botones(visor)["Animar"].click()
    app.processEvents()
    assert cerrado(visor) and ventana.paginas.currentIndex() == ventana.orden.index(crear)
    assert crear.imagen.text() == str(imagen) and crear.modo.currentIndex() == 1 and crear.formato.valor() == formato
    assert crear.prompt.toPlainText() and crear.prompt.textCursor().hasSelection()  # escribir encima lo cambia
    assert crear.tarea is None and crear.iniciar.isEnabled()  # nada empezó solo
# Lo que el usuario ya escribió en Crear con IA no se pisa sin preguntar: con un «no», todo se queda como estaba
crear.prompt.setPlainText("Mi video de la playa")
crear.imagen.setText("")
crear.modo.setCurrentIndex(0)
preguntas = []
for respuesta, pedido in ((QMessageBox.No, "Mi video de la playa"),
                          (QMessageBox.Yes, "Que cobre vida con un movimiento suave y natural")):
    QMessageBox.question = staticmethod(lambda padre, titulo, texto, r=respuesta: preguntas.append(texto) or r)
    visor = ver_imagen(ventana, vista, "x")
    botones(visor)["Animar"].click()
    assert crear.prompt.toPlainText() == pedido and crear.imagen.text() == ("" if respuesta == QMessageBox.No
                                                                             else str(vista)), respuesta
assert preguntas == ["En Crear con IA ya hay un pedido escrito. ¿Cambiarlo por el de animar esta imagen?"] * 2
preguntas.clear()
botones(ver_imagen(ventana, vista, "x"))["Animar"].click()  # el pedido es el sugerido: no hay nada que perder
assert not preguntas
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
# Con «Sin animar» recordado en su «Modelo de video», «Generar video» decía «Elige un modelo de video»: llega en
# Automático (que si es de pago, pregunta el costo antes)
claves.elegir_por_defecto(crear.modelo.clave, "ninguno")
crear.modelo.recargar()
assert crear.modelo.valor() == "ninguno"
botones(ver_imagen(ventana, vista, "x"))["Animar"].click()
assert crear.modelo.valor() == "auto" and claves.ajustes()[crear.modelo.clave] == "auto"
assert crear.tarea is None  # y tampoco empezó nada

# «Imagen» desde Inicio: si pide una foto real, a Diseño como foto (salía sticker vectorial); si no, ilustración
for texto, tipo in (("una mariposa real en un jardín", "foto"), ("una mariposa", "ilustracion")):
    ventana._pedir("imagen", texto)
    assert ventana.diseno.tipo_ia.currentData() == tipo and ventana.diseno.pedido.text() == texto, texto
print("Pruebas del visor de imágenes pasadas.", flush=True)  # os._exit no vacía la salida
os._exit(0)  # sin esperar los hilos de fondo de la ventana (Ráfaga Guardia revisa la app al abrirla)
