"""Banco con el QGIS REAL (sin pantalla): GEORREF de IngeCAD en QGIS (3.93.0).

Una imagen «pegada» en un lugar cualquiera (archivo de mundo de prueba) se lleva
a su lugar con pares de puntos marcados sobre el mapa:
* con la imagen activa pide «Punto en la imagen 1»; cada par (clic en la imagen,
  clic en el destino) guarda el píxel de QGIS y el destino; U quita el último;
  se ven el marco, las flechas, los números y, con los puntos suficientes, dónde
  quedaría;
* Intro abre la TABLA DE PUNTOS de verdad (3 filas, los 7 métodos, el botón del
  Georreferenciador de QGIS); Transformar con Helmert: una copia _georref con su
  archivo de mundo, la capa la usa, las esquinas caen donde dice el ajuste; los
  puntos en «<imagen>.points»; la original no cambia;
* «Archivo de mundo junto a la original» (con .bak del que había);
* Thin Plate Spline y Proyectiva rehacen la imagen en una copia (Proyectiva con
  los dos fondos: transparente y blanco);
* el botón «Abrir en el Georreferenciador de QGIS» guarda los puntos (esta
  ventana de prueba no tiene el Georreferenciador: avisa); Esc no cambia nada.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_georref_orden_qgis.py <carpeta de trabajo>'
Termina en «TODO OK».
"""
import os, sys, tempfile, hashlib, math, faulthandler
faulthandler.dump_traceback_later(280, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
TRABAJO = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="banco-georref-")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import QgsPointXY, QgsProject, QgsRasterLayer, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtWidgets import QApplication, QComboBox, QDialog, QMainWindow, QPushButton, QTableWidget
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
from geocad.dibujo import georref_qgis as GQ
from geocad import georref_cuentas as G
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


def clic(xy):
    mgr.point_clicked(QgsPointXY(*xy), False, False)


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


os.makedirs(TRABAJO, exist_ok=True)
D = os.path.join(TRABAJO, "planos"); os.makedirs(D)
plano = os.path.join(D, "plano.png")
im = QImage(400, 200, QImage.Format.Format_RGB32); im.fill(QColor(255, 255, 255))
p = QPainter(im)
p.fillRect(0, 0, 400, 6, QColor(0, 0, 0)); p.fillRect(0, 194, 400, 6, QColor(0, 0, 0))
p.fillRect(0, 0, 6, 200, QColor(0, 0, 0)); p.fillRect(394, 0, 6, 200, QColor(0, 0, 0))
p.fillRect(180, 80, 40, 40, QColor(200, 0, 0)); p.end()
im.save(plano, "PNG")
PGW = "0.1\n0\n0\n-0.1\n5000.05\n7019.95\n"            # «pegada»: 40 x 20 desde (5000, 7000)
open(os.path.join(D, "plano.pgw"), "w").write(PGW)
huella = md5(plano)
capa = QgsRasterLayer(plano, "plano")
QgsProject.instance().addMapLayer(capa)
canvas.setLayers([capa, lyr]); canvas.setExtent(QgsRectangle(4990, 6990, 5050, 7030)); canvas.refresh()
QApplication.processEvents()
iface.activeLayer.return_value = capa


def en_mapa(col, fila):                                 # donde está hoy (el .pgw de prueba)
    return 5000 + col * 0.1, 7020 - fila * 0.1


# el lugar verdadero: Helmert con escala 0,25, giro 10° y (1000, 2000)
A = math.radians(10)


def verdadero(col, fila):
    s = 0.25
    x, y = col * s, -fila * s
    return 1000 + x * math.cos(A) - y * math.sin(A), 2000 + x * math.sin(A) + y * math.cos(A)


print("1. pares sobre el mapa")
plugin.run_command("GEORREF")
cmd = mgr.command
ver("con la imagen activa pide el punto en la imagen", isinstance(cmd, GQ.GeorrefCommand) and cmd.capa is capa)
puntos = [(0, 0), (400, 0), (400, 200), (0, 200)]
for c, f in puntos[:3]:
    clic(en_mapa(c, f)); clic(verdadero(c, f))
