"""EXPORTARKML (3.29.0, módulo «Intercambio»): lo elegido a un KMZ para
Google Earth en WGS 84. Coordenadas convertidas como pyproj, una carpeta por
capa (o todo junto), color ACI y grosor, polígonos y sombreados con relleno
semitransparente (el % elegido), arcos y círculos en tramos, textos y
bloques como marcadores, atributos de IMPORTARSHP en ExtendedData, y el KMZ
como un zip con doc.kml."""
import json, math, os, tempfile, zipfile
os.environ["HOME"] = tempfile.mkdtemp()
import xml.etree.ElementTree as ET
from pathlib import Path
from importlib import import_module
import ezdxf
from pyproj import Transformer
from core.document import Document
from core.georef import Georef, write_georef
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
KML = import_module("ingecad_plugin_geocad.kml")
IX = import_module("ingecad_plugin_geocad.intercambio")
IMP = import_module("ingecad_plugin_geocad.importados")
mods = import_module("ingecad_plugin_geocad.modulos")
barra = import_module("ingecad_plugin_geocad.barra")
plugin = import_module("ingecad_plugin_geocad")
N = "{http://www.opengis.net/kml/2.2}"

# ------------------------------------------------------------- 1. menú, barra y módulo
spec = plugin.construir_spec()
assert "GEOEXPORTKML" in spec.commands
sub = {getattr(s, "label", ""): s for s in spec.menu}
assert [i.command for i in sub["Export"].items] == ["GEOEXPORTSHP", "GEOEXPORTKML"]
item = sub["Export"].items[1]
assert item.icon and Path(item.icon).exists(), item.icon
assert "GEOEXPORTKML" in {t.command for t in spec.toolbar}
assert barra.TEMAS["GEOEXPORTKML"] == "intercambio"
base = Path(plugin.__file__).parent
es = json.loads((base / "i18n" / "es" / "commands.json").read_text())
assert es["GEOEXPORTKML"]["name"] == "EXPORTARKML"
ui = json.loads((base / "i18n" / "es" / "ui.json").read_text())
assert ui[item.label] == "KML / KMZ... (EXPORTARKML)"
assert all(t.label in ui for t in spec.toolbar if t.command == "GEOEXPORTKML")
mods.poner("ingecad", "intercambio", False)
s2 = plugin.construir_spec()
assert "GEOEXPORTKML" not in s2.commands and "GEOEXPORTKML" not in {t.command for t in s2.toolbar}
mods.poner("ingecad", "intercambio", True)
print("ok menú GeoCAD > Exportar > KML / KMZ..., barra GeoCAD y módulo Intercambio")

# ------------------------------------------------------------- 2. un dibujo en Posadas (POSGAR 2007 faja 7)
SIS = "EPSG:5349"
ida = Transformer.from_crs("EPSG:4326", SIS, always_xy=True)
vuelta = Transformer.from_crs(SIS, "EPSG:4326", always_xy=True)
X0, Y0 = ida.transform(-55.896, -27.367)          # plaza 9 de Julio, más o menos

doc = Document(ezdxf.new("R2018")); msp = doc.modelspace()
write_georef(doc.doc, Georef(crs=SIS))
d = doc.doc
d.layers.add("LOTES", color=3).dxf.lineweight = 50           # verde, 0,50 mm
d.layers.add("CALLES", color=1)                              # rojo, grosor por defecto
d.layers.add("TEXTOS", color=7)                              # blanco/negro de CAD
d.layers.add("SOMBRAS", color=5)
d.layers.add("MOJONES", color=2)
lote = msp.add_lwpolyline([(X0, Y0), (X0 + 20, Y0), (X0 + 20, Y0 + 30), (X0, Y0 + 30)],
                          close=True, dxfattribs={"layer": "LOTES"})
