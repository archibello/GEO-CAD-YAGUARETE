"""Google Earth: los vuelos de la captura (3.33.3, 3.33.4 y 3.33.6).

3.33.3 (Fernando, 21/10/2026): «la captura funciona el 50 % de las veces»,
«Mosaico falló todas las veces», «en vez de dar tantos mensajes de error
debería empezar el ciclo de una nueva captura», «ni siquiera entregó un
resultado parcial».

3.33.4: el registro de vuelos mostró la causa: Google Earth se lleva el vuelo
por /camara pero NUNCA vuelve a mandar /vista después (1069 vuelos, ninguna
vista nueva). Ahora las cruces de cada pieza viajan con el vuelo por /camara y
la pieza está lista cuando la foto se aquieta con las cuatro cruces en su
forma. Y la ventanita: video de la vista 3D y barra de fotogramas.

El Google Earth de mentira se porta como el de verdad: /vista sólo al
empezar; /camara cada 20 ms; a veces está ocupado y no pide /camara, o se
corta.

(Hecha el 21/10/2026; se suma a test_googleearth.)"""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, threading, time, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from urllib.parse import urlencode
import re

import numpy as np

UI_TXT = (Path(__file__).resolve().parents[1] / "nucleo" / "googleearth_ui.py").read_text(encoding="utf-8")

NUCLEO = Path(__file__).resolve().parents[1] / "nucleo"
paquete = types.ModuleType("nucleo_ge")
paquete.__path__ = [str(NUCLEO)]
sys.modules["nucleo_ge"] = paquete
from nucleo_ge import googleearth as GE          # noqa: E402
from nucleo_ge import googleearth_vivo as V      # noqa: E402
from nucleo_ge import googleearth_ui as UIM      # noqa: E402

LON0, LAT0 = -54.6119450, -27.0136788            # la prueba de Fernando, 21/10/2026


class GEDeMentira:
    """``ocupado``: vuelos que no se lleva enseguida (no pide /camara un
    rato); ``malas``: lugares donde las cruces nunca se ven (tapadas);
    ``cortado``: deja de pedir /camara."""

    def __init__(self, srv, rango=828.0, ocupado=0, malas=(), cortado=False, tilt=0.0, lento=0.0):
        self.srv, self.ocupado, self.malas, self.cortado = srv, ocupado, list(malas), cortado
        self.lento = lento                        # segundos que tarda en arrancar cada vuelo
        self.despues = None                       # (cuándo, cámara, cruces) que todavía no aplicó
        self.cam = [LON0, LAT0, rango]
        self.cruces = []
        self.vuelos = 0
        self.parar = threading.Event()
        d = 0.004 * rango / 828
        q = {"BBOX": f"{LON0 - 1.9 * d},{LAT0 - d},{LON0 + 1.9 * d},{LAT0 + d}",
             "cam": f"{LON0},{LAT0},{rango},{tilt},0", "px": "3432,1846"}
        srv.atender("/vista?" + urlencode(q))     # la única /vista: el usuario la movió
        self.hilo = threading.Thread(target=self.andar, daemon=True)
        self.hilo.start()

    def andar(self):
        while not self.parar.is_set():
            if self.cortado:
                time.sleep(0.02)
                continue
            if self.ocupado > 0 and self.srv.pendiente is not None:
                self.ocupado -= 1                 # cargando: no pide /camara por un rato
                time.sleep(0.3)
                continue
            texto = self.srv.atender("/camara")[1].decode()
            assert "<Placemark>" not in texto, "cruces en el enlace con flyToView"
            cruces = self.srv.atender("/cruces")[1].decode()
            cruces = [(float(a), float(b)) for a, b in
                      re.findall(r"<coordinates>([-\d.]+),([-\d.]+),0", cruces)]
            if "<LookAt>" in texto:
                self.vuelos += 1
                cam = [float(texto.split("<longitude>")[1].split("<")[0]),
                       float(texto.split("<latitude>")[1].split("<")[0]),
                       float(texto.split("<range>")[1].split("<")[0])]
                # el lento sigue mostrando la vista y las cruces de antes un rato
                self.despues = (time.time() + self.lento, cam, cruces)
            if self.despues is not None:
                if time.time() >= self.despues[0]:
                    self.cam, self.cruces = self.despues[1], cruces
                    self.despues = None
            else:
                self.cruces = cruces
            time.sleep(0.02)

    @staticmethod
    def valor(cam):
        return int(abs(cam[0] * 1e5 + cam[1] * 1e4 + cam[2])) % 200

    def foto(self):
        """Una imagen que cambia con la cámara y queda quieta al llegar."""
        return np.full((8, 8, 3), self.valor(self.cam), np.uint8)

    def detectar(self, _a, **_k):
        """Las cruces que se ven: las de /camara, si están en la pantalla."""
        if len(self.cruces) != 4:
            raise GE.GoogleEarthError("No se ve la cruz de control.")
        for lon, lat in self.malas:
            if abs(self.cam[0] - lon) < 1e-6 and abs(self.cam[1] - lat) < 1e-6:
                raise GE.GoogleEarthError("No se ve la cruz de control arriba a la izquierda.")
        (o, s), (e, _s2), (_e2, n), _no = self.cruces       # SO, SE, NE, NO
        an = GE.distancia_m(o, s, e, s)
        al = GE.distancia_m(o, s, o, n)
        return {"NO": (10, 10), "NE": (10 + an, 10), "SO": (10, 10 + al), "SE": (10 + an, 10 + al),
                "largo": 9}

    def fin(self):
        self.parar.set()
        self.hilo.join(1)


