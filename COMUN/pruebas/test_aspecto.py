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
spec = plugin.construir_spec(completo=True)
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
s2 = plugin.construir_spec(completo=True)
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
#   3.83.0: contraste de las líneas (la «tinta» se multiplica) e imagen final sobre blanco
v = A.normalizar({"contraste": 9999}); assert v["contraste"] == A.CONTRASTE_MAX
assert A.normalizar({"contraste": 3})["contraste"] == 100 and A.normalizar({})["final"] is False
assert "contraste de las líneas 200 %" in A.describir({"contraste": 200})
tenue = Image.new("RGBA", (4, 1))
tenue.putdata([(255, 255, 255, 255), (200, 200, 200, 255), (255, 160, 160, 255), (0, 0, 0, 255)])
p = px({"transparente": False, "contraste": 200}, tenue)
assert p[0][:3] == (255, 255, 255)                          # el papel sigue blanco
assert p[1][:3] == (145, 145, 145)                          # el gris tenue, el doble de tinta
assert p[2][:3] == (255, 65, 65)                            # una línea roja tenue: más roja
assert p[3][:3] == (0, 0, 0)                                # lo negro no puede ser más negro
assert px({"transparente": False, "contraste": 100}, tenue) == px({"transparente": False}, tenue)
a1 = px({"transparente": True, "blanco": 0}, tenue)[1][3]
a2 = px({"transparente": True, "blanco": 0, "contraste": 300}, tenue)[1][3]
assert a2 > 2 * a1                                          # con fondo transparente: más opaca
assert px({"transparente": True, "blanco": 25, "contraste": 400})[2][3] == 0   # el papel amarillento sigue borrado
p = px({"transparente": True, "blanco": 0, "lineas": "color", "color": "#0000FF", "final": True}, tenue)
assert all(q[3] == 255 for q in p)                          # la final: opaca
assert p[0][:3] == (255, 255, 255) and p[3][:3] == (0, 0, 255)   # papel blanco, línea azul
assert 0 < p[1][0] < 255 and p[1][2] == 255                 # lo tenue, azul claro sobre blanco
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


fondos_pedidos = []
def falsa_ventana(parent, original, valores, con_aspecto, fondo=False):
    pedidos.append((Path(original), dict(valores), con_aspecto))
    fondos_pedidos.append(fondo)
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

