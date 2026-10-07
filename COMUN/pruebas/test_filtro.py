"""3.2.0 FILTRO (FI) estilo FILTER de AutoCAD: condiciones por tipo, capa, color,
medidas, textos y datos de QGIS; grupos Y / O / XO / NO; filtros guardados;
la orden FILTRO y FI dentro de cualquier «Designar objetos»."""
import os, sys, tempfile, types
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
import ezdxf
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from core.xdata import APPID, ensure_appid
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
spec = lp.spec
F = import_module("ingecad_plugin_geocad.filtro")
sel = import_module("ingecad_plugin_geocad.seleccion")
enlace = import_module("ingecad_plugin_geocad.enlace")
hd = import_module("ingecad_plugin_geocad.herramientas_datos")

# ------------------------------------------------------------- 1. registro
assert spec.tools.get("GEOFILTER") is F.FiltroTool and F.FiltroTool is not None
assert spec.aliases.get("FI") == "GEOFILTER" and spec.aliases.get("FILTER") == "GEOFILTER"
assert any(getattr(i, "command", "") == "GEOFILTER" for i in spec.toolbar)
print("ok registro")

# ------------------------------------------------------------- 2. un dibujo
doc = Document(ezdxf.new("R2018"))
d = doc.doc; msp = d.modelspace()
for n in ("A", "B", "X-ROTULOS", "APAGADA"): d.layers.add(n)
d.layers.get("APAGADA").off()
c1 = msp.add_circle((2, 2), 1, dxfattribs={"layer": "A"})
c2 = msp.add_circle((20, 2), 2.5, dxfattribs={"layer": "B", "color": 1})
c3 = msp.add_circle((40, 2), 9, dxfattribs={"layer": "APAGADA"})          # no se puede elegir
ln = msp.add_line((0, 0), (3, 4), dxfattribs={"layer": "A", "color": 1})
pl = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "B"})
ab = msp.add_lwpolyline([(0, 0), (5, 0)], dxfattribs={"layer": "B"})
tx = msp.add_text("0838", dxfattribs={"layer": "X-ROTULOS", "height": 2.5, "insert": (5, 5)})
tx2 = msp.add_text("Calle", dxfattribs={"layer": "A", "height": 1.0, "insert": (50, 5)})
ensure_appid(d); tx.set_xdata(APPID, [(1000, hd.LABEL_TAG), (1000, "SHP-parc"), (1071, 3), (1000, "QGIS")])
fondo = msp.add_circle((5, 5), 3, dxfattribs={"layer": "X-ROTULOS"})
fondo.set_xdata(APPID, [(1000, hd.LABEL_TAG), (1000, "SHP-parc"), (1071, 3), (1000, "QGIS")])
blk = d.blocks.new("GEOCAD-SIMBOLO-STAR"); blk.add_line((0, 0), (1, 1))
sim = msp.add_blockref("GEOCAD-SIMBOLO-STAR", (7, 7), dxfattribs={"layer": "A"})
d.blocks.new("POSTE").add_attdef("NUM", (0, 0))
poste = msp.add_blockref("POSTE", (9, 9), dxfattribs={"layer": "A"}); poste.add_attrib("NUM", "P-12", (9, 9))
enlace.set_feat_tag(pl, "SHP-parc", 3, 0)

todos = F.candidatos(doc)
assert c3 not in todos and c1 in todos and len(todos) == 10, len(todos)

def h(conds, ents=None):
    return {e.dxf.handle for e in F.filtrar(todos if ents is None else ents, conds, doc)}
H = lambda *es: {e.dxf.handle for e in es}                                  # noqa: E731

