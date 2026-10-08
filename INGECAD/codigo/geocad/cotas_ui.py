# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventana CREAR COTA del módulo «Cotas» (3.9.0). Las cuentas están en
cotas.py."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from . import cotas as C

ESCALAS = ("1:50", "1:75", "1:100", "1:200", "1:250", "1:500", "1:1000", "1:2000")


def _icono_cabecera(clave: str, color: QColor) -> QIcon:
    """La cabecera dibujada como en el boceto: línea de cota entre dos
    líneas de referencia."""
    pix = QPixmap(56, 24)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color, 1.4)
    p.setPen(pen)
    y, x1, x2 = 12.0, 10.0, 46.0
    p.drawLine(QPointF(x1, 3), QPointF(x1, 21))
    p.drawLine(QPointF(x2, 3), QPointF(x2, 21))
    p.drawLine(QPointF(x1, y), QPointF(x2, y))
    for x, s in ((x1, 1), (x2, -1)):
        if clave == "oblicuo":
            p.drawLine(QPointF(x - 4, y + 4), QPointF(x + 4, y - 4))
        elif clave == "punto":
            p.setBrush(color)
            p.drawEllipse(QPointF(x, y), 2.4, 2.4)
            p.setBrush(Qt.NoBrush)
        else:
            p.setBrush(color)
            p.drawPolygon([QPointF(x, y), QPointF(x + 7 * s, y - 2.5),
                           QPointF(x + 7 * s, y + 2.5)])
            p.setBrush(Qt.NoBrush)
    p.end()
    return QIcon(pix)


class CrearCotaDialog(QDialog):
    def __init__(self, parent, valores: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crear cota - GeoCAD Yaguareté")
        self.setMinimumWidth(420)
        form = QFormLayout()

        self.escala = QComboBox()
        self.escala.setEditable(True)
        self.escala.setInsertPolicy(QComboBox.NoInsert)
        self.escala.setCompleter(None)
        self.escala.addItems(ESCALAS)
        self.escala.setEditText(f"1:{C._num(valores['escala'])}")
        self.escala.setToolTip("Elegir o escribir: 1:100, 1/100 o 100")
        form.addRow("Escala del papel", self.escala)

        fila = QWidget()
        h = QHBoxLayout(fila)
        h.setContentsMargins(0, 0, 0, 0)
        self.fuente = QComboBox()
        for visible, archivo in C.FUENTES:
            self.fuente.addItem(visible, archivo)
        i = self.fuente.findData(valores["fuente"])
        if i < 0:
            self.fuente.addItem(valores["fuente"], valores["fuente"])
            i = self.fuente.count() - 1
        self.fuente.setCurrentIndex(i)
        self.altura = QDoubleSpinBox()
        self.altura.setRange(0.5, 50.0)
        self.altura.setDecimals(1)
        self.altura.setSingleStep(0.5)
        self.altura.setSuffix(" mm")
        self.altura.setValue(valores["altura"])
        h.addWidget(self.fuente, 1)
        h.addWidget(self.altura)
        form.addRow("Estilo de texto", fila)

        self.decimales = QSpinBox()
        self.decimales.setRange(0, 4)
        self.decimales.setValue(valores["decimales"])
        self.decimales.setToolTip("0 = números enteros")
        form.addRow("Decimales", self.decimales)

        self.angulos = QComboBox()
        for clave, visible, _ in C.ANGULOS:
            self.angulos.addItem(visible, clave)
        self.angulos.setCurrentIndex(max(0, self.angulos.findData(valores.get("angulos", "gms"))))
        self.precision = QComboBox()
        for texto, codigo in C.PRECISION_GMS:
            self.precision.addItem(texto.replace(".", ","), codigo)
        self.precision.setCurrentIndex(max(0, self.precision.findData(
            valores.get("precision_gms", C.PRECISION_GMS_DEFECTO))))
        self.precision.setToolTip("Precisión de los ángulos en grados, minutos y segundos")
        fila = QWidget()
        h = QHBoxLayout(fila)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.angulos, 1)
        h.addWidget(self.precision)
        form.addRow("Ángulos", fila)
        self.angulos.currentIndexChanged.connect(
            lambda _i: self.precision.setEnabled(self.angulos.currentData() == "gms"))
        self.precision.setEnabled(self.angulos.currentData() == "gms")

        fila = QWidget()
        h = QHBoxLayout(fila)
        h.setContentsMargins(0, 0, 0, 0)
        self.cabeceras = QButtonGroup(self)
        for clave, visible, _ in C.CABECERAS:
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(_icono_cabecera(clave, self.palette().color(QPalette.WindowText)))
            b.setIconSize(QSize(56, 24))
            b.setToolTip(visible)
            b.setProperty("clave", clave)
            b.setChecked(clave == valores["cabecera"])
            self.cabeceras.addButton(b)
            h.addWidget(b)
        h.addStretch(1)
        form.addRow("Tipo de cabecera", fila)

        self.resultado = QLabel()
        self.resultado.setWordWrap(True)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Crear cota")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        self._ok = botones.button(QDialogButtonBox.Ok)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addWidget(self.resultado)
        v.addWidget(botones)

        self.escala.editTextChanged.connect(self._actualizar)
        self.altura.valueChanged.connect(self._actualizar)
        self.decimales.valueChanged.connect(self._actualizar)
        self._actualizar()

    def valores(self):
        b = self.cabeceras.checkedButton()
        return {"escala": C.parse_escala(self.escala.currentText()),
                "altura": self.altura.value(),
                "decimales": self.decimales.value(),
                "cabecera": b.property("clave") if b is not None else "oblicuo",
                "fuente": self.fuente.currentData(),
                "angulos": self.angulos.currentData(),
                "precision_gms": self.precision.currentData()}

    def _actualizar(self, *_):
        v = self.valores()
        if v["escala"] is None:
            self.resultado.setText("Escala no válida: escriba 1:100, 1/100 o 100.")
            self._ok.setEnabled(False)
            return
        nombre = C.nombre_estilo(v["escala"], v["altura"], v["decimales"])
        self.resultado.setText(f"Estilo de cota: <b>{nombre}</b><br>"
                               f"Capa: <b>{C.nombre_capa(nombre)}</b>")
        self._ok.setEnabled(True)

    def _aceptar(self):
        if self.valores()["escala"] is not None:
            self.accept()


def crear_cota(ctx) -> None:
    document = ctx.document
    if document is None:
        ctx.echo("CREAR COTA: no hay un dibujo abierto.")
        return
    dlg = CrearCotaDialog(ctx.host, C.ultimos(document))
    if not dlg.exec():
        return
    v = dlg.valores()
    orden, nombre = C.comando_crear(document, v["escala"], v["altura"],
                                    v["decimales"], v["cabecera"], v["fuente"],
                                    v["angulos"], v["precision_gms"])
    ctx.execute(orden)
    window = ctx.host
    for refresco in ("after_style_change", "regen_in_memory"):
        f = getattr(window, refresco, None)
        if callable(f):
            try:
                f()
            except Exception:  # noqa: BLE001
                pass
    ctx.echo(f"Estilo de cota activo: {nombre}. Las cotas van a la capa "
             f"«{C.nombre_capa(nombre)}». Use los botones de MEDIR.")
