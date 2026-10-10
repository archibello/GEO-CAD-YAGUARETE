"""3.9.0 Cotas para el papel: CREAR COTA arma el estilo «Acot-100-6mm» con la
altura en mm de hoja (dibujo en metros), lo deja activo y se deshace con U;
toda cota con un estilo nuestro cae en su capa «COTAS Acot-100-6mm» sin
cambiar la capa actual. (La ventana usa Qt: se prueba aparte, en IngeCAD.)"""
import os, sys, tempfile, types, math
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["HOME"], ".config")
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin
from core import actions
from core import styles as style_ops
from core.commands import History
from core.document import Document

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
C = import_module("ingecad_plugin_geocad.cotas")
M = import_module("ingecad_plugin_geocad.modulos")
G = import_module("ingecad_plugin_geocad")


def cerca(a, b, tol=1e-9):
    return abs(a - b) <= tol


# ------------------------------------------------------------- 1. el módulo, la barra y el menú
assert any(m.clave == "cotas" for m in M.catalogo("ingecad")) and C.activo()
spec = G.construir_spec()
assert "GEODIMSETUP" in spec.commands
barra = [t.command for t in spec.toolbar]
assert ["GEODIMSETUP", "DIMLINEAR", "DIMALIGNED", "DIMANGULAR"] == [c for c in barra if c in
        ("GEODIMSETUP", "DIMLINEAR", "DIMALIGNED", "DIMANGULAR")]
M.guardar("ingecad", {"cotas": False})
spec = G.construir_spec()
assert "GEODIMSETUP" not in spec.commands and not C.activo()
assert "DIMLINEAR" not in [t.command for t in spec.toolbar]
M.guardar("ingecad", {"cotas": True})
print("ok módulo")

# ------------------------------------------------------------- 2. nombres
assert C.nombre_estilo(100, 6, 0) == "Acot-100-6mm"
assert C.nombre_estilo(100, 2.5, 2) == "Acot-100-2.5mm-2d"
assert C.nombre_estilo(75.0, 3.0) == "Acot-75-3mm"
assert C.nombre_capa("Acot-100-6mm") == "COTAS Acot-100-6mm"
assert C.es_nuestro("Acot-100-6mm") and C.es_nuestro("Acot-100-2.5mm-2d")
assert not C.es_nuestro("Acot-100") and not C.es_nuestro("ISO-25") and not C.es_nuestro("")
assert C.leer_nombre("Acot-500-3.5mm-1d") == (500.0, 3.5, 1)
assert ":" not in C.nombre_estilo(100, 6) + C.nombre_capa(C.nombre_estilo(100, 6))
for texto, valor in (("1:100", 100), ("1/100", 100), ("100", 100), (" 1:73,5 ", 73.5)):
    assert C.parse_escala(texto) == valor, texto
for malo in ("", "abc", "1:0", "0", "2:1:3"):
    assert C.parse_escala(malo) is None, malo
print("ok nombres")

# ------------------------------------------------------------- 3. cuentas (metros)
doc = Document(ezdxf.new("R2018")); doc.doc.header["$INSUNITS"] = 6
style_ops.install_default_styles(doc, unit_factor=0.001)
assert cerca(C.unidades_por_mm(doc), 0.001)
a = C.atributos(doc, 100, 6, 0, "oblicuo", "ariblk.ttf")
assert cerca(a["dimscale"], 100) and cerca(a["dimtxt"], 0.006)
assert cerca(a["dimtxt"] * a["dimscale"], 0.6)           # 6 mm a 1:100 = 0,60 m
assert cerca(a["dimasz"], 0.0025) and a["dimdec"] == 0 and a["dimdsep"] == ord(",")
assert a["dimblk1"] == a["dimblk2"] == "ARCHTICK" and a["dimtxsty"] == "Acot-ariblk"
assert C.atributos(doc, 100, 6, 0, "punto", "arial.ttf")["dimblk1"] == "DOT"
assert C.atributos(doc, 100, 6, 0, "flecha", "arial.ttf")["dimblk1"] == ""
d0 = Document(ezdxf.new("R2018")); d0.doc.header["$INSUNITS"] = 0
assert cerca(C.unidades_por_mm(d0), 0.001)                # sin unidad: metros
d4 = Document(ezdxf.new("R2018")); d4.doc.header["$INSUNITS"] = 4
assert cerca(C.unidades_por_mm(d4), 1.0)                  # milímetros
print("ok cuentas")

