"""Banco con el QGIS REAL (sin pantalla): el relleno de los polígonos en Yaguá Capas
(3.64.0), dibujado de verdad y medido en los píxeles.

Fernando, 03/11/2026: «cuando estamos trabajando con polígonos, ¿podríamos
agregar dos nuevos campos para configurar color de fondo y transparencia de los
polígonos?». Comprueba: sin relleno se dibuja como antes; el relleno y su
transparencia por capa CAD (columnas del panel, a la vista sólo con polígonos,
después del Grosor); por objeto con las listas de la barra (CAD_FILL y
CAD_FILLTR, vacío = PorCapa, Ninguno), lo próximo que se dibuje, los estados de
capa y que con una capa de líneas no aparece nada de esto.

Se corre como banco_capas_qgis.py (QGIS 4.2.2). Termina en «TODO OK».
"""
import os, sys, tempfile, faulthandler
faulthandler.dump_traceback_later(180, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import (QgsFeature, QgsGeometry, QgsMapRendererSequentialJob, QgsMapSettings,
                       QgsPointXY, QgsProject, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication, QMainWindow

iface = get_iface()
win = QMainWindow()
canvas = QgsMapCanvas(win)
canvas.setCanvasColor(QColor("white"))
win.setCentralWidget(canvas)
win.show()
iface.mainWindow.return_value = win
iface.mapCanvas.return_value = canvas
iface.addToolBar.side_effect = lambda nombre: win.addToolBar(nombre)
iface.addDockWidget.side_effect = lambda area, dock: win.addDockWidget(area, dock)
iface.removeDockWidget.side_effect = lambda dock: win.removeDockWidget(dock)

fallas = []


def comprobar(cond, texto):
    print(("ok   " if cond else "MAL  ") + texto)
    if not cond:
        fallas.append(texto)


def eventos():
    for _ in range(3):
        QApplication.processEvents()


def cuadrado(x):
    return QgsGeometry.fromPolygonXY([[QgsPointXY(x, 0), QgsPointXY(x + 10, 0), QgsPointXY(x + 10, 10),
                                       QgsPointXY(x, 10), QgsPointXY(x, 0)]])


def pixeles(layer, puntos=((5, 5), (25, 5))):
    """El color dibujado en el centro de cada cuadrado, sobre fondo blanco."""
    ms = QgsMapSettings()
    ms.setLayers([layer])
    ms.setDestinationCrs(layer.crs())
    ms.setExtent(QgsRectangle(-5, -5, 35, 15))
    ms.setOutputSize(QSize(400, 200))
    ms.setBackgroundColor(QColor("white"))
    job = QgsMapRendererSequentialJob(ms)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()
    salida = []
    for x, y in puntos:
        p = ms.mapToPixel().transform(x, y)
        c = QColor(img.pixel(int(p.x()), int(p.y())))
        salida.append((c.red(), c.green(), c.blue()))
    return salida


def cerca(rgb, esperado, tol=4):
    return all(abs(a - b) <= tol for a, b in zip(rgb, esperado))


poli = QgsVectorLayer("Polygon?crs=EPSG:3857&field=id:integer", "Lotes", "memory")
lineas = QgsVectorLayer("LineString?crs=EPSG:3857&field=id:integer", "Ejes", "memory")
QgsProject.instance().addMapLayers([poli, lineas])
for i in range(2):
    f = QgsFeature(poli.fields())
    f.setGeometry(cuadrado(20 * i))
    f.setAttributes([i])
    poli.dataProvider().addFeatures([f])
f = QgsFeature(lineas.fields())
f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(10, 10)]))
lineas.dataProvider().addFeatures([f])
fids = sorted(f.id() for f in poli.getFeatures())

from geocad.capas.plugin import LayerPropertiesPlugin
from geocad.capas.panel import C_FILL, C_FILLTR, C_LW
P = LayerPropertiesPlugin(iface)
P.initGui()
ctrl = P.ctrl
ctrl.attach(poli)
ctrl.ensure_initialized()
eventos()
P.toggle_manager(True)
eventos()
panel = P.dock.panel
t = panel.table
relleno, transp = P.props[3], P.props[4]

# ---- 1. sin relleno: como siempre ----------------------------------------------------
sym = poli.renderer().categories()[0].symbol()
comprobar(sym.symbolLayerCount() == 1, "sin relleno: el símbolo de siempre (sólo el borde)")
comprobar(all(cerca(c, (255, 255, 255)) for c in pixeles(poli)), "sin relleno: adentro se ve el fondo")
comprobar(not t.isColumnHidden(C_FILL) and not t.isColumnHidden(C_FILLTR), "polígonos: columnas Relleno y Transp.")
h = t.horizontalHeader()
comprobar(h.visualIndex(C_FILL) == h.visualIndex(C_LW) + 1 and h.visualIndex(C_FILLTR) == h.visualIndex(C_LW) + 2,
          "las columnas de relleno después del Grosor")
fila = panel._rows.index("0")
comprobar(t.item(fila, C_FILL).text() == "Ninguno" and t.item(fila, C_FILLTR).text() == "0",
          "capa 0: Ninguno, 0")
comprobar(relleno.isEnabled() and transp.isEnabled(), "polígonos: listas de relleno habilitadas")
comprobar(relleno.currentText() == "PorCapa" and transp.currentText() == "PorCapa", "lo próximo: PorCapa")

