# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventanas de los Bloques de GeoCAD: vista previa + confirmación.

  crear(...)    nombre, qué hacer con los objetos y una vista previa del bloque
                con su punto base y el segundo punto opcional (P2); botones
                «Segundo punto (opcional)...» y «Crear bloque».
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
        cruz amarilla en (0, 0): el punto base; y, si hay, P2 en naranja."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.segs = []
            self.p2 = None
            self.setMinimumSize(320, 240)

        def poner(self, segs, p2=None):
            self.segs = list(segs)
            self.p2 = p2
            self.update()

        def paintEvent(self, _ev):  # noqa: N802
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.fillRect(self.rect(), QtGui.QColor(33, 40, 48))
            extra = [self.p2] if self.p2 is not None else []
            xs = [c for (a, b) in self.segs for c in (a[0], b[0])] + [0.0] + [q[0] for q in extra]
            ys = [c for (a, b) in self.segs for c in (a[1], b[1])] + [0.0] + [q[1] for q in extra]
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
            if self.p2 is not None:
                q = pt(*self.p2)
                naranja = QtGui.QColor(255, 170, 40)
                p.setPen(QtGui.QPen(naranja, 1.5, QtCore.Qt.DashLine))
                p.drawLine(c, q)
                p.setPen(QtGui.QPen(naranja, 2))
                p.drawLine(QtCore.QPointF(q.x() - 6, q.y() - 6), QtCore.QPointF(q.x() + 6, q.y() + 6))
                p.drawLine(QtCore.QPointF(q.x() - 6, q.y() + 6), QtCore.QPointF(q.x() + 6, q.y() - 6))
                p.drawText(QtCore.QPointF(q.x() + 9, q.y() - 9), "P2")
            p.setPen(QtGui.QPen(QtGui.QColor(255, 220, 0), 2))
            p.drawLine(QtCore.QPointF(c.x() - 7, c.y()), QtCore.QPointF(c.x() + 7, c.y()))
            p.drawLine(QtCore.QPointF(c.x(), c.y() - 7), QtCore.QPointF(c.x(), c.y() + 7))
            p.drawText(QtCore.QPointF(c.x() + 9, c.y() - 9), "punto base")
            p.end()

    return Vista


def crear(parent, segs, nombres, cantidad, modo, validar, nombre="", p2=None):
    """Confirmación del BLOQUE. Devuelve {"nombre", "modo", "p2"} («p2»: False
    si se quitó el segundo punto), {"accion": "p2", "nombre", "modo"} para
    elegir el segundo punto en el dibujo, None (cancelado) o SIN_QT.
    ``validar(nombre)`` devuelve None o el texto del problema; ``p2`` es el
    segundo punto ya elegido, relativo al punto base."""
    qt = _qt()
    if qt is None:
        return SIN_QT
    QtCore, QtGui, QtWidgets = qt
    Vista = _vista_clase(QtCore, QtGui, QtWidgets)
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("GEO-CAD-YAGUARETÉ - Crear bloque")
    dlg.setMinimumWidth(460)
    lay = QtWidgets.QVBoxLayout(dlg)
    vista = Vista(dlg)
    estado = {"p2": p2}
    vista.poner(segs, p2)
    lay.addWidget(vista, 1)
    lay.addWidget(QtWidgets.QLabel(f"{cantidad} objeto(s). La cruz amarilla es el punto base (P1)."))
    fila_p2 = QtWidgets.QHBoxLayout()
    texto_p2 = QtWidgets.QLabel("", dlg)
    texto_p2.setWordWrap(True)
    elegir_p2 = QtWidgets.QPushButton("Segundo punto (opcional)...", dlg)
    elegir_p2.setToolTip("P2: al insertar, P1 y P2 escalan y giran el bloque, y después "
                         "se puede reflejar sobre la línea P1-P2 o su perpendicular.")
    quitar_p2 = QtWidgets.QPushButton("Quitar P2", dlg)
    fila_p2.addWidget(texto_p2, 1)
    fila_p2.addWidget(elegir_p2)
    fila_p2.addWidget(quitar_p2)
    lay.addLayout(fila_p2)

    def mostrar_p2():
        q = estado["p2"]
        if q is None:
            texto_p2.setText("Sin segundo punto: se inserta con escala y rotación fijas.")
        else:
            d = (q[0] ** 2 + q[1] ** 2) ** 0.5
            texto_p2.setText(f"P2 a {d:.4g} del punto base: al insertar, escala, giro y reflejos.")
        quitar_p2.setEnabled(q is not None)

    def sin_p2():
        estado["p2"] = None
        vista.poner(segs, None)
        mostrar_p2()

    quitar_p2.clicked.connect(sin_p2)
    elegir_p2.clicked.connect(lambda: dlg.done(2))
    mostrar_p2()
    form = QtWidgets.QFormLayout()
    combo = QtWidgets.QComboBox(dlg)
    combo.setEditable(True)
    combo.addItems(list(nombres))
    combo.setCurrentText(nombre or "")
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
    res = dlg.exec()
    elegido = next(k for k, r in radios.items() if r.isChecked())
    if res == 2:
        return {"accion": "p2", "nombre": combo.currentText().strip(), "modo": elegido}
    if not res:
        return None
    return {"nombre": combo.currentText().strip(), "modo": elegido, "p2": estado["p2"] is not None}


def insertar(parent, nombres, segs_de, escala, rotacion, actual=None, tiene_p2=None):
    """Elegir el bloque a insertar. Devuelve {"nombre", "escala", "rotacion"},
    None o SIN_QT. ``segs_de(nombre)`` da los segmentos de la vista previa."""
    qt = _qt()
    if qt is None:
        return SIN_QT
    QtCore, QtGui, QtWidgets = qt
    Vista = _vista_clase(QtCore, QtGui, QtWidgets)
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("GEO-CAD-YAGUARETÉ - Insertar bloque")
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
    nota = QtWidgets.QLabel("", dlg)
    nota.setWordWrap(True)
    der.addWidget(nota)
    botones = QtWidgets.QDialogButtonBox(dlg)
    botones.addButton("Insertar", QtWidgets.QDialogButtonBox.AcceptRole)
    botones.addButton("Cancelar", QtWidgets.QDialogButtonBox.RejectRole)
    der.addWidget(botones)
    lay.addLayout(der, 1)
    def cambiar(n):
        vista.poner(segs_de(n) if n else [])
        dos = bool(n) and bool(tiene_p2 and tiene_p2(n))
        esc.setEnabled(not dos)
        rot.setEnabled(not dos)
        nota.setText("Bloque con P2: en el dibujo P1, P2 (escala y giro) y reflejos."
                     if dos else "Después: punto de inserción en el dibujo, con referencias.")

    lista.currentTextChanged.connect(cambiar)
    fila = list(nombres).index(actual) if actual in nombres else 0
    lista.setCurrentRow(fila)
    lista.itemDoubleClicked.connect(lambda _i: dlg.accept())
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    if not dlg.exec() or lista.currentItem() is None:
        return None
    return {"nombre": lista.currentItem().text(), "escala": esc.value(), "rotacion": rot.value()}
