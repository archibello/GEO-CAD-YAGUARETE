"""Banco con el QGIS REAL (sin pantalla): COPIABASE / PEGARENPUNTO (CAD
Copiar/Mover de Fernando) y ALINEAR con Copia (Alinear y Duplicar), 3.44.0.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_copiabase_qgis.py'
Termina en «TODO OK».
"""
import os, sys, tempfile, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas, QgsMapToolPan
from qgis.PyQt.QtCore import QEvent, Qt
from qgis.PyQt.QtGui import QKeyEvent
from qgis.PyQt.QtWidgets import QApplication, QMainWindow

# ---- un QGIS de prueba: ventana, mapa y una capa de líneas en edición -------------------
iface = get_iface()
mw = QMainWindow()
canvas = QgsMapCanvas(mw)
mw.setCentralWidget(canvas)
mw.resize(1000, 800)
iface.mainWindow.return_value = mw
iface.mapCanvas.return_value = canvas
iface.cadDockWidget.return_value = QgsAdvancedDigitizingDockWidget(canvas)
iface.addToolBar.side_effect = lambda nombre: mw.addToolBar(nombre)
iface.addDockWidget.side_effect = lambda area, dock: mw.addDockWidget(area, dock)

lyr = QgsVectorLayer("LineString?crs=EPSG:32721", "lineas", "memory")
QgsProject.instance().addMapLayer(lyr)
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr])
mw.show()
canvas.setExtent(QgsRectangle(-10, -10, 15, 10))
canvas.refresh()
QApplication.processEvents()
lyr.startEditing()


def linea(*pts):
    f = QgsFeature(lyr.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in pts]))
    lyr.addFeature(f)
    return f.id()


def geoms():
    return {f.id(): f.geometry() for f in lyr.getFeatures()}


def limpiar():
    for fid in [f.id() for f in lyr.getFeatures()]:
        lyr.deleteFeature(fid)


def P(x, y):
    return QgsPointXY(x, y)


from geocad.dibujo.plugin import DibujoCADPlugin
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr


def clic(x, y, shift=False):
    mgr.point_clicked(P(x, y), False, shift)


from qgis.core import QgsField
try:
    from qgis.PyQt.QtCore import QMetaType
    _TXT = QMetaType.Type.QString
except Exception:  # noqa: BLE001
    from qgis.PyQt.QtCore import QVariant
    _TXT = QVariant.String


def bb(g):
    r = g.boundingBox()
    return (round(r.xMinimum(), 6), round(r.yMinimum(), 6), round(r.xMaximum(), 6), round(r.yMaximum(), 6))


# ---- 1. COPIABASE y PEGARENPUNTO (varias veces), datos por nombre de campo ------------------
lyr.dataProvider().addAttributes([QgsField("nombre", _TXT)])
lyr.updateFields()
limpiar()
a = linea((0, 0), (2, 0))
lyr.changeAttributeValue(a, lyr.fields().indexOf("nombre"), "eje")
mgr.run("COPIABASE")
clic(1, 0)                                  # designa
mgr.enter()
clic(0, 0)                                  # punto base
assert mgr.command is None
mgr.run("PB")
pv = mgr.command.preview_geoms(P(10, 10))
assert pv and bb(pv[0]) == (10, 10, 12, 10), "vista previa en el punto de inserción"
clic(10, 10)
clic(20, 0)
assert mgr.command is not None, "copia múltiple: sigue pidiendo puntos"
mgr.submit("H")
clic(5, 5)
mgr.enter()
cajas = sorted(bb(g) for g in geoms().values())
assert cajas == [(0, 0, 2, 0), (5, 5, 7, 5), (10, 10, 12, 10)], cajas
nombres = sorted(f["nombre"] for f in lyr.getFeatures())
assert nombres == ["eje", "eje", "eje"], nombres
print("ok COPIABASE / PEGARENPUNTO: punto base, vista previa, varias copias, desHacer, datos")

# pegar en otra capa (otro SRC de capa) con el campo por nombre
otra = QgsVectorLayer("LineString?crs=EPSG:32721&field=id:integer&field=nombre:string", "otra", "memory")
QgsProject.instance().addMapLayer(otra)
canvas.setLayers([lyr, otra])
otra.startEditing()
iface.activeLayer.return_value = otra
mgr.run("PEGARENPUNTO")
clic(0, -5)
mgr.enter()
f = next(otra.getFeatures())
assert bb(f.geometry()) == (0, -5, 2, -5) and f["nombre"] == "eje", (bb(f.geometry()), f["nombre"])
iface.activeLayer.return_value = lyr
canvas.setLayers([lyr])
print("ok PEGARENPUNTO en otra capa: datos por nombre de campo")

# ---- 2. ALINEAR con Copia y ALINEARCOPIA -------------------------------------------------
limpiar()
a = linea((0, 0), (2, 0))
mgr.run("ALINEAR")
clic(1, 0)
mgr.enter()
mgr.submit("C")                              # Copia = Sí
assert mgr.command.copia
clic(0, 0); clic(10, 10)                     # origen 1 -> destino 1
clic(2, 0); clic(10, 14)                     # origen 2 -> destino 2 (gira 90 y escala x2)
mgr.submit("S")
cajas = sorted(bb(g) for g in geoms().values())
assert cajas == [(0, 0, 2, 0), (10, 10, 10, 14)], cajas
print("ok ALINEAR con Copia: el original queda, la copia alineada y escalada")
limpiar()
a = linea((0, 0), (2, 0))
mgr.run("ALC")
clic(1, 0)
mgr.enter()
assert mgr.command.copia
clic(0, 0); clic(5, 0)
mgr.enter()                                  # un solo par: desplaza
cajas = sorted(bb(g) for g in geoms().values())
assert cajas == [(0, 0, 2, 0), (5, 0, 7, 0)], cajas
print("ok ALINEARCOPIA (Alinear y Duplicar): siempre copia")
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