# ------------------------------------------------------------- 4. CREAR COTA y U
h = History(doc)
estilo_antes = doc.doc.header.get("$DIMSTYLE")
orden, nombre = C.comando_crear(doc, 100, 6, 0, "oblicuo", "ariblk.ttf")
assert nombre == "Acot-100-6mm"
h.execute(orden)
assert doc.doc.header["$DIMSTYLE"] == "Acot-100-6mm"
ds = doc.doc.dimstyles.get("Acot-100-6mm")
assert cerca(ds.dxf.dimtxt, 0.006) and cerca(ds.dxf.dimscale, 100)
assert doc.doc.styles.get("Acot-ariblk").dxf.font == "ariblk.ttf"
capa = doc.doc.layers.get("COTAS Acot-100-6mm")
assert capa.dxf.color == 8 and capa.dxf.lineweight == 15
h.undo()
assert doc.doc.header.get("$DIMSTYLE") == estilo_antes
assert "Acot-100-6mm" not in doc.doc.dimstyles and "Acot-ariblk" not in doc.doc.styles
assert "COTAS Acot-100-6mm" not in doc.doc.layers
h.redo()
assert doc.doc.header["$DIMSTYLE"] == "Acot-100-6mm"
v = C.ultimos(doc)
assert (v["escala"], v["altura"], v["decimales"], v["cabecera"], v["fuente"]) == \
       (100.0, 6.0, 0, "oblicuo", "ariblk.ttf")
print("ok crear")

# ------------------------------------------------------------- 5. las cotas caen en su capa
doc.doc.layers.add("MUROS"); doc.doc.header["$CLAYER"] = "MUROS"
h.execute(actions.dim_linear((0, 0), (10, 0), (5, 4)))
dim = doc.modelspace().query("DIMENSION")[-1]
assert dim.dxf.layer == "COTAS Acot-100-6mm" and dim.dxf.dimstyle == "Acot-100-6mm"
assert doc.doc.header["$CLAYER"] == "MUROS"              # la capa actual no cambia
# volver a CREAR COTA con otra cabecera: actualiza el estilo, no lo duplica
orden, nombre = C.comando_crear(doc, 100, 6, 0, "punto", "ariblk.ttf")
h.execute(orden)
assert doc.doc.dimstyles.get("Acot-100-6mm").dxf.dimblk1 == "DOT"
assert [s.dxf.name for s in doc.doc.dimstyles].count("Acot-100-6mm") == 1
# un estilo que no es nuestro: la cota va a la capa actual
h.execute(style_ops.SetCurrentDimStyleCommand("Acot-100"))
h.execute(actions.dim_linear((0, 0), (10, 0), (5, 8)))
assert doc.modelspace().query("DIMENSION")[-1].dxf.layer == "MUROS"
# otro estilo nuestro: otra capa, creada al acotar
h.execute(C.comando_crear(doc, 500, 3, 1, "flecha", "arial.ttf")[0])
doc.doc.layers.remove("COTAS Acot-500-3mm-1d")
h.execute(actions.dim_linear((0, 0), (10, 0), (5, 12)))
assert doc.modelspace().query("DIMENSION")[-1].dxf.layer == "COTAS Acot-500-3mm-1d"
assert doc.doc.layers.get("COTAS Acot-500-3mm-1d").dxf.color == 8
# la opción Capa de DIM manda
cmd = actions.dim_linear((0, 0), (10, 0), (5, 16)); cmd.layer = "MUROS"
h.execute(cmd)
assert doc.modelspace().query("DIMENSION")[-1].dxf.layer == "MUROS"
# U de una cota: la cota se va
n = len(doc.modelspace().query("DIMENSION")); h.undo()
assert len(doc.modelspace().query("DIMENSION")) == n - 1
# módulo apagado: IngeCAD como venía
M.guardar("ingecad", {"cotas": False})
h.execute(actions.dim_linear((0, 0), (10, 0), (5, 20)))
assert doc.modelspace().query("DIMENSION")[-1].dxf.layer == "MUROS"
M.guardar("ingecad", {"cotas": True})
print("ok capa")

# ------------------------------------------------------------- 6. se guarda y se vuelve a leer
ruta = Path(tempfile.mkdtemp()) / "cotas.dxf"
doc.doc.saveas(ruta)
leido = ezdxf.readfile(ruta)
assert "Acot-100-6mm" in leido.dimstyles and "COTAS Acot-100-6mm" in leido.layers
assert cerca(leido.dimstyles.get("Acot-100-6mm").dxf.dimtxt, 0.006)
print("ok guardar")

