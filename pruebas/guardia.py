"""Ráfaga Guardia (motor/guardia.py y su página): el historial compartido por la app y el MCP (dos procesos a la vez),
lo que se apunta (nunca una clave, un enlace firmado ni una ruta con tu nombre), que cada defensa apunta su evento, la
integridad del código, el bloqueo (y que solo lo quita la página), las reglas del bloqueo automático y la página
offscreen. Sin red ni claves de verdad. Sola: python -m pruebas.guardia"""
import ast
import asyncio
import base64
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from motor import claves, conexion_mcp, director, guardia, memoria, nubes, seguro  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="rafaga-prueba-guardia-"))
# Nada de verdad: ni tus claves, ni tu memoria, ni las configuraciones de Claude (llevan tokens de otros servidores)
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"
memoria.ARCHIVO = tmp / "memoria.json"
conexion_mcp.CLIENTES = {c: tmp / f"claude-{n}.json" for n, c in enumerate(conexion_mcp.CLIENTES)}
nubes.MODELOS = tmp / "modelos"


def nuevo_historial():
    guardia.ARCHIVO = tmp / f"guardia-{time.time_ns()}.json"
    guardia._recientes.clear()


def tipos() -> list[str]:
    return [e["tipo"] for e in guardia.eventos()]


def falla(funcion, *args, error=Exception, **kw) -> str:
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


# ---------- Lo que se apunta: corto y sin secretos ----------
clave = "sk-ant-api03-" + "A1b2C3d4" * 6
firmada = "https://bucket.s3.amazonaws.com/v.mp4?X-Amz-Signature=deadbeef1234&X-Amz-Credential=AKIAXYZ123"
ruta = r"C:\Users\Juan Perez\Desktop\foto secreta.png"
red = r"\\servidor-del-atacante\compartida\cuentas.png"
token = "0123456789abcdef0123456789abcdef"
limpio = guardia.limpiar(f"clave {clave} enlace {firmada} ruta {ruta} red {red} token {token} casa {Path.home()}\\x.png")
for secreto in (clave, "sk-ant", "Signature", "AKIA", "Juan", "Perez", "servidor-del-atacante", token,
                str(Path.home())):
    assert secreto not in limpio, (secreto, limpio)
assert "bucket.s3.amazonaws.com" in limpio and "cuentas.png" in limpio, limpio
assert len(guardia.limpiar("x" * 1000)) <= 240
# Un texto enorme no cuelga a nadie (antes, «a+a+a+…» tardaba un tiempo cuadrático) y un nombre de archivo largo se
# ve entero; un token al final de una frase sigue tapado
inicio = time.time()
guardia.limpiar("\\\\srv\\share\\" + "a+" * 50_000)
assert time.time() - inicio < 1, time.time() - inicio
largo = "mi_video_final_version_2026_10_24_editado.gif"
assert largo in guardia.limpiar(f"Se rechazó un archivo que no es lo que dice su nombre: {largo}")
assert token not in guardia.limpiar(f"el token {token}. Nada más")
nuevo_historial()
guardia.registrar("prueba", "media", f"{clave} {firmada} {ruta}")
guardado = guardia.ARCHIVO.read_text(encoding="utf-8")
assert clave not in guardado and "Signature" not in guardado and "Juan" not in guardado and "AKIA" not in guardado

# ---------- El historial: dos procesos y dos hilos a la vez no se pisan ----------
nuevo_historial()
escribir = ("import sys; from pathlib import Path; from motor import guardia; guardia.ARCHIVO = Path(sys.argv[1]); "
            "[guardia.registrar('prueba', 'baja', f'proceso {sys.argv[2]} evento {i}', 'mcp') for i in range(40)]")
procesos = [subprocess.Popen([sys.executable, "-c", escribir, str(guardia.ARCHIVO), str(n)], cwd=RAIZ)
            for n in range(2)]
hilos = [threading.Thread(target=lambda n=n: [guardia.registrar("prueba", "baja", f"hilo {n} evento {i}")
                                              for i in range(25)]) for n in range(2)]
for hilo in hilos:
    hilo.start()
for hilo in hilos:
    hilo.join()
assert all(p.wait(120) == 0 for p in procesos)
detalles = {e["detalle"] for e in guardia.eventos()}
assert len(detalles) == 2 * 40 + 2 * 25, len(detalles)
assert not guardia.ARCHIVO.with_name(guardia.ARCHIVO.name + ".lock").exists()
assert {e["origen"] for e in guardia.eventos()} == {"mcp", "app"}
# Con tope: solo los más nuevos
nuevo_historial()
tope_real, guardia.MAX_EVENTOS = guardia.MAX_EVENTOS, 10
try:
    for i in range(15):
        guardia.registrar("prueba", "baja", f"evento {i}")
    assert [e["detalle"] for e in guardia.eventos()] == [f"evento {i}" for i in range(14, 4, -1)]
finally:
    guardia.MAX_EVENTOS = tope_real
# Lo mismo otra vez suma «veces» en vez de llenar el historial
nuevo_historial()
for _ in range(2):
    guardia._recientes.clear()
    guardia.registrar("red", "media", "lo mismo")
assert len(guardia.eventos()) == 1 and guardia.eventos()[0]["veces"] == 2
# Un cerrojo que dejó un proceso muerto no cuelga a nadie
cerrojo = guardia.ARCHIVO.with_name(guardia.ARCHIVO.name + ".lock")
cerrojo.write_text("")
os.utime(cerrojo, (time.time() - 60, time.time() - 60))
guardia.registrar("prueba", "baja", "tras un cerrojo viejo")
assert "tras un cerrojo viejo" in {e["detalle"] for e in guardia.eventos()} and not cerrojo.exists()
# Ni uno que otro programa mantiene fresco: la ventana (que también escribe aquí) no se congela 10 s por escritura
parar = threading.Event()


def refrescar():
    while not parar.is_set():
        cerrojo.touch()
        time.sleep(0.3)


hilo = threading.Thread(target=refrescar)
hilo.start()
try:
    time.sleep(0.1)
    inicio = time.time()
    guardia.marcar_visto()
    assert time.time() - inicio < 4 and guardia._leer()["visto"], time.time() - inicio
