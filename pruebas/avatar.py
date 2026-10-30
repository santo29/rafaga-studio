"""Avatar IA (motor/nube.avatar y motor/ia.avatar) sin red, sin Modal y sin Spaces: el motor de Modal y el Space se
sustituyen por falsos con el mismo contrato. Lo que no puede salir no gasta cupo, lo gratis nunca se usa sin la
casilla, al Space solo van los píxeles de la foto, lo que falla con la GPU ya en marcha se cuenta como gastado y el
«como mucho» que ve el usuario cubre los plazos y los topes de modal_app.Avatar: python -m pruebas.avatar"""
import os
import struct
import tempfile
from pathlib import Path

os.environ.setdefault("RAFAGA_IDIOMA", "es")
import modal.exception  # noqa: E402
from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

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
# Una foto de móvil con un nombre que dice quién es y, en el EXIF (APP1, TIFF little endian), IFD0 → GPSInfo → 18° 28'
# 30" N; ffmpeg ya le pone su comentario (COM «Lavc…»)
movil, base = tmp / "Maria_Perez_calle_Duarte_12.jpg", tmp / "base.jpg"
video.ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x48", "-frames:v", "1", base)
exif = b"Exif\0\0II*\0" + struct.pack("<IHHHIIIH", 8, 1, 0x8825, 4, 1, 26, 0, 2) \
    + struct.pack("<HHI4sHHII7I", 1, 2, 2, b"N\0\0\0", 2, 5, 3, 56, 0, 18, 1, 28, 1, 30, 1)
movil.write_bytes(base.read_bytes()[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif
                  + base.read_bytes()[2:])


def falla(funcion, *args, error=Exception, **kw):
    try:
        funcion(*args, **kw)
    except error as e:
        return str(e)
    raise AssertionError(f"debió fallar: {getattr(funcion, '__name__', funcion)}")


class Avatar:
    """Lo que da modal.Cls.from_name: hydrate() sin GPU (falla si el motor no tiene el avatar) y ().hablar.remote
    (que lanza `error` si lo hay: lo que falla con la GPU ya en marcha)."""
    existe, llamadas, error = True, [], None

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
        if Avatar.error:
            raise Avatar.error
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

    # Todo bien: el MP4 queda escrito, cuenta 1 clip y a Modal va la foto tal cual y la voz en WAV con su calidad (es
    # la que lleva el MP4: en 16 kHz se perdían los agudos; su wav2vec ya la baja para el modelo)
    destino = nube.avatar(foto, voz_corta, "9:16", tmp / "a.mp4")
    assert destino.read_bytes() == MP4 and nube.usados_hoy() == 1
    imagen, wav, vertical = Avatar.llamadas[-1]
    assert imagen == foto.read_bytes() and vertical is True and wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert struct.unpack("<HHI", wav[20:28]) == (1, 2, 44100), wav[20:28]  # PCM, estéreo y 44,1 kHz, como la voz
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

    # Si falla con la GPU ya en marcha (sin memoria, el plazo, el modelo), pudo gastar: cuenta en el cupo, la actividad
    # apunta lo que suele costar y se dice en claro por qué, sin «Ninguna opción» ni el traceback en inglés
    claves.elegir_por_defecto("limite_nube_diario", 10)
    for remoto, motivo in ((MemoryError(), "sin memoria: prueba con una voz más corta"),
                           (modal.exception.FunctionTimeoutError("Function timed out after 900 seconds"),
                            "se le acabó el tiempo"), (ChildProcessError(1), "registro de tu app en Modal")):
        Avatar.error, usados = remoto, nube.usados_hoy()
        error = falla(ia.avatar, foto, voz_corta, "9:16", tmp / "h.mp4", error=ia.Cobrado)
        assert motivo in error and "US$0.95" in error and "Ninguna opción" not in error and "Function" not in error, error
        ultima = actividad.ultimas(1)[0]
        assert nube.usados_hoy() == usados + 1 and (ultima["costo"], ultima["resultado"]) == \
            (nube.PRECIO_AVATAR, "fallo"), ultima
    Avatar.error = None
    claves.elegir_por_defecto("limite_nube_diario", 5)
    usados = nube.usados_hoy()

    # Con la casilla: solo el Space oficial de Wan, gratis y sin tocar Modal ni su cupo. Al Space (lo ve su dueño) va
    # una copia con solo los píxeles: ni el EXIF con el GPS, ni el comentario, ni el nombre de la foto
    pedidos = []

    def space_falso(espacio, *entradas, api_name, espera=nubes.ESPERA_HF):
        pedidos.append((espacio, entradas, api_name, espera, Path(entradas[0]["path"]).read_bytes()))
        return {"video": MP4}
    nubes.llamar_space = space_falso
    llamadas = len(Avatar.llamadas)
    assert ia.avatar(movil, voz_corta, "9:16", tmp / "f.mp4", space=True).read_bytes() == MP4
    (espacio, (ref_img, audio, resolucion), api_name, espera, subida), = pedidos
    assert (espacio, api_name, resolucion) == ("Wan-AI/Wan2.2-S2V", "/predict", "480P")
    assert espera >= 600  # Alibaba tarda unos 5-10 min: la espera de siempre (5 min) lo cortaba
    assert Path(audio["path"]) == voz_corta  # subidos como archivos (handle_file)
    assert b"Exif" not in subida and b"Lavc" not in subida and "Maria" not in str(ref_img), ref_img
    assert QImage.fromData(subida).size() == QSize(64, 48)  # la misma foto
    assert len(Avatar.llamadas) == llamadas and nube.usados_hoy() == usados
    assert actividad.ultimas(1)[0]["proveedor"] == "huggingface" and actividad.ultimas(1)[0]["costo"] == 0
    # El Space admite menos de 20 s: una de 19 no se sube
    assert "como mucho 18 s" in falla(ia.avatar, foto, voz_space, "9:16", tmp / "g.mp4", space=True)
    assert len(pedidos) == 1
finally:
    modal.Cls.from_name, nube._cliente, nubes.llamar_space = real

# El «como mucho» que ve el usuario cubre lo más que puede cobrar modal_app.Avatar: sus plazos por la L40S y los topes
# de CPU y RAM. Subir uno sin subir el precio rompe esta prueba. Y el motor acepta toda voz que la app deja pasar
nucleos, mib = (modal_app.RECURSOS_AVATAR[k][1] for k in ("cpu", "memory"))
assert nube.HASTA_AVATAR >= sum(modal_app.PLAZOS_AVATAR.values()) * (
    nube.PRECIO_L40S + nucleos * nube.PRECIO_CPU + mib / 1024 * nube.PRECIO_GIB), modal_app.RECURSOS_AVATAR
assert modal_app.SEGUNDOS_AVATAR >= nube.MAX_AVATAR and nube.PRECIO_AVATAR < nube.HASTA_AVATAR
# Se compara lo que se enseña: 10,04 s es «10.0 s» y cabe; 10,06 s, «10.1 s», no
assert nube.voz_larga(10.04, 10) == "" and "dura 10.1 s" in nube.voz_larga(10.06, 10)
assert all(len(revision) == 40 for revision, _ in modal_app.AVATAR.values()) and len(modal_app.ECHOMIMIC_COMMIT) == 40
assert isinstance(modal_app.Avatar, modal.Cls)  # se importa y define sin red (desplegarlo es cosa de «Instalar motor»)
print("Pruebas del Avatar IA pasadas.")
