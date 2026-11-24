"""ASPECTOIMAGEN en QGIS (3.91.0), sin Qt: la cuenta del núcleo (aspecto_cuentas, sólo
numpy, sin PIL: el Python de QGIS no lo trae) da lo mismo que ASPECTOIMAGEN de
IngeCAD; la ventana de QGIS es la de IngeCAD sin PIL y sin «Fondo blanco»; el botón
en «Yaguá Imagenes» (fábrica, banco y migración). La orden, la copia, la capa y la
ventana de verdad los prueba ventana/banco_aspecto_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import builtins, json, os, sys, tempfile
from pathlib import Path
from importlib import import_module
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
ROOT = Path(__file__).resolve().parents[2]
QG = ROOT / "QGIS" / "codigo" / "geocad"
import numpy as np

# ---- 1. el núcleo, sin PIL --------------------------------------------------------------------
_imp = builtins.__import__
def sin_pil(nombre, *a, **k):
    if nombre == "PIL" or nombre.startswith("PIL."):
        raise ImportError("sin PIL, como QGIS")
    return _imp(nombre, *a, **k)
builtins.__import__ = sin_pil
sys.path.insert(0, str(ROOT / "COMUN"))
AC = import_module("nucleo.aspecto_cuentas")
assert "PIL" not in (ROOT / "COMUN" / "nucleo" / "aspecto_cuentas.py").read_text(encoding="utf-8").split('"""', 2)[2]
# un plano chico: papel blanco, una línea negra, una línea gris tenue, un punto suelto
a = np.full((60, 80, 4), 255, dtype=np.uint8)
a[30, 5:75, :3] = 0                      # línea negra
a[10, 5:75, :3] = 170                    # línea tenue
a[50, 60, :3] = 0                        # un punto de polvo, solo
h = AC.procesar_arreglo(a, {})
assert h.shape == a.shape and h.dtype == np.uint8
assert h[0, 0, 3] == 0 and h[30, 40, 3] == 255 and tuple(h[30, 40, :3]) == (0, 0, 0)
assert 0 < h[10, 40, 3] < 255                            # lo tenue, semitransparente
neg = AC.procesar_arreglo(a, {"lineas": "negativo"})
assert tuple(neg[30, 40, :3]) == (255, 255, 255)
col = AC.procesar_arreglo(a, {"lineas": "color", "color": "#00ff00"})
assert tuple(col[30, 40, :3]) == (0, 255, 0)
fin = AC.procesar_arreglo(a, {"final": True})
assert (fin[..., 3] == 255).all() and tuple(fin[0, 0, :3]) == (255, 255, 255)
op = AC.procesar_arreglo(a, {"opacidad": 50})
assert abs(int(op[30, 40, 3]) - 128) <= 1
con = AC.procesar_arreglo(a, {"contraste": 300})
assert con[10, 40, 3] > h[10, 40, 3]                     # la tenue se refuerza
lim = AC.procesar_arreglo(a, {"limpiar": True, "distancia": 4, "tolerancia": 30})
assert lim[50, 60, 3] == 0 and lim[30, 40, 3] == 255     # el polvo se va, la línea queda
roja = AC.procesar_arreglo(a, {"limpiar": True, "distancia": 4, "tolerancia": 30}, marcar=True)
assert tuple(roja[50, 60]) == (255, 0, 0, 255)
hecho = [0.0]
AC.procesar_arreglo(a, {"limpiar": True}, hecho=hecho)
assert hecho[0] == 1.0
assert AC.describir({"lineas": "negativo", "opacidad": 80}).startswith("fondo transparente")
print("ok núcleo sin PIL")
builtins.__import__ = _imp

