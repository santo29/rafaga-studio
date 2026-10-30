"""Motor de video IA en la nube de Modal (corre en sus GPU, no en este PC).

Ráfaga Studio lo instala solo desde "Claves de IA" → "Instalar motor de video en Modal".
Modelos: Wan 2.2 TI2V-5B (imagen → video de ~5 s en 720p; aprox. $0.20–0.35 por clip en H100) y, para el Avatar IA,
EchoMimicV3-Flash (foto + voz de hasta 10 s → video que habla; aprox. $0.30–0.35 en L40S, como mucho $0.95).
"""
import modal

app = modal.App("rafaga-studio-video")
# Los pesos se bajan una sola vez. Nombre propio: «hf-hub-cache» es el de los ejemplos de Modal, y otra app de la
# misma cuenta que lo use podría cambiar los pesos que carga este motor.
cache = modal.Volume.from_name("rafaga-studio-hf-cache", create_if_missing=True)

imagen = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    # Como en el PC: solo archivos ya compilados (nada de ejecutar código de instalación) y publicados hace 7 días o
    # más (si uno sale malicioso, da tiempo a que lo retiren). Lo sabe hacer el pip del lock (26+).
    # ponytail: versiones sin fijar (no hay lock para Linux con GPU); si una actualización rompe el motor, fijarlas aquí.
    .pip_install("pip==26.2.2")
    .pip_install("torch", "diffusers>=0.35", "transformers", "accelerate", "ftfy", "sentencepiece",
                 "imageio", "imageio-ffmpeg", "pillow", "numpy",
                 extra_options="--only-binary :all: --uploaded-prior-to P7D")
    .env({"HF_HUB_CACHE": "/models", "HF_XET_HIGH_PERFORMANCE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"})
)

MODELO = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
NEGATIVO = ("blurry, low quality, static, distorted face, deformed hands, extra fingers, watermark, text, "
            "subtitles, jpeg artifacts, flicker")

# Avatar IA: EchoMimicV3-Flash (Ant Group, Apache 2.0), montado como el benchmark de tight-studio que lo midió en Modal
# (runners/modal/echomimic_v3_flash_modal.py). Su código, fijado a un commit, y cada modelo a su revisión entera: un
# cambio en GitHub o en Hugging Face nunca llega solo. Unos 22 GiB en el mismo volumen.
ECHOMIMIC, ECHOMIMIC_COMMIT, CODIGO_AVATAR = ("https://github.com/antgroup/echomimic_v3.git",
                                              "7e89489ca51c0d008fc1963ec6c03fc5bd0b9397", "/opt/echomimic_v3")
AVATAR = {  # repo: (revisión, lo que se baja)
    "alibaba-pai/Wan2.1-Fun-V1.1-1.3B-InP": ("fc913c34361f4ec879e2f9c78b4f11ae50a937d1", [
        "Wan2.1_VAE.pth", "config.json", "configuration.json", "diffusion_pytorch_model.safetensors",
        "google/umt5-xxl/*", "models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth",
        "models_t5_umt5-xxl-enc-bf16.pth", "xlm-roberta-large/*"]),
    "BadToBest/EchoMimicV3": ("311e176905a8c4c24b240b530488fe636ce4d249", ["echomimicv3-flash-pro/*"]),
    "TencentGameMate/chinese-wav2vec2-base": ("3991242c806928916fff4a8c0e4f76acf661b743", [
        "config.json", "preprocessor_config.json", "pytorch_model.bin"]),
}
# Segundos: lo más que puede durar (y cobrarse) un avatar. nube.HASTA_AVATAR, el «como mucho» que ve el usuario, sale
# de aquí: una prueba falla si se suben sin subir ese precio
PLAZOS_AVATAR = {"startup_timeout": 300, "timeout": 900, "scaledown_window": 60}
# Núcleos de CPU y MiB de RAM: (lo pedido, el tope). Modal cobra lo que se usa y el tope no se pasa: sin él, la RAM y la
# CPU no tenían techo (su benchmark pidió 64 GiB). El «como mucho» también sale de aquí
RECURSOS_AVATAR = {"cpu": (2, 4), "memory": (16384, 65536)}
SEGUNDOS_AVATAR = 10.5  # la voz más larga que acepta: los 10 s de la app (nube.MAX_AVATAR) y margen al medir
FPS_AVATAR = 25  # los del modelo
PROMPT_AVATAR = ("A person speaks naturally to the camera. Static camera, stable identity, clothing, and background, "
                 "subtle conversational gestures.")

imagen_avatar = (
    modal.Image.debian_slim(python_version="3.10")  # la de su benchmark: decord y estas versiones se probaron en 3.10
    .apt_install("ffmpeg", "git", "libgl1", "libglib2.0-0", "libsndfile1")
    .pip_install("pip==26.2.2")
    # La misma regla que la otra imagen (solo compilado y con 7 días o más). torch, diffusers, transformers y moviepy,
    # en las versiones del benchmark; torch 2.6.0 de PyPI ya trae CUDA 12.4, la del índice de PyTorch que usó él.
    # ponytail: el resto sin fijar, como en el benchmark; si una actualización rompe el avatar, fijarlas aquí.
    .pip_install("torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0", "diffusers==0.35.2",
                 "transformers==4.57.3", "moviepy==2.2.1", "numpy<2", "Pillow", "einops", "safetensors", "timm",
                 "torchdiffeq", "torchsde", "decord", "scikit-image", "opencv-python", "omegaconf", "SentencePiece",
                 "imageio[ffmpeg]", "ftfy", "accelerate", "librosa", "mmgp", "pyloudnorm", "huggingface_hub",
                 extra_options="--only-binary :all: --uploaded-prior-to P7D")
    .run_commands(f"git clone {ECHOMIMIC} {CODIGO_AVATAR}", f"git -C {CODIGO_AVATAR} checkout {ECHOMIMIC_COMMIT}")
    .env({"HF_HUB_CACHE": "/models", "HF_XET_HIGH_PERFORMANCE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
          "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"})
)


