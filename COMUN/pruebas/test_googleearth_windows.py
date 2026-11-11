"""Google Earth en Windows: la foto, el video de la ventanita y Ctrl+Alt+G.

Fernando, 11/11/2026: «los usuarios de Windows son la mayoría», y la captura
sólo andaba en Linux (X11). FotoWin, VideoWin y AtajoWin hacen lo mismo con la
API de Win32 (ctypes). Acá Windows es de mentira: user32, gdi32 y kernel32
simulados, con una pantalla de numpy; cada llamada se controla contra las
firmas (argtypes) que GeoCAD declara, como lo haría ctypes en Windows. Corre
igual en Linux y en Windows. La prueba con el Google Earth real de Windows
queda en 02_PRUEBAS_MANUALES.txt."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import ctypes, json, os, sys, tempfile, threading, time, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from urllib.request import urlopen

import numpy as np

NUCLEO = Path(__file__).resolve().parents[1] / "nucleo"
paquete = types.ModuleType("nucleo_gew")
paquete.__path__ = [str(NUCLEO)]
sys.modules["nucleo_gew"] = paquete
from nucleo_gew import googleearth as GE          # noqa: E402
from nucleo_gew import googleearth_vivo as V      # noqa: E402

UI = (NUCLEO / "googleearth_ui.py").read_text(encoding="utf-8")


# ------------------------------------------------- 1. las firmas que declara GeoCAD
class _Funcion:
    def __init__(self):
        self.restype, self.argtypes = None, None


class _Dll:
    def __init__(self, nombre, **_kw):
        self.nombre, self.funciones = nombre, {}

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return self.funciones.setdefault(n, _Funcion())


dlls = {}
plat, sin_windll = sys.platform, not hasattr(ctypes, "WinDLL")
sys.platform = "win32"
ctypes.WinDLL = lambda nombre, **kw: dlls.setdefault(nombre, _Dll(nombre))
viejo_gle = getattr(ctypes, "get_last_error", None)
ctypes.get_last_error = lambda: 0
try:
    V._W["api"] = None
    assert V._win32() is not None
finally:
    sys.platform = plat
    if sin_windll:
        del ctypes.WinDLL
    if viejo_gle is None:
        del ctypes.get_last_error
FIRMAS = {d: {n: f.argtypes for n, f in dll.funciones.items()} for d, dll in dlls.items()}
assert set(FIRMAS) == {"user32", "gdi32", "kernel32"}
assert all(a is not None for f in FIRMAS.values() for a in f.values())
V._W["api"] = None
assert V._win32() is None or sys.platform == "win32"      # en Linux: no es Windows
print("ok firmas de Win32:", sum(len(f) for f in FIRMAS.values()), "funciones")


# ------------------------------------------------- 2. un Windows de mentira
class Ventana:
    def __init__(self, h, exe, titulo, x, y, ancho, alto, padre=None, visible=True):
        self.h, self.exe, self.titulo = h, exe, titulo
        self.x, self.y, self.ancho, self.alto = x, y, ancho, alto     # en pantalla
        self.padre, self.hijas, self.visible, self.minimizada = padre, [], visible, False


class Windows:
    """Ventanas, pantalla (BGRX), DC y mapas de bits."""

    def __init__(self):
        self.ventanas = {}
        self.pantalla = np.zeros((900, 1400, 4), np.uint8)
        self.contenido = {}            # lo que PrintWindow dibuja de cada ventana
        self.negra_3d = False          # PrintWindow no ve la vista 3D (OpenGL)
        self.bitmaps, self.dc, self.sueltos = {}, {}, set()
        self.proximo = 1000
        self.atajos, self.cola, self.error = {}, [], 0
        self.llamadas = []
        self.sin_permiso = set()       # procesos que no se dejan leer (OpenProcess falla)
        self.dpi = set()               # hilos en píxeles reales

    def nuevo(self):
        self.proximo += 1
        return self.proximo

    def ventana(self, *a, **kw):
        v = Ventana(*a, **kw)
        self.ventanas[v.h] = v
        if v.padre is not None:
            self.ventanas[v.padre].hijas.append(v.h)
        return v

    def raiz(self, h):
        while self.ventanas[h].padre is not None:
            h = self.ventanas[h].padre
        return h


W = Windows()


def _obj(p):
    return getattr(p, "_obj", p)


def _hacer(dll, nombre, f):
    tipos = FIRMAS[dll][nombre]

    def llamar(*args):
        assert len(args) == len(tipos), (nombre, len(args), len(tipos))
        for a, t in zip(args, tipos):
            t.from_param(a)                         # lo que hace ctypes en Windows
        W.llamadas.append(nombre)
        return f(*args)
    return llamar


def _escribir_bitmap(mem, img):
    bmp = W.bitmaps[W.dc[mem]]
    alto, ancho = bmp["alto"], bmp["ancho"]
    assert img.shape == (alto, ancho, 4), (img.shape, alto, ancho)
    ctypes.memmove(bmp["buf"], np.ascontiguousarray(img).tobytes(), alto * ancho * 4)


def EnumWindows(cb, lp):
    for h, v in list(W.ventanas.items()):
        if v.padre is None and not cb(h, lp):
            break
    return 1


def EnumChildWindows(padre, cb, lp):
    pila = list(W.ventanas[padre].hijas)
    while pila:
        h = pila.pop(0)
        if not cb(h, lp):
            break
        pila.extend(W.ventanas[h].hijas)
    return 1


def IsWindowVisible(h):
    return int(W.ventanas[h].visible)


def IsIconic(h):
    return int(W.ventanas[W.raiz(h)].minimizada)


def GetWindow(h, cual):
    assert cual == 5
    hijas = W.ventanas[h].hijas
    return hijas[0] if hijas else None


def GetWindowThreadProcessId(h, pid):
    _obj(pid).value = h * 10
    return 1


def GetWindowTextW(h, buf, n):
    buf.value = W.ventanas[h].titulo[:n - 1]
    return len(buf.value)


def GetClientRect(h, r):
    v, r = W.ventanas[h], _obj(r)
    r.left, r.top = 0, 0
    r.right, r.bottom = (0, 0) if W.ventanas[W.raiz(h)].minimizada else (v.ancho, v.alto)
    return 1


def ClientToScreen(h, p):
    v, p = W.ventanas[h], _obj(p)
    p.x += v.x
    p.y += v.y
    return 1


def GetDC(h):
    assert h is None
    dc = W.nuevo()
    W.dc[dc] = "pantalla"
    return dc


def ReleaseDC(h, dc):
    W.sueltos.add(dc)
    return 1


def PrintWindow(h, mem, flags):
    assert flags == 3
    v = W.ventanas[h]
    img = W.contenido[h].copy()
    if W.negra_3d:
        for c in v.hijas:
            t = W.ventanas[c]
            if t.titulo == "vista3d":
                img[t.y - v.y:t.y - v.y + t.alto, t.x - v.x:t.x - v.x + t.ancho] = 0
    _escribir_bitmap(mem, img)
    return 1


def RegisterHotKey(h, ident, mods, vk):
    if (mods, vk) in W.atajos.values() or W.error:
        W.error = W.error or 1409
        return 0
    W.atajos[ident] = (mods, vk)
    return 1


def UnregisterHotKey(h, ident):
    W.atajos.pop(ident, None)
    return 1


def PeekMessageW(msg, h, desde, hasta, quitar):
    if not W.cola:
        return 0
    m = _obj(msg)
    m.message, m.wParam = W.cola.pop(0)
    return 1


def CreateCompatibleDC(dc):
    mem = W.nuevo()
    W.dc[mem] = None
    return mem


def CreateDIBSection(dc, bih, uso, bits, sec, off):
    b = _obj(bih)
    assert b.biSize == ctypes.sizeof(V._BITMAPINFOHEADER) and b.biBitCount == 32 and b.biHeight < 0
    buf = ctypes.create_string_buffer(b.biWidth * -b.biHeight * 4)
    h = W.nuevo()
    W.bitmaps[h] = {"buf": buf, "ancho": b.biWidth, "alto": -b.biHeight}
    _obj(bits).value = ctypes.addressof(buf)
    return h


def SelectObject(dc, obj):
    antes = W.dc[dc]
    W.dc[dc] = obj
    return antes or 7


def DeleteObject(h):
    W.sueltos.add(h)
    return 1


def DeleteDC(h):
    W.sueltos.add(h)
    return 1


def SetStretchBltMode(dc, modo):
    return 1


def StretchBlt(mem, x, y, an_d, al_d, src, xs, ys, an, al, rop):
    assert W.dc[src] == "pantalla" and (x, y) == (0, 0)
    zona = W.pantalla[ys:ys + al, xs:xs + an]
    filas = (np.arange(al_d) * al) // al_d
    cols = (np.arange(an_d) * an) // an_d
    _escribir_bitmap(mem, zona[filas][:, cols])
    return 1


def OpenProcess(acceso, hereda, pid):
    return None if pid // 10 in W.sin_permiso else pid + 1


def QueryFullProcessImageNameW(hp, flags, buf, n):
    buf.value = "C:\\Program Files\\" + W.ventanas[(hp - 1) // 10].exe
    _obj(n).value = len(buf.value)
    return 1


def CloseHandle(h):
    return 1


def SetThreadDpiAwarenessContext(ctx):
    W.dpi.add(threading.get_ident())
    return 1


api = types.SimpleNamespace(
    user32=types.SimpleNamespace(**{n: _hacer("user32", n, globals()[n]) for n in FIRMAS["user32"]}),
    gdi32=types.SimpleNamespace(**{n: _hacer("gdi32", n, globals()[n]) for n in FIRMAS["gdi32"]}),
    kernel32=types.SimpleNamespace(**{n: _hacer("kernel32", n, globals()[n]) for n in FIRMAS["kernel32"]}),
    ultimo_error=lambda: W.error,
    pixeles_reales=lambda: api.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4)))
V._W["api"] = api

# el escritorio: un Bloc de notas grande, Google Earth (panel + vista 3D) y su diálogo
rng = np.random.default_rng(7)
W.ventana(1, "notepad.exe", "Sin título - Bloc de notas", 0, 0, 1400, 900)
ge = W.ventana(2, "Google Earth Pro\\client\\googleearth.exe", "Google Earth Pro", 120, 60, 1000, 700)
panel = W.ventana(3, "", "panel", 120, 60, 260, 700, padre=2)
W.ventana(4, "", "boton", 130, 70, 40, 20, padre=3)
vista = W.ventana(5, "", "vista3d", 380, 60, 740, 700, padre=2)
W.ventana(6, "Google Earth Pro\\client\\googleearth.exe", "Buscar", 300, 300, 300, 200)
W.ventana(7, "Google Earth Pro\\client\\googleearth.exe", "Oculta", 0, 0, 1300, 800, visible=False)
W.pantalla[:] = 200
contenido = rng.integers(20, 255, (700, 1000, 4), dtype=np.uint8)
W.contenido[2] = contenido
W.pantalla[60:760, 120:1120] = contenido          # Google Earth al frente
W.pantalla[300:500, 300:600] = 90                 # su diálogo, encima

# ------------------------------------------------- 3. la ventana de Google Earth
f = V.FotoWin()
assert f.ventana() == (2, 1000, 700), f.ventana()
W.sin_permiso = {2, 6}                             # sin permiso: por el título
assert f.ventana() == (2, 1000, 700)
W.sin_permiso = set()
ge.minimizada, W.ventanas[6].visible = True, False    # minimizado (Windows esconde su diálogo)
assert f.ventana() is None
assert f.ventana(visible=False) is not None        # ¿está abierto? sí, minimizado
ge.minimizada, W.ventanas[6].visible = False, True
assert f._vista3d() == (2, 260, 0, 740, 700), f._vista3d()
print("ok la ventana de Google Earth: la más grande de googleearth.exe, sin el Bloc de notas")

# ------------------------------------------------- 4. la foto: PrintWindow o la pantalla
a = f.foto()
assert a.shape == (700, 1000, 3) and f.metodo == "ventana"
assert np.array_equal(a, contenido[..., 2::-1])    # BGRX -> RGB, aunque el diálogo la tape
assert W.llamadas.count("PrintWindow") == 1
f2 = V.FotoWin()
W.negra_3d = True                                  # OpenGL: PrintWindow la ve negra
b = f2.foto()
assert f2.metodo == "pantalla"
assert np.array_equal(b, W.pantalla[60:760, 120:1120, 2::-1])
n = W.llamadas.count("PrintWindow")
f2.foto()
assert W.llamadas.count("PrintWindow") == n         # ya sabe: directo de la pantalla
W.negra_3d = False
ge.minimizada, W.ventanas[6].visible = True, False
try:
    f.foto()
    raise AssertionError("foto minimizada")
except GE.GoogleEarthError as e:
    assert "minimizar" in str(e)
ge.minimizada, W.ventanas[6].visible = False, True
abiertos = [d for d in W.dc if d not in W.sueltos and W.dc[d] != "pantalla"]
assert not abiertos and all(b in W.sueltos for b in W.bitmaps), "GDI sin soltar"
print("ok foto por PrintWindow; si la vista 3D sale negra, desde la pantalla; GDI suelto")

# ------------------------------------------------- 5. el video de la ventanita
vid = V.VideoWin()
c = vid.cuadro(370)
assert c.shape == (350, 370, 3), c.shape
assert np.array_equal(c, W.pantalla[60:760:2, 380:1120:2, 2::-1])
ge.minimizada = True
assert vid.cuadro(370) is None
ge.minimizada = False
ge.x, vista.x, panel.x = ge.x + 10, vista.x + 10, panel.x + 10      # la movieron
W.pantalla[60:760, 130:1130] = contenido
c2 = vid.cuadro(740)
assert c2.shape == (700, 740, 3) and np.array_equal(c2, W.pantalla[60:760, 390:1130, 2::-1])
t0, k = time.time(), 0
while time.time() - t0 < 0.3:
    vid.cuadro(800)
    k += 1
hilo = threading.Thread(target=lambda: vid.cuadro(200))
hilo.start()
hilo.join()
assert hilo.ident in W.dpi and threading.get_ident() in W.dpi     # pantalla escalada: píxeles reales
print(f"ok video de la vista 3D desde la pantalla, en píxeles reales ({k / 0.3:.0f} cuadros/s simulados)")

# ------------------------------------------------- 6. Ctrl+Alt+G
apretado = threading.Event()
at = V.AtajoWin(apretado.set)
assert at.iniciar() is True, at.error
assert W.atajos == {at.ID: (0x1 | 0x2 | 0x4000, ord("G"))}
W.cola.append((0x0312, at.ID))                     # WM_HOTKEY
assert apretado.wait(2)
otro = V.AtajoWin(lambda: None)
assert otro.iniciar() is False and otro.error == "otro programa ya usa Ctrl+Alt+G"
at.detener()
assert W.atajos == {}                              # apagado no queda rastro
W.error = 5
assert V.AtajoWin(lambda: None).iniciar() is False
W.error = 0
print("ok Ctrl+Alt+G con RegisterHotKey; ocupado avisa; al detener se suelta")

# ------------------------------------------------- 7. cada sistema con lo suyo
sys.platform = "win32"
try:
    assert isinstance(V.Foto(), V.FotoWin) and isinstance(V.Video(), V.VideoWin)
    assert isinstance(V.Atajo(lambda: None), V.AtajoWin)
finally:
    sys.platform = plat
if plat != "win32":
    V._W["api"] = None
    assert not isinstance(V.Atajo(lambda: None), V.AtajoWin)
    assert V.AtajoWin(lambda: None).iniciar() is False
    V._W["api"] = api
for n in ("V.Foto()", "V.Video()", "V.Atajo(self._tecla.set)"):
    assert n in UI, n
assert "X11(" not in UI, "la ventanita usa X11 directo"
print("ok la ventanita usa Foto(), Video() y Atajo(): Windows o X11 según el sistema")

# ------------------------------------------------- 8. lo que ya era multiplataforma
srv = V.Servidor(puerto=0)
srv.iniciar()
try:
    url = f"http://127.0.0.1:{srv.puerto}"
    assert url.startswith("http://127.0.0.1:")
    with urlopen(url + "/vista?BBOX=-54.62,-27.02,-54.60,-27.00&CAMERA=-54.61,-27.01,900,0,0",
                 timeout=5) as r:
        assert r.status == 200 and b"kml" in r.read(200).lower()
finally:
    srv.detener()
ruta = GE.archivo_kml()
assert ruta.is_relative_to(Path.home()) and ".config" in ruta.parts      # %USERPROFILE%\.config en Windows
assert GE.soltar_candado(False) is False            # sin candado (Windows no lo deja): no hace nada
print("ok servidor local en 127.0.0.1 y enlace KML en la carpeta del usuario: igual en Windows")

# ------------------------------------------------- 9. los dos lados con el mismo núcleo
raiz = NUCLEO.parents[1]
for nombre in ("googleearth_vivo.py", "googleearth_ui.py"):
    for lado in ("INGECAD", "QGIS"):
        assert (raiz / lado / "codigo" / "geocad" / nombre).read_bytes() == (NUCLEO / nombre).read_bytes(), (lado, nombre)
print("ok núcleo igual en IngeCAD y QGIS")
print("TODO OK GOOGLE EARTH WINDOWS")
