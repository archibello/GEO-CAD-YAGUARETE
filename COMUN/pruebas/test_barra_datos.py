import os, sys, tempfile, types, shutil
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
from fixtures import make_parcelas
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False); assert lp.available, lp.reason
spec = lp.spec
for n in ("SHPTABLE", "SHPQUERY", "SHPSPATIAL", "SHPTHEME", "SHPTHEMEOFF", "SHPLABEL", "SHPLABELOFF", "SHPNEW"): assert n in spec.tools, n
enlace = import_module("ingecad_plugin_geocad.enlace")
shpio = import_module("ingecad_plugin_geocad.shpio")
G = import_module("ingecad_plugin_geocad.gpkgio")
HD = import_module("ingecad_plugin_geocad.herramientas_datos")
doc = Document.new(); hist = History(doc); log = []
services = types.SimpleNamespace(document=doc)
def run(name, answers=(), sel=None):
    a = list(answers); log.clear()
    ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=log.append, finish=lambda: None,
        ask_text=lambda p, d="": a.pop(0) if a else d,
        ask_choice=lambda p, items, d="": (lambda x: None if x is None else next((i for i in items if i.startswith(x)), None))(a.pop(0) if a else None),
        services=services)
    t = spec.tools[name](ctx); t.start()
    if sel is not None: t.on_selection(sel)
    return "\n".join(log)
msp = doc.doc.modelspace()
tagged = lambda key: [(t, e) for e in msp if (t := enlace.feat_tag(e)) and t.key == key]
shp = make_parcelas(tempfile.mkdtemp()); run("SHPCONNECT", [shp]); key = "SHP-parcelas"
# consulta -> selección
out = run("SHPQUERY", ["SUP_M2 > 502"]); print(out)
sel = {enlace.feat_tag(e).fid for e in msp if e.dxf.handle in services.selection}; assert sel == {3, 4}, sel
out = run("SHPQUERY", ["SUP_M2 >>> 1"]); assert "no válida" in out, out
# ubicación
x0, y0 = 5_430_000.0, 6_300_000.0
zona = msp.add_lwpolyline([(x0 - 1, y0 - 1), (x0 + 65, y0 - 1), (x0 + 65, y0 + 30), (x0 - 1, y0 + 30)], close=True)
out = run("SHPSPATIAL", ["Dentro"], [zona]); print(out)
assert {enlace.feat_tag(e).fid for e in msp if e.dxf.handle in services.selection} == {0, 1}
out = run("SHPSPATIAL", ["A una distancia", "15"], [zona]); assert "3 objeto" in out, out
# temático por categorías y por rangos, con deshacer
out = run("SHPTHEME", ["TITULAR"]); print(out)
colors = {t.fid: e.dxf.color for t, e in tagged(key)}; assert len(set(colors.values())) >= 4, colors
out = run("SHPTHEME", ["SUP_M2", "Por rangos", "3"]); print(out)
cs = {t.fid: e.dxf.color for t, e in tagged(key)}; assert cs[0] == 51 and cs[4] == 10, cs
hist.undo(); assert {t.fid: e.dxf.color for t, e in tagged(key)} == colors
run("SHPTHEMEOFF"); assert all(e.dxf.color == 256 for _t, e in tagged(key))
# rótulos (no son datos: no aparecen como objetos nuevos)
out = run("SHPLABEL", ["PARTIDA", "1.5"]); print(out)
labels = HD.existing_labels(doc, key); assert len(labels) == 5 and labels[0].dxf.layer == "SHP-parcelas-ROTULOS"
lab2 = [l for l in labels if l.dxf.text == "01-0002"][0]
from ingecad_plugin_geocad import datos as D
ring = [(x0 + 60, y0), (x0 + 60, y0 + 25), (x0 + 80, y0 + 25), (x0 + 80, y0)]
p = lab2.dxf.insert if lab2.dxf.halign == 0 else lab2.dxf.align_point
assert D.point_in_ring((p.x, p.y), ring) and not D.point_in_ring((p.x, p.y), [(x0 + 65, y0 + 5), (x0 + 70, y0 + 5), (x0 + 70, y0 + 10), (x0 + 65, y0 + 10)])
out = run("SHPLABEL", ["TITULAR", "2"]); assert "reemplazan a 5" in out and len(HD.existing_labels(doc, key)) == 5
out = run("SHPSTATUS"); assert "0 nuevo(s)" in out, out
run("SHPLABELOFF"); assert not HD.existing_labels(doc, key)
hist.undo(); assert len(HD.existing_labels(doc, key)) == 5
# objeto nuevo con formulario (dibujado en la capa 0)
nuevo = msp.add_lwpolyline([(x0 + 200, y0), (x0 + 220, y0), (x0 + 220, y0 + 20), (x0 + 200, y0 + 20)], close=True)
otro = msp.add_lwpolyline([(x0 + 240, y0), (x0 + 260, y0), (x0 + 260, y0 + 20)], close=True)
out = run("SHPNEW", ["01-9999", "Fernández", "abc", "400", "13", "15/03/2025", "V", "Sí"], [nuevo, otro]); print(out)
assert "no es un número" in out and "2 objeto(s) nuevos" in out
assert nuevo.dxf.layer == key and enlace.feat_tag(nuevo).fid < 0
data = D.LayerData(doc, key); news = [r for r in data.rows if r.new]; assert len(news) == 2 and news[0].values["TITULAR"] == "Fernández"
hist.undo(); assert nuevo.dxf.layer == "0" and enlace.feat_tag(nuevo) is None and not [f for f in enlace.read_links(doc.doc)[key].pending if f < 0]
hist.redo(); assert enlace.feat_tag(nuevo).fid < 0
out = run("SHPSTATUS"); assert "2 nuevo(s)" in out, out
out = run("SHPCHECKIN", ["Sí"]); print(out); assert "Guardado" in out
sf = shpio.Shapefile(shp); print(len(sf), sf.attributes(5)); assert len(sf) == 7
a5 = sf.attributes(5); assert a5["TITULAR"] == "Fernández" and a5["SUP_M2"] == 400.0 and a5["EDIFICADO"] is True
assert enlace.feat_tag(nuevo).fid in (5, 6) and not [f for f in enlace.read_links(doc.doc)[key].pending if f < 0]
out = run("SHPSTATUS"); assert "0 nuevo(s)" in out and "0 modificado(s)" in out, out
# GeoPackage: objeto nuevo con formulario
gp = os.path.join(tempfile.mkdtemp(), "c.gpkg"); shutil.copy(os.environ["GDAL_GPKG"] + "/poly_golden.gpkg", gp)
doc2 = Document.new(); hist2 = History(doc2); doc, hist = doc2, hist2; services.document = doc2; msp = doc2.doc.modelspace()
run("SHPCONNECT", [gp])
n2 = msp.add_lwpolyline([(480000, 4760000), (480050, 4760000), (480050, 4760050)], close=True)
out = run("SHPNEW", ["123,5", "7", "NUEVA"], [n2]); print(out)
out = run("SHPCHECKIN", ["Sí"]); print(out); assert "Guardado" in out
c = G.connect(gp); L = G.open_layer(c, gp, "poly"); rows = G.read_rows(c, L); c.close()
fid = enlace.feat_tag(n2).fid; print(fid, rows[fid][1]); assert rows[fid][1] == (123.5, 7, "NUEVA")
print("TODO OK BARRA DATOS")
