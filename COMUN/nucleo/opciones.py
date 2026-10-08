# SPDX-License-Identifier: GPL-3.0-or-later
"""La página "Configuración común (GeoCAD)".

Se arma sola a partir de ``config.SETTINGS``. El complemento de QGIS usa
este mismo archivo, así que los dos menús muestran los mismos campos, en
el mismo orden y con los mismos valores. Sólo depende de Qt
(PySide6 en IngeCAD; en QGIS se importa vía qgis.PyQt).
"""
from __future__ import annotations

try:                                    # IngeCAD
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                   QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
                                   QMessageBox, QSpinBox, QVBoxLayout, QWidget)
except ImportError:                     # QGIS
    from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                     QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
                                     QMessageBox, QSpinBox, QVBoxLayout, QWidget)

from . import config


class SharedOptionsPage(QWidget):
    """Construida con ``(dialog, window)`` por el diálogo de Opciones de
    IngeCAD; su ``apply()`` corre al aceptar."""

    PROGRAM = "IngeCAD"

    def __init__(self, dialog=None, window=None) -> None:
        super().__init__(dialog)
        layout = QVBoxLayout(self)
        intro = QLabel("Estos ajustes los comparten IngeCAD y QGIS: lo que cambie acá "
                       "se ve igual en el menú del otro programa.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        layout.addLayout(form)
        self._widgets = {}
        values = config.load()
        for s in config.SETTINGS:
            value = values[s.key]
            if s.kind == "bool":
                w = QCheckBox(self)
                w.setChecked(bool(value))
            elif s.kind == "choice":
                w = QComboBox(self)
                for data, label in s.choices:
                    w.addItem(label, data)
                w.setCurrentIndex(max(0, w.findData(value)))
            elif s.kind == "int":
                w = QSpinBox(self)
                w.setRange(int(s.minimum), int(s.maximum))
                w.setValue(int(value))
            elif s.kind == "float":
                w = QDoubleSpinBox(self)
                w.setRange(float(s.minimum), float(s.maximum))
                w.setDecimals(2)
                w.setValue(float(value))
            else:
                w = QLineEdit(self)
                w.setText(str(value))
            if s.help:
                w.setToolTip(s.help)
            form.addRow(s.label + ":", w)
            self._widgets[s.key] = w
        where = QLabel(f"Archivo: {config.config_path()}")
        where.setWordWrap(True)
        layout.addWidget(where)
        layout.addStretch(1)

    def values(self) -> dict:
        out = {}
        for s in config.SETTINGS:
            w = self._widgets[s.key]
            if s.kind == "bool":
                out[s.key] = w.isChecked()
            elif s.kind == "choice":
                out[s.key] = w.currentData()
            elif s.kind in ("int", "float"):
                out[s.key] = w.value()
            else:
                out[s.key] = w.text()
        return out

    def apply(self) -> bool:
        try:
            config.save(self.values(), self.PROGRAM)
        except ValueError as exc:
            QMessageBox.warning(self, "Configuración común", str(exc))
            return False
        return True


def open_dialog(parent, program: str = "IngeCAD") -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Configuración común GEO-CAD-YAGUARETÉ")
    box = QVBoxLayout(dialog)
    page = SharedOptionsPage(dialog)
    page.PROGRAM = program
    box.addWidget(page)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
    box.addWidget(buttons)

    def accept():
        if page.apply():
            dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    dialog.resize(560, 420)
    dialog.exec()
