# -*- coding: utf-8 -*-
"""Medidas de IngeCAD para el panel y la barra Yaguá Capas (3.61.2).

Una sola definición para los dos (Fernando, 02/11/2026: «así como regulamos las
dimensiones del Panel Yaguá Capas, tendríamos que optimizar las dimensiones de
la barra ... Si podemos utilizar los mismos para ambas sería mejor»).

QGIS pone su letra (11 pt) con una hoja de estilo para toda la aplicación: un
setFont() solo no alcanza, por eso la letra va también en hoja de estilo, como
en IngeCAD 0.7.0 (views/main_window.py, _build_props_toolbar: «font-size: 11px;
combobox-popup: 0»).
"""
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionComboBox

from .compat import enum

LETRA_PX = 11        # letra del panel y de la barra (QGIS: 11 pt = ~15 px)
FILA = 20            # alto de las filas del panel y de las listas de la barra
ENCABEZADO = 24      # encabezado del panel
ICONO_COL = 28       # columnas de íconos del panel

# Panel Yaguá Capas: medidas compactas de IngeCAD con los colores del tema de QGIS
# (Fernando, 01/11/2026: «del color de QGIS y no del color de IngeCAD»)
PANEL_STYLE = """
#CadLayersPanel QTableWidget { font-size: %(px)dpx; }
#CadLayersPanel QHeaderView::section { padding: 1px 3px; font-size: %(px)dpx; border: none;
    border-right: 1px solid palette(midlight); }
#CadLayersPanel QToolButton { border: none; padding: 2px 5px; font-size: %(px)dpx; }
#CadLayersPanel QTreeWidget { font-size: %(px)dpx; }
#CadLayersPanel QLineEdit { font-size: %(px)dpx; padding: 1px 4px; }
""" % {'px': LETRA_PX}

# Listas de la barra: la misma letra; «combobox-popup: 0» = la lista común de Qt (no la
# del estilo Breeze, del ancho de la casilla y con filas de menú de 33 px)
LISTA_STYLE = ("QComboBox { font-size: %dpx; combobox-popup: 0; } "
               "QComboBox QAbstractItemView { font-size: %dpx; }" % (LETRA_PX, LETRA_PX))


def letra_chica(font):
    """La letra del panel y de la barra a partir de la del programa."""
    chica = QFont(font)
    chica.setPixelSize(LETRA_PX)
    return chica


class FilaDelegate(QStyledItemDelegate):
    """Filas de la lista con el alto del panel."""

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), FILA)


def preparar_lista(combo, delegate=True):
    """Letra y filas compartidas en una lista de la barra y en su desplegable."""
    combo.setStyleSheet(LISTA_STYLE)
    chica = letra_chica(combo.font())
    combo.setFont(chica)
    combo.view().setFont(chica)
    if delegate:
        combo.setItemDelegate(FilaDelegate(combo))
    combo.ensurePolished()


def ancho_casilla(combo, textos, icono=True, minimo=0):
    """Ancho para que la casilla muestre entero el más largo de «textos»."""
    combo.ensurePolished()
    fm = combo.fontMetrics()
    texto = max([fm.horizontalAdvance(t) for t in textos] or [0])
    if icono:
        texto += combo.iconSize().width() + 4
    opt = QStyleOptionComboBox()
    combo.initStyleOption(opt)
    size = combo.style().sizeFromContents(enum(QStyle, 'ContentsType', 'CT_ComboBox'), opt,
                                          QSize(texto, fm.height()), combo)
    return max(minimo, size.width() + 2)


def ancho_desplegable(combo):
    """Ancho para que en el desplegable se lea entero cada renglón (sin «…»)."""
    v = combo.view()
    v.ensurePolished()
    fm = v.fontMetrics()
    icono = combo.iconSize().width()
    renglon = 0
    for i in range(combo.count()):      # ícono + texto + los márgenes de cada renglón
        con_icono = not combo.itemIcon(i).isNull()
        renglon = max(renglon, fm.horizontalAdvance(combo.itemText(i)) + (icono + 6 if con_icono else 0) + 12)
    ancho = max(v.sizeHintForColumn(0), renglon) + 2 * v.frameWidth() + 4
    if combo.count() > combo.maxVisibleItems():
        ancho += v.style().pixelMetric(enum(QStyle, 'PixelMetric', 'PM_ScrollBarExtent'), None, v)
    return ancho


def ajustar_desplegable(combo):
    """El desplegable nunca más angosto que su renglón más largo."""
    combo.view().setMinimumWidth(ancho_desplegable(combo))