IMP.poner_atributos(lote, "parcelas", [IX.shpio.DbfField("PARTIDA", "C", 10, 0, 0),
                                       IX.shpio.DbfField("TITULAR", "C", 40, 0, 0),
                                       IX.shpio.DbfField("SUP", "N", 10, 2, 0)],
                    {"PARTIDA": "01-0042", "TITULAR": "Fernández & Hijos <SA>", "SUP": "600.00"})
lote2 = msp.add_lwpolyline([(X0 + 30, Y0), (X0 + 50, Y0), (X0 + 50, Y0 + 30)], close=True,
                           dxfattribs={"layer": "LOTES", "color": 6, "lineweight": 100})
# una calle con un arco (bulge) y un círculo
calle = msp.add_lwpolyline([(X0, Y0 - 10, 0, 0, 1.0), (X0 + 40, Y0 - 10)], format="xyseb",
                           dxfattribs={"layer": "CALLES"})
msp.add_circle((X0 + 100, Y0), 5, dxfattribs={"layer": "CALLES"})
# un sombreado con hueco y una isla suelta
h = msp.add_hatch(color=256, dxfattribs={"layer": "SOMBRAS"})
h.paths.add_polyline_path([(X0, Y0 + 50), (X0 + 40, Y0 + 50), (X0 + 40, Y0 + 90), (X0, Y0 + 90)], is_closed=True)
h.paths.add_polyline_path([(X0 + 10, Y0 + 60), (X0 + 20, Y0 + 60), (X0 + 20, Y0 + 70), (X0 + 10, Y0 + 70)], is_closed=True)
h.paths.add_polyline_path([(X0 + 60, Y0 + 50), (X0 + 70, Y0 + 50), (X0 + 70, Y0 + 60), (X0 + 60, Y0 + 60)], is_closed=True)
txt = msp.add_text("MZA 12", dxfattribs={"insert": (X0 + 5, Y0 + 5), "height": 2.5, "layer": "TEXTOS"})
blk = d.blocks.new("MOJON")
blk.add_circle((0, 0), 0.5)
blk.add_attdef("NUMERO", (0, 1))
ins = msp.add_blockref("MOJON", (X0 + 20, Y0 + 30), dxfattribs={"layer": "MOJONES"})
ins.add_auto_attribs({"NUMERO": "M-7"})
msp.add_point((X0 + 1, Y0 + 1), dxfattribs={"layer": "MOJONES"})
msp.add_xline((X0, Y0), (1, 0))                                # no va a Google Earth

plan = KML.plan_kml(list(msp), d, "Prueba")
assert plan.origen == SIS
assert sorted(c for c, _m in plan.carpetas()) == ["CALLES", "LOTES", "MOJONES", "SOMBRAS", "TEXTOS"]
assert sum(plan.salteados.values()) == 1, plan.salteados
por = {(m.capa, m.tipo): m for m in plan.marcas}
print("ok plan: una carpeta por capa, lo que no va se cuenta")

# ------------------------------------------------------------- 3. coordenadas como pyproj
m = plan.marcas[0]
assert m.tipo == "poligono" and m.capa == "LOTES"
borde = m.geometria[0][0]
esperado = [vuelta.transform(x, y) for x, y in [(X0, Y0), (X0 + 20, Y0), (X0 + 20, Y0 + 30), (X0, Y0 + 30)]]
for p in esperado:
    assert min(math.dist(p, q) for q in borde) < 1e-10, p
assert borde[0] == borde[-1]                                  # anillo cerrado
lon, lat = borde[0]
assert -56 < lon < -55.8 and -27.4 < lat < -27.3
# el arco en tramos: cada vértice, de vuelta, a 1 cm del arco o menos
linea = [m for m in plan.marcas if m.tipo == "linea"][0]
assert len(linea.geometria) > 10
cx, cy, r = X0 + 20, Y0 - 10, 20.0                           # bulge 1 = medio círculo
for lon, lat in linea.geometria:
    x, y = ida.transform(lon, lat)
    assert abs(math.hypot(x - cx, y - cy) - r) < 0.011, math.hypot(x - cx, y - cy)
