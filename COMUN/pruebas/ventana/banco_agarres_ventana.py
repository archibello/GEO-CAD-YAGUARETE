"""Banco con la VENTANA REAL de IngeCAD: el módulo «Agarres de vértices» (3.70), con clics y
teclas de verdad. Pedido de Fernando del 05/11/2026: lo mismo que la 3.69 en QGIS.

Uso (ver COMUN/LEEME_DESARROLLO.txt; necesita PySide6 y ezdxf):
    python banco_agarres_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento» DESPUÉS: no cuenta.
"""
import os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(280, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtCore import Qt, QEvent, QPoint, QPointF
from PySide6.QtGui import QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
AG = import_module("ingecad_plugin_geocad.agarres_ingecad")
from views.main_window import MainWindow
try:
    from core.version import __version__ as VERSION_INGECAD
except Exception:  # noqa: BLE001 -- las viejas no lo tienen
    VERSION_INGECAD = "0"
#: IngeCAD 0.8.0 hace solo, sin el módulo, lo escrito con el agarre tomado y Mayús + derecho
#: (cambios e57c356 y ac79782): sin el módulo ya no «suelta» ni ignora lo escrito
NATIVOS = tuple(int(x) for x in VERSION_INGECAD.split(".")[:2] if x.isdigit()) >= (0, 8)
print("IngeCAD", VERSION_INGECAD, "(con lo nativo de la 0.8)" if NATIVOS else "")
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def esperar(s=0.05):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        time.sleep(0.005)


def pts(e):
    return [(round(float(p[0]), 1), round(float(p[1]), 1)) for p in e.get_points("xy")]


class B:
    """Una ventana con un dibujo; construir(msp) agrega los objetos."""

    def __init__(self, construir):
        self.win = MainWindow()
        self.win.new_document("m")
        self.msp = self.win.document.modelspace()
        self.objs = construir(self.msp)
        self.c = self.win.tools
        self.ecos = []
        cl = self.win.command_line
        orig = cl.echo
        cl.echo = lambda t, *a, **k: (self.ecos.append(str(t)), orig(t, *a, **k))[1]
        self.win.document.dirty = True
        self.win.resize(1200, 800)
        self.win.show(); esperar()
        self.win.regen_in_memory(); esperar(0.3)
        self.win.viewport.zoom_extents(); esperar(0.1)
        self.win.viewport.setFocus(); esperar()
        AG.aplicar(self.win)
        self.c.osnap_on = False

    def px(self, x, y):
        sx, sy = self.win.viewport.view.world_to_screen(x, y)
        return QPoint(int(round(sx)), int(round(sy)))

    def _mover(self, p):
        # con evento propio: en «offscreen», QTest.mouseMove llega tarde
        v = self.win.viewport
        QApplication.sendEvent(v, QMouseEvent(QEvent.MouseMove, QPointF(p), QPointF(v.mapToGlobal(p)),
                                              Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        esperar()

    def mover(self, x, y):
        self._mover(self.px(x, y))

    def clic(self, x, y, mod=Qt.NoModifier):
        p = self.px(x, y)
        self._mover(p)
        QTest.keyPress(self.win.viewport, Qt.Key_Shift) if mod & Qt.ShiftModifier else None
        QTest.mouseClick(self.win.viewport, Qt.LeftButton, mod, p); esperar(0.1)
        QTest.keyRelease(self.win.viewport, Qt.Key_Shift) if mod & Qt.ShiftModifier else None
        esperar()

    def escribir(self, txt, visor=False):
        w = self.win.viewport if visor else self.win.command_line.input
        if txt:
            QTest.keyClicks(w, txt); esperar()
        QTest.keyClick(w, Qt.Key_Return); esperar(0.1)

    def esc(self):
        QTest.keyClick(self.win.command_line.input, Qt.Key_Escape); esperar(0.1)

    def elegir(self, *objs):
        self.c.selection = {o.dxf.handle for o in objs}
        self.c._grips_cache = None
        self.c.changed.emit(); esperar()

    def caliente(self):
        return self.c._grip_drag is not None

    def marcas(self):
        return AG._marcas(self.c)

    def deshacer(self):
        self.win.history.undo(); self.c._invalidate_geometry(); esperar(0.1)

    def rehacer(self):
        self.win.history.redo(); self.c._invalidate_geometry(); esperar(0.1)

    def cerrar(self):
        if self.c._grip_drag is not None:
            self.c.cancel()
        self.win.close(); esperar()


def pl(msp):
    return [msp.add_lwpolyline([(0, 0), (100, 0), (100, 100)]), msp.add_line((160, 40), (160, 90))]


print("== lo escrito con el agarre tomado")
for txt, fin in (("@10,5", (110, 105)), ("@20<90", (100, 120)), ("120,50", (120, 50))):
    for visor in (False, True):
        b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(130, 100)
        b.escribir(txt, visor)
        ver(f"{txt} {'visor' if visor else 'línea'}", pts(p)[2] == fin and not b.caliente()
            and b.c.tool is None, pts(p))
        if not visor:
            b.deshacer(); ver(f"{txt} U", pts(p)[2] == (100, 100), pts(p))
        b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(130, 100); b.escribir("25")
ver("distancia hacia el cursor", abs(pts(p)[2][0] - 125) < 0.3 and abs(pts(p)[2][1] - 100) < 0.3, pts(p)); b.cerrar()
b = B(pl); p = b.objs[0]; b.c.ortho_on = True; b.elegir(p); b.clic(100, 100); b.mover(130, 110); b.escribir("25")
ver("distancia con ORTO", pts(p)[2] == (125, 100), pts(p)); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(159, 89)
b.escribir("END"); ver("END no suelta", b.caliente())
b.mover(159.7, 89.7); b.clic(159.7, 89.7)     # más cerca que su propio vértice: la caché de referencias se arma recién acá y lo ve
ver("END, referencia de una vez", pts(p)[2] == (160, 90) and b.c.osnap_override is None, pts(p)); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(130, 130); b.escribir("L")
ver("un comando no arranca con el agarre tomado", b.c.tool is None and b.caliente(), b.ecos[-1:])
b.escribir("abc,de"); ver("lo inválido tampoco lo suelta", b.caliente())
if NATIVOS:   # IngeCAD 0.8: Intro sigue con el agarre (X o Esc lo sueltan); GeoCAD se aparta
    b.escribir(""); ver("Intro: IngeCAD 0.8 sigue con el agarre", b.caliente(), pts(p))
    b.escribir("X"); ver("X lo suelta sin mover", not b.caliente() and pts(p)[2] == (100, 100), pts(p))
else:
    b.escribir(""); ver("Intro cancela", not b.caliente() and pts(p)[2] == (100, 100), pts(p))
b.escribir("L"); ver("sin agarre, los comandos andan", b.c.tool is not None)
b.c.cancel(); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 50); b.mover(120, 50); b.escribir("@20,0")
ver("escrito en el agarre del medio", pts(p) == [(0, 0), (120, 0), (120, 100)], pts(p)); b.cerrar()
b = B(lambda m: [m.add_circle((50, 50), 20)]); b.elegir(b.objs[0]); b.clic(50, 50); b.mover(60, 60); b.escribir("@10,0")
ver("otros objetos: el centro de un círculo", tuple(b.objs[0].dxf.center)[:2] == (60, 50)); b.cerrar()


print("== marcar varios")
b = B(pl); p = b.objs[0]; b.elegir(p)
b.clic(100, 100, Qt.ShiftModifier)
ver("Mayús marca sin tomar", len(b.marcas()) == 1 and not b.caliente() and pts(p)[2] == (100, 100), len(b.marcas()))
b.clic(100, 0, Qt.ShiftModifier); b.clic(0, 0, Qt.ShiftModifier)
ver("tres marcados", len(b.marcas()) == 3)
b.clic(0, 0, Qt.ShiftModifier); ver("Mayús otra vez desmarca", len(b.marcas()) == 2)
b.mover(50, 50)
img = QImage(1200, 800, QImage.Format_RGB32); img.fill(0)
q = QPainter(img); b.win.viewport._draw_grips(q); q.end()
sx, sy = b.win.viewport._space_to_screen(100, 100)
c = img.pixelColor(int(sx), int(sy)); ver("el marcado se ve rojo", (c.red(), c.green(), c.blue()) == (255, 0, 0), c.name())
sx, sy = b.win.viewport._space_to_screen(0, 0)
c = img.pixelColor(int(sx), int(sy)); ver("el otro no", c.red() != 255, c.name())
b.clic(100, 100); ver("clic en un marcado lo toma", b.caliente())
b.mover(110, 120)
ver("los dos siguen al cursor", abs(pts(p)[1][0] - 110) < 1 and abs(pts(p)[1][1] - 20) < 1
    and abs(pts(p)[2][0] - 110) < 1, pts(p))
b.esc(); ver("Esc vuelve todo", pts(p) == [(0, 0), (100, 0), (100, 100)] and not b.caliente(), pts(p))
ver("Esc deja los marcados", len(b.marcas()) == 2)
b.clic(100, 100); b.mover(110, 120); b.escribir("@10,20")
ver("escrito con marcados", pts(p) == [(0, 0), (110, 20), (110, 120)], pts(p))
ver("al soltar se desmarcan", not b.marcas())
b.deshacer(); ver("un solo deshacer", pts(p) == [(0, 0), (100, 0), (100, 100)], pts(p))
b.rehacer(); ver("rehacer", pts(p) == [(0, 0), (110, 20), (110, 120)], pts(p))
b.deshacer(); b.elegir(p)
b.clic(100, 100, Qt.ShiftModifier); b.clic(100, 0); b.mover(100, 10); b.clic(100, 10)
ver("clic en uno no marcado: se mueve sólo él", abs(pts(p)[1][1] - 10) < 0.3 and pts(p)[2] == (100, 100) and not b.marcas(), pts(p))
b.esc(); ver("Esc en reposo deselecciona", not b.c.selection)
b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100, Qt.ShiftModifier)
b.c.clear_selection(); ver("deseleccionar saca los marcados", not b.marcas()); b.elegir(p)
ver("y no vuelven", not b.marcas())
b.cerrar()
b = B(pl); p, l = b.objs; b.elegir(p, l)
b.clic(100, 100, Qt.ShiftModifier); b.clic(160, 90, Qt.ShiftModifier); b.clic(100, 100); b.mover(110, 100); b.clic(110, 100)
ver("marcados de dos objetos", abs(pts(p)[2][0] - 110) < 1 and abs(l.dxf.end.x - 170) < 1 and abs(l.dxf.end.y - 90) < 1,
    (pts(p), tuple(l.dxf.end)[:2]))
b.deshacer(); ver("U de dos objetos", pts(p)[2] == (100, 100) and tuple(l.dxf.end)[:2] == (160, 90))
b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 50, Qt.ShiftModifier)
ver("Mayús en el medio no hace nada", not b.caliente() and not b.marcas()); b.cerrar()


