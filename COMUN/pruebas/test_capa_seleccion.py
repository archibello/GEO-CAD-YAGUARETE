"""CREAR CAPA A PARTIR DE ELEMENTOS SELECCIONADOS en QGIS (3.73.0).

Sin Qt: el nombre de la capa, el filtro por proveedor y que GeoCAD no dependa del
complemento externo. Lo que hace QGIS de verdad lo prueba
ventana/banco_capa_seleccion_qgis_real.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import ast, os, sys, tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
RAIZ = Path(HERE).parent.parent
sys.path[:0] = [HERE, os.path.join(HERE, "fake_qgis"), str(RAIZ / "QGIS" / "codigo")]
os.environ["HOME"] = tempfile.mkdtemp()
from geocad import capa_seleccion as CS, modulos, submodulos

EXTERNO = "create_layer_from_selected_features"

# el nombre: el mismo sufijo del complemento, sin pisar otra capa
assert CS.nombre_libre("Parcelas", []) == "Parcelas_filtered"
assert CS.nombre_libre("P", ["P_filtered"]) == "P_filtered_1"
assert CS.nombre_libre("P", ["P_filtered", "P_filtered_1", "P_filtered_2"]) == "P_filtered_3"

# lo agregado sin guardar tiene id negativo y no se puede filtrar
assert CS.separar({5, -1, 2, -7}) == ([2, 5], [-7, -1])

# cada proveedor con su filtro; un solo id también va en una lista válida
assert CS.filtro("memory", [3]) == "$id IN (3)"
assert CS.filtro("delimitedtext", [2, 9]) == "$id IN (2,9)"
assert CS.filtro("ogr", [0, 4]) == "FID IN (0,4)"                     # shapefile
assert CS.filtro("ogr", [7, 8], ["fid"], [7, 8]) == '"fid" IN (7,8)'  # GeoPackage
assert CS.filtro("postgres", [1], ["gid"], [55]) == '"gid" IN (55)'
assert CS.filtro("spatialite", [1, 2], ["pk"], ["a", "b"]) == "\"pk\" IN ('a','b')"

# comillas: ni el campo ni el texto pueden cortar la condición
assert CS.filtro("postgres", [1], ['raro"id'], ["O'Higgins"]) == "\"raro\"\"id\" IN ('O''Higgins')"

# sin forma segura de filtrar no hay filtro
assert CS.filtro("memory", []) is None
assert CS.filtro("postgres", [1]) is None                            # sin clave
assert CS.filtro("postgres", [1], ["a", "b"], [1]) is None           # compuesta
assert CS.filtro("ogr", [1, 2], ["fid"], [1]) is None                # falta un valor
assert CS.filtro("postgres", [1], ["gid"], [None]) is None
assert CS.filtro("postgres", [1], ["gid"], [1.5]) is None
assert CS.filtro("postgres", [1], ["gid"], [True]) is None

# módulo propio de QGIS, prendido por defecto; IngeCAD no lo tiene
m = next(x for x in modulos.catalogo("qgis") if x.clave == "capa_seleccion")
assert m.nombre == CS.TITULO and m.defecto
assert not [x for x in modulos.catalogo("ingecad") if x.clave == "capa_seleccion"]

# el complemento externo sólo se nombra en la lista de retiro
assert EXTERNO in submodulos.VIEJOS["capa_seleccion"]
codigo = RAIZ / "QGIS" / "codigo" / "geocad"
nombrado = [p.relative_to(codigo).as_posix() for p in codigo.rglob("*.py") if EXTERNO in p.read_text(encoding="utf-8")]
assert nombrado == ["submodulos.py"], nombrado
for nombre in ("capa_seleccion.py", "capa_seleccion_qgis.py"):
    arbol = ast.parse((codigo / nombre).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            assert not (nodo.module or "").startswith("create_layer"), nombre
    assert "qgis.utils" not in (codigo / nombre).read_text(encoding="utf-8"), nombre

# se retira guardando una copia, y apagado el módulo el complemento ni se mira
plugins = Path(tempfile.mkdtemp())
(plugins / EXTERNO).mkdir()
(plugins / EXTERNO / "metadata.txt").write_text("x", encoding="utf-8")
assert submodulos.retirar_viejos("capa_seleccion", plugins) == [EXTERNO]
assert not (plugins / EXTERNO).exists()
assert (plugins / (".anterior-" + EXTERNO) / "metadata.txt").read_text(encoding="utf-8") == "x"
assert submodulos.retirar_viejos("capa_seleccion", plugins) == []

# conectado y descargado en plugin.py; sólo se retira si la herramienta propia arrancó
p = (codigo / "plugin.py").read_text(encoding="utf-8")
assert "self._sync_capa_seleccion()" in p and "self._quitar_capa_seleccion()" in p
assert p.index("CapaSeleccionQgis(self.iface)") < p.index('retirar_viejos("capa_seleccion"')
assert '"geocad:capaseleccion"' in p
q = (RAIZ / "COMUN" / "nucleo" / "botones.py").read_text(encoding="utf-8")
assert '"geocad:capaseleccion"' in q

print("TODO OK capa_seleccion")
