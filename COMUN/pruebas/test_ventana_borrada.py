"""3.84.1 Una ventana gráfica borrada no queda como fantasma (módulo Papel).

Fernando, 16/11/2026, «Tarjeta de presentacion.dwg», Layout4: «no me deja
borrar el viewport que viene por defecto». El primer Supr (o BORRA) SÍ la
borraba (el autoguardado ya no la tenía), pero IngeCAD no la sacaba de su
índice de selección: un comando que toca una ventana va por la regeneración
y se saltea el parche del índice. Un clic en el borde la volvía a elegir y el
segundo borrado fallaba callado (ezdxf: «list.remove(x): x not in list»).
Medido con la ventana real de IngeCAD 0.8.0, también sin GeoCAD
(COMUN/pruebas/ventana/banco_ventana_borrada.py).

Sin Qt: un controlador de mentira que hace lo mismo que IngeCAD en esa rama
(ejecuta el comando y no toca el índice) y el GeometryIndex de IngeCAD.
"""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
from core.plugins import load_plugin
from core.document import Document
from core.select import GeometryIndex
from core.actions import EraseCommand
from core import layouts as L

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
P = import_module("ingecad_plugin_geocad.papel")
M = import_module("ingecad_plugin_geocad.modulos")
assert P.activo()


class Controlador:
    """Lo que hace ToolController._execute_command de IngeCAD con un comando
    que toca una ventana: lo ejecuta y pide regenerar, sin tocar el índice."""

    def __init__(self, document):
        self.document = document
        self.index = GeometryIndex(document)
        self.snap_engine = None
        self.selection = set()
        self.ejecutados = []

    def _execute_command(self, command):
        command.do(self.document)
        self.ejecutados.append(command)


def hoja():
    doc = Document.new()
    doc.doc.modelspace().add_circle((10, 5), 3)
    doc.active_layout = "Layout1"
    psp = doc.doc.layouts.get("Layout1")
    vp = psp.add_viewport(center=(100, 100), size=(80, 60),
                          view_center_point=(10, 5), view_height=20)
    c = Controlador(doc)
    return doc, psp, vp, c


BORDE = (60.0, 100.0)            # el lado izquierdo de la ventana


def flotantes(psp):
    return [e for e in psp if e.dxftype() == "VIEWPORT" and e.dxf.get("id", 0) != 1]


# ------------------------------------------------------------- 1. el fantasma (IngeCAD solo)
doc, psp, vp, c = hoja()
h = vp.dxf.handle
assert c.index.pick(BORDE, 2.0) == h, "el borde elige la ventana"
c.selection = {h}
c._execute_command(EraseCommand([vp]))              # sin el gancho: como IngeCAD
assert not flotantes(psp), "el primer borrado la saca del dibujo"
assert c.index.pick(BORDE, 2.0) == h, "IngeCAD: el borde la sigue eligiendo (fantasma)"
try:
    EraseCommand([vp]).do(doc)
    falla = None
except ValueError as e:
    falla = e
assert falla is not None, "el segundo borrado falla (lo que veía Fernando: nada cambia)"
print("ok fantasma reproducido (sin GeoCAD)")

# ------------------------------------------------------------- 2. con el gancho de GeoCAD
doc, psp, vp, c = hoja()
h = vp.dxf.handle
ventana = types.SimpleNamespace(tools=c)
P.enganchar_ventanas(ventana)
assert getattr(vars(c).get("_execute_command"), "_geocad_papel", False)
c.selection = {h}
borrar = EraseCommand([vp])
c._execute_command(borrar)
assert c.ejecutados == [borrar], "el comando de IngeCAD corre una sola vez"
assert not flotantes(psp)
assert P.ventanas_borradas(borrar) == [h]
assert c.index.pick(BORDE, 2.0) is None, "el borde ya no elige nada"
assert h not in c.selection
print("ok sin fantasma")

# deshacer: vuelve la ventana y se puede elegir y borrar de nuevo
borrar.undo(doc)
c.index.add_entities([vp])                          # lo que hace IngeCAD al deshacer
assert flotantes(psp) and c.index.pick(BORDE, 2.0) == h
c.selection = {h}
c._execute_command(EraseCommand([vp]))
assert not flotantes(psp) and c.index.pick(BORDE, 2.0) is None
print("ok deshacer y borrar otra vez")

# ------------------------------------------------------------- 3. lo demás no se toca
doc, psp, vp, c = hoja()
P.enganchar_ventanas(types.SimpleNamespace(tools=c))
linea = psp.add_line((0, 0), (40, 0))
c.index.invalidate()
hv = vp.dxf.handle
c.selection = {hv, linea.dxf.handle}
c._execute_command(EraseCommand([linea]))
assert c.index.pick(BORDE, 2.0) == hv, "una ventana que sigue en la hoja se sigue eligiendo"
assert hv in c.selection
# un comando compuesto (sus pasos en .commands) también
compuesto = types.SimpleNamespace(commands=[EraseCommand([vp])],
                                  do=lambda d: [s.do(d) for s in compuesto.commands])
c._execute_command(compuesto)
assert c.index.pick(BORDE, 2.0) is None and hv not in c.selection
# RemoveViewportCommand (la ventana se destruye): por sus removed_handles
doc, psp, vp, c = hoja()
P.enganchar_ventanas(types.SimpleNamespace(tools=c))
hv = vp.dxf.handle
quitar = L.RemoveViewportCommand(vp, "Layout1")
c._execute_command(quitar)
assert not flotantes(psp) and c.index.pick(BORDE, 2.0) is None
# si IngeCAD ya la sacó del índice (una versión que lo arregle), no pasa nada
assert P.olvidar_ventanas(c, [hv]) == 1 and c.index.pick(BORDE, 2.0) is None
print("ok lo demás igual")

# ------------------------------------------------------------- 4. módulo apagado: como venía
M.guardar("ingecad", {"papel": False})
assert not P.activo()
P.enganchar_ventanas(types.SimpleNamespace(tools=c))
assert "_execute_command" not in vars(c), "apagado, el gancho se saca"
M.guardar("ingecad", {"papel": True})
P.enganchar_ventanas(types.SimpleNamespace(tools=c))
P.enganchar_ventanas(types.SimpleNamespace(tools=c))   # dos veces: un solo gancho
c.ejecutados = []
c._execute_command(EraseCommand([psp.add_line((0, 0), (1, 1))]))
assert len(c.ejecutados) == 1
# sin controlador o sin el método, no hace nada
P.enganchar_ventanas(types.SimpleNamespace())
P.enganchar_ventanas(types.SimpleNamespace(tools=object()))
print("ok apagado")

print("TODO OK VENTANA BORRADA")
