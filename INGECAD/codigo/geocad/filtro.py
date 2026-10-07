# SPDX-License-Identifier: GPL-3.0-or-later
"""FILTRO (FI): filtros de selección como el FILTER de AutoCAD (3.2.0).

Una lista de condiciones (todas se cumplen, como en AutoCAD) sobre el tipo
de objeto y sus propiedades, con los grupos Comenzar/Terminar Y, O, XO y NO.
Las condiciones son diccionarios simples (se guardan en JSON):

    {"p": "circulo"}                                  un tipo de objeto
    {"p": "capa", "op": "=", "v": "*-ROTULOS"}        texto, con comodines
    {"p": "radio_circulo", "op": ">", "v": 2.5}       número
    {"p": "centro_circulo", "x": ["<", 100], "y": ["*", 0]}   punto
    {"p": "campo_qgis", "campo": "PROPIETARI", "op": "=", "v": "PEREZ*"}
    {"p": "**O("} ... {"p": "**O)"}                   grupos

Una propiedad de un tipo (p. ej. el radio de un círculo) sólo la cumplen
los objetos de ese tipo, como en AutoCAD. Los textos se comparan sin
distinguir mayúsculas; «*» y «?» son comodines y la coma separa
alternativas («MUROS,EJES»).

Los filtros con nombre se guardan en ~/.config/geocad/filtros.json (los
comparten todos los dibujos). Esta parte no usa Qt: la ventana está en
filtro_ui.py.
"""
from __future__ import annotations

import fnmatch
import json
import math
from dataclasses import dataclass

from . import buzon

#: operadores: números y coordenadas usan todos; textos, = y !=
OPS = ("=", "!=", "<", "<=", ">", ">=", "*")
OPS_TEXTO = ("=", "!=")

#: grupos: clave -> (operador, abre)
GRUPOS = {
    "**Y(": ("Y", True), "**Y)": ("Y", False),
    "**O(": ("O", True), "**O)": ("O", False),
    "**XO(": ("XO", True), "**XO)": ("XO", False),
    "**NO(": ("NO", True), "**NO)": ("NO", False),
}
NOMBRE_GRUPO = {"Y": "Y", "O": "O", "XO": "XO (uno u otro)", "NO": "NO"}


@dataclass(frozen=True)
class Prop:
    clave: str
    nombre: str
    clase: str              # tipo, texto, numero, punto, color, campo, grupo
    tipos: tuple = ()       # dxftypes a los que se aplica (vacío = todos)


def _P(clave, nombre, clase, *tipos):
    return Prop(clave, nombre, clase, tuple(tipos))


LINEALES = ("LINE", "ARC", "CIRCLE", "ELLIPSE", "LWPOLYLINE", "POLYLINE", "SPLINE")

