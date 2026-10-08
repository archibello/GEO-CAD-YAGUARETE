# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventana «Filtros de selección de objetos» de GeoCAD (FILTRO / FI, 3.2.0).

Como la de AutoCAD: arriba la lista de condiciones; abajo, a la izquierda,
«Seleccionar filtro» con su valor (operador y valor, o X / Y para los
puntos) y los botones Agregar a la lista / Sustituir / Agregar objeto
seleccionado; a la derecha Editar elemento / Suprimir / Borrar lista y los
filtros guardados (Actual, Guardar como, Suprimir lista de filtros actual);
al pie Aplicar y Cancelar.

editar(...) devuelve {"accion": "aplicar" | "objeto", "conds": [...]} o None
(Cancelar). Sin Qt devuelve SIN_QT y la orden sigue por la línea de comandos.
"""
from __future__ import annotations

from . import filtro as F

SIN_QT = object()

#: los valores que ofrece «Elegir...» para cada propiedad de texto
ELEGIBLES = ("capa", "tipo_linea", "nombre_bloque", "estilo_texto", "estilo_cota",
             "patron_sombreado", "conexion", "etiqueta_atributo")
COLORES = ["PorCapa", "PorBloque", "1 - Rojo", "2 - Amarillo", "3 - Verde", "4 - Cian",
           "5 - Azul", "6 - Magenta", "7 - Blanco"]


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
        return QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return None


def valores_en(entidades, clave: str) -> list:
    """Los valores distintos de una propiedad de texto en el dibujo."""
    out = set()
    for e in entidades:
        try:
            v = F.valor(e, clave)
        except Exception:  # noqa: BLE001
            continue
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            if x not in (None, ""):
                out.add(str(x))
    return sorted(out, key=str.upper)


def campos_en(document) -> list:
    """Los campos de las tablas de QGIS conectadas al dibujo."""
    out = []
    try:
        from . import datos, enlace
        for key in enlace.read_links(document.doc):
            for f in datos.LayerData(document, key).fields:
                if f.name not in out:
                    out.append(f.name)
    except Exception:  # noqa: BLE001
        pass
    return out


def editar(parent, conds=None, entidades=(), document=None, con_objeto=True):
    qt = _qt()
    if qt is None:
        return SIN_QT
    QtCore, QtWidgets = qt
    dlg = _Dialogo(QtCore, QtWidgets, parent, list(conds or []), list(entidades),
                   document, con_objeto)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return {"accion": dlg.accion, "conds": list(dlg.conds)}


def _Dialogo(QtCore, QtWidgets, parent, conds, entidades, document, con_objeto):  # noqa: N802
    W = QtWidgets

    class Dialogo(W.QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Filtros de selección de objetos — GEO-CAD-YAGUARETÉ")
            self.conds = conds
            self.accion = "aplicar"
            self._armar()
            self._refrescar()
            self._cambio_propiedad()

        # ------------------------------------------------------- armado
        def _armar(self):
            raiz = W.QVBoxLayout(self)
            self.lista = W.QTreeWidget()
            self.lista.setHeaderLabels(["Propiedad", "Condición"])
            self.lista.setRootIsDecorated(False)
            self.lista.setColumnWidth(0, 300)
            self.lista.setMinimumHeight(170)
            self.lista.itemDoubleClicked.connect(lambda *_: self._editar_elemento())
            raiz.addWidget(self.lista)

            abajo = W.QHBoxLayout()
            raiz.addLayout(abajo)
            izq = W.QVBoxLayout()
            der = W.QVBoxLayout()
            abajo.addLayout(izq, 3)
            abajo.addLayout(der, 2)

            izq.addWidget(W.QLabel("Seleccionar filtro"))
            fila = W.QHBoxLayout()
            self.prop = W.QComboBox()
            for p in F.PROPIEDADES:
                self.prop.addItem(p.nombre, p.clave)
            self.prop.setMaxVisibleItems(25)
            self.prop.currentIndexChanged.connect(self._cambio_propiedad)
            fila.addWidget(self.prop, 1)
            self.elegir = W.QPushButton("Elegir...")
            self.elegir.clicked.connect(self._elegir)
            fila.addWidget(self.elegir)
            izq.addLayout(fila)

            rejilla = W.QGridLayout()
            self.etq, self.ops, self.vals = [], [], []
            for i, nombre in enumerate(("X:", "Y:")):
                etq = W.QLabel(nombre)
                op = W.QComboBox()
                val = W.QComboBox()
                val.setEditable(True)
                rejilla.addWidget(etq, i, 0)
                rejilla.addWidget(op, i, 1)
                rejilla.addWidget(val, i, 2)
                rejilla.setColumnStretch(2, 1)
                self.etq.append(etq), self.ops.append(op), self.vals.append(val)
            izq.addLayout(rejilla)

            fila = W.QHBoxLayout()
            b = W.QPushButton("Agregar a la lista")
            b.clicked.connect(self._agregar)
            fila.addWidget(b)
            b = W.QPushButton("Sustituir")
            b.clicked.connect(self._sustituir)
            fila.addWidget(b)
            izq.addLayout(fila)
            b = W.QPushButton("Agregar objeto seleccionado <")
            b.setEnabled(con_objeto)
            b.setToolTip("Cierra la ventana, pide un objeto y vuelve con sus propiedades"
                         if con_objeto else "No disponible dentro de otra orden")
            b.clicked.connect(self._objeto)
            izq.addWidget(b)
            izq.addStretch(1)

            fila = W.QHBoxLayout()
            for texto, fn in (("Editar elemento", self._editar_elemento),
                              ("Suprimir", self._suprimir), ("Borrar lista", self._borrar_lista)):
                b = W.QPushButton(texto)
                b.clicked.connect(fn)
                fila.addWidget(b)
            der.addLayout(fila)
            caja = W.QGroupBox("Filtros guardados")
            g = W.QGridLayout(caja)
            g.addWidget(W.QLabel("Actual:"), 0, 0)
            self.actual = W.QComboBox()
            self.actual.activated.connect(self._cargar_guardado)
            g.addWidget(self.actual, 0, 1)
            b = W.QPushButton("Guardar como:")
            b.clicked.connect(self._guardar)
            g.addWidget(b, 1, 0)
            self.nombre = W.QLineEdit()
            g.addWidget(self.nombre, 1, 1)
            b = W.QPushButton("Suprimir lista de filtros actual")
            b.clicked.connect(self._borrar_guardado)
            g.addWidget(b, 2, 0, 1, 2)
            der.addWidget(caja)
            der.addStretch(1)
            self._llenar_guardados()

            self.aviso = W.QLabel("")
            self.aviso.setWordWrap(True)
            raiz.addWidget(self.aviso)
            botones = W.QDialogButtonBox()
            botones.addButton("Aplicar", W.QDialogButtonBox.ButtonRole.AcceptRole)
            botones.addButton("Cancelar", W.QDialogButtonBox.ButtonRole.RejectRole)
            botones.accepted.connect(self._aplicar)
            botones.rejected.connect(self.reject)
            raiz.addWidget(botones)
            self.resize(860, 520)

        # ------------------------------------------------------- estado
        def _clave(self):
            return self.prop.currentData()

        def _refrescar(self, elegir=None):
            self.lista.clear()
            for cond, n in zip(self.conds, F.sangrias(self.conds)):
                a, b = F.describir(cond)
                self.lista.addTopLevelItem(W.QTreeWidgetItem(["    " * n + a, b]))
            if elegir is not None and 0 <= elegir < len(self.conds):
                self.lista.setCurrentItem(self.lista.topLevelItem(elegir))
            try:
                F.arbol(self.conds)
                self.aviso.setText("")
            except F.FiltroError as exc:
                self.aviso.setText(f"Atención: {exc}.")

        def _cambio_propiedad(self, *_):
            prop = F.POR_CLAVE[self._clave()]
            punto = prop.clase == "punto"
            con_valor = prop.clase not in ("tipo", "grupo")
            for i in range(2):
                visible = con_valor and (punto or i == 0)
                for w in (self.etq[i], self.ops[i], self.vals[i]):
                    w.setVisible(visible)
                self.ops[i].clear()
                self.vals[i].clear()
            if not con_valor:
                self.elegir.setEnabled(False)
                return
            if punto:
                self.etq[0].setText("X:")
                for op in self.ops:
                    op.addItems(F.OPS)
                return
            ops = F.OPS_TEXTO + ("*",) if prop.clase == "texto" else F.OPS
            if prop.clase == "campo":
                ops = F.OPS
                self.etq[0].setText("Campo:")
                self.etq[1].setText("Valor:")
                for w in (self.etq[1], self.ops[1], self.vals[1]):
                    w.setVisible(True)
                self.ops[0].setVisible(False)
                self.vals[0].addItems(campos_en(document))
                self.ops[1].addItems(ops)
                self.elegir.setEnabled(False)
                return
            self.etq[0].setText("Valor:")
            self.ops[0].addItems(ops)
            if prop.clase == "color":
                self.vals[0].addItems(COLORES)
            self.elegir.setEnabled(self._clave() in ELEGIBLES)

        def _elegir(self):
            clave = self._clave()
            items = valores_en(entidades, clave)
            if not items:
                self.aviso.setText("No hay valores para elegir en el dibujo.")
                return
            item, ok = W.QInputDialog.getItem(self, "Elegir", F.POR_CLAVE[clave].nombre,
                                              items, 0, False)
            if ok:
                self.vals[0].setCurrentText(item)

        def _leer(self):
            """La condición armada abajo, o None (con el aviso)."""
            clave = self._clave()
            prop = F.POR_CLAVE[clave]
            if prop.clase in ("tipo", "grupo"):
                return {"p": clave}
            if prop.clase == "punto":
                cond = {"p": clave}
                for i, eje in enumerate(("x", "y")):
                    op = self.ops[i].currentText() or "*"
                    v = 0.0
                    if op != "*":
                        v = F._num(self.vals[i].currentText())
                        if v is None:
                            self.aviso.setText(f"{eje.upper()}: escriba un número (o use *).")
                            return None
                    cond[eje] = [op, v]
                return cond
            if prop.clase == "campo":
                campo = self.vals[0].currentText().strip()
                if not campo:
                    self.aviso.setText("Falta el nombre del campo.")
                    return None
                return {"p": clave, "campo": campo, "op": self.ops[1].currentText() or "=",
                        "v": self.vals[1].currentText()}
            op = self.ops[0].currentText() or "="
            texto = self.vals[0].currentText()
            if prop.clase == "numero" and op != "*":
                v = F._num(texto)
                if v is None:
                    self.aviso.setText("Escriba un número.")
                    return None
                return {"p": clave, "op": op, "v": v}
            if prop.clase == "color" and op != "*":
                n = F.numero_de_color(texto)
                if n is None or not 0 <= n <= 256:
                    self.aviso.setText("Color: 1 a 255, PorCapa o PorBloque.")
                    return None
                return {"p": clave, "op": op, "v": n}
            return {"p": clave, "op": op, "v": texto}

        def _fila(self):
            item = self.lista.currentItem()
            return -1 if item is None else self.lista.indexOfTopLevelItem(item)

        def _agregar(self):
            cond = self._leer()
            if cond is None:
                return
            i = self._fila()
            pos = len(self.conds) if i < 0 else i + 1
            self.conds.insert(pos, cond)
            self._refrescar(pos)

        def _sustituir(self):
            i = self._fila()
            cond = self._leer()
            if cond is None or i < 0:
                if i < 0:
                    self.aviso.setText("Elija en la lista el renglón a sustituir.")
                return
            self.conds[i] = cond
            self._refrescar(i)

        def _editar_elemento(self):
            i = self._fila()
            if i < 0:
                return
            cond = self.conds[i]
            idx = self.prop.findData(cond.get("p"))
            if idx < 0:
                return
            self.prop.setCurrentIndex(idx)
            self._cambio_propiedad()
            prop = F.POR_CLAVE[cond["p"]]
            if prop.clase == "punto":
                for j, eje in enumerate(("x", "y")):
                    op, v = (cond.get(eje) or ["*", 0])[:2]
                    self.ops[j].setCurrentText(op)
                    self.vals[j].setCurrentText("" if op == "*" else str(v))
            elif prop.clase == "campo":
                self.vals[0].setCurrentText(str(cond.get("campo", "")))
                self.ops[1].setCurrentText(cond.get("op", "="))
                self.vals[1].setCurrentText(str(cond.get("v", "")))
            elif prop.clase not in ("tipo", "grupo"):
                self.ops[0].setCurrentText(cond.get("op", "="))
                v = cond.get("v", "")
                if prop.clase == "color":
                    v = F.describir(cond)[1].split(" ", 1)[-1]
                self.vals[0].setCurrentText(str(v))

        def _suprimir(self):
            i = self._fila()
            if i >= 0:
                del self.conds[i]
                self._refrescar(min(i, len(self.conds) - 1))

        def _borrar_lista(self):
            self.conds.clear()
            self._refrescar()

        def _objeto(self):
            self.accion = "objeto"
            self.accept()

        # ---------------------------------------------------- guardados
        def _llenar_guardados(self, actual=None):
            self.actual.clear()
            nombres = list(F.guardados())
            if F.SIN_NOMBRE not in nombres:
                nombres.insert(0, F.SIN_NOMBRE)
            self.actual.addItems(nombres)
            if actual:
                self.actual.setCurrentText(actual)

        def _cargar_guardado(self, *_):
            conds_g = F.guardados().get(self.actual.currentText())
            if conds_g is not None:
                self.conds[:] = list(conds_g)
                self._refrescar()

        def _guardar(self):
            nombre = self.nombre.text().strip()
            if not nombre or nombre.startswith("*"):
                self.aviso.setText("Escriba un nombre (sin * al principio) para guardar el filtro.")
                return
            try:
                F.guardar(nombre, self.conds)
            except F.FiltroError as exc:
                self.aviso.setText(f"No se guardó: {exc}.")
                return
            self._llenar_guardados(nombre)
            self.aviso.setText(f"Filtro «{nombre}» guardado.")

        def _borrar_guardado(self):
            nombre = self.actual.currentText()
            if nombre and nombre != F.SIN_NOMBRE and F.borrar(nombre):
                self._llenar_guardados()
                self.aviso.setText(f"Filtro «{nombre}» suprimido.")

        def _aplicar(self):
            try:
                F.arbol(self.conds)
            except F.FiltroError as exc:
                self.aviso.setText(f"No se puede aplicar: {exc}.")
                return
            self.accion = "aplicar"
            self.accept()

    return Dialogo()
