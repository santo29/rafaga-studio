"""Página «Conexión MCP»: conectar Ráfaga Studio con Claude y otros agentes."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from motor import conexion_mcp
from motor.idioma import t
from ui.comun import boton, etiqueta, mensaje_error, Tarea, tarjeta


class PaginaMCP(QWidget):
    """Conecta Ráfaga Studio a Claude por MCP, para pedirle videos desde el chat."""
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(etiqueta(t("Conexión MCP"), "titulo"))
        lay.addWidget(etiqueta(t("Con MCP, Claude puede usar Ráfaga Studio: le pides \"hazme 5 shorts de este enlace\" "
                                 "en el chat y él lo hace aquí. Después de conectar, abre una sesión nueva de Claude."),
                               "sub"))
        caja, self.caja_lay = tarjeta()
        self.filas = {}
        for cliente in conexion_mcp.CLIENTES:
            fila = QHBoxLayout()
            estado = etiqueta("")
            accion = boton("")
            accion.clicked.connect(lambda _, c=cliente: self._alternar(c))
            nombre = etiqueta(cliente)
            nombre.setFixedWidth(230)
            fila.addWidget(nombre)
            fila.addWidget(estado, 1)
            fila.addWidget(accion)
            self.caja_lay.addLayout(fila)
            self.filas[cliente] = (estado, accion)
        lay.addWidget(caja)
        prueba, prueba_lay = tarjeta()
        self.resultado = etiqueta(t("Pulsa \"Probar\" para comprobar que el servidor responde."), "sub")
        self.probar = boton(t("Probar conexión"), "principal")
        self.probar.clicked.connect(self._probar)
        prueba_lay.addWidget(self.resultado)
        prueba_lay.addWidget(self.probar, 0, Qt.AlignLeft)
        lay.addWidget(prueba)
        otros, otros_lay = tarjeta()
        otros_lay.addWidget(etiqueta(t("Otros programas con MCP (Cursor, Windsurf…): usa este comando"), "sub"))
        comando = QLineEdit(conexion_mcp.comando_manual())
        comando.setReadOnly(True)
        copiar = boton(t("Copiar comando"))
        copiar.clicked.connect(lambda: QGuiApplication.clipboard().setText(comando.text()))
        otros_lay.addWidget(comando)
        otros_lay.addWidget(copiar, 0, Qt.AlignLeft)
        lay.addWidget(otros)
        lay.addStretch()
        self.tarea = None
        self._refrescar()

    def _refrescar(self):
        for cliente, conectado in conexion_mcp.estado().items():
            estado, accion = self.filas[cliente]
            estado.setText(f"🟢 {t('Conectado')}" if conectado else f"⚪ {t('Sin conectar')}")
            accion.setText(t("Desconectar") if conectado else t("Conectar"))

    def _alternar(self, cliente):
        try:
            (conexion_mcp.desconectar if conexion_mcp.estado()[cliente] else conexion_mcp.conectar)(cliente)
        except (OSError, ValueError) as e:
            mensaje_error(self, t("No se pudo cambiar la conexión"), str(e))
        self._refrescar()

    def _probar(self):
        self.probar.setEnabled(False)
        self.resultado.setText(t("Arrancando el servidor…"))
        self.tarea = Tarea(lambda aviso: {"herramientas": conexion_mcp.probar()})
        self.tarea.listo.connect(lambda r: self.resultado.setText("✅ " + t(
            "Responde. Herramientas que Claude puede usar: {lista}", lista=", ".join(r["herramientas"]))))
        self.tarea.fallo.connect(lambda e: self.resultado.setText("❌ " + t("No responde: {error}", error=e)))
        self.tarea.finished.connect(lambda: self.probar.setEnabled(True))
        self.tarea.start()
