"""3.85.0 Grilla de hoja (GRILLAHOJA, módulo Papel): grilla milimetrada de la
hoja, como la de referencia de Vectorworks; casi imperceptible, no se imprime,
sólo con la hoja en mm (1 mm = 1 o 0,001 unidades). Si la hoja no está en
mm, el botón la pasa a mm y escala lo de la hoja (un solo U)."""
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
G = import_module("ingecad_plugin_geocad.grilla_hoja")
C = import_module("ingecad_plugin_geocad.config")
M = import_module("ingecad_plugin_geocad.modulos")
P.instalar()
G.instalar()                                     # sin Qt: no hace nada, no falla

# ------------------------------------------------------------- 1. ajustes y orden
assert M.activo("ingecad", "papel")
assert C.get("grilla_hoja") is False and C.get("grilla_hoja_intensidad") == "media"   # 3.85.1
assert G.prendida() is False
spec = import_module("ingecad_plugin_geocad").construir_spec()
assert "GEOSHEETGRID" in spec.commands, "falta la orden"
assert spec.aliases.get("GRILLAHOJA") == "GEOSHEETGRID"
assert any(getattr(t, "command", None) == "GEOSHEETGRID" for t in spec.toolbar)
B = import_module("ingecad_plugin_geocad.barra")
assert B.TEMAS["GEOSHEETGRID"] == "impresion"
# 3.85.1 (Fernando eligió la Media de tres muestras): suave < media < marcada,
# crecen con el paso y ninguna pasa del 65 % (nunca tapa lo dibujado)
assert [k for k, _e in G.ETIQUETAS] == ["suave", "media", "marcada"] and G.DE_FABRICA == "media"
for nivel, (a1, a5, a10) in G.INTENSIDADES.items():
    assert 0 < a1 < a5 < a10 <= 165, (nivel, a1, a5, a10)
# 3.85.2 (Fernando: «cada una con su espesor»; eligió la muestra C)
assert G.INTENSIDADES["media"] == (35, 60, 100) and G.GROSOR == (0.5, 1.0, 1.5)
assert all(a < b for a, b in zip(G.INTENSIDADES["suave"], G.INTENSIDADES["media"]))
assert all(a < b for a, b in zip(G.INTENSIDADES["media"], G.INTENSIDADES["marcada"]))
# lo guardado con la 3.85.0 («muy_suave», «normal») no rompe: vuelve a la de fábrica
G._al_guardar({"grilla_hoja": False, "grilla_hoja_intensidad": "normal"})
assert G.intensidad() == "media"
G._estado["prendida"] = None
print("ok ajustes y orden")


def dibujo(insunits=6):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    return types.SimpleNamespace(doc=d, dirty=False, uninitialized_layouts=set())


def a3(doc, layout, escala):
    L.page_setup_command(layout, 420.0, 297.0, (20.0, 7.5, 20.0, 7.5), "ISO A3",
                         fit_to_paper=False, scale=escala).do(doc)


# ------------------------------------------------------------- 2. ¿la hoja está en mm?
doc = dibujo(6)
lay = doc.doc.layouts.get("Layout1")
assert G.en_mm(lay)                                          # de fábrica: 1:1 en mm
a3(doc, lay, (1.0, 0.001))
assert G.en_mm(lay) and abs(G.mm_por_unidad(lay) - 1000.0) < 1e-6
a3(doc, lay, (1.0, 100.0))                                   # 1 mm = 100 unidades
assert not G.en_mm(lay)
a3(doc, lay, (1.0, 1.0))
lay.dxf.plot_paper_units = 0                                 # en pulgadas
assert not G.en_mm(lay)
assert G.en_mm(None) is False
assert G.mm_destino(dibujo(6)) == 1000.0 and G.mm_destino(dibujo(4)) == 1.0
assert G.mm_destino(dibujo(0)) is None and G.mm_destino(dibujo(1)) is None
print("ok hoja en mm")

# ------------------------------------------------------------- 3. pasar la hoja a mm
doc = dibujo(6)
lay = doc.doc.layouts.get("Layout1")
a3(doc, lay, (1.0, 100.0))                                   # 1 mm = 100 u: no está en mm
if hasattr(L, "ensure_main_viewport"):
    L.ensure_main_viewport(lay)
