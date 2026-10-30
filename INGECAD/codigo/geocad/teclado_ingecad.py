# SPDX-License-Identifier: GPL-3.0-or-later
"""El teclado va siempre a la línea de comandos en IngeCAD (módulo «Teclado», 3.59).

Pedido de Fernando (30/10/2026): «que siempre la prioridad de ingreso de los
comandos sea por teclado». IngeCAD ya pasa a la línea de comandos lo que se
escribe sobre el dibujo (MainWindow.eventFilter -> CommandLine.type_ahead),
pero sólo si el foco está en el dibujo: después de un clic en el panel de
capas, la paleta Properties, una barra o al cerrar un diálogo, había que
hacer clic en la línea. Con el módulo, un filtro de la aplicación hace lo
mismo desde cualquier lugar de la ventana principal donde no se esté
escribiendo (las reglas, en teclado.py, las mismas que en QGIS). El dibujo
lo sigue manejando IngeCAD; apagado el módulo, el filtro se quita.
"""
from __future__ import annotations

from . import modulos

PROGRAMA = "ingecad"
PLUGIN_ID = "geocad"

_teclado = None


def _plugin_activo(window) -> bool:
    mgr = getattr(window, "plugins", None)
    try:
        return mgr is None or bool(mgr.is_active(PLUGIN_ID))
    except Exception:  # noqa: BLE001
        return True


def _comando_en_marcha(window) -> bool:
    try:
        tools = window.tools
        return bool(tools.active() or getattr(tools, "_selecting_for", None) is not None
                    or window.dispatcher.pending_prompt is not None)
    except Exception:  # noqa: BLE001
        return False


def _propio(window, w) -> bool:
    """El dibujo (y lo que tenga adentro) ya lo maneja IngeCAD."""
    vp = getattr(window, "viewport", None)
    if vp is None:
        return False
    try:
        return w is vp or vp.isAncestorOf(w)
    except (RuntimeError, TypeError):
        return False


def _linea(window):
    if not _plugin_activo(window):
        return None
    cl = getattr(window, "command_line", None)
    return getattr(cl, "input", None)


def aplicar(window) -> None:
    """Instala o quita el filtro según el módulo (al abrir un dibujo y al
    cambiar la elección de módulos)."""
    global _teclado
    quiere = window is not None and modulos.activo(PROGRAMA, "teclado")
    if not quiere:
        quitar()
        return
    if _teclado is not None:
        return
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        return
    from .teclado import Teclado

    _teclado = Teclado(
        QtCore, QtWidgets, lambda: window,
        lambda: _linea(window),
        lambda: _comando_en_marcha(window),
        lambda w: _propio(window, w),
        lambda ev: window.command_line.type_ahead(ev))
    _teclado.instalar()


def quitar() -> None:
    global _teclado
    if _teclado is not None:
        _teclado.quitar()
        _teclado = None


def activo() -> bool:
    return _teclado is not None
