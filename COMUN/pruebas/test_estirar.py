"""ESTIRA (STRETCH) para IngeCAD (módulo «Estirar»): el resultado queda en
pantalla al momento (la orden dice qué tocó, la vista no regenera), lo
atrapado entero sigue al cursor como en DESPLAZA y lo que se estira se ve
estirado antes del clic. Con el módulo apagado, el STRETCH de IngeCAD."""
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
from tools.modify import StretchTool

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
est = import_module("ingecad_plugin_geocad.estirar")
dib = import_module("ingecad_plugin_geocad.dibujo")
mods = import_module("ingecad_plugin_geocad.modulos")
T = est.EstirarTool
assert lp.spec.tools.get("GEOSTRETCH") is T and issubclass(T, StretchTool)
assert "estirado" in dib.ESTILO_RESALTADO


def close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class Services:
    def __init__(self, rects): self.rects = rects
    def crossing_rects(self): return self.rects


def armar(rects):
    """El caso de Fernando: un rectángulo largo y un texto; la ventana de
    captura toma el lado derecho del rectángulo y el texto entero."""
    doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
    rect = msp.add_lwpolyline([(0, 0), (20, 0), (20, 2), (0, 2)], close=True)
    texto = msp.add_text("esto es muy largo", dxfattribs={"insert": (15, 3), "height": 1})
    lejos = msp.add_line((-10, -10), (-5, -10))           # sin puntos adentro: no cambia
    msgs, fin = [], []
    ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=msgs.append,
                      finish=lambda: fin.append(1), services=Services(rects))
    t = T(ctx); t.start()
    t.on_selection([rect, texto, lejos])
    return t, hist, rect, texto, lejos, fin


ventana = [(10, -1, 25, 5)]

# ---- 1. clasificar: enteros (se mueven) y estirados -----------------------
t, hist, rect, texto, lejos, fin = armar(ventana)
enteros, estirados = est.clasificar([rect, texto, lejos], ventana)
assert enteros == [texto] and estirados == [rect]
print("ok clasificar")

# ---- 2. vista previa: el fantasma y el rectángulo estirado ----------------
assert t.ghost_entities is None and t.resaltado((5, 5)) == {"estirado": []}   # antes del punto base
t.on_point((20, 1))
assert t.ghost_entities == [texto] and t.ghost_base == (20, 1)              # el texto sigue al cursor
segs = t.resaltado((30, 1))["estirado"]
xs = {round(p[0], 6) for s in segs for p in s}
assert xs == {0.0, 30.0}, xs                                                # estirado hasta el cursor
assert close(rect.get_points("xy")[1], (20, 0))                             # el original no se tocó
assert t.resaltado(None) == {"estirado": []}
print("ok vista previa")

# ---- 3. el clic: la orden dice qué tocó (la vista no regenera) ------------
t.on_point((30, 1))
cmd = hist._undo[-1]
assert isinstance(cmd, est.EstirarCommand) and cmd.targets == [rect, texto, lejos]
assert fin and t.ghost_entities is None
assert [close(p, q) for p, q in zip(rect.get_points("xy"), [(0, 0), (30, 0), (30, 2), (0, 2)])] == [True] * 4
assert close(texto.dxf.insert, (25, 3)) and close(lejos.dxf.start, (-10, -10))
hist.undo()
assert close(rect.get_points("xy")[1], (20, 0)) and close(texto.dxf.insert, (15, 3))
print("ok resultado y deshacer")

# la vista de IngeCAD la reconoce como «actualizable al momento»
try:
    from views.tool_controller import ToolController
except Exception:  # noqa: BLE001 -- sin PySide6: lo demás ya está probado
    ToolController = None
if ToolController is not None:
    from core import modify
    assert ToolController._patchable(cmd)
    assert not ToolController._patchable(modify.StretchCommand([rect], ventana, 1, 0))  # el de IngeCAD, no
    print("ok vista al momento")

# ---- 4. Enter en el segundo punto: el primero es el desplazamiento --------
t, hist, rect, texto, lejos, fin = armar(ventana)
t.on_point((3, 0)); t.on_enter()
assert close(rect.get_points("xy")[1], (23, 0)) and close(texto.dxf.insert, (18, 3))
print("ok Enter")

# ---- 5. elegidos uno por uno: se mueven enteros (como AutoCAD) ------------
t, hist, rect, texto, lejos, fin = armar([])
t.on_point((0, 0))
assert len(t.ghost_entities) == 3 and t.resaltado((1, 1)) == {"estirado": []}
print("ok sin ventana")

# ---- 6. el módulo: S / STRETCH van a GEOSTRETCH sólo si está activo -------
registradas = {"GEOSTRETCH": T}
assert dib.herramienta_para("STRETCH", None, registradas) == "GEOSTRETCH"
mods.poner("ingecad", "estirar", False)
assert dib.herramienta_para("STRETCH", None, registradas) == "STRETCH"
mods.poner("ingecad", "estirar", True)
print("ok módulo")

print("TODO OK ESTIRAR")
