"""Google Earth: los vuelos de la captura (3.33.3). Fernando, 21/10/2026:
«Google Earth no fue a la posición pedida» con Google Earth enlazado, una y
otra vez. Se pedía 0,2 m de precisión y un solo vuelo; si Google Earth se
tragaba el vuelo o devolvía la vista redondeada, la captura fallaba.

Un Google Earth de mentira habla con el servidor de verdad (como los
NetworkLink: /camara cada tanto y /vista al quedar quieto) y se porta mal a
propósito: se traga un vuelo, redondea, se corta, se inclina.

(Hecha el 21/10/2026 en la copia sin el disco; se suma a test_googleearth.)"""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, threading, time, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from urllib.parse import urlencode

import numpy as np

NUCLEO = Path(__file__).resolve().parents[1] / "nucleo"
paquete = types.ModuleType("nucleo_ge")
paquete.__path__ = [str(NUCLEO)]
sys.modules["nucleo_ge"] = paquete
from nucleo_ge import googleearth as GE          # noqa: E402
from nucleo_ge import googleearth_vivo as V      # noqa: E402

GE.detectar = lambda a, **_k: {}                 # sin cruces dibujadas: la foto se da por buena


class GEDeMentira:
    """``tragar`` vuelos que ignora; ``decimales`` con que devuelve la
    cámara; ``corrido`` grados que se corre; ``cortado`` deja de pedir
    /camara; ``inclinado`` tilt con que llega."""

    def __init__(self, srv, lon=-58.381234567, lat=-34.603456789, rango=705.0,
                 tragar=0, decimales=6, corrido=0.0, cortado=False, inclinado=0.0, inicial_tilt=0.0):
        self.srv, self.tragar, self.decimales = srv, tragar, decimales
        self.corrido, self.cortado, self.inclinado = corrido, cortado, inclinado
        self.vuelos = 0
        self.parar = threading.Event()
        self.mandar(lon, lat, rango, inicial_tilt)
        self.hilo = threading.Thread(target=self.andar, daemon=True)
        self.hilo.start()

    def mandar(self, lon, lat, rango, tilt=0.0):
        d = 0.004
        r = lambda v: round(v, self.decimales)  # noqa: E731
        q = {"BBOX": f"{r(lon - d)},{r(lat - d)},{r(lon + d)},{r(lat + d)}",
             "cam": f"{r(lon)},{r(lat)},{rango:.1f},{tilt},0", "px": "1200,800"}
        self.srv.atender("/vista?" + urlencode(q))

    def andar(self):
        while not self.parar.is_set():
            if not self.cortado:
                _tipo, cuerpo = self.srv.atender("/camara")
                texto = cuerpo.decode()
                if "<LookAt>" in texto:
                    self.vuelos += 1
                    if self.tragar > 0:
                        self.tragar -= 1
                    else:
                        lon = float(texto.split("<longitude>")[1].split("<")[0]) + self.corrido
                        lat = float(texto.split("<latitude>")[1].split("<")[0])
                        rango = float(texto.split("<range>")[1].split("<")[0])
                        time.sleep(0.05)
                        self.mandar(lon, lat, rango, self.inclinado)
            time.sleep(0.02)

    def fin(self):
        self.parar.set()
        self.hilo.join(1)


def captura(srv):
    return V.Captura(srv, lambda: np.zeros((8, 8, 3), np.uint8), paso=0.02, quietas=2,
                     tope_quieta=2.0, tope_vuelo=1.5, reintento=0.4)


def servidor(marcas_siempre=False):
    srv = V.Servidor(puerto=0, marcas_siempre=marcas_siempre)
    srv.atender("/camara")                       # enlazado
    return srv


# --- llego: tolerancia razonable, vertical
v = GE.Vista(0, 0, 1, 1, -58.38123, -34.60346, 705.0)
assert GE.llego(v, -58.381234567, -34.603456789, 705.0)          # redondeado a 5 decimales: ~0,6 m
assert not GE.llego(v, -58.3820, -34.60346, 705.0)                # 70 m: no
assert not GE.llego(v, -58.38123, -34.60346, 760.0)               # otra altura: no
assert not GE.llego(GE.Vista(0, 0, 1, 1, -58.38123, -34.60346, 705.0, inclinacion=30),
                    -58.38123, -34.60346, 705.0)                  # inclinado: no
assert abs(GE.distancia_m(-58.0, -34.0, -58.0, -34.001) - 111.3) < 0.1
print("ok llego: 1 % de la altura (mín. 1 m), 2 % de altura, mirando hacia abajo")