circ = [m for m in plan.marcas if m.capa == "CALLES" and m.tipo == "poligono"][0]
assert len(circ.geometria[0][0]) > 20
print("ok coordenadas: iguales a pyproj; arcos y círculos en tramos de 1 cm")

# ------------------------------------------------------------- 4. el KMZ
salida = Path(tempfile.mkdtemp())
kmz = KML.escribir(plan, salida / "prueba.kmz")
with zipfile.ZipFile(kmz) as z:
    assert z.namelist() == ["doc.kml"]
    texto = z.read("doc.kml").decode("utf-8")
assert texto.startswith('<?xml version="1.0" encoding="UTF-8"?>')
raiz = ET.fromstring(texto)
assert raiz.tag == N + "kml"
documento = raiz.find(N + "Document")
assert documento.find(N + "name").text == "Prueba"
carpetas = {f.find(N + "name").text: f for f in documento.findall(N + "Folder")}
assert sorted(carpetas) == ["CALLES", "LOTES", "MOJONES", "SOMBRAS", "TEXTOS"]
assert len(carpetas["LOTES"].findall(N + "Placemark")) == 2
assert len(raiz.findall(f".//{N}Placemark")) == len(plan.marcas) == 8
for c in raiz.iter(N + "coordinates"):                        # lon,lat,0 con 9 decimales
    for p in c.text.split():
        lo, la, z = p.split(",")
        assert len(lo.split(".")[1]) == 9 and z == "0"
assert all(a.text == "clampToGround" for a in raiz.iter(N + "altitudeMode"))
estilos = {s.get("id"): s for s in documento.findall(N + "Style")}


def estilo(pm):
    return estilos[pm.find(N + "styleUrl").text[1:]]


def pm_de(capa, nombre):
    for pm in carpetas[capa].findall(N + "Placemark"):
        if pm.find(N + "name") is not None and pm.find(N + "name").text == nombre:
            return pm
    raise AssertionError((capa, nombre))


# el lote: verde de la capa (ACI 3), 0,50 mm = 3 px, relleno 40 % = 0x66
p1 = pm_de("LOTES", "LOTES 1")
s = estilo(p1)
assert s.find(f"{N}LineStyle/{N}color").text == "ff00ff00"
assert s.find(f"{N}LineStyle/{N}width").text == "3"
assert s.find(f"{N}PolyStyle/{N}color").text == "6600ff00"
assert s.find(f"{N}PolyStyle/{N}fill").text == "1" and s.find(f"{N}PolyStyle/{N}outline").text == "1"
datos = {x.get("name"): x.find(N + "value").text for x in p1.iter(N + "Data")}
assert datos == {"PARTIDA": "01-0042", "TITULAR": "Fernández & Hijos <SA>", "SUP": "600.00"}
assert "Área 600,00 m²" in p1.find(N + "description").text
# 3.30.1: Google Earth no muestra los ExtendedData si hay descripción: la tabla va en el globo
globo = p1.find(N + "description").text
assert "<table>" in globo and "<b>PARTIDA</b>" in globo and "01-0042" in globo, globo
assert "Fernández &amp; Hijos &lt;SA&gt;" in globo                     # escapado en el HTML
assert globo.index("<table>") < globo.index("Área 600,00 m²")            # primero la tabla, después las medidas
# el otro lote: su propio color (ACI 6, magenta) y 1 mm = 6 px
s = estilo(pm_de("LOTES", "LOTES 2"))
assert s.find(f"{N}LineStyle/{N}color").text == "ffff00ff" and s.find(f"{N}LineStyle/{N}width").text == "6"
# la calle: roja, grosor por defecto = 2 px, largo de medio círculo
pc = pm_de("CALLES", "CALLES 1")
assert pc.find(N + "LineString") is not None and pc.find(f"{N}LineString/{N}tessellate").text == "1"
assert estilo(pc).find(f"{N}LineStyle/{N}color").text == "ff0000ff"
assert estilo(pc).find(f"{N}LineStyle/{N}width").text == "2"
assert "Largo 62,8" in pc.find(N + "description").text
# el sombreado: dos polígonos (MultiGeometry), uno con su hueco; sin borde
ps = carpetas["SOMBRAS"].find(N + "Placemark")
pols = ps.findall(f"{N}MultiGeometry/{N}Polygon")
assert len(pols) == 2 and sorted(len(p.findall(N + "innerBoundaryIs")) for p in pols) == [0, 1]
s = estilo(ps)
assert s.find(f"{N}PolyStyle/{N}color").text == "66ff0000" and s.find(f"{N}PolyStyle/{N}outline").text == "0"
assert "Área 1.600,00 m²" in ps.find(N + "description").text            # 1600 - 100 + 100
# el texto: marcador sin chinche, el rótulo blanco (ACI 7)
pt = pm_de("TEXTOS", "MZA 12")
s = estilo(pt)
assert s.find(f"{N}IconStyle/{N}scale").text == "0" and s.find(f"{N}LabelStyle/{N}color").text == "ffffffff"
lo, la, _z = pt.find(f"{N}Point/{N}coordinates").text.split(",")
assert math.dist((float(lo), float(la)), vuelta.transform(X0 + 5, Y0 + 5)) < 1e-9
# el bloque: marcador con su nombre y sus atributos en la tabla del globo
pb = pm_de("MOJONES", "MOJON")
assert {x.get("name"): x.find(N + "value").text for x in pb.iter(N + "Data")} == {"NUMERO": "M-7"}
assert estilo(pb).find(f"{N}IconStyle/{N}color").text == "ff00ffff"
assert len(carpetas["MOJONES"].findall(N + "Placemark")) == 2           # el bloque y el punto
print("ok KMZ: doc.kml, carpetas, estilos (color ACI, grosor, relleno 40 %), sombreados, textos, bloques, ExtendedData")

