"""Agarres de IngeCAD con lo mismo que QGIS (módulo «Agarres de vértices», 3.70).

Pedido de Fernando (05/11/2026): dotar a IngeCAD de lo que se agregó a QGIS en la 3.69.
Medido con la ventana real en 0.6.7, 0.6.8.2 y 0.7.0: sus agarres ya responden a las
referencias, ORTO, F3, F8 y Esc, y clics repetidos ya pasan de un objeto tapado a otro: eso
sigue siendo de IngeCAD. Faltaba:
- lo escrito con el agarre tomado (@dx,dy, @d<ángulo, una coordenada, una distancia, END...):
  iba a la línea de comandos, y una «L» abría LINE con el agarre todavía en la mano;
- Mayús + clic marca varios agarres, que se mueven juntos;
- Ctrl + clic en el agarre del medio de una polilínea agrega un vértice (el clic solo sigue
  moviendo el tramo, como en AutoCAD);
- Supr con agarres marcados borra esos vértices (sin marcados, el objeto, como siempre);
- los objetos designados con un agarre en el mismo lugar se mueven juntos;
- Mayús + botón derecho con el agarre tomado abre el menú de referencias (lo soltaba);
- con el agarre tomado se ve la marca de la referencia (enganchaba sin que se viera).

Todo va sobre el arrastre de IngeCAD: los compañeros se suman a la foto de deshacer y siguen
al agarre tomado. Se engancha en la ventana, como el recorte de imágenes, para no pisarse con
los envoltorios de la clase; con el módulo apagado se saca y no queda nada.

IngeCAD 0.8.0 adoptó cuatro de las siete: lo escrito con el agarre (e57c356), la marca de la
referencia (49197aa), los que comparten lugar se estiran juntos (e384637, sus «partners») y
Mayús + botón derecho (ac79782). Desde esa versión GeoCAD se las deja y conserva las suyas:
varios agarres marcados, agregar vértice y Supr con marcados (Fernando, 11/11/2026).
"""
from __future__ import annotations

import math

from . import modulos
from .convivencia import NATIVO_08, ingecad_desde
from .recorte_imagen import _teclas

PROGRAMA = "ingecad"
#: dos agarres a menos que esto están en el mismo lugar
EPS = 1e-6


# ------------------------------------------------------------------ las decisiones
def familia(rol: str):
    """Qué agarres pueden moverse juntos: los de un punto y los del medio de un tramo."""
    if rol in ("vertex", "end"):
        return "punto"
    return "medio" if rol == "mid" else None


def accion_clic(rol: str, marcado: bool, mayus: bool, ctrl: bool) -> str:
    """Qué hace un clic sobre un agarre."""
    tipo = familia(rol)
    if tipo == "punto":
        if mayus:
            return "desmarcar" if marcado else "marcar"
        return "mover_marcados" if marcado else "mover"
    if tipo == "medio":
        if mayus:
            return "nada"
        return "agregar" if ctrl else "mover"
    return "mover"


def coincidentes(grips, principales) -> list:
    """De ``grips`` (x, y, rol, handle, índice), los que comparten lugar y familia con alguno
    de ``principales``, sin contarlos a ellos."""
    propios = {(g[3], g[4]) for g in principales}
    out = []
    for g in grips:
        if (g[3], g[4]) in propios or familia(g[2]) is None:
            continue
        if any(familia(g[2]) == familia(p[2]) and abs(g[0] - p[0]) <= EPS
               and abs(g[1] - p[1]) <= EPS for p in principales):
            out.append(g)
    return out


def tramo_recto(entidad, indice: int) -> bool:
    """¿El agarre del medio ``indice`` es de un tramo recto de esta polilínea?"""
    puntos = entidad.get_points("xyseb")
    tramo = indice - len(puntos)
    return 0 <= tramo < len(puntos) and not puntos[tramo][4]


def agregar_vertice(entidad, indice: int, punto) -> int:
    """El vértice nuevo en el tramo del agarre del medio ``indice``. Devuelve su índice."""
    from core import ocs

    ocs.upright(entidad)          # como apply_grip_edit: lo que se escribe queda en el mundo
    puntos = entidad.get_points("xyseb")
    tramo = indice - len(puntos)
    puntos.insert(tramo + 1, (punto[0], punto[1], puntos[tramo][2], puntos[tramo][3], 0.0))
    entidad.set_points(puntos, format="xyseb")
    return tramo + 1


