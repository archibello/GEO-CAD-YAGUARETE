# -*- coding: utf-8 -*-
"""BLOQUE, INSERT, WBLOQUE y LIMPIA (bloques al estilo AutoCAD)."""

import math
import os

from qgis.PyQt.QtCore import QPointF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                                 QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                                 QLineEdit, QPushButton, QVBoxLayout, QWidget)
from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsProject

from . import blocks as B
from .commands import _DrawCommand, _key
from .compat import accepted_code, enum, exec_dialog, qt
from .editkit import EditCommand
from .units import InputError, parse_degrees, parse_distance

STYLE = """
QDialog { background: #3b4453; color: #e6e9ee; }
QLabel, QCheckBox, QGroupBox { color: #e6e9ee; }
QGroupBox { border: 1px solid #20252d; margin-top: 9px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
QComboBox, QLineEdit, QDoubleSpinBox { background: #262b34; color: #e6e9ee; border: 1px solid #20252d; padding: 2px 4px; }
QComboBox QAbstractItemView { background: #262b34; color: #e6e9ee; selection-background-color: #3d6a99; }
QPushButton { background: #4a5466; color: #e6e9ee; border: 1px solid #20252d; padding: 4px 12px; }
QPushButton:hover { background: #46536a; }
"""


def _btns(dlg):
    box = QDialogButtonBox()
    box.addButton(enum(QDialogButtonBox, 'StandardButton', 'Ok')).setText('Aceptar')
    box.addButton(enum(QDialogButtonBox, 'StandardButton', 'Cancel')).setText('Cancelar')
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


# ---------------------------------------------------------------- vista previa
class BlockPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.setMinimumSize(170, 150)

    def set_rows(self, rows):
        self.rows = rows or []
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#222730'))
        geoms = [r['lgeom'] for r in self.rows if r.get('lgeom') is not None]
        if not geoms:
            p.setPen(QColor('#8fa0b3'))
            p.drawText(self.rect(), qt('AlignmentFlag', 'AlignCenter'), 'Sin vista previa')
            p.end()
            return
        bb = QgsGeometry.collectGeometry(geoms).boundingBox()
        bb.combineExtentWith(0.0, 0.0)
        w, h = max(bb.width(), 1e-9), max(bb.height(), 1e-9)
        m = 12
        k = min((self.width() - 2 * m) / w, (self.height() - 2 * m) / h)
        ox = m + (self.width() - 2 * m - w * k) / 2 - bb.xMinimum() * k
        oy = self.height() - m - (self.height() - 2 * m - h * k) / 2 + bb.yMinimum() * k
        tr = lambda x, y: QPointF(ox + x * k, oy - y * k)  # noqa: E731
        p.setRenderHint(enum(QPainter, 'RenderHint', 'Antialiasing'))
        p.setPen(QPen(QColor('#e6e9ee'), 1.2))
        for g in geoms:
            parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            for part in parts:
                for a, b in zip(part, part[1:]):
                    p.drawLine(tr(a.x(), a.y()), tr(b.x(), b.y()))
        # punto base
        p.setPen(QPen(QColor('#ff5a4e'), 1.5))
        c = tr(0, 0)
        p.drawLine(QPointF(c.x() - 6, c.y()), QPointF(c.x() + 6, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 6), QPointF(c.x(), c.y() + 6))
        p.end()


