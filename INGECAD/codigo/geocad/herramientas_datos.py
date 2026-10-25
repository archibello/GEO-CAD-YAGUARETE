# SPDX-License-Identifier: GPL-3.0-or-later
"""La barra "Datos": consultas, temático, rótulos y objetos nuevos con
formulario. Todo lo que cambia el dibujo es un Command con deshacer exacto;
nada de esto escribe en el archivo de datos (eso es sólo el guardado)."""
from __future__ import annotations

from core.actions import EraseCommand
from core.commands import Command, CompositeCommand
from core.layers import NewLayerCommand
from core.xdata import APPID, ensure_appid
from tools.base import Tool

from .modelo import AddToModelCommand
from . import config, datos, enlace, puente

LABEL_TAG = "SHP-LABEL"
#: colores ACI para categorías (bien distintos entre sí) y rampa amarillo -> rojo
CATEGORY_COLORS = (1, 3, 5, 30, 6, 4, 2, 140, 210, 40, 92, 230, 50, 160, 12, 72)
RAMP = {2: (51, 10), 3: (51, 30, 10), 4: (51, 40, 30, 10), 5: (51, 41, 31, 21, 10),
        6: (51, 41, 31, 21, 11, 240), 7: (51, 43, 33, 23, 13, 11, 240)}
NULL_COLOR = 8


# -- utilidades comunes ----------------------------------------------------------------------

def _window(ctx):
    return getattr(ctx.services, "window", None)


def _document(ctx):
    document = getattr(ctx.services, "document", None)
    if document is None:
        document = getattr(_window(ctx), "document", None)
    return document


def choose_link(ctx, document, kinds=None, imported=True):
    """Capa conectada o (``imported``) SHP importado con base de datos."""
    links = enlace.read_links(document.doc)
    if kinds:
        links = {k: v for k, v in links.items() if v.kind in kinds}
    names = {k: f"{k}  ({v.name})" for k, v in links.items()}
    if imported and not kinds:
        names = {**datos.data_tables(document), **names}
    if not names:
        ctx.echo("No hay capas SIG conectadas" + (" de ese tipo" if kinds else "") +
                 " (QGIS ▸ Conectar datos SIG)"
                 + (" ni SHP importados con base de datos (IMPORTARSHP)." if imported else "."))
        return None
    if len(names) == 1:
        return next(iter(names))
    keys = sorted(names)
    labels = [names[k] for k in keys]
    answer = ctx.ask_choice("¿Qué capa?", labels, labels[0])
    return None if answer is None else keys[labels.index(answer)]


def select(ctx, entities) -> None:
    """Deja ``entities`` seleccionadas en el dibujo (como Ctrl+A)."""
    services = ctx.services
    handles = {e.dxf.handle for e in entities}
    try:
        services.selection = handles
        services._highlight_cache = None
        services._grips_cache = None
        services.changed.emit()
    except AttributeError:
        pass
    puente.table_selection_changed()


def entities_of(document, key, fids):
    fids = set(fids)
    return [e for fid, e in datos.tagged(document, key) if fid in fids]


# -- comandos con deshacer -------------------------------------------------------------------

class ColorCommand(Command):
    """Cambia el color (ACI) de muchas entidades; deshacer restaura el de cada una."""

    name = "SHP theme"

    def __init__(self, changes) -> None:
        self.changes = list(changes)       # (entidad, color ACI)
        self._old = []

    def do(self, document) -> None:
        self._old = [(e, e.dxf.get("color", None)) for e, _c in self.changes]
        for e, color in self.changes:
            e.dxf.color = color
        document.dirty = True

    def undo(self, document) -> None:
        for e, color in self._old:
            if color is None:
                e.dxf.discard("color")
            else:
                e.dxf.color = color
        document.dirty = True


