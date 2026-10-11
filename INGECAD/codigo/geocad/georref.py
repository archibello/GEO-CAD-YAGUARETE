# SPDX-License-Identifier: GPL-3.0-or-later
"""GEORREF (RUBBERSHEET, AJUSTEIMAGEN): llevar una imagen a su lugar con
puntos de control, como el Georreferenciador de QGIS (módulo «georref», 3.18.0).

IngeCAD no tiene cómo ajustar un plano escaneado o una foto aérea con
puntos de control (AutoCAD Map lo hace con RUBBERSHEET). Acá:

  1) se designa UNA imagen (imágenes y vectores no se mezclan; de a una);
  2) se marcan pares de puntos con referencias o coordenadas escritas:
     «Punto en la imagen n» (dónde está) y «Punto de destino n» (dónde
     tiene que quedar). Cada par se ve como una flecha numerada; U quita
     el último. Con los puntos suficientes se ve, punteado, dónde va a
     quedar la imagen;
  3) Enter abre la TABLA DE PUNTOS, como la «Tabla de PCT» de QGIS:
     habilitado, X/Y de origen (píxeles de la imagen, como QGIS), X/Y de
     destino, dX, dY y residuo, y el error medio; el método con los mismos
     nombres de QGIS;
  4) «Transformar»: Lineal, Helmert y Polinómica 1 no rehacen la imagen:
     cambian su punto de inserción y sus vectores. Un solo U la vuelve a
     como estaba. Los puntos quedan en «<imagen>.points», el mismo archivo
     del Georreferenciador de QGIS (y se pueden cargar de ahí).

Thin Plate Spline, Polinómica 2-3 y Proyectiva (rehacer la imagen) llegan en
3.19.0; «Transformar en QGIS» con GDAL, en 3.20.0. Las cuentas no usan Qt.
"""
from __future__ import annotations

import math
import re
import shutil
from pathlib import Path

from core import actions
from tools.base import Tool

from . import modulos

PROGRAMA = "ingecad"

#: clave -> (nombre como en QGIS, puntos mínimos, disponible en esta versión)
METODOS = {
    "lineal": ("Lineal", 2, True),
    "helmert": ("Helmert", 2, True),
    "polinomica1": ("Polinómica 1", 3, True),
    "polinomica2": ("Polinómica 2", 6, False),
    "polinomica3": ("Polinómica 3", 10, False),
    "tps": ("Thin Plate Spline", 10, False),
    "proyectiva": ("Proyectiva", 4, False),
}
DISPONIBLES = tuple(k for k, (_n, _m, d) in METODOS.items() if d)
#: el método con que arranca la tabla (Helmert: no deforma un plano escaneado)
METODO_INICIAL = "helmert"
_ultimo_metodo = [METODO_INICIAL]          # el último usado, mientras IngeCAD esté abierto
#: qué se guarda al transformar (3.18.1), además del dibujo
SALIDAS = {
    "copia": "Una copia ajustada, con su archivo de mundo (la original queda como está)",
    "mundo": "Un archivo de mundo junto a la imagen original",
    "dibujo": "Sólo el dibujo",
}
_ultima_salida = ["copia"]
SUFIJO_COPIA = "_georref"

CABECERA_POINTS = "mapX,mapY,sourceX,sourceY,enable,dX,dY,residual"
EPS = 1e-12


def _fmt(v: float, dec: int = 4) -> str:
    return f"{v:.{dec}f}".rstrip("0").rstrip(".") if abs(v) < 1e15 else f"{v:g}"


# ------------------------------------------------------------- los métodos
class AjusteError(ValueError):
    """No se puede calcular (pocos puntos, puntos repetidos o alineados)."""


