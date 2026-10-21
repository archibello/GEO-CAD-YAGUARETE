"""IMPORTARKML (3.30.0, módulo «Intercambio»): un KML o KMZ de Google Earth
al sistema del dibujo. De WGS 84 al sistema declarado (sin sistema, se
propone la faja según dónde cae el KML y queda asignado); puntos, líneas y
polígonos con huecos; una capa por carpeta; el nombre como rótulo
(opcional); los colores; ExtendedData como atributos (como IMPORTARSHP),
todo en un solo deshacer. Ida y vuelta con EXPORTARKML: el mismo lugar, al
milímetro."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import json, math, os, tempfile, zipfile
os.environ["HOME"] = tempfile.mkdtemp()
from collections import Counter
from pathlib import Path
from importlib import import_module
import ezdxf
from pyproj import Transformer
from core.commands import History
from core.document import Document
from core.georef import Georef, write_georef
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
KML = import_module("ingecad_plugin_geocad.kml")
IX = import_module("ingecad_plugin_geocad.intercambio")
IMP = import_module("ingecad_plugin_geocad.importados")
D = import_module("ingecad_plugin_geocad.datos")
mods = import_module("ingecad_plugin_geocad.modulos")
barra = import_module("ingecad_plugin_geocad.barra")
plugin = import_module("ingecad_plugin_geocad")

# ------------------------------------------------------------- 1. menú, barra y módulo
spec = plugin.construir_spec()
assert "GEOIMPORTKML" in spec.commands
sub = {getattr(s, "label", ""): s for s in spec.menu}
assert [i.command for i in sub["Import"].items] == ["GEOIMPORTSHP", "GEOIMPORTKML"]
item = sub["Import"].items[1]
assert item.icon and Path(item.icon).exists() and Path(item.icon).name == "importar_kml.png"
assert "GEOIMPORTKML" in {t.command for t in spec.toolbar}
assert barra.TEMAS["GEOIMPORTKML"] == "intercambio"
base = Path(plugin.__file__).parent
es = json.loads((base / "i18n" / "es" / "commands.json").read_text())
assert es["GEOIMPORTKML"]["name"] == "IMPORTARKML"
ui = json.loads((base / "i18n" / "es" / "ui.json").read_text())
assert ui[item.label] == "KML / KMZ... (IMPORTARKML)"
assert all(t.label in ui for t in spec.toolbar if t.command == "GEOIMPORTKML")
mods.poner("ingecad", "intercambio", False)
s2 = plugin.construir_spec()
assert "GEOIMPORTKML" not in s2.commands and "GEOIMPORTKML" not in {t.command for t in s2.toolbar}
mods.poner("ingecad", "intercambio", True)
print("ok menú GeoCAD > Importar > KML / KMZ..., barra GeoCAD y módulo Intercambio")

# ------------------------------------------------------------- 2. leer un KML como los de Google Earth
KML_GE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
<Document><name>Candelaria</name>
  <Style id="rojo_n"><LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
    <PolyStyle><color>4d0000ff</color></PolyStyle></Style>
  <Style id="rojo_h"><LineStyle><color>ff00ffff</color></LineStyle></Style>
  <StyleMap id="rojo"><Pair><key>normal</key><styleUrl>#rojo_n</styleUrl></Pair>
    <Pair><key>highlight</key><styleUrl>#rojo_h</styleUrl></Pair></StyleMap>
  <Style id="pin"><IconStyle><color>ff00ff00</color><scale>1.1</scale></IconStyle></Style>
  <Style id="rotulo"><IconStyle><scale>0</scale></IconStyle><LabelStyle><color>ffffffff</color></LabelStyle></Style>
  <Placemark><name>Suelto</name><Point><coordinates>-55.745, -27.46, 0</coordinates></Point></Placemark>
  <Folder><name>Relevamiento</name>
    <Folder><name>Lotes</name>
      <Placemark><name>Lote 1</name><styleUrl>#rojo</styleUrl>
        <ExtendedData><Data name="PARTIDA"><value>01-0042</value></Data>
          <Data name="SUP"><value>612.50</value></Data><Data name="LOTE"><value>1</value></Data></ExtendedData>
        <Polygon><outerBoundaryIs><LinearRing><coordinates>
          -55.7460,-27.4600,0 -55.7450,-27.4600,0 -55.7450,-27.4590,0 -55.7460,-27.4590,0 -55.7460,-27.4600,0
        </coordinates></LinearRing></outerBoundaryIs>
        <innerBoundaryIs><LinearRing><coordinates>
          -55.7457,-27.4597 -55.7453,-27.4597 -55.7453,-27.4593 -55.7457,-27.4593 -55.7457,-27.4597
        </coordinates></LinearRing></innerBoundaryIs></Polygon></Placemark>
      <Placemark><name>Lote 2</name><styleUrl>#rojo</styleUrl>
        <ExtendedData><SchemaData schemaUrl="#s"><SimpleData name="PARTIDA">01-0043</SimpleData>
          <SimpleData name="TITULAR">Núñez &amp; Cía</SimpleData></SchemaData></ExtendedData>
        <MultiGeometry>
          <Polygon><outerBoundaryIs><LinearRing><coordinates>-55.744,-27.46 -55.743,-27.46 -55.743,-27.459 -55.744,-27.46</coordinates></LinearRing></outerBoundaryIs></Polygon>
          <Point><coordinates>-55.7435,-27.4595</coordinates></Point>
        </MultiGeometry></Placemark>
    </Folder>
    <Placemark><name>Camino</name><Style><LineStyle><color>ffff0000</color></LineStyle></Style>
      <LineString><tessellate>1</tessellate><coordinates>-55.747,-27.461,0 -55.742,-27.461,0 -55.742,-27.457,0</coordinates></LineString></Placemark>
    <Placemark><name>Recorrido</name><gx:Track><when>2026-10-18T10:00:00Z</when><when>2026-10-18T10:01:00Z</when>
      <gx:coord>-55.748 -27.462 100</gx:coord><gx:coord>-55.7475 -27.4615 101</gx:coord></gx:Track></Placemark>
    <Placemark><name>Mojón 7</name><styleUrl>#pin</styleUrl><Point><coordinates>-55.7461,-27.4601,0</coordinates></Point></Placemark>
    <Placemark><name>MZA 12</name><styleUrl>#rotulo</styleUrl><Point><coordinates>-55.7455,-27.4595,0</coordinates></Point></Placemark>
  </Folder>
  <GroundOverlay><name>Plano escaneado</name><Icon><href>plano.png</href></Icon></GroundOverlay>
  <Placemark><name>Vacío</name></Placemark>
</Document></kml>"""
tmp = Path(tempfile.mkdtemp())
kmz = tmp / "Candelaria (prueba).kmz"
with zipfile.ZipFile(kmz, "w") as z:
    z.writestr("files/leeme.txt", "nada")
    z.writestr("doc.kml", KML_GE)
