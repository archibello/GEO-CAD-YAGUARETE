# SPDX-License-Identifier: GPL-3.0-or-later
"""Perpendicular y Apparent Intersection con guías de puntos (3.56.0).

Pedido de Fernando (29/10/2026): «extender las líneas con líneas de punto
hasta un punto flotante que se produce donde debería concretarse la
operación». Las cuentas, iguales en IngeCAD y en QGIS:

- Perpendicular: el pie desde el punto anterior sobre la RECTA de la
  línea; si cae fuera del tramo, la guía va de la punta más cercana al pie.
- Apparent Intersection: el cruce de las RECTAS de dos líneas; cada una
  que no llega tiene su guía de la punta más cercana al cruce. Paralelas:
  no hay punto.

Una línea se TOMA deteniéndose ``TOMA_MS`` encima (como en AutoCAD) y
queda tomada aunque el cursor se vaya; la tercera reemplaza a la más
vieja. El reloj lo pone cada programa (QTimer); acá sólo las cuentas.

Un tramo es (x1, y1, x2, y2); lo que venga después se ignora.
Python puro (sin Qt): el complemento de QGIS usa una copia idéntica.
"""
from __future__ import annotations

import math

TOMA_MS = 500           # detenerse medio segundo sobre una línea la toma
MAX_TOMADAS = {"PER": 1, "APP": 2}


def tramo(s):
    return (float(s[0]), float(s[1]), float(s[2]), float(s[3]))


def mismo_tramo(a, b, tol=1e-9):
    """El mismo tramo, recorrido en cualquier sentido."""
    if a is None or b is None:
        return False
    a, b = tramo(a), tramo(b)
    ida = all(abs(a[i] - b[i]) <= tol for i in range(4))
    vuelta = all(abs(a[i] - b[(i + 2) % 4]) <= tol for i in range(4))
    return ida or vuelta


def _largo2(s):
    return (s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2


def distancia(s, p):
    """Distancia de p al tramo (no a la recta)."""
    x1, y1, x2, y2 = tramo(s)
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((p[0] - x1) * dx + (p[1] - y1) * dy) / l2))
    return math.hypot(x1 + t * dx - p[0], y1 + t * dy - p[1])


def tramo_cercano(cursor, umbral, tramos):
    """El tramo (con largo) más cercano al cursor dentro de ``umbral``, o None."""
    mejor, dmin = None, None
    for s in tramos:
        if _largo2(s) <= 1e-24:
            continue
        d = distancia(s, cursor)
        if d <= umbral and (dmin is None or d < dmin):
            mejor, dmin = tramo(s), d
    return mejor


def _parametro(s, p):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    return ((p[0] - x1) * dx + (p[1] - y1) * dy) / (dx * dx + dy * dy)


def prolongacion(s, p, tol=1e-9):
    """La guía de puntos que lleva el tramo hasta p (que está sobre su
    recta): (punta más cercana, p), o None si p ya está en el tramo."""
    s = tramo(s)
    t = _parametro(s, p)
    if -tol <= t <= 1 + tol:
        return None
    punta = (s[0], s[1]) if t < 0 else (s[2], s[3])
    return (punta, (float(p[0]), float(p[1])))


def perpendicular(previo, s):
    """(pie, guías) de la perpendicular desde ``previo`` a la recta de s, o
    None si s no tiene largo o ``previo`` está sobre esa recta."""
    if previo is None:
        return None
    s = tramo(s)
    if _largo2(s) <= 1e-24:
        return None
    t = _parametro(s, previo)
    pie = (s[0] + t * (s[2] - s[0]), s[1] + t * (s[3] - s[1]))
    largo = math.sqrt(_largo2(s))
    if math.hypot(pie[0] - previo[0], pie[1] - previo[1]) <= largo * 1e-9:
        return None
    g = prolongacion(s, pie)
    return pie, ([g] if g else [])


def aparente(a, b):
    """(cruce, guías) de las rectas de a y b, o None si son paralelas o
    alguna no tiene largo."""
    a, b = tramo(a), tramo(b)
    if _largo2(a) <= 1e-24 or _largo2(b) <= 1e-24:
        return None
    x1, y1, x2, y2 = a
    x3, y3, x4, y4 = b
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    escala = math.sqrt(_largo2(a) * _largo2(b))
    if abs(d) <= escala * 1e-9:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    p = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    guias = [g for g in (prolongacion(a, p), prolongacion(b, p)) if g]
    return p, guias


class Tomadas:
    """Las líneas tomadas para PER (una) o APP (dos), y la que se está
    por tomar (el cursor encima, esperando el medio segundo)."""

    def __init__(self, modo):
        self.modo = modo
        self.lista = []
        self.espera = None

    def maximo(self):
        return MAX_TOMADAS.get(self.modo, 1)

    def tiene(self, s):
        return any(mismo_tramo(s, t) for t in self.lista)

    def esperar(self, s):
        """El cursor está sobre s (o sobre nada, None). True si hay que
        (re)arrancar el reloj: es otra línea y todavía no está tomada."""
        if s is None or self.tiene(s):
            self.espera = None
            return False
        if mismo_tramo(s, self.espera):
            return False
        self.espera = tramo(s)
        return True

    def tomar(self):
        """Se cumplió el medio segundo: la línea en espera queda tomada (la
        más vieja sale si ya había el máximo). True si cambió algo."""
        s, self.espera = self.espera, None
        if s is None or self.tiene(s):
            return False
        self.lista = (self.lista + [s])[-self.maximo():]
        return True


def calcular(modo, tomadas, encima, previo):
    """El punto flotante y sus guías para ``modo`` ("PER" o "APP").

    ``encima``: el tramo bajo el cursor (o None), que cuenta aunque todavía
    no esté tomado; ``tomadas``: una Tomadas. Devuelve (punto, guías,
    tramos usados) o None.
    """
    lista = list(tomadas.lista)
    if modo == "PER":
        s = encima if encima is not None else (lista[-1] if lista else None)
        if s is None:
            return None
        r = perpendicular(previo, s)
        return (r[0], r[1], [s]) if r else None
    if modo == "APP":
        if encima is not None and not tomadas.tiene(encima) and lista:
            par = (lista[-1], encima)
        elif len(lista) >= 2:
            par = (lista[-2], lista[-1])
        else:
            return None
        r = aparente(*par)
        return (r[0], r[1], list(par)) if r else None
    return None
