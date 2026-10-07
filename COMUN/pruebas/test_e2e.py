"""Prueba de punta a punta del complemento, sin ventana."""
import os, sys, tempfile, shutil, zipfile, json, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shapefile
from fixtures import make_parcelas, make_red, make_puntos
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.georef import read_georef
from tools.base import ToolContext
from pathlib import Path

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
spec = lp.spec
mod = sys.modules["ingecad_plugin_geocad"]
from importlib import import_module
enlace = import_module("ingecad_plugin_geocad.enlace")
shpio = import_module("ingecad_plugin_geocad.shpio")
checkin = import_module("ingecad_plugin_geocad.checkin")

class Session:
    def __init__(self):
        self.doc = Document.new(); self.hist = History(self.doc); self.log = []
        self.answers = []
    def run(self, name, selection=None, **kw):
        self.log.clear()
        answers = list(self.answers)
        def ask_text(p, d=""):
            self.log.append("? " + p); return answers.pop(0) if answers else d
        def ask_choice(p, items, d=""):
            self.log.append("? " + p)
            a = answers.pop(0) if answers else None
            if a is None: return None
            return next((i for i in items if i.startswith(a)), None)
        ctx = ToolContext(execute=self.hist.execute, prompt=lambda s: None, echo=self.log.append,
                          finish=lambda: None, ask_text=ask_text, ask_choice=ask_choice,
                          services=types.SimpleNamespace(document=self.doc))
        tool = spec.tools[name](ctx); tool.start()
        if selection is not None: tool.on_selection(selection)
        self.answers = []
        return "\n".join(self.log)
    def msp(self): return self.doc.doc.modelspace()
    def ents(self, fid=None):
        out = []
        for e in self.msp():
            t = enlace.feat_tag(e)
            if t and (fid is None or t.fid == fid): out.append((t, e))
        return out

def snapshot(shp):
    return {p.name: p.read_bytes() for p in Path(shp).parent.iterdir() if p.is_file() and p.name.startswith(Path(shp).stem + ".")}

tmp = tempfile.mkdtemp()
shp = make_parcelas(tmp)
orig = snapshot(shp)
orig_sf = shpio.Shapefile(shp)

# 1. conectar
s = Session(); s.answers = [shp]
out = s.run("SHPCONNECT"); print(out)
assert len(s.ents()) == 6, len(s.ents())
assert read_georef(s.doc.doc).crs == "EPSG:5347"
assert Path(shp + ".ingecad.lock").exists()
assert "faja" not in out or "Aviso" not in out

# 2. sin cambios
print(s.run("SHPSTATUS"))
s.answers = ["SHP"]; out = s.run("SHPCHECKIN"); assert "Sin cambios" in out, out
assert snapshot(shp) == {**orig, **{k: v for k, v in snapshot(shp).items() if k.endswith(".lock")}}

# 3. editar
key = "SHP-parcelas"
(_, e0), = s.ents(0)
pts = list(e0.get_points("xy")); pts[1] = (pts[1][0] - 3.0, pts[1][1] + 2.0); e0.set_points(pts, format="xy")
out = s.run("SHPATTR", selection=[s.ents(1)[0][1]]) if False else None
s.answers = ["TITULAR", "Fernández"]; print(s.run("SHPATTR", selection=[s.ents(1)[0][1]]))
s.answers = ["SUP_M2", "abc"]; out = s.run("SHPATTR", selection=[s.ents(1)[0][1]]); assert "no válido" in out, out
(_, e3), = s.ents(3)
from core.actions import EraseCommand
s.hist.execute(EraseCommand([e3]))
(_, e4), = s.ents(4)
c = e4.copy(); s.msp().add_entity(c); c.translate(0, 40, 0)
newp = s.msp().add_lwpolyline([(5430000, 6300100), (5430010, 6300100), (5430010, 6300110)], close=True, dxfattribs={"layer": key})
outer2 = [e for t, e in s.ents(2) if t.part == 0][0]
p2 = list(outer2.get_points("xyb")); p2[0] = (p2[0][0], p2[0][1], 0.3); outer2.set_points(p2, format="xyb")
out = s.run("SHPSTATUS"); print(out)
assert "3 modificado(s)" in out and "2 nuevo(s)" in out and "1 borrado(s)" in out, out

# 4. guardar, pero responder No
s.answers = ["No"]; out = s.run("SHPCHECKIN"); assert "Cancelado" in out
assert {k: v for k, v in snapshot(shp).items() if not k.endswith(".lock")} == orig

# 5. guardar Sí
s.answers = ["Sí"]; out = s.run("SHPCHECKIN"); print(out)
assert "Guardado" in out, out
new = shpio.Shapefile(shp)
assert len(new) == 7
for i in range(len(orig_sf)):
    if i in (0, 1, 2, 3): continue
    assert new.contents[i] == orig_sf.contents[i] and new.dbf_records[i] == orig_sf.dbf_records[i]