class NewFeaturesCommand(Command):
    """Convierte entidades sueltas en objetos nuevos de una capa SIG, con sus
    atributos pendientes. Deshacer las deja exactamente como estaban."""

    name = "SHP new"

    def __init__(self, key: str, items, values: dict) -> None:
        self.key = key
        self.items = list(items)           # (entidad, id provisorio < 0)
        self.values = dict(values)
        self._old = []

    def do(self, document) -> None:
        doc = document.doc
        self._old = []
        for e, tmp in self.items:
            try:
                old_xdata = list(e.get_xdata(APPID))
            except Exception:
                old_xdata = None
            self._old.append((e, e.dxf.get("layer", "0"), old_xdata))
            e.dxf.layer = self.key
            enlace.set_feat_tag(e, self.key, tmp, 0)
        link = enlace.read_links(doc)[self.key]
        for _e, tmp in self.items:
            link.pending[tmp] = dict(self.values)
        enlace.write_link(doc, link)
        document.dirty = True

    def undo(self, document) -> None:
        doc = document.doc
        for e, layer, xdata in self._old:
            e.dxf.layer = layer
            if xdata is None:
                enlace.clear_feat_tag(e)
            else:
                ensure_appid(doc)
                e.set_xdata(APPID, xdata)
        link = enlace.read_links(doc).get(self.key)
        if link is not None:
            for _e, tmp in self.items:
                link.pending.pop(tmp, None)
            enlace.write_link(doc, link)
        document.dirty = True


def next_temp_ids(document, key, n: int) -> list[int]:
    link = enlace.read_links(document.doc)[key]
    tagged, _ = enlace.linked_entities(document, key)
    used = [f for f in link.pending if f < 0] + [t.fid for t, _e in tagged if t.fid < 0]
    start = min(used + [0]) - 1
    return [start - i for i in range(n)]


# -- temático ----------------------------------------------------------------------------------

