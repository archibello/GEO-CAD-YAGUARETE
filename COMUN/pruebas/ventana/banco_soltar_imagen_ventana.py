"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
SOLTARIMAGEN, una imagen arrastrada desde el explorador (3.88.0).

* el lienzo acepta el arrastre de una imagen y no el de otro archivo;
* al soltarla arranca SOLTARIMAGEN con ese archivo;
* esquina y 2º punto tecleados en la línea de comandos de verdad: todavía no
  hay IMAGE; el lienzo PINTA la imagen semitransparente donde va (se cuentan
  los píxeles del color de la imagen) y gira con el cursor;
* 30 + Enter: la IMAGE queda con su ancho y su giro, apunta al archivo soltado;
  U la quita; terminada la orden, el lienzo ya no la pinta;
* Esc a mitad de camino: no queda nada;
* apagado el módulo «georref», el lienzo vuelve a no aceptar arrastres.

Uso (PySide6, ezdxf, Pillow):
    python banco_soltar_imagen_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
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
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
SI = import_module("ingecad_plugin_geocad.soltar_imagen")
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


def imagenes():
    return [e for e in win.document.modelspace() if e.dxftype() == "IMAGE"]


def cerca(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def mime(ruta):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(ruta))])
    return m


def arrastrar(ruta):
    """(aceptado al entrar, aceptado al soltar)"""
    visor = win.viewport
    centro = QPointF(visor.width() / 2, visor.height() / 2)
    m = mime(ruta)
    entra = QDragEnterEvent(centro.toPoint(), Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(visor, entra)
    if not entra.isAccepted():
        return False, False
    suelta = QDropEvent(centro, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(visor, suelta)
    esperar(0.1)
    return True, suelta.isAccepted()


def a_dibujo(sx, sy):
    """El punto del dibujo que cae en (sx, sy) de la pantalla."""
    v = win.viewport
    o, ex, ey = v._space_to_screen(0, 0), v._space_to_screen(1, 0), v._space_to_screen(0, 1)
    a, b = ex[0] - o[0], ey[0] - o[0]
    c, d = ex[1] - o[1], ey[1] - o[1]
    det = a * d - b * c
    dx, dy = sx - o[0], sy - o[1]
    return ((d * dx - b * dy) / det, (-c * dx + a * dy) / det)


def pintados(cursor):
    """Píxeles rojos que el lienzo pinta en la vista previa con el cursor ahí."""
    v = win.viewport
    win.tools._cursor = cursor
    lienzo = QImage(v.width(), v.height(), QImage.Format_ARGB32)
    lienzo.fill(QColor(0, 0, 0))
    p = QPainter(lienzo)
    try:
        v._draw_tool_preview(p)
    finally:
        p.end()
    n = 0
    for y in range(0, lienzo.height(), 2):
        for x in range(0, lienzo.width(), 2):
            c = lienzo.pixelColor(x, y)
            if c.red() > 100 and c.green() < 40 and c.blue() < 40:
                n += 1
    return n


carpeta = Path(tempfile.mkdtemp(prefix="banco-soltar-"))
from PIL import Image
foto = carpeta / "fachada.png"; Image.new("RGB", (400, 200), (255, 0, 0)).save(foto)
otro = carpeta / "plano.dwg"; otro.write_bytes(b"no")

win = MainWindow()
win.plugins.loaded["geocad"] = lp           # como IngeCAD al arrancar
ver("GeoCAD activo", bool(win.plugins.activate("geocad")) or win.plugins.is_active("geocad"))
win.new_document("r")
win.resize(1000, 700)
win.show(); esperar()
ver("el lienzo acepta arrastres", win.viewport.acceptDrops())

print("1. arrastrar")
ver("otro archivo: no", arrastrar(otro) == (False, False) and win.tools.tool is None)
ver("la imagen: sí", arrastrar(foto) == (True, True))
t = win.tools.tool
ver("arranca SOLTARIMAGEN", isinstance(t, SI.SoltarImagenTool) and t._ruta == foto and t._tam == (400, 200),
    type(t).__name__)

print("2. esquina y ancho tecleados; la imagen se ve")
w, h = win.viewport.width(), win.viewport.height()
p1 = a_dibujo(w * 0.3, h * 0.6)
p2 = a_dibujo(w * 0.6, h * 0.6)
ancho = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
escribir(f"{p1[0]:.6f},{p1[1]:.6f}")
ver("pide el 2º punto", t._p1 is not None and t._ancho is None)
n_estira = pintados(p2)
ver("pinta la imagen mientras se estira", n_estira > 500, f"{n_estira} píxeles")
escribir(f"{p2[0]:.6f},{p2[1]:.6f}")
ver("pide el giro, todavía sin IMAGE", t._ancho is not None and abs(t._ancho - ancho) < 1e-6
    and not imagenes())
derecha = pintados((p1[0] + ancho, p1[1]))
arriba = pintados((p1[0], p1[1] + ancho))
ver("pinta la imagen girando con el cursor", derecha > 500 and arriba > 500, f"{derecha} / {arriba}")

print("3. giro escrito: queda")
escribir("30")
im = imagenes()
ver("una IMAGE", len(im) == 1 and win.tools.tool is None)
if im:
    u = tuple(im[0].dxf.u_pixel)[:2]
    lado = ancho / 400
    ver("ancho y giro", cerca(u, (lado * math.cos(math.radians(30)), lado * math.sin(math.radians(30)))),
        repr(u))
    ver("esquina", cerca(tuple(im[0].dxf.insert)[:2], p1))
    ver("el archivo soltado tal cual", Path(im[0].image_def.dxf.filename) == foto)
ver("terminada, ya no la pinta", pintados(p2) == 0)
ver("el gancho se fue", "_draw_tool_preview" not in vars(win.viewport))
escribir("U"); esperar()
ver("U la quita", not imagenes())

print("4. Esc a mitad de camino")
arrastrar(foto)
escribir(f"{p1[0]:.6f},{p1[1]:.6f}")
escribir(f"{p2[0]:.6f},{p2[1]:.6f}")
QTest.keyClick(win.command_line.input, Qt.Key_Escape); esperar()
ver("no queda nada", not imagenes() and win.tools.tool is None)

print("4b. como llega en Wayland (3.88.1): urls() con un número, la ruta en el texto")
m = QMimeData()
m.setUrls([QUrl("154348542434273464005941809929656718809")])
m.setText(str(foto))
m.setData("application/vnd.portal.filetransfer", b"1835\x00")
visor = win.viewport
centro = QPointF(visor.width() / 2, visor.height() / 2)
entra = QDragEnterEvent(centro.toPoint(), Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
QApplication.sendEvent(visor, entra)
suelta = QDropEvent(centro, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
QApplication.sendEvent(visor, suelta); esperar(0.1)
t = win.tools.tool
ver("acepta y arranca con la ruta del texto", entra.isAccepted() and suelta.isAccepted()
    and isinstance(t, SI.SoltarImagenTool) and t._ruta == foto)
QTest.keyClick(win.command_line.input, Qt.Key_Escape); esperar()

print("5. apagado el módulo")
mods.poner("ingecad", "georref", False)
SI.aplicar(win)
ver("el lienzo no acepta arrastres", not win.viewport.acceptDrops() and arrastrar(foto) == (False, False))
mods.poner("ingecad", "georref", True)
SI.aplicar(win)
ver("prendido otra vez: acepta", win.viewport.acceptDrops())

print("FALLAS:", fallas if fallas else "ninguna")
if not fallas:
    print("TODO OK")
win.document.dirty = False if hasattr(win.document, "dirty") else None
sys.stdout.flush()
os._exit(0 if not fallas else 1)