ver("tres pares, con el píxel de QGIS", [(round(p["sx"], 6), round(p["sy"], 6)) for p in cmd._pares]
    == [(0, 0), (400, 0), (400, -200)], repr([(p["sx"], p["sy"]) for p in cmd._pares]))
mgr.submit("U")
ver("U quita el último", len(cmd._pares) == 2)
clic(en_mapa(400, 200)); clic(verdadero(400, 200))
geoms = cmd.preview_geoms(None)
ver("se ven el marco, 3 flechas y dónde quedaría", len(geoms) == 1 + 3 * 3 + 1, str(len(geoms)))
ver("con sus números", cmd.numeros is not None and [t for _p, t in cmd.numeros.textos] == ["1", "2", "3"])
clic(en_mapa(0, 200))
path = cmd.preview(QgsPointXY(1000, 1990))[0]
ver("la flecha en curso sigue al cursor", len(path) >= 2 and cerca((path[1].x(), path[1].y()), (1000, 1990)))
mgr.submit("U")
ver("U quita el punto sin destino", cmd._pendiente is None and len(cmd._pares) == 3)

print("2. la tabla de verdad y Transformar (Helmert)")
visto = {}


def manejar():
    d = QApplication.activeModalWidget()
    if not isinstance(d, QDialog):
        QTimer.singleShot(150, manejar); return
    visto["titulo"] = d.windowTitle()
    t = d.findChild(QTableWidget)
    visto["filas"] = t.rowCount() if t else -1
    combos = d.findChildren(QComboBox)
    visto["metodos"] = combos[0].count() if combos else 0
    visto["metodo"] = combos[0].currentText() if combos else ""
    visto["botones"] = [b.text() for b in d.findChildren(QPushButton)]
    next(b for b in d.findChildren(QPushButton) if b.text() == "Transformar").click()


QTimer.singleShot(200, manejar)
mgr.submit("")
ver("la tabla de puntos", visto.get("titulo", "").startswith("GEORREF — Tabla de puntos") and visto.get("filas") == 3
    and visto.get("metodos") == 7 and visto.get("metodo") == "Helmert", repr({k: visto.get(k) for k in ("filas", "metodos", "metodo")}))
ver("con el botón del Georreferenciador de QGIS", "Abrir en el Georreferenciador de QGIS" in visto.get("botones", []))
copia = os.path.join(D, "plano_georref.png")
ver("la capa usa la copia _georref", mgr.command is None and capa.source() == copia, capa.source())
gt = gdal.Open(copia).GetGeoTransform()


def esquina(gt, col, fila):
    return gt[0] + gt[1] * col + gt[2] * fila, gt[3] + gt[4] * col + gt[5] * fila


ver("las esquinas en su lugar verdadero", all(cerca(esquina(gt, c, f), verdadero(c, f), 1e-6) for c, f in puntos),
    repr(esquina(gt, 400, 200)) + " " + repr(verdadero(400, 200)))
ver("con su archivo de mundo y su sistema", os.path.isfile(os.path.join(D, "plano_georref.pgw"))
    and QgsRasterLayer(copia, "c").crs().authid() == "EPSG:32721", QgsRasterLayer(copia, "c").crs().authid())
pts = G.leer_points(plano + ".points")
ver("los puntos en plano.png.points", len(pts) == 3 and cerca((pts[0]["X"], pts[0]["Y"]), verdadero(0, 0)))
ver("la original, igual", md5(plano) == huella and open(os.path.join(D, "plano.pgw")).read() == PGW)
ver("lo dice", "Imagen ajustada con Helmert: 3 puntos" in historia() and "escala 0.25" in historia(), historia()[-300:])

