# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventana «Aspecto de la imagen» de ASPECTOIMAGEN (3.31.0), confirmada con
Fernando el 20/10/2026.

A la izquierda: Fondo (transparente y cuánto blanco se borra; fondo blanco
en su capa, 3.82.0), Líneas (como
están, en negativo o de un color) y Opacidad. A la derecha la vista previa
sobre cuadriculado, blanco o un fondo oscuro tipo satélite (sólo para mirar).
Abajo: Volver al original, Valores iniciales, Aceptar y Cancelar.

ventana(...) devuelve {"accion": "aceptar" | "original", "valores",
"fondo_blanco"} o None.
"""
from __future__ import annotations

from pathlib import Path

from . import aspecto as A

LADO_PREVIA = 360          # el recuadro mínimo de la vista previa
#: 3.83.0 (Fernando: «mejorar el tamaño de la imagen previa, o poder hacer
#: zoom»): la vista entera sale de una copia de este lado; al acercarse, lo
#: que se ve se calcula con los píxeles del original
LADO_BASE = 1200
ZOOM_MAX = 8.0             # píxeles de pantalla por píxel del original
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


def ventana(parent, original, valores, con_aspecto: bool, fondo: bool = False):
    qt = _qt()
    if qt is None:
        return None
    QtCore, QtGui, QtWidgets = qt
    from . import georref_progreso as GP

    def leer():
        im = A.abrir(original)
        return im.size, A.reducida(im, LADO_BASE), im

    try:
        try:
            with A._pil().open(str(original)) as cabecera:       # sólo el tamaño
                mp = cabecera.size[0] * cabecera.size[1] / 1e6
        except Exception:  # noqa: BLE001 -- abrir() dirá qué pasa
            mp = 0.0
        # 3.31.2: un plano grande tarda en abrir; la barra en vez de «no responde»
        with GP.Progreso(parent, "ASPECTOIMAGEN") as prog:
            tam, chica, completa = prog.trabajo("Abriendo la imagen para la vista previa", leer,
                                      A.estimar("abrir", mp), 0, 100)
    except A.AspectoError as exc:
        QtWidgets.QMessageBox.warning(parent, "ASPECTOIMAGEN", str(exc))
        return None
    dlg = _Dialogo(QtCore, QtGui, QtWidgets, parent, Path(original), tam, chica,
                   A.normalizar(valores), con_aspecto, fondo, completa)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return {"accion": dlg.accion, "valores": dlg.valores(),
            "fondo_blanco": dlg.fondo_blanco.isChecked()}


def _pixmap(QtGui, im):
    datos = im.convert("RGBA").tobytes("raw", "RGBA")
    qimg = QtGui.QImage(datos, im.width, im.height, im.width * 4,
                        QtGui.QImage.Format.Format_RGBA8888).copy()
    return QtGui.QPixmap.fromImage(qimg)


def _componer(hecha, clave):
    vista = fondo_previa(hecha.size, clave)
    vista.alpha_composite(hecha)
    return vista


def _Previa(QtCore, QtGui, QtWidgets, tam, chica, completa):  # noqa: N802
    """La vista previa con zoom (3.83.0): la escena va en píxeles del
    original; la vista entera sale de ``chica`` y, más cerca de lo que ella
    alcanza, lo que se ve se calcula con ``completa`` (sólo ese pedazo, al
    tamaño de la pantalla: rápido aun con un plano de 37 megapíxeles).
    Rueda: zoom donde está el cursor; arrastrar: mover; doble clic: ver todo."""
    W = QtWidgets
    Qt = QtCore.Qt

    class Previa(W.QGraphicsView):
        def __init__(self):
            super().__init__()
            self.setScene(W.QGraphicsScene(self))
            self.scene().setSceneRect(0, 0, tam[0], tam[1])
            self.setMinimumSize(LADO_PREVIA * 16 // 9, LADO_PREVIA)
            self.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Expanding)
            self.setDragMode(W.QGraphicsView.DragMode.ScrollHandDrag)
            self.setTransformationAnchor(W.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
            self.setBackgroundBrush(QtGui.QColor(60, 60, 60))
            self.base = self.scene().addPixmap(QtGui.QPixmap())
            self.base.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.base.setScale(tam[0] / max(1, chica.width))
            self.detalle = self.scene().addPixmap(QtGui.QPixmap())
            self.detalle.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.detalle.setZValue(1)
            self.detalle.hide()
            self.valores, self.clave = None, "q"
            self.ajustada = True
            self.al_cambiar_zoom = None
            self._reloj = QtCore.QTimer(self)
            self._reloj.setSingleShot(True)
            self._reloj.setInterval(120)
            self._reloj.timeout.connect(self._calcular_detalle)
            self.horizontalScrollBar().valueChanged.connect(self._pedir_detalle)
            self.verticalScrollBar().valueChanged.connect(self._pedir_detalle)

        # -- lo que se muestra -----------------------------------------------
        def mostrar(self, valores, clave):
            self.valores, self.clave = valores, clave
            self.base.setPixmap(_pixmap(QtGui, _componer(A.procesar(chica, valores), clave)))
            self._pedir_detalle()

        def zoom(self) -> float:
            """Píxeles de pantalla por píxel del original."""
            return self.transform().m11()

        def _pedir_detalle(self, *_):
            self._reloj.start()

        def _calcular_detalle(self):
            t = self.zoom()
            if (self.valores is None or chica.size == completa.size   # la entera ya es el original
                    or t <= chica.width / tam[0] * 1.05):
                self.detalle.hide()
                return
            r = self.mapToScene(self.viewport().rect()).boundingRect()
            x0, y0 = max(0, int(r.left())), max(0, int(r.top()))
            x1, y1 = min(tam[0], int(r.right()) + 2), min(tam[1], int(r.bottom()) + 2)
            if x1 <= x0 or y1 <= y0:
                self.detalle.hide()
                return
            pedazo = completa.crop((x0, y0, x1, y1))
            ancho = max(1, min(x1 - x0, int((x1 - x0) * t)))      # nunca más que la pantalla
            alto = max(1, min(y1 - y0, int((y1 - y0) * t)))
            if (ancho, alto) != pedazo.size:
                pedazo = pedazo.resize((ancho, alto))
            hecha = A.procesar(pedazo, self.valores)
            self.detalle.setPixmap(_pixmap(QtGui, _componer(hecha, self.clave)))
            self.detalle.setPos(x0, y0)
            self.detalle.setScale((x1 - x0) / ancho)
            self.detalle.show()

        # -- zoom ------------------------------------------------------------
        def ver_todo(self):
            self.resetTransform()
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.ajustada = True
            self._avisar()

        def poner_zoom(self, t):
            minimo = self._minimo()
            t = max(minimo, min(ZOOM_MAX, t))
            self.scale(t / self.zoom(), t / self.zoom())
            self.ajustada = t <= minimo * 1.001
            self._avisar()

        def _minimo(self):
            v = self.viewport().rect()
            return min(v.width() / tam[0], v.height() / tam[1])

        def _avisar(self):
            self._pedir_detalle()
            if self.al_cambiar_zoom:
                self.al_cambiar_zoom(self.zoom())

        def wheelEvent(self, ev):  # noqa: N802
            pasos = ev.angleDelta().y() / 120.0
            if pasos:
                self.poner_zoom(self.zoom() * (1.25 ** pasos))
            ev.accept()

        def mouseDoubleClickEvent(self, ev):  # noqa: N802
            self.ver_todo()

        def resizeEvent(self, ev):  # noqa: N802
            super().resizeEvent(ev)
            if self.ajustada:
                self.ver_todo()
            else:
                self._pedir_detalle()

    return Previa()


def _Dialogo(QtCore, QtGui, QtWidgets, parent, original, tam, chica, valores, con_aspecto,  # noqa: N802
             fondo=False, completa=None):
    W = QtWidgets
    Qt = QtCore.Qt
    if completa is None:
        completa = chica

    class Dialogo(W.QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Aspecto de la imagen (ASPECTOIMAGEN) — GEO-CAD-YAGUARETÉ")
            self.accion = "aceptar"
            self._color = valores["color"]
            self._armar()
            if fondo:                         # ya tiene su fondo: se mira sobre blanco
                self._ver_fondo_blanco(True)
            self._poner(valores)
            self.resize(1280, 760)
            QtCore.QTimer.singleShot(0, self.previa.ver_todo)

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
            # 3.82.0 (Fernando): un fondo blanco en su capa, que se prende y
            # se apaga, en vez de rellenar los píxeles
            self.fondo_blanco = W.QCheckBox("Fondo blanco")
            self.fondo_blanco.setChecked(bool(fondo))
            self.fondo_blanco.setToolTip(
                f"Un sombreado blanco debajo de la imagen, en la capa {A.CAPA_FONDO}: "
                "apagando la capa se saca de la vista. La imagen no se toca.")
            fila = W.QHBoxLayout()
            fila.addWidget(self.transparente)
            fila.addStretch(1)
            fila.addWidget(self.fondo_blanco)
            lg.addLayout(fila)
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
            grilla = W.QGridLayout(g)
            grilla.addWidget(W.QLabel("Opacidad"), 0, 0)
            self.opacidad = W.QSlider(Qt.Orientation.Horizontal)
            self.opacidad.setRange(A.OPACIDAD_MIN, 100)
            self.opacidad.setSingleStep(5)
            grilla.addWidget(self.opacidad, 0, 1)
            self.opacidad_txt = W.QLabel()
            self.opacidad_txt.setMinimumWidth(48)
            grilla.addWidget(self.opacidad_txt, 0, 2)
            # 3.83.0 (Fernando): las líneas más fuertes, sean del color que sean
            grilla.addWidget(W.QLabel("Contraste"), 1, 0)
            self.contraste = W.QSlider(Qt.Orientation.Horizontal)
            self.contraste.setRange(100, A.CONTRASTE_MAX)
            self.contraste.setSingleStep(10)
            self.contraste.setPageStep(50)
            self.contraste.setToolTip("Refuerza las líneas tenues (negras o de color); el "
                                      "papel blanco sigue blanco. 100 %: como están.")
            grilla.addWidget(self.contraste, 1, 1)
            self.contraste_txt = W.QLabel()
            self.contraste_txt.setMinimumWidth(48)
            grilla.addWidget(self.contraste_txt, 1, 2)
            grilla.setColumnStretch(1, 1)
            izq.addWidget(g)

            nota = W.QLabel(f"Se guarda una copia: {original.stem}{A.SUFIJO}.png, junto al "
                            "dibujo. El original no se toca. U lo deshace.")
            nota.setWordWrap(True)
            nota.setStyleSheet("color: gray;")
            izq.addWidget(nota)
            izq.addStretch(1)

            der = W.QVBoxLayout()
            medio.addLayout(der)
            medio.setStretch(1, 2)
            fila = W.QHBoxLayout()
            fila.addWidget(W.QLabel("Vista previa"))
            fila.addStretch(1)
            self.zoom_txt = W.QLabel()
            fila.addWidget(self.zoom_txt)
            b_todo = W.QPushButton("Ver todo")
            b_todo.setToolTip("Doble clic en la vista hace lo mismo.")
            b_real = W.QPushButton("1:1")
            b_real.setToolTip("Un píxel del original por píxel de pantalla.")
            fila.addWidget(b_todo)
            fila.addWidget(b_real)
            der.addLayout(fila)
            self.previa = _Previa(QtCore, QtGui, QtWidgets, tam, chica, completa)
            self.previa.al_cambiar_zoom = lambda t: self.zoom_txt.setText(
                f"Zoom {t * 100:.0f} %".replace(".", ","))
            b_todo.clicked.connect(self.previa.ver_todo)
            b_real.clicked.connect(lambda: self.previa.poner_zoom(1.0))
            ayuda = W.QLabel("Rueda: acercar y alejar · arrastrar: mover · doble clic: ver todo")
            ayuda.setStyleSheet("color: gray;")
            der.addWidget(self.previa, 1)
            der.addWidget(ayuda)
            fila = W.QHBoxLayout()
            fila.addWidget(W.QLabel("Fondo de la vista previa:"))
            self.fondo = W.QComboBox()
            for clave, texto in FONDOS:
                self.fondo.addItem(texto, clave)
            fila.addWidget(self.fondo, 1)
            der.addLayout(fila)

            botones = W.QHBoxLayout()
            self.b_original = W.QPushButton("Volver al original")
            self.b_original.setEnabled(con_aspecto)
            self.b_original.setToolTip("La imagen vuelve a usar su archivo original "
                                       "(la copia queda en el disco).")
            b_inicio = W.QPushButton("Valores iniciales")
            # 3.83.0 (Fernando): «para entregar el trabajo terminado vamos a
            # hacer una captura del resultado y transformar todo en una imagen nueva»
            self.b_final = W.QPushButton("Entregar imagen final...")
            self.b_final.setToolTip(
                f"Una imagen nueva ({original.stem}{A.SUFIJO_FINAL}.png): el aspecto sobre papel "
                "blanco, opaca. La imagen del dibujo pasa a usarla y se quita su fondo de "
                f"la capa {A.CAPA_FONDO}. El original no se toca. U lo deshace.")
            b_aceptar = W.QPushButton("Aceptar")
            b_aceptar.setDefault(True)
            b_cancelar = W.QPushButton("Cancelar")
            botones.addWidget(self.b_original)
            botones.addWidget(b_inicio)
            botones.addStretch(1)
            botones.addWidget(self.b_final)
            botones.addWidget(b_aceptar)
            botones.addWidget(b_cancelar)
            raiz.addLayout(botones)

            for w in (self.transparente, self.como, self.negativo, self.de_color):
                w.toggled.connect(self._refrescar)
            self.blanco.valueChanged.connect(self._refrescar)
            self.opacidad.valueChanged.connect(self._refrescar)
            self.contraste.valueChanged.connect(self._refrescar)
            self.b_final.clicked.connect(self._final)
            self.fondo.currentIndexChanged.connect(self._refrescar)
            self.fondo_blanco.toggled.connect(self._ver_fondo_blanco)
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
            self.contraste.setValue(v["contraste"])
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
                                 "color": self._color, "opacidad": self.opacidad.value(),
                                 "contraste": self.contraste.value()})

        def _elegir_color(self):
            c = W.QColorDialog.getColor(QtGui.QColor(self._color), self, "Color de las líneas")
            if c.isValid():
                self._color = c.name().upper()
                self.de_color.setChecked(True)
                self._refrescar()

        def _ver_fondo_blanco(self, si):
            # la vista previa muestra cómo queda sobre su fondo blanco
            if si:
                i = self.fondo.findData("b")
                if i >= 0:
                    self.fondo.setCurrentIndex(i)

        def _final(self):
            self.accion = "final"
            self.accept()

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
            self.contraste_txt.setText(f"{v['contraste']} %")
            self.boton_color.setStyleSheet(f"background-color: {v['color']};")
            self.previa.mostrar(v, self.fondo.currentData())

    return Dialogo()
