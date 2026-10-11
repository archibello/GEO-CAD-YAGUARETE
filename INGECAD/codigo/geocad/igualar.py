# SPDX-License-Identifier: GPL-3.0-or-later
"""IGUALARPROP (MATCHPROP / MA) estilo AutoCAD (módulo «Igualar propiedades», 3.17.0).

El MATCHPROP de IngeCAD copia bien las propiedades (capa, color, tipo, escala
y grosor de línea, altura, transparencia, estilo de texto y de cota), pero:
  - el objeto de origen no queda marcado: después del primer clic no se sabe
    de cuál se están copiando;
  - los destinos se eligen sólo de a uno, con clic.

Acá, como en AutoCAD:
  - el objeto de origen queda resaltado con SU PROPIO color, más grueso,
    hasta que termina la orden (Enter o Esc). Como se trabaja en AutoCAD
    (3.17.1): 1) clic en el origen y Enter para confirmarlo (antes del Enter
    otro clic lo cambia); 2) los destinos, todas las veces que haga falta;
    3) Enter termina. Con un objeto ya elegido antes, ése es el origen y
    pide directamente los destinos;
  - los destinos se eligen con todas las opciones de «Designar objetos» del
    módulo Selección: clic, ventana con el ratón, W C WP CP F ALL L P R U FI
    (y en español V PV PC B TODO UL E H FILTRO);
  - cada paso de la selección se aplica en el momento: lo elegido se ve ya
    con sus propiedades nuevas (sin el resaltado de selección, que lo
    taparía);
  - R (quitar) y U (deshacer) devuelven a esos objetos las propiedades que
    tenían antes de la orden; A vuelve a agregar.

Cada paso queda en DESHACER (U / Ctrl+Z) por separado. Se apaga con el
módulo «igualar»: IngeCAD queda como venía. Las cuentas no usan Qt.
"""
from __future__ import annotations

from core import modify
from core.i18n import tr
from tools.modify import MatchPropTool

from . import modulos

PROGRAMA = "ingecad"

#: el origen se dibuja con su color y este ancho (px)
ANCHO_ORIGEN = 5
#: más tramos que éstos (un sombreado enorme) y se resaltan sólo los primeros
MAX_TRAMOS = 20000

PEDIDO_ORIGEN = "Origen elegido (resaltado). Enter confirma; clic en otro objeto lo cambia:"
PEDIDO = ("Designar objetos de destino (W C WP CP F ALL L P R U FI, ? ayuda; "
          "Enter termina):")


# ------------------------------------------------------------- el color
def _rgb_aci(aci: int):
    from ezdxf import colors

    return tuple(colors.int2rgb(colors.DXF_DEFAULT_COLORS[aci]))


def color_rgb(entity, document=None):
    """(r, g, b) con que se ve el objeto; None = color 7 (blanco o negro,
    según el fondo) o algo que no se puede saber."""
    from ezdxf import colors

    try:                                   # un MTEXT con color dentro del texto
        efectivo = modify._effective_text_color(entity)
    except Exception:  # noqa: BLE001
        efectivo = None
    if efectivo is not None:
        tipo, valor = efectivo
        if tipo == "rgb":
            return tuple(int(v) for v in valor)
        if tipo == "rgb_raw":
            return tuple(colors.int2rgb(int(valor)))
        aci = int(valor)
    elif entity.dxf.hasattr("true_color"):
        return tuple(colors.int2rgb(int(entity.dxf.true_color)))
    else:
        aci = int(entity.dxf.get("color", 256))
    if aci == 256:                         # PorCapa: el color de la capa
        capa = None
        try:
            capas = document.doc.layers
            nombre = entity.dxf.get("layer", "0")
            capa = capas.get(nombre) if nombre in capas else None
        except Exception:  # noqa: BLE001
            capa = None
        if capa is None:
            return None
        if capa.dxf.hasattr("true_color"):
            return tuple(colors.int2rgb(int(capa.dxf.true_color)))
        aci = abs(int(capa.dxf.get("color", 7)))
    if not 1 <= aci <= 255 or aci == 7:    # PorBloque, 7 y lo raro: blanco/negro
        return None
    return _rgb_aci(aci)


def tramos(index, handle) -> list:
    """Los tramos con que se resalta un objeto: ((x1, y1), (x2, y2))."""
    from .seleccion import _filas

    if index is None or not handle:
        return []
    try:
        filas, _duenos = _filas(index, [handle])
    except Exception:  # noqa: BLE001 -- índice reconstruyéndose: sin resaltado
        return []
    return [((float(a), float(b)), (float(c), float(d)))
            for a, b, c, d in filas[:MAX_TRAMOS]]


# ------------------------------------------------------------- quitar (R / U)
class RestaurarCommand(modify.Command):
    """Devuelve a unos destinos lo que tenían antes de igualarlos (R o U
    dentro de la orden). DESHACER los vuelve a igualar."""

    name = "MATCHPROP"

    def __init__(self, source, targets, antes, antes_xdata) -> None:
        self.source = source
        self.targets = list(targets)
        self.entities = self.targets       # la vista los actualiza al momento
        self.antes = list(antes)
        self.antes_xdata = list(antes_xdata)
        self.needs_regen = False

    def do(self, document) -> None:
        m = modify.MatchPropCommand(self.source, self.targets)
        m._before, m._before_xdata = list(self.antes), list(self.antes_xdata)
        m.undo(document)

    def undo(self, document) -> None:
        modify.MatchPropCommand(self.source, self.targets).do(document)


