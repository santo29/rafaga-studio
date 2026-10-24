"""Publicar a una hora programada. v1: YouTube, que guarda el video como privado y lo publica solo a la hora elegida
(status.publishAt), aunque el PC esté apagado. Cada usuario usa su propio cliente OAuth de Google Cloud («App de
escritorio»): el cupo de 100 subidas al día es suyo y no hace falta que Google verifique Ráfaga Studio."""
import base64
import hashlib
import http.server
import json
import re
import secrets
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from . import claves, seguro
from .idioma import t

HISTORIAL = Path(__file__).resolve().parent.parent / "datos" / "publicaciones.json"
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
SUBIDA = "https://www.googleapis.com/upload/youtube/v3/videos"
PERMISO = "https://www.googleapis.com/auth/youtube.upload"
MARGEN = timedelta(minutes=15)  # la subida tiene que terminar antes de la hora de salida


def leer_cliente(ruta: str) -> tuple[str, str]:
    """(client_id, client_secret) del client_secret.json que se descarga de Google Cloud."""
    if seguro.es_ruta_de_red(str(ruta)):  # abrirla ya conectaría por SMB con ese servidor
        raise ValueError(t("Elige un archivo de este PC, no de una carpeta de red."))
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            cliente = json.loads(f.read(65536))["installed"]
        client_id, client_secret = cliente["client_id"], cliente["client_secret"]
        if not (isinstance(client_secret, str) and re.fullmatch(r"[\w.-]+\.apps\.googleusercontent\.com", client_id)):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError(t("Ese archivo no es el client_secret.json de un cliente OAuth «App de escritorio» de Google "
                           "Cloud. Descárgalo otra vez en Credenciales, con el botón de descarga JSON.")) from None
    return client_id, client_secret


def _pedir_token(datos: dict) -> dict:
    """POST al servidor de tokens de Google: los tokens van en el cuerpo, nunca en la URL."""
    try:
        r = httpx.post(TOKEN, data=datos, timeout=30)
    except httpx.HTTPError as e:
        raise RuntimeError(t("No hay conexión con {proveedor}: {error}. Inténtalo de nuevo.", proveedor="Google",
                             error=type(e).__name__)) from None
    try:
        respuesta = r.json()
    except ValueError:
        respuesta = None
    respuesta = respuesta if isinstance(respuesta, dict) else {}
    if respuesta.get("error") == "invalid_grant":
        raise RuntimeError(t("Vuelve a conectar YouTube (si tu app de Google está en Testing, el permiso caduca a "
                             "los 7 días: pásala a En producción)."))
    if r.status_code >= 400:
        raise RuntimeError(t("Google no aceptó la conexión ({codigo}: {error}).", codigo=r.status_code,
                             error=str(respuesta.get("error") or t("sin detalle"))[:80]))
    return respuesta


