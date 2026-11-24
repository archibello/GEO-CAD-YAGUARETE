# -*- coding: utf-8 -*-
"""Ventana «Aspecto de la imagen» de ASPECTOIMAGEN en QGIS (3.91.0).

La misma ventana de IngeCAD (aspecto_ui.py, confirmada con Fernando el
20/10/2026, zoom 3.83.0, limpiar manchas 3.84.0), con las imágenes en arreglos
numpy (QGIS no trae PIL) y sin «Fondo blanco» (decidido con Fernando,
23/11/2026). A la izquierda: Fondo (transparente y cuánto blanco se borra),
Líneas (como están, en negativo o de un color), Opacidad, Contraste y Limpiar
manchas. A la derecha la vista previa sobre cuadriculado, blanco o un fondo
oscuro tipo satélite (sólo para mirar). Abajo: Volver al original, Valores
iniciales, Entregar imagen final..., Aceptar y Cancelar.

ventana(...) devuelve {"accion": "aceptar" | "final" | "original", "valores"} o None.
"""

import os

from .. import aspecto_cuentas as A
from . import aspecto_qgis as AQ

LADO_PREVIA = 360          # el recuadro mínimo de la vista previa
LADO_BASE = 1200           # la vista entera sale de una copia de este lado (3.83.0)
ZOOM_MAX = 8.0             # píxeles de pantalla por píxel del original
FONDOS = (("q", "Cuadriculado"), ("b", "Blanco"), ("s", "Satélite (oscuro)"))


def _qt():
    from qgis.PyQt import QtCore, QtGui, QtWidgets
    if QtWidgets.QApplication.instance() is None:
        return None
    return QtCore, QtGui, QtWidgets


