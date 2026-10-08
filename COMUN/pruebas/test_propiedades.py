"""3.3.0 Propiedades en masa: con varios objetos del mismo tipo la paleta
Properties de IngeCAD muestra (y cambia en todos) lo propio del tipo; suma
«Atributos» de los bloques y «Totales (GeoCAD)» con largo y área."""
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
P = import_module("ingecad_plugin_geocad.propiedades")
M = import_module("ingecad_plugin_geocad.modulos")

# ------------------------------------------------------------- 1. el módulo
assert any(m.clave == "propiedades" for m in M.catalogo("ingecad")) and M.activo("ingecad", "propiedades")
print("ok módulo")

# ------------------------------------------------------------- 2. cuentas
d = ezdxf.new("R2018"); msp = d.modelspace()
l1 = msp.add_line((0, 0), (3, 4)); l2 = msp.add_line((0, 0), (10, 0))
cuadro = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
abierta = msp.add_lwpolyline([(0, 0), (5, 0)])
circ = msp.add_circle((0, 0), 1)
tx = msp.add_text("A")
t = P.totales([l1, l2, cuadro, abierta, circ, tx])
assert t["n"] == 6 and t["n_largo"] == 5 and abs(t["largo"] - (5 + 10 + 40 + 5 + 2 * 3.141592653589793)) < 1e-6, t
assert t["n_area"] == 2 and abs(t["area"] - (100 + 3.141592653589793)) < 1e-6, t
assert P._num(1234.5) == "1 234,500"
assert P.representante([cuadro, abierta]) is abierta and P.representante([cuadro]) is cuadro
# atributos
b = d.blocks.new("POSTE"); b.add_attdef("NUM", (0, 0)); b.add_attdef("TIPO", (0, 1))
p1 = msp.add_blockref("POSTE", (0, 0)); p1.add_attrib("NUM", "1", (0, 0)); p1.add_attrib("TIPO", "H", (0, 1))
p2 = msp.add_blockref("POSTE", (5, 0)); p2.add_attrib("NUM", "2", (5, 0))
assert P.etiquetas([p1, p2, tx]) == ["NUM", "TIPO"]
assert P.valor_atributo(p1, "TIPO") == "H" and P.valor_atributo(p2, "TIPO") is None
assert P.poner_atributo([p1, p2], "NUM", "P-9") == 2 and P.valor_atributo(p2, "NUM") == "P-9"
print("ok cuentas y atributos")

# ------------------------------------------------------------- 3. la paleta (con una de mentira)
class Row:
    def __init__(self, label, kind, get, apply=None, items=None):
        self.label, self.kind, self.get, self.apply, self.items = label, kind, get, apply, items
hechos = []
pp = types.SimpleNamespace(Row=Row, _TYPE_ROWS={
    "LINE": lambda panel, e: ("Geometry", [Row("Start X", "num", lambda e: e.dxf.start.x)]),
    "LWPOLYLINE": lambda panel, e: ("Geometry", [Row("Area", "ro", None)] if e.closed else [])})
panel = types.SimpleNamespace(window=None, _active=lambda: activos,
                              _in_place=lambda mutate: (mutate(), hechos.append(1)))
