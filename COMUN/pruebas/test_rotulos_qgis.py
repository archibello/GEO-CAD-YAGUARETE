"""3.50.0 rótulos y simbología de QGIS como en IngeCAD (Fernando: «que no haya
disparidades»): los rótulos que llegan de QGIS ({fid: [texto, altura]}) se
ubican con el motor de ROTULOSIG y sus últimas opciones, y quedan IGUALES a
los de un ROTULOSIG corrido en IngeCAD; una capa categorizada llega como
SHPTHEME (leyenda y SHPTHEMEOFF); los puntos, sin símbolo."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, types
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
import shapefile
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False); assert lp.available, lp.reason
spec = lp.spec
buzon = import_module("ingecad_plugin_geocad.buzon")
puente = import_module("ingecad_plugin_geocad.puente")
enlace = import_module("ingecad_plugin_geocad.enlace")
rotulos = import_module("ingecad_plugin_geocad.rotulos")
hd = import_module("ingecad_plugin_geocad.herramientas_datos")

doc = Document.new(); hist = History(doc); log = []; answers = []
class Tools:
    def start_tool(self, name):
        ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=log.append, finish=lambda: None,
                          ask_text=lambda p, d="": answers.pop(0) if answers else d,
                          ask_choice=lambda p, items, d="": (lambda a: None if a is None else next((i for i in items if i.startswith(a)), None))(answers.pop(0) if answers else None),
                          services=types.SimpleNamespace(document=doc))
        spec.tools[name](ctx).start()
class VP:
    def __init__(self): self.view = types.SimpleNamespace(zoom_extents=lambda *a: None)
    def push_view(self): pass
    def update(self): pass
win = types.SimpleNamespace(tools=Tools(), viewport=VP(), command_line=types.SimpleNamespace(echo=log.append),
                            isMinimized=lambda: False, raise_=lambda: None, activateWindow=lambda: None)
puente._state["window"] = win
tmp = tempfile.mkdtemp()


def send(base, estilo, fids=None):
    ref = buzon.layer_ref("shp", base + ".shp", ""); ref["estilo"] = estilo
    if fids is not None:
        ref["fids"] = fids
    log.clear(); buzon.send("ingecad", {"tipo": "conectar", "capas": [ref]}, "qgis")
    for m in buzon.receive("ingecad"): puente.handle(m)
    print("\n".join(log))


def labels(key):
    """Los rótulos de la capa, comparables: texto, punto, altura, giro, alineación, XDATA; y círculos."""
    out = []
    for e in doc.doc.modelspace():
        if e.dxf.layer != f"{key}-ROTULOS":
            continue
        xd = [v for _c, v in e.get_xdata("INGECAD")] if e.has_xdata("INGECAD") else []
        if e.dxftype() == "TEXT":
            out.append(("T", e.dxf.text, tuple(round(v, 6) for v in tuple(e.dxf.align_point)[:2]),
                        round(e.dxf.height, 6), round(e.dxf.rotation, 6), e.dxf.halign, tuple(xd)))
        elif e.dxftype() == "CIRCLE":
            out.append(("C", tuple(round(v, 6) for v in tuple(e.dxf.center)[:2]), round(e.dxf.radius, 6), tuple(xd)))
    return sorted(out, key=repr)


def rotulosig(key, field, height, op):
    """Lo mismo, pero con ROTULOSIG corrido en IngeCAD (después de borrar lo que llegó)."""
    for c in hd.erase_labels(doc, key):
        hist.execute(c)
    assert not labels(key)
    command, n, _old = hd.label_commands(doc, key, field, height, op)
    hist.execute(command)
    return labels(key)


# las últimas opciones de ROTULOSIG: con círculo y todos con la altura del más chico
op = rotulos.OpcionesRotulo(circulo="si", altura="menor")
rotulos.guardar_opciones(op)

# polígonos: una parcela grande, una angosta (el rótulo se achica) y una sin nombre
base = os.path.join(tmp, "parcelas")
w = shapefile.Writer(base, shapeType=shapefile.POLYGON); w.field("NOMBRE", "C", size=20); w.field("USO", "C", size=10)
w.poly([[(0, 0), (0, 60), (80, 60), (80, 0), (0, 0)]]); w.record("Parcela 1", "RURAL")
w.poly([[(100, 0), (100, 6), (160, 6), (160, 0), (100, 0)]]); w.record("Parcela angosta 2", "URBANO")
w.poly([[(0, 100), (0, 140), (30, 140), (30, 100), (0, 100)]]); w.record("", "RURAL")
w.close()
estilo = {"objetos": {"0": ["", "#00ff00"], "1": ["", "#ff0000"], "2": ["", "#00ff00"]},
          "rotulos_sig": {"0": ["Parcela 1", 5.0], "1": ["Parcela angosta 2", 5.0]},
          "campo_rotulo": "NOMBRE",
          "tematico": {"campo": "USO", "metodo": "categorias",
                       "leyenda": [["#00ff00", "RURAL"], ["#ff0000", "URBANO"]]},
          "rotulos": {"0": ["no", 0, 0, 9.0, 0.0, "c", ""]}}     # el formato viejo no se usa
send(base, estilo)
key = "SHP-parcelas"
got = labels(key); print(got)
texts = [g for g in got if g[0] == "T"]
assert sorted(t[1] for t in texts) == ["Parcela 1", "Parcela angosta 2"], texts
assert sum(1 for g in got if g[0] == "C") == 2, got                         # con círculo, como ROTULOSIG
assert len({t[3] for t in texts}) == 1 and texts[0][3] < 5.0, texts          # todos con la altura del más chico
assert all(t[6][-1] == "NOMBRE" for t in texts), texts
assert not any(g[1] == "no" for g in texts)
assert any("2 rótulo(s) de QGIS" in l and "ubicados como ROTULOSIG" in l and "2 con círculo" in l for l in log), log
# el temático, como SHPTHEME: leyenda en la línea de comandos y SHPTHEMEOFF lo quita
assert any("Temático de SHP-parcelas por USO (categorías)" in l for l in log), log
assert any(l.strip() == "color   3: RURAL" for l in log) and any(l.strip() == "color   1: URBANO" for l in log), log
assert any("SHPTHEMEOFF" in l for l in log) and not any(l == "Con los colores de QGIS." for l in log), log
feats = {enlace.feat_tag(e).fid: e for e in doc.doc.modelspace() if enlace.feat_tag(e) and enlace.feat_tag(e).key == key}
assert feats[0].dxf.color == 3 and feats[1].dxf.color == 1, (feats[0].dxf.color, feats[1].dxf.color)
# SIN DISPARIDADES: igual que ROTULOSIG con el mismo campo, altura y opciones
same = rotulosig(key, "NOMBRE", 5.0, op)
assert got == same, (got, same)
log.clear(); win.tools.start_tool("SHPTHEMEOFF")      # una sola capa conectada: no pregunta
assert all(e.dxf.get("color", 256) == 256 for e in feats.values()), [e.dxf.get("color", 256) for e in feats.values()]

# líneas: centradas sobre la línea, en la mitad, a media altura del texto; sin círculo
rotulos.guardar_opciones(rotulos.OpcionesRotulo())
base = os.path.join(tmp, "calles")
w = shapefile.Writer(base, shapeType=shapefile.POLYLINE); w.field("CALLE", "C", size=20)
w.line([[(0, 0), (40, 30)]]); w.record("San Martin")
w.line([[(100, 0), (60, 0)]]); w.record("Belgrano")                         # de derecha a izquierda: legible
w.close()
send(base, {"rotulos_sig": {"0": ["San Martin", 2.0], "1": ["Belgrano", 3.0]}, "campo_rotulo": "CALLE"})
got = labels("SHP-calles"); print(got)
sm = next(g for g in got if g[1] == "San Martin"); be = next(g for g in got if g[1] == "Belgrano")
assert sm[2] == (20.0, 15.0) and abs(sm[4] - 36.869898) < 1e-5 and sm[3] == 2.0, sm
assert be[2] == (80.0, 0.0) and be[4] == 0.0 and be[3] == 3.0 and be[5] == 1, be      # 1 = centro
assert not any(g[0] == "C" for g in got)
# con altura propia cada uno conserva la de su etiqueta de QGIS; ROTULOSIG con 2 da lo mismo para el de 2
assert rotulosig("SHP-calles", "CALLE", 2.0, rotulos.OpcionesRotulo())[1:] == [sm], "líneas"

# puntos: sin el símbolo de QGIS (POINT, no bloque); rótulo como ROTULOSIG (centrado en el punto)
base = os.path.join(tmp, "postes")
w = shapefile.Writer(base, shapeType=shapefile.POINT); w.field("ID", "C", size=5)
w.point(10, 10); w.record("P1"); w.point(20, 10); w.record("P2"); w.close()
send(base, {"rotulos_sig": {"0": ["P1", 1.0]}, "campo_rotulo": ""}, fids=[0])
ents = [e for e in doc.doc.modelspace() if enlace.feat_tag(e) and enlace.feat_tag(e).key == "SHP-postes"]
assert [e.dxftype() for e in ents] == ["POINT"], ents
got = labels("SHP-postes"); assert got == [("T", "P1", (10.0, 10.0), 1.0, 0.0, 1, ("SHP-LABEL", "SHP-postes", 0, "QGIS"))], got
# ampliar la conexión: el que se suma llega con su rótulo, los anteriores siguen
send(base, {"rotulos_sig": {"1": ["P2", 1.0]}, "campo_rotulo": ""}, fids=[1])
got = labels("SHP-postes"); assert sorted(g[1] for g in got) == ["P1", "P2"], got
assert any("1 rótulo(s) de QGIS" in l for l in log), log

# QGIS anterior a 3.50.0 (rótulos ya ubicados): siguen llegando como antes
base = os.path.join(tmp, "viejo")
w = shapefile.Writer(base, shapeType=shapefile.POINT); w.field("ID", "C", size=5)
w.point(0, 0); w.record("V"); w.close()
send(base, {"rotulos": {"0": ["V", 0.5, 0, 1.0, 0.0, "i", ""]}})
got = labels("SHP-viejo"); assert len(got) == 1 and got[0][2] == (0.5, 0.0), got
# 3.50.1 a 3.50.3 «Enviar a IngeCAD» con la altura elegida: círculo siempre = diagonal del texto
# + 10 %; los que entran, con esa altura; los achicados con la INTERMEDIA (a mitad de camino,
# en proporción, entre la mínima y la media de la 3.50.2) donde entra, iguales entre sí; los
# demás con la mínima, o sin rótulo si no llega a 1/3 de la intermedia; aunque ROTULOSIG
# tenga otras opciones guardadas
rotulos.guardar_opciones(rotulos.OpcionesRotulo(circulo="no", altura="propia"))
medir = rotulos.medidor(doc.doc)
k = lambda txt: (medir(txt, 1.0) ** 2 + 1) ** 0.5 * 1.1 / 2                    # radio por unidad de altura


def manzana(nombre, anchos):
    """Una parcela grande (L1) y una angosta por ancho (L2...), de 60 de largo."""
    base = os.path.join(tmp, nombre)
    w = shapefile.Writer(base, shapeType=shapefile.POLYGON); w.field("N", "C", size=5)
    w.poly([[(0, 0), (0, 60), (80, 60), (80, 0), (0, 0)]]); w.record("L1")
    for i, alto in enumerate(anchos):
        x = 100 * (i + 1)
        w.poly([[(x, 0), (x, alto), (x + 60, alto), (x + 60, 0), (x, 0)]]); w.record(f"L{i + 2}")
    w.close()
    send(base, {"rotulos_sig": {str(i): [f"L{i + 1}", 5.0] for i in range(len(anchos) + 1)},
                "campo_rotulo": "N", "rotulos_opciones": {"circulo": "si", "altura": "achicados"}})
    got = labels(f"SHP-{nombre}"); print(got)
    return {g[1]: g for g in got if g[0] == "T"}, {g[3][2]: g for g in got if g[0] == "C"}


# seis lotes parecidos (8 a 6) y dos pasillos (2 y 1,8): los lotes, todos con la intermedia
t, c = manzana("lotes", (8, 7.6, 7.2, 6.8, 6.4, 6, 2, 1.8))
assert t["L1"][3] == 5.0 and abs(c[0][2] - 5.0 * k("L1")) < 1e-5, (t["L1"], c[0])   # entra: la elegida
kmax = max(k(f"L{i}") for i in range(2, 10))
minima, media = 0.9 * 0.9 / kmax, 0.9 * 3.4 / kmax         # lo que entra en la mitad chica / holgada
inter = (minima * media) ** 0.5
lotes = [f"L{i}" for i in range(2, 8)]
assert all(abs(t[x][3] - inter) < 1e-6 for x in lotes), [t[x][3] for x in lotes]          # iguales
assert all(abs(c[i][2] - inter * kmax) < 1e-6 for i in range(1, 7)), c                    # círculos iguales
assert inter * kmax <= 0.9 * 3 + 1e-9                                                     # entran en el más chico
assert abs(t["L8"][3] - t["L9"][3]) < 1e-12 and abs(t["L9"][3] - 0.9 * 0.9 / max(k("L8"), k("L9"))) < 1e-6, t
assert c[7][2] == c[8][2] and t["L9"][3] < inter, c                                       # pasillos: la mínima
assert c[1][1] == t["L2"][2] == (130.0, 4.0), (c[1], t["L2"])                              # en su epicentro
# pasillos muy angostos (0,6 y 0,5): la mínima no llega a 1/3 de la intermedia -> sin rótulo
t, c = manzana("lotes2", (8, 7.6, 7.2, 6.8, 6.4, 6, 0.6, 0.5))
assert "L8" not in t and "L9" not in t and 7 not in c and 8 not in c, t
assert all(t[x][3] == t["L2"][3] for x in lotes) and len(t) == 7, t
assert any("2 parcela(s) muy chicas van sin rótulo" in l for l in log), log
print("TODO OK ROTULOS QGIS")
