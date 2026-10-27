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
from ui.comun import ESTILO, VisorImagen, ver_imagen  # noqa: E402

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
# Con sus botones, cabe en la pantalla (en un portátil de 1280×720 se salía por abajo)
assert visor.sizeHint().height() <= visor.screen().availableGeometry().height(), visor.sizeHint()
# Descargar: por defecto en Descargas con el nombre del diseño; en PNG, en JPG o sin extensión (PNG)
for nombre, cabecera in (("bajada.png", b"\x89PNG"), ("bajada.jpg", b"\xff\xd8\xff"), ("sin-extension", b"\x89PNG")):
    destinos.append(str(tmp / nombre))
    b["Descargar"].click()
    hecho = tmp / (nombre if "." in nombre else f"{nombre}.png")
    assert hecho.read_bytes()[:len(cabecera)] == cabecera, nombre
    assert QImage(str(hecho)).size() == QImage(str(vista)).size()
    assert avisos[-1] == f"Guardada en {hecho}", avisos
assert sugeridos[0] == str(Path(QStandardPaths.writableLocation(QStandardPaths.DownloadLocation))
                           / "Mariposa Vectorial.png"), sugeridos
antes = len(avisos)
destinos.append("")  # cancelado: nada se guarda ni se avisa
b["Descargar"].click()
assert len(avisos) == antes
destinos.append(str(tmp / "no-existe" / "x.png"))  # donde no se puede: lo dice en claro
b["Descargar"].click()
assert avisos[-1].startswith("No se pudo guardar la imagen en"), avisos
b["Abrir carpeta"].click()
assert abiertas == [carpeta]
b["Cerrar"].click()
app.processEvents()
assert cerrado(visor)

# ---------- En la app: editar en Diseño y animar llevan a su página sin empezar nada ----------
import app as aplicacion  # noqa: E402

ventana = aplicacion.Ventana()
ventana.resize(1280, 720)
ventana.show()
assert VisorImagen.al_disenar is not None and VisorImagen.al_animar is not None
visor = ver_imagen(ventana, vista, "Mariposa Vectorial")
app.processEvents()
assert visibles(visor) == ["Descargar", "Editar en Diseño", "Animar", "Abrir carpeta", "Cerrar"], visibles(visor)
botones(visor)["Editar en Diseño"].click()  # un diseño guardado se abre tal cual
app.processEvents()
assert cerrado(visor) and ventana.paginas.currentIndex() == ventana.orden.index(ventana.diseno)
assert ventana.diseno.carpeta == carpeta and ventana.diseno.diseno["nombre"] == "Mariposa Vectorial"
# Una imagen suelta (un ejemplo de la galería) entra en un diseño nuevo de su forma, llenándolo
visor = ver_imagen(ventana, suelta, "Flyer de ejemplo")
botones(visor)["Editar en Diseño"].click()
nuevo = ventana.diseno.diseno
assert ventana.diseno.carpeta not in (None, carpeta) and (nuevo["ancho"], nuevo["alto"]) == (1080, 1350), nuevo
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

# «Imagen» desde Inicio: si pide una foto real, a Diseño como foto (salía sticker vectorial); si no, ilustración
for texto, tipo in (("una mariposa real en un jardín", "foto"), ("una mariposa", "ilustracion")):
    ventana._pedir("imagen", texto)
    assert ventana.diseno.tipo_ia.currentData() == tipo and ventana.diseno.pedido.text() == texto, texto
print("Pruebas del visor de imágenes pasadas.", flush=True)  # os._exit no vacía la salida
os._exit(0)  # sin esperar los hilos de fondo de la ventana (Ráfaga Guardia revisa la app al abrirla)
