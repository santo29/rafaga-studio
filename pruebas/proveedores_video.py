"""Kling y Seedance (videos de pago) dentro del estudio, sin red ni claves: claves, rotación, animar, escenas que
hablan, costos, el MCP que pregunta antes de gastar y la interfaz. Sus módulos (motor/kling.py, motor/seedance.py)
se sustituyen por falsos con el mismo contrato: python -m pruebas.proveedores_video"""
import asyncio
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
import httpx  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

import motor  # noqa: E402
from motor import claves, desde_prompt, director, ia, nubes, video  # noqa: E402

app = QApplication.instance() or QApplication(["pruebas"])
QMessageBox.exec = lambda caja: QMessageBox.Ok  # sin ventana no hay quien pulse «Aceptar»
tmp = Path(tempfile.mkdtemp(prefix="rafaga-video-pago-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves del usuario
nubes.USO = tmp / "uso_nubes.json"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64  # pasa seguro.es_video
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def falla(funcion, *args, error=ValueError, **kw):
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


def esperar(condicion, plazo=10):
    fin = time.monotonic() + plazo
    while not condicion() and time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)
    assert condicion(), "no terminó a tiempo"


def no_autorizada(url):
    peticion = httpx.Request("GET", url)
    return httpx.HTTPStatusError("401", request=peticion, response=httpx.Response(401, request=peticion))


# ---------- Los módulos falsos, con el contrato de motor/kling.py y motor/seedance.py ----------
def modulo_falso(nombre: str, consola: str, modelos: list[dict]):
    m = types.ModuleType(f"motor.{nombre.lower()}")
    m.NOMBRE, m.CONSOLA, m.SEGUNDOS_CLIP, m.SEGUNDOS_VOZ, m.MODELOS = nombre, consola, 5, 8, modelos
    m.llamadas, m.valida, m.falla, m.hecho_con = [], {}, None, modelos[0]["id"]
    m.falla_voz = None  # falla_voz(prompt) -> el error de esa escena que habla (o None)

    def validar(clave):
        m.llamadas.append(("validar", clave))
        if isinstance(m.valida, Exception):
            raise m.valida
        return dict(m.valida)

    def estimar(info, segundos, voz=False):
        campo = "voz" if voz else "mudo"
        ids = [x["id"] for x in modelos]
        desde = info.get("modelo_voz" if voz else "modelo_video")
        resto = modelos[ids.index(desde) if desde in ids else 0:]
        return max(x[campo] or 0 for x in resto) * segundos

    def animar(info, imagen, prompt, destino, segundos=5):
        m.llamadas.append(("animar", info.get("modelo_video"), Path(imagen), prompt, Path(destino), segundos))
        if m.falla:
            raise m.falla
        Path(destino).write_bytes(MP4)
        return m.hecho_con

    def hablar(info, imagen, prompt, destino, segundos=8):
        m.llamadas.append(("hablar", info.get("modelo_voz"), imagen, prompt, Path(destino), segundos))
        error = m.falla or (m.falla_voz and m.falla_voz(prompt))
        if error:
            raise error
        Path(destino).write_bytes(MP4)
        return m.hecho_con
    m.validar, m.estimar, m.animar, m.hablar = validar, estimar, animar, hablar
    return m


kling = modulo_falso("Kling", "https://kling.ai/dev/api-key",
                     [{"id": "kling-a", "mudo": 0.1, "voz": 0.2}, {"id": "kling-b", "mudo": 0.05, "voz": None}])
seedance = modulo_falso("Seedance", "https://console.example/ark/apiKey",
                        [{"id": "sd-a", "mudo": 0.2, "voz": 0.25}, {"id": "sd-b", "mudo": 0.03, "voz": None}])
for _nombre, _falso in (("kling", kling), ("seedance", seedance)):
    sys.modules[f"motor.{_nombre}"] = _falso
    setattr(motor, _nombre, _falso)
assert claves.modulo_video("kling") is kling and claves.modulo_video("seedance") is seedance

# ---------- Claves: Seedance por su formato exacto; Kling (sin formato conocido) solo con su botón ----------
ARK = "ark-0a1b2c3d-4e5f-6789-abcd-ef0123456789-AbC9z"
UUID = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
assert claves.candidatos(ARK) == ["seedance"]
for ajena in (UUID, UUID.upper(), f"ark-{UUID}", f"ark-{UUID}-AbC9zz", f"ark-{UUID.upper()}-AbC9z"):
    assert claves.candidatos(ajena) == [], ajena  # un UUID cualquiera nunca se manda a Kling ni a Seedance
assert "Kling o Seedance" in falla(claves.detectar, UUID) and not kling.llamadas and not seedance.llamadas

seedance.valida = {}
info = claves.detectar(ARK)  # la reconoce sola y la prueba solo en Seedance
assert seedance.llamadas == [("validar", ARK)] and not kling.llamadas
assert info["proveedor"] == "seedance" and info["usos"] == ["video", "video_voz"]
assert info["modelo_video"] == "sd-a" and info["modelo_voz"] == "sd-a"  # lo mejor de su catálogo

KLING = "KlingClave_0123456789abcdef"
kling.valida = {"base": "https://api-singapore.klingai.com", "proveedor": "otro"}  # lo de su módulo no pisa lo nuestro
info = claves.detectar(f"  {KLING}\n", "kling")
assert kling.llamadas == [("validar", KLING)] and info["base"] == "https://api-singapore.klingai.com"
assert info["proveedor"] == "kling" and info["clave"] == KLING and info["modelo_video"] == "kling-a"
assert info["modelo_voz"] == "kling-a"  # el primero que habla
kling.llamadas.clear()
# Con su botón no se le manda una clave que parece de otro servicio (tampoco secretos que candidatos() no conoce:
# GitHub, GitLab, Slack, AWS, JWT), ni texto pegado
SECRETOS = ("ghp_" + "a1B2" * 9, "github_pat_11ABCDEFG0" + "x" * 40, "glpat-" + "x" * 20, "xoxb-1234-5678-abcdEFGH",
            "AKIAIOSFODNN7EXAMPLE", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJl")
for ajena, motivo in (("AIzaSyXXXXXXXXXXXXXXXX", "otro servicio"), ("sk_live_" + "a" * 24, "otro servicio"),
                      ("sk-ant-api03-xxxxxxxx", "otro servicio"), (ARK, "otro servicio"),
                      *((s, "otro servicio") for s in SECRETOS),
                      (f"{KLING} {KLING}", "sin espacios"), ("corta", "sin espacios")):
    assert motivo in falla(claves.detectar, ajena, "kling"), ajena
for ajena in SECRETOS:
    assert "otro servicio" in falla(claves.detectar, ajena, "seedance"), ajena
assert not kling.llamadas and len(seedance.llamadas) == 1  # solo la validación de ARK de arriba
falla(claves.detectar, KLING, "gemini")  # por aquí solo van Kling y Seedance
kling.valida = no_autorizada("https://api-singapore.klingai.com/tasks?task_ids=0")
assert falla(claves.detectar, KLING, "kling").startswith("Kling no acepta esta clave (401)")
kling.valida = httpx.ConnectError("sin red")
assert falla(claves.detectar, KLING, "kling").startswith("Sin conexión con Kling.")
peticion = httpx.Request("GET", "https://api-singapore.klingai.com/tasks")
kling.valida = httpx.HTTPStatusError("503", request=peticion, response=httpx.Response(503, request=peticion))
assert "503" in falla(claves.detectar, KLING, "kling")
kling.valida = {"base": "https://api-singapore.klingai.com"}
# Antes de que llegue su módulo (otra rama), un aviso claro en vez de un error raro
delattr(motor, "kling")
sys.modules["motor.kling"] = None
try:
    assert "todavía no trae Kling" in falla(claves.detectar, KLING, "kling")
finally:
    sys.modules["motor.kling"] = kling
    motor.kling = kling

# ---------- Solo eligiéndolos: Automático nunca los usa, y elegidos no tienen respaldo ----------
claves.guardar({"proveedor": "modal", "clave": "ak-a as-b", "usos": ["video"]})
claves.guardar(claves.detectar(KLING, "kling"))
claves.guardar(claves.detectar(ARK))
assert "kling" not in nubes.orden("video") and "seedance" not in nubes.orden("video")
assert {"kling", "seedance"} <= set(claves.opciones("video")) and {"kling", "seedance"} <= set(claves.opciones("video_voz"))
assert claves.para("video_voz") is None  # sin Gemini, Automático no tiene quien haga escenas que hablan
assert ia.video_de_pago() is None and not desde_prompt.con_voz_propia()
claves.elegir_por_defecto("video", "kling")
assert nubes.orden("video") == ["kling"] and ia.video_de_pago() == "kling"  # sin respaldo: nunca se paga dos veces
claves.elegir_por_defecto("video_voz", "seedance")
assert claves.para("video_voz")["proveedor"] == "seedance" and desde_prompt.proveedor_voz() == "seedance"
# Ya cobrado: rotar no prueba la siguiente opción (pagaría otra vez) y la nota de gasto lo cuenta
probadas = []
claves.guardar({"proveedor": "cloudflare", "clave": f"{'a' * 32} {'T' * 40}", "usos": ["imagen"]})
assert nubes.orden("imagen")[:2] == ["cloudflare", "huggingface"]
falla(nubes.rotar, "imagen", {"cloudflare": lambda: (_ for _ in ()).throw(ia.Cobrado("no llegó")),
                              "huggingface": lambda: probadas.append("huggingface")}, error=ia.Cobrado)
assert not probadas
claves.borrar("cloudflare")

# ---------- Animar una escena con Kling: su clip de 5 s, y el modelo que funcionó se guarda ----------
foto = tmp / "escena.png"
foto.write_bytes(PNG)
kling.hecho_con = "kling-b"  # la cuenta no tenía kling-a: su módulo lo saltó sin pagar
clip = ia.video_desde_imagen(foto, "a cat dancing", "9:16", 7.3, tmp / "clip.mp4", pago="kling")
assert clip == tmp / "clip.mp4" and clip.read_bytes() == MP4
_, modelo, imagen, prompt, destino, segundos = kling.llamadas[-1]
assert modelo == "kling-a" and imagen == foto and "a cat dancing" in prompt and segundos == kling.SEGUNDOS_CLIP
assert claves.cargar()["kling"]["modelo_video"] == "kling-b"  # la próxima vez empieza por el que funcionó
ia.video_desde_imagen(foto, "otra", "9:16", 3, tmp / "clip2.mp4", pago="kling")
assert kling.llamadas[-1][1] == "kling-b"
assert abs(ia.precio_video("kling") - 0.05 * 5) < 1e-9  # desde kling-b: sus respaldos (ninguno) no son más caros
kling.falla = ia.Cobrado("la descarga se cortó")
assert "se cortó" in falla(ia.video_desde_imagen, foto, "x", "9:16", 3, tmp / "c3.mp4", "kling", error=ia.Cobrado)
kling.falla = RuntimeError("Kling: no te queda saldo")
assert "no te queda saldo" in falla(ia.video_desde_imagen, foto, "x", "9:16", 3, tmp / "c4.mp4", "kling",
                                    error=RuntimeError)
kling.falla = None
# Kling elegido a mitad de un trabajo que empezó sin video de pago (pago=None): esa escena no se paga ni se pide
antes = len(kling.llamadas)
assert "No hay ninguna conectada" in falla(ia.video_desde_imagen, foto, "x", "9:16", 3, tmp / "c0.mp4",
                                           error=RuntimeError) and len(kling.llamadas) == antes
# Guardar el modelo que funcionó nunca tira el clip ya pagado (claves.json abierto por otro proceso, p. ej. el MCP)
guardar_real, kling.hecho_con = claves.guardar, "kling-a"
claves.guardar = lambda info: (_ for _ in ()).throw(PermissionError("claves.json en uso"))
try:
    assert ia.video_desde_imagen(foto, "x", "9:16", 3, tmp / "c5.mp4", pago="kling") == tmp / "c5.mp4"
    kling.hecho_con = "kling-b"  # su modelo_voz guardado es kling-a: también intenta guardarlo
    assert ia.video_hablado("x", "9:16", tmp / "c6.mp4", foto, quien="kling") == tmp / "c6.mp4"
finally:
    claves.guardar, kling.hecho_con = guardar_real, "kling-b"
# Las consolas fijas de Kling y Seedance siguen en el error que ve el usuario (para recargar); las demás URL, no
causa = nubes._causa(RuntimeError(f"Recarga en {kling.CONSOLA} y vuelve; ve a {seedance.CONSOLA}; "
                                  f"https://api.cloudflare.com/client/v4/accounts/{'a' * 32}/ai (se consigue en "
                                  f"{kling.CONSOLA})."), "kling")
assert f"en {kling.CONSOLA} y" in causa and f"{seedance.CONSOLA};" in causa and f"en {kling.CONSOLA})." in causa
assert "cloudflare" not in causa and "a" * 32 not in causa

# ---------- Escenas que hablan con Seedance (elegido); Gemini sigue siendo el de Automático ----------
seedance.llamadas.clear()
seedance.hecho_con = "sd-a"
hablado = ia.video_hablado('Una manzana dice: "Hola"', "9:16", tmp / "voz.mp4", foto)
assert hablado == tmp / "voz.mp4" and seedance.llamadas[-1][2] == foto and seedance.llamadas[-1][5] == 8
assert '"Hola"' in seedance.llamadas[-1][3]
assert abs(ia.precio_video("seedance", voz=True) - 0.25 * 8) < 1e-9
escenas, costo = desde_prompt.costo_hablado(40)
assert escenas == 5 and abs(costo - 5 * 0.25 * 8) < 1e-9
assert desde_prompt.con_voz_propia()
claves.elegir_por_defecto("video_voz", "auto")
falla(ia.video_hablado, "x", "9:16", tmp / "voz2.mp4", error=ia.SinClave)  # Automático: Gemini, nunca Seedance
assert len(seedance.llamadas) == 1
assert "Kling o Seedance" in falla(desde_prompt.generar, "", guion={"titulo": "t", "descripcion": "d", "hashtags": [],
                                   "estilo_visual": "e", "escenas": [{"narracion": "n", "imagen": "i"}]},
                                   animado=True, error=ia.SinClave)
assert abs(ia.precio_video("gemini", voz=True) - 10 * ia.PRECIO_OMNI) < 1e-9 and ia.precio_video("huggingface") == 0
# Fijado al empezar el trabajo: elegir otro en «Escenas que hablan» a mitad no paga con otro servicio
claves.elegir_por_defecto("video_voz", "kling")
kling.llamadas.clear()
ia.video_hablado("x", "9:16", tmp / "voz3.mp4", foto, quien="seedance")
assert len(seedance.llamadas) == 2 and not kling.llamadas
falla(ia.video_hablado, "x", "9:16", tmp / "voz4.mp4", quien="gemini", error=ia.SinClave)  # Gemini, nunca Kling
assert not kling.llamadas and len(seedance.llamadas) == 2
claves.elegir_por_defecto("video_voz", "seedance")

# ---------- Montar: tope de clips de pago por trabajo, nota de gasto y nada se paga dos veces ----------
reales = desde_prompt.narrar, video.duracion, video.escena_de_clip, video.escena_de_imagen, video.unir
desde_prompt.narrar = lambda texto, voz, destino: []
video.duracion = lambda p: 1.0
video.escena_de_clip = lambda clip, audio, formato, palabras, escena: escena
video.escena_de_imagen = lambda img, audio, formato, palabras, escena, i: escena
video.unir = lambda partes, destino: destino


def dibujar(prompt, ancho, alto, destino):  # como en serie: lo que ya está dibujado no se vuelve a pedir
    if not destino.is_file():
        destino.write_bytes(PNG)
    return destino


guion = {"estilo_visual": "cartoon", "escenas": [{"narracion": f"n{i}", "imagen": f"scene {i}"} for i in range(20)]}
VOZ = "es-DO-EmilioNeural"
try:
    kling.llamadas.clear()
    carpeta, notas = tmp / "trabajo", []
    carpeta.mkdir()
    desde_prompt.montar(guion, carpeta, "9:16", VOZ, lambda *a: None, crear_imagen=dibujar, notas=notas, pago="kling")
    assert len(kling.llamadas) == desde_prompt.MAX_CLIPS_PAGO == 15  # el resto, zoom suave
    assert any("tope de gasto" in n for n in notas)
    assert f"Kling hizo clips de video (15): hasta unos US${15 * 0.25:.2f}" in " ".join(notas), notas
    # Reintento en la misma carpeta: las 15 ya animadas desde esa misma imagen no se pagan otra vez (solo las 5 que
    # quedaron con zoom, en este trabajo nuevo)
    notas.clear()
    desde_prompt.montar(guion, carpeta, "9:16", VOZ, lambda *a: None, crear_imagen=dibujar, notas=notas, pago="kling")
    # (sin cámara en lo que muestra la imagen, ia.direccion_video pone delante un acercamiento lento)
    assert len(kling.llamadas) == 20 and {ll[3].split("; ")[1].split(".")[0] for ll in kling.llamadas[15:]} == {
        f"scene {i}" for i in range(15, 20)} and any("Kling hizo clips de video (5)" in n for n in notas), notas
    # Un plano redibujado (más nuevo que su clip viejo) sí se anima de nuevo: es otra imagen
    os.utime(carpeta / "video_final_imagen_03.png", (time.time() + 60, time.time() + 60))
    desde_prompt.montar(guion, carpeta, "9:16", VOZ, lambda *a: None, crear_imagen=dibujar, pago="kling")
    assert len(kling.llamadas) == 21 and "; scene 3." in kling.llamadas[-1][3]
    # Varios montajes de un mismo trabajo (anuncios: uno por variante) comparten el tope; lo cobrado sin llegar cuenta
    kling.llamadas.clear()
    pagados, notas = {"clips": 0}, []
    for k in range(2):
        (tmp / f"anuncio{k}").mkdir()
        desde_prompt.montar({**guion, "escenas": guion["escenas"][:10]}, tmp / f"anuncio{k}", "9:16", VOZ,
                            lambda *a: None, crear_imagen=dibujar, notas=notas, pagados=pagados, nombre="base",
                            pago="kling")
    assert len(kling.llamadas) == 15 and pagados["clips"] == 15
    kling.llamadas.clear()
    kling.falla = ia.Cobrado("se cortó la descarga")
    notas, carpeta = [], tmp / "cobrado"
    carpeta.mkdir()
    desde_prompt.montar({**guion, "escenas": guion["escenas"][:3]}, carpeta, "9:16", VOZ, lambda *a: None,
                        crear_imagen=dibujar, notas=notas, pago="kling")
    assert len(kling.llamadas) == 1 and any("Kling hizo clips de video (1)" in n for n in notas), notas  # y no reintenta
    kling.falla = None

    # El trabajo empezó con la IA de video en «No usar» (no se preguntó nada) y el usuario elige Kling en Claves de IA
    # a mitad: ni una escena se paga (el trabajo siguiente sí pregunta)
    claves.elegir_por_defecto("video", "ninguno")
    kling.llamadas.clear()

    def cambia_a_kling(prompt, ancho, alto, destino):
        claves.elegir_por_defecto("video", "kling")
        return dibujar(prompt, ancho, alto, destino)
    notas, carpeta = [], tmp / "cambio"
    carpeta.mkdir()
    desde_prompt.montar(guion, carpeta, "9:16", VOZ, lambda *a: None, crear_imagen=cambia_a_kling, notas=notas,
                        pago=None)
    assert ia.video_de_pago() == "kling" and not kling.llamadas and not any("US$" in n for n in notas), notas

    # Escenas que hablan con Kling (generar entero): cada una arranca en la imagen de SU escena, también sin foto de
    # partida; la que se cobró sin llegar no se paga otra vez con un clip mudo (va con imagen y narración); la que
    # falló sin cobro sí se anima con el Kling que se preguntó al empezar
    reales_generar = desde_prompt.escena_hablada, desde_prompt.PROYECTOS, ia.imagen, ia.imagen_con_producto
    pedidas = []
    desde_prompt.escena_hablada = lambda clip, texto, formato, destino: destino
    ia.imagen = lambda p, w, h, d: pedidas.append(d.name) or dibujar(p, w, h, d)
    ia.imagen_con_producto = lambda p, f, w, h, d, realista=True, **k: pedidas.append(d.name) or dibujar(p, w, h, d)
    corto = {"titulo": "t", "descripcion": "d", "hashtags": [], "estilo_visual": "cartoon",
             "escenas": [{"narracion": f"n{i}", "imagen": f"scene {i}"} for i in range(3)]}
    claves.elegir_por_defecto("video_voz", "kling")
    try:
        for k, (imagen, falla_voz) in enumerate(((None, None), ("foto", None), (None, lambda p: (
                ia.Cobrado("la descarga se cortó") if "scene 0" in p else
                RuntimeError("filtro de contenido") if "scene 1" in p else None)))):
            desde_prompt.PROYECTOS = tmp / f"proyectos_{k}"  # van en el mismo segundo
            kling.llamadas.clear(), pedidas.clear()
            kling.falla_voz = falla_voz
            r = desde_prompt.generar("x", segundos=24, guion=json.loads(json.dumps(corto)), animado=True,
                                     imagen=str(foto) if imagen else "")
            habladas = sorted((ll for ll in kling.llamadas if ll[0] == "hablar"), key=lambda ll: ll[3])
            assert len(habladas) == 3 and all(isinstance(ll[2], Path) and ll[2].is_file() for ll in habladas)
            assert [ll[2].name for ll in habladas][1:] == ["video_final_imagen_01.png", "video_final_imagen_02.png"]
            assert len(pedidas) == (2 if imagen else 3), pedidas  # una por escena (la 1ª con foto es la foto), sin repetir
            # la 1ª escena con foto arranca en la foto (con su formato); sin foto, en su imagen
            assert habladas[0][2].read_bytes() == foto.read_bytes() if imagen else \
                habladas[0][2].name == "video_final_imagen_00.png"
            mudas = [ll[3].split("; ")[1].split(".")[0] for ll in kling.llamadas if ll[0] == "animar"]
            assert mudas == (["scene 1"] if falla_voz else []), mudas
            if falla_voz:
                assert any("Kling hizo escenas animadas con voz (2)" in a for a in r["avisos"]), r["avisos"]
                assert any("Kling hizo clips de video (1)" in a for a in r["avisos"]), r["avisos"]
        # Seedance sin foto: solo del texto (sus 2.x no aceptan caras reales en la imagen)
        kling.falla_voz = None
        claves.elegir_por_defecto("video_voz", "seedance")
        desde_prompt.PROYECTOS = tmp / "proyectos_seedance"
        seedance.llamadas.clear()
        desde_prompt.generar("x", segundos=24, guion=json.loads(json.dumps(corto)), animado=True)
        assert [ll[2] for ll in seedance.llamadas if ll[0] == "hablar"] == [None] * 3

        # Si el trabajo falla después de pagar clips, el error dice lo gastado y la carpeta (reintentar lo pagaría)
        assert "x" == falla(desde_prompt.relanzar_con_gasto, ValueError("x"), ["La IA entendió: y"], tmp)
        e = falla(desde_prompt.relanzar_con_gasto, ValueError("x"), ["Kling a fait 2 clip(s) vidéo : jusqu'à environ "
                                                                     "0.50 $ US selon ses tarifs."], tmp,
                  error=RuntimeError)
        assert e.startswith("x · ") and "0.50 $ US" in e and str(tmp) in e  # también las notas en francés
        # Solo animar: el clip cobrado que no llegó, o que llegó y falló al ajustarlo, se dice con su costo
        for k, (falla_kling, segmento) in enumerate(((ia.Cobrado("Kling no terminó el video a tiempo"), None),
                                                    (None, RuntimeError("ffmpeg falló")),
                                                    (RuntimeError("Kling: no te queda saldo"), None))):
            desde_prompt.PROYECTOS, kling.falla = tmp / f"proyectos_animar{k}", falla_kling
            segmento_real = video.segmento_mudo
            video.segmento_mudo = lambda *a, s=segmento: (_ for _ in ()).throw(s) if s else a[3]
            try:
                e = falla(desde_prompt.animar_imagen, str(foto), "x", error=RuntimeError)
            finally:
                video.segmento_mudo, kling.falla = segmento_real, None
            assert ("Kling hizo clips de video (1)" in e and str(desde_prompt.PROYECTOS) in e) == (k < 2), e  # sin tarea, no
        # Anuncios: falla el cierre de la 2ª variante; el error cuenta los clips de pago de las dos
        from motor import anuncios
        reales_anuncios = ia.investigar_web, ia.texto_json, video.cierre, anuncios.PROYECTOS

        def variante(k):
            return {"angulo": f"a{k}", "gancho": "g", "titulo": "t", "texto_anuncio": "x", "hashtags": [],
                    "estilo_visual": "ugc", "escenas": [{"narracion": "n", "imagen": f"ad {k} {i}"} for i in range(3)]}

        def cierre(montado, texto, formato, destino, producto=None):
            if destino.name == "anuncio_2.mp4":
                raise RuntimeError("ffmpeg falló al poner el cierre")
            return destino
        ia.investigar_web, video.cierre, anuncios.PROYECTOS = lambda pedido: "", cierre, tmp / "proyectos_anuncio"
        ia.texto_json = lambda instrucciones, pedido, esquema: {"variantes": [variante(1), variante(2)]}
        kling.llamadas.clear()
        try:
            e = falla(anuncios.crear, str(foto), "p", "d", "p", "oferta", "ugc", segundos=10, error=RuntimeError)
        finally:
            ia.investigar_web, ia.texto_json, video.cierre, anuncios.PROYECTOS = reales_anuncios
        assert len(kling.llamadas) == 6 and "cierre" in e and e.count("Kling hizo clips de video (3)") == 2, e
    finally:
        desde_prompt.escena_hablada, desde_prompt.PROYECTOS, ia.imagen, ia.imagen_con_producto = reales_generar
        kling.falla_voz = None
finally:
    desde_prompt.narrar, video.duracion, video.escena_de_clip, video.escena_de_imagen, video.unir = reales

# ---------- El costo que pregunta el Director (y el MCP): animar con Kling y hablar con Seedance ----------
precio_clip = ia.precio_video("kling")
assert f"US${10 * precio_clip:.2f}" in director.costo("crear_video", {"prompt": "x", "segundos": 45})  # 10 escenas
assert f"US${precio_clip:.2f}" in director.costo("crear_video", {"imagen": "a.png", "solo_animar": True})
assert f"US${15 * precio_clip:.2f}" in director.costo("crear_episodio", {"planos": 40})  # tope por trabajo
assert f"US${15 * precio_clip:.2f}" in director.costo("crear_episodio", {"planos": 3, "numero": 2})  # rehacer
assert f"US${15 * precio_clip:.2f}" in director.costo("crear_anuncios", {"variantes": 6, "segundos": 90})
assert director.costo("crear_serie", {}) is None and director.costo("crear_cancion", {"idea": "x"}) is None
animado = director.costo("crear_video", {"prompt": "x", "segundos": 16, "animado": True})
assert f"US${2 * 0.25 * 8 + 2 * precio_clip:.2f}" in animado, animado  # 2 escenas que hablan y, por lo alto, animadas
assert "DE PAGO" in director.INSTRUCCIONES and "US$1 por cada 8 s" not in director.INSTRUCCIONES

# ---------- MCP: lo que cuesta, publica, se guarda o usa archivos de fuera, solo con el sí de una persona ----------
# En una ventana de Windows que el agente no puede leer ni contestar (antes era un código que él mismo recibía en el
# error y podía devolver solo: así un agente inyectado pagaba Kling, publicaba en YouTube o guardaba órdenes).
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

import mcp_server  # noqa: E402
from motor import guardia  # noqa: E402

# Aquí se prueba la ventana del MCP diciendo «No» muchas veces seguidas: la regla de Ráfaga Guardia que bloquea al
# agente que insiste tiene su propia prueba (pruebas/guardia.py)
guardia.INSISTENCIA = 10 ** 6


def por_protocolo(nombre: str, argumentos: dict) -> str:
    """Como llega de un agente de verdad. El error si no se hizo; "" si se hizo."""
    try:
        asyncio.run(mcp_server.mcp.call_tool(nombre, argumentos))
        return ""
    except ToolError as e:
        return str(e)


hechos, ventanas, contesta = [], [], [False]
generar_real, animar_real, preguntar_real = desde_prompt.generar, desde_prompt.animar_imagen, mcp_server._preguntar
desde_prompt.generar = lambda *a, **k: hechos.append(k) or {"tipo": "video", "resultados": []}
desde_prompt.animar_imagen = lambda *a, **k: hechos.append(a) or {"tipo": "animacion", "resultados": []}
mcp_server._preguntar = lambda texto: ventanas.append(texto) or contesta[0]
try:
    # Sin el sí no se hace, y al agente no le llega nada que pueda devolver para saltarse la pregunta
    error = falla(mcp_server.crear_video, "un gato", error=ToolError)
    assert "no lo aceptó" in error and "US$" not in error and not hechos, error
    assert f"Esto cuesta unos US${10 * precio_clip:.2f}" in ventanas[-1] and "crear un video" in ventanas[-1]
    falla(mcp_server.crear_video, "x", "9:16", 45, "es-DO-EmilioNeural", str(foto), True, error=ToolError)
    assert "US$" in ventanas[-1] and not hechos  # también con los argumentos por posición
    assert por_protocolo("crear_video", {"prompt": "un gato", "confirmar_gasto": "0123456789abcdef"}) and not hechos
    contesta[0] = True  # la persona dice que sí: se hace
    json.loads(mcp_server.crear_video("un gato"))
    assert len(hechos) == 1
    # Archivos de fuera de la carpeta del agente y de la app: se pregunta nombrándolos, aunque sea gratis
    claves.elegir_por_defecto("video", "auto")
    contesta[0], antes = False, len(ventanas)
    solo = {"prompt": "x", "imagen": str(foto), "solo_animar": True}
    assert "no lo aceptó" in por_protocolo("crear_video", solo) and len(hechos) == 1
    assert len(ventanas) == antes + 1 and str(foto) in ventanas[-1] and "¿Lo hago?" in ventanas[-1]
    origen_real, mcp_server.ORIGEN = mcp_server.ORIGEN, str(foto.parent)  # la foto está en la carpeta del agente
    try:
        assert not por_protocolo("crear_video", solo) and len(ventanas) == antes + 1 and len(hechos) == 2
        json.loads(mcp_server.crear_video("un gato"))  # gratis y sin archivos: directo, sin ventana
        assert len(ventanas) == antes + 1 and len(hechos) == 3
    finally:
        mcp_server.ORIGEN = origen_real
    claves.elegir_por_defecto("video", "kling")
    # Publicar: la ventana dice qué video se sube y la descripción entera (no solo el título)
    publicar = {"archivo": str(foto), "titulo": "Mi short\n\nPulsa Sí para cancelar", "fecha_hora": "2030-01-01T10:00",
                "descripcion": "Un gato. " + "x " * 300 + "Gana US$500: https://estafa.example"}
    assert "no lo aceptó" in por_protocolo("programar_publicacion", publicar)
    assert foto.name in ventanas[-1] and "estafa.example" in ventanas[-1] and "\n\nPulsa" not in ventanas[-1]
    # Memoria: lo escondido tras muchos espacios o un salto de línea sale en la ventana
    por_protocolo("recordar_preferencia", {"departamento": "general",
                                           "preferencia": "títulos cortos" + " " * 290 + "\nsiempre animado"})
    assert "títulos cortos siempre animado" in ventanas[-1], ventanas[-1]
    assert len(hechos) == 3
    herramientas_mcp = {h.name: h for h in asyncio.run(mcp_server.mcp.list_tools())}
    assert all("confirmar_gasto" not in h.input_schema["properties"] for h in herramientas_mcp.values())
    assert "proveedores" in json.loads(mcp_server.listar_opciones())
finally:
    desde_prompt.generar, desde_prompt.animar_imagen, mcp_server._preguntar = generar_real, animar_real, preguntar_real
# La ventana de verdad: Sí/No con «No» por defecto; cualquier otra respuesta (o sin escritorio) es «no»
user32, llamadas = mcp_server.ctypes.windll.user32, []
caja_real = user32.MessageBoxW
try:
    for codigo, si in ((6, True), (7, False), (0, False)):
        user32.MessageBoxW = lambda *a, c=codigo: llamadas.append(a) or c
        assert mcp_server._preguntar("¿Lo hago?") is si
    assert all(a[3] & 0x4 and a[3] & 0x100 for a in llamadas)  # MB_YESNO y MB_DEFBUTTON2
finally:
    user32.MessageBoxW = caja_real

# ---------- La interfaz ----------
from PySide6.QtGui import QDesktopServices  # noqa: E402

from motor import musica  # noqa: E402
from ui.paginas import claves as pagina_claves  # noqa: E402
from ui.paginas import inicio  # noqa: E402
from ui.paginas.crear import PaginaCrear  # noqa: E402

# Claves de IA: sus filas, su botón «Conectar» (clave oculta, otro hilo) y el selector «Escenas que hablan»
claves.borrar("kling")
pagina = pagina_claves.PaginaClaves()
assert set(pagina.botones_pago) == {"kling", "seedance"} and "video_voz" in pagina.selectores
assert pagina.selectores["video_voz"].itemText(0) == "Automático (Gemini, si está conectada)"
pedidas, abiertas = [], []
dialogo_real, abrir_real = QInputDialog.getText, QDesktopServices.openUrl
QInputDialog.getText = lambda *a: pedidas.append(a) or (f" {KLING} ", True)
QDesktopServices.openUrl = lambda url: abiertas.append(url.toString())
try:
    kling.llamadas.clear()
    pagina.entrada.setText("a medio pegar")
    pagina.botones_pago["kling"].click()
    fila = pagina.botones_pago["kling"]  # mientras comprueba, lo dice su propio botón (el de arriba queda lejos)
    assert not fila.isEnabled() and fila.text() == "Comprobando…" and not pagina.conectar.isEnabled()
    esperar(lambda: "kling" in claves.cargar())
    assert pedidas[0][3] == pagina_claves.QLineEdit.Password and kling.llamadas == [("validar", KLING)]
    esperar(lambda: not pagina.tarea.isRunning() and fila.isEnabled())
    assert fila.text() == "Conectar" and pagina.entrada.text() == "a medio pegar"  # su clave no se pegó ahí
    assert "kling" in [pagina.selectores["video"].itemData(i) for i in range(pagina.selectores["video"].count())]
    pagina._abrir_consola(None, "seedance")
    assert abiertas == [seedance.CONSOLA]
finally:
    QInputDialog.getText, QDesktopServices.openUrl = dialogo_real, abrir_real
claves.elegir_por_defecto("video", "kling")
precio_clip = ia.precio_video("kling")  # conectada otra vez: empieza por su mejor modelo (y el más caro)
assert abs(precio_clip - 0.1 * 5) < 1e-9

# Crear: la casilla dice quién hace las escenas que hablan, y todo trabajo que anima con Kling pregunta antes
crear = PaginaCrear()
assert "Seedance" in crear.animado.text() and "Gemini" not in crear.animado.text()
preguntas, respuesta = [], [QMessageBox.No]
pregunta_real = QMessageBox.question
QMessageBox.question = lambda padre, titulo, texto, *a: preguntas.append(texto) or respuesta[0]
try:
    assert crear.lanzar(crear.iniciar, desde_prompt.animar_imagen, imagen=str(foto), prompt="x") is False
    assert crear.tarea is None and "con Kling: hasta 1," in preguntas[-1]
    assert f"US${precio_clip:.2f}" in preguntas[-1]
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45}) is False
    assert f"con Kling: hasta 10, por unos US${10 * precio_clip:.2f}" in preguntas[-1]
    # Animado con voz y animar con Kling: una sola pregunta con el total (las mismas escenas, no unas más)
    antes = len(preguntas)
    _, hablado = desde_prompt.costo_hablado(45)
    total = hablado + director.clips("crear_video", {"segundos": 45, "animado": True}) * precio_clip
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45, "animado": True}) is False
    assert len(preguntas) == antes + 1 and "en Seedance: 6. Las que no salgan con voz se animarán con Kling" in \
        preguntas[-1] and f"US${total:.2f} en total" in preguntas[-1], preguntas[-1]
    claves.elegir_por_defecto("video", "auto")
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45, "animado": True}) is False
    assert f"en Seedance: 6, hasta unos US${hablado:.2f}" in preguntas[-1] and "Kling" not in preguntas[-1]
    claves.elegir_por_defecto("video", "kling")
    antes = len(preguntas)
    assert crear._pagar_video(musica.crear, {"idea": "x"})  # no anima escenas: ni se pregunta
    respuesta[0] = QMessageBox.Yes
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45}) and len(preguntas) == antes + 1
    claves.elegir_por_defecto("video", "auto")
    assert crear._pagar_video(desde_prompt.generar, {"segundos": 45}) and len(preguntas) == antes + 1  # gratis
    claves.elegir_por_defecto("video", "kling")
finally:
    QMessageBox.question = pregunta_real

# Inicio: el video con IA dice que es Kling, y lo pagado no cuenta como «uso gratis»
nubes.USO.write_text(json.dumps({"fecha": time.strftime("%Y-%m-%d"), "kling": 4, "huggingface": 1}), encoding="utf-8")
ind = {i["titulo"]: i for i in inicio.indicadores()}
assert ind["Video con IA"]["valor"] == "Kling (de pago)" and not ind["Video con IA"]["conectar"]
assert ind["Uso gratis de hoy"]["valor"] == "1 creaciones" and "Kling" not in ind["Uso gratis de hoy"]["detalle"]
print("Pruebas de Kling y Seedance pasadas.")