#: el catálogo, en el orden de la lista de la ventana
PROPIEDADES = (
    # tipos de objeto
    _P("arco", "Arco", "tipo", "ARC"),
    _P("bloque", "Bloque", "tipo", "INSERT"),
    _P("circulo", "Círculo", "tipo", "CIRCLE"),
    _P("cota", "Cota", "tipo", "DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION"),
    _P("directriz", "Directriz", "tipo", "LEADER", "MULTILEADER"),
    _P("elipse", "Elipse", "tipo", "ELLIPSE"),
    _P("imagen", "Imagen", "tipo", "IMAGE"),
    _P("linea", "Línea", "tipo", "LINE"),
    _P("linea_aux", "Línea auxiliar", "tipo", "XLINE"),
    _P("polilinea", "Polilínea", "tipo", "LWPOLYLINE", "POLYLINE"),
    _P("punto", "Punto", "tipo", "POINT"),
    _P("rayo", "Rayo", "tipo", "RAY"),
    _P("sombreado", "Sombreado", "tipo", "HATCH"),
    _P("spline", "Spline", "tipo", "SPLINE"),
    _P("texto", "Texto", "tipo", "TEXT"),
    _P("texto_m", "Texto múltiple", "tipo", "MTEXT"),
    # geometría
    _P("centro_arco", "Centro de arco", "punto", "ARC"),
    _P("radio_arco", "Radio de arco", "numero", "ARC"),
    _P("centro_circulo", "Centro de círculo", "punto", "CIRCLE"),
    _P("radio_circulo", "Radio de círculo", "numero", "CIRCLE"),
    _P("diametro_circulo", "Diámetro de círculo", "numero", "CIRCLE"),
    _P("centro_elipse", "Centro de elipse", "punto", "ELLIPSE"),
    _P("inicio_linea", "Inicio de línea", "punto", "LINE"),
    _P("fin_linea", "Fin de línea", "punto", "LINE"),
    _P("pos_punto", "Posición de punto", "punto", "POINT"),
    _P("pos_texto", "Posición de texto", "punto", "TEXT", "MTEXT"),
    _P("pos_bloque", "Posición de bloque", "punto", "INSERT"),
    # nombres y textos
    _P("nombre_bloque", "Nombre de bloque", "texto", "INSERT"),
    _P("etiqueta_atributo", "Etiqueta de atributo", "texto", "INSERT"),
    _P("valor_atributo", "Valor de atributo", "texto", "INSERT"),
    _P("valor_texto", "Valor de texto", "texto", "TEXT", "MTEXT"),
    _P("altura_texto", "Altura de texto", "numero", "TEXT", "MTEXT"),
    _P("giro_texto", "Giro de texto", "numero", "TEXT", "MTEXT"),
    _P("estilo_texto", "Estilo de texto", "texto", "TEXT", "MTEXT"),
    _P("patron_sombreado", "Patrón de sombreado", "texto", "HATCH"),
    _P("estilo_cota", "Estilo de cota", "texto", "DIMENSION", "ARC_DIMENSION",
       "LARGE_RADIAL_DIMENSION"),
    # propiedades generales
    _P("color", "Color", "color"),
    _P("capa", "Capa", "texto"),
    _P("tipo_linea", "Tipo de línea", "texto"),
    _P("escala_tipo_linea", "Escala de tipo de línea", "numero"),
    _P("grosor", "Grosor de línea (mm)", "numero"),
    _P("elevacion", "Elevación", "numero"),
    _P("espesor", "Espesor", "numero"),
    # de GeoCAD (AutoCAD no los tiene)
    _P("largo", "Largo (líneas, arcos, polilíneas...)", "numero", *LINEALES),
    _P("area", "Área (cerrados)", "numero", "CIRCLE", "ELLIPSE", "LWPOLYLINE",
       "POLYLINE", "SPLINE", "HATCH"),
    _P("cerrada", "Polilínea cerrada", "tipo", "LWPOLYLINE", "POLYLINE"),
    _P("conexion", "Conexión de QGIS", "texto"),
    _P("campo_qgis", "Campo de la tabla de QGIS", "campo"),
    _P("rotulo_qgis", "Rótulo de QGIS", "tipo", "TEXT", "MTEXT"),
    _P("fondo_rotulo", "Fondo de rótulo de QGIS", "tipo"),
    _P("simbolo", "Símbolo de punto de GeoCAD", "tipo", "INSERT"),
    # grupos
    _P("**Y(", "** Comenzar Y", "grupo"), _P("**Y)", "** Terminar Y", "grupo"),
    _P("**O(", "** Comenzar O", "grupo"), _P("**O)", "** Terminar O", "grupo"),
    _P("**XO(", "** Comenzar XO", "grupo"), _P("**XO)", "** Terminar XO", "grupo"),
    _P("**NO(", "** Comenzar NO", "grupo"), _P("**NO)", "** Terminar NO", "grupo"),
)
POR_CLAVE = {p.clave: p for p in PROPIEDADES}


class FiltroError(ValueError):
    pass


# --------------------------------------------------------------- lectura
def _dxf(e, nombre, defecto=None):
    try:
        return e.dxf.get(nombre, defecto)
    except Exception:  # noqa: BLE001
        return defecto


