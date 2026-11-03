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
- Parallel (3.62.0, Fernando 03/11/2026): la línea elegida queda TOMADA y
  resaltada toda la operación (las que se cruzan después no la cambian);
  el punto flotante va donde la paralela por el punto anterior corta el
  objeto bajo el cursor (o su prolongación), o la prolongación de una
  línea cercana que el cursor cruza al seguir la paralela.

Una línea se TOMA deteniéndose ``TOMA_MS`` encima (como en AutoCAD) y
queda tomada aunque el cursor se vaya; la tercera reemplaza a la más
vieja. El reloj lo pone cada programa (QTimer); acá sólo las cuentas.

Un tramo es (x1, y1, x2, y2); lo que venga después se ignora.
Python puro (sin Qt): el complemento de QGIS usa una copia idéntica.
"""
from __future__ import annotations

import math

TOMA_MS = 500           # detenerse medio segundo sobre una línea la toma
MAX_TOMADAS = {"PER": 1, "APP": 2, "PAR": 1}
LEJOS = 20              # PAR: las prolongaciones se buscan hasta 20 veces el radio del cursor


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
        (re)arrancar el reloj: es otra línea y todavía no está tomada.
        PAR: la línea tomada queda fija hasta el punto (o Esc)."""
        if s is None or self.tiene(s) or (self.modo == "PAR" and self.lista):
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


def paralela(previo, ref, cursor, umbral, tramos=()):
    """(punto, guías, tramos usados) de Parallel, o None.

    La paralela a ``ref`` por ``previo``; el punto, en este orden:
    1. donde corta la RECTA del objeto bajo el cursor (a ``umbral`` o
       menos), aunque quede lejos del cursor;
    2. donde corta la prolongación de otro tramo de ``tramos``, si ese
       cruce está a ``umbral`` o menos del cursor;
    3. el punto de la paralela más cercano al cursor, si está a ``umbral``.
    Guías: la paralela desde ``previo`` y la prolongación del objeto.
    """
    if previo is None or ref is None or cursor is None:
        return None
    ref = tramo(ref)
    l2 = _largo2(ref)
    if l2 <= 1e-24:
        return None
    largo = math.sqrt(l2)
    ux, uy = (ref[2] - ref[0]) / largo, (ref[3] - ref[1]) / largo
    px, py = float(previo[0]), float(previo[1])
    eje = (px, py, px + ux * largo, py + uy * largo)
    tol = max(umbral * 1e-6, largo * 1e-9)

    def sobre(p):            # lejos del punto anterior (no es él mismo)
        return abs((p[0] - px) * ux + (p[1] - py) * uy) > tol

    def resultado(p, s=None):
        guias = [((px, py), (float(p[0]), float(p[1])))]
        if s is not None:
            g = prolongacion(s, p)
            if g:
                guias.append(g)
        return (float(p[0]), float(p[1])), guias, ([ref, tramo(s)] if s is not None else [ref])

    otros = [tramo(s) for s in tramos if _largo2(s) > 1e-24 and not mismo_tramo(s, ref)]
    mejor = None
    for s in otros:                                   # 1. el objeto bajo el cursor
        d = distancia(s, cursor)
        if d > umbral or (mejor is not None and d >= mejor[0]):
            continue
        r = aparente(eje, s)
        if r is not None and sobre(r[0]):
            mejor = (d, r[0], s)
    if mejor is None:                                 # 2. la prolongación que cruza
        for s in otros:
            r = aparente(eje, s)
            if r is None or not sobre(r[0]):
                continue
            d = math.hypot(r[0][0] - cursor[0], r[0][1] - cursor[1])
            if d <= umbral and (mejor is None or d < mejor[0]):
                mejor = (d, r[0], s)
    if mejor is not None:
        return resultado(mejor[1], mejor[2])
    t = (cursor[0] - px) * ux + (cursor[1] - py) * uy  # 3. sobre la paralela
    p = (px + t * ux, py + t * uy)
    if abs(t) > tol and math.hypot(p[0] - cursor[0], p[1] - cursor[1]) <= umbral:
        return resultado(p)
    return None


def calcular(modo, tomadas, encima, previo, cursor=None, umbral=0.0, tramos=()):
    """El punto flotante y sus guías para ``modo`` ("PER", "APP" o "PAR").

    ``encima``: el tramo bajo el cursor (o None), que cuenta aunque todavía
    no esté tomado; ``tomadas``: una Tomadas. PAR usa además el cursor, el
    umbral y los tramos cercanos (ver paralela). Devuelve (punto, guías,
    tramos usados) o None.
    """
    lista = list(tomadas.lista)
    if modo == "PAR":
        return paralela(previo, lista[-1], cursor, umbral, tramos) if lista else None
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
