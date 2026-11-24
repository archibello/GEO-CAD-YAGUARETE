"""INSERTARGEO, EXPORTARGEO y GEORREF en QGIS (3.90.0), sin Qt: el archivo de mundo
de una geotransformación de GDAL (el mismo que lee INSERTARGEO de IngeCAD), las
esquinas y el clic adentro, la copia geo que nunca pisa la original, y los
botones en «Yaguá Imagenes» (fábrica, bancos y migración). Las órdenes, la capa
ráster y el Georreferenciador de QGIS los prueba ventana/banco_imagen_geo_qgis.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import json, math, os, sys, tempfile, types, importlib
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
ROOT = Path(__file__).resolve().parents[2]
DIBUJO = ROOT / "QGIS" / "codigo" / "geocad" / "dibujo"
pkg = types.ModuleType("dib"); pkg.__path__ = [str(DIBUJO)]; sys.modules["dib"] = pkg
SI = importlib.import_module("dib.soltar_imagen")
IG = importlib.import_module("dib.imagen_geo")
sys.path.insert(0, str(ROOT / "COMUN"))
from nucleo import botones as BT


def cerca(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ---- 1. geotransformación <-> archivo de mundo, como SOLTARIMAGEN e IngeCAD ---------------------
for giro in (0, 30, -120):
    p1, ancho, px, py = (1000.0, 2000.0), 80.0, 400, 200
    mundo = SI.archivo_mundo(p1, ancho, giro, px, py)
    A, D, B, E, C, F = mundo
    gt = (C - 0.5 * A - 0.5 * B, A, B, F - 0.5 * D - 0.5 * E, D, E)     # lo que arma GDAL
    assert cerca(IG.mundo_de_gt(gt), mundo, 1e-6), giro
    assert cerca(sum(IG.esquinas_gt(gt, px, py), ()), sum(SI.esquinas(p1, ancho, giro, px, py), ()), 1e-6)
# lo mismo que lee INSERTARGEO de IngeCAD (coef_de_mundo): la esquina de arriba a la izquierda
ing = (ROOT / "INGECAD" / "codigo" / "geocad" / "imagengeo.py").read_text(encoding="utf-8")
assert "return (C - 0.5 * b + 0.5 * c, b, c, F - 0.5 * e + 0.5 * f, e, f)" in ing
gt = (500000.0, 0.5, 0.0, 6100000.0, 0.0, -0.5)
assert IG.mundo_de_gt(gt) == (0.5, 0.0, 0.0, -0.5, 500000.25, 6099999.75)
assert IG.georreferenciada(gt) and not IG.georreferenciada(IG.IDENTIDAD)
assert not IG.georreferenciada(None) and IG.georreferenciada(None, 4)
assert IG.describir(gt, 100, 50) == "X 500000 a 500050, Y 6099975 a 6100000; píxel 0.5 × 0.5"
assert IG.describir((0, 1, 0, 10, 0, -1), 10, 10).endswith("píxel 1 × 1")
print("ok archivo de mundo")

# ---- 2. el clic adentro de la imagen (también girada) --------------------------------------------
esq = SI.esquinas((0, 0), 100, 45, 100, 50)
assert IG.dentro((10, 20), esq) and not IG.dentro((60, 0), esq) and IG.dentro((0, 0), esq)
assert IG.dentro((50, 25), IG.esquinas_gt((0, 1, 0, 50, 0, -1), 100, 50))
assert not IG.dentro((1, 1), []) and IG.caja([(1, 5), (3, 2)]) == (1, 2, 3, 5)
print("ok clic")

# ---- 3. de dónde salió la georreferencia ---------------------------------------------------------
assert IG.fuente(["/a/plano.png", "/a/plano.pgw", "/a/plano.png.aux.xml"]) == "archivo de mundo plano.pgw"
assert IG.fuente(["/a/plano.png", "/a/plano.pngw"]) == "archivo de mundo plano.pngw"
assert IG.fuente(["/a/plano.jpg", "/a/PLANO.WLD"]) == "archivo de mundo PLANO.WLD"
assert IG.fuente(["/a/orto.tif"]) == "georreferencia del archivo" and IG.fuente(None) == "georreferencia del archivo"
print("ok fuente")

# ---- 4. la copia geo: nunca la original, ni pisa otra copia --------------------------------------
d = Path(tempfile.mkdtemp())
orig = d / "plano.png"; orig.write_bytes(b"\x89PNG plano")
(d / "plano.pgw").write_text("1\n0\n0\n-1\n0.5\n0.5\n")
assert IG.nombre_copia(orig) == str(d / "plano_georref.png")
(d / "plano_georref.png.points").write_text("x")             # unos puntos sueltos tampoco se pisan
assert IG.nombre_copia(orig) == str(d / "plano_georref2.png")
for mal in (orig, str(orig)[:-4], d / "no_existe" / "x.png"):
    try:
        IG.exportar(orig, mal, gt)
        raise SystemExit("tenía que fallar: %s" % mal)
    except OSError:
        pass
assert sorted(p.name for p in d.iterdir()) == ["plano.pgw", "plano.png", "plano_georref.png.points"]
hechos = IG.exportar(orig, d / "copia", gt, 'PROJCS["UTM <21S>"]')         # la extensión, la de la original
assert hechos == [str(d / "copia.png"), str(d / "copia.pgw"), str(d / "copia.png.aux.xml")], hechos
assert (d / "copia.png").read_bytes() == orig.read_bytes()
assert [float(v) for v in (d / "copia.pgw").read_text().split()] == list(IG.mundo_de_gt(gt))
assert "UTM &lt;21S&gt;" in (d / "copia.png.aux.xml").read_text()
assert (d / "plano.pgw").read_text() == "1\n0\n0\n-1\n0.5\n0.5\n"           # lo de la original, igual
(d / "otra.PNG.aux.xml").write_text("mio")
assert IG.exportar(orig, d / "otra.PNG", gt, "WKT") == [str(d / "otra.PNG"), str(d / "otra.pgw")]
assert (d / "otra.PNG.aux.xml").read_text() == "mio"                         # un .aux.xml que estaba no se toca
print("ok copia geo")

# ---- 5. los botones en «Yaguá Imagenes»: fábrica, bancos y migración -----------------------------
fab = dict(BT.DEFECTO["qgis"])
assert fab["Yaguá Imagenes"][:3] == ("dibujo:insertgeo", "dibujo:georref", "dibujo:exportgeo")   # 3.91.0: y ASPECTOIMAGEN
assert fab["Yaguá Imagenes"][-1] == "dibujo:pasteimage"
ing_bar = dict(BT.DEFECTO["ingecad"])["Yaguá Imagenes"]
assert ing_bar.index("INSERTARGEO") < ing_bar.index("GEORREF") < ing_bar.index("EXPORTARGEO")    # el orden de IngeCAD
assert "dibujo:insertgeo" in BT.TEMA_BANCO["qgis"]["Dibujo"] and "INSERTARGEO" in BT.TEMA_BANCO["ingecad"]["Dibujo"]
assert "dibujo:georref" in BT.TEMA_BANCO["qgis"]["Edición"] and "GEORREF" in BT.TEMA_BANCO["ingecad"]["Edición"]
assert "dibujo:exportgeo" in BT.TEMA_BANCO["qgis"]["Configuración"]
assert "EXPORTARGEO" in BT.TEMA_BANCO["ingecad"]["Configuración"]
hechas = [m for m in BT.MIGRACIONES["qgis"] if m != "imagenes-geo-qgis"]
BT.archivo().parent.mkdir(parents=True, exist_ok=True)


def migrar(cats, ya=hechas):
    BT.archivo().write_text(json.dumps({"qgis": {"categorias": cats, "migraciones": ya}}), encoding="utf-8")
    return [(c["nombre"], c["botones"]) for c in BT.leer("qgis")["categorias"]]


# lo que dejó la 3.89.0: delante de PEGARIMAGEN
assert migrar([{"nombre": "Yaguá Imagenes", "botones": ["dibujo:pasteimage"]}]) == [
    ("Yaguá Imagenes", ["dibujo:insertgeo", "dibujo:georref", "dibujo:exportgeo", "dibujo:pasteimage"])]
# PEGARIMAGEN llevado por Fernando a otra barra: ahí, en su lugar
assert migrar([{"nombre": "Mía", "botones": ["dibujo:line", "dibujo:pasteimage", "dibujo:move"]}]) == [
    ("Mía", ["dibujo:line", "dibujo:insertgeo", "dibujo:georref", "dibujo:exportgeo", "dibujo:pasteimage",
             "dibujo:move"])]
# uno ya puesto a mano no se repite; sin PEGARIMAGEN, nada
assert migrar([{"nombre": "A", "botones": ["dibujo:georref"]}, {"nombre": "B", "botones": ["dibujo:pasteimage"]}]) == [
    ("A", ["dibujo:georref"]), ("B", ["dibujo:insertgeo", "dibujo:exportgeo", "dibujo:pasteimage"])]
assert migrar([{"nombre": "A", "botones": ["dibujo:line"]}]) == [("A", ["dibujo:line"])]
# desde la 3.88.0 (sin ninguna de las dos): la barra nueva y después los tres
assert migrar([{"nombre": "A", "botones": ["dibujo:rumbos"]}], [m for m in hechas if m != "imagenes-qgis"]) == [
    ("A", ["dibujo:rumbos"]), ("Yaguá Imagenes", ["dibujo:insertgeo", "dibujo:georref", "dibujo:exportgeo",
                                                  "dibujo:pasteimage"])]
# una sola vez
assert migrar([{"nombre": "A", "botones": ["dibujo:pasteimage"]}], list(BT.MIGRACIONES["qgis"])) == [
    ("A", ["dibujo:pasteimage"])]
BT.restablecer("qgis")
print("ok barra")

# ---- 6. las órdenes y los botones en el complemento -----------------------------------------------
plugin = (DIBUJO / "plugin.py").read_text(encoding="utf-8")
for b in ("insertgeo", "georref", "exportgeo"):
    assert "self._action('%s'" % b in plugin and (DIBUJO / "icons" / (b + ".svg")).is_file(), b
assert plugin.index("_action('insertgeo'") < plugin.index("_action('georref'") < plugin.index(
    "_action('exportgeo'") < plugin.index("_action('pasteimage'")
orden = (DIBUJO / "imagen_geo_qgis.py").read_text(encoding="utf-8")
assert "ACCION_GEORREF = 'mActionShowGeoreferencer'" in orden          # el botón de la tabla de GEORREF
assert "CommandSpec('GEORREF'" in (DIBUJO / "georref_qgis.py").read_text(encoding="utf-8")   # 3.93.0
print("ok complemento")

print("TODO OK IMAGEN GEO QGIS")
