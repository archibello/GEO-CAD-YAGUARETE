"""Imágenes nuevas que IngeCAD no dibuja (3.36.0, encontrado por Fernando).

Cuando IngeCAD CREA una imagen (pegar, en el mismo dibujo o desde otro;
COPIA; GIRA, ESCALA o SIMETRÍA con copia; rehacer una de esas) la manda a
su capa provisoria de dibujo, que no dibuja imágenes (decodificar el archivo
en cada refresco la congelaba), y nadie la vuelve a dibujar: queda vacía o
negra hasta un REGEN. Sus agarres sí están, en su lugar: por eso, con GIRA
con copia, los agarres aparecían girados sobre la original, que se veía
derecha (la copia girada era invisible). Reproducido con la ventana real de
IngeCAD 0.6.8.2 (banco en el scratchpad de la sesión del 24/10/2026).

GeoCAD, después de cada comando, de cada U o rehacer y de cada redibujo de
entidades: si quedó una imagen sin textura en la capa provisoria, la saca
de ahí y pide el redibujo (como hace GEORREF con la imagen rehecha). Va con
el módulo «georref» (Imágenes georreferenciadas).
"""
from __future__ import annotations

import time

_activo_cache = [0.0, False]
METODOS = ("_execute_command", "after_history_change", "redraw_entities")


def _activo() -> bool:
    ahora = time.monotonic()
    if ahora - _activo_cache[0] > 2.0:
        _activo_cache[0] = ahora
        from . import modulos
        _activo_cache[1] = modulos.activo("ingecad", "georref")
    return _activo_cache[1]


def sin_textura(controlador) -> list:
    """Las imágenes de la capa provisoria que la pantalla no tiene."""
    escena = getattr(controlador.window.viewport, "_scene", None)
    con_textura = {im.handle for im in getattr(escena, "images", None) or []}
    return [e for e in list(getattr(controlador, "_pending_render", None) or [])
            if e.is_alive and e.dxftype() == "IMAGE" and e.dxf.handle not in con_textura]


def _regenerar(ventana) -> None:
    regen = getattr(ventana, "regen_in_background", None) or ventana.regen_in_memory
    try:
        from PySide6 import QtCore
    except Exception:  # noqa: BLE001 -- sin Qt (pruebas): en el acto
        regen()
        return
    QtCore.QTimer.singleShot(0, regen)


def revisar(controlador) -> bool:
    """Saca las imágenes sin textura de la capa provisoria y pide el
    redibujo. True si había alguna."""
    faltan = sin_textura(controlador)
    if not faltan:
        return False
    for e in faltan:
        controlador._pending_render.remove(e)
    try:
        controlador._refresh_overlay()
    except Exception:  # noqa: BLE001
        pass
    _regenerar(controlador.window)
    return True


def _envolver(original):
    def metodo(self, *args, **kwargs):
        resultado = original(self, *args, **kwargs)
        try:
            if _activo():
                revisar(self)
        except Exception:  # noqa: BLE001 -- ante la duda, IngeCAD como venía
            pass
        return resultado

    metodo._puente_original = original
    metodo._puente_fabrica = _envolver
    metodo.__name__ = getattr(original, "__name__", "metodo")
    return metodo


def instalar() -> None:
    try:
        from views.tool_controller import ToolController
    except Exception:  # noqa: BLE001 -- sin la vista de IngeCAD (pruebas)
        return
    from .dibujo import envolver
    for nombre in METODOS:
        if hasattr(ToolController, nombre):
            envolver(ToolController, nombre, _envolver, reemplazar=True)
