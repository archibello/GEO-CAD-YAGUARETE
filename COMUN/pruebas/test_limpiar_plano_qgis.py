"""LIMPIARPLANO en QGIS (3.92.0), sin Qt: la receta del núcleo (limpieza.py) sin PIL
(el Python de QGIS no lo trae) pasa la misma prueba contra la referencia aprobada
por Fernando que la de IngeCAD, y casi no se aparta de la de PIL; las cuentas de
píxel <-> mapa de las zonas de sello y de la copia ×2 en el mismo lugar; el botón en
«Yaguá Imagenes» (fábrica, banco y migración). La orden, la copia y la capa de verdad
los prueba ventana/banco_limpiar_plano_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import builtins, json, os, sys, tempfile, types, importlib
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parents[1]
QG = ROOT / "QGIS" / "codigo" / "geocad"
import numpy as np

# ---- 1. la receta sin PIL ------------------------------------------------------------------------
_imp = builtins.__import__
def sin_pil(nombre, *a, **k):
    if nombre == "PIL" or nombre.startswith("PIL."):
        raise ImportError("sin PIL, como QGIS")
    return _imp(nombre, *a, **k)
builtins.__import__ = sin_pil
sys.path.insert(0, str(ROOT / "COMUN"))
L = importlib.import_module("nucleo.limpieza")
# un plano chico con una mancha de humedad suave y un trazo
a = np.full((80, 120, 4), 245, np.uint8); a[..., 3] = 255
yy, xx = np.mgrid[0:80, 0:120]
a[..., :3] = (245 - 40 * np.exp(-((xx - 60) ** 2 + (yy - 15) ** 2) / 300.0))[..., None].astype(np.uint8)
a[38:41, 10:110, :3] = 20
gris, alfa = L.limpiar_arreglo(a)
assert gris.shape == (160, 240) and gris.dtype == np.uint8 and alfa is None
assert gris[10, 10] == 255 and gris[30, 120] == 255              # papel y mancha: blanco
assert gris[79, 120] < 80                                        # el trazo sigue
b = a.copy(); b[:5, :5, 3] = 0
_g, alfa = L.limpiar_arreglo(b)
assert alfa is not None and alfa.shape == (160, 240) and alfa[0, 0] == 0 and alfa[50, 50] == 255
avance = []
L.limpiar_arreglo(a, avance=avance.append)
assert avance and avance[-1] == 0.95 and avance == sorted(avance)
assert L.gris_arreglo(np.array([[[255, 0, 0, 255], [0, 0, 0, 0]]], np.uint8)).tolist() == [[76, 255]]
builtins.__import__ = _imp
print("ok sin PIL")

# ---- 2. contra la referencia aprobada y contra la de PIL ------------------------------------------
from PIL import Image
DATOS = AQUI / "datos_limpiar_plano"
X0, Y0 = 1150, 1140
SELLO = (1215 - X0, 1195 - Y0, 1815 - X0, 1465 - Y0)
recorte = Image.open(DATOS / "recorte_original.png")
ref = np.asarray(Image.open(DATOS / "recorte_limpio_2x.png").convert("L")).astype(int)
o, _al = L.limpiar_arreglo(np.asarray(recorte.convert("RGBA")), [SELLO])
o = o.astype(int)
dif = np.abs(o - ref)
adentro = dif[40:-40, 40:-40]
print(f"   sin PIL: interior {100 * (adentro > 0).mean():.3f} % distintos, "
      f"{100 * (adentro > 8).mean():.3f} % con más de 8, media {adentro.mean():.3f}")
assert (adentro > 8).mean() <= 0.001 and adentro.mean() < 0.5 and (dif > 0).mean() <= 0.03   # lo de IngeCAD
pil = np.asarray(L.limpiar(recorte, [SELLO])).astype(int)
assert (pil != o).mean() < 0.005, (pil != o).mean()          # casi igual a la de PIL
g = np.asarray(L.gris(recorte))
assert np.array_equal(g, L.gris_arreglo(np.asarray(recorte.convert("RGBA"))))
amp = np.asarray(Image.fromarray(g).resize((600, 600), Image.LANCZOS)).astype(int)
assert np.abs(amp - L.ampliar_arreglo(g).astype(int)).max() <= 1
# IngeCAD usa el mismo módulo (el del núcleo, copiado)
assert (ROOT / "INGECAD" / "codigo" / "geocad" / "limpieza.py").read_bytes() == \
    (ROOT / "COMUN" / "nucleo" / "limpieza.py").read_bytes() == (QG / "limpieza.py").read_bytes()
print("ok contra la referencia aprobada")

# ---- 3. píxel <-> mapa ----------------------------------------------------------------------------
pkg = types.ModuleType("dib"); pkg.__path__ = [str(QG / "dibujo")]; sys.modules["dib"] = pkg
IG = importlib.import_module("dib.imagen_geo")
gt = (1000.0, 0.5, 0.0, 2050.0, 0.0, -0.5)
assert IG.a_pixel(gt, 1000, 2050) == (0, 0) and IG.a_pixel(gt, 1050, 2025) == (100, 50)
gg = IG.esquinas_gt((0, 1, 0, 0, 0, -1), 10, 10)
assert IG.gt_como_qgis((0, 1, 0, 0, 0, 1)) == (0.0, 1.0, 0.0, 0.0, 0.0, -1.0) and IG.gt_como_qgis(gt) == gt
import math
gir = (10.0, math.cos(0.5), math.sin(0.5), 20.0, math.sin(0.5), -math.cos(0.5))
x, y = IG.a_mapa(gir, 7, 3)
assert all(abs(u - v) < 1e-9 for u, v in zip(IG.a_pixel(gir, x, y), (7, 3)))
d2 = IG.gt_ampliada(gt, 2)
assert d2 == (1000.0, 0.25, 0.0, 2050.0, 0.0, -0.25)
assert IG.esquinas_gt(d2, 400, 200) == IG.esquinas_gt(gt, 200, 100)          # ×2, mismo lugar
print("ok píxel <-> mapa")

# ---- 4. el botón: fábrica, banco y migración ------------------------------------------------------
from nucleo import botones as BT
fab = dict(BT.DEFECTO["qgis"])["Yaguá Imagenes"]
assert fab == ("dibujo:insertgeo", "dibujo:georref", "dibujo:exportgeo", "dibujo:aspecto",
               "dibujo:limpiarplano", "dibujo:pasteimage")
ing = dict(BT.DEFECTO["ingecad"])["Yaguá Imagenes"]
assert ing.index("ASPECTOIMAGEN") + 1 == ing.index("LIMPIARPLANO")             # el orden de IngeCAD
assert "dibujo:limpiarplano" in BT.TEMA_BANCO["qgis"]["Edición"] and "LIMPIARPLANO" in BT.TEMA_BANCO["ingecad"]["Edición"]
hechas = [m for m in BT.MIGRACIONES["qgis"] if m != "limpiar-plano-qgis"]
BT.archivo().parent.mkdir(parents=True, exist_ok=True)


def migrar(cats, ya=hechas):
    BT.archivo().write_text(json.dumps({"qgis": {"categorias": cats, "migraciones": ya}}), encoding="utf-8")
    return [(c["nombre"], c["botones"]) for c in BT.leer("qgis")["categorias"]]


assert migrar([{"nombre": "I", "botones": ["dibujo:aspecto", "dibujo:pasteimage"]}]) == [
    ("I", ["dibujo:aspecto", "dibujo:limpiarplano", "dibujo:pasteimage"])]
assert migrar([{"nombre": "I", "botones": ["dibujo:pasteimage"]}]) == [("I", ["dibujo:limpiarplano", "dibujo:pasteimage"])]
assert migrar([{"nombre": "I", "botones": ["dibujo:line"]}]) == [("I", ["dibujo:line"])]
assert migrar([{"nombre": "I", "botones": ["dibujo:limpiarplano"]}, {"nombre": "J", "botones": ["dibujo:aspecto"]}]) == [
    ("I", ["dibujo:limpiarplano"]), ("J", ["dibujo:aspecto"])]
# desde la 3.90.0 (sin ASPECTOIMAGEN): los dos, en orden
assert migrar([{"nombre": "I", "botones": ["dibujo:exportgeo", "dibujo:pasteimage"]}],
              [m for m in hechas if m != "aspecto-qgis"]) == [
    ("I", ["dibujo:exportgeo", "dibujo:aspecto", "dibujo:limpiarplano", "dibujo:pasteimage"])]
BT.restablecer("qgis")
plugin = (QG / "dibujo" / "plugin.py").read_text(encoding="utf-8")
assert plugin.index("_action('aspecto'") < plugin.index("_action('limpiarplano'") < plugin.index("_action('pasteimage'")
assert (QG / "dibujo" / "icons" / "limpiarplano.svg").is_file()
orden = (QG / "dibujo" / "limpiar_plano_qgis.py").read_text(encoding="utf-8")
assert "('LIMPIARPLANO', ('LIMPIARPLANO', 'GEOLIMPIARPLANO', 'CLEANSCAN')" in orden
assert "from .. import limpieza as L" in orden and "PIL" not in orden.split('"""', 2)[2]
# 3.92.1 (Fernando: «QGIS no responde» durante la limpieza): la barra desde el primer momento
# y la cuenta en otro hilo, en las dos órdenes y al abrir la ventana del aspecto
aq = (QG / "dibujo" / "aspecto_qgis.py").read_text(encoding="utf-8")
assert "setMinimumDuration(0)" in aq and "threading.Thread" in aq and "processEvents(" in aq
assert "prog.trabajo('1/3  Limpiando el plano'" in orden and "_Progreso" not in orden
assert "prog.trabajo('2/4  Aplicando el aspecto'" in aq and "_Progreso" not in aq
assert 'prog.trabajo("Abriendo la imagen para la vista previa"' in (QG / "dibujo" / "aspecto_ui_qgis.py").read_text(encoding="utf-8")
print("ok botón y barra de avance")

print("TODO OK LIMPIARPLANO QGIS")
