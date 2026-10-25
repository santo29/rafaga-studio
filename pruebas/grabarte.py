"""Pruebas de «Grabarte» (ui/grabarte.py y lo que usa del editor de video) con la cámara, el micrófono y el grabador
SIMULADOS (pruebas/camara_falsa): nunca se abre la cámara ni el micrófono de este PC. Sin red ni claves:
python -m pruebas.grabarte"""
import os
import sys
import tempfile
import time
import types
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QHideEvent, QImage, QMouseEvent  # noqa: E402
from PySide6.QtMultimedia import QCamera, QMediaFormat, QMediaRecorder  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from motor import claves, diseno, edicion, marca, video  # noqa: E402
from pruebas import camara_falsa  # noqa: E402
from pruebas.camara_falsa import Camara, Dispositivo, Dispositivos, Grabador, Microfono  # noqa: E402
from ui.comun import ESTILO  # noqa: E402
import ui.grabarte as gr  # noqa: E402
import ui.paginas.edicion as pe  # noqa: E402

camara_falsa.usar()
app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
avisos = []
QMessageBox.exec = lambda caja: avisos.append(caja.text()) or QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
permiso_real = gr.permiso_denegado
gr.permiso_denegado = lambda que: False  # la privacidad de ESTE PC no decide la prueba (abajo se prueba con «Deny»)
libre_real = gr._libre
CAMARA = Dispositivo("Cámara de prueba", b"camara-1", True)


def esperar(condicion, plazo=60):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def raton(widget, tipo, punto):
    boton = Qt.NoButton if tipo == QEvent.MouseMove else Qt.LeftButton
    botones = Qt.NoButton if tipo == QEvent.MouseButtonRelease else Qt.LeftButton
    QApplication.sendEvent(widget, QMouseEvent(tipo, punto, widget.mapToGlobal(punto), boton, botones, Qt.NoModifier))


def arrastrar(widget, desde, hasta):
    for tipo, punto in ((QEvent.MouseButtonPress, desde), (QEvent.MouseMove, (desde + hasta) / 2),
                        (QEvent.MouseMove, hasta), (QEvent.MouseButtonRelease, hasta)):
        raton(widget, tipo, punto)


def videos_capa():
    return [c for c in p.proyecto["capas"] if c["tipo"] == "video"]


def grabar_hasta_grabando():
    """«Grabar», el video montado (en el hilo) y la cuenta atrás 3, 2, 1 (sin esperar 3 s de verdad)."""
    g.grabar_btn.click()
    esperar(lambda: g.estado == "cuenta")
    for _ in range(gr.CUENTA):
        g._tic()
    assert g.estado == "grabando" and Grabador.creados[-1].estado == camara_falsa.GRABANDO, g.estado
    return Grabador.creados[-1]