def se_puede_borrar(entidad, indices) -> bool:
    """¿Sigue siendo una polilínea sin esos vértices?"""
    if entidad.dxftype() != "LWPOLYLINE":
        return False
    return len(entidad) - len(set(indices)) >= (3 if entidad.closed else 2)


def borrar_vertices(entidad, indices) -> None:
    puntos = entidad.get_points("xyseb")
    for i in sorted(set(indices), reverse=True):
        del puntos[i]
    entidad.set_points(puntos, format="xyseb")


# ------------------------------------------------------------------ el estado de la ventana
class _Estado:
    def __init__(self):
        self.marcas = set()         # (x, y, rol, handle, índice) de los marcados
        self.companeros = []        # los que siguen al agarre tomado


def _estado(controlador) -> _Estado:
    estado = controlador.__dict__.get("_geocad_agarres")
    if estado is None:
        estado = controlador._geocad_agarres = _Estado()
    return estado


def _caliente(controlador) -> bool:
    datos = controlador._grip_drag
    return datos is not None and datos[3] is not None     # sin foto: la ventana de una presentación


def _marcas(controlador) -> set:
    """Los marcados que siguen ahí: un deshacer o designar otra cosa los dejan sin efecto."""
    estado = _estado(controlador)
    if estado.marcas:
        estado.marcas &= set(controlador.grip_points())
    return estado.marcas


def _nativo() -> bool:
    """IngeCAD 0.8.0 o más nuevo: lo escrito, la marca, los compañeros del lugar y el menú son suyos."""
    return ingecad_desde(NATIVO_08)


def _socios(controlador) -> set:
    """Los objetos que IngeCAD 0.8.0 ya estira con el agarre tomado."""
    return {h for h, _i, _r in vars(controlador).get("_grip_partners", ())}


def _echo(controlador, texto: str) -> None:
    controlador.window.command_line.echo(texto)


# ------------------------------------------------------------------ tomar, mover, soltar
def _mover_companeros(controlador, x, y) -> None:
    from views import tool_controller

    bx, by = controlador._grip_base
    for cx, cy, rol, handle, indice in _estado(controlador).companeros:
        entidad = controlador.index.entity(handle)
        if entidad is not None:
            tool_controller.apply_grip_edit(entidad, indice, rol, (cx + x - bx, cy + y - by))


def _sumar_a_la_foto(controlador, handles) -> None:
    """Un solo deshacer para todos, y Esc los deja a todos como estaban."""
    handle, indice, rol, foto = controlador._grip_drag
    ids = sorted((set(handles) | _socios(controlador)) - {handle})   # sin perder los de IngeCAD
    entidades = [controlador.index.entity(h) for h in ids]
    foto = type(foto)([controlador.index.entity(handle)] + entidades)
    controlador._grip_drag = (handle, indice, rol, foto)
    controlador.window.viewport.hide_handles(ids)


def _agregar(controlador, grip, todos) -> None:
    gx, gy, _rol, handle, indice = grip
    otros = [g for g in coincidentes(todos, [grip]) if _polilinea_recta(controlador, g)]
    _sumar_a_la_foto(controlador, [g[3] for g in otros])
    nuevo = agregar_vertice(controlador.index.entity(handle), indice, (gx, gy))
    h, _i, _r, foto = controlador._grip_drag
    controlador._grip_drag = (h, nuevo, "vertex", foto)
    _estado(controlador).companeros = [
        (g[0], g[1], "vertex", g[3],
         agregar_vertice(controlador.index.entity(g[3]), g[4], (g[0], g[1]))) for g in otros]


def _polilinea_recta(controlador, grip) -> bool:
    entidad = controlador.index.entity(grip[3])
    return (entidad is not None and entidad.dxftype() == "LWPOLYLINE"
            and tramo_recto(entidad, grip[4]))


