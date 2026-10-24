"""Imágenes nuevas que IngeCAD no dibuja (3.36.0): una imagen recién creada
(pegar, COPIA, GIRA con copia...) que quedó en la capa provisoria sin
textura sale de ahí y se pide el redibujo; las demás no se tocan. La
prueba con la ventana real de IngeCAD está en ventana/ (necesita PySide6)."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
RD = import_module("ingecad_plugin_geocad.redibujo_imagenes")
mods = import_module("ingecad_plugin_geocad.modulos")

doc = ezdxf.new("R2018"); m = doc.modelspace()
defi = doc.add_image_def(filename="plano.png", size_in_pixel=(10, 10))
vieja = m.add_image(defi, insert=(0, 0), size_in_units=(10, 10))
nueva = m.add_image(defi, insert=(20, 0), size_in_units=(10, 10))
linea = m.add_line((0, 0), (1, 1))


class Textura:
    def __init__(self, h): self.handle = h


class Vista:
    def __init__(self, handles): self._scene = type("Escena", (), {"images": [Textura(h) for h in handles]})()


class Ventana:
    def __init__(self, handles):
        self.viewport, self.regens = Vista(handles), 0
    def regen_in_memory(self): self.regens += 1


class Controlador:
    def __init__(self, pendientes, con_textura):
        self.window, self._pending_render, self.refrescos = Ventana(con_textura), list(pendientes), 0
    def _refresh_overlay(self): self.refrescos += 1


# la imagen nueva sin textura sale de la capa provisoria y se redibuja; la línea queda
c = Controlador([nueva, linea, vieja], [vieja.dxf.handle])
assert RD.sin_textura(c) == [nueva]
assert RD.revisar(c) is True
assert c._pending_render == [linea, vieja] and c.window.regens == 1 and c.refrescos == 1
# nada que hacer: ni redibujo ni refresco
c = Controlador([linea], [vieja.dxf.handle, nueva.dxf.handle])
assert RD.revisar(c) is False and c.window.regens == 0 and c.refrescos == 0
print("ok imágenes sin textura: fuera de la capa provisoria y redibujo")

# el envoltorio: después del método de IngeCAD, revisa; con el módulo apagado, no
class TC:
    def __init__(self): self.c = Controlador([nueva], [])
    def _execute_command(self, cmd): return "hecho"


envuelto = RD._envolver(TC._execute_command)
mods.guardar("ingecad", {"georref": True}); RD._activo_cache[0] = 0.0
t = TC(); t.window, t._pending_render, t._refresh_overlay = t.c.window, t.c._pending_render, t.c._refresh_overlay
assert envuelto(t, None) == "hecho" and t._pending_render == [] and t.window.regens == 1
mods.guardar("ingecad", {"georref": False}); RD._activo_cache[0] = 0.0
t = TC(); t.window, t._pending_render, t._refresh_overlay = t.c.window, t.c._pending_render, t.c._refresh_overlay
assert envuelto(t, None) == "hecho" and t._pending_render == [nueva] and t.window.regens == 0
assert envuelto._puente_original is TC._execute_command
print("ok envoltorio: revisa después; apagado, IngeCAD como venía")
print("TODO OK")
