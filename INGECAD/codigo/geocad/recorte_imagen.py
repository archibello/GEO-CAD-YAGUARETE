"""Recortar una imagen con los agarres (3.35.0 y 3.36.0, pedidos de Fernando).

Los agarres de una imagen en IngeCAD son sus cuatro esquinas y la escalan
desde la esquina opuesta. Con teclas al SOLTAR el agarre, GeoCAD recorta en
vez de escalar:

  Ctrl          (3.35.0) en una esquina de una imagen rectangular: la esquina
                queda donde se suelta y los dos lados que llegan a ella la
                siguen; recorta en rectángulo. Hacia afuera se vuelve a abrir,
                hasta el tamaño de la original.
  Shift+Ctrl    (3.36.0) en una esquina: sólo esa esquina se mueve; el
                recorte pasa a ser un polígono (para seguir el borde torcido
                del papel). Soltada sobre la esquina vecina, la borra.
  Ctrl          (3.36.0) en el agarre del medio de un lado: sólo ese lado se
                mueve, paralelo a sí mismo (como los 8 agarres de la
                Transformación libre de Photoshop).
  Alt+clic      (3.36.0) sobre un lado de la imagen elegida: agrega una
                esquina ahí, al instante, para que el recorte siga el borde
                sin cortar parte de la imagen (con Alt, al pasar sobre el
                lado se ve el agarre donde caería). GNOME mueve las
                ventanas con Super, así que Alt+clic llega a IngeCAD.

En un recorte que ya es un polígono, Ctrl mueve la esquina sola, como
Shift+Ctrl. La imagen no se mueve ni cambia de escala: lo que queda fuera
del recorte se saca o queda transparente.

IngeCAD no dibuja el recorte que el DWG guarda en la imagen (muestra la
imagen entera), así que GeoCAD arma una COPIA (los mismos píxeles, sin
remuestrear; fuera del polígono, transparente) en «<dibujo>_imagenes», como
ASPECTOIMAGEN, y el dibujo pasa a usarla. El polígono queda además como
recorte del DWG: IngeCAD dibuja el marco con su forma, y AutoCAD lo recorta
igual. La original no se toca. En la imagen quedan anotados (XDATA) la
original y el polígono, en píxeles de la original, para seguir recortando
o volver a abrir. Un U por recorte. Mientras se arrastra con Ctrl la imagen
queda quieta.

El recorte es una OPERACIÓN (pedido de Fernando, 24/10/2026: recortar es
descartar lo que queda fuera del perímetro útil): se abre con el primer
recorte y, mientras dura, todo se ajusta y se recupera como arriba. ENTER
(sin comando activo) la termina: el lienzo GIRA CON EL PAPEL (el rectángulo
de menor área alrededor del polígono), la imagen se rehace una sola vez, lo
de afuera queda descartado y se borra la marca de la original (ya no se
reabre). ESC la cancela entera: la imagen vuelve a como estaba antes del
primer recorte. Un U deshace el Enter o el Esc. Mientras la operación está
abierta, GeoCAD toma ese Enter y ese Esc enganchándose sólo en la ventana de
IngeCAD que la abrió (su dispatcher y su controlador, no las clases).

Va con el módulo «georref» (Imágenes georreferenciadas). Las cuentas no
usan Qt.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

APPID = "GEOCAD_RECORTE"
MARCA = "GEOCAD_RECORTE_1"         # 3.35.0: la ventana (rectángulo)
MARCA2 = "GEOCAD_RECORTE_2"        # 3.36.0: el polígono
ROL_MEDIO = "geocad_medio"         # el punto de un lado donde se agrega una esquina
ROL_LADO = "geocad_lado"           # el agarre del medio de un lado

_activo_cache = [0.0, False]
#: mientras GeoCAD suelta el agarre él mismo, el agarre no escala
_soltando = [False]


class RecorteError(Exception):
    pass


def _activo() -> bool:
    """Módulo georref prendido (se relee el archivo cada 2 s como mucho)."""
    ahora = time.monotonic()
    if ahora - _activo_cache[0] > 2.0:
        _activo_cache[0] = ahora
        from . import modulos
        _activo_cache[1] = modulos.activo("ingecad", "georref")
    return _activo_cache[1]


def _teclas() -> tuple:
    """(Ctrl, Shift, Alt) apretadas. Sin Qt (pruebas), ninguna."""
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return False, False, False
    if QtWidgets.QApplication.instance() is None:
        return False, False, False
    m = QtWidgets.QApplication.keyboardModifiers()
    return (bool(m & QtCore.Qt.ControlModifier), bool(m & QtCore.Qt.ShiftModifier),
            bool(m & QtCore.Qt.AltModifier))


def _ctrl() -> bool:
    return _teclas()[0]


def _shift() -> bool:
    return _teclas()[1]


def _alt() -> bool:
    return _teclas()[2]


def _recortando(entity) -> bool:
    try:
        return entity.dxftype() == "IMAGE" and (_soltando[0] or (_activo() and _ctrl()))
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ la marca
def _texto(tags) -> str:
    return "".join(str(v) for c, v in tags if c == 1000)


def leer(img):
    """(original, ventana, polígono) si la imagen es un recorte de GeoCAD:
    la ventana (x0, y0, x1, y1) y el polígono [(x, y), ...] en píxeles de la
    original (arriba a la izquierda = 0, 0)."""
    try:
        tags = list(img.get_xdata(APPID))
    except Exception:  # noqa: BLE001 -- sin XDATA
        return None
    if not tags or tags[0][0] != 1000:
        return None
    if tags[0][1] == MARCA2:
        try:
            n = int(tags[1][1])
            nums = [float(v) for c, v in tags[2:2 + 2 * n]]
            poligono = [(nums[2 * i], nums[2 * i + 1]) for i in range(n)]
        except (IndexError, TypeError, ValueError):
            return None
        if n < 3 or len(nums) < 2 * n:
            return None
        return _texto(tags[2 + 2 * n:]), caja(poligono), poligono
    if tags[0][1] == MARCA and len(tags) >= 3:           # de la 3.35.0
        try:
            v = tuple(int(n) for n in json.loads(tags[1][1]))
        except (TypeError, ValueError):
            return None
        if len(v) != 4:
            return None
        return _texto(tags[2:]), v, rectangulo(v)
    return None


def etiquetas(original, poligono) -> list:
    """Marca, cantidad de esquinas, sus coordenadas y la original en trozos
    de 200 caracteres (el límite de un texto de XDATA es 255)."""
    original = str(original)
    trozos = [original[i:i + 200] for i in range(0, len(original), 200)] or [""]
    tags = [(1000, MARCA2), (1071, len(poligono))]
    for x, y in poligono:
        tags += [(1040, float(x)), (1040, float(y))]
    return tags + [(1000, t) for t in trozos]


def _xdata(img):
    try:
        return list(img.get_xdata(APPID))
    except Exception:  # noqa: BLE001
        return None


def _poner_xdata(img, tags) -> None:
    if tags:
        doc = img.doc
        if doc is not None and APPID not in doc.appids:
            doc.appids.add(APPID)
        img.set_xdata(APPID, tags)
    elif img.has_xdata(APPID):
        img.discard_xdata(APPID)


# ------------------------------------------------------------------ polígonos
def rectangulo(v) -> list:
    """Las cuatro esquinas de la ventana: arriba izquierda, arriba derecha,
    abajo derecha, abajo izquierda (el orden de las esquinas de ezdxf)."""
    x0, y0, x1, y1 = v
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def caja(poligono) -> tuple:
    import math
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    return (math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys)))


def es_rectangulo(poligono) -> bool:
    return len(poligono) == 4 and [tuple(p) for p in poligono] == rectangulo(caja(poligono))


def _normalizar(poligono) -> list:
    """Cuatro esquinas que forman un rectángulo derecho (aunque dadas vuelta):
    en el orden de siempre."""
    if len(poligono) == 4:
        xs = sorted({p[0] for p in poligono})
        ys = sorted({p[1] for p in poligono})
        if len(xs) == 2 and len(ys) == 2 and \
                sorted(map(tuple, poligono)) == sorted(rectangulo((xs[0], ys[0], xs[1], ys[1]))):
            return rectangulo((xs[0], ys[0], xs[1], ys[1]))
    return [tuple(p) for p in poligono]


def _area(poligono) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(poligono, poligono[1:] + poligono[:1]))) / 2


def _se_cortan(a, b, c, d) -> bool:
    def lado(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = lado(c, d, a), lado(c, d, b), lado(a, b, c), lado(a, b, d)
    return d1 * d2 < 0 and d3 * d4 < 0


def simple(poligono) -> bool:
    """¿Ningún lado cruza a otro?"""
    n = len(poligono)
    lados = [(poligono[i], poligono[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue                      # vecinos por la vuelta
            if _se_cortan(*lados[i], *lados[j]):
                return False
    return True


def nuevo_poligono(poligono, k: int, punto, modo: str) -> list:
    """El recorte después de soltar. ``modo``: «rect» mueve la esquina ``k`` y
    los lados que llegan a ella (Ctrl en un rectángulo), «libre» sólo la
    esquina (Shift+Ctrl; sobre la vecina, la borra), «agregar» pone una
    esquina nueva en ``punto`` entre la ``k`` y la siguiente, «lado» corre el
    lado que va de la ``k`` a la siguiente, paralelo, hasta ``punto``."""
    p = [tuple(v) for v in poligono]
    n = len(p)
    punto = (float(punto[0]), float(punto[1]))
    if modo == "agregar":
        p.insert(k + 1, punto)
    elif modo == "lado":
        (ax, ay), (bx, by) = p[k], p[(k + 1) % n]
        largo = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if largo <= 0:
            raise RecorteError("el lado no tiene largo")
        nx, ny = -(by - ay) / largo, (bx - ax) / largo
        dist = (punto[0] - (ax + bx) / 2) * nx + (punto[1] - (ay + by) / 2) * ny
        p[k] = (round(ax + dist * nx, 2), round(ay + dist * ny, 2))
        p[(k + 1) % n] = (round(bx + dist * nx, 2), round(by + dist * ny, 2))
    elif modo == "rect":
        anterior, siguiente = (k - 1) % n, (k + 1) % n
        p[k] = punto
        if k % 2 == 0:       # arriba izquierda y abajo derecha
            p[anterior] = (punto[0], p[anterior][1])
            p[siguiente] = (p[siguiente][0], punto[1])
        else:                # arriba derecha y abajo izquierda
            p[anterior] = (p[anterior][0], punto[1])
            p[siguiente] = (punto[0], p[siguiente][1])
    else:
        vecinas = (p[(k - 1) % n], p[(k + 1) % n])
        if n > 3 and any(abs(v[0] - punto[0]) <= 1 and abs(v[1] - punto[1]) <= 1 for v in vecinas):
            del p[k]                          # sobre la vecina: se borra
        else:
            p[k] = punto
    # sin esquinas repetidas una tras otra
    p = [v for i, v in enumerate(p) if v != p[i - 1]] if len(p) > 1 else p
    p = _normalizar(p)
    if len(p) < 3 or _area(p) < 1:
        raise RecorteError("el recorte deja la imagen sin nada")
    if not simple(p):
        raise RecorteError("los lados del recorte se cruzan")
    return p


# ------------------------------------------------------------------ las cuentas
def _vec(p):
    return float(p[0]), float(p[1])


def _local(img, punto):
    """(s, t) del punto en el marco entero de la imagen: 0..1 de izquierda a
    derecha (s) y de abajo hacia arriba (t)."""
    from . import georref as G
    w, h = G.tamano(img)
    ix, iy = _vec(img.dxf.insert)
    ux, uy = _vec(img.dxf.u_pixel)
    vx, vy = _vec(img.dxf.v_pixel)
    ax, ay, bx, by = ux * w, uy * w, vx * h, vy * h
    det = ax * by - ay * bx
    if abs(det) < 1e-18:
        raise RecorteError("la imagen no tiene tamaño")
    dx, dy = punto[0] - ix, punto[1] - iy
    return (dx * by - dy * bx) / det, (ax * dy - ay * dx) / det


def a_pixel(img, ventana, punto) -> tuple:
    """El punto del dibujo en píxeles de la original."""
    from . import georref as G
    w, h = G.tamano(img)
    s, t = _local(img, punto)
    return ventana[0] + s * w, ventana[1] + (1 - t) * h


def a_dibujo(img, ventana, pixel) -> tuple:
    """El píxel de la original (arriba a la izquierda = 0, 0) en el dibujo."""
    from . import georref as G
    _w, h = G.tamano(img)
    ix, iy = _vec(img.dxf.insert)
    ux, uy = _vec(img.dxf.u_pixel)
    vx, vy = _vec(img.dxf.v_pixel)
    c, f = pixel[0] - ventana[0], h - (pixel[1] - ventana[1])
    return ix + c * ux + f * vx, iy + c * uy + f * vy


def estado(img, document=None):
    """(original, ventana, polígono, ancho y alto de la original)."""
    from . import georref as G
    marca = leer(img)
    if marca is not None:
        original, ventana, poligono = marca
        ancho, alto = _tamano_archivo(original)
        return Path(original), ventana, poligono, ancho, alto
    ruta = G.archivo_imagen(img, document)
    if ruta is None:
        raise RecorteError("la imagen no tiene archivo")
    w, h = (int(round(n)) for n in G.tamano(img))
    return Path(ruta), (0, 0, w, h), rectangulo((0, 0, w, h)), w, h


def _tamano_archivo(ruta):
    from . import aspecto
    Image = aspecto._pil()
    try:
        with Image.open(str(ruta)) as im:
            return im.size
    except Exception as exc:  # noqa: BLE001
        raise RecorteError(f"no se encuentra la original {Path(ruta).name}") from exc


def esquinas(img) -> list:
    """Las esquinas del recorte en el dibujo, en el orden del polígono (sin
    recorte de GeoCAD, las cuatro de la imagen)."""
    marca = leer(img)
    if marca is not None:
        _o, ventana, poligono = marca
    else:
        from . import georref as G
        ventana = (0, 0) + tuple(int(round(n)) for n in G.tamano(img))
        poligono = rectangulo(ventana)
    return [a_dibujo(img, ventana, p) for p in poligono]


def agarres(img) -> list:
    """Los agarres de la imagen: sus esquinas (rol «corner», en el orden del
    polígono; sin recorte, las cuatro de IngeCAD en su orden) y el medio de
    cada lado (rol ROL_LADO)."""
    puntos = esquinas(img)
    n = len(puntos)
    return ([(x, y, "corner") for x, y in puntos]
            + [((puntos[i][0] + puntos[(i + 1) % n][0]) / 2,
                (puntos[i][1] + puntos[(i + 1) % n][1]) / 2, ROL_LADO) for i in range(n)])


def lado_cercano(img, punto, tol: float):
    """(número de lado, punto sobre el lado) del lado del recorte más cerca
    de ``punto``, a no más de ``tol``; None si no hay."""
    puntos = esquinas(img)
    n, mejor = len(puntos), None
    for i in range(n):
        (ax, ay), (bx, by) = puntos[i], puntos[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        largo = dx * dx + dy * dy
        if largo <= 0:
            continue
        u = max(0.0, min(1.0, ((punto[0] - ax) * dx + (punto[1] - ay) * dy) / largo))
        px, py = ax + u * dx, ay + u * dy
        d = ((px - punto[0]) ** 2 + (py - punto[1]) ** 2) ** 0.5
        if d <= tol and 0 < u < 1 and (mejor is None or d < mejor[0]):
            mejor = (d, i, (px, py))
    return None if mejor is None else (mejor[1], mejor[2])


def nombre_copia(carpeta, original, poligono) -> Path:
    """<original>_recorte_<x>_<y>_<ancho>x<alto>[_<huella>].png: el mismo
    recorte de la misma original es siempre el mismo archivo (U vuelve a uno
    que existe)."""
    x0, y0, x1, y1 = caja(poligono)
    nombre = f"{Path(original).stem}_recorte_{x0}_{y0}_{x1 - x0}x{y1 - y0}"
    if not es_rectangulo(poligono):
        huella = hashlib.sha1(json.dumps([list(p) for p in poligono]).encode()).hexdigest()[:8]
        nombre += f"_{huella}"
    return Path(carpeta) / f"{nombre}.png"


def guardar_copia(original, poligono, ruta_dibujo):
    """Recorta la original (los mismos píxeles; fuera del polígono,
    transparente) y la guarda junto al dibujo: (ruta, tiene transparencia)."""
    from . import aspecto, pegarimagen
    carpeta = pegarimagen.carpeta_destino(ruta_dibujo)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = nombre_copia(carpeta, original, poligono)
    im = aspecto.abrir(original)
    transparente = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    ventana = caja(poligono)
    if not es_rectangulo(poligono):
        transparente = True
    if not ruta.exists():
        hecha = im.crop(ventana)
        if not es_rectangulo(poligono):
            from PIL import Image, ImageChops, ImageDraw
            hecha = hecha.convert("RGBA")
            mascara = Image.new("L", hecha.size, 0)
            ImageDraw.Draw(mascara).polygon(
                [(x - ventana[0], y - ventana[1]) for x, y in poligono], fill=255)
            hecha.putalpha(ImageChops.multiply(hecha.getchannel("A"), mascara))
        elif hecha.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
            hecha = hecha.convert("RGBA" if transparente else "RGB")
        aspecto.guardar_png(hecha, ruta)
    return ruta, transparente


def preparar(img, indice: int, punto, document=None, libre: bool = False, rol: str = "corner"):
    """El comando que recorta ``img`` al soltar la esquina ``indice`` (en el
    orden del polígono) en ``punto`` (ya con las referencias), o RecorteError.
    ``libre``: Shift+Ctrl, la esquina sola. Con ``rol`` ROL_MEDIO, agrega una
    esquina en ``punto`` sobre el lado ``indice``."""
    from ezdxf.math import Matrix44
    from . import georref as G
    original, ventana, poligono, ancho, alto = estado(img, document)
    n = len(poligono)
    x, y = a_pixel(img, ventana, punto)
    p = (float(min(ancho, max(0, round(x)))), float(min(alto, max(0, round(y)))))
    if rol == ROL_MEDIO:                 # ``indice``: el número de lado
        nuevo = nuevo_poligono(poligono, indice % n, p, "agregar")
    elif rol == ROL_LADO:                # el agarre ``indice`` es el medio del lado indice - n
        nuevo = [(min(ancho, max(0.0, vx)), min(alto, max(0.0, vy))) for vx, vy in
                 nuevo_poligono(poligono, (indice - n) % n, (x, y), "lado")]
    else:
        if indice >= n:
            raise RecorteError("agarre desconocido")
        modo = "rect" if (not libre and es_rectangulo(poligono)) else "libre"
        nuevo = nuevo_poligono(poligono, indice, p, modo)
    if nuevo == [tuple(v) for v in poligono]:
        raise RecorteError("la imagen queda igual")
    nueva = caja(nuevo)
    w, h = G.tamano(img)
    # la esquina inferior izquierda de la caja nueva, en el marco de ahora
    s = (nueva[0] - ventana[0]) / w
    t = 1 - (nueva[3] - ventana[1]) / h
    ix, iy = _vec(img.dxf.insert)
    ux, uy = _vec(img.dxf.u_pixel)
    vx, vy = _vec(img.dxf.v_pixel)
    nx, ny = ix + s * ux * w + t * vx * h, iy + s * uy * w + t * vy * h
    matriz = Matrix44.translate(nx - ix, ny - iy, 0)
    tamano = (nueva[2] - nueva[0], nueva[3] - nueva[1])
    borde = None
    if es_rectangulo(nuevo) and nueva == (0, 0, ancho, alto):
        copia, transparente, marca = original, False, None      # de vuelta entera
    else:
        copia, transparente = guardar_copia(original, nuevo, getattr(document, "path", None))
        marca = etiquetas(original, nuevo)
        if not es_rectangulo(nuevo):
            # el recorte del DWG, en píxeles de la copia (ezdxf: arriba a la
            # izquierda, el borde del píxel en -0,5)
            borde = [(x - nueva[0] - 0.5, y - nueva[1] - 0.5) for x, y in nuevo]
    return RecorteCommand(img, matriz, copia, tamano, transparente, marca, borde)


_clase_cache: list = []


def _clase():
    """RecorteCommand hereda de GeorrefCommand (que necesita IngeCAD): se
    arma la primera vez que se usa."""
    if _clase_cache:
        return _clase_cache[0]
    from . import georref as G

    class RecorteCommand(G.GeorrefCommand):
        """La imagen recortada: otra copia, otro tamaño, la esquina en su
        lugar y el polígono como recorte, en un solo paso (U lo deshace
        entero, la marca incluida)."""

        def __init__(self, img, matriz, copia, tamano, transparente, marca, borde=None) -> None:
            super().__init__(img, matriz, copia=copia, tamano=tamano, transparente=transparente)
            self.name = "RECORTE"
            self.marca = marca
            self.borde = borde
            self._marca_antes = None
            #: Enter o Esc: la operación que cierra (U la vuelve a abrir)
            self.operacion = None

        def do(self, document) -> None:
            self._marca_antes = _xdata(self.img)
            super().do(document)
            if self.borde:
                self.img.set_boundary_path(self.borde)
            _poner_xdata(self.img, self.marca)
            if self.operacion is not None:
                _cerrar(self.operacion)

        def undo(self, document) -> None:
            super().undo(document)
            _poner_xdata(self.img, self._marca_antes)
            if self.operacion is not None:
                _reabrir(self.operacion)

    _clase_cache.append(RecorteCommand)
    return RecorteCommand


def RecorteCommand(*args, **kwargs):  # noqa: N802 -- se usa como una clase
    return _clase()(*args, **kwargs)


# ------------------------------------------------------------------ el lienzo final (Enter)
def envolvente(puntos) -> list:
    """La envolvente convexa (cadena monótona), sin puntos repetidos ni
    alineados."""
    ps = sorted({(float(x), float(y)) for x, y in puntos})
    if len(ps) < 3:
        return ps

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    abajo, arriba = [], []
    for p in ps:
        while len(abajo) >= 2 and giro(abajo[-2], abajo[-1], p) <= 0:
            abajo.pop()
        abajo.append(p)
    for p in reversed(ps):
        while len(arriba) >= 2 and giro(arriba[-2], arriba[-1], p) <= 0:
            arriba.pop()
        arriba.append(p)
    return abajo[:-1] + arriba[:-1]


def rectangulo_minimo(puntos) -> tuple:
    """(origen, ángulo, ancho, alto) del rectángulo de menor área que
    contiene los puntos: calibres rotantes sobre la envolvente convexa (un
    lado del rectángulo va sobre un lado de la envolvente). El ángulo, en
    radianes, entre -45° y 45° (el más cerca de cero); el ancho va a lo largo
    de (cos, sen) y el alto de (-sen, cos), desde el origen. En píxeles."""
    casco = envolvente(puntos)
    if len(casco) < 3:
        raise RecorteError("el recorte deja la imagen sin nada")
    mejor = None
    for i in range(len(casco)):
        a, b = casco[i], casco[(i + 1) % len(casco)]
        ang = (math.atan2(b[1] - a[1], b[0] - a[0]) + math.pi / 4) % (math.pi / 2) - math.pi / 4
        if abs(ang) < 1e-9:
            ang = 0.0
        c, s = math.cos(ang), math.sin(ang)
        us = [x * c + y * s for x, y in casco]
        vs = [-x * s + y * c for x, y in casco]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if mejor is None or area < mejor[0] - 1e-6 or (area <= mejor[0] + 1e-6 and abs(ang) < abs(mejor[1])):
            mejor = (area, ang, min(us), max(us), min(vs), max(vs))
    _area_r, ang, u0, u1, v0, v1 = mejor
    c, s = math.cos(ang), math.sin(ang)
    origen = (u0 * c - v0 * s, u0 * s + v0 * c)
    if ang == 0.0:
        origen = tuple(round(n, 9) for n in origen)
    return origen, ang, u1 - u0, v1 - v0


def _entero(n: float) -> int:
    r = round(n)
    return max(1, int(r) if abs(n - r) < 0.01 else math.ceil(n))


def preparar_final(img, document=None):
    """El comando que termina la operación (Enter): la imagen rehecha UNA vez
    desde la original, en el rectángulo de menor área alrededor del polígono
    (el lienzo gira con el papel), sin moverse en el dibujo; fuera del
    polígono, transparente (si no es un rectángulo); sin la marca."""
    from . import aspecto, pegarimagen
    from . import georref as G
    from PIL import Image, ImageChops, ImageDraw
    marca = leer(img)
    if marca is None:
        raise RecorteError("la imagen no está recortada")
    original, ventana, poligono = marca
    (ox, oy), ang, ancho_r, alto_r = rectangulo_minimo(poligono)
    ancho, alto = _entero(ancho_r), _entero(alto_r)
    c, s = math.cos(ang), math.sin(ang)
    rect = abs(_area(poligono) - ancho_r * alto_r) <= 1.0 + 1e-6 * ancho_r * alto_r
    # el polígono en píxeles de la imagen nueva
    nuevo = [((x - ox) * c + (y - oy) * s, -(x - ox) * s + (y - oy) * c) for x, y in poligono]
    try:
        im = aspecto.abrir(original)
    except Exception as exc:  # noqa: BLE001
        raise RecorteError(f"no se encuentra la original {Path(original).name}") from exc
    transparente = (not rect) or im.mode in ("RGBA", "LA", "PA") or \
        (im.mode == "P" and "transparency" in im.info)
    carpeta = pegarimagen.carpeta_destino(getattr(document, "path", None))
    carpeta.mkdir(parents=True, exist_ok=True)
    huella = hashlib.sha1(json.dumps([[list(p) for p in poligono], ancho, alto]).encode()).hexdigest()[:8]
    ruta = Path(carpeta) / f"{Path(original).stem}_lienzo_{ancho}x{alto}_{huella}.png"
    if not ruta.exists():
        modo = "RGBA" if transparente else "RGB"
        base = im if im.mode == modo else im.convert(modo)
        if ang == 0.0 and float(ox).is_integer() and float(oy).is_integer():
            hecha = base.crop((int(ox), int(oy), int(ox) + ancho, int(oy) + alto))   # derecho: sin remuestrear
        else:
            bicubica = getattr(Image, "Resampling", Image).BICUBIC
            hecha = base.transform((ancho, alto), Image.AFFINE, (c, -s, ox, s, c, oy),
                                   resample=bicubica,
                                   fillcolor=(0, 0, 0, 0) if transparente else (255, 255, 255))
        if not rect:
            mascara = Image.new("L", hecha.size, 0)
            ImageDraw.Draw(mascara).polygon(nuevo, fill=255)
            hecha.putalpha(ImageChops.multiply(hecha.getchannel("A"), mascara))
        aspecto.guardar_png(hecha, ruta)
    # dónde queda en el dibujo: el píxel (x, y) de la original no se mueve
    def dibujo(px, py):
        return a_dibujo(img, ventana, (px, py))
    arriba = dibujo(ox, oy)
    a_lo_ancho = dibujo(ox + c, oy + s)
    a_lo_alto = dibujo(ox - s, oy + c)
    u = (a_lo_ancho[0] - arriba[0], a_lo_ancho[1] - arriba[1])
    v = (arriba[0] - a_lo_alto[0], arriba[1] - a_lo_alto[1])          # hacia arriba
    coef = (arriba[0], u[0], v[0], arriba[1], u[1], v[1])
    borde = None if rect else [(x - 0.5, y - 0.5) for x, y in nuevo]
    comando = RecorteCommand(img, G.matriz(img, coef, alto=alto), ruta, (ancho, alto),
                             transparente, None, borde)
    comando.angulo = math.degrees(ang)
    return comando


# ------------------------------------------------------------------ la operación (Enter / Esc)
#: las operaciones de recorte abiertas: (id del documento, handle) -> datos
_abiertas: dict = {}
#: el último tools.cancel() encontró a IngeCAD sin comando, agarre ni selección en curso
_esc_libre = [False]
AVISO = "Recortando: Enter termina (el lienzo gira con el papel y lo de afuera se descarta), Esc cancela."


def foto(img) -> dict:
    """Lo que hace falta para volver la imagen a como está ahora."""
    from . import georref as G
    d = img.dxf
    defi = img.image_def
    return {"def": defi, "archivo": str(defi.dxf.filename) if defi is not None else None,
            "coef": G.coef_imagen(img), "tamano": G.tamano(img),
            "transparente": bool(d.get("flags", 0) & img.USE_TRANSPARENCY),
            "borde": [(p[0], p[1]) for p in img.boundary_path] if d.get("clipping", 0) else None,
            "marca": _xdata(img)}


def _igual(a, b) -> bool:
    def norma(f):
        return (id(f["def"]), tuple(round(n, 9) for n in f["coef"]), tuple(f["tamano"]),
                f["borde"], f["marca"])
    return norma(a) == norma(b)


def preparar_cancelar(img, antes):
    """El comando que deja la imagen como en la foto ``antes`` (Esc)."""
    from . import georref as G
    comando = RecorteCommand(img, G.matriz(img, antes["coef"], alto=antes["tamano"][1]),
                             antes["archivo"], antes["tamano"], antes["transparente"],
                             antes["marca"], antes["borde"])
    if antes["def"] is not None and antes["def"].is_alive:
        comando._def_nuevo = antes["def"]           # el mismo IMAGEDEF de antes
    return comando


def _clave(documento, img) -> tuple:
    return id(documento), img.dxf.handle


def abrir(controlador, img) -> None:
    """Antes del primer recorte de ``img``: abre su operación (con la foto de
    cómo está) y engancha Enter y Esc en la ventana."""
    documento = controlador.window.document
    clave = _clave(documento, img)
    if clave not in _abiertas:
        _abiertas[clave] = {"clave": clave, "ctrl": controlador, "doc": documento,
                            "img": img, "antes": foto(img)}
    _enganchar(controlador)


def _cerrar(op) -> None:
    _abiertas.pop(op["clave"], None)
    if not any(o["ctrl"] is op["ctrl"] for o in _abiertas.values()):
        _desenganchar(op["ctrl"])


def _reabrir(op) -> None:
    _abiertas[op["clave"]] = op
    _enganchar(op["ctrl"])


def abiertas(controlador) -> list:
    """Las operaciones abiertas en el dibujo de la ventana."""
    documento = getattr(controlador.window, "document", None)
    out = []
    for clave, op in list(_abiertas.items()):
        if not op["img"].is_alive:
            _cerrar(op)
        elif op["doc"] is documento and op["img"].dxf.owner is not None:
            out.append(op)
    return out


def terminar(controlador) -> bool:
    """Enter: termina las operaciones abiertas en el dibujo (True si había)."""
    ops = abiertas(controlador)
    if not ops:
        return False
    for op in ops:
        img = op["img"]
        if leer(img) is None:                      # sin recorte (U o abierta hasta la original)
            _cerrar(op)
            _echo(controlador, "Recorte terminado: la imagen quedó entera.")
            continue
        try:
            comando = preparar_final(img, controlador.window.document)
        except RecorteError as exc:
            _echo(controlador, f"GeoCAD Yaguareté: no se termina el recorte, {exc}. "
                               "Esc lo cancela.")
            continue
        comando.operacion = op
        controlador._execute(comando)
        w, h = comando.tamano
        _echo(controlador, f"Recorte terminado: {int(w)} x {int(h)} píxeles, lienzo girado "
                           f"{comando.angulo:.2f}°; lo de afuera quedó descartado (U lo deshace).")
    return True


def cancelar(controlador) -> bool:
    """Esc: la imagen vuelve a como estaba antes del primer recorte (True si
    había una operación abierta)."""
    ops = abiertas(controlador)
    if not ops:
        return False
    for op in ops:
        img = op["img"]
        if _igual(foto(img), op["antes"]):
            _cerrar(op)
            continue
        comando = preparar_cancelar(img, op["antes"])
        comando.operacion = op
        controlador._execute(comando)
    _echo(controlador, "Recorte cancelado: la imagen volvió a como estaba (U lo deshace).")
    return True


def _enganchar(controlador) -> None:
    """Enter y Esc de ESTA ventana, sólo mientras dura la operación: se
    envuelven el dispatcher y el controlador de la ventana (atributos de la
    instancia, que tapan los de la clase y se sacan al cerrar), no las clases
    que otros módulos de GeoCAD ya envuelven. En IngeCAD 0.6.7 y 0.6.8, un
    Enter (o Espacio, Ctrl+J, el botón derecho como Enter) sin comando llega a
    ``dispatcher.submit("")``, que repite el último comando; Esc (y Ctrl+[)
    llama a ``tools.cancel()`` y después a ``dispatcher.cancel()``, y
    ``tools.cancel()`` se llama además al empezar cualquier comando."""
    disp = getattr(controlador.window, "dispatcher", None)
    if disp is None:
        return

    def submit(raw, *args, **kwargs):
        if (not str(raw).strip() and getattr(disp, "pending_prompt", None) is None
                and _activo() and terminar(controlador)):
            return None                         # el Enter terminó el recorte: no repite
        return type(disp).submit(disp, raw, *args, **kwargs)

    def cancelar_comando(*args, **kwargs):
        _esc_libre[0] = (getattr(controlador, "tool", None) is None
                         and getattr(controlador, "_grip_drag", None) is None
                         and getattr(controlador, "_selecting_for", None) is None)
        return type(controlador).cancel(controlador, *args, **kwargs)

    def cancelar_prompt(*args, **kwargs):
        libre = _esc_libre[0] and getattr(disp, "pending_prompt", None) is None
        _esc_libre[0] = False
        if libre and _activo():
            cancelar(controlador)
        return type(disp).cancel(disp, *args, **kwargs)

    for objeto, nombre, funcion in ((disp, "submit", submit), (disp, "cancel", cancelar_prompt),
                                    (controlador, "cancel", cancelar_comando)):
        if not getattr(vars(objeto).get(nombre), "_geocad_recorte", False):
            funcion._geocad_recorte = True
            setattr(objeto, nombre, funcion)


def _desenganchar(controlador) -> None:
    disp = getattr(controlador.window, "dispatcher", None)
    for objeto, nombre in ((disp, "submit"), (disp, "cancel"), (controlador, "cancel")):
        if objeto is not None and getattr(vars(objeto).get(nombre), "_geocad_recorte", False):
            delattr(objeto, nombre)


# ------------------------------------------------------------------ IngeCAD
def _envolver_agarres(original):
    def entity_grips(entity):
        try:
            if entity.dxftype() == "IMAGE" and _activo():
                propios = agarres(entity)
                if propios:
                    return propios
        except Exception:  # noqa: BLE001
            pass
        return original(entity)

    entity_grips._puente_original = original
    entity_grips._puente_fabrica = _envolver_agarres
    return entity_grips


def _envolver_agarre(original):
    def apply_grip_edit(entity, grip_index, role, new_point):
        if _recortando(entity):
            return True       # con Ctrl la imagen no se escala: se recorta al soltar
        if role in (ROL_MEDIO, ROL_LADO):
            return False      # el medio de un lado sólo sirve con Ctrl (y Alt+clic)
        return original(entity, grip_index, role, new_point)

    apply_grip_edit._puente_original = original
    apply_grip_edit._puente_fabrica = _envolver_agarre
    return apply_grip_edit


def _echo(controlador, texto: str) -> None:
    try:
        controlador.window.command_line.echo(texto)
    except Exception:  # noqa: BLE001
        pass


def _envolver_soltar(original):
    def finish_grip_drag(self, wx, wy):
        datos = getattr(self, "_grip_drag", None)
        try:
            handle, indice, rol, snap = datos
            entidad = self.index.entity(handle) if snap is not None else None
            recortar = (entidad is not None and entidad.dxftype() == "IMAGE"
                        and _activo() and _ctrl())
        except Exception:  # noqa: BLE001
            recortar = False
        if not recortar:
            return original(self, wx, wy)
        documento = self.window.document
        snap.undo(documento)           # la imagen como estaba al tomar el agarre
        comando, aviso = None, ""
        try:
            comando = preparar(entidad, indice, (wx, wy), documento, libre=_shift(), rol=rol)
        except RecorteError as exc:
            aviso = f"GeoCAD Yaguareté: no se recorta, {exc}."
        except Exception as exc:  # noqa: BLE001
            aviso = f"GeoCAD Yaguareté: no se pudo recortar la imagen ({exc})."
        base = getattr(self, "_grip_base", None) or (wx, wy)
        _soltando[0] = True
        try:
            original(self, *base)      # suelta el agarre sin cambiar nada
        finally:
            _soltando[0] = False
        historia = getattr(self.window, "history", None)
        pila = getattr(historia, "_undo", None)
        if pila and pila[-1] is snap:
            pila.pop()                 # ese paso vacío no cuenta para U
        if comando is not None:
            abrir(self, entidad)
            self._execute(comando)
            w, h = comando.tamano
            esquinas = len(leer(entidad)[2]) if leer(entidad) else 4
            _echo(self, f"Imagen recortada: {int(w)} x {int(h)} píxeles, {esquinas} esquinas. "
                        "Ctrl: esquina y lados; Shift+Ctrl: la esquina sola; "
                        "Alt+clic en un lado: una esquina nueva.")
            _echo(self, AVISO)
        elif aviso:
            _echo(self, aviso)

    finish_grip_drag._puente_original = original
    finish_grip_drag._puente_fabrica = _envolver_soltar
    return finish_grip_drag


def _imagenes_elegidas(controlador) -> list:
    vistas, out = set(), []
    for _x, _y, _rol, h, _i in controlador.grip_points():
        if h in vistas:
            continue
        vistas.add(h)
        e = controlador.index.entity(h)
        if e is not None and e.dxftype() == "IMAGE":
            out.append(e)
    return out


def _envolver_buscar(original):
    """Con Alt, sobre un lado de una imagen elegida: el agarre donde se
    agrega una esquina (también al pasar el mouse, para verlo)."""
    def grip_at(self, wx, wy, tol=None):
        hallado = original(self, wx, wy, tol)
        if hallado is not None:
            return hallado
        try:
            if not (_alt() and _activo()):
                return None
            sx, sy = self.to_space(wx, wy)
            from views.apertures import GRIP_PX
            t = self.px_to_space(GRIP_PX) if tol is None else tol / self.space_factor()
            for e in _imagenes_elegidas(self):
                lado = lado_cercano(e, (sx, sy), t)
                if lado is not None:
                    i, (px, py) = lado
                    return (px, py, ROL_MEDIO, e.dxf.handle, i)
        except Exception:  # noqa: BLE001
            pass
        return None

    grip_at._puente_original = original
    grip_at._puente_fabrica = _envolver_buscar
    return grip_at


def agregar(controlador, grip) -> bool:
    """Alt+clic en un lado: la esquina nueva, al instante (un U la saca)."""
    gx, gy, _rol, h, lado = grip
    entidad = controlador.index.entity(h)
    try:
        comando = preparar(entidad, lado, (gx, gy), controlador.window.document, rol=ROL_MEDIO)
    except RecorteError as exc:
        _echo(controlador, f"GeoCAD Yaguareté: no se agrega la esquina, {exc}.")
        return False
    abrir(controlador, entidad)
    controlador._execute(comando)
    _echo(controlador, f"Esquina agregada ({len(leer(entidad)[2])} esquinas). "
                       "Shift+Ctrl en una esquina la mueve sola.")
    _echo(controlador, AVISO)
    return True


def _envolver_tomar(original):
    def begin_grip_drag(self, grip):
        try:
            if grip is not None and grip[2] == ROL_MEDIO:
                agregar(self, grip)
                return None          # no se arrastra: la esquina ya está
        except Exception:  # noqa: BLE001
            pass
        return original(self, grip)

    begin_grip_drag._puente_original = original
    begin_grip_drag._puente_fabrica = _envolver_tomar
    return begin_grip_drag


def _envolver_punto(original):
    """Shift invierte ORTHO mientras se tiene apretado; con Ctrl (recortando
    una imagen) no: la esquina va libre adonde se suelta."""
    def resolved_point(self, wx, wy):
        datos = getattr(self, "_grip_drag", None)
        if datos is not None and getattr(self, "shift_held", False):
            try:
                entidad = self.index.entity(datos[0]) if datos[3] is not None else None
                if entidad is not None and entidad.dxftype() == "IMAGE" and _activo() and _ctrl():
                    self.shift_held = False
                    try:
                        return original(self, wx, wy)
                    finally:
                        self.shift_held = True
            except Exception:  # noqa: BLE001
                pass
        return original(self, wx, wy)

    resolved_point._puente_original = original
    resolved_point._puente_fabrica = _envolver_punto
    return resolved_point


def _poner(modulo, nombre: str, fabrica) -> None:
    actual = getattr(modulo, nombre, None)
    if actual is None or getattr(actual, "_puente_fabrica", None) is fabrica:
        return
    setattr(modulo, nombre, fabrica(getattr(actual, "_puente_original", actual)))


def instalar() -> None:
    """Se llama al cargar el plugin. Sin la ventana de IngeCAD (pruebas) se
    instala sólo sobre core.select."""
    try:
        from core import select
    except Exception:  # noqa: BLE001
        return
    _poner(select, "apply_grip_edit", _envolver_agarre)
    _poner(select, "entity_grips", _envolver_agarres)
    try:
        from views import tool_controller
    except Exception:  # noqa: BLE001 -- sin Qt
        return
    _poner(tool_controller, "apply_grip_edit", _envolver_agarre)
    _poner(tool_controller, "entity_grips", _envolver_agarres)
    from .dibujo import envolver
    envolver(tool_controller.ToolController, "finish_grip_drag", _envolver_soltar, reemplazar=True)
    envolver(tool_controller.ToolController, "resolved_point", _envolver_punto, reemplazar=True)
    envolver(tool_controller.ToolController, "grip_at", _envolver_buscar, reemplazar=True)
    envolver(tool_controller.ToolController, "begin_grip_drag", _envolver_tomar, reemplazar=True)