finally:
    parar.set()
    hilo.join()
    cerrojo.unlink(missing_ok=True)

# ---------- Un historial roto nunca rompe nada ----------
for roto in ("{roto", "[1, 2]", '{"eventos": "x", "bloqueo": 5, "visto": 3}', '{"eventos": [{"tipo": 1}, 7]}', ""):
    nuevo_historial()
    guardia.ARCHIVO.write_text(roto, encoding="utf-8")
    assert guardia.eventos() == [] and guardia.bloqueado() is None and guardia.estado() == "ok", roto
    guardia.registrar("prueba", "media", "después de romperse")
    assert tipos() == ["prueba"] and json.loads(guardia.ARCHIVO.read_text(encoding="utf-8"))["eventos"]
# Ni sin poder escribir: la función que lo avisa sigue (registrar nunca lanza)
archivo_real, guardia.ARCHIVO = guardia.ARCHIVO, tmp / "soy-un-archivo" / "guardia.json"
(tmp / "soy-un-archivo").write_text("")
guardia.registrar("prueba", "alta", "no se puede escribir")
guardia.bloquear("x")
guardia.desbloquear()
assert guardia.eventos() == [] and guardia.bloqueado() is None
guardia.ARCHIVO = archivo_real
# Otro programa lo abre en exclusiva: falla cerrado (cuenta como bloqueado), nadie lo pisa (se perdería el bloqueo de
# verdad) y no quedan temporales; al soltarlo, todo sigue como estaba
if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                wintypes.DWORD, wintypes.HANDLE]

    def en_exclusiva():
        asa = k32.CreateFileW(str(guardia.ARCHIVO), 0x80000000, 0, None, 3, 0, None)  # GENERIC_READ, sin compartir
        assert asa and asa != wintypes.HANDLE(-1).value, ctypes.get_last_error()
        return asa

    nuevo_historial()
    guardia.registrar("prueba", "baja", "antes")
    asa = en_exclusiva()
    try:
        assert guardia.bloqueado()["ilegible"] and guardia.estado() == "peligro"
        assert "No se puede leer" in falla(guardia.sin_bloqueo, error=RuntimeError)
        guardia.registrar("prueba", "alta", "mientras está abierto")
        guardia.desbloquear()
        falla(claves._reemplazar, guardia.ARCHIVO, "{}", error=PermissionError)
    finally:
        k32.CloseHandle(asa)
    assert tipos() == ["prueba"] and guardia.bloqueado() is None and not list(tmp.glob("guardia-*.tmp"))
print("Historial de Ráfaga Guardia: limpio, compartido y a prueba de roturas.")

# ---------- Cada defensa apunta su evento (con una línea, donde ya decide) ----------
from motor import herramientas  # noqa: E402

nuevo_historial()
assert "red" in falla(seguro.archivo_medio, red, seguro.IMAGENES, "Foto", error=ValueError)
assert tipos()[0] == "red" and "servidor-del-atacante" not in guardia.eventos()[0]["detalle"]
falsa = tmp / "claves.png"
falsa.write_bytes(b'{"openai": "sk-..."}')
falla(seguro.archivo_medio, str(falsa), seguro.IMAGENES, "Foto", error=ValueError)
assert tipos()[0] == "archivo_falso" and "claves.png" in guardia.eventos()[0]["detalle"]
falla(seguro.enlace_publico, "http://127.0.0.1:8080/admin", error=ValueError)
assert tipos()[0] == "red_local" and "127.0.0.1" in guardia.eventos()[0]["detalle"]
guardia._recientes.clear()
import httpcore  # noqa: E402

falla(seguro._SoloPublicas().connect_tcp, "localhost", 80, error=httpcore.ConnectError)  # también tras un salto
assert tipos()[0] == "red_local"
resolver = seguro.socket.getaddrinfo
seguro.socket.getaddrinfo = lambda *a, **k: [(2, 1, 6, "", ("198.18.0.7", 443))]
try:
    assert "fake-ip" in falla(seguro._SoloPublicas().connect_tcp, "proxy.example", 443, error=httpcore.ConnectError)
finally:
    seguro.socket.getaddrinfo = resolver
assert tipos()[0] == "fake_ip" and guardia.eventos()[0]["gravedad"] == "baja"
# El Director: herramientas que no existen y archivos que no vienen del usuario ni del estudio
nada = lambda *a, **k: None  # noqa: E731
_, r = director._usar("borrar_todo", "{}", nada, nada, "", "")
assert r.startswith("ERROR") and tipos()[0] == "herramienta" and guardia.eventos()[0]["origen"] == "director"
_, r = director._usar("crear_video", {"prompt": "x", "imagen": r"C:\Users\Juan\Desktop\dni.png"}, nada, nada, "", "")
assert r.startswith("ERROR") and tipos()[0] == "director" and "Juan" not in guardia.eventos()[0]["detalle"]
# Claves: una de otro servicio pegada en «Conectar» de Kling, Windows que no descifra, un archivo dañado y uno
# cambiado por otro programa
falla(claves.detectar, "ghp_" + "a" * 36, "kling", error=ValueError)
assert tipos()[0] == "clave_ajena" and "ghp_" not in guardia.ARCHIVO.read_text(encoding="utf-8")
assert guardia.eventos()[0]["gravedad"] == "baja"  # un despiste de la persona, ya resuelto: no pone el escudo ámbar
claves.guardar({"proveedor": "groq", "clave": "gsk_prueba", "usos": ["texto"]})
assert "claves_cambiadas" not in tipos()  # lo escribió la app: no avisa
claves.ARCHIVO.write_text('{"groq": {"proveedor": "groq", "clave": "gsk_otra", "usos": ["texto"]}}', encoding="utf-8")
assert claves.cargar()["groq"]["clave"] == "gsk_otra" and tipos()[0] == "claves_cambiadas"
claves.cargar()
assert tipos().count("claves_cambiadas") == 1  # se avisa una vez
if os.name == "nt":
    claves.ARCHIVO.write_text("DPAPI:" + base64.b64encode(b"no es de esta cuenta").decode(), encoding="utf-8")
    assert claves.cargar() == {} and tipos()[0] == "claves_dpapi"
    claves.ARCHIVO.write_text("DPAPI:abc", encoding="utf-8")  # base64 roto: dañado de verdad
    assert claves.cargar() == {} and "claves_danadas" in tipos()
    for apartado in tmp.glob("claves.danado-*"):
        apartado.unlink()
