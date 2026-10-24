"""Recortar una imagen con Ctrl + agarre (3.35.0): la esquina queda donde se
suelta y la opuesta fija; la imagen no se mueve ni cambia de escala. Una
copia recortada (los mismos píxeles) en «<dibujo>_imagenes»; la original no
se toca. Hacia afuera se vuelve a abrir hasta la original. Un U deshace
cada recorte. Sin Ctrl, el agarre escala como siempre."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from PIL import Image
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from core import select as SEL
from core.actions import SnapshotCommand

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
RI = import_module("ingecad_plugin_geocad.recorte_imagen")
mods = import_module("ingecad_plugin_geocad.modulos")


def modulo(prendido):
    mods.guardar("ingecad", {"georref": prendido})
    RI._activo_cache[0] = 0.0


modulo(True)
carpeta = Path(tempfile.mkdtemp())
original = carpeta / "plano.png"
im = Image.new("RGB", (400, 200))
im.putdata([(x % 256, y, (x * 7 + y) % 256) for y in range(200) for x in range(400)])
im.save(original)
d = Document(ezdxf.new("R2018")); d.path = carpeta / "obra.dwg"
m = d.doc.modelspace()
defi = d.doc.add_image_def(filename=str(original), size_in_pixel=(400, 200))
img = m.add_image(defi, insert=(100, 50), size_in_units=(40, 20))      # 0,1 por píxel
h = History(d)


def r(v):
    return tuple(round(c, 6) for c in v)


def marco(e):
    return sorted({r((p.x, p.y)) for p in e.boundary_path_wcs()})


def indice(e, x, y):
    esq = list(e.boundary_path_wcs())[:4]
    return min(range(4), key=lambda i: (esq[i].x - x) ** 2 + (esq[i].y - y) ** 2)


def archivo(e):
    return Path(e.image_def.dxf.filename)


def recortar(x0, y0, x, y):
    cmd = RI.preparar(img, indice(img, x0, y0), (x, y), d)
    h.execute(cmd)
    return cmd


# ------------------------------------------------ 1. achicar desde una esquina
recortar(140, 70, 130, 65)                      # arriba a la derecha, hacia adentro
assert r(img.dxf.insert)[:2] == (100, 50)       # la esquina opuesta no se movió
assert r(img.dxf.u_pixel)[:2] == (0.1, 0) and r(img.dxf.v_pixel)[:2] == (0, 0.1)   # misma escala
assert tuple(img.dxf.image_size)[:2] == (300, 150)
assert marco(img) == [(100, 50), (100, 65), (130, 50), (130, 65)], marco(img)
copia = archivo(img)
assert copia.parent == carpeta / "obra_imagenes" and copia.name == "plano_recorte_0_50_300x150.png", copia
assert list(Image.open(copia).getdata()) == list(im.crop((0, 50, 300, 200)).getdata())   # los mismos píxeles
assert RI.leer(img) == (str(original), (0, 50, 300, 200))
assert Image.open(original).size == (400, 200)                                         # la original intacta
print("ok achicar: esquina en su lugar, misma escala, los mismos píxeles")

# ------------------------------------------------ 2. otra esquina, sobre el recorte
recortar(100, 50, 110, 55)                      # abajo a la izquierda, hacia adentro
assert r(img.dxf.insert)[:2] == (110, 55)
assert marco(img) == [(110, 55), (110, 65), (130, 55), (130, 65)], marco(img)
assert RI.leer(img)[1] == (100, 50, 300, 150)
assert list(Image.open(archivo(img)).getdata()) == list(im.crop((100, 50, 300, 150)).getdata())
print("ok segundo recorte, contado sobre la original")

# ------------------------------------------------ 3. hacia afuera: se vuelve a abrir, hasta la original
recortar(130, 65, 500, 500)
assert RI.leer(img)[1] == (100, 0, 400, 150), RI.leer(img)
assert marco(img) == [(110, 55), (110, 70), (140, 55), (140, 70)], marco(img)
recortar(110, 55, -50, -50)                     # todo afuera: la original entera
assert RI.leer(img) is None and archivo(img) == original
assert marco(img) == [(100, 50), (100, 70), (140, 50), (140, 70)], marco(img)
assert tuple(img.dxf.image_size)[:2] == (400, 200)
print("ok hacia afuera: vuelve a abrir, hasta la original")

# ------------------------------------------------ 4. U deshace cada paso (archivo, marco y marca)
h.undo(); assert RI.leer(img)[1] == (100, 0, 400, 150) and marco(img)[0] == (110, 55)
h.undo(); assert RI.leer(img)[1] == (100, 50, 300, 150)
h.undo(); assert RI.leer(img)[1] == (0, 50, 300, 200) and marco(img)[0] == (100, 50)
h.undo(); assert RI.leer(img) is None and archivo(img) == original and tuple(img.dxf.image_size)[:2] == (400, 200)
assert marco(img) == [(100, 50), (100, 70), (140, 50), (140, 70)]
h.redo(); assert RI.leer(img)[1] == (0, 50, 300, 200) and archivo(img) == copia
h.undo()
print("ok U y rehacer")

# ------------------------------------------------ 5. girada 90°
g = m.add_image(defi, insert=(300, 0), size_in_units=(40, 20), rotation=90)   # el ancho va hacia arriba
cmd = RI.preparar(g, indice(g, 280, 40), (290, 30), d); h.execute(cmd)
assert marco(g) == [(290, 0), (290, 30), (300, 0), (300, 30)], marco(g)
assert RI.leer(g)[1] == (0, 100, 300, 200), RI.leer(g)   # la mitad de abajo de la imagen
print("ok girada")

# ------------------------------------------------ 6. lo que no se puede
for x, y in ((100, 70), (140, 50)):             # la esquina sobre un lado de la opuesta: sin nada
    try:
        RI.preparar(img, indice(img, 140, 70), (x, y), d)
        raise AssertionError("tenía que fallar")
    except RI.RecorteError:
        pass
try:
    RI.preparar(img, indice(img, 140, 70), (140, 70), d)       # soltar donde estaba
    raise AssertionError("tenía que fallar")
except RI.RecorteError as exc:
    assert "igual" in str(exc)
print("ok sin recorte: avisa")

# ------------------------------------------------ 7. el agarre: con Ctrl no escala, sin Ctrl sí
antes = marco(img)
RI._ctrl = lambda: True
assert SEL.apply_grip_edit(img, indice(img, 140, 70), "corner", (160, 80)) is True and marco(img) == antes
modulo(False)
SEL.apply_grip_edit(img, indice(img, 140, 70), "corner", (160, 80)); assert marco(img) != antes   # apagado: escala
modulo(True)
RI._ctrl = lambda: False
img2 = m.add_image(defi, insert=(0, 0), size_in_units=(40, 20))
SEL.apply_grip_edit(img2, indice(img2, 40, 20), "corner", (80, 40))
assert marco(img2) == [(0, 0), (0, 40), (80, 0), (80, 40)]                          # sin Ctrl: escala
print("ok agarre: Ctrl recorta, sin Ctrl escala")

# ------------------------------------------------ 8. soltar el agarre con Ctrl (el controlador de IngeCAD, simulado)
class Linea:
    def __init__(self): self.dicho = []
    def echo(self, t): self.dicho.append(t)


class Ventana:
    def __init__(self): self.document, self.history, self.command_line = d, h, Linea()


class Indice:
    def entity(self, handle): return d.doc.entitydb.get(handle)


class Controlador:
    def __init__(self): self.window, self.index, self._grip_drag = Ventana(), Indice(), None
    def begin(self, e, x, y):
        self._grip_drag = (e.dxf.handle, indice(e, x, y), "corner", SnapshotCommand([e]))
        self._grip_base = (x, y)
    def update(self, x, y):
        hd, i, rol, _s = self._grip_drag
        SEL.apply_grip_edit(self.index.entity(hd), i, rol, (x, y))
    def finish_grip_drag(self, x, y):        # lo que hace IngeCAD al soltar
        hd, i, rol, snap = self._grip_drag
        self._grip_drag = None
        e = self.index.entity(hd)
        SEL.apply_grip_edit(e, i, rol, (x, y))
        snap.commit(d); self.window.history.record(snap)
    def _execute(self, cmd): self.window.history.execute(cmd)


Controlador.finish_grip_drag = RI._envolver_soltar(Controlador.finish_grip_drag)
c = Controlador()
img3 = m.add_image(defi, insert=(0, 100), size_in_units=(40, 20))
pasos = len(h._undo)
c.begin(img3, 40, 120); c.update(60, 130)                       # se mueve SIN Ctrl: escala en vivo
RI._ctrl = lambda: True
c.update(30, 115)                                               # con Ctrl: quieta
c.finish_grip_drag(30, 115)                                     # suelta con Ctrl: recorta
assert marco(img3) == [(0, 100), (0, 115), (30, 100), (30, 115)], marco(img3)
assert len(h._undo) == pasos + 1                                # un solo paso para U
assert "recortada" in c.window.command_line.dicho[-1]
h.undo(); assert marco(img3) == [(0, 100), (0, 120), (40, 100), (40, 120)]          # U: como estaba
c.begin(img3, 40, 120); c.finish_grip_drag(0, 100)              # recortar a nada: avisa, no cambia
assert "no se recorta" in c.window.command_line.dicho[-1] and len(h._undo) == pasos
assert marco(img3) == [(0, 100), (0, 120), (40, 100), (40, 120)]
RI._ctrl = lambda: False
c.begin(img3, 40, 120); c.finish_grip_drag(80, 140)             # sin Ctrl: escala, como siempre
assert marco(img3) == [(0, 100), (0, 140), (80, 100), (80, 140)]
print("ok soltar: Ctrl recorta en un paso; sin Ctrl escala")

# ------------------------------------------------ 9. una sola vez
RI.instalar(); RI.instalar()
f, capas = SEL.apply_grip_edit, 0
while f is not None:
    capas += getattr(f, "_puente_fabrica", None) is RI._envolver_agarre
    f = getattr(f, "_puente_original", None)
assert capas == 1, capas
print("ok instalado una sola vez")
print("TODO OK")
