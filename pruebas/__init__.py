"""Pruebas sin internet ni claves. Todas: python -m pruebas · una sola: python -m pruebas.serie"""
import tempfile
from pathlib import Path

from motor import actividad, claves, guardia

# Cada proceso de pruebas con su propio historial de Ráfaga Guardia: las pruebas rechazan rutas de red y dicen «No» al
# MCP a propósito, y eso no puede llenar (ni bloquear) el datos/guardia.json de verdad ni el de otra prueba
_tmp = Path(tempfile.mkdtemp(prefix="rafaga-guardia-"))
guardia.ARCHIVO = _tmp / "guardia.json"
# Igual la actividad de la IA y el estado de las conexiones: las IA falsas de las pruebas no pueden salir en «Claves de
# IA» como gasto de verdad, ni un «sin saldo» de prueba avisar al dueño antes de sus trabajos
actividad.ARCHIVO = _tmp / "actividad.json"
claves.CONEXIONES = _tmp / "conexiones.json"
