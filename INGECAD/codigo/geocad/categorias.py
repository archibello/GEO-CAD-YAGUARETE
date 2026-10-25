# SPDX-License-Identifier: GPL-3.0-or-later
"""Administrar botones en IngeCAD (3.38.0): las categorías como barras.

Las barras de fábrica son la barra GeoCAD (la arma IngeCAD con la lista
del plugin) y Yaguareté Tools (la arma yaguarete.py). Cada botón se conoce
por su orden (FILLET, SHPTABLE...). Lo que se elige se guarda en el núcleo
(botones.py, ~/.config/geocad/botones.json, sección «ingecad»); las barras
las pone botones_barras.py, que también lo deja todo como estaba.
"""
from __future__ import annotations

from . import botones, botones_barras

PROGRAMA = "ingecad"

#: los temas de la barra GeoCAD y de Yaguareté Tools, con su nombre para
#: «Una por tema» (la idea de Fernando del 08/10/2026: barras por tema)
NOMBRES_TEMA = {
    "seleccion": "Selección", "datos": "Datos", "edicion": "Edición", "orden": "Orden",
    "bloques": "Bloques", "cotas": "Cotas", "tablas": "Tablas e imágenes pegadas",
    "impresion": "Impresión", "puente": "Puente", "intercambio": "Importar y exportar",
    "dibujo": "Dibujo", "imagenes": "Imágenes",
}


def tema_de(orden: str):
    from . import barra, yaguarete
    return yaguarete.TEMAS.get(orden) or barra.TEMAS.get(orden)


def id_de(accion):
    try:
        return accion.property("geocad_orden") or None
    except RuntimeError:
        return None


def fabricas(window) -> list:
    """[(título, barra)]: la barra GeoCAD y Yaguareté Tools, las que haya."""
    salida = []
    bar = getattr(window, "_plugin_toolbars", {}).get("geocad")
    if bar is not None:
        salida.append((bar.windowTitle() or "GeoCAD Yaguareté", bar))
    yag = getattr(window, "_geocad_yaguarete", (None, []))[0]
    if yag is not None:
        salida.append((yag.windowTitle(), yag))
    return salida


def fabrica(window) -> list:
    """[(barra, [órdenes])] como las arma hoy GeoCAD."""
    return [(n, [b for b, _a in fila])
            for n, fila in botones_barras.elementos(fabricas(window), id_de)]


def _nueva_barra(window):
    def nueva(nombre):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QToolBar
        bar = QToolBar(nombre, window)
        bar.setObjectName(botones.objeto_barra(nombre))
        bar.setMovable(True)
        window.addToolBar(Qt.TopToolBarArea, bar)
        return bar
    return nueva


def _divisor(bar):
    from .barra import _divisor as divisor
    return bar.addWidget(divisor(bar))


def aplicar(window) -> None:
    """Pone las categorías guardadas (o deja la fábrica). Se llama cada vez
    que IngeCAD rearma la barra GeoCAD (al arrancar, al cambiar los módulos)."""
    fab = fabricas(window)
    if not fab:
        return
    botones_barras.aplicar(window, fab, id_de, lambda fabrica: botones.barras(PROGRAMA, fabrica),
                           _nueva_barra(window), _divisor)


def restaurar(window) -> None:
    botones_barras.restaurar(window)


def cmd_administrar(ctx, *args) -> None:
    """GEOBUTTONS: la ventana Administrar botones."""
    from . import botones_ui, ventanas, yaguarete

    window = getattr(ctx, "host", None)
    QtWidgets = ventanas._qtwidgets()
    if window is None or QtWidgets is None:
        ctx.echo("Administrar botones necesita la ventana de IngeCAD.")
        return
    botones_barras.restaurar(window)            # la fábrica, para leer los botones
    try:
        elems = botones_barras.elementos(fabricas(window), id_de)
        fab = [(n, [b for b, _a in fila]) for n, fila in elems]
        etiquetas, iconos = {}, {}
        for _n, fila in elems:
            for b, a in fila:
                texto, _o = yaguarete.separar_orden(a.text().replace("&", ""))
                etiquetas[b] = f"{texto or b}  ({b})"
                iconos[b] = a.icon()
        if not fab:
            ctx.echo("No hay barras de GeoCAD a la vista (Herramientas > Complementos).")
            return
        if botones_ui.administrar(QtWidgets, window, PROGRAMA, fab, etiquetas, iconos,
                                  tema_de, NOMBRES_TEMA):
            ctx.echo("Botones de GeoCAD: categorías guardadas.")
    finally:
        aplicar(window)