claves.ARCHIVO.unlink(missing_ok=True)
# La memoria no guarda datos sensibles
falla(memoria.recordar, "general", "mi contraseña es 1234", error=ValueError)
assert tipos()[0] == "memoria"
# El MCP: archivos de fuera de su carpeta y el «No» del usuario
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

import mcp_server  # noqa: E402

preguntas, preguntar_real = [], mcp_server._preguntar
mcp_server._preguntar = lambda texto: preguntas.append(texto) or False
try:
    nuevo_historial()
    assert "no lo aceptó" in falla(mcp_server.crear_video, "un gato", imagen=str(tmp / "foto.png"), error=ToolError)
    assert tipos() == ["mcp_no", "mcp_fuera"] and {e["origen"] for e in guardia.eventos()} == {"mcp"}
    assert str(tmp) not in guardia.ARCHIVO.read_text(encoding="utf-8")
    assert guardia.estado() == "ok"  # un «No» suelto es una decisión tuya: escudo verde (3 en 10 min bloquean)
finally:
    mcp_server._preguntar = preguntar_real
    guardia.ORIGEN = "app"  # importar mcp_server firma lo de este proceso como «mcp»; el resto de la prueba es la app
print("Cada defensa apunta su evento en Ráfaga Guardia.")

# ---------- Las reglas del bloqueo automático (las decide el código, nunca una IA) ----------
nuevo_historial()
for n in range(guardia.INSISTENCIA):
    assert guardia.bloqueado() is None
    guardia.registrar("mcp_no", "baja", "Dijiste «No»", "mcp")
assert "insistió" in guardia.bloqueado()["motivo"] and guardia.eventos()[0]["tipo"] == "bloqueo"
assert guardia.eventos()[0]["gravedad"] == "alta" and guardia.estado() == "peligro"
# Tras desbloquear, los «No» de antes no cuentan
guardia.desbloquear()
guardia.registrar("mcp_no", "baja", "Dijiste «No»", "mcp")
assert guardia.bloqueado() is None
# Fuera de la ventana de 10 minutos no cuentan
nuevo_historial()
viejo = (datetime.now() - timedelta(seconds=guardia.VENTANA + 60)).strftime("%Y-%m-%d %H:%M:%S")
guardia.ARCHIVO.write_text(json.dumps({"eventos": [
    {"id": f"v{n}", "fecha": viejo, "tipo": "mcp_no", "gravedad": "media", "detalle": "No", "origen": "mcp"}
    for n in range(2)]}), encoding="utf-8")
guardia.registrar("mcp_no", "media", "No", "mcp")
assert guardia.bloqueado() is None
# Otros eventos, aunque sean «alta», no bloquean; el código cambiado sí
guardia.registrar("claves_cambiadas", "alta", "otro programa")
guardia.registrar("integridad", "media", "no es alta")
assert guardia.bloqueado() is None
guardia.registrar("integridad", "alta", "plantado")
assert "código" in guardia.bloqueado()["motivo"]
# visto: lo revisado ya no pone el escudo en rojo, el bloqueo sí
guardia.marcar_visto()
assert guardia.estado() == "peligro"
guardia.desbloquear()
assert guardia.estado() == "ok" and guardia.estado([{"estado": "aviso"}]) == "aviso"
assert guardia.estado([{"estado": "peligro"}]) == "peligro"
print("Reglas del bloqueo automático: 3 «No» en 10 minutos o el código cambiado, nada más.")

# ---------- Con el estudio bloqueado: ni el MCP, ni lo de pago del Director, ni las llamadas de pago ----------
from motor import desde_prompt, ia, kling, musica, seedance  # noqa: E402
from motor import publicar as subir  # noqa: E402  («publicar» es aquí lo que pide el Director)

nuevo_historial()
guardia.bloquear("prueba")
mcp_server._preguntar = lambda texto: (_ for _ in ()).throw(AssertionError("no debió preguntar"))
try:
    for llamada in (lambda: mcp_server.listar_opciones(),
                    lambda: asyncio.run(mcp_server.mcp.call_tool("listar_proyectos", {})),
                    lambda: mcp_server.crear_video("un gato")):
        assert "bloqueado" in falla(llamada, error=ToolError)
finally:
    mcp_server._preguntar = preguntar_real
assert "bloqueado" in tipos()
confirmaciones = []
si = lambda pregunta: confirmaciones.append(pregunta) or True  # noqa: E731
_, r = director._usar("recordar_preferencia", {"departamento": "general", "preferencia": "títulos cortos"}, nada, nada,
                      "títulos cortos", "", si)
assert "bloqueado" in r and not confirmaciones and memoria.cargar() == {}
publicar = {"archivo": "v.mp4", "titulo": "t", "descripcion": "d", "fecha_hora": "2030-01-01T10:00"}
_, r = director._usar("programar_publicacion", publicar, nada, nada, "v.mp4", "v.mp4", si)
assert "bloqueado" in r and not confirmaciones
_, r = director._usar("listar_opciones", {}, nada, nada, "", "", si)  # lo gratis del Director sigue
assert not r.startswith("ERROR"), r
claves.guardar({"proveedor": "gemini", "clave": "AIzaPrueba", "usos": ["texto", "musica"], "modelo_musica": "lyria-3.5"})
claves.guardar({"proveedor": "elevenlabs", "clave": "e" * 32, "usos": ["voz"]})
claves.guardar({"proveedor": "openai", "clave": "sk-prueba", "usos": ["transcripcion"],
                "modelo_transcripcion": "whisper-1"})
