"""SOLTARIMAGEN (GEODROPIMAGE) para IngeCAD (módulo «georref», 3.88.0): una
imagen arrastrada desde el explorador entra con la esquina inferior
izquierda, un 2º punto que da el ancho (la escala) y el giro al final
(señalado, escrito o Enter = 0°). Recién ahí queda; Esc no deja nada; U la
quita. El archivo se usa tal cual."""
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
SI = import_module("ingecad_plugin_geocad.soltar_imagen")
mods = import_module("ingecad_plugin_geocad.modulos")
plugin = import_module("ingecad_plugin_geocad")


def cerca(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ------------------------------------------------------------- 1. la orden, con el módulo
spec = plugin.construir_spec(completo=True)
assert spec.tools["GEODROPIMAGE"] is SI.SoltarImagenTool
import json
es = json.loads((Path(plugin.__file__).parent / "i18n" / "es" / "commands.json").read_text("utf-8"))
assert es["GEODROPIMAGE"]["name"] == "SOLTARIMAGEN"
mods.poner("ingecad", "georref", False)
assert "GEODROPIMAGE" not in plugin.construir_spec(completo=True).tools
mods.poner("ingecad", "georref", True)
print("ok orden")

# ------------------------------------------------------------- 2. las cuentas
assert SI.ancho_de((0, 0), (3, 4)) == 5
assert abs(SI.angulo_de((0, 0), (0, 2)) - 90) < 1e-12
assert cerca(SI.ubicar((10, 20), 50, 0), (60, 20)) and cerca(SI.ubicar((0, 0), 2, 90), (0, 2))
e = SI.esquinas_giradas((10, 20), 100, 0, 200, 100)                        # derecha: ancho 100, alto 50
assert cerca(sum(e, ()), (10, 20, 110, 20, 110, 70, 10, 70))
e = SI.esquinas_giradas((0, 0), 100, 90, 200, 100)                          # girada 90°
assert cerca(e[1], (0, 100)) and cerca(e[3], (-50, 0))
assert SI.esquinas_giradas((0, 0), 0, 0, 10, 10) == []
assert SI.leer_giro("30") == 30 and SI.leer_giro("-12,5") == -12.5 and SI.leer_giro("45°") == 45
assert SI.leer_giro("hola") is None
assert SI.es_imagen("a/b.PNG") and SI.es_imagen("x.tif") and not SI.es_imagen("plano.dwg")
print("ok cuentas")

# ------------------------------------------------------------- 3. en el dibujo
carpeta = Path(tempfile.mkdtemp())
foto = carpeta / "fachada.jpg"; Image.new("RGB", (400, 200), (90, 140, 200)).save(foto)
assert SI.medida(foto) == (400, 200) and SI.medida(carpeta / "no.png") is None
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
doc.path = str(carpeta / "obra.dwg")
doc.doc.layers.add("IMAGENES"); doc.doc.header["$CLAYER"] = "IMAGENES"
msgs, fin, prompts = [], [], []


def herramienta(ruta=foto, tam=(400, 200)):
    msgs.clear(); fin.clear(); prompts.clear()
    ctrl = types.SimpleNamespace(window=types.SimpleNamespace(document=doc))
    ctx = ToolContext(execute=hist.execute, prompt=prompts.append, echo=msgs.append,
                      finish=lambda: fin.append(1), services=ctrl)
    t = SI.SoltarImagenTool(ctx); t.name = t.NOMBRE; t.empezar(ruta, tam)
    return t


t = herramienta()
assert prompts == [t.PRIMERO] and not fin and t.preview_segments((5, 5)) == []
t.on_point((1000, 2000))
assert prompts[-1] == t.SEGUNDO and t.last_point == (1000, 2000)
pre = t.preview_segments((1030, 2040))                                      # distancia 50: ancho 50, derecha
assert len(pre) == 5 and cerca(pre[1][1], (1050, 2025)) and cerca(pre[4][1], (1030, 2040))
t.on_point((1000, 2000))                                                    # el mismo punto: otra vez
assert not fin and any("distinto" in m for m in msgs)
t.on_point((1030, 2040))
assert prompts[-1] == t.TERCERO and not fin and not list(msp.query("IMAGE"))  # todavía no queda
pre = t.preview_segments((1000, 2010))                                      # gira con el cursor: 90°
assert cerca(pre[0][1], (1000, 2050)) and cerca(pre[2][1], (975, 2000))
t.on_enter()                                                                # Enter = 0°
assert fin
img = next(iter(msp.query("IMAGE")))
assert img.dxf.layer == "IMAGENES" and Path(img.image_def.dxf.filename) == foto   # el archivo tal cual
assert cerca(tuple(img.dxf.insert)[:2], (1000, 2000)) and cerca(tuple(img.dxf.u_pixel)[:2], (0.125, 0))
assert cerca(tuple(img.dxf.v_pixel)[:2], (0, 0.125))
assert any("Imagen agregada: fachada.jpg, 400 × 200 píxeles, 50 × 25 unidades." in m for m in msgs)
assert sorted(p.name for p in carpeta.iterdir()) == ["fachada.jpg"]          # nada copiado
hist.undo(); assert not list(msp.query("IMAGE"))                            # U la quita
print("ok esquina, ancho y Enter")

# giro señalado y giro escrito; ancho escrito
t = herramienta(); t.on_point((0, 0)); t.on_point((100, 0)); t.on_point((0, 7))   # señalado: 90°
img = next(iter(msp.query("IMAGE")))
assert cerca(tuple(img.dxf.u_pixel)[:2], (0, 0.25)) and cerca(tuple(img.dxf.v_pixel)[:2], (-0.25, 0))
assert any("girada 90°" in m for m in msgs)
hist.undo()
t = herramienta(); t.on_point((5, 5))
assert t.on_option("80") and not fin and prompts[-1] == t.TERCERO          # ancho escrito
assert t.on_option("30") and fin                                            # giro escrito
img = next(iter(msp.query("IMAGE")))
c, s = math.cos(math.radians(30)) * 0.2, math.sin(math.radians(30)) * 0.2
assert cerca(tuple(img.dxf.u_pixel)[:2], (c, s)) and cerca(tuple(img.dxf.insert)[:2], (5, 5))
hist.undo()
t = herramienta(); t.on_point((0, 0))
assert t.on_option("-3") and not fin and any("mayor que cero" in m for m in msgs)
assert not t.on_option("hola")
t.on_point((10, 0)); assert not t.on_option("hola") and not fin
t.on_point((0, 0)); assert fin                                              # sobre la esquina: 0°
img = next(iter(msp.query("IMAGE"))); assert cerca(tuple(img.dxf.u_pixel)[:2], (0.025, 0))
hist.undo()
print("ok giro y ancho")

# Esc en cualquier paso: no queda nada
for pasos in ([], [(0, 0)], [(0, 0), (10, 0)]):
    t = herramienta()
    for p in pasos:
        t.on_point(p)
    t.on_cancel()
    assert fin and not list(msp.query("IMAGE")) and any("sin agregar" in m for m in msgs)
# Enter antes del ancho: tampoco
t = herramienta(); t.on_point((0, 0)); t.on_enter()
assert fin and not list(msp.query("IMAGE"))

# sin imagen o ilegible: avisa y termina
t = herramienta(None, None)
assert fin and msgs == [SI.SoltarImagenTool.SIN_IMAGEN]
t.on_point((0, 0)); assert not list(msp.query("IMAGE"))
t = herramienta(carpeta / "rota.png", None)
assert fin and "no se pudo leer" in msgs[0]
# escrita a mano sin soltar nada: el aviso
SI._pendiente.clear()
t = SI.SoltarImagenTool(ToolContext(execute=hist.execute, prompt=prompts.append, echo=msgs.append,
                                    finish=lambda: fin.append(1), services=None))
msgs.clear(); fin.clear(); t.start()
assert fin and msgs == [SI.SoltarImagenTool.SIN_IMAGEN]
# lo soltado llega a la orden
SI._pendiente[:] = [foto]; prompts.clear(); fin.clear()
t = SI.SoltarImagenTool(ToolContext(execute=hist.execute, prompt=prompts.append, echo=msgs.append,
                                    finish=lambda: fin.append(1), services=None))
t.start()
assert prompts == [t.PRIMERO] and not fin and t._tam == (400, 200) and not SI._pendiente
# sin Qt: el gancho del lienzo no hace nada
SI.aplicar(None); SI.aplicar(types.SimpleNamespace())
print("ok casos")

# ------------------------------------------------------------- 4. Wayland (3.88.1): la ruta en el texto
R = SI.rutas_de_texto
assert R(b"/home/u/Planos/plano#1958#hoja1.jpg") == [Path("/home/u/Planos/plano#1958#hoja1.jpg")]
assert R("file:///home/u/a%20b%23c.png\r\nfile:///x/y.jpg\n") == [Path("/home/u/a b#c.png"), Path("/x/y.jpg")]
assert R(b"154348542434273464005941809929656718809\x00") == []          # el número del portal: no es ruta
assert R("C:\\Planos\\x.png") == [Path("C:\\Planos\\x.png")] and R("") == [] and R(None) == []
assert SI.del_portal(b"") == [] and SI.del_portal("123") == []          # sin Qt: nada


class Datos:                                     # lo que entrega Qt en Wayland
    def __init__(self, formatos):
        self.f = formatos
    def hasUrls(self): return False
    def urls(self): return []
    def hasFormat(self, f): return f in self.f
    def data(self, f): return self.f[f]


w = Datos({"text/uri-list": b"154348542434273464005941809929656718809\x00",
           "text/plain": str(foto).encode(), SI.PORTAL: b"1835\x00"})
assert SI.imagen_soltada(w) == foto and SI.quiza_imagen(w)
assert SI.imagen_soltada(Datos({"text/plain": b"/no/existe.jpg"})) is None
assert SI.quiza_imagen(Datos({SI.PORTAL: b"1"}))                        # sólo el portal: se acepta y se ve al soltar
assert not SI.quiza_imagen(Datos({"text/plain": str(carpeta / "obra.dwg").encode()})) and not SI.quiza_imagen(None)
print("ok Wayland")

print("TODO OK SOLTARIMAGEN")
