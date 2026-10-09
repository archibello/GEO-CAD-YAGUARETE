# SPDX-License-Identifier: GPL-3.0-or-later
"""ESTIRA (STRETCH) al instante y con vista previa, para IngeCAD.

El STRETCH de IngeCAD estira bien, pero:
  - el resultado no se ve al terminar: el dibujo viejo queda en pantalla
    junto al nuevo hasta que se regenera todo el modelo («Regenerando...»).
    Causa: su orden (StretchCommand) no está entre las que la vista sabe
    actualizar al momento (ToolController._patchable), así que no esconde
    la copia vieja y además tira los índices de selección y referencias;
  - mientras se busca el segundo punto sólo se ve una línea elástica: no se
    ve cómo van a quedar los objetos.

Acá, como en AutoCAD:
  - lo que la ventana atrapa entero sigue al cursor (el mismo fantasma que
    usa DESPLAZA: los textos y bloques se ven tal cual);
  - lo que se estira (un lado de un rectángulo, el extremo de una línea o de
    un arco) se dibuja estirado, resaltado, hasta el clic;
  - al hacer clic el resultado queda en el momento, sin regenerar: la orden
    dice qué objetos tocó (``targets``) y la vista esconde los viejos y
    muestra los nuevos, igual que con DESPLAZA o BORRA. DESHACER también.

Se apaga con el módulo «estirar»: IngeCAD queda como venía.
"""
from __future__ import annotations

from core import modify
from core.i18n import tr
from tools.modify import StretchTool

from .empalme import trazo

#: más objetos que se estiran (no los que se mueven enteros) y la vista
#: previa se deja: copiarlos y estirarlos en cada movimiento del ratón
#: frenaría el cursor en un plano grande
MAX_VISTA = 400


class EstirarCommand(modify.StretchCommand):
    """El StretchCommand de IngeCAD, diciendo qué objetos toca: con
    ``targets`` la vista los actualiza al momento en vez de regenerar."""

    def __init__(self, entities, rects, dx: float, dy: float) -> None:
        super().__init__(entities, rects, dx, dy)
        self.targets = self.entities


def clasificar(entities, rects):
    """(enteros, estirados): los que la ventana atrapa enteros (se mueven) y
    los que tienen sólo algunos puntos adentro (se estiran). Los que no
    tienen ningún punto adentro no cambian y no van en ninguna lista."""
    enteros, estirados = [], []
    for e in entities:
        try:
            puntos = modify.stretch_points(e)
        except Exception:  # noqa: BLE001 -- un objeto raro no corta la orden
            continue
        dentro = [modify._inside(p, rects) for p in puntos]
        if not puntos or not any(dentro):
            continue
        (enteros if all(dentro) else estirados).append(e)
    return enteros, estirados


def estirado(entity, rects, dx: float, dy: float) -> list:
    """Los trazos de cómo queda ``entity`` estirado (sobre una copia)."""
    try:
        copia = entity.copy()
        modify.stretch_entity(copia, rects, dx, dy)
        return trazo(copia)
    except Exception:  # noqa: BLE001 -- sin vista previa, nunca un error
        return []


class EstirarTool(StretchTool):
    """STRETCH de IngeCAD con vista previa y resultado al momento."""

    def start(self) -> None:
        super().start()
        self._estirados: list = []
        self.ghost_entities = None
        self.ghost_base = None

    def on_point(self, point) -> None:
        primero = self._base is None
        super().on_point(point)
        if primero and self._base is not None:
            enteros, self._estirados = clasificar(self._entities, self._rects)
            if len(self._estirados) > MAX_VISTA:
                self._estirados = []
            # lo atrapado entero: el fantasma de DESPLAZA, que sigue al cursor
            self.ghost_entities = enteros or None
            self.ghost_base = self._base

    def resaltado(self, cursor) -> dict:
        """Lo que se estira, ya estirado hasta el cursor."""
        out = {"estirado": []}
        if self._base is None or cursor is None:
            return out
        dx, dy = cursor[0] - self._base[0], cursor[1] - self._base[1]
        for e in self._estirados:
            out["estirado"] += estirado(e, self._rects, dx, dy)
        return out

    def _commit(self, dx: float, dy: float) -> None:
        self.ghost_entities = None
        self.ctx.execute(EstirarCommand(self._entities, self._rects, dx, dy))
        self.ctx.echo(tr("{count} stretched.", count=len(self._entities)))
        self.ctx.finish()

