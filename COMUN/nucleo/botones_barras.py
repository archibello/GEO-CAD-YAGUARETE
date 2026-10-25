# SPDX-License-Identifier: GPL-3.0-or-later
"""Las categorías de Administrar botones puestas en las barras (3.38.0).

Sirve a los dos programas sin importar Qt (IngeCAD usa PySide6, QGIS
qgis.PyQt): las barras nuevas las crea el programa (``nueva_barra``).

Las barras de fábrica no se rehacen: se les sacan sus botones (y sus
divisores), que pasan a la barra de su categoría; lo que no es un botón
(una lista de fuentes, la capa actual) se queda donde estaba. Una categoría
con el nombre de una barra de fábrica usa esa misma barra. La barra de
fábrica que queda vacía se esconde. ``restaurar`` deja todo como estaba,
en el mismo orden: apagado, no queda rastro.
"""
from __future__ import annotations

DIVISOR = "geocad_divisor"           # objectName de los divisores de GeoCAD

#: lo que se movió en cada ventana, por la dirección de la ventana en C++. No
#: va como atributo de la ventana: en QGIS la ventana principal es de C++ y su
#: envoltorio de Python se rehace entre llamadas, y el atributo se perdía
#: (Fernando, 24/10/2026: «No hay barras de GeoCAD» con la 3.41.0)
_ESTADOS: dict = {}


def _clave(window):
    try:
        from shiboken6 import getCppPointer          # IngeCAD (PySide6)
        return getCppPointer(window)[0]
    except Exception:  # noqa: BLE001
        pass
    try:
        from qgis.PyQt import sip                     # QGIS (PyQt)
        return sip.unwrapinstance(window)
    except Exception:  # noqa: BLE001
        return id(window)                             # sin Qt (pruebas)


def _es_divisor(bar, accion) -> bool:
    try:
        if accion.isSeparator():
            return True
        w = bar.widgetForAction(accion)
        return w is not None and w.objectName() == DIVISOR
    except RuntimeError:
        return False


def _escondida_a_proposito(bar) -> bool:
    """¿La escondió el usuario? Una barra recién puesta también dice
    isHidden() hasta que Qt la muestra: eso no cuenta."""
    try:
        import importlib
        Qt = importlib.import_module(type(bar).__module__.rsplit(".", 1)[0] + ".QtCore").Qt
        explicita = getattr(getattr(Qt, "WidgetAttribute", Qt), "WA_WState_ExplicitShowHide")
        return bar.isHidden() and bar.testAttribute(explicita)
    except Exception:  # noqa: BLE001 - sin Qt (pruebas): lo que diga la barra
        return bar.isHidden()


def elementos(fabricas, id_de) -> list:
    """[(título de la barra, [(botón, acción), ...])] de las barras de fábrica
    (la primera vez que aparece cada botón)."""
    salida, vistos = [], set()
    for nombre, bar in fabricas:
        fila = []
        for a in bar.actions():
            b = id_de(a)
            if b and b not in vistos:
                vistos.add(b)
                fila.append((b, a))
        salida.append((nombre, fila))
    return salida


def temas(fabricas, id_de) -> dict:
    """{botón: (barra, tramo)}: los tramos entre divisores de la fábrica.
    Entre dos botones de tramos distintos va un divisor también en las
    barras de las categorías."""
    salida = {}
    for i, (_nombre, bar) in enumerate(fabricas):
        tramo = 0
        for a in bar.actions():
            if _es_divisor(bar, a):
                tramo += 1
                continue
            b = id_de(a)
            if b:
                salida.setdefault(b, (i, tramo))
    return salida