def _xy(v):
    try:
        return (float(v[0]), float(v[1]))
    except (TypeError, ValueError, IndexError):
        return None


def _xdata(e):
    try:
        from core.xdata import APPID
        return [v for _c, v in e.get_xdata(APPID)]
    except Exception:  # noqa: BLE001
        return []


def _es_rotulo(e) -> bool:
    from .herramientas_datos import LABEL_TAG
    vals = _xdata(e)
    return len(vals) >= 2 and vals[0] == LABEL_TAG


def _puntos(e, tramo=None):
    """Puntos de la figura (aproximada con tramos rectos), o []."""
    try:
        from ezdxf import path
        p = path.make_path(e)
        return [(v.x, v.y) for v in p.flattening(distance=tramo or 0.001, segments=16)]
    except Exception:  # noqa: BLE001
        return []


def largo(e):
    t = e.dxftype()
    if t == "LINE":
        a, b = e.dxf.start, e.dxf.end
        return math.hypot(b[0] - a[0], b[1] - a[1])
    if t == "CIRCLE":
        return 2 * math.pi * e.dxf.radius
    if t == "ARC":
        span = (e.dxf.end_angle - e.dxf.start_angle) % 360.0 or 360.0
        return math.radians(span) * e.dxf.radius
    pts = _puntos(e)
    if len(pts) < 2:
        return None
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _cerrada(e) -> bool:
    t = e.dxftype()
    if t in ("LWPOLYLINE", "POLYLINE"):
        try:
            return bool(e.closed if t == "LWPOLYLINE" else e.is_closed)
        except Exception:  # noqa: BLE001
            return False
    if t == "SPLINE":
        try:
            return bool(e.closed)
        except Exception:  # noqa: BLE001
            return False
    if t == "ELLIPSE":
        return abs((e.dxf.end_param - e.dxf.start_param) - 2 * math.pi) < 1e-9 or \
            abs(e.dxf.end_param - e.dxf.start_param) < 1e-12
    return t in ("CIRCLE", "HATCH")


def area(e):
    t = e.dxftype()
    if t == "CIRCLE":
        return math.pi * e.dxf.radius ** 2
    if t == "HATCH":
        total = 0.0
        try:
            from ezdxf import path
            for p in path.from_hatch(e):
                pts = [(v.x, v.y) for v in p.flattening(distance=0.001, segments=16)]
                total += _shoelace(pts)
        except Exception:  # noqa: BLE001
            return None
        return abs(total)
    if not _cerrada(e):
        return None
    pts = _puntos(e)
    return abs(_shoelace(pts)) if len(pts) >= 3 else None


def _shoelace(pts) -> float:
    if len(pts) < 3:
        return 0.0
    s = 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        s += ax * by - bx * ay
    return s / 2.0


def _atributos(e):
    try:
        return list(e.attribs)
    except Exception:  # noqa: BLE001
        return []


def _texto_de(e):
    if e.dxftype() == "MTEXT":
        try:
            return e.plain_text()
        except Exception:  # noqa: BLE001
            return e.text
    return _dxf(e, "text", "")


