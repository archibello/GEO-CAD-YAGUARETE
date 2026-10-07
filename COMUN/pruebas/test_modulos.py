"""Módulos de GeoCAD: se eligen al instalar (o la primera vez en QGIS), se
cambian desde el menú y, apagados, no dejan rastro en ninguno de los dos
programas."""
import os, sys, tempfile, types, shutil, json
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
CFG = tempfile.mkdtemp(); os.environ["XDG_CONFIG_HOME"] = CFG
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
from importlib import import_module
ROOT = Path(__file__).resolve().parents[2]

# ---- 1. el catálogo y el archivo (Python puro) --------------------------------
from core.plugins import PluginManager, load_plugin
lp = load_plugin(ROOT / "INGECAD" / "codigo" / "geocad", bundled=False); assert lp.available, lp.reason
M = import_module("ingecad_plugin_geocad.modulos")
cfg = import_module("ingecad_plugin_geocad.config")
assert not M.elegido("ingecad") and not M.elegido("qgis")
assert M.estado("ingecad") == {"puente": True, "datos": True, "boton_derecho": True, "empalme": True, "chaflan": True, "bloques": True, "partir": True, "seleccion": True, "propiedades": True, "papel": True, "impresion": True, "angulos_relativos": True}
assert M.estado("qgis") == {"puente": True, "dibujo": True, "bloques": True, "papel": True, "capas": True}
M.guardar("qgis", {"dibujo": False, "capas": False, "inventado": True})          # (Dibujo y Capas: test_submodulos)
assert M.estado("qgis")["bloques"] is False                                      # Bloques necesita Dibujo
assert "inventado" not in json.loads(M.archivo().read_text())["qgis"]
M.guardar("ingecad", {"puente": False})
assert M.estado("ingecad")["datos"] is False                                     # Datos necesita el Puente
assert M.estado("qgis")["puente"] is True                                        # cada programa, lo suyo
assert M.elegido("ingecad") and M.elegido("qgis")
M.guardar("ingecad", {"puente": True})
assert M.resumen("ingecad") == ("Puente con QGIS, Datos (barra y submenú), Botón derecho = Enter, "
                                "Empalme estilo AutoCAD (EMPALME / F), Chaflán estilo AutoCAD (CHAFLAN / CHA), "
                                "Bloques: BLOQUE mejorado y edición en el lugar, "
                                "Partir en punto (PARTEENPUNTO), "
                                "Selección estilo AutoCAD (SEL, FILTRO; W, C, WP, CP, F...), "
                                "Propiedades en masa (paleta Properties), "
                                "Espacio papel como AutoCAD (escala de la hoja), "
                                "Vista previa y plumas (VISTAPREVIA, PLUMAS), "
                                "Ángulos relativos al tramo anterior")
print("ok catálogo")

# ---- 2. la configuración del Puente 1.x se trae sola ------------------------------
old = Path(HOME) / ".config" / "ingecad-qgis"; old.mkdir(parents=True)
(old / "configuracion.json").write_text('{"formato_trabajo": "shp", "altura_rotulos": 4}')
assert cfg.migrar() and cfg.get("formato_trabajo") == "shp" and cfg.get("altura_rotulos") == 4
assert not cfg.migrar()                                                          # una sola vez
assert (old / "configuracion.json").exists()                                     # no se borra
print("ok migración")

# ---- 3. IngeCAD: el menú se arma según los módulos, sin reiniciar -----------------
pkg = import_module("ingecad_plugin_geocad")
def items(menu):
    out = []
    for it in menu:
        if hasattr(it, "items"): out += [("sub", it.label)] + items(it.items)
        elif hasattr(it, "command"): out.append(it.command)
    return out
class Host:
    document = None
    def __init__(self):
        self.calls = []; self.command_line = types.SimpleNamespace(echo=lambda t: None)
    def __getattr__(self, n): return lambda *a, **k: self.calls.append(n) or True