# ---------------------------------------------------------------- diálogo Insertar
class InsertDialog(QDialog):
    def __init__(self, parent, mgr):
        super().__init__(parent)
        self.setWindowTitle('Insertar')
        self.setStyleSheet(STYLE)
        self.mgr = mgr
        self.library = {}           # nombre -> filas de una biblioteca externa
        self.lib_path = None
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel('Nombre:'))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(220)
        top.addWidget(self.combo, 1)
        b = QPushButton('Examinar...')
        b.setToolTip('Abrir una biblioteca de bloques (.gpkg creada con WBLOQUE)')
        b.clicked.connect(self._browse)
        top.addWidget(b)
        v.addLayout(top)
        self.lbl_src = QLabel('')
        v.addWidget(self.lbl_src)
        mid = QHBoxLayout()
        self.preview = BlockPreview()
        mid.addWidget(self.preview)
        right = QVBoxLayout()
        g1 = QGroupBox('Punto de inserción')
        l1 = QVBoxLayout(g1)
        chk = QCheckBox('Precisar en pantalla')
        chk.setChecked(True)
        chk.setEnabled(False)
        l1.addWidget(chk)
        right.addWidget(g1)
        g2 = QGroupBox('Escala')
        f2 = QFormLayout(g2)
        self.sx = self._spin(1.0)
        self.sy = self._spin(1.0)
        self.uniform = QCheckBox('Escala uniforme')
        self.uniform.setChecked(True)
        self.uniform.toggled.connect(lambda on: self.sy.setEnabled(not on))
        self.sy.setEnabled(False)
        f2.addRow('X:', self.sx)
        f2.addRow('Y:', self.sy)
        f2.addRow(self.uniform)
        right.addWidget(g2)
        g3 = QGroupBox('Rotación')
        f3 = QFormLayout(g3)
        self.rot = QLineEdit('0')
        self.rot.setToolTip("Admite 45, 45d30'15\", 50g, 0.78r")
        f3.addRow('Ángulo:', self.rot)
        right.addWidget(g3)
        self.explode = QCheckBox('Descomponer')
        right.addWidget(self.explode)
        right.addStretch()
        mid.addLayout(right)
        v.addLayout(mid)
        v.addWidget(_btns(self))
        self._fill()
        self.combo.currentIndexChanged.connect(self._changed)
        self._changed()

    def _spin(self, val):
        s = QDoubleSpinBox()
        s.setDecimals(4)
        s.setRange(-1e6, 1e6)
        s.setValue(val)
        return s

    def _fill(self, select=None):
        self.combo.blockSignals(True)
        self.combo.clear()
        for n in B.LIB.names():
            self.combo.addItem(n, ('project', n))
        for n in sorted(self.library):
            self.combo.addItem('%s  (biblioteca)' % n, ('library', n))
        self.combo.blockSignals(False)
        if select is not None:
            for i in range(self.combo.count()):
                if self.combo.itemData(i) == select:
                    self.combo.setCurrentIndex(i)

    def _browse(self):
        start = QgsProject.instance().homePath() or ''
        path, _ = QFileDialog.getOpenFileName(self, 'Biblioteca de bloques', start, 'Biblioteca (*.gpkg)')
        if not path:
            return
        self.library = B.read_library(path)
        self.lib_path = path
        first = sorted(self.library)[0] if self.library else None
        self._fill(('library', first) if first else None)
        self._changed()

    def _changed(self, *a):
        data = self.combo.currentData()
        if not data:
            self.preview.set_rows([])
            self.lbl_src.setText('No hay bloques definidos: créelos con BLOQUE o abra una biblioteca.')
            return
        src, name = data
        rows = B.LIB.rows(name) if src == 'project' else self.library.get(name, [])
        self.preview.set_rows(rows)
        self.lbl_src.setText('%d entidad(es)%s' % (len(rows), '  ·  ' + os.path.basename(self.lib_path)
                                                    if src == 'library' and self.lib_path else ''))

    def values(self):
        data = self.combo.currentData()
        if not data:
            return None
        src, name = data
        rot = parse_degrees(self.rot.text() or '0', self.mgr.units)
        if self.mgr.units.angdir_cw:
            rot = -rot
        sx = self.sx.value()
        sy = sx if self.uniform.isChecked() else self.sy.value()
        return {'source': src, 'name': name, 'rows': self.library.get(name) if src == 'library' else None,
                'sx': sx, 'sy': sy, 'rot': rot, 'explode': self.explode.isChecked()}