print("== agregar vértice")
b = B(pl); p = b.objs[0]; b.elegir(p)
b.clic(100, 50, Qt.ControlModifier)
ver("Ctrl en el medio toma el vértice nuevo", b.caliente() and pts(p) == [(0, 0), (100, 0), (100, 50), (100, 100)], pts(p))
b.mover(130, 50); b.clic(130, 50)
ver("el nuevo se ubica", len(pts(p)) == 4 and abs(pts(p)[2][0] - 130) < 1 and pts(p)[3] == (100, 100), pts(p))
b.deshacer(); ver("U lo saca", pts(p) == [(0, 0), (100, 0), (100, 100)], pts(p))
b.rehacer(); ver("rehacer lo pone", len(pts(p)) == 4, pts(p))
b.deshacer(); b.elegir(p)
b.clic(50, 0, Qt.ControlModifier); b.mover(50, 40); b.esc()
ver("Esc lo saca", pts(p) == [(0, 0), (100, 0), (100, 100)] and not b.caliente(), pts(p))
b.elegir(p); b.clic(50, 0, Qt.ControlModifier); b.escribir("@0,-10")
ver("escrito en el nuevo", pts(p) == [(0, 0), (50, -10), (100, 0), (100, 100)], pts(p))
b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 50); b.mover(120, 50); b.clic(120, 50)
# el cursor cae en un píxel: X = 120 ± medio píxel (0.8.0: 119,95 por el encuadre)
ver("el clic solo sigue moviendo el tramo", pts(p)[0] == (0, 0) and all(abs(q[0] - 120) < 0.2 for q in pts(p)[1:])
    and [q[1] for q in pts(p)] == [0, 0, 100], pts(p)); b.cerrar()