def valor(e, clave: str, ctx=None):
    """El valor de la propiedad ``clave`` en ``e`` (None si no la tiene).
    Para los textos puede devolver una lista (se cumple si alguno coincide)."""
    t = e.dxftype()
    if clave in ("centro_arco", "centro_circulo", "centro_elipse"):
        return _xy(_dxf(e, "center"))
    if clave in ("radio_arco", "radio_circulo"):
        return _dxf(e, "radius")
    if clave == "diametro_circulo":
        r = _dxf(e, "radius")
        return None if r is None else 2 * r
    if clave == "inicio_linea":
        return _xy(_dxf(e, "start"))
    if clave == "fin_linea":
        return _xy(_dxf(e, "end"))
    if clave in ("pos_punto",):
        return _xy(_dxf(e, "location"))
    if clave in ("pos_texto", "pos_bloque"):
        return _xy(_dxf(e, "insert"))
    if clave == "nombre_bloque":
        return _dxf(e, "name")
    if clave == "etiqueta_atributo":
        return [a.dxf.tag for a in _atributos(e)]
    if clave == "valor_atributo":
        return [a.dxf.text for a in _atributos(e)]
    if clave == "valor_texto":
        return _texto_de(e)
    if clave == "altura_texto":
        return _dxf(e, "char_height") if t == "MTEXT" else _dxf(e, "height")
    if clave == "giro_texto":
        return _dxf(e, "rotation", 0.0)
    if clave == "estilo_texto":
        return _dxf(e, "style", "Standard")
    if clave == "patron_sombreado":
        return _dxf(e, "pattern_name")
    if clave == "estilo_cota":
        return _dxf(e, "dimstyle")
    if clave == "color":
        return _dxf(e, "color", 256)
    if clave == "capa":
        return _dxf(e, "layer", "0")
    if clave == "tipo_linea":
        return _dxf(e, "linetype", "BYLAYER")
    if clave == "escala_tipo_linea":
        return _dxf(e, "ltscale", 1.0)
    if clave == "grosor":
        lw = _dxf(e, "lineweight", -1)
        return lw / 100.0 if lw is not None and lw >= 0 else lw
    if clave == "elevacion":
        if t in ("LWPOLYLINE", "HATCH"):
            return _dxf(e, "elevation", 0.0) if t == "LWPOLYLINE" else _dxf(e, "elevation", (0, 0, 0))[2]
        for nombre in ("insert", "center", "start", "location"):
            p = _dxf(e, nombre)
            if p is not None:
                try:
                    return float(p[2])
                except (TypeError, IndexError):
                    return 0.0
        return 0.0
    if clave == "espesor":
        return _dxf(e, "thickness", 0.0)
    if clave == "largo":
        return largo(e)
    if clave == "area":
        return area(e)
    if clave == "conexion":
        from . import enlace
        tag = enlace.feat_tag(e)
        if tag is not None:
            return tag.key
        vals = _xdata(e)
        return vals[1] if len(vals) >= 2 and _es_rotulo(e) else None
    return None


def _cumple_tipo(e, clave: str) -> bool:
    t = e.dxftype()
    if clave == "cerrada":
        return t in ("LWPOLYLINE", "POLYLINE") and _cerrada(e)
    if clave == "rotulo_qgis":
        return t in ("TEXT", "MTEXT") and _es_rotulo(e)
    if clave == "fondo_rotulo":
        return t not in ("TEXT", "MTEXT") and _es_rotulo(e)
    if clave == "simbolo":
        from .estilo import SYMBOL_BLOCK
        return t == "INSERT" and str(_dxf(e, "name", "")).upper().startswith(SYMBOL_BLOCK)
    return t in POR_CLAVE[clave].tipos


# ---------------------------------------------------------- comparación
def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def comparar_numero(actual, op: str, buscado) -> bool:
    if op == "*":
        return actual is not None
    a, b = _num(actual), _num(buscado)
    if a is None or b is None:
        return False
    tol = 1e-6 * max(1.0, abs(b))
    return {"=": abs(a - b) <= tol, "!=": abs(a - b) > tol, "<": a < b - tol,
            "<=": a <= b + tol, ">": a > b + tol, ">=": a >= b - tol}.get(op, False)


def comparar_texto(actual, op: str, buscado) -> bool:
    """Sin distinguir mayúsculas; * y ? comodines; la coma separa opciones.
    Con una lista (atributos), se cumple si alguno coincide."""
    if isinstance(actual, (list, tuple)):
        hit = any(comparar_texto(a, "=", buscado) for a in actual)
        return hit if op != "!=" else not hit
    if actual is None:
        return False
    a = str(actual).upper()
    patrones = [p.strip().upper() for p in str(buscado if buscado is not None else "").split(",")]
    hit = any(fnmatch.fnmatchcase(a, p) for p in patrones)
    if op == "*":
        return True
    return hit if op != "!=" else not hit


