"""Objetos tapados con clics repetidos (módulo «Objetos tapados», 3.68): pedido de Fernando
del 05/11/2026. Sin Qt: el módulo, la pila y que Dibujo la conecta sin escribir en la capa.
Con QGIS de verdad: COMUN/pruebas/ventana/banco_pila_qgis_real.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ / "QGIS" / "codigo")]
from geocad import modulos
from geocad.pila import Pila

# ================================================================ el módulo
m = [x for x in modulos.catalogo("qgis") if x.clave == "apilados"]
assert m and m[0].defecto and m[0].cambia_programa and m[0].requiere == "dibujo"
assert not [x for x in modulos.catalogo("ingecad") if x.clave == "apilados"]    # sólo QGIS
assert modulos.activo("qgis", "apilados")
modulos.guardar("qgis", {"dibujo": False})
assert not modulos.activo("qgis", "apilados")
modulos.guardar("qgis", {"dibujo": True, "apilados": False})
assert not modulos.activo("qgis", "apilados")
modulos.guardar("qgis", {"apilados": True})

# ================================================================ pasar de uno a otro
ABC = [1, 2, 3]
p = Pila()
assert not p.activa() and p.actual() is None
assert p.clic("L", 10, 10, 1, ABC, set()) == (1, None) and p.activa()
assert p.clic("L", 10.5, 9.5, 1, ABC, {1}) == (2, 1)        # dentro de la tolerancia
assert p.clic("L", 10, 10, 1, ABC, {2}) == (3, 2) and p.actual() == 3
assert p.clic("L", 10, 10, 1, ABC, {3}) == (1, 3)           # da la vuelta

# la lista queda la del primer clic, aunque en el borde cambie lo que se alcanza
p = Pila()
p.clic("L", 0, 0, 1, ABC, set())
assert p.clic("L", 1, 0, 1, [1, 2], {1}) == (2, 1) and p.fids == ABC

# otro lugar u otra capa: empieza de nuevo y no suelta nada
p = Pila()
p.clic("L", 0, 0, 1, ABC, set())
assert p.clic("L", 50, 50, 1, [7, 8], {1}) == (7, None)
assert p.clic("M", 50, 50, 1, [9, 8], {1, 7}) == (9, None)
assert p.clic("M", 90, 90, 1, [], {1, 7, 9}) == (None, None) and not p.activa()

# un solo objeto: se elige y no queda pila; repetir el clic no suelta nada
p = Pila()
assert p.clic("L", 0, 0, 1, [5], set()) == (5, None) and not p.activa()
assert p.clic("L", 0, 0, 1, [5], {5}) == (5, None)

# lo que ya estaba designado antes de empezar no se suelta
p = Pila()
assert p.clic("L", 0, 0, 1, ABC, {1}) == (1, None)
assert p.clic("L", 0, 0, 1, ABC, {1}) == (2, None)          # 1 sigue
assert p.clic("L", 0, 0, 1, ABC, {1, 2}) == (3, 2)          # 2 lo eligió la pila
assert p.clic("L", 0, 0, 1, ABC, {1, 3}) == (1, 3)
assert p.clic("L", 0, 0, 1, ABC, {1}) == (2, None)          # al pasar de nuevo por 1, sigue

# olvidar (Esc, otro comando, otra herramienta)
p = Pila()
p.clic("L", 0, 0, 1, ABC, set())
p.olvidar()
assert not p.activa() and p.clic("L", 0, 0, 1, ABC, {1}) == (1, None)

# Mayús + clic: el designado, aunque esté tapado
p = Pila()
assert p.quitar(ABC, {3}) == 3 and not p.activa()
assert p.quitar(ABC, set()) == 1
assert p.quitar([], {3}) is None

# ================================================================ Dibujo lo conecta y no escribe
qd = RAIZ / "QGIS/codigo/geocad/dibujo"
qp = (qd / "plugin.py").read_text(encoding="utf-8")
assert "_modulo('apilados')" in qp and "self.mgr.pila = Pila()" in qp
cm = (qd / "commands.py").read_text(encoding="utf-8")
assert "self.pila = None" in cm and "if self.pila is None:" in cm
assert "pick_feature(self.canvas, io, layer, pt)[0], None" in cm      # apagado: el de siempre
ek = (qd / "editkit.py").read_text(encoding="utf-8")
assert "self.mgr.elegir_en_punto(" in ek
mt = (qd / "maptool.py").read_text(encoding="utf-8")
assert "def show_pila" in mt and "self.rb_pila, self.rb_pila_pts" in mt
fuente = (RAIZ / "QGIS/codigo/geocad/pila.py").read_text(encoding="utf-8")
codigo = fuente.split('"""', 2)[2]
for prohibido in ("startEditing", "changeGeometry", "changeAttributeValue", "setRenderer", "commitChanges"):
    assert prohibido not in codigo, prohibido

print("TODO OK test_pila_qgis")
