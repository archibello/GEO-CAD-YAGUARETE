"""GEORREF de IngeCAD en QGIS (3.93.0), sin Qt: las cuentas son las del núcleo
(georref_cuentas, las mismas de IngeCAD: el GEORREF de IngeCAD las importa de ahí);
rehacer la imagen sin PIL (georref_rehacer, numpy) da lo mismo que IngeCAD con PIL
(Vecino idéntico; Lineal y Cúbica a lo sumo ±1 por redondeo) con Proyectiva,
Polinómica 2 y Thin Plate Spline; la tabla de QGIS es la de IngeCAD, sin «sólo el
dibujo» y con el botón del Georreferenciador de QGIS. La orden, la tabla y la capa
de verdad: ventana/banco_georref_orden_qgis.py; el Georreferenciador de QGIS:
ventana/banco_georref_qgis.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import builtins, os, sys, tempfile
from pathlib import Path
from importlib import import_module
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
ROOT = Path(__file__).resolve().parents[2]
QG = ROOT / "QGIS" / "codigo" / "geocad"
import numpy as np

# ---- 1. el núcleo y el rehacer, sin PIL --------------------------------------------------------
_imp = builtins.__import__
def sin_pil(nombre, *a, **k):
    if nombre == "PIL" or nombre.startswith("PIL."):
        raise ImportError("sin PIL, como QGIS")
    return _imp(nombre, *a, **k)
builtins.__import__ = sin_pil
sys.path.insert(0, str(ROOT / "COMUN"))
GC = import_module("nucleo.georref_cuentas")
GR = import_module("nucleo.georref_rehacer")
a = np.zeros((60, 80, 4), np.uint8); a[..., 3] = 255; a[..., :3] = 200; a[20:24, :, :3] = 0
src = [(0, 0), (80, 0), (80, -60), (0, -60), (40, -30), (20, -50)]
dst = [(1000 + 0.5 * x + 0.02 * y, 2000 + 0.5 * y + 0.01 * x + 0.0003 * x * x) for x, y in src]
for met in ("proyectiva", "polinomica2", "tps"):
    nv, coef, tam = GR.rehacer_arreglo(a, GC.ajustar(met, src, dst), "cubica")
    assert nv.shape == (tam[1], tam[0], 4) and nv[..., 3].max() == 255, met
    assert (nv[..., 3] == 0).any() or met == "proyectiva"      # transparente alrededor
try:
    GR.rehacer_arreglo(a, GC.ajustar("proyectiva", src[:4], [(0, 0), (1, 0), (0, 1), (1, 1)]))
    raise SystemExit("tenía que fallar")
except GC.AjusteError:
    pass
for nombre in ("georref_cuentas.py", "georref_rehacer.py"):
    cuerpo = (ROOT / "COMUN" / "nucleo" / nombre).read_text(encoding="utf-8").split('"""', 2)[2]
    assert "import PIL" not in cuerpo and "from PIL" not in cuerpo and "ezdxf" not in cuerpo \
        and "PySide" not in cuerpo, nombre
builtins.__import__ = _imp
print("ok sin PIL")

