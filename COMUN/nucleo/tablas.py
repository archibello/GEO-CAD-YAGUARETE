# SPDX-License-Identifier: GPL-3.0-or-later
"""Tablas que llegan por el portapapeles (3.22.0, módulo «Tablas»).

Lo que se copia en una hoja de cálculo o en la tabla de atributos de QGIS
llega al portapapeles como HTML y como texto con tabulaciones. Este módulo
lo convierte en una tabla neutra (``Tabla``), la misma para IngeCAD y para
QGIS, y la arma como dibujo: fondos, bordes y textos en milímetros, con la
esquina superior izquierda en (0, 0) y las filas hacia abajo (y negativa).

De dónde viene (``detectar``), probado el 14/10/2026:

* GenOffice: HTML como el de Google Sheets (<google-sheets-html-origin>)
  sin los ``data-sheets-value`` de Google, con todo el formato: anchos de
  columna (<col width> en px), alto de fila, fuente y tamaño, negrita,
  color, alineación, bordes de cada lado con su grosor y celdas combinadas.
* QGIS (Ctrl+C en la tabla de atributos): texto con tabulaciones y un HTML
  sin formato; la primera columna ``wkt_geom`` trae la geometría.
* LibreOffice Calc y Excel: su HTML (atributos sueltos o una hoja de estilo
  con clases); texto suelto o CSV: sólo los valores.

Python puro (sin Qt): IngeCAD y QGIS usan una copia idéntica.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser

PT_MM = 25.4 / 72.0
PX_MM = 25.4 / 96.0
#: altura de las mayúsculas / tamaño de la letra (Arial: 0,716): un texto de
#: CAD se mide por sus mayúsculas, una planilla por el cuerpo de la letra.
MAYUSCULA = 0.716
LADOS = ("arriba", "abajo", "izquierda", "derecha")

#: grosores de línea de DXF (centésimas de mm), los que ofrece AutoCAD
GROSORES_DXF = (0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90,
                100, 106, 120, 140, 158, 200, 211)

ORIGENES = {
    "genoffice": "GenOffice",
    "google": "Google Sheets",
    "libreoffice": "LibreOffice Calc",
    "excel": "Excel",
    "qgis": "QGIS (tabla de atributos)",
    "texto": "texto",
}


# ------------------------------------------------------------------ la tabla
@dataclass
class Borde:
    grosor_mm: float = 0.0          # 0 = sin borde
    color: str = "#000000"


@dataclass
class Celda:
    fila: int
    col: int
    texto: str = ""
    filas: int = 1                  # combinada hacia abajo
    cols: int = 1                   # combinada hacia la derecha
    fuente: str = ""
    tam_pt: float = 0.0             # 0 = el de la tabla
    negrita: bool = False
    cursiva: bool = False
    subrayado: bool = False
    color: str = ""                 # "" = negro / PorBloque
    fondo: str = ""                 # "" = sin fondo
    alin_h: str = ""                # izquierda / centro / derecha; "" = como la planilla
    alin_v: str = ""                # arriba / medio / abajo
    bordes: dict = field(default_factory=dict)   # lado -> Borde
    margen_mm: float = -1.0         # -1 = el de la tabla


@dataclass
class Tabla:
    celdas: list                    # sólo la celda que manda en cada combinada
    n_filas: int
    n_cols: int
    anchos_mm: list = field(default_factory=list)   # vacío o None = calcular
    altos_mm: list = field(default_factory=list)
    origen: str = "texto"
    fuente: str = ""
    tam_pt: float = 0.0
    con_formato: bool = False       # el HTML traía formato (no sólo valores)

    def grilla(self) -> list:
        """Los textos fila por fila; una combinada ocupa su primera casilla."""
        g = [["" for _ in range(self.n_cols)] for _ in range(self.n_filas)]
        for c in self.celdas:
            g[c.fila][c.col] = c.texto
        return g

    def encabezados(self) -> list:
        return self.grilla()[0] if self.n_filas else []

    def columna(self, nombre: str) -> int:
        """El índice de la columna con ese encabezado (sin distinguir
        mayúsculas), o -1."""
        nombre = nombre.strip().lower()
        for i, h in enumerate(self.encabezados()):
            if h.strip().lower() == nombre:
                return i
        return -1

    def con_bordes(self) -> bool:
        return any(b.grosor_mm > 0 for c in self.celdas for b in c.bordes.values())


def tabla_de_filas(filas: list, origen: str = "texto") -> Tabla:
    """Una tabla sin formato a partir de una lista de filas de textos."""
    n_cols = max((len(f) for f in filas), default=0)
    celdas = [Celda(r, c, str(v) if v is not None else "")
              for r, f in enumerate(filas) for c, v in enumerate(f)]
    return Tabla(celdas, len(filas), n_cols, origen=origen)


# ------------------------------------------------------------------ colores y medidas
_NOMBRES = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
            "blue": "#0000ff", "yellow": "#ffff00", "gray": "#808080", "grey": "#808080",
            "silver": "#c0c0c0", "maroon": "#800000", "navy": "#000080", "orange": "#ffa500",
            "purple": "#800080", "teal": "#008080", "lime": "#00ff00", "aqua": "#00ffff",
            "fuchsia": "#ff00ff", "olive": "#808000"}


def color(texto) -> str:
    """'#rrggbb' en minúsculas, o "" si no es un color (o es transparente)."""
    t = (texto or "").strip().lower()
    if not t or t in ("transparent", "none", "inherit", "initial", "auto", "windowtext"):
        return "#000000" if t == "windowtext" else ""
    if t in _NOMBRES:
        return _NOMBRES[t]
    m = re.fullmatch(r"#?([0-9a-f]{6})", t)
    if m:
        return "#" + m.group(1)
    m = re.fullmatch(r"#([0-9a-f]{3})", t)
    if m:
        return "#" + "".join(ch * 2 for ch in m.group(1))
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", t)
    if m:
        if m.group(4) is not None and float(m.group(4)) == 0:
            return ""
        return "#%02x%02x%02x" % tuple(min(255, int(m.group(i))) for i in (1, 2, 3))
    return ""


def rgb(hexa: str) -> tuple:
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))


def medida_mm(texto, por_defecto: float = 0.0, unidad: str = "px") -> float:
    """'2pt', '20px', '1.5mm', '0.3cm', '1in' o un número (en ``unidad``) a mm."""
    t = (str(texto) if texto is not None else "").strip().lower()
    m = re.match(r"^(-?[\d.]+)\s*(pt|px|mm|cm|in|em)?", t)
    if not m:
        return por_defecto
    try:
        v = float(m.group(1))
    except ValueError:
        return por_defecto
    u = m.group(2) or unidad
    return v * {"pt": PT_MM, "px": PX_MM, "mm": 1.0, "cm": 10.0, "in": 25.4,
                "em": 12 * PT_MM}.get(u, PX_MM)


def tam_pt(texto, por_defecto: float = 0.0) -> float:
    """Tamaño de letra de CSS o de <font size> en puntos."""
    t = (str(texto) if texto is not None else "").strip().lower()
    if re.fullmatch(r"[1-7]", t):                      # <font size="3">
        return (8, 10, 12, 14, 18, 24, 36)[int(t) - 1]
    if re.fullmatch(r"[\d.]+", t):
        try:
            return float(t)
        except ValueError:
            return por_defecto
    mm = medida_mm(t, -1.0, "pt")
    return mm / PT_MM if mm > 0 else por_defecto


def grosor_dxf(mm: float) -> int:
    """El grosor de DXF más cercano (centésimas de mm): 0,5 pt -> 18, 1 pt -> 35."""
    if mm <= 0:
        return 0
    cent = mm * 100.0
    return min(GROSORES_DXF[1:], key=lambda g: (abs(g - cent), g))


def estilo_css(texto: str) -> dict:
    """'a: b; c: d' -> {'a': 'b', 'c': 'd'} (propiedades en minúsculas)."""
    salida = {}
    for parte in (texto or "").split(";"):
        if ":" in parte:
            k, v = parte.split(":", 1)
            salida[k.strip().lower()] = v.strip()
    return salida


def _borde_css(valor: str) -> Borde | None:
    """'0.5pt solid #000000' -> Borde; 'none' / '0' -> Borde vacío; None si no dice nada."""
    v = (valor or "").strip().lower()
    if not v:
        return None
    if v in ("none", "0", "hidden") or v.startswith("none"):
        return Borde(0.0)
    grosor, col, estilo = None, "#000000", "solid"
    for parte in re.split(r"\s+(?![^(]*\))", v):
        if parte in ("none", "hidden"):
            return Borde(0.0)
        if parte in ("solid", "dashed", "dotted", "double", "groove", "ridge", "inset", "outset"):
            estilo = parte
        elif parte in ("thin", "medium", "thick"):
            grosor = {"thin": 0.5 * PT_MM, "medium": 1.0 * PT_MM, "thick": 1.5 * PT_MM}[parte]
        elif re.match(r"^[\d.]+(pt|px|mm|cm|in)?$", parte):
            grosor = medida_mm(parte, 0.0, "px")
        elif color(parte):
            col = color(parte)
    if grosor is None:
        grosor = 1.0 * PX_MM
    if estilo == "double":
        grosor *= 3
    return Borde(grosor, col)


# ------------------------------------------------------------------ de dónde viene
def detectar(html: str = "", texto: str = "", url: str = "") -> str:
    """El origen de lo copiado: una clave de ``ORIGENES``."""
    h = (html or "")[:20000].lower()
    u = (url or "").lower()
    if "genoffice" in u:
        return "genoffice"
    if "<google-sheets-html-origin" in h:
        return "google" if "data-sheets-value" in h or "docs.google.com" in u else "genoffice"
    primera = (texto or "").lstrip("﻿").split("\n", 1)[0]
    if primera.split("\t", 1)[0].strip().lower() == "wkt_geom":
        return "qgis"
    if (texto or "").lstrip().startswith("{") and '"featurecollection"' in (texto or "")[:400].lower():
        return "qgis"
    if "libreoffice" in h or "openoffice" in h or " sdval=" in h or " sdnum=" in h:
        return "libreoffice"
    if "urn:schemas-microsoft-com:office:excel" in h or "excel.sheet" in h:
        return "excel"
    return "texto"


# ------------------------------------------------------------------ texto con tabulaciones / CSV
def leer_texto(texto: str, origen: str = "texto") -> Tabla:
    """Texto con tabulaciones (lo que dejan todas las planillas y QGIS) o CSV."""
    texto = (texto or "").lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if texto.lstrip().startswith("{"):
        geo = _leer_geojson(texto)
        if geo is not None:
            return geo
    lineas = texto.split("\n")
    while lineas and not lineas[-1].strip():
        lineas.pop()
    if not lineas:
        return Tabla([], 0, 0, origen=origen)
    if any("\t" in ln for ln in lineas):
        filas = [ln.split("\t") for ln in lineas]
    else:
        muestra = "\n".join(lineas[:20])
        try:
            dialecto = csv.Sniffer().sniff(muestra, delimiters=";,|")
            filas = list(csv.reader(io.StringIO("\n".join(lineas)), dialecto))
        except csv.Error:
            filas = [[ln] for ln in lineas]
    filas = [[_sin_comillas(v) for v in f] for f in filas]
    return tabla_de_filas(filas, origen)


def _sin_comillas(v: str) -> str:
    v = v.strip("\n")
    if len(v) >= 2 and v[0] == v[-1] == '"':
        v = v[1:-1].replace('""', '"')
    return v


def _leer_geojson(texto: str) -> Tabla | None:
    """«Copiar objetos como GeoJSON» de QGIS: una fila por objeto, con la
    geometría como WKT en la columna wkt_geom."""
    try:
        datos = json.loads(texto)
    except ValueError:
        return None
    if not isinstance(datos, dict) or datos.get("type") != "FeatureCollection":
        return None
    feats = [f for f in datos.get("features", []) if isinstance(f, dict)]
    campos = []
    for f in feats:
        for k in (f.get("properties") or {}):
            if k not in campos:
                campos.append(k)
    filas = [["wkt_geom"] + campos]
    for f in feats:
        props = f.get("properties") or {}
        filas.append([geojson_a_wkt(f.get("geometry"))] +
                     ["" if props.get(k) is None else str(props.get(k)) for k in campos])
    return tabla_de_filas(filas, "qgis")


def geojson_a_wkt(g) -> str:
    if not isinstance(g, dict) or "coordinates" not in g:
        return ""
    t = g.get("type", "")

    def pts(lista):
        return ", ".join(f"{p[0]!r} {p[1]!r}" for p in lista)

    c = g["coordinates"]
    if t == "Point":
        return f"Point ({c[0]!r} {c[1]!r})"
    if t == "MultiPoint":
        return "MultiPoint (" + ", ".join(f"({p[0]!r} {p[1]!r})" for p in c) + ")"
    if t == "LineString":
        return f"LineString ({pts(c)})"
    if t == "MultiLineString":
        return "MultiLineString (" + ", ".join(f"({pts(l)})" for l in c) + ")"
    if t == "Polygon":
        return "Polygon (" + ", ".join(f"({pts(r)})" for r in c) + ")"
    if t == "MultiPolygon":
        return "MultiPolygon (" + ", ".join(
            "(" + ", ".join(f"({pts(r)})" for r in poly) + ")" for poly in c) + ")"
    return ""


# ------------------------------------------------------------------ HTML
_BLOQUE = {"p", "div", "li", "tr"}


class _LectorHTML(HTMLParser):
    """Lee la PRIMERA tabla del HTML, con el formato de cada celda."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.clases: dict = {}          # .xl65 -> {propiedades}  (Excel, LibreOffice)
        self._en_estilo = False
        self._css = []
        self.tabla_estilo: dict = {}
        self.cols: list = []            # anchos (mm) de <col>
        self.filas: list = []           # [(estilo de <tr>, [celdas crudas])]
        self._prof = 0                  # profundidad de <table>
        self._listo = False
        self._celda = None
        self._formato: list = []        # pila de formatos en línea dentro de la celda
        self.hubo_formato = False

    # estilos de una etiqueta: clase + atributos sueltos + style
    def _props(self, tag, attrs) -> dict:
        a = {k.lower(): (v or "") for k, v in attrs}
        p = {}
        for cl in a.get("class", "").split():
            p.update(self.clases.get(cl, {}))
            p.update(self.clases.get(f"{tag}.{cl}", {}))
        if "bgcolor" in a:
            p["background-color"] = a["bgcolor"]
        if "align" in a:
            p["text-align"] = a["align"]
        if "valign" in a:
            p["vertical-align"] = a["valign"]
        if tag == "font":
            if "face" in a:
                p["font-family"] = a["face"]
            if "size" in a:
                p["font-size"] = a["size"]
            if "color" in a:
                p["color"] = a["color"]
        if "width" in a:
            p.setdefault("width", a["width"])
        if "height" in a:
            p.setdefault("height", a["height"])
        p.update(estilo_css(a.get("style", "")))
        return p

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "style":
            self._en_estilo = True
            return
        if self._listo:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "table":
            self._prof += 1
            if self._prof == 1:
                self.tabla_estilo = self._props(tag, attrs)
            return
        if self._prof != 1:
            return
        if tag == "col":
            ancho = a.get("width") or estilo_css(a.get("style", "")).get("width", "")
            n = int(a.get("span", "1") or 1) if a.get("span", "1").isdigit() else 1
            self.cols.extend([medida_mm(ancho, 0.0, "px")] * max(1, n))
        elif tag == "tr":
            self.filas.append((self._props(tag, attrs), []))
        elif tag in ("td", "th"):
            if not self.filas:
                self.filas.append(({}, []))
            props = self._props(tag, attrs)
            if tag == "th":
                props.setdefault("font-weight", "bold")
            self._celda = {"props": props, "partes": [], "inline": {},
                           "cols": _entero(a.get("colspan")), "filas": _entero(a.get("rowspan"))}
            self._formato = []
            self.filas[-1][1].append(self._celda)
        elif self._celda is not None:
            if tag == "br":
                self._celda["partes"].append("\n")
            elif tag in _BLOQUE and self._celda["partes"]:
                self._celda["partes"].append("\n")
            props = self._props(tag, attrs)
            if tag in ("b", "strong"):
                props["font-weight"] = "bold"
            elif tag in ("i", "em"):
                props["font-style"] = "italic"
            elif tag == "u":
                props["text-decoration"] = "underline"
            if tag != "br":
                self._formato.append(props)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "style":
            self._en_estilo = False
            self.clases.update(_clases_css("".join(self._css)))
            self._css = []
            return
        if self._listo:
            return
        if tag == "table":
            self._prof -= 1
            if self._prof == 0 and self.filas:
                self._listo = True
            return
        if self._prof != 1:
            return
        if tag in ("td", "th"):
            self._celda = None
        elif self._celda is not None and self._formato and tag not in ("br",):
            self._formato.pop()

    def handle_data(self, data):
        if self._en_estilo:
            self._css.append(data)
            return
        if self._celda is None or self._listo:
            return
        if data.strip():
            # el formato en línea (<b>, <span style>) cuenta si cubre el texto
            for props in self._formato:
                self._celda["inline"].update(props)
        self._celda["partes"].append(data)