# ------------------------------------------------------------- 5. opciones
# todo junto, sin relleno, nombre desde un atributo, KML de texto
plan2 = KML.plan_kml([lote, lote2, h, calle, txt], d, "Junto", por_capa=False, relleno=0,
                     campo_nombre="PARTIDA")
kml = KML.escribir(plan2, salida / "junto.kml")
raiz = ET.parse(kml).getroot()
assert raiz.find(f"{N}Document/{N}Folder") is None
assert len(raiz.findall(f"{N}Document/{N}Placemark")) == 5
nombres = [pm.find(N + "name").text for pm in raiz.iter(N + "Placemark")]
assert nombres[0] == "01-0042" and nombres[1] == "LOTES 2", nombres     # sin el atributo: capa y número (su lugar en la capa)
for s in raiz.iter(N + "PolyStyle"):
    assert s.find(N + "fill").text == "0" and s.find(N + "outline").text == "1"   # sin relleno, el borde
# polilíneas cerradas como líneas
plan3 = KML.plan_kml([lote], d, cerradas_como_poligono=False)
assert plan3.marcas[0].tipo == "linea" and plan3.marcas[0].geometria[0] == plan3.marcas[0].geometria[-1]
# relleno opaco
assert KML.color_kml("#123456", round(100 * 2.55)) == "ff563412"
print("ok opciones: todo junto, sin relleno, nombre desde un atributo, .kml, cerradas como líneas")

# ------------------------------------------------------------- 6. seguridad
# sin sistema no se exporta (la ventana lo pregunta y lo asigna)
sin = Document(ezdxf.new("R2018"))
sin.modelspace().add_point((1, 1))
try:
    KML.plan_kml(list(sin.modelspace()), sin.doc); raise AssertionError("exportó sin sistema")
except ValueError as exc:
    assert "SISTEMAGEO" in str(exc)
# reemplazar un archivo que ya está: por un temporal, sin dejar rastro
viejo = salida / "prueba.kmz"
KML.escribir(KML.plan_kml([txt], d, "Otro"), viejo)
with zipfile.ZipFile(viejo) as z:
    assert b"<name>Otro</name>" in z.read("doc.kml")
