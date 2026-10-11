"""Enviar a QGIS como capas nuevas (3.20.0, ENVIARQGIS): cualquier objeto de
IngeCAD, venga o no de QGIS, viaja como capa temporal por tipo (puntos,
líneas, polígonos, textos). Lado IngeCAD (qué sale de cada objeto, el
mensaje) y lado QGIS sin QGIS (campos, direcciones de las capas en memoria)."""
import os, sys, tempfile, types, math
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
from importlib import import_module
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext

RAIZ = Path(__file__).resolve().parents[2]
lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
spec = lp.spec
A = import_module("ingecad_plugin_geocad.aqgis")
buzon = import_module("ingecad_plugin_geocad.buzon")
barra = import_module("ingecad_plugin_geocad.barra")
yag = import_module("ingecad_plugin_geocad.yaguarete")

# -- la orden, el botón (tema Puente de la barra GeoCAD), el menú y el nombre en español
assert "QGISEXPORT" in spec.tools
botones = [t.command for t in spec.toolbar]
assert "QGISEXPORT" in botones and barra.TEMAS["QGISEXPORT"] == "puente"
assert all(Path(t.icon).exists() for t in spec.toolbar if t.command == "QGISEXPORT")
assert "QGISEXPORT" in yag.DESCRIPCIONES
import json
gd = RAIZ / "INGECAD" / "codigo" / "geocad" / "i18n" / "es"
assert json.loads((gd / "commands.json").read_text())["QGISEXPORT"]["name"] == "ENVIARQGIS"
assert "Send selection to QGIS as new layers" in json.loads((gd / "ui.json").read_text())
print("ok orden")

# -- WKT
assert A.wkt_linea([(0, 0), (0, 0), (1.5, 2)]) == "LINESTRING (0 0, 1.5 2)"
assert A.wkt_linea([(1, 1), (1, 1)]) is None
assert A.wkt_poligono([[(0, 0), (4, 0), (4, 3), (0, 0)]]) == "POLYGON ((0 0, 4 0, 4 3, 0 0))"
assert A.wkt_poligono([[(0, 0), (4, 0)]]) is None
assert A.wkt_punto((5430000.123456789, -0.0000001)) == "POINT (5430000.123457 0)"

# -- cada objeto a su tipo
doc = Document.new(); msp = doc.doc.modelspace()
doc.doc.layers.add("MUROS", color=1)
p = msp.add_point((1, 2), dxfattribs={"layer": "MUROS"})
blk = doc.doc.blocks.new("ARBOL"); blk.add_circle((0, 0), 1)
ins = msp.add_blockref("ARBOL", (10, 20), dxfattribs={"rotation": 30, "xscale": 2, "color": 3})
ln = msp.add_line((0, 0), (10, 0))
abierta = msp.add_lwpolyline([(0, 0), (5, 0), (5, 5)])
cerrada = msp.add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
curva = msp.add_lwpolyline([(0, 0, 0, 0, 1), (10, 0)], format="xyseb", close=True)  # medio círculo + cuerda
circ = msp.add_circle((100, 100), 5)
arco = msp.add_arc((0, 0), 10, 0, 90)
txt = msp.add_text("Lote 3", height=2.5, rotation=15, dxfattribs={"insert": (7, 8)})
mtx = msp.add_mtext("Calle\\PNorte", dxfattribs={"insert": (3, 4), "char_height": 1.2})
hat = msp.add_hatch(color=5)
hat.paths.add_polyline_path([(0, 0), (30, 0), (30, 30), (0, 30)], is_closed=True)
hat.paths.add_polyline_path([(10, 10), (20, 10), (20, 20), (10, 20)], is_closed=True)
dim = msp.add_linear_dim(base=(0, 5), p1=(0, 0), p2=(10, 0)).dimension

tipo = lambda e: A.elementos(e, doc.doc)[0]
assert tipo(p) == "puntos" and tipo(ins) == "puntos" and tipo(txt) == "textos" and tipo(mtx) == "textos"
assert tipo(ln) == "lineas" and tipo(abierta) == "lineas" and tipo(arco) == "lineas"
assert tipo(cerrada) == "poligonos" and tipo(circ) == "poligonos" and tipo(hat) == "poligonos"
assert tipo(curva) == "poligonos"
assert A.elementos(dim, doc.doc) == (None, "DIMENSION")

