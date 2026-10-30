"""Banco con el QGIS REAL (sin pantalla): RECORTA y ALARGA con el
comportamiento de las herramientas de Fernando, y F3 / F8 con otra
herramienta de QGIS (3.40.0). RECORTA en una capa de polígonos: el de corte
le quita a cada polígono tocado la parte superpuesta (3.58.0).

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_recorta_qgis.py'
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


# ---- 1. RECORTA: la arista designada corta por su prolongación ---------------------------
limpiar()
tijera = linea((0, 1), (0, 2))              # no llega a la línea
blanco = linea((-5, 0), (5, 0))
mgr.run("RECORTA")
assert mgr.command is not None and mgr.command.selecting, "RECORTA empieza designando aristas"
clic(0, 1.5)                                # designa la tijera
assert lyr.selectedFeatureIds() == [tijera]
mgr.enter()
assert not mgr.command.selecting and mgr.command.boundary == [tijera]
assert lyr.selectedFeatureIds() == [tijera], "la arista queda marcada"
pv = mgr.command.preview_geoms(P(3, 0))     # vista previa: el tramo que se va
assert pv and abs(pv[0].length() - 5.0) < 1e-6, pv
clic(3, 0)
g = geoms()[blanco]
assert abs(g.length() - 5.0) < 1e-6 and abs(g.boundingBox().xMaximum()) < 1e-6, g.asWkt()
print("ok RECORTA: la tijera corta por su prolongación, con vista previa")

# H deshace el recorte; Arista = No prolongación: la tijera que no llega no corta y no borra
mgr.submit("H")
assert abs(geoms()[blanco].length() - 10.0) < 1e-6
mgr.submit("A")
mgr.submit("N")
assert mgr.command.edge == "N"
clic(3, 0)
assert blanco in geoms() and abs(geoms()[blanco].length() - 10.0) < 1e-6, "no se borra"
mgr.submit("A")
mgr.submit("P")
assert mgr.command.edge == "E"
mgr.cancel()
assert mgr.command is None and not lyr.selectedFeatureIds()
print("ok RECORTA: desHacer, Arista Prolongación / No prolongación (se recuerda)")

# ---- 2. RECORTA en modo rápido (Intro sin designar): todo lo visible corta, sin prolongar
limpiar()
linea((0, 1), (0, 2))
cruza = linea((2, -1), (2, 1))
blanco = linea((-5, 0), (5, 0))
mgr.run("TR")
mgr.enter()
assert mgr.command.boundary is None and not mgr.command.selecting
clic(4, 0)
g = geoms()[blanco]
assert abs(g.length() - 7.0) < 1e-6, g.asWkt()          # cortó en x=2, no en x=0
# Mayús + clic alarga (como AutoCAD)
corta = linea((-3, 5), (1, 5))
vertical = linea((4, 3), (4, 7))
clic(0.5, 5, shift=True)
assert abs(geoms()[corta].boundingBox().xMaximum() - 4.0) < 1e-6, geoms()[corta].asWkt()
mgr.cancel()
print("ok RECORTA rápido (Intro = todos los objetos visibles) y Mayús = alargar")

# ---- 3. ALARGA: primero las líneas de llegada, después las que se alargan ---------------
limpiar()
llegada = linea((10, -5), (10, 5))
otra = linea((7, -5), (7, -1))              # visible, pero no designada
fuente = linea((-5, 3), (5, 3))
mgr.run("ALARGA")
assert mgr.command.selecting, "ALARGA empieza designando contornos"
clic(10, 0)
mgr.enter()
assert mgr.command.boundary == [llegada]
pv = mgr.command.preview_geoms(P(4, 3))
assert pv and abs(pv[0].length() - 5.0) < 1e-6, "vista previa del tramo que se agrega"
clic(4, 3)
bb = geoms()[fuente].boundingBox()
assert abs(bb.xMaximum() - 10.0) < 1e-6, geoms()[fuente].asWkt()
antes = geoms()[llegada].asWkt()
clic(10, 4.5)                               # el contorno no se alarga
assert geoms()[llegada].asWkt() == antes
mgr.cancel()
# Intro sin designar = todos los objetos visibles (llega a la más cercana)
fuente2 = linea((0, -3), (5, -3))
mgr.run("EX")
mgr.enter()
clic(4.5, -3)
assert abs(geoms()[fuente2].boundingBox().xMaximum() - 7.0) < 1e-6, geoms()[fuente2].asWkt()
mgr.cancel()
print("ok ALARGA: líneas de llegada primero, vista previa, contornos quietos, Intro = todos")


# ---- 3b. RECORTA con polígonos: el de corte quita lo superpuesto (3.58.0) -----------------
plyr = QgsVectorLayer("MultiPolygon?crs=EPSG:32721&field=nombre:string", "poligonos", "memory")
QgsProject.instance().addMapLayer(plyr)
canvas.setLayers([plyr, lyr])
plyr.startEditing()
iface.activeLayer.return_value = plyr


def poligono(nombre, wkt):
    f = QgsFeature(plyr.fields())
    f.setAttributes([nombre])
    f.setGeometry(QgsGeometry.fromWkt(wkt))
    plyr.addFeature(f)
    return f.id()


def pgeoms():
    return {f.id(): f for f in plyr.getFeatures()}


corte = poligono("corte", "POLYGON((0 0, 4 0, 4 4, 0 4, 0 0))")
a = poligono("a", "POLYGON((2 2, 8 2, 8 3, 2 3, 2 2))")                 # se superpone en 2..4
b = poligono("b", "POLYGON((-2 1, 6 1, 6 1.5, -2 1.5, -2 1))")          # lo atraviesa: dos pedazos
c = poligono("c", "POLYGON((1 3.2, 2 3.2, 2 3.8, 1 3.8, 1 3.2))")       # entero adentro
d = poligono("d", "POLYGON((10 -5, 12 -5, 12 -3, 10 -3, 10 -5))")       # no se toca
mgr.run("RECORTA")
assert mgr.command is not None and mgr.command.selecting
mgr.enter()                                     # sin designar: con polígonos no hay modo rápido
assert mgr.command.selecting, "con polígonos hay que designar el de corte"
clic(0.5, 0.5)
assert plyr.selectedFeatureIds() == [corte]
mgr.enter()
assert not mgr.command.selecting and mgr.command.boundary == [corte]
pv = mgr.command.preview_geoms(P(7, 2.5))       # vista previa: lo que se va
assert pv and abs(pv[0].area() - 2.0) < 1e-6, pv
clic(7, 2.5)
g = pgeoms()[a].geometry()
assert abs(g.area() - 4.0) < 1e-6 and abs(g.boundingBox().xMinimum() - 4.0) < 1e-6, g.asWkt()
assert abs(pgeoms()[corte].geometry().area() - 16.0) < 1e-6, "el de corte no cambia"
n0 = len(pgeoms())
clic(5, 1.25)                                   # partido: dos objetos con el mismo nombre
fs = [f for f in pgeoms().values() if f["nombre"] == "b"]
assert len(pgeoms()) == n0 + 1 and len(fs) == 2, [f.geometry().asWkt() for f in fs]
assert sorted(round(f.geometry().area(), 6) for f in fs) == [1.0, 1.0]
clic(1.5, 3.5)                                  # entero adentro: se borra
assert c not in pgeoms()
clic(11, -4)                                    # no se superpone: queda igual
assert abs(pgeoms()[d].geometry().area() - 4.0) < 1e-6
mgr.submit("H")                                 # deshace el borrado de c
assert c in pgeoms()
mgr.submit("H")                                 # y el corte en dos de b
assert len([f for f in pgeoms().values() if f["nombre"] == "b"]) == 1
assert abs(pgeoms()[b].geometry().area() - 4.0) < 1e-6
mgr.cancel()
assert mgr.command is None
iface.activeLayer.return_value = lyr
canvas.setLayers([lyr])
print("ok RECORTA con polígonos: quita lo superpuesto, pedazos con sus atributos, desHacer")


# ---- 4. F3 / F8 con otra herramienta de QGIS ---------------------------------------------
def tecla(key, mods=Qt.KeyboardModifier.NoModifier):
    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyPress, key, mods))


pan = QgsMapToolPan(canvas)
canvas.setMapTool(pan)
snap0 = QgsProject.instance().snappingConfig().enabled()
orto0 = mgr.ortho
tecla(Qt.Key.Key_F3)
assert QgsProject.instance().snappingConfig().enabled() != snap0
tecla(Qt.Key.Key_F8)
assert mgr.ortho != orto0
tecla(Qt.Key.Key_F3, Qt.KeyboardModifier.ControlModifier)     # Ctrl+F3 no es nuestra
assert QgsProject.instance().snappingConfig().enabled() != snap0
tecla(Qt.Key.Key_F3)
tecla(Qt.Key.Key_F8)
assert QgsProject.instance().snappingConfig().enabled() == snap0 and mgr.ortho == orto0
print("ok F3 / F8 con la herramienta Desplazar de QGIS")

# ---- 5. apagado: no queda nada escuchando ------------------------------------------------
errores = []
sys.excepthook = lambda t, v, tb: errores.append("%s: %s" % (t.__name__, v))
combo, fuente = plugin.size_combo, plugin.font_combo
plugin.unload()
tecla(Qt.Key.Key_F3)
assert QgsProject.instance().snappingConfig().enabled() == snap0, "sin GeoCAD, F3 no hace nada"
# Fernando, 24/10/2026 (3.45.1): tras descargar Dibujo los combos de Texto CAD
# avisaban y daban «'NoneType' object has no attribute 'text_style'».
for w in (combo, fuente):
    try:
        w.blockSignals(False)
        if w is combo:
            w.lineEdit().blockSignals(False)
    except RuntimeError:
        pass
try:
    combo.setEditText("7.5")
    combo.lineEdit().editingFinished.emit()
    combo.activated.emit(0)
except RuntimeError:
    pass                                     # el combo ya no existe: tampoco hay aviso
plugin._set_size(); plugin._set_bold(True); plugin._set_text_color("#ff0000"); plugin._style_changed("height")
QApplication.processEvents()
assert not errores, errores
print("ok sin rastro al apagar (y los combos de Texto CAD no fallan después)")
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