def ajustar(metodo: str, origen, destino) -> tuple:
    """Los 6 coeficientes (a, b, c, d, e, f) de X = a + b·x + c·y,
    Y = d + e·x + f·y que llevan ``origen`` (x, y) a ``destino`` (X, Y), por
    mínimos cuadrados, como QGIS:
      Lineal        escala en X y en Y por separado y desplazamiento, sin giro;
      Helmert       escala única, giro y desplazamiento (no deforma);
      Polinómica 1  afín: escalas, giro y sesgo."""
    if metodo not in METODOS:
        raise AjusteError(f"Método desconocido: {metodo}.")
    nombre, minimo, disponible = METODOS[metodo]
    if not disponible:
        raise AjusteError(f"{nombre} llega en GeoCAD 3.19.0.")
    origen = [(float(x), float(y)) for x, y in origen]
    destino = [(float(x), float(y)) for x, y in destino]
    n = len(origen)
    if n != len(destino):
        raise AjusteError("Hay distinta cantidad de puntos de origen y de destino.")
    if n < minimo:
        raise AjusteError(f"{nombre} necesita al menos {minimo} puntos habilitados (hay {n}).")
    mx = sum(p[0] for p in origen) / n
    my = sum(p[1] for p in origen) / n
    mX = sum(p[0] for p in destino) / n
    mY = sum(p[1] for p in destino) / n
    o = [(x - mx, y - my) for x, y in origen]
    d = [(x - mX, y - mY) for x, y in destino]
    sxx = sum(x * x for x, _y in o)
    syy = sum(y * y for _x, y in o)
    escala = max(sxx, syy, 1.0)
    if metodo == "lineal":
        if sxx <= EPS * escala or syy <= EPS * escala:
            raise AjusteError("Lineal necesita puntos que no estén todos en una misma "
                              "horizontal o vertical de la imagen.")
        b = sum(p[0] * q[0] for p, q in zip(o, d)) / sxx
        f = sum(p[1] * q[1] for p, q in zip(o, d)) / syy
        c = e = 0.0
    elif metodo == "helmert":
        s = sxx + syy
        if s <= EPS:
            raise AjusteError("Los puntos de origen están todos en el mismo lugar.")
        A = sum(p[0] * q[0] + p[1] * q[1] for p, q in zip(o, d)) / s
        B = sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(o, d)) / s
        b, c, e, f = A, -B, B, A
    else:                                          # polinomica1: afín
        sxy = sum(x * y for x, y in o)
        det = sxx * syy - sxy * sxy
        if abs(det) <= 1e-9 * escala * escala:
            raise AjusteError("Polinómica 1 necesita 3 puntos que no estén alineados.")
        sxX = sum(p[0] * q[0] for p, q in zip(o, d))
        syX = sum(p[1] * q[0] for p, q in zip(o, d))
        sxY = sum(p[0] * q[1] for p, q in zip(o, d))
        syY = sum(p[1] * q[1] for p, q in zip(o, d))
        b = (sxX * syy - syX * sxy) / det
        c = (syX * sxx - sxX * sxy) / det
        e = (sxY * syy - syY * sxy) / det
        f = (syY * sxx - sxY * sxy) / det
    if abs(b * f - c * e) <= EPS:
        raise AjusteError("Con estos puntos la imagen quedaría aplastada (escala cero).")
    a = mX - b * mx - c * my
    dd = mY - e * mx - f * my
    return (a, b, c, dd, e, f)


def aplicar(coef, p) -> tuple:
    a, b, c, d, e, f = coef
    x, y = p
    return (a + b * x + c * y, d + e * x + f * y)


def inversa(coef):
    a, b, c, d, e, f = coef
    det = b * f - c * e
    ib, ic, ie, if_ = f / det, -c / det, -e / det, b / det
    return (-(ib * a + ic * d), ib, ic, -(ie * a + if_ * d), ie, if_)


def residuos(coef, origen, destino) -> list:
    """(dX, dY, residuo) de cada punto: destino − calculado, en unidades
    del dibujo."""
    out = []
    for p, q in zip(origen, destino):
        X, Y = aplicar(coef, p)
        dx, dy = q[0] - X, q[1] - Y
        out.append((dx, dy, math.hypot(dx, dy)))
    return out


def error_medio(res, habilitados) -> float:
    """Error medio cuadrático de los puntos habilitados."""
    r = [x[2] for x, h in zip(res, habilitados) if h]
    return math.sqrt(sum(v * v for v in r) / len(r)) if r else 0.0


def describir(coef) -> str:
    """Escala y giro que resultan, para el informe."""
    _a, b, c, _d, e, f = coef
    sx, sy = math.hypot(b, e), math.hypot(c, f)
    giro = math.degrees(math.atan2(e, b))
    if abs(sx - sy) <= 1e-9 * max(sx, sy):
        return f"escala {_fmt(sx, 6)}, giro {_fmt(giro, 4)}°"
    return f"escala X {_fmt(sx, 6)}, Y {_fmt(sy, 6)}, giro {_fmt(giro, 4)}°"


# ------------------------------------------------------------- la imagen
def tamano(img) -> tuple:
    s = img.dxf.image_size
    return float(s[0]), float(s[1])


def _base(img):
    """insert, u, v (por píxel) de la imagen, en 2D."""
    i, u, v = img.dxf.insert, img.dxf.u_pixel, img.dxf.v_pixel
    return (i[0], i[1]), (u[0], u[1]), (v[0], v[1])


def coef_imagen(img) -> tuple:
    """Píxel de QGIS (columna, −fila; arriba a la izquierda = 0, 0) -> dibujo.
    ezdxf cuenta las filas desde abajo: y = sourceY + alto."""
    (ix, iy), (ux, uy), (vx, vy) = _base(img)
    _w, h = tamano(img)
    return (ix + vx * h, ux, vx, iy + vy * h, uy, vy)


def mundo_a_pixel(img, p) -> tuple:
    return aplicar(inversa(coef_imagen(img)), p)


def pixel_a_mundo(img, s) -> tuple:
    return aplicar(coef_imagen(img), s)


def esquinas(img, coef=None) -> list:
    """Las 4 esquinas de la imagen en el dibujo (con ``coef``: donde
    quedarían después de transformar)."""
    w, h = tamano(img)
    c = coef if coef is not None else coef_imagen(img)
    return [aplicar(c, s) for s in ((0, 0), (w, 0), (w, -h), (0, -h))]


