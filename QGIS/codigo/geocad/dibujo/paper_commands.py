# -*- coding: utf-8 -*-
"""TRAZAR (PLOT), PRESENTACION (LAYOUT), VENTANAS (MVIEW) y pestañas Modelo / Presentaciones."""

import os

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                                 QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                                 QLabel, QLineEdit, QMenu, QPushButton, QRadioButton, QSpinBox,
                                 QTabBar, QVBoxLayout)
from qgis.core import QgsProject, QgsRectangle

from . import paper as PP
from .commands import _DrawCommand, _key
from .compat import enum, exec_dialog, exec_menu, qt
from .settings import get_setting, set_setting
from .units import InputError

STYLE = """
QDialog { background: #3b4453; color: #e6e9ee; }
QLabel, QCheckBox, QRadioButton, QGroupBox { color: #e6e9ee; }
QGroupBox { border: 1px solid #20252d; margin-top: 9px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
QComboBox, QLineEdit, QSpinBox { background: #262b34; color: #e6e9ee; border: 1px solid #20252d; padding: 2px 4px; }
QComboBox QAbstractItemView { background: #262b34; color: #e6e9ee; selection-background-color: #3d6a99; }
QPushButton { background: #4a5466; color: #e6e9ee; border: 1px solid #20252d; padding: 4px 12px; }
QPushButton:hover { background: #46536a; }
"""
PICK_WINDOW = 2          # código de retorno: "Ventana <" (designar en el modelo)


def _btns(dlg, ok_text='Aceptar'):
    box = QDialogButtonBox()
    box.addButton(enum(QDialogButtonBox, 'StandardButton', 'Ok')).setText(ok_text)
    box.addButton(enum(QDialogButtonBox, 'StandardButton', 'Cancel')).setText('Cancelar')
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


def _combo(items, current=None, editable=False):
    c = QComboBox()
    c.setEditable(editable)
    for it in items:
        if isinstance(it, tuple):
            c.addItem(it[1], it[0])
        else:
            c.addItem(it, it)
    if current is not None:
        i = c.findData(current)
        if i < 0:
            i = c.findText(str(current))
        if i >= 0:
            c.setCurrentIndex(i)
        elif editable:
            c.setEditText(str(current))
    return c


def _rect_text(r):
    return '%.2f, %.2f  →  %.2f, %.2f' % (r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()) if r else '(sin definir)'


# ==========================================================================
class PreviewDialog(QDialog):
    """Vista preliminar dentro de QGIS: la hoja sobre fondo gris, con zoom."""

    def __init__(self, parent, image, title):
        super().__init__(parent)
        from qgis.PyQt.QtGui import QPixmap
        from qgis.PyQt.QtWidgets import QScrollArea
        self.setWindowTitle('Vista preliminar - ' + title)
        self.resize(1000, 760)
        self.pix = QPixmap.fromImage(image)
        self.zoom = 1.0
        v = QVBoxLayout(self)
        self.area = QScrollArea()
        self.area.setStyleSheet('QScrollArea { background: #5a6070; }')
        self.area.setAlignment(qt('AlignmentFlag', 'AlignCenter'))
        self.lbl = QLabel()
        self.lbl.setStyleSheet('background: white; border: 1px solid #222;')
        self.area.setWidget(self.lbl)
        v.addWidget(self.area, 1)
        row = QHBoxLayout()
        for text, f in (('Zoom +', 1.25), ('Zoom −', 0.8)):
            b = QPushButton(text)
            b.clicked.connect(lambda *_, f=f: self._zoom(self.zoom * f))
            row.addWidget(b)
        b = QPushButton('Ajustar')
        b.clicked.connect(self._fit)
        row.addWidget(b)
        row.addStretch()
        bp = QPushButton('Trazar')
        bp.clicked.connect(self.accept)
        bc = QPushButton('Cerrar')
        bc.clicked.connect(self.reject)
        row.addWidget(bp)
        row.addWidget(bc)
        v.addLayout(row)
        self._fit()

    def _fit(self):
        vw = max(200, self.area.viewport().width() - 20) if self.isVisible() else 960
        vh = max(200, self.area.viewport().height() - 20) if self.isVisible() else 680
        z = min(vw / max(1, self.pix.width()), vh / max(1, self.pix.height()))
        self._zoom(z)

    def _zoom(self, z):
        self.zoom = max(0.05, min(z, 8.0))
        w, h = int(self.pix.width() * self.zoom), int(self.pix.height() * self.zoom)
        self.lbl.setPixmap(self.pix.scaled(w, h, qt('AspectRatioMode', 'KeepAspectRatio'),
                                           qt('TransformationMode', 'SmoothTransformation')))
        self.lbl.resize(w, h)


