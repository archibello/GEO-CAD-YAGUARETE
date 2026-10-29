"""Medidas y ángulos por teclado en Dibujo de QGIS (3.56.1), sin Qt: lo
acordado con Fernando, «@distancia<ángulo interno en contra de las agujas del
reloj» desde el tramo anterior (como IngeCAD, Q3 y P4), tiene que valer en un
perfil de QGIS nuevo (Windows) y con coma decimal (el punto del teclado
numérico escribe coma con la configuración regional de Argentina)."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import math, importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DIBUJO = ROOT / "QGIS" / "codigo" / "geocad" / "dibujo"
spec = importlib.util.spec_from_file_location("units", DIBUJO / "units.py")
U = importlib.util.module_from_spec(spec); spec.loader.exec_module(U)
units = U.Units()


def cerca(a, b, tol=1e-9):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def linea(entradas, relative):
    """Como LÍNEA: cada entrada desde el último punto, ref = dirección del tramo anterior."""
    pts, ref = [], None
    for t in entradas:
        last = pts[-1] if pts else None
        p = U.parse_point(t, units, last, ref, relative).point
        if last is not None:
            ref = math.atan2(p[1] - last[1], p[0] - last[0])
        pts.append(p)
    return pts


# 1) REL prendido por defecto: un perfil de QGIS nuevo no tiene «relangle» guardado
src = (DIBUJO / "commands.py").read_text(encoding="utf-8")
assert "get_setting('relangle', True, bool)" in src, "REL tiene que arrancar prendido"
assert "get_setting('relangle', False" not in src

# 2) P4: 0,0 @10<0 @5<90 @10<90 @5<90 cierra (interior, antihorario)
pts = linea(["0,0", "@10<0", "@5<90", "@10<90", "@5<90"], True)
assert cerca(pts[1], (10, 0)) and cerca(pts[2], (10, -5)) and cerca(pts[3], (0, -5)), pts
assert cerca(pts[-1], pts[0]), pts
# 180 = sigue derecho; <<a fuerza absoluto
pts = linea(["0,0", "@10<0", "@10<180", "@5<<90"], True)
assert cerca(pts[2], (20, 0)) and cerca(pts[3], (20, 5)), pts
# el primer tramo es absoluto (0 = este)
assert cerca(linea(["0,0", "@10<90"], True)[1], (0, 10))

# 3) coma decimal en la polar: distancia y ángulo
pts = linea(["0,0", "@12,5<0", "@2,5<90,0"], True)
assert cerca(pts[1], (12.5, 0)) and cerca(pts[2], (12.5, -2.5)), pts
pts = linea(["0,0", "@12.5<0", "@2.5<90"], True)        # con punto, igual
assert cerca(pts[2], (12.5, -2.5)), pts
assert cerca(U.parse_point("@10<45,5", units, (0, 0)).point,
             (10 * math.cos(math.radians(45.5)), 10 * math.sin(math.radians(45.5))))
# «;» entre X e Y para usar coma decimal; «12,5» sigue siendo el punto X=12, Y=5 (AutoCAD)
assert cerca(U.parse_point("12,5;-3,25", units).point, (12.5, -3.25))
assert cerca(U.parse_point("@1,5;2", units, (1, 1)).point, (2.5, 3))
assert cerca(U.parse_point("12,5", units).point, (12, 5))
assert cerca(U.parse_point("@3,4", units, (1, 1)).point, (4, 5))
# distancia sola con coma decimal
assert U.parse_point("7,25", units).kind == "point"
assert abs(U.parse_distance("7,25") - 7.25) < 1e-12
d = U.parse_point("7.25", units)
assert d.kind == "distance" and abs(d.distance - 7.25) < 1e-12
# RUMBOS también toma la coma decimal en la distancia
prev, cur = (0.0, 0.0), (10.0, 0.0)
p = U.tramo_rumbo(prev, cur, "2,5<180", units, "interior")
p = p[0] if isinstance(p[0], tuple) else p
assert cerca(p, (12.5, 0)), p
# lo que no es número sigue dando error
for malo in ("@1,2,3,4<9", "@abc<90", "@10<9x"):
    try:
        U.parse_point(malo, units, (0, 0)); raise AssertionError(malo)
    except U.InputError:
        pass

print("TODO OK test_medidas_angulos_qgis")
