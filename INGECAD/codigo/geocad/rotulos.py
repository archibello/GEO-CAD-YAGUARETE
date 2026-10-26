# SPDX-License-Identifier: GPL-3.0-or-later
"""Dónde va cada rótulo (3.26.0): reglas estandarizadas de Fernando
(16/10/2026) para ROTULOSIG / SHPLABEL.

POLÍGONOS CERRADOS (3.48.1, Fernando, 25/10/2026: «que la prioridad de las
etiquetas sea en el epicentro del polígono» y «que siempre se respete la
orientación del texto en función del eje más largo»): el rótulo siempre
dentro, con su centro en el CENTROIDE (el epicentro) y según el EJE MÁS
LARGO del polígono. Si con la altura pedida no entra, se achica ahí mismo.
Sólo si el centroide cae afuera (polígonos en U, en L) o en un hueco, va
al centro visual (el punto más alejado de los bordes, como QGIS). Ya no hay
opciones A-E (3.26.0 a 3.48.0).
CÍRCULO (3.48.0), sólo en polígonos: el rótulo dentro de un círculo de
diámetro = la diagonal del texto + 10 %, y el círculo dentro del polígono
usando como mucho el 90 % del lugar hasta el borde; si no entra, el
círculo más grande que entra ahí y el texto achicado adentro.
LÍNEAS: según el eje de la línea (el tramo donde cae la mitad del largo),
nunca cabeza abajo; en la mitad, sobre la línea o por arriba / por debajo.
PUNTOS: centrado en el punto, o empezando en el punto a media altura.
ALTURA (3.48.1): la pedida, o todos con la del más chico de esa vez.
ANTERIORES (3.48.1): reemplazar los rótulos de esos objetos, o conservarlos.

Todo es geometría plana, sin Qt; se prueba sin IngeCAD abierto."""
from __future__ import annotations

import heapq
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Optional

LINEA = {"sobre": "Sobre la línea", "arriba": "Por arriba de la línea",
         "abajo": "Por debajo de la línea"}
PUNTO = {"centro": "Centrado en el punto", "desde": "Empezando en el punto, a media altura"}
CIRCULO = {"no": "Sin círculo", "si": "Con círculo (sólo polígonos)"}
ALTURA = {"propia": "La altura pedida (los que no entran, achicados)",
          "menor": "Todos con la altura del más chico"}
ANTERIORES = {"reemplazar": "Reemplazar los rótulos anteriores de esos objetos",
              "conservar": "Conservar los anteriores y sumar los nuevos"}

MARGEN = 0.15           # aire alrededor del texto, en alturas de texto
ESCALA_MINIMA = 0.05    # más chico que 1/20 de la altura pedida no se lee: se omite
LLENADO = 0.80          # un rótulo achicado ocupa el 80 % del lugar donde entra (3.26.3, Fernando)
AIRE_CIRCULO = 1.10     # el círculo: la diagonal del texto + 10 % (3.48.0, Fernando)
USO_CIRCULO = 0.90      # el círculo usa como mucho el 90 % del lugar hasta el borde
ILEGIBLE_INTERMEDIA = 1 / 3   # 3.50.3: más chico que 1/3 de la intermedia, sin rótulo


@dataclass
class OpcionesRotulo:
    linea: str = "sobre"
    punto: str = "centro"
    circulo: str = "no"
    altura: str = "propia"
    anteriores: str = "reemplazar"

    def validas(self) -> "OpcionesRotulo":
        def una(valor, permitidas, defecto):
            return valor if valor in permitidas else defecto
        return OpcionesRotulo(una(self.linea, LINEA, "sobre"), una(self.punto, PUNTO, "centro"),
                              una(self.circulo, CIRCULO, "no"), una(self.altura, ALTURA, "propia"),
                              una(self.anteriores, ANTERIORES, "reemplazar"))


@dataclass
class Ubicacion:
    """Un rótulo listo para dibujar: TEXT con ``alineacion`` en ``punto``."""
    punto: tuple
    altura: float
    giro: float              # grados, antihorario
    alineacion: str          # "MIDDLE_CENTER" | "MIDDLE_LEFT"
    circulo: Optional[float] = None    # radio del círculo alrededor (centro = punto), 3.48.0


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


def epicentro(externo, huecos=()) -> tuple:
    """El centroide si cae dentro (y fuera de los huecos); si no, el centro
    visual. Devuelve (x, y)."""
    c = centroide(externo)
    if c is not None and _dentro(c, externo) and not any(_dentro(c, h) for h in huecos):
        return c
    cx, cy, _r = centro_visual(externo, huecos)
    return (cx, cy)


