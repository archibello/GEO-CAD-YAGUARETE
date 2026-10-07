"""3.7.0 Vista previa y plumas: el editor de la tabla de plumas (.ctb) cambia
color de impresión, grosor, tramado y grises por color de AutoCAD (1 Rojo,
2 Amarillo...), guarda con respaldo y la página provisoria de Page Setup se
deshace exacta. (Las ventanas usan Qt: se prueban aparte, en IngeCAD.)"""
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["HOME"], ".config")
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin
from core import layouts as L, plotstyles

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
I = import_module("ingecad_plugin_geocad.impresion")
M = import_module("ingecad_plugin_geocad.modulos")
G = import_module("ingecad_plugin_geocad")

# ------------------------------------------------------------- 1. el módulo, la barra y el menú
assert any(m.clave == "impresion" for m in M.catalogo("ingecad")) and I.activo()
spec = G.construir_spec()
assert {"GEOPREVIEW", "GEOPLOTSTYLES"} <= set(spec.commands)
assert {"GEOPREVIEW", "GEOPLOTSTYLES"} <= {t.command for t in spec.toolbar}
M.guardar("ingecad", {"impresion": False})
spec = G.construir_spec()
assert "GEOPREVIEW" not in spec.commands and not I.activo()
M.guardar("ingecad", {"impresion": True})
print("ok módulo")

# ------------------------------------------------------------- 2. colores de AutoCAD
assert I.nombre_color(1) == "1 · Rojo" and I.nombre_color(2) == "2 · Amarillo"
assert I.nombre_color(3) == "3 · Verde" and I.nombre_color(7) == "7 · Blanco/Negro"
assert I.nombre_color(8) == "8 · Color 8"
print("ok colores")

# ------------------------------------------------------------- 3. editar plumas
carpeta = I.carpeta()
assert carpeta == plotstyles.folder() and (carpeta / "acad.ctb").exists()
t = I.leer(carpeta / "acad.ctb")
assert I.pluma(t, 1) == {"color": None, "grises": False, "tramado": 100,
                         "grosor": 0.0, "descripcion": ""}
assert I.cambiar(t, [1], color=(0, 0, 0), grosor=0.5) == 1
assert I.cambiar(t, [3, 5], grosor=0.13, tramado=50, grises=True, descripcion="ejes") == 2
assert I.cambiar(t, [0, 256], grosor=1.0) == 0                 # fuera de 1..255
n = len(t.lineweights)
I.cambiar(t, [4], grosor=0.13)
assert len(t.lineweights) == n                                  # 0,13 ya estaba (float32)
assert I.pluma(t, 1)["color"] == (0, 0, 0) and I.pluma(t, 1)["grosor"] == 0.5
assert I.pluma(t, 5) == {"color": None, "grises": True, "tramado": 50,
                         "grosor": 0.13, "descripcion": "ejes"}
I.cambiar(t, [1], color=None)
assert I.pluma(t, 1)["color"] is None
I.cambiar(t, [1], color=(255, 0, 0), tramado=150)
assert I.pluma(t, 1)["tramado"] == 100
print("ok editar")

# ------------------------------------------------------------- 4. guardar con respaldo
assert I.nombre_archivo("Mis plumas") == "Mis plumas.ctb"
assert I.nombre_archivo("../x.CTB") == "x.CTB"
for malo in ("", "  ", ".."):
    try:
        I.nombre_archivo(malo)
        raise AssertionError(malo)
    except ValueError:
        pass
ruta = carpeta / "Prueba.ctb"
assert I.guardar(t, ruta) is None and ruta.exists()
assert "Prueba.ctb" in plotstyles.available()
leida = plotstyles.load("Prueba.ctb")                           # como la lee IngeCAD al imprimir
assert 1 not in leida.object_color and 5 in leida.object_color
assert leida.pen_color(1, (9, 9, 9)) == (255, 0, 0)
assert abs(leida.table[3].get_lineweight() - 0.13) < 1e-4
assert leida.pen_color(5, (0, 0, 255)) == (142, 142, 142)       # gris 29, tramado 50 %
I.cambiar(t, [2], grosor=2.0)
respaldo = I.guardar(t, ruta)
assert respaldo == carpeta / "Prueba.ctb.bak" and respaldo.exists()
import shutil; copia = carpeta / "copia_respaldo.ctb"; shutil.copy2(respaldo, copia)
assert I.pluma(I.leer(copia), 2)["grosor"] == 0.0 and I.pluma(I.leer(ruta), 2)["grosor"] == 2.0
assert not list(carpeta.glob("*geocad-tmp*"))
assert "Prueba.ctb.bak" not in plotstyles.available()
nueva = I.nueva()
assert all(I.pluma(nueva, a)["color"] is None for a in (1, 7, 255))
try:
    I.leer(carpeta / "algo.stb")
    raise AssertionError("stb")
except ValueError:
    pass
print("ok guardar")

# ------------------------------------------------------------- 5. página provisoria (Page Setup)
d = ezdxf.new("R2018"); d.header["$INSUNITS"] = 6
doc = types.SimpleNamespace(doc=d, dirty=False)
lay = d.layouts.get("Layout1")
antes = dict(lay.dxf.all_existing_dxf_attribs())
cmd = L.page_setup_command(lay, 420.0, 297.0, (20.0, 7.5, 20.0, 7.5), "ISO A3",
                           fit_to_paper=False, scale=(1.0, 0.001), style_sheet="Prueba.ctb")
visto = I.con_pagina_provisoria(doc, lay, cmd, lambda: (lay.dxf.get("current_style_sheet"),
                                                        doc.dirty))
assert visto == ("Prueba.ctb", True)
assert dict(lay.dxf.all_existing_dxf_attribs()) == antes and doc.dirty is False
try:
    I.con_pagina_provisoria(doc, lay, cmd, lambda: 1 / 0)
except ZeroDivisionError:
    pass
assert dict(lay.dxf.all_existing_dxf_attribs()) == antes and doc.dirty is False
print("ok página provisoria")

print("TODO OK IMPRESION")
