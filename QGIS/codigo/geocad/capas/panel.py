# -*- coding: utf-8 -*-
"""Panel Capas: el administrador de capas de IngeCAD 0.7.0 en QGIS (3.60.0).

Fernando, 01/11/2026: «reemplaces por completo el panel administrador de
capas de QGIS (Yaguá Capas) por el de IngeCAD y que adoptes todos sus
comportamientos». Copiado de views/layers_panel.py de IngeCAD 0.7.0, con sus
textos en español; los cambios van por el controlador de capas CAD (CAPAP
los deshace, como antes).

Columnas: Estado, Nombre, Encendida/Apagada, Inut, Bloq, Color, Tipo de
línea, Grosor de línea, Imprimir, Descripción. Arriba: nueva / eliminar /
establecer actual / nuevo filtro de grupo y Buscar capa. Doble clic en una
fila la hace actual; en el nombre, lo cambia. Un clic en la bombilla, el sol,
el candado o la impresora lo cambia; en el color, el tipo o el grosor, los
elige. Clic derecho en el encabezado: qué columnas se ven y Optimizar.

Encima de la tabla, cuando la capa tiene alguno, los filtros de grupo: un
clic muestra sus capas, clic derecho las activa, inutiliza o bloquea de una
vez y crea, cambia el nombre o elimina un grupo. Las capas entran a un grupo
arrastradas sobre él o desde su clic derecho.

Diferencia con IngeCAD: las capas CAD son las de la capa QGIS activa (el
título lo dice) y los filtros de propiedades de AutoCAD no existen acá.
"""
import fnmatch

from qgis.PyQt.QtCore import QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QCursor, QFont, QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QDockWidget, QHBoxLayout, QHeaderView, QLineEdit, QMenu,
    QSplitter, QStyle, QTableWidget, QTableWidgetItem, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import filtros
from .aci import ACI_RGB, color_hex
from .compat import accepted_code, enum, exec_dialog, exec_menu, qt
from .dialogs import ColorDialog, LinetypeDialog
from .icons import color_swatch, icon
from .linetypes import LINEWEIGHTS, LW_DEFAULT, lineweight_text

TITLE = 'Yaguá Capas'         # «Capas» a secas es el panel de QGIS (3.60.2)
(C_STATUS, C_NAME, C_ON, C_FRZ, C_LCK, C_COLOR, C_LT, C_LW, C_PLOT, C_DESC) = range(10)
ROLE = qt('ItemDataRole', 'UserRole')
STATE_ROLE = ROLE + 1           # el estado de la celda (encendida, reutilizada, desbloqueada, imprime)
ALL_LAYERS, USED_LAYERS = -1, -2
NAME_WIDTH = 150
HIDEABLE = (C_STATUS, C_ON, C_FRZ, C_LCK, C_COLOR, C_LT, C_LW, C_PLOT, C_DESC)
DEFAULT_HIDDEN = str(C_DESC)    # Descripción oculta hasta que se pida (IngeCAD)
AUTO_SIZED = (C_STATUS, C_ON, C_FRZ, C_LCK, C_COLOR, C_LT, C_LW, C_PLOT)
ICON_COLS = (C_STATUS, C_ON, C_FRZ, C_LCK, C_PLOT)
ICON_WIDTH = 28                 # como en IngeCAD; el encabezado de QGIS pedía 40 (3.60.5)


def lw_label(lw):
    """El grosor como lo escribe IngeCAD en español («Por defecto», no «Predeterminado»)."""
    return 'Por defecto' if lw is None or lw < 0 else lineweight_text(lw)

# Medidas compactas de IngeCAD, con los colores del tema de QGIS (Fernando, 01/11/2026:
# «del color de QGIS y no del color de IngeCAD»)
PANEL_STYLE = """
#CadLayersPanel QTableWidget { font-size: 11px; }
#CadLayersPanel QHeaderView::section { padding: 1px 3px; font-size: 11px; border: none;
    border-right: 1px solid palette(midlight); }
#CadLayersPanel QToolButton { border: none; padding: 2px 5px; font-size: 11px; }
#CadLayersPanel QTreeWidget { font-size: 11px; }
#CadLayersPanel QLineEdit { font-size: 11px; padding: 1px 4px; }
"""