def _tomar(controlador, grip) -> None:
    tipo = type(controlador)
    estado = _estado(controlador)
    estado.companeros = []
    if grip is None or controlador.paper_vp is not None:
        tipo.begin_grip_drag(controlador, grip)
        return
    grip = tuple(grip)
    ctrl, mayus, _alt = _teclas()
    todos = list(controlador.grip_points())
    marcas = _marcas(controlador)
    accion = accion_clic(grip[2], grip in marcas, mayus, ctrl)
    if accion in ("marcar", "desmarcar"):
        (marcas.add if accion == "marcar" else marcas.discard)(grip)
        controlador.window.viewport.setFocus()     # Supr va al dibujo, no a la línea de comandos
        return
    if accion == "nada":
        return
    if accion == "agregar" and not _polilinea_recta(controlador, grip):
        _echo(controlador, "GeoCAD Yaguareté: sólo se agrega un vértice en un tramo recto de una polilínea.")
        return
    principales = sorted(marcas, key=lambda g: g != grip) if accion == "mover_marcados" else [grip]
    if accion != "mover_marcados":
        marcas.clear()
    tipo.begin_grip_drag(controlador, grip)
    if not _caliente(controlador):
        return                                     # el agarre era de otro (un lado de una imagen)
    if accion == "agregar":
        if _nativo():
            # IngeCAD estiraría el medio de los otros tramos; acá se les agrega el vértice a ellos
            ajenos = _socios(controlador) - {g[3] for g in coincidentes(todos, [grip])
                                              if _polilinea_recta(controlador, g)}
            controlador._grip_partners = []
            if ajenos and hasattr(controlador.window.viewport, "unhide_handles"):
                controlador.window.viewport.unhide_handles(sorted(ajenos))
        _agregar(controlador, grip, todos)
    else:
        companeros = [g for g in principales if g != grip] + coincidentes(todos, principales)
        if _nativo():                              # los del lugar del agarre ya los lleva IngeCAD
            socios = _socios(controlador)
            companeros = [g for g in companeros if g[3] not in socios]
        if companeros:
            _sumar_a_la_foto(controlador, [g[3] for g in companeros])
            estado.companeros = companeros
    controlador._refresh_overlay()
    if not _nativo():                              # IngeCAD 0.8.0 ya lo pide
        _echo(controlador, "Precise el punto nuevo (clic, @dx,dy, @d<ángulo, una coordenada o una distancia):")


def _seguir(controlador, x, y) -> None:
    if _caliente(controlador) and _estado(controlador).companeros:
        _mover_companeros(controlador, x, y)       # antes: IngeCAD arma el dibujo provisorio
    type(controlador).update_grip_drag(controlador, x, y)


def _soltar(controlador, x, y) -> None:
    estado = _estado(controlador)
    caliente = _caliente(controlador)
    companeros = estado.companeros if caliente else []
    if companeros:
        _mover_companeros(controlador, x, y)
    estado.companeros = []
    type(controlador).finish_grip_drag(controlador, x, y)
    if not caliente:
        return
    estado.marcas.clear()
    controlador.osnap_override = None              # una referencia escrita dura un punto
    if companeros:
        _al_dia(controlador, {g[3] for g in companeros})


def _al_dia(controlador, handles) -> None:
    """Lo que IngeCAD hace al soltar con el objeto del agarre, para los demás."""
    ids = sorted(handles)
    entidades = [e for h in ids if (e := controlador.index.entity(h)) is not None]
    controlador._drop_conflicting_stamps(ids)
    for cache in (controlador.snap_engine, controlador.index):
        if cache is not None:
            cache.remove_handles(ids)
            cache.add_entities(entidades)
    for entidad in entidades:
        if entidad not in controlador._pending_render:
            controlador._pending_render.append(entidad)
    controlador._base_handles.difference_update(ids)
    controlador._refresh_overlay()


def _dibujo_provisorio(controlador) -> list:
    out = list(type(controlador).grip_overlay_entities(controlador))
    if _caliente(controlador):
        for g in _estado(controlador).companeros:
            entidad = controlador.index.entity(g[3])
            if entidad is not None and entidad.is_alive and entidad not in out:
                out.append(entidad)
    return out