def marco(puntos) -> list:
    return [(puntos[i], puntos[(i + 1) % len(puntos)]) for i in range(len(puntos))]


def dentro(img, p) -> bool:
    w, h = tamano(img)
    try:
        x, y = mundo_a_pixel(img, p)
    except ZeroDivisionError:
        return False
    return -EPS <= x <= w + EPS and -h - EPS <= y <= EPS


def matriz(img, coef):
    """La Matrix44 (dibujo -> dibujo) que lleva la imagen de donde está a
    donde la deja ``coef`` (píxel de QGIS -> dibujo). Va por TransformCommand
    de IngeCAD: deshacer exacto y la imagen se redibuja sin regenerar."""
    from ezdxf.math import Matrix44

    _w, h = tamano(img)
    (ix, iy), (ux, uy), (vx, vy) = _base(img)
    a, b, c, d, e, f = coef
    nu, nv = (b, e), (c, f)                   # vectores nuevos por píxel
    ni = (a - c * h, d - f * h)               # esquina de abajo a la izquierda
    det = ux * vy - vx * uy
    # L·[u v] = [nu nv]  ->  L = [nu nv]·[u v]⁻¹
    i00, i01, i10, i11 = vy / det, -vx / det, -uy / det, ux / det
    l00 = nu[0] * i00 + nv[0] * i10
    l01 = nu[0] * i01 + nv[0] * i11
    l10 = nu[1] * i00 + nv[1] * i10
    l11 = nu[1] * i01 + nv[1] * i11
    tx = ni[0] - (l00 * ix + l01 * iy)
    ty = ni[1] - (l10 * ix + l11 * iy)
    return Matrix44((l00, l10, 0, 0, l01, l11, 0, 0, 0, 0, 1, 0, tx, ty, 0, 1))


def archivo_imagen(img, document=None):
    """La ruta del archivo de la imagen (relativa al dibujo si no es absoluta)."""
    try:
        nombre = img.image_def.dxf.filename
    except Exception:  # noqa: BLE001
        return None
    if not nombre:
        return None
    p = Path(nombre)
    if not p.is_absolute():
        base = getattr(document, "path", None)
        if base:
            p = Path(base).parent / p
    return p


def ruta_points(img, document=None):
    """«plano.png.points», junto a la imagen, como lo guarda QGIS."""
    p = archivo_imagen(img, document)
    return p.with_name(p.name + ".points") if p is not None else None


# ------------------------------------------------------------- archivo .points
def escribir_points(ruta, pares, crs: str = "", metodo: str = "") -> Path:
    """El .points del Georreferenciador de QGIS. ``pares``: dicts con sx, sy
    (píxel de QGIS), X, Y (dibujo) y on. dX, dY y residuo, en píxeles (como
    QGIS; él los vuelve a calcular al cargar). Si ya había uno distinto,
    queda una copia «.points.bak»."""
    ruta = Path(ruta)
    hab = [p for p in pares if p["on"]]
    coef_inv = None
    if metodo:
        try:
            coef_inv = inversa(ajustar(metodo, [(p["sx"], p["sy"]) for p in hab],
                                       [(p["X"], p["Y"]) for p in hab]))
        except (AjusteError, ZeroDivisionError):
            coef_inv = None
    lineas = []
    if crs:
        lineas.append(f"#CRS: {crs}")
    lineas.append(CABECERA_POINTS)
    for p in pares:
        dx = dy = r = 0.0
        if coef_inv is not None:
            qx, qy = aplicar(coef_inv, (p["X"], p["Y"]))
            dx, dy = qx - p["sx"], qy - p["sy"]
            r = math.hypot(dx, dy)
        lineas.append(",".join(repr(float(v)) for v in (p["X"], p["Y"], p["sx"], p["sy"]))
                      + f",{1 if p['on'] else 0},{dx!r},{dy!r},{r!r}")
    texto = "\n".join(lineas) + "\n"
    if ruta.exists():
        try:
            if ruta.read_text(encoding="utf-8") == texto:
                return ruta
            shutil.copy2(ruta, ruta.with_name(ruta.name + ".bak"))
        except OSError:
            pass
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def leer_points(ruta) -> list:
    """Los pares de un .points de QGIS (también los viejos, separados por
    espacios o tabuladores, sin «enable»)."""
    pares = []
    for linea in Path(ruta).read_text(encoding="utf-8", errors="replace").splitlines():
        t = linea.strip()
        if not t or t.startswith("#") or t.lower().startswith("mapx"):
            continue
        campos = [c for c in t.replace("\t", ",").replace(" ", ",").split(",") if c != ""]
        try:
            X, Y, sx, sy = (float(v) for v in campos[:4])
        except ValueError:
            continue
        on = True
        if len(campos) > 4:
            try:
                on = bool(int(float(campos[4])))
            except ValueError:
                on = True
        pares.append({"sx": sx, "sy": sy, "X": X, "Y": Y, "on": on})
    return pares


def crs_dibujo() -> str:
    """El sistema de coordenadas del proyecto (GeoCAD > Opciones), o ""."""
    try:
        from . import config

        return str(config.get("crs_proyecto") or "")
    except Exception:  # noqa: BLE001
        return ""


