"""Motor de Ráfaga Studio."""
import os

# Privacidad: las librerías de Hugging Face y de Gradio mandan avisos de uso a sus servidores si no se apagan antes de
# importarlas (todo el motor pasa por aquí primero).
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
