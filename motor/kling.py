"""Kling (Kuaishou), de pago: anima la imagen de una escena en un clip mudo o con voz propia, con la clave del usuario.
Nunca va solo: quien llama enseña antes lo máximo que puede costar (estimar) y el usuario dice que sí."""
import base64
import re
import time
from pathlib import Path

import httpx

from . import seguro
from .idioma import t

NOMBRE = "Kling"
CONSOLA = "https://kling.ai/dev/api-key"
BASES = ("https://api-singapore.klingai.com", "https://api-beijing.klingai.com")  # cada clave vale solo en su región
SEGUNDOS_CLIP = 5  # mudo: el estudio lo repite en bucle
SEGUNDOS_VOZ = 8
# Del mejor al más barato: el orden en que se prueban. US$ por segundo a 720p, precio de lista de kling.ai/dev/pricing
# (24-10-2026), sin el descuento de los paquetes de prueba: el aviso nunca se queda corto. None = no habla a 720p.
MODELOS = [{"id": "kling-4.0", "mudo": 0.157, "voz": 0.157},  # precio de estreno; abre a todos el 28-10-2026
           {"id": "kling-3.0", "mudo": 0.084, "voz": 0.126},
           {"id": "kling-3.0-turbo", "mudo": 0.112, "voz": 0.112},  # cobra siempre con audio
           {"id": "kling-2.6", "mudo": 0.042, "voz": None},  # su audio solo sale a 1080p
           {"id": "kling-2.5-turbo", "mudo": 0.042, "voz": None}]
_AJUSTE_AUDIO = {"kling-3.0", "kling-2.6"}  # los únicos con settings.audio (4.0 y 3.0 Turbo suenan siempre)
_DURACIONES = {"kling-4.0": range(3, 31), "kling-2.6": (5, 10), "kling-2.5-turbo": (5, 10)}  # los demás, 3 a 15 s
ESPERA, PLAZO = 5, 12 * 60  # cada cuánto se mira la tarea y hasta cuándo (tarda de 1 a 5 min)
PAUSA, REINTENTOS = 1, 5  # ante el límite de pedidos: primera espera (se dobla cada vez) y vueltas


def validar(clave: str) -> dict:
    """Comprueba la clave sin gastar (consultar tareas es gratis). Beijing solo si Singapur dice 401: la clave sería
    de la otra región. 401 en las dos = no es de Kling (claves.detectar prueba entonces otro proveedor)."""
    for base in BASES:
        r = httpx.get(f"{base}/tasks?task_ids=0", headers={"Authorization": f"Bearer {clave}"}, timeout=20)
        if r.status_code != 401:
            break
    r.raise_for_status()
    return {"base": base}


def _modelos(info: dict, voz: bool) -> list[dict]:
    """Los que se probarán, en orden: desde el último que funcionó (o el mejor); con voz, solo los que hablan."""
    lista = [m for m in MODELOS if m["voz" if voz else "mudo"] is not None]
    ids = [m["id"] for m in lista]
    ultimo = info.get("modelo_voz" if voz else "modelo_video")
    return lista[ids.index(ultimo):] if ultimo in ids else lista


def _duracion(modelo: str, segundos: float) -> int:
    """Los segundos que se piden de verdad: lo más corto que admite el modelo y cubre lo pedido (o lo más largo)."""
    validas = _DURACIONES.get(modelo, range(3, 16))
    return next((d for d in validas if d >= segundos), max(validas))


def estimar(info: dict, segundos: float, voz: bool = False) -> float:
    """Lo MÁXIMO que puede costar un clip: el más caro de los modelos que aún se pueden probar (un respaldo puede
    costar más que el último que funcionó), por los segundos que se le piden de verdad."""
    return max(m["voz" if voz else "mudo"] * _duracion(m["id"], segundos) for m in _modelos(info, voz))


def _codigo(r: httpx.Response) -> int | None:
    try:
        return int(r.json().get("code") or 0)
    except (ValueError, TypeError, AttributeError):
        return None


def _crear(url: str, cabecera: dict, cuerpo: dict) -> httpx.Response:
    """Crea la tarea. Con el límite de pedidos (1302) o de tareas a la vez (1303) espera y repite, cada vez el doble."""
    from . import ia
    for intento in range(REINTENTOS):
        if intento:
            time.sleep(PAUSA * 2 ** intento)
        try:
            r = httpx.post(url, headers=cabecera, json=cuerpo, timeout=120)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as e:  # no llegó: ni tarea ni cobro
            raise RuntimeError(t("No hay conexión con {proveedor}: {error}. Inténtalo de nuevo.", proveedor=NOMBRE,
                                 error=type(e).__name__))
        except httpx.HTTPError as e:  # llegó y no se sabe si creó (y cobra) la tarea: no se pide otra a ciegas
            raise ia.Cobrado(t("Se cortó la conexión con {nombre} al pedir el video; puede que lo haya hecho y "
                               "cobrado: {error}", nombre=NOMBRE, error=type(e).__name__))
        if _codigo(r) not in (1302, 1303):
            return r
    return r


