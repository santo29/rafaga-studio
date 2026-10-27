"""Tu nube de video en Modal: instalar el motor, animar imágenes y no pasarse del crédito gratis."""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import claves
from .idioma import t

RAIZ = Path(__file__).resolve().parent.parent
USO = RAIZ / "datos" / "uso_nube.json"
LIMITE_DIARIO = 3  # ~3 clips/día × 30 días × ~$0.30 ≈ los $30 gratis del plan Starter
PRECIO_CLIP = 0.35  # US$ por clip de 5 s del crédito de Modal, por lo alto (lo que dice «Claves de IA»: 0,20 a 0,35)


def limite() -> int:
    return int(claves.ajustes().get("limite_nube_diario", LIMITE_DIARIO))


def usados_hoy() -> int:
    try:
        uso = json.loads(USO.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return 0
    if not isinstance(uso, dict) or uso.get("fecha") != time.strftime("%Y-%m-%d"):
        return 0
    return uso["clips"] if isinstance(uso.get("clips"), int) else 0


_cerrojo_hilos = threading.Lock()


def _cambiar_uso(cambio: int) -> None:
    """Suma o resta clips del día con un cerrojo que vale entre hilos y entre procesos (la app y el MCP pueden
    trabajar a la vez), así nunca se pasa del tope."""
    cerrojo = USO.with_suffix(".lock")
    USO.parent.mkdir(exist_ok=True)
    with _cerrojo_hilos:
        for _ in range(100):
            try:
                fd = os.open(cerrojo, os.O_CREAT | os.O_EXCL)
                break
            except (FileExistsError, PermissionError):  # Windows da PermissionError si otro lo está borrando
                time.sleep(0.1)
        else:  # 10 s esperando: es un cerrojo viejo de un proceso que se cerró a la mitad
            try:
                cerrojo.unlink(missing_ok=True)
                fd = os.open(cerrojo, os.O_CREAT | os.O_EXCL)
            except OSError:  # otro proceso lo tiene de verdad o lo recuperó a la vez: no tocar el cupo
                raise RuntimeError(t("El cupo de Modal está ocupado por otra tarea ahora mismo; inténtalo en un "
                                     "momento."))
        try:
            usados = usados_hoy()
            if cambio > 0 and limite() <= 0:
                raise RuntimeError(t("La nube Modal está apagada (tope de 0 clips al día en «Claves de IA»)."))
            if cambio > 0 and usados >= limite():
                raise RuntimeError(t("Ya se usaron los {n} clips de nube de hoy (para no pasar del crédito gratis).",
                                     n=limite()))
            USO.write_text(json.dumps({"fecha": time.strftime("%Y-%m-%d"), "clips": max(usados + cambio, 0)}),
                           encoding="utf-8")
        finally:
            os.close(fd)
            try:
                cerrojo.unlink(missing_ok=True)
            except OSError:  # p. ej. un antivirus lo tiene abierto: el cupo ya quedó apuntado
                pass


def usar_gpu(objeto_modal, llamada):
    """Comprueba primero el motor y el token (hydrate: sin GPU ni coste) y SOLO entonces aparta el clip del cupo y
    llama. Si la llamada falla ya en marcha cuenta igual: no se puede saber si la GPU llegó a gastar, y el tope
    está para no pasarse nunca del crédito gratis."""
    objeto_modal.hydrate()  # motor sin instalar, token malo o sin red fallan aquí, sin tocar el cupo
    _cambiar_uso(+1)
    return llamada()


def _cliente(clave: str):
    """Un cliente de Modal con el token del usuario, sin ponerlo en os.environ: ahí lo heredaría todo programa que la
    app abre después (ffmpeg, node, el navegador…) y seguiría ahí aunque se quite la clave."""
    import modal
    e = claves.modal_env(clave)
    return modal.Client.from_credentials(e["MODAL_TOKEN_ID"], e["MODAL_TOKEN_SECRET"])


def instalar() -> str:
    """Sube el motor de video (modal_app.py) a la cuenta de Modal del usuario."""
    c = claves.cargar().get("modal")
    if not c:
        raise RuntimeError(t("Primero conecta tu token de Modal en «Claves de IA»."))
    r = subprocess.run([sys.executable, "-m", "modal", "deploy", str(RAIZ / "modal_app.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
                       env=claves.modal_env(c["clave"]), cwd=RAIZ,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise RuntimeError(t("Modal no pudo instalar el motor:\n{detalle}", detalle=(r.stderr or r.stdout)[-1200:]))
    # Los pesos del modelo se bajan ya, con CPU (casi gratis): si no, los bajaría la GPU en el primer clip (pagado)
    import modal
    modal.Function.from_name("rafaga-studio-video", "preparar", client=_cliente(c["clave"])).remote()
    return r.stdout[-600:]


def animar(imagen_png: Path, prompt: str, formato: str, segundos: float, destino: Path) -> Path:
    """Anima una imagen en la nube. Lanza error si ya se usaron los clips del día."""
    c = claves.cargar()["modal"]
    import modal
    imagen = imagen_png.read_bytes()  # si la imagen no existe, falla aquí, antes de apartar cupo
    clase = modal.Cls.from_name("rafaga-studio-video", "Wan", client=_cliente(c["clave"]))
    datos = usar_gpu(clase, lambda: clase().animar.remote(imagen, prompt, formato in ("9:16", "4:5"), segundos))
    destino.write_bytes(datos)
    return destino