lugares, salteados = KML.leer(kmz)
assert salteados == Counter({"imágenes sin ubicación": 1, "marcadores sin geometría": 1}), salteados
assert [(lg.tipo, lg.nombre, lg.carpeta) for lg in lugares] == [
    ("punto", "Suelto", ""), ("poligono", "Lote 1", "Lotes"), ("poligono", "Lote 2", "Lotes"),
    ("punto", "Lote 2", "Lotes"), ("linea", "Camino", "Relevamiento"),
    ("linea", "Recorrido", "Relevamiento"), ("punto", "Mojón 7", "Relevamiento"),
    ("punto", "MZA 12", "Relevamiento")], [(lg.tipo, lg.nombre, lg.carpeta) for lg in lugares]
suelto, lote1, lote2, lote2p, camino, recorrido, mojon, mza = lugares
assert suelto.geometria == [(-55.745, -27.46)]                     # «lon, lat» con espacios
assert len(lote1.geometria) == 2 and len(lote1.geometria[0]) == 4  # borde y hueco, sin repetir el cierre
assert lote1.color == "#ff0000"                                    # el StyleMap -> su «normal»
assert lote1.datos == [("PARTIDA", "01-0042"), ("SUP", "612.50"), ("LOTE", "1")]
assert lote2.datos == [("PARTIDA", "01-0043"), ("TITULAR", "Núñez & Cía")]
assert lote2.n == lote2p.n != lote1.n                              # las partes del MultiGeometry, un marcador
assert camino.color == "#0000ff" and len(camino.geometria) == 3    # estilo propio
assert recorrido.geometria == [(-55.748, -27.462), (-55.7475, -27.4615)]
assert mojon.color == "#00ff00" and not mojon.solo_rotulo
assert mza.solo_rotulo and mza.color == "#ffffff"                  # ícono de escala 0: un texto
assert KML.color_rgb("7f00ff00") == "#00ff00" and KML.color_rgb("ff0000") == "#0000ff"
assert KML.color_rgb("") == "" and KML.color_rgb("zz") == ""
# un .kml suelto y archivos que no son KML
(tmp / "suelto.kml").write_text(KML_GE, encoding="utf-8")
assert len(KML.leer(tmp / "suelto.kml")[0]) == 8
(tmp / "malo.kml").write_text("esto no es XML", encoding="utf-8")
for malo in (tmp / "malo.kml",):
    try:
        KML.leer(malo); raise AssertionError("leyó un archivo que no es KML")
    except Exception as exc:  # noqa: BLE001
        assert not isinstance(exc, AssertionError)