# ------------------------------------------------------------- 6. fondo blanco en su capa (3.82.0)
#   Fernando: «volver al fondo blanco cuando lo necesitemos», con una capa que
#   se prende o se apaga en vez de rellenar los píxeles
from core.draworder import order_groups
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
doc.path = str(d / "lote13.dwg")
otra_linea = msp.add_line((0, 0), (1, 1))                           # algo dibujado antes
ddef = doc.doc.add_image_def(filename=str(plano), size_in_pixel=(60, 40))
img = msp.add_image(ddef, insert=(1000, 2000), size_in_units=(60, 40))
assert A.fondo_de(img) is None
respuesta[0] = {"accion": "aceptar", "valores": A.DEFECTO, "fondo_blanco": True}
herramienta({img.dxf.handle})
assert fondos_pedidos[-1] is False                                  # la ventana: sin fondo todavía
f = A.fondo_de(img)
assert f is not None and f.dxf.layer == A.CAPA_FONDO and A.CAPA_FONDO in doc.doc.layers
assert f.dxf.solid_fill and f.rgb == (255, 255, 255)               # blanco verdadero, no el color 7
xs = sorted({round(v[0], 6) for v in f.paths[0].vertices}); ys = sorted({round(v[1], 6) for v in f.paths[0].vertices})
assert xs[0] <= 1000 and xs[-1] >= 1059 and ys[0] <= 2000 and ys[-1] >= 2039   # el contorno de la imagen
grupos = order_groups(msp)
assert grupos.get(f.dxf.handle) == -1 and img.dxf.handle not in grupos     # al fondo, debajo de la imagen
assert any("capa FONDO_IMAGENES" in m for m in msgs)
assert Path(img.image_def.dxf.filename).name == "mensura_aspecto.png"      # el aspecto, igual que siempre
copia_fondo = img.image_def.dxf.filename
hist.undo()                                                         # un U: aspecto y fondo juntos
assert A.fondo_de(img) is None and A.CAPA_FONDO not in doc.doc.layers
assert img.image_def.dxf.filename == str(plano) and not order_groups(msp)
hist.redo()
assert A.fondo_de(img) is not None and img.image_def.dxf.filename == copia_fondo
#   la ventana lo ve tildado; sin cambiar el aspecto, sólo se quita el fondo (sin rehacer la copia)
respuesta[0] = {"accion": "aceptar", "valores": A.DEFECTO, "fondo_blanco": False}
herramienta({img.dxf.handle})
assert fondos_pedidos[-1] is True
assert A.fondo_de(img) is None and img.image_def.dxf.filename == copia_fondo
assert any("Fondo blanco quitado" in m for m in msgs)
assert f.dxf.handle not in order_groups(msp)                        # sin rastro en el orden de dibujo
hist.undo(); assert A.fondo_de(img) is not None                     # U lo devuelve
#   la imagen se movió: el fondo se rehace al contorno nuevo (uno solo)
img.dxf.insert = (3000, 4000)
respuesta[0] = {"accion": "aceptar", "valores": dict(A.DEFECTO, opacidad=60), "fondo_blanco": True}
herramienta({img.dxf.handle})
fs = [h for h in msp.query("HATCH") if h.dxf.layer == A.CAPA_FONDO]
assert len(fs) == 1 and min(v[0] for v in fs[0].paths[0].vertices) >= 2999
hist.undo()
fs = [h for h in msp.query("HATCH") if h.dxf.layer == A.CAPA_FONDO]
assert len(fs) == 1 and fs[0] is f                                  # vuelve el de antes
#   sin la clave en la respuesta (ventana vieja) el fondo queda como estaba
respuesta[0] = {"accion": "aceptar", "valores": dict(A.DEFECTO, opacidad=70)}
herramienta({img.dxf.handle}); assert A.fondo_de(img) is not None
#   «Volver al original» con fondo: los dos juntos; el fondo queda
respuesta[0] = {"accion": "original", "fondo_blanco": True}
herramienta({img.dxf.handle})
assert img.image_def.dxf.filename == str(plano) and A.fondo_de(img) is not None
#   imagen sin aspecto: «original» + fondo sólo pone o quita el fondo
respuesta[0] = {"accion": "original", "fondo_blanco": False}
herramienta({img.dxf.handle}); assert A.fondo_de(img) is None
assert not any("ya usa su archivo original" in m for m in msgs)
#   una imagen enviada al fondo vuelve al orden normal (si no, su fondo la taparía)
from core.draworder import DrawOrderCommand
hist.execute(DrawOrderCommand([img], "back"))
assert order_groups(msp)[img.dxf.handle] == -1
respuesta[0] = {"accion": "original", "fondo_blanco": True}
herramienta({img.dxf.handle})
g = order_groups(msp)
assert g[A.fondo_de(img).dxf.handle] == -1 and img.dxf.handle not in g
assert any("vuelve al orden normal" in m for m in msgs)
hist.undo(); assert order_groups(msp)[img.dxf.handle] == -1 and A.fondo_de(img) is None
#   imagen recortada: el fondo sigue el recorte
hist.execute(DrawOrderCommand([img], "front")); hist.undo()
img.set_boundary_path([(10, 10), (50, 10), (30, 35)])
respuesta[0] = {"accion": "original", "fondo_blanco": True}
herramienta({img.dxf.handle})
assert len(A.fondo_de(img).paths[0].vertices) == 3
#   se guarda con el DXF y se vuelve a encontrar al abrirlo
dxf = d / "lote13.dxf"; doc.doc.saveas(dxf)
abierto = ezdxf.readfile(dxf).modelspace()
otra = next(iter(abierto.query("IMAGE")))
assert A.fondo_de(otra) is not None and A.fondo_de(otra).dxf.layer == A.CAPA_FONDO
assert order_groups(abierto)[A.fondo_de(otra).dxf.handle] == -1
print("ok fondo blanco")

# ------------------------------------------------------------- 7. entregar imagen final (3.83.0)
#   Fernando: «para entregar el trabajo terminado vamos a hacer una captura del
#   resultado y transformar todo en una imagen nueva»
respuesta[0] = {"accion": "aceptar", "valores": A.DEFECTO, "fondo_blanco": True}
herramienta({img.dxf.handle}); assert A.fondo_de(img) is not None
antes_final = img.image_def.dxf.filename
elegidos = dict(A.DEFECTO, lineas="color", color="#0000FF", contraste=250)
respuesta[0] = {"accion": "final", "valores": elegidos, "fondo_blanco": True}
herramienta({img.dxf.handle})
final = Path(img.image_def.dxf.filename)
assert final.name.startswith("mensura_final") and final.suffix == ".png" and final.is_file()
hecha = Image.open(final)
assert hecha.mode == "RGB"                                  # opaca: sin canal alfa
assert hecha.getpixel((2, 2)) == (255, 255, 255)            # el papel, blanco
assert hecha.getpixel((30, 20))[2] == 255 and hecha.getpixel((30, 20))[0] < 60   # la línea, azul fuerte
assert A.fondo_de(img) is None                              # el fondo de la capa ya no hace falta
assert A.leer(img)[0]["final"] and A.leer(img)[0]["contraste"] == 250 and A.leer(img)[1] == str(plano)
assert plano.read_bytes() == original_bytes                 # el original NUNCA se toca
assert any("Imagen final" in m and str(final) in m for m in msgs)
assert A._ultimos[0]["final"] is False                      # la próxima imagen no sale «final»
hist.undo()                                                 # un U: la imagen y su fondo como estaban
assert img.image_def.dxf.filename == antes_final and A.fondo_de(img) is not None
hist.redo(); assert Path(img.image_def.dxf.filename) == final and A.fondo_de(img) is None
print("ok imagen final")

