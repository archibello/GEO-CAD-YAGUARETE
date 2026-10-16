# SPDX-License-Identifier: GPL-3.0-or-later
"""Dónde va cada rótulo (3.26.0): reglas estandarizadas de Fernando
(16/10/2026) para ROTULOSIG / SHPLABEL.

POLÍGONOS CERRADOS: el rótulo siempre dentro, con su centro en el
CENTROIDE del polígono (el epicentro) y la altura sugerida como prioridad;
si ahí no entra entero, en el centro visual (el punto más alejado de los
bordes, como QGIS), entero (3.26.2). Los que igual no entran:
  A  se achican hasta que entran, siempre horizontales;
  B  se rotan según el eje más largo del polígono y, si igual no entran,
     se achican con esa orientación;
  C  todos según el eje más largo; los que no entran, achicados;
  D  se omiten.
  E  según el eje más largo como prioridad; si así no entran, horizontales;
     si tampoco, se omiten. Nunca se achican (3.26.5, Fernando).
LÍNEAS: según el eje de la línea (el tramo donde cae la mitad del largo),
nunca cabeza abajo; en la mitad, sobre la línea o por arriba / por debajo.
PUNTOS: centrado en el punto, o empezando en el punto a media altura.

Todo es geometría plana, sin Qt; se prueba sin IngeCAD abierto."""
from __future__ import annotations

import heapq
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

POLIGONO = {"A": "Achicar (horizontal)", "B": "Rotar al eje más largo y, si no entra, achicar",
            "C": "Todos según el eje más largo, achicando los grandes", "D": "Omitir los que no entran",
            "E": "Según el eje más largo (si no, horizontal); omitir los que no entran"}
LINEA = {"sobre": "Sobre la línea", "arriba": "Por arriba de la línea",
         "abajo": "Por debajo de la línea"}
PUNTO = {"centro": "Centrado en el punto", "desde": "Empezando en el punto, a media altura"}

MARGEN = 0.15           # aire alrededor del texto, en alturas de texto
ESCALA_MINIMA = 0.05    # más chico que 1/20 de la altura pedida no se lee: se omite
LLENADO = 0.80          # un rótulo achicado ocupa el 80 % del lugar donde entra (3.26.3, Fernando)


@dataclass
class OpcionesRotulo:
    poligono: str = "A"
    linea: str = "sobre"
    punto: str = "centro"

    def validas(self) -> "OpcionesRotulo":
        return OpcionesRotulo(self.poligono if self.poligono in POLIGONO else "A",
                              self.linea if self.linea in LINEA else "sobre",
                              self.punto if self.punto in PUNTO else "centro")


@dataclass
class Ubicacion:
    """Un rótulo listo para dibujar: TEXT con ``alineacion`` en ``punto``."""
    punto: tuple
    altura: float
    giro: float              # grados, antihorario
    alineacion: str          # "MIDDLE_CENTER" | "MIDDLE_LEFT"


# ------------------------------------------------------------------ lo último elegido
def _archivo() -> Path:
    from . import config
    return config.config_path().parent / "rotulos.json"


def leer_opciones() -> OpcionesRotulo:
    try:
        data = json.loads(_archivo().read_text(encoding="utf-8"))
        return OpcionesRotulo(**{k: str(v) for k, v in data.items()
                                 if k in OpcionesRotulo.__dataclass_fields__}).validas()
    except (OSError, ValueError, TypeError):
        return OpcionesRotulo()


def guardar_opciones(op: OpcionesRotulo) -> None:
    ruta = _archivo()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".rotulos-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(op.validas()), fh, ensure_ascii=False, indent=1)
        os.replace(tmp, ruta)
    except OSError:
        pass


