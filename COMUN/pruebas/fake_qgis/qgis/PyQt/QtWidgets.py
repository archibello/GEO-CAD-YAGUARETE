import enum
class QMenu:
    def __init__(self, *a): self.items = []
    def setObjectName(self, n): pass
    def addSection(self, t): self.items.append("--" + t)
    def clear(self): self.items = []
    def addMenu(self, t):
        m = QMenu(t); m.title = t; self.items.append(m); return m
    def addSeparator(self): self.items.append("---")
    def addAction(self, a): self.items.append(a)
    def menuAction(self): return self
    def deleteLater(self): pass
class QMessageBox:
    class StandardButton(enum.IntFlag):
        Yes = 1; No = 2; Cancel = 4
    answer = None; shown = []
    @staticmethod
    def question(*a): return QMessageBox.answer
    @staticmethod
    def information(parent, title, text): QMessageBox.shown.append(text)


# -- lo mínimo para la ventana «Módulos de GeoCAD» --------------------------------
class _Sig:
    def __init__(self): self.f = []
    def connect(self, f): self.f.append(f)
class _W:
    def __init__(self, *a): self.enabled = True
    def setWordWrap(self, b): pass
    def setMinimumWidth(self, w): self.min_width = w
    def setToolTip(self, t): pass
    def setEnabled(self, b): self.enabled = b
class QLabel(_W):
    pass
class QCheckBox(_W):
    def __init__(self, text, parent=None):
        super().__init__(); self.text = text; self.checked = False; self.toggled = _Sig()
    def setChecked(self, b): self.checked = bool(b)
    def isChecked(self): return self.checked
class QVBoxLayout:
    def __init__(self, *a): self.widgets = []
    def addWidget(self, w): self.widgets.append(w)
class QDialogButtonBox(_W):
    class StandardButton(enum.IntFlag):
        Ok = 1; Cancel = 2
    def __init__(self, *a): super().__init__(); self.accepted = _Sig(); self.rejected = _Sig()
    def setStandardButtons(self, b): pass
class QDialog(_W):
    respuesta = 1                     # 1 = Aceptar, 0 = Cancelar
    abiertos = []
    def __init__(self, *a): super().__init__(); QDialog.abiertos.append(self)
    def setWindowTitle(self, t): self.title = t
    def accept(self): pass
    def reject(self): pass
    def exec(self): return QDialog.respuesta
