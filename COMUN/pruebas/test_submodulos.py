"""Dibujo CAD (con Bloques y Papel) y Capas CAD dentro de GeoCAD en QGIS:
mismos ángulos que el núcleo, submenús en GeoCAD, se encuentran entre sí con
sus nombres de siempre, se prenden y apagan sin rastro y retiran los
complementos sueltos de antes."""
import os, sys, tempfile, types, shutil, json, math, compileall
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

# ---- 0. todo el complemento compila ---------------------------------------------------
assert compileall.compile_dir(str(ROOT / "QGIS" / "codigo" / "geocad"), quiet=1, force=True)

plugins_dir = Path(tempfile.mkdtemp()) / "plugins"; plugins_dir.mkdir()
shutil.copytree(ROOT / "QGIS" / "codigo" / "geocad", plugins_dir / "geocad",
                ignore=shutil.ignore_patterns("__pycache__"))
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(plugins_dir)]
import qgis.utils
from geocad import angulos, modulos, submodulos
from geocad.dibujo import units

# ---- 1. el núcleo y Dibujo CAD entienden los ángulos igual ---------------------------
U = units.Units()                       # grados decimales, antihorario, 0 = este, REL interior
def dibujo(texto, ref):
    r = units.parse_angle(texto, U, None if ref is None else math.radians(ref), relative=True)
    return math.degrees(r) % 360.0
casos = ["90", "180", "270", "45.5", "45d30'15\"", "<45", "30dI", "30dD", "N45dE", "S30dW",
         "N", "E", "100g", "0.5r", "-30", "359d59'59\""]
for ref in (None, 0.0, 33.0, 271.5):
    for t in casos:
        if ref is None and t.endswith(("dI", "dD")):
            continue
        a = angulos.direccion(t, ref) % 360.0
        b = dibujo(t, ref)
        assert abs((a - b + 180) % 360 - 180) < 1e-9, (t, ref, a, b)
print("ok ángulos iguales en el núcleo y en Dibujo CAD")

# ---- 2. catálogo: Bloques y Papel dependen de Dibujo ----------------------------------
assert modulos.estado("qgis") == {"puente": True, "dibujo": True, "bloques": True, "papel": True,
                                  "capas": True}
modulos.guardar("qgis", {"dibujo": False})
e = modulos.estado("qgis"); assert not e["bloques"] and not e["papel"] and e["capas"]
modulos.guardar("qgis", {"dibujo": True})
print("ok catálogo")

# ---- 3. el cargador, con submódulos de mentira ----------------------------------------
creados = []
class FakeSub:
    def __init__(self, iface): self.iface = iface; self.descargado = False; creados.append(self)
    def initGui(self):
        a = types.SimpleNamespace(text=f"acción de {type(self).__name__}")
        self.iface.addPluginToMenu("&" + self.MENU, a)
        self.accion = a
        # se encuentran entre sí por el nombre de siempre
        self.vio_dibujo = qgis.utils.plugins.get("Dibujo_CAD") is not None
    def unload(self):
        self.iface.removePluginMenu("&" + self.MENU, self.accion); self.descargado = True
class DibujoCADPlugin(FakeSub): MENU = "Dibujo CAD"
class LayerPropertiesPlugin(FakeSub): MENU = "Capas CAD"
class Rompe(FakeSub):
    MENU = "x"
    def initGui(self): raise RuntimeError("se rompió")
def fabrica(base, sub, iface):
    return {"DibujoCADPlugin": DibujoCADPlugin, "LayerPropertiesPlugin": LayerPropertiesPlugin}[sub.clase](iface)

# complementos sueltos de antes, instalados y cargados
for viejo in ("Dibujo_CAD", "Layer_Properties"):
    (plugins_dir / viejo).mkdir(); (plugins_dir / viejo / "metadata.txt").write_text("version=1")
    qgis.utils.plugins[viejo] = object()
