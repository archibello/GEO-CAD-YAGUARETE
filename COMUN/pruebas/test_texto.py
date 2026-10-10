"""TEXTO (TEXT) como AutoCAD para IngeCAD (módulo «texto»): 1er punto el
inicio, 2º la altura, 3º la dirección; mientras se eligen la altura y la
dirección, una «Ɪ» de muestra dibujada como texto de verdad (preview_command)
que crece y gira con el cursor, sin tocar el plano ni el historial."""
import os, sys, tempfile, types, math
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
tx = import_module("ingecad_plugin_geocad.texto")
T = tx.TextoTool
assert lp.spec.tools.get("GEOTEXT") is T
assert tx.MUESTRA == "Ɪ" and tx.MUESTRA_SIMPLE == "I"


class Harness:
    def __init__(self):
        self.document = Document(ezdxf.new("R2018")); self.history = History(self.document)
        self.msgs = []; self.finished = False
        self.ctx = ToolContext(execute=self.history.execute, prompt=self.msgs.append,
                               echo=self.msgs.append, finish=lambda: setattr(self, "finished", True),
                               services=None)
    @property
    def msp(self): return self.document.modelspace()


# render.backend usa Qt: uno falso anota qué recibe (en IngeCAD real se
# verificó aparte que la escena se arma y que no queda nada en el plano)
VISTOS = []
def _escena_falsa(document, entities, flatten, canvas=None):
    VISTOS.append([(e.dxftype(), e.dxf.text, e.is_alive) for e in entities])
    if FALLAR: raise RuntimeError("fuente rota")
    return object()
FALLAR = False
sys.modules["render.backend"] = types.SimpleNamespace(build_scene_for_entities=_escena_falsa)


class Controlador:
    """Lo que ``escena`` usa del ToolController de IngeCAD."""
    def __init__(self, h):
        self.window = types.SimpleNamespace(document=h.document); self._flatten = 0.01
    def canvas_space(self): return None


def vista(h, t, cursor):
    """La muestra que se dibujaría: (texto, altura, giro, inserción). Pasa
    también por ``escena`` (crea, dibuja y borra) y comprueba que no quede."""
    cmd = t.preview_command(cursor)
    if cmd is None:
        return None
    assert not hasattr(cmd, "_factory")     # sin GeoCAD, IngeCAD no la dibuja (ni la deja)
    antes = len(h.msp)
    assert cmd.escena(Controlador(h)) is not None and len(h.msp) == antes
    assert VISTOS[-1][0][0] == "TEXT" and VISTOS[-1][0][2]     # se dibujó viva y después se borró
    space = h.msp
    e = cmd.comando(h.document.doc)._factory(space)
    try:
        return e.dxf.text, e.dxf.height, e.dxf.rotation, tuple(e.dxf.insert)[:2]
    finally:
        space.delete_entity(e)


def cerca(a, b): return abs(a - b) < 1e-9


h = Harness(); t = T(h.ctx); t.start()
assert t.preview_command((3, 4)) is None and t.muestra((3, 4)) is None   # falta el 1er punto
t.on_point((10, 20))
assert t._pide() == "altura"

# 2º punto: la «Ɪ» crece con el cursor (altura = distancia), sin girar
v = vista(h, t, (13, 24))
assert v[0] in ("Ɪ", "I") and cerca(v[1], 5) and cerca(v[2], 0) and v[3] == (10, 20), v
v = vista(h, t, (10, 22.5))
assert cerca(v[1], 2.5), v
assert vista(h, t, (10, 20)) is None                  # en el mismo punto: nada
r = t.resaltado((13, 24))
assert r["textos"] == [((13, 24), "Altura 5")] and "vista" not in r
assert len(h.msp) == 0 and not h.history._undo     # la muestra no deja nada

t.on_point((10, 25))                                   # altura 5
assert cerca(t._height, 5) and t._pide() == "angulo"