def _entero(v, defecto=1) -> int:
    try:
        return max(1, int(str(v).strip()))
    except (TypeError, ValueError):
        return defecto


def _clases_css(css: str) -> dict:
    """'.xl65 {color: red} td.b {..}' -> {'xl65': {...}, 'td.b': {...}}."""
    css = re.sub(r"/\*.*?\*/|<!--|-->", " ", css, flags=re.S)
    clases = {}
    for sel, cuerpo in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        props = estilo_css(cuerpo)
        for s in sel.split(","):
            s = s.strip()
            m = re.fullmatch(r"(\w*)\.([\w-]+)", s)
            if m:
                clave = f"{m.group(1)}.{m.group(2)}" if m.group(1) else m.group(2)
                clases.setdefault(clave, {}).update(props)
    return clases


def _texto_celda(partes) -> str:
    t = "".join(partes).replace("\xa0", " ")
    lineas = [re.sub(r"[ \t\r\n]+", " ", ln).strip() for ln in t.split("\n")]
    while lineas and not lineas[-1]:
        lineas.pop()
    while lineas and not lineas[0]:
        lineas.pop(0)
    return "\n".join(lineas)


def _primera_fuente(valor: str) -> str:
    f = (valor or "").split(",")[0].strip().strip("'\"")
    return "" if f.lower() in ("sans-serif", "serif", "monospace", "inherit") else f