with zipfile.ZipFile(tmp / "sin.kmz", "w") as z:
    z.writestr("a.txt", "x")
try:
    KML.leer(tmp / "sin.kmz"); raise AssertionError("leyó un KMZ sin KML")
except ValueError as exc:
    assert "ningún .kml" in str(exc)
print("ok leer: KMZ (doc.kml), carpetas, StyleMap, estilo propio, huecos, MultiGeometry, gx:Track, "
      "ExtendedData (Data y SchemaData), textos, lo que no se importa se cuenta")

# ------------------------------------------------------------- 3. la faja según la ubicación
assert IX.faja_de_lon(-55.745) == 6 and IX.faja_de_lon(-55.4) == 7 and IX.faja_de_lon(-72) == 1
assert IX.faja_de_lon(-58.38) == 6 and IX.faja_de_lon(-68.83) == 2 and IX.faja_de_lon(-3.7) is None
assert IX.sistema_por_ubicacion([-55.745], [-27.46]) == "EPSG:5348"        # Candelaria: POSGAR 2007 faja 6
assert IX.sistema_por_ubicacion([-68.83, -68.8, -40.0], [-32.9, -32.8, -32.0]) == "EPSG:5344"   # la del medio
assert IX.sistema_por_ubicacion([-3.7], [40.4]) == "EPSG:32630"           # fuera de la Argentina: UTM
assert IX.sistema_por_ubicacion([-56.2], [-34.9]) == "EPSG:5348"          # Montevideo: dentro del rango, faja 6
assert IX.sistema_por_ubicacion([-47.9], [-15.8]) == "EPSG:32723"         # Brasilia: UTM 23S
assert IX.sistema_por_ubicacion([], []) == ""
print("ok faja según la longitud del KML (POSGAR 2007), UTM fuera de la Argentina")

# ------------------------------------------------------------- 4. importar a un dibujo en Campo Inchauspe faja 6
SIS = "EPSG:22196"
ida = Transformer.from_crs("EPSG:4326", SIS, always_xy=True)
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
write_georef(doc.doc, Georef(crs=SIS))
doc.doc.layers.add("Lotes", color=5)                                      # ya estaba: conserva su color
plan = KML.plan_importar(doc.doc, kmz, lugares, KML.OpcionesKml(), salteados)
hist.execute(plan.comando)
assert plan.sistema_adoptado == "" and plan.objetos == len(list(msp)) == 9
assert {e.dxf.layer for e in msp} == {"Candelaria (prueba)", "Lotes", "Relevamiento"}
assert doc.doc.layers.get("Lotes").dxf.color == 5 and doc.doc.layers.get("Relevamiento").dxf.color == 7
polis = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "Lotes"]
assert len(polis) == 3 and all(p.closed for p in polis)                  # borde y hueco del lote 1, lote 2
for p, anillo in zip(polis, lote1.geometria + lote2.geometria):
    for (x, y), (lo, la) in zip(p.get_points("xy"), anillo):
        X, Y = ida.transform(lo, la)
        assert math.hypot(x - X, y - Y) < 1e-6, (x, X, y, Y)
