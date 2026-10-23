"""Página «Mis proyectos»: todo lo creado, para verlo y copiar su texto."""
from PySide6.QtWidgets import QListWidget, QVBoxLayout, QWidget

from motor import shorts
from motor.idioma import t
from ui.comun import etiqueta, Reproductor


class PaginaProyectos(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(etiqueta(t("Mis proyectos"), "titulo"))
        self.lista = QListWidget()
        self.lista.setMaximumHeight(200)
        self.reproductor = Reproductor()
        lay.addWidget(self.lista)
        lay.addWidget(self.reproductor, 1)
        self.lista.currentRowChanged.connect(lambda f: f >= 0 and self.reproductor.mostrar(self.proyectos[f]))

    def showEvent(self, e):
        self.proyectos = shorts.proyectos()  # salta los proyecto.json rotos en vez de romper la página
        self.lista.clear()
        for p in self.proyectos:
            tipo = {"shorts": "⚡ Shorts", "anuncio": f"🚀 {t('Anuncios')}", "musica": f"🎵 {t('Música')}",
                    "videomusical": f"🎬 {t('Video musical')}", "cabina": f"🎙️ {t('Cabina')}",
                    "separacion": f"✂️ {t('Separación')}", "animacion": f"🖼️ {t('Animación')}"
                    }.get(p.get("tipo"), f"✨ {t('Video')}")
            self.lista.addItem(f"{tipo}  ·  {t(p.get('formato', ''))}  ·  {p.get('titulo', '')}  ({len(p['resultados'])})")
        super().showEvent(e)
