"""GEORREF (RUBBERSHEET, AJUSTEIMAGEN) para IngeCAD (módulo «georref», 3.18.0):
una imagen, pares de puntos (en la imagen -> destino) con flechas numeradas,
tabla de puntos con residuos y error medio, Lineal / Helmert / Polinómica 1
sin rehacer la imagen (un solo U la vuelve atrás) y el .points de QGIS.
3.21.0: Proyectiva, Polinómica 2-3 y Thin Plate Spline, que rehacen la imagen
(remuestreo y fondo transparente, blanco o los dos)."""
import math, os, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
G = import_module("ingecad_plugin_geocad.georref")
UI = import_module("ingecad_plugin_geocad.georref_ui")
mods = import_module("ingecad_plugin_geocad.modulos")
yag = import_module("ingecad_plugin_geocad.yaguarete")
dib = import_module("ingecad_plugin_geocad.dibujo")
barra = import_module("ingecad_plugin_geocad.barra")
plugin = import_module("ingecad_plugin_geocad")


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ------------------------------------------------------------- 1. el módulo
m = next(m for m in mods.catalogo("ingecad") if m.clave == "georref")
assert m.defecto and not m.cambia_programa
spec = plugin.construir_spec()
assert spec.tools.get("GEORREF") is G.GeorrefTool
assert spec.aliases["RUBBERSHEET"] == "GEORREF" and spec.aliases["AJUSTEIMAGEN"] == "GEORREF"
dibujo_menu = next(s for s in spec.menu if getattr(s, "label", "") == "Drawing")
assert any(getattr(i, "command", "") == "GEORREF" for i in dibujo_menu.items)
assert ("GEORREF", "georref", None) in yag.HERRAMIENTAS and "GEORREF" in yag.DESCRIPCIONES
assert "GEORREF" in barra._iconos_propios()                          # su ícono
assert "flecha" in dib.ESTILO_RESALTADO and "flecha_off" in dib.ESTILO_RESALTADO
mods.poner("ingecad", "georref", False)
spec = plugin.construir_spec()
assert "GEORREF" not in spec.tools and "RUBBERSHEET" not in spec.aliases
mods.poner("ingecad", "georref", True)
print("ok módulo")

# ------------------------------------------------------------- 2. los métodos (las cuentas de QGIS)
org = [(0, 0), (1000, 0), (1000, -800), (0, -800), (400, -300)]


def con(coef):
    return [G.aplicar(coef, p) for p in org]


lin = (5000.0, 0.05, 0.0, 7000.0, 0.0, 0.04)                         # escalas distintas, sin giro
a = math.radians(30); s = 0.1
hel = (100.0, s * math.cos(a), -s * math.sin(a), 200.0, s * math.sin(a), s * math.cos(a))
afi = (10.0, 0.11, 0.02, 20.0, -0.01, 0.09)                          # con sesgo
for metodo, coef in (("lineal", lin), ("helmert", hel), ("polinomica1", afi)):
    r = G.ajustar(metodo, org, con(coef))
    assert cerca(r, coef, 1e-9), (metodo, r)
    assert G.error_medio(G.residuos(r, org, con(coef)), [1] * 5) < 1e-9
# Helmert no deforma: con datos afines da el mejor parecido, con residuos
r = G.ajustar("helmert", org, con(afi))
assert abs(r[1] - r[5]) < 1e-12 and abs(r[2] + r[4]) < 1e-12
assert G.error_medio(G.residuos(r, org, con(afi)), [1] * 5) > 1
# dos puntos alcanzan para Helmert y Lineal, no para Polinómica 1
assert cerca(G.ajustar("helmert", org[:2], con(hel)[:2]), hel, 1e-9)
for metodo, pts, txt in (("polinomica1", 2, "al menos 3"), ("helmert", 1, "al menos 2"),
                         ("polinomica2", 5, "al menos 6"), ("proyectiva", 3, "al menos 4"),
                         ("polinomica3", 5, "al menos 10"), ("tps", 2, "al menos 3")):
    try:
        G.ajustar(metodo, org[:pts], con(afi)[:pts]); raise AssertionError(metodo)
    except G.AjusteError as exc:
        assert txt in str(exc), exc