def servidor(marcas_siempre=False):
    srv = V.Servidor(puerto=0, marcas_siempre=marcas_siempre)
    srv.atender("/camara")                       # enlazado
    return srv


def captura(srv, ge, aviso=None):
    GE.detectar = ge.detectar
    return V.Captura(srv, ge.foto, aviso=aviso, paso=0.02, quietas=2, tope_quieta=1.0,
                     tope_vuelo=1.0)


# --- /camara lleva el vuelo y las cruces; /vista nunca lleva cruces
srv = servidor()
consulta = "/vista?" + urlencode({"BBOX": "-55,-27.1,-54.9,-27", "cam": "-54.95,-27.05,700,0,0",
                                  "px": "10,10"})
srv.atender(consulta)
srv.armado = True
assert b"<Placemark>" not in srv.atender(consulta)[1]
srv.cruces = GE.marcas_de_bbox(-55, -27.1, -54.9, -27)
srv.volar(-54.95, -27.05, 200)
k = srv.atender("/camara")[1].decode()
assert "<LookAt>" in k and "<Placemark>" not in k and srv.t_entregado > 0
assert "<LookAt>" not in srv.atender("/camara")[1].decode()        # el vuelo, una vez
k = srv.atender("/cruces")[1].decode()
assert k.count("<Placemark>") == 4 and "<LookAt>" not in k             # las cruces, cada vez
assert srv.atender("/cruces")[1].decode().count("<Placemark>") == 4
srv.cruces, srv.armado = None, False
assert "<Placemark>" not in srv.atender("/cruces")[1].decode()
srv.marcas_siempre = True
assert srv.atender("/cruces")[1].decode().count("<Placemark>") == 4
assert "<Placemark>" not in srv.atender("/camara")[1].decode()      # nunca con flyToView
enl = GE.kml_enlaces(48765).decode()
cr = enl.split("<name>Cruces (GeoCAD)</name>")[1].split("</NetworkLink>")[0]
assert "<flyToView>0</flyToView>" in cr and "/cruces" in cr
viejo = V.Servidor(puerto=0)
viejo.atender("/camara")
assert viejo.enlace_viejo()                    # el enlace de antes (sin /cruces): hay que cambiarlo
viejo.atender("/cruces")
assert not viejo.enlace_viejo()
print("ok enlaces: /camara sólo el vuelo; /cruces sólo las cruces (sin flyToView); enlace viejo avisado")

