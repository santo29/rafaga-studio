"""Lo que escribe una IA llega limpio a donde el usuario lo ve, lo oye o lo publica: sin Markdown (**, #, listas,
`código`, tablas, [enlaces](url)), sin entidades HTML ni «\\n» escritos como texto, y los errores de los servicios
sin JSON crudo. Sin red: las respuestas de la IA, la voz y YouTube son de mentira, pero pasan por las funciones de
verdad. python -m pruebas.textos"""
import json
import os
import tempfile
import types
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")

import httpx  # noqa: E402

from motor import claves, desde_prompt, director, guardia, ia, memoria, musica, publicar, seguro, voz  # noqa: E402
from motor.idioma import dinero, porcentaje, texto_de_error  # noqa: E402

s = ia.sin_markdown

# ---------- El limpiador común ----------
casos = [
    ("texto", "## Título\nUn video sobre gatos:\n* punto uno\n- punto dos\nMás en [mi web](https://ejemplo.com)",
     "Título\nUn video sobre gatos:\n• punto uno\n• punto dos\nMás en mi web: https://ejemplo.com"),
    ("voz", "**¡Oye!** Mira esto:\n* punto uno\n* punto dos", "¡Oye! Mira esto: punto uno. punto dos."),
    ("voz", "### El secreto\nSoy un _gato_ 😺 y hablo\\ncontigo &amp; tus amigos.",
     "El secreto. Soy un gato y hablo. contigo & tus amigos."),
    ("voz", "Visita [mi web](https://ejemplo.com) y usa `#viral` 🔥", "Visita mi web y usa viral."),
    ("texto", "**¡Listo!** Hice tu video:\n* 45 segundos\n### Siguiente paso\nMíralo en `Crear`.",
     "¡Listo! Hice tu video:\n• 45 segundos\nSiguiente paso\nMíralo en Crear."),
    ("linea", "**Gatos que hablan** | Episodio 1", "Gatos que hablan | Episodio 1"),
    ("linea", "**PIZZA 2x1**", "PIZZA 2x1"),
    ("texto", "| Nicho | Vistas |\n|---|---|\n| Gatos | 1M |", "Nicho · Vistas\n\nGatos · 1M"),
    ("texto", "**[Chorus]**\nDale que dale\n[Verse 1]", "[Chorus]\nDale que dale\n[Verse 1]"),
    # lo que NO se toca: tipografía española, hashtags, huecos de diseño, emojis fuera de la voz, nombres_con_guion
    ("texto", "«Hola» ¿Qué tal? ¡Oferta 2x1! Dembow · 2026 🚀 [Precio] #viral #gatos 5 * 3 mi_archivo_nuevo 3-4 años",
     "«Hola» ¿Qué tal? ¡Oferta 2x1! Dembow · 2026 🚀 [Precio] #viral #gatos 5 * 3 mi_archivo_nuevo 3-4 años"),
    ("voz", "A 25°C, 50% más. 1. Primero 2. Segundo", "A 25°C, 50% más. 1. Primero 2. Segundo."),
    ("texto", "Línea uno\n\n\n\nLínea dos   ", "Línea uno\n\nLínea dos"),
    ("texto", "Tranquilo.<br>No pasa nada &quot;de verdad&quot;", "Tranquilo.\nNo pasa nada \"de verdad\""),
    ("linea", "Mi <video> y <b>negrita</b>", "Mi <video> y negrita"),  # solo las etiquetas de formato
    ("texto", "```json\n{\"a\": 1}\n```\n> cita\n---\nfin", "{\"a\": 1}\ncita\n\nfin"),  # la raya: un respiro
]
for para, entrada, esperado in casos:
    assert s(entrada, para) == esperado, (para, entrada, s(entrada, para))
assert s(None) == "" and s(42) == "42"
# Un texto que es JSON (los «argumentos» del Director) no se toca: limpiarlo lo rompería
assert ia._limpio({"mensaje": "**a**", "argumentos": '{"t": "**b**\\n"}', "lista": ["`c`"], "n": 3}) == \
    {"mensaje": "a", "argumentos": '{"t": "**b**\\n"}', "lista": ["c"], "n": 3}
