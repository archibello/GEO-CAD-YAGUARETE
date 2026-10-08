import os, sys, tempfile, types, shutil, json
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
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
assert spec.name == "GeoCAD Yaguareté" and "QGISSAVE" in spec.tools
buzon = import_module("ingecad_plugin_geocad.buzon")
puente = import_module("ingecad_plugin_geocad.puente")
enlace = import_module("ingecad_plugin_geocad.enlace")

doc = Document.new(); hist = History(doc); log = []
answers = []
class Tools:
    def start_tool(self, name):
        ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=log.append, finish=lambda: None,
                          ask_text=lambda p, d="": answers.pop(0) if answers else d,
                          ask_choice=lambda p, items, d="": (lambda a: None if a is None else next((i for i in items if i.startswith(a)), None))(answers.pop(0) if answers else None),
                          services=types.SimpleNamespace(document=doc))
        spec.tools[name](ctx).start()
class VP:
    def __init__(self): self.view = types.SimpleNamespace(zoom_extents=lambda *a: log.append(f"zoom {a}"))
    def push_view(self): pass
    def update(self): pass
win = types.SimpleNamespace(tools=Tools(), viewport=VP(), command_line=types.SimpleNamespace(echo=log.append),
                            isMinimized=lambda: False, raise_=lambda: None, activateWindow=lambda: None)
puente._state["window"] = win

tmp = tempfile.mkdtemp(); shp = make_parcelas(tmp)
gp = os.path.join(tmp, "datos.gpkg"); shutil.copy(os.environ["GDAL_GPKG"] + "/poly_golden.gpkg", gp)
# QGIS manda dos capas (un gpkg en EPSG:27700 y un shp POSGAR): la segunda se rechaza por sistema distinto
buzon.send("ingecad", {"tipo": "conectar", "capas": [buzon.layer_ref("gpkg", gp, "poly")], "extension": [1, 2, 3, 4]}, "qgis")
for m in buzon.receive("ingecad"): puente.handle(m)
print("\n".join(log)); assert "zoom (1.0, 2.0, 3.0, 4.0)" in log
links = enlace.read_links(doc.doc); assert list(links) == ["GPKG-poly"]
msgs = buzon.receive("qgis"); print(msgs); assert msgs[0]["tipo"] == "conectado" and msgs[0]["capas"][0]["tabla"] == "poly"
# repetir el envío no duplica
buzon.send("ingecad", {"tipo": "conectar", "capas": [buzon.layer_ref("gpkg", gp, "poly")]}, "qgis")
log.clear(); [puente.handle(m) for m in buzon.receive("ingecad")]; assert any("ya tenía conectado todo" in l for l in log), log
# editar y devolver todo con un clic
e = next(e for e in doc.doc.modelspace() if enlace.feat_tag(e))
p = list(e.get_points("xy")); p[0] = (p[0][0] + 3, p[0][1]); e.set_points(p, format="xy")
log.clear(); answers[:] = ["Sí"]; win.tools.start_tool("QGISSAVE"); print("\n".join(log))
assert any("devueltas a QGIS" in l for l in log)
msgs = buzon.receive("qgis"); assert msgs[-1]["tipo"] == "guardado", msgs
log.clear(); win.tools.start_tool("QGISSAVE"); assert any("Sin cambios" in l for l in log), log
# mensajes viejos se descartan; los temporales no se leen
old = buzon.send("ingecad", {"tipo": "conectar", "capas": [], "fecha": 0}, "qgis"); assert buzon.receive("ingecad") == []
buzon.heartbeat("ingecad"); assert buzon.is_alive("ingecad")
print("TODO OK PUENTE")