# --- forma de las cruces: si la cámara no llegó, no coincide
m = GE.marcas_de_bbox(-55, -27.1, -54.9, -27)
an, al = GE.distancia_m(-55, -27.1, -54.9, -27.1), GE.distancia_m(-55, -27.1, -55, -27)
bien = {"NO": (0, 0), "NE": (an, 0), "SO": (0, al), "SE": (an, al)}
mal = {"NO": (0, 0), "NE": (an * 0.6, 0), "SO": (0, al), "SE": (an * 0.6, al)}
assert GE.forma_coincide(bien, m) and not GE.forma_coincide(mal, m)
print("ok forma de las cruces: la de la pieza o todavía no llegó")

# --- vista inclinada: se estima la vertical; BBOX de cada pieza a escala
v = GE.Vista(-55, -27.1, -54.9, -27, -54.95, -27.05, 700, inclinacion=40, ancho_px=3432, alto_px=1846)
vv = GE.vista_vertical(v)
forma = (vv.este - vv.oeste) * 111320 * np.cos(np.radians(-27.05)) / ((vv.norte - vv.sur) * 110574)
assert vv.vertical and abs(forma - 3432 / 1846) < 0.01, forma
b = GE.bbox_en(GE.Vista(-55, -27.1, -54.9, -27, -54.95, -27.05, 800), -54.9, -27.0, 200)
assert abs((b[2] - b[0]) - 0.1 * 200 / 800) < 1e-12
print("ok vista vertical estimada y BBOX de cada pieza a escala")

# --- Pantalla: cruces sin mover la cámara; sin ninguna /vista nueva
srv = servidor()
ge = GEDeMentira(srv)
c = captura(srv, ge)
fotos = c.pantalla()
assert len(fotos) == 1 and ge.vuelos == 0 and c.estados == ["ok"]
time.sleep(0.1)
assert ge.cruces == [] and srv.cruces is None                     # las cruces se fueron
ge.fin()
print("ok Pantalla: cruces por /cruces, sin vuelo, sin esperar /vista")

# --- Pantalla con la vista inclinada: se endereza volando
srv = servidor()
ge = GEDeMentira(srv, tilt=35.0)
fotos = captura(srv, ge).pantalla()
assert ge.vuelos == 1 and len(fotos) == 1
ge.fin()
print("ok Pantalla inclinada: un vuelo para enderezar y la foto")

# --- Mosaico: 25 piezas, Google Earth nunca manda /vista y a veces está ocupado
crs = GE.sistema_sugerido(LON0, LAT0)
a_planas, a_geo = GE.transformadores(crs)
srv = servidor()
ge = GEDeMentira(srv, ocupado=3)
c = captura(srv, ge)
t0 = time.time()
piezas = c.mosaico(a_planas, a_geo, 200.0)
dt = time.time() - t0
assert len(piezas) == len(c.plan.centros) == 25 and not c.faltan and c.estados == ["ok"] * 25
assert len(c.tiempos) == 25 and not c.lento                         # 3.33.6: vuela rápido
assert all(len(m) == 4 for _a, m, _f, _c in piezas)
time.sleep(0.1)
assert abs(ge.cam[2] - 828) < 0.01 and srv.cruces is None          # la vista volvió, sin cruces
ge.fin()
print(f"ok Mosaico de 25 piezas a {c.plan.rango:g} m sin ninguna /vista nueva, en {dt:.1f} s "
      "(con Google Earth ocupado a ratos)")

