# -*- coding: utf-8 -*-
"""RECTANG (REC) al estilo AutoCAD.

    Precise primer punto de esquina o [Chaflán/Empalme]:
    Precise otra esquina o [Área/Cotas/Rotación]:

- Segunda esquina con clic, x,y, @dx,dy, @d<ang... (con Rotación, @dx,dy se
  interpreta en los ejes girados del rectángulo, como en AutoCAD).
- Chaflán y Empalme se recuerdan para los próximos rectángulos (son excluyentes).
- Área tiene en cuenta lo que restan los chaflanes o empalmes.
- En capas de líneas crea una polilínea cerrada; en capas de polígonos, un polígono.
- Con Empalme en capas que admiten curvas (CompoundCurve) guarda arcos verdaderos.
"""

import math

from qgis.core import QgsGeometry, QgsPointXY

from .commands import _DrawCommand, _key
from .geomops import arc_points
from .settings import get_setting, set_setting
from .units import InputError, format_angle, format_length, parse_angle, parse_distance

OPT_CHAMFER = ('C', 'CH', 'CHAFLAN', 'CHAFLÁN', 'CHAMFER')
OPT_FILLET = ('E', 'EM', 'EMPALME', 'F', 'FILLET')
OPT_AREA = ('A', 'AREA', 'ÁREA')
OPT_DIMS = ('C', 'CO', 'COTAS', 'D', 'DIMENSIONS')
OPT_ROT = ('R', 'ROTACION', 'ROTACIÓN', 'ROTATION')
OPT_PICK = ('D', 'DESIGNAR', 'P', 'PICK')
OPT_LEN = ('L', 'LONGITUD', 'LENGTH')
OPT_WID = ('N', 'ANCHURA', 'W', 'WIDTH')
TOL = 1e-12


def _P(t):
    return QgsPointXY(t[0], t[1])


def _curved(layer):
    try:
        from qgis.core import QgsWkbTypes
        return QgsWkbTypes.isCurvedType(layer.wkbType())
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------- geometría
def rect_corners(p1, w, h, rot):
    """Esquinas (tuplas) de un rectángulo con origen p1, lados w (eje u) y h (eje v)."""
    c, s = math.cos(rot), math.sin(rot)
    out = []
    for lx, ly in ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)):
        out.append((p1[0] + lx * c - ly * s, p1[1] + lx * s + ly * c))
    return out


def corner_loss(cham, fillet):
    """Área que restan las 4 esquinas."""
    if fillet > 0:
        return 4.0 * fillet * fillet * (1.0 - math.pi / 4.0)
    if cham[0] > 0 or cham[1] > 0:
        return 4.0 * cham[0] * cham[1] / 2.0
    return 0.0


def _fits(w, h, cham, fillet):
    a, b = abs(w), abs(h)
    if fillet > 0:
        return 2 * fillet <= a + 1e-9 and 2 * fillet <= b + 1e-9
    return 2 * cham[0] <= a + 1e-9 and 2 * cham[1] <= b + 1e-9