pagos = {"kling": lambda: kling._generar({"clave": "k"}, tmp / "x.png", "p", tmp / "x.mp4", 5, False),
         "seedance": lambda: seedance._generar({"clave": "k"}, None, "p", tmp / "x.mp4", 5, False),
         "video con voz": lambda: ia.video_hablado("p", "9:16", tmp / "x.mp4"),
         "imagen de Gemini": lambda: ia._imagen_gemini({"clave": "k"}, "p", 512, 512),
         "música": lambda: musica.crear("una canción", "pop"),
         "voz de ElevenLabs": lambda: ia.voz_elevenlabs("hola", "v", tmp / "v.mp3"),
         "publicar en YouTube": lambda: subir.programar(str(tmp / "v.mp4"), "t")}
post_real = ia.httpx.post
ia.httpx.post = subir.httpx.post = lambda *a, **k: (_ for _ in ()).throw(AssertionError("salió a la red"))
try:
    for nombre, llamada in pagos.items():
        assert "bloqueado" in falla(llamada, error=RuntimeError), nombre
    # El crear_video del Director narra con desde_prompt.narrar: con una voz de ElevenLabs (costo no la pregunta),
    # tampoco empieza
    assert "bloqueado" in falla(desde_prompt.narrar, "hola", "eleven:abc", tmp / "v.mp3", error=RuntimeError)
    # La transcripción de OpenAI (de pago) no sale: se hace gratis en el PC (aquí falla su ffmpeg: no es audio)
    assert claves.para("transcripcion")["proveedor"] == "openai"
    (tmp / "a.mp3").write_bytes(b"no es audio")
    falla(ia.transcribir, tmp / "a.mp3", error=subprocess.CalledProcessError)
finally:
    ia.httpx.post = subir.httpx.post = post_real
claves.ARCHIVO.unlink()
# Desbloquear solo lo hace la página «Ráfaga Guardia»: ni el Director, ni el MCP, ni ninguna herramienta
llamadas = []
for archivo in [RAIZ / "app.py", RAIZ / "mcp_server.py", *(RAIZ / "motor").rglob("*.py"), *(RAIZ / "ui").rglob("*.py")]:
    for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Attribute) and nodo.attr == "desbloquear":
            llamadas.append(archivo.relative_to(RAIZ).as_posix())
assert llamadas == ["ui/paginas/guardia.py"], llamadas
assert not any("bloque" in nombre for nombre in herramientas.TODAS)
print("Bloqueo: el MCP, lo de pago del Director y las llamadas de pago no empiezan; solo la página desbloquea.")

# ---------- La integridad del código ----------
app_falsa = tmp / "Programs" / "Ráfaga Studio"
for nombre in ("app.py", "mcp_server.py", "modal_app.py", "Ráfaga Studio.bat", "motor/a.py", "ui/b.py",
               "ui/paginas/c.py"):
    (app_falsa / nombre).parent.mkdir(parents=True, exist_ok=True)
    (app_falsa / nombre).write_text(f"# {nombre}\n", encoding="utf-8")
raiz_real, manifiesto_real, local_real = guardia.RAIZ, guardia.MANIFIESTO, os.environ.get("LOCALAPPDATA")
guardia.RAIZ, guardia.MANIFIESTO = app_falsa, app_falsa / "integridad.json"
try:
    nuevo_historial()
    os.environ["LOCALAPPDATA"] = str(tmp / "otra")  # una copia de git de quien desarrolla: modo desarrollo
    r = guardia.revisar_integridad()
    assert r["estado"] == "ok" and "desarrollo" in r["texto"] and guardia.eventos() == []
    os.environ["LOCALAPPDATA"] = str(tmp)  # instalada sin manifiesto: alguien lo borró
    assert guardia.revisar_integridad()["estado"] == "aviso" and guardia.bloqueado() is None
    guardia.MANIFIESTO.write_text(json.dumps({"version": 1, "archivos": guardia.huellas(app_falsa)}), encoding="utf-8")
    r = guardia.revisar_integridad()
    assert r["estado"] == "ok" and "7 archivos" in r["texto"], r
    assert guardia._carpeta()["estado"] == "ok"
    # Lo que hay en una instalación limpia y no es código de la app no avisa: ejemplos (sin __init__), Python con sus
    # librerías, datos, las cachés __pycache__ y los documentos
    for nombre in ("ejemplos/crear.py", "python/tools/Lib/os.py", "datos/guardia.json", "motor/__pycache__/a.pyc",
                   "__pycache__/modal_app.cpython-314.pyc", "README.md", "requirements.lock"):
        (app_falsa / nombre).parent.mkdir(parents=True, exist_ok=True)
        (app_falsa / nombre).write_text("x", encoding="utf-8")
    assert guardia.revisar_integridad()["estado"] == "ok"
    extension = f"a{importlib.machinery.EXTENSION_SUFFIXES[0]}"  # a.cp314-win_amd64.pyd: se carga antes que a.py
    for cambio, deshacer in (
            (lambda: (app_falsa / "motor" / "a.py").write_text("robar()", encoding="utf-8"),
             lambda: (app_falsa / "motor" / "a.py").write_text("# motor/a.py\n", encoding="utf-8")),
            (lambda: (app_falsa / "ui" / "b.py").unlink(),
             lambda: (app_falsa / "ui" / "b.py").write_text("# ui/b.py\n", encoding="utf-8")),
            (lambda: (app_falsa / "json.py").write_text("robar()", encoding="utf-8"),  # un módulo plantado
             lambda: (app_falsa / "json.py").unlink()),
            (lambda: (app_falsa / "json.pyc").write_bytes(b"robar()"),  # Python también los carga sin su .py
             lambda: (app_falsa / "json.pyc").unlink()),
            (lambda: (app_falsa / "json.pyw").write_text("robar()", encoding="utf-8"),
             lambda: (app_falsa / "json.pyw").unlink()),
            (lambda: ((app_falsa / "json").mkdir(), (app_falsa / "json" / "__init__.py").write_text("robar()")),
             lambda: shutil.rmtree(app_falsa / "json")),  # un paquete plantado
            (lambda: (app_falsa / "motor" / extension).write_bytes(b"MZ"),
             lambda: (app_falsa / "motor" / extension).unlink()),
            (lambda: (app_falsa / "ui" / "paginas" / "plantada.py").write_text("x", encoding="utf-8"),
             lambda: (app_falsa / "ui" / "paginas" / "plantada.py").unlink()),
            (lambda: (app_falsa / "Ráfaga Studio.bat").write_text("start malo.exe", encoding="utf-8"),
             lambda: (app_falsa / "Ráfaga Studio.bat").write_text("# Ráfaga Studio.bat\n", encoding="utf-8")),
            (lambda: guardia.MANIFIESTO.write_text("{roto", encoding="utf-8"),
             lambda: guardia.MANIFIESTO.write_text(json.dumps({"version": 1, "archivos": guardia.huellas(app_falsa)}),
                                                   encoding="utf-8"))):
        nuevo_historial()
        cambio()
        r = guardia.revisar_integridad()
        assert r["estado"] == "peligro" and tipos()[-1] == "integridad", r
        assert guardia.eventos()[-1]["gravedad"] == "alta" and "código" in guardia.bloqueado()["motivo"]
        assert "reinstala" in r["texto"] and "reinstala" in guardia.bloqueado()["motivo"]  # y qué hacer
        deshacer()
        assert guardia.revisar_integridad()["estado"] == "ok"
    # El servidor MCP también lo comprueba al arrancar (quien solo usa Claude no abre la app): bloquea y rechaza
    nuevo_historial()
    (app_falsa / "motor" / "a.py").write_text("robar()", encoding="utf-8")
    mcp_server.revisar_codigo().join(60)
    assert "código" in guardia.bloqueado()["motivo"] and "bloqueado" in falla(mcp_server.listar_opciones,
                                                                              error=ToolError)
    (app_falsa / "motor" / "a.py").write_text("# motor/a.py\n", encoding="utf-8")
    os.environ["LOCALAPPDATA"] = str(tmp / "otra")  # instalada fuera del perfil
    assert guardia._carpeta()["estado"] == "peligro"
