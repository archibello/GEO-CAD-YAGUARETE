"""Relleno de los polígonos en Yaguá Capas (3.64.0), sin Qt: los campos CAD_FILL y
CAD_FILLTR, la conversión de los botones guardados y que el panel, la barra y la
simbología lo tengan. Lo que se ve y se toca en QGIS lo prueba
ventana/banco_relleno_qgis.py con el QGIS real.

Fernando, 03/11/2026: «cuando estamos trabajando con polígonos, ¿podríamos
agregar dos nuevos campos para configurar color de fondo y transparencia de los
polígonos?». Acordado: sólo QGIS, por capa CAD (panel) y por entidad (barra),
vacío = PorCapa."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import ast
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPAS = ROOT / "QGIS" / "codigo" / "geocad" / "capas"
os.environ["HOME"] = tempfile.mkdtemp(prefix="geocad-relleno-")
sys.path.insert(0, str(ROOT / "COMUN"))


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def funcion(fuente, nombre):
    """Una función suelta del código (el controlador importa qgis.core)."""
    arbol = ast.parse(fuente)
    nodo = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == nombre)
    espacio = {}
    exec(compile(ast.Module([nodo], []), nombre, "exec"), espacio)
    return espacio[nombre]


ctrl = (CAPAS / "controller.py").read_text(encoding="utf-8")
panel = (CAPAS / "panel.py").read_text(encoding="utf-8")
barra = (CAPAS / "barra.py").read_text(encoding="utf-8")
plugin = (CAPAS / "plugin.py").read_text(encoding="utf-8")
dialogs = (CAPAS / "dialogs.py").read_text(encoding="utf-8")

# ---- 1. la transparencia como en AutoCAD: entera, de 0 a 90 ------------------------------
clamp = funcion(ctrl, "clamp_transparency")
assert [clamp(v) for v in (0, 50, 49.6, 90, 95, -3, "40", None, "x")] == [0, 50, 50, 90, 90, 0, 40, 0, 0]
print("ok transparencia 0-90")

# ---- 2. el modelo: por capa CAD y por entidad -------------------------------------------
assert "'fill': ('cefill', 'CAD_FILL')" in ctrl and "'filltr': ('cefilltr', 'CAD_FILLTR')" in ctrl
assert "'fill': None, 'filltr': 0," in ctrl                 # una capa nueva: sin relleno
assert "'cefill': None, 'cefilltr': None" in ctrl           # lo próximo: PorCapa
assert "'transparency', 'fill', 'filltr')" in ctrl          # entra en los estados de capa
assert "('fill', 'Color de relleno'), ('filltr', 'Transparencia de relleno')" in dialogs
assert "NO_FILL = 'none'" in ctrl and "NO_FILL = 'none'" in barra
assert "NUMBER_PROPS = ('lineweight', 'filltr')" in ctrl    # CAD_FILLTR es un número
# sólo en las capas de polígonos (selección, objetos nuevos y simbología)
assert ctrl.count("prop in FILL_PROPS and geometry_kind(") == 3
assert "if kind == 'polygon' and (lay.get('fill') or has('CAD_FILL')):" in ctrl   # lo de antes, igual
assert "sym = QgsFillSymbol([fill, sl] if fill is not None else [sl])" in ctrl    # el borde encima
expr = funcion(ctrl, "fill_color_expression")
override = funcion(ctrl, "override_color_expression")
e = expr.__globals__
e["override_color_expression"], e["clamp_transparency"], e["NO_FILL"] = override, clamp, "none"
sin_campos = expr("'255,0,0,255'", 50, False, False, False)
assert "CAD_FILL" not in sin_campos and "round(255 * (100 - 50) / 100)" in sin_campos, sin_campos
con = expr("'255,0,0,255'", 95, True, True, True)
assert "lower(coalesce(\"CAD_FILL\", '')) = 'none' THEN '0,0,0,0'" in con
assert 'max(0, min(90, coalesce("CAD_FILLTR", 90)))' in con, con
assert "color_part(" in con and "set_color_part(" in con
# 3.64.1: la leyenda del panel Capas de QGIS no evalúa la expresión de cada objeto y
# mostraba el azul de QGIS: el símbolo lleva fijo el relleno de su capa CAD
assert "fill.setColor(self._fill_legend_color(lay, dark))" in ctrl
leyenda = ctrl[ctrl.index("def _fill_legend_color"):ctrl.index("def preview_color")]
assert "return QColor(0, 0, 0, 0)" in leyenda                        # sin relleno: nada
assert "clamp_transparency(lay.get('filltr', 0))" in leyenda and "setAlpha(" in leyenda
print("ok modelo")

# ---- 3. panel: Relleno y Transp. después del Grosor, sólo con polígonos ----------------
assert "C_FILL, C_FILLTR = 10, 11" in panel                  # al final: lo guardado no se corre
assert "(C_FILL, 'Relleno', 'Color de relleno', None)" in panel
assert "(C_FILLTR, 'Transp.', 'Transparencia de relleno', None)" in panel
assert "header.moveSection(header.visualIndex(C_FILL), header.visualIndex(C_LW) + 1)" in panel
assert "col in FILL_COLS and not polygons" in panel
assert "'Ninguno'" in panel and "'Seleccionar color...'" in panel and "'Otro...'" in panel
print("ok panel")

# ---- 4. barra: Color de relleno y Transparencia de relleno ------------------------------
assert "class FillCombo(ColorCombo)" in barra and "class FillTransparencyCombo(_PropCombo)" in barra
assert barra.count("poligonos = True") == 2
assert "FillCombo(self.ctrl, self.toolbar)" in plugin and "FillTransparencyCombo(self.ctrl, self.toolbar)" in plugin
assert "'fill', 'Color de relleno'" in plugin and "'filltr', 'Transparencia de relleno'" in plugin
print("ok barra")

# ---- 5. botones: de fábrica en Yaguá Capas y, una vez, en lo ya guardado ---------------
from nucleo import botones as BT  # noqa: E402
assert dict(BT.DEFECTO["qgis"])["Yaguá Capas"][-3:] == ("capas:lineweight", "capas:fill", "capas:filltr")
YA = ["capas-ingecad", "capas-panel", "capas-banco"]


def guardado(cats, ocultos=()):
    BT.archivo().parent.mkdir(parents=True, exist_ok=True)
    BT.archivo().write_text(json.dumps({"qgis": {"categorias": cats, "ocultos": list(ocultos),
                                                 "migraciones": YA}}), encoding="utf-8")
    return BT.leer("qgis")


m = guardado([{"nombre": "Yaguá Capas", "botones": ["capas:layprops", "capas:capa", "capas:color",
                                                    "capas:linetype", "capas:lineweight"]}])
assert m["categorias"][0]["botones"][-3:] == ["capas:lineweight", "capas:fill", "capas:filltr"], m
assert json.loads(BT.archivo().read_text(encoding="utf-8"))["qgis"]["migraciones"] == YA + ["capas-relleno"]
# el grosor en otra barra de Fernando: el relleno va al lado
m = guardado([{"nombre": "Yaguá Capas", "botones": ["capas:layprops"]},
              {"nombre": "Mía", "botones": ["capas:lineweight", "dibujo:line"]}])
assert m["categorias"][1]["botones"] == ["capas:lineweight", "capas:fill", "capas:filltr", "dibujo:line"], m
# ya los tenía en algún lado: no se tocan
m = guardado([{"nombre": "Yaguá Capas", "botones": ["capas:lineweight"]},
              {"nombre": "Otra", "botones": ["capas:filltr"]}])
assert m["categorias"][0]["botones"] == ["capas:lineweight"] and m["categorias"][1]["botones"] == ["capas:filltr"]
# una sola vez: si después los saca, quedan afuera
cats = [{"nombre": "Yaguá Capas", "botones": ["capas:lineweight"]}]
BT.archivo().write_text(json.dumps({"qgis": {"categorias": cats, "ocultos": [],
                                             "migraciones": YA + ["capas-relleno"]}}), encoding="utf-8")
assert BT.leer("qgis")["categorias"][0]["botones"] == ["capas:lineweight"]
# los dos programas con el mismo núcleo
for prog in ("QGIS", "INGECAD"):
    assert (ROOT / prog / "codigo/geocad/botones.py").read_text(encoding="utf-8") == \
        (ROOT / "COMUN/nucleo/botones.py").read_text(encoding="utf-8"), prog
print("ok botones")
print("TODO OK")
