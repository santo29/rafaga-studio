"""Conexiones y actividad de la IA, sin red: cada llamada queda apuntada (sin secretos, con su costo y con lo que pasó
después), «Comprobar conexiones» dice el estado real de cada servicio con la petición más barata, los trabajos avisan
ANTES de empezar si un servicio no atiende, y cada «sin saldo» pasa a otra opción gratis o se dice claro sin cobrar.
Las respuestas de los servicios son de mentira, pero pasan por las funciones de verdad.
python -m pruebas.conexiones"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402

from motor import actividad, claves, desde_prompt, director, guardia, herramientas, ia, memoria, musica, nubes, serie  # noqa: E402,E501
from motor.idioma import dinero  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="rafaga-conexiones-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"
nubes.USO, memoria.ARCHIVO, musica.PROYECTOS = tmp / "uso_nubes.json", tmp / "memoria.json", tmp / "proyectos"
SIN_SALDO = {"error": {"code": 402, "message": "Your prepayment credits are depleted."}}
GEMINI = {"proveedor": "gemini", "clave": "AIzaSyPRUEBA0000000000000000000000000", "usos": ["texto", "musica"],
          "modelo_texto": "gemini-flash-latest", "modelo_musica": "lyria-3.5"}
GROQ = {"proveedor": "groq", "clave": "gsk_PRUEBA00000000000000000000000000000", "usos": ["texto", "transcripcion"],
        "modelo_texto": "qwen/qwen3.8-27b"}
ELEVEN = {"proveedor": "elevenlabs", "clave": "sk_" + "a1" * 24, "usos": ["voz", "musica"], "modelo_musica": "music_v2_5"}
POLLI = {"proveedor": "pollinations", "clave": "sk_" + "AbCdEfGh" * 8, "usos": ["texto", "imagen", "video"],
         "modelo_imagen": "zimage", "modelo_texto": "openai"}
reales = {"get": httpx.get, "post": httpx.post}


def sin_red(*a, **k):
    raise AssertionError(f"salió a la red: {a[:1]}")


httpx.get = httpx.post = sin_red  # nada sale a internet salvo lo que cada parte simula


def respuesta(codigo, cuerpo=None, metodo="GET", url="https://servicio.example/v1/x", **k):
    if cuerpo is not None and not isinstance(cuerpo, (str, bytes)):
        k["json"] = cuerpo
    elif cuerpo is not None:
        k["content" if isinstance(cuerpo, bytes) else "text"] = cuerpo
    return httpx.Response(codigo, request=httpx.Request(metodo, url), **k)


def falla(funcion, *a, error=Exception, **k):
    try:
        funcion(*a, **k)
    except error as e:
        return e
    raise AssertionError(f"{getattr(funcion, '__name__', funcion)} debió fallar")


def conectar(*infos, **ajustes):
    """Solo estas claves, estos ajustes y sin estados ni actividad de antes."""
    for archivo in (claves.ARCHIVO, claves.AJUSTES, claves.CONEXIONES, actividad.ARCHIVO):
        archivo.unlink(missing_ok=True)
    for info in infos:
        claves.guardar(info)
    for uso, proveedor in ajustes.items():
        claves.elegir_por_defecto(uso, proveedor)


def estado(proveedor, que, hace=0):
    """Un estado comprobado hace `hace` segundos."""
    todos = claves.estados()
    todos[proveedor] = {"estado": que, "detalle": "", "paso": claves.paso(proveedor, que),
                        "fecha": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - hace))}
    claves.CONEXIONES.write_text(json.dumps(todos), encoding="utf-8")


# ---------- La actividad de la IA: qué, quién, cuánto y cómo salió, sin secretos ----------
conectar()
actividad.anotar("texto", "gemini", "gemini-flash-latest", 0.004)
actividad.anotar("musica", "elevenlabs", "music_v2_5", 0.45)
secreto = ("401: clave AIzaSyA1234567890abcdefghijklmnopqrstu no vale; ver https://x.example/v1/files/abc?sig=FIRMA123 "
           "y C:\\Users\\King\\Videos\\mi_video.mp4 con sk-ant-api03-SECRETO1234567890abcdefgh")
actividad.anotar("texto", "gemini", "modelo sk-ant-api03-OTROSECRETO1234567890", error=secreto, paso_a="groq")
ultima = actividad.ultimas(1)[0]
assert ultima["resultado"] == "fallo" and ultima["paso_a"] == "groq" and ultima["costo"] == 0, ultima
guardado = actividad.ARCHIVO.read_text(encoding="utf-8")
for nada in ("AIzaSy", "sig=", "FIRMA123", "King", "SECRETO", "Videos"):
    assert nada not in guardado, nada  # ni claves, ni firmas de enlaces, ni rutas con tu nombre
assert "mi_video.mp4" in ultima["motivo"] and "x.example" in ultima["motivo"]  # el porqué sí se entiende
assert actividad.texto_resultado(ultima).startswith("falló: 401") and \
    actividad.texto_resultado(ultima).endswith("· pasó a Groq"), actividad.texto_resultado(ultima)
assert actividad.texto_resultado(actividad.ultimas(2)[1]) == "salió bien"
gasto = actividad.gasto()
assert gasto["hoy"] == {"gemini": 0.004, "elevenlabs": 0.45} and gasto["mes"] == gasto["hoy"], gasto
assert actividad.texto_costo(0) == "gratis" and actividad.texto_costo(0.004) == "menos de US$0.01"
assert actividad.texto_costo(0.45) == dinero(0.45) == "US$0.45"
assert actividad.nombre_servicio("gratis_sin_clave") == "Pollinations sin clave"
assert [l["que"] for l in actividad.ultimas(5)] == ["texto", "musica", "texto"]  # de la más nueva a la más vieja
# Un error de httpx se apunta en claro: su código y su «message», nunca el texto en inglés con el enlace de mozilla
error_http = httpx.HTTPStatusError("Client error '402 Payment Required' for url 'https://gen.pollinations.ai/v1/x'\n"
                                   "For more information check: https://developer.mozilla.org/402",
                                   request=httpx.Request("POST", "https://gen.pollinations.ai/v1/x"),
                                   response=respuesta(402, {"error": {"message": "Insufficient pollen"}}))
assert actividad.motivo(error_http) == "402: Insufficient pollen"

# La tarea sale sola de quién llamó: la página (o la herramienta del Director), sin que cada una lo diga
paginas = {"__name__": "motor.director", "actividad": actividad}
anuncios = {"__name__": "motor.anuncios", "actividad": actividad}
exec("def interno():\n    actividad.anotar('imagen', 'pollinations', 'zimage')\n", anuncios)
exec("def llamar():\n    interno()\n", paginas)
paginas["interno"] = anuncios["interno"]
paginas["llamar"]()
assert actividad.ultimas(1)[0]["tarea"] == "Director IA · Anuncios"
assert actividad.nombre_tarea("Director IA · Anuncios") == "Director IA · Anuncios"
anuncios["interno"]()
assert actividad.ultimas(1)[0]["tarea"] == "Anuncios" and actividad.ultimas(1)[0]["origen"] == "app"

# Tope de llamadas guardadas, pero los totales del día y del mes cuentan todas
conectar()
tope = actividad.MAX_LLAMADAS
actividad.MAX_LLAMADAS = 5
try:
    for _ in range(8):
        actividad.anotar("video", "modal", "wan", 0.35)
    assert len(actividad.ultimas(50)) == 5 and abs(actividad.gasto()["hoy"]["modal"] - 8 * 0.35) < 1e-9
finally:
    actividad.MAX_LLAMADAS = tope

# A la vez: varios hilos de la app y otro proceso (el servidor MCP) apuntan sin perder ninguna línea
conectar()
mcp = subprocess.Popen([sys.executable, "-s", "-E", "-c",
                        "import sys; from pathlib import Path; from motor import actividad; "
                        "actividad.ARCHIVO = Path(sys.argv[1]); actividad.ORIGEN = 'mcp'\n"
                        "for _ in range(40): actividad.anotar('texto', 'groq', 'm')", str(actividad.ARCHIVO)],
                       cwd=RAIZ, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
hilos = [threading.Thread(target=lambda: [actividad.anotar("imagen", "cloudflare", "flux", 0.0) for _ in range(20)])
         for _ in range(3)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
assert mcp.wait(120) == 0
llamadas = actividad.ultimas(500)
assert len(llamadas) == 100, len(llamadas)
assert sum(l["origen"] == "mcp" for l in llamadas) == 40 and sum(l["origen"] == "app" for l in llamadas) == 60

# Nunca tumba la llamada que apunta: disco que no deja escribir o un archivo dañado
bueno = actividad.ARCHIVO
actividad.ARCHIVO = tmp / "no_es_carpeta.txt" / "actividad.json"
(tmp / "no_es_carpeta.txt").write_text("x", encoding="utf-8")
try:
    actividad.anotar("texto", "groq", "m")  # no lanza (el detalle va a la consola)
    assert actividad.ultimas() == [] and actividad.gasto() == {"hoy": {}, "mes": {}}
finally:
    actividad.ARCHIVO = bueno
actividad.ARCHIVO.write_text("{roto", encoding="utf-8")
assert actividad.ultimas() == []
actividad.anotar("texto", "groq", "m")
assert len(actividad.ultimas()) == 1
print("Actividad de la IA: bien.")

# ---------- Lo que dice cada respuesta de un servicio ----------
c = claves.clasificar
assert c(200) == "ok" and c(402) == "sin_saldo" and c(401) == "clave" and c(403) == "clave"
assert c(429, "Your prepayment credits are depleted.") == "sin_saldo" and c(429, "rate limit") == "sin_cuota"
assert c(400, "API key not valid. Please pass a valid API key.") == "clave"
assert c(400, "Your credit balance is too low to access the Anthropic API.") == "sin_saldo"
assert c(400, "bad schema") == "error" and c(503, "overloaded") == "error"
assert "aistudio.google.com" in claves.paso("gemini", "sin_saldo") and "Billing" in claves.paso("gemini", "sin_saldo")
assert "openrouter.ai/settings/credits" in claves.paso("openrouter", "sin_saldo")
assert claves.paso("groq", "ok") == ""

# ---------- «Comprobar conexiones»: la petición más barata que dice el estado real ----------
DEEPSEEK = {"proveedor": "deepseek", "clave": "sk-deepseekPRUEBA", "usos": ["texto"], "modelo_texto": "deepseek-chat"}
ROUTER = {"proveedor": "openrouter", "clave": "sk-or-v1-PRUEBA", "usos": ["texto"], "modelo_texto": "x"}
CLAUDE = {"proveedor": "anthropic", "clave": "sk-ant-api03-PRUEBA", "usos": ["texto"], "modelo_texto": "claude-opus-5-5"}
HF = {"proveedor": "huggingface", "clave": "hf_PRUEBA", "usos": ["imagen", "video"]}
conectar(GEMINI, GROQ, ELEVEN, DEEPSEEK, ROUTER, CLAUDE, HF)
pedidos = []


def get_falso(url, **k):
    pedidos.append(("GET", url))
    if "groq.com" in url:
        return respuesta(401, {"error": {"message": "Invalid API Key"}})
    if "deepseek.com/user/balance" in url:
        return respuesta(200, {"is_available": False, "balance_infos": []})
    if "openrouter.ai/api/v1/key" in url:
        return respuesta(200, {"data": {"limit_remaining": 0}})
    if "elevenlabs.io/v1/user/subscription" in url:
        return respuesta(200, {"character_count": 10000, "character_limit": 10000})
    if "anthropic.com" in url:
        raise httpx.ConnectError("sin red", request=httpx.Request("GET", url))
    if "huggingface.co" in url:
        return respuesta(429, {"error": "Rate limit reached"})
    raise AssertionError(url)


def post_falso(url, **k):
    pedidos.append(("POST", url, k.get("json")))
    assert "googleapis.com" in url and ":generateContent" in url, url
    return respuesta(402, SIN_SALDO, "POST")


httpx.get, httpx.post = get_falso, post_falso
try:
    hechos = claves.comprobar()
finally:
    httpx.get = httpx.post = sin_red
esperado = {"gemini": "sin_saldo", "groq": "clave", "deepseek": "sin_saldo", "openrouter": "sin_saldo",
            "elevenlabs": "sin_saldo", "anthropic": "sin_conexion", "huggingface": "sin_cuota"}
assert {p: e["estado"] for p, e in hechos.items()} == esperado, hechos
assert claves.estados().keys() == esperado.keys() and claves.estados()["gemini"]["estado"] == "sin_saldo"
assert hechos["gemini"]["detalle"] == "402: Your prepayment credits are depleted."
assert "Recarga en AI Studio" in hechos["gemini"]["paso"] and "Conseguir clave" in hechos["groq"]["paso"]
assert "internet" in hechos["anthropic"]["paso"]
# El detalle, en claro: no «ConnectError», el nombre de la clase en inglés
assert hechos["anthropic"]["detalle"].startswith("Sin conexión con api.anthropic.com"), hechos["anthropic"]
# Gemini: un solo token del modelo de texto más barato (solo un pedido de verdad dice «sin saldo prepago»)
gemini_pedido = [p for p in pedidos if p[0] == "POST"]
assert len(gemini_pedido) == 1 and claves.GEMINI_BARATO in gemini_pedido[0][1]
assert gemini_pedido[0][2]["generationConfig"]["maxOutputTokens"] == 1
guardado = claves.CONEXIONES.read_text(encoding="utf-8")
assert all(i["clave"] not in guardado for i in (GEMINI, GROQ, ELEVEN, DEEPSEEK, ROUTER, CLAUDE, HF))  # nunca claves
# ElevenLabs con una clave sin el permiso «User: Read» (pasó con la del dueño, buena y con saldo): no es «Clave no
# válida». Su lista de modelos dice que la clave vale; las letras que quedan no se pueden ver
SIN_PERMISO = "The API key you used is missing the permission user_read to execute this operation."
assert claves.clasificar(401, SIN_PERMISO) == "permiso" and claves.clasificar(401, "Invalid API key") == "clave"
assert "permiso" not in claves.NO_ATIENDE | claves.BLOQUEA and "edita esta clave" in claves.paso("elevenlabs", "permiso")


def get_permiso(url, **k):
    if "elevenlabs.io/v1/user/subscription" in url:
        return respuesta(401, {"detail": {"status": "missing_permissions", "message": SIN_PERMISO}})
    assert "elevenlabs.io/v1/models" in url, url
    return respuesta(200, [])


httpx.get = get_permiso
try:
    hecho = claves._comprobar_uno("elevenlabs", ELEVEN)
finally:
    httpx.get = sin_red
assert hecho["estado"] == "clave_ok" and "User: Read" in hecho["detalle"] and not hecho["paso"], hecho
# La comprobación de Gemini es un pedido de verdad: queda en la actividad, desde «Claves de IA» y sin costo (no cobró)
sonda = actividad.ultimas(1)[0]
assert (sonda["proveedor"], sonda["tarea"], sonda["resultado"], sonda["costo"]) == ("gemini", "Claves de IA",
                                                                                      "fallo", 0.0), sonda
# Conectar una clave: el motivo de verdad, en claro (antes todo era «Clave no válida», con el error de httpx en inglés
# y el nombre interno «elevenlabs»). Sin «Voices: Read» se conecta igual: la música no lo necesita, sus voces no salen
SIN_VOCES = SIN_PERMISO.replace("user_read", "voices_read")
VOZ = {"voice_id": "v1", "name": "Rafa", "labels": {"accent": "caribeño"}}
assert claves._permiso(SIN_VOCES) == "Voices: Read" and claves._permiso("Forbidden") == ""
assert claves._permiso("You don't have permission to access this resource") == ""
assert claves._permiso("missing the permission text_to_speech") == "Text to speech"


def eleven_falso(modelos, voces=None):
    """httpx.get de ElevenLabs al conectar: su lista de modelos responde `modelos`, la de voces `voces` (o lanzan)."""
    def get(url, **k):
        assert "elevenlabs.io/v1/models" in url or "elevenlabs.io/v2/voices" in url, url  # las letras no se miran
        r = modelos if "/v1/models" in url else voces
        if isinstance(r, Exception):
            raise r
        return r
    return get


def sin_permiso(texto):
    return respuesta(401, {"detail": {"status": "missing_permissions", "message": texto}})


# Sin «User: Read» ni «Models: Read», «Comprobar conexiones» tampoco la pinta ámbar: esa lista la app no la usa
SIN_MODELOS = SIN_PERMISO.replace("user_read", "models_read")
httpx.get = lambda url, **k: sin_permiso(SIN_MODELOS if "elevenlabs.io/v1/models" in url else SIN_PERMISO)
try:
    hecho = claves._comprobar_uno("elevenlabs", ELEVEN)
finally:
    httpx.get = sin_red
assert hecho["estado"] == "clave_ok" and "User: Read" in hecho["detalle"], hecho
NO_VALE = respuesta(401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}})
PROHIBIDO = respuesta(403, {"detail": "Forbidden"})
CON_VOCES = respuesta(200, {"voices": [VOZ], "has_more": False})
CONECTADA_SIN_VOCES = "La clave de ElevenLabs quedó conectada, pero le falta el permiso «Voices: Read»"
casos = {  # caso: (lista de modelos, lista de voces, estado del fallo o None si conecta, cómo empieza lo que dice)
    "sin user_read": (respuesta(200, []), CON_VOCES, None, None),
    "sin voices_read": (respuesta(200, []), sin_permiso(SIN_VOCES), None, CONECTADA_SIN_VOCES),
    # Sin «Models: Read» también conecta: ElevenLabs reconoce la clave y esa lista no se usa para narrar ni para música
    "sin models_read": (sin_permiso(SIN_MODELOS), CON_VOCES, None, None),
    "sin models_read ni voices_read": (sin_permiso(SIN_MODELOS), sin_permiso(SIN_VOCES), None, CONECTADA_SIN_VOCES),
    "403 llano en las voces": (respuesta(200, []), PROHIBIDO, None, CONECTADA_SIN_VOCES),  # ya listó los modelos
    "no vale": (NO_VALE, None, "clave", "ElevenLabs no acepta esta clave (401: Invalid API key). Comprueba"),
    # Un servicio que repite la clave en su respuesta: a la ventana y a la consola llega tapada (guardia.limpiar)
    "repite la clave": (respuesta(401, {"detail": {"message": f"Invalid API key: {ELEVEN['clave']}"}}), None, "clave",
                        "ElevenLabs no acepta esta clave (401: Invalid API key: [clave])."),
    "403": (PROHIBIDO, None, "permiso", "ElevenLabs no deja usar esta clave (403: Forbidden). En la web de ElevenLabs"),
    "sin red": (httpx.ConnectError("sin internet"), None, "sin_conexion",
                "Sin conexión con ElevenLabs. Revisa tu internet e inténtalo de nuevo."),
    "sin red en las voces": (respuesta(200, []), httpx.ConnectError("x"), "sin_conexion", "Sin conexión con ElevenLabs."),
    # Un portal wifi o un proxy que redirige sin fin, o una respuesta que no se puede leer: tampoco hay conexión
    "redirección sin fin": (httpx.TooManyRedirects("x"), None, "sin_conexion", "Sin conexión con ElevenLabs."),
    "respuesta ilegible": (httpx.DecodingError("x"), None, "sin_conexion", "Sin conexión con ElevenLabs."),
    "sin saldo": (respuesta(402, {"detail": "quota_exceeded"}), None, "sin_saldo",
                  "ElevenLabs no tiene saldo (402: quota_exceeded). Recarga saldo en elevenlabs.io"),
}
for caso, (modelos, voces, fallo, dice) in casos.items():
    httpx.get = eleven_falso(modelos, voces)
    try:
        if fallo:
            e = falla(claves.detectar, ELEVEN["clave"], error=claves.NoConecta)
            assert e.estado == fallo and str(e).startswith(dice), (caso, e.estado, str(e))
            assert "Client error" not in str(e) and "elevenlabs" not in str(e).replace("elevenlabs.io", ""), str(e)
            assert fallo == "sin_conexion" or "inténtalo de nuevo" not in str(e), (caso, str(e))  # un permiso no
            assert ELEVEN["clave"] not in str(e), (caso, str(e))
        else:
            info = claves.detectar(ELEVEN["clave"])
            assert info["proveedor"] == "elevenlabs" and info["modelo_musica"] == "music_v2_5", (caso, info)
            if dice:
                assert info["voces"] == [] and info["aviso"].startswith(dice), (caso, info)
            else:
                assert info["voces"] == [{"id": "v1", "nombre": "Rafa", "acento": "caribeño"}] and "aviso" not in info
    finally:
        httpx.get = sin_red
e = falla(claves.detectar, "hola", error=claves.NoConecta)  # sin preguntar a nadie
assert e.estado == "formato" and str(e).startswith("No reconozco el formato de esta clave"), (e.estado, str(e))
e = falla(claves.detectar, GEMINI["clave"], "kling", error=claves.NoConecta)  # pegada en el botón de Kling
assert e.estado == "formato" and "no de Kling" in str(e), (e.estado, str(e))
# OpenAI: una clave restringida sin «Models: Read» responde 401 «Missing scopes» (pasó lo mismo que con ElevenLabs):
# es un permiso que falta, no una clave mal copiada; «Comprobar conexiones» dice lo mismo
SCOPES = ("You have insufficient permissions for this operation. Missing scopes: api.model.read. Check that you have the "
          "correct role in your organization, and if you're using a restricted API key, that it has the necessary scopes.")
assert claves.clasificar(401, SCOPES) == "permiso" and claves._permiso(SCOPES) == "api.model.read"
CLAVE_OPENAI = "sk-proj-" + "A1b2" * 12


def openai_sin_scopes(url, **k):
    assert url.startswith("https://api.openai.com/v1/models"), url
    return respuesta(401, {"error": {"message": SCOPES, "type": "invalid_request_error"}}, url=url)


httpx.get = openai_sin_scopes
try:
    e = falla(claves.detectar, CLAVE_OPENAI, error=claves.NoConecta)
    hecho = claves._comprobar_uno("openai", {"proveedor": "openai", "clave": CLAVE_OPENAI})
finally:
    httpx.get = sin_red
assert e.estado == "permiso" and "«api.model.read»" in str(e) and "copiaste entera" not in str(e), str(e)
assert hecho["estado"] == "permiso" and "api.model.read" in hecho["detalle"], hecho
# Cloudflare: el token solo que no vale es «Clave no válida»; si falta pegar la cuenta, es lo que se pegó; y un 403 con
# la cuenta pegada puede ser el ID de una zona (también 32 letras y números)
TOKEN_CF = "cfut_" + "A1b2C3d4" * 6
for clave, cf, motivo_cf, dice in (
        (TOKEN_CF, respuesta(401), "clave", "Cloudflare no acepta ese token"),
        (TOKEN_CF, respuesta(200, {"result": []}), "formato", "Pega también tu Account ID"),
        (f"{'0123456789abcdef' * 2} {TOKEN_CF}", respuesta(403, {"errors": [{"message": "Authentication error"}]}),
         "permiso", "Cloudflare no deja usar esta clave (403: Authentication error)")):
    httpx.get = lambda url, cf=cf, **k: cf if url.startswith("https://api.cloudflare.com/") else sin_red(url)
    try:
        e = falla(claves.detectar, clave, error=claves.NoConecta)
    finally:
        httpx.get = sin_red
    assert e.estado == motivo_cf and str(e).startswith(dice), (motivo_cf, e.estado, str(e))
    assert motivo_cf != "permiso" or str(e).endswith("(no el de una zona)."), str(e)
# Con saldo: lo que cuesta es una fracción de centavo; y si la clave no tiene el modelo barato, con el de sus guiones
conectar(GEMINI)
modelos = []


def post_ok(url, **k):
    modelos.append(url.split("/models/")[1].split(":")[0])
    if claves.GEMINI_BARATO in url:
        return respuesta(404, {"error": {"message": "model not found"}}, "POST")
    return respuesta(200, {"usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1}}, "POST")


httpx.post = post_ok
try:
    assert claves.comprobar()["gemini"]["estado"] == "ok"
finally:
    httpx.post = sin_red
assert modelos == [claves.GEMINI_BARATO, "gemini-flash-latest"]
assert 0 < actividad.ultimas(1)[0]["costo"] < 0.0001  # menos de una centésima de centavo
# De pago y sin consulta de saldo (OpenAI, Claude, xAI…): su lista gratis responde bien aunque la cuenta no tenga
# crédito, así que no se dice «Funciona» sino que la clave vale. Groq (gratis) sí funciona
OPENAI = {**GROQ, "proveedor": "openai", "clave": "sk-proj-PRUEBA"}
conectar(OPENAI, GROQ)
httpx.get = lambda url, **k: respuesta(200, {"data": [{"id": "gpt"}]}, "GET", url)
try:
    assert {p: e["estado"] for p, e in claves.comprobar().items()} == {"openai": "clave_ok", "groq": "ok"}
finally:
    httpx.get = sin_red
assert claves.estados()["openai"]["paso"] == "" and not claves.antes_de(["texto"])  # no es un problema
claves.recordar("openai", 200)  # una llamada de verdad salió bien: ahora sí se sabe que funciona
assert claves.estados()["openai"]["estado"] == "ok"
# Modal sin internet: «modal app list» falla, pero no es la clave (antes mandaba a crear otra); cada sonda, en un hilo
# daemon (Python no espera a ninguno al salir: cerrar la app no se queda colgado)
MODAL = {"proveedor": "modal", "clave": "ak-PRUEBA as-PRUEBA", "usos": ["video"]}
conectar(MODAL)
correr, daemons = subprocess.run, []


def modal_responde(salida):
    def run(*a, **k):
        daemons.append(threading.current_thread().daemon)
        if isinstance(salida, Exception):
            raise salida
        return subprocess.CompletedProcess(a, 1 if salida else 0, "", salida)
    return run


for salida, que in (("Error: Could not connect to the Modal server.", "sin_conexion"),
                    (subprocess.TimeoutExpired("modal", 60), "sin_conexion"),
                    ("Error: Token validation failed.", "clave"), ("", "clave_ok")):
    subprocess.run = modal_responde(salida)
    try:
        hecho = claves.comprobar()["modal"]
    finally:
        subprocess.run = correr
    assert hecho["estado"] == que, (salida, hecho)
    assert que != "sin_conexion" or "internet" in hecho["paso"] and "rechazó" not in hecho["detalle"], hecho
assert daemons == [True] * 4, daemons
print("Comprobar conexiones: bien.")

# ---------- Antes de empezar: lo que no atiende se dice, y lo de pago que no puede salir ni empieza ----------
conectar(GEMINI, GROQ)
estado("gemini", "sin_saldo")
assert claves.antes_de(["texto"]) == ["Gemini no tiene saldo: usaré Groq para el texto."], claves.antes_de(["texto"])
estado("groq", "clave")
assert claves.antes_de(["texto"]) == ["Gemini no tiene saldo: usaré la IA gratis sin clave para el texto (más lenta)."]
claves.recordar("groq", 200)  # Groq volvió a responder bien en un trabajo: deja de avisar
assert claves.estados()["groq"]["estado"] == "ok" and "usaré Groq" in claves.antes_de(["texto"])[0]
estado("gemini", "sin_saldo", hace=claves.VIGENCIA + 60)  # lo de ayer ya no vale para avisar (pudo recargar)
assert claves.antes_de(["texto"]) == [] and claves.impide(["video_voz"]) is None
# Escenas que hablan (solo de pago): sin saldo, ni empieza ni se pregunta el costo
estado("gemini", "sin_saldo")
no = claves.impide(["video_voz"])
assert no.startswith("No se puede hacer el video que habla: Gemini no tiene saldo (comprobado hoy a las ") and \
    "aistudio.google.com" in no and "No se cobró nada." in no, no
# Como ni se pide, ninguna respuesta buena lo desbloquea sola: dice cómo, también a un agente MCP
assert "Si ya recargaste o cambiaste la clave, pulsa «Comprobar conexiones» en «Claves de IA». O desmarca" in no, no
estado("gemini", "sin_cuota")  # una cuota por minuto no impide: puede liberarse enseguida
assert claves.impide(["video_voz"]) is None
# La canción: en automático y con ElevenLabs conectado, pasa a ElevenLabs y lo dice con su costo; sin él, no empieza
estado("gemini", "sin_saldo")
assert "No se puede hacer la canción: Gemini no tiene saldo" in claves.impide(["musica"])
assert "pulsa «Comprobar conexiones»" in claves.impide(["musica"])
claves.guardar(ELEVEN)
assert claves.impide(["musica"]) is None
assert claves.antes_de(["musica"]) == [f"Gemini no tiene saldo: la canción la hará ElevenLabs (hasta unos "
                                       f"{dinero(musica.PRECIO['elevenlabs'])})."]
claves.elegir_por_defecto("musica", "gemini")  # Gemini elegido a mano: nunca pasa a otro de pago por detrás
assert "No se puede hacer la canción" in claves.impide(["musica"])
claves.elegir_por_defecto("musica", "auto")

# El Director: lo dice en el chat antes de su primer paso, y lo de pago imposible vuelve como ERROR sin preguntar
dichos, preguntas, usadas = [], [], []
real_texto = ia.texto_json
ia.texto_json = lambda instrucciones, pedido, esquema, uso="texto", **k: {"mensaje": "Listo.", "herramienta": "",
                                                                    "argumentos": "{}"}
try:
    director.dirigir("hazme un video", al_decir=dichos.append)
    assert dichos == ["Gemini no tiene saldo: usaré Groq para el texto."], dichos
    # Una vez por conversación, no al empezar cada respuesta (ni en cada frase del modo voz); si deja de valer y
    # vuelve, se dice otra vez
    director.dirigir("y otro", al_decir=dichos.append)
    assert len(dichos) == 1, dichos
    estado("gemini", "ok")
    director.dirigir("otro más", al_decir=dichos.append)
    estado("gemini", "sin_saldo")
    director.dirigir("y el último", al_decir=dichos.append)
finally:
    ia.texto_json = real_texto
assert dichos == ["Gemini no tiene saldo: usaré Groq para el texto."] * 2, dichos
args, r = director._usar("crear_video", {"prompt": "una manzana que habla", "animado": True}, lambda *a: None,
                         usadas.append, "una manzana que habla", "", lambda p: preguntas.append(p) or True)
assert r.startswith("ERROR: No se puede hacer el video que habla: Gemini no tiene saldo"), r
assert not preguntas and not usadas  # ni se preguntó el costo ni empezó
avisados, real_crear = [], herramientas.TODAS["crear_video"]
herramientas.TODAS["crear_video"] = lambda prompt, formato="9:16", segundos=45, voz="", imagen="", \
    solo_animar=False, guion=None, animado=False: '{"ok": true}'
try:
    args, r = director._usar("crear_video", {"prompt": "un gato"}, lambda *a: None, usadas.append, "un gato", "",
                             lambda p: True, avisados.extend)
finally:
    herramientas.TODAS["crear_video"] = real_crear
assert r == '{"ok": true}' and avisados == ["Gemini no tiene saldo: usaré Groq para el texto."], avisados

# El servidor MCP: lo mismo, antes de preguntar nada; y un error de httpx le llega en claro
import mcp_server  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

guardia.ORIGEN = actividad.ORIGEN = "app"  # importar mcp_server firma este proceso como «mcp»
preguntar_real = mcp_server._preguntar
mcp_server._preguntar = lambda texto: (_ for _ in ()).throw(AssertionError("no debió preguntar"))
generar_real = desde_prompt.generar
try:
    e = falla(mcp_server.crear_video, "una manzana que habla", animado=True, error=ToolError)
    assert "No se puede hacer el video que habla: Gemini no tiene saldo" in str(e), e
    desde_prompt.generar = lambda *a, **k: (_ for _ in ()).throw(error_http)
    e = falla(mcp_server.crear_video, "un gato", error=ToolError)
    assert str(e) == "gen.pollinations.ai respondió 402: Insufficient pollen", e
finally:
    mcp_server._preguntar, desde_prompt.generar = preguntar_real, generar_real
print("Avisos antes de empezar: bien.")

# ---------- La IA de texto: cada intento queda apuntado con lo que pasó después ----------
import anthropic  # noqa: E402
import openai  # noqa: E402

pedido = httpx.Request("POST", "https://api.example/v1/chat/completions")
enviados = []  # (servicio, lo que se le mandó) de cada pedido a una IA compatible con OpenAI


class OpenAIFalso:
    def __init__(self, api_key, base_url, **k):
        self.base = base_url
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.crear))

    def crear(self, **k):
        enviados.append((self.base, k))
        if "googleapis" in self.base:
            raise openai.APIStatusError("402", body=SIN_SALDO, response=httpx.Response(402, request=pedido,
                                                                                         json=SIN_SALDO))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
            content='{"palabra": "listo"}'))], usage=types.SimpleNamespace(prompt_tokens=100, completion_tokens=10))


class ClaudeSinSaldo:  # Claude sin saldo responde 400, no 402: tampoco cobra y otra IA sí puede
    def __init__(self, **k):
        self.messages = types.SimpleNamespace(stream=self.stream)

    def stream(self, **k):
        cuerpo = {"error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access "
                                                                        "the Anthropic API."}}
        raise anthropic.APIStatusError("400", body=cuerpo, response=httpx.Response(400, request=pedido, json=cuerpo))


esquema = {"type": "object", "properties": {"palabra": {"type": "string"}}, "required": ["palabra"]}
abrir_openai, abrir_claude = openai.OpenAI, anthropic.Anthropic
openai.OpenAI, anthropic.Anthropic = OpenAIFalso, ClaudeSinSaldo
try:
    conectar(GEMINI, GROQ)
    assert ia.texto_json("i", "p", esquema) == {"palabra": "listo"}
    groq, gemini = actividad.ultimas(2)
    assert (gemini["proveedor"], gemini["resultado"], gemini["paso_a"], gemini["costo"]) == ("gemini", "fallo", "groq",
                                                                                            0.0), gemini
    assert gemini["motivo"] == "402: Your prepayment credits are depleted."
    assert (groq["proveedor"], groq["resultado"], groq["costo"]) == ("groq", "ok", 0.0), groq  # Groq: gratis
    assert claves.estados()["gemini"]["estado"] == "sin_saldo"  # el próximo trabajo ya avisa antes
    # Ya se sabe que Gemini no tiene saldo: los siguientes pedidos ni le preguntan (cada paso del Director esperaba
    # 1-3 s su 402) y van directo a Groq; en la actividad queda que se saltó y por qué, sin gastar un pedido
    enviados.clear()
    assert ia.texto_json("i", "p", esquema) == {"palabra": "listo"}
    assert [b for b, _ in enviados] == [claves.OPENAI_COMPAT["groq"]], enviados
    groq, gemini = actividad.ultimas(2)
    assert (gemini["proveedor"], gemini["resultado"], gemini["paso_a"]) == ("gemini", "fallo", "groq"), gemini
    assert gemini["motivo"].startswith("No se le pidió: Gemini no tiene saldo (comprobado hoy a las"), gemini
    assert groq["resultado"] == "ok"
    # Sin cuota (el límite por minuto) no se salta: pasa enseguida
    estado("gemini", "sin_cuota")
    enviados.clear()
    ia.texto_json("i", "p", esquema)
    assert [b for b, _ in enviados] == [claves.OPENAI_COMPAT["gemini"], claves.OPENAI_COMPAT["groq"]], enviados
    # Pasada una hora (pudo recargar) se le vuelve a pedir, y también si «Comprobar conexiones» dice que ya atiende
    for que, hace in (("sin_saldo", ia.SALTO + 60), ("ok", 0)):
        estado("gemini", que, hace)
        enviados.clear()
        ia.texto_json("i", "p", esquema)
        assert enviados[0][0] == claves.OPENAI_COMPAT["gemini"], (que, enviados)
    # Una clave NUEVA de Gemini: el «sin saldo» era de la anterior, así que se le pide (y no bloquea lo de pago).
    # Volver a guardar la misma (p. ej. con el modelo que funcionó) no lo olvida
    estado("gemini", "sin_saldo")
    claves.guardar({**GEMINI, "modelo_texto": "gemini-flash-lite-latest"})
    assert claves.estados()["gemini"]["estado"] == "sin_saldo"
    claves.guardar({**GEMINI, "clave": "AIzaSyNUEVA00000000000000000000000000"})
    assert "gemini" not in claves.estados() and claves.impide(["video_voz"]) is None
    enviados.clear()
    ia.texto_json("i", "p", esquema)
    assert enviados[0][0] == claves.OPENAI_COMPAT["gemini"], enviados
    # Un 403 que no habla de la clave (la moderación de OpenRouter) no apaga esa IA de texto; uno de la clave sí
    conectar(GEMINI, GROQ)
    for detalle, saltada in (("403: Your input was flagged by moderation", False), ("401: Invalid API Key", True),
                             ("403: API key not valid", True)):
        todos = claves.estados()
        todos["groq"] = {"estado": "clave", "detalle": detalle, "paso": "", "fecha": time.strftime("%Y-%m-%d %H:%M:%S")}
        claves.CONEXIONES.write_text(json.dumps(todos), encoding="utf-8")
        assert (ia._saltado(GROQ) is not None) == saltada, detalle
    # Sin ninguna que atienda: la gratis sin clave, y si tampoco, el motivo de la elegida en claro
    conectar(GEMINI)
    estado("gemini", "sin_saldo")
    gratis, ia._texto_gratis = ia._texto_gratis, lambda *a: (_ for _ in ()).throw(RuntimeError("sin red"))
    enviados.clear()
    try:
        error = falla(ia.texto_json, "i", "p", esquema, error=ia.SinServicio)
    finally:
        ia._texto_gratis = gratis
    assert str(error).startswith("Gemini no tiene saldo. Recarga en AI Studio") and enviados == [], error
    # La ortografía tampoco espera a una IA sin saldo: el aviso del trabajo lo dice y queda en la actividad
    notas = []
    assert ia.ortografia(["Miren que bien"], "es", notas) == ["Miren que bien"] and enviados == []
    assert notas == ["No se pudo repasar la ortografía (Gemini: Gemini no tiene saldo. Recarga en AI Studio: "
                     "aistudio.google.com → tu proyecto → Billing.)."], notas
    assert actividad.ultimas(1)[0]["motivo"].startswith("No se le pidió: Gemini no tiene saldo")
    # El Director y entender un pedido, sin el razonamiento escondido de Qwen en Groq (lo que más tardaba); los
    # guiones, con él. Un modelo que no deja apagarlo responde 400: se repite como siempre, sin fallar
    conectar(GROQ)
    enviados.clear()
    ia.texto_json("i", "p", esquema, rapido=True)
    ia.texto_json("i", "p", esquema)
    assert [k.get("extra_body") for _, k in enviados] == [{"reasoning_effort": "none"}, None], enviados
    assert ia._sin_razonar("groq", "openai/gpt-oss-120b") == {"reasoning_effort": "low"}
    assert ia._sin_razonar("groq", "llama-3.3-70b-versatile") == ia._sin_razonar("gemini", "qwen3") == {}
    crear_real = OpenAIFalso.crear

    def no_admite(self, **k):
        if (k.get("extra_body") or {}).get("reasoning_effort"):
            enviados.append((self.base, k))
            cuerpo = {"error": {"message": "reasoning_effort is not supported with this model"}}
            raise openai.APIStatusError("400", body=cuerpo, response=httpx.Response(400, request=pedido, json=cuerpo))
        return crear_real(self, **k)
    OpenAIFalso.crear = no_admite
    try:
        enviados.clear()
        assert ia.texto_json("i", "p", esquema, rapido=True) == {"palabra": "listo"}
        assert [k.get("extra_body") for _, k in enviados] == [{"reasoning_effort": "none"}, None], enviados
    finally:
        OpenAIFalso.crear = crear_real
    # Sin pensar respondió a medias: la otra vez, pensando (con toda su calidad). Y el 400 de un modelo que no deja
    # apagarlo no se gasta el reintento: 400, una a medias y una buena salen bien

    def responde(*contenidos, rechaza=False):
        cola = list(contenidos)

        def crear(self, **k):
            enviados.append((self.base, k))
            if rechaza and (k.get("extra_body") or {}).get("reasoning_effort"):
                cuerpo = {"error": {"message": "reasoning_effort is not supported with this model"}}
                raise openai.APIStatusError("400", body=cuerpo, response=httpx.Response(400, request=pedido,
                                                                                          json=cuerpo))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
                content=cola.pop(0)))], usage=types.SimpleNamespace(prompt_tokens=100, completion_tokens=10))
        return crear
    try:
        for rechaza in (False, True):
            OpenAIFalso.crear = responde('{"pala', '{"palabra": "listo"}', rechaza=rechaza)
            enviados.clear()
            assert ia.texto_json("i", "p", esquema, rapido=True) == {"palabra": "listo"}
            esperado = [{"reasoning_effort": "none"}, None] + ([None] if rechaza else [])
            assert [k.get("extra_body") for _, k in enviados] == esperado, (rechaza, enviados)
    finally:
        OpenAIFalso.crear = crear_real
    conectar(CLAUDE, GROQ)
    assert ia.texto_json("i", "p", esquema) == {"palabra": "listo"}
    groq, claude = actividad.ultimas(2)
    assert claude["proveedor"] == "anthropic" and claude["paso_a"] == "groq" and "credit balance" in claude["motivo"]
    assert claves.estados()["anthropic"]["estado"] == "sin_saldo"
    # De pago y con respuesta: su costo con los tokens que dice el servicio
    conectar({**GROQ, "proveedor": "openai", "clave": "sk-proj-PRUEBA"})
    ia.texto_json("i", "p", esquema)
    assert abs(actividad.ultimas(1)[0]["costo"] - ia.costo_texto("openai", 100, 10)) < 1e-12
    assert ia.costo_texto("openai", 100, 10) == (100 * 2.5 + 10 * 15.0) / 1_000_000
finally:
    openai.OpenAI, anthropic.Anthropic = abrir_openai, abrir_claude
print("IA de texto apuntada: bien.")

# ---------- Imágenes: cada intento de la rotación, con lo que pasó después ----------
conectar({"proveedor": "cloudflare", "clave": "0123456789abcdef0123456789abcdef " + "T" * 40, "usos": ["imagen"]},
         POLLI)
cuota = respuesta(429, {"errors": [{"message": "you used your 10,000 neurons"}]}, "POST")
datos, quien = nubes.rotar("imagen", {
    "cloudflare": lambda: cuota.raise_for_status(), "pollinations": lambda: b"png"},
    que_fue=lambda p: ("zimage", 0.0) if p == "pollinations" else ("flux-1-schnell", 0.0))
assert (datos, quien) == (b"png", "pollinations")
polli, cf = actividad.ultimas(2)
assert cf["resultado"] == "fallo" and cf["paso_a"] == "pollinations" and "cuota gratis" in cf["motivo"], cf
assert polli["resultado"] == "ok" and polli["modelo"] == "zimage"

# Edición con referencia sin saldo (Pollinations Kontext, 402): un error en claro, sin el texto de httpx
foto = tmp / "foto.png"
foto.write_bytes(b"\x89PNG\r\n\x1a\n")
claves.elegir_por_defecto("imagen", "pollinations")
assert ia.puede_referencia()
ediciones = []
httpx.post = lambda url, **k: ediciones.append(url) or respuesta(402, "Payment Required", "POST", url)
try:
    e = falla(ia.imagen_con_producto, "a cat", foto, 64, 64, tmp / "e.png", respaldo=False, error=RuntimeError)
    assert str(e) == "Pollinations respondió 402: Payment Required" and "mozilla" not in str(e), e
    assert actividad.ultimas(1)[0]["resultado"] == "fallo" and "402" in actividad.ultimas(1)[0]["motivo"]
    # Con respaldo (Crear con foto, Anuncios): la escena sale igual, con la foto sobre un fondo nuevo, y se dice una
    # sola vez aunque fallen varias escenas igual
    from motor import anuncios, video  # noqa: E402
    fondos, avisos = [], []
    NOTA = ("La edición con la imagen de referencia falló (Pollinations respondió 402: Payment Required): la escena se "
            "hizo con la foto encima de un fondo nuevo.")
    imagen_real, ffmpeg_real, cierre_real = ia.imagen, video.ffmpeg, video.cierre
    montar_real, proyectos_real = anuncios.montar, anuncios.PROYECTOS
    ia.imagen = lambda p, w, h, d, calidad="1K": fondos.append(p) or d
    video.ffmpeg = lambda *a, **k: None
    try:
        for n in (2, 3):
            assert ia.imagen_con_producto("a cat", foto, 64, 64, tmp / f"e{n}.png", avisos=avisos) == tmp / f"e{n}.png"
        assert len(fondos) == 2 and avisos == [NOTA], avisos
        # Anuncios también lo dice (antes la escena salía con la foto pegada y solo quedaba en la actividad)

        def montar_falso(v, carpeta, formato, voz, aviso, nombre, crear_imagen, **k):
            for i, e in enumerate(v["escenas"]):
                crear_imagen(f"{e['imagen']}, {v['estilo_visual']}", 64, 64, carpeta / f"{nombre}_{i}.png")
            return carpeta / f"{nombre}.mp4"
        plan = {"variantes": [{"angulo": "Antojo", "gancho": "g", "titulo": "Café", "texto_anuncio": "x",
                               "hashtags": [], "estilo_visual": "photo",
                               "escenas": [{"narracion": "n", "imagen": "the product on a table"}] * 3}]}
        anuncios.montar, anuncios.PROYECTOS, ia.texto_json = montar_falso, tmp / "anuncios", lambda *a, **k: plan
        video.cierre = lambda montado, texto, formato, destino, **k: montado
        p = anuncios.crear(str(foto), "Café", "d", "gente", "", "UGC", variantes=1)
        assert p["avisos"][-1:] == [f"Anuncio 1: {NOTA}"], p["avisos"]
    finally:
        ia.imagen, video.ffmpeg, video.cierre, ia.texto_json = imagen_real, ffmpeg_real, cierre_real, real_texto
        anuncios.montar, anuncios.PROYECTOS = montar_real, proyectos_real

    # La edición de pago ya respondió bien y lo que falla es después (la imagen no vale, el disco): ya se cobró. Nunca
    # se paga otra imagen por detrás (Cobrado), y la actividad cuenta su costo
    no_es_imagen = base64.b64encode(b"<html>no es una imagen</html>").decode()
    httpx.post = lambda url, **k: respuesta(200, {"data": [{"b64_json": no_es_imagen}]}, "POST", url)
    conectar({**OPENAI, "usos": ["texto", "imagen"], "modelo_imagen": "gpt-image-1"}, imagen="openai")
    ia.imagen, fondos = (lambda *a, **k: fondos.append(a) or a[3]), []
    try:
        e = falla(ia.imagen_con_producto, "a cat", foto, 64, 64, tmp / "e4.png", avisos=avisos, error=ia.Cobrado)
        assert str(e) == "no devolvió una imagen" and not fondos, (e, fondos)
        apunte = actividad.ultimas(1)[0]
        assert (apunte["proveedor"], apunte["resultado"], apunte["costo"]) == ("openai", "fallo",
                                                                               ia.PRECIO_EDITAR_OPENAI), apunte
        # Gemini (Nano Banana) igual, con su precio; y los dibujos de una serie tampoco se pagan dos veces
        conectar({**GEMINI, "usos": ["texto", "imagen", "musica"]}, imagen="gemini")
        ia._elegidos[(GEMINI["clave"], claves.elegir_modelo_imagen_gemini)] = ia.IMAGEN_GEMINI
        httpx.post = lambda url, **k: respuesta(200, {"candidates": [{"content": {"parts": [{"inlineData": {
            "data": no_es_imagen}}]}}]}, "POST", url)
        falla(ia.imagen_con_producto, "a cat", foto, 64, 64, tmp / "e5.png", avisos=avisos, error=ia.Cobrado)
        assert actividad.ultimas(1)[0]["costo"] == ia.PRECIO_IMAGEN_GEMINI[ia.IMAGEN_GEMINI]["1K"]
        (tmp / "serie2" / "personajes").mkdir(parents=True)
        (tmp / "serie2" / "personajes" / "p3.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        falla(serie._dibujar, tmp / "serie2", {"ref": {"id": "p3", "nombre": "Don Tito"}}, "x", 64, 64,
              tmp / "p1.png", {}, 1, error=ia.Cobrado)
        assert not fondos and avisos == [NOTA], (fondos, avisos)  # ni fondo, ni dibujo sin lámina, ni otra nota
    finally:
        ia.imagen = imagen_real
    conectar(POLLI, imagen="pollinations")
    httpx.post = lambda url, **k: ediciones.append(url) or respuesta(402, "Payment Required", "POST", url)

    # Dibujos animados: el plano se dibuja igual sin su lámina (antes repetía el anterior) y los siguientes ya no la
    # intentan (fallaría igual)
    carpeta = tmp / "serie"
    (carpeta / "personajes").mkdir(parents=True)
    (carpeta / "personajes" / "p3.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    escena = {"ref": {"id": "p3", "nombre": "Don Tito"}}
    dibujados, sin_lamina = [], {}
    ia.imagen = lambda p, w, h, d, calidad="1K": dibujados.append(p) or d
    try:
        ediciones.clear()
        for plano in (6, 7):
            assert serie._dibujar(carpeta, escena, "Don Tito in his shop", 64, 64, tmp / f"p{plano}.png", sin_lamina,
                                  plano) == tmp / f"p{plano}.png"
    finally:
        ia.imagen = imagen_real
    assert len(ediciones) == 1 and len(dibujados) == 2, (ediciones, dibujados)
    assert sin_lamina == {"motivo": "Pollinations respondió 402: Payment Required", "planos": [6, 7]}, sin_lamina
finally:
    httpx.post = sin_red
print("Imágenes y su respaldo: bien.")

# ---------- Música: Gemini sin saldo (402) pasa a ElevenLabs en automático, con su costo, y sin cobrar dos veces ----------
conectar(GEMINI, ELEVEN)
CANCION = {"titulo": "Viernes", "estilo": "hard 808s", "letra": "[Chorus]\nDale", "descripcion": "d", "hashtags": []}
llamadas = []


def post_musica(url, **k):
    llamadas.append(url)
    if "googleapis" in url:
        return respuesta(402, SIN_SALDO, "POST", url)
    return respuesta(200, b"ID3audio", "POST", url)


# La ortografía se repasa con su propia llamada de texto: aquí no cuenta (ni debe pisar el estado «sin saldo»)
ortografia_real, ia.ortografia = ia.ortografia, lambda textos, *a, **k: list(textos)
ia.texto_json, httpx.post = (lambda *a, **k: dict(CANCION)), post_musica
try:
    p = musica.crear("un dembow de viernes", "Dembow moderno")
    assert Path(p["resultados"][0]["archivo"]).read_bytes() == b"ID3audio"
    assert len(llamadas) == 2 and "googleapis" in llamadas[0] and "elevenlabs" in llamadas[1]  # una vez cada uno
    assert p["avisos"] == [f"Gemini no tiene saldo para Lyria (no cobró nada): esta canción se hizo con tu clave de "
                           f"ElevenLabs, hasta unos {dinero(musica.PRECIO['elevenlabs'])}. Recarga en AI Studio: "
                           f"aistudio.google.com → tu proyecto → Billing."], p["avisos"]
    eleven, gemini = actividad.ultimas(2)
    assert (gemini["proveedor"], gemini["que"], gemini["resultado"], gemini["costo"]) == ("gemini", "musica", "fallo",
                                                                                          0.0)
    assert (eleven["proveedor"], eleven["resultado"], eleven["costo"]) == ("elevenlabs", "ok",
                                                                           musica.PRECIO["elevenlabs"])
    assert claves.estados()["gemini"]["estado"] == "sin_saldo"
    # Gemini elegido a mano: no pasa a otro de pago y el error dice qué hacer, en claro
    claves.elegir_por_defecto("musica", "gemini")
    llamadas.clear()
    musica.PROYECTOS = tmp / "proyectos_a_mano"  # otra carpeta: van en el mismo segundo
    e = falla(musica.crear, "otra", "Dembow moderno", error=RuntimeError)
    assert "Gemini no tiene saldo para Lyria (402)" in str(e) and "mozilla" not in str(e) and len(llamadas) == 1, e
    # Fallan los dos: el motivo de ElevenLabs también en claro (no «[Errno 11001] getaddrinfo failed»)
    claves.elegir_por_defecto("musica", "auto")
    musica.PROYECTOS = tmp / "proyectos_sin_red"

    def post_sin_eleven(url, **k):
        if "googleapis" in url:
            return respuesta(402, SIN_SALDO, "POST", url)
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed", request=httpx.Request("POST", url))
    httpx.post = post_sin_eleven
    e = falla(musica.crear, "otra más", "Dembow moderno", error=RuntimeError)
    assert "Sin conexión con api.elevenlabs.io" in str(e) and "getaddrinfo" not in str(e), e
finally:
    ia.texto_json, httpx.post, ia.ortografia = real_texto, sin_red, ortografia_real
print("Música sin saldo: bien.")

# ---------- Video que habla (Omni) sin saldo: dicho claro, con su costo, sin cobrar y sin pedir las demás escenas ----
conectar(GEMINI)
ia._elegidos[(GEMINI["clave"], claves.elegir_modelo_video_voz)] = ia.OMNI  # sin preguntar a la red qué modelos tiene
omni = []
httpx.post = lambda url, **k: omni.append(url) or respuesta(402, SIN_SALDO, "POST", url)
try:
    e = falla(ia.video_hablado, "una manzana dice hola", "9:16", tmp / "omni.mp4", error=ia.SinSaldo)
finally:
    httpx.post = sin_red
assert str(e).startswith("Gemini no tiene saldo: no hizo el video que habla y no se cobró nada. Cada escena que habla "
                         f"cuesta hasta unos {dinero(ia.precio_video('gemini', voz=True))}.") and \
    "aistudio.google.com" in str(e) and "Your prepayment credits are depleted." in str(e), e
assert len(omni) == 1 and claves.estados()["gemini"]["estado"] == "sin_saldo"
hablado = actividad.ultimas(1)[0]
assert (hablado["que"], hablado["resultado"], hablado["costo"]) == ("video", "fallo", 0.0), hablado
# En un trabajo: la escena que dio «sin saldo» para a las demás (fallarían igual); cada hilo deja de pedir
pedidas = []


def sin_saldo_omni(*a, **k):
    pedidas.append(1)
    time.sleep(0.05)
    raise ia.SinSaldo("Gemini no tiene saldo")


hablado_real, ia.video_hablado = ia.video_hablado, sin_saldo_omni
try:
    guion = {"estilo_visual": "cartoon", "escenas": [{"narracion": f"frase {i}", "imagen": f"scene {i}"}
                                                    for i in range(6)]}
    notas = []
    hechos = desde_prompt.clips_hablados(guion, tmp, "9:16", lambda *a: None, None, notas, quien="gemini")
finally:
    ia.video_hablado = hablado_real
assert hechos == {} and 1 <= len(pedidas) <= 3, len(pedidas)  # como mucho las 3 que iban a la vez; las otras, no
assert notas == ["Las escenas 1, 2, 3, 4, 5, 6 no salieron animadas con voz (Gemini no tiene saldo). Se hicieron con "
                 "imagen y narración."], notas
print("Video que habla sin saldo: bien.")

# ---------- La página «Claves de IA»: estados, «Comprobar conexiones» y la actividad ----------
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from ui import comun  # noqa: E402
from ui.paginas import claves as pagina_claves  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»


def esperar(condicion, plazo=10):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


conectar(GEMINI, GROQ, OPENAI, {"proveedor": "cloudflare", "clave": "0123456789abcdef0123456789abcdef " + "T" * 40,
                                "usos": ["imagen"]})
estado("gemini", "sin_saldo")
estado("groq", "ok")
estado("openai", "clave_ok")
actividad.anotar("texto", "gemini", "gemini-flash-latest", error="402: Your prepayment credits are depleted.",
                 paso_a="groq")
actividad.anotar("musica", "elevenlabs", "music_v2_5", 0.45)
pagina = pagina_claves.PaginaClaves()
assert (pagina.estados["gemini"].text(), pagina.estados["groq"].text(), pagina.estados["cloudflare"].text(),
        pagina.estados["huggingface"].text()) == ("Sin saldo", "Funciona", "Conectada", "No conectada")
assert "#FF4D8D" in pagina.estados["gemini"].styleSheet() and "#3DDC97" in pagina.estados["groq"].styleSheet()
assert "Comprobar conexiones" in pagina.estados["cloudflare"].toolTip()  # sin comprobar todavía
assert "Recarga en AI Studio" in pagina.estados["gemini"].toolTip()
# OpenAI: la clave vale, pero su saldo no se ve sin usarla: ni «Funciona» en verde ni un paso que dar
assert pagina.estados["openai"].text() == "La clave vale" and "#A9A9B6" in pagina.estados["openai"].styleSheet()
assert pagina.estados["openai"].toolTip().startswith("Su saldo solo se ve al usarla: si se acaba, la actividad de la "
                                                     "IA lo dice.\ncomprobado hoy a las ")
assert not pagina.pasos.isHidden() and pagina.pasos.text() == ("⚠️ Gemini no tiene saldo. Recarga en AI Studio: "
                                                               "aistudio.google.com → tu proyecto → Billing.")
assert pagina.comprobado.text().startswith("Comprobado hoy a las ")
assert pagina.gasto.text() == "Gasto estimado de hoy: ElevenLabs US$0.45\nEste mes: ElevenLabs US$0.45"
assert pagina.tabla.rowCount() == 2 and pagina.sin_actividad.isHidden()
fila = [pagina.tabla.item(0, c).text() for c in range(6)]
assert fila[1:] == ["sin tarea", "música", "ElevenLabs", "US$0.45", "salió bien"], fila
fila = [pagina.tabla.item(1, c).text() for c in range(6)]
assert fila[2:] == ["texto", "Gemini", "no se cobró",
                    "falló: 402: Your prepayment credits are depleted. · pasó a Groq"], fila
# El botón: comprueba en otro hilo (la ventana no se congela) y pinta lo nuevo
suelta, comprobadas = threading.Event(), []


def comprobar_falso(proveedores=None):
    comprobadas.append((proveedores, threading.current_thread().daemon))  # daemon: cerrar la app no la espera
    suelta.wait(10)
    estado("gemini", "ok")
    return {"gemini": claves.estados()["gemini"]}


comprobar_real, claves.comprobar = claves.comprobar, comprobar_falso
errores, error_real = [], pagina_claves.mensaje_error
pagina_claves.mensaje_error = lambda *a: errores.append(a)
try:
    pagina.comprobar.click()
    assert not pagina.comprobar.isEnabled() and pagina.comprobar.text() == "Comprobando…"
    assert pagina.estados["gemini"].text() == "Comprobando…"
    pagina.comprobar_ahora()  # una sola a la vez
    suelta.set()
    esperar(lambda: pagina.comprobar.isEnabled())
    assert comprobadas == [(None, True)] and pagina.estados["gemini"].text() == "Funciona" and pagina.pasos.isHidden()
    assert pagina.comprobar.text() == "Comprobar conexiones"
    # La de cuando se abre la app: si falla, ninguna ventana (se ve en su pastilla y se repite con el botón)
    claves.comprobar = lambda proveedores=None: (_ for _ in ()).throw(RuntimeError("sin red"))
    pagina.comprobar_ahora(al_abrir=True)
    esperar(lambda: pagina.comprobar.isEnabled())
    assert errores == []
    pagina.comprobar_ahora()
    esperar(lambda: pagina.comprobar.isEnabled() and errores)
    assert errores[0][1] == "No se pudo comprobar" and errores[0][2] == "sin red"
    conectar()  # sin claves no hay nada que comprobar
    pagina.comprobar_ahora()
    assert pagina.comprobar.isEnabled()
    pagina._refrescar()
    assert pagina.tabla.isHidden() and not pagina.sin_actividad.isHidden()
finally:
    claves.comprobar, pagina_claves.mensaje_error = comprobar_real, error_real
# Conectar desde la página: el título de la ventana es el motivo de verdad, no «Clave no válida» para todo
errores, avisos, mensaje_real = [], [], pagina_claves.mensaje
pagina_claves.mensaje_error = lambda *a: errores.append(a)
pagina_claves.mensaje = lambda *a: avisos.append(a)
try:
    for clave, get, titulo in (("hola", sin_red, "Formato no reconocido"),
                               (ELEVEN["clave"], eleven_falso(httpx.ConnectError("x")), "Sin conexión"),
                               (ELEVEN["clave"], eleven_falso(NO_VALE), "Clave no válida"),
                               (ELEVEN["clave"], eleven_falso(PROHIBIDO), "Falta un permiso"),
                               (CLAVE_OPENAI, openai_sin_scopes, "Falta un permiso"),
                               (TOKEN_CF, lambda url, **k: respuesta(401), "Clave no válida")):
        httpx.get = get
        pagina.entrada.setText(clave)
        pagina._conectar()
        esperar(lambda: errores and pagina.conectar.isEnabled())
        assert errores.pop()[1] == titulo and not errores, titulo
    # Sin «Voices: Read»: queda conectada (sin el aviso dentro de claves.json) y se dice qué pasa con sus voces
    httpx.get = eleven_falso(respuesta(200, []), sin_permiso(SIN_VOCES))
    pagina.entrada.setText(ELEVEN["clave"])
    pagina._conectar()
    esperar(lambda: avisos and pagina.conectar.isEnabled())
    assert avisos[0][1] == "Falta un permiso" and "«Voices: Read»" in avisos[0][2] and not errores, avisos
    assert claves.cargar()["elevenlabs"]["voces"] == [] and "aviso" not in claves.cargar()["elevenlabs"]
    assert pagina.entrada.text() == ""
finally:
    httpx.get, pagina_claves.mensaje_error, pagina_claves.mensaje = sin_red, error_real, mensaje_real
# Cerrar la app con la comprobación del arranque aún en marcha (Modal tarda hasta 60 s; Gemini, hasta 40): sale enseguida
# y sin caerse. Con un QThread vivo salía con 0xC0000409 («QThread destroyed while running»)
conectar(GROQ)
cierre = subprocess.run([sys.executable, "-s", "-E", "-c", """if True:
    import sys, time
    from pathlib import Path
    import httpx
    import pruebas  # sus archivos de prueba: nada del dueño
    from motor import claves
    claves.ARCHIVO, claves.AJUSTES = Path(sys.argv[1]), Path(sys.argv[2])
    httpx.get = httpx.post = lambda *a, **k: sys.exit("salió a la red")
    claves.comprobar = lambda proveedores=None: time.sleep(30) or {}
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from ui.paginas.claves import PaginaClaves
    app = QApplication(sys.argv)
    pagina = PaginaClaves()
    pagina.comprobar_ahora(al_abrir=True)
    QTimer.singleShot(300, app.quit)
    sys.exit(app.exec())
