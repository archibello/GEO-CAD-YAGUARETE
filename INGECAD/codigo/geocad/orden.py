# SPDX-License-Identifier: GPL-3.0-or-later
"""Orden de dibujo en la barra GeoCAD (3.16.0): Traer al frente y Enviar al
fondo, el DRAWORDER de AutoCAD a un clic (pedido de Fernando, 10/10/2026).

Los dos botones llaman a la orden de IngeCAD (0.6.5 en adelante), que
escribe la tabla de orden como AutoCAD (al abrir el DXF se respeta) y se
deshace exacta. Con objetos ya elegidos actúa al momento; si no, pide
elegirlos, y al terminar la pantalla se regenera (3.16.1).

Pantalla (3.16.2). IngeCAD pinta en tandas fijas: todos los rellenos
(sombreados y textos), después todas las líneas, los puntos y las líneas
con grosor. El orden de dibujo sólo valía dentro de cada tanda: una línea
enviada al fondo seguía encima del sombreado. Con el módulo activo se pinta
por grupos: todo lo enviado al fondo (rellenos, líneas, grosores), después
lo normal y al final lo traído al frente. Dentro de cada grupo queda la
regla de IngeCAD (rellenos abajo, líneas arriba). Para eso, al armar la
escena se anota dónde empieza y termina cada grupo en cada tanda (IngeCAD
ya los guarda en ese orden) y el pintado de la escena se hace grupo por
grupo con los mismos datos. Apagado el módulo, IngeCAD pinta como venía.

Hojas e impresión (3.102.1, Fernando: «en el espacio papel, las líneas del
Hatch permanecen sobre las polilíneas del contorno, por más que el orden es que
estén por detrás»; «en la vista previa es mucho más notorio»). Dos causas:
  - al armar una hoja, IngeCAD toma la tabla de orden de la HOJA; lo del modelo
    que muestran sus ventanas quedaba todo en el grupo «normal» (sin fondo ni
    frente): ahora la hoja suma el orden del modelo;
  - dentro de una ventana, ezdxf (vista previa, PDF, imprimir) recorre el modelo
    en el orden en que se crearon los objetos, sin mirar la tabla: un sombreado
    hecho después de su borde se pintaba encima. Ahora va en el orden de dibujo.

Encima de / Debajo de un objeto no se ofrece: IngeCAD sólo sabe «debajo de
todo», «normal» y «encima de todo».
"""
from __future__ import annotations

from types import SimpleNamespace

from . import modulos

PROGRAMA = "ingecad"
FRENTE, FONDO = "front", "back"
#: las tandas de la escena, en el orden en que IngeCAD las pinta
TANDAS = ("triangles", "lines", "points")
MODOS = {"triangles": 4, "lines": 1, "points": 0}   # GL_TRIANGLES, GL_LINES, GL_POINTS


def activo() -> bool:
    return modulos.activo(PROGRAMA, "orden")


def regenerar(host) -> None:
    """La pantalla al día con el orden nuevo (3.16.1). La orden de IngeCAD
    sólo refresca lo tocado, y el orden no cambia la forma de nada: sin
    esto, lo enviado al fondo seguía viéndose encima hasta un REGEN."""
    regen = getattr(host, "regen_in_memory", None)
    if callable(regen):
        regen()


def _regenerar_al_terminar(host) -> None:
    """Si la orden quedó pidiendo objetos, regenera cuando los ordene.
    Sólo esta vez (la herramienta es nueva en cada orden): el Draw Order
    propio de IngeCAD queda como venía."""
    tool = getattr(getattr(host, "tools", None), "tool", None)
    original = getattr(tool, "_apply", None)
    if getattr(tool, "name", None) != "DRAWORDER" or not callable(original):
        return

    def _apply(modo):
        original(modo)
        regenerar(host)
    tool._apply = _apply


def aplicar(ctx, modo: str) -> None:
    """Frente o fondo con la orden de IngeCAD, sobre lo elegido o pidiéndolo,
    y al terminar la pantalla regenerada."""
    host = getattr(ctx, "host", None)
    draworder = getattr(host, "_draworder", None)
    if callable(draworder):
        draworder(modo)       # con objetos elegidos ya ordenó y regeneró
        _regenerar_al_terminar(host)
        return
    invocar = getattr(host, "_invoke_command", None)
    if callable(invocar):                 # un IngeCAD sin el atajo: la orden
        invocar("DRAWORDER")
        _regenerar_al_terminar(host)
        return
    ctx.echo("El orden de dibujo necesita IngeCAD 0.6.5 o más nuevo.")


