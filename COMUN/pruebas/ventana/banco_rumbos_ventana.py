"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
RUMBOS en IngeCAD (3.87.0).

GeoCAD activo como al arrancar IngeCAD (con «Ángulos relativos» prendido) y
todo tecleado en la línea de comandos de verdad:
* RB arranca RUMBOS; el tramo base 0,0 / 10,0; 25.4<91d30'15" y 8<30dI
  llegan a la orden SIN que GeoCAD los reescriba y dan los puntos de QGIS;
  Enter deja una polilínea;
* Base = Sí, 10<90, 10<90 y C: un cuadrado cerrado; U lo borra de una vez;
* Modo Tramos (Base = Sí recordada): una línea por tramo, H borra la última;
* LÍNEA sigue con los ángulos relativos de siempre (@5<90 gira a la derecha);
* el botón está en «Yaguá Dibujo» (de fábrica) o en Yaguareté Tools, con ícono, y arranca la orden.

Uso (PySide6, ezdxf):
    python banco_rumbos_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
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
RB = import_module("ingecad_plugin_geocad.rumbos")
mods = import_module("ingecad_plugin_geocad.modulos")
mods.guardar("ingecad", {})
if mods.nuevos("ingecad"):
    mods.aceptar_nuevos("ingecad")
mods.poner("ingecad", "angulos_relativos", True)
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


def objetos(tipo):
    return [e for e in win.document.modelspace() if e.dxftype() == tipo]


def cerca(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


win = MainWindow()
win.plugins.loaded["geocad"] = lp           # como IngeCAD al arrancar
ver("GeoCAD activo", bool(win.plugins.activate("geocad")) or win.plugins.is_active("geocad"))
win.new_document("r")
win.show(); esperar()

print("1. RB, base y dos tramos escritos")
RB._set(RB.KEY_ANGULO, "interior"); RB._set(RB.KEY_TRAMOS, False); RB._set(RB.KEY_BASE, False)
escribir("RB")
ver("RB arranca RUMBOS", isinstance(win.tools.tool, RB.RumbosTool), type(win.tools.tool).__name__)
escribir("0,0"); escribir("10,0")
escribir("25.4<91d30'15\""); escribir("8<30dI")
p1, _ = RB.tramo((0, 0), (10, 0), "25.4<91d30'15\"")
p2, _ = RB.tramo((10, 0), p1, "8<30dI")
t = win.tools.tool
ver("los tramos llegan sin reescribir", t is not None and len(t.pts) == 4
    and cerca(t.pts[2], p1) and cerca(t.pts[3], p2), str(getattr(t, "pts", None)))
escribir()
pl = objetos("LWPOLYLINE")
ver("Enter deja una polilínea desde el 2º punto", len(pl) == 1 and len(pl[0]) == 3
    and cerca(pl[0][0], (10, 0)) and cerca(pl[0][2], p2) and win.tools.tool is None)

print("2. Base = Sí y Cerrar; U")
escribir("RUMBOS"); escribir("0,0"); escribir("10,0"); escribir("B")
escribir("10<90"); escribir("10<90"); escribir("C")
pl = objetos("LWPOLYLINE")
cuadrado = pl[-1] if len(pl) == 2 else None
ver("un cuadrado cerrado desde 0,0", cuadrado is not None and cuadrado.closed
    and [tuple(round(c, 6) for c in v[:2]) for v in cuadrado.get_points("xy")]
    == [(0, 0), (10, 0), (10, -10), (0, -10)])
escribir("U")
ver("U lo borra de una vez", len(objetos("LWPOLYLINE")) == 1)

print("3. Modo Tramos y H")
escribir("RB"); escribir("0,20"); escribir("10,20"); escribir("M")      # Base = Sí: recordada de la parte 2
for _ in range(3):
    escribir("5<180")
ver("una línea por tramo (base + 3)", len(objetos("LINE")) == 4)
escribir("H")
ver("H borra la última de verdad", len(objetos("LINE")) == 3)
escribir()
ver("Enter termina sin agregar nada", len(objetos("LINE")) == 3 and win.tools.tool is None)
RB._set(RB.KEY_TRAMOS, False); RB._set(RB.KEY_BASE, False)

print("4. LÍNEA sigue con los ángulos relativos")
escribir("L"); escribir("0,40"); escribir("10,40"); escribir("@5<90"); escribir()
ln = [e for e in objetos("LINE") if abs(e.dxf.start.y - 40) < 1e-9 and abs(e.dxf.start.x - 10) < 1e-9]
ver("@5<90 interior gira a la derecha", len(ln) == 1 and cerca(ln[0].dxf.end, (10, 35)),
    str([tuple(e.dxf.end)[:2] for e in ln]))

print("5. el botón")
pkg = import_module("ingecad_plugin_geocad")
bot = import_module("ingecad_plugin_geocad.botones")
import json
pkg.PLUGIN = pkg.construir_spec()
# las barras ya guardadas de antes de la 3.87.0 (como las de Fernando): la
# migración «rumbos» pone el botón, a la vista, detrás de RECTANG
bot.archivo().parent.mkdir(parents=True, exist_ok=True)
bot.archivo().write_text(json.dumps({"ingecad": {
    "categorias": [{"nombre": "Yaguá Dibujo", "botones": ["RECTANG", "TEXT"]}],
    "ocultos": [], "apagadas": [], "migraciones": ["limpiar-plano"]}}), encoding="utf-8")
win.add_toolbar(pkg.PLUGIN); esperar()                  # como IngeCAD arma la barra GeoCAD
from PySide6.QtWidgets import QToolBar
barras = {b.objectName(): b for b in win.findChildren(QToolBar)}
def ordenes(b):
    return [a.property("geocad_orden") for a in b.actions() if a.property("geocad_orden")]
dib = barras.get(bot.objeto_barra("Yaguá Dibujo"))
ver("barra guardada: «Yaguá Dibujo» con RUMBOS detrás de RECTANG", dib is not None
    and ordenes(dib) == ["RECTANG", "RUMBOS", "TEXT"], str(ordenes(dib) if dib else None))
fab =dict(bot.DEFECTO["ingecad"])["Yaguá Dibujo"]
ver("de fábrica en «Yaguá Dibujo», sin tildar (sólo lo reconfigurado de IngeCAD)",
    fab[:2] == ("RECTANG", "RUMBOS") and "RUMBOS" not in bot.PRENDIDOS["ingecad"])
accion = next((a for a in dib.actions() if a.property("geocad_orden") == "RUMBOS"), None) if dib else None
ver("con su ícono", accion is not None and not accion.icon().isNull())
bot.archivo().unlink()
bot.DEFECTO = {}                                        # sin categorías: la barra Yaguareté
win.add_toolbar(pkg.PLUGIN); esperar()
yag = next((b for b in win.findChildren(QToolBar) if b.objectName() == "geocad_yaguarete_toolbar"), None)
o = ordenes(yag) if yag is not None else []
ver("sin categorías, en Yaguareté Tools detrás de TEXT", "RUMBOS" in o
    and o.index("RUMBOS") == o.index("TEXT") + 1, str(o))
accion = next((a for a in yag.actions() if a.property("geocad_orden") == "RUMBOS"), None) if yag else None
ver("y el botón arranca la orden", accion is not None and (accion.trigger() or True)
    and isinstance(win.tools.tool, RB.RumbosTool))
escribir()                                              # Enter: termina sin dibujar
win.document.dirty = False
win.close()
print("TODO OK" if not fallas else "FALLAS: " + ", ".join(fallas))
sys.stdout.flush()
os._exit(0 if not fallas else 1)
