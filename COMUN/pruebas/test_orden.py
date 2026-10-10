"""Orden de dibujo (3.16.0): Traer al frente / Enviar al fondo en la barra
GeoCAD, sobre la orden DRAWORDER de IngeCAD, para líneas, polilíneas,
sombreados, textos, cotas y bloques."""
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pathlib import Path
from importlib import import_module
from core.commands import History
from core.document import Document
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
spec = lp.spec
orden = import_module("ingecad_plugin_geocad.orden")
barra = import_module("ingecad_plugin_geocad.barra")
yag = import_module("ingecad_plugin_geocad.yaguarete")
modulos = import_module("ingecad_plugin_geocad.modulos")

# -- el módulo, los botones y el menú
assert "orden" in {m.clave for m in modulos.CATALOGO["ingecad"]}
assert spec.commands["GEODRAWFRONT"] is orden.cmd_frente
assert spec.commands["GEODRAWBACK"] is orden.cmd_fondo
botones = [t.command for t in spec.toolbar]
i = botones.index("GEODRAWFRONT"); assert botones[i + 1] == "GEODRAWBACK", botones
assert all(t.icon and Path(t.icon).exists() for t in spec.toolbar if t.command.startswith("GEODRAW"))
assert i in barra.cortes(botones), "el orden de dibujo es un tema propio de la barra"
assert "GEODRAWFRONT" in yag.DESCRIPCIONES and "GEODRAWBACK" in yag.DESCRIPCIONES


def comandos_menu(items):
    for it in items:
        sub = getattr(it, "items", None)
        if sub:
            yield from comandos_menu(sub)
        elif getattr(it, "command", None):
            yield it.command


assert {"GEODRAWFRONT", "GEODRAWBACK"} <= set(comandos_menu(spec.menu))
import json
ui = json.loads((Path(lp.spec.i18n_dir) / "es" / "ui.json").read_text())
assert ui["Bring to front (DRAWORDER)"] == "Traer al frente (ALFRENTE)"
assert ui["Send to back (DRAWORDER)"] == "Enviar al fondo (ALFONDO)"

# -- con el módulo apagado no queda nada
est = modulos.estado("ingecad"); real = modulos.estado
modulos.estado = lambda prog: {**est, "orden": False}
try:
    apagado = import_module("ingecad_plugin_geocad").construir_spec()
finally:
    modulos.estado = real
assert not any(t.command.startswith("GEODRAW") for t in apagado.toolbar)
assert "GEODRAWFRONT" not in apagado.commands
assert not {"GEODRAWFRONT", "GEODRAWBACK"} & set(comandos_menu(apagado.menu))

# -- los botones llaman a la orden de IngeCAD
from core.draworder import DrawOrderCommand, order_groups

doc = Document.new(); hist = History(doc); log = []
msp = doc.doc.modelspace()
linea = msp.add_line((0, 0), (10, 10))
poli = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)], close=True)
somb = msp.add_hatch(color=3); somb.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
somb.set_solid_fill(color=3)
texto = msp.add_text("ALFA", height=2.5, dxfattribs={"insert": (2, 2)})
mtexto = msp.add_mtext("BETA", dxfattribs={"insert": (4, 4), "char_height": 2.5})
doc.doc.blocks.new("B1").add_circle((0, 0), 1)
bloque = msp.add_blockref("B1", (5, 5))
todos = [linea, poli, somb, texto, mtexto, bloque]


class Ventana:
    """Hace lo que hace la ventana de IngeCAD (MainWindow._draworder)."""
    def __init__(self, elegidos):
        self.elegidos, self.document = elegidos, doc

    def _draworder(self, modo):
        hist.execute(DrawOrderCommand(self.elegidos, modo))


def ctx_con(host):
    return types.SimpleNamespace(host=host, echo=log.append)


g = lambda e: order_groups(msp).get(e.dxf.handle, 0)
orden.cmd_fondo(ctx_con(Ventana([somb, texto])))
assert g(somb) == -1 and g(texto) == -1 and g(linea) == 0, order_groups(msp)
orden.cmd_frente(ctx_con(Ventana([texto, mtexto, bloque, poli])))
assert g(texto) == g(mtexto) == g(bloque) == g(poli) == 1 and g(somb) == -1
hist.undo(); assert g(texto) == -1 and g(bloque) == 0 and g(poli) == 0
hist.undo(); assert order_groups(msp) == {}
orden.cmd_fondo(ctx_con(Ventana([somb]))); orden.cmd_frente(ctx_con(Ventana([texto, mtexto])))

# -- en pantalla: cada tipo cae en su grupo (fondo debajo de todo, frente encima)
try:
    import core.window_colors  # noqa: F401  (lee los colores con Qt)
except ImportError:                      # sin Qt: el fondo oscuro de siempre
    sys.modules["core.window_colors"] = types.SimpleNamespace(background=lambda espacio: "#212830")
