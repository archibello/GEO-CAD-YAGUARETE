# SPDX-License-Identifier: GPL-3.0-or-later
"""El teclado va siempre a la línea de comandos (módulo «Teclado», 3.59).

Pedido de Fernando (30/10/2026): en AutoCAD lo que se escribe va a la línea de
comandos esté donde esté el foco; en IngeCAD y en QGIS había que hacer clic en
ella después de tocar el panel de capas, una barra, un diálogo o al empezar a
editar una capa. Acordado:

- letras, números y signos van a la línea de comandos;
- Intro, Retroceso y Espacio sólo si ya tiene algo escrito;
- Esc si tiene algo escrito o hay un comando en marcha (lo cancela);
- nunca con Ctrl/Alt/Meta, ni las flechas, Supr o las teclas F;
- nunca en campos de texto, números, listas editables, consolas, la tabla
  de atributos (o una tabla donde una letra edita la celda), diálogos o
  ventanas aparte. El panel de capas (en IngeCAD, una tabla) sí.

Las decisiones son Python puro; el filtro de eventos recibe los módulos de Qt
del programa (PyQt de QGIS o PySide6 de IngeCAD), como modulos_ui.
"""
from __future__ import annotations

#: teclas especiales, por nombre de Qt.Key
_CON_TEXTO = ("Key_Return", "Key_Enter", "Key_Backspace", "Key_Space")
_ESC = "Key_Escape"

#: clases (por nombre, también las de QGIS y QScintilla) donde se escribe
_PROTEGIDAS = ("QLineEdit", "QTextEdit", "QPlainTextEdit", "QAbstractSpinBox",
               "QsciScintillaBase", "QgsDualView", "QgsAttributeTableView",
               "QgsCodeEditor")

#: QAbstractItemView.AnyKeyPressed: en esa tabla una letra empieza a editar
_EDITA_AL_TECLEAR = 16


def decidir(nombre_tecla: str, texto: str, modificadores: bool,
            linea_con_texto: bool, comando_en_marcha: bool) -> bool:
    """¿Esta tecla va a la línea de comandos?

    nombre_tecla: «Key_A», «Key_Return»... ; texto: lo que escribe la tecla;
    modificadores: Ctrl, Alt o Meta apretados (Mayús no cuenta)."""
    if modificadores:
        return False
    if nombre_tecla in _CON_TEXTO:
        return linea_con_texto
    if nombre_tecla == _ESC:
        return linea_con_texto or comando_en_marcha
    return bool(texto) and texto.isprintable() and not texto.isspace()


def _clases(widget) -> list:
    """Nombres de la clase del widget y de sus clases madre (metaObject)."""
    out = []
    try:
        meta = widget.metaObject()
    except (AttributeError, RuntimeError):
        return out
    while meta is not None:
        out.append(meta.className())
        meta = meta.superClass()
    return out


def protegido(widget, QtCore) -> bool:
    """¿Se está escribiendo en este widget (o en un padre que es tabla)?"""
    w = widget
    while w is not None:
        clases = _clases(w)
        if any(c in _PROTEGIDAS for c in clases):
            return True
        if "QAbstractItemView" in clases:
            # el panel de capas de IngeCAD es una tabla que no se edita al
            # teclear; donde una letra edita la celda, no se toca
            try:
                if _int(w.editTriggers()) & _EDITA_AL_TECLEAR:
                    return True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        if "QComboBox" in clases:
            try:
                if w.isEditable():
                    return True
            except (AttributeError, RuntimeError):
                pass
        try:
            if w.isWindow():
                break
            w = w.parentWidget()
        except (AttributeError, RuntimeError):
            break
    return False


def _int(v) -> int:
    try:
        return int(v)
    except TypeError:            # enum de PyQt6 que no es IntEnum
        return int(v.value)


def nombre_tecla(QtCore, key) -> str:
    Key = getattr(QtCore.Qt, "Key", QtCore.Qt)
    for n in _CON_TEXTO + (_ESC,):
        if _int(getattr(Key, n)) == _int(key):
            return n
    return ""