_t, d = A.elemento(p, doc.doc)
assert d == {"capa": "MUROS", "color": "#ff0000", "tipo_cad": "POINT", "wkt": "POINT (1 2)"}, d
_t, d = A.elemento(ins, doc.doc)
assert d["bloque"] == "ARBOL" and d["giro"] == 30 and d["escala"] == 2 and d["color"] == "#00ff00", d
_t, d = A.elemento(ln, doc.doc)
assert d["wkt"] == "LINESTRING (0 0, 10 0)" and d["color"] == "#000000" and d["capa"] == "0"
_t, d = A.elemento(cerrada, doc.doc)
assert d["wkt"] == "POLYGON ((0 0, 20 0, 20 10, 0 10, 0 0))", d["wkt"]


def extremos(wkt):
    return [tuple(map(float, v.split())) for v in wkt[len("LINESTRING ("):-1].split(", ")]


# los textos: una línea por el medio de la letra, del ancho del texto, en su dirección
_t, [d] = A.elementos(txt, doc.doc)
assert d["etiqueta"] == "Lote 3" and d["altura"] == 2.5 and d["giro"] == 15 and "texto" not in d
(x1, y1), (x2, y2) = extremos(d["wkt"])
ancho = A.ancho_texto("Lote 3", 2.5)
assert ancho > 5 and abs(math.hypot(x2 - x1, y2 - y1) - ancho) < 1e-4
assert abs(math.degrees(math.atan2(y2 - y1, x2 - x1)) - 15) < 1e-4       # su dirección
medio = A._girar((7, 8), 15, 0, 1.25)                                     # mitad de la letra
assert abs(x1 - medio[0]) < 1e-5 and abs(y1 - medio[1]) < 1e-5
# alineado al centro: la línea queda centrada en el punto de alineación
cen = msp.add_text("ABC", height=1, dxfattribs={"halign": 1, "align_point": (50, 50), "insert": (50, 50)})
(a1, b1), (a2, b2) = extremos(A.elementos(cen, doc.doc)[1][0]["wkt"])
assert abs((a1 + a2) / 2 - 50) < 1e-5 and abs(b1 - 50.5) < 1e-5 and b1 == b2
cen.destroy()
# MTEXT: un renglón por línea, uno debajo del otro
_t, ds = A.elementos(mtx, doc.doc)
assert [d["etiqueta"] for d in ds] == ["Calle", "Norte"] and all(d["altura"] == 1.2 for d in ds)
(p1, _q1), (p2, _q2) = extremos(ds[0]["wkt"]), extremos(ds[1]["wkt"])
assert abs(p1[0] - 3) < 1e-5 and abs(p1[1] - (4 - 0.6)) < 1e-5            # arriba-izq (adjunto 1)
assert abs(p2[1] - (p1[1] - 1.2 * A.INTERLINEA)) < 1e-5
vacio = msp.add_text("   ", height=1)
assert A.elementos(vacio, doc.doc)[0] in (None, "textos"); vacio.destroy()
_t, d = A.elemento(hat, doc.doc)
assert d["wkt"].count("(") == 3 and d["color"] == "#0000ff", d     # borde + un hueco


def vertices(wkt):
    return [tuple(map(float, v.split())) for v in wkt.split("((")[1].split(")")[0].split(", ")]


# los arcos se pasan a tramos que no se apartan más que la tolerancia
_t, d = A.elemento(circ, doc.doc)
vs = vertices(d["wkt"]); assert len(vs) > 30 and vs[0] == vs[-1]
assert max(abs(math.hypot(x - 100, y - 100) - 5) for x, y in vs) < A.TOLERANCIA
_t, d = A.elemento(arco, doc.doc)
assert d["wkt"].startswith("LINESTRING (10 0,") and d["wkt"].endswith("0 10)"), d["wkt"]
print("ok objetos")

