"""Genera el manifiesto de integridad que va con el instalador: dist/integridad.json, con la huella SHA-256 de cada
archivo de código que copia rafaga.iss (app.py, mcp_server.py, modal_app.py, el lanzador .bat y todos los .py de motor
y ui). La app instalada lo compara con su código (motor/guardia.py, revisar_integridad): un archivo cambiado, uno que
falta o un .py de más es un evento «alta» de Ráfaga Guardia y bloquea lo de pago.

rafaga.iss lo ejecuta solo al compilar (así nunca se empaqueta uno viejo); a mano:
    .venv\\Scripts\\python.exe -s -E instalador\\integridad.py

Va en dist/ y no en la raíz: con un manifiesto en la copia de git, cada cambio de quien desarrolla bloquearía su app.
Límite honesto: quien puede reescribir el código instalado también puede reescribir el manifiesto; esto pilla lo que
cambia un programa malicioso (o cualquier otro) que no sabe de él."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from motor import guardia  # noqa: E402  las mismas reglas que usa la app para comprobar


def generar(destino: Path = RAIZ / "dist" / "integridad.json") -> dict:
    archivos = guardia.huellas(RAIZ)
    faltan = [n for n in guardia.RAIZ_CODIGO if n not in archivos]
    if faltan:  # un manifiesto sin el lanzador o sin app.py avisaría en cada instalación
        raise SystemExit(f"Faltan archivos de la app: {', '.join(faltan)}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"version": 1, "archivos": archivos}, indent=1, ensure_ascii=False),
                       encoding="utf-8")
    return archivos


if __name__ == "__main__":
    print(f"dist/integridad.json: {len(generar())} archivos")
