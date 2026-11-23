# SPDX-License-Identifier: GPL-3.0-or-later
"""RUMBOS (RB, GMS, POLIGONAL) en IngeCAD: poligonal por rumbos, la misma
orden de Dibujo CAD en QGIS (3.43.0), en la barra GeoCAD (3.87.0).

    Precise primer punto del tramo base:
    Precise segundo punto del tramo base (da la dirección):
    Precise tramo distancia<ángulo o [Ángulo/Modo/Base/Cerrar/desHacer]:

- El tramo base A-B (dos clics, con referencias) da la dirección del primer
  ángulo. Base = No (por defecto, como Líneas GMS): no se dibuja; Base = Sí
  (como el Continuo): es el primer tramo.
- Cada tramo: 25.4<91d30'15" . Ángulo Interior (180 = sigue derecho,
  antihorario desde el tramo anterior) o Deflexión (0 = sigue derecho, + a la
  izquierda). Siempre valen 30dI / 30dD (deflexión), los rumbos N45d30'E y
  '<<' (absoluto). También un clic o una distancia sola hacia el cursor.
- Modo Polilínea (un objeto) o Tramos (una línea por tramo, como Líneas GMS).
  Se elige antes del primer tramo. Cerrar: en Polilínea queda cerrada.
- La longitud de cada tramo y la acumulada se ven en la línea de comandos.

Los ángulos se leen con ``angulos.direccion`` (el mismo núcleo de QGIS), así
que el resultado es el de ``units.tramo_rumbo`` de Dibujo CAD.
"""
from __future__ import annotations

import math
import re

from core import actions
from tools.base import Tool

from .angulos import AnguloError, direccion

PROGRAMA = "ingecad"
KEY_ANGULO = "geocad/rumbos/angulo"       # "interior" / "deflexion"
KEY_TRAMOS = "geocad/rumbos/tramos"       # True = una línea por tramo
KEY_BASE = "geocad/rumbos/base"           # True = el tramo base se dibuja

OPT_ANG = ("A", "ANGULO", "ÁNGULO", "ANGLE")
OPT_MODO = ("M", "MODO", "MODE")
OPT_BASE = ("B", "BASE")
OPT_CERRAR = ("C", "CERRAR", "CLOSE")
OPT_DESHACER = ("H", "U", "DESHACER", "UNDO")

_TRAMO_RE = re.compile(r"^@?(?P<dist>[^<@]+)<(?P<ang>.+)$")
EPS = 1e-12


# -- cuentas (sin Qt) --------------------------------------------------------------
def tramo(prev, cur, texto: str, modo: str = "interior"):
    """'distancia<ángulo' -> (punto siguiente, distancia), o None si el texto
    no es un tramo. ``prev`` y ``cur``: los dos últimos vértices. ``modo``:
    "interior" o "deflexion". Lanza AnguloError si el texto está mal."""
    m = _TRAMO_RE.match(str(texto).strip().replace(" ", ""))
    if not m:
        return None
    try:
        d = float(m.group("dist").replace(",", "."))
    except ValueError:
        raise AnguloError(f'distancia no válida: "{m.group("dist")}"') from None
    if d <= 0:
        raise AnguloError("la distancia debe ser mayor que cero")
    ref = math.degrees(math.atan2(cur[1] - prev[1], cur[0] - prev[0]))
    a = math.radians(direccion(m.group("ang"), ref, rel=True,
                               modo_rel="interior" if modo == "interior" else "direccion"))
    return (cur[0] + d * math.cos(a), cur[1] + d * math.sin(a)), d


def _bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "sí", "si", "yes")
    return bool(value)


def _get(key, default):
    from .dibujo import _get as leer
    return leer(key, default)


def _set(key, value) -> None:
    from .dibujo import _set as poner
    poner(key, value)


