# SPDX-License-Identifier: GPL-3.0-or-later
"""Agarres en el cursor de GeoCAD (módulo «Agarres de vértices», 3.69): las decisiones.

Pedido de Fernando (05/11/2026): la herramienta de vértices de QGIS no responde a las ayudas
al dibujo ni a las medidas escritas. Acordado: como en AutoCAD, lo designado con el cursor
muestra agarres; clic en uno y se mueve como cualquier comando. Mayús + clic marca varios,
el agarre del medio de un tramo agrega un vértice y Supr borra los marcados.

Python puro; el mapa y las geometrías están en dibujo/agarres.py.
"""
from __future__ import annotations

#: más que esto, no se muestran: serían una mancha y demorarían cada selección
LIMITE_OBJETOS = 200
LIMITE_AGARRES = 3000


def mas_cercano(puntos, x, y, tol):
    """Índice del punto (x, y) más cercano dentro de la tolerancia, o None."""
    mejor, mejor_d = None, None
    for i, (px, py) in enumerate(puntos):
        d = max(abs(px - x), abs(py - y))
        if d <= tol and (mejor_d is None or d < mejor_d):
            mejor, mejor_d = i, d
    return mejor


def accion_clic(es_medio: bool, marcado: bool, mayus: bool) -> str:
    """Qué hace un clic sobre un agarre."""
    if mayus:
        if es_medio:
            return "nada"
        return "desmarcar" if marcado else "marcar"
    if es_medio:
        return "insertar"
    return "mover_marcados" if marcado else "mover"


def indices_para_borrar(por_posicion):
    """De cada posición, un solo índice (el anillo repite el vértice de cierre), de mayor a
    menor para que borrar uno no corra los otros."""
    return sorted((min(v) for v in por_posicion.values()), reverse=True)


def conserva_forma(antes, despues) -> bool:
    """¿Sigue con las mismas partes y anillos? antes/después: anillos por parte."""
    return bool(despues) and list(antes) == list(despues)