COLORES = {"PORCAPA": 256, "BYLAYER": 256, "PORBLOQUE": 0, "BYBLOCK": 0,
           "ROJO": 1, "RED": 1, "AMARILLO": 2, "YELLOW": 2, "VERDE": 3, "GREEN": 3,
           "CIAN": 4, "CYAN": 4, "AZUL": 5, "BLUE": 5, "MAGENTA": 6,
           "BLANCO": 7, "WHITE": 7, "NEGRO": 7}


def numero_de_color(v):
    """1-255, 256 = PorCapa, 0 = PorBloque; acepta el número o el nombre."""
    if isinstance(v, (int, float)):
        return int(v)
    t = str(v or "").strip().upper()
    if t in COLORES:
        return COLORES[t]
    if " - " in t:                               # «1 - Rojo», como AutoCAD
        t = t.split(" - ", 1)[0]
    try:
        return int(float(t))
    except ValueError:
        return None


class Campos:
    """Los valores de la tabla de QGIS de cada conexión, leídos una sola vez
    por filtrado."""

    def __init__(self, document) -> None:
        self.document = document
        self._por_key: dict = {}

    def de(self, e, campo: str):
        from . import enlace
        tag = enlace.feat_tag(e)
        if tag is None or self.document is None:
            return None
        filas = self._por_key.get(tag.key)
        if filas is None:
            try:
                from . import datos
                data = datos.LayerData(self.document, tag.key)
                filas = {r.fid: {k.upper(): v for k, v in r.values.items()} for r in data.rows}
            except Exception:  # noqa: BLE001
                filas = {}
            self._por_key[tag.key] = filas
        fila = filas.get(tag.fid)
        if fila is None:
            return None
        return fila.get(str(campo).strip().upper(), _SIN_CAMPO)


_SIN_CAMPO = object()


def cumple(e, cond: dict, ctx=None) -> bool:
    """¿El objeto ``e`` cumple una condición (no un grupo)?"""
    clave = cond.get("p")
    prop = POR_CLAVE.get(clave)
    if prop is None:
        raise FiltroError(f"propiedad desconocida: {clave}")
    if prop.clase == "tipo":
        return _cumple_tipo(e, clave)
    if prop.tipos and e.dxftype() not in prop.tipos:
        return False
    op = cond.get("op", "=")
    if prop.clase == "campo":
        if ctx is None:
            return False
        v = ctx.de(e, cond.get("campo", ""))
        if v is None or v is _SIN_CAMPO:
            return False
        if _num(v) is not None and _num(cond.get("v")) is not None and op != "*":
            return comparar_numero(v, op, cond.get("v"))
        return comparar_texto(v, op if op in ("=", "!=", "*") else "=", cond.get("v"))
    actual = valor(e, clave, ctx)
    if prop.clase == "punto":
        if actual is None:
            return False
        for i, eje in enumerate(("x", "y")):
            par = cond.get(eje) or ["*", 0]
            if not comparar_numero(actual[i], par[0], par[1]):
                return False
        return True
    if prop.clase == "numero":
        return comparar_numero(actual, op, cond.get("v"))
    if prop.clase == "color":
        if op == "*":
            return True
        return comparar_numero(actual, op, numero_de_color(cond.get("v")))
    return comparar_texto(actual, op, cond.get("v"))


# ---------------------------------------------------------------- grupos
def arbol(conds):
    """La lista de condiciones como árbol ("Y", [hijos]); FiltroError si los
    grupos no están bien abiertos y cerrados."""
    pila = [("Y", [])]
    for c in conds:
        clave = c.get("p")
        if clave in GRUPOS:
            op, abre = GRUPOS[clave]
            if abre:
                pila.append((op, []))
                continue
            if len(pila) == 1 or pila[-1][0] != op:
                raise FiltroError(f"«Terminar {op}» sin su «Comenzar {op}»")
            op_, hijos = pila.pop()
            if op_ == "NO" and len(hijos) != 1:
                raise FiltroError("NO lleva exactamente una condición (o un grupo)")
            if op_ == "XO" and len(hijos) != 2:
                raise FiltroError("XO lleva exactamente dos condiciones (o grupos)")
            if not hijos:
                raise FiltroError(f"el grupo {op_} está vacío")
            pila[-1][1].append((op_, hijos))
        else:
            if POR_CLAVE.get(clave) is None:
                raise FiltroError(f"propiedad desconocida: {clave}")
            pila[-1][1].append(c)
    if len(pila) > 1:
        raise FiltroError(f"falta «Terminar {pila[-1][0]}»")
    return pila[0]