# ---- 2. lo mismo que IngeCAD (con PIL) ------------------------------------------------------
from core.plugins import load_plugin
from PIL import Image
lp = load_plugin(ROOT / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
A = import_module("ingecad_plugin_geocad.aspecto")
assert A.normalizar is import_module("ingecad_plugin_geocad.aspecto_cuentas").normalizar
rng = np.random.default_rng(7)
b = rng.integers(0, 256, (90, 70, 4), dtype=np.uint8)
b[..., 3] = 255
for v in ({}, {"lineas": "negativo", "contraste": 250}, {"lineas": "color", "transparente": False},
          {"limpiar": True, "distancia": 3, "tolerancia": 40, "final": True}, {"blanco": 60, "opacidad": 30}):
    ing = np.asarray(A.procesar(Image.fromarray(b, "RGBA"), v))
    assert (ing == AC.procesar_arreglo(b, v)).all(), v
# IngeCAD sigue teniendo los nombres de siempre
for n in ("DEFECTO", "SUFIJO_FINAL", "manchas", "_franja", "describir", "AspectoError", "ROJO"):
    assert hasattr(A, n), n
print("ok igual que IngeCAD")

# ---- 3. la ventana de QGIS: la de IngeCAD, sin PIL y sin Fondo blanco ------------------------
ui = (QG / "dibujo" / "aspecto_ui_qgis.py").read_text(encoding="utf-8")
cuerpo = ui.split('"""', 2)[2]
assert "PIL" not in cuerpo and "fondo_blanco" not in cuerpo and "CAPA_FONDO" not in cuerpo
assert "U lo deshace" not in cuerpo and "Volver al original" in cuerpo and "Entregar imagen final..." in cuerpo
assert "from qgis.PyQt import QtCore, QtGui, QtWidgets" in cuerpo
ing_ui = (ROOT / "INGECAD" / "codigo" / "geocad" / "aspecto_ui.py").read_text(encoding="utf-8")
for texto in ("Blanco que se borra", "Limpiar manchas", "Ver en rojo lo que se borra", "Contraste",
              "Valores iniciales", "Fondo de la vista previa:", "Satélite (oscuro)"):
    assert texto in cuerpo and texto in ing_ui, texto
orden = (QG / "dibujo" / "aspecto_qgis.py").read_text(encoding="utf-8")
assert "from .. import aspecto_cuentas as A" in orden and "PROPIEDAD = 'geocad/aspecto'" in orden
assert "('ASPECTOIMAGEN', ('ASPECTOIMAGEN', 'IMAGEASPECT', 'ASPECTO')" in orden
assert (QG / "aspecto_cuentas.py").read_bytes() == (ROOT / "COMUN" / "nucleo" / "aspecto_cuentas.py").read_bytes()
print("ok ventana")

# ---- 4. el botón: fábrica, banco y migración --------------------------------------------------
from nucleo import botones as BT
fab = dict(BT.DEFECTO["qgis"])["Yaguá Imagenes"]
assert fab[:4] == ("dibujo:insertgeo", "dibujo:georref", "dibujo:exportgeo", "dibujo:aspecto")   # 3.92.0: y LIMPIARPLANO
assert fab[-1] == "dibujo:pasteimage"
ing_bar = dict(BT.DEFECTO["ingecad"])["Yaguá Imagenes"]
assert ing_bar.index("EXPORTARGEO") < ing_bar.index("ASPECTOIMAGEN")
assert "dibujo:aspecto" in BT.TEMA_BANCO["qgis"]["Edición"] and "ASPECTOIMAGEN" in BT.TEMA_BANCO["ingecad"]["Edición"]
hechas = [m for m in BT.MIGRACIONES["qgis"] if m != "aspecto-qgis"]
BT.archivo().parent.mkdir(parents=True, exist_ok=True)


def migrar(cats, ya=hechas):
    BT.archivo().write_text(json.dumps({"qgis": {"categorias": cats, "migraciones": ya}}), encoding="utf-8")
    return [(c["nombre"], c["botones"]) for c in BT.leer("qgis")["categorias"]]


assert migrar([{"nombre": "Yaguá Imagenes", "botones": ["dibujo:insertgeo", "dibujo:exportgeo", "dibujo:pasteimage"]}]) == [
    ("Yaguá Imagenes", ["dibujo:insertgeo", "dibujo:exportgeo", "dibujo:aspecto", "dibujo:pasteimage"])]
assert migrar([{"nombre": "A", "botones": ["dibujo:pasteimage"]}]) == [("A", ["dibujo:aspecto", "dibujo:pasteimage"])]
assert migrar([{"nombre": "A", "botones": ["dibujo:line"]}]) == [("A", ["dibujo:line"])]
assert migrar([{"nombre": "A", "botones": ["dibujo:aspecto"]}, {"nombre": "B", "botones": ["dibujo:exportgeo"]}]) == [
    ("A", ["dibujo:aspecto"]), ("B", ["dibujo:exportgeo"])]
assert migrar([{"nombre": "A", "botones": ["dibujo:exportgeo"]}], list(BT.MIGRACIONES["qgis"])) == [
    ("A", ["dibujo:exportgeo"])]
BT.restablecer("qgis")
plugin = (QG / "dibujo" / "plugin.py").read_text(encoding="utf-8")
assert plugin.index("_action('exportgeo'") < plugin.index("_action('aspecto'") < plugin.index("_action('pasteimage'")
assert (QG / "dibujo" / "icons" / "aspecto.svg").is_file()
print("ok botón")

print("TODO OK ASPECTO QGIS")
