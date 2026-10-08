"""Chaflán estilo AutoCAD para IngeCAD (módulo «Chaflán»): lo que el CHAMFER
nativo no hace (polilíneas, lado elegido, propiedades, distancias 0, Ángulo,
Polilínea entera, Múltiple, desHacer) sobre la misma geometría del Empalme."""
import os, sys, tempfile, types, math
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from core import trimmode
from tools.base import ToolContext
from tools.modify import ChamferTool

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
cha = import_module("ingecad_plugin_geocad.chaflan")
dib = import_module("ingecad_plugin_geocad.dibujo")
enl = import_module("ingecad_plugin_geocad.enlace")
mods = import_module("ingecad_plugin_geocad.modulos")
T = cha.ChaflanTool
assert lp.spec.tools.get("GEOCHAMFER") is T
_b = [i.command for i in lp.spec.toolbar]; _k = _b.index("FILLET")
assert _b[_k:_k + 3] == ["FILLET", "CHAMFER", "BREAKATPOINT"]


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


def distancias(d1, d2=None, metodo="D", largo=0.0, angulo=0.0):
    T.dist1, T.dist2 = d1, d1 if d2 is None else d2
    T.metodo, T.largo, T.angulo = metodo, largo, angulo
    ChamferTool.dist1, ChamferTool.dist2 = T.dist1, T.dist2


def chaflan(build, p1, p2, shift=False, cls=T):
    h = Harness(); build(h.msp)
    t = cls(h.ctx); t.start(); t.on_point(p1)
    if shift: t.shift = True
    t.on_point(p2)
    t.shift = False
    return h


R = lambda v: round(float(v), 6)
def lineas(h):
    return sorted(tuple(R(v) for v in (e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
                  for e in h.msp.query("LINE"))
def pl(h):
    (p,) = list(h.msp.query("LWPOLYLINE"))
    return [(R(r[0]), R(r[1]), R(r[4])) for r in p.get_points("xyseb")], p.closed

trimmode.set_trimmode(True)

# ---- 1. dos líneas: distancias en el orden en que se tocan, propiedades conservadas ------
L = lambda m: (m.add_line((0, 0), (10, 0), dxfattribs={"layer": "MUROS", "color": 2}),
               m.add_line((12, 2), (12, 10), dxfattribs={"layer": "MUROS", "color": 2}))
distancias(2, 3)
h = chaflan(L, (5, 0), (12, 6))
assert lineas(h) == [(0, 0, 10, 0), (10, 0, 12, 3), (12, 3, 12, 10)]
assert all(e.dxf.layer == "MUROS" and e.dxf.color == 2 for e in h.msp.query("LINE"))
hn = chaflan(L, (5, 0), (12, 6), cls=ChamferTool)
assert any(e.dxf.layer != "MUROS" for e in hn.msp.query("LINE"))          # nativo: pierden la capa
h.history.undo(); assert lineas(h) == [(0, 0, 10, 0), (12, 2, 12, 10)]
print("ok dos líneas")

# ---- 2. lado elegido en líneas que se cruzan (el nativo conservaba el extremo lejano) ------
cruz = lambda m: (m.add_line((0, 5), (10, 5)), m.add_line((5, 0), (5, 10)))
distancias(1)
h = chaflan(cruz, (9, 5), (5, 9))
assert lineas(h) == [(5, 6, 5, 10), (6, 5, 5, 6), (10, 5, 6, 5)]
hn = chaflan(cruz, (9, 5), (5, 9), cls=ChamferTool)
assert lineas(hn) != lineas(h)
print("ok lado elegido")

# ---- 3. distancias 0 = esquina (el nativo dejaba una línea de largo cero); Mayús ----------
distancias(0)
h = chaflan(L, (5, 0), (12, 6))
assert lineas(h) == [(0, 0, 12, 0), (12, 0, 12, 10)]
hn = chaflan(L, (5, 0), (12, 6), cls=ChamferTool)
assert any(R(e.dxf.start.x) == R(e.dxf.end.x) and R(e.dxf.start.y) == R(e.dxf.end.y)
           for e in hn.msp.query("LINE"))                                     # nativo: largo cero
distancias(2)
h = chaflan(L, (5, 0), (12, 6), shift=True)
assert lineas(h) == [(0, 0, 12, 0), (12, 0, 12, 10)]
print("ok esquina")

# ---- 4. polilíneas: un vértice, línea + polilínea, dos polilíneas (el nativo: nada) --------
distancias(2)
V = lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10)])
h = chaflan(V, (5, 0), (10, 5))
assert pl(h) == ([(0, 0, 0), (8, 0, 0), (10, 2, 0), (10, 10, 0)], False)
hn = chaflan(V, (5, 0), (10, 5), cls=ChamferTool)
assert pl(hn)[0] == [(0, 0, 0), (10, 0, 0), (10, 10, 0)] and any("lines" in m.lower() or "línea" in m.lower() for m in hn.msgs)
distancias(1, 3)                                     # primero el tramo vertical: d1 va ahí
h = chaflan(V, (10, 5), (5, 0))
assert pl(h)[0] == [(0, 0, 0), (7, 0, 0), (10, 1, 0), (10, 10, 0)]
distancias(2)
LP = lambda m: (m.add_line((0, 0), (10, 0)), m.add_lwpolyline([(20, 10), (12, 10), (12, 2)]))
h = chaflan(LP, (5, 0), (12, 5))
assert [r[:2] for r in pl(h)[0]] == [(0, 0), (10, 0), (12, 2), (12, 10), (20, 10)] and not list(h.msp.query("LINE"))
PP = lambda m: (m.add_lwpolyline([(-5, 5), (0, 0), (10, 0)]), m.add_lwpolyline([(12, 2), (12, 10), (20, 10)]))
h = chaflan(PP, (5, 0), (12, 5))
assert [r[:2] for r in pl(h)[0]] == [(-5, 5), (0, 0), (10, 0), (12, 2), (12, 10), (20, 10)]
print("ok polilíneas")