# --- un vuelo tragado: se vuelve a pedir y llega
srv = servidor()
ge = GEDeMentira(srv, tragar=1)
c = captura(srv)
c._ir(-58.38, -34.60, 200.0)
assert ge.vuelos >= 2, ge.vuelos
ge.fin()
print(f"ok un vuelo tragado: se pide de nuevo ({ge.vuelos} vuelos) y llega")

# --- la vista vuelve redondeada y algo corrida: igual llegó
srv = servidor()
ge = GEDeMentira(srv, decimales=5, corrido=5e-6)
captura(srv)._ir(-58.381234567, -34.603456789, 705.0)
ge.fin()
print("ok vista redondeada a 5 decimales y corrida medio metro: llegó")

# --- Pantalla con las cruces siempre y la vista derecha: sin vuelo
srv = servidor(marcas_siempre=True)
ge = GEDeMentira(srv)
time.sleep(0.1)
fotos = captura(srv).pantalla()
assert ge.vuelos == 0, ge.vuelos
assert len(fotos) == 1 and len(fotos[0][1]) == 4
ge.fin()
print("ok Pantalla con cruces siempre y vista derecha: foto sin volar")

# --- Pantalla con la vista inclinada: se endereza volando
srv = servidor(marcas_siempre=True)
ge = GEDeMentira(srv, inicial_tilt=35.0)
time.sleep(0.1)
fotos = captura(srv).pantalla()
assert ge.vuelos >= 1 and srv.vista.vertical
ge.fin()
print("ok Pantalla con la vista inclinada: se endereza y saca la foto")

# --- Pantalla sin cruces siempre: vuela (para poner las cruces) y las quita
srv = servidor(marcas_siempre=False)
ge = GEDeMentira(srv, tragar=1)
time.sleep(0.1)
fotos = captura(srv).pantalla()
assert ge.vuelos >= 2 and len(fotos[0][1]) == 4
time.sleep(0.2)
assert srv.armado is False
ge.fin()
print("ok Pantalla sin cruces siempre: vuela, reintenta si hace falta, saca la foto")

# --- Mosaico: cada pieza vuela (alguna tragada) y la vista vuelve
for altura_vista, rango_pieza in ((705.0, 200.0), (150.0, 200.0)):
    srv = servidor()
    ge = GEDeMentira(srv, rango=altura_vista, tragar=1)
    time.sleep(0.1)
    c = captura(srv)
    crs = GE.sistema_sugerido(srv.vista.lon, srv.vista.lat)
    a_planas, a_geo = GE.transformadores(crs)
    piezas = c.mosaico(a_planas, a_geo, rango_pieza)
    plan = GE.plan_mosaico(c.original, a_planas, a_geo, rango_pieza)
    assert len(piezas) == len(plan.centros) and all(len(m) == 4 for _a, m, _f, _c in piezas)
    assert abs(srv.vista.rango - altura_vista) <= altura_vista * 0.02     # volvió
    ge.fin()
    print(f"ok Mosaico desde {altura_vista:g} m con piezas a {rango_pieza:g} m: "
          f"{len(piezas)} pieza(s), {ge.vuelos} vuelos, la vista volvió")

# --- Mosaico muy alto: en vez de «Harían falta 180 piezas», sube la altura de las piezas
lon0, lat0 = -54.8021745, -27.0953292                        # la prueba de Fernando, 21/10/2026
a_planas, a_geo = GE.transformadores("EPSG:5349")
d = 0.012
alta = GE.Vista(lon0 - d * 1.9, lat0 - d, lon0 + d * 1.9, lat0 + d, lon0, lat0, 2297.0)
try:
    GE.plan_mosaico(alta, a_planas, a_geo, 200.0, ajustar=False)
    raise AssertionError("con 200 m debía pasar el tope")
except GE.DemasiadasPiezas:
    pass
p = GE.plan_mosaico(alta, a_planas, a_geo, 200.0)
assert len(p.centros) <= GE.TOPE_PIEZAS and 200 < p.rango < 2297 and p.pedida == 200, p
zona = (7417000.0, 7001000.0, 7421000.0, 7004000.0)          # 4 x 3 km de IngeCAD
pz = GE.plan_mosaico(alta, a_planas, a_geo, 200.0, zona=zona)
assert len(pz.centros) <= GE.TOPE_PIEZAS and pz.rango > 200, pz
print(f"ok Mosaico a 2297 m: piezas a {p.rango:g} m ({len(p.centros)}); "
      f"zona de 4 x 3 km: a {pz.rango:g} m ({len(pz.centros)})")

