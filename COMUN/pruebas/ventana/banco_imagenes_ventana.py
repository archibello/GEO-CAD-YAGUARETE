"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
¿lo que muestra la pantalla coincide con lo que dice el dibujo?

Nació de la prueba de Fernando del 24/10/2026: los agarres de una imagen no
coincidían con ella y la copia salía vacía. Las pruebas de COMUN/pruebas
corren sin Qt y no lo podían ver: IngeCAD dejaba las imágenes NUEVAS (pegar,
COPIA, GIRA con copia) en su capa provisoria, sin textura. Este banco lo
reproduce y comprueba el arreglo (redibujo_imagenes.py), el recorte con los
agarres (recorte_imagen.py) y que girar, alinear, escalar, simetría y
GEORREF sigan coincidiendo. Desde el recorte como operación: Enter con el
teclado de verdad (termina el recorte y NO repite el último comando; el
lienzo girado coincide en pantalla), Esc (cancela la operación entera) y U.

Uso (ver COMUN/LEEME_DESARROLLO.txt; necesita PySide6, ezdxf, numpy, Pillow):
    python banco_imagenes_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
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
import numpy as np
from PIL import Image as PILImage
from PySide6.QtWidgets import QApplication, QMessageBox
from ezdxf.math import Matrix44

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
RI = import_module("ingecad_plugin_geocad.recorte_imagen")
RD = import_module("ingecad_plugin_geocad.redibujo_imagenes")
G = import_module("ingecad_plugin_geocad.georref")
from core import actions, modify
from core.select import entity_grips
from views.main_window import MainWindow

tmp = Path(tempfile.mkdtemp(prefix="banco-"))
png = tmp / "plano.png"
PILImage.fromarray((np.random.rand(200, 400, 3) * 255).astype(np.uint8)).save(png)
fallas = []


def modulo(prendido):
    mods.guardar("ingecad", {"georref": prendido})
    RI._activo_cache[0] = RD._activo_cache[0] = 0.0


