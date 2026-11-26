"""Banco con el QGIS REAL (sin pantalla): 3.97.0 (Fernando, 26/11/2026).

1. Lo que no se dibuja no se designa: una capa CAD apagada (categoría sin
   tildar, como la apaga Capas) no entra en la ventana, la captura, PC, el
   clic ni Todo; las encendidas sí.
2. FILTRO (FI): con la ventana del núcleo (acá se le contesta sin mostrarla),
   Intro = toda la capa; con preselección filtra ésa; el resultado queda
   seleccionado; los de capas apagadas no cuentan; FI dentro de DESIGNA suma;
   FI <nombre> usa un filtro guardado. La ventana de verdad se arma con el Qt
   de QGIS (PyQt6) y agrega condiciones.
3. Propiedades: «Cerrada» Sí/No en polilíneas (una o varias), un solo U por
   capa; en polígonos queda Sí, sin elegir.

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

from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol
from qgis.PyQt.QtWidgets import QComboBox

lyr = QgsVectorLayer("Polygon?crs=EPSG:5349&field=LAYER_CODE:string&field=PROP:string&field=SUP:double",
                     "parcelas", "memory")
lin = QgsVectorLayer("LineString?crs=EPSG:5349&field=LAYER_CODE:string", "lineas", "memory")
QgsProject.instance().addMapLayers([lyr, lin])
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr, lin])
mw.show()
canvas.setExtent(QgsRectangle(-5, -5, 60, 40))
canvas.refresh()
QApplication.processEvents()
lyr.startEditing()


def poli(capa, prop, sup, x, y, w=8, h=8):
    f = QgsFeature(lyr.fields())
    f.setAttributes([capa, prop, sup])
    f.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(x, y), QgsPointXY(x + w, y),
                                               QgsPointXY(x + w, y + h), QgsPointXY(x, y + h),
                                               QgsPointXY(x, y)]]))
    lyr.addFeature(f)
    return f.id()


A1 = poli("visible", "PEREZ", 64, 0, 0)
A2 = poli("visible", "GOMEZ", 64, 10, 0)
B1 = poli("apagada", "PEREZ", 64, 0, 10)          # encima, en la capa CAD apagada
B2 = poli("apagada", "LOPEZ", 64, 10, 10)
C1 = poli("visible", "PEREZ", 16, 30, 0, 4, 4)
cats = []
for valor, on in (("visible", True), ("apagada", False)):
    c = QgsRendererCategory(valor, QgsSymbol.defaultSymbol(lyr.geometryType()), valor)
    c.setRenderState(on)
    cats.append(c)
lyr.setRenderer(QgsCategorizedSymbolRenderer("LAYER_CODE", cats))
canvas.refresh()
QApplication.processEvents()

from geocad.dibujo.plugin import DibujoCADPlugin
import geocad.filtro_ui as UI
import geocad.filtro as FQ
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr
ecos = []
_echo = mgr.cmdline.echo
mgr.cmdline.echo = lambda t, *a, **k: (ecos.append(t), _echo(t, *a, **k))


def clic(x, y):
    mgr.point_clicked(QgsPointXY(x, y), False, False)


def sel():
    return sorted(lyr.selectedFeatureIds())


# ---- 1. lo que no se dibuja no se designa ----------------------------------------------------
mgr.run("DESIGNA"); clic(-2, -2); clic(40, 25); mgr.enter()         # ventana que encierra todo
assert sel() == sorted([A1, A2, C1]), sel()
lyr.removeSelection()
mgr.run("DESIGNA"); clic(40, 25); clic(-2, -2); mgr.enter()         # captura
assert sel() == sorted([A1, A2, C1]), sel()
lyr.removeSelection()
mgr.run("DESIGNA"); clic(4, 4)                                       # clic en A1: se elige
clic(4, 14)                                                          # en B1 (apagada): no la elige,
assert mgr.command.win is not None                                   # empieza una ventana (como AutoCAD)
mgr.enter(); mgr.enter()
assert sel() == [A1], sel()
lyr.removeSelection()
mgr.run("DESIGNA"); mgr.submit("T"); mgr.enter()
assert sel() == sorted([A1, A2, C1]), sel()
lyr.removeSelection()
mgr.run("DESIGNA"); mgr.submit("PC")
for p in ((-1, -1), (50, -1), (50, 30), (-1, 30)):
    clic(*p)
mgr.enter(); mgr.enter()
assert sel() == sorted([A1, A2, C1]), sel()
lyr.removeSelection()
# encendida otra vez: entra
r = lyr.renderer().clone(); r.updateCategoryRenderState(1, True); lyr.setRenderer(r)
mgr.run("DESIGNA"); mgr.submit("T"); mgr.enter()
assert sel() == sorted([A1, A2, B1, B2, C1]), sel()
r = lyr.renderer().clone(); r.updateCategoryRenderState(1, False); lyr.setRenderer(r)
lyr.removeSelection()
print("ok las capas CAD apagadas no se designan (ventana, captura, clic, Todo, PC)")

# ---- 2. FILTRO -----------------------------------------------------------------------------
respuestas = []
_editar = UI.editar
UI.editar = lambda *a, **k: respuestas.pop(0)
PEREZ = [{"p": "campo_qgis", "campo": "PROP", "op": "=", "v": "PEREZ"}]
respuestas.append({"accion": "aplicar", "conds": PEREZ})
mgr.run("FI")
assert type(mgr.command).__name__ == "FilterCommand", mgr.command
mgr.enter()                                                          # Intro: toda la capa
assert sel() == sorted([A1, C1]) and mgr.command is None, sel()      # B1 (apagada) no
assert sorted(mgr.prev_selection[lyr.id()]) == sel(), mgr.prev_selection.get(lyr.id())
print("ok FI, Intro = toda la capa: sólo los visibles que cumplen; quedan seleccionados")
lyr.selectByIds([A1, A2])
respuestas.append({"accion": "aplicar", "conds": PEREZ})
mgr.run("FILTRO")
assert sel() == [A1] and mgr.command is None, sel()
print("ok con preselección filtra ésa")
respuestas.append({"accion": "aplicar", "conds": [{"p": "area", "op": "<", "v": 20}]})
lyr.removeSelection()
mgr.run("FI"); clic(-2, -2); clic(40, 25); mgr.enter()
assert sel() == [C1], sel()
print("ok designando: ventana y después el filtro")
lyr.removeSelection()
respuestas.append({"accion": "aplicar", "conds": [{"p": "campo_qgis", "campo": "PROP", "op": "=", "v": "GOMEZ"}]})
mgr.run("DESIGNA"); clic(34, 2); mgr.submit("FI"); mgr.enter()
assert sel() == sorted([A2, C1]), sel()
FQ.guardar("perez", PEREZ)
lyr.removeSelection()
mgr.run("DESIGNA"); mgr.submit("FI perez"); mgr.enter()
assert sel() == sorted([A1, C1]), sel()
assert not respuestas
print("ok FI dentro de DESIGNA y FI <nombre>")
respuestas.append(None)
lyr.selectByIds([A2])
mgr.run("FI")
assert sel() == [A2] and mgr.command is None and any("cancelado" in e for e in ecos[-2:])
print("ok cancelar no toca la selección")
UI.editar = _editar
# la ventana de verdad, con el Qt de QGIS
from qgis.PyQt import QtCore, QtWidgets
objs = FQ.candidatos(canvas, lyr)
dlg = UI._Dialogo(QtCore, QtWidgets, mw, [], objs, lyr, True)
assert dlg.windowTitle().startswith("Filtros de selección")
dlg.prop.setCurrentIndex(dlg.prop.findData("capa")); dlg._cambio_propiedad()
dlg.vals[0].setCurrentText("vis*"); dlg._agregar()
dlg.prop.setCurrentIndex(dlg.prop.findData("campo_qgis")); dlg._cambio_propiedad()
assert [dlg.vals[0].itemText(i) for i in range(dlg.vals[0].count())] == ["LAYER_CODE", "PROP", "SUP"]
assert dlg.lista.topLevelItemCount() == 1 and dlg.conds == [{"p": "capa", "op": "=", "v": "vis*"}]
assert sorted(o.fid for o in FQ.filtrar(objs, dlg.conds)) == sorted([A1, A2, C1])
dlg.close()
print("ok la ventana del núcleo con el Qt de QGIS")

# ---- 3. Cerrada en Propiedades -----------------------------------------------------------------
iface.activeLayer.return_value = lin
lin.startEditing()
def linea(*pts):
    f = QgsFeature(lin.fields()); f.setAttributes(["0"])
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in pts])); lin.addFeature(f)
    return f.id()
L1 = linea((0, 30), (10, 30), (10, 38))
L2 = linea((20, 30), (30, 30), (30, 38))
L3 = linea((40, 30), (45, 30))                                     # 2 vértices: no se cierra
props = plugin.props
props.show()
lyr.removeSelection()                    # con tipos mezclados el panel no muestra Geometría
lin.selectByIds([L1])
props.refresh(); props._build()
filas = {props.table.item(r, 0).text().strip(): props.table.cellWidget(r, 1)
         for r in range(props.table.rowCount()) if props.table.item(r, 0)}
assert isinstance(filas.get("Cerrada"), QComboBox) and filas["Cerrada"].currentText() == "No", filas.keys()
pila = lin.undoStack().index()
props._set_closed([(lin, L1, "Polilínea")], True)
v = lin.getFeature(L1).geometry().asPolyline()
assert len(v) == 4 and v[0] == v[-1] and lin.undoStack().index() == pila + 1, v
props._set_closed([(lin, L1, "Polilínea"), (lin, L2, "Polilínea"), (lin, L3, "Línea")], True)
assert lin.getFeature(L2).geometry().asPolyline()[-1] == QgsPointXY(20, 30)
assert len(lin.getFeature(L3).geometry().asPolyline()) == 2
props._set_closed([(lin, L1, "Polilínea"), (lin, L2, "Polilínea")], False)
assert len(lin.getFeature(L1).geometry().asPolyline()) == 3 and len(lin.getFeature(L2).geometry().asPolyline()) == 3
lin.undoStack().undo()
assert len(lin.getFeature(L2).geometry().asPolyline()) == 4
iface.activeLayer.return_value = lyr
lin.removeSelection()
lyr.selectByIds([A1])
props.refresh(); props._build()
filas = {props.table.item(r, 0).text().strip(): props.table.cellWidget(r, 1)
         for r in range(props.table.rowCount()) if props.table.item(r, 0)}
assert not isinstance(filas.get("Cerrada"), QComboBox) and filas["Cerrada"].text() == "Sí"
print("ok Cerrada Sí/No en polilíneas (una o varias, un U); polígonos: Sí")
plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
