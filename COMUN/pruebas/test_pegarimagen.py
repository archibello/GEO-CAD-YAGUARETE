"""PEGARIMAGEN (GEOPASTEIMAGE) para IngeCAD (módulo «georref», 3.28.0): la
captura de pantalla del portapapeles entra con Ctrl+V y dos clics: la esquina
inferior izquierda y la inferior derecha, que da la escala (y el giro, si no
es horizontal). Se guarda como PNG junto al dibujo; U la quita."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import math, os, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from PIL import Image
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
PI = import_module("ingecad_plugin_geocad.pegarimagen")
mods = import_module("ingecad_plugin_geocad.modulos")
yag = import_module("ingecad_plugin_geocad.yaguarete")
barra = import_module("ingecad_plugin_geocad.barra")
plugin = import_module("ingecad_plugin_geocad")


def cerca(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ------------------------------------------------------------- 1. orden, barra GeoCAD y menú
spec = plugin.construir_spec()
assert spec.tools["GEOPASTEIMAGE"] is PI.PegarImagenTool
assert spec.aliases["PASTEIMAGE"] == "GEOPASTEIMAGE"
assert "GEOPASTEIMAGE" in {i.command for i in spec.toolbar}                 # barra GeoCAD
assert barra.TEMAS["GEOPASTEIMAGE"] == barra.TEMAS["GEOPASTETABLE"]          # junto a Pegar tabla
dibujo_menu = next(s for s in spec.menu if getattr(s, "label", "") == "Drawing")
assert "GEOPASTEIMAGE" in {getattr(i, "command", "") for i in dibujo_menu.items}
assert "GEOPASTEIMAGE" in yag.DESCRIPCIONES
icono = Path(plugin.__file__).parent / "iconos" / "pegar_imagen.png"
assert icono.is_file() and Image.open(icono).size == (24, 24)
import json
es = json.loads((Path(plugin.__file__).parent / "i18n" / "es" / "commands.json").read_text("utf-8"))
assert es["GEOPASTEIMAGE"]["name"] == "PEGARIMAGEN"
mods.poner("ingecad", "georref", False)
s2 = plugin.construir_spec()
assert "GEOPASTEIMAGE" not in s2.tools and "GEOPASTEIMAGE" not in {i.command for i in s2.toolbar}
mods.poner("ingecad", "georref", True)
print("ok botones")

# ------------------------------------------------------------- 2. las cuentas
assert PI.colocar((0, 0), (0, 0), 100, 50) is None
(o, u, v) = PI.colocar((10, 20), (110, 20), 200, 100)                        # horizontal
assert o == (10, 20) and cerca(u, (0.5, 0)) and cerca(v, (0, 0.5))
assert cerca(sum(PI.esquinas((10, 20), (110, 20), 200, 100), ()), (10, 20, 110, 20, 110, 70, 10, 70))
e = PI.esquinas((0, 0), (30, 40), 100, 50)                                   # girada, ancho 50
assert cerca(e[1], (30, 40)) and cerca(e[3], (-20, 15)) and cerca(e[2], (10, 55))
print("ok cuentas")

# ------------------------------------------------------------- 3. Ctrl+V: ¿imagen u objetos?
assert PI.ctrl_v_es_imagen(True, False, False)
assert not PI.ctrl_v_es_imagen(True, True, False)       # copia de IngeCAD: pega los objetos
assert not PI.ctrl_v_es_imagen(True, False, True)       # Ctrl+C recién hecho en esta ventana
assert not PI.ctrl_v_es_imagen(False, False, False)
# el envoltorio de paste (sin Qt: ante la duda, el Ctrl+V de siempre)
llamado = []
envuelto = PI._envolver_paste(lambda self: llamado.append(1))
envuelto(types.SimpleNamespace(start_tool=lambda n: llamado.append(n)))
assert llamado == [1] and envuelto._puente_original is not None
print("ok ctrl+v")

# ------------------------------------------------------------- 4. dónde se guarda
base = Path(tempfile.mkdtemp())
assert PI.carpeta_destino(base / "obra" / "plano.dwg") == base / "obra" / "plano_imagenes"
assert PI.carpeta_destino(None) == Path.home() / "GeoCAD"
(Path.home() / "Imágenes").mkdir()
assert PI.carpeta_destino("") == Path.home() / "Imágenes" / "GeoCAD"
n1 = PI.nombre_libre(base, 0); n1.write_bytes(b"x")
n2 = PI.nombre_libre(base, 0)
assert n1.name.startswith("captura_") and n2.name == n1.stem + "_2.png"
print("ok carpeta")

# ------------------------------------------------------------- 5. PEGARIMAGEN en el dibujo
carpeta_dibujo = Path(tempfile.mkdtemp())
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
doc.path = str(carpeta_dibujo / "relevamiento.dwg")
doc.doc.layers.add("CAPTURAS"); doc.doc.header["$CLAYER"] = "CAPTURAS"
msgs, fin, prompts = [], [], []


def captura(ancho=400, alto=300):
    im = Image.new("RGB", (ancho, alto), (90, 140, 200))
    return PI.Copiada(ancho, alto, guardar=lambda r: im.save(r, "PNG") or True)


def herramienta(copiada, ruta_dibujo=None):
    msgs.clear(); fin.clear(); prompts.clear()
    ctrl = types.SimpleNamespace(window=types.SimpleNamespace(document=doc))
    ctx = ToolContext(execute=hist.execute, prompt=prompts.append, echo=msgs.append,
                      finish=lambda: fin.append(1), services=ctrl)
    t = PI.PegarImagenTool(ctx); t.name = t.NOMBRE; t.empezar(copiada)
    return t


t = herramienta(captura())
assert prompts == [t.PRIMERO] and not fin
assert t.preview_segments((5, 5)) == []                                      # antes del 1er punto
t.on_point((1000, 2000))
assert prompts[-1] == t.SEGUNDO and t.last_point == (1000, 2000) and t.ortho_applies()
pre = t.preview_segments((1040, 2000))
assert len(pre) == 6 and cerca(pre[1][1], (1040, 2030))                      # contorno y diagonales
t.on_point((1000, 2000))                                                     # el mismo punto: otra vez
assert not fin and any("distinto" in m for m in msgs)
t.on_point((1040, 2000))
assert fin
img = next(iter(msp.query("IMAGE")))
assert img.dxf.layer == "CAPTURAS"
assert cerca(tuple(img.dxf.insert)[:2], (1000, 2000)) and cerca(tuple(img.dxf.u_pixel)[:2], (0.1, 0))
assert cerca(tuple(img.dxf.v_pixel)[:2], (0, 0.1))
ruta = Path(img.image_def.dxf.filename)
assert ruta.parent == carpeta_dibujo / "relevamiento_imagenes" and ruta.suffix == ".png"
assert Image.open(ruta).size == (400, 300) and tuple(img.image_def.dxf.image_size)[:2] == (400, 300)
assert any("Imagen pegada: 400 × 300 píxeles, 40 × 30 unidades" in m for m in msgs)
assert not any("girada" in m or "no está guardado" in m for m in msgs)
hist.undo(); assert not list(msp.query("IMAGE"))                             # U la quita
print("ok pegar")

# girada (sin ORTO) y escribiendo el ancho
t = herramienta(captura(200, 100)); t.on_point((0, 0)); t.on_point((30, 40))
img = next(iter(msp.query("IMAGE")))
assert cerca(tuple(img.dxf.u_pixel)[:2], (0.15, 0.2)) and cerca(tuple(img.dxf.v_pixel)[:2], (-0.2, 0.15))
assert any("girada 53.13°" in m for m in msgs)
hist.undo()
t = herramienta(captura(200, 100)); t.on_point((5, 5))
assert t.on_option("12,5") and fin
img = next(iter(msp.query("IMAGE")))
assert cerca(tuple(img.dxf.u_pixel)[:2], (0.0625, 0)) and cerca(tuple(img.dxf.insert)[:2], (5, 5))
hist.undo()
t = herramienta(captura()); t.on_point((0, 0)); assert t.on_option("-3") and not fin
assert not t.on_option("hola")
print("ok girada y ancho")

# un archivo copiado en el explorador: se usa tal cual, no se copia
foto = carpeta_dibujo / "foto.jpg"; Image.new("RGB", (64, 32)).save(foto)
antes = sorted((carpeta_dibujo / "relevamiento_imagenes").iterdir())
t = herramienta(PI.Copiada(64, 32, archivo=foto)); t.on_point((0, 0)); t.on_point((64, 0))
img = next(iter(msp.query("IMAGE")))
assert Path(img.image_def.dxf.filename) == foto
assert sorted((carpeta_dibujo / "relevamiento_imagenes").iterdir()) == antes
assert any("archivo copiado" in m for m in msgs)
hist.undo()

# dibujo sin guardar: en Imágenes/GeoCAD, con aviso
doc.path = None
t = herramienta(captura()); t.on_point((0, 0)); t.on_point((4, 0))
img = next(iter(msp.query("IMAGE")))
assert Path(img.image_def.dxf.filename).parent == Path.home() / "Imágenes" / "GeoCAD"
assert any("no está guardado" in m for m in msgs)
hist.undo()

# no se pudo escribir: avisa y no inserta nada
t = herramienta(PI.Copiada(10, 10, guardar=lambda r: False)); t.on_point((0, 0)); t.on_point((1, 0))
assert fin and any("no se pudo guardar" in m for m in msgs) and not list(msp.query("IMAGE"))

# portapapeles sin imagen (o sin Qt): avisa y termina
t = herramienta(None)
assert fin and msgs == [PI.PegarImagenTool.SIN_IMAGEN] and PI.del_portapapeles() is None
t.on_point((0, 0)); assert not list(msp.query("IMAGE"))
print("ok casos")

print("TODO OK PEGARIMAGEN")
