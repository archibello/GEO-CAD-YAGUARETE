# -*- coding: utf-8 -*-
"""Paleta 'Administrador de propiedades de capas' al estilo de AutoCAD."""

from qgis.PyQt.QtCore import QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QFont, QIcon, QKeySequence
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QDockWidget, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
    QMessageBox, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolBar, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .aci import color_display_name
from .compat import QAction, QActionGroup, QShortcut, enum, exec_dialog, exec_menu, qt, accepted_code
from .dialogs import (ColorDialog, LayerStatesDialog, LinetypeDialog,
                      LineweightDialog, TransparencyDialog)
from .icons import color_swatch, icon, lineweight_sample
from .linetypes import LWDEFAULT_MM, lineweight_text
from .theme import palette, stylesheet

(C_STATUS, C_NAME, C_ON, C_FRZ, C_LCK, C_PLOT, C_COLOR, C_LT, C_LW, C_TR, C_DESC) = range(11)
HEADERS = ['Estado', 'Nombre', 'Act.', 'Inutilizar', 'Bloquear', 'Trazar', 'Color',
           'Tipo de línea', 'Grosor de línea', 'Transparencia', 'Descripción']
TOGGLE_COLS = {C_ON: 'on', C_FRZ: 'frozen', C_LCK: 'locked', C_PLOT: 'plot'}
ACTION_COLS = set(TOGGLE_COLS) | {C_COLOR, C_LT, C_LW, C_TR}
FILTERS = [('all', 'Todas', 'filter'), ('used', 'Todas las capas utilizadas', 'filter_used'),
           ('unused', 'Capas no utilizadas', 'filter_unused')]
ROLE = qt('ItemDataRole', 'UserRole')


def _add(menu, ico, text, slot=None):
    """addAction compatible con Qt5/Qt6."""
    a = menu.addAction(text)
    if ico is not None:
        a.setIcon(ico)
    if slot is not None:
        a.triggered.connect(lambda *_: slot())
    return a


