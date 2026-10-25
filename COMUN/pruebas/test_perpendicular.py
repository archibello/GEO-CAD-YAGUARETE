"""PERPENDICULAR de Fernando dentro de Dibujo (3.42.0), sin Qt: el pie de la
perpendicular sobre el tramo o su prolongación, su botón en «Yaguá Edición» y
el retiro de tool_perpendicular. Lo que se ve en QGIS lo prueba
ventana/banco_perpendicular_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, importlib.util
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"

spec = importlib.util.spec_from_file_location("geomops", GEOCAD / "dibujo" / "geomops.py")
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)


def cerca(a, b):
    return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


# ---- 1. el pie de la perpendicular ------------------------------------------------------
linea = [(0.0, 0.0), (10.0, 0.0)]
assert cerca(G.perpendicular_foot(linea, (3.0, 5.0), (5.0, 0.0)), (3.0, 0.0))
# sobre la prolongación (el origen cae fuera del tramo)
assert cerca(G.perpendicular_foot(linea, (15.0, 4.0), (9.0, 0.0)), (15.0, 0.0))
assert cerca(G.perpendicular_foot(linea, (-7.0, -2.0), (1.0, 0.0)), (-7.0, 0.0))
# polilínea: manda el tramo más cercano al clic, prolongado
pl = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
assert cerca(G.perpendicular_foot(pl, (4.0, 20.0), (10.0, 8.0)), (10.0, 20.0))
assert cerca(G.perpendicular_foot(pl, (4.0, 20.0), (2.0, 0.0)), (4.0, 0.0))
# diagonal: el pie es perpendicular de verdad
d = [(0.0, 0.0), (4.0, 4.0)]
f = G.perpendicular_foot(d, (0.0, 4.0), (1.0, 1.0))
assert cerca(f, (2.0, 2.0)) and abs(G.dot(G.sub(f, (0.0, 4.0)), G.sub(d[1], d[0]))) < 1e-9
# el origen sobre la recta: no hay perpendicular
assert G.perpendicular_foot(linea, (20.0, 0.0), (5.0, 0.0)) is None
print("ok pie de la perpendicular, con prolongación y polilíneas")

# ---- 2. botón en «Yaguá Edición» y retiro del suelto --------------------------------------
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import botones, submodulos
edicion = dict(botones.DEFECTO["qgis"])["Yaguá Edición"]
assert edicion.index("dibujo:perp") == edicion.index("dibujo:fillet") + 1
assert "tool_perpendicular" in submodulos.VIEJOS["dibujo"]
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir()
(plugins / "tool_perpendicular").mkdir()
assert submodulos.retirar_viejos("dibujo", plugins) == ["tool_perpendicular"]
assert (plugins / ".anterior-tool_perpendicular").is_dir()
src = (GEOCAD / "dibujo" / "edit_commands.py").read_text(encoding="utf-8")
assert "('PERPENDICULAR', ('PERP', 'PERPEND'), PerpendicularCommand" in src
assert (GEOCAD / "dibujo" / "icons" / "perp.svg").is_file()
print("ok botón en Yaguá Edición, ícono y retiro de tool_perpendicular")
print("TODO OK")
