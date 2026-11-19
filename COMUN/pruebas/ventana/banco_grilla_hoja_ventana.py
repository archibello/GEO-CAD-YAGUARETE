"""Banco con la VENTANA REAL de IngeCAD: la grilla de hoja (3.85.0).

Fernando, 19/11/2026: una grilla milimetrada como la de Vectorworks, que no
se imprime, sólo con la hoja en mm (1 o 0,001); si no lo está, el botón la
pasa a mm; «casi imperceptible a la vista para que no interfiera con la
visibilidad de los objetos a imprimir».

* GeoCAD se activa como al arrancar IngeCAD y se abre un dibujo en metros.
* El botón está en la barra Ventanas gráficas, después del desplegable.
* Una presentación a 1 mm = 100 u (no está en mm) con una línea y una
  ventana gráfica: el botón la pasa a 1 mm = 0,001 y las escala; la línea
  mide lo mismo en el papel. Un U la deja como estaba.
* Se pinta de verdad (con OpenGL): la grilla tiñe la hoja apenas (ningún
  píxel cambia más que la opacidad elegida), la línea dibujada sigue igual,
  y fuera de la hoja no hay grilla. Sin OpenGL se espía la llamada.

Uso:
    flatpak run --filesystem=<repo> --filesystem=<ingecad> \\
        --env=QT_QPA_PLATFORM=wayland --command=python3 org.ingecad.IngeCAD -u \\
        banco_grilla_hoja_ventana.py <carpeta de IngeCAD> <repo>/INGECAD/codigo/geocad
Termina en «TODO OK». Un «violación de segmento» DESPUÉS no cuenta.
"""
import os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(int(os.environ.get("BANCO_ESPERA", "600")), exit=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
os.environ["INGECAD_SERIAL_REGEN"] = "1"
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtWidgets import QApplication, QMessageBox, QToolBar, QToolButton

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
G = import_module("ingecad_plugin_geocad.grilla_hoja")
VPM = import_module("views.viewport")
from views.main_window import MainWindow
from core import layouts as L
try:
    from core.version import __version__ as VERSION_INGECAD
except Exception:  # noqa: BLE001
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


mods = import_module("ingecad_plugin_geocad.modulos")
mods.guardar("ingecad", {})
if mods.nuevos("ingecad"):
    mods.aceptar_nuevos("ingecad")
win = MainWindow()
win.plugins.loaded["geocad"] = lp
ver("GeoCAD activo en la ventana", bool(win.plugins.activate("geocad"))
    or win.plugins.is_active("geocad"))
con_pantalla = os.environ.get("QT_QPA_PLATFORM") != "offscreen"
if con_pantalla:
    win.setWindowOpacity(0.0)        # pinta con OpenGL, sin verse
    win.resize(1200, 800)
    win.show()
    esperar(1.0)
win.new_document("m")
esperar(0.2)
win.document.doc.header["$INSUNITS"] = 6           # dibujo en metros
ver("paintGL y _draw_grid envueltos",
    getattr(VPM.Viewport.paintGL, "_puente_fabrica", None) is not None
    and getattr(VPM.Viewport._draw_grid, "_puente_fabrica", None) is G._envolver_draw_grid)

# ------------------------------------------------------------- el botón
barra = win.findChild(QToolBar, "viewports_toolbar")
boton = win.findChild(QToolButton, "geocad_grilla_hoja")
ver("botón en la barra Ventanas gráficas", barra is not None and boton is not None
    and boton.parent() is barra)
acciones = barra.actions() if barra is not None else []
pos = [i for i, a in enumerate(acciones) if barra.widgetForAction(a) is boton]
combo = getattr(win, "_vp_scale_combo", None)
pos_combo = [i for i, a in enumerate(acciones) if barra.widgetForAction(a) is combo]
ver("después del desplegable de escala", pos and pos_combo and pos[0] > pos_combo[0], f"{pos} {pos_combo}")
ver("botón apagado al empezar", boton is not None and not boton.defaultAction().isChecked())
ver("menú de intensidad con 3 opciones", boton is not None and boton.menu() is not None
    and len(boton.menu().actions()) == 3)

# ------------------------------------------------------------- la hoja a mm
win._new_layout_tab()
nombre = win._layout_names()[-1]
lay = win.document.doc.layouts.get(nombre)
L.page_setup_command(lay, 420.0, 297.0, (10.0, 10.0, 10.0, 10.0), "ISO A3",
                     fit_to_paper=False, scale=(1.0, 100.0)).do(win.document)
mm0 = G.mm_por_unidad(lay)
linea = lay.add_line((5000, 10000), (25000, 10000), dxfattribs={"color": 1})   # 200 mm de papel
win.switch_layout(nombre)
esperar()
ver("la hoja no está en mm (1 mm = 100 u)", not G.en_mm(lay), f"{mm0}")
G._confirmar = lambda w, t: True          # la ventanita: sí
boton.defaultAction().trigger()            # el clic del botón
esperar(0.5)
ver("la hoja pasó a 1 mm = 0,001", G.en_mm(lay) and abs(G.mm_por_unidad(lay) - 1000.0) < 1e-6)
largo = (linea.dxf.end.x - linea.dxf.start.x) * G.mm_por_unidad(lay)
ver("la línea mide lo mismo en el papel", abs(largo - 200.0) < 1e-6, f"{largo:.4f} mm")
ver("botón prendido", boton.defaultAction().isChecked() and G.prendida())
win._cmd_undo()
esperar(0.3)
ver("U deja la hoja como estaba", not G.en_mm(lay) and abs(G.mm_por_unidad(lay) - mm0) < 1e-12
    and abs(linea.dxf.start.x - 5000) < 1e-9)
ver("sin la hoja en mm la grilla no se dibuja", G._a_dibujar(win.viewport) is None)
G.alternar(win, win.command_line.echo)      # apagar
G.alternar(win, win.command_line.echo)      # prender otra vez: vuelve a pasarla a mm
esperar(0.5)
ver("prendida y en mm otra vez", G.prendida() and G.en_mm(lay))
if hasattr(win, "regen_in_memory"):
    win.regen_in_memory()
lienzo = win.viewport
for _ in range(100):
    if lienzo._scene is not None and getattr(lienzo._scene, "paper", None):
        break
    esperar(0.1)
ver("el lienzo tiene la hoja", G._a_dibujar(lienzo) is not None)

# ------------------------------------------------------------- pintar
llamadas, errores = [], []
dibujar = G.dibujar
def espia(vp, gl, hoja, mm):
    llamadas.append((hoja, mm))
    try:
        return dibujar(vp, gl, hoja, mm)
    except Exception as e:  # noqa: BLE001 -- el envoltorio la callaría
        errores.append(repr(e))
        raise
G.dibujar = espia
lienzo.zoom_extents()
esperar(0.3)


def captura():
    lienzo.repaint()
    esperar(0.3)
    return lienzo.grabFramebuffer()


img_con = captura()
G.guardar(prender=False)
img_sin = captura()
G.guardar(prender=True)
G.dibujar = dibujar
if not llamadas or not con_pantalla:
    print("  (sin OpenGL no pinta: se midió el envoltorio y la hoja, no el dibujado)")
else:
    ver("al pintar la hoja se dibuja la grilla", not errores, f"{len(llamadas)} vez/veces {errores[:1]}")
    hoja, mm = llamadas[-1]
    paso, segs = G.lineas(hoja, mm, lienzo._view_world_rect(), float(lienzo.view.scale))
    print(f"    hoja {hoja}, {lienzo.view.scale:.1f} px/u, paso {paso} mm, {len(segs)} líneas")
    # la hoja en píxeles del lienzo
    import numpy as np

    def arr(img):
        img = img.convertToFormat(img.Format.Format_RGBA8888)
        ptr = img.constBits()
        a = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes()).reshape(
            img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3].astype(int)
        return a
    a_con, a_sin = arr(img_con), arr(img_sin)
    dif = np.abs(a_con - a_sin).max(axis=2)
    cambiados = int((dif > 0).sum())
    ver("la grilla cambia píxeles de la hoja", cambiados > 1000, f"{cambiados} px")
    tope = round(max(G.alfas()) / 255 * 255) + 3
    ver("casi imperceptible: ningún píxel cambia más que su opacidad",
        int(dif.max()) <= tope, f"máx {int(dif.max())} (tope {tope})")
    if int(dif.max()) > tope:
        ys, xs = np.nonzero(dif > tope)
        for y, x in list(zip(ys, xs))[:6]:
            print(f"    px ({x},{y}): sin {a_sin[y, x].tolist()} con {a_con[y, x].tolist()}")
        print(f"    {len(ys)} px pasan el tope")
    alfa_lienzo = None
    try:
        img = img_con.convertToFormat(img_con.Format.Format_RGBA8888)
        alfa_lienzo = int(np.frombuffer(img.constBits(), dtype=np.uint8, count=img.sizeInBytes())
                          .reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), 3][dif > 0].min())
    except Exception:  # noqa: BLE001
        pass
    ver("el lienzo sigue opaco donde está la grilla", alfa_lienzo == 255, str(alfa_lienzo))
    azul = (a_con[..., 2] - a_con[..., 0])[dif > 0]
    ver("el tinte es celeste", float(azul.mean()) > 0, f"{float(azul.mean()):.1f}")
    # la línea roja se ve igual
    rojo = (a_sin[..., 0] > 240) & (a_sin[..., 1] < 20) & (a_sin[..., 2] < 20)   # el trazo, sin su borde suavizado
    ver("la línea dibujada no cambia", rojo.any() and int(dif[rojo].max()) == 0,
        f"{int(rojo.sum())} px rojos")
    # fuera de la hoja nada: con zoom de la hoja entera, los bordes del lienzo
    borde = np.concatenate([dif[:, :3].ravel(), dif[:, -3:].ravel()])
    ver("fuera de la hoja no hay grilla", int(borde.max()) == 0)
    img_con.save(str(Path(os.environ.get("BANCO_CAPTURA", tempfile.gettempdir())) / "grilla_hoja_con.png"))
    # 3.85.2: acercada (4 px por mm de papel), las tres medidas con su grosor
    G.dibujar = espia
    del llamadas[:]
    w_, h_ = lienzo.width(), lienzo.height()
    lienzo.view.zoom_at(w_ / 3, h_ / 3, 4.0 / (lienzo.view.scale / mm))
    cerca = captura()
    G.dibujar = dibujar
    paso_c, segs_c = G.lineas(hoja, mm, lienzo._view_world_rect(), float(lienzo.view.scale))
    ver("acercada se ven las líneas de 1 mm", paso_c == 1 and {x[4] for x in segs_c} == {0, 1, 2},
        f"{lienzo.view.scale / 1000.0:.1f} px/mm")
    cerca.save(str(Path(os.environ.get("BANCO_CAPTURA", tempfile.gettempdir())) / "grilla_hoja_cerca.png"))

