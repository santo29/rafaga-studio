"""Genera requirements.lock (y requirements-torch.lock) con lo instalado en .venv y el hash de cada archivo.

Con hashes, pip solo instala los archivos exactos que se probaron: si alguien sube a PyPI otro archivo para la misma
versión, o el índice de PyTorch sirviera otro, la instalación se para en vez de instalarlo. Además:
- solo entra lo que de verdad necesita requirements.txt (herramientas como pip-audit se quedan fuera);
- se niega a fijar versiones de prueba (rc, beta, dev) o retiradas de PyPI;
- se niega a fijar versiones subidas hace menos de 7 días (si una sale maliciosa, da tiempo a que la retiren),
  salvo con --aceptar-recientes (p. ej. por un arreglo de seguridad urgente); entonces lo apunta en el lock.

Uso, tras probar una actualización:  .venv\\Scripts\\python actualizar_lock.py [--aceptar-recientes]
"""
import datetime as dt
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import httpx
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

RAIZ = Path(__file__).resolve().parent
PYTORCH = "https://download.pytorch.org/whl/cpu"
ESPERA = dt.timedelta(days=7)
CABECERA = """# Versiones exactas ya probadas, con el hash de cada archivo (las instala «Ráfaga Studio.bat» con --require-hashes):
# una versión o un archivo nuevo malicioso de una librería no entra solo. yt-dlp se actualiza luego en segundo plano
# (YouTube cambia a menudo), solo con versiones de hace 7 días o más. Regenerar: ver actualizar_lock.py.
"""


def necesarios() -> set[str]:
    """requirements.txt y todo lo que eso necesita, según lo instalado (con sus marcadores y extras)."""
    pendientes = [Requirement(linea) for linea in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
                  if linea.strip() and not linea.strip().startswith("#")]
    vistos = {"pip"}  # pip va fijado: la actualización de yt-dlp usa --uploaded-prior-to (pip 26+)
    while pendientes:
        req = pendientes.pop()
        nombre = canonicalize_name(req.name)
        if nombre in vistos:
            continue
        vistos.add(nombre)
        try:
            dependencias = distribution(req.name).requires or []
        except PackageNotFoundError:
            raise SystemExit(f"{req.name} está en requirements.txt pero no instalado en .venv.")
        for texto in dependencias:
            dep = Requirement(texto)
            if dep.marker is None or any(dep.marker.evaluate({"extra": e}) for e in (req.extras or {""})):
                pendientes.append(dep)
    return vistos


def instalados() -> list[tuple[str, str]]:
    congelado = subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"], capture_output=True, text=True,
                               check=True).stdout
    fijados = []
    for linea in congelado.splitlines():
        hallado = re.fullmatch(r"([A-Za-z0-9_.\-]+)==(\S+)", linea.strip())
        if not hallado:  # «paquete @ file:///…», «-e …»: algo instalado a mano que no se puede fijar con hash
            raise SystemExit(f"No se puede fijar esta línea de pip freeze: {linea}")
        fijados.append(hallado.groups())
    return fijados


def archivos_pypi(nombre: str, version: str) -> list[dict]:
    r = httpx.get(f"https://pypi.org/pypi/{nombre}/{version}/json", timeout=60)
    r.raise_for_status()
    return r.json()["urls"]


def hashes_pytorch(nombre: str, version: str) -> list[str]:
    r = httpx.get(f"{PYTORCH}/{nombre}/", timeout=60)
    r.raise_for_status()
    archivo = re.escape(f"{nombre}-{version.replace('+', '%2B')}-")
    return sorted(set(re.findall(rf'href="[^"]*/{archivo}[^"#]*#sha256=([0-9a-f]{{64}})"', r.text)))


def revisar(paquete: tuple[str, str]) -> tuple[str, str, list[str], list[str], bool]:
    """(nombre, versión, hashes, problemas que impiden fijarla, subida hace menos de 7 días)."""
    nombre, version = paquete
    publica = version.split("+")[0]  # torch 2.14.1+cpu: la fecha y si está retirada se miran en PyPI (2.14.1)
    archivos = archivos_pypi(nombre, publica)
    problemas = []
    if Version(version).is_prerelease:
        problemas.append("es una versión de prueba")
    if any(a.get("yanked") for a in archivos):
        problemas.append("está retirada de PyPI")
    subida = min((dt.datetime.fromisoformat(a["upload_time_iso_8601"].replace("Z", "+00:00")) for a in archivos),
                 default=None)
    reciente = subida is None or dt.datetime.now(dt.timezone.utc) - subida < ESPERA
    hashes = hashes_pytorch(nombre, version) if "+" in version else sorted({a["digests"]["sha256"] for a in archivos})
    if not hashes:
        problemas.append("no tiene archivos publicados")
    return nombre, version, hashes, problemas, reciente


def bloque(nombre: str, version: str, hashes: list[str]) -> str:
    return f"{nombre}=={version} \\\n" + " \\\n".join(f"    --hash=sha256:{h}" for h in hashes) + "\n"


def main() -> None:
    aceptar_recientes = "--aceptar-recientes" in sys.argv
    validos = necesarios()
    todos = instalados()
    fuera = [n for n, _ in todos if canonicalize_name(n) not in validos]
    if fuera:
        print("Fuera del lock (la app no los necesita):", ", ".join(fuera))
    with ThreadPoolExecutor(16) as hilos:
        revisados = list(hilos.map(revisar, [p for p in todos if canonicalize_name(p[0]) in validos]))
    malos = [f"{n}=={v}: {', '.join(p)}" for n, v, _, p, _ in revisados if p]
    recientes = [f"{n}=={v}" for n, v, _, _, r in revisados if r]
    if recientes and not aceptar_recientes:
        malos.append("subidas hace menos de 7 días (o usa --aceptar-recientes): " + ", ".join(recientes))
    if malos:
        raise SystemExit("No se generó el lock:\n- " + "\n- ".join(malos))
    nota = ""
    if recientes:
        fecha = (dt.date.today() + ESPERA).isoformat()
        nota = (f"# OJO: aceptadas con menos de 7 días (vuelve a generar el lock sin --aceptar-recientes desde el {fecha}"
                f"):\n#   {', '.join(recientes)}\n")
    torch = [bloque(n, v, h) for n, v, h, _, _ in revisados if "+" in v]
    # torch también va en el lock principal: la 2.ª instalación del .bat lo ve ya instalado y no lo baja
    (RAIZ / "requirements.lock").write_text(CABECERA + nota + "".join(bloque(n, v, h) for n, v, h, _, _ in revisados),
                                           encoding="utf-8", newline="\n")
    (RAIZ / "requirements-torch.lock").write_text(
        "# torch y torchaudio sin GPU, del índice oficial de PyTorch (ver actualizar_lock.py).\n" + "".join(torch),
        encoding="utf-8", newline="\n")
    print(f"{len(revisados)} paquetes con hash ({sum(len(h) for _, _, h, _, _ in revisados)} archivos).")


if __name__ == "__main__":
    main()
