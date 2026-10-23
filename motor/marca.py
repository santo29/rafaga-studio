"""La marca del usuario (nombre, eslogan, logo, colores, fuentes y tono) para el estudio de diseño y la IA diseñadora.
Se guarda en datos/marca.json; el logo, copiado en datos/marca/."""
import json
import shutil
import uuid
from pathlib import Path

from . import diseno, seguro
from .idioma import t

ARCHIVO = Path(__file__).resolve().parent.parent / "datos" / "marca.json"
CARPETA_LOGO = ARCHIVO.parent / "marca"
POR_DEFECTO = {"nombre": "", "eslogan": "", "logo": "", "colores": [], "fuente_titulo": "Montserrat",
               "fuente_texto": "Poppins", "tono": ""}


def _campo(campo: str, valor):
    """El valor limpio, o ValueError si no vale."""
    if campo == "logo":
        return "" if valor == "" else diseno.nombre_imagen(valor)
    if campo == "colores":
        if not isinstance(valor, list) or len(valor) > 8:
            raise ValueError(t("tiene que ser una lista de hasta 8 colores #RRGGBB"))
        return [diseno.color(c) for c in valor]
    if campo in ("fuente_titulo", "fuente_texto"):  # «+ Texto» y la IA la copian a las capas
        return diseno.nombre_fuente(valor)
    maximo = {"nombre": 120, "eslogan": 300, "tono": 500}.get(campo, 100)
    if not isinstance(valor, str) or len(valor) > maximo:
        raise ValueError(t("tiene que ser un texto de hasta {maximo} caracteres", maximo=maximo))
    return valor


def cargar() -> dict:
    """La marca guardada; lo que falte o no valga (archivo dañado o tocado a mano) toma su valor por defecto."""
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        datos = {}
    marca = {**POR_DEFECTO, "colores": []}
    for campo in POR_DEFECTO:
        try:
            marca[campo] = _campo(campo, datos[campo])
        except (KeyError, TypeError, ValueError):  # TypeError: el archivo no trae un objeto JSON
            pass
    return marca


def guardar(marca: dict) -> None:
    """Valida y escribe de forma atómica. ValueError en español si algo no vale."""
    if not isinstance(marca, dict):
        raise ValueError(t("La marca no es válida."))
    limpia = {}
    for campo, defecto in POR_DEFECTO.items():
        try:
            limpia[campo] = _campo(campo, marca.get(campo, defecto))
        except ValueError as e:
            raise ValueError(t("Marca, «{campo}»: {error}.", campo=campo, error=e)) from None
    diseno.escribir_json(ARCHIVO, limpia)


def poner_logo(ruta: str) -> str:
    """Copia el logo (local y de verdad una imagen) a datos/marca/ y devuelve su nombre, para marca["logo"]."""
    origen = seguro.archivo_medio(ruta, seguro.IMAGENES, t("logo"))
    CARPETA_LOGO.mkdir(parents=True, exist_ok=True)
    nombre = f"logo-{uuid.uuid4().hex[:8]}{origen.suffix.lower()}"
    shutil.copyfile(origen, CARPETA_LOGO / nombre)
    return nombre


def ruta_logo() -> Path | None:
    logo = cargar()["logo"]
    return CARPETA_LOGO / logo if logo and (CARPETA_LOGO / logo).is_file() else None