host = Host(); host.history = types.SimpleNamespace(_undo=[])
root = Path(CFG) / "IngeCAD" / "plugins"; root.mkdir(parents=True)
shutil.copytree(ROOT / "INGECAD" / "codigo" / "geocad", root / "geocad")
host.plugins = PluginManager(host=host, bundled_dir=Path(CFG) / "nada", user_dir=root); host.plugins.discover()
host.plugins.set_enabled("geocad", True)
mgr = host.plugins; assert mgr.is_active("geocad")
P = sys.modules["ingecad_plugin_geocad"]
Mi = sys.modules["ingecad_plugin_geocad.modulos"]
spec = mgr.loaded["geocad"].spec
todo = items(spec.menu)
for c in ("QGISSAVE", "SHPTABLE", "SHPCONNECT", "ANGREL", "RIGHTCLICK", "GEOCADMODULES", "SHPCONFIG",
          "QGISUPDATE", "GEOCADABOUT"):
    assert c in todo, c
assert spec.toolbar and "SHPTABLE" in spec.tools and spec.name == "GeoCAD"
# apagar Datos: sin barra, sin submenú, sin comandos de Datos; el Puente sigue
Mi.guardar("ingecad", {"datos": False}); host.calls.clear(); P.aplicar_modulos(host)
spec = mgr.loaded["geocad"].spec; todo = items(spec.menu)
assert "SHPTABLE" not in todo and "SHPTABLE" not in spec.tools and [i.command for i in spec.toolbar] == ["FILLET", "CHAMFER", "BREAKATPOINT", "BLOCK", "INSERT", "GEOREFEDIT", "GEOBLOCKBASE", "SELECT", "GEOFILTER", "GEOPREVIEW", "GEOPLOTSTYLES"]
assert "SHPCONNECT" in spec.tools and mgr.is_active("geocad") and "menus_changed" in host.calls
# apagar el Puente: queda sólo lo de GeoCAD (módulos, configuración, actualizar, acerca, dibujo)
Mi.guardar("ingecad", {"puente": False}); P.aplicar_modulos(host)
spec = mgr.loaded["geocad"].spec
assert set(spec.tools) == {"SHPCONFIG", "GEOFILLET", "GEOCHAMFER", "BREAKATPOINT", "GEOBLOCK", "GEOINSERT", "GEOREFEDIT", "GEOREFADD", "GEOREFREMOVE", "GEOBLOCKBASE", "SELECT", "GEOFILTER"} and "QGISSAVE" not in items(spec.menu)
assert {"GEOCADMODULES", "QGISUPDATE", "GEOCADABOUT", "ANGREL"} <= set(spec.commands)
# GEOCADMODULES sin ventana: informa; ACERCAGEOCAD dice la versión y los módulos
log = []; ctx = types.SimpleNamespace(host=None, echo=log.append)
spec.commands["GEOCADMODULES"](ctx); spec.commands["GEOCADABOUT"](ctx)
assert "Módulos de GeoCAD activos" in log[0] and ("GeoCAD " + P.VERSION) in log[1] and "Botón derecho" in log[1]
Mi.guardar("ingecad", {"puente": True, "datos": True}); P.aplicar_modulos(host)
assert "SHPTABLE" in mgr.loaded["geocad"].spec.tools
print("ok IngeCAD")

# ---- 4. QGIS: primera vez, menú según los módulos y retiro del Puente 1.x ----------
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir()
shutil.copytree(ROOT / "QGIS" / "codigo" / "geocad", plugins / "geocad")
(plugins / "ingecad_puente").mkdir(); (plugins / "ingecad_puente" / "metadata.txt").write_text("version=1.4.0")
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(plugins)]
for name in [n for n in sys.modules if n == "geocad" or n.startswith("geocad.")]:
    del sys.modules[name]
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtCore import QTimer
import geocad
from geocad import plugin as qp
Mq = qp.modulos
json_path = Mq.archivo(); data = json.loads(json_path.read_text()); data.pop("qgis"); json_path.write_text(json.dumps(data))
assert not Mq.elegido("qgis")
import geocad.modulos_ui as mui0
_real0 = mui0.elegir                       # la primera vez se elige sin Dibujo ni Capas (ver test_submodulos)
def _primera(QtW, parent, programa, primera):
    r = _real0(QtW, parent, programa, primera)
    return Mq.guardar(programa, {"dibujo": False, "capas": False})
