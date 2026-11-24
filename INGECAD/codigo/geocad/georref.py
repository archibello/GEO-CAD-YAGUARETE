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
     cambian su punto de inserción y sus vectores. Proyectiva, Polinómica
     2-3 y Thin Plate Spline (3.21.0) la deforman: GeoCAD la rehace con PIL
     (remuestreo Vecino / Lineal / Cúbica; fondo transparente, blanco o los
     dos) en una copia con su archivo de mundo, y el dibujo pasa a usarla.
     Un solo U la vuelve a como estaba. Los puntos quedan en
     «<imagen>.points», el mismo archivo del Georreferenciador de QGIS (y se
     pueden cargar de ahí).

«Transformar en QGIS» con GDAL llega más adelante. Las cuentas no usan Qt.
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

# 3.93.0: las cuentas (métodos, residuos, .points, archivo de mundo, tabla) están en
# el núcleo, georref_cuentas.py, y las usa también GEORREF de QGIS
from .georref_cuentas import (  # noqa: F401 -- nombres de siempre para el resto de GeoCAD
    METODOS, DISPONIBLES, REHACEN, REMUESTREOS, _ultimo_remuestreo, FONDOS,
    _ultimo_fondo, METODO_INICIAL, _ultimo_metodo, SALIDAS, _ultima_salida, SUFIJO_COPIA,
    CABECERA_POINTS, EPS, _fmt, AjusteError, _resolver, _minimos_cuadrados,
    _normalizador, _terminos, Modelo, _Invertido, _h_aplicar, _h_mult,
    _h_inversa, Proyectiva, _Polinomio, Polinomica, _u, _Spline,
    ThinPlateSpline, _ajustar_deformante, ajustar, aplicar, inversa, residuos,
    error_medio, describir, borde_pixeles, marco, escribir_points, leer_points,
    texto_mundo, filas_tabla, texto_tabla, _metodo_de_texto, _remuestreo_de_texto)

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


def esquinas(img, coef=None, tramos: int = 16) -> list:
    """Las 4 esquinas de la imagen en el dibujo (con ``coef``: donde
    quedarían después de transformar). Polinómica 2-3 y TPS curvan los
    bordes: van ``tramos`` puntos por lado."""
    w, h = tamano(img)
    c = coef if coef is not None else coef_imagen(img)
    return [aplicar(c, s) for s in borde_pixeles(w, h, c, tramos)]


def dentro(img, p) -> bool:
    w, h = tamano(img)
    try:
        x, y = mundo_a_pixel(img, p)
    except ZeroDivisionError:
        return False
    return -EPS <= x <= w + EPS and -h - EPS <= y <= EPS


def matriz(img, coef, alto=None):
    """La Matrix44 (dibujo -> dibujo) que lleva la imagen de donde está a
    donde la deja ``coef`` (píxel de QGIS -> dibujo). Va por TransformCommand
    de IngeCAD: deshacer exacto y la imagen se redibuja sin regenerar.
    ``alto``: el de la imagen rehecha (si no, el de la imagen)."""
    from ezdxf.math import Matrix44

    h = float(alto) if alto is not None else tamano(img)[1]
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


def nombre_copia(ruta, ext=None) -> Path:
    """«plano_georref.png» (o _georref2, 3...): nunca pisa nada, ni la
    imagen ni su archivo de mundo, puntos o .aux.xml. ``ext``: otra
    extensión (la imagen rehecha con fondo transparente es PNG)."""
    ruta = Path(ruta)
    ext = ext or ruta.suffix
    for i in range(1, 1000):
        nueva = ruta.with_name(f"{ruta.stem}{SUFIJO_COPIA}{i if i > 1 else ''}{ext}")
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


def _recargar_pixeles(handle) -> None:
    """IngeCAD guarda la textura de cada IMAGE y, cuando la IMAGE cambia,
    sólo corre las 4 esquinas de esa textura (nunca vuelve a leer el
    archivo): con la imagen rehecha se veía la ORIGINAL, sin deformar, con
    el tamaño de píxel nuevo. Después del comando (y de cada U o rehacer):
    se oculta la textura vieja y se regenera, que lee el archivo nuevo. Sin
    ventana (pruebas), nada."""
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    def hacer():
        for w in app.topLevelWidgets():
            vp = getattr(w, "viewport", None)
            if vp is None or not hasattr(w, "regen_in_memory"):
                continue
            try:
                vp.hide_handles([handle])
            except Exception:  # noqa: BLE001
                pass
            (getattr(w, "regen_in_background", None) or w.regen_in_memory)()

    # después de que IngeCAD termine con el comando: él vuelve a mostrar la
    # textura vieja al correr sus esquinas
    QtCore.QTimer.singleShot(0, hacer)


