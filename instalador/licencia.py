"""Genera dist/licencia.rtf, el texto de la página «Términos de uso» del instalador, desde TERMINOS.md (la única fuente):
títulos de verdad, negritas, viñetas y párrafos enteros. Inno enseñaba el .md como texto plano («## 9.», asteriscos,
`código` y frases cortadas a la mitad por los saltos de línea a mano); con RTF parte las líneas a su ancho.
rafaga.iss lo ejecuta al compilar, igual que integridad.py; a mano:
    .venv\\Scripts\\python.exe -s -E instalador\\licencia.py
Sin tabla de colores: el texto toma el color del asistente, también en modo oscuro (WizardStyle=modern dynamic).
Va en dist/ (no en git), como integridad.json."""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EN_LINEA = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\([^)\s]+\)")
# El instalador no enseña los otros documentos: se dice dónde están (TERMINOS.md los nombra en su primera frase)
AL_FINAL = ("El Aviso de privacidad y los Avisos de terceros se instalan con la app: la app te enseña el aviso al "
            "abrirla por primera vez, y los dos están siempre en «Privacidad y legal».")


def _escapar(texto: str) -> str:
    """Texto plano a RTF: \\ { } escapados y todo lo que no es ASCII como \\uN? (UTF-16, también los emojis)."""
    salida = []
    for c in texto:
        if c in "\\{}":
            salida.append("\\" + c)
        elif ord(c) < 128:
            salida.append(c)
        else:
            u16 = c.encode("utf-16-le")
            for i in range(0, len(u16), 2):
                n = int.from_bytes(u16[i:i + 2], "little")
                salida.append(f"\\u{n - 65536 if n > 32767 else n}?")
    return "".join(salida)


def _en_linea(texto: str) -> str:
    """**negrita** en negrita; `código` y [enlace](destino) se quedan solo con su texto."""
    partes, pos = [], 0
    for m in EN_LINEA.finditer(texto):
        partes.append(_escapar(texto[pos:m.start()]))
        negrita, codigo, enlace = m.groups()
        partes.append("{\\b " + _escapar(negrita) + "}" if negrita else _escapar(codigo or enlace))
        pos = m.end()
    partes.append(_escapar(texto[pos:]))
    return "".join(partes)


def _bloques(md: str):
    """(tipo, texto) por bloque: las líneas cortadas a mano se juntan en un solo párrafo o viñeta."""
    tipo, lineas = None, []
    for linea in md.splitlines() + [""]:
        if linea.lstrip().startswith("|"):  # ponytail: sin tablas; si TERMINOS.md trae una, no compila antes que enseñar «|»
            raise SystemExit("TERMINOS.md tiene una tabla y instalador/licencia.py no las convierte")
        if not linea.strip() or linea.startswith(("#", "- ")) or re.match(r"\d+\. ", linea):
            if lineas:
                yield tipo, " ".join(lineas)
            tipo, lineas = None, []
            if linea.startswith("#"):
                nivel = len(linea) - len(linea.lstrip("#"))
                yield f"h{nivel}", linea[nivel:].strip()
            elif linea.strip():
                tipo, lineas = "li", [re.sub(r"^(- |\d+\. )", "", linea).strip()]
        else:
            tipo, lineas = tipo or "p", lineas + [linea.strip()]


def rtf(md: str) -> str:
    cuerpo = []
    for tipo, texto in [*_bloques(md), ("p", AL_FINAL)]:
        t = _en_linea(texto)
        if tipo == "h1":
            cuerpo.append(f"\\pard\\sa160\\b\\fs30 {t}\\b0\\fs18\\par")
        elif tipo in ("h2", "h3"):
            cuerpo.append(f"\\pard\\sb200\\sa80\\b\\fs21 {t}\\b0\\fs18\\par")
        elif tipo == "li":  # viñeta con sangría colgante: la segunda línea empieza debajo del texto, no del «•»
            cuerpo.append(f"\\pard\\fi-220\\li440\\tx440\\sa80 \\u8226?\\tab {t}\\par")
        else:
            cuerpo.append(f"\\pard\\sa120 {t}\\par")
    return ("{\\rtf1\\ansi\\ansicpg1252\\deff0\\uc1{\\fonttbl{\\f0\\fswiss\\fcharset0 Segoe UI;}}\\f0\\fs18\n"
            + "\n".join(cuerpo) + "\n}\n")


def generar(destino: Path = RAIZ / "dist" / "licencia.rtf") -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(rtf((RAIZ / "TERMINOS.md").read_text(encoding="utf-8")), encoding="ascii")
    return destino


if __name__ == "__main__":
    # Autocomprobación: nada de Markdown crudo en lo que verá el usuario
    prueba = rtf("# T\n\n**Versión 4** · `x/`\n\n- **A** uno\n  dos [B](B.md)\n\n## 9. Cambios\n\nSi alguna parte\nde estos.")
    assert "**" not in prueba and "`" not in prueba and "](" not in prueba and "## " not in prueba, prueba
    assert "Si alguna parte de estos." in prueba and "\\u8226?\\tab {\\b A} uno dos B\\par" in prueba, prueba
    print(generar(Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dist" / "licencia.rtf"))
