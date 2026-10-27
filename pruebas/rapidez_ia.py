"""Rapidez: el investigador de nichos (YouTube y la web a la vez, con plazos y sin colgarse nunca), cómo se le pide a
Claude cada trabajo (esfuerzo, tope, caché, streaming, plazos) y el modelo de Claude elegido en «Claves de IA». Sin red
ni claves (YouTube y Claude falsos, con esperas que imitan las de verdad): python -m pruebas.rapidez_ia"""
import json
import os
import re
import tempfile
import threading
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
import anthropic  # noqa: E402
import httpx  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from motor import actividad, claves, diseno, director, ia, memoria, nichos  # noqa: E402

diseno.asegurar_qt()
app = QApplication.instance()
tmp = Path(tempfile.mkdtemp(prefix="rafaga-rapidez-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # sin claves: nunca las del usuario
memoria.ARCHIVO = tmp / "memoria.json"
nichos.PROYECTOS, nichos.FECHAS = tmp / "proyectos", tmp / "nichos" / "fechas.json"

# ---------- Nichos: YouTube falso con las esperas de verdad, divididas entre 10 (búsqueda 0,3 s; cada fecha 0,5 s) ----
LAT_BUSQUEDA, LAT_FECHA, AHORA = 0.3, 0.5, time.time()
COLGADO = f"z{19:010d}"  # el más visto: pedir su fecha no termina nunca (60 s)
pedidos_yt, cerrojo = [], threading.Lock()


class YDLFalso:
    def __init__(self, opciones):
        self.opciones = opciones

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        with cerrojo:
            pedidos_yt.append(url)
        assert self.opciones.get("socket_timeout"), "yt-dlp sin plazo espera sin fin a un servidor callado"
        if url.startswith("ytsearch"):
            time.sleep(LAT_BUSQUEDA)
            letra = "abc"[["tema", "tema shorts", f"tema {time.strftime('%Y')}"].index(url.split(":", 1)[1])]
            aproximada = "approximate_date" in json.dumps(self.opciones.get("extractor_args"))
            # 20 de la búsqueda y 20 que salen en las tres («z»). Los pares, de hace 2 días (su fecha aproximada ya
            # vale); los impares, de hace un año (gruesa: a los más vistos se les pide la exacta)
            return {"entries": [{"id": f"{p}{i:010d}", "title": f"Video {p}{i}", "channel": "Canal",
                                 "view_count": 1000 * (i + 1) + (50_000 if p == "z" else 0), "duration": 30,
                                 "timestamp": AHORA - (2 if i % 2 == 0 else 365) * 86400 if aproximada else None}
                                for p in (letra, "z") for i in range(20)]}
        video = url.rsplit("=", 1)[1]
        time.sleep(60 if video == COLGADO else LAT_FECHA)
        return {"upload_date": time.strftime("%Y%m%d", time.localtime(AHORA - 400 * 86400))}


def resultado_falso():
    return {"resumen": "Resumen", "nichos": [{"nombre": "Recetas", "potencial": 80, "competencia": "baja",
                                              "por_que_es_viral": "x", "redes": ["TikTok"], "formato": "f",
                                              "monetizacion": "m", "pruebas": "p", "hashtags": ["#a"],
                                              "ideas": [{"titulo": "t", "gancho": "g", "prompt": "p"}]}]}


analisis, plazos_web = [], []


def analizar(instrucciones, pedido, esquema, uso="texto"):
    analisis.append(pedido)
    time.sleep(0.3)
    return resultado_falso()


def web_lenta(pregunta, plazo=300):
    plazos_web.append(plazo)
    time.sleep(1.5)
    return "En TikTok explotan las recetas de 1 minuto."


reales = nichos.yt_dlp.YoutubeDL, ia.investigar_web, ia.texto_json, nichos.PLAZO_FECHAS, nichos.PLAZO_WEB, claves.para
nichos.yt_dlp.YoutubeDL, ia.investigar_web, ia.texto_json = YDLFalso, web_lenta, analizar
nichos.PLAZO_FECHAS = 1.5
claves.para = lambda uso: {"proveedor": "groq", "clave": "gsk_prueba"}  # con clave: la IA ve los 80 videos
try:
    avisos = []
    inicio = time.monotonic()
    r = nichos.investigar("tema", aviso=lambda texto, f: avisos.append(texto))
    duracion = time.monotonic() - inicio
    # Antes, todo seguido: 3 × (0,3 + 2 × 0,5) + 60 s de la fecha colgada + 1,5 de la web + 0,3 = unos 66 s. Ahora la web
    # va a la vez que YouTube, las fechas tienen su plazo y la colgada no frena nada
    assert duracion < 3.5, duracion
    busquedas = [u for u in pedidos_yt if u.startswith("ytsearch")]
    fechas = [u.rsplit("=", 1)[1] for u in pedidos_yt if "watch?v=" in u]
    assert len(busquedas) == 3
    assert len(fechas) == len(set(fechas)) <= nichos.CON_FECHA, fechas  # sin repetir los que salen en las tres
    assert all(int(i[1:]) % 2 for i in fechas), fechas  # solo las de fecha gruesa: «hace 2 días» ya vale
    assert COLGADO in fechas and all(i.startswith("z") for i in fechas)  # los más vistos
    pedido = analisis[-1]
    assert "En TikTok explotan" in pedido and "subido hace 400 días" in pedido and "subido hace 2 días" in pedido
    assert pedido.count("Video z3 |") == 1  # el que sale en las tres búsquedas, una vez
    assert plazos_web == [nichos.PLAZO_WEB] and r["con_web"] and "avisos" not in r
    assert any(re.search(r" · \d+ s$", a) for a in avisos), avisos  # el progreso dice el tiempo que lleva
    assert avisos[-1] == "¡Listo!" and len(list((tmp / "nichos").glob("2*.json"))) == 1
    guardadas = json.loads(nichos.FECHAS.read_text(encoding="utf-8"))
    assert set(guardadas) == set(fechas) - {COLGADO}, guardadas  # la colgada no llegó: no se guarda

    # La segunda vez, las fechas salen de la caché: solo se pide la que no llegó
    pedidos_yt.clear()
    nichos.investigar("tema")
    assert [u.rsplit("=", 1)[1] for u in pedidos_yt if "watch?v=" in u] == [COLGADO]
    # Una caché vieja (más de VIGENCIA_FECHAS) o dañada no se usa
    nichos.FECHAS.write_text(json.dumps({i: [f, AHORA - nichos.VIGENCIA_FECHAS - 1] for i, (f, _) in
                                         guardadas.items()}), encoding="utf-8")
    assert nichos._fechas_guardadas() == {}
    nichos.FECHAS.write_text("{roto", encoding="utf-8")
    assert nichos._fechas_guardadas() == {}

    # La web no responde nunca: la investigación sigue sin ella cuando se acaba su plazo, y lo dice
    nichos.PLAZO_WEB = 1.0
    claves.para = lambda uso: {"proveedor": "anthropic", "clave": "sk-ant-prueba"}
    ia.investigar_web = lambda pregunta, plazo=300: threading.Event().wait()
    inicio = time.monotonic()
    r = nichos.investigar("tema")
    assert time.monotonic() - inicio < 4, time.monotonic() - inicio
    assert not r["con_web"] and "tardó demasiado" in r["avisos"][0], r
    assert "no terminó a tiempo o falló" in analisis[-1] and "Dame 5 nichos" in analisis[-1]
    # La web falla (Claude sin saldo): igual, sigue con YouTube y dice por qué
    ia.investigar_web = lambda pregunta, plazo=300: (_ for _ in ()).throw(RuntimeError("Claude no tiene saldo."))
    r = nichos.investigar("tema")
    assert r["avisos"] == ["La investigación en internet falló (Claude no tiene saldo.): el análisis siguió solo con "
                           "YouTube."], r["avisos"]
finally:
    (nichos.yt_dlp.YoutubeDL, ia.investigar_web, ia.texto_json, nichos.PLAZO_FECHAS, nichos.PLAZO_WEB,
     claves.para) = reales

# Un hilo que tarda más que su plazo no frena a los demás ni se espera (y uno que falla no tumba nada)
inicio = time.monotonic()
hechas = nichos._a_tiempo({"rapida": lambda: 1, "falla": lambda: 1 / 0, "lenta": lambda: time.sleep(30)}, 0.5)
assert hechas == {"rapida": 1} and time.monotonic() - inicio < 1.5
print("Investigador de nichos a la vez y con plazos: bien.")

# ---------- Claude: cada trabajo con su esfuerzo y su tope, en streaming, con plazos y su costo real ----------
creados, pedidos_claude, respuestas = [], [], []


def mensaje(texto, stop="end_turn", **uso):
    return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=texto)], stop_reason=stop,
                                 usage=types.SimpleNamespace(**uso))


