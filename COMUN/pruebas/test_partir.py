"""PARTEENPUNTO (BREAKATPOINT) para IngeCAD (módulo «Partir en punto»): corte
exacto sobre el objeto, también en polilíneas cerradas, vértices y tramos en
arco, sin perder propiedades ni el vínculo con QGIS; referencias sumadas
mientras se elige el punto; vista previa de los dos pedazos."""
import os, sys, tempfile, types, math
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from core import modify
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
par = import_module("ingecad_plugin_geocad.partir")
dib = import_module("ingecad_plugin_geocad.dibujo")
enl = import_module("ingecad_plugin_geocad.enlace")
mods = import_module("ingecad_plugin_geocad.modulos")
T = par.PartirTool
assert lp.spec.tools.get("BREAKATPOINT") is T
_y = import_module("ingecad_plugin_geocad.yaguarete")   # 3.13.0: van en la barra Yaguareté Tools
_b = [o for o, _m in _y.elegidas(mods.estado("ingecad"))]
assert _b == ["RECTANG", "TEXT", "STRETCH", "BREAKATPOINT", "CHAMFER", "FILLET"]
assert not {"FILLET", "CHAMFER", "BREAKATPOINT"} & {i.command for i in lp.spec.toolbar}


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
                               undo_last=self._undo)
    def _execute(self, cmd):
        self.history.execute(cmd); self.services.index.invalidate()
    def _undo(self):
        self.history.undo(); self.services.index.invalidate()
    @property
    def msp(self): return self.document.modelspace()


def partir(build, pick, punto, multiple=()):
    h = Harness(); build(h.msp)
    t = T(h.ctx); t.start(); t.on_point(pick)
    if multiple:
        t.on_option("M")
        for q in multiple: t.on_point(q)
    else:
        t.on_point(punto)
    return h, t


R = lambda v: round(float(v), 6)
def plines(h):
    return sorted(([tuple(R(c) for c in (r[0], r[1], r[2], r[3], r[4])) for r in p.get_points("xyseb")], p.closed)
                  for p in h.msp.query("LWPOLYLINE"))
