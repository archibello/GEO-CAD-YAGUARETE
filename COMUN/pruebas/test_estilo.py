"""3.0.0 GIS to CAD / CAD to GIS: capas (LAYER_CODE), colores y rótulos de
QGIS llegan a IngeCAD; los cambios de capa y color vuelven a QGIS."""
import os, sys, tempfile, types
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
import shapefile
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False); assert lp.available, lp.reason
spec = lp.spec
buzon = import_module("ingecad_plugin_geocad.buzon")
puente = import_module("ingecad_plugin_geocad.puente")
enlace = import_module("ingecad_plugin_geocad.enlace")
estilo = import_module("ingecad_plugin_geocad.estilo")

doc = Document.new(); hist = History(doc); log = []; answers = []
class Tools:
    def start_tool(self, name):
        ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=log.append, finish=lambda: None,
                          ask_text=lambda p, d="": answers.pop(0) if answers else d,
                          ask_choice=lambda p, items, d="": (lambda a: None if a is None else next((i for i in items if i.startswith(a)), None))(answers.pop(0) if answers else None),
                          services=types.SimpleNamespace(document=doc))
        spec.tools[name](ctx).start()
class VP:
    def __init__(self): self.view = types.SimpleNamespace(zoom_extents=lambda *a: None)
    def push_view(self): pass
    def update(self): pass
win = types.SimpleNamespace(tools=Tools(), viewport=VP(), command_line=types.SimpleNamespace(echo=log.append),
                            isMinimized=lambda: False, raise_=lambda: None, activateWindow=lambda: None)
puente._state["window"] = win

# colores
assert estilo.color_of_hex("#FF0000") == (1, None) and estilo.color_of_hex("#000000") == (7, None)
assert estilo.color_of_hex("") is None and estilo.color_of_hex("#80ff0000") == (1, None)
aci, tc = estilo.color_of_hex("#123456"); assert tc == 0x123456 and 1 <= aci <= 255
# 3.1.1 rótulos: casi negro o casi blanco -> 7; los demás como siempre
assert estilo.label_color("#1a1a1a") == (7, None) and estilo.label_color("#f0f0f0") == (7, None)
assert estilo.label_color("#ff0000") == (1, None) and estilo.label_color("") is None

# una capa de líneas con LAYER_CODE y CAD_COLOR (como las del módulo Capas)
tmp = tempfile.mkdtemp(); base = os.path.join(tmp, "lineas")
w = shapefile.Writer(base, shapeType=shapefile.POLYLINE)
w.field("NOMBRE", "C", size=10); w.field("LAYER_CODE", "C", size=50); w.field("CAD_COLOR", "C", size=10)
w.line([[(0, 0), (10, 0)]]); w.record("a", "MUROS", "")
w.line([[(0, 5), (10, 5)]]); w.record("b", "EJES", "#ff0000")
w.line([[(0, 9), (10, 9)]]); w.record("c", "", "#123456")
w.close()
doc.doc.layers.add("EJES")          # ya existe en el dibujo y no es de la conexión

pres = {"campo_capa": "LAYER_CODE", "campo_color": "CAD_COLOR",
        "capas": {"MUROS": {"color": 3, "rgb": None, "tipo": "Continuous", "grosor": 0.5},
                  "EJES": {"color": 1, "rgb": None, "tipo": "NOEXISTE", "grosor": -1}},
        "objetos": {"0": ["MUROS", ""], "1": ["EJES", "#ff0000"], "2": ["", "#123456"]},
        "rotulos": {"0": ["a", 5, 0, 2.0, 30.0, "c", "#000000", ["rectangle", 5, 0, 4, 2, 90.0, "#ff0000"]],
                    "1": ["b", 5, 5, 1.5, 0.0, "c", "#00ff00", ["circle", 5, 5, 4, 4, 0.0, "#1a1a1a"]],
                    "2": ["", 5, 9, 1.0, 0.0, "c", ""]}}
