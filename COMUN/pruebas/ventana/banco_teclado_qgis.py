"""Banco con el QGIS REAL (sin pantalla): el teclado siempre a la línea de
comandos de Dibujo (módulo «Teclado», 3.59).

Con el foco en el panel de capas o en el mapa con la herramienta Desplazar
de QGIS (sin hacer clic en la línea de comandos): lo escrito llega a la
línea; Intro con algo escrito arranca la orden y Esc la cancela. Espacio
con la línea vacía sigue siendo de QGIS. La tabla de atributos, la consola
de Python, un campo de texto y un diálogo se quedan con lo suyo; con la
Digitalización avanzada prendida, las letras sobre el mapa son de QGIS.
Botón derecho (módulo «Botón derecho = Enter»): con Desplazar repite el
último comando, durante un comando es Intro, acepta lo escrito; Ctrl y las
herramientas de edición de QGIS conservan el suyo. Módulos apagados: como venía.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 -u banco_teclado_qgis.py'
Termina en «TODO OK».
"""
import os, sys, tempfile, time, faulthandler
faulthandler.enable()
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")

from unittest import mock
from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import QgsProject, QgsRectangle, QgsVectorLayer, QgsLayerTreeModel
from qgis.gui import (QgsAdvancedDigitizingDockWidget, QgsMapCanvas, QgsMapToolPan,
                      QgsLayerTreeView, QgsAttributeTableView, QgsCodeEditorPython)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QApplication, QMainWindow, QDockWidget, QLineEdit, QDialog,
                                 QPushButton, QVBoxLayout)
from qgis.PyQt.QtTest import QTest

# ---- un QGIS de prueba: ventana, mapa, panel de capas y una capa de líneas en edición ----
iface = get_iface()
mw = QMainWindow()
canvas = QgsMapCanvas(mw)
mw.setCentralWidget(canvas)
mw.resize(1000, 800)
cad = QgsAdvancedDigitizingDockWidget(canvas)
iface.mainWindow.return_value = mw
iface.mapCanvas.return_value = canvas
iface.cadDockWidget.return_value = cad
iface.addToolBar.side_effect = lambda nombre: mw.addToolBar(nombre)
iface.addDockWidget.side_effect = lambda area, dock: mw.addDockWidget(area, dock)
iface.removeDockWidget.side_effect = lambda dock: mw.removeDockWidget(dock)

lyr = QgsVectorLayer("LineString?crs=EPSG:32721", "lineas", "memory")
QgsProject.instance().addMapLayer(lyr)
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr])


def en_dock(titulo, w):
    d = QDockWidget(titulo, mw)
    d.setWidget(w)
    mw.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, d)
    return w


arbol = en_dock("Capas", QgsLayerTreeView())
modelo_capas = QgsLayerTreeModel(QgsProject.instance().layerTreeRoot())
arbol.setModel(modelo_capas)
tabla = en_dock("Tabla de atributos", QgsAttributeTableView())
consola = en_dock("Consola de Python", QgsCodeEditorPython())
campo = en_dock("Campo", QLineEdit())
mw.show()
mw.activateWindow()
canvas.setExtent(QgsRectangle(-10, -10, 15, 10))
canvas.refresh()
QApplication.processEvents()
lyr.startEditing()
pan = QgsMapToolPan(canvas)
canvas.setMapTool(pan)

fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}", flush=True)
    if not ok:
        fallas.append(nombre)


def esperar(s=0.05):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        time.sleep(0.01)


def enfocar(w):
    w.setFocus(Qt.FocusReason.OtherFocusReason)
    esperar()
    return QApplication.focusWidget() is w


def teclear(texto):
    """Como el teclado de verdad: cada tecla al widget que tiene el foco."""
    for ch in texto:
        QTest.keyClicks(QApplication.focusWidget() or mw, ch)
        app.processEvents()


