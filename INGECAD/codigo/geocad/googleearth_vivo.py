# SPDX-License-Identifier: GPL-3.0-or-later
"""Módulo «Google Earth» (3.33.0): lo que habla con Google Earth.

  Servidor   el servidor local (127.0.0.1) de los NetworkLink: /vista sabe
             la vista y devuelve las cruces sólo mientras se captura (o
             siempre, si se eligió); /camara mueve la cámara (flyToView).
             Vive desde que se abre la ventanita hasta que se apaga el
             módulo o se cierra el programa (3.33.3): Google Earth abandona
             un NetworkLink cuando el servidor se cae (prueba del 20/10/2026).
  FotoX11    la foto de la ventana de Google Earth con XGetImage (en
             silencio; la vista 3D sola sale negra: se toma la ventana
             entera). Google Earth va por X11 (XWayland).
  AtajoX11   Ctrl+Alt+G mientras Google Earth tiene el foco (XGrabKey sobre
             la raíz de XWayland). No toca los atajos de GNOME: los Flatpak
             de IngeCAD y QGIS no pueden, y apagado no queda rastro.
  Captura    el recorrido: enderezar la vista, poner las cruces, esperar a
             que la imagen se aquiete, sacar la foto; en el mosaico, volar a
             cada pieza y devolver la vista a donde estaba. Nunca se vuela a
             una posición inválida.

Las teclas por XSendEvent no le llegan a Google Earth y XTest pide permiso
de control remoto: GeoCAD no aprieta teclas. Sin Qt (hilos de Python).
"""
from __future__ import annotations

import ctypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import googleearth as GE

KML = "application/vnd.google-earth.kml+xml"


# ================================================================== registro
def archivo_registro():
    """Lo que pasa entre GeoCAD y Google Earth (3.33.3): para ver por qué un
    vuelo queda sin respuesta. Se corta solo al pasar 1 MB."""
    return GE.archivo_ajustes().parent / "googleearth_registro.txt"


_CERROJO_REGISTRO = threading.Lock()


