"""Banco con el QGIS REAL (sin pantalla): CHAFLÁN con Ochava en Dibujo
(3.57.0), el de IngeCAD en QGIS.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 -u banco_chaflan_qgis.py'
Termina en «TODO OK». Probado con 4.2.2 (al Flatpak 3.28.9 le falta el módulo mock).
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

lyr = QgsVectorLayer("LineString?crs=EPSG:32721&field=nombre:string", "lineas", "memory")
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


import json, math
R2 = math.sqrt(2.0)


def cerca(a, b, tol=1e-6):
    return abs(a - b) < tol


def vertices(g):
    return [(round(p.x(), 6), round(p.y(), 6)) for p in g.vertices()]


# ---- 1. sin largo guardado pide el largo; dos líneas: bisel A = B como objeto nuevo ------
limpiar()
h = QgsFeature(lyr.fields()); h["nombre"] = "calle"
h.setGeometry(QgsGeometry.fromPolylineXY([P(0, 0), P(10, 0)])); lyr.addFeature(h); h = h.id()
v = linea((10, 0), (10, 10))
mgr.run("CHA")
cmd = mgr.command
assert cmd is not None and cmd.state == "ochava", cmd and cmd.state
mgr.submit("5")
assert cmd.state == "first" and cmd.metodo == "O"
arch = os.path.join(os.environ["HOME"], ".config", "geocad", "chaflan.json")
assert json.load(open(arch))["ochava"] == 5.0, "compartido con IngeCAD"
clic(5, 0)
pv = cmd.preview_geoms(P(10, 5))              # vista previa: las dos recortadas y el bisel
assert pv and len(pv) == 3 and cerca(pv[2].length(), 5.0), pv
clic(10, 5)
c = round(10 - 5 / R2, 6)
g = geoms()
assert vertices(g[h]) == [(0, 0), (c, 0)], vertices(g[h])
assert vertices(g[v]) == [(10, round(5 / R2, 6)), (10, 10)], vertices(g[v])
nuevas = [fid for fid in g if fid not in (h, v)]
assert len(nuevas) == 1 and cerca(g[nuevas[0]].length(), 5.0)
assert lyr.getFeature(nuevas[0])["nombre"] == "calle", "atributos de la primera"
assert mgr.command is None, "sin Múltiple termina"
print("ok CHA pide el largo, bisel de 5 a 3,5355 de la esquina, objeto nuevo con atributos")

# ---- 2. con el largo guardado va directo; H deshace; Mayús = esquina ------------------------
limpiar()
a = linea((0, 0), (8, 0)); b = linea((10, 2), (10, 9))
mgr.run("CHAFLAN")
cmd = mgr.command
assert cmd.state == "first" and cmd.ochava == 5.0
mgr.submit("M")
clic(4, 0); clic(10, 6, shift=True)
g = geoms()
assert vertices(g[a])[-1] == (10, 0) and vertices(g[b])[0] == (10, 0) and len(g) == 2
mgr.submit("H")
g = geoms()
assert vertices(g[a]) == [(0, 0), (8, 0)] and vertices(g[b]) == [(10, 2), (10, 9)]
assert mgr.command is cmd, "Múltiple: sigue"
print("ok largo recordado, Mayús = esquina, H deshace, Múltiple")

# ---- 3. Distancia y No recortar --------------------------------------------------------------
mgr.submit("D"); mgr.submit("1"); mgr.submit("3")
assert cmd.metodo == "D" and cmd.dist1 == 1 and cmd.dist2 == 3
mgr.submit("R"); mgr.submit("N")
assert cmd.trim is False
clic(4, 0); clic(10, 6)
g = geoms()
assert vertices(g[a]) == [(0, 0), (8, 0)], "No recortar: quedan"
bis = [x for fid, x in g.items() if fid not in (a, b)]
assert len(bis) == 1 and vertices(bis[0]) == [(9, 0), (10, 3)], vertices(bis[0])
mgr.submit("R"); mgr.submit("R"); mgr.submit("E"); mgr.submit("O")
assert cmd.trim is True and cmd.metodo == "O"
mgr.enter()
assert mgr.command is None
print("ok Distancia (d1 en la primera), No recortar, mEtodo")

# ---- 3b. polilínea + línea: unidas en una (la otra se borra), como IngeCAD; multiparte ------
limpiar()
pl = QgsFeature(lyr.fields()); pl["nombre"] = "alambrado"
pl.setGeometry(QgsGeometry.fromPolylineXY([P(0, 5), P(0, 0), P(10, 0)])); lyr.addFeature(pl); pl = pl.id()
ln = linea((10, 0), (10, 10))
mgr.run("CHA")
cmd = mgr.command
mgr.submit("M")
clic(10, 5); clic(5, 0)                       # primero la línea: la base es la polilínea
g = geoms()
assert list(g) == [pl], "la línea se unió a la polilínea"
c = round(5 / R2, 6)
assert vertices(g[pl]) == [(10, 10), (10, c), (round(10 - 5 / R2, 6), 0), (0, 0), (0, 5)], vertices(g[pl])  # desde la primera tocada, como IngeCAD
assert lyr.getFeature(pl)["nombre"] == "alambrado"
mgr.submit("H")
assert sorted(geoms()) == sorted([pl, ln]), "H recupera la línea"
mgr.enter()
assert mgr.command is None
# tramo del medio de una polilínea: el aviso de IngeCAD y no cambia nada
limpiar()
mid = linea((0, 0), (5, 0), (8, 0), (8, -5)); cruz = linea((7, -9), (7, 9))
mgr.run("CHA"); clic(6.5, 0); clic(7, 5)
assert vertices(geoms()[mid]) == [(0, 0), (5, 0), (8, 0), (8, -5)]
# dos partes de una línea multiparte
limpiar()
f = QgsFeature(lyr.fields())
f.setGeometry(QgsGeometry.fromMultiPolylineXY([[P(0, 0), P(10, 0)], [P(10, 0), P(10, 10)]]))
lyr.addFeature(f); mp = f.id()
mgr.run("CHA"); clic(5, 0); clic(10, 5)
g = geoms()
assert len(g) == 2 and g[mp].isMultipart() and cerca(g[mp].length(), 20 - 2 * 5 / R2)
print("ok polilínea + línea unidas en una, tramo del medio no, multiparte")

# ---- 4. polígono: la ochava de la esquina de una parcela, y Polilínea ---------------------
pol = QgsVectorLayer("Polygon?crs=EPSG:32721", "parcelas", "memory")
QgsProject.instance().addMapLayer(pol)
canvas.setLayers([pol, lyr])
iface.activeLayer.return_value = pol
pol.startEditing()
f = QgsFeature(pol.fields())
f.setGeometry(QgsGeometry.fromPolygonXY([[P(0, 0), P(10, 0), P(10, 8), P(0, 8), P(0, 0)]]))
pol.addFeature(f)
fid = f.id()
area0 = pol.getFeature(fid).geometry().area()
mgr.run("CHA")
cmd = mgr.command
assert cmd.layer is pol
clic(5, 0); clic(10, 4)
g = pol.getFeature(fid).geometry()
assert cerca(area0 - g.area(), 25 / 4.0), g.area()            # triángulo de catetos 5/√2
assert len(list(pol.getFeatures())) == 1, "en el mismo objeto"
f = QgsFeature(pol.fields())
f.setGeometry(QgsGeometry.fromPolygonXY([[P(20, 0), P(30, 0), P(30, 8), P(20, 8), P(20, 0)]]))
pol.addFeature(f)
mgr.run("CHA")
mgr.submit("P")
clic(20, 4)
g = pol.getFeature(f.id()).geometry()
assert cerca(area0 - g.area(), 4 * 25 / 4.0), g.area()       # las cuatro esquinas
assert len(vertices(g)) == 9
# dos polígonos distintos: no (como las cerradas en IngeCAD)
f2 = QgsFeature(pol.fields())
f2.setGeometry(QgsGeometry.fromPolygonXY([[P(0, 20), P(10, 20), P(10, 28), P(0, 28), P(0, 20)]]))
pol.addFeature(f2)
antes = pol.getFeature(f2.id()).geometry().asWkt()
mgr.run("CHA"); clic(5, 20); clic(20, 4)
assert pol.getFeature(f2.id()).geometry().asWkt() == antes
print("ok ochava en la esquina de un polígono y opción Polilínea; dos polígonos no")
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
