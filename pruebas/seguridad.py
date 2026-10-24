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
              "sk-lf-3433941e-467c-4875-b178-ce26348b0fac"):  # Langfuse
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
assert seguro._ip_publica("198.18.0.5")  # proxies «fake-ip»: no es una red real

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

print("Ataques de la verificación bloqueados.")
