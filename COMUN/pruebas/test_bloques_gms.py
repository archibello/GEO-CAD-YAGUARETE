"""INSERTAR con P2 y las dos simetrías (Bloques GMS de Fernando, 3.45.0), sin
Qt: la colocación de GeoCAD (punto, escalas, giro) deja cada punto del bloque
donde lo deja Bloques GMS, con y sin simetrías; lectura de sus .json (sin
tocarlos), botón y retiro. Lo de la capa lo prueba ventana/banco_bloques_gms_qgis.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, json, math, tempfile, importlib.util
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"


def modulo(nombre):
    spec = importlib.util.spec_from_file_location(nombre, GEOCAD / "dibujo" / (nombre + ".py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


G, J = modulo("geomops"), modulo("gms_json")


# ---- Bloques GMS tal cual (transform_geom_mirrored, en puntos) ---------------------------
def refl(p, o, u):
    """Reflexión de p respecto de la recta por o con dirección unitaria u (su matriz)."""
    a, b, d = 2 * u[0] ** 2 - 1, 2 * u[0] * u[1], 2 * u[1] ** 2 - 1
    tx, ty = o[0] - a * o[0] - b * o[1], o[1] - b * o[0] - d * o[1]
    return (a * p[0] + b * p[1] + tx, b * p[0] + d * p[1] + ty)


def gms(pt, anchor, sp, p2, mirrored, horizon):
    base_len = math.hypot(*p2)
    tl = math.hypot(sp[0] - anchor[0], sp[1] - anchor[1])
    s = tl / base_len
    ang = math.atan2(sp[1] - anchor[1], sp[0] - anchor[0]) - math.atan2(p2[1], p2[0])
    c, si = math.cos(ang) * s, math.sin(ang) * s
    q = (c * pt[0] - si * pt[1] + anchor[0], si * pt[0] + c * pt[1] + anchor[1])
    ux, uy = (sp[0] - anchor[0]) / tl, (sp[1] - anchor[1]) / tl
    if mirrored:
        q = refl(q, ((anchor[0] + sp[0]) / 2, (anchor[1] + sp[1]) / 2), (-uy, ux))
    if horizon:
        q = refl(q, anchor, (ux, uy))
    return q


def geocad(pt, colocacion):
    (x, y), sx, sy, rot = colocacion            # blocks.place: R(rot) · diag(sx, sy) · local + punto
    c, s = math.cos(rot), math.sin(rot)
    return (sx * c * pt[0] - sy * s * pt[1] + x, sx * s * pt[0] + sy * c * pt[1] + y)


puntos = [(0, 0), (3, 0), (3, 1), (-1, 2), (0.5, -4)]
casos = [((10, 5), (16, 13), (3, 0)), ((0, 0), (-2, 7), (1, 1)), ((5, -3), (5.5, -9), (0, 2))]
for anchor, sp, p2 in casos:
    for mir in (False, True):
        for hor in (False, True):
            col = G.gms_insercion(anchor, sp, p2, mir, hor)
            for pt in puntos:
                a, b = gms(pt, anchor, sp, p2, mir, hor), geocad(pt, col)
                assert abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9, (anchor, sp, mir, hor, pt, a, b)
try:
    G.gms_insercion((1, 1), (1, 1), (3, 0)); raise SystemExit("P2 = P1 aceptado")
except G.GeomError:
    pass
print("ok INSERTAR con P2 y las dos simetrías = Bloques GMS, punto por punto")

# ---- lectura de los .json de Bloques GMS ---------------------------------------------------
carpeta = Path(tempfile.mkdtemp()) / "bloques"; carpeta.mkdir()
datos = {"format": 2, "name": "puerta", "project_crs": "EPSG:32721", "p1": [0, 0], "p2": [0.9, 0],
         "base_length": 0.9, "source_layer_name": "muros",
         "geometries_wkt": ["LineString (0 0, 0.9 0)", "LineString (0 0, 0 0.9)"]}
(carpeta / "puerta.json").write_text(json.dumps(datos), encoding="utf-8")
(carpeta / "roto.json").write_text("{no es json", encoding="utf-8")
(carpeta / "otro.txt").write_text("x", encoding="utf-8")
antes = {p.name: p.read_bytes() for p in carpeta.iterdir()}
rutas = J.archivos(str(carpeta))
assert [os.path.basename(r) for r in rutas] == ["puerta.json", "roto.json"]
b = J.leer(rutas[0])
assert b["nombre"] == "puerta" and b["p2"] == (0.9, 0.0) and len(b["wkts"]) == 2 and b["crs"] == "EPSG:32721"
assert J.leer(rutas[1]) is None
datos["name"] = 'a/b:c'
(carpeta / "raro.json").write_text(json.dumps(datos), encoding="utf-8")
assert J.leer(str(carpeta / "raro.json"))["nombre"] == "a_b_c"
assert all((carpeta / n).read_bytes() == v for n, v in antes.items()), "los archivos no se tocan"
print("ok lectura de los .json de Bloques GMS, sin tocarlos")

# ---- botón y retiro ------------------------------------------------------------------------
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import botones, submodulos
assert list(dict(botones.DEFECTO["qgis"])["Yaguá Bloques"])[-1] == "dibujo:gmsblocks"
assert "Bloques_GMS" in submodulos.VIEJOS["dibujo"]
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir(); (plugins / "Bloques_GMS").mkdir()
assert submodulos.retirar_viejos("dibujo", plugins) == ["Bloques_GMS"]
assert (GEOCAD / "dibujo" / "icons" / "gmsblocks.svg").is_file()
print("ok botón en Yaguá Bloques, ícono y retiro de Bloques_GMS")
print("TODO OK")
