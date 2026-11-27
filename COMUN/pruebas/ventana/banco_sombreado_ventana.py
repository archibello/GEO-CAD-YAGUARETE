"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
sombreado Custom del HATCH (3.99.0).

GeoCAD activo como al arrancar IngeCAD y todo tecleado en la línea de comandos:
* GeoCAD carga con GEOHATCH (no choca con el HATCH de IngeCAD);
* la ventana Hatch real trae «Custom»: una sola muestra, el grupo Custom en vez
  de Angle y Scale, «Elegir en el dibujo <»; Ninguna apaga lo de las líneas y
  pone fondo blanco;
* H, Custom, clic dentro (escrito 5,5) e Intro: un HATCH _USER doble a 45°,
  con fondo y grosor; U lo quita;
* «Elegir en el dibujo <»: la ventana se cierra, pide origen y segundo punto y
  vuelve con ellos;
* dos áreas separadas: dos sombreados; el botón SOMBREADOCUSTOM abre en Custom;
* HATCHEDIT (doble clic) abre en Custom, sin «Elegir en el dibujo <», y cambia
  la separación; a ANSI31 deja de ser Custom;
* módulo apagado: H y la ventana como los trae IngeCAD.

Uso (PySide6, ezdxf):
    python banco_sombreado_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
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
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialogButtonBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
S = import_module("ingecad_plugin_geocad.sombreado")
SH = import_module("ingecad_plugin_geocad.sombreado_herramienta")
mods = import_module("ingecad_plugin_geocad.modulos")
mods.guardar("ingecad", {})
if mods.nuevos("ingecad"):
    mods.aceptar_nuevos("ingecad")
from views.main_window import MainWindow
from views.hatch_dialog import HatchDialog
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


vistos = []


def responder(*pasos):
    """Contesta las ventanas Hatch que se abran, en orden: cada paso recibe la
    ventana y la deja lista (OK, Cancelar o el botón que toque)."""
    cola = list(pasos)

    def mirar():
        d = QApplication.activeModalWidget()
        if isinstance(d, HatchDialog) and cola:
            vistos.append(d)
            cola.pop(0)(d)
        if cola:
            QTimer.singleShot(30, mirar)
    QTimer.singleShot(30, mirar)


def ok(d):
    d.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()


def custom(d, **valores):
    d.category.setCurrentIndex(d.category.findData("GEOCUSTOM"))
    p = d._geo_custom
    if "lineas" in valores:
        p.lineas.setCurrentIndex(p.lineas.findData(valores["lineas"]))
    if "separacion" in valores:
        p.separacion.setValue(valores["separacion"])
    if "direccion" in valores:
        p.direccion.setValue(valores["direccion"])
    if "origen" in valores:
        p.ox.setValue(valores["origen"][0]); p.oy.setValue(valores["origen"][1])
    if "fondo" in valores:
        p._con_rgb(valores["fondo"])
    if "grosor" in valores:
        p.grosor.setCurrentIndex(p.grosor.findData(valores["grosor"]))
    if "separados" in valores:
        p.separados.setChecked(valores["separados"])


def hatches():
    return [e for e in win.document.modelspace() if e.dxftype() == "HATCH"]


win = MainWindow()
win.plugins.loaded["geocad"] = lp           # como IngeCAD al arrancar
ver("GeoCAD activo", bool(win.plugins.activate("geocad")) or win.plugins.is_active("geocad"))
from views.tool_controller import ALL_TOOL_CLASSES
ver("GEOHATCH registrada; HATCH sigue siendo de IngeCAD",
    ALL_TOOL_CLASSES.get("GEOHATCH") is SH.GeoHatchTool
    and ALL_TOOL_CLASSES.get("HATCH") is not SH.GeoHatchTool and "RUMBOS" in ALL_TOOL_CLASSES)
win.new_document("r")
win.show(); esperar()
doc = win.document.doc
msp = doc.modelspace()
for x in (0, 20):
    msp.add_lwpolyline([(x, 0), (x + 10, 0), (x + 10, 10), (x, 10)], close=True)
win.document.dirty = True
win.regen_in_memory() if hasattr(win, "regen_in_memory") else None
esperar()