original = lambda self, ents: [("General", [Row("Color", "combo", None)])]       # noqa: E731
titulos = lambda secs: [s[0] for s in secs]                                        # noqa: E731
# un solo objeto: como IngeCAD (más nada)
activos = [l1]; assert titulos(P.esquema(panel, activos, original, pp)) == ["General"]
# varias líneas: aparece «Geometry» (lo del tipo) y los totales
activos = [l1, l2]; secs = P.esquema(panel, activos, original, pp)
assert titulos(secs) == ["General", "Geometry", "Totales (GeoCAD Yaguareté)"], titulos(secs)
tot = dict((r.label, r.get(None)) for r in secs[2][1])
assert tot == {"Cantidad": 2, "Largo total (2)": "15,000"}, tot
# polilíneas: «Área» del tipo sólo si todas están cerradas
activos = [cuadro, abierta]; secs = P.esquema(panel, activos, original, pp)
assert secs[1] == ("Geometry", []) and any(r.label.startswith("Área total (1") for r in secs[2][1])
# tipos mezclados: sólo lo general y los totales (como AutoCAD)
activos = [l1, circ]; assert titulos(P.esquema(panel, activos, original, pp)) == ["General", "Totales (GeoCAD Yaguareté)"]
# bloques: «Atributos»; escribir un valor lo cambia en todos los que lo tienen
activos = [p1, p2]; secs = P.esquema(panel, activos, original, pp)
assert titulos(secs) == ["General", "Atributos", "Totales (GeoCAD Yaguareté)"], titulos(secs)
filas = {r.label: r for r in secs[1][1]}
assert list(filas) == ["NUM", "TIPO"] and filas["NUM"].get(p1) == "P-9" and filas["TIPO"].get(p2) is None
filas["NUM"].apply("P-10"); assert hechos and P.valor_atributo(p1, "NUM") == P.valor_atributo(p2, "NUM") == "P-10"
activos = [p1]; assert titulos(P.esquema(panel, activos, original, pp)) == ["General", "Atributos"]
# un constructor que falla no rompe la paleta
pp._TYPE_ROWS["CIRCLE"] = lambda panel, e: 1 / 0
activos = [circ, circ]; assert titulos(P.esquema(panel, activos, original, pp)) == ["General", "Totales (GeoCAD Yaguareté)"]
# módulo apagado: la paleta como venía
M.guardar("ingecad", {"propiedades": False})
activos = [l1, l2]; assert titulos(P.esquema(panel, activos, original, pp)) == ["General"]
M.guardar("ingecad", {"propiedades": True})
print("ok paleta")

# ------------------------------------------------------------- 4. coma decimal
class Editor:
    def __init__(self, t): self.t = t
    def text(self): return self.t
    def setText(self, t): self.t = t
vistos = []
envuelto = P._envolver_edit_text(lambda self, row, ed: vistos.append(ed.text()))
envuelto(types.SimpleNamespace(window=None), Row("Radio", "num", None, lambda v: None), Editor("2,5"))
envuelto(types.SimpleNamespace(window=None), Row("Texto", "str", None), Editor("a,b"))
assert vistos == ["2.5", "a,b"], vistos
# ------------------------------------------------------------- 5. operaciones (3.3.1)
assert P.expresion("h*0.9") == "h*0.9" and P.expresion("*0,9") == "h*0.9" and P.expresion("/1.1") == "h/1.1"
assert P.expresion("H/1,1") == "H/1.1" and P.expresion("+2") == "h+2" and P.expresion("(x+1)*2") == "(x+1)*2"
assert P.expresion("2,5") is None and P.expresion("-3") is None                 # números: como siempre
for malo in ("hola", "h**2", "__import__('os')", "h*", "h/0", "y*2"):
    assert P.expresion(malo) is None, malo
