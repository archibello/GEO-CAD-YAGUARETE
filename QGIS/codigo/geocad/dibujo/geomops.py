# -*- coding: utf-8 -*-
"""
Geometría 2D pura (sin QGIS) para EMPALME y ALARGA.

Puntos: tuplas (x, y). Polilíneas: listas de puntos.
"""

import math

EPS = 1e-9


class GeomError(ValueError):
    pass


# ---------------------------------------------------------------- vectores
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def norm(a):
    return math.hypot(a[0], a[1])


def dist(a, b):
    return norm(sub(a, b))


def unit(a):
    n = norm(a)
    if n < EPS:
        raise GeomError('Vector nulo.')
    return (a[0] / n, a[1] / n)


def same(a, b, tol=1e-9):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def dedupe(pts):
    out = []
    for p in pts:
        if not out or not same(out[-1], p):
            out.append(p)
    return out


# ---------------------------------------------------------------- consultas
def seg_param(a0, a1, p):
    d = sub(a1, a0)
    L2 = dot(d, d)
    return 0.0 if L2 < EPS else dot(sub(p, a0), d) / L2


def closest_segment(coords, p):
    """-> (índice de segmento, punto proyectado, distancia)."""
    best = None
    for i in range(len(coords) - 1):
        a0, a1 = coords[i], coords[i + 1]
        t = max(0.0, min(1.0, seg_param(a0, a1, p)))
        q = add(a0, mul(sub(a1, a0), t))
        d = dist(p, q)
        if best is None or d < best[2]:
            best = (i, q, d)
    if best is None:
        raise GeomError('La geometría no tiene segmentos.')
    return best


def line_intersection(a0, a1, b0, b1):
    """Intersección de las rectas infinitas a0-a1 y b0-b1 (None si son paralelas)."""
    r, s = sub(a1, a0), sub(b1, b0)
    den = cross(r, s)
    if abs(den) < EPS * max(1.0, norm(r) * norm(s)):
        return None
    t = cross(sub(b0, a0), s) / den
    return add(a0, mul(r, t))


def ray_segment(origin, direction, b0, b1):
    """Parámetro t>0 donde el rayo corta el segmento b0-b1, o None."""
    s = sub(b1, b0)
    den = cross(direction, s)
    if abs(den) < EPS:
        return None
    w = sub(b0, origin)
    t = cross(w, s) / den
    u = cross(w, direction) / den
    if t > 1e-7 and -1e-9 <= u <= 1 + 1e-9:
        return t
    return None


