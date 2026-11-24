"""Banco con el QGIS REAL (sin pantalla): ASPECTOIMAGEN en Dibujo (3.91.0).

* la ventana de verdad (PyQt6 de QGIS) se abre con la imagen activa; se mueve un
  control, la vista previa se pinta, y Aceptar;
* queda la copia PNG con su archivo de mundo en «<proyecto>_imagenes»; la capa la
  usa (mismo nombre), en el mismo lugar; al dibujar el mapa, el papel se ve
  transparente y la línea negra; el original no cambió (sus bytes);
* volver a abrir: la ventana recibe lo guardado y se rehace desde el original;
* «Entregar imagen final»: copia opaca (_final); «Volver al original»: la capa
  vuelve a su archivo y se quita la marca; Cancelar no hace nada;
* con otra capa activa: el cursor encima resalta la imagen y el clic la elige.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_aspecto_qgis.py <carpeta de trabajo>'
Termina en «TODO OK».
"""
import os, sys, tempfile, hashlib, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
TRABAJO = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="banco-aspecto-")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import (QgsMapRendererCustomPainterJob, QgsMapSettings, QgsPointXY, QgsProject,
                       QgsRasterLayer, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtCore import QSize, QTimer
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtWidgets import QApplication, QDialog, QMainWindow, QPushButton, QSlider
from osgeo import gdal

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
canvas.setDestinationCrs(lyr.crs())
mw.show()

from geocad.dibujo.plugin import DibujoCADPlugin
from geocad.dibujo import aspecto_qgis as AQ
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'OK' if ok else 'FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def historia():
    return plugin.cmdline.history.toPlainText()


def md5(ruta):
    return hashlib.md5(open(ruta, "rb").read()).hexdigest()


def original_intacto():
    """La imagen y su .pgw, iguales; lo único nuevo que puede haber es el .aux.xml de
    estadísticas que QGIS mismo deja al lado de toda imagen que dibuja (medido sin
    GeoCAD), sin sistema de coordenadas."""
    otros = sorted(set(os.listdir(D)) - {"plano.pgw", "plano.png"})
    if otros not in ([], ["plano.png.aux.xml"]):
        return False
    if otros:
        aux = open(os.path.join(D, otros[0])).read()
        if "<SRS" in aux or "STATISTICS_" not in aux:
            return False
    return (md5(plano) == huella
            and open(os.path.join(D, "plano.pgw")).read() == "0.5\n0\n0\n-0.5\n1000.25\n2049.75\n")


os.makedirs(TRABAJO, exist_ok=True)
D = os.path.join(TRABAJO, "escaneos"); os.makedirs(D)
plano = os.path.join(D, "plano.png")
im = QImage(200, 100, QImage.Format.Format_RGB32); im.fill(QColor(250, 245, 230))   # papel amarillento
p = QPainter(im); p.fillRect(10, 48, 180, 4, QColor(0, 0, 0)); p.end()           # una línea negra
im.save(plano, "PNG")
open(os.path.join(D, "plano.pgw"), "w").write("0.5\n0\n0\n-0.5\n1000.25\n2049.75\n")  # 100 x 50 desde (1000, 2000)
huella = md5(plano)
QgsProject.instance().setFileName(os.path.join(TRABAJO, "obra.qgz"))
capa = QgsRasterLayer(plano, "plano")
QgsProject.instance().addMapLayer(capa)
canvas.setLayers([capa, lyr])
canvas.setExtent(QgsRectangle(990, 1990, 1110, 2060)); canvas.refresh(); QApplication.processEvents()
iface.activeLayer.return_value = capa
carpeta = os.path.join(TRABAJO, "obra_imagenes")


def pixel_mapa(x, y):
    """El color del mapa dibujado sólo con la capa, sobre fondo rojo, en (x, y)."""
    ms = QgsMapSettings()
    ms.setLayers([capa]); ms.setDestinationCrs(capa.crs())
    ms.setExtent(QgsRectangle(1000, 2000, 1100, 2050)); ms.setOutputSize(QSize(200, 100))
    ms.setBackgroundColor(QColor(255, 0, 0))
    img = QImage(QSize(200, 100), QImage.Format.Format_ARGB32); img.fill(QColor(255, 0, 0))
    pt = QPainter(img); job = QgsMapRendererCustomPainterJob(ms, pt); job.renderSynchronously(); pt.end()
    return img.pixelColor(int((x - 1000) * 2), int((2050 - y) * 2))


print("1. la ventana de verdad")
visto = {}


def manejar():
    d = QApplication.activeModalWidget()
    if not isinstance(d, QDialog):
        QTimer.singleShot(200, manejar); return
    visto["titulo"] = d.windowTitle()
    sl = [s for s in d.findChildren(QSlider) if s.maximum() == 80]       # «Blanco que se borra»
    if sl:
        sl[0].setValue(30)
    QApplication.processEvents()
    visto["previa"] = not d.previa.base.pixmap().isNull()
    visto["botones"] = sorted(b.text() for b in d.findChildren(QPushButton))
    next(b for b in d.findChildren(QPushButton) if b.text() == "Aceptar").click()


QTimer.singleShot(300, manejar)
plugin.run_command("ASPECTOIMAGEN")
ver("se abrió", visto.get("titulo", "").startswith("Aspecto de la imagen"), visto.get("titulo", ""))
ver("pinta la vista previa", visto.get("previa") is True)
ver("los botones de IngeCAD", visto.get("botones") == sorted(
    ["Volver al original", "Valores iniciales", "Entregar imagen final...", "Aceptar", "Cancelar", "Ver todo", "1:1", ""]),
    repr(visto.get("botones")))
copia = os.path.join(carpeta, "plano_aspecto.png")
ver("la capa usa la copia", capa.source() == copia and capa.name() == "plano", capa.source())
ver("con su archivo de mundo", os.path.isfile(os.path.join(carpeta, "plano_aspecto.pgw"))
    and gdal.Open(copia).GetGeoTransform() == gdal.Open(plano).GetGeoTransform())
ver("RGBA", capa.dataProvider().bandCount() == 4)
papel, linea = pixel_mapa(1010, 2040), pixel_mapa(1050, 2025)
ver("el papel se ve transparente", papel.red() == 255 and papel.green() < 10, papel.name())
ver("la línea, negra", linea.red() < 30 and linea.green() < 30, linea.name())
ver("blanco que se borra 30 guardado", (AQ.leer(capa) or ({}, ""))[0].get("blanco") == 30
    and AQ.leer(capa)[1] == plano)
ver("el original, igual", original_intacto(), repr(sorted(os.listdir(D))))
ver("lo dice", "Aspecto de la imagen: fondo transparente (blanco que se borra 30 %)" in historia())

print("2. otra vez: desde el original, con lo guardado")
pedidos = []
real = AQ.ventana


def falsa(respuesta):
    def v(parent, original, valores, con_aspecto):
        pedidos.append((original, valores, con_aspecto))
        return respuesta
    return v


AQ.ventana = falsa({"accion": "aceptar", "valores": {"lineas": "negativo"}})
plugin.run_command("ASPECTOIMAGEN")
ver("recibe lo guardado y el original", pedidos[-1][0] == plano and pedidos[-1][1]["blanco"] == 30
    and pedidos[-1][2] is True, repr(pedidos[-1][:1]))
ver("otra copia, sin pisar", capa.source() == os.path.join(carpeta, "plano_aspecto_2.png"))
linea = pixel_mapa(1050, 2025)
ver("negativo: la línea blanca", linea.red() > 240 and linea.green() > 240, linea.name())

print("3. imagen final, Cancelar y Volver al original")
AQ.ventana = falsa({"accion": "final", "valores": {}})
plugin.run_command("ASPECTOIMAGEN")
ver("copia final opaca", capa.source() == os.path.join(carpeta, "plano_final.png")
    and capa.dataProvider().bandCount() == 3 and "Imagen final" in historia())
papel = pixel_mapa(1010, 2040)
ver("sobre papel blanco", papel.red() == 255 and papel.green() == 255, papel.name())
fuente = capa.source()
AQ.ventana = falsa(None)
plugin.run_command("ASPECTOIMAGEN")
ver("Cancelar: nada", capa.source() == fuente and "cancelado" in historia())
AQ.ventana = falsa({"accion": "original", "valores": {}})
plugin.run_command("ASPECTOIMAGEN")
ver("vuelve al original", capa.source() == plano and AQ.leer(capa) is None)
papel = pixel_mapa(1010, 2040)
ver("y se ve como antes", papel.red() == 250 and papel.green() == 245, papel.name())
plugin.run_command("ASPECTOIMAGEN")
ver("ya en el original: lo dice", "ya usa su archivo original" in historia())
ver("el original, siempre igual", original_intacto())

print("4. con otra capa activa: resaltado y clic")
iface.activeLayer.return_value = lyr
AQ.ventana = falsa(None)
plugin.run_command("ASPECTOIMAGEN")
ver("pide la imagen", isinstance(mgr.command, AQ.AspectoImagenCommand))
pts = mgr.command.preview(QgsPointXY(1050, 2025))[0]
ver("la resalta", len(pts) == 4)
n = len(pedidos)
mgr.point_clicked(QgsPointXY(1050, 2025), False, False)
ver("el clic la elige", len(pedidos) == n + 1 and mgr.command is None)
AQ.ventana = real

plugin.unload()
print("FALLAS:", fallas if fallas else "ninguna")
if not fallas:
    print("TODO OK")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
