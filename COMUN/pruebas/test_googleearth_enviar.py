"""Enviar / Traer de Google Earth (3.81.0, IngeCAD). Fernando, 15/11/2026: las
dos órdenes se pisaban (la ventanita de «Abrir Google Earth» ya traía
CAPTURAR). Ahora cada una tiene un trabajo:
  GEOEARTHOPEN    «Enviar a Google Earth...»: lo seleccionado, lo que se ve en
                  pantalla o las capas elegidas (una imagen en una capa y los
                  polígonos en otra) a un KMZ que se abre en Google Earth.
  GEOEARTHCAPTURE «Traer imagen de Google Earth...»: abre y enlaza Google
                  Earth y deja la ventanita lista; ya NO captura en el acto.
Sin Qt ni Google Earth: lo que elige la ventana se prueba con entidades_de."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import json, math, os, tempfile, types, zipfile
os.environ["HOME"] = tempfile.mkdtemp()
import xml.etree.ElementTree as ET
from pathlib import Path
from importlib import import_module
import ezdxf
from PIL import Image
from pyproj import Transformer
from core.document import Document
from core.georef import Georef, write_georef
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
plugin = import_module("ingecad_plugin_geocad")
GEC = import_module("ingecad_plugin_geocad.googleearth_cmd")
ENV = import_module("ingecad_plugin_geocad.googleearth_enviar")
KML = import_module("ingecad_plugin_geocad.kml")
GE = import_module("ingecad_plugin_geocad.googleearth")
N = "{http://www.opengis.net/kml/2.2}"

# ------------------------------------------------------------- 1. menú: Enviar / Traer
spec = plugin.construir_spec()
sub = next(s for s in spec.menu if getattr(s, "label", "") == "Google Earth")
items = [i for i in sub.items if not isinstance(i, str)]
assert [(i.label, i.command) for i in items[:2]] == [
    ("Send to Google Earth...", "GEOEARTHOPEN"), ("Get image from Google Earth...", "GEOEARTHCAPTURE")]
es = json.loads((Path(plugin.__file__).parent / "i18n" / "es" / "ui.json").read_text(encoding="utf-8"))
assert es["Send to Google Earth..."] == "Enviar a Google Earth..."
assert es["Get image from Google Earth..."] == "Traer imagen de Google Earth..."
assert GEC.COMMANDS["GEOEARTHOPEN"] is GEC.cmd_abrir and GEC.COMMANDS["GEOEARTHCAPTURE"] is GEC.cmd_capturar
print("ok menú GeoCAD > Google Earth: «Enviar a Google Earth...» y «Traer imagen de Google Earth...»")

# ------------------------------------------------------------- 2. cada orden hace lo suyo
llamadas = []
_abrir_original, _enviar_original = GEC._abrir, ENV.enviar
GEC._abrir = lambda ctx, **kw: llamadas.append(("ventanita", kw))
ENV.enviar = lambda ctx: llamadas.append(("enviar", {}))
try:
    GEC.cmd_capturar(None)
    GEC.cmd_abrir(None)
finally:
    GEC._abrir, ENV.enviar = _abrir_original, _enviar_original
assert llamadas == [("ventanita", {"abrir_ge": True}), ("enviar", {})], llamadas   # Traer ya no captura solo
msgs = []
ENV.enviar(types.SimpleNamespace(document=None, echo=msgs.append))
assert msgs == ["Enviar a Google Earth: no hay un dibujo abierto."], msgs
print("ok Traer abre y enlaza Google Earth sin capturar en el acto; Enviar va a su ventana")

# ------------------------------------------------------------- 3. un dibujo: imagen en una capa, polígonos en otra
SIS7 = "EPSG:5349"                                                        # POSGAR 2007 faja 7, Posadas
X0, Y0 = Transformer.from_crs("EPSG:4326", SIS7, always_xy=True).transform(-55.896, -27.367)
tmp = Path(tempfile.mkdtemp())
Image.new("RGB", (40, 20), (200, 30, 30)).save(tmp / "foto.jpg", quality=95)
doc = Document(ezdxf.new("R2018")); msp = doc.modelspace(); d = doc.doc
write_georef(d, Georef(crs=SIS7))
for capa, color in (("IMAGEN", 7), ("LOTES", 3), ("CALLES", 1)):
    d.layers.add(capa, color=color)
idef = d.add_image_def(filename=str(tmp / "foto.jpg"), size_in_pixel=(40, 20))
img = msp.add_image(idef, insert=(X0, Y0), size_in_units=(40, 20), dxfattribs={"layer": "IMAGEN"})
img.dxf.u_pixel = (1.0, 0.0, 0.0); img.dxf.v_pixel = (0.0, 1.0, 0.0)          # 40 x 20 m
lote1 = msp.add_lwpolyline([(X0, Y0), (X0 + 30, Y0), (X0 + 30, Y0 + 15), (X0, Y0 + 15)],
                           close=True, dxfattribs={"layer": "LOTES"})
lote2 = msp.add_lwpolyline([(X0 + 500, Y0), (X0 + 530, Y0), (X0 + 530, Y0 + 15)],
                           close=True, dxfattribs={"layer": "LOTES"})       # lejos: fuera de pantalla
calle = msp.add_line((X0 - 50, Y0 - 5), (X0 + 900, Y0 - 5), dxfattribs={"layer": "CALLES"})  # asoma
assert ENV.capas_con_objetos(d) == ["CALLES", "IMAGEN", "LOTES"]         # «0» y las vacías no se ofrecen

# lo seleccionado: tal cual
assert ENV.entidades_de(d, ENV.SELECCION, [lote2]) == [lote2]
# las capas elegidas: la imagen de una capa y los polígonos de otra
assert ENV.entidades_de(d, ENV.CAPAS, capas={"IMAGEN", "LOTES"}) == [img, lote1, lote2]
# lo que se ve en pantalla: lo que toca la zona; la calle que asoma va entera
zona = (X0 - 10, Y0 - 10, X0 + 100, Y0 + 60)
assert ENV.entidades_de(d, ENV.PANTALLA, zona=zona) == [img, lote1, calle]
assert ENV.entidades_de(d, ENV.PANTALLA, zona=(X0 + 2000, Y0, X0 + 2100, Y0 + 50)) == []
assert ENV.entidades_de(d, ENV.PANTALLA, zona=None) == []
try:
    ENV.entidades_de(d, "otra")
    raise AssertionError("aceptó una opción que no existe")
except ValueError:
    pass
print("ok qué se envía: seleccionado, lo que se ve (lo que asoma va entero) y capas elegidas")

# ------------------------------------------------------------- 4. el KMZ que se abre en Google Earth
ruta = ENV.ruta_envio("Mensura: lote/6")
assert ruta.parent == Path(os.environ["HOME"]) / ".config" / "geocad" / "googleearth" / "enviados"
assert ruta.name == "Mensura_ lote_6.kmz", ruta.name                  # sin / ni : en el nombre
assert ENV.ruta_envio("").name == "dibujo.kmz"
entidades = ENV.entidades_de(d, ENV.CAPAS, capas={"IMAGEN", "LOTES"})
plan = KML.plan_kml(entidades, d, "Mensura", True, 40, True, "", tmp / "mensura.dxf")
ruta.parent.mkdir(parents=True, exist_ok=True)
KML.escribir(plan, ruta)
with zipfile.ZipFile(ruta) as z:
    nombres = z.namelist()
    raiz = ET.fromstring(z.read("doc.kml"))
assert "doc.kml" in nombres and any(n.endswith(".png") for n in nombres), nombres
carpetas = {f.findtext(f"{N}name") for f in raiz.iter(f"{N}Folder")}
assert {"IMAGEN", "LOTES"} <= carpetas, carpetas                      # una carpeta por capa
assert len(list(raiz.iter(f"{N}GroundOverlay"))) == 1
assert len(list(raiz.iter(f"{N}Polygon"))) == 2
assert "CALLES" not in carpetas
KML.escribir(plan, ruta)                                              # se reemplaza sin preguntar
assert ruta.is_file()
print("ok el KMZ enviado: imagen y polígonos de dos capas, una carpeta por capa, en la carpeta de GeoCAD")

print("TODO OK")