# --- Mosaico con una pieza imposible: las demás salen, ésa queda en rojo
srv = servidor()
ge0 = GEDeMentira(srv)
plan = GE.plan_mosaico(srv.vista, a_planas, a_geo, 200.0)
ge0.fin()
mala = plan.centros[7]
srv = servidor()
ge = GEDeMentira(srv, malas=[(mala[2], mala[3])])
c = captura(srv, ge)
piezas = c.mosaico(a_planas, a_geo, 200.0)
assert len(piezas) == 24 and c.faltan == [(mala[0], mala[1])] and c.estados[7] == "falla", c.estados
assert c.estados.count("ok") == 24
ge.fin()
print(f"ok Mosaico con una pieza imposible: 24 de 25 y la 8 en rojo ({UIM.resumen_fotogramas(c.estados)})")

# --- Google Earth lento (tarda en arrancar cada vuelo, como el de Fernando): ninguna
#     pieza sale con la imagen y las cruces de la anterior (barrios repetidos)
srv = servidor()
ge = GEDeMentira(srv, lento=0.25)
avisos = []
c = captura(srv, ge, aviso=lambda t, _f=None: avisos.append(t))
c.tope_quieta = 3.0
LENTO = V.LENTO
V.LENTO = 0.2                                     # a escala: cada pieza tarda más de 0,25 s
piezas = c.mosaico(a_planas, a_geo, 200.0)
lento_mosaico = c.lento
V.LENTO = LENTO
assert len(piezas) == 25 and not c.faltan
for (a, m, fila, col), (f2, c2, lon, lat) in zip(piezas, c.plan.centros):
    assert (fila, col) == (f2, c2)
    assert a[0, 0, 0] == GEDeMentira.valor([lon, lat, c.plan.rango]), (fila, col)   # su lugar
ge.fin()
print("ok Google Earth lento: cada pieza con su propia imagen (se espera a que se mueva)")

# --- 3.33.6: Google Earth vuela lento (Velocidad de vuelo de fábrica, 0,18):
#     se avisa durante el mosaico y al terminar (GeoCAD no la puede cambiar)
assert lento_mosaico and len(c.tiempos) == 25
assert any("vuela lento" in t for t in avisos) and not any("vuela lento" in t for t in avisos[:3])
assert "Velocidad de vuelo en 5" in V.AVISO_LENTO
c2 = V.Captura(srv, ge.foto)
c2.tiempos = [9.2, 8.8, 9.1]                      # la prueba de Fernando con 5 (23/10/2026)
assert not c2.lento
c2.tiempos = [45.0, 44.1, 9.0]                    # con 0,18
assert c2.lento
c2.tiempos = [45.0]                               # una sola pieza no alcanza para decir
assert not c2.lento
assert "lento=cap.lento" in UI_TXT and "V.AVISO_LENTO" in UI_TXT
print("ok vuela lento: aviso con la Velocidad de vuelo (mediana de las piezas)")

# --- 3.33.6: el candado de Google Earth que queda de un cierre de golpe
#     («Another instance of this application is already running»)
carpeta = Path(tempfile.mkdtemp())
cand = carpeta / "instance-running-lock"
os.symlink("/proc/5", cand)
viejo = time.time() - 600
os.utime(cand, (viejo, viejo), follow_symlinks=False)
assert not GE.soltar_candado(True, ruta=cand) and os.path.lexists(cand)        # abierto: no
assert GE.soltar_candado(False, ruta=cand) and not os.path.lexists(cand)       # colgado: se borra
os.symlink("/proc/5", cand)                                                     # recién puesto:
assert not GE.soltar_candado(False, ruta=cand) and os.path.lexists(cand)       # está arrancando
assert not GE.soltar_candado(False, ruta=carpeta / "no-hay")
assert GE.candado() == Path.home() / ".googleearth" / "instance-running-lock"
abrir = UI_TXT.split("def abrir_google_earth")[1].split("def llevar")[0]
assert "GE.soltar_candado(foto.ventana(visible=False) is not None)" in abrir
assert abrir.index("soltar_candado") < abrir.index("openUrl")
print("ok candado colgado: se borra sólo sin Google Earth abierto y si no es nuevo")

# --- enlace cortado: avisa en el acto, sin dar vueltas
srv = servidor()
ge = GEDeMentira(srv, cortado=True)
srv.t_camara = 0.0
try:
    captura(srv, ge).pantalla()
    raise AssertionError("debía fallar")