mm_antes = G.mm_por_unidad(lay)
linea = lay.add_line((10, 20), (110, 70))
texto = lay.add_text("Hola", dxfattribs={"height": 5.0, "insert": (30, 40)})
vp = lay.add_viewport(center=(200, 150), size=(100, 80), view_center_point=(0, 0), view_height=50)
principales = [e for e in lay if e.dxftype() == "VIEWPORT" and int(e.dxf.get("id", 0)) == 1]
objetos = G.objetos_de_la_hoja(lay)
assert linea in objetos and texto in objetos and vp in objetos
assert not any(p in objetos for p in principales)
cmd, factor, objs = G.comando_a_mm(lay, G.mm_destino(doc))
assert abs(factor - mm_antes / 1000.0) < 1e-12, (factor, mm_antes)
largo_mm = 100.0 * mm_antes                                  # largo de la línea en el papel
cmd.do(doc)
assert G.en_mm(lay) and abs(G.mm_por_unidad(lay) - 1000.0) < 1e-6
assert abs(linea.dxf.start.x - 10 * factor) < 1e-12 and abs(linea.dxf.end.y - 70 * factor) < 1e-12
assert abs((linea.dxf.end.x - linea.dxf.start.x) * G.mm_por_unidad(lay) - largo_mm) < 1e-6
assert abs(texto.dxf.height - 5.0 * factor) < 1e-12
assert abs(vp.dxf.width - 100 * factor) < 1e-12 and abs(vp.dxf.center.x - 200 * factor) < 1e-12
assert abs(vp.dxf.view_height - 50) < 1e-12                  # la vista no cambia: escala impresa igual
cmd.undo(doc)
assert not G.en_mm(lay) and abs(G.mm_por_unidad(lay) - mm_antes) < 1e-9
assert abs(linea.dxf.start.x - 10) < 1e-9 and abs(texto.dxf.height - 5.0) < 1e-9
assert abs(vp.dxf.width - 100) < 1e-9
# papel en pulgadas -> mm, sin objetos: sólo la configuración
doc2 = dibujo(4)
lay2 = doc2.doc.layouts.get("Layout1")
lay2.dxf.plot_paper_units = 0
cmd2, factor2, objs2 = G.comando_a_mm(lay2, 1.0)
cmd2.do(doc2)
assert G.en_mm(lay2) and int(lay2.dxf.plot_paper_units) == 1
cmd2.undo(doc2)
assert int(lay2.dxf.plot_paper_units) == 0
print("ok pasar a mm")

# ------------------------------------------------------------- 4. las líneas
A3 = (0.0, 0.0, 420.0, 297.0)
paso, segs = G.lineas(A3, 1.0, A3, 2.0)                      # 2 px/mm: sólo cada 5
assert paso == 5 and len(segs) == 83 + 59, (paso, len(segs))   # sin los bordes
assert {s[4] for s in segs} == {1, 2}
paso, segs = G.lineas(A3, 1.0, A3, 10.0)                     # 10 px/mm: cada 1
assert paso == 1 and len(segs) == 419 + 296
assert [s[4] for s in segs] == sorted(s[4] for s in segs)   # la de 10 mm, última
assert sum(1 for s in segs if s[4] == 2) == 41 + 29
assert sum(1 for s in segs if s[4] == 1) == 42 + 30
paso, segs = G.lineas(A3, 1.0, A3, 0.25)                     # 2,5 px cada 10 mm: nada
assert paso is None and segs == []
paso, segs = G.lineas(A3, 1.0, A3, 0.5)                      # 5 px cada 10 mm: sólo esas
assert paso == 10 and {s[4] for s in segs} == {2}
assert G.lineas(A3, 1.0, A3, 3.0)[0] == 1                    # 3 px por mm: ya las de 1 mm
paso, segs = G.lineas(A3, 1.0, (100.0, 100.0, 150.0, 120.0), 10.0)
assert len(segs) == 51 + 21
vert = [s for s in segs if s[0] == s[2]]
assert all(0.0 < s[1] < 0.3 and 296.7 < s[3] < 297.0 for s in vert)   # toda la hoja, 2 px adentro del borde
assert G.lineas(A3, 1.0, (500.0, 0.0, 600.0, 50.0), 10.0)[1] == []   # fuera de la hoja
# hoja en metros (1 mm = 0,001): las mismas líneas
H = (-0.0075, -0.020, 0.4125, 0.277)
paso, segs = G.lineas(H, 1000.0, H, 10000.0)
assert paso == 1 and len(segs) == 419 + 296
assert abs(segs[0][0] - (H[0] + 0.001)) < 1e-12
assert all(H[0] < s[0] < H[2] for s in segs if s[0] == s[2])   # nunca sobre el borde
print("ok líneas")

