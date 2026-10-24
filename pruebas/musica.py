"""Pruebas del estudio de música sin red ni claves de verdad: python -m pruebas.musica"""
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QScrollArea  # noqa: E402

from motor import cabina, claves, ia, musica, seguro, video_musical  # noqa: E402
from ui.comun import PaginaTrabajo  # noqa: E402
from ui.paginas.cabina import PaginaCabina  # noqa: E402
from ui.paginas.musica import PaginaMusica  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»


def esperar(condicion, plazo=10):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


class Respuesta:
    status_code, content, text = 200, b"ID3audio", ""

    def raise_for_status(self):
        pass


CANCION = {"titulo": "Viernes", "estilo": "hard 808s", "letra": "[Chorus]\nDale que es vierne'",
           "descripcion": "Para el finde", "hashtags": ["#dembow"]}
reales = ia.texto_json, musica._gemini, musica.httpx.post, cabina.separar_cancion, video_musical.crear
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"
    try:
        # ---------- Con las dos claves, el automático usa Gemini (~$0.08 por canción) y no ElevenLabs (~$0.30-0.45) --
        claves.guardar({"proveedor": "elevenlabs", "clave": "sk_x", "usos": ["voz", "musica"],
                        "modelo_musica": "music_v2_5"})
        claves.guardar({"proveedor": "gemini", "clave": "AIza-x", "usos": ["texto", "musica"],
                        "modelo_musica": "lyria-3.5"})
        assert claves.para("musica")["proveedor"] == "gemini"
        assert claves.opciones("musica") == ["auto", "gemini", "elevenlabs"]

        # ---------- ElevenLabs pide el formato de sus modelos v2 ----------
        pedidos = []
        musica.httpx.post = lambda url, **k: pedidos.append(k) or Respuesta()
        assert musica._elevenlabs({"clave": "x", "modelo_musica": "music_v2_5"}, "dembow", "letra", 30) == b"ID3audio"
        assert pedidos[0]["params"] == {"output_format": "mp3_48000_192"}, pedidos

        # ---------- Si el audio falla, la letra ya está guardada y el error dice dónde ----------
        ia.texto_json = lambda instrucciones, pedido, esquema: dict(CANCION)

        def falla(c, estilo, letra, segundos):
            raise RuntimeError("Gemini no devolvió audio.")
        musica._gemini = falla
        musica.PROYECTOS = d / "falla"
        try:
            musica.crear("un dembow de viernes", "Dembow moderno")
            raise AssertionError("debió fallar")
        except RuntimeError as e:
            letra = next(musica.PROYECTOS.glob("*/letra.txt"))
            assert "Gemini no devolvió audio." in str(e) and str(letra) in str(e), e
            assert letra.read_text(encoding="utf-8") == "Viernes\n\n[Chorus]\nDale que es vierne'"
        musica.PROYECTOS = d / "falla_instrumental"  # sin letra que salvar: el error sale tal cual
        try:
            musica.crear("pista de fondo", "Lo-fi para videos", con_voz=False)
            raise AssertionError("debió fallar")
        except RuntimeError as e:
            assert str(e) == "Gemini no devolvió audio.", e

        # ---------- Bien: canción y letra en su carpeta ----------
        musica._gemini = lambda c, estilo, letra, segundos: b"ID3cancion"
        musica.PROYECTOS = d / "bien"
        p = musica.crear("un dembow de viernes", "Dembow moderno")
        assert Path(p["resultados"][0]["archivo"]).read_bytes() == b"ID3cancion"
        assert (Path(p["carpeta"]) / "letra.txt").read_text(encoding="utf-8").startswith("Viernes\n\n[Chorus]")

        # ---------- Gemini sin facturación (Lyria no tiene plan gratis): en automático sale con ElevenLabs ----------
        class Rechazo(Respuesta):
            status_code, text = 429, '{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}'

            def raise_for_status(self):
                raise RuntimeError(f"Client error '{self.status_code}'")
        llamadas = []
        musica._gemini = reales[1]
        musica.httpx.post = lambda url, **k: llamadas.append(url) or (Rechazo() if "googleapis" in url else Respuesta())
        musica.PROYECTOS = d / "respaldo"
        p = musica.crear("un dembow de viernes", "Dembow moderno")
        assert Path(p["resultados"][0]["archivo"]).read_bytes() == b"ID3audio"
        assert "googleapis" in llamadas[0] and "elevenlabs" in llamadas[1] and len(llamadas) == 2, llamadas
        assert "facturación de Gemini" in p["avisos"][0] and "ElevenLabs" in p["avisos"][0], p["avisos"]
        # Gemini elegido a mano: no cambia de proveedor, y el error dice qué hacer (también con 403)
        claves.elegir_por_defecto("musica", "gemini")
        Rechazo.status_code, llamadas[:], musica.PROYECTOS = 403, [], d / "a_mano"  # carpeta por segundo: otra
        try:
            musica.crear("un dembow de viernes", "Dembow moderno")
            raise AssertionError("debió fallar")
        except RuntimeError as e:
            assert "Lyria no está en el plan gratis de Gemini (403)" in str(e) and "Claves de IA → Música" in str(e), e
            assert len(llamadas) == 1, llamadas
        claves.elegir_por_defecto("musica", "auto")
        # Si también ElevenLabs rechaza (su plan gratis no hace música), el error trae los dos motivos
        Rechazo.status_code, llamadas[:], musica.PROYECTOS = 429, [], d / "ambos"
        musica.httpx.post = lambda url, **k: llamadas.append(url) or (
            Rechazo() if "googleapis" in url else type("Sin", (Respuesta,), {"status_code": 402, "text": "paid plan"})())
        try:
            musica.crear("un dembow de viernes", "Dembow moderno")
            raise AssertionError("debió fallar")
        except RuntimeError as e:
            assert "Lyria no está en el plan gratis de Gemini (429)" in str(e) and "paid plan" in str(e), e
        musica.httpx.post = lambda url, **k: llamadas.append(url) or (Rechazo() if "googleapis" in url else Respuesta())
        # Sin clave de música, el aviso nombra primero a Gemini (el de por defecto)
        claves.ARCHIVO = d / "sin_claves.json"
        try:
            musica.crear("un dembow de viernes", "Dembow moderno")
            raise AssertionError("debió fallar")
        except ia.SinClave as e:
            assert str(e).startswith("Conecta una clave de música: Gemini") and "facturación" in str(e), e
        claves.ARCHIVO = d / "claves.json"

        # ---------- Reloj mientras se trabaja: «Produciendo… 1:23» ----------
        pagina = PaginaTrabajo("Prueba", "")
        pagina._texto, pagina._inicio = "Produciendo con Gemini…", time.monotonic() - 83
        pagina._contar()
        assert pagina.estado.text() == "Produciendo con Gemini…  1:23"
        pagina._inicio = time.monotonic() - 0.98  # el temporizador salta unos ms antes del segundo: ya es 0:01
        pagina._contar()
        assert pagina.estado.text() == "Produciendo con Gemini…  0:01", pagina.estado.text()

        def lento(aviso):
            aviso("Produciendo…", 0.3)
            time.sleep(2.3)  # el temporizador de Qt puede saltar algo antes del segundo: da tiempo a dos vueltas
            raise RuntimeError("sin cuota")
        boton = QLabel()  # cualquier widget con setEnabled
        assert pagina.lanzar(boton, lento)
        esperar(lambda: pagina.estado.text() == "Produciendo…  0:01")
        esperar(lambda: not pagina.tarea.isRunning())
        app.processEvents()
        assert not pagina.reloj.isActive() and pagina.estado.text() == "" and boton.isEnabled()

        # ---------- Página Música: Gemini por defecto y cómo traer una canción de Suno ----------
        musical = PaginaMusica()
        # En un portátil (728 px) el progreso queda bajo las tarjetas: al empezar se baja hasta él
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(musical)
        area.resize(1100, 600)
        area.show()
        app.processEvents()
        assert musical.estado.mapTo(area.viewport(), QPoint()).y() > area.viewport().height()  # empieza fuera
        assert musical.lanzar(QLabel(), lambda aviso: time.sleep(0.3) or {"resultados": []})
        esperar(lambda: not musical.tarea.isRunning())
        app.processEvents()
        assert 0 < musical.estado.mapTo(area.viewport(), QPoint()).y() < area.viewport().height()
        textos = " ".join(e.text() for e in musical.findChildren(QLabel))
        assert "Por defecto usa Gemini (Lyria 3.5" in textos and "ElevenLabs" in textos
        assert "necesita la facturación de Gemini activada" in textos
        assert "¿Hiciste tu canción en Suno u otra app?" in textos

        # Una canción de fuera (mp3 con ID3 o wav) vale para el video musical y para la Cabina
        mp3, wav = d / "suno.mp3", d / "suno.wav"
        mp3.write_bytes(b"ID3\x04" + b"\x00" * 64)
        wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32)
        for f in (mp3, wav):
            assert seguro.archivo_medio(str(f), seguro.AUDIOS, "canción") == f.resolve()
        videos = []
        video_musical.crear = lambda aviso, **datos: videos.append(datos) or {"resultados": [], "formato": "9:16"}
        musical.cancion.setText(str(mp3))
        musical._video()
        esperar(lambda: videos and not musical.tarea.isRunning())
        assert videos[0]["cancion"] == str(mp3) and videos[0]["letra"] == "", videos

        # En la Cabina, al separar la canción quedan voz y pista listas para «Producir canción» (mezcla y master)
        cabina.separar_cancion = lambda cancion, aviso: {
            "tipo": "separacion", "formato": "audio", "carpeta": str(d), "titulo": Path(cancion).stem,
            "resultados": [{"archivo": str(d / "voz.wav"), "titulo": "Voz (acapella)", "descripcion": "", "hashtags": []},
                           {"archivo": str(d / "pista.wav"), "titulo": "Pista (instrumental)", "descripcion": "",
                            "hashtags": []}]}
        estudio = PaginaCabina()
        estudio.para_separar.setText(str(wav))
        estudio._separar()
        esperar(lambda: not estudio.tarea.isRunning() and estudio.pista.text())
        assert estudio.voz.text() == str(d / "voz.wav") and estudio.pista.text() == str(d / "pista.wav")
        assert estudio.titulo_cancion.text() == "suno"
        # Separar otra canción no pisa el trabajo en curso: beat, toma y título siguen; voz y pista nunca se mezclan
        # de dos canciones, y un título ya escrito se respeta aunque se llenen voz y pista
        referencia = d / "referencia.wav"
        referencia.write_bytes(wav.read_bytes())
        for voz, pista, titulo in (("C:/grabaciones/toma.wav", "C:/beats/mi_beat.wav", "Mi tema"),
                                   ("", "C:/beats/mi_beat.wav", ""), ("", "", "Mi tema")):
            estudio.voz.setText(voz), estudio.pista.setText(pista), estudio.titulo_cancion.setText(titulo)
            estudio.para_separar.setText(str(referencia))
            estudio._separar()
            esperar(lambda: estudio.separar_btn.isEnabled())  # se activa al acabar, después de rellenar
            esperado = (voz, pista) if voz or pista else (str(d / "voz.wav"), str(d / "pista.wav"))
            assert (estudio.voz.text(), estudio.pista.text()) == esperado, (voz, pista, estudio.voz.text())
            assert estudio.titulo_cancion.text() == (titulo or "referencia")
    finally:
        ia.texto_json, musica._gemini, musica.httpx.post, cabina.separar_cancion, video_musical.crear = reales
print("Pruebas de música pasadas.")