class PlotDialog(QDialog):
    """Trazar - Modelo / Presentación (como el diálogo de AutoCAD)."""

    def __init__(self, parent, window, preset_layout=None, on_preview=None):
        super().__init__(parent)
        self.setWindowTitle('Trazar')
        self.setStyleSheet(STYLE)
        self.window = window
        self.on_preview = on_preview
        g = QGridLayout(self)

        dev = QGroupBox('Impresora/trazador')
        f = QFormLayout(dev)
        items = [('PDF', 'DWG To PDF  →  archivo PDF'), ('PNG', 'Imagen PNG')] + [(p, p) for p in PP.printers()]
        self.device = _combo(items, get_setting('plot/device', 'PDF', str))
        f.addRow('Nombre:', self.device)
        self.open_after = QCheckBox('Abrir el archivo al terminar')
        self.open_after.setChecked(get_setting('plot/open', True, bool))
        f.addRow(self.open_after)
        g.addWidget(dev, 0, 0, 1, 2)

        pap = QGroupBox('Tamaño de papel')
        f = QFormLayout(pap)
        self.paper = _combo(PP.PAPER_ORDER, get_setting('plot/paper', PP.PAPER_ORDER[1], str))
        f.addRow(self.paper)
        g.addWidget(pap, 1, 0)

        ori = QGroupBox('Orientación del dibujo')
        h = QVBoxLayout(ori)
        self.portrait = QRadioButton('Vertical')
        self.landscape = QRadioButton('Horizontal')
        (self.landscape if get_setting('plot/landscape', True, bool) else self.portrait).setChecked(True)
        h.addWidget(self.portrait)
        h.addWidget(self.landscape)
        g.addWidget(ori, 1, 1)

        area = QGroupBox('Área de trazado')
        f = QFormLayout(area)
        items = [('window', 'Ventana'), ('extents', 'Extensión'), ('display', 'Pantalla')] + \
                [('layout:' + l.name(), 'Presentación: ' + l.name()) for l in PP.layouts()]
        default = ('layout:' + preset_layout) if preset_layout else get_setting('plot/area', 'display', str)
        self.area = _combo(items, default)
        row = QHBoxLayout()
        row.addWidget(self.area, 1)
        b = QPushButton('Ventana <')
        b.setToolTip('Designar la ventana en el espacio modelo')
        b.clicked.connect(lambda: self.done(PICK_WINDOW))
        row.addWidget(b)
        f.addRow('Qué trazar:', row)
        self.lbl_win = QLabel(_rect_text(window))
        f.addRow('Ventana:', self.lbl_win)
        g.addWidget(area, 2, 0)

        sc = QGroupBox('Escala de trazado')
        f = QFormLayout(sc)
        self.scale = _combo(PP.SCALES, get_setting('plot/scale', PP.SCALES[0], str), editable=True)
        f.addRow('Escala:', self.scale)
        f.addRow(QLabel('1 mm del papel = N mm del dibujo (unidades del SRC en metros).'))
        g.addWidget(sc, 2, 1)

        st = QGroupBox('Tabla de estilos de trazado (asignación de plumillas)')
        f = QFormLayout(st)
        self.ctb = _combo(PP.CTB, get_setting('plot/ctb', 'monochrome', str))
        self.lw = QCheckBox('Trazar grosores de línea')
        self.lw.setChecked(get_setting('plot/lw', True, bool))
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 1200)
        self.dpi.setValue(get_setting('plot/dpi', 300, int))
        f.addRow(self.ctb)
        f.addRow(self.lw)
        f.addRow('Calidad (ppp):', self.dpi)
        g.addWidget(st, 3, 0, 1, 2)

        bottom = QHBoxLayout()
        pv = QPushButton('Vista preliminar...')
        pv.clicked.connect(self._preview)
        bottom.addWidget(pv)
        bottom.addStretch()
        bottom.addWidget(_btns(self))
        g.addLayout(bottom, 4, 0, 1, 2)
        self.area.currentIndexChanged.connect(self._area_changed)
        self._area_changed()

    def _area_changed(self, *a):
        is_layout = str(self.area.currentData()).startswith('layout:')
        for w in (self.paper, self.portrait, self.landscape, self.scale):
            w.setEnabled(not is_layout)

    def values(self):
        v = {'device': self.device.currentData(), 'paper': self.paper.currentData(),
             'landscape': self.landscape.isChecked(), 'area': self.area.currentData(),
             'scale': PP.parse_scale(self.scale.currentText()), 'scale_text': self.scale.currentText(),
             'ctb': self.ctb.currentData(), 'lw': self.lw.isChecked(), 'dpi': self.dpi.value(),
             'open': self.open_after.isChecked()}
        for k, sk in (('device', 'device'), ('paper', 'paper'), ('landscape', 'landscape'), ('area', 'area'),
                      ('scale_text', 'scale'), ('ctb', 'ctb'), ('lw', 'lw'), ('dpi', 'dpi'), ('open', 'open')):
            if not (k == 'area' and str(v[k]).startswith('layout:')):
                set_setting('plot/' + sk, v[k])
        return v

    def _preview(self):
        if self.on_preview is None:
            return
        from qgis.PyQt.QtWidgets import QMessageBox
        try:
            image, title = self.on_preview(self.values())
            if image is None or image.isNull():
                raise InputError('No se pudo generar la vista preliminar.')
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, 'Vista preliminar', str(e))
            return
        if exec_dialog(PreviewDialog(self, image, title)) == 1:
            self.accept()             # "Trazar" desde la vista preliminar