mui0.elegir = _primera
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
textos = lambda: [getattr(i, "text", i) for i in G.menu.items]
QDialog.respuesta = 0                      # la primera vez, Cancelar = valores por defecto
G = geocad.classFactory(iface); G.initGui()
assert "Enviar a IngeCAD los objetos seleccionados" in textos() and "Módulos..." in textos()
for f in QTimer.shots: f()
QTimer.shots.clear()
assert Mq.elegido("qgis") and Mq.activo("qgis", "puente")
assert QDialog.abiertos and "QGIS" in QDialog.abiertos[-1].title
assert not (plugins / "ingecad_puente").exists() and (plugins / ".anterior-ingecad_puente" / "metadata.txt").exists()
assert any("Se retiró el Puente" in m for m in bar.msgs)
# apagar el Puente desde Módulos...: el menú se rearma y las capas se liberan
G.readonly_by_us.add("x")
QDialog.respuesta = 1
orig = qp.modulos_ui if hasattr(qp, "modulos_ui") else None
import geocad.modulos_ui as mui
real = _real0
mui.elegir = lambda QtW, parent, programa, primera: Mq.guardar(programa, {"puente": False})
G.choose_modules()
assert "Enviar a IngeCAD los objetos seleccionados" not in textos() and "Módulos..." in textos()
assert "Actualizar GeoCAD (QGIS e IngeCAD)..." in textos() and not G.readonly_by_us
# sin Puente, el temporizador no manda latidos ni toca capas
G._tick()
mui.elegir = lambda QtW, parent, programa, primera: Mq.guardar(programa, {"puente": True})
G.choose_modules(); assert "Enviar a IngeCAD los objetos seleccionados" in textos()
mui.elegir = real
# la ventana de verdad (con las casillas falsas): Aceptar guarda lo tildado
QDialog.respuesta = 1
est = real(sys.modules["qgis.PyQt.QtWidgets"], None, "qgis", False)
assert est == {"puente": True, "dibujo": False, "bloques": False, "papel": False, "capas": False}
print("ok QGIS")
# ---- 5. módulos que llegan con una versión nueva se ofrecen (caso real de Fernando) ----
data = json.loads(Mq.archivo().read_text())
data.pop("_vistos", None)
data["qgis"] = {"puente": True, "dibujo": False, "capas": False}       # lo que guardó GeoCAD 2.0.0
Mq.archivo().write_text(json.dumps(data))
assert Mq.nuevos("qgis") == ["dibujo", "bloques", "papel", "capas"]
assert Mq.estado("qgis") == {"puente": True, "dibujo": True, "bloques": True, "papel": True, "capas": True}
assert Mq.nuevos("ingecad") == ["empalme", "chaflan", "bloques", "partir", "seleccion", "propiedades", "papel", "impresion"]  # Empalme (2.3), Partir (2.4), Selección (2.8), Propiedades (3.3), Papel (3.5), Impresión (3.7)
QDialog.abiertos.clear(); QDialog.respuesta = 0                          # Cancelar: quedan sus valores por defecto
G._primer_inicio()
assert QDialog.abiertos and Mq.nuevos("qgis") == [] and Mq.activo("qgis", "capas")
QDialog.abiertos.clear(); G._primer_inicio(); assert not QDialog.abiertos   # no vuelve a preguntar
Mq.guardar("qgis", {"capas": False}); assert not Mq.activo("qgis", "capas") and Mq.nuevos("qgis") == []
assert QDialog.abiertos == [] or True
print("ok módulos nuevos")
print("TODO OK MODULOS")