# ------------------------------------------------------------- 7. ángulos en g/m/s
a = C.atributos(doc, 100, 6, 0, "oblicuo", "arial.ttf")
assert a["dimaunit"] == 1 and a["dimadec"] == 4 and a["dimdec"] == 0   # longitudes siguen enteras
a = C.atributos(doc, 100, 6, 2, "oblicuo", "arial.ttf", "decimal")
assert a["dimaunit"] == 0 and a["dimadec"] == 2


def texto_cota(dim):
    for e in doc.doc.blocks[dim.dxf.geometry]:
        if e.dxftype() in ("MTEXT", "TEXT"):
            return e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
    return None


h.execute(C.comando_crear(doc, 100, 6, 0, "oblicuo", "arial.ttf")[0])
h.execute(actions.dim_angular((0, 0), (10, 0), (10, 3), (8, 1)))
t = texto_cota(doc.modelspace().query("DIMENSION")[-1])
assert t.replace("\\", "") .startswith("16°41'57"), t       # atan(3/10) = 16°41'57"
h.execute(actions.dim_linear((0, 0), (10.4, 0), (5, 30)))
assert texto_cota(doc.modelspace().query("DIMENSION")[-1]) == "10", "longitud entera"
h.execute(C.comando_crear(doc, 100, 6, 0, "oblicuo", "arial.ttf", "decimal")[0])
assert C.ultimos(doc)["angulos"] == "decimal"
h.execute(C.comando_crear(doc, 100, 6, 0, "oblicuo", "arial.ttf")[0])
assert C.ultimos(doc)["angulos"] == "gms"
print("ok grados minutos segundos")

# ------------------------------------------------------------- 8. DIMANGULAR en vivo
from tools.dimension import DimAngularTool
assert DimAngularTool.preview_command is C._vista_angular
herr = DimAngularTool.__new__(DimAngularTool)
herr.__dict__.update(_mode="vp2", _pending=None, _quadrant=None, _line1=None, _line2=None,
                     _vertex=(0, 0), _p1=(10, 0), _p2=(0, 10), _region_free=True,
                     _text="<>", _text_rotation=None)
assert herr.preview_command((5, 5)) is None                 # todavía no se ubica el arco
herr._mode = "locate"
cmd = herr.preview_command((5, 5))
assert cmd is not None and herr.preview_segments((5, 5)) == []
n = len(doc.modelspace().query("DIMENSION"))
h.execute(cmd)                                              # la vista previa es la cota del clic
assert len(doc.modelspace().query("DIMENSION")) == n + 1
t = texto_cota(cmd.dim); assert t == "90°", t
# dos líneas
herr.__dict__.update(_line1=((0, 0), (10, 0)), _line2=((0, 0), (10, 10)), _vertex=None)
assert herr.preview_command((6, 2)) is not None
herr.__dict__.update(_line2=((0, 5), (10, 5)))              # paralelas
assert herr.preview_command((6, 2)) is None
M.guardar("ingecad", {"cotas": False})
herr.__dict__.update(_line2=((0, 0), (10, 10)))
assert herr.preview_command((6, 2)) is None                 # apagado: como venía
herr._vertex = (0, 0)
assert herr.preview_segments((6, 2)) == [((0, 0), (6, 2))]  # la línea suelta de IngeCAD
M.guardar("ingecad", {"cotas": True})
print("ok angular en vivo")

# ------------------------------------------------------------- 9. DIMANGULAR: lados, centro, interior / exterior
msp = doc.modelspace()
lote = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
l_a = msp.add_line((20, 0), (30, 0)); l_b = msp.add_line((20, 0), (30, 10))      # 45°
curva = msp.add_lwpolyline([(40, 0, 0, 0, 1), (50, 0)], format="xyseb")       # un tramo curvo


class Ctx:
    def __init__(self):
        self.ecos, self.terminado, self.objetos = [], False, {}
        self.document = doc
        self.services = types.SimpleNamespace(pick_entity=lambda q: self.objetos.get(tuple(q)))
    def prompt(self, texto): self.ultimo = texto
    def echo(self, texto): self.ecos.append(texto)
    def execute(self, cmd): h.execute(cmd); self.cmd = cmd
    def finish(self): self.terminado = True


def herramienta():
    t = DimAngularTool.__new__(DimAngularTool); t.ctx = Ctx(); t.start(); return t


def texto(t, cursor):
    return t.resaltado(cursor)["textos"][0][1]