_PROPS_FORMATO = ("font-weight", "font-style", "color", "background-color", "background",
                  "text-align", "border", "border-top", "border-bottom", "border-left",
                  "border-right", "font-family", "font-size")


def leer_html(html: str, origen: str = "") -> Tabla | None:
    """La primera tabla del HTML con su formato, o None si no hay tabla."""
    lector = _LectorHTML()
    try:
        lector.feed(html or "")
        lector.close()
    except Exception:  # noqa: BLE001 -- HTML roto: se usa el texto
        return None
    if not lector.filas or not any(cs for _, cs in lector.filas):
        return None
    t_est = lector.tabla_estilo
    fuente_tabla = _primera_fuente(t_est.get("font-family", ""))
    tam_tabla = tam_pt(t_est.get("font-size", ""), 0.0)
    # ubicar cada celda en la grilla (las combinadas ocupan varias casillas)
    ocupado = set()
    celdas, altos, con_formato = [], [], False
    n_cols = 0
    for r, (tr_props, crudas) in enumerate(lector.filas):
        altos.append(medida_mm(tr_props.get("height", ""), 0.0, "px"))
        c = 0
        for cr in crudas:
            while (r, c) in ocupado:
                c += 1
            p = dict(tr_props)
            p.pop("height", None)
            p.update(cr["props"])
            p.update({k: v for k, v in cr["inline"].items() if k != "width"})
            if any(k in p for k in _PROPS_FORMATO):
                con_formato = True
            celda = _celda_de(r, c, cr, p)
            if celda.filas == 1 and "height" in p and not altos[-1]:
                altos[-1] = medida_mm(p["height"], 0.0, "px")
            for dr in range(celda.filas):
                for dc in range(celda.cols):
                    ocupado.add((r + dr, c + dc))
            celdas.append(celda)
            c += celda.cols
            n_cols = max(n_cols, c)
    n_filas = max([r + 1 for r, _ in ocupado] + [len(lector.filas)])
    altos += [0.0] * (n_filas - len(altos))
    anchos = list(lector.cols[:n_cols]) + [0.0] * max(0, n_cols - len(lector.cols))
    # sin <col>: el ancho de las celdas sueltas
    for celda in celdas:
        w = getattr(celda, "_ancho", 0.0)
        if celda.cols == 1 and w and not anchos[celda.col]:
            anchos[celda.col] = w
    tabla = Tabla(celdas, n_filas, n_cols, anchos, altos, origen or detectar(html),
                  fuente_tabla, tam_tabla, con_formato)
    # una tabla que es sólo una celda vacía no sirve
    if not any(c.texto for c in celdas):
        return None
    return tabla


