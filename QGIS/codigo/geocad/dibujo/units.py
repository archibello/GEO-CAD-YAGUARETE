# -*- coding: utf-8 -*-
"""
Unidades, ángulos y entrada de coordenadas al estilo AutoCAD.

Python puro (sin QGIS) para poder probarlo de forma aislada.

Convención interna: ángulos en radianes "matemáticos" (0 = este, antihorario).
Los ángulos que escribe el usuario se interpretan según ANGBASE / ANGDIR,
salvo los rumbos topográficos (N45d30'15"E), que son siempre absolutos.
"""

import math
import re

# AUNITS (mismos códigos que AutoCAD)
DECIMAL, DMS, GRADS, RADIANS, SURVEYOR = 0, 1, 2, 3, 4
AUNITS_LABELS = ['Grados decimales', 'Grados/minutos/segundos', 'Grados centesimales',
                 'Radianes', 'Unidades topográficas']

# Precisión GMS/rumbos: igual que AUPREC de AutoCAD (0, 2, 4, 5, 6, 7, 8)
DMS_PRECISIONS = [(0, '0d'), (2, "0d00'"), (4, "0d00'00\""), (5, "0d00'00.0\""),
                  (6, "0d00'00.00\""), (7, "0d00'00.000\""), (8, "0d00'00.0000\"")]


def dms_level(auprec):
    """AUPREC -> nivel interno (0 grados, 1 minutos, 2 segundos, 3+ decimales)."""
    if auprec <= 0:
        return 0
    if auprec <= 2:
        return 1
    if auprec <= 4:
        return 2
    return min(auprec - 2, 6)


RELMODES = ('interior', 'direction')
RELMODE_LABELS = ['Ángulo interior en el vértice, desde el tramo anterior (180 = recto)',
                  'Desde la dirección del tramo anterior (0 = recto)']


def rel_zero(ref, units):
    """Dirección desde la que se miden los ángulos relativos."""
    return ref + math.pi if units.relmode == 'interior' else ref


class Units:
    """Equivalente a las variables LUPREC, AUNITS, AUPREC, ANGBASE y ANGDIR."""

    def __init__(self, luprec=4, aunits=DECIMAL, auprec=0, angbase=0.0, angdir_cw=False,
                 relmode='interior'):
        self.luprec = luprec          # decimales de longitud
        self.aunits = aunits          # formato de ángulo para mostrar
        self.auprec = auprec          # precisión de ángulo
        self.angbase = angbase        # grados, dirección del ángulo 0 (0 = este)
        self.angdir_cw = angdir_cw    # True = sentido horario
        # modo REL: 'interior' = ángulo en el vértice desde el tramo anterior (180 = recto)
        #           'direction' = desde la dirección del tramo (0 = recto)
        self.relmode = relmode if relmode in RELMODES else 'interior'

    def as_dict(self):
        return dict(luprec=self.luprec, aunits=self.aunits, auprec=self.auprec,
                    angbase=self.angbase, angdir_cw=self.angdir_cw, relmode=self.relmode)


class InputError(ValueError):
    pass


_NUM = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
_DMS_RE = re.compile(
    r'^(?P<sign>[+-]?)(?P<d>\d+(?:\.\d*)?|\.\d+)\s*[d°]'
    r'(?:\s*(?P<m>\d+(?:\.\d*)?)\s*\')?'
    r'(?:\s*(?P<s>\d+(?:\.\d*)?)\s*(?:"|\'\')?)?$', re.I)
_BEARING_RE = re.compile(r'^(?P<ns>[NS])(?P<ang>.*?)(?P<ew>[EWO])$', re.I)


def _num(text):
    if not re.match('^' + _NUM + '$', text):
        raise InputError('Valor numérico no válido: "%s"' % text)
    return float(text)


def _norm360(deg):
    deg = math.fmod(deg, 360.0)
    return deg + 360.0 if deg < 0 else deg


def parse_degrees(text, units=None):
    """Valor de ángulo (sin rumbos) -> grados. Acepta 45, 45.5, 45d30'15", 50g, 0.78r.

    Un número sin sufijo se interpreta en las unidades actuales si son
    centesimales o radianes (como AutoCAD); en otro caso, en grados.
    """
    t = text.strip().replace(' ', '')
    if not t:
        raise InputError('Ángulo vacío.')
    m = _DMS_RE.match(t)
    if m:
        deg = float(m.group('d')) + float(m.group('m') or 0) / 60.0 + float(m.group('s') or 0) / 3600.0
        if m.group('m') and float(m.group('m')) >= 60 or m.group('s') and float(m.group('s')) >= 60:
            raise InputError('Minutos y segundos deben ser menores que 60: "%s"' % text)
        return -deg if m.group('sign') == '-' else deg
    low = t.lower()
    if low.endswith('g'):
        return _num(t[:-1]) * 0.9
    if low.endswith('r'):
        return math.degrees(_num(t[:-1]))
    v = _num(t)
    if units is not None and units.aunits == GRADS:
        return v * 0.9
    if units is not None and units.aunits == RADIANS:
        return math.degrees(v)
    return v


