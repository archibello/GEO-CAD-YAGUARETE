# SPDX-License-Identifier: GPL-3.0-or-later
"""Enviar a QGIS como capas nuevas (3.20.0, ENVIARQGIS).

Cualquier objeto elegido en IngeCAD, venga o no de QGIS, viaja a QGIS como
capa temporal, una por tipo:

* Puntos: POINT y bloques (INSERT, con el nombre del bloque, giro y escala).
* Líneas: LINE, ARC, polilíneas abiertas, SPLINE y elipses abiertas.
* Polígonos: polilíneas cerradas, CIRCLE, elipses enteras y sombreados
  (HATCH, con sus huecos).
* Textos: TEXT y MTEXT como LÍNEAS cortas del ancho del texto, por el
  medio de la letra y en su dirección, con el texto en «etiqueta» (una
  línea por renglón del MTEXT). QGIS las rotula sobre la línea: el rótulo
  queda en el lugar, con la dirección y el tamaño del texto (pedido de
  Fernando, 11/10/2026).

Los arcos y curvas se pasan a tramos rectos (cada tramo se aparta de la
curva menos que ``TOLERANCIA`` unidades del dibujo). Cada objeto lleva su
capa CAD, su color (el propio o el de su capa) y su tipo de CAD. Lo demás
(cotas, imágenes...) se saltea y se cuenta.

La parte sin IngeCAD (qué sale de cada objeto) se prueba sola; el envío es
un mensaje del buzón que QGIS atiende (ver desde_ingecad.py de QGIS).
"""
from __future__ import annotations

import math
from collections import Counter

from . import buzon, config, estilo

TIPO_MENSAJE = "capas_nuevas"
TIPOS = ("puntos", "lineas", "poligonos", "textos")
TOLERANCIA = 0.01                     # 1 cm con el dibujo en metros

# ezdxf: qué entidades sabe pasar a trazos (make_path)
_TRAZOS = {"LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "LWPOLYLINE", "POLYLINE"}


def _num(v: float) -> str:
    texto = "%.6f" % v
    texto = texto.rstrip("0").rstrip(".")
    return "0" if texto in ("-0", "") else texto


def _xy(p) -> str:
    return f"{_num(p[0])} {_num(p[1])}"


def _limpios(pts) -> list:
    """Los vértices sin repetidos seguidos (en 2D)."""
    out = []
    for p in pts:
        q = (float(p[0]), float(p[1]))
        if not out or abs(q[0] - out[-1][0]) > 1e-9 or abs(q[1] - out[-1][1]) > 1e-9:
            out.append(q)
    return out


def wkt_linea(pts) -> str | None:
    pts = _limpios(pts)
    if len(pts) < 2:
        return None
    return "LINESTRING (" + ", ".join(_xy(p) for p in pts) + ")"


def _anillo(pts):
    pts = _limpios(pts)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    return "(" + ", ".join(_xy(p) for p in pts + [pts[0]]) + ")"


def wkt_poligono(anillos) -> str | None:
    """El primer anillo es el borde; los demás, huecos."""
    partes = [a for a in (_anillo(r) for r in anillos) if a]
    if not partes or _anillo(anillos[0]) is None:
        return None
    return "POLYGON (" + ", ".join(partes) + ")"


def wkt_punto(p) -> str:
    return f"POINT ({_xy(p)})"


# -- color ---------------------------------------------------------------------------

def _hex_aci(aci: int) -> str:
    aci = abs(int(aci or 7))
    if aci in (0, 7, 256) or aci > 255:
        return "#000000"
    return "#%06x" % estilo._palette()[aci]


def color_de(e, doc) -> str:
    """El color con que se ve: el propio, o el de su capa (PorCapa/PorBloque)."""
    propio = estilo.hex_of_entity(e)
    if propio:
        return propio
    try:
        capa = doc.layers.get(e.dxf.get("layer", "0"))
    except Exception:
        capa = None
    if capa is None:
        return "#000000"
    if capa.dxf.hasattr("true_color"):
        return "#%06x" % capa.dxf.true_color
    return _hex_aci(capa.dxf.get("color", 7))


# -- objetos -> elementos -----------------------------------------------------------

def _cerrado(e) -> bool:
    t = e.dxftype()
    if t == "CIRCLE":
        return True
    if t == "ELLIPSE":
        import math
        return abs((e.dxf.end_param - e.dxf.start_param) % (2 * math.pi)) < 1e-9
    if t == "LWPOLYLINE":
        return bool(e.closed)
    if t == "POLYLINE":
        return bool(e.is_closed)
    if t == "SPLINE":
        return bool(e.closed)
    return False


def _vertices(e, tolerancia: float) -> list:
    from ezdxf import path as ezpath
    trazo = ezpath.make_path(e)
    return [(v.x, v.y) for v in trazo.flattening(tolerancia, segments=8)]


def _hatch(e, tolerancia: float) -> str | None:
    from ezdxf import path as ezpath
    anillos = [[(v.x, v.y) for v in p.flattening(tolerancia, segments=8)]
               for p in ezpath.from_hatch(e)]
    anillos = [a for a in anillos if len(_limpios(a)) >= 3]
    if not anillos:
        return None
    # el borde es el anillo más grande; los demás, huecos
    def area(a):
        return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(a, a[1:] + a[:1]))) / 2
    anillos.sort(key=area, reverse=True)
    return wkt_poligono(anillos)


