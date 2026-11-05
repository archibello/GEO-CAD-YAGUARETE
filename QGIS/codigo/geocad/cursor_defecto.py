# SPDX-License-Identifier: GPL-3.0-or-later
"""El cursor de GeoCAD es la herramienta por defecto de QGIS (módulo «Cursor de
GeoCAD», 3.67).

Pedido de Fernando (05/11/2026): «la opción por defecto del cursor, en todo
momento, sea la del cursor de geocad, dado que es la única que acepta ESC para
deseleccionar objetos». Acordado:

- queda activo al abrir QGIS, al abrir o crear un proyecto y cuando el mapa se
  queda sin herramienta; la que se elige a propósito se respeta;
- Esc, en reposo, deselecciona todas las capas, también con el foco en el panel
  de capas, y con Desplazar, las de acercar, Identificar, Seleccionar o Vértices
  vuelve al cursor;
- en la herramienta de vértices de QGIS (3.69), también: cancela lo que se esté moviendo;
- Agregar entidad, Medir y demás conservan su Esc sobre el mapa;
- nunca en campos de texto, tablas que se editan al teclear, ni diálogos.

Los módulos de Qt y lo propio de QGIS entran por parámetro, como en teclado.py.
"""
from __future__ import annotations

from .teclado import _ESC, Teclado, con_modificadores, nombre_tecla, protegido

#: las herramientas de QGIS desde las que Esc vuelve al cursor
_VUELVEN = ("actionPan", "actionZoomIn", "actionZoomOut", "actionIdentify",
            "actionSelect", "actionSelectRectangle", "actionSelectPolygon",
            "actionSelectFreehand", "actionSelectRadius",
            "actionVertexTool", "actionVertexToolActiveLayer")


class EscReposo(Teclado):
    """Filtro de la aplicación: el Esc que no le llega a la línea de comandos
    ni a una herramienta de GeoCAD. El mapa con otra herramienta sólo lo
    entrega si Esc vuelve desde ella."""

    def __init__(self, QtCore, QtWidgets, ventana, linea, es_mapa, nuestra, vuelve,
                 entregar):
        super().__init__(QtCore, QtWidgets, ventana, linea, lambda: False,
                         lambda w: False, entregar)
        self.es_mapa = es_mapa
        self.nuestra = nuestra
        self.vuelve = vuelve

    def quiere(self, receptor, evento) -> bool:
        if nombre_tecla(self.QtCore, evento.key()) != _ESC:
            return False
        if con_modificadores(self.QtCore, evento.modifiers()):
            return False
        app = self.QtWidgets.QApplication
        foco = app.focusWidget()
        if foco is not None and receptor is not foco:
            return False
        if foco is None and receptor is not self.ventana():
            return False
        if app.activeModalWidget() is not None or app.activePopupWidget() is not None:
            return False
        if not self._en_ventana(receptor) or receptor is self.linea():
            return False
        if self.es_mapa(receptor):
            return not self.nuestra() and self.vuelve()
        return not protegido(receptor, self.QtCore)


class CursorDefecto:
    """iface, mgr (el de los comandos), cmdline y las herramientas de GeoCAD;
    capas() da las capas vectoriales del proyecto."""

    def __init__(self, iface, mgr, cmdline, herramientas, capas, QtCore, QtWidgets, QtGui=None):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.mgr = mgr
        self.cmdline = cmdline
        self.herramientas = herramientas
        self.capas = capas
        self.QtCore = QtCore
        self.QtGui = QtGui
        self.vivo = False
        self.esc = EscReposo(QtCore, QtWidgets, iface.mainWindow, lambda: cmdline.input,
                             lambda w: w is self.canvas or w is self.canvas.viewport(),
                             self.es_nuestra, self.vuelve, cmdline.feed_key)

    # ---------------------------------------------------------------- herramienta
    def es_nuestra(self) -> bool:
        tool = self.canvas.mapTool()
        return any(tool is x for x in self.herramientas)

    def vuelve(self) -> bool:
        """¿Es de las herramientas de QGIS desde las que Esc vuelve al cursor?"""
        tool = self.canvas.mapTool()
        if tool is None:
            return True
        accion = tool.action()
        if accion is None:
            return False
        for nombre in _VUELVEN:
            fn = getattr(self.iface, nombre, None)
            if fn is not None and fn() is accion:
                return True
        return False

    def activar(self) -> None:
        if not self.vivo or self.mgr.command is not None or self.es_nuestra():
            return
        self.mgr._switching = True
        try:
            self.canvas.setMapTool(self.mgr.tool)
        finally:
            self.mgr._switching = False

    def _luego(self, *_args) -> None:
        # QGIS pone Desplazar después de avisar del proyecto nuevo
        self.QtCore.QTimer.singleShot(0, self.activar)

    def _cambio(self, nueva, _vieja=None) -> None:
        if nueva is None:
            self._luego()

    # ---------------------------------------------------------------- Esc
    def esc_reposo(self) -> None:
        """Esc sin comando en marcha: mgr.cancel() lo deriva acá."""
        if self.canvas.isDrawing():
            self.canvas.stopRendering()       # lo que Esc hace en QGIS
        hubo = False
        for capa in self.capas():
            if capa.selectedFeatureCount():
                capa.removeSelection()
                hubo = True
        if hubo:
            self.cmdline.echo('*Cancelar*')
        if not self.es_nuestra() and self.vuelve():
            self._cancelar_herramienta()
            self.activar()

    def _cancelar_herramienta(self) -> None:
        """Esc primero a la herramienta: la de vértices, sacada a mitad de un arrastre, queda
        sin responder la próxima vez (medido en QGIS 4.2.2)."""
        tool = self.canvas.mapTool()
        if tool is None or self.QtGui is None:
            return
        T = getattr(self.QtCore.QEvent, "Type", self.QtCore.QEvent)
        Key = getattr(self.QtCore.Qt, "Key", self.QtCore.Qt)
        M = getattr(self.QtCore.Qt, "KeyboardModifier", self.QtCore.Qt)
        tool.keyPressEvent(self.QtGui.QKeyEvent(T.KeyPress, Key.Key_Escape, M.NoModifier))

    # ---------------------------------------------------------------- instalar
    def instalar(self) -> None:
        if self.vivo:
            return
        self.vivo = True
        self.mgr.esc_en_reposo = self.esc_reposo
        self.esc.instalar()
        self.canvas.mapToolSet.connect(self._cambio)
        self.iface.initializationCompleted.connect(self._luego)
        self.iface.newProjectCreated.connect(self._luego)
        self.iface.projectRead.connect(self._luego)
        self.activar()

    def quitar(self) -> None:
        """Apagado queda como venía: Esc de antes y, en vez del cursor, Desplazar."""
        if not self.vivo:
            return
        self.vivo = False
        self.mgr.esc_en_reposo = None
        self.esc.quitar()
        for senal, fn in ((self.canvas.mapToolSet, self._cambio),
                          (self.iface.initializationCompleted, self._luego),
                          (self.iface.newProjectCreated, self._luego),
                          (self.iface.projectRead, self._luego)):
            try:
                senal.disconnect(fn)
            except (TypeError, RuntimeError):
                pass
        if self.es_nuestra() and self.mgr.command is None:
            try:
                self.iface.actionPan().trigger()
            except (AttributeError, RuntimeError):
                pass