finally:
    guardia.RAIZ, guardia.MANIFIESTO = raiz_real, manifiesto_real
    if local_real is None:
        os.environ.pop("LOCALAPPDATA", None)
    else:
        os.environ["LOCALAPPDATA"] = local_real
# El generador del instalador: el mismo código que copia rafaga.iss, y nada de las pruebas
sys.path.insert(0, str(RAIZ / "instalador"))
import integridad  # noqa: E402

generado = integridad.generar(tmp / "dist" / "integridad.json")
assert {"app.py", "mcp_server.py", "modal_app.py", "Ráfaga Studio.bat", "motor/guardia.py",
        "ui/paginas/guardia.py"} <= set(generado)
assert not any(r.startswith(("pruebas/", "instalador/", "ejemplos/")) for r in generado)
assert json.loads((tmp / "dist" / "integridad.json").read_text(encoding="utf-8"))["archivos"] == generado
iss = (RAIZ / "instalador" / "rafaga.iss").read_text(encoding="utf-8-sig")
assert "instalador\\integridad.py" in iss and 'Source: "..\\dist\\integridad.json"' in iss
assert 'Source: "..\\Ráfaga Studio.bat"' in iss and 'Source: "..\\motor\\*.py"; DestDir: "{app}\\motor"; Flags: ignoreversion recursesubdirs' in iss
# Al actualizar, Inno no borra lo que la versión nueva ya no trae: sin esto, un .py viejo contaría como plantado y
# bloquearía en cada arranque (ISCC no corre en las pruebas: se comprueba el texto)
borrar = iss.split("[InstallDelete]", 1)[1].split("\n[", 1)[0]
assert all(f'Name: "{{app}}\\{n}"' in borrar for n in ("motor", "ui", "*.py", "*.pyw", "*.pyc", "*.pyd")), borrar
assert "datos" not in borrar.replace("«datos»", "")  # tus proyectos y claves nunca
print("Integridad: un archivo cambiado, uno que falta o uno de más bloquea; sin manifiesto, modo desarrollo.")

# La página de términos del instalador: TERMINOS.md pasado a RTF al compilar, sin Markdown a la vista ni frases
# cortadas por los saltos de línea del .md (antes se veían «## 9. Cambios», asteriscos y `código`)
import licencia  # noqa: E402

rtf = licencia.generar(tmp / "dist" / "licencia.rtf").read_text(encoding="ascii")
assert rtf.startswith("{\\rtf1") and "\\colortbl" not in rtf  # sin colores: el modo oscuro del asistente pinta el texto
assert not any(marca in rtf for marca in ("**", "`", "](", "## ", "|")), "Markdown en la licencia del instalador"
assert "{\\b " in rtf and "\\u8226?\\tab" in rtf  # negritas y viñetas de verdad
assert "Si alguna parte de estos t\\u233?rminos no fuera v\\u225?lida" in rtf  # el párrafo entero, no partido
assert "instalador\\licencia.py" in iss and "LicenseFile=..\\dist\\licencia.rtf" in iss and "SetupLogging=yes" in iss
try:  # una tabla no se enseña con «|»: el generador corta la compilación
    licencia.rtf("| a | b |\n|---|---|")
    raise AssertionError("debió negarse a convertir una tabla")
except SystemExit:
    pass
print("Instalador: los términos salen como texto con formato, sin Markdown.")

# ---------- La revisión completa ----------
nuevo_historial()
claves.guardar({"proveedor": "groq", "clave": "gsk_prueba", "usos": ["texto"]})
cliente = next(iter(conexion_mcp.CLIENTES))
conexion_mcp.conectar(cliente)
textos = {r["texto"]: r["estado"] for r in guardia.revisar()}
assert textos[f"{cliente}: la conexión MCP es la de esta app y arranca en modo seguro."] == "ok", textos
assert "Sin bloqueo: el estudio funciona con normalidad." in textos
if os.name == "nt":
    assert textos["Tus claves están cifradas con tu cuenta de Windows y se pueden leer."] == "ok"
