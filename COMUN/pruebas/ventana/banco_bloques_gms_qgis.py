"""Banco con el QGIS REAL (sin pantalla): Bloques GMS de Fernando dentro de
Bloques (3.45.0): BLOQUE con P2, INSERTAR con P2 y las dos simetrías como copias en las
mismas capas (sin la capa «Bloques CAD»), BLOQUESGMS (sus .json).

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_bloques_gms_qgis.py'
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


import json, math
from geocad.dibujo import block_commands as BC, blocks as B
from geocad.dibujo.compat import accepted_code
from geocad.dibujo.geomops import gms_insercion
BC.exec_dialog = lambda dlg: accepted_code()          # el diálogo de INSERTAR, aceptado tal cual


def puntos(g):
    return sorted((round(v.x(), 6), round(v.y(), 6)) for v in g.vertices())


_vistas = set()


def nuevas():
    """Las líneas que dejó la última inserción (en la misma capa)."""
    fs = [f for f in lyr.getFeatures() if f.id() not in _vistas]
    _vistas.update(f.id() for f in fs)
    return fs


def sin_capa_bloques():
    return B.instance_layer(iface, mgr.cmdline.echo, create=False) is None


# ---- 1. BLOQUE con P2 -------------------------------------------------------------------
limpiar()
linea((0, 0), (3, 0))
linea((3, 0), (3, 1))
mgr.run("BLOQUE")
mgr.submit("puerta")
clic(0, 0)                                   # punto base P1
assert mgr.command.state == "ref"
clic(3, 0)                                   # P2
clic(1.5, 0)
clic(3, 0.5)
mgr.enter()
mgr.enter()                                  # Retener (por defecto)
assert mgr.command is None
assert B.LIB.reference("puerta") == (3.0, 0.0) and len(B.LIB.rows("puerta")) == 2
print("ok BLOQUE con punto de referencia P2 (no se dibuja ni se descompone)")

# sin P2: Intro; al insertar se usa el ancho del bloque
mgr.run("BLOQUE")
mgr.submit("sinref")
clic(0, 0)
mgr.enter()
clic(1.5, 0)
mgr.enter()
mgr.submit("C")                              # Convertir ya no crea una inserción: retiene
assert B.LIB.reference("sinref") == (3.0, 0.0) and sin_capa_bloques()
print("ok BLOQUE sin P2: la referencia es el ancho del bloque")

# ---- 2. INSERTAR con P1, P2 y las dos simetrías: copias en la misma capa ----------------
_vistas.update(f.id() for f in lyr.getFeatures())


def esperado(colocacion):
    (x, y), sx, sy, rot = colocacion
    c, s_ = math.cos(rot), math.sin(rot)
    out = set()
    for seg in ([(0, 0), (3, 0)], [(3, 0), (3, 1)]):
        out.add(tuple(sorted((round(sx * c * a - sy * s_ * b + x, 6), round(sx * s_ * a + sy * c * b + y, 6))
                             for a, b in seg)))
    return out


def obtenido(fs):
    return {tuple(sorted(puntos(f.geometry()))) for f in fs}


mgr.run("INSERT")
cmd = mgr.command
assert cmd.name == "puerta" and cmd.state == "pt"
clic(10, 5)
assert cmd.state == "p2"
assert cmd.preview_geoms(P(16, 13)), "vista previa con P2"
clic(16, 13)
assert cmd.state == "sim"
clic(0, 0)                                   # clic: simetría perpendicular
assert cmd.perp and not cmd.horiz
mgr.enter()                                  # siguiente: horizonte
mgr.submit("H")
assert cmd.horiz
mgr.enter()                                  # insertar
assert mgr.command is None
fs = nuevas()
assert len(fs) == 2 and obtenido(fs) == esperado(gms_insercion((10, 5), (16, 13), (3, 0), True, True)), obtenido(fs)
assert sin_capa_bloques(), "no se crea la capa Bloques CAD"
print("ok INSERTAR: P1, P2, las dos simetrías; copias en la misma capa, sin capas nuevas")

mgr.run("I")
clic(0, 20); clic(0, 26)
mgr.submit("S")
mgr.submit("A")
fs = nuevas()
assert obtenido(fs) == esperado(gms_insercion((0, 20), (0, 26), (3, 0), True, False)), obtenido(fs)
print("ok INSERTAR: S y Aceptar escritos")

mgr.run("I")
clic(-20, -20)
mgr.enter()
fs = nuevas()
assert obtenido(fs) == esperado(((-20, -20), 1.0, 1.0, 0.0)), obtenido(fs)
assert sin_capa_bloques()
print("ok INSERTAR sin P2: escala y giro de la ventana")

# ---- 3. BLOQUESGMS: los .json de Bloques GMS ----------------------------------------------
carpeta = tempfile.mkdtemp()
dat = {"format": 2, "name": "ventana", "project_crs": "EPSG:32721", "p1": [0, 0], "p2": [1.2, 0],
       "base_length": 1.2, "source_layer_name": "muros",
       "geometries_wkt": ["LineString (0 0, 1.2 0)", "LineString (0 0.1, 1.2 0.1)"]}
open(os.path.join(carpeta, "ventana.json"), "w").write(json.dumps(dat))
otro = dict(dat, name="lejos", project_crs="EPSG:4326")
open(os.path.join(carpeta, "lejos.json"), "w").write(json.dumps(otro))
pisa = dict(dat, name="puerta")
open(os.path.join(carpeta, "puerta.json"), "w").write(json.dumps(pisa))
n = BC.importar_gms(mgr, carpeta)
assert n == 1 and "ventana" in B.LIB.names() and "lejos" not in B.LIB.names()
assert B.LIB.reference("ventana") == (1.2, 0.0) and len(B.LIB.rows("ventana")) == 2
assert B.LIB.reference("puerta") == (3.0, 0.0), "un bloque que ya existe no se pisa"
assert BC.importar_gms(mgr, carpeta) == 0
print("ok BLOQUESGMS: trae los .json con su P2, no pisa, no mezcla sistemas")
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
