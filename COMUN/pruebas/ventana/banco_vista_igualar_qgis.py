"""Banco con el QGIS REAL (sin pantalla): ZOOM (Z), ENCUADRE (P), REGEN (RE),
REDIBUJA (R) e IGUALARPROP (MA) de IngeCAD en Dibujo (3.61.0).

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 -u banco_vista_igualar_qgis.py'
Termina en «TODO OK». Probado con 4.2.2.
"""
import os, sys, tempfile, faulthandler, json
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
# lo que falla dentro de una llamada de QGIS a Python (flags(), eventos) no corta el
# banco: sólo se imprime. Se junta acá y el banco falla (3.61.1: _PanTool.flags()
# devolvía un int y QGIS 4 lo rechazaba: «int cannot be converted to QFlags»).
ERRORES = []
sys.excepthook = lambda tipo, valor, tb: ERRORES.append(valor)
sys.unraisablehook = lambda u: ERRORES.append(u.exc_value)
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

CFG = "cad_layer_manager/config"
lyr = QgsVectorLayer("LineString?crs=EPSG:32721&field=LAYER_CODE:string(50)&field=CAD_COLOR:string(20)"
                     "&field=CAD_LTYPE:string(40)&field=CAD_LW:double", "lineas", "memory")
lyr.setCustomProperty(CFG, json.dumps({"layers": [
    {"name": "0", "color": {"aci": 7, "rgb": None}},
    {"name": "MUROS", "color": {"aci": 1, "rgb": None}}]}))
QgsProject.instance().addMapLayer(lyr)
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr])
mw.show()
canvas.setExtent(QgsRectangle(-10, -10, 15, 10))
canvas.refresh()
QApplication.processEvents()
lyr.startEditing()


def P(x, y):
    return QgsPointXY(x, y)


def linea(pts, **attrs):
    f = QgsFeature(lyr.fields())
    for k, v in attrs.items():
        f[k] = v
    f.setGeometry(QgsGeometry.fromPolylineXY([P(*p) for p in pts]))
    lyr.addFeature(f)
    return f.id()


from geocad.dibujo.plugin import DibujoCADPlugin
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr


def clic(x, y):
    mgr.point_clicked(P(x, y), False, False)


def ext():
    e = canvas.extent()
    return (e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())


def contiene(e, r):
    return e[0] <= r[0] + 1e-6 and e[1] <= r[1] + 1e-6 and e[2] >= r[2] - 1e-6 and e[3] >= r[3] - 1e-6


def ancho():
    return canvas.extent().width()


a = linea([(0, 0), (100, 0)], LAYER_CODE="MUROS", CAD_COLOR="#ff0000", CAD_LTYPE="DASHED", CAD_LW=0.5)
b = linea([(0, 50), (100, 50)], LAYER_CODE="0")
c = linea([(500, 500), (510, 505)])
lyr.updateExtents()

# ---- 1. ZOOM E (y Intro = Extensión), Previo y Siguiente --------------------------------------
mgr.run("Z E")
assert mgr.command is None, "Z E en una línea"
assert contiene(ext(), (0, 0, 510, 505)), ext()
assert ancho() < 700, "Extensión es lo dibujado (con margen), no más"
mgr.run("ZOOM")
assert mgr.command is not None and mgr.command.state == "opcion"
assert "Extensión" in mgr.cmdline._prompt_plain and "Ventana" in mgr.cmdline._prompt_plain
mgr.submit("")
assert mgr.command is None and contiene(ext(), (0, 0, 510, 505))
canvas.setExtent(QgsRectangle(0, 0, 40, 40)); canvas.refresh()
e40 = ext()
mgr.run("Z E")
mgr.run("Z P")
assert all(abs(x - y) < 1e-6 for x, y in zip(ext(), e40)), (ext(), e40)
mgr.run("Z SI")
assert contiene(ext(), (0, 0, 510, 505)), "Siguiente vuelve a la Extensión"
print("ok ZOOM E (también Intro), Previo y Siguiente")

