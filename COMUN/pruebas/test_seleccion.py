"""Selección estilo AutoCAD para IngeCAD (módulo «Selección»): W, C, WP, CP,
F, ALL, L, P, R, A, U (y en español V, PV, PC, B, TODO, UL, E, H) escritos en
cualquier «Select objects»; la orden SEL; la línea de comandos sin
autocompletar; la vista previa de la ventana, el polígono y el borde."""
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
sel = import_module("ingecad_plugin_geocad.seleccion")
dib = import_module("ingecad_plugin_geocad.dibujo")
mods = import_module("ingecad_plugin_geocad.modulos")
geo = import_module("ingecad_plugin_geocad")


# ------------------------------------------------------------- 1. el módulo
assert any(m.clave == "seleccion" for m in mods.catalogo("ingecad"))
assert mods.activo("ingecad", "seleccion")                       # prendido por defecto
spec = lp.spec
assert tuple(int(x) for x in spec.version.split(".")[:2]) >= (2, 8), spec.version
assert spec.tools.get("SELECT") is sel.SelTool
assert spec.aliases.get("SEL") == "SELECT"
assert any(getattr(i, "command", "") == "SELECT" for i in spec.toolbar)
print("ok módulo")

# ------------------------------------------------------------- 2. opciones
for escrito, op in [("wp", "WP"), ("PV", "WP"), ("_CP", "CP"), ("pc", "CP"), ("f", "F"),
                    ("B", "F"), ("todo", "ALL"), ("ALL", "ALL"), ("l", "L"), ("UL", "L"),
                    ("P", "P"), ("r", "R"), ("E", "R"), ("A", "A"), ("u", "U"), ("H", "U"),
                    ("V", "W"), ("c", "C"), ("XYZ", ""), ("12,3", "")]:
    assert sel.opcion(escrito) == op, (escrito, sel.opcion(escrito))
print("ok opciones")

# ------------------------------------------------------------- 3. geometría
doc = Document(ezdxf.new("R2018"))
msp = doc.doc.modelspace()
adentro = msp.add_line((2, 2), (4, 2)).dxf.handle            # dentro del polígono
cruza = msp.add_line((8, 2), (12, 2)).dxf.handle             # cruza el borde derecho
afuera = msp.add_line((20, 20), (22, 20)).dxf.handle         # lejos de todo
circ = msp.add_circle((5, 4.5), 1).dxf.handle                  # dentro
hueco = msp.add_line((4.5, 8.5), (5.5, 8.5)).dxf.handle      # en la muesca del polígono en U
texto = msp.add_text("T", dxfattribs={"height": 0.5}).dxf.handle
msp.query(f'TEXT').first.dxf.insert = (2, 7)
idx = GeometryIndex(doc)
# polígono en U (cóncavo): de 0,0 a 10,10 con una muesca de 4,7 a 6,10
U = [(0, 0), (10, 0), (10, 10), (6, 10), (6, 7), (4, 7), (4, 10), (0, 10)]
wp = sel.seleccionar(idx, "WP", U)
assert adentro in wp and circ in wp and texto in wp, wp
assert cruza not in wp and afuera not in wp and hueco not in wp, wp   # la muesca no es «adentro»
cp = sel.seleccionar(idx, "CP", U)
assert adentro in cp and cruza in cp and circ in cp, cp
assert afuera not in cp and hueco not in cp, cp
f = sel.seleccionar(idx, "F", [(3, 0), (3, 3), (11, 3), (11, 1)])     # corta la de adentro y la que cruza
assert set(f) == {adentro, cruza}, f
assert sel.seleccionar(idx, "F", [(5, 4.3), (5, 4.7)]) == []          # dentro del círculo, sin tocarlo
assert circ in sel.seleccionar(idx, "F", [(5, 3), (5, 6)])            # lo atraviesa
assert sel.seleccionar(idx, "WP", [(0, 0), (1, 1)]) == []             # faltan puntos
print("ok geometría")


# ------------------------------------------------------------- 4. «Select objects»
class Senal:
    def __init__(self): self.n = 0
    def emit(self): self.n += 1


