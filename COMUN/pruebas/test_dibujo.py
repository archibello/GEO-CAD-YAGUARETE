"""Dibujo al estilo Dibujo CAD: ángulos relativos al tramo anterior y botón
derecho = Enter. Sin ventana: un controlador falso que hace lo mismo que
ToolController.on_text (parse_point de IngeCAD + tool.on_point) con las
herramientas LÍNEA y POLILÍNEA reales de IngeCAD."""
import math, os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
from core.commands import History
from core.coords import parse_point
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
from tools.draw import LineTool, PlineTool

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
spec = lp.spec
assert "ANGREL" in spec.commands and "RIGHTCLICK" in spec.commands and spec.name == "GeoCAD Yaguareté"
dib = import_module("ingecad_plugin_geocad.dibujo")

def close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))

# ---- 1. el ángulo, como Dibujo CAD (units.parse_angle) -------------------
D = dib.direccion
assert D("90", None) == 90                          # primer tramo: absoluto
assert D("90", 0.0) == 270                          # interior: 180 + 90 (gira a la derecha)
assert D("180", 0.0) == 360                         # 180 = sigue derecho
assert D("270", 0.0) == 450                         # gira a la izquierda
assert D("<45", 0.0) == 45                          # << fuerza absoluto
assert abs(D("45d30'15\"", None) - 45.50416666666) < 1e-9
assert abs(D("30dI", 10.0) - 40.0) < 1e-12 and abs(D("30dD", 10.0) + 20.0) < 1e-12
assert D("N45dE", 0.0) == 45 and D("S30dO", 0.0) == 240   # rumbos: absolutos
assert D("N", 33.0) == 90
assert D("100g", None) == 90
assert D("30", 0.0, modo_rel="direccion") == 30
assert D("30", 0.0, rel=False) == 30
for malo in ("abc", "45d70'", "N95dE"):
    try: D(malo, 0.0); raise SystemExit("debió fallar: " + malo)
    except dib.AnguloError: pass
try: D("30dI", None); raise SystemExit("deflexión sin tramo")
except dib.AnguloError: pass
# la reescritura que recibe IngeCAD
R = dib.reescribir
assert R("@10<90", 0.0) == "@10<270"
assert R("@10<90", None) == "@10<90"
assert R("10<90", 0.0) == "10<90"                   # polar absoluta desde 0,0: no se toca
assert R("10<90", 0.0, relativa_sin_arroba=True) == "10<270"   # entrada dinámica
assert R("#10<45d30'", 0.0) == "#10<45.5"
assert R("@10<<90", 0.0) == "@10<90"
assert R("10,5", 0.0) is None and R("LINE", 0.0) is None
print("ok ángulos")

# ---- 2. dibujando de verdad con LÍNEA y POLILÍNEA -------------------------
doc = Document.new(); hist = History(doc); log = []
ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=log.append,
                  finish=lambda: None, undo_last=hist.undo)

class FakeController:
    """Lo esencial de ToolController.on_text para puntos tipeados."""
    def __init__(self, tool):
        self.tool = tool; self._selecting_for = None; self._modifier = None
        self.dyn_on = False; self.window = types.SimpleNamespace(
            plugins=None, command_line=types.SimpleNamespace(echo=log.append))
    def on_text(self, text):
        anchor = self.tool.last_point or (0.0, 0.0)
        p = parse_point(text.strip(), anchor, 0.0, relative_default=False)
        self.tool.on_point((p.x, p.y)); return True

assert dib.envolver(FakeController, "on_text", dib._envolver_on_text)
assert not dib.envolver(FakeController, "on_text", dib._envolver_on_text)   # una sola vez

def lines():
    return [(tuple(e.dxf.start)[:2], tuple(e.dxf.end)[:2]) for e in doc.modelspace().query("LINE")]

t = LineTool(ctx); t.start(); c = FakeController(t)
for s in ("0,0", "@10<0", "@5<90", "@10<90", "@5<90"):
    c.on_text(s)
L = lines()
assert len(L) == 4, L
# este -> (interior 90, antihorario) sur -> oeste -> norte: rectángulo que cierra
assert close(L[0][1], (10, 0)) and close(L[1][1], (10, -5)) and close(L[2][1], (0, -5)) and close(L[3][1], (0, 0)), L
t.on_enter()

# 180 = sigue derecho; 270 = gira a la izquierda; << absoluto; deflexión
t = LineTool(ctx); t.start(); c = FakeController(t)
for s in ("100,0", "@10<0", "@10<180", "@10<270", "@10<<0", "@10<90dI"):
    c.on_text(s)
L = lines()[4:]
assert close(L[1][1], (120, 0)) and close(L[2][1], (120, 10)) and close(L[3][1], (130, 10)) \
    and close(L[4][1], (130, 20)), L
t.on_enter()

# polilínea: un cuadrado de 10 con ángulos interiores de 90
t = PlineTool(ctx); t.start(); c = FakeController(t)
for s in ("0,100", "@10<90", "@10<90", "@10<90", "@10<90"):
    c.on_text(s)
v = [tuple(p) for p in t._verts]
assert close(v[1], (0, 110)) and close(v[2], (10, 110)) and close(v[3], (10, 100)) and close(v[4], (0, 100)), v
t.on_enter()

# un error de ángulo no dibuja nada y avisa
t = LineTool(ctx); t.start(); c = FakeController(t)
c.on_text("0,0"); c.on_text("@10<0"); n = len(lines())
assert c.on_text("@10<45d75'") is True and len(lines()) == n and "Ángulo no válido" in log[-1]
t.on_enter()

