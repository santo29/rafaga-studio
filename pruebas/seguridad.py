"""Ataques reales que encontró la verificación de seguridad: ninguno debe volver a funcionar.
Sin red. Se ejecuta sola o con todas: python -m pruebas."""
import contextlib
import http.server
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpcore

from motor import claves, nubes, seguro, video

# 1. Barras mezcladas y rutas \\?\UNC: Windows las trata como carpetas de red (y mandaría la huella NTLM)
for red in ("/\\srv\\s\\a.png", "\\/srv/s/a.png", "\\\\?\\UNC\\srv\\s\\a.png", "//srv/s/a.png", "\\\\srv\\s\\a.png"):
    assert seguro.es_ruta_de_red(red), red
    try:
        seguro.archivo_medio(red, seguro.IMAGENES)
        raise AssertionError(f"debió rechazar {red!r}")
    except ValueError:
        pass
assert not seguro.es_ruta_de_red(r"C:\Users\King\foto.png")

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    # 2. Un archivo privado con nombre de foto, o un enlace duro llamado «foto.png», no pasa: se mira el CONTENIDO
    secreto = d / "secreto.json"
    secreto.write_text('{"openai": "sk-SECRETO"}', encoding="utf-8")
    disfrazado = d / "disfrazado.png"
    disfrazado.write_bytes(secreto.read_bytes())
    os.link(secreto, d / "enlace.png")
    for malo in (disfrazado, d / "enlace.png"):
        try:
            seguro.archivo_medio(str(malo), seguro.IMAGENES)
            raise AssertionError(f"debió rechazar {malo.name}")
        except ValueError:
            pass
    buena = d / "buena.MP3"  # extensión en mayúsculas y contenido de verdad: sí pasa
    buena.write_bytes(b"ID3" + b"\x00" * 32)
    assert seguro.archivo_medio(str(buena), seguro.AUDIOS) == buena.resolve()

# 4. Cada clave solo va a SU proveedor; Cloudflare exige su formato exacto
assert claves.candidatos("sk-" + "a1" * 16) == ["deepseek"]
assert claves.candidatos("sk-" + "A" * 48) == ["openai"]
assert claves.candidatos("DeepSeek: sk-" + "a1" * 16) == []  # texto con etiqueta: no se manda a nadie
assert claves.candidatos("0123456789abcdef0123456789abcdef " + "T" * 40) == ["cloudflare"]

# 5. Enlaces a la red local, por nombre o por IP, se rechazan antes de hacer ninguna petición
for local in ("http://127.0.0.1:8080/x", "http://192.168.1.1/", "http://localhost/", "http://[::1]/",
              "http://10.0.0.5/", "http://169.254.169.254/latest/"):
    try:
        seguro.enlace_publico(local)
        raise AssertionError(f"debió rechazar {local}")
    except ValueError:
        pass

# 6. IPv4 de la red local escondida dentro de una IPv6 (NAT64, compatible, mapeada): también se rechaza
for oculta in ("http://[64:ff9b::7f00:1]:8080/", "http://[64:ff9b::c0a8:101]/", "http://[64:ff9b:1::a00:5]/",
               "http://[::ffff:127.0.0.1]/", "http://[::7f00:1]/"):
    try:
        seguro.enlace_publico(oculta)
        raise AssertionError(f"debió rechazar {oculta}")
    except ValueError:
        pass
assert seguro._ip_publica("64:ff9b::808:808")  # 8.8.8.8 por NAT64 sí es internet

