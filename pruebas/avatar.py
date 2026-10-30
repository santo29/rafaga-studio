"""Avatar IA (motor/nube.avatar y motor/ia.avatar) sin red, sin Modal y sin Spaces: el motor de Modal y el Space se
sustituyen por falsos con el mismo contrato. Lo que no puede salir no gasta cupo, lo gratis nunca se usa sin la
casilla y el «como mucho» que ve el usuario cubre los plazos de modal_app.Avatar: python -m pruebas.avatar"""
import os
import struct
import tempfile
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")
import modal.exception  # noqa: E402

import modal_app  # noqa: E402
from motor import actividad, claves, ia, nube, nubes, video  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="rafaga-avatar-"))
claves.ARCHIVO, claves.AJUSTES = tmp / "claves.json", tmp / "ajustes.json"  # nunca las claves ni el cupo del usuario
nube.USO, nubes.USO = tmp / "uso_nube.json", tmp / "uso_nubes.json"
foto, mp4 = tmp / "foto.png", tmp / "hecho.mp4"
voz_corta, voz_larga, voz_space = tmp / "corta.m4a", tmp / "larga.wav", tmp / "space.wav"
video.ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", foto)
video.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=64x64:r=25:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", mp4)
video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=9.5", "-ac", "2", "-ar", "44100", voz_corta)
video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=12", voz_larga)
video.ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=19", voz_space)
MP4 = mp4.read_bytes()


def falla(funcion, *args, error=Exception, **kw):
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


class Avatar:
    """Lo que da modal.Cls.from_name: hydrate() sin GPU (falla si el motor no tiene el avatar) y ().hablar.remote."""
    existe, llamadas = True, []

    def hydrate(self):
        if not Avatar.existe:
            raise modal.exception.NotFoundError("Lookup failed for Cls 'Avatar' from the 'rafaga-studio-video' app")
        return self

    def __call__(self):
        return self

    @property
    def hablar(self):
        return self

    def remote(self, *args):
        Avatar.llamadas.append(args)
        return MP4


def space_prohibido(*a, **k):
    raise AssertionError("sin la casilla, tu cara y tu voz no van a ningún Space")


