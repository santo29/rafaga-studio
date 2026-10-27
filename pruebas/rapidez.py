"""Lo que tarda el Director en hacer una imagen, medido con un reloj simulado y sin red: la conversación de la mariposa
del dueño (Gemini sin saldo desde las 07:03, Groq con Qwen y la imagen gratis de Pollinations), antes y después.
Groq y Gemini son de mentira pero cuentan los tokens como el servicio (también los del razonamiento escondido) y el
límite de tokens por minuto de la cuenta gratis: al pasarlo, la librería de OpenAI espera sola lo que dice Groq.
python -m pruebas.rapidez"""
import json
import os
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402
import openai  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402

from motor import actividad, claves, diseno, director, ia, marca, memoria  # noqa: E402

diseno.asegurar_qt()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-rapidez-"))
claves.ARCHIVO, claves.AJUSTES, claves.CONEXIONES = tmp / "claves.json", tmp / "ajustes.json", tmp / "conexiones.json"
actividad.ARCHIVO, memoria.ARCHIVO, diseno.CARPETA = tmp / "actividad.json", tmp / "memoria.json", tmp / "disenos"
marca.ARCHIVO, marca.CARPETA_LOGO = tmp / "marca.json", tmp / "marca"
claves.guardar({"proveedor": "gemini", "clave": "AIzaSyPRUEBA0000000000000000000000000", "usos": ["texto"],
                "modelo_texto": "gemini-flash-latest"})
claves.guardar({"proveedor": "groq", "clave": "gsk_PRUEBA00000000000000000000000000000", "usos": ["texto"],
                "modelo_texto": "qwen/qwen3.8-27b"})

# Lo que se supone, ajustado al registro de actividad del dueño (08:25:22-08:26:13): el 402 de Gemini, ~1 s; el primer
# paso del Director, 1-2 s; entender, <1 s; diseñar, 3 s; la imagen, ~6 s, y la respuesta final, 38 s. Con 6.000
# tokens por minuto (el límite gratis de Groq para Qwen 3) que se dejan gastar de más y luego se esperan, sale igual
LETRAS_POR_TOKEN = 3.8  # español con JSON
GROQ_LATENCIA, GROQ_LEE, GROQ_ESCRIBE = 0.3, 25_000, 450  # s; tokens/s al leer el pedido y al escribir
TPM = 6_000  # tokens por minuto de la cuenta gratis para ese modelo (se rellena poco a poco, como en Groq)
RAZONA = {"director": 700, "entender": 500, "diseno": 1100}  # tokens que Qwen piensa antes de responder
GEMINI_402, IMAGEN = 1.2, 6.0
reloj = {"ahora": 0.0, "cuota": float(TPM), "visto": 0.0}
eventos = []  # (servicio, para qué, empieza, termina, tokens)
pedido = httpx.Request("POST", "https://api.example/v1/chat/completions")
SIN_SALDO = {"error": {"code": 402, "message": "Your prepayment credits are depleted."}}


def respuesta(para: str, usuario: str) -> dict:
    if para == "director":  # primero hace la foto; con ella hecha, termina
        if "(ninguno todavía)" in usuario:
            return {"mensaje": "Te hago la foto de la mariposa en el jardín.", "herramienta": "crear_diseno",
                    "argumentos": json.dumps({"pedido": "una mariposa real en un jardín", "tipo": "ilustracion"})}
        return {"mensaje": "Listo: tu foto de la mariposa está en Diseño.", "herramienta": "", "argumentos": "{}"}
    if para == "entender":  # como la IA pequeña: lo toma por un dibujo suelto
        return {"entendido": "una mariposa real en un jardín", "seguro": True, "pregunta": "", "opciones": [],
                "tipo": "ilustracion", "estilo": "vector"}
    return {"titulo": "Mariposa en el jardín", "descripcion": "Una mariposa monarca en un jardín al sol.",
            "fondo_colores": ["#2E5E2E"], "fondo_prompt_imagen": "a real monarch butterfly on a flower in a sunny "
                                                                 "garden", "capas": []}


def gastar(tokens: float) -> None:
    """La cuota de tokens por minuto, que se rellena poco a poco: un pedido entra si queda algo (aunque la deje en
    negativo) y, si ya está en negativo, espera a que vuelva a cero (Groq responde 429 con lo que hay que esperar y la
    librería de OpenAI lo espera sola, sin que la app lo sepa)."""
    reloj["cuota"] = min(TPM, reloj["cuota"] + (reloj["ahora"] - reloj["visto"]) * TPM / 60)
    if reloj["cuota"] < 0:
        reloj["ahora"] += -reloj["cuota"] / (TPM / 60)
        reloj["cuota"] = 0.0
    reloj["cuota"] -= tokens
    reloj["visto"] = reloj["ahora"]


