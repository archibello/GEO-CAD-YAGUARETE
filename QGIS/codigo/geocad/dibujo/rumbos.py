# -*- coding: utf-8 -*-
"""RUMBOS (RB, GMS): poligonal por rumbos, los dos Digitalizadores GMS de
Fernando en una orden de Dibujo (3.43.0).

    Precise primer punto del tramo base:
    Precise segundo punto del tramo base:
    Precise tramo distancia<ángulo o [Ángulo/Modo/Base/Cerrar/desHacer]:

- El tramo base A-B (dos clics, con referencias) da la dirección del primer
  ángulo. Base = No (por defecto, como Líneas GMS): no se dibuja; Base = Sí
  (como el Continuo): es el primer tramo.
- Cada tramo: 25.4<91d30'15" . Ángulo Interior (180 = sigue derecho) o
  Deflexión (0 = sigue derecho, + a la izquierda). Siempre valen 30dI / 30dD
  (deflexión), los rumbos N45d30'E y '<<' (absoluto). También un clic.
- Modo Polilínea (un objeto; en capas de polígonos se cierra) o Tramos (un
  objeto por tramo, como Líneas GMS). Se elige antes del primer tramo.
- No toca la tabla de la capa ni la guarda: la longitud de cada tramo y la
  acumulada se ven en la línea de comandos (Fernando, 24/10/2026).
"""

import math

from qgis.core import QgsPointXY

from .commands import OPT_CLOSE, OPT_UNDO, _DrawCommand, _key
from .settings import get_setting, set_setting
from .units import InputError, format_length, tramo_rumbo

OPT_ANG = ('A', 'ANGULO', 'ÁNGULO', 'ANGLE')
OPT_MODO = ('M', 'MODO', 'MODE')
OPT_BASE = ('B', 'BASE')


def _xy(p):
    return (p.x(), p.y())


