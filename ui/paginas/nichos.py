"""Página «Nichos virales»: investigación de nichos con ideas listas para crear."""
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QTextEdit,
                               QVBoxLayout, QWidget)

from motor import ia, idioma, nichos
from motor.idioma import t
from ui.comun import AccionesResultado, boton, etiqueta, mensaje_error, Tarea, tarjeta

# El país va en español al pedido de la IA; se enseña traducido.
PAISES = ("Latinoamérica", "República Dominicana", "México", "Estados Unidos (hispanos)", "España", "Brasil",
          "Mundial (inglés)")
PAIS_DEL_IDIOMA = {"pt": "Brasil", "en": "Mundial (inglés)"}  # el que sale elegido si la app no está en español


class PaginaNichos(QWidget):
    """Investiga nichos virales y manda cualquier idea directo a «Crear con IA»."""
    def __init__(self, crear_video):
        super().__init__()
        self.crear_video = crear_video
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(etiqueta(t("Nichos virales"), "titulo"))
        lay.addWidget(etiqueta(t("Analiza datos reales de YouTube (vistas por día) y, con Claude conectado, investiga "
                                 "en vivo TikTok, Instagram y Facebook. Te da nichos con ideas listas para producir."),
                               "sub"))
        caja, caja_lay = tarjeta()
        fila = QHBoxLayout()
        self.tema = QLineEdit()
        self.tema.setPlaceholderText(t("Tema o palabra clave (si lo dejas vacío, busca lo más viral). Ej.: finanzas, dembow"))
        self.pais = QComboBox()
        for pais in PAISES:
            self.pais.addItem(t(pais), pais)
        self.pais.setCurrentIndex(PAISES.index(PAIS_DEL_IDIOMA.get(idioma.actual(), PAISES[0])))
        self.iniciar = boton(f"🔎  {t('Investigar')}", "principal")
        self.iniciar.clicked.connect(self._iniciar)
        fila.addWidget(self.tema, 1)
        fila.addWidget(self.pais)
        fila.addWidget(self.iniciar)
        caja_lay.addLayout(fila)
        lay.addWidget(caja)
        self.progreso = QProgressBar()
        self.progreso.hide()
        self.estado = etiqueta("", "sub")
        lay.addWidget(self.progreso)
        lay.addWidget(self.estado)
        self.acciones = AccionesResultado()  # el informe: dónde quedó y descargarlo
        lay.addWidget(self.acciones)
        cuerpo = QHBoxLayout()
        self.lista = QListWidget()
        self.lista.setFixedWidth(330)
        self.detalle = QTextEdit()
        self.detalle.setReadOnly(True)
        derecha = QVBoxLayout()
        self.ideas = QListWidget()
        self.ideas.setMaximumHeight(170)
        usar = boton(f"🎬  {t('Crear este video')}", "principal")
        usar.clicked.connect(self._usar_idea)
        derecha.addWidget(self.detalle, 1)
        derecha.addWidget(etiqueta(t("Ideas de video (elige una y créala)"), "sub"))
        derecha.addWidget(self.ideas)
        derecha.addWidget(usar, 0, Qt.AlignRight)
        cuerpo.addWidget(self.lista)
        cuerpo.addLayout(derecha, 1)
        lay.addLayout(cuerpo, 1)
        self.lista.currentRowChanged.connect(self._mostrar)
        self.nichos, self.tarea = [], None

    def _iniciar(self):
        self.iniciar.setEnabled(False)
        self.progreso.show()
        self.tarea = Tarea(nichos.investigar, tema=self.tema.text(), pais=self.pais.currentData())
        self.tarea.progreso.connect(lambda t, f: (self.estado.setText(t), self.progreso.setValue(int(f * 100))))
        self.tarea.listo.connect(self._listo)
        self.tarea.fallo.connect(lambda e: (self.estado.setText(""),
                                            mensaje_error(self, t("No se pudo investigar"), e)))
        self.tarea.finished.connect(lambda: (self.iniciar.setEnabled(True), self.progreso.hide()))
        self.tarea.start()

    def _listo(self, r):
        self.estado.setText("\n".join([*r.get("avisos", []), r["resumen"]]))  # p. ej. «la web tardó demasiado»
        self.nichos = r["nichos"]
        self.lista.clear()
        for n in self.nichos:
            self.lista.addItem(t("{potencial}/100 · {nombre}\ncompetencia {competencia}",
                                 potencial=n["potencial"], nombre=n["nombre"], competencia=n["competencia"]))
        if self.nichos:
            self.lista.setCurrentRow(0)
        self._guardar_informe(r)

    def _guardar_informe(self, r):
        """El informe en texto, junto al que guarda el motor (en JSON, que no se lee bien): se dice dónde quedó y se
        puede descargar."""
        informe = nichos.PROYECTOS.parent / "nichos" / time.strftime("%Y%m%d-%H%M%S.txt")
        texto = "\n\n".join([r["resumen"]] + [
            self._texto(n) + "\n\n" + "\n\n".join(t("{titulo}\nGancho: {gancho}", titulo=i["titulo"],
                                                    gancho=i["gancho"]) for i in n["ideas"])
            for n in self.nichos])
        try:
            informe.parent.mkdir(parents=True, exist_ok=True)
            informe.write_text(texto, encoding="utf-8")
        except OSError:  # el motor ya guardó el suyo: sin el de texto, solo no se ofrece descargarlo
            return self.acciones.hide()
        self.acciones.mostrar(informe, f"{t('Nichos virales')} {r.get('tema', '')}")

    @staticmethod
    def _texto(n) -> str:
        return (t("{nombre} ({potencial}/100, competencia {competencia})\n\nPor qué es viral: {viral}\n\n"
                  "Pruebas: {pruebas}\n\nRedes: {redes}\nFormato: {formato}\nMonetización: {monetizacion}\n\n",
                  nombre=n["nombre"], potencial=n["potencial"], competencia=n["competencia"],
                  viral=n["por_que_es_viral"], pruebas=n["pruebas"], redes=", ".join(n["redes"]),
                  formato=n["formato"], monetizacion=n["monetizacion"])
                + " ".join(map(ia.hashtag, n["hashtags"])))

    def _mostrar(self, fila):
        if fila < 0:
            return
        n = self.nichos[fila]
        self.detalle.setPlainText(self._texto(n))
        self.ideas.clear()
        for idea in n["ideas"]:
            item = QListWidgetItem(t("{titulo}\nGancho: {gancho}", titulo=idea["titulo"], gancho=idea["gancho"]))
            item.setData(Qt.UserRole, idea["prompt"])
            self.ideas.addItem(item)

    def _usar_idea(self):
        item = self.ideas.currentItem()
        if item:
            self.crear_video(item.data(Qt.UserRole))
