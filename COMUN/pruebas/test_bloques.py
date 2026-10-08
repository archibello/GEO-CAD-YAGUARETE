"""Bloques de GeoCAD para IngeCAD: BLOQUE con punto base (geometría relativa a
la base, capa actual, redefinir, Centro / abajo-Izquierda, Convertir /
Retener / Borrar) y edición EN EL LUGAR (doble clic): contenido en su sitio,
lo nuevo se suma, Guardar actualiza todas las referencias en un paso que se
deshace, Descartar deja todo como estaba, no se guarda el dibujo a medias."""
import os, sys, tempfile, types, math
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from core import actions
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
B = import_module("ingecad_plugin_geocad.bloques")
dib = import_module("ingecad_plugin_geocad.dibujo")
mods = import_module("ingecad_plugin_geocad.modulos")
assert lp.spec.tools.get("GEOBLOCK") is B.BloqueTool and "GEOREFSAVE" in lp.spec.commands
assert "GEOREFEDIT" in [i.command for i in lp.spec.toolbar]
assert dib.herramienta_para("BLOCK", None, {"GEOBLOCK": 1}) == "GEOBLOCK"


class Services:
    def __init__(self, w): self.w = w; self.index = GeometryIndex(w.document)
    window = property(lambda s: s.w)
    document = property(lambda s: s.w.document)
    def pick_entity(self, point):
        self.index.invalidate()
        h = self.index.pick(point, 1.0)
        return self.index.entity(h) if h else None


class Window:
    """Lo que la edición en el lugar usa de la ventana de IngeCAD."""
    def __init__(self):
        self.document = Document(ezdxf.new("R2018")); self.history = History(self.document)
        self.msgs = []; self.command_line = types.SimpleNamespace(echo=self.msgs.append)
        self.tools = Services(self); self._active_vp = None; self.plugins = None
        self.finished = False
    @property
    def msp(self): return self.document.modelspace()
    def ctx(self):
        return ToolContext(execute=self.history.execute, prompt=self.msgs.append, echo=self.msgs.append,
                           finish=lambda: setattr(self, "finished", True), services=self.tools,
                           undo_last=self.history.undo)
    # los métodos que GeoCAD envuelve
    def on_canvas_double_click(self, wx, wy): self.msgs.append("doble clic nativo")
    def _cmd_undo(self, *a): self.history.undo()
    def _write_document(self, path): self.msgs.append("escrito"); return True
    def maybe_save_changes(self): return True

for nombre, fab in (("on_canvas_double_click", B._envolver_doble_clic), ("_cmd_undo", B._envolver_deshacer),
                    ("_write_document", B._envolver_escribir), ("maybe_save_changes", B._envolver_cerrar)):
    assert dib.envolver(Window, nombre, fab)