def _evaluar(e, nodo, ctx) -> bool:
    if isinstance(nodo, dict):
        return cumple(e, nodo, ctx)
    op, hijos = nodo
    if op == "Y":
        return all(_evaluar(e, h, ctx) for h in hijos)
    if op == "O":
        return any(_evaluar(e, h, ctx) for h in hijos)
    if op == "XO":
        return _evaluar(e, hijos[0], ctx) != _evaluar(e, hijos[1], ctx)
    return not _evaluar(e, hijos[0], ctx)            # NO


def filtrar(entidades, conds, document=None) -> list:
    """Las entidades que cumplen el filtro (todas si la lista está vacía)."""
    raiz = arbol(conds)
    ctx = Campos(document)
    return [e for e in entidades if _evaluar(e, raiz, ctx)]


# ----------------------------------------------------- texto para la lista
def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def describir(cond: dict) -> tuple:
    """(propiedad, operador y valor) como los muestra la lista de la ventana."""
    clave = cond.get("p")
    prop = POR_CLAVE.get(clave)
    if prop is None:
        return (str(clave), "")
    if prop.clase in ("tipo", "grupo"):
        return (prop.nombre, "")
    if prop.clase == "punto":
        partes = []
        for eje in ("x", "y"):
            op, v = (cond.get(eje) or ["*", 0])[:2]
            partes.append(f"{eje.upper()} {op}" + ("" if op == "*" else f" {_fmt(v)}"))
        return (prop.nombre, ",  ".join(partes))
    op = cond.get("op", "=")
    if prop.clase == "campo":
        return (f"{prop.nombre}: {cond.get('campo', '')}",
                f"{op}" + ("" if op == "*" else f" {_fmt(cond.get('v', ''))}"))
    if prop.clase == "color":
        n = numero_de_color(cond.get("v"))
        nombre = {256: "PorCapa", 0: "PorBloque", 1: "1 - Rojo", 2: "2 - Amarillo",
                  3: "3 - Verde", 4: "4 - Cian", 5: "5 - Azul", 6: "6 - Magenta",
                  7: "7 - Blanco"}.get(n, str(n))
        return (prop.nombre, f"{op}" + ("" if op == "*" else f" {nombre}"))
    return (prop.nombre, f"{op}" + ("" if op == "*" else f" {_fmt(cond.get('v', ''))}"))


def sangrias(conds) -> list:
    """Cuánto sangrar cada renglón de la lista (dentro de los grupos)."""
    out, nivel = [], 0
    for c in conds:
        g = GRUPOS.get(c.get("p"))
        if g is not None and not g[1]:
            nivel = max(0, nivel - 1)
        out.append(nivel)
        if g is not None and g[1]:
            nivel += 1
    return out