print("1. la ventana Hatch real con Custom")
d = HatchDialog(win, {"pattern": "SOLID", "scale": 1.0, "angle": 0.0, "color": 256, "_puede_pedir": True})
cats = [d.category.itemText(i) for i in range(d.category.count())]
ver("Category trae Custom", "Custom" in cats, str(cats))
custom(d)
ver("una sola muestra CUSTOM", d.gallery.count() == 1 and d.gallery.item(0).text() == "CUSTOM")
ver("grupo Custom a la vista; Angle y Scale escondidos",
    not d._geo_custom.isHidden() and d.angle.isHidden() and d.scale.isHidden())
ver("«Elegir en el dibujo <» a la vista", not d._geo_custom.elegir.isHidden())
ver("Dirección sólo se ve (se da con dos puntos); el Ángulo se escribe, respecto de ella",
    d._geo_custom.direccion.isReadOnly() and not d._geo_custom.giro.isReadOnly()
    and d._geo_custom.layout().labelForField(d._geo_custom.giro).text() == "Ángulo")
custom(d, lineas="ninguna")
p = d._geo_custom
ver("Ninguna: separación y grosor apagados, fondo blanco",
    not p.separacion.isEnabled() and not p.grosor.isEnabled() and p.fondo.currentData() == (255, 255, 255))
custom(d, lineas="dobles", separacion=0.15)
ver("separación con punto decimal (0.1500)", p.separacion.text() == "0.1500" and p.giro.text() == "0.0000",
    p.separacion.text())
custom(d, lineas="ninguna")
s = d.settings()
ver("settings() de Custom", s["pattern"] == "CUSTOM" and s["custom"]["lineas"] == "ninguna", str(s.get("custom")))
d.category.setCurrentIndex(d.category.findData("ANSI"))
ver("otra categoría: el grupo se esconde", d._geo_custom.isHidden() and not d.angle.isHidden())
d.deleteLater()

print("1b. estilos guardados (3.99.2)")
from PySide6.QtWidgets import QInputDialog
SU = import_module("ingecad_plugin_geocad.sombreado_ui")
d = HatchDialog(win, {"pattern": "SOLID", "scale": 1.0, "angle": 0.0, "color": 256})
custom(d, lineas="dobles", separacion=0.3, fondo=(128, 128, 128), grosor=15)
d.color.setCurrentIndex(d.color.findData(3))
_get = QInputDialog.getText
QInputDialog.getText = staticmethod(lambda *a, **k: ("Piso gris", True))
d._geo_custom.guardar.click()
QInputDialog.getText = _get
textos = [d.gallery.item(i).text() for i in range(d.gallery.count())]
ver("«Guardar estilo...» lo deja en la galería con su nombre", textos == ["CUSTOM", "Piso gris"]
    and d.gallery.currentItem().text() == "Piso gris", str(textos))
d.deleteLater()
d = HatchDialog(win, {"pattern": "CUSTOM", "scale": 1.0, "angle": 0.0, "color": 256,
                      "custom": {"lineas": "simples", "separacion": 2.0, "origen": (7, 8), "direccion": 45}})
ver("en otra ventana, el estilo sigue ahí", d.gallery.count() == 2 and d.gallery.item(1).text() == "Piso gris")
d.gallery.setCurrentRow(1)
p = d._geo_custom
ver("clic en el estilo: carga líneas, separación, fondo, grosor y color; origen y dirección quedan",
    p.lineas.currentData() == "dobles" and abs(p.separacion.value() - 0.3) < 1e-9
    and p.fondo.currentData() == (128, 128, 128) and p.grosor.currentData() == 15
    and d.color.currentData() == 3 and p.ox.value() == 7 and p.direccion.value() == 45)
ver("settings() con el estilo puesto", d.settings()["custom"]["separacion"] == 0.3 and d.settings()["pattern"] == "CUSTOM")
S.renombrar_estilo("Piso gris", "Piso"); SU._rellenar(d, S.PREFIJO + "Piso")
ver("renombrar", [d.gallery.item(i).text() for i in range(d.gallery.count())] == ["CUSTOM", "Piso"])
S.borrar_estilo("Piso"); SU._rellenar(d, S.CUSTOM)
ver("borrar", d.gallery.count() == 1)
d.deleteLater()