for metodo, o in (("polinomica1", [(0, 0), (1, 1), (2, 2)]),        # alineados
                  ("lineal", [(0, 0), (5, 0), (9, 0)]),              # misma horizontal
                  ("helmert", [(3, 3), (3, 3)])):                    # repetidos
    try:
        G.ajustar(metodo, o, [(1, 2), (3, 4), (5, 7)][:len(o)]); raise AssertionError(metodo)
    except G.AjusteError:
        pass
assert "giro 30°" in G.describir(hel) and "escala 0.1," in G.describir(hel)
assert "escala X 0.05, Y 0.04" in G.describir(lin)
assert cerca(G.aplicar(G.inversa(afi), G.aplicar(afi, (7, -3))), (7, -3), 1e-9)
print("ok métodos")

# ------------------------------------------------------------- 3. la imagen: píxeles de QGIS
carpeta = Path(tempfile.mkdtemp())
plano = carpeta / "plano.png"; plano.write_bytes(b"\x89PNG")             # el archivo no se lee
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
ddef = doc.doc.add_image_def(filename=str(plano), size_in_pixel=(1000, 800))
img = msp.add_image(ddef, insert=(10, 20), size_in_units=(100, 80), rotation=0)
linea = msp.add_line((500, 500), (600, 500))
assert cerca(G.pixel_a_mundo(img, (0, 0)), (10, 100))                    # arriba a la izquierda
assert cerca(G.pixel_a_mundo(img, (0, -800)), (10, 20))                  # abajo a la izquierda
assert cerca(G.pixel_a_mundo(img, (1000, -800)), (110, 20))
assert cerca(G.mundo_a_pixel(img, (60, 60)), (500, -400))
assert G.dentro(img, (60, 60)) and not G.dentro(img, (200, 60))
assert G.ruta_points(img, doc) == carpeta / "plano.png.points"
# la imagen va a donde dicen los coeficientes, por TransformCommand (deshacer exacto)
from core import actions
antes = [tuple(v) for v in (img.dxf.insert, img.dxf.u_pixel, img.dxf.v_pixel)]
hist.execute(actions.TransformCommand("GEORREF", [img], G.matriz(img, hel)))
for p in ((0, 0), (1000, -800), (250, -100)):
    assert cerca(G.pixel_a_mundo(img, p), G.aplicar(hel, p), 1e-6)
hist.undo()
assert all(cerca(tuple(v), b, 1e-9) for v, b in zip((img.dxf.insert, img.dxf.u_pixel, img.dxf.v_pixel), antes))
hist.execute(actions.TransformCommand("GEORREF", [img], G.matriz(img, afi)))   # también con sesgo
assert cerca(G.pixel_a_mundo(img, (1000, 0)), G.aplicar(afi, (1000, 0)), 1e-6)
hist.undo()
print("ok imagen")

# ------------------------------------------------------------- 4. el .points de QGIS
pares = [{"sx": sx, "sy": sy, "X": X, "Y": Y, "on": i != 2}
         for i, ((sx, sy), (X, Y)) in enumerate(zip(org, con(hel)))]
pares[4]["X"] += 0.5                                                      # un punto con error
ruta = G.escribir_points(carpeta / "a.points", pares, "EPSG:5349", "helmert")
lineas = ruta.read_text().splitlines()
assert lineas[0] == "#CRS: EPSG:5349" and lineas[1] == G.CABECERA_POINTS and len(lineas) == 7
assert lineas[4].split(",")[4] == "0"                                    # el apagado
assert float(lineas[6].split(",")[7]) > 0                                 # residuo en píxeles
leidos = G.leer_points(ruta)
assert [p["on"] for p in leidos] == [p["on"] for p in pares]
assert all(cerca((p["sx"], p["sy"], p["X"], p["Y"]), (q["sx"], q["sy"], q["X"], q["Y"]), 0)
           for p, q in zip(leidos, pares))
pares[0]["on"] = False
G.escribir_points(ruta, pares, "", "helmert")                            # distinto: queda copia
assert (carpeta / "a.points.bak").read_text().startswith("#CRS")
assert not ruta.read_text().startswith("#")
viejo = carpeta / "viejo.points"; viejo.write_text("mapX mapY pixelX pixelY\n1 2 3 -4\n5\t6\t7\t-8\n")
assert [(p["X"], p["Y"], p["sx"], p["sy"], p["on"]) for p in G.leer_points(viejo)] == \
    [(1, 2, 3, -4, True), (5, 6, 7, -8, True)]
