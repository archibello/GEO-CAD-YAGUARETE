"""Empalme estilo AutoCAD para IngeCAD (módulo «Empalme»): lo que el FILLET
nativo no hace (polilíneas, lado elegido en líneas que se cruzan) y lo que sí
hace bien, que se hereda igual (paralelas, radio 0, Deshacer)."""
import os, sys, tempfile, types, math
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from tools.base import ToolContext
from tools.edit import FilletTool

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
emp = import_module("ingecad_plugin_geocad.empalme")
dib = import_module("ingecad_plugin_geocad.dibujo")
mods = import_module("ingecad_plugin_geocad.modulos")
T = emp.EmpalmeTool
assert "GEOFILLET" in lp.spec.tools and lp.spec.tools["GEOFILLET"] is T


class Services:
    def __init__(self, document): self.index = GeometryIndex(document)
    def pick_entity(self, point):
        h = self.index.pick(point, 2.0)
        return self.index.entity(h) if h else None


class Harness:
    def __init__(self):
        self.document = Document(ezdxf.new("R2018")); self.history = History(self.document)
        self.services = Services(self.document); self.msgs = []; self.finished = False
        self.ctx = ToolContext(execute=self._execute, prompt=self.msgs.append, echo=self.msgs.append,
                               finish=lambda: setattr(self, "finished", True), services=self.services,
                               undo_last=self.history.undo)
    def _execute(self, cmd):
        self.history.execute(cmd); self.services.index.invalidate()
    @property
    def msp(self): return self.document.modelspace()


def empalmar(build, radio, p1, p2, shift=False, cls=T):
    h = Harness(); build(h.msp)
    t = cls(h.ctx); cls.radius = radio; t.start(); t.on_point(p1)
    if shift: t.shift = True
    t.on_point(p2)
    return h


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def lineas(h):
    return sorted(tuple(round(v, 6) for v in (e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
                  for e in h.msp.query("LINE"))


def pl(h):
    (p,) = list(h.msp.query("LWPOLYLINE"))
    return [(round(float(r[0]), 6), round(float(r[1]), 6), round(float(r[4]), 6)) for r in p.get_points("xyseb")], p.closed


B90 = round(math.tan(math.pi / 8), 6)          # bulge de un cuarto de círculo

# ---- 1. el nativo falla con polilíneas; el nuestro no -------------------------------------
h = empalmar(lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10)]), 2, (5, 0), (10, 5), cls=FilletTool)
assert pl(h)[0] == [(0, 0, 0), (10, 0, 0), (10, 10, 0)]           # nativo: no hizo nada
h = empalmar(lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10)]), 2, (5, 0), (10, 5))
assert pl(h) == ([(0, 0, 0), (8, 0, B90), (10, 2, 0), (10, 10, 0)], False)
h.history.undo(); assert pl(h)[0] == [(0, 0, 0), (10, 0, 0), (10, 10, 0)]   # se deshace
print("ok tramos de una polilínea")

# ---- 2. línea + polilínea: quedan unidas, la polilínea en cualquier sentido ----------------
for pts in ([(12, 2), (12, 10), (20, 10)], [(20, 10), (12, 10), (12, 2)]):
    h = empalmar(lambda m: (m.add_line((0, 0), (10, 0)), m.add_lwpolyline(pts)), 2, (5, 0), (12, 5))
    filas, cerrada = pl(h)
    assert [r[:2] for r in filas] == [(0, 0), (10, 0), (12, 2), (12, 10), (20, 10)] and not cerrada
    assert filas[1][2] == B90 and not list(h.msp.query("LINE"))
print("ok línea + polilínea")

# ---- 3. dos polilíneas por sus extremos: una sola (con y sin radio) ------------------------
build = lambda m: (m.add_lwpolyline([(-5, 5), (0, 0), (10, 0)]), m.add_lwpolyline([(12, 2), (12, 10), (20, 10)]))
h = empalmar(build, 2, (5, 0), (12, 5))
assert [r[:2] for r in pl(h)[0]] == [(-5, 5), (0, 0), (10, 0), (12, 2), (12, 10), (20, 10)]
assert any("unidas" in m for m in h.msgs)
h = empalmar(build, 0, (5, 0), (12, 5))
assert [r[:2] for r in pl(h)[0]] == [(-5, 5), (0, 0), (12, 0), (12, 10), (20, 10)]
print("ok dos polilíneas")