assert sorted(p.name for p in salida.iterdir()) == ["junto.kml", "prueba.kmz"]
assert "Ábralo en Google Earth" in KML.resumen(plan, kmz) and "5 carpeta(s)" in KML.resumen(plan, kmz)
assert "todo junto" in KML.resumen(plan2, kml)
# un punto fuera del área de la faja: se cuenta, no rompe
lejos = msp.add_point((1e12, 1e12))
p4 = KML.plan_kml([lejos, txt], d)
assert len(p4.marcas) == 1 and sum(p4.salteados.values()) == 1, p4.salteados
print("ok seguridad: sin sistema no exporta, reemplazo sin rastro, lo que no se convierte se cuenta")

# ------------------------------------------------------------- 7. 3.29.1: control de faja
# el plano de Candelaria: X de faja 6 (6.620.549) declarado en faja 7 -> 700 km al oeste
xs = IX.este_de(msp)
assert IX.faja_de_x(xs) == 7                                    # Posadas en faja 7: 7.4xx.xxx
assert IX.faja_sugerida(SIS, xs) == ""                          # concuerdan: no se avisa
assert IX.faja_sugerida("EPSG:5348", xs) == SIS                 # declarado en faja 6: se propone la 7
assert IX.faja_sugerida("EPSG:22196", xs) == "EPSG:22197"       # el mismo datum (Campo Inchauspe)
assert IX.faja_sugerida("", xs) == SIS                          # sin sistema: POSGAR 2007 de esa faja
assert IX.faja_de("EPSG:22196") == (6, 22191) and IX.faja_de("EPSG:32721") is None
assert IX.faja_sugerida("EPSG:32721", xs) == ""                 # UTM: no se puede decir
assert IX.faja_de_x([6_620_549.0, 6_620_600.0, 10.0]) == 6      # un objeto suelto en 0,0 no cuenta
assert IX.faja_de_x([6_620_549.0, 10.0]) is None                # mitad y mitad: no se dice
assert IX.faja_de_x([]) is None and IX.faja_de_x([12_000_000.0]) is None
# bloques con nombre automático (A$C… de copiar y pegar, *U anónimos): sin rótulo
assert KML.nombre_automatico("A$CBF30FDEB") and KML.nombre_automatico("*U12")
assert not KML.nombre_automatico("MOJON") and not KML.nombre_automatico("A$CASA")
pegado = d.blocks.new("A$CBF30FDEB"); pegado.add_circle((0, 0), 1)
# 3.29.2: los bloques sin datos van como su dibujo, sin marcador ni rótulo (como en IngeCAD)
d.layers.add("PUERTAS", color=4)
puerta = d.blocks.new("Puerta 1")
puerta.add_line((0, 0), (1, 0))                                       # capa 0 -> la del bloque
puerta.add_line((0, 0), (0, 1), dxfattribs={"layer": "CALLES", "color": 0})   # color por bloque
puerta.add_blockref(pegado.name, (2, 0))                              # anidado
p_ins = msp.add_blockref("Puerta 1", (X0 + 1, Y0 + 1), dxfattribs={"layer": "PUERTAS", "color": 6})
p5 = KML.plan_kml([p_ins], d)
assert [(m.tipo, m.capa) for m in p5.marcas] == [("linea", "PUERTAS"), ("linea", "CALLES"),
                                                 ("poligono", "PUERTAS")], p5.marcas