def toma_entra(antes: int, clave="capas"):
    """Espera a que la toma se mida (en el hilo) y entre en el video; devuelve lo que entró."""
    esperar(lambda: not p.tareas and len(p.proyecto[clave]) > antes)
    return p.proyecto[clave][-1]


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    edicion.CARPETA, diseno.CARPETA = d / "ediciones", d / "disenos"  # nada de tocar datos/ de verdad
    marca.ARCHIVO, marca.CARPETA_LOGO = d / "marca.json", d / "marca"
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"
    clip, cara = d / "clip.mp4", d / "mi_cara.mp4"
    for destino, segundos in ((clip, 4), (cara, 2)):
        video.ffmpeg("-f", "lavfi", "-i", f"testsrc2=s=320x180:r=30:d={segundos}", "-f", "lavfi", "-i",
                     f"sine=frequency=440:duration={segundos}", "-c:v", "libx264", "-preset", "ultrafast",
                     "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", destino)
    vistas, fotos_capa = [], []

    def vista_previa(proyecto, carpeta, aviso=lambda t, f: None, desde=0, segundos=None):
        vistas.append((desde, segundos))
        return clip

    def fotograma_capa(capa, carpeta, momento, fps=30, alto_max=360):
        fotos_capa.append(momento)
        imagen = QImage(320, 180, QImage.Format_RGB32)
        imagen.fill(QColor("#00FF00"))
        return imagen

    def gris(*_a, **_k):
        imagen = QImage(64, 36, QImage.Format_RGB32)
        imagen.fill(QColor("#808080"))
        return imagen
    sys.modules["motor.render_edicion"] = types.SimpleNamespace(
        vista_previa=vista_previa, fotograma_capa=fotograma_capa, fotograma=gris, miniatura=gris,
        forma_de_onda=lambda archivo, carpeta, ancho, alto: gris())

    p = pe.PaginaEdicion()
    p.resize(1400, 1000)
    p.show()
    app.processEvents()
    g = p.grabarte
    # Construir el editor no enciende nada: solo lista los dispositivos
    assert g.estado == "apagada" and not (Camara.creadas or Microfono.creados or Grabador.creados)
    assert (g.camaras.currentText(), g.micros.currentText()) == ("Cámara de prueba", "Micrófono de prueba")
    p.importar([clip])
    esperar(lambda: not p.tareas and p.proyecto["clips"])
    p.herramientas["grabarte"].click()
    app.processEvents()
    assert not Camara.creadas and g.isVisible()  # abrir el panel tampoco: la cámara, solo con su botón o al grabar

    # ---------- Encender la cámara; salir del panel o de la página la apaga ----------
    g.encender_btn.click()
    camara = Camara.creadas[-1]
    assert g.estado == "vista" and camara.activa and g.sesion.camara is camara and g.sesion.salida is g.imagen
    assert camara.dispositivo is Dispositivos.camaras[0] and g.sesion.micro is None  # el micro, solo al grabar
    assert "Apagar" in g.encender_btn.text()
    p.herramientas["texto"].click()
    assert g.estado == "apagada" and not camara.activa and g.sesion.camara is None
    p.herramientas["grabarte"].click()
    g.encender()
    p.hideEvent(QHideEvent())  # otra página del menú
    assert g.estado == "apagada" and not Camara.creadas[-1].activa
    g.encender()
    g.encender_btn.click()  # «Apagar cámara»
    assert g.estado == "apagada" and not Camara.creadas[-1].activa

    # ---------- Grabar: 3, 2, 1, graba con el video sonando desde el cursor y la toma entra en el cursor ----------
    p._al_mover_cursor(1.0)
    g.tiles["sup_izq"].click()  # sin capa de video elegida: queda para la próxima toma
    assert g.disposicion() == ("sup_izq", "circulo")
    pila, creadas = len(p.deshacer_pila), len(Camara.creadas)
    g.grabar_btn.click()
    assert g.estado == "preparando" and len(Camara.creadas) == creadas + 1  # enciende la cámara sola
    esperar(lambda: g.estado == "cuenta")
    assert vistas[-1] == (1.0, None) and g.numero.text() == "3" and "3" in g.tiempo.text()
    assert "Detener" in g.grabar_btn.text() and not g.importar_btn.isEnabled() and not g.camaras.isEnabled()
    g._tic()
    assert g.numero.text() == "2" and g.estado == "cuenta"
    g._tic()
    g._tic()
    grabador = Grabador.creados[-1]
    assert g.estado == "grabando" and grabador.estado == camara_falsa.GRABANDO and g.numero.text() == ""
    assert g.sesion.micro is Microfono.creados[-1] and Microfono.creados[-1].dispositivo is Dispositivos.micros[0]
    assert g.sesion.grabador is grabador and grabador.calidad == QMediaRecorder.Quality.HighQuality
    formato = grabador.formato  # MPEG-4 con H.264 y AAC
    assert (formato.fileFormat(), formato.videoCodec(), formato.audioCodec()) == (
        QMediaFormat.FileFormat.MPEG4, QMediaFormat.VideoCodec.H264, QMediaFormat.AudioCodec.AAC)
    salida = Path(grabador.salida.toLocalFile())
    assert salida.parent == p.carpeta / "grabaciones" and salida.suffix == ".mp4"
    assert salida.name.startswith("grabacion")
    # El video suena desde el cursor en la vista previa del editor, silenciado («Silenciar el video mientras grabo»)
    assert p.centro.currentWidget() is p.pantalla and p.sonido.isMuted() and g.silenciar.isChecked()
    g._tic()
    assert "Grabando" in g.tiempo.text() and "0:02" in g.tiempo.text()
    g.grabar_btn.click()  # «Detener»
    capa = toma_entra(0)
    assert capa["tipo"] == "video" and Path(capa["archivo"]) == salida.resolve() and capa["inicio"] == 1.0
    caja = edicion.disposicion(p.proyecto["formato"], "sup_izq", "circulo", edicion.BORDE)
    assert {k: capa[k] for k in caja} == caja and abs(capa["hasta"] - 2) < 0.05
    assert g.estado == "vista" and g.sesion.micro is None and g.sesion.grabador is None  # el micrófono, fuera
    assert not p.sonido.isMuted() and p.centro.currentWidget() is p.vista  # el video ya no suena
    assert p.sel == capa["id"] and len(p.deshacer_pila) == pila + 1  # un solo «deshacer»
    p.deshacer()
    assert not videos_capa() and salida.is_file()  # deshacer no borra tu grabación
    p.rehacer()
    assert videos_capa() == [capa]
    g.apagar()

    # ---------- La capa en el lienzo (su fotograma, en el hilo) y en la línea de tiempo ----------
    p._elegir(capa["id"])
    p._al_mover_cursor(1.5)
    esperar(lambda: fotos_capa and any(isinstance(i, pe.ItemVideo) and i.imagen is not None for i in p._items()))
    item = next(i for i in p._items() if isinstance(i, pe.ItemVideo))
    assert item.boundingRect().width() == capa["ancho"] and item.pos() == QPointF(capa["x"], capa["y"])
    assert abs(fotos_capa[-1] - 1.5) < 1e-6
    item.setPos(item.pos() + QPointF(100, 50))  # arrastrada en la vista previa
    p.guardar_posiciones()
    assert (videos_capa()[0]["x"], videos_capa()[0]["y"]) == (capa["x"] + 100, capa["y"] + 50)
    p.deshacer()
    assert f"🎥 {salida.name}" in p.titulo_props.text(), p.titulo_props.text()
    assert p.w[("capas", "forma")].isVisible() and not p.w[("capas", "duracion")].isVisible()  # dura lo que su tramo
    L = p.linea
    caja = L.caja(capa["id"])
    arrastrar(L, QPointF(caja.left() + 2, caja.center().y()), QPointF(caja.left() + 2 + 0.5 * L.escala,
                                                                      caja.center().y()))
    recortada = videos_capa()[0]
    assert abs(recortada["desde"] - 0.5) < 0.03 and abs(recortada["inicio"] - 1.5) < 0.03  # no se corre
    p.deshacer()

    # ---------- Disposiciones de un clic sobre la capa elegida y su forma (cada clic, un «deshacer») ----------
    p._elegir(capa["id"])
    g.tiles["completa"].click()
    assert {k: videos_capa()[0][k] for k in ("x", "y", "ancho", "alto", "forma")} == {
        k: edicion.disposicion(p.proyecto["formato"], "completa")[k] for k in ("x", "y", "ancho", "alto", "forma")}
    g.tiles["inf_der"].click()  # las esquinas vuelven a su forma (círculo), no a la recta de pantalla completa
    assert videos_capa()[0]["forma"] == "circulo" and g.tiles["inf_der"].isChecked()
    g.forma.grupo.button(1).click()  # redondeada
    assert videos_capa()[0]["forma"] == "redondeado" and g.disposicion()[1] == "redondeado"
    p.deshacer()
    assert videos_capa()[0]["forma"] == "circulo"
    p.deshacer()
    assert videos_capa()[0]["ancho"] == edicion.disposicion(p.proyecto["formato"], "completa")["ancho"]
    p.deshacer()
    assert videos_capa()[0] == capa

    # ---------- «Bajar la música cuando hablas»: en Grabarte y en Audio, la misma ----------
    assert p.proyecto["bajar_musica"] and g.bajar.isChecked() and p.bajar_musica.isChecked()
    g.bajar.setChecked(False)
    assert not p.proyecto["bajar_musica"] and not p.bajar_musica.isChecked()
    p.deshacer()
    assert p.proyecto["bajar_musica"] and g.bajar.isChecked()

    # ---------- Solo voz: .m4a sin cámara y entra como audio «voz» ----------
    g.modo.grupo.button(1).click()
    assert not g.encender_btn.isEnabled()
    creadas = len(Camara.creadas)
    p._al_mover_cursor(0.5)
    grabador = grabar_hasta_grabando()
    assert len(Camara.creadas) == creadas and g.sesion.camara is None  # ni se enciende
    assert grabador.formato.fileFormat() == QMediaFormat.FileFormat.Mpeg4Audio
    assert Path(grabador.salida.toLocalFile()).suffix == ".m4a"
    g.detener()
    voz = toma_entra(0, "audios")
    assert voz["tipo"] == "voz" and voz["inicio"] == 0.5 and g.estado == "apagada"
    g.modo.grupo.button(0).click()

    # ---------- Sin cámara, sin micrófono y sin permiso de Windows ----------
    Dispositivos.cambio(camaras=[])
    assert g.camaras.currentData() is None and not g.camaras.isEnabled() and not g.encender_btn.isEnabled()
    n, creadas = len(avisos), len(Camara.creadas)
    g.encender()
    assert len(avisos) == n + 1 and "ninguna cámara" in avisos[-1] and len(Camara.creadas) == creadas
    Dispositivos.cambio(camaras=[CAMARA], micros=[])
    g.modo.grupo.button(1).click()
    g.grabar()
    assert "ningún micrófono" in avisos[-1] and g.estado == "apagada"
    g.modo.grupo.button(0).click()
    Dispositivos.cambio(micros=[Dispositivo("Micrófono de prueba", b"micro-1", True)])
    gr.permiso_denegado = lambda que: que == "webcam"
    g.encender()
    assert "Configuración → Privacidad y seguridad → Cámara" in avisos[-1] and len(Camara.creadas) == creadas
    gr.permiso_denegado = lambda que: que == "microphone"
    g.grabar()
    assert "Configuración → Privacidad y seguridad → Micrófono" in avisos[-1] and g.estado == "apagada"
    gr.permiso_denegado = lambda que: False

    # El registro de Windows: «Deny» en cualquiera de sus tres interruptores es «sin permiso» (sin tocar el de verdad)
    class Registro:
        HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER = "HKLM", "HKCU"
        valores = {}

        @staticmethod
        @contextmanager
        def OpenKey(raiz, ruta):
            if (raiz, ruta) not in Registro.valores:
                raise OSError("no está")
            yield (raiz, ruta)

        @staticmethod
        def QueryValueEx(clave, nombre):
            return Registro.valores[clave], 1
    base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
    winreg_real = sys.modules.get("winreg")
    sys.modules["winreg"] = Registro
    try:
        assert permiso_real("webcam") is False  # sin claves: no se sabe, no se bloquea
        Registro.valores = {("HKLM", f"{base}\\webcam"): "Allow", ("HKCU", f"{base}\\webcam"): "Allow",
                            ("HKCU", f"{base}\\webcam\\NonPackaged"): "Deny"}
        assert permiso_real("webcam") is True and permiso_real("microphone") is False
        Registro.valores[("HKCU", f"{base}\\webcam\\NonPackaged")] = "Allow"
        assert permiso_real("webcam") is False
        Registro.valores[("HKLM", f"{base}\\webcam")] = "Deny"
        assert permiso_real("webcam") is True
    finally:
        sys.modules["winreg"] = winreg_real
    assert permiso_real("microphone") in (True, False)  # el de este PC solo se lee y no falla

    # ---------- Errores mientras grabas: se para y se guarda lo grabado ----------
    def grabar_y(accion, aviso_esperado, guarda=True):
        antes, n = len(videos_capa()), len(avisos)
        p._al_mover_cursor(0.0)
        grabador = grabar_hasta_grabando()
        accion(grabador)
        if guarda:
            toma_entra(antes)
        esperar(lambda: not p.tareas)
        assert len(avisos) > n and aviso_esperado in avisos[-1], avisos[-1]
        assert g.estado in ("vista", "apagada") and g.grabador is None and g.sesion.micro is None
        assert len(videos_capa()) == antes + guarda and not p.sonido.isMuted()
        assert Path(grabador.salida.toLocalFile()).is_file()  # lo grabado, guardado
        if guarda:
            p.deshacer()  # hasta MAX_VIDEOS capas de video: la siguiente prueba tiene sitio

    # La cámara se queda sin permiso a mitad (E_ACCESSDENIED) o la coge otra app
    grabar_y(lambda _: Camara.creadas[-1].errorOccurred.emit(QCamera.Error.CameraError,
                                                             "Access is denied (0x80070005)"),
             "Privacidad y seguridad → Cámara")
    assert g.estado == "apagada" and not Camara.creadas[-1].activa
    grabar_y(lambda _: Camara.creadas[-1].errorOccurred.emit(QCamera.Error.CameraError, "Device busy"), "otra app")
    # El disco se llena (el grabador lo dice) o se va llenando (lo vigila el panel cada segundo)
    grabar_y(lambda gb: gb.errorOccurred.emit(QMediaRecorder.Error.OutOfSpaceError, "No space left"), "disco se llenó")

    def poco_disco(_):  # ya grabando, quedan 100 MB
        gr._libre = lambda carpeta: 100 * 1024 ** 2
        try:
            g._tic()
        finally:
            gr._libre = libre_real
    grabar_y(poco_disco, "disco se está llenando")
    # Llegar al final de los 60 minutos del video
    grabar_y(lambda _: (setattr(g, "_inicio", edicion.MAX_DURACION - 2.5), g._tic()), "60 minutos")
    p.rehacer()  # la toma que grabar_y quitó
    assert videos_capa()[-1]["inicio"] == edicion.MAX_DURACION - 2.5
    assert edicion.duracion_total(p.proyecto) <= edicion.MAX_DURACION
    p.deshacer()
    # Se desenchufa la cámara
    grabar_y(lambda _: Dispositivos.cambio(camaras=[]), "Se desconectó")
    Dispositivos.cambio(camaras=[CAMARA])
    # Cambias de herramienta o de página mientras grabas
    grabar_y(lambda _: (p.herramientas["texto"].click(), avisos.append("cambio de herramienta")), "cambio")
    p.herramientas["grabarte"].click()
    grabar_y(lambda _: (p.hideEvent(QHideEvent()), avisos.append("cambio de página")), "página")
    # El grabador falla al empezar (carpeta sin permiso de escritura): no entra nada
    Grabador.fallo = (QMediaRecorder.Error.LocationNotWritable, "Permission denied?")
    try:
        antes, n = len(videos_capa()), len(avisos)
        p._al_mover_cursor(0.0)
        g.grabar_btn.click()
        esperar(lambda: g.estado == "cuenta")
        for _ in range(gr.CUENTA):
            g._tic()
        assert "No puedo escribir" in avisos[-1] and g.estado == "vista" and len(videos_capa()) == antes
        assert p.centro.currentWidget() is p.vista and not p.sonido.isMuted()
    finally:
        Grabador.fallo = None
    # Poco disco antes de empezar: ni empieza
    gr._libre = lambda carpeta: 100 * 1024 ** 2
    try:
        creados = len(Grabador.creados)
        g.grabar()
        assert "poco espacio" in avisos[-1] and g.estado == "vista" and len(Grabador.creados) == creados
    finally:
        gr._libre = libre_real
    # «Detener» durante la cuenta atrás: se cancela sin grabar nada
    creados = len(Grabador.creados)
    g.grabar_btn.click()
    esperar(lambda: g.estado == "cuenta")
    g.grabar_btn.click()
    assert g.estado == "vista" and len(Grabador.creados) == creados and not g._reloj.isActive()
    g.apagar()

    # ---------- Importar una grabación de tu cara: entra en el cursor con la disposición elegida ----------
    p._elegir("")
    g.tiles["dividida"].click()  # sin capa de video elegida: para la próxima
    p._al_mover_cursor(0.5)
    antes = len(videos_capa())
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(cara), ""))
    g.importar_btn.click()
    importada = toma_entra(antes)
    assert importada["inicio"] == 0.5 and Path(importada["archivo"]) == cara.resolve()
    assert {k: importada[k] for k in ("x", "y", "ancho", "alto")} == {
        k: edicion.disposicion(p.proyecto["formato"], "dividida")[k] for k in ("x", "y", "ancho", "alto")}
    n = len(avisos)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(d / "claves.json"), ""))
    (d / "claves.json").write_text('{"openai": "sk-SECRETO"}', encoding="utf-8")
    g.importar_btn.click()
    esperar(lambda: not p.tareas)
    assert len(avisos) == n + 1 and "sk-SECRETO" not in avisos[-1] and len(videos_capa()) == antes + 1

    # ---------- Con el tope de capas de video lleno: lo dice y tu grabación se queda en grabaciones/ ----------
    llenas = edicion.validar({**p.proyecto, "capas": [{**importada, "id": None}] * edicion.MAX_VIDEOS})
    p._aplicar(llenas)
    n = len(avisos)
    grabador = grabar_hasta_grabando()
    g.detener()
    esperar(lambda: not p.tareas)
    assert len(avisos) == n + 1 and f"hasta {edicion.MAX_VIDEOS} grabaciones" in avisos[-1], avisos[-1]
    assert len(videos_capa()) == edicion.MAX_VIDEOS and Path(grabador.salida.toLocalFile()).is_file()
    p.deshacer()

    # ---------- Al cerrar la app grabando: se para, se guarda y entra en el video antes de preguntar ----------
    antes = len(videos_capa())
    grabar_hasta_grabando()
    p.parar_grabacion()
    assert len(videos_capa()) == antes + 1 and not p.tareas and g.estado == "apagada"  # aquí mismo, sin hilo
    # Un grabador que no contesta no deja la app sin cerrar
    Grabador.responde, gr.PanelGrabarte.ESPERA = False, 300
    grabar_hasta_grabando()
    t0 = time.monotonic()
    p.parar_grabacion()
    assert time.monotonic() - t0 < 3 and g.estado == "guardando"
    Grabador.responde = True

    # Nada de esto usó la cámara ni el micrófono de verdad
    assert gr.PanelGrabarte.Camara is Camara and gr.PanelGrabarte.Grabador is Grabador
    assert all(isinstance(c.dispositivo, Dispositivo) for c in Camara.creadas)
print("Pruebas de Grabarte pasadas (cámara y micrófono simulados).")
