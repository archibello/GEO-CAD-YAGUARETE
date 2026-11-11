"""Manual de usuario en GitHub (3.76.0): en el menú GeoCAD Yaguareté de cada
programa, un ítem que abre su capítulo (QGIS -> capítulo 1, IngeCAD ->
capítulo 2) y, en el submenú Google Earth, el capítulo 3."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import json, os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
from core.plugins import load_plugin

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "COMUN" / "nucleo"))
import nombre

# ------------------------------------------------------------- 1. las direcciones
assert nombre.url_manual("qgis").endswith("/blob/main/manual/02_qgis.md")
assert nombre.url_manual("ingecad").endswith("/blob/main/manual/03_ingecad.md")
assert nombre.url_manual("googleearth").endswith("/blob/main/manual/04_google_earth.md")
assert nombre.url_manual("").endswith("/blob/main/manual/README.md")
assert nombre.url_manual("qgis").startswith(nombre.REPOSITORIO + "/")
for clave, (archivo, titulo) in nombre.CAPITULOS.items():
    assert (RAIZ / "manual" / archivo).is_file(), archivo        # el capítulo existe
    primera = (RAIZ / "manual" / archivo).read_text("utf-8").splitlines()[0]
    assert titulo.split("—")[1].strip() in primera, (titulo, primera)
assert (RAIZ / "manual" / "README.md").is_file()

# ------------------------------------------------------------- 2. abrir: Qt, y si no, webbrowser
abiertas = []
url, ok = nombre.abrir_manual("qgis", lambda u: abiertas.append(u) or True)
assert ok and abiertas == [nombre.url_manual("qgis")] and url == abiertas[0]
import webbrowser
webbrowser.open = lambda u: abiertas.append("wb:" + u) or True
url, ok = nombre.abrir_manual("ingecad", lambda u: False)        # Qt no pudo
assert ok and abiertas[-1] == "wb:" + nombre.url_manual("ingecad")
url, ok = nombre.abrir_manual("googleearth", lambda u: 1 / 0)    # Qt falló
assert ok and abiertas[-1] == "wb:" + nombre.url_manual("googleearth")
webbrowser.open = lambda u: False
url, ok = nombre.abrir_manual("ingecad", None)
assert not ok and url == nombre.url_manual("ingecad")            # se escribe la dirección

# ------------------------------------------------------------- 3. IngeCAD: órdenes, menú y español
lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
mods = import_module("ingecad_plugin_geocad.modulos")
plugin = import_module("ingecad_plugin_geocad")
mods.poner("ingecad", "googleearth", True)
spec = plugin.construir_spec()
assert spec.commands["GEOCADMANUAL"] is plugin.cmd_manual
assert spec.commands["GEOEARTHMANUAL"] is plugin.cmd_manual_ge
raiz = [getattr(i, "command", "") for i in spec.menu]
assert raiz.index("GEOCADMANUAL") == raiz.index("GEOCADABOUT") - 1   # justo antes de Acerca de
ge = next(s for s in spec.menu if getattr(s, "label", "") == "Google Earth")
assert [getattr(i, "command", "") for i in ge.items][-1] == "GEOEARTHMANUAL"
mods.poner("ingecad", "googleearth", False)
spec = plugin.construir_spec()
assert "GEOCADMANUAL" in [getattr(i, "command", "") for i in spec.menu]   # el manual, siempre
assert not any(getattr(s, "label", "") == "Google Earth" for s in spec.menu)
carpeta = Path(plugin.__file__).parent / "i18n" / "es"
ui = json.loads((carpeta / "ui.json").read_text("utf-8"))
assert ui["User manual (IngeCAD)..."] == "Manual de usuario (IngeCAD)..."
assert ui["Google Earth manual (chapter 3)..."] == "Manual de Google Earth (capítulo 3)..."
cmds = json.loads((carpeta / "commands.json").read_text("utf-8"))
assert cmds["GEOCADMANUAL"]["name"] == "MANUALGEOCAD" and cmds["GEOEARTHMANUAL"]["name"] == "MANUALGE"

ecos = []
ctx = types.SimpleNamespace(echo=ecos.append)
webbrowser.open = lambda u: True
plugin._abrir_url = lambda u: False                               # sin Qt: webbrowser
plugin.cmd_manual(ctx)
assert ecos[-1] == "Manual de usuario, Capítulo 2 — GeoCAD en IngeCAD: " + nombre.url_manual("ingecad")
webbrowser.open = lambda u: False
plugin.cmd_manual_ge(ctx)
assert ecos[-1].startswith("No se pudo abrir el navegador.") and ecos[-1].endswith(nombre.url_manual("googleearth"))

# ------------------------------------------------------------- 4. QGIS: los ítems en el menú
qg = (RAIZ / "QGIS" / "codigo" / "geocad" / "plugin.py").read_text("utf-8")
assert 'add("manual", "Manual de usuario (QGIS)...", lambda: self.open_manual("qgis"))' in qg
assert qg.index('add("manual"') < qg.index('add("about"')
assert '"Manual de Google Earth (capítulo 3)..."' in qg and 'self.open_manual("googleearth")' in qg
assert "nombre.abrir_manual(clave" in qg
# el núcleo, igual en los dos lados
for lado in ("QGIS", "INGECAD"):
    assert (RAIZ / lado / "codigo" / "geocad" / "nombre.py").read_text("utf-8") == \
        (RAIZ / "COMUN" / "nucleo" / "nombre.py").read_text("utf-8"), lado
print("TODO OK")
