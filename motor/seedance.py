"""Seedance (ByteDance, en BytePlus ModelArk), de pago: anima la imagen de una escena en un clip mudo o con voz propia,
con la clave del usuario. Nunca va solo: quien llama enseña antes lo máximo que puede costar (estimar) y el usuario
dice que sí."""
import base64
import re
import time
from pathlib import Path

import httpx

from . import guardia, seguro
from .idioma import t

NOMBRE = "Seedance"
CONSOLA = "https://ai.byteplus.com/ark/region:ap-southeast-1/apiKey"
BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"  # solo la región de Asia tiene Seedance
SEGUNDOS_CLIP = 5  # mudo: el estudio lo repite en bucle
SEGUNDOS_VOZ = 8
# Del mejor al más barato: el orden en que se prueban. US$ por segundo a 720p según docs.byteplus.com/en/docs/modelark/
# model-pricing (24-10-2026): tokens = segundos × ancho × alto × 24 / 1024, con el fotograma de 720p más grande de su
# tabla (4:3 en 2.x, 21:9 en 1.0), porque «adaptive» sigue a la imagen y un 16:9 sale algo más barato; redondeado hacia
# arriba. En 2.x el audio no cambia el precio; 1.0 no habla. (Seedance 1.5 Pro no: se retira el 11-11-2026.)
MODELOS = [{"id": "dreamina-seedance-2-5-260628", "mudo": 0.233, "voz": 0.233},
           {"id": "dreamina-seedance-2-0-260128", "mudo": 0.153, "voz": 0.153},
           {"id": "dreamina-seedance-2-0-fast-260128", "mudo": 0.122, "voz": 0.122},
           {"id": "dreamina-seedance-2-0-mini-260615", "mudo": 0.077, "voz": 0.077},
           {"id": "seedance-1-0-pro-250528", "mudo": 0.057, "voz": None},
           {"id": "seedance-1-0-pro-fast-251015", "mudo": 0.023, "voz": None}]
_DURACIONES = {"dreamina-seedance-2-5-260628": range(4, 31), "seedance-1-0-pro-250528": range(2, 13),
               "seedance-1-0-pro-fast-251015": range(2, 13)}  # la serie 2.0, de 4 a 15 s
# La cuenta no tiene el modelo activado: se prueba el siguiente, sin pagar (también InvalidEndpointOrModel.*)
_SIN_MODELO = ("ModelNotOpen", "OperationDenied.ServiceNotOpen")
# 2.x no acepta caras reales en la imagen; 1.0 no tiene esa regla, así que un clip mudo pasa al siguiente
_CARA_REAL = "InputImageSensitiveContentDetected.PrivacyInformation"
ESPERA, PLAZO = 5, 12 * 60  # cada cuánto se mira la tarea y hasta cuándo
PAUSA, REINTENTOS = 1, 5  # ante el límite de pedidos (429): primera espera (se dobla cada vez) y vueltas


def validar(clave: str) -> dict:
    """Comprueba la clave sin gastar (listar tareas es gratis). 401 = no es de BytePlus (claves.detectar prueba
    entonces otro proveedor)."""
    r = httpx.get(f"{BASE}/contents/generations/tasks?page_size=1", headers={"Authorization": f"Bearer {clave}"},
                  timeout=20)
    r.raise_for_status()
    return {}


def _modelos(info: dict, voz: bool) -> list[dict]:
    """Los que se probarán, en orden: desde el último que funcionó (o el mejor); con voz, solo los que hablan."""
    lista = [m for m in MODELOS if m["voz" if voz else "mudo"] is not None]
    ids = [m["id"] for m in lista]
    ultimo = info.get("modelo_voz" if voz else "modelo_video")
    return lista[ids.index(ultimo):] if ultimo in ids else lista


def _duracion(modelo: str, segundos: float) -> int:
    """Los segundos que se piden de verdad: lo más corto que admite el modelo y cubre lo pedido (o lo más largo)."""
    validas = _DURACIONES.get(modelo, range(4, 16))
    return next((d for d in validas if d >= segundos), max(validas))