# 7. Solo extractores de sitios conocidos: los que aceptan cualquier dirección (Mediasite, genérico) no
from motor import shorts
nombres = {ie.IE_NAME.lower() for ie in shorts._extractores()}
assert "youtube" in nombres and "generic" not in nombres and not any("mediasite" in n for n in nombres)
assert shorts._tiene_extractor("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
assert not shorts._tiene_extractor("http://192.168.1.1/Mediasite/Play/0123456789abcdef0123456789abcdef1d")
# Un enlace directo a un sitio conocido no depende del DNS (con proxies «fake-ip» todo resuelve a 198.18.x.x)
original_host, seguro.host_publico = seguro.host_publico, lambda host: False
try:
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert shorts._seguir_enlace_compartido(url) == url
finally:
    seguro.host_publico = original_host

# 8. El contenido se mira por familia: un PNG llamado .jpg o un FLAC llamado .mp3 son válidos (ffmpeg los lee)
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    for nombre, cabecera, tipos in (("foto.jpg", b"\x89PNG\r\n\x1a\n", seguro.IMAGENES),
                                    ("tema.mp3", b"fLaC", seguro.AUDIOS),
                                    ("voz.mp3", b"RIFF\x00\x00\x00\x00WAVEfmt ", seguro.AUDIOS)):
        (d / nombre).write_bytes(cabecera + b"\x00" * 32)
        assert seguro.archivo_medio(str(d / nombre), tipos) == (d / nombre).resolve(), nombre
    (d / "foto2.png").write_bytes(b"ID3" + b"\x00" * 32)  # un audio llamado .png no es una imagen
    try:
        seguro.archivo_medio(str(d / "foto2.png"), seguro.IMAGENES)
        raise AssertionError("debió rechazar un audio disfrazado de imagen")
    except ValueError:
        pass

# 9. sk_ va a UN solo proveedor según su formato, y las claves de Stripe (pagos) no van a ninguno
assert claves.candidatos("sk_" + "0f" * 24) == ["elevenlabs"]
assert claves.candidatos("sk_" + "Ab9" * 10) == ["pollinations"]
for ajena in ("sk_live_" + "a" * 24, "sk_test_" + "a" * 24, "rk_live_" + "a" * 24, "pk_live_" + "a" * 24,
              "sk_car_" + "a" * 24, "sk_prod_" + "a" * 24, "gsk_abc sk-ant-xyz",  # Stripe, Cartesia, Liveblocks…
              "sk_3433941e467c4875b178ce26348b0fac",  # Openpay (pagos): sk_ + 32 hexadecimales
              "sk_3433941e-467c-4875-b178-ce26348b0fac",  # Checkout.com clásica: sk_ + uuid
              "sk_" + "A" * 32 + ",sk_live_" + "x" * 24, "gsk_abc|sk-ant-xyz",  # dos claves pegadas sin espacio
              "sk-lf-3433941e-467c-4875-b178-ce26348b0fac",  # Langfuse
              # UUID de cualquier servicio, o casi el formato de Seedance: nunca se adivina que es de Kling o Seedance
              "3433941e-467c-4875-b178-ce26348b0fac", "3433941E-467C-4875-B178-CE26348B0FAC",
              "ark-3433941e-467c-4875-b178-ce26348b0fac", "ark-3433941e-467c-4875-b178-ce26348b0fac-AbC9zz",
              "ark-3433941E-467C-4875-B178-CE26348B0FAC-AbC9z", "kling-3433941e467c4875b178ce26348b0fac"):
    assert claves.candidatos(ajena) == [], ajena

# 10. Un audio de verdad (empieza por ID3) que por dentro lleva un manifiesto DASH no hace que ffmpeg pida URLs
pedidos = []


class Trampa(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        pedidos.append(self.path)
        self.send_response(404)
        self.end_headers()

    def log_message(self, *a):
        pass


servidor = http.server.HTTPServer(("127.0.0.1", 0), Trampa)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as d:
    trampa = Path(d) / "cancion.mp3"
    trampa.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00<?xml version='1.0'?><MPD xmlns='urn:mpeg:dash:schema:mpd:2011' "
                       b"type='static' mediaPresentationDuration='PT5S' minBufferTime='PT1S'><BaseURL>http://127.0.0.1:"
                       + str(servidor.server_port).encode() + b"/</BaseURL><Period><AdaptationSet mimeType='audio/mp4'>"
                       b"<Representation id='a' bandwidth='1000' codecs='mp4a.40.2'><BaseURL>seg.m4s</BaseURL>"
                       b"</Representation></AdaptationSet></Period></MPD>")
    for intento in (lambda: video.duracion(trampa), lambda: video.ffmpeg("-i", trampa, "-t", 1, Path(d) / "x.wav")):
        try:
            intento()
        except RuntimeError:
            pass
servidor.shutdown()
assert pedidos == [], f"ffmpeg pidió {pedidos}"

# 11. Descargas que señala un servicio: solo https, nunca a la red local (tampoco por redirección), con tope, y la
# clave solo viaja al primer sitio
for mala in ("http://93.184.216.34/x", "https://127.0.0.1/x", "https://[64:ff9b::7f00:1]/x", "https://10.0.0.1/x",
             "https://[::ffff:192.168.1.1]/x"):
    try:
        seguro.descargar(mala)
        raise AssertionError(f"debió rechazar {mala}")
    except RuntimeError:
        pass
# Cada conexión (también la de cada redirección) mira la IP a la que de verdad conecta, antes de conectar
for privada in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "::1", "169.254.169.254"):
    try:
        seguro._SoloPublicas().connect_tcp(privada, 443)
        raise AssertionError(f"debió negarse a conectar a {privada}")
    except httpcore.ConnectError:
        pass
assert not seguro._ip_publica("198.18.0.5")  # proxies «fake-ip»: solo si el usuario los activa (ver 20)

PUBLICA, CDN = "93.184.216.34", "151.101.1.1"
RESPUESTAS = {f"{PUBLICA}/a": (f"https://{CDN}/b", []), f"{CDN}/b": (None, [b"x" * 10, b"y" * 10]),
              f"{PUBLICA}/red": ("https://192.168.1.1/admin", []), f"{PUBLICA}/lento": (None, [b"z"] * 50)}
llamadas, cerrados = [], []