# ---- 2. nX, n, 1:n, Ampliar y Reducir ------------------------------------------------------------
w = ancho()
mgr.run("Z 2X")
assert abs(ancho() - w / 2) < 1e-6 * w, (ancho(), w)
mgr.run("ZOOM AM")
assert abs(ancho() - w / 4) < 1e-6 * w
mgr.run("Z R")
assert abs(ancho() - w / 2) < 1e-6 * w
mgr.run("Z 1:500")
assert abs(canvas.scale() - 500) < 1, canvas.scale()
mgr.run("Z E"); we = ancho()
mgr.run("Z 2")
assert abs(ancho() - we / 2) < 1e-3 * we, "2 = de todo el dibujo"
mgr.run("Z 1/100XP")
assert mgr.command is None
print("ok 2X, 2, 1:500, Ampliar, Reducir; nXP avisa")

# ---- 3. Ventana: con clics, con V y con una esquina tecleada ---------------------------------
mgr.run("ZOOM")
clic(10, 10)
assert mgr.command.state == "esquina2"
pv = mgr.command.preview(P(30, 20))
assert len(pv[2]) == 5, "rectángulo elástico"
clic(30, 20)
assert mgr.command is None and contiene(ext(), (10, 10, 30, 20)) and ancho() < 40, ext()
mgr.run("Z V"); clic(0, 0); clic(50, 50)
assert contiene(ext(), (0, 0, 50, 50)) and ancho() < 90
mgr.run("ZOOM"); mgr.submit("200;200"); mgr.submit("210;220")
assert contiene(ext(), (200, 200, 210, 220)) and ancho() < 40, ext()
print("ok ZOOM Ventana (clic, V, esquina tecleada)")

# ---- 4. Centro y Escala --------------------------------------------------------------------------
mgr.run("Z C"); clic(100, 100); mgr.submit("20")
e = canvas.extent()
assert abs(e.center().x() - 100) < 1e-6 and abs(e.center().y() - 100) < 1e-6 and abs(e.height() - 20) < 1e-6
mgr.run("Z C"); clic(50, 50); mgr.submit("2X")
assert abs(canvas.extent().height() - 10) < 1e-6, canvas.extent().height()
mgr.run("Z S"); mgr.submit("0.5X")
assert abs(canvas.extent().height() - 20) < 1e-6
mgr.run("Z S"); mgr.submit("1:1000")
assert abs(canvas.scale() - 1000) < 1
print("ok ZOOM Centro (altura y 2X) y Escala")

# ---- 5. Objeto: lo seleccionado, o designado ------------------------------------------------------
mgr.run("Z E")
lyr.selectByIds([c])
mgr.run("Z O")
assert mgr.command is None and contiene(ext(), (500, 500, 510, 505)) and ancho() < 40, ext()
lyr.removeSelection()
mgr.run("Z E")
mgr.run("Z O")
assert mgr.command is not None and mgr.command.state == "objeto"
clic(50, 0)
assert len(mgr.command.objetos) == 1 and mgr.command.preview_geoms(None)
mgr.submit("")
assert contiene(ext(), (0, 0, 100, 0)) and ancho() < 200, ext()
print("ok ZOOM Objeto (selección y designando)")

# ---- 6. transparente: 'Z dentro de LÍNEA no la corta ----------------------------------------------
mgr.run("Z E")
mgr.run("LINEA")
cmd = mgr.command
clic(0, 10)
mgr.submit("'Z 2X")
assert mgr.command is cmd and len(cmd.pts) == 1, "LÍNEA sigue"
mgr.submit("'P")
assert mgr.command is cmd
mgr.submit("'Z V")                                  # pide puntos: no transparente
assert mgr.command is cmd
mgr.submit("'RE")
assert mgr.command is cmd
mgr.cancel()
assert mgr.command is None
print("ok 'Z 2X, 'P, 'RE dentro de LÍNEA; 'Z V avisa")