# ------------------------------------------------------------- 3.85.3: presentación nueva
# Fernando, 19/11/2026 («no se activa»): dibujo en metros, presentación nueva
# sin tocar la página (dice 1 mm = 0,001 pero la hoja se ve en mm)
win._new_layout_tab()
esperar(0.3)
nueva = win._layout_names()[-1]
win.switch_layout(nueva)
esperar(0.5)
lay_n = win.document.doc.layouts.get(nueva)
G.guardar(prender=True)
datos_n = G._a_dibujar(lienzo)
hoja_vista = getattr(lienzo._scene, "paper", None) or {}
print(f"    {nueva}: página {G.mm_por_unidad(lay_n):g} mm/u, hoja vista {hoja_vista.get('mm_per_unit')} mm/u")
ver("presentación nueva: la grilla va (sigue la hoja como se ve)", datos_n is not None, str(datos_n and datos_n[1]))
if con_pantalla and datos_n is not None:
    lienzo.zoom_extents()
    esperar(0.3)
    con_n = captura()
    G.guardar(prender=False)
    sin_n = captura()
    G.guardar(prender=True)
    import numpy as np
    def arr2(img):
        img = img.convertToFormat(img.Format.Format_RGBA8888)
        return np.frombuffer(img.constBits(), dtype=np.uint8, count=img.sizeInBytes()).reshape(
            img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3].astype(int)
    n_px = int((np.abs(arr2(con_n) - arr2(sin_n)).max(axis=2) > 0).sum())
    ver("presentación nueva: la grilla se ve en pantalla", n_px > 1000, f"{n_px} px")

