"""RUMBOS (3.43.0), sin Qt: el cálculo de cada tramo da lo mismo que los dos
Digitalizadores GMS de Fernando (Líneas GMS: ángulo interior con Izquierda /
Derecha; Continuo 3.0: deflexión, + izquierda), botón en «Yaguá Dibujo» y retiro
de los sueltos. Lo que se ve en QGIS lo prueba ventana/banco_rumbos_qgis.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, math, tempfile, importlib.util
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"
spec = importlib.util.spec_from_file_location("units", GEOCAD / "dibujo" / "units.py")
U = importlib.util.module_from_spec(spec); spec.loader.exec_module(U)
units = U.Units()


def cerca(a, b, tol=1e-9):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


# las fórmulas de los sueltos, copiadas de su código (lineaGSM 0.2 y digitalizador_gms 3.0)
def lineas_gms(origen, inicio, g, m, s, dist, lado):
    g_dec = g + m / 60.0 + s / 3600.0
    ang = math.radians(g_dec)
    base = math.atan2(origen[1] - inicio[1], origen[0] - inicio[0])
    fin = base - ang if lado == "Izquierda" else base + ang
    return (inicio[0] + dist * math.cos(fin), inicio[1] + dist * math.sin(fin))


def continuo_gms(a, b, g, m, s, dist):
    lado = "Izquierda" if g >= 0 else "Derecha"
    ang = math.radians(abs(g) + m / 60.0 + s / 3600.0)
    base = math.atan2(b[1] - a[1], b[0] - a[0])
    base = base + ang if lado == "Izquierda" else base - ang
    return (b[0] + dist * math.cos(base), b[1] + dist * math.sin(base))


A, B = (0.0, 0.0), (10.0, 3.0)
# ---- 1. Interior = Líneas GMS (Derecha suma = antihorario; Izquierda = negativo) ---------
for g, m, s, dist in [(91, 30, 15.5, 25.4), (180, 0, 0, 10.0), (45, 0, 0, 7.0), (270, 12, 0, 3.3)]:
    txt = "%s<%dd%d'%s\"" % (dist, g, m, s)
    p, d = U.tramo_rumbo(A, B, txt, units, "interior")
    assert d == dist and cerca(p, lineas_gms(A, B, g, m, s, dist, "Derecha")), (txt, p)
    p, _d = U.tramo_rumbo(A, B, "%s<-%dd%d'%s\"" % (dist, g, m, s), units, "interior")
    assert cerca(p, lineas_gms(A, B, g, m, s, dist, "Izquierda")), (txt, p)
# 180 sigue derecho
p, _d = U.tramo_rumbo(A, B, "5<180", units, "interior")
dirB = math.atan2(B[1] - A[1], B[0] - A[0])
assert cerca(p, (B[0] + 5 * math.cos(dirB), B[1] + 5 * math.sin(dirB)))
print("ok Interior = Digitalizador de Líneas GMS (Derecha / Izquierda)")

# ---- 2. Deflexión = Continuo 3.0 (0 sigue derecho, + izquierda, - derecha) ---------------
for g, m, s, dist in [(45, 30, 15, 25.4), (-90, 0, 0, 12.8), (0, 0, 0, 4.0), (-12, 5, 30.5, 9.0)]:
    txt = "%s<%dd%d'%s\"" % (dist, g, m, s)
    p, _d = U.tramo_rumbo(A, B, txt, units, "deflexion")
    assert cerca(p, continuo_gms(A, B, g, m, s, dist)), (txt, p)
print("ok Deflexión = Digitalizador Continuo GMS 3.0")

# ---- 3. en los dos modos: 30dI / 30dD, rumbos y '<<' absoluto -----------------------------
for modo in ("interior", "deflexion"):
    p, _d = U.tramo_rumbo(A, B, "10<30dI", units, modo)
    assert cerca(p, continuo_gms(A, B, 30, 0, 0, 10))
    p, _d = U.tramo_rumbo(A, B, "10<30dD", units, modo)
    assert cerca(p, continuo_gms(A, B, -30, 0, 0, 10))
    p, _d = U.tramo_rumbo(A, B, "10<N45dE", units, modo)
    assert cerca(p, (B[0] + 10 * math.cos(math.radians(45)), B[1] + 10 * math.sin(math.radians(45))))
    p, _d = U.tramo_rumbo(A, B, "10<<90", units, modo)
    assert cerca(p, (B[0], B[1] + 10))
# lo que no es un tramo: None (se resuelve como punto); distancia cero: error
assert U.tramo_rumbo(A, B, "@10,5", units) is None and U.tramo_rumbo(A, B, "10,5", units) is None
try:
    U.tramo_rumbo(A, B, "0<90", units); raise SystemExit("distancia cero aceptada")
except U.InputError:
    pass
print("ok 30dI / 30dD, rumbos, '<<' absoluto, puntos y distancia cero")

# ---- 4. botón y retiro -----------------------------------------------------------------
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import botones, submodulos
dib = dict(botones.DEFECTO["qgis"])["Yaguá Dibujo"]
assert dib.index("dibujo:rumbos") == dib.index("dibujo:rect") + 1
assert {"lineaGSM", "digitalizador_gms"} <= set(submodulos.VIEJOS["dibujo"])
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir()
(plugins / "lineaGSM").mkdir()
assert submodulos.retirar_viejos("dibujo", plugins) == ["lineaGSM"]
assert (GEOCAD / "dibujo" / "icons" / "rumbos.svg").is_file()
print("ok botón en Yaguá Dibujo, ícono y retiro de los digitalizadores")
print("TODO OK")
