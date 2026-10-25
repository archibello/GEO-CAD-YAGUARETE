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
from .geomops import GeomError, gms_insercion
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
        # Fernando, 24/10/2026: en QGIS un bloque son copias de sus elementos en
        # las mismas capas, sin capas nuevas: INSERTAR siempre lo deja así.
        self.explode = QCheckBox('Descomponer')
        self.explode.setChecked(True)
        self.explode.setVisible(False)
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
        elif st == 'ref':
            self.cl.set_prompt('Precise punto de referencia P2 (escala y giro al insertar) o', None,
                               'ninguno')
        elif st == 'mode':
            self.cl.set_prompt('Objetos de origen', [('R', 'Retener'), ('S', 'Suprimir')], 'Retener')

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
                self.finish('retain')       # en QGIS el bloque son sus elementos en sus capas
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
        if self.state == 'base':
            self.base_pt = p
            self.ref_pt = None
            self._set_last(p)
            self.cl.raw_mode = False
            self.state = 'ref'          # P2 como en Bloques GMS de Fernando (3.45.0)
            self.prompt()
            return
        if self.state != 'ref':
            return
        if abs(p.x() - self.base_pt.x()) < 1e-12 and abs(p.y() - self.base_pt.y()) < 1e-12:
            self.cl.echo('P2 no puede coincidir con el punto base.')
            return
        self.ref_pt = p
        self._designar()

    def _designar(self):
        self.state = 'objs'
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
        elif st == 'ref':
            self._designar()            # sin P2: al insertar se usa el ancho del bloque
        elif st == 'mode':
            self.finish('retain')
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
        ref = None
        if getattr(self, 'ref_pt', None) is not None:
            ref = (self.ref_pt.x() - bx, self.ref_pt.y() - by)
        n = B.write_definition(defs, self.name, entities, ref=ref)
        msg = 'Bloque "%s" definido con %d entidad(es)%s.' % (self.name, n, ' y punto P2' if ref else '')
        if mode == 'delete':
            self.layer.beginEditCommand('BLOQUE')
            for fid in self.geoms:
                self.layer.deleteFeature(fid)
            self.layer.endEditCommand()
            self.layer.triggerRepaint()
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
        self.ref = B.LIB.reference(self.name)
        self.p1 = self.p2 = None
        self.perp = self.horiz = False
        self.etapa = 1
        self.state = 'pt'
        self.prompt()

    def prompt(self):
        st = self.state
        if st == 'pt':
            self.cl.set_prompt('Precise punto de inserción P1 o', [('E', 'Escala'), ('X', 'X'), ('Y', 'Y'),
                                                                   ('R', 'Rotar')])
        elif st == 'p2':
            self.cl.set_prompt('Precise P2 (escala y giro) o', None, 'escala y giro elegidos')
        elif st == 'sim':
            estado = '%s, %s' % ('perpendicular SÍ' if self.perp else 'perpendicular no',
                                 'horizonte SÍ' if self.horiz else 'horizonte no')
            if self.etapa == 1:
                txt = 'Simetría perpendicular (%s): clic alterna; Intro = siguiente' % estado
            else:
                txt = 'Simetría horizonte P1-P2 (%s): clic alterna; Intro = insertar' % estado
            self.cl.set_prompt(txt + ' o', [('S', 'Perpendicular'), ('H', 'Horizonte'), ('A', 'Aceptar')])
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
        if self.state == 'pt':
            self.p1 = p                       # Bloques GMS: P1, después P2
            self._set_last(p)
            self.state = 'p2'
            self.prompt()
            return
        if self.state == 'p2':
            if abs(p.x() - self.p1.x()) < 1e-12 and abs(p.y() - self.p1.y()) < 1e-12:
                self.cl.echo('P2 no puede coincidir con P1.')
                return
            self.p2 = p
            self.perp = self.horiz = False
            self.etapa = 1
            self.state = 'sim'
            self.prompt()
            return
        if self.state == 'sim':               # el clic alterna la simetría de la etapa
            if self.etapa == 1:
                self.perp = not self.perp
            else:
                self.horiz = not self.horiz
            self.prompt()

    def _colocacion(self, p2=None):
        """(x, y, escala X, escala Y, giro en radianes) de la inserción."""
        if p2 is None:
            return self.p1.x(), self.p1.y(), self.sx, self.sy, self.rot
        (x, y), ex, ey, rot = gms_insercion((self.p1.x(), self.p1.y()), (p2.x(), p2.y()), self.ref,
                                            self.perp, self.horiz)
        return x, y, ex, ey, rot

    def _insertar(self, p2=None):
        """Copias de los elementos del bloque en sus capas de origen (como Bloques
        GMS de Fernando): nunca se crea la capa «Bloques CAD» (3.45.0)."""
        x, y, sx, sy, rot = self._colocacion(p2)
        made, skipped = B.explode_rows(self.rows, x, y, sx, sy, rot,
                                       self.mgr.canvas.mapSettings().destinationCrs(),
                                       fallback=self.mgr.iface.activeLayer())
        msg = 'Bloque "%s" insertado: %d objeto(s) en sus capas.' % (self.name, made)
        if skipped:
            msg += ' %d sin capa de destino compatible.' % skipped
        self.cl.echo(msg)
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
        elif st == 'sim' and k in ('S', 'PERPENDICULAR', 'P'):
            self.perp = not self.perp
        elif st == 'sim' and k in ('H', 'HORIZONTE'):
            self.horiz = not self.horiz
        elif st == 'sim' and k in ('A', 'ACEPTAR', 'I', 'INSERTAR'):
            self._insertar(self.p2)
            return
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def on_enter(self):
        if self.state == 'p2':
            self._insertar()                  # sin P2: escala y giro elegidos (como antes)
            return
        if self.state == 'sim':
            if self.etapa == 1:
                self.etapa = 2
                self.prompt()
            else:
                self._insertar(self.p2)
            return
        if self.state != 'pt':
            self.state = 'pt'
            self.prompt()
            return
        self.end()

    def escape(self):
        self.end()

    def preview(self, cur):
        if self.state == 'p2' and cur is not None:
            return [], False, [self.p1, cur], []
        if self.state == 'sim':
            return [], False, [], [self.p1, self.p2]
        return [], False, [], []

    def preview_geoms(self, cur):
        if cur is None:
            return None
        try:
            if self.state == 'pt':
                x, y, sx, sy, rot = cur.x(), cur.y(), self.sx, self.sy, self.rot
            elif self.state == 'p2':
                x, y, sx, sy, rot = self._colocacion(cur)
            elif self.state == 'sim':
                x, y, sx, sy, rot = self._colocacion(self.p2)
            else:
                return None
        except GeomError:
            return None
        out = []
        for r in self.rows[:500]:
            g = r['lgeom'] if r['lgeom'] is not None else r['geom']
            if g is not None:
                out.append(B.place(g, x, y, sx, sy, rot))
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