assert ia.hashtag("comida dominicana") == "#comidadominicana" and ia.hashtag("**#viral**") == "#viral"
assert ia.hashtag("#Año nuevo") == "#Añonuevo"
assert ia.recortar("hola mundo cruel", 12) == "hola mundo…" and ia.recortar("hola", 12) == "hola"
assert ia.recortar("palabralarguísima sin fin", 10) == "palabrala…" and ia.recortar("uno dos tres", 7) == "uno…"
assert "Markdown" in ia.TEXTO_PLANO and "emojis" in ia.TEXTO_PLANO
# Cada herramienta tiene su nombre para el usuario (ventanas del MCP, historial de Guardia, progreso del Director)
assert set(director.herramientas.NOMBRES) == set(director.herramientas.TODAS)
assert director.herramientas.nombre("crear_video") == "crear un video"
# Una lista donde va un texto: un punto por línea, no JSON; y las redes escritas como texto no se parten
nicho = {"type": "object", "properties": {"viral": {"type": "string"}, "redes": {"type": "array", "items": {"type": "string"}}}}
assert ia._normalizar({"viral": ["Mucho público", "Poca competencia"], "redes": "Instagram Reels, YouTube Shorts"},
                      nicho) == {"viral": "• Mucho público\n• Poca competencia", "redes": ["Instagram Reels", "YouTube Shorts"]}
