"""Color de capa en IngeCAD (3.96.2, retoque fijo de capas.py). Una capa con
color exacto (RGB, como las que trae PEGARENLUGAR desde QGIS o las de AutoCAD)
se seguía viendo con ese RGB aunque en el panel Layers (o -CAPA Color) se le
eligiera otro color: IngeCAD cambiaba sólo el número (ACI). Ahora, como en
AutoCAD, elegir un color quita el RGB; U lo devuelve y rehacer lo vuelve a
quitar. Otras propiedades y las capas sin RGB, como siempre."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from ezdxf.colors import rgb2int
from ezdxf.addons.drawing.properties import RenderContext
from core.commands import History
from core.document import Document
from core.layers import LayerPropertyCommand
from core.plugins import load_plugin

ROOT = Path(__file__).resolve().parents[2]
lp = load_plugin(ROOT / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
capas = import_module("ingecad_plugin_geocad.capas")
assert capas.instalar_color()
assert capas.instalar_color()                          # dos veces: un solo envoltorio
assert getattr(LayerPropertyCommand.do, "_puente_fabrica", None).__name__ == "_envolver_color_do"
assert getattr(LayerPropertyCommand.do._puente_original, "_puente_fabrica", None) is None

GRIS = rgb2int((0x7d, 0x8b, 0x8f))                     # «Nueva capa borrador» de QGIS
doc = ezdxf.new("R2018")
document = Document(doc)
h = History(document)
lay = doc.layers.add("Nueva capa borrador", color=7)
lay.dxf.true_color = GRIS
e = doc.modelspace().add_lwpolyline([(0, 0), (1, 0), (1, 1)], close=True,
                                    dxfattribs={"layer": "Nueva capa borrador"})


def se_ve():
    return RenderContext(doc).resolve_color(e)


assert se_ve() == "#7d8b8f"

# ---- 1. elegir el color 160: se ve 160 --------------------------------------------------------
h.execute(LayerPropertyCommand("Nueva capa borrador", "color", 160))
assert lay.dxf.color == 160 and not lay.dxf.hasattr("true_color")
from ezdxf.colors import aci2rgb
assert se_ve() == "#%02x%02x%02x" % tuple(aci2rgb(160)), se_ve()
print("ok el color elegido reemplaza al RGB")

# ---- 2. U devuelve el RGB, rehacer lo vuelve a quitar ----------------------------------------
h.undo()
assert lay.dxf.color == 7 and lay.dxf.true_color == GRIS and se_ve() == "#7d8b8f"
h.redo()
assert lay.dxf.color == 160 and not lay.dxf.hasattr("true_color")
h.undo()
assert lay.dxf.true_color == GRIS
print("ok U devuelve el RGB; rehacer lo quita")

# ---- 3. apagada: el número negativo se respeta; otras propiedades no tocan el RGB -----------
lay.off()
h.execute(LayerPropertyCommand("Nueva capa borrador", "linetype", "DASHED")
          if "DASHED" in doc.linetypes else LayerPropertyCommand("Nueva capa borrador", "locked", True))
assert lay.dxf.true_color == GRIS
h.execute(LayerPropertyCommand("Nueva capa borrador", "color", 1))
assert lay.dxf.color == -1 and not lay.dxf.hasattr("true_color") and not lay.is_on()
print("ok otras propiedades no tocan el RGB; apagada sigue apagada")

# ---- 4. una capa sin RGB, como siempre ----------------------------------------------------------
b = doc.layers.add("muros", color=3)
h.execute(LayerPropertyCommand("muros", "color", 5))
assert b.dxf.color == 5 and not b.dxf.hasattr("true_color")
h.undo()
assert b.dxf.color == 3 and not b.dxf.hasattr("true_color")
print("ok capa sin RGB: igual que antes")
print("TODO OK")
