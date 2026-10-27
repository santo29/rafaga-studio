"""Kling y Seedance (video de pago) sin red ni claves de verdad: python -m pruebas.video_pago"""
import base64
import os
import tempfile
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")  # los mensajes que se comprueban están en español
import httpx  # noqa: E402

from motor import ia, kling, seedance, seguro  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="rafaga-video-pago-"))
foto = tmp / "escena.png"
foto.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(40)))
FOTO64 = base64.b64encode(foto.read_bytes()).decode()
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
CDN = "https://cdn.ejemplo.com/clip.mp4"
for modulo in (kling, seedance):
    modulo.ESPERA = modulo.PAUSA = 0  # sin esperas de verdad

red, bajadas, guion = [], [], {}  # guion: (método, url) -> respuestas en orden (la última se repite)
video_bajado = [MP4]


def falsa(metodo):
    def llamar(url, headers=None, json=None, timeout=None, **k):
        assert timeout, f"sin plazo: {metodo} {url}"
        red.append((metodo, url, headers or {}, json))
        cola = guion.get((metodo, url))
        assert cola, f"petición inesperada: {metodo} {url}"
        r = cola.pop(0) if len(cola) > 1 else cola[0]
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r[0], json=r[1], request=httpx.Request(metodo, url))
    return llamar


def bajar(url, cabeceras=None, **k):
    bajadas.append((url, cabeceras))
    if isinstance(video_bajado[0], Exception):
        raise video_bajado[0]
    return video_bajado[0]


def escenario(rutas: dict):
    red.clear(), bajadas.clear(), guion.clear()
    guion.update({ruta: list(respuestas) for ruta, respuestas in rutas.items()})
    video_bajado[0] = MP4


def falla(funcion, *args, error=RuntimeError, **kw) -> Exception:
    try:
        funcion(*args, **kw)
    except error as e:
        return e
    raise AssertionError(f"debió fallar: {funcion.__name__}")


def cerca(a, b):
    return abs(a - b) < 1e-9