# ---------------------------------------------------------------- BLOQUESGMS
def importar_gms(mgr, carpeta=None):
    """Trae como bloques de GeoCAD los bloques de Bloques GMS (.json) de la
    carpeta 'bloques' del proyecto, con su P2. No pisa bloques que ya existan
    ni toca los archivos. Devuelve la cantidad de bloques creados."""
    from . import gms_json
    if carpeta is None:
        fn = QgsProject.instance().fileName()
        inicio = os.path.join(os.path.dirname(fn), 'bloques') if fn else ''
        if not inicio or not os.path.isdir(inicio):
            inicio = QFileDialog.getExistingDirectory(mgr.iface.mainWindow(),
                                                      'Carpeta con los bloques de Bloques GMS', inicio or '')
        carpeta = inicio
    if not carpeta:
        return 0
    rutas = gms_json.archivos(carpeta)
    if not rutas:
        mgr.cmdline.echo('No hay bloques de Bloques GMS (.json) en %s.' % carpeta)
        return 0
    crs = mgr.canvas.mapSettings().destinationCrs().authid()
    existentes = set(B.LIB.names())
    defs = None
    hechos, avisos = 0, []
    for ruta in rutas:
        b = gms_json.leer(ruta)
        if b is None:
            avisos.append('%s: no es un bloque de Bloques GMS' % os.path.basename(ruta))
            continue
        if b['nombre'] in existentes:
            avisos.append('"%s" ya existe en el proyecto: no se pisa' % b['nombre'])
            continue
        if b['crs'] and crs and b['crs'] != crs:
            avisos.append('"%s" está en %s y el mapa en %s: no se trae' % (b['nombre'], b['crs'], crs))
            continue
        ents = []
        for w in b['wkts']:
            g = QgsGeometry.fromWkt(w)
            if g is not None and not g.isEmpty():
                ents.append({'geom': g, 'layer_code': '', 'src_layer': '', 'src_name': b['capa']})
        if not ents:
            avisos.append('"%s" no tiene geometrías' % b['nombre'])
            continue
        if defs is None:
            defs = B.defs_layer(mgr.iface, mgr.cmdline.echo, create=True)
        B.write_definition(defs, b['nombre'], ents, ref=b['p2'])
        existentes.add(b['nombre'])
        hechos += 1
    for a in avisos:
        mgr.cmdline.echo(a)
    mgr.cmdline.echo('%d bloque(s) de Bloques GMS traído(s) con su P2. Los archivos quedan como estaban.' % hechos)
    return hechos
