"""Imágenes en KML/KMZ (3.32.0, módulo «Intercambio»). EXPORTARKML lleva las
imágenes del dibujo como superposiciones (GroundOverlay) con sus cuatro
esquinas (gx:LatLonQuad: el norte de la faja no es el geográfico), en PNG,
con el aspecto de ASPECTOIMAGEN, dentro del KMZ o en «<nombre>_imagenes»
junto al .kml. IMPORTARKML las trae como imágenes georreferenciadas, en la
capa de su carpeta, copiadas a «<dibujo>_imagenes». Ida y vuelta al
milímetro; también las de Google Earth (LatLonBox con giro)."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import io, math, os, tempfile, zipfile
os.environ["HOME"] = tempfile.mkdtemp()
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from importlib import import_module
import ezdxf
from PIL import Image
from pyproj import Transformer
from core.commands import History
from core.document import Document
from core.georef import Georef, write_georef
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
KML = import_module("ingecad_plugin_geocad.kml")
G = import_module("ingecad_plugin_geocad.georref")

tmp = Path(tempfile.mkdtemp())
PNG = b"\x89PNG\r\n\x1a\n"
SIS7 = "EPSG:5349"                                                        # POSGAR 2007 faja 7, Posadas
a_geo = Transformer.from_crs(SIS7, "EPSG:4326", always_xy=True)
X0, Y0 = Transformer.from_crs("EPSG:4326", SIS7, always_xy=True).transform(-55.896, -27.367)

# ------------------------------------------------------------- 1. un dibujo con dos imágenes
# un JPG girado 30° (se convierte a PNG) y la copia con aspecto de ASPECTOIMAGEN
# (PNG con transparencia, nombrada relativa al dibujo)
Image.new("RGB", (40, 20), (200, 30, 30)).save(tmp / "foto.jpg", quality=95)
(tmp / "ida_imagenes").mkdir()
asp = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
asp.putpixel((3, 4), (10, 20, 30, 255))
asp.save(tmp / "ida_imagenes" / "plano_aspecto.png")
dibujo = tmp / "ida.dxf"
orig = Document(ezdxf.new("R2018")); om = orig.modelspace()
write_georef(orig.doc, Georef(crs=SIS7))
orig.doc.layers.add("FOTOS", color=3); orig.doc.layers.add("PLANOS", color=1)


def imagen(ruta_escrita, w, h, insert, u, v, capa):
    d = orig.doc.add_image_def(filename=str(ruta_escrita), size_in_pixel=(w, h))
    img = om.add_image(d, insert=insert, size_in_units=(w, h), dxfattribs={"layer": capa})
    img.dxf.insert = (*insert, 0.0)
    img.dxf.u_pixel = (*u, 0.0)
    img.dxf.v_pixel = (*v, 0.0)
    return img


g = math.radians(30)
foto = imagen(tmp / "foto.jpg", 40, 20, (X0, Y0), (0.5 * math.cos(g), 0.5 * math.sin(g)),
              (-0.5 * math.sin(g), 0.5 * math.cos(g)), "FOTOS")
plano = imagen("ida_imagenes/plano_aspecto.png", 30, 30, (X0 + 100, Y0 + 50), (2.0, 0.0), (0.0, 2.0),
               "PLANOS")
om.add_lwpolyline([(X0, Y0), (X0 + 10, Y0 + 10)], dxfattribs={"layer": "FOTOS"})

plan = KML.plan_kml(list(om), orig.doc, "Ida", ruta_dibujo=dibujo)
assert len(plan.superposiciones) == 2 and len(plan.marcas) == 1, plan
s_foto, s_plano = plan.superposiciones
assert (s_foto.nombre, s_foto.capa) == ("foto", "FOTOS")
assert (s_plano.nombre, s_plano.capa) == ("plano", "PLANOS"), s_plano      # sin «_aspecto»
for s, img in ((s_foto, foto), (s_plano, plano)):
    esperadas = [a_geo.transform(*p) for p in
                 (G.pixel_a_mundo(img, q) for q in ((0, -img.dxf.image_size[1]),
                                                    (img.dxf.image_size[0], -img.dxf.image_size[1]),
                                                    (img.dxf.image_size[0], 0), (0, 0)))]
    assert all(math.dist(a, b) < 1e-9 for a, b in zip(s.esquinas, esperadas))
# el norte de la faja no es el geográfico: la foto sin girar no tiene lados norte-sur
plano_esq = s_plano.esquinas
assert abs(plano_esq[0][0] - plano_esq[3][0]) > 1e-7          # el lado izquierdo no es un meridiano
print("ok las imágenes del dibujo como superposiciones: capa, nombre y sus 4 esquinas en WGS 84")

# ------------------------------------------------------------- 2. el KMZ: PNG adentro y gx:LatLonQuad
kmz = KML.escribir(plan, tmp / "ida.kmz")
with zipfile.ZipFile(kmz) as z:
    nombres = sorted(z.namelist())
    assert nombres == ["doc.kml", "imagenes/foto.png", "imagenes/plano_aspecto.png"], nombres
    assert all(z.read(n)[:8] == PNG for n in nombres if n.endswith(".png"))
    assert z.read("imagenes/plano_aspecto.png") == (tmp / "ida_imagenes" / "plano_aspecto.png").read_bytes()
    convertida = Image.open(io.BytesIO(z.read("imagenes/foto.png")))
    assert convertida.size == (40, 20) and convertida.format == "PNG"
    texto = z.read("doc.kml").decode()
raiz = ET.fromstring(texto)
NS = {"k": KML.KML_NS, "gx": KML.GX_NS}
carpetas = {f.find("k:name", NS).text: f for f in raiz.iter(f"{{{KML.KML_NS}}}Folder")}
assert set(carpetas) == {"FOTOS", "PLANOS"}
go = carpetas["PLANOS"].find("k:GroundOverlay", NS)
assert go.find("k:Icon/k:href", NS).text == "imagenes/plano_aspecto.png"
assert go.find("k:altitudeMode", NS).text == "clampToGround"
quad = go.find("gx:LatLonQuad/k:coordinates", NS).text.split()
assert len(quad) == 4 and go.find("k:LatLonBox", NS) is None
# en FOTOS la imagen va primero (debajo de la línea)
assert [KML._local(c.tag) for c in carpetas["FOTOS"]][1:] == ["GroundOverlay", "Placemark"]
assert "2 imagen(es)" in KML.resumen(plan, kmz)
print("ok KMZ: PNG adentro (el JPG convertido, el del aspecto tal cual), gx:LatLonQuad, carpeta por capa")

# ------------------------------------------------------------- 3. ida y vuelta al milímetro (KMZ y KML)
# junto al .kml va «ida_imagenes», que es la carpeta de imágenes del dibujo: no se pisa nada
ajena = tmp / "ida_imagenes" / "foto.png"
Image.new("RGB", (3, 3), (1, 2, 3)).save(ajena)
ajena_bytes = ajena.read_bytes()
for ext in (".kmz", ".kml"):
    archivo = KML.escribir(KML.plan_kml(list(om), orig.doc, "Ida", ruta_dibujo=dibujo), tmp / ("ida" + ext))
    if ext == ".kml":
        assert sorted(p.name for p in (tmp / "ida_imagenes").iterdir()) == ["foto.png", "foto_2.png",
                                                                           "plano_aspecto.png"]
        assert ajena.read_bytes() == ajena_bytes                      # la del dibujo, intacta
        texto = archivo.read_text()
        assert "ida_imagenes/foto_2.png" in texto and "ida_imagenes/plano_aspecto.png" in texto
        KML.escribir(KML.plan_kml(list(om), orig.doc, "Ida", ruta_dibujo=dibujo), archivo)
        assert len(list((tmp / "ida_imagenes").iterdir())) == 3       # exportar otra vez no suma copias
    lgs, salt = KML.leer(archivo)
    assert not salt, salt
    assert sorted((lg.tipo, lg.carpeta) for lg in lgs) == [("imagen", "FOTOS"), ("imagen", "PLANOS"),
                                                          ("linea", "FOTOS")]
    vuelta = Document(ezdxf.new("R2018")); hv = History(vuelta)
    write_georef(vuelta.doc, Georef(crs=SIS7))
    destino = tmp / f"vuelta{ext[1:]}.dxf"
    plan_i = KML.plan_importar(vuelta.doc, archivo, lgs, KML.OpcionesKml(), Counter(), destino)
    assert plan_i.comando.needs_regen
    hv.execute(plan_i.comando)
    imgs = {i.dxf.layer: i for i in vuelta.modelspace().query("IMAGE")}
    assert set(imgs) == {"FOTOS", "PLANOS"}, imgs
    for capa, img0 in (("FOTOS", foto), ("PLANOS", plano)):
        img = imgs[capa]
        assert tuple(img.dxf.image_size)[:2] == tuple(img0.dxf.image_size)[:2]
        peor = max(math.dist(a, b) for a, b in zip(G.esquinas(img), G.esquinas(img0)))
        assert peor < 1e-3, (capa, peor)
        archivo_img = Path(img.image_def.dxf.filename)
        assert archivo_img.parent == tmp / f"vuelta{ext[1:]}_imagenes" and archivo_img.read_bytes()[:8] == PNG
    assert imgs["PLANOS"].get_flag_state(imgs["PLANOS"].USE_TRANSPARENCY)          # trae alfa
    assert not imgs["FOTOS"].get_flag_state(imgs["FOTOS"].USE_TRANSPARENCY)
    r = KML.resumen_importar(plan_i)
    assert "Con 2 imágenes en vuelta" in r and "U lo deshace" in r, r
    # importar otra vez el mismo archivo usa las mismas copias (no foto_2.png)
    hv.execute(KML.plan_importar(vuelta.doc, archivo, lgs, KML.OpcionesKml(), Counter(), destino).comando)
    assert len(list((tmp / f"vuelta{ext[1:]}_imagenes").iterdir())) == 2
    hv.undo(); hv.undo()
    assert not list(vuelta.modelspace().query("IMAGE"))
    print(f"ok ida y vuelta {ext}: las imágenes en su lugar (peor {peor * 1000:.4f} mm), en su capa, "
          "con su transparencia; U las quita")

# ------------------------------------------------------------- 4. las de Google Earth: LatLonBox con giro
assert all(math.dist(a, b) < 1e-12 for a, b in zip(
    KML.esquinas_caja(1, -1, 2, -2, 90), [(1, -2), (1, 2), (-1, 2), (-1, -2)]))
Image.new("RGB", (64, 32), (0, 128, 0)).save(tmp / "ortofoto.jpg")
GE = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder><name>Ortofotos</name>
  <GroundOverlay><name>Orto</name><Icon><href>ortofoto.jpg</href></Icon>
    <LatLonBox><north>-27.366</north><south>-27.368</south><east>-55.894</east><west>-55.898</west>
      <rotation>12.5</rotation></LatLonBox></GroundOverlay>
  <GroundOverlay><name>Satélite</name><Icon><href>https://example.com/tile.png</href></Icon>
    <LatLonBox><north>1</north><south>0</south><east>1</east><west>0</west></LatLonBox></GroundOverlay>
  <GroundOverlay><name>Falta</name><Icon><href>no_esta.png</href></Icon>
    <LatLonBox><north>-27.366</north><south>-27.367</south><east>-55.895</east><west>-55.896</west></LatLonBox>
  </GroundOverlay>
  <ScreenOverlay><name>Leyenda</name></ScreenOverlay>
</Folder></Document></kml>"""
ge = tmp / "google.kml"
ge.write_text(GE, encoding="utf-8")
lgs, salt = KML.leer(ge)
assert salt == Counter({"imágenes de internet": 1, "imágenes de pantalla o fotos": 1}), salt
assert [lg.nombre for lg in lgs] == ["Orto", "Falta"]
d3 = Document(ezdxf.new("R2018")); write_georef(d3.doc, Georef(crs=SIS7))
plan_g = KML.plan_importar(d3.doc, ge, lgs, KML.OpcionesKml(), salt, None)
History(d3).execute(plan_g.comando)
[orto] = d3.modelspace().query("IMAGE")
assert orto.dxf.layer == "Ortofotos" and tuple(orto.dxf.image_size)[:2] == (64, 32)
assert Path(orto.image_def.dxf.filename).suffix == ".jpg"           # tal cual venía
a_dib = Transformer.from_crs("EPSG:4326", SIS7, always_xy=True)
esperadas = [a_dib.transform(*p) for p in KML.esquinas_caja(-27.366, -27.368, -55.894, -55.898, 12.5)]
peor = max(math.dist(a, b) for a, b in zip(G.esquinas(orto), esperadas[::-1]))   # G: desde arriba izq.
assert peor < 0.05, peor                      # la caja de grados es casi un paralelogramo en la faja
r = KML.resumen_importar(plan_g)
assert "No se encontraron las imágenes: no_esta.png" in r and "imágenes de internet 1" in r, r
print(f"ok Google Earth: LatLonBox girado en su lugar ({peor * 1000:.1f} mm), las de internet y las que "
      "faltan se avisan")

# ------------------------------------------------------------- 5. sin Pillow: el tamaño de un PNG por su cabecera
buf = io.BytesIO(); Image.new("RGBA", (7, 5)).save(buf, "PNG")
assert KML.tamano_y_alfa(buf.getvalue()) == (7, 5, True)
buf = io.BytesIO(); Image.new("RGB", (9, 3)).save(buf, "PNG")
assert KML.tamano_y_alfa(buf.getvalue()) == (9, 3, False)
# una imagen sin su archivo no se exporta y se avisa
(tmp / "foto.jpg").unlink()
plan_f = KML.plan_kml([foto], orig.doc, "x", ruta_dibujo=dibujo)
assert not plan_f.superposiciones and plan_f.salteados == Counter({"imágenes sin su archivo": 1})
print("ok tamaño de PNG sin Pillow; imagen sin archivo avisada")
print("TODO OK")