# ------------------------------------------------------------------ medir el texto
def medidor(doc=None) -> Callable[[str, float], float]:
    """Ancho de un texto de altura ``h`` medido como lo dibuja IngeCAD: un
    TEXT con el estilo Standard del dibujo, por ezdxf.tools.text_size, que
    busca la fuente igual que el dibujo (también con el retoque de
    tipografías). 3.26.2: antes se medía con otra fuente y algunos rótulos
    se salían. Sin eso, una estimación. Se mide una vez por texto."""
    anchos: dict = {}
    try:
        import ezdxf
        from ezdxf.entities import Text
        from ezdxf.tools.text_size import text_size
        base = doc if doc is not None else ezdxf.new("R2018")

        def medir(texto: str, h: float) -> float:
            if texto not in anchos:
                t = Text.new(dxfattribs={"text": texto, "height": 1.0, "style": "Standard"},
                             doc=base)
                anchos[texto] = text_size(t).width
            return anchos[texto] * h
        if medir("0", 1.0) <= 0:
            raise ValueError("sin medida")
        return medir
    except Exception:  # noqa: BLE001 -- sin ezdxf o sin fuente: estimación
        return lambda texto, h: 0.75 * h * max(len(texto), 1)


# ------------------------------------------------------------------ geometría
def _area(r) -> float:
    """Área con signo. Relativa al primer vértice: con coordenadas de
    Gauss-Krüger (X 7.400.000) los productos x*y pierden los decimales
    (3.26.2: el centroide salía hasta 40 m corrido)."""
    n = len(r)
    if n < 3:
        return 0.0
    x0, y0 = r[0][0], r[0][1]
    return sum((r[i][0] - x0) * (r[(i + 1) % n][1] - y0) - (r[(i + 1) % n][0] - x0) * (r[i][1] - y0)
               for i in range(n)) / 2


