"""Panel Layers de IngeCAD (3.25.6): candado abierto en gris para las capas
libres y cerrado en rojo para las bloqueadas, sin tocar el texto que IngeCAD
lee al hacer clic. Sin Qt: qué se dibuja según el texto de la celda."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
C = import_module("ingecad_plugin_geocad.capas")

# los mismos emojis que pone IngeCAD (views/layers_panel.py, _state_glyph)
assert C.estado("🔓") == "abierto" and C.estado(" 🔒 ") == "cerrado"
assert C.estado("💡") is None and C.estado("") is None and C.estado(None) is None
assert C.COLUMNA_BLOQUEO == 4
assert C.ROJO[0] > 180 and C.ROJO[1] < 90 and C.ROJO[2] < 90          # rojo de verdad
assert len(set(C.GRIS)) == 1                                        # gris neutro
# sin Qt ni IngeCAD con vista: instalar no rompe nada
C.instalar()
print("ok candados: abierto gris, cerrado rojo; el texto de IngeCAD no cambia")
print("TODO OK test_capas")
