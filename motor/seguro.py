"""Validación de lo que entra desde fuera (MCP, interfaz, servicios): solo imágenes, audios y videos locales de verdad,
solo enlaces web públicos y descargas acotadas. Es la frontera que impide sacar archivos privados (p. ej. datos/claves.json) o
atacar la red local a través de las herramientas."""
import functools
import ipaddress
import ntpath
import os
import socket
import threading
from pathlib import Path
from urllib.parse import urlsplit

import httpcore

from . import guardia
from .idioma import t

IMAGENES = {".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp"}
AUDIOS = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".aiff", ".aif", ".wma", ".webm", ".mp4"}
VIDEOS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".ts", ".mts"}
TAMANO_MAXIMO = 2 * 1024 ** 3  # 2 GB: nada legítimo que se suba o procese aquí pesa más
TAMANO_VIDEO = 8 * 1024 ** 3  # salvo los videos del editor: una grabación larga del móvil pasa de 2 GB


def es_ruta_de_red(texto: str) -> bool:
    """\\\\servidor\\…, //servidor/…, /\\servidor… o \\\\?\\UNC\\…: Windows las trata igual (con cualquier mezcla de
    barras) y abrirlas conecta por SMB con ese servidor."""
    t = texto.replace("/", "\\")
    return t.startswith("\\\\") or ntpath.splitdrive(t)[0].startswith("\\\\")


def _enlace_a_red(ruta: str) -> bool:
    """Si algún enlace del camino (symlink o junction) lleva a una carpeta de red. Cada enlace se lee sin seguirlo, de
    la raíz hacia abajo: seguirlo (is_file, resolve, open) ya conectaría por SMB y mandaría la huella del usuario."""
    pendientes, actual = list(Path(os.path.abspath(ruta)).parts), None
    for _ in range(256):  # un bucle de enlaces no cuelga: cuenta como sospechoso
        if not pendientes:
            return False
        actual = Path(pendientes.pop(0)) if actual is None else actual / pendientes.pop(0)
        if actual.is_symlink() or actual.is_junction():
            destino = os.readlink(actual)  # «\\?\C:\…» en una junction; «\\?\UNC\servidor\…» es de red
            if es_ruta_de_red(destino if destino[4:8].upper() == "UNC\\" else destino.removeprefix("\\\\?\\")):
                return True
            pendientes = [*Path(os.path.abspath(actual.parent / destino.removeprefix("\\\\?\\"))).parts, *pendientes]
            actual = None
    return True


def _es_imagen(c: bytes) -> bool:
    return (c.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"BM"))
            or (c[:4] == b"RIFF" and c[8:12] == b"WEBP"))


