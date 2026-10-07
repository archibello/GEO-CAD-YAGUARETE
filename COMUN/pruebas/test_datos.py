import os, sys, tempfile, types, datetime as dt
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
D = import_module("ingecad_plugin_geocad.datos")
enlace = import_module("ingecad_plugin_geocad.enlace")
spec = lp.spec
doc = Document.new(); hist = History(doc); log = []
def run(name, answers=(), sel=None):
    a = list(answers); log.clear()
    ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=log.append, finish=lambda: None,
        ask_text=lambda p, d="": a.pop(0) if a else d,
        ask_choice=lambda p, items, d="": (lambda x: None if x is None else next((i for i in items if i.startswith(x)), None))(a.pop(0) if a else None),
        services=types.SimpleNamespace(document=doc))
    t = spec.tools[name](ctx); t.start()
    if sel is not None: t.on_selection(sel)
    return "\n".join(log)
shp = make_parcelas(tempfile.mkdtemp())
run("SHPCONNECT", [shp])
key = "SHP-parcelas"
ents = lambda fid: [e for e in doc.doc.modelspace() if (t := enlace.feat_tag(e)) and t.fid == fid]
run("SHPATTR", ["TITULAR", "Gómez Hnos"], [ents(0)[0]])
L = D.LayerData(doc, key)
print([f.family for f in L.fields]); r0 = L.row(0); print(r0.values, r0.pending)
assert r0.values["TITULAR"] == "Gómez Hnos" and r0.pending == {"TITULAR"}
def q(text): f = D.parse_query(text, L.fields); return sorted(r.fid for r in L.rows if f(r))
assert q("MANZANA = 12") == [0, 1, 2, 3, 4]
assert q("SUP_M2 > 501,5") == [2, 3, 4]
assert q("SUP_M2 >= 502 y SUP_M2 < 504") == [2, 3]
assert q("titular contiene 'gómez'") == [0, 1], q("titular contiene 'gómez'")
assert q("TITULAR CONTIENE GÓMEZ O PARTIDA EMPIEZA '01-0004'") == [0, 1, 4]
assert q("NO (EDIFICADO = V)") == [1, 3]
assert q("EDIFICADO = falso") == [1, 3]
assert q("FECHA ENTRE 01/01/2024 Y 31/01/2024") == [0, 1, 2, 3, 4]
assert q("FECHA > 2024-02-01") == []
assert q("(MANZANA = 12 O MANZANA = 13) Y NO TITULAR ES NULO") == [0, 1, 2, 3, 4]
assert q("TITULAR NO ES NULO y [SUP_M2] <> 500") == [1, 2, 3, 4]
assert q("") == [0, 1, 2, 3, 4]
for bad in ["MANZANA", "XXX = 1", "SUP_M2 = abc", "FECHA = 99/99/9999", "MANZANA = 1 Y", "(MANZANA = 1"]:
    try: D.parse_query(bad, L.fields); print("NO FALLÓ", bad)
    except D.QueryError as e: print("ok:", bad, "->", e)
# ubicación: zona que cubre las parcelas 0 y 1 completas, toca la 2
x0, y0 = 5_430_000.0, 6_300_000.0
z = doc.doc.modelspace().add_lwpolyline([(x0 - 1, y0 - 1), (x0 + 65, y0 - 1), (x0 + 65, y0 + 30), (x0 - 1, y0 + 30)], close=True)
assert D.spatial_select(doc, key, [z], "dentro") == {0, 1}, D.spatial_select(doc, key, [z], "dentro")
assert D.spatial_select(doc, key, [z], "toca") == {0, 1, 2}
c = doc.doc.modelspace().add_circle((x0 + 150, y0 + 12), 2)
assert D.spatial_select(doc, key, [c], "distancia", 5) == set()
assert D.spatial_select(doc, key, [c], "distancia", 12) == {4}, D.spatial_select(doc, key, [c], "distancia", 12)
a, l = D.feature_measures(ents(2)); print("área con hueco", a, l); assert abs(a - (500 - 25)) < 1e-6
a, l = D.feature_measures(ents(0)); assert abs(a - 500) < 1e-6 and abs(l - 90) < 1e-6
# estado de la tabla
T = D.TableState(doc, key)
print(T.columns); assert T.columns[0] == "FID" and T.columns[-1] == "Área"
assert len(T.rows) == 5 and T.text(T.rows[0], 0) == "0"
T.sort(T.columns.index("SUP_M2"), True); assert [r.fid for r in T.rows] == [4, 3, 2, 1, 0]
T.sort(T.columns.index("TITULAR"), False); print([T.text(r, 2) for r in T.rows])
T.set_query("SUP_M2 >= 502"); assert {r.fid for r in T.rows} == {2, 3, 4}
r0 = [r for r in T.data.rows if r.fid == 0][0]
assert T.is_pending(r0, T.columns.index("TITULAR")) and not T.is_pending(r0, T.columns.index("PARTIDA"))
assert T.editable(T.columns.index("TITULAR")) and not T.editable(0) and not T.editable(len(T.columns) - 1)
print(T.summary({2, 3})); assert "2 seleccionados" in T.summary({2, 3}) and "975" in T.summary({2, 3}).replace(" ", "")
T.only_selected = {3}; T.apply(); assert [r.fid for r in T.rows] == [3]
try: T.set_query("SUP_M2 >"); raise SystemExit("debía fallar")
except D.QueryError: pass
print("TODO OK DATOS")