# ---------------------------------------------------------------- BLOQUE
class BlockCommand(EditCommand):
    """BLOQUE: nombre, punto base, objetos y qué hacer con ellos."""
    title = 'BLOQUE'

    def start(self):
        if B.is_block_layer(self.layer):
            self.cl.echo('No se pueden anidar bloques en esta versión: designe objetos de una capa de dibujo.')
            self.end()
            return
        self.pre = list(self.layer.selectedFeatureIds())
        self.selecting = False
        self.state = 'name'
        self.name = None
        self.prompt()

    def step_prompt(self):
        st = self.state
        self.text_mode = st == 'name'
        self.cl.raw_mode = self.text_mode
        if st == 'name':
            self.cl.set_prompt('Indique nombre de bloque o', [('?', '?')])
        elif st == 'redef':
            self.cl.set_prompt('El bloque "%s" ya existe. ¿Desea redefinirlo?' % self.name,
                               [('S', 'Sí'), ('N', 'No')], 'No')
        elif st == 'base':
            self.cl.set_prompt('Precise punto base de inserción')
        elif st == 'mode':
            self.cl.set_prompt('Objetos de origen', [('R', 'Retener'), ('C', 'Convertir en bloque'),
                                                     ('S', 'Suprimir')], 'Convertir en bloque')

    def base(self):
        return None

    def step_text(self, text):
        st, k = self.state, _key(text)
        if st == 'name':
            name = text.strip()
            if name == '?':
                names = B.LIB.names()
                self.cl.echo('Bloques definidos: %s' % (', '.join(names) if names else '(ninguno)'))
            elif not name:
                raise InputError('Indique un nombre.')
            elif any(c in B.INVALID_NAME for c in name) or len(name) > 80:
                raise InputError('Nombre de bloque no válido.')
            else:
                self.name = name
                self.state = 'redef' if name in B.LIB.names() else 'base'
        elif st == 'redef':
            if k in ('S', 'SI', 'SÍ', 'Y', 'YES'):
                self.state = 'base'
            elif k in ('N', 'NO'):
                self.state = 'name'
            else:
                raise InputError('Responda Sí o No.')
        elif st == 'mode':
            if k in ('R', 'RETENER', 'RETAIN'):
                self.finish('retain')
            elif k in ('C', 'CONVERTIR', 'CONVERT'):
                self.finish('convert')
            elif k in ('S', 'SUPRIMIR', 'D', 'DELETE'):
                self.finish('delete')
            else:
                raise InputError('Opción no válida.')
            return
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def step_point(self, p):
        if self.state != 'base':
            return
        self.base_pt = p
        self._set_last(p)
        self.cl.raw_mode = False
        if self.pre:
            self.sel = self.pre
            self.cl.echo('%d objeto(s) preseleccionado(s).' % len(self.sel))
            self._selection_done()
            return
        self.layer.removeSelection()
        self.selecting = True
        self.prompt()

    def step_enter(self):
        st = self.state
        if st == 'redef':
            self.state = 'name'
            self.prompt()
        elif st == 'mode':
            self.finish('convert')
        else:
            self.end()

    def after_selection(self):
        if not self.sel:
            self.cl.echo('No se designaron objetos.')
            self.end()
            return
        self.state = 'mode'
        self.prompt()

    def finish(self, mode):
        bx, by = self.base_pt.x(), self.base_pt.y()
        idx = self.layer.fields().indexOf('LAYER_CODE')
        entities = []
        for fid, g in self.geoms.items():
            lg = QgsGeometry(g)
            lg.translate(-bx, -by)
            code = ''
            if idx != -1:
                v = self.feats[fid].attribute(idx)
                code = '' if v is None else str(v)
            entities.append({'geom': lg, 'layer_code': code, 'src_layer': self.layer.id(),
                             'src_name': self.layer.name()})
        defs = B.defs_layer(self.mgr.iface, self.cl.echo, create=True)
        n = B.write_definition(defs, self.name, entities)
        msg = 'Bloque "%s" definido con %d entidad(es).' % (self.name, n)
        if mode in ('convert', 'delete'):
            self.layer.beginEditCommand('BLOQUE')
            for fid in self.geoms:
                self.layer.deleteFeature(fid)
            self.layer.endEditCommand()
            self.layer.triggerRepaint()
        if mode == 'convert':
            B.add_instance(self.mgr, self.name, self.base_pt, 1.0, 1.0, 0.0, self.cl.echo)
            msg += ' Objetos convertidos en una inserción.'
        elif mode == 'delete':
            msg += ' Objetos de origen suprimidos.'
        self.cl.echo(msg)
        self.end()

    def preview(self, cur):
        if self.selecting:
            return super().preview(cur)
        return [], False, [], []