class OpenAIFalso:
    def __init__(self, api_key, base_url, **k):
        self.base = base_url
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.crear))

    def crear(self, model, messages, extra_body=None, **k):
        sistema, usuario = messages[0]["content"], messages[1]["content"]
        para = ("director" if "Eres el Director" in sistema else
                "entender" if "Recibes el pedido de una pieza" in sistema else "diseno")
        inicio = reloj["ahora"]
        if "googleapis" in self.base:
            reloj["ahora"] += GEMINI_402
            eventos.append(("gemini", para, inicio, reloj["ahora"], 0))
            raise openai.APIStatusError("402", body=SIN_SALDO, response=httpx.Response(402, request=pedido,
                                                                                         json=SIN_SALDO))
        contenido = json.dumps(respuesta(para, usuario), ensure_ascii=False)
        piensa = (extra_body or {}).get("reasoning_effort") != "none"
        entrada = (len(sistema) + len(usuario)) / LETRAS_POR_TOKEN
        salida = len(contenido) / LETRAS_POR_TOKEN + (RAZONA[para] if piensa else 0)
        gastar(entrada + salida)
        reloj["ahora"] += GROQ_LATENCIA + entrada / GROQ_LEE + salida / GROQ_ESCRIBE
        eventos.append(("groq", para, inicio, reloj["ahora"], entrada + salida))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=contenido))],
                                     usage=types.SimpleNamespace(prompt_tokens=entrada, completion_tokens=salida))


def imagen(prompt, ancho, alto, destino, calidad="1K"):
    inicio = reloj["ahora"]
    reloj["ahora"] += IMAGEN
    eventos.append(("pollinations", "imagen", inicio, reloj["ahora"], 0))
    foto = QImage(ancho, alto, QImage.Format_RGB32)  # una «foto» con degradado: nada de un color liso
    degradado = QLinearGradient(0, 0, ancho, alto)
    degradado.setColorAt(0, QColor("#1E6B2A"))
    degradado.setColorAt(1, QColor("#F2A93B"))
    p = QPainter(foto)
    p.fillRect(foto.rect(), degradado)
    p.end()
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    assert foto.save(str(destino))
    return Path(destino)


def conversacion(mejorada: bool) -> dict:
    """«Hazme una imagen de una mariposa real en un jardín» al Director, con Gemini sin saldo comprobado a las 07:03.
    Sin la mejora: se le pide igual a Gemini y Qwen piensa antes de cada respuesta."""
    eventos.clear()
    reloj.update(ahora=0.0, cuota=float(TPM), visto=0.0)
    claves.CONEXIONES.write_text(json.dumps({"gemini": {
        "estado": "sin_saldo", "detalle": "402: Your prepayment credits are depleted.", "paso": "",
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))}}), encoding="utf-8")
    actividad.ARCHIVO.unlink(missing_ok=True)
    reales = ia._saltado, ia._sin_razonar
    if not mejorada:
        ia._saltado, ia._sin_razonar = (lambda c: None), (lambda proveedor, modelo: {})
    preguntas = []
    try:
        r = director.dirigir("hazme una imagen de una mariposa real en un jardín",
                             confirmar=lambda p: preguntas.append(p) or True)
    finally:
        ia._saltado, ia._sin_razonar = reales
    assert not preguntas  # todo gratis: nada que preguntar
    fin_imagen = next(fin for quien, _, _, fin, _ in eventos if quien == "pollinations")
    hecho = json.loads((Path(r["resultados"][0]["archivo"]).parent / "diseno.json").read_text(encoding="utf-8"))
    return {"total": reloj["ahora"], "final": reloj["ahora"] - fin_imagen, "diseno": hecho,
            "gemini": sum(quien == "gemini" for quien, *_ in eventos),
            "tokens": round(sum(t for quien, *_, t in eventos if quien == "groq")),
            "saltos": [a for a in actividad.ultimas() if a["motivo"].startswith("No se le pidió")]}


abrir_openai, imagen_real = openai.OpenAI, ia.imagen
openai.OpenAI, ia.imagen = OpenAIFalso, imagen
try:
    antes, despues = conversacion(False), conversacion(True)
finally:
    openai.OpenAI, ia.imagen = abrir_openai, imagen_real

# Antes: cada paso de texto (2 del Director, entender el pedido y diseñar) esperaba el 402 de Gemini, y Qwen pensaba
# antes de cada respuesta. Después: Gemini ni se pregunta (queda en la actividad que se saltó) y el Director y entender
# responden sin pensar; diseñar sigue pensando (calidad)
assert antes["gemini"] == 4 and not antes["saltos"], antes
assert despues["gemini"] == 0 and len(despues["saltos"]) == 4, despues
assert {s["paso_a"] for s in despues["saltos"]} == {"groq"}
assert despues["tokens"] < antes["tokens"] - 1500, (antes["tokens"], despues["tokens"])
assert despues["total"] < antes["total"] - 8 and despues["final"] < antes["final"] / 2, (antes, despues)
# Las dos veces, la foto llena el lienzo (el Director pidió «ilustracion», pero el pedido dice «real»)
for vez in (antes, despues):
    d = vez["diseno"]
    assert d["fondo"]["tipo"] == "imagen" and not [c for c in d["capas"] if c["tipo"] == "imagen"], d
print(f"Antes: {antes['total']:.1f} s en total; la respuesta final del Director, {antes['final']:.1f} s; "
      f"{antes['gemini']} esperas a Gemini sin saldo; {antes['tokens']} tokens a Groq.")
print(f"Después: {despues['total']:.1f} s en total; la respuesta final del Director, {despues['final']:.1f} s; "
      f"{despues['gemini']} esperas a Gemini; {despues['tokens']} tokens a Groq.")
print("Pruebas de rapidez del Director pasadas.")