ref = buzon.layer_ref("shp", base + ".shp", ""); ref["estilo"] = pres
buzon.send("ingecad", {"tipo": "conectar", "capas": [ref]}, "qgis")
for m in buzon.receive("ingecad"): puente.handle(m)
print("\n".join(log))
key = "SHP-lineas"
link = enlace.read_links(doc.doc)[key]
assert link.campo_capa == "LAYER_CODE" and link.campo_color == "CAD_COLOR", link
assert link.capas == {"MUROS": "MUROS", f"{key}-EJES": "EJES"}, link.capas
assert link.estilo == {0: ["MUROS", ""], 1: ["EJES", "#ff0000"], 2: ["", "#123456"]}, link.estilo
lay = doc.doc.layers.get("MUROS"); assert lay.color == 3 and lay.dxf.lineweight == 50, (lay.color, lay.dxf.lineweight)
assert doc.doc.layers.get(f"{key}-EJES").color == 1 and doc.doc.layers.get(f"{key}-EJES").dxf.linetype == "Continuous"
by_fid = {enlace.feat_tag(e).fid: e for e in doc.doc.modelspace() if enlace.feat_tag(e)}
assert by_fid[0].dxf.layer == "MUROS" and by_fid[0].dxf.get("color", 256) == 256
assert by_fid[1].dxf.layer == f"{key}-EJES" and by_fid[1].dxf.color == 1
assert by_fid[2].dxf.layer == key and by_fid[2].dxf.true_color == 0x123456
texts = [e for e in doc.doc.modelspace() if e.dxftype() == "TEXT"]
assert len(texts) == 2 and {t.dxf.layer for t in texts} == {f"{key}-ROTULOS"}, texts
t0 = next(t for t in texts if t.dxf.text == "a")
assert t0.dxf.height == 2.0 and t0.dxf.rotation == 30.0 and t0.dxf.color == 7, t0.dxf.all_existing_dxf_attribs()
assert tuple(t0.dxf.align_point)[:2] == (5, 0)
assert any("Capas por LAYER_CODE" in l for l in log) and any("2 rótulo(s)" in l and "2 con su fondo" in l for l in log), log
# 3.1.1 fondo de las etiquetas: círculo (casi negro -> 7) y rectángulo girado, en la capa de rótulos
circ = [e for e in doc.doc.modelspace() if e.dxftype() == "CIRCLE"]
assert len(circ) == 1 and circ[0].dxf.radius == 2 and tuple(circ[0].dxf.center)[:2] == (5, 5), circ
assert circ[0].dxf.layer == f"{key}-ROTULOS" and circ[0].dxf.color == 7
rect = [e for e in doc.doc.modelspace() if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == f"{key}-ROTULOS"]
assert len(rect) == 1 and rect[0].closed and rect[0].dxf.color == 1, rect
xs = [p[0] for p in rect[0].get_points("xy")]; ys = [p[1] for p in rect[0].get_points("xy")]
assert abs(max(xs) - min(xs) - 2) < 1e-9 and abs(max(ys) - min(ys) - 4) < 1e-9, (xs, ys)   # girado 90°
# QUITARROTULOS los borra como a los de ROTULOSIG (con sus fondos)
log.clear(); win.tools.start_tool("SHPLABELOFF"); assert any("2 rótulo(s) borrados (y 2 fondo(s))" in l for l in log), log
assert not [e for e in doc.doc.modelspace() if e.dxftype() == "CIRCLE"]
# las entidades sin etiqueta sobre las capas propias son de la conexión; la capa EJES ajena, no
tagged, untagged = enlace.linked_entities(doc, key); assert len(tagged) == 3 and not untagged
doc.doc.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "EJES"})
assert not enlace.linked_entities(doc, key)[1]

# IngeCAD -> QGIS: pasar de capa, cambiar el color y dibujar sobre MUROS
by_fid[0].dxf.layer = f"{key}-EJES"
by_fid[2].dxf.discard("true_color"); by_fid[2].dxf.color = 5
doc.doc.modelspace().add_lwpolyline([(0, 20), (10, 20)], dxfattribs={"layer": "MUROS", "color": 256})
edits, news = estilo.differences(doc, key)
assert sorted(edits) == [(0, "LAYER_CODE", "EJES"), (2, "CAD_COLOR", "#0000ff")], edits
assert len(news) == 1 and news[0][1] == "MUROS", news
log.clear(); win.tools.start_tool("SHPSTATUS"); assert any("capa/color: 2 objeto(s)" in l for l in log), log
log.clear(); answers[:] = ["Sí"]; win.tools.start_tool("QGISSAVE"); print("\n".join(log))
assert any("devueltas a QGIS" in l for l in log), log
r = shapefile.Reader(base)
recs = [rec.as_dict() for rec in r.records()]; r.close(); print(recs)
assert recs[0]["LAYER_CODE"] == "EJES" and recs[0]["NOMBRE"] == "a"
assert recs[1]["LAYER_CODE"] == "EJES" and recs[1]["CAD_COLOR"] == "#ff0000"
assert recs[2]["CAD_COLOR"] == "#0000ff" and recs[2]["LAYER_CODE"] == ""
assert len(recs) == 4 and recs[3]["LAYER_CODE"] == "MUROS" and recs[3]["CAD_COLOR"] == "", recs[3]
link = enlace.read_links(doc.doc)[key]
assert link.estilo[0] == ["EJES", ""] and link.estilo[2] == ["", "#0000ff"] and link.estilo[3] == ["MUROS", ""], link.estilo
assert not any(estilo.differences(doc, key))
log.clear(); win.tools.start_tool("QGISSAVE"); assert any("Sin cambios" in l for l in log), log
# un cambio sólo de capa avisa al desconectar
by_fid[1].dxf.layer = "MUROS"
log.clear(); answers[:] = ["No"]; win.tools.start_tool("SHPRELEASE"); assert any("Cancelado" in l for l in log), log
# deshacer el paso de capa/color deja las entidades como estaban
doc.doc.modelspace().add_lwpolyline([(0, 30), (10, 30)], dxfattribs={"layer": "MUROS"})
cmd = estilo.prepare_save(doc, key); hist.execute(cmd)
link = enlace.read_links(doc.doc)[key]; assert link.pending.get(1) == {"LAYER_CODE": "MUROS"}, link.pending
assert any(f < 0 and v == {"LAYER_CODE": "MUROS", "CAD_COLOR": ""} for f, v in link.pending.items()), link.pending
hist.undo()
link = enlace.read_links(doc.doc)[key]; assert not link.pending, link.pending
assert len(enlace.linked_entities(doc, key)[1]) == 1