def rect_segments(p1, w, h, rot, cham=(0.0, 0.0), fillet=0.0):
    """Contorno como lista de ('L', a, b) y ('A', a, centro, b). Devuelve (segs, modificado)."""
    corners = rect_corners(p1, w, h, rot)
    use_f = fillet > 0 and _fits(w, h, cham, fillet)
    use_c = not use_f and fillet <= 0 and (cham[0] > 0 or cham[1] > 0) and _fits(w, h, cham, 0)
    if not (use_f or use_c):
        segs = [('L', corners[i], corners[(i + 1) % 4]) for i in range(4)]
        return segs, False
    # en cada esquina: punto de entrada (sobre el lado anterior) y de salida (lado siguiente)
    pieces = []
    for i in range(4):
        v = corners[i]
        prv, nxt = corners[i - 1], corners[(i + 1) % 4]
        lp, ln = math.hypot(prv[0] - v[0], prv[1] - v[1]), math.hypot(nxt[0] - v[0], nxt[1] - v[1])
        up = ((prv[0] - v[0]) / lp, (prv[1] - v[1]) / lp)
        un = ((nxt[0] - v[0]) / ln, (nxt[1] - v[1]) / ln)
        if use_f:
            d1 = d2 = fillet
        else:
            # primera distancia sobre lados horizontales (eje u), segunda sobre los verticales
            d1, d2 = (cham[1], cham[0]) if i % 2 == 0 else (cham[0], cham[1])
        a = (v[0] + up[0] * d1, v[1] + up[1] * d1)
        b = (v[0] + un[0] * d2, v[1] + un[1] * d2)
        ctr = (v[0] + (up[0] + un[0]) * fillet, v[1] + (up[1] + un[1]) * fillet) if use_f else None
        pieces.append((a, b, ctr))
    segs = []
    for i in range(4):
        a, b, ctr = pieces[i]
        if math.hypot(b[0] - a[0], b[1] - a[1]) > TOL:
            segs.append(('A', a, ctr, b) if use_f else ('L', a, b))
        na = pieces[(i + 1) % 4][0]
        if math.hypot(na[0] - b[0], na[1] - b[1]) > TOL:
            segs.append(('L', b, na))
    return segs, True


def _arc_sweep(a, c, b):
    a0 = math.atan2(a[1] - c[1], a[0] - c[0])
    a1 = math.atan2(b[1] - c[1], b[0] - c[0])
    sw = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    return a0, sw


def densify(segs):
    """Anillo cerrado (lista de tuplas, el último = el primero)."""
    pts = []
    for s in segs:
        if s[0] == 'L':
            part = [s[1], s[2]]
        else:
            _, a, c, b = s
            r = math.hypot(a[0] - c[0], a[1] - c[1])
            a0, sw = _arc_sweep(a, c, b)
            part = arc_points(c, r, a0, sw, 5.0)
            part[0], part[-1] = a, b
        if pts:
            part = part[1:]
        pts.extend(part)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def rect_geometry(layer, segs, polygon):
    has_arc = any(s[0] == 'A' for s in segs)
    if has_arc and _curved(layer):
        try:
            from qgis.core import QgsCircularString, QgsCompoundCurve, QgsCurvePolygon, QgsLineString, QgsPoint
            cc = QgsCompoundCurve()
            for s in segs:
                if s[0] == 'L':
                    cc.addCurve(QgsLineString([QgsPoint(*s[1]), QgsPoint(*s[2])]))
                else:
                    _, a, c, b = s
                    r = math.hypot(a[0] - c[0], a[1] - c[1])
                    a0, sw = _arc_sweep(a, c, b)
                    m = (c[0] + r * math.cos(a0 + sw / 2), c[1] + r * math.sin(a0 + sw / 2))
                    cc.addCurve(QgsCircularString(QgsPoint(*a), QgsPoint(*m), QgsPoint(*b)))
            if polygon:
                cp = QgsCurvePolygon()
                cp.setExteriorRing(cc)
                return QgsGeometry(cp)
            return QgsGeometry(cc)
        except Exception:  # noqa: BLE001
            pass
    ring = [_P(p) for p in densify(segs)]
    return QgsGeometry.fromPolygonXY([ring]) if polygon else QgsGeometry.fromPolylineXY(ring)


