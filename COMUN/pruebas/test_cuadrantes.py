"""Empalme y chaflán en un cruce: el lado que queda es el que se toca, en los
4 cuadrantes, con líneas y polilíneas dibujadas en cualquier sentido (error
encontrado por Fernando: con polilíneas sólo andaba un cuadrante)."""
import os, tempfile, sys; os.environ["HOME"]=tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from core import trimmode
from tools.base import ToolContext
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
cha = import_module("ingecad_plugin_geocad.chaflan"); emp = import_module("ingecad_plugin_geocad.empalme")
trimmode.set_trimmode(True)
class S:
    def __init__(s,d): s.index=GeometryIndex(d)
    def pick_entity(s,p):
        s.index.invalidate(); h=s.index.pick(p,2.0); return s.index.entity(h) if h else None
def segs(m):
    out=[]
    for e in m:
        if e.dxftype()=="LINE": out.append([(e.dxf.start.x,e.dxf.start.y),(e.dxf.end.x,e.dxf.end.y)])
        elif e.dxftype()=="LWPOLYLINE": out.append([(p[0],p[1]) for p in e.get_points("xy")])
        else: out.append([])
    return out
def run(cls, kind_h, kind_v, h, v, a, b):
    doc=Document(ezdxf.new()); hist=History(doc); msgs=[]
    ctx=ToolContext(execute=hist.execute,prompt=msgs.append,echo=msgs.append,finish=lambda:None,services=S(doc),undo_last=hist.undo)
    m=doc.modelspace()
    for k,pts in ((kind_h,h),(kind_v,v)):
        m.add_line(*pts) if k=="L" else m.add_lwpolyline(list(pts))
    cls.dist1=cls.dist2=1; cls.metodo="D"; cls.radius=1
    t=cls(ctx); t.start(); t.on_point(a); t.on_point(b)
    return segs(m), [x for x in msgs if "GeoCAD" in x or "fit" in x or "entra" in x]
def ok_result(S_, qh, qv):
    pts=[p for s in S_ for p in s]
    # nothing may remain on the non-picked side of the cross (beyond 1e-6)
    for (x,y) in pts:
        if abs(y-5)<1e-6 and ((qh[0]>5 and x<5-1e-6) or (qh[0]<5 and x>5+1e-6)): return False
        if abs(x-5)<1e-6 and ((qv[1]>5 and y<5-1e-6) or (qv[1]<5 and y>5+1e-6)): return False
    return any(abs(y-5)<1e-6 for x,y in pts) and any(abs(x-5)<1e-6 for x,y in pts)
H=[((0,5),(10,5)),((10,5),(0,5))]; V=[((5,0),(5,10)),((5,10),(5,0))]
quads={"der-arr":((9,5),(5,9)),"izq-arr":((1,5),(5,9)),"izq-ab":((1,5),(5,1)),"der-ab":((9,5),(5,1))}
total = 0
for cls in (cha.ChaflanTool, emp.EmpalmeTool):
  for kinds in (("L","L"),("P","P"),("L","P"),("P","L")):
    for hd in H:
      for vd in V:
        for qn,(qh,qv) in quads.items():
          for fh in (True,False):
            a,b=(qh,qv) if fh else (qv,qh)
            S_,ms=run(cls,kinds[0],kinds[1],hd,vd,a,b)
            assert ok_result(S_,qh,qv), (cls.__name__, kinds, hd, vd, qn, fh, S_, ms)
            total += 1
print("ok", total, "cruces: cada cuadrante, cada sentido, líneas y polilíneas")

# polilínea de varios tramos tocada del lado de afuera: se explica (no corta el resto)
doc=Document(ezdxf.new()); hist=History(doc); msgs=[]
ctx=ToolContext(execute=hist.execute,prompt=msgs.append,echo=msgs.append,finish=lambda:None,services=S(doc),undo_last=hist.undo)
m=doc.modelspace(); m.add_lwpolyline([(0,5),(10,5),(10,20)]); m.add_line((5,0),(5,10))
t=cha.ChaflanTool(ctx); t.start(); t.on_point((1,5)); t.on_point((5,9))
assert any("resto de la polilínea" in x for x in msgs) and len(m.query("LWPOLYLINE")[0]) == 3
print("TODO OK CUADRANTES")