# ------------------------------------------------------------- la orden
class IgualarTool(MatchPropTool):
    """MATCHPROP: el origen resaltado, los destinos con todas las opciones
    de selección, cada paso aplicado en el momento."""

    entity_picker = True
    #: lo elegido no se resalta: se ve con sus propiedades nuevas
    SIN_RESALTAR_SELECCION = True
    #: el pedido que repite el módulo Selección después de cada opción
    PEDIDO_SELECCION = PEDIDO

    def start(self) -> None:
        self.name = "MATCHPROP"
        self._source = None
        self._confirmado = False           # Enter después de elegir el origen
        self._pintados = {}                # handle -> (objeto, copia antes, xdata antes)
        s = self.ctx.services
        previa = set(getattr(s, "selection", None) or ())
        if s is not None:
            s.selection = set()            # lo preseleccionado no es destino
        if len(previa) == 1:               # un objeto elegido antes: es el origen
            e = self._entidad(next(iter(previa)))
            if e is not None:
                self._source = e
                self._confirmar()
                return
        self.prompt("Select source object:")

    def selection_prompt(self) -> str:
        return PEDIDO

    def _documento(self):
        return getattr(getattr(self.ctx.services, "window", None), "document", None)

    def _entidad(self, handle):
        doc = self._documento()
        if doc is None:
            return None
        e = doc.doc.entitydb.get(handle)
        return e if e is not None and e.is_alive else None

    def _confirmar(self) -> None:
        """Origen confirmado (Enter): ahora los destinos."""
        self._confirmado = True
        self.ctx.echo(tr("Current active settings: Color Layer Ltype "
                         "Ltscale Lineweight Thickness"))
        pedir = getattr(self.ctx.services, "request_selection", None)
        if pedir is not None:
            pedir()
        else:
            self.prompt(PEDIDO)

    def on_point(self, point) -> None:
        if self._confirmado:
            return                         # los destinos van por la selección
        services = self.ctx.services
        entity = services.pick_entity(point) if services else None
        if entity is None:
            self.prompt(PEDIDO_ORIGEN if self._source is not None
                        else "Nothing selected. Select source object:")
            return
        self._source = entity              # otro clic cambia el origen
        self.prompt(PEDIDO_ORIGEN)

    def on_enter(self) -> None:
        """Enter con el origen elegido: lo confirma. Sin origen: termina."""
        if self._source is None or not self._source.is_alive:
            self.ctx.finish()
            return
        if not self._confirmado:
            self._confirmar()

    # -- cada cambio de la selección se aplica en el momento -------------------
    def seleccion_cambiada(self, handles) -> None:
        """El módulo Selección avisa cada vez que cambia lo elegido: se
        igualan los nuevos y se devuelven a como estaban los que salieron."""
        src = self._source
        if src is None or not src.is_alive or not self._confirmado:
            return
        quiero = set(handles) - {src.dxf.handle}
        salen = [h for h in self._pintados if h not in quiero]
        if salen:
            filas = [self._pintados.pop(h) for h in salen]
            filas = [f for f in filas if f[0].is_alive]
            if filas:
                self.ctx.execute(RestaurarCommand(src, [f[0] for f in filas],
                                                  [f[1] for f in filas],
                                                  [f[2] for f in filas]))
                self.ctx.echo(f"{len(filas)} objeto(s) vuelven a como estaban.")
        nuevos = [e for h in sorted(quiero - set(self._pintados))
                  if (e := self._entidad(h)) is not None]
        if nuevos:
            cmd = modify.match_properties(src, nuevos)
            self.ctx.execute(cmd)
            for e, antes, xdata in zip(cmd.targets, cmd._before, cmd._before_xdata):
                self._pintados[e.dxf.handle] = (e, antes, xdata)
            self.ctx.echo(f"{len(nuevos)} objeto(s) igualados, "
                          f"{len(self._pintados)} en total.")

    def on_selection(self, entities: list) -> None:
        """Enter: lo último elegido también se iguala, y termina."""
        self.seleccion_cambiada({e.dxf.handle for e in entities})
        n = len(self._pintados)
        self.ctx.finish()
        self.ctx.echo(f"Igualar propiedades: {n} objeto(s) igualados.")

    # -- resaltado (lo dibuja dibujo.py sobre la vista de IngeCAD) ------------
    def resaltado(self, cursor) -> dict:
        """El origen con su color y más grueso; antes de elegirlo, lo que
        tomaría un clic."""
        s = self.ctx.services
        idx = getattr(s, "index", None)
        src = self._source
        if src is not None:
            if not src.is_alive:
                return {}
            return {"propio": [(color_rgb(src, self._documento()),
                                tramos(idx, src.dxf.handle))]}
        if cursor is None or idx is None:
            return {}
        tol = getattr(s, "_pick_tolerance", None) or 1.0
        try:
            h = idx.pick(tuple(cursor), tol)
        except Exception:  # noqa: BLE001
            return {}
        return {"cursor": tramos(idx, h)} if h else {}


# ------------------------------------------------------------- resaltado de selección
def sin_resaltado(ctrl) -> bool:
    """¿La orden que pide objetos no quiere el resaltado de selección? (lo
    igualado se ve con sus propiedades nuevas). Lo consulta el único
    envoltorio de ``highlight_geometry`` (texto.py): dos envoltorios de la
    misma función se pisarían al reinstalarse."""
    para = getattr(ctrl, "_selecting_for", None)
    return bool(getattr(para, "SIN_RESALTAR_SELECCION", False))


def vacio():
    import numpy as np

    v = np.empty((0, 4))
    return v, v, v


def activo() -> bool:
    return modulos.activo(PROGRAMA, "igualar")
