"""ASPECTOIMAGEN para IngeCAD (módulo «georref», 3.31.0): fondo transparente
por la oscuridad del píxel (cuánto blanco se borra), líneas como están, en
negativo o de un color, opacidad. El original no se toca: copia PNG junto al
dibujo, la imagen pasa a usarla con sus valores guardados (XDATA), se puede
volver al original y U lo deshace."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import json, os, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from PIL import Image
from core.commands import History
from core.document import Document
from core.select import GeometryIndex
from core.plugins import load_plugin
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
A = import_module("ingecad_plugin_geocad.aspecto")
UI = import_module("ingecad_plugin_geocad.aspecto_ui")
G = import_module("ingecad_plugin_geocad.georref")
mods = import_module("ingecad_plugin_geocad.modulos")
yag = import_module("ingecad_plugin_geocad.yaguarete")
barra = import_module("ingecad_plugin_geocad.barra")
plugin = import_module("ingecad_plugin_geocad")

# ------------------------------------------------------------- 1. orden, barra y menú
spec = plugin.construir_spec()
assert spec.tools["ASPECTOIMAGEN"] is A.AspectoImagenTool
assert spec.aliases["IMAGEASPECT"] == "ASPECTOIMAGEN"
ordenes = [h[0] for h in yag.HERRAMIENTAS]
assert ordenes.index("ASPECTOIMAGEN") == ordenes.index("EXPORTARGEO") + 1    # junto a las de imágenes
assert yag.TEMAS["ASPECTOIMAGEN"] == yag.TEMAS["GEORREF"] == "imagenes"
assert "ASPECTOIMAGEN" in yag.DESCRIPCIONES and "ASPECTOIMAGEN" in yag.ETIQUETAS
assert barra._iconos_propios()["ASPECTOIMAGEN"].is_file()
dibujo_menu = next(s for s in spec.menu if getattr(s, "label", "") == "Drawing")
cmds = [getattr(i, "command", "") for i in dibujo_menu.items]
assert cmds.index("ASPECTOIMAGEN") == cmds.index("EXPORTARGEO") + 1
icono = Path(plugin.__file__).parent / "iconos" / "aspecto_imagen.png"
assert icono.is_file() and Image.open(icono).size == (24, 24)
ui = json.loads((Path(plugin.__file__).parent / "i18n" / "es" / "ui.json").read_text("utf-8"))
assert ui["Image appearance (ASPECTOIMAGEN)"] == "Aspecto de la imagen (ASPECTOIMAGEN)"
mods.poner("ingecad", "georref", False)
s2 = plugin.construir_spec()
assert "ASPECTOIMAGEN" not in s2.tools
mods.poner("ingecad", "georref", True)
print("ok botones")

# ------------------------------------------------------------- 2. los valores
assert A.normalizar({}) == A.DEFECTO
v = A.normalizar({"blanco": 500, "opacidad": -3, "lineas": "raro", "color": "zz", "otro": 1})
assert v["blanco"] == A.BLANCO_MAX and v["opacidad"] == A.OPACIDAD_MIN
assert v["lineas"] == "como" and v["color"] == A.DEFECTO["color"] and "otro" not in v
assert A.normalizar({"color": "00aa11"})["color"] == "#00AA11"
assert A.rgb("#00AA11") == (0, 170, 17)
assert "negativo" in A.describir({"lineas": "negativo"})
assert "blanco que se borra 25 %" in A.describir({})
print("ok valores")

# ------------------------------------------------------------- 3. los píxeles
#   negro, gris medio, papel amarillento claro, blanco, y un rojo semitransparente
src = Image.new("RGBA", (5, 1))
src.putdata([(0, 0, 0, 255), (128, 128, 128, 255), (236, 223, 190, 255),
             (255, 255, 255, 255), (255, 0, 0, 128)])
def px(valores, im=src):
    hecha = A.procesar(im, valores)
    return [hecha.getpixel((x, 0)) for x in range(hecha.width)]

p = px({"transparente": True, "blanco": 0})                 # alfa = oscuridad
assert p[0] == (0, 0, 0, 255) and p[3][3] == 0
assert abs(p[1][3] - 127) <= 1                              # gris medio, medio transparente: borde suave
assert 0 < p[2][3] < 40                                     # el papel amarillento casi no se ve...
p = px({"transparente": True, "blanco": 25})
assert p[2][3] == 0 and p[0][3] == 255                      # ...y con 25 % se borra del todo
assert p[1][3] > 0                                          # el gris sigue
p = px({"transparente": False})
assert [q[3] for q in p] == [255, 255, 255, 255, 128]       # sin transparencia: sólo la propia
assert p[2][:3] == (236, 223, 190)                          # como están: el color no cambia
p = px({"transparente": False, "lineas": "negativo"})
assert p[0][:3] == (255, 255, 255) and p[3][:3] == (0, 0, 0)
p = px({"transparente": True, "blanco": 0, "lineas": "color", "color": "#00FF00"})
assert p[0] == (0, 255, 0, 255) and p[1][:3] == (0, 255, 0)
p = px({"transparente": False, "opacidad": 50})
assert abs(p[0][3] - 128) <= 1 and abs(p[4][3] - 64) <= 1
gris = Image.new("L", (3, 3), 0)                            # escala de grises y paleta también
assert A.procesar(gris, {}).mode == "RGBA" and A.procesar(gris.convert("P"), {}).size == (3, 3)
assert max(A.reducida(Image.new("RGB", (2000, 1000)), 400).size) == 400
#   3.31.2: por franjas, con su avance (la barra de progreso): igual que de una vez
import random
random.seed(7)
alta = Image.new("RGBA", (37, A.FILAS_FRANJA * 2 + 41))
alta.putdata([tuple(random.randrange(256) for _ in range(4)) for _ in range(alta.width * alta.height)])
for valores in ({}, {"lineas": "negativo", "opacidad": 60}, {"lineas": "color", "blanco": 0},
                {"transparente": False, "lineas": "color", "color": "#123456"}):
    hecho = [0.0]
    por_franjas = A.procesar(alta, valores, hecho)
    assert hecho == [1.0]
    viejo = A.FILAS_FRANJA; A.FILAS_FRANJA = 10 ** 6
    de_una = A.procesar(alta, valores); A.FILAS_FRANJA = viejo
    assert por_franjas.tobytes() == de_una.tobytes()
assert A.estimar("guardar", 0.1) == 1.0 and A.estimar("abrir", 1000) > 1
A.medir("guardar", 40, 8.0); assert abs(A._ritmo["guardar"] - 0.2) < 1e-9
GP = import_module("ingecad_plugin_geocad.georref_progreso")
with GP.Progreso(None, "ASPECTOIMAGEN") as prog:                      # sin Qt: corre directo
    hecho = [0.0]
    assert prog.trabajo("2/4", lambda: A.procesar(src, {}, hecho), 0, 15, 35, hecho=hecho).size == (5, 1)
    assert hecho == [1.0]
    prog.regeneracion(None, None, 75, 25, etapa="4/4")
f = UI.fondo_previa((30, 20), "q")
assert f.size == (30, 20) and f.getpixel((0, 0)) != f.getpixel((10, 0))   # cuadriculado
assert UI.ventana(None, "x.png", {}, False) is None                         # sin Qt, sin ventana
print("ok pixeles")

# ------------------------------------------------------------- 4. la orden
d = Path(tempfile.mkdtemp()) / "obra"; d.mkdir()
plano = d / "mensura.jpg"
im = Image.new("RGB", (60, 40), (236, 223, 190))
for x in range(5, 55):
    im.putpixel((x, 20), (10, 10, 10))
im.save(plano, quality=95)
original_bytes = plano.read_bytes()

doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
doc.path = str(d / "lote12.dwg")
ddef = doc.doc.add_image_def(filename=str(plano), size_in_pixel=(60, 40))
img = msp.add_image(ddef, insert=(1000, 2000), size_in_units=(60, 40))
msgs, fin, pedidos, respuesta = [], [], [], [None]


class Ctrl:
    def __init__(self):
        self.window = types.SimpleNamespace(document=doc)
        self.index = GeometryIndex(doc)
        self.selection = set()
        self._pick_tolerance = 0.2
    def pick_entity(self, p):
        h = self.index.pick(tuple(p), self._pick_tolerance)
        return self.index.entity(h) if h else None


def falsa_ventana(parent, original, valores, con_aspecto):
    pedidos.append((Path(original), dict(valores), con_aspecto))
    return respuesta[0]
A.ventana = falsa_ventana


def herramienta(selection=()):
    msgs.clear(); fin.clear(); pedidos.clear()
    ctrl = Ctrl(); ctrl.selection = set(selection)
    ctx = ToolContext(execute=hist.execute, prompt=lambda t: None, echo=msgs.append,
                      finish=lambda: fin.append(1), services=ctrl)
    t = A.AspectoImagenTool(ctx); t.start()
    return t

dentro = G.aplicar(G.coef_imagen(img), (30, -20))
t = herramienta()
assert t.resaltado(dentro)["cursor"]                        # se ilumina al pasar
respuesta[0] = None
t.on_point(dentro)                                          # Cancelar
assert fin and any("cancelado" in m for m in msgs) and img.image_def.dxf.filename == str(plano)
assert pedidos[0] == (plano, A.DEFECTO, False)              # la primera vez: valores iniciales
t = herramienta(); t.on_point((-500, -500)); assert not fin # nada ahí: sigue pidiendo

elegidos = {"transparente": True, "blanco": 30, "lineas": "color", "color": "#0000FF", "opacidad": 80}
respuesta[0] = {"accion": "aceptar", "valores": elegidos}
herramienta({img.dxf.handle})                               # elegida de antes
copia = d / "lote12_imagenes" / "mensura_aspecto.png"
assert fin and copia.is_file()
assert img.image_def.dxf.filename == str(copia)
assert plano.read_bytes() == original_bytes                 # el original NUNCA se toca
assert img.dxf.flags & img.USE_TRANSPARENCY                 # si no, el fondo se ve negro
hecha = Image.open(copia)
assert hecha.mode == "RGBA" and hecha.size == (60, 40)
assert hecha.getpixel((0, 0))[3] == 0                       # el papel se borró
assert hecha.getpixel((30, 20))[:3] == (0, 0, 255) and 150 < hecha.getpixel((30, 20))[3] < 210
assert A.leer(img) == (A.normalizar(elegidos), str(plano))  # los valores quedan con la imagen
assert any("Copia:" in m and "el original no se toca" in m for m in msgs)

respuesta[0] = {"accion": "aceptar", "valores": dict(elegidos, lineas="negativo")}
herramienta({img.dxf.handle})                               # otra vez: desde el ORIGINAL
assert pedidos[0] == (plano, A.normalizar(elegidos), True)  # abre con los guardados
copia2 = d / "lote12_imagenes" / "mensura_aspecto_2.png"    # no pisa la anterior (U vuelve a ella)
assert img.image_def.dxf.filename == str(copia2) and copia.is_file()
assert A.leer(img)[0]["lineas"] == "negativo" and A.leer(img)[1] == str(plano)
hist.undo()                                                 # U: la copia anterior y sus valores
assert img.image_def.dxf.filename == str(copia) and A.leer(img)[0]["lineas"] == "color"

respuesta[0] = {"accion": "original"}
herramienta({img.dxf.handle})                               # Volver al original
assert img.image_def.dxf.filename == str(plano) and A.leer(img) is None
assert copia.is_file()                                      # la copia queda en el disco
assert any("vuelve a su original" in m for m in msgs)
hist.undo()
assert img.image_def.dxf.filename == str(copia) and A.leer(img)[0]["color"] == "#0000FF"
hist.undo()                                                 # U: como estaba al principio
assert img.image_def.dxf.filename == str(plano) and A.leer(img) is None
assert not (img.dxf.flags & img.USE_TRANSPARENCY)
herramienta({img.dxf.handle})                               # «original» sin aspecto: nada
assert any("ya usa su archivo original" in m for m in msgs)
assert pedidos[0][1] == A.normalizar(dict(elegidos, lineas="negativo"))   # los últimos usados

# los valores sobreviven a guardar y abrir el DXF
respuesta[0] = {"accion": "aceptar", "valores": elegidos}
herramienta({img.dxf.handle})
dxf = d / "lote12.dxf"; doc.doc.saveas(dxf)
otra = next(iter(ezdxf.readfile(dxf).modelspace().query("IMAGE")))
assert A.leer(otra) == (A.normalizar(elegidos), str(plano))
largo = "/x" * 300                                          # ruta larga: en trozos de XDATA
assert all(len(t[1]) <= 255 for t in A.etiquetas({}, largo))
otra.set_xdata(A.APPID, A.etiquetas({}, largo)); assert A.leer(otra)[1] == largo

ddef.dxf.filename = str(d / "no_existe.jpg")                # original perdido
img2 = msp.add_image(ddef, insert=(0, 0), size_in_units=(6, 4))
herramienta({img2.dxf.handle}); assert any("no se encuentra el archivo original" in m for m in msgs)
print("ok orden")

# ------------------------------------------------------------- 5. el recorrido de Fernando (3.31.1)
#   negativo -> EXPORTARGEO -> INSERTARGEO en otro dibujo: antes salía un rectángulo
#   blanco (la IMAGE sin «usar transparencia» mostraba los píxeles invisibles)
IG = import_module("ingecad_plugin_geocad.imagengeo")
PI = import_module("ingecad_plugin_geocad.pegarimagen")
G.crs_dibujo = lambda: ""
ddef.dxf.filename = str(plano)
respuesta[0] = {"accion": "aceptar", "valores": dict(elegidos, lineas="negativo", opacidad=100)}
herramienta({img.dxf.handle})
neg = Path(img.image_def.dxf.filename)
assert Image.open(neg).getpixel((0, 0))[3] == 0                    # el papel, invisible
afuera = Path(tempfile.mkdtemp())
hechos = IG.exportar(img, afuera / "negativo transparente.png", neg)
assert IG.leer(hechos[0])["alfa"] and not IG.leer(plano)["alfa"]
cmd = IG.insertar_command(hechos[0], 60, 40, IG.leer(hechos[0])["coef"], True)
hist.execute(cmd)
assert cmd.entity.dxf.flags & cmd.entity.USE_TRANSPARENCY
hist.undo()
cmd = IG.insertar_command(plano, 60, 40, (0, 1, 0, 0, 0, -1))      # un JPG: como antes
hist.execute(cmd); assert not (cmd.entity.dxf.flags & cmd.entity.USE_TRANSPARENCY); hist.undo()
cmd = PI.comando(hechos[0], 60, 40, (0, 0), (60, 0))               # PEGARIMAGEN de un archivo
hist.execute(cmd); assert cmd.entity.dxf.flags & cmd.entity.USE_TRANSPARENCY; hist.undo()
cmd = PI.comando(plano, 60, 40, (0, 0), (60, 0))
hist.execute(cmd); assert not (cmd.entity.dxf.flags & cmd.entity.USE_TRANSPARENCY); hist.undo()
#   ASPECTOIMAGEN sobre ese negativo: lo blanco se borra entero, y se avisa
ddef2 = doc.doc.add_image_def(filename=str(hechos[0]), size_in_pixel=(60, 40))
img3 = msp.add_image(ddef2, insert=(5000, 0), size_in_units=(60, 40))
respuesta[0] = {"accion": "aceptar", "valores": A.DEFECTO}
herramienta({img3.dxf.handle})
assert any(m.startswith("Atención: la imagen quedó invisible") for m in msgs)
respuesta[0] = {"accion": "aceptar", "valores": dict(A.DEFECTO, transparente=False)}
herramienta({img3.dxf.handle})                                    # sin fondo transparente: se ve
assert not any(m.startswith("Atención") for m in msgs)
print("ok recorrido")

print("TODO OK ASPECTO")
