# SPDX-License-Identifier: GPL-3.0-or-later
"""Formulario de atributos para un objeto nuevo (PySide6, dentro de IngeCAD)."""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QVBoxLayout)

PLACEHOLDER = {"date": "DD/MM/AAAA", "datetime": "DD/MM/AAAA HH:MM",
               "int": "número entero", "real": "número"}


def ask_form(parent, title: str, fields, validate):
    """Pide los valores de ``fields``; devuelve {campo: texto} (sólo los
    completados) o None si se cancela. ``validate(nombre, texto)`` lanza
    una excepción con el motivo si el valor no entra."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    box = QVBoxLayout(dialog)
    form = QFormLayout()
    box.addLayout(form)
    widgets = {}
    for f in fields:
        if f.family == "bool":
            w = QComboBox(dialog)
            w.addItems(["", "Verdadero", "Falso"])
        else:
            w = QLineEdit(dialog)
            if f.family in PLACEHOLDER:
                w.setPlaceholderText(PLACEHOLDER[f.family])
        label = f.label + (" *" if f.required else "")
        form.addRow(label + ":", w)
        widgets[f.name] = (f, w)
    note = QLabel("* obligatorio. Los valores se guardan en el archivo al "
                  "«Devolver todo a QGIS».")
    note.setWordWrap(True)
    box.addWidget(note)
    error = QLabel("")
    error.setStyleSheet("color: #c0392b;")
    error.setWordWrap(True)
    box.addWidget(error)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel, dialog)
    box.addWidget(buttons)
    result = {}

    def text_of(f, w):
        if isinstance(w, QComboBox):
            return {"Verdadero": "V", "Falso": "F"}.get(w.currentText(), "")
        return w.text()

    def accept():
        result.clear()
        for name, (f, w) in widgets.items():
            text = text_of(f, w)
            if f.required and not text.strip():
                error.setText(f"«{name}» es obligatorio.")
                w.setFocus()
                return
            if text.strip():
                try:
                    validate(name, text)
                except Exception as exc:
                    error.setText(str(exc))
                    w.setFocus()
                    return
                result[name] = text
        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    dialog.resize(460, min(120 + 34 * len(fields), 700))
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dict(result)
