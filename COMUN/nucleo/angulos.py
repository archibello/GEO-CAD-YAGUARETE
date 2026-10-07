# SPDX-License-Identifier: GPL-3.0-or-later
"""Ángulos al estilo de Dibujo CAD, iguales en QGIS y en IngeCAD.

    45  45.5  45d30'15"  50g  0.78r       grados, GMS, centesimales, radianes
    @d<a     interior en el vértice, antihorario desde el tramo anterior
             (180 = recto); en el primer tramo, absoluto (0 = este)
    @d<<a    fuerza absoluto
    30dI / 30dD   deflexión a la Izquierda / Derecha del tramo
    N45d30'15"E   rumbo, siempre absoluto

Python puro: lo usan los dos programas.
"""
from __future__ import annotations

import math
import re

class AnguloError(ValueError):
    pass


_NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_DMS_RE = re.compile(
    r"^(?P<sign>[+-]?)(?P<d>\d+(?:\.\d*)?|\.\d+)\s*[d°]"
    r"(?:\s*(?P<m>\d+(?:\.\d*)?)\s*')?"
    r"(?:\s*(?P<s>\d+(?:\.\d*)?)\s*(?:\"|'')?)?$", re.I)
_BEARING_RE = re.compile(r"^(?P<ns>[NS])(?P<ang>.*?)(?P<ew>[EWO])$", re.I)
_DEFLECT_RE = re.compile(r"^(?P<ang>.+?)(?P<side>[Ii]|(?<=[d°'\"])D)$")
_POLAR_RE = re.compile(rf"^(?P<pre>[@#]?)\s*(?P<d>{_NUM})\s*<\s*(?P<a>.+)$")


def _num(text: str) -> float:
    if not re.match("^" + _NUM + "$", text):
        raise AnguloError(f'valor numérico no válido: "{text}"')
    return float(text)


def grados(text: str) -> float:
    """45, 45.5, 45d30'15", 50g, 0.78r -> grados decimales."""
    t = text.strip().replace(" ", "")
    if not t:
        raise AnguloError("ángulo vacío")
    m = _DMS_RE.match(t)
    if m:
        mins, secs = float(m.group("m") or 0), float(m.group("s") or 0)
        if mins >= 60 or secs >= 60:
            raise AnguloError(f'minutos y segundos deben ser menores que 60: "{text}"')
        deg = float(m.group("d")) + mins / 60.0 + secs / 3600.0
        return -deg if m.group("sign") == "-" else deg
    low = t.lower()
    if low.endswith("g"):
        return _num(t[:-1]) * 0.9
    if low.endswith("r"):
        return math.degrees(_num(t[:-1]))
    return _num(t)


def _rumbo(ns: str, ang: float, ew: str) -> float:
    ns, ew = ns.upper(), ew.upper().replace("O", "W")
    if ns == "N":
        return 90.0 - ang if ew == "E" else 90.0 + ang
    return 270.0 + ang if ew == "E" else 270.0 - ang


def direccion(text: str, ref, rel: bool = True, modo_rel: str = "interior") -> float:
    """Texto del ángulo -> dirección absoluta en grados (0 = este, antihorario).

    ``ref`` es la dirección (grados) del tramo anterior, o None si no hay.
    Mismas reglas que ``parse_angle`` de Dibujo CAD (units.py)."""
    t = text.strip().replace(" ", "")
    forzar_abs = t.startswith("<")
    if forzar_abs:
        t = t[1:]
    up = t.upper()
    cardinal = {"N": 90.0, "S": 270.0, "E": 0.0, "W": 180.0, "O": 180.0}
    if up in cardinal:
        return cardinal[up]
    m = _BEARING_RE.match(t)
    if m:
        a = grados(m.group("ang")) if m.group("ang") else 0.0
        if a < 0 or a > 90:
            raise AnguloError(f'el ángulo de un rumbo va de 0 a 90: "{text}"')
        return _rumbo(m.group("ns"), a, m.group("ew"))
    d = _DEFLECT_RE.match(t)
    if d:
        if ref is None:
            raise AnguloError("no hay un tramo anterior desde el cual medir la deflexión")
        sign = 1.0 if d.group("side").upper() == "I" else -1.0
        return ref + sign * grados(d.group("ang"))
    user = grados(t)
    if rel and ref is not None and not forzar_abs:
        cero = ref + 180.0 if modo_rel == "interior" else ref
        return cero + user
    return user


def _fmt(value: float) -> str:
    text = f"{value:.12f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def reescribir(text: str, ref, relativa_sin_arroba: bool = False,
               rel: bool = True, modo_rel: str = "interior"):
    """Una entrada polar ``[@|#]d<ángulo`` -> la misma con el ángulo ya
    convertido a dirección absoluta en grados decimales, que es lo que
    entiende IngeCAD. None si no es una entrada polar.

    El ángulo relativo al tramo sólo se aplica a entradas relativas
    (``@``, o sin prefijo cuando la entrada dinámica las toma relativas);
    a una polar absoluta (``d<a`` desde 0,0 o ``#d<a``) sólo se le
    traduce el formato (45d30'15", rumbos...)."""
    m = _POLAR_RE.match(text.strip())
    if m is None:
        return None
    pre = m.group("pre")
    es_relativa = pre == "@" or (pre == "" and relativa_sin_arroba)
    ang = direccion(m.group("a"), ref if es_relativa else None, rel, modo_rel)
    return f"{pre}{m.group('d')}<{_fmt(ang)}"