# ------------------------------------------------------------- 3.85.4: escalas
# Fernando, 19/11/2026 («grave problema con las escalas»): en la presentación
# nueva la hoja y su primera ventana nacían en mm sobre una página en metros;
# a 1:100 un cuadrado de 10 m tiene que medir 100 mm = 10 módulos de 10 mm.
x0, y0, x1, y1 = L.paper_frame(lay_n)["sheet"]
ancho_mm = (x1 - x0) * G.mm_por_unidad(lay_n)
ver("presentación nueva: la A3 mide 420 mm a la escala de la página", abs(ancho_mm - 420.0) < 1e-6, f"{ancho_mm:g}")
flotantes = [v for v in lay_n if v.dxftype() == "VIEWPORT" and int(v.dxf.get("id", 0) or 0) != 1]
ver("presentación nueva: su ventana entra en la hoja", flotantes
    and flotantes[0].dxf.width * G.mm_por_unidad(lay_n) <= 420.0, str(flotantes and flotantes[0].dxf.width))
if flotantes:
    win.history.execute(L.xp_zoom_command(flotantes[0], 0.01))      # 1:100
    lado = 10.0 * L.viewport_scale(flotantes[0]) * G.mm_por_unidad(lay_n)
    ver("1:100: 10 m = 100 mm de papel (10 módulos)", abs(lado - 100.0) < 1e-9, f"{lado:g} mm")

print("TODO OK" if not fallas else f"FALLAS: {fallas}")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