# tipos y propiedades de un tipo (sólo las cumple ese tipo, como en AutoCAD)
assert h([{"p": "circulo"}]) == H(c1, c2, fondo)
assert h([{"p": "radio_circulo", "op": ">", "v": 2}]) == H(c2, fondo)
assert h([{"p": "radio_circulo", "op": "=", "v": "2,5"}]) == H(c2)        # coma decimal
assert h([{"p": "diametro_circulo", "op": "<=", "v": 2}]) == H(c1)
assert h([{"p": "centro_circulo", "x": ["<", 10], "y": ["*", 0]}]) == H(c1, fondo)
assert h([{"p": "inicio_linea", "x": ["=", 0], "y": ["=", 0]}]) == H(ln)
# capa: comodines, alternativas con coma, distinto
assert h([{"p": "capa", "op": "=", "v": "*-rotulos"}]) == H(tx, fondo)
assert h([{"p": "circulo"}, {"p": "capa", "op": "=", "v": "A,B"}]) == H(c1, c2)
assert h([{"p": "circulo"}, {"p": "capa", "op": "!=", "v": "A"}]) == H(c2, fondo)
# color: número, nombre, PorCapa
assert h([{"p": "color", "op": "=", "v": "1 - Rojo"}]) == H(c2, ln)
assert h([{"p": "circulo"}, {"p": "color", "op": "=", "v": "PorCapa"}]) == H(c1, fondo)
# medidas de GeoCAD: largo y área
assert h([{"p": "largo", "op": "=", "v": 5}]) == H(ln, ab)
assert h([{"p": "area", "op": ">=", "v": 100}]) == H(pl, c3) - H(c3)       # el cuadrado de 10 x 10
assert abs(F.area(pl) - 100) < 1e-6 and abs(F.largo(pl) - 40) < 1e-6
assert h([{"p": "cerrada"}]) == H(pl)
# textos
assert h([{"p": "valor_texto", "op": "=", "v": "08*"}]) == H(tx)
assert h([{"p": "altura_texto", "op": "<", "v": 2}]) == H(tx2)
assert h([{"p": "nombre_bloque", "op": "=", "v": "GEOCAD-*"}]) == H(sim)
assert h([{"p": "valor_atributo", "op": "=", "v": "P-1?"}]) == H(poste)
assert h([{"p": "etiqueta_atributo", "op": "=", "v": "NUM"}]) == H(poste)
# de GeoCAD: rótulos, fondos, símbolos, conexión
assert h([{"p": "rotulo_qgis"}]) == H(tx)
assert h([{"p": "fondo_rotulo"}]) == H(fondo)
assert h([{"p": "simbolo"}]) == H(sim)
assert h([{"p": "conexion", "op": "=", "v": "SHP-parc"}]) == H(pl, tx, fondo)
print("ok propiedades")

# ------------------------------------------------------------- 3. grupos
O = lambda *cs: [{"p": "**O("}, *cs, {"p": "**O)"}]                         # noqa: E731
assert h(O({"p": "linea"}, {"p": "texto"})) == H(ln, tx, tx2)
assert h([{"p": "**NO("}, {"p": "capa", "op": "=", "v": "A"}, {"p": "**NO)"}, {"p": "circulo"}]) == H(c2, fondo)
assert h([{"p": "**XO("}, {"p": "circulo"}, {"p": "capa", "op": "=", "v": "A"}, {"p": "**XO)"}]) \
    == H(c2, fondo, ln, tx2, sim, poste)
anidado = O({"p": "**Y("}, {"p": "circulo"}, {"p": "capa", "op": "=", "v": "B"}, {"p": "**Y)"},
            {"p": "texto"})
assert h(anidado) == H(c2, tx, tx2)
assert F.sangrias(anidado) == [0, 1, 2, 2, 1, 1, 0], F.sangrias(anidado)
assert h([]) == H(*todos)                                                  # lista vacía: todo
for malo, texto in (([{"p": "**O("}, {"p": "linea"}], "falta"),
                    ([{"p": "**Y)"}], "sin su"),
                    ([{"p": "**NO("}, {"p": "linea"}, {"p": "texto"}, {"p": "**NO)"}], "exactamente una"),
                    ([{"p": "**XO("}, {"p": "linea"}, {"p": "**XO)"}], "exactamente dos"),
                    ([{"p": "nada"}], "desconocida")):
    try:
        F.arbol(malo); raise AssertionError(malo)
    except F.FiltroError as exc:
        assert texto in str(exc), exc
print("ok grupos")

# ------------------------------------------------------------- 4. lista, objeto, guardados
assert F.describir({"p": "radio_circulo", "op": ">", "v": 2.5}) == ("Radio de círculo", "> 2.5")
assert F.describir({"p": "color", "op": "=", "v": 1}) == ("Color", "= 1 - Rojo")
assert F.describir({"p": "centro_circulo", "x": ["<", 10], "y": ["*", 0]}) == \
    ("Centro de círculo", "X < 10,  Y *")
assert F.describir({"p": "**O("}) == ("** Comenzar O", "")
desc = F.de_objeto(c2)
assert {"p": "circulo"} in desc and {"p": "capa", "op": "=", "v": "B"} in desc
assert h(desc) == H(c2), desc                                             # describe sólo a ése
assert F.pedido("fi") == "" and F.pedido("'FILTER") == "" and F.pedido("FI Selección rojo") == "Selección rojo"
assert F.pedido("F") is None and F.pedido("FILA") is None
assert F.guardados() == {}
rojos = [{"p": "color", "op": "=", "v": 1}]
F.guardar("Selección rojo", rojos); F.guardar("circulos", [{"p": "circulo"}])
assert F.buscar("selección ROJO") == rojos and set(F.guardados()) == {"Selección rojo", "circulos"}
try:
    F.guardar("roto", [{"p": "**O("}]); raise AssertionError("guardó un filtro roto")
except F.FiltroError:
    pass