""", str(claves.ARCHIVO), str(claves.AJUSTES)], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=60, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
assert cierre.returncode == 0, (cierre.returncode, cierre.stderr[-2000:])

# Crear: con lo último comprobado, lo de pago imposible ni empieza (ni se pregunta su costo), y lo que pasa a otro
# servicio se dice antes y se queda a la vista
from ui.paginas.crear import PaginaCrear  # noqa: E402

conectar(GEMINI, GROQ)
estado("gemini", "sin_saldo")
crear = PaginaCrear()
errores, preguntas = [], []
error_real, pregunta_real = comun.mensaje_error, QMessageBox.question
comun.mensaje_error = lambda *a: errores.append(a)
QMessageBox.question = lambda *a: preguntas.append(a) or QMessageBox.No
generar_real = desde_prompt.generar
desde_prompt.generar = lambda **k: (_ for _ in ()).throw(RuntimeError("de mentira"))
try:
    assert crear.lanzar(crear.iniciar, desde_prompt.generar, prompt="x", segundos=45, animado=True) is False
    assert crear.tarea is None and not preguntas and errores[0][1] == "No se puede empezar"
    assert errores[0][2].startswith("No se puede hacer el video que habla: Gemini no tiene saldo")
    assert crear.lanzar(crear.iniciar, desde_prompt.generar, prompt="x", segundos=45, animado=False) is True
    assert crear.antes.text() == "⚠️ Gemini no tiene saldo: usaré Groq para el texto." and not crear.antes.isHidden()
    esperar(lambda: not crear.tarea.isRunning() and len(errores) == 2)
    estado("gemini", "ok")
    assert crear.lanzar(crear.iniciar, desde_prompt.generar, prompt="x", segundos=45) is True
    assert crear.antes.isHidden()
    esperar(lambda: not crear.tarea.isRunning() and len(errores) == 3)
finally:
    comun.mensaje_error, QMessageBox.question, desde_prompt.generar = error_real, pregunta_real, generar_real
httpx.get, httpx.post = reales["get"], reales["post"]
print("Pruebas de conexiones y actividad de la IA pasadas.")