x, y = polis[0].get_points("xy")[0]
assert 6_620_000 < x < 6_630_000 and 6_960_000 < y < 6_970_000           # X de faja 6, como el plano de Candelaria
assert polis[0].rgb == (255, 0, 0) and polis[1].rgb == (255, 0, 0)
cam = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "Relevamiento"]
assert len(cam) == 2 and not cam[0].closed and cam[0].rgb == (0, 0, 255)
assert not cam[1].has_dxf_attrib("true_color")                            # sin color: el de la capa
txt = [e for e in msp if e.dxftype() == "TEXT"]
assert [t.dxf.text for t in txt] == ["MZA 12"] and txt[0].dxf.color == 7  # blanco de GE = blanco/negro de CAD
assert math.dist(tuple(txt[0].dxf.insert)[:2], ida.transform(-55.7455, -27.4595)) < 1e-6
pts = [e for e in msp if e.dxftype() == "POINT"]
assert len(pts) == 3 and all(p.dxf.location.z == 0 for p in pts)
# atributos: una tabla con todas las columnas, números como N
assert plan.tablas == ["Candelaria (prueba)"]
origen, at = IX.atributos(polis[0])
assert origen == "Candelaria (prueba)"
d = {n: (t, v) for n, t, v in at}
assert d["PARTIDA"] == (("C", 254, 0), "01-0042") and d["SUP"] == (("N", 19, 2), "612.50")
assert d["LOTE"] == (("N", 18, 0), "1") and d["TITULAR"] == (("C", 254, 0), "")
assert {n: v for n, _t, v in IX.atributos(polis[2])[1]}["TITULAR"] == "Núñez & Cía"
assert IX.atributos(polis[0])[1] == IX.atributos(polis[1])[1]             # el hueco, los mismos datos
tabla = D.layer_data(doc, "Candelaria (prueba)")
assert [f.name for f in tabla.fields] == ["PARTIDA", "SUP", "LOTE", "TITULAR"]
assert len(tabla.rows) == 6          # un renglón por marcador con geometría; el rótulo sin datos no (3.30.1)
assert len(tabla.entities_by_fid(doc)[lote2.n]) == 2                     # polígono y punto del lote 2
r = KML.resumen_importar(plan)
assert "7 marcador(es), 9 objeto(s), de WGS 84 a Campo Inchauspe" in r, r
assert "imágenes sin ubicación 1" in r and "conservan su color" in r and "TABLASIG" in r and "U lo deshace" in r
hist.undo()
assert not list(msp) and "Relevamiento" not in doc.doc.layers and "Lotes" in doc.doc.layers
print("ok importar: de WGS 84 a Campo Inchauspe faja 6 como pyproj, capa por carpeta, huecos, colores, "
      "textos, ExtendedData como atributos (tabla), un deshacer")

# opciones: una sola capa, sin colores, sin atributos, con rótulos
op = KML.OpcionesKml(capa="fija", capa_fija="GE", colores=False, atributos=False, rotulos=True, altura=2.0)
plan = KML.plan_importar(doc.doc, kmz, lugares, op)
hist.execute(plan.comando)
assert {e.dxf.layer for e in msp} == {"GE"} and not plan.tablas
assert not any(e.has_dxf_attrib("true_color") for e in msp) and not any(IX.atributos(e)[1] for e in msp)
assert sorted(t.dxf.text for t in msp.query("TEXT")) == ["Camino", "Lote 1", "Lote 2", "Lote 2",
                                                       "MZA 12", "Mojón 7", "Recorrido", "Suelto"]
rot = {t.dxf.text: t for t in msp.query("TEXT")}
r1 = rot["Lote 1"]
assert r1.dxf.height == 2.0 and r1.dxf.halign == 1 and r1.dxf.valign == 2      # centrado
cx, cy = ida.transform(-55.7455, -27.4595)                                # centro del cuadrado
assert math.dist(tuple(r1.dxf.align_point)[:2], (cx, cy)) < 0.01
rc = rot["Camino"]                                                        # a mitad del camino
ax, ay = ida.transform(-55.747, -27.461); bx, by = ida.transform(-55.742, -27.461); qx, qy = ida.transform(-55.742, -27.457)
mitad = (math.hypot(bx - ax, by - ay) + math.hypot(qx - bx, qy - by)) / 2
tramo1 = math.hypot(bx - ax, by - ay)
if mitad <= tramo1:
    assert abs(math.hypot(rc.dxf.align_point[0] - ax, rc.dxf.align_point[1] - ay) - mitad) < 0.01
else:
    assert abs(math.hypot(rc.dxf.align_point[0] - bx, rc.dxf.align_point[1] - by) - (mitad - tramo1)) < 0.01
rs = rot["Suelto"]
sx, sy = ida.transform(-55.745, -27.46)
assert rs.dxf.halign == 0 and abs(rs.dxf.align_point[0] - (sx + 1.2)) < 1e-6   # a la derecha del punto
hist.undo(); assert not list(msp)
print("ok opciones: una sola capa, sin colores ni atributos, nombres como rótulos (centroide, mitad, al lado)")

# ------------------------------------------------------------- 5. sin sistema: se asigna el elegido
sin = Document(ezdxf.new("R2018")); h2 = History(sin)
try:
    KML.plan_importar(sin.doc, kmz, lugares, KML.OpcionesKml()); raise AssertionError("importó sin sistema")
except ValueError as exc:
    assert "SISTEMAGEO" in str(exc)