# con ANGREL desactivado vuelve a ser absoluto (como AutoCAD)
dib.set_relativo(False)
t = LineTool(ctx); t.start(); c = FakeController(t)
c.on_text("0,0"); c.on_text("@10<0"); c.on_text("@10<90")
assert close(lines()[-1][1], (10, 10)); t.on_enter()
dib.set_relativo(True)

# plugin desactivado: no toca nada
c.window.plugins = types.SimpleNamespace(is_active=lambda pid: False)
t = LineTool(ctx); t.start(); c.tool = t
c.on_text("0,0"); c.on_text("@10<0"); c.on_text("@10<90")
assert close(lines()[-1][1], (10, 10)); t.on_enter()
dib.desenvolver(FakeController, "on_text")
assert not hasattr(FakeController.on_text, "_puente_original")
print("ok dibujo")

# ---- 3. comando ANGREL ----------------------------------------------------
out = []; pctx = types.SimpleNamespace(echo=out.append)
spec.commands["ANGREL"](pctx, "D"); assert not dib.relativo() and "DESACTIVADOS" in out[-1]
spec.commands["ANGREL"](pctx);      assert dib.relativo() and "INTERIOR" in out[-1]
spec.commands["ANGREL"](pctx, "DIR"); assert dib.modo() == "direccion"
spec.commands["ANGREL"](pctx, "I"); assert dib.modo() == "interior"
print("ok ANGREL")

# ---- 4. botón derecho = Enter -------------------------------------------
sys.modules.setdefault("views", types.ModuleType("views"))
od = types.ModuleType("views.options_dialog"); od.RIGHT_CLICK_ENTER = "enter"; od.RIGHT_CLICK_MENU = "menu"
od.SETTING_RIGHT_CLICK = "input/right_click"; od.MODE = "enter"; od.right_click_mode = lambda: od.MODE
sys.modules["views.options_dialog"] = od

class FakeWindow:
    def __init__(self):
        self.calls = []; self.plugins = None; self.typed = ""
        self.tools = types.SimpleNamespace(active=lambda: False, _selecting_for=None, selection={"A1"})
        self.dispatcher = types.SimpleNamespace(pending_prompt=None, submit=lambda t: self.calls.append(("submit", t)))
        self.command_line = types.SimpleNamespace(input=types.SimpleNamespace(text=lambda: self.typed))
    def on_canvas_right_click(self, pos):
        self.calls.append(("original", pos))
    def show_canvas_context_menu(self, pos):
        self.calls.append(("menu", pos))

assert dib.envolver(FakeWindow, "on_canvas_right_click", dib._envolver_clic_derecho)
w = FakeWindow(); w.on_canvas_right_click(1)
assert w.calls == [("submit", "")], w.calls          # con selección también repite la última
w = FakeWindow(); w.tools.active = lambda: True; w.on_canvas_right_click(2)
assert w.calls == [("original", 2)]                  # en una orden: el Enter de IngeCAD
dib.set_boton_derecho(False); w = FakeWindow(); w.on_canvas_right_click(3)
assert w.calls == [("original", 3)]                  # módulo apagado: IngeCAD como venía
dib.set_boton_derecho(True)
od.MODE = "menu"; w = FakeWindow(); w.on_canvas_right_click(6)
assert w.calls == [("submit", "")]                   # el módulo manda, no el ajuste de IngeCAD
od.MODE = "enter"; w = FakeWindow(); w.plugins = types.SimpleNamespace(is_active=lambda p: False)
w.on_canvas_right_click(4); assert w.calls == [("original", 4)]
pressed = []; dib._apretar_enter_en_linea = lambda win: pressed.append(win.typed)
w = FakeWindow(); w.typed = "@10<90"; w.on_canvas_right_click(5)
assert pressed == ["@10<90"] and w.calls == []       # lo escrito se acepta como con Enter
print("ok botón derecho")

# ------------------------------------------------------------- REC con ORTO (3.9.4)
from tools.draw import RectangTool


class Ctrl:
    """Lo que el envoltorio usa del ToolController: ORTO lleva el punto a la
    horizontal/vertical del último punto, como resolved_point de IngeCAD."""
    def __init__(self, tool):
        self.tool, self.ortho_on, self.shift_held, self.window = tool, True, False, None
    def resolved_point(self, wx, wy):
        ancla = getattr(self.tool, "last_point", None)
        if ancla is not None and (self.ortho_on != self.shift_held):
            return (wx, ancla[1]) if abs(wx - ancla[0]) >= abs(wy - ancla[1]) else (ancla[0], wy)
        return (wx, wy)


resolver = dib._envolver_resolved_point(Ctrl.resolved_point)
rect = RectangTool.__new__(RectangTool); rect._first = None; rect._await = None; rect.last_point = None
c = Ctrl(rect)
assert not dib.orto_suelto(rect) and resolver(c, 3, 1) == (3, 1)      # primera esquina: como venía
rect._first = rect.last_point = (0, 0)
assert dib.orto_suelto(rect) and resolver(c, 10, 4) == (10, 4)        # otra esquina: sin ORTO
assert c.ortho_on is True                                             # ORTO queda como estaba
c.shift_held = True; assert resolver(c, 10, 4) == (10, 4); c.shift_held = False
rect._await = "dim_len"; assert not dib.orto_suelto(rect)             # sub-pregunta numérica: como venía
linea = types.SimpleNamespace(last_point=(0, 0)); c2 = Ctrl(linea)
assert resolver(c2, 10, 4) == (10, 0)                                 # LÍNEA: ORTO sigue mandando
print("ok REC con ORTO")

print("TODO OK DIBUJO")
