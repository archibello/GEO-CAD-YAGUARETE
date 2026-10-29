"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
Perpendicular y Apparent Intersection con guías de puntos (3.56.0).

Con LINE: Apparent Intersection sale del gris en el menú de Mayús + clic
derecho; detenerse medio segundo sobre una línea la toma (el reloj de Qt
de verdad); pasar por otra muestra el cruce flotante con las dos guías de
puntos (se dibujan en el lienzo) y el clic pone el punto ahí. Perpendicular
con el pie fuera del tramo: su guía y el punto en el pie. Módulo apagado:
APP en gris, como viene IngeCAD.

Uso (necesita PySide6, ezdxf, numpy; el Python del Flatpak de IngeCAD los trae):
    python banco_guias_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QImage, QPainter, QColor

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
GI = import_module("ingecad_plugin_geocad.guias_ingecad")
from views.main_window import MainWindow
fallas = []


def ver(nombre, ok):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'}")
    if not ok:
        fallas.append(nombre)


def esperar(win, s=0.0):
    t0 = time.monotonic()
    while True:
        app.processEvents()
        listo = not getattr(win.tools, "caches_warming", lambda: False)()
        if listo and time.monotonic() - t0 >= s:
            break
        if time.monotonic() - t0 > 20:
            break
        time.sleep(0.01)


def cerca(hit, x, y, tol=1e-6):
    return hit is not None and abs(hit.x - x) <= tol and abs(hit.y - y) <= tol


def ventana():
    win = MainWindow()
    win.new_document("m")
    ms = win.document.modelspace()
    ms.add_line((0, 0), (10, 0))          # H
    ms.add_line((20, 5), (20, 15))        # V
    win.document.dirty = True
    win.show(); app.processEvents()
    win.regen_in_memory(); esperar(win, 0.3)
    return win


def menu_app(win):
    menu = win.osnap_override_menu()
    return next(a for a in menu.actions() if a.text() == "Apparent Intersection")


def pintar_guias(win):
    """Lo que dibuja _draw_tracking (de IngeCAD + GeoCAD) en una imagen."""
    img = QImage(win.viewport.width() or 800, win.viewport.height() or 600, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    win.viewport._draw_tracking(p, win.tools)
    p.end()
    naranja = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = img.pixelColor(x, y)
            if c.red() > 200 and 120 < c.green() < 200 and c.blue() < 90:
                naranja += 1
    return naranja


U = 0.5      # la apertura en unidades del dibujo (la app la saca de los píxeles)
mods.guardar("ingecad", {"referencias": True})

print("1. Apparent Intersection en LINE")
win = ventana()
ver("APP habilitada en el menú", menu_app(win).isEnabled())
win.tools.start_tool("LINE"); esperar(win)
win.tools.on_click(30.0, -10.0); esperar(win)                 # primer punto
ok = win.tools.set_osnap_override({"APP"})
ver("set_osnap_override(APP) aceptado", ok is not False)
win.tools.on_hover(5.0, 0.1, U)
ver("una sola línea: todavía sin punto", win.tools.snap_hit is None)
esperar(win, 0.7)                                             # medio segundo encima
ver("H tomada con el reloj de Qt", len(getattr(win.tools, "_geocad_tomadas").lista) == 1)
win.tools.on_hover(20.1, 10.0, U)                             # sobre V
ver("cruce aparente (20, 0)", win.tools.snap_hit is not None
    and win.tools.snap_hit.kind == "APP" and cerca(win.tools.snap_hit, 20, 0))
guias, tomadas = win.tools._geocad_guias
ver("dos guías de puntos", len(guias) == 2)
ver("las guías se dibujan", pintar_guias(win) > 10)
win.tools.on_hover(-30.0, 40.0, U)                            # lejos, sin tomar V
ver("lejos sin tomar V: sin punto", win.tools.snap_hit is None)
win.tools.on_hover(20.1, 10.0, U); esperar(win, 0.7)          # tomar V
win.tools.on_hover(-30.0, 40.0, U)
ver("con las dos tomadas el punto queda", cerca(win.tools.snap_hit, 20, 0))
win.tools.on_click(-30.0, 40.0); esperar(win)                 # clic lejos: va al cruce
win.tools.on_text(""); esperar(win)                           # Enter: termina LINE
nuevas = [e for e in win.document.modelspace() if e.dxftype() == "LINE"
          and (round(e.dxf.start.x, 6), round(e.dxf.start.y, 6)) == (30.0, -10.0)]
ver("la línea termina en el cruce", len(nuevas) == 1
    and (round(nuevas[0].dxf.end.x, 6), round(nuevas[0].dxf.end.y, 6)) == (20.0, 0.0))
ver("con el punto se sueltan las tomadas", getattr(win.tools, "_geocad_tomadas", None) is None)
win.close(); app.processEvents()

print("2. Perpendicular con el pie fuera del tramo")
win = ventana()
win.tools.start_tool("LINE"); esperar(win)
win.tools.on_click(-5.0, 10.0); esperar(win)
win.tools.set_osnap_override({"PER"})
win.tools.on_hover(5.0, 0.1, U)
ver("pie (-5, 0)", win.tools.snap_hit is not None and win.tools.snap_hit.kind == "PER"
    and cerca(win.tools.snap_hit, -5, 0))
guias, _ = win.tools._geocad_guias
ver("guía desde la punta (0, 0)", len(guias) == 1 and guias[0][0] == (0.0, 0.0))
esperar(win, 0.7)
win.tools.on_hover(-30.0, 40.0, U)
ver("tomada: el pie sigue lejos de la línea", cerca(win.tools.snap_hit, -5, 0))
win.tools.on_click(-30.0, 40.0); esperar(win)
win.tools.on_text(""); esperar(win)
nuevas = [e for e in win.document.modelspace() if e.dxftype() == "LINE"
          and (round(e.dxf.start.x, 6), round(e.dxf.start.y, 6)) == (-5.0, 10.0)]
ver("la línea termina en el pie", len(nuevas) == 1
    and (round(nuevas[0].dxf.end.x, 6), round(nuevas[0].dxf.end.y, 6)) == (-5.0, 0.0))
win.close(); app.processEvents()

print("3. Módulo apagado: como viene IngeCAD")
mods.guardar("ingecad", {"referencias": False})
win = ventana()
ver("APP en gris", not menu_app(win).isEnabled())
win.tools.start_tool("LINE"); esperar(win)
win.tools.on_click(-5.0, 10.0); esperar(win)
win.tools.set_osnap_override({"PER"})
win.tools.on_hover(5.0, 0.1, U)
# IngeCAD solo da el pie dentro del tramo (_project_on_segment): fuera, nada
ver("PER de IngeCAD: sin pie fuera del tramo, sin guías", win.tools.snap_hit is None
    and getattr(win.tools, "_geocad_guias", ([], [])) == ([], []))
win.tools.on_hover(20.1, 8.0, U)                              # sobre V: el pie (20, 10) en el tramo
ver("PER de IngeCAD dentro del tramo", cerca(win.tools.snap_hit, 20, 10))
win.tools.on_text("")
win.close(); app.processEvents()
mods.guardar("ingecad", {"referencias": True})

if fallas:
    print("FALLAS:", fallas)
    sys.exit(1)
print("TODO OK")