assert abs(P.evaluar("h/1.1", 2.2) - 2.0) < 1e-12 and P.evaluar("-h+1", 3) == -2
# cada objeto con SU valor, con el «apply» de la fila (de a uno)
a1 = msp.add_text("a", dxfattribs={"height": 1.0}); a2 = msp.add_text("b", dxfattribs={"height": 2.0})
pan = types.SimpleNamespace(window=None, _active=lambda: [a1, a2])
fila = Row("Height", "num", lambda e: e.dxf.height, lambda v: pan._set_prop("height", v))
assert P.aplicar_expresion(pan, fila, "h*0.5") == 2 and (a1.dxf.height, a2.dxf.height) == (0.5, 1.0)
assert set(vars(pan)) == {"window", "_active"} and pan._active() == [a1, a2]     # la paleta queda como estaba
c1 = msp.add_circle((0, 0), 1); c2 = msp.add_circle((0, 0), 3)
pan._active = lambda: [c1, c2]
diam = Row("Diameter", "num", lambda e: e.dxf.radius * 2, lambda v: pan._set_prop("radius", v / 2))
assert P.aplicar_expresion(pan, diam, P.expresion("+2")) == 2 and (c1.dxf.radius, c2.dxf.radius) == (2.0, 4.0)
# ------------------------------------------------------------- 6. color: quitar el RGB (3.3.2)
from core.actions import SetPropertyCommand
from core.commands import History
from core.document import Document
estilo = import_module("ingecad_plugin_geocad.estilo")
assert hasattr(SetPropertyCommand.do, "_puente_original")
doc = Document(ezdxf.new("R2018")); hist = History(doc); m2 = doc.doc.modelspace()
parcela = m2.add_lwpolyline([(0, 0), (10, 0), (10, 10)], close=True, dxfattribs={"color": 30, "true_color": 0xA0522D})
otra = m2.add_lwpolyline([(0, 0), (5, 0)], dxfattribs={"color": 3})
assert estilo.hex_of_entity(parcela) == "#a0522d"                       # llegó de QGIS en marrón
hist.execute(SetPropertyCommand([parcela, otra], "color", 1))
assert parcela.dxf.color == 1 and not parcela.dxf.hasattr("true_color") and otra.dxf.color == 1
assert estilo.hex_of_entity(parcela) == "#ff0000"                       # y así vuelve a QGIS
hist.undo()
assert parcela.dxf.color == 30 and parcela.dxf.true_color == 0xA0522D and otra.dxf.color == 3
hist.redo(); assert not parcela.dxf.hasattr("true_color"); hist.undo()
hist.execute(SetPropertyCommand([parcela], "color", 256))               # PorCapa: también sin RGB
assert not parcela.dxf.hasattr("true_color"); hist.undo()
hist.execute(SetPropertyCommand([parcela], "layer", "0"))               # otra propiedad: el RGB queda
assert parcela.dxf.true_color == 0xA0522D; hist.undo()
M.guardar("ingecad", {"propiedades": False})                              # módulo apagado: como IngeCAD
hist.execute(SetPropertyCommand([parcela], "color", 1)); assert parcela.dxf.true_color == 0xA0522D
hist.undo(); M.guardar("ingecad", {"propiedades": True})
print("ok color")

# ---- 3.11.0: el formato del texto en la paleta Properties ----------------------------------
import importlib.util as _iu
ET = import_module("ingecad_plugin_geocad.editor_texto")
_src = Path(_iu.find_spec("views").submodule_search_locations[0], "mtext_editor.py").read_text()
_nombres = ET.controles()
assert len(_nombres) == len(set(_nombres)) == 15
for _n in _nombres:                         # los controles existen en el editor de IngeCAD
    assert f"self.{_n} = " in _src, _n
for _m in ET.ENVOLTORIOS:                   # y los métodos que se envuelven
    assert f"def {_m}(self" in _src, _m
assert "self._bar = QWidget(self)" in _src and "self._bar.sizeHint()" in _src
assert ET.en_recuadro(types.SimpleNamespace(_geocad_formato=None), object()) is False
print("ok formato del texto en la paleta")

# ---- 3.11.1: un clic en las ventanas del editor («Discard...?», Máscara...) no lo cierra ----
_ed = types.SimpleNamespace(_geocad_formato=None)
class _W:
    def __init__(self, padre=None): self._p = padre
    def parentWidget(self): return self._p
_caja = _W(); _ed._geocad_formato = _caja
_box = _W(_W(_ed))                          # botón del cuadro de pregunta, hijo del editor
assert ET.depende_del_editor(_ed, _box) and ET.depende_del_editor(_ed, _W(_caja))
assert not ET.depende_del_editor(_ed, _W(_W()))
assert "clic_no_cierra(self, obj)" in Path(ET.__file__).read_text(encoding="utf-8")
assert "QMessageBox.question(\n                self," in _src or "QMessageBox.question(" in _src
print("ok ventanas del editor")
print("TODO OK PROPIEDADES")