cambios = []
iface = types.SimpleNamespace(mainWindow=lambda: None, addToolBar=lambda n: n)
C = submodulos.Cargador(iface, "geocad", plugins_dir, al_cambiar=lambda: cambios.append(1), fabrica=fabrica)
C.cargar(modulos.estado("qgis"))
assert set(C.activos) == {"dibujo", "capas"}
assert isinstance(qgis.utils.plugins["Dibujo_CAD"], DibujoCADPlugin)
assert isinstance(qgis.utils.plugins["Layer_Properties"], LayerPropertiesPlugin)
assert C.activos["capas"][0].vio_dibujo                       # Capas encuentra a Dibujo
assert qgis.utils.descargados == ["Dibujo_CAD", "Layer_Properties"]
assert not (plugins_dir / "Dibujo_CAD").exists() and (plugins_dir / ".anterior-Dibujo_CAD" / "metadata.txt").exists()
assert (plugins_dir / ".anterior-Layer_Properties").exists()
avisos = C.tomar_avisos(); assert len(avisos) == 2 and "Se retiró el complemento Dibujo_CAD" in avisos[0]
assert [t for t, _ in C.menus()] == ["Dibujo CAD", "Capas CAD"]
assert C.menus()[0][1][0].text == "acción de DibujoCADPlugin"
assert C.activos["dibujo"][1].mainWindow() is None            # el resto del iface pasa tal cual
# volver a cargar no duplica nada
C.cargar(modulos.estado("qgis")); assert len(creados) == 2
# apagar Capas: se descarga, sale del registro y del menú; Dibujo sigue
C.descargar({"capas"})
assert creados[1].descargado and "Layer_Properties" not in qgis.utils.plugins
assert [t for t, _ in C.menus()] == ["Dibujo CAD"] and "Dibujo_CAD" in qgis.utils.plugins
C.descargar()
assert creados[0].descargado and "Dibujo_CAD" not in qgis.utils.plugins and C.menus() == []
# un submódulo que falla al iniciar no rompe GeoCAD: avisa y queda fuera
C2 = submodulos.Cargador(iface, "geocad", plugins_dir, fabrica=lambda b, s, i: Rompe(i))
C2.cargar({"dibujo": True, "capas": False})
assert not C2.activos and "No se pudo iniciar Dibujo CAD" in C2.tomar_avisos()[0]
assert "Dibujo_CAD" not in qgis.utils.plugins
print("ok cargador")

# ---- 4. dentro del menú GeoCAD de QGIS --------------------------------------------------
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QDialog
from geocad import plugin as qp
modulos.guardar("qgis", {"puente": True, "dibujo": True, "capas": True})
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
creados.clear()
G = qp.GeoCAD(iface); G.initGui(); G.subs.fabrica = fabrica
for f in QTimer.shots: f()
QTimer.shots.clear()
titulos = lambda: [i.title for i in G.menu.items if isinstance(getattr(i, "title", None), str)]
assert titulos() == ["Dibujo CAD", "Capas CAD"]
sub_dibujo = [i for i in G.menu.items if isinstance(getattr(i, "title", None), str) and i.title == "Dibujo CAD"][0]
assert [a.text for a in sub_dibujo.items] == ["acción de DibujoCADPlugin"]
# apagar Dibujo desde Módulos...: se descarga (con Bloques y Papel) y sale del menú
import geocad.modulos_ui as mui
mui.elegir = lambda QtW, parent, programa, primera: modulos.guardar(programa, {"dibujo": False})
G.choose_modules()
assert titulos() == ["Capas CAD"] and "Dibujo_CAD" not in qgis.utils.plugins
assert creados[0].descargado and creados[1].descargado and len(creados) == 3   # Capas se reinicia
mui.elegir = lambda QtW, parent, programa, primera: modulos.guardar(programa, {"dibujo": True})
G.choose_modules(); assert titulos() == ["Dibujo CAD", "Capas CAD"]
G.unload()
assert "Dibujo_CAD" not in qgis.utils.plugins and "Layer_Properties" not in qgis.utils.plugins
print("ok menú GeoCAD")
print("TODO OK SUBMODULOS")
