# SPDX-License-Identifier: GPL-3.0-or-later
"""El formato del texto en la paleta Properties (3.11.0, módulo «Propiedades»).

El editor de texto en el lugar de IngeCAD (views/mtext_editor.py) lleva
arriba del texto la barra de formato (Estilo, Fuente, Altura, N K S O,
Color, a/b, interlineado, Lista, Máscara, Columnas, Justificar, OK) y la
caja toma el ancho mayor entre el texto y esa barra: con un texto corto,
la caja es mucho más ancha que el texto. Pedido de Fernando (08/10/2026):
el formato en la paleta Properties y sobre el texto sólo la regla.

Mientras se edita, los MISMOS controles de IngeCAD (no copias: siguen
haciendo lo mismo) pasan a un recuadro «Formato del texto» arriba de la
paleta Properties, en columna. Sobre el texto quedan la regla y el texto, y
la caja mide lo que mide el texto. Al cerrar el editor el recuadro se va y
la paleta vuelve a la solapa que estaba.

El editor guarda y se cierra con un clic fuera de él; un clic en el
recuadro cuenta como adentro. Apagado el módulo, el editor queda como viene.
"""
from __future__ import annotations

from . import propiedades

NOMBRE = "GeoCADFormatoTexto"

#: El recuadro, renglón por renglón: (rótulo o None, controles del editor).
FILAS = (
    ("Estilo", ("style_combo",)),
    ("Fuente", ("font_combo",)),
    ("Altura", ("height_spin",)),
    (None, ("bold", "italic", "under", "over")),
    ("Color", ("color_combo",)),
    (None, ("stack", "spacing", "lists")),
    (None, ("mask", "columns", "justify")),
    (None, ("ok",)),
)


def controles() -> list:
    """Todos los controles que se mudan, en orden."""
    return [n for _, nombres in FILAS for n in nombres]


def _ventana(editor):
    try:
        return editor._viewport.window()
    except Exception:  # noqa: BLE001
        return None


def mudar(editor) -> bool:
    """Pasa los controles de la barra del editor a la paleta Properties.
    Devuelve False (y no toca nada) si no se puede."""
    from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                                   QSizePolicy, QWidget)

    window = _ventana(editor)
    panel = getattr(window, "_properties_panel", None)
    tabs = getattr(window, "_sidebar_tabs", None)
    if panel is None or tabs is None or panel.layout() is None:
        return False
    if not all(getattr(editor, n, None) is not None for n in controles()):
        return False                        # otra versión de IngeCAD: como viene

    caja = QFrame(panel)
    caja.setObjectName(NOMBRE)
    caja.setFrameShape(QFrame.StyledPanel)
    grilla = QGridLayout(caja)
    grilla.setContentsMargins(6, 6, 6, 6)
    grilla.setHorizontalSpacing(6)
    grilla.setVerticalSpacing(4)
    titulo = QLabel("<b>Formato del texto</b>", caja)
    grilla.addWidget(titulo, 0, 0, 1, 2)
    for fila, (rotulo, nombres) in enumerate(FILAS, start=1):
        widgets = [getattr(editor, n) for n in nombres]
        if rotulo is not None:
            grilla.addWidget(QLabel(rotulo, caja), fila, 0)
            for w in widgets:
                w.setMaximumWidth(16777215)          # la fuente venía topeada
                grilla.addWidget(w, fila, 1)
        else:
            renglon = QWidget(caja)
            fila_h = QHBoxLayout(renglon)
            fila_h.setContentsMargins(0, 0, 0, 0)
            fila_h.setSpacing(2)
            for w in widgets:
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                fila_h.addWidget(w, 1)
            grilla.addWidget(renglon, fila, 0, 1, 2)
    grilla.setColumnStretch(1, 1)

    editor._bar.hide()                      # vacía: ya no ensancha la caja
    editor._geocad_formato = caja
    editor._geocad_solapa = tabs.currentWidget()
    panel.layout().insertWidget(0, caja)
    mostrar = getattr(window, "_show_sidebar", None)
    if callable(mostrar):
        mostrar()
    tabs.setCurrentWidget(panel)
    editor._sync_geometry()
    editor.edit.setFocus()
    return True


