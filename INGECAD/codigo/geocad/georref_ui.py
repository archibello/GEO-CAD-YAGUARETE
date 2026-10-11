# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventana «Tabla de puntos» de GEORREF (3.18.0), como la «Tabla de PCT» del
Georreferenciador de QGIS.

Arriba el método (los mismos nombres de QGIS; los que rehacen la imagen
llegan en 3.19.0) y el remuestreo; en el medio la tabla: habilitado, ID,
X/Y de origen (píxeles de la imagen), X/Y de destino, dX, dY y residuo
(unidades del dibujo). Apagar un punto recalcula al momento. Abajo el
error medio, Cargar / Guardar .points, Marcar más pares, Transformar y
Cancelar.

tabla(...) devuelve {"accion": "transformar" | "marcar", "metodo",
"habilitados", "pares" (si se cargaron otros)} o None (Cancelar). Sin Qt
devuelve SIN_QT y la orden sigue por la línea de comandos.
"""
from __future__ import annotations

from . import georref as G
from . import imagengeo as IG

SIN_QT = object()

COLUMNAS = ("", "ID", "X origen (píx.)", "Y origen (píx.)", "X destino", "Y destino",
            "dX", "dY", "Residuo")


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return None
    if QtWidgets.QApplication.instance() is None:
        return None
    return QtCore, QtWidgets


def tabla(parent, tool):
    qt = _qt()
    if qt is None:
        return SIN_QT
    QtCore, QtWidgets = qt
    dlg = _Dialogo(QtCore, QtWidgets, parent, tool)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return {"accion": dlg.accion, "metodo": dlg.metodo, "salida": dlg.salida,
            "copia_en": dlg.copia_en,
            "habilitados": [p["on"] for p in dlg.pares],
            "pares": dlg.pares if dlg.cargados else None}


def _Dialogo(QtCore, QtWidgets, parent, tool):  # noqa: N802
    W = QtWidgets
    Qt = QtCore.Qt

    class Dialogo(W.QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("GEORREF — Tabla de puntos — GEO-CAD-YAGUARETÉ")
            self.tool = tool
            self.pares = [dict(p) for p in tool._pares]
            self.metodo = tool._metodo
            self.salida = getattr(tool, "_salida", G._ultima_salida[0])
            self.copia_en = getattr(tool, "_copia_en", None)
            self.accion = "transformar"
            self.cargados = False
            self._llenando = False
            self._armar()
            self._refrescar()

        def _armar(self):
            raiz = W.QVBoxLayout(self)
            arriba = W.QHBoxLayout()
            raiz.addLayout(arriba)
            arriba.addWidget(W.QLabel("Tipo de transformación:"))
            self.combo = W.QComboBox()
            modelo = self.combo.model()
            for i, (clave, (nombre, minimo, disponible)) in enumerate(G.METODOS.items()):
                self.combo.addItem(nombre if disponible else f"{nombre} (llega en 3.19.0)", clave)
                if not disponible:
                    modelo.item(i).setEnabled(False)
            self.combo.setCurrentIndex(list(G.METODOS).index(self.metodo))
            self.combo.currentIndexChanged.connect(self._cambio_metodo)
            arriba.addWidget(self.combo)
            arriba.addSpacing(20)
            arriba.addWidget(W.QLabel("Remuestreo:"))
            rem = W.QComboBox()
            rem.addItems(["Vecino más próximo", "Lineal", "Cúbica"])
            rem.setEnabled(False)
            rem.setToolTip("Lineal, Helmert y Polinómica 1 no rehacen la imagen: "
                           "sólo cambian su lugar, tamaño y giro (sin pérdida).")
            arriba.addWidget(rem)
            arriba.addStretch(1)

            self.grilla = W.QTableWidget(0, len(COLUMNAS))
            self.grilla.setHorizontalHeaderLabels(list(COLUMNAS))
            self.grilla.verticalHeader().setVisible(False)
            self.grilla.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.grilla.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
            self.grilla.itemChanged.connect(self._cambio_item)
            self.grilla.setMinimumSize(820, 220)
            raiz.addWidget(self.grilla)

            self.estado = W.QLabel()
            self.estado.setWordWrap(True)
            raiz.addWidget(self.estado)

            fila = W.QHBoxLayout()
            raiz.addLayout(fila)
            fila.addWidget(W.QLabel("Al transformar, guardar:"))
            self.combo_salida = W.QComboBox()
            for clave, texto in G.SALIDAS.items():
                self.combo_salida.addItem(texto, clave)
            self.combo_salida.setCurrentIndex(list(G.SALIDAS).index(self.salida))
            self.combo_salida.setToolTip(
                "Copia: «<imagen>_georref» con su archivo de mundo; el dibujo pasa a usarla y "
                "la original no se toca. Con cualquiera de las dos, QGIS abre la imagen en su "
                "lugar (y con el sistema de coordenadas de GeoCAD > Opciones, si lo hay).")
            self.combo_salida.currentIndexChanged.connect(self._cambio_salida)
            fila.addWidget(self.combo_salida)
            como = W.QPushButton("Guardar copia geo como...")
            como.setAutoDefault(False)
            como.setToolTip("Elegir carpeta y nombre de la copia ajustada (con su archivo "
                            "de mundo); el dibujo pasa a usarla.")
            como.clicked.connect(self._copia_como)
            fila.addWidget(como)
            fila.addStretch(1)
            self.donde = W.QLabel()
            self.donde.setWordWrap(True)
            raiz.addWidget(self.donde)
            self._mostrar_donde()

            abajo = W.QHBoxLayout()
            raiz.addLayout(abajo)
            for texto, fn in (("Cargar .points...", self._cargar),
                              ("Guardar .points...", self._guardar),
                              ("Marcar más pares", self._marcar)):
                b = W.QPushButton(texto)
                b.setAutoDefault(False)
                b.clicked.connect(fn)
                abajo.addWidget(b)
            abajo.addStretch(1)
            self.boton = W.QPushButton("Transformar")
            self.boton.setDefault(True)
            self.boton.clicked.connect(self._transformar)
            abajo.addWidget(self.boton)
            cancelar = W.QPushButton("Cancelar")
            cancelar.setAutoDefault(False)
            cancelar.clicked.connect(self.reject)
            abajo.addWidget(cancelar)

        def _refrescar(self):
            t = G.filas_tabla(self.pares, self.metodo)
            self._llenando = True
            try:
                self.grilla.setRowCount(len(t["filas"]))
                for r, f in enumerate(t["filas"]):
                    chk = W.QTableWidgetItem()
                    chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    chk.setCheckState(Qt.CheckState.Checked if f["on"] else Qt.CheckState.Unchecked)
                    self.grilla.setItem(r, 0, chk)
                    valores = [str(f["id"]), f"{f['sx']:.2f}", f"{f['sy']:.2f}",
                               f"{f['X']:.4f}", f"{f['Y']:.4f}"]
                    for k in ("dX", "dY", "residuo"):
                        valores.append("" if f[k] is None else f"{f[k]:.4f}")
                    for c, v in enumerate(valores, 1):
                        it = W.QTableWidgetItem(v)
                        it.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                        self.grilla.setItem(r, c, it)
                self.grilla.resizeColumnsToContents()
            finally:
                self._llenando = False
            if t["coef"] is None:
                self.estado.setText(t["motivo"])
            else:
                self.estado.setText(f"Error medio: {G._fmt(t['rms'])} (unidades del dibujo) · "
                                    f"{G.describir(t['coef'])}")
            self.boton.setEnabled(t["coef"] is not None)

        def _cambio_salida(self, i):
            self.salida = self.combo_salida.itemData(i)
            if hasattr(self, "donde"):
                self._mostrar_donde()

        def _cambio_metodo(self, i):
            self.metodo = self.combo.itemData(i)
            self._refrescar()

        def _cambio_item(self, item):
            if self._llenando or item.column() != 0:
                return
            self.pares[item.row()]["on"] = item.checkState() == Qt.CheckState.Checked
            self._refrescar()

        def _cargar(self):
            inicio = G.ruta_points(self.tool._img, self.tool._documento())
            ruta = IG.pedir_abrir_en(self, "Cargar puntos de control",
                                     "Puntos de QGIS (*.points);;Todos (*)", str(inicio or ""))
            if not ruta:
                return
            try:
                pares = G.leer_points(ruta)
            except OSError as exc:
                W.QMessageBox.warning(self, "GEORREF", f"No se pudo leer el archivo:\n{exc}")
                return
            self.pares, self.cargados = pares, True
            self._refrescar()

        def _guardar(self):
            inicio = G.ruta_points(self.tool._img, self.tool._documento())
            ruta = IG.pedir_guardar(None, "Guardar puntos de control", str(inicio or ""),
                                    "Puntos de QGIS (*.points)", parent=self)
            if not ruta:
                return
            self.tool._pares, self.tool._metodo = self.pares, self.metodo
            self.tool._guardar(ruta)

        def _original(self):
            try:
                return G.archivo_imagen(self.tool._img, self.tool._documento())
            except Exception:  # noqa: BLE001
                return None

        def _mostrar_donde(self):
            if self.salida != "copia":
                self.donde.setText("")
                return
            if self.copia_en:
                self.donde.setText(f"Copia geo en: {self.copia_en}")
                return
            orig = self._original()
            try:
                txt = str(G.nombre_copia(orig)) if orig else "(junto a la original)"
            except OSError:
                txt = "(junto a la original)"
            self.donde.setText(f"Copia geo en: {txt}")

        def _copia_como(self):
            orig = self._original()
            ext = orig.suffix if orig else ""
            try:
                inicio = str(self.copia_en or (G.nombre_copia(orig) if orig else ""))
            except OSError:
                inicio = ""
            ruta = IG.pedir_guardar(None, "Guardar copia geo como", inicio,
                                    f"Imagen (*{ext});;Todos (*)" if ext else "Todos (*)", parent=self)
            if not ruta:
                return
            if orig is not None:
                try:
                    ruta = str(G.destino_copia(ruta, orig))
                except OSError as exc:
                    W.QMessageBox.warning(self, "GEORREF", str(exc))
                    return
            self.copia_en = ruta
            self.salida = "copia"
            self.combo_salida.setCurrentIndex(list(G.SALIDAS).index("copia"))
            self._mostrar_donde()

        def _marcar(self):
            self.accion = "marcar"
            self.accept()

        def _transformar(self):
            self.accion = "transformar"
            self.accept()

    return Dialogo()
