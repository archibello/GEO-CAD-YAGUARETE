"""Módulo «Google Earth» (3.33.0): captura georreferenciada y mosaico, sin
Google Earth real. Un Google Earth SIMULADO dibuja una textura conocida en
POSGAR 2007 faja 7 (Posadas) vista desde la cámara, en geográficas (así la
foto queda girada la convergencia, como en la real), con las cruces magenta
donde caen las marcas, y le habla al servidor de GeoCAD por HTTP como el de
verdad (/vista con BBOX y cámara, /camara con flyToView). Se comprueba: las
marcas y la detección por el cruce de los brazos (también con media cruz
tapada, como la brújula), la proyectiva, el GeoTIFF / PNG+PGW leído de nuevo
en su lugar (menos de medio píxel), el mosaico como UNA imagen con costuras
medidas, el plan de piezas, que nunca se vuela a una posición inválida y que
la vista vuelve a donde estaba."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import io, math, os, sys, tempfile, threading, time, urllib.request
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # COMUN: el núcleo como paquete
from pathlib import Path
import numpy as np
from PIL import Image
from pyproj import Transformer
from nucleo import googleearth as GE

SIS7 = "EPSG:5349"
a_planas, a_geo = GE.transformadores(SIS7)
A7 = Transformer.from_crs("EPSG:4326", SIS7, always_xy=True)
LON0, LAT0 = -55.896, -27.367


X0, Y0 = A7.transform(LON0, LAT0)
_PASO = 0.25                                       # m: un terreno de 700 x 560 m al azar,
_rng = np.random.default_rng(7)                    # suavizado (detalle de ~1,5 m, sin repetirse)
_campo = _rng.random((2240, 2800, 3)).astype(np.float32)
for _eje in (0, 1):
    _c = np.cumsum(_campo, axis=_eje)
    _campo = (np.take(_c, range(6, _c.shape[_eje]), axis=_eje)
              - np.take(_c, range(0, _c.shape[_eje] - 6), axis=_eje)) / 6
_campo = (_campo - _campo.min()) / (_campo.max() - _campo.min())


def textura(X, Y):
    """Lo que «hay» en el terreno (RGB 30-220, sin magenta)."""
    c = (np.asarray(X) - (X0 - 350)) / _PASO
    f = ((Y0 + 280) - np.asarray(Y)) / _PASO
    c0 = np.clip(np.floor(c).astype(int), 0, _campo.shape[1] - 2)
    f0 = np.clip(np.floor(f).astype(int), 0, _campo.shape[0] - 2)
    fc, ff = (c - c0)[..., None], (f - f0)[..., None]
    v = (_campo[f0, c0] * (1 - fc) + _campo[f0, c0 + 1] * fc) * (1 - ff) \
        + (_campo[f0 + 1, c0] * (1 - fc) + _campo[f0 + 1, c0 + 1] * fc) * ff
    return 30 + 190 * v


class GESimulado:
    """La ventana de Google Earth: W x H píxeles; el ancho visto es 1,4 veces
    la altura de la cámara; el BBOX que informa es 3 % más grande que lo que
    se ve (en la real tampoco coincide)."""
    W, H = 720, 520

    def __init__(self, lon, lat, rango):
        self.cam = [lon, lat, rango]
        self.marcas = []
        self.vuelos = []

    def grados(self):
        lon, lat, rango = self.cam
        m_lon = 111320 * math.cos(math.radians(lat))
        ancho_m = 1.4 * rango
        dlon = ancho_m / m_lon / self.W
        return dlon, dlon * m_lon / 110574           # píxeles cuadrados en el suelo

    def a_pixel(self, lon, lat):
        dlon, dlat = self.grados()
        return (self.W / 2 + (lon - self.cam[0]) / dlon, self.H / 2 - (lat - self.cam[1]) / dlat)

    def bbox(self):
        dlon, dlat = self.grados()
        k = 1.03
        return (self.cam[0] - k * dlon * self.W / 2, self.cam[1] - k * dlat * self.H / 2,
                self.cam[0] + k * dlon * self.W / 2, self.cam[1] + k * dlat * self.H / 2)

    def foto(self, tapar=None):
        dlon, dlat = self.grados()
        xs = self.cam[0] + (np.arange(self.W) + 0.5 - self.W / 2) * dlon
        ys = self.cam[1] - (np.arange(self.H) + 0.5 - self.H / 2) * dlat
        LON, LAT = np.meshgrid(xs, ys)
        X, Y = A7.transform(LON, LAT)
        a = textura(X, Y).astype(np.uint8)
        cruz = GE.imagen_marca()
        for _k, lon, lat in self.marcas:
            px, py = self.a_pixel(lon, lat)
            c0, r0 = int(round(px - 16.5)), int(round(py - 16.5))
            zona = a[r0:r0 + 33, c0:c0 + 33]
            al = cruz[..., 3:] > 0
            zona[:] = np.where(al, cruz[..., :3], zona)
        if tapar == "NE":                               # la brújula: media cruz tapada
            px, py = self.a_pixel(*[(lo, la) for kk, lo, la in self.marcas if kk == "NE"][0])
            a[: int(py) + 4, int(px) + 4:] = (40, 40, 40)   # el brazo derecho y casi todo el de arriba
        return a


# ------------------------------------------------------------- 1. KML, marcas y vista
k = GE.kml_enlaces(48765).decode()
assert "http://127.0.0.1:48765/vista" in k and "onStop" in k and "<flyToView>1</flyToView>" in k
assert "[bboxWest]" in k and "[lookatHeading]" in k
assert not GE.posicion_valida(0, 0, 200) and not GE.posicion_valida(-55, -27, 0)
assert not GE.posicion_valida(float("nan"), -27, 200) and not GE.posicion_valida(-200, -27, 200)
assert GE.posicion_valida(LON0, LAT0, 200)
try:
    GE.kml_lookat(0, 0, 200)
    raise AssertionError("voló a 0, 0")
except GE.GoogleEarthError:
    pass
assert "<heading>0</heading><tilt>0</tilt>" in GE.kml_lookat(LON0, LAT0, 200).decode()
assert GE.leer_vista({"BBOX": "0,0,0,0", "cam": "0,0,0,0,0"}) is None
assert GE.leer_vista({"BBOX": "-55.9,-27.4,-55.8,-27.3"}) is None
v = GE.leer_vista({"BBOX": "-55.9,-27.4,-55.8,-27.3", "cam": f"{LON0},{LAT0},374,0,0", "px": "2630,1846"})
assert v.vertical and v.ancho_px == 2630 and v.rango == 374
assert not GE.leer_vista({"BBOX": "-55.9,-27.4,-55.8,-27.3", "cam": f"{LON0},{LAT0},374,30,0"}).vertical
assert not GE.leer_vista({"BBOX": "-55.9,-27.4,-55.8,-27.3", "cam": f"{LON0},{LAT0},374,0,12"}).vertical
assert GE.leer_vista({"BBOX": "-55.9,-27.4,-55.8,-27.3", "cam": f"{LON0},{LAT0},374,0,359.9"}).vertical
m = GE.marcas_de_bbox(0, 0, 10, 20)
assert m == [("SO", 1, 2), ("SE", 9, 2), ("NE", 9, 18), ("NO", 1, 18)]
assert GE.kml_marcas(m, "http://x/m.png").decode().count("<Placemark>") == 4
print("ok KML, marcas y vista; nunca se vuela a 0,0")

# ------------------------------------------------------------- 2. detección de las cruces
sim = GESimulado(LON0, LAT0, 374)
sim.marcas = GE.marcas_de_bbox(*sim.bbox())
foto = sim.foto()
pix = GE.detectar(foto)
for kk, lon, lat in sim.marcas:
    ex, ey = sim.a_pixel(lon, lat)
    assert math.hypot(pix[kk][0] - ex, pix[kk][1] - ey) < 0.75, (kk, pix[kk], ex, ey)
tapada = GE.detectar(sim.foto(tapar="NE"))
assert math.hypot(tapada["NE"][0] - pix["NE"][0], tapada["NE"][1] - pix["NE"][1]) < 0.75, (tapada, pix)
sin = foto.copy()
sin[GE.mascara(sin) & (np.arange(sim.W)[None, :] < sim.W // 2) & (np.arange(sim.H)[:, None] < sim.H // 2)] = 0
try:
    GE.detectar(sin)
    raise AssertionError("faltaba una cruz")
except GE.GoogleEarthError as e:
    assert "arriba a la izquierda" in str(e) and "chincheta" in str(e)
print("ok cruces por el cruce de los brazos (también tapadas a medias); falta una: avisa cuál")

# ------------------------------------------------------------- 3. una captura: GeoTIFF y PNG+PGW
p = GE.pieza_de_foto(foto, sim.marcas, a_planas)
assert p.residuo < 0.05, p.residuo
conv = math.degrees(math.atan2(*(lambda a, b: (b[1] - a[1], b[0] - a[0]))(
    GE.aplicar(p.H, 100, 300), GE.aplicar(p.H, 600, 300))))
from pyproj import Proj
assert abs(conv - Proj(SIS7).get_factors(LON0, LAT0).meridian_convergence) < 0.03, conv
mc = GE.marco([p])
assert abs(mc.res - round(p.tamano_pixel(), 2)) < 1e-9
im = GE.componer([p], mc)
assert im.shape == (mc.alto, mc.ancho, 3)
assert not GE.mascara(im).any(), "quedaron cruces adentro del recorte"
xs = mc.xmin + (np.arange(mc.ancho) + 0.5) * mc.res
ys = mc.ymax - (np.arange(mc.alto) + 0.5) * mc.res
ideal = textura(*np.meshgrid(xs, ys))
err = np.abs(im.astype(float) - ideal).mean()
assert err < 10, err                 # dos remuestreos de un detalle de 1,5 m
dy, dx = GE._fase(ideal.mean(-1), im.astype(float).mean(-1))
assert math.hypot(dx, dy) < 0.5, (dx, dy)                     # menos de medio píxel
carpeta = Path(os.environ["HOME"]) / "Documentos" / "GeoCAD Google Earth"
assert GE.problema_carpeta(carpeta) == "" and carpeta.is_dir()
ruta = carpeta / GE.nombre_archivo("05/2024", "tif", 0)
# 3.33.3: fecha-hora, coordenadas y la fecha de la imagen al final (Fernando)
assert ruta.name.startswith("GE_2") and ruta.name.endswith("_img-05-2024.tif"), ruta.name
escritas = GE.guardar(im, mc, SIS7, ruta, "tif", descripcion="fecha 05/2024")
assert [e.suffix for e in escritas] == [".tif", ".tfw"]
with Image.open(ruta) as t:
    assert t.size == (mc.ancho, mc.alto) and t.mode == "RGB"
    assert np.array_equal(np.asarray(t), im)
    tags = dict(t.tag_v2)
assert tuple(tags[33550])[:2] == (mc.res, mc.res)
assert abs(tags[33922][3] - mc.xmin) < 1e-6 and abs(tags[33922][4] - mc.ymax) < 1e-6
assert 5349 in tuple(tags[34735]) and "05/2024" in tags[270]
# la misma lectura que INSERTARGEO (imagengeo.coef_de_geotiff)
sys.path.insert(0, str(Path(HERE).parents[1] / "INGECAD" / "codigo"))
mundo = [float(x) for x in ruta.with_suffix(".tfw").read_text().split()]
assert abs(mundo[4] - (mc.xmin + mc.res / 2)) < 1e-6 and abs(mundo[5] - (mc.ymax - mc.res / 2)) < 1e-6
rp = carpeta / "una.png"
assert [e.suffix for e in GE.guardar(im, mc, SIS7, rp, "png")] == [".png", ".pgw", ".prj"]
with Image.open(rp) as t:
    assert np.array_equal(np.asarray(t.convert("RGB")), im)
assert "Argentina_Zone_7" in rp.with_suffix(".prj").read_text()
try:
    GE.guardar(im, mc, SIS7, carpeta / "x.jpg", "jpg")
    raise AssertionError("JPG sin escritor")
except GE.GoogleEarthError:
    pass
GE.guardar(im, mc, SIS7, carpeta / "x.jpg", "jpg",
           escribir_jpg=lambda a, r: Image.fromarray(a).save(r, quality=92))
assert (carpeta / "x.jgw").is_file() and (carpeta / "x.prj").is_file()
# un GeoTIFF de varias tiras
grande = np.random.default_rng(1).integers(0, 255, (300, 400, 3), np.uint8)
GE.guardar(grande, GE.Marco(1000.0, 2000.0, 0.1, 400, 300), SIS7, carpeta / "g.tif", "tif")
with Image.open(carpeta / "g.tif") as t:
    assert np.array_equal(np.asarray(t), grande)
RUTA1, MC1 = ruta, mc
print(f"ok una captura: residuo {p.residuo * 1000:.0f} mm, giro = convergencia, error "
      f"{math.hypot(dx, dy):.2f} px; GeoTIFF, PNG+PGW+PRJ y JPG+JGW se leen de nuevo")

# ------------------------------------------------------------- 4. carpeta y ajustes comunes
assert "portal" in GE.problema_carpeta("/run/user/1000/doc/abc123/Fotos")
assert "ruta completa" in GE.problema_carpeta("Documentos")
solo = Path(os.environ["HOME"]) / "solo_lectura"
solo.mkdir()
solo.chmod(0o500)
if os.geteuid() != 0:
    assert "No se puede guardar" in GE.problema_carpeta(solo / "x")
solo.chmod(0o700)
aj = GE.ajustes()
assert aj["carpeta"].endswith("GeoCAD Google Earth") and aj["altura_pieza"] == 200 and aj["formato"] == "tif"
GE.guardar_ajustes({"formato": "png", "altura_pieza": "150,5", "calidad": "nada", "otra": 1})
aj = GE.ajustes()
assert aj["formato"] == "png" and aj["altura_pieza"] == 150.5 and aj["calidad"] == "pantalla"
assert GE.archivo_ajustes() == Path(os.environ["HOME"]) / ".config" / "geocad" / "googleearth.json"
GE.archivo_ajustes().write_text("{dañado")
assert GE.ajustes() == GE.DEFECTOS
print("ok carpeta común (sin portal, escribible) y ajustes en ~/.config/geocad/googleearth.json")

# ------------------------------------------------------------- 5. sistemas
assert GE.sistema_sugerido(LON0, LAT0) == "EPSG:5348"            # faja 6 (meridiano -57)
assert GE.sistema_sugerido(-54.2, -26) == "EPSG:5349"
assert GE.sistema_sugerido(2.35, 48.85) == "EPSG:32631"
assert GE.aviso_faja(SIS7, LON0) == "" and "faja 5" in GE.aviso_faja("EPSG:5347", LON0)
assert GE.es_planas(SIS7) and not GE.es_planas("EPSG:4326") and GE.epsg_de("epsg:5349") == 5349
print("ok sistema sugerido por la ubicación y aviso de faja")

# ------------------------------------------------------------- 6. el servidor
from nucleo import googleearth_vivo as V
import re as _re
srv = V.Servidor(puerto=0)
puerto = srv.iniciar()
URL = f"http://127.0.0.1:{puerto}"


def pedir(ruta):
    with urllib.request.urlopen(URL + ruta, timeout=5) as r:
        return r.read()


consulta = (f"/vista?BBOX=-55.9,-27.4,-55.8,-27.3&cam={LON0},{LAT0},374,0,0&px=2630,1846")
assert b"<Placemark>" not in pedir(consulta), "cruces sin capturar"
assert srv.vista.rango == 374 and len(srv.marcas) == 4
srv.armado = True                       # 3.33.4: las cruces van por /camara, nunca por /vista
assert b"<Placemark>" not in pedir(consulta)
k = pedir("/camara")
assert k.count(b"<Placemark>") == 4 and f"{URL}/marca.png".encode() in k and b"<LookAt>" not in k
srv.armado = False
assert b"<Placemark>" not in pedir("/camara")
srv.cruces = GE.marcas_de_bbox(-55.9, -27.4, -55.8, -27.3)      # las de una pieza
assert pedir("/camara").count(b"<Placemark>") == 4
srv.cruces = None
srv.t_camara = 0.0                      # (lo de abajo prueba el enlace desde cero)
assert pedir("/marca.png").startswith(b"\x89PNG")
assert b"/vista" in pedir("/geocad.kml")
assert not srv.conectado()
assert b"<LookAt>" not in pedir("/camara") and srv.conectado()
try:
    srv.volar(0, 0, 200)
    raise AssertionError("voló a 0,0")
except GE.GoogleEarthError:
    pass
srv.volar(LON0, LAT0, 200)
assert b"<LookAt>" in pedir("/camara") and b"<LookAt>" not in pedir("/camara")   # una sola vez
srv.pendiente = (0.0, 0.0, 200.0)                       # aunque se colara: no se vuela
assert b"<LookAt>" not in pedir("/camara")
pedir("/vista?BBOX=0,0,0,0&cam=0,0,0,0,0")              # la vista vacía no pisa la buena
assert srv.vista.lon == LON0
try:
    pedir("/otra")
    raise AssertionError("404")
except urllib.error.HTTPError as e:
    assert e.code == 404
otro = V.Servidor(puerto=puerto)                        # puerto ocupado: el siguiente
assert otro.iniciar() != puerto
otro.detener()
print("ok servidor: vista, cruces sólo armado, vuelo una vez, nunca a 0,0, puerto ocupado")


class EnlaceSimulado(threading.Thread):
    """Google Earth pidiendo /camara cada 50 ms y /vista al detenerse."""

    def __init__(self, sim):
        super().__init__(daemon=True)
        self.sim, self.parar, self.vuelos = sim, threading.Event(), []

    def vista(self):
        o, s, e, n = self.sim.bbox()
        lon, lat, rango = self.sim.cam
        k = pedir(f"/vista?BBOX={o},{s},{e},{n}&cam={lon},{lat},{rango},0,0&px={GESimulado.W},{GESimulado.H}")
        self.sim.marcas = [(None, float(a), float(b)) for a, b in
                           _re.findall(rb"<coordinates>([-\d.]+),([-\d.]+),0", k)]
        # las claves de las marcas no viajan: se ordenan como marcas_de_bbox
        if self.sim.marcas:
            self.sim.marcas = GE.marcas_de_bbox(o, s, e, n)

    def run(self):
        # 3.33.4: como el Google Earth de verdad (registro del 21/10/2026):
        # manda /vista al empezar (cuando lo mueve el usuario) y NUNCA después
        # de un vuelo pedido por el enlace; las cruces llegan por /camara
        self.vista()
        while not self.parar.is_set():
            k = pedir("/camara")
            m = _re.search(rb"<longitude>([-\d.]+)</longitude><latitude>([-\d.]+)</latitude>.*"
                           rb"<range>([\d.]+)</range>", k)
            if m:
                self.sim.cam = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
                self.vuelos.append(tuple(self.sim.cam))
            cruces = [(float(a), float(b)) for a, b in
                      _re.findall(rb"<coordinates>([-\d.]+),([-\d.]+),0", k)]
            claves = ["SO", "SE", "NE", "NO"] if len(cruces) == 4 else [None] * len(cruces)
            self.sim.marcas = [(kk, lo, la) for kk, (lo, la) in zip(claves, cruces)]
            time.sleep(0.05)


# ------------------------------------------------------------- 7. captura de pantalla de punta a punta
sim = GESimulado(LON0, LAT0, 374)
enlace = EnlaceSimulado(sim)
t_enlace = time.time()
enlace.start()
# (3.33.3) esperar la vista del simulador: la de las pruebas de arriba tenía
# otro BBOX y sus cruces armadas, y Pantalla ya no vuela si las ve puestas
while srv.t_vista <= t_enlace or abs(srv.vista.rango - 374) > 1e-6 or srv.vista.lon != LON0:
    time.sleep(0.05)
cap = V.Captura(srv, sim.foto, paso=0.02, quietas=2, tope_quieta=10, tope_vuelo=10)
fotos = cap.pantalla()
assert len(fotos) == 1 and not srv.armado
time.sleep(0.3)
assert sim.marcas == [], "las cruces quedaron en Google Earth"
# 3.33.3: si Google Earth ya muestra las cruces de esta vista no se vuela;
# si no, un vuelo «quieto» (+5 cm); al final la vista queda como estaba
assert abs(sim.cam[2] - 374) < 1e-6 and all(abs(vv[2] - 374) < 0.1 for vv in enlace.vuelos), (sim.cam, enlace.vuelos)
im, mc, piezas, cost = V.procesar(fotos, SIS7)
assert cost == [] and not GE.mascara(im).any()
ideal = textura(*np.meshgrid(mc.xmin + (np.arange(mc.ancho) + 0.5) * mc.res,
                             mc.ymax - (np.arange(mc.alto) + 0.5) * mc.res))
dy, dx = GE._fase(ideal.mean(-1), im.astype(float).mean(-1))
assert math.hypot(dx, dy) < 0.5, (dx, dy)
# y la prueba es sensible: un píxel corrido se nota
dy2, dx2 = GE._fase(ideal.mean(-1)[:, 1:], im.astype(float).mean(-1)[:, :-1])
assert 0.7 < math.hypot(dx2, dy2) < 1.3, (dx2, dy2)
RES_PANTALLA = mc.res
print(f"ok captura de pantalla: vuelo quieto, cruces puestas y quitadas, {mc.ancho} x {mc.alto} px "
      f"de {mc.res:.2f} m, error {math.hypot(dx, dy):.2f} px")

pasos = []
cap = V.Captura(srv, sim.foto, aviso=lambda t, f=None: pasos.append(t), paso=0.02, quietas=2,
                tope_quieta=10, tope_vuelo=10)
cap.pantalla()
# 3.33.4: la vista está derecha: se ponen las cruces sin mover la cámara
assert pasos[0] == "1/5 Poniendo las cruces..." and pasos[-1].startswith("3/5 Foto"), pasos
n_vuelos = len(enlace.vuelos)
pasos = []
cap.pantalla(volar=True)                                 # al reintentar: se endereza volando
assert pasos[0] == "1/5 Enderezando la vista y poniendo las cruces..." and len(enlace.vuelos) > n_vuelos
assert any(p.startswith("2/5 Cruces puestas; esperando que cargue la imagen... ") for p in pasos)
time.sleep(0.3)

# ------------------------------------------------------------- 8. el mosaico: UNA imagen
v = srv.vista
plan = GE.plan_mosaico(v, a_planas, a_geo, 200)
assert (plan.columnas, plan.filas) == (3, 3) and len(plan.centros) == 9 and plan.rango == 200
assert plan.centros[0][:2] == (0, 0) and plan.centros[0][3] > plan.centros[-1][3]   # la fila 0, al norte
try:
    GE.plan_mosaico(v, a_planas, a_geo, 40, ajustar=False)
    raise AssertionError("pasó el tope")
except GE.GoogleEarthError as e:
    assert "tope es 25" in str(e)
p40 = GE.plan_mosaico(v, a_planas, a_geo, 40)          # 3.33.3: sube la altura y entra
assert len(p40.centros) <= 25 and p40.rango > 40 and p40.pedida == 40, p40
assert len(GE.plan_mosaico(v, a_planas, a_geo, 400).centros) == 1   # más alto que la vista: una
avisos = []
cap = V.Captura(srv, sim.foto, aviso=lambda t, f=None: avisos.append(t), paso=0.02, quietas=2,
                tope_quieta=10, tope_vuelo=10)
n_vuelos = len(enlace.vuelos)
fotos = cap.mosaico(a_planas, a_geo, 200)
assert len(fotos) == 9 and "1/5 Preparando 9 pieza(s) a 200 m..." in avisos
assert any(a.startswith("2/5 Pieza 9 de 9: volando... · faltan unos") for a in avisos), avisos
assert any(a.startswith("2/5 Pieza 1 de 9: esperando que cargue la imagen... 0 s") for a in avisos)
assert avisos[-1] == "3/5 Volviendo a la vista de antes..."
assert all(GE.posicion_valida(*vv) for vv in enlace.vuelos)
time.sleep(0.2)                          # el simulador mueve la cámara al leer /camara
assert abs(sim.cam[0] - LON0) < 1e-9 and abs(sim.cam[2] - 374) < 1e-6, "la vista no volvió"
time.sleep(0.3)
assert sim.marcas == [] and not srv.armado
fr = []
im, mc, piezas, cost = V.procesar(fotos, SIS7, progreso=fr.append)
assert fr[-1] == 1.0 and not GE.mascara(im).any()
assert len(cost) == 12 and max(c for _p, _q, c in cost) < mc.res, [round(c, 3) for *_x, c in cost]
assert mc.res < 0.6 * RES_PANTALLA, (mc.res, RES_PANTALLA)   # más detalle que la pantalla
ideal = textura(*np.meshgrid(mc.xmin + (np.arange(mc.ancho) + 0.5) * mc.res,
                             mc.ymax - (np.arange(mc.alto) + 0.5) * mc.res))
err = np.abs(im.astype(float) - ideal).mean()
dy, dx = GE._fase(ideal.mean(-1), im.astype(float).mean(-1))
assert err < 10 and math.hypot(dx, dy) < 0.5, (err, dx, dy)
ancho_m, alto_m = mc.ancho * mc.res, mc.alto * mc.res
assert ancho_m > 380 and alto_m > 260, (ancho_m, alto_m)      # cubre la vista de 374 m
# las costuras se miden de verdad: la pieza del medio corrida 1 m al este
medio = [q for q in piezas if (q.fila, q.col) == (1, 1)][0]
corrida = GE.Pieza(medio.imagen, medio.pix, {kk: (x + 1.0, y) for kk, (x, y) in medio.xy.items()}, 1, 1)
otras = [corrida if q is medio else q for q in piezas]
malas = [c for q1, q2, c in GE.costuras(otras, mc.res) if corrida in (q1, q2)]
assert len(malas) == 4 and all(0.8 < c < 1.2 for c in malas), malas
# cancelar a mitad de camino: la vista vuelve igual
cap = V.Captura(srv, sim.foto, aviso=lambda t, f=None: cap.cancelar.set() if "Pieza 3" in t else None,
                paso=0.02, quietas=2, tope_quieta=10, tope_vuelo=10)
try:
    cap.mosaico(a_planas, a_geo, 200)
    raise AssertionError("no se canceló")
except V.Cancelado:
    pass
time.sleep(0.2)
assert abs(sim.cam[0] - LON0) < 1e-9 and abs(sim.cam[2] - 374) < 1e-6 and not srv.armado
print(f"ok mosaico 3 x 3 a 200 m: UNA imagen de {ancho_m:.0f} x {alto_m:.0f} m con píxel de "
      f"{mc.res:.2f} m, costuras hasta {max(c for *_x, c in cost) * 100:.1f} cm, error "
      f"{math.hypot(dx, dy):.2f} px; la vista vuelve (también al cancelar)")
enlace.parar.set()
enlace.join(2)
srv.detener()
assert not srv.vivo

# ------------------------------------------------------------- 9. sin Google Earth
srv = V.Servidor(puerto=0)
srv.iniciar()
cap = V.Captura(srv, sim.foto, paso=0.02, quietas=2, tope_quieta=1, tope_vuelo=0.5)
try:
    cap.pantalla()
    raise AssertionError("capturó sin vista")
except GE.GoogleEarthError as e:
    assert "Abrí Google Earth con GeoCAD" in str(e)
srv.detener()
viejo = os.environ.pop("DISPLAY", None)
assert V.AtajoX11(lambda: None).iniciar() is False
try:
    V.FotoX11()
    raise AssertionError("foto sin X11")
except GE.GoogleEarthError as e:
    assert "X11" in str(e)
print("ok sin Google Earth ni X11: avisa, no se cuelga")
if viejo is not None:
    os.environ["DISPLAY"] = viejo

# ------------------------------------------------------------- 10. IngeCAD: menú, órdenes, insertar
import types
import ezdxf
from importlib import import_module
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext

lp = load_plugin(Path(HERE).parents[1] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
assert "ingecad_plugin_geocad.googleearth_ui" not in sys.modules            # nada pesado al cargar
assert "ingecad_plugin_geocad.googleearth_vivo" not in sys.modules
plugin = import_module("ingecad_plugin_geocad")
mods = import_module("ingecad_plugin_geocad.modulos")
GEC = import_module("ingecad_plugin_geocad.googleearth_cmd")
G = import_module("ingecad_plugin_geocad.georref")
puente = import_module("ingecad_plugin_geocad.puente")


def ordenes(spec):
    return set(spec.commands) | set(spec.tools)


def submenu_ge(spec):
    return next((s for s in spec.menu if getattr(s, "label", "") == "Google Earth"), None)


assert mods.estado("ingecad")["googleearth"] is True                        # nuevo: se ofrece prendido
spec = plugin.construir_spec()
assert {"GEOEARTHOPEN", "GEOEARTHCAPTURE", "GEOEARTHSETUP", "GEOEARTHINSERT"} <= ordenes(spec)
sub = submenu_ge(spec)
assert [i.command for i in sub.items] == ["GEOEARTHOPEN", "GEOEARTHCAPTURE", "GEOEARTHSETUP"]
assert sub.items[0].icon and sub.items[1].icon
import json as _json
_es = Path(HERE).parents[1] / "INGECAD" / "codigo" / "geocad" / "i18n" / "es"
ui_es = _json.loads((_es / "ui.json").read_text(encoding="utf-8"))
assert ui_es["Capture view (Ctrl+Alt+G)"] == "Capturar vista (Ctrl+Alt+G)"
assert _json.loads((_es / "commands.json").read_text(encoding="utf-8"))["GEOEARTHCAPTURE"]["name"] == "CAPTURARGE"
mods.guardar("ingecad", {"googleearth": False})
spec = plugin.construir_spec()
assert not {"GEOEARTHOPEN", "GEOEARTHCAPTURE", "GEOEARTHSETUP", "GEOEARTHINSERT"} & ordenes(spec)
assert submenu_ge(spec) is None
mods.guardar("ingecad", {"googleearth": True, "georref": False})             # depende de Imágenes
assert mods.estado("ingecad")["googleearth"] is False and submenu_ge(plugin.construir_spec()) is None
mods.guardar("ingecad", {"georref": True})
assert submenu_ge(plugin.construir_spec()) is not None
q = [m for m in mods.catalogo("qgis") if m.clave == "googleearth"]
assert q and not q[0].requiere
print("ok IngeCAD: GeoCAD > Google Earth (Abrir, Capturar Ctrl+Alt+G, Configurar) sólo con el módulo")

# la captura recién guardada entra en su lugar, en la capa actual; U la quita
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
msgs, fin = [], []
ventana = types.SimpleNamespace(document=doc, zoom_to_entity=lambda e: None)
ctx = ToolContext(execute=hist.execute, prompt=lambda t: None, echo=msgs.append,
                  finish=lambda: fin.append(1), services=types.SimpleNamespace(window=ventana))
GEC._PENDIENTES.append(str(RUTA1))
GEC.InsertarCapturaTool(ctx).start()
img = next(iter(msp.query("IMAGE")))
assert fin and any("insertada en su lugar (georreferencia del GeoTIFF)" in m for m in msgs), msgs
x, y = G.pixel_a_mundo(img, (0, 0))
assert abs(x - MC1.xmin) < 1e-6 and abs(y - MC1.ymax) < 1e-6
x, y = G.pixel_a_mundo(img, (MC1.ancho, -MC1.alto))   # la y de los píxeles va hacia abajo en negativo
assert abs(x - MC1.xmax) < 1e-6 and abs(y - MC1.ymin) < 1e-6
hist.undo(); assert not list(msp.query("IMAGE")) and not GEC._PENDIENTES
prog = GEC.Programa(types.SimpleNamespace(document=None))
assert prog.sistema() == ("", "el dibujo no tiene sistema")
# 3.33.2: el sistema se lee del dibujo de la pestaña activa (window.document es la
# pestaña; su .doc es el de ezdxf) -- antes salía siempre «sin sistema»
IXm = import_module("ingecad_plugin_geocad.intercambio")
pestana = Document(ezdxf.new("R2018")); h2 = History(pestana)
assert GEC.Programa(types.SimpleNamespace(document=pestana)).sistema() == ("", "el dibujo no tiene sistema")
h2.execute(IXm.DefinirSistemaCommand("EPSG:22177"))
assert GEC.Programa(types.SimpleNamespace(document=pestana)).sistema() == ("EPSG:22177", "del dibujo")
prog.escribir_jpg(np.zeros((4, 5, 3), np.uint8), carpeta / "j.jpg")
assert Image.open(carpeta / "j.jpg").size == (5, 4)
print("ok IngeCAD: la captura entra en su lugar (esquinas al milímetro) y U la quita")

# desde QGIS por el Puente; y el apagado sin rastro
empezadas, ecos = [], []
win = types.SimpleNamespace(tools=types.SimpleNamespace(start_tool=empezadas.append),
                            command_line=types.SimpleNamespace(echo=ecos.append), document=None)
puente._state["window"] = win
puente.handle(GE.mensaje(RUTA1, SIS7))
assert empezadas == ["GEOEARTHINSERT"] and GEC._PENDIENTES == [str(RUTA1.resolve())]
assert "QGIS mandó una captura de Google Earth" in ecos[0]
GEC._PENDIENTES.clear()
assert not GEC.recibir(win, GE.mensaje(carpeta / "no_existe.tif", SIS7))
assert not GEC.recibir(win, {"tipo": "imagen_google_earth", "ruta": "/etc/passwd"})
mods.guardar("ingecad", {"googleearth": False})
assert not GEC.recibir(win, GE.mensaje(RUTA1, SIS7))
GE.archivo_kml().parent.mkdir(parents=True, exist_ok=True)
GE.archivo_kml().write_bytes(GE.kml_enlaces())
plugin.aplicar_modulos(types.SimpleNamespace())
assert not GE.archivo_kml().exists(), "quedó el enlace de Google Earth"
print("ok IngeCAD: lo que manda QGIS se inserta; apagado, sin enlace ni ventanita")

# ------------------------------------------------------------- 11. listo para capturar (3.33.1)
UI = import_module("nucleo.googleearth_ui")
vv = GE.leer_vista({"BBOX": "-55.9,-27.4,-55.8,-27.3", "cam": f"{LON0},{LAT0},374,0,0"})
nada = UI.requisitos(False, None, "", "el dibujo no tiene sistema", "Falta la carpeta.", "ingecad")
assert [ok for ok, _t in nada] == [False] * 4
assert "Abrir Google Earth con GeoCAD" in nada[0][1] and "mové un poco Google Earth" in nada[1][1]
assert nada[2][1] == ("Falta el sistema: el dibujo no tiene sistema. Usá SISTEMAGEO en el dibujo o "
                      "elegilo en Configurar captura")
# lo de la captura de Fernando: enlazado, sin vista ni sistema
caso = UI.requisitos(True, None, "", "el dibujo no tiene sistema", "", "ingecad")
assert [ok for ok, _t in caso] == [True, False, False, True]
con_vista = UI.requisitos(True, vv, "", "el proyecto está en geográficas (EPSG:4326)", "", "qgis")
assert "para esta zona: EPSG:5348" in con_vista[2][1] and "planas en el proyecto" in con_vista[2][1]
listo = UI.requisitos(True, vv, SIS7, "del dibujo", "", "ingecad")
assert all(ok for ok, _t in listo) and listo[1][1] == "Vista recibida: 374 m de altura"
h = UI.html_requisitos(caso)
assert h.count("✔") == 2 and h.count("✘") == 2 and "<br>" in h and UI.ROJO in h and UI.VERDE in h
assert UI.html_requisitos([(False, "a <b> & c")]).endswith("a &lt;b> &amp; c")
assert _re.match(r"\d\d:\d\d:\d\d — hola$", UI.con_hora("hola"))
print("ok listo para capturar: ✔/✘ con qué hacer (enlace, vista, sistema con el sugerido, carpeta)")

# ------------------------------------------------------------- 12. la pantalla de IngeCAD/QGIS posiciona Google Earth (3.33.1)
Z = (X0 - 180.0, Y0 - 60.0, X0 + 120.0, Y0 + 140.0)                       # 300 x 200 m del dibujo
lon, lat, rango = GE.camara_para_zona(Z, a_geo)                          # sin vista: lo medido
assert abs(lon - a_geo(X0 - 30, Y0 + 40)[0]) < 1e-9 and abs(rango - max(300 / (1.016 * GE.UTIL), 200 / (0.733 * GE.UTIL))) < 1e-6
loca = GE.leer_vista({"BBOX": "-55.9,-27.4,-55.8,-27.3", "cam": f"{LON0},{LAT0},374,0,0"})  # 10 km a 374 m
assert GE.camara_para_zona(Z, a_geo, loca, a_planas)[2] == GE.camara_para_zona(Z, a_geo)[2]
try:
    GE.camara_para_zona((1, 1, 0, 0), a_geo)
    raise AssertionError("zona al revés")
except GE.GoogleEarthError:
    pass
assert GE.zona_en(Z, SIS7, "epsg:5349") == Z
z6 = GE.zona_en(Z, SIS7, "EPSG:5348")                                     # a la faja 6: entra adentro
a6, g6 = GE.transformadores("EPSG:5348")
for x, y in ((z6[0], z6[1]), (z6[2], z6[3]), (z6[0], z6[3]), (z6[2], z6[1])):
    xx, yy = a_planas(*g6(x, y))
    assert Z[0] - 1e-6 <= xx <= Z[2] + 1e-6 and Z[1] - 1e-6 <= yy <= Z[3] + 1e-6
assert (z6[2] - z6[0]) > 285 and (z6[3] - z6[1]) > 185, z6         # ~1,5° de giro entre fajas
r = GE.recortar_marco(GE.Marco(0.0, 100.0, 0.5, 400, 200), (10.2, 20.0, 150.0, 90.1))
assert (r.xmin, r.ymax, r.ancho, r.alto) == (10.5, 90.0, 279, 140)
# con Google Earth simulado: el botón «Llevar» y el mosaico de la zona
srv = V.Servidor(puerto=0)
puerto = srv.iniciar()
URL = f"http://127.0.0.1:{puerto}"
sim = GESimulado(LON0, LAT0, 374)
enlace = EnlaceSimulado(sim)
enlace.start()
while srv.vista is None:
    time.sleep(0.05)
lon, lat, rango = GE.camara_para_zona(Z, a_geo, srv.vista, a_planas)     # medido de la vista real
srv.volar(lon, lat, rango)
while abs(sim.cam[2] - rango) > 0.01:
    time.sleep(0.05)
enlace.vista()                          # (Google Earth la manda cuando el usuario lo toca)
cx, cy, ancho, alto = GE._entre_marcas(srv.vista, a_planas)
assert ancho * GE.UTIL >= 300 - 0.5 and alto * GE.UTIL >= 200 - 0.5, (ancho, alto)
assert abs(cx - (X0 - 30)) < 1 and abs(cy - (Y0 + 40)) < 1
assert min(ancho * GE.UTIL - 300, alto * GE.UTIL - 200) < 1, "más alto de lo necesario"   # un lado justo
print(f"ok Llevar Google Earth: la zona de 300 x 200 m queda entre las cruces (cámara a {rango:.0f} m)")
srv.volar(LON0, LAT0, 374)
while abs(sim.cam[2] - 374) > 0.01:
    time.sleep(0.05)
enlace.vista()
plan = GE.plan_mosaico(srv.vista, a_planas, a_geo, 200, zona=Z)
assert (plan.columnas, plan.filas) == (2, 2), (plan.columnas, plan.filas)
try:
    GE.plan_mosaico(srv.vista, a_planas, a_geo, 40, zona=Z, ajustar=False)
    raise AssertionError("tope")
except GE.GoogleEarthError as e:
    assert "Achicá la zona en pantalla" in str(e)
assert len(GE.plan_mosaico(srv.vista, a_planas, a_geo, 40, zona=Z).centros) <= 25   # 3.33.3: se ajusta
cap = V.Captura(srv, sim.foto, paso=0.02, quietas=2, tope_quieta=10, tope_vuelo=10)
fotos = cap.mosaico(a_planas, a_geo, 200, zona=Z)
assert len(fotos) == 4 and abs(sim.cam[2] - 374) < 1e-6                  # y la vista volvió
im, mc, piezas, cost = V.procesar(fotos, SIS7, zona=Z)
assert Z[0] <= mc.xmin < Z[0] + mc.res and Z[2] - mc.res < mc.xmax <= Z[2] + 1e-9
assert Z[1] <= mc.ymin < Z[1] + mc.res and Z[3] - mc.res < mc.ymax <= Z[3] + 1e-9
ideal = textura(*np.meshgrid(mc.xmin + (np.arange(mc.ancho) + 0.5) * mc.res,
                             mc.ymax - (np.arange(mc.alto) + 0.5) * mc.res))
dy, dx = GE._fase(ideal.mean(-1), im.astype(float).mean(-1))
assert math.hypot(dx, dy) < 0.5 and not GE.mascara(im).any(), (dx, dy)
enlace.parar.set(); enlace.join(2); srv.detener()
print(f"ok mosaico de lo que veo en IngeCAD: 2 x 2 piezas, UNA imagen de exactamente "
      f"{mc.ancho * mc.res:.0f} x {mc.alto * mc.res:.0f} m de la zona, error {math.hypot(dx, dy):.2f} px")

# los programas: la pantalla de IngeCAD (vista del dibujo) y la zona en la ventanita
from render.view import ViewTransform2D
vista_dib = ViewTransform2D(cx=X0, cy=Y0, scale=2.0, width=800, height=600)
prog = GEC.Programa(types.SimpleNamespace(viewport=types.SimpleNamespace(view=vista_dib), document=None))
assert prog.zona() == (X0 - 200, Y0 - 150, X0 + 200, Y0 + 150)
assert GEC.Programa(types.SimpleNamespace()).zona() is None
class ProgZ:
    nombre = "ingecad"
    def __init__(self, z, crs): self.z, self.crs = z, crs
    def sistema(self): return (self.crs, "del dibujo") if self.crs else ("", "el dibujo no tiene sistema")
    def zona(self): return self.z
assert UI.zona_de(ProgZ(Z, SIS7), SIS7) == (Z, "300 x 200 m")
assert UI.zona_de(ProgZ(Z, ""), SIS7) == (Z, "300 x 200 m")       # sin sistema propio: el de la captura
assert UI.zona_de(ProgZ(Z, ""), "") == (None, "falta el sistema del dibujo")
assert UI.zona_de(ProgZ(None, SIS7), SIS7)[0] is None
assert UI.zona_de(ProgZ(Z, SIS7), "EPSG:5348")[0] == z6
con_zona = UI.requisitos(True, vv, SIS7, "del dibujo", "", "ingecad", (True, "Zona de IngeCAD: 300 x 200 m"))
assert len(con_zona) == 5 and all(ok for ok, _t in con_zona)
print("ok la zona de la pantalla de IngeCAD (y su sistema) en la ventanita")
print("TODO OK")