# ---------------------------------------------------------------- INSERT
class InsertCommand(_DrawCommand):
    title = 'INSERT'

    def start(self):
        dlg = InsertDialog(self.mgr.iface.mainWindow(), self.mgr)
        if exec_dialog(dlg) != accepted_code():
            self.end()
            return
        try:
            v = dlg.values()
        except InputError as e:
            self.cl.echo(str(e))
            self.end()
            return
        if not v:
            self.end()
            return
        if v['source'] == 'library':
            # se copia la definición al proyecto (como al insertar desde DesignCenter)
            defs = B.defs_layer(self.mgr.iface, self.cl.echo, create=True)
            if v['name'] in B.LIB.names():
                self.cl.echo('El bloque "%s" ya existe en el proyecto: se usa la definición del proyecto.' % v['name'])
            else:
                B.write_definition(defs, v['name'], [{'geom': r['geom'], 'layer_code': r['layer_code'],
                                                      'src_layer': '', 'src_name': r['src_name']}
                                                     for r in v['rows'] if r['geom'] is not None])
        self.name, self.sx, self.sy, self.rot, self.explode = v['name'], v['sx'], v['sy'], v['rot'], v['explode']
        self.rows = B.LIB.rows(self.name)
        self.state = 'pt'
        self.prompt()

    def prompt(self):
        st = self.state
        if st == 'pt':
            self.cl.set_prompt('Precise punto de inserción o', [('E', 'Escala'), ('X', 'X'), ('Y', 'Y'),
                                                                ('R', 'Rotar')])
        elif st == 'scale':
            self.cl.set_prompt('Precise factor de escala XYZ', None, '%g' % self.sx)
        elif st == 'sx':
            self.cl.set_prompt('Precise factor de escala X', None, '%g' % self.sx)
        elif st == 'sy':
            self.cl.set_prompt('Precise factor de escala Y', None, '%g' % self.sy)
        elif st == 'rot':
            self.cl.set_prompt('Precise ángulo de rotación', None, '%g' % math.degrees(self.rot))

    def base(self):
        return None

    def snap_points(self):
        return []

    def on_point(self, p):
        if self.state != 'pt':
            return
        if self.explode:
            made, skipped = B.explode_rows(self.rows, p.x(), p.y(), self.sx, self.sy, self.rot,
                                           self.mgr.canvas.mapSettings().destinationCrs(),
                                           fallback=self.mgr.iface.activeLayer())
            msg = 'Bloque "%s" insertado descompuesto: %d objeto(s).' % (self.name, made)
            if skipped:
                msg += ' %d sin capa de destino compatible.' % skipped
            self.cl.echo(msg)
        else:
            B.add_instance(self.mgr, self.name, p, self.sx, self.sy, math.degrees(self.rot), self.cl.echo)
        self._set_last(p)
        self.end()

    def on_text(self, text):
        st, k = self.state, _key(text)
        u = self.mgr.units
        if st == 'pt' and k in ('E', 'ESCALA', 'S', 'SCALE'):
            self.state = 'scale'
        elif st == 'pt' and k == 'X':
            self.state = 'sx'
        elif st == 'pt' and k == 'Y':
            self.state = 'sy'
        elif st == 'pt' and k in ('R', 'ROTAR', 'ROTATE'):
            self.state = 'rot'
        elif st == 'scale':
            self.sx = self.sy = float(parse_distance(text))
            self.state = 'pt'
        elif st == 'sx':
            self.sx = float(parse_distance(text))
            self.state = 'pt'
        elif st == 'sy':
            self.sy = float(parse_distance(text))
            self.state = 'pt'
        elif st == 'rot':
            v = parse_degrees(text, u)
            self.rot = math.radians(-v if u.angdir_cw else v)
            self.state = 'pt'
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def on_enter(self):
        if self.state != 'pt':
            self.state = 'pt'
            self.prompt()
            return
        self.end()

    def escape(self):
        self.end()

    def preview(self, cur):
        return [], False, [], []

    def preview_geoms(self, cur):
        if self.state != 'pt' or cur is None:
            return None
        out = []
        for r in self.rows[:500]:
            g = r['lgeom'] if r['lgeom'] is not None else r['geom']
            if g is not None:
                out.append(B.place(g, cur.x(), cur.y(), self.sx, self.sy, self.rot))
        return out


