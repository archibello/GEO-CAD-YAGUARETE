# SPDX-License-Identifier: GPL-3.0-or-later
"""Retoques del panel Layers de IngeCAD (3.25.6).

El panel muestra el bloqueo con dos emojis (🔓 / 🔒) que en tamaño chico se
ven casi iguales (Fernando, 16/10/2026). Se dibujan en su lugar un candado
ABIERTO en gris (capa libre) y uno CERRADO en rojo (capa bloqueada). El
texto de la celda no se toca: IngeCAD lo lee para saber el estado al hacer
clic. Retoque fijo, sin módulo («algo muy puntual y de uso tradicional»).

Lo que no necesita Qt (qué se dibuja según el texto) se prueba sin Qt."""
from __future__ import annotations

COLUMNA_BLOQUEO = 4            # Status, Name, On, Freeze, Lock, ...
ABIERTO, CERRADO = "🔓", "🔒"
GRIS = (170, 170, 170)         # libre: no llama la atención
ROJO = (220, 50, 47)           # bloqueada: se ve de un vistazo


def estado(texto: str):
    """«abierto», «cerrado» o None (otra cosa: se deja como la pinta IngeCAD)."""
    texto = (texto or "").strip()
    if texto == ABIERTO:
        return "abierto"
    if texto == CERRADO:
        return "cerrado"
    return None


def pintar_candado(painter, rect, abierto: bool) -> None:
    """Un candado de ~14 px centrado en ``rect``: cuerpo lleno y arco; el
    abierto con el arco levantado y corrido a la derecha."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QPen

    color = QColor(*(GRIS if abierto else ROJO))
    lado = min(rect.width(), rect.height(), 18) - 2
    x0 = rect.x() + (rect.width() - lado) / 2
    y0 = rect.y() + (rect.height() - lado) / 2
    ancho_cuerpo, alto_cuerpo = lado * 0.70, lado * 0.50
    cx = x0 + (lado - ancho_cuerpo) / 2
    cy = y0 + lado - alto_cuerpo
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    pen = QPen(color, max(1.6, lado / 8))
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    ancho_arco = ancho_cuerpo * 0.62
    ax = cx + (ancho_cuerpo - ancho_arco) / 2
    if abierto:
        ax += ancho_cuerpo * 0.42          # corrido a la derecha
        sube = lado * 0.20                 # y levantado
    else:
        sube = 0.0
    alto_arco = lado * 0.62
    arco = QRectF(ax, y0 - sube, ancho_arco, alto_arco)
    painter.drawArc(arco, 0, 180 * 16)
    # las patas del arco hasta el cuerpo (el abierto: sólo la izquierda llega)
    medio = arco.center().y()
    fondo = cy if not abierto else cy - lado * 0.08
    painter.drawLine(arco.left(), medio, arco.left(), fondo + (0 if abierto else 1))
    if not abierto:
        painter.drawLine(arco.right(), medio, arco.right(), cy + 1)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(cx, cy, ancho_cuerpo, alto_cuerpo), 1.5, 1.5)
    painter.restore()


def _delegado():
    from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

    class Candados(QStyledItemDelegate):
        geocad_candados = True

        def paint(self, painter, option, index):
            cual = estado(index.data())
            if cual is None:
                return super().paint(painter, option, index)
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""                  # el emoji queda en la celda, pero no se ve
            estilo = opt.widget.style() if opt.widget else QApplication.style()
            estilo.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
            pintar_candado(painter, option.rect, cual == "abierto")

    return Candados


def aplicar(panel) -> bool:
    """Pone los candados en un panel Layers ya armado (una sola vez)."""
    tabla = getattr(panel, "table", None)
    if tabla is None:
        return False
    actual = tabla.itemDelegateForColumn(COLUMNA_BLOQUEO)
    if actual is not None and getattr(actual, "geocad_candados", False):
        return False
    tabla.setItemDelegateForColumn(COLUMNA_BLOQUEO, _delegado()(tabla))
    tabla.viewport().update()
    return True


def _envolver_init(original):
    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        try:
            aplicar(self)
        except Exception:  # noqa: BLE001 -- el panel queda como lo arma IngeCAD
            pass
    __init__._puente_original = original
    __init__._puente_fabrica = _envolver_init
    return __init__


def instalar() -> None:
    """Se llama al cargar el plugin: los paneles que se armen después y los
    que ya están abiertos."""
    try:
        from views.layers_panel import LayersPanel
        from PySide6.QtWidgets import QApplication
    except Exception:  # noqa: BLE001 -- otro IngeCAD o sin Qt
        return
    from .dibujo import envolver
    if getattr(LayersPanel.__init__, "_puente_fabrica", None) is not _envolver_init:
        envolver(LayersPanel, "__init__", _envolver_init, reemplazar=True)
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        if isinstance(w, LayersPanel):
            try:
                aplicar(w)
            except Exception:  # noqa: BLE001
                pass