def aci_of(color):
    """El número ACI del color de la capa (None si es color verdadero)."""
    aci = color.get('aci')
    if aci:
        return int(aci)
    rgb = (color.get('rgb') or '').lower()
    for i, v in ACI_RGB.items():
        if '#%02x%02x%02x' % v == rgb:
            return i
    return None


def color_text(color):
    """Lo que muestra la columna Color: el número ACI, o R,G,B."""
    aci = aci_of(color)
    if aci:
        return str(aci)
    h = (color.get('rgb') or '#000000').lstrip('#')
    return '%d,%d,%d' % tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def echo(ctrl, text):
    """Los avisos van a la línea de comandos, como en IngeCAD (sin Dibujo, a la barra)."""
    try:
        from qgis.utils import plugins
        mgr = getattr(plugins.get('Dibujo_CAD'), 'mgr', None)
        if mgr is not None:
            mgr.cmdline.echo(text)
            return
    except Exception:  # noqa: BLE001
        pass
    ctrl.msg(text)


class _FilterTree(QTreeWidget):
    """El árbol de filtros: las capas arrastradas desde la tabla entran al grupo."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def _group_at(self, event):
        if event.source() is not self.panel.table:
            return None
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        return self.panel._path_of(self.itemAt(pos))

    def dragEnterEvent(self, event):
        if event.source() is self.panel.table:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._group_at(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._group_at(event)
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.panel.group_layers(path, self.panel.selected_layers(), True)


class LayersPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setObjectName('CadLayersPanel')
        self.setStyleSheet(PANEL_STYLE)
        self._loading = False
        self._rows = []
        self._user_sized = set()
        self._auto_sizing = False

        self.table = QTableWidget(0, 10, self)
        heads = ((C_STATUS, '✓', 'Estado', None), (C_NAME, 'Nombre', 'Nombre', None),
                 (C_ON, '', 'Encendida/Apagada', 'bulb_on'), (C_FRZ, '', 'Inut', 'thaw'),
                 (C_LCK, '', 'Bloq', 'lock_open'), (C_COLOR, '■', 'Color', None),
                 # títulos cortos: en español el título manda el ancho de la columna
                 # («Tipo de línea» contra «Continuous»); el nombre entero, en la ayuda (3.60.5)
                 (C_LT, 'Tipo', 'Tipo de línea', None),
                 (C_LW, 'Grosor', 'Grosor de línea', None),
                 (C_PLOT, '', 'Imprimir', 'plot'), (C_DESC, 'Descripción', 'Descripción', None))
        for col, text, tip, ico in heads:
            item = QTableWidgetItem(text)
            item.setToolTip(tip)
            item.setTextAlignment(qt('AlignmentFlag', 'AlignCenter'))
            if ico:
                item.setIcon(icon(ico))
            self.table.setHorizontalHeaderItem(col, item)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(enum(QAbstractItemView, 'SelectionBehavior', 'SelectRows'))
        self.table.setEditTriggers(enum(QAbstractItemView, 'EditTrigger', 'DoubleClicked'))
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(14, 14))
        # letra y filas de IngeCAD (11 px, filas de 20): con la letra general de QGIS (11 pt)
        # las filas salían de 30 y el encabezado de 36 (3.60.5)
        chica = QFont(self.table.font())
        chica.setPixelSize(11)
        self.table.setFont(chica)
        self.table.horizontalHeader().setFont(chica)
        self.table.horizontalHeader().setFixedHeight(24)
        self.table.verticalHeader().setMinimumSectionSize(18)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.setTextElideMode(qt('TextElideMode', 'ElideRight'))
        self.table.setMinimumHeight(48)      # poca altura mínima: no agranda la ventana (3.60.4)

        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(16)
        interactive = enum(QHeaderView, 'ResizeMode', 'Interactive')
        for col in AUTO_SIZED + (C_NAME,):
            header.setSectionResizeMode(col, interactive)
        header.setSectionResizeMode(C_DESC, enum(QHeaderView, 'ResizeMode', 'Stretch'))
        self.table.setColumnWidth(C_NAME, self._remembered_name_width())
        header.sectionResized.connect(self._remember_width)
        header.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
        header.customContextMenuRequested.connect(self._header_menu)
        self._restore_hidden_columns()

        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.cellClicked.connect(self._on_cell_clicked)

        self.btn_new = self._tool_button('＋', 'Nueva capa', self.new_layer)
        self.btn_del = self._tool_button('🗑', 'Eliminar capa', self.delete_layer)
        self.btn_cur = self._tool_button('✓', 'Establecer actual', self.set_current_selected)
        self.btn_group = self._tool_button('', 'Nuevo filtro de grupo', lambda: self.new_group_filter())
        self.btn_group.setIcon(self.style().standardIcon(
            enum(QStyle, 'StandardPixmap', 'SP_FileDialogNewFolder')))
        buttons = QHBoxLayout()
        buttons.setContentsMargins(2, 2, 2, 0)
        buttons.setSpacing(1)
        for b in (self.btn_new, self.btn_del, self.btn_cur, self.btn_group):
            buttons.addWidget(b)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText('Buscar capa')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self.refresh())
        buttons.addWidget(self.search, 1)

        self.filters = _FilterTree(self)
        self.filters.setHeaderHidden(True)
        self.filters.setMinimumHeight(24)
        self.filters.setIndentation(12)
        self.filters.setEditTriggers(enum(QAbstractItemView, 'EditTrigger', 'EditKeyPressed')
                                     | enum(QAbstractItemView, 'EditTrigger', 'SelectedClicked'))
        self.filters.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
        self.filters.customContextMenuRequested.connect(self._filter_menu)
        self.filters.currentItemChanged.connect(self._filter_chosen)
        self.filters.itemChanged.connect(self._filter_renamed)
        self._filter_paths = []
        self._filter_signature = None
        self._chosen_path = None
        self._filters_of = None
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(enum(QAbstractItemView, 'DragDropMode', 'DragOnly'))
        self.table.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
        self.table.customContextMenuRequested.connect(self._table_menu)
        splitter = QSplitter(qt('Orientation', 'Vertical'), self)
        splitter.addWidget(self.filters)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([90, 400])
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addLayout(buttons)
        layout.addWidget(splitter)

        ctrl.changed.connect(self.refresh)
        ctrl.attachedChanged.connect(self.refresh)
        self.refresh()

    def _tool_button(self, text, tip, slot):
        btn = QToolButton(self)
        btn.setText(text)
        btn.setToolTip(tip)
        btn.clicked.connect(lambda *_: slot())
        return btn

    # ------------------------------------------------------------ columnas
    def _remembered_name_width(self):
        try:
            width = int(self.ctrl.setting('panel/name_width', NAME_WIDTH, int))
        except (TypeError, ValueError):
            width = NAME_WIDTH
        return max(40, width)

    def _remember_width(self, index, _old, new):
        if self._auto_sizing or new <= 0:
            return
        self._user_sized.add(index)
        if index == C_NAME:
            self.ctrl.set_setting('panel/name_width', int(new))

    def _size_columns(self):
        self._auto_sizing = True
        try:
            for col in AUTO_SIZED:
                if col not in self._user_sized and not self.table.isColumnHidden(col):
                    if col in ICON_COLS:
                        self.table.setColumnWidth(col, ICON_WIDTH)
                    else:
                        self.table.resizeColumnToContents(col)
        finally:
            self._auto_sizing = False

    def _restore_hidden_columns(self):
        stored = self.ctrl.setting('panel/hidden_columns', DEFAULT_HIDDEN, str)
        hidden = {int(c) for c in str(stored or '').split(',') if c.strip().isdigit()}
        for col in HIDEABLE:
            self.table.setColumnHidden(col, col in hidden)

    def _save_hidden_columns(self):
        hidden = [str(c) for c in HIDEABLE if self.table.isColumnHidden(c)]
        self.ctrl.set_setting('panel/hidden_columns', ','.join(hidden))

    def _header_menu(self, pos):
        menu = QMenu(self)
        for col in HIDEABLE:
            item = self.table.horizontalHeaderItem(col)
            action = menu.addAction(item.toolTip() if item else str(col))
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(col))
            action.triggered.connect(lambda checked, c=col: self._toggle_column(c, checked))
        menu.addSeparator()
        menu.addAction('Optimizar todas las columnas').triggered.connect(
            lambda *_: self._optimize_columns())
        exec_menu(menu, self.table.horizontalHeader().mapToGlobal(pos))

    def _toggle_column(self, col, visible):
        self.table.setColumnHidden(col, not visible)
        self._save_hidden_columns()

    def _optimize_columns(self):
        self.table.resizeColumnToContents(C_NAME)
        self.ctrl.set_setting('panel/name_width', int(self.table.columnWidth(C_NAME)))

    # ------------------------------------------------------------ datos
    def refresh(self, *args):
        if self._loading:
            return
        active = self.ctrl.active
        for w in (self.btn_new, self.btn_del, self.btn_cur, self.btn_group, self.search):
            w.setEnabled(active)
        title = TITLE if not active else '%s · %s' % (TITLE, self.ctrl.layer.name())
        dock = self.parent()
        if isinstance(dock, QDockWidget):
            dock.setWindowTitle(title)
        self._loading = True
        try:
            if not active:
                self.table.setRowCount(0)
                self._fill_filters([])
                return
            used = self.ctrl.used_names()
            self._fill_filters(self.ctrl.filters())
            names = self.ctrl.names()
            shown = self._filter_names(used)
            if shown is not None:
                names = [n for n in names if n in shown]
            needle = self.search.text().strip().lower()
            if needle:
                pattern = needle if any(c in needle for c in '*?') else '*%s*' % needle
                names = [n for n in names if fnmatch.fnmatchcase(n.lower(), pattern)]
            self._rows = list(names)
            self.table.setRowCount(len(names))
            for row, name in enumerate(names):
                self._fill_row(row, self.ctrl.find(name, True), name in used)
        finally:
            self._loading = False
        self._size_columns()
        self.changed.emit()

    def _fill_row(self, row, lay, in_use):
        enabled = qt('ItemFlag', 'ItemIsEnabled')
        selectable = qt('ItemFlag', 'ItemIsSelectable')
        is_current = lay['name'] == self.ctrl.current
        cur = QTableWidgetItem('✓' if is_current else ('▪' if in_use else ''))
        cur.setToolTip('Capa actual' if is_current else ('Capa en uso' if in_use else 'Capa vacía'))
        cur.setTextAlignment(qt('AlignmentFlag', 'AlignCenter'))
        cur.setFlags(enabled)
        self.table.setItem(row, C_STATUS, cur)

        name = QTableWidgetItem(lay['name'])
        if lay['name'] == '0':
            name.setFlags(enabled | selectable)       # la capa 0 no cambia de nombre
        if is_current:
            bold = QFont(self.table.font())
            bold.setBold(True)
            name.setFont(bold)
        self.table.setItem(row, C_NAME, name)

        for col, active in ((C_ON, lay['on']), (C_FRZ, not lay['frozen']),
                            (C_LCK, not lay['locked']), (C_PLOT, lay.get('plot', True))):
            item = self._state_item(col, active)
            item.setFlags(enabled | selectable)
            self.table.setItem(row, col, item)

        swatch = QTableWidgetItem(color_text(lay['color']))
        swatch.setTextAlignment(qt('AlignmentFlag', 'AlignCenter'))
        swatch.setIcon(QIcon(color_swatch(color_hex(lay['color']), 12, 12)))
        aci = aci_of(lay['color'])
        swatch.setToolTip('Color ACI %d' % aci if aci else 'Color verdadero %s' % color_text(lay['color']))
        swatch.setFlags(enabled | selectable)
        self.table.setItem(row, C_COLOR, swatch)

        lt = QTableWidgetItem(lay['linetype'])
        lt.setFlags(enabled | selectable)
        self.table.setItem(row, C_LT, lt)

        lw = QTableWidgetItem(lw_label(lay['lineweight']))
        lw.setFlags(enabled | selectable)
        self.table.setItem(row, C_LW, lw)

        self.table.setItem(row, C_DESC, QTableWidgetItem(lay.get('description', '')))

    @staticmethod
    def _state_item(col, active):
        item = QTableWidgetItem()
        if col == C_ON:
            item.setIcon(icon('bulb_on' if active else 'bulb_off'))
            item.setToolTip('Enc' if active else 'Des')
        elif col == C_FRZ:
            item.setIcon(icon('thaw' if active else 'freeze'))
            item.setToolTip('Reutilizada' if active else 'Inutilizada')
        elif col == C_LCK:
            item.setIcon(icon('lock_open' if active else 'lock_closed'))
            item.setToolTip('Desbloqueada' if active else 'Bloqueada')
        else:
            item.setIcon(icon('plot' if active else 'noplot'))
            item.setToolTip('Imprimir' if active else 'No imprimir')
        item.setData(STATE_ROLE, active)
        return item

    def _row_layer(self, row):
        if 0 <= row < len(self._rows):
            return self._rows[row]
        item = self.table.item(row, C_NAME)
        return item.text() if item else ''

    # ------------------------------------------------------------ filtros de grupo
    def _fill_filters(self, groups):
        """Se rearma el árbol sólo si cambiaron los filtros; el elegido sigue elegido."""
        rows = filtros.rows(groups)
        self._filter_paths = [p for p, _d, _f in rows]
        layer_id = self.ctrl.layer.id() if self.ctrl.active else None
        signature = (layer_id, tuple(self._filter_paths))
        if signature == self._filter_signature:
            self.filters.setVisible(bool(rows))
            return
        self._filter_signature = signature
        if self._filters_of != layer_id:
            self._filters_of = layer_id
            self._chosen_path = None             # otra capa QGIS: vuelve a Todas
        chosen = self._chosen_path
        self.filters.blockSignals(True)
        self.filters.clear()
        root = QTreeWidgetItem(self.filters, ['Todas'])
        root.setData(0, ROLE, ALL_LAYERS)
        used = QTreeWidgetItem(root, ['Todas las capas utilizadas'])
        used.setData(0, ROLE, USED_LAYERS)
        current = {None: root, 'used': used}.get(chosen, root)
        parents = [root]
        for index, (path, depth, f) in enumerate(rows):
            del parents[depth + 1:]
            item = QTreeWidgetItem(parents[-1], [f['name']])
            item.setData(0, ROLE, index)
            item.setFlags(item.flags() | qt('ItemFlag', 'ItemIsEditable')
                          | qt('ItemFlag', 'ItemIsDropEnabled'))
            if path == chosen:
                current = item
            parents.append(item)
        self.filters.expandAll()
        self.filters.setCurrentItem(current)
        self.filters.blockSignals(False)
        self._remember_chosen()
        self.filters.setVisible(bool(rows))

    def _path_of(self, item):
        index = item.data(0, ROLE) if item is not None else None
        if isinstance(index, int) and 0 <= index < len(self._filter_paths):
            return self._filter_paths[index]
        return None

    def _chosen_kind(self):
        item = self.filters.currentItem()
        if item is None or not self._filter_paths:
            return ALL_LAYERS
        return item.data(0, ROLE)

    def _remember_chosen(self):
        path = self._path_of(self.filters.currentItem())
        if path is not None:
            self._chosen_path = path
        elif self._chosen_kind() == USED_LAYERS:
            self._chosen_path = 'used'
        else:
            self._chosen_path = None

    def _filter_names(self, used):
        """Las capas del filtro elegido; None para todas."""
        kind = self._chosen_kind()
        if kind == ALL_LAYERS:
            return None
        if kind == USED_LAYERS:
            return set(used)
        f = filtros.find(self.ctrl.filters(), self._path_of(self.filters.currentItem()))
        return set(f['layers']) if f else None

    def _filter_chosen(self, *args):
        self._remember_chosen()
        self.refresh()

    def _filter_menu(self, pos):
        item = self.filters.itemAt(pos)
        if item is None or not self.ctrl.active:
            return
        self.filters.setCurrentItem(item)
        path = self._path_of(item)
        menu = QMenu(self)
        if item.data(0, ROLE) == ALL_LAYERS or path is not None:
            menu.addAction('Nuevo filtro de grupo').triggered.connect(
                lambda *_: self.new_group_filter())
        if path is not None:
            menu.addAction('Cambiar nombre').triggered.connect(lambda *_: self.filters.editItem(item))
            menu.addAction('Eliminar').triggered.connect(lambda *_: self.delete_filter())
        menu.addSeparator()
        for label, prop, value in (('Activar capas', 'on', True), ('Desactivar capas', 'on', False),
                                   ('Reutilizar capas', 'frozen', False),
                                   ('Inutilizar capas', 'frozen', True),
                                   ('Bloquear capas', 'locked', True),
                                   ('Desbloquear capas', 'locked', False)):
            if prop == 'locked' and value:
                menu.addSeparator()
            menu.addAction(label).triggered.connect(
                lambda *_, p=prop, v=value: self.set_filter_state(p, v))
        exec_menu(menu, self.filters.viewport().mapToGlobal(pos))

    def set_filter_state(self, prop, value):
        """Todas las capas del filtro elegido en un estado, en un solo paso."""
        shown = self._filter_names(self.ctrl.used_names())
        names = [n for n in self.ctrl.names() if shown is None or n in shown]
        if not self.ctrl.set_names_state(names, prop, value):
            echo(self.ctrl, 'No hay nada que cambiar.')

    def new_group_filter(self):
        """Un grupo nuevo dentro del grupo elegido (arriba desde Todas), con el
        nombre abierto para escribir, como en AutoCAD."""
        if not self.ctrl.active:
            return
        path = self._path_of(self.filters.currentItem())
        new = self.ctrl.new_group(path or ())
        if new is None:
            return
        self._chosen_path = new
        self._filter_signature = None
        self.refresh()
        item = self.filters.currentItem()
        if item is not None and self._path_of(item) is not None:
            self.filters.editItem(item)

    def delete_filter(self):
        path = self._path_of(self.filters.currentItem())
        if path is None:
            return
        self._chosen_path = None
        self.ctrl.delete_group(path)

    def _filter_renamed(self, item, _column):
        path = self._path_of(item)
        if path is None or self._loading:
            return
        new = item.text(0).strip()
        if new == path[-1]:
            return
        err = self.ctrl.rename_group(path, new) if new else 'vacío'
        if err:
            if new:
                echo(self.ctrl, 'Ya existe un filtro llamado %s.' % new)
            self.filters.blockSignals(True)
            item.setText(0, path[-1])
            self.filters.blockSignals(False)
            return
        self._chosen_path = path[:-1] + (new,)
        self._filter_signature = None
        self.refresh()

    def selected_layers(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [self._row_layer(r) for r in rows if self._row_layer(r)]

    def group_layers(self, path, names, add):
        if path is None or not names:
            return
        self.ctrl.group_layers(path, names, add)

    def _table_menu(self, pos):
        if not self.ctrl.active:
            return
        names = self.selected_layers()
        if not names:
            return
        menu = QMenu(self)
        groups = filtros.rows(self.ctrl.filters())
        if groups:
            add = menu.addMenu('Añadir al grupo')
            for path, depth, f in groups:
                add.addAction('    ' * depth + f['name']).triggered.connect(
                    lambda *_, p=path: self.group_layers(p, names, True))
        menu.addAction('Nuevo grupo con estas capas').triggered.connect(
            lambda *_: self._new_group_with(names))
        chosen = self._path_of(self.filters.currentItem())
        if chosen is not None:
            menu.addAction('Quitar del grupo').triggered.connect(
                lambda *_: self.group_layers(chosen, names, False))
        exec_menu(menu, self.table.viewport().mapToGlobal(pos))

    def _new_group_with(self, names):
        new = self.ctrl.new_group((), names)
        if new is None:
            return
        self._chosen_path = new
        self._filter_signature = None
        self.refresh()

    # ------------------------------------------------------------ cambios
    def new_layer(self):
        """Capa nueva con las propiedades de la elegida y el nombre abierto para escribir."""
        if not self.ctrl.active:
            return
        row = self.table.currentRow()
        base = self._row_layer(row) if row >= 0 else None
        name = self.ctrl.add_layer(based_on=base)
        if name:
            self._select_and_edit(name)

    def _select_and_edit(self, name):
        if name not in self._rows:
            self.search.clear()
            self.filters.setCurrentItem(self.filters.topLevelItem(0))
        if name not in self._rows:
            return
        row = self._rows.index(name)
        self.table.setCurrentCell(row, C_NAME)
        item = self.table.item(row, C_NAME)
        if item is not None:
            self.table.scrollToItem(item)
            self.table.editItem(item)

    def delete_layer(self):
        row = self.table.currentRow()
        if row < 0 or not self.ctrl.active:
            return
        name = self._row_layer(row)
        if name in ('0', 'Defpoints'):
            echo(self.ctrl, 'La capa %s no se puede suprimir.' % name)
            return
        if name == self.ctrl.current:
            echo(self.ctrl, 'No se puede eliminar la capa actual.')
            return
        if name in self.ctrl.used_names():
            echo(self.ctrl, 'La capa %s está en uso.' % name)
            return
        self.ctrl.delete_layers([name])

    def set_current_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.make_current(self._row_layer(row))

    def make_current(self, name):
        self.ctrl.set_current(name)

    def _on_double_click(self, row, col):
        if col != C_NAME:
            self.make_current(self._row_layer(row))

    def _on_cell_clicked(self, row, col):
        if self._loading or not self.ctrl.active:
            return
        name = self._row_layer(row)
        lay = self.ctrl.find(name, True)
        if lay is None:
            return
        if col in (C_ON, C_FRZ, C_LCK, C_PLOT):
            active = bool(self.table.item(row, col).data(STATE_ROLE))
            prop = {C_ON: 'on', C_FRZ: 'frozen', C_LCK: 'locked', C_PLOT: 'plot'}[col]
            # encendida -> apagada, reutilizada -> inutilizada, desbloqueada -> bloqueada
            value = not active if prop in ('on', 'plot') else active
            self.ctrl.set_props([name], **{prop: value})
        elif col == C_COLOR:
            dlg = ColorDialog(self, lay['color'])
            if exec_dialog(dlg) == accepted_code() and dlg.color != lay['color']:
                self.ctrl.set_props([name], color=dlg.color)
        elif col == C_LT:
            dlg = LinetypeDialog(self, lay['linetype'])
            if exec_dialog(dlg) == accepted_code() and dlg.value() and dlg.value() != lay['linetype']:
                self.ctrl.set_props([name], linetype=dlg.value())
        elif col == C_LW:
            self._pick_lineweight(name)

    def _pick_lineweight(self, name):
        menu = QMenu(self)
        for lw in [LW_DEFAULT] + LINEWEIGHTS:
            menu.addAction(lw_label(lw)).triggered.connect(
                lambda *_, v=lw: self.ctrl.set_props([name], lineweight=v))
        exec_menu(menu, QCursor.pos())

    def _on_cell_changed(self, row, col):
        if self._loading or not self.ctrl.active:
            return
        name = self._row_layer(row)
        if not name or col not in (C_NAME, C_DESC):
            return
        # se aplica después: la tabla se rearma y la celda editada se destruye
        text = self.table.item(row, col).text()
        QTimer.singleShot(0, lambda: self._apply_edit(name, col, text))

    def _apply_edit(self, name, col, text):
        if col == C_DESC:
            self.ctrl.set_props([name], description=text)
            return
        new = text.strip()
        if not new or new == name:
            self.refresh()
            return
        if self.ctrl.find(new) is not None:
            echo(self.ctrl, 'La capa %s ya existe.' % new)
            self.refresh()
            return
        if not self.ctrl.rename(name, new):
            self.refresh()


class LayersDock(QDockWidget):
    """El panel en un panel acoplable de QGIS (en IngeCAD es una pestaña del costado)."""

    def __init__(self, ctrl, parent=None):
        super().__init__(TITLE, parent)
        # nombre nuevo en la 3.60.4: el viejo traía guardada la pestaña a la izquierda
        self.setObjectName('YaguaCapasDock')
        self.ctrl = ctrl
        self.panel = LayersPanel(ctrl, self)
        self.setWidget(self.panel)
        self.panel.refresh()

    def closeEvent(self, event):
        """Cerrado con la ×: al volver a abrir QGIS sigue cerrado (3.60.2)."""
        self.ctrl.set_setting('panel/visible', False)
        super().closeEvent(event)
