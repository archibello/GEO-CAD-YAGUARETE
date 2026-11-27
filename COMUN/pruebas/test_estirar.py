"""ESTIRA (STRETCH) para IngeCAD (módulo «Estirar»): el resultado queda en
pantalla al momento (la orden dice qué tocó, la vista no regenera), lo
atrapado entero sigue al cursor como en DESPLAZA y lo que se estira se ve
estirado antes del clic. Con el módulo apagado, el STRETCH de IngeCAD."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
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

# ---- 7. sombreados (3.102.0, Fernando: «que "Stretch" pudiera modificar también
# los "hatch"»): como una polilínea; entero adentro se mueve entero ----------
S = import_module("ingecad_plugin_geocad.sombreado")


def sombreado(caminos=(), custom=True):
    doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
    h = msp.add_hatch()
    for c in caminos:
        h.paths.add_polyline_path(c, is_closed=True)
    if custom:
        S.aplicar(h, {"color": 256, "custom": {**S.DEFECTO, "lineas": "dobles", "separacion": 0.5,
                                                "origen": (1.0, 1.0), "fondo": (200, 220, 255)}})
    return doc, hist, msp, h


def herramienta(hist, rects, elegidos):
    msgs = []
    ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=msgs.append,
                      finish=lambda: None, services=Services(rects))
    t = T(ctx); t.start(); t.on_selection(elegidos)
    return t, msgs


def vertices(h, i=0):
    return [(round(v[0], 9), round(v[1], 9)) for v in h.paths[i].vertices]


# 7a. en parte: sólo los vértices adentro; Custom, fondo, grosor y origen quedan
doc, hist, msp, h = sombreado([[(0, 0), (20, 0), (20, 2), (0, 2)]])
antes = S.leer_custom(h)
enteros, estirados = est.clasificar([h], ventana)
assert enteros == [] and estirados == [h]
t, msgs = herramienta(hist, ventana, [h])
t.on_point((0, 0))
assert len(t.resaltado((5, 0))["estirado"]) == 4               # vista previa: el borde estirado
t.on_point((5, 0))
assert vertices(h) == [(0, 0), (25, 0), (25, 2), (0, 2)], vertices(h)
assert S.leer_custom(h) == antes                              # el origen de Custom queda
assert h.dxf.pattern_name == "_USER" and h.bgcolor is not None
hist.undo()
assert vertices(h) == [(0, 0), (20, 0), (20, 2), (0, 2)]
print("ok sombreado estirado en parte; un U lo deshace")

# 7b. entero adentro: se mueve entero, con el origen de Custom y el patrón
doc, hist, msp, h = sombreado([[(12, 0), (20, 0), (20, 2), (12, 2)]])
base = tuple(h.pattern.lines[0].base_point)
t, msgs = herramienta(hist, ventana, [h]); t.on_point((0, 0))
assert t.ghost_entities == [h]                                  # sigue al cursor como en DESPLAZA
t.on_point((3, 1))
assert vertices(h) == [(15, 1), (23, 1), (23, 3), (15, 3)]
assert close(S.leer_custom(h)["origen"], (4.0, 2.0)), S.leer_custom(h)
assert close(h.pattern.lines[0].base_point, (base[0] + 3, base[1] + 1)), (base, [tuple(l.base_point) for l in h.pattern.lines])
# elegido sin ventana (uno por uno): entero, como IngeCAD
doc, hist, msp, h = sombreado([[(0, 0), (4, 0), (4, 4), (0, 4)]])
t, msgs = herramienta(hist, [], [h]); t.on_point((0, 0)); t.on_point((10, 0))
assert vertices(h)[0] == (10, 0) and close(S.leer_custom(h)["origen"], (11.0, 1.0))
print("ok sombreado entero: se mueve con su origen")

# 7c. islas: sus vértices adentro también se mueven; si una queda afuera, avisa
doc, hist, msp, h = sombreado([[(0, 0), (20, 0), (20, 10), (0, 10)],
                               [(14, 4), (16, 4), (16, 6), (14, 6)]], custom=False)
h.set_pattern_fill("ANSI31", scale=1.0)
t, msgs = herramienta(hist, [(13, -1, 25, 11)], [h]); t.on_point((0, 0)); t.on_point((2, 0))
assert vertices(h, 0) == [(0, 0), (22, 0), (22, 10), (0, 10)]
assert vertices(h, 1) == [(16, 4), (18, 4), (18, 6), (16, 6)]
assert not any("Atención" in m for m in msgs), msgs
t, msgs = herramienta(hist, [(15, 3, 19, 7)], [h]); t.on_point((0, 0)); t.on_point((10, 0))
assert vertices(h, 1) == [(26, 4), (28, 4), (28, 6), (26, 6)]
assert "Atención: en un sombreado una isla quedó fuera del borde." in msgs, msgs
# el borde que se cruza solo, también avisa
doc, hist, msp, h = sombreado([[(0, 0), (10, 0), (10, 10), (0, 10)]], custom=False)
h.set_pattern_fill("ANSI31")
t, msgs = herramienta(hist, [(9, 9, 11, 11)], [h]); t.on_point((0, 0)); t.on_point((-15, -5))
assert "Atención: en un sombreado el borde se cruza." in msgs, msgs
print("ok islas: se estiran con el borde; avisa si una queda afuera o el borde se cruza")

# 7d. lados curvos: siguen curvos (la misma comba), en caminos de polilínea y de aristas
doc, hist, msp, h = sombreado(custom=False)
h.paths.add_polyline_path([(0, 0, 0), (10, 0, 1.0), (10, 10, 0), (0, 10, 0)], is_closed=True)
h.set_pattern_fill("ANSI31")
t, msgs = herramienta(hist, [(-1, -1, 11, 1)], [h]); t.on_point((0, 0)); t.on_point((0, -2))
v = list(h.paths[0].vertices)
assert close(v[1], (10, -2, 1.0)) and close(v[2], (10, 10, 0)), v
doc, hist, msp, h = sombreado(custom=False)
ca = h.paths.add_edge_path()
ca.add_line((0, 0), (10, 0)); arco = ca.add_arc((10, 5), 5, -90, 90, ccw=True)
ca.add_line((10, 10), (0, 10)); ca.add_line((0, 10), (0, 0))
h.set_pattern_fill("ANSI31")
t, msgs = herramienta(hist, [(-1, -1, 11, 1)], [h]); t.on_point((0, 0)); t.on_point((0, -2))
assert close(arco.real_start_point, (10, -2), 1e-6) and close(arco.real_end_point, (10, 10), 1e-6), \
    (arco.real_start_point, arco.real_end_point)
assert abs(arco.radius - 6) < 1e-6 and close(arco.center, (10, 4), 1e-6)   # sigue siendo medio círculo
assert close(ca.edges[0].end, (10, -2)) and close(ca.edges[0].start, (0, -2))
# horario (ccw=False), y el arco entero adentro se traslada
doc, hist, msp, h = sombreado(custom=False)
ca = h.paths.add_edge_path()
ca.add_line((0, 0), (0, 10)); arco = ca.add_arc((5, 10), 5, 0, 180, ccw=False)
ca.add_line((10, 10), (10, 0)); ca.add_line((10, 0), (0, 0))
h.set_pattern_fill("ANSI31")
t, msgs = herramienta(hist, [(-1, 9, 1, 11)], [h]); t.on_point((0, 0)); t.on_point((0, 2))
assert close(arco.real_start_point, (0, 12), 1e-6) and close(arco.real_end_point, (10, 10), 1e-6), \
    (arco.real_start_point, arco.real_end_point)
t, msgs = herramienta(hist, [(-1, 8, 11, 20)], [h]); t.on_point((0, 0)); t.on_point((0, 1))
assert close(arco.real_end_point, (10, 11), 1e-6) and close(arco.real_start_point, (0, 13), 1e-6)
print("ok lados curvos: siguen curvos con la misma comba; horarios también")

# 7e. una elipse a medias no se estira (sería inventarle la forma); lejos, nada cambia
doc, hist, msp, h = sombreado(custom=False)
ce = h.paths.add_edge_path()
ce.add_ellipse((5, 5), (5, 0), 0.5, 0, 360)
h.set_pattern_fill("ANSI31")
c0 = tuple(ce.edges[0].center)
t, msgs = herramienta(hist, [(9, -10, 11, 10)], [h]); t.on_point((0, 0)); t.on_point((3, 0))
assert close(ce.edges[0].center, c0)
t, msgs = herramienta(hist, [(-1, -1, 11, 11)], [h]); t.on_point((0, 0)); t.on_point((3, 0))
assert close(ce.edges[0].center, (8, 5))
assert est.estirar_sombreado(h, [(100, 100, 101, 101)], 1, 1) is False
print("ok elipse: entera se mueve, a medias queda; fuera de la ventana, nada")

print("TODO OK ESTIRAR")