# ------------------------------------------------------------- 8. limpiar manchas (3.84.0)
#   Fernando: «un limpiador de píxeles que no pertenecen a un dibujo ... con un
#   porcentaje de admitidos a pequeñas distancias», «dando prioridad a los textos»
import numpy as np
from PIL import ImageDraw
assert A.DEFECTO["limpiar"] is False                        # apagado: nada cambia
n = A.normalizar({"limpiar": 1, "distancia": 99, "tolerancia": 1})
assert n["limpiar"] is True and n["distancia"] == A.DISTANCIA_MAX and n["tolerancia"] == A.TOLERANCIA_MIN
assert A.normalizar({"distancia": "x"})["distancia"] == A.DEFECTO["distancia"]
assert "manchas limpiadas (distancia 8 px, tolerancia 30 %)" in A.describir(dict(A.DEFECTO, limpiar=True))
assert "manchas" not in A.describir(A.DEFECTO)
sucio = Image.new("RGB", (600, 300), (238, 232, 214))       # papel amarillento
dib = ImageDraw.Draw(sucio)
dib.line((20, 150, 580, 150), fill=(0, 0, 0), width=1)       # línea fina negra
dib.line((20, 220, 580, 220), fill=(175, 175, 175), width=1) # línea tenue
dib.line((300, 20, 300, 26), fill=(0, 0, 0), width=1)        # trazo corto (7 px): se queda
dib.rectangle((40, 40, 70, 70), fill=(0, 0, 0))              # «letra»
dib.rectangle((74, 66, 75, 68), fill=(0, 0, 0))              # coma (6 px) a 4 px de la letra
polvo = [(400, 60), (450, 90), (500, 260), (120, 260)]
for x, y in polvo:
    sucio.putpixel((x, y), (40, 40, 40))
dib.rectangle((200, 80, 201, 81), fill=(20, 20, 20))         # mancha de 4 px, sola
vl = dict(A.DEFECTO, limpiar=True)                           # distancia 8, tolerancia 30: < 5,1 px
b = A.manchas(np.asarray(sucio.convert("RGBA")), A.normalizar(vl))
assert all(b[y, x] for x, y in polvo) and b[80:82, 200:202].all()
assert not b[150].any() and not b[220].any()                 # las líneas, ni la tenue
assert not b[20:27, 300].any()                               # un trazo corto no es mancha
assert not b[40:71, 40:71].any() and not b[66:69, 74:76].any()   # la letra y su coma
# la coma sola (lejos de todo) sí se va con más tolerancia; la línea nunca, ni en 50 %
b50 = A.manchas(np.asarray(sucio.convert("RGBA")), A.normalizar(dict(vl, tolerancia=50)))
assert not b50[150].any() and not b50[220].any() and not b50[66:69, 74:76].any()
# transparente: lo borrado, invisible; sin transparencia: blanco; final: blanco opaco
h = A.procesar(sucio, vl)
assert h.getpixel((400, 60))[3] == 0 and h.getpixel((300, 150))[3] > 200
h = A.procesar(sucio, dict(vl, transparente=False))
assert h.getpixel((400, 60))[:3] == (255, 255, 255) and h.getpixel((300, 150))[:3] == (0, 0, 0)
h = A.procesar(sucio, dict(vl, final=True))
assert h.getpixel((400, 60)) == (255, 255, 255, 255) and h.getpixel((5, 5)) == (255, 255, 255, 255)
assert h.getpixel((300, 150))[0] < 30 and h.getpixel((300, 150))[3] == 255
assert A.procesar(sucio, dict(vl, limpiar=False)).getpixel((400, 60))[3] > 100   # apagado: queda
# la vista previa: en rojo; reducida, la distancia se achica con ella
h = A.procesar(sucio, vl, marcar=True)
assert h.getpixel((400, 60)) == (255, 0, 0, 255) and h.getpixel((300, 150))[:3] == (0, 0, 0)
chica = sucio.resize((300, 150))
hc = A.procesar(chica, vl, escala=0.5, marcar=True)
assert hc.getpixel((150, 75))[:3] != (255, 0, 0)             # la línea, tampoco reducida
# más alta que una franja: el mismo resultado que de a pedazos no importa, es de una vez
alto = Image.new("RGB", (60, 3 * A.FILAS_FRANJA + 7), (255, 255, 255))
alto.putpixel((30, A.FILAS_FRANJA), (0, 0, 0))               # justo en el borde de franjas
assert A.procesar(alto, vl).getpixel((30, A.FILAS_FRANJA))[3] == 0
hecho = [0.0]; A.procesar(alto, vl, hecho); assert hecho[0] == 1.0
# la orden: la copia sale limpia y los valores quedan en la imagen
plano_sucio = Path(tempfile.mkdtemp()) / "sucio.png"; sucio.save(plano_sucio)
img = msp.add_image(doc.doc.add_image_def(filename=str(plano_sucio), size_in_pixel=(600, 300)),
                    insert=(9000, 0), size_in_units=(60, 30))