def con_modificadores(QtCore, mods) -> bool:
    M = getattr(QtCore.Qt, "KeyboardModifier", QtCore.Qt)
    for n in ("ControlModifier", "AltModifier", "MetaModifier"):
        if mods & getattr(M, n):
            return True
    return False


class Teclado:
    """Filtro de la aplicación: las teclas de la ventana principal que nadie
    está escribiendo van a la línea de comandos.

    QtCore / QtWidgets: los del programa. Lo propio de cada programa entra por
    funciones:
      ventana()            la ventana principal
      linea()              el campo de la línea de comandos (QLineEdit)
      comando_en_marcha()  bool
      propio(widget)       True si ese widget ya maneja el teclado él mismo
                           (el mapa con una herramienta de GeoCAD, el lienzo
                           de IngeCAD, la línea de comandos)
      entregar(evento)     pasa la tecla a la línea de comandos
    """

    def __init__(self, QtCore, QtWidgets, ventana, linea, comando_en_marcha,
                 propio, entregar):
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.ventana = ventana
        self.linea = linea
        self.comando_en_marcha = comando_en_marcha
        self.propio = propio
        self.entregar = entregar
        T = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
        self._press = T.KeyPress
        self._override = T.ShortcutOverride
        self._filtro = None

    # ---------------------------------------------------------------- decisión
    def _en_ventana(self, w) -> bool:
        main = self.ventana()
        if main is None or w is None:
            return False
        try:
            win = w.window()
            if win is main:
                return True
            # un panel suelto (flotante) de la ventana principal
            return (isinstance(win, self.QtWidgets.QDockWidget)
                    and win.parentWidget() is main)
        except (AttributeError, RuntimeError):
            return False

    def quiere(self, receptor, evento) -> bool:
        """¿Esta tecla, llegando a este widget, va a la línea de comandos?"""
        app = self.QtWidgets.QApplication
        foco = app.focusWidget()
        # sólo la primera entrega (la tecla ignorada sube a los padres)
        if foco is not None and receptor is not foco:
            return False
        if foco is None and receptor is not self.ventana():
            return False
        if app.activeModalWidget() is not None or app.activePopupWidget() is not None:
            return False
        if not self._en_ventana(receptor):
            return False
        linea = self.linea()
        if linea is None or receptor is linea:
            return False
        try:
            if not linea.isVisible():
                return False
        except RuntimeError:
            return False
        if self.propio(receptor) or protegido(receptor, self.QtCore):
            return False
        try:
            con_texto = bool(linea.text())
        except RuntimeError:
            return False
        return decidir(nombre_tecla(self.QtCore, evento.key()), evento.text(),
                       con_modificadores(self.QtCore, evento.modifiers()),
                       con_texto, bool(self.comando_en_marcha()))

    def filtrar(self, receptor, evento) -> bool:
        """Para el eventFilter: True si la tecla ya se entregó."""
        t = evento.type()
        if t != self._press and t != self._override:
            return False
        try:
            if not self.quiere(receptor, evento):
                return False
        except RuntimeError:
            return False
        if t == self._override:
            evento.accept()          # la tecla es nuestra: no dispara atajos
            return True
        self.entregar(evento)
        return True

    # ---------------------------------------------------------------- instalar
    def instalar(self) -> None:
        if self._filtro is not None:
            return
        dueño = self

        class _Filtro(self.QtCore.QObject):
            def eventFilter(self, obj, ev):          # noqa: N802
                try:
                    return dueño.filtrar(obj, ev)
                except Exception:  # noqa: BLE001  (nunca romper el teclado)
                    return False

        self._filtro = _Filtro()
        self.QtWidgets.QApplication.instance().installEventFilter(self._filtro)

    def quitar(self) -> None:
        if self._filtro is None:
            return
        try:
            app = self.QtWidgets.QApplication.instance()
            if app is not None:
                app.removeEventFilter(self._filtro)
        except RuntimeError:
            pass
        self._filtro = None
