"""Actividad de la IA: cada llamada que el estudio hace a un servicio de IA (desde la app y desde el servidor MCP) queda
apuntada en datos/actividad.json: cuándo, desde qué tarea, qué servicio y modelo, qué se pidió (texto, imagen, video,
voz, música o transcripción), lo que cuesta como mucho y cómo salió. Así el dueño ve adónde se va el saldo de cada
servicio (pasó: no sabía en qué se le fueron los US$5 de Gemini).

Nunca se guardan claves, tokens, enlaces firmados ni rutas enteras (guardia.limpiar), y apuntar nunca tumba la llamada
que se apunta: si el disco falla, la IA sigue y solo se pierde esa línea. El costo es una estimación por lo alto con
los precios del propio estudio (ia.PRECIO_*, musica.PRECIO, kling y seedance.estimar): lo exacto lo da la web de cada
servicio."""
import json
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import guardia
from .idioma import dinero, t

ARCHIVO = Path(__file__).resolve().parent.parent / "datos" / "actividad.json"
MAX_LLAMADAS = 600  # las últimas que se guardan con detalle (la página enseña 50)
DIAS, MESES = 62, 24  # los totales de gasto que se guardan: dos meses de días y dos años de meses
ORIGEN = "app"  # mcp_server.py lo cambia a «mcp»: cada proceso firma lo que apunta (como en Ráfaga Guardia)
QUE = ("texto", "imagen", "video", "voz", "musica", "transcripcion")
# El módulo que hizo la llamada → la página de la app donde se pidió (su nombre del menú, sin traducir: se traduce al
# enseñarlo, así cambiar de idioma no deja la actividad vieja en otro)
PAGINAS = {"desde_prompt": "Crear con IA", "crear": "Crear con IA", "anuncios": "Anuncios",
           "serie": "Dibujos animados", "musica": "Música", "video_musical": "Música", "shorts": "Shorts mágicos",
           "nichos": "Nichos virales", "diseno_ia": "Diseño", "diseno": "Diseño", "edicion": "Editor de video",
           "render_edicion": "Editor de video", "cabina": "Cabina de grabación", "guardia": "Ráfaga Guardia",
           "director": "Director IA", "voz": "Director IA", "claves": "Claves de IA", "publicar": "Publicar",
           "inicio": "Inicio"}
_hilos = threading.Lock()  # dentro de un proceso: el cerrojo de archivo es para la app y el MCP a la vez


def _tarea() -> str:
    """La página o la herramienta que pidió la llamada, sacada de quién llamó (sin que cada página tenga que decirlo):
    la de más fuera de motor/ o ui/paginas/. Anuncios monta con lo de Crear, pero es Anuncios. El Director, si usa una
    herramienta, la nombra: «Director IA · Anuncios»."""
    etiquetas = []
    marco = sys._getframe(2)
    while marco is not None:
        modulo = str(marco.f_globals.get("__name__", ""))
        if modulo.startswith(("motor.", "ui.paginas.")):
            pagina = PAGINAS.get(modulo.rsplit(".", 1)[1])
            if pagina and (not etiquetas or etiquetas[-1] != pagina):
                etiquetas.append(pagina)
        marco = marco.f_back
    etiquetas.reverse()  # de fuera adentro
    if len(etiquetas) > 1 and etiquetas[0] == "Director IA":
        return f"{etiquetas[0]} · {etiquetas[1]}"
    return etiquetas[0] if etiquetas else ""


def motivo(error) -> str:
    """El porqué de un fallo, corto y sin secretos: el código y el «message» del servicio (nunca el texto de httpx en
    inglés con su enlace), sin claves, enlaces firmados ni rutas (guardia.limpiar)."""
    import httpx
    if isinstance(error, httpx.HTTPStatusError):
        from .ia import motivo as del_servicio  # aquí: ia importa este módulo
        texto = f"{error.response.status_code}: {del_servicio(error.response)}"
    elif isinstance(error, BaseException):
        from .idioma import texto_de_error
        texto = texto_de_error(error)
    else:
        texto = str(error or "")
    return guardia.limpiar(texto)[:200] or t("sin motivo")


