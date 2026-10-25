"""Memoria del estudio: las preferencias duraderas del usuario por departamento («títulos cortos», «sin Montserrat»,
«mi marca es X»). Se guardan en datos/memoria.json, en este PC, y cada especialista añade las suyas a lo que le pide
a su IA (para()). Nunca datos sensibles: claves, contraseñas ni tarjetas se rechazan aquí, no en la IA."""
import json
import re
from pathlib import Path

from . import claves, guardia, roles
from .idioma import t

ARCHIVO = Path(__file__).resolve().parent.parent / "datos" / "memoria.json"
MAX_POR_DEPARTAMENTO, MAX_LARGO = 8, 120  # va en cada paso del Director y en cada pedido a la IA: corta
_SENSIBLE = re.compile(
    r"contrase[ñn]a|password|passwd|\bpass\b|\b(?:mi|la|tu|su) contra\b|senha|mot de passe|\bpin\b(?!-)|\bcvv\b|"
    r"\bcvc\b|c[oó]digo de seguridad|tarjeta de (?:cr[eé]dito|d[eé]bito)|credit card|debit card|card number|"
    r"cart[ãa]o de cr[eé]dito|carte bancaire|api[ _-]?key|\btoken|\bsecret|"
    r"\bmi clave\b|\bclaves? (?:de|del|api|secreta)\b|\biban\b|cuenta bancaria|n[uú]mero de cuenta|seguro social",
    re.IGNORECASE)
# 13 a 19 cifras seguidas, con espacios, puntos o guiones: tarjeta o cuenta (un teléfono tiene menos). Cuatro años
# seguidos (2023 2024 2025 2026) no son una tarjeta: ninguna empieza por 19 ni por 20
_TARJETA = re.compile(r"(?<!\d)(?!(?:(?:19|20)\d\d[ .,-]*){4})(?:\d[ .-]?){13,19}")
_TOKEN = re.compile(r"(?<![#\w-])(?=[\w-]*\d)(?=[\w-]*[A-Za-z])[\w-]{20,}")  # letras y cifras, largo: clave; no #tag


def cargar() -> dict[str, list[str]]:
    """{departamento: [preferencias]}; lo que no valga (archivo dañado o tocado a mano) se ignora."""
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return {}
    validos = {roles.GENERAL, *roles.DEPARTAMENTOS}
    return {d: [p for p in lista if isinstance(p, str)][:MAX_POR_DEPARTAMENTO]
            for d, lista in (datos.items() if isinstance(datos, dict) else []) if d in validos and isinstance(lista, list)}


def sensible(texto: str) -> bool:
    return bool(_SENSIBLE.search(texto) or _TARJETA.search(texto) or _TOKEN.search(texto)
                or any(claves.candidatos(p) for p in texto.split()))


def recordar(departamento: str, preferencia: str) -> dict[str, list[str]]:
    """Guarda una preferencia (ValueError en español si no vale). La más nueva va al final; si se repite, no se
    duplica, y pasado el tope se olvida la más vieja."""
    if not isinstance(departamento, str) or departamento not in {roles.GENERAL, *roles.DEPARTAMENTOS}:
        raise ValueError(t("Departamento desconocido ({departamento!r:.30}); valen {departamentos}.",
                           departamento=departamento,
                           departamentos=", ".join([roles.GENERAL, *roles.DEPARTAMENTOS])))
    preferencia = " ".join(str(preferencia or "").split())
    if not preferencia or len(preferencia) > MAX_LARGO:
        raise ValueError(t("La preferencia tiene que ser un texto de 1 a {maximo} caracteres.", maximo=MAX_LARGO))
    if sensible(preferencia):
        guardia.registrar("memoria", "media", t("La memoria del estudio no guardó un dato sensible (una clave, una "
                                                "contraseña o una tarjeta)."))
        raise ValueError(t("No guardo claves, contraseñas, tarjetas ni números de cuenta en la memoria del estudio."))
    memoria = cargar()
    lista = [p for p in memoria.get(departamento, []) if p.lower() != preferencia.lower()] + [preferencia]
    memoria[departamento] = lista[-MAX_POR_DEPARTAMENTO:]
    _guardar(memoria)
    return memoria


def olvidar(departamento: str, preferencia: str) -> None:
    memoria = cargar()
    memoria[departamento] = [p for p in memoria.get(departamento, []) if p != preferencia]
    _guardar({d: lista for d, lista in memoria.items() if lista})


def _guardar(memoria: dict) -> None:
    from . import diseno  # aquí: diseno carga Qt, y los especialistas que solo leen la memoria no lo necesitan
    diseno.escribir_json(ARCHIVO, memoria)


def para(departamento: str) -> str:
    """La línea que un especialista añade a lo que manda a su IA: las preferencias de todo el estudio y las de su
    departamento. "" si no hay ninguna."""
    memoria = cargar()
    lista = memoria.get(roles.GENERAL, []) + (memoria.get(departamento, []) if departamento != roles.GENERAL else [])
    return ("\nPreferencias guardadas del usuario (síguelas salvo que este pedido diga otra cosa): "
            + "; ".join(lista) + ".") if lista else ""
