"""Publicar en YouTube a una hora programada (motor/publicar.py y su página) contra un Google falso en 127.0.0.1: sin
red ni claves de verdad. python -m pruebas.publicar"""
import base64
import contextlib
import hashlib
import io
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
import httpx  # noqa: E402

from motor import claves, herramientas, publicar, shorts  # noqa: E402

CODIGO, ACCESO, REFRESCO, SECRETO = "4/codigo-de-un-uso", "ya29.acceso-falso", "1//refresco-falso", "GOCSPX-secreto"
retos, rutas, subidas, metadatos = [], [], [], []
partes = {"falla": True}


class Google(BaseHTTPRequestHandler):
    """El servidor de tokens y la subida reanudable de YouTube, en falso."""
    def _responder(self, codigo, datos=None, cabeceras=()):
        cuerpo = json.dumps(datos).encode() if datos is not None else b""
        self.send_response(codigo)
        for k, v in cabeceras:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _cuerpo(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_POST(self):
        rutas.append(self.path)
        cuerpo = self._cuerpo()
        if self.path == "/token":
            f = {k: v[0] for k, v in parse_qs(cuerpo.decode()).items()}
            if f["grant_type"] == "authorization_code":
                reto = base64.urlsafe_b64encode(hashlib.sha256(f["code_verifier"].encode()).digest()).rstrip(b"=")
                ok = f["code"] == CODIGO and reto.decode() in retos and f["client_secret"] == SECRETO  # PKCE
                return self._responder(200, {"access_token": ACCESO, "refresh_token": REFRESCO, "expires_in": 3599}) \
                    if ok else self._responder(400, {"error": "invalid_grant"})
            if f["refresh_token"] != REFRESCO:  # app en Testing: el permiso caducó a los 7 días
                return self._responder(400, {"error": "invalid_grant", "error_description": "Token has been expired"})
            return self._responder(200, {"access_token": ACCESO, "expires_in": 3599})
        assert self.headers["Authorization"] == f"Bearer {ACCESO}" and self.headers["X-Upload-Content-Length"]
        metadatos.append((self.path, json.loads(cuerpo)))
        sesion = f"http://{self.headers['Host']}/upload/youtube/v3/videos?uploadType=resumable&upload_id=XYZ"
        self._responder(200, cabeceras=[("Location", sesion)])

    def do_PUT(self):
        rutas.append(self.path)
        assert "upload_id=XYZ" in self.path and self.headers["Authorization"] == f"Bearer {ACCESO}"
        rango = self.headers["Content-Range"]
        if rango.startswith("bytes */"):  # ¿cuánto llegó? Se quedó con los primeros 1000 bytes del intento cortado
            return self._responder(308, cabeceras=[("Range", "bytes=0-999")])
        subidas.append((rango, self._cuerpo()))
        if partes["falla"]:
            partes["falla"] = False
            return self._responder(503, {"error": {"message": "backendError"}})
        self._responder(200, {"id": "VID123", "status": {"privacyStatus": "private"}})

    def log_message(self, *args):
        pass


servidor = ThreadingHTTPServer(("127.0.0.1", 0), Google)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{servidor.server_address[1]}"
publicar.TOKEN, publicar.SUBIDA = f"{base}/token", f"{base}/upload/youtube/v3/videos"
_dormir = publicar.time.sleep
publicar.time.sleep = lambda s: None  # sin esperar entre reintentos de la subida


def falla(funcion, *args, error=ValueError, **kwargs):
    try:
        funcion(*args, **kwargs)
    except error as e:
        return str(e)
    raise AssertionError("debió fallar")


def navegador(responde=None):
    """El navegador del usuario: abre la URL de Google y Google redirige a Ráfaga con el código (en otro hilo, como
    de verdad: abrir() no espera)."""
    vistas = []

    def abrir(url):
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        vistas.append((url, q))
        retos.append(q["code_challenge"])
        datos = responde(q) if responde else {"code": CODIGO, "state": q["state"]}
        threading.Thread(target=lambda: httpx.get(q["redirect_uri"], params=datos, timeout=10), daemon=True).start()
    return abrir, vistas


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"
    publicar.HISTORIAL, shorts.PROYECTOS = d / "publicaciones.json", d / "proyectos"
    cliente = d / "client_secret.json"
    cliente.write_text(json.dumps({"installed": {"client_id": "123-abc.apps.googleusercontent.com",
                                                 "client_secret": SECRETO, "redirect_uris": ["http://localhost"]}}),
                       encoding="utf-8")

    # ---------- El client_secret.json: solo el de una «App de escritorio» ----------
    assert publicar.leer_cliente(str(cliente)) == ("123-abc.apps.googleusercontent.com", SECRETO)
    web, lista = d / "web.json", d / "lista.json"
    web.write_text(json.dumps({"web": {"client_id": "1.apps.googleusercontent.com", "client_secret": "x"}}))
    lista.write_text("[1]")
    for malo in (str(web), str(lista), str(d / "no_existe.json"), r"\\atacante.example\s\c.json"):
        assert any(s in falla(publicar.leer_cliente, malo) for s in ("App de escritorio", "carpeta de red")), malo

    # ---------- Conectar: OAuth con 127.0.0.1, PKCE (S256) y state; el permiso queda cifrado ----------
    abrir, vistas = navegador()
    consola = io.StringIO()
    with contextlib.redirect_stderr(consola):
        assert publicar.conectar(str(cliente), abrir=abrir, espera=10) == {"conectado": True}
    url, q = vistas[0]
    assert url.startswith(publicar.AUTORIZAR) and q["code_challenge_method"] == "S256" and q["scope"] == publicar.PERMISO
    assert q["redirect_uri"].startswith("http://127.0.0.1:") and q["access_type"] == "offline" and len(q["state"]) > 20
    assert SECRETO not in url and CODIGO not in consola.getvalue()  # ni el secreto en la URL ni el código en la consola
    cuenta = claves.cargar()["youtube"]
    assert cuenta["clave"] == REFRESCO and cuenta["client_secret"] == SECRETO
    if os.name == "nt":  # cifrado con DPAPI: el archivo no deja ver el permiso
        assert REFRESCO not in claves.ARCHIVO.read_text(encoding="utf-8")
    visto = next(c for c in claves.publico() if c["proveedor"] == "youtube")  # lo que ven la app, el Director y el MCP
    assert "client_secret" not in visto and REFRESCO not in json.dumps(visto)
    assert claves.para("texto") is None and "youtube" not in claves.opciones("imagen")  # nunca va a una IA

    # Un state distinto (otra página que cuela su código), un permiso denegado y nadie que responda: error claro
    abrir, _ = navegador(lambda q: {"code": CODIGO, "state": "otro"})
    assert "no venía de tu inicio de sesión" in falla(publicar.conectar, str(cliente), abrir=abrir, espera=10,
                                                      error=RuntimeError)
    abrir, _ = navegador(lambda q: {"error": "access_denied", "state": q["state"]})
    assert "access_denied" in falla(publicar.conectar, str(cliente), abrir=abrir, espera=10, error=RuntimeError)
    assert "a tiempo" in falla(publicar.conectar, str(cliente), abrir=lambda url: None, espera=0.3, error=RuntimeError)
    # PKCE: si el verificador no es el del reto, Google no da el permiso
    abrir, _ = navegador()
    _token = publicar._pedir_token
    publicar._pedir_token = lambda datos: _token({**datos, "code_verifier": "otro-verificador"})
    try:
        assert "Vuelve a conectar" in falla(publicar.conectar, str(cliente), abrir=abrir, espera=10, error=RuntimeError)
    finally:
        publicar._pedir_token = _token
    assert claves.cargar()["youtube"]["clave"] == REFRESCO  # lo que falló no tocó el permiso guardado

    # ---------- Programar: subida reanudable con la hora de salida en el futuro ----------
    video = d / "mi video.mp4"
    contenido = b"\x00\x00\x00\x18ftypmp42" + os.urandom(2_500_000)  # un MP4 de verdad por su cabecera
    video.write_bytes(contenido)
    en_dos_horas = (datetime.now() + timedelta(hours=2)).replace(second=0, microsecond=0)
    pasos = []
    r = publicar.programar(str(video), "Mi <video> " + "x" * 200, "Descripción ñ" * 600, ["#dembow", "dembow", "rd"],
                           en_dos_horas.isoformat(), aviso=lambda texto, f: pasos.append(f))
    assert r == {"archivo": str(video.resolve()), "red": "youtube", "titulo": ("Mi video " + "x" * 200)[:100],
                 "id": "VID123", "estado": "programado", "hora": r["hora"]}
    ruta, datos = metadatos[-1]
    assert "uploadType=resumable" in ruta and "part=snippet,status" in ruta
    assert datos["status"] == {"privacyStatus": "private", "publishAt": r["hora"], "selfDeclaredMadeForKids": False,
                               "containsSyntheticMedia": True}
    salida = datetime.fromisoformat(datos["status"]["publishAt"])
    assert salida.tzinfo == timezone.utc and salida == en_dos_horas.astimezone(timezone.utc)  # hora del PC → UTC
    assert len(datos["snippet"]["title"]) == 100 and "<" not in datos["snippet"]["title"]
    assert len(datos["snippet"]["description"].encode()) <= 5000 and datos["snippet"]["tags"] == ["dembow", "rd"]
    # Reanudable: el primer PUT se cortó (503), se preguntó cuánto llegó y se mandó solo lo que faltaba
    total = len(contenido)
    assert [rango for rango, _ in subidas] == [f"bytes 0-{total - 1}/{total}", f"bytes 1000-{total - 1}/{total}"]
    assert subidas[1][1] == contenido[1000:] and pasos and max(pasos) == 1.0
    assert publicar.historial() == [r]

    # La hora: al menos 15 minutos en el futuro y con formato válido, antes de subir nada
    antes = len(rutas)
    for hora, se_lee in (((datetime.now() + timedelta(minutes=5)).isoformat(), "15 minutos"),
                         ("2020-01-01T10:00", "15 minutos"), ("mañana a las 6", "no válidas"), ("", "no válidas"),
                         ("1960-01-01T10:00", "no válidas"), ("3500-01-01T10:00", "no válidas")):  # OSError en Windows
        assert se_lee in falla(publicar.programar, str(video), "T", "", (), hora)
    assert "solo se puede programar en YouTube" in falla(publicar.programar, str(video), "T", "", (),
                                                         en_dos_horas.isoformat(), red="tiktok")
    disfrazado = d / "claves.mp4"  # un archivo que no es un video, aunque se llame .mp4, no se sube
    disfrazado.write_bytes(b'{"clave": "sk-x"}')
    assert "no es una imagen, un audio ni un video" in falla(publicar.programar, str(disfrazado), "T", "", (),
                                                             en_dos_horas.isoformat())
    assert len(rutas) == antes  # nada salió de la app

    # invalid_grant: el permiso caducó (app de Google en Testing): se pide volver a conectar, con el porqué
    claves.guardar({**cuenta, "clave": "1//caducado"})
    error = falla(publicar.programar, str(video), "T", "", (), en_dos_horas.isoformat(), error=RuntimeError)
    assert "Vuelve a conectar YouTube" in error and "7 días" in error and "En producción" in error
    claves.borrar("youtube")
    assert "Primero conecta YouTube" in falla(publicar.programar, str(video), "T", "", (), en_dos_horas.isoformat())
    claves.guardar(cuenta)

    # ---------- La herramienta del Director y del MCP ----------
    assert len(herramientas.TODAS) == 16 and "programar_publicacion" in herramientas.TODAS
    partes["falla"] = False
    r = json.loads(herramientas.programar_publicacion(str(video), "Con hashtags", "Mira esto #RD #viral",
                                                      en_dos_horas.isoformat(), red=" YouTube "))  # como la escribe una IA
    assert r["id"] == "VID123" and r["red"] == "youtube" and metadatos[-1][1]["snippet"]["tags"] == ["RD", "viral"]
    # La cuenta de YouTube no va a la IA del Director ni al agente MCP (la página de Claves sí la ve, para quitarla)
    claves.guardar({"proveedor": "groq", "clave": "gsk_" + "x" * 30, "usos": ["texto"]})
    vistos = [c["proveedor"] for c in json.loads(herramientas.listar_opciones())["proveedores"]]
    assert vistos == ["groq"] and "youtube" in [c["proveedor"] for c in claves.publico()]
    claves.borrar("groq")
    from motor import director  # noqa: E402
    assert director.RUTAS["programar_publicacion"] == ("archivo",)  # solo videos del usuario o del estudio

    # ---------- Ningún token en una URL ni en el historial ----------
    for secreto in (ACCESO, REFRESCO, SECRETO, CODIGO, "1//caducado"):
        assert not any(secreto in ruta for ruta in rutas), secreto
        assert secreto not in publicar.HISTORIAL.read_text(encoding="utf-8"), secreto
    publicar.HISTORIAL.write_text("{roto", encoding="utf-8")
    assert publicar.historial() == []  # un historial dañado no rompe la página

    # ---------- La página: solo los videos de Mis proyectos, rellena sus textos y programa ----------
    from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

    from ui.paginas import publicar as pagina_publicar  # noqa: E402
    app = QApplication.instance() or QApplication(["pruebas"])
    QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
    (shorts.PROYECTOS / "1").mkdir(parents=True)
    (shorts.PROYECTOS / "1" / "proyecto.json").write_text(json.dumps({"resultados": [
        {"archivo": str(video), "titulo": "Lugares de RD", "descripcion": "Tres sitios", "hashtags": ["rd", "#viaje"]},
        {"archivo": str(d / "cancion.mp3"), "titulo": "Una canción", "descripcion": "", "hashtags": []}]}),
        encoding="utf-8")
    publicar.HISTORIAL.write_text(json.dumps([{"hora": "2030-01-01T10:00:00Z", "titulo": "Viejo", "id": "A1"}]))
    pagina = pagina_publicar.PaginaPublicar()
    pagina.recargar()
    assert pagina.videos.count() == 1 and "Conectado" in pagina.estado.text()
    assert "youtu.be/A1" in pagina.programados.item(0).text()
    assert pagina.hora.dateTime().toSecsSinceEpoch() > time.time() + 15 * 60
    pagina.videos.setCurrentRow(0)
    assert pagina.titulo.text() == "Lugares de RD" and pagina.hashtags.text() == "#rd #viaje"
    pedidos = []
    _programar = publicar.programar
    publicar.programar = lambda **k: pedidos.append(k) or {"id": "X"}
    try:
        pagina._programar()
        fin = time.monotonic() + 10
        while (not pedidos or pagina.tarea.isRunning()) and time.monotonic() < fin:
            app.processEvents()
        app.processEvents()
    finally:
        publicar.programar = _programar
    k = pedidos[0]
    assert k["archivo"] == str(video) and k["red"] == "youtube" and k["etiquetas"] == ["#rd", "#viaje"]
    assert k["descripcion"] == "Tres sitios\n\n#rd #viaje" and "T" in k["fecha_hora"]

publicar.time.sleep = _dormir
servidor.shutdown()
print("Pruebas de publicar en YouTube pasadas.")