def registrar(texto: str) -> None:
    try:
        ruta = archivo_registro()
        with _CERROJO_REGISTRO:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            if ruta.exists() and ruta.stat().st_size > 1_000_000:
                ruta.replace(ruta.with_suffix(".anterior.txt"))
            with open(ruta, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {texto}\n")
    except OSError:
        pass


# ================================================================== servidor
class Servidor:
    """El servidor de los NetworkLink. ``armado`` = devolver las cruces."""

    def __init__(self, puerto: int = GE.PUERTO, marcas_siempre: bool = False) -> None:
        self.cerrojo = threading.Lock()
        self.vista = None            # la última Vista válida
        self.t_vista = 0.0           # cuándo llegó
        self.marcas = []             # las de la última vista
        self.marcas_servidas = 0.0   # cuándo se mandaron cruces por última vez
        self.t_camara = 0.0          # último pedido de /camara (Google Earth conectado)
        self.pendiente = None        # (lon, lat, rango) a volar
        self.t_crudo = ""            # lo que mandó Google Earth como fecha (3.33.3, para el informe)
        self.cruces = None           # 3.33.4: las de la captura en curso (van por /camara)
        self.cruces_servidas = []    # las últimas que se mandaron
        self.t_entregado = 0.0       # cuándo Google Earth se llevó el último vuelo
        self.t_cruces = 0.0          # último pedido de /cruces (el enlace de 3.33.4)
        self.armado = False
        self.marcas_siempre = marcas_siempre
        self._icono = GE.png(GE.imagen_marca())
        self._srv = None
        self.puerto = puerto

    # -- arranque y parada
    def iniciar(self) -> int:
        """Arranca en ``puerto`` (o el primero libre de los diez siguientes);
        devuelve el puerto."""
        dueno = self
        ultimo = None

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):  # noqa: N802
                try:
                    tipo, cuerpo = dueno.atender(self.path)
                except Exception:  # noqa: BLE001 -- el servidor no se cae nunca
                    tipo, cuerpo = KML, GE.kml_vacio()
                if cuerpo is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(cuerpo)

        for p in ([self.puerto] if self.puerto == 0 else range(self.puerto, self.puerto + 10)):
            try:
                self._srv = ThreadingHTTPServer(("127.0.0.1", p), Manejador)
                break
            except OSError as exc:
                ultimo = exc
        if self._srv is None:
            raise GE.GoogleEarthError(f"No se pudo abrir el servidor local de GeoCAD ({ultimo}).")
        self._srv.daemon_threads = True
        self.puerto = self._srv.server_address[1]
        threading.Thread(target=self._srv.serve_forever, name="geocad-ge-servidor",
                         daemon=True).start()
        return self.puerto

    def detener(self) -> None:
        if self._srv is not None:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None

    @property
    def vivo(self) -> bool:
        return self._srv is not None

    # -- lo que pide Google Earth
    def atender(self, ruta: str):
        u = urlparse(ruta)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        url = f"http://127.0.0.1:{self.puerto}"
        if u.path == "/marca.png":
            return "image/png", self._icono
        if u.path == "/vista":
            vista = GE.leer_vista(q)
            registrar(f"/vista {q.get('cam', '-')}" + ("" if vista is not None else " (inválida)"))
            with self.cerrojo:
                if vista is not None:
                    self.vista = vista
                    self.t_crudo = str(q.get("t", ""))
                    self.marcas = GE.marcas_de_bbox(vista.oeste, vista.sur, vista.este, vista.norte)
                    self.t_vista = time.time()
            # 3.33.4: las cruces van sólo por /camara (se renueva cada 1 s);
            # /vista no se vuelve a pedir después de un vuelo y sus cruces
            # quedaban viejas
            return KML, GE.kml_vacio()
        if u.path == "/camara":
            with self.cerrojo:
                self.t_camara = time.time()
                p, self.pendiente = self.pendiente, None
                if p is not None and not GE.posicion_valida(*p):
                    p = None
                if p is not None:
                    self.t_entregado = self.t_camara
            if p is not None:
                registrar(f"/camara entrega el vuelo {p[0]:.7f},{p[1]:.7f},{p[2]:.1f}")
            return KML, GE.kml_camara(p, [], url + "/marca.png")      # nunca cruces acá
        if u.path == "/cruces":
            with self.cerrojo:
                ahora = time.time()
                self.t_cruces = ahora
                marcas = self.cruces_a_mostrar()
                if marcas:
                    self.marcas_servidas = ahora
                    self.cruces_servidas = list(marcas)
            return KML, GE.kml_camara(None, marcas, url + "/marca.png")
        if u.path == "/geocad.kml":
            return KML, GE.kml_enlaces(self.puerto)
        return KML, None

    def cruces_a_mostrar(self) -> list:
        """Las de la captura en curso; si no, las de la última vista mientras
        se arma una captura o si se eligió verlas siempre."""
        if self.cruces is not None:
            return list(self.cruces)
        if self.armado or self.marcas_siempre:
            return list(self.marcas)
        return []

    # -- lo que pide GeoCAD
    def conectado(self, segundos: float = 4.0) -> bool:
        """¿Google Earth pide /camara (cada 1 s)?"""
        return time.time() - self.t_camara < segundos

    def enlace_viejo(self, segundos: float = 4.0) -> bool:
        """¿Enlazado con el enlace de antes de la 3.33.4 (sin /cruces)? Hay que
        borrarlo en Google Earth y abrirlo de nuevo con GeoCAD."""
        return self.conectado(segundos) and time.time() - self.t_cruces >= segundos

    def volar(self, lon: float, lat: float, rango: float) -> None:
        if not GE.posicion_valida(lon, lat, rango):
            raise GE.GoogleEarthError(f"Posición inválida ({lon}, {lat}, {rango} m): no se vuela.")
        with self.cerrojo:
            if self.pendiente is not None:
                registrar("volar: el vuelo anterior no se había entregado (se reemplaza)")
            self.pendiente = (float(lon), float(lat), float(rango))
        registrar(f"volar pedido {lon:.7f},{lat:.7f},{rango:.1f}")

    def ultima(self):
        with self.cerrojo:
            return self.vista, self.t_vista, list(self.marcas)


# ================================================================== X11
class _XImage(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
                ("format", ctypes.c_int), ("data", ctypes.POINTER(ctypes.c_ubyte)),
                ("byte_order", ctypes.c_int), ("bitmap_unit", ctypes.c_int),
                ("bitmap_bit_order", ctypes.c_int), ("bitmap_pad", ctypes.c_int),
                ("depth", ctypes.c_int), ("bytes_per_line", ctypes.c_int),
                ("bits_per_pixel", ctypes.c_int)]


