"""Pruebas rápidas sin internet ni claves: python pruebas.py"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")  # los mensajes que se comprueban están en español (y nada de detectar)

from motor import claves, shorts, video

# Detección de proveedor por formato de clave
assert claves.candidatos("sk-ant-api03-xxx") == ["anthropic"]
assert claves.candidatos("sk-or-v1-xxx") == ["openrouter"]
assert claves.candidatos("sk-proj-xxx") == ["openai"]  # solo OpenAI usa sk-proj-: nunca se prueba en otro
assert claves.candidatos("sk-abc") == ["openai"]  # una clave nunca se prueba en otro proveedor
assert claves.candidatos("AIzaSyXXX") == ["gemini"]
assert claves.candidatos("gsk_xxx") == ["groq"]
assert claves.candidatos("r8_xxx") == ["replicate"]
assert claves.candidatos("hola") == []

# Elección automática de modelo
assert claves.elegir_modelo_texto("anthropic", [{"id": "claude-fable-5-1"}, {"id": "claude-opus-5-5"}]) == "claude-opus-5-5"
assert claves.elegir_modelo_texto("anthropic", [{"id": "claude-sonnet-5"}, {"id": "claude-opus-5"}]) == "claude-opus-5"
openai = [{"id": "gpt-5", "created": 10}, {"id": "gpt-5-mini", "created": 20}, {"id": "text-embedding-3", "created": 30},
          {"id": "gpt-image-1", "created": 40}, {"id": "whisper-1", "created": 50}]
assert claves.elegir_modelo_texto("openai", openai) == "gpt-5"
assert claves.elegir_modelo_imagen("openai", openai) == "gpt-image-1"

# Subtítulos: la palabra que suena va en amarillo
pal = [{"palabra": "hola", "inicio": 0.0, "fin": 0.4}, {"palabra": "a", "inicio": 0.5, "fin": 0.6},
       {"palabra": "todos.", "inicio": 0.7, "fin": 1.2}, {"palabra": "Bien", "inicio": 1.5, "fin": 1.9}]
with tempfile.TemporaryDirectory() as d:
    ass = video.subtitulos_ass(pal, "9:16", Path(d) / "s.ass").read_text(encoding="utf-8")
    dialogos = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert len(dialogos) == 4, dialogos
    assert "\\c&H00FFFF&\\fscx125\\fscy125\\t(0,120,\\fscx100\\fscy100)}HOLA{" in dialogos[0], dialogos[0]
    assert dialogos[0].endswith("} A TODOS."), dialogos[0]
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass

# Transcripción en frases y ajuste de cortes al borde de palabra
assert shorts._lineas(pal).splitlines()[0] == "[0.0-1.2] hola a todos."
c = shorts._ajustar({"inicio": 0.45, "fin": 1.3}, pal, 2.0)
assert abs(c["inicio"] - 0.35) < 1e-9 and abs(c["fin"] - 1.55) < 1e-9, c

assert set(video.FORMATOS) == {"9:16", "16:9", "1:1", "4:5"}
assert claves.candidatos("sk_" + "AbCdEfGh" * 8) == ["pollinations"]  # cada formato va a un solo proveedor
assert claves.candidatos("sk_" + "a1" * 24) == ["elevenlabs"]  # formato de ElevenLabs
assert claves.candidatos("sk_live_" + "x" * 24) == []  # Stripe: nunca se manda a nadie
assert claves.candidatos("gsk_abc sk-ant-xyz") == []  # dos claves pegadas: no se adivina
assert claves.candidatos("ak-AAA111 as-BBB222") == ["modal"]
# Modal, al crear un token, da la orden entera: se entiende igual
assert claves.limpiar("modal token set --token-id ak-AAA111 --token-secret as-BBB222 --profile=yo") == \
    "ak-AAA111 as-BBB222"
try:
    claves.detectar("ak-AAA111")
    raise AssertionError("debió avisar de que falta la otra parte del token de Modal")
except ValueError as e:
    assert "falta la otra parte" in str(e)
# Si Modal rechaza el token, el motivo llega al usuario (antes se rompía con un AttributeError)
import subprocess as _sp
_run, _sp.run = _sp.run, lambda *a, **k: _sp.CompletedProcess(a, 1, "", "DeprecationWarning: x\n│ Token not found │")
try:
    claves.detectar("ak-AAA111 as-BBB222")
    raise AssertionError("debió rechazar el token")
except ValueError as e:
    assert "Token not found" in str(e) and "Warning" not in str(e)
finally:
    _sp.run = _run
assert claves.candidatos("0123456789abcdef0123456789abcdef " + "T" * 40) == ["cloudflare"]
# Cloudflare: el token solo (la cuenta se pregunta) y lo copiado con texto alrededor
cuenta, token = "0123456789abcdef0123456789abcdef", "Ab9" * 13 + "x"
assert claves.candidatos(token) == ["cloudflare"] and claves.candidatos("cfut_" + "A1b" * 15) == ["cloudflare"]
assert claves.candidatos("ghp_" + "a" * 36) == [] and claves.candidatos("glpat-" + "a" * 34) == []  # GitHub, GitLab
assert claves.limpiar(f"Account ID: {cuenta}\nAPI token: {token}") == f"{cuenta} {token}"
assert claves.limpiar(f'curl https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/x -H "Authorization: '
                      f'Bearer {token}"') == f"{cuenta} {token}"
_get = claves.httpx.get


class RespuestaCF:
    def __init__(self, codigo, datos=None):
        self.status_code, self.datos = codigo, datos or {}

    def json(self):
        return self.datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise claves.httpx.HTTPStatusError("x", request=None, response=self)


try:
    for cuentas, error in (([cuenta], None), ([cuenta, "f" * 32], "Account ID"), (None, "no acepta")):
        claves.httpx.get = lambda url, **k: (RespuestaCF(401) if cuentas is None else
                                             RespuestaCF(200, {"result": [{"id": c} for c in cuentas]}))
        try:
            info = claves.detectar(token)
            assert error is None and info["clave"] == f"{cuenta} {token}", info
        except ValueError as e:
            assert error and error in str(e), e
finally:
    claves.httpx.get = _get
from motor import ia
assert ia.cloudflare_partes("MiToken_123:0123456789abcdef0123456789abcdef") == ("0123456789abcdef0123456789abcdef",
                                                                                  "MiToken_123")
# IA gratis sin clave: sacar el JSON aunque venga con texto alrededor, y detectar campos que faltan
assert ia._json_de('Claro:\n```json\n{"a": 1}\n```') == {"a": 1}
esq = {"type": "object", "required": ["clips"], "properties": {"clips": {"type": "array", "items": {
    "type": "object", "required": ["inicio", "fin"], "properties": {}}}}}
assert ia._faltan({"clips": [{"inicio": 1, "fin": 2}]}, esq) == []
assert ia._faltan({"clips": [{"inicio": 1}]}, esq) == ["clips.fin"]
assert ia._faltan({}, esq) == ["clips"]
# Tipos: null, texto donde va número y booleanos donde va número cuentan como mal
esq2 = {"type": "object", "required": ["n", "t"], "properties": {"n": {"type": "integer"}, "t": {"type": "string"}}}
assert ia._faltan({"n": 3, "t": "x"}, esq2) == []
assert ia._faltan({"n": "3", "t": None}, esq2) == ["n", "t"]
assert ia._faltan({"n": True, "t": "x"}, esq2) == ["n"]
# Modo gratis: se queda con los elementos completos; si no queda ninguno, la respuesta no sirve
podado, ok = ia._podar({"clips": [{"inicio": 1, "fin": 2}, {"inicio": 3}]}, esq)
assert ok and podado == {"clips": [{"inicio": 1, "fin": 2}]} and not ia._faltan(podado, esq)
assert ia._podar({"clips": [{"inicio": 3}]}, esq)[1] is False  # se quedó vacía: no sirve
# Una variante con su lista de escenas incompleta se quita, sin tirar las variantes buenas
from motor import anuncios as _an
v_ok = {"angulo": "a", "gancho": "g", "titulo": "t", "texto_anuncio": "x", "hashtags": [], "estilo_visual": "e",
        "escenas": [{"narracion": "n", "imagen": "i"}]}
podado, ok = ia._podar({"variantes": [v_ok, {**v_ok, "escenas": [{"narracion": "n"}]}]}, _an.ESQUEMA)
assert ok and len(podado["variantes"]) == 1
# JSON válido seguido de texto con llaves, dos objetos seguidos, y llaves ANTES del JSON
assert ia._json_de('{"a": 1}\nNota: cambia {a}.') == {"a": 1}
assert ia._json_de('{"a": 1}\n{"b": 2}') == {"a": 1}
assert ia._json_de('Formato {inicio, fin}:\n{"clips": [{"inicio": 1, "fin": 2}]}') == {"clips": [{"inicio": 1, "fin": 2}]}
# Un ejemplo de formato antes de la respuesta real, comentarios, claves sin comillas y "inf" como número
assert ia._json_de('Formato: {"clips": [...]}\n{"clips": [{"inicio": 1, "fin": 2}]}', esq) == {"clips": [{"inicio": 1, "fin": 2}]}
assert ia._json_de('{ // guion\n "clips": [{"inicio": 1, "fin": 2}]}', esq) == {"clips": [{"inicio": 1, "fin": 2}]}
assert ia._json_de('{clips: [{"inicio": 1, "fin": 2}]}', esq) == {"clips": [{"inicio": 1, "fin": 2}]}
assert ia._validar({"n": "inf", "t": "x"}, esq2) is None  # no revienta: simplemente no es válido
assert ia._normalizar({"t": 1985}, esq2) == {"t": "1985"}
assert ia._normalizar(["#a #b"], {"type": "array", "items": {"type": "string"}}) == ["#a #b"]
assert ia._normalizar("#a #b, #c", {"type": "array", "items": {"type": "string"}}) == ["#a", "#b", "#c"]
# Números escritos como texto se aceptan; una respuesta cortada con un elemento incompleto se queda con lo completo
esq3 = {"type": "object", "required": ["nichos"], "properties": {"nichos": {"type": "array", "items": {
    "type": "object", "required": ["nombre", "potencial"], "properties": {"nombre": {"type": "string"},
                                                                       "potencial": {"type": "integer"}}}}}}
assert ia._validar({"nichos": [{"nombre": "a", "potencial": "8"}]}, esq3) == {"nichos": [{"nombre": "a", "potencial": 8}]}
cortado = ia._json_de('{"nichos": [{"nombre": "y", "potencial": 8}, {"nombre": "z", "pot', esq3)
assert ia._validar(cortado, esq3) == {"nichos": [{"nombre": "y", "potencial": 8}]}
# JSON roto típico de una IA pequeña: comillas sin escapar, coma que falta y respuesta cortada
assert ia._json_de('{"a": "dice "hola" fuerte", "b": [1, 2 "c": 3}') == {"a": 'dice "hola" fuerte', "b": [1, 2], "c": 3}
assert ia._json_de('Aquí va: {"resumen": "x", "nichos": [{"nombre": "y"') == {"resumen": "x", "nichos": [{"nombre": "y"}]}
env = claves.modal_env("as-BBB222\nak-AAA111")
assert env["MODAL_TOKEN_ID"] == "ak-AAA111" and env["MODAL_TOKEN_SECRET"] == "as-BBB222"

# Proveedor por defecto: automático, elegido, opción gratis y vuelta a automático si se quita la clave
with tempfile.TemporaryDirectory() as d:
    claves.ARCHIVO, claves.AJUSTES = Path(d) / "claves.json", Path(d) / "ajustes.json"
    from motor import nubes
    assert nubes.orden("separacion") == ["pc"]  # privacidad: tus canciones no van a un Space público
    assert claves.para("imagen") is None and claves.opciones("imagen") == ["auto", "pollinations"]
    claves.guardar({"proveedor": "openai", "clave": "sk-x", "usos": ["texto", "imagen"]})
    # Las claves se guardan cifradas con la cuenta de Windows: el archivo no deja ver la clave
    assert "sk-x" not in claves.ARCHIVO.read_text(encoding="utf-8") and claves.cargar()["openai"]["clave"] == "sk-x"
    claves.ARCHIVO.write_text('{"groq": {"proveedor": "groq", "clave": "gsk_viejo", "usos": ["texto"]}}', encoding="utf-8")
    assert claves.cargar()["groq"]["clave"] == "gsk_viejo" and "gsk_viejo" not in claves.ARCHIVO.read_text(encoding="utf-8")
    claves.borrar("groq")
    claves.guardar({"proveedor": "openai", "clave": "sk-x", "usos": ["texto", "imagen"]})
    claves.guardar({"proveedor": "pollinations", "clave": "sk_y", "usos": ["texto", "imagen", "video"]})
    assert claves.para("imagen")["proveedor"] == "pollinations"  # lo gratis va antes que OpenAI
    claves.elegir_por_defecto("imagen", "pollinations")
    assert claves.para("imagen")["clave"] == "sk_y"
    claves.elegir_por_defecto("transcripcion", "pc")
    assert claves.para("transcripcion") == {"proveedor": "pc"}
    claves.borrar("pollinations")
    assert claves.para("imagen") == {"proveedor": "pollinations"}  # sigue en su modo gratis sin clave
    assert "gratis_sin_clave" in nubes.orden("imagen")  # eligió lo gratis: sigue habiendo opción sin clave
    assert "openai" not in nubes.orden("imagen")  # ni siquiera si lo gratis falla: eligió gratis
    assert nubes.orden("imagen")[-1] == "gratis_sin_clave"  # el modo sin clave (baja calidad) va al final
    # Eligió su nube Modal para animar: si falla, su foto no se sube por detrás al Space público de Hugging Face
    claves.guardar({"proveedor": "modal", "clave": "ak-a as-b", "usos": ["video"]})
    assert "huggingface" in nubes.orden("video")
    claves.elegir_por_defecto("video", "modal")
    assert nubes.orden("video") == ["modal"]
    claves.borrar("modal")
    # Contadores con forma rara no tiran nada
    nubes.USO = Path(d) / "uso_nubes.json"
    for raro in ("[]", "null", "5", '{"fecha": "x"}'):
        nubes.USO.write_text(raro)
        nubes.contar("pc")
        assert nubes.resumen_hoy() == {"pc": 1}
    # Modal: si el motor no existe (o el token falla) no se toca el cupo; si falla ya en marcha, cuenta
    import modal.exception
    from motor import nube
    nube.USO = Path(d) / "uso_nube.json"
    claves.elegir_por_defecto("limite_nube_diario", 2)

    class MotorFalso:
        def __init__(self, existe):
            self.existe = existe

        def hydrate(self):
            if not self.existe:
                raise modal.exception.NotFoundError("App not found")

    def falla_en_marcha():
        raise modal.exception.FunctionTimeoutError("se pasó de tiempo")
    for motor, llamada in ((MotorFalso(False), lambda: None), (MotorFalso(True), falla_en_marcha)):
        try:
            nube.usar_gpu(motor, llamada)
        except Exception:
            pass
    assert nube.usados_hoy() == 1  # «App not found» no gastó cupo; el que se pasó de tiempo cuenta
    claves.elegir_por_defecto("limite_nube_diario", 0)
    try:
        nube.usar_gpu(MotorFalso(True), lambda: None)
        raise AssertionError("con tope 0 no debe usar la GPU")
    except RuntimeError as e:
        assert "apagada" in str(e)
    claves.elegir_por_defecto("video", "modal")
    claves.guardar({"proveedor": "modal", "clave": "ak-1 as-2", "usos": ["video"]})
    claves.borrar("modal")
    assert "video" not in claves.ajustes()  # al quitar la clave, su elección vuelve a Automático
    claves.elegir_por_defecto("texto", "pollinations")
    assert claves.para("texto")["proveedor"] == "openai"  # sin clave no hay texto gratis: vuelve a automático
    assert claves.publico()[0]["clave"] == "sk-x…sk-x"
print("Todas las pruebas pasaron.")

# ---------- Seguridad: los ataques de la auditoría no deben volver a funcionar ----------
from motor import cabina, nubes as _nubes, seguro, shorts
with tempfile.TemporaryDirectory() as d:
    foto = Path(d) / "foto.png"
    foto.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)  # firma PNG de verdad: se comprueba el contenido
    assert seguro.archivo_medio(str(foto), seguro.IMAGENES) == foto.resolve()
    for malo in ("datos/claves.json", r"\atacante.example\s\a.png", "//atacante.example/s/a.png", "",
                 str(Path(d) / "no_existe.png"), str(Path(d) / "virus.exe")):
        try:
            seguro.archivo_medio(malo, seguro.IMAGENES | seguro.AUDIOS)
            raise AssertionError(f"debió rechazar {malo!r}")
        except ValueError:
            pass
    # Exfiltración por el MCP: pedir «separar» el archivo de claves falla ANTES de copiar o subir nada
    try:
        cabina.separar_cancion(str(claves.ARCHIVO))
        raise AssertionError("debió rechazar el archivo de claves")
    except ValueError:
        pass
    # Un Space no puede hacer que se copie un archivo del PC que no descargó él
    for ruta in (str(foto), r"\atacante.example\s\v.mp4", {"path": str(foto)}):
        try:
            _nubes.archivo_del_space(ruta)
            raise AssertionError(f"debió rechazar {ruta!r}")
        except RuntimeError:
            pass
for malo in ("file:///C:/Users/King/.ssh/id_rsa", "ftp://x", "javascript:alert(1)", ""):
    try:
        seguro.enlace_publico(malo)
        raise AssertionError(f"debió rechazar {malo!r}")
    except ValueError:
        pass
# Enlaces a la red local (router, servicios del PC): yt-dlp los rechaza sin hacer ninguna petición
with tempfile.TemporaryDirectory() as d:
    try:
        shorts.descargar("http://127.0.0.1:9/admin", Path(d))
        raise AssertionError("debió rechazar un enlace a la red local")
    except (RuntimeError, ValueError) as e:  # lo para el chequeo de host público (antes) o yt-dlp (después)
        assert "red local" in str(e) or "sitios conocidos" in str(e)
import pruebas_seguridad  # noqa: E402,F401  los ataques de la segunda auditoría (archivo aparte)
print("Pruebas de seguridad pasadas.")

# El estudio de diseño: cada archivo en su propio proceso (cada uno prepara Qt y sus propias carpetas temporales)
for archivo in ("pruebas_diseno_recursos.py", "pruebas_diseno.py", "pruebas_diseno_ia.py", "pruebas_diseno_ui.py",
                "pruebas_edicion.py", "pruebas_render_edicion.py", "pruebas_edicion_ui.py", "pruebas_director.py",
                "pruebas_serie.py", "pruebas_idioma.py"):
    subprocess.run([sys.executable, str(Path(__file__).with_name(archivo))], check=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8", "QT_QPA_PLATFORM": "offscreen"})
print("Pruebas del estudio de diseño, del editor de video y del Director pasadas.")
