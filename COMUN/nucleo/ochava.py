# SPDX-License-Identifier: GPL-3.0-or-later
"""La cuenta del CHAFLÁN de GeoCAD, compartida por IngeCAD y QGIS (3.57.0).

Ochava (O), la opción principal y por defecto (3.15.0, Fernando): se da el
Largo (L) del bisel y los dos ángulos quedan iguales (A = B). En una esquina
a 90° son 135° y cada línea se corta a L/√2 de la esquina; en cualquier
esquina, a L / (2·sen(θ/2)), con θ el ángulo entre las dos ramas.
Distancia (D): dist1 sobre la primera línea, dist2 sobre la segunda.
Ángulo (A): longitud sobre la primera línea y ángulo desde ella.

El largo de ochava queda guardado hasta que se cambie, el mismo para los dos
programas (3.57.0: «compartido»): ~/.config/geocad/chaflan.json.

Python puro (sin Qt ni IngeCAD).
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def archivo() -> Path:
    return Path.home() / ".config" / "geocad" / "chaflan.json"


def leer_ochava() -> float:
    """El largo de ochava guardado (0 si no hay)."""
    try:
        v = float(json.loads(archivo().read_text(encoding="utf-8")).get("ochava", 0.0))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0
    return v if v >= 0 and math.isfinite(v) else 0.0


def guardar_ochava(valor: float) -> None:
    path = archivo()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ochava": valor}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass                    # sin disco: vale para esta sesión


def distancia_ochava(largo: float, theta: float) -> float:
    """Cuánto se corta cada rama para un bisel de ``largo`` con A = B."""
    if largo <= 0:
        return 0.0
    return largo / (2.0 * math.sin(theta / 2.0))


def distancias(metodo: str, theta: float, ochava: float = 0.0, dist1: float = 0.0,
               dist2: float = 0.0, largo: float = 0.0, angulo: float = 0.0):
    """(d1, d2) según el método ("O", "D" o "A"); theta = ángulo entre las dos
    ramas, en radianes. d2 = inf: con Ángulo, el bisel no llega a la otra."""
    if metodo == "O":
        d = distancia_ochava(ochava or 0.0, theta)
        return d, d
    if metodo != "A":
        return dist1, dist2
    alfa = math.radians(angulo)
    if largo <= 0 or alfa <= 0:
        return 0.0, 0.0
    if alfa + theta >= math.pi - 1e-9:
        return largo, float("inf")
    return largo, largo * math.sin(alfa) / math.sin(alfa + theta)
