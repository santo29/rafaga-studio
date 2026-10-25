"""Pruebas del editor de video (ui/paginas/edicion.py y ui/linea_tiempo.py) sin ventana, red ni claves:
python -m pruebas.edicion_ui"""
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QDropEvent, QImage, QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from motor import claves, diseno, edicion, marca, video  # noqa: E402
from pruebas import camara_falsa  # noqa: E402
from ui.comun import ESTILO  # noqa: E402
import ui.paginas.diseno as pd  # noqa: E402
import ui.paginas.edicion as pe  # noqa: E402

camara_falsa.usar()  # «Grabarte» con cámara y micrófono simulados: nunca los de este PC

app = QApplication.instance() or QApplication(["pruebas"])
app.setStyleSheet(ESTILO)
avisos, abiertas = [], []
QMessageBox.exec = lambda caja: avisos.append(caja.text()) or QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
os.startfile = abiertas.append  # que «Abrir carpeta» no abra el Explorador
sys.modules["motor.render_edicion"] = None  # todavía no está: el editor tiene que funcionar igual


def esperar(condicion, plazo=30):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def raton(widget, tipo, punto):
    """Un evento de ratón de verdad, en coordenadas del widget."""
    boton = Qt.NoButton if tipo == QEvent.MouseMove else Qt.LeftButton
    botones = Qt.NoButton if tipo == QEvent.MouseButtonRelease else Qt.LeftButton
    QApplication.sendEvent(widget, QMouseEvent(tipo, punto, widget.mapToGlobal(punto), boton, botones, Qt.NoModifier))


def arrastrar(widget, desde, hasta):
    raton(widget, QEvent.MouseButtonPress, desde)
    raton(widget, QEvent.MouseMove, (desde + hasta) / 2)
    raton(widget, QEvent.MouseMove, hasta)
    raton(widget, QEvent.MouseButtonRelease, hasta)


def clic(widget, punto):
    arrastrar(widget, punto, punto)


def en_escena(punto):
    return QPointF(p.vista.mapFromScene(punto))


def elemento(id_):
    return next(e for clave in ("clips", "capas", "audios") for e in p.proyecto[clave] if e["id"] == id_)