class Flujo:
    """Lo que devuelve messages.stream: sus eventos (uno cada `pausa` s) y el mensaje final."""

    def __init__(self, final, eventos=1, pausa=0.0, parcial=None):
        self.final, self.eventos, self.pausa, self.current_message_snapshot = final, eventos, pausa, parcial

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for _ in range(self.eventos):
            time.sleep(self.pausa)
            yield types.SimpleNamespace(type="content_block_delta")

    def get_final_message(self):
        return self.final


class ClaudeFalso:
    def __init__(self, **k):
        creados.append(k)
        self.messages = types.SimpleNamespace(stream=self.stream)

    def stream(self, **k):
        pedidos_claude.append(k)
        respuesta = respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


ESQ = {"type": "object", "properties": {"palabra": {"type": "string"}}, "required": ["palabra"]}
abrir_claude = anthropic.Anthropic
anthropic.Anthropic = ClaudeFalso
try:
    # Guardada cuando se conectó con otro modelo: se usa el elegido ahora (de fábrica, Opus 5.5)
    claves.guardar({"proveedor": "anthropic", "clave": "sk-ant-prueba", "usos": ["texto"],
                    "modelo_texto": "claude-opus-4-8"})
    respuestas.append(Flujo(mensaje('{"palabra": "hola"}', input_tokens=1000, output_tokens=200)))
    assert ia.texto_json("i", "p", ESQ) == {"palabra": "hola"}
    k = pedidos_claude[-1]
    assert (k["model"], k["max_tokens"], k["output_config"]["effort"]) == ("claude-opus-5-5", 32000, "medium"), k
    assert isinstance(k["system"], str)  # un pedido suelto: sin caché (escribirla cuesta 1,25 × y no se recupera)
    # El cliente no espera 10 min por intento (el de fábrica): 30 min sin noticias parecía colgado
    assert creados[-1]["timeout"].read == ia.PLAZO_CLAUDE == 120 and creados[-1]["timeout"].connect == 15
    hecha = actividad.ultimas(1)[0]
    assert hecha["modelo"] == "claude-opus-5-5" and abs(hecha["costo"] - (1000 * 4 + 200 * 20) / 1e6) < 1e-12, hecha

    # Un turno del Director: piensa poco y sus instrucciones van en caché (el 2.º turno las lee a US$0,20 el millón)
    respuestas += [Flujo(mensaje('{"palabra": "uno"}', input_tokens=100, output_tokens=50,
                                 cache_creation_input_tokens=3000, cache_read_input_tokens=0)),
                   Flujo(mensaje('{"palabra": "dos"}', input_tokens=100, output_tokens=50,
                                 cache_creation_input_tokens=0, cache_read_input_tokens=3000))]
    with ia.charla():
        ia.texto_json("instrucciones largas", "turno 1", ESQ)
        ia.texto_json("instrucciones largas", "turno 2", ESQ)
    assert not ia._CHARLA.get()  # fuera del with, todo vuelve a ser normal
    k = pedidos_claude[-1]
    assert (k["max_tokens"], k["output_config"]["effort"]) == (16000, "low")
    assert k["system"][0]["cache_control"] == {"type": "ephemeral"} and "instrucciones largas" in k["system"][0]["text"]
    dos, uno = actividad.ultimas(2)
    assert abs(uno["costo"] - (100 * 4 + 3000 * 4 * 1.25 + 50 * 20) / 1e6) < 1e-12, uno
    assert abs(dos["costo"] - (100 * 4 + 3000 * 0.20 + 50 * 20) / 1e6) < 1e-12, dos

    # El Director pide cada paso dentro de ia.charla()
    vistos, pensar = [], ia.texto_json
    ia.texto_json = lambda *a, **k: vistos.append(ia._CHARLA.get()) or {"mensaje": "Hola.", "herramienta": "",
                                                                         "argumentos": "{}"}
    try:
        assert director.dirigir("hola, ¿qué sabes hacer?")["mensaje"] == "Hola."
    finally:
        ia.texto_json = pensar
    assert vistos == [True]

    # El repaso de ortografía: rápido
    respuestas.append(Flujo(mensaje('{"textos": ["Hola amigo"]}', input_tokens=50, output_tokens=10)))
    assert ia.ortografia(["Hola amigo"]) == ["Hola amigo"]
    assert (pedidos_claude[-1]["max_tokens"], pedidos_claude[-1]["output_config"]["effort"]) == (16000, "low")

    # La investigación en internet: en streaming, esfuerzo «low» y hasta 5 búsquedas, con el modelo elegido (Sonnet)
    claves.elegir_por_defecto("modelo_claude", "claude-sonnet-5-5")
    busca = types.SimpleNamespace
    respuestas += [Flujo(mensaje("parte 1", "pause_turn", input_tokens=500, output_tokens=100,
                                 server_tool_use=busca(web_search_requests=3)), eventos=3),
                   Flujo(mensaje("Las recetas cortas explotan.", input_tokens=800, output_tokens=300,
                                 server_tool_use=busca(web_search_requests=2)), eventos=3)]
    assert ia.investigar_web("¿Qué es viral?") == "Las recetas cortas explotan."
    k1, k2 = pedidos_claude[-2:]
    assert k1["model"] == "claude-sonnet-5-5" and k1["output_config"] == {"effort": "low"}
    assert k1["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
    assert k2["messages"][-1]["role"] == "assistant"  # retoma el turno pausado
    segunda, primera = actividad.ultimas(2)
    assert primera["modelo"] == "claude-sonnet-5-5" and primera["resultado"] == "ok"
    assert abs(primera["costo"] - ((500 * 2 + 100 * 10) / 1e6 + 3 * 0.01)) < 1e-12, primera
    assert abs(segunda["costo"] - ((800 * 2 + 300 * 10) / 1e6 + 2 * 0.01)) < 1e-12, segunda
    # Llega a su plazo: corta y devuelve lo que ya tenía (y queda apuntado como cortado, con lo gastado)
    respuestas.append(Flujo(mensaje("lo del final"), eventos=100, pausa=0.05,
                            parcial=mensaje("Lo encontrado hasta ahora.", input_tokens=400, output_tokens=0)))
    inicio = time.monotonic()
    assert ia.investigar_web("¿Qué es viral?", plazo=0.3) == "Lo encontrado hasta ahora."
    assert time.monotonic() - inicio < 1.5
    cortada = actividad.ultimas(1)[0]
    assert cortada["resultado"] == "fallo" and "Se cortó" in cortada["motivo"] and cortada["costo"] > 0, cortada
    # Claude sin saldo: el motivo en claro (no el JSON del SDK), apuntado y recordado para avisar en el próximo trabajo
    cuerpo = {"error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the "
                                                                    "Anthropic API."}}
    respuestas.append(anthropic.APIStatusError("400", body=cuerpo, response=httpx.Response(
        400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"), json=cuerpo)))
    try:
        ia.investigar_web("¿Qué es viral?")
        raise AssertionError("debió fallar")
    except ia.SinServicio as e:
        assert str(e) == ("La IA de texto (Claude) respondió 400: Your credit balance is too low to access the "
                          "Anthropic API."), e
    fallida = actividad.ultimas(1)[0]
    assert fallida["resultado"] == "fallo" and "credit balance" in fallida["motivo"] and not fallida["costo"]
    assert claves.estados()["anthropic"]["estado"] == "sin_saldo"
    # Sin Claude como IA de texto no se investiga (ni se crea su cliente)
    claves.borrar("anthropic")
    creados.clear()
    assert ia.investigar_web("x") is None and not creados
finally:
    anthropic.Anthropic = abrir_claude
assert not respuestas, respuestas
print("Claude con su esfuerzo, su caché y sus plazos: bien.")

# ---------- El modelo de Claude: Opus 5.5 (de fábrica) o Sonnet 5.5, elegido en «Claves de IA» ----------
claves.AJUSTES = tmp / "ajustes_modelo.json"
assert claves.modelo_claude() == "claude-opus-5-5"  # de fábrica
assert claves.elegir_modelo_texto("anthropic", [{"id": "claude-fable-5-1"}, {"id": "claude-opus-5"}]) == \
    "claude-opus-5-5"  # al conectar no se elige otro: solo los dos que pidió el dueño
claves.elegir_por_defecto("modelo_claude", "claude-sonnet-5-5")
assert claves.modelo_claude() == "claude-sonnet-5-5"
claves.elegir_por_defecto("modelo_claude", "claude-opus-4-8")  # ajustes.json tocado a mano: otro modelo no vale
assert claves.modelo_claude() == "claude-opus-5-5"
claves.elegir_por_defecto("modelo_claude", "claude-sonnet-5-5")
claves.guardar({"proveedor": "anthropic", "clave": "sk-ant-prueba", "usos": ["texto"], "modelo_texto": "claude-opus-5-5"})
assert claves.cargar()["anthropic"]["modelo_texto"] == claves.para("texto")["modelo_texto"] == "claude-sonnet-5-5"
assert claves._leer()["anthropic"]["modelo_texto"] == "claude-opus-5-5"  # lo guardado no se toca
# Los precios por millón de tokens (los de la skill de Claude): la actividad cuesta Sonnet como Sonnet
assert ia.costo_texto("claude-opus-5-5", 1e6, 1e6) == ia.costo_texto("anthropic", 1e6, 1e6) == 24.0
assert ia.costo_texto("claude-sonnet-5-5", 1e6, 1e6) == 12.0

import ui.paginas.claves as pc  # noqa: E402
import ui.paginas.nichos as pn  # noqa: E402

pagina = pc.PaginaClaves()
combo = pagina.modelo_claude
assert [combo.itemData(i) for i in range(combo.count())] == list(claves.MODELOS_CLAUDE)
assert combo.currentData() == "claude-sonnet-5-5"  # el elegido
assert combo.itemText(0) == ("Opus 5.5 (la mejor calidad) · US$4.00 por millón de tokens de entrada y US$20.00 de "
                             "salida"), combo.itemText(0)
assert combo.itemText(1) == ("Sonnet 5.5 (más rápido y más barato) · US$2.00 por millón de tokens de entrada y "
                             "US$10.00 de salida"), combo.itemText(1)
combo.setCurrentIndex(0)
assert claves.ajustes()["modelo_claude"] == "claude-opus-5-5" and claves.modelo_claude() == "claude-opus-5-5"
assert any("claude-opus-5-5" in pagina.lista.item(i).text() for i in range(pagina.lista.count()))
# La actividad de la IA dice con qué modelo respondió Claude
actividad.anotar("texto", "anthropic", "claude-sonnet-5-5", 0.01)
pagina._pintar_actividad()
assert pagina.tabla.item(0, 3).text() == "Claude Sonnet 5.5", pagina.tabla.item(0, 3).text()
claves.borrar("anthropic")
assert claves.ajustes()["modelo_claude"] == "claude-opus-5-5"  # quitar la clave no olvida el modelo elegido
# La página de nichos enseña antes del resumen lo que no salió (p. ej. «la web tardó demasiado»)
pagina_nichos = pn.PaginaNichos(lambda prompt: None)
pagina_nichos._listo({**resultado_falso(), "avisos": ["La web tardó."]})
assert pagina_nichos.estado.text() == "La web tardó.\nResumen"
print("Modelo de Claude elegido en «Claves de IA»: bien.")
print("Pruebas de rapidez pasadas.")
