"""Tablas (3.22.0): PEGARTABLA en la barra GeoCAD de IngeCAD. Reconoce de
dónde viene lo copiado (GenOffice, QGIS, Calc, Excel, texto), pega como
tabla con el formato de la planilla (anchos, combinadas, letras, colores,
espesor de los bordes), ubicada con dos puntos que le dan la escala (modelo
o papel), o como dibujo y textos (la geometría de QGIS en su lugar)."""
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import json
from pathlib import Path
from importlib import import_module
from core.commands import History
from core.document import Document
from core.plugins import load_plugin

RAIZ = Path(__file__).resolve().parents[2]
lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
spec = lp.spec
T = import_module("ingecad_plugin_geocad.tablas")
PT = import_module("ingecad_plugin_geocad.pegartabla")
barra = import_module("ingecad_plugin_geocad.barra")
yag = import_module("ingecad_plugin_geocad.yaguarete")
modulos = import_module("ingecad_plugin_geocad.modulos")

# -- el núcleo es el mismo en los dos lados
for lado in ("INGECAD", "QGIS"):
    assert (RAIZ / lado / "codigo" / "geocad" / "tablas.py").read_bytes() == \
        (RAIZ / "COMUN" / "nucleo" / "tablas.py").read_bytes(), lado

# ================================================================ origen
# GenOffice: el HTML tal como lo deja (sonda del 14/10/2026), con datos inventados
TD = ('<td style="font-family: Arial; font-size: 11pt; --data-rotate: (0deg);padding-bottom: 2pt; '
      'padding-left: 2pt; padding-right: 2pt; border-bottom: 0.5pt solid #000000; border-top: {t}pt '
      'solid #000000; border-right: 0.5pt solid #000000; border-left: 1pt solid #000000; {extra}"'
      '{span}>{txt}</td>')
GENOFFICE = (
    '<html><head></head><body><google-sheets-html-origin><table data-copy-id="cclH8p" '
    'xmlns="http://www.w3.org/1999/xhtml" cellspacing="0" cellpadding="0" dir="ltr" '
    'style="table-layout:fixed;font-size:10pt;font-family:Arial;width:0px;border-collapse:collapse;'
    'border:none"><colgroup><col width="69.33333333333333"><col width="69.33333333333333">'
    '<col width="100"></colgroup><tbody>'
    '<tr style="height: 20px;">'
    + TD.format(t=1, extra="font-weight: bold; color: #c00000; text-align: center;", span=' colspan="2"',
                txt="CUADRO DE SUPERFICIES")
    + TD.format(t=1, extra="font-style: italic;", span=' rowspan="2"', txt="Obs.") + '</tr>'
    '<tr style="height: 20px;">'
    + TD.format(t=0.5, extra="font-weight:bold; background-color: #ddebf7;", span="", txt="Lote")
    + TD.format(t=0.5, extra="", span="", txt="Sup. m&sup2;") + '</tr>'
    '<tr style="height: 20px;">'
    + TD.format(t=0.5, extra="", span="", txt="1")
    + TD.format(t=0.5, extra="text-align:right", span="", txt="452,37")
    + TD.format(t=0.5, extra="", span="", txt="esquina {norte}") + '</tr>'
    '</tbody></table></google-sheets-html-origin></body></html>')
GENOFFICE_TXT = "CUADRO DE SUPERFICIES\t\tObs.\nLote\tSup. m²\t\n1\t452,37\tesquina {norte}\n"
QGIS_TXT = ("wkt_geom\tname\tsup\tpartida\n"
            "MultiPolygon (((0 0, 100 0, 100 50, 0 50, 0 0)))\t0001\t5000\tP-1\n"
            "Polygon ((200 0, 300 0, 300 100, 200 100, 200 0), (240 40, 260 40, 260 60, 240 60, 240 40))"
            "\t0002\t9600\tP-2\n"
            "LineString (0 200, 30 240, 60 200)\t0003\t\t\n"
            "Point Z (500 500 12)\t0004\t\tP-4\n"
            "\t0005\t\tsin geometría\n")
QGIS_HTML = ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"><html><head>'
             '<meta http-equiv="content-type" content="text/html; charset=utf-8"/></head><body>'
             '<table border="1"><tr><td>wkt_geom</td><td>name</td></tr></table></body></html>')