print("ok points")

# ------------------------------------------------------------- 5. la orden
from core.select import GeometryIndex


class Ctrl:
    def __init__(self, document):
        self.window = types.SimpleNamespace(document=document)
        self.index = GeometryIndex(document)
        self.selection = set()
        self._pick_tolerance = 0.2
    def pick_entity(self, p):
        h = self.index.pick(tuple(p), self._pick_tolerance)
        return self.index.entity(h) if h else None


msgs, prompts, fin = [], [], []
respuesta = [None]                                                         # lo que se escribe en ask_text


def herramienta(selection=()):
    msgs.clear(); prompts.clear(); fin.clear()
    ctrl = Ctrl(doc); ctrl.selection = set(selection)
    ctx = ToolContext(execute=hist.execute, prompt=prompts.append, echo=msgs.append,
                      finish=lambda: fin.append(1), services=ctrl,
                      ask_text=lambda pedido, inicio="": respuesta[0])
    t = G.GeorrefTool(ctx); t.start()
    return t


assert UI.tabla(None, None) is UI.SIN_QT                                 # sin Qt: la línea de comandos
t = herramienta()
assert "UNA imagen" in prompts[-1] and t.resaltado((60, 60))["cursor"]   # la imagen bajo el cursor
t.on_point((550, 500))                                                    # una línea: no
assert any("no es una imagen" in m for m in msgs) and t._img is None
t.on_point((60, 60))                                                      # clic dentro de la imagen
assert t._img is img and "1000 x 800" in msgs[-1] and t.referencias_extra()
assert prompts[-1].startswith("Punto en la imagen 1")
dest = {(0, 0): (5000, 7000), (1000, -800): (5100, 6920), (1000, 0): (5100, 7000), (0, -800): (5000, 6920)}
t.on_point(G.pixel_a_mundo(img, (0, 0)))
assert prompts[-1].startswith("Punto de destino 1")
r = t.resaltado((4000, 4000))
assert r["flecha"] and r["textos"][-1][1] == "1"                          # el par a medio marcar
t.on_option("U"); assert t._pendiente is None and prompts[-1].startswith("Punto en la imagen 1")
for px, X in dest.items():
    t.on_point(G.pixel_a_mundo(img, px)); t.on_point(X)
assert len(t._pares) == 4 and "error medio 0" in msgs[-1]
t.on_option("U"); assert len(t._pares) == 3                              # U quita el último par
t.on_point(G.pixel_a_mundo(img, (0, -800))); t.on_point((5000, 6921))    # el 4º, con 1 m de error
r = t.resaltado(None)
assert len(r["flecha"]) == 4 * 3 and r["vista"] and [x[1] for x in r["textos"]] == ["1", "2", "3", "4"]
t.on_enter()                                                              # la tabla, en texto
assert t._tabla and any("Tabla de puntos" in m for m in msgs) and "Transformar" in prompts[-1]
assert any("Error medio" in m for m in msgs)
msgs.clear(); t.on_option("A4")                                          # apaga el 4
assert not t._pares[3]["on"] and any(m.startswith("  Error medio: 0 ") for m in msgs)
r = t.resaltado(None); assert len(r["flecha_off"]) == 3
t.on_option("L"); assert t._metodo == "lineal"
t.on_option("E4"); t.on_option("A 4"); assert not t._pares[3]["on"]
assert not t.on_option("ZZZ")
assert G.SALIDAS["copia"] in " ".join(msgs)                              # de entrada: la copia
t.on_option("DIBUJO"); assert t._salida == "dibujo" and "Sólo el dibujo" in msgs[-1]
t.on_enter()                                                              # Enter = Transformar
assert fin and any("Imagen ajustada con Lineal: 3 puntos" in m for m in msgs)
for px, X in dest.items():
    assert cerca(G.pixel_a_mundo(img, px), X, 1e-6), px
assert linea.dxf.start == (500, 500, 0)                                   # los vectores, ni tocados
pts = carpeta / "plano.png.points"
assert pts.exists() and len(G.leer_points(pts)) == 4                     # junto a la imagen, para QGIS
hist.undo()                                                               # un solo U: como estaba
assert cerca(G.pixel_a_mundo(img, (0, -800)), (10, 20), 1e-9)
assert G._ultimo_metodo[0] == "lineal"                                   # la próxima arranca con Lineal
print("ok orden")

