"""Gestiona la conexión MCP: registra Ráfaga Studio en Claude Code y Claude Desktop, y comprueba que responde."""
import json
import os
import subprocess
import sys
from pathlib import Path

from .idioma import t

RAIZ = Path(__file__).resolve().parent.parent
NOMBRE = "rafaga-studio"
PYTHON = str(Path(sys.executable).with_name("python.exe"))  # pythonw no sirve para stdio
# -s -E: un PYTHONPATH, un PYTHONHOME o las librerías de la cuenta de Windows no se meten en el servidor (Claude lo
# arranca con su propio entorno). -E también ignora PYTHONIOENCODING: -X utf8 hace lo mismo. Nunca -I: quitaría la
# carpeta de la app de sys.path y no encontraría «motor».
SERVIDOR = {
    "type": "stdio",
    "command": PYTHON,
    "args": ["-s", "-E", "-X", "utf8", str(RAIZ / "mcp_server.py")],
    "env": {"HF_HUB_DISABLE_SYMLINKS_WARNING": "1"},
}

CLIENTES = {
    "Claude Code": Path.home() / ".claude.json",
    "Claude Desktop (chat)": Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json",
}


def _leer(archivo: Path) -> dict:
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8-sig"))  # -sig: acepta archivos guardados con BOM
    except FileNotFoundError:
        return {}
    # Formato inesperado: mejor no tocarla que machacar la config del usuario.
    if not isinstance(datos, dict) or not isinstance(datos.get("mcpServers") or {}, dict):
        raise ValueError(t("La configuración de Claude tiene un formato inesperado: {archivo}", archivo=archivo))
    return datos


def _escribir(archivo: Path, datos: dict) -> None:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    temporal = archivo.with_name(archivo.name + ".tmp-rafaga")  # atómico: nunca deja la config de Claude a medias
    temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, archivo)
    # Sin copias: la config de Claude lleva los tokens de otros servidores MCP, y una copia en claro los guardaría
    # aunque el usuario los quite. Se borra la que dejaban las versiones anteriores.
    archivo.with_name(archivo.name + ".bak-rafaga").unlink(missing_ok=True)


def estado() -> dict[str, bool]:
    resultado = {}
    for cliente, archivo in CLIENTES.items():
        try:  # una config de Claude ilegible cuenta como «sin conectar»; no debe impedir abrir la app
            resultado[cliente] = NOMBRE in (_leer(archivo).get("mcpServers") or {})
        except Exception:  # cualquier fallo al leerla (incluso JSON absurdo): «sin conectar», nunca tumba la app
            resultado[cliente] = False
    return resultado


def conectar(cliente: str) -> None:
    archivo = CLIENTES[cliente]
    datos = _leer(archivo)
    servidor = SERVIDOR if cliente == "Claude Code" else {k: v for k, v in SERVIDOR.items() if k != "type"}
    datos["mcpServers"] = {**(datos.get("mcpServers") or {}), NOMBRE: servidor}
    _escribir(archivo, datos)


def desconectar(cliente: str) -> None:
    archivo = CLIENTES[cliente]
    datos = _leer(archivo)
    # También el ámbito local de cada proyecto de Claude Code (~/.claude.json → projects), que gana al de usuario:
    # así «Desconectar» y «Conectar» arreglan un registro cambiado ahí (Ráfaga Guardia lo revisa)
    proyectos = datos.get("projects") if isinstance(datos.get("projects"), dict) else {}
    registros = [datos.get("mcpServers") or {},
                 *(p.get("mcpServers") for p in proyectos.values() if isinstance(p, dict))]
    if [r.pop(NOMBRE) for r in registros if isinstance(r, dict) and NOMBRE in r]:
        _escribir(archivo, datos)


def desconectar_todo() -> None:
    """Al desinstalar (rafaga.iss): ningún Claude sigue arrancando el python.exe de una carpeta que ya no es de la app."""
    for cliente in CLIENTES:
        try:
            desconectar(cliente)
        except Exception:  # una config ilegible no impide limpiar la otra
            pass


def probar() -> list[str]:
    """Arranca el servidor como lo haría Claude y devuelve los nombres de sus herramientas."""
    proc = subprocess.Popen([SERVIDOR["command"], *SERVIDOR["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", env={**os.environ, **SERVIDOR["env"]},
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        def enviar(m):
            proc.stdin.write(json.dumps(m) + "\n")
            proc.stdin.flush()
        enviar({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "rafaga", "version": "1"}}})
        json.loads(proc.stdout.readline())
        enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        enviar({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        return [t["name"] for t in json.loads(proc.stdout.readline())["result"]["tools"]]
    finally:
        proc.kill()


def comando_manual() -> str:
    """Para otros clientes MCP (Cursor, Windsurf…): el comando que deben ejecutar."""
    return " ".join(f'"{a}"' for a in (SERVIDOR["command"], *SERVIDOR["args"]))