# --------------------------------------------------------------- comando
class RectangCommand(_DrawCommand):
    title = 'RECTANG'
    no_ortho = True     # ORTO no tiene sentido para la esquina opuesta

    def start(self):
        if self.kind not in ('line', 'polygon'):
            self.cl.echo('RECTANG: la capa activa debe ser de líneas o polígonos.')
            self.end()
            return
        self.cham = (get_setting('rect_cham1', 0.0, float), get_setting('rect_cham2', 0.0, float))
        self.fillet = get_setting('rect_fillet', 0.0, float)
        self.rot = get_setting('rect_rot', 0.0, float)
        self.len_ = get_setting('rect_len', 10.0, float)
        self.wid = get_setting('rect_wid', 10.0, float)
        self.area = get_setting('rect_area', 100.0, float)
        self.p1 = None
        self.rp = None          # primer punto de Rotación > Designar puntos
        self.state = 'first'
        self._echo_modes()
        self.prompt()

    # -- utilidades
    def _echo_modes(self):
        u = self.mgr.units
        modes = []
        if self.fillet > 0:
            modes.append('Empalme=%s' % format_length(self.fillet, u))
        elif self.cham[0] > 0 or self.cham[1] > 0:
            modes.append('Chaflán=%s x %s' % (format_length(self.cham[0], u), format_length(self.cham[1], u)))
        if abs(self.rot) > 1e-12:
            modes.append('Rotación=%s' % format_angle(self.rot, u))
        if modes:
            self.cl.echo('Modos de rectángulo actuales: %s' % '  '.join(modes))

    def _axes(self):
        c, s = math.cos(self.rot), math.sin(self.rot)
        return (c, s), (-s, c)

    def _dims_to(self, p):
        """Lados (w, h) en los ejes del rectángulo hasta el punto p."""
        (ux, uy), (vx, vy) = self._axes()
        dx, dy = p.x() - self.p1.x(), p.y() - self.p1.y()
        return dx * ux + dy * uy, dx * vx + dy * vy

    def _segs(self, w, h):
        return rect_segments((self.p1.x(), self.p1.y()), w, h, self.rot, self.cham, self.fillet)

    def _make(self, w, h):
        if abs(w) < 1e-12 or abs(h) < 1e-12:
            raise InputError('El rectángulo tendría un lado de longitud cero.')
        segs, modified = self._segs(w, h)
        if not modified and (self.fillet > 0 or self.cham[0] > 0 or self.cham[1] > 0):
            self.cl.echo('El rectángulo es demasiado pequeño para el %s: se dibuja sin él.'
                         % ('empalme' if self.fillet > 0 else 'chaflán'))
        g = rect_geometry(self.layer, segs, self.kind == 'polygon')
        if self.mgr.add_geometry(self.layer, g, 'RECTANG'):
            self.len_, self.wid = abs(w), abs(h)
            set_setting('rect_len', self.len_)
            set_setting('rect_wid', self.wid)
            (ux, uy), (vx, vy) = self._axes()
            self.mgr.lastpoint = QgsPointXY(self.p1.x() + w * ux + h * vx, self.p1.y() + w * uy + h * vy)
        self.end()

    # -- interfaz del comando
    def prompt(self):
        st, u = self.state, self.mgr.units
        L = lambda v: format_length(v, u)  # noqa: E731
        if st == 'first':
            self.cl.set_prompt('Precise primer punto de esquina o', [('C', 'Chaflán'), ('E', 'Empalme')])
        elif st == 'cham1':
            self.cl.set_prompt('Precise primera distancia de chaflán para rectángulos', None, L(self.cham[0]))
        elif st == 'cham2':
            self.cl.set_prompt('Precise segunda distancia de chaflán para rectángulos', None, L(self._c1))
        elif st == 'fillet':
            self.cl.set_prompt('Precise radio de empalme para rectángulos', None, L(self.fillet))
        elif st == 'second':
            self.cl.set_prompt('Precise otra esquina o', [('A', 'Área'), ('C', 'Cotas'), ('R', 'Rotación')])
        elif st == 'area':
            self.cl.set_prompt('Indique área de rectángulo en unidades actuales', None, L(self.area))
        elif st == 'area_by':
            self.cl.set_prompt('Calcular dimensiones de rectángulo según',
                               [('L', 'Longitud'), ('N', 'aNchura')], 'Longitud')
        elif st == 'area_len':
            self.cl.set_prompt('Indique longitud de rectángulo', None, L(self.len_))
        elif st == 'area_wid':
            self.cl.set_prompt('Indique anchura de rectángulo', None, L(self.wid))
        elif st == 'dim_len':
            self.cl.set_prompt('Precise longitud de rectángulos', None, L(self.len_))
        elif st == 'dim_wid':
            self.cl.set_prompt('Precise anchura de rectángulos', None, L(self.wid))
        elif st == 'dim_quad':
            self.cl.set_prompt('Precise otra esquina (elija el cuadrante con el cursor)')
        elif st == 'rot':
            self.cl.set_prompt('Precise ángulo de rotación o', [('D', 'Designar puntos')], format_angle(self.rot, u))
        elif st == 'rot_p1':
            self.cl.set_prompt('Designe primer punto')
        elif st == 'rot_p2':
            self.cl.set_prompt('Designe segundo punto')

    def base(self):
        if self.state in ('rot', 'second', 'dim_quad'):
            return self.p1
        if self.state == 'rot_p2':
            return self.rp
        return None

    def snap_points(self):
        return [p for p in (self.p1, self.rp) if p is not None]

    def on_point(self, p):
        st = self.state
        if st == 'first':
            self.p1, self.state = p, 'second'
            self._set_last(p)
        elif st == 'second':
            self._make(*self._dims_to(p))
            return
        elif st == 'dim_quad':
            w, h = self._dims_to(p)
            self._make(self.len_ if w >= 0 else -self.len_, self.wid if h >= 0 else -self.wid)
            return
        elif st == 'rot':
            self._set_rot_from(self.p1, p)
        elif st == 'rot_p1':
            self.rp, self.state = p, 'rot_p2'
        elif st == 'rot_p2':
            self._set_rot_from(self.rp, p)
            self.rp = None
        else:
            raise InputError('Se esperaba un valor numérico.')
        self.prompt()

    def _set_rot_from(self, a, b):
        if math.hypot(b.x() - a.x(), b.y() - a.y()) < 1e-12:
            raise InputError('Los dos puntos coinciden.')
        self._set_rot(math.atan2(b.y() - a.y(), b.x() - a.x()))

    def _set_rot(self, ang):
        self.rot = ang
        set_setting('rect_rot', ang)
        self.state = 'second'
        self.mgr.lastpoint = self.p1

    def _positive(self, text):
        v = parse_distance(text)
        if v < 0:
            raise InputError('El valor no puede ser negativo.')
        return v

    def on_text(self, text):
        k, st = _key(text), self.state
        if st == 'first':
            if k in OPT_CHAMFER:
                self.state = 'cham1'
            elif k in OPT_FILLET:
                self.state = 'fillet'
            else:
                self._resolve_and_apply(text)
                return
        elif st == 'cham1':
            self._c1 = self._positive(text)
            self.state = 'cham2'
        elif st == 'cham2':
            self._set_chamfer(self._c1, self._positive(text))
        elif st == 'fillet':
            self._set_fillet(self._positive(text))
        elif st == 'second':
            if k in OPT_AREA:
                self.state = 'area'
            elif k in OPT_DIMS:
                self.state = 'dim_len'
            elif k in OPT_ROT:
                self.state = 'rot'
            else:
                self._second_text(text)
                return
        elif st == 'area':
            a = self._positive(text)
            if a <= 0:
                raise InputError('El área debe ser mayor que cero.')
            self.area = a
            set_setting('rect_area', a)
            self.state = 'area_by'
        elif st == 'area_by':
            if k in OPT_LEN:
                self.state = 'area_len'
            elif k in OPT_WID:
                self.state = 'area_wid'
            else:
                raise InputError('Opción no válida: escriba L (Longitud) o N (aNchura).')
        elif st in ('area_len', 'area_wid'):
            self._area_make(self._positive(text), st == 'area_len')
            return
        elif st == 'dim_len':
            self.len_ = self._nonzero(text)
            self.state = 'dim_wid'
        elif st == 'dim_wid':
            self.wid = self._nonzero(text)
            self.state = 'dim_quad'
        elif st == 'rot':
            if k in OPT_PICK:
                self.state = 'rot_p1'
            else:
                try:
                    ang = parse_angle(text, self.mgr.units)
                except (InputError, ValueError):
                    self._resolve_and_apply(text)
                    return
                self._set_rot(ang)
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def _nonzero(self, text):
        v = self._positive(text)
        if v <= 0:
            raise InputError('El valor debe ser mayor que cero.')
        return v

    def _second_text(self, text):
        kind, val = self.mgr.resolve(text)
        if kind == 'lock':
            self.angle_lock = val
            self.cl.echo('Modificación de ángulo: %s' % format_angle(val, self.mgr.units))
            self.prompt()
            return
        t = text.strip()
        if t.startswith('@') and '<' not in t and abs(self.rot) > 1e-12:
            # @dx,dy en los ejes girados del rectángulo
            dx, dy = val.x() - self.p1.x(), val.y() - self.p1.y()
            self._make(dx, dy)
            return
        self._make(*self._dims_to(val))

    def _area_make(self, v, is_len):
        if v <= 0:
            raise InputError('El valor debe ser mayor que cero.')
        total = self.area + corner_loss(self.cham, self.fillet if self.fillet > 0 else 0.0)
        other = total / v
        w, h = (v, other) if is_len else (other, v)
        self._make(w, h)

    def _set_chamfer(self, d1, d2):
        self.cham, self.fillet = (d1, d2), 0.0
        set_setting('rect_cham1', d1)
        set_setting('rect_cham2', d2)
        set_setting('rect_fillet', 0.0)
        self.state = 'first'

    def _set_fillet(self, r):
        self.fillet, self.cham = r, (0.0, 0.0)
        set_setting('rect_fillet', r)
        set_setting('rect_cham1', 0.0)
        set_setting('rect_cham2', 0.0)
        self.state = 'first'

    def on_enter(self):
        st = self.state
        if st == 'cham1':
            self._c1 = self.cham[0]
            self.state = 'cham2'
        elif st == 'cham2':
            self._set_chamfer(self._c1, self._c1)
        elif st == 'fillet':
            self._set_fillet(self.fillet)
        elif st == 'area':
            self.state = 'area_by'
        elif st == 'area_by':
            self.state = 'area_len'
        elif st == 'area_len':
            self._area_make(self.len_, True)
            return
        elif st == 'area_wid':
            self._area_make(self.wid, False)
            return
        elif st == 'dim_len':
            self.state = 'dim_wid'
        elif st == 'dim_wid':
            self.state = 'dim_quad'
        elif st == 'rot':
            self._set_rot(self.rot)
        else:
            self.end()
            return
        self.prompt()

    def escape(self):
        self.end()

    def info(self, cur):
        """Dimensiones en curso para la barra de información."""
        if self.state != 'second' or cur is None or self.p1 is None:
            return None
        w, h = self._dims_to(cur)
        u = self.mgr.units
        return 'Rect: %s x %s' % (format_length(abs(w), u), format_length(abs(h), u))

    def preview(self, cur):
        st = self.state
        try:
            if self.p1 is not None and cur is not None:
                if st == 'second':
                    w, h = self._dims_to(cur)
                    if abs(w) > 1e-12 and abs(h) > 1e-12:
                        return [_P(q) for q in densify(self._segs(w, h)[0])], False, [], []
                elif st == 'dim_quad':
                    w, h = self._dims_to(cur)
                    w = self.len_ if w >= 0 else -self.len_
                    h = self.wid if h >= 0 else -self.wid
                    return [_P(q) for q in densify(self._segs(w, h)[0])], False, [], []
                elif st == 'rot':
                    return [self.p1], False, [self.p1, cur], []
                elif st == 'rot_p2' and self.rp is not None:
                    return [self.p1], False, [self.rp, cur], []
                return [self.p1], False, [], []
        except (InputError, ValueError, ZeroDivisionError):
            pass
        return [], False, [], []
