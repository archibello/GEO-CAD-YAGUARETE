"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
UNIR (J) con polígonos (3.96.0).

GeoCAD activo como al arrancar IngeCAD y todo tecleado en la línea de comandos:
* GeoCAD carga con GEOJOIN (no choca con el JOIN de IngeCAD: si chocara, IngeCAD
  rechazaría TODAS las herramientas del plugin);
* con las parcelas de las capturas preseleccionadas, J arranca la de GeoCAD,
  pregunta «¿Dónde dejo el resultado?» y N deja «combinados de lotes» con la
  unión (168 m²); la original queda igual; U la quita;
* Enter (de fábrica, 3.96.1) lo deja en la misma capa; U la devuelve; JOIN
  también (UNIR con IngeCAD en español); la capa nueva sale en rojo;
* con dos líneas, J es el JOIN de IngeCAD; con el submódulo apagado, también
  con polígonos.

Uso (PySide6, ezdxf):
    python banco_unir_poligonos_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
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
UP = import_module("ingecad_plugin_geocad.unir_poligonos")
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


def polis(capa="lotes"):
    return [e for e in win.document.modelspace() if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == capa]


def area(e):
    r = UP.anillo(e)
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]))) / 2


E, N = 14522900.0, 9977200.0
PARCELAS = [
    [(E, N), (E + 10, N), (E + 10, N + 6), (E + 4.7, N + 6), (E, N + 6)],
    [(E, N + 6), (E + 4.7, N + 6), (E + 4.7, N + 12), (E, N + 12)],
    [(E + 4.7, N + 6), (E + 4.72, N + 9), (E + 4.7, N + 12), (E + 10, N + 12), (E + 10, N + 6)],
    [(E + 10, N), (E + 14, N), (E + 14, N + 12), (E + 10, N + 12), (E + 10.01, N + 6)],
]

win = MainWindow()
win.plugins.loaded["geocad"] = lp           # como IngeCAD al arrancar
ver("GeoCAD activo", bool(win.plugins.activate("geocad")) or win.plugins.is_active("geocad"))
from views.tool_controller import ALL_TOOL_CLASSES
ver("GEOJOIN registrada; JOIN sigue siendo de IngeCAD", ALL_TOOL_CLASSES.get("GEOJOIN") is UP.UnirTool
    and ALL_TOOL_CLASSES.get("JOIN") is not UP.UnirTool and "RUMBOS" in ALL_TOOL_CLASSES)
win.new_document("r")
win.show(); esperar()
doc = win.document.doc
doc.layers.add("lotes", color=3)
msp = doc.modelspace()
for p in PARCELAS:
    msp.add_lwpolyline(p, close=True, dxfattribs={"layer": "lotes"})
win.document.dirty = True
esperar()


def preseleccionar(ents):
    win.tools.selection = {e.dxf.handle for e in ents}
    for _ in range(5):
        app.processEvents()


print("1. J con las cuatro parcelas, S (Sí: capa nueva)")
preseleccionar(polis())
escribir("J")
t = win.tools.tool
ver("J arranca la de GeoCAD y pregunta", isinstance(t, UP.UnirTool) and getattr(t, "_islas", None) is not None,
    type(t).__name__)
escribir("S")
nuevas = polis("combinados de lotes")
ver("«combinados de lotes» con la unión, en rojo", len(nuevas) == 1 and abs(area(nuevas[0]) - 168) < 1e-3
    and win.tools.tool is None and doc.layers.get("combinados de lotes").dxf.color == 1,
    str([area(e) for e in nuevas]))
ver("la original igual", len(polis()) == 4)
escribir("U")
ver("U la quita", not polis("combinados de lotes") and len(polis()) == 4)

print("2. JOIN y Enter (en la misma capa); U")
preseleccionar(polis())
escribir("JOIN")
ver("JOIN también", isinstance(win.tools.tool, UP.UnirTool), type(win.tools.tool).__name__)
escribir()
ver("Enter: una sola, de 168 m², en la misma capa", len(polis()) == 1 and abs(area(polis()[0]) - 168) < 1e-3)
escribir("U")
ver("U devuelve las cuatro", len(polis()) == 4)

print("3. líneas: el JOIN de IngeCAD")
l1 = msp.add_line((0, 0), (5, 0)); l2 = msp.add_line((5, 0), (9, 0))
preseleccionar([l1, l2])
escribir("J")
lineas = [e for e in msp if e.dxftype() == "LINE"]
ver("dos líneas en una", len(lineas) == 1 and win.tools.tool is None,
    "%d %s %s" % (len(lineas), type(win.tools.tool).__name__, win.command_line.prompt.text() if hasattr(win.command_line, "prompt") else ""))

print("4. submódulo apagado: J es el de IngeCAD")
mods.guardar("ingecad", {**mods.estado("ingecad"), "unir_poligonos": False})
preseleccionar(polis())
escribir("J")
ver("no pregunta ni une polígonos", not isinstance(win.tools.tool, UP.UnirTool)
    and len(polis()) == 4 and not polis("combinados de lotes"), type(win.tools.tool).__name__)
if win.tools.tool is not None:
    QTest.keyClick(win.command_line.input, Qt.Key_Escape)
mods.guardar("ingecad", {**mods.estado("ingecad"), "unir_poligonos": True})
win.document.dirty = False
win.close()
print("TODO OK" if not fallas else "FALLAS: " + ", ".join(fallas))
sys.stdout.flush()
os._exit(0 if not fallas else 1)
