# -*- coding: utf-8 -*-
"""Panel 'Línea de comandos' al estilo AutoCAD."""

import html

from qgis.PyQt.QtCore import QEvent, pyqtSignal
from qgis.PyQt.QtGui import QFont, QTextCursor
from qgis.PyQt.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QLineEdit,
                                 QPlainTextEdit, QVBoxLayout, QWidget)

from .compat import enum, qt

# Tema claro (como la línea de comandos de AutoCAD) y tema oscuro
STYLE_LIGHT = """
QWidget#CadCmdRoot { background: #ffffff; }
QPlainTextEdit#CadCmdHistory { background: #f3f3f3; color: #3a3a3a; border: none;
    border-bottom: 1px solid #c9c9c9; selection-background-color: #99c3ee; selection-color: #000000; }
QLabel#CadCmdPrompt { color: #1a1a1a; padding-left: 4px; }
QLabel#CadCmdInfo { color: #6b6b6b; padding-right: 6px; }
QLineEdit#CadCmdInput { background: #ffffff; color: #000000; border: none; padding: 3px 2px;
    selection-background-color: #99c3ee; selection-color: #000000; }
QWidget#CadCmdBar { background: #ffffff; border-top: 1px solid #c9c9c9; }
QLabel#CadCmdRecent { background: #f3f3f3; color: #555555; padding: 1px 4px; }
"""

STYLE = """
QWidget#CadCmdRoot { background: #2b313c; }
QPlainTextEdit#CadCmdHistory { background: #222730; color: #b9c2cc; border: none;
    border-bottom: 1px solid #191d23; selection-background-color: #3d6a99; }
QLabel#CadCmdPrompt { color: #e6e9ee; padding-left: 4px; }
QLabel#CadCmdPrompt a { color: #6fb6ff; text-decoration: none; }
QLabel#CadCmdInfo { color: #8fa0b3; padding-right: 6px; }
QLineEdit#CadCmdInput { background: #2b313c; color: #ffffff; border: none; padding: 3px 2px;
    selection-background-color: #3d6a99; }
QWidget#CadCmdBar { background: #2b313c; border-top: 1px solid #3b4453; }
QLabel#CadCmdRecent { background: #222730; color: #9aa6b2; padding: 1px 4px; }
"""

_KEY = lambda name: qt('Key', name)  # noqa: E731


