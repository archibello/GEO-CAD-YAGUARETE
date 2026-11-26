"""Banco con el QGIS REAL (sin pantalla): UNIR (J) con POLÍGONOS (3.96.0), como
«Combinar objetos espaciales».

Una capa de polígonos con tabla (NOMBRE, LOTE) y el caso de las capturas de
Fernando (cuatro parcelas que se tocan en los vértices, con ranuras entre ellas):
* J, designar, Enter: avisa islas y huecos y pregunta «¿Quiere crear una capa
  nueva con el resultado? [Sí/No] <No>» (3.97.2);
* Enter o N (No): queda el mayor con la geometría unida, los demás se
  borran, un solo U;
* S (Sí): capa «combinados de <capa>», GeoPackage en la carpeta del proyecto, en
  borde rojo y sin relleno, datos del de mayor superficie; la original no se toca; otra N sobre la
  misma capa con S agrega a ESA capa (también si se quitó del proyecto);
* islas aparte, cada una con su mayor; si no se tocan, avisa y no hace nada;
* capa temporal y proyecto sin guardar: Documentos/GeoCAD;
* con LÍNEAS, J sigue igual (la pregunta no aparece).

Se corre como banco_unir_qgis.py, con el Python de QGIS. Termina en «TODO OK».
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

CASA = os.environ["HOME"]
os.makedirs(os.path.join(CASA, "Documentos"))
OBRA = tempfile.mkdtemp(prefix="banco-obra-")
lyr = QgsVectorLayer("Polygon?crs=EPSG:5349&field=NOMBRE:string&field=LOTE:integer", "parcelas", "memory")
QgsProject.instance().addMapLayer(lyr)
QgsProject.instance().setFileName(os.path.join(OBRA, "obra.qgz"))
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr])
mw.show()
E, N = 14522900.0, 9977200.0
canvas.setExtent(QgsRectangle(E - 5, N - 5, E + 60, N + 20))
canvas.refresh()
QApplication.processEvents()
lyr.startEditing()


def poli(nombre, lote, pts, capa=None):
    capa = capa or lyr
    f = QgsFeature(capa.fields())
    f.setAttributes([nombre, lote])
    f.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(*p) for p in pts + pts[:1]]]))
    capa.addFeature(f)
    return f.id()


def filas(capa=None):
    return {f["NOMBRE"]: (f["LOTE"], f.geometry()) for f in (capa or lyr).getFeatures()}


def limpiar():
    for fid in [f.id() for f in lyr.getFeatures()]:
        lyr.deleteFeature(fid)


from geocad.dibujo.plugin import DibujoCADPlugin
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr
ecos = []
_echo = mgr.cmdline.echo
mgr.cmdline.echo = lambda t, *a, **k: (ecos.append(t), _echo(t, *a, **k))


def clic(x, y):
    mgr.point_clicked(QgsPointXY(x, y), False, False)


def armar():
    limpiar()
    poli("A", 1, [(E, N), (E + 10, N), (E + 10, N + 6), (E + 4.7, N + 6), (E, N + 6)])      # 60 m²: manda
    poli("B", 2, [(E, N + 6), (E + 4.7, N + 6), (E + 4.7, N + 12), (E, N + 12)])
    poli("C", 3, [(E + 4.7, N + 6), (E + 4.72, N + 9), (E + 4.7, N + 12), (E + 10, N + 12), (E + 10, N + 6)])
    poli("D", 4, [(E + 10, N), (E + 14, N), (E + 14, N + 12), (E + 10, N + 12), (E + 10.01, N + 6)])
    poli("S", 5, [(E + 40, N), (E + 42, N), (E + 42, N + 2), (E + 40, N + 2)])             # solo
    poli("T", 6, [(E + 42, N), (E + 43, N), (E + 43, N + 1), (E + 42, N + 1)])             # toca a S


def capa(nombre):
    cs = QgsProject.instance().mapLayersByName(nombre)
    assert len(cs) == 1, (nombre, cs)
    return cs[0]


def designar_cuatro():
    clic(E + 2, N + 2); clic(E + 2, N + 10); clic(E + 7, N + 10); clic(E + 12, N + 5)


# ---- 1. Enter: en la misma capa, un solo U ------------------------------------------------
armar()
pila = lyr.undoStack().index()
mgr.run("J")
assert type(mgr.command).__name__ == "JoinCommand"
designar_cuatro(); mgr.enter()
assert "¿Quiere crear una capa nueva con el resultado? [Sí/No] <No>" in mgr.cmdline._prompt_plain, \
    mgr.cmdline._prompt_plain
assert any("2 hueco(s) encerrado(s) relleno(s)" in e for e in ecos), ecos[-3:]
mgr.enter()
f = filas()
assert sorted(f) == ["A", "S", "T"] and abs(f["A"][1].area() - 168) < 1e-3, f
assert lyr.undoStack().index() == pila + 1, "un solo paso de deshacer"
assert not QgsProject.instance().mapLayersByName("combinados de parcelas")
lyr.undoStack().undo()
assert sorted(filas()) == ["A", "B", "C", "D", "S", "T"]
mgr.run("J"); designar_cuatro(); mgr.enter(); mgr.submit("N")      # N = No: también la misma capa
assert sorted(filas()) == ["A", "S", "T"] and not QgsProject.instance().mapLayersByName("combinados de parcelas")
lyr.undoStack().undo()
print("ok Enter o N (No): en la misma capa con los datos del mayor; un solo U")

# ---- 2. N: capa nueva en rojo, la original intacta --------------------------------------------
mgr.run("J"); designar_cuatro(); mgr.enter(); mgr.submit("S")
assert mgr.command is None
nueva = capa("combinados de parcelas")
ruta = nueva.source().split("|")[0]
assert ruta == os.path.join(OBRA, "combinados de parcelas.gpkg") and os.path.exists(ruta), ruta
f = filas(nueva)
assert list(f) == ["A"] and f["A"][0] == 1 and abs(f["A"][1].area() - 168) < 1e-3, f
capa_sim = nueva.renderer().symbol().symbolLayer(0)
borde = capa_sim.strokeColor()
assert (borde.red(), borde.green(), borde.blue()) == (255, 0, 0), borde.name()   # el borde, en rojo
assert capa_sim.fillColor().alpha() == 0 or capa_sim.brushStyle() == 0, "sin relleno (nunca rojo)"
assert len(filas()) == 6, "la original no se toca"
print("ok S (Sí): «combinados de parcelas».gpkg en la carpeta del proyecto, en rojo, datos de A")

# ---- 3. otra N sobre la misma capa: a la MISMA capa combinada ------------------------------
mgr.run("J"); clic(E + 41, N + 1); clic(E + 42.5, N + 0.5); mgr.enter(); mgr.submit("S")
cs = QgsProject.instance().mapLayersByName("combinados de parcelas")
assert len(cs) == 1 and cs[0].id() == nueva.id(), [c.source() for c in cs]
assert sorted(filas(nueva)) == ["A", "S"] and any("Agregado a la capa" in e for e in ecos[-2:]), ecos[-2:]
assert not os.path.exists(os.path.join(OBRA, "combinados de parcelas (2).gpkg"))
# quitada del proyecto (o el proyecto vuelto a abrir): usa el mismo archivo
QgsProject.instance().removeMapLayer(nueva.id())
mgr.run("J"); clic(E + 41, N + 1); clic(E + 42.5, N + 0.5); mgr.enter(); mgr.submit("S")
cs = QgsProject.instance().mapLayersByName("combinados de parcelas")
assert len(cs) == 1 and cs[0].source().split("|")[0] == ruta and cs[0].featureCount() == 3, \
    [c.source() for c in cs]
assert not os.path.exists(os.path.join(OBRA, "combinados de parcelas (2).gpkg"))
nueva = cs[0]
print("ok la segunda S va a la misma capa combinada (y al mismo archivo)")

# ---- 4. no se tocan: avisa y no hace nada; Esc en la pregunta tampoco ------------------------
armar()
n = len(QgsProject.instance().mapLayers())
mgr.run("J"); clic(E + 2, N + 2); clic(E + 41, N + 1); mgr.enter()
assert mgr.command is None and any("no se tocan" in e for e in ecos[-2:]), ecos[-2:]
mgr.run("J"); designar_cuatro(); mgr.enter(); mgr.cancel()
assert len(filas()) == 6 and len(QgsProject.instance().mapLayers()) == n and mgr.command is None
print("ok sin contacto o con Esc: nada cambia")

# ---- 5. capa temporal sin proyecto guardado: Documentos/GeoCAD -------------------------------
QgsProject.instance().setFileName("")
for c in QgsProject.instance().mapLayersByName("combinados de parcelas"):
    QgsProject.instance().removeMapLayer(c.id())
QApplication.processEvents()
assert not QgsProject.instance().mapLayersByName("combinados de parcelas")
mgr.run("J"); designar_cuatro(); mgr.enter(); mgr.submit("S")
c = [x for x in QgsProject.instance().mapLayersByName("combinados de parcelas")
     if os.path.join(CASA, "Documentos", "GeoCAD") in x.source()]
assert len(c) == 1, [x.source() for x in QgsProject.instance().mapLayers().values()]
print("ok sin proyecto guardado: Documentos/GeoCAD")

# ---- 6. con líneas, J como antes ---------------------------------------------------------------
lin = QgsVectorLayer("LineString?crs=EPSG:5349&field=NOMBRE:string&field=LOTE:integer", "lineas", "memory")
QgsProject.instance().addMapLayer(lin)
iface.activeLayer.return_value = lin
canvas.setLayers([lin, lyr])
lin.startEditing()
for nom, pts in (("l1", [(E, N - 3), (E + 10, N - 3)]), ("l2", [(E + 10, N - 3), (E + 12, N - 3)])):
    fe = QgsFeature(lin.fields()); fe.setAttributes([nom, 1])
    fe.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in pts])); lin.addFeature(fe)
mgr.run("J"); clic(E + 5, N - 3); clic(E + 11, N - 3); mgr.enter()
assert mgr.command is None and [fe["NOMBRE"] for fe in lin.getFeatures()] == ["l1"]
print("ok con líneas, J sigue igual")
# ---- 7. capa de LÍNEAS con polilíneas cerradas (3.97.3), como la de Fernando -----------------
pl = QgsVectorLayer("LineString?crs=EPSG:5349&field=NOMBRE:string&field=LOTE:integer", "borrador", "memory")
QgsProject.instance().addMapLayer(pl)
QgsProject.instance().setFileName(os.path.join(OBRA, "obra.qgz"))
iface.activeLayer.return_value = pl
canvas.setLayers([pl, lyr, lin])
pl.startEditing()
OX = 100.0
ANILLOS = {
    "A": [(E, N), (E + 10, N), (E + 10, N + 6), (E + 4.7, N + 6), (E, N + 6)],
    "B": [(E, N + 6), (E + 4.7, N + 6), (E + 4.7, N + 12), (E, N + 12)],
    "C": [(E + 4.7, N + 6), (E + 4.72, N + 9), (E + 4.7, N + 12), (E + 10, N + 12), (E + 10, N + 6)],
    "D": [(E + 10, N), (E + 14, N), (E + 14, N + 12), (E + 10, N + 12), (E + 10.01, N + 6)],
}
for i, (nom, pts) in enumerate(ANILLOS.items()):
    fe = QgsFeature(pl.fields()); fe.setAttributes([nom, i + 1])
    pts = [(x + OX, y) for x, y in pts]
    fe.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in pts + pts[:1]])); pl.addFeature(fe)
fe = QgsFeature(pl.fields()); fe.setAttributes(["abierta", 9])
fe.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(E + OX, N - 5), QgsPointXY(E + OX + 10, N - 5)]))
pl.addFeature(fe)


def filas_pl(capa=None):
    return {f["NOMBRE"]: f.geometry() for f in (capa or pl).getFeatures()}


pl.selectByIds([f.id() for f in pl.getFeatures()])
pila = pl.undoStack().index()
mgr.run("J")
assert "¿Quiere crear una capa nueva con el resultado? [Sí/No] <No>" in mgr.cmdline._prompt_plain, \
    mgr.cmdline._prompt_plain
assert any("1 objeto(s) que no son polígonos ni polilíneas cerradas" in e for e in ecos[-4:]), ecos[-4:]
mgr.enter()
f = filas_pl()
assert sorted(f) == ["A", "abierta"], f.keys()
g = f["A"]
v = g.asPolyline() if not g.isMultipart() else g.asMultiPolyline()[0]
assert v[0] == v[-1] and abs(QgsGeometry.fromPolygonXY([v]).area() - 168) < 1e-3, g.asWkt()
assert pl.undoStack().index() == pila + 1
pl.undoStack().undo()
assert len(filas_pl()) == 5
pl.selectByIds([f.id() for f in pl.getFeatures() if f["NOMBRE"] != "abierta"])
mgr.run("J"); mgr.submit("S")
c = capa("combinados de borrador")
assert c.geometryType() == pl.geometryType() and list(filas_pl(c)) == ["A"], filas_pl(c)
sim = c.renderer().symbol()
assert (sim.color().red(), sim.color().green(), sim.color().blue()) == (255, 0, 0), sim.color().name()
assert len(filas_pl()) == 5, "la original no se toca"
# dos líneas abiertas: el UNIR de líneas de siempre
pl.selectByIds([f.id() for f in pl.getFeatures() if f["NOMBRE"] == "abierta"])
print("ok capa de líneas: polilíneas cerradas se unen como polígonos (Enter y Sí, en rojo como línea)")
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
