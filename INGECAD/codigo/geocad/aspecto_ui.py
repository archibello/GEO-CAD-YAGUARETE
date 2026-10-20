# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventana «Aspecto de la imagen» de ASPECTOIMAGEN (3.31.0), confirmada con
Fernando el 20/10/2026.

A la izquierda: Fondo (transparente y cuánto blanco se borra), Líneas (como
están, en negativo o de un color) y Opacidad. A la derecha la vista previa
sobre cuadriculado, blanco o un fondo oscuro tipo satélite (sólo para mirar).
Abajo: Volver al original, Valores iniciales, Aceptar y Cancelar.

ventana(...) devuelve {"accion": "aceptar" | "original", "valores"} o None.
"""
from __future__ import annotations

from pathlib import Path

from . import aspecto as A

LADO_PREVIA = 360
FONDOS = (("q", "Cuadriculado"), ("b", "Blanco"), ("s", "Satélite (oscuro)"))


def _qt():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except Exception:  # noqa: BLE001
        return None
    if QtWidgets.QApplication.instance() is None:
        return None
    return QtCore, QtGui, QtWidgets


def fondo_previa(tamano, clave: str):
    """La imagen de fondo de la vista previa (PIL, RGBA)."""
    from PIL import Image, ImageDraw
    w, h = tamano
    if clave == "b":
        return Image.new("RGBA", (w, h), (255, 255, 255, 255))
    if clave == "s":
        im = Image.new("RGBA", (w, h), (47, 61, 42, 255))
        d = ImageDraw.Draw(im)
        for i in range(12):
            x, y = (i * 37) % max(w, 1), (i * 53) % max(h, 1)
            d.rectangle((x, y, x + 46, y + 30), fill=(67, 85, 58, 255))
        return im
    im = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 10):
        for x in range(0, w, 10):
            if (x // 10 + y // 10) % 2:
                d.rectangle((x, y, x + 9, y + 9), fill=(204, 204, 204, 255))
    return im


def ventana(parent, original, valores, con_aspecto: bool):
    qt = _qt()
    if qt is None:
        return None
    QtCore, QtGui, QtWidgets = qt
    from . import georref_progreso as GP

    def leer():
        im = A.abrir(original)
        return im.size, A.reducida(im, LADO_PREVIA)

    try:
        try:
            with A._pil().open(str(original)) as cabecera:       # sólo el tamaño
                mp = cabecera.size[0] * cabecera.size[1] / 1e6
        except Exception:  # noqa: BLE001 -- abrir() dirá qué pasa
            mp = 0.0
        # 3.31.2: un plano grande tarda en abrir; la barra en vez de «no responde»
        with GP.Progreso(parent, "ASPECTOIMAGEN") as prog:
            tam, chica = prog.trabajo("Abriendo la imagen para la vista previa", leer,
                                      A.estimar("abrir", mp), 0, 100)
    except A.AspectoError as exc:
        QtWidgets.QMessageBox.warning(parent, "ASPECTOIMAGEN", str(exc))
        return None
    dlg = _Dialogo(QtCore, QtGui, QtWidgets, parent, Path(original), tam, chica,
                   A.normalizar(valores), con_aspecto)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return {"accion": dlg.accion, "valores": dlg.valores()}


def _Dialogo(QtCore, QtGui, QtWidgets, parent, original, tam, chica, valores, con_aspecto):  # noqa: N802
    W = QtWidgets
    Qt = QtCore.Qt

    class Dialogo(W.QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Aspecto de la imagen (ASPECTOIMAGEN) — GEO-CAD-YAGUARETÉ")
            self.accion = "aceptar"
            self._color = valores["color"]
            self._armar()
            self._poner(valores)

        # -- armado ---------------------------------------------------------
        def _armar(self):
            raiz = W.QVBoxLayout(self)
            estado = "con aspecto de GeoCAD" if con_aspecto else "original"
            raiz.addWidget(W.QLabel(f"Imagen: {original.name} ({estado}) · "
                                    f"{tam[0]} × {tam[1]} píxeles"))
            medio = W.QHBoxLayout()
            raiz.addLayout(medio)
            izq = W.QVBoxLayout()
            medio.addLayout(izq, 1)

            g = W.QGroupBox("Fondo")
            lg = W.QVBoxLayout(g)
            self.transparente = W.QCheckBox("Fondo transparente")
            lg.addWidget(self.transparente)
            fila = W.QHBoxLayout()
            fila.addWidget(W.QLabel("Blanco que se borra"))
            self.blanco = W.QSlider(Qt.Orientation.Horizontal)
            self.blanco.setRange(0, A.BLANCO_MAX)
            fila.addWidget(self.blanco, 1)
            self.blanco_txt = W.QLabel()
            self.blanco_txt.setMinimumWidth(40)
            fila.addWidget(self.blanco_txt)
            lg.addLayout(fila)
            ayuda = W.QLabel("Subilo si el papel es amarillento o el escaneo quedó gris.")
            ayuda.setStyleSheet("color: gray;")
            lg.addWidget(ayuda)
            izq.addWidget(g)

            g = W.QGroupBox("Líneas")
            lg = W.QVBoxLayout(g)
            self.como = W.QRadioButton("Como están")
            self.negativo = W.QRadioButton("En negativo (lo negro pasa a blanco)")
            self.de_color = W.QRadioButton("De un color:")
            self.boton_color = W.QPushButton()
            self.boton_color.setFixedWidth(56)
            fila = W.QHBoxLayout()
            fila.addWidget(self.de_color)
            fila.addWidget(self.boton_color)
            fila.addStretch(1)
            lg.addWidget(self.como)
            lg.addWidget(self.negativo)
            lg.addLayout(fila)
            izq.addWidget(g)

            g = W.QGroupBox()
            fila = W.QHBoxLayout(g)
            fila.addWidget(W.QLabel("Opacidad"))
            self.opacidad = W.QSlider(Qt.Orientation.Horizontal)
            self.opacidad.setRange(A.OPACIDAD_MIN, 100)
            self.opacidad.setSingleStep(5)
            fila.addWidget(self.opacidad, 1)
            self.opacidad_txt = W.QLabel()
            self.opacidad_txt.setMinimumWidth(40)
            fila.addWidget(self.opacidad_txt)
            izq.addWidget(g)

            nota = W.QLabel(f"Se guarda una copia: {original.stem}{A.SUFIJO}.png, junto al "
                            "dibujo. El original no se toca. U lo deshace.")
            nota.setWordWrap(True)
            nota.setStyleSheet("color: gray;")
            izq.addWidget(nota)
            izq.addStretch(1)

            der = W.QVBoxLayout()
            medio.addLayout(der)
            der.addWidget(W.QLabel("Vista previa"))
            self.previa = W.QLabel()
            self.previa.setFixedSize(LADO_PREVIA, LADO_PREVIA)
            self.previa.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.previa.setFrameShape(W.QFrame.Shape.StyledPanel)
            der.addWidget(self.previa)
            fila = W.QHBoxLayout()
            fila.addWidget(W.QLabel("Fondo de la vista previa:"))
            self.fondo = W.QComboBox()
            for clave, texto in FONDOS:
                self.fondo.addItem(texto, clave)
            fila.addWidget(self.fondo, 1)
            der.addLayout(fila)
            der.addStretch(1)

            botones = W.QHBoxLayout()
            self.b_original = W.QPushButton("Volver al original")
            self.b_original.setEnabled(con_aspecto)
            self.b_original.setToolTip("La imagen vuelve a usar su archivo original "
                                       "(la copia queda en el disco).")
            b_inicio = W.QPushButton("Valores iniciales")
            b_aceptar = W.QPushButton("Aceptar")
            b_aceptar.setDefault(True)
            b_cancelar = W.QPushButton("Cancelar")
            botones.addWidget(self.b_original)
            botones.addWidget(b_inicio)
            botones.addStretch(1)
            botones.addWidget(b_aceptar)
            botones.addWidget(b_cancelar)
            raiz.addLayout(botones)

            for w in (self.transparente, self.como, self.negativo, self.de_color):
                w.toggled.connect(self._refrescar)
            self.blanco.valueChanged.connect(self._refrescar)
            self.opacidad.valueChanged.connect(self._refrescar)
            self.fondo.currentIndexChanged.connect(self._refrescar)
            self.boton_color.clicked.connect(self._elegir_color)
            self.b_original.clicked.connect(self._original)
            b_inicio.clicked.connect(lambda: self._poner(A.DEFECTO))
            b_aceptar.clicked.connect(self.accept)
            b_cancelar.clicked.connect(self.reject)

        # -- valores --------------------------------------------------------
        def _poner(self, v):
            v = A.normalizar(v)
            self._llenando = True
            self.transparente.setChecked(v["transparente"])
            self.blanco.setValue(v["blanco"])
            self.opacidad.setValue(v["opacidad"])
            {"como": self.como, "negativo": self.negativo,
             "color": self.de_color}[v["lineas"]].setChecked(True)
            self._color = v["color"]
            self._llenando = False
            self._refrescar()

        def valores(self):
            lineas = ("negativo" if self.negativo.isChecked()
                      else "color" if self.de_color.isChecked() else "como")
            return A.normalizar({"transparente": self.transparente.isChecked(),
                                 "blanco": self.blanco.value(), "lineas": lineas,
                                 "color": self._color, "opacidad": self.opacidad.value()})

        def _elegir_color(self):
            c = W.QColorDialog.getColor(QtGui.QColor(self._color), self, "Color de las líneas")
            if c.isValid():
                self._color = c.name().upper()
                self.de_color.setChecked(True)
                self._refrescar()

        def _original(self):
            self.accion = "original"
            self.accept()

        # -- vista previa ---------------------------------------------------
        def _refrescar(self, *_):
            if getattr(self, "_llenando", False):
                return
            v = self.valores()
            self.blanco.setEnabled(v["transparente"])
            self.blanco_txt.setText(f"{v['blanco']} %")
            self.opacidad_txt.setText(f"{v['opacidad']} %")
            self.boton_color.setStyleSheet(f"background-color: {v['color']};")
            hecha = A.procesar(chica, v)
            vista = fondo_previa(hecha.size, self.fondo.currentData())
            vista.alpha_composite(hecha)
            datos = vista.convert("RGBA").tobytes("raw", "RGBA")
            qimg = QtGui.QImage(datos, vista.width, vista.height, vista.width * 4,
                                QtGui.QImage.Format.Format_RGBA8888).copy()
            self.previa.setPixmap(QtGui.QPixmap.fromImage(qimg))

    return Dialogo()
