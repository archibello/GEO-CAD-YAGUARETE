"""Envío selectivo: conectar sólo lo pedido, ampliar, y devolver sólo lo seleccionado."""
from pathlib import Path
import os, sys, tempfile, types, shutil
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from importlib import import_module
from fixtures import make_parcelas
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
spec = lp.spec; assert "QGISSAVESEL" in spec.tools
M = lambda n: import_module("ingecad_plugin_geocad." + n)
enlace, shpio, puente, buzon, D, G = M("enlace"), M("shpio"), M("puente"), M("buzon"), M("datos"), M("gpkgio")
tools_mod = M("tools")

class S:
    def __init__(self):
        self.doc = Document.new(); self.hist = History(self.doc); self.log = []
        self.services = types.SimpleNamespace(document=self.doc)
    def run(self, name, answers=(), sel=None, request=None):
        a = list(answers); self.log.clear()
        ctx = ToolContext(execute=self.hist.execute, prompt=lambda s: None, echo=self.log.append, finish=lambda: None,
            ask_text=lambda p, d="": a.pop(0) if a else d,
            ask_choice=lambda p, items, d="": (lambda x: None if x is None else next((i for i in items if i.startswith(x)), None))(a.pop(0) if a else None),
            services=self.services)
        if request: puente._state["pending"].append(request)
        t = spec.tools[name](ctx); t.start()
        if sel is not None: t.on_selection(sel)
        return "\n".join(self.log)
    def ents(self, fid=None):
        return [e for e in self.doc.doc.modelspace() if (t := enlace.feat_tag(e)) and (fid is None or t.fid == fid)]

tmp = tempfile.mkdtemp(); shp = make_parcelas(tmp); orig = shpio.Shapefile(shp)
s = S()
out = s.run("SHPCONNECT", request=buzon.layer_ref("shp", shp) | {"fids": [1, 3]}); print(out)
link = enlace.read_links(s.doc.doc)["SHP-parcelas"]
assert set(link.hashes) == {1, 3} and link.count == 5 and "2 de 5" in out and "parcial" in out
assert {enlace.feat_tag(e).fid for e in s.ents()} == {1, 3}
assert "0 borrado(s)" in s.run("SHPSTATUS")                       # lo no conectado no cuenta como borrado
# la tabla muestra sólo lo conectado; lo otro es sólo lectura
T = D.TableState(s.doc, "SHP-parcelas"); assert [r.fid for r in T.rows] == [1, 3]
T.only_connected = False; T.apply(); assert len(T.rows) == 5
r0 = [r for r in T.rows if r.fid == 0][0]; assert not T.cell_editable(r0, 2) and T.cell_editable([r for r in T.rows if r.fid == 1][0], 2)
# ampliar: pedir 3 y 4 suma sólo el 4 (un paso de deshacer)
out = s.run("SHPCONNECT", request=buzon.layer_ref("shp", shp) | {"fids": [3, 4]}); print(out)
assert "sumaron 1" in out and set(enlace.read_links(s.doc.doc)["SHP-parcelas"].hashes) == {1, 3, 4}
s.hist.undo(); assert set(enlace.read_links(s.doc.doc)["SHP-parcelas"].hashes) == {1, 3} and not s.ents(4)
s.hist.redo(); assert s.ents(4)
out = s.run("SHPCONNECT", request=buzon.layer_ref("shp", shp) | {"fids": [1]}); assert "ya tenía conectado" in out
# por pantalla (bbox): toca la parcela 2 (y su hueco)
x0, y0 = 5_430_000.0, 6_300_000.0
out = s.run("SHPCONNECT", request=buzon.layer_ref("shp", shp) | {"bbox": [x0 + 62, y0 + 2, x0 + 64, y0 + 3]}); print(out)
assert set(enlace.read_links(s.doc.doc)["SHP-parcelas"].hashes) == {1, 2, 3, 4} and len(s.ents(2)) == 2
# seguridad: atributo pendiente sobre un registro NO conectado -> error, no se escribe
s.hist.execute(enlace.AttrEditCommand("SHP-parcelas", 0, "TITULAR", "Intruso"))
out = s.run("SHPSTATUS"); assert "no está conectado" in out, out
s.hist.undo()
# editar 1, 3 y 4; devolver SÓLO la selección (objeto 3)
def mover(fid, dx):
    e = [e for e in s.ents(fid) if enlace.feat_tag(e).part == 0][0]
    p = list(e.get_points("xy")); p[0] = (p[0][0] + dx, p[0][1]); e.set_points(p, format="xy")
