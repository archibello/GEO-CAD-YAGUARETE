# SPDX-License-Identifier: GPL-3.0-or-later
"""Selección estilo AutoCAD para IngeCAD (módulo «Selección»).

1. En cualquier «Select objects» (BORRA / E, MOVE, COPY, ROTATE... y SEL) se
   pueden escribir las opciones de AutoCAD, en inglés o en español:

       W  / V       ventana                C  / C      captura
       WP / PV      polígono ventana       CP / PC     polígono captura
       F  / B       borde (fence)          ALL / TODO  todo
       L  / UL      último objeto          P  / P      selección previa
       R  / E       quitar objetos         A  / A      agregar objetos
       U  / H       deshacer el último paso de la selección
       ?            lista de opciones

   IngeCAD ignoraba todo lo que se escribía ahí: sólo aceptaba clic,
   ventana y captura con el ratón.
2. SEL (SELECT; en español SELECCIONA): selecciona con esas opciones y deja los objetos
   seleccionados para la orden siguiente (por ejemplo E).
3. FI / FILTRO (también 'FILTER) dentro de cualquier «Designar objetos»
   (3.2.0): abre la ventana de filtros y suma a la selección los objetos de
   todo el dibujo que lo cumplen (con R, los quita). «FI <nombre>» usa un
   filtro guardado sin abrir la ventana. La orden FILTRO está en filtro.py.
4. La línea de comandos no autocompleta: se ejecuta lo escrito, tal cual
   (el autocompletado se metía en el medio de las órdenes).

Apagado el módulo, IngeCAD queda como venía. La lógica trabaja sobre el
ToolController de IngeCAD (``ctrl``) a través de sus atributos y no usa Qt,
para poder probarla sin la interfaz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import modulos

PROGRAMA = "ingecad"
PLUGIN_ID = "geocad"

#: lo escrito -> la opción (inglés y español; AutoCAD acepta «_» adelante)
OPCIONES = {
    "W": "W", "WINDOW": "W", "V": "W", "VENTANA": "W",
    "C": "C", "CROSSING": "C", "CAPTURA": "C",
    "WP": "WP", "WPOLYGON": "WP", "PV": "WP", "POLIGONOV": "WP", "POLÍGONOV": "WP",
    "CP": "CP", "CPOLYGON": "CP", "PC": "CP", "POLIGONOC": "CP", "POLÍGONOC": "CP",
    "F": "F", "FENCE": "F", "B": "F", "BORDE": "F",
    "ALL": "ALL", "TODO": "ALL", "TO": "ALL",
    "L": "L", "LAST": "L", "UL": "L", "ULTIMO": "L", "ÚLTIMO": "L",
    "P": "P", "PREVIOUS": "P", "PREVIO": "P", "PREVIA": "P",
    "R": "R", "REMOVE": "R", "E": "R", "ELIMINAR": "R", "QUITAR": "R",
    "A": "A", "ADD": "A", "AÑADIR": "A", "AGREGAR": "A",
    "U": "U", "UNDO": "U", "H": "U", "DESHACER": "U",
    "?": "?",
}

AYUDA = ("Opciones: W/V ventana, C captura, WP/PV polígono ventana, CP/PC polígono "
         "captura, F/B borde, ALL/TODO, L/UL último, P previa, R/E quitar, A agregar, "
         "U/H deshacer, FI filtro (FI <nombre>: uno guardado). Enter termina.")

#: cuerdas para convertir un círculo o arco en tramos rectos
CUERDAS = 64


def opcion(texto: str) -> str:
    """La opción que pide lo escrito, o "" si no es una opción."""
    t = str(texto).strip().upper()
    if t.startswith("_"):
        t = t[1:]
    return OPCIONES.get(t, "")


# ------------------------------------------------------------- geometría
def _tramos_de_circulos(circulos) -> list:
    """(cx, cy, r, arco, a0, a1) -> tramos rectos (x1, y1, x2, y2)."""
    out = []
    for cx, cy, r, arco, a0, a1 in circulos:
        if not arco:
            a0, a1 = 0.0, math.tau
        n = max(4, int(math.ceil(CUERDAS * (a1 - a0) / math.tau)))
        pts = [(cx + r * math.cos(a0 + (a1 - a0) * i / n),
                cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
        out += [(*pts[i], *pts[i + 1]) for i in range(n)]
    return out


def _tramos_de_cajas(cajas) -> list:
    out = []
    for x0, y0, x1, y1 in cajas:
        out += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
    return out


def _filas(index, handles):
    """Los tramos de cada objeto: (tramos Mx4, dueño de cada tramo M)."""
    import numpy as np

    if getattr(index, "_dirty", False):
        index._build()
    ids = [index._owner_ids[h] for h in handles if h in index._owner_ids]
    tramos, duenos = [], []
    if not ids:
        return np.empty((0, 4)), np.empty(0, dtype=np.int64)
    ids = np.asarray(ids)
    m = np.isin(index._seg_oidx, ids)
    tramos.append(index._segs[m])
    duenos.append(index._seg_oidx[m])
    m = np.isin(index._circle_oidx, ids)
    for fila, o in zip(index._circles[m], index._circle_oidx[m]):
        t = _tramos_de_circulos([fila])
        tramos.append(np.asarray(t, dtype=float).reshape(-1, 4))
        duenos.append(np.full(len(t), o))
    m = np.isin(index._box_oidx, ids)
    for fila, o in zip(index._boxes[m], index._box_oidx[m]):
        t = _tramos_de_cajas([fila])
        tramos.append(np.asarray(t, dtype=float).reshape(-1, 4))
        duenos.append(np.full(len(t), o))
    return (np.concatenate(tramos).reshape(-1, 4),
            np.concatenate(duenos).astype(np.int64))


def _adentro(puntos, poligono):
    """¿Cada punto (N x 2) está dentro del polígono (K x 2)? Par-impar."""
    import numpy as np

    x, y = puntos[:, 0:1], puntos[:, 1:2]
    xi, yi = poligono[:, 0], poligono[:, 1]
    xj, yj = np.roll(xi, -1), np.roll(yi, -1)
    cruza = (yi > y) != (yj > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = (xj - xi) * (y - yi) / (yj - yi) + xi
    return ((cruza & (x < xc)).sum(axis=1) % 2) == 1


def _se_cortan(tramos, bordes):
    """¿Cada tramo (M x 4) toca alguno de los bordes (K x 4)?"""
    import numpy as np

    if not len(tramos) or not len(bordes):
        return np.zeros(len(tramos), dtype=bool)
    p = tramos[:, None, 0:2]
    r = tramos[:, None, 2:4] - p
    q = bordes[None, :, 0:2]
    s = bordes[None, :, 2:4] - q
    rxs = r[..., 0] * s[..., 1] - r[..., 1] * s[..., 0]
    qp = q - p
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qp[..., 0] * s[..., 1] - qp[..., 1] * s[..., 0]) / rxs
        u = (qp[..., 0] * r[..., 1] - qp[..., 1] * r[..., 0]) / rxs
        hit = (np.abs(rxs) > 1e-12) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
    return hit.any(axis=1)


def _caja(puntos):
    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    return (min(xs), min(ys), max(xs), max(ys))


def seleccionar(index, modo: str, puntos) -> list:
    """Los objetos que toma WP, CP o F con esos puntos (handles, ordenados).

    WP  todo el objeto dentro del polígono (y sin cruzar su borde)
    CP  el objeto toca el polígono o está dentro
    F   el objeto toca el borde (la línea abierta de los puntos)
    """
    import numpy as np

    puntos = [(float(x), float(y)) for x, y in puntos]
    if modo == "F":
        if len(puntos) < 2:
            return []
        candidatos = index.crossing(_caja(puntos))
    else:
        if len(puntos) < 3:
            return []
        caja = _caja(puntos)
        candidatos = index.window(caja) if modo == "WP" else index.crossing(caja)
    if not candidatos:
        return []
    tramos, duenos = _filas(index, candidatos)
    if not len(tramos):
        return []
    pol = np.asarray(puntos, dtype=float)
    siguientes = pol[1:] if modo == "F" else np.roll(pol, -1, axis=0)
    bordes = np.column_stack((pol[:len(siguientes)], siguientes))
    cortan = _se_cortan(tramos, bordes)
    n = len(index._owners)
    if modo == "F":
        tocados = np.zeros(n, dtype=bool)
        tocados[duenos[cortan]] = True
        elegidos = tocados
    else:
        a = _adentro(tramos[:, 0:2], pol)
        b = _adentro(tramos[:, 2:4], pol)
        if modo == "WP":
            presentes = np.zeros(n, dtype=bool)
            malos = np.zeros(n, dtype=bool)
            presentes[duenos] = True
            malos[duenos[~(a & b & ~cortan)]] = True
            elegidos = presentes & ~malos
        else:
            tocados = np.zeros(n, dtype=bool)
            tocados[duenos[a | b | cortan]] = True
            elegidos = tocados
    return sorted(index._owners[i] for i in np.nonzero(elegidos)[0])


# ------------------------------------------------------- estado por orden
@dataclass
class Estado:
    para: object = None                         # la orden que pide la selección
    modo: str = ""                              # "", W, C, WP, CP, F
    puntos: list = field(default_factory=list)
    quitar: bool = False                        # R: los próximos objetos se quitan
    pasos: list = field(default_factory=list)   # selecciones anteriores (para U)


def activo(window=None) -> bool:
    """¿Está prendido el módulo (y el plugin GeoCAD)?"""
    if not modulos.activo(PROGRAMA, "seleccion"):
        return False
    mgr = getattr(window, "plugins", None)
    if mgr is None:
        return True
    try:
        return bool(mgr.is_active(PLUGIN_ID))
    except Exception:  # noqa: BLE001
        return True


def estado(ctrl):
    """El estado de la selección en curso, o None si no se está eligiendo."""
    para = getattr(ctrl, "_selecting_for", None)
    if para is None:
        return None
    st = getattr(ctrl, "_geocad_sel", None)
    if st is None or st.para is not para:
        st = Estado(para=para)
        ctrl._geocad_sel = st
    return st


def _echo(ctrl, texto: str) -> None:
    try:
        ctrl.window.command_line.echo(texto)
    except Exception:  # noqa: BLE001
        pass


def _pedir(ctrl, st) -> None:
    """El prompt que corresponde a lo que se está haciendo."""
    if st.modo in ("W", "C"):
        texto = "Primera esquina:" if not st.puntos else "Esquina opuesta:"
    elif st.modo in ("WP", "CP"):
        texto = ("Primer punto del polígono:" if not st.puntos
                 else "Siguiente punto del polígono (U deshace, Enter termina):")
    elif st.modo == "F":
        texto = ("Primer punto del borde:" if not st.puntos
                 else "Siguiente punto del borde (U deshace, Enter termina):")
    else:
        texto = ("Quitar objetos (A agrega, Enter termina):" if st.quitar
                 else "Designar objetos (W C WP CP F ALL L P R U FI, ? ayuda; Enter termina):")
    try:
        ctrl.current_prompt = texto
    except Exception:  # noqa: BLE001
        pass
    _echo(ctrl, texto)


def _cambio(ctrl) -> None:
    for nombre in ("_highlight_cache", "_grips_cache", "_sel_entities_cache"):
        if hasattr(ctrl, nombre):
            setattr(ctrl, nombre, None)
    señal = getattr(ctrl, "changed", None)
    if señal is not None:
        try:
            señal.emit()
        except Exception:  # noqa: BLE001
            pass


def _indice(ctrl):
    if getattr(ctrl, "index", None) is None:
        from core.select import GeometryIndex
        ctrl.index = GeometryIndex(ctrl.window.document)
    return ctrl.index


def aplicar(ctrl, st, handles) -> int:
    """Suma (o quita, con R) esos objetos a la selección. Devuelve cuántos."""
    handles = set(handles)
    grupos = getattr(ctrl, "_with_groups", None)
    if callable(grupos) and handles:
        handles = set(grupos(handles))
    st.pasos.append(set(ctrl.selection))
    if st.quitar:
        ctrl.selection = set(ctrl.selection) - handles
        _echo(ctrl, f"{len(handles)} encontrados, {len(st.pasos[-1] & handles)} quitados, "
                    f"{len(ctrl.selection)} en total.")
    else:
        ctrl.selection = set(ctrl.selection) | handles
        _echo(ctrl, f"{len(handles)} encontrados, {len(ctrl.selection)} en total.")
    _cambio(ctrl)
    return len(handles)


def _visibles(ctrl, handles) -> list:
    """Sólo los objetos que siguen existiendo y se pueden elegir."""
    doc = getattr(getattr(ctrl, "window", None), "document", None)
    if doc is None:
        return []
    layers = doc.doc.layers
    ocultos = getattr(doc, "_isolated_hidden", None) or set()
    out = []
    for h in handles:
        e = doc.doc.entitydb.get(h)
        if e is None or not e.is_alive or h in ocultos:
            continue
        capa = layers.get(e.dxf.get("layer", "0")) if e.dxf.get("layer", "0") in layers else None
        if capa is not None and (capa.is_off() or capa.is_frozen() or capa.is_locked()):
            continue
        out.append(h)
    return out


def todos(ctrl) -> list:
    """ALL: lo que se puede elegir en el espacio actual."""
    doc = getattr(getattr(ctrl, "window", None), "document", None)
    if doc is None:
        return []
    return _visibles(ctrl, [e.dxf.get("handle") for e in doc.current_space()
                            if e.dxf.get("handle")])


def ultimo(ctrl) -> list:
    """L: el último objeto dibujado que se ve (como AutoCAD)."""
    doc = getattr(getattr(ctrl, "window", None), "document", None)
    if doc is None:
        return []
    for e in reversed(list(doc.current_space())):
        h = e.dxf.get("handle")
        if h and _visibles(ctrl, [h]):
            return [h]
    return []


def _punto_escrito(ctrl, texto: str):
    try:
        from core.coords import parse_point
        p = parse_point(texto, getattr(ctrl, "lastpoint", (0.0, 0.0)), 0.0)
    except Exception:  # noqa: BLE001
        return None
    return None if p is None else (p.x, p.y)


def agregar_punto(ctrl, st, punto) -> None:
    """Un punto (clic o escrito) para la ventana, el polígono o el borde."""
    st.puntos.append((float(punto[0]), float(punto[1])))
    if st.modo in ("W", "C") and len(st.puntos) == 2:
        (ax, ay), (bx, by) = st.puntos
        rect = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
        indice = _indice(ctrl)
        hits = indice.window(rect) if st.modo == "W" else indice.crossing(rect)
        st.modo, st.puntos = "", []
        aplicar(ctrl, st, hits)
    _pedir(ctrl, st)
    _cambio(ctrl)


def cerrar(ctrl, st) -> None:
    """Enter con el polígono o el borde: se eligen los objetos."""
    modo, puntos = st.modo, list(st.puntos)
    st.modo, st.puntos = "", []
    minimo = 2 if modo == "F" else 3
    if len(puntos) < minimo:
        _echo(ctrl, f"Hacen falta al menos {minimo} puntos.")
    else:
        aplicar(ctrl, st, seleccionar(_indice(ctrl), modo, puntos))
    _pedir(ctrl, st)


def on_text(ctrl, texto: str) -> bool:
    """Lo escrito en un «Select objects». True si lo usó GeoCAD; False deja
    seguir a IngeCAD (Enter vacío = terminar la selección)."""
    st = estado(ctrl)
    if st is None or not activo(getattr(ctrl, "window", None)):
        return False
    t = str(texto).strip()
    op = opcion(t)
    if st.modo:
        if not t:
            if st.modo in ("WP", "CP", "F"):
                cerrar(ctrl, st)
            else:
                st.modo, st.puntos = "", []
                _pedir(ctrl, st)
            _cambio(ctrl)
            return True
        if op == "U":
            if st.puntos:
                st.puntos.pop()
            _pedir(ctrl, st)
            _cambio(ctrl)
            return True
        p = _punto_escrito(ctrl, t)
        if p is None:
            _echo(ctrl, "Punto no válido.")
            _pedir(ctrl, st)
            return True
        agregar_punto(ctrl, st, p)
        return True
    if not t:
        return False                      # IngeCAD termina la selección
    from . import filtro
    nombre = filtro.pedido(t)
    if nombre is not None:
        filtro_en_seleccion(ctrl, st, nombre)
        _pedir(ctrl, st)
        _cambio(ctrl)
        return True
    if not op:
        _echo(ctrl, f"«{t}» no es una opción. {AYUDA}")
        _pedir(ctrl, st)
        return True
    if op in ("W", "C", "WP", "CP", "F"):
        st.modo, st.puntos = op, []
        try:
            ctrl._window_anchor = None
        except Exception:  # noqa: BLE001
            pass
    elif op == "ALL":
        aplicar(ctrl, st, todos(ctrl))
    elif op == "L":
        aplicar(ctrl, st, ultimo(ctrl))
    elif op == "P":
        previa = _visibles(ctrl, getattr(ctrl, "_geocad_previa", None) or ())
        if not previa:
            _echo(ctrl, "No hay selección previa.")
        else:
            aplicar(ctrl, st, previa)
    elif op == "R":
        st.quitar = True
    elif op == "A":
        st.quitar = False
    elif op == "U":
        if st.pasos:
            ctrl.selection = st.pasos.pop()
            _echo(ctrl, f"Deshecho. {len(ctrl.selection)} en total.")
            _cambio(ctrl)
        else:
            _echo(ctrl, "No hay nada que deshacer.")
    elif op == "?":
        _echo(ctrl, AYUDA)
    _pedir(ctrl, st)
    _cambio(ctrl)
    return True


def filtro_en_seleccion(ctrl, st, nombre: str = "") -> int:
    """FI dentro de un «Designar objetos»: los objetos de todo el dibujo que
    cumplen el filtro se suman (o se quitan, con R). Devuelve cuántos."""
    from . import filtro, filtro_ui
    doc = getattr(getattr(ctrl, "window", None), "document", None)
    if nombre:
        conds = filtro.buscar(nombre)
        if conds is None:
            nombres = ", ".join(n for n in filtro.guardados() if n != filtro.SIN_NOMBRE)
            _echo(ctrl, f"No hay un filtro guardado «{nombre}». "
                        + (f"Guardados: {nombres}." if nombres else "No hay filtros guardados."))
            return 0
    else:
        r = filtro_ui.editar(getattr(ctrl, "window", None), filtro.ultimo(),
                             filtro.candidatos(doc), doc, con_objeto=False)
        if r is filtro_ui.SIN_QT:
            _echo(ctrl, "Escriba FI <nombre> para usar un filtro guardado.")
            return 0
        if r is None:
            _echo(ctrl, "Filtro cancelado.")
            return 0
        conds = r["conds"]
    try:
        ents = filtro.candidatos(doc)
        ok = filtro.filtrar(ents, conds, doc)
    except filtro.FiltroError as exc:
        _echo(ctrl, f"Filtro no válido: {exc}.")
        return 0
    filtro.recordar(conds)
    _echo(ctrl, f"Filtro: {len(ok)} de {len(ents)} objeto(s) lo cumplen.")
    return aplicar(ctrl, st, [e.dxf.handle for e in ok])


def en_modo(ctrl) -> bool:
    st = getattr(ctrl, "_geocad_sel", None)
    return (st is not None and bool(st.modo)
            and getattr(ctrl, "_selecting_for", None) is st.para)


def resaltado(ctrl, cursor) -> dict:
    """La ventana, el polígono o el borde que se está marcando, hasta el cursor."""
    if not en_modo(ctrl) or not ctrl._geocad_sel.puntos:
        return {}
    st = ctrl._geocad_sel
    pts = list(st.puntos) + ([tuple(cursor)] if cursor is not None else [])
    if st.modo in ("W", "C"):
        if len(pts) < 2:
            return {}
        (ax, ay), (bx, by) = pts[0], pts[-1]
        pts = [(ax, ay), (bx, ay), (bx, by), (ax, by)]
    cerrado = st.modo != "F" and len(pts) > 2
    tramos = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if cerrado else [])
    capa = {"W": "sel_ventana", "WP": "sel_ventana", "C": "sel_captura",
            "CP": "sel_captura", "F": "sel_borde"}[st.modo]
    return {capa: tramos}


# ------------------------------------------------------------- SEL
def _clase_sel():
    from tools.base import Tool

    class SelTool(Tool):
        """SEL: designar objetos (con todas las opciones) y dejarlos
        seleccionados para la orden siguiente."""

        def start(self) -> None:
            self.name = "SELECT"
            servicios = self.ctx.services
            pedir = getattr(servicios, "request_selection", None)
            if pedir is None:
                self.ctx.finish()
                return
            pedir()

        def selection_prompt(self) -> str:
            return "Designar objetos (W C WP CP F ALL L P R U FI, ? ayuda; Enter termina):"

        def on_selection(self, entities: list) -> None:
            handles = {e.dxf.handle for e in entities}
            servicios = self.ctx.services
            self.ctx.finish()
            if servicios is not None:
                servicios.selection = handles
                servicios._geocad_previa = set(handles)
                _cambio(servicios)
            self.ctx.echo(f"{len(handles)} seleccionados. La orden siguiente los usa.")

    return SelTool


try:
    SelTool = _clase_sel()
except Exception:  # noqa: BLE001 -- sin IngeCAD (QGIS, pruebas sueltas)
    SelTool = None


# ------------------------------------------------------- autocompletado
def aplicar_autocompletar(window) -> None:
    """Sin autocompletar mientras el módulo esté prendido; apagado, vuelve
    el de IngeCAD."""
    linea = getattr(window, "command_line", None)
    if linea is None:
        return
    try:
        if activo(window):
            linea.input.setCompleter(None)
        else:
            original = getattr(type(linea).set_completions, "_puente_original", None)
            if original is not None:
                original(linea, window.dispatcher.known_names())
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------- envoltorios
def _envolver_set_completions(original):
    def set_completions(self, names, *args, **kwargs):
        try:
            ventana = self.window()
        except Exception:  # noqa: BLE001
            ventana = None
        if activo(ventana):
            self.input.setCompleter(None)
            return None
        return original(self, names, *args, **kwargs)

    set_completions._puente_original = original
    set_completions._puente_fabrica = _envolver_set_completions
    return set_completions


def _envolver_on_click(original):
    def on_click(self, wx, wy, shift=False, *args, **kwargs):
        if (en_modo(self) and getattr(self, "space_vp", None) is None
                and activo(getattr(self, "window", None))):
            self._window_anchor = None
            agregar_punto(self, self._geocad_sel, self.to_space(wx, wy))
            return None
        return original(self, wx, wy, shift, *args, **kwargs)

    on_click._puente_original = original
    on_click._puente_fabrica = _envolver_on_click
    return on_click


def _envolver_start_window(original):
    def start_window(self, wx, wy, *args, **kwargs):
        if en_modo(self):
            return None                  # en un polígono, arrastrar no abre ventana
        return original(self, wx, wy, *args, **kwargs)

    start_window._puente_original = original
    start_window._puente_fabrica = _envolver_start_window
    return start_window


def _envolver_selection_click(original):
    def _selection_click(self, wx, wy, shift, *args, **kwargs):
        st = estado(self) if activo(getattr(self, "window", None)) else None
        if st is None:
            return original(self, wx, wy, shift, *args, **kwargs)
        antes = set(self.selection)
        resultado = original(self, wx, wy, shift or st.quitar, *args, **kwargs)
        if set(self.selection) != antes:
            st.pasos.append(antes)       # para U
        return resultado

    _selection_click._puente_original = original
    _selection_click._puente_fabrica = _envolver_selection_click
    return _selection_click


def _envolver_finish(original):
    def _finish(self, *args, **kwargs):
        if getattr(self, "selection", None):
            self._geocad_previa = set(self.selection)    # para P
        self._geocad_sel = None
        return original(self, *args, **kwargs)

    _finish._puente_original = original
    _finish._puente_fabrica = _envolver_finish
    return _finish


def _envolver_cancel(original):
    def cancel(self, *args, **kwargs):
        self._geocad_sel = None
        return original(self, *args, **kwargs)

    cancel._puente_original = original
    cancel._puente_fabrica = _envolver_cancel
    return cancel


ENVOLTORIOS = {
    "on_click": _envolver_on_click,
    "start_window": _envolver_start_window,
    "_selection_click": _envolver_selection_click,
    "_finish": _envolver_finish,
    "cancel": _envolver_cancel,
}


def instalar() -> None:
    """Se llama al cargar el plugin. Sin interfaz (pruebas) no hace nada."""
    from .dibujo import envolver
    try:
        from views.tool_controller import ToolController
        from views.command_line import CommandLine
    except Exception:  # noqa: BLE001
        return
    for nombre, fabrica in ENVOLTORIOS.items():
        if getattr(getattr(ToolController, nombre, None), "_puente_fabrica", None) is not fabrica:
            envolver(ToolController, nombre, fabrica, reemplazar=True)
    if getattr(CommandLine.set_completions, "_puente_fabrica", None) is not _envolver_set_completions:
        envolver(CommandLine, "set_completions", _envolver_set_completions, reemplazar=True)