assert F.borrar("circulos") and not F.borrar("circulos") and set(F.guardados()) == {"Selección rojo"}
assert (Path(HOME) / ".config" / "geocad" / "filtros.json").exists()
print("ok lista y guardados")

# ------------------------------------------------------------- 5. datos de QGIS
class Campos(F.Campos):                                   # la tabla, sin leer el archivo
    def de(self, e, campo):
        tag = enlace.feat_tag(e)
        fila = {3: {"PROPIETARI": "Pérez Juan", "SUP": 512.5}}.get(tag.fid) if tag else None
        return None if fila is None else fila.get(campo.upper(), F._SIN_CAMPO)
real = F.Campos; F.Campos = Campos
assert h([{"p": "campo_qgis", "campo": "propietari", "op": "=", "v": "pérez*"}]) == H(pl)
assert h([{"p": "campo_qgis", "campo": "SUP", "op": ">", "v": 500}]) == H(pl)
assert h([{"p": "campo_qgis", "campo": "SUP", "op": "<", "v": 500}]) == set()
assert h([{"p": "campo_qgis", "campo": "NOEXISTE", "op": "*", "v": ""}]) == set()
F.Campos = real
print("ok campos de QGIS")

# ------------------------------------------------------------- 6. la orden FILTRO (sin ventana)
log, answers = [], []
class Servicios:
    def __init__(self, seleccion=()):
        self.document = doc; self.selection = set(seleccion); self.pedidos = 0
        self.changed = types.SimpleNamespace(emit=lambda: None)
    def request_selection(self): self.pedidos += 1
def correr(servicios):
    terminado = []
    ctx = ToolContext(execute=lambda c: None, prompt=lambda s: None, echo=log.append,
                      finish=lambda: terminado.append(1),
                      ask_text=lambda p, d="": answers.pop(0) if answers else d,
                      ask_choice=lambda p, items, d="": (lambda a: next((i for i in items if i == a), None))(answers.pop(0) if answers else None),
                      services=servicios)
    t = spec.tools["GEOFILTER"](ctx); t.start(); return t, terminado
s = Servicios(); answers[:] = ["Selección rojo"]
t, fin = correr(s)
assert s.pedidos == 1 and "Enter = todo el dibujo" in t.selection_prompt() and not fin
t.on_selection([])                                                        # Enter: todo el dibujo
assert s.selection == H(c2, ln) and s._geocad_previa == s.selection and fin, (s.selection, log)
assert any("2 de 10 objeto(s) cumplen el filtro" in l for l in log), log
assert F.ultimo() == rojos                                                # queda como «*sin nombre»
# designando con ventana: sólo entre ésos
s = Servicios(); answers[:] = ["Selección rojo"]; t, fin = correr(s)
t.on_selection([c1, c2, c3]); assert s.selection == H(c2), s.selection   # c3: capa apagada
# con objetos ya seleccionados (orden-objeto): se filtran ésos, sin pedir
s = Servicios([c1.dxf.handle, ln.dxf.handle]); answers[:] = ["Selección rojo"]; t, fin = correr(s)
assert s.pedidos == 0 and s.selection == H(ln) and fin
# cancelar
log.clear(); s = Servicios(); answers[:] = [None]; t, fin = correr(s)
assert fin and s.pedidos == 0 and any("cancelado" in l for l in log)
print("ok orden FILTRO")

# ------------------------------------------------------------- 7. FI dentro de «Designar objetos»
class Linea:
    def __init__(self): self.msgs = []
    def echo(self, t): self.msgs.append(t)
class Ctrl:
    def __init__(self):
        self.window = types.SimpleNamespace(document=doc, command_line=Linea())
        self.index = GeometryIndex(doc); self.selection = set(); self._selecting_for = object()
        self._window_anchor = None; self.changed = types.SimpleNamespace(emit=lambda: None)
        self.lastpoint = (0.0, 0.0); self.space_vp = None
    def _with_groups(self, handles): return set(handles)
c = Ctrl()
assert sel.on_text(c, "FI Selección rojo") and c.selection == H(c2, ln), c.selection
msgs = c.window.command_line.msgs
assert any("Filtro: 2 de 10" in m for m in msgs) and "FI" in msgs[-1], msgs
assert sel.on_text(c, "R") and sel.on_text(c, "'FILTER Selección rojo") and c.selection == set()
assert sel.on_text(c, "A") and sel.on_text(c, "FI noexiste") and any("No hay un filtro guardado «noexiste»" in m for m in msgs)
assert sel.on_text(c, "FI") and any("FI <nombre>" in m for m in msgs)   # sin ventana: avisa
assert sel.on_text(c, "U") is True                                      # U deshace lo del filtro
assert sel.opcion("F") == "F"                                           # F sigue siendo «borde»
print("TODO OK FILTRO")
