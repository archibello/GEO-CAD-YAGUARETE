# SPDX-License-Identifier: GPL-3.0-or-later
"""UNIR (J) con polígonos: la cuenta, compartida por IngeCAD y QGIS (3.96.0).

Pedido de Fernando (26/11/2026): que UNIR, con polígonos, actúe como
«Combinar objetos espaciales» de QGIS:
  - los datos (la fila de la tabla) son los del polígono de MAYOR superficie;
  - se rellenan los huecos que quedan encerrados ENTRE los polígonos unidos
    (bordes que se tocan en los vértices pero se separan en algún trayecto:
    las ranuras finitas de la digitalización); los huecos que un polígono ya
    tenía (un patio, una dona) se respetan;
  - los polígonos que no tocan a ningún otro quedan aparte: cada isla es un
    objeto, con los datos del polígono de mayor superficie de esa isla.

Cada objeto es una lista de anillos (bordes y huecos, regla par-impar, como un
SHP o como varias polilíneas cerradas con el mismo registro). Un anillo es una
lista de (x, y), cerrado o no.

``unir_anillos`` hace la unión en Python puro (IngeCAD no trae biblioteca de
geometría): parte los bordes en sus cruces y contactos, se queda con los
tramos que tienen polígono de un solo lado y los encadena. QGIS hace la unión
con GEOS y usa ``islas_de`` para lo demás, así los dos programas deciden igual.

Python puro (sin Qt ni IngeCAD).
"""
from __future__ import annotations

import math


# -- medidas -------------------------------------------------------------------------------
def abierto(anillo):
    """El anillo sin el punto de cierre repetido."""
    pts = [(float(p[0]), float(p[1])) for p in anillo]
    while len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def area_con_signo(anillo) -> float:
    pts = abierto(anillo)
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s += x1 * y2 - x2 * y1
    return s / 2.0