# ==========================================================================
class LayoutDialog(QDialog):
    """Nueva presentación (PRESENTACION) o nueva ventana (VENTANAS)."""

    def __init__(self, parent, window, mview=False):
        super().__init__(parent)
        self.mview = mview
        self.setWindowTitle('Nueva ventana gráfica' if mview else 'Nueva presentación')
        self.setStyleSheet(STYLE)
        self.window = window
        f = QFormLayout(self)
        if mview:
            self.layout_combo = _combo([l.name() for l in PP.layouts()])
            f.addRow('Presentación:', self.layout_combo)
        else:
            self.name = QLineEdit(PP.unique_layout_name())
            f.addRow('Nombre:', self.name)
            self.paper = _combo(PP.PAPER_ORDER, get_setting('layout/paper', PP.PAPER_ORDER[1], str))
            f.addRow('Hoja:', self.paper)
            self.landscape = QCheckBox('Horizontal')
            self.landscape.setChecked(get_setting('layout/landscape', True, bool))
            f.addRow('Orientación:', self.landscape)
            self.tb = QCheckBox('Recuadro y cajetín (proyecto, plano, escala, fecha, dibujó)')
            self.tb.setChecked(True)
            f.addRow(self.tb)
            self.north = QCheckBox('Norte y escala gráfica')
            self.north.setChecked(True)
            f.addRow(self.north)
            self.ctb = _combo(PP.CTB, get_setting('plot/ctb', 'monochrome', str))
            f.addRow('Estilo de trazado:', self.ctb)
        self.scale = _combo(PP.SCALES, get_setting('layout/scale', '1:100', str), editable=True)
        f.addRow('Escala de la ventana:', self.scale)
        row = QHBoxLayout()
        self.area = _combo([('display', 'Pantalla actual'), ('extents', 'Extensión'), ('window', 'Ventana')],
                           'window' if window else 'display')
        row.addWidget(self.area, 1)
        b = QPushButton('Ventana <')
        b.clicked.connect(lambda: self.done(PICK_WINDOW))
        row.addWidget(b)
        f.addRow('Contenido:', row)
        f.addRow('Ventana:', QLabel(_rect_text(window)))
        self.open_it = QCheckBox('Abrir la presentación')
        self.open_it.setChecked(True)
        f.addRow(self.open_it)
        f.addRow(_btns(self))

    def values(self):
        v = {'scale': PP.parse_scale(self.scale.currentText()), 'area': self.area.currentData(),
             'open': self.open_it.isChecked()}
        set_setting('layout/scale', self.scale.currentText())
        if self.mview:
            v['layout'] = self.layout_combo.currentText()
        else:
            v.update(name=self.name.text().strip() or PP.unique_layout_name(), paper=self.paper.currentData(),
                     landscape=self.landscape.isChecked(), title_block=self.tb.isChecked(),
                     north=self.north.isChecked(), ctb=self.ctb.currentData())
            set_setting('layout/paper', v['paper'])
            set_setting('layout/landscape', v['landscape'])
        return v