def _celda_de(r, c, cr, p) -> Celda:
    celda = Celda(r, c, _texto_celda(cr["partes"]), filas=cr["filas"], cols=cr["cols"])
    celda.fuente = _primera_fuente(p.get("font-family", ""))
    celda.tam_pt = tam_pt(p.get("font-size", ""), 0.0)
    peso = p.get("font-weight", "").lower()
    celda.negrita = peso in ("bold", "bolder") or (peso.isdigit() and int(peso) >= 600)
    celda.cursiva = p.get("font-style", "").lower() in ("italic", "oblique")
    celda.subrayado = "underline" in p.get("text-decoration", "").lower()
    celda.color = color(p.get("color", ""))
    fondo = p.get("background-color") or p.get("background", "")
    celda.fondo = color(fondo.split()[0] if fondo else "")
    if celda.fondo == "#ffffff":
        celda.fondo = ""                        # el blanco de la planilla es «sin fondo»
    al = p.get("text-align", "").lower()
    celda.alin_h = {"left": "izquierda", "start": "izquierda", "center": "centro",
                    "middle": "centro", "right": "derecha", "end": "derecha",
                    "justify": "izquierda"}.get(al, "")
    va = p.get("vertical-align", "").lower()
    celda.alin_v = {"top": "arriba", "middle": "medio", "center": "medio",
                    "bottom": "abajo"}.get(va, "")
    todos = _borde_css(p.get("border", ""))
    for lado, css in zip(LADOS, ("border-top", "border-bottom", "border-left", "border-right")):
        b = _borde_css(p.get(css, ""))
        b = b if b is not None else todos
        if b is not None:
            celda.bordes[lado] = b
    margenes = [medida_mm(p[k], -1.0, "px") for k in ("padding-left", "padding-right", "padding")
                if k in p]
    if margenes:
        celda.margen_mm = max(0.0, min(margenes))
    celda._ancho = medida_mm(p.get("width", ""), 0.0, "px")    # type: ignore[attr-defined]
    return celda