class Linea:
    def __init__(self): self.msgs = []
    def echo(self, t): self.msgs.append(t)


class Ctrl:
    """Lo que el módulo usa del ToolController de IngeCAD."""
    def __init__(self, document):
        self.window = types.SimpleNamespace(document=document, command_line=Linea())
        self.index = GeometryIndex(document)
        self.selection = set()
        self._selecting_for = object()             # una orden pidiendo objetos
        self._window_anchor = None
        self.changed = Senal()
        self.lastpoint = (0.0, 0.0)
        self.space_vp = None
    def _with_groups(self, handles): return set(handles)
    def to_space(self, x, y): return (x, y)


c = Ctrl(doc)
def escribir(*textos):
    for t in textos:
        assert sel.on_text(c, t) is True, t

escribir("WP", "0,0", "10,0", "10,10", "6,10", "6,7", "4,7", "4,10", "0,10", "")
assert c.selection == set(wp), c.selection
assert any("encontrados" in m for m in c.window.command_line.msgs)
escribir("U")                                       # deshace el polígono
assert c.selection == set()
escribir("PC", "7,1", "13,1", "13,3", "7,3", "")   # en español
assert c.selection == {cruza}
escribir("B", "3,0", "3,3", "")                     # borde
assert c.selection == {cruza, adentro}
escribir("E", "F", "3,0", "3,3", "")                # E = quitar (en «Select objects»)
assert c.selection == {cruza}
escribir("A", "W", "1,1", "5,3")                    # ventana con dos puntos escritos
assert c.selection == {cruza, adentro}
escribir("C", "21,19")                              # captura: el primer punto...
sel.agregar_punto(c, c._geocad_sel, (23, 21))       # ...y el segundo con un clic
assert afuera in c.selection
escribir("WP", "0,0", "1,0", "U", "U", "")          # U dentro del polígono borra vértices
assert c._geocad_sel.modo == "" and afuera in c.selection
escribir("ALL")
assert {adentro, cruza, afuera, circ, hueco, texto} <= c.selection
escribir("R", "L")                                  # quita el último dibujado (el texto)
assert texto not in c.selection
escribir("cualquiera")                              # no es opción: se avisa y no se rompe nada
assert any("no es una opción" in m for m in c.window.command_line.msgs)
assert sel.on_text(c, "") is False                  # Enter sin modo: IngeCAD termina la selección
c.selection, c._geocad_previa = set(), {circ, hueco}
escribir("A", "P")
assert c.selection == {circ, hueco}
# una orden nueva empieza con el estado limpio
c._selecting_for = object()
assert sel.estado(c).quitar is False and sel.estado(c).pasos == []
# sin «Select objects» en curso no se toca nada
c._selecting_for = None
assert sel.on_text(c, "WP") is False
print("ok designar objetos")

# ------------------------------------------------------------- 5. vista previa
c = Ctrl(doc)
escribir("CP", "0,0", "4,0")
r = sel.resaltado(c, (4, 4))
assert set(r) == {"sel_captura"} and len(r["sel_captura"]) == 3        # triángulo cerrado
escribir("")
c2 = Ctrl(doc); c = c2
escribir("F", "0,0")
assert len(sel.resaltado(c, (5, 5))["sel_borde"]) == 1
escribir("U", "")                                   # sin puntos: Enter sale del borde
assert sel.resaltado(c, (5, 5)) == {}


class Pintor:
    def __init__(self): self.lineas = 0
    def save(self): pass
    def restore(self): pass
    def setPen(self, p): pass
    def drawLine(self, a, b): self.lineas += 1
    def drawText(self, p, t): pass


c = Ctrl(doc)
escribir("WP", "0,0", "4,0", "4,4")
vista = types.SimpleNamespace(tool_delegate=types.SimpleNamespace(
    tool=None, _cursor=(0, 4), _selecting_for=c._selecting_for, _geocad_sel=c._geocad_sel),
    _space_to_screen=lambda x, y: (x, y))
qt = (lambda *a, **k: None, lambda *a: None, lambda x, y: (x, y),
      types.SimpleNamespace(DashLine=1, SolidLine=0))
