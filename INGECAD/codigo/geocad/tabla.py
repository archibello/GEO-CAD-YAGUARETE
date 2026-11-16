# SPDX-License-Identifier: GPL-3.0-or-later
"""Tabla de atributos acoplable (PySide6, dentro de IngeCAD).

Toda la lógica (filas, filtro, orden, valores) está en ``datos.TableState``;
este módulo sólo la dibuja y conecta:

* Elegir filas selecciona los objetos en el dibujo (y hace zoom si es uno).
* Seleccionar en el dibujo marca las filas.
* Editar una celda valida el valor y lo deja pendiente con deshacer
  (AttrEditCommand); se escribe en el archivo sólo al guardar.
* También muestra los SHP importados con base de datos (IMPORTARSHP,
  3.25.1): ahí el cambio queda en el dibujo, con deshacer, y sale con
  EXPORTARSHP.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QItemSelection, QItemSelectionModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDockWidget,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableView, QVBoxLayout, QWidget)

from . import datos, puente
from .datos import tramos_de_filas

PENDING_BG = QColor(255, 243, 176)       # amarillo suave: cambio sin guardar
NEW_BG = QColor(214, 245, 214)           # verde suave: objeto nuevo
DOCK_NAME = "PuenteQGIS_TablaAtributos"
R = Qt.ItemDataRole
_ELEGIBLE = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
_EDITABLE = _ELEGIBLE | Qt.ItemFlag.ItemIsEditable


class AttributeModel(QAbstractTableModel):
    def __init__(self, panel) -> None:
        super().__init__(panel)
        self.panel = panel
        self.state = None

    def set_state(self, state) -> None:
        self.beginResetModel()
        self.state = state
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if (self.state is None or parent.isValid()) else len(self.state.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if (self.state is None or parent.isValid()) else len(self.state.columns)

    def headerData(self, section, orientation, role=R.DisplayRole):
        if self.state is None or role != R.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.state.columns[section]
        return None

    def data(self, index, role=R.DisplayRole):
        if self.state is None or not index.isValid():
            return None
        row = self.state.rows[index.row()]
        col = index.column()
        if role in (R.DisplayRole, R.EditRole):
            return self.state.text(row, col)
        if role == R.BackgroundRole:
            if row.new:
                return QBrush(NEW_BG)
            if self.state.is_pending(row, col):
                return QBrush(PENDING_BG)
        if role == R.FontRole and self.state.is_pending(row, col):
            f = QFont()
            f.setBold(True)
            return f
        if role == R.ForegroundRole and not (row.connected or row.new):
            return QBrush(QColor(140, 140, 140))      # no conectado: gris, sólo lectura
        if role == R.ToolTipRole:
            if not (row.connected or row.new):
                return "No conectado en este dibujo: sólo lectura"
            if row.new:
                return "Objeto nuevo: se crea en el archivo al guardar"
            if self.state.is_pending(row, col):
                return "Cambio sin guardar"
        if role == R.TextAlignmentRole:
            v = self.state.value(row, col)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def flags(self, index):
        # Qt la pide por cada celda al marcar filas: con miles de parcelas
        # tiene que ser barata (3.81.1: banderas armadas una sola vez).
        if self.state is not None and index.isValid() and \
                self.state.cell_editable(self.state.rows[index.row()], index.column()):
            return _EDITABLE
        return _ELEGIBLE

    def setData(self, index, value, role=R.EditRole):
        if role != R.EditRole or self.state is None:
            return False
        row = self.state.rows[index.row()]
        f = self.state.field_of(index.column())
        if f is None:
            return False
        text = "" if value is None else str(value)
        if text == self.state.text(row, index.column()):
            return False
        return self.panel.edit_value(row.fid, f.name, text)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if self.state is None:
            return
        self.layoutAboutToBeChanged.emit()
        self.state.sort(column, order == Qt.SortOrder.DescendingOrder)
        self.layoutChanged.emit()
        self.panel.sync_from_drawing()


class AttributePanel(QWidget):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self._syncing = False
        self._ultima_sync = None
        self._cache_fids = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        self.layer_combo = QComboBox(self)
        self.layer_combo.setMinimumWidth(180)
        top.addWidget(QLabel("Capa:"))
        top.addWidget(self.layer_combo, 1)
        self.refresh_btn = QPushButton("Actualizar", self)
        top.addWidget(self.refresh_btn)
        lay.addLayout(top)
        filt = QHBoxLayout()
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Filtro: MANZANA = 12 Y SUP_M2 > 500 · TITULAR CONTIENE 'pérez'")
        filt.addWidget(self.filter_edit, 1)
        self.only_sel = QCheckBox("Sólo seleccionados", self)
        filt.addWidget(self.only_sel)
        self.only_conn = QCheckBox("Sólo conectados", self)
        self.only_conn.setChecked(True)
        filt.addWidget(self.only_conn)
        self.select_btn = QPushButton("Seleccionar en el dibujo", self)
        filt.addWidget(self.select_btn)
        lay.addLayout(filt)
        self.table = QTableView(self)
        self.model = AttributeModel(self)
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        self.status = QLabel("", self)
        lay.addWidget(self.status)

        self.layer_combo.currentIndexChanged.connect(self._layer_changed)
        self.refresh_btn.clicked.connect(self.reload)
        self.filter_edit.returnPressed.connect(self._apply_filter)
        self.only_sel.toggled.connect(self._apply_filter)
        self.only_conn.toggled.connect(self._apply_filter)
        self.select_btn.clicked.connect(self._select_filtered)
        self.table.selectionModel().selectionChanged.connect(self._rows_selected)
        try:
            window.tools.changed.connect(self._dibujo_cambio)
        except Exception:
            pass
        self.reload()

    # datos
    def document(self):
        return getattr(self.window, "document", None)

    def current_key(self):
        return self.layer_combo.currentData()

    def reload(self) -> None:
        doc = self.document()
        tablas = datos.data_tables(doc) if doc is not None else {}
        keep = self.current_key()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for key in sorted(tablas):
            self.layer_combo.addItem(tablas[key], key)
        if keep in tablas:
            self.layer_combo.setCurrentIndex(self.layer_combo.findData(keep))
        self.layer_combo.blockSignals(False)
        self._layer_changed()

    def _layer_changed(self, *_args) -> None:
        key = self.current_key()
        doc = self.document()
        if key is None or doc is None:
            self.model.set_state(None)
            self.status.setText("No hay capas SIG conectadas (QGIS ▸ Conectar datos SIG) "
                                "ni SHP importados con base de datos (IMPORTARSHP).")
            return
        old = self.model.state
        self.only_conn.setEnabled(not datos.is_imported(doc, key))     # importado: no hay vínculo
        try:
            state = datos.TableState(doc, key)
        except Exception as exc:
            self.model.set_state(None)
            self.status.setText(f"No se puede leer la capa: {exc}")
            return
        state.only_connected = self.only_conn.isChecked()
        state.apply()
        if old is not None and old.key == key:
            state.sort_col, state.sort_desc = old.sort_col, old.sort_desc
            try:
                state.set_query(self.filter_edit.text())
            except datos.QueryError:
                pass
        self.model.set_state(state)
        self.table.resizeColumnsToContents()
        self.sync_from_drawing()

    def _apply_filter(self, *_args) -> None:
        state = self.model.state
        if state is None:
            return
        state.only_selected = set(self._drawing_fids()) if self.only_sel.isChecked() else None
        state.only_connected = self.only_conn.isChecked()
        try:
            state.set_query(self.filter_edit.text())
        except datos.QueryError as exc:
            QMessageBox.warning(self, "Filtro", f"Consulta no válida: {exc}\n\nCampos: "
                                + ", ".join(f.name for f in state.data.fields))
            return
        self.model.set_state(state)
        self.sync_from_drawing()

    def edit_value(self, fid: int, field: str, text: str) -> bool:
        state = self.model.state
        try:
            state.data.validate(field, text)
        except Exception as exc:
            QMessageBox.warning(self, "Valor no válido", str(exc))
            return False
        self.window.tools._execute(datos.edit_command(self.document(), state.key, fid, field, text))
        QTimer.singleShot(0, self.reload)        # recargar fuera de setData
        return True

    # selección dibujo <-> tabla
    def _controller(self):
        return getattr(self.window, "tools", None)

    def _drawing_fids(self):
        ctrl = self._controller()
        key = self.current_key()
        out = set()
        if ctrl is None or key is None:
            return out
        doc = self.document()
        state = self.model.state
        por_objeto = self._fid_por_objeto(state) if state is not None and state.key == key else {}
        for e in ctrl._selection_entities():
            fid = por_objeto.get(e.dxf.handle)
            if fid is None:               # objeto que no estaba al leer la capa
                fid = datos.fid_of(doc, e, key)
            if fid is not None:
                out.add(fid)
        return out

    def _fid_por_objeto(self, state) -> dict:
        """{handle: fid} de la capa, armado una vez por lectura (3.81.1: leer
        los datos de cada objeto seleccionado tardaba ~0,7 s con 12 801)."""
        cache = self._cache_fids
        if cache is None or cache[0] is not state.ents:
            mapa = {}
            for fid, ents in state.ents.items():
                for e in ents:
                    try:
                        mapa[e.dxf.handle] = fid
                    except Exception:
                        pass
            cache = self._cache_fids = (state.ents, mapa)
        return cache[1]

    def sync_from_drawing(self, *_args) -> None:
        state = self.model.state
        if state is None or self._syncing:
            return
        self._syncing = True
        try:
            fids = self._drawing_fids()
            if self.only_sel.isChecked():
                state.only_selected = fids
                state.apply()
                self.model.set_state(state)
            # 3.81.1: todas las filas de una vez, en tramos seguidos (marcarlas
            # de a una crecía al cuadrado: 12 801 parcelas colgaban IngeCAD).
            ultima = self.model.columnCount() - 1
            seleccion = QItemSelection()
            first = None
            for i, j in tramos_de_filas(state.rows, fids):
                seleccion.select(self.model.index(i, 0), self.model.index(j, max(ultima, 0)))
                if first is None:
                    first = self.model.index(i, 0)
            # Vaciar y después marcar: ClearAndSelect compara la selección vieja
            # con la nueva y en Qt eso también crece al cuadrado (mitad -> todo:
            # 1,6 s contra 0,2 s).
            sm = self.table.selectionModel()
            sm.clearSelection()
            if not seleccion.isEmpty():
                sm.select(seleccion, QItemSelectionModel.SelectionFlag.Select
                          | QItemSelectionModel.SelectionFlag.Rows)
            if first is not None:
                self.table.scrollTo(first)
            self.status.setText(state.summary(fids))
            self._ultima_sync = self._firma_sync()
        finally:
            self._syncing = False

    def _firma_sync(self):
        """Lo que define las filas marcadas: estado, orden de filas y selección del dibujo."""
        state = self.model.state
        ctrl = self._controller()
        try:
            sel = frozenset(ctrl.selection) if ctrl is not None else frozenset()
        except Exception:
            sel = None
        return (state, getattr(state, "rows", None), self.current_key(),
                self.only_sel.isChecked(), sel)

    def _dibujo_cambio(self, *_args) -> None:
        """El dibujo avisa cambios muy seguido (también sin tocar la selección):
        sólo se vuelve a sincronizar si cambió algo que la tabla muestra."""
        firma = self._firma_sync()
        ultima = self._ultima_sync
        if (ultima is not None and firma[4] is not None and firma[0] is ultima[0]
                and firma[1] is ultima[1] and firma[2:] == ultima[2:]):
            return
        self.sync_from_drawing()

    def _rows_selected(self, *_args) -> None:
        state = self.model.state
        if state is None or self._syncing:
            return
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        fids = {state.rows[r].fid for r in rows}
        self._select_fids(fids, zoom=len(fids) == 1)

    def _select_fids(self, fids, zoom=False) -> None:
        ctrl = self._controller()
        state = self.model.state
        if ctrl is None or state is None:
            return
        ents = [e for fid in fids for e in state.ents.get(fid, [])]
        self._syncing = True
        try:
            ctrl.selection = {e.dxf.handle for e in ents}
            ctrl._highlight_cache = None
            ctrl._grips_cache = None
            ctrl.changed.emit()
        finally:
            self._syncing = False
        self._ultima_sync = self._firma_sync()      # las filas ya muestran esta selección
        if zoom and ents:
            try:
                self.window.zoom_to_entity(ents[0])
            except Exception:
                pass
        self.status.setText(state.summary(fids))

    def _select_filtered(self) -> None:
        state = self.model.state
        if state is not None:
            self._select_fids({r.fid for r in state.rows})
            self.sync_from_drawing()


def show_table(window) -> None:
    """Abre (o trae al frente) la tabla de atributos, acoplada abajo."""
    dock = window.findChild(QDockWidget, DOCK_NAME)
    if dock is None:
        dock = QDockWidget("Tabla de atributos", window)
        dock.setObjectName(DOCK_NAME)
        panel = AttributePanel(window)
        dock.setWidget(panel)
        window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        puente.register_table(panel)
    else:
        dock.widget().reload()
    dock.show()
    dock.raise_()


def remove_table(window) -> None:
    """Quita la tabla sin dejar rastro (al desactivar el plugin)."""
    dock = window.findChild(QDockWidget, DOCK_NAME)
    if dock is None:
        return
    panel = dock.widget()
    try:
        window.tools.changed.disconnect(panel._dibujo_cambio)
    except Exception:
        pass
    puente.register_table(None)
    window.removeDockWidget(dock)
    dock.deleteLater()
