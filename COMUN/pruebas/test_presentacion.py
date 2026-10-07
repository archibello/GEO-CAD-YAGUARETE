"""3.0.0 GIS to CAD, lado QGIS: lo que se manda con cada capa (presentacion.py).
Las funciones sueltas se prueban siempre; con QGIS instalado, también contra
capas de verdad (sin ventanas)."""
import json, os, sys, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "QGIS", "codigo"))
from importlib import import_module

# el módulo se carga sin el resto del complemento
import importlib.util
spec = importlib.util.spec_from_file_location(
    "presentacion", os.path.join(HERE, "..", "..", "QGIS", "codigo", "geocad", "presentacion.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)

assert P.height_in_map(2.5, "millimeters", 1000) == 2.5
assert abs(P.height_in_map(10, "points", 500) - 10 * 25.4 / 72 * 0.5) < 1e-9
assert P.height_in_map(4, "mapunits", 99999) == 4
assert P.readable(180) == 0 and P.readable(135) == -45 and P.readable(-100) == 80 and P.readable(90) == 90
assert P.azimuth_to_ccw(0) == 90 and abs(P.azimuth_to_ccw(3.141592653589793 / 4) - 45) < 1e-9
class U:  # enum de QGIS 4 (con .name) y de QGIS 3 (texto)
    name = "RenderMillimeters"
assert P.unit_name(U()) == "millimeters" and P.unit_name("QgsUnitTypes.RenderPoints") == "points"
cfg = {"version": 2, "layers": [{"name": "0", "color": {"aci": 7, "rgb": None}},
                                {"name": "MUROS", "color": {"aci": 3, "rgb": None}, "linetype": "DASHED", "lineweight": 0.5}]}
t = P.capas_table(json.dumps(cfg))
assert t == {"": {"color": 7, "rgb": None, "tipo": "Continuous", "grosor": -1},
             "MUROS": {"color": 3, "rgb": None, "tipo": "DASHED", "grosor": 0.5}}, t
assert P.capas_table("no es json") == {}
# rectángulo de texto y ajuste: un cuadrado de 10 adentro de otro de 10x10 no entra; achicado sí
b = P.box(5, 5, 4, 2, 90, "c"); assert all(abs(a - c) < 1e-9 for p_, q in zip(b, [(6, 3), (6, 7), (4, 7), (4, 3)]) for a, c in zip(p_, q)), b
inside = lambda pts: all(0 <= x <= 10 and 0 <= y <= 10 for x, y in pts)
assert P.fit_factor(inside, 5, 5, 4, 2, 0) == 1.0
k = P.fit_factor(inside, 5, 5, 30, 3, 0); assert 0.1 < k < 0.34 and 30 * k <= 10, k
assert P.fit_factor(inside, 50, 50, 1, 1, 0) == 0.1          # afuera: lo mínimo
assert P.text_width("abcd", 2.0) == 4.8
# 3.1.1 fondo de etiquetas: como lo calcula QGIS
assert P.background_size("rectangle", "buffer", 4, 2, 0.5, 0.25) == (5.0, 2.5)
assert P.background_size("square", "buffer", 4, 2) == (4, 4)
W, H = P.background_size("circle", "buffer", 3, 4, 1, 1); assert W == H == 7.0, (W, H)
W, H = P.background_size("ellipse", "buffer", 4, 2); assert abs(W - 4 * 2 ** .5) < 1e-9 and abs(H - 2 * 2 ** .5) < 1e-9
assert P.background_size("circle", "fixed", 4, 2, 6, 3) == (6, 6)
assert P.background_size("rectangle", "percent", 4, 2, 50, 0) == (6.0, 3.0)
assert P.text_height(2.0) == 2.0
# 3.4.0 tramos del tamaño de la pantalla, superpuestos, que cubren la zona
t1 = P.tiles((0, 0, 5, 5), 10, 10); assert t1 == [(-2.5, -2.5, 7.5, 7.5)], t1   # entra en uno
t4 = P.tiles((0, 0, 18, 10), 10, 10); assert len(t4) == 2, t4
assert t4[0][0] <= 0 and t4[-1][2] >= 18 and t4[0][2] > t4[1][0]          # cubren y se pisan
big = P.tiles((0, 0, 1000, 1000), 10, 10); assert big is None                # demasiados
assert len(P.tiles((0, 0, 1000, 1000), 10, 10, limit=100000)) == 125 ** 2
assert P._inside_rect((0, 0, 10, 10), 5, 5) and not P._inside_rect((0, 0, 10, 10), 11, 5)
print("ok funciones sueltas")

try:
    from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer,
                           QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
                           QgsProperty, QgsMarkerSymbol, QgsSingleSymbolRenderer, Qgis)
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import QSizeF
except ImportError:
    print("(sin QGIS en este equipo: se saltean las pruebas con capas de verdad)")
    print("TODO OK PRESENTACION")
    raise SystemExit(0)

app = QgsApplication([], False); app.initQgis()

def labels(layer, field, size, unit, placement=None, rotation_expr=None, color="#00ff00", expr=False):
    s = QgsPalLayerSettings(); s.fieldName = field; s.isExpression = expr
    if placement is not None: s.placement = placement
    fmt = QgsTextFormat(); fmt.setSize(size); fmt.setSizeUnit(unit); fmt.setColor(QColor(color)); s.setFormat(fmt)
    if rotation_expr:
        s.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.LabelRotation,
                                              QgsProperty.fromExpression(rotation_expr))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s)); layer.setLabelsEnabled(True)

