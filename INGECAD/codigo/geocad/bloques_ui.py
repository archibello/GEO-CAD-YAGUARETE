# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventanas de los Bloques de GeoCAD: vista previa + confirmación.

  crear(...)    nombre, qué hacer con los objetos y una vista previa del bloque
                con su punto base; botón «Crear bloque».
  insertar(...) lista de bloques con vista previa, escala y rotación; botón
                «Insertar».

Sin Qt (pruebas) devuelven SIN_QT y la herramienta sigue por la línea de
comandos.
"""
from __future__ import annotations

SIN_QT = object()


def _qt():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        return QtCore, QtGui, QtWidgets
    except Exception:  # noqa: BLE001
        return None


def _vista_clase(QtCore, QtGui, QtWidgets):
    class Vista(QtWidgets.QWidget):
        """Dibuja segmentos ((x1, y1), (x2, y2)) ajustados al recuadro, con una
        cruz amarilla en (0, 0): el punto base."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.segs = []
            self.setMinimumSize(320, 240)

        def poner(self, segs):
            self.segs = list(segs)
            self.update()

        def paintEvent(self, _ev):  # noqa: N802
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.fillRect(self.rect(), QtGui.QColor(33, 40, 48))
            xs = [c for (a, b) in self.segs for c in (a[0], b[0])] + [0.0]
            ys = [c for (a, b) in self.segs for c in (a[1], b[1])] + [0.0]
            w, h = self.width() - 24, self.height() - 24
            ancho = max(max(xs) - min(xs), 1e-9)
            alto = max(max(ys) - min(ys), 1e-9)
            k = min(w / ancho, h / alto)
            ox = 12 + (w - ancho * k) / 2 - min(xs) * k
            oy = 12 + (h - alto * k) / 2 + max(ys) * k

            def pt(x, y):
                return QtCore.QPointF(ox + x * k, oy - y * k)

            p.setPen(QtGui.QPen(QtGui.QColor(225, 232, 238), 1.2))
            for a, b in self.segs[:20000]:
                p.drawLine(pt(*a), pt(*b))
            c = pt(0.0, 0.0)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 220, 0), 2))
            p.drawLine(QtCore.QPointF(c.x() - 7, c.y()), QtCore.QPointF(c.x() + 7, c.y()))
            p.drawLine(QtCore.QPointF(c.x(), c.y() - 7), QtCore.QPointF(c.x(), c.y() + 7))
            p.drawText(QtCore.QPointF(c.x() + 9, c.y() - 9), "punto base")
            p.end()

    return Vista


def crear(parent, segs, nombres, cantidad, modo, validar):
    """Confirmación del BLOQUE. Devuelve {"nombre", "modo"}, None (cancelado)
    o SIN_QT. ``validar(nombre)`` devuelve None o el texto del problema."""
    qt = _qt()
    if qt is None:
        return SIN_QT
    QtCore, QtGui, QtWidgets = qt
    Vista = _vista_clase(QtCore, QtGui, QtWidgets)
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("GeoCAD - Crear bloque")
    dlg.setMinimumWidth(460)
    lay = QtWidgets.QVBoxLayout(dlg)
    vista = Vista(dlg)
    vista.poner(segs)
    lay.addWidget(vista, 1)
    lay.addWidget(QtWidgets.QLabel(f"{cantidad} objeto(s). La cruz amarilla es el punto base."))
    form = QtWidgets.QFormLayout()
    combo = QtWidgets.QComboBox(dlg)
    combo.setEditable(True)
    combo.addItems(list(nombres))
    combo.setCurrentText("")
    combo.lineEdit().setPlaceholderText("nombre del bloque")
    form.addRow("Nombre:", combo)
    lay.addLayout(form)
    grupo = QtWidgets.QButtonGroup(dlg)
    fila = QtWidgets.QHBoxLayout()
    radios = {}
    for clave, texto in (("C", "Convertir en bloque"), ("R", "Retener los objetos"),
                         ("B", "Borrar los objetos")):
        r = QtWidgets.QRadioButton(texto, dlg)
        r.setChecked(clave == modo)
        grupo.addButton(r)
        fila.addWidget(r)
        radios[clave] = r
    lay.addLayout(fila)
    aviso = QtWidgets.QLabel("", dlg)
    aviso.setStyleSheet("color: #ffb74d;")
    aviso.setWordWrap(True)
    lay.addWidget(aviso)
    botones = QtWidgets.QDialogButtonBox(dlg)
    ok = botones.addButton("Crear bloque", QtWidgets.QDialogButtonBox.AcceptRole)
    botones.addButton("Cancelar", QtWidgets.QDialogButtonBox.RejectRole)
    lay.addWidget(botones)

    def revisar(_t=None):
        nombre = combo.currentText().strip()
        problema = validar(nombre) if nombre else "Escriba un nombre."
        if problema and problema.startswith("~"):           # aviso, no error
            aviso.setText(problema[1:])
            ok.setEnabled(True)
        else:
            aviso.setText(problema or "")
            ok.setEnabled(not problema)

    combo.currentTextChanged.connect(revisar)
    revisar()
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    combo.setFocus()
    if not dlg.exec():
        return None
    elegido = next(k for k, r in radios.items() if r.isChecked())
    return {"nombre": combo.currentText().strip(), "modo": elegido}


def insertar(parent, nombres, segs_de, escala, rotacion, actual=None):
    """Elegir el bloque a insertar. Devuelve {"nombre", "escala", "rotacion"},
    None o SIN_QT. ``segs_de(nombre)`` da los segmentos de la vista previa."""
    qt = _qt()
    if qt is None:
        return SIN_QT
    QtCore, QtGui, QtWidgets = qt
    Vista = _vista_clase(QtCore, QtGui, QtWidgets)
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("GeoCAD - Insertar bloque")
    dlg.setMinimumWidth(560)
    lay = QtWidgets.QHBoxLayout(dlg)
    lista = QtWidgets.QListWidget(dlg)
    lista.addItems(list(nombres))
    lista.setMaximumWidth(200)
    lay.addWidget(lista)
    der = QtWidgets.QVBoxLayout()
    vista = Vista(dlg)
    der.addWidget(vista, 1)
    form = QtWidgets.QFormLayout()
    esc = QtWidgets.QDoubleSpinBox(dlg)
    esc.setDecimals(4)
    esc.setRange(0.0001, 1e6)
    esc.setValue(escala)
    rot = QtWidgets.QDoubleSpinBox(dlg)
    rot.setDecimals(2)
    rot.setRange(-360, 360)
    rot.setValue(rotacion)
    form.addRow("Escala:", esc)
    form.addRow("Rotación (°):", rot)
    der.addLayout(form)
    der.addWidget(QtWidgets.QLabel("Después: punto de inserción en el dibujo, con referencias."))
    botones = QtWidgets.QDialogButtonBox(dlg)
    botones.addButton("Insertar", QtWidgets.QDialogButtonBox.AcceptRole)
    botones.addButton("Cancelar", QtWidgets.QDialogButtonBox.RejectRole)
    der.addWidget(botones)
    lay.addLayout(der, 1)
    lista.currentTextChanged.connect(lambda n: vista.poner(segs_de(n) if n else []))
    fila = list(nombres).index(actual) if actual in nombres else 0
    lista.setCurrentRow(fila)
    lista.itemDoubleClicked.connect(lambda _i: dlg.accept())
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    if not dlg.exec() or lista.currentItem() is None:
        return None
    return {"nombre": lista.currentItem().text(), "escala": esc.value(), "rotacion": rot.value()}
