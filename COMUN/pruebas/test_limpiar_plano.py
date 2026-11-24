"""LIMPIARPLANO para IngeCAD (módulo «georref», 3.86.0): limpiar un plano
antiguo escaneado (manchas de humedad, pliegues) dejando legibles los textos,
con zonas de sello de umbrales suaves. Sin scipy (el Flatpak de IngeCAD no lo
trae): las cuentas de limpieza.py se comparan con versiones directas (lentas)
y con la referencia que aprobó Fernando el 19/11/2026 («QUEDO PERFECTO»).

Datos (datos_limpiar_plano/): sólo un RECORTE de 300 × 300 píxeles del plano
de mensura de 1958 (es un documento de un tercero; el plano entero no va al
repositorio) y el mismo recorte de la referencia aprobada (plano_limpio_2x,
hecha por el prototipo con scipy y la zona de sello 1215,1195,1815,1465).
El recorte va desde (1150, 1140) del plano.

Tolerancia: con el plano ENTERO, limpieza.py da la referencia idéntica (0
píxeles distintos, medido el 19/11/2026 contra scipy). Con el recorte, cerca
del borde falta contexto (la ventana del cierre, 27 px a 2x, y los grupos de
tinta que siguen afuera), así que se compara el interior, dejando 20 px del
recorte (40 a 2x) de cada lado: ahí hoy da idéntico. Se admite hasta 0,1 %
de píxeles con más de 8 niveles de diferencia y una diferencia media menor
que 0,5 (por si otra versión de PIL redondea distinto el LANCZOS o el
desenfoque); en todo el recorte, hasta 3 % de píxeles distintos."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import hashlib, json, os, tempfile, time, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
import numpy as np
from PIL import Image
from core.commands import History
from core.document import Document
from core.select import GeometryIndex
from core.plugins import load_plugin
from tools.base import ToolContext

AQUI = Path(__file__).resolve().parent
lp = load_plugin(AQUI.parents[1] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
L = import_module("ingecad_plugin_geocad.limpieza")
LP = import_module("ingecad_plugin_geocad.limpiar_plano")
G = import_module("ingecad_plugin_geocad.georref")
mods = import_module("ingecad_plugin_geocad.modulos")
yag = import_module("ingecad_plugin_geocad.yaguarete")
barra = import_module("ingecad_plugin_geocad.barra")
botones = import_module("ingecad_plugin_geocad.botones")
plugin = import_module("ingecad_plugin_geocad")

# ------------------------------------------------------------- 1. orden, barra y menú
spec = plugin.construir_spec(completo=True)
assert spec.tools["LIMPIARPLANO"] is LP.LimpiarPlanoTool
assert spec.aliases["GEOLIMPIARPLANO"] == "LIMPIARPLANO"
ordenes = [h[0] for h in yag.HERRAMIENTAS]
assert ordenes.index("LIMPIARPLANO") == ordenes.index("ASPECTOIMAGEN") + 1
assert yag.TEMAS["LIMPIARPLANO"] == "imagenes"
assert "LIMPIARPLANO" in yag.DESCRIPCIONES and "LIMPIARPLANO" in yag.ETIQUETAS
icono = barra._iconos_propios()["LIMPIARPLANO"]
assert icono.is_file() and Image.open(icono).size == (24, 24)
dibujo_menu = next(s for s in spec.menu if getattr(s, "label", "") == "Drawing")
cmds = [getattr(i, "command", "") for i in dibujo_menu.items]
assert cmds.index("LIMPIARPLANO") == cmds.index("ASPECTOIMAGEN") + 1
ui = json.loads((Path(plugin.__file__).parent / "i18n" / "es" / "ui.json").read_text("utf-8"))
assert ui["Clean old scanned plan (LIMPIARPLANO)"].startswith("Limpiar plano")
# barra «Yaguá Imagenes» de fábrica, detrás de ASPECTOIMAGEN
imagenes = dict(botones.DEFECTO["ingecad"])["Yaguá Imagenes"]
assert imagenes.index("LIMPIARPLANO") == imagenes.index("ASPECTOIMAGEN") + 1
assert "LIMPIARPLANO" in botones.TEMA_BANCO["ingecad"]["Imágenes"]
# una barra YA GUARDADA (la de Fernando) la recibe detrás de ASPECTOIMAGEN, una sola vez
crudo = {"categorias": [{"nombre": "Yaguá Imagenes", "botones": [
    "INSERTARGEO", "GEORREF", "EXPORTARGEO", "ASPECTOIMAGEN", "GEOPASTEIMAGE"]}], "migraciones": []}
assert botones._migrar("ingecad", crudo)
assert crudo["categorias"][0]["botones"] == [
    "INSERTARGEO", "GEORREF", "EXPORTARGEO", "ASPECTOIMAGEN", "LIMPIARPLANO", "GEOPASTEIMAGE"]
assert not botones._migrar("ingecad", crudo)
crudo = {"categorias": [{"nombre": "Mía", "botones": ["LIMPIARPLANO", "ASPECTOIMAGEN"]}]}
botones._migrar("ingecad", crudo)
assert crudo["categorias"][0]["botones"] == ["LIMPIARPLANO", "ASPECTOIMAGEN"]   # ya la tenía
mods.poner("ingecad", "georref", False)
assert "LIMPIARPLANO" not in plugin.construir_spec(completo=True).tools
mods.poner("ingecad", "georref", True)
print("ok orden, barra y menú")

# ------------------------------------------------------------- 2. las cuentas, sin scipy
rng = np.random.default_rng(7)


def ventana_directa(a, k, f):
    r = k // 2
    p = np.pad(a, r, mode="symmetric")
    v = np.lib.stride_tricks.sliding_window_view(p, (k, k))
    return f(v, axis=(-1, -2))


a = rng.random((61, 47)).astype(np.float32)
for k in (1, 3, 5, 13, 27):
    assert np.array_equal(L.maximo(a, k), ventana_directa(a, k, np.max)), k
    assert np.array_equal(L.minimo(a, k), ventana_directa(a, k, np.min)), k
    assert np.array_equal(L.cierre(a, k), ventana_directa(ventana_directa(a, k, np.max), k, np.min)), k


def grupos_directo(m):
    """Etiquetado de 8 vecinos por recorrido (lento, para comparar)."""
    h, w = m.shape
    lab = np.zeros(m.shape, int)
    n = 0
    for y in range(h):
        for x in range(w):
            if m[y, x] and not lab[y, x]:
                n += 1
                pila = [(y, x)]
                lab[y, x] = n
                while pila:
                    cy, cx = pila.pop()
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            yy, xx = cy + dy, cx + dx
                            if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                                lab[yy, xx] = n
                                pila.append((yy, xx))
    return lab, n


for prob, minimo in ((0.5, 5), (0.6, 20), (0.35, 1), (0.0, 3), (1.0, 3)):
    m = rng.random((53, 71)) < prob
    f = rng.random((53, 71)) < 0.03
    lab, n = grupos_directo(m)
    tam = np.bincount(lab.ravel(), minlength=n + 1)
    fu = np.zeros(n + 1, bool)
    fu[np.unique(lab[f & m])] = True
    ok = fu & (tam >= minimo)
    ok[0] = False
    assert np.array_equal(L.histeresis(m, f, minimo), ok[lab]), (prob, minimo)
# una espiral: un solo grupo que el union-find tiene que juntar de punta a punta
esp = np.zeros((41, 41), bool)
esp[0, :] = esp[:, -1] = esp[-1, :] = True
esp[2:, 0] = esp[2, :-2] = esp[2:-2, -3] = esp[-3, 2:-2] = True
fuerte = np.zeros_like(esp); fuerte[-3, 5] = True
assert np.array_equal(L.histeresis(esp, fuerte, 10), grupos_directo(esp)[0] == grupos_directo(esp)[0][-3, 5])
m = rng.random((30, 30)) < 0.2
d = m.copy(); d[1:] |= m[:-1]; d[:-1] |= m[1:]; d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
assert np.array_equal(L.dilatar_cruz(m), d)
assert L._zona((50, 40, -5, 10), (30, 20)) == (0, 10, 30, 20)
assert L._zona((5, 5, 5, 9), (30, 20)) is None
print("ok cuentas (cierre, grupos conexos, histéresis y dilatación como ndimage)")

# ------------------------------------------------------------- 3. contra la referencia aprobada
DATOS = AQUI / "datos_limpiar_plano"
X0, Y0 = 1150, 1140                                        # el recorte, en el plano
SELLO = (1215 - X0, 1195 - Y0, 1815 - X0, 1465 - Y0)       # la zona de sello, en el recorte
recorte = Image.open(DATOS / "recorte_original.png")
ref = np.asarray(Image.open(DATOS / "recorte_limpio_2x.png").convert("L")).astype(int)
hecha = L.limpiar(recorte, [SELLO])
assert hecha.mode == "L" and hecha.size == (600, 600)
o = np.asarray(hecha).astype(int)
dif = np.abs(o - ref)
M = 2 * 20
adentro = dif[M:-M, M:-M]
print(f"   interior: {100 * (adentro > 0).mean():.3f} % distintos, "
      f"{100 * (adentro > 8).mean():.3f} % con más de 8, media {adentro.mean():.3f}; "
      f"todo el recorte: {100 * (dif > 0).mean():.2f} % distintos")
assert (adentro > 8).mean() <= 0.001 and adentro.mean() < 0.5
assert (dif > 0).mean() <= 0.03
# sin la zona de sello el sello tenue se pierde (por eso existe la zona)
sin = np.asarray(L.limpiar(recorte)).astype(int)
z = (slice(2 * SELLO[1], 2 * SELLO[3]), slice(2 * SELLO[0], 2 * SELLO[2]))
assert (sin[z] < 200).sum() < (o[z] < 200).sum()
# lo de fuera de la zona no cambia
fuera = np.ones(o.shape, bool); fuera[z] = False
assert np.array_equal(sin[fuera], o[fuera])
# el papel queda blanco: la mayoría es 255, y la tinta sigue
assert (o == 255).mean() > 0.6 and (o < 100).sum() > 2000
print("ok contra la referencia aprobada")

# ------------------------------------------------------------- 4. tiempo, con el tamaño del plano
grande = Image.fromarray(np.tile(np.asarray(recorte), (6, 7))[:1533, :2000])
t0 = time.monotonic()
g = L.limpiar(grande, [(100, 100, 700, 400)])
seg = time.monotonic() - t0
print(f"   2000 × 1533 a 2x: {seg:.1f} s")
assert g.size == (4000, 3066) and seg < 30
del g, grande

# ------------------------------------------------------------- 5. la orden en un dibujo
d = Path(tempfile.mkdtemp())
plano = d / "mensura 1958.png"
recorte.save(plano)
original_bytes = hashlib.sha256(plano.read_bytes()).hexdigest()
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
doc.path = str(d / "lote12.dwg")
ddef = doc.doc.add_image_def(filename=str(plano), size_in_pixel=(300, 300))
img = msp.add_image(ddef, insert=(1000, 2000), size_in_units=(150, 150))  # 0,5 por píxel
doc.doc.appids.add("GEOCAD_ASPECTO")                       # como si tuviera ASPECTOIMAGEN
img.set_xdata("GEOCAD_ASPECTO", [(1000, "ASPECTO 1"), (1000, "{}"), (1000, str(plano))])
esquinas_antes = [tuple(round(c, 6) for c in p) for p in G.esquinas(img)]
msgs, fin = [], []


class Ctrl:
    def __init__(self):
        self.window = types.SimpleNamespace(document=doc)
        self.index = GeometryIndex(doc)
        self.selection = set()
        self._pick_tolerance = 0.2
    def pick_entity(self, p):
        h = self.index.pick(tuple(p), self._pick_tolerance)
        return self.index.entity(h) if h else None


def herramienta(selection=()):
    msgs.clear(); fin.clear()
    ctrl = Ctrl(); ctrl.selection = set(selection)
    ctx = ToolContext(execute=hist.execute, prompt=lambda t: None, echo=msgs.append,
                      finish=lambda: fin.append(1), services=ctrl)
    t = LP.LimpiarPlanoTool(ctx); t.start()
    return t


def punto(px, py):
    """El píxel (arriba a la izquierda = 0, 0) de la imagen en el dibujo."""
    return G.pixel_a_mundo(img, (px * G.tamano(img)[0] / 300, -py * G.tamano(img)[1] / 300))


t = herramienta()
assert t.resaltado(punto(150, 150))["cursor"]               # se ilumina al pasar
t.on_point((-500, -500)); assert not fin and t.img is None  # nada ahí: sigue pidiendo
t.on_point(punto(150, 150)); assert t.img is img and not fin
t.on_cancel(); assert fin and any("cancelado" in m for m in msgs)
assert img.image_def.dxf.filename == str(plano)

t = herramienta({img.dxf.handle})                           # elegida de antes
assert t.img is img
t.on_point(punto(10, 10)); t.on_point(punto(40, 30))       # una zona y...
assert t.zonas == [(10, 10, 40, 30)], (t.zonas, msgs)
assert t.on_option("D") and t.zonas == []                   # ...D la quita
t.on_point(punto(SELLO[0], SELLO[1]))
assert t.preview_segments(punto(250, 250))                  # el rectángulo sigue al cursor
assert not t.ortho_applies()
t.on_point(punto(400, 400))                                 # se recorta a la imagen
assert t.zonas == [(SELLO[0], SELLO[1], 300, 300)], t.zonas
assert len(t.resaltado(None)["sel_borde"]) == 4
t.on_enter()
copia = d / "lote12_imagenes" / "mensura 1958_limpio.png"
assert fin and copia.is_file(), msgs
assert img.image_def.dxf.filename == str(copia)
assert hashlib.sha256(plano.read_bytes()).hexdigest() == original_bytes   # el original NUNCA se toca
assert tuple(img.dxf.image_size)[:2] == (600, 600)          # al doble...
assert [tuple(round(c, 6) for c in p) for p in G.esquinas(img)] == esquinas_antes   # ...en el mismo lugar
assert abs(img.dxf.u_pixel[0] - 0.25) < 1e-9
assert np.array_equal(np.asarray(Image.open(copia).convert("L")), o)   # lo mismo que la cuenta
assert LP.leer(img) == (str(plano), [(SELLO[0], SELLO[1], 300, 300)])
assert not img.has_xdata("GEOCAD_ASPECTO")                  # ASPECTOIMAGEN parte ahora de la limpia
assert any("Plano limpio" in m and "el original no se toca" in m.lower() for m in msgs), msgs

t = herramienta({img.dxf.handle})                           # otra vez: desde el ORIGINAL, con sus zonas
assert t.original == plano and t.zonas == [(SELLO[0], SELLO[1], 300, 300)]
assert any("ya está limpia" in m for m in msgs)
assert t.on_option("D") and t.zonas == []
t.on_enter()
copia2 = d / "lote12_imagenes" / "mensura 1958_limpio_2.png"   # no pisa la anterior
assert img.image_def.dxf.filename == str(copia2) and copia.is_file()
assert tuple(img.dxf.image_size)[:2] == (600, 600)          # sigue al doble, no al cuádruple
assert [tuple(round(c, 6) for c in p) for p in G.esquinas(img)] == esquinas_antes
assert LP.leer(img) == (str(plano), [])
hist.undo()                                                 # U: la limpieza anterior
assert img.image_def.dxf.filename == str(copia) and LP.leer(img)[1] == [(SELLO[0], SELLO[1], 300, 300)]
hist.undo()                                                 # U: como estaba al principio
assert img.image_def.dxf.filename == str(plano) and LP.leer(img) is None
assert tuple(img.dxf.image_size)[:2] == (300, 300) and abs(img.dxf.u_pixel[0] - 0.5) < 1e-9
assert img.has_xdata("GEOCAD_ASPECTO")                      # U devuelve la marca del aspecto

# con transparencia (un recorte de GeoCAD): lo transparente sigue transparente
rgba = Image.new("RGBA", (40, 30), (255, 255, 255, 255))
for x in range(5, 35):
    rgba.putpixel((x, 15), (0, 0, 0, 255))
for x in range(30, 40):
    for y in range(30):
        rgba.putpixel((x, y), (0, 0, 0, 0))
h2 = L.limpiar(rgba)
assert h2.mode == "LA" and h2.size == (80, 60)
assert h2.getpixel((79, 10))[1] == 0 and h2.getpixel((10, 10)) == (255, 255)
assert h2.getpixel((20, 31))[0] < 128                       # la línea sigue

# un archivo que no está
ddef3 = doc.doc.add_image_def(filename=str(d / "no_esta.png"), size_in_pixel=(10, 10))
img3 = msp.add_image(ddef3, insert=(9000, 0), size_in_units=(10, 10))
herramienta({img3.dxf.handle})
assert fin and any("no se encuentra" in m for m in msgs)
print("ok la orden en un dibujo")
print("TODO OK")