def add(layer, wkt, values):
    f = QgsFeature(layer.fields()); f.setGeometry(QgsGeometry.fromWkt(wkt)); f.setAttributes(values)
    assert layer.dataProvider().addFeatures([f])

# líneas gestionadas por Capas, con LAYER_CODE y CAD_COLOR; etiquetas paralelas en mm
lin = QgsVectorLayer("LineString?crs=EPSG:5347&field=NOMBRE:string&field=LAYER_CODE:string&field=CAD_COLOR:string", "lin", "memory")
add(lin, "LineString(0 0, 10 10)", ["E1", "MUROS", ""])
add(lin, "LineString(0 0, -10 0)", ["E2", "0", "#ff0000"])
add(lin, "LineString(0 5, 10 5)", [None, "", ""])
lin.setCustomProperty(P.CAPAS_KEY, json.dumps(cfg))
labels(lin, "NOMBRE", 2.5, Qgis.RenderUnit.Millimeters, Qgis.LabelPlacement.Line)
pres = P.of_layer(lin, None, 1000)
print(json.dumps(pres))
assert pres["campo_capa"] == "LAYER_CODE" and pres["campo_color"] == "CAD_COLOR"
assert pres["capas"]["MUROS"]["color"] == 3
ids = sorted(int(k) for k in pres["objetos"]); a, b, c = [str(i) for i in ids]
assert pres["objetos"][a] == ["MUROS", ""] and pres["objetos"][b] == ["", "#ff0000"] and pres["objetos"][c] == ["", ""]
r = pres["rotulos"]; assert set(r) == {a, b}, r                    # el que no tiene texto no va
assert r[a][:6] == ["E1", 5.0, 5.0, 2.5, 45.0, "c"] and r[a][6] == "#00ff00", r[a]
assert r[b][4] == 0.0, r[b]                                        # de derecha a izquierda: legible
# sólo los seleccionados, y en otra escala
pres = P.of_layer(lin, None, 500, fids=[ids[0]])
assert list(pres["objetos"]) == [a] and pres["rotulos"][a][3] == 1.25
# rótulos apagados / estilo apagado
assert "rotulos" not in P.of_layer(lin, None, 1000, with_labels=False)
assert set(P.of_layer(lin, None, 1000, with_style=False)) == {"rotulos"}

# puntos sin Capas: color de la simbología; giro y altura definidos por datos (en unidades del mapa)
pts = QgsVectorLayer("Point?crs=EPSG:5347&field=ID:integer&field=ANG:double", "pts", "memory")
add(pts, "Point(100 200)", [7, 30.0])
pts.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"color": "#123456"})))
labels(pts, "'P' || \"ID\"", 3, Qgis.RenderUnit.MapUnits, rotation_expr='"ANG"', expr=True)
pres = P.of_layer(pts, None, 1000)
fid = next(iter(pres["objetos"]))
assert pres["campo_capa"] == "" and "capas" not in pres and pres["objetos"][fid] == ["", "#123456"], pres
assert pres["rotulos"][fid][:6] == ["P7", 101.5, 200.0, 3.0, -30.0, "i"], pres["rotulos"]
# polígonos: rótulo sobre la superficie; capa sin etiquetas -> sin rótulos
pol = QgsVectorLayer("Polygon?crs=EPSG:5347&field=N:string", "pol", "memory")
add(pol, "Polygon((0 0, 10 0, 10 10, 0 10, 0 0))", ["X"])
labels(pol, "N", 10, Qgis.RenderUnit.Points)
pres = P.of_layer(pol, None, 2000)
fid = next(iter(pres["rotulos"])); x, y = pres["rotulos"][fid][1:3]
assert 0 < x < 10 and 0 < y < 10 and abs(pres["rotulos"][fid][3] - 10 * 25.4 / 72 * 2) < 1e-6
pol.setLabelsEnabled(False); assert "rotulos" not in P.of_layer(pol, None, 2000)

