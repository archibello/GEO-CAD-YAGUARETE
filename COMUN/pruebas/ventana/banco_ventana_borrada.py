"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
borrar la ventana gráfica que trae una presentación (3.84.1).

Fernando, 16/11/2026 («Tarjeta de presentacion.dwg», Layout4): «no me deja
borrar el viewport que viene por defecto». El primer Supr la borraba, pero
IngeCAD la dejaba en su índice de selección: un clic en el borde elegía el
fantasma y el siguiente Supr o BORRA fallaba callado. Pasa sin GeoCAD.

* Sin el gancho (IngeCAD solo): se mide el fantasma (sólo informa: si una
  IngeCAD nueva lo arregla, el banco lo dice y sigue).
* Con GeoCAD (Papel y Agarres enganchados): presentación nueva, clic en el
  borde, la acción Supr real la borra; un clic en el mismo borde no elige
  nada; U la devuelve, se elige y se borra otra vez; rehacer también.

Uso (PySide6, ezdxf, numpy):
    python banco_ventana_borrada.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Con el Python del Flatpak de IngeCAD (trae PySide6):
    flatpak run --filesystem=<repo> --command=python3 org.ingecad.IngeCAD -u \\
        banco_ventana_borrada.py /app/ingecad <repo>/INGECAD/codigo/geocad
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(600, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QAction, QKeySequence

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
P = import_module("ingecad_plugin_geocad.papel")
AG = import_module("ingecad_plugin_geocad.agarres_ingecad")
from views.main_window import MainWindow
from core import layouts as L
try:
    from core.version import __version__ as VERSION_INGECAD
except Exception:  # noqa: BLE001 -- las viejas no lo tienen
    VERSION_INGECAD = "?"
print("IngeCAD", VERSION_INGECAD)
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def esperar(s=0.3):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        time.sleep(0.01)


def hoja_nueva():
    """Dibujo nuevo, presentación nueva con el botón «+» y abierta: IngeCAD le
    pone su ventana (la «que viene por defecto»)."""
    win = MainWindow()
    win.new_document("m")
    win.document.modelspace().add_line((0, 0), (100, 50))
    esperar(0.1)
    win._new_layout_tab()
    nombre = win._layout_names()[-1]
    win.switch_layout(nombre)
    esperar()
    lay = win.document.doc.layouts.get(nombre)
    vps = L.visible_viewports(lay)
    assert len(vps) == 1, vps
    return win, lay, vps[0]


def supr(win):
    """La acción «Delete» del dibujo (la que dispara la tecla Supr)."""
    for a in win.viewport.actions():
        if any(k.matches(QKeySequence(QKeySequence.Delete)) == QKeySequence.ExactMatch
               for k in a.shortcuts()):
            a.trigger()
            esperar()
            return True
    return False


def borde(vp):
    x0, y0, x1, y1 = L.viewport_rect(vp)
    return x0, (y0 + y1) / 2.0


# ------------------------------------------------------------- 1. IngeCAD solo
win, lay, vp = hoja_nueva()
t = win.tools
x, y = borde(vp)
t.on_click(x, y)
ver("IngeCAD solo: el borde elige la ventana", t.selection == {vp.dxf.handle})
ver("IngeCAD solo: Supr la borra", supr(win) and not L.visible_viewports(lay))
t.on_click(x, y)
fantasma = bool(t.selection)
print(f"  IngeCAD solo, después de borrar, el borde elige: {sorted(t.selection) or 'nada'}"
      f" -> {'FANTASMA (el error que arregla GeoCAD)' if fantasma else 'IngeCAD ya lo arregló'}")
if fantasma:
    try:
        r = t.delete_selection()
        print(f"  segundo Supr: devuelve {r}, sin error")
    except ValueError as e:
        print(f"  segundo Supr: falla callado en la ventana real ({e})")
t.clear_selection()
win.close(); esperar(0.1)

# ------------------------------------------------------------- 2. con GeoCAD
win, lay, vp = hoja_nueva()
t = win.tools
AG.aplicar(win)                                   # Agarres también toma Supr: que convivan
P.enganchar_ventanas(win)
ver("gancho puesto", getattr(vars(t).get("_execute_command"), "_geocad_papel", False))
h = vp.dxf.handle
x, y = borde(vp)
t.on_click(x, y)
ver("el borde elige la ventana", t.selection == {h})
ver("Supr la borra", supr(win) and not L.visible_viewports(lay))
t.on_click(x, y)
ver("el borde ya no elige nada (sin fantasma)", not t.selection, str(t.selection))
t.clear_selection()

win._cmd_undo(); esperar()
vps = L.visible_viewports(lay)
ver("U la devuelve", len(vps) == 1 and vps[0].dxf.handle == h)
t.on_click(x, y)
ver("vuelta, se elige de nuevo", t.selection == {h})
ver("y Supr la borra otra vez", supr(win) and not L.visible_viewports(lay))
t.on_click(x, y)
ver("sin fantasma otra vez", not t.selection)
t.clear_selection()

win._cmd_undo(); esperar()
win._cmd_redo(); esperar()
ver("rehacer: borrada", not L.visible_viewports(lay))
t.on_click(x, y)
ver("rehacer: sin fantasma", not t.selection, str(t.selection))
t.clear_selection()

# BORRA escrito, con la ventana elegida antes (lo que probó Fernando con «E»)
win._cmd_undo(); esperar()
t.on_click(x, y)
win.dispatcher.submit("ERASE"); esperar()
if t.tool is not None:                            # pide designar: Enter
    win.dispatcher.submit(""); esperar()
ver("BORRA la borra", not L.visible_viewports(lay))
t.on_click(x, y)
ver("BORRA: sin fantasma", not t.selection, str(t.selection))
win.close(); esperar(0.1)

# ------------------------------------------------------------- 3. moverla (3.84.2)
# Fernando: «hice un viewport nuevo y crea un fantasma cuando lo desplazas»:
# la ventana se movía, pero el resaltado y el clic quedaban en el lugar viejo.
def resaltado(t):
    segs = t.highlight_geometry()[0]
    if not len(segs):
        return None
    xs = list(segs[:, 0]) + list(segs[:, 2])
    ys = list(segs[:, 1]) + list(segs[:, 3])
    return (min(xs), min(ys), max(xs), max(ys))


def igual(a, b, tol=1e-6):
    return a is not None and b is not None and all(abs(p - q) <= tol for p, q in zip(a, b))


def mover(gancho, como):
    win, lay, vp = hoja_nueva()
    t = win.tools
    if gancho:
        AG.aplicar(win)
        P.enganchar_ventanas(win)
    viejo = L.viewport_rect(vp)
    xv, yv = borde(vp)
    t.on_click(xv, yv)
    assert t.selection == {vp.dxf.handle}
    if como == "MOVE":                            # la herramienta MOVE, con la ventana elegida
        t.osnap_on = False
        t.start_tool("MOVE"); esperar(0.1)
        bx, by = (viejo[0] + viejo[2]) / 2.0, viejo[1] - 10.0     # fuera de la ventana
        t.on_click(bx, by); esperar(0.1)
        t.on_click(bx + 40.0, by + 30.0); esperar()
    else:                                         # el agarre del centro
        cx, cy = (viejo[0] + viejo[2]) / 2.0, (viejo[1] + viejo[3]) / 2.0
        grip = t.grip_at(cx, cy, 3.0)
        t.begin_grip_drag(grip)
        t.update_grip_drag(cx + 40.0, cy + 30.0)
        t.finish_grip_drag(cx + 40.0, cy + 30.0)
        esperar()
    nuevo = L.viewport_rect(vp)
    movida = igual(nuevo, (viejo[0] + 40, viejo[1] + 30, viejo[2] + 40, viejo[3] + 30))
    t.selection = {vp.dxf.handle}                 # sigue elegida (como en la captura)
    r = resaltado(t)
    t.clear_selection()
    t.on_click(xv, yv)
    en_viejo = set(t.selection)
    t.clear_selection()
    xn, yn = borde(vp)
    t.on_click(xn, yn)
    en_nuevo = set(t.selection)
    t.clear_selection()
    return win, lay, vp, t, movida, r, nuevo, en_viejo, en_nuevo


for como in ("MOVE", "agarre"):
    win, lay, vp, t, movida, r, nuevo, en_viejo, en_nuevo = mover(False, como)
    print(f"  IngeCAD solo, {como}: movida={movida}, resaltado en el lugar "
          f"{'NUEVO' if igual(r, nuevo) else 'VIEJO (fantasma)'}, el borde viejo elige "
          f"{sorted(en_viejo) or 'nada'}")
    win.close(); esperar(0.1)
    if not movida:
        # IngeCAD 0.6.7 y 0.6.8.2: el agarre del centro no mueve la ventana
        # (tampoco sin GeoCAD): no hay nada que medir
        print(f"  {como}: esta IngeCAD no mueve la ventana así (tampoco sola): no se mide")
        continue
    win, lay, vp, t, movida, r, nuevo, en_viejo, en_nuevo = mover(True, como)
    h = vp.dxf.handle
    ver(f"{como}: la ventana se movió", movida)
    ver(f"{como}: el resaltado está en el lugar nuevo", igual(r, nuevo), f"{r} vs {nuevo}")
    ver(f"{como}: el borde viejo no elige nada", not en_viejo, str(en_viejo))
    ver(f"{como}: el borde nuevo la elige", en_nuevo == {h}, str(en_nuevo))
    win._cmd_undo(); esperar()
    atras = L.viewport_rect(vp)
    t.selection = {h}
    ver(f"{como}: U, el resaltado vuelve con ella", igual(resaltado(t), atras))
    t.clear_selection()
    x, y = borde(vp)
    t.on_click(x, y)
    ver(f"{como}: U, se elige en su lugar y Supr la borra",
        t.selection == {h} and supr(win) and not L.visible_viewports(lay))
    win.close(); esperar(0.1)

print()
if fallas:
    print("FALLAS:", ", ".join(fallas))
    os._exit(1)
print("TODO OK BANCO VENTANA BORRADA")
os._exit(0)