class _XWindowAttributes(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("width", ctypes.c_int),
                ("height", ctypes.c_int), ("border_width", ctypes.c_int), ("depth", ctypes.c_int),
                ("visual", ctypes.c_void_p), ("root", ctypes.c_ulong), ("class_", ctypes.c_int),
                ("bit_gravity", ctypes.c_int), ("win_gravity", ctypes.c_int),
                ("backing_store", ctypes.c_int), ("backing_planes", ctypes.c_ulong),
                ("backing_pixel", ctypes.c_ulong), ("save_under", ctypes.c_int),
                ("colormap", ctypes.c_ulong), ("map_installed", ctypes.c_int),
                ("map_state", ctypes.c_int), ("all_event_masks", ctypes.c_long),
                ("your_event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p)]


class _XClassHint(ctypes.Structure):
    # punteros crudos: los libera X (XFree), no Python
    _fields_ = [("res_name", ctypes.c_void_p), ("res_class", ctypes.c_void_p)]


class _XKeyEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("root", ctypes.c_ulong),
                ("subwindow", ctypes.c_ulong), ("time", ctypes.c_ulong), ("x", ctypes.c_int),
                ("y", ctypes.c_int), ("x_root", ctypes.c_int), ("y_root", ctypes.c_int),
                ("state", ctypes.c_uint), ("keycode", ctypes.c_uint), ("same_screen", ctypes.c_int)]


class _XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xkey", _XKeyEvent), ("pad", ctypes.c_long * 24)]


_X = {"lib": None, "errores": 0}
_MANEJADOR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


@_MANEJADOR
def _al_error(_dpy, _ev):
    # sin esto, un error de X (una ventana que se cerró) termina el programa
    _X["errores"] += 1
    return 0


def _xlib():
    """libX11 con las firmas que se usan, o None (sin X11)."""
    if _X["lib"] is not None:
        return _X["lib"] or None
    try:                                          # la AppImage de IngeCAD no trae ctypes.util
        from ctypes.util import find_library

        nombre = find_library("X11") or "libX11.so.6"
    except ImportError:
        nombre = "libX11.so.6"
    try:
        x = ctypes.cdll.LoadLibrary(nombre)
    except OSError:
        _X["lib"] = False
        return None
    x.XInitThreads()
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                             ctypes.POINTER(ctypes.c_ulong),
                             ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                             ctypes.POINTER(ctypes.c_uint)]
    x.XGetClassHint.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XClassHint)]
    x.XGetWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                       ctypes.POINTER(_XWindowAttributes)]
    x.XGetImage.restype = ctypes.POINTER(_XImage)
    x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                            ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x.XFree.argtypes = [ctypes.c_void_p]
    x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x.XKeysymToKeycode.restype = ctypes.c_ubyte
    x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int]
    x.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
    x.XPending.argtypes = [ctypes.c_void_p]
    x.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(_XEvent)]
    x.XSetErrorHandler.argtypes = [_MANEJADOR]
    x.XSetErrorHandler(_al_error)
    _X["lib"] = x
    return x