# ------------------------------------------------------------- 6. cargar puntos, preselección, Esc
t = herramienta({img.dxf.handle, linea.dxf.handle})                      # imagen + vector elegidos antes
assert t._img is img and any("quedan afuera 1 objeto" in m for m in msgs)
assert any("Hay 4 puntos guardados" in m for m in msgs)
t.on_option("C"); assert len(t._pares) == 4 and not t._pares[3]["on"]
t.on_option("M")                                                          # fuera de la tabla: no es opción
t.on_enter(); t.on_option("Helmert"); t.on_option("T")
assert any("Imagen ajustada con Helmert: 3 puntos" in m for m in msgs)
assert (carpeta / "plano.png.points.bak").exists() is False              # mismo contenido: sin copia
hist.undo()
t = herramienta()
t.on_point((60, 60)); t.on_point((60, 60)); t.on_point((70, 70))
t.on_cancel()
assert fin and any("queda como estaba" in m for m in msgs)
assert cerca(G.pixel_a_mundo(img, (0, -800)), (10, 20), 1e-9)
t = herramienta()
t.on_point((60, 60)); t.on_point((60, 60)); t.on_point((70, 70))
t.on_enter(); t.on_enter()                                                # 1 par: no alcanza
assert any("al menos 2" in m for m in msgs) and not fin
t.on_option("M"); assert not t._tabla and prompts[-1].startswith("Punto en la imagen 2")
print("ok cargar y cancelar")

# ------------------------------------------------------------- 7. copia ajustada y archivo de mundo (3.18.1)
G.crs_dibujo = lambda: "EPSG:5349"
assert G.ruta_mundo("a/plano.png").name == "plano.pgw" and G.ruta_mundo("x.JPG").name == "x.jgw"
assert G.ruta_mundo("x.tif").name == "x.tfw" and G.ruta_mundo("x.webp").name == "x.wpw"
(carpeta / "plano_georref.pgw").write_text("de otro")                    # un vecino ocupado: no se pisa
assert G.nombre_copia(plano).name == "plano_georref2.png"
(carpeta / "plano_georref.pgw").unlink()


def ajustar_con(*opciones):
    t = herramienta()
    t.on_point((60, 60))
    for px, X in dest.items():
        t.on_point(G.pixel_a_mundo(img, px)); t.on_point(X)
    t.on_enter()
    for o in opciones:
        t.on_option(o)
    t.on_option("Helmert"); t.on_option("T")
    assert fin, msgs
    return t


def mundo_ok(ruta):
    A, D, B, E, C, F = (float(v) for v in ruta.read_text().split())
    for col, fila in ((0, 0), (999, 799), (10, 500)):                    # centros de píxel
        x, y = G.pixel_a_mundo(img, (col + 0.5, -(fila + 0.5)))
        assert cerca((A * col + B * fila + C, D * col + E * fila + F), (x, y), 1e-6)


