# SPDX-License-Identifier: GPL-3.0-or-later
"""CHAFLÁN (CHAMFER) al estilo AutoCAD, para IngeCAD.

El CHAMFER de IngeCAD tiene los mismos problemas que tenía el FILLET, y más:
  - sólo acepta líneas sueltas (no polilíneas, que es casi todo lo de QGIS);
  - con dos líneas que se cruzan no respeta el lado que se tocó;
  - los pedazos y el bisel nacen en la capa actual (pierden capa, color y el
    vínculo con QGIS);
  - con distancias 0 deja una línea de largo cero en vez de hacer la esquina;
  - no tiene las opciones Polilínea, Ángulo, métOdo, Múltiple ni desHacer.

Este chaflán es el Empalme de GeoCAD con otra pieza en la esquina: la misma
geometría (lado elegido, polilíneas, uniones, vista previa, resaltado) con
un bisel recto en lugar del arco. Opciones como en AutoCAD:

  Ochava (la principal y por defecto, de GeoCAD): se da el Largo (L) del
  bisel y los dos ángulos quedan iguales (A = B): en una esquina a 90° son
  135° y cada línea se corta a L/√2 de la esquina; en cualquier esquina,
  a L / (2·sen(θ/2)). El largo queda guardado hasta que se cambie (también
  al cerrar y abrir IngeCAD) /
  desHacer / Polilínea (todos los vértices) / Distancia (dist1 sobre el
  primer objeto, dist2 sobre el segundo) / Ángulo (longitud sobre el primero
  y ángulo) / Recortar / mEtodo (Ochava, Distancia o Ángulo) / Múltiple,
  y Mayús en el segundo objeto = esquina.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from core import actions
from core.i18n import tr

from .empalme import EPS, EmpalmeTool, _unit


def _archivo() -> Path:
    return Path.home() / ".config" / "geocad" / "chaflan.json"


def leer_ochava() -> float:
    """El largo de ochava guardado (0 si no hay)."""
    try:
        v = float(json.loads(_archivo().read_text(encoding="utf-8")).get("ochava", 0.0))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0
    return v if v >= 0 and math.isfinite(v) else 0.0


def guardar_ochava(valor: float) -> None:
    path = _archivo()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ochava": valor}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass                    # sin disco: vale para esta sesión


def _cortas(n: int) -> str:
    return "1 era demasiado corta" if n == 1 else f"{n} eran demasiado cortas"


class ChaflanTool(EmpalmeTool):
    """CHAMFER de AutoCAD: el Empalme de GeoCAD con un bisel en la esquina."""

    NOMBRE = "CHAMFER"
    NO_ENTRA = "GeoCAD Yaguareté: el chaflán no entra en esos tramos."
    TIPOS = ("LINE", "LWPOLYLINE")
    OPTIONS = ("Designe primera línea o "
               "[Ochava/desHacer/Polilínea/Distancia/Ángulo/Recortar/mEtodo/Múltiple]:")
    PROMPT_SEGUNDO = "Designe segunda línea o Mayús+clic para hacer esquina:"
    MSG_TIPO = "CHAFLÁN trabaja con líneas y polilíneas (no con arcos ni círculos)."

    # valores de la sesión, como en AutoCAD
    dist1 = 0.0
    dist2 = 0.0
    largo = 0.0          # método Ángulo: longitud sobre la primera línea
    angulo = 0.0         # método Ángulo: grados desde la primera línea
    metodo = "O"         # "O" ochava (por defecto), "D" distancia, "A" ángulo
    ochava = None        # método Ochava: largo del bisel (None = leer el guardado)

    def start(self) -> None:
        self.name = "CHAMFER"
        self._first = None
        self._first_pick = None
        self._await = None
        self._multiple = False
        self._done = 0
        cls = type(self)
        if cls.ochava is None:
            cls.ochava = leer_ochava()
        self._announce()
        if cls.metodo == "O" and cls.ochava <= 0:        # sin largo todavía: se pide
            self._pedir_ochava()

    def on_point(self, point) -> None:
        if self._await == "ochava":             # un clic en vez del largo: sigue con el que había
            self._await = None
        return super().on_point(point)

    def _pedir_ochava(self) -> None:
        self._await = "ochava"
        self.prompt(f"Precise largo de ochava (L) <{self._fmt(type(self).ochava or 0.0)}>:")

    def _announce(self) -> None:
        from core import trimmode

        cls = type(self)
        modo = "RECORTAR" if trimmode.trimmode() else "NO RECORTAR"
        if cls.metodo == "O":
            self.ctx.echo(f"(Modo {modo}) Ochava actual: Largo = {self._fmt(cls.ochava or 0.0)}")
        elif cls.metodo == "A":
            self.ctx.echo(f"(Modo {modo}) Longitud actual de chaflán = {self._fmt(cls.largo)}, "
                          f"Ángulo = {cls.angulo:g}")
        else:
            self.ctx.echo(f"(Modo {modo}) Distancia1 actual de chaflán = {self._fmt(cls.dist1)}, "
                          f"Distancia2 = {self._fmt(cls.dist2)}")
        self.prompt(self.OPTIONS)

    # -- la geometría: lo único distinto del empalme ----------------------------
    def _radio_actual(self, shift=None) -> float:
        """1 = chaflán con las distancias; 0 = esquina (Mayús)."""
        shift = getattr(self, "shift", False) if shift is None else shift
        return 0.0 if shift else 1.0

    def distancias(self, theta: float):
        """(d1, d2) según el método; theta = ángulo entre las dos ramas."""
        cls = type(self)
        if cls.metodo == "O":                       # A = B: la misma distancia en las dos
            largo = cls.ochava or 0.0
            if largo <= 0:
                return 0.0, 0.0
            d = largo / (2.0 * math.sin(theta / 2.0))
            return d, d
        if cls.metodo != "A":
            return cls.dist1, cls.dist2
        alfa = math.radians(cls.angulo)
        if cls.largo <= 0 or alfa <= 0:
            return 0.0, 0.0
        if alfa + theta >= math.pi - 1e-9:
            return cls.largo, float("inf")          # el bisel no llega a la otra línea
        return cls.largo, cls.largo * math.sin(alfa) / math.sin(alfa + theta)

    def _esquina(self, p, u1, u2, radio):
        cos_t = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        theta = math.acos(cos_t)
        if theta < 1e-7 or math.pi - theta < 1e-7:
            return None
        d1, d2 = (0.0, 0.0) if radio <= 0 else self.distancias(theta)
        if d1 <= EPS or d2 <= EPS:
            d1 = d2 = 0.0                          # como AutoCAD: con 0, la esquina
        if math.isinf(d2):
            return p, p, None, 0.0, d1, d2
        t1 = (p[0] + u1[0] * d1, p[1] + u1[1] * d1)
        t2 = (p[0] + u2[0] * d2, p[1] + u2[1] * d2)
        return t1, t2, None, 0.0, d1, d2

    def _union(self, c, fuente):
        from core.modify import inherit_style

        t1, t2 = c["t1"], c["t2"]
        if math.dist(t1, t2) <= EPS:
            return None
        return lambda msp: inherit_style(msp.add_line(t1, t2), fuente)

    def _paralelas(self, segundo, pick2, radio) -> bool:
        self.ctx.echo("GeoCAD Yaguareté: las líneas son paralelas.")
        return False

    def _otros(self, point):
        self.ctx.echo(self.MSG_TIPO)
        return None

    # -- opciones --------------------------------------------------------------
    def _numero(self, text):
        try:
            v = float(text.replace(",", "."))
        except ValueError:
            return None
        return v if v >= 0 else None

    def on_option(self, text: str) -> bool:
        from core import trimmode

        t = text.strip().upper().lstrip("_")
        cls = type(self)
        a = self._await
        if a in ("d1", "d2", "largo", "angulo", "ochava"):
            if not t:                                  # Enter: el valor que estaba
                v = {"d1": cls.dist1, "d2": cls.dist1 if a == "d2" else 0,
                     "largo": cls.largo, "angulo": cls.angulo,
                     "ochava": cls.ochava or 0.0}[a]
            else:
                v = self._numero(text)
                if v is None:
                    self.ctx.echo("Requiere un número positivo.")
                    return True
            if a == "d1":
                cls.dist1 = v
                self._await = "d2"
                self.prompt(f"Precise segunda distancia de chaflán <{self._fmt(v)}>:")
                return True
            if a == "ochava":
                cls.ochava, cls.metodo = v, "O"
                guardar_ochava(v)
            elif a == "d2":
                cls.dist2, cls.metodo = v, "D"
            elif a == "largo":
                cls.largo = v
                self._await = "angulo"
                self.prompt(f"Precise ángulo de chaflán desde la primera línea <{cls.angulo:g}>:")
                return True
            else:
                if v >= 180:
                    self.ctx.echo("El ángulo tiene que ser menor que 180.")
                    return True
                cls.angulo, cls.metodo = v, "A"
            self._await = None
            self._first_prompt()
            return True
        if a == "trim":
            if t.startswith("N"):
                trimmode.set_trimmode(False)
            elif t[:1] in ("R", "T") or not t:
                trimmode.set_trimmode(bool(t) or trimmode.trimmode())
            else:
                self.ctx.echo("Requiere Recortar o No recortar.")
                return True
            self._await = None
            self._first_prompt()
            return True
        if a == "metodo":
            if t[:1] == "O":
                cls.metodo = "O"
            elif t[:1] == "A":
                cls.metodo = "A"
            elif t[:1] == "D":
                cls.metodo = "D"
            elif t:
                self.ctx.echo("Requiere Ochava, Distancia o Ángulo.")
                return True
            self._await = None
            self._first_prompt()
            return True
        if self._first is not None:
            return False
        if t in ("O", "OCHAVA", "L", "LARGO"):
            self._pedir_ochava()
            return True
        if t in ("D", "DISTANCIA", "DISTANCE"):
            self._await = "d1"
            self.prompt(f"Precise primera distancia de chaflán <{self._fmt(cls.dist1)}>:")
            return True
        if t in ("A", "ANGULO", "ÁNGULO", "ANGLE"):
            self._await = "largo"
            self.prompt(f"Precise longitud de chaflán en la primera línea <{self._fmt(cls.largo)}>:")
            return True
        if t in ("R", "RECORTAR", "T", "TRIM"):
            self._await = "trim"
            actual = "Recortar" if trimmode.trimmode() else "No recortar"
            self.prompt(f"Indique opción de modo Recortar [Recortar/No recortar] <{actual}>:")
            return True
        if t in ("E", "METODO", "MÉTODO", "METHOD"):
            self._await = "metodo"
            actual = {"A": "Ángulo", "D": "Distancia"}.get(cls.metodo, "Ochava")
            self.prompt(f"Indique método [Ochava/Distancia/Ángulo] <{actual}>:")
            return True
        if t in ("M", "MULTIPLE", "MÚLTIPLE"):
            self._multiple = True
            self._first_prompt()
            return True
        if t in ("P", "POLILINEA", "POLILÍNEA", "POLYLINE"):
            self._await = "polyline"
            self.prompt("Designe polilínea 2D:")
            return True
        if t in ("H", "U", "DESHACER", "UNDO"):
            if self._done:
                self.ctx.undo_last()
                self._done -= 1
            else:
                self.ctx.echo("El comando se ha deshecho completamente.")
            self._first_prompt()
            return True
        return False

    def on_enter(self) -> None:
        if self._await in ("d1", "d2", "largo", "angulo", "ochava", "trim", "metodo"):
            self.on_option("")
            return
        self.ctx.finish()

    # -- opción Polilínea: todos los vértices -----------------------------------
    def _polilinea_entera(self, point):
        pl = self.ctx.services.pick_entity(point)
        if pl is None or pl.dxftype() != "LWPOLYLINE":
            self.ctx.echo("No es una polilínea 2D.")
            return
        filas = [list(f) for f in pl.get_points("xyseb")]
        n = len(filas)
        cerrada = bool(pl.closed)
        pts = [(f[0], f[1]) for f in filas]
        largos = [math.dist(pts[k], pts[(k + 1) % n]) for k in range(n)]
        usado_ini = [0.0] * n        # lo que ya se comió del principio de cada tramo
        usado_fin = [0.0] * n        # y del final
        cortes, cortos = {}, 0
        for v in (range(n) if cerrada else range(1, n - 1)):
            ant, sig = (v - 1) % n, (v + 1) % n
            if abs(filas[ant][4]) > EPS or abs(filas[v][4]) > EPS:
                continue                              # tramos en arco: no
            p = pts[v]
            u_ant = _unit(pts[ant][0] - p[0], pts[ant][1] - p[1])
            u_sig = _unit(pts[sig][0] - p[0], pts[sig][1] - p[1])
            if u_ant is None or u_sig is None:
                continue
            r = self._esquina(p, u_ant, u_sig, 1.0)
            if r is None:
                continue                              # alineados
            t1, t2, _c, _b, d_ant, d_sig = r
            if math.dist(t1, t2) <= EPS:
                continue
            if (usado_ini[ant] + d_ant > largos[ant] + 1e-9
                    or usado_fin[v] + d_sig > largos[v] + 1e-9):
                cortos += 1
                continue
            usado_fin[ant] = d_ant
            usado_ini[v] = d_sig
            cortes[v] = (t1, t2)
        if not cortes:
            self.ctx.echo("0 líneas achaflanadas" + (f" ({_cortas(cortos)})." if cortos else "."))
            self._await = None
            self._first_prompt() if self._multiple else self.ctx.finish()
            return
        nuevas = []
        for k, f in enumerate(filas):
            if k in cortes:
                t1, t2 = cortes[k]
                nuevas.append([t1[0], t1[1], f[2], f[3], 0.0])
                nuevas.append([t2[0], t2[1], f[2], f[3], f[4]])
            else:
                nuevas.append(f)

        def fabrica(msp, e=pl, rows=nuevas):
            clon = e.copy()
            clon.set_points([tuple(r) for r in rows], format="xyseb")
            msp.add_entity(clon)
            return clon

        self.ctx.execute(actions.ReplaceEntitiesCommand(self.NOMBRE, [pl], [fabrica]))
        n = len(cortes)
        msg = f"{n} línea achaflanada" if n == 1 else f"{n} líneas achaflanadas"
        if cortos:
            msg += f"; {_cortas(cortos)}"
        self.ctx.echo(msg + ".")
        self._await = None
        self._after_fillet()