respuesta[0] = {"accion": "aceptar", "valores": dict(vl, distancia=10, tolerancia=40)}
herramienta({img.dxf.handle})
copia = Image.open(img.image_def.dxf.filename)
assert Path(img.image_def.dxf.filename).name.startswith("sucio_aspecto")
assert copia.getpixel((400, 60))[3] == 0 and copia.getpixel((300, 150))[3] > 200
g = A.leer(img)[0]
assert g["limpiar"] is True and g["distancia"] == 10 and g["tolerancia"] == 40
assert any("manchas limpiadas (distancia 10 px, tolerancia 40 %)" in m for m in msgs)
print("ok limpiar manchas")

# ------------------------------------------------------------- 9. después de GEORREF (3.94.1)
#   Fernando, 24/11/2026: aspecto -> Ajustar imagen (rehace la imagen) -> «Entregar
#   imagen final» rehacía el original sin deformar y lo estiraba en el marco nuevo
from ezdxf.math import Matrix44
dg = Path(tempfile.mkdtemp())
viejo = dg / "mensura.png"; Image.new("RGB", (80, 40), (255, 255, 255)).save(viejo)
img = msp.add_image(doc.doc.add_image_def(filename=str(viejo), size_in_pixel=(80, 40)),
                    insert=(12000, 0), size_in_units=(80, 40))
respuesta[0] = {"accion": "aceptar", "valores": {"transparente": True}}
herramienta({img.dxf.handle})
assert A.leer(img)[1] == str(viejo) and A.marca_vigente(img, viejo)
assert A.tamano_archivo(viejo) == (80, 40) and A.tamano_archivo(dg / "no.png") is None
rehecha = dg / "mensura_aspecto_georref.png"                # Proyectiva / Polinómica 2-3 / TPS
Image.new("RGBA", (70, 50), (0, 0, 0, 0)).save(rehecha)
hist.execute(G.GeorrefCommand(img, Matrix44(), copia=str(rehecha), tamano=(70, 50)))
assert img.image_def.dxf.filename == str(rehecha) and A.leer(img)[1] == str(viejo)
assert not A.marca_vigente(img, viejo)                      # la marca quedó vieja
respuesta[0] = {"accion": "final", "valores": {"transparente": True}}
herramienta({img.dxf.handle})
assert pedidos[0][0] == rehecha and pedidos[0][2] is False  # la ventana abre con la de hoy
final = Path(img.image_def.dxf.filename)
assert final.name.startswith("mensura_aspecto_georref") and Image.open(final).size == (70, 50)
assert tuple(img.dxf.image_size)[:2] == (70, 50) and A.leer(img)[1] == str(rehecha)
assert any("cambió después del aspecto" in m for m in msgs)
hist.undo()                                                 # U: la marca vieja vuelve, intacta
assert img.image_def.dxf.filename == str(rehecha) and A.leer(img)[1] == str(viejo)
#   Lineal / Helmert / Polinómica 1 sólo mueven la imagen: la marca sigue valiendo
hist.undo()
assert A.marca_vigente(img, viejo)
hist.execute(G.GeorrefCommand(img, Matrix44.translate(5, 5, 0)))
assert A.marca_vigente(img, viejo)
msgs.clear(); respuesta[0] = {"accion": "final", "valores": {"transparente": True}}
herramienta({img.dxf.handle})
assert pedidos[0][0] == viejo and pedidos[0][2] is True
assert not any("cambió después" in m for m in msgs)
print("ok después de GEORREF")

print("TODO OK ASPECTO")
