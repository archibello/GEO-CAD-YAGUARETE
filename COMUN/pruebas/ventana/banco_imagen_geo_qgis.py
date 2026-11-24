"""Banco con el QGIS REAL (sin pantalla): INSERTARGEO y EXPORTARGEO en Dibujo (3.90.0).

* INSERTARGEO: una imagen con archivo de mundo y sin sistema entra en su lugar
  (sus esquinas donde dice el .pgw) con el sistema del mapa; un GeoTIFF en otro
  sistema entra y avisa que QGIS lo reproyecta; una imagen sin georreferencia no
  entra y avisa; cancelar la ventana no hace nada;
* EXPORTARGEO: con la imagen activa, «Guardar como» y queda la copia con su
  archivo de mundo y .aux.xml, la original igual; con otra capa activa, el clic
  dentro de la imagen (girada) la elige, afuera avisa, y el cursor encima la
  resalta con su marco; cancelar no escribe nada;
* GEORREF (el de IngeCAD desde la 3.93.0): ventana/banco_georref_orden_qgis.py;
  el Georreferenciador de QGIS de verdad: ventana/banco_georref_qgis.py.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_imagen_geo_qgis.py <carpeta de trabajo>'
Termina en «TODO OK».
"""
import os, sys, tempfile, math, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
TRABAJO = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="banco-geo-")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import (QgsCoordinateReferenceSystem, QgsPointXY, QgsProject, QgsRasterLayer,
                       QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtGui import QColor, QImage
from qgis.PyQt.QtWidgets import QApplication, QMainWindow
from osgeo import gdal, osr

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
canvas.setExtent(QgsRectangle(0, 0, 200, 160))
canvas.refresh()
QApplication.processEvents()

from geocad.dibujo.plugin import DibujoCADPlugin
from geocad.dibujo import imagen_geo_qgis as GQ
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


def rasters():
    return [c for c in QgsProject.instance().mapLayers().values() if isinstance(c, QgsRasterLayer)]


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


os.makedirs(TRABAJO, exist_ok=True)
D = os.path.join(TRABAJO, "imagenes"); os.makedirs(D, exist_ok=True)
plano = os.path.join(D, "plano.png")
im = QImage(400, 200, QImage.Format.Format_RGB32); im.fill(QColor(255, 0, 0)); im.save(plano, "PNG")
# girada 30°, ancho 80, esquina inferior izquierda en (20, 30)
a = math.radians(30); lado = 80 / 400
u = (lado * math.cos(a), lado * math.sin(a)); v = (-u[1], u[0])
sx, sy = 20 + v[0] * 200, 30 + v[1] * 200
open(os.path.join(D, "plano.pgw"), "w").write("".join("%.12f\n" % x for x in (
    u[0], u[1], -v[0], -v[1], sx + 0.5 * u[0] - 0.5 * v[0], sy + 0.5 * u[1] - 0.5 * v[1])))
suelta = os.path.join(D, "suelta.png"); im.save(suelta, "PNG")
orto = os.path.join(D, "orto.tif")
ds = gdal.GetDriverByName("GTiff").Create(orto, 20, 10, 1)
ds.SetGeoTransform((-57.0, 0.001, 0, -34.0, 0, -0.001))
s = osr.SpatialReference(); s.ImportFromEPSG(4326); ds.SetProjection(s.ExportToWkt()); ds = None
antes = sorted(os.listdir(D))

elegidos = []
GQ.pedir_archivo = lambda parent, titulo, filtro, inicio="": elegidos.pop(0) if elegidos else ""
guardar_como = []
GQ.pedir_guardar = lambda parent, titulo, sugerido, filtro: (guardar_como.append(sugerido),
                                                             guardados.pop(0) if guardados else "")[1]
guardados = []

print("1. INSERTARGEO")
elegidos[:] = [""]
plugin.run_command("INSERTARGEO")
ver("cancelar: nada", not rasters())
elegidos[:] = [suelta]
plugin.run_command("INSERTARGEO")
ver("sin georreferencia: no entra y avisa", not rasters() and "no tiene georreferencia" in historia())
elegidos[:] = [plano]
plugin.run_command("INSERTARGEO")
rs = rasters()
ver("con archivo de mundo: una capa", len(rs) == 1 and rs[0].source() == plano, repr([r.source() for r in rs]))
if rs:
    capa_plano = rs[0]
    gt = gdal.Open(plano).GetGeoTransform()
    ver("en su lugar: esquina inferior izquierda", cerca((gt[0] + gt[2] * 200, gt[3] + gt[5] * 200), (20, 30)))
    ver("el sistema del mapa", capa_plano.crs().authid() == "EPSG:32721" and "se toma el del mapa" in historia())
    ver("dice de dónde y dónde", "archivo de mundo plano.pgw" in historia() and "girada 30°" in historia())
    ex = canvas.extent()
    ver("zoom a la imagen", ex.contains(capa_plano.extent()) and ex.width() < 150, ex.toString())
elegidos[:] = [orto]
plugin.run_command("INSERTARGEO")
ver("GeoTIFF en otro sistema: entra y avisa", len(rasters()) == 2 and "reproyecta al vuelo" in historia())
ver("los originales, solos", sorted(os.listdir(D)) == antes, repr(os.listdir(D)))

print("2. EXPORTARGEO")
canvas.setLayers([capa_plano, lyr])
canvas.setExtent(QgsRectangle(-60, 0, 140, 160)); canvas.refresh(); QApplication.processEvents()
iface.activeLayer.return_value = capa_plano
destino = os.path.join(TRABAJO, "entrega"); os.makedirs(destino)
guardados[:] = [os.path.join(destino, "para_ingecad")]
plugin.run_command("EXPORTARGEO")
copia = os.path.join(destino, "para_ingecad.png")
ver("con la imagen activa: la copia", os.path.isfile(copia) and mgr.command is None)
ver("sugiere plano_georref.png al lado", guardar_como[-1:] == [os.path.join(D, "plano_georref.png")], repr(guardar_como))
ver("con su archivo de mundo, igual al de la original",
    os.path.isfile(os.path.join(destino, "para_ingecad.pgw"))
    and cerca(gdal.Open(copia).GetGeoTransform(), gdal.Open(plano).GetGeoTransform(), 1e-9))
ver("y su sistema", os.path.isfile(copia + ".aux.xml")
    and QgsRasterLayer(copia, "c").crs().authid() == "EPSG:32721")
ver("la original, igual", sorted(os.listdir(D)) == antes)
# con otra capa activa: clic adentro (girada), afuera, resaltado
iface.activeLayer.return_value = lyr
plugin.run_command("EXPORTARGEO")
ver("pide la imagen", mgr.command is not None and isinstance(mgr.command, GQ.ExportarGeoCommand))
pts, cerrado, _g, _e = mgr.command.preview(QgsPointXY(30, 40))
ver("el cursor encima la resalta", len(pts) == 4 and cerrado and cerca((pts[0].x(), pts[0].y()), (20, 30)))
ver("afuera, nada resaltado", mgr.command.preview(QgsPointXY(95, 31))[0] == [])
mgr.point_clicked(QgsPointXY(95, 31), False, False)          # al lado de la esquina, fuera de la girada
ver("clic afuera: avisa y sigue", mgr.command is not None and "no hay una imagen" in historia())
guardados[:] = [""]
mgr.point_clicked(QgsPointXY(30, 40), False, False)
ver("cancelar: no escribe nada", mgr.command is None and sorted(os.listdir(destino)) == sorted(
    ["para_ingecad.png", "para_ingecad.pgw", "para_ingecad.png.aux.xml"]) and "cancelado" in historia())
guardados[:] = [plano]
plugin.run_command("EXPORTARGEO")
mgr.point_clicked(QgsPointXY(30, 40), False, False)
ver("nunca sobre la original", "no puede ser la imagen original" in historia() and sorted(os.listdir(D)) == antes)

plugin.unload()
print("FALLAS:", fallas if fallas else "ninguna")
if not fallas:
    print("TODO OK")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