from render.backend import TolerantFrontend, TolerantRenderContext, VertexBackend, frontend_config

backend = VertexBackend(0.01, order_groups(msp))
import inspect
config = (frontend_config(0.01, doc) if len(inspect.signature(frontend_config).parameters) > 1
          else frontend_config(0.01))        # IngeCAD 0.6.5: sin el documento
front = TolerantFrontend(TolerantRenderContext(doc.doc), backend, config)
front._host_document = doc
front.draw_entities(msp)
grupos = {}
for b in backend.buckets.values():
    for dueño in b.lines_owner + b.triangles_owner + b.points_owner:
        grupos.setdefault(dueño, set()).add(b.group)
assert grupos[somb.dxf.handle] == {-1}, grupos
assert grupos[texto.dxf.handle] == {1} and grupos[mtexto.dxf.handle] == {1}, grupos
assert grupos[linea.dxf.handle] == {0} and grupos[bloque.dxf.handle] == {0}, grupos

# -- 3.16.2: la pantalla pinta por grupos (fondo, normal, frente); antes las
# líneas quedaban siempre encima de rellenos y textos
from render import backend as RB, batches as RBA
orden.instalar(); orden.instalar()                       # una sola vez
assert RB.pack._puente_fabrica is orden._envolver_pack and RBA.pack._puente_fabrica is orden._envolver_pack
assert RBA.Batch.visible_runs._puente_original.__name__ == "visible_runs"
assert not hasattr(RBA.Batch.visible_runs._puente_original, "_puente_original")

d2 = Document.new(); m2 = d2.doc.modelspace()
roja = m2.add_line((0, 0), (10, 10), dxfattribs={"color": 1})
azul = m2.add_lwpolyline([(0, 10), (10, 0)], dxfattribs={"color": 5})
gruesa = m2.add_line((0, 5), (10, 5), dxfattribs={"color": 4, "lineweight": 100})
s2 = m2.add_hatch(color=2); s2.paths.add_polyline_path([(2, 2), (8, 2), (8, 8), (2, 8)], is_closed=True)
t2 = m2.add_text("ABC", height=2, dxfattribs={"insert": (3, 4), "color": 6})
nombre = {roja.dxf.handle: "roja", azul.dxf.handle: "azul", gruesa.dxf.handle: "gruesa",
          s2.dxf.handle: "sombreado", t2.dxf.handle: "texto"}


def escena():
    be = VertexBackend(0.01, order_groups(m2))
    fr = TolerantFrontend(TolerantRenderContext(d2.doc), be, frontend_config(0.01, d2) if
                          len(inspect.signature(frontend_config).parameters) > 1 else frontend_config(0.01))
    fr._host_document = d2
    fr.draw_entities(m2)
    return RB.pack(be.buckets, None)


class Nada:
    def bind(self): pass
    def release(self): pass
    def setUniformValue(self, *a): pass


def pintado(sc):
    """El orden en que la pantalla pinta cada objeto (su primer trazo)."""
    llamadas = []
    tanda_de = {4: "triangles", 1: "lines", 0: "points"}
    gl = types.SimpleNamespace(glDrawArrays=lambda modo, a, n: llamadas.append((tanda_de[modo], a, n)))
    vp = types.SimpleNamespace(_scene=sc, _view_world_rect=lambda: (-1e9, -1e9, 1e9, 1e9),
                               view=types.SimpleNamespace(scale=50.0), _program=Nada(), _loc_mvp=0,
                               _scene_bufs={t: (Nada(), None, 0) for t in ("triangles", "lines", "points", "thick")})
    def thick(_vp, _gl, _mvp, _rect, _buf, parte):
        llamadas.extend(("thick", r.first, r.count) for r in parte.ranges)
    orden.pintar(vp, gl, None, sc._geocad_cortes, RBA.Batch.visible_runs._puente_original, thick)
    vistos = []
    for tanda, a, n in llamadas:
        for h, rangos in sc.handle_ranges.items():
            if h in nombre and nombre[h] not in vistos and any(
                    t == tanda and f < a + n and a < f + c for t, f, c in rangos):
                vistos.append(nombre[h])
    return vistos


def ordenar(ents, modo):
    DrawOrderCommand(ents, modo).do(d2)