def fondo_previa(ancho, alto, clave):
    """El fondo de la vista previa (arreglo RGBA)."""
    import numpy as np
    im = np.empty((alto, ancho, 4), dtype=np.uint8)
    im[...] = (255, 255, 255, 255)
    if clave == "s":
        im[...] = (47, 61, 42, 255)
        for i in range(12):
            x, y = (i * 37) % max(ancho, 1), (i * 53) % max(alto, 1)
            im[y:y + 31, x:x + 47] = (67, 85, 58, 255)
    elif clave != "b":
        yy, xx = np.mgrid[0:alto, 0:ancho]
        im[((xx // 10 + yy // 10) % 2) == 1] = (204, 204, 204, 255)
    return im


def ventana(parent, original, valores, con_aspecto):
    qt = _qt()
    if qt is None:
        return None
    QtCore, QtGui, QtWidgets = qt
    # 3.92.1: un plano grande tarda en abrir; la barra desde el primer momento
    prog = AQ.Progreso(parent, "ASPECTOIMAGEN", AQ.megapixeles(original))
    try:
        completa = prog.trabajo("Abriendo la imagen para la vista previa", lambda: AQ.abrir(original),
                                0.0, 0.8, "abrir")
        chica = prog.trabajo("Preparando la vista previa", lambda: AQ.reducida(completa, LADO_BASE),
                             0.8, 1.0)
    except A.AspectoError as exc:
        prog.cerrar()
        QtWidgets.QMessageBox.warning(parent, "ASPECTOIMAGEN", str(exc))
        return None
    prog.cerrar()
    tam = (completa.shape[1], completa.shape[0])
    dlg = _Dialogo(QtCore, QtGui, QtWidgets, parent, str(original), tam, chica,
                   A.normalizar(valores), con_aspecto, completa)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return {"accion": dlg.accion, "valores": dlg.valores()}


def _pixmap(QtGui, a):
    return QtGui.QPixmap.fromImage(AQ.a_qimage(a))


def _componer(hecha, clave):
    """La imagen sobre el fondo de la vista previa."""
    import numpy as np
    fondo = fondo_previa(hecha.shape[1], hecha.shape[0], clave).astype(np.float32)
    alfa = hecha[..., 3:4].astype(np.float32) / 255.0
    fondo[..., :3] = hecha[..., :3] * alfa + fondo[..., :3] * (1.0 - alfa)
    return np.clip(np.rint(fondo), 0, 255).astype(np.uint8)


def _ancho(a):
    return a.shape[1]


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
            self.base.setScale(tam[0] / max(1, _ancho(chica)))
            self.detalle = self.scene().addPixmap(QtGui.QPixmap())
            self.detalle.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.detalle.setZValue(1)
            self.detalle.hide()
            self.valores, self.clave = None, "q"
            self.marcar = True             # 3.84.0: lo que la limpieza borra, en rojo
            self.ajustada = True
            self.al_cambiar_zoom = None
            self._reloj = QtCore.QTimer(self)
            self._reloj.setSingleShot(True)
            self._reloj.setInterval(120)
            self._reloj.timeout.connect(self._calcular_detalle)
            self.horizontalScrollBar().valueChanged.connect(self._pedir_detalle)
            self.verticalScrollBar().valueChanged.connect(self._pedir_detalle)

        # -- lo que se muestra -----------------------------------------------
        def mostrar(self, valores, clave, marcar=None):
            self.valores, self.clave = valores, clave
            if marcar is not None:
                self.marcar = bool(marcar)
            hecha = A.procesar_arreglo(chica, valores, escala=_ancho(chica) / max(1, tam[0]),
                                       marcar=self.marcar)
            self.base.setPixmap(_pixmap(QtGui, _componer(hecha, clave)))
            self._pedir_detalle()

        def zoom(self) -> float:
            """Píxeles de pantalla por píxel del original."""
            return self.transform().m11()

        def _pedir_detalle(self, *_):
            self._reloj.start()

        def _calcular_detalle(self):
            t = self.zoom()
            if (self.valores is None or chica.shape == completa.shape   # la entera ya es el original
                    or t <= _ancho(chica) / tam[0] * 1.05):
                self.detalle.hide()
                return
            r = self.mapToScene(self.viewport().rect()).boundingRect()
            x0, y0 = max(0, int(r.left())), max(0, int(r.top()))
            x1, y1 = min(tam[0], int(r.right()) + 2), min(tam[1], int(r.bottom()) + 2)
            if x1 <= x0 or y1 <= y0:
                self.detalle.hide()
                return
            ancho = max(1, min(x1 - x0, int((x1 - x0) * t)))      # nunca más que la pantalla
            alto = max(1, min(y1 - y0, int((y1 - y0) * t)))
            if self.valores.get("limpiar"):
                # la limpieza mira los píxeles del original con su vecindad:
                # se calcula con un margen y después se achica
                m = int(self.valores.get("distancia", 0)) + 1
                bx0, by0 = max(0, x0 - m), max(0, y0 - m)
                bx1, by1 = min(tam[0], x1 + m), min(tam[1], y1 + m)
                hecha = A.procesar_arreglo(completa[by0:by1, bx0:bx1], self.valores,
                                           marcar=self.marcar)
                hecha = hecha[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]
                if (ancho, alto) != (hecha.shape[1], hecha.shape[0]):
                    hecha = AQ.redimensionar(hecha, ancho, alto)
            else:
                pedazo = completa[y0:y1, x0:x1]
                if (ancho, alto) != (pedazo.shape[1], pedazo.shape[0]):
                    pedazo = AQ.redimensionar(pedazo, ancho, alto)
                hecha = A.procesar_arreglo(pedazo, self.valores)
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
             completa=None):
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
            self._poner(valores)
            self.resize(1280, 760)
            QtCore.QTimer.singleShot(0, self.previa.ver_todo)

        # -- armado ---------------------------------------------------------
        def _armar(self):
            raiz = W.QVBoxLayout(self)
            estado = "con aspecto de GeoCAD" if con_aspecto else "original"
            raiz.addWidget(W.QLabel(f"Imagen: {os.path.basename(original)} ({estado}) · "
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

            # 3.84.0 (Fernando): la limpieza de planos, cuidando los textos
            self.limpiar = W.QGroupBox("Limpiar manchas")
            self.limpiar.setCheckable(True)
            self.limpiar.setToolTip(
                "Borra el polvo y los granos del escaneo: lo chico que está solo. Una línea "
                "nunca se borra; un punto, una coma o una tilde cerca de una letra se quedan.")
            grilla = W.QGridLayout(self.limpiar)
            grilla.addWidget(W.QLabel("Distancia"), 0, 0)
            self.distancia = W.QSlider(Qt.Orientation.Horizontal)
            self.distancia.setRange(A.DISTANCIA_MIN, A.DISTANCIA_MAX)
            self.distancia.setToolTip("Hasta dónde busca otra tinta (píxeles del original). "
                                      "Lo que tiene tinta más cerca, se queda: más distancia "
                                      "cuida más los textos.")
            grilla.addWidget(self.distancia, 0, 1)
            self.distancia_txt = W.QLabel()
            self.distancia_txt.setMinimumWidth(48)
            grilla.addWidget(self.distancia_txt, 0, 2)
            grilla.addWidget(W.QLabel("Tolerancia"), 1, 0)
            self.tolerancia = W.QSlider(Qt.Orientation.Horizontal)
            self.tolerancia.setRange(A.TOLERANCIA_MIN, A.TOLERANCIA_MAX)
            self.tolerancia.setToolTip("Cuánta tinta tiene que haber alrededor, en % de una "
                                       "línea fina: más alto borra manchas más grandes. "
                                       "Hasta 50 %, una línea nunca se borra.")
            grilla.addWidget(self.tolerancia, 1, 1)
            self.tolerancia_txt = W.QLabel()
            self.tolerancia_txt.setMinimumWidth(48)
            grilla.addWidget(self.tolerancia_txt, 1, 2)
            self.rojo = W.QCheckBox("Ver en rojo lo que se borra")
            self.rojo.setChecked(True)
            grilla.addWidget(self.rojo, 2, 0, 1, 2)
            self.mancha_txt = W.QLabel()
            self.mancha_txt.setStyleSheet("color: gray;")
            self.mancha_txt.setWordWrap(True)
            grilla.addWidget(self.mancha_txt, 3, 0, 1, 3)
            grilla.setColumnStretch(1, 1)
            izq.addWidget(self.limpiar)

            stem = os.path.splitext(os.path.basename(original))[0]
            nota = W.QLabel(f"Se guarda una copia: {stem}{AQ.SUFIJO}.png, en la carpeta de "
                            "imágenes del proyecto, y la capa pasa a usarla. El original no se "
                            "toca; «Volver al original» la devuelve.")
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
            self.b_original.setToolTip("La capa vuelve a usar su archivo original "
                                       "(la copia queda en el disco).")
            b_inicio = W.QPushButton("Valores iniciales")
            # 3.83.0 (Fernando): «para entregar el trabajo terminado vamos a
            # hacer una captura del resultado y transformar todo en una imagen nueva»
            self.b_final = W.QPushButton("Entregar imagen final...")
            self.b_final.setToolTip(
                f"Una imagen nueva ({stem}{A.SUFIJO_FINAL}.png): el aspecto sobre papel "
                "blanco, opaca. La capa pasa a usarla. El original no se toca.")
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
            self.limpiar.toggled.connect(self._refrescar)
            self.distancia.valueChanged.connect(self._refrescar)
            self.tolerancia.valueChanged.connect(self._refrescar)
            self.rojo.toggled.connect(self._refrescar)
            self.b_final.clicked.connect(self._final)
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
            self.contraste.setValue(v["contraste"])
            self.limpiar.setChecked(v["limpiar"])
            self.distancia.setValue(v["distancia"])
            self.tolerancia.setValue(v["tolerancia"])
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
                                 "contraste": self.contraste.value(),
                                 "limpiar": self.limpiar.isChecked(),
                                 "distancia": self.distancia.value(),
                                 "tolerancia": self.tolerancia.value()})

        def _elegir_color(self):
            c = W.QColorDialog.getColor(QtGui.QColor(self._color), self, "Color de las líneas")
            if c.isValid():
                self._color = c.name().upper()
                self.de_color.setChecked(True)
                self._refrescar()

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
            self.distancia_txt.setText(f"{v['distancia']} px")
            self.tolerancia_txt.setText(f"{v['tolerancia']} %")
            mayor = int(v["tolerancia"] / 100.0 * (2 * v["distancia"] + 1) - 1e-9)
            self.mancha_txt.setText(
                f"Borra manchas de hasta {mayor} píxeles sin otra tinta a menos de "
                f"{v['distancia']} píxeles." if mayor >= 1 else
                "Con estos valores no borra nada: subí la tolerancia o la distancia.")
            self.boton_color.setStyleSheet(f"background-color: {v['color']};")
            self.previa.mostrar(v, self.fondo.currentData(),
                                marcar=v["limpiar"] and self.rojo.isChecked())

    return Dialogo()