# ------------------------------------------------------------------ lo escrito
def _punto_escrito(controlador, texto: str) -> bool:
    """Lo escrito con el agarre tomado: lo mismo que en el punto de un comando."""
    limpio = texto.strip()
    if not limpio:                                 # Intro: como en QGIS, cancela
        controlador.cancel()
        controlador.window.viewport.update()
        return True
    from core import coords, osnap

    try:
        from core.calc import expand_input
        limpio = expand_input(limpio)
    except ImportError:                            # IngeCAD 0.6.8 y anteriores
        pass
    referencia = osnap.override_from_text(limpio)
    if referencia is not None:
        controlador.set_osnap_override(referencia, typed=True)
        return True
    origen = controlador._grip_base
    ucs = controlador.current_ucs() if hasattr(controlador, "current_ucs") else None
    angulo_ucs = ucs.angle if ucs is not None else 0.0
    direccion = angulo_ucs
    if controlador._cursor is not None:
        destino = controlador.resolved_point(*controlador._cursor)
        direccion = math.atan2(destino[1] - origen[1], destino[0] - origen[0])
        if controlador.track_hint is not None and coords.is_direct_distance(limpio):
            (sx, sy), (px, py), _etiqueta = controlador.track_hint
            if math.hypot(px - sx, py - sy) > 1e-12:
                origen, direccion = (sx, sy), math.atan2(py - sy, px - sx)
    try:
        punto = coords.parse_point(limpio, ucs.to_ucs(*origen) if ucs is not None else origen,
                                   direccion - angulo_ucs, relative_default=controlador.dyn_on)
    except coords.CoordinateError as exc:
        _echo(controlador, f"Punto no válido: {exc}")
        return True
    if punto is None:
        _echo(controlador, "GeoCAD Yaguareté: con un agarre tomado se escribe un punto "
                           "(@dx,dy, @d<ángulo, una coordenada o una distancia); Esc lo suelta.")
        return True
    x, y = punto.x, punto.y
    if ucs is not None and not ucs.is_world:
        x, y = ucs.to_world(x, y)
    controlador._note_point((x, y))
    controlador.clear_tracking()
    controlador.finish_grip_drag(x, y)
    controlador.window.viewport.update()
    return True


def _referencia_escrita(controlador, texto: str) -> bool:
    """END, MID, INT... con el agarre tomado: IngeCAD 0.8.0 toma los puntos, pero no esto."""
    from core import osnap

    referencia = osnap.override_from_text(texto.strip())
    if referencia is None:
        return False
    controlador.set_osnap_override(referencia, typed=True)
    return True


def _texto(controlador, texto: str):
    if (controlador.tool is None and _caliente(controlador)
            and getattr(controlador, "_selecting_for", None) is None):
        if _nativo():                              # el punto es de IngeCAD; la referencia, nuestra
            return (_referencia_escrita(controlador, texto)
                    or type(controlador).on_text(controlador, texto))
        return _punto_escrito(controlador, texto)
    return type(controlador).on_text(controlador, texto)


# ------------------------------------------------------------------ Supr
def _suprimir(controlador):
    tipo = type(controlador)
    if controlador._grip_drag is not None:
        return False       # con el agarre en la mano IngeCAD borraría el objeto y seguiría arrastrándolo
    marcas = _marcas(controlador)
    if controlador.tool is not None or not marcas:
        return tipo.delete_selection(controlador)
    grips = list(marcas) + coincidentes(controlador.grip_points(), list(marcas))
    por_objeto = {}
    for g in grips:
        por_objeto.setdefault(g[3], []).append(g[4])
    aptas, rechazados = {}, 0
    for handle, indices in por_objeto.items():
        entidad = controlador.index.entity(handle)
        if se_puede_borrar(entidad, indices):
            aptas[handle] = (entidad, indices)
        else:
            rechazados += 1
    marcas.clear()
    if aptas:
        controlador._execute(_comando_borrar(list(aptas.values())))
        _echo(controlador, f"{len(aptas)} objeto(s) con vértices borrados.")
    if rechazados:
        _echo(controlador, f"{rechazados} objeto(s) sin cambios: sólo se borran vértices de "
                           "polilíneas, y sin dejarlas sin forma.")
    controlador.window.viewport.update()
    return True


def _comando_borrar(partes):
    from core.actions import SnapshotCommand

    class BorrarVertices(SnapshotCommand):
        name = "VERTICE"
        needs_regen = True

        def do(self, document):
            if self._after is not None:
                super().do(document)
                return
            for entidad, indices in partes:
                borrar_vertices(entidad, indices)
            self.commit(document)

    return BorrarVertices([e for e, _i in partes])