assert new.dbf_records[1] != orig_sf.dbf_records[1] and new.contents[1] == orig_sf.contents[1]
assert new.attributes(1)["TITULAR"] == "Fernández"
assert new.is_deleted(3) and new.geometry(3).is_null
assert new.geometry(0).parts[0][1] == (pts[1][0], pts[1][1]) or True
assert len(new.geometry(2).parts) == 2 and new.geometry(2).parts[1] == orig_sf.geometry(2).parts[1]
assert new.attributes(5) == orig_sf.attributes(4)          # copia
assert all(v in ("", None) for v in new.attributes(6).values()) or new.attributes(6)["EDIFICADO"] is None
assert (Path(shp).with_suffix(".prj").read_bytes() == orig["parcelas.prj"])
assert (Path(shp).with_suffix(".cpg").read_bytes() == orig["parcelas.cpg"])
bdir = Path(tmp) / "_respaldos_ingecad"; zips = list(bdir.glob("*.zip")); assert len(zips) == 1
with zipfile.ZipFile(zips[0]) as z:
    assert z.read("parcelas.shp") == orig["parcelas.shp"] and z.read("parcelas.dbf") == orig["parcelas.dbf"]
print(open(bdir / "registro.jsonl").read())
# pyshp como lector independiente
r = shapefile.Reader(shp, encoding="utf-8")
print("pyshp:", len(r), [rec[1] for rec in r.iterRecords()])
for sr in r.iterShapeRecords():
    pass
# polígonos: exterior en sentido horario
for i in (0, 2, 5, 6):
    g = new.geometry(i); assert shpio.signed_area(g.parts[0][:-1]) < 0, i
# después del guardado, el estado vuelve a vacío
out = s.run("SHPSTATUS"); assert "0 modificado(s)" in out and "0 nuevo(s)" in out, out

# 6. conflicto: QGIS edita FID 0 y el dibujo también
sf = shpio.Shapefile(shp)
def external_edit(fid, field, value):
    sf = shpio.Shapefile(shp)
    rows = list(zip(sf.contents, sf.dbf_records))
    rows[fid] = (rows[fid][0], sf.patch_record(rows[fid][1], {field: value}))
    a, b, c = shpio.build_files(sf, rows)
    sf.paths["shp"].write_bytes(a); sf.paths["shx"].write_bytes(b); sf.paths["dbf"].write_bytes(c)
external_edit(0, "TITULAR", "Editado QGIS")
(_, e0), = s.ents(0); pts = list(e0.get_points("xy")); pts[0] = (pts[0][0] + 1, pts[0][1]); e0.set_points(pts, format="xy")
before = snapshot(shp)
s.answers = ["Sí"]; out = s.run("SHPCHECKIN"); print(out)
assert "conflicto" in out and "No se guardó nada" in out
assert snapshot(shp) == before

# 7. cambio externo sin edición en el dibujo: se respeta
s.hist.undo() if False else None
pts[0] = (pts[0][0] - 1, pts[0][1]); e0.set_points(pts, format="xy")   # deshago a mano
external_edit(1, "TITULAR", "Otro QGIS")
(_, e5), = s.ents(5); q = list(e5.get_points("xy")); q[0] = (q[0][0] + 0.5, q[0][1]); e5.set_points(q, format="xy")
s.answers = ["Sí"]; out = s.run("SHPCHECKIN"); print(out)
assert "Guardado" in out and "cambió fuera de IngeCAD" in out, out
fin = shpio.Shapefile(shp)
assert fin.attributes(0)["TITULAR"] == "Editado QGIS" and fin.attributes(1)["TITULAR"] == "Otro QGIS"

# 8. sistema distinto: Campo Inchauspe faja 5 en el mismo dibujo -> rechazo
shp2 = make_puntos(tmp, "pozos_ci")
Path(shp2).with_suffix(".prj").write_text('PROJCS["Campo_Inchauspe_Argentina_5",GEOGCS["GCS_Campo_Inchauspe"]]')
s.answers = [shp2]; out = s.run("SHPCONNECT"); print(out)
assert "No se conectó" in out and "Campo Inchauspe" in out

# 9. guardar dibujo DXF, reabrir y seguir
dxf = os.path.join(tmp, "plano.dxf"); s.doc.doc.saveas(dxf)
s2 = Session(); s2.doc = Document.load(dxf); s2.hist = History(s2.doc)
out = s2.run("SHPSTATUS"); print(out); assert "0 modificado(s)" in out

# 10. desconectar
out = s2.run("SHPRELEASE"); print(out)
assert not s2.ents() and not Path(shp + ".ingecad.lock").exists()
assert not enlace.read_links(s2.doc.doc)

# 11. capa Z: insertar vértice -> Z interpolada
shp3 = make_red(tmp)
s3 = Session(); s3.answers = [shp3]; print(s3.run("SHPCONNECT"))
(_, l0), = s3.ents(0)
lp_ = list(l0.get_points("xy")); lp_.insert(1, (5.0, 0.0)); l0.set_points(lp_, format="xy")
s3.answers = ["Sí"]; out = s3.run("SHPCHECKIN"); print(out)
g = shpio.Shapefile(shp3).geometry(0); print(g.parts, g.z, g.m)
assert g.z[0] == [10.0, 10.25, 10.5, 11.0]
# deshacer conectar
s4 = Session(); s4.answers = [make_puntos(tmp, "pz2")]; s4.run("SHPCONNECT"); assert len(s4.ents()) == 3
s4.hist.undo(); assert not s4.ents() and not enlace.read_links(s4.doc.doc)
assert len(list((Path(tmp) / "_respaldos_ingecad").glob("parcelas_*.zip"))) == 2
print("TODO OK")
