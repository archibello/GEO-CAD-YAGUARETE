import os, sys, tempfile, shutil, glob
CFG = tempfile.mkdtemp(); os.environ["XDG_CONFIG_HOME"] = CFG; os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from core.plugins import PluginManager, user_plugins_dir
from core import scripting
root = user_plugins_dir(); assert str(root).startswith(CFG)
# lo de antes: la versión de prueba (conexion_shp) y el Puente 1.x (puente_qgis)
(root / "conexion_shp").mkdir(parents=True); (root / "conexion_shp" / "__init__.py").write_text("raise RuntimeError('vieja')")
(root / "puente_qgis").mkdir(); (root / "puente_qgis" / "viejo.py").write_text("# viejo")
# y una configuración del Puente 1.x, que GeoCAD trae sola
old = Path(os.environ["HOME"]) / ".config" / "ingecad-qgis"; old.mkdir(parents=True)
(old / "configuracion.json").write_text('{"formato_trabajo": "shp"}')
class Host:
    document = None
    def __init__(self): self.calls = []; self.command_line = type("C", (), {"echo": lambda s, t: print("IngeCAD>", t)})()
    def __getattr__(self, n): return lambda *a, **k: self.calls.append(n) or True
host = Host(); host.history = type("H", (), {"_undo": []})(); host.plugins = PluginManager(host=host, bundled_dir=Path(CFG) / "nada", user_dir=root)
host.plugins.discover()
inst = sorted(glob.glob(str(Path(__file__).resolve().parents[2] / "VERSIONES" / "*" / "GeoCad Tool" / "instalar_geocad_*.py")), key=lambda f: tuple(int(x) for x in f.rsplit("_", 1)[1][:-3].split(".")))[-1]
count, err = scripting.run_python(inst, host); print("run_python:", count, err)
assert err is None
# lo viejo se retira pero queda guardado
assert not (root / "conexion_shp").exists() and not (root / "puente_qgis").exists()
assert (root / ".anterior-puente_qgis" / "viejo.py").exists() and (root / ".anterior-conexion_shp").exists()
assert host.plugins.is_active("geocad"), host.plugins.loaded.get("geocad")
assert "register_tools" in host.calls and "menus_changed" in host.calls
spec = host.plugins.loaded["geocad"].spec
assert spec.name == "GeoCAD Yaguareté" and "SHPCONNECT" in spec.tools and "SHPTABLE" in spec.tools
mods = sys.modules["ingecad_plugin_geocad.modulos"]; cfg = sys.modules["ingecad_plugin_geocad.config"]
assert mods.elegido("ingecad")                          # la primera elección quedó guardada
assert cfg.get("formato_trabajo") == "shp"              # configuración del Puente 1.x migrada
# reinstalar encima (la misma versión) también queda limpio y no vuelve a preguntar
mods.guardar("ingecad", {"datos": False})
count, err = scripting.run_python(inst, host); assert err is None and host.plugins.is_active("geocad")
assert not mods.activo("ingecad", "datos") and "SHPTABLE" not in host.plugins.loaded["geocad"].spec.tools
# un instalador dañado no toca nada
bad = Path(tempfile.mkdtemp()) / "roto.py"; t = Path(inst).read_text(); i = t.index('DATA = """') + 20
bad.write_text(t[:i] + ("A" if t[i] != "A" else "B") + t[i + 1:])
before = sorted(p.name for p in (root / "geocad").iterdir())
count, err = scripting.run_python(bad, host)
assert sorted(p.name for p in (root / "geocad").iterdir()) == before
print("TODO OK INSTALADOR")
