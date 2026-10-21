"""IGUALARPROP (MATCHPROP / MA) para IngeCAD (módulo «Igualar propiedades»):
el origen (clic y Enter, como AutoCAD) queda resaltado con su propio color y
más grueso hasta el final;
los destinos se eligen con todas las opciones de «Designar objetos» (W C WP
CP F ALL L P R U FI) y cada paso se ve en el momento con las propiedades
nuevas; R y U los devuelven a como estaban. Apagado, el MATCHPROP de IngeCAD."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from tools.base import ToolContext
from tools.modify import MatchPropTool

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
ig = import_module("ingecad_plugin_geocad.igualar")
sel = import_module("ingecad_plugin_geocad.seleccion")
dib = import_module("ingecad_plugin_geocad.dibujo")
mods = import_module("ingecad_plugin_geocad.modulos")
yag = import_module("ingecad_plugin_geocad.yaguarete")
tex = import_module("ingecad_plugin_geocad.texto")
T = ig.IgualarTool

# ------------------------------------------------------------- 1. el módulo
m = next(m for m in mods.catalogo("ingecad") if m.clave == "igualar")
assert m.requiere == "seleccion" and m.defecto
assert lp.spec.tools.get("GEOMATCHPROP") is T and issubclass(T, MatchPropTool)
registradas = {"GEOMATCHPROP": T}
assert dib.herramienta_para("MATCHPROP", None, registradas) == "GEOMATCHPROP"
assert dib.herramienta_para("ma", None, registradas) == "ma"          # el alias lo resuelve IngeCAD
mods.poner("ingecad", "igualar", False)
assert dib.herramienta_para("MATCHPROP", None, registradas) == "MATCHPROP"
mods.poner("ingecad", "igualar", True)
mods.poner("ingecad", "seleccion", False)                            # sin Selección no hay igualar
assert not mods.estado("ingecad")["igualar"]
mods.poner("ingecad", "seleccion", True)
assert ("MATCHPROP", "igualar", "standard_toolbar") in yag.HERRAMIENTAS
assert "MATCHPROP" in yag.DESCRIPCIONES
print("ok módulo")

# ------------------------------------------------------------- 2. el color del origen
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
doc.doc.layers.add("ROJA", color=1)
doc.doc.layers.add("VERDE_RGB", true_color=ezdxf.rgb2int((10, 200, 30)))
origen = msp.add_line((0, 20), (10, 20), dxfattribs={"layer": "ROJA", "lineweight": 50})
assert ig.color_rgb(origen, doc) == (255, 0, 0)                         # PorCapa: el de la capa
assert ig.color_rgb(msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "VERDE_RGB"}), doc) == (10, 200, 30)
assert ig.color_rgb(msp.add_line((0, 0), (1, 0), dxfattribs={"color": 5}), doc) == (0, 0, 255)
assert ig.color_rgb(msp.add_line((0, 0), (1, 0), dxfattribs={"color": 7}), doc) is None
assert ig.color_rgb(msp.add_line((0, 0), (1, 0), dxfattribs={"color": 0}), doc) is None   # PorBloque
c1 = msp.add_line((0, 0), (1, 0), dxfattribs={"color": 3}); c1.rgb = (1, 2, 3)
assert ig.color_rgb(c1, doc) == (1, 2, 3)                               # color verdadero manda
for e in list(msp)[1:]:
    msp.delete_entity(e)
print("ok color")

# ------------------------------------------------------------- 3. la orden
a = msp.add_line((0, 0), (4, 0), dxfattribs={"color": 3})
b = msp.add_line((0, 2), (4, 2), dxfattribs={"color": 3})
c = msp.add_circle((30, 0), 1, dxfattribs={"color": 3})
t = msp.add_text("T", dxfattribs={"insert": (50, 0), "height": 1, "color": 3})
destinos = (a, b, c, t)


def antes(e):
    return (e.dxf.layer, e.dxf.get("color", 256), e.dxf.get("lineweight", -1))


ORIG, IGUAL = ("0", 3, -1), ("ROJA", 256, 50)


class Senal:
    def __init__(self): self.n = 0
    def emit(self): self.n += 1


class Linea:
    def __init__(self): self.msgs = []
    def echo(self, t): self.msgs.append(t)


class Ctrl:
    """Lo que la orden y el módulo Selección usan del ToolController."""
    def __init__(self, document):
        self.window = types.SimpleNamespace(document=document, command_line=Linea())
        self.index = GeometryIndex(document)
        self.selection = set()
        self._selecting_for = None
        self._window_anchor = None
        self.changed = Senal()
        self.lastpoint = (0.0, 0.0)
        self.space_vp = None
        self._pick_tolerance = 0.2
        self.tool = None
    def _with_groups(self, handles): return set(handles)
    def to_space(self, x, y): return (x, y)
    def pick_entity(self, p):
        h = self.index.pick(tuple(p), self._pick_tolerance)
        return self.index.entity(h) if h else None
    def request_selection(self): self._selecting_for = self.tool
    def finish(self): self.tool = None; self._selecting_for = None; self.selection = set()
    def execute(self, cmd):
        hist.execute(cmd)
        self.index = GeometryIndex(self.window.document)    # como el parche de la vista


def arrancar(ctrl):
    ctx = ToolContext(execute=ctrl.execute, prompt=lambda s: ctrl.window.command_line.echo(s),
                      echo=ctrl.window.command_line.echo, finish=ctrl.finish, services=ctrl)
    ctrl.tool = T(ctx); ctrl.tool.start()
    return ctrl.tool


k = Ctrl(doc)
tool = arrancar(k)
assert k._selecting_for is None and tool._source is None
r = tool.resaltado((2, 20))                                    # antes del clic: lo que tomaría
assert r.get("cursor"), r
tool.on_point((2, 0))                                          # primero otro objeto...
assert tool._source is a and k._selecting_for is None          # ...todavía no pide destinos
assert antes(a) == ORIG
tool.on_point((5, 20))                                         # otro clic cambia el origen
assert tool._source is origen and k._selecting_for is None
assert tool.resaltado(None)["propio"][0][0] == (255, 0, 0)     # ya resaltado, antes del Enter
assert "Enter confirma" in k.window.command_line.msgs[-1]
tool.on_enter()                                                # Enter: confirma el origen
assert k._selecting_for is tool                                # ahora pide los destinos
tool.on_enter()                                                # otro Enter acá no rompe nada
assert k._selecting_for is tool
r = tool.resaltado(None)
(rgb, segs), = r["propio"]
assert rgb == (255, 0, 0) and segs == [((0.0, 20.0), (10.0, 20.0))], r   # su color, su trazo


def escribir(*textos):
    for x in textos:
        assert sel.on_text(k, x) is True, x


escribir("W", "-1,-1", "5,3")                                  # ventana: a y b, al momento
assert antes(a) == IGUAL and antes(b) == IGUAL and antes(c) == ORIG, (antes(a), antes(c))
assert any("igualados" in x for x in k.window.command_line.msgs)
assert k.window.command_line.msgs[-1].startswith("Designar objetos de destino")
escribir("U")                                                  # U: vuelven a como estaban
assert antes(a) == ORIG and antes(b) == ORIG
escribir("ALL")                                                # todo, menos el origen
assert all(antes(e) == IGUAL for e in destinos)
assert antes(origen) == IGUAL and origen.dxf.handle not in tool._pintados
escribir("R", "L")                                             # R + último: el texto vuelve
assert antes(t) == ORIG and antes(c) == IGUAL
escribir("A", "CP", "28,-2", "32,-2", "32,2", "")              # ya igualado: nada cambia
assert antes(c) == IGUAL
escribir("F", "49,0.5", "52,0.5", "")                          # borde sobre el texto
assert antes(t) == IGUAL
r = tool.resaltado(None)
assert r["propio"][0][0] == (255, 0, 0)                        # el origen sigue resaltado
# Enter: IngeCAD termina la selección y la orden
assert sel.on_text(k, "") is False
tool.on_selection([k.index.entity(h) for h in k.selection])
assert k.tool is None and k._selecting_for is None
assert any("Igualar propiedades:" in x for x in k.window.command_line.msgs)
assert all(antes(e) == IGUAL for e in destinos)
# deshacer todo, paso por paso, deja el dibujo como estaba
while hist.undo() is not None:
    pass
assert all(antes(e) == ORIG for e in destinos), [antes(e) for e in destinos]
assert antes(origen) == IGUAL
while hist.redo() is not None:
    pass
assert all(antes(e) == IGUAL for e in destinos)
while hist.undo() is not None:
    pass
print("ok orden")

# ------------------------------------------------------------- 4. preselección
k = Ctrl(doc)
k.selection = {origen.dxf.handle}
tool = arrancar(k)
assert tool._source is origen and k._selecting_for is tool and k.selection == set()
k.selection = {a.dxf.handle}; sel.avisar(k)                    # un clic nativo
assert antes(a) == IGUAL
k.selection = set(); sel.avisar(k)                             # Mayús + clic lo quita
assert antes(a) == ORIG
k2 = Ctrl(doc); k2.selection = {a.dxf.handle, b.dxf.handle}   # varios: ninguno es origen
tool2 = arrancar(k2)
assert tool2._source is None and k2.selection == set()
k3 = Ctrl(doc); tool3 = arrancar(k3)
tool3.on_enter()                                               # Enter sin origen: termina
assert k3.tool is None
print("ok preselección")

# ------------------------------------------------------------- 5. envoltorios
class CtrlFalso(Ctrl):
    def _selection_click(self, wx, wy, shift):
        self.selection = self.selection | {a.dxf.handle}
    def highlight_geometry(self): return ("nativo", (), ())


dib.envolver(CtrlFalso, "_selection_click", sel._envolver_selection_click, reemplazar=True)
dib.envolver(CtrlFalso, "highlight_geometry", tex._envolver_resaltado, reemplazar=True)
k = CtrlFalso(doc)
assert k.highlight_geometry()[0] == "nativo"                   # sin la orden: como venía
tool = arrancar(k); tool.on_point((5, 20)); tool.on_enter()
vacio = k.highlight_geometry()
assert len(vacio) == 3 and all(len(x) == 0 for x in vacio)     # lo elegido no se resalta
k._selection_click(1, 0, False)                                # el clic avisa a la orden
assert antes(a) == IGUAL
tool.on_selection([])
while hist.undo() is not None:
    pass
print("ok envoltorios")

# ------------------------------------------------------------- 6. el dibujo del resaltado
class Pintor:
    def __init__(self): self.lineas, self.plumas = 0, []
    def save(self): pass
    def restore(self): pass
    def setPen(self, p): self.plumas.append(p)
    def drawLine(self, a, b): self.lineas += 1
    def drawText(self, p, t): pass


pluma = lambda color, ancho, estilo: (color, ancho)
qt = (pluma, lambda *a: tuple(a), lambda x, y: (x, y), types.SimpleNamespace(DashLine=1, SolidLine=0))
for claro, esperado in ((True, (0, 0, 0, 255)), (False, (255, 255, 255, 255))):
    herramienta = types.SimpleNamespace(resaltado=lambda cur: {"propio": [(None, [((0, 0), (1, 0))])]})
    vista = types.SimpleNamespace(
        tool_delegate=types.SimpleNamespace(tool=herramienta, _cursor=None, _selecting_for=None),
        _space_to_screen=lambda x, y: (x, y), _light_background=lambda c=claro: c)
    p = Pintor()
    assert dib.dibujar_resaltado(vista, p, qt=qt) == 1
    assert p.plumas[0] == (esperado, dib.ANCHO_PROPIO), p.plumas      # color 7 según el fondo
print("ok dibujo")

print("TODO OK IGUALAR")