# 3.1.0 símbolos: forma, tamaño (mm -> mapa) y giro (horario -> antihorario); rótulo al costado
sym = QgsMarkerSymbol.createSimple({"name": "star", "size": "4", "angle": "15", "color": "#ff0000"})
pts.setRenderer(QgsSingleSymbolRenderer(sym))
pres = P.of_layer(pts, None, 1000, with_symbols=True)
fid = next(iter(pres["simbolos"]))
assert pres["simbolos"][fid] == ["star", 4.0, -15.0], pres["simbolos"]
assert pres["rotulos"][fid][1] == 103.5 and pres["objetos"][fid][1] == "#ff0000", pres
assert "simbolos" not in P.of_layer(pts, None, 1000) and "simbolos" not in P.of_layer(lin, None, 1000, with_symbols=True)
# achicar hasta que entren: el rótulo del polígono (10 x 10) y el símbolo dentro de una parcela
pol.setLabelsEnabled(True)
labels(pol, "'Parcela 12'", 10, Qgis.RenderUnit.Millimeters, expr=True)
real = P.of_layer(pol, None, 1000)["rotulos"]; fid = next(iter(real))
assert real[fid][3] == 10.0                                     # tamaño real aunque la supere
fit = P.of_layer(pol, None, 1000, parcels=P.Parcels([pol]))["rotulos"][fid]
assert 1.0 < fit[3] < 10.0 and P.text_width(fit[0], fit[3], QgsTextFormat().font()) <= 10, fit
par = QgsVectorLayer("Polygon?crs=EPSG:5347&field=N:string", "par", "memory")
add(par, "Polygon((95 195, 105 195, 105 205, 95 205, 95 195))", ["P"])
big = P.of_layer(pts, None, 5000, with_symbols=True, with_labels=False)["simbolos"]
small = P.of_layer(pts, None, 5000, with_symbols=True, with_labels=False, parcels=P.Parcels([par]))["simbolos"]
f0 = next(iter(big)); assert big[f0][1] == 20.0 and small[f0][1] <= 10.0, (big, small)
# 3.1.1 fondo círculo (borde azul) alrededor del texto: centro, tamaño, giro; se achica con el texto
from qgis.core import QgsTextBackgroundSettings
pol.setLabelsEnabled(True)
labels(pol, "'0131'", 4, Qgis.RenderUnit.Millimeters, expr=True)
s = pol.labeling().settings(); fmt = s.format(); bg = QgsTextBackgroundSettings()
bg.setEnabled(True); bg.setType(QgsTextBackgroundSettings.ShapeType.ShapeCircle)
bg.setSizeType(QgsTextBackgroundSettings.SizeType.SizeBuffer); bg.setSize(QSizeF(1, 1))
bg.setSizeUnit(Qgis.RenderUnit.Millimeters); bg.setStrokeColor(QColor("#1f77b4")); bg.setStrokeWidth(0.5)
fmt.setBackground(bg); s.setFormat(fmt); pol.setLabeling(QgsVectorLayerSimpleLabeling(s))
r = P.of_layer(pol, None, 1000)["rotulos"]; fid = next(iter(r)); print("fondo:", r[fid])
shape, cx, cy, W, H, ang, col = r[fid][7]
assert shape == "circle" and (cx, cy) == tuple(r[fid][1:3]) and W == H and W > 6 and col == "#1f77b4", r[fid]
fit = P.of_layer(pol, None, 5000, parcels=P.Parcels([pol]))["rotulos"][fid]
assert fit[7][3] <= 10 and fit[3] < 20, fit                     # el círculo entra en la parcela de 10
bg.setEnabled(False); fmt.setBackground(bg); s.setFormat(fmt); pol.setLabeling(QgsVectorLayerSimpleLabeling(s))
assert len(P.of_layer(pol, None, 1000)["rotulos"][fid]) == 7     # sin fondo, como antes
# sólo los rótulos que QGIS muestra
assert "rotulos" in P.of_layer(pol, None, 1000, shown=set()) and not P.of_layer(pol, None, 1000, shown=set())["rotulos"]
from qgis.core import QgsMapSettings, QgsRectangle
from qgis.PyQt.QtCore import QSize
ms = QgsMapSettings(); ms.setLayers([pol]); ms.setDestinationCrs(pol.crs()); ms.setOutputSize(QSize(400, 400))
ms.setExtent(QgsRectangle(-5, -5, 15, 15))
pol.setLabelsEnabled(True); labels(pol, "N", 8, Qgis.RenderUnit.Points)
vis = P.visible_labels(None, ms); print("visibles:", vis)
assert vis.get(pol.id()) == {int(fid)}, vis
ms.setExtent(QgsRectangle(1000, 1000, 1010, 1010))              # fuera de la vista: no se muestra
assert not P.visible_labels(None, ms).get(pol.id())
# 3.4.0 A: lo que QGIS no muestra en pantalla queda afuera; lo de fuera de la pantalla va siempre
anchor = P.of_layer(pol, None, 1000)["rotulos"][fid]
assert not P.of_layer(pol, None, 1000, shown=set(), screen=(-5, -5, 15, 15))["rotulos"]
out = P.of_layer(pol, None, 1000, shown=set(), screen=(1000, 1000, 1010, 1010))["rotulos"]
assert out.get(fid) == anchor, out
assert P.of_layer(pol, None, 1000, shown={int(fid)}, screen=(-5, -5, 15, 15))["rotulos"].get(fid)
# 3.4.0 B: la pantalla está lejos, pero en toda la zona QGIS sí lo muestra
zone = P.visible_labels_zone(ms, (-5, -5, 15, 15)); print("zona:", zone)
assert zone.get(pol.id()) == {int(fid)}, zone
assert P.visible_labels_zone(ms, (-1e7, -1e7, 1e7, 1e7)) is None             # demasiado grande