assert ia._normalizar("#a #b", nicho["properties"]["redes"]) == ["#a", "#b"]
# Números y dinero como se escriben en cada idioma
assert dinero(0.364) == "US$0.36" and porcentaje(0.45) == "45\u00a0%"

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    d = Path(d)
    reales = (claves.ARCHIVO, claves.AJUSTES, memoria.ARCHIVO, guardia.ARCHIVO, musica.PROYECTOS, seguro.pedir,
              desde_prompt._voz, desde_prompt.narrar, voz.CARPETA, musica._elevenlabs, ia.texto_json)
    claves.ARCHIVO, claves.AJUSTES = d / "claves.json", d / "ajustes.json"
    memoria.ARCHIVO, guardia.ARCHIVO, musica.PROYECTOS, voz.CARPETA = (d / "memoria.json", d / "guardia.json",
                                                                       d / "proyectos", d / "voz")
    try:
        # ---------- La IA gratis responde con Markdown: texto_json lo devuelve limpio ----------
        enviados = []

        def responde(contenido):
            def pedir(metodo, url, **k):
                enviados.append(k["json"])
                return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(contenido)}}]})
            return pedir

        seguro.pedir = responde({"titulo": "**Gatos que hablan**", "descripcion": "## Gatos\n* uno\n* dos",
                                 "hashtags": ["**#gatos**"]})
        esquema = {"type": "object", "properties": {"titulo": {"type": "string"}, "descripcion": {"type": "string"},
                                                    "hashtags": {"type": "array", "items": {"type": "string"}}},
                   "required": ["titulo", "descripcion", "hashtags"]}
        r = ia.texto_json("Eres guionista.", "un video de gatos", esquema)
        assert r == {"titulo": "Gatos que hablan", "descripcion": "Gatos\n• uno\n• dos", "hashtags": ["#gatos"]}, r
        assert ia.TEXTO_PLANO in enviados[-1]["messages"][0]["content"]  # y se le pide texto plano

        # ---------- Música: la letra y el texto para publicar ----------
        claves.guardar({"proveedor": "elevenlabs", "clave": "sk_x", "usos": ["voz", "musica"], "modelo_musica": "m"})
        musica._elevenlabs = lambda c, estilo, letra, segundos: b"ID3audio"
        seguro.pedir = responde({"titulo": "**Viernes**", "estilo": "hard 808s",
                                 "letra": "**[Chorus]**\n* Dale que dale\n### Verse 1\nEsto es _flow_",
                                 "descripcion": "Nueva canción 🔥\n**Escúchala** ya", "hashtags": ["comida dominicana"]})
        p = musica.crear("dembow del viernes", "Dembow", segundos=30)
        letra = (Path(p["carpeta"]) / "letra.txt").read_text(encoding="utf-8")
        assert letra == "Viernes\n\n[Chorus]\nDale que dale\nVerse 1\nEsto es flow", letra
        assert p["resultados"][0]["descripcion"] == "Nueva canción 🔥\nEscúchala ya\n\nDale que dale\nVerse 1\nEsto es flow"
        assert "[Chorus]" not in p["resultados"][0]["descripcion"] and p["titulo"] == "Viernes"

        # ---------- La voz y sus subtítulos: solo palabras ----------
        oido = []

        async def voz_falsa(texto, voz_id, destino):
            oido.append(texto)
            return [{"palabra": w, "inicio": 0, "fin": 0} for w in texto.split()]
        desde_prompt._voz = voz_falsa
        palabras = desde_prompt.narrar("**¡Oye!** Mira esto:\n* punto uno\n### El secreto\nVisita [mi web]"
                                       "(https://ejemplo.com) y usa `#viral` 🔥 &amp; _ojo_", "es-DO-EmilioNeural", d / "v.mp3")
        assert oido[-1] == "¡Oye! Mira esto: punto uno. El secreto. Visita mi web y usa viral & ojo.", oido[-1]
        assert not any(c in " ".join(w["palabra"] for w in palabras) for c in "*#_`[]()|\\"), palabras
        # Lo que dice el Director: de una ruta, solo el nombre; los dólares, como se dicen
        dichos = []
        desde_prompt.narrar = lambda texto, voz_id, destino: dichos.append(texto) or []
        voz.hablar("Esto sube el video C:\\Users\\King\\Desktop\\Ráfaga Studio\\proyectos\\x\\video final.mp4 a tu "
                   "canal. Esto cuesta unos US$0.36. Y esto unos US$12.20.")
        assert dichos[-1] == ("Esto sube el video video final.mp4 a tu canal. Esto cuesta unos 36 centavos de dólar. "
                              "Y esto unos 13 dólares."), dichos[-1]
        assert voz.para_decir("Listo… Mira el video.mp4.") == "Listo… Mira el video.mp4."  # sin ruta, nada cambia

        # ---------- El Director: el chat sin Markdown y sin cortar palabras ----------
        ia.texto_json = lambda instrucciones, pedido, esquema, **k: {
            "mensaje": "**¡Listo!** Hice tu video:\n* 45 segundos\n### Siguiente paso\nMíralo en `Crear` o en "
                       "[YouTube](https://youtu.be/abc).", "herramienta": "", "argumentos": "{}"}
        r = director.dirigir("hazme un video")
        assert r["mensaje"] == ("¡Listo! Hice tu video:\n• 45 segundos\nSiguiente paso\nMíralo en Crear o en YouTube: "
                                "https://youtu.be/abc."), r["mensaje"]
        ia.texto_json = lambda instrucciones, pedido, esquema, **k: {"mensaje": "palabra " * 200, "herramienta": "",
                                                                 "argumentos": "{}"}
        largo = director.dirigir("algo")["mensaje"]
        assert len(largo) <= 600 and largo.endswith("palabra…"), largo[-30:]

        # ---------- YouTube: lo que se pregunta es lo que se publica, sin Markdown ----------
        args = {"archivo": "C:/x/gatos.mp4", "titulo": "**Gatos que hablan** | Episodio 1",
                "descripcion": "## Gatos\n**El mejor video** de gatos:\n- uno\n- dos\n[Suscríbete](https://y.t)\n#gatos",
                "fecha_hora": "2026-11-01T18:00"}
        pregunta = director.costo("programar_publicacion", args)
        titulo, descripcion = publicar.publicable(args["titulo"], args["descripcion"])
        assert titulo == "Gatos que hablan | Episodio 1" and "**" not in descripcion and "](" not in descripcion
        assert descripcion == "Gatos\nEl mejor video de gatos:\n• uno\n• dos\nSuscríbete: https://y.t\n#gatos"
        assert f"«{titulo}»" in pregunta and "«Gatos El mejor video de gatos: • uno • dos Suscríbete: https://y.t " \
                                               "#gatos»" in pregunta and "01/11/2026 18:00" in pregunta, pregunta

        # ---------- La memoria y Guardia ----------
        memoria.recordar("general", "**títulos cortos**")
        assert memoria.cargar()["general"] == ["títulos cortos"]
        assert "«títulos cortos»" in director.costo("recordar_preferencia", {"departamento": "general",
                                                                             "preferencia": "**títulos cortos**"})
        ia.texto_json = lambda instrucciones, pedido, esquema, **k: {
            "explicacion": "**Tranquilo.**\n* Se bloqueó un enlace raro.\n* No tienes que hacer nada."}
        assert guardia.explicar({"tipo": "red", "detalle": "x"}) == \
            "Tranquilo.\n• Se bloqueó un enlace raro.\n• No tienes que hacer nada."
    finally:
        (claves.ARCHIVO, claves.AJUSTES, memoria.ARCHIVO, guardia.ARCHIVO, musica.PROYECTOS, seguro.pedir,
         desde_prompt._voz, desde_prompt.narrar, voz.CARPETA, musica._elevenlabs, ia.texto_json) = reales