def _dentro(p, r) -> bool:
    x, y = p
    adentro = False
    n = len(r)
    for i in range(n):
        x1, y1 = r[i]
        x2, y2 = r[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            adentro = not adentro
    return adentro


def _dist_seg(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _dist_borde(p, anillos) -> float:
    """Distancia con signo al borde: + adentro (fuera de los huecos), - afuera."""
    externo, huecos = anillos[0], anillos[1:]
    adentro = _dentro(p, externo) and not any(_dentro(p, h) for h in huecos)
    d = min(_dist_seg(p, r[i], r[(i + 1) % len(r)]) for r in anillos for i in range(len(r)))
    return d if adentro else -d


def centro_visual(externo, huecos=(), precision: Optional[float] = None) -> tuple:
    """El polo de inaccesibilidad (algoritmo «polylabel» de Mapbox, el que usa
    QGIS): el punto interior más alejado de los bordes. Devuelve (x, y, r)."""
    anillos = [list(externo)] + [list(h) for h in huecos]
    xs = [p[0] for p in externo]
    ys = [p[1] for p in externo]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    ancho, alto = x1 - x0, y1 - y0
    lado = min(ancho, alto)
    if lado <= 0:
        return (x0, y0, 0.0)
    precision = precision or max(lado / 1000.0, 1e-9)
    h = lado / 2
    cola = []
    n = 0

    def celda(cx, cy, hh):
        nonlocal n
        d = _dist_borde((cx, cy), anillos)
        n += 1
        return (-(d + hh * math.sqrt(2)), n, cx, cy, hh, d)

    x = x0
    while x < x1:
        y = y0
        while y < y1:
            heapq.heappush(cola, celda(x + h, y + h, h))
            y += lado
        x += lado
    # el centroide, como primer candidato
    c = centroide(externo)
    if c is not None:
        mejor = celda(c[0], c[1], 0)
    else:
        mejor = celda(x0 + ancho / 2, y0 + alto / 2, 0)
    caja = celda(x0 + ancho / 2, y0 + alto / 2, 0)
    if caja[5] > mejor[5]:
        mejor = caja
    while cola and n < 20000:
        c = heapq.heappop(cola)
        if c[5] > mejor[5]:
            mejor = c
        if -c[0] - mejor[5] <= precision:
            continue
        hh = c[4] / 2
        for dx in (-hh, hh):
            for dy in (-hh, hh):
                heapq.heappush(cola, celda(c[2] + dx, c[3] + dy, hh))
    return (mejor[2], mejor[3], max(mejor[5], 0.0))


def _envolvente(puntos):
    pts = sorted(set(puntos))
    if len(pts) < 3:
        return pts

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    abajo, arriba = [], []
    for p in pts:
        while len(abajo) >= 2 and giro(abajo[-2], abajo[-1], p) <= 0:
            abajo.pop()
        abajo.append(p)
    for p in reversed(pts):
        while len(arriba) >= 2 and giro(arriba[-2], arriba[-1], p) <= 0:
            arriba.pop()
        arriba.append(p)
    return abajo[:-1] + arriba[:-1]


def legible(grados: float) -> float:
    """El mismo ángulo, pero que el texto se lea desde abajo o desde la
    derecha de la hoja (regla de dibujo): (-85, 95]. Los casi verticales van
    de abajo hacia arriba (93°, no -87°)."""
    g = (grados + 180.0) % 360.0 - 180.0
    if g > 95.0:
        g -= 180.0
    elif g <= -85.0:
        g += 180.0
    g = round(g, 9)                     # sin ruido de coma flotante
    return 0.0 if g == 0 else g


def eje_mas_largo(anillo) -> float:
    """Ángulo (grados, legible) del lado largo del rectángulo de menor área que
    contiene al polígono: el «sentido más largo» de una parcela."""
    env = _envolvente(anillo)
    if len(env) < 3:
        if len(env) == 2:
            return legible(math.degrees(math.atan2(env[1][1] - env[0][1], env[1][0] - env[0][0])))
        return 0.0
    mejor = None
    for i in range(len(env)):
        (ax, ay), (bx, by) = env[i], env[(i + 1) % len(env)]
        ang = math.atan2(by - ay, bx - ax)
        c, s = math.cos(ang), math.sin(ang)
        us = [px * c + py * s for px, py in env]
        vs = [-px * s + py * c for px, py in env]
        largo, ancho = max(us) - min(us), max(vs) - min(vs)
        area = largo * ancho
        if mejor is None or area < mejor[0] - 1e-12:
            mejor = (area, ang if largo >= ancho else ang + math.pi / 2)
    return legible(math.degrees(mejor[1]))


def _caja(centro, ancho, alto, grados):
    cx, cy = centro
    c, s = math.cos(math.radians(grados)), math.sin(math.radians(grados))
    out = []
    for u, v in ((-ancho / 2, -alto / 2), (ancho / 2, -alto / 2),
                 (ancho / 2, alto / 2), (-ancho / 2, alto / 2)):
        out.append((cx + u * c - v * s, cy + u * s + v * c))
    return out


def _cortan(a, b, c, d) -> bool:
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = o(c, d, a), o(c, d, b), o(a, b, c), o(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def entra(caja, externo, huecos=()) -> bool:
    """La caja del texto (4 esquinas) está toda dentro del polígono, fuera de
    los huecos y sin que ningún borde la cruce."""
    if not all(_dentro(p, externo) for p in caja):
        return False
    if any(_dentro(p, h) for p in caja for h in huecos):
        return False
    for r in [externo, *huecos]:
        # un hueco (o una punta del borde) metido en la caja sin tocar esquinas
        if any(_dentro(v, caja) for v in r):
            return False
        for i in range(len(r)):
            a, b = r[i], r[(i + 1) % len(r)]
            for j in range(4):
                if _cortan(a, b, caja[j], caja[(j + 1) % 4]):
                    return False
    return True


def _escala(centro, ancho, alto, grados, externo, huecos) -> float:
    """La mayor escala (<= 1) con la que la caja entra; 0 si ni la mínima."""
    if entra(_caja(centro, ancho, alto, grados), externo, huecos):
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(18):
        mid = (lo + hi) / 2
        if entra(_caja(centro, ancho * mid, alto * mid, grados), externo, huecos):
            lo = mid
        else:
            hi = mid
    return lo if lo >= ESCALA_MINIMA else 0.0


# ------------------------------------------------------------------ las reglas
def centroide(anillo):
    """El centro de gravedad del polígono (el «epicentro»); None si no tiene área."""
    a = _area(anillo)
    if not a:
        return None
    m = len(anillo)
    x0, y0 = anillo[0][0], anillo[0][1]         # relativo: ver _area
    cx = cy = 0.0
    for i in range(m):
        x1, y1 = anillo[i][0] - x0, anillo[i][1] - y0
        x2, y2 = anillo[(i + 1) % m][0] - x0, anillo[(i + 1) % m][1] - y0
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    return (x0 + cx / (6 * a), y0 + cy / (6 * a))


def en_poligono(texto: str, altura: float, externo, huecos, modo: str,
                medir) -> Optional[Ubicacion]:
    """3.26.2 (Fernando): el centro del texto en el CENTROIDE de la parcela,
    con la altura sugerida como prioridad. Si ahí no entra entero, en el
    centro visual (donde hay más lugar), también entero. Recién si tampoco
    entra, la opción: A achicar, B rotar al eje y achicar, C todo al eje
    (achicando), D omitir."""
    externo = [tuple(p) for p in externo]
    huecos = [[tuple(p) for p in h] for h in huecos]
    puntos = []
    c = centroide(externo)
    if c is not None and _dentro(c, externo) and not any(_dentro(c, h) for h in huecos):
        puntos.append(c)
    cx, cy, _r = centro_visual(externo, huecos)
    puntos.append((cx, cy))
    ancho = medir(texto, altura) + 2 * MARGEN * altura
    alto = altura * (1 + 2 * MARGEN)
    eje = eje_mas_largo(externo)

    def entero(giro):
        for p in puntos:
            if entra(_caja(p, ancho, alto, giro), externo, huecos):
                return Ubicacion(p, altura, giro, "MIDDLE_CENTER")
        return None

    def achicado(giro):
        # si igual hay que achicar, en el centroide (el corrimiento sólo vale
        # para conservar la altura entera); el centro visual, si el
        # centroide cae afuera o ni achicado entra ahí
        for p in puntos:
            s = _escala(p, ancho, alto, giro, externo, huecos)
            if s > 0:                     # con aire: no toca los bordes
                return Ubicacion(p, altura * s * LLENADO, giro, "MIDDLE_CENTER")
        return None

    if modo == "C":
        return entero(eje) or achicado(eje)
    if modo == "E":
        return entero(eje) or (entero(0.0) if eje != 0.0 else None)
    u = entero(0.0)
    if u is not None or modo == "D":
        return u
    if modo == "B" and eje != 0.0:
        return entero(eje) or achicado(eje)
    return achicado(0.0)


def en_linea(altura: float, puntos, modo: str) -> Optional[Ubicacion]:
    pts = [tuple(p) for p in puntos]
    largos = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    total = sum(largos)
    if total <= 0:
        return Ubicacion(pts[0], altura, 0.0, "MIDDLE_CENTER") if pts else None
    acc = 0.0
    for (a, b), L in zip(zip(pts, pts[1:]), largos):
        if L > 0 and acc + L >= total / 2:
            t = (total / 2 - acc) / L
            medio = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            giro = legible(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
            break
        acc += L
    if modo in ("arriba", "abajo"):
        d = altura if modo == "arriba" else -altura      # medio alto de aire + medio texto
        g = math.radians(giro)
        medio = (medio[0] - d * math.sin(g), medio[1] + d * math.cos(g))
    return Ubicacion(medio, altura, giro, "MIDDLE_CENTER")


def en_punto(altura: float, punto, modo: str) -> Ubicacion:
    return Ubicacion(tuple(punto), altura, 0.0, "MIDDLE_LEFT" if modo == "desde" else "MIDDLE_CENTER")


def ubicar(texto: str, altura: float, anillos, op: OpcionesRotulo, medir) -> Optional[Ubicacion]:
    """``anillos``: [(puntos, cerrado)] del objeto (datos.entity_rings).
    Polígono si hay un anillo cerrado; si no, línea; si no, punto."""
    op = op.validas()
    cerrados = [list(p) for p, c in anillos if c and len(p) >= 3 and abs(_area(p)) > 0]
    if cerrados:
        externo = max(cerrados, key=lambda r: abs(_area(r)))
        huecos = [r for r in cerrados if r is not externo and _dentro(r[0], externo)]
        return en_poligono(texto, altura, externo, huecos, op.poligono, medir)
    lineas = [list(p) for p, _c in anillos if len(p) >= 2]
    if lineas:
        return en_linea(altura, max(lineas, key=lambda r: sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(r, r[1:]))), op.linea)
    for p, _c in anillos:
        if len(p) == 1:
            return en_punto(altura, p[0], op.punto)
    return None
