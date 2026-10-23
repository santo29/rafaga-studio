"""Idiomas: la regla de detección, t() y que cada texto marcado con t() esté traducido en todos los idiomas.
Sin red. Se ejecuta solo o desde pruebas.py."""
import ast
import json
import os
import re
import tempfile
from pathlib import Path

from motor import idioma

RAIZ = Path(__file__).resolve().parent

# ---------- Regla de detección (ver motor/idioma.py) ----------
d = idioma.detectar
assert d("es", lambda: "en") == "es"  # un PC en español manda, aunque se conecte desde EE. UU.
assert d("pt", lambda: "es") == "pt"
assert d("en", lambda: "es") == "es"  # PC en inglés de fábrica en República Dominicana: español
assert d("en", lambda: None) == "en"  # sin red: lo del PC
assert d(None, lambda: "fr") == "fr" and d(None, lambda: None) == "en"
preguntas = []
d("es", lambda: preguntas.append(1))
assert preguntas == []  # si el PC ya lo deja claro, no se pregunta a internet
assert idioma.PAISES["DO"] == "es" and idioma.PAISES["BR"] == "pt" and idioma.PAISES["HT"] == "fr"

# ---------- Elegir, recordar y forzar ----------
original = idioma.AJUSTE, os.environ.pop("RAFAGA_IDIOMA", None)
with tempfile.TemporaryDirectory() as carpeta:
    idioma.AJUSTE = Path(carpeta) / "idioma.json"
    assert idioma.elegido() == "auto"
    idioma.elegir("pt")
    assert idioma.elegido() == "pt" and json.loads(idioma.AJUSTE.read_text(encoding="utf-8"))["elegido"] == "pt"
    idioma.actual.cache_clear()
    assert idioma.actual() == "pt"
    for malo in ("de", "../x", None):
        try:
            idioma.elegir(malo)
            raise AssertionError(f"debió rechazar {malo!r}")
        except ValueError:
            pass
    idioma.AJUSTE.write_text("{roto", encoding="utf-8")  # un archivo dañado no rompe la app
    assert idioma.elegido() == "auto"
    os.environ["RAFAGA_IDIOMA"] = "fr"
    idioma.actual.cache_clear()
    assert idioma.actual() == "fr"
idioma.AJUSTE = original[0]
os.environ.pop("RAFAGA_IDIOMA", None)
if original[1]:
    os.environ["RAFAGA_IDIOMA"] = original[1]
idioma.actual.cache_clear()

# ---------- t(): traduce, rellena huecos y, si falta una traducción, deja el español ----------
idioma._textos.cache_clear()
os.environ["RAFAGA_IDIOMA"] = "es"
idioma.actual.cache_clear()
assert idioma.t("Hoy: {n} clips", n=3) == "Hoy: 3 clips" and idioma.t("Texto sin traducir") == "Texto sin traducir"
if original[1] is None:
    os.environ.pop("RAFAGA_IDIOMA")
else:
    os.environ["RAFAGA_IDIOMA"] = original[1]
idioma.actual.cache_clear()


# ---------- Cada texto con t() está en todos los idiomas, con los mismos {huecos} ----------
def textos_marcados() -> dict[str, str]:
    marcados = {}
    for archivo in [RAIZ / "app.py", RAIZ / "mcp_server.py", *(RAIZ / "ui").rglob("*.py"), *(RAIZ / "motor").glob("*.py")]:
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if (isinstance(nodo, ast.Call) and (getattr(nodo.func, "id", None) == "t" or getattr(nodo.func, "attr", None) == "t")
                    and nodo.args and isinstance(nodo.args[0], ast.Constant) and isinstance(nodo.args[0].value, str)):
                marcados[nodo.args[0].value] = f"{archivo.name}:{nodo.lineno}"
    return marcados


def huecos(texto: str) -> set[str]:
    return set(re.findall(r"\{(\w*)[^{}]*\}", texto))


marcados = textos_marcados()
assert len(marcados) > 100, "casi ningún texto está marcado con t()"
for codigo in idioma.IDIOMAS:
    if codigo == "es":
        continue
    traducciones = json.loads((RAIZ / "idiomas" / f"{codigo}.json").read_text(encoding="utf-8"))
    faltan = [f"{donde}: {texto[:50]!r}" for texto, donde in marcados.items() if not traducciones.get(texto)]
    assert not faltan, f"{codigo}: faltan {len(faltan)} traducciones, p. ej. " + "; ".join(faltan[:5])
    mal = [texto[:50] for texto in marcados if huecos(texto) != huecos(traducciones[texto])]
    assert not mal, f"{codigo}: los {{huecos}} no coinciden en: " + "; ".join(mal[:5])

print(f"Pruebas de idiomas pasadas ({len(marcados)} textos en {len(idioma.IDIOMAS)} idiomas).")
