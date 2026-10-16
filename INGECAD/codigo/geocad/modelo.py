# SPDX-License-Identifier: GPL-3.0-or-later
"""Crear objetos SIEMPRE en el espacio modelo (3.25.4).

``AddEntityCommand`` de IngeCAD crea en el espacio ACTIVO: con la pestaña de
una presentación abierta, el objeto cae en el papel. Para lo que es un dato
del terreno (SHP importados o conectados, sus rótulos, imágenes
georreferenciadas) eso es un error: Fernando corrió ROTULOSIG con la lámina
abierta y 652 rótulos de 250 m de alto quedaron en el papel, a 7.300 km de
una hoja de 0,84 m; la lámina se veía como una cuadrícula con diagonales y
un cuadro negro (16/10/2026).
"""
from __future__ import annotations

from core.actions import AddEntityCommand


class AddToModelCommand(AddEntityCommand):
    """Como ``AddEntityCommand``, pero siempre en el espacio modelo."""

    def space(self, document):
        return document.doc.modelspace()