def en_poligono(texto: str, altura: float, externo, huecos, medir,
                circulo: bool = False) -> Optional[Ubicacion]:
    """3.48.1 (Fernando): en el epicentro, según el eje más largo; si con la
    altura pedida no entra, achicado ahí (el texto, al LLENADO del lugar; con
    círculo, el círculo al USO_CIRCULO del lugar y el texto con su 10 % de
    aire adentro). Si en el epicentro quedaría ilegible (ESCALA_MINIMA: p. ej.
    cae justo sobre el borde de un hueco), en el centro visual; si ahí
    también, None."""
    externo = [tuple(p) for p in externo]
    huecos = [[tuple(p) for p in h] for h in huecos]
    giro = eje_mas_largo(externo)

    def en(p):
        if circulo:
            radio = math.hypot(medir(texto, altura), altura) * AIRE_CIRCULO / 2
            lugar = USO_CIRCULO * _dist_borde(p, [externo] + huecos)
            if radio <= 0 or lugar <= 0:
                return None
            if radio <= lugar:
                return Ubicacion(p, altura, giro, "MIDDLE_CENTER", radio)
            s = lugar / radio
            return Ubicacion(p, altura * s, giro, "MIDDLE_CENTER", lugar) if s >= ESCALA_MINIMA else None
        ancho = medir(texto, altura) + 2 * MARGEN * altura
        alto = altura * (1 + 2 * MARGEN)
        s = _escala(p, ancho, alto, giro, externo, huecos)
        if s >= 1.0:
            return Ubicacion(p, altura, giro, "MIDDLE_CENTER")
        if s > 0:                         # con aire: no toca los bordes
            return Ubicacion(p, altura * s * LLENADO, giro, "MIDDLE_CENTER")
        return None

    p = epicentro(externo, huecos)
    u = en(p)
    if u is None:
        cx, cy, _r = centro_visual(externo, huecos)
        if (cx, cy) != p:
            u = en((cx, cy))
    return u


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


def grupos_achicados(items, pedidas: dict, medir) -> dict:
    """Los rótulos que no entraron con la altura pedida, en categorías iguales
    entre sí (Enviar a IngeCAD). ``items``: [(fid, texto, Ubicacion)];
    ``pedidas``: {fid: altura pedida}. Devuelve {fid: Ubicacion nueva, o None
    = sin rótulo}.

    3.50.2 (Fernando: «todas las etiquetas y sus círculos, reducidos, deben
    ser iguales»): en cada categoría el mismo texto y el mismo círculo (la
    diagonal del texto más ancho + 10 %), el que entra en la parcela más
    chica de la categoría.
    3.50.3 (Fernando: «una categoría intermedia que se distribuya por esta
    familia de polígonos semejantes»): ordenados por su lugar y partidos por
    la mediana, la «mínima» (lo que entra en la mitad más chica) y la «media»
    (en la más holgada); la INTERMEDIA queda a mitad de camino entre las dos
    (media geométrica) y la toman todos donde entra. Los demás van con lo que
    entra en el más chico de ellos, y sin rótulo si eso no llega a
    ILEGIBLE_INTERMEDIA de la intermedia."""
    chicos = [(fid, t, u) for fid, t, u in items if u.altura < pedidas[fid] * (1 - 1e-9)]
    if not chicos:
        return {}
    circulo = all(u.circulo for _f, _t, u in chicos)
    # lugar: el radio que admite la parcela (con círculo) o la altura que entró;
    # k: lo que ocupa (radio o altura) por unidad de altura del texto
    lugar = {fid: u.circulo if circulo else u.altura for fid, _t, u in chicos}
    k = {fid: math.hypot(medir(t, 1.0), 1.0) * AIRE_CIRCULO / 2 if circulo else 1.0
         for fid, t, _u in chicos}
    chicos.sort(key=lambda x: lugar[x[0]])
    out = {}

    def alto(grupo):
        return min(lugar[f] for f, _t, _u in grupo) / max(k[f] for f, _t, _u in grupo)

    def poner(grupo, altura):
        kg = max(k[f] for f, _t, _u in grupo)
        for fid, _t, u in grupo:
            out[fid] = replace(u, altura=altura, circulo=altura * kg if circulo else u.circulo)

    n = len(chicos)
    if n == 1:
        poner(chicos, alto(chicos))
        return out
    intermedia = math.sqrt(alto(chicos[:n // 2]) * alto(chicos[n // 2:]))
    kmax = max(k.values())
    entran = [x for x in chicos if lugar[x[0]] >= intermedia * kmax * (1 - 1e-9)]
    resto = [x for x in chicos if lugar[x[0]] < intermedia * kmax * (1 - 1e-9)]
    if entran:
        poner(entran, intermedia)
    if resto:
        minima = alto(resto)
        if entran and minima < intermedia * ILEGIBLE_INTERMEDIA:
            out.update({fid: None for fid, _t, _u in resto})
        else:
            poner(resto, minima)
    return out


def ubicar(texto: str, altura: float, anillos, op: OpcionesRotulo, medir) -> Optional[Ubicacion]:
    """``anillos``: [(puntos, cerrado)] del objeto (datos.entity_rings).
    Polígono si hay un anillo cerrado; si no, línea; si no, punto."""
    op = op.validas()
    cerrados = [list(p) for p, c in anillos if c and len(p) >= 3 and abs(_area(p)) > 0]
    if cerrados:
        externo = max(cerrados, key=lambda r: abs(_area(r)))
        huecos = [r for r in cerrados if r is not externo and _dentro(r[0], externo)]
        return en_poligono(texto, altura, externo, huecos, medir, op.circulo == "si")
    lineas = [list(p) for p, _c in anillos if len(p) >= 2]
    if lineas:
        return en_linea(altura, max(lineas, key=lambda r: sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(r, r[1:]))), op.linea)
    for p, _c in anillos:
        if len(p) == 1:
            return en_punto(altura, p[0], op.punto)
    return None
