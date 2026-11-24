# -*- coding: utf-8 -*-
"""Ventana «Tabla de puntos» de GEORREF en QGIS (3.93.0): la de IngeCAD
(georref_ui.py, 3.18.0), como la «Tabla de PCT» del Georreferenciador de QGIS.

Arriba el método (los nombres de QGIS) y el remuestreo (sólo para los que
rehacen la imagen); en el medio la tabla: habilitado, ID, X/Y de origen
(píxeles de la imagen), X/Y de destino, dX, dY y residuo. Apagar un punto
recalcula al momento. Abajo el error medio, dónde se guarda, Cargar / Guardar
.points, Marcar más pares, «Abrir en el Georreferenciador de QGIS» (decidido
con Fernando, 23/11/2026), Transformar y Cancelar.

tabla(...) devuelve {"accion": "transformar" | "marcar" | "nativo", "metodo",
"salida", "remuestreo", "fondo", "copia_en", "habilitados", "pares" (si se
cargaron otros)} o None (Cancelar).
"""

import os

from .. import georref_cuentas as G
from . import imagen_geo as IG

COLUMNAS = ("", "ID", "X origen (píx.)", "Y origen (píx.)", "X destino", "Y destino",
            "dX", "dY", "Residuo")


def tabla(parent, tool):
    from qgis.PyQt import QtCore, QtWidgets
    dlg = _Dialogo(QtCore, QtWidgets, parent, tool)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return {"accion": dlg.accion, "metodo": dlg.metodo, "salida": dlg.salida,
            "remuestreo": dlg.remuestreo, "fondo": dlg.fondo, "copia_en": dlg.copia_en,
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
            self.salida = tool._salida
            self.remuestreo = getattr(tool, "_remuestreo", G._ultimo_remuestreo[0])
            self.fondo = getattr(tool, "_fondo", G._ultimo_fondo[0])
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
                self.combo.addItem(nombre if disponible else f"{nombre} (llega más adelante)", clave)
                if not disponible:
                    modelo.item(i).setEnabled(False)
            self.combo.setCurrentIndex(list(G.METODOS).index(self.metodo))
            self.combo.currentIndexChanged.connect(self._cambio_metodo)
            arriba.addWidget(self.combo)
            arriba.addSpacing(20)
            arriba.addWidget(W.QLabel("Remuestreo:"))
            self.combo_rem = rem = W.QComboBox()
            for clave, texto in G.REMUESTREOS.items():
                rem.addItem(texto, clave)
            rem.setCurrentIndex(list(G.REMUESTREOS).index(self.remuestreo))
            rem.currentIndexChanged.connect(self._cambio_remuestreo)
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
            for clave, texto in tool.SALIDAS.items():
                self.combo_salida.addItem(texto, clave)
            self.combo_salida.setCurrentIndex(list(tool.SALIDAS).index(self.salida))
            self.combo_salida.setToolTip(
                "Copia: «<imagen>_georref» con su archivo de mundo; la capa pasa a usarla y "
                "la original no se toca. Archivo de mundo: junto a la original (si había "
                "uno, queda una copia .bak).")
            self.combo_salida.currentIndexChanged.connect(self._cambio_salida)
            fila.addWidget(self.combo_salida)
            como = W.QPushButton("Guardar copia geo como...")
            como.setAutoDefault(False)
            como.setToolTip("Elegir carpeta y nombre de la copia ajustada (con su archivo "
                            "de mundo); la capa pasa a usarla.")
            como.clicked.connect(self._copia_como)
            fila.addWidget(como)
            fila.addStretch(1)
            fila_fondo = W.QHBoxLayout()
            raiz.addLayout(fila_fondo)
            self.etiqueta_fondo = W.QLabel("Fondo de la imagen rehecha:")
            fila_fondo.addWidget(self.etiqueta_fondo)
            self.combo_fondo = W.QComboBox()
            for clave, texto in G.FONDOS.items():
                self.combo_fondo.addItem(texto, clave)
            self.combo_fondo.setCurrentIndex(list(G.FONDOS).index(self.fondo))
            self.combo_fondo.setToolTip("Lo que queda alrededor de la imagen deformada. "
                                        "Transparente: no tapa lo de abajo. Blanco: como un papel.")
            self.combo_fondo.currentIndexChanged.connect(self._cambio_fondo)
            fila_fondo.addWidget(self.combo_fondo)
            fila_fondo.addStretch(1)
            self.donde = W.QLabel()
            self.donde.setWordWrap(True)
            raiz.addWidget(self.donde)
            self._mostrar_donde()

            abajo = W.QHBoxLayout()
            raiz.addLayout(abajo)
            for texto, fn in (("Cargar .points...", self._cargar),
                              ("Guardar .points...", self._guardar),
                              ("Marcar más pares", self._marcar),
                              ("Abrir en el Georreferenciador de QGIS", self._nativo)):
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
                self.estado.setText(f"Error medio: {G._fmt(t['rms'])} (unidades del mapa) · "
                                    f"{G.describir(t['coef'])}")
            self.boton.setEnabled(t["coef"] is not None)
            self._segun_metodo()

        def _segun_metodo(self):
            """Los que rehacen la imagen: siempre una copia, con remuestreo y fondo."""
            rehace = self.metodo in G.REHACEN
            self.combo_rem.setEnabled(rehace)
            self.combo_rem.setToolTip(
                "Cómo se calcula cada píxel de la imagen rehecha." if rehace else
                "Lineal, Helmert y Polinómica 1 no rehacen la imagen: sólo cambian su "
                "lugar, tamaño y giro (sin pérdida).")
            self.combo_fondo.setEnabled(rehace)
            self.etiqueta_fondo.setEnabled(rehace)
            self.combo_salida.setEnabled(not rehace)
            if rehace:
                self.combo_salida.setToolTip("Este método deforma la imagen: siempre se "
                                             "guarda una copia rehecha, con su archivo de mundo.")
            self._mostrar_donde()

        def _cambio_remuestreo(self, i):
            self.remuestreo = self.combo_rem.itemData(i)

        def _cambio_fondo(self, i):
            self.fondo = self.combo_fondo.itemData(i)
            self._mostrar_donde()

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
            ruta, _f = W.QFileDialog.getOpenFileName(self, "Cargar puntos de control",
                                                     self.tool.ruta_points(),
                                                     "Puntos de QGIS (*.points);;Todos (*)")
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
            ruta, _f = W.QFileDialog.getSaveFileName(self, "Guardar puntos de control",
                                                     self.tool.ruta_points(), "Puntos de QGIS (*.points)")
            if not ruta:
                return
            self.tool._pares, self.tool._metodo = self.pares, self.metodo
            self.tool.guardar(ruta)

        def _original(self):
            return self.tool.original

        def _mostrar_donde(self):
            if not hasattr(self, "combo_fondo"):
                return
            orig = self._original()
            if self.metodo in G.REHACEN:
                if orig is None:
                    self.donde.setText("Imagen rehecha: (junto a la original)")
                    return
                from . import georref_qgis as GQ
                try:
                    rs = GQ.rutas(orig, self.fondo, self.copia_en)
                    self.donde.setText("Imagen rehecha en: " + " · ".join(str(r) for r, _f in rs))
                except (OSError, ValueError) as exc:
                    self.donde.setText(f"Imagen rehecha: {exc}")
                return
            if self.salida != "copia":
                self.donde.setText("Archivo de mundo junto a la original: %s" % IG.SI.ruta_mundo(orig)
                                   if orig else "")
                return
            if self.copia_en:
                self.donde.setText(f"Copia geo en: {self.copia_en}")
                return
            try:
                txt = str(IG.nombre_copia(orig)) if orig else "(junto a la original)"
            except OSError:
                txt = "(junto a la original)"
            self.donde.setText(f"Copia geo en: {txt}")

        def _copia_como(self):
            orig = self._original()
            ext = os.path.splitext(orig)[1] if orig else ""
            try:
                inicio = str(self.copia_en or (IG.nombre_copia(orig) if orig else ""))
            except OSError:
                inicio = ""
            ruta, _f = W.QFileDialog.getSaveFileName(self, "Guardar copia geo como", inicio,
                                                     f"Imagen (*{ext});;Todos (*)" if ext else "Todos (*)")
            if not ruta:
                return
            if orig is not None:
                try:
                    ruta = str(IG.destino_copia(ruta, orig))
                except OSError as exc:
                    W.QMessageBox.warning(self, "GEORREF", str(exc))
                    return
            self.copia_en = ruta
            self.salida = "copia"
            self.combo_salida.setCurrentIndex(list(self.tool.SALIDAS).index("copia"))
            self._mostrar_donde()

        def _marcar(self):
            self.accion = "marcar"
            self.accept()

        def _transformar(self):
            self.accion = "transformar"
            self.accept()

        def _nativo(self):
            self.accion = "nativo"
            self.accept()

    return Dialogo()
