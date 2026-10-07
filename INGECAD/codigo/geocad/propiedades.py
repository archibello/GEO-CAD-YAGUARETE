# SPDX-License-Identifier: GPL-3.0-or-later
"""Propiedades en masa (módulo «Propiedades», 3.3.0).

La paleta Properties de IngeCAD (Ctrl+1, views/properties_panel.py) es como la
de AutoCAD, pero con varios objetos seleccionados sólo mostraba lo general
(color, capa, tipo y grosor de línea...): lo propio de cada tipo (altura de
texto, radio, escala de bloque...) aparecía sólo con UN objeto. Sus cambios
ya se aplican a todos los objetos del tipo elegido; GeoCAD agrega:

1. Con varios objetos del mismo tipo (o eligiendo el tipo en el desplegable
   de arriba) aparece la sección de ese tipo: lo que se cambia, cambia en
   todos (*varies* donde difieren; se deshace con U / Ctrl+Z).
2. «Totales (GeoCAD)» con varios objetos: cantidad, largo total y área
   total de los cerrados (AutoCAD sólo dice *VARIES*).
3. «Atributos» de los bloques: un renglón por etiqueta; lo que se escribe va
   a ese atributo de todos los bloques elegidos que lo tienen.
4. En los números se puede escribir coma decimal.
5. Operaciones sobre el valor de CADA objeto (3.3.1): h/1.1, h*0.9, h+0,5
   (la variable puede ser h, x o v) o abreviado *0.9, /1.1, +2. Todo el
   cambio se deshace con un solo U.
6. Elegir un color (en la paleta o en la barra de propiedades) quita el
   «color verdadero» RGB del objeto, como en AutoCAD (3.3.2). Antes los
   polígonos que llegan de QGIS con color RGB no cambiaban: IngeCAD cambiaba
   sólo el color ACI y el RGB seguía mandando. Se deshace con U.

Apagado el módulo, la paleta queda como venía. Las cuentas no usan Qt, para
poder probarlas sin la interfaz.
"""
from __future__ import annotations

from . import filtro, modulos

PROGRAMA = "ingecad"
PLUGIN_ID = "geocad"


def activo(window=None) -> bool:
    if not modulos.activo(PROGRAMA, "propiedades"):
        return False
    mgr = getattr(window, "plugins", None)
    if mgr is None:
        return True
    try:
        return bool(mgr.is_active(PLUGIN_ID))
    except Exception:  # noqa: BLE001
        return True


# ---------------------------------------------------------------- cuentas
def totales(entidades) -> dict:
    """{"n", "largo", "n_largo", "area", "n_area"} de los objetos."""
    out = {"n": 0, "largo": 0.0, "n_largo": 0, "area": 0.0, "n_area": 0}
    for e in entidades:
        out["n"] += 1
        t = e.dxftype()
        if t in filtro.LINEALES:
            try:
                v = filtro.largo(e)
            except Exception:  # noqa: BLE001
                v = None
            if v is not None:
                out["largo"] += v
                out["n_largo"] += 1
        try:
            a = filtro.area(e)
        except Exception:  # noqa: BLE001
            a = None
        if a is not None:
            out["area"] += a
            out["n_area"] += 1
    return out


def _atributos(e):
    if e.dxftype() != "INSERT":
        return []
    try:
        return list(e.attribs)
    except Exception:  # noqa: BLE001
        return []


def etiquetas(entidades) -> list:
    """Las etiquetas de atributo de los bloques, en orden de aparición."""
    out = []
    for e in entidades:
        for a in _atributos(e):
            tag = a.dxf.tag
            if tag not in out:
                out.append(tag)
    return out


def valor_atributo(e, tag: str):
    for a in _atributos(e):
        if a.dxf.tag == tag:
            return a.dxf.text
    return None                      # sin ese atributo: *varies* en la paleta


def poner_atributo(entidades, tag: str, valor: str) -> int:
    """Cambia el atributo ``tag`` de todos los bloques que lo tienen."""
    n = 0
    for e in entidades:
        for a in _atributos(e):
            if a.dxf.tag == tag:
                a.dxf.text = str(valor)
                n += 1
    return n


def editar_atributo(panel, tag: str, valor: str) -> None:
    """Cambia el atributo en los bloques activos de la paleta, con deshacer:
    la copia para deshacer lleva también los ATTRIB (son entidades aparte;
    la de IngeCAD sólo copiaba los bloques y el deshacer no los devolvía)."""
    bloques = [e for e in panel._active() if e.dxftype() == "INSERT"]
    historia = getattr(getattr(panel, "window", None), "history", None)
    if historia is None:
        panel._in_place(lambda: poner_atributo(bloques, tag, valor))
        return
    from core import actions
    attribs = [a for e in bloques for a in _atributos(e)]
    actions.apply_in_place(historia, bloques + attribs,
                           lambda: poner_atributo(bloques, tag, valor))
    try:                                   # que se vea ya, como _in_place de IngeCAD
        tools = panel.window.tools
        tools._invalidate_geometry()
        panel.window.viewport.hide_handles([e.dxf.handle for e in bloques])
        tools._pending_render.extend(e for e in bloques if e not in tools._pending_render)
        tools._refresh_overlay()
    except Exception:  # noqa: BLE001
        panel.window.regen_in_memory()


