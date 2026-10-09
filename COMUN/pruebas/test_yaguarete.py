"""Barra «Yaguareté Tools» y carteles de los botones (3.13.0): qué
herramientas pasan a la barra según los módulos (y salen de su barra de
IngeCAD), y el cartel como el de AutoCAD: nombre, qué hace y la orden."""
import os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
Y = import_module("ingecad_plugin_geocad.yaguarete")
mods = import_module("ingecad_plugin_geocad.modulos")
B = import_module("ingecad_plugin_geocad.barra")

# ---- 1. qué va en la barra ----------------------------------------------------------
assert Y.NOMBRE_BARRA == "Yaguareté Tools"
todo = {m.clave: True for m in mods.CATALOGO["ingecad"]}
assert Y.elegidas(todo) == [("RECTANG", "draw_toolbar"), ("STRETCH", "modify_toolbar"),
                            ("BREAKATPOINT", None), ("CHAMFER", "modify_toolbar"),
                            ("FILLET", "modify_toolbar")]
apagados = dict(todo, empalme=False, estirar=False)
assert [o for o, _ in Y.elegidas(apagados)] == ["RECTANG", "BREAKATPOINT", "CHAMFER"]  # vuelven a IngeCAD
assert [o for o, _ in Y.elegidas({})] == ["RECTANG"]           # REC: siempre con GeoCAD
spec = import_module("ingecad_plugin_geocad").construir_spec()
assert not {"FILLET", "CHAMFER", "BREAKATPOINT"} & {i.command for i in spec.toolbar}  # no repetidas
assert {o for o, _m, _b in Y.HERRAMIENTAS if _b is None} <= set(Y.ETIQUETAS)
print("ok barra")

# ---- 2. el cartel ---------------------------------------------------------------------
assert Y.separar_orden("Empalme (FILLET)") == ("Empalme", "FILLET")
assert Y.separar_orden("Empalme estilo AutoCAD (EMPALME)") == ("Empalme estilo AutoCAD", "EMPALME")
assert Y.separar_orden("Guardar") == ("Guardar", None)
assert Y.separar_orden("") == ("", None)
nombres = {"EMPALME": "FILLET", "EM": "FILLET", "ESTIRA": "STRETCH"}
assert Y.nombre_local("FILLET", nombres) == "EMPALME" and Y.nombre_local("TRIM", nombres) == "TRIM"
c = Y.texto_cartel("Empalme", "FILLET", nombres)
assert c.startswith("<b>Empalme</b><br>Redondea") and c.endswith("Orden: EMPALME</span>"), c
assert Y.texto_cartel("Guardar", None) == "<b>Guardar</b>"
assert "&lt;" in Y.texto_cartel("a<b", None)
assert Y.ESPERA_MS == 1000
# toda herramienta de la barra y de las barras Dibujo/Modificar tiene su línea
for o in ("LINE", "PLINE", "CIRCLE", "ARC", "REVCLOUD", "SPLINE", "ELLIPSE", "RECTANG", "POLYGON",
          "POINT", "TEXT", "MTEXT", "HATCH", "ERASE", "COPY", "MIRROR", "OFFSET", "ARRAY", "MOVE",
          "ROTATE", "SCALE", "STRETCH", "TRIM", "EXTEND", "BREAK", "JOIN", "CHAMFER", "FILLET",
          "EXPLODE", "BREAKATPOINT"):
    assert o in Y.DESCRIPCIONES, o
for item in spec.toolbar:
    assert item.command in Y.DESCRIPCIONES, item.command
print("ok cartel")

# ---- 3. se engancha al armar y al sacar la barra GeoCAD ---------------------------------
assert callable(B._envolver_add_toolbar) and callable(B._envolver_remove_toolbar)
print("TODO OK YAGUARETE")
