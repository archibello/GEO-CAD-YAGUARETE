"""El motor KML compartido (3.74.0): escribir y control de faja, sin Qt ni IngeCAD.
Lo que hace QGIS de verdad lo prueba ventana/banco_kml_qgis_real.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import ast, os, sys, tempfile, zipfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = Path(HERE).parent.parent
sys.path[:0] = [str(RAIZ / "COMUN" / "nucleo")]
import crs as C
import kmlformato as F

# la faja que dicen las X
assert C.faja_de_x([6_620_549.0, 6_700_000.0]) == 6
assert C.faja_de_x([6_620_549.0, 6_700_000.0, 0.0]) == 6            # un objeto suelto no cuenta
assert C.faja_de_x([500_000.0]) is None                             # UTM
assert C.faja_de_x([]) is None
assert C.faja_sugerida("", [6_620_549.0]) == "EPSG:5348"            # sin sistema: POSGAR 2007
assert C.faja_sugerida("EPSG:5349", [6_620_549.0]) == "EPSG:5348"   # el mismo marco
assert C.faja_sugerida("EPSG:22197", [6_620_549.0]) == "EPSG:22196"  # Campo Inchauspe sigue siéndolo
assert C.faja_sugerida("EPSG:5348", [6_620_549.0]) == ""            # concuerda
assert C.faja_sugerida("EPSG:32721", [6_620_549.0]) == ""           # UTM: no se opina
assert C.faja_de("EPSG:5348") == (6, 5343)
assert C.faja_de("EPSG:4326") is None

# relleno y borde propios (QGIS); sin ellos, como siempre (IngeCAD)
tmp = Path(tempfile.mkdtemp())
pol = [([(-55.9, -27.4), (-55.8, -27.4), (-55.8, -27.3), (-55.9, -27.4)], [])]
comun = F.Marca("poligono", pol, "A", "c", "#ff0000", 25)
propio = F.Marca("poligono", pol, "B", "c", "#0000ff", 50, color_relleno="#00ff00", relleno=0)
assert F._estilo_id(comun) == "pff0000_25"                         # el id de siempre
assert F._estilo_id(propio) != "p0000ff_50"
t = F.texto_kml(F.PlanKml([comun, propio], __import__("collections").Counter(), "EPSG:5348", "T", nombre_origen="POSGAR"))
assert "desde POSGAR a WGS 84" in t
assert "<color>660000ff</color>" in t                              # 40 % del plan, en aabbggrr
assert "<color>0000ff00</color>" in t and "<fill>0</fill>" in t    # el propio: verde, sin relleno
assert "<color>ffff0000</color>" in t                              # el borde azul

# KMZ: zip con doc.kml; .kml: texto; si falla no queda el temporal
plan = F.PlanKml([comun], __import__("collections").Counter(), "", "T")
kmz = F.escribir(plan, tmp / "a.kmz")
assert zipfile.ZipFile(kmz).namelist() == ["doc.kml"]
assert F.escribir(plan, tmp / "a.kml").read_bytes()[:5] == b"<?xml"
assert sorted(p.name for p in tmp.iterdir()) == ["a.kml", "a.kmz"]

# QGIS no depende de lo de IngeCAD; y nada de KML en el menú GeoCAD
arbol = ast.parse((RAIZ / "COMUN" / "nucleo" / "kmlformato.py").read_text(encoding="utf-8"))
for nodo in ast.walk(arbol):
    if isinstance(nodo, ast.ImportFrom):
        assert nodo.level == 0, "kmlformato no importa módulos de un programa"
fuente = (RAIZ / "QGIS" / "codigo" / "geocad" / "plugin.py").read_text(encoding="utf-8")
bloque = fuente[fuente.index('("ge_exportar"'):fuente.index('add("modules"')]
assert "addAction" not in bloque, "las herramientas KML van sólo al banco"

# 3.74.1: cada herramienta con su ícono, y los dos archivos existen y son distintos
iconos = RAIZ / "QGIS" / "codigo" / "geocad" / "iconos"
assert (iconos / "exportar_kml.png").read_bytes() != (iconos / "ver_google_earth.png").read_bytes()
assert '"ver_google_earth.png"' in bloque and '"exportar_kml.png"' in bloque

print("TODO OK test_kmlformato")