# ------------------------------------------------- «agregar objeto seleccionado»
def de_objeto(e) -> list:
    """Las condiciones que describen ``e`` (como «Añadir objeto seleccionado»
    de AutoCAD): el tipo, la capa, el color y sus propiedades propias."""
    t = e.dxftype()
    out = []
    for p in PROPIEDADES:
        if p.clase == "tipo" and p.clave not in ("cerrada", "rotulo_qgis", "fondo_rotulo",
                                                 "simbolo") and t in p.tipos:
            out.append({"p": p.clave})
            break
    out.append({"p": "capa", "op": "=", "v": valor(e, "capa")})
    out.append({"p": "color", "op": "=", "v": valor(e, "color")})
    for p in PROPIEDADES:
        if not p.tipos or t not in p.tipos or p.clase not in ("numero", "punto", "texto"):
            continue
        if p.clave in ("largo", "area", "diametro_circulo", "etiqueta_atributo",
                       "valor_atributo", "giro_texto"):
            continue
        v = valor(e, p.clave)
        if v is None:
            continue
        if p.clase == "punto":
            out.append({"p": p.clave, "x": ["=", round(v[0], 6)], "y": ["=", round(v[1], 6)]})
        else:
            out.append({"p": p.clave, "op": "=", "v": round(v, 6) if isinstance(v, float) else v})
    return out


# ---------------------------------------------------------- guardados
SIN_NOMBRE = "*sin nombre"


def _archivo():
    return buzon.base_dir() / "filtros.json"


def guardados() -> dict:
    """{nombre: [condiciones]} (incluye «*sin nombre», el último usado)."""
    try:
        data = json.loads(_archivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    filtros = data.get("filtros") if isinstance(data, dict) else None
    if not isinstance(filtros, dict):
        return {}
    return {str(k): list(v) for k, v in filtros.items() if isinstance(v, list)}


def _escribir(filtros: dict) -> None:
    ruta = _archivo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "filtros": filtros}, ensure_ascii=False,
                              indent=1), encoding="utf-8")
    tmp.replace(ruta)


def guardar(nombre: str, conds) -> None:
    nombre = str(nombre).strip()
    if not nombre:
        raise FiltroError("falta el nombre")
    arbol(conds)                                # no se guarda un filtro roto
    filtros = guardados()
    filtros[nombre] = list(conds)
    _escribir(filtros)


def borrar(nombre: str) -> bool:
    filtros = guardados()
    if nombre not in filtros:
        return False
    del filtros[nombre]
    _escribir(filtros)
    return True


def buscar(nombre: str):
    """El filtro guardado con ese nombre (sin distinguir mayúsculas), o None."""
    filtros = guardados()
    if nombre in filtros:
        return filtros[nombre]
    for k, v in filtros.items():
        if k.upper() == str(nombre).strip().upper():
            return v
    return None


# ------------------------------------------------------------ en el dibujo
def candidatos(document, handles=None) -> list:
    """Los objetos que se pueden elegir (de ``handles`` o de todo el espacio
    actual): no los de capas apagadas, inutilizadas o bloqueadas, ni los
    ocultos por AISLAR."""
    if document is None:
        return []
    db = document.doc.entitydb
    if handles:
        ents = [db.get(h) for h in handles]
    else:
        space = document.current_space() if hasattr(document, "current_space") \
            else document.doc.modelspace()
        ents = list(space)
    layers = document.doc.layers
    ocultos = getattr(document, "_isolated_hidden", None) or set()
    out = []
    for e in ents:
        if e is None or not e.is_alive or e.dxf.get("handle") in ocultos:
            continue
        nombre = e.dxf.get("layer", "0")
        capa = layers.get(nombre) if nombre in layers else None
        if capa is not None and (capa.is_off() or capa.is_frozen() or capa.is_locked()):
            continue
        out.append(e)
    return out


def recordar(conds) -> None:
    """El último filtro aplicado queda como «*sin nombre» (como AutoCAD)."""
    try:
        guardar(SIN_NOMBRE, conds)
    except (OSError, FiltroError):
        pass


def ultimo() -> list:
    return guardados().get(SIN_NOMBRE, [])


#: lo que se escribe para filtrar (en la línea de comandos o en «Designar»)
NOMBRES_ORDEN = ("FI", "FILTRO", "FILTER", "'FI", "'FILTRO", "'FILTER", "_FILTER", "'_FILTER")


def pedido(texto: str):
    """«FI» -> ""; «FI nombre» -> "nombre"; otra cosa -> None."""
    t = str(texto).strip()
    partes = t.split(None, 1)
    if not partes or partes[0].upper() not in NOMBRES_ORDEN:
        return None
    return partes[1].strip() if len(partes) > 1 else ""


