"""Color propio del menú GeoCAD Yaguareté en IngeCAD (prueba, Fernando 12/11/2026).

Bordó profundo (opción B) porque combina con el fondo negro de IngeCAD. La hoja de estilo va
SÓLO en nuestro menú (los submenús la heredan); los demás menús de IngeCAD
quedan como vienen. IngeCAD rearma los menús al prender o apagar un plugin,
así que se vuelve a aplicar desde el envoltorio de _build_menus.
"""
from __future__ import annotations

ESTILO = """
QMenu { background-color: #430E18; color: #F0E2E4; border: 1px solid #66202C; }
QMenu::item { background-color: transparent; padding: 4px 28px 4px 30px; }
QMenu::item:selected { background-color: #7D1C2C; color: #FFFFFF; }
QMenu::item:disabled { color: #977A80; }
QMenu::separator { height: 1px; background-color: #66202C; margin: 4px 8px; }
"""


def _es_nuestro(titulo: str) -> bool:
    return "GeoCAD" in titulo.replace("&", "")


FONDO, RESALTADO, LETRA = "#430E18", "#7D1C2C", "#F0E2E4"
# 3.78.3 (Fernando: «el tono más claro… ese contraste los hace más visibles»): el título
# de la barra va en el tono claro y, con el menú abierto o el mouse encima, en el del menú
BARRA, BARRA_ACTIVA = RESALTADO, FONDO


def barra_de(window):
    """IngeCAD tiene su propia barra de menús (_menu_bar), no la de QMainWindow."""
    barra = getattr(window, "_menu_bar", None)
    if barra is None and hasattr(window, "menuBar"):
        barra = window.menuBar()
    return barra


def menu_geocad(window):
    """El QMenu «GeoCAD Yaguareté» de la barra de IngeCAD, o None."""
    barra = barra_de(window)
    if barra is None:
        return None
    for accion in barra.actions():
        menu = accion.menu()
        if menu is not None and _es_nuestro(menu.title()):
            return menu
    return None


def aplicar(window) -> bool:
    """Pinta el menú GeoCAD; nunca tira abajo a IngeCAD."""
    try:
        menu = menu_geocad(window)
        if menu is None:
            return False
        if menu.styleSheet() != ESTILO:
            menu.setStyleSheet(ESTILO)
        try:
            from . import color_barra  # 3.78.1: el título de la barra, del mismo color
            color_barra.instalar(barra_de(window), _es_nuestro, BARRA, BARRA_ACTIVA, LETRA)
        except Exception:  # noqa: BLE001 - el menú queda pintado igual
            pass
        return True
    except Exception:  # noqa: BLE001
        return False
