"""Rotación de nubes: cada tarea prueba primero lo gratis (cuota diaria, este PC), luego el crédito de Modal y por
último lo de pago. Así el crédito gratis dura y siempre hay al menos unas creaciones al día."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import httpx

from . import claves, seguro
from .idioma import t

USO = Path(__file__).resolve().parent.parent / "datos" / "uso_nubes.json"

# Del más barato al más caro. "pc" = este ordenador (gratis, más lento).
ORDEN = {
    "imagen": ["cloudflare", "pollinations", "huggingface", "replicate", "openai", "gratis_sin_clave"],
    "video": ["huggingface", "modal", "pollinations"],
    # Privacidad: tus canciones y tu voz no salen de tu PC (Demucs local; ver _separar_pc).
    "separacion": ["pc"],
}
NOMBRES = {"huggingface": t("Hugging Face (cuota gratis)"), "modal": t("tu nube Modal"), "pollinations": "Pollinations",
           "pc": t("este PC"), "cloudflare": t("Cloudflare (gratis diario)"), "openai": "OpenAI",
           "replicate": "Replicate", "gratis_sin_clave": t("Pollinations sin clave")}
# Opciones que funcionan sin clave. Los Spaces de Hugging Face se usan sin token (cuota anónima: ~2 min de GPU al día).
SIEMPRE = {"pc", "gratis_sin_clave", "huggingface"}
ESPERA_HF = 300  # segundos máximos en la cola gratis antes de pasar a la siguiente opción
TOPE_SPACE = 300 * 1024 ** 2  # lo más que se baja de un Space (un clip de 5 s pesa unos pocos MB)


def token_hf() -> str | None:
    return (claves.cargar().get("huggingface") or {}).get("clave")


def llamar_space(espacio: str, *entradas, api_name: str, **parametros):
    """Llama a un Space de Hugging Face con o sin token; si la cola gratis tarda demasiado, se rinde."""
    from gradio_client import Client
    from huggingface_hub import get_space_runtime

    def estado():
        return str(get_space_runtime(espacio, token=token_hf()).stage)
    # Construyéndose: Client() esperaría sin límite. Roto o pausado: no va a responder. En los dos casos se pasa a la
    # siguiente opción. Dormido o arrancando: Client() no espera (5 s y se rinde), así que se despierta visitando su
    # página y se espera aquí, con el mismo límite que la cola.
    # ponytail: probado solo con Spaces encendidos; si uno dormido no despierta así, se agota la espera y pasa al siguiente.
    no_sirve = ("BUILDING", "NO_APP_FILE", "CONFIG_ERROR", "BUILD_ERROR", "RUNTIME_ERROR", "PAUSED")
    actual, limite_espera, despertado = estado(), time.time() + ESPERA_HF, False
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
    cliente = Client(espacio, token=False, verbose=False, download_files=False)
    trabajo = cliente.submit(*entradas, api_name=api_name, **parametros)
    try:
        resultado = trabajo.result(timeout=ESPERA_HF)
    except TimeoutError:
        trabajo.cancel()
        raise RuntimeError(t("la cola gratis de Hugging Face tardó más de {minutos} min", minutos=ESPERA_HF // 60))
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
    """Proveedores a probar: el elegido por el usuario primero (si eligió uno) y luego del más barato al más caro."""
    conectados = set(claves.cargar()) | SIEMPRE
    elegido = claves.ajustes().get(uso, "auto")
    lista = [p for p in ORDEN[uso] if p in conectados]
    if elegido == claves.GRATIS.get(uso) == "pollinations":
        # Eligió «Pollinations (gratis)»: solo opciones gratis y nunca una de pago, aunque fallen todas.
        # Hugging Face (con token) también es gratis; Pollinations sin clave va al final por su baja calidad.
        return [p for p in ("pollinations", "cloudflare", "huggingface", "gratis_sin_clave") if p in lista]
    if uso == "video" and elegido in ("modal", "pollinations"):
        # Eligió dónde animar sus fotos: si esa nube falla, nunca se suben por detrás a un Space público de terceros.
        lista = [p for p in lista if p != "huggingface"]
    return ([elegido] + [p for p in lista if p != elegido]) if elegido in lista else lista


def _causa(e: Exception) -> str:
    """Por qué falló un proveedor, dicho para el usuario: sin direcciones ni el ID de la cuenta (la URL de Cloudflare
    lo lleva dentro y el mensaje acaba en pantalla y en los avisos guardados)."""
    causa = str(e).strip() or type(e).__name__  # algunos errores no traen mensaje
    if isinstance(e, httpx.HTTPStatusError):  # el código y lo que dice el servicio (p. ej. qué campo no acepta)
        causa = (f"{e.response.status_code} {e.response.reason_phrase} — "
                 f"{' '.join(e.response.text.split())[:200]}")
    if re.search(r"\b429\b|quota|neurons", causa, re.IGNORECASE):
        return t("se acabó la cuota gratis de hoy")
    return re.sub(r"https?://\S+|\b[0-9a-fA-F]{32}\b", "…", causa)


def rotar(uso: str, tareas: dict[str, Callable[[], object]], aviso: Callable[[str, float], None] = lambda t, f: None,
          progreso: float = 0.0):
    """Ejecuta la primera tarea que funcione siguiendo `orden(uso)`. Devuelve (resultado, proveedor)."""
    errores = []
    for proveedor in orden(uso):
        if proveedor not in tareas:
            continue
        try:
            resultado = tareas[proveedor]()
        except Exception as e:  # cuota agotada, servicio caído…: se pasa al siguiente
            causa = _causa(e)
            errores.append(f"{NOMBRES.get(proveedor, proveedor)}: {causa if len(causa) <= 400 else causa[:150] + ' … ' + causa[-240:]}")
            aviso(t("{proveedor} no pudo; pruebo la siguiente opción…", proveedor=NOMBRES.get(proveedor, proveedor)),
                  progreso)
            continue
        try:
            contar(proveedor)
        except Exception:  # el contador es informativo: nunca debe tirar un resultado ya hecho (y pagado)
            pass
        return resultado, proveedor
    raise RuntimeError(t("Ninguna opción pudo hacerlo.") + "\n"
                       + "\n".join(errores or [t("No hay ninguna conectada.")]))


# ---------- Separación de voz y pista ----------

def _separar_pc(cancion: Path, carpeta: Path) -> dict:
    """Demucs (de Meta, open source) en este PC. Gratis; en un portátil sin GPU tarda varios minutos."""
    salida = carpeta / "demucs"
    from .cabina import a_wav
    cancion = a_wav(cancion, carpeta / f"{cancion.stem}_para_separar.wav")  # Demucs no lee m4a/ogg: siempre WAV
    # -P: no cargar módulos de la carpeta de trabajo. HF_HUB_OFFLINE: usar el modelo ya descargado y verificado; si
    # no está, Demucs lo baja de su repositorio oficial con suma de control en lugar de la rama «main» sin fijar.
    r = subprocess.run([sys.executable, "-P", "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", str(salida),
                        str(cancion)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "HF_HUB_OFFLINE": "1"}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-400:])  # el final es donde está la causa real
    base = salida / "htdemucs" / cancion.stem
    return {"voz": base / "vocals.wav", "pista": base / "no_vocals.wav"}


def separar(cancion: Path, carpeta: Path, aviso: Callable[[str, float], None] = lambda t, f: None) -> dict:
    aviso(t("Separando voz y pista en tu PC…"), 0.1)
    partes, proveedor = rotar("separacion", {"pc": lambda: _separar_pc(cancion, carpeta)}, aviso, 0.1)
    return {**partes, "donde": t("Separado con {proveedor}", proveedor=NOMBRES.get(proveedor, proveedor))}
