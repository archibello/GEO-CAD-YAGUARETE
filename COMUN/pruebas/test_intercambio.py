"""Módulo «Intercambio» para IngeCAD (3.25.0): sistema de coordenadas del
dibujo (SISTEMAGEO), REPROYECTAR con un solo deshacer exacto, IMPORTARSHP
(llevado al sistema del dibujo, con sus atributos en cada objeto) y
EXPORTARSHP (por capa y tipo o por tipo con LAYER, en el sistema del dibujo
u otro, con .prj y .cpg). Ida y vuelta: importar y exportar devuelve los
mismos atributos y las mismas coordenadas."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import datetime, math, os, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
import shapefile
from pyproj import Transformer
from core.commands import History
from core.document import Document
from core.georef import Georef, read_georef, write_georef
from core.plugins import load_plugin

import fixtures

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
IX = import_module("ingecad_plugin_geocad.intercambio")
enlace = import_module("ingecad_plugin_geocad.enlace")
mods = import_module("ingecad_plugin_geocad.modulos")
barra = import_module("ingecad_plugin_geocad.barra")
plugin = import_module("ingecad_plugin_geocad")


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ------------------------------------------------------------- 1. menú, barra y módulo
spec = plugin.construir_spec()
ORDENES = ("GEOCRS", "GEOREPROJECT", "GEOIMPORTSHP", "GEOEXPORTSHP")
assert set(ORDENES) <= set(spec.tools) | set(spec.commands), "faltan las órdenes"
sub = {getattr(s, "label", ""): s for s in spec.menu}
assert {"Coordinate system", "Import", "Export"} <= set(sub), list(sub)
assert [i.command for i in sub["Coordinate system"].items] == ["GEOCRS", "GEOREPROJECT"]
assert [i.command for i in sub["Import"].items] == ["GEOIMPORTSHP", "GEOIMPORTKML"]   # 3.30.0
assert [i.command for i in sub["Export"].items] == ["GEOEXPORTSHP", "GEOEXPORTKML"]   # 3.29.0
assert {t.command for t in spec.toolbar} >= set(ORDENES)
assert all(barra.TEMAS.get(o) == "intercambio" for o in ORDENES)
assert spec.aliases.get("MAPCSASSIGN") == "GEOCRS" and spec.aliases.get("MAPIMPORT") == "GEOIMPORTSHP"
import json
es = json.loads((Path(plugin.__file__).parent / "i18n" / "es" / "commands.json").read_text())
assert [es[o]["name"] for o in ORDENES] == ["SISTEMAGEO", "REPROYECTAR", "IMPORTARSHP", "EXPORTARSHP"]
ui = json.loads((Path(plugin.__file__).parent / "i18n" / "es" / "ui.json").read_text())
for s in ("Coordinate system", "Import", "Export"):
    assert s in ui, s
    for i in sub[s].items:
        assert i.label in ui, i.label
mods.poner("ingecad", "intercambio", False)
s2 = plugin.construir_spec()
assert not set(ORDENES) & (set(s2.tools) | set(s2.commands))
assert not {"Coordinate system", "Import", "Export"} & {getattr(s, "label", "") for s in s2.menu}
mods.poner("ingecad", "intercambio", True)
print("ok menú, barra y módulo")

# ------------------------------------------------------------- 2. los sistemas
lista = IX.lista_corta()
assert ("EPSG:5347", "POSGAR 2007 / Argentina faja 5") in lista and len(lista) == 4 * 7 + 5
assert IX.normalizar(" epsg: 22195") == "EPSG:22195" and IX.normalizar("5347") == "EPSG:5347"
assert IX.normalizar("hola") == ""
assert IX.validar("EPSG:5347") == ""
assert "geográfico" in IX.validar("EPSG:4326")
assert IX.validar("EPSG:999999") and IX.validar("")
assert IX.nombre("EPSG:22195").startswith("Campo Inchauspe / Argentina faja 5")
assert "27700" in IX.nombre("EPSG:27700") and IX.nombre("") == "sin definir"
assert IX.sistema_de(Georef(19, False, "WGS84")) == "EPSG:32719"
assert IX.sistema_de(Georef(18, False, "PSAD56")) == "EPSG:24878"
assert IX.sistema_de(Georef(crs="EPSG:5347")) == "EPSG:5347" and IX.sistema_de(None) == ""
print("ok sistemas")

# ------------------------------------------------------------- 3. SISTEMAGEO: declarar sin mover
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
msp.add_point((5_500_000.0, 6_200_000.0))
assert IX.sistema_del_dibujo(doc.doc) == ""
hist.execute(IX.DefinirSistemaCommand("EPSG:22195"))
assert IX.sistema_del_dibujo(doc.doc) == "EPSG:22195"
assert read_georef(doc.doc).crs == "EPSG:22195"           # el GEOREF de IngeCAD: lo ve Terreno
assert cerca(list(msp)[0].dxf.location, (5_500_000.0, 6_200_000.0, 0))  # no movió nada
hist.execute(IX.DefinirSistemaCommand("EPSG:5347"))
hist.undo(); assert IX.sistema_del_dibujo(doc.doc) == "EPSG:22195"
hist.undo(); assert IX.sistema_del_dibujo(doc.doc) == "" and read_georef(doc.doc) is None
print("ok SISTEMAGEO")

# ------------------------------------------------------------- 4. REPROYECTAR
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
X0, Y0 = 5_430_000.0, 6_300_000.0                   # faja 5
pt = msp.add_point((X0, Y0, 7.5))
ln = msp.add_line((X0, Y0), (X0 + 100, Y0 + 50))
pl = msp.add_lwpolyline([(X0, Y0), (X0 + 20, Y0), (X0 + 20, Y0 + 30)], close=True)
ci = msp.add_circle((X0 + 50, Y0 + 50), 5)
ar = msp.add_arc((X0 + 60, Y0 + 60), 4, 10, 80)
tx = msp.add_text("LOTE 1", dxfattribs={"insert": (X0 + 5, Y0 + 5), "height": 2, "rotation": 30})
mt = msp.add_mtext("Hola\\Pmundo", dxfattribs={"insert": (X0 + 8, Y0 + 8), "char_height": 1.5})
blk = doc.doc.blocks.new("MOJON"); blk.add_circle((0, 0), 0.5); blk.add_attdef("NUM", (0, 1))
ins = msp.add_blockref("MOJON", (X0 + 70, Y0 + 10), dxfattribs={"rotation": 15})
ins.add_auto_attribs({"NUM": "M-1"})
giro_attrib = ins.attribs[0].dxf.rotation
att_ins = tuple(ins.attribs[0].dxf.insert)
ha = msp.add_hatch(color=3); ha.paths.add_polyline_path([(X0, Y0 - 10), (X0 + 10, Y0 - 10), (X0 + 10, Y0 - 20)])
sp = msp.add_spline([(X0, Y0 + 90), (X0 + 10, Y0 + 95), (X0 + 20, Y0 + 90)])
con = msp.add_lwpolyline([(X0, Y0), (X0 + 1, Y0 + 1)])
enlace.set_feat_tag(con, "SHP-catastro", 3, 0)           # de una capa CONECTADA: no se toca
antes = {id(e): e.dxfattribs() for e in msp}
pl_antes = list(pl.get_points("xyseb"))

try:
    IX.preparar_reproyeccion(doc.doc, "EPSG:5347")
    raise AssertionError("sin sistema no se puede reproyectar")
except ValueError as exc:
    assert "SISTEMAGEO" in str(exc)
write_georef(doc.doc, Georef(crs="EPSG:22195"))           # Campo Inchauspe faja 5
try:
    IX.preparar_reproyeccion(doc.doc, "EPSG:22195"); raise AssertionError
except ValueError:
    pass
cmd, conectados = IX.preparar_reproyeccion(doc.doc, "EPSG:5346")   # a POSGAR 2007 faja 4
assert conectados == 1
hist.execute(cmd)
T = Transformer.from_crs("EPSG:22195", "EPSG:5346", always_xy=True)
assert IX.sistema_del_dibujo(doc.doc) == "EPSG:5346"
assert cerca(pt.dxf.location, (*T.transform(X0, Y0), 7.5), 1e-6)        # la Z queda
assert cerca(ln.dxf.end, (*T.transform(X0 + 100, Y0 + 50), 0), 1e-6)
assert cerca(pl.get_points("xy")[2], T.transform(X0 + 20, Y0 + 30), 1e-6) and pl.closed
assert cerca(ci.dxf.center, (*T.transform(X0 + 50, Y0 + 50), 0), 1e-6) and ci.dxf.radius == 5
# de faja 5 a faja 4 el norte gira (convergencia): textos, bloques y arcos giran con él
x0, y0 = T.transform(X0 + 5, Y0 + 5); x1, y1 = T.transform(X0 + 6, Y0 + 5)
g = math.degrees(math.atan2(y1 - y0, x1 - x0))
assert abs(g) > 1.0, g                                       # de verdad gira
assert abs(tx.dxf.rotation - (30 + g) % 360) < 1e-3
assert abs(ins.dxf.rotation - (15 + g) % 360) < 1e-3
assert abs(ins.attribs[0].dxf.rotation - (giro_attrib + g) % 360) < 1e-3
assert cerca(ins.attribs[0].dxf.insert, (*T.transform(*att_ins[:2]), 0), 1e-6)
assert abs((ar.dxf.start_angle - 10 - g) % 360) < 1e-2
assert cerca(mt.dxf.insert, (*T.transform(X0 + 8, Y0 + 8), 0), 1e-6)
assert cerca(ha.paths[0].vertices[1][:2], T.transform(X0 + 10, Y0 - 10), 1e-6)
assert cerca(sp.fit_points[0][:2], T.transform(X0, Y0 + 90), 1e-6)
assert con.dxf.handle and cerca(con.get_points("xy")[0], (X0, Y0))     # la conectada quedó
texto = IX.resumen_reproyeccion(cmd, conectados)
assert "POSGAR 2007 / Argentina faja 4" in texto and "1 objeto(s) de capas conectadas" in texto
# un solo deshacer y exacto
hist.undo()
assert IX.sistema_del_dibujo(doc.doc) == "EPSG:22195"
for e in msp:
    assert e.dxfattribs() == antes[id(e)], (e.dxftype(), e.dxfattribs(), antes[id(e)])
assert list(pl.get_points("xyseb")) == pl_antes
assert ins.attribs[0].dxf.rotation == giro_attrib and ins.attribs[0].dxf.text == "M-1"
hist.redo(); assert IX.sistema_del_dibujo(doc.doc) == "EPSG:5346"
assert cerca(pt.dxf.location, (*T.transform(X0, Y0), 7.5), 1e-6)
print("ok REPROYECTAR (convierte, gira, respeta las conectadas, un deshacer exacto)")

# sólo la selección
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
a = msp.add_point((X0, Y0)); b = msp.add_point((X0 + 1, Y0 + 1))
write_georef(doc.doc, Georef(crs="EPSG:22195"))
cmd, _c = IX.preparar_reproyeccion(doc.doc, "EPSG:5347", [a])
hist.execute(cmd)
assert not cerca(a.dxf.location, (X0, Y0), 1.0) and cerca(b.dxf.location, (X0 + 1, Y0 + 1, 0))
print("ok REPROYECTAR la selección")

# ------------------------------------------------------------- 5. IMPORTARSHP
tmp = tempfile.mkdtemp()
parcelas = fixtures.make_parcelas(tmp)          # .prj POSGAR 2007 faja 5 (sólo el nombre)
red = fixtures.make_red(tmp)                    # sin .prj
pozos = fixtures.make_puntos(tmp)
v = IX.ver_shp(parcelas)
assert v.tipo == "Polygon" and v.cantidad == 5 and v.sistema == "EPSG:5347" and v.codificacion == "utf-8"
assert "TITULAR" in v.campos
assert IX.ver_shp(red).sistema == ""

# dibujo sin sistema: adopta el del SHP
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
plan = IX.plan_importar(doc.doc, [parcelas], IX.OpcionesImportar())
hist.execute(plan.comando)
assert plan.sistema_adoptado == "EPSG:5347" and IX.sistema_del_dibujo(doc.doc) == "EPSG:5347"
polis = list(msp.query("LWPOLYLINE"))
assert len(polis) == 6 and all(p.closed for p in polis)      # 5 parcelas + el hueco
assert {p.dxf.layer for p in polis} == {"parcelas"} and "parcelas" in doc.doc.layers
origen, at = IX.atributos(polis[0])
assert origen == "parcelas"
d = {n: (t, x) for n, t, x in at}
assert d["PARTIDA"] == (("C", 12, 0), "01-0000") and d["TITULAR"][1] == "Pérez"
assert d["SUP_M2"] == (("N", 12, 2), "500.0") and d["FECHA"][1] == "15/01/2024"
assert cerca(polis[0].get_points("xy")[0], (5_430_000.0, 6_300_000.0))
assert not list(msp.query("TEXT"))                                    # sin rótulos: van después
assert plan.tablas == ["parcelas"]
assert "El dibujo adoptó el sistema POSGAR 2007" in IX.resumen_importar(plan)
assert "Base de datos: «parcelas»" in IX.resumen_importar(plan)
hist.undo()
assert not list(msp) and IX.sistema_del_dibujo(doc.doc) == "" and "parcelas" not in doc.doc.layers
print("ok IMPORTARSHP: adopta el sistema, atributos en cada objeto, sin rótulos, un deshacer")

# dibujo en Campo Inchauspe: el SHP en POSGAR 2007 se reproyecta
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
write_georef(doc.doc, Georef(crs="EPSG:22195"))
plan = IX.plan_importar(doc.doc, [parcelas, red, pozos],
                        IX.OpcionesImportar(capa="campo", campo_capa="MANZANA", atributos=True))
hist.execute(plan.comando)
T = Transformer.from_crs("EPSG:5347", "EPSG:22195", always_xy=True)
pol = next(p for p in msp.query("LWPOLYLINE") if p.closed)
assert pol.dxf.layer == "12"                                         # capa según el campo
assert cerca(pol.get_points("xy")[0], T.transform(5_430_000.0, 6_300_000.0), 1e-6)
assert not plan.sistema_adoptado and IX.sistema_del_dibujo(doc.doc) == "EPSG:22195"
assert any("red: no tiene .prj" in a for a in plan.avisos)
ptos = list(msp.query("POINT"))
assert len(ptos) == 3 and cerca(ptos[0].dxf.location, (100.0, 200.0, 0))      # sin .prj: como viene
nombres = [n for n, *_r in plan.por_archivo]
assert nombres == ["parcelas", "red", "pozos"]
assert "de POSGAR 2007 / Argentina faja 5" in plan.por_archivo[0][4]
print("ok IMPORTARSHP: reproyecta al sistema del dibujo; sin .prj entra como viene y avisa")

# el sistema de un SHP sin .prj, elegido en la ventana
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
write_georef(doc.doc, Georef(crs="EPSG:5347"))
op = IX.OpcionesImportar(sistema_shp={str(Path(pozos)): "EPSG:5347"}, puntos="texto",
                         campo_texto="NOMBRE", altura=1.0, atributos=False)
plan = IX.plan_importar(doc.doc, [pozos], op)
hist.execute(plan.comando)
txt = list(msp.query("TEXT"))
assert [t.dxf.text for t in txt] == ["P1", "P2", "P3"] and not plan.avisos
assert IX.atributos(txt[0]) == ("", [])                                # sin atributos
# bloque que no existe: puntos y aviso
plan = IX.plan_importar(doc.doc, [pozos], IX.OpcionesImportar(puntos="bloque", bloque="NOESTA"))
assert any("NOESTA" in a for a in plan.avisos)
print("ok IMPORTARSHP: sistema elegido, puntos como texto, bloque inexistente")

# ------------------------------------------------------------- 5b. la base de datos importada (3.25.1)
D = import_module("ingecad_plugin_geocad.datos")
IMP = import_module("ingecad_plugin_geocad.importados")
HD = import_module("ingecad_plugin_geocad.herramientas_datos")
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
write_georef(doc.doc, Georef(crs="EPSG:5347"))
hist.execute(IX.plan_importar(doc.doc, [parcelas, pozos], IX.OpcionesImportar()).comando)
assert set(D.data_tables(doc)) == {"parcelas", "pozos"}
assert "importado, 5 registros" in D.data_tables(doc)["parcelas"]
data = D.layer_data(doc, "parcelas")
assert data.kind == "polygon" and D.layer_data(doc, "pozos").kind == "point"
assert [r.fid for r in data.rows] == [0, 1, 2, 3, 4]                  # el hueco no es otra fila
assert len(data.entities_by_fid(doc)[2]) == 2
assert data.row(1).values["TITULAR"] == "Gómez" and data.row(1).values["SUP_M2"] == 501.0
assert data.row(0).values["FECHA"] == datetime.date(2024, 1, 15) and data.row(0).values["EDIFICADO"] is True
assert [f.name for f in data.fields][:3] == ["PARTIDA", "TITULAR", "SUP_M2"]
st = D.TableState(doc, "parcelas")
assert st.columns[-1] == "Área" and len(st.rows) == 5 and abs(st._measures[2] - (500 - 25)) < 1e-6
st.set_query("SUP_M2 > 502"); assert [r.fid for r in st.rows] == [3, 4]
hueco = data.entities_by_fid(doc)[2][1]
assert D.fid_of(doc, hueco, "parcelas") == 2 and D.fid_of(doc, hueco, "pozos") is None
assert sorted(fid for fid, _e in D.tagged(doc, "pozos")) == [0, 1, 2]
# editar: valida como el .dbf, cambia todas las partes, un deshacer
try:
    data.validate("SUP_M2", "mucho"); raise AssertionError
except IX.shpio.ShapefileError:
    pass
data.validate("TITULAR", "Fernández")
hist.execute(D.edit_command(doc, "parcelas", 2, "TITULAR", "Fernández"))
assert {dict((n, x) for n, _t, x in IX.atributos(e)[1])["TITULAR"]
        for e in D.layer_data(doc, "parcelas").entities_by_fid(doc)[2]} == {"Fernández"}
assert D.layer_data(doc, "parcelas").row(2).values["TITULAR"] == "Fernández"
hist.undo(); assert D.layer_data(doc, "parcelas").row(2).values["TITULAR"] == "Núñez"
hist.redo()
# consultas y rótulos después, desde la base (CONSULTASIG, ROTULOSIG)
ctx = types.SimpleNamespace(services=types.SimpleNamespace(), echo=lambda *_a: None)
fids = HD.run_query(ctx, doc, "parcelas", "TITULAR CONTIENE 'fern'")
assert fids == [2]
cmd, n, _old = HD.label_commands(doc, "parcelas", "PARTIDA", 2.0)
hist.execute(cmd)
rot = [t for t in msp.query("TEXT") if t.dxf.layer == "parcelas-ROTULOS"]
assert n == 5 and len(rot) == 5 and {t.dxf.text for t in rot} == {f"01-{i:04d}" for i in range(5)}
# importar otra vez el mismo archivo: otra tabla, no se mezclan
plan = IX.plan_importar(doc.doc, [parcelas], IX.OpcionesImportar())
hist.execute(plan.comando)
assert plan.tablas == ["parcelas (2)"] and D.data_tables(doc).keys() >= {"parcelas", "parcelas (2)"}
assert len(D.layer_data(doc, "parcelas (2)").rows) == 5
# color y espesor de las capas que se crean; las que ya estaban no se tocan
plan = IX.plan_importar(doc.doc, [pozos, parcelas], IX.OpcionesImportar(color=3, grosor=50))
hist.execute(plan.comando)
assert doc.doc.layers.get("parcelas").color != 3
assert any("parcelas" in a and "conservan" in a for a in plan.avisos), plan.avisos
hist.undo()
doc_c = Document(ezdxf.new("R2018")); h_c = History(doc_c)
h_c.execute(IX.plan_importar(doc_c.doc, [parcelas], IX.OpcionesImportar(color=3, grosor=50)).comando)
assert doc_c.doc.layers.get("parcelas").color == 3 and doc_c.doc.layers.get("parcelas").dxf.lineweight == 50
assert all(e.dxf.color == 256 for e in doc_c.doc.modelspace())          # los objetos, por capa
h_c.execute(IX.plan_importar(doc_c.doc, [pozos], IX.OpcionesImportar()).comando)
assert doc_c.doc.layers.get("pozos").color == 7 and doc_c.doc.layers.get("pozos").dxf.lineweight == -3
# sólo la geometría: no hay tabla
plan = IX.plan_importar(doc.doc, [red], IX.OpcionesImportar(atributos=False))
assert plan.tablas == [] and "Base de datos" not in IX.resumen_importar(plan)
# lo editado sale con EXPORTARSHP
ents = [e for _f, e in D.tagged(doc, "parcelas")]
outx = Path(tempfile.mkdtemp())
IX.escribir(IX.plan_exportar(ents, doc.doc, "capa"), outx)
r = shapefile.Reader(str(outx / "parcelas_poligonos.shp"), encoding="utf-8")
assert "Fernández" in {rec.as_dict()["TITULAR"] for rec in r.records()}
# lo importado con 3.25.0 (sin número de registro) también se ve: una fila por objeto
viejo = msp.add_point((1, 1))
IMP.poner_atributos(viejo, "viejo", [IX.shpio.DbfField("A", "C", 5, 0, 0)], {"A": "x"})
assert [r.values["A"] for r in D.layer_data(doc, "viejo").rows] == ["x"]
assert D.fid_of(doc, viejo, "viejo") is not None
print("ok la base de datos importada: tabla, consulta, edición con deshacer, rótulos, exportar")

# con una presentación abierta, lo importado y sus rótulos van igual al MODELO (3.25.4:
# ROTULOSIG con la lámina abierta dejaba 652 rótulos en el papel y la hoja se veía rota)
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
write_georef(doc.doc, Georef(crs="EPSG:5347"))
doc.active_layout = "Layout1"
papel = doc.doc.layouts.get("Layout1")
assert doc.current_space() is papel
hist.execute(IX.plan_importar(doc.doc, [parcelas], IX.OpcionesImportar()).comando)
assert len(list(msp.query("LWPOLYLINE"))) == 6 and not list(papel.query("LWPOLYLINE"))
cmd, n, _old = HD.label_commands(doc, "parcelas", "PARTIDA", 2.0)
hist.execute(cmd)
assert n == 5 and len(list(msp.query("TEXT"))) == 5 and not list(papel.query("TEXT"))
# rótulos que ya quedaron en el papel (dibujos hechos antes): ROTULOSIG los reemplaza
viejo = papel.add_text("01-0000", dxfattribs={"layer": "parcelas-ROTULOS"})
viejo.set_xdata(HD.APPID, [(1000, HD.LABEL_TAG), (1000, "parcelas"), (1071, 0), (1000, "PARTIDA")])
assert len(HD.existing_labels(doc, "parcelas")) == 6
cmd, n, old = HD.label_commands(doc, "parcelas", "PARTIDA", 2.0)
hist.execute(cmd)
assert old == 6 and not list(papel.query("TEXT")) and len(list(msp.query("TEXT"))) == 5
hist.undo(); assert len(list(papel.query("TEXT"))) == 1           # deshacer lo devuelve a su lugar
hist.redo()
# QUITARROTULOS borra también los del papel
hist.undo()
hist.execute(HD.CompositeCommand("quitar", HD.erase_labels(doc, "parcelas")))
assert not HD.existing_labels(doc, "parcelas")
print("ok con la lámina abierta: importar y rotular van al modelo; los rótulos que quedaron en el papel se quitan")

# ------------------------------------------------------------- 6. EXPORTARSHP
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
hist.execute(IX.plan_importar(doc.doc, [parcelas], IX.OpcionesImportar()).comando)
msp.add_line((5_430_000.0, 6_300_100.0), (5_430_050.0, 6_300_100.0), dxfattribs={"layer": "EJES"})
msp.add_circle((5_430_100.0, 6_300_100.0), 3, dxfattribs={"layer": "EJES"})
msp.add_text("MZA 12", dxfattribs={"insert": (5_430_010.0, 6_300_050.0), "height": 2.5,
                                   "rotation": 90, "layer": "TEXTOS"})
doc.doc.blocks.new("ARBOL").add_circle((0, 0), 1)
msp.add_blockref("ARBOL", (5_430_200.0, 6_300_000.0), dxfattribs={"rotation": 45, "layer": "VEG"})
plan = IX.plan_exportar(list(msp), doc.doc, "capa")
assert plan.origen == plan.destino == "EPSG:5347"
assert sorted(g.archivo for g in plan.grupos) == ["EJES_lineas", "EJES_poligonos", "TEXTOS_puntos",
                                                  "VEG_puntos", "parcelas_poligonos"]
out = Path(tempfile.mkdtemp()) / "salida"
assert plan.existentes(out) == []
hechos = IX.escribir(plan, out)
assert len(hechos) == 5 and plan.existentes(out)               # la segunda vez, se avisa
r = shapefile.Reader(str(out / "parcelas_poligonos.shp"), encoding="utf-8")
assert r.shapeType == shapefile.POLYGON and len(r) == 6
campos = [f[0] for f in r.fields[1:]]
assert campos[:3] == ["LAYER", "COLOR", "TIPO_CAD"] and {"PARTIDA", "TITULAR", "SUP_M2", "FECHA"} <= set(campos)
rec = r.record(0).as_dict()
assert rec["PARTIDA"] == "01-0000" and rec["TITULAR"] == "Pérez" and rec["SUP_M2"] == 500.0
assert rec["MANZANA"] == 12 and rec["LAYER"] == "parcelas"
import datetime
assert rec["FECHA"] == datetime.date(2024, 1, 15) and rec["EDIFICADO"] is True
f = {x[0]: x for x in r.fields[1:]}
assert list(f["SUP_M2"])[1:] == ["N", 12, 2] and list(f["PARTIDA"])[1:] == ["C", 12, 0], (f["SUP_M2"], f["PARTIDA"])   # el esquema original
pts = r.shape(0).points
assert cerca(pts[0], (5_430_000.0, 6_300_000.0)) and pts[0] == pts[-1]
assert IX.shpio.signed_area(pts[:-1]) < 0                      # ESRI: borde en sentido horario
assert (out / "parcelas_poligonos.cpg").read_text() == "UTF-8"
assert "POSGAR" in (out / "parcelas_poligonos.prj").read_text().upper()
assert IX.sistema_de_prj(out / "parcelas_poligonos.shp") == "EPSG:5347"     # se reconoce al volver
r = shapefile.Reader(str(out / "TEXTOS_puntos.shp"), encoding="utf-8")
rec = r.record(0).as_dict()
assert rec["TEXTO"] == "MZA 12" and rec["ALTURA"] == 2.5 and rec["GIRO"] == 90.0
r = shapefile.Reader(str(out / "VEG_puntos.shp"))
assert r.record(0).as_dict()["BLOQUE"] == "ARBOL" and r.record(0).as_dict()["GIRO"] == 45.0
r = shapefile.Reader(str(out / "EJES_poligonos.shp"))          # el círculo, a tramos
assert len(r.shape(0).points) > 20
print("ok EXPORTARSHP por capa y tipo, con los atributos y su esquema")

# por tipo con LAYER, reproyectado
plan = IX.plan_exportar(list(msp), doc.doc, "tipo", nombre_base="plano", destino="EPSG:22195")
assert sorted(g.archivo for g in plan.grupos) == ["plano_lineas", "plano_poligonos", "plano_puntos"]
out2 = Path(tempfile.mkdtemp())
IX.escribir(plan, out2)
r = shapefile.Reader(str(out2 / "plano_poligonos.shp"), encoding="utf-8")
assert {rec.as_dict()["LAYER"] for rec in r.records()} == {"parcelas", "EJES"}
T = Transformer.from_crs("EPSG:5347", "EPSG:22195", always_xy=True)
assert cerca(r.shape(0).points[0], T.transform(5_430_000.0, 6_300_000.0), 1e-6)
assert IX.sistema_de_prj(out2 / "plano_poligonos.shp") == "EPSG:22195"
assert "Reproyectado desde POSGAR 2007" in IX.resumen_exportar(plan, [])
print("ok EXPORTARSHP por tipo con LAYER, reproyectado")

# ida y vuelta: lo exportado se vuelve a importar igual
doc2 = Document(ezdxf.new("R2018")); h2 = History(doc2)
write_georef(doc2.doc, Georef(crs="EPSG:5347"))
h2.execute(IX.plan_importar(doc2.doc, [out / "parcelas_poligonos.shp"], IX.OpcionesImportar()).comando)
p2 = list(doc2.doc.modelspace().query("LWPOLYLINE"))
_o, at2 = IX.atributos(p2[0])
d2 = {n: x for n, _t, x in at2}
assert d2["PARTIDA"] == "01-0000" and d2["TITULAR"] == "Pérez" and d2["SUP_M2"] == "500.0"
assert cerca(p2[0].get_points("xy")[0], (5_430_000.0, 6_300_000.0), 1e-9)
print("ok ida y vuelta")

# SHPINFO muestra los atributos de un objeto importado
import types
tools_mod = import_module("ingecad_plugin_geocad.tools")
eco = []
fin = []
ctx = types.SimpleNamespace(services=types.SimpleNamespace(document=doc2), echo=eco.append,
                            finish=lambda: fin.append(1))
info = tools_mod.InfoTool(ctx)
info.on_selection([p2[0]])
assert eco[0] == "Importado de parcelas_poligonos (copia, sin vínculo)" and "  TITULAR = Pérez" in eco and fin
eco.clear(); info.on_selection([doc2.doc.modelspace().add_point((0, 0))])
assert eco == ["El objeto no pertenece a una capa SHP conectada."]
print("ok SHPINFO con atributos importados")

# sin sistema en el dibujo ni elegido: se pide
doc3 = Document(ezdxf.new("R2018")); doc3.doc.modelspace().add_point((0, 0))
try:
    IX.plan_exportar(list(doc3.doc.modelspace()), doc3.doc); raise AssertionError
except ValueError as exc:
    assert "elija" in str(exc)
# ------------------------------------------------------------- 3.25.5: columnas y favoritos
# vista previa: los primeros registros como texto, en el orden de los campos
v = IX.ver_shp(parcelas, filas=3)
assert len(v.muestra) == 3 and len(v.muestra[0]) == len(v.campos)
assert v.muestra[0][v.campos.index("PARTIDA")] == "01-0000"
# sólo las columnas tildadas; el .dbf de origen no cambia
dbf = Path(parcelas).with_suffix(".dbf")
antes_dbf = dbf.read_bytes()
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
op = IX.OpcionesImportar(columnas={str(Path(parcelas)): ["TITULAR", "SUP_M2"]})
plan = IX.plan_importar(doc.doc, [parcelas], op)
hist.execute(plan.comando)
_o, at = IX.atributos(next(iter(msp.query("LWPOLYLINE"))))
assert [n for n, _t, _x in at] == ["TITULAR", "SUP_M2"], at
assert plan.tablas == ["parcelas"] and dbf.read_bytes() == antes_dbf
# ninguna tildada: sólo la geometría, sin tabla
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
plan = IX.plan_importar(doc.doc, [parcelas], IX.OpcionesImportar(columnas={str(Path(parcelas)): []}))
hist.execute(plan.comando)
assert list(msp.query("LWPOLYLINE")) and not plan.tablas
assert IX.atributos(next(iter(msp.query("LWPOLYLINE"))))[1] in (None, [], ())
print("ok IMPORTARSHP: sólo las columnas tildadas, ninguna = sólo geometría, el .dbf intacto")

# favoritos: el último arriba, sin repetir, se quitan; archivo dañado = vacío
fav = Path(tempfile.mkdtemp()) / "favoritos.json"
IX._archivo_favoritos = lambda: fav
assert IX.favoritos() == []
IX.agregar_favorito("5347"); IX.agregar_favorito("EPSG:4326"); IX.agregar_favorito("epsg:5347")
assert IX.favoritos() == ["EPSG:5347", "EPSG:4326"]
assert IX.quitar_favorito("EPSG:5347") == ["EPSG:4326"] and IX.favoritos() == ["EPSG:4326"]
for n in range(IX.MAX_FAVORITOS + 5):
    IX.agregar_favorito(str(32600 + n))
assert len(IX.favoritos()) == IX.MAX_FAVORITOS and IX.favoritos()[0] == f"EPSG:{32600 + IX.MAX_FAVORITOS + 4}"
fav.write_text("{dañado", encoding="utf-8")
assert IX.favoritos() == []
# buscador: todos los de PROJ, por nombre o código, con o sin geográficos
r = IX.buscar_sistemas("posgar 2007 faja 5", solo_metros=True)
assert ("EPSG:5347", IX.crs_mod.KNOWN[5347]) in r, r[:5]
assert any(c == "EPSG:5347" for c, _n in IX.buscar_sistemas("5347", solo_metros=True))
assert any(c == "EPSG:27700" for c, _n in IX.buscar_sistemas("27700", solo_metros=True))
assert any(c == "EPSG:4326" for c, _n in IX.buscar_sistemas("wgs 84", solo_metros=False))
assert not any(c == "EPSG:4326" for c, _n in IX.buscar_sistemas("wgs 84", solo_metros=True))
assert len(IX.catalogo(True)) > 3000
print("ok sistemas: favoritos (último arriba, X para quitar) y buscador como el de QGIS")

print("TODO OK test_intercambio")
