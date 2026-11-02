"""ZOOM (Z), ENCUADRE (P), REGEN (RE), REDIBUJA (R) e IGUALARPROP (MA) de IngeCAD
en Dibujo de QGIS (3.61.0), sin Qt: las opciones y cuentas de ZOOM, qué copia
IGUALARPROP, los mismos alias que IngeCAD, los comandos registrados y sus
botones sólo en el banco Dibujo CAD. Lo que se ve en QGIS lo prueba
ventana/banco_vista_igualar_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, importlib.util, re
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"
DIBUJO = GEOCAD / "dibujo"


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


V = cargar("vista", DIBUJO / "vista.py")
I = cargar("igualar", DIBUJO / "igualar.py")


def cerca(a, b, tol=1e-9):
    return len(a) == len(b) and all(abs(x - y) < tol for x, y in zip(a, b))


# ---- 1. las opciones de ZOOM: las de IngeCAD 0.7.0 y las que pidió Fernando -----------------
for escrito, opt in (("E", "E"), ("extensión", "E"), ("_EXTENTS", "E"), ("T", "T"), ("todo", "T"),
                     ("A", "T"), ("C", "C"), ("centro", "C"), ("P", "P"), ("previo", "P"),
                     ("V", "V"), ("W", "V"), ("ventana", "V"), ("S", "S"), ("escala", "S"),
                     ("SI", "SI"), ("siguiente", "SI"), ("O", "O"), ("objeto", "O"),
                     ("AM", "AM"), ("ampliar", "AM"), ("R", "R"), ("reducir", "R")):
    assert V.opcion(escrito) == opt, (escrito, V.opcion(escrito))
assert V.opcion("XYZ") is None and V.opcion("") is None
claves = [k for k, _l in V.OPCIONES]
assert claves == ["T", "C", "E", "P", "SI", "S", "V", "O", "AM", "R"] and V.DEFECTO == "Extensión"
assert all(V.opcion(k) == k for k in claves), "cada opción del pedido se puede elegir con su clave"
print("ok opciones de ZOOM (Todo, Centro, Extensión, Previo, Siguiente, Escala, Ventana, Objeto, Ampliar, Reducir)")

# ---- 2. lo que ZOOM toma además de una palabra -------------------------------------------------
assert V.factor("2X") == ("veces", 2.0) and V.factor("0.5x") == ("veces", 0.5)
assert V.factor("0,5X") == ("veces", 0.5), "con X la coma es decimal"
assert V.factor("2") == ("todo", 2.0) and V.factor("0.25") == ("todo", 0.25)
assert V.factor("1:500") == ("escala", 500.0) and V.factor("1 : 2500") == ("escala", 2500.0)
assert V.factor("1/100XP") == ("xp", None) and V.factor("2XP") == ("xp", None)
assert V.factor("0,5") is None, "un número con coma es una esquina (como IngeCAD)"
assert V.factor("10,20") is None and V.factor("E") is None and V.factor("0X") is None
assert V.factor("0") is None and V.factor("-2") is None
print("ok nX, n, 1:n y nXP; 0,5 es una esquina")

# ---- 3. las cuentas de la vista ------------------------------------------------------------------
assert V.rect_ventana((5, 8), (1, 2)) == (1, 2, 5, 8)
assert V.rect_ventana((3, 3), (3, 3)) is None
assert V.rect_ventana((0, 0), (4, 0)) == (0, 0, 4, 0), "una raya también sirve (QGIS la ajusta)"
assert cerca(V.rect_centro((10, 20), 4, 1.5), (7, 18, 13, 22))
assert cerca(V.rect_escalado((0, 0, 10, 4), 2), (2.5, 1, 7.5, 3)), "2 = el doble de cerca"
assert cerca(V.rect_escalado((0, 0, 10, 4), 0.5), (-5, -2, 15, 6))
u = V.union([(0, 0, 10, 10), (20, 5, 30, 8)])
assert cerca(u, (-1.5, -1.5, 31.5, 11.5)), u            # 5 % del lado mayor de margen
p = V.union([(5, 5, 5, 5)], minimo=2)
assert cerca(p, (3.9, 3.9, 6.1, 6.1)), p                # un punto: lado mínimo
r = V.union([(0, 3, 10, 3)])
assert r[3] - r[1] > 10, "una línea horizontal no queda como una raya"
assert V.union([None]) is None and V.union([]) is None
assert V.altura("", 50) == 50 and V.altura("2X", 50) == 25 and V.altura("12,5", 50) == 12.5
for malo in ("0", "-3", "0X", "abc"):
    try:
        V.altura(malo, 50)
        raise AssertionError(malo)
    except ValueError:
        pass
assert V.PASO == 2.0
print("ok Ventana, Centro, Escala, Objeto (unión con margen) y altura de Centro")

# ---- 3b. el historial de Previo / Siguiente (QGIS 4 no anota lo que cambia un complemento) ------
H = V.Historial()
assert H.previo() is None and H.siguiente() is None and H.actual() is None
H.anotar((0, 0, 10, 10), 0.0)
H.cortar(); H.anotar((0, 0, 20, 20), 1.0); H.cortar()          # un comando de vista
for k, t in enumerate((5.0, 5.1, 5.2, 5.3)):                    # la rueda: una ráfaga
    H.anotar((0, 0, 30 + k, 30 + k), t)
assert len(H.vistas) == 3 and H.actual() == (0, 0, 33, 33), H.vistas
H.anotar((0, 0, 33, 33), 9.0)
assert len(H.vistas) == 3, "la misma vista no se repite"
H.anotar((1, 1, 2, 2), 9.0)                                       # después de la pausa: otra
assert len(H.vistas) == 4
assert H.previo() == (0, 0, 33, 33) and H.previo() == (0, 0, 20, 20) and H.previo() == (0, 0, 10, 10)
assert H.previo() is None
assert H.siguiente() == (0, 0, 20, 20)
H.anotar((7, 7, 8, 8), 20.0)                                      # una vista nueva corta lo siguiente
assert H.siguiente() is None and H.vistas[-1] == (7, 7, 8, 8) and len(H.vistas) == 3
H2 = V.Historial()
for k in range(80):
    H2.cortar(); H2.anotar((0, 0, k + 1, k + 1), float(k))
assert len(H2.vistas) == V.Historial.MAXIMO and H2.actual() == (0, 0, 80, 80)
print("ok historial de vistas: ráfagas de la rueda, Previo, Siguiente y tope")

# ---- 4. IGUALARPROP: qué se copia ---------------------------------------------------------------
lin = {"LAYER_CODE": "CALLES", "CAD_COLOR": "#FF0000", "CAD_LTYPE": "DASHED", "CAD_LW": 0.35}
assert I.a_copiar(lin, False, False) == {"LAYER_CODE": "CALLES", "CAD_COLOR": "#ff0000",
                                          "CAD_LTYPE": "DASHED", "CAD_LW": 0.35}
# PorCapa (vacío) se copia como PorCapa
assert I.a_copiar({"LAYER_CODE": "", "CAD_COLOR": "", "CAD_LTYPE": None, "CAD_LW": None},
                  False, False) == {"LAYER_CODE": "0", "CAD_COLOR": None, "CAD_LTYPE": None, "CAD_LW": None}
# a un texto: la capa y el color (en COLOR), no el tipo ni el grosor
assert I.a_copiar(lin, False, True) == {"LAYER_CODE": "CALLES", "COLOR": "#ff0000"}
# a un punto: sin tipo de línea
assert I.a_copiar(lin, False, False, destino_punto=True) == {"LAYER_CODE": "CALLES", "CAD_COLOR": "#ff0000",
                                                              "CAD_LW": 0.35}
# entre textos: además altura, fuente y negrita (si la capa de destino los tiene)
txt = {"LAYER_CODE": "ROTULOS", "COLOR": "#00FF00", "ALTURA": 2.5, "FUENTE": "Arial", "NEGRITA": "1"}
assert I.a_copiar(txt, True, True) == {"LAYER_CODE": "ROTULOS", "COLOR": "#00ff00", "ALTURA": 2.5,
                                        "FUENTE": "Arial", "NEGRITA": "1"}
assert I.a_copiar(txt, True, True, destino_campos=["LAYER_CODE", "COLOR", "ALTURA"]) == \
    {"LAYER_CODE": "ROTULOS", "COLOR": "#00ff00", "ALTURA": 2.5}
# de un texto a una línea: capa y color en CAD_COLOR, nada de texto
assert I.a_copiar(txt, True, False) == {"LAYER_CODE": "ROTULOS", "CAD_COLOR": "#00ff00"}
# una capa sin campos CAD: nada que copiar
assert I.a_copiar({}, False, False) == {}
assert I.a_copiar({"CAD_COLOR": "#123456"}, False, False) == {"CAD_COLOR": "#123456"}, "sólo lo que tiene"
assert set(I.CAMPOS) >= {"LAYER_CODE", "CAD_COLOR", "COLOR", "CAD_LTYPE", "CAD_LW", "ALTURA", "FUENTE", "NEGRITA"}
print("ok IGUALARPROP: capa CAD, color, tipo y grosor; entre textos altura, fuente y negrita")

# ---- 5. los mismos alias que IngeCAD (el de PYTHONPATH: 0.6.8.2 o 0.6.7) -------------------------
from core import aliases as ing
A = ing.DEFAULT_ALIASES
assert (A["Z"], A["P"], A["RE"], A["R"], A["MA"]) == ("ZOOM", "PAN", "REGEN", "REDRAW", "MATCHPROP")
plugin_src = (DIBUJO / "plugin.py").read_text(encoding="utf-8")


def alias_de(nombre):
    m = re.search(r"CommandSpec\('%s', \(([^)]*)\)" % nombre, plugin_src)
    assert m, nombre
    return [a.strip().strip("'") for a in m.group(1).replace("\n", " ").split(",") if a.strip()]


for corto, nombre in (("Z", "ZOOM"), ("P", "PAN"), ("RE", "REGEN"), ("R", "REDRAW"), ("MA", "MATCHPROP")):
    assert corto in alias_de(nombre) and A[corto] == nombre, (corto, nombre)
assert "IGUALARPROP" in alias_de("MATCHPROP") and "ENCUADRE" in alias_de("PAN")
assert "REDIBUJA" in alias_de("REDRAW")
# ningún otro comando de Dibujo usa esos alias
todos = re.findall(r"CommandSpec\('([A-Z_-]+)', \(([^)]*)\)", plugin_src +
                   (DIBUJO / "commands.py").read_text(encoding="utf-8"))
edit_src = (DIBUJO / "edit_commands.py").read_text(encoding="utf-8")
todos += re.findall(r"\('([A-Z_-]+)', \(([^)]*)\), \w+Command", edit_src)
for nombre, als in todos:
    als = [a.strip().strip("'") for a in als.split(",")]
    for corto in ("Z", "P", "RE", "R", "RA", "MA"):
        if corto in als:
            assert nombre in ("ZOOM", "PAN", "REGEN", "REDRAW", "MATCHPROP"), (nombre, corto)
print("ok Z, P, RE, R y MA como en IngeCAD; sin choques con otros comandos")

# ---- 6. transparentes y «Z E» en una línea -----------------------------------------------------
cmd_src = (DIBUJO / "commands.py").read_text(encoding="utf-8")
assert "transparent=None" in cmd_src and "spec.transparent(self, args)" in cmd_src
assert "head, args = key.split(None, 1)" in cmd_src and "self.command.on_text(args)" in cmd_src
assert "transparent=zoom_transparente" in plugin_src and "transparent=pan_transparente" in plugin_src
assert "self.run_command(\"'\" + o)" in plugin_src, "los botones de vista no cortan el comando en curso"
# 3.61.1: en QGIS 4 (PyQt6) Flag & ~Flag es un int y QGIS rechaza flags(): se devuelve su tipo
vc = (DIBUJO / "vista_commands.py").read_text(encoding="utf-8")
assert "return type(f)(int(f) & ~int(enum(QgsMapTool, 'Flag', 'ShowContextMenu')))" in vc
assert "super().flags() & ~" not in vc
print("ok 'Z y 'P transparentes; Z E con la opción en la misma línea; flags() del tipo de QGIS")

# ---- 7. botones nuevos: en el banco Dibujo CAD, no en las categorías de fábrica -------------------
nuevos = ("zoom", "zoomwin", "zoomext", "zoomprev", "zoomobj", "pan", "regen", "matchprop")
for ico in nuevos:
    svg = DIBUJO / "icons" / (ico + ".svg")
    assert svg.is_file(), svg
    import xml.dom.minidom
    xml.dom.minidom.parse(str(svg))
    assert re.search(r"\('%s'," % ico, plugin_src), ico          # self._action(ico, ...)
assert plugin_src.count("toolbar=False)") == 2, "los de vista y el de IGUALARPROP, sin barra"
assert "if toolbar is not False:" in plugin_src
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import botones
for nombre, lista in botones.DEFECTO["qgis"]:
    for ico in nuevos:
        assert "dibujo:" + ico not in lista, (nombre, ico)
print("ok botones zoom, pan, regen y matchprop sólo en el banco (sin categoría de fábrica)")

# ---- 8. lo del panel Propiedades se comparte con IGUALARPROP ------------------------------------
pp = (DIBUJO / "properties_panel.py").read_text(encoding="utf-8")
assert "\ndef ensure_field(" in pp and "\ndef restyle(" in pp and "\ndef add_cad_layer_def(" in pp
assert "return ensure_field(lyr, name, kind, length, self.mgr.cmdline.echo)" in pp
ig = (DIBUJO / "igualar_commands.py").read_text(encoding="utf-8")
assert "from .properties_panel import CFG_KEY, TEXT_FLAG, add_cad_layer_def, ensure_field, restyle" in ig
print("ok IGUALARPROP usa lo del panel Propiedades (campos y capas CAD)")

print("TODO OK test_vista_igualar_qgis")
