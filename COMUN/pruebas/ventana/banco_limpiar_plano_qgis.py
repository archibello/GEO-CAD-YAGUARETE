"""Banco con el QGIS REAL (sin pantalla): LIMPIARPLANO en Dibujo (3.92.0).

Con el recorte del plano de 1958 (datos_limpiar_plano) como capa georreferenciada:
* con la imagen activa pide zonas de sello; dos esquinas hacen una zona (en
  píxeles del original), D la quita, se vuelve a marcar; Intro limpia;
* queda la copia _limpio.png en gris al doble (600 × 600) con su archivo de mundo
  en «<proyecto>_imagenes»; la capa la usa en el MISMO lugar; el resultado es el
  de la referencia aprobada (mismas tolerancias que IngeCAD); al dibujar el mapa
  el papel sale blanco y la tinta oscura, sin estirar el gris;
* el original no cambió; la marca del aspecto (si la tenía) se suelta;
* otra vez: «ya está limpia», vuelven sus zonas; O devuelve la capa al original;
* con otra capa activa, el clic elige la imagen; Esc cancela sin tocar nada.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_limpiar_plano_qgis.py <carpeta de trabajo> <carpeta datos_limpiar_plano>'
Termina en «TODO OK».
"""
import os, sys, tempfile, hashlib, shutil, faulthandler
faulthandler.dump_traceback_later(280, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
TRABAJO = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="banco-limpiar-")
DATOS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "datos_limpiar_plano")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import (QgsMapRendererCustomPainterJob, QgsMapSettings, QgsPointXY, QgsProject,
                       QgsRasterLayer, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtWidgets import QApplication, QMainWindow
from osgeo import gdal
import numpy as np

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
from geocad.dibujo import limpiar_plano_qgis as LQ
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


def leer_gris(ruta):
    ds = gdal.Open(ruta)
    return ds.GetRasterBand(1).ReadAsArray().astype(int)


def clic(x, y):
    mgr.point_clicked(QgsPointXY(x, y), False, False)


os.makedirs(TRABAJO, exist_ok=True)
D = os.path.join(TRABAJO, "escaneos"); os.makedirs(D)
plano = os.path.join(D, "plano.png")
shutil.copyfile(os.path.join(DATOS, "recorte_original.png"), plano)
PGW = "0.1\n0\n0\n-0.1\n5000.05\n7029.95\n"           # 300 px de 0,1: de (5000, 7000) a (5030, 7030)
open(os.path.join(D, "plano.pgw"), "w").write(PGW)
huella = md5(plano)
QgsProject.instance().setFileName(os.path.join(TRABAJO, "obra.qgz"))
capa = QgsRasterLayer(plano, "plano")
QgsProject.instance().addMapLayer(capa)
extension = capa.extent()
canvas.setLayers([capa, lyr])
canvas.setExtent(QgsRectangle(4995, 6995, 5035, 7035)); canvas.refresh(); QApplication.processEvents()
iface.activeLayer.return_value = capa
carpeta = os.path.join(TRABAJO, "obra_imagenes")
X0, Y0 = 1150, 1140
SELLO = (1215 - X0, 1195 - Y0, 1815 - X0, 1465 - Y0)                 # en píxeles del recorte (se recorta a 300)


def mapa(px, py):
    return 5000 + px * 0.1, 7030 - py * 0.1


def original_intacto():
    otros = sorted(set(os.listdir(D)) - {"plano.pgw", "plano.png"})
    if otros not in ([], ["plano.png.aux.xml"]):
        return False
    if otros and "<SRS" in open(os.path.join(D, otros[0])).read():
        return False
    return md5(plano) == huella and open(os.path.join(D, "plano.pgw")).read() == PGW


print("1. zonas de sello")
AQ.marcar(capa, {"lineas": "negativo"}, plano)        # como si tuviera aspecto
plugin.run_command("LIMPIARPLANO")
ver("con la imagen activa pide zonas", isinstance(mgr.command, LQ.LimpiarPlanoCommand)
    and mgr.command.capa is capa and not mgr.command.limpia)
clic(*mapa(10, 10)); clic(*mapa(40, 30))
ver("dos esquinas: una zona", mgr.command.zonas == [(10, 10, 40, 30)], repr(mgr.command.zonas))
pts = mgr.command.preview_geoms(None)
ver("se ven la zona y el marco", len(pts) == 2)
mgr.submit("D")
ver("D la quita", mgr.command.zonas == [])
clic(*mapa(SELLO[0], SELLO[1]))
p, cerrado, _t, _g = mgr.command.preview(QgsPointXY(*mapa(200, 200)))
ver("la zona en curso se ve", len(p) == 4 and cerrado)
clic(*mapa(400, 400))                                  # fuera: se recorta a la imagen
ver("la zona de sello, recortada", mgr.command.zonas == [(SELLO[0], SELLO[1], 300, 300)], repr(mgr.command.zonas))

print("2. Intro limpia")
mgr.submit("")
copia = os.path.join(carpeta, "plano_limpio.png")
ver("la capa usa la copia limpia", mgr.command is None and capa.source() == copia, capa.source())
ds = gdal.Open(copia)
ver("en gris, al doble", ds.RasterCount == 1 and (ds.RasterXSize, ds.RasterYSize) == (600, 600))
ver("en el mismo lugar", capa.extent().toString(6) == extension.toString(6), capa.extent().toString(3))
from geocad import limpieza as L
ref = L.gris_arreglo(AQ.abrir(os.path.join(DATOS, "recorte_limpio_2x.png"))).astype(int)
o = leer_gris(copia)
dif = np.abs(o - ref); adentro = dif[40:-40, 40:-40]
ver("el de la referencia aprobada", (adentro > 8).mean() <= 0.001 and adentro.mean() < 0.5 and (dif > 0).mean() <= 0.03,
    "interior %.3f %% distintos, media %.3f" % (100 * (adentro > 0).mean(), adentro.mean()))
ver("con su archivo de mundo", os.path.isfile(os.path.join(carpeta, "plano_limpio.pgw"))
    and abs(ds.GetGeoTransform()[1] - 0.05) < 1e-12)
ms = QgsMapSettings(); ms.setLayers([capa]); ms.setDestinationCrs(capa.crs())
ms.setExtent(QgsRectangle(5000, 7000, 5030, 7030)); ms.setOutputSize(QSize(600, 600))
img = QImage(QSize(600, 600), QImage.Format.Format_ARGB32); img.fill(QColor(255, 0, 0))
pt = QPainter(img); job = QgsMapRendererCustomPainterJob(ms, pt); job.renderSynchronously(); pt.end()
blanco = int(np.argmax(o.ravel() == 255)); oscuro = int(np.argmin(o.ravel()))
cb = img.pixelColor(blanco % 600, blanco // 600); co = img.pixelColor(oscuro % 600, oscuro // 600)
medio = int(np.argmin(np.abs(o.ravel() - 128))); cm = img.pixelColor(medio % 600, medio // 600)
ver("el papel blanco y la tinta oscura, sin estirar", cb.name() == "#ffffff" and co.red() == o.min()
    and abs(cm.red() - o.ravel()[medio]) <= 1, "%s %s; gris %d -> %d" % (cb.name(), co.name(),
                                                                         o.ravel()[medio], cm.red()))
ver("la marca, con su zona", LQ.leer(capa) == (plano, [(SELLO[0], SELLO[1], 300, 300)]))
ver("el aspecto se soltó", AQ.leer(capa) is None)
ver("el original, igual", original_intacto(), repr(sorted(os.listdir(D))))
ver("lo dice", "Plano limpio (600 × 600 píxeles, 1 zonas de sello" in historia())

print("3. otra vez: desde el original; O vuelve al original")
plugin.run_command("LIMPIARPLANO")
ver("ya está limpia: sus zonas", mgr.command.limpia and mgr.command.original == plano
    and mgr.command.zonas == [(SELLO[0], SELLO[1], 300, 300)] and "ya está limpia" in historia())
mgr.submit("O")
ver("O: la capa vuelve al original", mgr.command is None and capa.source() == plano and LQ.leer(capa) is None)
ver("en su lugar", capa.extent().toString(6) == extension.toString(6))
plugin.run_command("LIMPIARPLANO")
mgr.submit("O")
ver("sin limpiar, O no es una opción", mgr.command is not None and capa.source() == plano)
mgr.cancel()

print("4. con otra capa activa; Esc")
iface.activeLayer.return_value = lyr
plugin.run_command("LIMPIARPLANO")
ver("pide la imagen", isinstance(mgr.command, LQ.LimpiarPlanoCommand) and mgr.command.capa is None)
ver("resalta la imagen bajo el cursor", len(mgr.command.preview(QgsPointXY(5015, 7015))[0]) == 4)
clic(5015, 7015)
ver("el clic la elige", mgr.command.capa is capa)
mgr.cancel()
ver("Esc: nada", mgr.command is None and capa.source() == plano and original_intacto())

print("5. QGIS responde mientras limpia (3.92.1)")
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QProgressDialog
grande = os.path.join(D, "grande.png")
rec = QImage(plano).convertToFormat(QImage.Format.Format_RGB32)
img = QImage(1500, 1500, QImage.Format.Format_RGB32)
pt = QPainter(img)
for i in range(5):
    for j in range(5):
        pt.drawImage(300 * i, 300 * j, rec)
pt.end(); img.save(grande, "PNG")
open(os.path.join(D, "grande.pgw"), "w").write("0.1\n0\n0\n-0.1\n6000.05\n7149.95\n")
cg = QgsRasterLayer(grande, "grande"); QgsProject.instance().addMapLayer(cg)
iface.activeLayer.return_value = cg
latidos, vistos = [], []


def latido():
    latidos.append(1)
    for w in QApplication.topLevelWidgets() + mw.findChildren(QProgressDialog):
        if isinstance(w, QProgressDialog) and w.isVisible():
            vistos.append((w.value(), w.labelText()))
            break


reloj = QTimer(); reloj.timeout.connect(latido); reloj.start(100)
import time as _t
plugin.run_command("LIMPIARPLANO")
t0 = _t.monotonic(); mgr.submit(""); dur = _t.monotonic() - t0
reloj.stop()
ver("limpió el grande", cg.source().endswith("grande_limpio.png"), "%.1f s" % dur)
ver("QGIS siguió atendiendo (el reloj latió)", len(latidos) >= max(5, int(dur * 10 * 0.6)),
    "%d latidos en %.1f s" % (len(latidos), dur))
valores = [v for v, _x in vistos]
ver("la barra se vio y avanzó", len(vistos) >= 5 and valores == sorted(valores) and valores[-1] > valores[0],
    "%s ... %s" % (vistos[:1], vistos[-1:]))
ver("con la etapa, el % y los segundos", any("Limpiando el plano" in x and "%" in x and " s" in x for _v, x in vistos))
ver("la barra se cerró", not any(isinstance(w, QProgressDialog) and w.isVisible()
                                 for w in QApplication.topLevelWidgets() + mw.findChildren(QProgressDialog)))

plugin.unload()
print("FALLAS:", fallas if fallas else "ninguna")
if not fallas:
    print("TODO OK")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