b = B(lambda m: [m.add_lwpolyline([(0, 0), (100, 0), (100, 100)], close=True)]); p = b.objs[0]; b.elegir(p)
b.clic(50, 50, Qt.ControlModifier); b.mover(40, 60); b.clic(40, 60)
ver("en el tramo de cierre", len(pts(p)) == 4 and pts(p)[:3] == [(0, 0), (100, 0), (100, 100)] and p.closed, pts(p)); b.cerrar()
b = B(lambda m: [m.add_lwpolyline([(0, 0, 0, 0, 1.0), (100, 0)])]); p = b.objs[0]; b.elegir(p)
b.clic(50, 0, Qt.ControlModifier)
ver("tramo curvo: no y lo dice", not b.caliente() and len(pts(p)) == 2 and any("tramo recto" in e for e in b.ecos), b.ecos[-1:]); b.cerrar()
b = B(lambda m: [m.add_line((0, 0), (100, 0))]); b.elegir(b.objs[0]); b.clic(50, 0, Qt.ControlModifier)
ver("una línea no: y lo dice", not b.caliente() and tuple(b.objs[0].dxf.end)[:2] == (100, 0)); b.cerrar()


print("== borrar vértices con Supr")
def cuatro(m):
    return [m.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)]), m.add_line((160, 40), (160, 90))]
