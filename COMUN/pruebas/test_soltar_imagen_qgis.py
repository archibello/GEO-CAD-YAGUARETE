"""SOLTARIMAGEN en QGIS (3.88.0), sin Qt: las cuentas de la imagen arrastrada
(esquina, ancho, giro), el archivo de mundo con giro y la copia en
«<proyecto>_imagenes» sin tocar el original. La orden, el arrastre y la capa
ráster de verdad los prueba ventana/banco_soltar_imagen_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import math, os, tempfile, importlib.util
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"
spec = importlib.util.spec_from_file_location("soltar_imagen", GEOCAD / "dibujo" / "soltar_imagen.py")
SI = importlib.util.module_from_spec(spec); spec.loader.exec_module(SI)


def cerca(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ---- 1. las cuentas, iguales a las de IngeCAD --------------------------------------------------
assert SI.ancho_de((0, 0), (3, 4)) == 5 and abs(SI.angulo_de((0, 0), (0, 2)) - 90) < 1e-12
assert cerca(sum(SI.esquinas((10, 20), 100, 0, 200, 100), ()), (10, 20, 110, 20, 110, 70, 10, 70))
e = SI.esquinas((0, 0), 100, 90, 200, 100)
assert cerca(e[1], (0, 100)) and cerca(e[3], (-50, 0)) and SI.esquinas((0, 0), 0, 0, 1, 1) == []
assert SI.leer_giro("30") == 30 and SI.leer_giro("-12,5") == -12.5 and SI.leer_giro("45°") == 45
assert SI.leer_giro("x") is None and SI.leer_ancho("12,5") == 12.5 and SI.leer_ancho("Z") is None
assert SI.es_imagen("a.JPG") and SI.es_imagen("b.tiff") and not SI.es_imagen("c.shp")
print("ok cuentas")

# ---- 2. el archivo de mundo: cada esquina de la imagen cae en su lugar ------------------------
for giro in (0, 30, 90, -135):
    p1, ancho, px, py = (1000.0, 2000.0), 80.0, 400, 200
    A, D, B, E, C, F = SI.archivo_mundo(p1, ancho, giro, px, py)

    def mapa(col, fila):          # borde del píxel: centro - medio píxel
        return (A * (col - 0.5) + B * (fila - 0.5) + C, D * (col - 0.5) + E * (fila - 0.5) + F)
    esq = SI.esquinas(p1, ancho, giro, px, py)
    assert cerca(mapa(0, py), esq[0], 1e-6), (giro, mapa(0, py), esq[0])      # inf. izq. = p1
    assert cerca(mapa(px, py), esq[1], 1e-6) and cerca(mapa(px, 0), esq[2], 1e-6)
    assert cerca(mapa(0, 0), esq[3], 1e-6)
    assert abs(math.hypot(A, D) - ancho / px) < 1e-12                          # píxel cuadrado
assert SI.archivo_mundo((0, 0), 4, 0, 4, 2) == (1.0, 0.0, -0.0, -1.0, 0.5, 1.5)
assert SI.texto_mundo((1, 0, 0, -1, 0.5, 1.5)).splitlines()[3] == "-1.000000000000"
print("ok archivo de mundo")

# ---- 3. dónde va la copia ---------------------------------------------------------------------
assert SI.carpeta_destino("/obra/plano.qgz") == "/obra/plano_imagenes"
casa = tempfile.mkdtemp()
assert SI.carpeta_destino("", casa) == os.path.join(casa, "GeoCAD")
os.mkdir(os.path.join(casa, "Imágenes"))
assert SI.carpeta_destino(None, casa) == os.path.join(casa, "Imágenes", "GeoCAD")
assert SI.ruta_mundo("/a/b.png") == "/a/b.pgw" and SI.ruta_mundo("/a/b.JPG") == "/a/b.jgw"
assert SI.ruta_mundo("/a/b.tif") == "/a/b.tfw"
print("ok carpeta")

# ---- 4. la copia: el original no se toca, no se pisa otra ------------------------------------
orig_dir = Path(tempfile.mkdtemp()); orig = orig_dir / "fachada.png"
orig.write_bytes(b"\x89PNG imagen")
destino = Path(tempfile.mkdtemp()) / "obra_imagenes"
c1 = SI.copiar(orig, destino, (5, 5), 40, 30, 400, 200, 'PROJCS["x <y>"]')
assert Path(c1) == destino / "fachada.png" and Path(c1).read_bytes() == orig.read_bytes()
assert (destino / "fachada.pgw").read_text().count("\n") == 6
assert "<SRS>PROJCS[\"x &lt;y&gt;\"]</SRS>" in (destino / "fachada.png.aux.xml").read_text()
c2 = SI.copiar(orig, destino, (5, 5), 40, 0, 400, 200)
assert Path(c2).name == "fachada_2.png" and not Path(c2 + ".aux.xml").exists()
assert sorted(p.name for p in orig_dir.iterdir()) == ["fachada.png"]          # el original, solo
print("ok copia")

print("TODO OK SOLTARIMAGEN QGIS")
