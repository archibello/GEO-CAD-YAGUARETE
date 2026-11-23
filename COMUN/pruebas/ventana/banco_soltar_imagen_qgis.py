"""Banco con el QGIS REAL (sin pantalla): SOLTARIMAGEN en Dibujo (3.88.0).

* GeoCAD registra su manejador de lo soltado en QGIS;
* soltar un archivo que no es imagen, o una imagen ya georreferenciada: QGIS
  hace lo de siempre; una imagen sin georreferencia arranca SOLTARIMAGEN;
* esquina y 2º punto con clics: todavía no hay capa; la imagen se PINTA
  semitransparente (se cuentan sus píxeles) y sigue al cursor;
* 30 escrito: queda una capa ráster, copia con archivo de mundo en
  «<proyecto>_imagenes»; sus esquinas caen donde se marcaron; el original, solo;
* Esc a mitad de camino: no queda nada y la vista previa se va;
* ancho escrito e Intro = 0°.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_soltar_imagen_qgis.py <carpeta de trabajo>'
Termina en «TODO OK».
"""
import os, sys, tempfile, math, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
TRABAJO = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="banco-soltar-")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import QgsPointXY, QgsProject, QgsRasterLayer, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtWidgets import QApplication, QMainWindow
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
iface.activeLayer.return_value = lyr
canvas.setDestinationCrs(lyr.crs())
canvas.setLayers([lyr])
mw.show()
canvas.setExtent(QgsRectangle(0, 0, 200, 160))
canvas.refresh()
QApplication.processEvents()

from geocad.dibujo.plugin import DibujoCADPlugin
from geocad.dibujo import soltar_imagen_qgis as SQ
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'OK' if ok else 'FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def clic(x, y):
    mgr.point_clicked(QgsPointXY(x, y), False, False)


def mover(x, y):
    mgr.mouse_moved(QgsPointXY(x, y), False, False)
    QApplication.processEvents()


def rasters():
    return [c for c in QgsProject.instance().mapLayers().values() if isinstance(c, QgsRasterLayer)]


def pintados():
    v = mgr.command.vista if mgr.command is not None else None
    if v is None or not v.isVisible():
        return 0
    r = v.boundingRect()
    im = QImage(int(r.width()) + 2, int(r.height()) + 2, QImage.Format.Format_ARGB32)
    im.fill(QColor(0, 0, 0))
    p = QPainter(im)
    v.paint(p)
    p.end()
    n = 0
    for y in range(0, im.height(), 2):
        for x in range(0, im.width(), 2):
            c = im.pixelColor(x, y)
            if c.red() > 100 and c.green() < 40 and c.blue() < 40:
                n += 1
    return n


os.makedirs(TRABAJO, exist_ok=True)
originales = os.path.join(TRABAJO, "originales")
os.makedirs(originales, exist_ok=True)
foto = os.path.join(originales, "fachada.png")
im = QImage(400, 200, QImage.Format.Format_RGB32); im.fill(QColor(255, 0, 0)); im.save(foto, "PNG")
otro = os.path.join(originales, "notas.txt")
open(otro, "w").write("x")
geo = os.path.join(originales, "orto.tif")
ds = gdal.GetDriverByName("GTiff").Create(geo, 10, 10, 1)
ds.SetGeoTransform((500000, 1, 0, 6100000, 0, -1)); ds = None
antes = sorted(os.listdir(originales))
proyecto = os.path.join(TRABAJO, "obra.qgz")
QgsProject.instance().setFileName(proyecto)

print("1. el manejador de lo soltado")
llamadas = iface.registerCustomDropHandler.call_args_list
manejador = llamadas[-1][0][0] if llamadas else None
ver("registrado", isinstance(manejador, SQ.ManejadorSoltar))
ver("otro archivo: lo de siempre", manejador.handleFileDrop(otro) is False and mgr.command is None)
ver("georreferenciada: lo de siempre", manejador.handleFileDrop(geo) is False and mgr.command is None)
ver("imagen: SOLTARIMAGEN", manejador.handleFileDrop(foto) is True
    and isinstance(mgr.command, SQ.SoltarImagenCommand) and mgr.command.tam == (400, 200))

print("2. esquina y ancho; la imagen se ve")
clic(20, 30)
mover(100, 30)
n1 = pintados()
ver("pinta la imagen mientras se estira", n1 > 300, f"{n1} píxeles")
clic(100, 30)                                   # ancho 80
ver("pide el giro, todavía sin capa", mgr.command is not None and abs(mgr.command.ancho - 80) < 1e-9
    and not rasters())
mover(20, 90)                                   # gira con el cursor: 90°
e = mgr.command.vista.esq
ver("gira con el cursor", len(e) == 4 and abs(e[1][0] - 20) < 1e-6 and abs(e[1][1] - 110) < 1e-6, repr(e[:2]))
ver("y se pinta girada", pintados() > 300)

print("3. 30 escrito: queda")
vista = mgr.command.vista
mgr.submit("30")
rs = rasters()
ver("una capa ráster", len(rs) == 1 and mgr.command is None, repr([r.name() for r in rs]))
ver("la vista previa se fue", vista.scene() is None)
if rs:
    capa = rs[0]
    carpeta = os.path.join(TRABAJO, "obra_imagenes")
    ver("copia en obra_imagenes", os.path.dirname(capa.source()) == carpeta
        and os.path.basename(capa.source()) == "fachada.png", capa.source())
    ver("con su archivo de mundo", os.path.isfile(os.path.join(carpeta, "fachada.pgw")))
    gt = gdal.Open(capa.source()).GetGeoTransform()
    a = math.radians(30)
    lado = 80 / 400

    def mapa(col, fila):
        return (gt[0] + gt[1] * col + gt[2] * fila, gt[3] + gt[4] * col + gt[5] * fila)
    ver("esquina inferior izquierda", all(abs(x - y) < 1e-6 for x, y in zip(mapa(0, 200), (20, 30))),
        repr(mapa(0, 200)))
    ver("ancho y giro", all(abs(x - y) < 1e-6 for x, y in
                            zip(mapa(400, 200), (20 + 80 * math.cos(a), 30 + 80 * math.sin(a)))))
    ver("sistema de coordenadas", capa.crs().authid() == "EPSG:32721", capa.crs().authid())
    ver("el original, solo", sorted(os.listdir(originales)) == antes, repr(os.listdir(originales)))

print("4. Esc a mitad de camino")
manejador.handleFileDrop(foto)
clic(0, 0); clic(50, 0)
vista = mgr.command.vista
mgr.cancel()
ver("no queda nada", len(rasters()) == 1 and mgr.command is None and vista.scene() is None)

print("5. ancho escrito e Intro = 0°")
manejador.handleFileDrop(foto)
clic(10, 10)
mgr.submit("40")
mgr.submit("")
rs = [r for r in rasters() if r.name() == "fachada_2"]
ver("otra copia, sin pisar", len(rs) == 1)
if rs:
    gt = gdal.Open(rs[0].source()).GetGeoTransform()
    ver("derecha, ancho 40", abs(gt[1] - 0.1) < 1e-12 and abs(gt[2]) < 1e-12 and abs(gt[4]) < 1e-12, repr(gt))

plugin.unload()
ver("al descargar se va el manejador", iface.unregisterCustomDropHandler.called)
print("FALLAS:", fallas if fallas else "ninguna")
if not fallas:
    print("TODO OK")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