real = modal.Cls.from_name, nube._cliente, nubes.llamar_space
modal.Cls.from_name, nube._cliente = (lambda app, clase, client=None: Avatar()), (lambda clave: None)
nubes.llamar_space = space_prohibido
try:
    claves.guardar({"proveedor": "modal", "clave": "ak-1 as-2", "usos": ["video"]})
    claves.elegir_por_defecto("limite_nube_diario", 2)

    # Una voz de más de 10 s no sale: ValueError antes de apartar cupo y sin llamar a Modal
    assert "como mucho 10 s" in falla(nube.avatar, foto, voz_larga, "9:16", tmp / "a.mp4", error=ValueError)
    assert nube.usados_hoy() == 0 and not Avatar.llamadas and not (tmp / "a.mp4").exists()

    # Un motor instalado antes del avatar (o sin instalar): dice que se reinstale y el cupo no cambia
    Avatar.existe = False
    error = falla(nube.avatar, foto, voz_corta, "9:16", tmp / "a.mp4", error=RuntimeError)
    assert "Instalar motor en Modal" in error and "otra vez" in error and "No se gastó nada" in error, error
    assert nube.usados_hoy() == 0 and not Avatar.llamadas
    Avatar.existe = True

    # Todo bien: el MP4 queda escrito, cuenta 1 clip y a Modal va la foto tal cual y la voz en WAV mono de 16 kHz
    destino = nube.avatar(foto, voz_corta, "9:16", tmp / "a.mp4")
    assert destino.read_bytes() == MP4 and nube.usados_hoy() == 1
    imagen, wav, vertical = Avatar.llamadas[-1]
    assert imagen == foto.read_bytes() and vertical is True and wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert struct.unpack("<HHI", wav[20:28]) == (1, 1, 16000), wav[20:28]  # PCM, mono, 16 kHz
    nube.avatar(foto, voz_corta, "16:9", tmp / "b.mp4")
    assert Avatar.llamadas[-1][2] is False and nube.usados_hoy() == 2

    # Sin cupo (o con tope 0) no llama a Modal
    llamadas = len(Avatar.llamadas)
    assert "Ya se usaron los 2 clips" in falla(nube.avatar, foto, voz_corta, "9:16", tmp / "c.mp4", error=RuntimeError)
    claves.elegir_por_defecto("limite_nube_diario", 0)
    assert "apagada" in falla(nube.avatar, foto, voz_corta, "9:16", tmp / "c.mp4", error=RuntimeError)
    assert len(Avatar.llamadas) == llamadas and nube.usados_hoy() == 2
    claves.elegir_por_defecto("limite_nube_diario", 5)

    # ia.avatar sin la casilla: solo Modal, con su costo en la actividad; el Space nunca, tampoco si Modal falla
    assert ia.avatar(foto, voz_corta, "9:16", tmp / "d.mp4").read_bytes() == MP4 and nube.usados_hoy() == 3
    ultima = actividad.ultimas(1)[0]
    assert (ultima["que"], ultima["proveedor"], ultima["costo"], ultima["resultado"]) == \
        ("video", "modal", nube.PRECIO_AVATAR, "ok"), ultima
    Avatar.existe = False
    assert "Instalar motor en Modal" in falla(ia.avatar, foto, voz_corta, "9:16", tmp / "e.mp4", error=RuntimeError)
    assert actividad.ultimas(1)[0]["costo"] == 0 and nube.usados_hoy() == 3  # lo que no se hizo no se apunta como gasto
    Avatar.existe = True

    # Con la casilla: solo el Space oficial de Wan, gratis y sin tocar Modal ni su cupo
    pedidos = []

    def space_falso(espacio, *entradas, api_name, espera=nubes.ESPERA_HF):
        pedidos.append((espacio, entradas, api_name, espera))
        return {"video": MP4}
    nubes.llamar_space = space_falso
    llamadas = len(Avatar.llamadas)
    assert ia.avatar(foto, voz_corta, "9:16", tmp / "f.mp4", space=True).read_bytes() == MP4
    (espacio, (ref_img, audio, resolucion), api_name, espera), = pedidos
    assert (espacio, api_name, resolucion) == ("Wan-AI/Wan2.2-S2V", "/predict", "480P")
    assert espera >= 600  # Alibaba tarda unos 5-10 min: la espera de siempre (5 min) lo cortaba
    assert Path(ref_img["path"]) == foto and Path(audio["path"]) == voz_corta  # subidos como archivos (handle_file)
    assert len(Avatar.llamadas) == llamadas and nube.usados_hoy() == 3
    assert actividad.ultimas(1)[0]["proveedor"] == "huggingface" and actividad.ultimas(1)[0]["costo"] == 0
    # El Space admite menos de 20 s: una de 19 no se sube
    assert "como mucho 18 s" in falla(ia.avatar, foto, voz_space, "9:16", tmp / "g.mp4", space=True)
    assert len(pedidos) == 1
finally:
    modal.Cls.from_name, nube._cliente, nubes.llamar_space = real

# El «como mucho» que ve el usuario cubre los plazos de modal_app.Avatar en una L40S: subir uno sin subir el precio
# rompe esta prueba. Y el motor acepta toda voz que la app deja pasar
assert nube.HASTA_AVATAR >= sum(modal_app.PLAZOS_AVATAR.values()) * nube.PRECIO_L40S, modal_app.PLAZOS_AVATAR
assert modal_app.SEGUNDOS_AVATAR >= nube.MAX_AVATAR and nube.PRECIO_AVATAR < nube.HASTA_AVATAR
assert all(len(revision) == 40 for revision, _ in modal_app.AVATAR.values()) and len(modal_app.ECHOMIMIC_COMMIT) == 40
assert isinstance(modal_app.Avatar, modal.Cls)  # se importa y define sin red (desplegarlo es cosa de «Instalar motor»)
print("Pruebas del Avatar IA pasadas.")
