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


def _ordenes_menu(entradas):
    """Los MenuItem del menú GeoCAD, también los de los submenús."""
    for e in entradas:
        if hasattr(e, "command"):
            yield e
        elif hasattr(e, "items"):
            yield from _ordenes_menu(e.items)


def bancos(window) -> list:
    """[(botones.BANCO + tema, [acciones])]: todo lo de GeoCAD en los bancos
    Configuración, Edición y Dibujo de Administrar botones (3.65.0, como los de
    QGIS). Lo que está en una barra de fábrica va con ese mismo botón; lo que
    sólo está en el menú, con uno propio que la ventana guarda para siempre."""
    acciones = [a for _n, fila in botones_barras.elementos(fabricas(window), id_de, window)
                for _b, a in fila]
    hay = {id_de(a) for a in acciones}
    propias = getattr(window, "_geocad_banco", None)
    if propias is None:
        propias = {}
        window._geocad_banco = propias
    try:
        from . import construir_spec
        items = list(_ordenes_menu(construir_spec(completo=True).menu))
    except Exception:  # noqa: BLE001 - sin el menú, sólo los botones de las barras
        items = []
    for item in items:
        orden = item.command
        if orden in hay:
            continue
        hay.add(orden)
        if orden not in propias:
            try:
                propias[orden] = _accion_menu(window, item)
            except Exception:  # noqa: BLE001 - sin Qt: esa orden sigue sólo en el menú
                continue
        acciones.append(propias[orden])
    return botones.bancos(PROGRAMA, acciones, id_de)


def _accion_menu(window, item):
    """Un botón para una orden que sólo estaba en el menú."""
    from PySide6 import QtCore, QtGui
    from PySide6.QtGui import QAction, QIcon

    from core.i18n import tr
    from views.icons import command_icon

    from . import yaguarete

    orden = item.command
    etiqueta, _o = yaguarete.separar_orden(tr(item.label))
    etiqueta = (etiqueta or orden).rstrip(".").strip()
    icono = QIcon(str(item.icon)) if item.icon else command_icon(orden)
    if icono.isNull():
        icono = botones.icono_letras(QtGui, QtCore, orden)
    act = QAction(icono, etiqueta, window)
    act.setToolTip(f"{etiqueta} ({orden})")
    act.setProperty("geocad_orden", orden)
    act.triggered.connect(lambda _=False, n=orden: window._invoke_command(n))
    return act


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


def aplicar(window, mostrar=False) -> None:
    """Pone las categorías guardadas (o deja la fábrica). Se llama cada vez
    que IngeCAD rearma la barra GeoCAD (al arrancar, al cambiar los módulos).
    Las barras que el usuario escondió siguen escondidas, salvo ``mostrar``."""
    fab = fabricas(window)
    if not fab:
        return
    botones_barras.aplicar(window, fab, id_de, lambda fabrica: botones.barras(PROGRAMA, fabrica),
                           _nueva_barra(window), _divisor, mostrar, bancos=bancos(window))


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
    # los botones de la foto de fábrica, sin tocar las barras: mirar no prende
    # nada (Fernando, 25/10/2026); con Cancelar todo queda como estaba
    elems = botones_barras.elementos(fabricas(window), id_de, window, bancos=bancos(window))
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
                              tema_de, NOMBRES_TEMA, botones_barras.escondidas(window)):
        aplicar(window, mostrar=True)
        ctx.echo("Botones de GeoCAD: categorías guardadas.")