def restaurar(window) -> None:
    """Todo como de fábrica: las barras nuevas fuera, los botones y divisores
    de vuelta a su barra y en su orden, las barras escondidas a la vista."""
    est = _ESTADOS.pop(_clave(window), None)
    if not est:
        return
    for bar, accion in est["agregados"]:
        try:
            bar.removeAction(accion)
        except RuntimeError:
            pass
    # las barras de las categorías se vacían ANTES de devolver nada: una lista
    # (fuente, capa actual) sólo puede estar en una barra; si la vieja todavía
    # la tiene, la de fábrica recibe un botón vacío en su lugar (3.46.0)
    for bar in est["nuevas"]:
        try:
            for accion in list(bar.actions()):
                bar.removeAction(accion)
        except RuntimeError:
            pass
    movidas = [a for _bar, _foto, quitadas in est["fotos"] for a in quitadas]
    for bar, _foto, _q in est["fotos"]:
        try:                          # un botón pudo ir a otra barra de fábrica
            for a in movidas:
                bar.removeAction(a)
        except RuntimeError:
            pass
    for bar, foto, quitadas in est["fotos"]:
        try:
            siguiente = None
            for a in reversed(foto):
                if a in quitadas:
                    if siguiente is None:
                        bar.addAction(a)
                    else:
                        bar.insertAction(siguiente, a)
                siguiente = a
        except RuntimeError:          # la barra ya no existe
            pass
    for bar in est["nuevas"]:
        try:
            window.removeToolBar(bar)
            bar.setParent(None)
            bar.deleteLater()
        except RuntimeError:
            pass
    for bar in est["escondidas"]:
        try:
            bar.setVisible(True)
            bar.toggleViewAction().setVisible(True)
        except RuntimeError:
            pass


def aplicar(window, fabricas, id_de, distribucion, nueva_barra, divisor=None) -> list:
    """Arma las barras de ``distribucion`` ([(categoría, [botones])], o None =
    de fábrica; o una función que la calcula con la fábrica [(barra, [botones])]
    DESPUÉS de restaurar: con las categorías puestas, las barras de fábrica
    están vacías y una cuenta hecha antes las perdía, 3.39.1). ``fabricas``:
    [(título, barra)]; ``id_de(acción)``: el botón
    o None; ``nueva_barra(nombre)``: una barra nueva ya puesta en la ventana;
    ``divisor(barra)``: agrega un divisor (por defecto, un separador).
    Devuelve las barras de las categorías."""
    restaurar(window)
    if callable(distribucion):
        distribucion = distribucion([(n, [b for b, _a in fila])
                                     for n, fila in elementos(fabricas, id_de)])
    if not distribucion:
        return []
    divisor = divisor or (lambda bar: bar.addSeparator())
    acciones = {b: a for _n, fila in elementos(fabricas, id_de) for b, a in fila}
    tema = temas(fabricas, id_de)
    est = {"fotos": [], "agregados": [], "nuevas": [], "escondidas": []}
    _ESTADOS[_clave(window)] = est
    por_titulo = {}
    for nombre, bar in fabricas:
        foto = list(bar.actions())
        quitadas = [a for a in foto if id_de(a) or _es_divisor(bar, a)]
        for a in quitadas:
            bar.removeAction(a)
        est["fotos"].append((bar, foto, quitadas))
        por_titulo.setdefault(nombre, bar)
    salida = []
    for nombre, botones in distribucion:
        botones = [b for b in botones if b in acciones]
        if not botones:
            continue
        bar = por_titulo.get(nombre)
        if bar is None:
            bar = nueva_barra(nombre)
            est["nuevas"].append(bar)
        # en su barra de fábrica, los botones van primero (antes de las listas)
        quedan = list(bar.actions())
        primera = quedan[0] if quedan else None

        def poner(accion, bar=bar, primera=primera):
            if primera is not None:
                bar.removeAction(accion)
                bar.insertAction(primera, accion)

        for i, b in enumerate(botones):
            if i and tema.get(b) != tema.get(botones[i - 1]):
                sep = divisor(bar)
                poner(sep)
                est["agregados"].append((bar, sep))
            bar.addAction(acciones[b])
            poner(acciones[b])
        if primera is not None:
            sep = divisor(bar)
            poner(sep)
            est["agregados"].append((bar, sep))
        salida.append(bar)
    usadas = {id(b) for b in salida}
    for _nombre, bar in fabricas:
        if id(bar) not in usadas and not bar.actions() and not _escondida_a_proposito(bar):
            bar.setVisible(False)
            bar.toggleViewAction().setVisible(False)
            est["escondidas"].append(bar)
    return salida