def _leer() -> dict | None:
    """Lo guardado, con su forma; vacío si no hay o está dañado (un diario roto nunca rompe la app). None si existe y
    otro programa lo retiene: entonces no se escribe encima (se perdería todo lo apuntado)."""
    datos = {}
    for _ in range(20):
        try:
            datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
            break
        except PermissionError:  # se está reemplazando ahora (Windows lo bloquea un instante)
            time.sleep(0.05)
        except (OSError, ValueError, RecursionError):
            datos = {}
            break
    else:
        return None
    datos = datos if isinstance(datos, dict) else {}
    llamadas = []
    for l in datos.get("llamadas") if isinstance(datos.get("llamadas"), list) else []:
        if isinstance(l, dict) and all(isinstance(l.get(k), str) for k in ("fecha", "proveedor", "que", "resultado")):
            costo = l.get("costo")
            llamadas.append({**{k: str(l.get(k) or "") for k in ("fecha", "tarea", "proveedor", "modelo", "que",
                                                                  "resultado", "motivo", "paso_a", "origen")},
                             "costo": float(costo) if isinstance(costo, (int, float)) and not isinstance(costo, bool)
                             and costo >= 0 else 0.0})

    def totales(clave):
        bruto = datos.get(clave)
        if not isinstance(bruto, dict):
            return {}
        return {k: {p: float(v) for p, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
                for k, d in bruto.items() if isinstance(k, str) and isinstance(d, dict)}
    return {"llamadas": llamadas[-MAX_LLAMADAS:], "dias": totales("dias"), "meses": totales("meses")}


def anotar(que: str, proveedor: str, modelo: str = "", costo: float = 0.0, error=None, paso_a: str = "") -> None:
    """Apunta una llamada a un servicio de IA. Sin error: salió bien. Con error (la excepción o un texto): «falló» con
    su motivo corto, y paso_a, el servicio que se probó después en su lugar («pasó a Groq»). costo: US$ como mucho
    (0 si es gratis o no se cobró). Nunca lanza."""
    try:
        try:
            costo = max(float(costo or 0), 0.0)
        except (TypeError, ValueError):
            costo = 0.0
        entrada = {"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "tarea": _tarea(),
                   "proveedor": re.sub(r"[^\w-]", "", str(proveedor))[:40], "modelo": guardia.limpiar(modelo)[:80],
                   "que": que if que in QUE else "texto", "costo": round(costo, 6),
                   "resultado": "ok" if error is None else "fallo", "motivo": "" if error is None else motivo(error),
                   "paso_a": re.sub(r"[^\w-]", "", str(paso_a or ""))[:40], "origen": ORIGEN}

        def guardar():
            from .claves import _reemplazar  # aquí: claves carga más cosas al importarse
            ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
            with _hilos, guardia._cerrojo(ARCHIVO):
                datos = _leer()
                if datos is None:
                    return
                datos["llamadas"] = (datos["llamadas"] + [entrada])[-MAX_LLAMADAS:]
                if entrada["costo"] > 0:  # los totales no dependen del tope de llamadas: el mes sale entero
                    for clave, periodo, maximo in (("dias", entrada["fecha"][:10], DIAS),
                                                   ("meses", entrada["fecha"][:7], MESES)):
                        tabla = datos[clave].setdefault(periodo, {})
                        tabla[entrada["proveedor"]] = round(tabla.get(entrada["proveedor"], 0.0) + entrada["costo"], 6)
                        for viejo in sorted(datos[clave])[:-maximo]:
                            del datos[clave][viejo]
                _reemplazar(ARCHIVO, json.dumps(datos, ensure_ascii=False, indent=0))
        guardar()
    except Exception:  # disco lleno, carpeta de solo lectura…: la llamada a la IA sigue
        traceback.print_exc()


# ---------- Lo que enseña la página «Claves de IA» ----------

def ultimas(n: int = 50) -> list[dict]:
    """Las últimas llamadas, de la más nueva a la más vieja."""
    return ((_leer() or {}).get("llamadas") or [])[::-1][:n]


def gasto(dia: str | None = None) -> dict:
    """{"hoy": {proveedor: US$}, "mes": {proveedor: US$}}: lo estimado de hoy y de este mes, por servicio."""
    datos, dia = _leer() or {}, dia or time.strftime("%Y-%m-%d")
    return {"hoy": dict((datos.get("dias") or {}).get(dia, {})), "mes": dict((datos.get("meses") or {}).get(dia[:7], {}))}


def nombre_servicio(proveedor: str) -> str:
    """Cómo se escribe el servicio en lo que lee el usuario."""
    from . import claves
    if proveedor == "gratis_sin_clave":
        return t("Pollinations sin clave")
    return claves.nombre(proveedor)


def nombre_que(que: str) -> str:
    return {"texto": t("texto"), "imagen": t("imagen"), "video": t("video"), "voz": t("voz"), "musica": t("música"),
            "transcripcion": t("transcripción")}.get(que, que)


def nombre_tarea(tarea: str) -> str:
    """«Director IA · Anuncios», en el idioma de la app (se guarda sin traducir)."""
    return " · ".join(t(p) for p in tarea.split(" · ") if p) or t("sin tarea")


def texto_costo(usd: float) -> str:
    """Lo que costó, dicho para leerlo: «gratis», «menos de US$0.01» o el importe."""
    if usd <= 0:
        return t("gratis")
    return t("menos de {costo}", costo=dinero(0.01)) if usd < 0.005 else dinero(usd)


def texto_resultado(llamada: dict) -> str:
    """«salió bien», o «falló: 402: Your prepayment credits are depleted · pasó a Groq»."""
    if llamada.get("resultado") == "ok":
        return t("salió bien")
    texto = t("falló: {motivo}", motivo=llamada.get("motivo") or t("sin motivo"))
    if llamada.get("paso_a"):
        texto += " · " + t("pasó a {servicio}", servicio=nombre_servicio(llamada["paso_a"]))
    return texto
