"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
«Enviar a Google Earth...» (GEOEARTHOPEN, 3.81.0).

Un dibujo en POSGAR 2007 faja 7 con una imagen en la capa IMAGEN, dos lotes
en LOTES (uno lejos) y una calle en CALLES. Con la ventana de verdad:
* sin selección, «Los elementos seleccionados (0)» está apagado y viene
  marcado «Lo que se ve en pantalla»; la lista ofrece sólo las capas con
  objetos; el botón dice «Enviar».
* Capas IMAGEN + LOTES: el KMZ tiene la imagen y los dos lotes, una carpeta
  por capa, y se abre (openUrl) en Google Earth; la calle no va.
* Lo que se ve (zoom al lote cercano): no va el lote lejano.
* Con un lote seleccionado viene marcado «Los elementos seleccionados (1)».
* Avance en 3 etapas: Preparando, Escribiendo, Guardando.

Uso (PySide6, ezdxf, numpy, pyshp, pyproj, pillow):
    python banco_enviar_ge_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, zipfile, faulthandler
faulthandler.dump_traceback_later(300, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
import xml.etree.ElementTree as ET
from pathlib import Path
from importlib import import_module
from PIL import Image
from pyproj import Transformer
from PySide6 import QtGui, QtWidgets
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
from core.georef import Georef, write_georef
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
ENV = import_module("ingecad_plugin_geocad.googleearth_enviar")
GEC = import_module("ingecad_plugin_geocad.googleearth_cmd")
AV = import_module("ingecad_plugin_geocad.avance")
from views.main_window import MainWindow
fallas = []
N = "{http://www.opengis.net/kml/2.2}"


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


# lo que se abre en Google Earth y las etapas de la ventanita de avance
abiertos = []
QtGui.QDesktopServices.openUrl = staticmethod(lambda url: (abiertos.append(url.toLocalFile()), True)[1])
etapas = []
_etapa = AV.Avance.etapa
AV.Avance.etapa = lambda self, texto, *a, **k: (etapas.append(f"{self.numero + 1}/{self.etapas} {texto}"),
                                                _etapa(self, texto, *a, **k))[1]

# la ventana de Enviar: se mira y se elige como lo haría el usuario
vista = {}
eleccion = {}


def exec_falso(self):
    if self.windowTitle() != "Enviar a Google Earth":
        return 0
    vista.update(sel=(self.sel.isEnabled(), self.sel.isChecked(), self.sel.text()),
                 pantalla=self.pantalla.isChecked(),
                 capas=[self.lista.item(i).text() for i in range(self.lista.count())],
                 boton=[b.text() for b in self.findChildren(QtWidgets.QPushButton)])
    que = eleccion.get("que")
    if que == "capas":
        from PySide6.QtCore import Qt
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            it.setCheckState(Qt.Checked if it.text() in eleccion["capas"] else Qt.Unchecked)
    elif que == "pantalla":
        self.pantalla.setChecked(True)
    self.accept()
    return int(self.result())


QtWidgets.QDialog.exec = exec_falso

win = MainWindow()
win.new_document("m")
doc = win.document.doc
SIS7 = "EPSG:5349"
write_georef(doc, Georef(crs=SIS7))
X0, Y0 = Transformer.from_crs("EPSG:4326", SIS7, always_xy=True).transform(-55.896, -27.367)
tmp = Path(tempfile.mkdtemp(prefix="banco-img-"))
Image.new("RGB", (40, 20), (200, 30, 30)).save(tmp / "foto.png")
msp = doc.modelspace()
for capa in ("IMAGEN", "LOTES", "CALLES", "VACIA"):
    doc.layers.add(capa)
idef = doc.add_image_def(filename=str(tmp / "foto.png"), size_in_pixel=(40, 20))
img = msp.add_image(idef, insert=(X0, Y0), size_in_units=(40, 20), dxfattribs={"layer": "IMAGEN"})
img.dxf.u_pixel = (1.0, 0.0, 0.0); img.dxf.v_pixel = (0.0, 1.0, 0.0)
lote1 = msp.add_lwpolyline([(X0, Y0), (X0 + 30, Y0), (X0 + 30, Y0 + 15), (X0, Y0 + 15)],
                           close=True, dxfattribs={"layer": "LOTES"})
lote2 = msp.add_lwpolyline([(X0 + 3000, Y0), (X0 + 3030, Y0), (X0 + 3030, Y0 + 15)],
                           close=True, dxfattribs={"layer": "LOTES"})
msp.add_line((X0 - 50, Y0 - 5), (X0 + 80, Y0 - 5), dxfattribs={"layer": "CALLES"})
win.show(); app.processEvents()
win.viewport.view.zoom_extents(X0 - 20, Y0 - 20, X0 + 60, Y0 + 40)
win.viewport.update(); app.processEvents()


class Ctx:
    host = win
    document = property(lambda self: win.document)

    def echo(self, t):
        self.ecos.append(t)

    def execute(self, c):
        win.tools._execute(c)


ctx = Ctx(); ctx.ecos = []
destino = ENV.ruta_envio("dibujo")


def contenido():
    with zipfile.ZipFile(destino) as z:
        raiz = ET.fromstring(z.read("doc.kml"))
    return ({f.findtext(f"{N}name") for f in raiz.iter(f"{N}Folder")},
            len(list(raiz.iter(f"{N}GroundOverlay"))), len(list(raiz.iter(f"{N}Polygon"))))


# ------------------------------------------------------------- capas elegidas: imagen + lotes
win.tools.selection = set()
eleccion.update(que="capas", capas={"IMAGEN", "LOTES"})
GEC.cmd_abrir(ctx)
ver("ventana: seleccionados apagado sin selección", vista["sel"][:2] == (False, False), vista["sel"])
ver("ventana: «Lo que se ve en pantalla» marcado", vista["pantalla"])
ver("ventana: sólo capas con objetos", vista["capas"] == ["CALLES", "IMAGEN", "LOTES"], vista["capas"])
ver("ventana: botón «Enviar»", "Enviar" in vista["boton"], vista["boton"])
ver("capas: KMZ escrito y abierto en Google Earth", destino.is_file() and abiertos[-1:] == [str(destino)],
    abiertos[-1:])
ver("capas: imagen y dos lotes, sin la calle", contenido() == ({"IMAGEN", "LOTES"}, 1, 2), contenido())
ver("capas: aviso", ctx.ecos[-1:] and "Enviado a Google Earth" in ctx.ecos[-1], ctx.ecos[-1:])
ver("avance en 3 etapas", [e.split(" ", 1)[0] for e in etapas] == ["1/3", "2/3", "3/3"], etapas)

# ------------------------------------------------------------- lo que se ve en pantalla
eleccion.clear(); eleccion["que"] = "pantalla"; abiertos.clear()
GEC.cmd_abrir(ctx)
ver("pantalla: sin el lote lejano", contenido() == ({"IMAGEN", "LOTES", "CALLES"}, 1, 1), contenido())
ver("pantalla: abierto", abiertos == [str(destino)], abiertos)

# ------------------------------------------------------------- con selección
win.tools.selection = {lote2.dxf.handle}
eleccion.clear()
GEC.cmd_abrir(ctx)
ver("selección: viene marcado «Los elementos seleccionados (1)»",
    vista["sel"][:2] == (True, True) and "(1 objeto(s))" in vista["sel"][2], vista["sel"])
ver("selección: sólo el lote lejano", contenido() == ({"LOTES"}, 0, 1), contenido())

win.document.dirty = False
if fallas:
    print("FALLAS:", fallas)
    os._exit(1)
print("TODO OK")
sys.stdout.flush()
os._exit(0)