# ---- 5. método Ángulo: longitud sobre la primera y ángulo ----------------------------------
distancias(0, metodo="A", largo=2, angulo=45)
h = chaflan(lambda m: (m.add_line((0, 0), (10, 0)), m.add_line((10, 1), (10, 10))), (5, 0), (10, 6))
(bisel,) = [l for l in lineas(h) if l not in ((0, 0, 8, 0), (10, 2, 10, 10))]
assert bisel == (8, 0, 10, 2)                        # 45° en esquina recta: d2 = d1
distancias(0, metodo="A", largo=2, angulo=30)
h = chaflan(lambda m: (m.add_line((0, 0), (10, 0)), m.add_line((10, 1), (10, 10))), (5, 0), (10, 6))
assert (10, R(2 * math.tan(math.radians(30))), 10, 10) in lineas(h)
distancias(0, metodo="A", largo=2, angulo=100)     # 100° + 90° > 180: no llega
h = chaflan(L, (5, 0), (12, 6)); assert any("no entra" in m for m in h.msgs)
print("ok ángulo")

# ---- 6. opciones por la línea de comandos (como en AutoCAD) --------------------------------
distancias(0)
h = Harness(); L(h.msp); t = T(h.ctx); t.start()
for x in ("D", "2", ""):                             # Enter en la segunda: igual a la primera
    t.on_option(x)
assert (T.dist1, T.dist2, T.metodo) == (2, 2, "D")
t.on_option("A"); t.on_option("3"); t.on_option("60"); assert (T.largo, T.angulo, T.metodo) == (3, 60, "A")
t.on_option("O"); t.on_option("D"); assert T.metodo == "D"
t.on_option("R"); t.on_option("N"); assert not trimmode.trimmode()
t.on_option("R"); t.on_option("R"); assert trimmode.trimmode()
t.on_option("M"); t.on_point((5, 0)); t.on_point((12, 6)); assert not h.finished and len(lineas(h)) == 3
t.on_option("H"); assert lineas(h) == [(0, 0, 10, 0), (12, 2, 12, 10)]
t.on_enter(); assert h.finished
print("ok opciones")

# ---- 7. Recortar apagado: quedan los originales y se agrega el bisel ------------------------
distancias(2); trimmode.set_trimmode(False)
h = chaflan(L, (5, 0), (12, 6))
assert lineas(h) == [(0, 0, 10, 0), (10, 0, 12, 2), (12, 2, 12, 10)]
trimmode.set_trimmode(True)
print("ok sin recortar")

# ---- 8. Polilínea entera: todos los vértices que entran, avisa los cortos -------------------
distancias(1)
h = Harness(); h.msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
t = T(h.ctx); t.start(); t.on_option("P"); t.on_point((5, 0))
filas, cerrada = pl(h)
assert cerrada and len(filas) == 8 and any("4 líneas achaflanadas" in m for m in h.msgs)
distancias(3)
h = Harness(); h.msp.add_lwpolyline([(0, 0), (10, 0), (10, 4), (20, 4)])
t = T(h.ctx); t.start(); t.on_option("P"); t.on_point((5, 0))
assert any("1 línea achaflanada" in m and "1 era demasiado corta" in m for m in h.msgs)
print("ok polilínea entera")

# ---- 9. arcos y círculos: se explica; vínculo con QGIS conservado ---------------------------
distancias(2)
h = chaflan(lambda m: (m.add_circle((0, 0), 5), m.add_line((10, 0), (20, 0))), (5, 0), (15, 0))
assert any("no con arcos" in m for m in h.msgs) and not list(h.msp.query("LWPOLYLINE"))
def sig(m):
    a, b = L(m); enl.set_feat_tag(a, "muros", 4, 0); enl.set_feat_tag(b, "muros", 5, 0)
h = chaflan(sig, (5, 0), (12, 6))
tags = sorted(enl.feat_tag(e).fid for e in h.msp.query("LINE") if enl.feat_tag(e))
assert tags[0] == 4 and 5 in tags                   # los recortados conservan su registro
print("ok tipos y QGIS")

# ---- 10. vista previa: el bisel antes del clic --------------------------------------------
distancias(2, 3)
h = Harness(); L(h.msp); t = T(h.ctx); t.start(); t.on_point((5, 0))
r = t.resaltado((12, 6))
assert r["elegido"] == [((0, 0), (10, 0))] and r["vista"] == [((10.0, 0.0), (12.0, 3.0))]
print("ok vista previa")

# ---- 11. el módulo: CHAMFER / CHAFLAN abren éste sólo si está activo -----------------------
reg = {"CHAMFER": ChamferTool, "GEOCHAMFER": T}
assert dib.herramienta_para("CHAMFER", None, reg) == "GEOCHAMFER"
mods.poner("ingecad", "chaflan", False)
assert dib.herramienta_para("CHAMFER", None, reg) == "CHAMFER"
pkg = import_module("ingecad_plugin_geocad")
assert "GEOCHAMFER" not in pkg.construir_spec().tools
mods.poner("ingecad", "chaflan", True)
print("ok módulo")
print("TODO OK CHAFLAN")