sc = escena(); assert sc._geocad_cortes is None, "sin orden: IngeCAD pinta como siempre"
ordenar([roja, azul], "back")
sc = escena(); p = pintado(sc); print("roja y azul al fondo:", p)
assert set(p[:2]) == {"roja", "azul"} and p.index("sombreado") > 1 and p.index("texto") > 1, p
ordenar([t2], "front")
p = pintado(escena()); print("texto al frente:", p); assert p[-1] == "texto", p
ordenar([s2], "front")
p = pintado(escena()); print("sombreado al frente:", p)
assert p.index("gruesa") < p.index("sombreado") and p.index("gruesa") < p.index("texto"), p
ordenar([gruesa], "front")
p = pintado(escena()); print("gruesa al frente:", p)
assert p.index("sombreado") < p.index("gruesa") and p.index("texto") < p.index("gruesa"), p
# todo lo dibujado se pinta una sola vez: ni falta ni sobra
sc = escena(); total = {"triangles": 0, "lines": 0, "points": 0, "thick": 0}
gl_cuenta = []
vp_cuenta = types.SimpleNamespace(_scene=sc, _view_world_rect=lambda: (-1e9, -1e9, 1e9, 1e9),
    view=types.SimpleNamespace(scale=50.0), _program=Nada(), _loc_mvp=0,
    _scene_bufs={t: (Nada(), None, 0) for t in total})
orden.pintar(vp_cuenta, types.SimpleNamespace(glDrawArrays=lambda m, a, n: gl_cuenta.append((m, n))), None,
             sc._geocad_cortes, RBA.Batch.visible_runs._puente_original,
             lambda _v, _g, _m, _r, _b, parte: gl_cuenta.extend(("k", r.count) for r in parte.ranges))
for modo, tanda in ((4, "triangles"), (1, "lines"), (0, "points")):
    assert sum(n for m, n in gl_cuenta if m == modo) == sum(n for _a, n in RBA.Batch.visible_runs._puente_original(
        getattr(sc, tanda), (-1e9, -1e9, 1e9, 1e9), 50.0, 2.0)), tanda
assert sum(n for m, n in gl_cuenta if m == "k") == sum(r.count for r in sc.thick.ranges)
# ya pintadas por grupos, IngeCAD no las vuelve a pintar (y el cuadro siguiente sí)
orden._pintadas.update({id(sc.lines)})
assert sc.lines.visible_runs((-1e9, -1e9, 1e9, 1e9), 50.0, 2.0) == []
orden._pintadas.clear(); assert sc.lines.visible_runs((-1e9, -1e9, 1e9, 1e9), 50.0, 2.0)
# con el módulo apagado, la escena sale sin cortes
modulos.estado = lambda prog: {**est, "orden": False}
try:
    assert escena()._geocad_cortes is None
finally:
    modulos.estado = real

# -- el DXF lleva la tabla de orden para AutoCAD
salida = Path(tempfile.mkdtemp()) / "orden.dxf"
doc.doc.saveas(salida)
import ezdxf
otra = ezdxf.readfile(salida).modelspace()
tabla = dict(otra.get_redraw_order())
assert int(tabla[somb.dxf.handle], 16) < int(linea.dxf.handle, 16) < int(tabla[texto.dxf.handle], 16)

# -- 3.16.1: al terminar, la pantalla regenerada también cuando la orden pide
# los objetos (la DRAWORDER de IngeCAD sólo refresca lo tocado, sin regen)
class Herramienta:
    name = "DRAWORDER"
    def __init__(self): self.mode, self.aplicada = None, []
    def _apply(self, modo): self.aplicada.append(modo)


class VentanaQuePide:
    """MainWindow._draworder sin nada elegido: arranca la orden y fija el modo."""
    def __init__(self):
        self.tools, self.regens = types.SimpleNamespace(tool=None), 0
    def regen_in_memory(self): self.regens += 1
    def _draworder(self, modo):
        self.tools.tool = Herramienta(); self.tools.tool.mode = modo
    def _invoke_command(self, nombre):
        assert nombre == "DRAWORDER"; self.tools.tool = Herramienta()


v = VentanaQuePide(); orden.cmd_fondo(ctx_con(v))
assert v.regens == 0, "todavía no eligió nada"
v.tools.tool._apply("back"); assert v.tools.tool.aplicada == ["back"] and v.regens == 1
otra_vez = Herramienta(); v.tools.tool = otra_vez       # el Draw Order propio de IngeCAD
otra_vez._apply("front"); assert v.regens == 1, "no se toca la orden de IngeCAD"
v = VentanaQuePide(); v._draworder = None               # IngeCAD sin el atajo
orden.cmd_frente(ctx_con(v)); v.tools.tool._apply("front"); assert v.regens == 1
v = VentanaQuePide(); v.tools.tool = types.SimpleNamespace(name="LINE", _apply=lambda m: None)
v._draworder = lambda modo: None                        # con elegidos: IngeCAD ya regeneró
orden.cmd_frente(ctx_con(v)); v.tools.tool._apply("x"); assert v.regens == 0

# -- sin el atajo de la ventana: la orden DRAWORDER; sin ventana, el aviso
llamadas = []
orden.cmd_frente(ctx_con(types.SimpleNamespace(_invoke_command=llamadas.append)))
assert llamadas == ["DRAWORDER"], llamadas
log.clear(); orden.cmd_fondo(ctx_con(None)); assert "0.6.5" in log[0], log

print("TODO OK orden de dibujo")