# ==========================================================================
class _WindowPickCommand(_DrawCommand):
    """Base: diálogo + 'Ventana <' (designar dos esquinas en el modelo y volver al diálogo)."""

    def start(self):
        self.window = getattr(self.mgr, 'last_plot_window', None)
        self.corner = None
        self.state = 'dialog'
        self.show_dialog()

    def prompt(self):
        if self.state == 'w1':
            self.cl.set_prompt('Precise primera esquina')
        elif self.state == 'w2':
            self.cl.set_prompt('Precise esquina opuesta')

    def base(self):
        return None

    def on_point(self, p):
        if self.state == 'w1':
            self.corner = p
            self.state = 'w2'
            self.prompt()
        elif self.state == 'w2':
            r = QgsRectangle(self.corner, p)
            r.normalize()
            if r.width() <= 0 or r.height() <= 0:
                raise InputError('La ventana no puede tener ancho o alto nulo.')
            self.window = r
            self.mgr.last_plot_window = r
            self.state = 'dialog'
            self.show_dialog()

    def on_text(self, text):
        self._resolve_and_apply(text)

    def on_enter(self):
        self.end()

    def escape(self):
        self.end()

    def preview(self, cur):
        if self.state == 'w2' and cur is not None:
            a = self.corner
            rect = [a, type(a)(cur.x(), a.y()), cur, type(a)(a.x(), cur.y()), a]
            return rect, False, [], []
        return [], False, [], []

    def pick(self):
        self.state = 'w1'
        self.prompt()

    def extent_for(self, area):
        c = self.mgr.canvas
        if area == 'window':
            if self.window is None:
                raise InputError('Designe la ventana con el botón "Ventana <".')
            return self.window
        if area == 'extents':
            return c.fullExtent()
        return c.extent()


class PlotCommand(_WindowPickCommand):
    title = 'TRAZAR'

    def show_dialog(self):
        preset = getattr(self.mgr, 'plot_preset', None)
        self.mgr.plot_preset = None
        dlg = PlotDialog(self.mgr.iface.mainWindow(), self.window, preset, self._preview)
        res = exec_dialog(dlg)
        if res == PICK_WINDOW:
            self.pick()
            return
        if res != 1:
            self.end()
            return
        try:
            self.plot(dlg.values())
        except InputError as e:
            self.cl.echo(str(e))
        self.end()

    def _layout_for(self, v):
        area = str(v['area'])
        if area.startswith('layout:'):
            lay = PP.find_layout(area[7:])
            if lay is None:
                raise InputError('La presentación ya no existe.')
            return lay, False
        ext = self.extent_for(area)
        return PP.model_layout(self.mgr.iface, v['paper'], v['landscape'], ext, v['scale'], v['ctb'], v['lw']), True

    def _preview(self, v):
        lay, temp = self._layout_for(v)
        return PP.render_preview(lay, v['ctb'], v['lw'], dpi=96), lay.name()

    def plot(self, v):
        lay, temp = self._layout_for(v)
        dev = v['device']
        path = None
        if dev in ('PDF', 'PNG'):
            ext = '.pdf' if dev == 'PDF' else '.png'
            home = QgsProject.instance().homePath() or os.path.expanduser('~')
            base = QgsProject.instance().baseName() or 'dibujo'
            name = '%s-%s%s' % (base, lay.name(), ext)
            path, _ = QFileDialog.getSaveFileName(self.mgr.iface.mainWindow(), 'Guardar archivo de trazado',
                                                  os.path.join(home, name),
                                                  'PDF (*.pdf)' if dev == 'PDF' else 'Imagen PNG (*.png)')
            if not path:
                self.cl.echo('*Cancelar*')
                return
        ok, where = PP.export(lay, dev, path, v['dpi'], v['ctb'], v['lw'])
        if ok:
            self.cl.echo('Trazado terminado: %s' % where)
            if path and v.get('open'):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            self.cl.echo('No se pudo completar el trazado.')


