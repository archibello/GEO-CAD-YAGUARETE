# -*- coding: utf-8 -*-
"""
GeoCAD · módulo Dibujo (antes el complemento Dibujo CAD 16.3).

Dibujo CAD para QGIS: línea de comandos al estilo AutoCAD y barra de dibujo.

API para otros complementos (barras de edición, Layer Properties Manager...):

    from qgis.utils import plugins
    host = plugins.get('Dibujo_CAD')
    if host:
        host.register_command('LAYISO', ['AISLARCAPA'], mi_funcion,
                              title='AISLARCAPA', group='capas', description='Aísla capas')

Además, si un complemento define el método register_cad_commands(host),
Dibujo CAD lo llama automáticamente al iniciarse.
"""

import os

from qgis.PyQt.QtCore import QTimer

from .commands import CommandManager, CommandSpec
from .maptool import KeyGuard
from .edit_commands import EDIT_COMMANDS, oops
from .block_commands import BlockCommand, InsertCommand, purge, wblock
from .curves import ArcCommand, CircleCommand
from .rectang import RectangCommand
from .paper_commands import LayoutCommand, LayoutTabs, MViewCommand, MVLockCommand, PlotCommand
from .text_select import TextSelectTool
from .text_tool import SIZES, DTextCommand, EditTextCommand, TextStyle, apply_style_to_selection
from .cmdline import CommandLine
from .compat import QAction, exec_dialog, accepted_code, qt
from .settings import save_units
from .units_dialog import UnitsDialog

ICON_DIR = os.path.join(os.path.dirname(__file__), 'icons')
MENU = '&Dibujo CAD'