config = json.loads(conexion_mcp.CLIENTES[cliente].read_text(encoding="utf-8"))
config["mcpServers"][conexion_mcp.NOMBRE]["args"] = [str(RAIZ / "mcp_server.py")]  # sin -s -E
conexion_mcp.CLIENTES[cliente].write_text(json.dumps(config), encoding="utf-8")
assert "aviso" in {r["estado"] for r in guardia._mcp()}
config["mcpServers"][conexion_mcp.NOMBRE] = {"command": "C:\\malo\\python.exe", "args": ["-s", "-E", "C:\\malo\\x.py"]}
conexion_mcp.CLIENTES[cliente].write_text(json.dumps(config), encoding="utf-8")
assert [r["estado"] for r in guardia._mcp()] == ["peligro"]
conexion_mcp.CLIENTES[cliente].write_text("{roto", encoding="utf-8")
assert [r["estado"] for r in guardia._mcp()] == ["aviso"]
# Un registro secuestrado que empieza y acaba como el bueno también es peligro: un -c o un script delante del
# mcp_server.py (corren otro código), un env con el proxy y el certificado de otro, u otro tipo de conexión
servidor = conexion_mcp.SERVIDOR
for malo in ({**servidor, "args": ["-s", "-E", "-c", "import os; os.system('calc')", servidor["args"][-1]]},
             {**servidor, "args": ["-s", "-E", "C:\\x\\otro.py", servidor["args"][-1]]},
             {**servidor, "env": {"HTTPS_PROXY": "http://127.0.0.1:8888", "SSL_CERT_FILE": "C:\\x\\ca.pem"}},
             {**servidor, "type": "http", "url": "http://127.0.0.1:9/mcp"}):
    conexion_mcp.CLIENTES[cliente].write_text(json.dumps({"mcpServers": {conexion_mcp.NOMBRE: malo}}), encoding="utf-8")
    assert [r["estado"] for r in guardia._mcp()] == ["peligro"], malo
# El ámbito local de un proyecto de Claude Code gana al de usuario: uno distinto es peligro, uno igual no, y
# «Desconectar» los quita todos (y nada más)
falso = {"command": "C:\\atacante\\python.exe", "args": ["C:\\atacante\\falso.py"]}
config = {"mcpServers": {conexion_mcp.NOMBRE: servidor, "otro": {"command": "x"}},
          "projects": {"C:/x/proyecto": {"mcpServers": {conexion_mcp.NOMBRE: falso}}, "C:/x/otro": {"mcpServers": {}}}}
conexion_mcp.CLIENTES[cliente].write_text(json.dumps(config), encoding="utf-8")
assert [r["estado"] for r in guardia._mcp()] == ["peligro"]
config["projects"]["C:/x/proyecto"]["mcpServers"][conexion_mcp.NOMBRE] = servidor
conexion_mcp.CLIENTES[cliente].write_text(json.dumps(config), encoding="utf-8")
assert [r["estado"] for r in guardia._mcp()] == ["ok"]
config["projects"]["C:/x/proyecto"]["mcpServers"][conexion_mcp.NOMBRE] = falso
conexion_mcp.CLIENTES[cliente].write_text(json.dumps(config), encoding="utf-8")
conexion_mcp.desconectar(cliente)
config = json.loads(conexion_mcp.CLIENTES[cliente].read_text(encoding="utf-8"))
assert config["mcpServers"] == {"otro": {"command": "x"}} and set(config["projects"]) == {"C:/x/proyecto", "C:/x/otro"}
assert all(conexion_mcp.NOMBRE not in p["mcpServers"] for p in config["projects"].values())
assert [r["estado"] for r in guardia._mcp()] == ["ok"] and "Ningún Claude" in guardia._mcp()[0]["texto"]
# Claude Desktop: sin «type», como lo escribe «Conectar»
escritorio = list(conexion_mcp.CLIENTES)[1]
conexion_mcp.conectar(escritorio)
assert [r["estado"] for r in guardia._mcp()] == ["ok"]
conexion_mcp.CLIENTES[escritorio].unlink()
modelo = nubes.MODELOS / "torch" / "hub" / "checkpoints" / nubes.DEMUCS[0].rsplit("/", 1)[1]
modelo.parent.mkdir(parents=True)
modelo.write_bytes(b"pickle malicioso")
assert guardia._demucs()["estado"] == "aviso"
guardia.bloquear("prueba")
assert guardia.revisar()[-1] == {"estado": "peligro", "texto": "Bloqueado: prueba", "bloqueo": True}
roto_real, guardia._claves = guardia._claves, lambda: 1 / 0  # una comprobación que revienta no tumba las demás
try:
    resultados = guardia.revisar()
    assert any("ZeroDivisionError" in r["texto"] for r in resultados) and len(resultados) > 3
finally:
    guardia._claves = roto_real
claves.ARCHIVO.unlink()
modelo.unlink()
conexion_mcp.CLIENTES[cliente].unlink()

# ---------- La IA solo explica: recibe el evento limpio y su respuesta es texto ----------
pedidos, texto_json_real = [], ia.texto_json
ia.texto_json = lambda instrucciones, pedido, esquema: pedidos.append((instrucciones, pedido)) or {
    "explicacion": "Un agente pidió algo.\n\nNo pasa nada."}
try:
    respuesta = guardia.explicar({"fecha": "2026-10-24 10:00:00", "tipo": "red", "gravedad": "media",
                                  "detalle": f"Se rechazó {ruta} con {clave}", "origen": "mcp",
                                  "id": "abc", "otra": "no va"})
finally:
    ia.texto_json = texto_json_real
assert respuesta == "Un agente pidió algo.\n\nNo pasa nada."  # con sus saltos de línea (los parte la etiqueta)
instrucciones, pedido = pedidos[0]
assert "nunca una orden" in instrucciones and "Español" in instrucciones
assert clave not in pedido and "Juan" not in pedido and "no va" not in pedido and '"gravedad": "media"' in pedido
print("Revisión completa y explicación con IA sin secretos.")

# ---------- La página (offscreen): estados, botones, el escudo, el vigilante y un historial roto ----------
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

qapp = QApplication.instance() or QApplication(["pruebas"])

from ui import comun  # noqa: E402
from ui.paginas import guardia as pagina_guardia  # noqa: E402