b = B(cuatro); p, l = b.objs; b.elegir(p)
b.clic(100, 0, Qt.ShiftModifier); QTest.keyClick(b.win.viewport, Qt.Key_Delete); esperar(0.3)
ver("Supr borra el marcado", pts(p) == [(0, 0), (100, 100), (0, 100)] and p in list(b.msp), pts(p))
ver("sigue designado, sin marcas", p.dxf.handle in b.c.selection and not b.marcas())
g = {(round(x), round(y)) for x, y, *_r in b.c.grip_points()}
ver("los agarres nuevos", (100, 0) not in g and (100, 100) in g, sorted(g))
b.deshacer(); ver("U lo devuelve", pts(p) == [(0, 0), (100, 0), (100, 100), (0, 100)], pts(p))
b.rehacer(); ver("rehacer lo borra", len(pts(p)) == 3, pts(p))
b.deshacer(); b.elegir(p)
for x, y in ((0, 0), (100, 0), (100, 100)):
    b.clic(x, y, Qt.ShiftModifier)
b.win._cmd_delete(); esperar(0.2)
ver("no se borra lo que la dejaría sin forma", len(pts(p)) == 4 and any("sin forma" in e for e in b.ecos), pts(p))
b.elegir(p); b.clic(100, 100); ver("toma", b.caliente()); b.win._cmd_delete(); esperar(0.2)
ver("Supr con un agarre en la mano no borra nada", p in list(b.msp) and b.caliente())
b.esc(); b.elegir(p, l); b.clic(160, 90, Qt.ShiftModifier); b.win._cmd_delete(); esperar(0.2)
ver("el extremo de una línea no se borra", l in list(b.msp) and any("sin cambios" in e for e in b.ecos))
b.elegir(p); b.win._cmd_delete(); esperar(0.2)
ver("sin marcas, Supr borra el objeto", p not in list(b.msp))
b.cerrar()


print("== compartidos")
def dos(m):
    return [m.add_lwpolyline([(0, 0), (50, 50)]), m.add_lwpolyline([(50, 50), (100, 0)])]