# -- textos -> líneas de rótulo ----------------------------------------------------

#: separación entre renglones de MTEXT (la de AutoCAD: 5/3 de la altura)
INTERLINEA = 5.0 / 3.0
#: lo que baja la base respecto del punto, según la alineación vertical
#: de TEXT (0 base, 1 abajo, 2 medio, 3 arriba), en alturas de letra
_BASE_TEXT = {0: 0.0, 1: 0.25, 2: -0.5, 3: -1.0}


def _fuente(doc, e):
    """La letra del estilo del texto, para medir el ancho (ezdxf)."""
    nombre = "txt"
    try:
        estilo_txt = doc.styles.get(e.dxf.get("style", "Standard"))
        if estilo_txt is not None and estilo_txt.dxf.get("font"):
            nombre = estilo_txt.dxf.font
    except Exception:
        pass
    return nombre


def ancho_texto(texto: str, altura: float, fuente: str = "txt", factor: float = 1.0) -> float:
    """El ancho del texto con su letra (o 0,6 de la altura por letra)."""
    try:
        from ezdxf.fonts import fonts
        return float(fonts.make_font(fuente, altura, factor).text_width(texto))
    except Exception:
        return 0.6 * altura * factor * len(texto)


def _girar(origen, giro_grados: float, dx: float, dy: float):
    r = math.radians(giro_grados)
    c, s = math.cos(r), math.sin(r)
    return (origen[0] + dx * c - dy * s, origen[1] + dx * s + dy * c)


def linea_de_renglon(origen, giro: float, x0: float, ancho: float, y_base: float,
                     altura: float):
    """Los dos extremos de la línea de un renglón: de x0 a x0 + ancho, a la
    mitad de la letra (y_base + altura/2), en el marco del texto sin girar
    con el ``origen`` en (0, 0)."""
    y = y_base + altura / 2.0
    return [_girar(origen, giro, x0, y), _girar(origen, giro, x0 + ancho, y)]


def renglones(e, doc) -> list:
    """[(texto, [p1, p2], altura, giro)] de un TEXT o un MTEXT."""
    fuente = _fuente(doc, e)
    if e.dxftype() == "TEXT":
        texto = e.plain_text() if hasattr(e, "plain_text") else e.dxf.get("text", "")
        altura = float(e.dxf.get("height", 1.0))
        giro = float(e.dxf.get("rotation", 0.0))
        factor = float(e.dxf.get("width", 1.0) or 1.0)
        h, v = e.dxf.get("halign", 0), e.dxf.get("valign", 0)
        if h in (3, 5) and e.dxf.hasattr("align_point"):          # ALIGNED / FIT
            a, b = e.dxf.insert, e.dxf.align_point
            giro = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            ancho = math.hypot(b[0] - a[0], b[1] - a[1])
            return [(texto, linea_de_renglon(a, giro, 0.0, ancho, 0.0, altura), altura, giro)]
        origen = e.dxf.align_point if (h or v) and e.dxf.hasattr("align_point") else e.dxf.insert
        ancho = ancho_texto(texto, altura, fuente, factor)
        x0 = {0: 0.0, 1: -ancho / 2, 2: -ancho, 4: -ancho / 2}.get(h, 0.0)
        y_base = _BASE_TEXT.get(v, 0.0) * altura
        return [(texto, linea_de_renglon(origen, giro, x0, ancho, y_base, altura), altura, giro)]
    # MTEXT: un renglón por línea; el punto de inserción es una de las 9
    # esquinas/medios del bloque de texto (1 arriba-izq ... 9 abajo-der)
    altura = float(e.dxf.get("char_height", 1.0))
    try:
        giro = float(e.get_rotation())
    except Exception:
        giro = float(e.dxf.get("rotation", 0.0))
    paso = altura * INTERLINEA * float(e.dxf.get("line_spacing_factor", 1.0) or 1.0)
    lineas = [t for t in e.plain_text().split("\n")]
    while lineas and not lineas[-1].strip():
        lineas.pop()
    alto = altura + paso * (len(lineas) - 1)
    adjunto = int(e.dxf.get("attachment_point", 1))
    fila, columna = (adjunto - 1) // 3, (adjunto - 1) % 3
    arriba = {0: 0.0, 1: alto / 2, 2: alto}[fila]        # el borde de arriba, desde el punto
    out = []
    for i, texto in enumerate(lineas):
        if not texto.strip():
            continue
        ancho = ancho_texto(texto, altura, fuente)
        x0 = {0: 0.0, 1: -ancho / 2, 2: -ancho}[columna]
        y_base = arriba - altura - i * paso
        out.append((texto, linea_de_renglon(e.dxf.insert, giro, x0, ancho, y_base, altura),
                    altura, giro))
    return out