def caja(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def dentro_anillo(p, pts) -> bool:
    """Punto en el anillo (``pts`` abierto), por cruces."""
    x, y = p
    dentro = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            xc = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xc:
                dentro = not dentro
        j = i
    return dentro


class _Objeto:
    """Un objeto: sus anillos (par-impar) con sus cajas."""

    def __init__(self, oid, anillos) -> None:
        self.oid = oid
        self.anillos = [a for a in (abierto(r) for r in anillos) if len(a) >= 3]
        self.cajas = [caja(a) for a in self.anillos]
        self.caja = (min(c[0] for c in self.cajas), min(c[1] for c in self.cajas),
                     max(c[2] for c in self.cajas), max(c[3] for c in self.cajas)) if self.cajas else None

    def cuantos(self, p) -> int:
        """En cuántos de sus anillos cae el punto."""
        if self.caja is None:
            return 0
        x, y = p
        if not (self.caja[0] <= x <= self.caja[2] and self.caja[1] <= y <= self.caja[3]):
            return 0
        n = 0
        for a, c in zip(self.anillos, self.cajas):
            if c[0] <= x <= c[2] and c[1] <= y <= c[3] and dentro_anillo(p, a):
                n += 1
        return n

    def contiene(self, p) -> bool:
        return self.cuantos(p) % 2 == 1

    def en_su_hueco(self, p) -> bool:
        """El punto cae en un hueco propio: dentro de un borde, pero fuera."""
        n = self.cuantos(p)
        return n >= 2 and n % 2 == 0

    def partes(self):
        """[(anillos de la parte, superficie)]: cada borde (profundidad par) con
        sus huecos inmediatos."""
        prof = [sum(1 for j, b in enumerate(self.anillos) if j != i and _anillo_en(a, b))
                for i, a in enumerate(self.anillos)]
        out = []
        for i, a in enumerate(self.anillos):
            if prof[i] % 2:
                continue
            huecos = [b for j, b in enumerate(self.anillos)
                      if prof[j] == prof[i] + 1 and _anillo_en(b, a)]
            sup = abs(area_con_signo(a)) - sum(abs(area_con_signo(h)) for h in huecos)
            out.append(([a] + huecos, sup))
        return out


def _anillo_en(a, b) -> bool:
    """El anillo ``a`` está dentro del ``b`` (no se cruzan): por mayoría de
    hasta cinco de sus vértices (uno puede tocar el borde)."""
    paso = max(1, len(a) // 5)
    votos = [dentro_anillo(p, b) for p in a[::paso][:5]]
    return sum(votos) * 2 > len(votos)


def punto_interior(anillos):
    """Un punto que cae dentro del polígono (borde + huecos), lejos de los bordes:
    el medio del tramo más ancho de una horizontal que no pasa por vértices."""
    anillos = [abierto(a) for a in anillos]
    anillos = [a for a in anillos if len(a) >= 3]
    if not anillos:
        return None
    ys = sorted({p[1] for a in anillos for p in a})
    if len(ys) < 2:
        return None
    # varias alturas candidatas; la del tramo más ancho
    mejor = None
    pares = sorted(zip(ys, ys[1:]), key=lambda t: t[1] - t[0], reverse=True)[:8]
    alto = ys[-1] - ys[0]
    pares += [(ys[0] + alto * k / 10.0, ys[0] + alto * k / 10.0) for k in (3, 5, 7)]
    for y0, y1 in pares:
        y = (y0 + y1) / 2.0
        if y in ys:
            continue
        xs = []
        for a in anillos:
            n = len(a)
            for i in range(n):
                (x1, y1_), (x2, y2_) = a[i], a[(i + 1) % n]
                if (y1_ > y) != (y2_ > y):
                    xs.append(x1 + (y - y1_) * (x2 - x1) / (y2_ - y1_))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            ancho = xs[k + 1] - xs[k]
            if mejor is None or ancho > mejor[0]:
                mejor = (ancho, ((xs[k] + xs[k + 1]) / 2.0, y))
    return mejor[1] if mejor else None


def tolerancia(objetos) -> float:
    """Puntos «iguales»: 1e-10 de la coordenada más grande (UTM: ~1 mm), como
    UNIR con líneas."""
    m = max((abs(c) for rs in objetos.values() for r in rs for p in r for c in p[:2]), default=0.0)
    return max(1e-12, 1e-10 * m)


# -- la unión en Python puro ---------------------------------------------------------------
class _Puntos:
    """Agrupa los puntos que caen a menos de ``tol``: un solo vértice."""

    def __init__(self, tol) -> None:
        self.tol = tol
        self.celda = tol
        self.xy = []
        self.originales = set()
        self._rejilla = {}

    def id(self, p, original=False) -> int:
        cx, cy = int(math.floor(p[0] / self.celda)), int(math.floor(p[1] / self.celda))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in self._rejilla.get((cx + dx, cy + dy), ()):
                    q = self.xy[k]
                    if abs(q[0] - p[0]) <= self.tol and abs(q[1] - p[1]) <= self.tol:
                        if original:
                            self.originales.add(k)
                        return k
        k = len(self.xy)
        self.xy.append((p[0], p[1]))
        self._rejilla.setdefault((cx, cy), []).append(k)
        if original:
            self.originales.add(k)
        return k


def _proyeccion(a, b, p):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    if ll == 0.0:
        return 0.0, math.dist(a, p)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll
    q = (a[0] + t * dx, a[1] + t * dy)
    return t, math.dist(q, p)


def _cruce(a, b, c, d):
    """Parámetros (t, u) del cruce propio de a-b con c-d, o None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if den == 0.0:
        return None
    qp = (c[0] - a[0], c[1] - a[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    u = (qp[0] * r[1] - qp[1] * r[0]) / den
    if 0.0 < t < 1.0 and 0.0 < u < 1.0:
        return t, u
    return None


def _cortes(segs, tol):
    """Para cada segmento, los puntos donde hay que partirlo: (t, punto)."""
    cortes = [[(0.0, a), (1.0, b)] for a, b in segs]
    if not segs:
        return cortes
    x0 = min(min(a[0], b[0]) for a, b in segs)
    y0 = min(min(a[1], b[1]) for a, b in segs)
    x1 = max(max(a[0], b[0]) for a, b in segs)
    y1 = max(max(a[1], b[1]) for a, b in segs)
    n = max(1, int(math.sqrt(len(segs))))
    celda = max((x1 - x0) / n, (y1 - y0) / n, tol * 4, 1e-300)
    rejilla = {}
    for i, (a, b) in enumerate(segs):
        cx0 = int((min(a[0], b[0]) - tol - x0) // celda)
        cx1 = int((max(a[0], b[0]) + tol - x0) // celda)
        cy0 = int((min(a[1], b[1]) - tol - y0) // celda)
        cy1 = int((max(a[1], b[1]) + tol - y0) // celda)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                rejilla.setdefault((cx, cy), []).append(i)
    vistos = set()
    for lista in rejilla.values():
        for ii in range(len(lista)):
            i = lista[ii]
            a, b = segs[i]
            for jj in range(ii + 1, len(lista)):
                j = lista[jj]
                par = (i, j) if i < j else (j, i)
                if par in vistos:
                    continue
                vistos.add(par)
                c, d = segs[j]
                if (max(a[0], b[0]) + tol < min(c[0], d[0]) or max(c[0], d[0]) + tol < min(a[0], b[0])
                        or max(a[1], b[1]) + tol < min(c[1], d[1])
                        or max(c[1], d[1]) + tol < min(a[1], b[1])):
                    continue
                # extremos de uno sobre el otro (contactos en T y tramos superpuestos)
                for (p, q, k), extremos in (((a, b, i), (c, d)), ((c, d, j), (a, b))):
                    largo = math.dist(p, q)
                    if largo == 0.0:
                        continue
                    for e in extremos:
                        t, dist = _proyeccion(p, q, e)
                        if dist <= tol and tol / largo < t < 1.0 - tol / largo:
                            cortes[k].append((t, e))
                x = _cruce(a, b, c, d)
                if x is not None:
                    t, u = x
                    pt = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                    cortes[i].append((t, pt))
                    cortes[j].append((u, pt))
    return cortes


def _giro(din, dout) -> float:
    """Ángulo con signo de din a dout (izquierda positivo), en (-pi, pi]."""
    a = math.atan2(din[0] * dout[1] - din[1] * dout[0], din[0] * dout[0] + din[1] * dout[1])
    return math.pi if a <= -math.pi else a


def _lazos(camino):
    """Separa un recorrido cerrado en lazos simples, cortando en los vértices
    repetidos (dos islas que se tocan en un punto, un hueco que toca el borde)."""
    out = []
    pila = []
    pos = {}
    for v in camino:
        if v in pos:
            k = pos[v]
            lazo = pila[k:]
            for w in lazo[1:]:
                pos.pop(w, None)
            del pila[k + 1:]
            if len(lazo) >= 3:
                out.append(lazo)
        else:
            pos[v] = len(pila)
            pila.append(v)
    if len(pila) >= 3:
        out.append(pila)
    return out


def _sin_alineados(lazo, pts, originales, tol):
    """Quita los vértices nuevos (de los cortes) que quedaron en línea recta."""
    cambio = True
    while cambio and len(lazo) > 3:
        cambio = False
        for i in range(len(lazo)):
            v = lazo[i]
            if v in originales:
                continue
            a, b, c = pts[lazo[i - 1]], pts[v], pts[lazo[(i + 1) % len(lazo)]]
            _t, dist = _proyeccion(a, c, b)
            if dist <= tol and (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) > 0:
                del lazo[i]
                cambio = True
                break
    return lazo


def unir_anillos(objetos, tol=None):
    """La unión de los objetos ({id: [anillos]}).

    Devuelve [[borde, hueco, ...], ...]: un polígono por isla; bordes en sentido
    antihorario y huecos en horario, abiertos (sin el punto de cierre)."""
    objs = [_Objeto(k, v) for k, v in objetos.items()]
    objs = [o for o in objs if o.anillos]
    if tol is None:
        tol = tolerancia({o.oid: o.anillos for o in objs})
    puntos = _Puntos(tol)
    segs = []
    for o in objs:
        for a in o.anillos:
            ids = [puntos.id(p, original=True) for p in a]
            for i in range(len(a)):
                u, v = ids[i], ids[(i + 1) % len(a)]
                if u != v:
                    segs.append((puntos.xy[u], puntos.xy[v]))
    cortes = _cortes(segs, tol)
    aristas = set()
    for lista in cortes:
        lista.sort(key=lambda t: t[0])
        ids = []
        for _t, p in lista:
            k = puntos.id(p)
            if not ids or ids[-1] != k:
                ids.append(k)
        for u, v in zip(ids, ids[1:]):
            if u != v:
                aristas.add((u, v) if u < v else (v, u))

    def adentro(p):
        return any(o.contiene(p) for o in objs)

    pts = puntos.xy
    salen = {}
    for u, v in aristas:
        a, b = pts[u], pts[v]
        largo = math.dist(a, b)
        if largo == 0.0:
            continue
        off = min(tol * 0.5, largo * 0.25)
        nx, ny = -(b[1] - a[1]) / largo, (b[0] - a[0]) / largo
        m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        izq = adentro((m[0] + nx * off, m[1] + ny * off))
        der = adentro((m[0] - nx * off, m[1] - ny * off))
        if izq == der:
            continue
        if izq:
            salen.setdefault(u, []).append(v)
        else:
            salen.setdefault(v, []).append(u)

    # encadenar: el polígono siempre a la izquierda; en un vértice con varias
    # salidas, la que más dobla a la DERECHA: el borde de afuera rodea a los
    # polígonos que se tocan en dos o más puntos y la ranura que encierran queda
    # como hueco (se rellena); los que se tocan en un solo punto pasan dos veces
    # por él y ``_lazos`` los separa en dos islas
    usadas = set()
    lazos = []
    for u0 in list(salen):
        for v0 in list(salen[u0]):
            if (u0, v0) in usadas:
                continue
            camino = [u0]
            u, v = u0, v0
            while (u, v) not in usadas:
                usadas.add((u, v))
                camino.append(v)
                din = (pts[v][0] - pts[u][0], pts[v][1] - pts[u][1])
                libres = [w for w in salen.get(v, ()) if (v, w) not in usadas]
                if not libres:
                    break
                w = min(libres, key=lambda w: _giro(din, (pts[w][0] - pts[v][0], pts[w][1] - pts[v][1])))
                u, v = v, w
            if camino[-1] == camino[0]:
                camino.pop()
            lazos.extend(_lazos(camino))

    bordes, huecos = [], []
    for lazo in lazos:
        lazo = _sin_alineados(list(lazo), pts, puntos.originales, tol)
        anillo = [pts[k] for k in lazo]
        a = area_con_signo(anillo)
        if abs(a) <= tol * tol:
            continue
        (bordes if a > 0 else huecos).append((anillo, abs(a)))
    polis = [[b] for b, _a in bordes]
    sup = [a for _b, a in bordes]
    for h, _a in huecos:
        q = punto_interior([h])
        dueno = None
        for i, p in enumerate(polis):
            if q is not None and dentro_anillo(q, p[0]) and (dueno is None or sup[i] < sup[dueno]):
                dueno = i
        if dueno is not None:
            polis[dueno].append(h)
    return polis


# -- islas, huecos y datos (lo usan los dos programas) -------------------------------------
def islas_de(partes, objetos, tol=None):
    """Las islas que salen de una unión ya hecha.

    ``partes``: [[borde, hueco, ...], ...] (de ``unir_anillos`` o de GEOS).
    ``objetos``: {id: [anillos]}, lo que se unió.

    Devuelve una lista de dicts, uno por isla:
      anillos    [borde, huecos que se respetan...] (abiertos)
      jefe       el id del objeto de mayor superficie de la isla (sus datos)
      miembros   [ids], de mayor a menor superficie
      rellenos   cuántos huecos nuevos se rellenaron
      sin_cambio True si la isla es un objeto tal como estaba
    """
    objs = [_Objeto(k, v) for k, v in objetos.items()]
    objs = [o for o in objs if o.anillos]
    if tol is None:
        tol = tolerancia({o.oid: o.anillos for o in objs})
    islas = []
    for p in partes:
        borde = abierto(p[0])
        if len(borde) < 3:
            continue
        guardar, rellenos = [], 0
        for h in p[1:]:
            h = abierto(h)
            if len(h) < 3:
                continue
            q = punto_interior([h])
            if q is not None and any(o.en_su_hueco(q) for o in objs):
                guardar.append(h)
            else:
                rellenos += 1
        islas.append({"anillos": [borde] + guardar, "jefe": None, "miembros": [],
                      "rellenos": rellenos, "sup": abs(area_con_signo(borde)),
                      "_partes": []})
    # cada parte de cada objeto, a la isla más chica que la contiene
    orden = {o.oid: i for i, o in enumerate(objs)}
    for o in objs:
        for anillos, sup in o.partes():
            q = punto_interior(anillos)
            if q is None:
                continue
            mejor = None
            for isla in islas:
                if dentro_anillo(q, isla["anillos"][0]) and (mejor is None or isla["sup"] < mejor["sup"]):
                    mejor = isla
            if mejor is not None:
                mejor["_partes"].append((o.oid, anillos, sup))
    out = []
    for isla in islas:
        sup_de = {}
        for oid, _a, sup in isla["_partes"]:
            sup_de[oid] = sup_de.get(oid, 0.0) + sup
        if not sup_de:
            continue
        miembros = sorted(sup_de, key=lambda k: (-sup_de[k], orden[k]))
        sup_isla = isla["sup"] - sum(abs(area_con_signo(h)) for h in isla["anillos"][1:])
        sin_cambio = (len(miembros) == 1 and len(isla["_partes"]) == 1 and isla["rellenos"] == 0
                      and abs(sup_isla - isla["_partes"][0][2]) <= max(tol * tol, 1e-9 * sup_isla))
        out.append({"anillos": isla["anillos"], "jefe": miembros[0], "miembros": miembros,
                    "rellenos": isla["rellenos"], "sin_cambio": sin_cambio,
                    "superficie": sup_isla})
    return out


def combinar(objetos, tol=None):
    """La unión en Python puro y sus islas (lo que usa IngeCAD)."""
    if tol is None:
        tol = tolerancia(objetos)
    return islas_de(unir_anillos(objetos, tol), objetos, tol)


def superficies(objetos):
    """{id: superficie} de cada objeto (par-impar)."""
    return {k: sum(s for _a, s in _Objeto(k, v).partes()) for k, v in objetos.items()}


def nombre_combinados(capa: str) -> str:
    """El nombre de la capa nueva: «combinados de <capa>»."""
    return "combinados de " + (capa or "").strip()


def plan_original(islas):
    """Qué hacer en la capa original: [(fid, isla)] a cambiar, [(fid, isla)] a
    crear como copia de fid (segunda isla del mismo objeto) y [fids] a borrar."""
    jefe_de = {}
    aparece = {}
    for isla in islas:
        jefe_de.setdefault(isla['jefe'], []).append(isla)
        for m in isla['miembros']:
            aparece[m] = aparece.get(m, 0) + 1
    cambiar, crear = [], []
    for fid, lista in jefe_de.items():
        primera = lista[0]
        if not (len(lista) == 1 and primera['sin_cambio'] and aparece.get(fid, 0) == 1):
            cambiar.append((fid, primera))
        crear += [(fid, isla) for isla in lista[1:]]
    borrar = [m for m in aparece if m not in jefe_de]
    return cambiar, crear, borrar


def archivo_libre(carpeta: str, nombre: str, existe=None, ext: str = ".gpkg") -> str:
    """«<carpeta>/<nombre>.gpkg»; si ya está, «<nombre> (2).gpkg», «(3)»..."""
    import os

    existe = existe or os.path.exists
    ruta = os.path.join(carpeta, nombre + ext)
    n = 2
    while existe(ruta):
        ruta = os.path.join(carpeta, "%s (%d)%s" % (nombre, n, ext))
        n += 1
    return ruta


def carpeta_para(ruta_proyecto: str = "", ruta_capa: str = "", casa: str = "") -> str:
    """Dónde va el archivo de la capa nueva: la carpeta del proyecto guardado;
    si no, la de la capa original (si es un archivo); si no (capa temporal y
    proyecto sin guardar), Documentos/GeoCAD (o Documents/GeoCAD, o ~/GeoCAD)."""
    import os

    if ruta_proyecto:
        d = os.path.dirname(os.path.abspath(ruta_proyecto))
        if os.path.isdir(d):
            return d
    if ruta_capa:
        f = ruta_capa.split("|")[0]
        if os.path.isfile(f):
            return os.path.dirname(os.path.abspath(f))
    casa = casa or os.path.expanduser("~")
    for nombre in ("Documentos", "Documents"):
        if os.path.isdir(os.path.join(casa, nombre)):
            return os.path.join(casa, nombre, "GeoCAD")
    return os.path.join(casa, "GeoCAD")


# -- la pregunta del final (3.97.2, Fernando: «¿quieres crear una capa nueva con
# el resultado? Yes or Not; por defecto después de ENTER es Not») --------------
PREGUNTA = "¿Quiere crear una capa nueva con el resultado?"
RESP_SI = ("S", "SI", "SÍ", "Y", "YES")
RESP_NO = ("N", "NO", "NOT")


def respuesta(texto):
    """'nueva' (Sí), 'original' (No, también Intro) o None (no se entiende)."""
    t = str(texto or "").strip().upper().lstrip("_")
    if t == "":
        return "original"
    if t in RESP_SI:
        return "nueva"
    if t in RESP_NO:
        return "original"
    return None