# 3er punto: con la altura elegida, la «Ɪ» gira hacia el cursor
v = vista(h, t, (20, 30))
assert v[0] in ("Ɪ", "I") and cerca(v[1], 5) and cerca(v[2], 45), v
v = vista(h, t, (10, 15))
assert cerca(v[2], 270), v
assert t.resaltado((10, 30))["textos"] == [((10, 30), "Ángulo 90°")]
assert len(h.msp) == 0 and not h.history._undo

t.on_point((10, 40))                                   # dirección: 90°
assert cerca(t._rotation, 90) and t.typing
assert t.preview_command((50, 50)) is None and t.resaltado((50, 50))["textos"] == []

t._buffer = "Lote 12"; t.finish_typing()
textos = [e for e in h.msp if e.dxftype() == "TEXT"]
assert len(textos) == 1, textos
e = textos[0]
assert e.dxf.text == "Lote 12" and cerca(e.dxf.height, 5) and cerca(e.dxf.rotation, 90)
assert tuple(e.dxf.insert)[:2] == (10, 20) and h.finished
assert not [x for x in h.msp if x.dxftype() == "TEXT" and x.dxf.text in ("Ɪ", "I")]

# altura escrita: la muestra ya gira con esa altura
h = Harness(); t = T(h.ctx); t.start(); t.on_point((0, 0)); t.on_option("2")
v = vista(h, t, (0, 7))
assert cerca(v[1], 2) and cerca(v[2], 90), v

# justificación (MC): la muestra sale con la misma; FIT/ALIGNED no la usa
h = Harness(); t = T(h.ctx); t.start(); t._align = "MC"; t.on_point((0, 0))
e = t.preview_command((0, 3)).comando(h.document.doc)._factory(h.msp)
assert cerca(e.dxf.height, 3) and tuple(e.dxf.align_point)[:2] == (0, 0)
h.msp.delete_entity(e)

# si el dibujo falla, la muestra igual se borra
FALLAR = True
h = Harness(); t = T(h.ctx); t.start(); t.on_point((0, 0))
try:
    t.preview_command((0, 3)).escena(Controlador(h)); raise AssertionError("debía fallar")
except RuntimeError:
    pass
assert len(h.msp) == 0
FALLAR = False

# la letra: «Ɪ» sólo si la fuente la tiene (DejaVu Sans no: salía un rectángulo)
d = ezdxf.new("R2018")
assert tx.caracter_muestra(d) in ("Ɪ", "I")
d.styles.add("SINFUENTE", font="no_existe_xyz.ttf")
assert tx.caracter_muestra(d, "SINFUENTE") == "I"
assert tx.caracter_muestra(None) == "I"                 # sin documento: la segura

# recuadro girado: la caja del texto sin girar, girada con él
from ezdxf import bbox
d = ezdxf.new("R2018"); m = d.modelspace()
for giro, alin in ((0, "LEFT"), (30, "LEFT"), (-20, "LEFT"), (90, "MIDDLE_CENTER"), (135, "BOTTOM_RIGHT")):
    e = m.add_text("dsdfd", height=2.5, dxfattribs={"rotation": giro})
    from ezdxf.enums import TextEntityAlignment
    e.set_placement((10, 20), align=getattr(TextEntityAlignment, alin)) if alin != "LEFT" else e.set_placement((10, 20))
    q = tx.recuadro(e); assert q and len(q) == 4
    lados = [math.dist(q[i], q[(i + 1) % 4]) for i in range(4)]
    assert cerca(lados[0], lados[2]) and cerca(lados[1], lados[3])      # rectángulo
    assert abs(math.degrees(math.atan2(q[1][1] - q[0][1], q[1][0] - q[0][0])) - giro) % 360 < 1e-6 \
        or abs(abs(math.degrees(math.atan2(q[1][1] - q[0][1], q[1][0] - q[0][0])) - giro) % 360 - 360) < 1e-6
    caja = bbox.extents([e], fast=False)                                 # su caja derecha = la de ezdxf
    xs, ys = [p[0] for p in q], [p[1] for p in q]
    assert abs(min(xs) - caja.extmin.x) < 1e-6 and abs(max(ys) - caja.extmax.y) < 1e-6, (giro, alin)