def conectar(cliente: str, abrir=webbrowser.open, espera: float = 300, aviso=None) -> dict:
    """Conecta el canal de YouTube: abre el navegador para que el usuario dé permiso y guarda ese permiso cifrado
    (claves.json, proveedor «youtube»). OAuth de app de escritorio: redirección a 127.0.0.1 + PKCE (S256) + state."""
    client_id, client_secret = leer_cliente(cliente)
    verificador, state = secrets.token_urlsafe(64), secrets.token_urlsafe(24)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    llegada = {}

    class Respuesta(http.server.BaseHTTPRequestHandler):
        timeout = 5  # una conexión que no manda nada (el navegador la abre por adelantado) no bloquea la espera

        def do_GET(self):
            datos = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
            if "code" in datos or "error" in datos:
                llegada.update(datos)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(t("Ráfaga Studio recibió la respuesta de Google. Ya puedes cerrar esta pestaña.").encode())

        def log_message(self, *args):  # la línea de la petición lleva el código de autorización: nunca a la consola
            pass

    with http.server.HTTPServer(("127.0.0.1", 0), Respuesta) as servidor:
        redireccion = f"http://127.0.0.1:{servidor.server_address[1]}"
        abrir(f"{AUTORIZAR}?" + urlencode({
            "client_id": client_id, "redirect_uri": redireccion, "response_type": "code", "scope": PERMISO,
            "code_challenge": reto, "code_challenge_method": "S256", "state": state, "access_type": "offline",
            "prompt": "consent"}))
        limite = time.monotonic() + espera
        while not llegada and (resta := limite - time.monotonic()) > 0:
            servidor.timeout = resta
            servidor.handle_request()
    if not llegada:
        raise RuntimeError(t("No llegó el permiso de Google a tiempo. Pulsa «Conectar YouTube» otra vez y acepta en el "
                             "navegador."))
    if llegada.get("state") != state:  # otra página intentó colar su código
        raise RuntimeError(t("La respuesta no venía de tu inicio de sesión con Google. Inténtalo de nuevo."))
    if "code" not in llegada:
        raise RuntimeError(t("Google no dio el permiso ({error}).", error=llegada.get("error", "")[:60]))
    r = _pedir_token({"grant_type": "authorization_code", "code": llegada["code"], "redirect_uri": redireccion,
                      "code_verifier": verificador, "client_id": client_id, "client_secret": client_secret})
    if not r.get("refresh_token"):
        raise RuntimeError(t("Google no dio un permiso duradero. Quita el acceso de tu app en myaccount.google.com → "
                             "Seguridad y vuelve a conectar."))
    claves.guardar({"proveedor": "youtube", "clave": r["refresh_token"], "client_id": client_id,
                    "client_secret": client_secret, "usos": ["publicar"]})
    return {"conectado": True}


def hora_utc(fecha_hora: str) -> datetime:
    """La hora de salida en UTC (sin zona horaria, es la hora de este PC), al menos 15 minutos en el futuro."""
    try:
        hora = datetime.fromisoformat(str(fecha_hora).strip()).astimezone(timezone.utc)
    except (ValueError, OverflowError):  # OverflowError: el año 9999 en una zona detrás de UTC
        raise ValueError(t("Fecha y hora no válidas ({fecha!r:.40}); usa el formato 2026-10-25T18:00.",
                           fecha=fecha_hora)) from None
    if hora < datetime.now(timezone.utc) + MARGEN:
        raise ValueError(t("La hora de salida tiene que ser al menos 15 minutos en el futuro."))
    return hora.replace(microsecond=0)


def _etiquetas(lista) -> list[str]:
    """Hashtags como etiquetas de YouTube: sin «#» ni repetidas y, entre todas, como mucho 500 caracteres."""
    salida, largo = [], 0
    for e in lista:
        e = re.sub(r"[<>,#]", "", str(e)).strip()
        if e and e not in salida and largo + len(e) + 1 <= 500:
            salida.append(e)
            largo += len(e) + 1
    return salida


def _error(r: httpx.Response) -> RuntimeError:
    try:
        motivo = r.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        motivo = ""
    return RuntimeError(t("YouTube no aceptó el video ({codigo}): {motivo}", codigo=r.status_code,
                          motivo=str(motivo)[:200] or t("sin detalle")))


def _trozos(f, tamano: int, aviso):
    while trozo := f.read(1 << 20):
        yield trozo
        aviso(t("Subiendo a YouTube…"), f.tell() / tamano)


def _subir(sesion: str, archivo: Path, cabecera: dict, aviso) -> httpx.Response:
    """PUT del video a la sesión reanudable. Si se corta (red o error 5xx), pregunta cuánto llegó (308 con «Range:
    bytes=0-N») y sigue desde ahí, hasta 3 veces."""
    tamano, enviado = archivo.stat().st_size, 0
    with open(archivo, "rb") as f:
        for intento in range(4):
            try:
                if intento:
                    time.sleep(2 * intento)
                    r = httpx.put(sesion, headers={**cabecera, "Content-Range": f"bytes */{tamano}"}, timeout=30)
                    if r.status_code != 308:
                        if r.status_code < 500:
                            return r
                        continue
                    rango = r.headers.get("Range")
                    enviado = int(rango.rsplit("-", 1)[1]) + 1 if rango else 0
                f.seek(enviado)
                r = httpx.put(sesion, content=_trozos(f, tamano, aviso), timeout=120, headers={
                    **cabecera, "Content-Type": "video/*", "Content-Length": str(tamano - enviado),
                    "Content-Range": f"bytes {enviado}-{tamano - 1}/{tamano}"})
                if r.status_code < 500:
                    return r
            except httpx.TransportError:
                pass
    raise RuntimeError(t("La subida a YouTube se cortó varias veces. Revisa tu conexión e inténtalo de nuevo."))