def tecla(w, key, mods=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(w, key, mods)
    esperar()


from geocad.dibujo.plugin import DibujoCADPlugin
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr
entrada = plugin.cmdline.input
plugin.cmdline.show()
esperar()
ver("filtro instalado (módulo prendido por defecto)", plugin.teclado is not None)

# 1) desde el panel de capas
entrada.clear()
ver("foco en el panel de capas", enfocar(arbol))
teclear("linea")
ver("lo escrito en el panel de capas llega a la línea", entrada.text().lower() == "linea",
    repr(entrada.text()))
ver("el foco pasa a la línea de comandos", QApplication.focusWidget() is entrada)
enfocar(arbol)
tecla(arbol, Qt.Key.Key_Return)
ver("Intro desde el panel arranca LINEA", mgr.command is not None and entrada.text() == "")
enfocar(arbol)
tecla(arbol, Qt.Key.Key_Escape)
ver("Esc desde el panel cancela la orden", mgr.command is None)
canvas.setMapTool(pan)
esperar()

# 2) el mapa con la herramienta Desplazar de QGIS
entrada.clear()
enfocar(canvas)
teclear("circ")
ver("con Desplazar de QGIS: las letras van a la línea", entrada.text().lower() == "circ",
    repr(entrada.text()))
entrada.clear()
enfocar(canvas)
tecla(canvas, Qt.Key.Key_Space)
ver("Espacio con la línea vacía sigue siendo de QGIS", entrada.text() == "" and mgr.command is None)

# 3) con la Digitalización avanzada prendida, las letras sobre el mapa son de QGIS
with mock.patch.object(cad, "cadEnabled", return_value=True):
    iface.cadDockWidget.return_value = cad
    enfocar(canvas)
    teclear("d")
    ver("Digitalización avanzada: la letra queda para QGIS", entrada.text() == "",
        repr(entrada.text()))

# 4) donde se escribe, no se toca
for nombre, w in (("tabla de atributos", tabla), ("consola de Python", consola),
                  ("campo de texto", campo)):
    entrada.clear()
    enfocar(w)
    teclear("x1")
    ver(f"{nombre}: no va a la línea", entrada.text() == "", repr(entrada.text()))
ver("el campo de texto escribe en él", campo.text() == "x1", repr(campo.text()))

# 5) un diálogo
dlg = QDialog(mw)
boton = QPushButton("b", dlg)
QVBoxLayout(dlg).addWidget(boton)
dlg.show(); dlg.activateWindow(); esperar()
enfocar(boton)
teclear("abc")
ver("diálogo: no va a la línea", entrada.text() == "", repr(entrada.text()))
dlg.close(); mw.activateWindow(); esperar()

# 6) Ctrl + tecla
enfocar(arbol)
tecla(arbol, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
ver("Ctrl+L no va a la línea", entrada.text() == "", repr(entrada.text()))

# 7) botón derecho = Intro / último comando, también con Desplazar de QGIS
from qgis.gui import QgsMapTool


def derecho(mods=Qt.KeyboardModifier.NoModifier):
    vp = canvas.viewport()
    QTest.mouseClick(vp, Qt.MouseButton.RightButton, mods, vp.rect().center())
    esperar()


class Edicion(QgsMapTool):          # como Agregar entidad o Vértices
    def __init__(self, c):
        super().__init__(c)
        try:
            self.setFlags(QgsMapTool.Flag.EditTool)
        except AttributeError:
            pass

    def isEditTool(self):           # QGIS 3
        return True


ver("clic derecho instalado (módulo prendido por defecto)", plugin.clic_derecho is not None)
mgr.cancel(); canvas.setMapTool(pan); esperar()
enfocar(arbol)                       # el foco afuera de la línea y del mapa
derecho()
ver("con Desplazar: clic derecho repite el último (LINEA)", mgr.command is not None,
    repr(mgr.last_cmd))
derecho()
ver("durante el comando: clic derecho = Intro (termina)", mgr.command is None)
canvas.setMapTool(pan); esperar()
entrada.setText("linea")
enfocar(campo)
derecho()
ver("con algo escrito: clic derecho lo acepta", mgr.command is not None and entrada.text() == "")
mgr.cancel(); canvas.setMapTool(pan); esperar()
# (el menú de QGIS bloquearía sin pantalla: se pregunta al filtro con el evento)
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtCore import QEvent, QPointF
vp = canvas.viewport()
c = QPointF(vp.rect().center())
ctrl = QMouseEvent(QEvent.Type.MouseButtonPress, c, vp.mapToGlobal(c), Qt.MouseButton.RightButton,
                   Qt.MouseButton.RightButton, Qt.KeyboardModifier.ControlModifier)
ver("Ctrl + clic derecho: queda para QGIS",
    plugin.clic_derecho.eventFilter(vp, ctrl) is False and mgr.command is None)
edicion = Edicion(canvas)
canvas.setMapTool(edicion); esperar()
derecho()
ver("herramienta de edición de QGIS: conserva su clic derecho",
    mgr.command is None and canvas.mapTool() is edicion)
canvas.setMapTool(pan); esperar()

# 8) módulos apagados: Dibujo se rearma sin el filtro (como hace GeoCAD > Módulos)
from geocad import modulos
plugin.unload()
modulos.guardar("qgis", {"teclado": False, "boton_derecho": False})
plugin = DibujoCADPlugin(iface)
plugin.initGui()
entrada = plugin.cmdline.input
plugin.cmdline.show()
esperar()
ver("módulo apagado: sin filtro", plugin.teclado is None)
enfocar(arbol)
teclear("linea")
ver("módulo apagado: el panel no manda a la línea", entrada.text() == "", repr(entrada.text()))
ver("botón derecho apagado: sin filtro", plugin.clic_derecho is None)
# (apagado, el clic derecho con Desplazar abre el menú de QGIS: sin pantalla bloquearía)
plugin.unload()

if fallas:
    print("FALLAS:", fallas, flush=True)
    faulthandler.cancel_dump_traceback_later()
    os._exit(1)
print("TODO OK", flush=True)
faulthandler.cancel_dump_traceback_later()
os._exit(0)
