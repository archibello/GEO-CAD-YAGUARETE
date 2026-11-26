# SPDX-License-Identifier: GPL-3.0-or-later
"""FILTRO (FI): lo común a IngeCAD y QGIS (3.97.0).

Hasta la 3.96 todo estaba en el filtro.py de IngeCAD (3.2.0). Para llevar
FILTRO a QGIS (Fernando, 26/11/2026) se separó lo que no depende del
programa: las condiciones y sus grupos (Y, O, XO, NO), las comparaciones de
números, textos (con comodines) y colores, el texto de la lista de la
ventana y los filtros guardados. Cada programa tiene su filtro.py con sus
propiedades (qué es un «tipo», una «capa», un «largo» en cada uno) y su
archivo de filtros guardados: IngeCAD ~/.config/geocad/filtros.json y QGIS
~/.config/geocad/filtros_qgis.json (separados, decidido con Fernando).

Python puro (sin Qt).
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass

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
    tipos: tuple = ()       # tipos de objeto a los que se aplica (vacío = todos)


def _P(clave, nombre, clase, *tipos):
    return Prop(clave, nombre, clase, tuple(tipos))


#: los grupos, al final de la lista de propiedades de cada programa
PROP_GRUPOS = (
    _P("**Y(", "** Comenzar Y", "grupo"), _P("**Y)", "** Terminar Y", "grupo"),
    _P("**O(", "** Comenzar O", "grupo"), _P("**O)", "** Terminar O", "grupo"),
    _P("**XO(", "** Comenzar XO", "grupo"), _P("**XO)", "** Terminar XO", "grupo"),
    _P("**NO(", "** Comenzar NO", "grupo"), _P("**NO)", "** Terminar NO", "grupo"),
)


class FiltroError(ValueError):
    pass


# ------------------------------------------------------------ comparaciones
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


SIN_CAMPO = object()


def cumple_valor(prop, cond: dict, actual) -> bool:
    """¿El valor ``actual`` de la propiedad cumple la condición? (no tipos,
    grupos ni campos: ésos los resuelve cada programa)."""
    op = cond.get("op", "=")
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


def cumple_campo(v, cond: dict) -> bool:
    """Un campo de la tabla: número si los dos lo son; si no, texto."""
    if v is None or v is SIN_CAMPO:
        return False
    op = cond.get("op", "=")
    if _num(v) is not None and _num(cond.get("v")) is not None and op != "*":
        return comparar_numero(v, op, cond.get("v"))
    return comparar_texto(v, op if op in ("=", "!=", "*") else "=", cond.get("v"))


# ------------------------------------------------------------------ grupos
def arbol(conds, por_clave):
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
            if por_clave.get(clave) is None:
                raise FiltroError(f"propiedad desconocida: {clave}")
            pila[-1][1].append(c)
    if len(pila) > 1:
        raise FiltroError(f"falta «Terminar {pila[-1][0]}»")
    return pila[0]


def evaluar(obj, nodo, cumple) -> bool:
    """``cumple(obj, condición)`` decide cada condición suelta."""
    if isinstance(nodo, dict):
        return cumple(obj, nodo)
    op, hijos = nodo
    if op == "Y":
        return all(evaluar(obj, h, cumple) for h in hijos)
    if op == "O":
        return any(evaluar(obj, h, cumple) for h in hijos)
    if op == "XO":
        return evaluar(obj, hijos[0], cumple) != evaluar(obj, hijos[1], cumple)
    return not evaluar(obj, hijos[0], cumple)            # NO


# ------------------------------------------------------ texto de la lista
def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def describir(cond: dict, por_clave) -> tuple:
    """(propiedad, operador y valor) como los muestra la lista de la ventana."""
    clave = cond.get("p")
    prop = por_clave.get(clave)
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


# --------------------------------------------------------------- guardados
SIN_NOMBRE = "*sin nombre"


class Guardados:
    """Los filtros con nombre de un programa, en un archivo JSON.
    ``archivo``: función que devuelve la ruta (se lee cada vez: las pruebas
    cambian HOME)."""

    def __init__(self, archivo, por_clave) -> None:
        self.archivo = archivo
        self.por_clave = por_clave

    def todos(self) -> dict:
        """{nombre: [condiciones]} (incluye «*sin nombre», el último usado)."""
        try:
            data = json.loads(self.archivo().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        filtros = data.get("filtros") if isinstance(data, dict) else None
        if not isinstance(filtros, dict):
            return {}
        return {str(k): list(v) for k, v in filtros.items() if isinstance(v, list)}

    def _escribir(self, filtros: dict) -> None:
        ruta = self.archivo()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "filtros": filtros}, ensure_ascii=False,
                                  indent=1), encoding="utf-8")
        tmp.replace(ruta)

    def guardar(self, nombre: str, conds) -> None:
        nombre = str(nombre).strip()
        if not nombre:
            raise FiltroError("falta el nombre")
        arbol(conds, self.por_clave)                # no se guarda un filtro roto
        filtros = self.todos()
        filtros[nombre] = list(conds)
        self._escribir(filtros)

    def borrar(self, nombre: str) -> bool:
        filtros = self.todos()
        if nombre not in filtros:
            return False
        del filtros[nombre]
        self._escribir(filtros)
        return True

    def buscar(self, nombre: str):
        """El filtro guardado con ese nombre (sin distinguir mayúsculas), o None."""
        filtros = self.todos()
        if nombre in filtros:
            return filtros[nombre]
        for k, v in filtros.items():
            if k.upper() == str(nombre).strip().upper():
                return v
        return None

    def recordar(self, conds) -> None:
        """El último filtro aplicado queda como «*sin nombre» (como AutoCAD)."""
        try:
            self.guardar(SIN_NOMBRE, conds)
        except (OSError, FiltroError):
            pass

    def ultimo(self) -> list:
        return self.todos().get(SIN_NOMBRE, [])


#: lo que se escribe para filtrar (en la línea de comandos o en «Designar»)
NOMBRES_ORDEN = ("FI", "FILTRO", "FILTER", "'FI", "'FILTRO", "'FILTER", "_FILTER", "'_FILTER")


def pedido(texto: str):
    """«FI» -> ""; «FI nombre» -> "nombre"; otra cosa -> None."""
    t = str(texto).strip()
    partes = t.split(None, 1)
    if not partes or partes[0].upper() not in NOMBRES_ORDEN:
        return None
    return partes[1].strip() if len(partes) > 1 else ""
