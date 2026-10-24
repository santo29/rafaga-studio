"""Motor de video IA en la nube de Modal (corre en sus GPU, no en este PC).

Ráfaga Studio lo instala solo desde "Claves de IA" → "Instalar motor de video en Modal".
Modelo: Wan 2.2 TI2V-5B (imagen → video de ~5 s en 720p). Coste aprox.: $0.20–0.35 por clip en H100.
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


@app.function(image=imagen, volumes={"/models": cache}, timeout=3600)
def preparar() -> str:
    """Baja los pesos del modelo al volumen con una CPU (casi gratis). Si no, los bajaba la H100 en su primer clip:
    unos minutos de GPU pagados solo por descargar."""
    from huggingface_hub import snapshot_download
    snapshot_download(MODELO)
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