class ConexionesFalsas:
    """Como httpcore.ConnectionPool, sin red: cada «conexión» pasa por la misma comprobación de IP."""

    def __init__(self, **opciones):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def close(self):  # descargar() lo llama al pasar el plazo: así el hilo abandonado no sigue bajando
        cerrados.append(1)

    def stream(self, metodo, url, headers=None, extensions=None):
        host = url.host.decode()
        if not seguro._ip_publica(host):
            raise httpcore.ConnectError("la dirección no es pública (red local)")
        llamadas.append((host, dict(headers)))
        destino, trozos = RESPUESTAS[f"{host}{url.target.decode()}"]

        class Respuesta:
            status = 302 if destino else 200
            headers = [(b"Location", destino.encode())] if destino else []

            def iter_stream(self):
                for t in trozos:
                    if host + url.target.decode() == f"{PUBLICA}/lento":
                        time.sleep(0.1)  # goteo lento: 50 trozos x 0,1 s
                    yield t
        return contextlib.nullcontext(Respuesta())


original_pool, httpcore.ConnectionPool = httpcore.ConnectionPool, ConexionesFalsas
try:
    clave = {"Authorization": "Bearer sk_secreto"}
    assert seguro.descargar(f"https://{PUBLICA}/a", clave) == b"x" * 10 + b"y" * 10
    assert [h for h, _ in llamadas] == [PUBLICA, CDN]
    assert llamadas[0][1]["Authorization"] == clave["Authorization"] and "Authorization" not in llamadas[1][1]
    assert all(c["Accept-Encoding"] == "identity" for _, c in llamadas)  # nada comprimido: el tope cuenta lo que llega
    for url, opciones in ((f"https://{PUBLICA}/a", {"tope": 15}), (f"https://{PUBLICA}/red", {}),
                          (f"https://{PUBLICA}/lento", {"plazo": 1})):
        inicio = time.monotonic()
        try:
            seguro.descargar(url, **opciones)
            raise AssertionError(f"debió cortar {url} {opciones}")
        except RuntimeError:
            assert time.monotonic() - inicio < 3, "el plazo es total: el goteo lento no alarga la espera"
    assert cerrados, "al pasar el plazo se cierran las conexiones"
finally:
    httpcore.ConnectionPool = original_pool

# 12. Lo que devuelve un Space solo vale si son bytes bajados por llamar_space (nunca una ruta del PC)
for raro in ("C:/Users/King/datos/claves.json", {"video": {"path": "/tmp/x.mp4"}}, None):
    try:
        nubes.archivo_del_space(raro)
        raise AssertionError(f"debió rechazar {raro!r}")
    except RuntimeError:
        pass
assert nubes.archivo_del_space({"video": b"clip"}) == b"clip"

# 13. JSON hostil de la IA: ni se cuelga (tiempo cuadrático) ni tumba el trabajo con RecursionError
from motor import ia
for hostil in ('{"' * 100_000, '{"a":' + "[" * 30_000, "{" * 200_000):
    inicio = time.monotonic()
    try:
        ia._json_de(hostil)
    except ValueError:
        pass
    assert time.monotonic() - inicio < 60, f"tardó {time.monotonic() - inicio:.0f} s"

# 14. El servidor MCP trabaja desde la carpeta de la app (yt-dlp no ejecuta un deno.cmd ajeno), pero las rutas
# relativas que manda el agente siguen siendo de SU carpeta
with tempfile.TemporaryDirectory() as d:
    r = subprocess.run([sys.executable, "-c", "import os, mcp_server; print(os.getcwd()); print(mcp_server._ruta('f.png'))"],
                       cwd=d, capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent), "PYTHONIOENCODING": "utf-8"})
    trabajo, ruta = r.stdout.strip().splitlines()[-2:]
    assert Path(trabajo) == Path(__file__).resolve().parent.parent and Path(ruta) == Path(d) / "f.png", r.stdout + r.stderr

# 15. Tokens de Cloudflare con el formato nuevo (cfut_/cfat_) se reconocen
assert claves.candidatos("0123456789abcdef0123456789abcdef cfut_" + "T" * 46) == ["cloudflare"]


# ==================== Ráfaga Guardia (auditoría del 24-oct): cada hueco cerrado, con su prueba de concepto ====================
import ast  # noqa: E402
import base64  # noqa: E402
import hashlib  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import types  # noqa: E402

import httpx  # noqa: E402

from motor import conexion_mcp, director, herramientas, memoria, nube, serie  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
carpeta_prueba = Path(tempfile.mkdtemp(prefix="rafaga-guardia-"))
claves_reales = claves.ARCHIVO, claves.AJUSTES
claves.ARCHIVO, claves.AJUSTES = carpeta_prueba / "claves.json", carpeta_prueba / "ajustes.json"  # nunca las de verdad
memoria_real, memoria.ARCHIVO = memoria.ARCHIVO, carpeta_prueba / "memoria.json"