antes_bytes = plano.read_bytes()
ajustar_con("COPIA")
copia = carpeta / "plano_georref.png"
assert copia.read_bytes() == antes_bytes and plano.read_bytes() == antes_bytes
assert img.image_def.dxf.filename == str(copia)                          # el dibujo usa la copia
assert any("el dibujo usa la copia" in m and "plano.png queda como estaba" in m for m in msgs)
mundo_ok(carpeta / "plano_georref.pgw")
aux = (carpeta / "plano_georref.png.aux.xml").read_text()
assert aux.startswith("<PAMDataset>") and "POSGAR 2007" in aux
assert len(G.leer_points(carpeta / "plano_georref.png.points")) == 4    # los puntos, con la copia
assert not (carpeta / "plano.pgw").exists()                              # junto a la original, nada
r = img.image_def_reactor
assert r is None or r.dxf.handle in img.image_def.reactors
hist.undo()                                                               # un U: lugar y archivo
assert img.image_def.dxf.filename == str(plano) and cerca(G.pixel_a_mundo(img, (0, -800)), (10, 20), 1e-9)
hist.redo(); assert img.image_def.dxf.filename == str(copia); hist.undo()
ajustar_con("COPIA"); assert img.image_def.dxf.filename.endswith("plano_georref2.png"); hist.undo()
# relativa al dibujo: la copia también
doc.path = carpeta / "dibujo.dxf"; img.image_def.dxf.filename = "plano.png"
ajustar_con("COPIA"); assert img.image_def.dxf.filename == "plano_georref3.png"; hist.undo()
assert img.image_def.dxf.filename == "plano.png"
img.image_def.dxf.filename = str(plano)
# archivo de mundo junto a la original (y el anterior queda como .bak)
(carpeta / "plano.pgw").write_text("viejo\n")
ajustar_con("MUNDO")
mundo_ok(carpeta / "plano.pgw")
assert (carpeta / "plano.pgw.bak").read_text() == "viejo\n"
assert img.image_def.dxf.filename == str(plano) and any("junto a la original" in m for m in msgs)
assert G._ultima_salida[0] == "mundo"
hist.undo()
# sin el archivo de la imagen: sólo el dibujo, avisando
plano.rename(carpeta / "otro.png")
ajustar_con("COPIA"); assert any("no se encuentra el archivo" in m for m in msgs); hist.undo()
(carpeta / "otro.png").rename(plano)
# «Guardar copia geo como...»: otra carpeta, el nombre que se quiera
otra = Path(tempfile.mkdtemp()) / "entregas"; otra.mkdir()
respuesta[0] = str(otra / "lote 12 georref")                             # sin extensión: lleva la de la original
G._ultima_salida[0] = "dibujo"
ajustar_con("COMO")
geo = otra / "lote 12 georref.png"
assert geo.read_bytes() == antes_bytes and img.image_def.dxf.filename == str(geo)
mundo_ok(otra / "lote 12 georref.pgw")
assert (otra / "lote 12 georref.png.aux.xml").exists() and (otra / "lote 12 georref.png.points").exists()
assert any(str(geo) in m and "el dibujo usa la copia" in m for m in msgs)
hist.undo(); assert img.image_def.dxf.filename == str(plano)
assert G.destino_copia(otra / "x.PNG", plano).name == "x.PNG"
for mala in (plano, carpeta / "no_existe" / "x.png"):
    try:
        G.destino_copia(mala, plano); raise AssertionError(mala)
    except OSError:
        pass
respuesta[0] = str(plano)                                                 # la original misma: no
ajustar_con("COMO")
assert any("no se pudo copiar" in m for m in msgs) and plano.read_bytes() == antes_bytes
hist.undo()
respuesta[0] = None                                                       # Esc en el pedido: nada cambia
t = herramienta(); t.on_point((60, 60)); t._pares = [dict(p) for p in G.leer_points(carpeta / "plano.png.points")]
t.on_enter(); t.on_option("DIBUJO"); t.on_option("COMO"); assert t._salida == "dibujo" and t._copia_en is None
t.on_cancel()
print("ok copia y mundo")

# ------------------------------------------------------------- 8. los que deforman (3.21.0): las cuentas
cuad = [(0, 0), (1000, 0), (1000, -800), (0, -800)]
trap = [(5000, 7000), (5100, 7010), (5095, 6920), (5010, 6925)]          # un trapecio cualquiera
pr = G.ajustar("proyectiva", cuad, trap)
assert isinstance(pr, G.Modelo) and "rehace" in G.describir(pr)
assert all(cerca(G.aplicar(pr, a), b, 1e-6) for a, b in zip(cuad, trap))  # 4 puntos: exacta
assert all(cerca(pr.inverso(b), a, 1e-6) for a, b in zip(cuad, trap))
assert cerca(G.aplicar(G.inversa(pr), trap[2]), cuad[2], 1e-6)
# las rectas siguen rectas: el medio de un lado cae sobre el lado deformado
q = G.aplicar(pr, (500, 0)); a, b = trap[0], trap[1]
assert abs((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])) < 1e-6
# con más puntos: mínimos cuadrados (residuos cero si los datos son proyectivos)
mas = cuad + [(500, -400), (200, -700), (900, -100), (300, -100), (700, -600), (100, -400)]
for metodo in ("proyectiva", "polinomica2", "polinomica3", "tps"):
    m = G.ajustar(metodo, mas, [G.aplicar(pr, x) for x in mas])
    rms = G.error_medio(G.residuos(m, mas, [G.aplicar(pr, x) for x in mas]), [1] * len(mas))
    assert rms < (1.0 if metodo == "polinomica2" else 1e-5), (metodo, rms)
    vuelta = m.inverso(G.aplicar(m, (400, -300)))
    assert cerca(vuelta, (400, -300), 1e-3 if metodo == "proyectiva" else 3.0), (metodo, vuelta)  # la vuelta: otro ajuste, como GDAL