plan = KML.plan_importar(sin.doc, kmz, lugares, KML.OpcionesKml(sistema="EPSG:5348"))
h2.execute(plan.comando)
assert IX.sistema_del_dibujo(sin.doc) == "EPSG:5348" and plan.sistema_adoptado == "EPSG:5348"
assert "El dibujo quedó en POSGAR 2007 / Argentina faja 6" in KML.resumen_importar(plan)
h2.undo()
assert IX.sistema_del_dibujo(sin.doc) == "" and not list(sin.modelspace())
# un punto que no se puede llevar al sistema: se cuenta, no rompe
lejos = [KML.Lugar("punto", [(200.0, 95.0)], "x")] + lugares[:1]
plan = KML.plan_importar(doc.doc, kmz, lejos, KML.OpcionesKml())
assert plan.objetos == 1 and any("fuera del área" in a for a in plan.avisos), plan.avisos
print("ok sin sistema: no importa a ciegas; con el elegido queda asignado y U lo deshace; lo que no se convierte se cuenta")

# ------------------------------------------------------------- 6. ida y vuelta con EXPORTARKML, al milímetro
SIS7 = "EPSG:5349"                                                        # POSGAR 2007 faja 7, Posadas
X0, Y0 = Transformer.from_crs("EPSG:4326", SIS7, always_xy=True).transform(-55.896, -27.367)
orig = Document(ezdxf.new("R2018")); om = orig.modelspace()
write_georef(orig.doc, Georef(crs=SIS7))
orig.doc.layers.add("LOTES", color=3); orig.doc.layers.add("CALLES", color=1)
orig.doc.layers.add("TEXTOS", color=7); orig.doc.layers.add("MOJONES", color=2)
a = om.add_lwpolyline([(X0, Y0), (X0 + 20.123, Y0), (X0 + 20.123, Y0 + 30.456), (X0, Y0 + 30.456)],
                      close=True, dxfattribs={"layer": "LOTES"})
IMP.poner_atributos(a, "parcelas", [IX.shpio.DbfField("PARTIDA", "C", 10, 0, 0),
                                    IX.shpio.DbfField("SUP", "N", 10, 2, 0)],
                    {"PARTIDA": "01-0042", "SUP": "612.85"})
b = om.add_lwpolyline([(X0 + 30, Y0), (X0 + 50, Y0), (X0 + 50, Y0 + 30)], close=True,
                      dxfattribs={"layer": "LOTES", "color": 6})
c = om.add_lwpolyline([(X0 - 5, Y0 - 10), (X0 + 40.5, Y0 - 10.25), (X0 + 80, Y0 - 3)],
                      dxfattribs={"layer": "CALLES"})