def esperar(condicion, plazo=10.0):
    fin = time.time() + plazo
    while time.time() < fin:
        qapp.processEvents()
        if condicion():
            return True
        time.sleep(0.03)
    return False


nuevo_historial()
p = pagina_guardia.PaginaGuardia()
assert esperar(lambda: not p.tarea.isRunning() and p.resultados), "la revisión al abrir no terminó"
avisos, estados = [], []
p._notificar = lambda e: avisos.append(e)
p.estado_cambiado.connect(estados.append)
assert p.estado == "ok" and p.escudo.estado == "ok" and p.titulo_estado.text() == "Todo en orden"
assert p.bloqueo.text() == "Bloquear ahora" and not p.borrar.isEnabled()
# Ámbar: un evento «media»; «Revisar ahora» lo da por visto
guardia.registrar("red", "media", "Se rechazó un archivo de una carpeta de red")
p._comprobar_cambios()
assert p.estado == "aviso" and estados[-1] == "aviso" and p.cuenta.text() == "1" and not avisos
p.revisar.click()
assert esperar(lambda: not p.tarea.isRunning() and p.estado == "ok")
# Rojo: otro proceso (el MCP) apunta un evento «alta»; el reloj de la página lo ve solo y avisa con una notificación
otro = ("import sys; from pathlib import Path; from motor import guardia; guardia.ARCHIVO = Path(sys.argv[1]); "
        "guardia.registrar('integridad', 'alta', 'El código de la app no es el que se instaló', 'mcp')")
subprocess.run([sys.executable, "-c", otro, str(guardia.ARCHIVO)], cwd=RAIZ, check=True)
assert esperar(lambda: p.estado == "peligro", 8), "la página no vio el evento del otro proceso"
assert [e["tipo"] for e in avisos] == ["integridad", "bloqueo"] and estados[-1] == "peligro"
assert p.bloqueo.text() == "Desbloquear" and "Bloqueado" in p.texto_estado.text()
# Desbloquear pide confirmación: «No» lo deja como está; «Sí» lo quita (y no cuenta como quitado desde fuera)
respuestas, question_real = [QMessageBox.No], QMessageBox.question
QMessageBox.question = lambda *a, **k: respuestas[0]
try:
    p.bloqueo.click()
    assert guardia.bloqueado() and p.estado == "peligro"
    respuestas[0] = QMessageBox.Yes
    p.bloqueo.click()
    assert guardia.bloqueado() is None and "bloqueo_quitado" not in tipos()
    assert esperar(lambda: not p.tarea.isRunning() and p.estado == "ok"), p.resultados  # revisa otra vez sola
    # «Bloquear ahora» no pregunta
    respuestas[0] = None
    p.bloqueo.click()
    assert guardia.bloqueado() and p.estado == "peligro"
    # Quitar el bloqueo desde fuera (editando guardia.json) no vale: se vuelve a poner y se avisa
    datos = json.loads(guardia.ARCHIVO.read_text(encoding="utf-8"))
    datos["bloqueo"] = None
    guardia.ARCHIVO.write_text(json.dumps(datos), encoding="utf-8")
    p._comprobar_cambios()
    assert guardia.bloqueado() and "bloqueo_quitado" in tipos() and avisos[-1]["tipo"] == "bloqueo_quitado"
    # Ni rompiéndolo: un guardia.json roto no tumba la página, y el bloqueo vuelve
    guardia.ARCHIVO.write_text("{roto", encoding="utf-8")
    p._comprobar_cambios()
    assert guardia.bloqueado() and p.estado == "peligro"
    # Borrar historial (pregunta): los eventos se van, el bloqueo se queda
    respuestas[0] = QMessageBox.Yes
    p.borrar.click()
    assert guardia.eventos() == [] and guardia.bloqueado() and p.lista_eventos.count() == 1  # «Sin eventos…»
    # Desbloquear para seguir
    p.bloqueo.click()
    assert guardia.bloqueado() is None
finally:
    QMessageBox.question = question_real
assert esperar(lambda: not p.tarea.isRunning())
# «Explicar con IA»: la respuesta se ve como texto bajo su evento
guardia.registrar("memoria", "media", "La memoria del estudio no guardó un dato sensible")
p._comprobar_cambios()
explicar_real = guardia.explicar
guardia.explicar = lambda evento: f"Explicación de {evento['tipo']}"
try:
    fila = p.lista_eventos.itemAt(0).widget()
    next(b for b in fila.findChildren(comun.QPushButton) if b.text() == "Explicar con IA").click()
    assert esperar(lambda: any(l.text() == "Explicación de memoria"
                               for l in p.findChildren(comun.QLabel, "explicacion")))
finally:
    guardia.explicar = explicar_real
# Una revisión que falla no tumba la página
revisar_real = guardia.revisar
guardia.revisar = lambda: 1 / 0
try:
    p.revisar.click()
    assert esperar(lambda: not p.tarea.isRunning() and any("No se pudo revisar" in r["texto"] for r in p.resultados))
    rota = pagina_guardia.PaginaGuardia()  # ni la de al abrir la app
    assert esperar(lambda: not rota.tarea.isRunning() and rota.resultados)
    rota.cerrar()
finally:
    guardia.revisar = revisar_real
# Con la app abierta dos veces: desbloquear en una no es «quitado desde fuera» para la otra (ni alarma ni vuelta al
# bloqueo); lo dice el historial, donde guardia.desbloquear lo apunta el último
p.reloj.stop()  # la página de antes no sigue los historiales nuevos de estas pruebas (los tomaría por manipulados)
nuevo_historial()
guardia.bloquear("prueba")
a, b = pagina_guardia.PaginaGuardia(), pagina_guardia.PaginaGuardia()
avisos_ab = []
a._notificar = b._notificar = avisos_ab.append
assert esperar(lambda: not a.tarea.isRunning() and not b.tarea.isRunning() and b.estado == "peligro")
QMessageBox.question = lambda *x, **k: QMessageBox.Yes
try:
    a.bloqueo.click()
    b._comprobar_cambios()
    assert guardia.bloqueado() is None and "bloqueo_quitado" not in tipos() and not avisos_ab
    assert esperar(lambda: not b.tarea.isRunning() and b.estado == "ok" and a.estado == "ok"), b.resultados
