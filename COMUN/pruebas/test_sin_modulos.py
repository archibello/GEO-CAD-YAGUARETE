"""GeoCAD carga en un IngeCAD cuyo Python no trae todo (3.31.3). La AppImage
de IngeCAD 0.6.8 está armada con PyInstaller, que sólo empaqueta lo que usa
IngeCAD: no trae html.parser ni sqlite3, e IngeCAD dejaba a GeoCAD sin
cargar («No module named 'html.parser'»). Se simula ese Python bloqueando
los módulos y se carga el plugin."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path

#: lo que le falta a la AppImage de IngeCAD 0.6.8 (lista de su PyInstaller)
FALTAN_EN_APPIMAGE = ("html.parser", "sqlite3", "_sqlite3", "sqlite3.dbapi2", "ctypes.util")
for m in FALTAN_EN_APPIMAGE:
    sys.modules[m] = None                    # import m -> ImportError
try:
    import sqlite3  # noqa: F401
    raise SystemExit("no se pudo simular el Python sin sqlite3")
except ImportError:
    pass

from importlib import import_module
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
print("ok GeoCAD carga sin html.parser ni sqlite3")

# las tablas pegadas se leen del texto
T = import_module("ingecad_plugin_geocad.tablas")
assert T.HAY_HTML is False
assert T.leer_html("<table><tr><td>1</td></tr></table>") is None
t = T.leer(html="<table><tr><td>a</td><td>b</td></tr></table>", texto="a\tb\n1\t2\n")
assert t is not None and t.n_filas == 2, t
print("ok tablas: sin html.parser, del texto")

# GeoPackage avisa en vez de romperse
G = import_module("ingecad_plugin_geocad.gpkgio")
assert G.HAY_SQLITE is False
try:
    G.connect(Path(tempfile.mkdtemp()) / "x.gpkg")
    raise AssertionError("debía avisar")
except G.sqlite3.Error as exc:
    assert "SQLite" in str(exc), exc
for nombre in ("gpkg_checkin", "tools", "datos", "fuentes", "checkin"):
    import_module("ingecad_plugin_geocad." + nombre)
print("ok GeoPackage: avisa que este IngeCAD no trae SQLite")

# Google Earth (3.33.0): la ventanita usa http.server (la AppImage lo trae) y
# libX11 por ctypes, sin ctypes.util (no lo trae): carga igual
V = import_module("ingecad_plugin_geocad.googleearth_vivo")
import_module("ingecad_plugin_geocad.googleearth_cmd")
srv = V.Servidor(puerto=0); srv.iniciar(); srv.detener()
V._xlib()                                    # sin ctypes.util: libX11.so.6 directo (o None sin X11)
print("ok Google Earth: carga sin ctypes.util")
print("TODO OK SIN MODULOS")