class LayoutCommand(_WindowPickCommand):
    """PRESENTACION: [Nueva/Abrir/Copiar/Renombrar/Suprimir/?]."""
    title = 'PRESENTACION'
    mview = False

    def start(self):
        self.window = getattr(self.mgr, 'last_plot_window', None)
        self.corner = None
        self.state = 'opt'
        self.target = None
        self.prompt()

    def prompt(self):
        st = self.state
        self.text_mode = st in ('name', 'newname')
        self.cl.raw_mode = self.text_mode
        if st == 'opt':
            self.cl.set_prompt('Indique opción de presentación',
                               [('N', 'Nueva'), ('A', 'Abrir'), ('C', 'Copiar'), ('R', 'Renombrar'),
                                ('S', 'Suprimir'), ('?', '?')], 'Nueva')
        elif st == 'name':
            self.cl.set_prompt('Indique nombre de la presentación')
        elif st == 'newname':
            self.cl.set_prompt('Indique nuevo nombre')
        else:
            super().prompt()

    def on_text(self, text):
        st, k = self.state, _key(text)
        if st == 'opt':
            if k in ('N', 'NUEVA', 'NEW'):
                self.state = 'dialog'
                self.show_dialog()
                return
            if k == '?':
                names = [l.name() for l in PP.layouts()]
                self.cl.echo('Presentaciones: %s' % (', '.join(names) if names else '(ninguna)'))
            elif k in ('A', 'ABRIR', 'O', 'OPEN', 'C', 'COPIAR', 'COPY', 'R', 'RENOMBRAR', 'RENAME',
                       'S', 'SUPRIMIR', 'D', 'DELETE'):
                self.action = k[0]
                self.state = 'name'
            else:
                raise InputError('Opción no válida.')
        elif st == 'name':
            lay = PP.find_layout(text.strip())
            if lay is None:
                raise InputError('No existe la presentación "%s".' % text.strip())
            self.target = lay
            if self.action in ('A', 'O'):
                self.mgr.iface.openLayoutDesigner(lay)
                self.end()
                return
            if self.action in ('S', 'D'):
                PP.layout_manager().removeLayout(lay)
                self.cl.echo('Presentación "%s" suprimida.' % text.strip())
                self.end()
                return
            self.state = 'newname'
        elif st == 'newname':
            new = text.strip()
            if not new or PP.find_layout(new):
                raise InputError('Nombre vacío o ya existente.')
            if self.action == 'R':
                self.target.setName(new)
                self.cl.echo('Presentación renombrada a "%s".' % new)
            else:
                PP.layout_manager().duplicateLayout(self.target, new)
                self.cl.echo('Presentación copiada como "%s".' % new)
            self.end()
            return
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def on_enter(self):
        if self.state == 'opt':
            self.state = 'dialog'
            self.show_dialog()
            return
        self.end()

    def show_dialog(self):
        dlg = LayoutDialog(self.mgr.iface.mainWindow(), self.window, self.mview)
        if self.mview and not PP.layouts():
            self.cl.echo('No hay presentaciones: cree una con PRESENTACION.')
            self.end()
            return
        res = exec_dialog(dlg)
        if res == PICK_WINDOW:
            self.pick()
            return
        if res != 1:
            self.end()
            return
        try:
            v = dlg.values()
            ext = self.extent_for(v['area'])
            if self.mview:
                lay = PP.find_layout(v['layout'])
                PP.add_viewport(self.mgr.iface, lay, ext, v['scale'])
                self.cl.echo('Ventana gráfica agregada a "%s".' % lay.name())
            else:
                lay = PP.create_layout(self.mgr.iface, v['name'], v['paper'], v['landscape'], ext, v['scale'],
                                       v['title_block'], v['north'], v['ctb'])
                self.cl.echo('Presentación "%s" creada.' % lay.name())
            if v['open']:
                self.mgr.iface.openLayoutDesigner(lay)
        except InputError as e:
            self.cl.echo(str(e))
        self.end()


class MViewCommand(LayoutCommand):
    title = 'VENTANAS'
    mview = True

    def start(self):
        self.window = getattr(self.mgr, 'last_plot_window', None)
        self.corner = None
        self.state = 'dialog'
        self.show_dialog()