c.rgb = (12, 34, 56)
hh = om.add_hatch(color=256, dxfattribs={"layer": "LOTES"})
hh.paths.add_polyline_path([(X0, Y0 + 50), (X0 + 40, Y0 + 50), (X0 + 40, Y0 + 90), (X0, Y0 + 90)], is_closed=True)
hh.paths.add_polyline_path([(X0 + 10, Y0 + 60), (X0 + 20, Y0 + 60), (X0 + 20, Y0 + 70), (X0 + 10, Y0 + 70)], is_closed=True)
t = om.add_text("MZA 12", dxfattribs={"insert": (X0 + 5.5, Y0 + 5.25), "height": 2.5, "layer": "TEXTOS"})
p = om.add_point((X0 + 1.001, Y0 + 1.002), dxfattribs={"layer": "MOJONES"})
for ext in (".kmz", ".kml"):
    plan_k = KML.plan_kml(list(om), orig.doc, "Ida")
    archivo = KML.escribir(plan_k, tmp / ("ida" + ext))
    lgs, salt = KML.leer(archivo)
    assert not salt, salt
    vuelta = Document(ezdxf.new("R2018")); vm = vuelta.modelspace(); hv = History(vuelta)
    write_georef(vuelta.doc, Georef(crs=SIS7))
    hv.execute(KML.plan_importar(vuelta.doc, archivo, lgs, KML.OpcionesKml()).comando)
    # el mismo lugar, al milímetro, vértice por vértice
    peor = 0.0
    por_capa = {}
    for e in vm:
        por_capa.setdefault((e.dxf.layer, e.dxftype()), []).append(e)
    assert sorted(por_capa) == [("CALLES", "LWPOLYLINE"), ("LOTES", "LWPOLYLINE"), ("MOJONES", "POINT"),
                                ("TEXTOS", "TEXT")], sorted(por_capa)
    lotes = por_capa[("LOTES", "LWPOLYLINE")]
    assert len(lotes) == 4                                               # a, b, el sombreado y su hueco
    for viejo, nuevo in zip([a.get_points("xy"), b.get_points("xy")], lotes[:2]):
        n = nuevo.get_points("xy")
        assert len(n) == len(viejo) and nuevo.closed          # el mismo anillo (quizá en otro sentido)
        peor = max([peor] + [min(math.dist(u, v) for v in n) for u in viejo]
                   + [min(math.dist(u, v) for v in viejo) for u in n])
    anillos = [[tuple(v[:2]) for v in pth.vertices] for pth in hh.paths]
    for viejo, nuevo in zip(anillos, lotes[2:]):
        n = nuevo.get_points("xy")
        assert len(n) == len(viejo) and nuevo.closed
        peor = max([peor] + [min(math.dist(u, v) for v in n) for u in viejo]
                   + [min(math.dist(u, v) for v in viejo) for u in n])
    nc = por_capa[("CALLES", "LWPOLYLINE")][0].get_points("xy")
    peor = max([peor] + [math.dist(u, v) for u, v in zip(c.get_points("xy"), nc)])
    np_ = por_capa[("MOJONES", "POINT")][0].dxf.location
    peor = max(peor, math.dist(tuple(np_)[:2], tuple(p.dxf.location)[:2]))
    nt = por_capa[("TEXTOS", "TEXT")][0]
    assert nt.dxf.text == "MZA 12"
    peor = max(peor, math.dist(tuple(nt.dxf.insert)[:2], tuple(t.dxf.insert)[:2]))
    assert peor < 0.001, peor                                            # al milímetro (en realidad, < 0,1 mm)
    # colores y datos
    assert lotes[0].rgb == (0, 255, 0) and lotes[1].rgb == (255, 0, 255)  # ACI 3 de la capa, ACI 6 propio
    assert por_capa[("CALLES", "LWPOLYLINE")][0].rgb == (12, 34, 56)
    assert nt.dxf.color == 7                                              # blanco/negro
    assert {n: v for n, _t, v in IX.atributos(lotes[0])[1]} == {"PARTIDA": "01-0042", "SUP": "612.85"}
    # y otra vuelta: exportar lo importado da las mismas coordenadas
    otra = KML.plan_kml(list(vm), vuelta.doc, "Vuelta")
    m1 = [m.geometria for m in plan_k.marcas if m.tipo == "linea"]
    m2 = [m.geometria for m in otra.marcas if m.tipo == "linea"]
    assert all(abs(u[0] - v[0]) < 1e-8 and abs(u[1] - v[1]) < 1e-8 for g1, g2 in zip(m1, m2) for u, v in zip(g1, g2))
    print(f"ok ida y vuelta {ext}: el mismo lugar (peor diferencia {peor * 1000:.4f} mm), capas, colores, "
          "texto y atributos")

# ------------------------------------------------------------- 7. las ventanas (con el Qt de IngeCAD)
try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
except Exception:  # noqa: BLE001 -- sin PySide6: lo demás ya está probado
    print("(sin PySide6: no se arman las ventanas)")
else:
    app = QApplication.instance() or QApplication([])
    UI = import_module("ingecad_plugin_geocad.intercambio_ui")
    vistos = []
    QMessageBox.information = staticmethod(lambda parent, titulo, texto, *a: vistos.append(texto))
    QMessageBox.exec = lambda caja: vistos.append(caja.text()) or 0
    QMessageBox.clickedButton = lambda caja: None

    class Ctx:
        def __init__(c, documento):
            c.document, c.host, c.ecos, c.cmds = documento, None, [], []

        def echo(c, t):
            c.ecos.append(t)

        def execute(c, cmd):
            c.cmds.append(cmd)
    # sin sistema: se propone la faja por la ubicación del KML
    propuestas = []

    def falso_exec(dlg):
        propuestas.append(dlg.combo.codigo())
        return 1
    UI.SistemaDialog.exec = falso_exec
    vacio = Document(ezdxf.new("R2018"))
    assert UI._sistema_para_kml(Ctx(vacio), lugares) == ("EPSG:5348", "EPSG:5348")
    assert propuestas == ["EPSG:5348"] and "faja 6" in vistos[-1], vistos
    # con sistema que concuerda con las X: ni pregunta
    n = len(vistos)
    assert UI._sistema_para_kml(Ctx(doc), lugares) == (SIS, "") and len(vistos) == n
    # la ventana de opciones
    dlg = UI.ImportarKmlDialog(kmz.name, lugares, salteados, SIS)
    assert dlg.por_carpeta.isChecked() and dlg.colores.isChecked() and dlg.atributos.isChecked()
    assert not dlg.rotulos.isChecked()
    dlg.rotulos.setChecked(True); dlg.fija.setChecked(True); dlg.nombre_capa.setText("GE")
    op = dlg.opciones("")
    assert op.capa == "fija" and op.capa_fija == "GE" and op.atributos and op.sistema == ""
    # 3.30.4: con tabla, rotula ROTULOSIG al terminar (no el nombre de cada marcador)
    assert "ROTULOSIG" in dlg.rotulos.text() and dlg.altura.isHidden()
    assert not op.rotulos and dlg.rotular_con_tabla() and not op.textos   # ni los textos del KML
    dlg.atributos.setChecked(False)                         # sin tabla no hay con qué rotular
    assert not dlg.rotulos.isEnabled() and not dlg.rotulos.isChecked() and not dlg.rotular_con_tabla()
    sin_datos = [lg for lg in lugares if not lg.datos]
    d2 = UI.ImportarKmlDialog("x.kml", sin_datos, Counter(), SIS)
    assert not d2.atributos.isEnabled() and not d2.atributos.isChecked()
    assert "nombre de cada marcador" in d2.rotulos.text() and not d2.altura.isHidden()
    d2.rotulos.setChecked(True)
    assert d2.opciones("").rotulos and not d2.rotular_con_tabla() and d2.opciones("").textos
    print("ok ventanas: sin sistema propone la faja del KML; opciones de capas, colores, atributos y rótulos")

