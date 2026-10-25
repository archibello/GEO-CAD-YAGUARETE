"""Banco con el QGIS REAL (sin pantalla): EMPALME y EQDIST con el
comportamiento del Fillet y del Offset de Fernando (3.41.0).

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_empalme_eqdist_qgis.py'
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


def n():
    return lyr.featureCount()


# ---- 1. EMPALME: resalta, muestra el resultado antes del segundo clic, lado del clic ----
limpiar()
a = linea((-5, 0), (5, 0))
b = linea((0, -5), (0, 5))
mgr.run("EMPALME")
cmd = mgr.command
assert cmd.radius == 0.0
pv = cmd.preview_geoms(P(3, 0))                      # la línea bajo el cursor
assert pv and abs(pv[0].length() - 10.0) < 1e-6
clic(3, 0)
assert lyr.selectedFeatureIds() == [a]
pv = cmd.preview_geoms(P(0, 3))                      # cómo quedan las dos
assert pv and len(pv) == 2 and all(abs(g.length() - 5.0) < 1e-6 for g in pv), [g.asWkt() for g in pv]
clic(0, 3)
ga, gb = geoms()[a].boundingBox(), geoms()[b].boundingBox()
assert abs(ga.xMinimum()) < 1e-6 and abs(ga.xMaximum() - 5) < 1e-6, geoms()[a].asWkt()
assert abs(gb.yMinimum()) < 1e-6 and abs(gb.yMaximum() - 5) < 1e-6, geoms()[b].asWkt()
assert mgr.command is None
print("ok EMPALME: resalta, vista previa de las dos, queda el lado del clic")

# líneas que no se tocan: se alargan hasta la esquina
limpiar()
a = linea((-5, 0), (-1, 0))
b = linea((2, 1), (2, 5))
mgr.run("F")
clic(-3, 0)
clic(2, 3)
assert abs(geoms()[a].boundingBox().xMaximum() - 2) < 1e-6 and abs(geoms()[b].boundingBox().yMinimum()) < 1e-6
print("ok EMPALME: alarga hasta la esquina")

# radio (lo de Dibujo que se conserva): la vista previa trae el arco y se agrega
limpiar()
a = linea((-5, 0), (5, 0))
b = linea((0, -5), (0, 5))
mgr.run("EMPALME")
mgr.submit("R")
mgr.submit("1")
clic(3, 0)
pv = mgr.command.preview_geoms(P(0, 3))
assert pv and len(pv) == 3, "con radio: las dos líneas y el arco"
clic(0, 3)
assert n() == 3 and abs(geoms()[a].boundingBox().xMinimum() - 1) < 1e-6
mgr.run("EMPALME")
assert mgr.command.radius == 1.0, "el radio se recuerda"
mgr.submit("R")
mgr.submit("0")
mgr.cancel()
print("ok EMPALME con radio: arco en la vista previa y en la capa")

# ---- 2. EQDIST: varias copias, clic derecho = otra distancia sin salir --------------------
limpiar()
base = linea((0, 0), (10, 0))
mgr.run("EQDIST")
mgr.submit("2")
cmd = mgr.command
assert cmd.state == "pick"
pv = cmd.preview_geoms(P(5, 0))
assert pv and abs(pv[0].length() - 10) < 1e-6, "resalta la línea bajo el cursor"
clic(5, 0)
pv = cmd.preview_geoms(P(5, 1))
assert pv and abs(pv[0].boundingBox().yMinimum() - 2) < 1e-6, "la copia antes del clic"
clic(5, 1)
assert n() == 2 and cmd.state == "pick" and mgr.command is cmd, "sigue activo"
mgr.enter()                                         # clic derecho / Intro
assert mgr.command is cmd and cmd.state == "dist", "pide otra distancia sin salir"
mgr.submit("3")
clic(5, 0)
clic(5, -1)
ys = sorted(round(g.boundingBox().yMinimum(), 6) for g in geoms().values())
assert ys == [-3.0, 0.0, 2.0], ys
mgr.submit("D")
assert cmd.state == "dist"
mgr.enter()                                         # Intro: se queda con la distancia
assert cmd.state == "pick" and abs(cmd.dist - 3) < 1e-9
mgr.submit("H")
assert n() == 2
mgr.submit("S")
assert mgr.command is None
print("ok EQDIST: varias copias, vista previa, clic derecho = otra distancia, S sale")

plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
