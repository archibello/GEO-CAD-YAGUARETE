"""GeoPackage de punta a punta con archivos reales creados por GDAL."""
import os, sys, tempfile, shutil, sqlite3, zipfile, types, hashlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.actions import EraseCommand
from tools.base import ToolContext

GD = os.environ["GDAL_GPKG"]
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False); assert lp.available, lp.reason
spec = lp.spec
enlace = import_module("ingecad_plugin_geocad.enlace")
G = import_module("ingecad_plugin_geocad.gpkgio")

class Session:
    def __init__(self):
        self.doc = Document.new(); self.hist = History(self.doc); self.log = []; self.answers = []
    def run(self, name, selection=None):
        self.log.clear(); answers = list(self.answers)
        def ask_text(p, d=""): return answers.pop(0) if answers else d
        def ask_choice(p, items, d=""):
            a = answers.pop(0) if answers else None
            return None if a is None else next((i for i in items if i.startswith(a)), None)
        ctx = ToolContext(execute=self.hist.execute, prompt=lambda s: None, echo=self.log.append,
                          finish=lambda: None, ask_text=ask_text, ask_choice=ask_choice,
                          services=types.SimpleNamespace(document=self.doc))
        t = spec.tools[name](ctx); t.start()
        if selection is not None: t.on_selection(selection)
        self.answers = []; return "\n".join(self.log)
    def ents(self, fid=None):
        return [(t, e) for e in self.doc.doc.modelspace() if (t := enlace.feat_tag(e)) and (fid is None or t.fid == fid)]

def rows(path, table="poly"):
    c = sqlite3.connect(path); r = {x[0]: x[1:] for x in c.execute(f"select * from {table}")}; c.close(); return r
def fhash(p): return hashlib.sha1(Path(p).read_bytes()).hexdigest()

tmp = tempfile.mkdtemp()
gp = os.path.join(tmp, "catastro.gpkg"); shutil.copy(os.path.join(GD, "poly_golden.gpkg"), gp)
orig_rows = rows(gp)
print("filas", len(orig_rows), list(orig_rows)[:3])

s = Session(); s.answers = [gp]; out = s.run("SHPCONNECT"); print(out)
assert "GPKG-poly" in out and len({t.fid for t, _ in s.ents()}) == 10
assert Path(gp + ".poly.ingecad.lock").exists()
out = s.run("SHPSTATUS"); assert "0 modificado(s)" in out, out

fids = sorted({t.fid for t, _ in s.ents()})
f1, f3, f4 = fids[0], fids[2], fids[3]
(_, e1), *_ = [x for x in s.ents(f1) if x[0].part == 0]
p = list(e1.get_points("xy")); p[1] = (p[1][0] + 5.0, p[1][1] + 5.0); e1.set_points(p, format="xy")
s.answers = ["PRFEDEA", "X" * 17]; out = s.run("SHPATTR", selection=[s.ents(fids[1])[0][1]]); assert "no válido" in out, out
s.answers = ["PRFEDEA", "NUEVO-123"]; print(s.run("SHPATTR", selection=[s.ents(fids[1])[0][1]]))
s.answers = ["AREA", "1234,5"]; s.run("SHPATTR", selection=[s.ents(fids[1])[0][1]])
s.hist.execute(EraseCommand([e for _t, e in s.ents(f3)]))
src = s.ents(f4)[0][1]; c = src.copy(); s.doc.doc.modelspace().add_entity(c); c.translate(0, 2000, 0)
x0, y0 = 480000, 4760000
s.doc.doc.modelspace().add_lwpolyline([(x0, y0), (x0 + 50, y0), (x0 + 50, y0 + 50)], close=True, dxfattribs={"layer": "GPKG-poly"})
out = s.run("SHPSTATUS"); print(out)
assert "2 modificado(s)" in out and "2 nuevo(s)" in out and "1 borrado(s)" in out, out
s.answers = ["Sí"]; out = s.run("SHPCHECKIN"); print(out); assert "Guardado" in out, out

new_rows = rows(gp)
assert f3 not in new_rows and len(new_rows) == 11
for fid, r in orig_rows.items():
    if fid in (f1, fids[1], f3): continue
    assert new_rows[fid] == r, fid
