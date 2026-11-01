"""Rotación de nubes: cada tarea prueba primero lo gratis (cuota diaria, este PC) y por último lo de pago. Para animar,
tu nube Modal (privada, de tu crédito, sin cola) va antes que el Space público de Hugging Face, que solo se usa sin
ella. Un servicio que dijo «sin saldo» va el último (claves.recordar)."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import httpx

from . import actividad, claves, seguro
from .idioma import t

USO = Path(__file__).resolve().parent.parent / "datos" / "uso_nubes.json"

# Del más barato al más caro. "pc" = este ordenador (gratis, más lento).
ORDEN = {
    "imagen": ["cloudflare", "pollinations", "huggingface", "replicate", "openai", "gemini", "gratis_sin_clave"],
    "video": ["modal", "huggingface", "pollinations", "kling", "seedance"],
    # Privacidad: tus canciones y tu voz no salen de tu PC (Demucs local; ver _separar_pc).
    "separacion": ["pc"],
    # Tu cara y tu voz: ia.avatar pasa solo una de las dos (la que elegiste), nunca una como respaldo de la otra
    "avatar": ["modal", "huggingface"],
}
NOMBRES = {"huggingface": t("Hugging Face (cuota gratis)"), "modal": t("tu nube Modal"), "pollinations": "Pollinations",
           "pc": t("este PC"), "cloudflare": t("Cloudflare (gratis diario)"), "openai": "OpenAI",
           "replicate": "Replicate", "gratis_sin_clave": t("Pollinations sin clave"),
           "gemini": t("Gemini (de pago)"), "kling": t("Kling (de pago)"), "seedance": t("Seedance (de pago)")}
# Opciones que funcionan sin clave. Los Spaces de Hugging Face se usan sin token (cuota anónima: ~2 min de GPU al día).
SIEMPRE = {"pc", "gratis_sin_clave", "huggingface"}
ESPERA_HF = 300  # segundos máximos en la cola gratis antes de pasar a la siguiente opción
TOPE_SPACE = 300 * 1024 ** 2  # lo más que se baja de un Space (un clip de 5 s pesa unos pocos MB)


def token_hf() -> str | None:
    return (claves.cargar().get("huggingface") or {}).get("clave")


def llamar_space(espacio: str, *entradas, api_name: str, espera: int = ESPERA_HF, **parametros):
    """Llama a un Space de Hugging Face con o sin token; si la cola gratis tarda más de `espera` segundos, se rinde."""
    from urllib.parse import urljoin, urlsplit

    from gradio_client import Client
    from huggingface_hub import get_space_runtime

    class _Cliente(Client):
        """El /config lo sirve el Space: un «api_prefix» absoluto (http://127.0.0.1:…/) mandaría todas las peticiones de
        gradio_client, con tu imagen y tu pedido, a otra dirección (tu red local), sin pasar por seguro. Se mira con el
        mismo cálculo que hace la librería, antes de que lo use."""

        def _get_config(self):
            config = super()._get_config()
            destino = urljoin(self.src, str(config.get("api_prefix", "")).lstrip("/") + "/")
            if urlsplit(destino)[:2] != urlsplit(self.src)[:2]:
                raise RuntimeError(t("el Space pidió hablar con otra dirección"))
            return config

    def estado():
        return str(get_space_runtime(espacio, token=token_hf()).stage)
    # Construyéndose: Client() esperaría sin límite. Roto o pausado: no va a responder. En los dos casos se pasa a la
    # siguiente opción. Dormido o arrancando: Client() no espera (5 s y se rinde), así que se despierta visitando su
    # página y se espera aquí, con el mismo límite que la cola.
    # ponytail: probado solo con Spaces encendidos; si uno dormido no despierta así, se agota la espera y pasa al siguiente.
    no_sirve = ("BUILDING", "NO_APP_FILE", "CONFIG_ERROR", "BUILD_ERROR", "RUNTIME_ERROR", "PAUSED")
    actual, limite_espera, despertado = estado(), time.time() + espera, False
    while not actual.startswith("RUNNING"):
        if actual in no_sirve or time.time() > limite_espera:
            raise RuntimeError(t("el Space de Hugging Face no está disponible ahora ({estado})", estado=actual))
        if not despertado:
            httpx.get(f"https://huggingface.co/spaces/{espacio}", timeout=30, follow_redirects=True)
            despertado = True
        time.sleep(5)
        actual = estado()
    # token=False: NUNCA se manda el token del usuario a un Space de terceros. gradio_client lo reenviaría a cualquier
    # dirección que el Space devuelva, y su dueño podría robarlo. (None tampoco sirve: cogería el token guardado en
    # el PC.) Contrapartida: se usa la cuota anónima de ZeroGPU.
    # download_files=False: gradio_client bajaría los archivos siguiendo cualquier URL o redirección que el Space
    # quiera (también hacia tu red local) y sin tope de tamaño. Se bajan aquí, solo desde el propio Space.
    cliente = _Cliente(espacio, token=False, verbose=False, download_files=False)
    trabajo = cliente.submit(*entradas, api_name=api_name, **parametros)
    try:
        resultado = trabajo.result(timeout=espera)
    except TimeoutError:
        trabajo.cancel()
        raise RuntimeError(t("la cola gratis de Hugging Face tardó más de {minutos} min", minutos=espera // 60))
    from gradio_client import utils
    raiz, bajados = cliente.src_prefixed, []

    def bajar(archivo: dict) -> bytes | None:
        if bajados:  # solo el primero (el que se usa): un Space no puede multiplicar el tope devolviendo cientos
            return None
        bajados.append(archivo)
        return seguro.descargar(raiz + "file=" + utils.encode_file_path(archivo["path"]), tope=TOPE_SPACE)
    return utils.traverse(resultado, bajar, lambda d: utils.is_file_obj_with_meta(d) or utils.is_file_obj(d))


def archivo_del_space(resultado) -> bytes:
    """El archivo que devolvió el Space (ya bajado por llamar_space), suelto o dentro de {"video": …}."""
    datos = resultado.get("video") if isinstance(resultado, dict) else resultado
    if not isinstance(datos, bytes):
        raise RuntimeError(t("el Space no devolvió ningún archivo"))
    return datos


def _hoy() -> dict:
    try:
        uso = json.loads(USO.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):  # vacío o a medio escribir: el contador es solo informativo
        uso = {}
    if not isinstance(uso, dict) or uso.get("fecha") != time.strftime("%Y-%m-%d"):  # otro día o forma rara
        uso = {"fecha": time.strftime("%Y-%m-%d")}
    return uso


def contar(proveedor: str) -> None:
    uso = _hoy()
    previo = uso.get(proveedor, 0)
    uso[proveedor] = (previo if isinstance(previo, int) else 0) + 1
    USO.parent.mkdir(exist_ok=True)
    USO.write_text(json.dumps(uso), encoding="utf-8")


def resumen_hoy() -> dict:
    return {k: v for k, v in _hoy().items() if k != "fecha"}


def orden(uso: str) -> list[str]:
    """Proveedores a probar: el elegido por el usuario primero (si eligió uno) y luego del más barato al más caro. Uno
    que dijo «sin saldo» hace poco (claves.recordar) va el último: con 0 saldo cada imagen esperaba su 402. Tu nube
    Modal con su token malo, también: como si no estuviera (ni va delante ni quita el Space)."""
    conectados = set(claves.cargar()) | SIEMPRE
    elegido = claves.ajustes().get(uso, "auto")
    lista = [p for p in ORDEN[uso] if p in conectados]

    def malo(p):
        return bool(claves._vigente(p, claves.BLOQUEA if p == "modal" else {"sin_saldo"}))
    if elegido == claves.GRATIS.get(uso) == "pollinations":
        # Eligió «Pollinations (gratis)»: solo opciones gratis y nunca una de pago, aunque fallen todas.
        # Hugging Face también es gratis; Pollinations sin clave va al final por su baja calidad.
        lista = [p for p in ("pollinations", "cloudflare", "huggingface", "gratis_sin_clave") if p in lista]
    else:
        # De pago con una clave que muchos conectan por otra cosa: solo si el usuario lo eligió (claves.SOLO_ELIGIENDO)
        lista = [p for p in lista if p not in claves.SOLO_ELIGIENDO.get(uso, []) or p == elegido]
        if uso == "video" and elegido in claves.SOLO_ELIGIENDO["video"] and elegido in lista:
            return [elegido]  # video de pago (Kling, Seedance): sin respaldo, que un fallo nunca se pague dos veces
        if uso == "video" and (elegido in ("modal", "pollinations", "ninguno") or
                               (elegido != "huggingface" and "modal" in lista and not malo("modal"))):
            # Con tu nube Modal (o eligiendo Pollinations), tus fotos nunca se suben por detrás a un Space público de
            # terceros ni esperan su cola de 5 minutos por escena: el Space es solo para quien no tiene otra. Con «No
            # usar» solo se llega aquí al animar una foto suelta (ia.video_desde_imagen, forzar): tampoco al Space
            lista = [p for p in lista if p != "huggingface"]
        lista = ([elegido] + [p for p in lista if p != elegido]) if elegido in lista else lista
    return sorted(lista, key=malo)


CUOTA_DIARIA = {"cloudflare", "huggingface"}  # su 429 es la cuota gratis del día; en los demás, saldo o límite por minuto


def _causa(e: Exception, proveedor: str) -> str:
    """Por qué falló un proveedor, dicho para el usuario: sin direcciones ni el ID de la cuenta (la URL de Cloudflare
    lo lleva dentro y el mensaje acaba en pantalla y en los avisos guardados)."""
    causa = str(e).strip() or type(e).__name__  # algunos errores no traen mensaje
    if isinstance(e, httpx.HTTPStatusError):  # el código y lo que dice el servicio (p. ej. qué campo no acepta)
        from .ia import motivo  # su «message», no el JSON entero: aquí, ia también carga este módulo
        causa = f"{e.response.status_code} {e.response.reason_phrase} — {motivo(e.response)}"
    elif isinstance(e, httpx.TransportError):  # «[Errno 11001] getaddrinfo failed», en inglés: dicho en claro
        from .idioma import texto_de_error
        causa = texto_de_error(e)
    if re.search(r"\b429\b|quota|neurons", causa, re.IGNORECASE):
        return t("se acabó la cuota gratis de hoy") if proveedor in CUOTA_DIARIA else \
            t("límite de uso alcanzado: espera un poco o revisa tu saldo")
    from . import kling, seedance  # sus consolas son fijas: el usuario las necesita para recargar o sacar la clave
    fijas = (kling.CONSOLA, seedance.CONSOLA)
    return re.sub(r"https?://\S+|\b[0-9a-fA-F]{32}\b", lambda m: m[0] if m[0].startswith(fijas) else "…", causa)


def _apuntar(uso: str, proveedor: str, que_fue, error=None, paso_a: str = "", cobrado: bool = False) -> None:
    """Un intento de la rotación en la actividad de la IA. Lo que no se cobró (falló) cuesta 0; lo cobrado sin llegar
    (Cobrado), lo de siempre. Lo de este PC no es un servicio de IA: no se apunta. Un avatar es un video."""
    if proveedor == "pc" or uso not in ("imagen", "video", "avatar"):
        return
    try:
        modelo, costo = que_fue(proveedor)
    except Exception:  # el modelo y el precio son informativos: nunca tumban la rotación
        modelo, costo = "", 0.0
    actividad.anotar("video" if uso == "avatar" else uso, proveedor, modelo, costo if error is None or cobrado else 0.0,
                     error, paso_a)


def rotar(uso: str, tareas: dict[str, Callable[[], object]], aviso: Callable[[str, float], None] = lambda t, f: None,
          progreso: float = 0.0, que_fue: Callable[[str], tuple[str, float]] = lambda p: ("", 0.0)):
    """Ejecuta la primera tarea que funcione siguiendo `orden(uso)`. Devuelve (resultado, proveedor).
    Cada intento queda en la actividad de la IA: el que no pudo, con su motivo y la opción que se probó después; el
    que sí, con su modelo y lo que cuesta (que_fue(proveedor) → (modelo, US$ como mucho)). Lo de este PC no se apunta."""
    errores = []
    cola = [p for p in orden(uso) if p in tareas]
    for i, proveedor in enumerate(cola):
        siguiente = cola[i + 1] if i + 1 < len(cola) else ""
        try:
            resultado = tareas[proveedor]()
        except Exception as e:  # cuota agotada, servicio caído…: se pasa al siguiente
            from .ia import Cobrado
            if isinstance(e, Cobrado):  # ya se pagó: sigue hacia arriba para la nota de gasto, sin probar otra opción
                _apuntar(uso, proveedor, que_fue, e, cobrado=True)
                raise
            causa = _causa(e, proveedor)
            if proveedor in claves.USOS and re.search(r"\b402\b|insufficient[_ ]balance", f"{e} {causa}", re.I):
                claves.recordar(proveedor, 402, causa)  # sin saldo: la próxima imagen ya no lo espera (orden)
            _apuntar(uso, proveedor, que_fue, causa, paso_a=siguiente)
            errores.append(f"{NOMBRES.get(proveedor, proveedor)}: {causa if len(causa) <= 400 else causa[:150] + ' … ' + causa[-240:]}")
            aviso(t("{proveedor} no pudo; pruebo la siguiente opción…", proveedor=NOMBRES.get(proveedor, proveedor)),
                  progreso)
            continue
        _apuntar(uso, proveedor, que_fue)
        try:
            contar(proveedor)
        except Exception:  # el contador es informativo: nunca debe tirar un resultado ya hecho (y pagado)
            pass
        return resultado, proveedor
    raise RuntimeError(t("Ninguna opción pudo hacerlo.") + "\n"
                       + "\n".join(errores or [t("No hay ninguna conectada.")]))


# ---------- Separación de voz y pista ----------

MODELOS = Path(__file__).resolve().parent.parent / "datos" / "modelos"  # cachés propias, no las de ~/.cache
# El modelo «htdemucs» de Meta con su huella SHA-256 entera: Demucs lo abre con pickle (ejecuta código) y por su
# cuenta solo comprueba 8 cifras, y solo al bajarlo.
DEMUCS = ("https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th",
          "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4")


def _modelo_demucs() -> None:
    """Deja el modelo en la caché de la app, comprobado entero antes de CADA uso (un archivo cambiado no se abre)."""
    url, huella = DEMUCS
    archivo = MODELOS / "torch" / "hub" / "checkpoints" / url.rsplit("/", 1)[1]  # donde lo busca torch.hub
    datos = archivo.read_bytes() if archivo.is_file() else seguro.descargar(url, tope=200 * 1024 ** 2, plazo=900)
    if hashlib.sha256(datos).hexdigest() != huella:
        archivo.unlink(missing_ok=True)
        raise RuntimeError(t("el modelo para separar voz y pista no es el original (se borró): vuelve a intentarlo"))
    if not archivo.is_file():
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(datos)


def _separar_pc(cancion: Path, carpeta: Path) -> dict:
    """Demucs (de Meta, open source) en este PC. Gratis; en un portátil sin GPU tarda varios minutos."""
    salida = carpeta / "demucs"
    from .cabina import a_wav
    cancion = a_wav(cancion, carpeta / f"{cancion.stem}_para_separar.wav")  # Demucs no lee m4a/ogg: siempre WAV
    _modelo_demucs()
    # -P: no cargar módulos de la carpeta de trabajo. Cachés de la app (TORCH_HOME, HF_HUB_CACHE vacía) y sin red de
    # Hugging Face: Demucs usa el modelo que se acaba de comprobar, nunca uno que otro programa dejó en ~/.cache.
    r = subprocess.run([sys.executable, "-P", "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", str(salida),
                        str(cancion)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "HF_HUB_OFFLINE": "1", "TORCH_HOME": str(MODELOS / "torch"),
                            "HF_HUB_CACHE": str(MODELOS / "hf")},
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-400:])  # el final es donde está la causa real
    base = salida / "htdemucs" / cancion.stem
    return {"voz": base / "vocals.wav", "pista": base / "no_vocals.wav"}


def separar(cancion: Path, carpeta: Path, aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    aviso(t("Separando voz y pista en tu PC…"), 0.1)
    partes, proveedor = rotar("separacion", {"pc": lambda: _separar_pc(cancion, carpeta)}, aviso, 0.1)
    return {**partes, "donde": t("Separado con {proveedor}", proveedor=NOMBRES.get(proveedor, proveedor))}