# ---------- Errores de los servicios: su motivo, no el JSON crudo ----------
pedido = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent")
gemini = httpx.Response(400, request=pedido, json={"error": {"code": 400, "message": "API key not valid.",
                                                             "status": "INVALID_ARGUMENT", "details": [{"@type": "x"}]}})
assert ia.motivo(gemini) == "API key not valid."
assert ia.motivo(httpx.Response(403, request=pedido, json={"detail": {"status": "missing_permissions",
                                                                       "message": "Missing the permission music"}})) == \
    "Missing the permission music"
assert ia.motivo(httpx.Response(400, request=pedido, json={"errors": [{"code": 5006, "message": "oneOf not met"}],
                                                           "success": False})) == "oneOf not met"
assert ia.motivo(httpx.Response(502, request=pedido, text="<html><body><h1>502 Bad Gateway</h1></body></html>")) == \
    "502 Bad Gateway"
assert len(ia.motivo(httpx.Response(500, request=pedido, text="x " * 500))) <= 300
# Los SDK de OpenAI (Groq, Gemini…) y de Claude: sin el diccionario de Python crudo
import anthropic  # noqa: E402
import openai  # noqa: E402

cuerpo = {"error": {"message": "Invalid API Key", "type": "invalid_request_error", "code": "invalid_api_key"}}
error_openai = openai.APIStatusError("Error code: 401 - " + str(cuerpo), body=cuerpo,
                                     response=httpx.Response(401, request=pedido, json=cuerpo))


class OpenAIFalso:
    def __init__(self, **k):
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.crear))

    def crear(self, **k):
        raise error_openai


class ClaudeFalso:
    def __init__(self, **k):
        self.messages = types.SimpleNamespace(stream=self.stream)

    def stream(self, **k):
        raise anthropic.APIStatusError("Error code: 401", body=cuerpo, response=httpx.Response(401, request=pedido,
                                                                                               json=cuerpo))


para, cargar, gratis, abrir_openai, abrir_claude = (claves.para, claves.cargar, ia._texto_gratis, openai.OpenAI,
                                                     anthropic.Anthropic)
