"""Recursos para el estudio de diseño: iconos Lucide (ISC), fuentes de Google Fonts (OFL) y los emojis del sistema.
De dónde sale cada archivo de assets/, con su licencia y su hash: assets/LEEME.md."""
import json
import re
import unicodedata
from functools import cache
from pathlib import Path

from .idioma import t

RAIZ_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_ICONOS = RAIZ_ASSETS / "iconos"
_FUENTES = RAIZ_ASSETS / "fuentes"
FUENTE_EMOJI = ["Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji"]

# Emojis de un solo carácter según emoji-data.txt de Unicode 16 (unicodedata no trae la propiedad «Emoji», y en esos
# bloques también hay símbolos en blanco y negro que no lo son): rangos desde U+1F000, las caritas primero, y los
# sueltos de antes. Los huecos sin asignar los descarta unicodedata.name.
_RANGOS_EMOJI = ("1F600-1F64F 1F300-1F321 1F324-1F393 1F396-1F397 1F399-1F39B 1F39E-1F3F0 1F3F3-1F3F5 1F3F7-1F4FD "
                 "1F4FF-1F53D 1F549-1F54E 1F550-1F567 1F56F-1F570 1F573-1F57A 1F587 1F58A-1F58D 1F590 1F595-1F596 "
                 "1F5A4-1F5A5 1F5A8 1F5B1-1F5B2 1F5BC 1F5C2-1F5C4 1F5D1-1F5D3 1F5DC-1F5DE 1F5E1 1F5E3 1F5E8 1F5EF "
                 "1F5F3 1F5FA-1F5FF 1F680-1F6C5 1F6CB-1F6D2 1F6D5-1F6D7 1F6DC-1F6E5 1F6E9 1F6EB-1F6EC 1F6F0 "
                 "1F6F3-1F6FC 1F7E0-1F7EB 1F7F0 1F90C-1F93A 1F93C-1F945 1F947-1F9FF 1FA70-1FAFF 1F004 1F0CF "
                 "1F170-1F171 1F17E-1F17F 1F18E 1F191-1F19A 1F201-1F202 1F21A 1F22F 1F232-1F23A 1F250-1F251")
_EMOJIS_SUELTOS = ("©®‼⁉™ℹ↔↕↖↗↘↙↩↪⌚⌛⌨⏏⏩⏪⏫⏬⏭⏮⏯⏰⏱⏲⏳⏸⏹⏺Ⓜ▪▫▶◀◻◼◽◾☀☁☂☃☄☎☑☔☕☘☝☠☢☣☦☪☮☯☸☹☺♀♂♈♉♊♋♌♍♎♏♐♑♒♓♟♠♣♥♦♨"
                   "♻♾♿⚒⚓⚔⚕⚖⚗⚙⚛⚜⚠⚡⚧⚪⚫⚰⚱⚽⚾⛄⛅⛈⛎⛏⛑⛓⛔⛩⛪⛰⛱⛲⛳⛴⛵⛷⛸⛹⛺⛽✂✅✈✉✊✋✌✍✏✒✔✖✝✡✨✳✴❄❇❌❎❓❔❕❗❣❤"
                   "➕➖➗➡➰➿⤴⤵⬅⬆⬇⬛⬜⭐⭕〰〽㊗㊙")


@cache
def _nombres() -> frozenset[str]:
    return frozenset(p.stem for p in _ICONOS.glob("*.svg") if re.fullmatch(r"[a-z0-9-]+", p.stem))


def iconos() -> list[str]:
    return sorted(_nombres())


def svg_icono(nombre: str, color: str = "#FFFFFF", grosor: float = 2) -> bytes:
    """El SVG del icono con su color y grosor de trazo. El nombre y el color pueden venir de la IA o de un diseño
    ajeno: se validan antes de tocar el disco (nada de «../», solo iconos que existen)."""
    if not isinstance(nombre, str) or not re.fullmatch(r"[a-z0-9-]+", nombre) or nombre not in _nombres():
        raise ValueError(t("No existe el icono «{nombre}».", nombre=nombre))
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise ValueError(t("Color no válido: {color!r} (tiene que ser #RRGGBB).", color=color))
    if isinstance(grosor, bool) or not isinstance(grosor, (int, float)) or not 0 < grosor <= 10:
        raise ValueError(t("Grosor de trazo no válido: {grosor!r} (de 0 a 10).", grosor=grosor))
    svg = (_ICONOS / f"{nombre}.svg").read_text(encoding="utf-8").replace("currentColor", color)
    return re.sub(r'stroke-width="[^"]*"', f'stroke-width="{grosor:g}"', svg).encode("utf-8")


@cache
def _etiquetas() -> dict:
    try:
        return json.loads((_ICONOS / "etiquetas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def buscar_iconos(texto: str, limite: int = 60) -> list[str]:
    """Primero el nombre exacto, luego los que empiezan así, los que lo contienen y por último por etiquetas."""
    buscado = "-".join(str(texto or "").lower().split())
    if not buscado:
        return iconos()[:limite]
    palabras = buscado.split("-")
    etiquetas = _etiquetas()

    def orden(n: str) -> int:
        if n == buscado:
            return 0
        if n.startswith(buscado):
            return 1
        if all(p in n for p in palabras):
            return 2
        return 3 if all(p in f"{n} {' '.join(etiquetas.get(n, []))}" for p in palabras) else 9
    return [n for o, n in sorted((orden(n), n) for n in _nombres()) if o < 9][:limite]


def archivos_fuentes() -> list[Path]:
    return sorted(p for p in _FUENTES.glob("*") if p.suffix.lower() in (".ttf", ".otf"))


def fuentes() -> list[str]:
    # La familia sale del nombre del archivo de Google Fonts: «PlayfairDisplay-Italic[wght].ttf» → «Playfair Display».
    return sorted({re.sub(r"(?<=[a-z])(?=[A-Z])", " ", re.match(r"[A-Za-z0-9]+", p.stem)[0])
                   for p in archivos_fuentes()})


@cache
def _emojis() -> tuple[tuple[str, str], ...]:
    rangos = [r.partition("-")[::2] for r in _RANGOS_EMOJI.split()]
    caracteres = [chr(c) for a, b in rangos for c in range(int(a, 16), int(b or a, 16) + 1)] + list(_EMOJIS_SUELTOS)
    nombres = ((c, unicodedata.name(c, "").lower()) for c in caracteres)
    # Los tonos de piel y los «componentes» (pelo rojo…) solos son cuadraditos: no sirven en un selector.
    return tuple((c, n) for c, n in nombres if n and not n.startswith(("emoji modifier", "emoji component")))


def emojis() -> list[tuple[str, str]]:
    return list(_emojis())


def buscar_emojis(texto: str, limite: int = 120) -> list[str]:
    palabras = str(texto or "").lower().split()
    hallados = [(c, n) for c, n in _emojis() if all(p in n for p in palabras)]
    # La palabra entera primero: «sun» da antes el sol que el girasol («sunflower»).
    hallados.sort(key=lambda h: not all(p in h[1].split() for p in palabras))
    return [c for c, _ in hallados][:limite]