corto = m.add_text("ab", height=2.5, dxfattribs={"rotation": 30}); corto.set_placement((0, 0))
largo = m.add_text("ab" * 6, height=2.5, dxfattribs={"rotation": 30}); largo.set_placement((0, 0))
assert math.dist(*tx.recuadro(largo)[:2]) > 4 * math.dist(*tx.recuadro(corto)[:2])   # acompaña al largo
al = m.add_text("x", height=1); al.set_placement((0, 0), (5, 5), align=TextEntityAlignment.ALIGNED)
assert tx.recuadro(al) is None and tx.recuadro(m.add_line((0, 0), (1, 1))) is None

# resaltado: el TEXT elegido cambia su caja derecha por los 4 lados girados
from core.document import Document
from core.select import GeometryIndex
D = Document(d); idx = GeometryIndex(D)
sel = {e.dxf.handle}
boxes = idx.boxes_of(sel)
assert len(boxes) == 1
lados, fuera = tx.resaltar_girados(idx, sel, boxes)
assert len(lados) == 4 and fuera == {0}
lados, fuera = tx.resaltar_girados(idx, set(), boxes)
assert lados == [] and fuera == set()

# clic: un TEXT se elige sólo desde adentro de su recuadro girado
assert tx.adentro((1, 1), [(0, 0), (2, 0), (2, 2), (0, 2)])
assert tx.adentro((2, 1), [(0, 0), (2, 0), (2, 2), (0, 2)])            # el borde cuenta
assert not tx.adentro((3, 1), [(0, 0), (2, 0), (2, 2), (0, 2)])
assert tx.activo()
d = ezdxf.new("R2018"); m = d.modelspace()
t45 = m.add_text("Largo (L) =5m", height=2.5, dxfattribs={"rotation": 45}); t45.set_placement((0, 0))
q = tx.recuadro(t45)
xs, ys = [p[0] for p in q], [p[1] for p in q]
esquina = (max(xs) - 0.2, min(ys) + 0.2)            # dentro de la caja derecha, lejos del texto
medio = (sum(xs) / 4, sum(ys) / 4)                  # sobre el texto
assert not tx.adentro(esquina, q) and tx.adentro(medio, q)
idx = GeometryIndex(Document(d))
assert GeometryIndex.pick._puente_fabrica is tx._envolver_pick
assert idx.pick(medio, 0.5) == t45.dxf.handle
assert idx.pick(esquina, 0.5) is None, "elegido desde afuera del recuadro"
assert idx.pick_all(esquina, 0.5) == [] and idx.pick_all(medio, 0.5) == [t45.dxf.handle]
ln = m.add_line((esquina[0] - 1, esquina[1]), (esquina[0] + 1, esquina[1]))   # una línea ahí: gana ella
idx = GeometryIndex(Document(d))
assert idx.pick(esquina, 0.5) == ln.dxf.handle
derecho = m.add_text("abc", height=2.5); derecho.set_placement((100, 0))       # sin girar: igual que antes
idx = GeometryIndex(Document(d))
assert idx.pick((101, 1), 0.5) == derecho.dxf.handle