print("2. H, Custom, clic dentro e Intro")
responder(lambda d: (custom(d, lineas="dobles", separacion=0.5, direccion=30.0, origen=(1.0, 1.0),
                            fondo=(200, 225, 255), grosor=35), ok(d)))
escribir("H")
esperar(0.5)
ver("H arranca la de GeoCAD", isinstance(win.tools.tool, SH.GeoHatchTool), type(win.tools.tool).__name__)
escribir("5,5")
escribir()
hs = hatches()
ver("un HATCH _USER doble paralelo a la dirección (30°/120°), fondo y grosor",
    len(hs) == 1 and hs[0].dxf.pattern_name == "_USER" and hs[0].dxf.pattern_double == 1
    and abs(hs[0].dxf.pattern_angle - 30) < 1e-9 and hs[0].bgcolor == (200, 225, 255)
    and hs[0].dxf.lineweight == 35 and win.tools.tool is None,
    str([(h.dxf.pattern_name, h.dxf.get("pattern_angle")) for h in hs]))
escribir("U")
ver("U lo quita", not hatches())

print("3. Elegir en el dibujo <: origen y dirección")
responder(lambda d: d._geo_custom.elegir.click(), ok)
escribir("H")
esperar(0.5)
pr = win.command_line.prompt.text() if hasattr(win.command_line, "prompt") else ""
ver("pide el origen", isinstance(win.tools.tool, SH.GeoHatchTool) and win.tools.tool._pedir == "origen", pr)
ver("al pedir el origen, la cruz (con referencias a objeto)", win.tools.cursor_mode() == "point",
    win.tools.cursor_mode())
escribir("2,3")
ver("pide el segundo punto", win.tools.tool._pedir == "direccion")
escribir("2,13")
esperar(0.5)
c = S.custom_de(win.tools.tool.settings)
ver("la ventana volvió con origen 2,3 y dirección 90°",
    len(vistos) == 3 and c["origen"] == (2.0, 3.0) and abs(c["direccion"] - 90.0) < 1e-9, str(c))
escribir("5,5"); escribir()
hs = hatches()
ver("el sombreado pasa por el origen elegido, paralelo a la dirección (90°)",
    len(hs) == 1 and abs(hs[0].dxf.pattern_angle - 90) < 1e-9
    and abs(hs[0].pattern.lines[0].base_point.x - 2) < 1e-9)

print("4. dos áreas separadas y el botón SOMBREADOCUSTOM")
escribir("U")
responder(lambda d: (ver("el botón abre en Custom", d.category.currentData() == "GEOCUSTOM"),
                     custom(d, separados=True), ok(d)))
win._invoke_command("GEOHATCHCUSTOM")
esperar(0.5)
escribir("5,5"); escribir("25,5"); escribir()
ver("dos sombreados, uno por área", len(hatches()) == 2, str(len(hatches())))

print("5. HATCHEDIT")
h = hatches()[0]
responder(lambda d: (ver("abre en Custom sin «Elegir en el dibujo <»",
                         d.category.currentData() == "GEOCUSTOM" and d._geo_custom.elegir.isHidden()),
                     custom(d, separacion=2.0), ok(d)))
win.tools.edit_hatch(h)
esperar(0.3)
ver("separación 2 con un U", abs(h.dxf.pattern_scale - 2.0) < 1e-9 and S.leer_custom(h)["separacion"] == 2.0)
responder(lambda d: (d.category.setCurrentIndex(d.category.findData("ANSI")),
                     d.gallery.setCurrentRow(0), ok(d)))
win.tools.edit_hatch(h)
esperar(0.3)
ver("a ANSI deja de ser Custom", S.leer_custom(h) is None and h.dxf.pattern_name.startswith("ANSI"),
    h.dxf.pattern_name)

print("6. agarres en el medio de cada lado")
h = hatches()[1]
win.tools.selection = {h.dxf.handle}
for _ in range(5):
    app.processEvents()
puntos = list(win.tools.grip_points())
medios = [g for g in puntos if g[2] == "mid" and g[3] == h.dxf.handle]
ver("ningún agarre en el centro, fuera de la figura (3.101.0)",
    not [p for p in puntos if p[2] == "center" and p[3] == h.dxf.handle],
    str([p[2] for p in puntos if p[3] == h.dxf.handle]))