# ---- 7. ENCUADRE: la mano; Esc, Intro o clic derecho vuelven al modo CAD ------------------------------
from geocad.dibujo.vista_commands import PanCommand, _PanTool
from qgis.PyQt.QtCore import QPoint, Qt
from qgis.PyQt.QtTest import QTest
for salir in ("esc", "intro", "derecho", "tecla esc"):
    mgr.run("P")
    assert isinstance(mgr.command, PanCommand) and isinstance(canvas.mapTool(), _PanTool), salir
    if salir == "esc":
        mgr.cancel()                                   # Esc en la línea de comandos
    elif salir == "intro":
        mgr.submit("")
    elif salir == "derecho":                           # un clic derecho de verdad en el mapa
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(300, 300))
        QApplication.processEvents()
    else:                                              # Esc con el foco en el mapa
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
        QApplication.processEvents()
    assert mgr.command is None and canvas.mapTool() is mgr.tool, salir
# otra herramienta de QGIS mientras tanto: termina sin volver al modo CAD
from qgis.gui import QgsMapToolPan
otra = QgsMapToolPan(canvas)
mgr.run("ENCUADRE")
canvas.setMapTool(otra)
assert mgr.command is None and canvas.mapTool() is otra
mgr.run("P")
f = canvas.mapTool().flags()                       # lo que pide QGIS al activar la mano
from qgis.gui import QgsMapTool
from geocad.dibujo.compat import enum
assert type(f) is type(QgsMapToolPan(canvas).flags()), type(f)
assert not int(f) & int(enum(QgsMapTool, "Flag", "ShowContextMenu")), "sin el menú de QGIS"
mgr.cancel()
assert not ERRORES, ERRORES
print("ok ENCUADRE (P): Esc, Intro, clic derecho y otra herramienta; flags() del tipo de QGIS")

# ---- 8. REGEN y REDIBUJA ------------------------------------------------------------------------------
mgr.run("RE"); mgr.run("R"); mgr.run("REDIBUJA"); mgr.run("REGEN")
assert mgr.command is None
print("ok REGEN (RE) y REDIBUJA (R)")

# ---- 9. IGUALARPROP: origen resaltado, Intro, destinos al momento; E y H devuelven -------------------
d1 = linea([(0, 20), (100, 20)], LAYER_CODE="0", CAD_COLOR="#00ff00")
d2 = linea([(0, 30), (100, 30)])
d3 = linea([(0, 40), (100, 40)], LAYER_CODE="0", CAD_LW=0.13)
mgr.run("Z E")
mgr.run("MA")
cmd = mgr.command
assert cmd is not None and not cmd.selecting
clic(50, 0)                                          # origen: la línea a
assert cmd.origen[1].id() == a and cmd.hl is not None
assert cmd.hl.color().name() == "#ff0000", "resaltado con su color"
mgr.submit("")                                       # Intro confirma
assert cmd.selecting
clic(50, 20)                                         # d1 al momento
g = lyr.getFeature(d1)
assert (g["LAYER_CODE"], g["CAD_COLOR"], g["CAD_LTYPE"], g["CAD_LW"]) == ("MUROS", "#ff0000", "DASHED", 0.5)
assert not lyr.selectedFeatureIds(), "sin el resaltado de selección"
clic(50, 30)
assert lyr.getFeature(d2)["LAYER_CODE"] == "MUROS"
mgr.submit("H")                                      # deshace d2: vuelve a como estaba
g = lyr.getFeature(d2)
assert g["LAYER_CODE"] in (None, "") or g["LAYER_CODE"] != "MUROS", g["LAYER_CODE"]
mgr.submit("E"); clic(50, 20)                        # quitar d1: vuelve a como estaba
g = lyr.getFeature(d1)
assert (g["LAYER_CODE"], g["CAD_COLOR"]) == ("0", "#00ff00"), (g["LAYER_CODE"], g["CAD_COLOR"])
mgr.submit("A"); mgr.submit("C"); clic(-5, 35); clic(105, 45)   # Captura: d3
g = lyr.getFeature(d3)
assert (g["LAYER_CODE"], g["CAD_LW"]) == ("MUROS", 0.5)
assert lyr.getFeature(a)["CAD_COLOR"] == "#ff0000", "el origen no cambia"
mgr.submit("")
assert mgr.command is None and cmd.hl is None
assert lyr.getFeature(d3)["LAYER_CODE"] == "MUROS", "Intro termina y queda"
print("ok IGUALARPROP: origen resaltado, Intro, destinos al momento, H y E devuelven, Captura")