def representante(entidades):
    """El objeto con que se arma la sección del tipo: una polilínea abierta
    si alguna lo es (así «Área» aparece sólo si TODAS están cerradas)."""
    for e in entidades:
        if e.dxftype() == "LWPOLYLINE" and not e.closed:
            return e
    return entidades[0]


def _num(v: float) -> str:
    return f"{v:,.3f}".replace(",", " ").replace(".", ",")


def secciones_extra(panel, entidades, Row) -> list:
    """Lo que GeoCAD agrega a la paleta: [(título, [Row...])]."""
    out = []
    tags = etiquetas(entidades)
    if tags and {e.dxftype() for e in entidades} == {"INSERT"}:
        filas = []
        for tag in tags:
            def poner(v, t=tag):
                editar_atributo(panel, t, v)
            filas.append(Row(tag, "str", lambda e, t=tag: valor_atributo(e, t), poner))
        out.append(("Atributos", filas))
    if len(entidades) > 1:
        t = totales(entidades)
        filas = [Row("Cantidad", "ro", lambda e, v=t["n"]: v)]
        if t["n_largo"]:
            filas.append(Row(f"Largo total ({t['n_largo']})", "ro",
                             lambda e, v=_num(t["largo"]): v))
        if t["n_area"]:
            filas.append(Row(f"Área total ({t['n_area']} cerrados)", "ro",
                             lambda e, v=_num(t["area"]): v))
        out.append(("Totales (GeoCAD)", filas))
    return out


def esquema(panel, entidades, original, pp) -> list:
    """El _schema de la paleta con lo de GeoCAD. ``pp`` es el módulo
    views.properties_panel (Row y _TYPE_ROWS)."""
    secciones = list(original(panel, entidades))
    if not entidades or not activo(getattr(panel, "window", None)):
        return secciones
    tipos = {e.dxftype() for e in entidades}
    if len(tipos) == 1 and len(entidades) > 1:
        constructor = getattr(pp, "_TYPE_ROWS", {}).get(next(iter(tipos)))
        if constructor is not None:
            try:
                secciones.append(constructor(panel, representante(entidades)))
            except Exception:  # noqa: BLE001 -- nunca rompe la paleta
                pass
    try:
        secciones += secciones_extra(panel, entidades, pp.Row)
    except Exception:  # noqa: BLE001
        pass
    return secciones


# ------------------------------------------------------------ envoltorios
def _envolver_schema(original):
    def _schema(self, entities):
        import sys
        pp = sys.modules.get(type(self).__module__)
        return esquema(self, entities, original, pp)

    _schema._puente_original = original
    _schema._puente_fabrica = _envolver_schema
    return _schema


# ------------------------------------------------------- operaciones (3.3.1)
VARIABLES = ("H", "X", "V")


def _texto_numero(texto: str) -> str:
    t = str(texto).strip()
    return t.replace(",", ".")                          # coma decimal


def es_numero(texto: str) -> bool:
    """Un número solo («+2» no: es «sumarle 2»)."""
    t = _texto_numero(texto)
    if t[:1] == "+":
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def expresion(texto: str):
    """La operación escrita lista para evaluar, o None si no es una.
    «*0.9» -> «h*0.9»; «h/1,1» -> «h/1.1»."""
    t = _texto_numero(texto)
    if not t or es_numero(t):
        return None
    if t[0] in "*/+":
        t = "h" + t
    try:
        evaluar(t, 1.0)
    except ValueError:
        return None
    return t