def _clase_tool():
    from tools.base import Tool

    from . import filtro_ui, seleccion

    class FiltroTool(Tool):
        """FILTRO / FI: la ventana de filtros; después «Designar objetos a
        filtrar» (Enter = todo el dibujo). Con objetos ya seleccionados, se
        filtran ésos. El resultado queda seleccionado para la orden siguiente."""

        def start(self) -> None:
            self.name = "GEOFILTER"
            servicios = self.ctx.services
            self._previos = set(getattr(servicios, "selection", None) or ())
            self._conds = list(ultimo())
            self._fase = ""
            self._ventana()

        def _documento(self):
            return getattr(self.ctx.services, "document", None)

        def _ventana(self) -> None:
            doc = self._documento()
            r = filtro_ui.editar(getattr(self.ctx.services, "window", None), self._conds,
                                 candidatos(doc), doc, con_objeto=True)
            if r is filtro_ui.SIN_QT:
                r = self._sin_ventana()
            if r is None:
                self.ctx.echo("FILTRO: cancelado.")
                self.ctx.finish()
                return
            self._conds = r["conds"]
            if r["accion"] == "objeto":
                self._fase = "objeto"
                self._pedir("Designe el objeto cuyas propiedades van al filtro:")
                return
            self._aplicar_filtro()

        def _sin_ventana(self):
            """Sin interfaz: se elige un filtro guardado por su nombre."""
            nombres = sorted(guardados(), key=lambda n: (n != SIN_NOMBRE, n.upper()))
            if not nombres:
                self.ctx.echo("No hay filtros guardados (se arman en la ventana de FILTRO).")
                return None
            nombre = self.ctx.ask_choice("Filtro guardado:", nombres, nombres[0])
            if nombre is None:
                return None
            return {"accion": "aplicar", "conds": guardados().get(nombre, [])}

        def _pedir(self, texto: str) -> None:
            self._prompt = texto
            servicios = self.ctx.services
            try:
                servicios.selection = set()
            except AttributeError:
                pass
            pedir = getattr(servicios, "request_selection", None)
            if pedir is None:
                self.ctx.finish()
                return
            pedir()

        def selection_prompt(self) -> str:
            return getattr(self, "_prompt", "Designar objetos:")

        def _aplicar_filtro(self) -> None:
            recordar(self._conds)
            if self._previos:
                self._resultado(candidatos(self._documento(), self._previos))
                return
            self._fase = "filtrar"
            self._pedir("Designar objetos a filtrar (W C WP CP F ALL...; "
                        "Enter = todo el dibujo):")

        def on_selection(self, entities: list) -> None:
            if self._fase == "objeto":
                if entities:
                    self._conds = self._conds + de_objeto(entities[0])
                else:
                    self.ctx.echo("No se eligió ningún objeto.")
                self._fase = ""
                self._ventana()
                return
            elegibles = candidatos(self._documento(), {e.dxf.handle for e in entities}) \
                if entities else candidatos(self._documento())
            self._resultado(elegibles)

        def _resultado(self, elegibles) -> None:
            try:
                ok = filtrar(elegibles, self._conds, self._documento())
            except FiltroError as exc:
                self.ctx.echo(f"Filtro no válido: {exc}.")
                self.ctx.finish()
                return
            handles = {e.dxf.handle for e in ok}
            servicios = self.ctx.services
            self.ctx.finish()
            if servicios is not None:
                servicios.selection = handles
                servicios._geocad_previa = set(handles)
                seleccion._cambio(servicios)
            self.ctx.echo(f"{len(handles)} de {len(elegibles)} objeto(s) cumplen el filtro; "
                          "quedan seleccionados para la orden siguiente.")

    return FiltroTool


try:
    FiltroTool = _clase_tool()
except Exception:  # noqa: BLE001 -- sin IngeCAD (QGIS, pruebas sueltas)
    FiltroTool = None