def bearing_to_math_deg(ns, angle_deg, ew):
    ns, ew = ns.upper(), ew.upper().replace('O', 'W')
    if ns == 'N':
        return 90.0 - angle_deg if ew == 'E' else 90.0 + angle_deg
    return 270.0 + angle_deg if ew == 'E' else 270.0 - angle_deg


_DEFLECT_RE = re.compile(r'^(?P<ang>.+?)(?P<side>[Ii]|(?<=[d°\'"])D)$')


def parse_angle(text, units, ref=None, relative=False):
    """Texto de ángulo -> radianes matemáticos (0 = este, antihorario).

    ref       dirección del tramo anterior (radianes) o None.
    relative  modo RELATIVO: los ángulos numéricos se miden desde ref.
    Prefijo '<' (es decir, '<<' en la entrada de punto) fuerza ángulo absoluto.
    Sufijo I / D (30dI, 45d30'15"D) = deflexión izquierda/derecha respecto de ref.
    Los rumbos (N45dE) y direcciones cardinales son siempre absolutos.
    """
    t = text.strip().replace(' ', '')
    force_abs = t.startswith('<')
    if force_abs:
        t = t[1:]
    up = t.upper()
    cardinal = {'N': 90.0, 'S': 270.0, 'E': 0.0, 'W': 180.0, 'O': 180.0}
    if up in cardinal:
        return math.radians(cardinal[up])
    m = _BEARING_RE.match(t)
    if m:
        ang = m.group('ang')
        a = parse_degrees(ang, None) if ang else 0.0
        if a < 0 or a > 90:
            raise InputError('El ángulo de un rumbo debe estar entre 0 y 90: "%s"' % text)
        return math.radians(bearing_to_math_deg(m.group('ns'), a, m.group('ew')))
    d = _DEFLECT_RE.match(t)
    if d:
        if ref is None:
            raise InputError('No hay un tramo anterior desde el cual medir la deflexión.')
        val = parse_degrees(d.group('ang'), units)
        sign = 1.0 if d.group('side').upper() == 'I' else -1.0
        return ref + math.radians(sign * val)
    user = parse_degrees(t, units)
    signed = -user if units.angdir_cw else user
    if relative and ref is not None and not force_abs:
        return rel_zero(ref, units) + math.radians(signed)
    return math.radians(units.angbase + signed)


