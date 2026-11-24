"""UNIR (JOIN, J) en QGIS (3.87.0), sin Qt: las líneas que comparten un extremo
quedan en una sola polilínea y conservan los datos del objeto MAYOR: el más
largo (Criterio = Longitud, de fábrica) o el de más tramos (Criterio = Tramos).
Botón en «Yaguá Edición» delante de DESCOMP (también en una barra guardada).
Lo que pasa en la capa (datos, borrados, U) lo prueba
ventana/banco_unir_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, importlib.util
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"
spec = importlib.util.spec_from_file_location("unir", GEOCAD / "dibujo" / "unir.py")
U = importlib.util.module_from_spec(spec); spec.loader.exec_module(U)

# ---- 1. el más largo manda; el de más tramos, con Criterio = Tramos -------------------------
largo = [(0, 0), (10, 0)]                         # 10 m, 1 tramo
quebrada = [(10, 0), (10, 2), (12, 2), (12, 4)]   # 6 m, 3 tramos
corta = [(-3, 0), (0, 0)]                         # 3 m, 1 tramo (al revés: se da vuelta)
res, cad = U.unir({"A": [largo], "B": [quebrada], "C": [corta]})
assert cad == [("A", ["A", "B", "C"])]
assert res == {"A": [[(-3, 0), (0, 0), (10, 0), (10, 2), (12, 2), (12, 4)]], "B": [], "C": []}, res
res, cad = U.unir({"A": [largo], "B": [quebrada], "C": [corta]}, U.TRAMOS)
assert cad[0][0] == "B" and res["B"][0][0] == (-3, 0) and res["A"] == [] and res["C"] == []
print("ok manda el más largo (o el de más tramos)")

# ---- 2. sentidos: extremos al revés, por los dos lados ---------------------------------------
res, _ = U.unir({1: [[(5, 0), (0, 0)]], 2: [[(5, 0), (5, 5)]], 3: [[(-2, 0), (0, 0)]]})
assert res[1] == [[(5, 5), (5, 0), (0, 0), (-2, 0)]] or res[1] == [[(-2, 0), (0, 0), (5, 0), (5, 5)]], res
print("ok extremos en cualquier sentido")

# ---- 3. se cierra: cuadrado de 4 líneas; una cerrada no se toca ------------------------------
res, cad = U.unir({1: [[(0, 0), (10, 0)]], 2: [[(10, 0), (10, 10)]], 3: [[(0, 10), (10, 10)]],
                   4: [[(0, 0), (0, 10)]]})
p = res[1][0]
assert len(cad) == 1 and p[0] == p[-1] and len(p) == 5 and res[2] == res[3] == res[4] == []
anillo = [(20, 0), (30, 0), (30, 10), (20, 0)]
res, cad = U.unir({1: [anillo], 2: [[(20, 0), (15, 0)]]})
assert cad == [] and res == {}
print("ok se cierra; una cerrada no se une")

# ---- 4. sueltas y cruces ------------------------------------------------------------------
res, cad = U.unir({1: [[(0, 0), (1, 0)]], 2: [[(5, 5), (6, 6)]]})
assert res == {} and cad == []                                   # no se tocan
# cruce en T: sigue por la mayor, la otra queda como estaba
res, cad = U.unir({1: [[(0, 0), (10, 0)]], 2: [[(10, 0), (20, 0)]], 3: [[(10, 0), (10, 3)]]})
assert cad == [(1, [1, 2])] and res == {1: [[(0, 0), (10, 0), (20, 0)]], 2: []} and 3 not in res
# dos grupos que no se tocan entre sí: dos uniones, cada una con su mayor
res, cad = U.unir({1: [[(0, 0), (10, 0)]], 2: [[(10, 0), (11, 0)]],
                   3: [[(50, 0), (52, 0)]], 4: [[(52, 0), (60, 0)]]})
assert sorted(cad) == [(1, [1, 2]), (4, [4, 3])] and res[2] == res[3] == []
print("ok sueltas, cruce en T y grupos aparte")

# ---- 5. tolerancia: casi iguales (snap) sí, a 1 cm no -------------------------------------
x, y = 5500000.0, 6950000.0                                      # UTM / POSGAR
res, cad = U.unir({1: [[(x, y), (x + 10, y)]], 2: [[(x + 10 + 1e-5, y), (x + 20, y)]]})
assert len(cad) == 1
res, cad = U.unir({1: [[(x, y), (x + 10, y)]], 2: [[(x + 10.01, y), (x + 20, y)]]})
assert cad == []
print("ok tolerancia (0,01 mm sí, 1 cm no)")

# ---- 6. multiparte: la parte que no se une queda en su objeto -----------------------------
res, cad = U.unir({1: [[(0, 0), (10, 0)], [(100, 100), (101, 100)]], 2: [[(10, 0), (12, 0)]]})
assert cad == [(1, [1, 2])] and res[1] == [[(0, 0), (10, 0), (12, 0)], [(100, 100), (101, 100)]]
assert res[2] == []
print("ok multiparte")

# ---- 7. la orden, el botón y la barra guardada --------------------------------------------
src = (GEOCAD / "dibujo" / "edit_commands.py").read_text(encoding="utf-8")
assert "('JOIN', ('UNIR', 'UNE', 'J'), JoinCommand, 'UNIR'," in src
assert "OPT_CRITERIO = ('CR', 'CRITERIO', 'CRITERION')" in src
assert (GEOCAD / "dibujo" / "icons" / "join.svg").is_file()
assert "('BREAKATPOINT', 'BREAK', 'JOIN', 'EXPLODE')" in (GEOCAD / "dibujo" / "plugin.py").read_text(encoding="utf-8")
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import botones
edicion = dict(botones.DEFECTO["qgis"])["Yaguá Edición"]
assert edicion.index("dibujo:join") == edicion.index("dibujo:explode") - 1
assert "dibujo:join" in botones.TEMA_BANCO["qgis"]["Edición"]
hechas = [m for m in botones.MIGRACIONES["qgis"] if m != "unir"]   # 3.89.0: ya no es la última
crudo = {"categorias": [{"nombre": "Mía", "botones": ["dibujo:break", "dibujo:explode"]}], "migraciones": hechas}
assert botones._migrar("qgis", crudo)
assert crudo["categorias"][0]["botones"] == ["dibujo:break", "dibujo:join", "dibujo:explode"]
assert not botones._migrar("qgis", crudo)
print("ok orden, ícono, botón y barra guardada")
print("TODO OK UNIR QGIS")
