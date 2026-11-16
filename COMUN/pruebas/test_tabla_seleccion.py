"""Tabla de atributos con muchas parcelas seleccionadas (3.81.1).

Fernando, 15/11/2026: con 12 801 parcelas y la tabla abierta, seleccionar
todo dejaba IngeCAD «no responde». Sin Qt se prueba lo que hace la cuenta:
* tramos_de_filas: las filas seleccionadas en tramos seguidos (la tabla las
  marca de una vez, no de a una);
* el resumen arma el conjunto de seleccionados una sola vez (antes, una por
  fila: ~8 s con 12 801).
Lo que hace Qt se mide en ventana/banco_tabla_seleccion_ventana.py.
"""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, time, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
from core.plugins import load_plugin

RAIZ = Path(__file__).resolve().parents[2]
lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
D = import_module("ingecad_plugin_geocad.datos")


def filas(*fids):
    return [types.SimpleNamespace(fid=f) for f in fids]


# ------------------------------------------------------------- tramos
T = D.tramos_de_filas
assert T([], {1}) == []
assert T(filas(1, 2, 3), set()) == []
assert T(filas(1, 2, 3), {1, 2, 3}) == [(0, 2)]
assert T(filas(5, 1, 2, 9, 3), {1, 2, 3}) == [(1, 2), (4, 4)]
assert T(filas(1, 2, 3, 4), [2, 4]) == [(1, 1), (3, 3)]            # también con lista
assert T(filas(1, 2, 3, 4), frozenset({1, 4})) == [(0, 0), (3, 3)]
N = 12801
muchas = filas(*range(N))
assert T(muchas, set(range(N))) == [(0, N - 1)]
assert len(T(muchas, set(range(0, N, 2)))) == 6401
print("tramos de filas: bien")

# ------------------------------------------------------------- resumen
estado = D.TableState.__new__(D.TableState)
estado.rows = [types.SimpleNamespace(fid=i, pending=False, new=False, connected=True) for i in range(N)]
estado.data = types.SimpleNamespace(rows=estado.rows)
estado.measure = "Área"
estado._measures = {i: 2.0 for i in range(N)}
t0 = time.monotonic()
texto = estado.summary(list(range(N)))           # lista, como llega del dibujo
dt = time.monotonic() - t0
assert f"{N} de {N} registros" in texto and f"{N} seleccionados" in texto, texto
assert "25 602.00" in texto, texto
assert dt < 0.5, f"el resumen tarda {dt:.2f} s con {N} (antes ~8 s)"
assert "1 seleccionados" in estado.summary({7})
assert "seleccionados" not in estado.summary(())
print(f"resumen con {N} seleccionados: {dt:.3f} s, bien")

# ------------------------------------------------------------- la tabla usa lo rápido
fuente = (RAIZ / "INGECAD" / "codigo" / "geocad" / "tabla.py").read_text(encoding="utf-8")
assert "tramos_de_filas(state.rows, fids)" in fuente
assert "changed.connect(self._dibujo_cambio)" in fuente      # no recalcula con cada aviso
assert "SelectionFlag.ClearAndSelect" not in fuente.split("def sync_from_drawing")[1].split("def _firma_sync")[0]
print("TODO OK")
