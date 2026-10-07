"""El instalador único: un solo archivo instala y activa GeoCAD en IngeCAD y en
QGIS, desde la Consola (con los dos programas cerrados) o con AP en IngeCAD.
Se arma una carpeta personal falsa con la misma forma que la de Fernando:
IngeCAD y QGIS 4 en Flatpak, el Puente 1.4.0 instalado y activo."""
import os, sys, tempfile, subprocess, shutil, glob, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
inst = sorted(glob.glob(str(ROOT / "VERSIONES" / "*" / "GeoCad Tool" / "instalar_geocad_*.py")),
              key=lambda f: tuple(int(x) for x in f.rsplit("_", 1)[1][:-3].split(".")))[-1]
VERSION = Path(inst).stem.rsplit("_", 1)[1]

def casa():
    home = Path(tempfile.mkdtemp())
    ing = home / ".var/app/org.ingecad.IngeCAD/config/IngeCAD"
    (ing / "plugins/puente_qgis").mkdir(parents=True)
    (ing / "plugins/puente_qgis/__init__.py").write_text("# Puente 1.4.0")
    (ing / "IngeCAD.conf").write_text(
        "[input]\nright_click=enter\n\n[plugins]\nconexion_shp\\enabled=false\n"
        "puente_qgis\\enabled=true\npuente_qgis\\toolbar=true\n\n[startup]\nshow=false\n")
    qg = home / ".var/app/org.qgis.qgis/data/QGIS/QGIS4/profiles/default"
    (qg / "python/plugins/Trim_Tool").mkdir(parents=True)
    (qg / "QGIS").mkdir()
    (qg / "QGIS/QGIS4.ini").write_text(
        "[Cad]\nx=1\n\n[PythonPlugins]\nEasyFillet=true\ningecad_puente=true\nxyz_coordinate_tool=true\n"
        "\n[QgsCollapsibleGroupBox]\ny=2\n")
    return home, ing, qg

# ---- 1. desde la Consola: instala y activa los dos ---------------------------------------
home, ing, qg = casa()
r = subprocess.run([sys.executable, inst], env={**os.environ, "HOME": str(home), "PYTHONPATH": ""},
                   capture_output=True, text=True, timeout=120)
print(r.stdout); assert r.returncode == 0, r.stderr
assert "IngeCAD: GeoCAD instalado y activado" in r.stdout and "QGIS: GeoCAD " + VERSION in r.stdout
# IngeCAD: plugin nuevo, el Puente retirado con copia, activado en IngeCAD.conf (sin tocar el resto)
assert (ing / "plugins/geocad/__init__.py").exists()
assert not (ing / "plugins/puente_qgis").exists() and (ing / "plugins/.anterior-puente_qgis/__init__.py").exists()
conf = (ing / "IngeCAD.conf").read_text()
assert "geocad\\enabled=true" in conf and "geocad\\toolbar=true" in conf
assert "puente_qgis\\enabled=false" in conf and "puente_qgis\\enabled=true" not in conf
assert "[input]\nright_click=enter" in conf and "[startup]\nshow=false" in conf
assert conf.count("[plugins]") == 1
# QGIS: complemento copiado (con Dibujo y Capas adentro) y activado en QGIS4.ini
assert (qg / "python/plugins/geocad/metadata.txt").read_text().count("version=" + VERSION) == 1
assert (qg / "python/plugins/geocad/dibujo/plugin.py").exists() and (qg / "python/plugins/geocad/capas/plugin.py").exists()
assert (qg / "python/plugins/Trim_Tool").exists()                       # lo demás no se toca
ini = (qg / "QGIS/QGIS4.ini").read_text()
sec = ini.split("[PythonPlugins]\n", 1)[1].split("\n\n", 1)[0].splitlines()
assert "geocad=true" in sec and "EasyFillet=true" in sec and "[QgsCollapsibleGroupBox]\ny=2" in ini
assert ini.count("[PythonPlugins]") == 1
# otra vez encima: deja copia de la anterior y no duplica claves
r = subprocess.run([sys.executable, inst], env={**os.environ, "HOME": str(home), "PYTHONPATH": ""},
                   capture_output=True, text=True, timeout=120)
assert r.returncode == 0 and (qg / "python/plugins/.anterior-geocad").exists()
assert (qg / "QGIS/QGIS4.ini").read_text().count("geocad=true") == 1
assert (ing / "IngeCAD.conf").read_text().count("geocad\\enabled=true") == 1
print("ok desde la Consola")

# ---- 2. sin QGIS en la computadora: instala IngeCAD y explica cómo terminar ---------------
home2, ing2, qg2 = casa(); shutil.rmtree(home2 / ".var/app/org.qgis.qgis")
r = subprocess.run([sys.executable, inst], env={**os.environ, "HOME": str(home2), "PYTHONPATH": ""},
                   capture_output=True, text=True, timeout=120)
assert r.returncode == 0 and (ing2 / "plugins/geocad").exists()
assert "QGIS: no se encontró" in r.stdout and "python3 instalar_geocad_" in r.stdout
print("ok sin QGIS")

# ---- 3. con AP dentro de IngeCAD: también pone la parte de QGIS --------------------------
home3, ing3, qg3 = casa()
os.environ["HOME"] = str(home3); os.environ["XDG_CONFIG_HOME"] = str(home3 / ".var/app/org.ingecad.IngeCAD/config")
from core.plugins import PluginManager, user_plugins_dir
from core import scripting
root = user_plugins_dir(); assert root == ing3 / "plugins"
said = []
class Host:
    document = None
    def __init__(self): self.calls = []; self.command_line = types.SimpleNamespace(echo=said.append)
    def __getattr__(self, n): return lambda *a, **k: self.calls.append(n) or True
host = Host(); host.history = types.SimpleNamespace(_undo=[])
host.plugins = PluginManager(host=host, bundled_dir=home3 / "nada", user_dir=root); host.plugins.discover()
count, err = scripting.run_python(inst, host); assert err is None, err
print("\n".join(said))
assert host.plugins.is_active("geocad")
assert (qg3 / "python/plugins/geocad/plugin.py").exists() and "geocad=true" in (qg3 / "QGIS/QGIS4.ini").read_text()
assert any(t.startswith("QGIS: GeoCAD " + VERSION) for t in said)
print("ok con AP")
print("TODO OK INSTALADOR UNICO")