def leer(html: str = "", texto: str = "", url: str = "") -> Tabla | None:
    """Lo que hay en el portapapeles, como tabla (None si no hay nada).

    De QGIS se usa el texto: trae los valores exactos y la geometría completa
    (el HTML de QGIS no tiene formato). De una planilla, el HTML con su formato;
    si no lo hay o está roto, el texto."""
    origen = detectar(html, texto, url)
    tabla = None
    if html and origen != "qgis":
        tabla = leer_html(html, origen)
    if tabla is None and texto and texto.strip():
        tabla = leer_texto(texto, origen)
    if tabla is None and html:
        tabla = leer_html(html, origen)
    if tabla is None or not tabla.n_filas:
        return None
    tabla.origen = origen
    return tabla


# ------------------------------------------------------------------ elegir columnas
def sin_columnas(tabla: Tabla, quitar) -> Tabla:
    """La tabla sin las columnas ``quitar`` (índices). Las combinadas que
    cruzan una columna quitada se achican."""
    quitar = set(quitar)
    nuevo_idx, k = {}, 0
    for c in range(tabla.n_cols):
        if c not in quitar:
            nuevo_idx[c] = k
            k += 1
    celdas = []
    for c in tabla.celdas:
        quedan = [i for i in range(c.col, c.col + c.cols) if i not in quitar]
        if not quedan:
            continue
        celdas.append(replace(c, col=nuevo_idx[quedan[0]], cols=len(quedan),
                              bordes=dict(c.bordes)))
    anchos = [w for i, w in enumerate(tabla.anchos_mm or []) if i not in quitar]
    return Tabla(celdas, tabla.n_filas, k, anchos, list(tabla.altos_mm or []), tabla.origen,
                 tabla.fuente, tabla.tam_pt, tabla.con_formato)


# ------------------------------------------------------------------ armado
@dataclass
class Fondo:
    x0: float
    y0: float
    x1: float
    y1: float
    color: str