reales = httpx.get, httpx.post, httpx.delete, seguro.descargar, seguro.pedir
httpx.get, httpx.post, httpx.delete, seguro.descargar = falsa("GET"), falsa("POST"), falsa("DELETE"), bajar
seguro.pedir = lambda metodo, url, plazo=None, tope=None, **k: falsa(metodo)(url, timeout=plazo, **k)  # el sondeo
try:
    # ---------- Kling ----------
    SG, BJ = kling.BASES
    CLAVE = "clave-kling-de-prueba"
    info = {"clave": CLAVE, "base": SG}
    ok = (200, {"code": 0, "data": []})
    no = (401, {"code": 1002, "message": "Authentication error"})

    # Validar sin gastar: Beijing solo si Singapur dice 401
    escenario({("GET", f"{SG}/tasks?task_ids=0"): [ok]})
    assert kling.validar(CLAVE) == {"base": SG} and len(red) == 1
    assert red[0][2] == {"Authorization": f"Bearer {CLAVE}"}
    escenario({("GET", f"{SG}/tasks?task_ids=0"): [no], ("GET", f"{BJ}/tasks?task_ids=0"): [ok]})
    assert kling.validar(CLAVE) == {"base": BJ} and [u for _, u, _, _ in red] == [f"{SG}/tasks?task_ids=0",
                                                                                  f"{BJ}/tasks?task_ids=0"]
    escenario({("GET", f"{SG}/tasks?task_ids=0"): [no], ("GET", f"{BJ}/tasks?task_ids=0"): [no]})
    assert falla(kling.validar, CLAVE, error=httpx.HTTPStatusError).response.status_code == 401  # no es de Kling
    escenario({("GET", f"{SG}/tasks?task_ids=0"): [(500, {"code": 5000})]})  # fallo del servidor: Beijing no la ve
    assert falla(kling.validar, CLAVE, error=httpx.HTTPStatusError).response.status_code == 500 and len(red) == 1
    escenario({("GET", f"{SG}/tasks?task_ids=0"): [httpx.ConnectError("sin red")]})
    falla(kling.validar, CLAVE, error=httpx.HTTPError)
    assert len(red) == 1

    # Lo máximo que puede costar: el más caro de lo que queda por probar, por los segundos que se piden de verdad
    assert cerca(kling.estimar({}, 5), 0.112 * 5)  # el respaldo Turbo cuesta más que 3.0
    assert cerca(kling.estimar({"modelo_video": "kling-3.0"}, 5), 0.112 * 5)
    assert cerca(kling.estimar({"modelo_video": "kling-2.6"}, 8), 0.042 * 10)  # 2.6 y 2.5 Turbo: 5 o 10 s
    assert cerca(kling.estimar({"modelo_voz": "kling-3.0"}, 8, voz=True), 0.126 * 8)
    assert cerca(kling.estimar({"modelo_video": "kling-3.0-turbo"}, 20), 0.112 * 15)  # hasta 15 s
    assert cerca(kling.estimar({"modelo_voz": "kling-2.6"}, 8, voz=True), 0.126 * 8)  # 2.6 no habla: desde el mejor
    # Kling 4.0 no, mientras su precio sea provisional: una clave que lo tenía guardado empieza por el mejor de la lista
    assert [m["id"] for m in kling.MODELOS] == ["kling-3.0", "kling-3.0-turbo", "kling-2.6", "kling-2.5-turbo"]
    assert cerca(kling.estimar({"modelo_video": "kling-4.0", "modelo_voz": "kling-4.0"}, 8, voz=True), 0.126 * 8)

    # Animar: los modelos que la cuenta no tiene se saltan sin pagar; la clave solo va a la API, el video a la CDN
    tarea = (200, {"code": 0, "data": {"id": "860393985781006412", "status": "submitted"}})
    lista = ("GET", f"{SG}/tasks?task_ids=860393985781006412")
    hecha = (200, {"code": 0, "data": [{"id": "860393985781006412", "status": "succeeded", "outputs": [
        {"type": "image", "url": "https://cdn.ejemplo.com/portada.png"}, {"type": "video", "url": CDN}],
        "billing": [{"charge_type": "unit", "amount": "4"}]}]})
    escenario({("POST", f"{SG}/image-to-video/kling-3.0"): [(403, {"code": 1103, "message": "no permission"})],
               ("POST", f"{SG}/image-to-video/kling-3.0-turbo"): [tarea],
               lista: [(200, {"code": 0, "data": [{"status": "processing"}]}), httpx.ReadTimeout("corte"), hecha]})
    assert kling.animar(info, foto, "un gato salta", tmp / "k1.mp4") == "kling-3.0-turbo"
    assert (tmp / "k1.mp4").read_bytes() == MP4 and bajadas == [(CDN, None)]  # sin cabeceras: la clave no va a la CDN
    assert all(u.startswith(f"{SG}/") and h == {"Authorization": f"Bearer {CLAVE}"} for _, u, h, _ in red)
    cuerpo = red[1][3]
    assert cuerpo["contents"] == [{"type": "prompt", "text": "un gato salta"}, {"type": "first_frame", "url": FOTO64}]
    assert red[0][3]["settings"] == {"resolution": "720p", "duration": 5, "audio": "off"}
    assert cuerpo["options"] == {"watermark_info": {"enabled": False}}
    assert cuerpo["settings"] == {"resolution": "720p", "duration": 5}  # 3.0 Turbo no tiene ese ajuste
    escenario({("POST", f"{SG}/image-to-video/kling-2.6"): [tarea], lista: [hecha]})
    assert kling.animar({**info, "modelo_video": "kling-2.6"}, foto, "x", tmp / "k2.mp4", segundos=8) == "kling-2.6"
    assert red[0][3]["settings"] == {"resolution": "720p", "duration": 10, "audio": "off"}
    escenario({("POST", f"{SG}/image-to-video/kling-2.5-turbo"): [tarea], lista: [hecha]})
    kling.animar({**info, "modelo_video": "kling-2.5-turbo"}, foto, "x", tmp / "k3.mp4")
    assert red[0][3]["settings"] == {"resolution": "720p", "duration": 5}
    # Una base guardada que no es de Kling no recibe la clave
    escenario({("POST", f"{SG}/image-to-video/kling-3.0"): [tarea], lista: [hecha]})
    kling.animar({"clave": CLAVE, "base": "https://ladron.example", "modelo_video": "kling-3.0"}, foto, "x",
                 tmp / "k4.mp4")
    assert all(u.startswith(f"{SG}/") for _, u, _, _ in red)

    # Hablar: audio nativo donde hay ajuste, 8 s, y nunca los que no hablan a 720p
    escenario({("POST", f"{SG}/image-to-video/kling-3.0"): [tarea], lista: [hecha]})
    assert kling.hablar({**info, "modelo_voz": "kling-3.0"}, foto, 'Ana dice: "Hola"', tmp / "k5.mp4") == "kling-3.0"
    assert red[0][3]["settings"] == {"resolution": "720p", "duration": 8, "audio": "native"}
    sin_permiso = [(403, {"code": 1103})]
    escenario({("POST", f"{SG}/image-to-video/{m}"): sin_permiso for m in ("kling-3.0", "kling-3.0-turbo")})
    assert "ninguno" in str(falla(kling.hablar, info, foto, "x", tmp / "k6.mp4"))
    assert len(red) == 2  # ni 2.6 ni 2.5 Turbo
    escenario({("POST", f"{SG}/image-to-video/kling-3.0"): [(404, {"code": 1203})],
               ("POST", f"{SG}/image-to-video/kling-3.0-turbo"): [tarea], lista: [hecha]})
    assert kling.hablar(info, foto, "x", tmp / "k7.mp4") == "kling-3.0-turbo"
    assert red[0][3]["settings"] == {"resolution": "720p", "duration": 8, "audio": "native"}
    assert "audio" not in red[1][3]["settings"] and red[1][3]["settings"]["duration"] == 8
    escenario({})
    falla(kling.hablar, info, None, "x", tmp / "k8.mp4", error=ValueError)  # red de seguridad: sin imagen, ni se pide
    assert not red

    # Un paquete que no cubre un modelo (1102 en ese modelo): el siguiente, sin pagar; «sin saldo» solo si ninguno pudo
    k3 = ("POST", f"{SG}/image-to-video/kling-3.0")
    k3t = ("POST", f"{SG}/image-to-video/kling-3.0-turbo")
    escenario({k3: [(429, {"code": 1102, "message": "pack does not cover this model"})], k3t: [tarea], lista: [hecha]})
    assert kling.animar(info, foto, "x", tmp / "k8b.mp4") == "kling-3.0-turbo"
    assert [u for m, u, _, _ in red if m == "POST"] == [k3[1], k3t[1]] and len(bajadas) == 1  # una sola tarea pagada
    escenario({k3: [(429, {"code": 1102})], k3t: [tarea], lista: [hecha]})
    assert kling.hablar(info, foto, "x", tmp / "k8c.mp4") == "kling-3.0-turbo"
    info3 = {**info, "modelo_video": "kling-3.0"}
    escenario({("POST", f"{SG}/image-to-video/{m}"): [(429, {"code": 1102, "message": f"pack used up {CLAVE}"})]
               for m in ("kling-3.0", "kling-3.0-turbo", "kling-2.6", "kling-2.5-turbo")})
    e = falla(kling.animar, info3, foto, "x", tmp / "k9.mp4")
    assert type(e) is ia.SinSaldo and "saldo" in str(e) and kling.CONSOLA in str(e) and CLAVE not in str(e)
    assert len(red) == 4 and not bajadas  # todos probados, ninguno creó tarea
    escenario({k3: [(403, {"code": 1103})], k3t: [(429, {"code": 1102})]})
    assert "saldo" in str(falla(kling.hablar, info, foto, "x", tmp / "k9b.mp4")) and len(red) == 2

    # Errores con causa clara, sin pagar ni probar otro modelo
    escenario({k3: [(429, {"code": 1101, "message": "account in arrears"})]})  # la cuenta entera debe: se para aquí
    e = falla(kling.animar, info3, foto, "x", tmp / "k9c.mp4")
    assert type(e) is ia.SinSaldo and "saldo" in str(e) and len(red) == 1
    escenario({k3: [(400, {"code": 1301, "message": f"risk control {CLAVE}"})]})
    e = falla(kling.animar, info3, foto, "x", tmp / "k9.mp4")
    assert "normas de contenido" in str(e) and "no se cobró" in str(e) and CLAVE not in str(e) and len(red) == 1
    escenario({k3: [(401, {"code": 1002})]})
    assert "no aceptó la clave" in str(falla(kling.animar, info3, foto, "x", tmp / "k9.mp4"))
    escenario({k3: [(500, {"code": 5000, "message": f"eco {CLAVE}"})]})
    e = falla(kling.animar, info3, foto, "x", tmp / "k9.mp4")
    assert "500" in str(e) and CLAVE not in str(e)  # un error nunca enseña la clave
    # Límite de pedidos: espera y repite el mismo modelo; si no se libera, se dice
    escenario({k3: [(429, {"code": 1303}), (429, {"code": 1302}), tarea], lista: [hecha]})
    assert kling.animar(info3, foto, "x", tmp / "k10.mp4") == "kling-3.0"
    assert len([r for r in red if r[0] == "POST"]) == 3
    escenario({k3: [(429, {"code": 1302})]})
    assert "demasiados pedidos" in str(falla(kling.animar, info3, foto, "x", tmp / "k11.mp4"))
    assert len(red) == kling.REINTENTOS
    # Sin conexión no se creó nada; un corte después de mandar el pedido puede haberlo creado (y cobrado)
    escenario({k3: [httpx.ConnectError("sin red")]})
    assert type(falla(kling.animar, info3, foto, "x", tmp / "k12.mp4")) is RuntimeError
    escenario({k3: [httpx.ReadTimeout("lento")]})
    falla(kling.animar, info3, foto, "x", tmp / "k12.mp4", error=ia.Cobrado)

    # Ya creada: lo que no se pudo traer se cuenta como cobrado; lo que falló sin cobro, no
    for maliciosa in ("../x", "https://ladron.example/x", "a/b", "", None, "x" * 101):
        escenario({k3: [(200, {"code": 0, "data": {"id": maliciosa}})]})
        falla(kling.animar, info3, foto, "x", tmp / "k13.mp4", error=ia.Cobrado)
        assert len(red) == 1  # el id nunca llega a una URL
    fallida = {"status": "failed", "message": "risk", "billing": []}
    escenario({k3: [tarea], lista: [(200, {"code": 0, "data": [fallida]})]})
    e = falla(kling.animar, info3, foto, "x", tmp / "k14.mp4")
    assert type(e) is RuntimeError and "no se cobró" in str(e) and "risk" in str(e)
    escenario({k3: [tarea], lista: [(200, {"code": 0, "data": [{"status": "failed", "billing": [{"amount": "4"}]}]})]})
    falla(kling.animar, info3, foto, "x", tmp / "k15.mp4", error=ia.Cobrado)
    escenario({k3: [tarea], lista: [hecha]})
    video_bajado[0] = RuntimeError("el servicio respondió con el error 403")
    falla(kling.animar, info3, foto, "x", tmp / "k16.mp4", error=ia.Cobrado)
    escenario({k3: [tarea], lista: [hecha]})
    video_bajado[0] = b"<html>no es un video</html>"
    falla(kling.animar, info3, foto, "x", tmp / "k17.mp4", error=ia.Cobrado)
    assert not (tmp / "k17.mp4").exists()
    escenario({k3: [tarea], lista: [(200, {"code": 0, "data": [{"status": "succeeded", "outputs": []}]})]})
    assert "ningún video" in str(falla(kling.animar, info3, foto, "x", tmp / "k18.mp4", error=ia.Cobrado))
    plazo, kling.PLAZO = kling.PLAZO, 0  # no termina a tiempo
    escenario({k3: [tarea], lista: [(200, {"code": 0, "data": [{"status": "processing"}]})]})
    assert "a tiempo" in str(falla(kling.animar, info3, foto, "x", tmp / "k19.mp4", error=ia.Cobrado))
    kling.PLAZO = plazo
    print("Pruebas de Kling pasadas.")

    # ---------- Seedance ----------
    B = seedance.BASE
    CLAVE = "ark-0a1b2c3d-4e5f-6789-abcd-ef0123456789-AbC9z"
    info = {"clave": CLAVE}
    LISTAR = ("GET", f"{B}/contents/generations/tasks?page_size=1")
    escenario({LISTAR: [(200, {"items": []})]})
    assert seedance.validar(CLAVE) == {} and red[0][2] == {"Authorization": f"Bearer {CLAVE}"}
    escenario({LISTAR: [(401, {"error": {"code": "AuthenticationError", "message": "The API key doesn't exist"}})]})
    assert falla(seedance.validar, CLAVE, error=httpx.HTTPStatusError).response.status_code == 401
    escenario({LISTAR: [(429, {"error": {"code": "APIAccountRpmRateLimitExceeded"}})]})
    assert falla(seedance.validar, CLAVE, error=httpx.HTTPStatusError).response.status_code == 429

    S25, S20, FAST, MINI, PRO, PRO_FAST = (m["id"] for m in seedance.MODELOS)
    assert cerca(seedance.estimar({}, 5), 0.233 * 5)
    assert cerca(seedance.estimar({"modelo_video": PRO}, 5), 0.057 * 5)
    assert cerca(seedance.estimar({"modelo_video": PRO_FAST}, 1), 0.023 * 2)  # 1.0: de 2 a 12 s
    assert cerca(seedance.estimar({"modelo_video": MINI}, 1), 0.077 * 4)  # 2.x: desde 4 s
    assert cerca(seedance.estimar({"modelo_voz": MINI}, 8, voz=True), 0.077 * 8)
    assert cerca(seedance.estimar({"modelo_voz": PRO}, 8, voz=True), 0.233 * 8)  # 1.0 no habla: desde el mejor
    assert cerca(seedance.estimar({"modelo_video": S20}, 20), 0.153 * 15)  # la serie 2.0, hasta 15 s
    assert all(m["voz"] is None for m in seedance.MODELOS[4:]) and "1-5" not in str(seedance.MODELOS)

    CREAR = ("POST", f"{B}/contents/generations/tasks")
    TAREA = f"{B}/contents/generations/tasks/cgt-20261024-abc12"
    creada = (200, {"id": "cgt-20261024-abc12"})
    lista_s = (200, {"id": "cgt-20261024-abc12", "status": "succeeded", "content": {"video_url": CDN}})
    borrar = {("DELETE", TAREA): [(200, {})]}

    def cuerpos():
        return [c for m, _, _, c in red if m == "POST"]

    # Animar mudo: sin el modelo activado o con una cara real (2.x), al siguiente sin pagar; 1.0 sin generate_audio
    escenario({CREAR: [(404, {"error": {"code": "ModelNotOpen"}}),
                       (403, {"error": {"code": "OperationDenied.ServiceNotOpen"}}),
                       (404, {"error": {"code": "InvalidEndpointOrModel.NotFound"}}),
                       (400, {"error": {"code": "InputImageSensitiveContentDetected.PrivacyInformation"}}), creada],
               ("GET", TAREA): [(200, {"status": "queued"}), (200, {"status": "running"}), lista_s], **borrar})
    assert seedance.animar(info, foto, "un gato salta", tmp / "s1.mp4") == PRO
    assert (tmp / "s1.mp4").read_bytes() == MP4 and bajadas == [(CDN, None)]
    assert [c["model"] for c in cuerpos()] == [S25, S20, FAST, MINI, PRO]
    assert all(c["generate_audio"] is False for c in cuerpos()[:4]) and "generate_audio" not in cuerpos()[4]
    c = cuerpos()[4]
    assert c["content"] == [{"type": "text", "text": "un gato salta"},
                            {"type": "image_url", "role": "first_frame",
                             "image_url": {"url": f"data:image/png;base64,{FOTO64}"}}]
    assert (c["ratio"], c["duration"], c["resolution"], c["watermark"]) == ("adaptive", 5, "720p", False)
    assert red[-1][:2] == ("DELETE", TAREA)  # el registro (con la foto) no se queda en BytePlus
    assert all(u.startswith(f"{B}/") and h == {"Authorization": f"Bearer {CLAVE}"} for _, u, h, _ in red)

    # Hablar: con audio, 8 s; una cara real no se salta (1.0 no habla) y se explica
    escenario({CREAR: [creada], ("GET", TAREA): [lista_s], **borrar})
    assert seedance.hablar({**info, "modelo_voz": MINI}, foto, 'Ana dice: "Hola"', tmp / "s2.mp4") == MINI
    assert cuerpos()[0]["generate_audio"] is True and cuerpos()[0]["duration"] == 8
    escenario({CREAR: [creada], ("GET", TAREA): [lista_s], **borrar})
    seedance.hablar({**info, "modelo_voz": S25}, None, "solo texto", tmp / "s3.mp4")
    assert cuerpos()[0]["content"] == [{"type": "text", "text": "solo texto"}]
    escenario({CREAR: [(400, {"error": {"code": "InputImageSensitiveContentDetected.PrivacyInformation",
                                        "message": "may contain real person"}})]})
    e = falla(seedance.hablar, info, foto, "x", tmp / "s4.mp4")
    assert "normas de contenido" in str(e) and "real person" in str(e) and len(red) == 1
    escenario({CREAR: [(404, {"error": {"code": "ModelNotOpen"}})]})
    e = falla(seedance.hablar, info, foto, "x", tmp / "s5.mp4")
    assert "US$30" in str(e) and seedance.CONSOLA in str(e) and len(red) == 4  # solo los 2.x, ninguno pagado

    # Errores con causa clara
    info_pro = {**info, "modelo_video": PRO}
    escenario({CREAR: [(403, {"error": {"code": "AccountOverdueError", "message": "overdue"}})]})
    e = falla(seedance.animar, info_pro, foto, "x", tmp / "s6.mp4")
    assert type(e) is ia.SinSaldo and "saldo" in str(e) and "US$30" in str(e) and len(red) == 1
    escenario({CREAR: [(403, {"error": {"code": "OperationDenied.ServiceOverdue"}})]})
    assert "saldo" in str(falla(seedance.animar, info_pro, foto, "x", tmp / "s6.mp4"))
    escenario({CREAR: [(400, {"error": {"code": "InputTextSensitiveContentDetected", "message": f"bad {CLAVE}"}})]})
    e = falla(seedance.animar, info_pro, foto, "x", tmp / "s7.mp4")
    assert "normas de contenido" in str(e) and CLAVE not in str(e)
    escenario({CREAR: [(401, {"error": {"code": "AuthenticationError"}})]})
    assert "no aceptó la clave" in str(falla(seedance.animar, info_pro, foto, "x", tmp / "s8.mp4"))
    escenario({CREAR: [(429, {"error": {"code": "ModelAccountRpmRateLimitExceeded"}}), creada],
               ("GET", TAREA): [lista_s], **borrar})
    assert seedance.animar(info_pro, foto, "x", tmp / "s9.mp4") == PRO and len(cuerpos()) == 2
    escenario({CREAR: [(429, {"error": {"code": "ServerOverloaded"}})]})
    assert "demasiados pedidos" in str(falla(seedance.animar, info_pro, foto, "x", tmp / "s10.mp4"))
    assert len(red) == seedance.REINTENTOS
    escenario({CREAR: [httpx.ConnectTimeout("sin red")]})
    assert type(falla(seedance.animar, info_pro, foto, "x", tmp / "s11.mp4")) is RuntimeError
    escenario({CREAR: [httpx.RemoteProtocolError("cortado")]})
    falla(seedance.animar, info_pro, foto, "x", tmp / "s11.mp4", error=ia.Cobrado)

    # Ya creada: fallos y bloqueos no se cobran; lo que no se pudo traer, sí; el registro se borra igual
    for maliciosa in ("../x", "https://ladron.example/x", "cgt?x=1", None):
        escenario({CREAR: [(200, {"id": maliciosa})]})
        falla(seedance.animar, info_pro, foto, "x", tmp / "s12.mp4", error=ia.Cobrado)
        assert len(red) == 1
    for estado in ("failed", "expired", "cancelled"):
        escenario({CREAR: [creada], ("GET", TAREA): [(200, {"status": estado, "error": {
            "code": "OutputVideoSensitiveContentDetected", "message": "blocked"}})], **borrar})
        e = falla(seedance.animar, info_pro, foto, "x", tmp / "s13.mp4")
        assert type(e) is RuntimeError and "no se cobró" in str(e) and red[-1][0] == "DELETE"
    escenario({CREAR: [creada], ("GET", TAREA): [lista_s], ("DELETE", TAREA): [httpx.ConnectError("sin red")]})
    assert seedance.animar(info_pro, foto, "x", tmp / "s14.mp4") == PRO  # borrar es lo de menos: el video está
    escenario({CREAR: [creada], ("GET", TAREA): [lista_s], **borrar})
    video_bajado[0] = RuntimeError("no se pudo bajar el archivo")
    falla(seedance.animar, info_pro, foto, "x", tmp / "s15.mp4", error=ia.Cobrado)
    assert red[-1][0] == "DELETE"
    escenario({CREAR: [creada], ("GET", TAREA): [(200, {"status": "succeeded", "content": {}})], **borrar})
    assert "ningún video" in str(falla(seedance.animar, info_pro, foto, "x", tmp / "s16.mp4", error=ia.Cobrado))
    plazo, seedance.PLAZO = seedance.PLAZO, 0
    escenario({CREAR: [creada], ("GET", TAREA): [(200, {"status": "running"})], **borrar})
    assert "a tiempo" in str(falla(seedance.animar, info_pro, foto, "x", tmp / "s17.mp4", error=ia.Cobrado))
    assert red[-1][:2] == ("DELETE", TAREA)  # si aún estaba en cola, así se cancela
    seedance.PLAZO = plazo
    print("Pruebas de Seedance pasadas.")
finally:
    httpx.get, httpx.post, httpx.delete, seguro.descargar, seguro.pedir = reales
print("Pruebas del video de pago pasadas.")