# ------------------------------------------------------------- archivo de mundo y copia (3.18.1)
#: extensión del archivo de mundo según la de la imagen (la de ESRI / GDAL)
MUNDO = {".png": ".pgw", ".jpg": ".jgw", ".jpeg": ".jgw", ".tif": ".tfw", ".tiff": ".tfw",
         ".bmp": ".bpw", ".gif": ".gfw"}


def ruta_mundo(ruta) -> Path:
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    return ruta.with_suffix(MUNDO.get(ext, (ext[:2] + ext[-1:] + "w") if len(ext) >= 3 else ".wld"))


def texto_mundo(coef) -> str:
    """Las 6 líneas del archivo de mundo: tamaño del píxel en X, giro, giro,
    tamaño en Y (negativo), X e Y del CENTRO del píxel de arriba a la
    izquierda. Lineal, Helmert y Polinómica 1 entran exactos (giro y sesgo)."""
    a, b, c, d, e, f = coef
    x0, y0 = aplicar(coef, (0.5, -0.5))
    return "\n".join(repr(float(v)) for v in (b, e, -c, -f, x0, y0)) + "\n"


def _escribir(ruta: Path, texto: str) -> Path:
    """Escribe sin perder lo que había: si existía distinto, queda «.bak»."""
    if ruta.exists():
        try:
            if ruta.read_text(encoding="utf-8") == texto:
                return ruta
            shutil.copy2(ruta, ruta.with_name(ruta.name + ".bak"))
        except OSError:
            pass
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def wkt(crs: str) -> str:
    try:
        import pyproj

        return pyproj.CRS.from_user_input(crs).to_wkt()
    except Exception:  # noqa: BLE001 -- sin pyproj o un código raro: sin sistema
        return ""


def escribir_mundo(ruta_imagen, coef, crs: str = "") -> list:
    """El archivo de mundo junto a la imagen y, si hay sistema de
    coordenadas, «<imagen>.aux.xml» con él (lo lee GDAL, y así QGIS). Un
    .aux.xml que ya estaba no se toca. Devuelve lo escrito."""
    ruta_imagen = Path(ruta_imagen)
    hechos = [_escribir(ruta_mundo(ruta_imagen), texto_mundo(coef))]
    texto = wkt(crs) if crs else ""
    aux = ruta_imagen.with_name(ruta_imagen.name + ".aux.xml")
    if texto and not aux.exists():
        from xml.sax.saxutils import escape

        aux.write_text("<PAMDataset>\n  <SRS dataAxisToSRSAxisMapping=\"1,2\">"
                       f"{escape(texto)}</SRS>\n</PAMDataset>\n", encoding="utf-8")
        hechos.append(aux)
    return hechos


def nombre_copia(ruta) -> Path:
    """«plano_georref.png» (o _georref2, 3...): nunca pisa nada, ni la
    imagen ni su archivo de mundo, puntos o .aux.xml."""
    ruta = Path(ruta)
    for i in range(1, 1000):
        nueva = ruta.with_name(f"{ruta.stem}{SUFIJO_COPIA}{i if i > 1 else ''}{ruta.suffix}")
        vecinos = (nueva, ruta_mundo(nueva), nueva.with_name(nueva.name + ".points"),
                   nueva.with_name(nueva.name + ".aux.xml"))
        if not any(v.exists() for v in vecinos):
            return nueva
    raise OSError("demasiadas copias ajustadas de esta imagen")


def destino_copia(elegida, original) -> Path:
    """La ruta elegida con «Guardar copia geo como...», con la extensión de
    la original (los mismos bytes con otra extensión confundirían a QGIS).
    Nunca la original misma."""
    elegida, original = Path(elegida).expanduser(), Path(original)
    if elegida.suffix.lower() != original.suffix.lower():
        elegida = elegida.with_name(elegida.name + original.suffix)
    if elegida.resolve() == original.resolve():
        raise OSError("la copia no puede ser la imagen original")
    if not elegida.parent.is_dir():
        raise OSError(f"no existe la carpeta {elegida.parent}")
    return elegida


def nombre_en_dibujo(copia, guardado, original) -> str:
    """Cómo queda escrita la copia en el dibujo: relativa (como estaba la
    original) si está en la misma carpeta; si no, la ruta completa."""
    guardado = Path(guardado)
    if not guardado.is_absolute() and Path(copia).parent.resolve() == Path(original).parent.resolve():
        return str(guardado.with_name(Path(copia).name))
    return str(copia)


