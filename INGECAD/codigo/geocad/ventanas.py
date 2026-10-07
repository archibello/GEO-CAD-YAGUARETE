# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventanas de GeoCAD en IngeCAD: elegir los módulos (al instalar y desde
GeoCAD > Módulos...). Sin ventana (pruebas), sólo informa."""
from __future__ import annotations

from . import modulos

PROGRAMA = "ingecad"


def _qtwidgets():
    try:
        from PySide6 import QtWidgets
        return QtWidgets if QtWidgets.QApplication.instance() is not None else None
    except ImportError:
        return None


def _aplicar(window) -> None:
    from . import aplicar_modulos

    aplicar_modulos(window)


def elegir_modulos(window, echo, primera_vez: bool = False) -> None:
    QtWidgets = _qtwidgets()
    if QtWidgets is None or window is None:
        if primera_vez and not modulos.elegido(PROGRAMA):
            modulos.guardar(PROGRAMA, modulos.estado(PROGRAMA))
        echo("Módulos de GeoCAD activos: " + modulos.resumen(PROGRAMA) + ".")
        return
    from . import modulos_ui

    nuevo = modulos_ui.elegir(QtWidgets, window, PROGRAMA, primera_vez)
    if nuevo is None:
        return
    _aplicar(window)
    echo("Módulos de GeoCAD activos: " + modulos.resumen(PROGRAMA) + ".")


def primera_eleccion(window, echo) -> None:
    """Lo llama el instalador: la primera vez se eligen los módulos (en una
    actualización ya están elegidos y no se pregunta de nuevo)."""
    if modulos.elegido(PROGRAMA) and not modulos.nuevos(PROGRAMA):
        return
    elegir_modulos(window, echo, primera_vez=not modulos.elegido(PROGRAMA))
    if modulos.nuevos(PROGRAMA):
        modulos.aceptar_nuevos(PROGRAMA)       # cancelado: valores por defecto, sin volver a preguntar
