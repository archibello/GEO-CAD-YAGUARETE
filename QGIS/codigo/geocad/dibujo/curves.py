# -*- coding: utf-8 -*-
"""ARCO y CÍRCULO al estilo AutoCAD.

En capas que admiten curvas (tipos 'Curve', p. ej. GeoPackage CompoundCurve)
se guardan arcos verdaderos; en el resto, polilíneas finas (2° por tramo).
"""

import math

from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes

from .commands import _DrawCommand, _key
from .geomops import GeomError, arc_3p, arc_center, circle_3p, circle_points, dist
from .settings import get_setting, set_setting
from .units import InputError, format_length, parse_degrees, parse_distance


def _xy(p):
    return (p.x(), p.y())


def _P(t):
    return QgsPointXY(t[0], t[1])


def _curved(layer):
    try:
        return QgsWkbTypes.isCurvedType(layer.wkbType())
    except Exception:  # noqa: BLE001
        return False


def arc_geometry(layer, pts, p_start=None, p_mid=None, p_end=None):
    """Geometría del arco: curva verdadera si la capa la admite."""
    if _curved(layer) and p_start is not None:
        try:
            from qgis.core import QgsCircularString, QgsPoint
            cs = QgsCircularString(QgsPoint(*p_start), QgsPoint(*p_mid), QgsPoint(*p_end))
            return QgsGeometry(cs)
        except Exception:  # noqa: BLE001
            pass
    return QgsGeometry.fromPolylineXY([_P(p) for p in pts])


def circle_geometry(layer, center, r, polygon):
    if _curved(layer):
        try:
            from qgis.core import QgsCircle, QgsCurvePolygon, QgsPoint
            cs = QgsCircle(QgsPoint(*center), r).toCircularString()
            if polygon:
                cp = QgsCurvePolygon()
                cp.setExteriorRing(cs)
                return QgsGeometry(cp)
            return QgsGeometry(cs)
        except Exception:  # noqa: BLE001
            pass
    pts = [_P(p) for p in circle_points(center, r)]
    return QgsGeometry.fromPolygonXY([pts]) if polygon else QgsGeometry.fromPolylineXY(pts)


