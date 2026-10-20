"""INSERTARGEO y EXPORTARGEO para IngeCAD (módulo «georref», 3.19.0): una
imagen con archivo de mundo o GeoTIFF entra en su lugar; una imagen del
dibujo sale como copia con su archivo de mundo, donde se elija. Ida y vuelta:
exportar e insertar la copia la deja exactamente donde estaba."""
import math, os, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from PIL import Image
from PIL.TiffImagePlugin import ImageFileDirectory_v2
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core.select import GeometryIndex
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
G = import_module("ingecad_plugin_geocad.georref")
IG = import_module("ingecad_plugin_geocad.imagengeo")
mods = import_module("ingecad_plugin_geocad.modulos")
yag = import_module("ingecad_plugin_geocad.yaguarete")
barra = import_module("ingecad_plugin_geocad.barra")
plugin = import_module("ingecad_plugin_geocad")


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ------------------------------------------------------------- 1. los tres botones
spec = plugin.construir_spec()
assert spec.tools["INSERTARGEO"] is IG.InsertarGeoTool and spec.tools["EXPORTARGEO"] is IG.ExportarGeoTool
assert [o for o, m, _b in yag.HERRAMIENTAS if m == "georref"] == ["INSERTARGEO", "GEORREF", "EXPORTARGEO", "ASPECTOIMAGEN"]
assert all(o in yag.DESCRIPCIONES for o in ("INSERTARGEO", "EXPORTARGEO"))
assert {"INSERTARGEO", "EXPORTARGEO", "GEORREF"} <= set(barra._iconos_propios())
dibujo_menu = next(s for s in spec.menu if getattr(s, "label", "") == "Drawing")
assert {"INSERTARGEO", "EXPORTARGEO"} <= {getattr(i, "command", "") for i in dibujo_menu.items}
mods.poner("ingecad", "georref", False)
assert not {"INSERTARGEO", "EXPORTARGEO"} & set(plugin.construir_spec().tools)
mods.poner("ingecad", "georref", True)
print("ok botones")

# ------------------------------------------------------------- 2. leer la georreferencia
a = math.radians(12)
coef = (5500000.0, 0.25 * math.cos(a), -0.25 * math.sin(a), 6200000.0, 0.25 * math.sin(a), 0.25 * math.cos(a))
assert cerca(IG.coef_de_mundo([float(v) for v in G.texto_mundo(coef).split()]), coef, 1e-6)
d = Path(tempfile.mkdtemp())
Image.new("RGB", (400, 300), (90, 140, 200)).save(d / "foto.png")
(d / "foto.pgw").write_text(G.texto_mundo(coef))
r = IG.leer(d / "foto.png")
assert (r["ancho"], r["alto"]) == (400, 300) and cerca(r["coef"], coef, 1e-6) and "foto.pgw" in r["fuente"]
assert r["crs"] == ""
(d / "foto.png.aux.xml").write_text("<PAMDataset><SRS>" + G.wkt("EPSG:5349").replace("<", "&lt;") + "</SRS></PAMDataset>")
assert IG.leer(d / "foto.png")["crs"] == "EPSG:5349"
# otros nombres del archivo de mundo: .pngw, .wld, en mayúsculas
for nombre in ("otra.pngw", "otra.wld", "OTRA.PGW"):
    Image.new("RGB", (10, 10)).save(d / "otra.png")
    for v in d.glob("otra.*w*"):
        v.unlink()
    (d / nombre).write_text(G.texto_mundo(coef))
    assert cerca(IG.leer(d / "otra.png")["coef"], coef, 1e-6), nombre
assert IG.leer_mundo(d / "nada.png") is None
# GeoTIFF: escala + punto de enlace, con el sistema adentro
def geo_ifd():
    ifd = ImageFileDirectory_v2()
    for t in (33550, 33922, 34264):
        ifd.tagtype[t] = 12                                               # DOUBLE
    ifd.tagtype[34735] = 3                                                # SHORT
    return ifd


ifd = geo_ifd()
ifd[33550] = (0.5, 0.5, 0.0)
ifd[33922] = (0.0, 0.0, 0.0, 5400000.0, 6300000.0, 0.0)
ifd[34735] = (1, 1, 0, 2, 1024, 0, 1, 1, 3072, 0, 1, 5349)
Image.new("RGB", (200, 100)).save(d / "orto.tif", tiffinfo=ifd)
r = IG.leer(d / "orto.tif")
assert cerca(r["coef"], (5400000, 0.5, 0, 6300000, 0, 0.5)) and r["crs"] == "EPSG:5349" and "GeoTIFF" in r["fuente"]
# PixelIsPoint: el enlace es el centro del píxel
ifd[34735] = (1, 1, 0, 2, 1025, 0, 1, 2, 3072, 0, 1, 5349)
Image.new("RGB", (200, 100)).save(d / "punto.tif", tiffinfo=ifd)
assert cerca(IG.leer(d / "punto.tif")["coef"][:4:3], (5400000 - 0.25, 6300000 + 0.25))
# ModelTransformation (con giro)
ifd = geo_ifd()
ifd[34264] = (coef[1], -coef[2], 0, coef[0], coef[4], -coef[5], 0, coef[3], 0, 0, 0, 0, 0, 0, 0, 1)
Image.new("RGB", (50, 40)).save(d / "girada.tif", tiffinfo=ifd)
assert cerca(IG.leer(d / "girada.tif")["coef"], coef, 1e-9)
Image.new("RGB", (5, 5)).save(d / "sin.png")
assert IG.leer(d / "sin.png")["coef"] is None
assert IG.aviso_crs("EPSG:32720", "EPSG:5349").startswith("Atención") and not IG.aviso_crs("EPSG:5349", "epsg:5349")
assert not IG.aviso_crs("", "EPSG:5349")
print("ok leer")