@dataclass
class Linea:
    x0: float
    y0: float
    x1: float
    y1: float
    grosor_mm: float
    color: str = "#000000"


@dataclass
class Texto:
    x: float
    y: float
    alin_h: str                     # izquierda / centro / derecha
    alin_v: str                     # arriba / medio / abajo
    alto_mm: float                  # altura de las mayúsculas
    texto: str
    fuente: str = ""
    negrita: bool = False
    cursiva: bool = False
    subrayado: bool = False
    color: str = ""
    ancho_mm: float = 0.0           # ancho de la celda (para cortar renglones)


@dataclass
class Armado:
    fondos: list
    lineas: list
    textos: list
    ancho_mm: float
    alto_mm: float


def _es_numero(t: str) -> bool:
    t = t.strip().replace(" ", "").replace("$", "").replace("%", "")
    if re.match(r"^0\d", t):            # «0001», una partida: es un código, no un número
        return False
    return bool(re.fullmatch(r"[-+]?(\d+([.,]\d+)*|\d*[.,]\d+)([eE][-+]?\d+)?", t))


def ancho_texto_mm(texto: str, alto_mm: float, negrita: bool = False) -> float:
    """Ancho aproximado de un renglón en Arial (sin medir la fuente): el
    promedio de Arial es 0,55 del cuerpo; las mayúsculas, 0,716."""
    if not texto:
        return 0.0
    cuerpo = alto_mm / MAYUSCULA
    ancho = 0.0
    for ch in texto:
        if ch in "il.,:;|!'ftjI ":
            f = 0.28
        elif ch in "mwMW@":
            f = 0.85
        elif ch.isupper():
            f = 0.67
        elif ch.islower():
            f = 0.50
        else:
            f = 0.56
        ancho += f * cuerpo
    return ancho * (1.07 if negrita else 1.0)


def armar(tabla: Tabla, respetar_formato: bool = True, alto_texto_mm: float = 2.5,
          encabezado: bool = True, grosor_mm: float = 0.25) -> Armado:
    """La tabla como fondos, líneas y textos en mm (esquina superior izquierda
    en 0, 0; y hacia abajo negativa).

    ``respetar_formato``: anchos, altos, letras, colores, alineación y bordes
    de la planilla (si los trae). Si no: estilo GeoCAD, todo con
    ``alto_texto_mm``, la grilla completa con ``grosor_mm`` y la primera fila
    en negrita si ``encabezado``."""
    formato = respetar_formato and tabla.con_formato
    n_f, n_c = tabla.n_filas, tabla.n_cols
    alto_base = alto_texto_mm
    if formato and tabla.tam_pt:
        alto_base = tabla.tam_pt * PT_MM * MAYUSCULA

    def alto_de(c: Celda) -> float:
        if formato and c.tam_pt:
            return c.tam_pt * PT_MM * MAYUSCULA
        return alto_base

    def margen_de(c: Celda) -> float:
        if formato and c.margen_mm >= 0:
            return c.margen_mm
        return max(0.5, 0.4 * alto_de(c))

    def negrita_de(c: Celda) -> bool:
        return (c.negrita if formato else False) or (encabezado and not formato and c.fila == 0)

    # anchos y altos: los de la planilla o calculados por el texto
    anchos = [0.0] * n_c
    altos = [0.0] * n_f
    if formato:
        anchos = [w if w and w > 0 else 0.0 for w in (list(tabla.anchos_mm or []) + [0.0] * n_c)[:n_c]]
        altos = [h if h and h > 0 else 0.0 for h in (list(tabla.altos_mm or []) + [0.0] * n_f)[:n_f]]
    necesita_w = [0.0] * n_c
    necesita_h = [0.0] * n_f
    for c in tabla.celdas:
        h = alto_de(c)
        m = margen_de(c)
        renglones = c.texto.split("\n") if c.texto else [""]
        if c.cols == 1:
            w = max(ancho_texto_mm(r, h, negrita_de(c)) for r in renglones) + 2 * m
            necesita_w[c.col] = max(necesita_w[c.col], w)
        if c.filas == 1:
            necesita_h[c.fila] = max(necesita_h[c.fila], len(renglones) * h * 1.6 + h * 0.6 + m)
    for i in range(n_c):
        if not anchos[i]:
            anchos[i] = max(necesita_w[i], 4 * alto_base)
    for i in range(n_f):
        if not altos[i]:
            altos[i] = max(necesita_h[i], 2.0 * alto_base)
    xs = [0.0]
    for w in anchos:
        xs.append(xs[-1] + w)
    ys = [0.0]
    for h in altos:
        ys.append(ys[-1] - h)

    def rect(c: Celda):
        return (xs[c.col], ys[c.fila], xs[min(n_c, c.col + c.cols)], ys[min(n_f, c.fila + c.filas)])

    fondos, textos = [], []
    for c in tabla.celdas:
        x0, y0, x1, y1 = rect(c)
        if formato and c.fondo:
            fondos.append(Fondo(x0, y0, x1, y1, c.fondo))
        if not c.texto:
            continue
        h, m = alto_de(c), margen_de(c)
        ah = c.alin_h if formato else ""
        if not ah:
            ah = "derecha" if (_es_numero(c.texto) and not (encabezado and c.fila == 0)) \
                else ("centro" if (not formato and encabezado and c.fila == 0) else "izquierda")
        av = (c.alin_v if formato else "") or ("abajo" if formato else "medio")
        x = {"izquierda": x0 + m, "centro": (x0 + x1) / 2, "derecha": x1 - m}[ah]
        y = {"arriba": y0 - m, "medio": (y0 + y1) / 2, "abajo": y1 + m}[av]
        textos.append(Texto(x, y, ah, av, h, c.texto,
                            (c.fuente or tabla.fuente) if formato else "",
                            negrita_de(c), c.cursiva if formato else False,
                            c.subrayado if formato else False,
                            c.color if formato and c.color not in ("#000000",) else "",
                            max(0.0, x1 - x0 - 2 * m)))
    lineas = _bordes(tabla, xs, ys, formato and tabla.con_bordes(), grosor_mm)
    return Armado(fondos, lineas, textos, xs[-1], -ys[-1])