def cmd_frente(ctx, *args) -> None:
    """TRAER AL FRENTE (GEODRAWFRONT): lo elegido se dibuja encima de todo."""
    aplicar(ctx, FRENTE)


def cmd_fondo(ctx, *args) -> None:
    """ENVIAR AL FONDO (GEODRAWBACK): lo elegido se dibuja debajo de todo."""
    aplicar(ctx, FONDO)


COMMANDS = {"GEODRAWFRONT": cmd_frente, "GEODRAWBACK": cmd_fondo}


# ---------------------------------------------------------------- pantalla
def cortes(buckets, scene):
    """{tanda: (fin del fondo, comienzo del frente)} en vértices, o None si
    nada está enviado al fondo ni traído al frente. IngeCAD guarda cada tanda
    con los grupos en orden (fondo, normal, frente): basta ubicar dónde
    terminan los objetos del fondo y dónde empiezan los del frente."""
    grupo = {}
    for b in buckets.values():
        if b.group:
            for dueño in b.lines_owner + b.triangles_owner + b.points_owner:
                if dueño is not None:
                    grupo[dueño] = b.group
    if not grupo:
        return None
    fin, ini = {}, {}
    for handle, rangos in scene.handle_ranges.items():
        g = grupo.get(handle)
        if not g:
            continue
        for tanda, first, count in rangos:
            if g < 0:
                fin[tanda] = max(fin.get(tanda, 0), first + count)
            else:
                ini[tanda] = min(ini.get(tanda, first), first)
    resultado = {}
    for tanda in TANDAS + ("thick",):
        n = getattr(scene, tanda).vertex_count
        resultado[tanda] = (fin.get(tanda, 0), ini.get(tanda, n))
    return resultado


def ventana(c, tanda: str, g: int, n: int) -> tuple[int, int]:
    """Los vértices [desde, hasta) del grupo ``g`` en una tanda de ``n``."""
    fin, ini = c.get(tanda, (0, n))
    return {-1: (0, fin), 0: (fin, ini), 1: (ini, n)}[g]


def pintar(vp, gl, mvp, c, runs, thick) -> None:
    """La escena de ``vp`` grupo por grupo (fondo, normal, frente), cada
    grupo con las tandas de IngeCAD. ``runs`` y ``thick`` son los de IngeCAD
    (Batch.visible_runs y Viewport._draw_thick sin envolver)."""
    import sys

    # el mismo tamaño mínimo de texto que usa IngeCAD al pintar
    min_texto = getattr(sys.modules.get(type(vp).__module__), "MIN_TEXT_PX", 2.0)
    scene = vp._scene
    rect = vp._view_world_rect()
    for g in (-1, 0, 1):
        vp._program.bind()
        vp._program.setUniformValue(vp._loc_mvp, mvp)
        for tanda in TANDAS:
            buf = vp._scene_bufs.get(tanda)
            if buf is None:
                continue
            batch = getattr(scene, tanda)
            desde, hasta = ventana(c, tanda, g, batch.vertex_count)
            if desde >= hasta:
                continue
            vao = buf[0]
            vao.bind()
            for first, count in runs(batch, rect, vp.view.scale, min_texto):
                a, b = max(first, desde), min(first + count, hasta)
                if b > a:
                    gl.glDrawArrays(MODOS[tanda], a, b - a)
            vao.release()
        vp._program.release()
        batch = scene.thick
        desde, hasta = ventana(c, "thick", g, batch.vertex_count)
        idx = [i for i, r in enumerate(batch.ranges) if desde <= r.first < hasta]
        if idx:
            parte = SimpleNamespace(
                ranges=[batch.ranges[i] for i in idx],
                bounds=None if batch.bounds is None else batch.bounds[idx])
            thick(vp, gl, mvp, rect, vp._scene_bufs.get("thick"), parte)