class GeorrefCommand(actions.TransformCommand):
    """La imagen a su lugar y, con copia, apuntando al archivo nuevo. Es un
    TransformCommand: IngeCAD la redibuja al instante y un solo U deshace
    las dos cosas (el archivo copiado queda en el disco). Con ``tamano``
    (imagen rehecha, 3.21.0) cambia además su tamaño en píxeles y su recorte
    vuelve al rectángulo entero; U devuelve los dos."""

    def __init__(self, img, matrix, copia=None, tamano=None, transparente=False) -> None:
        super().__init__("GEORREF", [img], matrix)
        self.img = img
        self.copia = copia                   # nombre a guardar en el IMAGEDEF nuevo
        self.tamano = tamano
        self.transparente = transparente     # imagen rehecha con fondo transparente
        self._def_antes = img.image_def
        self._def_nuevo = None
        self._tam_antes = None

    def _cambiar_tamano(self) -> None:
        img = self.img
        d = img.dxf
        self._tam_antes = (tuple(d.image_size), list(img.boundary_path), d.get("flags", 0),
                           d.get("clipping", 0), d.get("clipping_boundary_type", 1),
                           d.get("count_boundary_points", 2))
        d.image_size = (float(self.tamano[0]), float(self.tamano[1]))
        img.reset_boundary_path()
        if self.transparente:
            # sin la marca «usar transparencia» el alfa no cuenta y el fondo se ve negro
            img.set_flag_state(img.USE_TRANSPARENCY, state=True)

    def _devolver_tamano(self) -> None:
        if self._tam_antes is None:
            return
        img = self.img
        size, borde, flags, clip, tipo, cuenta = self._tam_antes
        img.dxf.image_size = size
        img._boundary_path = list(borde)
        img.dxf.flags = flags
        img.dxf.clipping = clip
        img.dxf.clipping_boundary_type = tipo
        img.dxf.count_boundary_points = cuenta
        self._tam_antes = None

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
        if self.tamano is not None and self.entities:
            self._cambiar_tamano()
        if self.copia is not None and self.entities:
            if self._def_nuevo is None:
                w, h = tamano(self.img)
                self._def_nuevo = document.doc.add_image_def(
                    filename=str(self.copia), size_in_pixel=(int(w), int(h)))
            self._apuntar(self._def_nuevo)
        if self.tamano is not None and self.entities:
            _recargar_pixeles(self.img.dxf.handle)

    def undo(self, document) -> None:
        if self.copia is not None and self._def_antes is not None:
            self._apuntar(self._def_antes)
        self._devolver_tamano()
        super().undo(document)
        if self.tamano is not None and self.entities:
            _recargar_pixeles(self.img.dxf.handle)