# -- la herramienta -----------------------------------------------------------------
class RumbosTool(Tool):
    """RUMBOS: tramo base y tramos distancia<ángulo."""

    #: GeoCAD no le reescribe los ángulos (dibujo._envolver_on_text): los lee ella
    angulos_propios = True

    def start(self) -> None:
        self.name = "RUMBOS"
        self.pts: list = []
        self.largo = 0.0
        self.angulo = "deflexion" if str(_get(KEY_ANGULO, "interior")) == "deflexion" else "interior"
        self.tramos = _bool(_get(KEY_TRAMOS, False))
        self.con_base = _bool(_get(KEY_BASE, False))
        self.objetos = 0            # líneas ya creadas en modo Tramos (para desHacer)
        self.ctx.echo("Parámetros actuales: Ángulo = %s  Modo = %s  Base = %s"
                      % (self._ang_txt(), self._modo_txt(), "Sí" if self.con_base else "No"))
        self._pedir()

    # -- textos ---------------------------------------------------------------------
    def _ang_txt(self) -> str:
        return "Interior" if self.angulo == "interior" else "Deflexión"

    def _modo_txt(self) -> str:
        return "Tramos" if self.tramos else "Polilínea"

    def _largo_txt(self, v: float) -> str:
        try:
            return self.length_text(v)
        except Exception:  # noqa: BLE001 - IngeCAD 0.6.x no tiene length_text
            return f"{v:.3f}"

    def _dibujados(self) -> list:
        """Los vértices que quedan en el dibujo (sin la base si no se dibuja)."""
        return list(self.pts if self.con_base else self.pts[1:])

    def _pedir(self) -> None:
        n = len(self.pts)
        if n == 0:
            self.prompt("Precise primer punto del tramo base:")
            return
        if n == 1:
            self.prompt("Precise segundo punto del tramo base (da la dirección):")
            return
        opts = ["Ángulo=" + self._ang_txt()]
        if n == 2:
            opts += ["Modo=" + self._modo_txt(), "Base=" + ("Sí" if self.con_base else "No")]
        if len(self._dibujados()) >= 3:
            opts.append("Cerrar")
        if n > 2:
            opts.append("desHacer")
        self.prompt("Precise tramo distancia<ángulo o [" + "/".join(opts) + "]:")

    # -- entrada --------------------------------------------------------------------
    def on_point(self, point) -> None:
        p = (float(point[0]), float(point[1]))
        if self.pts and math.dist(p, self.pts[-1]) < EPS:
            self.ctx.echo("Punto repetido: se ignora.")
            return
        self._agregar(p)

    def _linea(self, a, b) -> None:
        self.ctx.execute(actions.add_line(a, b))
        self.objetos += 1

    def _agregar(self, p) -> None:
        n = len(self.pts)
        if n >= 2:
            if self.tramos:
                if n == 2 and self.con_base:            # la base, como primera línea
                    self._linea(self.pts[0], self.pts[1])
                self._linea(self.pts[-1], p)
            d = math.dist(self.pts[-1], p)
            self.largo += d
            self.ctx.echo("Tramo %d: %s   (acumulado %s)"
                          % (n - 1, self._largo_txt(d), self._largo_txt(self.largo)))
        self.pts.append(p)
        self.last_point = p
        self._pedir()

    def on_option(self, text: str) -> bool:
        t = str(text).strip()
        k = t.upper().lstrip("_")
        n = len(self.pts)
        if n < 2:
            return False                     # los puntos del tramo base: los lee IngeCAD
        if k in OPT_ANG:
            self.angulo = "deflexion" if self.angulo == "interior" else "interior"
            _set(KEY_ANGULO, self.angulo)
            self.ctx.echo("Ángulo = %s" % self._ang_txt())
        elif n == 2 and k in OPT_MODO:
            self.tramos = not self.tramos
            _set(KEY_TRAMOS, self.tramos)
            self.ctx.echo("Modo = %s" % self._modo_txt())
        elif n == 2 and k in OPT_BASE:
            self.con_base = not self.con_base
            _set(KEY_BASE, self.con_base)
            self.ctx.echo("Base = %s" % ("Sí" if self.con_base else "No"))
        elif n > 2 and k in OPT_DESHACER:
            self._deshacer()
            return True
        elif len(self._dibujados()) >= 3 and k in OPT_CERRAR:
            self._cerrar()
            return True
        else:
            try:
                r = tramo(self.pts[-2], self.pts[-1], t, self.angulo)
            except AnguloError as exc:
                self.ctx.echo(f"Tramo no válido: {exc}")
                self._pedir()
                return True
            if r is None:
                return False                 # un punto, una distancia sola: IngeCAD
            self._agregar(r[0])
            return True
        self._pedir()
        return True

    def _deshacer(self) -> None:
        q = self.pts.pop()
        if self.tramos and self.objetos:
            self.ctx.undo_last()
            self.objetos -= 1
            if len(self.pts) == 2 and self.con_base and self.objetos:
                self.ctx.undo_last()         # la base salió junto con el primer tramo
                self.objetos -= 1
        self.largo = max(0.0, self.largo - math.dist(q, self.pts[-1]))
        self.last_point = self.pts[-1]
        self.ctx.echo("Tramo deshecho (acumulado %s)" % self._largo_txt(self.largo))
        self._pedir()

    def _cerrar(self) -> None:
        pts = self._dibujados()
        if self.tramos:
            self._agregar(pts[0])
            self._terminar()
            return
        d = math.dist(pts[-1], pts[0])
        self.largo += d
        self.ctx.echo("Cierre: %s   (perímetro %s)" % (self._largo_txt(d), self._largo_txt(self.largo)))
        self.ctx.execute(actions.add_polyline(pts, closed=True))
        self.pts = []                        # ya creada: _terminar no la repite
        self.ctx.finish()

    def on_enter(self) -> None:
        self._terminar()

    def on_cancel(self) -> None:
        self._terminar()

    def _terminar(self) -> None:
        if not self.tramos and len(self.pts) > 2:
            pts = self._dibujados()
            if len(pts) >= 2:
                self.ctx.execute(actions.add_polyline(pts, closed=False))
        self.ctx.finish()

    # -- pantalla -------------------------------------------------------------------
    def _decididos(self) -> list:
        if self.tramos or len(self.pts) < 2:
            return []                        # en Tramos cada línea ya está en el dibujo
        pts = self._dibujados()
        return list(zip(pts, pts[1:]))

    def drawn_segments(self) -> list:
        return [(a[0], a[1], b[0], b[1]) for a, b in self._decididos()]

    def preview_segments(self, cursor) -> list:
        segs = self._decididos()
        if len(self.pts) == 2 and not self.con_base:
            segs = [(self.pts[0], self.pts[1])] + segs   # la base, como guía, hasta el 1er tramo
        if self.pts and cursor is not None:
            segs.append((self.pts[-1], (float(cursor[0]), float(cursor[1]))))
        return segs