class GeorrefCommand(actions.TransformCommand):
    """La imagen a su lugar y, con copia, apuntando al archivo nuevo. Es un
    TransformCommand: IngeCAD la redibuja al instante y un solo U deshace
    las dos cosas (el archivo copiado queda en el disco)."""

    def __init__(self, img, matrix, copia=None) -> None:
        super().__init__("GEORREF", [img], matrix)
        self.img = img
        self.copia = copia                   # nombre a guardar en el IMAGEDEF nuevo
        self._def_antes = img.image_def
        self._def_nuevo = None

    def _apuntar(self, imagedef) -> None:
        img = self.img
        reactor = img.image_def_reactor
        viejo = img.image_def
        if reactor is not None and viejo is not None and viejo is not imagedef:
            viejo.discard_reactor_handle(reactor.dxf.handle)
            imagedef.append_reactor_handle(reactor.dxf.handle)
        img.image_def = imagedef

    def do(self, document) -> None:
        super().do(document)
        if self.copia is not None and self.entities:
            if self._def_nuevo is None:
                w, h = tamano(self.img)
                self._def_nuevo = document.doc.add_image_def(
                    filename=str(self.copia), size_in_pixel=(int(w), int(h)))
            self._apuntar(self._def_nuevo)

    def undo(self, document) -> None:
        if self.copia is not None and self._def_antes is not None:
            self._apuntar(self._def_antes)
        super().undo(document)


# ------------------------------------------------------------- la tabla
def filas_tabla(pares, metodo: str) -> dict:
    """Lo que muestra la tabla: cada fila con sus residuos (si se puede
    calcular), el error medio y el motivo si no se puede."""
    hab = [p for p in pares if p["on"]]
    coef, motivo = None, ""
    try:
        coef = ajustar(metodo, [(p["sx"], p["sy"]) for p in hab],
                       [(p["X"], p["Y"]) for p in hab])
    except AjusteError as exc:
        motivo = str(exc)
    filas = []
    res = residuos(coef, [(p["sx"], p["sy"]) for p in pares],
                   [(p["X"], p["Y"]) for p in pares]) if coef else [None] * len(pares)
    for i, (p, r) in enumerate(zip(pares, res), 1):
        filas.append({"id": i, "on": p["on"], "sx": p["sx"], "sy": p["sy"],
                      "X": p["X"], "Y": p["Y"],
                      "dX": r[0] if r else None, "dY": r[1] if r else None,
                      "residuo": r[2] if r else None})
    rms = error_medio(res, [p["on"] for p in pares]) if coef else None
    return {"filas": filas, "coef": coef, "rms": rms, "motivo": motivo}


def texto_tabla(pares, metodo: str) -> list:
    """La tabla en líneas de texto (para la línea de comandos)."""
    t = filas_tabla(pares, metodo)
    out = [f"Tabla de puntos — método {METODOS[metodo][0]}:",
           "  On  ID   X origen    Y origen     X destino      Y destino        dX        dY   Residuo"]
    for f in t["filas"]:
        res = ("" if f["dX"] is None else
               f"{f['dX']:>10.4f}{f['dY']:>10.4f}{f['residuo']:>10.4f}")
        out.append(f"  {'sí' if f['on'] else 'no':>2}{f['id']:>4}{f['sx']:>11.2f}{f['sy']:>12.2f}"
                   f"{f['X']:>15.4f}{f['Y']:>15.4f}{res}")
    if t["coef"] is None:
        out.append("  " + t["motivo"])
    else:
        out.append(f"  Error medio: {_fmt(t['rms'])} · {describir(t['coef'])}")
    return out


def _metodo_de_texto(t: str):
    t = t.upper().replace(" ", "").replace("Ó", "O")
    if t in ("L", "LINEAL", "LINEAR"):
        return "lineal"
    if t in ("H", "HELMERT"):
        return "helmert"
    if t in ("P", "P1", "POL1", "POLINOMICA", "POLINOMICA1", "POLYNOMIAL1"):
        return "polinomica1"
    return None