print("3. archivo de mundo junto a la original")
otra = os.path.join(D, "otra.png"); im.save(otra, "PNG")
open(os.path.join(D, "otra.pgw"), "w").write(PGW)
c2 = QgsRasterLayer(otra, "otra"); QgsProject.instance().addMapLayer(c2)
iface.activeLayer.return_value = c2
respuesta = {}
GQ.tabla = lambda parent, tool: dict(respuesta)
plugin.run_command("GEORREF")
for c, f in puntos[:2]:
    clic(en_mapa(c, f)); clic(verdadero(c, f))
respuesta.update(accion="transformar", metodo="helmert", salida="mundo")
mgr.submit("")
gt2 = gdal.Open(otra).GetGeoTransform()
ver("el .pgw de la original, con .bak del anterior", open(os.path.join(D, "otra.pgw.bak")).read() == PGW
    and cerca(esquina(gt2, 400, 200), verdadero(400, 200), 1e-6) and c2.source() == otra)
ver("la capa se ve en su lugar", cerca((c2.extent().xMinimum(),), (min(verdadero(c, f)[0] for c, f in puntos),), 1e-3),
    c2.extent().toString(3))

print("4. Thin Plate Spline y Proyectiva rehacen la imagen")
for nombre, metodo, fondo, n in (("tps", "tps", "transparente", 4), ("pr", "proyectiva", "ambos", 4)):
    ruta = os.path.join(D, nombre + ".png"); im.save(ruta, "PNG")
    open(os.path.join(D, nombre + ".pgw"), "w").write(PGW)
    cx = QgsRasterLayer(ruta, nombre); QgsProject.instance().addMapLayer(cx)
    iface.activeLayer.return_value = cx
    plugin.run_command("GEORREF")
    for c, f in puntos[:n]:
        clic(en_mapa(c, f)); clic(verdadero(c, f))
    respuesta.clear(); respuesta.update(accion="transformar", metodo=metodo, fondo=fondo, remuestreo="lineal")
    mgr.submit("")
    nueva = cx.source()
    ver(f"{metodo}: la capa usa la imagen rehecha", nueva == os.path.join(D, nombre + "_georref.png"), nueva)
    ds = gdal.Open(nueva)
    ver(f"{metodo}: RGBA, transparente alrededor y en su lugar", ds is not None and ds.RasterCount == 4
        and abs(cx.extent().xMinimum() - min(verdadero(c, f)[0] for c, f in puntos)) < 0.5,
        cx.extent().toString(2))
    if fondo == "ambos":
        blanca = os.path.join(D, nombre + "_blanco_georref.png")
        ver("proyectiva: también la de fondo blanco", os.path.isfile(blanca)
            and os.path.isfile(os.path.join(D, nombre + "_blanco_georref.pgw")), repr(sorted(os.listdir(D))))

print("5. el Georreferenciador de QGIS y Esc")
iface.activeLayer.return_value = capa
c3 = os.path.join(D, "nat.png"); im.save(c3, "PNG"); open(os.path.join(D, "nat.pgw"), "w").write(PGW)
cn = QgsRasterLayer(c3, "nat"); QgsProject.instance().addMapLayer(cn); iface.activeLayer.return_value = cn
plugin.run_command("GEORREF")
for c, f in puntos[:2]:
    clic(en_mapa(c, f)); clic(verdadero(c, f))
respuesta.clear(); respuesta.update(accion="nativo")
mgr.submit("")
ver("guarda los puntos y avisa (sin Georreferenciador en esta ventana)", mgr.command is None
    and len(G.leer_points(c3 + ".points")) == 2 and "Abrir ráster" in historia() and cn.source() == c3)
plugin.run_command("GEORREF")
clic(en_mapa(0, 0)); clic(verdadero(0, 0))
mgr.cancel()
ver("Esc: la imagen como estaba", mgr.command is None and cn.source() == c3 and "GEORREF cancelado" in historia())

plugin.unload()
print("FALLAS:", fallas if fallas else "ninguna")
if not fallas:
    print("TODO OK")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
