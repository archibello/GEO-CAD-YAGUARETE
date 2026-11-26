"""Banco con el QGIS REAL (sin pantalla): ESCALA (SCALE, SC) en Dibujo (3.98.0).

La misma que SCALE (SC) de IngeCAD 0.8.0 (tools/edit.py ScaleTool), con la orden de verdad:
* SC, designar, punto base, factor escrito: escala; un solo U vuelve atrás;
* el factor también es la distancia del clic a la base;
* Copia: el original queda y se agrega la copia escalada;
* Referencia: longitud escrita o con dos puntos (Intro = 1) y nueva longitud escrita,
  desde la base o con [Puntos];
* el valor debe ser positivo (0 y negativos se rechazan y la orden sigue);
* textos (ALTURA) y bloques (ESCALA_X/Y) escalan con el objeto;
* el botón «dibujo:scale» va detrás de GIRA en Yaguá Edición y en el banco Edición,
  y la migración «escala-qgis» lo agrega a las barras ya guardadas.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_escala_qgis.py'
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

lyr = QgsVectorLayer("LineString?crs=EPSG:32721&field=NOMBRE:string", "lineas", "memory")
txt = QgsVectorLayer("Point?crs=EPSG:32721&field=TEXTO:string&field=ALTURA:double&field=ROTACION:double"
                     "&field=ESCALA_X:double&field=ESCALA_Y:double", "textos", "memory")
QgsProject.instance().addMapLayers([lyr, txt])
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr, txt])
mw.show()
canvas.setExtent(QgsRectangle(-20, -20, 60, 60))
canvas.refresh()
QApplication.processEvents()
lyr.startEditing()
txt.startEditing()

CUADRADO = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]


def armar():
    for fid in [f.id() for f in lyr.getFeatures()]:
        lyr.deleteFeature(fid)
    f = QgsFeature(lyr.fields())
    f.setAttributes(["cuadrado"])
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in CUADRADO]))
    lyr.addFeature(f)


def largos():
    return sorted(round(f.geometry().length(), 6) for f in lyr.getFeatures())


def caja():
    r = QgsRectangle()
    for f in lyr.getFeatures():
        r.combineExtentWith(f.geometry().boundingBox())
    return tuple(round(v, 6) for v in (r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()))


from geocad.dibujo.plugin import DibujoCADPlugin
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr


def clic(x, y):
    mgr.point_clicked(QgsPointXY(x, y), False, False)


def designar_y_base(orden="SC"):
    mgr.run(orden)
    assert type(mgr.command).__name__ == "ScaleCommand", mgr.command
    clic(5, 0); mgr.enter()                     # designa el cuadrado
    clic(0, 0)                                  # punto base
    assert mgr.command.state == "factor", mgr.command.state


# ---- 0. nombres: SCALE, ESCALA, SC, ES -------------------------------------------------------
for orden in ("SCALE", "ESCALA", "SC", "ES"):
    mgr.run(orden)
    assert type(mgr.command).__name__ == "ScaleCommand", (orden, mgr.command)
    mgr.cancel()
print("ok SCALE, ESCALA, SC y ES abren ESCALA")

# ---- 1. factor escrito; un solo U -------------------------------------------------------------
armar()
pila = lyr.undoStack().index()
designar_y_base()
mgr.submit("2")
assert mgr.command is None
assert largos() == [80.0] and caja() == (0, 0, 20, 20), (largos(), caja())
assert lyr.undoStack().index() == pila + 1, "un solo paso de deshacer"
lyr.undoStack().undo()
assert largos() == [40.0] and caja() == (0, 0, 10, 10), "U vuelve atrás"
mgr.run("SC"); clic(5, 0); mgr.enter(); clic(0, 0); mgr.submit("2,5")      # coma decimal
assert caja() == (0, 0, 25, 25), caja()
print("ok factor escrito (2 y 2,5); un solo U")

# ---- 2. factor = distancia del clic a la base -------------------------------------------------
armar()
designar_y_base("ESCALA")
vista = mgr.command.preview_geoms(QgsPointXY(3, 0))
assert vista and abs(vista[0].length() - 120) < 1e-6, "vista previa con el factor del cursor"
clic(3, 0)
assert caja() == (0, 0, 30, 30), caja()
print("ok factor por distancia desde la base")

# ---- 3. Copia -------------------------------------------------------------------------------
armar()
designar_y_base()
mgr.submit("C")
assert mgr.command.copy and mgr.command.state == "factor"
mgr.submit("0.5")
assert largos() == [20.0, 40.0], largos()
print("ok Copia: el original queda y se agrega la escalada")

# ---- 4. Referencia escrita ---------------------------------------------------------------------
armar()
designar_y_base()
mgr.submit("R")
assert mgr.command.state == "ref"
mgr.submit("10")
assert mgr.command.state == "new"
mgr.submit("25")
assert caja() == (0, 0, 25, 25), caja()
print("ok Referencia 10 -> 25")

# ---- 5. Referencia con dos puntos, nueva con [Puntos] -------------------------------------------
armar()
designar_y_base()
mgr.submit("R")
clic(0, 0); clic(10, 0)                         # longitud de referencia = 10
assert mgr.command.state == "new" and abs(mgr.command.ref_len - 10) < 1e-9
mgr.submit("P")
assert mgr.command.state == "pts1"
clic(0, 0); clic(0, 5)                          # nueva = 5
assert caja() == (0, 0, 5, 5), caja()
print("ok Referencia con dos puntos y nueva con Puntos")

# ---- 6. Referencia con Intro (= 1) y nueva desde la base ----------------------------------------
armar()
designar_y_base()
mgr.submit("R"); mgr.enter()
assert mgr.command.state == "new" and mgr.command.ref_len == 1.0
clic(0, 4)                                      # nueva = 4 -> factor 4
assert caja() == (0, 0, 40, 40), caja()
print("ok Referencia <1> y nueva longitud desde la base")

# ---- 7. el valor debe ser positivo ---------------------------------------------------------------
armar()
designar_y_base()
mgr.submit("0")
assert mgr.command is not None and mgr.command.state == "factor", "0 se rechaza y sigue"
mgr.submit("-2")
assert mgr.command is not None and caja() == (0, 0, 10, 10), "negativo se rechaza"
mgr.submit("R"); mgr.submit("0")
assert mgr.command.state == "ref", "referencia 0 se rechaza"
mgr.cancel()
assert caja() == (0, 0, 10, 10)
print("ok 0 y negativos se rechazan; la orden sigue")

# ---- 8. Intro en el factor: sale sin cambiar nada ------------------------------------------------
armar()
designar_y_base()
mgr.enter()
assert mgr.command is None and caja() == (0, 0, 10, 10)
print("ok Intro en el factor sale sin cambios")

# ---- 9. textos y bloques: ALTURA y ESCALA_X/Y ----------------------------------------------------
iface.activeLayer.return_value = txt
t = QgsFeature(txt.fields())
t.setAttributes(["rótulo", 2.5, 30.0, 1.0, 1.0])
t.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(10, 10)))
txt.addFeature(t)
mgr.run("SC")
clic(10, 10); mgr.enter()
clic(0, 0); mgr.submit("3")
f = next(txt.getFeatures())
p = f.geometry().asPoint()
assert (round(p.x(), 6), round(p.y(), 6)) == (30, 30), p
assert abs(f["ALTURA"] - 7.5) < 1e-9 and abs(f["ESCALA_X"] - 3) < 1e-9 and abs(f["ESCALA_Y"] - 3) < 1e-9
assert abs(f["ROTACION"] - 30) < 1e-9, "el giro no cambia"
iface.activeLayer.return_value = lyr
print("ok textos: ALTURA ×3; bloques: ESCALA_X/Y ×3; ROTACION igual")

# ---- 10. botón: barra, banco y migración ---------------------------------------------------------
from geocad import botones
for nombre, bs in botones.DEFECTO["qgis"]:
    if "dibujo:rotate" in bs:
        assert bs[bs.index("dibujo:rotate") + 1] == "dibujo:scale", (nombre, bs)
banco = botones.TEMA_BANCO["qgis"]["Edición"]
assert banco[banco.index("dibujo:rotate") + 1] == "dibujo:scale", banco
crudo = {"categorias": [{"nombre": "Mía", "botones": ["dibujo:move", "dibujo:rotate", "dibujo:erase"]}],
         "migraciones": [m for m in botones.MIGRACIONES["qgis"] if m != "escala-qgis"]}
assert botones._migrar("qgis", crudo)
assert crudo["categorias"][0]["botones"] == ["dibujo:move", "dibujo:rotate", "dibujo:scale", "dibujo:erase"]
assert not botones._migrar("qgis", crudo), "una sola vez"
crudo = {"categorias": [{"nombre": "Sin girar", "botones": ["dibujo:move"]}],
         "migraciones": [m for m in botones.MIGRACIONES["qgis"] if m != "escala-qgis"]}
botones._migrar("qgis", crudo)
assert crudo["categorias"][0]["botones"] == ["dibujo:move"], "sin GIRA no agrega nada"
iconos = os.path.join(os.path.dirname(botones.__file__), "dibujo", "icons", "scale.svg")
assert os.path.isfile(iconos)
print("ok botón detrás de GIRA; migración «escala-qgis»; ícono")

plugin.unload()
print("TODO OK")
faulthandler.cancel_dump_traceback_later()
os._exit(0)
