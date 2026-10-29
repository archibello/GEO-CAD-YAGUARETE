"""CHAFLÁN con Ochava en Dibujo de QGIS (3.57.0), sin Qt: la cuenta del núcleo
(ochava.py, la misma de IngeCAD), el largo guardado y compartido, el bisel
entre dos líneas (lado del clic, No recortar, esquina), la ochava en la
esquina de un polígono, la opción Polilínea y el botón en la barra y en
«Yaguá Edición». Lo que se ve en QGIS lo prueba
ventana/banco_chaflan_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, importlib.util, json, math
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


G = cargar("geomops", GEOCAD / "dibujo" / "geomops.py")
O = cargar("ochava", ROOT / "COMUN" / "nucleo" / "ochava.py")


def cerca(a, b, tol=1e-9):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def todos_cerca(xs, ys):
    return len(xs) == len(ys) and all(cerca(a, b) for a, b in zip(xs, ys))


R2 = math.sqrt(2.0)

# ---- 1. la cuenta del núcleo: Ochava A = B, Distancia, Ángulo ------------------------------
d = O.distancias("O", math.pi / 2, ochava=5.0)
assert abs(d[0] - 5.0 / R2) < 1e-12 and d[0] == d[1]              # 3,5355 en esquina a 90°
d = O.distancias("O", math.radians(60), ochava=5.0)
assert abs(d[0] - 5.0) < 1e-12 and d[0] == d[1]                   # a 60°: triángulo equilátero
assert O.distancias("O", math.pi / 2, ochava=0.0) == (0.0, 0.0)
assert O.distancias("D", 1.0, dist1=2.0, dist2=3.0) == (2.0, 3.0)
d = O.distancias("A", math.pi / 2, largo=2.0, angulo=45.0)
assert abs(d[0] - 2.0) < 1e-12 and abs(d[1] - 2.0) < 1e-12
assert math.isinf(O.distancias("A", math.pi / 2, largo=2.0, angulo=100.0)[1])   # no llega
# la misma cuenta en los dos programas (copias del núcleo al día)
for lado in ("QGIS", "INGECAD"):
    assert (ROOT / lado / "codigo" / "geocad" / "ochava.py").read_bytes() == \
        (ROOT / "COMUN" / "nucleo" / "ochava.py").read_bytes(), lado
src_ing = (ROOT / "INGECAD" / "codigo" / "geocad" / "chaflan.py").read_text(encoding="utf-8")
assert "_ochava.distancias(" in src_ing
print("ok cuenta de Ochava, Distancia y Ángulo en el núcleo")

# ---- 2. el largo guardado, compartido con IngeCAD ------------------------------------------
assert O.leer_ochava() == 0.0
O.guardar_ochava(5.0)
arch = Path(HOME) / ".config" / "geocad" / "chaflan.json"
assert json.loads(arch.read_text())["ochava"] == 5.0 and O.leer_ochava() == 5.0
arch.write_text("{roto")
assert O.leer_ochava() == 0.0
print("ok largo de ochava guardado en ~/.config/geocad/chaflan.json")


def ochava(L):
    return lambda t: O.distancias("O", t, ochava=L)


# ---- 3. dos líneas: bisel con A = B, del lado del clic (como en IngeCAD) -------------------
def dos(l1, p1, l2, p2, dists, trim=True):
    r = G.chamfer_two(l1, p1, l2, p2, dists, trim)
    assert "lines" in r, r
    return r["lines"][0], r["lines"][1], r["bevel"]


h = [(0.0, 0.0), (10.0, 0.0)]
v = [(10.0, 0.0), (10.0, 10.0)]
n1, n2, b = dos(h, (5.0, 0.0), v, (10.0, 5.0), ochava(5.0))
c = 5.0 / R2
assert todos_cerca(n1, [(0.0, 0.0), (10.0 - c, 0.0)])
assert todos_cerca(n2, [(10.0, c), (10.0, 10.0)])
assert todos_cerca(b, [(10.0 - c, 0.0), (10.0, c)]) and abs(G.dist(*b) - 5.0) < 1e-9
# los dos ángulos iguales: 135° en esquina a 90°
ang = lambda p, q, r: math.degrees(math.acos(G.dot(G.unit(G.sub(p, q)), G.unit(G.sub(r, q)))))
assert abs(ang(n1[0], b[0], b[1]) - 135) < 1e-9 and abs(ang(b[0], b[1], n2[1]) - 135) < 1e-9
# una X: queda el cuadrante tocado
x1 = [(-10.0, 0.0), (10.0, 0.0)]
x2 = [(0.0, -10.0), (0.0, 10.0)]
n1, n2, b = dos(x1, (-5.0, 0.0), x2, (0.0, 5.0), ochava(2.0))
c = 2.0 / R2
assert todos_cerca(n1, [(-10.0, 0.0), (-c, 0.0)]) and todos_cerca(n2, [(0.0, c), (0.0, 10.0)])
n1, n2, b = dos(x1, (5.0, 0.0), x2, (0.0, -5.0), ochava(2.0))
assert todos_cerca(n1, [(c, 0.0), (10.0, 0.0)]) and todos_cerca(n2, [(0.0, -10.0), (0.0, -c)])
# líneas que no llegan a tocarse: se prolongan hasta el bisel
n1, n2, b = dos([(0.0, 0.0), (6.0, 0.0)], (3.0, 0.0), [(10.0, 4.0), (10.0, 10.0)],
                (10.0, 7.0), ochava(R2))
assert todos_cerca(b, [(9.0, 0.0), (10.0, 1.0)])
# Distancia: d1 sobre la primera tocada
n1, n2, b = dos(v, (10.0, 5.0), h, (5.0, 0.0), lambda t: (1.0, 3.0))
assert todos_cerca(b, [(10.0, 1.0), (7.0, 0.0)])
# No recortar: el bisel solo (los objetos los deja el comando)
r = G.chamfer_two(h, (5.0, 0.0), v, (10.0, 5.0), ochava(5.0), trim=False)
assert len(r["bevel"]) == 2
# distancias 0 (o Mayús): la esquina, sin bisel
n1, n2, b = dos([(0.0, 0.0), (8.0, 0.0)], (3.0, 0.0), [(10.0, 2.0), (10.0, 9.0)],
                (10.0, 5.0), lambda t: (0.0, 0.0))
assert b is None and n1[-1] == (10.0, 0.0) and n2[0] == (10.0, 0.0)
print("ok bisel entre dos líneas: A = B, lado del clic, No recortar, esquina")

# ---- 3b. con polilínea: tramo extremo y todo unido en una, como IngeCAD ---------------------
pl = [(0.0, 5.0), (0.0, 0.0), (10.0, 0.0)]                 # su último tramo va al cruce
r = G.chamfer_two(pl, (5.0, 0.0), v, (10.0, 5.0), ochava(5.0))
c = 5.0 / R2
assert r["base"] == 1 and r["bevel"] == [r["join"][2], r["join"][3]]
assert todos_cerca(r["join"], [(0.0, 5.0), (0.0, 0.0), (10.0 - c, 0.0), (10.0, c), (10.0, 10.0)])
# primero la línea: la base es la polilínea, y la línea llega al cruce
r = G.chamfer_two(v, (10.0, 5.0), pl, (5.0, 0.0), ochava(5.0))
assert r["base"] == 2
assert todos_cerca(r["join"], [(10.0, 10.0), (10.0, c), (10.0 - c, 0.0), (0.0, 0.0), (0.0, 5.0)])
# dos polilíneas por su primer tramo
pl2 = [(10.0, 2.0), (10.0, 10.0), (20.0, 10.0)]
r = G.chamfer_two(pl, (5.0, 0.0), pl2, (10.0, 5.0), ochava(5.0))
assert todos_cerca(r["join"], [(0.0, 5.0), (0.0, 0.0), (10.0 - c, 0.0), (10.0, c), (10.0, 10.0),
                               (20.0, 10.0)])
# Mayús: unidas en la esquina
r = G.chamfer_two(pl, (5.0, 0.0), pl2, (10.0, 5.0), lambda t: (0.0, 0.0))
assert r["bevel"] is None and todos_cerca(r["join"], [(0.0, 5.0), (0.0, 0.0), (10.0, 0.0),
                                                      (10.0, 10.0), (20.0, 10.0)])
# errores con los mensajes de IngeCAD
mid = [(0.0, 0.0), (5.0, 0.0), (8.0, 0.0), (8.0, -5.0)]
for args, msg in (((h, (5, 0), [(0, 3), (10, 3)], (5, 3), ochava(1)), "las líneas son paralelas"),
                  ((pl, (5, 0), [(0, 3), (5, 3), (5, 8)], (2, 3), ochava(1)), "los tramos son paralelos"),
                  ((h, (5, 0), v, (10, 5), ochava(30)), "el chaflán no entra"),
                  ((h, (5, 0), v, (10, 5), lambda t: O.distancias("A", t, largo=2, angulo=100)),
                   "el chaflán no entra"),
                  ((mid, (6.5, 0), [(7, -9), (7, 9)], (7, 5), ochava(1)), "tramo EXTREMO"),
                  ((pl, (12, 0), [(11, -9), (11, 9)], (11, 5), ochava(1)), "el lado que sigue"),
                  (([(0, 0), (4, 0), (4, 4), (0, 0)], (2, 0), v, (10, 5), ochava(1)), "las cerradas")):
    try:
        G.chamfer_two(*args); raise AssertionError(msg)
    except G.GeomError as e:
        assert msg in str(e), (msg, str(e))
print("ok con polilínea: tramo extremo, unidas en una, mensajes de IngeCAD")

# ---- 4. la esquina de un polígono (o de una polilínea): el bisel queda en el objeto --------
cuadra = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0)]
new, b = G.chamfer_same(cuadra, (50.0, 0.0), (100.0, 50.0), ochava(5.0), closed=True)
c = 5.0 / R2
assert todos_cerca(new, [(0.0, 0.0), (100.0 - c, 0.0), (100.0, c), (100.0, 100.0), (0.0, 100.0),
                         (0.0, 0.0)])
assert todos_cerca(b, [(100.0 - c, 0.0), (100.0, c)])
# la esquina del cierre (vértice 0), tocando primero el lado que llega
new, b = G.chamfer_same(cuadra, (0.0, 50.0), (50.0, 0.0), ochava(5.0), closed=True)
assert len(new) == 6 and new[0] == new[-1] and abs(G.dist(*b) - 5.0) < 1e-9
assert all(abs(p[0]) > 1e-9 or abs(p[1]) > 1e-9 for p in new)    # el vértice (0,0) ya no está
# Distancia en polilínea abierta: d1 sobre el primer tramo tocado
pl = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
new, b = G.chamfer_same(pl, (10.0, 5.0), (5.0, 0.0), lambda t: (1.0, 3.0))
assert todos_cerca(new, [(0.0, 0.0), (7.0, 0.0), (10.0, 1.0), (10.0, 10.0)])
for args, msg in (((pl, (2, 0), (2.1, 0), ochava(1)), "Elija un objeto distinto"),
                  (([(0, 0), (5, 0), (5, 5), (9, 5)], (2, 0), (7, 5), ochava(1)), "contiguos"),
                  ((pl, (5, 0), (10, 5), lambda t: (0.0, 0.0)), "ya es una esquina"),
                  ((pl, (5, 0), (10, 5), ochava(40)), "el chaflán no entra")):
    try:
        G.chamfer_same(*args); raise AssertionError(msg)
    except G.GeomError as e:
        assert msg in str(e), e
# el empalme sigue igual después de compartir la búsqueda del vértice
new = G.fillet_same(pl, (5.0, 0.0), (10.0, 5.0), 1.0)
assert new[0] == (0.0, 0.0) and new[-1] == (10.0, 10.0) and len(new) > 4
print("ok ochava en la esquina de un polígono y de una polilínea")

# ---- 5. opción Polilínea: todos los vértices -----------------------------------------------
new, hechas, cortas = G.chamfer_all(cuadra, ochava(5.0), closed=True)
assert hechas == 4 and cortas == 0 and len(new) == 9 and new[0] == new[-1]
lados = [G.dist(new[k], new[k + 1]) for k in range(8)]
assert sorted(round(x, 9) for x in lados)[:4] == [5.0] * 4          # cuatro biseles de 5
new, hechas, cortas = G.chamfer_all([(0, 0), (10, 0), (10, 10), (11, 10)], ochava(3.0))
assert hechas == 1 and cortas == 1                                  # el último tramo (1) no alcanza
new, hechas, cortas = G.chamfer_all([(0, 0), (5, 0), (10, 0)], ochava(1.0))
assert hechas == 0 and new == [(0, 0), (5, 0), (10, 0)]             # alineados: nada
print("ok opción Polilínea")

# ---- 6. CHAFLÁN en Dibujo: barra, menú, alias, ícono, Yaguá Edición -------------------------
src = (GEOCAD / "dibujo" / "edit_commands.py").read_text(encoding="utf-8")
assert "('CHAMFER', ('CHAFLAN', 'CHAFLÁN', 'CHA', 'CHANFLE'), ChamferCommand, 'CHAFLÁN'" in src
assert "from .. import ochava" in src and "ochava.distancias(" in src
for op in ("('O', 'Ochava')", "('H', 'desHacer')", "('P', 'Polilínea')", "('D', 'Distancia')",
           "('A', 'Ángulo')", "('R', 'Recortar')", "('E', 'mEtodo')", "('M', 'Múltiple')"):
    assert op in src, op
assert "'Precise largo de ochava (L)'" in src
assert "('TRIM', 'EXTEND', 'CHAMFER', 'FILLET', 'PERPENDICULAR')" in \
    (GEOCAD / "dibujo" / "plugin.py").read_text(encoding="utf-8")
assert (GEOCAD / "dibujo" / "icons" / "chamfer.svg").is_file()
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import botones
edicion = dict(botones.DEFECTO["qgis"])["Yaguá Edición"]
assert edicion.index("dibujo:chamfer") + 1 == edicion.index("dibujo:fillet")
print("ok CHAFLÁN en la barra Edición CAD, el menú y Yaguá Edición")
print("TODO OK")
