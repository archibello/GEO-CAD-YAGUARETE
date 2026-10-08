# SPDX-License-Identifier: GPL-3.0-or-later
"""La barra GeoCAD de IngeCAD, ordenada y separada por temas (3.10.1).

IngeCAD acepta separadores en el menú de un plugin pero no en su barra:
ahí cada entrada es un botón. Por eso la lista de la barra sigue siendo
sólo de botones y, cuando IngeCAD termina de armarla (al arrancar, al
cambiar los módulos o al prenderla en Herramientas > Complementos), se
le agrega un divisor entre un tema y el siguiente. Las barras de otros
plugins quedan como vienen.
"""
from __future__ import annotations

#: Los temas en el orden de la barra (pedido de Fernando, 08/10/2026).
ORDEN = ("seleccion", "datos", "edicion", "bloques", "cotas", "impresion", "puente")

#: El tema de cada botón; dentro de un tema, el orden es el de la lista.
TEMAS = {
    "FILLET": "edicion", "CHAMFER": "edicion", "BREAKATPOINT": "edicion",
    "BLOCK": "bloques", "INSERT": "bloques", "GEOREFEDIT": "bloques", "GEOBLOCKBASE": "bloques",
    "SELECT": "seleccion", "GEOFILTER": "seleccion",
    "GEOPREVIEW": "impresion", "GEOPLOTSTYLES": "impresion",
    "GEODIMSETUP": "cotas", "DIMLINEAR": "cotas", "DIMALIGNED": "cotas", "DIMANGULAR": "cotas",
    "SHPTABLE": "datos", "SHPQUERY": "datos", "SHPSPATIAL": "datos", "SHPTHEME": "datos",
    "SHPLABEL": "datos", "SHPNEW": "datos",
    "QGISSAVESEL": "puente", "QGISSAVE": "puente",
}


def ordenar(items) -> list:
    """Los botones de la barra agrupados por tema, en el orden de ``ORDEN``
    (un botón sin tema va al final)."""
    def clave(item):
        tema = TEMAS.get(item.command)
        return ORDEN.index(tema) if tema in ORDEN else len(ORDEN)
    return sorted(items, key=clave)


def cortes(comandos) -> list:
    """Las posiciones de los botones que empiezan un tema nuevo (antes de
    cada una va un divisor). Nunca antes del primero."""
    comandos = list(comandos)
    return [i for i in range(1, len(comandos))
            if TEMAS.get(comandos[i]) != TEMAS.get(comandos[i - 1])]


def _divisor(bar):
    """Un divisor con el mismo dibujo que el agarre de la barra (los puntitos
    de la izquierda): lo pinta el estilo de IngeCAD, así sigue al tema claro
    u oscuro. La línea común de Qt casi no se ve en el tema oscuro."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QStyle, QStyleOption, QWidget

    class Divisor(QWidget):
        def __init__(self, barra):
            super().__init__(barra)
            self._barra = barra
            ancho = self.style().pixelMetric(QStyle.PM_ToolBarHandleExtent, None, barra)
            self.setFixedWidth(max(ancho, 8) + 6)        # aire a los dos lados

        def paintEvent(self, _evento):
            opcion = QStyleOption()
            opcion.initFrom(self)
            opcion.rect = self.rect().adjusted(3, 3, -3, -3)
            if self._barra.orientation() == Qt.Horizontal:
                opcion.state |= QStyle.State_Horizontal
            pintor = QPainter(self)
            self.style().drawPrimitive(QStyle.PE_IndicatorToolBarHandle, opcion, pintor, self)

    return Divisor(bar)


def separar(bar, spec) -> None:
    """Pone un divisor entre tema y tema en una barra ya armada con los
    botones de ``spec``."""
    acciones = list(bar.actions())
    if len(acciones) != len(spec.toolbar):
        return                              # no es la barra que esperamos
    for i in cortes(t.command for t in spec.toolbar):
        bar.insertWidget(acciones[i], _divisor(bar))


def _envolver_add_toolbar(original):
    def add_toolbar(self, spec, *args, **kwargs):
        original(self, spec, *args, **kwargs)
        if getattr(spec, "id", None) != "geocad":
            return
        try:
            bar = getattr(self, "_plugin_toolbars", {}).get(spec.id)
            if bar is not None:
                separar(bar, spec)
        except Exception:  # noqa: BLE001 - la barra queda como la armó IngeCAD
            pass
    add_toolbar._puente_original = original
    add_toolbar._puente_fabrica = _envolver_add_toolbar
    return add_toolbar


def instalar() -> None:
    try:
        from views.main_window import MainWindow   # usa Qt
    except Exception:  # noqa: BLE001
        return
    from .dibujo import envolver
    if getattr(MainWindow.add_toolbar, "_puente_fabrica", None) is not _envolver_add_toolbar:
        envolver(MainWindow, "add_toolbar", _envolver_add_toolbar, reemplazar=True)