# ---------------------------------------------------------------- formato
def _fmt_dms(deg, prec, with_sec_symbol=True):
    """Grados (>=0) -> texto GMS con la precisión de AutoCAD."""
    sign = '-' if deg < 0 else ''
    deg = abs(deg)
    prec = dms_level(prec)
    if prec == 0:
        return '%s%dd' % (sign, int(round(deg)))
    if prec == 1:
        tot = int(round(deg * 60))
        return "%s%dd%02d'" % (sign, tot // 60, tot % 60)
    dec = prec - 2
    factor = 10 ** dec
    tot = int(round(deg * 3600 * factor))
    d, rem = divmod(tot, 3600 * factor)
    mnt, sec = divmod(rem, 60 * factor)
    if dec:
        s = ('%0' + str(3 + dec) + '.' + str(dec) + 'f') % (sec / float(factor))
    else:
        s = '%02d' % sec
    return '%s%dd%02d\'%s"' % (sign, d, mnt, s)


def format_angle(math_rad, units):
    """Radianes matemáticos -> texto según AUNITS/AUPREC/ANGBASE/ANGDIR."""
    md = _norm360(math.degrees(math_rad))
    if units.aunits == SURVEYOR:
        return format_bearing(md, units.auprec)
    user = md - units.angbase
    if units.angdir_cw:
        user = -user
    user = _norm360(user)
    p = units.auprec
    if units.aunits == DMS:
        txt = _fmt_dms(user, p)
        return txt.replace('360d', '0d') if txt.startswith('360d') else txt
    if units.aunits == GRADS:
        return '%.*fg' % (p, user / 0.9)
    if units.aunits == RADIANS:
        return '%.*fr' % (p, math.radians(user))
    txt = '%.*f' % (p, user)
    return '0' if float(txt) == 360.0 and p == 0 else txt


def format_bearing(math_deg, prec):
    az = _norm360(90.0 - math_deg)          # acimut desde el norte, horario
    lv = dms_level(prec)
    eps = 0.5 / (3600 * 10 ** max(0, lv - 2)) if lv >= 2 else (0.5 / 60 if lv == 1 else 0.5)
    for val, card in ((0, 'N'), (90, 'E'), (180, 'S'), (270, 'W'), (360, 'N')):
        if abs(az - val) < eps:
            return card
    if az < 90:
        ns, a, ew = 'N', az, 'E'
    elif az < 180:
        ns, a, ew = 'S', 180 - az, 'E'
    elif az < 270:
        ns, a, ew = 'S', az - 180, 'W'
    else:
        ns, a, ew = 'N', 360 - az, 'W'
    return '%s%s%s' % (ns, _fmt_dms(a, prec), ew)


def format_rel(deg, units):
    """Ángulo relativo con signo (grados) en el formato actual (sin ANGBASE)."""
    sign = '-' if deg < 0 else ''
    a = abs(deg)
    if units.aunits in (DMS, SURVEYOR):
        return sign + _fmt_dms(a, units.auprec)
    if units.aunits == GRADS:
        return '%s%.*fg' % (sign, units.auprec, a / 0.9)
    if units.aunits == RADIANS:
        return '%s%.*fr' % (sign, units.auprec, math.radians(a))
    return '%s%.*f' % (sign, units.auprec, a)


def format_length(v, units):
    return '%.*f' % (units.luprec, v)


def format_point(x, y, units):
    return '%s,%s' % (format_length(x, units), format_length(y, units))


# ---------------------------------------------------------------- puntos
class PointInput:
    """Resultado de interpretar una entrada de punto."""

    def __init__(self, kind, point=None, angle=None, distance=None):
        self.kind = kind          # 'point', 'distance', 'anglelock'
        self.point = point
        self.angle = angle
        self.distance = distance

    def __repr__(self):
        return 'PointInput(%s, %s, %s, %s)' % (self.kind, self.point, self.angle, self.distance)


def _split_xy(t):
    parts = t.split(',')
    if len(parts) not in (2, 3):
        raise InputError('Se esperaba X,Y: "%s"' % t)
    return _num(parts[0]), _num(parts[1])


def parse_point(text, units, last=None, ref=None, relative=False):
    """
    Interpreta una entrada de punto al estilo AutoCAD:

        x,y          absoluta              #x,y     absoluta (forzada)
        @dx,dy       relativa              @        último punto
        @d<ang       polar relativa        d<ang    polar absoluta (desde 0,0)
        <ang         modificación de ángulo
        d            distancia directa (en la dirección del cursor)
    """
    t = text.strip().replace(' ', '')
    if not t:
        raise InputError('Entrada vacía.')
    if t.startswith('#'):
        t = t[1:]
        if '<' in t:
            d, a = t.split('<', 1)
            ang = parse_angle(a, units, ref, relative)
            dist = _num(d)
            return PointInput('point', (dist * math.cos(ang), dist * math.sin(ang)))
        return PointInput('point', _split_xy(t))
    if t.startswith('@'):
        if last is None:
            raise InputError('No hay un último punto para "@".')
        body = t[1:]
        if body == '':
            return PointInput('point', tuple(last))
        if '<' in body:
            d, a = body.split('<', 1)
            dist = _num(d)
            ang = parse_angle(a, units, ref, relative)
            return PointInput('point', (last[0] + dist * math.cos(ang), last[1] + dist * math.sin(ang)))
        dx, dy = _split_xy(body)
        return PointInput('point', (last[0] + dx, last[1] + dy))
    if t.startswith('<'):
        return PointInput('anglelock', angle=parse_angle(t[1:], units, ref, relative))
    if '<' in t:
        d, a = t.split('<', 1)
        dist = _num(d)
        ang = parse_angle(a, units, ref, relative)
        return PointInput('point', (dist * math.cos(ang), dist * math.sin(ang)))
    if ',' in t:
        return PointInput('point', _split_xy(t))
    try:
        return PointInput('distance', distance=_num(t))
    except InputError:
        raise InputError('Punto o distancia no válidos: "%s"' % text)


def parse_distance(text):
    return _num(text.strip().replace(' ', ''))