assert p5.marcas[1].color == KML.color_de(p_ins, d) != p5.marcas[0].color   # magenta del bloque / cian de la capa
lo, la = p5.marcas[0].geometria[1]
assert math.dist((lo, la), vuelta.transform(X0 + 2, Y0 + 1)) < 1e-9          # en su lugar
raiz5 = ET.fromstring(KML.texto_kml(p5))
assert not list(raiz5.iter(N + "Point")) and "Puerta 1" not in KML.texto_kml(p5)
# con datos (atributos): marcador con su tabla; con nombre automático, sin rótulo
con = d.blocks.new("A$C0123ABCD"); con.add_circle((0, 0), 1); con.add_attdef("NUMERO", (0, 1))
c_ins = msp.add_blockref(con.name, (X0 + 1, Y0 + 1), dxfattribs={"layer": "MOJONES"})
c_ins.add_auto_attribs({"NUMERO": "M-9"})
anonimo = d.blocks.new_anonymous_block(); anonimo.add_circle((0, 0), 1); anonimo.add_attdef("N", (0, 1))
a_ins = msp.add_blockref(anonimo.name, (X0 + 1, Y0 + 1)); a_ins.add_auto_attribs({"N": "1"})
p6 = KML.plan_kml([c_ins, a_ins, ins], d)
assert [(m.tipo, m.nombre) for m in p6.marcas] == [("bloque", ""), ("bloque", ""), ("bloque", "MOJON")]
assert p6.marcas[0].datos == [("NUMERO", "M-9")]
raiz6 = ET.fromstring(KML.texto_kml(p6))
assert [pm.find(N + "name") is None for pm in raiz6.iter(N + "Placemark")] == [True, True, False]
print("ok 3.29.1/3.29.2: faja según las X; bloques sin datos desarmados, con datos como marcador (automáticos sin rótulo)")

# ------------------------------------------------------------- 8. 3.29.1: las ventanas (con el Qt de IngeCAD)
try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
except Exception:  # noqa: BLE001 -- sin PySide6: lo demás ya está probado
    print("(sin PySide6: no se arman las ventanas)")
else:
    app = QApplication.instance() or QApplication([])
    UI = import_module("ingecad_plugin_geocad.intercambio_ui")
    vistos, boton = [], [""]

    def falso_exec(caja):
        vistos.append((caja.text(), [b.text() for b in caja.buttons()]))
        caja._clic = next((b for b in caja.buttons() if boton[0] and b.text() == boton[0]), None)
        return 0
    QMessageBox.exec = falso_exec
    QMessageBox.clickedButton = lambda caja: getattr(caja, "_clic", None)

    class Ctx:
        def __init__(c, documento):
            c.document, c.host, c.ecos, c.cmds = documento, None, [], []

        def echo(c, t):
            c.ecos.append(t)

        def execute(c, cmd):
            c.cmds.append(cmd); write_georef(c.document.doc, Georef(crs=cmd.code))
    plano = Document(ezdxf.new("R2018"))
    for x in (6_620_549, 6_620_560, 6_620_580):
        plano.modelspace().add_point((x, 6_960_512))
    plano.modelspace().add_point((0, 0))                    # un objeto suelto
    for b, esperado, cambia in (("Usar faja 6", "EPSG:22196", True), ("Dejar faja 7", "EPSG:22197", False),
                                ("", "", False)):
        write_georef(plano.doc, Georef(crs="EPSG:22197")); boton[0] = b; ctx = Ctx(plano)
        assert UI._asegurar_sistema(ctx) == esperado and bool(ctx.cmds) == cambia, b
    texto, botones = vistos[-1]
    assert "empiezan con 6 (6.620.549 a 6.620.580)" in texto and "Campo Inchauspe" in texto, texto
    assert botones == ["Usar faja 6", "Cancelar", "Dejar faja 7"], botones
    write_georef(plano.doc, Georef(crs="EPSG:22196")); n = len(vistos)
    assert UI._asegurar_sistema(Ctx(plano)) == "EPSG:22196" and len(vistos) == n   # concuerda: ni pregunta
    dlg = UI.SistemaDialog("", None, "EPSG:5348")
    assert dlg.combo.codigo() == "EPSG:5348"                # la faja propuesta
    print("ok ventanas: aviso de faja (usar, dejar, cancelar), SISTEMAGEO con la faja propuesta")

print("TODO OK test_kml")
