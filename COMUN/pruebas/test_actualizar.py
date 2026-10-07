"""Actualizar el puente desde el menú, en los dos lados: busca la versión
más nueva en la carpeta de actualizaciones, la instala y avisa al otro."""
import os, sys, tempfile, types, shutil, zipfile, re, importlib.util
CFG = tempfile.mkdtemp(); os.environ["XDG_CONFIG_HOME"] = CFG
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
ING = ROOT / "INGECAD" / "codigo" / "geocad"
QG = ROOT / "QGIS" / "codigo" / "geocad"

spec_b = importlib.util.spec_from_file_location("build_puente", ROOT / "COMUN" / "build.py")
build = importlib.util.module_from_spec(spec_b); spec_b.loader.exec_module(build)
build.sincronizar()                                # lo mismo que hace build.py

def con_version(src: Path, version: str) -> Path:
    """Copia del código con otro número de versión (una «versión futura»)."""
    dst = Path(tempfile.mkdtemp()) / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    if (dst / "__init__.py").read_text().find('version="') >= 0:
        t = (dst / "__init__.py").read_text()
        (dst / "__init__.py").write_text(re.sub(r'version="[^"]+"', f'version="{version}"', t, count=1))
    if (dst / "metadata.txt").exists():
        t = (dst / "metadata.txt").read_text()
        (dst / "metadata.txt").write_text(re.sub(r"^version=.*$", f"version={version}", t, flags=re.M))
        t = (dst / "plugin.py").read_text()
        (dst / "plugin.py").write_text(re.sub(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', t, flags=re.M))
    return dst

def instalador(version: str) -> str:
    return build.instalador(con_version(ING, version), version)


# ---- una carpeta de proyecto con varias versiones ---------------------------
proj = Path(tempfile.mkdtemp()) / "000-PUENTE"
(proj / "INGECAD" / "versiones").mkdir(parents=True)
(proj / "QGIS" / "versiones").mkdir(parents=True)
(proj / "COMUN" / "entregas").mkdir(parents=True)
(proj / "INGECAD" / "versiones" / "instalar_geocad_1.2.0.py").write_text("# viejo")
(proj / "INGECAD" / "versiones" / "instalar_geocad_9.9.9.py").write_text(instalador("9.9.9"), encoding="utf-8")
(proj / "COMUN" / "CAMBIOS_9.9.9.txt").write_text("Versión de prueba 9.9.9: trae cosas nuevas.")
(proj / "QGIS" / "versiones" / "geocad_qgis_1.2.0.zip").write_bytes(build.zip_folder(QG, "geocad"))
qsrc = con_version(QG, "9.10.0")
inner = build.zip_folder(qsrc, "geocad")
with zipfile.ZipFile(proj / "COMUN" / "entregas" / "GeoCAD_9.10.0.zip", "w") as zf:
    zf.writestr("GeoCAD_9.10.0/1_QGIS_geocad_qgis_9.10.0.zip", inner)
    zf.writestr("GeoCAD_9.10.0/CAMBIOS_9.10.0.txt", "QGIS 9.10.0")
(proj / "_respaldos_ingecad").mkdir(); (proj / "_respaldos_ingecad" / "instalar_geocad_99.0.0.py").write_text("x")

sys.path.insert(0, str(ING.parent))
import geocad.actualizar as A
assert [c.version for c in A.buscar(proj, "ingecad")] == ["9.9.9", "1.2.0"]     # _respaldos se ignora
assert [c.version for c in A.buscar(proj, "qgis")] == ["9.10.0", "1.2.0"]       # 9.10 > 1.2 (no alfabético)
assert A.mas_nueva(proj, "ingecad", "9.9.9") is None
c = A.mas_nueva(proj, "qgis", "1.3.0"); assert c.dentro and c.nombre == "1_QGIS_geocad_qgis_9.10.0.zip"
assert A.extraer(c).read_bytes() == inner and A.cambios(c) == "QGIS 9.10.0"
assert "9.9.9" in A.cambios(A.mas_nueva(proj, "ingecad", "1.0.0"))
assert A.buscar(proj / "no-existe", "qgis") == [] and A.buscar("", "qgis") == []
sys.path.remove(str(ING.parent)); del sys.modules["geocad.actualizar"], sys.modules["geocad"]
print("ok buscar")

# ---- IngeCAD: instala la versión actual y se actualiza desde el menú --------
from core.plugins import PluginManager, user_plugins_dir
from core import scripting
root = user_plugins_dir()
class Host:
    document = None
    def __init__(self): self.calls = []; self.command_line = types.SimpleNamespace(echo=lambda t: print("IngeCAD>", t))
    def __getattr__(self, n): return lambda *a, **k: self.calls.append(n) or True
host = Host(); host.history = types.SimpleNamespace(_undo=[])
host.plugins = PluginManager(host=host, bundled_dir=Path(CFG) / "nada", user_dir=root); host.plugins.discover()
actual_inst = Path(tempfile.mkdtemp()) / "instalar_actual.py"
actual_inst.write_text(build.instalador(con_version(ING, "1.4.0"), "1.4.0"), encoding="utf-8")
_c, err = scripting.run_python(actual_inst, host); assert err is None, err
assert host.plugins.loaded["geocad"].spec.version == "1.4.0"

mod = sys.modules["ingecad_plugin_geocad.actualizacion"]
cfg = sys.modules["ingecad_plugin_geocad.config"]
qb = sys.modules["ingecad_plugin_geocad.buzon"]
log, preguntas, pedidas = [], [], []
mod._pedir_carpeta = lambda w, a: pedidas.append(a) or str(proj)
mod._preguntar = lambda w, t, x: preguntas.append(x) or True
spec = host.plugins.loaded["geocad"].spec
assert "QGISUPDATE" in spec.commands
ctx = types.SimpleNamespace(host=host, echo=log.append)
spec.commands["QGISUPDATE"](ctx)
print("\n".join(log))
assert pedidas == [""] and cfg.get("carpeta_actualizaciones") == str(proj)      # pidió la carpeta y la guardó
assert "nueva:     9.9.9" in preguntas[0] and "Versión de prueba 9.9.9" in preguntas[0]
assert host.plugins.loaded["geocad"].spec.version == "9.9.9"               # quedó instalada la nueva
assert host.plugins.is_active("geocad")
assert (root / ".anterior-geocad").exists()
msgs = qb.receive("qgis"); assert [m["tipo"] for m in msgs] == ["actualizar"] and msgs[0]["carpeta"] == str(proj)
# otra vez: ya está la última (no pregunta), y la carpeta guardada no se vuelve a pedir
mod = sys.modules["ingecad_plugin_geocad.actualizacion"]
mod._pedir_carpeta = lambda w, a: pedidas.append(a) or None
mod._preguntar = lambda w, t, x: preguntas.append(x) or True
log.clear(); host.plugins.loaded["geocad"].spec.commands["QGISUPDATE"](ctx)
assert "ya está en la última versión (9.9.9)" in log[-1] and len(preguntas) == 1 and len(pedidas) == 1
# si dice que no, no se instala nada
(proj / "INGECAD" / "versiones" / "instalar_geocad_10.0.0.py").write_text(instalador("10.0.0"), encoding="utf-8")
mod._preguntar = lambda w, t, x: False
log.clear(); host.plugins.loaded["geocad"].spec.commands["QGISUPDATE"](ctx)
assert host.plugins.loaded["geocad"].spec.version == "9.9.9" and "no se instaló nada" in log[-1]
# el aviso de QGIS ofrece la versión nueva sin contestarle a QGIS
qb.receive("qgis"); mod._preguntar = lambda w, t, x: True
mod.desde_qgis(host, {"tipo": "actualizar", "carpeta": str(proj)}, log.append)
assert host.plugins.loaded["geocad"].spec.version == "10.0.0" and qb.receive("qgis") == []
print("ok IngeCAD")

# ---- QGIS: se actualiza desde su menú y avisa a IngeCAD ----------------------
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir()
shutil.copytree(QG, plugins / "geocad", ignore=shutil.ignore_patterns("__pycache__"))
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(plugins)]
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QTimer
import geocad as ingecad_puente
from geocad import plugin as qp, buzon as qgb
class Bar:
    def __init__(self): self.msgs = []
    def pushMessage(self, title, text, level=None, duration=0): self.msgs.append(text)
bar = Bar()
class MB:
    def insertMenu(self, b, m): pass
    def removeAction(self, a): pass
iface = types.SimpleNamespace(mainWindow=lambda: types.SimpleNamespace(menuBar=lambda: MB(), removeToolBar=lambda t: None),
                              helpMenu=lambda: types.SimpleNamespace(menuAction=lambda: None),
                              messageBar=lambda: bar, addToolBar=lambda n: None)
qp.modulos.guardar("qgis", {"puente": True})
P = ingecad_puente.classFactory(iface); P.initGui()
for f in QTimer.shots: f()
QTimer.shots.clear()
assert any(getattr(i, "text", "") == "Actualizar GeoCAD (QGIS e IngeCAD)..." for i in P.menu.items)
qgb.receive("ingecad")
QMessageBox.answer = QMessageBox.StandardButton.Yes; QMessageBox.shown.clear()
assert P.update_bridge(False) is True                      # la carpeta ya está en la configuración común
meta = (plugins / "geocad" / "metadata.txt").read_text()
assert "version=9.10.0" in meta and (plugins / ".anterior-geocad").exists()
assert not (plugins / ".instalando-geocad").exists()
assert [m["tipo"] for m in qgb.receive("ingecad")] == ["actualizar"]
for f in QTimer.shots: f()                                  # recargar: sin qgis.utils -> aviso
assert "Reinicie QGIS" in QMessageBox.shown[-1]
QTimer.shots.clear()
# un aviso de IngeCAD con nada nuevo para QGIS: no pregunta ni muestra nada
qp.VERSION = "9.10.0"; QMessageBox.answer = None; n = len(bar.msgs)
P._handle({"tipo": "actualizar", "carpeta": str(proj)})
for f in QTimer.shots: f()
assert len(bar.msgs) == n and qgb.receive("ingecad") == []
# un .zip dañado no toca lo instalado
bad = Path(tempfile.mkdtemp()) / "geocad_qgis_99.0.0.zip"; bad.write_bytes(b"no es un zip")
before = sorted(p.name for p in (plugins / "geocad").iterdir())
try:
    qp.actualizar.instalar_zip(bad, plugins, "geocad"); raise SystemExit("debió fallar")
except Exception as exc:
    assert not isinstance(exc, SystemExit)
assert sorted(p.name for p in (plugins / "geocad").iterdir()) == before
print("ok QGIS")
print("TODO OK ACTUALIZAR")
