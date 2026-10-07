# -*- coding: utf-8 -*-
# GeoCAD · módulo Capas CAD (antes el complemento Layer Properties 6.7).
"""
Layer Properties Manager (estilo AutoCAD) para QGIS 3.28+ / 4.x

Barra de herramientas 'Capas CAD' (equivalente a la barra Capas / panel Capas de AutoCAD)
y paleta 'Administrador de propiedades de capas'.
"""

from qgis.PyQt.QtCore import Qt, QTimer

from .compat import QAction, qt
from .controller import CadLayerController
from .icons import icon
from .layer_combo import LayerCombo
from .manager import LayerManagerDock
from .maptools import PickFeatureTool

MENU = '&Capas CAD'


class LayerPropertiesPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.ctrl = None
        self.toolbar = None
        self.dock = None
        self.actions = []
        self.pick_tool = None

    # ------------------------------------------------------------ GUI
    def initGui(self):
        self.ctrl = CadLayerController(self.iface)

        self.toolbar = self.iface.addToolBar('Capas CAD')
        self.toolbar.setObjectName('CadLayersToolbar')
        self.toolbar.setToolTip('Capas CAD')

        self.a_props = self._action('layprops', 'Administrador de propiedades de capas (LAYER)',
                                    self.toggle_manager, checkable=True, menu=True)
        self.combo = LayerCombo(self.ctrl, self.toolbar)
        self.toolbar.addWidget(self.combo)
        self._action('laymcur', 'Establecer como actual la capa del objeto (LAYMCUR)', self.cmd_laymcur)
        self.a_prev = self._action('layerp', 'Capa previa (LAYERP)', self.ctrl.layer_previous)
        self.toolbar.addSeparator()
        self._action('laymch', 'Igualar capa (LAYMCH)', self.cmd_laymch)
        self._action('layiso', 'Aislar (LAYISO)', self.cmd_layiso)
        self._action('layuniso', 'Desaislar (LAYUNISO)', self.ctrl.unisolate)
        self._action('layoff', 'Desactivar capa del objeto (LAYOFF)', lambda: self._with_layers(self.ctrl.layoff, 'desactivar'))
        self._action('layfrz', 'Inutilizar capa del objeto (LAYFRZ)', lambda: self._with_layers(self.ctrl.layfrz, 'inutilizar'))
        self._action('laylck', 'Bloquear capa del objeto (LAYLCK)', lambda: self._with_layers(self.ctrl.laylck, 'bloquear'))
        self._action('layulk', 'Desbloquear capa del objeto (LAYULK)', lambda: self._with_layers(self.ctrl.layulk, 'desbloquear'))
        self._action('layon', 'Activar todas las capas (LAYON)', self.ctrl.layon_all)
        self._action('laythw', 'Reutilizar todas las capas (LAYTHW)', self.ctrl.laythw_all)
        self.toolbar.addSeparator()
        self.a_lw = self._action('lwdisplay', 'Mostrar/ocultar grosor de línea (LWDISPLAY)',
                                 self._toggle_lw, checkable=True)
        self.a_lw.setChecked(self.ctrl.lwdisplay)

        self.ctrl.changed.connect(self._update_actions)
        self.ctrl.attachedChanged.connect(self._update_actions)
        self.ctrl.attach(self.iface.activeLayer())
        self._update_actions()
        QTimer.singleShot(0, self._connect_command_line)

    # ------------------------------------------------------------ línea de comandos (Dibujo CAD)
    def _connect_command_line(self):
        try:
            from qgis.utils import plugins
        except ImportError:
            return
        host = plugins.get('Dibujo_CAD')
        if host is not None and getattr(host, 'mgr', None) is not None:
            self.register_cad_commands(host)

    def register_cad_commands(self, host):
        """Registra los comandos de capa en la línea de comandos de Dibujo CAD."""
        self._cad_host = host
        cmds = [
            ('LAYER', ('CAPA', 'LA', 'CA'), lambda: self.toggle_manager(True), 'CAPA',
             'Administrador de propiedades de capas'),
            ('LAYMCUR', ('ESTCAPACT',), self.cmd_laymcur, 'LAYMCUR', 'Capa del objeto como actual'),
            ('LAYERP', ('CAPAP',), self.ctrl.layer_previous, 'CAPAP', 'Capa previa'),
            ('LAYMCH', ('IGUALARCAPA',), self.cmd_laymch, 'IGUALARCAPA', 'Igualar capa'),
            ('LAYISO', ('AISLARCAPA',), self.cmd_layiso, 'AISLARCAPA', 'Aislar capas'),
            ('LAYUNISO', ('DESAISLARCAPA',), self.ctrl.unisolate, 'DESAISLARCAPA', 'Desaislar capas'),
            ('LAYOFF', ('DESACTCAPA',), lambda: self._with_layers(self.ctrl.layoff, 'desactivar'),
             'DESACTCAPA', 'Desactivar capa del objeto'),
            ('LAYFRZ', ('INUTCAPA',), lambda: self._with_layers(self.ctrl.layfrz, 'inutilizar'),
             'INUTCAPA', 'Inutilizar capa del objeto'),
            ('LAYLCK', ('BLOQCAPA',), lambda: self._with_layers(self.ctrl.laylck, 'bloquear'),
             'BLOQCAPA', 'Bloquear capa del objeto'),
            ('LAYULK', ('DESBLOQCAPA',), lambda: self._with_layers(self.ctrl.layulk, 'desbloquear'),
             'DESBLOQCAPA', 'Desbloquear capa del objeto'),
            ('LAYON', ('ACTCAPA',), self.ctrl.layon_all, 'ACTCAPA', 'Activar todas las capas'),
            ('LAYTHW', ('REUTCAPA',), self.ctrl.laythw_all, 'REUTCAPA', 'Reutilizar todas las capas'),
            ('LWDISPLAY', ('GROSORVIS', 'LWD'),
             lambda: self.a_lw.trigger(), 'LWDISPLAY', 'Mostrar/ocultar grosor de línea'),
        ]
        for name, aliases, fn, title, desc in cmds:
            host.register_command(name, aliases, fn, title=title, group='capas', description=desc)

    def _action(self, ico, text, slot, checkable=False, menu=False):
        a = QAction(icon(ico), text, self.iface.mainWindow())
        a.setToolTip(text)
        a.setStatusTip(text)
        a.setCheckable(checkable)
        if checkable:
            a.triggered.connect(lambda checked=False: slot(checked))
        else:
            a.triggered.connect(lambda *_: slot())
        self.toolbar.addAction(a)
        if menu:
            self.iface.addPluginToMenu(MENU, a)
        self.actions.append((a, menu))
        return a

    def _update_actions(self, *args):
        if self.ctrl is None or not self.actions:
            return                  # complemento ya descargado (aviso tardío de una señal)
        active = self.ctrl.active
        for a, menu in self.actions:
            if a not in (self.a_props, self.a_lw):
                a.setEnabled(active)
        self.a_prev.setEnabled(self.ctrl.can_previous())
        self.a_lw.setChecked(self.ctrl.lwdisplay)

    def unload(self):
        host = getattr(self, '_cad_host', None)
        if host is not None:
            try:
                host.unregister_commands('capas')
            except Exception:
                pass
            self._cad_host = None
        if self.pick_tool is not None:
            self.pick_tool.finish()
            self.pick_tool = None
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        for a, menu in self.actions:
            if menu:
                self.iface.removePluginMenu(MENU, a)
        self.actions = []
        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.ctrl is not None:
            for sig in (self.ctrl.changed, self.ctrl.attachedChanged):
                try:
                    sig.disconnect(self._update_actions)
                except (TypeError, RuntimeError):
                    pass
            self.ctrl.shutdown()
            self.ctrl = None

    # ------------------------------------------------------------ paleta
    def toggle_manager(self, checked=True):
        if self.dock is None:
            self.dock = LayerManagerDock(self.iface, self.ctrl, self.iface.mainWindow())
            self.iface.addDockWidget(qt('DockWidgetArea', 'RightDockWidgetArea'), self.dock)
            self.dock.setFloating(True)
            mw = self.iface.mainWindow().geometry()
            w, h = min(1100, mw.width() - 80), 440
            self.dock.resize(w, h)
            self.dock.move(mw.x() + (mw.width() - w) // 2, mw.y() + (mw.height() - h) // 2)
            self.dock.visibilityChanged.connect(self.a_props.setChecked)
        self.dock.setVisible(checked)
        if checked:
            self.dock.raise_()
            self.ctrl.refresh()

    def _toggle_lw(self, checked):
        self.ctrl.set_global('lwdisplay', bool(checked))

    # ------------------------------------------------------------ comandos con objetos
    def _pick(self, prompt, callback):
        """Designar un objeto en el mapa (si no hay selección previa)."""
        if not self.ctrl.active:
            self.ctrl.warn('Selecciona una capa vectorial en el panel Capas.')
            return
        if self.pick_tool is not None:
            self.pick_tool.finish()
        self.pick_tool = PickFeatureTool(self.iface, self.ctrl.layer, callback, prompt)
        self.iface.mapCanvas().setMapTool(self.pick_tool)
        self.ctrl.msg(prompt + ' (Esc para cancelar)', 'Info', 3)

    def _with_layers(self, fn, verb):
        names = self.ctrl.selected_layer_names() if self.ctrl.active else None
        if names:
            fn(sorted(names))
            return
        self._pick('Designe un objeto de la capa que desea %s' % verb,
                   lambda f: fn([self.ctrl.feature_layer(f)]))

    def cmd_laymcur(self):
        names = self.ctrl.selected_layer_names() if self.ctrl.active else None
        if names:
            if len(names) == 1:
                self.ctrl.set_current(next(iter(names)))
            else:
                self.ctrl.warn('Los objetos seleccionados están en varias capas.')
            return
        self._pick('Designe el objeto cuya capa será la actual',
                   lambda f: self.ctrl.set_current(self.ctrl.feature_layer(f)))

    def cmd_laymch(self):
        if not self.ctrl.active or not self.ctrl.has_selection():
            self.ctrl.warn('IGUALARCAPA: seleccione primero los objetos que desea cambiar.')
            return
        self._pick('Designe un objeto de la capa de destino',
                   lambda f: self.ctrl.assign_selection(self.ctrl.feature_layer(f)))

    def cmd_layiso(self):
        self._with_layers(self.ctrl.isolate, 'aislar')


__all__ = ['LayerPropertiesPlugin', 'Qt']
