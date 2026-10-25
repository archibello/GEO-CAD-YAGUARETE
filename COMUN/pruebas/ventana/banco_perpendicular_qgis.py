"""Banco con el QGIS REAL (sin pantalla): PERPENDICULAR, la Tool
Perpendicular de Fernando dentro de Dibujo (3.42.0).

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_perpendicular_qgis.py'
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


limpiar()
ref = linea((0, 0), (10, 0))
diag = linea((0, 5), (4, 9))
mgr.run("PERPENDICULAR")
cmd = mgr.command
assert cmd is not None and cmd.p0 is None
clic(3, 5)                                   # origen
assert cmd.p0 is not None
pv = cmd.preview_geoms(P(6, 0))              # vista previa hasta la línea
assert pv and abs(pv[0].length() - 5) < 1e-6, pv
pv = cmd.preview_geoms(P(1, 6))              # hacia la diagonal (prolongada)
assert pv and pv[0].length() > 0
clic(6, 0)
nuevas = [g for fid, g in geoms().items() if fid not in (ref, diag)]
assert len(nuevas) == 1, nuevas
bb = nuevas[0].boundingBox()
assert abs(bb.xMinimum() - 3) < 1e-6 and abs(bb.xMaximum() - 3) < 1e-6 and \
    abs(bb.yMinimum()) < 1e-6 and abs(bb.yMaximum() - 5) < 1e-6, nuevas[0].asWkt()
assert cmd.p0 is None and mgr.command is cmd, "queda lista para la siguiente"
print("ok PERPENDICULAR: origen, vista previa, línea perpendicular")

# a la prolongación: el origen cae fuera del tramo
clic(15, 4)
clic(9, 0)
n = [g for fid, g in geoms().items() if fid not in (ref, diag)]
assert len(n) == 2
ult = max(n, key=lambda g: g.boundingBox().xMaximum())
assert abs(ult.boundingBox().xMinimum() - 15) < 1e-6 and abs(ult.boundingBox().yMinimum()) < 1e-6, ult.asWkt()
print("ok PERPENDICULAR a la prolongación de la línea")

# Intro con origen lo suelta; H deshace; Intro sin origen sale; Esc sale
clic(1, 1)
mgr.enter()
assert mgr.command is cmd and cmd.p0 is None, "Intro con origen: lo suelta y sigue"
mgr.submit("H")
assert len([1 for fid in geoms() if fid not in (ref, diag)]) == 1
mgr.enter()
assert mgr.command is None
mgr.run("PERP")
clic(1, 1)
mgr.cancel()
assert mgr.command is None
print("ok Intro suelta el origen, H deshace, Intro / Esc salen")
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