ver("el controlador de IngeCAD ve un agarre en el medio de cada lado", len(medios) == len(h.paths[0].vertices),
    "%d medios, %d vértices" % (len(medios), len(h.paths[0].vertices)))
from core import select as SEL
g = medios[0]
antes = [tuple(v[:2]) for v in h.paths[0].vertices]
ver("arrastrar el del medio mueve el lado", SEL.apply_grip_edit(h, g[4], "mid", (g[0], g[1] - 1.0))
    and [tuple(v[:2]) for v in h.paths[0].vertices] != antes)
AG = import_module("ingecad_plugin_geocad.agarres_ingecad")
nuevo = AG.agregar_vertice(h, g[4], (g[0], g[1] - 1.0))
ver("agregar un vértice en ese lado", len(h.paths[0].vertices) == len(antes) + 1
    and SEL.entity_grips(h)[nuevo][2] == "vertex")
win.tools.selection = set()

print("7. clic sobre un objeto y contorno abierto")
def borrar_sombreados():
    """Como el usuario: elegidos y ERASE (borrarlos por debajo deja a IngeCAD 0.7.0
    y anteriores con handles muertos en la lista de redibujo)."""
    if hatches():
        win.tools.selection = {h.dxf.handle for h in hatches()}
        for _ in range(5):
            app.processEvents()
        escribir("ERASE")
        esperar(0.3)


borrar_sombreados()
abierta = msp.add_lwpolyline([(40, 0), (50, 0), (50, 10), (40, 10)])          # sin el lado izquierdo
win.regen_in_memory() if hasattr(win, "regen_in_memory") else None
esperar()
responder(lambda d: (custom(d, lineas="simples", separacion=1.0), ok(d)))
escribir("H"); esperar(0.5)
escribir("45,5"); escribir()
ver("clic adentro de una polilínea abierta: se toma cerrada", len(hatches()) == 1, str(len(hatches())))
escribir("U")
responder(lambda d: (custom(d), ok(d)))
escribir("H"); esperar(0.5)
escribir("O")                    # 3.101.1: los objetos, con Elegir objetos (O)
escribir("50,5")                                                              # sobre el lado derecho
t = win.tools.tool
ver("Objetos(O), clic sobre el objeto: es el contorno", isinstance(t, SH.GeoHatchTool) and abierta in t.selected,
    str(getattr(t, "selected", None)))
escribir()
ver("sombreado con ese objeto", len(hatches()) == 1)

print("7b. TRIM y JOIN con sombreados (3.100.0)")
E = import_module("ingecad_plugin_geocad.sombreado_edicion")
borrar_sombreados()
cuadro = msp.add_lwpolyline([(60, 0), (70, 0), (70, 10), (60, 10)], close=True)
responder(lambda d: (custom(d, lineas="simples", separacion=1.0, fondo=(200, 225, 255)), ok(d)))
escribir("H"); esperar(0.5); escribir("65,5"); escribir()
corte = msp.add_line((64, -1), (64, 11))
win.regen_in_memory() if hasattr(win, "regen_in_memory") else None
esperar()
ver("un sombreado para recortar", len(hatches()) == 1)
escribir("TR"); esperar(0.3)
t = win.tools.tool
ver("TR arranca la de GeoCAD", isinstance(t, SH.GeoTrimTool), type(t).__name__)
preseleccion = getattr(t, "on_selection", None)
t.on_selection([corte])
pick = win.tools.pick_entity((62.0, 5.0))
ver("el clic adentro del sombreado lo toma (pick_entity)", pick is not None and pick.dxftype() in ("HATCH", "LWPOLYLINE"),
    getattr(pick, "dxftype", lambda: None)())
t.apply_to_entity(hatches()[0], (62.0, 5.0))
hs = hatches()
ver("TRIM borra la parte del clic: queda 6 x 10, con su fondo",
    len(hs) == 1 and abs(E.superficie(hs[0]) - 60) < 1e-6 and hs[0].bgcolor == (200, 225, 255),
    str([E.superficie(h) for h in hs]))
