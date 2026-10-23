"""Idioma de la app. Los textos se escriben en español en el código y t() los traduce con idiomas/<código>.json (si
falta una traducción, queda en español). El idioma se fija al arrancar: cambiarlo pide reiniciar.

En «Automático» se decide así (y se guarda, para no volver a preguntar a internet):
1. El idioma del PC, si la app lo tiene y no es inglés (un PC en español o portugués es una elección de la persona).
2. Si no, el del país (por la IP): muchos PC de Latinoamérica vienen en inglés de fábrica.
3. Si no, el del PC si lo tenemos; y si no, inglés.
"""
import json
import locale
import os
import re
import sys
import tempfile
from functools import cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "idiomas"
AJUSTE = RAIZ / "datos" / "idioma.json"
IDIOMAS = {"es": "Español", "en": "English", "pt": "Português", "fr": "Français"}
_PAISES = {
    "es": "AR BO CL CO CR CU DO EC ES GQ GT HN MX NI PA PE PR PY SV UY VE",
    "pt": "AO BR CV GW MZ PT ST TL",
    "fr": "BE BF BI BJ CD CF CG CI CM DJ FR GA GN HT LU MC MG ML NC NE PF RE RW SN TD TG",
    "en": "AG AU BB BS BZ CA GB GD GH GY IE JM KE LR NG NZ SG TT UG US ZA ZM ZW",
}
PAISES = {pais: codigo for codigo, lista in _PAISES.items() for pais in lista.split()}
_WINDOWS = {0x0A: "es", 0x09: "en", 0x16: "pt", 0x0C: "fr"}  # idioma principal de GetUserDefaultUILanguage


def _leer() -> dict:
    try:
        datos = json.loads(AJUSTE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _escribir(datos: dict) -> None:
    AJUSTE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=AJUSTE.parent, prefix=".idioma-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(tmp, AJUSTE)


def elegido() -> str:
    """Lo que eligió el usuario: «auto» o un código de IDIOMAS."""
    valor = _leer().get("elegido", "auto")
    return valor if valor in IDIOMAS else "auto"


def elegir(codigo: str) -> None:
    if codigo != "auto" and codigo not in IDIOMAS:
        raise ValueError(t("Idioma desconocido: {codigo!r:.20}", codigo=codigo))
    _escribir({**_leer(), "elegido": codigo})


def del_sistema() -> str | None:
    """El idioma de la interfaz del PC (Windows: el de los menús, no el formato de fechas)."""
    if sys.platform == "win32":
        import ctypes
        return _WINDOWS.get(ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF)
    nombre = (locale.getlocale()[0] or os.environ.get("LANG") or "")[:2].lower()
    return nombre if nombre in IDIOMAS else None


def del_pais() -> str | None:
    """El idioma principal del país desde el que se conecta (una consulta corta a Cloudflare; None si no hay red)."""
    import httpx
    try:
        r = httpx.get("https://www.cloudflare.com/cdn-cgi/trace", timeout=2.5)
        pais = re.search(r"^loc=([A-Z]{2})$", r.text, re.MULTILINE)
    except httpx.HTTPError:
        return None
    return PAISES.get(pais.group(1)) if pais else None


def detectar(sistema: str | None, pais) -> str:
    """La regla del docstring del módulo. `pais` es una función: solo se pregunta a internet si hace falta."""
    if sistema and sistema != "en":
        return sistema
    return pais() or sistema or "en"


@cache
def actual() -> str:
    """El idioma de esta sesión. RAFAGA_IDIOMA lo fuerza (las pruebas usan español)."""
    forzado = os.environ.get("RAFAGA_IDIOMA")
    if forzado in IDIOMAS:
        return forzado
    datos = _leer()
    if datos.get("elegido") in IDIOMAS:
        return datos["elegido"]
    if datos.get("detectado") in IDIOMAS:
        return datos["detectado"]
    pais = []  # si internet no responde, se usa lo del PC esta vez y se vuelve a intentar al arrancar otra vez
    codigo = detectar(del_sistema(), lambda: pais.append(del_pais()) or pais[0])
    if not pais or pais[0]:
        try:
            _escribir({**datos, "detectado": codigo})
        except OSError:
            pass
    return codigo


@cache
def _textos(codigo: str) -> dict[str, str]:
    if codigo == "es":
        return {}
    try:
        datos = json.loads((CARPETA / f"{codigo}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in datos.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(datos, dict) else {}


def t(texto: str, /, **datos) -> str:
    """El texto en el idioma de la sesión. Con datos, rellena sus {huecos}: t("Hoy: {n} clips", n=3).
    `texto` va solo por posición: así un hueco también puede llamarse {texto}."""
    traducido = _textos(actual()).get(texto, texto)
    return traducido.format(**datos) if datos else traducido