# ---------------------------------------------------------------- WBLOQUE / LIMPIA
class WBlockDialog(QDialog):
    def __init__(self, parent, names):
        super().__init__(parent)
        self.setWindowTitle('Escribir bloque')
        self.setStyleSheet(STYLE)
        f = QFormLayout(self)
        self.combo = QComboBox()
        self.combo.addItems(names)
        self.chk_all = QCheckBox('Todos los bloques del proyecto')
        f.addRow('Bloque:', self.combo)
        f.addRow(self.chk_all)
        row = QHBoxLayout()
        home = QgsProject.instance().homePath() or os.path.expanduser('~')
        self.path = QLineEdit(os.path.join(home, 'biblioteca_bloques.gpkg'))
        b = QPushButton('...')
        b.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(b)
        f.addRow('Biblioteca:', row)
        f.addRow(QLabel('Si la biblioteca existe, el bloque se agrega o se reemplaza.'))
        f.addRow(_btns(self))

    def _browse(self):
        p, _ = QFileDialog.getSaveFileName(self, 'Biblioteca de bloques', self.path.text(), 'Biblioteca (*.gpkg)')
        if p:
            self.path.setText(p if p.lower().endswith('.gpkg') else p + '.gpkg')


def wblock(mgr):
    names = B.LIB.names()
    if not names:
        mgr.cmdline.echo('No hay bloques definidos en el proyecto.')
        return
    dlg = WBlockDialog(mgr.iface.mainWindow(), names)
    if exec_dialog(dlg) != accepted_code():
        return
    path = dlg.path.text().strip()
    todo = names if dlg.chk_all.isChecked() else [dlg.combo.currentText()]
    ok = 0
    for n in todo:
        if B.write_library(path, n, B.LIB.rows(n)):
            ok += 1
    mgr.cmdline.echo('%d bloque(s) escrito(s) en %s' % (ok, path))


def purge(mgr):
    defs = B.defs_layer()
    if defs is None:
        mgr.cmdline.echo('No hay bloques definidos.')
        return
    used = set()
    for lyr in QgsProject.instance().mapLayers().values():
        if B.is_block_layer(lyr):
            idx = lyr.fields().indexOf('NOMBRE')
            used |= {str(v) for v in lyr.uniqueValues(idx) if v is not None}
    unused = [n for n in B.LIB.names(defs) if n not in used]
    if not unused:
        mgr.cmdline.echo('No hay bloques sin usar.')
        return
    fids = [f.id() for f in defs.getFeatures() if str(f['NOMBRE']) in unused]
    defs.dataProvider().deleteFeatures(fids)
    B.refresh_instances()
    mgr.cmdline.echo('Bloques eliminados: %s' % ', '.join(unused))


__all__ = ['BlockCommand', 'InsertCommand', 'wblock', 'purge', 'QgsFeatureRequest', 'QgsPointXY']