def evaluar(expr: str, valor: float) -> float:
    """El resultado de ``expr`` con h (o x, v) = ``valor``. Sólo números,
    + - * / y paréntesis (nada de Python suelto)."""
    import ast

    try:
        arbol = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError("operación no válida") from exc

    def calc(n):
        if isinstance(n, ast.Expression):
            return calc(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
                and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name) and n.id.upper() in VARIABLES:
            return float(valor)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = calc(n.operand)
            return v if isinstance(n.op, ast.UAdd) else -v
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = calc(n.left), calc(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if b == 0:
                raise ValueError("división por cero")
            return a / b
        raise ValueError("operación no válida")
    return calc(arbol)


def aplicar_expresion(panel, row, expr: str) -> int:
    """Aplica la operación a cada objeto activo con SU valor, en un solo paso
    para deshacer. Usa el mismo «apply» de la fila de IngeCAD, de a un objeto
    por vez. Devuelve cuántos cambió."""
    entidades = list(panel._active())
    nuevos = []
    for e in entidades:
        try:
            v = row.get(e)
            nuevos.append((e, evaluar(expr, float(v))))
        except (TypeError, ValueError):
            continue                                     # sin ese valor: no se toca
    if not nuevos:
        return 0

    def mutar():
        nombres = ("_active", "_set_prop", "_in_place")
        nada = object()
        antes = {n: vars(panel).get(n, nada) for n in nombres}
        try:
            for e, v in nuevos:
                panel._active = lambda e=e: [e]          # la fila de IngeCAD ve un solo objeto
                panel._set_prop = lambda prop, valor, e=e: e.dxf.set(prop, valor)
                panel._in_place = lambda mutate, regen=False: mutate()
                row.apply(v)
        finally:
            for n, previo in antes.items():
                if previo is nada:
                    vars(panel).pop(n, None)
                else:
                    setattr(panel, n, previo)

    historia = getattr(getattr(panel, "window", None), "history", None)
    if historia is not None:
        from core import actions
        attribs = [a for e, _v in nuevos for a in _atributos(e)]
        actions.apply_in_place(historia, [e for e, _v in nuevos] + attribs, mutar)
    else:
        mutar()
    return len(nuevos)


def _envolver_edit_text(original):
    def _edit_text(self, row, editor):
        if getattr(row, "kind", "") == "num" and activo(getattr(self, "window", None)) \
                and not getattr(self, "_loading", False) and row.apply is not None:
            texto = editor.text()
            if es_numero(texto):
                editor.setText(_texto_numero(texto))        # coma decimal
            elif texto.strip():
                expr = expresion(texto)
                linea = getattr(getattr(self, "window", None), "command_line", None)
                if expr is None:
                    if linea is not None:
                        linea.echo(f"«{texto}» no es un número ni una operación "
                                   "(p. ej. h*0.9, h/1.1, *0.9, +2).")
                    return None
                n = aplicar_expresion(self, row, expr)
                if linea is not None:
                    linea.echo(f"{row.label}: {expr} en {n} objeto(s).")
                self._after_edit()
                return None
        return original(self, row, editor)

    _edit_text._puente_original = original
    _edit_text._puente_fabrica = _envolver_edit_text
    return _edit_text


ENVOLTORIOS = {"_schema": _envolver_schema, "_edit_text": _envolver_edit_text}


# ------------------------------------------------- color: quitar el RGB (3.3.2)
def _envolver_color_do(original):
    def do(self, document):
        self._geocad_rgb = []
        if getattr(self, "prop", None) == "color" and activo():
            for e in self.entities:
                try:
                    if e.dxf.hasattr("true_color"):
                        self._geocad_rgb.append((e, e.dxf.true_color))
                        e.dxf.discard("true_color")
                except Exception:  # noqa: BLE001
                    continue
        return original(self, document)

    do._puente_original = original
    do._puente_fabrica = _envolver_color_do
    return do


def _envolver_color_undo(original):
    def undo(self, document):
        resultado = original(self, document)
        for e, rgb in getattr(self, "_geocad_rgb", None) or ():
            try:
                if e.is_alive:
                    e.dxf.true_color = rgb
            except Exception:  # noqa: BLE001
                continue
        return resultado

    undo._puente_original = original
    undo._puente_fabrica = _envolver_color_undo
    return undo


COLOR = {"do": _envolver_color_do, "undo": _envolver_color_undo}


def instalar() -> None:
    """Se llama al cargar el plugin. Sin interfaz (pruebas) no hace nada."""
    from .dibujo import envolver
    try:
        from core.actions import SetPropertyCommand
    except Exception:  # noqa: BLE001
        SetPropertyCommand = None
    if SetPropertyCommand is not None:                # sin Qt: también en las pruebas
        for nombre, fabrica in COLOR.items():
            if getattr(getattr(SetPropertyCommand, nombre, None), "_puente_fabrica", None) \
                    is not fabrica:
                envolver(SetPropertyCommand, nombre, fabrica, reemplazar=True)
    try:
        from views.properties_panel import PropertiesPanel
    except Exception:  # noqa: BLE001
        return
    for nombre, fabrica in ENVOLTORIOS.items():
        if getattr(getattr(PropertiesPanel, nombre, None), "_puente_fabrica", None) is not fabrica:
            envolver(PropertiesPanel, nombre, fabrica, reemplazar=True)


def refrescar(window) -> None:
    """Al prender o apagar el módulo, la paleta se rearma."""
    panel = getattr(window, "_properties_panel", None)
    if panel is not None:
        try:
            panel.refresh()
        except Exception:  # noqa: BLE001
            pass