def _motivo(r: httpx.Response, codigo: int | None, clave: str) -> str:
    """El error de Kling en claro (el cuerpo de la respuesta, nunca la clave)."""
    detalle = " ".join(r.text.split())[:300].replace(clave, "…")
    if r.status_code == 401:
        return t("{nombre} no aceptó la clave: conecta una nueva en «Claves de IA» (se consigue en {consola}).",
                 nombre=NOMBRE, consola=CONSOLA)
    if codigo in (1101, 1102):
        return t("Kling: no te queda saldo, o tu paquete se acabó o venció. Recarga en {consola} y vuelve a "
                 "intentarlo.", consola=CONSOLA)
    if codigo in (1300, 1301):
        return t("{nombre} rechazó la escena por sus normas de contenido (no se cobró): {detalle}", nombre=NOMBRE,
                 detalle=detalle)
    if codigo in (1302, 1303):
        return t("{nombre} tiene demasiados pedidos a la vez; espera unos minutos y vuelve a intentarlo.",
                 nombre=NOMBRE)
    return t("{nombre} respondió {codigo}: {detalle}", nombre=NOMBRE, codigo=r.status_code, detalle=detalle)


def _cobrada(tarea: dict) -> bool:
    """Si Kling dice que cobró la tarea (algún importe en billing). Un importe que no se entiende cuenta como cobro."""
    for cargo in tarea.get("billing") or []:
        try:
            if float(cargo.get("amount") or 0) > 0:
                return True
        except (ValueError, TypeError, AttributeError):
            return True
    return False


def _esperar(url: str, cabecera: dict) -> dict:
    """La tarea cuando termina, o {} si no termina dentro de PLAZO. Un corte de red de un momento no la pierde."""
    limite = time.monotonic() + PLAZO
    while time.monotonic() < limite:
        time.sleep(ESPERA)
        try:
            tarea = httpx.get(url, headers=cabecera, timeout=30).json()["data"][0]
        except (httpx.HTTPError, ValueError, LookupError, TypeError):
            continue
        if isinstance(tarea, dict) and tarea.get("status") in ("succeeded", "failed"):
            return tarea
    return {}


def _generar(info: dict, imagen: Path, prompt: str, destino: Path, segundos: float, voz: bool) -> str:
    from . import ia  # ia también importa este módulo
    base = info.get("base") if info.get("base") in BASES else BASES[0]  # la clave solo viaja a la API de Kling
    cabecera = {"Authorization": f"Bearer {info['clave']}"}
    foto = base64.b64encode(imagen.read_bytes()).decode()  # en crudo, sin «data:»
    for m in _modelos(info, voz):
        modelo = m["id"]
        ajustes = {"resolution": "720p", "duration": _duracion(modelo, segundos)}
        if modelo in _AJUSTE_AUDIO:
            ajustes["audio"] = "native" if voz else "off"
        r = _crear(f"{base}/image-to-video/{modelo}", cabecera, {
            "contents": [{"type": "prompt", "text": prompt[:2500]}, {"type": "first_frame", "url": foto}],
            "settings": ajustes, "options": {"watermark_info": {"enabled": False}}})
        codigo = _codigo(r)
        if codigo in (1103, 1203):  # la cuenta no tiene este modelo (o aún no abrió): el siguiente, sin pagar
            continue
        if r.is_error or codigo:
            raise RuntimeError(_motivo(r, codigo, info["clave"]))
        try:
            tarea = r.json()["data"]["id"]
        except (ValueError, LookupError, TypeError):
            tarea = None
        if not isinstance(tarea, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", tarea):  # va en una URL con la clave
            raise ia.Cobrado(t("{nombre} devolvió una tarea inesperada", nombre=NOMBRE))
        hecha = _esperar(f"{base}/tasks?task_ids={tarea}", cabecera)
        if hecha.get("status") == "failed" and not _cobrada(hecha):
            raise RuntimeError(t("{nombre} no pudo hacer el video (no se cobró): {detalle}", nombre=NOMBRE,
                                 detalle=str(hecha.get("message") or "")[:300]))
        try:
            if hecha.get("status") != "succeeded":  # falló y la cobró, o no terminó a tiempo
                raise RuntimeError(str(hecha.get("message") or t("{nombre} no terminó el video a tiempo",
                                                                  nombre=NOMBRE))[:300])
            url = next((o.get("url") for o in hecha.get("outputs") or []
                        if isinstance(o, dict) and o.get("type") == "video"), None)
            if not isinstance(url, str):
                raise RuntimeError(t("{nombre} no devolvió ningún video", nombre=NOMBRE))
            ia._clip_real(seguro.descargar(url, tope=ia.VIDEO_MAXIMO, plazo=300), destino)  # la CDN, sin la clave
            return modelo
        except Exception as error:  # la tarea ya existe y Kling la cobra
            raise ia.Cobrado(str(error) or type(error).__name__) from error
    raise RuntimeError(t("Tu cuenta de Kling no puede usar ninguno de sus modelos de video; revisa tus paquetes en "
                         "{consola}.", consola=CONSOLA))


def animar(info: dict, imagen: Path, prompt: str, destino: Path, segundos: float = SEGUNDOS_CLIP) -> str:
    """Imagen -> clip MUDO en `destino`. Devuelve el modelo que lo hizo (se guarda para empezar por él la próxima)."""
    return _generar(info, imagen, prompt, destino, segundos, voz=False)


def hablar(info: dict, imagen: Path | None, prompt: str, destino: Path, segundos: float = SEGUNDOS_VOZ) -> str:
    """Clip CON audio propio: el prompt ya trae el diálogo en español entre comillas. La imagen es el primer
    fotograma."""
    if imagen is None:  # las escenas del estudio siempre tienen imagen
        raise ValueError(t("Kling necesita la imagen de la escena para hacerla hablar."))
    return _generar(info, imagen, prompt, destino, segundos, voz=True)