def devolver(editor) -> None:
    """Al cerrar el editor: el recuadro se va y la paleta vuelve a su solapa."""
    caja = getattr(editor, "_geocad_formato", None)
    if caja is None:
        return
    editor._geocad_formato = None
    caja.hide()
    caja.setParent(None)
    caja.deleteLater()
    window = _ventana(editor)
    tabs = getattr(window, "_sidebar_tabs", None)
    anterior = getattr(editor, "_geocad_solapa", None)
    if tabs is not None and anterior is not None and tabs.indexOf(anterior) >= 0:
        tabs.setCurrentWidget(anterior)


def en_recuadro(editor, obj) -> bool:
    caja = getattr(editor, "_geocad_formato", None)
    return caja is not None and (obj is caja or caja.isAncestorOf(obj))


def depende_del_editor(editor, obj) -> bool:
    """obj está en el editor, en el recuadro o en una ventana que depende de
    ellos («Discard...?», Máscara, Columnas, interlineado). isAncestorOf de
    Qt no cruza de una ventana a otra; parentWidget sí."""
    caja = getattr(editor, "_geocad_formato", None)
    w = obj
    while w is not None:
        if w is editor or (caja is not None and w is caja):
            return True
        try:
            w = w.parentWidget()
        except Exception:  # noqa: BLE001
            return False
    return False


def clic_no_cierra(editor, obj) -> bool:
    """Error de IngeCAD (también sin GeoCAD, 3.11.1): el editor toma un clic
    en sus propias ventanas como «clic afuera» y guarda y cierra. En
    «Discard the changes...?» el «Yes» cerraba el editor dos veces (guardar
    y cancelar) y el programa se caía; el «No» guardaba y cerraba. Con una
    ventana modal abierta, ningún clic es un clic en el dibujo."""
    if depende_del_editor(editor, obj):
        return True
    from PySide6.QtWidgets import QApplication
    return QApplication.activeModalWidget() is not None


# ---------------------------------------------------------------- envoltorios
def _envolver_init(original):
    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self._geocad_formato = None
        if self._single_line or not propiedades.activo(_ventana(self)):
            return
        try:
            mudar(self)
        except Exception:  # noqa: BLE001 - el editor sigue como viene
            pass
    __init__._puente_original = original
    __init__._puente_fabrica = _envolver_init
    return __init__


def _envolver_event_filter(original):
    def eventFilter(self, obj, event):
        try:
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.MouseButtonPress and clic_no_cierra(self, obj):
                return False                # recuadro o ventanas del editor: «adentro»
        except Exception:  # noqa: BLE001
            pass
        return original(self, obj, event)
    eventFilter._puente_original = original
    eventFilter._puente_fabrica = _envolver_event_filter
    return eventFilter


def _envolver_teardown(original):
    def _teardown(self, *args, **kwargs):
        try:
            devolver(self)
        except Exception:  # noqa: BLE001
            pass
        return original(self, *args, **kwargs)
    _teardown._puente_original = original
    _teardown._puente_fabrica = _envolver_teardown
    return _teardown


ENVOLTORIOS = {
    "__init__": _envolver_init,
    "eventFilter": _envolver_event_filter,
    "_teardown": _envolver_teardown,
}


def instalar() -> None:
    """Se llama al cargar el plugin. Sin interfaz (pruebas) no hace nada."""
    try:
        from views.mtext_editor import MTextInPlaceEditor   # usa Qt
    except Exception:  # noqa: BLE001
        return
    from .dibujo import envolver
    for nombre, fabrica in ENVOLTORIOS.items():
        if getattr(getattr(MTextInPlaceEditor, nombre, None), "_puente_fabrica", None) \
                is not fabrica:
            envolver(MTextInPlaceEditor, nombre, fabrica, reemplazar=True)