# ==========================================================================
class MVLockCommand(_DrawCommand):
    """BLOQVENT: bloquea o desbloquea las ventanas de una presentación (VENTANAS > Bloquear)."""
    title = 'BLOQVENT'

    def start(self):
        self.state = 'mode'
        self.on = True
        self.prompt()

    def prompt(self):
        if self.state == 'mode':
            self.cl.set_prompt('Bloquear ventanas', [('A', 'Activar'), ('D', 'Desactivar')], 'Activar')
        else:
            names = [l.name() for l in PP.layouts()]
            self.cl.set_prompt('Presentación (%s) o' % ', '.join(names), [('T', 'Todas')],
                               names[0] if len(names) == 1 else 'Todas')

    def base(self):
        return None

    def on_point(self, p):
        pass

    def on_text(self, text):
        k = _key(text)
        if self.state == 'mode':
            if k in ('A', 'ACTIVAR', 'ON', 'SI', 'SÍ', 'BLOQUEAR'):
                self.on = True
            elif k in ('D', 'DESACTIVAR', 'OFF', 'NO', 'DESBLOQUEAR'):
                self.on = False
            else:
                raise InputError('Escriba A (Activar) o D (Desactivar).')
            self._after_mode()
            return
        if k in ('T', 'TODAS', 'ALL', '*'):
            self._apply(PP.layouts())
            return
        lay = PP.find_layout(text.strip()) or next(
            (l for l in PP.layouts() if l.name().upper() == text.strip().upper()), None)
        if lay is None:
            raise InputError('No existe la presentación "%s".' % text.strip())
        self._apply([lay])

    def _after_mode(self):
        lays = PP.layouts()
        if not lays:
            self.cl.echo('No hay presentaciones.')
            self.end()
            return
        if len(lays) == 1:
            self._apply(lays)
            return
        self.state = 'layout'
        self.prompt()

    def on_enter(self):
        if self.state == 'mode':
            self._after_mode()
        else:
            self._apply(PP.layouts())

    def _apply(self, lays):
        canvas = self.mgr.canvas
        for lay in lays:
            n = PP.lock_layout(lay, self.on, canvas)
            self.cl.echo('%s: %d ventana(s) %s.' % (lay.name(), n, 'bloqueada(s)' if self.on else 'desbloqueada(s)'))
        try:
            from qgis.utils import plugins
            tabs = getattr(plugins.get('Dibujo_CAD'), 'layout_tabs', None)
            if tabs is not None:
                tabs.refresh()
        except Exception:  # noqa: BLE001
            pass
        self.end()

    def escape(self):
        self.end()

    def preview(self, cur):
        return [], False, [], []