# lote de QGIS (polilínea): dos tramos, interior 90°, exterior 270°
t = herramienta(); t.ctx.objetos = {(5, 0): lote, (0, 5): lote, (6, 1): lote}
assert t.resaltado((6, 1))["cursor"] == [((0.0, 0.0), (10.0, 0.0))]           # el lado bajo el cursor
t.on_point((5, 0)); assert t._mode == "line2"
r = t.resaltado((0, 5))
assert r["pieza_a"] == [((0.0, 0.0), (10.0, 0.0))] and r["puntos"] == [(0.0, 0.0)]  # centro antes del clic
t.on_point((0, 5)); assert t._mode == "locate" and t._vertex == (0.0, 0.0)
r = t.resaltado((3, 3))
assert r["puntos"] == [(0.0, 0.0)] and r["pieza_a"] and r["pieza_b"]
assert texto(t, (3, 3)) == "Interior 90°", texto(t, (3, 3))
assert texto(t, (-3, -3)) == "Exterior 270°", texto(t, (-3, -3))
assert texto(t, (5, -4)) == "Exterior 270°"
cmd = t.preview_command((-3, -3)); h.execute(cmd)
assert texto_cota(cmd.dim) == "270°", texto_cota(cmd.dim)
h.undo()
t.on_point((-3, -3)); assert t.ctx.terminado
assert texto_cota(t.ctx.cmd.dim) == "270°" and t.ctx.cmd.dim.dxf.layer.startswith("COTAS ")
# dos LÍNEAS a 45°: IngeCAD medía 45° también del lado opuesto; ahora 315°
t = herramienta(); t.ctx.objetos = {(25, 0): l_a, (25, 5): l_b}
t.on_point((25, 0)); t.on_point((25, 5))
assert texto(t, (28, 1)) == "Interior 45°"
assert texto(t, (15, -5)) == "Exterior 315°"
cmd = t.preview_command((15, -5)); h.execute(cmd)
assert texto_cota(cmd.dim) == "315°", texto_cota(cmd.dim)
# dos líneas en X (3.15.2): cada lado, la mitad del lado del clic (como EMPALME
# y CHAFLÁN). Antes tomaba la punta más lejana: en una X, siempre el mismo cuadrante
azul = msp.add_line((90, 10), (110, -10)); verde = msp.add_line((90, -10), (110, 10))   # cruce en (100, 0)
for c_azul, c_verde, adentro, afuera in (((95, 5), (105, 5), (100, 3), (100, -3)),     # A, arriba
                                         ((105, -5), (105, 5), (103, 0), (97, 0)),     # B, derecha
                                         ((105, -5), (95, -5), (100, -3), (100, 3)),   # C, abajo
                                         ((95, 5), (95, -5), (97, 0), (103, 0))):      # D, izquierda
    t = herramienta(); t.ctx.objetos = {c_azul: azul, c_verde: verde}
    t.on_point(c_azul); t.on_point(c_verde)
    assert t._vertex == (100.0, 0.0)
    assert texto(t, adentro) == "Interior 90°", (c_azul, c_verde, texto(t, adentro))
    assert texto(t, afuera) == "Exterior 270°", (c_azul, c_verde, texto(t, afuera))
# el centro antes del segundo clic, igual
t = herramienta(); t.ctx.objetos = {(95, 5): azul, (105, 5): verde}
t.on_point((95, 5)); assert t.resaltado((105, 5))["puntos"] == [(100.0, 0.0)]
# extensiones: desde el arco, no desde la punta de la línea
t.on_point((105, 5))
cmd = t.preview_command((100, 3)); h.execute(cmd)
for nombre in ("defpoint2", "defpoint3"):
    q = cmd.dim.dxf.get(nombre)
    assert abs(math.dist((q.x, q.y), (100, 0)) - 3) < 1e-9, (nombre, q)    # en el arco (radio 3)