# ---- 4. líneas que se cruzan: se conserva el lado tocado ----------------------------------
cruz = lambda m: (m.add_line((0, 5), (10, 5)), m.add_line((5, 0), (5, 10)))
h = empalmar(cruz, 1, (1, 5), (5, 1))
assert lineas(h) == [(0, 5, 4, 5), (5, 4, 5, 0)]
(a,) = list(h.msp.query("ARC")); assert cerca((a.dxf.center.x, a.dxf.center.y, a.dxf.radius), (4, 4, 1))
h = empalmar(cruz, 1, (9, 5), (5, 9))
assert lineas(h) == [(5, 6, 5, 10), (10, 5, 6, 5)]
(a,) = list(h.msp.query("ARC")); assert cerca((a.dxf.center.x, a.dxf.center.y), (6, 6))
h = empalmar(cruz, 1, (9, 5), (5, 9), cls=FilletTool)              # el nativo se equivocaba de lado
assert lineas(h) != [(5, 6, 5, 10), (10, 5, 6, 5)]
print("ok lado elegido")

# ---- 5. lo que el nativo ya hacía bien sigue igual ----------------------------------------
h = empalmar(lambda m: (m.add_line((0, 0), (10, 0)), m.add_line((12, 2), (12, 10))), 0, (5, 0), (12, 6))
assert lineas(h) == [(0, 0, 12, 0), (12, 0, 12, 10)]                 # radio 0: esquina
h = empalmar(lambda m: (m.add_line((0, 0), (10, 0)), m.add_line((12, 2), (12, 10))), 3, (5, 0), (12, 6), shift=True)
assert lineas(h) == [(0, 0, 12, 0), (12, 0, 12, 10)] and not list(h.msp.query("ARC"))   # Mayús = esquina
h = empalmar(lambda m: (m.add_line((0, 0), (10, 0)), m.add_line((-5, 4), (20, 4))), 5, (8, 0), (3, 4))
(a,) = list(h.msp.query("ARC")); assert cerca((a.dxf.center.x, a.dxf.center.y, a.dxf.radius), (10, 2, 2))
print("ok lo heredado")

# ---- 6. cerradas, arcos y casos que no corresponden --------------------------------------
h = empalmar(lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True), 1, (5, 0), (0, 5))
filas, cerrada = pl(h)
assert cerrada and filas[0] == (0, 1, B90) and filas[1][:2] == (1, 0)
h = empalmar(lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10)]), 20, (5, 0), (10, 5))
assert any("fit" in m.lower() or "cabe" in m.lower() for m in h.msgs) and pl(h)[0][1] == (10, 0, 0)
h = empalmar(lambda m: (m.add_line((12, 5), (20, 5)), m.add_lwpolyline([(0, 0), (10, 0), (10, 10), (20, 10)])), 1, (15, 5), (10, 5))
assert any("EXTREMO" in m for m in h.msgs)                          # tramo interior: se explica
h = empalmar(lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)]), 1, (5, 0), (5, 5))
assert any("contiguos" in m for m in h.msgs)
print("ok casos límite")

# ---- 7. el módulo: F / FILLET / EMPALME abren el de GeoCAD sólo si está activo ------------
reg = {"FILLET": FilletTool, "GEOFILLET": T}
assert dib.herramienta_para("FILLET", None, reg) == "GEOFILLET"
assert dib.herramienta_para("LINE", None, reg) == "LINE"
mods.poner("ingecad", "empalme", False)
assert dib.herramienta_para("FILLET", None, reg) == "FILLET"          # apagado: el de IngeCAD
mods.poner("ingecad", "empalme", True)
assert dib.herramienta_para("FILLET", None, {"FILLET": FilletTool}) == "FILLET"   # sin registrar: el nativo
apagado = types.SimpleNamespace(plugins=types.SimpleNamespace(is_active=lambda p: False))
assert dib.herramienta_para("FILLET", apagado, reg) == "FILLET"       # plugin desactivado
class FakeController:
    def __init__(self): self.window = None; self.started = []
    def start_tool(self, name): self.started.append(name)
assert dib.envolver(FakeController, "start_tool", dib._envolver_start_tool)
c = FakeController(); c.start_tool("FILLET"); c.start_tool("LINE")
assert c.started == ["FILLET", "LINE"]                                # sin ALL_TOOL_CLASSES real: nativo
print("ok módulo")

# ---- 8. resaltado: lo que está bajo el cursor, lo ya elegido y el empalme que va a quedar --
def herramienta(build, radio=2):
    h = Harness(); build(h.msp); t = T(h.ctx); T.radius = radio; t.start()
    return h, t
