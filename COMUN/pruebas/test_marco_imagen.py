"""Referencias en el marco de las imágenes (3.33.7): Final en las esquinas,
Medio, Intersección, Cercano, Perpendicular e Inserción, como en AutoCAD,
para ubicar y escalar una imagen ya insertada. Con el recorte, por el
recorte. Con el módulo «georref» apagado, IngeCAD queda como venía."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.document import Document
from core.plugins import load_plugin
from core.snap import SnapEngine

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
MI = import_module("ingecad_plugin_geocad.marco_imagen")
B = import_module("ingecad_plugin_geocad.bloques")
mods = import_module("ingecad_plugin_geocad.modulos")


def modulo(prendido):
    mods.guardar("ingecad", {"georref": prendido})
    MI._activo_cache[0] = 0.0


modulo(True)
d = Document(ezdxf.new("R2018")); m = d.doc.modelspace()
defi = d.doc.add_image_def(filename="foto.png", size_in_pixel=(400, 200))
m.add_image(defi, insert=(100, 50), size_in_units=(40, 20))                 # 40 x 20
girada = m.add_image(defi, insert=(300, 0), size_in_units=(40, 20), rotation=90)
m.add_line((90, 60), (150, 60))                                             # corta el borde izquierdo y derecho
eng = SnapEngine(d)
TODAS = frozenset({"END", "MID", "INT", "INS", "NEA", "PER"})


def ref(x, y, kinds=TODAS, desde=None):
    h = eng.find((x, y), 0.5, frozenset(kinds), from_point=desde) if desde else \
        eng.find((x, y), 0.5, frozenset(kinds))
    return None if h is None else (h.kind, round(h.x, 6), round(h.y, 6))


# ---------------------------------------------------------------- 1. el marco
assert ref(140.2, 70.1, {"END"}) == ("END", 140, 70), ref(140.2, 70.1, {"END"})   # esquina opuesta
assert ref(100.1, 70.2, {"END"}) == ("END", 100, 70)
assert ref(120.1, 50.2, {"MID"}) == ("MID", 120, 50)                                 # medio de un lado
assert ref(140.1, 60.1, {"INT"}) == ("INT", 140, 60)                                 # marco x línea
assert ref(100.2, 50.1, {"INS"}) == ("INS", 100, 50)                                 # inserción
h = ref(130, 69.8, {"NEA"}); assert h and h[0] == "NEA" and abs(h[2] - 70) < 1e-6, h
# girada 90°: el ancho va hacia arriba
assert ref(300.1, 40.1, {"END"}) == ("END", 300, 40), ref(300.1, 40.1, {"END"})
assert ref(280.1, 40.1, {"END"}) == ("END", 280, 40), ref(280.1, 40.1, {"END"})
print("ok marco: esquinas, medio, intersección, inserción, cercano, girada")

# ---------------------------------------------------------------- 2. recortada
from ezdxf.math import Vec2
img = m.add_image(defi, insert=(0, 200), size_in_units=(40, 20))
img.set_boundary_path([Vec2(-0.5, -0.5), Vec2(199.5, -0.5), Vec2(199.5, 99.5), Vec2(-0.5, 99.5)])   # píxeles (borde = -0,5): mitad
eng.invalidate()
assert ref(20.1, 210.1, {"END"}) == ("END", 20, 210), ref(20.1, 210.1, {"END"})
assert ref(40, 220, {"END"}) is None                                                # fuera del recorte
print("ok recortada: por el recorte")

# ---------------------------------------------------------------- 3. una imagen nueva
nueva = m.add_image(defi, insert=(500, 0), size_in_units=(10, 10))
eng.add_entities([nueva])
assert ref(510.1, 10.1, {"END"}) == ("END", 510, 10)
print("ok imagen recién insertada")

# ---------------------------------------------------------------- 4. módulo apagado
modulo(False); eng.invalidate()
assert ref(140.2, 70.1, {"END"}) is None and ref(100.2, 50.1, {"INS"}) is None
modulo(True); eng.invalidate()
assert ref(140.2, 70.1, {"END"}) == ("END", 140, 70)
print("ok apagado: IngeCAD como venía")

# ---------------------------------------------------------------- 5. una sola vez, con bloques
antes = SnapEngine.__dict__["_extract"]
MI.instalar(); B.instalar_referencias(); MI.instalar()
assert SnapEngine.__dict__["_extract"] is antes or MI._instalado(SnapEngine.__dict__["_extract"].__func__)
f = SnapEngine.__dict__["_extract"].__func__; capas = 0
while f is not None:
    capas += getattr(f, "_marco_fabrica", None) is MI._envolver_extract
    f = getattr(f, "_marco_original", None) or getattr(f, "_puente_original", None)
assert capas == 1, capas
eng.invalidate(); assert ref(140.2, 70.1, {"END"}) == ("END", 140, 70)
print("ok instalado una sola vez")
print("TODO OK")
