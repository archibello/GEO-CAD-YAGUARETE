"""Banco con el QGIS REAL (sin pantalla): PEGARIMAGEN en Dibujo (3.89.0).

* el Ctrl+V del mapa (un QShortcut, como el de QGIS) queda enganchado;
* sin imagen en el portapapeles: PEGARIMAGEN avisa y Ctrl+V no hace nada nuestro;
* una captura (imagen suelta) y Ctrl+V: arranca PEGARIMAGEN; esquina y 2º punto
  con clics; la imagen se PINTA semitransparente y sigue al cursor; queda una
  capa ráster, PNG con archivo de mundo en «<proyecto>_imagenes»; sus esquinas
  caen donde se marcaron (girada como se marcó);
* Esc a mitad de camino: no queda nada y la vista previa se va;
* un archivo copiado en el explorador y el ancho escrito: una copia derecha, el
  original solo; un archivo ya georreferenciado entra en su lugar, sin copia;
* Ctrl+V con la línea de comandos vacía arranca PEGARIMAGEN;
* al descargar, Ctrl+V vuelve a ser el de QGIS.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_pegar_imagen_qgis.py <carpeta de trabajo>'
Termina en «TODO OK».
"""
import os, sys, tempfile, math, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
TRABAJO = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="banco-pegar-")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import QgsPointXY, QgsProject, QgsRasterLayer, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtCore import QMimeData, Qt, QUrl
from qgis.PyQt.QtGui import QColor, QImage, QKeySequence, QPainter, QShortcut
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QLineEdit, QMainWindow
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
# el Ctrl+V del mapa de QGIS es un QShortcut del lienzo
atajo_qgis = QShortcut(QKeySequence("Ctrl+V"), canvas)
pegados_qgis = []
atajo_qgis.activated.connect(lambda: pegados_qgis.append(1))

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
from geocad.dibujo import pegar_imagen_qgis as PQ
plugin = DibujoCADPlugin(iface)
plugin.initGui()
mgr = plugin.mgr
board = QApplication.clipboard()
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


def ctrl_v():
    atajo_qgis.activated.emit()
    QApplication.processEvents()


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


def historia():
    return plugin.cmdline.history.toPlainText()


os.makedirs(TRABAJO, exist_ok=True)
originales = os.path.join(TRABAJO, "originales")
os.makedirs(originales, exist_ok=True)
foto = os.path.join(originales, "fachada.png")
im = QImage(400, 200, QImage.Format.Format_RGB32); im.fill(QColor(255, 0, 0)); im.save(foto, "PNG")
geo = os.path.join(originales, "orto.tif")
ds = gdal.GetDriverByName("GTiff").Create(geo, 10, 10, 1)
ds.SetGeoTransform((500000, 1, 0, 6100000, 0, -1)); ds = None
antes = sorted(os.listdir(originales))
proyecto = os.path.join(TRABAJO, "obra.qgz")
QgsProject.instance().setFileName(proyecto)
carpeta = os.path.join(TRABAJO, "obra_imagenes")

print("1. Ctrl+V enganchado; sin imagen no hace nada nuestro")
ver("el atajo del mapa", PQ._ctrl_v and PQ._ctrl_v[0].atajos == [atajo_qgis])
board.setText("hola")
ctrl_v()
ver("texto: Ctrl+V de QGIS, sin PEGARIMAGEN", mgr.command is None and len(pegados_qgis) == 1)
plugin.run_command("PEGARIMAGEN")
ver("PEGARIMAGEN avisa", mgr.command is None and "no tiene una imagen" in historia())

print("2. una captura: Ctrl+V y dos clics")
captura = QImage(400, 200, QImage.Format.Format_RGB32); captura.fill(QColor(255, 0, 0))
board.setImage(captura)
ctrl_v()
ver("arranca PEGARIMAGEN", isinstance(mgr.command, PQ.PegarImagenCommand)
    and (mgr.command.copiada.ancho, mgr.command.copiada.alto) == (400, 200)
    and mgr.command.copiada.archivo is None)
clic(20, 30)
a = math.radians(30)
p2 = (20 + 80 * math.cos(a), 30 + 80 * math.sin(a))
mover(*p2)
n1 = pintados()
ver("pinta la imagen mientras sigue al cursor", n1 > 300, f"{n1} píxeles")
e = mgr.command.vista.esq
ver("girada como el borde de abajo", len(e) == 4 and abs(e[1][0] - p2[0]) < 1e-6
    and abs(e[1][1] - p2[1]) < 1e-6 and not rasters(), repr(e[:2]))