# ------------------------------------------------------------------ el menú de referencias
def _menu_referencias(window, posicion) -> None:
    """El menú de Mayús + botón derecho, para el agarre tomado. «Desde» y «Medio entre 2 puntos»
    necesitan un comando en marcha: se ven, apagados."""
    menu = window._osnap_menu = window.osnap_override_menu()
    for accion in menu.actions()[:2]:
        accion.setEnabled(False)
    menu.popup(posicion)


def _filtro_visor(window):
    """IngeCAD suelta el agarre con cualquier botón derecho y abre el menú sólo con un comando
    en marcha (Fernando, 05/11/2026). Sin Qt, nada."""
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
    except ImportError:
        return None

    class Filtro(QObject):
        def eventFilter(self, _objeto, evento):
            if (evento.type() == QEvent.MouseButtonPress and evento.button() == Qt.RightButton
                    and evento.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier)
                    and window.tools.tool is None and _caliente(window.tools)):
                _menu_referencias(window, evento.globalPosition().toPoint())
                return True
            return False

    return Filtro(window.viewport)


def _poner_filtro(window) -> None:
    _sacar_filtro(window)
    if _nativo():
        return                                     # IngeCAD 0.8.0 ya abre el menú (ac79782)
    if hasattr(window.viewport, "installEventFilter"):
        filtro = _filtro_visor(window)
        if filtro is not None:
            window.viewport.installEventFilter(filtro)
            window._geocad_agarres_filtro = filtro


def _sacar_filtro(window) -> None:
    filtro = vars(window).pop("_geocad_agarres_filtro", None)
    if filtro is not None:
        window.viewport.removeEventFilter(filtro)
        filtro.deleteLater()


# ------------------------------------------------------------------ la pantalla
def _pintar(visor, p) -> None:
    type(visor)._draw_grips(visor, p)
    controlador = visor.tool_delegate
    if controlador is None:
        return
    if controlador.tool is None and _caliente(controlador):
        if _nativo():
            return                                 # IngeCAD 0.8.0 ya pinta la marca
        # IngeCAD las pinta sólo con un comando en marcha: enganchaba sin que se viera (Fernando, 05/11/2026)
        visor._draw_tracking(p, controlador)
        marca = controlador.snap_hit
        if marca is not None:
            sx, sy = visor._space_to_screen(marca.x, marca.y)
            visor._draw_snap_marker(p, marca.kind, sx, sy)
        return
    marcas = _marcas(controlador)
    if not marcas:
        return
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QPen

    s = visor.GRIP_SIZE / 2.0
    rojo = QColor(255, 0, 0)
    p.setPen(QPen(rojo, 1))
    p.setBrush(rojo)
    for x, y, _rol, _h, _i in marcas:
        sx, sy = visor._space_to_screen(x, y)
        p.drawRect(QRectF(sx - s, sy - s, 2 * s, 2 * s))
    p.setBrush(Qt.NoBrush)


# ------------------------------------------------------------------ enganchar
def _ganchos(window) -> list:
    c, v = window.tools, window.viewport
    return [(c, "begin_grip_drag", lambda grip: _tomar(c, grip)),
            (c, "update_grip_drag", lambda x, y: _seguir(c, x, y)),
            (c, "finish_grip_drag", lambda x, y: _soltar(c, x, y)),
            (c, "grip_overlay_entities", lambda: _dibujo_provisorio(c)),
            (c, "on_text", lambda texto: _texto(c, texto)),
            (c, "delete_selection", lambda: _suprimir(c)),
            (v, "_draw_grips", lambda p: _pintar(v, p))]


def aplicar(window) -> None:
    """Pone o saca los ganchos según el módulo (al abrir y al cambiar los módulos)."""
    if window is None or not hasattr(window, "tools"):
        return
    if modulos.activo(PROGRAMA, "agarres"):
        quitar(window)                             # lo de otra versión de IngeCAD no queda
        for objeto, nombre, funcion in _ganchos(window):
            funcion._geocad_agarres = True
            setattr(objeto, nombre, funcion)
        _poner_filtro(window)
        return
    quitar(window)


def quitar(window) -> None:
    _sacar_filtro(window)
    for objeto, nombre, _funcion in _ganchos(window):
        if getattr(vars(objeto).get(nombre), "_geocad_agarres", False):
            delattr(objeto, nombre)
    window.tools.__dict__.pop("_geocad_agarres", None)