finally:
    QMessageBox.question = question_real
    a.cerrar()
    b.cerrar()
# Un mismo incidente, un aviso de cada (integridad y bloqueo), también tras cada «Desbloquear» con el código aún
# cambiado: sin una tercera notificación ni una entrada repetida en el historial
guardia.RAIZ, guardia.MANIFIESTO = app_falsa, app_falsa / "integridad.json"
(app_falsa / "motor" / "a.py").write_text("robar()", encoding="utf-8")
nuevo_historial()
avisos_uno, notificar_real = [], pagina_guardia.PaginaGuardia._notificar
pagina_guardia.PaginaGuardia._notificar = lambda self, evento: avisos_uno.append(evento["tipo"])
QMessageBox.question = lambda *x, **k: QMessageBox.Yes
try:
    c = pagina_guardia.PaginaGuardia()
    assert esperar(lambda: not c.tarea.isRunning() and c.estado == "peligro")
    esperar(lambda: False, 2)  # unos tics del reloj: ninguna revisión de más
    assert avisos_uno == ["integridad", "bloqueo"] and tipos() == ["bloqueo", "integridad"], (avisos_uno, tipos())
    c.bloqueo.click()
    assert esperar(lambda: not c.tarea.isRunning() and guardia.bloqueado() and len(avisos_uno) == 4)
    esperar(lambda: False, 2)
    assert avisos_uno == ["integridad", "bloqueo"] * 2, avisos_uno
    assert tipos() == ["bloqueo", "integridad", "desbloqueo", "bloqueo", "integridad"], tipos()
    assert "reinstala" in c.texto_estado.text()  # qué hacer, también en la página
    c._bloqueo = None
    guardia.desbloquear()
    c.cerrar()
finally:
    pagina_guardia.PaginaGuardia._notificar = notificar_real
    QMessageBox.question = question_real
    (app_falsa / "motor" / "a.py").write_text("# motor/a.py\n", encoding="utf-8")
    guardia.RAIZ, guardia.MANIFIESTO = raiz_real, manifiesto_real
# Otro programa abre guardia.json en exclusiva: la página lo enseña bloqueado (aunque su fecha no cambie) y, al
# soltarlo, no lo toma por un bloqueo quitado desde fuera
if os.name == "nt":
    nuevo_historial()
    guardia.registrar("prueba", "baja", "antes")
    d = pagina_guardia.PaginaGuardia()
    assert esperar(lambda: not d.tarea.isRunning() and d.estado == "ok")
    asa = en_exclusiva()
    try:
        d._comprobar_cambios()
        assert d.estado == "peligro" and "No se puede leer" in d.texto_estado.text()
    finally:
        k32.CloseHandle(asa)
    d._comprobar_cambios()
    assert guardia.bloqueado() is None and "bloqueo_quitado" not in tipos()
    assert esperar(lambda: not d.tarea.isRunning() and d.estado == "ok"), d.resultados
    d.cerrar()
# Con el estudio bloqueado, un trabajo con video de pago no empieza (ni pregunta el costo)
claves.guardar({"proveedor": "kling", "clave": "k" * 32, "usos": ["video", "video_voz"]})
claves.elegir_por_defecto("video", "kling")
errores, error_real = [], comun.mensaje_error
comun.mensaje_error = lambda padre, titulo, texto: errores.append(texto)
QMessageBox.question = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debió preguntar el costo"))
guardia.bloquear("prueba")
try:
    trabajo = comun.PaginaTrabajo("x", "y")
    assert trabajo._pagar_video(desde_prompt.animar_imagen, {}) is False and "bloqueado" in errores[0]
finally:
    comun.mensaje_error, QMessageBox.question = error_real, question_real
    p._bloqueo = None  # lo quita la prueba, no un programa de fuera
    guardia.desbloquear()
    claves.ARCHIVO.unlink()
    claves.AJUSTES.unlink()
p.cerrar()

# El escudo del menú cambia de color con el estado (la ventana entera, como la abre el usuario)
import app as aplicacion  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402

segoe = [f"C:/Windows/Fonts/{f}.ttf" for f in ("segoeui", "segoeuib", "seguisb", "seguiemj")]
if all(os.path.isfile(f) for f in segoe):  # sin plataforma de ventanas, Qt no carga las fuentes de Windows solo
    for fuente in segoe:
        QFontDatabase.addApplicationFont(fuente)
qapp.setStyle(aplicacion.EstiloApp())
qapp.setFont(QFont("Segoe UI", 10))
qapp.setStyleSheet(aplicacion.ESTILO)
nuevo_historial()
ventana = aplicacion.Ventana()
assert ventana.orden[-1] is ventana.guardia and ventana.escudo.text() == "Ráfaga Guardia"
assert esperar(lambda: not ventana.guardia.tarea.isRunning())
if all(os.path.isfile(f) for f in segoe):  # en un portátil (1366 × 768 menos la barra de tareas), el menú no se desplaza
    ventana.resize(1366, 728)
    ventana.show()
    menu_desplazable = ventana.findChild(aplicacion.QFrame, "barra").findChild(aplicacion.QScrollArea)
    assert esperar(lambda: menu_desplazable.height() > 400) and menu_desplazable.verticalScrollBar().maximum() == 0, \
        menu_desplazable.verticalScrollBar().maximum()
assert ventana.escudo.property("icono") == "shield-check" and "Todo en orden" in ventana.escudo.toolTip()
guardia.registrar("integridad", "alta", "plantado")
ventana.guardia._notificar = lambda e: None
ventana.guardia._comprobar_cambios()
assert ventana.escudo.property("icono") == "shield-x" and "Bloqueado o en peligro" in ventana.escudo.toolTip()
ventana.guardia.abrir.emit()  # la notificación pulsada lleva a la página
assert ventana.paginas.currentIndex() == ventana.orden.index(ventana.guardia) and ventana.escudo.isChecked()
ventana.guardia._bloqueo = None
guardia.desbloquear()
ventana.guardia.cerrar()
print("Página de Ráfaga Guardia: estados, botones, escudo, vigilante y notificaciones.")