# sin presentación (QGIS viejo o capa sin campos): todo como antes
base2 = os.path.join(tmp, "otra")
w = shapefile.Writer(base2, shapeType=shapefile.POLYLINE); w.field("N", "C", size=4)
w.line([[(0, 0), (1, 0)]]); w.record("x"); w.close()
buzon.send("ingecad", {"tipo": "conectar", "capas": [buzon.layer_ref("shp", base2 + ".shp", "")]}, "qgis")
for m in buzon.receive("ingecad"): puente.handle(m)
l2 = enlace.read_links(doc.doc)["SHP-otra"]; assert not l2.capas and not l2.estilo and not l2.campo_capa
assert estilo.differences(doc, "SHP-otra") == ([], [])

# 3.1.0 símbolos: cada punto llega como un bloque con el tamaño y el giro de QGIS, y ES el punto
base3 = os.path.join(tmp, "arboles")
w = shapefile.Writer(base3, shapeType=shapefile.POINT); w.field("ESPECIE", "C", size=10)
w.point(100, 100); w.record("tala"); w.point(110, 100); w.record("ceibo"); w.point(120, 100); w.record("x"); w.close()
ref = buzon.layer_ref("shp", base3 + ".shp", "")
ref["estilo"] = {"objetos": {"0": ["", "#00ff00"], "1": ["", "#00ff00"], "2": ["", ""]},
                 "simbolos": {"0": ["star", 2.0, 30.0], "1": ["Circle", 1.5, 0.0], "2": ["svg-raro", 0, 0]},
                 "rotulos": {"0": ["tala", 102, 100, 1.0, 0.0, "i", "#000000"]}}
log.clear(); buzon.send("ingecad", {"tipo": "conectar", "capas": [ref]}, "qgis")
for m in buzon.receive("ingecad"): puente.handle(m)
print("\n".join(log)); assert any("2 punto(s) con su símbolo" in l for l in log), log
k3 = "SHP-arboles"
ents = {enlace.feat_tag(e).fid: e for e in doc.doc.modelspace() if enlace.feat_tag(e) and enlace.feat_tag(e).key == k3}
star = ents[0]; assert star.dxftype() == "INSERT" and star.dxf.name == "GEOCAD-SIMBOLO-STAR", star.dxftype()
assert star.dxf.xscale == 2.0 and star.dxf.yscale == 2.0 and star.dxf.rotation == 30.0 and star.dxf.color == 3
assert ents[1].dxf.name == "GEOCAD-SIMBOLO-CIRCLE" and ents[2].dxftype() == "POINT"   # tamaño 0: punto
blk = doc.doc.blocks.get("GEOCAD-SIMBOLO-STAR"); assert len(list(blk)) == 1 and list(blk)[0].dxf.color == 0
assert next(iter(doc.doc.blocks.get("GEOCAD-SIMBOLO-CIRCLE"))).dxftype() == "CIRCLE"
# mover el símbolo mueve el punto en el archivo
star.dxf.insert = (105, 107)
log.clear(); answers[:] = ["Sí"]; win.tools.start_tool("QGISSAVE"); print("\n".join(log))
r = shapefile.Reader(base3); pts = [s.points[0] for s in r.shapes()]; r.close(); print(pts)
assert tuple(pts[0]) == (105, 107) and tuple(pts[1]) == (110, 100)
log.clear(); win.tools.start_tool("QGISSAVE"); assert any("Sin cambios" in l for l in log), log
print("TODO OK ESTILO")