b = B(dos); a, c = b.objs; b.elegir(a, c); b.clic(50, 50); b.mover(50, 80)
ver("siguen juntos", abs(pts(a)[1][1] - 80) < 1 and abs(pts(c)[0][1] - 80) < 1, (pts(a), pts(c)))
b.clic(50, 80); esperar(0.5)
ver("los dos designados se mueven", abs(pts(a)[1][1] - 80) < 1 and abs(pts(c)[0][1] - 80) < 1, (pts(a), pts(c)))
ver("no quedan escondidos", not (getattr(b.win.viewport, "_hidden_handles", None) or set()) & {a.dxf.handle, c.dxf.handle})
h = b.c.index.pick((50, 79.5), 1.0)
ver("se los puede designar en el lugar nuevo", h in (a.dxf.handle, c.dxf.handle), h)
b.deshacer(); ver("un deshacer para los dos", pts(a)[1] == (50, 50) and pts(c)[0] == (50, 50), (pts(a), pts(c)))
b.cerrar()
b = B(dos); a, c = b.objs; b.elegir(a); b.clic(50, 50); b.mover(50, 80); b.clic(50, 80)
ver("el no designado no se toca", pts(c)[0] == (50, 50) and abs(pts(a)[1][1] - 80) < 1, (pts(a), pts(c))); b.cerrar()
b = B(dos); a, c = b.objs; b.elegir(a, c); b.clic(50, 50); b.mover(50, 80); b.esc()
ver("Esc los vuelve", pts(a)[1] == (50, 50) and pts(c)[0] == (50, 50), (pts(a), pts(c))); b.cerrar()
def tres(m):
    return [m.add_lwpolyline([(0, 0), (50, 50), (100, 0)]), m.add_lwpolyline([(50, 100), (50, 50), (100, 100)])]
b = B(tres); a, c = b.objs; b.elegir(a, c); b.clic(50, 50, Qt.ShiftModifier); b.win._cmd_delete(); esperar(0.3)
ver("Supr borra el compartido en los dos", len(pts(a)) == 2 and len(pts(c)) == 2, (pts(a), pts(c)))
b.deshacer(); ver("U en los dos", len(pts(a)) == 3 and len(pts(c)) == 3)
b.cerrar()
def tramo(m):
    return [m.add_lwpolyline([(0, 0), (100, 0), (100, 50)]), m.add_lwpolyline([(0, 0), (100, 0), (100, -50)])]
b = B(tramo); a, c = b.objs; b.elegir(a, c); b.clic(50, 0); b.mover(50, 10); b.clic(50, 10)
ver("tramo compartido: se mueve en los dos", abs(pts(a)[0][1] - 10) < 1 and abs(pts(c)[0][1] - 10) < 1, (pts(a), pts(c))); b.cerrar()
b = B(tramo); a, c = b.objs; b.elegir(a, c); b.clic(50, 0, Qt.ControlModifier); b.mover(50, 10)
ver("agregar en el tramo compartido", len(pts(a)) == 4 and len(pts(c)) == 4, (pts(a), pts(c)))
b.clic(50, 10); ver("agregado", abs(pts(a)[1][1] - 10) < 1 and abs(pts(c)[1][1] - 10) < 1, (pts(a), pts(c)))
b.deshacer(); ver("U en los dos", len(pts(a)) == 3 and len(pts(c)) == 3); b.cerrar()
b = B(lambda m: [m.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 0)])]); p = b.objs[0]; b.elegir(p)
b.clic(0, 0); b.mover(10, 10); b.clic(10, 10)
ver("los dos extremos de un anillo abierto", abs(pts(p)[0][0] - 10) < 1 and abs(pts(p)[3][0] - 10) < 1, pts(p)); b.cerrar()


print("== lo de IngeCAD sigue igual")
def iguales(m):
    return [m.add_line((0, 0), (100, 0)), m.add_line((0, 0), (100, 0))]
b = B(iguales); seq = []
for _ in range(3):
    b.clic(30, 0); seq.append(next(iter(b.c.selection)))