# polinómica 2 exacta con datos de segundo grado; TPS pasa por cada punto
cuadr = lambda p: (3 + 0.1 * p[0] + 1e-5 * p[0] * p[1], 7 + 0.1 * p[1] + 2e-5 * p[0] ** 2)
m = G.ajustar("polinomica2", mas, [cuadr(x) for x in mas])
assert cerca(G.aplicar(m, (333, -222)), cuadr((333, -222)), 1e-6)
ruido = [(x + (i % 3) * 0.7, y - (i % 2) * 0.4) for i, (x, y) in enumerate(G.aplicar(pr, p) for p in mas)]
m = G.ajustar("tps", mas, ruido)
assert G.error_medio(G.residuos(m, mas, ruido), [1] * len(mas)) < 1e-6
assert len(G.esquinas(img, m)) == 64 and len(G.esquinas(img, pr)) == 4   # TPS curva los bordes
for metodo, o in (("proyectiva", [(0, 0), (1, 0), (2, 0), (0, -1)]),     # 3 alineados
                  ("tps", [(0, 0), (1, 1), (2, 2)]),                      # alineados
                  ("tps", [(0, 0), (0, 0), (5, 1)])):                     # repetidos
    try:
        G.ajustar(metodo, o, trap[:len(o)]); raise AssertionError(metodo)
    except G.AjusteError:
        pass
for t_, m_ in (("P2", "polinomica2"), ("p3", "polinomica3"), ("TPS", "tps"), ("Proyectiva", "proyectiva")):
    assert G._metodo_de_texto(t_) == m_
ruta = G.escribir_points(carpeta / "pr.points", [{"sx": a[0], "sy": a[1], "X": b[0], "Y": b[1], "on": True}
                                                 for a, b in zip(cuad, trap)], "", "proyectiva")
assert all(abs(float(l.split(",")[7])) < 1e-6 for l in ruta.read_text().splitlines()[1:])
print("ok métodos que deforman")

# ------------------------------------------------------------- 9. rehacer la imagen (PIL)
from PIL import Image
GI = import_module("ingecad_plugin_geocad.georref_imagen")
colores = {}
foto = Image.new("RGB", (1000, 800))
for i in range(4):                                       # una grilla de 4 x 4 colores
    for j in range(4):
        c = (40 + 60 * i, 30 + 70 * j, 200 - 40 * i)
        foto.paste(c, (250 * i, 200 * j, 250 * (i + 1), 200 * (j + 1)))
        colores[(250 * i + 125, -(200 * j + 100))] = c
foto.save(plano)


def ajustar_rehaciendo(metodo, *opciones, destinos=trap):
    t = herramienta()
    t.on_point((60, 60))
    for px, X in zip(cuad, destinos):
        t.on_point(G.pixel_a_mundo(img, px)); t.on_point(X)
    t.on_enter()
    t.on_option(metodo)
    for o in opciones:
        t.on_option(o)
    t.on_option("T")
    assert fin, msgs
    return t


def color_en(ruta, X, Y):
    """El color de la imagen rehecha en el punto (X, Y) del dibujo, leído
    con su archivo de mundo."""
    A, D, B, E, C, F = (float(v) for v in G.ruta_mundo(ruta).read_text().split())
    col, fila = (X - C) / A + 0.5, (Y - F) / E + 0.5
    with Image.open(ruta) as im:
        return im.getpixel((int(col), int(fila)))


ancho_antes = G.tamano(img)
ajustar_rehaciendo("PROYECTIVA")
nueva = carpeta / "plano_georref4.png"                    # 1-3 ya los usó la copia (7.)
assert img.image_def.dxf.filename == str(nueva), img.image_def.dxf.filename
assert any("Imagen rehecha con Proyectiva: 4 puntos" in m for m in msgs)
assert any("la usa el dibujo" in m for m in msgs) and plano.exists()
with Image.open(nueva) as im:
    assert im.mode == "RGBA" and im.size == tuple(int(v) for v in G.tamano(img))
    assert im.getpixel((0, im.size[1] - 1)) == (255, 255, 255, 0)         # afuera: transparente (blanco)