# --- Mosaico con una pieza que no sale nunca: sigue, la repite al final y entrega lo que hay
class GEQueFallaUna(GEDeMentira):
    """Nunca manda la vista de la pieza ``mala`` (la n-ésima posición pedida distinta)."""
    def __init__(self, srv, mala, **kw):
        self.mala, self.lugares = mala, []
        super().__init__(srv, **kw)

    def mandar(self, lon, lat, rango, tilt=0.0):
        if getattr(self, "lugares", None) is not None and self.vuelos:
            clave = (round(lon, 5), round(lat, 5))
            if clave not in self.lugares:
                self.lugares.append(clave)
            if self.lugares.index(clave) == self.mala:
                return
        super().mandar(lon, lat, rango, tilt)

srv = servidor()
ge = GEQueFallaUna(srv, mala=2, rango=359.0)
time.sleep(0.1)
c = captura(srv)
crs = GE.sistema_sugerido(srv.vista.lon, srv.vista.lat)
a_planas, a_geo = GE.transformadores(crs)
piezas = c.mosaico(a_planas, a_geo, 200.0)
total = len(c.plan.centros)
assert total == 9 and len(piezas) == 8 and len(c.faltan) == 1, (total, len(piezas), c.faltan)
ge.fin()
print(f"ok Mosaico con una pieza imposible: entrega {len(piezas)} de {total} y avisa {c.faltan}")

# el mosaico incompleto abarca todo y deja el hueco en blanco (no se achica)
assert "huecos" in GE.componer.__code__.co_varnames and hasattr(GE, "marco_todo")
assert "completo=not cap.faltan" in (NUCLEO / "googleearth_ui.py").read_text(encoding="utf-8")
print("ok mosaico incompleto: marco de todas las piezas y huecos en blanco")

# --- los motivos, cada uno con su texto
srv = servidor()
ge = GEDeMentira(srv, tragar=99)
try:
    captura(srv)._ir(-58.38, -34.60, 200.0)
    raise AssertionError("debía fallar")
except GE.GoogleEarthError as exc:
    assert "no respondió" in str(exc), exc
ge.fin()
srv = servidor()
ge = GEDeMentira(srv, inclinado=40.0)
try:
    captura(srv)._ir(-58.38, -34.60, 200.0)
    raise AssertionError("debía fallar")
except GE.GoogleEarthError as exc:
    assert "inclinado" in str(exc), exc
ge.fin()
srv = servidor()
ge = GEDeMentira(srv, corrido=0.01)
try:
    captura(srv)._ir(-58.38, -34.60, 200.0)
    raise AssertionError("debía fallar")
except GE.GoogleEarthError as exc:
    assert "quedó a" in str(exc), exc
ge.fin()
srv = servidor()
ge = GEDeMentira(srv, cortado=True)
srv.t_camara = 0.0                               # Google Earth dejó de pedir /camara
try:
    captura(srv)._ir(-58.38, -34.60, 200.0)
    raise AssertionError("debía fallar")
except GE.GoogleEarthError as exc:
    assert "Se cortó el enlace" in str(exc), exc
ge.fin()
print("ok los errores dicen qué pasó: no respondió / inclinado / quedó corrido / enlace cortado")

# --- en vez de un error, la captura empieza de nuevo sola (Fernando, 21/10/2026)
srv = servidor(marcas_siempre=False)
ge = GEDeMentira(srv, tragar=5)                  # el primer ciclo entero falla (1,5 s sin respuesta)
time.sleep(0.1)
c = captura(srv)
avisos = []
fotos = V.con_reintentos(lambda k: c.pantalla(volar=k > 1), lambda t, f=None: avisos.append(t), c.cancelar)
assert len(fotos) == 1 and any("intento 2 de 3" in t for t in avisos), avisos
ge.fin()
srv = servidor()
ge = GEDeMentira(srv, cortado=True)
srv.t_camara = 0.0
n = []
try:
    V.con_reintentos(lambda k: (n.append(k), captura(srv)._ir(-58.38, -34.60, 200.0)))
    raise AssertionError("debía fallar")
except V.Reintentable:
    raise AssertionError("sin enlace no se repite")
except GE.GoogleEarthError as exc:
    assert n == [1] and "Se cortó el enlace" in str(exc), (n, exc)
ge.fin()
n = []
try:
    V.con_reintentos(lambda k: (n.append(k), (_ for _ in ()).throw(V.Reintentable("x"))))
except GE.GoogleEarthError as exc:
    assert n == [1, 2, 3] and "3 intentos" in str(exc), (n, exc)