mover(1, 0.5); mover(3, 0.25); mover(4, 0.75)
buzon.receive("qgis")
out = s.run("QGISSAVESEL", ["Sí"], sel=s.ents(3)); print(out)
assert "1 modificado(s)" in out and "sólo lo seleccionado" in out
now = shpio.Shapefile(shp)
assert now.contents[3] != orig.contents[3]
for f in (0, 1, 2, 4): assert now.contents[f] == orig.contents[f], f   # 1 y 4 siguen pendientes
msg = buzon.receive("qgis")[-1]; assert msg["tipo"] == "guardado" and msg["capas"][0]["fids"] == [3], msg
out = s.run("SHPSTATUS"); assert "2 modificado(s)" in out, out
# polígono con hueco: elegir sólo el contorno guarda el registro completo
hole = [e for e in s.ents(2) if enlace.feat_tag(e).part == 1][0]
hp = list(hole.get_points("xy")); hp[0] = (hp[0][0] + 1, hp[0][1]); hole.set_points(hp, format="xy")
outer2 = [e for e in s.ents(2) if enlace.feat_tag(e).part == 0][0]
out = s.run("QGISSAVESEL", ["Sí"], sel=[outer2]); assert "guardado" in out, out
g2 = shpio.Shapefile(shp).geometry(2); assert len(g2.parts) == 2 and (hp[0][0], hp[0][1]) in g2.parts[1]
# devolver todo lo que queda
out = s.run("QGISSAVE", ["Sí"]); assert "2 modificado(s)" in out and "Listo" in out, out
# selección sin objetos SIG
free = s.doc.doc.modelspace().add_line((0, 0), (1, 1))
out = s.run("QGISSAVESEL", sel=[free]); assert "Nada de lo seleccionado" in out

# GeoPackage: por pantalla usando el índice espacial
gp = os.path.join(tempfile.mkdtemp(), "c.gpkg"); shutil.copy(os.environ["GDAL_GPKG"] + "/poly_golden.gpkg", gp)
c = G.connect(gp); L = G.open_layer(c, gp, "poly"); rows = G.read_rows(c, L); c.close()
b5 = G.blob_bounds(rows[5][0]); bbox = [b5[0] + 1, b5[2] + 1, b5[0] + 2, b5[2] + 2]
s2 = S(); out = s2.run("SHPCONNECT", request=buzon.layer_ref("gpkg", gp, "POLY") | {"bbox": bbox}); print(out)
got = set(enlace.read_links(s2.doc.doc)["GPKG-poly"].hashes); print("bbox ->", got); assert 5 in got and len(got) < 10
out = s2.run("SHPCONNECT", request=buzon.layer_ref("gpkg", gp, "poly") | {"fids": [1, 2]})
assert {1, 2} <= set(enlace.read_links(s2.doc.doc)["GPKG-poly"].hashes)
e1 = s2.ents(1)[0]; p = list(e1.get_points("xy")); p[0] = (p[0][0] + 1, p[0][1]); e1.set_points(p, format="xy")
e2 = s2.ents(2)[0]; p = list(e2.get_points("xy")); p[0] = (p[0][0] + 1, p[0][1]); e2.set_points(p, format="xy")
before = rows
out = s2.run("QGISSAVESEL", ["Sí"], sel=[e2]); print(out)
c = G.connect(gp); after = G.read_rows(c, L); c.close()
assert after[2] != before[2] and after[1] == before[1] and all(after[f] == before[f] for f in before if f != 2)
# la ventana: lo que se ve en pantalla
view = types.SimpleNamespace(width=200, height=100, screen_to_world=lambda sx, sy: (sx * 2.0, (100 - sy) * 2.0))
assert tools_mod._screen_bbox(types.SimpleNamespace(viewport=types.SimpleNamespace(view=view))) == (0.0, 0.0, 400.0, 200.0)
print("TODO OK PARCIAL")