def _es_audio(c: bytes) -> bool:
    return (c.startswith((b"ID3", b"fLaC", b"OggS", b"ADIF", b"\x1aE\xdf\xa3",  # ID3, FLAC, OGG/Opus, AAC, WebM
                          b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"))  # WMA (ASF)
            or (c[:4] in (b"RIFF", b"RF64") and c[8:12] == b"WAVE")
            or (c[:4] == b"FORM" and c[8:12] in (b"AIFF", b"AIFC"))
            or c[4:8] == b"ftyp"  # M4A / MP4
            or (len(c) > 1 and c[0] == 0xFF and c[1] & 0xE0 == 0xE0))  # trama MP3 o AAC (ADTS)


def es_video(c: bytes) -> bool:
    """MP4/MOV/3GP (ftyp), MKV/WebM (EBML), AVI y MPEG-TS: el byte 0x47 cada 188 bytes, o cada 192 con 4 bytes de
    marca de tiempo delante (.mts de cámara). Se piden tres seguidos: un texto que empiece por «G» no pasa."""
    return (c[4:8] == b"ftyp" or c.startswith(b"\x1aE\xdf\xa3") or (c[:4] == b"RIFF" and c[8:12] == b"AVI ")
            or c[:377:188] == b"GGG" or c[4:389:192] == b"GGG")


def _es_del_tipo(cabecera: bytes, tipos: set[str]) -> bool:
    """Que el CONTENIDO sea de verdad una imagen, un audio o un video (no basta con el nombre: un archivo de claves
    renombrado o un enlace llamado «foto.png» no pasa). Se acepta cualquier formato de la familia, porque es normal
    que un PNG venga llamado .jpg o un WAV llamado .mp3, y ffmpeg los lee igual."""
    # .mp4 y .webm son de las dos familias: el contenido de audio cuenta solo si se pide un audio puro (.mp3, .wav…);
    # si no, un WAV llamado .avi pasaría como video
    return bool((tipos & IMAGENES and _es_imagen(cabecera)) or (tipos & (AUDIOS - VIDEOS) and _es_audio(cabecera))
                or (tipos & VIDEOS and es_video(cabecera)))


def archivo_medio(ruta: str, tipos: set[str], que: str = "archivo") -> Path:
    """La ruta real, si es una imagen/audio local que existe y lo es de verdad. Si no, error claro.
    `que` es el nombre de lo que se pide (p. ej. "Canción"), para los mensajes."""
    texto = str(ruta or "").strip()
    if not texto:
        raise ValueError(t("{que}: falta elegir el archivo.", que=que.capitalize()))
    # Rutas de red se rechazan ANTES de tocar el disco: comprobarlas ya abriría una conexión SMB y Windows mandaría
    # la huella de la contraseña del usuario a ese servidor. Lo mismo si se llega a ella por un enlace del disco.
    if es_ruta_de_red(texto) or _enlace_a_red(texto):
        guardia.registrar("red", "media", t("Se rechazó un archivo de una carpeta de red: {ruta}", ruta=texto))
        raise ValueError(t("{que}: tiene que ser un archivo de este PC, no de una carpeta de red (cópialo a tu PC o "
                           "ábrelo desde una unidad con letra, como Z:): {ruta}", que=que.capitalize(), ruta=texto))
    p = Path(texto)
    if p.suffix.lower() not in tipos:
        raise ValueError(t("{que}: formato no admitido ({extension}). Valen: {tipos}.", que=que.capitalize(),
                           extension=p.suffix or t("sin extensión"), tipos=", ".join(sorted(tipos))))
    if not p.is_file():
        raise ValueError(t("{que}: no encuentro el archivo {ruta}", que=que.capitalize(), ruta=texto))
    real = p.resolve(strict=True)  # sigue accesos directos/enlaces: se valida y se usa el archivo de verdad
    if es_ruta_de_red(str(real)):  # por si un enlace de otro tipo llevó a la red: nunca se abre ni se renderiza
        guardia.registrar("red", "media", t("Se rechazó un acceso directo que lleva a una carpeta de red: {ruta}",
                                            ruta=texto))
        raise ValueError(t("{que}: tiene que ser un archivo de este PC, no de una carpeta de red (cópialo a tu PC o "
                           "ábrelo desde una unidad con letra, como Z:): {ruta}", que=que.capitalize(), ruta=texto))
    if real.suffix.lower() not in tipos:
        raise ValueError(t("{que}: el archivo apunta a otro de un tipo no admitido ({nombre}).", que=que.capitalize(),
                           nombre=p.name))
    # 8 GB solo si se piden videos (todo VIDEOS): un .mp4 pedido como audio, p. ej. para subirlo, sigue en 2 GB
    tope = TAMANO_VIDEO if VIDEOS <= tipos and real.suffix.lower() in VIDEOS else TAMANO_MAXIMO
    if real.stat().st_size > tope:
        raise ValueError(t("{que}: el archivo es demasiado grande (más de {gb} GB): {nombre}", que=que.capitalize(),
                           gb=tope // 1024 ** 3, nombre=p.name))
    with open(real, "rb") as f:
        if not _es_del_tipo(f.read(512), tipos):  # 512: MPEG-TS se reconoce por su tercer paquete (byte 388)
            guardia.registrar("archivo_falso", "media", t("Se rechazó un archivo que no es lo que dice su nombre: "
                                                          "{nombre}", nombre=p.name))
            raise ValueError(t("{que}: {nombre} no es una imagen, un audio ni un video de verdad.",
                               que=que.capitalize(), nombre=p.name))
    return real


def _ip_publica(texto: str) -> bool:
    ip = ipaddress.ip_address(texto.split("%")[0])
    if ip.version == 6:
        if ip in ipaddress.ip_network("64:ff9b:1::/48"):  # NAT64 de uso local: siempre traduce a la red interna
            return False
        # IPv4 metido dentro de una IPv6 (NAT64 64:ff9b::/96, compatible ::/96, mapeada ::ffff:): Python puede
        # llamarla «global» aunque dentro lleve 127.0.0.1 o 192.168.x.x. Se mira la IPv4 de dentro.
        if ip.ipv4_mapped or ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("::/96"):
            return _ip_publica(str(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)))
    if es_fake_ip(ip):
        from . import claves
        return claves.ajustes().get("proxy_fake_ip") is True
    return ip.is_global


def es_fake_ip(ip) -> bool:
    """198.18.0.0/15 no es una red de verdad (reservada para pruebas): los proxies «fake-ip» (Clash…) responden con ella
    a cada nombre y luego conectan a lo que diga el DNS real, también a 127.0.0.1 o a tu router. Por eso solo vale si
    el usuario lo activa a propósito en «Claves de IA» (proxy_fake_ip): con él, esta protección no frena la red local."""
    return ipaddress.ip_address(str(ip).split("%")[0]) in ipaddress.ip_network("198.18.0.0/15")


def host_publico(host: str) -> bool:
    """Que el nombre apunte solo a direcciones públicas de internet (nada de 127.0.0.1, router, red de la casa…)."""
    try:
        direcciones = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError):
        return False
    return bool(direcciones) and all(_ip_publica(d) for d in direcciones)


def enlace_web(url: str) -> str:
    """Solo enlaces http(s)."""
    texto = str(url or "").strip()
    if not texto.lower().startswith(("http://", "https://")) or not urlsplit(texto).hostname:
        raise ValueError(t("El enlace debe empezar por http:// o https://"))
    return texto


def enlace_publico(url: str) -> str:
    """http(s) hacia un host público. Se usa en cada salto que el programa pide por su cuenta."""
    texto = enlace_web(url)
    if not host_publico(urlsplit(texto).hostname):
        guardia.registrar("red_local", "media", t("Se rechazó un enlace a tu red local: {host}",
                                                  host=urlsplit(texto).hostname))
        raise ValueError(t("El enlace debe ser de un sitio público de internet (no de tu red local)."))
    return texto


class _SoloPublicas(httpcore.SyncBackend):
    """Resuelve el nombre UNA vez, exige que todas sus IP sean públicas y conecta a esa misma IP. Así no sirve cambiar
    el DNS entre la comprobación y la conexión (DNS rebinding) ni que el nombre se lea distinto (IDNA): se comprueba
    justo la dirección a la que se conecta, en cada salto de redirección."""

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            ips = [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        except (socket.gaierror, UnicodeError) as e:
            raise httpcore.ConnectError(t("no se encontró {host}: {error}", host=host, error=e))
        if not ips or not all(_ip_publica(ip) for ip in ips):
            if ips and all(es_fake_ip(ip) for ip in ips):  # que quien usa Clash sepa por qué y dónde activarlo
                guardia.registrar("fake_ip", "baja", t("Se frenó una conexión a una dirección de un proxy «fake-ip»: "
                                                       "{host}", host=host))
                raise httpcore.ConnectError(t("la dirección es de un proxy «fake-ip» (Clash…): si lo usas a propósito, "
                                              "actívalo en «Claves de IA»"))
            guardia.registrar("red_local", "media", t("Se frenó una conexión a una dirección de tu red local: {host}",
                                                      host=host))
            raise httpcore.ConnectError(t("la dirección no es pública (red local)"))
        for ip in ips:  # todas ya comprobadas: se prueba la siguiente si una no responde (p. ej. IPv6 roto)
            try:
                return super().connect_tcp(ip, port, timeout, local_address, socket_options)
            except httpcore.ConnectError as e:
                ultimo = e
        raise ultimo


@functools.cache
def _tls():
    """El contexto TLS (los certificados de confianza), preparado una sola vez: en un PC de 4 hilos crearlo cuesta 1,5 s,
    y se pagaba en cada descarga. Un SSLContext se puede usar a la vez desde varios hilos."""
    import httpx
    return httpx.create_ssl_context()


def redireccion(url: str, plazo: float = 15) -> str | None:
    """Adónde redirige `url` (o None), pidiéndolo por una conexión a una IP pública comprobada (ver _SoloPublicas).
    Sirve para seguir enlaces de «Compartir» sin que un cambio de DNS lleve la petición a la red local."""
    import httpx
    from urllib.parse import urljoin
    u = httpx.URL(enlace_web(url))
    tiempos = {"timeout": {"connect": plazo, "read": plazo, "write": plazo, "pool": plazo}}
    destino = httpcore.URL(scheme=u.raw_scheme, host=u.raw_host, port=u.port, target=u.raw_path)
    with httpcore.ConnectionPool(ssl_context=_tls(), network_backend=_SoloPublicas()) as conexiones:
        try:
            with conexiones.stream("GET", destino, headers=[(b"User-Agent", b"Mozilla/5.0")], extensions=tiempos) as r:
                if r.status not in (301, 302, 303, 307, 308):
                    return None
                return urljoin(url, next((v for k, v in r.headers if k.lower() == b"location"), b"").decode("latin-1"))
        except httpcore.ConnectError as e:
            raise ValueError(t("El enlace debe ser de un sitio público de internet (no de tu red local): {error}",
                               error=e))


def descargar(url: str, cabeceras: dict | None = None, tope: int = 50 * 1024 ** 2, plazo: float = 300) -> bytes:
    """Baja el archivo que señala un servicio de IA sin fiarse de él: solo https y solo IP públicas (ver _SoloPublicas),
    sin descomprimir (una «bomba» gzip no llena la memoria), con tope de tamaño y de tiempo TOTAL (el goteo lento no
    cuelga la app). Las cabeceras (la clave) solo viajan al primer host."""
    import httpx
    # ponytail: conexión directa, sin el proxy del sistema; con proxies «fake-ip» (Clash), solo si se activa (ver es_fake_ip).
    conexiones = httpcore.ConnectionPool(ssl_context=_tls(), network_backend=_SoloPublicas())
    resultado = {}

    def bajar():
        try:
            with conexiones:
                resultado["datos"] = _bajar(conexiones, url, cabeceras or {}, tope, plazo)
        except Exception as e:  # se relanza abajo, en el hilo que espera
            resultado["error"] = e
    hilo = threading.Thread(target=bajar, daemon=True)
    hilo.start()
    hilo.join(plazo)
    if hilo.is_alive():
        conexiones.close()  # cierra el socket: el hilo abandonado termina ya, en vez de seguir bajando hasta el tope
        raise RuntimeError(t("el servicio tarda demasiado en mandar el archivo"))
    if "error" in resultado:
        raise resultado["error"]
    return resultado["datos"]


def _bajar(conexiones: httpcore.ConnectionPool, url: str, cabeceras: dict, tope: int, plazo: float) -> bytes:
    import httpx
    from urllib.parse import urljoin
    primero = httpx.URL(url).raw_host
    tiempos = {"timeout": {"connect": 30, "read": plazo, "write": 30, "pool": 30}}
    for _ in range(6):
        u = httpx.URL(url)
        if u.scheme != "https":
            raise RuntimeError(t("el servicio mandó a bajar el archivo de una dirección que no es segura"))
        pedir = {"Accept-Encoding": "identity", **(cabeceras if u.raw_host == primero else {})}
        destino = httpcore.URL(scheme=b"https", host=u.raw_host, port=u.port, target=u.raw_path)
        try:
            with conexiones.stream("GET", destino, headers=list(pedir.items()), extensions=tiempos) as r:
                if r.status in (301, 302, 303, 307, 308):
                    salto = next((v for k, v in r.headers if k.lower() == b"location"), b"")
                    url = urljoin(url, salto.decode("latin-1"))
                    continue
                if r.status >= 400:
                    raise RuntimeError(t("el servicio respondió con el error {codigo}", codigo=r.status))
                datos = bytearray()
                for trozo in r.iter_stream():  # bytes tal como llegan: nada se descomprime
                    datos += trozo
                    if len(datos) > tope:
                        raise RuntimeError(t("el archivo del servicio es demasiado grande"))
                return bytes(datos)
        except httpcore.ConnectError as e:
            raise RuntimeError(t("no se pudo bajar el archivo: {error}", error=e))
    raise RuntimeError(t("el servicio redirigió demasiadas veces"))


def pedir(metodo: str, url: str, tope: int = 8 * 1024 ** 2, plazo: float = 300, **opciones):
    """Una petición a la API de un servicio con tope de tamaño y de tiempo TOTAL. El timeout de httpx es por lectura:
    un servidor que gotea un byte cada poco nunca corta, y uno que manda GB llena la memoria antes de .json().
    Devuelve la respuesta ya leída (con .json(), .status_code…, como httpx.request); sus fallos son httpx.HTTPError."""
    import httpx
    cliente, resultado = httpx.Client(timeout=plazo), {}

    def hacer():
        try:
            with cliente.stream(metodo, url, **opciones) as r:
                datos = bytearray()
                for trozo in r.iter_bytes():
                    datos += trozo
                    if len(datos) > tope:
                        raise httpx.ReadError(t("la respuesta del servicio es demasiado grande"), request=r.request)
                # ya descomprimida: sin las cabeceras que harían que httpx la descomprimiera otra vez
                cabeceras = [(k, v) for k, v in r.headers.multi_items()
                             if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
                resultado["r"] = httpx.Response(r.status_code, headers=cabeceras, content=bytes(datos),
                                                request=r.request)
        except Exception as e:  # se relanza abajo, en el hilo que espera
            resultado["error"] = e
    hilo = threading.Thread(target=hacer, daemon=True)
    hilo.start()
    hilo.join(plazo)
    tarde = hilo.is_alive()
    cliente.close()  # si sigue esperando, cierra su conexión: el hilo abandonado termina ya
    if tarde:
        raise httpx.ReadTimeout(t("el servicio tarda demasiado en responder"))
    if "error" in resultado:
        raise resultado["error"]
    return resultado["r"]