# la ventana «Enviar a IngeCAD»
from geocad import envio_ui, config
o = envio_ui.from_config("pantalla")
assert o == {"modo": "pantalla", "escala": 0, "capas_colores": True, "rotulos": "visibles_resto",
             "simbolos": True, "ajustar": False, "preguntar": True}, o
dlg = envio_ui.EnvioDialog(None, o, 2500)
assert dlg.values() == o and not dlg.escala.isEnabled()
o2 = dict(o, modo="seleccion", escala=500, rotulos="visibles", ajustar=True, capas_colores=False, preguntar=False)
dlg.set_values(o2); assert dlg.values() == o2, dlg.values()
envio_ui.remember(o2)
assert envio_ui.from_config("seleccion") == o2 and config.get("envio_predeterminado") == "seleccion"
assert envio_ui.ask(None, "completa", 1000) == dict(o2, modo="completa")   # no pregunta más: lo guardado
dlg.set_values(dict(o2, rotulos="ninguno")); assert dlg.values()["rotulos"] == "ninguno"
# 3.4.0 las opciones nuevas se eligen, se guardan y vuelven; lo guardado antes sigue valiendo
for rot in ("visibles_resto", "visibles_zona", "todos", "visibles"):
    o3 = dict(o2, rotulos=rot); dlg.set_values(o3); assert dlg.values() == o3, dlg.values()
    envio_ui.remember(o3); assert envio_ui.from_config("seleccion")["rotulos"] == rot, rot
    assert config.get("rotulos_visibles") == (rot != "todos")
# lo guardado con 3.3.x: «todos» sigue en todos; «sólo los que QGIS muestra» pasa a A
config.save({"rotulos_cuales": "visibles_resto", "rotulos_visibles": False}, "qgis")
assert envio_ui.from_config("seleccion")["rotulos"] == "todos"
config.save({"rotulos_cuales": "todos", "rotulos_visibles": True}, "qgis")
assert envio_ui.from_config("seleccion")["rotulos"] == "visibles_resto"
assert envio_ui.ROTULOS[0][0] == "visibles_resto"                          # A, primera
envio_ui.remember(dict(o2, rotulos="ninguno"))
assert envio_ui.from_config("seleccion")["rotulos"] == "ninguno"
app.exitQgis()
print("TODO OK PRESENTACION")
