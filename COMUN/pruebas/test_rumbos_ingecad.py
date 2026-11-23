"""RUMBOS en IngeCAD (3.87.0, módulo «rumbos»): la misma orden de QGIS. Cada
tramo da EXACTAMENTE lo mismo que tramo_rumbo de Dibujo CAD (QGIS), en los dos
modos y con 30dI/30dD, rumbos y '<<'; Polilínea / Tramos, Base Sí / No, Cerrar,
desHacer; GeoCAD no le reescribe los ángulos; botón en «Yaguá Dibujo» detrás de
RECTANG (también en una barra ya guardada), menú GeoCAD > Dibujo y alias RB."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, types, math, json, importlib.util
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
rb = import_module("ingecad_plugin_geocad.rumbos")
dib = import_module("ingecad_plugin_geocad.dibujo")
mods = import_module("ingecad_plugin_geocad.modulos")
bot = import_module("ingecad_plugin_geocad.botones")
pkg = import_module("ingecad_plugin_geocad")
T = rb.RumbosTool

# el cálculo de QGIS, para comparar
spec = importlib.util.spec_from_file_location("units_qgis", ROOT / "QGIS" / "codigo" / "geocad" / "dibujo" / "units.py")
U = importlib.util.module_from_spec(spec); spec.loader.exec_module(U)


def cerca(a, b, tol=1e-9):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


# ---- 1. cada tramo = tramo_rumbo de QGIS ------------------------------------------------
A, B = (0.0, 0.0), (10.0, 3.0)
textos = ["25.4<91d30'15\"", "25.4<-91d30'15\"", "5<180", "7<45", "3.3<270d12'", "10<0",
          "12.8<-90", "9<-12d5'30.5\"", "8<30dI", "8<30dD", "6<N45d30'E", "6<S10W", "6<<45",
          "4<100g", "4<1.2r", "2.5<N", "@25.4<91d30'15\""]
for modo in ("interior", "deflexion"):
    for txt in textos:
        p, d = rb.tramo(A, B, txt, modo)
        q, dq = U.tramo_rumbo(A, B, txt.lstrip("@"), U.Units(), modo)
        assert cerca(p, q) and d == dq, (modo, txt, p, q)
assert rb.tramo(A, B, "12,5") is None and rb.tramo(A, B, "3,4") is None   # un punto: lo lee IngeCAD
for malo in ("0<90", "-3<90", "5<N95E", "5<abc"):
    try:
        rb.tramo(A, B, malo); raise AssertionError(malo)
    except rb.AnguloError:
        pass
print("ok cada tramo da lo mismo que RUMBOS de QGIS (interior y deflexión)")


# ---- la herramienta con un contexto de prueba ---------------------------------------------
class Harness:
    def __init__(self):
        self.document = Document(ezdxf.new("R2018")); self.history = History(self.document)
        self.msgs = []; self.finished = False
        self.ctx = ToolContext(execute=self.history.execute, prompt=self.msgs.append,
                               echo=self.msgs.append, finish=lambda: setattr(self, "finished", True),
                               undo_last=self.history.undo)

    def ents(self, tipo):
        return [e for e in self.document.modelspace() if e.dxftype() == tipo]


def correr(*entradas, angulo="interior", tramos=False, base=False):
    rb._set(rb.KEY_ANGULO, angulo); rb._set(rb.KEY_TRAMOS, tramos); rb._set(rb.KEY_BASE, base)
    h = Harness(); t = T(h.ctx); t.start()
    for e in entradas:
        if isinstance(e, tuple):
            t.on_point(e)
        elif e == "":
            t.on_enter()
        elif not t.on_option(e):
            raise AssertionError(f"no la tomó: {e}")
    return h, t


def vertices(pl):
    return [tuple(round(c, 9) for c in v[:2]) for v in pl.get_points("xy")]


def r9(p):
    return tuple(round(c, 9) for c in p)


# ---- 2. Polilínea, Base = No: B y los tramos, un solo objeto -------------------------------
p1, _ = rb.tramo(A, B, "25.4<91d30'15\"")
p2, _ = rb.tramo(B, p1, "10<30dI")
h, t = correr(A, B, "25.4<91d30'15\"", "10<30dI", "")
pl = h.ents("LWPOLYLINE")
assert len(pl) == 1 and not h.ents("LINE") and h.finished
assert vertices(pl[0]) == [r9(B), r9(p1), r9(p2)] and not pl[0].closed
assert any("Tramo 2" in m and "acumulado" in m for m in h.msgs), h.msgs
assert any("[Ángulo=Interior/Modo=Polilínea/Base=No]" in m for m in h.msgs), h.msgs
print("ok Polilínea sin base")

# ---- 3. Base = Sí y Cerrar: polilínea cerrada desde A ------------------------------------
h, t = correr(A, B, "B", "10<90", "10<90", "C")
pl = h.ents("LWPOLYLINE")
assert len(pl) == 1 and pl[0].closed and len(vertices(pl[0])) == 4 and vertices(pl[0])[0] == r9(A)
print("ok Base Sí + Cerrar (polilínea cerrada)")

# ---- 4. Tramos: una línea por tramo, la base primero; desHacer saca la última --------------
h, t = correr(A, B, "M", "B", "5<180", "5<90", "5<90")
assert len(h.ents("LINE")) == 4 and not h.ents("LWPOLYLINE")       # base + 3 tramos
t.on_option("H")
assert len(h.ents("LINE")) == 3 and len(t.pts) == 4
t.on_option("U"); t.on_option("U")           # el primer tramo se lleva la base
assert len(h.ents("LINE")) == 0 and len(t.pts) == 2
t.on_option("5<90"); t.on_option("5<90"); t.on_option("C")
assert len(h.ents("LINE")) == 4 and h.finished                      # base, 2 tramos y el cierre
print("ok Tramos, desHacer y Cerrar")

# ---- 5. Deflexión, ajustes recordados, distancia sola y clics --------------------------------
h, t = correr(A, B, "A", "5<0")
assert t.angulo == "deflexion" and str(rb._get(rb.KEY_ANGULO, "")) == "deflexion"
assert cerca(t.pts[-1], rb.tramo(A, B, "5<0", "deflexion")[0])
assert t.on_option("7") is False            # distancia sola: la resuelve IngeCAD hacia el cursor
t.on_point((30.0, 30.0)); t.on_point((30.0, 30.0))
assert any("repetido" in m for m in h.msgs)
t.on_cancel()                                # Esc también deja la polilínea, como QGIS
assert len(h.ents("LWPOLYLINE")) == 1 and len(vertices(h.ents("LWPOLYLINE")[0])) == 3
h, t = correr(A, B, "5<N95E")
assert len(t.pts) == 2 and any("no válido" in m for m in h.msgs)
h, t = correr(A, "")                         # Enter sin tramos: nada
assert h.finished and not list(h.document.modelspace())
print("ok Deflexión, ajustes, clics y errores")

# ---- 6. vista previa y referencias ----------------------------------------------------------
h, t = correr(A, B, angulo="interior")
assert t.preview_segments((20.0, 3.0)) == [(A, B), (B, (20.0, 3.0))]      # base como guía
t.on_option("5<180")
segs = t.preview_segments((40.0, 0.0))
assert len(segs) == 2 and segs[0][0] == B and t.drawn_segments() == [(B[0], B[1], *t.pts[-1])]
print("ok vista previa")

# ---- 7. GeoCAD no le reescribe los ángulos (en LÍNEA sí) -------------------------------------
recibido = []
envuelta = dib._envolver_on_text(lambda self, text: recibido.append(text) or True)
ctl = types.SimpleNamespace(tool=t, _selecting_for=None, _modifier=None, dyn_on=False, window=None)
envuelta(ctl, "8<30dI")
linea = types.SimpleNamespace(name="LINE", _points=[(0, 0), (1, 0)], last_point=(1, 0),
                              entity_picker=False, wants_raw_text=lambda: False)
ctl.tool = linea
envuelta(ctl, "@8<90")
assert recibido[0] == "8<30dI" and recibido[1] != "@8<90", recibido
print("ok el envoltorio de ángulos relativos la deja pasar")

# ---- 8. registro, menú, barra, módulo -----------------------------------------------------
s = pkg.construir_spec(completo=True)
assert s.tools.get("RUMBOS") is T
assert all(s.aliases.get(a) == "RUMBOS" for a in ("RB", "GMS", "POLIGONAL"))
items = []
def recorrer(es):
    for e in es:
        if hasattr(e, "command"): items.append(e)
        elif hasattr(e, "items"): recorrer(e.items)
recorrer(s.menu)
it = [i for i in items if i.command == "RUMBOS"]
assert it and it[0].label == "Bearings traverse (RUMBOS)" and Path(str(it[0].icon)).name == "rumbos.png"
assert Path(str(it[0].icon)).is_file()
es = json.loads((ROOT / "INGECAD/codigo/geocad/i18n/es/ui.json").read_text(encoding="utf-8"))
assert es["Bearings traverse (RUMBOS)"] == "Poligonal por rumbos (RUMBOS)"
y = import_module("ingecad_plugin_geocad.yaguarete")
assert ("RUMBOS", None) in y.elegidas(mods.estado("ingecad")) and "RUMBOS" in y.DESCRIPCIONES
dibujo_bar = dict(bot.DEFECTO["ingecad"])["Yaguá Dibujo"]
assert dibujo_bar[:2] == ("RECTANG", "RUMBOS")
assert "RUMBOS" in bot.TEMA_BANCO["ingecad"]["Dibujo"]
mods.poner("ingecad", "rumbos", False)
s = pkg.construir_spec(completo=True)
assert "RUMBOS" not in s.tools and "RB" not in s.aliases
assert ("RUMBOS", None) not in y.elegidas(mods.estado("ingecad"))
mods.poner("ingecad", "rumbos", True)
print("ok orden, alias, menú, barra y módulo")

# ---- 9. una barra ya guardada recibe RUMBOS detrás de RECTANG, una sola vez -----------------
crudo = {"categorias": [{"nombre": "Mi dibujo", "botones": ["TEXT", "RECTANG", "SHPNEW"]}],
         "migraciones": ["limpiar-plano"]}
assert bot._migrar("ingecad", crudo)
assert crudo["categorias"][0]["botones"] == ["TEXT", "RECTANG", "RUMBOS", "SHPNEW"]
assert not bot._migrar("ingecad", crudo)
crudo = {"categorias": [{"nombre": "X", "botones": ["SHPNEW"]}], "migraciones": ["limpiar-plano"]}
bot._migrar("ingecad", crudo)
assert crudo["categorias"][0]["botones"] == ["SHPNEW"]          # sin RECTANG: queda en la barra GeoCAD
print("ok barra guardada")
print("TODO OK RUMBOS INGECAD")
