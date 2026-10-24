"""Motor de Ráfaga Studio."""
import os

# Privacidad: las librerías de Hugging Face y de Gradio mandan avisos de uso a sus servidores si no se apagan antes de
# importarlas (todo el motor pasa por aquí primero).
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
# Los procesos de Python que lanza la app (Demucs, Modal, reiniciar) no usan las librerías de la cuenta de Windows
# (%APPDATA%\Python): con el Python del instalador se mezclarían con otras versiones.
os.environ.setdefault("PYTHONNOUSERSITE", "1")
# El -E de los accesos directos protege solo a este proceso: los Python que lanza (pip, el reinicio, Modal, Demucs, el
# MCP de prueba) heredarían un PYTHONPATH o un PYTHONHOME que otro programa dejó en Windows y ejecutarían su código.
for _variable in ("PYTHONPATH", "PYTHONHOME"):
    os.environ.pop(_variable, None)
