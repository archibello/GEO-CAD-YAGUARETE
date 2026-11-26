"""FILTRO (FI) en QGIS (3.97.0), sin QGIS: las propiedades de QGIS (tipo como
en Propiedades, capa CAD, color, tipo y grosor de línea, largo, área,
perímetro, vértices, polilínea cerrada, textos, bloques, campos de la tabla),
los grupos Y/O/XO/NO y los comodines del núcleo (filtro_base, el mismo que
usa IngeCAD), «Agregar objeto seleccionado» y los filtros guardados en
~/.config/geocad/filtros_qgis.json, aparte de los de IngeCAD. La ventana es
la misma de IngeCAD (nucleo/filtro_ui.py). Lo que pasa en QGIS (sólo lo
visible, FI dentro de Designar, el resultado seleccionado) lo prueba
ventana/banco_filtro_qgis.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, shutil, importlib, json
from pathlib import Path
CASA = tempfile.mkdtemp(); os.environ["HOME"] = CASA
ROOT = Path(__file__).resolve().parents[2]
# un paquete «geocadq» con el filtro.py de QGIS y el núcleo (sin QGIS)
pkg = Path(tempfile.mkdtemp()) / "geocadq"
pkg.mkdir()
(pkg / "__init__.py").write_text("")
for f in (ROOT / "QGIS" / "codigo" / "geocad" / "filtro.py", ROOT / "COMUN" / "nucleo" / "filtro_base.py",
          ROOT / "COMUN" / "nucleo" / "filtro_ui.py"):
    shutil.copy(f, pkg / f.name)
sys.path.insert(0, str(pkg.parent))
F = importlib.import_module("geocadq.filtro")
UI = importlib.import_module("geocadq.filtro_ui")
B = importlib.import_module("geocadq.filtro_base")
O = F.Objeto

# los núcleos de IngeCAD y QGIS son el mismo archivo
assert (ROOT / "COMUN" / "nucleo" / "filtro_base.py").read_bytes() == \
    (ROOT / "QGIS" / "codigo" / "geocad" / "filtro_base.py").read_bytes()

cuadro = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
objs = [
    O(1, F.POLIGONO, {"LAYER_CODE": "LOTES", "CAD_COLOR": "", "PROPIETARI": "PEREZ JUAN", "SUP": 100.0},
      [cuadro]),
    O(2, F.POLIGONO, {"LAYER_CODE": "LOTES-ESQ", "CAD_COLOR": "#ff0000", "PROPIETARI": "GOMEZ", "SUP": 40},
      [[(20, 0), (24, 0), (24, 10), (20, 10), (20, 0)]]),
    O(3, F.POLILINEA, {"LAYER_CODE": "EJES", "CAD_LTYPE": "DASHED", "CAD_LW": 0.5},
      [[(0, 20), (30, 20), (30, 40)]]),
    O(4, F.POLILINEA, {"LAYER_CODE": "EJES"}, [[(0, 50), (5, 50), (5, 55), (0, 50)]]),
    O(5, F.LINEA, {"LAYER_CODE": None}, [[(0, 60), (3, 64)]]),
    O(6, F.TEXTO, {"LAYER_CODE": "ROTULOS", "TEXTO": "Lote 12", "ALTURA": 2.5, "COLOR": "#00ff00",
                   "FUENTE": "Arial"}, punto=(5, 5)),
    O(7, F.BLOQUE, {"LAYER_CODE": "SIMBOLOS", "NOMBRE": "ARBOL"}, punto=(50, 50)),
    O(8, F.PUNTO, {"LAYER_CODE": "MOJONES"}, punto=(-3, 4)),
]


def ids(conds):
    return [o.fid for o in F.filtrar(objs, conds)]


# ---- 1. tipos y propiedades generales -----------------------------------------------------------
assert ids([]) == [1, 2, 3, 4, 5, 6, 7, 8]
assert ids([{"p": "poligono"}]) == [1, 2]
assert ids([{"p": "polilinea"}]) == [3, 4] and ids([{"p": "cerrada"}]) == [4]
assert ids([{"p": "linea"}]) == [5] and ids([{"p": "texto"}]) == [6] and ids([{"p": "bloque"}]) == [7]
assert ids([{"p": "capa", "op": "=", "v": "lotes*"}]) == [1, 2]                 # comodín, sin mayúsculas
assert ids([{"p": "capa", "op": "=", "v": "EJES,ROTULOS"}]) == [3, 4, 6]       # la coma: alternativas
assert ids([{"p": "capa", "op": "=", "v": "0"}]) == [5]                         # sin capa = 0
assert ids([{"p": "color", "op": "=", "v": 256}]) == [1, 3, 4, 5, 7, 8]        # PorCapa
assert ids([{"p": "color", "op": "=", "v": "Rojo"}]) == [2]
assert ids([{"p": "color", "op": "=", "v": "3 - Verde"}]) == [6]               # el texto usa COLOR
assert ids([{"p": "tipo_linea", "op": "=", "v": "dashed"}]) == [3]
assert ids([{"p": "tipo_linea", "op": "=", "v": "PorCapa"}, {"p": "polilinea"}]) == [4]
assert ids([{"p": "grosor", "op": ">=", "v": 0.5}]) == [3]
print("ok tipos, capa CAD (comodines), color, tipo y grosor de línea")

# ---- 2. medidas y posiciones ------------------------------------------------------------------
assert ids([{"p": "area", "op": ">", "v": 50}]) == [1]
assert ids([{"p": "area", "op": "*"}]) == [1, 2, 4]                       # polígonos y la polilínea cerrada
assert ids([{"p": "largo", "op": ">", "v": 40}]) == [3]
assert ids([{"p": "perimetro", "op": "=", "v": 28}]) == [2]
assert ids([{"p": "vertices", "op": "=", "v": 4}]) == [1, 2]
assert ids([{"p": "pos_punto", "x": ["<", 0], "y": ["*", 0]}]) == [8]
assert ids([{"p": "inicio_linea", "x": ["=", 0], "y": [">", 30]}]) == [4, 5]
assert ids([{"p": "centro", "x": ["<", 10], "y": ["<", 10]}]) == [1, 6, 8]
print("ok medidas (área, largo, perímetro, vértices) y posiciones")

# ---- 3. textos, bloques y campos de la tabla ----------------------------------------------
assert ids([{"p": "valor_texto", "op": "=", "v": "lote *"}]) == [6]
assert ids([{"p": "altura_texto", "op": "<", "v": 3}]) == [6]
assert ids([{"p": "nombre_bloque", "op": "=", "v": "ARB*"}]) == [7]
assert ids([{"p": "campo_qgis", "campo": "propietari", "op": "=", "v": "PEREZ*"}]) == [1]
assert ids([{"p": "campo_qgis", "campo": "SUP", "op": ">", "v": 50}]) == [1]
assert ids([{"p": "campo_qgis", "campo": "SUP", "op": "*"}]) == [1, 2]
print("ok textos, bloques y campos de la tabla")

# ---- 4. grupos (el núcleo, como IngeCAD) -----------------------------------------------------
o = [{"p": "**O("}, {"p": "texto"}, {"p": "bloque"}, {"p": "**O)"}]
assert ids(o) == [6, 7]
no = [{"p": "**NO("}, {"p": "capa", "op": "=", "v": "LOTES*"}, {"p": "**NO)"}, {"p": "poligono"}]
assert ids(no) == []
xo = [{"p": "**XO("}, {"p": "poligono"}, {"p": "color", "op": "=", "v": 1}, {"p": "**XO)"}]
assert ids(xo) == [1]
for malo in ([{"p": "**O("}], [{"p": "**Y)"}], [{"p": "**NO("}, {"p": "texto"}, {"p": "punto"}, {"p": "**NO)"}],
             [{"p": "nada"}]):
    try:
        F.filtrar(objs, malo); raise AssertionError(malo)
    except F.FiltroError:
        pass
assert F.sangrias(o) == [0, 1, 1, 0]
assert F.describir({"p": "capa", "op": "=", "v": "LOTES*"}) == ("Capa CAD", "= LOTES*")
assert F.describir({"p": "color", "op": "=", "v": 1}) == ("Color", "= 1 - Rojo")
print("ok grupos Y / O / XO / NO y errores")

# ---- 5. «Agregar objeto seleccionado» -------------------------------------------------------
d = F.de_objeto(objs[5])
assert d[:3] == [{"p": "texto"}, {"p": "capa", "op": "=", "v": "ROTULOS"}, {"p": "color", "op": "=", "v": 3}], d
assert {"p": "valor_texto", "op": "=", "v": "Lote 12"} in d
assert ids(d) == [6]
assert ids(F.de_objeto(objs[0])) == [1]
print("ok agregar objeto seleccionado")

# ---- 6. «Elegir...», campos y guardados aparte de IngeCAD ----------------------------------
assert F.valores_en(objs, "capa") == ["0", "EJES", "LOTES", "LOTES-ESQ", "MOJONES", "ROTULOS", "SIMBOLOS"]
assert F.campos_en(["A", "B"]) == ["A", "B"] and F.campos_en(None) == []
assert F.pedido("fi") == "" and F.pedido("FI rojos") == "rojos" and F.pedido("F") is None
assert F.guardados() == {} and F.ultimo() == []
F.guardar("rojos", [{"p": "color", "op": "=", "v": 1}])
F.recordar([{"p": "poligono"}])
arch = Path(CASA) / ".config" / "geocad" / "filtros_qgis.json"
assert arch.exists() and not (Path(CASA) / ".config" / "geocad" / "filtros.json").exists()
assert set(json.loads(arch.read_text())["filtros"]) == {"rojos", F.SIN_NOMBRE}
assert F.buscar("ROJOS") == [{"p": "color", "op": "=", "v": 1}] and F.ultimo() == [{"p": "poligono"}]
try:
    F.guardar("roto", [{"p": "**O("}]); raise AssertionError("roto")
except F.FiltroError:
    pass
assert F.borrar("rojos") and F.buscar("rojos") is None
print("ok «Elegir», FI <nombre> y guardados en filtros_qgis.json (aparte de IngeCAD)")

# ---- 7. la ventana del núcleo sin Qt --------------------------------------------------------
assert UI.F is F                                     # usa el filtro.py del programa
if UI._qt() is None:
    assert UI.editar(None, [], objs, ["A"]) is UI.SIN_QT
print("ok ventana común")
print("TODO OK")
