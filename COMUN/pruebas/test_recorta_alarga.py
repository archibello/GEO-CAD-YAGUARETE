"""RECORTA y ALARGA de Fernando dentro de Dibujo (3.40.0; retiro de Fillet y
Offset en 3.41.0), sin Qt: la geometría
de la tijera prolongada y del tramo que se quita (vista previa), y el retiro
de los complementos sueltos que reemplaza, sin pisar nunca una copia anterior.
Lo que se ve en QGIS lo prueba ventana/banco_recorta_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, importlib.util
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"

spec = importlib.util.spec_from_file_location("geomops", GEOCAD / "dibujo" / "geomops.py")
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)


def largo(pts):
    return G.length(pts)


# ---- 1. la tijera prolongada corta aunque no llegue ------------------------------------
linea = [(-5.0, 0.0), (5.0, 0.0)]
tijera = [((0.0, 1.0), (0.0, 2.0))]                     # no toca la línea
assert G.trim_polyline(linea, (3.0, 0.0), tijera) == []   # sin prolongar: no la cruza
larga = G.prolong_segments(tijera, 100.0)
assert len(larga) == 1 and larga[0][0][1] < -90 and larga[0][1][1] > 90
partes = G.trim_polyline(linea, (3.0, 0.0), larga)
assert len(partes) == 1 and abs(largo(partes[0]) - 5.0) < 1e-9 and abs(partes[0][-1][0]) < 1e-9
# diagonal, de un solo lado: también corta por su prolongación
diag = G.prolong_segments([((1.0, 1.0), (2.0, 2.0))], 50.0)
partes = G.trim_polyline(linea, (-4.0, 0.0), diag)
assert len(partes) == 1 and abs(partes[0][0][0]) < 1e-9 and abs(largo(partes[0]) - 5.0) < 1e-9
# segmentos de largo cero no se prolongan (no hay dirección)
assert G.prolong_segments([((1.0, 1.0), (1.0, 1.0))], 10.0) == []
print("ok la tijera prolongada corta aunque no llegue")

# ---- 2. el tramo que se quita (vista previa) y lo que queda suman la línea ---------------
pl = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
cortes = [((4.0, -1.0), (4.0, 1.0)), ((9.0, 5.0), (11.0, 5.0))]
for pick in [(1.0, 0.0), (6.0, 0.0), (10.0, 2.0), (10.0, 8.0)]:
    queda = G.trim_polyline(pl, pick, cortes)
    va = G.trim_removed(pl, pick, cortes)
    assert va and abs(sum(largo(q) for q in queda) + largo(va) - largo(pl)) < 1e-9, (pick, queda, va)
    # el clic cae dentro del tramo que se quita
    assert G.locate(pl, va[0]) - 1e-9 <= G.locate(pl, pick) <= G.locate(pl, va[-1]) + 1e-9, (pick, va)
assert abs(largo(G.trim_removed(pl, (6.0, 0.0), cortes)) - 11.0) < 1e-9     # de x=4 a y=5
# sin cortes: se va entero (como AutoCAD en modo rápido)
assert abs(largo(G.trim_removed(linea, (1.0, 0.0), [])) - 10.0) < 1e-9
# anillo cerrado: entre los dos cortes vecinos
anillo = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
cc = [((5.0, -1.0), (5.0, 1.0)), ((5.0, 9.0), (5.0, 11.0))]
va = G.trim_removed(anillo, (10.0, 5.0), cc)
queda = G.trim_polyline(anillo, (10.0, 5.0), cc)
assert abs(largo(va) - 20.0) < 1e-9 and abs(largo(queda[0]) - 20.0) < 1e-9
print("ok tramo que se quita (vista previa) = línea - lo que queda")

# ---- 3. retiro de los sueltos: nunca se pisa una copia anterior ----------------------------
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import submodulos
assert {"Trim_Tool", "Extend_Tool", "autocad_shortcuts",                  # 3.40.0
        "Fillet_Tools_Independiente", "Offset_tool"} <= set(submodulos.VIEJOS["dibujo"])   # 3.41.0
assert "Dibujo_CAD" in submodulos.VIEJOS["dibujo"]
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir()
for nombre, marca in (("Trim_Tool", "nuevo"), (".anterior-Trim_Tool", "copia vieja")):
    (plugins / nombre).mkdir(); (plugins / nombre / "marca.txt").write_text(marca)
(plugins / "Extend_Tool").mkdir(); (plugins / "Extend_Tool" / "marca.txt").write_text("extend")
(plugins / "Fillet_Tools_Independiente").mkdir()
(plugins / "Offset_tool").mkdir()
(plugins / "Ajeno").mkdir()                               # no es de GeoCAD: se queda
retirados = submodulos.retirar_viejos("dibujo", plugins)
assert retirados == ["Trim_Tool", "Extend_Tool", "Fillet_Tools_Independiente", "Offset_tool"], retirados
assert (plugins / ".anterior-Offset_tool").is_dir() and (plugins / ".anterior-Fillet_Tools_Independiente").is_dir()
assert (plugins / ".anterior-Trim_Tool" / "marca.txt").read_text() == "copia vieja"
assert (plugins / ".anterior-Trim_Tool-2" / "marca.txt").read_text() == "nuevo"
assert (plugins / ".anterior-Extend_Tool" / "marca.txt").read_text() == "extend"
assert not (plugins / "Trim_Tool").exists() and (plugins / "Ajeno").is_dir()
# una tercera vez: -3, las otras dos copias intactas
(plugins / "Trim_Tool").mkdir(); (plugins / "Trim_Tool" / "marca.txt").write_text("tercero")
assert submodulos.retirar_viejos("dibujo", plugins) == ["Trim_Tool"]
assert (plugins / ".anterior-Trim_Tool-3" / "marca.txt").read_text() == "tercero"
assert (plugins / ".anterior-Trim_Tool-2" / "marca.txt").read_text() == "nuevo"
assert submodulos.retirar_viejos("dibujo", plugins) == []
print("ok retiro de Trim, Extend, AutoCAD Shortcuts, Fillet y Offset sin pisar copias")
print("TODO OK")