h, t = herramienta(lambda m: (m.add_line((0, 0), (10, 0)), m.add_lwpolyline([(12, 2), (12, 10), (20, 10)])))
r = t.resaltado((5, 0.3))                                            # sobre la línea
assert r["cursor"] == [((0, 0), (10, 0))] and not r["elegido"] and not r["vista"]
r = t.resaltado((12.2, 5))                                           # sobre la polilínea: sólo ese tramo
assert r["cursor"] == [((12, 2), (12, 10))]
assert t.resaltado((50, 50)) == {"elegido": [], "cursor": [], "vista": []}   # nada debajo
t.on_point((5, 0))                                                   # primer objeto elegido
r = t.resaltado((12, 5))
assert r["elegido"] == [((0, 0), (10, 0))] and r["cursor"] == [((12, 2), (12, 10))]
v = r["vista"]; assert len(v) >= 2                                   # el arco, antes del clic
assert cerca(v[0][0], (10, 0)) or cerca(v[0][0], (12, 2))
assert {tuple(round(c, 6) for c in v[0][0]), tuple(round(c, 6) for c in v[-1][1])} == {(10, 0), (12, 2)}
assert all(abs(math.dist(q, (10, 2)) - 2) < 1e-6 for s_ in v for q in s_)   # radio 2, centro (10, 2)
r = t.resaltado((5, 0.2)); assert r["cursor"] == [] and r["elegido"]  # el mismo objeto: no se ofrece
T.radius = 50; assert t.resaltado((12, 5))["vista"] == []            # no cabe: sin vista previa
T.radius = 0
r = t.resaltado((12, 5))                                             # radio 0: la esquina
assert [tuple(tuple(round(c, 6) for c in q) for q in s_) for s_ in r["vista"]] == [((0, 0), (12, 0)), ((12, 0), (12, 10))]
# misma polilínea: el vértice que se redondearía
h, t = herramienta(lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10)]))
t.on_point((5, 0)); r = t.resaltado((10, 5))
assert r["elegido"] == [((0, 0), (10, 0))] and r["cursor"] == [((10, 0), (10, 10))]
assert r["vista"] and all(abs(math.dist(q, (8, 2)) - 2) < 1e-6 for s_ in r["vista"] for q in s_)
# tramo con arco y arcos/círculos: se resaltan enteros, como curvas
h, t = herramienta(lambda m: (m.add_circle((30, 30), 5), m.add_lwpolyline([(0, 0, 0, 0, 1), (10, 0)], format="xyseb")))
assert len(t.resaltado((35, 30))["cursor"]) > 20
assert all(abs(math.dist(q, (5, 0)) - 5) < 1e-6 for s_ in t.resaltado((5, -5))["cursor"] for q in s_)
# opción Polilínea: la polilínea entera; una línea no
h, t = herramienta(lambda m: (m.add_line((0, 20), (10, 20)), m.add_lwpolyline([(0, 0), (10, 0), (10, 10)])))
t.on_option("P"); assert len(t.resaltado((5, 0))["cursor"]) == 2 and t.resaltado((5, 20))["cursor"] == []
# el dibujo sobre la vista (Qt de mentira) y el envoltorio que nunca rompe la vista
class Pen:
    def __init__(self, color, ancho, estilo): self.color, self.ancho, self.estilo = color, ancho, estilo
class Painter:
    def __init__(self): self.pens = []; self.lineas = 0; self.saves = 0
    def save(self): self.saves += 1
    def restore(self): self.saves -= 1
    def setPen(self, p): self.pens.append(p)
    def drawLine(self, a, b): self.lineas += 1
qt = (Pen, lambda *c: c, lambda x, y: (x, y), types.SimpleNamespace(DashLine="--", SolidLine="-"))
h, t = herramienta(lambda m: (m.add_line((0, 0), (10, 0)), m.add_line((12, 2), (12, 10))))
T.radius = 2; t.on_point((5, 0))
vp = types.SimpleNamespace(tool_delegate=types.SimpleNamespace(tool=t, _cursor=(12, 5)),
                           _space_to_screen=lambda x, y: (x, -y))
pa = Painter(); n = dib.dibujar_resaltado(vp, pa, qt)
assert n == pa.lineas > 3 and pa.saves == 0
assert [q.ancho for q in pa.pens] == [5, 3, 2] and pa.pens[-1].estilo == "--"
vp.tool_delegate.tool = FilletTool(h.ctx); assert dib.dibujar_resaltado(vp, Painter(), qt) == 0   # el nativo: nada
class FakeViewport:
    def __init__(self): self.dibujos = 0; self.tool_delegate = None
    def _draw_tool_preview(self, p): self.dibujos += 1
assert dib.envolver(FakeViewport, "_draw_tool_preview", dib._envolver_vista)
fv = FakeViewport(); fv.tool_delegate = types.SimpleNamespace(tool=types.SimpleNamespace(
    resaltado=lambda c: 1 / 0), _cursor=(0, 0))
fv._draw_tool_preview(Painter()); assert fv.dibujos == 1                # error en el resaltado: la vista sigue
print("ok resaltado")
print("TODO OK EMPALME")
