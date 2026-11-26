"""UNIR (J) con polígonos en IngeCAD (3.96.0, submódulo «unir_poligonos»): como
«Combinar objetos espaciales» de QGIS, con la misma cuenta del núcleo.
Con dos o más polígonos (polilíneas cerradas, círculos) los que se tocan quedan
en uno, con los datos del de mayor superficie; las ranuras encerradas se
rellenan; los grupos aislados quedan aparte. Al final pregunta «¿Quiere crear
una capa nueva con el resultado? [Sí/No] <No>» (3.97.2): No o Enter lo deja
en la misma capa (un solo U) y Sí en la capa «combinados de <capa>», en rojo (la original no se toca); las siguientes con Sí van a esa
misma capa y a su misma tabla. Con líneas, el JOIN de IngeCAD sin cambios. Capa
conectada a un SHP: al guardar, quedan el registro del mayor y los demás se
borran; en la capa nueva los datos viajan en cada objeto (tabla «combinados
de <capa>»), sin tocar el SHP."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, math
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext

ROOT = Path(__file__).resolve().parents[2]
lp = load_plugin(ROOT / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
up = import_module("ingecad_plugin_geocad.unir_poligonos")
mods = import_module("ingecad_plugin_geocad.modulos")
pkg = import_module("ingecad_plugin_geocad")
enl = import_module("ingecad_plugin_geocad.enlace")
shpio = import_module("ingecad_plugin_geocad.shpio")
imp = import_module("ingecad_plugin_geocad.importados")
checkin = import_module("ingecad_plugin_geocad.checkin")
datos = import_module("ingecad_plugin_geocad.datos")

E, N = 14522900.0, 9977200.0
PARCELAS = {   # el caso de las capturas de Fernando: se tocan en vértices, con ranuras
    "A": [(E, N), (E + 10, N), (E + 10, N + 6), (E + 4.7, N + 6), (E, N + 6)],                 # 60 m²
    "B": [(E, N + 6), (E + 4.7, N + 6), (E + 4.7, N + 12), (E, N + 12)],
    "C": [(E + 4.7, N + 6), (E + 4.72, N + 9), (E + 4.7, N + 12), (E + 10, N + 12), (E + 10, N + 6)],
    "D": [(E + 10, N), (E + 14, N), (E + 14, N + 12), (E + 10, N + 12), (E + 10.01, N + 6)],
    "S": [(E + 40, N), (E + 42, N), (E + 42, N + 2), (E + 40, N + 2)],                         # aparte
    "T": [(E + 42, N), (E + 43, N), (E + 43, N + 1), (E + 42, N + 1)],                         # toca a S
}


class Harness:
    def __init__(self):
        self.document = Document(ezdxf.new("R2018")); self.history = History(self.document)
        self.msgs = []; self.finished = False
        self.ctx = ToolContext(execute=self.history.execute, prompt=self.msgs.append,
                               echo=self.msgs.append, finish=lambda: setattr(self, "finished", True),
                               undo_last=self.history.undo)
        self.msp = self.document.doc.modelspace()

    def polis(self, capa="lotes"):
        return [e for e in self.msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == capa]

    def unir(self, entidades, *respuestas):
        t = up.UnirTool(self.ctx); t.start(); t.on_selection(list(entidades))
        for r in respuestas:
            if r == "":
                t.on_enter()
            else:
                assert t.on_option(r), r
        return t


def area(e):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
                   in zip(up.anillo(e), up.anillo(e)[1:] + up.anillo(e)[:1]))) / 2


def dibujar(h, nombres="ABCDST", capa="lotes"):
    if capa not in h.document.doc.layers:
        h.document.doc.layers.add(capa, color=3)
    return {n: h.msp.add_lwpolyline(PARCELAS[n], close=True, dxfattribs={"layer": capa}) for n in nombres}


# ---- 1. Enter: en la misma capa (de fábrica), un solo U -------------------------------------
h = Harness(); p = dibujar(h)
mano = p["A"].dxf.handle
t = h.unir([p[n] for n in "ABCD"])
assert any("¿Quiere crear una capa nueva con el resultado? [Sí/No] <No>" in m for m in h.msgs), h.msgs
assert any("4 polígono(s) en 1 isla(s), 2 hueco(s) encerrado(s) relleno(s)" in m for m in h.msgs), h.msgs
t.on_enter()
assert h.finished
quedan = h.polis()
assert len(quedan) == 3 and sorted(round(area(e), 3) for e in quedan) == [1.0, 4.0, 168.0]
assert "combinados de lotes" not in h.document.doc.layers
h.history.undo()
assert len(h.polis()) == 6 and any(e.dxf.handle == mano for e in h.polis())
h.unir([p[n] for n in "ABCD"], "N")                  # N (No): también en la misma capa
assert len(h.polis()) == 3
h.history.undo()
h.finished = False; h.msgs.clear()
t = h.unir([p[n] for n in "ABCD"], "QUIZAS")                # no se entiende: vuelve a preguntar
assert not h.finished and any("No (o Intro): en la misma capa" in m for m in h.msgs)
for r in ("Sí", "yes", "Y"):
    assert up.C.respuesta(r) == "nueva"
for r in ("no", "NOT", ""):
    assert up.C.respuesta(r) == "original"
t.on_cancel()
print("ok Enter: en la misma capa; un solo U")

# ---- 2. N: capa nueva en rojo; la original no se toca --------------------------------------
h = Harness(); p = dibujar(h)
p["A"].dxf.color = 2                                   # un color propio: en la capa nueva, PorCapa
t = h.unir([p[n] for n in "ABCD"], "S")
nuevas = h.polis("combinados de lotes")
assert nuevas[0].dxf.color == 256 and p["A"].dxf.color == 2
assert len(nuevas) == 1 and abs(area(nuevas[0]) - 168) < 1e-3 and nuevas[0].closed
assert h.document.doc.layers.get("combinados de lotes").dxf.color == 1, "en rojo"
assert len(h.polis()) == 6, "la original no se toca"
assert any("Capa nueva «combinados de lotes»" in m for m in h.msgs), h.msgs
h.history.undo()
assert not h.polis("combinados de lotes") and "combinados de lotes" not in h.document.doc.layers
print("ok N: capa nueva en rojo con la unión, la original intacta; U la quita entera")

# ---- 3. otra N sobre la misma capa: a la MISMA capa combinada ------------------------------
h = Harness(); p = dibujar(h)
h.unir([p[n] for n in "ABCD"], "S")
h.document.doc.layers.get("combinados de lotes").dxf.color = 5       # si la cambia, se respeta
h.msgs.clear()
h.unir([p["S"], p["T"]], "S")
assert any("Agregado a la capa «combinados de lotes»" in m for m in h.msgs), h.msgs
assert "combinados de lotes (2)" not in h.document.doc.layers
assert sorted(round(area(e), 3) for e in h.polis("combinados de lotes")) == [5.0, 168.0]
assert h.document.doc.layers.get("combinados de lotes").dxf.color == 5
h.history.undo()                                     # U de la segunda: la capa queda
assert "combinados de lotes" in h.document.doc.layers and len(h.polis("combinados de lotes")) == 1
print("ok la segunda N va a la misma capa combinada; su U no borra la capa")

# ---- 4. sin contacto, uno solo, líneas: nada o el JOIN de IngeCAD -----------------------------
h = Harness(); p = dibujar(h)
h.unir([p["A"], p["S"]])
assert h.finished and any("no se tocan" in m for m in h.msgs) and len(h.polis()) == 6
h = Harness()
l1 = h.msp.add_line((0, 0), (5, 0)); l2 = h.msp.add_line((5, 0), (9, 0))
h.unir([l1, l2])
assert h.finished and [e.dxftype() for e in h.msp] == ["LINE"], [e.dxftype() for e in h.msp]
assert abs(next(iter(h.msp)).dxf.end.x - 9) < 1e-9 or abs(next(iter(h.msp)).dxf.start.x - 9) < 1e-9
print("ok sin contacto avisa; con líneas, el JOIN de IngeCAD")

# ---- 5. círculo y arcos: pasan a tramos ------------------------------------------------------
h = Harness(); h.document.doc.layers.add("lotes")
c = h.msp.add_circle((5, 5), 3, dxfattribs={"layer": "lotes"})
r = h.msp.add_lwpolyline([(0, 0, 0), (5, 0, 0), (5, 5, 0), (0, 5, 0)], format="xyb", close=True,
                         dxfattribs={"layer": "lotes"})
h.unir([c, r], "N")
(u,) = h.polis()
assert abs(area(u) - (25 + 3 * math.pi * 9 / 4)) < 0.2, area(u)      # cuadrado + 3/4 de círculo
print("ok círculo + polígono")

# ---- 6. capa conectada a un SHP: guardar deja el registro del mayor ----------------------------
d = Path(tempfile.mkdtemp()); shp = d / "parcelas.shp"
campos = [shpio.nuevo_campo("NOMBRE", "C", 10), shpio.nuevo_campo("LOTE", "N", 5)]
filas = []
for i, n in enumerate("ABCDST"):
    ring = PARCELAS[n] + PARCELAS[n][:1]
    if shpio.signed_area(ring) > 0:
        ring = ring[::-1]                                     # SHP: borde en sentido horario
    filas.append((shpio.Geometry(5, [ring]), {"NOMBRE": n, "LOTE": str(i + 1)}))
shpio.escribir_nuevo(shp, 5, campos, filas)


def conectar():
    h = Harness()
    sf = shpio.Shapefile(shp)
    key = enl.layer_key(h.document.doc, shp)
    cmd, n, _sk = enl.connect_commands(h.document, sf, key)
    h.history.execute(cmd)
    ents = {enl.feat_tag(e).fid: e for e in h.msp if enl.feat_tag(e) is not None}
    return h, key, ents


h, key, ents = conectar()
h.unir([ents[i] for i in range(4)], "S")
nuevas = h.polis("combinados de " + key)
assert len(nuevas) == 1 and enl.feat_tag(nuevas[0]) is None, "la capa nueva no queda vinculada"
origen, fid, at = imp._leer(nuevas[0])
assert origen == "combinados de " + key and dict((a, v) for a, _t, v in at) == {"NOMBRE": "A", "LOTE": "1"}, at
assert ("combinados de " + key) in datos.data_tables(h.document)
h.unir([ents[4], ents[5]], "S")                          # otra vez N: misma capa, misma tabla
assert imp.tablas(h.document.doc) == {"combinados de " + key: 2}
assert sorted(f for _o, f, _e in imp.objetos(h.document.doc, "combinados de " + key)) == [0, 1]
plan = checkin.make_plan(h.document, key)
assert plan.is_empty if hasattr(plan, "is_empty") else (not plan.changes and not plan.new), plan
print("ok capa conectada -> capa nueva con los datos del mayor, sin vínculo; el SHP no cambia")

h, key, ents = conectar()
h.unir([ents[i] for i in range(4)] + [ents[4], ents[5]], "N")
plan = checkin.make_plan(h.document, key)
assert plan.deleted == {1, 2, 3, 5} and plan.geom_changed - plan.deleted == {0, 4}, plan.summary() if hasattr(plan, "summary") else plan
assert not plan.new and not plan.errors, plan.errors
print("ok capa conectada, Modificar: queda el registro del mayor, los demás se borran al guardar")

# ---- 7. importados con base de datos (IMPORTARSHP) ------------------------------------------
h = Harness(); p = dibujar(h, "ABCD")
f = [shpio.DbfField("NOMBRE", "C", 10, 0, 1)]
for i, n in enumerate("ABCD"):
    imp.poner_atributos(p[n], "parcelas", f, {"NOMBRE": n}, i)
h.unir(p.values(), "N")
(u,) = h.polis()
assert imp._leer(u)[0] == "parcelas" and imp._leer(u)[2][0][2] == "A" and imp.tablas(h.document.doc) == {"parcelas": 1}
print("ok importados: quedan los datos del mayor")

# ---- 8. el submódulo: encendido, J pasa por GeoCAD; apagado, el de IngeCAD -------------------
assert any(m.clave == "unir_poligonos" and m.cambia_programa for m in mods.CATALOGO["ingecad"])
dib = import_module("ingecad_plugin_geocad.dibujo")
herr = getattr(pkg.construir_spec(), "tools", None) or {}
assert herr.get("GEOJOIN") is up.UnirTool and "JOIN" not in herr, sorted(herr)  # JOIN es de IngeCAD
assert dib.REEMPLAZOS["JOIN"] == ("unir_poligonos", "GEOJOIN")
assert dib.herramienta_para("JOIN", None, herr) == "GEOJOIN"
mods.guardar("ingecad", {**mods.estado("ingecad"), "unir_poligonos": False})
herr = getattr(pkg.construir_spec(), "tools", None) or {}
assert "GEOJOIN" not in herr and dib.herramienta_para("JOIN", None, herr) == "JOIN"
mods.guardar("ingecad", {**mods.estado("ingecad"), "unir_poligonos": True})
print("ok submódulo unir_poligonos")
print("TODO OK")