def lines(h):
    return sorted(tuple(R(v) for v in (e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
                  for e in h.msp.query("LINE"))


# ---- 1. línea: el punto va SOBRE la línea (proyección), propiedades intactas -------------
def linea(m):
    e = m.add_line((0, 0), (10, 0), dxfattribs={"layer": "CALLES", "color": 3}); return e
h, t = partir(linea, (5, 0), (4, 1.5))                       # punto fuera: se proyecta
assert lines(h) == [(0, 0, 4, 0), (4, 0, 10, 0)] and h.finished
assert all(e.dxf.layer == "CALLES" and e.dxf.color == 3 for e in h.msp.query("LINE"))
assert any("quedan 4 y 6" in m for m in h.msgs)
h.history.undo(); assert lines(h) == [(0, 0, 10, 0)]           # se deshace de una
h, t = partir(linea, (5, 0), (10, 0))                         # en el extremo: nada
assert lines(h) == [(0, 0, 10, 0)] and any("extremo" in m for m in h.msgs) and not h.finished
print("ok línea")

# ---- 2. polilínea abierta: en un tramo, en un vértice (sin repetirlo), anchos -------------
L = lambda m: m.add_lwpolyline([(0, 0, 1, 3), (10, 0, 0, 0), (10, 10, 0, 0)], format="xyse")
h, t = partir(L, (5, 0), (5, 0))
assert plines(h) == [([(0, 0, 1, 2, 0), (5, 0, 0, 0, 0)], False),
                     ([(5, 0, 2, 3, 0), (10, 0, 0, 0, 0), (10, 10, 0, 0, 0)], False)]   # ancho interpolado
h, t = partir(L, (5, 0), (10, 0))                             # en el vértice
assert plines(h) == [([(0, 0, 1, 3, 0), (10, 0, 0, 0, 0)], False),
                     ([(10, 0, 0, 0, 0), (10, 10, 0, 0, 0)], False)]
h0 = Harness(); p0 = L(h0.msp)
assert len(modify.break_pieces(p0, (10, 0), (10, 0))[1][1]) == 3                 # nativo: vértice repetido
print("ok polilínea abierta")

# ---- 3. polilínea cerrada: se ABRE en el punto (el nativo perdía el tramo de cierre) -------
C = lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
h, t = partir(C, (5, 0), (5, 0))
((filas, cerrada),) = plines(h)
assert not cerrada and [r[:2] for r in filas] == [(5, 0), (10, 0), (10, 10), (0, 10), (0, 0), (5, 0)]
assert abs(par.largo_filas(filas) - 40) < 1e-9                 # el perímetro entero
h0 = Harness(); p0 = C(h0.msp)
nat = modify.break_pieces(p0, (5, 0), (5, 0))
assert sum(par.largo_filas(pz[1]) for pz in nat) < 40 - 1     # nativo: se pierde un lado
h, t = partir(C, (0, 5), (10, 10))                            # cerrada, en un vértice
((filas, cerrada),) = plines(h)
assert [r[:2] for r in filas] == [(10, 10), (0, 10), (0, 0), (10, 0), (10, 10)] and not cerrada
print("ok polilínea cerrada")

# ---- 4. tramo en arco: dos arcos exactos (el nativo lo volvía recto) ----------------------
A = lambda m: m.add_lwpolyline([(0, 0, 0, 0, 1), (10, 0, 0, 0, 0), (10, -10, 0, 0, 0)], format="xyseb")
h, t = partir(A, (5, -5), (5, -5))                            # media vuelta de radio 5: abajo en (5, -5)
(f1, _), (f2, _) = plines(h)
cab, cola = (f1, f2) if len(f1) == 2 else (f2, f1)
b45 = R(math.tan(math.pi / 8))
assert cab == [(0, 0, 0, 0, b45), (5, -5, 0, 0, 0)] and cola[0] == (5, -5, 0, 0, b45)
assert abs(par.largo_filas(cab) + par.largo_filas(cola) - (5 * math.pi + 10)) < 1e-4
print("ok tramo en arco")

# ---- 5. arco suelto; círculo como en AutoCAD; otros tipos ---------------------------------
h, t = partir(lambda m: m.add_arc((0, 0), 5, 0, 180), (0, 5), (0, 9))
angs = sorted((R(a.dxf.start_angle), R(a.dxf.end_angle)) for a in h.msp.query("ARC"))
assert angs == [(0, 90), (90, 180)]
h, t = partir(lambda m: m.add_circle((0, 0), 5), (5, 0), (5, 0))
assert len(h.msp.query("CIRCLE")) == 1 and any("círculo" in m for m in h.msgs)
h, t = partir(lambda m: m.add_text("hola", dxfattribs={"insert": (0, 0)}), (0, 0), (0, 0))
assert not h.finished
print("ok arcos y círculos")

# ---- 6. QGIS: los dos pedazos conservan el vínculo; un polígono SIG no se parte ------------
def con_tag(m):
    e = m.add_line((0, 0), (10, 0), dxfattribs={"layer": "rutas"}); enl.set_feat_tag(e, "rutas", 7, 0); return e
h, t = partir(con_tag, (5, 0), (3, 0))
tags = [enl.feat_tag(e) for e in h.msp.query("LINE")]
assert len(tags) == 2 and all(x is not None and x.fid == 7 for x in tags)
assert any("registro nuevo con los mismos atributos" in m for m in h.msgs)
def poli_tag(m):
    e = C(m); enl.set_feat_tag(e, "lotes", 3, 0)
h, t = partir(poli_tag, (5, 0), (5, 0))
assert len(h.msp.query("LWPOLYLINE")) == 1 and h.msp.query("LWPOLYLINE")[0].closed
assert any("polígono" in m for m in h.msgs)
print("ok vínculo con QGIS")

# ---- 7. Múltiple: cada punto parte el pedazo donde cae; Deshacer de a uno ------------------
h, t = partir(linea, (5, 0), None, multiple=[(2, 0), (8, 0), (5, 0)])
assert lines(h) == [(0, 0, 2, 0), (2, 0, 5, 0), (5, 0, 8, 0), (8, 0, 10, 0)] and not h.finished
t.on_option("D"); assert lines(h) == [(0, 0, 2, 0), (2, 0, 8, 0), (8, 0, 10, 0)]
t.on_point((6, 0)); assert (2, 0, 6, 0) in lines(h)
t.on_enter(); assert h.finished
h, t = partir(linea, (5, 0), None, multiple=[(5, 0)])
t.on_option("O"); assert t._ent is None and t.entity_picker       # otro objeto
print("ok múltiple")

# ---- 8. referencias: se suman sólo mientras se elige el punto ------------------------------
h = Harness(); linea(h.msp); t = T(h.ctx); t.start()
assert t.referencias_extra() == frozenset() and t.entity_picker
t.on_point((5, 0)); assert t.referencias_extra() == {"END", "MID", "INT", "QUA"} and not t.entity_picker
class Ctl:
    osnap_on = True; osnap_override = None; osnap_modes = {"CEN"}
    def snap_kinds(self): return self.osnap_override if self.osnap_override is not None else (
        frozenset(self.osnap_modes) if self.osnap_on else frozenset())
assert dib.envolver(Ctl, "snap_kinds", dib._envolver_snap_kinds)
c = Ctl(); c.tool = t
assert c.snap_kinds() == {"CEN", "END", "MID", "INT", "QUA"}
c.osnap_override = frozenset({"PER"}); assert c.snap_kinds() == {"PER"}       # FIN, INT... de una vez: manda
c.osnap_override = None; c.osnap_on = False; assert c.snap_kinds() == frozenset()   # F3 apagado: se respeta
c.osnap_on = True; c.tool = None; assert c.snap_kinds() == {"CEN"}           # sin herramienta: lo de siempre
print("ok referencias")

# ---- 9. vista previa: el objeto bajo el cursor, luego los dos pedazos, el corte y los largos
h = Harness(); linea(h.msp); C(h.msp); t = T(h.ctx); t.start()
assert t.resaltado((5, 0.3))["cursor"] == [((0, 0), (10, 0))]
assert t.resaltado((50, 50))["cursor"] == []
t.on_point((5, 0)); r = t.resaltado((4, 2))
assert r["elegido"] == [((0, 0), (10, 0))] and r["pieza_a"] == [((0, 0), (4, 0))] and r["pieza_b"] == [((4, 0), (10, 0))]
assert r["puntos"] == [(4, 0)] and r["textos"] == [((4, 0), "4  |  6")]
assert t.resaltado((10, 0))["puntos"] == []                    # en el extremo: no hay vista previa
class Pen:
    def __init__(self, color, ancho, estilo): self.color, self.ancho, self.estilo = color, ancho, estilo
class Painter:
    def __init__(self): self.pens = []; self.lineas = 0; self.textos = []; self.saves = 0
    def save(self): self.saves += 1
    def restore(self): self.saves -= 1
    def setPen(self, p): self.pens.append(p)
    def drawLine(self, a, b): self.lineas += 1
    def drawText(self, p, s): self.textos.append(s)
qt = (Pen, lambda *c: c, lambda x, y: (x, y), types.SimpleNamespace(DashLine="--", SolidLine="-"))
deleg = types.SimpleNamespace(tool=t, _cursor=(4, 2), resolved_point=lambda x, y: (4.0, 0.0))  # con la referencia
vp = types.SimpleNamespace(tool_delegate=deleg, _space_to_screen=lambda x, y: (x, -y))
pa = Painter(); n = dib.dibujar_resaltado(vp, pa, qt)
assert pa.textos == ["4  |  6"] and pa.saves == 0 and pa.lineas == 1 + 1 + 1 + 2   # elegido, a, b, la X
assert [p.color[:3] for p in pa.pens] == [(60, 170, 255), (60, 170, 255), (90, 220, 120), (255, 220, 0)]
print("ok vista previa")

# ---- 10. el módulo: apagado no hay comando, ni menú, ni botón ------------------------------
pkg = import_module("ingecad_plugin_geocad")
mods.poner("ingecad", "partir", False)
spec = pkg.construir_spec()
assert "BREAKATPOINT" not in spec.tools and "BREAKATPOINT" not in [i.command for i in spec.toolbar]
mods.poner("ingecad", "partir", True)
assert "BREAKATPOINT" in pkg.construir_spec().tools
print("ok módulo")
print("TODO OK PARTIR")
