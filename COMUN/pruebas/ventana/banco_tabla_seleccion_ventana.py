"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
seleccionar muchas parcelas con la Tabla de atributos abierta (3.81.1).

Fernando, 15/11/2026: con PC_APOSTOLES (12 801 parcelas) y la tabla
abierta, seleccionar todo dejaba IngeCAD «no responde». La tabla seguía la
selección del dibujo con dos cálculos que crecían al cuadrado.

Con 12 801 parcelas con base de datos (IMPORTARSHP de verdad):
* Sin la tabla: cuánto tarda IngeCAD solo en avisar la selección (referencia).
* Con la tabla: seleccionar todo, la mitad salteada (peor caso: 6401 tramos),
  «Sólo seleccionados» y vaciar la selección; cada una en menos de LIMITE s,
  con las filas marcadas y el resumen correctos.
* Un segundo aviso del dibujo sin cambiar la selección no recalcula nada.

Uso (PySide6, ezdxf, numpy, pyshp, pyproj):
    python banco_tabla_seleccion_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(900, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 12801
LIMITE = 1.0
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
import shapefile
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
AV = import_module("ingecad_plugin_geocad.avance")
UI = import_module("ingecad_plugin_geocad.intercambio_ui")
TABLA = import_module("ingecad_plugin_geocad.tabla")
from views.main_window import MainWindow
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def hacer_shp(carpeta):
    ruta = os.path.join(carpeta, "parcelas")
    w = shapefile.Writer(ruta, shapeType=shapefile.POLYGON, encoding="utf-8")
    w.field("PARC", "C", 10)
    w.field("AREA", "N", 12, 2)
    for k in range(N):
        x0, y0 = 6_500_000 + (k % 113) * 40, 6_950_000 + (k // 113) * 40
        w.poly([[(x0, y0), (x0, y0 + 30), (x0 + 25, y0 + 32), (x0 + 30, y0 + 2), (x0, y0)]])
        w.record(f"{k:05d}", 800.0 + k % 50)
    w.close()
    return ruta + ".shp"


win = MainWindow()
win.new_document("m")
win.show(); app.processEvents()
shp = hacer_shp(tempfile.mkdtemp(prefix="banco-shp-"))


class Ctx:
    host = win
    document = property(lambda self: win.document)

    def echo(self, t):
        self.ecos.append(t)

    def execute(self, c):
        win.tools._execute(c)


ctx = Ctx(); ctx.ecos = []
UI.QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([shp], ""))


def aceptar_con_base(self):
    from PySide6.QtCore import Qt
    for t, campos in self.previas.values():
        for j in range(len(campos)):
            t.item(0, j).setCheckState(Qt.Checked)
    return True


UI.ImportarDialog.exec = aceptar_con_base
UI.importar(ctx)
app.processEvents()
ver("IMPORTARSHP", ctx.ecos[-1].startswith(f"IMPORTARSHP: Importado: {N}"), ctx.ecos[-1][:60])
handles = [e.dxf.handle for e in win.document.modelspace() if e.dxftype() in ("LWPOLYLINE", "POLYLINE")]
ver("parcelas en el dibujo", len(handles) == N, len(handles))
tools = win.tools


def seleccionar(hs):
    """Como la ventana de selección de IngeCAD: cambia la selección y avisa."""
    t0 = time.monotonic()
    tools.selection = set(hs)
    tools._highlight_cache = None
    tools._grips_cache = None
    tools.changed.emit()
    app.processEvents()
    return time.monotonic() - t0


# ------------------------------------------------------------- referencia: IngeCAD solo
def avisar():
    t0 = time.monotonic(); tools.changed.emit(); app.processEvents()
    return time.monotonic() - t0


mitad = handles[::2]
solo = {}
for _ in range(2):                      # la segunda vuelta, ya en caliente
    solo["todo"] = seleccionar(handles)
    solo["aviso"] = avisar()
    solo["mitad"] = seleccionar(mitad)
    solo["nada"] = seleccionar([])
print("  IngeCAD solo (sin la tabla): " + ", ".join(f"{k} {v:.2f} s" for k, v in solo.items()))


def nuestro(dt, caso):
    """Lo que agrega la tabla: el tiempo menos lo que tarda IngeCAD solo."""
    return max(0.0, dt - solo[caso])

# ------------------------------------------------------------- con la tabla abierta
TABLA.show_table(win)
app.processEvents()
panel = win.findChild(TABLA.QDockWidget, TABLA.DOCK_NAME).widget()
ver("la tabla muestra la capa", panel.model.rowCount() == N, panel.model.rowCount())


def filas_marcadas():
    return len(panel.table.selectionModel().selectedRows())


dt = nuestro(seleccionar(handles), "todo")
ver(f"seleccionar las {N}: la tabla agrega < {LIMITE} s", dt < LIMITE, f"{dt:.2f} s")
ver("todas las filas marcadas", filas_marcadas() == N, filas_marcadas())
ver("resumen con los seleccionados", f"{N} seleccionados" in panel.status.text(), panel.status.text())

veces = []
_orig_sync = panel.sync_from_drawing
panel.sync_from_drawing = lambda *a: (veces.append(1), _orig_sync(*a))[1]
avisar(); avisar()
ver("otros avisos sin cambiar la selección: no recalcula", not veces, f"{len(veces)} veces")
seleccionar(handles[:10]); seleccionar(handles)
ver("cambiar la selección sí recalcula", len(veces) == 2, f"{len(veces)} veces")
panel.sync_from_drawing = _orig_sync

dt = nuestro(seleccionar(mitad), "mitad")
ver(f"la mitad salteada (peor caso): la tabla agrega < {LIMITE} s", dt < LIMITE, f"{dt:.2f} s")
ver("filas de la mitad marcadas", filas_marcadas() == len(mitad), filas_marcadas())

panel.only_sel.setChecked(True); app.processEvents()
ver("Sólo seleccionados: quedan las de la mitad", panel.model.rowCount() == len(mitad), panel.model.rowCount())
dt = nuestro(seleccionar(handles), "todo")
ver(f"Sólo seleccionados y seleccionar todo: la tabla agrega < {LIMITE} s", dt < LIMITE and panel.model.rowCount() == N,
    f"{dt:.2f} s, {panel.model.rowCount()} filas")
panel.only_sel.setChecked(False); app.processEvents()

dt = nuestro(seleccionar([]), "nada")
ver(f"vaciar la selección: la tabla agrega < {LIMITE} s", dt < LIMITE and filas_marcadas() == 0, f"{dt:.2f} s")

# elegir filas en la tabla sigue seleccionando en el dibujo
sm = panel.table.selectionModel()
from PySide6.QtCore import QItemSelectionModel
sm.select(panel.model.index(3, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect
          | QItemSelectionModel.SelectionFlag.Rows)
app.processEvents()
ver("elegir una fila selecciona su parcela", len(tools.selection) == 1, len(tools.selection))

win.close()
print("TODO OK" if not fallas else f"FALLAS: {fallas}")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