def lineas(space):
    return sorted(tuple(round(v, 6) for v in (e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
                  for e in space.query("LINE"))


def bloque(w, ents, nombre, pasos):
    """Sin Qt: base -> nombre por la línea de comandos -> confirmar."""
    t = B.BloqueTool(w.ctx()); t.start(); t.on_selection(ents)
    for p in pasos:
        if isinstance(p, str):
            t.on_enter() if p == "" else t.on_option(p)
        else:
            t.on_point(p)
    return t


# ---- 1. BLOQUE: resaltado -> punto base -> nombre -> confirmar ------------------------------
w = Window()
w.document.doc.layers.add("ARBOLES"); w.document.doc.header["$CLAYER"] = "ARBOLES"
a = w.msp.add_line((10, 10), (14, 10), dxfattribs={"layer": "VEREDA"})
b = w.msp.add_circle((12, 12), 2, dxfattribs={"layer": "VEREDA"})
t = B.BloqueTool(w.ctx()); t.start(); t.on_selection([a, b])
assert t._paso == "base" and "punto base" in w.msgs[-1]                 # primero el punto base
r = t.resaltado((12, 12))
assert len(r["elegido"]) > 10 and ((10, 10), (14, 10)) in r["elegido"]   # los objetos, iluminados
assert r["puntos"] == [(12, 12)] and r["textos"] == [((12, 12), "punto base")]
assert t.referencias_extra() >= {"END", "CEN", "INT"} and t.REFERENCIAS_SIEMPRE
t.on_point((12, 12)); assert t._paso == "nombre" and t.wants_raw_text()   # sin ventana: por texto
assert t.resaltado((0, 0))["elegido"] == []
t.on_option("ARBOL"); assert t._paso == "confirmar" and "¿Crear el bloque?" in w.msgs[-1]
t.on_enter(); assert w.finished                                           # Enter = Sí
blk = w.document.doc.blocks.get("ARBOL")
assert sorted(e.dxftype() for e in blk) == ["CIRCLE", "LINE"]
(l,) = blk.query("LINE"); (c,) = blk.query("CIRCLE")
assert (l.dxf.start.x, l.dxf.start.y, c.dxf.center.x, c.dxf.center.y) == (-2, -2, 0, 0)   # relativo a la base
assert l.dxf.layer == "VEREDA"
(ins,) = w.msp.query("INSERT")
assert (ins.dxf.insert.x, ins.dxf.insert.y, ins.dxf.layer) == (12, 12, "ARBOLES")
w.history.undo()
assert "ARBOL" not in w.document.doc.blocks and lineas(w.msp) == [(10, 10, 14, 10)] and not w.msp.query("INSERT")
print("ok BLOQUE: resaltado, base, nombre, confirmar")

# ---- 2. con la ventana: vista previa relativa a la base, validación en vivo, Cancelar ---------
ui = import_module("ingecad_plugin_geocad.bloques_ui")
real_crear = ui.crear
visto = {}
def ventana(parent, segs, nombres, cantidad, modo, validar, **k):
    visto.update(segs=segs, nombres=nombres, cantidad=cantidad, modo=modo,
                 malo=validar("a/b"), vacio=validar(""), ok=validar("NUEVO"))
    return visto.get("respuesta")
ui.crear = ventana
w = Window(); w.document.doc.blocks.new("VIEJO")
a = w.msp.add_line((10, 10), (14, 10))
visto["respuesta"] = None
t = B.BloqueTool(w.ctx()); t.start(); t.on_selection([a]); t.on_point((10, 10))
assert visto["segs"] == [((0, 0), (4, 0))] and visto["cantidad"] == 1 and visto["nombres"] == ["VIEJO"]
assert "no válido" in visto["malo"] and visto["vacio"] and visto["ok"] is None
assert t._paso == "base" and not w.msp.query("INSERT")                     # Cancelar: otra base
assert t.validar("VIEJO").startswith("~") and "REDEFINIR" in t.validar("VIEJO")
visto["respuesta"] = {"nombre": "NUEVO", "modo": "R"}
t.on_option("I")                                                            # abajo-Izquierda
assert "NUEVO" in w.document.doc.blocks and lineas(w.msp) == [(10, 10, 14, 10)] and B.BloqueTool.modo == "R"
B.BloqueTool.modo = "C"
ui.crear = real_crear
print("ok ventana de confirmación")

# ---- 3. Centro, Retener/Borrar en la confirmación, redefinir, ? y nombres malos -----------------
w2 = Window(); a = w2.msp.add_line((0, 0), (10, 4))
t = bloque(w2, [a], "X", ["C", "?"]); assert any("Bloques: (ninguno)" in m for m in w2.msgs)
t.on_option("mal/nombre"); assert any("no válido" in m for m in w2.msgs) and t._paso == "nombre"
t.on_option("con espacios"); t.on_option("S")
(ins,) = w2.msp.query("INSERT"); assert (ins.dxf.insert.x, ins.dxf.insert.y) == (5, 2)
w = Window(); a = w.msp.add_line((0, 0), (2, 0))
bloque(w, [a], "R", [(0, 0), "R", "R", "S"])
assert lineas(w.msp) == [(0, 0, 2, 0)] and not w.msp.query("INSERT") and "R" in w.document.doc.blocks
w = Window(); a = w.msp.add_line((0, 0), (2, 0))
bloque(w, [a], "S", [(0, 0), "S", "B", "S"]); assert not w.msp.query("LINE") and not w.msp.query("INSERT")
B.BloqueTool.modo = "C"
w = Window(); a = w.msp.add_line((0, 0), (2, 0))
bloque(w, [a], "P", [(0, 0), "P", "S"])
w.msp.add_blockref("P", (50, 50))
nuevo = w.msp.add_circle((0, 0), 1)
t = bloque(w, [nuevo], "P", [(0, 0), "P"]); assert t._paso == "redefinir"
t.on_option("S"); t.on_option("S")
assert [e.dxftype() for e in w.document.doc.blocks.get("P")] == ["CIRCLE"]
w.history.undo(); assert [e.dxftype() for e in w.document.doc.blocks.get("P")] == ["LINE"]
w.history.redo()
ref = w.msp.query("INSERT")[0]
t = bloque(w, [ref], "P", [(0, 0), "P"]); assert t._paso == "nombre" and any("a sí mismo" in m for m in w.msgs)
w4 = Window(); a = w4.msp.add_line((0, 0), (1, 1)); t = bloque(w4, [a], "Z", [(0, 0), ""])
assert w4.finished and "Z" not in w4.document.doc.blocks
print("ok opciones, redefinir, nombres")

# ---- 3b. INSERT: vista previa, fantasma en el cursor, referencias, escala y rotación ------------
w = Window()
blk = w.document.doc.blocks.new("MESA"); blk.add_line((0, 0), (2, 0)); blk.add_circle((0, 0), 1)
w.document.doc.layers.add("MUEBLES"); w.document.doc.header["$CLAYER"] = "MUEBLES"
pedido = {}
def ventana_ins(parent, nombres, segs_de, escala, rotacion, actual=None, **k):
    pedido.update(nombres=nombres, segs=segs_de("MESA"))
    return {"nombre": "MESA", "escala": 2.0, "rotacion": 90.0}
ui.insertar = ventana_ins
t = B.InsertarTool(w.ctx()); t.start()
assert pedido["nombres"] == ["MESA"] and ((0, 0), (2, 0)) in pedido["segs"]
assert t.referencias_extra() >= {"END", "MID", "CEN", "INT", "INS", "NOD"} and t.REFERENCIAS_SIEMPRE
f = t.resaltado((10, 10))["fantasma"]
assert ((10, 10), (10, 14)) in [(tuple(round(c, 6) for c in a), tuple(round(c, 6) for c in b)) for a, b in f]  # x2, girado 90°
t.on_option("E"); assert t.referencias_extra() == frozenset(); t.on_option("1")
t.on_option("R"); t.on_option("0")
t.on_point((5, 5))
(ins,) = w.msp.query("INSERT")
assert (ins.dxf.name, ins.dxf.insert.x, ins.dxf.insert.y, ins.dxf.xscale, ins.dxf.rotation, ins.dxf.layer) == \
    ("MESA", 5, 5, 1, 0, "MUEBLES") and w.finished
w.history.undo(); assert not w.msp.query("INSERT")
ui.insertar = lambda *a, **k: None
t = B.InsertarTool(w.ctx()); w.finished = False; t.start(); assert w.finished          # Cancelar
ui.insertar = lambda *a, **k: ui.SIN_QT
w.ctx_choice = None
c = w.ctx(); c.ask_choice = lambda p, items, d: "MESA"
t = B.InsertarTool(c); t.start(); assert t._nombre == "MESA"                               # sin ventana
assert dib.herramienta_para("INSERT", None, {"GEOINSERT": 1}) == "GEOINSERT"
w5 = Window(); c5 = w5.ctx(); t = B.InsertarTool(c5); t.start()
assert any("No hay bloques" in m for m in w5.msgs)
print("ok INSERT")

# ---- 4. edición en el lugar: doble clic, contenido en su sitio --------------------------------
w = Window()
blk = w.document.doc.blocks.new("CASA", base_point=(0, 0, 0))
blk.add_line((0, 0), (4, 0)); blk.add_line((4, 0), (4, 3))
r1 = w.msp.add_blockref("CASA", (100, 100), dxfattribs={"rotation": 90})
r2 = w.msp.add_blockref("CASA", (200, 0))
w.history.execute(actions.AddEntityCommand("LINE", lambda m: m.add_line((-50, -50), (-40, -50))))
antes = len(w.history._undo)
w.on_canvas_double_click(100, 102)                                  # sobre la primera línea, girada
s = B.sesion(w); assert s is not None and "doble clic nativo" not in w.msgs
assert (100.0, 100.0, 100.0, 104.0) in lineas(w.msp)               # en su lugar (girado 90°)
assert r1.dxf.handle not in {e.dxf.handle for e in w.msp}          # la referencia se oculta
assert any("sus 2 referencias" in m for m in w.msgs)
# el deshacer no cruza el comienzo de la edición
w._cmd_undo(); assert len(w.history._undo) == antes and any("Nada para deshacer" in m for m in w.msgs)
# no se guarda el dibujo a medio editar
assert w._write_document("x.dxf") is False and "escrito" not in w.msgs
print("ok abrir en el lugar")

# ---- 5. se edita con las herramientas de siempre y se guarda: todas las referencias ----------
(l1,) = [e for e in w.msp.query("LINE") if round(e.dxf.end.y, 6) == 104 and round(e.dxf.end.x, 6) == 100]
w.history.execute(actions.ReplaceEntitiesCommand("TRIM", [l1],
                  [lambda m: m.add_line((100, 100), (100, 102))]))   # se acorta un objeto del bloque
w.history.execute(actions.AddEntityCommand("CIRCLE", lambda m: m.add_circle((99, 101), 0.5)))   # uno nuevo
w._cmd_undo(); w.history.redo()                                     # dentro de la sesión, el deshacer anda
s.guardar()
assert B.sesion(w) is None
blk = w.document.doc.blocks.get("CASA")
geo = sorted((e.dxftype(),) + tuple(round(v, 6) for v in (
    (e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y) if e.dxftype() == "LINE"
    else (e.dxf.center.x, e.dxf.center.y, e.dxf.radius, 0))) for e in blk)
assert geo == [("CIRCLE", 1, 1, 0.5, 0), ("LINE", 0, 0, 2, 0), ("LINE", 4, 0, 4, 3)], geo   # de vuelta a la base
assert lineas(w.msp) == [(-50, -50, -40, -50)] and len(w.msp.query("INSERT")) == 2
assert not w.msp.query("CIRCLE")
assert len(w.history._undo) == antes + 1                            # un solo paso: «REFEDIT»
w.history.undo(); assert sorted(e.dxftype() for e in blk) == ["LINE", "LINE"] and \
    lineas(blk) == [(0, 0, 4, 0), (4, 0, 4, 3)]
w.history.redo(); assert len(list(blk)) == 3
assert w._write_document("x.dxf") is True
print("ok guardar")

# ---- 6. descartar: todo como estaba ---------------------------------------------------------
w = Window()
blk = w.document.doc.blocks.new("POSTE"); blk.add_circle((0, 0), 1)
ref = w.msp.add_blockref("POSTE", (10, 10))
s = B.EdicionEnSitio.abrir(w, ref)
(cc,) = w.msp.query("CIRCLE")
w.history.execute(actions.DeleteEntitiesCommand([cc]) if hasattr(actions, "DeleteEntitiesCommand")
                  else actions.ReplaceEntitiesCommand("ERASE", [cc], []))
w.history.execute(actions.AddEntityCommand("LINE", lambda m: m.add_line((0, 0), (1, 1))))
s.descartar()
assert B.sesion(w) is None and not w.msp.query("CIRCLE") and not w.msp.query("LINE")
assert [e.dxftype() for e in w.msp] == ["INSERT"] and [e.dxftype() for e in blk] == ["CIRCLE"]
assert not w.history._redo
print("ok descartar")

# ---- 7. sumar / dejar fuera; cerrar el dibujo descarta; casos que no se abren ---------------
w = Window()
blk = w.document.doc.blocks.new("K"); blk.add_line((0, 0), (1, 0))
ref = w.msp.add_blockref("K", (0, 0))
suelta = w.msp.add_line((5, 5), (6, 5))
s = B.EdicionEnSitio.abrir(w, ref)
w.history.execute(actions.AddEntityCommand("LINE", lambda m: m.add_line((0, 1), (1, 1))))
nueva = [e for e in w.msp.query("LINE") if e.dxf.start.y == 1][0]
assert s.agregar([suelta]) == 1 and s.quitar([nueva]) == 1
s.guardar()
assert lineas(w.document.doc.blocks.get("K")) == [(0, 0, 1, 0), (5, 5, 6, 5)]
assert lineas(w.msp) == [(0, 1, 1, 1)]                                # lo dejado fuera queda en el dibujo
s = B.EdicionEnSitio.abrir(w, w.msp.query("INSERT")[0])
assert isinstance(B.EdicionEnSitio.abrir(w, w.msp.query("INSERT")[0] if w.msp.query("INSERT") else ref), str)
w.maybe_save_changes(); assert B.sesion(w) is None and len(w.msp.query("INSERT")) == 1
nu = w.msp.add_blockref("K", (0, 0), dxfattribs={"xscale": 1, "yscale": 2})
assert "escala distinta" in B.EdicionEnSitio.abrir(w, nu)
assert isinstance(B.EdicionEnSitio.abrir(w, suelta), str)
# un bloque con atributos: el doble clic sigue abriendo el editor de atributos
w.msgs.clear()
blk = w.document.doc.blocks.new("ATR"); blk.add_attdef("N", (0, 0)); blk.add_line((0, 0), (3, 0))
ra = w.msp.add_blockref("ATR", (300, 0)); ra.add_auto_attribs({"N": "1"})
w.on_canvas_double_click(301, 0); assert "doble clic nativo" in w.msgs and B.sesion(w) is None
# módulo apagado: doble clic nativo
mods.poner("ingecad", "bloques", False); w.msgs.clear()
w.on_canvas_double_click(0.5, 0); assert "doble clic nativo" in w.msgs and B.sesion(w) is None
mods.poner("ingecad", "bloques", True)
print("ok conjunto, cierre y casos")

# ---- 8. las referencias se suman aunque estén apagadas (F3), salvo una de una vez ---------------
class Ctl:
    osnap_on = False; osnap_override = None; osnap_modes = set()
    def snap_kinds(self): return self.osnap_override if self.osnap_override is not None else (
        frozenset(self.osnap_modes) if self.osnap_on else frozenset())
assert dib.envolver(Ctl, "snap_kinds", dib._envolver_snap_kinds)
w = Window(); a = w.msp.add_line((0, 0), (1, 1))
t = B.BloqueTool(w.ctx()); t.start(); t.on_selection([a])
c = Ctl(); c.tool = t
assert c.snap_kinds() >= {"END", "CEN", "INT"}
c.osnap_override = frozenset({"PER"}); assert c.snap_kinds() == {"PER"}
print("ok referencias")

# ---- 9. PUNTOBASEBLOQUE: volver a elegir el punto base de un bloque ya creado ------------------
assert lp.spec.tools.get("GEOBLOCKBASE") is B.PuntoBaseTool
assert "GEOBLOCKBASE" in [i.command for i in lp.spec.toolbar]               # en la barra GeoCAD


def huella(space):
    """Lo que se VE: cada referencia desarmada en el dibujo (anidadas también) y sus atributos."""
    out = []

    def bajar(e):
        if e.dxftype() == "INSERT":
            out.extend(("ATTRIB", tuple(round(c, 6) for c in a.ocs().to_wcs(a.dxf.insert))) for a in e.attribs)
            for v in e.virtual_entities():
                bajar(v)
        elif e.dxftype() == "LINE":
            out.append(("LINE",) + tuple(round(c, 6) for c in (*e.dxf.start, *e.dxf.end)))
        elif e.dxftype() in ("CIRCLE", "ELLIPSE"):
            c = e.dxf.center if e.dxftype() == "ELLIPSE" else e.ocs().to_wcs(e.dxf.center)
            out.append((e.dxftype(),) + tuple(round(v, 6) for v in c))
    for e in space:
        bajar(e)
    return sorted(out)


def poste(w):
    """POSTE: línea + círculo + atributo; referencias girada, simétrica, con escala X≠Y,
    anidada en otro bloque y en una presentación."""
    blk = w.document.doc.blocks.new("POSTE")
    blk.add_line((-1, 0), (3, 2)); blk.add_circle((3, 2), 0.5)
    blk.add_attdef("NUM", (3, 3), dxfattribs={"height": 0.2})
    refs = []
    for p, sx, sy, rot in (((10, 10), 1, 1, 0), ((50, -20), 2, 2, 37), ((-5, 40), -1.5, 1.5, 210),
                           ((7, 70), 1, 3, 90)):
        r = w.msp.add_blockref("POSTE", p, dxfattribs={"xscale": sx, "yscale": sy, "rotation": rot})
        r.add_auto_attribs({"NUM": "P"}); refs.append(r)
    padre = w.document.doc.blocks.new("LINEA")
    padre.add_blockref("POSTE", (0, 0)); padre.add_blockref("POSTE", (20, 0), dxfattribs={"rotation": 15})
    w.msp.add_blockref("LINEA", (100, 100), dxfattribs={"rotation": 30, "xscale": 0.5, "yscale": 0.5})
    w.document.doc.layout("Layout1").add_blockref("POSTE", (3, 4), dxfattribs={"rotation": 45})
    return refs


def en_dibujo(ref, x, y):
    return tuple(ref.matrix44().transform((x, y, 0)))[:2]


# Mantener (por defecto): el dibujo no cambia; el clic pasa a ser el punto de inserción
w = Window(); refs = poste(w)
papel = w.document.doc.layout("Layout1")
antes, antes_papel, pasos = huella(w.msp), huella(papel), len(w.history._undo)
t = B.PuntoBaseTool(w.ctx()); t.start()
assert t.entity_picker and "Designe la referencia" in w.msgs[-1]
t.on_point((0, -100)); assert t._paso == "referencia" and "no es una referencia" in w.msgs[-1]
t.on_point(en_dibujo(refs[1], 1, 1))                                     # sobre la línea de la 2.ª
assert t._paso == "punto" and not t.entity_picker and "nuevo punto base de «POSTE»" in w.msgs[-1]
assert t.referencias_extra() >= {"END", "MID", "CEN", "INT", "INS"} and t.REFERENCIAS_SIEMPRE
r = t.resaltado((1, 2)); assert len(r["elegido"]) > 10 and r["textos"] == [((1, 2), "nuevo punto base")]
clic = en_dibujo(refs[1], 3, 2)                                          # el centro del círculo
t.on_point(clic)
assert t._paso == "modo" and "tiene 7 referencia(s)" in w.msgs[-1] and "<Mantener>" in w.msgs[-1]
assert t.referencias_extra() == frozenset()
t.on_enter()                                                              # Enter = Mantener
assert w.finished and "7 referencia(s) quedan en su lugar" in w.msgs[-1]
assert huella(w.msp) == antes and huella(papel) == antes_papel           # nada se movió
assert tuple(round(v, 6) for v in refs[1].dxf.insert)[:2] == tuple(round(v, 6) for v in clic)
blk = w.document.doc.blocks.get("POSTE")
(c,) = blk.query("CIRCLE"); assert (round(c.dxf.center.x, 9), round(c.dxf.center.y, 9)) == (0, 0)
(l,) = blk.query("LINE"); assert (round(l.dxf.start.x, 9), round(l.dxf.start.y, 9)) == (-4, -2)
assert len(w.history._undo) == pasos + 1                                  # un paso
w.history.undo()
assert huella(w.msp) == antes and (c.dxf.center.x, c.dxf.center.y) == (3, 2)
assert tuple(refs[1].dxf.insert)[:2] == (50, -20)
w.history.redo(); assert huella(w.msp) == antes and c.dxf.center.isclose((0, 0, 0), abs_tol=1e-9)
print("ok punto base: Mantener (girada, simétrica, X≠Y, anidadas, presentación, deshacer)")

# bloque nativo de IngeCAD (base en coordenadas del dibujo): lo mismo
w = Window()
blk = w.document.doc.blocks.new("NATIVO", base_point=(5000, 7000, 0))
blk.add_line((5000, 7000), (5004, 7003))
ref = w.msp.add_blockref("NATIVO", (10, 10), dxfattribs={"rotation": 90})
antes = huella(w.msp)
t = B.PuntoBaseTool(w.ctx()); t.start(); t.on_point(en_dibujo(ref, 5002, 7001.5))
t.on_point(en_dibujo(ref, 5004, 7003)); t.on_option("M")
assert huella(w.msp) == antes and tuple(blk.block.dxf.base_point) == (5000, 7000, 0)
(l,) = blk.query("LINE"); assert tuple(l.dxf.end)[:2] == (5000, 7000)    # el extremo cae en la base
print("ok punto base: bloque nativo")

# Desplazar: las referencias quedan; el bloque (y sus atributos) se corre
w = Window(); refs = poste(w)
ins = [tuple(r.dxf.insert) for r in refs]
t = B.PuntoBaseTool(w.ctx()); t.start(); t.on_point(en_dibujo(refs[0], 1, 1))
t.on_point(en_dibujo(refs[0], 3, 2)); t.on_option("D")
assert B.PuntoBaseTool.mantener is False and "se desplazan" in w.msgs[-1]
for r, p in zip(refs, ins):
    assert tuple(r.dxf.insert) == p
    (cc,) = [v for v in r.virtual_entities() if v.dxftype() in ("CIRCLE", "ELLIPSE")]
    centro = cc.dxf.center if cc.dxftype() == "ELLIPSE" else cc.ocs().to_wcs(cc.dxf.center)
    assert centro.isclose(p, abs_tol=1e-9)                                # el círculo, en la inserción
    (a,) = r.attribs
    assert a.ocs().to_wcs(a.dxf.insert).isclose(r.matrix44().transform((0, 1, 0)), abs_tol=1e-6)
t = B.PuntoBaseTool(w.ctx()); t.start(); t.on_point(en_dibujo(refs[0], 1, 1)); t.on_point((0, 0))
assert "<Desplazar>" in w.msgs[-1]                                        # recuerda la elección
t.on_option("x"); assert "Responda M" in w.msgs[-1] and t._paso == "modo"
t.on_option("M"); B.PuntoBaseTool.mantener = True
print("ok punto base: Desplazar")

# dentro de la edición en el lugar: se anota y se aplica al guardar, en un solo paso
w = Window(); refs = poste(w)
antes, pasos = huella(w.msp), len(w.history._undo)
s = B.EdicionEnSitio.abrir(w, refs[1]); assert s is B.sesion(w)
t = B.PuntoBaseTool(w.ctx()); t.start()
assert t._paso == "punto" and not t.entity_picker                         # no pide la referencia
t.on_point(en_dibujo(refs[1], 3, 2)); assert "tiene 7 referencia(s)" in w.msgs[-1]
t.on_enter(); assert "se aplica al GUARDARBLOQUE" in w.msgs[-1]
assert tuple(w.document.doc.blocks.get("POSTE").query("CIRCLE")[0].dxf.center)[:2] == (3, 2)   # todavía no
s.guardar()
assert "punto base nuevo" in w.msgs[-1] and len(w.history._undo) == pasos + 1
assert huella(w.msp) == antes
assert tuple(round(v, 9) for v in w.document.doc.blocks.get("POSTE").query("CIRCLE")[0].dxf.center)[:2] == (0, 0)
w.history.undo(); assert huella(w.msp) == antes
assert tuple(w.document.doc.blocks.get("POSTE").query("CIRCLE")[0].dxf.center)[:2] == (3, 2)
# descartar también descarta el punto base anotado
s = B.EdicionEnSitio.abrir(w, refs[0]); s.nueva_base = (999, 999); s.descartar()
assert tuple(w.document.doc.blocks.get("POSTE").query("CIRCLE")[0].dxf.center)[:2] == (3, 2)
print("ok punto base: en la edición en el lugar")
# ------------------------------------------------ 10. referencias sobre bloques (2.8.1)
from core.snap import SnapEngine
from core.document import Document as _Doc
d10 = _Doc(ezdxf.new("R2018")); m10 = d10.doc.modelspace()
mesa = d10.doc.blocks.new("MESA")
mesa.add_line((0, 0), (4, 0)); mesa.add_circle((2, 2), 1)
caja = d10.doc.blocks.new("CAJA")                       # bloque anidado: CAJA lleva una MESA
caja.add_line((0, 0), (0, 3)); caja.add_blockref("MESA", (10, 0))
m10.add_blockref("MESA", (100, 100), dxfattribs={"rotation": 90, "xscale": 2, "yscale": 2})
m10.add_blockref("MESA", (200, 0), dxfattribs={"xscale": -1})          # espejada
m10.add_blockref("CAJA", (300, 0))
nat = d10.doc.blocks.new("NATIVO", base_point=(50, 50))   # bloque nativo: base en coordenadas del dibujo
nat.add_line((50, 50), (53, 50))
m10.add_blockref("NATIVO", (400, 0), dxfattribs={"rotation": 180})
m10.add_blockref("MESA", (500, 0), dxfattribs={"xscale": 1, "yscale": 3})   # X distinta de Y: camino lento
m10.add_line((90, 104), (110, 104))                      # corta la línea de la mesa girada en (100,104)
eng = SnapEngine(d10)
def ref(x, y, kinds=None):
    h = eng.find((x, y), 0.5, frozenset(kinds) if kinds else frozenset({"END", "MID", "CEN", "INT", "QUA", "INS"}))
    return None if h is None else (h.kind, round(h.x, 6), round(h.y, 6))
assert ref(100, 100.2, {"INS"}) == ("INS", 100, 100)                                 # la inserción, como antes
assert ref(100.1, 108.1) == ("END", 100, 108), ref(100.1, 108.1)                       # final, girado y escalado
assert ref(100.1, 104.1, {"MID"}) == ("MID", 100, 104), ref(100.1, 104.1, {"MID"})     # medio
assert ref(100.1, 104.0, {"INT"}) == ("INT", 100, 104)                                  # bloque x línea suelta
assert ref(96.1, 104.0, {"CEN"}) == ("CEN", 96, 104), ref(96.1, 104.0, {"CEN"})        # centro del círculo
assert ref(195.9, 0.1) == ("END", 196, 0)                                               # espejada
assert ref(310.1, 0.1, {"END"}) == ("END", 310, 0) and ref(314, 0.1, {"END"}) == ("END", 314, 0)   # anidado
assert ref(300, 2.9, {"END"}) == ("END", 300, 3)
assert ref(300.1, 0.1, {"INS"}) == ("INS", 300, 0)                                      # la inserción sigue
assert ref(397.1, 0.1, {"END"}) == ("END", 397, 0), ref(397.1, 0.1, {"END"})              # nativo girado 180
assert ref(504, 0.1, {"END"}) == ("END", 504, 0) and ref(502, 2.9, {"QUA"}) == ("QUA", 502, 3)   # escala 1 x 3
# editar el contenido del bloque (mismo número de objetos): al rearmar, la referencia nueva
d10.doc.blocks.get("NATIVO").query("LINE")[0].dxf.end = (55, 50)
eng.invalidate(); assert ref(395.1, 0.1, {"END"}) == ("END", 395, 0)
# todo queda a nombre del bloque: borrarlo se lleva sus referencias
h = [e for e in m10 if e.dxftype() == "INSERT"][0].dxf.handle
eng.remove_handles([h]); assert ref(100.1, 108.1, {"END"}) is None
# un bloque enorme: sólo el punto de inserción, como venía
B.MAX_OBJETOS_REFERENCIAS, viejo = 1, B.MAX_OBJETOS_REFERENCIAS
eng.invalidate(); assert ref(195.9, 0.1, {"END"}) is None and ref(200, 0.1, {"INS"}) == ("INS", 200, 0)
B.MAX_OBJETOS_REFERENCIAS = viejo
# módulo Bloques apagado: IngeCAD como venía
mods.poner("ingecad", "bloques", False); B._activo_cache[0] = 0.0
eng.invalidate(); assert ref(195.9, 0.1, {"END"}) is None
mods.poner("ingecad", "bloques", True); B._activo_cache[0] = 0.0
eng.invalidate(); assert ref(195.9, 0.1, {"END"}) == ("END", 196, 0)
print("ok referencias sobre bloques")
# ---- 3.10.0: segundo punto de inserción (P2) ------------------------------------------------
import io
def r6(p): return (round(p[0], 6), round(p[1], 6))
# crear por la línea de comandos: base -> nombre -> 2 -> P2 -> Sí
w = Window(); a = w.msp.add_line((10, 10), (14, 10)); b_ = w.msp.add_line((14, 10), (13, 11))
t = bloque(w, [a, b_], "FLECHA", [(10, 10), "FLECHA", "2"]); assert t._paso == "p2"
assert t.referencias_extra() >= {"END", "MID"} and t.resaltado((14, 10))["vista"] == [((10, 10), (14, 10))]
t.on_point((10, 10)); assert t._paso == "p2" and any("coincidir" in m for m in w.msgs)
t.on_point((14, 10)); assert t._paso == "confirmar" and any("P2 (14, 10)" in m for m in w.msgs)
t.on_option("S")
blk = w.document.doc.blocks.get("FLECHA"); assert B.p2_de(blk) == (4.0, 0.0)
f = io.StringIO(); w.document.doc.write(f)                         # viaja con el dibujo
otro = ezdxf.read(io.StringIO(f.getvalue())); assert B.p2_de(otro.blocks.get("FLECHA")) == (4.0, 0.0)
# sin P2 (Enter en el paso P2) y SIN2
w2 = Window(); a = w2.msp.add_line((0, 0), (2, 0))
bloque(w2, [a], "SIMPLE", [(0, 0), "SIMPLE", "2", "", "S"])
assert B.p2_de(w2.document.doc.blocks.get("SIMPLE")) is None
# redefinir sin P2 lo quita; deshacer lo devuelve
nuevo_c = w.msp.add_circle((0, 0), 1)
t = bloque(w, [nuevo_c], "FLECHA", [(0, 0), "FLECHA", "S", "S"])
assert B.p2_de(w.document.doc.blocks.get("FLECHA")) is None
w.history.undo(); assert B.p2_de(w.document.doc.blocks.get("FLECHA")) == (4.0, 0.0)
w.history.undo(); assert "FLECHA" not in w.document.doc.blocks       # deshacer la creación
# con la ventana: «Segundo punto...» -> punto -> la ventana vuelve con P2 y el nombre
llamadas = []
respuestas = [{"accion": "p2", "nombre": "PUERTA", "modo": "R"},
              {"nombre": "PUERTA", "modo": "R", "p2": True}]
def ventana_p2(parent, segs, nombres, cantidad, modo, validar, nombre="", p2=None):
    llamadas.append((nombre, p2, modo)); return respuestas.pop(0)
ui.crear = ventana_p2
w = Window(); a = w.msp.add_line((5, 5), (8, 5))
t = B.BloqueTool(w.ctx()); t.start(); t.on_selection([a]); t.on_point((5, 5))
assert t._paso == "p2"; t.on_point((8, 9))
assert llamadas == [("", None, "C"), ("PUERTA", (3.0, 4.0), "R")]
assert B.p2_de(w.document.doc.blocks.get("PUERTA")) == (3.0, 4.0) and lineas(w.msp) == [(5, 5, 8, 5)]
respuestas[:] = [{"nombre": "SINP2", "modo": "R", "p2": False}]     # «Quitar P2»
t = B.BloqueTool(w.ctx()); t.start(); t.on_selection([a]); t._p2 = (1, 1); t.on_point((5, 5))
assert B.p2_de(w.document.doc.blocks.get("SINP2")) is None
ui.crear = real_crear; B.BloqueTool.modo = "C"
# PUNTOBASEBLOQUE corre P2 con la geometría (y deshacer)
w = Window(); blk = w.document.doc.blocks.new("V"); blk.add_line((0, 0), (4, 0))
B.poner_p2(w.document.doc, blk, (4, 0))
w.history.execute(B.CambiarPuntoBase("V", (2, 0))); assert B.p2_de(blk) == (2.0, 0.0)
w.history.undo(); assert B.p2_de(blk) == (4.0, 0.0)
print("ok P2 al crear: línea de comandos, ventana, redefinir, punto base, DXF")

# INSERT de un bloque con P2: P1 -> P2 (escala 2, giro 90°) -> reflejos -> inserta
w = Window(); blk = w.document.doc.blocks.new("FLECHA")
blk.add_line((0, 0), (4, 0)); blk.add_line((4, 0), (3, 1))      # la punta mira hacia +y
B.poner_p2(w.document.doc, blk, (4, 0))
ui.insertar = lambda *a, **k: {"nombre": "FLECHA", "escala": 1.0, "rotacion": 0.0}
def insertar_flecha(pasos):
    w.finished = False
    for e in list(w.msp.query("INSERT")): w.msp.delete_entity(e)
    t = B.InsertarTool(w.ctx()); t.start()
    for p in pasos:
        if p == "": t.on_enter()
        elif isinstance(p, str): t.on_option(p)
        else: t.on_point(p)
    return t
def puntos(ins):
    return sorted({r6(q) for e in ins.virtual_entities() for q in ((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))})
t = insertar_flecha([])
assert t._paso == "p1" and t.referencias_extra() >= {"END", "INS"}
assert len(t.resaltado((1, 1))["fantasma"]) == 2
t.on_point((10, 10)); assert t._paso == "p2"
fa = t.resaltado((10, 18))["fantasma"]; assert ((10, 18), (8, 16)) in [(r6(p), r6(q)) for p, q in fa]
t.on_point((10, 10)); assert t._paso == "p2"                       # P2 = P1: no
t.on_point((10, 18)); assert t._paso == "perpendicular" and t.referencias_extra() == frozenset()
t.on_enter(); assert t._paso == "eje"; t.on_enter()
(ins,) = w.msp.query("INSERT"); assert w.finished
assert (r6(ins.dxf.insert), round(ins.dxf.xscale, 6), round(ins.dxf.yscale, 6), round(ins.dxf.rotation, 6)) == ((10, 10), 2, 2, 90)
assert puntos(ins) == [(8, 16), (10, 10), (10, 18)]
casos = {(True, False): [(8, 12), (10, 10), (10, 18)],     # perpendicular: P1 y P2 se cambian
         (False, True): [(10, 10), (10, 18), (12, 16)],    # sobre P1-P2: la punta al otro lado
         (True, True): [(10, 10), (10, 18), (12, 12)]}
for (perp, eje), esperado in casos.items():
    pasos = [(10, 10), (10, 18)] + ([(0, 0)] if perp else []) + [""] + (["R"] if eje else []) + [""]
    t = insertar_flecha(pasos)
    (ins,) = w.msp.query("INSERT"); assert puntos(ins) == esperado, (perp, eje, puntos(ins))
    assert (ins.dxf.yscale < 0) == (perp != eje)
t = insertar_flecha([(10, 10), (10, 18), (0, 0), (0, 0)]); assert t._perp is False   # clic alterna
n = len(w.history._undo); t = insertar_flecha([(10, 10), (10, 18), "", ""])
w.history.undo(); assert not w.msp.query("INSERT")                  # un solo deshacer
# un bloque sin P2 no tiene P1/P2 ni reflejos
blk2 = w.document.doc.blocks.new("MESA"); blk2.add_line((0, 0), (1, 0))
ui.insertar = lambda *a, **k: {"nombre": "MESA", "escala": 1.0, "rotacion": 0.0}
t = B.InsertarTool(w.ctx()); t.start(); assert t._dos is None and t._paso is None
t.on_point((3, 3)); (ins,) = [e for e in w.msp.query("INSERT") if e.dxf.name == "MESA"]
assert ins.dxf.yscale == 1 and w.finished
# la ventana de INSERTAR sabe qué bloques tienen P2
visto_ins = {}
def ventana_ins2(parent, nombres, segs_de, escala, rotacion, actual=None, tiene_p2=None):
    visto_ins.update({n: tiene_p2(n) for n in nombres}); return None
ui.insertar = ventana_ins2; B.InsertarTool(w.ctx()).start()
assert visto_ins == {"FLECHA": True, "MESA": False}
# las cuentas: a_insercion devuelve lo mismo que la matriz
m = B.reflejar(B.afin_dos_puntos((0, 0), (4, 0), (1, 2), (4, 6)), (1, 2), (4, 6), "eje")
(x, y), xs, ys, rot = B.a_insercion(m, (0, 0))
co, si = math.cos(math.radians(rot)), math.sin(math.radians(rot))
for q in ((1, 0), (0, 1), (3, -2)):
    esperado = B.aplicar(m, q)
    assert r6((x + co * xs * q[0] - si * ys * q[1], y + si * xs * q[0] + co * ys * q[1])) == r6(esperado)
print("ok INSERT con P2: escala, giro, reflejos, deshacer")

print("TODO OK BLOQUES")
