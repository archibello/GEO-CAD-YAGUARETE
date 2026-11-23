"""Banco con el QGIS REAL (sin pantalla): UNIR (JOIN, J) en Dibujo (3.87.0).

Una capa de líneas con tabla (NOMBRE, LOTE). Con la orden de verdad:
* J, designar tres líneas que se tocan, Enter: queda UNA línea con los datos
  de la más larga; las otras dos se borran; un solo U de la capa vuelve atrás;
* CR (Criterio = Tramos): manda la de más tramos; el criterio se recuerda;
* con objetos ya seleccionados une al momento;
* las que no se tocan quedan como estaban; con una sola, avisa.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_unir_qgis.py'
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
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtWidgets import QApplication, QMainWindow

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

lyr = QgsVectorLayer("LineString?crs=EPSG:32721&field=NOMBRE:string&field=LOTE:integer", "lineas", "memory")
QgsProject.instance().addMapLayer(lyr)
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr])
mw.show()
canvas.setExtent(QgsRectangle(-10, -20, 40, 20))
canvas.refresh()
QApplication.processEvents()
lyr.startEditing()


def linea(nombre, lote, *pts):
    f = QgsFeature(lyr.fields())
    f.setAttributes([nombre, lote])
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in pts]))
    lyr.addFeature(f)
    return f.id()


def filas():
    return {f["NOMBRE"]: (f["LOTE"], f.geometry()) for f in lyr.getFeatures()}


def limpiar():
    for fid in [f.id() for f in lyr.getFeatures()]:
        lyr.deleteFeature(fid)


from geocad.dibujo.plugin import DibujoCADPlugin
from geocad.dibujo.settings import set_setting
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr
set_setting('join_criterio', 'longitud')


def clic(x, y):
    mgr.point_clicked(QgsPointXY(x, y), False, False)


def armar():
    limpiar()
    linea("larga", 1, (0, 0), (20, 0))                         # 20 m, 1 tramo
    linea("quebrada", 2, (20, 0), (20, 2), (22, 2), (22, 4), (24, 4))   # 8 m, 4 tramos
    linea("corta", 3, (-5, 0), (0, 0))                          # 5 m
    linea("lejos", 4, (30, -15), (35, -15))                    # no toca a nadie


# ---- 1. J por Longitud ----------------------------------------------------------------------
armar()
pila = lyr.undoStack().index()
mgr.run("J")
assert type(mgr.command).__name__ == "JoinCommand", mgr.command
clic(10, 0); clic(21, 2); clic(-2, 0); mgr.enter()
f = filas()
assert set(f) == {"larga", "lejos"}, f.keys()
g = f["larga"][1]
assert f["larga"][0] == 1 and abs(g.length() - 33) < 1e-6 and not g.isMultipart(), g.asWkt()
v = g.asPolyline()
assert (v[0].x(), v[-1].x()) in ((-5, 24), (24, -5)) and len(v) == 7, g.asWkt()
assert lyr.undoStack().index() == pila + 1, "un solo paso de deshacer"
lyr.undoStack().undo()
assert set(filas()) == {"larga", "quebrada", "corta", "lejos"}, "U vuelve atrás"
print("ok J: una línea con los datos de la más larga; un solo U")

# ---- 2. Criterio = Tramos, recordado -------------------------------------------------------
armar()
mgr.run("UNIR")
mgr.submit("CR")
assert mgr.command.criterio == "tramos"
clic(10, 0); clic(21, 2); clic(-2, 0); mgr.enter()
f = filas()
assert set(f) == {"quebrada", "lejos"} and f["quebrada"][0] == 2 and abs(f["quebrada"][1].length() - 33) < 1e-6
mgr.run("JOIN")
assert mgr.command.criterio == "tramos", "se recuerda"
mgr.submit("CR"); mgr.cancel()
print("ok CR: manda la de más tramos; se recuerda")

# ---- 3. con selección previa, y la que no se toca ---------------------------------------------
armar()
lyr.selectByIds([fe.id() for fe in lyr.getFeatures()])
mgr.run("J")
f = filas()
assert set(f) == {"larga", "lejos"} and mgr.command is None
assert abs(f["lejos"][1].length() - 5) < 1e-6, "la que no se toca queda como estaba"
print("ok con selección previa; la suelta queda igual")

# ---- 4. una sola, o ninguna que se toque ------------------------------------------------------
armar()
mgr.run("J"); clic(10, 0); mgr.enter()
assert len(filas()) == 4 and mgr.command is None
mgr.run("J"); clic(32, -15); clic(-2, 0); mgr.enter()
assert len(filas()) == 4 and mgr.command is None
print("ok una sola o sin extremos en común: no cambia nada")
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
