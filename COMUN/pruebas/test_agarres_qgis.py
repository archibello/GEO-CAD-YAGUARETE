"""Agarres de vértices en el cursor de GeoCAD (módulo «Agarres de vértices», 3.69): pedido de
Fernando del 05/11/2026. Sin Qt: el módulo, las decisiones y que Dibujo los conecta. Con QGIS de
verdad: COMUN/pruebas/ventana/banco_agarres_qgis_real.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ / "QGIS" / "codigo")]
from geocad import agarres as A, modulos

# ================================================================ el módulo
m = [x for x in modulos.catalogo("qgis") if x.clave == "agarres"]
assert m and m[0].defecto and m[0].cambia_programa and m[0].requiere == "dibujo"
assert [x for x in modulos.catalogo("ingecad") if x.clave == "agarres"]         # desde 3.70, también IngeCAD (test_agarres_ingecad)
modulos.guardar("qgis", {"dibujo": False})
assert not modulos.activo("qgis", "agarres")
modulos.guardar("qgis", {"dibujo": True, "agarres": False})
assert not modulos.activo("qgis", "agarres")
modulos.guardar("qgis", {"agarres": True})

# ================================================================ qué agarre
P = [(0, 0), (10, 0), (10.5, 0)]
assert A.mas_cercano(P, 0.5, 0.5, 1) == 0
assert A.mas_cercano(P, 10.4, 0, 1) == 2                # el más cercano, no el primero
assert A.mas_cercano(P, 5, 5, 1) is None
assert A.mas_cercano([], 0, 0, 1) is None
assert A.mas_cercano(P, 1, 0, 1) == 0                   # en el borde de la tolerancia, sí

# ================================================================ qué hace el clic
c = A.accion_clic
assert c(False, False, False) == "mover"
assert c(False, True, False) == "mover_marcados"
assert c(True, False, False) == "insertar"
assert c(False, False, True) == "marcar"
assert c(False, True, True) == "desmarcar"
assert c(True, False, True) == "nada"                   # el del medio no se marca

# ================================================================ borrar
assert A.indices_para_borrar({(0, 0): [0, 4], (1, 1): [2]}) == [2, 0]    # el cierre, una vez
assert A.indices_para_borrar({(0, 0): [1], (1, 1): [3], (2, 2): [2]}) == [3, 2, 1]
assert A.conserva_forma([1], [1])
assert A.conserva_forma([2, 1], [2, 1])
assert not A.conserva_forma([2], [1])                   # perdió un agujero
assert not A.conserva_forma([1, 1], [1])                # perdió una parte
assert not A.conserva_forma([1], [])                    # quedó vacío

# ================================================================ Dibujo los conecta
qd = RAIZ / "QGIS/codigo/geocad/dibujo"
qp = (qd / "plugin.py").read_text(encoding="utf-8")
assert "_modulo('agarres')" in qp and "ag.quitar()" in qp
cm = (qd / "commands.py").read_text(encoding="utf-8")
assert "self.agarres.clic(pt, shift)" in cm and "self.agarres.luego()" in cm
mt = (qd / "maptool.py").read_text(encoding="utf-8")
assert "self.mgr.agarres.borrar_marcados()" in mt
ag = (qd / "agarres.py").read_text(encoding="utf-8")
assert "commitChanges" not in ag                        # nunca guarda solo
assert "self.mgr.last_cmd = ultimo" in ag               # Intro repite el último de verdad
cu = (RAIZ / "QGIS/codigo/geocad/cursor_defecto.py").read_text(encoding="utf-8")
assert '"actionVertexTool"' in cu                       # Esc vuelve desde Vértices

assert "or not layer.isEditable()" in ag and "capa.editingStopped" in ag  # sólo en edición (3.70.3)

print("TODO OK test_agarres_qgis")