#: las tandas de la escena ya pintadas por grupos en este cuadro: IngeCAD
#: no las vuelve a pintar
_pintadas: set = set()


def _envolver_pack(original):
    def pack(buckets, *args, **kwargs):
        scene = original(buckets, *args, **kwargs)
        try:
            # el módulo se mira al armar la escena, no en cada cuadro (leer
            # la configuración al hacer zoom sería caro): prenderlo o apagarlo
            # se ve en la regeneración siguiente
            scene._geocad_cortes = cortes(buckets, scene) if activo() else None
        except Exception:  # noqa: BLE001  (sin cortes, IngeCAD pinta como siempre)
            scene._geocad_cortes = None
        return scene
    pack._puente_original = original
    pack._puente_fabrica = _envolver_pack
    return pack


def _envolver_imagenes(original):
    def _draw_images(self, gl, mvp, front):
        original(self, gl, mvp, front)
        scene = getattr(self, "_scene", None)
        c = getattr(scene, "_geocad_cortes", None)
        if front or not c or not getattr(self, "_scene_bufs", None):
            return
        # IngeCAD pinta las imágenes del fondo justo antes de la escena:
        # acá va la escena entera, por grupos, y las tandas quedan pintadas
        from render.batches import Batch
        from views.viewport import Viewport

        runs = getattr(Batch.visible_runs, "_puente_original", Batch.visible_runs)
        thick = getattr(Viewport._draw_thick, "_puente_original", Viewport._draw_thick)
        try:
            pintar(self, gl, mvp, c, runs, thick)
        except Exception:  # noqa: BLE001  (que IngeCAD pinte como siempre)
            return
        _pintadas.update(id(getattr(scene, t)) for t in TANDAS + ("thick",))
    _draw_images._puente_original = original
    _draw_images._puente_fabrica = _envolver_imagenes
    return _draw_images


def _envolver_runs(original):
    def visible_runs(self, *args, **kwargs):
        if id(self) in _pintadas:
            return []
        return original(self, *args, **kwargs)
    visible_runs._puente_original = original
    visible_runs._puente_fabrica = _envolver_runs
    return visible_runs


def _envolver_thick(original):
    def _draw_thick(self, gl, mvp, view_rect, buf, batch, *args, **kwargs):
        if id(batch) in _pintadas:
            return None
        return original(self, gl, mvp, view_rect, buf, batch, *args, **kwargs)
    _draw_thick._puente_original = original
    _draw_thick._puente_fabrica = _envolver_thick
    return _draw_thick


def _envolver_paint(original):
    def paintGL(self, *args, **kwargs):
        _pintadas.clear()
        try:
            return original(self, *args, **kwargs)
        finally:
            _pintadas.clear()
    paintGL._puente_original = original
    paintGL._puente_fabrica = _envolver_paint
    return paintGL


def nativo(batches) -> bool:
    """IngeCAD 0.6.7 en adelante pinta por grupos él mismo (lo tomó de la
    3.16.2): sus tandas saben qué grupo tiene cada trazo."""
    return hasattr(getattr(batches, "Batch", None), "group_set")


def _quitar(batches, backend) -> None:
    """Deja la pantalla como la pinta IngeCAD. En 0.6.7 el envoltorio de
    ``_draw_images`` no aceptaba ``group=`` y cada cuadro fallaba: la vista
    quedaba sin pintar (3.20.1)."""
    from .dibujo import desenvolver
    for modulo in (batches, backend):
        actual = getattr(modulo, "pack", None)
        if getattr(actual, "_puente_fabrica", None) is _envolver_pack:
            setattr(modulo, "pack", actual._puente_original)
    # sólo los envoltorios de ESTE módulo (3.84.4): el de afuera de paintGL
    # podía ser el de la hoja de textos legibles, y abrir un dibujo lo sacaba
    desenvolver(batches.Batch, "visible_runs", _envolver_runs)
    try:
        from views.viewport import Viewport
    except Exception:  # noqa: BLE001
        return
    for nombre, fabrica in (("_draw_images", _envolver_imagenes),
                            ("_draw_thick", _envolver_thick),
                            ("paintGL", _envolver_paint)):
        desenvolver(Viewport, nombre, fabrica)