LIBRE = ('<html><head><meta name="generator" content="LibreOffice 7.6.4.1 (Linux)"/></head><body>'
         '<table cellspacing="0" border="0"><colgroup width="120"></colgroup><colgroup width="80"></colgroup>'
         '<tr><td style="border-top: 1px solid #000000; border-bottom: 1px solid #000000" height="20" '
         'align="center" bgcolor="#FFFF00"><b><font face="DejaVu Sans" size="3" color="#0000FF">Punto</font>'
         '</b></td><td align="right" sdval="12.5" sdnum="3082;">12,5</td></tr>'
         '<tr><td><i>A</i></td><td>3</td></tr></table></body></html>')
EXCEL = ('<html xmlns:x="urn:schemas-microsoft-com:office:excel"><head><style>'
         '<!--.xl65 {font-weight:700; color:red; border:.5pt solid windowtext;} '
         '.xl66 {text-align:center; background:#92D050;}--></style></head><body>'
         '<table><tr><td class="xl65" width="64">X</td><td class="xl66">Y</td></tr>'
         '<tr><td>1</td><td>2</td></tr></table></body></html>')

assert T.detectar(GENOFFICE, GENOFFICE_TXT) == "genoffice"
assert T.detectar(GENOFFICE.replace('data-copy-id', 'data-sheets-value="x" data-copy-id'), "") == "google"
assert T.detectar("", "", "genoffice-app://sheets/1") == "genoffice"
assert T.detectar(QGIS_HTML, QGIS_TXT) == "qgis"
assert T.detectar(LIBRE, "Punto\t12,5") == "libreoffice"
assert T.detectar(EXCEL, "X\tY") == "excel"
assert T.detectar("", "a;b\n1;2") == "texto"
assert T.leer("", "") is None and T.leer("<p>hola</p>", "") is None

# ================================================================ GenOffice con su formato
t = T.leer(GENOFFICE, GENOFFICE_TXT)
assert (t.origen, t.n_filas, t.n_cols, t.con_formato) == ("genoffice", 3, 3, True)
assert [round(w, 2) for w in t.anchos_mm] == [18.34, 18.34, 26.46], t.anchos_mm
assert [round(h, 2) for h in t.altos_mm] == [5.29] * 3
por = {(c.fila, c.col): c for c in t.celdas}
assert len(t.celdas) == 7                        # 9 casillas, dos ocupadas por combinadas
tit = por[(0, 0)]
assert (tit.cols, tit.filas, tit.negrita, tit.color, tit.alin_h, tit.fuente, tit.tam_pt) == \
    (2, 1, True, "#c00000", "centro", "Arial", 11.0)
assert round(tit.bordes["arriba"].grosor_mm, 3) == 0.353 and round(tit.bordes["abajo"].grosor_mm, 3) == 0.176
assert por[(0, 2)].filas == 2 and por[(0, 2)].cursiva
assert por[(1, 0)].fondo == "#ddebf7" and por[(1, 1)].texto == "Sup. m²"
assert por[(2, 1)].alin_h == "derecha" and por[(2, 2)].texto == "esquina {norte}"
assert t.grilla()[2] == ["1", "452,37", "esquina {norte}"]
CORTO = lambda texto, alto, negrita=False, cursiva=False, fuente="": 1.0   # todo entra: la geometría de la planilla
a = T.armar(t, medir=CORTO)
W, H = a.ancho_mm, a.alto_mm
assert abs(W - (2 * 69.33333333333333 + 100) * T.PX_MM) < 1e-9 and abs(H - 3 * 20 * T.PX_MM) < 1e-9, (W, H)
assert [(f.color, round(f.x1 - f.x0, 2)) for f in a.fondos] == [("#ddebf7", 18.34)]
# cada tramo de borde una sola vez, con el más grueso de los dos lados
assert sorted({T.grosor_dxf(l.grosor_mm) for l in a.lineas}) == [18, 35]
arriba = [l for l in a.lineas if l.y0 == l.y1 == 0.0]
assert len(arriba) == 1 and abs(arriba[0].x1 - W) < 1e-9 and T.grosor_dxf(arriba[0].grosor_mm) == 35
# por dentro de la combinada del título no hay línea vertical
assert not [l for l in a.lineas if l.x0 == l.x1 and abs(l.x0 - 18.34) < 0.01 and l.y0 == 0.0]
assert not [l for l in a.lineas if l.y0 == l.y1 and abs(l.y0 + 5.29) < 0.01 and l.x0 > 36.0]
txt = {x.texto: x for x in a.textos}
assert round(txt["CUADRO DE SUPERFICIES"].alto_mm, 2) == round(11 * T.PT_MM * T.MAYUSCULA, 2) == 2.78
assert (txt["CUADRO DE SUPERFICIES"].alin_h, txt["CUADRO DE SUPERFICIES"].color) == ("centro", "#c00000")
assert round(txt["CUADRO DE SUPERFICIES"].x, 2) == 18.34              # centrada en las dos columnas
assert txt["1"].alin_h == "derecha" and txt["esquina {norte}"].alin_h == "izquierda"
assert txt["Obs."].cursiva and txt["Lote"].negrita and txt["Lote"].fuente == "Arial"
# estilo GeoCAD: un solo alto, la grilla completa, encabezado en negrita
g = T.armar(t, respetar_formato=False, alto_texto_mm=3.0)
assert {x.alto_mm for x in g.textos} == {3.0} and not g.fondos
assert {T.grosor_dxf(l.grosor_mm) for l in g.lineas} == {25}
assert all(x.negrita == (x.texto in ("CUADRO DE SUPERFICIES", "Obs.")) for x in g.textos)