def imagen(ancho, alto, color):
    img = QImage(ancho, alto, QImage.Format_RGB32)
    img.fill(QColor(color))
    return img


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    edicion.CARPETA, diseno.CARPETA = d / "ediciones", d / "disenos"  # nada de tocar datos/ de verdad
    marca.ARCHIVO, marca.CARPETA_LOGO = d / "marca.json", d / "marca"
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"
    pe.carpeta_videos = lambda: d / "Videos"  # ni la carpeta Videos del usuario
    clip = d / "clip.mp4"
    video.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                 "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip)
    musica = d / "musica.wav"
    video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=3", musica)
    foto = d / "foto.png"
    assert imagen(320, 180, "#FF0000").save(str(foto))
    secreto = d / "claves.mp4"  # un archivo privado con nombre de video
    secreto.write_text('{"openai": "sk-SECRETO"}', encoding="utf-8")
    secreto_png = d / "claves.png"
    shutil.copyfile(secreto, secreto_png)

    p = pe.PaginaEdicion()
    p.resize(1400, 1000)
    p.show()
    app.processEvents()
    L = p.linea
    assert p.proyecto == edicion.nuevo() and p.carpeta is None and not p.deshacer_btn.isEnabled()
    assert not edicion.CARPETA.exists()  # abrir la página no crea carpetas vacías

    # ---------- Importar: lo bueno entra, lo hostil no ----------
    n = len(avisos)
    p.importar([clip, foto, musica, secreto, r"\\atacante.example\s\v.mp4", "//atacante.example/s/v.mp4",
                d / "no_existe.mp4", "datos/claves.json"])
    assert p.tareas  # se mide en un hilo: la ventana no se congela
    esperar(lambda: not p.tareas)
    clips, audios = p.proyecto["clips"], p.proyecto["audios"]
    assert [c["tipo"] for c in clips] == ["video", "imagen"] and len(audios) == 1, p.proyecto
    assert clips[0]["archivo"] == str(clip.resolve()) and abs(clips[0]["hasta"] - 2) < 0.1
    assert audios[0]["archivo"] == str(musica.resolve()) and audios[0]["inicio"] == 0 and audios[0]["tipo"] == "musica"
    assert len(avisos) == n + 1 and avisos[-1].count("\n\n") == 4, avisos[-1]  # un solo aviso con los 5 rechazos
    assert "red" in avisos[-1] and "sk-SECRETO" not in avisos[-1]
    assert p.carpeta.parent == edicion.CARPETA and (p.carpeta / "cache").is_dir()
    assert p.sel == clips[-1]["id"] and p.sucio and p.deshacer_btn.isEnabled()
    a, b = (c["id"] for c in clips)
    # «Importar música»: un .mp4 ahí es su sonido, no un clip
    p.importar([clip], audio=True)
    esperar(lambda: not p.tareas)
    assert len(p.proyecto["clips"]) == 2 and p.proyecto["audios"][-1]["archivo"] == str(clip.resolve())
    p.deshacer()
    # Soltar archivos en la página o en la vista previa también importa (y rechaza)
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(foto))])
    p.dropEvent(QDropEvent(QPointF(10, 10), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier))
    esperar(lambda: len(p.proyecto["clips"]) == 3)
    p.deshacer()
    assert [c["id"] for c in p.proyecto["clips"]] == [a, b]
    datos.setUrls([QUrl.fromLocalFile(str(secreto))])
    n = len(avisos)
    p.vista.dropEvent(QDropEvent(QPointF(10, 10), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier))
    esperar(lambda: not p.tareas)
    assert len(avisos) == n + 1 and len(p.proyecto["clips"]) == 2
    # Una foto encima (capa) hostil no entra
    n = len(avisos)
    p.anadir_imagen(str(secreto_png))
    assert len(avisos) == n + 1 and not p.proyecto["capas"]

    # ---------- Sin motor/render_edicion: avisa y sigue ----------
    p._pedir_fotograma()
    assert "aún no" in p.estado.text() and not p.foto.isVisible()
    n = len(avisos)
    p.reproducir()
    p.exportar()
    assert len(avisos) == n + 2 and "aún no" in avisos[-1]

    # ---------- Con un motor de render simulado ----------
    pedidos, minis, previas, exportados, cancelados = [], [], [], [], []

    def fotograma(proyecto, carpeta, t, alto_max=640):
        pedidos.append((t, len(proyecto["capas"]), [a["tipo"] for a in proyecto["audios"]]))
        time.sleep(0.05)
        return imagen(36, 64, "#00FF00")

    def miniatura(clip_, carpeta, alto=72):
        minis.append(clip_["id"])
        return imagen(128, alto, "#FF0000")

    def vista_previa(proyecto, carpeta, aviso=lambda t, f: None, desde=0, segundos=None):
        aviso("Preparando vista previa…", 0.5)
        previas.append((proyecto, desde, segundos))
        return clip

    def exportar(proyecto, carpeta, destino, calidad="1080p", aviso=lambda t, f: None):
        aviso("Exportando…", 0.5)
        shutil.copyfile(clip, destino)
        exportados.append(calidad)
        return destino

    def voz_ia(texto, voz, carpeta):
        destino = Path(carpeta) / "voz.wav"
        video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=500:duration=1", destino)
        return destino

    def subtitulos(proyecto, carpeta, aviso=lambda t, f: None):
        return [{"palabra": "Hola", "inicio": 0.1, "fin": 0.5}, {"palabra": "<b>mundo</b>", "inicio": 0.6, "fin": 1.0}]

    sys.modules["motor.render_edicion"] = types.SimpleNamespace(
        fotograma=fotograma, miniatura=miniatura, vista_previa=vista_previa, exportar=exportar, voz_ia=voz_ia,
        forma_de_onda=lambda archivo, carpeta, ancho, alto: imagen(ancho, alto, "#FFFFFF"),
        subtitulos_automaticos=subtitulos, cancelar=lambda: cancelados.append(True))
    # Miniaturas y forma de onda: en el hilo, una vez por clip
    L.grab()
    esperar(lambda: sum(isinstance(v, QImage) for v in L._imagenes.values()) == 3)
    L.grab()
    assert sorted(minis) == sorted([a, b])
    # Arrastrar el cursor por la regla: un fotograma cuando se para, no uno por cada movimiento
    raton(L, QEvent.MouseButtonPress, QPointF(L.x_de(0.1), 10))
    for k in range(2, 30):
        raton(L, QEvent.MouseMove, QPointF(L.x_de(k * 0.05), 10))
    raton(L, QEvent.MouseButtonRelease, QPointF(L.x_de(1.45), 10))
    assert abs(p.cursor - 1.45) < 0.03 and L.cursor == p.cursor and p.reloj_txt.text().startswith("0:01.4")
    esperar(lambda: p.foto.isVisible() and not p._foto_en_curso and not p._espera.isActive())
    # sin capas (las pinta el lienzo); con la música, que marca el ritmo de los efectos «al ritmo»
    assert 1 <= len(pedidos) <= 2 and pedidos[-1] == (p.cursor, 0, ["musica"]), pedidos
    assert p.foto.sceneBoundingRect() == p.escena.sceneRect()  # en baja resolución, estirado a 1080×1920
    clic(L, QPointF(L.x_de(4), 10))  # el cursor, lejos de lo que se va a arrastrar (el imán lo usa)

    # ---------- Línea de tiempo: mover, recortar, imán, zoom ----------
    pila = len(p.deshacer_pila)
    caja = L.caja(b)
    arrastrar(L, caja.center(), QPointF(L.x_de(0.3), caja.center().y()))  # la foto delante del video
    assert [c["id"] for c in p.proyecto["clips"]] == [b, a] and len(p.deshacer_pila) == pila + 1
    p.deshacer()
    assert [c["id"] for c in p.proyecto["clips"]] == [a, b] and p.rehacer_btn.isEnabled()
    clic(L, L.caja(a).center())  # un clic sin mover solo elige
    assert p.sel == a and len(p.deshacer_pila) == pila and "Clip" in p.titulo_props.text()
    caja = L.caja(a)
    y = caja.center().y()
    arrastrar(L, QPointF(caja.right() - 2, y), QPointF(caja.right() - 2 - 0.5 * L.escala, y))  # borde derecho
    assert abs(elemento(a)["hasta"] - 1.5) < 0.03 and elemento(a)["desde"] == 0, elemento(a)
    caja = L.caja(a)
    arrastrar(L, QPointF(caja.left() + 2, y), QPointF(caja.left() + 2 + 0.5 * L.escala, y))  # borde izquierdo
    assert abs(elemento(a)["desde"] - 0.5) < 0.03 and abs(elemento(a)["hasta"] - 1.5) < 0.03, elemento(a)
    assert abs(edicion.tiempos(p.proyecto)[1][0] - 1.0) < 0.03  # la foto sigue pegada detrás
    caja = L.caja(a)
    arrastrar(L, QPointF(caja.right() - 2, y), QPointF(caja.right() + 10 * L.escala, y))  # no pasa del archivo
    assert abs(elemento(a)["hasta"] - elemento(a)["duracion_archivo"]) < 1e-3
    audio = p.proyecto["audios"][0]["id"]
    caja = L.caja(audio)
    arrastrar(L, caja.center(), caja.center() + QPointF(L.escala, 0))
    assert abs(elemento(audio)["inicio"] - 1) < 0.03 and elemento(audio)["desde"] == 0
    caja = L.caja(audio)
    arrastrar(L, QPointF(caja.left() + 2, caja.center().y()), QPointF(caja.left() + 2 + 0.5 * L.escala, caja.center().y()))
    assert abs(elemento(audio)["desde"] - 0.5) < 0.03 and abs(elemento(audio)["inicio"] - 1.5) < 0.03  # no se corre
    p.deshacer()
    caja = L.caja(audio)
    arrastrar(L, caja.center(), caja.center() - QPointF(30 * L.escala, 0))  # no antes del 0
    assert elemento(audio)["inicio"] == 0
    # Una capa de texto en el cursor, y el imán: soltada a 4 px del final del video, se pega a él
    clic(L, QPointF(L.x_de(0), 10))
    p.herramientas["texto"].click()
    p.textos.itemClicked.emit(p.textos.item(1))
    texto = p.proyecto["capas"][-1]
    assert texto["tipo"] == "texto" and (texto["inicio"], texto["duracion"]) == (0, 3) and p.sel == texto["id"]
    assert texto["grosor_contorno"] > 0 and [i.data(0) for i in p._items()] == [texto["id"]]
    fin_a = edicion.tiempos(p.proyecto)[0][1]
    caja = L.caja(texto["id"])
    desde = QPointF(caja.left() + 20, caja.center().y())
    arrastrar(L, desde, desde + QPointF((fin_a + 0.1) * L.escala, 0))
    assert abs(elemento(texto["id"])["inicio"] - fin_a) < 1e-3, (elemento(texto["id"]), fin_a)
    caja = L.caja(texto["id"])
    arrastrar(L, QPointF(caja.right() - 2, caja.center().y()), QPointF(caja.right() - 2 - L.escala, caja.center().y()))
    assert abs(elemento(texto["id"])["duracion"] - 2) < 0.03 and abs(elemento(texto["id"])["inicio"] - fin_a) < 1e-3
    assert not p._items()  # el cursor (0) ya no cae dentro de la capa: no se ve en el lienzo
    # Zoom con el deslizador y con la rueda
    ancho = L.minimumWidth()
    L.deslizador.setValue(80)
    assert L.escala == 80 and L.minimumWidth() > ancho
    L.wheelEvent(QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
                             Qt.NoModifier, Qt.NoScrollPhase, False))
    assert L.escala == 100
    L.deslizador.setValue(40)

    # ---------- Dividir, borrar, duplicar, deshacer y rehacer ----------
    clic(L, QPointF(L.x_de(0.5), 10))
    p.dividir()
    assert len(p.proyecto["clips"]) == 3 and abs(edicion.duracion_clip(p.proyecto["clips"][0]) - 0.5) < 0.03
    p.deshacer()
    assert [c["id"] for c in p.proyecto["clips"]] == [a, b]
    p.rehacer()
    assert len(p.proyecto["clips"]) == 3
    p.deshacer()
    clic(L, QPointF(L.x_de(30), 10))  # pasado el final: el cursor se queda en el final
    assert p.cursor == edicion.duracion_total(p.proyecto)
    p.dividir()
    assert "⚠️" in p.estado.text() and len(p.proyecto["clips"]) == 2
    clic(L, L.caja(b).center())
    p._suprimir()  # Supr
    assert [c["id"] for c in p.proyecto["clips"]] == [a] and p.sel == ""
    p.deshacer()
    clic(L, L.caja(texto["id"]).center())
    p.duplicar()
    copia = p.proyecto["capas"][-1]
    assert len(p.proyecto["capas"]) == 2 and p.sel == copia["id"] != texto["id"]
    assert abs(copia["inicio"] - (fin_a + 2)) < 1e-3 and copia["texto"] == texto["texto"]
    p.deshacer()
    clic(L, QPointF(L.x_de(0.2), L.height() - 5))  # clic en un hueco: suelta lo elegido
    assert p.sel == "" and "Proyecto" in p.titulo_props.text()

    # ---------- Stickers, capas y su tiempo ----------
    assert p.stickers.count() == 0  # dibujar 120 iconos tarda: no al arrancar
    p.herramientas["stickers"].click()
    assert p.stickers.count() > 100  # se llena al abrir la pestaña
    p.buscar_sticker.setText("fire")
    fuego = next(p.stickers.item(i) for i in range(p.stickers.count()) if p.stickers.item(i).data(Qt.UserRole) == "🔥")
    p.stickers.itemClicked.emit(fuego)
    p.buscar_sticker.setText("pizza")
    icono = next(p.stickers.item(i) for i in range(p.stickers.count())
                 if p.stickers.item(i).data(Qt.UserRole + 1) == "icono")
    assert icono.data(Qt.UserRole) == "pizza" and icono.text() == "" and icono.toolTip() == "pizza"
    p.stickers.itemClicked.emit(icono)
    emoji, pizza = p.proyecto["capas"][-2:]
    assert (emoji["tipo"], emoji["texto"], pizza["tipo"], pizza["nombre"]) == ("emoji", "🔥", "icono", "pizza")
    assert emoji["inicio"] == pizza["inicio"] == round(p.cursor, 3)
    assert [i.data(0) for i in p._items()] == [c["id"] for c in edicion.capas_en(p.proyecto, p.cursor)] == \
        [emoji["id"], pizza["id"]]
    assert p.elegido()[1]["id"] == pizza["id"]
    leidas = diseno._leer_imagen.cache_info()
    p.anadir_imagen(str(foto))
    assert p.tareas  # copiarla y leerla (una foto de 50 MP tarda más de 1 s) va en el hilo
    esperar(lambda: not p.tareas)
    capa_foto = p.proyecto["capas"][-1]
    ahora = diseno._leer_imagen.cache_info()
    assert ahora.misses == leidas.misses + 1 and ahora.hits > leidas.hits  # el lienzo la encontró ya leída
    assert capa_foto["tipo"] == "imagen" and (p.carpeta / "imagenes" / capa_foto["archivo"]).is_file()
    assert (capa_foto["ancho"], capa_foto["alto"]) == (648, 364)  # cabe sin deformarse
    p.deshacer()

    # ---------- Propiedades ----------
    clic(L, L.caja(a).center())
    w = p.w
    assert not w[("clips", "velocidad")].isHidden() and w[("clips", "movimiento")].isHidden()  # un video no se mueve
    pila = len(p.deshacer_pila)
    for v in (1.5, 2):
        w[("clips", "velocidad")].setValue(v)
    assert elemento(a)["velocidad"] == 2 and len(p.deshacer_pila) == pila + 1  # lo seguido, un solo «deshacer»
    w[("clips", "volumen")].setValue(50)
    w[("clips", "silencio")].setChecked(True)
    assert (elemento(a)["volumen"], elemento(a)["silencio"]) == (0.5, True)
    assert w[("clips", "duracion_transicion")].isHidden()  # sin transición no hay duración que tocar
    p.listas["filtro"].itemClicked.emit(p.listas["filtro"].item(1))
    p.listas["transicion"].itemClicked.emit(p.listas["transicion"].item(1))
    assert not w[("clips", "duracion_transicion")].isHidden()
    assert (elemento(a)["filtro"], elemento(a)["transicion"]) == ("byn", "fundido") and len(L._marcas()) == 1
    assert w[("clips", "filtro")].currentData() == "byn"
    clic(L, L._marcas()[0][0])  # clic en el rombo de la transición: elige su clip
    assert p.sel == a
    clic(L, L.caja(b).center())
    assert w[("clips", "velocidad")].isHidden() and not w[("clips", "movimiento")].isHidden()  # una foto sí
    p.listas["transicion"].itemClicked.emit(p.listas["transicion"].item(1))  # el último clip no tiene a qué pasar
    assert elemento(b)["transicion"] == "ninguna" and "⚠️" in p.estado.text()
    p._elegir("")
    n = len(avisos)
    p.listas["filtro"].itemClicked.emit(p.listas["filtro"].item(2))
    assert len(avisos) == n + 1 and "clip" in avisos[-1]
    clic(L, L.caja(audio).center())
    w[("audios", "volumen")].setValue(50)
    w[("audios", "entrada")].setValue(2)
    assert (elemento(audio)["volumen"], elemento(audio)["entrada"]) == (0.5, 2)
    clic(L, QPointF(L.x_de(fin_a + 0.5), 10))
    clic(L, L.caja(texto["id"]).center())
    assert not w[("capas", "fuente")].isHidden() and w[("capas", "ajuste")].isHidden()
    w[("capas", "texto")].setPlainText("<b>Hola</b>")
    item, capa = p.elegido()
    assert capa["texto"] == item.texto.toPlainText() == "<b>Hola</b>"  # texto plano, nunca HTML
    w[("capas", "entrada")].setCurrentIndex(w[("capas", "entrada")].findData("fundido"))
    w[("capas", "duracion")].setValue(4)
    assert (elemento(texto["id"])["entrada"], elemento(texto["id"])["duracion"]) == ("fundido", 4)
    # Mover y cambiar el tamaño con el ratón en la vista previa, como en el editor de diseño
    c = elemento(texto["id"])
    agarre = QPointF(c["x"] + 60, c["y"] + c["alto"] / 2)  # a un lado: en el centro están los stickers, encima
    pila = len(p.deshacer_pila)
    arrastrar(p.vista.viewport(), en_escena(agarre), en_escena(agarre + QPointF(100, 50)))
    c2 = elemento(texto["id"])
    assert abs(c2["x"] - c["x"] - 100) <= 4 and abs(c2["y"] - c["y"] - 50) <= 4 and len(p.deshacer_pila) == pila + 1
    esquina = QPointF(c2["x"] + c2["ancho"], c2["y"] + c2["alto"])
    arrastrar(p.vista.viewport(), en_escena(esquina), en_escena(esquina + QPointF(-200, 100)))
    c3 = elemento(texto["id"])
    assert abs(c3["ancho"] - c2["ancho"] + 200) <= 6 and (c3["x"], c3["y"]) == (c2["x"], c2["y"]), (c2, c3)
    assert w[("capas", "ancho")].value() == c3["ancho"]  # las propiedades siguen al lienzo
    arrastrar(p.vista.viewport(), en_escena(QPointF(20, 20)), en_escena(QPointF(20, 20)))  # clic en el fondo
    assert p.sel == "" and p.elegido() == (None, None)
    # Proyecto
    w[("proyecto", "nombre")].setText("Mi viaje")
    w[("proyecto", "nombre")].textEdited.emit("Mi viaje")
    w[("proyecto", "formato")].setCurrentIndex(w[("proyecto", "formato")].findData("16:9"))
    assert p.proyecto["nombre"] == "Mi viaje" and p.proyecto["formato"] == "16:9"
    assert p.escena.sceneRect().width() == 1920 and p.diseno == {"ancho": 1920, "alto": 1080}
    pd.pedir_color = lambda *a: "#112233"
    w[("proyecto", "fondo")].click()
    assert p.proyecto["fondo"] == "#112233" and w[("proyecto", "fondo")].text() == "#112233"
    p.deshacer()
    assert p.proyecto["fondo"] == "#000000" and p.proyecto["formato"] == "16:9"

    # ---------- Barra de herramientas (como en CapCut) y sus paneles ----------
    assert [b.text() for b in p.pestanas.buttons()] == [
        "Medios", "Audio", "Grabarte", "Texto", "Stickers", "Efectos", "Transiciones", "Subtítulos", "Filtros",
        "Ajustes", "Plantillas", "Avatar IA"]
    for b in p.pestanas.buttons():
        b.click()
        assert b.isChecked() and p.paneles.currentIndex() == p.pestanas.id(b) and p.titulo_pestana.text() == b.text()
        assert b.toolButtonStyle() == Qt.ToolButtonTextUnderIcon
    assert not camara_falsa.Camara.creadas  # abrir «Grabarte» no enciende la cámara: solo tú, con su botón
    assert p.listas["transicion"].count() == len(edicion.TRANSICIONES)  # la lista completa, también las nuevas
    assert not p.avatar_btn.isEnabled()  # «Próximamente»: no promete lo que aún no hace
    efectos, filtros, desl = p.listas["efecto"], p.listas["filtro"], p.deslizadores

    def opcion(lista, clave):
        return next(lista.item(i) for i in range(lista.count()) if lista.item(i).data(Qt.UserRole) == clave)

    # Sin clip elegido: los ajustes se apagan y un efecto pide elegir uno (y no se queda marcado)
    assert p.sel == "" and not desl["brillo"].isEnabled() and not p.restablecer.isEnabled()
    n = len(avisos)
    efectos.itemClicked.emit(opcion(efectos, "glitch"))
    assert len(avisos) == n + 1 and "clip" in avisos[-1] and not efectos.selectedItems()
    clic(L, L.caja(a).center())
    assert desl["brillo"].isEnabled() and desl["intensidad"].value() == 60
    assert filtros.currentItem().data(Qt.UserRole) == "byn" and efectos.currentItem().data(Qt.UserRole) == "ninguno"
    # Efecto e intensidad; arrastrar el deslizador es un solo «deshacer»
    pila = len(p.deshacer_pila)
    efectos.itemClicked.emit(opcion(efectos, "brillo_rafaga"))
    for v in (70, 80, 90):
        desl["intensidad"].setValue(v)
    assert (elemento(a)["efecto"], elemento(a)["intensidad"]) == ("brillo_rafaga", 90)
    assert len(p.deshacer_pila) == pila + 2
    p.deshacer()
    assert elemento(a)["intensidad"] == 60 and desl["intensidad"].value() == 60
    p.deshacer()
    assert elemento(a)["efecto"] == "ninguno" and efectos.currentItem().data(Qt.UserRole) == "ninguno"
    # Un filtro de la cuadrícula: también lo enseña Propiedades
    filtros.itemClicked.emit(opcion(filtros, "cine"))
    assert elemento(a)["filtro"] == "cine" == w[("clips", "filtro")].currentData()
    p.deshacer()
    assert elemento(a)["filtro"] == "byn" and filtros.currentItem().data(Qt.UserRole) == "byn"
    # Ajustes y «Restablecer» (un solo «deshacer» para los seis)
    nuevos = {"brillo": 20, "contraste": -10, "saturacion": 30, "temperatura": -40, "vineta": 50, "nitidez": 70}
    for campo, v in nuevos.items():
        desl[campo].setValue(v)
    assert {k: elemento(a)[k] for k in nuevos} == nuevos and w[("clips", "brillo")].value() == 20
    pila = len(p.deshacer_pila)
    p.restablecer.click()
    assert all(elemento(a)[k] == 0 for k in nuevos) and desl["nitidez"].value() == 0 and len(p.deshacer_pila) == pila + 1
    p.deshacer()
    assert {k: elemento(a)[k] for k in nuevos} == nuevos and desl["temperatura"].value() == -40
    for _ in nuevos:
        p.deshacer()
    assert all(elemento(a)[k] == 0 for k in nuevos)
    # Estilo de los subtítulos
    p.subs_estilo.setCurrentIndex(p.subs_estilo.findData("neon"))
    assert p.proyecto["subtitulos"]["estilo"] == "neon"
    p.deshacer()
    assert p.proyecto["subtitulos"]["estilo"] == "clasico" == p.subs_estilo.currentData()
    # Plantillas: todo de una vez, sin tocar los medios; aplicar otra no duplica sus textos
    antes = p.proyecto
    p.plantillas["anuncio"].click()
    q = p.proyecto
    assert [c["id"] for c in q["capas"] if c["id"].startswith("plantilla-")] == ["plantilla-titulo", "plantilla-cierre"]
    assert all((c["filtro"], c["efecto"]) == ("caribe", "brillo_rafaga") for c in q["clips"])
    assert [c["archivo"] for c in q["clips"]] == [c["archivo"] for c in antes["clips"]] and q["audios"] == antes["audios"]
    assert q["subtitulos"]["estilo"] == "caja" == p.subs_estilo.currentData() and p.subs_activos.isChecked()
    assert efectos.currentItem().data(Qt.UserRole) == "brillo_rafaga"  # el panel sigue al clip elegido
    p.plantillas["vlog"].click()
    assert [c["id"] for c in p.proyecto["capas"] if c["id"].startswith("plantilla-")] == ["plantilla-titulo"]
    p.deshacer()
    p.deshacer()
    assert p.proyecto == antes
    # Sin clips: lo dice claro y no cambia nada
    vacia = pe.PaginaEdicion()
    n = len(avisos)
    vacia.plantillas["short_viral"].click()
    assert len(avisos) == n + 1 and "clip" in avisos[-1] and vacia.proyecto == edicion.nuevo() and not vacia.deshacer_pila
    vacia.deleteLater()
    p._elegir("")

    # ---------- Subtítulos y voz IA (simulados) ----------
    p.subs_estilo.setCurrentIndex(p.subs_estilo.findData("karaoke"))
    p.subtitulos_automaticos()
    esperar(lambda: not p.tareas)
    assert p.proyecto["subtitulos"]["activos"] and [x["palabra"] for x in p.proyecto["subtitulos"]["palabras"]] == \
        ["Hola", "<b>mundo</b>"] and p.subs_activos.isChecked()
    assert p.proyecto["subtitulos"]["estilo"] == "karaoke"  # hacerlos no quita el estilo elegido
    L.grab()  # se pintan (texto plano)
    p.subs_activos.setChecked(False)
    assert not p.proyecto["subtitulos"]["activos"] and len(p.proyecto["subtitulos"]["palabras"]) == 2
    p.deshacer()
    p.texto_voz.setPlainText("Hola a todos")
    voces = len(p.proyecto["audios"])
    p.voz_ia()
    esperar(lambda: not p.tareas)
    voz = p.proyecto["audios"][-1]
    assert len(p.proyecto["audios"]) == voces + 1 and voz["tipo"] == "voz" and voz["inicio"] == round(p.cursor, 3)
    assert Path(voz["archivo"]).parent == p.carpeta.resolve()

    # ---------- Reproducir la vista previa ----------
    p._al_mover_cursor(0.5)
    p.reproducir()
    esperar(lambda: not p.tareas)
    assert p.centro.currentWidget() is p.pantalla and p.play_btn.property("icono") == "pause"
    p._al_reproducir(300)  # solo se monta un trozo desde el cursor, y el cursor sigue al video desde ahí
    assert previas == [(p.proyecto, 0.5, pe.PREVIA)] and abs(p.cursor - 0.8) < 1e-6, (previas[-1][1:], p.cursor)
    p.parar()
    assert p.centro.currentWidget() is p.vista
    p.reproducir()  # sin cambios: no se vuelve a preparar
    assert len(previas) == 1 and p.centro.currentWidget() is p.pantalla
    clic(L, QPointF(L.x_de(0.2), 10))  # tocar la línea de tiempo para la reproducción
    assert p.centro.currentWidget() is p.vista and p.play_btn.property("icono") == "play"

    # ---------- Guardar y abrir ----------
    p.guardar()
    carpeta = p.carpeta
    assert (carpeta / "proyecto.json").is_file() and not p.sucio and "Guardado" in p.estado.text()
    assert not QImage(str(carpeta / "miniatura.png")).isNull()
    guardado = p.proyecto
    p._empezar(edicion.nuevo(), None)
    assert p.proyecto == edicion.nuevo() and not p.deshacer_pila and not p._items() and carpeta.is_dir()
    assert p.player.source().isEmpty()  # suelta la vista previa: abierta en el reproductor, Windows no deja borrarla
    p.importar([foto])  # un video que se descarta sin guardar no deja su carpeta (y su caché) en datos/ediciones
    esperar(lambda: not p.tareas)
    tirada = p.carpeta
    assert tirada != carpeta and (tirada / "cache").is_dir()
    pd.Cuadricula.exec = lambda s: bool(s.rejilla.count()) and (s._elegir(s.rejilla.item(0)) or True)
    p.pedir_abrir()
    esperar(lambda: not p.tareas and p.carpeta == carpeta)
    assert p.proyecto == guardado and not p.sucio and not tirada.exists()
    for malo in (d / "no_existe", r"\\atacante.example\s\video"):
        n = len(avisos)
        p.abrir(malo)
        esperar(lambda: not p.tareas)
        assert len(avisos) == n + 1 and p.proyecto == guardado
    # Un video con una foto encima: al abrirlo se lee en el hilo y el lienzo la encuentra ya leída
    con_foto = edicion.nueva_carpeta("con foto")
    edicion.guardar({**guardado, "capas": [{"tipo": "imagen", "archivo": diseno.importar_imagen(str(foto), con_foto),
                                            "x": 0, "y": 0, "ancho": 320, "alto": 180}]}, con_foto)
    p.abrir(con_foto)
    esperar(lambda: not p.tareas and p.carpeta == con_foto)
    leidas = diseno._leer_imagen.cache_info()
    assert len(p._items()) == 1 and leidas.misses == 1 and leidas.hits >= 1, leidas

    # ---------- Exportar ----------
    p.calidad.setCurrentIndex(p.calidad.findData("720p"))
    p.exportar()
    esperar(lambda: not p.tareas)
    p.exportar()
    esperar(lambda: not p.tareas)
    assert exportados == ["720p", "720p"]
    assert (d / "Videos" / "Mi viaje.mp4").is_file() and (d / "Videos" / "Mi viaje (2).mp4").is_file()
    p.abrir_carpeta()
    assert abiertas == [d / "Videos"]
    assert pe.destino_libre("con").name == "video con.mp4" and pe.destino_libre('a\\b/c:"d"').name == "a b c d.mp4"

    # ---------- Un video que se movió de carpeta: en rojo y «Volver a enlazar…» ----------
    movido, nuevo_sitio = d / "movido.mp4", d / "nuevo sitio.mp4"
    shutil.copyfile(clip, movido)
    p._empezar(edicion.nuevo(), None)
    p.importar([movido])
    esperar(lambda: not p.tareas)
    p.guardar()
    movido.rename(nuevo_sitio)
    p.abrir(p.carpeta)
    esperar(lambda: not p.tareas)
    perdido = p.proyecto["clips"][0]
    assert perdido.get("falta") and "Volver a enlazar" in p.estado.text(), (perdido, p.estado.text())
    preguntas = []  # exportar con un clip en rojo pregunta antes (saldría un hueco del color de fondo y en silencio)
    QMessageBox.question = staticmethod(lambda padre, titulo, *a, **k: preguntas.append(titulo) or QMessageBox.No)
    p.reproducir()  # ▶ borra el aviso de arriba
    esperar(lambda: not p.tareas)
    p.parar()
    p.exportar()
    assert preguntas == ["Faltan archivos"] and not p.tareas and len(exportados) == 2, (preguntas, exportados)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    caja = L.caja(perdido["id"])
    assert L.grab().toImage().pixelColor(caja.center().toPoint()).name() == "#b23b3b"  # en rojo
    clic(L, caja.center())
    assert not p.reenlazar_btn.isHidden() and "Falta:" in p.titulo_props.text()
    pe.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(nuevo_sitio), ""))
    p.reenlazar_btn.click()
    esperar(lambda: not p.tareas)
    enlazado = p.proyecto["clips"][0]
    assert "falta" not in enlazado and enlazado["archivo"] == str(nuevo_sitio.resolve()) and p.reenlazar_btn.isHidden()
    assert "No encuentro" not in p.estado.text(), p.estado.text()  # el aviso de arriba se va al enlazarlos todos

    # ---------- Subtítulos de 60 min: la línea de tiempo pinta solo las palabras que se ven ----------
    larga = pe.LineaTiempo()
    larga.poner(edicion.validar({
        "capas": [{"tipo": "texto", "texto": "x", "x": 0, "y": 0, "ancho": 100, "alto": 100, "duracion": 3600}],
        "subtitulos": {"palabras": [{"palabra": "hola", "inicio": k * 0.18, "fin": k * 0.18 + 0.15}
                                    for k in range(edicion.MAX_PALABRAS)]}}), None)
    zona = QRect(int(larga.x_de(3000)), 0, 1400, larga.height())
    tardo = []
    for _ in range(3):
        t0 = time.perf_counter()
        pintado = larga.grab(zona).toImage()
        tardo.append(time.perf_counter() - t0)
    assert min(tardo) < 0.08, tardo  # antes recorría las 20 000 en cada repintado: ~0,3 s
    x = round(larga.x_de(larga._palabras[16667]["inicio"])) + 2 - zona.left()  # la de 3000.06 s, a la vista
    assert pintado.pixelColor(x, larga._y_subs + 1).name() == "#2c2c36"

    # ---------- Deshacer: como mucho 50 copias ----------
    for k in range(60):
        p._aplicar(edicion.validar({**p.proyecto, "fps": (24, 25)[k % 2]}))
    assert len(p.deshacer_pila) == 50

    # ---------- La ventana completa: la página después de «Diseño» y «✂️ Editar» en los resultados ----------
    # Lo que dejó un borrado a medias (una miniatura tenía abierto un archivo de cache/) se borra al arrancar; el video
    # sin guardar de otra ventana abierta (tiene imagenes/) se respeta
    resto, ajena = edicion.CARPETA / "resto", edicion.nueva_carpeta("otra ventana")
    (resto / "cache").mkdir(parents=True)
    import app as aplicacion
    from ui.comun import Reproductor
    ventana = aplicacion.Ventana()
    assert not resto.exists() and ajena.is_dir()
    i = next(i for i, pagina in enumerate(ventana.orden) if isinstance(pagina, pe.PaginaEdicion))
    assert ventana.orden[i - 1] is ventana.serie and "Editor de video" in ventana.grupo.buttons()[i].text()
    reproductor = ventana.crear.reproductor
    assert not reproductor.editar.isHidden()
    reproductor.mostrar({"formato": "16:9", "resultados": [{"archivo": str(clip), "titulo": "Prueba",
                                                             "descripcion": "", "hashtags": []}]})
    reproductor.editar.click()
    assert ventana.paginas.currentIndex() == i and ventana.grupo.buttons()[i].isChecked()
    esperar(lambda: not ventana.edicion.tareas and ventana.edicion.proyecto["clips"])
    assert ventana.edicion.proyecto["formato"] == "16:9"
    assert ventana.edicion.proyecto["clips"][0]["archivo"] == str(clip.resolve())
    # Con la cámara de «Grabarte» encendida, ir a otra página del menú la apaga (la ventana ya se ve: como de verdad)
    ventana.show()
    ventana.edicion.herramientas["grabarte"].click()
    assert ventana.edicion.grabarte.encender() and camara_falsa.Camara.creadas[-1].activa
    ventana.ir_a(0)
    assert ventana.edicion.grabarte.estado == "apagada" and not camara_falsa.Camara.creadas[-1].activa
    ventana.ir_a(i)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)  # un video sin guardar: cerrar pregunta
    reproductor.editar.click()  # y «No» deja el proyecto como estaba
    assert len(ventana.edicion.proyecto["clips"]) == 1 and not ventana.edicion.tareas
    assert not ventana.close()
    # Exportando (o preparando algo): cerrar pregunta. «No» sigue trabajando; «Sí» lo cancela (mata sus ffmpeg, que
    # si no seguirían solos y dejarían un «tmp-…mp4» en Videos) y cierra
    QMessageBox.question = staticmethod(lambda padre, titulo, *a, **k:
                                        QMessageBox.No if titulo == "Está trabajando" else QMessageBox.Yes)
    ventana.edicion._trabajo(lambda aviso: time.sleep(0.5) or {}, lambda r: None)
    assert not ventana.close() and ventana.edicion.tareas
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    tirada = ventana.edicion.carpeta  # nunca se guardó: al cerrar se borra con su caché
    assert tirada.is_dir() and ventana.close() and cancelados and not ventana.edicion.tareas and not tirada.exists()
    Reproductor.al_editar = None

    # ---------- Con motor/render_edicion de verdad, si ya está: fotograma, miniatura y forma de onda ----------
    del sys.modules["motor.render_edicion"]
    if pe.render() is None:
        print("(motor/render_edicion aún no está: no se prueba con el de verdad)")
    else:
        q = pe.PaginaEdicion()
        q.importar([clip, musica])
        esperar(lambda: not q.tareas)
        q._al_mover_cursor(1.0)
        esperar(lambda: q.foto.isVisible() and not q._foto_en_curso)
        assert q.foto.sceneBoundingRect() == q.escena.sceneRect()
        q.linea.grab()
        esperar(lambda: sum(isinstance(v, QImage) for v in q.linea._imagenes.values()) == 2)
print("Pruebas del editor de video pasadas.")
