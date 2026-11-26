"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
color de capa (3.96.2, capas.py).

Una capa con color exacto (RGB), como la «Nueva capa borrador» que trae
PEGARENLUGAR desde QGIS: en el panel Layers se le elige el color 160 (clic
en la columna Color, como Fernando) y la vista la dibuja en 160, no en el
gris de QGIS. U devuelve el gris. -CAPA Color también.

Uso (PySide6, ezdxf):
    python banco_color_capa_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, math, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
mods.guardar("ingecad", {})
if mods.nuevos("ingecad"):
    mods.aceptar_nuevos("ingecad")
from views.main_window import MainWindow
try:
    from core.version import __version__ as VERSION_INGECAD
except Exception:  # noqa: BLE001
    VERSION_INGECAD = "?"
print("IngeCAD", VERSION_INGECAD)
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'OK' if ok else 'FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def esperar(s=0.2):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        time.sleep(0.01)


def escribir(texto=""):
    entrada = win.command_line.input
    if texto:
        QTest.keyClicks(entrada, texto)
    QTest.keyClick(entrada, Qt.Key_Return)
    for _ in range(10):
        app.processEvents()


win = MainWindow()
win.plugins.loaded["geocad"] = lp           # como IngeCAD al arrancar
ver("GeoCAD activo", bool(win.plugins.activate("geocad")) or win.plugins.is_active("geocad"))
win.new_document("r")
win.show(); esperar()
import ezdxf
from ezdxf.colors import rgb2int, aci2rgb
from ezdxf.addons.drawing.properties import RenderContext
doc = win.document.doc
GRIS = rgb2int((0x7d, 0x8b, 0x8f))
lay = doc.layers.add("Nueva capa borrador", color=7)
lay.dxf.true_color = GRIS
e = doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 10)], close=True,
                                    dxfattribs={"layer": "Nueva capa borrador"})
win.document.dirty = True
esperar()


def se_ve():
    return RenderContext(doc).resolve_color(e)


AZUL = "#%02x%02x%02x" % tuple(aci2rgb(160))
print("1. panel Layers: clic en Color, se elige 160")
import views.color_dialog as CD
class _Dialogo:
    def __init__(self, *a, **k): pass
    def exec(self): return True
    def result_aci(self): return 160
CD.SelectColorDialog = _Dialogo
from views.layers_panel import LayersPanel
panel = getattr(win, "_layers_panel", None) or next(iter(app.allWidgets().__class__(
    w for w in app.allWidgets() if isinstance(w, LayersPanel))), None)
if hasattr(panel, "refresh"):
    panel.refresh()
esperar()
fila = next(r for r in range(panel.table.rowCount()) if panel._row_layer(r) == "Nueva capa borrador")
panel._on_cell_clicked(fila, 5)
esperar()
ver("la capa queda en 160 sin RGB", lay.dxf.color == 160 and not lay.dxf.hasattr("true_color"),
    f"{lay.dxf.color} {lay.dxf.get('true_color')}")
ver("y se ve en 160", se_ve() == AZUL, se_ve())
escribir("U")
ver("U devuelve el gris de QGIS", lay.dxf.get("true_color") == GRIS and se_ve() == "#7d8b8f", se_ve())

print("2. -CAPA Color")
otra = doc.layers.add("lotes_qgis", color=7)          # sin espacios: en la línea de comandos el espacio es Intro
otra.dxf.true_color = GRIS
escribir("-LAYER"); escribir("C"); escribir("1"); escribir("lotes_qgis"); escribir()
ver("-CAPA Color 1: rojo, sin RGB", abs(otra.dxf.color) == 1 and not otra.dxf.hasattr("true_color"),
    f"{otra.dxf.color} {otra.dxf.get('true_color')}")
win.document.dirty = False
win.close()
print("TODO OK" if not fallas else "FALLAS: " + ", ".join(fallas))
sys.stdout.flush()
os._exit(0 if not fallas else 1)