# ================================================================ LibreOffice / Excel
lo = T.leer(LIBRE, "Punto\t12,5\nA\t3")
c = {(x.fila, x.col): x for x in lo.celdas}
assert lo.origen == "libreoffice" and lo.con_formato
assert (c[(0, 0)].negrita, c[(0, 0)].color, c[(0, 0)].fondo, c[(0, 0)].fuente, c[(0, 0)].tam_pt,
        c[(0, 0)].alin_h) == (True, "#0000ff", "#ffff00", "DejaVu Sans", 12, "centro")
assert c[(1, 0)].cursiva and c[(0, 1)].alin_h == "derecha"
ex = T.leer(EXCEL, "X\tY\n1\t2")
c = {(x.fila, x.col): x for x in ex.celdas}
assert ex.origen == "excel" and c[(0, 0)].negrita and c[(0, 0)].color == "#ff0000"
assert round(c[(0, 0)].bordes["izquierda"].grosor_mm, 3) == 0.176 and c[(0, 1)].fondo == "#92d050"
assert round(ex.anchos_mm[0], 2) == round(64 * T.PX_MM, 2)

# ================================================================ texto y CSV
tx = T.leer("", "a;b;c\n1;2;3\n")
assert (tx.origen, tx.grilla()) == ("texto", [["a", "b", "c"], ["1", "2", "3"]])
assert T.leer("", 'x,y\n"1,5",2\n').grilla() == [["x", "y"], ["1,5", "2"]]
assert T.numero("7.425.885,37") == 7425885.37 and T.numero("1,5") == 1.5 and T.numero("abc") is None
assert T.grosor_dxf(0.5 * T.PT_MM) == 18 and T.grosor_dxf(T.PT_MM) == 35 and T.grosor_dxf(0) == 0