def _version():
    """Versión instalada: la de GeoCAD (metadata.txt de la carpeta de GeoCAD)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'metadata.txt'),
                  encoding='utf-8') as f:
            for line in f:
                if line.startswith('version='):
                    return line.split('=', 1)[1].strip()
    except OSError:
        pass
    return ''


def _modulo(clave):
    """¿Está activo ese módulo de GeoCAD en QGIS? (Bloques, Papel)."""
    try:
        from .. import modulos
        return modulos.activo('qgis', clave)
    except Exception:  # noqa: BLE001
        return True


def _safe(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass


def _icon(name):
    from qgis.PyQt.QtGui import QIcon
    return QIcon(os.path.join(ICON_DIR, name + '.svg'))


class DibujoCADPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.cmdline = None
        self.mgr = None
        self.toolbar = None
        self.edit_toolbar = None
        self.text_toolbar = None
        self.block_toolbar = None
        self.paper_toolbar = None
        self.actions = []

    # ------------------------------------------------------------ API pública
    def register_command(self, name, aliases, handler, kind='action', title=None,
                         layer_types=None, edit=False, group='', description=''):
        return self.mgr.register(CommandSpec(name, aliases, handler, kind, title,
                                             layer_types, edit, group, description))

    def unregister_commands(self, group):
        if self.mgr is not None:
            self.mgr.unregister(group=group)

    def run_command(self, text):
        """Ejecuta un comando como si se escribiera en la línea de comandos."""
        if self.cmdline is not None and not self.cmdline.isVisible():
            self.cmdline.show()
        self.cmdline.echo('Comando: %s' % text)
        self.mgr.run(text)

    # ------------------------------------------------------------ GUI
    def initGui(self):
        from . import crashlog
        crashlog.enable()
        mw = self.iface.mainWindow()
        self.cmdline = CommandLine(mw)
        self.iface.addDockWidget(qt('DockWidgetArea', 'BottomDockWidgetArea'), self.cmdline)
        self.mgr = CommandManager(self.iface, self.cmdline)
        self.mgr.unitsRequested.connect(self.open_units)
        self.iface.projectRead.connect(self.mgr.reload_units)
        self.iface.newProjectCreated.connect(self.mgr.reload_units)

        self.toolbar = self.iface.addToolBar('Dibujo CAD')
        self.toolbar.setObjectName('DibujoCADToolbar')
        self._action('line', 'Línea (LÍNEA / L)', lambda: self.run_command('LINEA'))
        self._action('pline', 'Polilínea (POLILÍNEA / PL)', lambda: self.run_command('POLILINEA'))
        self.mgr.register(CommandSpec('ARC', ('ARCO', 'A', 'ARC'), ArcCommand, 'interactive', 'ARCO',
                                      ('line',), True, 'dibujo',
                                      'Arco: 3 puntos, inicio-centro-final, ángulo, radio'))
        self.mgr.register(CommandSpec('CIRCLE', ('CIRCULO', 'CÍRCULO', 'C', 'CI'), CircleCommand,
                                      'interactive', 'CÍRCULO', ('line', 'polygon'), True, 'dibujo',
                                      'Círculo: centro-radio/diámetro, 3P, 2P'))
        self._action('arc', 'Arco (ARCO / A) — 3 puntos o con la opción Centro', lambda: self.run_command('ARCO'))
        self._action('circle', 'Círculo (CÍRCULO / C) — centro y radio, Diámetro, 3P, 2P',
                     lambda: self.run_command('CIRCULO'))
        self.mgr.register(CommandSpec('RECTANG', ('RECTANGULO', 'RECTÁNGULO', 'REC', 'RECTANG', 'RECTANGLE',
                                                  'RECT'), RectangCommand, 'interactive', 'RECTANG',
                                      ('line', 'polygon'), True, 'dibujo',
                                      'Rectángulo: Chaflán, Empalme, Área, Cotas, Rotación'))
        self._action('rect', 'Rectángulo (RECTANG / REC) — Chaflán, Empalme, Área, Cotas, Rotación',
                     lambda: self.run_command('RECTANG'))
        self.toolbar.addSeparator()
        self.a_ortho = self._action('ortho', 'Modo Orto (F8) — Mayús lo invierte temporalmente',
                                    self.mgr.set_ortho, checkable=True)
        self.a_ortho.setChecked(self.mgr.ortho)
        self.mgr.orthoChanged.connect(self.a_ortho.setChecked)
        self.a_osnap = self._action('osnap', 'Referencia a objetos (F3) — usa el snapping de QGIS',
                                    self.mgr.set_osnap, checkable=True)
        self.a_osnap.setChecked(self.mgr.osnap_enabled())
        self.mgr.osnapChanged.connect(self.a_osnap.setChecked)
        self.a_rel = self._action('relangle', 'Ángulos relativos al último tramo (REL). '
                                  'Con el modo activo, <<ang fuerza un ángulo absoluto',
                                  self.mgr.set_relative, checkable=True)
        self.a_rel.setChecked(self.mgr.relative)
        self.mgr.relativeChanged.connect(self.a_rel.setChecked)
        self._action('units', 'Unidades de dibujo (UNIDADES / UN)', self.open_units)
        from .dyninput import DynamicInput
        self.dyn = DynamicInput(self.iface.mapCanvas(), self.cmdline, self.mgr)
        self.mgr.register(CommandSpec('DYNMODE', ('ENTRADADIN', 'DYN', 'DYNMODE', 'ED2'), self.dyn.toggle,
                                      title='ENTRADADIN', group='dibujo',
                                      description='Entrada dinámica junto al cursor (F12)'))
        self.mgr.register(CommandSpec('CMDTHEME', ('FONDOLC', 'TEMALC', 'CMDTHEME'),
                                      lambda: self.cmdline.set_theme('dark' if self.cmdline.theme == 'light' else 'light'),
                                      title='FONDOLC', group='dibujo',
                                      description='Línea de comandos: fondo claro (AutoCAD) u oscuro'))
        self.a_cmd = self._action('cmdline', 'Línea de comandos (Ctrl+9)', self.cmdline.setVisible,
                                  checkable=True)
        self.a_cmd.setShortcut('Ctrl+9')
        self.a_cmd.setChecked(True)
        self.cmdline.visibilityChanged.connect(self.a_cmd.setChecked)

        # ---- barra Edición CAD
        self.edit_toolbar = self.iface.addToolBar('Edición CAD')
        self.edit_toolbar.setObjectName('EdicionCADToolbar')
        for name, aliases, cls, title, types, desc, ico in EDIT_COMMANDS:
            self.mgr.register(CommandSpec(name, aliases, cls, 'interactive', title, types, True,
                                          'edición', desc))
            al = ', '.join(a for a in aliases[:3])
            self._action(ico, '%s (%s) — %s' % (title, al, desc),
                         lambda t=title: self.run_command(t), toolbar=self.edit_toolbar)

        self.mgr.register(CommandSpec('OOPS', ('UPS', 'RECUPERAR'), lambda: oops(self.mgr), title='UPS',
                                      group='edición', description='Recupera lo borrado por el último BORRA'))

        # ---- paleta Propiedades (Ctrl+1)
        self._build_properties()

        # ---- barra Texto CAD
        self._build_text_toolbar()

        # ---- barra Bloques CAD (módulo «Bloques» de GeoCAD)
        if _modulo('bloques'):
            self._build_block_toolbar()
            from .blocks import start_sync
            start_sync(self.iface)          # snapping de QGIS sobre los bloques

        # ---- espacio papel: pestañas Modelo / Presentaciones y trazado (módulo «Papel»)
        if _modulo('papel'):
            self._build_paper_toolbar()

        # ---- aislamiento del teclado mientras se usan las herramientas CAD
        self.key_guard = KeyGuard(self.iface.mapCanvas(), self.mgr)
        self.key_guard.tools = [self.mgr.tool, self.text_select_tool]

        self.cmdline.echo('GeoCAD %s · Dibujo CAD listo. Escriba AYUDA para ver los comandos disponibles.'
                          % _version())
        QTimer.singleShot(0, self._discover)
        from qgis.core import QgsProject
        self._saving_again = False
        QgsProject.instance().projectSaved.connect(self._on_project_saved)
        self.iface.projectRead.connect(self._adopt_texts_later)
        QTimer.singleShot(500, self._adopt_texts_later)
        # composiciones: se actualizan al pasar a su ventana si el modelo cambió
        self.layout_refresh = None
        if _modulo('papel'):
            try:
                from .layout_refresh import LayoutAutoRefresh
                self.layout_refresh = LayoutAutoRefresh(self.iface)
            except Exception:  # noqa: BLE001
                self.layout_refresh = None

    def _adopt_texts_later(self, *args):
        QTimer.singleShot(300, self._adopt_texts)

    def _adopt_texts(self):
        from .text_tool import adopt_all_text_layers
        _safe(lambda: adopt_all_text_layers(self.iface))

    def _on_project_saved(self, *args):
        """Las capas temporales de Dibujo CAD se convierten en GeoPackage y se vuelve a guardar."""
        if self._saving_again:
            return
        from .auxlayers import persist_memory_layers
        n = persist_memory_layers(self.cmdline.echo if self.cmdline is not None else None)
        if n:
            from qgis.core import QgsProject
            self._saving_again = True
            try:
                QgsProject.instance().write()
            finally:
                self._saving_again = False

    def _build_properties(self):
        from .properties_panel import PropertiesPanel
        self.props = PropertiesPanel(self.iface, self.mgr, self.iface.mainWindow())
        self.iface.addDockWidget(qt('DockWidgetArea', 'RightDockWidgetArea'), self.props)
        self.props.hide()
        self.a_props = self._action('properties', 'Propiedades (PROPIEDADES / PR / Ctrl+1) — ver y modificar '
                                    'los objetos seleccionados', self.props.setVisible, checkable=True,
                                    toolbar=self.edit_toolbar)
        self.props.visibilityChanged.connect(self.a_props.setChecked)
        # Ctrl+1 como en AutoCAD, si QGIS no lo usa para otra cosa
        try:
            from qgis.PyQt.QtGui import QKeySequence
            _QA = QAction
            seq = QKeySequence('Ctrl+1')
            taken = any(a.shortcut() == seq for a in self.iface.mainWindow().findChildren(_QA)
                        if a is not self.a_props)
            if not taken:
                self.a_props.setShortcut(seq)
        except Exception:  # noqa: BLE001
            pass
        self.mgr.register(CommandSpec('PROPERTIES', ('PROPIEDADES', 'PR', 'CH', 'MO', 'PROPS', 'PROPERTIES'),
                                      lambda: (self.props.show(), self.props.raise_(), self.props.schedule()),
                                      title='PROPIEDADES', group='edición',
                                      description='Paleta Propiedades de los objetos seleccionados (Ctrl+1)'))

    def _build_text_toolbar(self):
        from qgis.PyQt.QtGui import QDoubleValidator, QFont
        from qgis.PyQt.QtWidgets import QComboBox, QFontComboBox
        self.mgr.text_style = TextStyle()
        self.mgr.register(CommandSpec('DTEXT', ('TEXTO', 'TEXT', 'DT', 'TX', 'TEXTODIN'), DTextCommand,
                                      'interactive', 'TEXTO', None, False, 'texto',
                                      'Texto en una línea: altura, ángulo y justificación'))
        self.mgr.register(CommandSpec('DDEDIT', ('EDITTEXTO', 'TEXTEDIT', 'ED'), EditTextCommand,
                                      'interactive', 'EDITTEXTO', None, False, 'texto',
                                      'Modificar el contenido de un texto'))
        tb = self.text_toolbar = self.iface.addToolBar('Texto CAD')
        tb.setObjectName('TextoCADToolbar')
        self._action('dtext', 'Texto (TEXTO / DT) — altura y ángulo al insertar, como DTEXT',
                     lambda: self.run_command('TEXTO'), toolbar=tb)
        self._action('edittext', 'Editar texto (EDITTEXTO / ED)', lambda: self.run_command('EDITTEXTO'),
                     toolbar=tb)
        self.text_select_tool = TextSelectTool(self.iface, self.mgr)
        self.mgr.register(CommandSpec('TEXTSEL', ('SELTEXTO', 'SELECCIONARTEXTO', 'ST'), self._activate_text_select,
                                      title='SELTEXTO', group='texto',
                                      description='Seleccionar textos: mover, girar, altura y editar en el lugar'))
        self._action('seltext', 'Seleccionar texto (SELTEXTO / ST) — pinzamientos para mover, girar, '
                     'cambiar altura; doble clic para editar', lambda: self.run_command('SELTEXTO'), toolbar=tb)
        self.font_combo = QFontComboBox()
        self.font_combo.setToolTip('Fuente del texto (se aplica también a los textos seleccionados)')
        self.font_combo.setMaximumWidth(190)
        tb.addWidget(self.font_combo)
        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.addItems(SIZES)
        self.size_combo.setToolTip('Altura de texto en unidades del mapa (se aplica también a los textos seleccionados)')
        self.size_combo.setMinimumWidth(80)
        v = QDoubleValidator(0.0001, 1e7, 4)
        self.size_combo.setValidator(v)
        tb.addWidget(self.size_combo)
        self.a_bold = self._action('bold', 'Negrita (se aplica también a los textos seleccionados)',
                                   self._set_bold, checkable=True, toolbar=tb)
        self._build_text_color(tb)
        self._sync_text_widgets()
        self.font_combo.currentFontChanged.connect(self._set_font)
        self.size_combo.activated.connect(lambda *_: self._set_size())
        self.size_combo.lineEdit().editingFinished.connect(self._set_size)
        self.mgr.textStyleChanged.connect(self._sync_text_widgets)
        self.iface.projectRead.connect(self._reload_text_style)

    def _build_block_toolbar(self):
        tb = self.block_toolbar = self.iface.addToolBar('Bloques CAD')
        tb.setObjectName('BloquesCADToolbar')
        self.mgr.register(CommandSpec('BLOCK', ('BLOQUE', 'B', 'BLOCK', 'BMAKE'), BlockCommand, 'interactive',
                                      'BLOQUE', ('line', 'polygon', 'point'), True, 'bloques',
                                      'Crea o redefine un bloque: nombre, punto base y objetos'))
        self.mgr.register(CommandSpec('INSERT', ('INSERTAR', 'I', 'INSERT', 'DDINSERT'), InsertCommand,
                                      'interactive', 'INSERT', None, False, 'bloques',
                                      'Inserta un bloque (escala, rotación, descomponer, biblioteca)'))
        self.mgr.register(CommandSpec('WBLOCK', ('WBLOQUE', 'W', 'WBLOCK'), lambda: wblock(self.mgr),
                                      title='WBLOQUE', group='bloques',
                                      description='Escribe bloques en una biblioteca .gpkg'))
        self.mgr.register(CommandSpec('PURGE', ('LIMPIA', 'PU', 'PURGE'), lambda: purge(self.mgr),
                                      title='LIMPIA', group='bloques',
                                      description='Elimina las definiciones de bloque sin usar'))
        self._action('block', 'Crear bloque (BLOQUE / B)', lambda: self.run_command('BLOQUE'), toolbar=tb)
        self._action('insert', 'Insertar bloque (INSERT / I)', lambda: self.run_command('INSERT'), toolbar=tb)
        self._action('wblock', 'Escribir bloque en biblioteca (WBLOQUE / W)', lambda: self.run_command('WBLOQUE'),
                     toolbar=tb)
        self._action('purge', 'Limpiar bloques sin usar (LIMPIA / PU)', lambda: self.run_command('LIMPIA'),
                     toolbar=tb)

    def _build_paper_toolbar(self):
        from qgis.PyQt.QtWidgets import QToolBar
        mw = self.iface.mainWindow()
        tb = self.paper_toolbar = QToolBar('Presentaciones', mw)
        tb.setObjectName('PresentacionesCADToolbar')
        mw.addToolBar(qt('ToolBarArea', 'BottomToolBarArea'), tb)
        self.mgr.register(CommandSpec('PLOT', ('TRAZAR', 'PLOT', 'IMPRIMIR', 'PRINT'), PlotCommand, 'interactive',
                                      'TRAZAR', None, False, 'papel',
                                      'Trazar a PDF, imagen o impresora (Ventana, Extensión, Pantalla, Presentación)'))
        self.mgr.register(CommandSpec('LAYOUT', ('PRESENTACION', 'PRESENTACIÓN', 'LAYOUT', 'LO', 'PRE'),
                                      LayoutCommand, 'interactive', 'PRESENTACION', None, False, 'papel',
                                      'Presentaciones: Nueva (hoja, cajetín, escala), Abrir, Copiar, Renombrar, Suprimir'))
        self.mgr.register(CommandSpec('MVIEW', ('VENTANAS', 'MVIEW', 'MV'), MViewCommand, 'interactive',
                                      'VENTANAS', None, False, 'papel', 'Agrega una ventana gráfica a escala'))
        self.mgr.register(CommandSpec('MVLOCK', ('BLOQVENT', 'BLOQUEARVENTANAS', 'VPLOCK', 'MVLOCK', 'BV'),
                                      MVLockCommand, 'interactive', 'BLOQVENT', None, False, 'papel',
                                      'Bloquea/desbloquea las ventanas de una presentación (capas, estilos y encuadre)'))
        self._action('plot', 'Trazar (TRAZAR / PLOT)', lambda: self.run_command('TRAZAR'), toolbar=tb)
        self._action('layout', 'Nueva presentación (PRESENTACION)', lambda: self.run_command('PRESENTACION'),
                     toolbar=tb)
        self._action('mview', 'Ventana gráfica (VENTANAS / MVIEW)', lambda: self.run_command('VENTANAS'), toolbar=tb)
        tb.addSeparator()
        self.layout_tabs = LayoutTabs(self)
        tb.addWidget(self.layout_tabs)
        self.iface.projectRead.connect(self.layout_tabs.refresh)
        self.iface.newProjectCreated.connect(self.layout_tabs.refresh)

    # -- color de texto (PorCapa o color propio), como la lista de colores de AutoCAD
    TEXT_COLORS = [('PorCapa', ''), ('1 Rojo', '#ff0000'), ('2 Amarillo', '#ffff00'),
                   ('3 Verde', '#00ff00'), ('4 Cian', '#00ffff'), ('5 Azul', '#0000ff'),
                   ('6 Magenta', '#ff00ff'), ('7 Blanco/Negro', '#000000'),
                   ('8 Gris oscuro', '#414141'), ('9 Gris', '#808080')]

    def _build_text_color(self, tb):
        from qgis.PyQt.QtWidgets import QMenu, QToolButton
        btn = self.text_color_btn = QToolButton()
        btn.setToolTip('Color del texto: PorCapa (color de su capa CAD) o un color propio.\n'
                       'Se aplica a los textos nuevos y a los textos seleccionados.')
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup
                         if hasattr(QToolButton, 'ToolButtonPopupMode') else QToolButton.InstantPopup)
        try:
            btn.setToolButtonStyle(qt('ToolButtonStyle', 'ToolButtonTextBesideIcon'))
        except Exception:  # noqa: BLE001
            pass
        m = QMenu(btn)
        for label, value in self.TEXT_COLORS:
            a = m.addAction(self._color_icon(value), label)
            a.triggered.connect(lambda *_, v=value: self._set_text_color(v))
        m.addSeparator()
        a = m.addAction('Otro color...')
        a.triggered.connect(lambda *_: self._pick_text_color())
        btn.setMenu(m)
        tb.addWidget(btn)
        self._sync_text_color()

    def _color_icon(self, value):
        from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPixmap
        pm = QPixmap(14, 14)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        if not value:                                   # PorCapa: cuadro mitad blanco / mitad negro
            p.fillRect(0, 0, 7, 14, QColor('#ffffff'))
            p.fillRect(7, 0, 7, 14, QColor('#000000'))
        elif value.lower() == '#000000':                # color 7
            p.fillRect(0, 0, 14, 14, QColor('#ffffff'))
            p.fillRect(0, 7, 14, 7, QColor('#000000'))
        else:
            p.fillRect(0, 0, 14, 14, QColor(value))
        p.setPen(QColor('#606060'))
        p.drawRect(0, 0, 13, 13)
        p.end()
        return QIcon(pm)

    def _sync_text_color(self):
        btn = getattr(self, 'text_color_btn', None)
        if btn is None or self.mgr.text_style is None:
            return
        v = self.mgr.text_style.color or ''
        name = next((l for l, c in self.TEXT_COLORS if c.lower() == v.lower()), v)
        btn.setIcon(self._color_icon(v))
        btn.setText(name)

    def _set_text_color(self, value):
        self.mgr.text_style.color = value or ''
        self._sync_text_color()
        self._style_changed('color')

    def _pick_text_color(self):
        from qgis.PyQt.QtGui import QColor
        from qgis.PyQt.QtWidgets import QColorDialog
        cur = self.mgr.text_style.color or '#ffffff'
        c = QColorDialog.getColor(QColor(cur), self.iface.mainWindow(), 'Color del texto')
        if c.isValid():
            self._set_text_color(c.name())

    def _activate_text_select(self):
        self.iface.mapCanvas().setMapTool(self.text_select_tool)

    def _reload_text_style(self):
        self.mgr.text_style = TextStyle()
        self._sync_text_widgets()

    def _sync_text_widgets(self):
        from qgis.PyQt.QtGui import QFont
        st = self.mgr.text_style
        for w in (self.font_combo, self.size_combo, self.a_bold):
            w.blockSignals(True)
        self.font_combo.setCurrentFont(QFont(st.font))
        self.size_combo.setEditText('%.2f' % st.height)
        self.a_bold.setChecked(st.bold)
        for w in (self.font_combo, self.size_combo, self.a_bold):
            w.blockSignals(False)
        self._sync_text_color()

    def _style_changed(self, what):
        st = self.mgr.text_style
        st.save()
        n = apply_style_to_selection(self.iface, st, what)
        if n:
            self.cmdline.echo('Estilo aplicado a %d texto(s) seleccionado(s).' % n)

    def _set_font(self, font):
        self.mgr.text_style.font = font.family()
        self._style_changed('font')

    def _set_size(self):
        try:
            h = float(self.size_combo.currentText().replace(',', '.'))
        except ValueError:
            return
        if h <= 0 or abs(h - self.mgr.text_style.height) < 1e-12:
            return
        self.mgr.text_style.height = h
        self._style_changed('height')

    def _set_bold(self, on):
        self.mgr.text_style.bold = bool(on)
        self._style_changed('bold')

    def _discover(self):
        """Pide a los demás complementos que registren sus comandos."""
        try:
            from qgis.utils import plugins
        except ImportError:
            return
        for name, inst in list(plugins.items()):
            if inst is self:
                continue
            fn = getattr(inst, 'register_cad_commands', None)
            if callable(fn):
                try:
                    fn(self)
                except Exception as e:  # noqa: BLE001
                    self.cmdline.echo('No se pudieron registrar los comandos de %s: %s' % (name, e))

    def _action(self, ico, text, slot, checkable=False, toolbar=None):
        a = QAction(_icon(ico), text, self.iface.mainWindow())
        a.setToolTip(text)
        a.setCheckable(checkable)
        if checkable:
            a.triggered.connect(lambda checked=False: slot(checked))
        else:
            a.triggered.connect(lambda *_: slot())
        (toolbar or self.toolbar).addAction(a)
        self.iface.addPluginToMenu(MENU, a)
        self.actions.append(a)
        return a

    def open_units(self):
        dlg = UnitsDialog(self.iface.mainWindow(), self.mgr.units)
        if exec_dialog(dlg) == accepted_code():
            self.mgr.units = dlg.units()
            save_units(self.mgr.units)
            self.mgr.refresh()

    def unload(self):
        dyn = getattr(self, 'dyn', None)
        if dyn is not None:
            try:
                dyn.unload()
            except Exception:  # noqa: BLE001
                pass
            self.dyn = None
        pp = getattr(self, 'props', None)
        if pp is not None:
            try:
                pp.unload()
                self.iface.removeDockWidget(pp)
                pp.deleteLater()
            except Exception:  # noqa: BLE001
                pass
            self.props = None
        lr = getattr(self, 'layout_refresh', None)
        if lr is not None:
            try:
                lr.unload()
            except Exception:  # noqa: BLE001
                pass
            self.layout_refresh = None
        try:
            from qgis.core import QgsProject
            QgsProject.instance().projectSaved.disconnect(self._on_project_saved)
        except (TypeError, RuntimeError, AttributeError):
            pass
        try:
            self.iface.projectRead.disconnect(self._adopt_texts_later)
        except (TypeError, RuntimeError, AttributeError):
            pass
        if self.mgr is not None:
            if self.mgr.command is not None:
                self.mgr.cancel()
            try:
                self.iface.projectRead.disconnect(self.mgr.reload_units)
                self.iface.newProjectCreated.disconnect(self.mgr.reload_units)
            except (TypeError, RuntimeError):
                pass
            self.mgr.tool.clear()
            self.mgr.tool.remove_items()
            if self.iface.mapCanvas().mapTool() is self.mgr.tool:
                self.iface.mapCanvas().unsetMapTool(self.mgr.tool)
        for a in self.actions:
            self.iface.removePluginMenu(MENU, a)
        self.actions = []
        try:
            self.iface.projectRead.disconnect(self._reload_text_style)
        except (TypeError, RuntimeError, AttributeError):
            pass
        try:
            from .blocks import stop_sync
            stop_sync()
        except Exception:  # noqa: BLE001
            pass
        kg = getattr(self, 'key_guard', None)
        if kg is not None:
            kg.remove()
            self.key_guard = None
        tst = getattr(self, 'text_select_tool', None)
        if tst is not None:
            if self.iface.mapCanvas().mapTool() is tst:
                self.iface.mapCanvas().unsetMapTool(tst)
            tst.remove_items()
            self.text_select_tool = None
        if getattr(self, 'paper_toolbar', None) is not None:
            try:
                self.iface.projectRead.disconnect(self.layout_tabs.refresh)
                self.iface.newProjectCreated.disconnect(self.layout_tabs.refresh)
            except (TypeError, RuntimeError):
                pass
            try:
                self.layout_tabs.disconnect_all()
            except (TypeError, RuntimeError):
                pass
            self.iface.mainWindow().removeToolBar(self.paper_toolbar)
        for tb in ('toolbar', 'edit_toolbar', 'text_toolbar', 'block_toolbar', 'paper_toolbar'):
            if getattr(self, tb, None) is not None:
                getattr(self, tb).deleteLater()
                setattr(self, tb, None)
        if self.cmdline is not None:
            self.iface.removeDockWidget(self.cmdline)
            self.cmdline.deleteLater()
            self.cmdline = None
        self.mgr = None