# ---- 2. por capa CAD -------------------------------------------------------------------
ctrl.set_props(["0"], fill={"aci": 1, "rgb": None}, filltr=50)
eventos()
a, b = pixeles(poli)
comprobar(cerca(a, (255, 128, 128)) and cerca(b, (255, 128, 128)), "capa 0 roja al 50 %%: %s %s" % (a, b))
fila = panel._rows.index("0")
comprobar(t.item(fila, C_FILL).text() == "1" and t.item(fila, C_FILLTR).text() == "50", "panel: 1, 50")
# 3.64.1: el cuadrito de la leyenda del panel Capas de QGIS con el mismo relleno (antes, azul)
items = [i for i in poli.renderer().legendSymbolItems() if i.label() == "0"]
img = items[0].symbol().asImage(QSize(40, 40))
c = img.pixelColor(20, 20)
comprobar(cerca((c.red(), c.green(), c.blue()), (255, 0, 0)) and 110 <= c.alpha() <= 145,
          "leyenda de la capa 0 roja al 50 %%: %s %s" % ((c.red(), c.green(), c.blue()), c.alpha()))
ctrl.set_props(["0"], transparency=50)                   # la de la capa sigue sumándose
eventos()
a, _b = pixeles(poli)
comprobar(cerca(a, (255, 191, 191), 6), "con la transparencia de capa al 50 %% encima: %s" % (a,))
ctrl.set_props(["0"], transparency=0)
eventos()

# ---- 3. por objeto, con la barra -------------------------------------------------------
poli.selectByIds([fids[1]])
eventos()
comprobar(relleno.currentText() == "PorCapa", "selección sin CAD_FILL: PorCapa")
relleno.apply("#0000ff")
eventos()
comprobar(poli.fields().indexOf("CAD_FILL") != -1, "se crea CAD_FILL")
a, b = pixeles(poli)
comprobar(cerca(a, (255, 128, 128)) and cerca(b, (128, 128, 255)), "el segundo azul al 50 %% (PorCapa): %s %s" % (a, b))
poli.selectByIds([fids[1]])
eventos()
transp.apply(0.0)
eventos()
comprobar(poli.fields().indexOf("CAD_FILLTR") != -1, "se crea CAD_FILLTR")
a, b = pixeles(poli)
comprobar(cerca(a, (255, 128, 128)) and cerca(b, (0, 0, 255)), "el segundo azul sin transparencia: %s %s" % (a, b))
poli.selectByIds([fids[1]])
eventos()
comprobar(relleno.currentText() == "#0000ff" or relleno.currentText() == "Azul", "la barra muestra el azul (%s)"
          % relleno.currentText())
comprobar(transp.currentText() == "0 %", "la barra muestra 0 %% (%s)" % transp.currentText())
relleno.apply("none")
eventos()
a, b = pixeles(poli)
comprobar(cerca(a, (255, 128, 128)) and cerca(b, (255, 255, 255)), "Ninguno: el segundo sin relleno: %s %s" % (a, b))
poli.selectByIds(fids)
eventos()
comprobar(relleno.currentIndex() == -1, "selección mixta: en blanco")
relleno.apply(None)
poli.selectByIds(fids)                                   # la barra quita la selección (3.60.1)
eventos()
transp.apply(None)
eventos()
a, b = pixeles(poli)
comprobar(cerca(a, (255, 128, 128)) and cerca(b, (255, 128, 128)), "PorCapa otra vez: %s %s" % (a, b))

# ---- 4. lo próximo que se dibuje -------------------------------------------------------
poli.removeSelection()
eventos()
relleno.apply("#00ff00")
transp.apply(30.0)
attrs = ctrl.new_feature_attrs(poli)
comprobar(attrs.get(poli.fields().indexOf("CAD_FILL")) == "#00ff00"
          and attrs.get(poli.fields().indexOf("CAD_FILLTR")) == 30.0, "objeto nuevo con verde al 30 %%: %s" % attrs)
comprobar(relleno.currentText() == "Verde" and transp.currentText() == "30 %", "la barra muestra lo actual")

# ---- 5. estados de capa ----------------------------------------------------------------
ctrl.save_state("A")
ctrl.set_props(["0"], fill=None, filltr=0)
ctrl.restore_state("A")
lay = ctrl.find("0")
comprobar(lay["fill"] == {"aci": 1, "rgb": None} and lay["filltr"] == 50, "los estados de capa guardan el relleno")

# ---- 6. capa de líneas: nada de relleno -------------------------------------------------
ctrl.attach(lineas)
ctrl.ensure_initialized()
eventos()
comprobar(t.isColumnHidden(C_FILL) and t.isColumnHidden(C_FILLTR), "líneas: sin columnas de relleno")
comprobar(not relleno.isEnabled() and not transp.isEnabled(), "líneas: listas de relleno apagadas")
comprobar(lineas.fields().indexOf("CAD_FILL") == -1 and not any(
    lineas.fields().field(i).name().startswith("CAD_FILL") for i in ctrl.new_feature_attrs(lineas)),
    "líneas: el objeto nuevo no lleva relleno")
ctrl.attach(poli)
eventos()
comprobar(not t.isColumnHidden(C_FILL) and relleno.isEnabled(), "de vuelta a los polígonos: columnas y listas")

P.unload()
print("TODO OK" if not fallas else "FALLAS: %s" % fallas)
sys.exit(1 if fallas else 0)