# ================================================================ QGIS: tabla de atributos
q = T.leer(QGIS_HTML, QGIS_TXT)
assert q.origen == "qgis" and not q.con_formato and q.columna("WKT_GEOM") == 0
assert q.grilla()[1][1] == "0001"                 # el código conserva sus ceros
partes = T.wkt_partes(q.grilla()[2][0])
assert partes[0][0] == "poligono" and len(partes[0][1]) == 2      # con su agujero
assert T.punto_rotulo(T.wkt_partes(q.grilla()[1][0])) == (50.0, 25.0)
assert T.wkt_partes("Point Z (500 500 12)") == [("punto", [(500.0, 500.0)])]
assert T.wkt_partes("MultiPoint ((1 2), (3 4))") == [("punto", [(1.0, 2.0)]), ("punto", [(3.0, 4.0)])]
assert T.wkt_partes("Polygon EMPTY") == [] and T.wkt_partes("basura") == []
# un polígono en C: el rótulo cae adentro
c_forma = [(0, 0), (10, 0), (10, 2), (2, 2), (2, 8), (10, 8), (10, 10), (0, 10), (0, 0)]
assert T.dentro(T.punto_rotulo([("poligono", [c_forma])]), c_forma)
# GeoJSON (Opciones de QGIS: copiar objetos como GeoJSON)
gj = json.dumps({"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"name": "0001", "sup": 10},
     "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 0]]]}}]})
g2 = T.leer("", gj)
assert g2.origen == "qgis" and g2.encabezados() == ["wkt_geom", "name", "sup"]
assert T.wkt_partes(g2.grilla()[1][0])[0][0] == "poligono"
# sin la geometría como tabla
s = T.sin_columnas(q, [0])
assert s.encabezados() == ["name", "sup", "partida"] and s.n_cols == 3
sa = T.armar(s)                                   # sin formato: estilo GeoCAD
assert {x.texto: x.alin_h for x in sa.textos}["0001"] == "izquierda"      # código
assert {x.texto: x.alin_h for x in sa.textos}["5000"] == "derecha"        # número
assert {x.texto: x.alin_h for x in sa.textos}["name"] == "centro"         # encabezado
assert len(sa.lineas) == 4 + 7                    # la grilla de 3 x 6, tramos juntados
# una combinada que cruza una columna quitada se achica
s2 = T.sin_columnas(t, [1])
assert {(c.fila, c.col): c.cols for c in s2.celdas}[(0, 0)] == 1 and s2.n_cols == 2

# ================================================================ el plugin
assert "tablas" in {m.clave for m in modulos.CATALOGO["ingecad"]}
assert spec.tools["GEOPASTETABLE"] is PT.PegarTablaTool
assert spec.aliases["PASTETABLE"] == "GEOPASTETABLE"
botones = [x.command for x in spec.toolbar]
assert "GEOPASTETABLE" in botones and botones.index("GEOPASTETABLE") in barra.cortes(botones)
item = next(x for x in spec.toolbar if x.command == "GEOPASTETABLE")
assert item.icon and Path(item.icon).exists() and "GEOPASTETABLE" in yag.DESCRIPCIONES


def comandos_menu(items):
    for it in items:
        sub = getattr(it, "items", None)
        if sub:
            yield from comandos_menu(sub)
        elif getattr(it, "command", None):
            yield it.command


assert "GEOPASTETABLE" in set(comandos_menu(spec.menu))
es = Path(spec.i18n_dir) / "es"
assert json.loads((es / "ui.json").read_text())["Paste table (PASTETABLE)"] == "Pegar tabla (PEGARTABLA)"
assert json.loads((es / "commands.json").read_text())["GEOPASTETABLE"]["name"] == "PEGARTABLA"
est = modulos.estado("ingecad"); real = modulos.estado
modulos.estado = lambda prog: {**est, "tablas": False}
try:
    apagado = import_module("ingecad_plugin_geocad").construir_spec()
finally:
    modulos.estado = real
assert "GEOPASTETABLE" not in apagado.tools and "GEOPASTETABLE" not in [x.command for x in apagado.toolbar]
assert "GEOPASTETABLE" not in set(comandos_menu(apagado.menu))

# ================================================================ MTEXT con formato
tx = T.Texto(0, 0, "centro", "medio", 2.5, "a{b}\\c\nsegunda", "Arial", True, False, True)
assert PT.contenido_mtext(tx) == "{\\fArial|b1|i0;\\La\\{b\\}\\\\c\\Psegunda\\l}"
assert PT.contenido_mtext(T.Texto(0, 0, "centro", "medio", 2.5, "solo")) == "solo"

# ================================================================ pegar como tabla (modelo)
doc = Document.new(); hist = History(doc); log = []
msp = doc.doc.modelspace()
doc.doc.header["$INSUNITS"] = 6                   # metros
assert PT.unidades_por_mm(doc, 100) == 0.1        # 1 mm de hoja a 1:100 = 0,1 m


class Servicios:
    window = None


def contexto():
    return types.SimpleNamespace(execute=hist.execute, echo=log.append, prompt=log.append,
                                 finish=lambda: log.append("FIN"), services=Servicios())


herramienta = PT.PegarTablaTool(contexto())
herramienta._p1 = None
herramienta.empezar(t, {"modo": "tabla", "respetar": True, "escala": 100.0}, doc)
assert herramienta._k0 == 0.1 and herramienta.ortho_applies()
assert not hasattr(herramienta, "ghost_entities")         # la vista previa son sólo líneas
# la herramienta mide con la fuente real: su tabla puede ser más ancha que a
W, H = herramienta._armado.ancho_mm, herramienta._armado.alto_mm
assert W >= a.ancho_mm - 1e-9 and abs(H - a.alto_mm) < 1e-9
n_lineas = len(herramienta._armado.lineas)
# antes del primer punto: las líneas con la esquina en el cursor (ya con la
# referencia a objetos), tamaño natural, y la marca del punto de inserción
seg = herramienta.preview_segments((10.0, 20.0))
assert len(seg) == n_lineas + 4
xs = [p[0] for s_ in seg[:n_lineas] for p in s_]; ys = [p[1] for s_ in seg[:n_lineas] for p in s_]
assert abs(min(xs) - 10.0) < 1e-9 and abs(max(xs) - (10.0 + W * 0.1)) < 1e-9
assert abs(max(ys) - 20.0) < 1e-9 and abs(min(ys) - (20.0 - H * 0.1)) < 1e-9
herramienta.on_point((1000.0, 2000.0))
assert herramienta._p1 == (1000.0, 2000.0) and not herramienta.ortho_applies()
# después: la tabla llena el rectángulo del primer punto al cursor, con la
# esquina inferior derecha EN el cursor (como TABLE de AutoCAD por ventana):
# 2 x W de ancho y 4 x H de alto; marcas en las dos esquinas
C = (1000.0 + 2 * W, 2000.0 - 4 * H)
seg = herramienta.preview_segments(C)
assert len(seg) == n_lineas + 8
xs = [p[0] for s_ in seg[:n_lineas] for p in s_]; ys = [p[1] for s_ in seg[:n_lineas] for p in s_]
assert abs(min(xs) - 1000.0) < 1e-9 and abs(max(xs) - C[0]) < 1e-6
assert abs(max(ys) - 2000.0) < 1e-9 and abs(min(ys) - C[1]) < 1e-6
marca = seg[-4:]                                   # la marca de la esquina, centrada en el cursor
assert abs(sum(p[0] for s_ in marca for p in s_) / 8 - C[0]) < 1e-6
assert abs(sum(p[1] for s_ in marca for p in s_) / 8 - C[1]) < 1e-6
# hacia arriba y a la izquierda también: la tabla llena el rectángulo igual
o, kx, ky = herramienta.ventana((1000.0 - W, 2000.0 + H))
assert o == (1000.0 - W, 2000.0 + H) and abs(kx - 1.0) < 1e-9 and abs(ky - 1.0) < 1e-9
assert herramienta.ventana((1000.0, 2000.0)) == ((1000.0, 2000.0), 0.1, 0.1)   # sin tamaño: natural
o, kx, ky = herramienta.ventana((1000.0 + W, 2000.0))                       # sin alto: proporcional
assert abs(kx - 1.0) < 1e-9 and kx == ky
herramienta.on_point(C)
assert log[-1] == "FIN" and "pegada" in log[-2], log
nuevos = [e for e in msp if e.dxf.layer == PT.CAPA_TABLA]
tipos = sorted({e.dxftype() for e in nuevos})
assert tipos == ["HATCH", "LINE", "MTEXT"], tipos
assert len([e for e in nuevos if e.dxftype() == "MTEXT"]) == 7
xs = [p for e in nuevos if e.dxftype() == "LINE" for p in (e.dxf.start.x, e.dxf.end.x)]
ys = [p for e in nuevos if e.dxftype() == "LINE" for p in (e.dxf.start.y, e.dxf.end.y)]
assert abs(min(xs) - 1000.0) < 1e-6 and abs(max(xs) - C[0]) < 1e-6
assert abs(max(ys) - 2000.0) < 1e-6 and abs(min(ys) - C[1]) < 1e-6
assert {e.dxf.lineweight for e in nuevos if e.dxftype() == "LINE"} == {18, 35}
tit = next(e for e in nuevos if e.dxftype() == "MTEXT" and "CUADRO" in e.text)
assert tit.text == "{\\fArial|b1|i0;CUADRO DE SUPERFICIES}" and tit.rgb == (0xc0, 0, 0)
assert abs(tit.dxf.char_height - 2.78 * 2.0) < 0.02 and tit.dxf.attachment_point == 8
fondo = next(e for e in nuevos if e.dxftype() == "HATCH")
assert fondo.rgb == (0xdd, 0xeb, 0xf7) and fondo.dxf.solid_fill == 1
assert doc.doc.layers.has_entry(PT.CAPA_TABLA)
grupo = doc.doc.groups.get("TABLA1")
assert grupo is not None and len(list(grupo)) == len(nuevos)
hist.undo()
assert not [e for e in msp if e.dxf.layer == PT.CAPA_TABLA]
assert not doc.doc.layers.has_entry(PT.CAPA_TABLA) and "TABLA1" not in doc.doc.groups
# Enter en el segundo punto: el tamaño natural (1:100 en metros)
log.clear()
herramienta = PT.PegarTablaTool(contexto()); herramienta._p1 = None
herramienta.empezar(t, {"modo": "tabla", "respetar": True, "escala": 100.0}, doc)
herramienta.on_point((0.0, 0.0)); herramienta.on_enter()
xs = [p for e in msp if e.dxftype() == "LINE" for p in (e.dxf.start.x, e.dxf.end.x)]
assert abs(max(xs) - W * 0.1) < 1e-9, max(xs)
# otra tabla: otro grupo
herramienta = PT.PegarTablaTool(contexto()); herramienta._p1 = None
herramienta.empezar(s, {"modo": "tabla", "respetar": False, "alto": 2.5, "escala": 100.0}, doc)
herramienta.on_point((50.0, 0.0)); herramienta.on_enter()
assert "TABLA1" in doc.doc.groups and "TABLA2" in doc.doc.groups

# ================================================================ X (DESCOMPONER) sobre una tabla
from tools.blocks import ExplodeTool
PT.instalar(); PT.instalar()                       # una sola vez
assert ExplodeTool.on_selection._puente_fabrica is PT._envolver_explode
miembros = list(doc.doc.groups.get("TABLA1"))
assert sorted({e.dxftype() for e in miembros}) == ["HATCH", "LINE", "MTEXT"]
poli = msp.add_lwpolyline([(0, -100), (10, -100), (10, -110)])
log.clear()
x = ExplodeTool(contexto()); x.start()
x.on_selection(miembros[:3] + [poli])              # alcanza con una parte de la tabla
assert "1 tabla(s) descompuesta(s)" in log[0] and "sin fondos" in log[0] and "1 objeto(s)" in log[0], log
assert "TABLA1" not in doc.doc.groups and "TABLA2" in doc.doc.groups
quedan = [e for e in miembros if e.is_alive and e.dxf.owner == msp.layout_key and e in msp]
assert sorted({e.dxftype() for e in quedan}) == ["LINE", "MTEXT"], "sólo líneas y textos"
assert not [e for e in msp if e.dxftype() == "HATCH" and e.dxf.layer == PT.CAPA_TABLA]
assert poli not in msp                             # lo demás, X como siempre
hist.undo()
assert "TABLA1" in doc.doc.groups and len(list(doc.doc.groups.get("TABLA1"))) == len(miembros)
assert [e for e in msp if e.dxftype() == "HATCH" and e.dxf.layer == PT.CAPA_TABLA] and poli in msp
# sin tablas entre lo elegido, X como venía
log.clear(); x = ExplodeTool(contexto()); x.start(); x.on_selection([poli])
assert poli not in msp and "TABLA1" in doc.doc.groups
hist.undo()
# con el módulo apagado, X no toca la tabla
modulos.estado = lambda prog: {**est, "tablas": False}
try:
    log.clear(); x = ExplodeTool(contexto()); x.start(); x.on_selection(miembros)
finally:
    modulos.estado = real
assert "TABLA1" in doc.doc.groups and not any("tabla(s)" in str(m) for m in log)

# ================================================================ en el papel
doc2 = Document.new(); hist = History(doc2)
nombre = next(n for n in doc2.doc.layouts.names() if n.lower() != "model")
doc2.active_layout = nombre
lay = doc2.doc.layouts.get(nombre)
assert PT.unidades_por_mm(doc2, 100) == 1.0       # hoja en mm: la escala no cuenta
herramienta = PT.PegarTablaTool(contexto()); herramienta._p1 = None
herramienta.empezar(t, {"modo": "tabla", "respetar": True}, doc2)
herramienta.on_point((20.0, 280.0)); herramienta.on_enter()
en_papel = [e for e in lay if e.dxf.layer == PT.CAPA_TABLA]
assert len(en_papel) > 10 and not [e for e in doc2.doc.modelspace() if e.dxf.layer == PT.CAPA_TABLA]
xs = [p for e in en_papel if e.dxftype() == "LINE" for p in (e.dxf.start.x, e.dxf.end.x)]
assert abs(max(xs) - (20.0 + W)) < 1e-9          # los mm de la planilla en mm de hoja
# hoja dibujada en metros (1 mm = 0,001 unidades, módulo Papel)
lay.dxf.standard_scale_type = 16; lay.dxf.scale_numerator = 1.0; lay.dxf.scale_denominator = 0.001
assert abs(PT.unidades_por_mm(doc2, 100) - 0.001) < 1e-12

# ================================================================ como dibujo y textos
doc3 = Document.new(); hist = History(doc3); log.clear()
herramienta = PT.PegarTablaTool(contexto())
herramienta.empezar(q, {"modo": "dibujo", "rotulos": [1, 3], "alto_rotulo": 2.0}, doc3)
m3 = doc3.doc.modelspace()
dib = [e for e in m3 if e.dxf.layer == PT.CAPA_DIBUJO]
cuenta = {}
for e in dib:
    cuenta[e.dxftype()] = cuenta.get(e.dxftype(), 0) + 1
assert cuenta == {"LWPOLYLINE": 4, "POINT": 1, "MTEXT": 4}, cuenta
cerradas = [e for e in dib if e.dxftype() == "LWPOLYLINE" and e.closed]
assert len(cerradas) == 3 and len(list(cerradas[0].vertices())) == 4      # sin repetir el primero
rot = {e.text: e for e in dib if e.dxftype() == "MTEXT"}
assert set(rot) == {"0001\\PP-1", "0002\\PP-2", "0003", "0004\\PP-4"}, set(rot)
assert tuple(rot["0001\\PP-1"].dxf.insert)[:2] == (50.0, 25.0)
assert rot["0004\\PP-4"].dxf.attachment_point == 4 and rot["0004\\PP-4"].dxf.insert.x > 500
assert "1 fila(s) sin geometría" in log[-2] and log[-1] == "FIN", log
hist.undo(); assert not [e for e in m3 if e.dxf.layer == PT.CAPA_DIBUJO]
# planilla con X / Y: puntos con su rótulo
xy = T.leer("", "Punto\tEste\tNorte\nA\t5.500.100,25\t7.020.000\nB\t5500200\t7020100\nC\t\t\n")
assert T.columnas_xy(xy) == (1, 2)
cmd, n, sin = PT.comando_dibujo(xy, [0], 1.5, col_x=1, col_y=2)
hist.execute(cmd)
pts = sorted(tuple(e.dxf.location)[:2] for e in m3 if e.dxftype() == "POINT")
assert pts == [(5500100.25, 7020000.0), (5500200.0, 7020100.0)] and sin == 1 and n == 4

# ================================================================ 3.23.0: el ancho de las columnas
# (pedido de Fernando, 14/10/2026: la «key» de 19 dígitos se metía en la
# columna siguiente). Ninguna columna queda más angosta que su texto.
KEY = "1234567890123456789"
html_key = ('<google-sheets-html-origin><table data-copy-id="x"><colgroup><col width="100"><col width="60">'
            '</colgroup><tr style="height:20px"><td style="font-family:Arial;font-size:10pt">key</td>'
            '<td style="font-family:Arial;font-size:10pt">name</td></tr>'
            '<tr style="height:20px"><td style="font-family:Arial;font-size:10pt">' + KEY + '</td>'
            '<td style="font-family:Arial;font-size:10pt">Lote 1</td></tr></table>')
tk = T.leer(html_key, "key\tname\n" + KEY + "\tLote 1")
assert tk.con_formato and round(tk.anchos_mm[0], 2) == round(100 * T.PX_MM, 2)
FIJO = lambda texto, alto, negrita=False, cursiva=False, fuente="": 1.6 * alto * len(texto) if texto == KEY else 1.0
ak = T.armar(tk, medir=FIJO)
celdas_k = {x.texto: x for x in ak.textos}
m_key = celdas_k[KEY]
assert abs(m_key.ancho_mm - FIJO(KEY, m_key.alto_mm)) < 1e-9, "la columna = el texto + los márgenes"
# la columna «key» se ensancha; «name» no cambia (su texto entra)
xk = sorted({round(l.x0, 9) for l in ak.lineas if abs(l.x0 - l.x1) < 1e-12})
assert len(xk) == 3 and xk[1] - xk[0] > 100 * T.PX_MM and abs(xk[2] - xk[1] - 60 * T.PX_MM) < 1e-6
assert abs(ak.ancho_mm - xk[2]) < 1e-6 and m_key.alin_h == "derecha" and m_key.x < xk[1]
# medir que falla o no sabe: la cuenta aproximada (nunca más angosta que antes)
def roto(*a, **k):
    raise RuntimeError("sin fuentes")
for med in (roto, lambda *a, **k: None):
    assert abs(T.armar(tk, medir=med).ancho_mm - T.armar(tk).ancho_mm) < 1e-9
assert T.armar(tk).ancho_mm >= 160 * T.PX_MM - 1e-9
# combinada más larga que sus columnas: se ensanchan en proporción
html_comb = html_key.replace('<tr style="height:20px"><td style="font-family:Arial;font-size:10pt">key</td>'
                             '<td style="font-family:Arial;font-size:10pt">name</td></tr>',
                             '<tr style="height:20px"><td colspan="2">' + "T" * 40 + '</td></tr>')
tc = T.leer(html_comb, "")
LARGO = lambda texto, alto, negrita=False, cursiva=False, fuente="": (200.0 if texto.startswith("TT") else 1.0)
ac = T.armar(tc, medir=LARGO)
tit_c = [x for x in ac.textos if x.texto.startswith("TT")][0]
assert tit_c.ancho_mm >= 200.0 - 1e-9
xs_v = sorted({round(l.x0, 6) for l in ac.lineas if abs(l.x0 - l.x1) < 1e-12})
assert len(xs_v) == 3 and abs((xs_v[1] - xs_v[0]) / (xs_v[2] - xs_v[1]) - 100 / 60) < 1e-6
# IngeCAD mide con la fuente con que dibuja el MTEXT (la de ezdxf con los
# parches de IngeCAD): negrita más ancha, y cada texto entra en su celda
med = PT.medidor(doc)
if med is not None and med(KEY, 2.5) is not None:
    assert med(KEY, 2.5) > 0 and med(KEY, 2.5, True) >= med(KEY, 2.5) - 1e-9
    assert abs(med(KEY, 5.0) - 2 * med(KEY, 2.5)) < 1e-6        # proporcional a la altura
    real = T.armar(tk, medir=med)
    for x in real.textos:
        assert med(x.texto, x.alto_mm, x.negrita, x.cursiva, x.fuente or tk.fuente) <= x.ancho_mm + 1e-9, x.texto
    print("  con la fuente real: la key mide", round(med(KEY, real.textos[0].alto_mm, False, False, "Arial"), 2),
          "mm; la estimación daba", round(T.ancho_texto_mm(KEY, real.textos[0].alto_mm), 2))
else:
    print("  (sin fuentes TrueType en este equipo: queda la cuenta aproximada)")

# ================================================================ se dibuja en pantalla
try:
    import core.window_colors  # noqa: F401
except ImportError:
    sys.modules["core.window_colors"] = types.SimpleNamespace(background=lambda espacio: "#212830")
from render.backend import TolerantFrontend, TolerantRenderContext, VertexBackend, frontend_config
import inspect
backend = VertexBackend(0.01, {})
cfg = (frontend_config(0.01, doc) if len(inspect.signature(frontend_config).parameters) > 1
       else frontend_config(0.01))
front = TolerantFrontend(TolerantRenderContext(doc.doc), backend, cfg)
front._host_document = doc
front.draw_entities(msp)
dibujados = {d for b in backend.buckets.values() for d in b.lines_owner + b.triangles_owner}
textos = [e.dxf.handle for e in msp if e.dxftype() == "MTEXT"]
assert textos and all(h in dibujados for h in textos), "los textos de la tabla se dibujan"

# ================================================================ sin tabla en el portapapeles
log.clear()
real_leer = PT.leer_portapapeles
PT.leer_portapapeles = lambda: ("", "", "")
try:
    herramienta = PT.PegarTablaTool(contexto()); herramienta.start()
finally:
    PT.leer_portapapeles = real_leer
assert "no tiene una tabla" in log[0] and log[-1] == "FIN"
print("TODO OK: tablas (PEGARTABLA)")