except V.Reintentable:
    raise AssertionError("sin enlace no se repite")
except GE.GoogleEarthError as exc:
    assert "Se cortó el enlace" in str(exc), exc
ge.fin()
print("ok enlace cortado: avisa en el acto")

# --- falla -> la captura empieza de nuevo sola (hasta 3)
n = []
try:
    V.con_reintentos(lambda k: (n.append(k), (_ for _ in ()).throw(V.Reintentable("x"))))
except GE.GoogleEarthError as exc:
    assert n == [1, 2, 3] and "3 intentos" in str(exc), (n, exc)
print("ok falla -> empieza de nuevo (hasta 3)")

# --- el tope: la altura de las piezas sube sola
alta = GE.Vista(LON0 - 0.03, LAT0 - 0.012, LON0 + 0.03, LAT0 + 0.012, LON0, LAT0, 2767.0)
try:
    GE.plan_mosaico(alta, a_planas, a_geo, 200.0, ajustar=False)
    raise AssertionError("con 200 m debía pasar el tope")
except GE.DemasiadasPiezas:
    pass
p = GE.plan_mosaico(alta, a_planas, a_geo, 200.0)
assert len(p.centros) <= GE.TOPE_PIEZAS and p.rango > 200 and p.pedida == 200
print(f"ok tope: a 2767 m las piezas suben a {p.rango:g} m")

# --- nombres: fecha y hora, coordenadas, fecha de la imagen; sólo ASCII
t = time.mktime((2026, 10, 21, 9, 35, 12, 0, 0, -1))
n = GE.nombre_archivo("9/7/2023", "png", t, lon=-54.888677, lat=-27.096328)
assert n == "GE_20261021-093512_S27.09633_W54.88868_img-9-7-2023.png", n
assert GE.nombre_archivo("año ñandú", "jpg", t) == "GE_20261021-093512_img-a-o-and.jpg"
print("ok nombres: GE_fecha-hora_coordenadas_img-fecha, sólo ASCII")

# --- la ventanita: video, fotogramas, enlace que sigue al cerrarla
UI = (NUCLEO / "googleearth_ui.py").read_text(encoding="utf-8")
assert "V.VideoX11()" in UI and "self.reloj_video.start(40)" in UI      # ~25 cuadros por segundo
assert "QScrollArea" in UI and "self.fotogramas.poner(cap.estados)" in UI
assert UIM.resumen_fotogramas(["ok", "falla", "actual", ""]) == "1 de 4 listos · 1 a repetir"
assert UIM.COLOR_FOTOGRAMA["ok"] and UIM.COLOR_FOTOGRAMA["falla"] and UIM.COLOR_FOTOGRAMA[""] is None
cierre = UI.split("def closeEvent")[1].split("def apagar")[0]
assert "if self._apagando:" in cierre and "self._detener_previa()" in cierre
assert "if self.srv.conectado() and not self.srv.enlace_viejo():" in UI.split("def abrir_google_earth")[1].split("def llevar")[0]
assert hasattr(V.VideoX11, "cuadro") and hasattr(V.VideoX11, "_vista3d")
print("ok ventanita: video de la vista 3D, barra de fotogramas, parte desplazable")

# --- registro de los vuelos
reg = V.archivo_registro()
assert reg.exists() and "entrega el vuelo" in reg.read_text(encoding="utf-8")
print("ok registro de vuelos en", reg.name)

# --- los dos lados con el mismo núcleo
raiz = NUCLEO.parents[1]
for f in ("googleearth.py", "googleearth_vivo.py", "googleearth_ui.py"):
    for lado in ("INGECAD", "QGIS"):
        assert (raiz / lado / "codigo" / "geocad" / f).read_bytes() == (NUCLEO / f).read_bytes(), (lado, f)
print("ok núcleo igual en IngeCAD y QGIS")
print("TODO OK GOOGLE EARTH VUELO")
