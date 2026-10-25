"""Banco con el QGIS REAL (sin pantalla): RUMBOS, los Digitalizadores GMS de
Fernando dentro de Dibujo (3.43.0).

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_rumbos_qgis.py'
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


def vertices(g):
    return [(round(v.x(), 6), round(v.y(), 6)) for v in g.vertices()]


# ---- 1. Polilínea, Ángulo Interior, sin base -------------------------------------------
limpiar()
mgr.run("RUMBOS")
cmd = mgr.command
assert cmd is not None and cmd.angulo == "interior" and not cmd.tramos and not cmd.con_base
clic(0, 0)
clic(10, 0)
path, _c, temp, guide = cmd.preview(P(12, 5))
assert len(guide) == 2, "la base se ve como guía"
mgr.submit("10<90")                       # 180 + 90: hacia abajo
mgr.submit("5<180")                       # sigue derecho
assert lyr.featureCount() == 0, "la polilínea se escribe al terminar"
mgr.enter()
assert mgr.command is None and lyr.featureCount() == 1
g = list(geoms().values())[0]
assert vertices(g) == [(10, 0), (10, -10), (10, -15)], vertices(g)
print("ok RUMBOS polilínea, ángulo interior (180 = sigue derecho), base sin dibujar")

# ---- 2. Tramos sueltos con la base, desHacer --------------------------------------------
limpiar()
mgr.run("RB")
clic(0, 0)
clic(10, 0)
mgr.submit("M")
mgr.submit("B")
cmd = mgr.command
assert cmd.tramos and cmd.con_base
mgr.submit("10<90")
assert lyr.featureCount() == 2, "la base y el primer tramo, cada uno un objeto"
mgr.submit("10<90")
assert lyr.featureCount() == 3
mgr.submit("H")
assert lyr.featureCount() == 2
mgr.enter()
assert mgr.command is None
segs = sorted(vertices(g) for g in geoms().values())
assert segs == [[(0, 0), (10, 0)], [(10, 0), (10, -10)]], segs
mgr.run("RB")                              # Modo y Base se recuerdan: se vuelven a dejar
assert mgr.command.tramos and mgr.command.con_base
clic(0, 0)
clic(10, 0)
mgr.submit("M")
mgr.submit("B")
mgr.cancel()
print("ok RUMBOS tramos sueltos, base dibujada, desHacer, se recuerda")

# ---- 3. Deflexión (0 = sigue derecho, + izquierda) --------------------------------------
limpiar()
mgr.run("GMS")
clic(0, 0)
clic(10, 0)
mgr.submit("A")
assert mgr.command.angulo == "deflexion"
mgr.submit("10<0")
mgr.submit("10<90")
mgr.submit("5<30dD")                       # deflexión explícita, en cualquier modo
mgr.enter()
g = list(geoms().values())[0]
v = vertices(g)
assert v[:3] == [(10, 0), (20, 0), (20, 10)], v
assert abs(v[3][0] - (20 + 5 * 0.5)) < 1e-6 and abs(v[3][1] - (10 + 5 * 3 ** 0.5 / 2)) < 1e-6, v
mgr.run("GMS")
assert mgr.command.angulo == "deflexion"
clic(0, 0)
clic(10, 0)
mgr.submit("A")
mgr.cancel()
print("ok RUMBOS deflexión y 30dD")

# ---- 4. capa de polígonos: un polígono, Cerrar ------------------------------------------
pol = QgsVectorLayer("Polygon?crs=EPSG:32721", "poligonos", "memory")
QgsProject.instance().addMapLayer(pol)
canvas.setLayers([lyr, pol])
iface.activeLayer.return_value = pol
pol.startEditing()
mgr.run("RUMBOS")
clic(0, 0)
clic(10, 0)
mgr.submit("M")
assert not mgr.command.tramos, "en polígonos no hay tramos sueltos"
mgr.submit("10<90")
mgr.submit("10<90")
mgr.submit("C")
assert mgr.command is None and pol.featureCount() == 1
gp = next(pol.getFeatures()).geometry()
assert abs(gp.area() - 50.0) < 1e-6, gp.asWkt()
print("ok RUMBOS en capa de polígonos: un polígono cerrado")
iface.activeLayer.return_value = lyr
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