# ------------------------------------------------------------- la tabla
# ------------------------------------------------------------- la orden
class GeorrefTool(Tool):
    """GEORREF: una imagen, pares de puntos (origen -> destino) con
    referencias, la tabla de puntos y Transformar."""

    entity_picker = True
    #: referencias que se suman mientras se marcan los pares
    REFERENCIAS = frozenset({"END", "MID", "INT", "NOD", "CEN"})
    PEDIDO_IMAGEN = ("Designe UNA imagen a ajustar (imágenes y vectores no se mezclan; "
                     "clic en la imagen o en su borde):")
    PEDIDO_TABLA = ("Tabla de puntos [Lineal/Helmert/Polinómica1/P2/P3/TPS/PRoyectiva/Apagar n/"
                    "Guardar/Marcar más/COPIA/COMO/MUNDO/DIBUJO/VECINO/BILINEAL/CÚBICA/"
                    "TRANSPARENTE/BLANCO/NEGRO/AMBOS/Transformar] <Transformar>:")

    def start(self) -> None:
        self.name = "GEORREF"
        self._img = None
        self._pares = []                  # {sx, sy, X, Y, on}
        self._pendiente = None            # punto de origen sin su destino (dibujo)
        self._tabla = False               # en la tabla (línea de comandos)
        self._metodo = _ultimo_metodo[0]
        self._salida = _ultima_salida[0]
        self._remuestreo = _ultimo_remuestreo[0]
        self._fondo = _ultimo_fondo[0]
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
        self._remuestreo = _ultimo_remuestreo[0] = r.get("remuestreo", self._remuestreo)
        self._fondo = _ultimo_fondo[0] = r.get("fondo", self._fondo)
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
        elif (rm := _remuestreo_de_texto(t)) is not None:
            self._remuestreo = _ultimo_remuestreo[0] = rm
        elif t.lower() in FONDOS:
            self._fondo = _ultimo_fondo[0] = t.lower()
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
        if self._metodo in REHACEN:
            self.ctx.echo(f"  {METODOS[self._metodo][0]} deforma la imagen: se rehace en una copia "
                          f"(remuestreo {REMUESTREOS[self._remuestreo]}; fondo "
                          f"{FONDOS[self._fondo][0].lower() + FONDOS[self._fondo][1:]}).")
        else:
            self.ctx.echo(f"  Al transformar se guarda: {SALIDAS[self._salida]}.")
        if (self._salida == "copia" or self._metodo in REHACEN) and self._copia_en is not None:
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
        if self._metodo in REHACEN:
            self._rehacer(img, coef, original, t["rms"])
            return
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

    def _rehacer(self, img, modelo, original, rms) -> None:
        """Proyectiva, Polinómica 2-3, TPS: la imagen nueva (una o dos, según
        el fondo), su archivo de mundo, y el dibujo pasa a usarla."""
        import time

        from . import georref_imagen as GI
        from . import georref_progreso as GP

        nombre = METODOS[self._metodo][0]
        ventana = getattr(self.ctx.services, "window", None)
        if original is None or not original.exists():
            self.ctx.echo(f"GeoCAD Yaguareté: no se encuentra el archivo de la imagen; {nombre} "
                          "necesita rehacerla. Elegí Lineal, Helmert o Polinómica 1.")
            self._volver_a_tabla()
            return
        w, h = tamano(img)
        mp = w * h / 1e6
        with GP.Progreso(ventana, "GEORREF") as prog:
            try:
                salidas = GI.rutas(original, self._fondo, self._copia_en)
                self.ctx.echo(f"Rehaciendo la imagen con {nombre}...")
                t0 = time.monotonic()
                coef, tam = prog.trabajo(
                    f"1/2  Rehaciendo la imagen con {nombre}",
                    lambda: GI.rehacer(original, salidas, modelo, self._remuestreo),
                    GP.estimar(mp, len(salidas)))
                GP.medir(tam[0] * tam[1] / 1e6, len(salidas), time.monotonic() - t0)
            except (OSError, AjusteError, ValueError) as exc:
                self.ctx.echo(f"GeoCAD Yaguareté: no se pudo rehacer la imagen ({exc}).")
                prog.cerrar()
                self._volver_a_tabla()
                return
            self._colocar(img, coef, tam, salidas, original, nombre, rms, prog, ventana)

    def _colocar(self, img, coef, tam, salidas, original, nombre, rms, prog, ventana) -> None:
        """La imagen rehecha en el dibujo (un solo U) y la pantalla al día."""
        usada = salidas[0][0]
        cmd = GeorrefCommand(img, matriz(img, coef, tam[1]),
                             nombre_en_dibujo(usada, img.image_def.dxf.filename, original), tam,
                             transparente=salidas[0][1] == "transparente")
        if not cmd.entities:
            self.ctx.echo("GeoCAD Yaguareté: IngeCAD no puede mover esta imagen.")
            self.ctx.finish()
            return
        self.ctx.execute(cmd)
        prog.regeneracion(ventana, img.dxf.handle)
        n = sum(1 for p in self._pares if p["on"])
        self.ctx.echo(f"Imagen rehecha con {nombre}: {n} puntos, error medio {_fmt(rms)}, "
                      f"{tam[0]} x {tam[1]} píxeles. U la vuelve a como estaba.")
        crs = crs_dibujo()
        for ruta, fondo in salidas:
            try:
                hechos = escribir_mundo(ruta, coef, crs)
            except OSError as exc:
                self.ctx.echo(f"No se pudo escribir el archivo de mundo de {ruta.name}: {exc}")
                continue
            uso = "la usa el dibujo" if ruta == usada else "otra copia"
            self.ctx.echo(f"  {ruta} (fondo {fondo}; {uso}) y {' y '.join(h.name for h in hechos)}.")
        self.ctx.echo(f"{original.name} queda como estaba. QGIS abre la copia en su lugar.")
        self._guardar()
        self.ctx.finish()

    def _volver_a_tabla(self) -> None:
        if self._tabla:
            self.prompt(self.PEDIDO_TABLA)
        else:
            self._abrir_tabla()

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
