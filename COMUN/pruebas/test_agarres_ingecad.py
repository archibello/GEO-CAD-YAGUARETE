"""Agarres de vértices en IngeCAD (módulo «Agarres de vértices», 3.70): pedido de Fernando del
05/11/2026. Sin Qt: el módulo, las decisiones y los vértices. Con la ventana real, los clics y las
teclas: COMUN/pruebas/ventana/banco_agarres_ventana.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin
from core.select import entity_grips

RAIZ = Path(__file__).resolve().parents[2]
lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
A = import_module("ingecad_plugin_geocad.agarres_ingecad")
modulos = import_module("ingecad_plugin_geocad.modulos")

# ================================================================ el módulo
m = [x for x in modulos.catalogo("ingecad") if x.clave == "agarres"]
assert m and m[0].defecto and m[0].cambia_programa and not m[0].requiere
assert modulos.activo("ingecad", "agarres")
modulos.guardar("ingecad", {"agarres": False})
assert not modulos.activo("ingecad", "agarres")
modulos.guardar("ingecad", {"agarres": True})

# ================================================================ qué hace el clic
for rol in ("vertex", "end"):
    assert A.accion_clic(rol, False, False, False) == "mover"
    assert A.accion_clic(rol, True, False, False) == "mover_marcados"
    assert A.accion_clic(rol, False, True, False) == "marcar"
    assert A.accion_clic(rol, True, True, False) == "desmarcar"
    assert A.accion_clic(rol, False, False, True) == "mover"
assert A.accion_clic("mid", False, False, False) == "mover"      # el tramo, como en AutoCAD
assert A.accion_clic("mid", False, False, True) == "agregar"
assert A.accion_clic("mid", False, True, False) == "nada"
for rol in ("center", "quadrant", "corner", "dim_text"):         # los demás siguen de IngeCAD
    assert A.accion_clic(rol, False, True, False) == "mover"
    assert A.accion_clic(rol, False, False, True) == "mover"

# ================================================================ los que comparten lugar
G = [(0, 0, "vertex", "a", 0), (0, 0, "end", "b", 1), (0, 0, "center", "c", 0), (0, 0, "mid", "d", 5),
     (0.0000001, 0, "vertex", "e", 0), (0.01, 0, "vertex", "f", 0), (1, 1, "mid", "a", 3), (1, 1, "mid", "b", 4)]
assert A.coincidentes(G, [G[0]]) == [G[1], G[4]]                 # ni el centro, ni el medio, ni el lejano
assert A.coincidentes(G, [G[6]]) == [G[7]]
assert A.coincidentes(G, [G[0], G[1]]) == [G[4]]                 # sin contarse a sí mismos
assert A.coincidentes(G, []) == []
assert A.coincidentes(G, [G[2]]) == []                           # un centro no arrastra a nadie
mismo = [(5, 5, "vertex", "a", 0), (5, 5, "vertex", "a", 3)]     # un anillo abierto: sus dos extremos
assert A.coincidentes(mismo, [mismo[0]]) == [mismo[1]]

# ================================================================ agregar y borrar
doc = ezdxf.new()
msp = doc.modelspace()


def puntos(e):
    return [tuple(round(float(v), 3) for v in p) for p in e.get_points("xy")]


p = msp.add_lwpolyline([(0, 0, 1, 2, 0), (10, 0, 3, 4, 0), (10, 10)])
assert A.tramo_recto(p, 3) and A.tramo_recto(p, 4)
assert A.agregar_vertice(p, 3, (5, 0)) == 1                      # el agarre del medio del primer tramo
assert puntos(p) == [(0, 0), (5, 0), (10, 0), (10, 10)]
assert list(p.get_points("xyseb")[1])[2:] == [1, 2, 0]           # con el ancho del tramo
c = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)], close=True)
medios = [i for i, g in enumerate(entity_grips(c)) if g[2] == "mid"]
assert medios == [3, 4, 5]                                       # cerrada: también el tramo de cierre
assert A.agregar_vertice(c, 5, (5, 5)) == 3
assert puntos(c)[-1] == (5, 5) and c.closed
curva = msp.add_lwpolyline([(0, 0, 0, 0, 1.0), (10, 0), (20, 0)])
assert not A.tramo_recto(curva, 3) and A.tramo_recto(curva, 4)
assert not A.tramo_recto(curva, 0) and not A.tramo_recto(curva, 9)   # fuera de los medios

q = msp.add_lwpolyline([(0, 0), (1, 0), (2, 0), (3, 0)])
assert A.se_puede_borrar(q, [1, 2]) and not A.se_puede_borrar(q, [0, 1, 2])
assert A.se_puede_borrar(q, [1, 1, 2])                           # los repetidos cuentan una vez
A.borrar_vertices(q, [1, 2, 1])
assert puntos(q) == [(0, 0), (3, 0)]
assert not A.se_puede_borrar(c, [0, 1])                          # cerrada: quedan dos
assert A.se_puede_borrar(c, [0])
assert not A.se_puede_borrar(msp.add_line((0, 0), (1, 1)), [0])  # sólo polilíneas

# ================================================================ lo conecta y se apaga sin rastro
fuente = (RAIZ / "INGECAD/codigo/geocad/__init__.py").read_text(encoding="utf-8")
assert fuente.count("agarres_ingecad.aplicar(") == 2             # al abrir y al cambiar los módulos


class Cosa:
    def m(self):
        return "de la clase"


class Ventana:
    def __init__(self):
        self.tools, self.viewport = Cosa(), Cosa()


NOMBRES = ("begin_grip_drag", "update_grip_drag", "finish_grip_drag", "grip_overlay_entities",
           "on_text", "delete_selection")
v = Ventana()
A.aplicar(v)
assert all(n in vars(v.tools) for n in NOMBRES) and "_draw_grips" in vars(v.viewport)
assert not any(n in vars(v.tools) for n in ("cancel", "grip_at"))   # esos son del recorte de imágenes
A.aplicar(v)
modulos.guardar("ingecad", {"agarres": False})
v.tools._geocad_agarres = object()
A.aplicar(v)
assert not vars(v.tools) and not vars(v.viewport)
v.tools.on_text = "de otro"                                      # lo ajeno no se saca
A.aplicar(v)
assert vars(v.tools) == {"on_text": "de otro"}
A.aplicar(None)
ag = (RAIZ / "INGECAD/codigo/geocad/agarres_ingecad.py").read_text(encoding="utf-8")
assert "window.osnap_override_menu()" in ag                      # el menú de IngeCAD, para el agarre tomado
assert "window.viewport.removeEventFilter(filtro)" in ag         # apagado, sale el filtro
modulos.guardar("ingecad", {"agarres": True})

print("TODO OK test_agarres_ingecad")