def elementos(e, doc, tolerancia: float = TOLERANCIA):
    """(tipo, [{wkt y atributos}]) de un objeto, o (None, motivo). Un MTEXT
    da un elemento por renglón; lo demás, uno."""
    if e.dxftype() in ("TEXT", "MTEXT"):
        base = {"capa": e.dxf.get("layer", "0"), "color": color_de(e, doc),
                "tipo_cad": e.dxftype()}
        out = []
        for texto, extremos, altura, giro in renglones(e, doc):
            wkt = wkt_linea(extremos)
            if wkt:
                out.append(dict(base, wkt=wkt, etiqueta=texto, altura=altura,
                                giro=round(giro % 360.0, 6)))
        return ("textos", out) if out else (None, "texto vacío")
    tipo, dato = elemento(e, doc, tolerancia)
    return (tipo, [dato]) if tipo else (None, dato)


def elemento(e, doc, tolerancia: float = TOLERANCIA):
    """(tipo, {wkt y atributos}) de un objeto que no es texto, o (None, motivo)."""
    t = e.dxftype()
    base = {"capa": e.dxf.get("layer", "0"), "color": color_de(e, doc), "tipo_cad": t}
    if t == "POINT":
        return "puntos", dict(base, wkt=wkt_punto(e.dxf.location))
    if t == "INSERT":
        return "puntos", dict(base, wkt=wkt_punto(e.dxf.insert), bloque=e.dxf.name,
                              giro=float(e.dxf.get("rotation", 0.0)),
                              escala=float(e.dxf.get("xscale", 1.0)))
    if t == "HATCH":
        wkt = _hatch(e, tolerancia)
        return ("poligonos", dict(base, wkt=wkt)) if wkt else (None, "sombreado sin borde")
    if t in _TRAZOS:
        try:
            pts = _vertices(e, tolerancia)
        except Exception:
            return None, t
        if _cerrado(e):
            wkt = wkt_poligono([pts])
            if wkt:
                return "poligonos", dict(base, wkt=wkt)
        wkt = wkt_linea(pts)
        return ("lineas", dict(base, wkt=wkt)) if wkt else (None, "objeto sin largo")
    return None, t


def armar(entidades, doc, tolerancia: float = TOLERANCIA):
    """({tipo: [elementos]}, Counter de lo salteado)."""
    capas = {t: [] for t in TIPOS}
    salteados = Counter()
    for e in entidades:
        try:
            tipo, dato = elementos(e, doc, tolerancia)
        except Exception:
            tipo, dato = None, e.dxftype()
        if tipo is None:
            salteados[dato] += 1
        else:
            capas[tipo].extend(dato)
    return {t: v for t, v in capas.items() if v}, salteados


# -- el sistema de coordenadas -------------------------------------------------------

def crs_del_dibujo(document) -> str:
    """«EPSG:xxxx» del dibujo: el de la primera capa de QGIS conectada, el de
    la georreferencia, o el del proyecto (configuración común). "" = que
    QGIS use el de su proyecto."""
    from . import enlace, fuentes
    try:
        for link in enlace.read_links(document.doc).values():
            crs = fuentes.link_crs(link)
            if crs.epsg:
                return crs.code
    except Exception:
        pass
    try:
        from core.georef import read_georef
        georef = read_georef(document.doc)
        if georef is not None:
            if georef.crs:
                return georef.crs
            if georef.datum == "WGS84":
                return f"EPSG:{(32600 if georef.northern else 32700) + georef.zone}"
    except Exception:
        pass
    return config.get("crs_proyecto") or ""


def mensaje(capas: dict, crs: str, dibujo: str) -> dict:
    return {"tipo": TIPO_MENSAJE, "capas": capas, "crs": crs, "dibujo": dibujo}


def resumen(capas: dict, salteados: Counter) -> str:
    nombres = {"puntos": "punto(s)", "lineas": "línea(s)", "poligonos": "polígono(s)",
               "textos": "texto(s)"}
    partes = [f"{len(capas[t])} {nombres[t]}" for t in TIPOS if t in capas]
    texto = "Enviado a QGIS: " + ", ".join(partes) + "." if partes else "Nada para enviar."
    if salteados:
        texto += " Salteado: " + ", ".join(f"{n} {t}" for t, n in sorted(salteados.items())) + "."
    return texto


def enviar(capas: dict, crs: str, dibujo: str) -> None:
    buzon.send("qgis", mensaje(capas, crs, dibujo), "ingecad")