h.undo()
t.on_point((100, 3)); assert t.ctx.terminado
q = t.ctx.cmd.dim.dxf.defpoint2; assert abs(math.dist((q.x, q.y), (100, 0)) - 3) < 1e-9
h.undo()
# la línea no llega al arco: la extensión sale de su punta, como AutoCAD
t = herramienta(); t.ctx.objetos = {(95, 5): azul, (105, 5): verde}
t.on_point((95, 5)); t.on_point((105, 5))
cmd = t.preview_command((100, 30)); h.execute(cmd)
q = cmd.dim.dxf.defpoint2; assert abs(math.dist((q.x, q.y), (100, 0)) - math.dist((90, 10), (100, 0))) < 1e-9
h.undo()
assert C.lados(((0, 0), (10, 0)), ((0, 0), (0, 10))) == ((0.0, 0.0), (10, 0), (0, 10))   # sin clic: la lejana
# tramo curvo: avisa y no lo toma
t = herramienta(); t.ctx.objetos = {(45, 1): curva}
t.on_point((45, 1)); assert t._mode == "select" and t.ctx.ecos[-1].startswith("Elija un tramo recto")
# modo vértice: referencias y centro a la vista de principio a fin
t = herramienta(); assert t.referencias_extra() == frozenset()      # eligiendo objetos: sin referencias
t.on_enter(); assert t._mode == "vertex" and {"END", "INT"} <= t.referencias_extra()
t.on_point((0, 0)); assert t.resaltado((4, 0))["puntos"] == [(0, 0)]
t.on_point((10, 0)); r = t.resaltado((0, 10)); assert r["puntos"] == [(0, 0)] and r["pieza_a"] == [((0, 0), (10, 0))]
t.on_point((0, 10)); assert texto(t, (-2, -2)) == "Exterior 270°"
# apagado: IngeCAD como venía (sin resaltado, sin referencias extra)
M.guardar("ingecad", {"cotas": False})
assert not any(t.resaltado((-2, -2)).values()) and t.referencias_extra() == frozenset()
M.guardar("ingecad", {"cotas": True})
# la extensión nunca más larga que la altura del texto
for alto in (1.0, 2.5, 6.0):
    at = C.atributos(doc, 100, alto, 2, C.CABECERAS[0][0], "Arial")
    assert at["dimexe"] <= at["dimtxt"] + 1e-12, (alto, at["dimexe"], at["dimtxt"])
print("ok angular interior / exterior")

# ------------------------------------------------------------- 10. precisión de g/m/s como AutoCAD
T = C.texto_gms
assert T(51.842896, 0) == "52°" and T(51.842896, 1) == "52°"
assert T(51.842896, 2) == "51°51'" and T(51.842896, 3) == "51°51'"
assert T(51.842896, 4) == "51°50'34\""
assert T(51.842896, 5) == "51°50'34,4\"" and T(51.842896, 6) == "51°50'34,43\""
assert T(51.842896, 7) == "51°50'34,426\"" and T(51.842896, 8) == "51°50'34,4256\""
assert T(30.0, 6) == "30°" and T(30.0, 4) == "30°" and T(30.0, 2) == "30°"   # enteros: sólo grados
assert T(29.9999999, 4) == "30°" and T(29.99, 2) == "29°59'"  # sin 60"
assert T(30.5, 4) == "30°30'00\"" and T(30.0001, 8) == "30°00'00,3600\"" and T(30.0001, 8, sin_ceros=True) == "30°00'00,36\""
assert T(30.004, 6, sin_ceros=True) == "30°00'14,4\""
assert T(5.0833333, 4) == "5°05'00\""
assert [C.codigo_gms(d) for d in range(9)] == [0, 0, 2, 2, 4, 5, 6, 7, 8]
assert [c for _, c in C.PRECISION_GMS] == [0, 2, 4, 5, 6, 7, 8]
assert C.atributos(doc, 100, 6, 0, "oblicuo", "arial.ttf", "gms", 6)["dimadec"] == 6
# la cota dice lo que dice la lista (ezdxf: 5 sin decimales, 6-8 con ceros de relleno)
for codigo, esperado in ((4, "16°41'57\""), (5, "16°41'57,3\""), (6, "16°41'57,28\""),
                         (2, "16°42'"), (0, "17°")):
    h.execute(C.comando_crear(doc, 100, 6, 0, "oblicuo", "arial.ttf", "gms", codigo)[0])
    assert C.ultimos(doc)["precision_gms"] == codigo
    h.execute(actions.dim_angular((0, 0), (10, 0), (10, 3), (8, 1)))
    t = texto_cota(doc.modelspace().query("DIMENSION")[-1])
    assert t == esperado, (codigo, t)
M.guardar("ingecad", {"cotas": False})                      # apagado: ezdxf como venía
h.execute(C.comando_crear(doc, 100, 6, 0, "oblicuo", "arial.ttf", "gms", 4)[0])
h.execute(actions.dim_angular((0, 0), (10, 0), (10, 3), (8, 1)))
assert texto_cota(doc.modelspace().query("DIMENSION")[-1]) == "16°41'57\""
M.guardar("ingecad", {"cotas": True})
print("ok precisión g/m/s")

print("TODO OK COTAS")
