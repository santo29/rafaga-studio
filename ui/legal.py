"""Lo legal en la app: el aviso de privacidad y los términos, que se aceptan al primer uso (y otra vez si cambian), y la
ventana «Privacidad y legal» con la marca y los documentos (PRIVACIDAD.md, TERMINOS.md, AVISOS_DE_TERCEROS.md, LICENSE)."""
import json
import time
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout

from motor import diseno
from motor.idioma import t
from ui.comun import boton, etiqueta

RAIZ = Path(__file__).resolve().parent.parent
VERSION = "12"  # súbela cuando cambien PRIVACIDAD.md o TERMINOS.md: la app los vuelve a mostrar
ARCHIVO = RAIZ / "datos" / "legal.json"
TITULAR, ANIO = "Santo Montilla", 2026
DOCUMENTOS = {"PRIVACIDAD.md": t("Aviso de privacidad"), "TERMINOS.md": t("Términos de uso"),
              "AVISOS_DE_TERCEROS.md": t("Avisos de terceros"), "LICENSE": t("Licencia"),
              "SECURITY.md": t("Política de seguridad")}  # sin botón propio: se abre desde sus enlaces


def marca() -> str:
    return t("Ráfaga Studio™ · © {anio} {titular}. Todos los derechos reservados.", anio=ANIO, titular=TITULAR)


def pendiente() -> bool:
    """Si todavía no se aceptó esta versión del aviso y los términos."""
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8")).get("aceptado") != VERSION
    except (OSError, ValueError, AttributeError):
        return True


def aceptar() -> None:
    diseno.escribir_json(ARCHIVO, {"aceptado": VERSION, "fecha": time.strftime("%Y-%m-%d %H:%M")})


def ver_documento(padre, archivo: str) -> QDialog:
    """Un documento legal (Markdown de la carpeta de la app) en una ventana con el estilo de la app."""
    ventana = QDialog(padre)
    ventana.setWindowTitle(DOCUMENTOS.get(archivo, archivo))
    ventana.resize(820, 640)
    lay = QVBoxLayout(ventana)
    texto = QTextBrowser()
    texto.setOpenLinks(False)  # nada navega a internet: un enlace a otro documento legal lo abre en su ventana
    texto.anchorClicked.connect(lambda url: url.path() in DOCUMENTOS and ver_documento(padre, url.path()))
    try:
        contenido = (RAIZ / archivo).read_text(encoding="utf-8")
    except OSError:
        contenido = t("No encuentro {archivo} en la carpeta de la app.", archivo=archivo)
    texto.setMarkdown(contenido)  # LICENSE también es Markdown: sin `comillas` ni líneas cortadas a 80 columnas
    lay.addWidget(texto)
    cerrar = boton(t("Cerrar"))
    cerrar.clicked.connect(ventana.accept)
    lay.addWidget(cerrar, 0, Qt.AlignRight)
    ventana.setAttribute(Qt.WA_DeleteOnClose)
    ventana.open()
    return ventana


def _botones_documentos(padre, lay, cuales):
    fila = QHBoxLayout()
    for archivo in cuales:
        b = boton(DOCUMENTOS[archivo])
        b.clicked.connect(lambda _=False, a=archivo: ver_documento(padre, a))
        fila.addWidget(b)
    fila.addStretch()
    lay.addLayout(fila)


def _vineta(lay, punto: str):
    """«•» y el texto en dos etiquetas: lo que salta de línea queda alineado con el texto, no debajo de la viñeta."""
    fila = QHBoxLayout()
    fila.addWidget(etiqueta("•"), 0, Qt.AlignTop)
    fila.addWidget(etiqueta(punto), 1)
    lay.addLayout(fila)


def _cabecera(lay, titulo: str):
    fila = QHBoxLayout()
    logo = QLabel()
    logo.setPixmap(QPixmap(str(RAIZ / "assets" / "icono.png")).scaled(44, 44, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation))
    fila.addWidget(logo)
    fila.addWidget(etiqueta(titulo, "titulo"), 1)
    lay.addLayout(fila)


PUNTOS = (
    t("Ráfaga Studio se instala y guarda tus proyectos en tu PC. No tenemos servidores ni cuentas y no recogemos "
      "datos, pero las funciones de IA usan servicios de internet."),
    t("Tus proyectos y tus claves se guardan solo en este PC; las claves, cifradas con tu cuenta de Windows."),
    t("Para crear, la app envía tus pedidos, textos e imágenes directo a servicios de IA de terceros, también sin "
      "claves: Pollinations, un Space público de Hugging Face y las voces de Microsoft. El aviso de privacidad dice qué "
      "va a cada uno."),
    t("Usa contenido propio o con permiso, y avisa cuando algo realista esté hecho con IA."),
)


def aviso_inicial(padre=None) -> bool:
    """El aviso de privacidad y los términos, antes de empezar. True si se aceptan (queda guardado)."""
    ventana = QDialog(padre)
    ventana.setWindowTitle(t("Bienvenido a Ráfaga Studio"))
    ventana.setFixedWidth(680)  # con ancho fijo, Qt calcula bien el alto de los textos que saltan de línea
    lay = QVBoxLayout(ventana)
    lay.setContentsMargins(26, 24, 26, 22)
    lay.setSpacing(12)
    _cabecera(lay, t("Bienvenido a Ráfaga Studio"))
    lay.addWidget(etiqueta(t("Antes de empezar, lo importante sobre tu privacidad:"), "sub"))
    for punto in PUNTOS:
        _vineta(lay, punto)
    _botones_documentos(ventana, lay, ("PRIVACIDAD.md", "TERMINOS.md"))
    lay.addWidget(etiqueta(t("Al continuar aceptas el aviso de privacidad y los términos de uso."), "sub"))
    fila = QHBoxLayout()
    fila.addStretch()
    salir, aceptar_btn = boton(t("Salir")), boton(f"✨  {t('Acepto, empezar')}", "principal")
    salir.clicked.connect(ventana.reject)
    aceptar_btn.clicked.connect(ventana.accept)
    fila.addWidget(salir)
    fila.addWidget(aceptar_btn)
    lay.addLayout(fila)
    lay.addWidget(etiqueta(marca(), "sub"))
    aceptar_btn.setDefault(True)
    aceptado = ventana.exec() == QDialog.Accepted
    # Ya mismo: sus botones la mantenían viva y, destruida al final (después que Qt), la app se caía al cerrarse
    shiboken6.delete(ventana)
    if aceptado:
        aceptar()
    return aceptado


def acerca_de(padre) -> QDialog:
    """«Privacidad y legal»: la marca, cómo se protegen tus datos y los documentos."""
    ventana = QDialog(padre)
    ventana.setWindowTitle(t("Privacidad y legal"))
    ventana.setFixedWidth(720)
    lay = QVBoxLayout(ventana)
    lay.setContentsMargins(26, 24, 26, 22)
    lay.setSpacing(12)
    _cabecera(lay, "Ráfaga Studio™")
    lay.addWidget(etiqueta(marca(), "sub"))
    for punto in PUNTOS[:3]:
        _vineta(lay, punto)
    _botones_documentos(ventana, lay, ("PRIVACIDAD.md", "TERMINOS.md", "AVISOS_DE_TERCEROS.md", "LICENSE"))
    cerrar = boton(t("Cerrar"))
    cerrar.clicked.connect(ventana.accept)
    lay.addWidget(cerrar, 0, Qt.AlignRight)
    ventana.setAttribute(Qt.WA_DeleteOnClose)
    ventana.open()
    return ventana
