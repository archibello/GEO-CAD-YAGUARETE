"""PEGARIMAGEN en QGIS (3.89.0), sin Qt: las cuentas de GEOPASTEIMAGE de IngeCAD
(esquina inferior izquierda y derecha, ancho escrito), la captura guardada como
PNG con su archivo de mundo en «<proyecto>_imagenes» sin pisar otra, la ruta
copiada como texto, y la barra «Yaguá Imagenes» (fábrica, banco y migración).
La orden, el portapapeles, Ctrl+V y la capa ráster de verdad los prueba
ventana/banco_pegar_imagen_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import json, math, os, sys, tempfile, time, types, importlib
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
ROOT = Path(__file__).resolve().parents[2]
DIBUJO = ROOT / "QGIS" / "codigo" / "geocad" / "dibujo"
pkg = types.ModuleType("dib"); pkg.__path__ = [str(DIBUJO)]; sys.modules["dib"] = pkg
SI = importlib.import_module("dib.soltar_imagen")
PI = importlib.import_module("dib.pegar_imagen")
sys.path.insert(0, str(ROOT / "COMUN"))
from nucleo import botones as BT


def cerca(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ---- 1. las cuentas, las de IngeCAD: el borde de abajo va del 1º al 2º punto -------------------
assert PI.colocacion((0, 0), (0, 0)) is None
ancho, giro = PI.colocacion((10, 20), (10 + 80 * math.cos(math.radians(30)), 20 + 40))
assert abs(ancho - 80) < 1e-9 and abs(giro - 30) < 1e-9
# como pegarimagen.esquinas de IngeCAD: (10,20)->(110,20) con 200x100 px: 100 x 50
a, g = PI.colocacion((10, 20), (110, 20))
assert cerca(sum(SI.esquinas((10, 20), a, g, 200, 100), ()), (10, 20, 110, 20, 110, 70, 10, 70))
a, g = PI.colocacion((0, 0), (0, 100))
e = SI.esquinas((0, 0), a, g, 200, 100)
assert cerca(e[1], (0, 100)) and cerca(e[2], (-50, 100)) and cerca(e[3], (-50, 0))
# el ancho escrito: un número solo; «x,y», «@…» y «d<a» son puntos
assert PI.ancho_escrito("12.5") == 12.5 and PI.ancho_escrito(" 40 ") == 40 and PI.ancho_escrito(".5") == 0.5
assert PI.ancho_escrito("-3") == -3
for t in ("10,20", "@5,0", "30<45", "A", "", "1e3"):
    assert PI.ancho_escrito(t) is None, t
assert PI.resumen(400, 200, 80, 30) == "400 × 200 píxeles, 80 × 40 unidades, girada 30°"
assert PI.resumen(400, 200, 80, 0) == "400 × 200 píxeles, 80 × 40 unidades"
print("ok cuentas")

# ---- 2. la captura: PNG con archivo de mundo y .aux.xml, sin pisar otra ------------------------
carpeta = Path(tempfile.mkdtemp()) / "obra_imagenes"
ahora = 1795000000.0
escritas = []


def guardar(ruta):
    Path(ruta).write_bytes(b"\x89PNG captura")
    escritas.append(ruta)
    return True


r1 = PI.guardar_captura(guardar, carpeta, (5, 5), 40, 30, 400, 200, 'PROJCS["x"]', ahora=ahora)
nombre = "captura_" + time.strftime("%Y%m%d_%H%M%S", time.localtime(ahora))
assert Path(r1) == carpeta / (nombre + ".png"), r1
mundo = (carpeta / (nombre + ".pgw")).read_text().split()
assert [float(x) for x in mundo] == [float("%.12f" % v) for v in SI.archivo_mundo((5, 5), 40, 30, 400, 200)]
assert "<SRS>PROJCS[\"x\"]</SRS>" in Path(r1 + ".aux.xml").read_text()
r2 = PI.guardar_captura(guardar, carpeta, (5, 5), 40, 0, 400, 200, ahora=ahora)
assert Path(r2).name == nombre + "_2.png" and not Path(r2 + ".aux.xml").exists()
# un archivo de mundo suelto con ese nombre tampoco se pisa
(carpeta / (nombre + "_3.pgw")).write_text("x")
assert Path(PI.nombre_captura(carpeta, ahora)).name == nombre + "_4.png"
# si no se pudo escribir: error, y no queda archivo de mundo
try:
    PI.guardar_captura(lambda ruta: False, carpeta, (0, 0), 1, 0, 1, 1, ahora=ahora + 100)
    raise SystemExit("tenía que fallar")
except OSError:
    pass
assert not list(carpeta.glob("*%s*" % time.strftime("%H%M%S", time.localtime(ahora + 100))))
print("ok captura")

# ---- 3. un archivo copiado como texto (una ruta o file:// por renglón) ------------------------
d = Path(tempfile.mkdtemp()) / "mis fotos"; d.mkdir()
foto = d / "fachada ñ.png"; foto.write_bytes(b"x")
(d / "notas.txt").write_text("x")
assert PI.ruta_de_texto(str(foto)) == str(foto)
assert PI.ruta_de_texto("copy\nfile://" + str(foto).replace(" ", "%20").replace("ñ", "%C3%B1")) == str(foto)
assert PI.ruta_de_texto(str(d / "notas.txt")) is None and PI.ruta_de_texto(str(d / "no.png")) is None
assert PI.ruta_de_texto("") is None and PI.ruta_de_texto(None) is None
print("ok texto")

# ---- 4. la barra «Yaguá Imagenes»: fábrica, banco y migración ----------------------------------
fab = dict(BT.DEFECTO["qgis"])
assert fab["Yaguá Imagenes"][-1] == "dibujo:pasteimage"          # 3.90.0: con INSERTARGEO y demás
nombres = [n for n, _b in BT.DEFECTO["qgis"]]
assert nombres.index("Yaguá Imagenes") == nombres.index("Yaguá Dibujo") + 1
assert "dibujo:pasteimage" in BT.TEMA_BANCO["qgis"]["Dibujo"]
assert "imagenes-qgis" in BT.MIGRACIONES["qgis"] and "imagenes-qgis" not in BT.MIGRACIONES["ingecad"]
hechas = [m for m in BT.MIGRACIONES["qgis"] if m != "imagenes-qgis"]
# guardada con RUMBOS: la barra nueva va detrás de la de RUMBOS, prendida
BT.archivo().parent.mkdir(parents=True, exist_ok=True)
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [
    {"nombre": "Mía", "botones": ["dibujo:line", "dibujo:rumbos"]},
    {"nombre": "Otra", "botones": ["dibujo:move"]}], "apagadas": ["Otra"], "migraciones": hechas}}),
    encoding="utf-8")
m = BT.leer("qgis")
assert [c["nombre"] for c in m["categorias"]] == ["Mía", "Yaguá Imagenes", "Otra"], m
assert m["categorias"][1]["botones"] == ["dibujo:pasteimage"] and m["apagadas"] == ["Otra"]
assert "imagenes-qgis" in json.loads(BT.archivo().read_text(encoding="utf-8"))["qgis"]["migraciones"]
# una sola vez: si Fernando después la borra, no vuelve
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [{"nombre": "Mía", "botones": ["dibujo:line"]}],
                                             "migraciones": hechas + ["imagenes-qgis"]}}), encoding="utf-8")
assert [c["nombre"] for c in BT.leer("qgis")["categorias"]] == ["Mía"]
# el botón ya puesto en otra barra: nada
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [{"nombre": "Mía", "botones": [
    "dibujo:pasteimage"]}], "migraciones": hechas}}), encoding="utf-8")
assert [c["nombre"] for c in BT.leer("qgis")["categorias"]] == ["Mía"]
# ya había una «Yaguá Imagenes» (armada a mano): el botón va al final de ésa
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [{"nombre": "Yaguá Imagenes", "botones": [
    "dibujo:line"]}], "migraciones": hechas}}), encoding="utf-8")
assert BT.leer("qgis")["categorias"] == [{"nombre": "Yaguá Imagenes", "botones": ["dibujo:line", "dibujo:pasteimage"]}]
# sin RUMBOS: al final; IngeCAD no se toca
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [{"nombre": "A", "botones": ["dibujo:line"]}],
                                             "migraciones": hechas},
                                    "ingecad": {"categorias": [{"nombre": "B", "botones": ["FILLET"]}],
                                                "migraciones": list(BT.MIGRACIONES["ingecad"])}}),
                        encoding="utf-8")
assert [c["nombre"] for c in BT.leer("qgis")["categorias"]] == ["A", "Yaguá Imagenes"]
assert [c["nombre"] for c in BT.leer("ingecad")["categorias"]] == ["B"]
BT.restablecer("qgis"); BT.restablecer("ingecad")
print("ok barra Yaguá Imagenes")

# ---- 5. el botón y la orden están en el complemento ---------------------------------------------
plugin = (DIBUJO / "plugin.py").read_text(encoding="utf-8")
assert "self._action('pasteimage'" in plugin and "pegar_imagen_qgis.instalar(self)" in plugin
assert "pegar_imagen_qgis.quitar(self)" in plugin and (DIBUJO / "icons" / "pasteimage.svg").is_file()
orden = (DIBUJO / "pegar_imagen_qgis.py").read_text(encoding="utf-8")
assert "'PEGARIMAGEN', ('PEGARIMAGEN', 'PASTEIMAGE', 'GEOPASTEIMAGE')" in orden
print("ok complemento")

print("TODO OK PEGARIMAGEN QGIS")
