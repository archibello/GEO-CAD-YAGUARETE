"""Banco con QGIS ENTERO (sin pantalla): el Georreferenciador de QGIS desde GEORREF.

Desde la 3.93.0 GEORREF es el de IngeCAD (banco_georref_orden_qgis.py); su tabla
de puntos tiene «Abrir en el Georreferenciador de QGIS» (decidido con Fernando):
* GEORREF con una imagen activa, dos pares marcados sobre el mapa y ese botón:
  se guardan los puntos en «<imagen>.points» y se abre el Georreferenciador de
  QGIS con la imagen y esos 2 puntos;
* abrir_georreferenciador con otra imagen (sin puntos) la reemplaza ahí;
* ninguna ventana queda esperando una respuesta.

QGIS se abre con un perfil de prueba (nunca el del usuario) y este archivo como
--code; el complemento GeoCAD se toma de GEOCAD_PATH:
    flatpak run --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=GEOCAD_PATH=<carpeta con geocad> --env=SALIDA=<carpeta>/salida.txt \\
      org.qgis.qgis --profiles-path <carpeta>/perfil --noplugins --nologo \\
      --code banco_georref_qgis.py
La salida queda en SALIDA y termina en «TODO OK».
"""
import os, sys
sys.path.insert(0, os.environ["GEOCAD_PATH"])
from qgis.utils import iface
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QColor, QImage
from qgis.PyQt.QtWidgets import QApplication, QTableView

SALIDA = os.environ["SALIDA"]
D = os.path.join(os.path.dirname(SALIDA), "georref"); os.makedirs(D, exist_ok=True)
out = open(SALIDA, "w")
fallas, modales = [], []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'OK' if ok else 'FALLA'} {extra}", file=out, flush=True)
    if not ok:
        fallas.append(nombre)


def vigilar():
    m = QApplication.activeModalWidget()
    if m is not None:
        modales.append(m.windowTitle())
        m.close()


reloj = QTimer(); reloj.timeout.connect(vigilar); reloj.start(200)
plano = os.path.join(D, "plano.png")
im = QImage(300, 200, QImage.Format.Format_RGB32); im.fill(QColor(200, 0, 0)); im.save(plano)
_viejos = ("mapX,mapY,sourceX,sourceY,enable,dX,dY,residual\n"
                                   "100,200,10,-10,1,0,0,0\n300,200,250,-10,1,0,0,0\n300,400,250,-150,1,0,0,0\n")
open(os.path.join(D, "plano.pgw"), "w").write("1\n0\n0\n-1\n0.5\n199.5\n")
otra = os.path.join(D, "otra.png"); im.save(otra)
estado = {}


def georref():
    from geocad.dibujo import imagen_geo_qgis as GQ
    w = GQ.ventana_georref()
    if w is None:
        return None, None, 0
    c = w.findChild(QgsMapCanvas, "georefCanvas")
    filas = max((t.model().rowCount() for t in w.findChildren(QTableView) if t.model() is not None), default=0)
    return w, [l.source() for l in c.layers()] if c else None, filas


def paso1():
    from geocad.dibujo.plugin import DibujoCADPlugin
    from geocad.dibujo import imagen_geo_qgis as GQ
    from geocad.dibujo import georref_qgis as GR
    from qgis.core import QgsPointXY
    estado["GQ"] = GQ
    plugin = estado["plugin"] = DibujoCADPlugin(iface)
    plugin.initGui()
    capa = QgsRasterLayer(plano, "plano")
    QgsProject.instance().addMapLayer(capa)
    iface.setActiveLayer(capa)
    print("1. GEORREF, dos pares y «Abrir en el Georreferenciador de QGIS»", file=out, flush=True)
    plugin.run_command("GEORREF")
    mgr = plugin.mgr
    ver("GEORREF de IngeCAD", isinstance(mgr.command, GR.GeorrefCommand) and mgr.command.capa is capa)
    for a, b in (((10, 190), (100, 200)), ((250, 50), (300, 400))):
        mgr.point_clicked(QgsPointXY(*a), False, False)
        mgr.point_clicked(QgsPointXY(*b), False, False)
    GR.tabla = lambda parent, tool: {"accion": "nativo"}
    mgr.submit("")
    QTimer.singleShot(2500, paso2)


def paso2():
    w, capas, filas = georref()
    plugin = estado["plugin"]
    ver("el Georreferenciador abierto", w is not None and w.isVisible())
    ver("con la imagen", capas == [plano], repr(capas))
    ver("y los 2 puntos marcados", filas == 2, str(filas))
    ver("lo dice", "abierta en el Georreferenciador de QGIS con sus 2 puntos" in plugin.cmdline.history.toPlainText())
    print("2. otra imagen, sin puntos", file=out, flush=True)
    falla = estado["GQ"].abrir_georreferenciador(iface, otra)
    ver("se abre", falla == "", falla)
    QTimer.singleShot(2500, paso3)


def paso3():
    w, capas, filas = georref()
    ver("la otra imagen, sin puntos", capas == [otra] and filas == 0, "%r %s" % (capas, filas))
    ver("ninguna ventana esperando", not modales, repr(modales))
    try:
        estado["plugin"].unload()
    except Exception as e:  # noqa: BLE001
        ver("descargar", False, repr(e))
    print("FALLAS:", fallas if fallas else "ninguna", file=out, flush=True)
    if not fallas:
        print("TODO OK", file=out, flush=True)
    out.close()
    os._exit(0)


QTimer.singleShot(3000, paso1)
