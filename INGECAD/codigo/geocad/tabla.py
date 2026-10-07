# SPDX-License-Identifier: GPL-3.0-or-later
"""Tabla de atributos acoplable (PySide6, dentro de IngeCAD).

Toda la lógica (filas, filtro, orden, valores) está en ``datos.TableState``;
este módulo sólo la dibuja y conecta:

* Elegir filas selecciona los objetos en el dibujo (y hace zoom si es uno).
* Seleccionar en el dibujo marca las filas.
* Editar una celda valida el valor y lo deja pendiente con deshacer
  (AttrEditCommand); se escribe en el archivo sólo al guardar.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDockWidget,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableView, QVBoxLayout, QWidget)

from . import datos, enlace, puente

PENDING_BG = QColor(255, 243, 176)       # amarillo suave: cambio sin guardar
NEW_BG = QColor(214, 245, 214)           # verde suave: objeto nuevo
DOCK_NAME = "PuenteQGIS_TablaAtributos"
R = Qt.ItemDataRole


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
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self.state is not None and index.isValid() and \
                self.state.cell_editable(self.state.rows[index.row()], index.column()):
            base |= Qt.ItemFlag.ItemIsEditable
        return base

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
            window.tools.changed.connect(self.sync_from_drawing)
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
        links = enlace.read_links(doc.doc) if doc is not None else {}
        keep = self.current_key()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for key in sorted(links):
            self.layer_combo.addItem(f"{key}  ({links[key].name})", key)
        if keep in links:
            self.layer_combo.setCurrentIndex(self.layer_combo.findData(keep))
        self.layer_combo.blockSignals(False)
        self._layer_changed()

    def _layer_changed(self, *_args) -> None:
        key = self.current_key()
        doc = self.document()
        if key is None or doc is None:
            self.model.set_state(None)
            self.status.setText("No hay capas SIG conectadas (QGIS ▸ Conectar datos SIG).")
            return
        old = self.model.state
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
        self.window.tools._execute(enlace.AttrEditCommand(state.key, fid, field, text))
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
        for e in ctrl._selection_entities():
            tag = enlace.feat_tag(e)
            if tag is not None and tag.key == key:
                out.add(tag.fid)
        return out

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
            sm = self.table.selectionModel()
            sm.clearSelection()
            first = None
            for i, row in enumerate(state.rows):
                if row.fid in fids:
                    idx = self.model.index(i, 0)
                    sm.select(idx, QItemSelectionModel.SelectionFlag.Select
                              | QItemSelectionModel.SelectionFlag.Rows)
                    if first is None:
                        first = idx
            if first is not None:
                self.table.scrollTo(first)
            self.status.setText(state.summary(fids))
        finally:
            self._syncing = False

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
        window.tools.changed.disconnect(panel.sync_from_drawing)
    except Exception:
        pass
    puente.register_table(None)
    window.removeDockWidget(dock)
    dock.deleteLater()
