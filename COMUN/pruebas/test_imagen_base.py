"""Imagen base en las presentaciones (3.71.0): las cuentas, sin QGIS. La herramienta
de verdad (arrastre, bloqueo, recorte) se mide en ventana/banco_imagen_base_qgis_real.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [HERE, os.path.join(HERE, "fake_qgis"), str(RAIZ / "QGIS" / "codigo")]
from geocad import imagen_base as IB, botones, modulos

# ---- partir: lo que está arriba de la imagen queda arriba; ella y lo de abajo, abajo
es = lambda c: c.startswith("xyz")
assert IB.partir_capas(["lineas", "polig", "xyz", "fondo"], es) == (["lineas", "polig"], ["xyz", "fondo"])
assert IB.partir_capas(["xyz"], es) == ([], ["xyz"])
assert IB.partir_capas(["a", "xyz1", "xyz2"], es) == (["a"], ["xyz1", "xyz2"])    # la de más arriba
assert IB.partir_capas(["a", "b"], es) is None

# ---- corrimiento y extensión
fr, ba = (100.0, 200.0, 300.0, 400.0), (103.0, 195.0, 303.0, 395.0)
assert IB.corrimiento(fr, ba) == (3.0, -5.0)
assert IB.mover(fr, 3.0, -5.0) == ba
assert IB.corrimiento(fr, fr) == (0.0, 0.0)

# ---- recorte: 254 mm a 100 dpi son 1000 píxeles; 0,2 unidades por píxel
ext = (1000.0, 2000.0, 1200.0, 2100.0)
pl = IB.plan_recorte(ext, ext, 254.0, 100.0)
assert (pl["ancho"], pl["alto"]) == (1000, 500) and abs(pl["tam"] - 0.2) < 1e-12
assert pl["destino"] == (1000.0, 2000.0, 1200.0, 2100.0) or \
    max(abs(a - b) for a, b in zip(pl["destino"], ext)) < 1e-6
assert IB.geotransform(pl["destino"], pl["tam"]) == (1000.0, pl["tam"], 0.0, pl["destino"][3], 0.0, -pl["tam"])
# el destino cierra en píxeles enteros: el alto no da justo y se ajusta desde arriba
ext2 = (0.0, 0.0, 100.0, 33.37)
pl = IB.plan_recorte(ext2, ext2, 100.0, 25.4)
assert (pl["ancho"], pl["alto"]) == (100, 33)
assert abs(pl["destino"][3] - 33.37) < 1e-9 and abs(pl["destino"][1] - 0.37) < 1e-9
# mapa girado: lo visible es mayor que la extensión, con el mismo píxel
pl = IB.plan_recorte((-10.0, -10.0, 110.0, 60.0), (0.0, 0.0, 100.0, 50.0), 100.0, 25.4)
assert (pl["ancho"], pl["alto"]) == (120, 70) and abs(pl["tam"] - 1.0) < 1e-12
try:
    IB.plan_recorte(ext, (5.0, 0.0, 5.0, 1.0), 100.0, 300.0)
except ValueError:
    pass
else:
    raise AssertionError("una extensión vacía no se recorta")

# ---- la imagen guardada excede al recorte en un 25 % de área, centrada y con sus proporciones
am = IB.ampliar((100.0, 200.0, 300.0, 300.0))
assert abs((am[2] - am[0]) * (am[3] - am[1]) - 20000.0 * 1.25) < 1e-6
assert abs(am[0] + am[2] - 400.0) < 1e-9 and abs(am[1] + am[3] - 500.0) < 1e-9
assert abs((am[2] - am[0]) / (am[3] - am[1]) - 2.0) < 1e-9
assert IB.EXCESO_AREA == 0.25 and IB.ampliar((1.0, 2.0, 3.0, 4.0), 0.0) == (1.0, 2.0, 3.0, 4.0)

assert IB.nombre_archivo("Mapa 1") == "imagen_base_Mapa_1.tif"
assert IB.nombre_archivo("/../") == "imagen_base_mapa.tif"
assert "X +1.500 m" in IB.texto_corrimiento(1.5, -2.0, "m") and "Y -2.000 m" in IB.texto_corrimiento(1.5, -2.0, "m")

# ---- los tres botones van al banco Edición y a ninguna barra de fábrica
for b in ("geocad:imgbase_mover", "geocad:imgbase_bloquear", "geocad:imgbase_guardar"):
    assert botones.banco_de("qgis", b) == "Edición"
for icono in ("mover", "bloquear", "guardar"):
    assert (IB.ICONOS / ("imagen_base_%s.png" % icono)).is_file()
assert [m for m in modulos.catalogo("qgis") if m.clave == "imagen_base"][0].defecto
assert "imagen_base" not in [m.clave for m in modulos.catalogo("ingecad")]    # sólo QGIS

# fuera del menú GeoCAD: en plugin.py las acciones se crean a mano, sin add()
fuente = (RAIZ / "QGIS" / "codigo" / "geocad" / "plugin.py").read_text(encoding="utf-8")
assert 'add("imgbase' not in fuente and "self.imagen_base.respaldo()" in fuente

print("TODO OK imagen base")