def programar(archivo: str, titulo: str, descripcion: str = "", etiquetas=(), fecha_hora: str = "",
              red: str = "youtube", aviso=None) -> dict:
    """Sube el video a YouTube como privado con su hora de salida: YouTube lo publica solo a esa hora, aunque el PC
    esté apagado. Devuelve lo apuntado en el historial (datos/publicaciones.json)."""
    aviso = aviso or (lambda texto, f: None)
    if red != "youtube":
        raise ValueError(t("Por ahora solo se puede programar en YouTube; {red} llegará más adelante.",
                           red=str(red)[:30]))
    real = seguro.archivo_medio(archivo, seguro.VIDEOS, t("video"))
    hora = hora_utc(fecha_hora).strftime("%Y-%m-%dT%H:%M:%SZ")
    cuenta = claves.cargar().get("youtube")
    if not cuenta:
        raise ValueError(t("Primero conecta YouTube en la página «Publicar»."))
    # YouTube rechaza «<» y «>»; el título va hasta 100 caracteres y la descripción hasta 5000 bytes
    titulo = re.sub(r"[<>]", "", str(titulo or "")).strip()[:100] or real.stem[:100]
    descripcion = re.sub(r"[<>]", "", str(descripcion or "")).encode()[:5000].decode(errors="ignore")
    datos = {"snippet": {"title": titulo, "description": descripcion, "tags": _etiquetas(etiquetas)},
             "status": {"privacyStatus": "private", "publishAt": hora, "selfDeclaredMadeForKids": False,
                        "containsSyntheticMedia": True}}
    aviso(t("Conectando con YouTube…"), 0)
    acceso = _pedir_token({"grant_type": "refresh_token", "refresh_token": cuenta["clave"],
                           "client_id": cuenta["client_id"], "client_secret": cuenta["client_secret"]})
    cabecera = {"Authorization": f"Bearer {acceso['access_token']}"}
    try:
        r = httpx.post(f"{SUBIDA}?uploadType=resumable&part=snippet,status", json=datos, timeout=60, headers={
            **cabecera, "X-Upload-Content-Type": "video/*", "X-Upload-Content-Length": str(real.stat().st_size)})
    except httpx.HTTPError as e:
        raise RuntimeError(t("No hay conexión con {proveedor}: {error}. Inténtalo de nuevo.", proveedor="YouTube",
                             error=type(e).__name__)) from None
    sesion = r.headers.get("Location", "")
    # el permiso solo viaja a la sesión de subida del mismo servidor de Google
    if r.status_code >= 400 or urlsplit(sesion).netloc != urlsplit(SUBIDA).netloc:
        raise _error(r)
    r = _subir(sesion, real, cabecera, aviso)
    try:
        video = str(r.json()["id"]) if r.status_code in (200, 201) else ""
    except (ValueError, KeyError, TypeError):
        video = ""
    if not video:
        raise _error(r)
    entrada = {"archivo": str(real), "red": "youtube", "hora": hora, "titulo": titulo, "id": video,
               "estado": "programado"}
    HISTORIAL.parent.mkdir(exist_ok=True)
    HISTORIAL.write_text(json.dumps([*reversed(historial()), entrada], ensure_ascii=False, indent=2), encoding="utf-8")
    return entrada


def historial() -> list[dict]:
    """Lo programado desde este PC, del más nuevo al más viejo. Un archivo roto no rompe la página."""
    try:
        lista = json.loads(HISTORIAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in reversed(lista) if isinstance(p, dict)] if isinstance(lista, list) else []