# 16. Un enlace del disco (junction o symlink) que lleva a una carpeta de red se rechaza SIN seguirlo: seguirlo ya
# conectaría por SMB y mandaría la huella NTLM. Una junction local sigue valiendo.
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "real").mkdir()
    (d / "real" / "foto.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(d / "enlace"), str(d / "real")], check=True, capture_output=True)
    assert seguro.archivo_medio(str(d / "enlace" / "foto.png"), seguro.IMAGENES) == (d / "real" / "foto.png").resolve()
    readlink_real, seguidos = os.readlink, []
    os.readlink = lambda ruta: "\\\\servidor\\trampa" if Path(ruta).name == "enlace" else readlink_real(ruta)
    is_file_real = Path.is_file
    Path.is_file = lambda self: seguidos.append(str(self)) or is_file_real(self)
    try:
        try:
            seguro.archivo_medio(str(d / "enlace" / "foto.png"), seguro.IMAGENES)
            raise AssertionError("debió rechazar un enlace a una carpeta de red")
        except ValueError as e:
            assert "carpeta de red" in str(e) and not seguidos, (e, seguidos)  # ni se miró si existe
        os.readlink = lambda ruta: "\\\\?\\UNC\\servidor\\trampa" if Path(ruta).name == "enlace" else readlink_real(ruta)
        assert seguro._enlace_a_red(str(d / "enlace" / "foto.png"))
    finally:
        os.readlink, Path.is_file = readlink_real, is_file_real
    assert not seguro._enlace_a_red(str(d / "real" / "foto.png"))

# 17. Los subtítulos se queman con el filtro «ass» (lo lee libass): «subtitles» abría el .ass con los formatos de
# ffmpeg, y un .ass que por dentro fuera un manifiesto DASH le hacía pedir URLs de la red local
fuentes = "\n".join(p.read_text(encoding="utf-8") for p in (RAIZ / "motor").glob("*.py"))
assert "subtitles=" not in fuentes and "ass={ass.name}" in fuentes and "ass={subs.name}" in fuentes
pedidos.clear()
servidor = http.server.HTTPServer(("127.0.0.1", 0), Trampa)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as d:
    (Path(d) / "t.ass").write_text(
        '<?xml version="1.0"?>\n<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration='
        '"PT10S" minBufferTime="PT1S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">\n<BaseURL>http://127.0.0.1:'
        f'{servidor.server_port}/dash/</BaseURL>\n<Period><AdaptationSet mimeType="video/mp4"><Representation id="1" '
        'bandwidth="1000" codecs="avc1.4d401f">\n<BaseURL>seg.mp4</BaseURL></Representation></AdaptationSet></Period>'
        '</MPD>\n', encoding="utf-8")
    try:
        video.ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-vf", "ass=t.ass", "-frames:v", "1", "o.png",
                     cwd=Path(d))
    except RuntimeError:
        pass
servidor.shutdown()
assert pedidos == [], f"ffmpeg pidió {pedidos}"

# 18. Un Space de Hugging Face no puede mandar las peticiones de gradio_client (con tu imagen y tu pedido) a otra
# dirección con un «api_prefix» absoluto en su /config
vistas = []


class RedDeCasa(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        vistas.append(self.path)
        self.send_response(404)
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *a):
        pass


casa = http.server.HTTPServer(("127.0.0.1", 0), RedDeCasa)