# ---- 2. lo mismo que IngeCAD ----------------------------------------------------------------------
from core.plugins import load_plugin
from PIL import Image
lp = load_plugin(ROOT / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
G = import_module("ingecad_plugin_geocad.georref")
GI = import_module("ingecad_plugin_geocad.georref_imagen")
GRi = import_module("ingecad_plugin_geocad.georref_rehacer")
GCi = import_module("ingecad_plugin_geocad.georref_cuentas")
assert G.ajustar is GCi.ajustar and G.escribir_points is GCi.escribir_points and G.METODOS is GCi.METODOS
for n in ("nucleo/georref_cuentas.py", "nucleo/georref_rehacer.py"):
    nombre = n.split("/")[1]
    assert (ROOT / "COMUN" / n).read_bytes() == (QG / nombre).read_bytes() == \
        (ROOT / "INGECAD" / "codigo" / "geocad" / nombre).read_bytes(), nombre
b = np.zeros((120, 160, 4), np.uint8); b[..., 3] = 255
b[..., 0] = (np.arange(160)[None, :] * 1.5).astype(np.uint8); b[..., 1] = (np.arange(120)[:, None] * 2).astype(np.uint8)
b[..., 2] = 90; b[30:35, :, :3] = 0; b[:, 70:74, :3] = 0
d = Path(tempfile.mkdtemp()); orig = d / "p.png"; Image.fromarray(b, "RGBA").save(orig)
src = [(0, 0), (160, 0), (160, -120), (0, -120), (80, -60), (40, -30), (120, -90), (20, -100), (140, -20)]
dst = [(1000 + 0.5 * x + 0.05 * y + 0.0004 * x * x, 2000 + 0.5 * y + 0.03 * x + 0.0002 * x * y) for x, y in src]
for met in ("proyectiva", "polinomica2", "tps"):
    mod = G.ajustar(met, src, dst)
    for rem, tope in (("vecino", 0), ("lineal", 1), ("cubica", 1)):
        sal = GI.rutas(orig, "transparente", d / f"o_{met}_{rem}")
        coef, tam = GI.rehacer(orig, sal, mod, rem)
        pil = np.asarray(Image.open(sal[0][0]).convert("RGBA")).astype(int)
        nv, coef2, tam2 = GRi.rehacer_arreglo(b, mod, rem)
        assert tam == tam2 and max(abs(u - v) for u, v in zip(coef, coef2)) < 1e-9, (met, rem)
        assert np.abs(pil - nv.astype(int)).max() <= tope, (met, rem, np.abs(pil - nv.astype(int)).max())
# los fondos, como IngeCAD
trans = GRi.rehacer_arreglo(b, G.ajustar("tps", src, dst))[0]
afuera = trans[..., 3] == 0
assert afuera.any()
for fondo, color in (("blanco", (255, 255, 255)), ("negro", (0, 0, 0))):
    f = GRi.con_fondo(trans, fondo)
    assert (f[..., 3] == 255).all() and (f[afuera][:, :3] == color).all(), fondo
assert GRi.con_fondo(trans, "transparente") is trans
print("ok igual que IngeCAD")

# ---- 3. la orden y la tabla de QGIS ----------------------------------------------------------------
orden = (QG / "dibujo" / "georref_qgis.py").read_text(encoding="utf-8")
ui = (QG / "dibujo" / "georref_ui_qgis.py").read_text(encoding="utf-8")
assert "from .. import georref_cuentas as G" in orden and "from .. import georref_rehacer as GR" in orden
assert "SALIDAS = {k: v for k, v in G.SALIDAS.items() if k != \"dibujo\"}" in orden
assert "CommandSpec('GEORREF', ('GEORREF', 'RUBBERSHEET', 'AJUSTEIMAGEN'), GeorrefCommand" in orden
assert '("Abrir en el Georreferenciador de QGIS", self._nativo)' in ui and "PySide" not in ui
ing_ui = (ROOT / "INGECAD" / "codigo" / "geocad" / "georref_ui.py").read_text(encoding="utf-8")
for texto in ("Tipo de transformación:", "Remuestreo:", "Al transformar, guardar:", "Guardar copia geo como...",
              "Fondo de la imagen rehecha:", "Cargar .points...", "Guardar .points...", "Marcar más pares",
              "Transformar", "GEORREF — Tabla de puntos — GEO-CAD-YAGUARETÉ"):
    assert texto in ui and texto in ing_ui, texto
for texto in ("Punto en la imagen %d [Cargar puntos/Deshacer] <Intro: tabla de puntos>", "Punto de destino %d [Deshacer]"):
    assert texto in orden, texto
plugin = (QG / "dibujo" / "plugin.py").read_text(encoding="utf-8")
assert "georref_qgis.instalar(self)" in plugin and "Ajustar imagen con puntos de control (GEORREF)" in plugin
assert "CommandSpec('GEORREF'" not in (QG / "dibujo" / "imagen_geo_qgis.py").read_text(encoding="utf-8")
print("ok orden y tabla")

print("TODO OK GEORREF QGIS")