class RumbosCommand(_DrawCommand):
    title = 'RUMBOS'

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.angulo = 'deflexion' if get_setting('rumbos_angulo', 'interior', str) == 'deflexion' else 'interior'
        self.tramos = get_setting('rumbos_tramos', False, bool) and kind == 'line'
        self.con_base = get_setting('rumbos_base', False, bool)
        self.marks = []
        self.largo = 0.0

    # ------------------------------------------------------------ ciclo
    def start(self):
        self.cl.echo('Parámetros actuales: Ángulo = %s  Modo = %s  Base = %s'
                     % (self._ang_txt(), self._modo_txt(), 'Sí' if self.con_base else 'No'))
        self.prompt()

    def _ang_txt(self):
        return 'Interior' if self.angulo == 'interior' else 'Deflexión'

    def _modo_txt(self):
        return 'Tramos' if self.tramos else 'Polilínea'

    def _dibujados(self):
        """Los vértices que quedan en la capa (sin la base si no se dibuja)."""
        return list(self.pts if self.con_base else self.pts[1:])

    def prompt(self):
        n = len(self.pts)
        if n == 0:
            self.cl.set_prompt('Precise primer punto del tramo base')
        elif n == 1:
            self.cl.set_prompt('Precise segundo punto del tramo base (da la dirección)')
        else:
            opts = [('A', 'Ángulo=' + self._ang_txt())]
            if n == 2:
                opts += [('M', 'Modo=' + self._modo_txt()), ('B', 'Base=' + ('Sí' if self.con_base else 'No'))]
            if len(self._dibujados()) >= 3:
                opts.append(('C', 'Cerrar'))
            if n > 2:
                opts.append(('H', 'desHacer'))
            self.cl.set_prompt('Precise tramo distancia<ángulo o', opts)

    # ------------------------------------------------------------ entrada
    def on_point(self, p):
        if self.pts and abs(p.x() - self.pts[-1].x()) < 1e-12 and abs(p.y() - self.pts[-1].y()) < 1e-12:
            self.cl.echo('Punto repetido: se ignora.')
            return
        self._agregar(p)

    def _agregar(self, p):
        n = len(self.pts)
        if n >= 2:
            d = math.hypot(p.x() - self.pts[-1].x(), p.y() - self.pts[-1].y())
            if n == 2 and self.tramos and self.con_base:      # la base, como primer objeto
                if self.mgr.add_feature(self.layer, list(self.pts), title='RUMBOS'):
                    self.marks.append(self.layer.undoStack().index())
            if self.tramos:
                if not self.mgr.add_feature(self.layer, [self.pts[-1], p], title='RUMBOS'):
                    return
                self.marks.append(self.layer.undoStack().index())
            self.largo += d
            u = self.mgr.units
            self.cl.echo('Tramo %d: %s   (acumulado %s)'
                         % (n - 1, format_length(d, u), format_length(self.largo, u)))
        self.pts.append(p)
        self._set_last(p)
        self.prompt()

    def on_text(self, text):
        k = _key(text)
        n = len(self.pts)
        if n >= 2 and k in OPT_ANG:
            self.angulo = 'deflexion' if self.angulo == 'interior' else 'interior'
            set_setting('rumbos_angulo', self.angulo)
            self.cl.echo('Ángulo = %s' % self._ang_txt())
            self.prompt()
        elif n == 2 and k in OPT_MODO:
            if self.kind != 'line':
                self.cl.echo('En capas de polígonos RUMBOS hace un solo polígono.')
            else:
                self.tramos = not self.tramos
                set_setting('rumbos_tramos', self.tramos)
                self.cl.echo('Modo = %s' % self._modo_txt())
            self.prompt()
        elif n == 2 and k in OPT_BASE:
            self.con_base = not self.con_base
            set_setting('rumbos_base', self.con_base)
            self.cl.echo('Base = %s' % ('Sí' if self.con_base else 'No'))
            self.prompt()
        elif n > 2 and k in OPT_UNDO:
            self._deshacer()
        elif len(self._dibujados()) >= 3 and k in OPT_CLOSE:
            if self.kind == 'line':
                self._agregar(self._dibujados()[0])
            self.finish(closed=True)
        elif n >= 2:
            r = tramo_rumbo(_xy(self.pts[-2]), _xy(self.pts[-1]), text, self.mgr.units, self.angulo)
            if r is None:
                self._resolve_and_apply(text)
                return
            (x, y), _d = r
            self._agregar(QgsPointXY(x, y))
        else:
            self._resolve_and_apply(text)

    def _deshacer(self):
        q = self.pts[-1]
        if self.tramos:
            stack = self.layer.undoStack()
            if self.marks and stack.index() == self.marks[-1]:
                stack.undo()
                self.marks.pop()
            else:
                self.cl.echo('No se puede deshacer: la capa se modificó por otro medio.')
                self.prompt()
                return
        self.pts.pop()
        self.largo -= math.hypot(q.x() - self.pts[-1].x(), q.y() - self.pts[-1].y())
        self._set_last(self.pts[-1])
        self.prompt()

    def on_enter(self):
        self.finish(closed=False)

    def escape(self):
        self.finish(closed=False)

    def finish(self, closed=False):
        if not self.tramos:
            pts = self._dibujados()
            if self.kind == 'polygon':
                if len(pts) >= 3:
                    self.mgr.add_feature(self.layer, pts, polygon=True, title='RUMBOS')
                elif len(self.pts) > 2:
                    self.cl.echo('Un polígono necesita al menos 3 vértices: no se creó el objeto.')
            elif len(pts) >= 2 and len(self.pts) > 2:
                self.mgr.add_feature(self.layer, pts, title='RUMBOS')
        if len(self.pts) > 2:
            self.mgr.last_line_end = self.pts[-1]
            self.mgr.lastpoint = self.pts[-1]
        self.end()

    def preview(self, cur):
        temp = [self.pts[-1], cur] if self.pts and cur is not None else []
        dib = self._dibujados() if len(self.pts) >= 2 else []
        guide = [self.pts[0], self.pts[1]] if len(self.pts) >= 2 and not self.con_base else []
        if self.tramos:
            dib = []                       # cada tramo ya está en la capa
        return dib, False, temp, guide