# con un objeto ya elegido: es el origen; Deshacer de QGIS por pasos
lyr.selectByIds([b])
mgr.run("IGUALARPROP")
cmd = mgr.command
assert cmd.selecting and cmd.origen[1].id() == b
clic(50, 40)
g = lyr.getFeature(d3)
assert g["LAYER_CODE"] == "0" and (g["CAD_LW"] is None or str(g["CAD_LW"]) == "NULL"), "PorCapa"
mgr.submit("")
lyr.undoStack().undo()
assert lyr.getFeature(d3)["LAYER_CODE"] == "MUROS", "Deshacer de QGIS vuelve el paso"
print("ok IGUALARPROP con preselección; Ctrl+Z de QGIS por paso")

# a una capa sin campos CAD: los crea; y la capa CAD se agrega a su configuración
otra_capa = QgsVectorLayer("LineString?crs=EPSG:32721", "sin_cad", "memory")
otra_capa.setCustomProperty(CFG, json.dumps({"layers": [{"name": "0", "color": {"aci": 7, "rgb": None}}]}))
QgsProject.instance().addMapLayer(otra_capa)
canvas.setLayers([otra_capa, lyr])
otra_capa.startEditing()
f = QgsFeature(otra_capa.fields()); f.setGeometry(QgsGeometry.fromPolylineXY([P(0, 70), P(100, 70)]))
otra_capa.addFeature(f); fo = f.id()
iface.activeLayer.return_value = otra_capa
mgr.run("MA")
clic(50, 0)                                          # origen en OTRA capa (lineas)
assert mgr.command.origen[0] is lyr
mgr.submit("")
clic(50, 70)
mgr.submit("")
g = otra_capa.getFeature(fo)
assert g["LAYER_CODE"] == "MUROS" and g["CAD_COLOR"] == "#ff0000" and g["CAD_LTYPE"] == "DASHED", g.attributes()
cfg = json.loads(otra_capa.customProperty(CFG))
assert any(l["name"] == "MUROS" and l["color"]["aci"] == 1 for l in cfg["layers"]), cfg
print("ok IGUALARPROP entre capas: crea los campos y agrega la capa CAD con su color")

# ---- 10. los botones nuevos, con su geocad_id ---------------------------------------------------------
ids = {x.property("geocad_id") for x in plugin.actions}
for ico in ("zoom", "zoomwin", "zoomext", "zoomprev", "zoomobj", "pan", "regen", "matchprop"):
    assert "dibujo:" + ico in ids, ico
from qgis.PyQt.QtWidgets import QToolBar
en_barras = {a.property("geocad_id") for tb in mw.findChildren(QToolBar) for a in tb.actions()}
assert not {"dibujo:" + i for i in ("zoom", "zoomwin", "zoomext", "zoomprev", "zoomobj", "pan", "regen",
                                     "matchprop")} & en_barras, "sólo en el banco, en ninguna barra"
print("ok botones dibujo:zoom, zoomwin, zoomext, zoomprev, zoomobj, pan, regen, matchprop (sólo banco)")

plugin.unload()
QApplication.processEvents()
assert not ERRORES, "errores dentro de llamadas de QGIS: %r" % ERRORES
print("TODO OK banco_vista_igualar_qgis")