def segments_of(coords):
    return [(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]


def arc_points(center, radius, a_start, sweep, step_deg=5.0):
    n = max(2, int(math.ceil(abs(math.degrees(sweep)) / step_deg)))
    return [(center[0] + radius * math.cos(a_start + sweep * k / n),
             center[1] + radius * math.sin(a_start + sweep * k / n)) for k in range(n + 1)]


def _wrap(a):
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


# ---------------------------------------------------------------- ALARGA
def extend_end(coords, pick, boundaries):
    """
    Alarga el extremo de 'coords' más cercano a 'pick' hasta el primer contorno.
    boundaries: lista de segmentos ((x,y),(x,y)). Devuelve coords nuevas o None.
    """
    if len(coords) < 2:
        raise GeomError('El objeto no se puede alargar.')
    at_start = dist(pick, coords[0]) < dist(pick, coords[-1])
    e, n = (coords[0], coords[1]) if at_start else (coords[-1], coords[-2])
    d = unit(sub(e, n))
    best = None
    for b0, b1 in boundaries:
        if (same(b0, e) and same(b1, n)) or (same(b0, n) and same(b1, e)):
            continue
        t = ray_segment(e, d, b0, b1)
        if t is not None and (best is None or t < best):
            best = t
    if best is None:
        return None
    p = add(e, mul(d, best))
    return ([p] + list(coords[1:])) if at_start else (list(coords[:-1]) + [p])


# ---------------------------------------------------------------- EMPALME
def _kept_side(coords, i, q, x):
    """True si se conserva el lado del inicio (vértices 0..i) respecto de X."""
    a0, a1 = coords[i], coords[i + 1]
    return seg_param(a0, a1, x) >= seg_param(a0, a1, q)


def _trim_to(coords, i, keep_start, p):
    if keep_start:
        return dedupe(list(coords[:i + 1]) + [p])
    return dedupe([p] + list(coords[i + 1:]))


def _fillet_geometry(x, u1, u2, r):
    """Puntos de tangencia, centro y arco para dos direcciones que salen de X."""
    c = max(-1.0, min(1.0, dot(u1, u2)))
    theta = math.acos(c)
    if theta < 1e-7 or abs(theta - math.pi) < 1e-7:
        raise GeomError('Los objetos son colineales.')
    d = r / math.tan(theta / 2.0)
    t1, t2 = add(x, mul(u1, d)), add(x, mul(u2, d))
    bis = unit(add(u1, u2))
    center = add(x, mul(bis, r / math.sin(theta / 2.0)))
    a1 = math.atan2(t1[1] - center[1], t1[0] - center[0])
    a2 = math.atan2(t2[1] - center[1], t2[0] - center[0])
    arc = arc_points(center, r, a1, _wrap(a2 - a1))
    return d, t1, t2, arc


def fillet_two(l1, p1, l2, p2, r):
    """
    Empalme entre dos polilíneas distintas.
    Devuelve (nueva_l1, nueva_l2, arco_o_None). r = 0 -> esquina.
    Líneas paralelas -> semicírculo (como AutoCAD).
    """
    i1, q1, _ = closest_segment(l1, p1)
    i2, q2, _ = closest_segment(l2, p2)
    a0, a1 = l1[i1], l1[i1 + 1]
    b0, b1 = l2[i2], l2[i2 + 1]
    x = line_intersection(a0, a1, b0, b1)
    if x is None:
        return _fillet_parallel(l1, p1, l2, p2, a0, a1, b0, b1)
    k1 = _kept_side(l1, i1, q1, x)
    k2 = _kept_side(l2, i2, q2, x)
    if r <= 0:
        return _trim_to(l1, i1, k1, x), _trim_to(l2, i2, k2, x), None
    far1 = a0 if k1 else a1
    far2 = b0 if k2 else b1
    u1 = unit(sub(far1, x)) if not same(far1, x) else unit(sub(q1, x))
    u2 = unit(sub(far2, x)) if not same(far2, x) else unit(sub(q2, x))
    d, t1, t2, arc = _fillet_geometry(x, u1, u2, r)
    if d > dist(x, far1) + 1e-9 or d > dist(x, far2) + 1e-9:
        raise GeomError('Radio demasiado grande.')
    return _trim_to(l1, i1, k1, t1), _trim_to(l2, i2, k2, t2), arc


def _fillet_parallel(l1, p1, l2, p2, a0, a1, b0, b1):
    if dist(p1, l1[0]) <= dist(p1, l1[-1]):
        e1, n1, start1 = l1[0], l1[1], True
    else:
        e1, n1, start1 = l1[-1], l1[-2], False
    dirb = unit(sub(b1, b0))
    proj = add(b0, mul(dirb, dot(sub(e1, b0), dirb)))
    gap = dist(e1, proj)
    if gap < 1e-9:
        raise GeomError('Las líneas son colineales.')
    if dist(p2, l2[0]) <= dist(p2, l2[-1]):
        new2 = dedupe([proj] + list(l2[1:]))
    else:
        new2 = dedupe(list(l2[:-1]) + [proj])
    out = unit(sub(e1, n1))
    c = mul(add(e1, proj), 0.5)
    rad = gap / 2.0
    a_start = math.atan2(e1[1] - c[1], e1[0] - c[0])
    mid = (math.cos(a_start + math.pi / 2), math.sin(a_start + math.pi / 2))
    sweep = math.pi if dot(mid, out) > 0 else -math.pi
    arc = arc_points(c, rad, a_start, sweep)
    return list(l1), new2, arc


def fillet_same(coords, p1, p2, r, closed=False):
    """Empalme entre dos segmentos contiguos de la misma polilínea / anillo."""
    ring = list(coords[:-1]) if closed and same(coords[0], coords[-1]) else list(coords)
    n = len(ring)
    pts = ring + [ring[0]] if closed else ring
    i1, q1, _ = closest_segment(pts, p1)
    i2, q2, _ = closest_segment(pts, p2)
    nseg = len(pts) - 1
    if i1 == i2:
        raise GeomError('Designe dos segmentos distintos.')
    if closed:
        if (i1 + 1) % nseg == i2:
            v = i2 % n
        elif (i2 + 1) % nseg == i1:
            v = i1 % n
        else:
            raise GeomError('Los segmentos no son contiguos.')
    else:
        if i2 == i1 + 1:
            v = i2
        elif i1 == i2 + 1:
            v = i1
        else:
            raise GeomError('Los segmentos no son contiguos.')
    if r <= 0:
        raise GeomError('Los segmentos ya forman una esquina.')
    vprev = ring[(v - 1) % n] if (closed or v > 0) else None
    vnext = ring[(v + 1) % n] if (closed or v < n - 1) else None
    if vprev is None or vnext is None:
        raise GeomError('Los segmentos no son contiguos.')
    x = ring[v]
    u1, u2 = unit(sub(vprev, x)), unit(sub(vnext, x))
    d, t1, t2, arc = _fillet_geometry(x, u1, u2, r)
    if d > dist(x, vprev) + 1e-9 or d > dist(x, vnext) + 1e-9:
        raise GeomError('Radio demasiado grande.')
    new = dedupe(ring[:v] + arc + ring[v + 1:])
    if closed:
        if not same(new[0], new[-1]):
            new.append(new[0])
    return new


# ---------------------------------------------------------------- ARCO / CÍRCULO
def _norm2pi(a):
    a = math.fmod(a, 2 * math.pi)
    return a + 2 * math.pi if a < 0 else a


def circle_3p(p1, p2, p3):
    """Centro y radio del círculo que pasa por tres puntos."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < EPS:
        raise GeomError('Los tres puntos están alineados.')
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), dist((ux, uy), p1)


def arc_3p(p1, p2, p3, step_deg=2.0):
    """Arco por tres puntos -> (centro, radio, ángulo inicial, barrido, puntos)."""
    c, r = circle_3p(p1, p2, p3)
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    a2 = math.atan2(p2[1] - c[1], p2[0] - c[0])
    a3 = math.atan2(p3[1] - c[1], p3[0] - c[0])
    ccw = _norm2pi(a3 - a1)
    sweep = ccw if _norm2pi(a2 - a1) < ccw else ccw - 2 * math.pi
    return c, r, a1, sweep, arc_points(c, r, a1, sweep, step_deg)


def arc_center(start, center, end=None, included=None, step_deg=2.0):
    """Arco inicio-centro-fin (antihorario, como AutoCAD) o con ángulo incluido."""
    r = dist(start, center)
    if r < EPS:
        raise GeomError('El inicio coincide con el centro.')
    a1 = math.atan2(start[1] - center[1], start[0] - center[0])
    if included is not None:
        sweep = included
    else:
        sweep = _norm2pi(math.atan2(end[1] - center[1], end[0] - center[0]) - a1)
        if sweep < 1e-12:
            sweep = 2 * math.pi
    return center, r, a1, sweep, arc_points(center, r, a1, sweep, step_deg)


def circle_points(center, r, step_deg=2.0):
    if r <= 0:
        raise GeomError('El radio debe ser mayor que cero.')
    pts = arc_points(center, r, 0.0, 2 * math.pi, step_deg)
    pts[-1] = pts[0]
    return pts


# ---------------------------------------------------------------- longitudes
def length(coords):
    return sum(dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def locate(coords, p):
    """Distancia a lo largo de la polilínea del punto más cercano a p."""
    i, q, _ = closest_segment(coords, p)
    return sum(dist(coords[k], coords[k + 1]) for k in range(i)) + dist(coords[i], q)


def point_at(coords, s):
    acc = 0.0
    for i in range(len(coords) - 1):
        L = dist(coords[i], coords[i + 1])
        if acc + L >= s - 1e-12:
            t = 0.0 if L < EPS else (s - acc) / L
            return add(coords[i], mul(sub(coords[i + 1], coords[i]), max(0.0, min(1.0, t))))
        acc += L
    return coords[-1]


def substring(coords, s0, s1):
    """Tramo de la polilínea entre las distancias s0 < s1."""
    out = [point_at(coords, s0)]
    acc = 0.0
    for i in range(len(coords) - 1):
        L = dist(coords[i], coords[i + 1])
        acc += L
        if s0 + 1e-12 < acc < s1 - 1e-12:
            out.append(coords[i + 1])
    out.append(point_at(coords, s1))
    return dedupe(out)


def is_closed(coords):
    return len(coords) > 3 and same(coords[0], coords[-1])


# ---------------------------------------------------------------- PARTE
def break_at(coords, p):
    """PARTEENPUNTO: devuelve una o dos polilíneas."""
    L = length(coords)
    s = locate(coords, p)
    if is_closed(coords):
        ring = coords[:-1]
        # se abre el anillo en el punto designado
        opened = substring(coords, s, L) + substring(coords, 0.0, s)[1:]
        return [dedupe(opened)]
    if s <= 1e-9 or s >= L - 1e-9:
        raise GeomError('No se puede partir en el extremo del objeto.')
    return [substring(coords, 0.0, s), substring(coords, s, L)]


def break_between(coords, p1, p2):
    """PARTE: elimina el tramo entre p1 y p2."""
    L = length(coords)
    s1, s2 = locate(coords, p1), locate(coords, p2)
    if abs(s1 - s2) < 1e-9:
        return break_at(coords, p1)
    if is_closed(coords):
        if s1 < s2:
            kept = substring(coords, s2, L) + substring(coords, 0.0, s1)[1:]
        else:
            kept = substring(coords, s2, s1)
        return [dedupe(kept)]
    a, b = min(s1, s2), max(s1, s2)
    out = []
    if a > 1e-9:
        out.append(substring(coords, 0.0, a))
    if b < L - 1e-9:
        out.append(substring(coords, b, L))
    return out


# ---------------------------------------------------------------- DIVIDE / GRADÚA
def divide_distances(coords, n):
    if n < 2:
        raise GeomError('El número de segmentos debe ser 2 o más.')
    L = length(coords)
    if is_closed(coords):
        return [L * k / n for k in range(n)]
    return [L * k / n for k in range(1, n)]


def measure_distances(coords, d):
    if d <= 0:
        raise GeomError('La longitud debe ser mayor que cero.')
    L = length(coords)
    out, s = [], d
    while s < L - 1e-9:
        out.append(s)
        s += d
    return out


def split_at_distances(coords, ds):
    cuts = [0.0] + sorted(ds) + [length(coords)]
    return [substring(coords, cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)
            if cuts[i + 1] - cuts[i] > 1e-9]


# ---------------------------------------------------------------- DESCOMP
def explode_segments(coords):
    return [[a, b] for a, b in segments_of(dedupe(coords)) if not same(a, b)]


# ---------------------------------------------------------------- RECORTA
def seg_seg(a0, a1, b0, b1):
    """Intersección de dos segmentos -> (t sobre a, punto) o None."""
    r, s = sub(a1, a0), sub(b1, b0)
    den = cross(r, s)
    if abs(den) < EPS:
        return None
    w = sub(b0, a0)
    t = cross(w, s) / den
    u = cross(w, r) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return t, add(a0, mul(r, t))
    return None


def cut_distances(coords, boundaries):
    """Distancias a lo largo de la polilínea donde la cortan los contornos."""
    out = []
    acc = 0.0
    for i in range(len(coords) - 1):
        a0, a1 = coords[i], coords[i + 1]
        L = dist(a0, a1)
        for b0, b1 in boundaries:
            hit = seg_seg(a0, a1, b0, b1)
            if hit is not None:
                out.append(acc + hit[0] * L)
        acc += L
    out.sort()
    dedup = []
    for d in out:
        if not dedup or abs(d - dedup[-1]) > 1e-7:
            dedup.append(d)
    return dedup


def trim_polyline(coords, pick, boundaries):
    """
    RECORTA: elimina el tramo designado entre las intersecciones vecinas.
    Devuelve la lista de polilíneas resultantes ([] = el objeto se borra) o None si no cambia.
    """
    L = length(coords)
    if L <= 0:
        return None
    sp = locate(coords, pick)
    closed = is_closed(coords)
    cuts = [d for d in cut_distances(coords, boundaries)
            if closed or (1e-7 < d < L - 1e-7)]
    if closed:
        if len(cuts) < 2:
            return None
        lo = max([d for d in cuts if d < sp] or [cuts[-1]])
        hi = min([d for d in cuts if d > sp] or [cuts[0]])
        if lo < hi:
            kept = substring(coords, hi, L) + substring(coords, 0.0, lo)[1:]
        else:                       # el tramo designado cruza el inicio del anillo
            kept = substring(coords, hi, lo)
        return [dedupe(kept)]
    lo = [d for d in cuts if d < sp - 1e-9]
    hi = [d for d in cuts if d > sp + 1e-9]
    if not lo and not hi:
        return []                   # sin intersecciones: AutoCAD borra el objeto
    parts = []
    if lo:
        parts.append(substring(coords, 0.0, max(lo)))
    if hi:
        parts.append(substring(coords, min(hi), L))
    return [p for p in parts if len(p) >= 2 and length(p) > 1e-9]
