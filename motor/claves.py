"""Claves BYOK: el usuario pega una clave y aquí se detecta el proveedor y el mejor modelo."""
import json
import math
import os
import re
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from . import guardia
from .idioma import t

ARCHIVO = Path(__file__).resolve().parent.parent / "datos" / "claves.json"

# Proveedores compatibles con la API de OpenAI (texto). base = URL del endpoint.
OPENAI_COMPAT = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "pollinations": "https://gen.pollinations.ai/v1",
}

# Qué sabe hacer cada proveedor dentro de Ráfaga Studio.
USOS = {
    "anthropic": ["texto"],
    "openai": ["texto", "imagen", "transcripcion"],
    "groq": ["texto", "transcripcion"],
    "gemini": ["texto", "musica"],
    "deepseek": ["texto"],
    "openrouter": ["texto"],
    "xai": ["texto"],
    "replicate": ["imagen"],
    "huggingface": ["imagen", "video"],
    "pollinations": ["texto", "imagen", "video"],
    "elevenlabs": ["voz", "musica"],
    "modal": ["video"],
    "cloudflare": ["imagen"],
    "kling": ["video", "video_voz"],
    "seedance": ["video", "video_voz"],
}
# Videos de pago con su propio módulo (motor/kling.py, motor/seedance.py), los dos con el mismo contrato
VIDEO_DE_PAGO = ("kling", "seedance")
# Cómo se escribe cada marca en lo que lee el usuario (con .capitalize() salía «Elevenlabs» o «Openai»)
NOMBRES = {"anthropic": "Claude", "openai": "OpenAI", "groq": "Groq", "gemini": "Gemini", "deepseek": "DeepSeek",
           "openrouter": "OpenRouter", "xai": "xAI", "pollinations": "Pollinations", "elevenlabs": "ElevenLabs",
           "replicate": "Replicate", "huggingface": "Hugging Face", "cloudflare": "Cloudflare", "modal": "Modal",
           "kling": "Kling", "seedance": "Seedance"}


def nombre(proveedor: str) -> str:
    return NOMBRES.get(proveedor, proveedor)

# Orden de preferencia cuando hay varias claves para lo mismo (modo "automático").
PREFERENCIA = {
    "texto": ["anthropic", "openai", "gemini", "openrouter", "xai", "deepseek", "groq", "pollinations"],
    "imagen": ["cloudflare", "pollinations", "huggingface", "replicate", "openai"],  # gratis primero
    "transcripcion": ["groq", "openai"],
    "video": ["huggingface", "modal", "pollinations", "kling", "seedance"],  # gratis primero; igual que nubes.ORDEN
    "video_voz": ["gemini", "kling", "seedance"],  # escenas que hablan con su propio audio (todas de pago)
    "musica": ["gemini", "elevenlabs"],  # Lyria: ~$0.08 por canción y suena mejor; ElevenLabs: ~$0.30-0.45
}
# La IA que diseña (diseno_ia) es una de las de texto; en «auto», la misma que escribe los guiones (ver para)
PREFERENCIA["diseno"] = PREFERENCIA["texto"]

# De pago y con una clave que muchos conectan por otra cosa (Gemini, por su texto gratis): se ofrecen para elegir,
# pero el modo automático nunca los usa (ver también nubes.orden). Kling y Seedance cobran cada clip: solo eligiéndolos.
SOLO_ELIGIENDO = {"imagen": ["gemini", "openai", "replicate"],  # imágenes de pago: nunca por detrás si se acaba lo gratis
                  "video": list(VIDEO_DE_PAGO), "video_voz": list(VIDEO_DE_PAGO)}

# Opciones gratis que funcionan sin clave. "pc" = se hace en este ordenador.
GRATIS = {"imagen": "pollinations", "transcripcion": "pc", "video": "ninguno"}

AJUSTES = ARCHIVO.with_name("ajustes.json")


TOKEN_CF = r"(?:[A-Za-z0-9_-]{40}|cf[ua]t_[A-Za-z0-9_-]{40,60})"  # clásico, o cfut_/cfat_ (formato de 2026)
STRIPE = ("sk_live_", "sk_test_", "rk_live_", "rk_test_", "pk_live_", "pk_test_")  # claves de pagos: a nadie
# Secretos de otros servicios que candidatos() no conoce (GitHub, GitLab, Slack, AWS, JWT): el botón «Conectar» de
# Kling o Seedance no se los manda. ponytail: si una clave de Kling resulta empezar por «eyJ», quita la parte del JWT.
AJENAS = r"gh[opusr]_|github_pat_|glpat-|xox[abeprs]-|AKIA|ASIA|eyJ[\w-]+\.[\w-]+\."


def modulo_video(proveedor: str):
    """El módulo de Kling o Seedance. Se importa al usarlo: la app funciona aunque todavía no esté."""
    from . import kling, seedance
    return {"kling": kling, "seedance": seedance}[proveedor]