print("ok falla -> empieza de nuevo (hasta 3); sin enlace avisa en el acto")

# --- la fecha: la que tiene puesta Google Earth en ese momento (Fernando, 21/10/2026)
# Google Earth Pro no manda [timeBegin],[timeEnd] (probado con Fernando): no se pide
assert "timeBegin" not in GE.kml_enlaces(48765).decode()
assert GE.fecha_de_ge("[timeBegin],[timeEnd]") == ""                 # no la manda: nada
assert GE.fecha_de_ge("2023-07-09T00:00:00Z,2023-07-09T23:59:59Z") == "9/7/2023"
assert GE.fecha_de_ge("2019-05,") == "5/2019" and GE.fecha_de_ge("2015,2016") == "2016"
srv = servidor()
srv.atender("/vista?" + urlencode({"BBOX": "-55,-27.1,-54.9,-27", "cam": "-54.95,-27.05,700,0,0",
                                   "px": "10,10", "t": "2021-03-04T00:00:00Z,"}))
assert srv.vista.fecha == "4/3/2021" and srv.t_crudo.startswith("2021-03-04"), (srv.vista, srv.t_crudo)
assert "kml_lookat" in dir(GE) and "TimeStamp" not in GE.kml_lookat(-55, -27, 700).decode()  # no la cambia
UIF = (NUCLEO / "googleearth_ui.py").read_text(encoding="utf-8")
assert '"fecha": self.fecha.text()' not in UIF and 'self.fecha.setText(self.aj["fecha"])' not in UIF
print("ok fecha: la de Google Earth en ese momento; la escrita vale para una captura; no se toca la línea de tiempo")

# --- el nombre: fecha y hora, lugar en coordenadas, fecha de la imagen; sólo ASCII
t = time.mktime((2026, 10, 21, 9, 35, 12, 0, 0, -1))
n = GE.nombre_archivo("9/7/2023", "png", t, lon=-54.888677, lat=-27.096328)
assert n == "GE_20261021-093512_S27.09633_W54.88868_img-9-7-2023.png", n
assert GE.nombre_archivo("", "tif", t, lon=2.35, lat=48.85) == "GE_20261021-093512_N48.85000_E2.35000.tif"
assert GE.nombre_archivo("año ñandú", "jpg", t) == "GE_20261021-093512_img-a-o-and.jpg"
for x in (n, GE.nombre_archivo("mayo/2024: ¿?", "png", t, -58.4, -34.6)):
    assert x.isascii() and not set(x) & set(' <>:"/\\|?*'), x
print("ok nombre: GE_fecha-hora_coordenadas_img-fecha, sólo ASCII")

# --- la ventanita: al cerrarla el servidor sigue (no hay que reabrir Google Earth)
UI = (NUCLEO / "googleearth_ui.py").read_text(encoding="utf-8")
cierre = UI.split("def closeEvent")[1].split("def apagar")[0]
assert "if self._apagando:" in cierre and "self.srv.detener()" in cierre.split("if self._apagando:")[1]
assert "v.apagar()" in UI.split("def cerrar")[1].split("def abrir")[0]
assert "v.reanudar()" in UI.split("def abrir(")[1].split("def _Ventanita")[0]
assert "V.con_reintentos(ciclo" in UI
assert "if self.srv.conectado():" in UI.split("def abrir_google_earth")[1].split("def llevar")[0]
print("ok ventanita: cerrarla no corta el enlace; apagar el módulo sí; no se duplica el enlace")

# --- vista previa (idea de Fernando) y registro de los vuelos
assert "_mostrar_previa" in UI and "self.previa.setFixedHeight(180)" in UI
assert "_sacar_previas" in UI and "self._detener_previa()" in UI   # en otro hilo, ~4 por segundo
assert hasattr(V.FotoX11, "previa")
reg = V.archivo_registro()
assert reg.exists() and "volar pedido" in reg.read_text(encoding="utf-8") \
    and "/camara entrega el vuelo" in reg.read_text(encoding="utf-8")
print("ok vista previa en la ventanita y registro de vuelos en", reg.name)

# --- los dos lados con el mismo núcleo
raiz = NUCLEO.parents[1]
for f in ("googleearth.py", "googleearth_vivo.py", "googleearth_ui.py"):
    for lado in ("INGECAD", "QGIS"):
        assert (raiz / lado / "codigo" / "geocad" / f).read_bytes() == (NUCLEO / f).read_bytes(), (lado, f)
print("ok núcleo igual en IngeCAD y QGIS")
print("TODO OK GOOGLE EARTH VUELO")