@app.function(image=imagen, volumes={"/models": cache}, timeout=3600)
def preparar() -> str:
    """Baja los pesos de los modelos al volumen con una CPU (casi gratis). Si no, los bajaba la GPU en su primer uso:
    unos minutos de GPU pagados solo por descargar."""
    from huggingface_hub import snapshot_download
    snapshot_download(MODELO)
    for repo, (revision, archivos) in AVATAR.items():
        snapshot_download(repo, revision=revision, allow_patterns=archivos)
    cache.commit()
    return "listo"


@app.cls(image=imagen, gpu="H100", volumes={"/models": cache}, timeout=1800, scaledown_window=60)
class Wan:
    @modal.enter()
    def cargar(self):
        import torch
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
        vae = AutoencoderKLWan.from_pretrained(MODELO, subfolder="vae", torch_dtype=torch.float32)
        self.pipe = WanImageToVideoPipeline.from_pretrained(MODELO, vae=vae, torch_dtype=torch.bfloat16).to("cuda")

    @modal.method()
    def animar(self, imagen_png: bytes, prompt: str, vertical: bool, segundos: float = 5.0, pasos: int = 30) -> bytes:
        import io
        import tempfile

        from diffusers.utils import export_to_video
        from PIL import Image, ImageOps

        ancho, alto = (704, 1280) if vertical else (1280, 704)  # 720p nativo del modelo
        foto = ImageOps.fit(Image.open(io.BytesIO(imagen_png)).convert("RGB"), (ancho, alto))
        cuadros = int(min(max(segundos, 2), 5) * 24) // 4 * 4 + 1  # el modelo pide 4n+1 cuadros
        frames = self.pipe(image=foto, prompt=prompt, negative_prompt=NEGATIVO, height=alto, width=ancho,
                           num_frames=cuadros, guidance_scale=5.0, num_inference_steps=pasos).frames[0]
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            export_to_video(frames, f.name, fps=24)
            return open(f.name, "rb").read()


# L40S (48 GB): su benchmark midió 33,7 GB. Uno a la vez: dos avatares seguidos no pagan dos GPU
@app.cls(image=imagen_avatar, gpu="L40S", volumes={"/models": cache}, max_containers=1, **PLAZOS_AVATAR,
         **RECURSOS_AVATAR)
class Avatar:
    @modal.method()
    def hablar(self, foto: bytes, voz_wav: bytes, vertical: bool) -> bytes:
        """Tu foto hablando con tu voz: un MP4 de 480×848 (848×480 si no es vertical) a 25 fps con la voz ya dentro.
        Corre infer_flash.py de EchoMimicV3 como su benchmark (8 pasos).
        ponytail: un subproceso por llamada recarga el modelo (unos US$0,05); pasar a @modal.enter si el coste
        importa."""
        import io
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        from huggingface_hub import snapshot_download
        from PIL import Image, ImageOps

        with tempfile.TemporaryDirectory() as carpeta:
            carpeta = Path(carpeta)
            voz, imagen = carpeta / "voz.wav", carpeta / "foto.png"
            voz.write_bytes(voz_wav)
            segundos = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                             "csv=p=0", str(voz)], check=True, capture_output=True, text=True).stdout)
            if not 0 < segundos <= SEGUNDOS_AVATAR:  # la app ya lo mira antes de gastar: esto es por si otra se pasa
                raise ValueError(f"la voz dura {segundos:.1f} s; el avatar admite hasta {SEGUNDOS_AVATAR} s")
            foto_rgb = ImageOps.exif_transpose(Image.open(io.BytesIO(foto))).convert("RGB")
            ImageOps.fit(foto_rgb, (480, 848) if vertical else (848, 480)).save(imagen)  # la resolución medida
            base, flash, wav2vec = (snapshot_download(repo, revision=revision, allow_patterns=archivos)
                                    for repo, (revision, archivos) in AVATAR.items())
            cuadros = int(SEGUNDOS_AVATAR * FPS_AVATAR) // 4 * 4 + 1  # el tope (4n+1): usa los que dure la voz
            r = subprocess.run([sys.executable, "infer_flash.py", "--config_path", "config/config.yaml",
                                "--model_name", base, "--transformer_path",
                                f"{flash}/echomimicv3-flash-pro/diffusion_pytorch_model.safetensors",
                                "--wav2vec_model_dir", wav2vec, "--save_path", str(carpeta),
                                "--image_path", str(imagen), "--audio_path", str(voz), "--prompt", PROMPT_AVATAR,
                                "--video_length", str(cuadros),
                                "--num_inference_steps", "8", "--guidance_scale", "4", "--audio_guidance_scale", "2",
                                "--sample_size", "768", "768", "--seed", "43", "--fps", str(FPS_AVATAR)],
                               cwd=CODIGO_AVATAR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print(r.stdout)  # al registro de la app en Modal: el detalle (en inglés) se queda ahí
            if r.returncode:  # a la app, solo la causa: nube.avatar la dice en el idioma del usuario
                raise MemoryError() if "OutOfMemoryError" in r.stdout else ChildProcessError(r.returncode)
            return (carpeta / "foto_output.mp4").read_bytes()  # infer_flash.py lo llama «<foto>_output.mp4»