openai.OpenAI, anthropic.Anthropic = OpenAIFalso, ClaudeFalso
claves.cargar = lambda: {}
ia._texto_gratis = lambda *a: (_ for _ in ()).throw(RuntimeError("sin red en las pruebas"))
try:
    for proveedor, nombre in (("groq", "Groq"), ("anthropic", "Claude")):
        claves.para = lambda uso, p=proveedor: {"proveedor": p, "clave": "x", "modelo_texto": "m"}
        try:
            ia.texto_json("i", "p", {"type": "object"})
            raise AssertionError("debió fallar")
        except RuntimeError as e:  # si ninguna otra puede, el motivo que se enseña es el de la IA elegida
            assert str(e) == f"La IA de texto ({nombre}) respondió 401: Invalid API Key", str(e)

    # Sin saldo (402) en la IA elegida: se usa la siguiente IA de texto conectada. Pasó con Gemini prepago sin saldo:
    # todo el estudio se quedaba sin IA de texto aunque Groq (gratis) estaba conectado
    sin_saldo = {"error": {"message": "Your prepayment credits are depleted."}}
    pedidos = []
    claves.CONEXIONES.unlink(missing_ok=True)  # el 401 de arriba quedó recordado: con él, a Groq ni se le pediría

    class OpenAIPorServicio:
        def __init__(self, api_key, base_url, **k):
            self.base = base_url
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.crear))

        def crear(self, **k):
            pedidos.append(self.base)
            if "googleapis" in self.base:
                raise openai.APIStatusError("402", body=sin_saldo,
                                            response=httpx.Response(402, request=pedido, json=sin_saldo))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content='{"palabra": "listo"}'))])

    openai.OpenAI = OpenAIPorServicio
    gemini_c = {"proveedor": "gemini", "clave": "x", "modelo_texto": "m"}
    groq_c = {"proveedor": "groq", "clave": "y", "modelo_texto": "m"}
    claves.para = lambda uso: gemini_c
    claves.cargar = lambda: {"gemini": gemini_c, "groq": groq_c}
    esquema = {"type": "object", "properties": {"palabra": {"type": "string"}}, "required": ["palabra"]}
    assert ia.texto_json("i", "p", esquema) == {"palabra": "listo"}
    assert pedidos == [claves.OPENAI_COMPAT["gemini"], claves.OPENAI_COMPAT["groq"]], pedidos  # una vez cada una
    # Un error del pedido (400) no es falta de saldo: no se prueba otra IA con el mismo pedido malo
    pedidos.clear()
    malo = {"error": {"message": "bad schema"}}
    OpenAIPorServicio.crear = lambda self, **k: (pedidos.append(self.base), (_ for _ in ()).throw(
        openai.APIStatusError("400", body=malo, response=httpx.Response(400, request=pedido, json=malo))))[1]
    try:
        ia.texto_json("i", "p", esquema)
        raise AssertionError("debió fallar")
    except ia.SinServicio:
        raise AssertionError("un 400 no es falta de servicio")
    except RuntimeError as e:
        assert "400" in str(e) and len(pedidos) == 1
finally:
    claves.para, claves.cargar, ia._texto_gratis, openai.OpenAI, anthropic.Anthropic = (para, cargar, gratis,
                                                                                         abrir_openai, abrir_claude)
# Lo que se enseña de cualquier error: los mensajes de la app tal cual; los de Python, no
assert texto_de_error(ValueError("Escribe qué quieres.")) == "Escribe qué quieres."
assert texto_de_error(KeyError("mensaje")) == "Algo falló de forma inesperada. Inténtalo de nuevo."
assert texto_de_error(json.JSONDecodeError("Expecting value", "", 0)) == texto_de_error(KeyError("x"))
assert texto_de_error(PermissionError(13, "Acceso denegado", "C:\\Users\\King\\Videos\\a.mp4")) == \
    "No se pudo leer o guardar un archivo: a.mp4"
assert texto_de_error(httpx.HTTPStatusError("x", request=pedido, response=gemini)) == \
    "generativelanguage.googleapis.com respondió 400: API key not valid."
assert "Sin conexión con generativelanguage.googleapis.com" in texto_de_error(httpx.ConnectError("x", request=pedido))

# ---------- Un botón que solo lleva un símbolo se llama como su ayuda para el lector de pantalla ----------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.comun import boton  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
deshacer, exportar = boton("↶"), boton("Exportar")
deshacer.setToolTip("Deshacer (Ctrl+Z)")
exportar.setToolTip("Guarda el video")
assert deshacer.accessibleName() == "Deshacer" and exportar.accessibleName() == ""  # con texto, el lector lee el texto
print("Pruebas de textos limpios pasadas (pantalla, voz, subtítulos, publicaciones y errores).")