# -- todo junto: capas por tipo y lo salteado
capas, salteados = A.armar(list(msp), doc.doc)
assert sorted(capas) == ["lineas", "poligonos", "puntos", "textos"]
assert len(capas["puntos"]) == 2 and len(capas["textos"]) == 3 and len(capas["lineas"]) == 3
assert len(capas["poligonos"]) == 4 and salteados == {"DIMENSION": 1}
r = A.resumen(capas, salteados)
assert r == ("Enviado a QGIS: 2 punto(s), 3 línea(s), 4 polígono(s), 3 texto(s). "
             "Salteado: 1 DIMENSION."), r
assert A.resumen({}, {}) == "Nada para enviar."
print("ok armar")

# -- el sistema de coordenadas: el de la configuración común si no hay otro
config = import_module("ingecad_plugin_geocad.config")
assert A.crs_del_dibujo(doc) == ""
config.save({"crs_proyecto": "EPSG:5347"}, "IngeCAD")
assert A.crs_del_dibujo(doc) == "EPSG:5347"

# -- la orden: manda el mensaje al buzón de QGIS
log = []
ctx = ToolContext(execute=History(doc).execute, prompt=lambda s: None, echo=log.append,
                  finish=lambda: None, ask_text=lambda *a: None, ask_choice=lambda *a: None,
                  services=types.SimpleNamespace(document=doc))
t = spec.tools["QGISEXPORT"](ctx); t.start()
assert "capas nuevas" in t.selection_prompt()
buzon.receive("qgis")
t.on_selection([p, ln, cerrada, txt, dim])
msgs = buzon.receive("qgis")
assert len(msgs) == 1 and msgs[0]["tipo"] == "capas_nuevas" and msgs[0]["crs"] == "EPSG:5347"
assert sorted(msgs[0]["capas"]) == ["lineas", "poligonos", "puntos", "textos"]
assert "Enviado a QGIS: 1 punto(s), 1 línea(s), 1 polígono(s), 1 texto(s)." in log[0], log
assert any("QGIS no está abierto" in x for x in log), log
log.clear(); t.on_selection([dim])
assert not buzon.receive("qgis") and log[0] == "Nada para enviar. Salteado: 1 DIMENSION.", log
log.clear(); t.on_selection([])
assert log == ["No se seleccionó nada."]
print("ok orden ENVIARQGIS")

# -- lado QGIS sin QGIS
sys.path.insert(0, str(RAIZ / "QGIS" / "codigo"))
Q = import_module("geocad.desde_ingecad")
assert Q.TIPO_MENSAJE == A.TIPO_MENSAJE and set(Q.TIPOS) == set(A.TIPOS)
assert Q.uri("puntos", "EPSG:5347") == ("Point?crs=EPSG:5347&field=capa:string&field=color:string"
                                       "&field=tipo_cad:string&field=bloque:string"
                                       "&field=giro:double&field=escala:double")
assert Q.uri("poligonos", "").startswith("Polygon?field=capa:string")
assert [n for _t, n, _l in Q.capas_del_mensaje(msgs[0])] == ["Textos", "Puntos", "Líneas", "Polígonos"]
assert Q.capas_del_mensaje({"capas": {"lineas": []}}) == []
assert Q.uri("textos", "").startswith("LineString?field=capa:string")
assert Q.valores("textos", {"capa": "0", "etiqueta": "Lote 3", "altura": "2.5"}) == \
    ["0", None, None, "Lote 3", 2.5, None]
assert Q.valores("puntos", {"giro": "x"})[4] is None
assert Q.nombre_grupo("plano.dxf", 0).startswith("Desde IngeCAD - plano.dxf (")
assert Q.nombre_grupo("", 0).startswith("Desde IngeCAD (")
assert Q.resumen(msgs[0]) == "1 textos, 1 puntos, 1 líneas, 1 polígonos"
# los campos de QGIS son los que manda IngeCAD
for tipo_q, lista in capas.items():
    for elemento in lista:
        assert set(elemento) - {"wkt"} <= {n for n, _c in Q.CAMPOS[tipo_q]}, (tipo_q, elemento)
print("TODO OK ENVIARQGIS")