def _bordes(tabla: Tabla, xs, ys, con_formato: bool, grosor: float) -> list:
    """Los bordes como líneas: cada tramo entre dos celdas vecinas una sola vez
    (con el borde más grueso de los dos lados) y los tramos seguidos iguales
    juntados en una línea. Sin formato: la grilla completa, salvo por dentro
    de las combinadas."""
    n_f, n_c = tabla.n_filas, tabla.n_cols
    horiz = {}      # (línea de fila, columna) -> Borde
    vert = {}       # (línea de columna, fila) -> Borde

    def poner(dic, clave, b):
        if b is None or b.grosor_mm <= 0:
            return
        actual = dic.get(clave)
        if actual is None or b.grosor_mm > actual.grosor_mm:
            dic[clave] = b

    if con_formato:
        for c in tabla.celdas:
            f1, c1 = c.fila + c.filas, c.col + c.cols
            for col in range(c.col, min(c1, n_c)):
                poner(horiz, (c.fila, col), c.bordes.get("arriba"))
                poner(horiz, (min(f1, n_f), col), c.bordes.get("abajo"))
            for fila in range(c.fila, min(f1, n_f)):
                poner(vert, (c.col, fila), c.bordes.get("izquierda"))
                poner(vert, (min(c1, n_c), fila), c.bordes.get("derecha"))
    else:
        dentro_h, dentro_v = set(), set()
        for c in tabla.celdas:
            for f in range(c.fila + 1, c.fila + c.filas):
                for col in range(c.col, c.col + c.cols):
                    dentro_h.add((f, col))
            for col in range(c.col + 1, c.col + c.cols):
                for f in range(c.fila, c.fila + c.filas):
                    dentro_v.add((col, f))
        b = Borde(grosor)
        for f in range(n_f + 1):
            for col in range(n_c):
                if (f, col) not in dentro_h:
                    horiz[(f, col)] = b
        for col in range(n_c + 1):
            for f in range(n_f):
                if (col, f) not in dentro_v:
                    vert[(col, f)] = b
    lineas = []
    for f in range(n_f + 1):
        col = 0
        while col < n_c:
            b = horiz.get((f, col))
            if b is None:
                col += 1
                continue
            fin = col
            while fin + 1 < n_c and horiz.get((f, fin + 1)) == b:
                fin += 1
            lineas.append(Linea(xs[col], ys[f], xs[fin + 1], ys[f], b.grosor_mm, b.color))
            col = fin + 1
    for col in range(n_c + 1):
        f = 0
        while f < n_f:
            b = vert.get((col, f))
            if b is None:
                f += 1
                continue
            fin = f
            while fin + 1 < n_f and vert.get((col, fin + 1)) == b:
                fin += 1
            lineas.append(Linea(xs[col], ys[f], xs[col], ys[fin + 1], b.grosor_mm, b.color))
            f = fin + 1
    return lineas