assert img.dxf.flags & img.USE_TRANSPARENCY                                # si no, el fondo se ve negro
for (sx, sy), c in colores.items():                                        # cada color en su lugar
    X, Y = G.aplicar(pr, (sx, sy))
    assert color_en(nueva, X, Y)[:3] == c, (sx, sy)
# en el dibujo: la imagen nueva cubre el trapecio entero, derecha
x0, y0 = G.pixel_a_mundo(img, (0, 0)); w, h = G.tamano(img)
x1, y1 = G.pixel_a_mundo(img, (w, -h))
assert x0 <= min(p[0] for p in trap) + 1e-6 and x1 >= max(p[0] for p in trap) - 0.2
assert y0 >= max(p[1] for p in trap) - 1e-6 and y1 <= min(p[1] for p in trap) + 0.2
mundo_ok_n = G.ruta_mundo(nueva).exists() and (carpeta / "plano_georref4.png.aux.xml").exists()
assert mundo_ok_n and (carpeta / "plano_georref4.png.points").exists()
hist.undo()                                                                # un U: como estaba
assert img.image_def.dxf.filename == str(plano) and G.tamano(img) == ancho_antes
assert not img.dxf.flags & img.USE_TRANSPARENCY
assert cerca(G.pixel_a_mundo(img, (0, -800)), (10, 20), 1e-9)
hist.redo(); assert img.image_def.dxf.filename == str(nueva); hist.undo()
# fondo blanco y los dos; remuestreo cúbico; TPS con malla
jpg = carpeta / "foto.jpg"; foto.save(jpg, quality=98)
img.image_def.dxf.filename = str(jpg)
ajustar_rehaciendo("TPS", "AMBOS", "CÚBICA")
assert G._ultimo_remuestreo[0] == "cubica" and G._ultimo_fondo[0] == "ambos"
t_png, b_jpg = carpeta / "foto_georref.png", carpeta / "foto_georref.jpg"
assert img.image_def.dxf.filename == str(t_png) and b_jpg.exists() and G.ruta_mundo(b_jpg).exists()
with Image.open(b_jpg) as im:
    assert im.mode == "RGB" and min(im.getpixel((0, im.size[1] - 1))) > 240  # afuera: blanco
for (sx, sy), c in colores.items():
    X, Y = G.aplicar(G.ajustar("tps", cuad, trap), (sx, sy))
    assert all(abs(u - v) < 12 for u, v in zip(color_en(b_jpg, X, Y)[:3], c)), (sx, sy)
    assert all(abs(u - v) < 12 for u, v in zip(color_en(t_png, X, Y)[:3], c)), (sx, sy)
hist.undo(); assert img.image_def.dxf.filename == str(jpg)
ajustar_rehaciendo("PROYECTIVA", "BLANCO", "VECINO")
assert img.image_def.dxf.filename == str(carpeta / "foto_georref2.jpg")
assert not img.dxf.flags & img.USE_TRANSPARENCY                            # blanco: sin transparencia
hist.undo()
# una proyectiva que da vuelta la imagen: no se hace nada
cruzado = [trap[0], trap[2], trap[1], trap[3]]
t = herramienta(); t.on_point((60, 60))
for px, X in zip(cuad, cruzado):
    t.on_point(G.pixel_a_mundo(img, px)); t.on_point(X)
t.on_enter(); t.on_option("PROYECTIVA"); t.on_option("T")
assert not fin and any("no se pudo rehacer" in m for m in msgs), msgs
assert img.image_def.dxf.filename == str(jpg); t.on_cancel()
# sin el archivo: no se puede rehacer, se vuelve a la tabla
img.image_def.dxf.filename = str(carpeta / "no_esta.png")
t = herramienta(); t.on_point((60, 60))
for px, X in zip(cuad, trap):
    t.on_point(G.pixel_a_mundo(img, px)); t.on_point(X)