def theme_colors(data: datos.LayerData, field: str, method: str, classes: int = 5):
    """{fid: color} y la leyenda [(color, texto)]."""
    f = data.field(field)
    values = {r.fid: r.values.get(f.name) for r in data.rows}
    legend = []
    colors = {}
    if method == "rangos":
        nums = [v for v in values.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not nums:
            raise ValueError(f"«{f.name}» no tiene valores numéricos")
        lo, hi = min(nums), max(nums)
        classes = max(2, min(7, classes))
        ramp = RAMP[classes]
        step = (hi - lo) / classes if hi > lo else 1.0
        for i, color in enumerate(ramp):
            a = lo + i * step
            b = hi if i == classes - 1 else lo + (i + 1) * step
            legend.append((color, f"{datos.show(round(a, 6))} a {datos.show(round(b, 6))}"))
        for fid, v in values.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                k = min(classes - 1, int((v - lo) / step)) if hi > lo else 0
                colors[fid] = ramp[k]
            else:
                colors[fid] = NULL_COLOR
    else:
        cats = sorted({datos.show(v) for v in values.values() if v not in (None, "")},
                      key=lambda s: (s.casefold(), s))
        palette = {c: CATEGORY_COLORS[i % len(CATEGORY_COLORS)] for i, c in enumerate(cats)}
        legend = [(palette[c], c) for c in cats]
        for fid, v in values.items():
            colors[fid] = palette.get(datos.show(v), NULL_COLOR) if v not in (None, "") else NULL_COLOR
    if NULL_COLOR in colors.values():
        legend.append((NULL_COLOR, "(sin dato)"))
    return colors, legend


# -- herramientas ----------------------------------------------------------------------------------

class QueryTool(Tool):
    """SHPQUERY: selecciona los objetos que cumplen una condición de atributos."""

    def start(self) -> None:
        self.name = "SHPQUERY"
        document = _document(self.ctx)
        key = choose_link(self.ctx, document)
        if key:
            text = self.ctx.ask_text(
                "Consulta (ej.: MANZANA = 12 Y SUP_M2 > 500, TITULAR CONTIENE 'pérez'):", "")
            if text is not None:
                run_query(self.ctx, document, key, text)
        self.ctx.finish()


def run_query(ctx, document, key, text):
    data = datos.layer_data(document, key)
    try:
        test = datos.parse_query(text, data.fields)
    except datos.QueryError as exc:
        ctx.echo(f"Consulta no válida: {exc}")
        ctx.echo("Campos: " + ", ".join(f.name for f in data.fields))
        return None
    fids = [r.fid for r in data.rows if test(r)]
    ents = entities_of(document, key, fids)
    select(ctx, ents)
    sin_dibujo = len(fids) - len({datos.fid_of(document, e, key) for e in ents})
    ctx.echo(f"{len(fids)} registro(s) cumplen «{text}»; {len(ents)} objeto(s) seleccionados."
             + (f" ({sin_dibujo} sin geometría)" if sin_dibujo > 0 else ""))
    return fids


class SpatialQueryTool(Tool):
    """SHPSPATIAL: selecciona por ubicación respecto de una zona elegida."""

    wants_selection = True
    MODES = ("Dentro de la zona", "Toca la zona", "A una distancia de la zona")

    def start(self) -> None:
        self.name = "SHPSPATIAL"

    def selection_prompt(self) -> str:
        return "Seleccione la zona (polilíneas cerradas, círculos u otros objetos):"

    def on_selection(self, entities: list) -> None:
        document = _document(self.ctx)
        if not entities:
            self.ctx.echo("No se eligió ninguna zona.")
            self.ctx.finish()
            return
        key = choose_link(self.ctx, document)
        if key:
            mode = self.ctx.ask_choice("Condición:", list(self.MODES), self.MODES[1])
            if mode is not None:
                dist = 0.0
                if mode == self.MODES[2]:
                    raw = self.ctx.ask_text("Distancia:", "10")
                    try:
                        dist = float(str(raw).replace(",", "."))
                    except (TypeError, ValueError):
                        self.ctx.echo("Distancia no válida.")
                        self.ctx.finish()
                        return
                code = ("dentro", "toca", "distancia")[self.MODES.index(mode)]
                zone = [e for e in entities if datos.fid_of(document, e, key) is None] or entities
                fids = datos.spatial_select(document, key, zone, code, dist)
                ents = entities_of(document, key, fids)
                select(self.ctx, ents)
                self.ctx.echo(f"{len(fids)} objeto(s) de {key} cumplen «{mode.lower()}»"
                              + (f" ({dist:g})" if code == "distancia" else "") + ".")
        self.ctx.finish()


class ThemeTool(Tool):
    """SHPTHEME: colorea los objetos según un campo (sólo el dibujo)."""

    def start(self) -> None:
        self.name = "SHPTHEME"
        document = _document(self.ctx)
        key = choose_link(self.ctx, document)
        if key:
            self._theme(document, key)
        self.ctx.finish()

    def _theme(self, document, key) -> None:
        echo = self.ctx.echo
        data = datos.layer_data(document, key)
        labels = [f.name for f in data.fields]
        if not labels:
            echo("La capa no tiene campos.")
            return
        field = self.ctx.ask_choice("Campo para el temático:", labels, labels[0])
        if field is None:
            return
        f = data.field(field)
        method = "categorias"
        classes = 5
        if f.family in ("int", "real"):
            m = self.ctx.ask_choice("Método:", ["Por categorías (cada valor)", "Por rangos"],
                                    "Por rangos")
            if m is None:
                return
            if m.startswith("Por rangos"):
                method = "rangos"
                raw = self.ctx.ask_text("Cantidad de rangos (2 a 7):", "5")
                try:
                    classes = int(raw)
                except (TypeError, ValueError):
                    classes = 5
        try:
            colors, legend = theme_colors(data, f.name, method, classes)
        except ValueError as exc:
            echo(str(exc))
            return
        by_fid = data.entities_by_fid(document)
        changes = [(e, colors.get(fid, NULL_COLOR)) for fid, ents in by_fid.items() for e in ents]
        self.ctx.execute(ColorCommand(changes))
        echo(f"Temático de {key} por {f.name} ({'rangos' if method == 'rangos' else 'categorías'}):")
        for color, text in legend[:30]:
            echo(f"  color {color:>3}: {text}")
        if len(legend) > 30:
            echo(f"  ... y {len(legend) - 30} valores más")
        echo("Sólo cambia el dibujo; los datos no se tocan. Para quitarlo: SHPTHEMEOFF.")


class ThemeOffTool(Tool):
    """SHPTHEMEOFF: vuelve los objetos al color de su capa."""

    def start(self) -> None:
        self.name = "SHPTHEMEOFF"
        document = _document(self.ctx)
        key = choose_link(self.ctx, document)
        if key:
            self.ctx.execute(ColorCommand([(e, 256) for _f, e in datos.tagged(document, key)]))
            self.ctx.echo(f"{key}: colores por capa.")
        self.ctx.finish()


def label_layer(key: str) -> str:
    return f"{key}-ROTULOS"


def _labels_by_space(document, key, fids=None):
    """[(espacio, [rótulos])]: también los que quedaron en una presentación
    (ROTULOSIG corrido con la lámina abierta, antes de 3.25.4). Con ``fids``,
    sólo los rótulos de esos registros (3.26.1)."""
    out = []
    for space in document.doc.layouts:
        found = []
        for e in space:
            try:
                values = [v for _c, v in e.get_xdata(APPID)]
            except Exception:
                continue
            if len(values) >= 2 and values[0] == LABEL_TAG and values[1] == key:
                if fids is None or (len(values) > 2 and values[2] in fids):
                    found.append(e)
        if found:
            out.append((space, found))
    return out


def existing_labels(document, key, fids=None):
    return [e for _s, ents in _labels_by_space(document, key, fids) for e in ents]


def erase_labels(document, key, fids=None) -> list:
    """Un EraseCommand por espacio: EraseCommand borra en el espacio que
    tiene fijado, y el activo no tiene por qué ser el de los rótulos."""
    commands = []
    for space, ents in _labels_by_space(document, key, fids):
        command = EraseCommand(ents)
        command._space = space
        commands.append(command)
    return commands


def label_commands(document, key, field: str, height: float, opciones=None, fids=None):
    """Los rótulos de ``field``, ubicados con las reglas de rotulos.py (3.26.0):
    polígonos dentro y centrados, líneas según su eje, puntos centrados o
    desde el punto. Devuelve (comando, rótulos, reemplazados); comando.omitidos
    y comando.quedan (rótulos anteriores que siguen).

    ``fids`` (3.26.1): sólo esos registros (los objetos seleccionados). Sus
    rótulos anteriores se reemplazan y los de los demás quedan: cada
    selección SUMA a la composición. None = toda la capa, reemplazando todo.

    3.48.1: con ``anteriores == "conservar"`` no se borra ningún rótulo (los
    nuevos se suman); con ``altura == "menor"`` todos quedan con la altura
    del más chico de esa vez (cada uno se vuelve a ubicar con ella)."""
    from . import rotulos
    op = opciones or rotulos.OpcionesRotulo()
    medir = rotulos.medidor(document.doc)
    data = datos.layer_data(document, key)
    f = data.field(field)
    by_fid = data.entities_by_fid(document)
    values = {r.fid: datos.show(r.values.get(f.name)) for r in data.rows}
    layer = label_layer(key)
    commands: list = []
    if layer not in document.doc.layers:
        commands.append(NewLayerCommand(layer, color=7))
    if fids is not None:
        fids = set(fids)
        by_fid = {k: v for k, v in by_fid.items() if k in fids}
    if op.anteriores == "conservar":
        old = []
        quedan = _textos(existing_labels(document, key))
    else:
        old = existing_labels(document, key, fids)
        quedan = _textos(existing_labels(document, key)) - _textos(old)
        commands += erase_labels(document, key, fids)
    n = omitted = 0
    ubicados = []
    for fid, ents in sorted(by_fid.items()):
        text = values.get(fid, "")
        if not text:
            continue
        rings = [r for e in ents for r in datos.entity_rings(e)]
        u = rotulos.ubicar(text, height, rings, op, medir)
        if u is None:
            omitted += 1 if rings else 0
            continue
        ubicados.append((fid, text, rings, u))
    if op.altura == "menor" and ubicados:
        menor = min(u.altura for _f, _t, _r, u in ubicados)
        ubicados = [(fid, text, rings, u if u.altura <= menor
                     else rotulos.ubicar(text, menor, rings, op, medir) or u)
                    for fid, text, rings, u in ubicados]
    for fid, text, rings, u in ubicados:
        def make(msp, text=text, u=u, fid=fid):
            from ezdxf.enums import TextEntityAlignment

            ensure_appid(msp.doc)
            entity = msp.add_text(text, height=u.altura, rotation=u.giro)
            entity.set_placement(u.punto, align=getattr(TextEntityAlignment, u.alineacion))
            entity.set_xdata(APPID, [(1000, LABEL_TAG), (1000, key), (1071, fid), (1000, f.name)])
            return entity

        commands.append(AddToModelCommand("SHP label", make, layer=layer))
        if u.circulo:
            # 3.48.0: el círculo alrededor, con el XDATA de su rótulo (se borra
            # y se reemplaza con él, como los fondos que llegan de QGIS)
            def circulo(msp, u=u, fid=fid):
                ensure_appid(msp.doc)
                entity = msp.add_circle(u.punto, radius=u.circulo)
                entity.set_xdata(APPID, [(1000, LABEL_TAG), (1000, key), (1071, fid), (1000, f.name)])
                return entity

            commands.append(AddToModelCommand("SHP label circle", circulo, layer=layer))
        n += 1
    command = CompositeCommand("SHP labels", commands)
    command.omitidos = omitted          # polígonos donde el rótulo quedaría ilegible
    command.quedan = quedan             # rótulos anteriores que siguen
    command.conserva = op.anteriores == "conservar"
    return command, n, _textos(old)


def _textos(entidades) -> int:
    """Cuántos rótulos son (sin contar sus círculos ni fondos)."""
    return sum(1 for e in entidades if e.dxftype() in ("TEXT", "MTEXT"))


class LabelTool(Tool):
    """SHPLABEL: rótulos con el valor de un campo, en la capa <capa>-ROTULOS.

    3.26.1: rotula sólo los objetos seleccionados (antes o al «Designar») y
    SUMA a los rótulos que ya están; Enter sin elegir nada = toda la capa."""

    wants_selection = True
    modifies_selection = False          # sólo lee los objetos: también en capas bloqueadas

    def start(self) -> None:
        self.name = "SHPLABEL"

    def selection_prompt(self) -> str:
        return "Designe los objetos a rotular (Enter sin elegir = toda la capa):"

    def on_selection(self, entities: list) -> None:
        document = _document(self.ctx)
        fids = None
        if entities:
            elegidos = objetos_por_capa(document, entities)
            if not elegidos:
                self.ctx.echo("Los objetos elegidos no son de una capa SIG conectada ni de un "
                              "SHP importado con base de datos.")
                self.ctx.finish()
                return
            if len(elegidos) == 1:
                key = next(iter(elegidos))
            else:
                keys = sorted(elegidos)
                answer = self.ctx.ask_choice("¿Qué capa?", keys, keys[0])
                key = answer if answer in elegidos else None
            if key:
                fids = elegidos[key]
        else:
            key = choose_link(self.ctx, document)
        if key:
            data = datos.layer_data(document, key)
            names = [f.name for f in data.fields]
            elegido = self._preguntar(names) if names else None
            if elegido is not None:
                field, height, op = elegido
                command, n, replaced = label_commands(document, key, field, height, op, fids)
                self.ctx.execute(command)
                self.ctx.echo(resumen_rotulos(command, n, replaced, field, key, fids))
        self.ctx.finish()

    def _preguntar(self, names):
        """(campo, altura, opciones) o None. La ventana de rotulos_ui (3.26.0);
        sin ella, las preguntas de siempre con las últimas opciones."""
        from . import rotulos
        op = rotulos.leer_opciones()
        altura = float(config.get("altura_rotulos"))
        try:
            from .rotulos_ui import RotulosDialog
        except Exception:  # noqa: BLE001 -- sin Qt
            RotulosDialog = None
        if RotulosDialog is not None:
            dlg = RotulosDialog(names, altura, op, getattr(self.ctx.services, "window", None))
            if not dlg.exec():
                return None
            op = dlg.opciones()
            rotulos.guardar_opciones(op)
            return dlg.campo.currentText(), dlg.altura.value(), op
        field = self.ctx.ask_choice("Campo para rotular:", names, names[0])
        if field is None:
            return None
        raw = self.ctx.ask_text("Altura del texto:", f"{altura:g}")
        try:
            height = float(str(raw).replace(",", "."))
            if height <= 0:
                raise ValueError
        except (TypeError, ValueError):
            self.ctx.echo("Altura no válida.")
            return None
        return field, height, op


def objetos_por_capa(document, entities) -> dict:
    """{capa SIG: {registros}} de los objetos elegidos (los rótulos y lo que
    no es de una capa con base de datos se ignoran)."""
    out: dict = {}
    keys = list(datos.data_tables(document))
    for e in entities:
        for key in keys:
            fid = datos.fid_of(document, e, key)
            if fid is not None:
                out.setdefault(key, set()).add(fid)
                break
    return out


def resumen_rotulos(command, n: int, replaced: int, field: str, key: str, fids=None) -> str:
    omitidos = getattr(command, "omitidos", 0)
    quedan = getattr(command, "quedan", 0)
    texto = f"{n} rótulo(s) de {field} en la capa {label_layer(key)}"
    if fids is not None:
        texto += f" ({len(fids)} objeto(s) elegidos)"
    if replaced:
        texto += f"; reemplazan a {replaced} anteriores"
    if quedan and getattr(command, "conserva", False):
        texto += f"; se suman a {quedan} anteriores"
    elif quedan:
        texto += f"; quedan {quedan} de otros objetos"
    if omitidos:
        texto += f"; {omitidos} quedaban demasiado chicos para leerse en su polígono y se omitieron"
    return texto + "."


class LabelOffTool(Tool):
    """SHPLABELOFF: borra los rótulos de una capa SIG."""

    def start(self) -> None:
        self.name = "SHPLABELOFF"
        document = _document(self.ctx)
        key = choose_link(self.ctx, document)
        if key:
            old = existing_labels(document, key)
            if old:
                self.ctx.execute(CompositeCommand("SHP labels off", erase_labels(document, key)))
            texts = sum(1 for e in old if e.dxftype() == "TEXT")
            extra = len(old) - texts
            self.ctx.echo(f"{texts} rótulo(s) borrados"
                          + (f" (y {extra} fondo(s))." if extra else "."))
        self.ctx.finish()


class NewFeatureTool(Tool):
    """SHPNEW: convierte lo que dibujó (polilíneas, líneas, puntos) en objetos
    nuevos de una capa SIG y pide sus atributos en un formulario."""

    wants_selection = True

    def start(self) -> None:
        self.name = "SHPNEW"

    def selection_prompt(self) -> str:
        return "Seleccione lo que dibujó para agregarlo a una capa SIG:"

    def on_selection(self, entities: list) -> None:
        self._run(entities)
        self.ctx.finish()

    def _run(self, entities) -> None:
        from .checkin import GeometryError, part_from_entity

        echo = self.ctx.echo
        document = _document(self.ctx)
        free = [e for e in entities if enlace.feat_tag(e) is None]
        if not free:
            echo("Seleccione objetos que todavía no pertenezcan a una capa SIG.")
            return
        kinds = set()
        for e in free:
            t = e.dxftype()
            if t == "POINT":
                kinds.add("point")
            elif t in ("LWPOLYLINE", "POLYLINE", "LINE"):
                kinds.update(("line", "polygon") if t != "LINE" else ("line",))
        key = choose_link(self.ctx, document, kinds or None, imported=False)
        if not key:
            return
        link = enlace.read_links(document.doc)[key]
        usable, bad = [], []
        for e in free:
            try:
                part_from_entity(e, link.kind)
                usable.append(e)
            except GeometryError as exc:
                bad.append(f"{e.dxftype()} {e.dxf.handle}: {exc}")
        for b in bad[:10]:
            echo("No sirve: " + b)
        if not usable:
            return
        data = datos.LayerData(document, key)
        values = ask_attributes(self.ctx, data, f"Atributos del objeto nuevo ({key})")
        if values is None:
            echo("Cancelado.")
            return
        if len(usable) > 1 and self.ctx.ask_choice(
                f"¿Crear {len(usable)} objetos nuevos con estos mismos atributos?",
                ["Sí", "No"], "No") != "Sí":
            echo("Cancelado.")
            return
        ids = next_temp_ids(document, key, len(usable))
        self.ctx.execute(NewFeaturesCommand(key, zip(usable, ids), values))
        puente.table_refresh()
        echo(f"{len(usable)} objeto(s) nuevos en {key}. Se escriben al guardar "
             "(Devolver todo a QGIS).")


def ask_attributes(ctx, data: datos.LayerData, title: str):
    """Formulario: en la ventana, un diálogo con todos los campos; sin ventana,
    una pregunta por campo. Valida cada valor y los obligatorios."""
    fields = [f for f in data.fields if f.editable]
    window = _window(ctx)
    if window is not None:
        from .formulario import ask_form

        return ask_form(window, title, fields, data.validate)
    values = {}
    for f in fields:
        while True:
            text = ctx.ask_text(f"{f.label}{' *' if f.required else ''}:", "")
            if text is None:
                return None
            if f.required and not str(text).strip():
                ctx.echo(f"«{f.name}» es obligatorio.")
                continue
            try:
                data.validate(f.name, text)
            except Exception as exc:
                ctx.echo(f"Valor no válido: {exc}")
                continue
            break
        if str(text).strip():
            values[f.name] = text
    return values


class TableTool(Tool):
    """SHPTABLE: abre la tabla de atributos acoplable."""

    def start(self) -> None:
        self.name = "SHPTABLE"
        window = _window(self.ctx)
        if window is None:
            self.ctx.echo("La tabla de atributos necesita la ventana de IngeCAD.")
        else:
            from .tabla import show_table

            show_table(window)
        self.ctx.finish()


DATA_TOOLS = {
    "SHPTABLE": TableTool,
    "SHPQUERY": QueryTool,
    "SHPSPATIAL": SpatialQueryTool,
    "SHPTHEME": ThemeTool,
    "SHPTHEMEOFF": ThemeOffTool,
    "SHPLABEL": LabelTool,
    "SHPLABELOFF": LabelOffTool,
    "SHPNEW": NewFeatureTool,
}