class CenterIconDelegate(QStyledItemDelegate):
    """Dibuja el icono centrado en la celda (columnas de estado, como AutoCAD)."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        ico = QIcon(opt.icon)
        opt.icon = QIcon()
        opt.text = ''
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(enum(QStyle, 'ControlElement', 'CE_ItemViewItem'), opt, painter, widget)
        if not ico.isNull():
            ico.paint(painter, option.rect, qt('AlignmentFlag', 'AlignCenter'))


class CadGrid(QTableWidget):
    """Tabla que conserva la selección múltiple al pulsar un icono (como AutoCAD)."""
    cellAction = pyqtSignal(int, int)

    def mousePressEvent(self, ev):
        pos = ev.position().toPoint() if hasattr(ev, 'position') else ev.pos()
        idx = self.indexAt(pos)
        left = ev.button() == qt('MouseButton', 'LeftButton')
        no_mod = ev.modifiers() == qt('KeyboardModifier', 'NoModifier')
        if left and no_mod and idx.isValid() and idx.column() in ACTION_COLS:
            if self.selectionModel().isRowSelected(idx.row(), idx.parent()):
                self.setCurrentCell(idx.row(), idx.column(),
                                    enum(self.selectionModel().__class__, 'SelectionFlag', 'NoUpdate'))
            else:
                super().mousePressEvent(ev)
            r, c = idx.row(), idx.column()
            QTimer.singleShot(0, lambda: self.cellAction.emit(r, c))
            return
        super().mousePressEvent(ev)


class LayerManagerDock(QDockWidget):
    def __init__(self, iface, ctrl, parent=None):
        super().__init__('Administrador de propiedades de capas', parent)
        self.setObjectName('CadLayerManagerDock')
        self.iface = iface
        self.ctrl = ctrl
        self._populating = False
        self.filter_key = 'all'
        self.theme = ctrl.setting('theme', 'dark', str)

        root = QWidget()
        root.setObjectName('CadLayerRoot')
        self.setWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(6, 6, 6, 0)
        v.setSpacing(4)

        # ---- cabecera: capa actual + búsqueda
        top = QHBoxLayout()
        self.lbl_current = QLabel()
        self.lbl_current.setObjectName('CadTitle')
        self.lbl_source = QLabel()
        self.lbl_source.setObjectName('CadMuted')
        top.addWidget(self.lbl_current)
        top.addWidget(self.lbl_source)
        top.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName('CadSearch')
        self.search.setPlaceholderText('Buscar capa')
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(200)
        self.search.setToolTip('Filtra por nombre. Admite comodines * y ? y varias búsquedas separadas por comas.')
        try:
            self.search.addAction(icon('search'), enum(QLineEdit, 'ActionPosition', 'TrailingPosition'))
        except Exception:
            pass
        self.search.textChanged.connect(self.populate)
        top.addWidget(self.search)
        v.addLayout(top)

        # ---- barra de herramientas de la paleta
        tb = QToolBar()
        tb.setObjectName('CadPaletteBar')
        tb.setIconSize(QSize(20, 20))
        self.toolbar = tb
        self.a_states = self._act(tb, 'states', 'Administrador de estados de capa (LAYERSTATE)', self.open_states)
        tb.addSeparator()
        self.a_new = self._act(tb, 'new_layer', 'Nueva capa (Alt+N)', self.new_layer)
        self.a_del = self._act(tb, 'del_layer', 'Suprimir capa (Alt+D)', self.delete_layers)
        self.a_cur = self._act(tb, 'set_current', 'Definir actual (Alt+C)', self.set_current_selected)
        tb.addSeparator()
        self._act(tb, 'move_top', 'Traer al frente (orden de dibujo)', lambda: self._order(top=True))
        self._act(tb, 'move_up', 'Subir en el orden de dibujo', lambda: self._order(delta=-1))
        self._act(tb, 'move_down', 'Bajar en el orden de dibujo', lambda: self._order(delta=1))
        self._act(tb, 'move_bottom', 'Enviar al fondo (orden de dibujo)', lambda: self._order(top=False))
        tb.addSeparator()
        self._act(tb, 'select_objs', 'Seleccionar los objetos de las capas seleccionadas', self.select_objects)
        self._act(tb, 'assign', 'Mover los objetos seleccionados en el mapa a esta capa', self.assign_selection)
        spacer = QWidget()
        spacer.setSizePolicy(enum(QSizePolicy, 'Policy', 'Expanding'), enum(QSizePolicy, 'Policy', 'Preferred'))
        tb.addWidget(spacer)
        self._act(tb, 'refresh', 'Actualizar', self.ctrl.refresh)
        self.btn_settings = QToolButton()
        self.btn_settings.setIcon(icon('settings'))
        self.btn_settings.setToolTip('Parámetros')
        self.btn_settings.setPopupMode(enum(QToolButton, 'ToolButtonPopupMode', 'InstantPopup'))
        self.btn_settings.setMenu(self._settings_menu())
        tb.addWidget(self.btn_settings)
        v.addWidget(tb)

        # ---- filtros + tabla
        split = QSplitter(qt('Orientation', 'Horizontal'))
        self.filters = QTreeWidget()
        self.filters.setObjectName('CadFilters')
        self.filters.setHeaderLabels(['Filtros'])
        self.filters.setRootIsDecorated(True)
        root_item = None
        for key, label, ico in FILTERS:
            it = QTreeWidgetItem([label])
            it.setIcon(0, icon(ico))
            it.setData(0, ROLE, key)
            if root_item is None:
                self.filters.addTopLevelItem(it)
                root_item = it
            else:
                root_item.addChild(it)
        self.filters.expandAll()
        self.filters.setCurrentItem(root_item)
        self.filters.currentItemChanged.connect(self._filter_changed)
        split.addWidget(self.filters)

        self.grid = CadGrid(0, len(HEADERS))
        self.grid.setObjectName('CadGrid')
        self.grid.setHorizontalHeaderLabels(HEADERS)
        self.grid.verticalHeader().setVisible(False)
        self.grid.verticalHeader().setDefaultSectionSize(21)
        self.grid.setShowGrid(False)
        self.grid.setAlternatingRowColors(True)
        self.grid.setWordWrap(False)
        self.grid.setSelectionBehavior(enum(QAbstractItemView, 'SelectionBehavior', 'SelectRows'))
        self.grid.setSelectionMode(enum(QAbstractItemView, 'SelectionMode', 'ExtendedSelection'))
        self.grid.setEditTriggers(enum(QAbstractItemView, 'EditTrigger', 'NoEditTriggers'))
        self.grid.setIconSize(QSize(16, 16))
        self.grid.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
        self.grid.customContextMenuRequested.connect(self._context_menu)
        self.grid.cellAction.connect(self._cell_action)
        self.grid.cellDoubleClicked.connect(self._cell_double)
        self.grid.itemChanged.connect(self._item_changed)
        self._center = CenterIconDelegate(self.grid)
        for c in (C_STATUS, C_ON, C_FRZ, C_LCK, C_PLOT):
            self.grid.setItemDelegateForColumn(c, self._center)
        hh = self.grid.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setStretchLastSection(True)
        hh.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
        hh.customContextMenuRequested.connect(self._header_menu)
        hh.setSectionsMovable(True)
        hh.setDefaultAlignment(qt('AlignmentFlag', 'AlignLeft') | qt('AlignmentFlag', 'AlignVCenter'))
        widths = {C_STATUS: 46, C_NAME: 150, C_ON: 36, C_FRZ: 62, C_LCK: 62, C_PLOT: 50,
                  C_COLOR: 92, C_LT: 104, C_LW: 132, C_TR: 92}
        for c, w in widths.items():
            self.grid.setColumnWidth(c, w)
        for c in self._hidden_columns():
            self.grid.setColumnHidden(c, True)
        split.addWidget(self.grid)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([180, 900])
        v.addWidget(split, 1)

        # ---- barra de estado
        status = QFrame()
        status.setObjectName('CadStatus')
        sh = QHBoxLayout(status)
        sh.setContentsMargins(6, 3, 6, 3)
        self.chk_invert = QCheckBox('Invertir filtro')
        self.chk_invert.toggled.connect(self.populate)
        self.lbl_status = QLabel()
        sh.addWidget(self.chk_invert)
        sh.addSpacing(16)
        sh.addWidget(self.lbl_status, 1)
        v.addWidget(status)

        # ---- atajos de teclado
        ctx = qt('ShortcutContext', 'WidgetWithChildrenShortcut')
        for seq, fn in (('Alt+N', self.new_layer), ('Alt+D', self.delete_layers),
                        ('Alt+C', self.set_current_selected), ('F2', self.rename_selected),
                        ('Del', self.delete_layers), ('Ctrl+A', self.grid.selectAll)):
            sc = QShortcut(QKeySequence(seq), root)
            sc.setContext(ctx)
            sc.activated.connect(fn)

        ctrl.changed.connect(self.populate)
        ctrl.attachedChanged.connect(self.populate)
        self.apply_theme(self.theme)
        self.populate()

    # ------------------------------------------------------------ helpers UI
    def _act(self, tb, ico, tip, fn):
        a = QAction(icon(ico), tip, self)
        a.setToolTip(tip)
        a.triggered.connect(lambda *_: fn())
        tb.addAction(a)
        return a

    def _hidden_columns(self):
        raw = self.ctrl.setting('hidden_columns', '', str)
        return [int(x) for x in raw.split(',') if x.strip().isdigit()]

    def apply_theme(self, name):
        self.theme = name
        self.ctrl.set_setting('theme', name)
        self.widget().setStyleSheet(stylesheet(name))
        self.populate()

    def _settings_menu(self):
        m = QMenu(self)
        a_lw = m.addAction('Mostrar grosor de línea en pantalla (LWDISPLAY)')
        a_lw.setCheckable(True)
        m.aboutToShow.connect(lambda: a_lw.setChecked(self.ctrl.lwdisplay))
        a_lw.toggled.connect(lambda on: self.ctrl.lwdisplay != on and self.ctrl.set_global('lwdisplay', on))
        a_bw = m.addAction('Negro (0,0,0) se ve blanco sobre fondo oscuro, como el color 7')
        a_bw.setCheckable(True)
        m.aboutToShow.connect(lambda: a_bw.setChecked(self.ctrl.black_as_7))
        a_bw.toggled.connect(lambda on: self.ctrl.black_as_7 != on and self.ctrl.set_global('black_as_7', on))
        _add(m, None, 'Escala de tipo de línea (LTSCALE)...', self._ask_ltscale)
        _add(m, None, 'Atenuación de capas bloqueadas (LAYLOCKFADECTL)...', self._ask_lockfade)
        tm = m.addMenu('Tema')
        grp = QActionGroup(self)
        for key, label in (('dark', 'Oscuro'), ('light', 'Claro')):
            a = tm.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.theme == key)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.apply_theme(k))
        m.addSeparator()
        _add(m, icon('import'), 'Importar capas...', self.import_layers)
        _add(m, icon('export'), 'Exportar capas...', self.export_layers)
        m.addSeparator()
        _add(m, None, 'Guardar como plantilla para capas nuevas', self.ctrl.save_template)
        _add(m, None, 'Restablecer plantilla (solo capa 0)', lambda: (self.ctrl.set_setting('template', ''), self.ctrl.msg('Plantilla restablecida.')))
        return m

    def _ask_ltscale(self):
        v, ok = QInputDialog.getDouble(self, 'LTSCALE', 'Escala global de tipo de línea:',
                                       self.ctrl.ltscale, 0.01, 1000.0, 2)
        if ok:
            self.ctrl.set_global('ltscale', v)

    def _ask_lockfade(self):
        v, ok = QInputDialog.getInt(self, 'LAYLOCKFADECTL', 'Atenuación de capas bloqueadas (0-90 %):',
                                    self.ctrl.lockfade, 0, 90)
        if ok:
            self.ctrl.set_global('lockfade', v)

    # ------------------------------------------------------------ datos
    def selected_names(self):
        rows = sorted({i.row() for i in self.grid.selectedIndexes()})
        out = []
        for r in rows:
            it = self.grid.item(r, C_NAME)
            if it:
                out.append(it.data(ROLE))
        return out

    def _row_name(self, row):
        it = self.grid.item(row, C_NAME)
        return it.data(ROLE) if it else None

    def _targets(self, row):
        name = self._row_name(row)
        sel = self.selected_names()
        return sel if name in sel else [name]

    def _filter_changed(self, cur, prev):
        self.filter_key = cur.data(0, ROLE) if cur else 'all'
        self.populate()

    def _visible_names(self):
        names = self.ctrl.filter_names(self.search.text())
        if self.filter_key != 'all':
            used = self.ctrl.used_names()
            names = [n for n in names if (n in used) == (self.filter_key == 'used')]
        if self.chk_invert.isChecked():
            keep = set(names)
            names = [n for n in self.ctrl.names() if n not in keep]
        return names

    def populate(self, *args):
        if self._populating:
            return
        self._populating = True
        try:
            self._do_populate()
        finally:
            self._populating = False

    def _do_populate(self):
        ctrl = self.ctrl
        keep = set(self.selected_names())
        self.grid.setRowCount(0)
        active = ctrl.active
        self.widget().setEnabled(True)
        for w in (self.grid, self.toolbar, self.filters, self.search, self.chk_invert):
            w.setEnabled(active)
        if not active:
            self.lbl_current.setText('Capa actual: —')
            self.lbl_source.setText('')
            self.lbl_status.setText('Selecciona una capa vectorial (línea, polígono o punto) en el panel Capas.')
            return
        self.lbl_current.setText('Capa actual: %s' % ctrl.current)
        self.lbl_source.setText('  ·  %s' % ctrl.layer.name())
        used = ctrl.used_names()
        names = self._visible_names()
        fg = palette(self.theme)['text']
        bold = QFont(self.grid.font())
        bold.setBold(True)
        self.grid.setRowCount(len(names))
        for r, n in enumerate(names):
            lay = ctrl.find(n, True)
            is_cur = n == ctrl.current

            def mk(text='', ico=None, tip=None, editable=False):
                it = QTableWidgetItem(text)
                if ico is not None:
                    it.setIcon(ico if isinstance(ico, QIcon) else QIcon(ico))
                if tip:
                    it.setToolTip(tip)
                flags = it.flags()
                ed = qt('ItemFlag', 'ItemIsEditable')
                it.setFlags(flags | ed if editable else flags & ~ed)
                return it

            st = mk(ico=icon('current' if is_cur else ('layer_used' if n in used else 'layer_unused')),
                    tip='Capa actual' if is_cur else ('Capa en uso' if n in used else 'Capa sin objetos'))
            self.grid.setItem(r, C_STATUS, st)
            it = mk(n, editable=True, tip='Doble clic o F2 para cambiar el nombre')
            it.setData(ROLE, n)
            if is_cur:
                it.setFont(bold)
            self.grid.setItem(r, C_NAME, it)
            self.grid.setItem(r, C_ON, mk(ico=icon('bulb_on' if lay['on'] else 'bulb_off'),
                                          tip='Activada' if lay['on'] else 'Desactivada'))
            self.grid.setItem(r, C_FRZ, mk(ico=icon('freeze' if lay['frozen'] else 'thaw'),
                                           tip='Inutilizada' if lay['frozen'] else 'Reutilizada'))
            self.grid.setItem(r, C_LCK, mk(ico=icon('lock_closed' if lay['locked'] else 'lock_open'),
                                           tip='Bloqueada' if lay['locked'] else 'Desbloqueada'))
            self.grid.setItem(r, C_PLOT, mk(ico=icon('plot' if lay.get('plot', True) else 'noplot'),
                                            tip='Se traza en composiciones' if lay.get('plot', True)
                                            else 'No se traza en composiciones'))
            self.grid.setItem(r, C_COLOR, mk(color_display_name(lay['color']),
                                             color_swatch(ctrl.preview_color(lay).name(), 13, 13)))
            self.grid.setItem(r, C_LT, mk(lay['linetype']))
            lw = lay['lineweight']
            self.grid.setItem(r, C_LW, mk(lineweight_text(lw),
                                          lineweight_sample(LWDEFAULT_MM if lw is None or lw < 0 else lw,
                                                            28, 14, fg)))
            self.grid.setItem(r, C_TR, mk(str(lay.get('transparency', 0))))
            self.grid.setItem(r, C_DESC, mk(lay.get('description', ''), editable=True))
        self.grid.setIconSize(QSize(16, 16))
        for r, n in enumerate(names):
            if n in keep:
                self.grid.selectRow(r) if len(keep) == 1 else self._add_row_selection(r)
        fname = dict((k, l) for k, l, _ in FILTERS)[self.filter_key]
        extra = '' if ctrl.initialized else \
            '   ·   El campo LAYER_CODE se creará con el primer cambio.'
        self.lbl_status.setText('%s: %d capas mostradas de %d capas totales%s'
                                % (fname, len(names), len(ctrl.names()), extra))

    def _add_row_selection(self, r):
        sm = self.grid.selectionModel()
        SF = sm.__class__
        flags = enum(SF, 'SelectionFlag', 'Select') | enum(SF, 'SelectionFlag', 'Rows')
        sm.select(self.grid.model().index(r, 0), flags)

    def _select_names(self, names):
        self.grid.clearSelection()
        for r in range(self.grid.rowCount()):
            if self._row_name(r) in names:
                self._add_row_selection(r)

    # ------------------------------------------------------------ interacción
    def _cell_action(self, row, col):
        name = self._row_name(row)
        if name is None:
            return
        names = self._targets(row)
        lay = self.ctrl.find(name, True)
        if col in TOGGLE_COLS:
            self.ctrl.toggle(names, TOGGLE_COLS[col], reference=name)
        elif col == C_COLOR:
            dlg = ColorDialog(self, lay['color'], self.theme)
            if exec_dialog(dlg) == accepted_code():
                self.ctrl.set_props(names, color=dlg.color)
        elif col == C_LT:
            dlg = LinetypeDialog(self, lay['linetype'], self.theme)
            if exec_dialog(dlg) == accepted_code() and dlg.value():
                self.ctrl.set_props(names, linetype=dlg.value())
        elif col == C_LW:
            dlg = LineweightDialog(self, lay['lineweight'], self.theme)
            if exec_dialog(dlg) == accepted_code() and dlg.value() is not None:
                self.ctrl.set_props(names, lineweight=dlg.value())
        elif col == C_TR:
            dlg = TransparencyDialog(self, lay.get('transparency', 0), self.theme)
            if exec_dialog(dlg) == accepted_code():
                self.ctrl.set_props(names, transparency=dlg.value())

    def _cell_double(self, row, col):
        if col == C_STATUS:
            self.ctrl.set_current(self._row_name(row))
        elif col in (C_NAME, C_DESC):
            if col == C_NAME and self._row_name(row) == '0':
                self.ctrl.warn('No se puede cambiar el nombre de la capa 0.')
                return
            self.grid.editItem(self.grid.item(row, col))

    def _item_changed(self, item):
        if self._populating:
            return
        # Se difiere: la tabla se reconstruye y el elemento editado se destruye.
        name, col, text = self._row_name(item.row()), item.column(), item.text()
        QTimer.singleShot(0, lambda: self._apply_edit(name, col, text))

    def _apply_edit(self, name, col, text):
        if col == C_NAME:
            new = text.strip()
            if new == name:
                return
            if self.ctrl.rename(name, new):
                self._select_names([new])
            else:
                self.populate()
        elif col == C_DESC:
            self.ctrl.set_props([name], description=text)

    # ------------------------------------------------------------ comandos
    def new_layer(self):
        if not self.ctrl.active:
            return
        sel = self.selected_names()
        if self.search.text() or self.chk_invert.isChecked() or self.filter_key != 'all':
            self.search.clear()
            self.chk_invert.setChecked(False)
            self.filters.setCurrentItem(self.filters.topLevelItem(0))
        name = self.ctrl.add_layer(based_on=sel[0] if sel else None)
        if not name:
            return
        for r in range(self.grid.rowCount()):
            if self._row_name(r) == name:
                self.grid.selectRow(r)
                self.grid.scrollToItem(self.grid.item(r, C_NAME))
                self.grid.editItem(self.grid.item(r, C_NAME))
                break

    def delete_layers(self):
        names = self.selected_names()
        if not names:
            return
        deleted, errors = self.ctrl.delete_layers(names)
        if errors:
            QMessageBox.warning(self, 'Suprimir capa', '\n'.join(errors))

    def set_current_selected(self):
        names = self.selected_names()
        if len(names) == 1:
            self.ctrl.set_current(names[0])
        elif names:
            self.ctrl.warn('Selecciona una única capa para definirla como actual.')

    def rename_selected(self):
        r = self.grid.currentRow()
        if r >= 0:
            self._cell_double(r, C_NAME)

    def _order(self, delta=None, top=None):
        names = self.selected_names()
        if not names:
            return
        if delta is not None:
            self.ctrl.move(names, delta)
        else:
            self.ctrl.move_to(names, top)
        self._select_names(names)

    def select_objects(self):
        names = self.selected_names()
        if names:
            self.ctrl.select_objects(names)

    def assign_selection(self):
        names = self.selected_names()
        if len(names) != 1:
            self.ctrl.warn('Selecciona una única capa de destino.')
            return
        if not self.ctrl.has_selection():
            self.ctrl.warn('No hay objetos seleccionados en el mapa.')
            return
        self.ctrl.assign_selection(names[0])

    def merge_selected(self):
        names = self.selected_names()
        if not names:
            return
        targets = [n for n in self.ctrl.names() if n not in names]
        if not targets:
            return
        t, ok = QInputDialog.getItem(self, 'Fusionar capas (LAYMRG)',
                                     'Capa de destino para %s:' % ', '.join(names), targets, 0, False)
        if ok and t:
            if '0' in names:
                self.ctrl.warn('La capa 0 no se puede fusionar; se omite.')
            self.ctrl.merge(names, t)

    def open_states(self):
        if self.ctrl.ensure_initialized():
            exec_dialog(LayerStatesDialog(self, self.ctrl, self.theme))

    def import_layers(self):
        if not self.ctrl.active:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Importar capas', '', 'Configuración de capas (*.json *.txt)')
        if not path:
            return
        try:
            counts = self.ctrl.import_config(path)
            self.ctrl.msg('Importación: %d capas nuevas, %d actualizadas.' % (counts['new'], counts['upd']))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Importar capas', 'No se pudo leer el archivo:\n%s' % e)

    def export_layers(self):
        if not self.ctrl.active:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar capas', 'capas_cad.json',
                                              'Configuración de capas (*.json)')
        if path:
            try:
                self.ctrl.export_config(path)
                self.ctrl.msg('Capas exportadas a %s' % path)
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, 'Exportar capas', str(e))

    # ------------------------------------------------------------ menús
    def _context_menu(self, pos):
        if not self.ctrl.active:
            return
        row = self.grid.rowAt(pos.y())
        if row >= 0 and self._row_name(row) not in self.selected_names():
            self.grid.selectRow(row)
        names = self.selected_names()
        one = len(names) == 1
        m = QMenu(self)
        a = _add(m, icon('set_current'), 'Definir actual', self.set_current_selected)
        a.setEnabled(one)
        _add(m, icon('new_layer'), 'Nueva capa', self.new_layer)
        a = _add(m, None, 'Cambiar nombre de capa', self.rename_selected)
        a.setEnabled(one)
        a = _add(m, icon('del_layer'), 'Suprimir capa', self.delete_layers)
        a.setEnabled(bool(names))
        a = _add(m, None, 'Cambiar descripción', lambda: self._cell_double(self.grid.currentRow(), C_DESC))
        a.setEnabled(one)
        m.addSeparator()
        _add(m, None, 'Seleccionar todas', self.grid.selectAll)
        _add(m, None, 'Borrar todo', self.grid.clearSelection)
        _add(m, None, 'Seleccionar todas excepto la actual', lambda: self._select_names([n for n in self.ctrl.names() if n != self.ctrl.current]))
        _add(m, None, 'Invertir selección', lambda: self._select_names([n for n in self.ctrl.names() if n not in names]))
        _add(m, None, 'Invertir filtro de capas', lambda: self.chk_invert.toggle())
        m.addSeparator()
        a = _add(m, icon('select_objs'), 'Seleccionar objetos de la capa', self.select_objects)
        a.setEnabled(bool(names))
        a = _add(m, icon('assign'), 'Mover objetos seleccionados a esta capa', self.assign_selection)
        a.setEnabled(one and self.ctrl.has_selection())
        a = _add(m, icon('merge'), 'Fusionar en otra capa (LAYMRG)...', self.merge_selected)
        a.setEnabled(bool(names))
        a = _add(m, icon('layiso'), 'Aislar capas seleccionadas', lambda: self.ctrl.isolate(names))
        a.setEnabled(bool(names))
        om = m.addMenu('Orden de dibujo')
        _add(om, icon('move_top'), 'Traer al frente', lambda: self._order(top=True))
        _add(om, icon('move_up'), 'Subir', lambda: self._order(delta=-1))
        _add(om, icon('move_down'), 'Bajar', lambda: self._order(delta=1))
        _add(om, icon('move_bottom'), 'Enviar al fondo', lambda: self._order(top=False))
        m.addSeparator()
        _add(m, icon('states'), 'Guardar estado de capa...', self._quick_save_state)
        rm = m.addMenu('Restaurar estado de capa')
        states = sorted(self.ctrl.cfg['states'])
        rm.setEnabled(bool(states))
        for s in states:
            _add(rm, None, s, lambda _=False, s=s: self.ctrl.restore_state(s))
        exec_menu(m, self.grid.viewport().mapToGlobal(pos))

    def _quick_save_state(self):
        name, ok = QInputDialog.getText(self, 'Guardar estado de capa', 'Nombre del estado:')
        if ok and name.strip():
            self.ctrl.save_state(name.strip())
            self.ctrl.msg('Estado de capa "%s" guardado.' % name.strip())

    def _header_menu(self, pos):
        m = QMenu(self)
        for c, h in enumerate(HEADERS):
            if c == C_NAME:
                continue
            a = m.addAction(h)
            a.setCheckable(True)
            a.setChecked(not self.grid.isColumnHidden(c))
            a.toggled.connect(lambda on, c=c: self._set_col(c, on))
        exec_menu(m, self.grid.horizontalHeader().mapToGlobal(pos))

    def _set_col(self, c, visible):
        self.grid.setColumnHidden(c, not visible)
        hidden = [i for i in range(len(HEADERS)) if self.grid.isColumnHidden(i)]
        self.ctrl.set_setting('hidden_columns', ','.join(map(str, hidden)))
