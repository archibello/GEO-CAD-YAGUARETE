# SPDX-License-Identifier: GPL-3.0-or-later
"""Elegir objetos tapados con clics repetidos (módulo «Objetos tapados», 3.68).

Pedido de Fernando (05/11/2026): poder seleccionar objetos tapados por otros, sin
modificar las bases de datos. Acordado: en la capa activa, cada clic en el mismo
punto pasa al objeto siguiente de la pila y suelta el anterior; lo designado en
otro lugar se conserva y lo que ya estaba designado antes de empezar, también.

Python puro: quién dibuja y quién selecciona es de commands.py y editkit.py.
"""
from __future__ import annotations


class Pila:
    """Los objetos apilados del último clic y cuál está elegido."""

    def __init__(self):
        self.olvidar()

    def olvidar(self) -> None:
        self.capa = None
        self.x = self.y = None
        self.fids = []
        self.i = 0
        self.ya_estaba = False

    def activa(self) -> bool:
        return len(self.fids) >= 2

    def actual(self):
        return self.fids[self.i] if self.fids else None

    def _mismo_lugar(self, capa, x, y, tol) -> bool:
        return (self.activa() and capa == self.capa
                and abs(x - self.x) <= tol and abs(y - self.y) <= tol)

    def clic(self, capa, x, y, tol, apilados, seleccion):
        """Devuelve (objeto a elegir, objeto a soltar); (None, None) si no hay nada.

        apilados: los objetos en el punto, el de siempre primero.
        seleccion: lo designado ahora."""
        soltar = None
        if self._mismo_lugar(capa, x, y, tol):
            if not self.ya_estaba:
                soltar = self.actual()
            self.i = (self.i + 1) % len(self.fids)
        else:
            self.olvidar()
            if not apilados:
                return None, None
            self.capa, self.x, self.y, self.fids = capa, x, y, list(apilados)
        elegir = self.actual()
        self.ya_estaba = elegir in seleccion
        return elegir, soltar

    def quitar(self, apilados, seleccion):
        """Mayús + clic: el primero de la pila que esté designado, aunque esté tapado."""
        self.olvidar()
        for fid in apilados:
            if fid in seleccion:
                return fid
        return apilados[0] if apilados else None