def esperar(win, s=15.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        if getattr(win, "_regen_worker", None) is None and not win.tools._merge_timer.isActive():
            break
        time.sleep(0.01)
    for _ in range(20):
        app.processEvents()


def pantalla(win, h):
    """(esquinas de la textura en pantalla, oculta) o None si no está."""
    scene = win.viewport._scene
    im = next((i for i in getattr(scene, "images", []) if i.handle == h), None)
    if im is None:
        return None
    ox, oy = scene.origin
    return (sorted({(round(float(c[0]) + ox, 3), round(float(c[1]) + oy, 3)) for c in im.corners}),
            h in getattr(win.viewport, "_hidden_images", set()))


def caja_dibujo(img):
    """El rectángulo que contiene el borde de la imagen (con un recorte en
    polígono, la textura es ese rectángulo)."""
    ps = [(round(p.x, 3), round(p.y, 3)) for p in img.boundary_path_wcs()]
    if img.dxf.get("clipping", 0) and len(set(ps)) != 4:
        xs, ys = [p[0] for p in ps], [p[1] for p in ps]
        return sorted({(x, y) for x in (min(xs), max(xs)) for y in (min(ys), max(ys))})
    if img.dxf.get("clipping", 0):
        from ingecad_plugin_geocad import georref as _G
        w, h = _G.tamano(img)
        i, u, v = img.dxf.insert, img.dxf.u_pixel, img.dxf.v_pixel
        return sorted({(round(i.x + a * u.x * w + b * v.x * h, 3), round(i.y + a * u.y * w + b * v.y * h, 3))
                       for a in (0, 1) for b in (0, 1)})
    return sorted(set(ps))


def comprobar(nombre, win, img, debe=True):
    p = pantalla(win, img.dxf.handle)
    ok = p is not None and not p[1] and p[0] == caja_dibujo(img)
    print(f"  [{nombre}] {'coincide' if ok else 'NO coincide'}"
          + ("" if ok == debe else "   <-- FALLA"))
    if ok != debe:
        fallas.append(nombre)


def ventana_con_imagen():
    win = MainWindow()
    win.new_document("m")
    d = win.document.doc.add_image_def(filename=str(png), size_in_pixel=(400, 200))
    img = win.document.modelspace().add_image(image_def=d, insert=(0, 0), size_in_units=(40, 20))
    win.document.dirty = True
    win.show(); app.processEvents()
    win.regen_in_memory(); esperar(win)
    return win, img


def nuevas(win, antes):
    return [e for e in win.document.modelspace() if e.dxftype() == "IMAGE" and e.dxf.handle not in antes]


def pegar(win, img, destino=None):
    win.tools.selection = {img.dxf.handle}
    win.tools.copy_selection(base=(0, 0)); esperar(win)
    s, b = win.tools.clipboard_data()
    (destino or win).tools._execute(actions.PasteCommand(
        s, 100 - b[0], -b[1], originals=getattr(win.tools, "_clipboard_originals", None)))


# ------------------------------------------------------------------ 1. cambiar una imagen
modulo(True)
print("1. Cambiar una imagen: la pantalla sigue al dibujo")
cambios = [
    ("GIRA 7,5°", lambda w, i: w.tools._execute(actions.rotate_entities([i], (0, 0), 7.5))),
    ("GIRA y U", lambda w, i: (w.tools._execute(actions.rotate_entities([i], (0, 0), 7.5)), esperar(w), w._cmd_undo())),
    ("ESCALA x2", lambda w, i: w.tools._execute(actions.scale_entities([i], (0, 0), 2.0))),
    ("SIMETRÍA", lambda w, i: w.tools._execute(actions.mirror_entities([i], (50, 0), (50, 10), keep_source=False))),
    ("ALINEAR", lambda w, i: w.tools._execute(modify.align_entities([i], [(0, 0), (40, 0)], [(10, 10), (48, 16)]))),
    ("GEORREF Helmert", lambda w, i: w.tools._execute(G.GeorrefCommand(i, Matrix44.z_rotate(math.radians(-7.5))))),
    ("GEORREF Polinómica 1", lambda w, i: w.tools._execute(G.GeorrefCommand(i, Matrix44([1, .15, 0, 0, .1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])))),
    ("recorte Ctrl", lambda w, i: w.tools._execute(RI.preparar(i, 2, (30, 5), w.document))),
    ("recorte Shift+Ctrl", lambda w, i: w.tools._execute(RI.preparar(i, 1, (25, 18), w.document, libre=True))),
    ("recorte Ctrl en un lado", lambda w, i: w.tools._execute(RI.preparar(i, 5, (31, 10), w.document, rol=RI.ROL_LADO))),
    ("recorte y U", lambda w, i: (w.tools._execute(RI.preparar(i, 2, (30, 5), w.document)), esperar(w), w._cmd_undo())),
]
for nombre, hacer in cambios:
    win, img = ventana_con_imagen()
    hacer(win, img); esperar(win)
    comprobar(nombre, win, img)
    win.close()

# ------------------------------------------------------------------ 2. crear una imagen
casos = [
    ("pegar en el mismo dibujo", lambda w, i: pegar(w, i)),
    ("GIRA con copia", lambda w, i: w.tools._execute(actions.rotate_entities([i], (0, 0), 7.5, copy=True))),
    ("COPIA", lambda w, i: w.tools._execute(actions.copy_entities([i], 0, 50))),
    ("pegar, U y rehacer", lambda w, i: (pegar(w, i), esperar(w), w._cmd_undo(), esperar(w), w._cmd_redo())),
]
for prendido in (False, True):
    modulo(prendido)
    print(f"2. Crear una imagen, módulo {'prendido (con el arreglo)' if prendido else 'apagado (IngeCAD como viene)'}")
    for nombre, hacer in casos:
        win, img = ventana_con_imagen()
        antes = {e.dxf.handle for e in win.document.modelspace()}
        hacer(win, img); esperar(win)
        debe = prendido or nombre == "pegar, U y rehacer"     # IngeCAD solo sólo acierta al rehacer
        for e in nuevas(win, antes):
            comprobar(nombre, win, e, debe)
        win.close()
    w1, img = ventana_con_imagen()
    w2 = MainWindow(); w2.new_document("m"); w2.show(); app.processEvents(); w2.regen_in_memory(); esperar(w2)
    pegar(w1, img, w2); esperar(w2)
    for e in nuevas(w2, set()):
        comprobar("pegar en OTRO dibujo", w2, e, prendido)
    w2.close(); w1.close()

# ------------------------------------------------------------------ 3. la operación de recorte: Enter y Esc
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
modulo(True)
print("3. Recorte como operación: Enter termina (lienzo girado), Esc cancela, U")


def verificar(nombre, ok):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'}")
    if not ok:
        fallas.append(nombre)


def soltar(win, img, k, pixel, libre=False):
    """Shift+Ctrl (o Ctrl) en el agarre de la esquina ``k``, soltado sobre el
    píxel de la original, con el controlador de IngeCAD."""
    win.tools.selection = {img.dxf.handle}
    grip = next(g for g in win.tools.grip_points() if g[3] == img.dxf.handle and g[2] == "corner" and g[4] == k)
    marca = RI.leer(img)
    x, y = RI.a_dibujo(img, marca[1] if marca else (0, 0, 400, 200), pixel)
    RI._ctrl, RI._shift = (lambda: True), (lambda: libre)
    try:
        win.tools.begin_grip_drag(grip)
        win.tools.update_grip_drag(x, y)
        win.tools.finish_grip_drag(x, y)
    finally:
        RI._ctrl = RI._shift = lambda: False
    esperar(win)


def textura(win, img):
    scene = win.viewport._scene
    im = next((i for i in getattr(scene, "images", []) if i.handle == img.dxf.handle), None)
    return None if im is None else tuple(im.pixels.shape[:2])


def historia(win):
    return win.command_line.history.toPlainText()


girado = [(60, 5), (156, 77), (108, 141), (12, 69)]        # el papel: 120 x 80 píxeles, girado 36,87°
win, img = ventana_con_imagen()
corridos = []
win.dispatcher._run = lambda nombre, args: corridos.append(nombre)   # qué repetiría el Enter
win.dispatcher.last_command = "REGEN"
for k, q in enumerate(girado):
    soltar(win, img, k, q, libre=True)
verificar("Shift+Ctrl con el controlador: el polígono del papel", RI.leer(img) is not None and RI.leer(img)[2] == girado)
verificar("aviso «Recortando: Enter termina, Esc cancela»", RI.AVISO in historia(win))
comprobar("recortando (polígono)", win, img)
esquinas_antes = sorted((round(p[0], 3), round(p[1], 3)) for p in RI.esquinas(img))
QTest.keyClick(win.viewport, Qt.Key_Return)                          # Enter sobre el dibujo, sin comando
esperar(win)
verificar("Enter no repite el último comando", corridos == [])
verificar("Enter: sin la marca, 120 x 80", RI.leer(img) is None and tuple(img.dxf.image_size)[:2] == (120, 80))
comprobar("Enter: lienzo girado, la pantalla sigue al dibujo", win, img)
verificar("Enter: el lienzo es el papel, en su lugar", caja_dibujo(img) == sorted(set(esquinas_antes)))
verificar("Enter: la textura es la imagen nueva", textura(win, img) == (80, 120))
QTest.keyClick(win.command_line.input, Qt.Key_Return)               # otra vez: sin operación, IngeCAD repite
esperar(win)
verificar("después, Enter repite como siempre", corridos == ["REGEN"])
win._cmd_undo(); esperar(win)
verificar("U deshace el Enter", RI.leer(img) is not None and RI.leer(img)[2] == girado)
comprobar("U del Enter", win, img)
verificar("U del Enter: la textura de la copia", textura(win, img) == (136, 144))
QTest.keyClick(win.command_line.input, Qt.Key_Escape)               # Esc: la operación entera vuelve atrás
esperar(win)
verificar("Esc: como antes del primer recorte",
          RI.leer(img) is None and Path(img.image_def.dxf.filename) == png and tuple(img.dxf.image_size)[:2] == (400, 200)
          and not img.dxf.get("clipping", 0))
comprobar("Esc: la pantalla sigue al dibujo", win, img)
verificar("Esc: la textura de la original", textura(win, img) == (200, 400))
verificar("Esc no repite ni corre nada", corridos == ["REGEN"])
win._cmd_undo(); esperar(win)
verificar("U deshace el Esc", RI.leer(img) is not None and RI.leer(img)[2] == girado)
comprobar("U del Esc", win, img)
QTest.keyClick(win.command_line.input, Qt.Key_Return)
esperar(win)
verificar("Enter (reabierta por el U)", RI.leer(img) is None and corridos == ["REGEN"])
comprobar("Enter después del U", win, img)
win.close()

win, img = ventana_con_imagen()                                     # Ctrl en rectángulo y un comando en el medio
corridos = []
win.dispatcher._run = lambda nombre, args: corridos.append(nombre)
win.dispatcher.last_command = "REGEN"
soltar(win, img, 1, (300, 50))
win.tools._execute(actions.rotate_entities([img], (0, 0), 20)); esperar(win)
QTest.keyClick(win.command_line.input, Qt.Key_Return); esperar(win)
verificar("Ctrl y GIRA: Enter termina sin girar el lienzo",
          corridos == [] and RI.leer(img) is None and tuple(img.dxf.image_size)[:2] == (300, 150))
comprobar("Ctrl y GIRA: Enter", win, img)
win.close()

if fallas:
    print("FALLAN:", ", ".join(fallas))
    sys.exit(1)
print("TODO OK")
