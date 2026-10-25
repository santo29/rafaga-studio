"""Iconos de la interfaz: los de Lucide (assets/iconos), de línea fina y en el color del texto, como en las apps
profesionales. Los botones se siguen escribiendo con su emoji delante («📂  Abrir»): boton() lo cambia por el icono."""
from functools import cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from motor import recursos

COLOR = "#ECECF1"
MAPA = {"📄": "file-plus", "📂": "folder-open", "💾": "save", "↶": "undo-2", "↷": "redo-2", "⬇": "download",
        "📁": "folder", "➕": "plus", "🖼️": "image-plus", "🎙️": "mic", "✨": "sparkles", "🔗": "link", "▶": "play",
        "⏸": "pause", "⏹": "square", "✂️": "scissors", "🗑": "trash-2", "📋": "copy", "🔤": "type", "⭐": "sticker",
        "🎵": "music", "🎨": "palette", "🔀": "blend", "💬": "captions", "🎚️": "sliders-horizontal",
        "🎬": "clapperboard", "📷": "camera", "🔎": "search", "🔍": "zoom-in", "🔴": "circle-dot", "🚀": "megaphone",
        "⚡": "zap", "🔑": "key-round", "🔌": "plug", "⬛": "square",
        "▲": "arrow-up", "▼": "arrow-down", "🤖": "bot", "📎": "paperclip", "🎞️": "film", "🏠": "house",
        "🛡️": "shield-check", "🐰": "rabbit", "📅": "calendar-clock", "🧠": "brain", "🔒": "lock",
        "🔓": "lock-open", "⚖️": "scale"}


@cache
def icono(nombre: str, color: str = COLOR) -> QIcon:
    mapa = QPixmap(48, 48)  # de sobra para 16–24 px, también en pantallas con escala
    mapa.fill(Qt.transparent)
    pintor = QPainter(mapa)
    QSvgRenderer(QByteArray(recursos.svg_icono(nombre, color, 2))).render(pintor)
    pintor.end()
    return QIcon(mapa)


def separar(texto: str) -> tuple[str | None, str]:
    """(nombre del icono, texto sin el emoji) si el texto empieza por un emoji conocido; si no, (None, texto)."""
    emoji, _, resto = texto.partition(" ")
    return (MAPA[emoji], resto.strip()) if emoji in MAPA else (None, texto)


def poner(boton, texto: str, color: str = COLOR) -> None:
    """Texto de un botón con su icono de línea en vez del emoji (también al cambiarlo después, como ▶ / ⏸)."""
    nombre, texto = separar(texto)
    boton.setText(texto)
    boton.setIcon(icono(nombre, color) if nombre else QIcon())
    boton.setProperty("icono", nombre or "")  # qué icono lleva (un QIcon copiado no se puede comparar)