def _envolver_grupos(original):
    """order_groups de IngeCAD: en una hoja, también el orden del modelo (los
    identificadores no se repiten entre espacios; el de la hoja manda)."""
    def order_groups(layout):
        grupos = original(layout)
        if not activo():
            return grupos
        try:
            if not getattr(layout, "is_any_paperspace", False):
                return grupos
            modelo = original(layout.doc.modelspace())
        except Exception:  # noqa: BLE001 -- sin el del modelo, como venía
            return grupos
        if not modelo:
            return grupos
        juntos = dict(modelo)
        juntos.update(grupos)
        return juntos
    order_groups._puente_original = original
    order_groups._puente_fabrica = _envolver_grupos
    return order_groups


def en_orden_de_dibujo(msp, entidades) -> list:
    """Las entidades del modelo en su orden de dibujo (la tabla SORTENTS, como
    ezdxf.reorder.ascending): primero lo enviado al fondo, al final lo traído
    al frente; sin tabla, como vienen."""
    lista = list(entidades)
    try:
        tabla = dict(msp.get_redraw_order())
    except Exception:  # noqa: BLE001
        return lista
    if not tabla:
        return lista

    def clave(par):
        i, e = par
        try:
            h = e.dxf.handle
            return (int(tabla.get(h, h), 16), i)
        except Exception:  # noqa: BLE001 -- sin identificador: donde estaba
            return (-1, i)
    return [e for _i, e in sorted(enumerate(lista), key=clave)]


def _envolver_filtro(original):
    """filter_vp_entities de ezdxf: lo que dibuja una ventana de la hoja, en el
    orden de dibujo del modelo (vista previa, PDF e impresión lo pintan en ese
    orden, uno encima del otro)."""
    def filter_vp_entities(msp, limits, bbox_cache=None):
        entidades = original(msp, limits, bbox_cache)
        if not activo():
            return entidades
        return iter(en_orden_de_dibujo(msp, entidades))
    filter_vp_entities._puente_original = original
    filter_vp_entities._puente_fabrica = _envolver_filtro
    return filter_vp_entities


def _instalar_hojas() -> None:
    for nombre_mod, nombre, fabrica in (("core.draworder", "order_groups", _envolver_grupos),
                                        ("ezdxf.addons.drawing.pipeline", "filter_vp_entities",
                                         _envolver_filtro)):
        try:
            import importlib
            modulo = importlib.import_module(nombre_mod)
        except Exception:  # noqa: BLE001
            continue
        actual = getattr(modulo, nombre, None)
        if actual is None or getattr(actual, "_puente_fabrica", None) is fabrica:
            continue
        setattr(modulo, nombre, fabrica(getattr(actual, "_puente_original", actual)))


def instalar() -> None:
    """Se llama al cargar el plugin. El envoltorio de la escena mira
    ``activo()`` al armarla: prender o apagar el módulo no necesita
    reinstalarlos. Con un IngeCAD que ya pinta por grupos no se envuelve
    nada: los botones quedan y la pantalla es la de IngeCAD."""
    from .dibujo import envolver
    _instalar_hojas()          # hojas e impresión: también con IngeCAD 0.8 (3.102.1)
    try:
        from render import backend, batches
    except Exception:  # noqa: BLE001
        return
    if nativo(batches):
        _quitar(batches, backend)
        return
    for modulo in (batches, backend):
        actual = getattr(modulo, "pack", None)
        if actual is not None and getattr(actual, "_puente_fabrica", None) is not _envolver_pack:
            setattr(modulo, "pack", _envolver_pack(getattr(actual, "_puente_original", actual)))
    if getattr(batches.Batch.visible_runs, "_puente_fabrica", None) is not _envolver_runs:
        envolver(batches.Batch, "visible_runs", _envolver_runs, reemplazar=True)
    try:
        from views.viewport import Viewport
    except Exception:  # noqa: BLE001  (sin Qt: sólo la escena)
        return
    for nombre, fabrica in (("_draw_images", _envolver_imagenes),
                            ("_draw_thick", _envolver_thick),
                            ("paintGL", _envolver_paint)):
        if getattr(getattr(Viewport, nombre, None), "_puente_fabrica", None) is not fabrica:
            envolver(Viewport, nombre, fabrica, reemplazar=True)
