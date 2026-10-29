"""Perpendicular y Apparent Intersection con guías de puntos (3.56.0), sin Qt:
las cuentas de guias.py (iguales en IngeCAD y QGIS), las líneas tomadas con
el medio segundo, y el lado de IngeCAD (guias_ingecad) con un controlador
simulado: el punto flotante, las guías, APP fuera del gris y el módulo
apagado. Lo que se ve lo prueban ventana/banco_guias_ventana.py (IngeCAD
real) y test_referencias.py (QGIS real)."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, filecmp
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
import numpy as np
from core.plugins import load_plugin

RAIZ = Path(__file__).resolve().parents[2]
# una sola copia de las cuentas: el núcleo, igual en los dos lados
for lado in ("INGECAD", "QGIS"):
    assert filecmp.cmp(RAIZ / "COMUN" / "nucleo" / "guias.py",
                       RAIZ / lado / "codigo" / "geocad" / "guias.py", shallow=False), lado

lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
G = import_module("ingecad_plugin_geocad.guias")
GI = import_module("ingecad_plugin_geocad.guias_ingecad")
modulos = import_module("ingecad_plugin_geocad.modulos")


def cerca(a, b, tol=1e-9):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


# ---------------------------------------------------------------- cuentas
H = (0.0, 0.0, 10.0, 0.0)          # horizontal
V = (20.0, 5.0, 20.0, 15.0)        # vertical, a la derecha y arriba
P = (0.0, 3.0, 10.0, 3.0)          # paralela a H

pie, guias = G.perpendicular((5, 10), H)
assert cerca(pie, (5, 0)) and guias == []                     # cae en el tramo: sin guía
pie, guias = G.perpendicular((-5, 10), H)
assert cerca(pie, (-5, 0)) and len(guias) == 1
assert cerca(guias[0][0], (0, 0)) and cerca(guias[0][1], (-5, 0))   # de la punta más cercana
pie, guias = G.perpendicular((30, 7), (10.0, 0.0, 0.0, 0.0))  # al revés, misma guía
assert cerca(pie, (30, 0)) and cerca(guias[0][0], (10, 0))
assert G.perpendicular((3, 0), H) is None                     # el punto sobre la recta
assert G.perpendicular(None, H) is None
assert G.perpendicular((1, 1), (2, 2, 2, 2)) is None          # sin largo

cruce, guias = G.aparente(H, V)
assert cerca(cruce, (20, 0)) and len(guias) == 2
assert cerca(guias[0][0], (10, 0)) and cerca(guias[1][0], (20, 5))
assert all(cerca(g[1], (20, 0)) for g in guias)
cruce, guias = G.aparente(H, (5.0, -5.0, 5.0, 5.0))           # se cruzan de verdad
assert cerca(cruce, (5, 0)) and guias == []
cruce, guias = G.aparente(H, (5.0, 2.0, 5.0, 8.0))            # sólo una no llega
assert cerca(cruce, (5, 0)) and len(guias) == 1 and cerca(guias[0][0], (5, 2))
assert G.aparente(H, P) is None                               # paralelas
assert G.aparente(H, (3.0, 0.0, 8.0, 0.0)) is None            # colineales
# coordenadas grandes (Gauss-Krüger): sin perder el cruce
gk = (5500000.0, 6200000.0, 5500100.0, 6200000.0)
cruce, _ = G.aparente(gk, (5500200.0, 6200050.0, 5500200.0, 6200080.0))
assert cerca(cruce, (5500200.0, 6200000.0), 1e-6)

assert G.mismo_tramo(H, (10, 0, 0, 0)) and not G.mismo_tramo(H, P)
assert G.tramo_cercano((5, 0.3), 0.5, [P, H, V]) == H
assert G.tramo_cercano((5, 1.5), 0.5, [P, H, V]) is None
assert G.tramo_cercano((2, 2), 1, [(2, 2, 2, 2)]) is None      # sin largo no cuenta

# las tomadas: medio segundo encima; la tercera reemplaza a la más vieja
assert G.TOMA_MS == 500
t = G.Tomadas("APP")
assert t.esperar(H) is True and t.esperar(H) is False         # el reloj no se reinicia
assert t.tomar() and t.lista == [H]
assert t.esperar(H) is False and t.espera is None             # ya tomada
assert t.esperar(V) and t.tomar() and t.esperar(P) and t.tomar()
assert t.lista == [V, P]
assert t.esperar(None) is False and not t.tomar()
t = G.Tomadas("PER")
t.esperar(H); t.tomar(); t.esperar(V); t.tomar()
assert t.lista == [V]                                          # PER: una sola

# calcular: lo de encima cuenta al momento, aunque todavía no esté tomado
t = G.Tomadas("APP")
assert G.calcular("APP", t, H, None) is None                   # una sola línea
t.lista = [H]
p, guias, usados = G.calcular("APP", t, V, None)
assert cerca(p, (20, 0)) and usados == [H, V]
assert G.calcular("APP", t, None, None) is None
t.lista = [H, P]
assert G.calcular("APP", t, None, None) is None                # dos paralelas
t.lista = [H, V]
assert cerca(G.calcular("APP", t, None, None)[0], (20, 0))
t = G.Tomadas("PER")
assert G.calcular("PER", t, None, (5, 10)) is None
t.lista = [H]
assert cerca(G.calcular("PER", t, None, (-5, 10))[0], (-5, 0))
assert cerca(G.calcular("PER", t, V, (0, 10))[0], (20, 10))    # la de encima gana

# ---------------------------------------------------------------- IngeCAD
assert "referencias" in [m.clave for m in modulos.catalogo("ingecad")]
assert modulos.activo("ingecad", "referencias")

from core import osnap
assert "APP" not in osnap.AVAILABLE                            # IngeCAD la trae en gris
originales = osnap.MODES
GI.aplicar_modos()
assert "APP" in osnap.AVAILABLE and osnap.BY_KEY["APP"].available
assert osnap.BY_KEY["APP"].label == "Apparent Intersection"
assert [m.key for m in osnap.MODES] == [m.key for m in originales]
assert osnap.from_bits(2048) == frozenset({"APP"})             # también entre las activas
assert osnap.override_from_text("APP") == frozenset({"APP"})
modulos.guardar("ingecad", {"referencias": False})
GI.aplicar_modos()
assert osnap.MODES is originales and "APP" not in osnap.AVAILABLE   # apagado: como venía
modulos.guardar("ingecad", {"referencias": True})
GI.aplicar_modos()
assert "APP" in osnap.AVAILABLE


class Reloj:
    def __init__(self):
        self.andando = False

    def start(self):
        self.andando = True

    def stop(self):
        self.andando = False


class Motor:
    _dirty = False

    def __init__(self, tramos):
        self._segs = np.array(tramos, dtype=float)
        s = self._segs
        self._seg_bounds = np.column_stack([np.minimum(s[:, 0], s[:, 2]), np.minimum(s[:, 1], s[:, 3]),
                                            np.maximum(s[:, 0], s[:, 2]), np.maximum(s[:, 1], s[:, 3])])


class Herramienta:
    def __init__(self, ultimo):
        self.last_point = ultimo
        self.dibujado = []

    def drawn_segments(self):
        return self.dibujado


class Controlador:
    """Lo que guiar() usa del ToolController de IngeCAD."""

    def __init__(self, override, ultimo=(5.0, 10.0)):
        self.snap_engine = Motor([H, V, P])
        self.tool = Herramienta(ultimo)
        self.osnap_override = override
        self.activas = frozenset({"END"})
        self.snap_hit = None
        self._cursor = None
        self._track_tolerance = 0.5
        self.reloj = Reloj()
        self.cambios = 0
        self.changed = type("S", (), {"emit": lambda _s: setattr(self, "cambios", self.cambios + 1)})()

    def snap_kinds(self):
        return self.osnap_override if self.osnap_override is not None else self.activas

    def anchor_point(self):
        return self.tool.last_point

    def on_hover(self, x, y, hit=None):
        # como IngeCAD: su propia referencia (o nada), y después GeoCAD
        self._cursor, self.snap_hit = (x, y), hit
        self._geocad_ultimo = ((x, y), {"hit": hit})
        GI.guiar(self, self.reloj)

    def tomar(self):
        """Se cumplió el medio segundo."""
        assert self.reloj.andando
        self.reloj.andando = False
        GI._tomar(self)


# Perpendicular desde (-5, 10): el pie cae fuera de H, con su guía
c = Controlador(frozenset({"PER"}), ultimo=(-5.0, 10.0))
c.on_hover(5.0, 0.2)
assert c.snap_hit.kind == "PER" and cerca((c.snap_hit.x, c.snap_hit.y), (-5, 0))
guias, tomadas = c._geocad_guias
assert len(guias) == 1 and cerca(guias[0][0], (0, 0)) and tomadas == []
assert c.reloj.andando                                         # esperando el medio segundo
c.on_hover(50.0, 50.0)                                         # se fue antes: nada
assert c.snap_hit is None and not c.reloj.andando and c._geocad_guias == ([], [])
c.on_hover(5.0, 0.2); c.tomar()                                # se detuvo: tomada
assert c._geocad_tomadas.lista == [H] and c.cambios == 1
c.on_hover(50.0, 50.0)                                         # se fue: el pie sigue
assert cerca((c.snap_hit.x, c.snap_hit.y), (-5, 0)) and c._geocad_guias[1] == [H]

# Apparent Intersection: H, después V; el cruce flotante con las dos guías
c = Controlador(frozenset({"APP"}))
c.on_hover(5.0, 0.2)
assert c.snap_hit is None and c.reloj.andando                  # una sola línea: todavía no
c.tomar()
c.on_hover(20.1, 10.0)                                         # sobre V: al momento
assert c.snap_hit.kind == "APP" and cerca((c.snap_hit.x, c.snap_hit.y), (20, 0))
guias, tomadas = c._geocad_guias
assert len(guias) == 2 and tomadas == [H]
c.tomar()
c.on_hover(-40.0, 60.0)                                        # lejos de todo: queda
assert cerca((c.snap_hit.x, c.snap_hit.y), (20, 0)) and c._geocad_guias[1] == [H, V]
c.on_hover(5.0, 3.1); c.tomar()                                # P reemplaza a H (la más vieja)
assert c._geocad_tomadas.lista == [V, P]
c.on_hover(-40.0, 60.0)
assert cerca((c.snap_hit.x, c.snap_hit.y), (20, 3))
# dos paralelas tomadas: sin punto (y lo de IngeCAD queda)
c = Controlador(frozenset({"APP"}))
c.on_hover(5.0, 0.2); c.tomar(); c.on_hover(5.0, 3.1); c.tomar()
from core.snap import SnapHit
real = SnapHit(1.0, 1.0, "INT")
c.on_hover(-40.0, 60.0, hit=real)
assert c.snap_hit is real
# lo que el comando está dibujando también se toma
c = Controlador(frozenset({"APP"}))
c.tool.dibujado = [(100.0, 100.0, 110.0, 110.0)]
c.on_hover(105.0, 105.1); c.tomar()
c.on_hover(20.1, 10.0)
assert cerca((c.snap_hit.x, c.snap_hit.y), (20, 20))

# APP entre las activas (sin el menú): otra referencia más cerca gana
c = Controlador(None)
c.activas = frozenset({"END", "APP"})
c.on_hover(5.0, 0.2); c.tomar()
fin = SnapHit(20.0, 5.0, "END")
c.on_hover(20.0, 5.1, hit=fin)
assert c.snap_hit is fin
c.on_hover(20.1, 10.0)
assert c.snap_hit.kind == "APP"
# PER entre las activas: como en IngeCAD (sin tomar)
c = Controlador(None)
c.activas = frozenset({"PER"})
c.on_hover(5.0, 0.2)
assert c.snap_hit is None and getattr(c, "_geocad_tomadas", None) is None
# otra referencia de una vez (END): nada de GeoCAD
c = Controlador(frozenset({"END"}))
c.on_hover(5.0, 0.2)
assert c.snap_hit is None and c._geocad_guias == ([], [])
# módulo apagado: nada
modulos.guardar("ingecad", {"referencias": False})
c = Controlador(frozenset({"APP"}))
c.on_hover(5.0, 0.2)
assert c.snap_hit is None and not c.reloj.andando
modulos.guardar("ingecad", {"referencias": True})


# con el punto (clear_tracking de IngeCAD) se sueltan las tomadas
class Limpia:
    def clear_tracking(self):
        self.limpio = True


Limpia.clear_tracking = GI._envolver_clear_tracking(Limpia.clear_tracking)
x = Limpia(); x._geocad_tomadas = G.Tomadas("APP"); x._geocad_guias = ([1], [2])
x._geocad_reloj = Reloj(); x._geocad_reloj.andando = True
x.clear_tracking()
assert x.limpio and x._geocad_tomadas is None and x._geocad_guias == ([], [])
assert not x._geocad_reloj.andando


# el dibujo: las tomadas en verde y las guías de puntos
class Pintor:
    def __init__(self):
        self.lineas, self.plumas = [], []

    def save(self): pass

    def restore(self): pass

    def setPen(self, p):
        self.plumas.append(p)

    def drawLine(self, a, b):
        self.lineas.append((a, b, self.plumas[-1]))


class Vista:
    def _space_to_screen(self, x, y):
        return (x * 2.0, -y * 2.0)


qt = (lambda color, ancho, estilo="solida": (color, ancho, estilo),
      lambda *rgb: rgb, lambda x, y: (x, y),
      type("Qt", (), {"DotLine": "puntos"}))
d = type("D", (), {})()
assert GI.dibujar_guias(Vista(), Pintor(), d, qt) == 0
d._geocad_guias = ([((10.0, 0.0), (20.0, 0.0))], [H])
pintor = Pintor()
assert GI.dibujar_guias(Vista(), pintor, d, qt) == 2
(a, b, pluma_t), (c_, d_, pluma_g) = pintor.lineas
assert (a, b) == ((0.0, -0.0), (20.0, -0.0)) and pluma_t[2] == "solida"
assert (c_, d_) == ((20.0, -0.0), (40.0, -0.0)) and pluma_g == (GI.COLOR_GUIA, 2, "puntos")

GI.instalar()                                                   # sin ventana: no hace nada
print("TODO OK")
