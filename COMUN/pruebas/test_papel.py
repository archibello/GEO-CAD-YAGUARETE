"""3.5.0 Espacio papel como AutoCAD: la presentación respeta la escala de su
configuración de página (1 mm = 0,001 unidades con el dibujo en metros), así
una ventana a 1:100 (1/100XP) muestra una grilla de 100 m en 1000 mm."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin
from core import layouts as L

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
P = import_module("ingecad_plugin_geocad.papel")
M = import_module("ingecad_plugin_geocad.modulos")
P.instalar()

# ------------------------------------------------------------- 1. el módulo
assert any(m.clave == "papel" for m in M.catalogo("ingecad")) and M.activo("ingecad", "papel")
assert hasattr(L.paper_frame, "_puente_original") and hasattr(L.effective_page, "_puente_original")
print("ok módulo")


def dibujo(insunits=6):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    return types.SimpleNamespace(doc=d, dirty=False, uninitialized_layouts=set())   # IngeCAD 0.6.6


def a3_horizontal(doc, layout, escala):
    cmd = L.page_setup_command(layout, 420.0, 297.0, (20.0, 7.5, 20.0, 7.5), "ISO A3",
                               fit_to_paper=False, scale=escala)
    cmd.do(doc)
    return cmd


# ------------------------------------------------------------- 2. la escala de la hoja
doc = dibujo()
lay = doc.doc.layouts.get("Layout1")
assert P.unidades_por_mm(lay) == 1.0                       # IngeCAD de fábrica: 1:1
cmd = a3_horizontal(doc, lay, (1.0, 0.001))
assert abs(P.unidades_por_mm(lay) - 0.001) < 1e-15
# límites del papel en unidades del dibujo (como AutoCAD)
assert abs(lay.dxf.limmax[0] - (420.0 - 7.5) * 0.001) < 1e-12, lay.dxf.limmax
# ajustar al papel: 1 (como IngeCAD)
assert P.unidades_por_mm(lay, {"standard_scale_type": 0}) == 1.0
print("ok escala de la hoja")

# ------------------------------------------------------------- 3. la hoja en metros
f = L.paper_frame(lay)
x0, y0, x1, y1 = f["sheet"]
assert abs((x1 - x0) - 0.420) < 1e-12 and abs((y1 - y0) - 0.297) < 1e-12, f
px0, py0, px1, py1 = f["printable"]
assert abs((px1 - px0) - 0.405) < 1e-12 and abs((py1 - py0) - 0.257) < 1e-12, f
# la configuración de página sigue en mm
pag = L.effective_page(lay)
assert abs(pag["width"] - 420.0) < 1e-9 and abs(pag["height"] - 297.0) < 1e-9, pag
assert all(abs(a - b) < 1e-9 for a, b in zip(pag["margins"], (20.0, 7.5, 20.0, 7.5))), pag
print("ok hoja en metros, página en mm")

# ------------------------------------------------------------- 4. la grilla de 100 m a 1:100
msp = doc.doc.modelspace()
for i in range(101):
    msp.add_line((i, 0), (i, 100)); msp.add_line((0, i), (100, i))
L.viewport_fit_printable(doc, "Layout1").do(doc)
vp = L.visible_viewports(lay)[-1]
L.xp_zoom_command(vp, L.parse_xp_factor("1/100XP")).do(doc)
assert L.scale_label(L.viewport_scale(vp)) == "1:100"
a = L.model_to_paper(vp, 0.0, 0.0); b = L.model_to_paper(vp, 100.0, 0.0)
c = L.model_to_paper(vp, 1.0, 0.0)
mm_por_unidad_papel = 1.0 / P.unidades_por_mm(lay)          # lo que usa la impresión
lado_mm = (b[0] - a[0]) * mm_por_unidad_papel
celda_mm = (c[0] - a[0]) * mm_por_unidad_papel
assert abs(lado_mm - 1000.0) < 1e-6, lado_mm                # 100 m -> 1000 mm
assert abs(celda_mm - 10.0) < 1e-9, celda_mm                # 1 m -> 10 mm
# la ventana cubre el área imprimible: 405 mm de ancho -> 40,5 celdas
assert abs(vp.dxf.width * mm_por_unidad_papel - 405.0) < 1e-6, vp.dxf.width
print("ok grilla 100 m a 1:100 = 1000 mm, celdas de 10 mm")

# ------------------------------------------------------------- 5. presentaciones nuevas
L.NewLayoutCommand("Hoja metros").do(doc)
assert abs(P.unidades_por_mm(doc.doc.layouts.get("Hoja metros")) - 0.001) < 1e-15
doc_mm = dibujo(insunits=4)
L.NewLayoutCommand("Hoja mm").do(doc_mm)
assert P.unidades_por_mm(doc_mm.doc.layouts.get("Hoja mm")) == 1.0    # en mm, como venía
# una escala elegida por el usuario no se pisa
otra = doc.doc.layouts.new("Elegida"); otra.dxf.scale_denominator = 0.002
assert not P.escala_hoja_metros(otra) and otra.dxf.scale_denominator == 0.002
print("ok presentaciones nuevas en metros")

# ------------------------------------------------------------- 6. 1:1 y módulo apagado: como venía
doc2 = dibujo(insunits=4); lay2 = doc2.doc.layouts.get("Layout1")
a3_horizontal(doc2, lay2, (1.0, 1.0))
x0, y0, x1, y1 = L.paper_frame(lay2)["sheet"]
assert abs((x1 - x0) - 420.0) < 1e-9
M.guardar("ingecad", {"papel": False})
assert not P.activo()
x0, y0, x1, y1 = L.paper_frame(lay)["sheet"]
assert abs((x1 - x0) - 420.0) < 1e-9                          # IngeCAD de fábrica
L.NewLayoutCommand("Apagado").do(doc)
assert P.unidades_por_mm(doc.doc.layouts.get("Apagado")) == 1.0
M.guardar("ingecad", {"papel": True})
# instalar dos veces no envuelve dos veces
P.instalar()
assert not hasattr(L.paper_frame._puente_original, "_puente_original")
print("ok 1:1 y apagado")

# ------------------------------------------------------------- 7. escala escrita (3.6.0)
E = P.parse_escala
assert E("1/100") == 0.01 and E("1:100") == 0.01 and E(" 1 : 100 ") == 0.01
assert E("1/100XP") == 0.01 and E("1/100xp") == 0.01
assert E("2:1") == 2.0 and abs(E("1/250") - 0.004) < 1e-15 and abs(E("1:2,5") - 0.4) < 1e-15
assert E("100") == 0.01                                      # «100» = 1:100
for malo in ("", "hola", "1/0", "0:1", "-1:100", "1:-5", "1:", "inf:1"):
    assert E(malo) is None, malo
print("ok escalas escritas")

# Enter en el desplegable, con una ventana de IngeCAD de mentira
ecos, refrescos = [], []
hist = types.SimpleNamespace(execute=lambda c: c.do(doc))
win = types.SimpleNamespace(
    command_line=types.SimpleNamespace(echo=ecos.append),
    _refresh_vp_scale_combo=lambda: refrescos.append(1),
    _scale_target_vp=lambda: vp, _vp_gesture_commit=lambda: None,
    history=hist, regen_in_memory=lambda: None)
assert P.aplicar_escala(win, "1/250")
assert L.scale_label(L.viewport_scale(vp)) == "1:250" and ecos[-1] == "Escala de la ventana: 1:250."
a = L.model_to_paper(vp, 0.0, 0.0); b = L.model_to_paper(vp, 1.0, 0.0)
assert abs((b[0] - a[0]) / P.unidades_por_mm(lay) - 4.0) < 1e-9   # 1 m -> 4 mm
assert P.aplicar_escala(win, "1:100") and L.scale_label(L.viewport_scale(vp)) == "1:100"
# no válida: avisa y no cambia
assert not P.aplicar_escala(win, "1:x") and "no válida" in ecos[-1]
assert L.scale_label(L.viewport_scale(vp)) == "1:100"
# bloqueada: avisa y no cambia
L.SetViewportLockCommand(vp, True).do(doc)
assert L.is_viewport_locked(vp)
assert not P.aplicar_escala(win, "1/500") and "bloqueada" in ecos[-1]
assert L.scale_label(L.viewport_scale(vp)) == "1:100"
# sin ventana elegida
win._scale_target_vp = lambda: None
assert not P.aplicar_escala(win, "1/500") and "MSPACE" in ecos[-1]
print("ok escala escrita aplicada")

# ------------------------------------------------------------- 8. TRAZAR la presentación (3.26.6)
# Fernando: Layout2 A0 VERTICAL a 1:15000 y el PDF salía HORIZONTAL. (1) Con
# IngeCAD 0.6.7 la hoja a 1:1 fallaba en un dibujo en metros: IngeCAD le pasa
# ahora la escala a _use_physical_pens y nuestro envoltorio no la aceptaba.
# (2) En la presentación TRAZAR arrancaba en A4 horizontal: con «Extents»
# salía la hoja vertical en una página horizontal.
import formats
falso = types.ModuleType("formats.pdf_out")
falso.PAPER_SIZES_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0), "A2": (420.0, 594.0),
                        "A1": (594.0, 841.0), "A0": (841.0, 1189.0), "Letter": (215.9, 279.4)}
llamadas = []


class Pluma:
    def __init__(self):
        self.w = 0.25
    def isCosmetic(self):
        return False
    def widthF(self):
        return self.w
    def setWidthF(self, w):
        self.w = w


class Item:
    def __init__(self):
        self.p = Pluma()
    def pen(self):
        return self.p
    def setPen(self, p):
        self.p = p


escena = types.SimpleNamespace(items=lambda: [item])
item = Item()


def plumas_nuevas(scene, mm_per_unit=1.0, lineweights=True):   # IngeCAD 0.6.7
    for it in scene.items():
        it.pen().setWidthF(0.25 / mm_per_unit)


def plot(document, printer, layout_name=None, area=None, mm_per_unit=None,
         physical_pens=True, ctb=None, painter=None, lineweights=True):
    llamadas.append((layout_name, area, mm_per_unit))
    falso._use_physical_pens(escena, mm_per_unit, lineweights)


falso._use_physical_pens = plumas_nuevas
falso.plot = plot
falso.layout_sheet = lambda document, name: P._envolver_layout_sheet(
    lambda d, n: ((0.841, 1.189), (0.0, 0.0, 0.841, 1.189)))(document, name)
sys.modules["formats.pdf_out"] = falso
formats.pdf_out = falso

docA0 = dibujo()
layA0 = docA0.doc.layouts.get("Layout1")
L.page_setup_command(layA0, 841.0, 1189.0, (20.0, 7.5, 20.0, 7.5), "ISO A0",
                     fit_to_paper=False, scale=(1.0, 0.001)).do(docA0)
assert abs(P.unidades_por_mm(layA0) - 0.001) < 1e-15
pagina = L.effective_page(layA0)
assert abs(pagina["width"] - 841.0) < 1e-6 and abs(pagina["height"] - 1189.0) < 1e-6   # en mm
assert falso.layout_sheet(docA0, "Layout1")[0] == (841.0, 1189.0)       # el PDF, vertical
impresora = types.SimpleNamespace(setFullPage=lambda v: None)
P._envolver_plot_layout(lambda *a, **k: None)(docA0, impresora, "Layout1")   # antes: TypeError
assert llamadas[-1][2] == 1000.0 and llamadas[-1][1] == (0.0, 0.0, 0.841, 1.189)
assert abs(item.p.w - 0.00025) < 1e-15                    # 0,25 mm = 0,00025 m, no 1000 veces menos
# IngeCAD anterior (la pluma sin escala): el envoltorio la pasa a unidades
item = Item()
plumas_viejas = lambda scene: None
falso._use_physical_pens = plumas_viejas
falso.plot = lambda *a, **k: falso._use_physical_pens(escena)
P._envolver_plot_layout(lambda *a, **k: None)(docA0, impresora, "Layout1")
assert abs(item.p.w - 0.00025) < 1e-15
print("ok hoja a 1:1 con IngeCAD 0.6.7")

H = P.papel_de_la_hoja
T = list(falso.PAPER_SIZES_MM.values())
assert H(841.0, 1189.0, T) == (4, False) and H(1189.0, 841.0, T) == (4, True)
assert H(420.0, 297.0, T) == (1, True) and H(500.0, 700.0, T) == (None, False)


class Combo:
    def __init__(self, datos):
        self.datos, self.i = datos, 0
    def setCurrentIndex(self, i):
        self.i = i
    def findData(self, d):
        return self.datos.index(d) if d in self.datos else -1
    def currentData(self):
        return self.datos[self.i]


def dialogo(nombre):
    return types.SimpleNamespace(_layout_name=nombre, paper=Combo(list(falso.PAPER_SIZES_MM)),
                                 orientation=Combo([True, False]),
                                 area=Combo(["layout", "extents", "view", "window"]))


ventana = types.SimpleNamespace(document=docA0)
d = dialogo("Layout1")
P.hoja_en_el_trazado(d, ventana)
assert d.paper.currentData() == "A0" and d.orientation.currentData() is False   # A0 vertical
d = dialogo("Layout1")
P.hoja_en_el_trazado(d, ventana, {"area": "layout"})
assert d.paper.currentData() == "A0" and d.orientation.currentData() is False
d = dialogo("Layout1")                           # «Extents» de la vez anterior: la hoja
d.area.i = 1
P.hoja_en_el_trazado(d, ventana, {"area": "extents"})
assert d.area.currentData() == "layout" and d.orientation.currentData() is False
d = dialogo("Layout1")                           # una ventana recién marcada: se respeta
d.area.i = 3
P.hoja_en_el_trazado(d, ventana, {"area": "window", "window": (0, 0, 1, 1)})
assert d.area.currentData() == "window" and d.paper.currentData() == "A4"
d = dialogo("Model")                             # el modelo: lo hace IngeCAD
P.hoja_en_el_trazado(d, ventana)
assert d.paper.currentData() == "A4"
# el diálogo envuelto: apagado el módulo queda como venía
class Dialogo:
    def __init__(self, window, state=None):
        self._layout_name = "Layout1"
        self.paper = Combo(list(falso.PAPER_SIZES_MM))
        self.orientation = Combo([True, False])
        self.area = Combo(["layout", "extents"])
Dialogo.__init__ = P._envolver_print_init(Dialogo.__init__)
assert Dialogo(ventana).orientation.currentData() is False
M.guardar("ingecad", {"papel": False})
assert Dialogo(ventana).orientation.currentData() is True
M.guardar("ingecad", {"papel": True})
del sys.modules["formats.pdf_out"]
print("ok TRAZAR con la hoja de la presentación")

print("TODO OK PAPEL")
