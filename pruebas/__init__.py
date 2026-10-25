"""Pruebas sin internet ni claves. Todas: python -m pruebas · una sola: python -m pruebas.serie"""
import tempfile
from pathlib import Path

from motor import guardia

# Cada proceso de pruebas con su propio historial de Ráfaga Guardia: las pruebas rechazan rutas de red y dicen «No» al
# MCP a propósito, y eso no puede llenar (ni bloquear) el datos/guardia.json de verdad ni el de otra prueba
guardia.ARCHIVO = Path(tempfile.mkdtemp(prefix="rafaga-guardia-")) / "guardia.json"