vista = mgr.command.vista
clic(*p2)
rs = rasters()
ver("una capa ráster", len(rs) == 1 and mgr.command is None, repr([r.name() for r in rs]))
ver("la vista previa se fue", vista.scene() is None)
if rs:
    capa = rs[0]
    nombre = os.path.basename(capa.source())
    ver("captura PNG en obra_imagenes", os.path.dirname(capa.source()) == carpeta
        and nombre.startswith("captura_") and nombre.endswith(".png"), capa.source())
    ver("con su archivo de mundo", os.path.isfile(capa.source()[:-4] + ".pgw"))
    gt = gdal.Open(capa.source()).GetGeoTransform()

    def mapa(col, fila):
        return (gt[0] + gt[1] * col + gt[2] * fila, gt[3] + gt[4] * col + gt[5] * fila)
    ver("esquina inferior izquierda", all(abs(x - y) < 1e-6 for x, y in zip(mapa(0, 200), (20, 30))),
        repr(mapa(0, 200)))
    ver("esquina inferior derecha", all(abs(x - y) < 1e-6 for x, y in zip(mapa(400, 200), p2)))
    ver("sistema de coordenadas", capa.crs().authid() == "EPSG:32721", capa.crs().authid())
    ver("dice dónde quedó", "Imagen pegada" in historia() and "captura guardada" in historia())

print("3. Esc a mitad de camino")
ctrl_v()
clic(0, 0); mover(50, 0)
vista = mgr.command.vista
mgr.cancel()
ver("no queda nada", len(rasters()) == 1 and mgr.command is None and vista.scene() is None)

print("4. un archivo copiado y el ancho escrito")
datos = QMimeData(); datos.setUrls([QUrl.fromLocalFile(foto)])
board.setMimeData(datos)
ctrl_v()
ver("arranca con el archivo", isinstance(mgr.command, PQ.PegarImagenCommand)
    and mgr.command.copiada.archivo == foto)
clic(10, 10)
mgr.submit("40")
rs = [r for r in rasters() if r.name() == "fachada"]
ver("una copia en obra_imagenes", len(rs) == 1 and os.path.dirname(rs[0].source()) == carpeta)
if rs:
    gt = gdal.Open(rs[0].source()).GetGeoTransform()
    ver("derecha, ancho 40", abs(gt[1] - 0.1) < 1e-12 and abs(gt[2]) < 1e-12 and abs(gt[4]) < 1e-12, repr(gt))
ver("el original, solo", sorted(os.listdir(originales)) == antes, repr(os.listdir(originales)))
# «x,y» escrito es un punto, no un ancho
board.clear()
datos2 = QMimeData(); datos2.setUrls([QUrl.fromLocalFile(foto)]); board.setMimeData(datos2)
ctrl_v(); clic(0, 0); mgr.submit("20,0")
rs = [r for r in rasters() if r.name() == "fachada_2"]
ver("«20,0» es el 2º punto", len(rs) == 1
    and abs(gdal.Open(rs[0].source()).GetGeoTransform()[1] - 0.05) < 1e-12 if rs else False)

print("5. un archivo ya georreferenciado")
datos3 = QMimeData(); datos3.setUrls([QUrl.fromLocalFile(geo)]); board.setMimeData(datos3)
ctrl_v()
rs = [r for r in rasters() if r.source() == geo]
ver("entra en su lugar, sin copia", len(rs) == 1 and mgr.command is None
    and not os.path.exists(os.path.join(carpeta, "orto.tif")))

print("6. Ctrl+V con la línea de comandos vacía")
entrada = plugin.cmdline.findChild(QLineEdit, PQ.LINEA_COMANDOS)
board.setImage(captura)
mw.activateWindow(); entrada.setFocus(); QApplication.processEvents()
if QApplication.focusWidget() is entrada:
    QTest.keyClick(entrada, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    ver("arranca PEGARIMAGEN", isinstance(mgr.command, PQ.PegarImagenCommand))
    mgr.cancel()
else:
    filtro = PQ._ctrl_v[0].filtro
    ver("filtro instalado (sin foco en esta pantalla)", filtro is not None, repr(QApplication.focusWidget()))

plugin.unload()
n = len(pegados_qgis)
ctrl_v()
ver("al descargar, Ctrl+V es el de QGIS", mgr.command is None and not PQ._ctrl_v and len(pegados_qgis) == n + 1)
print("FALLAS:", fallas if fallas else "ninguna")
if not fallas:
    print("TODO OK")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