def candidatos(clave: str) -> list[str]:
    """Proveedores posibles según el formato de la clave, del más probable al menos."""
    c = clave.strip()
    # Modal: se pegan juntos el token id (ak-) y el secreto (as-), en cualquier orden
    if re.fullmatch(r"ak-[A-Za-z0-9]+[\s:;,]+as-[A-Za-z0-9]+|as-[A-Za-z0-9]+[\s:;,]+ak-[A-Za-z0-9]+", c):
        return ["modal"]
    if re.fullmatch(rf"[0-9a-f]{{32}}[\s:;,]+{TOKEN_CF}|{TOKEN_CF}[\s:;,]+[0-9a-f]{{32}}", c):
        return ["cloudflare"]  # «ID_de_cuenta token» con el formato exacto de Cloudflare
    # Solo el token (la cuenta se le pregunta a Cloudflare): el de 2026 lleva su prefijo; el clásico, 40 caracteres
    # sin el prefijo de otro servicio (ghp_ de GitHub, glpat- de GitLab…: esos nunca se mandan a Cloudflare)
    if re.fullmatch(r"cf[ua]t_[A-Za-z0-9_-]{40,60}", c) or (re.fullmatch(r"[A-Za-z0-9_-]{40}", c)
                                                             and not re.match(r"[A-Za-z]{2,10}[_-]", c)):
        return ["cloudflare"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", c):  # varias claves o texto pegados (espacio, coma, barra…): a nadie
        return []
    if c.startswith("sk-ant-"):
        return ["anthropic"]
    if c.startswith("sk-or-"):
        return ["openrouter"]
    if c.startswith("gsk_"):
        return ["groq"]
    if c.startswith("xai-"):
        return ["xai"]
    if c.startswith("AIza"):
        return ["gemini"]
    if c.startswith("r8_"):
        return ["replicate"]
    if c.startswith("hf_"):
        return ["huggingface"]
    if c.startswith(STRIPE):
        return []  # claves de Stripe (pagos): nunca se envían a ningún proveedor de IA
    # ElevenLabs y Pollinations usan sk_ (OpenAI usa sk-), igual que muchos servicios de pago (Openpay, Cartesia…).
    # Solo se aceptan sus formatos exactos: ElevenLabs, 48 hexadecimales; Pollinations, letras y números sin «_»
    # (no solo hexadecimal, que es el formato de Openpay). Lo demás no se manda a nadie.
    if re.fullmatch(r"sk_[0-9a-f]{48}", c):
        return ["elevenlabs"]
    if re.fullmatch(r"sk_[A-Za-z0-9]{16,128}", c) and not re.fullmatch(r"sk_[0-9a-f]+", c):
        return ["pollinations"]
    if c.startswith("sk_"):
        return []
    if c.startswith(("sk-proj-", "sk-svcacct-", "sk-admin-")):  # formatos que solo usa OpenAI
        return ["openai"]
    if re.match(r"sk-[a-z]{2,5}-", c):  # sk-lf-… (Langfuse) y parecidos: claves de otros servicios
        return []
    if re.fullmatch(r"sk-[0-9a-f]{32}", c):  # el formato de DeepSeek (DashScope de Alibaba usa el mismo: no se
        return ["deepseek"]                   # pueden distinguir; quien la pegue aquí la manda a DeepSeek)
    if c.startswith("sk-"):  # las sk- antiguas de OpenAI (Stability o Moonshot usan el mismo formato: van a OpenAI)
        return ["openai"]
    # Seedance (BytePlus ModelArk): «ark-», un UUID en minúsculas y 5 letras o números; solo Ark lo usa. Su formato
    # antiguo (el UUID solo) y las claves de Kling (sin formato conocido) no se adivinan: se conectan con su botón.
    if re.fullmatch(r"ark-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-[A-Za-z0-9]{5}", c):
        return ["seedance"]
    return []


def _ids_modelos(proveedor: str, clave: str) -> list[dict]:
    """Lista los modelos que la clave puede usar. Lanza excepción si la clave no vale."""
    if proveedor == "anthropic":
        r = httpx.get("https://api.anthropic.com/v1/models?limit=100",
                      headers={"x-api-key": clave, "anthropic-version": "2023-06-01"}, timeout=20)
    elif proveedor == "replicate":
        r = httpx.get("https://api.replicate.com/v1/account",
                      headers={"Authorization": f"Bearer {clave}"}, timeout=20)
        r.raise_for_status()
        return []
    elif proveedor == "huggingface":
        r = httpx.get("https://huggingface.co/api/whoami-v2",
                      headers={"Authorization": f"Bearer {clave}"}, timeout=20)
        r.raise_for_status()
        return []
    elif proveedor == "cloudflare":
        from .ia import cloudflare_partes
        cuenta, token = cloudflare_partes(clave)
        r = httpx.get(f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/models/search?per_page=1",
                      headers={"Authorization": f"Bearer {token}"}, timeout=20)
        r.raise_for_status()
        return []
    elif proveedor == "elevenlabs":
        r = httpx.get("https://api.elevenlabs.io/v1/models", headers={"xi-api-key": clave}, timeout=20)
        # Sin «Models: Read» ElevenLabs ya dijo que la clave es suya (nombra el permiso que le falta), y la app no usa
        # esta lista ni para narrar ni para la música: una clave hecha solo con esos permisos se conecta igual
        if r.status_code in (401, 403) and clasificar(r.status_code, r.text) == "permiso":
            return []
        r.raise_for_status()
        return []
    elif proveedor == "modal":
        import sys
        # -P: no carga un modal.py que haya en la carpeta de trabajo
        r = subprocess.run([sys.executable, "-P", "-m", "modal", "app", "list"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=modal_env(clave), timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode:
            # Las líneas de aviso de Python (DeprecationWarning) no explican nada: solo el mensaje de Modal
            motivo = " ".join(l for l in r.stderr.splitlines() if "Warning" not in l and "set_event_loop" not in l)
            motivo = " ".join(re.sub(r"[─│┌┐└┘]", " ", motivo).split())  # sin el recuadro que dibuja la consola
            raise RuntimeError(t("Modal rechazó el token ({motivo}). Comprueba que copiaste las dos partes enteras "
                                 "(ak-… y as-…) del token que acabas de crear.",
                                 motivo=motivo[-200:] or t("sin detalle")))
        return []
    elif proveedor in VIDEO_DE_PAGO:
        # No listan modelos: su módulo comprueba la clave sin gastar (401 = no es suya) y da lo que se guarda con ella
        # (p. ej. la región de Kling), que va como único elemento de la lista
        return [modulo_video(proveedor).validar(clave)]
    else:
        r = httpx.get(f"{OPENAI_COMPAT[proveedor]}/models",
                      headers={"Authorization": f"Bearer {clave}"}, timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])


NO_CHAT = re.compile(r"embed|tts|whisper|transcri|audio|realtime|image|dall-e|moderation|search|"
                     r"guard|vision-preview|instruct|babbage|davinci|computer|codex|veo|imagen|lyria|aqa|"
                     r"video|sfx|seedance|seedream|flux|wan-|kling|minimax-h")


def elegir_modelo_texto(proveedor: str, modelos: list[dict]) -> str | None:
    ids = [m["id"].removeprefix("models/") for m in modelos]
    if proveedor == "anthropic":
        # Opus 5.5 es el modelo por defecto; si la cuenta no lo tiene, el Opus más nuevo (la lista viene del más nuevo al más viejo).
        if "claude-opus-5-5" in ids:
            return "claude-opus-5-5"
        return next((i for i in ids if "opus" in i), ids[0] if ids else None)
    if proveedor == "gemini":
        # «gemini-flash-latest» es siempre el Flash estable más nuevo (el de más cuota gratis); si no, el Flash con el
        # número más alto. Por orden alfabético salía Gemma (un modelo abierto más flojo, «gemma» > «gemini»)
        if "gemini-flash-latest" in ids:
            return "gemini-flash-latest"
        flash = [i for i in ids if re.fullmatch(r"gemini-\d+(\.\d+)?-flash", i)]
        if flash:
            return max(flash, key=lambda i: float(re.search(r"\d+(\.\d+)?", i).group()))
    chat = [m for m in modelos if not NO_CHAT.search(m["id"].lower())]
    # ponytail: "el más nuevo" = mayor fecha de creación, o el id más alto si el proveedor no la da.
    # Si un proveedor publica modelos experimentales más nuevos que sus estables, fijar aquí una lista preferida.
    chat.sort(key=lambda m: (m.get("created") or 0, m["id"]), reverse=True)
    sin_variantes = [m for m in chat if not re.search(r"mini|nano|lite|preview|exp", m["id"])]
    elegido = (sin_variantes or chat or [None])[0]
    return elegido["id"].removeprefix("models/") if elegido else None


def elegir_modelo_video_voz(ids: list[str]) -> str | None:
    """El modelo de video con voz más nuevo que ofrece la clave de Gemini, entre los de precio conocido (Flash
    estable: ia.PRECIO_OMNI). Así, cuando Google saque una versión nueva, el estudio la usa sin cambiar el código, y el
    costo que se avisa sigue siendo el real. ponytail: Pro y preview no entran hasta conocer su precio."""
    def version(i):
        m = re.fullmatch(r"gemini-omni-(\d+(?:\.\d+)*)-flash", i)
        return m and tuple(int(n) for n in m[1].split("."))  # 1.10 es más nuevo que 1.9
    validos = [i for i in (i.removeprefix("models/") for i in ids) if version(i)]
    return max(validos, key=version) if validos else None


def elegir_modelo_imagen_gemini(ids: list[str]) -> str | None:
    """El modelo de imágenes de la clave de Gemini entre los de precio conocido (ia.PRECIO_IMAGEN_GEMINI): el Nano
    Banana estable más nuevo («gemini-nano-banana-X», mejor y más barato) y, si no lo hay, el Flash Image más nuevo.
    ponytail: Pro, Lite y preview no entran hasta conocer y anunciar su precio."""
    ids = [i.removeprefix("models/") for i in ids]
    for patron in (r"gemini-nano-banana-(\d+(?:\.\d+)*)", r"gemini-(\d+(?:\.\d+)*)-flash-image"):
        versiones = {i: tuple(int(n) for n in m[1].split(".")) for i in ids if (m := re.fullmatch(patron, i))}
        if versiones:
            return max(versiones, key=versiones.get)  # 2.10 es más nuevo que 2.9
    return None


def elegir_modelo_imagen(proveedor: str, modelos: list[dict]) -> str | None:
    if proveedor == "openai":
        ids = sorted((m["id"] for m in modelos if m["id"].startswith("gpt-image")), reverse=True)
        return ids[0] if ids else ("dall-e-3" if any(m["id"] == "dall-e-3" for m in modelos) else None)
    if proveedor == "replicate":
        return "black-forest-labs/flux-schnell"
    if proveedor == "huggingface":
        return "black-forest-labs/FLUX.1-schnell"
    if proveedor == "cloudflare":
        return "@cf/black-forest-labs/flux-1-schnell"
    if proveedor == "pollinations":
        return "tongyi-mai/z-image-turbo"  # alta calidad y el más barato: el saldo gratis de la cuenta rinde más
    return None


MODELO_VIDEO = {
    "huggingface": "zerogpu-aoti/wan2-2-fp8da-aoti-faster",  # Wan 2.2 con la cuota diaria gratis de GPU
    "pollinations": "alibaba/wan-2.2-fast",                   # gasta saldo (pollen) de la cuenta
    "modal": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",               # en tu nube de Modal ($30 gratis al mes)
}  # Kling y Seedance: el mejor de su catálogo (MODELOS de su módulo, que lleva sus precios), ver detectar


def modal_env(clave: str) -> dict:
    """Variables de entorno para Modal a partir de 'ak-… as-…' (en cualquier orden y separador)."""
    import os
    token_id = re.search(r"ak-[A-Za-z0-9]+", clave).group()
    secreto = re.search(r"as-[A-Za-z0-9]+", clave).group()
    return {**os.environ, "MODAL_TOKEN_ID": token_id, "MODAL_TOKEN_SECRET": secreto, "PYTHONIOENCODING": "utf-8"}


def voces_elevenlabs(clave: str) -> list[dict]:
    """Las voces de la cuenta (propias, guardadas y por defecto)."""
    voces, token = [], None
    while True:
        r = httpx.get("https://api.elevenlabs.io/v2/voices", headers={"xi-api-key": clave}, timeout=30,
                      params={"page_size": 100, **({"next_page_token": token} if token else {})})
        r.raise_for_status()
        d = r.json()
        voces += [{"id": v["voice_id"], "nombre": v["name"],
                   "acento": (v.get("labels") or {}).get("accent", "")} for v in d["voices"]]
        token = d.get("next_page_token")
        if not d.get("has_more") or not token:
            return voces


class NoConecta(ValueError):
    """Por qué una clave no se conectó. estado: el de ESTADOS que lo explica (clave, permiso, sin_conexion…) o
    «formato». La página lo pone de título: antes todo salía «Clave no válida», también sin internet o con una clave
    buena a la que le faltaba un permiso."""

    def __init__(self, texto: str, estado: str = "error"):
        super().__init__(texto)
        self.estado = estado


def _permiso(detalle: str) -> str:
    """El permiso que falta según el servicio, como lo enseña su web: «missing the permission voices_read» →
    «Voices: Read»; el de una clave restringida de OpenAI, tal cual («Missing scopes: api.model.read»). "" si no lo
    dice (un «no permission to access» no nombra ninguno)."""
    m = re.search(r"missing[_ ](?:the )?permissions?[\s:]+(\w+)|missing scopes?:\s*([\w.]+)", detalle, re.IGNORECASE)
    if not m:
        return ""
    if m[2]:
        return m[2].rstrip(".")
    que, _, nivel = m[1].lower().rpartition("_")
    return f"{que.replace('_', ' ').capitalize()}: {nivel.capitalize()}" if que and nivel in ("read", "write") \
        else m[1].replace("_", " ").capitalize()


def _sin_red(e: Exception) -> bool:
    """Sin internet, «modal app list» también falla (o no acaba): no es que el token de Modal no valga."""
    return isinstance(e, subprocess.TimeoutExpired) or \
        bool(re.search(r"\bconnect|network|timed? ?out|resolve|getaddrinfo", str(e), re.IGNORECASE))


def _voces_al_conectar(clave: str) -> tuple[list[dict], str]:
    """Las voces de la cuenta de ElevenLabs y, si la clave no puede verlas, qué pasa. Sin «Voices: Read» la clave sirve
    igual (la música no lo necesita): se conecta sin voces y se dice, en vez de rechazarla."""
    from .ia import motivo  # aquí: ia importa este módulo
    try:
        return voces_elevenlabs(clave), ""
    except httpx.HTTPStatusError as e:
        detalle = motivo(e.response)
        # Un 403 llano también: la clave ya listó los modelos, así que lo que le niegan son las voces
        if e.response.status_code != 403 and clasificar(e.response.status_code, detalle) != "permiso":
            raise
        return [], t("La clave de ElevenLabs quedó conectada, pero le falta el permiso «{permiso}»: tus voces de "
                     "ElevenLabs no saldrán para narrar (la música no lo necesita). Para elegirlas, dale ese permiso "
                     "a la clave en la web de ElevenLabs (botón «Conseguir clave ↗») y vuelve a conectarla.",
                     permiso=_permiso(detalle) or "Voices: Read")


def limpiar(clave: str) -> str:
    """Lo que se pega, como lo entiende candidatos(). El token de Modal tiene dos partes con prefijo propio (ak- y
    as-) y llega de muchas formas: la orden «modal token set --token-id ak-… --token-secret as-…» que da Modal, con
    comillas, con etiquetas, en dos líneas… Si hay exactamente una de cada, se sacan solo esas dos."""
    c = clave.strip()
    ids, secretos = re.findall(r"\bak-[A-Za-z0-9]+", c), re.findall(r"\bas-[A-Za-z0-9]+", c)
    if len(ids) == 1 and len(secretos) == 1 and len(c) <= 500:
        return f"{ids[0]} {secretos[0]}"
    # Cloudflare: el ID de cuenta y el token copiados con texto alrededor («Account ID: …», la orden curl de su
    # página «Use REST API»…). Si hay exactamente uno de cada, se sacan solo esos dos.
    if 72 < len(c) <= 2000 and not candidatos(c):
        cuentas = set(re.findall(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", c))
        tokens = set(re.findall(rf"(?<![A-Za-z0-9_-]){TOKEN_CF}(?![A-Za-z0-9_-])", c)) - cuentas
        if len(cuentas) == 1 and len(tokens) == 1:
            return f"{cuentas.pop()} {tokens.pop()}"
        # Solo el token (p. ej. la orden curl de «verificar token»): se saca, y detectar pide la cuenta si hace falta.
        # Solo con el prefijo de Cloudflare: una palabra cualquiera de 40 letras en un texto no es una clave
        if not cuentas and len(tokens) == 1 and re.match(r"cf[ua]t_", next(iter(tokens))):
            return tokens.pop()
    return c


def _cuenta_cloudflare(token: str) -> str:
    """El ID de la única cuenta a la que da acceso el token (si Cloudflare lo dice; si no, se pide pegarlo)."""
    falta = t("Pega también tu Account ID junto al token, separados por un espacio. Está en la página principal de "
              "tu cuenta de Cloudflare, a la derecha (32 letras y números).")
    try:
        r = httpx.get("https://api.cloudflare.com/client/v4/accounts", headers={"Authorization": f"Bearer {token}"},
                      timeout=20)
    except httpx.HTTPError:
        raise NoConecta(t("Sin conexión con {servicio}. Revisa tu internet e inténtalo de nuevo.",
                          servicio=nombre("cloudflare")), "sin_conexion") from None
    if r.status_code in (401, 403):
        raise NoConecta(t("Cloudflare no acepta ese token (¿se copió entero?). {falta}", falta=falta), "clave")
    try:
        cuentas = {str(a.get("id")) for a in r.json().get("result") or [] if isinstance(a, dict)}
    except (ValueError, AttributeError):
        cuentas = set()
    cuentas = {c for c in cuentas if re.fullmatch(r"[0-9a-f]{32}", c)}
    if r.status_code >= 400 or len(cuentas) != 1:
        raise NoConecta(falta, "formato")  # falta una parte de lo que se pega, como con Modal
    return cuentas.pop()


def detectar(clave: str, proveedor: str | None = None) -> dict:
    """Identifica el proveedor de la clave, la valida contra su API y elige los modelos.
    proveedor: Kling o Seedance, elegido por el usuario con su botón. Sus claves no tienen un formato que se pueda
    reconocer sin adivinar: se comprueban solo con el elegido, y nunca se le manda una que parece de otro servicio."""
    if proveedor:
        clave = clave.strip()
        # su formato no se conoce: cualquier token sin espacios (también base64 o JWT) de un largo razonable
        if proveedor not in VIDEO_DE_PAGO or not re.fullmatch(r"[A-Za-z0-9._~+/=-]{8,512}", clave):
            raise NoConecta(t("Pega solo la clave, sin espacios ni texto alrededor."), "formato")
        # ponytail: si las claves de Kling resultan medir 40 caracteres (como el token clásico de Cloudflare), esta
        # regla las rechaza: entonces hay que dejar pasar ese caso aquí.
        if candidatos(clave) not in ([], [proveedor]) or clave.startswith(STRIPE) or re.match(AJENAS, clave):
            # «baja»: lo hace la persona al pegar la clave en el cuadro equivocado y no se manda (sin escudo ámbar)
            guardia.registrar("clave_ajena", "baja", t("Se rechazó una clave de otro servicio pegada en «Conectar» "
                                                        "de {proveedor}: no se mandó.", proveedor=nombre(proveedor)))
            raise NoConecta(t("Esa clave es de otro servicio, no de {proveedor}: pégala en el cuadro de arriba, que "
                              "la reconoce sola.", proveedor=nombre(proveedor)), "formato")
        opciones = [proveedor]
    else:
        clave = limpiar(clave)
        opciones = candidatos(clave)
    if not opciones and re.fullmatch(r"a[ks]-[A-Za-z0-9]+", clave):
        raise NoConecta(t("Es un token de Modal, pero falta la otra parte: pega juntas las dos, la que empieza por "
                          "«ak-» y la que empieza por «as-», separadas por un espacio (o la orden «modal token set "
                          "…» entera que te da Modal)."), "formato")
    if not opciones:  # qué llegó (largo y principio), para saber qué se pegó sin enseñar la clave entera
        raise NoConecta(t("No reconozco el formato de esta clave (llegaron {n} caracteres que empiezan por "
                          "«{inicio}…»). Pega solo la clave, sin espacios ni texto alrededor. Si es de Kling o "
                          "Seedance, usa su botón «Conectar» en la lista de servicios.", n=len(clave),
                          inicio=clave[:6]), "formato")
    if opciones == ["cloudflare"] and not re.search(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", clave):
        clave = f"{_cuenta_cloudflare(clave)} {clave}"  # solo pegó el token: su cuenta se le pregunta a Cloudflare
    ultimo_error = None
    for proveedor in opciones:
        servicio = nombre(proveedor)
        try:
            modelos = _ids_modelos(proveedor, clave)
            voces, aviso = _voces_al_conectar(clave) if proveedor == "elevenlabs" else ([], "")
        except ImportError:  # esta copia de la app aún no trae su conexión
            raise ValueError(t("Esta versión de Ráfaga Studio todavía no trae {proveedor}: actualízala.",
                               proveedor=servicio)) from None
        except httpx.HTTPStatusError as e:
            from .ia import motivo  # aquí: ia importa este módulo
            # limpiar: el cuerpo de la respuesta va a la ventana y a la consola, y hay servicios que repiten la clave
            codigo, detalle = e.response.status_code, guardia.limpiar(motivo(e.response))
            respuesta = str(codigo) if detalle == str(codigo) else f"{codigo}: {detalle}"
            # 403: el servicio no deja usar la clave (no hay que probarla con otro proveedor, y reintentar no lo arregla)
            estado = "permiso" if codigo == 403 else clasificar(codigo, detalle)
            if estado == "clave":
                # Solo si ESTE proveedor rechaza la clave se prueba con el siguiente: así la clave no se manda a otro
                # proveedor por un fallo de red o del servidor.
                ultimo_error = t("{servicio} no acepta esta clave ({respuesta}). Comprueba que la copiaste entera, o "
                                 "crea otra con «Conseguir clave ↗» y conéctala.", servicio=servicio,
                                 respuesta=respuesta)
                continue
            if estado == "permiso":
                permiso = _permiso(detalle)
                texto = t("La clave de {servicio} vale, pero le falta el permiso «{permiso}». En la web de {servicio} "
                          "(botón «Conseguir clave ↗»), edita la clave y dale ese permiso, o crea una con acceso "
                          "completo; luego vuelve a conectarla.", servicio=servicio, permiso=permiso) if permiso else \
                    t("{servicio} no deja usar esta clave ({respuesta}). En la web de {servicio} (botón «Conseguir "
                      "clave ↗»), revisa los permisos de la clave o crea una con acceso completo; luego vuelve a "
                      "conectarla.", servicio=servicio, respuesta=respuesta)
                if proveedor == "cloudflare":  # el ID de una zona también mide 32: con él, Cloudflare dice 403
                    texto += " " + t("Comprueba también que el ID de cuenta es el de tu cuenta (no el de una zona).")
            elif estado in ("sin_saldo", "sin_cuota"):
                texto = f"{frase(proveedor, estado)} ({respuesta}). {paso(proveedor, estado)}"
            else:
                texto = t("{proveedor} no respondió bien ({codigo}); inténtalo de nuevo.", proveedor=servicio,
                          codigo=respuesta)
            raise NoConecta(texto, estado) from None
        except httpx.RequestError:  # también las redirecciones sin fin de un portal wifi o un proxy
            raise NoConecta(t("Sin conexión con {servicio}. Revisa tu internet e inténtalo de nuevo.",
                              servicio=servicio), "sin_conexion") from None
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:  # Modal (único candidato de su formato)
            if _sin_red(e):
                raise NoConecta(t("Sin conexión con {servicio}. Revisa tu internet e inténtalo de nuevo.",
                                  servicio=servicio), "sin_conexion") from None
            ultimo_error = str(e)  # Modal rechazó el token: su motivo ya va en claro
            continue
        usos = USOS[proveedor]
        info = {**(modelos[0] if proveedor in VIDEO_DE_PAGO else {}), "proveedor": proveedor, "clave": clave,
                "usos": usos}
        if "texto" in usos:
            info["modelo_texto"] = elegir_modelo_texto(proveedor, modelos)
        if "imagen" in usos:
            info["modelo_imagen"] = elegir_modelo_imagen(proveedor, modelos)
        if "transcripcion" in usos:
            info["modelo_transcripcion"] = "whisper-large-v3-turbo" if proveedor == "groq" else "whisper-1"
        if "video" in usos:
            info["modelo_video"] = MODELO_VIDEO.get(proveedor) or modulo_video(proveedor).MODELOS[0]["id"]
        if "video_voz" in usos:  # el mejor de los que hablan; las animaciones lo cambian por el último que funcionó
            info["modelo_voz"] = next((m["id"] for m in modulo_video(proveedor).MODELOS if m["voz"] is not None), None)
        if "musica" in usos:
            info["modelo_musica"] = "music_v2_5" if proveedor == "elevenlabs" else "lyria-3.5"
        if proveedor == "elevenlabs":
            info["modelo_voz"] = "eleven_multilingual_v2"  # el que admite tiempos por palabra para los subtítulos
            info["voces"] = voces
        if aviso:  # lo que la página dice al conectarla (no se guarda)
            info["aviso"] = aviso
        return info
    raise NoConecta(ultimo_error, "clave")


CIFRADO = "DPAPI:"  # prefijo de claves.json cifrado con la cuenta de Windows del usuario


def _dpapi(datos: bytes, cifrar: bool) -> bytes:
    """Cifra o descifra con DPAPI (la protección de Windows ligada a la cuenta del usuario): solo esta cuenta en este
    PC puede leer las claves; otra cuenta, un programa aislado o una copia del archivo en otro equipo no."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buffer = ctypes.create_string_buffer(datos, len(datos))
    entrada, salida = Blob(len(datos), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), Blob()
    funcion = ctypes.windll.crypt32.CryptProtectData if cifrar else ctypes.windll.crypt32.CryptUnprotectData
    if not funcion(ctypes.byref(entrada), None, None, None, None, 0x1, ctypes.byref(salida)):  # 0x1: sin ventanas
        raise OSError(t("Windows no pudo cifrar o descifrar las claves"))
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def _reemplazar(archivo: Path, texto: str) -> None:
    """Escribe de forma atómica: quien lo lee a la vez (otro hilo, el MCP) ve el archivo viejo o el nuevo, nunca uno
    vacío o a medias, y un corte de luz no lo deja roto. Un ajustes.json leído a medias es «Automático»: mandaría tu
    foto al Space público aunque elegiste otra cosa."""
    import tempfile
    archivo.parent.mkdir(exist_ok=True)
    # Temporal único: la app y el MCP pueden escribir a la vez sin pisarse el archivo a medio escribir.
    fd, temporal = tempfile.mkstemp(dir=archivo.parent, prefix=archivo.stem + "-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texto)
    for _ in range(20):  # otro proceso puede estar leyéndolo justo ahora (Windows lo bloquea un instante)
        try:
            os.replace(temporal, archivo)
            return
        except PermissionError:
            time.sleep(0.05)
    try:
        os.replace(temporal, archivo)
    except OSError:
        Path(temporal).unlink(missing_ok=True)  # sin dejar un «…-xxxx.tmp» en datos/ por cada intento fallido
        raise


def _escribir(todas: dict) -> None:
    """Guarda las claves cifradas, de forma atómica."""
    import base64
    texto = json.dumps(todas, indent=2)
    if os.name == "nt":
        texto = CIFRADO + base64.b64encode(_dpapi(texto.encode("utf-8"), cifrar=True)).decode("ascii")
    guardia.anotar_claves(texto)  # antes de escribir: así Guardia sabe que este cambio lo hizo la app
    _reemplazar(ARCHIVO, texto)


class NoSeDescifra(Exception):
    """Windows no puede descifrar claves.json ahora mismo: no es que esté dañado (ver _leer)."""


def _descifrar(texto: str) -> dict:
    """Lo que hay en claves.json (o en una copia apartada). NoSeDescifra si Windows no puede descifrarlo ahora mismo;
    ValueError si el archivo está dañado."""
    import base64
    claro = texto
    if texto.startswith(CIFRADO):
        cifrado = base64.b64decode(texto[len(CIFRADO):])  # base64 roto: dañado (ValueError)
        try:
            claro = _dpapi(cifrado, cifrar=False).decode("utf-8")
        except OSError:
            raise NoSeDescifra from None
    todas = json.loads(claro) if claro.strip() else {}
    if not isinstance(todas, dict):
        raise ValueError("formato inesperado")
    return todas


def _leer() -> dict:
    """Las claves. Si Windows no puede descifrarlas AHORA (perfil a medio cargar, otra cuenta, la carpeta sincronizada
    desde otro PC), NoSeDescifra y el archivo no se toca: las claves pueden estar bien y se leen en cuanto se pueda."""
    import base64
    try:
        texto = ARCHIVO.read_text(encoding="utf-8-sig")  # -sig: un BOM no debe impedir leer claves antiguas
    except FileNotFoundError:
        return {}
    guardia.vigilar_claves(texto)  # ¿lo escribió otro programa?
    try:
        todas = _descifrar(texto)
    except ValueError:
        # Dañado de verdad: se aparta con un nombre único (nunca pisa otra copia) y la app arranca sin claves.
        # Si estaba en claro, la copia apartada queda cifrada. La pantalla de Claves avisa de que existe.
        guardia.registrar("claves_danadas", "media", t("El archivo de tus claves estaba dañado: se apartó y la app "
                                                       "siguió sin claves."))
        apartado = ARCHIVO.with_name(f"claves.danado-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
        if os.name == "nt" and not texto.startswith(CIFRADO):
            apartado.write_text(CIFRADO + base64.b64encode(_dpapi(texto.encode("utf-8"), cifrar=True)).decode("ascii"),
                                encoding="utf-8")
            ARCHIVO.unlink()
        else:
            ARCHIVO.replace(apartado)
        return {}
    if todas and not texto.startswith(CIFRADO):
        _escribir(todas)  # claves de una versión anterior en texto plano: se cifran ahora mismo
    return todas


def cargar() -> dict:
    try:
        return _leer()
    except NoSeDescifra:  # Windows no puede descifrarlas ahora: la app sigue sin claves y el archivo queda como está
        guardia.registrar("claves_dpapi", "media", t("Windows no pudo descifrar tus claves guardadas (¿otra cuenta u "
                                                     "otro PC?): la app siguió sin ellas."))
        return {}


def _leer_para_cambiar() -> dict:
    """Para guardar o quitar una clave: nunca se pisa un claves.json que ahora no se puede descifrar."""
    try:
        return _leer()
    except NoSeDescifra:
        guardia.registrar("claves_dpapi", "media", t("Windows no pudo descifrar tus claves guardadas (¿otra cuenta u "
                                                     "otro PC?): la app siguió sin ellas."))
        raise ValueError(t("Windows no puede descifrar ahora tus claves guardadas (¿abriste la app desde otra cuenta "
                           "u otro PC?). No se tocan: cierra la sesión de Windows, vuelve a entrar y prueba otra "
                           "vez. Si tus claves vienen de otro PC, saca el archivo claves.json de la carpeta «datos» de la app y "
                           "vuelve a conectarlas en «Claves de IA».")) from None


def apartadas() -> list[Path]:
    """Archivos de claves que no se pudieron leer y se apartaron (para avisar al usuario). Los que ya se pueden
    descifrar (el fallo era de Windows y no del archivo, como apartaban las versiones anteriores) vuelven solos: sus
    claves se suman a las de ahora, sin pisar ninguna."""
    for apartado in sorted(ARCHIVO.parent.glob("claves.danado-*")):
        try:
            viejas = _descifrar(apartado.read_text(encoding="utf-8-sig"))
            _escribir({**viejas, **_leer()})
            apartado.unlink()
        except (NoSeDescifra, OSError, ValueError):  # sigue sin poder leerse: se queda apartado y se avisa
            continue
    return sorted(ARCHIVO.parent.glob("claves.danado-*"))


def guardar(info: dict) -> None:
    todas = _leer_para_cambiar()
    todas[info["proveedor"]] = info
    _escribir(todas)


def borrar(proveedor: str) -> None:
    todas = _leer_para_cambiar()
    todas.pop(proveedor, None)
    _escribir(todas)
    # Las elecciones «por defecto» que apuntaban a esa clave vuelven a Automático (salvo su opción gratis sin clave).
    # También el modelo de video recordado en el Director y en Crear (modelo_video_…)
    a = _guardados()
    limpias = {uso: p for uso, p in a.items() if p != proveedor or p == GRATIS.get(uso)}
    if limpias != a:
        _reemplazar(AJUSTES, json.dumps(limpias, indent=2))


def ajustes() -> dict:
    """Los ajustes guardados y, encima, el modelo de video elegido para el trabajo de este hilo (por_trabajo)."""
    return {**_guardados(), **getattr(_trabajo, "ajustes", {})}


def _guardados() -> dict:
    """Solo lo guardado en ajustes.json: lo que se lee para volver a escribirlo (nunca el modelo de un trabajo)."""
    for _ in range(20):
        try:
            return json.loads(AJUSTES.read_text(encoding="utf-8"))
        except PermissionError:  # se está reemplazando justo ahora (Windows lo bloquea un instante): otra vez
            time.sleep(0.05)
        except (FileNotFoundError, ValueError):  # ajustes.json vacío o roto: se usan los valores por defecto
            return {}
    return json.loads(AJUSTES.read_text(encoding="utf-8"))


def elegir_por_defecto(uso: str, proveedor: str) -> None:
    """Fija qué proveedor usa el software para un uso. 'auto' vuelve a la elección automática."""
    a = _guardados()
    a[uso] = proveedor
    _reemplazar(AJUSTES, json.dumps(a, indent=2))


def opciones(uso: str) -> list[str]:
    """Lo que se puede elegir para un uso: automático, lo conectado y lo gratis sin clave."""
    conectados = [p for p in dict.fromkeys(PREFERENCIA[uso] + SOLO_ELIGIENDO.get(uso, [])) if p in cargar()]
    gratis = [GRATIS[uso]] if uso in GRATIS and GRATIS[uso] not in conectados else []
    return ["auto", *conectados, *gratis]


def para(uso: str) -> dict | None:
    """La clave que toca para un uso ('texto', 'diseno', 'imagen', 'transcripcion', 'video', 'video_voz').
    Devuelve {'proveedor': 'pc'|'ninguno'|'pollinations'} sin clave si se eligió una opción gratis."""
    todas, elegido = cargar(), ajustes().get(uso, "auto")
    if elegido in todas:
        return todas[elegido]
    if elegido == GRATIS.get(uso):
        return {"proveedor": elegido}
    if uso == "diseno":  # «auto», o la elegida ya no tiene clave: la misma IA que escribe los guiones
        return para("texto")
    # "auto", o el proveedor elegido ya no tiene clave: elección automática (nunca uno de pago que hay que elegir)
    return next((todas[p] for p in PREFERENCIA[uso] if p in todas and p not in SOLO_ELIGIENDO.get(uso, [])), None)


# ---------- El modelo de video de UN trabajo: el selector «Modelo de video» (Director, Crear) y el MCP ----------
# Además de «auto» (lo de «Claves de IA»). «ninguno» = sin animar; Gemini es Omni, solo para escenas que hablan
VIDEO_GRATIS = ("ninguno", "huggingface", "modal", "pollinations")  # los que no cobran: nada que hable con una de pago
MODELOS_VIDEO = (*VIDEO_GRATIS, *VIDEO_DE_PAGO, "gemini")
_trabajo = threading.local()  # lo elegido para el trabajo que corre en cada hilo (ver por_trabajo)


@contextmanager
def por_trabajo(modelo):
    """Mientras dura, este hilo anima con `modelo` (ajustes() lo ve encima de lo guardado): vale para ese trabajo y
    nunca cambia ni guarda la elección de «Claves de IA». Kling y Seedance hacen también sus escenas que hablan.
    «auto», None o uno que no existe: lo de «Claves de IA» (quien lo recibe de fuera lo comprueba con
    validar_modelo_video, antes de gastar)."""
    antes = getattr(_trabajo, "ajustes", {})
    m = modelo if isinstance(modelo, str) and modelo in MODELOS_VIDEO else None
    _trabajo.ajustes = {} if not m else {"video_voz": m} if m == "gemini" else \
        {"video": m, **({"video_voz": m} if m in VIDEO_DE_PAGO else {})}
    try:
        yield
    finally:
        _trabajo.ajustes = antes


def validar_modelo_video(modelo) -> str:
    """El modelo de video que llega de un agente (MCP) o del Director, si vale: uno de la lista y conectado (sin
    animar y Hugging Face van sin clave). None (un null del agente) es Automático, como en por_trabajo."""
    if modelo in (None, "auto", "ninguno", "huggingface"):
        return modelo or "auto"
    if not isinstance(modelo, str) or modelo not in MODELOS_VIDEO:
        raise ValueError(t("Modelo de video desconocido ({modelo!r:.30}); valen {modelos}.", modelo=modelo,
                           modelos=", ".join(("auto", *MODELOS_VIDEO))))
    if modelo not in cargar():
        raise ValueError(t("{servicio} no está conectado: conéctalo en «Claves de IA» o usa «auto».",
                           servicio=nombre(modelo)))
    return modelo


def nombre_modelo(id_: str) -> str:
    """«kling-3.0-turbo» → «Kling 3.0 Turbo»; «seedance-1-0-pro-fast-251015» → «Seedance 1.0 Pro Fast»."""
    limpio = re.sub(r"(\d)-(\d)", r"\1.\2", re.sub(r"^dreamina-|-\d{6}$", "", id_))
    return " ".join(p.capitalize() for p in limpio.split("-"))


def modelos_video() -> list[dict]:
    """Lo que ofrece el selector «Modelo de video»: Automático, Sin animar y solo lo que funciona ya (Hugging Face va
    sin clave), con lo que cuesta dicho corto. [{"id", "nombre", "estado"}]; estado: el último comprobado de su
    servicio si no es bueno («sin_saldo», «permiso»…), o ""."""
    from . import ia, nube  # aquí: los dos importan este módulo
    from .idioma import dinero
    todas, recordados = cargar(), estados()
    # Automático es lo de «Claves de IA»: si allí se eligió Kling o Seedance, se dice (cobra, con su pregunta). Se
    # llama fuera de un trabajo (selector, Director, MCP): la capa de por_trabajo está vacía y esto es lo guardado
    pago = ia.video_de_pago()
    lista = [("auto", t("Automático (lo de «Claves de IA»: {servicio}, de pago)", servicio=ia.nombre_video(pago))
              if pago else t("Automático (el estudio elige: gratis primero)")),
             ("ninguno", t("Sin animar (fotos con movimiento, gratis)")),
             ("huggingface", t("Hugging Face · gratis, cupo diario"))]
    if "modal" in todas:
        lista.append(("modal", t("Mi nube Modal · gratis, quedan {n} de {m} hoy",
                                 n=max(nube.limite() - nube.usados_hoy(), 0), m=nube.limite())))
    if "pollinations" in todas:
        lista.append(("pollinations", t("Pollinations · gratis, con el saldo de tu cuenta")))
    # Lo más que cuesta un clip (ia.precio_video, como la pregunta de costo), al centavo de arriba: 0,115 dice 0,12.
    # Elegidos, hacen también las escenas que hablan (por_trabajo), que cuestan más: se dicen los dos
    def arriba(precio: float) -> str:
        return dinero(math.ceil(round(precio * 100, 6)) / 100)
    for p in VIDEO_DE_PAGO:
        if p in todas:
            id_ = todas[p].get("modelo_video") or modulo_video(p).MODELOS[0]["id"]
            lista.append((p, t("{modelo} · hasta {costo} por clip, {voz} si habla", modelo=nombre_modelo(id_),
                               costo=arriba(ia.precio_video(p)), voz=arriba(ia.precio_video(p, voz=True)))))
    if "gemini" in todas:
        lista.append(("gemini", t("Gemini Omni · {costo} por segundo, habla", costo=dinero(ia.PRECIO_OMNI))))
    # Sin clave no hay estado que mirar; Hugging Face anima con la cuota anónima, sin su token (impide tampoco lo mira)
    return [{"id": i, "nombre": n,
             "estado": "" if i in ("auto", "ninguno", "huggingface") or
             (e := (recordados.get(i) or {}).get("estado", "ok")) in ("ok", "clave_ok") else e}
            for i, n in lista]


def nombre_modelo_video(modelo: str) -> str:
    """Cómo lo dice el selector («Kling 3.0 · hasta US$0.56 por clip, US$1.01 si habla»); uno que ya no está, como
    Automático."""
    lista = modelos_video()
    return next((m["nombre"] for m in lista if m["id"] == modelo), lista[0]["nombre"])


def publico() -> list[dict]:
    """Lo que el panel puede ver: nunca la clave completa (ni el secreto del cliente de YouTube)."""
    return [{**{k: v for k, v in i.items() if k not in ("clave", "voces", "client_secret")},
             "clave": i["clave"][:6] + "…" + i["clave"][-4:]} for i in cargar().values()]


# ---------- Comprobar conexiones: el estado real de cada servicio conectado, antes de que un trabajo falle ----------

CONEXIONES = ARCHIVO.with_name("conexiones.json")  # el último estado de cada servicio (nunca su clave)
ESTADOS = ("ok", "clave_ok", "sin_saldo", "sin_cuota", "clave", "permiso", "sin_conexion", "error")
NO_ATIENDE = {"sin_saldo", "sin_cuota", "clave"}  # con estos, un trabajo que lo usa falla seguro: se avisa antes
# De pago, y su comprobación gratis (la lista de modelos, la cuenta, las tareas) solo dice si la clave vale: responde
# bien aunque no quede saldo (OpenAI da luego 429 insufficient_quota; Claude, 400 «credit balance is too low»). Con
# ellos no se dice «Funciona» sino «clave_ok»; su «sin saldo» llega en la primera llamada de verdad (recordar)
SALDO_INVISIBLE = {"openai", "anthropic", "xai", "replicate", "pollinations", "kling", "seedance", "modal"}
BLOQUEA = {"sin_saldo", "clave"}  # y con estos, un paso que solo se puede hacer pagando ni empieza
VIGENCIA = 12 * 3600  # un estado más viejo ya no se usa para avisar (pudo recargar): en la página se ve igual
# Dónde se recarga el saldo de cada servicio de pago (sin «https://»: se lee mejor en un aviso)
RECARGA = {"openai": "platform.openai.com/settings/organization/billing",
           "anthropic": "console.anthropic.com/settings/billing", "deepseek": "platform.deepseek.com/top_up",
           "openrouter": "openrouter.ai/settings/credits", "xai": "console.x.ai",
           "elevenlabs": "elevenlabs.io/app/subscription", "replicate": "replicate.com/account/billing",
           "pollinations": "enter.pollinations.ai", "modal": "modal.com/settings/usage",
           "kling": "kling.ai/dev/api-key", "seedance": "ai.byteplus.com"}
GEMINI_BARATO = "gemini-flash-lite-latest"  # el modelo de texto más barato de Gemini, para su comprobación
_cerrojo_estados = threading.Lock()  # la comprobación y las llamadas escriben a la vez (el MCP: guardia._cerrojo)


def clasificar(codigo: int, detalle: str = "") -> str:
    """El estado que dice la respuesta de un servicio: ok, sin_saldo (402, o el texto lo dice: «prepayment credits are
    depleted», «credit balance is too low»), sin_cuota (429: el límite gratis o por minuto), clave (401, 403, o la
    clave que Gemini no reconoce, que llega como 400) o error (un 5xx o lo que no se entiende)."""
    texto = str(detalle or "").lower()
    if codigo < 400:
        return "ok"
    if codigo == 402 or re.search(r"prepayment|credits? (?:are |is )?(?:depleted|exhausted)|credit balance|"
                                  r"insufficient[_ ](?:balance|quota|funds|credits)|out of credits", texto):
        return "sin_saldo"
    # La clave vale pero no tiene ese permiso (ElevenLabs deja crear claves con permisos sueltos: «missing the
    # permission user_read»; OpenAI, claves restringidas: «insufficient permissions… Missing scopes: api.model.read»).
    # Pasó: una clave buena, con saldo, salía como «Clave no válida»
    if codigo in (401, 403) and re.search(r"missing[_ ](?:the )?permission|missing scopes?\b|insufficient permissions",
                                          texto):
        return "permiso"
    if codigo in (401, 403) or (codigo == 400 and re.search(r"api[_ ]key", texto)):
        return "clave"
    return "sin_cuota" if codigo == 429 else "error"


def paso(proveedor: str, estado: str) -> str:
    """Qué hacer con un servicio que no atiende, dicho en una frase."""
    if estado == "sin_saldo":
        if proveedor == "gemini":
            return t("Recarga en AI Studio: aistudio.google.com → tu proyecto → Billing.")
        return t("Recarga saldo en {web}.", web=RECARGA.get(proveedor, nombre(proveedor)))
    if estado == "sin_cuota":
        return t("Espera un rato (o hasta mañana) o usa otra IA.")
    if estado == "clave":
        return t("La clave ya no vale: en «Claves de IA», pulsa «Conseguir clave ↗» de este servicio, crea una nueva y "
                 "conéctala.")
    if estado == "permiso":
        return t("En la web del servicio, edita esta clave y dale el permiso que dice el detalle (o acceso completo); "
                 "luego pulsa «Comprobar conexiones».")
    if estado == "sin_conexion":
        return t("Revisa tu internet y pulsa «Comprobar conexiones» en «Claves de IA».")
    if estado == "error":
        return t("El servicio falló justo ahora: vuelve a comprobar en un rato.")
    return ""


def _sonda(proveedor: str, info: dict):
    """La petición más barata que dice el estado real de la clave: las listas gratis donde las hay (modelos, cuenta,
    saldo) y, en Gemini, un pedido de 1 token al modelo de texto más barato (menos de una milésima de centavo): solo
    un pedido de verdad dice «prepayment credits are depleted». Devuelve la respuesta, o (estado, detalle) si la
    respuesta se lee de otra forma (el saldo de DeepSeek u OpenRouter, la cuota de ElevenLabs, el token de Modal)."""
    clave = info["clave"]
    if proveedor == "gemini":
        from . import actividad, ia  # aquí: ia importa este módulo
        cuerpo = {"contents": [{"parts": [{"text": "1"}]}], "generationConfig": {"maxOutputTokens": 1}}
        for modelo in dict.fromkeys((GEMINI_BARATO, info.get("modelo_texto") or "gemini-flash-latest")):
            r = httpx.post(f"{ia.API_GEMINI}/models/{modelo}:generateContent", headers={"x-goog-api-key": clave},
                           json=cuerpo, timeout=20)
            if r.status_code != 404:  # 404: la clave no tiene ese modelo, se prueba con el de sus guiones
                break
        if r.status_code >= 400:  # no atendió: no cobra
            actividad.anotar("texto", "gemini", modelo, error=f"{r.status_code}: {ia.motivo(r)}")
            return r
        uso = r.json().get("usageMetadata") or {}
        actividad.anotar("texto", "gemini", modelo, ia.costo_texto("gemini", uso.get("promptTokenCount", 2),
                                                                     uso.get("candidatesTokenCount", 1)))
        return r
    if proveedor == "anthropic":
        return httpx.get("https://api.anthropic.com/v1/models?limit=1",
                         headers={"x-api-key": clave, "anthropic-version": "2023-06-01"}, timeout=20)
    if proveedor == "deepseek":  # su saldo, gratis: «is_available» es falso sin saldo
        r = httpx.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {clave}"}, timeout=20)
        if r.status_code < 400 and r.json().get("is_available") is False:
            return "sin_saldo", t("La cuenta no tiene saldo.")
        return r
    if proveedor == "openrouter":  # la lista de modelos es pública: la de la clave dice si vale y cuánto le queda
        r = httpx.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {clave}"}, timeout=20)
        restante = (r.json().get("data") or {}).get("limit_remaining") if r.status_code < 400 else None
        if isinstance(restante, (int, float)) and restante <= 0:
            return "sin_saldo", t("La clave llegó a su límite de gasto.")
        return r
    if proveedor == "elevenlabs":  # la suscripción, gratis: las letras usadas y las del plan
        r = httpx.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": clave}, timeout=20)
        if r.status_code in (401, 403) and clasificar(r.status_code, r.text) == "permiso":
            # Una clave sin «User: Read» vale igual para voces y música, pero no deja ver las letras que quedan: si su
            # lista de modelos responde, la clave vale (como las de SALDO_INVISIBLE). Si tampoco tiene «Models: Read»,
            # ElevenLabs reconoce la clave igual, y esa lista la app no la usa: no se pinta ámbar por ella
            modelos = httpx.get("https://api.elevenlabs.io/v1/models", headers={"xi-api-key": clave}, timeout=20)
            if modelos.status_code < 400 or clasificar(modelos.status_code, modelos.text) == "permiso":
                return "clave_ok", t("Sin el permiso «User: Read» de esta clave no se ven las letras que te quedan.")
            return modelos
        if r.status_code < 400:
            d = r.json()
            usadas, tope = d.get("character_count"), d.get("character_limit")
            if isinstance(usadas, int) and isinstance(tope, int) and tope and usadas >= tope:
                return "sin_saldo", t("Se acabaron las letras de tu plan de este mes.")
        return r
    if proveedor == "modal":  # su token, con su propia herramienta (sin GPU ni costo)
        try:
            _ids_modelos("modal", clave)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            # Sin detalle: su texto diría «Modal rechazó el token», y el paso ya dice qué hacer
            if _sin_red(e):
                return "sin_conexion", ""
            return "clave", str(e)
        return "ok", ""
    if proveedor in VIDEO_DE_PAGO:  # consultar tareas es gratis (ver kling.validar y seedance.validar)
        try:
            modulo_video(proveedor).validar(clave)
        except httpx.HTTPStatusError as e:
            return e.response
        return "ok", ""
    if proveedor in ("replicate", "huggingface", "cloudflare"):
        try:
            _ids_modelos(proveedor, clave)
        except httpx.HTTPStatusError as e:
            return e.response
        return "ok", ""
    # ponytail: Pollinations, OpenAI y xAI no tienen (que sepamos) una consulta de saldo gratis; su lista de modelos solo
    # dice si la clave vale (SALDO_INVISIBLE). Su «sin saldo» se ve en la actividad de la IA cuando pasa.
    return httpx.get(f"{OPENAI_COMPAT[proveedor]}/models", headers={"Authorization": f"Bearer {clave}"}, timeout=20)


def _comprobar_uno(proveedor: str, info: dict) -> dict:
    from .ia import motivo  # aquí: ia importa este módulo
    try:
        r = _sonda(proveedor, info)
        if isinstance(r, tuple):
            estado, detalle = r
        else:
            estado = clasificar(r.status_code, motivo(r) if r.status_code >= 400 else "")
            detalle = "" if estado == "ok" else f"{r.status_code}: {motivo(r)}"
    except Exception as e:  # sin red (sin_conexion) o una respuesta rara, que no tumba las demás comprobaciones
        from .idioma import texto_de_error  # en claro: no «ConnectError» ni «KeyError»
        estado, detalle = "sin_conexion" if isinstance(e, httpx.TransportError) else "error", texto_de_error(e)
    if estado == "ok" and proveedor in SALDO_INVISIBLE:  # la clave vale; el saldo no se ve desde aquí
        estado = "clave_ok"
    return {"estado": estado, "detalle": guardia.limpiar(detalle)[:240], "paso": paso(proveedor, estado),
            "fecha": time.strftime("%Y-%m-%d %H:%M:%S")}


PLAZO_COMPROBAR = 90  # s: cada sonda tiene el suyo (20 s; Modal, 60): esto solo cubre una que se quede colgada


def comprobar(proveedores=None) -> dict:
    """Comprueba cada servicio conectado (o solo `proveedores`) con la petición más barata que dice su estado real
    (_sonda), todos a la vez. Devuelve {proveedor: {"estado", "detalle", "paso", "fecha"}} y lo recuerda en
    conexiones.json: así los trabajos avisan ANTES de empezar (antes_de, impide). Nunca guarda claves.
    Cada sonda va en un hilo daemon y no en un ThreadPoolExecutor, al que Python espera al salir: cerrar la app con la
    comprobación en marcha no la deja colgada. La que no termina en PLAZO_COMPROBAR no se guarda."""
    todas = cargar()
    elegidos = [p for p in (proveedores or todas) if p in todas and p in USOS]
    hechos = {}
    hilos = [threading.Thread(target=lambda p=p: hechos.__setitem__(p, _comprobar_uno(p, todas[p])), daemon=True)
             for p in elegidos]
    for h in hilos:
        h.start()
    fin = time.monotonic() + PLAZO_COMPROBAR
    for h in hilos:
        h.join(max(0.0, fin - time.monotonic()))
    resultados = {p: hechos[p] for p in elegidos if p in hechos}
    with _cerrojo_estados, guardia._cerrojo(CONEXIONES):
        guardados = {p: e for p, e in estados().items() if p in todas}  # las claves quitadas ya no salen
        guardados.update(resultados)
        try:
            _reemplazar(CONEXIONES, json.dumps(guardados, ensure_ascii=False, indent=1))
        except OSError:  # se comprueba otra vez la próxima: no tumba la página
            pass
    return resultados


def estados() -> dict:
    """El último estado comprobado de cada servicio: {proveedor: {"estado", "detalle", "paso", "fecha"}}."""
    try:
        datos = json.loads(CONEXIONES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {p: e for p, e in datos.items() if isinstance(e, dict) and e.get("estado") in ESTADOS
            and isinstance(e.get("fecha"), str)} if isinstance(datos, dict) else {}


def recordar(proveedor: str, codigo: int, detalle: str = "") -> None:
    """Lo que acaba de responder un servicio en una llamada de verdad pone al día su estado: Gemini sin saldo a media
    tarde ya avisa en el trabajo siguiente, y al volver a funcionar deja de avisar. Nunca lanza."""
    try:
        estado = clasificar(codigo, detalle)
        if estado == "error":  # un fallo pasajero no cambia lo que se sabe del servicio
            return
        with _cerrojo_estados, guardia._cerrojo(CONEXIONES):
            todos = estados()
            if estado == "ok" and todos.get(proveedor, {}).get("estado") in (None, "ok"):
                return  # ya se sabía: no se escribe en cada llamada que sale bien
            todos[proveedor] = {"estado": estado, "detalle": guardia.limpiar(f"{codigo}: {detalle}" if estado != "ok"
                                                                             else "")[:240],
                                "paso": paso(proveedor, estado), "fecha": time.strftime("%Y-%m-%d %H:%M:%S")}
            _reemplazar(CONEXIONES, json.dumps(todos, ensure_ascii=False, indent=1))
    except Exception:  # es solo un aviso para la próxima vez
        pass


def _vigente(proveedor: str, cuales=NO_ATIENDE) -> dict | None:
    """El estado guardado del servicio si es uno de `cuales` y es reciente (VIGENCIA)."""
    e = estados().get(proveedor)
    if not e or e.get("estado") not in cuales:
        return None
    try:
        fecha = time.mktime(time.strptime(str(e.get("fecha")), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, OverflowError):
        return None
    return e if time.time() - fecha < VIGENCIA else None


def frase(proveedor: str, estado: str) -> str:
    """«Gemini no tiene saldo», «La clave de Groq no vale»…"""
    n = nombre(proveedor)
    return {"sin_saldo": t("{servicio} no tiene saldo", servicio=n),
            "sin_cuota": t("{servicio} no tiene cuota ahora", servicio=n),
            "clave": t("La clave de {servicio} no vale", servicio=n),
            "permiso": t("A la clave de {servicio} le falta un permiso", servicio=n),
            "sin_conexion": t("Sin conexión con {servicio}", servicio=n)}.get(estado, t("{servicio} falló", servicio=n))


def _cuando(e: dict) -> str:
    fecha = str(e.get("fecha", ""))
    if fecha[:10] == time.strftime("%Y-%m-%d"):
        return t("comprobado hoy a las {hora}", hora=fecha[11:16])
    return t("comprobado el {fecha}", fecha=f"{fecha[8:10]}/{fecha[5:7]} {fecha[11:16]}")


def antes_de(usos) -> list[str]:
    """Lo que se le dice al usuario ANTES de empezar un trabajo que usa estas IA (texto, imagen, musica, video), según el
    último estado comprobado: «Gemini no tiene saldo: usaré Groq para el texto». Lo de pago que no se puede hacer lo
    dice impide()."""
    avisos = []
    if "texto" in usos:
        c = para("texto") or {}
        if c.get("clave") and (malo := _vigente(c["proveedor"])):
            todas = cargar()
            otra = next((p for p in PREFERENCIA["texto"] if p != c["proveedor"] and p in todas
                         and "texto" in USOS.get(p, []) and not _vigente(p)), None)
            avisos.append(t("{problema}: usaré {otra} para el texto.", problema=frase(c["proveedor"], malo["estado"]),
                            otra=nombre(otra)) if otra else
                          t("{problema}: usaré la IA gratis sin clave para el texto (más lenta).",
                            problema=frase(c["proveedor"], malo["estado"])))
    if "imagen" in usos:
        c = para("imagen") or {}
        if c.get("proveedor") in SOLO_ELIGIENDO["imagen"] and (malo := _vigente(c["proveedor"])):
            avisos.append(t("{problema}: las imágenes las hará la siguiente opción gratis.",
                            problema=frase(c["proveedor"], malo["estado"])))
    if "musica" in usos:
        c = para("musica") or {}
        if c.get("proveedor") == "gemini" and _vigente("gemini") and "elevenlabs" in cargar() \
                and ajustes().get("musica", "auto") == "auto" and not _vigente("elevenlabs"):
            from .musica import PRECIO
            from .idioma import dinero
            avisos.append(t("{problema}: la canción la hará ElevenLabs (hasta unos {costo}).",
                            problema=frase("gemini", _vigente("gemini")["estado"]), costo=dinero(PRECIO["elevenlabs"])))
    if "video" in usos:  # Kling o Seedance elegidos para animar: sin ellos (nunca otro de pago) va con zoom suave
        quien = ajustes().get("video")
        if quien in VIDEO_DE_PAGO and quien in cargar() and (malo := _vigente(quien, BLOQUEA)):
            avisos.append(t("{problema}: las escenas irán con zoom suave, sin animar.",
                            problema=frase(quien, malo["estado"])))
    return avisos


def impide(usos) -> str | None:
    """Por qué un paso que solo se hace pagando no puede empezar (el servicio que lo haría no tiene saldo o su clave
    no vale, según el último estado comprobado); None si puede. Así no se espera minutos para un fallo seguro.
    Como impide que se haga el pedido, ninguna respuesta buena lo desbloquea sola: se dice cómo (pasó: recargó y
    seguía bloqueado hasta 12 h)."""

    def que_hacer(proveedor: str, estado: str) -> str:
        return f"{paso(proveedor, estado)} " + t("Si ya recargaste o cambiaste la clave, pulsa «Comprobar conexiones» "
                                                 "en «Claves de IA».")
    if "video_voz" in usos:
        quien = (para("video_voz") or {}).get("proveedor")
        if quien and (malo := _vigente(quien, BLOQUEA)):
            return t("No se puede hacer el video que habla: {problema} ({cuando}). {paso} O desmarca «Video animado "
                     "con IA». No se cobró nada.", problema=frase(quien, malo["estado"]), cuando=_cuando(malo),
                     paso=que_hacer(quien, malo["estado"]))
    # El modelo elegido para este trabajo en «Modelo de video» (con el de «Claves de IA», las escenas van con zoom
    # suave: antes_de). Hugging Face no: para video va sin su token, que es lo que se comprueba
    quien = getattr(_trabajo, "ajustes", {}).get("video")
    if "video" in usos and quien != "huggingface" and quien in cargar() and (malo := _vigente(quien, BLOQUEA)):
        return t("No se puede animar con {servicio}, el modelo de video elegido: {problema} ({cuando}). {paso} O "
                 "elige otro modelo de video. No se cobró nada.", servicio=nombre(quien),
                 problema=frase(quien, malo["estado"]), cuando=_cuando(malo), paso=que_hacer(quien, malo["estado"]))
    if "musica" in usos:
        c = para("musica") or {}
        respaldo = "elevenlabs" in cargar() and ajustes().get("musica", "auto") == "auto" and \
            not _vigente("elevenlabs", BLOQUEA)
        if c.get("clave") and (malo := _vigente(c["proveedor"], BLOQUEA)) and not (c["proveedor"] == "gemini"
                                                                                    and respaldo):
            return t("No se puede hacer la canción: {problema} ({cuando}). {paso} No se cobró nada.",
                     problema=frase(c["proveedor"], malo["estado"]), cuando=_cuando(malo),
                     paso=que_hacer(c["proveedor"], malo["estado"]))
    return None