# ------------------------------------------------------------- 5. vértices
from render.batches import VERTEX_DTYPE
# cada medida con su grosor: ½ px = 1 px a media opacidad; 1½ px = 1 px + otro a 1 px con la mitad
t = G.trazos([(0, 0, 0, 10, 0), (5, 0, 5, 10, 1), (10, 0, 10, 10, 2), (0, 20, 30, 20, 2)], (35, 60, 100), 4.0)
assert [x[4] for x in t] == [18, 60, 100, 50, 100, 50], t
assert t[3][:4] == (10.25, 0, 10.25, 10) and t[5][:4] == (0, 20.25, 30, 20.25)   # 1 px al lado
# pantalla con escala ×2: ½ px = 1 físico entero, 1 px = 2, 1½ px = 3 (sin huecos)
t2 = G.trazos([(0, 0, 0, 10, 0), (5, 0, 5, 10, 1), (10, 0, 10, 10, 2)], (35, 60, 100), 4.0, dpr=2.0)
assert [x[4] for x in t2] == [35, 60, 60, 100, 100, 100], t2
assert [x[0] for x in t2] == [0, 5, 5.125, 10, 10.125, 10.25]          # a 1 píxel físico
v = G.vertices(t[:3], (0, 0), VERTEX_DTYPE)
# opaco, ya mezclado con la hoja blanca (una línea translúcida transparentaba el lienzo)
assert len(v) == 6 and list(v["rgba"][0]) == list(G.color_sobre_hoja(18)) and v["rgba"][5][3] == 255
assert G.color_sobre_hoja(0) == (255, 255, 255, 255) and G.color_sobre_hoja(255) == G.CELESTE + (255,)
r, g, b, _a = G.color_sobre_hoja(46)
assert r < g < b and b >= 249 and 255 - r <= 34                   # celeste pálido, apenas
assert G.color_sobre_hoja(46, (200, 200, 200))[0] < r        # sobre otra hoja, su color
v = G.vertices([(500010.0, 6200000.0, 500010.0, 6200010.0, 20)], (500000.0, 6200000.0), VERTEX_DTYPE)
assert tuple(v["pos"][0]) == (10.0, 0.0)                     # relativas al origen de la hoja
print("ok vértices")

# ------------------------------------------------------------- 6. el pintado (sin GL)
llamadas = []


class Lienzo:
    def __init__(self):
        self.grid_on = False

    def paintGL(self):
        if self.grid_on:
            self._draw_grid("gl")

    def _draw_grid(self, gl):
        llamadas.append("ingecad")


Lienzo.paintGL = G._envolver_paint(Lienzo.paintGL)
Lienzo._draw_grid = G._envolver_draw_grid(Lienzo._draw_grid)
dibujar, a_dibujar = G.dibujar, G._a_dibujar
G.dibujar = lambda vp, gl, hoja, mm: llamadas.append(("hoja", hoja, mm))
try:
    G._a_dibujar = lambda vp: None
    lz = Lienzo()
    lz.paintGL()
    assert llamadas == []
    lz.grid_on = True
    lz.paintGL()
    assert llamadas == ["ingecad"]
    del llamadas[:]
    G._a_dibujar = lambda vp: (A3, 1.0)
    lz.grid_on = False
    lz.paintGL()
    assert llamadas == [("hoja", A3, 1.0)] and lz.grid_on is False   # la de IngeCAD no
    del llamadas[:]
    lz.grid_on = True
    lz.paintGL()
    assert llamadas == [("hoja", A3, 1.0), "ingecad"] and lz.grid_on is True
finally:
    G.dibujar, G._a_dibujar = dibujar, a_dibujar
print("ok pintado")


# ------------------------------------------------------------- 7. GRILLAHOJA con una ventana falsa
class Ventana:
    def __init__(self, doc, activa):
        self.document = doc
        self._active_layout = activa
        self.ejecutados = []
        self.regen = 0
        self.history = types.SimpleNamespace(execute=self._ejecutar)
        self.tools = types.SimpleNamespace(_execute_command=self._ejecutar)

    def _ejecutar(self, cmd):
        cmd.do(self.document)
        self.ejecutados.append(cmd)

    def regen_in_memory(self):
        self.regen += 1

    def window(self):
        return self


ecos = []
eco = ecos.append
# a) presentación en 1:100 con objetos, dibujo en metros: confirma y la pasa a 0,001
doc = dibujo(6)
lay = doc.doc.layouts.get("Layout1")
a3(doc, lay, (1.0, 100.0))
lay.add_line((0, 0), (100, 0))
w = Ventana(doc, "Layout1")
pedidos = []
assert G.alternar(w, eco, preguntar=lambda win: pedidos.append("?"),
                  confirmar=lambda win, t: pedidos.append(t) or True) is True