class CommandLine(QDockWidget):
    submitted = pyqtSignal(str)
    cancelled = pyqtSignal()
    orthoToggled = pyqtSignal()
    osnapToggled = pyqtSignal()
    dynToggled = pyqtSignal()
    promptChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Línea de comandos', parent)
        self.setObjectName('DibujoCADCommandLine')
        root = QWidget()
        root.setObjectName('CadCmdRoot')
        self._root = root
        self.setWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        mono = QFont('Consolas')
        mono.setStyleHint(enum(QFont, 'StyleHint', 'Monospace'))
        mono.setPointSize(max(9, self.font().pointSize()))

        self.history = QPlainTextEdit()
        self.history.setObjectName('CadCmdHistory')
        self.history.setReadOnly(True)
        self.history.setMaximumBlockCount(1000)
        self.history.setFont(mono)
        from qgis.PyQt.QtGui import QFontMetrics
        self._line_h = QFontMetrics(mono).lineSpacing() + 6
        # Historial fijo de tres renglones (el panel no se agranda ni se achica)
        self.history.setFixedHeight(3 * QFontMetrics(mono).lineSpacing() + 8)
        v.addWidget(self.history, 1)

        # Modo compacto (una sola línea, como AutoCAD): en lugar del historial se ven
        # las últimas líneas sobre la barra, que se borran solas al rato
        self.recent = QLabel()
        self.recent.setObjectName('CadCmdRecent')
        self.recent.setFont(mono)
        self.recent.setTextFormat(qt('TextFormat', 'PlainText'))
        self.recent.hide()
        v.addWidget(self.recent)
        from qgis.PyQt.QtCore import QTimer
        self._recent_timer = QTimer()
        self._recent_timer.setSingleShot(True)
        self._recent_timer.setInterval(6000)
        self._recent_timer.timeout.connect(self._fade_recent)
        self._recent_lines = []

        bar = QWidget()
        bar.setObjectName('CadCmdBar')
        self._bar = bar
        h = QHBoxLayout(bar)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(2)
        self.prompt = QLabel()
        self.prompt.setObjectName('CadCmdPrompt')
        self.prompt.setFont(mono)
        self.prompt.setTextFormat(qt('TextFormat', 'RichText'))
        self.prompt.linkActivated.connect(self._option_clicked)
        self.input = QLineEdit()
        self.input.setObjectName('CadCmdInput')
        self.input.setFont(mono)
        self.input.setPlaceholderText('Escriba un comando')
        self.input.installEventFilter(self)
        self.info = QLabel()
        self.info.setObjectName('CadCmdInfo')
        self.info.setFont(mono)
        h.addWidget(self.prompt)
        h.addWidget(self.input, 1)
        h.addWidget(self.info)
        v.addWidget(bar)

        self.raw_mode = False   # True mientras se escribe texto (DTEXT): Espacio no confirma
        self._recent = []
        self._recent_pos = 0
        self._prompt_plain = ''
        self.set_prompt('Comando')
        from .settings import get_setting
        self.apply_theme(get_setting('cmdline_theme', 'light', str))
        self.history.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
        self.history.customContextMenuRequested.connect(self._history_menu)
        for w in (self.prompt, self._bar, self.recent):
            w.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
            w.customContextMenuRequested.connect(lambda pos, w=w: self._bar_menu(w, pos))
        self.compact = False
        root.setFixedHeight(root.sizeHint().height())    # altura fija: 3 renglones + línea de entrada

    def _one_line_height(self):
        title = self.height() - self.widget().height() if self.isVisible() else 0
        if title <= 0 or title > 60:
            title = 0 if self.compact else 24
        return self._line_h + self._bar.sizeHint().height() + 2 + title

    def _restore_height(self):
        from .settings import get_setting
        if not self.compact and not self.isFloating():
            h = get_setting('cmdline_height', 0, int) or self._one_line_height()
            try:
                from qgis.PyQt.QtWidgets import QMainWindow
                mw = self.parent()
                if isinstance(mw, QMainWindow):
                    mw.resizeDocks([self], [max(h, self._one_line_height())], qt('Orientation', 'Vertical'))
            except Exception:  # noqa: BLE001
                pass
        from qgis.PyQt.QtCore import QTimer
        QTimer.singleShot(300, self._end_restore)

    def _end_restore(self):
        self._restoring = False


    def _save_height(self):
        from .settings import set_setting
        if self.isVisible() and not self.compact and self.history.isVisible():
            set_setting('cmdline_height', int(self.height()))

    def reset_height(self):
        """Vuelve a un solo renglón de historial."""
        from .settings import set_setting
        set_setting('cmdline_height', 0)
        self._restoring = True
        self._restore_height()

    # ------------------------------------------------------------ modo compacto
    def set_compact(self, on, save=True):
        from qgis.PyQt.QtWidgets import QWidget as _W
        self.compact = bool(on)
        self.history.setVisible(not self.compact)
        if self.compact:
            self.setTitleBarWidget(_W())          # sin barra de título: ocupa una sola línea
            self.setMinimumHeight(0)
        else:
            self.setTitleBarWidget(None)
            self.recent.hide()
        self._show_recent()
        self._fit_height()
        if save:
            from .settings import set_setting
            set_setting('cmdline_compact', self.compact)

    def _fit_height(self):
        """Ajusta la altura del panel al contenido (en modo compacto, una línea)."""
        try:
            from qgis.PyQt.QtCore import QTimer
            from qgis.PyQt.QtWidgets import QMainWindow
            mw = self.parent()
            if not isinstance(mw, QMainWindow) or self.isFloating():
                return

            def fit():
                if not self.compact:
                    from .settings import get_setting
                    h = max(get_setting('cmdline_height', 0, int), self._one_line_height())
                else:
                    h = self.widget().sizeHint().height() + (0 if not self.history.isVisible() else 100)
                mw.resizeDocks([self], [h], qt('Orientation', 'Vertical'))
            QTimer.singleShot(0, fit)
        except Exception:  # noqa: BLE001
            pass

    def toggle_history(self):
        """F2: en modo compacto muestra u oculta el historial completo."""
        if self.compact:
            self.history.setVisible(not self.history.isVisible())
            if self.history.isVisible():
                self.recent.hide()
            self._fit_height()

    def _show_recent(self):
        if not self.compact or self.history.isVisible() or not self._recent_lines:
            self.recent.hide()
            return
        self.recent.setText('\n'.join(self._recent_lines[-3:]))
        self.recent.show()
        self._recent_timer.start()

    def _fade_recent(self):
        self._recent_lines = []
        self.recent.hide()

    def _menu_extra(self, m):
        a = m.addAction('Fondo oscuro' if self.theme == 'light' else 'Fondo claro (como AutoCAD)')
        a.triggered.connect(lambda *_: self.set_theme('dark' if self.theme == 'light' else 'light'))
        a = m.addAction('Entrada dinámica junto al cursor (F12)')
        a.triggered.connect(lambda *_: self.dynToggled.emit())

    def _bar_menu(self, w, pos):
        from qgis.PyQt.QtWidgets import QMenu
        from .compat import exec_menu
        m = QMenu(self)
        self._menu_extra(m)
        exec_menu(m, w.mapToGlobal(pos))

    # ------------------------------------------------------------ tema
    def apply_theme(self, name):
        from qgis.PyQt.QtGui import QColor
        self.theme = 'dark' if name == 'dark' else 'light'
        self._root.setStyleSheet(STYLE if self.theme == 'dark' else STYLE_LIGHT)
        pal = self.prompt.palette()
        pal.setColor(enum(type(pal), 'ColorRole', 'Link'), QColor('#6fb6ff' if self.theme == 'dark' else '#0063b1'))
        self.prompt.setPalette(pal)

    def set_theme(self, name):
        from .settings import set_setting
        self.apply_theme(name)
        set_setting('cmdline_theme', self.theme)

    def _history_menu(self, pos):
        m = self.history.createStandardContextMenu()
        m.addSeparator()
        self._menu_extra(m)
        a = m.addAction('Borrar historial')
        a.triggered.connect(lambda *_: self.history.clear())
        from .compat import exec_menu
        exec_menu(m, self.history.mapToGlobal(pos))

    # ------------------------------------------------------------ salida
    def echo(self, text):
        self.history.appendPlainText(text)
        self.history.moveCursor(enum(QTextCursor, 'MoveOperation', 'End'))
        if getattr(self, 'compact', False):
            self._recent_lines.extend(str(text).splitlines() or [''])
            del self._recent_lines[:-3]
            self._show_recent()

    def echo_input(self, text):
        self.echo('%s: %s' % (self._prompt_plain, text))

    def set_prompt(self, text, options=None, default=None):
        """text sin ':' final; options = [(clave, etiqueta), ...]; default = valor por defecto."""
        plain = text
        rich = html.escape(text)
        if options:
            plain += ' [%s]' % '/'.join(l for _, l in options)
            links = '/'.join('<a href="%s">%s</a>' % (html.escape(k), html.escape(l)) for k, l in options)
            rich += ' [%s]' % links
        if default is not None:
            plain += ' <%s>' % default
            rich += ' &lt;%s&gt;' % html.escape(str(default))
        self._prompt_plain = plain
        self.prompt.setText(rich + ':')
        self.input.setPlaceholderText('Escriba un comando' if text == 'Comando' else '')
        self.promptChanged.emit()

    def set_info(self, text):
        if text != self.info.text():
            self.info.setText(text)
            self.promptChanged.emit()

    # ------------------------------------------------------------ entrada
    def _option_clicked(self, key):
        self.input.setText(key)
        self.submit()

    def submit(self):
        raw = self.input.text()
        text = raw if self.raw_mode else raw.strip()
        self.input.clear()
        if text:
            self._recent.append(text)
            del self._recent[:-50]
        self._recent_pos = len(self._recent)
        self.submitted.emit(text)

    def feed_key(self, ev):
        """Recibe teclas desde el mapa: en AutoCAD lo que se escribe va a la línea de comandos."""
        key = ev.key()
        if key == _KEY('Key_Space') and self.raw_mode:
            self.input.insert(' ')
            return True
        if key in (_KEY('Key_Return'), _KEY('Key_Enter'), _KEY('Key_Space')):
            self.submit()
            return True
        if key == _KEY('Key_Escape'):
            self.input.clear()
            self.cancelled.emit()
            return True
        if key == _KEY('Key_F8'):
            self.orthoToggled.emit()
            return True
        if key == _KEY('Key_F3'):
            self.osnapToggled.emit()
            return True
        if key == _KEY('Key_F2'):
            self.toggle_history()
            return True
        if key == _KEY('Key_F12'):
            self.dynToggled.emit()
            return True
        if key == _KEY('Key_Backspace'):
            self.input.backspace()
            return True
        text = ev.text()
        mods = ev.modifiers()
        if text and text.isprintable() and not (mods & qt('KeyboardModifier', 'ControlModifier')) \
                and not (mods & qt('KeyboardModifier', 'AltModifier')):
            self.input.insert(text)
            return True
        return False

    def eventFilter(self, obj, ev):
        if obj is self.input and ev.type() == enum(QEvent, 'Type', 'KeyPress'):
            key = ev.key()
            if key == _KEY('Key_Space') and self.raw_mode:
                return False          # en modo texto la barra espaciadora escribe un espacio
            if key in (_KEY('Key_Return'), _KEY('Key_Enter'), _KEY('Key_Space')):
                self.submit()
                return True
            if key == _KEY('Key_Escape'):
                self.input.clear()
                self.cancelled.emit()
                return True
            if key == _KEY('Key_F8'):
                self.orthoToggled.emit()
                return True
            if key == _KEY('Key_F3'):
                self.osnapToggled.emit()
                return True
            if key == _KEY('Key_F2'):
                self.toggle_history()
                return True
            if key == _KEY('Key_F12'):
                self.dynToggled.emit()
                return True
            if key == _KEY('Key_Up') and self._recent:
                self._recent_pos = max(0, self._recent_pos - 1)
                self.input.setText(self._recent[self._recent_pos])
                return True
            if key == _KEY('Key_Down') and self._recent:
                self._recent_pos = min(len(self._recent), self._recent_pos + 1)
                self.input.setText(self._recent[self._recent_pos] if self._recent_pos < len(self._recent) else '')
                return True
        return super().eventFilter(obj, ev)