# ==========================================================================
class LayoutTabs(QTabBar):
    """Pestañas Modelo | Presentaciones | + (como en la parte inferior de AutoCAD)."""

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.setDocumentMode(True)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setContextMenuPolicy(qt('ContextMenuPolicy', 'CustomContextMenu'))
        self.customContextMenuRequested.connect(self._menu)
        self.currentChanged.connect(self._changed)
        self.setStyleSheet('QTabBar::tab { padding: 3px 14px; } QTabBar::tab:selected { font-weight: bold; }')
        # Conexiones a métodos (no lambdas) para poder desconectarlas al descargar el
        # complemento: si quedan vivas, QGIS llama a una pestaña ya destruida.
        self._connected = []
        mgr = PP.layout_manager()
        for sig in ('layoutAdded', 'layoutRemoved', 'layoutRenamed'):
            try:
                s = getattr(mgr, sig)
                s.connect(self._on_layouts_changed)
                self._connected.append(s)
            except Exception:  # noqa: BLE001
                pass
        self.refresh()

    def disconnect_all(self, *args):
        self._unwatch_layouts()
        for s in getattr(self, '_connected', []):
            try:
                s.disconnect(self._on_layouts_changed)
            except (TypeError, RuntimeError):
                pass
        self._connected = []

    def _on_layouts_changed(self, *args):
        self.refresh()

    # -- papel blanco en las ventanas de todas las presentaciones (también las creadas a mano)
    def _watch_layouts(self):
        from qgis.PyQt.QtCore import QTimer
        watched = getattr(self, '_watched_layouts', None)
        if watched is None:
            watched = self._watched_layouts = {}
        for l in PP.layouts():
            try:
                key = id(l)
                if key in watched:
                    continue
                PP.fix_layout_backgrounds(l)
                cb = (lambda *a, lay=l: QTimer.singleShot(0, lambda: PP.fix_layout_backgrounds(lay)))
                l.itemAdded.connect(cb)
                watched[key] = (l, cb)
            except (AttributeError, RuntimeError, TypeError):
                pass

    def _unwatch_layouts(self):
        for l, cb in getattr(self, '_watched_layouts', {}).values():
            try:
                l.itemAdded.disconnect(cb)
            except (TypeError, RuntimeError):
                pass
        self._watched_layouts = {}

    def _alive(self):
        try:
            from qgis.PyQt import sip
        except ImportError:
            import sip
        try:
            return not sip.isdeleted(self)
        except Exception:  # noqa: BLE001
            return True

    def refresh(self, *args):
        if not self._alive():
            self.disconnect_all()
            return
        try:
            self._watch_layouts()
        except Exception:  # noqa: BLE001
            pass
        self.blockSignals(True)
        while self.count():
            self.removeTab(0)
        self.addTab('Modelo')
        for l in PP.layouts():
            i = self.addTab(l.name())
            if PP.is_layout_locked(l):
                try:
                    from qgis.core import QgsApplication
                    self.setTabIcon(i, QgsApplication.getThemeIcon('/locked.svg'))
                except Exception:  # noqa: BLE001
                    pass
                self.setTabToolTip(i, 'Ventanas bloqueadas (clic derecho > Desbloquear ventanas)')
        self.addTab('+')
        self.setTabToolTip(self.count() - 1, 'Nueva presentación (PRESENTACION)')
        self.setCurrentIndex(0)
        self.blockSignals(False)

    def _changed(self, i):
        if i <= 0:
            return
        name = self.tabText(i)
        self.blockSignals(True)
        self.setCurrentIndex(0)          # el mapa principal es siempre el espacio modelo
        self.blockSignals(False)
        if i == self.count() - 1:
            self.plugin.run_command('PRESENTACION')
            return
        lay = PP.find_layout(name)
        if lay is not None:
            self.plugin.iface.openLayoutDesigner(lay)

    def _menu(self, pos):
        i = self.tabAt(pos)
        if i < 0 or i == self.count() - 1:
            return
        m = QMenu(self)
        name = self.tabText(i)
        if i == 0:
            a = m.addAction('Trazar el modelo...')
            a.triggered.connect(lambda *_: self.plugin.run_command('TRAZAR'))
        else:
            locked = PP.is_layout_locked(PP.find_layout(name)) if PP.find_layout(name) else False
            for text, fn in (('Abrir', lambda: self.plugin.iface.openLayoutDesigner(PP.find_layout(name))),
                             ('Trazar...', lambda: self._plot(name)),
                             ('Desbloquear ventanas' if locked else 'Bloquear ventanas',
                              lambda: self._lock(name, not locked)),
                             ('Renombrar...', lambda: self._rename(name)),
                             ('Copiar', lambda: self._copy(name)),
                             ('Suprimir', lambda: self._delete(name))):
                a = m.addAction(text)
                a.triggered.connect(lambda *_, fn=fn: fn())
            m.addSeparator()
        a = m.addAction('Nueva presentación...')
        a.triggered.connect(lambda *_: self.plugin.run_command('PRESENTACION'))
        exec_menu(m, self.mapToGlobal(pos))

    def _lock(self, name, on):
        lay = PP.find_layout(name)
        if lay is None:
            return
        n = PP.lock_layout(lay, on, self.plugin.iface.mapCanvas())
        self.plugin.cmdline.echo('%s: %d ventana(s) %s.' % (name, n, 'bloqueada(s)' if on else 'desbloqueada(s)'))
        self.refresh()

    def _plot(self, name):
        self.plugin.mgr.plot_preset = name
        self.plugin.run_command('TRAZAR')

    def _rename(self, name):
        lay = PP.find_layout(name)
        new, ok = QInputDialog.getText(self, 'Renombrar presentación', 'Nuevo nombre:', text=name)
        if ok and new.strip() and not PP.find_layout(new.strip()):
            lay.setName(new.strip())
            self.refresh()

    def _copy(self, name):
        lay = PP.find_layout(name)
        PP.layout_manager().duplicateLayout(lay, PP.unique_layout_name(name + ' copia '))
        self.refresh()

    def _delete(self, name):
        lay = PP.find_layout(name)
        if lay is not None:
            PP.layout_manager().removeLayout(lay)
            self.refresh()


__all__ = ['PlotCommand', 'LayoutCommand', 'MViewCommand', 'LayoutTabs']
