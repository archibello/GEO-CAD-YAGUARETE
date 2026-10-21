"""Uniones de los grosores en pantalla (3.20.2): con LWT, las esquinas de
las polilíneas y las líneas que se tocan quedan unidas en inglete, sin la
muesca de cada vértice (modelo y papel)."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, math, inspect
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
import numpy as np
from core.document import Document
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
U = import_module("ingecad_plugin_geocad.uniones")
modulos = import_module("ingecad_plugin_geocad.modulos")
assert "uniones" in {m.clave for m in modulos.CATALOGO["ingecad"]}

try:
    import core.window_colors  # noqa: F401
except ImportError:
    import types
    sys.modules["core.window_colors"] = types.SimpleNamespace(background=lambda espacio: "#212830")
from render import batches as RBA
from render import backend as RB
from render.backend import TolerantFrontend, TolerantRenderContext, VertexBackend, frontend_config

U.instalar(); U.instalar()                                         # una sola vez
assert RBA._pack_thick._puente_fabrica is U._envolver_pack_thick
assert not hasattr(RBA._pack_thick._puente_original, "_puente_original")

GRUESA = {"lineweight": 100, "color": 1}                           # 1 mm: va en la tanda gruesa


def escena(dibujar):
    d = Document.new(); m = d.doc.modelspace()
    dibujar(m)
    be = VertexBackend(0.01, {})
    cfg = (frontend_config(0.01, d) if len(inspect.signature(frontend_config).parameters) > 1
           else frontend_config(0.01))
    fr = TolerantFrontend(TolerantRenderContext(d.doc), be, cfg)
    fr._host_document = d
    fr.draw_entities(m)
    return RB.pack(be.buckets, None)


def triangulos(sc, h):
    """Los triángulos de la tanda gruesa como se ven con medio grosor h."""
    v = sc.thick.data
    p = v["pos"].astype(float) + v["normal"].astype(float) * h + sc.origin
    return p.reshape(-1, 3, 2)


def cubierto(sc, punto, h):
    t = triangulos(sc, h); q = np.asarray(punto, float)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    def lado(p1, p2):
        return (p2[:, 0] - p1[:, 0]) * (q[1] - p1[:, 1]) - (p2[:, 1] - p1[:, 1]) * (q[0] - p1[:, 0])
    d1, d2, d3 = lado(a, b), lado(b, c), lado(c, a)
    neg = (d1 < -1e-9) | (d2 < -1e-9) | (d3 < -1e-9)
    pos = (d1 > 1e-9) | (d2 > 1e-9) | (d3 > 1e-9)
    return bool((~(neg & pos)).any())


H = 0.5
ele = lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10)], dxfattribs=GRUESA)
afuera = (10.4, -0.4)                                              # la esquina de afuera del codo

# -- apagado: la muesca de siempre entre dos LÍNEAs (desde IngeCAD 0.6.8 las
# esquinas de una misma polilínea ya las cierra IngeCAD; entre objetos
# distintos no)
dos = lambda m: (m.add_line((0, 0), (10, 0), dxfattribs=GRUESA), m.add_line((10, 0), (10, 10), dxfattribs=GRUESA))
real = modulos.estado; est = real("ingecad")
modulos.estado = lambda prog: {**est, "uniones": False}
try:
    sc = escena(dos)
    ingecad_une = cubierto(escena(ele), afuera, H)
finally:
    modulos.estado = real
assert not cubierto(sc, afuera, H), "sin el módulo, IngeCAD deja la muesca entre dos LÍNEAs"
print("ok apagado; IngeCAD ya une las esquinas de una polilínea:", ingecad_une)

# -- prendido: la esquina queda llena, en inglete, a cualquier zoom
sc = escena(ele)
for h in (H, 0.05, 2.0):
    assert cubierto(sc, (10 + 0.8 * h, -0.8 * h), h), h
assert cubierto(sc, (10.49, -0.49), H) and not cubierto(sc, (10.6, -0.6), H)   # inglete, no más
assert cubierto(sc, (9.6, 0.4), H)                                              # el lado de adentro
assert not cubierto(sc, (-0.3, 0), H) and not cubierto(sc, (10, 10.3), H)       # las puntas sueltas, como venían

# -- un ángulo abierto (135°) y uno agudo (30°): llenos, el agudo sin pico largo
abierto = lambda m: m.add_lwpolyline([(0, 0), (10, 0), (20, 10)], dxfattribs=GRUESA)
sc = escena(abierto)
bis = np.array([math.cos(math.radians(-67.5)), math.sin(math.radians(-67.5))])
assert cubierto(sc, np.array([10, 0]) + bis * 0.5, H)
agudo = lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10 - 10 * math.cos(math.radians(30)), 10 * math.sin(math.radians(30)))],
                                   dxfattribs=GRUESA)
sc = escena(agudo)
n = sc.thick.data["normal"].astype(float).reshape(-1, 2)
assert np.hypot(n[:, 0], n[:, 1]).max() <= U.LIMITE + 1e-5, "el inglete se acorta"
assert cubierto(sc, (10.3, 0.1), H)

# -- polilínea cerrada: las cuatro esquinas, también la del cierre
cuadro = lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs=GRUESA)
sc = escena(cuadro)
for esquina in ((-0.4, -0.4), (10.4, -0.4), (10.4, 10.4), (-0.4, 10.4)):
    assert cubierto(sc, esquina, H), esquina

# -- dos LÍNEAs que se tocan, en cualquier sentido
for a, b in ((((0, 0), (10, 0)), ((10, 0), (10, 10))), (((10, 0), (0, 0)), ((10, 0), (10, 10))),
             (((0, 0), (10, 0)), ((10, 10), (10, 0)))):
    sc = escena(lambda m: (m.add_line(*a, dxfattribs=GRUESA), m.add_line(*b, dxfattribs=GRUESA)))
    assert cubierto(sc, afuera, H), (a, b)

# -- 3.31.3: dos LÍNEAs junto a una polilínea en la misma tanda (lo de todo
# plano). Con IngeCAD 0.6.8, que ya pone sus ingletes, el módulo se
# apartaba de toda la tanda y volvía la muesca entre las LÍNEAs.
mezcla = lambda m: (dos(m), m.add_lwpolyline([(50, 0), (60, 0), (60, 10)], dxfattribs=GRUESA),
                    m.add_lwpolyline([(0, 50), (10, 50), (10, 60), (0, 60)], close=True, dxfattribs=GRUESA))
sc = escena(mezcla)
assert cubierto(sc, afuera, H), "las LÍNEAs se unen aunque la tanda traiga polilíneas"
for esquina in ((60.4, -0.4), (10.4, 49.6), (-0.4, 60.4), (-0.4, 49.6)):
    assert cubierto(sc, esquina, H), esquina
assert not cubierto(sc, (50.6, -0.6), H)                                         # la punta suelta, como venía
# un punto de DASHDOT (tramo de largo 0, IngeCAD 0.6.8) no se toca
def punteada(m):
    if "PUNTOS" not in m.doc.linetypes:
        m.doc.linetypes.add("PUNTOS", pattern=[2.0, 1.0, -0.5, 0.0, -0.5])   # raya, punto
    dos(m)
    m.add_line((0, 20), (40, 20), dxfattribs={**GRUESA, "linetype": "PUNTOS"})
sc = escena(punteada)
assert cubierto(sc, afuera, H)
v = sc.thick.data.reshape(-1, 6)
puntos = (v["pos"][:, 0] == v["pos"][:, 2]).all(axis=1)
assert len(v) > 10, len(v)                                                       # la línea va en rayas
modulos.estado = lambda prog: {**est, "uniones": False}
try:
    sin_p = escena(punteada).thick.data.reshape(-1, 6)
finally:
    modulos.estado = real
assert (v["normal"][puntos] == sin_p["normal"][puntos]).all(), "los puntos quedan como venían"
print("ok LÍNEAs junto a polilíneas y líneas punteadas (puntos de largo 0:", int(puntos.sum()), ")")

# -- lo que no se une: otro color, tres tramos en un punto, otro grosor
sc = escena(lambda m: (m.add_line((0, 0), (10, 0), dxfattribs=GRUESA),
                       m.add_line((10, 0), (10, 10), dxfattribs={"lineweight": 100, "color": 5})))
assert not cubierto(sc, afuera, H)
te = lambda m: (m.add_line((0, 0), (10, 0), dxfattribs=GRUESA), m.add_line((10, 0), (10, 10), dxfattribs=GRUESA),
                m.add_line((10, 0), (20, 0), dxfattribs=GRUESA))
modulos.estado = lambda prog: {**est, "uniones": False}
try:
    sin_t = escena(te)
finally:
    modulos.estado = real
assert (escena(te).thick.data["normal"] == sin_t.thick.data["normal"]).all(), "la T queda como venía"
antes = escena(lambda m: (m.add_line((0, 0), (10, 0), dxfattribs=GRUESA),
                          m.add_line((10, 0), (10, 10), dxfattribs={"lineweight": 50, "color": 1})))
assert not cubierto(antes, afuera, H)

# -- la escena pesa lo mismo y sus tandas siguen iguales
modulos.estado = lambda prog: {**est, "uniones": False}
try:
    sin = escena(cuadro)
finally:
    modulos.estado = real
con = escena(cuadro)
assert len(sin.thick.data) == len(con.thick.data)
assert [(r.first, r.count, r.lineweight) for r in sin.thick.ranges] == [(r.first, r.count, r.lineweight) for r in con.thick.ranges]
assert (sin.thick.data["pos"] == con.thick.data["pos"]).all()

# -- una forma que no es la esperada: no se toca nada
class Raro:
    data = np.zeros(5, dtype=[("pos", "<f4", 2), ("normal", "<f4", 2), ("rgba", "u1", 4)])
    ranges = ()
assert U.unir(Raro()) == 0

print("TODO OK UNIONES")