# ------------------------------------------------------------- 3. INSERTARGEO
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
doc.doc.layers.add("FOTOS"); doc.doc.header["$CLAYER"] = "FOTOS"
msgs, fin, respuesta, zoom = [], [], [None], []


class Ctrl:
    def __init__(self):
        self.window = types.SimpleNamespace(document=doc, zoom_to_entity=zoom.append)
        self.index = GeometryIndex(doc)
        self.selection = set()
        self._pick_tolerance = 0.2
    def pick_entity(self, p):
        h = self.index.pick(tuple(p), self._pick_tolerance)
        return self.index.entity(h) if h else None


def herramienta(clase, selection=()):
    msgs.clear(); fin.clear()
    ctrl = Ctrl(); ctrl.selection = set(selection)
    ctx = ToolContext(execute=hist.execute, prompt=lambda t: None, echo=msgs.append,
                      finish=lambda: fin.append(1), services=ctrl,
                      ask_text=lambda pedido, inicio="": respuesta[0])
    t = clase(ctx); t.start()
    return t


G.crs_dibujo = lambda: "EPSG:5349"
respuesta[0] = str(d / "foto.png")
herramienta(IG.InsertarGeoTool)
img = next(iter(msp.query("IMAGE")))
assert fin and img.dxf.layer == "FOTOS" and zoom == [img]                # capa actual, y se ve
for p in ((0, 0), (400, 0), (400, -300), (123, -77)):
    assert cerca(G.pixel_a_mundo(img, p), G.aplicar(coef, p), 1e-6), p
assert img.image_def.dxf.filename == str(d / "foto.png")
assert any("insertada en su lugar (archivo de mundo foto.pgw)" in m and "giro 12°" in m for m in msgs)
assert not any(m.startswith("Atención") for m in msgs)                   # mismo sistema
hist.undo(); assert not list(msp.query("IMAGE"))                        # U la quita
G.crs_dibujo = lambda: "EPSG:32720"
herramienta(IG.InsertarGeoTool); assert any(m.startswith("Atención: la imagen está en EPSG:5349") for m in msgs)
hist.undo()
respuesta[0] = str(d / "sin.png"); herramienta(IG.InsertarGeoTool)
assert any("no tiene georreferencia" in m for m in msgs) and not list(msp.query("IMAGE"))
(d / "rota.png").write_bytes(b"no es una imagen")
respuesta[0] = str(d / "rota.png"); herramienta(IG.InsertarGeoTool)
assert any("no se puede leer" in m for m in msgs)
respuesta[0] = None; herramienta(IG.InsertarGeoTool); assert fin and not msgs   # Cancelar
print("ok insertar")

# ------------------------------------------------------------- 4. EXPORTARGEO e ida y vuelta
G.crs_dibujo = lambda: "EPSG:5349"
Image.new("RGB", (300, 200), (200, 120, 60)).save(d / "escaneo.jpg")
ddef = doc.doc.add_image_def(filename=str(d / "escaneo.jpg"), size_in_pixel=(300, 200))
esc = msp.add_image(ddef, insert=(1000, 2000), size_in_units=(30, 20), rotation=25)
afuera = Path(tempfile.mkdtemp()) / "para QGIS"; afuera.mkdir()
respuesta[0] = str(afuera / "escaneo geo")                                # sin extensión: lleva .jpg
t = herramienta(IG.ExportarGeoTool)
assert t.resaltado(G.aplicar(G.coef_imagen(esc), (150, -100)))["cursor"]  # se ilumina al pasar
t.on_point(G.aplicar(G.coef_imagen(esc), (150, -100)))                    # clic dentro
copia = afuera / "escaneo geo.jpg"
assert fin and copia.read_bytes() == (d / "escaneo.jpg").read_bytes()
assert (afuera / "escaneo geo.jgw").exists() and (afuera / "escaneo geo.jpg.aux.xml").exists()
assert esc.image_def.dxf.filename == str(d / "escaneo.jpg")               # el dibujo no cambia
assert any("el dibujo no cambia" in m for m in msgs)
respuesta[0] = str(copia)                                                 # ida y vuelta
herramienta(IG.InsertarGeoTool)
nueva = [i for i in msp.query("IMAGE") if i is not esc][0]
assert all(cerca(p, q, 1e-6) for p, q in zip(G.esquinas(nueva), G.esquinas(esc)))
hist.undo()
respuesta[0] = str(d / "escaneo.jpg")                                    # sobre la original: no
herramienta(IG.ExportarGeoTool, {esc.dxf.handle})                         # elegida de antes
assert any("no se pudo exportar" in m for m in msgs) and not (d / "escaneo.jgw").exists()
respuesta[0] = None
herramienta(IG.ExportarGeoTool, {esc.dxf.handle}); assert any("cancelado" in m for m in msgs)
t = herramienta(IG.ExportarGeoTool); t.on_point((-500, -500)); assert not fin   # nada ahí: sigue pidiendo
ddef.dxf.filename = str(d / "no_existe.jpg")
herramienta(IG.ExportarGeoTool, {esc.dxf.handle}); assert any("no se encuentra el archivo" in m for m in msgs)
assert not IG.es_portal("/home/x/a.png") and IG.es_portal("/run/user/1000/doc/ab12/a.png")
print("ok exportar")

print("TODO OK IMAGENGEO")
