"""ENVIARQGIS con una capa importada con IMPORTARSHP (3.27.3): la capa nueva
de QGIS lleva la misma tabla que el .shp de origen (mismas columnas, tipos y
valores). Antes llegaban los polígonos y los textos, pero sin la tabla.

Se arma un .shp latin-1 con texto, enteros, decimales, fecha, lógico y celdas
vacías; se importa como IMPORTARSHP (todas las columnas y sólo algunas), se
manda con la orden ENVIARQGIS y se compara, del lado de QGIS sin QGIS, la tabla
que se arma (campos y valores) con la que lee pyshp del .dbf."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, datetime, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
import shapefile
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext

RAIZ = Path(__file__).resolve().parents[2]
lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
A = import_module("ingecad_plugin_geocad.aqgis")
IX = import_module("ingecad_plugin_geocad.intercambio")
buzon = import_module("ingecad_plugin_geocad.buzon")
sys.path.insert(0, str(RAIZ / "QGIS" / "codigo"))
Q = import_module("geocad.desde_ingecad")

# -- un .shp como PC_2_DE_MAYO: latin-1, campo «key», un nombre igual a uno de GeoCAD
tmp = Path(tempfile.mkdtemp())
shp = tmp / "PC_PRUEBA.shp"
w = shapefile.Writer(str(shp), shapeType=shapefile.POLYGON, encoding="latin-1")
w.field("key", "C", 20)
w.field("NOMENCLA", "C", 60)
w.field("SUP_M2", "N", 19, 11)
w.field("MANZANA", "N", 9, 0)
w.field("PARTIDA", "N", 12, 0)
w.field("ALTA", "D", 8)
w.field("EDIFICADA", "L", 1)
w.field("capa", "C", 10)                  # choca con el «capa» de GeoCAD
FILAS = [
    ["239B", "Señor Ñandú", 1234.56789, 12, 123456789012, datetime.date(2026, 10, 5), True, "A"],
    ["0396", "Pañol", 0.5, 0, 7, datetime.date(1999, 1, 31), False, "B"],
    ["401A", "", None, None, None, None, None, ""],
]
for i, fila in enumerate(FILAS):
    x = 1000.0 * i
    w.poly([[(x, 0), (x, 50), (x + 40, 50), (x + 40, 0), (x, 0)]])
    w.record(*fila)
w.close()
(tmp / "PC_PRUEBA.cpg").write_text("ISO-8859-1")
antes_dbf = shp.with_suffix(".dbf").read_bytes()

r = shapefile.Reader(str(shp), encoding="latin-1")
CAMPOS_DBF = [(f[0], f[1], int(f[2]), int(f[3])) for f in r.fields[1:]]
REGISTROS = [list(rec) for rec in r.records()]
r.close()

CLASE = {"C": str, "N": (int, float), "D": datetime.date, "L": bool}


def igual(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(a - b) < 1e-9
    return a == b


def importar(columnas=None):
    doc = Document(ezdxf.new("R2018")); hist = History(doc)
    op = IX.OpcionesImportar(columnas=None if columnas is None else {str(shp): columnas})
    hist.execute(IX.plan_importar(doc.doc, [shp], op).comando)
    return doc


def enviar(doc):
    """La orden ENVIARQGIS con todo el dibujo elegido; el mensaje que llega a QGIS."""
    log = []
    ctx = ToolContext(execute=History(doc).execute, prompt=lambda s: None, echo=log.append,
                      finish=lambda: None, ask_text=lambda *a: None, ask_choice=lambda *a: None,
                      services=types.SimpleNamespace(document=doc))
    t = lp.spec.tools["QGISEXPORT"](ctx); t.start()
    buzon.receive("qgis")
    t.on_selection(list(doc.doc.modelspace()))
    msgs = buzon.receive("qgis")
    assert len(msgs) == 1, (msgs, log)
    return msgs[0], log


def tabla_qgis(msg):
    """(campos [(nombre, clase de la capa en memoria)], filas) de la capa de polígonos."""
    els = msg["capas"]["poligonos"]
    propios = Q.campos_propios("poligonos", els)
    u = Q.uri("poligonos", msg["crs"], propios)
    campos = [p.split(":", 1) for p in u.split("?", 1)[1].split("&") if p.startswith("field=")]
    campos = [(n[len("field="):], c) for n, c in campos]
    filas = [Q.valores("poligonos", e, propios) for e in els]
    return campos, filas, propios


# -- todas las columnas
doc = importar()
msg, log = enviar(doc)
assert "Enviado a QGIS: 3 polígono(s)." in log[0], log
campos, filas, propios = tabla_qgis(msg)
fijos = [n for n, _c in Q.CAMPOS["poligonos"]]
assert [n for n, _c in campos[:len(fijos)]] == fijos
# las columnas del .dbf, en su orden; «capa» se renombra para no pisar la de GeoCAD
assert [o for _n, _d, o in propios] == [c[0] for c in CAMPOS_DBF], propios
assert [n for n, _c in campos[len(fijos):]] == \
    ["key", "NOMENCLA", "SUP_M2", "MANZANA", "PARTIDA", "ALTA", "EDIFICADA", "capa_1"], campos
# los tipos (y anchos) del .dbf
assert dict(campos[len(fijos):]) == {
    "key": "string(20)", "NOMENCLA": "string(60)", "SUP_M2": "double(19,11)",
    "MANZANA": "integer(9)", "PARTIDA": "long(12)", "ALTA": "date", "EDIFICADA": "boolean",
    "capa_1": "string(10)"}, campos
assert [d for _n, d, _o in propios] == [(t, s, d) for _n, t, s, d in CAMPOS_DBF]
# los valores, fila por fila, en su tipo; vacío = NULL
por_key = {f[len(fijos)]: f for f in filas}
assert len(filas) == len(REGISTROS) == 3
for reg in REGISTROS:
    fila = por_key.get(reg[0])
    assert fila is not None, (reg, filas)
    assert fila[:len(fijos)] == ["PC_PRUEBA", fila[1], "LWPOLYLINE"], fila   # la capa CAD
    for (nombre, t, _s, _d), esperado, llego in zip(CAMPOS_DBF, reg, fila[len(fijos):]):
        if esperado in ("", None):
            assert llego is None, (nombre, esperado, llego)
        else:
            assert isinstance(llego, CLASE[t]) and igual(llego, esperado), (nombre, esperado, llego)
assert por_key["239B"][len(fijos) + 1] == "Señor Ñandú"
assert por_key["239B"][len(fijos) + 4] == 123456789012
assert shp.with_suffix(".dbf").read_bytes() == antes_dbf
print("ok ENVIARQGIS lleva la tabla importada: mismas columnas, tipos y valores")

# -- sólo las columnas tildadas al importar: llegan sólo esas
doc = importar(["key", "SUP_M2"])
msg, _log = enviar(doc)
campos, filas, propios = tabla_qgis(msg)
assert [n for n, _c in campos[len(fijos):]] == ["key", "SUP_M2"], campos
assert sorted(f[len(fijos)] for f in filas) == ["0396", "239B", "401A"]
print("ok sólo las columnas importadas")

# -- lo que no se importó no trae tabla (como antes); dos esquemas distintos = texto
doc = Document(ezdxf.new("R2018")); msp = doc.doc.modelspace()
msp.add_lwpolyline([(0, 0), (5, 0), (5, 5)], close=True)
_t, d = A.elemento(next(iter(msp)), doc.doc)
assert "atributos" not in d and A.elementos(next(iter(msp)), doc.doc)[1][0].get("atributos") is None
assert Q.campos_propios("poligonos", [{"wkt": "x"}]) == []
mezcla = [{"atributos": [["COD", "N", 5, 0, "12"]]}, {"atributos": [["COD", "C", 8, 0, "A-1"]]}]
pr = Q.campos_propios("poligonos", mezcla)
assert pr == [("COD", ("C", 254, 0), "COD")], pr
assert [Q.valores("poligonos", e, pr)[-1] for e in mezcla] == ["12", "A-1"]
# valores que no se leen quedan sin dato (QGIS no descarta la capa entera)
assert Q.valor_dbf("N", 0, "abc") is None and Q.valor_dbf("D", 0, "99/99/9999") is None
assert Q.valor_dbf("D", 0, "05/03/878") == datetime.date(878, 3, 5)      # PC_2_DE_MAYO tiene una
assert Q.valor_dbf("D", 0, "20261005") == datetime.date(2026, 10, 5)
assert Q.valor_dbf("L", 0, "Falso") is False and Q.valor_dbf("D", 0, "05/10/2026") == datetime.date(2026, 10, 5)
print("TODO OK ENVIARQGIS con la tabla importada")