def _mid_of(pts):
    return pts[len(pts) // 2]


# ==========================================================================
class ArcCommand(_DrawCommand):
    title = 'ARCO'

    def start(self):
        self.state = 'p1'
        self.s = self.m = self.e = self.c = None
        self.prompt()

    def prompt(self):
        st = self.state
        texts = {
            'p1': ('Precise punto inicial del arco o', [('C', 'Centro')]),
            'p2': ('Precise segundo punto del arco o', [('C', 'Centro'), ('F', 'Final')]),
            'p3': ('Precise punto final del arco', None),
            'cc': ('Precise centro del arco', None),
            'cs': ('Precise punto inicial del arco', None),
            'ce': ('Precise punto final del arco o', [('A', 'Ángulo')]),
            'ca': ('Precise ángulo incluido', None),
            'fe': ('Precise punto final del arco', None),
            'fc': ('Precise centro del arco o', [('A', 'Ángulo'), ('R', 'Radio')]),
            'fa': ('Precise ángulo incluido', None),
            'fr': ('Precise radio del arco', None),
        }
        t, o = texts[st]
        self.cl.set_prompt(t, o)

    def base(self):
        st = self.state
        if st in ('p2', 'cc', 'fe'):
            return self.s
        if st == 'p3':
            return self.m
        if st in ('cs', 'ce', 'ca'):
            return self.c
        if st in ('fc', 'fa', 'fr'):
            return self.e
        return None

    def snap_points(self):
        return [p for p in (self.s, self.m, self.e, self.c) if p is not None]

    # -- construcción
    def _finish(self, pts, start, mid, end):
        g = arc_geometry(self.layer, pts, start, mid, end)
        self.mgr.add_geometry(self.layer, g, 'ARCO')
        self.mgr.lastpoint = _P(end)
        self.mgr.last_line_end = _P(end)
        self.end()

    def _from_center(self, end=None, included=None):
        c, r, a1, sw, pts = arc_center(_xy(self.s), _xy(self.c), _xy(end) if end is not None else None, included)
        self._finish(pts, pts[0], _mid_of(pts), pts[-1])

    def _center_from_chord(self, r=None, included=None):
        s, e = _xy(self.s), _xy(self.e)
        chord = dist(s, e)
        if chord < 1e-12:
            raise InputError('El inicio y el final coinciden.')
        mid = ((s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0)
        ux, uy = (e[0] - s[0]) / chord, (e[1] - s[1]) / chord
        left = (-uy, ux)
        if included is not None:
            if abs(included) < 1e-9 or abs(abs(included) - 2 * math.pi) < 1e-9:
                raise InputError('Ángulo incluido no válido.')
            h = (chord / 2.0) / math.tan(included / 2.0)
        else:
            if abs(r) < chord / 2.0 - 1e-12:
                raise InputError('El radio es menor que la mitad de la cuerda.')
            h = math.sqrt(max(0.0, r * r - (chord / 2.0) ** 2))
            if r < 0:
                h = -h          # radio negativo: arco mayor (como AutoCAD)
        return (mid[0] + left[0] * h, mid[1] + left[1] * h)

    def on_point(self, p):
        st = self.state
        if st == 'p1':
            self.s, self.state = p, 'p2'
        elif st == 'p2':
            self.m, self.state = p, 'p3'
        elif st == 'p3':
            c, r, a1, sw, pts = arc_3p(_xy(self.s), _xy(self.m), _xy(p))
            self._finish(pts, _xy(self.s), _xy(self.m), _xy(p))
            return
        elif st == 'cc':
            self.c = p
            self.state = 'cs' if self.s is None else 'ce'
        elif st == 'cs':
            self.s, self.state = p, 'ce'
        elif st == 'ce':
            self._from_center(end=p)
            return
        elif st == 'fe':
            self.e, self.state = p, 'fc'
        elif st == 'fc':
            self.c = p
            self._from_center(end=self.e)
            return
        self._set_last(p)
        self.prompt()

    def on_text(self, text):
        k, st, u = _key(text), self.state, self.mgr.units
        if st in ('p1', 'p2') and k in ('C', 'CENTRO', 'CENTER', 'CE'):
            self.state = 'cc'
        elif st == 'p2' and k in ('F', 'FINAL', 'END', 'E'):
            self.state = 'fe'
        elif st == 'ce' and k in ('A', 'ANGULO', 'ÁNGULO', 'ANGLE'):
            self.state = 'ca'
        elif st == 'ca':
            v = parse_degrees(text, u)
            self._from_center(included=math.radians(-v if u.angdir_cw else v))
            return
        elif st == 'fc' and k in ('A', 'ANGULO', 'ÁNGULO', 'ANGLE'):
            self.state = 'fa'
        elif st == 'fc' and k in ('R', 'RADIO', 'RADIUS'):
            self.state = 'fr'
        elif st == 'fa':
            v = parse_degrees(text, u)
            self.c = _P(self._center_from_chord(included=math.radians(-v if u.angdir_cw else v)))
            self._from_center(end=self.e)
            return
        elif st == 'fr':
            self.c = _P(self._center_from_chord(r=parse_distance(text)))
            self._from_center(end=self.e)
            return
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def on_enter(self):
        self.end()

    def escape(self):
        self.end()

    def preview(self, cur):
        st = self.state
        try:
            if cur is not None:
                if st == 'p3':
                    return [_P(q) for q in arc_3p(_xy(self.s), _xy(self.m), _xy(cur))[4]], False, [], []
                if st == 'ce':
                    pts = arc_center(_xy(self.s), _xy(self.c), _xy(cur))[4]
                    return [_P(q) for q in pts], False, [], [self.c, cur]
                if st == 'fc':
                    pts = arc_center(_xy(self.s), _xy(cur), _xy(self.e))[4]
                    return [_P(q) for q in pts], False, [], [self.s, cur, self.e]
                b = self.base()
                if b is not None:
                    return [], False, [b, cur], []
        except (GeomError, InputError, ValueError, ZeroDivisionError):
            pass
        return [], False, [], []


# ==========================================================================
class CircleCommand(_DrawCommand):
    title = 'CÍRCULO'

    def start(self):
        self.state = 'center'
        self.radius = get_setting('circlerad', 1.0, float)
        self.c = None
        self.pp = []
        self.prompt()

    def prompt(self):
        st, u = self.state, self.mgr.units
        if st == 'center':
            self.cl.set_prompt('Precise punto central para círculo o', [('3P', '3P'), ('2P', '2P')])
        elif st == 'radius':
            self.cl.set_prompt('Precise radio de círculo o', [('D', 'Diámetro')], format_length(self.radius, u))
        elif st == 'diam':
            self.cl.set_prompt('Precise diámetro de círculo', None, format_length(self.radius * 2, u))
        elif st == '3p':
            self.cl.set_prompt(['Precise primer punto en círculo', 'Precise segundo punto en círculo',
                                'Precise tercer punto en círculo'][len(self.pp)])
        elif st == '2p':
            self.cl.set_prompt(['Precise primer punto final del diámetro de círculo',
                                'Precise segundo punto final del diámetro de círculo'][len(self.pp)])

    def base(self):
        if self.state in ('radius', 'diam'):
            return self.c
        return self.pp[-1] if self.pp else None

    def snap_points(self):
        return [p for p in ([self.c] + self.pp) if p is not None]

    def _make(self, center, r):
        if r <= 0:
            raise InputError('El radio debe ser mayor que cero.')
        self.radius = r
        set_setting('circlerad', r)
        g = circle_geometry(self.layer, center, r, self.kind == 'polygon')
        self.mgr.add_geometry(self.layer, g, 'CÍRCULO')
        self.mgr.lastpoint = _P(center)
        self.end()

    def on_point(self, p):
        st = self.state
        if st == 'center':
            self.c, self.state = p, 'radius'
            self._set_last(p)
        elif st == 'radius':
            self._make(_xy(self.c), math.hypot(p.x() - self.c.x(), p.y() - self.c.y()))
            return
        elif st == 'diam':
            self._make(_xy(self.c), math.hypot(p.x() - self.c.x(), p.y() - self.c.y()) / 2.0)
            return
        elif st == '3p':
            self.pp.append(p)
            self._set_last(p)
            if len(self.pp) == 3:
                c, r = circle_3p(*[_xy(q) for q in self.pp])
                self._make(c, r)
                return
        elif st == '2p':
            self.pp.append(p)
            self._set_last(p)
            if len(self.pp) == 2:
                a, b = _xy(self.pp[0]), _xy(self.pp[1])
                self._make(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0), dist(a, b) / 2.0)
                return
        self.prompt()

    def on_text(self, text):
        k, st = _key(text), self.state
        if st == 'center' and k == '3P':
            self.state, self.pp = '3p', []
        elif st == 'center' and k == '2P':
            self.state, self.pp = '2p', []
        elif st == 'radius' and k in ('D', 'DIAMETRO', 'DIÁMETRO', 'DIAMETER'):
            self.state = 'diam'
        elif st == 'radius':
            self._make(_xy(self.c), parse_distance(text))
            return
        elif st == 'diam':
            self._make(_xy(self.c), parse_distance(text) / 2.0)
            return
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def on_enter(self):
        if self.state == 'radius':
            self._make(_xy(self.c), self.radius)
        elif self.state == 'diam':
            self._make(_xy(self.c), self.radius)
        else:
            self.end()

    def escape(self):
        self.end()

    def preview(self, cur):
        st = self.state
        try:
            if cur is not None:
                if st == 'radius':
                    r = math.hypot(cur.x() - self.c.x(), cur.y() - self.c.y())
                    return [_P(q) for q in circle_points(_xy(self.c), r)], False, [self.c, cur], []
                if st == 'diam':
                    r = math.hypot(cur.x() - self.c.x(), cur.y() - self.c.y()) / 2.0
                    return [_P(q) for q in circle_points(_xy(self.c), r)], False, [self.c, cur], []
                if st == '3p' and len(self.pp) == 2:
                    c, r = circle_3p(_xy(self.pp[0]), _xy(self.pp[1]), _xy(cur))
                    return [_P(q) for q in circle_points(c, r)], False, [], []
                if st == '2p' and len(self.pp) == 1:
                    a, b = _xy(self.pp[0]), _xy(cur)
                    c = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                    return [_P(q) for q in circle_points(c, dist(a, b) / 2.0)], False, [self.pp[0], cur], []
                if st == '3p' and self.pp:
                    return [], False, [self.pp[-1], cur], []
        except (GeomError, InputError, ValueError, ZeroDivisionError):
            pass
        return [], False, [], []
