"""Que las partes del estudio digan y usen lo mismo (sin red ni claves): python pruebas_coherencia.py"""
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RAFAGA_IDIOMA", "es")
from motor import anuncios, desde_prompt, director, diseno_ia, herramientas, ia, musica, nichos, serie  # noqa: E402
from ui.paginas import diseno as pagina_diseno  # noqa: E402
from ui.paginas.director import PAGINA  # noqa: E402

RAIZ = Path(__file__).resolve().parent

# La regla de las faltas de ortografía, la misma en todas las IA que leen lo que escribe el usuario
for instrucciones in (desde_prompt.INSTRUCCIONES, anuncios.INSTRUCCIONES, director.INSTRUCCIONES, musica.INSTRUCCIONES,
                      nichos.INSTRUCCIONES, diseno_ia.INSTRUCCIONES, diseno_ia.INSTRUCCIONES_ENTENDER,
                      serie.INSTRUCCIONES_SERIE, serie.INSTRUCCIONES_EPISODIO):
    assert ia.FALTAS in instrucciones, instrucciones[:60]

# El estudio de dibujos animados se llama igual en todas partes
for archivo in [RAIZ / "app.py", *(RAIZ / "ui").rglob("*.py"), *(RAIZ / "motor").glob("*.py")]:
    assert "Serie animada" not in archivo.read_text(encoding="utf-8"), archivo

# Cada página a la que lleva el Director (y que ilumina) es un botón del menú
menu = set(re.findall(r"t\('([^']+)'\)\}\", self\.|t\('([^']+)'\)\}\", Pagina", (RAIZ / "app.py").read_text(encoding="utf-8")))
menu = {nombre for par in menu for nombre in par if nombre}
assert set(PAGINA.values()) <= menu, set(PAGINA.values()) - menu

# Diseño: los tipos y estilos del motor son los de la pantalla y los que conoce el Director o un agente MCP
assert set(pagina_diseno.TIPOS_IA) == {"auto", *diseno_ia.TIPOS}
assert set(pagina_diseno.ESTILOS_IA) == set(diseno_ia.ESTILOS)
ayuda = herramientas.crear_diseno.__doc__
assert all(tipo in ayuda for tipo in diseno_ia.TIPOS) and all(estilo in ayuda for estilo in diseno_ia.ESTILOS)
print("Pruebas de coherencia pasadas.")