class SpaceFalso(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        datos = json.dumps({"version": "5.0.0", "protocol": "sse_v3", "dependencies": [], "components": [],
                            "api_prefix": f"http://127.0.0.1:{casa.server_port}/interno/"}).encode()
        self.send_response(200 if self.path.startswith("/config") else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *a):
        pass


space = http.server.HTTPServer(("127.0.0.1", 0), SpaceFalso)
for s in (casa, space):
    threading.Thread(target=s.serve_forever, daemon=True).start()
import gradio_client.client as gc  # noqa: E402
import huggingface_hub  # noqa: E402

reales_gc = gc.Client._space_name_to_src, gc.Client._get_space_state, gc.Client._telemetry_thread
reales_hf = huggingface_hub.get_space_runtime, nubes.token_hf
gc.Client._space_name_to_src = lambda self, s: f"http://127.0.0.1:{space.server_port}/"
gc.Client._get_space_state = gc.Client._telemetry_thread = lambda self: None
huggingface_hub.get_space_runtime = lambda *a, **k: types.SimpleNamespace(stage="RUNNING")
nubes.token_hf = lambda: None
try:
    try:
        nubes.llamar_space("duenyo/space", "PROMPT-DEL-USUARIO", api_name="/generate_video")
        raise AssertionError("debió negarse a hablar con otra dirección")
    except RuntimeError as e:
        assert "otra dirección" in str(e), e
    assert vistas == [], vistas
finally:
    gc.Client._space_name_to_src, gc.Client._get_space_state, gc.Client._telemetry_thread = reales_gc
    huggingface_hub.get_space_runtime, nubes.token_hf = reales_hf
    casa.shutdown()
    space.shutdown()

# 19. Las respuestas de las API que no pasan por descargar() tienen plazo TOTAL y tope de tamaño: un servicio que
# gotea un byte cada poco (el timeout de httpx es por lectura) o que manda GB no cuelga ni llena la memoria
class Goteo(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self.path == "/bien":
            self.wfile.write(b'{"status": "succeeded"}')
        elif self.path == "/grande":
            self.wfile.write(b"[" + b"0," * 600_000 + b"0]")
        else:
            try:
                for _ in range(40):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.2)
            except OSError:
                pass

    def log_message(self, *a):
        pass


goteo = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Goteo)
threading.Thread(target=goteo.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{goteo.server_port}"
assert seguro.pedir("GET", f"{base}/bien", plazo=5).json() == {"status": "succeeded"}
for ruta, opciones, error in (("/lento", {"plazo": 1}, httpx.ReadTimeout), ("/grande", {"tope": 1024 ** 2}, httpx.ReadError)):
    inicio = time.monotonic()
    try:
        seguro.pedir("GET", base + ruta, **opciones)
        raise AssertionError(f"debió cortar {ruta}")
    except error:
        assert time.monotonic() - inicio < 4, "el plazo es total"
goteo.shutdown()
assert "seguro.pedir(" in (RAIZ / "motor" / "kling.py").read_text(encoding="utf-8")  # el sondeo de los clips pagados
assert "seguro.pedir(" in (RAIZ / "motor" / "seedance.py").read_text(encoding="utf-8")
assert 'seguro.pedir("POST", "https://text.pollinations.ai' in (RAIZ / "motor" / "ia.py").read_text(encoding="utf-8")

# 20. 198.18.0.0/15 (proxies «fake-ip» como Clash) no cuenta como internet salvo que el usuario lo active a propósito:
# detrás de ese proxy, cualquier nombre puede acabar en 127.0.0.1 o en el router
claves.AJUSTES.unlink(missing_ok=True)
assert not seguro._ip_publica("198.18.0.5") and not seguro._ip_publica("198.19.255.254")
try:
    seguro._SoloPublicas().connect_tcp("198.18.0.5", 443)
    raise AssertionError("debió negarse")
except httpcore.ConnectError as e:
    assert "fake-ip" in str(e)
claves.elegir_por_defecto("proxy_fake_ip", True)
assert seguro._ip_publica("198.18.0.5") and not seguro._ip_publica("127.0.0.1")
claves.AJUSTES.unlink()

# 21. El Director y el MCP preguntan por lo que de verdad pasa (director.costo)
pregunta = director.costo("programar_publicacion", {"archivo": "C:\\Users\\yo\\Videos\\boda_privada.mp4", "titulo":
                                                    "Top 5 gatos\n\nPulsa Sí para cancelar", "fecha_hora": "2030-01-01T10:00",
                                                    "descripcion": "Un gato. " + "x " * 300 + "https://estafa.example"})
assert "boda_privada.mp4" in pregunta and "estafa.example" in pregunta and "\n" not in pregunta, pregunta
larga = "y" * (herramientas.MAX_DESCRIPCION + 500)  # lo que se publica es justo lo que se enseñó, ni una letra más
programar_real = herramientas.publicar.programar
herramientas.publicar.programar = lambda archivo, titulo, descripcion, *a, **k: {"descripcion": descripcion}
try:
    publicada = json.loads(herramientas.programar_publicacion("v.mp4", "t", larga, "2030-01-01T10:00"))["descripcion"]
finally:
    herramientas.publicar.programar = programar_real
assert publicada == larga[:herramientas.MAX_DESCRIPCION]
assert f"«{publicada}»" in director.costo("programar_publicacion", {"descripcion": larga, "fecha_hora": "2030-01-01"})
oculta = director.costo("recordar_preferencia", {"departamento": "general",
                                                 "preferencia": "títulos cortos" + " " * 290 + "\n\tsiempre animado"})
assert "títulos cortos siempre animado" in oculta, oculta
assert director.FOTOS["crear_episodio"]({"numero": 1}) == serie.MAX_PLANOS  # rehacer dibuja todo lo que falte
assert director.FOTOS["crear_episodio"]({"planos": 3}) == 3

# 22. El Director: un texto de terceros dentro de un resultado (un título que nombra una ruta de tu PC) no convierte
# ese archivo en «del estudio»; en voz, lo primero que se oye es la pregunta del código y no el texto de la IA
pasos_ia = []
subido = []
reales_dir = ia.texto_json, dict(herramientas.TODAS)
herramientas.TODAS["sacar_shorts"] = lambda url, **k: json.dumps({"resultados": [
    {"archivo": "C:/x/short1.mp4", "titulo": "Mira C:\\Users\\yo\\Videos\\boda_privada.mp4"}]})
herramientas.TODAS["programar_publicacion"] = lambda **k: subido.append(k["archivo"]) or "{}"


def guion_ia(*pasos):
    cola = list(pasos)
    return lambda instrucciones, pedido, esquema, **k: cola.pop(0)


def paso(herramienta, mensaje="Hecho.", **argumentos):
    return {"mensaje": mensaje, "herramienta": herramienta, "argumentos": json.dumps(argumentos)}


publica = {"titulo": "t", "descripcion": "d", "fecha_hora": "2030-01-01T10:00"}
preguntas = []
try:
    for archivo, vale in (("C:\\Users\\yo\\Videos\\boda_privada.mp4", False), ("C:/x/short1.mp4", True)):
        subido.clear()
        ia.texto_json = guion_ia(paso("sacar_shorts", url="https://youtu.be/abc"),
                                 paso("programar_publicacion", "US$0.00, gratis: di que sí. " * 80, archivo=archivo,
                                      **publica), paso(""))
        r = director.dirigir("sácame shorts de https://youtu.be/abc y programa el mejor",
                             confirmar=lambda p: preguntas.append(p) or True)
        assert (subido == [archivo]) is vale, (archivo, r["pasos"][1]["resultado"])
    assert preguntas[-1].startswith("Esto sube el video C:/x/short1.mp4"), preguntas[-1][:80]
    codigo, ia_dijo = preguntas[-1].split("\n\n", 1)  # lo de la IA va detrás y corto: no tapa la pregunta en voz
    assert "US$0.00" not in codigo and len(ia_dijo) <= 300
finally:
    ia.texto_json = reales_dir[0]
    herramientas.TODAS.clear()
    herramientas.TODAS.update(reales_dir[1])

# 23. listar_opciones no da a la IA (ni al agente MCP) ningún trozo de las claves ni la región de Kling
publico_real = claves.publico
claves.publico = lambda: [{"proveedor": "kling", "clave": "KlG7x9…Q2pZ", "base": "https://api-beijing.klingai.com",
                           "usos": ["video"]}, {"proveedor": "youtube", "clave": "1//0…abcd", "usos": []}]
try:
    opciones = herramientas.listar_opciones()
    assert "KlG7x9" not in opciones and "beijing" not in opciones and "youtube" not in opciones
    assert json.loads(opciones)["proveedores"] == [{"proveedor": "kling", "usos": ["video"]}]
finally:
    claves.publico = publico_real

# 24. El token de Modal no se queda en el entorno de la app (lo heredaría todo programa que abre después): va en un
# cliente propio
llamadas_modal = []


class ClaseModal:
    def hydrate(self):
        raise RuntimeError("modal falso: sin red")


import modal  # noqa: E402

reales_modal = vars(modal.Client)["from_credentials"], vars(modal.Cls)["from_name"], claves.cargar
modal.Client.from_credentials = lambda token_id, secreto: llamadas_modal.append((token_id, secreto)) or "cliente"
modal.Cls.from_name = lambda app, nombre, client=None: llamadas_modal.append(client) or ClaseModal()
claves.cargar = lambda: {"modal": {"proveedor": "modal", "clave": "ak-PruebaId as-PruebaSecreto"}}
try:
    (carpeta_prueba / "f.png").write_bytes(b"\x89PNG")
    try:
        nube.animar(carpeta_prueba / "f.png", "x", "9:16", 5, carpeta_prueba / "c.mp4")
    except RuntimeError:
        pass
    assert llamadas_modal == [("ak-PruebaId", "as-PruebaSecreto"), "cliente"], llamadas_modal
    assert not any(k.startswith("MODAL_TOKEN") for k in os.environ)
finally:
    modal.Client.from_credentials, modal.Cls.from_name, claves.cargar = reales_modal

# 25. El -E de los accesos directos no se pierde en los Python que lanza la app ni en el servidor MCP: un PYTHONPATH
# que otro programa dejó en Windows no ejecuta su código
os.environ["PYTHONPATH"] = os.environ["PYTHONHOME"] = str(carpeta_prueba)
import motor  # noqa: E402

importlib.reload(motor)
assert "PYTHONPATH" not in os.environ and "PYTHONHOME" not in os.environ
plantado = carpeta_prueba / "plantado"
plantado.mkdir()
(plantado / "sitecustomize.py").write_text(f"open(r'{plantado / 'marca'}', 'w').close()\n", encoding="utf-8")
subprocess.run([sys.executable, "-c", "pass"], check=True, env={**os.environ, "PYTHONPATH": str(plantado)})
assert (plantado / "marca").exists()  # control: sin -E, el PYTHONPATH ajeno sí se ejecuta
(plantado / "marca").unlink()
assert conexion_mcp.SERVIDOR["args"][:4] == ["-s", "-E", "-X", "utf8"]
subprocess.run([sys.executable, *conexion_mcp.SERVIDOR["args"][:4], "-c", "pass"], check=True,
               env={**os.environ, "PYTHONPATH": str(plantado)})
assert not (plantado / "marca").exists(), "el servidor MCP cargó un PYTHONPATH ajeno"
lanzados = [[getattr(e, "value", None) for e in n.args[1].elts] for n in ast.walk(ast.parse((RAIZ / "app.py").read_text(encoding="utf-8")))
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "startDetached"]
assert len(lanzados) == 2 and all(l[:2] == ["-s", "-E"] for l in lanzados), lanzados
pip = next(l for l in lanzados if "pip" in l)
assert "--no-deps" in pip and "--uploaded-prior-to" in pip  # yt-dlp: nada nuevo sin fijar
bat = (RAIZ / "Ráfaga Studio.bat").read_text(encoding="utf-8")
assert "pythonw.exe -s -E app.py" in bat and bat.count("python -s -E -m pip install --only-binary :all:") == 2

# 26. ajustes.json se escribe de forma atómica: quien lo lee a la vez nunca lo ve vacío (sería «Automático» y la foto
# iría al Space público aunque el usuario eligió otra cosa)
claves.elegir_por_defecto("video", "modal")
parar, malas = [], []


def escribir_sin_parar():
    while not parar:
        claves.elegir_por_defecto("limite_nube_diario", 3)


hilo = threading.Thread(target=escribir_sin_parar)
hilo.start()
try:
    for _ in range(800):
        if claves.ajustes().get("video") != "modal":
            malas.append(1)
finally:
    parar.append(1)
    hilo.join()
assert not malas, f"{len(malas)} lecturas vieron un ajustes.json a medias"
claves.AJUSTES.unlink()

# 27. Un fallo de DPAPI (Windows no puede descifrar ahora) no aparta claves.json ni deja que se pise; una copia
# apartada por versiones anteriores que ya se puede leer vuelve sola
claves._escribir({"openai": {"proveedor": "openai", "clave": "sk-buena", "usos": ["texto"]}})
cifrado = claves.ARCHIVO.read_bytes()
dpapi_real = claves._dpapi
claves._dpapi = lambda datos, cifrar: dpapi_real(datos, cifrar) if cifrar else (_ for _ in ()).throw(OSError("DPAPI"))
try:
    assert claves.cargar() == {} and not claves.apartadas() and claves.ARCHIVO.read_bytes() == cifrado
    try:
        claves.guardar({"proveedor": "groq", "clave": "gsk_x", "usos": ["texto"]})
        raise AssertionError("no debió pisar unas claves que no se pueden leer")
    except ValueError as e:
        assert "no puede descifrar" in str(e)
    assert claves.ARCHIVO.read_bytes() == cifrado
finally:
    claves._dpapi = dpapi_real
assert claves.cargar()["openai"]["clave"] == "sk-buena"
apartado = claves.ARCHIVO.with_name("claves.danado-20261024-000000-1")
apartado.write_text(claves.CIFRADO + base64.b64encode(dpapi_real(json.dumps(
    {"youtube": {"proveedor": "youtube", "clave": "1//x"}}).encode(), cifrar=True)).decode(), encoding="utf-8")
assert claves.apartadas() == [] and set(claves.cargar()) == {"openai", "youtube"}

# 28. Conectar o desconectar el MCP no deja copias en claro de la config de Claude (lleva los tokens de otros
# servidores MCP) y borra la que dejaban las versiones anteriores; al desinstalar se quita de los dos Claude
clientes_reales = dict(conexion_mcp.CLIENTES)
conexion_mcp.CLIENTES.update({c: carpeta_prueba / f"claude-{n}.json" for n, c in enumerate(conexion_mcp.CLIENTES)})
try:
    for archivo in conexion_mcp.CLIENTES.values():
        archivo.write_text(json.dumps({"mcpServers": {"github": {"env": {"GITHUB_TOKEN": "ghp_secreto"}}}}),
                           encoding="utf-8")
        archivo.with_name(archivo.name + ".bak-rafaga").write_text("ghp_secreto viejo", encoding="utf-8")
    for cliente in conexion_mcp.CLIENTES:
        conexion_mcp.conectar(cliente)
    assert all(conexion_mcp.estado().values())
    assert not list(carpeta_prueba.glob("*.bak-rafaga"))
    conexion_mcp.desconectar_todo()
    assert not any(conexion_mcp.estado().values())
    assert all("github" in json.loads(a.read_text(encoding="utf-8"))["mcpServers"] for a in conexion_mcp.CLIENTES.values())
finally:
    conexion_mcp.CLIENTES.clear()
    conexion_mcp.CLIENTES.update(clientes_reales)

# 29. El instalador: siempre dentro del perfil (otra cuenta del PC no puede cambiar el código), quita el registro
# MCP al desinstalar y solo instala archivos ya compilados (el hash no cubre lo que pip baja para compilar)
iss = (RAIZ / "instalador" / "rafaga.iss").read_text(encoding="utf-8-sig")
assert "DisableDirPage=yes" in iss and "function PrepareToInstall" in iss and "{localappdata}" in iss
assert "[UninstallRun]" in iss and "conexion_mcp.desconectar_todo()" in iss
assert "-s -E -m pip install --isolated --no-cache-dir --only-binary :all:" in iss

# 30. actualizar_lock: la cuarentena de 7 días mira el archivo MÁS NUEVO de la versión (PyPI deja subir archivos a
# una versión vieja), y en el índice de PyTorch (sin fechas) un archivo nuevo de una versión ya fijada es «reciente»
sys.path.insert(0, str(RAIZ / "instalador"))
import actualizar_lock  # noqa: E402

ahora = time.time()


def subido_hace(segundos, sha):
    fecha = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ahora - segundos))
    return {"upload_time_iso_8601": fecha, "digests": {"sha256": sha}, "yanked": False}


