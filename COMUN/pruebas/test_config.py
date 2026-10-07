"""Configuración común: el mismo archivo para IngeCAD y QGIS."""
import os, sys, tempfile, types, json
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
from fixtures import make_parcelas, make_puntos
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False); assert lp.available, lp.reason
spec = lp.spec
config = import_module("ingecad_plugin_geocad.config")
enlace = import_module("ingecad_plugin_geocad.enlace")
shpio = import_module("ingecad_plugin_geocad.shpio")
assert str(config.config_path()).startswith(HOME)

class Session:
    def __init__(self): self.doc = Document.new(); self.hist = History(self.doc); self.log = []; self.answers = []
    def run(self, name, selection=None):
        self.log.clear(); answers = list(self.answers)
        def ask_text(p, d=""): return answers.pop(0) if answers else d
        def ask_choice(p, items, d=""):
            a = answers.pop(0) if answers else None
            return None if a is None else next((i for i in items if i.startswith(a)), None)
        ctx = ToolContext(execute=self.hist.execute, prompt=lambda s: None, echo=self.log.append, finish=lambda: None,
                          ask_text=ask_text, ask_choice=ask_choice, services=types.SimpleNamespace(document=self.doc))
        t = spec.tools[name](ctx); t.start()
        if selection is not None: t.on_selection(selection)
        self.answers = []; return "\n".join(self.log)
    def ents(self, fid=None): return [(t, e) for e in self.doc.doc.modelspace() if (t := enlace.feat_tag(e)) and (fid is None or t.fid == fid)]

# valores por defecto sin archivo
v = config.load(); assert v["formato_trabajo"] == "gpkg" and v["respaldos_a_conservar"] == 0
# por la línea de comandos de IngeCAD
s = Session(); s.answers = ["Sistema de coordenadas", "POSGAR 2007 / faja 4"]; out = s.run("SHPCONFIG"); print(out)
assert config.get("crs_proyecto") == "EPSG:5346"
s.answers = ["Respaldos a conservar", "5000"]; out = s.run("SHPCONFIG"); assert "No se guardó" in out, out
s.answers = ["Pedir confirmación", "No"]; s.run("SHPCONFIG"); assert config.get("confirmar_guardado") is False
config.save({"respaldos_a_conservar": 1, "tolerancia_arcos": 1.0}, "QGIS")      # lo cambia "QGIS"
data = json.loads(config.config_path().read_text()); assert data["_modificado_por"] == "QGIS"
# el otro programa agrega una clave propia: no se pierde
data["qgis_extra"] = 1; config.config_path().write_text(json.dumps(data)); config.save({"tolerancia_arcos": 2}, "IngeCAD")
assert json.loads(config.config_path().read_text())["qgis_extra"] == 1
# archivo dañado -> valores por defecto, sin romper
config.config_path().write_text("{roto"); assert config.load()["tolerancia_arcos"] == 5.0
config.save({"crs_proyecto": "EPSG:5346", "confirmar_guardado": False, "respaldos_a_conservar": 1, "tolerancia_arcos": 1.0}, "IngeCAD")

tmp = tempfile.mkdtemp(); shp = make_parcelas(tmp)          # .prj POSGAR 2007 faja 5
s = Session(); s.answers = [shp]; out = s.run("SHPCONNECT"); print(out)
assert "No se conectó" in out and "sistema del proyecto" in out
config.save({"crs_proyecto": "EPSG:5347"}, "IngeCAD")
s.answers = [shp]; out = s.run("SHPCONNECT"); assert "Conectada" in out, out
# arco con tolerancia 1°: muchos más vértices; sin pregunta de confirmación
(_, e), = [x for x in s.ents(0)]
p = list(e.get_points("xyb")); p[0] = (p[0][0], p[0][1], 0.4); e.set_points(p, format="xyb")
out = s.run("SHPCHECKIN"); print(out); assert "Guardado" in out and "?" not in out
n1 = len(shpio.Shapefile(shp).geometry(0).parts[0]); print("vértices con 1°:", n1); assert n1 > 40
(_, e), = [x for x in s.ents(1)]; q = list(e.get_points("xy")); q[0] = (q[0][0] + 1, q[0][1]); e.set_points(q, format="xy")
s.run("SHPCHECKIN")
zips = list((Path(tmp) / "_respaldos_ingecad").glob("*.zip")); print([z.name for z in zips]); assert len(zips) == 1
# carpeta de respaldos configurable
config.save({"carpeta_respaldos": "copias"}, "IngeCAD")
(_, e), = [x for x in s.ents(2) if x[0].part == 0]; q = list(e.get_points("xy")); q[0] = (q[0][0] + 1, q[0][1]); e.set_points(q, format="xy")
s.run("SHPCHECKIN"); assert list((Path(tmp) / "copias").glob("*.zip"))
try: config.save({"carpeta_respaldos": "../afuera"}, "IngeCAD"); raise SystemExit("debió fallar")
except ValueError as exc: print("ok:", exc)
print("TODO OK CONFIG")
