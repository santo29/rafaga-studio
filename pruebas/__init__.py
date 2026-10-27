"""Pruebas sin internet ni claves. Todas: python -m pruebas · una sola: python -m pruebas.serie"""
import ipaddress
import socket
import tempfile
from pathlib import Path

from motor import actividad, claves, guardia

# Sin internet de verdad, también para los SDK (openai, anthropic) que no pasan por los httpx falsos de cada prueba:
# una prueba que olvidaba una IA falsa mandaba sus textos y su clave de prueba a gen.pollinations.ai. Solo este PC
_resolver = socket.getaddrinfo


def _solo_este_pc(host, *a, **k):
    nombre = host.decode() if isinstance(host, bytes) else str(host or "")
    try:  # una IP escrita no se busca en la red (las pruebas de seguro.py comprueban IP como 198.18.0.5)
        ipaddress.ip_address(nombre)
        return _resolver(host, *a, **k)
    except ValueError:
        pass
    if nombre in ("", "localhost") or nombre.endswith(".localhost"):
        return _resolver(host, *a, **k)
    raise socket.gaierror(socket.EAI_NONAME, f"sin internet en las pruebas: {nombre}")


socket.getaddrinfo = _solo_este_pc

# Cada proceso de pruebas con su propio historial de Ráfaga Guardia: las pruebas rechazan rutas de red y dicen «No» al
# MCP a propósito, y eso no puede llenar (ni bloquear) el datos/guardia.json de verdad ni el de otra prueba
_tmp = Path(tempfile.mkdtemp(prefix="rafaga-guardia-"))
guardia.ARCHIVO = _tmp / "guardia.json"
# Igual la actividad de la IA y el estado de las conexiones: las IA falsas de las pruebas no pueden salir en «Claves de
# IA» como gasto de verdad, ni un «sin saldo» de prueba avisar al dueño antes de sus trabajos
actividad.ARCHIVO = _tmp / "actividad.json"
claves.CONEXIONES = _tmp / "conexiones.json"