# ------------------------------------------------------------- 3.30.1: a la tabla sólo lo que trae datos
# (PRUEBA CON ETIQUETAS: 16 parcelas con datos y 13 rótulos sin datos -> 29 registros y
# TABLASIG medía «Longitud»)
archivo = KML.escribir(KML.plan_kml([a, t], orig.doc, "Rotulos"), tmp / "rotulos.kmz")
lgs, _s = KML.leer(archivo)
assert sorted((l.tipo, l.solo_rotulo, bool(l.datos)) for l in lgs) == [("poligono", False, True),
                                                                       ("punto", True, False)]
rd = Document(ezdxf.new("R2018")); write_georef(rd.doc, Georef(crs=SIS7))
plan_r = KML.plan_importar(rd.doc, archivo, lgs, KML.OpcionesKml())
History(rd).execute(plan_r.comando)
(clave,) = IMP.tablas(rd.doc)
tabla_r = IMP.ImportedData(rd, clave)
assert tabla_r.kind == "polygon" and len(tabla_r._por_fid) == 1, (tabla_r.kind, tabla_r._por_fid)
assert D.TableState(rd, clave).measure == "Área"                          # TABLASIG: Área, no Longitud
assert [e.dxftype() for e in rd.modelspace()].count("TEXT") == 1       # el rótulo entra igual
# 3.30.4: si rotula ROTULOSIG, los textos del KML no se traen (no quedan dos números por parcela)
sd = Document(ezdxf.new("R2018")); write_georef(sd.doc, Georef(crs=SIS7))
plan_s = KML.plan_importar(sd.doc, archivo, lgs, KML.OpcionesKml(textos=False))
History(sd).execute(plan_s.comando)
assert [e.dxftype() for e in sd.modelspace()] == ["LWPOLYLINE"]
assert "1 texto(s) del archivo no se traen" in KML.resumen_importar(plan_s), KML.resumen_importar(plan_s)
print("ok 3.30.1: los rótulos sin datos no entran en la tabla; TABLASIG mide el área")

# ------------------------------------------------------------- 3.30.3: los nombres «capa número» no se rotulan
assert KML.nombre_generado("PC_2_DE_MAYO 5", "PC_2_DE_MAYO") and KML.nombre_generado("LOTES 12", "LOTES")
assert not KML.nombre_generado("0270", "PC_2_DE_MAYO") and not KML.nombre_generado("LOTES 12", "")
assert not KML.nombre_generado("Casa de Juan 2", "Prueba")             # uno puesto en Google Earth
for campo, esperados in (("", ["MZA 12"]), ("PARTIDA", ["01-0042", "MZA 12"])):
    archivo = KML.escribir(KML.plan_kml([a, t], orig.doc, "Nombres", campo_nombre=campo),
                           tmp / f"nombres{campo}.kmz")
    lgs, _s = KML.leer(archivo)
    nd = Document(ezdxf.new("R2018")); write_georef(nd.doc, Georef(crs=SIS7))
    History(nd).execute(KML.plan_importar(nd.doc, archivo, lgs, KML.OpcionesKml(rotulos=True)).comando)
    textos = sorted(e.dxf.text for e in nd.modelspace() if e.dxftype() == "TEXT")
    assert textos == esperados, (campo, textos)       # sin atributo: «LOTES 1» no se escribe