assert G.prendida() and G.en_mm(lay) and abs(G.mm_por_unidad(lay) - 1000.0) < 1e-6
assert len(w.ejecutados) == 1 and w.regen == 1
assert len(pedidos) == 1 and "1 mm = 0,001" in pedidos[0]    # no preguntó unidades, sí confirmó
assert C.get("grilla_hoja") is True                          # queda guardado
# lo que ve el lienzo
# (en IngeCAD 0.6.x paper_frame ya lo escala el módulo Papel)
vpf = types.SimpleNamespace(_scene=types.SimpleNamespace(paper=L.paper_frame(lay)), window=lambda: w)
datos = G._a_dibujar(vpf)
assert datos is not None and abs(datos[1] - 1000.0) < 1e-6
hx0, hy0, hx1, hy1 = datos[0]
assert abs((hx1 - hx0) - 0.420) < 1e-9, datos
# U deja la hoja como estaba; la grilla no se ve (no está en mm), sigue prendida
w.ejecutados[0].undo(doc)
vpf._scene.paper = L.paper_frame(lay)                      # IngeCAD regenera la hoja
assert not G.en_mm(lay) and G._a_dibujar(vpf) is None
# b) apagar
assert G.alternar(w, eco) is False and not G.prendida() and G._a_dibujar(vpf) is None
# c) dibujo sin unidades: pregunta; cancelar no toca nada
doc = dibujo(0)
lay = doc.doc.layouts.get("Layout1")
a3(doc, lay, (1.0, 100.0))
w = Ventana(doc, "Layout1")
assert G.alternar(w, eco, preguntar=lambda win: None, confirmar=lambda win, t: True) is False
assert not G.prendida() and not G.en_mm(lay) and w.ejecutados == []
# d) eligiendo milímetros, sin objetos: no pide confirmación
assert G.alternar(w, eco, preguntar=lambda win: 1.0,
                  confirmar=lambda win, t: (_ for _ in ()).throw(AssertionError("no debía confirmar"))) is True
assert G.en_mm(lay) and abs(G.mm_por_unidad(lay) - 1.0) < 1e-9
G.alternar(w, eco)
# e) en Model: sólo se prende
w = Ventana(dibujo(6), "Model")
assert G.alternar(w, eco) is True and w.ejecutados == []
G.alternar(w, eco)
# f) intensidad
G.elegir_intensidad(w, "marcada")
assert G.intensidad() == "marcada" and G.alfas() == G.INTENSIDADES["marcada"]
G.elegir_intensidad(w, "media")
# g) con el módulo Papel apagado no se dibuja
doc = dibujo(6)
w = Ventana(doc, "Layout1")
G.alternar(w, eco)
lay = doc.doc.layouts.get("Layout1")
vpf = types.SimpleNamespace(_scene=types.SimpleNamespace(paper=L.paper_frame(lay)), window=lambda: w)
assert G._a_dibujar(vpf) is not None
estado = M.estado("ingecad")
M.guardar("ingecad", {**estado, "papel": False})
assert G._a_dibujar(vpf) is None
M.guardar("ingecad", estado)
G.alternar(w, eco)
# h) 3.85.3 (Fernando: «no se activa»): la página dice 1 mm = 0,001 pero la
# hoja todavía se ve en mm (presentación nueva de un dibujo en metros): la
# grilla sigue la hoja como se ve
doc = dibujo(6)
lay = doc.doc.layouts.get("Layout1")
a3(doc, lay, (1.0, 0.001))
w = Ventana(doc, "Layout1")
G.guardar(prender=True)
en_mm_vista = {"sheet": (-7.5, -20.0, 412.5, 277.0), "printable": None, "mm_per_unit": 1.0}
vpf = types.SimpleNamespace(_scene=types.SimpleNamespace(paper=en_mm_vista), window=lambda: w)
datos = G._a_dibujar(vpf)
assert datos is not None and datos[1] == 1.0, datos
paso, segs = G.lineas(datos[0], datos[1], datos[0], 2.0)
assert paso == 5 and segs, paso                               # se ve (antes: nada)
# en metros como se ve: 1000
vpf._scene.paper = {"sheet": (-0.0075, -0.02, 0.4125, 0.277), "printable": None, "mm_per_unit": 1000.0}
assert G._a_dibujar(vpf)[1] == 1000.0
# una escena en pulgadas (25,4) o rara: no se dibuja
vpf._scene.paper = {"sheet": (0, 0, 16.5, 11.7), "printable": None, "mm_per_unit": 25.4}
assert G._a_dibujar(vpf) is None
# sin mm_per_unit (IngeCAD 0.6.x): la de la página
vpf._scene.paper = {"sheet": (-0.0075, -0.02, 0.4125, 0.277), "printable": None}
assert abs(G._a_dibujar(vpf)[1] - 1000.0) < 1e-6
assert G.mm_de_la_escena({"mm_per_unit": "x"}) is None and G.mm_de_la_escena({}) is None
G.guardar(prender=False)
print("ok GRILLAHOJA")

print("TODO OK GRILLA DE HOJA")