ver("clics repetidos pasan al de abajo", seq[0] != seq[1] and seq[0] == seq[2], seq); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.c.osnap_on = True; b.clic(100, 100); b.mover(159.2, 89.3); b.clic(159.2, 89.3)
ver("referencias", pts(p)[2] == (160, 90), pts(p)); b.cerrar()
b = B(pl); p = b.objs[0]; b.c.ortho_on = True; b.elegir(p); b.clic(100, 100); b.mover(130, 112); b.clic(130, 112)
ver("ORTO", abs(pts(p)[2][1] - 100) < 0.01, pts(p)); b.cerrar()


print("== menú de referencias con el agarre tomado")
def derecho(b, x, y, mod):
    QTest.mouseClick(b.win.viewport, Qt.RightButton, mod, b.px(x, y)); esperar(0.1)
def menu_de(b):
    return getattr(b.win, "_osnap_menu", None)
def opcion(menu, texto):
    return next(a for a in menu.actions() if a.text() == texto)
for nombre, mod in (("Mayús", Qt.ShiftModifier), ("Ctrl", Qt.ControlModifier)):
    b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(130, 110); derecho(b, 130, 110, mod); m = menu_de(b)
    ver(f"{nombre} + derecho abre el menú y no suelta", m is not None and m.isVisible() and b.caliente(), pts(p))
    ver(f"{nombre}: el vértice sigue donde estaba", abs(pts(p)[2][0] - 130) < 1, pts(p))
    m.close(); esperar(); b.mover(140, 110); ver("cerrar el menú: sigue tomado", b.caliente() and abs(pts(p)[2][0] - 140) < 1, pts(p))
    b.c.cancel(); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(150, 85); derecho(b, 150, 85, Qt.ShiftModifier); m = menu_de(b)
if not NATIVOS:   # en la 0.8 el menú es el de IngeCAD, como él lo arma
    ver("Desde y Medio entre 2 puntos, apagados", not m.actions()[0].isEnabled() and not m.actions()[1].isEnabled())
opcion(m, "Endpoint").trigger(); m.close(); esperar()
ver("elegir Final no suelta", b.caliente() and b.c.osnap_override == frozenset({"END"}), b.c.osnap_override)
b.mover(158, 88); b.mover(159.7, 89.7); b.clic(159.7, 89.7)
ver("engancha con lo elegido", pts(p)[2] == (160, 90) and not b.caliente(), pts(p))
ver("dura un punto", b.c.osnap_override is None); b.cerrar()
b = B(pl); p, l = b.objs; b.elegir(p); b.clic(100, 100, Qt.ShiftModifier); b.clic(100, 0, Qt.ShiftModifier); b.clic(100, 100); b.mover(150, 85)
derecho(b, 150, 85, Qt.ShiftModifier); m = menu_de(b); ver("con varios marcados también", m.isVisible() and b.caliente())
opcion(m, "Endpoint").trigger(); m.close(); esperar(); b.mover(158, 88); b.mover(159.7, 89.7); b.clic(159.7, 89.7)
ver("los marcados llegan con la referencia", pts(p)[2] == (160, 90) and pts(p)[1] == (160, -10), pts(p)); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(130, 110); derecho(b, 130, 110, Qt.NoModifier)
ver("el derecho solo sigue cancelando", not b.caliente() and pts(p)[2] == (100, 100), pts(p)); b.cerrar()
b = B(pl); b.win._osnap_menu = None; p = b.objs[0]; b.elegir(p); AG.quitar(b.win); b.clic(100, 100); b.mover(130, 110); derecho(b, 130, 110, Qt.ShiftModifier)
if NATIVOS:   # IngeCAD 0.8: abre su propio menú y sigue con el agarre
    ver("sin el módulo, IngeCAD 0.8 sigue con el agarre", b.caliente() and "_geocad_agarres_filtro" not in vars(b.win))
else:
    ver("sin el módulo, como IngeCAD: suelta", not b.caliente() and menu_de(b) is None and "_geocad_agarres_filtro" not in vars(b.win))
b.cerrar()