# editar el texto en el lugar no cambia la versión del índice: el recuadro
# (resaltado y clic) igual tiene que acompañar al texto nuevo
largo = m.add_text("B" + "-" * 40, height=2.5, dxfattribs={"rotation": 5}); largo.set_placement((300, 0))
idx = GeometryIndex(Document(d)); idx.pick((0, 0), 0.1)
antes = tx._recuadro_de(idx, largo.dxf.handle)
caja_larga = idx.boxes_of({largo.dxf.handle})[0]
lejos = (sum(p[0] for p in antes[1:3]) / 2 - 1, sum(p[1] for p in antes[1:3]) / 2)   # cerca del final
assert idx.pick(lejos, 0.1) == largo.dxf.handle
v = idx.version
largo.dxf.text = "B" + "-" * 20                         # se borra la mitad, sin tocar el índice
assert idx.version == v
despues = tx._recuadro_de(idx, largo.dxf.handle)
assert math.dist(*despues[:2]) < 0.7 * math.dist(*antes[:2])        # el recuadro se achicó
assert tx._firmas(idx, {largo.dxf.handle}) != ((largo.dxf.handle, None),)
f1 = tx._firmas(idx, {largo.dxf.handle}); largo.dxf.text = "B"; assert tx._firmas(idx, {largo.dxf.handle}) != f1
largo.dxf.text = "B" + "-" * 20
assert idx.pick(lejos, 0.1) != largo.dxf.handle                     # ya no llega hasta ahí

# y en el índice de IngeCAD: la caja derecha vieja (el rectángulo «fantasma»
# del resaltado) se cambia por la nueva al notar la edición
nueva = idx.boxes_of({largo.dxf.handle})[0]                         # la puso al día _recuadro_de
assert nueva[2] < caja_larga[2] - 1 and idx.version > v              # más corta
lados, fuera = tx.resaltar_girados(idx, {largo.dxf.handle}, idx.boxes_of({largo.dxf.handle}))
assert fuera == {0} and len(lados) == 4                              # sin caja de IngeCAD
largo.dxf.text = "B" + "-" * 10                                      # otra edición: la nota _recuadro_de
tx._recuadro_de(idx, largo.dxf.handle)
assert idx.boxes_of({largo.dxf.handle})[0][2] < nueva[2] - 1
# un elegido editado en el lugar: el resaltado de IngeCAD + el nuestro
class TC:
    def __init__(self, index, sel): self.index, self.selection = index, sel
import numpy as np
def original(self):
    return (np.empty((0, 4)), np.empty((0, 4)), self.index.boxes_of(self.selection))
resaltar = tx._envolver_resaltado(original)
t = TC(idx, {largo.dxf.handle})
segs, _, boxes = resaltar(t); assert len(boxes) == 0 and len(segs) == 4
antes_x = max(p[0] for p in tx.recuadro(largo))
largo.dxf.text = "B" + "-" * 40                                      # crece: también
segs, _, boxes = resaltar(t)
assert len(boxes) == 0 and max(max(r[0], r[2]) for r in segs) > antes_x + 5
assert idx.boxes_of({largo.dxf.handle})[0][2] > antes_x + 5          # y el clic la alcanza

# actualizar sin reiniciar IngeCAD: el índice trae el guardado de 3.15.1-3.15.4
# (una tupla). Rompía el clic: «'tuple' object has no attribute 'get'»
idx = GeometryIndex(Document(d)); idx._geocad_recuadros = (idx.version, {})
assert idx.pick(lejos, 0.1) == largo.dxf.handle and isinstance(idx._geocad_recuadros, dict)
idx._geocad_recuadros = "cualquier cosa"; idx.pick((0, 0), 0.1)
t._geocad_firmas_vistas = "viejo"; resaltar(t)
class Roto:
    def entity(self, h): raise RuntimeError("roto")
assert tx.fuera_del_texto(Roto(), "1", (0, 0)) is False          # un error nunca rompe el clic

# caja de edición de un TEXT: mide lo escrito y crece letra a letra
assert tx.ancho_caja(0, 2, 20) == 12 + 2 + 10                      # vacía: una letra
c, cc, ccc = (tx.ancho_caja(w, 2, 20) for w in (12, 24, 36))
assert c < cc < ccc and ccc - c == 24                             # crece con lo escrito
assert tx.ancho_caja(12, 2, 20) < 120                              # una «C»: no la franja de antes
print("TODO OK: TEXTO con «Ɪ» de muestra (altura y dirección con vista previa)")