def estimar(info: dict, segundos: float, voz: bool = False) -> float:
    """Lo MÁXIMO que puede costar un clip: el más caro de los modelos que aún se pueden probar (un respaldo puede
    costar más que el último que funcionó), por los segundos que se le piden de verdad."""
    return max(m["voz" if voz else "mudo"] * _duracion(m["id"], segundos) for m in _modelos(info, voz))


def _codigo(r: httpx.Response) -> str:
    try:
        return str(r.json()["error"]["code"])
    except (ValueError, LookupError, TypeError):
        return ""


def _crear(cabecera: dict, cuerpo: dict) -> httpx.Response:
    """Crea la tarea. Con el límite de pedidos (429) espera y repite, cada vez el doble."""
    from . import ia
    for intento in range(REINTENTOS):
        if intento:
            time.sleep(PAUSA * 2 ** intento)
        try:
            r = httpx.post(f"{BASE}/contents/generations/tasks", headers=cabecera, json=cuerpo, timeout=120)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as e:  # no llegó: ni tarea ni cobro
            raise RuntimeError(t("No hay conexión con {proveedor}: {error}. Inténtalo de nuevo.", proveedor=NOMBRE,
                                 error=type(e).__name__))
        except httpx.HTTPError as e:  # llegó y no se sabe si creó (y cobra) la tarea: no se pide otra a ciegas
            raise ia.Cobrado(t("Se cortó la conexión con {nombre} al pedir el video; puede que lo haya hecho y "
                               "cobrado: {error}", nombre=NOMBRE, error=type(e).__name__))
        if r.status_code != 429:
            return r
    return r


def _motivo(r: httpx.Response, codigo: str, clave: str) -> str:
    """El error de BytePlus en claro (el cuerpo de la respuesta, nunca la clave)."""
    from .ia import motivo  # aquí: ia también carga este módulo (por claves)
    detalle = motivo(r).replace(clave, "…")
    if r.status_code == 401:
        return t("{nombre} no aceptó la clave: conecta una nueva en «Claves de IA» (se consigue en {consola}).",
                 nombre=NOMBRE, consola=CONSOLA)
    if codigo in ("AccountOverdueError", "OperationDenied.ServiceOverdue"):
        return t("Seedance: tu cuenta de BytePlus no tiene saldo. Recarga en {consola}; para activar Seedance 2.x la "
                 "cuenta necesita al menos US$30.", consola=CONSOLA)
    if "SensitiveContentDetected" in codigo:
        return t("{nombre} rechazó la escena por sus normas de contenido (no se cobró): {detalle}", nombre=NOMBRE,
                 detalle=detalle)
    if r.status_code == 429:
        return t("{nombre} tiene demasiados pedidos a la vez; espera unos minutos y vuelve a intentarlo.",
                 nombre=NOMBRE)
    return t("{nombre} respondió {codigo}: {detalle}", nombre=NOMBRE, codigo=r.status_code, detalle=detalle)


def _esperar(url: str, cabecera: dict) -> dict:
    """La tarea cuando termina, o {} si no termina dentro de PLAZO. Un corte de red de un momento no la pierde."""
    limite = time.monotonic() + PLAZO
    while time.monotonic() < limite:
        time.sleep(ESPERA)
        try:
            tarea = seguro.pedir("GET", url, headers=cabecera, plazo=30).json()  # plazo total: ver seguro.pedir
        except (httpx.HTTPError, ValueError):
            continue
        if isinstance(tarea, dict) and tarea.get("status") in ("succeeded", "failed", "expired", "cancelled"):
            return tarea
    return {}


