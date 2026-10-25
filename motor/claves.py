"""Claves BYOK: el usuario pega una clave y aquí se detecta el proveedor y el mejor modelo."""
import json
import os
import re
import time
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
        r.raise_for_status()
        return []
    elif proveedor == "modal":
        import subprocess
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
    except httpx.HTTPError as e:
        raise ValueError(t("No hay conexión con {proveedor}: {error}. Inténtalo de nuevo.", proveedor="cloudflare",
                           error=type(e).__name__)) from None
    if r.status_code in (401, 403):
        raise ValueError(t("Cloudflare no acepta ese token (¿se copió entero?). {falta}", falta=falta))
    try:
        cuentas = {str(a.get("id")) for a in r.json().get("result") or [] if isinstance(a, dict)}
    except (ValueError, AttributeError):
        cuentas = set()
    cuentas = {c for c in cuentas if re.fullmatch(r"[0-9a-f]{32}", c)}
    if r.status_code >= 400 or len(cuentas) != 1:
        raise ValueError(falta)
    return cuentas.pop()


def detectar(clave: str, proveedor: str | None = None) -> dict:
    """Identifica el proveedor de la clave, la valida contra su API y elige los modelos.
    proveedor: Kling o Seedance, elegido por el usuario con su botón. Sus claves no tienen un formato que se pueda
    reconocer sin adivinar: se comprueban solo con el elegido, y nunca se le manda una que parece de otro servicio."""
    if proveedor:
        clave = clave.strip()
        # su formato no se conoce: cualquier token sin espacios (también base64 o JWT) de un largo razonable
        if proveedor not in VIDEO_DE_PAGO or not re.fullmatch(r"[A-Za-z0-9._~+/=-]{8,512}", clave):
            raise ValueError(t("Pega solo la clave, sin espacios ni texto alrededor."))
        # ponytail: si las claves de Kling resultan medir 40 caracteres (como el token clásico de Cloudflare), esta
        # regla las rechaza: entonces hay que dejar pasar ese caso aquí.
        if candidatos(clave) not in ([], [proveedor]) or clave.startswith(STRIPE) or re.match(AJENAS, clave):
            guardia.registrar("clave_ajena", "media", t("Se rechazó una clave de otro servicio pegada en «Conectar» "
                                                        "de {proveedor}: no se mandó.", proveedor=proveedor.capitalize()))
            raise ValueError(t("Esa clave es de otro servicio, no de {proveedor}: pégala en el cuadro de arriba, que "
                               "la reconoce sola.", proveedor=proveedor.capitalize()))
        opciones = [proveedor]
    else:
        clave = limpiar(clave)
        opciones = candidatos(clave)
    if not opciones and re.fullmatch(r"a[ks]-[A-Za-z0-9]+", clave):
        raise ValueError(t("Es un token de Modal, pero falta la otra parte: pega juntas las dos, la que empieza por "
                           "«ak-» y la que empieza por «as-», separadas por un espacio (o la orden «modal token set "
                           "…» entera que te da Modal)."))
    if not opciones:  # qué llegó (largo y principio), para saber qué se pegó sin enseñar la clave entera
        raise ValueError(t("No reconozco el formato de esta clave (llegaron {n} caracteres que empiezan por "
                           "«{inicio}…»). Pega solo la clave, sin espacios ni texto alrededor. Si es de Kling o "
                           "Seedance, usa su botón «Conectar» en la lista de servicios.", n=len(clave),
                           inicio=clave[:6]))
    if opciones == ["cloudflare"] and not re.search(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", clave):
        clave = f"{_cuenta_cloudflare(clave)} {clave}"  # solo pegó el token: su cuenta se le pregunta a Cloudflare
    ultimo_error = None
    for proveedor in opciones:
        try:
            modelos = _ids_modelos(proveedor, clave)
        except ImportError:  # esta copia de la app aún no trae su conexión
            raise ValueError(t("Esta versión de Ráfaga Studio todavía no trae {proveedor}: actualízala.",
                               proveedor=proveedor.capitalize())) from None
        except httpx.HTTPStatusError as e:
            # Solo si ESTE proveedor rechaza la clave se prueba con el siguiente: así la clave no se manda a otro
            # proveedor por un fallo de red o del servidor.
            if e.response.status_code != 401:  # 403 = clave válida sin permiso: no es de otro proveedor
                raise ValueError(t("{proveedor} no respondió bien ({codigo}); inténtalo de nuevo.", proveedor=proveedor,
                                   codigo=e.response.status_code))
            ultimo_error = e
            continue
        except httpx.HTTPError as e:
            raise ValueError(t("No hay conexión con {proveedor}: {error}. Inténtalo de nuevo.", proveedor=proveedor,
                               error=type(e).__name__))
        except (RuntimeError, OSError) as e:  # Modal (único candidato de su formato) rechazó el token
            ultimo_error = e
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
            info["voces"] = voces_elevenlabs(clave)
        return info
    raise ValueError(t("La clave parece de {proveedores} pero no funcionó: {error}", proveedores=", ".join(opciones),
                       error=ultimo_error))


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
    os.replace(temporal, archivo)


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
                           "vez. Si datos/claves.json viene de otro PC, sácalo de la carpeta datos.")) from None


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
    a = ajustes()
    limpias = {uso: p for uso, p in a.items() if p != proveedor or p == GRATIS.get(uso)}
    if limpias != a:
        _reemplazar(AJUSTES, json.dumps(limpias, indent=2))


def ajustes() -> dict:
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
    a = ajustes()
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


def publico() -> list[dict]:
    """Lo que el panel puede ver: nunca la clave completa (ni el secreto del cliente de YouTube)."""
    return [{**{k: v for k, v in i.items() if k not in ("clave", "voces", "client_secret")},
             "clave": i["clave"][:6] + "…" + i["clave"][-4:]} for i in cargar().values()]