# ------------------------------------------------------------- la orden
class GeorrefTool(Tool):
    """GEORREF: una imagen, pares de puntos (origen -> destino) con
    referencias, la tabla de puntos y Transformar."""

    entity_picker = True
    #: referencias que se suman mientras se marcan los pares
    REFERENCIAS = frozenset({"END", "MID", "INT", "NOD", "CEN"})
    PEDIDO_IMAGEN = ("Designe UNA imagen a ajustar (imágenes y vectores no se mezclan; "
                     "clic en la imagen o en su borde):")
    PEDIDO_TABLA = ("Tabla de puntos [Lineal/Helmert/Polinómica1/Apagar n/Guardar/"
                    "Marcar más/COPIA/COMO/MUNDO/DIBUJO/Transformar] <Transformar>:")

    def start(self) -> None:
        self.name = "GEORREF"
        self._img = None
        self._pares = []                  # {sx, sy, X, Y, on}
        self._pendiente = None            # punto de origen sin su destino (dibujo)
        self._tabla = False               # en la tabla (línea de comandos)
        self._metodo = _ultimo_metodo[0]
        self._salida = _ultima_salida[0]
        self._copia_en = None             # «Guardar copia geo como...»: dónde
        self.entity_picker = True
        s = self.ctx.services
        previa = list(getattr(s, "selection", None) or ())
        if previa:
            ents = [e for h in previa if (e := self._entidad(h)) is not None]
            imgs = [e for e in ents if e.dxftype() == "IMAGE"]
            if s is not None:
                s.selection = set()
            if len(imgs) == 1:
                otros = len(ents) - 1
                if otros:
                    self.ctx.echo(f"GeoCAD Yaguareté: imágenes y vectores no se mezclan; "
                                  f"se ajusta la imagen y quedan afuera {otros} objeto(s).")
                self._elegir(imgs[0])
                return
            if len(imgs) > 1:
                self.ctx.echo(f"GeoCAD Yaguareté: hay {len(imgs)} imágenes elegidas; "
                              "se ajustan de a una.")
        self.prompt(self.PEDIDO_IMAGEN)

    # -- ayudas -----------------------------------------------------------------
    def _documento(self):
        return getattr(getattr(self.ctx.services, "window", None), "document", None)

    def _entidad(self, handle):
        doc = self._documento()
        if doc is None:
            return None
        e = doc.doc.entitydb.get(handle)
        return e if e is not None and e.is_alive else None

    def _imagen_en(self, p):
        """La imagen bajo el punto: la que toma el clic (su borde) o, si no,
        la de más arriba que lo contiene."""
        s = self.ctx.services
        e = s.pick_entity(p) if s is not None else None
        if e is not None and e.dxftype() == "IMAGE":
            return e, None
        doc = self._documento()
        if doc is not None:
            imgs = [i for i in doc.doc.modelspace().query("IMAGE") if dentro(i, p)]
            if imgs:
                return imgs[-1], None
        return None, e

    def referencias_extra(self) -> frozenset:
        return self.REFERENCIAS if self._img is not None and not self._tabla else frozenset()

    def _n(self) -> int:
        return len(self._pares) + 1

    def _pedir_par(self) -> None:
        if self._pendiente is None:
            self.prompt(f"Punto en la imagen {self._n()} [Cargar puntos/Deshacer] "
                        "<Enter: tabla de puntos>:")
        else:
            self.prompt(f"Punto de destino {self._n()} [Deshacer]:")

    def _elegir(self, img) -> None:
        self._img = img
        self.entity_picker = False         # los pares, con referencias
        w, h = tamano(img)
        doc = self._documento()
        f = archivo_imagen(img, doc)
        self.ctx.echo(f"Imagen: {f.name if f else '(sin archivo)'} ({int(w)} x {int(h)} píxeles).")
        r = ruta_points(img, doc)
        if r is not None and r.exists():
            try:
                n = len(leer_points(r))
            except OSError:
                n = 0
            if n:
                self.ctx.echo(f"Hay {n} puntos guardados en {r.name}: C (Cargar puntos) los trae.")
        self._pedir_par()

    # -- entrada -------------------------------------------------------------------
    def on_point(self, point) -> None:
        if self._tabla:
            return
        p = (float(point[0]), float(point[1]))
        if self._img is None:
            img, otro = self._imagen_en(p)
            if img is None:
                if otro is not None:
                    self.ctx.echo(f"GeoCAD Yaguareté: {otro.dxftype()} no es una imagen. "
                                  "Por ahora GEORREF ajusta imágenes; los vectores llegan más adelante.")
                self.prompt(self.PEDIDO_IMAGEN)
                return
            self._elegir(img)
            return
        if not self._img.is_alive:
            self.ctx.echo("La imagen ya no está en el dibujo.")
            self.ctx.finish()
            return
        if self._pendiente is None:
            self._pendiente = p
            self.last_point = p
            self._pedir_par()
            return
        sx, sy = mundo_a_pixel(self._img, self._pendiente)
        self._pares.append({"sx": sx, "sy": sy, "X": p[0], "Y": p[1], "on": True})
        self._pendiente = None
        self.last_point = p
        self.ctx.echo(self._resumen())
        self._pedir_par()

    def _resumen(self) -> str:
        hab = [x for x in self._pares if x["on"]]
        nombre, minimo, _d = METODOS[self._metodo]
        if len(hab) < minimo:
            return f"{len(self._pares)} par(es). {nombre} necesita {minimo}."
        t = filas_tabla(self._pares, self._metodo)
        if t["coef"] is None:
            return f"{len(self._pares)} par(es). {t['motivo']}"
        return (f"{len(self._pares)} par(es). {nombre}: error medio {_fmt(t['rms'])}. "
                "Enter abre la tabla de puntos.")

    def on_option(self, text: str) -> bool:
        t = text.strip().upper().lstrip("_")
        if self._img is None:
            return False
        if self._tabla:
            return self._opcion_tabla(t)
        if t in ("U", "D", "DESHACER", "UNDO"):
            if self._pendiente is not None:
                self._pendiente = None
                self.ctx.echo("Se quitó el punto en la imagen sin destino.")
            elif self._pares:
                self._pares.pop()
                self.ctx.echo(f"Se quitó el par {len(self._pares) + 1}.")
            else:
                self.ctx.echo("No hay pares para quitar.")
            self._pedir_par()
            return True
        if t in ("C", "CARGAR", "CARGARPUNTOS", "LOAD") and self._pendiente is None:
            self._cargar()
            self._pedir_par()
            return True
        return False

    def _cargar(self, ruta=None) -> bool:
        ruta = ruta or ruta_points(self._img, self._documento())
        if ruta is None or not Path(ruta).exists():
            self.ctx.echo("No hay archivo de puntos junto a la imagen.")
            return False
        try:
            pares = leer_points(ruta)
        except OSError as exc:
            self.ctx.echo(f"No se pudo leer {Path(ruta).name}: {exc}")
            return False
        self._pares = pares
        self.ctx.echo(f"Cargados {len(pares)} pares de {Path(ruta).name}.")
        return True

    def on_enter(self) -> None:
        if self._img is None:
            self.ctx.finish()
            return
        if self._tabla:
            self._transformar()
            return
        if self._pendiente is not None:
            self.ctx.echo("Falta el punto de destino de ese par (U lo quita).")
            self._pedir_par()
            return
        if not self._pares:
            self.ctx.finish()
            return
        self._abrir_tabla()

    def on_cancel(self) -> None:
        if self._img is not None:
            self.ctx.echo("GEORREF cancelado: la imagen queda como estaba.")
        self.ctx.finish()

    # -- la tabla ------------------------------------------------------------------
    def _abrir_tabla(self) -> None:
        from . import georref_ui

        r = georref_ui.tabla(getattr(self.ctx.services, "window", None), self)
        if r is georref_ui.SIN_QT:
            self._tabla = True
            self._mostrar_tabla()
            return
        if r is None:
            self.on_cancel()
            return
        self._metodo = r.get("metodo", self._metodo)
        _ultimo_metodo[0] = self._metodo
        self._salida = _ultima_salida[0] = r.get("salida", self._salida)
        if r.get("copia_en"):
            self._copia_en = Path(r["copia_en"])
        for p, on in zip(self._pares, r.get("habilitados", ())):
            p["on"] = bool(on)
        if r.get("pares") is not None:          # cargados desde la tabla
            self._pares = r["pares"]
        accion = r.get("accion")
        if accion == "transformar":
            self._transformar()
        else:                                    # marcar más pares
            self._pedir_par()

    def _opcion_tabla(self, t: str) -> bool:
        m = _metodo_de_texto(t)
        if m is not None:
            self._metodo = _ultimo_metodo[0] = m
        elif (num := re.fullmatch(r"(?:A|APAGAR|E|ENCENDER)\s*(\d+)", t)) is not None:
            i = int(num.group(1)) - 1               # A3 / APAGAR 3 / E3: apaga o prende el 3
            if not 0 <= i < len(self._pares):
                self.ctx.echo(f"No hay punto {i + 1}.")
            else:
                self._pares[i]["on"] = not self._pares[i]["on"]
        elif t in ("G", "GUARDAR", "SAVE"):
            self._guardar()
        elif t in ("COPIA", "MUNDO", "DIBUJO"):
            self._salida = _ultima_salida[0] = t.lower()
        elif t in ("COMO", "CÓMO", "GUARDARCOMO", "COPIACOMO"):
            orig = archivo_imagen(self._img, self._documento())
            inicio = str(self._copia_en or (nombre_copia(orig) if orig else ""))
            texto = self.ctx.ask_text("Guardar copia geo como (carpeta y nombre):", inicio)
            if texto:
                self._copia_en = Path(texto.strip())
                self._salida = _ultima_salida[0] = "copia"
        elif t in ("M", "MARCAR", "MARCARMAS", "MARCARMÁS"):
            self._tabla = False
            self._pedir_par()
            return True
        elif t in ("T", "TRANSFORMAR"):
            self._transformar()
            return True
        else:
            return False
        self._mostrar_tabla()
        return True

    def _mostrar_tabla(self) -> None:
        for linea in texto_tabla(self._pares, self._metodo):
            self.ctx.echo(linea)
        self.ctx.echo(f"  Al transformar se guarda: {SALIDAS[self._salida]}.")
        if self._salida == "copia" and self._copia_en is not None:
            self.ctx.echo(f"  Copia geo en: {self._copia_en}")
        self.prompt(self.PEDIDO_TABLA)

    def _guardar(self, ruta=None):
        ruta = ruta or ruta_points(self._img, self._documento())
        if ruta is None:
            self.ctx.echo("La imagen no tiene archivo: no se pueden guardar los puntos.")
            return None
        try:
            r = escribir_points(ruta, self._pares, crs_dibujo(), self._metodo)
        except OSError as exc:
            self.ctx.echo(f"No se pudieron guardar los puntos en {ruta}: {exc}")
            return None
        self.ctx.echo(f"Puntos guardados en {r} (se abren en el Georreferenciador de QGIS).")
        return r

    def _transformar(self) -> None:
        img = self._img
        if img is None or not img.is_alive:
            self.ctx.echo("La imagen ya no está en el dibujo.")
            self.ctx.finish()
            return
        t = filas_tabla(self._pares, self._metodo)
        if t["coef"] is None:
            self.ctx.echo("No se puede transformar: " + t["motivo"])
            if self._tabla:
                self.prompt(self.PEDIDO_TABLA)
            else:
                self._abrir_tabla()
            return
        coef = t["coef"]
        original = archivo_imagen(img, self._documento())
        salida = self._salida
        if salida != "dibujo" and (original is None or not original.exists()):
            self.ctx.echo("GeoCAD Yaguareté: no se encuentra el archivo de la imagen; "
                          "se ajusta sólo en el dibujo.")
            salida = "dibujo"
        copia = guardar_como = None
        if salida == "copia":
            try:
                copia = (destino_copia(self._copia_en, original) if self._copia_en is not None
                         else nombre_copia(original))
                shutil.copy2(original, copia)
                from .imagengeo import ruta_real

                copia = Path(ruta_real(copia))
            except OSError as exc:
                self.ctx.echo(f"GeoCAD Yaguareté: no se pudo copiar la imagen ({exc}); "
                              "se ajusta sólo en el dibujo.")
                copia, salida = None, "dibujo"
            else:
                guardar_como = nombre_en_dibujo(copia, img.image_def.dxf.filename, original)
        cmd = GeorrefCommand(img, matriz(img, coef), guardar_como)
        if not cmd.entities:
            self.ctx.echo("GeoCAD Yaguareté: IngeCAD no puede mover esta imagen.")
            if copia is not None:
                copia.unlink(missing_ok=True)
            self.ctx.finish()
            return
        self.ctx.execute(cmd)
        n = sum(1 for p in self._pares if p["on"])
        self.ctx.echo(f"Imagen ajustada con {METODOS[self._metodo][0]}: {n} puntos, error medio "
                      f"{_fmt(t['rms'])} ({describir(coef)}). U la vuelve a como estaba.")
        if salida != "dibujo":
            destino = copia if salida == "copia" else original
            try:
                hechos = escribir_mundo(destino, coef, crs_dibujo())
            except OSError as exc:
                self.ctx.echo(f"No se pudo escribir el archivo de mundo: {exc}")
            else:
                extra = " y " .join(h.name for h in hechos)
                if salida == "copia":
                    self.ctx.echo(f"Copia ajustada: {copia} ({extra}); el dibujo usa la copia y "
                                  f"{original.name} queda como estaba. QGIS la abre en su lugar.")
                else:
                    self.ctx.echo(f"Archivo de mundo junto a la original: {extra}. "
                                  "QGIS la abre en su lugar.")
        self._guardar()
        self.ctx.finish()

    # -- resaltado (lo dibuja dibujo.py) ---------------------------------------
    def _flecha(self, a, b, punta) -> list:
        segs = [(a, b)]
        L = math.dist(a, b)
        if L <= EPS:
            return segs
        k = min(punta, 0.35 * L) / L
        dx, dy = (b[0] - a[0]) * k, (b[1] - a[1]) * k
        for s in (1, -1):                         # dos rayitas a ±25°
            c, si = math.cos(math.radians(25)), s * math.sin(math.radians(25))
            segs.append((b, (b[0] - (dx * c - dy * si), b[1] - (dx * si + dy * c))))
        return segs

    def resaltado(self, cursor) -> dict:
        """Antes de elegir: la imagen bajo el cursor. Después: su marco, las
        flechas numeradas de cada par (apagadas, punteadas), el par a medio
        marcar hasta el cursor y, punteado, dónde quedaría la imagen."""
        out = {"cursor": [], "elegido": [], "vista": [], "flecha": [], "flecha_off": [],
               "puntos": [], "textos": []}
        img = self._img
        if img is None:
            if cursor is not None:
                i, _o = self._imagen_en(tuple(cursor))
                if i is not None:
                    out["cursor"] = marco(esquinas(i))
            return out
        if not img.is_alive:
            return out
        caja = esquinas(img)
        out["elegido"] = marco(caja)
        diag = math.dist(caja[0], caja[2])
        punta = 0.02 * diag
        for i, p in enumerate(self._pares, 1):
            a = pixel_a_mundo(img, (p["sx"], p["sy"]))
            b = (p["X"], p["Y"])
            out["flecha" if p["on"] else "flecha_off"] += self._flecha(a, b, punta)
            out["puntos"].append(a)
            out["textos"].append((a, str(i)))
        pares = list(self._pares)
        if self._pendiente is not None:
            out["puntos"].append(self._pendiente)
            out["textos"].append((self._pendiente, str(self._n())))
            if cursor is not None:
                c = (float(cursor[0]), float(cursor[1]))
                out["flecha"] += self._flecha(self._pendiente, c, punta)
                sx, sy = mundo_a_pixel(img, self._pendiente)
                pares.append({"sx": sx, "sy": sy, "X": c[0], "Y": c[1], "on": True})
        hab = [p for p in pares if p["on"]]
        if len(hab) >= METODOS[self._metodo][1]:
            try:
                coef = ajustar(self._metodo, [(p["sx"], p["sy"]) for p in hab],
                               [(p["X"], p["Y"]) for p in hab])
                out["vista"] = marco(esquinas(img, coef))
            except (AjusteError, ZeroDivisionError):
                pass
        return out


def activo() -> bool:
    return modulos.activo(PROGRAMA, "georref")