def _generar(info: dict, imagen: Path | None, prompt: str, destino: Path, segundos: float, voz: bool) -> str:
    guardia.sin_bloqueo()  # de pago: con el estudio bloqueado no empieza
    from . import ia  # ia también importa este módulo
    cabecera = {"Authorization": f"Bearer {info['clave']}"}
    contenido = [{"type": "text", "text": prompt}]
    if imagen:
        tipo = {".png": "image/png", ".webp": "image/webp"}.get(imagen.suffix.lower(), "image/jpeg")
        contenido.append({"type": "image_url", "role": "first_frame", "image_url": {
            "url": f"data:{tipo};base64,{base64.b64encode(imagen.read_bytes()).decode()}"}})
    for m in _modelos(info, voz):
        modelo = m["id"]
        cuerpo = {"model": modelo, "content": contenido, "ratio": "adaptive", "duration": _duracion(modelo, segundos),
                  "resolution": "720p", "watermark": False}
        if m["voz"] is not None:  # solo los 2.x tienen audio: a 1.0 no se le manda
            cuerpo["generate_audio"] = voz
        r = _crear(cabecera, cuerpo)
        codigo = _codigo(r)
        if codigo in _SIN_MODELO or codigo.startswith("InvalidEndpointOrModel.") or (not voz and codigo == _CARA_REAL):
            continue
        if r.is_error:
            raise RuntimeError(_motivo(r, codigo, info["clave"]))
        try:
            tarea = r.json()["id"]
        except (ValueError, LookupError, TypeError):
            tarea = None
        if not isinstance(tarea, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", tarea):  # va en una URL con la clave
            raise ia.Cobrado(t("{nombre} devolvió una tarea inesperada", nombre=NOMBRE))
        url_tarea = f"{BASE}/contents/generations/tasks/{tarea}"
        try:
            hecha = _esperar(url_tarea, cabecera)
            if hecha.get("status") in ("failed", "expired", "cancelled"):  # BytePlus no cobra lo que no sale
                e = hecha.get("error")
                detalle = f"{e.get('code')}: {e.get('message')}" if isinstance(e, dict) else hecha["status"]
                raise RuntimeError(t("{nombre} no pudo hacer el video (no se cobró): {detalle}", nombre=NOMBRE,
                                     detalle=detalle[:300]))
            try:
                if hecha.get("status") != "succeeded":
                    raise RuntimeError(t("{nombre} no terminó el video a tiempo", nombre=NOMBRE))
                url = (hecha.get("content") or {}).get("video_url")
                if not isinstance(url, str):
                    raise RuntimeError(t("{nombre} no devolvió ningún video", nombre=NOMBRE))
                ia._clip_real(seguro.descargar(url, tope=ia.VIDEO_MAXIMO, plazo=300), destino)  # la CDN, sin la clave
                return modelo
            except Exception as error:  # hecho (o aún en marcha) y BytePlus lo cobra
                raise ia.Cobrado(str(error) or type(error).__name__) from error
        finally:  # el registro (con la foto y el pedido) no se queda allí; si no se borra, BytePlus lo quita en 7 días
            try:
                httpx.delete(url_tarea, headers=cabecera, timeout=30)
            except httpx.HTTPError:
                pass
    raise RuntimeError(t("Tu cuenta de BytePlus no tiene activado ningún modelo de Seedance: actívalos en {consola} "
                         "(Seedance 2.x pide al menos US$30 en la cuenta).", consola=CONSOLA))


def animar(info: dict, imagen: Path, prompt: str, destino: Path, segundos: float = SEGUNDOS_CLIP) -> str:
    """Imagen -> clip MUDO en `destino`. Devuelve el modelo que lo hizo (se guarda para empezar por él la próxima)."""
    return _generar(info, imagen, prompt, destino, segundos, voz=False)


def hablar(info: dict, imagen: Path | None, prompt: str, destino: Path, segundos: float = SEGUNDOS_VOZ) -> str:
    """Clip CON audio propio: el prompt ya trae el diálogo en español entre comillas. La imagen (si hay) es el primer
    fotograma; sin ella, el video sale solo del texto."""
    return _generar(info, imagen, prompt, destino, segundos, voz=True)
