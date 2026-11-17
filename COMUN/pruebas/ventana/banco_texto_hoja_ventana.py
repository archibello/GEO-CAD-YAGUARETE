"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
los textos de una presentación no se esconden por chicos (3.84.3).

Fernando, 17/11/2026 («Charla GeoCAD Yaguareté.dwg», Layout2): textos de
5 mm en una A3; viendo la hoja entera aparecían un instante al deshacer y
después quedaban sólo las cajas. Era el tamaño mínimo de GeoCAD (6 px,
texto_minimo_px): a ese zoom las letras miden ~7 px y su promedio ~4-5 px.
Acordado: en la hoja ninguno se esconde (como AutoCAD); en el modelo, 6 px.

* Escena real de la hoja con un MTEXT de 5 a ~1,5 px por unidad: con 6 px
  IngeCAD no lo dibujaría (se mide el error), con 0 sí.
* El lienzo real (Viewport.paintGL) queda envuelto por GeoCAD.
* Se pinta de verdad (si hay OpenGL) espiando Batch.visible_runs: en la hoja
  pide 0; en Model, el mínimo de la configuración. Sin OpenGL lo informa.

Uso (PySide6, ezdxf, numpy):
    flatpak run --filesystem=<repo> --filesystem=<ingecad> --command=python3 \\
        org.ingecad.IngeCAD -u banco_texto_hoja_ventana.py <carpeta de IngeCAD> \\
        <repo>/INGECAD/codigo/geocad
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(600, exit=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
os.environ["INGECAD_SERIAL_REGEN"] = "1"
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
LG = import_module("ingecad_plugin_geocad.legibles")
LG.aplicar_ya()
VPM = import_module("views.viewport")
from views.main_window import MainWindow
from render.batches import Batch
try:
    from core.version import __version__ as VERSION_INGECAD
except Exception:  # noqa: BLE001
    VERSION_INGECAD = "?"
print("IngeCAD", VERSION_INGECAD, "· mínimo de GeoCAD:", VPM.MIN_TEXT_PX, "px")
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


def vertices_texto(scene, px_por_unidad, minimo):
    b = scene.triangles
    if b.is_text is None or not len(b.ranges):
        return 0
    todo = (-1e12, -1e12, 1e12, 1e12)
    return sum(c for _f, c in b.visible_runs(todo, px_por_unidad, minimo))


ver("el mínimo de GeoCAD está puesto", VPM.MIN_TEXT_PX == 6.0, str(VPM.MIN_TEXT_PX))
ver("lienzo real envuelto", getattr(VPM.Viewport.paintGL, "_puente_fabrica", None)
    is LG._envolver_paint)

win = MainWindow()
if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
    win.setWindowOpacity(0.0)        # con pantalla: pinta con OpenGL, sin verse
    win.show()
    esperar(1.0)
win.new_document("m")
win.document.modelspace().add_line((0, 0), (100, 50))
esperar(0.1)
win._new_layout_tab()
nombre = win._layout_names()[-1]
lay = win.document.doc.layouts.get(nombre)
lay.add_mtext("Por que vincular estos dos programas\nLos primeros usuarios del CAD",
              dxfattribs={"char_height": 5.0, "insert": (20, 150), "width": 380,
                          "layer": "0"})
win.switch_layout(nombre)
esperar()
if hasattr(win, "regen_in_memory"):
    win.regen_in_memory()
    esperar()
lienzo = win.viewport
ver("la hoja es espacio papel", LG.en_papel(lienzo))
escena = lienzo._scene
# la hoja entera como en la captura: 420 mm en ~640 px
k = 1.52
con6, con0 = vertices_texto(escena, k, 6.0), vertices_texto(escena, k, 0.0)
print(f"  texto de 5 a {k} px/u: {con6} vértices con 6 px, {con0} con 0 px")
ver("hay texto en la escena de la hoja", con0 > 0)
ver("con 6 px IngeCAD lo escondería (el error)", con6 < con0)

# pintar de verdad, espiando lo que pide cada dibujado
pedidos = []
original = Batch.visible_runs
def espia(self, view_rect, px, minimo, *a, **kw):
    pedidos.append(minimo)
    return original(self, view_rect, px, minimo, *a, **kw)
Batch.visible_runs = espia
try:
    lienzo.repaint()
    esperar(0.5)
    en_hoja = set(pedidos)
    win.switch_layout("Model")
    esperar()
    pedidos.clear()      # un pintado de la hoja que quedó en cola no cuenta
    ver("Model no es espacio papel", not LG.en_papel(lienzo))
    lienzo.repaint()
    esperar(0.5)
    en_modelo = set(pedidos)
finally:
    Batch.visible_runs = original
if not en_hoja and not en_modelo:
    print("  (sin OpenGL no pinta: se midió la escena y el envoltorio, no el dibujado)")
else:
    ver("al pintar la hoja pide 0 px", en_hoja == {0.0}, str(en_hoja))
    ver("al pintar el modelo pide 6 px", en_modelo == {6.0}, str(en_modelo))
ver("después de pintar el mínimo sigue en 6", VPM.MIN_TEXT_PX == 6.0)

print("TODO OK" if not fallas else f"FALLAS: {fallas}")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
