"""Sombreado Custom del HATCH de IngeCAD (3.99.0, módulo «sombreado»).
Líneas Ninguna/Simples/Dobles a 45° de la dirección, separación, origen,
color de fondo (HATCHBACKGROUNDCOLOR de AutoCAD) y grosor; sin líneas = SOLID
del color de fondo. Origen y dirección elegidos en el dibujo con la ventana
que vuelve. Áreas juntas o separadas, con islas; arcos como arcos. HATCHEDIT
lo vuelve a leer. El fondo se pinta. Módulo apagado: HATCH de IngeCAD."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile, math
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core import actions
from tools.base import ToolContext

ROOT = Path(__file__).resolve().parents[2]
lp = load_plugin(ROOT / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
S = import_module("ingecad_plugin_geocad.sombreado")
H = import_module("ingecad_plugin_geocad.sombreado_herramienta")
mods = import_module("ingecad_plugin_geocad.modulos")
pkg = import_module("ingecad_plugin_geocad")
dib = import_module("ingecad_plugin_geocad.dibujo")
from tools.blocks import HatchTool


def cerca(a, b, tol=1e-9):
    return abs(a - b) <= tol


def cuadrado(x, y, l):
    return [(x, y), (x + l, y), (x + l, y + l), (x, y + l)]


# -- 1. el HATCH: dobles, con fondo y grosor -------------------------------------
doc = ezdxf.new("R2018"); msp = doc.modelspace()
h = msp.add_hatch(); h.paths.add_polyline_path(cuadrado(0, 0, 10), is_closed=True)
ajustes = {"pattern": "CUSTOM", "color": 3, "custom": {
    "lineas": "dobles", "separacion": 0.5, "origen": (2.0, 3.0), "direccion": 30.0,
    "fondo": (200, 225, 255), "grosor": 35, "separados": False}}
S.aplicar(h, ajustes)
assert h.dxf.pattern_name == "_USER" and h.dxf.pattern_type == 0 and h.dxf.pattern_double == 1
assert not h.dxf.solid_fill
assert cerca(h.dxf.pattern_angle, 30.0) and cerca(h.dxf.pattern_scale, 0.5)
lineas = h.pattern.lines
assert len(lineas) == 2
assert cerca(lineas[0].angle, 30.0) and cerca(lineas[1].angle, 120.0), [l.angle for l in lineas]
for l in lineas:
    assert cerca(l.base_point.x, 2.0) and cerca(l.base_point.y, 3.0)       # pasa por el origen
    assert cerca(math.hypot(l.offset.x, l.offset.y), 0.5)                    # la separación
    rad = math.radians(l.angle)                                              # perpendicular a la línea
    assert cerca(l.offset.x * math.cos(rad) + l.offset.y * math.sin(rad), 0.0)
    assert not l.dash_length_items                                           # continuas
assert h.bgcolor == (200, 225, 255)
assert h.dxf.lineweight == 35 and h.dxf.color == 3
leido = S.leer_custom(h)
assert leido["lineas"] == "dobles" and cerca(leido["separacion"], 0.5)
assert leido["origen"] == (2.0, 3.0) and cerca(leido["direccion"], 30.0)
assert leido["fondo"] == (200, 225, 255) and leido["grosor"] == 35
print("ok HATCH Custom dobles: _USER, paralela y perpendicular a la dirección, origen, fondo, grosor")
# 3.99.1: un giro pedido; y los de la 3.99.0 (sin giro guardado) siguen a 45°
S.aplicar(h, dict(ajustes, custom=dict(ajustes["custom"], giro=45.0)))
assert cerca(h.dxf.pattern_angle, 75.0) and S.leer_custom(h)["giro"] == 45.0
tags = [t for t in h.get_xdata(S.APPID)][:7]
h.discard_xdata(S.APPID); h.set_xdata(S.APPID, [(t.code, t.value) for t in tags])
assert S.leer_custom(h)["giro"] == 45.0
print("ok Giro respecto de la dirección; los de la 3.99.0 conservan sus 45°")

# simples, color PorCapa, sin fondo
S.aplicar(h, {"pattern": "CUSTOM", "color": 256, "custom": {"lineas": "simples", "separacion": 2,
                                                           "direccion": 0, "fondo": None}})
assert len(h.pattern.lines) == 1 and cerca(h.pattern.lines[0].angle, 0.0)
assert h.dxf.pattern_double == 0 and h.bgcolor is None and h.dxf.color == 256
assert S.leer_custom(h)["lineas"] == "simples"
# ninguna: sólo el color de fondo, como SOLID
S.aplicar(h, {"pattern": "CUSTOM", "color": 256, "custom": {"lineas": "ninguna",
                                                           "fondo": (250, 200, 0)}})
assert h.dxf.solid_fill == 1 and h.dxf.pattern_name == "SOLID"
assert h.rgb == (250, 200, 0) and h.bgcolor is None
assert S.leer_custom(h)["lineas"] == "ninguna" and S.leer_custom(h)["fondo"] == (250, 200, 0)
print("ok Simples, PorCapa sin fondo; Ninguna = SOLID del color de fondo")

# se guarda y se vuelve a abrir igual (DXF)
S.aplicar(h, ajustes)
ruta = Path(tempfile.mkdtemp()) / "custom.dxf"
doc.saveas(ruta)
h2 = [e for e in ezdxf.readfile(ruta).modelspace() if e.dxftype() == "HATCH"][0]
assert h2.bgcolor == (200, 225, 255) and h2.dxf.pattern_double == 1 and h2.dxf.lineweight == 35
assert S.leer_custom(h2) == S.leer_custom(h)
print("ok DXF guardado y abierto: fondo, doble, grosor y datos de Custom")

# -- 2. HATCHEDIT ----------------------------------------------------------------------
assert mods.activo("ingecad", "sombreado")
s = actions.hatch_settings(h)
assert s["pattern"] == "CUSTOM" and s["custom"]["lineas"] == "dobles" and cerca(s["scale"], 0.5)
s2 = dict(s); s2["custom"] = dict(s["custom"], separacion=1.0, fondo=None)
actions.apply_hatch_settings(h, s2)
assert cerca(h.dxf.pattern_scale, 1.0) and h.bgcolor is None
assert cerca(math.hypot(h.pattern.lines[0].offset.x, h.pattern.lines[0].offset.y), 1.0)
actions.apply_hatch_settings(h, {"pattern": "ANSI31", "angle": 0.0, "scale": 1.0, "color": 256})
assert h.dxf.pattern_name == "ANSI31" and S.leer_custom(h) is None and h.bgcolor is None
assert actions.hatch_settings(h)["pattern"] == "ANSI31"
if hasattr(actions, "hatch_too_dense"):
    assert actions.hatch_too_dense([cuadrado(0, 0, 10)], "CUSTOM", 0.5) is False
    assert actions.hatch_too_dense([cuadrado(0, 0, 100000)], "CUSTOM", 0.001) is True
print("ok HATCHEDIT: abre en Custom, cambia separación y fondo; a ANSI31 deja de ser Custom")


# -- 3. la herramienta -------------------------------------------------------------------
class Indice:
    """Como el índice de IngeCAD: por handle, con lo que haya en el dibujo ahora."""
    def __init__(self, ents):
        self.lugar = ents if hasattr(ents, "query") else None
        self.fijos = list(ents)
    def _todos(self):
        return list(self.lugar) if self.lugar is not None else self.fijos
    def crossing(self, rect):
        return [e.dxf.handle for e in self._todos()]
    def entity(self, h):
        return next((e for e in self._todos() if e.dxf.handle == h), None)


class Servicios:
    def __init__(self, harness):
        self.h = harness
        self.index = Indice(list(harness.msp))
        import types
        self.window = types.SimpleNamespace(document=harness.document)
    def hatch_region_at(self, point):
        from core.hatch_boundary import region_at_point
        return region_at_point(list(self.h.msp), point)
    def pick_entity(self, point):
        for e in self.h.msp:
            if e.dxftype() == "LWPOLYLINE":
                cerca_borde = min(abs(point[0] - p[0]) + abs(point[1] - p[1]) for p in e.get_points("xy"))
                if cerca_borde < 1e-6:
                    return e
        return None


class Harness:
    def __init__(self, respuestas):
        self.document = Document(ezdxf.new("R2018")); self.history = History(self.document)
        self.msp = self.document.doc.modelspace()
        self.msgs = []; self.finished = False; self.preguntas = []
        self.respuestas = list(respuestas)

        def ask_hatch(settings):
            self.preguntas.append(dict(settings))
            r = self.respuestas.pop(0)
            return None if r is None else r(settings)
        self.ctx = ToolContext(execute=self.history.execute, prompt=self.msgs.append,
                               echo=self.msgs.append, finish=lambda: setattr(self, "finished", True),
                               ask_hatch=ask_hatch, undo_last=self.history.undo)

    def servicios(self):
        self.ctx.services = Servicios(self)

    def hatches(self):
        return [e for e in self.msp if e.dxftype() == "HATCH"]


def custom(**c):
    base = {"lineas": "dobles", "separacion": 1.0, "origen": (0.0, 0.0), "direccion": 0.0,
            "fondo": (255, 255, 200), "grosor": 25, "separados": False}
    base.update(c)
    return lambda _s: {"pattern": "CUSTOM", "color": 5, "scale": 1.0, "angle": 0.0, "custom": dict(base)}


# 3a. origen y dirección en el dibujo; la ventana vuelve con ellos
HatchTool._last = {"pattern": "SOLID", "scale": 1.0, "angle": 0.0, "color": 256}
hz = Harness([custom(_pedir=True), lambda s: dict(s)])
t = H.GeoHatchTool(hz.ctx); t.start()
assert hz.preguntas[0].get("_puede_pedir") is True
assert "origen" in hz.msgs[-1].lower(), hz.msgs[-1]
t.on_point((10.0, 20.0))
assert "dirección" in hz.msgs[-1].lower(), hz.msgs[-1]
assert t.preview_segments((10.0, 25.0)) == [((10.0, 20.0), (10.0, 25.0))]
t.on_point((10.0, 30.0))                    # hacia arriba: 90°
assert len(hz.preguntas) == 2
c = hz.preguntas[1]["custom"]
assert c["origen"] == (10.0, 20.0) and cerca(c["direccion"], 90.0) and "_pedir" not in c
assert S.es_custom(t.settings) and t._pedir is None
print("ok Elegir en el dibujo: origen, segundo punto con línea elástica, vuelve a la ventana")

# Intro mantiene el origen; un número NO da la dirección (3.99.2: el ángulo es siempre
# respecto de la dirección elegida); un punto sí; Esc vuelve a la ventana
hz = Harness([custom(_pedir=True, origen=(1.0, 2.0)), lambda s: dict(s, custom=dict(s["custom"], _pedir=True)),
              lambda s: dict(s)])
t = H.GeoHatchTool(hz.ctx); t.start()
assert t.on_option("") is True and t._pedir == "direccion"
assert t.on_option("2,13") is False and t.on_option("@5<30") is False   # coordenadas: las lee IngeCAD como punto
assert t.on_option("120") is True and t._pedir == "direccion" and len(hz.preguntas) == 1
assert any("se da con un punto" in m for m in hz.msgs)
t.on_point((1.0, 7.0))                       # hacia arriba desde el origen 1,2: 90°
assert cerca(hz.preguntas[1]["custom"]["direccion"], 90.0) and hz.preguntas[1]["custom"]["origen"] == (1.0, 2.0)
assert t._pedir == "origen"
t.on_cancel()                               # Esc: a la ventana, no termina la orden
assert len(hz.preguntas) == 3 and not hz.finished
print("ok Intro conserva el origen, un número no es la dirección, Esc vuelve a la ventana")


# 3b. áreas juntas y separadas, con islas
def dibujar(hz):
    for pts in (cuadrado(0, 0, 10), cuadrado(3, 3, 4), cuadrado(20, 0, 10)):
        hz.msp.add_lwpolyline(pts, close=True)
    hz.servicios()


for separados, esperados in ((False, 1), (True, 2)):
    hz = Harness([custom(separados=separados)])
    dibujar(hz)
    t = H.GeoHatchTool(hz.ctx); t.start()
    t.on_point((1.0, 1.0))                  # dentro del primero, fuera de la isla
    t.on_point((25.0, 5.0))
    t.on_enter()
    hs = hz.hatches()
    assert len(hs) == esperados, (separados, len(hs), hz.msgs)
    caminos = sorted(len(x.paths) for x in hs)
    assert caminos == ([3] if not separados else [1, 2]), caminos
    for x in hs:
        assert S.leer_custom(x)["separados"] is separados and x.bgcolor == (255, 255, 200)
        assert x.dxf.lineweight == 25 and x.dxf.color == 5 and x.dxf.hatch_style == 0
    hz.history.undo()
    assert not hz.hatches()                 # un solo U
print("ok clic dentro: juntos = 1 sombreado con la isla; separados = 1 por área; un U")

# objetos elegidos separados: el anidado es isla del que lo contiene; uno dentro de la isla vuelve a ser área
hz = Harness([custom(separados=True)])
for pts in (cuadrado(0, 0, 10), cuadrado(2, 2, 6), cuadrado(4, 4, 2), cuadrado(20, 0, 5)):
    hz.msp.add_lwpolyline(pts, close=True)
hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start()
t.on_option("S")
for p in ((0, 0), (2, 2), (4, 4), (20, 0)):
    t.on_point(p)
assert len(t.selected) == 4
t.on_enter()
assert sorted(len(x.paths) for x in hz.hatches()) == [1, 1, 2], [len(x.paths) for x in hz.hatches()]
assert S.agrupar([cuadrado(0, 0, 10), cuadrado(2, 2, 6), cuadrado(4, 4, 2)]) == [(0, [1]), (2, [])]
print("ok objetos elegidos por separado: islas anidadas respetadas")

# 3c. los arcos quedan arcos (máxima precisión)
hz = Harness([custom()])
hz.msp.add_lwpolyline([(0, 0, 0), (10, 0, 1.0), (10, 10, 0), (0, 10, 0)], format="xyb", close=True)
hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start()
t.on_point((5.0, 5.0)); t.on_enter()
camino = hz.hatches()[0].paths[0]
bulges = [v[2] for v in camino.vertices]
assert len(camino.vertices) <= 6 and any(abs(b - 1.0) < 1e-6 for b in bulges), camino.vertices
print("ok el borde encontrado guarda el arco como arco (bulge 1), no tramos")

# 3d. con otro patrón, el HATCH de IngeCAD tal cual
hz = Harness([lambda _s: {"pattern": "ANSI31", "scale": 1.0, "angle": 0.0, "color": 256}])
dibujar(hz)
t = H.GeoHatchTool(hz.ctx); t.start(); t.on_point((25.0, 5.0)); t.on_enter()
assert len(hz.hatches()) == 1 and hz.hatches()[0].dxf.pattern_name == "ANSI31", (hz.msgs, t.selected, [h.dxf.pattern_name for h in hz.hatches()])
assert S.leer_custom(hz.hatches()[0]) is None
# el botón abre ya en Custom
H.GeoHatchTool._abrir_custom = True
hz = Harness([None])
t = H.GeoHatchTool(hz.ctx); t.start()
assert hz.preguntas[0]["pattern"] == "CUSTOM" and hz.finished
assert H.GeoHatchTool._abrir_custom is False
print("ok otro patrón = HATCH de IngeCAD; el botón abre en Custom")

# 3e. contornos abiertos o mal cerrados (3.99.1)
hz = Harness([custom()])
hz.msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)])            # abierta: le falta el lado izquierdo
hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start(); t.on_point((5.0, 5.0)); t.on_enter()
assert len(hz.hatches()) == 1 and abs(S.area([v[:2] for v in hz.hatches()[0].paths[0].vertices]) - 100) < 1e-6, hz.msgs
assert any("cerrado" in m for m in hz.msgs)
hz = Harness([custom()])
for a, b in (((0, 0), (10, 0)), ((10, 0), (10, 10)), ((10, 10), (0, 10)), ((0, 10.05), (0, 0.02))):
    hz.msp.add_line(a, b)                                                 # mal cerrada: aberturas chicas
hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start(); t.on_point((5.0, 5.0)); t.on_enter()
assert len(hz.hatches()) == 1, hz.msgs
assert S.cierres([hz.msp.add_line((0, 0), (1, 0)), hz.msp.add_line((5, 0), (9, 0))], 0.5) == []   # lejos: no se cierra
# la L de Fernando (27/11/2026): dos lados y dos puntas de 3 vértices que casi se tocan.
# La 3.99.1 cerraba cada punta sobre sí misma y quedaban triángulos sin sombrear.
f = lambda pts: [(x / 40.0, -y / 40.0) for x, y in pts]
hz = Harness([custom()])
hz.msp.add_lwpolyline(f([(1290, 367), (430, 330), (408, 742)]))
hz.msp.add_lwpolyline(f([(448, 725), (466, 371), (1207, 402)]))
hz.msp.add_lwpolyline(f([(1207, 402.4), (1290, 405), (1290, 367.3)]))
hz.msp.add_lwpolyline(f([(408.2, 742), (448, 745), (448, 725.3)]))
hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start(); t.on_point((440 / 40.0, -500 / 40.0)); t.on_enter()
v = [tuple(round(c * 40) for c in (p[0], -p[1])) for p in hz.hatches()[0].paths[0].vertices]
L = f([(448, 725), (466, 371), (1207, 402), (1290, 405), (1290, 367), (430, 330), (408, 742), (448, 745)])
assert len(v) == 8 and set(v) == {(448, 725), (466, 371), (1207, 402), (1290, 405), (1290, 367), (430, 330),
                                  (408, 742), (448, 745)}, v
assert abs(S.area([p[:2] for p in hz.hatches()[0].paths[0].vertices]) - S.area(L)) < 1e-2 * S.area(L), (S.area([p[:2] for p in hz.hatches()[0].paths[0].vertices]), S.area(L), v)   # toda la superficie (salvo los saltos chicos)
print("ok polilínea abierta y líneas mal cerradas: se toman cerradas; la L, entera")

# 3f. clic sobre un objeto: el objeto es el contorno (abierta también)
hz = Harness([custom()])
abierta = hz.msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)])
hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start(); t.on_point((0.0, 0.0))          # sobre la polilínea
assert t.selected == [abierta] and "Objeto elegido como contorno." in hz.msgs, hz.msgs
t.on_enter()
assert len(hz.hatches()) == 1 and len(hz.hatches()[0].paths) == 1
hz = Harness([lambda _s: {"pattern": "ANSI31", "scale": 1.0, "angle": 0.0, "color": 256}])
abierta = hz.msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)]); hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start(); t.on_point((10.0, 10.0)); t.on_enter()
assert len(hz.hatches()) == 1 and hz.hatches()[0].dxf.pattern_name == "ANSI31", (hz.msgs, t.selected, [h.dxf.pattern_name for h in hz.hatches()])
print("ok clic sobre un objeto lo toma de contorno, con cualquier patrón")

# 3h. el puntero de elección (3.101.0): varios de a uno, resaltados, desHacer y Quitar
hz = Harness([custom()])
dibujar(hz)                                         # 0..10 con isla 3..7, y 20..30
lejos = hz.msp.add_lwpolyline(cuadrado(50, 0, 5), close=True); hz.servicios()
t = H.GeoHatchTool(hz.ctx); t.start()
assert t.entity_picker is True and "desHacer(H)" in t._prompt_source   # cuadradito, sin referencias
assert t.preview_segments((0.0, 0.0)) == []
t.on_point((1.0, 1.0)); t.on_point((25.0, 5.0)); t.on_point((50.0, 0.0))   # 2 áreas y 1 objeto
assert [k for k, _d in t._elegidos] == ["area", "area", "objeto"] and t.selected == [lejos]
assert len(t.preview_segments((0.0, 0.0))) == 4 * 4          # exterior, isla, el otro y el objeto
t.on_point((50.0, 0.0))
assert "Ese objeto ya está elegido." in hz.msgs and len(t._elegidos) == 3
t.on_option("H")                                    # desHacer: el último (el objeto)
assert t.selected == [] and len(t._regiones) == 2 and len(t.preview_segments((0, 0))) == 12
t.on_option("Q"); assert t.mode == "quitar" and t._prompt_source == t.PROMPT_QUITAR
t.on_point((5.0, 5.0))                              # dentro de la isla: no es un área elegida...
assert "Ahí no hay un contorno elegido." in hz.msgs
t.on_point((1.0, 1.0))                              # ...pero acá sí: se quita
assert len(t._regiones) == 1 and len(t.islands) == 0 and "1 contorno quitado." in hz.msgs
t.on_enter(); assert t.mode == "pick" and not hz.finished    # Intro: vuelve a sumar
t.on_option("u"); t.on_option("deshacer")
assert not t._elegidos and "No hay nada que deshacer." in hz.msgs
t.on_option("S"); t.on_point((50.0, 0.0)); t.on_point((60.0, 60.0))
assert t.selected == [lejos] and "Ahí no hay un objeto que sirva de contorno." in hz.msgs
t.on_option("Q"); t.on_point((50.0, 0.0)); assert not t.selected
t.on_option("A"); assert t.mode == "select"
t.on_point((50.0, 0.0)); t.on_enter()
assert len(hz.hatches()) == 1 and len(hz.hatches()[0].paths) == 1
# al pedir el origen, la cruz con referencias a objeto; al volver, el cuadradito
hz = Harness([custom(_pedir=True), lambda s: dict(s)])
dibujar(hz)
t = H.GeoHatchTool(hz.ctx); t.start()
assert t._pedir == "origen" and t.entity_picker is False
t.on_point((0.0, 0.0)); t.on_point((10.0, 0.0))
assert t._pedir is None and t.entity_picker is True
# con un patrón de IngeCAD, igual (Deshacer y Quitar)
hz = Harness([lambda _s: {"pattern": "ANSI31", "scale": 1.0, "angle": 0.0, "color": 256}])
dibujar(hz)
t = H.GeoHatchTool(hz.ctx); t.start(); t.on_point((1.0, 1.0)); t.on_point((25.0, 5.0)); t.on_option("H")
t.on_enter()
assert len(hz.hatches()) == 1 and len(hz.hatches()[0].paths) == 2, [len(x.paths) for x in hz.hatches()]
print("ok puntero de elección: cuadradito, lo elegido resaltado, desHacer, Quitar contornos y Agregar")

# 3g. agarres: uno en el medio de cada lado; moverlo y agregar un vértice
from core import select
doc = ezdxf.new("R2018"); h = doc.modelspace().add_hatch()
h.paths.add_polyline_path(cuadrado(0, 0, 10), is_closed=True)
S.aplicar(h, ajustes)
g = select.entity_grips(h)
medios = [(i, x, y) for i, (x, y, r) in enumerate(g) if r == "mid"]
assert sorted((x, y) for _i, x, y in medios) == [(0, 5), (5, 0), (5, 10), (10, 5)], g
vert = [(i, x, y) for i, (x, y, r) in enumerate(g) if r == "vertex"]
assert len(vert) == 4
# 3.100.1 (Fernando): ningún agarre fuera de la figura, como un polígono
assert not [r for *_p, r in g if r == "center"] and len(g) == 8, g
i_abajo = [i for i, x, y in medios if (x, y) == (5, 0)][0]
assert select.apply_grip_edit(h, i_abajo, "mid", (5, -2))               # el lado de abajo baja 2
assert sorted(tuple(v[:2]) for v in h.paths[0].vertices) == [(0, -2), (0, 10), (10, -2), (10, 10)]
i_v = [i for i, x, y in vert if (x, y) == (10, 10)][0]
assert select.apply_grip_edit(h, i_v, "vertex", (12, 12))
assert (12, 12) in [tuple(v[:2]) for v in h.paths[0].vertices]
AG = import_module("ingecad_plugin_geocad.agarres_ingecad")
g = select.entity_grips(h)
i_der = [i for i, (x, y, r) in enumerate(g) if r == "mid" and abs(x - 11) < 1e-9][0]   # lado derecho
assert AG.tramo_recto(h, i_der)
nuevo = AG.agregar_vertice(h, i_der, (11.0, 5.0))
g2 = select.entity_grips(h)
assert g2[nuevo][:2] == (11.0, 5.0) and g2[nuevo][2] == "vertex" and len(h.paths[0].vertices) == 5
assert select.apply_grip_edit(h, nuevo, "vertex", (15.0, 5.0))
assert (15.0, 5.0) in [tuple(v[:2]) for v in h.paths[0].vertices]
assert len([r for *_p, r in select.entity_grips(h) if r == "mid"]) == 5
# un camino de lados (EdgePath), como los que vienen de AutoCAD
h2 = doc.modelspace().add_hatch(); ep = h2.paths.add_edge_path()
for a, b in zip(cuadrado(0, 0, 4), cuadrado(0, 0, 4)[1:] + cuadrado(0, 0, 4)[:1]):
    ep.add_line(a, b)
g = select.entity_grips(h2)
i_m = [i for i, (x, y, r) in enumerate(g) if r == "mid" and (x, y) == (2, 0)][0]
n2 = AG.agregar_vertice(h2, i_m, (2.0, 0.0))
assert select.entity_grips(h2)[n2][:2] == (2.0, 0.0) and len(h2.paths[0].edges) == 5
assert select.apply_grip_edit(h2, n2, "vertex", (2.0, -1.0))
assert [tuple(e.end) for e in h2.paths[0].edges][0] == (2.0, -1.0)
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": False})
assert not [r for *_p, r in select.entity_grips(h) if r == "mid"]   # apagado: los de IngeCAD
assert [r for *_p, r in select.entity_grips(h) if r == "center"]      # (con el del centro)
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": True})
print("ok agarre en el medio de cada lado: mueve el lado; agrega vértice (también en caminos de lados); sin agarre en el centro")

# -- 4. el fondo se pinta, debajo de las líneas -----------------------------------------
from ezdxf.addons.drawing.frontend import Frontend
from ezdxf.addons.drawing.properties import RenderContext
from ezdxf.addons.drawing.recorder import Recorder

doc = ezdxf.new("R2018"); msp = doc.modelspace()
h = msp.add_hatch(); h.paths.add_polyline_path(cuadrado(0, 0, 10), is_closed=True)
S.aplicar(h, ajustes)


def pintado(d):
    rec = Recorder()
    Frontend(RenderContext(d), rec).draw_layout(d.modelspace())
    return [("FILLED_PATHS" if type(r).__name__ == "FilledPathsRecord" else type(r).__name__, r.property_hash) for r in rec.records], rec


tipos, rec = pintado(doc)
props = rec.properties
colores = [(t, props[ph].color[:7]) for t, ph in tipos]
assert ("FILLED_PATHS", "#c8e1ff") in colores, colores
assert colores.index(("FILLED_PATHS", "#c8e1ff")) < max(i for i, c in enumerate(colores) if c[0] != "FILLED_PATHS")
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": False})
tipos2, rec2 = pintado(doc)
assert ("FILLED_PATHS", "#c8e1ff") not in [(t, rec2.properties[ph].color[:7]) for t, ph in tipos2]
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": True})
print("ok el color de fondo se pinta antes que las líneas; apagado, como IngeCAD")

# -- 4b. estilos guardados (3.99.2) -------------------------------------------------------
assert S.estilos() == {}
c = S.custom_de({"custom": {"lineas": "dobles", "separacion": 0.3, "giro": 10, "fondo": (128, 128, 128),
                            "grosor": 15, "origen": (5, 5), "direccion": 30}})
assert S.guardar_estilo("  Piso 30x30 gris ", c, 3) == "Piso 30x30 gris"
S.guardar_estilo("Pasto", dict(c, lineas="ninguna", fondo=(0, 160, 0)))
e = S.estilos()
assert list(e) == ["Piso 30x30 gris", "Pasto"]
assert e["Piso 30x30 gris"] == {"lineas": "dobles", "separacion": 0.3, "giro": 10.0, "fondo": (128, 128, 128),
                                "grosor": 15, "color": 3}, e                     # sin origen ni dirección
otro = S.aplicar_estilo(S.custom_de({"custom": {"origen": (1, 2), "direccion": 90}}), e["Pasto"])
assert otro["origen"] == (1.0, 2.0) and otro["direccion"] == 90.0 and otro["lineas"] == "ninguna"
assert S.renombrar_estilo("Pasto", "Césped") and list(S.estilos()) == ["Piso 30x30 gris", "Césped"]
assert not S.renombrar_estilo("Césped", "Piso 30x30 gris")                  # ya existe
assert S.borrar_estilo("Césped") and list(S.estilos()) == ["Piso 30x30 gris"]
try:
    S.guardar_estilo("   ", c); raise SystemExit("sin nombre no se guarda")
except ValueError:
    pass
S.archivo_estilos().write_text("roto", encoding="utf-8")
assert S.estilos() == {}                                                    # archivo roto: ninguno, sin error
S.archivo_estilos().unlink()
print("ok estilos guardados: guardar, sin origen ni dirección, cargar, renombrar, borrar")

# -- 4c. TRIM y JOIN con sombreados (3.100.0) ----------------------------------------------
E = import_module("ingecad_plugin_geocad.sombreado_edicion")
UP = import_module("ingecad_plugin_geocad.unir_poligonos")


class ServiciosTrim:
    def __init__(self, hz, hatch):
        self.index = Indice(hz.msp); self.h = hatch
    def pick_entity(self, point):
        return self.h if self.h.is_alive else None
    def edges_geometry(self, *a, **k):
        return [], []


hz = Harness([])
h = hz.msp.add_hatch(color=5); h.paths.add_polyline_path(cuadrado(0, 0, 10), is_closed=True)
h.paths.add_polyline_path(cuadrado(6, 6, 2), is_closed=True)
S.aplicar(h, ajustes)
corte = hz.msp.add_line((4, -1), (4, 11))
otra = hz.msp.add_line((-1, 3), (11, 3))
hz.ctx.services = ServiciosTrim(hz, h)
t = H.GeoTrimTool(hz.ctx); t.start(); t.on_selection([corte])          # sólo x = 4 corta
t.on_point((2.0, 5.0))
hs = hz.hatches()
assert len(hs) == 1 and hs[0] is not h, hz.msgs
nuevo = hs[0]
sup = E.superficie(nuevo)
assert abs(sup - (60 - 4)) < 1e-6, sup                                 # 6 x 10 menos la isla
assert S.leer_custom(nuevo) == S.leer_custom(h) and nuevo.bgcolor == (200, 225, 255)
assert nuevo.dxf.pattern_name == "_USER" and nuevo.dxf.color == h.dxf.color == 3 and len(nuevo.paths) == 2, (nuevo.dxf.pattern_name, nuevo.dxf.color, len(nuevo.paths), h.dxf.color)
hz.ctx.services.h = nuevo
t.on_point((5.0, 5.0)) if False else None
hz.history.undo()
assert [x for x in hz.hatches()] == [h] and h.is_alive                # un U lo devuelve
# sin borde que lo cruce en ese lugar: nada
hz.ctx.services.h = h
t = H.GeoTrimTool(hz.ctx); t.start(); t.on_selection([hz.msp.add_line((20, 0), (20, 5))])
t.on_point((2.0, 5.0))
assert hz.hatches() == [h] and any("Ningún borde de corte" in m for m in hz.msgs)
# todos los objetos como bordes (Intro): dos cortes, se borra el pedazo de abajo a la izquierda
t = H.GeoTrimTool(hz.ctx); t.start(); t.on_selection([])
t.on_point((1.0, 1.0))
assert abs(E.superficie(hz.hatches()[0]) - (96 - 12)) < 1e-6, E.superficie(hz.hatches()[0])
# un arco del borde sigue siendo arco después del corte
hz = Harness([])
h = hz.msp.add_hatch(); h.paths.add_polyline_path([(0, 0, 0), (10, 0, 1.0), (10, 10, 0), (0, 10, 0)], is_closed=True)
corte = hz.msp.add_line((4, -1), (4, 11))
hz.ctx.services = ServiciosTrim(hz, h)
t = H.GeoTrimTool(hz.ctx); t.start(); t.on_selection([corte]); t.on_point((2.0, 5.0))
v = hz.hatches()[0].paths[0].vertices
assert any(abs(b[2] - 1.0) < 1e-6 for b in v) and len(v) <= 6, v
# con una línea, el TRIM de IngeCAD
assert H.GeoTrimTool.apply_to_entity is not None
print("ok TRIM: el clic borra la parte del sombreado; islas, Custom, fondo y arcos quedan; un U")

# JOIN: mismo estilo se unen; distinto estilo pregunta
hz = Harness([])
a = hz.msp.add_hatch(); a.paths.add_polyline_path(cuadrado(0, 0, 4), is_closed=True); S.aplicar(a, ajustes)
b = hz.msp.add_hatch(); b.paths.add_polyline_path(cuadrado(4, 0, 2), is_closed=True); S.aplicar(b, ajustes)
c = hz.msp.add_hatch(); c.paths.add_polyline_path(cuadrado(6, 0, 2), is_closed=True)
c.set_pattern_fill("ANSI31", color=1, scale=1.0)
t = UP.UnirTool(hz.ctx); t.start(); t.on_selection([a, b, c])
assert t._sombreados is not None and "estilos distintos" in hz.msgs[-1], hz.msgs[-1]
t.on_enter()                                                            # No: sólo los del mismo estilo
hs = hz.hatches()
assert len(hs) == 2 and c in hs and a not in hs and b not in hs, hz.msgs
u = [x for x in hs if x is not c][0]
assert abs(E.superficie(u) - 20) < 1e-6 and S.leer_custom(u) is not None and u.bgcolor == (200, 225, 255)
assert any("de otro estilo quedaron aparte" in m for m in hz.msgs)
hz.history.undo()
assert len(hz.hatches()) == 3
t = UP.UnirTool(hz.ctx); t.start(); t.on_selection([a, b, c]); t.on_option("S")
hs = hz.hatches()
assert len(hs) == 1 and abs(E.superficie(hs[0]) - 24) < 1e-6
assert hs[0].dxf.pattern_name == "_USER" and S.leer_custom(hs[0]) is not None    # el del mayor (a)
hz.history.undo()
# los que no se tocan: nada
d = hz.msp.add_hatch(); d.paths.add_polyline_path(cuadrado(50, 0, 2), is_closed=True); S.aplicar(d, ajustes)
t = UP.UnirTool(hz.ctx); t.start(); t.on_selection([a, d])
assert any("no se tocan" in m for m in hz.msgs) and a.is_alive and d.is_alive
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": False})
t = UP.UnirTool(hz.ctx); t.start(); t.on_selection([a, b])
assert t._sombreados is None and a.is_alive                           # apagado: el JOIN de IngeCAD
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": True})
print("ok JOIN: mismo estilo se unen; distinto estilo: No = los del mismo estilo, Sí = el del mayor")

# -- 5. el módulo ---------------------------------------------------------------------------
assert any(m.clave == "sombreado" and m.cambia_programa for m in mods.CATALOGO["ingecad"])
spec = pkg.construir_spec()
herr = getattr(spec, "tools", None) or {}
assert "GEOHATCH" in herr and "GEOHATCHCUSTOM" in spec.commands
assert any(i.command == "GEOHATCHCUSTOM" for i in spec.toolbar)
assert dib.herramienta_para("HATCH", None, herr) == "GEOHATCH"
assert "GEOTRIM" in herr and dib.herramienta_para("TRIM", None, herr) == "GEOTRIM"
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": False})
spec = pkg.construir_spec(); herr = getattr(spec, "tools", None) or {}
assert "GEOHATCH" not in herr and "GEOHATCHCUSTOM" not in spec.commands
assert dib.herramienta_para("HATCH", None, herr) == "HATCH"
assert dib.herramienta_para("TRIM", None, herr) == "TRIM"
doc = ezdxf.new("R2018"); h = doc.modelspace().add_hatch()
h.paths.add_polyline_path(cuadrado(0, 0, 10), is_closed=True); S.aplicar(h, ajustes)
assert actions.hatch_settings(h)["pattern"] == "_USER"          # apagado: lo que ve IngeCAD
mods.guardar("ingecad", {**mods.estado("ingecad"), "sombreado": True})
print("ok módulo sombreado: HATCH -> GEOHATCH y botón; apagado, IngeCAD como venía")
print("TODO OK")