print("ok 3.30.3: con «el nombre como rótulo», los nombres «capa número» no se escriben")

# ------------------------------------------------------------- 3.30.5: sin capa vacía; rótulos aparte
lote = KML.Lugar("poligono", [[(-55.90, -27.40), (-55.899, -27.40), (-55.899, -27.399)]], "0270",
                 "PARCELAS", datos=[("PARTIDA", "0270")], n=1)
texto = KML.Lugar("punto", [(-55.8995, -27.3998)], "0270", "PARCELAS-TEXTOS", n=2, solo_rotulo=True)
nd = Document(ezdxf.new("R2018")); write_georef(nd.doc, Georef(crs=SIS7))
plan_v = KML.plan_importar(nd.doc, "Vacia.kmz", [lote, texto], KML.OpcionesKml(textos=False))
History(nd).execute(plan_v.comando)
assert "PARCELAS" in nd.doc.layers and "PARCELAS-TEXTOS" not in nd.doc.layers   # la de los textos no
assert "1 marcador(es), 1 objeto(s)" in KML.resumen_importar(plan_v), KML.resumen_importar(plan_v)
# como Prueba KI5.kmz: «Lineas 1» y «Lineas 2» movidas a otra carpeta y un punto sin nombre
ki5 = [KML.Lugar("linea", [(-55.90, -27.40), (-55.899, -27.40)], "Lineas 1", "Prueba KI5", n=1),
       KML.Lugar("linea", [(-55.90, -27.401), (-55.899, -27.401)], "Lineas 2", "Prueba KI5", n=2),
       KML.Lugar("punto", [(-55.8995, -27.4005)], "", "Prueba KI5", n=3)]
nd = Document(ezdxf.new("R2018")); write_georef(nd.doc, Georef(crs=SIS7))
plan_k = KML.plan_importar(nd.doc, "Prueba KI5.kmz", ki5, KML.OpcionesKml(rotulos=True))
History(nd).execute(plan_k.comando)
r = KML.resumen_importar(plan_k)
assert "3 marcador(es), 3 objeto(s)" in r and "Con 2 rótulo(s) del nombre" in r, r
assert sorted(e.dxftype() for e in nd.modelspace()) == ["LWPOLYLINE", "LWPOLYLINE", "POINT", "TEXT", "TEXT"]
print("ok 3.30.5: sin la capa vacía de los textos que no se traen; los rótulos se cuentan aparte")

# ------------------------------------------------------------- 3.30.4: rótulos con ROTULOSIG al importar
try:
    from PySide6.QtWidgets import QApplication
except Exception:  # noqa: BLE001
    pass
else:
    RUI = import_module("ingecad_plugin_geocad.rotulos_ui")
    elegido = {}

    def rot_exec(dlg):
        elegido["campos"] = [dlg.campo.itemText(i) for i in range(dlg.campo.count())]
        elegido["campo"] = dlg.campo.currentText()
        dlg.altura.setValue(3.0)
        return 1
    RUI.RotulosDialog.exec = rot_exec
    hist_r = History(rd)

    class CtxR:
        document, host, ecos = rd, None, []

        def echo(self, t):
            self.ecos.append(t)

        def execute(self, cmd):
            hist_r.execute(cmd)
    cr = CtxR()
    UI._rotular_como_rotulosig(cr, clave)
    assert elegido["campos"] == ["PARTIDA", "SUP"], elegido
    rot = [e for e in rd.modelspace() if e.dxftype() == "TEXT" and e.dxf.layer == f"{clave}-ROTULOS"]
    assert [e.dxf.text for e in rot] == ["01-0042"] and rot[0].dxf.height == 3.0, [e.dxf.text for e in rot]
    assert "ROTULOSIG: 1 rótulo(s) de PARTIDA" in cr.ecos[-1] and "U los deshace" in cr.ecos[-1], cr.ecos
    HD = import_module("ingecad_plugin_geocad.herramientas_datos")
    assert len(HD.existing_labels(rd, clave)) == 1                 # enlazados: QUITARROTULOS los borra
    hist_r.undo()
    assert not [e for e in rd.modelspace() if e.dxf.layer == f"{clave}-ROTULOS"]
    print("ok 3.30.4: con tabla, IMPORTARKML rotula con la ventana y el motor de ROTULOSIG")

print("TODO OK test_importarkml")