pintor = Pintor()
assert dib.dibujar_resaltado(vista, pintor, qt=qt) == 4 and pintor.lineas == 4
print("ok vista previa")

# ------------------------------------------------------------- 6. envoltorios
class CtrlFalso(Ctrl):
    def on_click(self, wx, wy, shift=False): self.clics.append((wx, wy, shift))
    def start_window(self, wx, wy): self._window_anchor = (wx, wy)
    def _selection_click(self, wx, wy, shift):
        self.clics.append((wx, wy, shift)); self.selection = self.selection | {"X"}
    def _finish(self): self.selection = set(); self._selecting_for = None
    def cancel(self): self.cancelado = True


for nombre, fabrica in sel.ENVOLTORIOS.items():
    dib.envolver(CtrlFalso, nombre, fabrica, reemplazar=True)
c = CtrlFalso(doc); c.clics = []
c.on_click(1, 1)                                     # sin modo: el clic nativo
assert c.clics == [(1, 1, False)]
escribir("WP")
c.on_click(0, 0); c.on_click(5, 0)                   # con WP: son vértices
assert c.clics == [(1, 1, False)] and c._geocad_sel.puntos == [(0, 0), (5, 0)]
c.start_window(3, 3)                                 # arrastrar no abre ventana
assert c._window_anchor is None
escribir("", "R")
c._selection_click(2, 2, False)                      # con R el clic quita (como Mayús)
assert c.clics[-1] == (2, 2, True)
escribir("U")                                        # y U deshace ese clic
assert "X" not in c.selection
c.selection = {"Y"}
c._finish()                                          # al terminar: queda como «previa»
assert c._geocad_previa == {"Y"} and c._geocad_sel is None
c.cancel()
assert c.cancelado
# autocompletado
class Entrada:
    def __init__(self): self.completer = "nativo"
    def setCompleter(self, x): self.completer = x
class LineaComandos:
    def __init__(self): self.input = Entrada(); self.nombres = None
    def window(self): return None
    def set_completions(self, names): self.nombres = names; self.input.setCompleter("completador")
dib.envolver(LineaComandos, "set_completions", sel._envolver_set_completions, reemplazar=True)
lc = LineaComandos()
lc.set_completions(["LINE"])
assert lc.input.completer is None and lc.nombres is None             # módulo prendido: sin autocompletar
ventana = types.SimpleNamespace(command_line=lc, dispatcher=types.SimpleNamespace(known_names=lambda: ["LINE"]))
mods.poner("ingecad", "seleccion", False)
lc.set_completions(["LINE"])
assert lc.input.completer == "completador"                          # apagado: como venía
lc.input.completer = "x"
sel.aplicar_autocompletar(ventana)
assert lc.input.completer == "completador"
mods.poner("ingecad", "seleccion", True)
sel.aplicar_autocompletar(ventana)
assert lc.input.completer is None
print("ok envoltorios y autocompletado")

# ------------------------------------------------------------- 7. módulo apagado
mods.poner("ingecad", "seleccion", False)
c = Ctrl(doc)
assert sel.on_text(c, "WP") is False                 # IngeCAD como venía
assert "SELECT" not in geo.construir_spec().tools
mods.poner("ingecad", "seleccion", True)
assert "SELECT" in geo.construir_spec().tools
print("ok módulo apagado")

# ------------------------------------------------------------- 8. SEL
class Servicios(Ctrl):
    def request_selection(self):
        self._selecting_for = self.tool
    def finish(self):
        self.selection = set(); self.terminado = True
c = Servicios(doc)
c._selecting_for = None
msgs = []
ctx = ToolContext(execute=lambda cmd: None, prompt=msgs.append, echo=msgs.append,
                  finish=c.finish, services=c)
t = sel.SelTool(ctx)
c.tool = t
t.start()
assert c._selecting_for is t                         # pide objetos, con todas las opciones
assert "WP" in t.selection_prompt()
e1, e2 = idx.entity(adentro), idx.entity(circ)
t.on_selection([e1, e2])
assert c.terminado and c.selection == {adentro, circ}   # quedan seleccionados para la orden siguiente
assert c._geocad_previa == {adentro, circ}
print("ok SEL")

print("TODO OK SELECCION")