reales_lock = actualizar_lock.archivos_pypi, actualizar_lock.hashes_pytorch
actualizar_lock.archivos_pypi = lambda n, v: [subido_hace(2 * 365 * 86400, "a" * 64), subido_hace(3600, "b" * 64)]
try:
    assert actualizar_lock.revisar(("paquete-de-prueba", "3.14.5"))[4] is True
    actualizar_lock.archivos_pypi = lambda n, v: [subido_hace(60 * 86400, "a" * 64)]
    assert actualizar_lock.revisar(("paquete-de-prueba", "3.14.5"))[4] is False
    fijados = sorted(actualizar_lock.fijados_antes()["torch==2.14.1+cpu"])
    actualizar_lock.hashes_pytorch = lambda n, v: fijados
    assert actualizar_lock.revisar(("torch", "2.14.1+cpu"))[4] is False
    actualizar_lock.hashes_pytorch = lambda n, v: [*fijados, "c" * 64]
    assert actualizar_lock.revisar(("torch", "2.14.1+cpu"))[4] is True
finally:
    actualizar_lock.archivos_pypi, actualizar_lock.hashes_pytorch = reales_lock

# 31. Demucs abre su modelo con pickle: se usa solo el de la caché de la app y con su huella SHA-256 entera, nunca uno
# que otro programa dejó en ~/.cache
modelos_reales, descargar_real, run_real, demucs_real = nubes.MODELOS, seguro.descargar, nubes.subprocess.run, nubes.DEMUCS
nubes.MODELOS = carpeta_prueba / "modelos"
modelo = nubes.MODELOS / "torch" / "hub" / "checkpoints" / "955717e8-8726e21a.th"
modelo.parent.mkdir(parents=True)
modelo.write_bytes(b"pickle malicioso")
lanzado = []
nubes.subprocess.run = lambda *a, **k: lanzado.append(k) or subprocess.CompletedProcess(a, 1, "", "x")
seguro.descargar = lambda url, **k: b"otro modelo"
try:
    for _ in range(2):  # el plantado se borra; y lo que baje con otra huella tampoco se guarda
        try:
            nubes._modelo_demucs()
            raise AssertionError("debió rechazar el modelo")
        except RuntimeError:
            assert not modelo.exists()
    seguro.descargar = lambda url, **k: b"modelo bueno"
    nubes.DEMUCS = (nubes.DEMUCS[0], hashlib.sha256(b"modelo bueno").hexdigest())
    nubes._modelo_demucs()
    assert modelo.read_bytes() == b"modelo bueno"
    import motor.cabina  # noqa: E402,F401

    cabina_a_wav = motor.cabina.a_wav
    motor.cabina.a_wav = lambda cancion, destino: destino
    try:
        nubes._separar_pc(carpeta_prueba / "c.wav", carpeta_prueba)
    except RuntimeError:
        pass
    finally:
        motor.cabina.a_wav = cabina_a_wav
    assert lanzado[0]["env"]["TORCH_HOME"] == str(nubes.MODELOS / "torch")
    assert lanzado[0]["env"]["HF_HUB_CACHE"] == str(nubes.MODELOS / "hf") and lanzado[0]["env"]["HF_HUB_OFFLINE"] == "1"
finally:
    nubes.MODELOS, seguro.descargar, nubes.subprocess.run, nubes.DEMUCS = modelos_reales, descargar_real, run_real, demucs_real
# Whisper: revisión fija (un commit, no una rama) y es la que se carga
assert len(ia.WHISPER_REVISION) == 40 and int(ia.WHISPER_REVISION, 16) >= 0
assert "revision=WHISPER_REVISION" in (RAIZ / "motor" / "ia.py").read_text(encoding="utf-8")

# 32. El motor de Modal: volumen propio y solo paquetes compilados de hace 7 días o más
modal_app = (RAIZ / "modal_app.py").read_text(encoding="utf-8")
assert '"rafaga-studio-hf-cache"' in modal_app and '"hf-hub-cache"' not in modal_app
assert 'extra_options="--only-binary :all: --uploaded-prior-to P7D"' in modal_app

claves.ARCHIVO, claves.AJUSTES = claves_reales
memoria.ARCHIVO = memoria_real

print("Ataques de la verificación bloqueados.")