assert new_rows[fids[1]][0] == orig_rows[fids[1]][0]            # geometría intacta
cols = [x[1] for x in sqlite3.connect(gp).execute("pragma table_info(poly)")]
print(cols, new_rows[fids[1]])
assert new_rows[fids[1]][cols.index("PRFEDEA") - 1] == "NUEVO-123"
assert new_rows[fids[1]][cols.index("AREA") - 1] == 1234.5
conn = sqlite3.connect(gp)
print("integridad", conn.execute("pragma integrity_check").fetchone(), "conteo ogr", conn.execute("select feature_count from gpkg_ogr_contents").fetchone())
assert conn.execute("select feature_count from gpkg_ogr_contents").fetchone()[0] == 11
# rtree coherente con las geometrías (para TODAS las filas)
for fid, blob in conn.execute("select fid, geom from poly"):
    b = G.blob_bounds(blob); r = conn.execute("select minx,maxx,miny,maxy from rtree_poly_geom where id=?", (fid,)).fetchone()
    assert r and r[0] <= b[0] + 0.01 and r[1] >= b[1] - 0.01 and r[2] <= b[2] + 0.01 and r[3] >= b[3] - 0.01, (fid, r, b)
assert conn.execute("select count(*) from rtree_poly_geom").fetchone()[0] == 11
print("last_change", conn.execute("select last_change from gpkg_contents").fetchone())
conn.close()
# geometría nueva de f1 contiene el vértice movido
g = G.parse_blob(new_rows[f1][0]); assert (p[1][0], p[1][1]) in g.parts[0], g.parts[0][:3]
# respaldo
z = list((Path(tmp) / "_respaldos_ingecad").glob("catastro_poly_*.zip")); assert len(z) == 1
bk = os.path.join(tmp, "bk.gpkg"); Path(bk).write_bytes(zipfile.ZipFile(z[0]).read("catastro.gpkg"))
assert rows(bk) == orig_rows
out = s.run("SHPSTATUS"); assert "0 modificado(s)" in out and "0 nuevo(s)" in out, out

# conflicto: "QGIS" cambia un atributo de f1; el dibujo mueve f1
qg = G.connect(gp, readonly=False); qg.execute("UPDATE poly SET PRFEDEA='QGIS' WHERE fid=?", (f1,)); qg.close()
(_, e1), *_ = [x for x in s.ents(f1) if x[0].part == 0]
p = list(e1.get_points("xy")); p[2] = (p[2][0] + 1, p[2][1]); e1.set_points(p, format="xy")
h = fhash(gp); s.answers = ["Sí"]; out = s.run("SHPCHECKIN"); print(out)
assert "conflicto" in out and fhash(gp) == h

# base ocupada por otro programa: no escribe nada
p[2] = (p[2][0] - 1, p[2][1]); e1.set_points(p, format="xy")
f5 = fids[5]; (_, e5), *_ = s.ents(f5); q = list(e5.get_points("xy")); q[0] = (q[0][0] + 0.25, q[0][1]); e5.set_points(q, format="xy")
other = sqlite3.connect(gp, isolation_level=None); other.execute("BEGIN IMMEDIATE")
h = fhash(gp); s.answers = ["Sí"]; out = s.run("SHPCHECKIN"); print(out)
assert "ocupado" in out and fhash(gp) == h
other.execute("ROLLBACK"); other.close()
s.answers = ["Sí"]; out = s.run("SHPCHECKIN"); print(out); assert "Guardado" in out
assert rows(gp)[f1][cols.index("PRFEDEA") - 1] == "QGIS"          # el cambio de QGIS se respetó

# LINESTRING Z con envolvente 3D
g3 = os.path.join(tmp, "red.gpkg"); shutil.copy(os.path.join(GD, "3d_envelope.gpkg"), g3)
s3 = Session(); s3.answers = [g3]; print(s3.run("SHPCONNECT"))
before = rows(g3, "foo"); fid = sorted(before)[0]; og = G.parse_blob(before[fid][0]); print("orig", og.parts, og.z, og.env_code)
(_, l), = s3.ents(fid); pts = list(l.get_points("xy"))
mid = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2); pts.insert(1, mid); l.set_points(pts, format="xy")
s3.answers = ["Sí"]; print(s3.run("SHPCHECKIN"))
ng = G.parse_blob(rows(g3, "foo")[fid][0]); print("nuevo", ng.parts, ng.z, ng.env_code)
assert ng.env_code == og.env_code and ng.has_z and abs(ng.z[0][1] - (og.z[0][0] + og.z[0][1]) / 2) < 1e-9
# desconectar
s.answers = ["GPKG"]; print(s.run("SHPRELEASE")); assert not Path(gp + ".poly.ingecad.lock").exists()
print("TODO OK GPKG")