t.on_enter(); t.on_option("P3"); t.on_option("T")                         # P3: 10 puntos
assert not fin and any("al menos 10" in m for m in msgs)
t.on_option("TPS"); t.on_option("T")
assert not fin and any("no se encuentra el archivo" in m for m in msgs); t.on_cancel()
img.image_def.dxf.filename = str(plano)
# nombres: Guardar copia geo como... con fondo transparente lleva .png
otra2 = Path(tempfile.mkdtemp())
r = GI.rutas(jpg, "ambos", otra2 / "x.jpg")
assert [p.name for p, _f in r] == ["x.png", "x.jpg"]
r = GI.rutas(plano, "ambos", otra2 / "y.png")
assert [p.name for p, _f in r] == ["y.png", "y_blanco.png"]
assert GI.extension("a.TIF", "transparente") == ".TIF"
print("ok rehacer la imagen")

# ------------------------------------------------------------- 10. la cuenta regresiva (3.21.2)
GP = import_module("ingecad_plugin_geocad.georref_progreso")
assert GP.texto_falta(10, 6.2) == "faltan unos 4 s" and GP.texto_falta(3, 2.5) == "falta 1 s"
assert GP.texto_falta(3, 4) == "ya casi..."
GP._ritmo[0] = 0.2
assert GP.estimar(26, 1) == 0.2 * 26 and GP.estimar(26, 2) == 0.2 * 52 and GP.estimar(0.1, 1) == 1.0
GP.medir(26, 2, 10.4); assert abs(GP._ritmo[0] - 0.2) < 1e-12
GP.medir(0.1, 1, 9); assert abs(GP._ritmo[0] - 0.2) < 1e-12              # una imagen chica no enseña
with GP.Progreso(None, "GEORREF") as pg:                                   # sin Qt: directo, sin ventana
    assert pg.trabajo("x", lambda: 42, 3) == 42 and pg.dlg is None
    try:
        pg.trabajo("x", lambda: 1 / 0, 3); raise AssertionError("sin error")
    except ZeroDivisionError:
        pass
    pg.regeneracion(types.SimpleNamespace())                               # sin Qt: nada
print("ok cuenta regresiva")

# ------------------------------------------------------------- 11. recorte al contenido y fondo negro (3.21.3)
otra3 = Path(tempfile.mkdtemp())
marco_tr = Image.new("RGBA", (1000, 800), (0, 0, 0, 0))                 # como una ya rehecha: esquinas
marco_tr.paste((200, 60, 60, 255), (200, 100, 800, 700))                 # transparentes (negro debajo)
fuente_tr = otra3 / "rehecha.png"; marco_tr.save(fuente_tr)
pr2 = G.ajustar("proyectiva", cuad, trap)
for fondo, esquina in (("transparente", (255, 255, 255, 0)), ("blanco", (255, 255, 255)), ("negro", (0, 0, 0))):
    salida = GI.rutas(fuente_tr, fondo)
    coef_r, (wr, hr) = GI.rehacer(fuente_tr, salida, pr2, "vecino")
    with Image.open(salida[0][0]) as im:
        assert im.size == (wr, hr)
        if fondo == "transparente":
            assert im.getchannel("A").getbbox() == (0, 0, wr, hr)          # sin margen sobrante
        else:
            assert im.mode == "RGB" and im.getpixel((0, 0)) == esquina, (fondo, im.getpixel((0, 0)))
            assert im.getpixel((wr // 2, hr // 2)) == (200, 60, 60)        # el contenido, no negro
    # el recorte: el marco nuevo envuelve justo la parte opaca deformada
    opaco = [G.aplicar(pr2, (x, -y)) for x, y in ((200, 100), (800, 100), (800, 700), (200, 700))]
    x0r, y0r = coef_r[0], coef_r[3]
    assert abs(x0r - min(p[0] for p in opaco)) < 2 * coef_r[1] and abs(y0r - max(p[1] for p in opaco)) < 2 * coef_r[1]
    assert abs(x0r + wr * coef_r[1] - max(p[0] for p in opaco)) < 2 * coef_r[1]
assert G._metodo_de_texto("NEGRO") is None and "negro" in G.FONDOS
t = herramienta(); t.on_point((60, 60)); t._pares = [{"sx": a[0], "sy": a[1], "X": b[0], "Y": b[1], "on": True}
                                                    for a, b in zip(cuad, trap)]
t.on_enter(); t.on_option("PROYECTIVA"); t.on_option("NEGRO")
assert t._fondo == "negro" and G._ultimo_fondo[0] == "negro" and any("fondo negro" in m for m in msgs)
t.on_option("TRANSPARENTE"); t.on_cancel()
print("ok recorte y negro")

print("TODO OK GEORREF")
