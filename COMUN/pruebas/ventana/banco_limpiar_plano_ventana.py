"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
LIMPIARPLANO (3.86.0), limpiar un plano antiguo escaneado.

Con la orden escrita en la línea de comandos de verdad (puntos, D y Enter
tecleados), sobre el recorte del plano de mensura de 1958 de las pruebas:
* la imagen elegida de antes, una zona de sello con dos esquinas, D la
  quita, otra zona y Enter;
* la imagen del dibujo pasa a la copia limpia, al doble de píxeles, y en la
  escena de IngeCAD se ven los píxeles NUEVOS (no la textura vieja) en el
  mismo lugar;
* el original no se toca; U vuelve a la imagen y la escena de antes.

Uso (PySide6, ezdxf, numpy, Pillow):
    python banco_limpiar_plano_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, hashlib, shutil, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
import numpy as np
from PIL import Image as PILImage
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
LP = import_module("ingecad_plugin_geocad.limpiar_plano")
import_module("ingecad_plugin_geocad.modulos").guardar("ingecad", {"georref": True})
from views.main_window import MainWindow
import views.tool_controller as TC
TC.ALL_TOOL_CLASSES["LIMPIARPLANO"] = LP.LimpiarPlanoTool       # como lo registra el plugin

tmp = Path(tempfile.mkdtemp(prefix="banco-"))
png = tmp / "mensura.png"
shutil.copy(Path(__file__).resolve().parents[1] / "datos_limpiar_plano" / "recorte_original.png", png)
huella = hashlib.sha256(png.read_bytes()).hexdigest()
fallas = []


def verificar(nombre, ok):
    print(f"  [{nombre}] {'OK' if ok else 'FALLA'}")
    if not ok:
        fallas.append(nombre)


def esperar(win, s=15.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        if getattr(win, "_regen_worker", None) is None and not win.tools._merge_timer.isActive():
            break
        time.sleep(0.01)
    for _ in range(20):
        app.processEvents()


def escribir(win, texto=""):
    entrada = win.command_line.input
    if texto:
        QTest.keyClicks(entrada, texto)
    QTest.keyClick(entrada, Qt.Key_Return)
    for _ in range(10):
        app.processEvents()


def en_escena(win, h):
    for i in getattr(win.viewport._scene, "images", []):
        if i.handle == h:
            return i
    return None


def punto(px, py):
    """Píxel del recorte (arriba a la izquierda = 0, 0) -> «x,y» del dibujo
    (la imagen: 300 × 300 px en (0, 0), 0,5 por píxel)."""
    return f"{px * 0.5:g},{(300 - py) * 0.5:g}"


win = MainWindow()
win.new_document("m")
win.document.path = tmp / "plano.dwg"
d = win.document.doc.add_image_def(filename=str(png), size_in_pixel=(300, 300))
img = win.document.modelspace().add_image(image_def=d, insert=(0, 0), size_in_units=(150, 150))
win.document.dirty = True
win.show(); app.processEvents()
win.regen_in_memory(); esperar(win)
antes = en_escena(win, img.dxf.handle)
verificar("la imagen en la escena", antes is not None and antes.pixels.shape[:2] == (300, 300))
esquinas = np.array(antes.corners, float) if antes is not None else None

print("1. la orden, con la línea de comandos")
win.tools.selection = {img.dxf.handle}
win.tools.start_tool("LIMPIARPLANO"); app.processEvents()
tool = win.tools.tool
verificar("la orden tomó la imagen elegida", isinstance(tool, LP.LimpiarPlanoTool) and tool.img is img)
escribir(win, punto(10, 10)); escribir(win, punto(40, 30))
verificar("una zona con dos esquinas tecleadas", tool.zonas == [(10, 10, 40, 30)])
escribir(win, "D")
verificar("D la quita", tool.zonas == [])
escribir(win, punto(65, 55)); escribir(win, punto(300, 300))
verificar("la zona del sello", tool.zonas == [(65, 55, 300, 300)])
t0 = time.monotonic()
escribir(win)                                     # Enter: limpiar
esperar(win)
print(f"     limpió en {time.monotonic() - t0:.1f} s")
copia = Path(img.image_def.dxf.filename)
verificar("la imagen usa la copia limpia", copia.name == "mensura_limpio.png" and copia.is_file())
verificar("el original no se toca", hashlib.sha256(png.read_bytes()).hexdigest() == huella)
verificar("al doble de píxeles", tuple(img.dxf.image_size)[:2] == (600, 600))
verificar("la orden terminó", not isinstance(win.tools.tool, LP.LimpiarPlanoTool))
win.regen_in_memory(); esperar(win)
ahora = en_escena(win, img.dxf.handle)
limpia = np.asarray(PILImage.open(copia).convert("L"))
verificar("la escena muestra los píxeles NUEVOS", ahora is not None and ahora.pixels.shape[:2] == (600, 600)
          and np.array_equal(ahora.pixels[..., 0], limpia))
verificar("en el mismo lugar", ahora is not None and np.allclose(np.array(ahora.corners, float), esquinas, atol=1e-4))
historia = win.command_line.history.toPlainText()
verificar("el eco lo dice", "Plano limpio" in historia and "U lo deshace" in historia)

print("2. U")
win.history.undo(); win.regen_in_memory(); esperar(win)
otra = en_escena(win, img.dxf.handle)
verificar("U: vuelve el original", img.image_def.dxf.filename == str(png) and LP.leer(img) is None)
verificar("U: la escena de antes", otra is not None and otra.pixels.shape[:2] == (300, 300)
          and np.allclose(np.array(otra.corners, float), esquinas, atol=1e-4))

win.document.dirty = False
win.close(); app.processEvents()
print("TODO OK" if not fallas else f"FALLAN: {fallas}")
