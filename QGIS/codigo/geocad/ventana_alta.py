# SPDX-License-Identifier: GPL-3.0-or-later
"""Aviso de ventana más alta que la pantalla (3.60.4).

Fernando, 01/11/2026: «minimizar y maximizar no responden correctamente».
Medido en su perfil: la ventana de QGIS necesitaba 1035 px de alto como
MÍNIMO y la pantalla útil (maximizada) tenía 994. Las alturas mínimas de los
paneles apilados en una columna se suman a las filas de barras; si pasan la
pantalla, GNOME no puede maximizar ni achicar la ventana. GeoCAD no mueve
los paneles del usuario: avisa una vez por sesión qué columna conviene
aliviar (poner paneles en pestaña o cerrar alguno).

``texto_aviso`` es Python puro (se prueba sin Qt); ``revisar`` mide la
ventana real.
"""

#: lo que la barra superior de GNOME y la barra de título le quitan a la
#: pantalla: 1080 de pantalla, 994 de ventana maximizada (medido, 01/11/2026)
MARGEN = 86

AREAS = {1: "izquierda", 2: "derecha"}


def texto_aviso(min_alto, alto_pantalla, columnas):
    """El aviso, o None si la ventana entra. ``columnas``: {área: [(título,
    alto mínimo), ...]} de los paneles apilados (uno por grupo de pestañas)."""
    util = alto_pantalla - MARGEN
    if min_alto <= util:
        return None
    nombre, paneles = max(columnas.items(), key=lambda kv: sum(a for _t, a in kv[1]),
                          default=(None, []))
    texto = ("La ventana de QGIS necesita al menos %d px de alto y la pantalla deja %d: "
             "no se puede maximizar ni achicar bien." % (min_alto, util))
    if len(paneles) > 1:
        texto += (" Poné en pestaña (arrastrando uno sobre otro) o cerrá alguno de los paneles "
                  "de la columna %s: %s." % (AREAS.get(nombre, nombre),
                                             ", ".join(t for t, _a in paneles)))
    else:
        texto += " Cerrá o poné en pestaña algún panel, o quitá alguna fila de barras."
    return texto


def columnas_de(win):
    """{área: [(título, alto mínimo)]} de los paneles acoplados visibles a la
    izquierda y a la derecha; de cada grupo de pestañas cuenta uno solo."""
    from qgis.PyQt.QtWidgets import QDockWidget
    salida, vistos = {}, set()
    for d in win.findChildren(QDockWidget):
        try:
            if d.isFloating() or not d.isVisible() or id(d) in vistos:
                continue
            area = int(getattr(win.dockWidgetArea(d), "value", win.dockWidgetArea(d)))
        except (RuntimeError, TypeError):
            continue
        if area not in AREAS:
            continue
        grupo = [d] + list(win.tabifiedDockWidgets(d))
        vistos.update(id(x) for x in grupo)
        alto = max(x.minimumSizeHint().height() for x in grupo)
        salida.setdefault(area, []).append((d.windowTitle() or d.objectName(), alto))
    return salida


def revisar(iface, avisar):
    """Mide la ventana principal y, si no entra en la pantalla, llama a ``avisar(texto)``."""
    try:
        win = iface.mainWindow()
        pantalla = win.screen().availableGeometry().height()
        texto = texto_aviso(win.minimumSizeHint().height(), pantalla, columnas_de(win))
    except Exception:  # noqa: BLE001 - un aviso nunca rompe el arranque
        return None
    if texto:
        avisar(texto)
    return texto