print("== la marca de la referencia se ve con el agarre tomado")
def marca_pintada(b, x, y):
    """¿Hay píxeles del color de la marca alrededor de (x, y), en lo que pinta el visor?"""
    v = b.win.viewport
    img = QImage(v.width(), v.height(), QImage.Format_RGB32); img.fill(0)
    q = QPainter(img); v._draw_grips(q)
    if NATIVOS:
        v._draw_tool_feedback(q)     # IngeCAD 0.8 la pinta ahí (49197aa); GeoCAD ya no
    q.end()
    sx, sy = v._space_to_screen(x, y)
    r = int(v.MARKER_SIZE) + 3
    color = v.MARKER_COLOR.rgb()
    return sum(img.pixel(i, j) == color for i in range(int(sx) - r, int(sx) + r)
               for j in range(int(sy) - r, int(sy) + r))
b = B(pl); p = b.objs[0]; b.c.osnap_on = True; b.elegir(p); b.clic(100, 100)
b.mover(130, 70); ver("lejos de todo: sin marca", b.c.snap_hit is None and marca_pintada(b, 130, 70) == 0)
b.mover(159.5, 89.5)
ver("referencia de siempre: la marca se ve", b.c.snap_hit is not None and marca_pintada(b, 160, 90) > 10, marca_pintada(b, 160, 90))
b.c.cancel(); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100); b.mover(150, 85); derecho(b, 150, 85, Qt.ShiftModifier); m = menu_de(b)
opcion(m, "Midpoint").trigger(); m.close(); esperar()
b.mover(159.5, 64.5); ver("elegida en el menú: la marca se ve", marca_pintada(b, 160, 65) > 10, marca_pintada(b, 160, 65))
b.clic(159.5, 64.5); ver("y queda ahí", pts(p)[2] == (160, 65), pts(p))
ver("soltado: sin marca", marca_pintada(b, 160, 65) == 0); b.cerrar()
b = B(pl); p = b.objs[0]; b.c.osnap_on = True; b.elegir(p); AG.quitar(b.win); b.clic(100, 100); b.mover(159.5, 89.5)
ver("sin el módulo, como IngeCAD: " + ("se ve (0.8)" if NATIVOS else "no se ve"),
    b.c.snap_hit is not None and (marca_pintada(b, 160, 90) > 10) == NATIVOS); b.c.cancel(); b.cerrar()


print("== módulo apagado")
b = B(pl); p = b.objs[0]; b.elegir(p); b.clic(100, 100, Qt.ShiftModifier)
ver("con marcas", len(b.marcas()) == 1)
mods.guardar("ingecad", {"agarres": False}); AG.aplicar(b.win)
c = b.win.tools
ver("sin rastro", not {"begin_grip_drag", "update_grip_drag", "finish_grip_drag", "on_text", "delete_selection",
                        "grip_overlay_entities", "_geocad_agarres"} & set(vars(c))
    and "_draw_grips" not in vars(b.win.viewport), sorted(set(vars(c)) & {"on_text", "_geocad_agarres"}))
b.clic(100, 100, Qt.ShiftModifier); ver("Mayús toma, como IngeCAD", b.caliente())
b.mover(130, 100); b.escribir("@10,5")
if NATIVOS:   # IngeCAD 0.8 lo toma solo
    ver("lo escrito va, como IngeCAD 0.8", pts(p)[2] == (110, 105), pts(p))
else:
    ver("lo escrito no va", b.caliente() and abs(pts(p)[2][0] - 130) < 1, pts(p))
b.c.cancel(); b.c.selection = {p.dxf.handle}; b.c._grips_cache = None; esperar()
b.win._cmd_delete(); esperar(0.1); ver("Supr borra el objeto", p not in list(b.msp))
mods.guardar("ingecad", {"agarres": True}); b.cerrar()
b = B(pl); p = b.objs[0]; b.elegir(p); AG.aplicar(b.win); AG.aplicar(b.win); b.clic(100, 100); b.mover(130, 100); b.escribir("@10,5")
ver("aplicar varias veces no lo apila", pts(p)[2] == (110, 105) and not b.caliente(), pts(p)); b.deshacer()
ver("un solo U", pts(p)[2] == (100, 100)); b.cerrar()

print("TODO OK" if not fallas else f"FALLAS: {fallas}")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