QTest.keyClick(win.command_line.input, Qt.Key_Escape); esperar(0.2)
escribir("U")
ver("U lo devuelve", len(hatches()) == 1 and abs(E.superficie(hatches()[0]) - 100) < 1e-6)
otro = msp.add_lwpolyline([(70, 0), (74, 0), (74, 10), (70, 10)], close=True)
responder(lambda d: (custom(d, lineas="simples", separacion=1.0, fondo=(200, 225, 255)), ok(d)))
escribir("H"); esperar(0.5); escribir("72,5"); escribir()
win.tools.selection = {h.dxf.handle for h in hatches()}
for _ in range(5):
    app.processEvents()
escribir("J")
hs = hatches()
ver("J con dos sombreados del mismo estilo: uno solo de 14 x 10",
    len(hs) == 1 and abs(E.superficie(hs[0]) - 140) < 1e-6 and win.tools.tool is None,
    str([E.superficie(h) for h in hs]))

print("7c. el puntero de elección (3.101.0)")
borrar_sombreados()
responder(lambda d: (custom(d, lineas="simples", separacion=1.0), ok(d)))
escribir("H"); esperar(0.5)
t = win.tools.tool
ver("al elegir áreas, el cuadradito (como «Designe un punto interno» de AutoCAD)",
    isinstance(t, SH.GeoHatchTool) and win.tools.cursor_mode() == "pick", win.tools.cursor_mode())
escribir("5,5"); escribir("25,5")
win.tools._cursor = (15.0, 15.0)                    # el mouse sobre el dibujo
tramos = win.tools.preview_segments()
ver("las dos áreas elegidas se ven resaltadas", len(tramos) == 8, str(len(tramos)))
escribir("H")
ver("H (desHacer) quita la última", win.tools.tool is t and len(t._regiones) == 1
    and len(win.tools.preview_segments()) == 4, str(len(t._regiones)))
escribir("25,5"); escribir("Q")
ver("Q pasa a quitar contornos", t.mode == "quitar")
escribir("5,5"); escribir()
ver("clic en una elegida la quita; Intro vuelve a sumar", t.mode == "pick" and len(t._regiones) == 1
    and win.tools.tool is t)
escribir()
hs = hatches()
ver("Intro: el sombreado sólo con la que quedó", len(hs) == 1 and abs(E.superficie(hs[0]) - 100) < 1e-6
    and min(v[0] for v in hs[0].paths[0].vertices) >= 20, str([E.superficie(h) for h in hs]))

print("7d. resaltado al pasar y al elegir (3.101.1)")
from PySide6.QtGui import QImage, QPainter
DIB = import_module("ingecad_plugin_geocad.dibujo")


def pintado(x, y, rgba, r=3):
    """Píxeles del color (rgba sobre negro) alrededor de (x, y) en lo que pinta la vista."""
    v = win.viewport
    img = QImage(v.width(), v.height(), QImage.Format_RGB32); img.fill(0)
    q = QPainter(img)
    # IngeCAD 0.8 pinta la herramienta en _draw_tool_feedback; las anteriores, en
    # _draw_tool_preview (el que envuelve dibujo.py)
    (getattr(v, "_draw_tool_feedback", None) or v._draw_tool_preview)(q)
    q.end()
    a = rgba[3] / 255.0
    quiero = [round(c * a) for c in rgba[:3]]
    sx, sy = v._space_to_screen(x, y)
    n = 0
    for i in range(int(sx) - r, int(sx) + r + 1):
        for j in range(int(sy) - r, int(sy) + r + 1):
            if 0 <= i < img.width() and 0 <= j < img.height():
                c = img.pixelColor(i, j)
                if all(abs(u - w) <= 3 for u, w in zip((c.red(), c.green(), c.blue()), quiero)):
                    n += 1
    return n


def pasar(x, y):
    sx, sy = win.viewport._space_to_screen(x, y)
    wx, wy = win.viewport.view.screen_to_world(sx, sy)
    win.tools.on_hover(wx, wy)
    t = win.tools.tool
    if t is not None:
        t._area_cuando = 0.0                     # sin la pausa entre búsquedas


SUAVE = DIB.ESTILO_RESALTADO["sombreado_cursor"][0]
FUERTE = DIB.ESTILO_RESALTADO["sombreado_elegido"][0]
ROJO = DIB.ESTILO_RESALTADO["sombreado_quitar"][0]
borrar_sombreados()
responder(lambda d: (custom(d, lineas="simples", separacion=1.0), ok(d)))
escribir("H"); esperar(0.5)
t = win.tools.tool
pasar(5.0, 5.0)
ver("al pasar por el vacío: su silueta, suave", pintado(0.0, 5.0, SUAVE) > 2 and pintado(0.0, 5.0, FUERTE) == 0,
    f"{pintado(0.0, 5.0, SUAVE)} / {pintado(0.0, 5.0, FUERTE)}")