# ------------------------------------------------------------------ geometría (WKT de QGIS)
def wkt_partes(wkt: str) -> list:
    """WKT -> [("punto", [(x, y)]), ("linea", [...]), ("poligono", [anillo, ...])].
    Acepta Z / M (se queda con x, y), Multi* y GeometryCollection."""
    texto = (wkt or "").strip()
    if not texto:
        return []
    pos = [0]

    def saltar():
        while pos[0] < len(texto) and texto[pos[0]].isspace():
            pos[0] += 1

    def palabra():
        saltar()
        m = re.match(r"[A-Za-z]+", texto[pos[0]:])
        if not m:
            return ""
        pos[0] += m.end()
        return m.group(0).upper()

    def lista():
        """'(' ... ')' anidado -> listas anidadas de tuplas (x, y)."""
        saltar()
        if texto[pos[0]:pos[0] + 1] != "(":
            raise ValueError("se esperaba (")
        pos[0] += 1
        items = []
        while True:
            saltar()
            ch = texto[pos[0]:pos[0] + 1]
            if ch == "(":
                items.append(lista())
            elif ch == ")":
                pos[0] += 1
                return items
            elif ch == ",":
                pos[0] += 1
            else:
                m = re.match(r"[-+\d.eE]+(\s+[-+\d.eE]+)+", texto[pos[0]:])
                if not m:
                    raise ValueError("coordenada")
                nums = m.group(0).split()
                items.append((float(nums[0]), float(nums[1])))
                pos[0] += m.end()

    def geometria():
        tipo = palabra()
        while True:                      # Z, M, ZM
            saltar()
            m = re.match(r"(ZM|Z|M)\b", texto[pos[0]:], re.I)
            if not m:
                break
            pos[0] += m.end()
        saltar()
        if texto[pos[0]:pos[0] + 5].upper() == "EMPTY":
            pos[0] += 5
            return []
        if tipo == "GEOMETRYCOLLECTION":
            saltar()
            pos[0] += 1
            partes = []
            while True:
                saltar()
                if texto[pos[0]:pos[0] + 1] == ")":
                    pos[0] += 1
                    return partes
                if texto[pos[0]:pos[0] + 1] == ",":
                    pos[0] += 1
                    continue
                partes += geometria()
        datos = lista()
        if tipo == "POINT":
            return [("punto", datos)]
        if tipo == "MULTIPOINT":
            return [("punto", [p if isinstance(p, tuple) else p[0]]) for p in datos]
        if tipo in ("LINESTRING", "CIRCULARSTRING"):
            return [("linea", datos)]
        if tipo == "MULTILINESTRING":
            return [("linea", l) for l in datos]
        if tipo == "POLYGON":
            return [("poligono", datos)]
        if tipo == "MULTIPOLYGON":
            return [("poligono", p) for p in datos]
        raise ValueError(f"tipo {tipo}")

    try:
        return geometria()
    except (ValueError, IndexError):
        return []


def area_anillo(anillo) -> float:
    """Área con signo (positiva = antihorario)."""
    s = 0.0
    for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1]):
        s += x0 * y1 - x1 * y0
    return s / 2.0


def punto_rotulo(partes) -> tuple | None:
    """Dónde va el rótulo: el centro del polígono más grande, la mitad del
    largo de la línea más larga o el primer punto."""
    polis = [p for t, p in partes if t == "poligono" and p and len(p[0]) >= 3]
    if polis:
        anillo = max((p[0] for p in polis), key=lambda a: abs(area_anillo(a)))
        a = area_anillo(anillo)
        if abs(a) > 1e-12:
            cx = cy = 0.0
            for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1]):
                k = x0 * y1 - x1 * y0
                cx += (x0 + x1) * k
                cy += (y0 + y1) * k
            centro = (cx / (6 * a), cy / (6 * a))
            if dentro(centro, anillo):
                return centro
        return _punto_interior(anillo)
    lineas = [p for t, p in partes if t == "linea" and len(p) >= 2]
    if lineas:
        linea = max(lineas, key=_largo)
        mitad, recorrido = _largo(linea) / 2.0, 0.0
        for (x0, y0), (x1, y1) in zip(linea, linea[1:]):
            d = math.hypot(x1 - x0, y1 - y0)
            if recorrido + d >= mitad and d > 0:
                t = (mitad - recorrido) / d
                return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
            recorrido += d
        return linea[0]
    puntos = [p[0] for t, p in partes if t == "punto" and p]
    return puntos[0] if puntos else None


def _largo(linea) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(linea, linea[1:]))


def dentro(p, anillo) -> bool:
    x, y = p
    adentro = False
    for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1]):
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                adentro = not adentro
    return adentro


def _punto_interior(anillo):
    """Un polígono en forma de C: el punto medio del tramo horizontal más
    largo que cruza la altura media."""
    ys = [p[1] for p in anillo]
    y = (min(ys) + max(ys)) / 2.0
    cortes = []
    for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1]):
        if (y0 > y) != (y1 > y):
            cortes.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
    cortes.sort()
    tramos = [(cortes[i], cortes[i + 1]) for i in range(0, len(cortes) - 1, 2)]
    if not tramos:
        return anillo[0]
    a, b = max(tramos, key=lambda t: t[1] - t[0])
    return ((a + b) / 2.0, y)


def columnas_xy(tabla: Tabla) -> tuple:
    """Las columnas de X e Y de una planilla de coordenadas, por su nombre
    (X/Y, Este/Norte, E/N, Longitud/Latitud), o (-1, -1)."""
    nombres = [h.strip().lower() for h in tabla.encabezados()]
    pares = (("x", "y"), ("este", "norte"), ("e", "n"), ("easting", "northing"),
             ("lon", "lat"), ("longitud", "latitud"), ("longitude", "latitude"))
    for a, b in pares:
        if a in nombres and b in nombres:
            return nombres.index(a), nombres.index(b)
    return -1, -1


def numero(t: str):
    """'7.425.885,37' / '7425885.37' / '1,5' -> float, o None."""
    t = (t or "").strip().replace(" ", "").replace("\xa0", "")
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif t.count(".") > 1:                  # 7.020.000: puntos de miles
        t = t.replace(".", "")
    elif t.count(",") > 1:                  # 7,020,000: comas de miles
        t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if math.isfinite(v) else None