class FotoX11:
    """La foto de la ventana más grande de Google Earth Pro."""

    CLASE = b"googleearth-bin"

    def __init__(self) -> None:
        self.x = _xlib()
        self.dpy = self.x.XOpenDisplay(None) if self.x else None
        if not self.dpy:
            raise GE.GoogleEarthError("No hay pantalla X11: la captura necesita Google Earth Pro "
                                      "(va por X11/XWayland).")

    def cerrar(self) -> None:
        if self.dpy:
            self.x.XCloseDisplay(self.dpy)
            self.dpy = None

    def _hijos(self, w):
        raiz, padre = ctypes.c_ulong(), ctypes.c_ulong()
        hijos, n = ctypes.POINTER(ctypes.c_ulong)(), ctypes.c_uint()
        if not self.x.XQueryTree(self.dpy, w, ctypes.byref(raiz), ctypes.byref(padre),
                                 ctypes.byref(hijos), ctypes.byref(n)):
            return []
        out = [hijos[i] for i in range(n.value)]
        if hijos:
            self.x.XFree(hijos)
        return out

    def ventana(self):
        """(id, ancho, alto) de la ventana principal de Google Earth, o None."""
        mejor = None
        pila = [self.x.XDefaultRootWindow(self.dpy)]
        while pila:
            w = pila.pop()
            pila.extend(self._hijos(w))
            pista = _XClassHint()
            if not self.x.XGetClassHint(self.dpy, w, ctypes.byref(pista)):
                continue
            nombres = [ctypes.string_at(p) if p else b"" for p in (pista.res_name, pista.res_class)]
            for p in (pista.res_name, pista.res_class):
                if p:
                    self.x.XFree(p)
            es_ge = self.CLASE in nombres
            if not es_ge:
                continue
            at = _XWindowAttributes()
            if not self.x.XGetWindowAttributes(self.dpy, w, ctypes.byref(at)) or at.map_state != 2:
                continue
            if mejor is None or at.width * at.height > mejor[1] * mejor[2]:
                mejor = (w, at.width, at.height)
        return mejor

    def previa(self, ancho: int = 440):
        """Una foto achicada para la vista previa de la ventanita (3.33.3,
        idea de Fernando), o None si Google Earth no está a la vista. Se
        achica sobre la memoria de X sin copiar la foto entera (la ventana
        se busca una vez y se recuerda): unas 10 veces más rápida que foto()."""
        import numpy as np

        for _vez in range(2):
            v = getattr(self, "_v_previa", None) or self.ventana()
            if v is None:
                return None
            w, ancho_v, alto_v = v
            antes = _X["errores"]
            img = self.x.XGetImage(self.dpy, w, 0, 0, ancho_v, alto_v, 0xFFFFFFFF, 2)
            self.x.XSync(self.dpy, 0)
            if not img or _X["errores"] != antes:
                self._v_previa = None                   # cambió de tamaño o se cerró: buscarla
                continue
            self._v_previa = v
            try:
                im = img.contents
                if im.bits_per_pixel != 32:
                    return None
                k = max(1, -(-im.width // ancho))
                crudo = np.ctypeslib.as_array(ctypes.cast(im.data, ctypes.POINTER(ctypes.c_uint8)),
                                              shape=(im.height, im.bytes_per_line))
                a = crudo[::k, :im.width * 4].reshape(-1, im.width, 4)[:, ::k, 2::-1]
                return np.ascontiguousarray(a)          # copia chica, antes de liberar
            finally:
                self.x.XFree(ctypes.cast(img.contents.data, ctypes.c_void_p))
                self.x.XFree(ctypes.cast(img, ctypes.c_void_p))
        return None

    def foto(self):
        """La ventana como arreglo RGB (alto x ancho x 3)."""
        import numpy as np

        v = self.ventana()
        if v is None:
            raise GE.GoogleEarthError("No se encuentra la ventana de Google Earth Pro (¿está "
                                      "abierta y sin minimizar?).")
        w, ancho, alto = v
        antes = _X["errores"]
        img = self.x.XGetImage(self.dpy, w, 0, 0, ancho, alto, 0xFFFFFFFF, 2)   # ZPixmap
        self.x.XSync(self.dpy, 0)
        if not img or _X["errores"] != antes:
            raise GE.GoogleEarthError("No se pudo sacar la foto de Google Earth (¿la ventana "
                                      "quedó tapada o minimizada?).")
        try:
            im = img.contents
            if im.bits_per_pixel != 32:
                raise GE.GoogleEarthError("La pantalla no es de 24/32 bits: no se puede capturar.")
            crudo = ctypes.string_at(im.data, im.bytes_per_line * im.height)
            a = np.frombuffer(crudo, np.uint8).reshape(im.height, im.bytes_per_line)
            a = a[:, :im.width * 4].reshape(im.height, im.width, 4)
            return np.ascontiguousarray(a[..., 2::-1])                         # BGRX -> RGB
        finally:
            self.x.XFree(ctypes.cast(img.contents.data, ctypes.c_void_p))
            self.x.XFree(ctypes.cast(img, ctypes.c_void_p))


class _ShmInfo(ctypes.Structure):
    _fields_ = [("shmseg", ctypes.c_ulong), ("shmid", ctypes.c_int),
                ("shmaddr", ctypes.c_void_p), ("readOnly", ctypes.c_int)]


class VideoX11(FotoX11):
    """La vista previa como video (3.33.4, Fernando: «que sea un video, no una
    suma de diapositivas»): sólo la vista 3D de Google Earth (sin el panel ni
    las barras), por memoria compartida de X (MIT-SHM: unos 70 cuadros por
    segundo con una pantalla 4K). Si no hay MIT-SHM (un Flatpak sin IPC
    compartido), con XGetImage de esa zona (más lento, igual sirve)."""

    def __init__(self) -> None:
        super().__init__()
        self._zona = None             # (ventana, x, y, ancho, alto) de la vista 3D
        self._shm = None              # (imagen, info, arreglo)
        self._xe = self._libc = None
        try:
            self._xe = ctypes.cdll.LoadLibrary("libXext.so.6")
            self._libc = ctypes.CDLL("libc.so.6")
            xe, lc = self._xe, self._libc
            xe.XShmQueryExtension.argtypes = [ctypes.c_void_p]
            xe.XShmCreateImage.restype = ctypes.POINTER(_XImage)
            xe.XShmCreateImage.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                           ctypes.c_int, ctypes.c_void_p,
                                           ctypes.POINTER(_ShmInfo), ctypes.c_uint, ctypes.c_uint]
            xe.XShmAttach.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ShmInfo)]
            xe.XShmDetach.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ShmInfo)]
            xe.XShmGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XImage),
                                        ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
            lc.shmget.argtypes = [ctypes.c_int, ctypes.c_size_t, ctypes.c_int]
            lc.shmat.restype = ctypes.c_void_p
            lc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
            lc.shmdt.argtypes = [ctypes.c_void_p]
            lc.shmctl.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
            if not xe.XShmQueryExtension(self.dpy):
                self._xe = None
        except (OSError, AttributeError):
            self._xe = None
        self.x.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong)]

    def _vista3d(self):
        """La subventana más grande sin hijas (la vista 3D) y dónde está."""
        v = self.ventana()
        if v is None:
            return None
        w = v[0]
        mejor, pila = None, [w]
        while pila:
            h = pila.pop()
            hijos = [c for c in self._hijos(h)]
            visibles = []
            for c in hijos:
                at = _XWindowAttributes()
                if self.x.XGetWindowAttributes(self.dpy, c, ctypes.byref(at)) and at.map_state == 2:
                    visibles.append((c, at.width, at.height))
            if not visibles and h != w:
                at = _XWindowAttributes()
                self.x.XGetWindowAttributes(self.dpy, h, ctypes.byref(at))
                if mejor is None or at.width * at.height > mejor[1] * mejor[2]:
                    mejor = (h, at.width, at.height)
            pila.extend(c for c, _a, _b in visibles)
        if mejor is None or mejor[1] * mejor[2] < 0.2 * v[1] * v[2]:
            return (w, 0, 0, v[1], v[2])                 # no se encontró: la ventana entera
        x, y, hijo = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        self.x.XTranslateCoordinates(self.dpy, mejor[0], w, 0, 0, ctypes.byref(x), ctypes.byref(y),
                                     ctypes.byref(hijo))
        return (w, x.value, y.value, mejor[1], mejor[2])

    def _soltar_shm(self) -> None:
        if self._shm is not None:
            img, info, _a = self._shm
            self._xe.XShmDetach(self.dpy, ctypes.byref(info))
            self.x.XSync(self.dpy, 0)
            self._libc.shmdt(ctypes.c_void_p(info.shmaddr))
            img.contents.data = None
            self.x.XFree(ctypes.cast(img, ctypes.c_void_p))
            self._shm = None

    def _armar_shm(self, w, ancho, alto) -> None:
        import numpy as np

        at = _XWindowAttributes()
        self.x.XGetWindowAttributes(self.dpy, w, ctypes.byref(at))
        info = _ShmInfo()
        img = self._xe.XShmCreateImage(self.dpy, at.visual, at.depth, 2, None, ctypes.byref(info),
                                       ancho, alto)
        if not img or img.contents.bits_per_pixel != 32:
            raise OSError("XShmCreateImage")
        im = img.contents
        info.shmid = self._libc.shmget(0, im.bytes_per_line * im.height, 0o1000 | 0o600)
        if info.shmid < 0:
            self.x.XFree(ctypes.cast(img, ctypes.c_void_p))
            raise OSError("shmget")
        info.shmaddr = self._libc.shmat(info.shmid, None, 0)
        info.readOnly = 0
        im.data = ctypes.cast(info.shmaddr, type(im.data))
        antes = _X["errores"]
        self._xe.XShmAttach(self.dpy, ctypes.byref(info))
        self.x.XSync(self.dpy, 0)
        self._libc.shmctl(info.shmid, 0, None)          # IPC_RMID: se borra al soltarla
        if _X["errores"] != antes:
            self._libc.shmdt(ctypes.c_void_p(info.shmaddr))
            raise OSError("XShmAttach")
        a = np.ctypeslib.as_array(ctypes.cast(info.shmaddr, ctypes.POINTER(ctypes.c_uint8)),
                                  shape=(im.height, im.bytes_per_line))
        self._shm = (img, info, a)

    def cuadro(self, ancho: int = 800):
        """La vista 3D achicada a ``ancho`` píxeles (más o menos), o None."""
        import numpy as np

        for _vez in range(2):
            if self._zona is None:
                self._soltar_shm()
                self._zona = self._vista3d()
                if self._zona is None:
                    return None
            w, x0, y0, an, al = self._zona
            k = max(1, -(-an // max(1, ancho)))
            antes = _X["errores"]
            if self._xe is not None:
                try:
                    if self._shm is None:
                        self._armar_shm(w, an, al)
                    img, _info, crudo = self._shm
                    self._xe.XShmGetImage(self.dpy, w, img, x0, y0, 0xFFFFFFFF)
                    self.x.XSync(self.dpy, 0)
                    if _X["errores"] == antes:
                        return np.ascontiguousarray(crudo[::k, :an * 4].reshape(-1, an, 4)[:, ::k, 2::-1])
                except OSError:
                    self._xe = None                     # sin MIT-SHM: a lo común
                    self._soltar_shm()
                self._zona = None                       # cambió de tamaño o se cerró
                continue
            img = self.x.XGetImage(self.dpy, w, x0, y0, an, al, 0xFFFFFFFF, 2)
            self.x.XSync(self.dpy, 0)
            if not img or _X["errores"] != antes:
                self._zona = None
                continue
            try:
                im = img.contents
                if im.bits_per_pixel != 32:
                    return None
                crudo = np.ctypeslib.as_array(ctypes.cast(im.data, ctypes.POINTER(ctypes.c_uint8)),
                                              shape=(im.height, im.bytes_per_line))
                return np.ascontiguousarray(crudo[::k, :im.width * 4].reshape(-1, im.width, 4)[:, ::k, 2::-1])
            finally:
                self.x.XFree(ctypes.cast(img.contents.data, ctypes.c_void_p))
                self.x.XFree(ctypes.cast(img, ctypes.c_void_p))
        return None

    def cerrar(self) -> None:
        if self.dpy:
            try:
                self._soltar_shm()
            except Exception:  # noqa: BLE001
                pass
        super().cerrar()


class AtajoX11:
    """Ctrl+Alt+G sobre la raíz de X11 mientras esté iniciado: ``al_apretar``
    se llama desde otro hilo (la ventanita lo pasa a su temporizador)."""

    XK_G = 0x67
    CONTROL, MOD1, LOCK, MOD2 = 1 << 2, 1 << 3, 1 << 1, 1 << 4      # Ctrl, Alt, Bloq Mayús, Bloq Num

    def __init__(self, al_apretar) -> None:
        self.al_apretar = al_apretar
        self._hilo = None
        self._parar = threading.Event()
        self.error = ""

    def iniciar(self) -> bool:
        x = _xlib()
        dpy = x.XOpenDisplay(None) if x else None
        if not dpy:
            self.error = "sin X11"
            return False
        raiz = x.XDefaultRootWindow(dpy)
        tecla = x.XKeysymToKeycode(dpy, self.XK_G)
        mods = [self.CONTROL | self.MOD1 | extra for extra in (0, self.LOCK, self.MOD2,
                                                               self.LOCK | self.MOD2)]
        antes = _X["errores"]
        for m in mods:
            x.XGrabKey(dpy, tecla, m, raiz, 1, 1, 1)              # GrabModeAsync
        x.XSync(dpy, 0)
        if _X["errores"] != antes:
            self.error = "otro programa ya usa Ctrl+Alt+G"
            for m in mods:
                x.XUngrabKey(dpy, tecla, m, raiz)
            x.XCloseDisplay(dpy)
            return False
        self._parar.clear()

        def escuchar():
            ev = _XEvent()
            try:
                while not self._parar.is_set():
                    while x.XPending(dpy):
                        x.XNextEvent(dpy, ctypes.byref(ev))
                        if ev.type == 2 and ev.xkey.keycode == tecla:     # KeyPress
                            try:
                                self.al_apretar()
                            except Exception:  # noqa: BLE001
                                pass
                    self._parar.wait(0.05)
            finally:
                for m in mods:
                    x.XUngrabKey(dpy, tecla, m, raiz)
                x.XSync(dpy, 0)
                x.XCloseDisplay(dpy)

        self._hilo = threading.Thread(target=escuchar, name="geocad-ge-atajo", daemon=True)
        self._hilo.start()
        return True

    def detener(self) -> None:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(2)
            self._hilo = None


# ================================================================== la captura
class Cancelado(GE.GoogleEarthError):
    pass


class Reintentable(GE.GoogleEarthError):
    """Una falla que se arregla probando de nuevo (Google Earth no respondió
    al vuelo, la imagen no terminó de cargar, no se vieron las cruces)."""


INTENTOS = 3              # la captura entera; y cada pieza del mosaico


def con_reintentos(hacer, aviso=None, cancelar=None, intentos: int = INTENTOS):
    """``hacer(intento)`` hasta que salga (3.33.3, Fernando: «en vez de dar
    tantos mensajes de error debería empezar el ciclo de una nueva captura;
    lo peor que puede pasar es que se demore un poco más»). Sólo se repite
    lo Reintentable; el resto (sin enlace, demasiadas piezas...) sale ya."""
    aviso = aviso or (lambda _t, _f=None: None)
    for n in range(1, intentos + 1):
        try:
            return hacer(n)
        except Reintentable as exc:
            if n == intentos:
                raise GE.GoogleEarthError(f"No salió en {intentos} intentos. Lo último: {exc}") from exc
            if cancelar is not None and cancelar.is_set():
                raise Cancelado("Cancelado.") from exc
            aviso(f"No salió ({exc}) Empezando de nuevo: intento {n + 1} de {intentos}...", 0.02)


class Captura:
    """El recorrido de una captura. ``foto()`` devuelve la ventana como
    arreglo RGB; ``aviso(texto, fraccion)`` informa el avance (desde el hilo
    de la captura). Los tiempos se pueden achicar en las pruebas.

    3.33.4: Google Earth no vuelve a mandar su vista después de un vuelo
    pedido por el enlace. Por eso las cruces de cada pieza viajan con el
    vuelo (por /camara) en su lugar previsto, y la pieza está lista cuando
    la foto se aquieta y muestra las cuatro cruces con la forma que deben
    tener. La foto se ubica por esas cruces: la cámara no necesita quedar
    exactamente donde se pidió.

    ``estados``: uno por fotograma ("" pendiente, "actual", "ok", "falla"),
    para la barra de fotogramas de la ventanita."""

    def __init__(self, servidor: Servidor, foto, aviso=None, paso: float = 1.0,
                 quietas: int = 3, tope_quieta: float = 60.0, tope_vuelo: float = 30.0,
                 reintento: float = 8.0) -> None:
        self.srv = servidor
        self.foto = foto
        self.aviso = aviso or (lambda _t, _f=None: None)
        self.paso = paso
        self.quietas = quietas
        self.tope_quieta = tope_quieta
        self.tope_vuelo = tope_vuelo          # para que Google Earth se lleve el vuelo
        self.reintento = reintento
        self.cancelar = threading.Event()
        self.original = None          # la vista de antes, para devolverla
        self.plan = None              # el del último mosaico (la altura que se usó)
        self.faltan = []              # (fila, col) de las piezas que no salieron
        self.ultimo_error = ""
        self.estados = []             # 3.33.4: la barra de fotogramas

    # -- esperas
    def _esperar(self, cond, tope: float, paso: float | None = None) -> bool:
        t0 = time.time()
        while time.time() - t0 < tope:
            if self.cancelar.is_set():
                raise Cancelado("Cancelado.")
            if cond():
                return True
            time.sleep(paso or self.paso / 4)
        return False

    def vista_actual(self):
        vista, _t, _m = self.srv.ultima()
        if vista is None:
            raise GE.GoogleEarthError("Google Earth todavía no mandó su vista. Abrí Google Earth "
                                      "con GeoCAD (menú GeoCAD > Google Earth) y movelo un poco.")
        return vista

    def _estado(self, i: int, cual: str) -> None:
        if 0 <= i < len(self.estados):
            self.estados[i] = cual

    def _entregar(self, marcas, vuelo=None) -> None:
        """Pone las cruces (y el vuelo) y espera a que Google Earth se los
        lleve por /camara. Sin enlace: error; si tarda: Reintentable."""
        t0 = time.time()
        with self.srv.cerrojo:
            self.srv.cruces = list(marcas) if marcas is not None else None
        if vuelo is not None:
            self.srv.volar(*vuelo)

        def listo():
            ok = self.srv.marcas_servidas > t0 if marcas else True
            return ok and (self.srv.t_entregado > t0 if vuelo is not None else True)

        if self._esperar(listo, self.tope_vuelo):
            registrar("entregado" + (" el vuelo" if vuelo else "") + (" y las cruces" if marcas else "")
                      + f" en {time.time() - t0:.1f} s")
            return
        if not self.srv.conectado(max(20.0, self.tope_vuelo)):
            raise GE.GoogleEarthError("Se cortó el enlace con Google Earth: tocá «Abrir Google Earth "
                                      "con GeoCAD» en esta ventana.")
        raise Reintentable(f"Google Earth no pidió el vuelo en {self.tope_vuelo:.0f} s (está "
                           "ocupado cargando).")

    def _foto_quieta(self, etapa: str = "", resto: str = "", marcas=None):
        """Fotos cada ``paso`` hasta que ``quietas`` seguidas casi no cambian
        y se ven las cuatro cruces (la imagen termina de cargar sola) con la
        forma de ``marcas`` (si no, la cámara todavía no llegó)."""
        import numpy as np

        previa, iguales, t0, ultimo = None, 0, time.time(), None
        while time.time() - t0 < self.tope_quieta:
            if self.cancelar.is_set():
                raise Cancelado("Cancelado.")
            self.aviso(f"{etapa}esperando que cargue la imagen... {time.time() - t0:.0f} s{resto}")
            a = self.foto()
            if previa is not None and a.shape == previa.shape \
                    and np.abs(a.astype(np.int16) - previa).mean() < 0.3:
                iguales += 1
            else:
                iguales = 0
            previa = a.astype(np.int16)
            if iguales >= self.quietas:
                try:
                    det = GE.detectar(a)
                    if marcas and not GE.forma_coincide(det, marcas):
                        raise GE.GoogleEarthError("Las cruces todavía no están donde deben "
                                                  "(Google Earth no terminó de llegar).")
                    registrar(f"foto lista en {time.time() - t0:.1f} s")
                    return a
                except GE.GoogleEarthError as exc:
                    ultimo = exc
            time.sleep(self.paso)
        registrar(f"foto sin cruces en {self.tope_quieta:.0f} s: {ultimo}")
        if ultimo is not None:
            raise Reintentable(str(ultimo))
        raise Reintentable("La imagen de Google Earth no se terminó de cargar "
                           f"en {self.tope_quieta:.0f} s.")

    def _una(self, lon: float, lat: float, rango: float, marcas, etapa: str = "", resto: str = ""):
        self._entregar(marcas, (lon, lat, rango))
        a = self._foto_quieta(etapa, resto, marcas)
        return a, list(marcas)

    # -- las dos calidades
    def pantalla(self, volar: bool = False):
        """[(foto, marcas, fila, col)] de lo que se ve. Si la vista está
        derecha, las cruces se ponen sin mover la cámara; si no (o al
        reintentar), se endereza con un vuelo sobre el mismo punto."""
        v = self.vista_actual()
        self.original = v
        self.estados = ["actual"]
        try:
            vv = GE.vista_vertical(v)
            marcas = GE.marcas_de_bbox(vv.oeste, vv.sur, vv.este, vv.norte)
            if v.vertical and not volar:
                self.aviso("1/5 Poniendo las cruces...", 0.05)
                self._entregar(marcas)
            else:
                self.aviso("1/5 Enderezando la vista y poniendo las cruces...", 0.05)
                self._entregar(marcas, (v.lon, v.lat, v.rango))
            self.aviso("2/5 Cruces puestas; esperando que cargue la imagen...", 0.2)
            a = self._foto_quieta("2/5 Cruces puestas; ", "", marcas)
            self._estado(0, "ok")
            self.aviso("3/5 Foto sacada; quitando las cruces...", 0.6)
            return [(a, marcas, 0, 0)]
        except Reintentable:
            self._estado(0, "falla")
            raise
        finally:
            self._quitar_cruces()

    def mosaico(self, a_planas, a_geo, rango: float, zona=None):
        """[(foto, marcas, fila, col)] de cada pieza; al final, la vista vuelve.
        Con ``zona`` cubre ese rectángulo (lo que se ve en IngeCAD o QGIS)."""
        v = self.vista_actual()
        vv = GE.vista_vertical(v)
        plan = GE.plan_mosaico(vv, a_planas, a_geo, rango, zona=zona)
        self.plan = plan
        self.original = v
        piezas = {}
        self.faltan = []
        total = len(plan.centros)
        self.estados = [""] * total
        self.aviso(f"1/5 Preparando {total} pieza(s) a {plan.rango:g} m...", 0.02)
        t0 = time.time()
        try:
            # 3.33.3 (Fernando: «ni siquiera entregó un resultado parcial»):
            # una pieza que no sale no frena el mosaico: se sigue con las
            # demás, al final se vuelve a buscar las que faltaron y, si
            # alguna no sale, se entrega lo que hay (con su hueco)
            pendientes = list(enumerate(plan.centros, 1))
            for vuelta, intentos in ((1, 1), (2, INTENTOS)):
                quedan = []
                for i, (n, (fila, col, lon, lat)) in enumerate(pendientes):
                    resto = ""
                    hechas = len(piezas)
                    if hechas:                          # lo que falta, por lo que vienen tardando
                        falta = (time.time() - t0) / hechas * (len(pendientes) - i)
                        resto = f" · faltan unos {falta:.0f} s"
                    etapa = (f"2/5 Pieza {n} de {total}: " if vuelta == 1 else
                             f"2/5 Repitiendo la pieza {n} de {total}: ")
                    self.aviso(f"{etapa}volando...{resto}", 0.05 + 0.75 * hechas / total)
                    self._estado(n - 1, "actual")
                    marcas = GE.marcas_de_bbox(*GE.bbox_en(vv, lon, lat, plan.rango))
                    try:
                        piezas[n] = con_reintentos(
                            lambda k, lon=lon, lat=lat, marcas=marcas, etapa=etapa, resto=resto:
                            self._una(lon, lat, plan.rango, marcas,
                                      etapa if k == 1 else f"{etapa}(otra vez, {k} de {intentos}) ",
                                      resto), self.aviso, self.cancelar, intentos) + (fila, col)
                        self._estado(n - 1, "ok")
                    except Cancelado:
                        raise
                    except GE.GoogleEarthError as exc:
                        self._estado(n - 1, "falla")
                        if not self.srv.conectado(max(20.0, self.tope_vuelo)):
                            raise                       # sin enlace no tiene sentido seguir
                        self.ultimo_error = str(exc)
                        quedan.append((n, (fila, col, lon, lat)))
                pendientes = quedan
                if not pendientes:
                    break
            self.faltan = [(fila, col) for _n, (fila, col, _lon, _lat) in pendientes]
            if not piezas:
                raise Reintentable(f"No salió ninguna pieza del mosaico ({self.ultimo_error})")
            return [piezas[n] for n in sorted(piezas)]
        finally:
            self.aviso("3/5 Volviendo a la vista de antes...", 0.82)
            self.devolver()

    def _quitar_cruces(self) -> None:
        with self.srv.cerrojo:
            self.srv.cruces = None
            self.srv.armado = False

    def devolver(self) -> bool:
        """La vista vuelve a donde estaba (norte arriba y vertical), sin las
        cruces de la captura."""
        self._quitar_cruces()
        v = self.original
        if v is None or not GE.posicion_valida(v.lon, v.lat, v.rango):
            return False
        guardado = self.cancelar.is_set()
        self.cancelar.clear()                            # aunque se haya cancelado
        try:
            self._entregar(None, (v.lon, v.lat, v.rango))
            return True
        except GE.GoogleEarthError:
            return False
        finally:
            if guardado:
                self.cancelar.set()


def procesar(fotos, crs: str, progreso=None, cancelado=None, zona=None, completo: bool = True):
    """De las fotos a la imagen: (imagen, Marco, piezas, costuras). Con
    ``zona`` la imagen se recorta a ese rectángulo (en ``crs``). Sin
    ``completo`` (faltaron piezas) el marco abarca todas las que hay y los
    huecos quedan en blanco, en vez de achicar la imagen."""
    a_planas, _a_geo = GE.transformadores(crs)
    try:
        piezas = [GE.pieza_de_foto(a, marcas, a_planas, fila, col) for a, marcas, fila, col in fotos]
    except Cancelado:
        raise
    except GE.GoogleEarthError as exc:                  # cruces mal vistas: otra foto
        raise Reintentable(str(exc)) from exc
    m = GE.marco(piezas) if completo else GE.marco_todo(piezas)
    if zona is not None:
        m = GE.recortar_marco(m, zona)
    im = GE.componer(piezas, m, progreso=progreso, cancelado=cancelado, huecos=not completo)
    cost = GE.costuras(piezas, m.res) if len(piezas) > 1 else []
    return im, m, piezas, cost