ver("la otra área no se resalta", pintado(20.0, 5.0, SUAVE) == 0)
escribir("5,5"); pasar(25.0, 5.0)
ver("elegida: más intensa y gruesa; la de al lado, suave",
    pintado(0.0, 5.0, FUERTE) > pintado(20.0, 5.0, SUAVE) > 2,
    f"{pintado(0.0, 5.0, FUERTE)} / {pintado(20.0, 5.0, SUAVE)}")
escribir("S"); pasar(25.0, 5.0)
ver("Seleccionar objetos: en el vacío nada", pintado(20.0, 5.0, SUAVE) == 0)
pasar(20.0, 5.0)
ver("Seleccionar objetos: sobre el borde, el objeto", pintado(20.0, 5.0, SUAVE) > 2, str(pintado(20.0, 5.0, SUAVE)))
escribir("Q"); pasar(5.0, 5.0)
ver("Quitar contornos: en rojo lo que se quitaría", pintado(0.0, 5.0, ROJO) > 2, str(pintado(0.0, 5.0, ROJO)))
QTest.keyClick(win.command_line.input, Qt.Key_Escape); esperar()

print("7e. Contornos en la ventana: Elegir islas / Elegir objetos / Quitar (3.101.1)")
visto = {}


def apretar(clave):
    def paso(d):
        p = getattr(d, "_geo_panel_contornos", None)
        visto["panel"] = p is not None
        if p is None:
            ok(d)
            return
        visto["marcado"] = [k for k, b in p.botones.items() if b.isChecked()]
        visto["quitar"] = p.botones["quitar"].isEnabled()
        p.botones[clave].click()
    return paso


borrar_sombreados()
responder(apretar("select"))
escribir("H"); esperar(0.5)
t = win.tools.tool
ver("la ventana trae el grupo Contornos, arranca en Elegir islas, Quitar apagado",
    visto.get("panel") and visto.get("marcado") == ["pick"] and visto.get("quitar") is False, str(visto))
ver("Elegir objetos: sigue en el dibujo eligiendo objetos", t is not None and t.mode == "select"
    and "Elegir objetos" in win.command_line.prompt_label.text() if hasattr(win.command_line, "prompt_label")
    else t.mode == "select", t.mode if t else "sin herramienta")
escribir("20,0")
ver("en Objetos, el clic en el borde toma el objeto", len(t.selected) == 1, str(len(t.selected)))
responder(apretar("pick"))
escribir("T"); esperar(0.5)
ver("al volver a la ventana: marcado Elegir objetos, Quitar encendido",
    visto.get("marcado") == ["select"] and visto.get("quitar") is True, str(visto))
ver("Elegir islas desde la ventana", t.mode == "pick", t.mode)
escribir("0,0")
ver("en Islas, el clic sobre un borde no toma el objeto", len(t.selected) == 1, str(len(t.selected)))
responder(apretar("quitar"))
escribir("T"); esperar(0.5)
ver("Quitar contornos desde la ventana", t.mode == "quitar", t.mode)
QTest.keyClick(win.command_line.input, Qt.Key_Escape); esperar()

print("8. módulo apagado")
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": False})
d = HatchDialog(win, {"pattern": "SOLID", "scale": 1.0, "angle": 0.0, "color": 256})
ver("la ventana sin Custom", "Custom" not in [d.category.itemText(i) for i in range(d.category.count())])
d.deleteLater()
responder(lambda d: d.reject())
escribir("H")
esperar(0.5)
ver("H es el de IngeCAD", not isinstance(win.tools.tool, SH.GeoHatchTool), type(win.tools.tool).__name__)
if win.tools.tool is not None:
    QTest.keyClick(win.command_line.input, Qt.Key_Escape)
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": True})
win.document.dirty = False
win.close()
print("TODO OK" if not fallas else "FALLAS: " + ", ".join(fallas))
sys.stdout.flush()
os._exit(0 if not fallas else 1)
