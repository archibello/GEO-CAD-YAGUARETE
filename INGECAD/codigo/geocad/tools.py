# SPDX-License-Identifier: GPL-3.0-or-later
"""Los comandos del complemento: cáscaras finas sobre ``enlace`` y
``checkin``. Funcionan también sin ventana (las pruebas los manejan con
un contexto falso): donde la GUI abriría un diálogo, ``ask_text`` pide
la ruta."""
from __future__ import annotations

from pathlib import Path

from tools.base import Tool

from . import bloqueo, checkin, config, crs as crs_mod, enlace, estilo, fuentes, puente, shpio

DATA_FILTER = ("Datos SIG (*.gpkg *.GPKG *.shp *.SHP);;GeoPackage (*.gpkg *.GPKG);;"
               "Shapefile (*.shp *.SHP);;Todos los archivos (*)")
YES, NO = "Sí", "No"


def _window(ctx):
    return getattr(ctx.services, "window", None)


def _document(ctx):
    document = getattr(ctx.services, "document", None)
    if document is None:
        document = getattr(_window(ctx), "document", None)
    return document


def _confirm(ctx, question: str) -> bool:
    return ctx.ask_choice(question, [YES, NO], NO) == YES


def _choose_link(ctx, document):
    links = enlace.read_links(document.doc)
    if not links:
        ctx.echo("No hay capas SHP conectadas en este dibujo (use SHPCONNECT).")
        return None
    if len(links) == 1:
        return next(iter(links))
    keys = sorted(links)
    labels = [f"{k}  ({links[k].name})" for k in keys]
    answer = ctx.ask_choice("¿Qué capa SHP?", labels, labels[0])
    if answer is None:
        return None
    return keys[labels.index(answer)]


def _link_crs(link) -> crs_mod.Crs:
    try:
        return fuentes.link_crs(link)
    except Exception:
        return crs_mod.Crs(None, "sistema no disponible")


def _drawing_name(document) -> str:
    try:
        return document.name
    except Exception:
        return ""


def _georef_conflict(document, layer: crs_mod.Crs):
    """Mensaje si la capa no puede convivir con la georreferencia del
    dibujo o con otra capa ya conectada; None si está todo bien."""
    from core.georef import read_georef

    project = config.get("crs_proyecto")
    if project and layer.epsg and layer.code != project:
        return (f"la capa está en {layer.label} y el sistema del proyecto "
                f"(configuración común) es {config.display('crs_proyecto', project)}")
    for link in enlace.read_links(document.doc).values():
        other = _link_crs(link)
        if not crs_mod.compatible(layer, other):
            return (f"la capa está en {layer.label} y {link.key} en {other.label}: "
                    "no se mezclan sistemas en un mismo dibujo (no se reproyecta)")
    georef = read_georef(document.doc)
    if georef is None or not layer.epsg:
        return None
    if georef.crs:
        if georef.crs != layer.code:
            return (f"el dibujo está georreferenciado en {georef.crs} y la capa "
                    f"en {layer.code} ({layer.label})")
        return None
    # dibujo en UTM (WGS84 / PSAD56): sólo coincide con WGS 84 / UTM de esa zona
    utm = 32700 + georef.zone if not georef.northern else 32600 + georef.zone
    if georef.datum == "WGS84" and layer.epsg == utm:
        return None
    hemi = "N" if georef.northern else "S"
    return (f"el dibujo está georreferenciado en UTM {georef.zone}{hemi} "
            f"{georef.datum} y la capa en {layer.label}")


class ConnectTool(Tool):
    """SHPCONNECT: conecta una capa de GeoPackage o un shapefile al dibujo
    para editarla (check-out). Puede conectar la capa entera, sólo lo que se
    ve en pantalla o (desde QGIS) sólo los objetos seleccionados. Si la capa
    ya estaba conectada, AMPLÍA la conexión con lo que falte."""

    SCOPES = ("Toda la capa", "Sólo lo que se ve en pantalla")

    def start(self) -> None:
        self.name = "SHPCONNECT"
        window = _window(self.ctx)
        puente.ensure_started(window)
        request = puente.take_request()            # capa mandada desde QGIS
        if request is not None:
            path = request["ruta"]
            gpkg = request.get("formato") == "gpkg" or path.lower().endswith(".gpkg")
            self._connect(path, request.get("tabla") or None if gpkg else None, gpkg,
                          fids=request.get("fids"), bbox=request.get("bbox"),
                          origin="QGIS", pres_qgis=request.get("estilo"))
            self.ctx.finish()
            return
        if window is not None:
            from views import file_dialogs

            path = file_dialogs.get_open_file(window, "Conectar datos SIG", DATA_FILTER)
        else:
            path = self.ctx.ask_text("Archivo .gpkg o .shp:", "")
        if path:
            bbox = None
            screen = _screen_bbox(window)
            if screen is not None:
                scope = self.ctx.ask_choice("¿Qué conectar?", list(self.SCOPES), self.SCOPES[0])
                if scope is None:
                    self.ctx.finish()
                    return
                if scope == self.SCOPES[1]:
                    bbox = screen
            self._connect(path, None, Path(path).suffix.lower() == ".gpkg", bbox=bbox)
        self.ctx.finish()

    # -- leer lo pedido ------------------------------------------------------------
    def _read_gpkg(self, path, table, fids, bbox):
        """(info, features, total, skipped) o None si no se pudo."""
        import sqlite3

        from . import gpkgio as G

        echo = self.ctx.echo
        try:
            conn = G.connect(path)
        except sqlite3.Error as exc:
            echo(f"No se puede abrir {path}: {exc}")
            return None
        try:
            try:
                layers = G.list_layers(conn)
            except sqlite3.Error:
                echo(f"{Path(path).name} no es un GeoPackage válido.")
                return None
            if not layers:
                echo(f"{Path(path).name} no tiene capas vectoriales.")
                return None
            names = [t for t, _g in layers]
            if table is not None:
                match = [n for n in names if n.lower() == table.lower()]
                if not match:
                    echo(f"{Path(path).name} no tiene la capa «{table}».")
                    return None
                table = match[0]
            elif len(names) == 1:
                table = names[0]
            else:
                labels = [f"{t}  ({g})" for t, g in layers]
                answer = self.ctx.ask_choice("¿Qué capa del GeoPackage?", labels, labels[0])
                if answer is None:
                    return None
                table = names[labels.index(answer)]
            try:
                layer = G.open_layer(conn, path, table)
            except (sqlite3.Error, shpio.ShapefileError) as exc:
                echo(f"No se puede abrir la capa {table}: {exc}")
                return None
            if layer.kind == "other":
                echo(f"La capa {table} ({layer.geom_type}) todavía no se puede editar: "
                     "sólo puntos, líneas o polígonos de un mismo tipo.")
                return None
            total = conn.execute(f"SELECT count(*) FROM {G.q(layer.table)}").fetchone()[0]
            wanted = None if fids is None else [int(f) for f in fids]
            if bbox is not None:
                inside = _gpkg_bbox_fids(conn, layer, bbox)
                wanted = inside if wanted is None else [f for f in wanted if f in set(inside)]
            rows = G.read_rows(conn, layer, wanted)
            crs = fuentes.gpkg_crs(conn, layer.srs_id)
        finally:
            conn.close()
        features, skipped = [], 0
        for fid in sorted(rows):
            blob, values = rows[fid]
            g = G.parse_blob(blob) if blob is not None else None
            if g is None or g.is_empty or g.kind != layer.kind:
                skipped += 1
                continue
            features.append((fid, G.row_hash(blob, values), g.parts, g.z))
        kind_code = {"point": shpio.POINT, "line": shpio.POLYLINE, "polygon": shpio.POLYGON}[layer.kind]
        info = {"fmt": "gpkg", "path": layer.path, "table": layer.table, "schema": layer.schema,
                "kind_code": kind_code, "crs": crs, "fields": [c.name for c in layer.columns],
                "type": f"{layer.geom_type}{' Z' if layer.z_flag else ''}{' M' if layer.m_flag else ''}",
                "name": f"{Path(path).name} · {layer.table}", "lock": f"{layer.path}.{layer.table}",
                "key_prefix": "GPKG", "key_name": layer.table, "encoding": ""}
        return info, features, total, skipped

    def _read_shp(self, path, fids, bbox):
        echo = self.ctx.echo
        try:
            sf = shpio.Shapefile(path)
        except (OSError, shpio.ShapefileError) as exc:
            echo(f"No se puede abrir {path}: {exc}")
            return None
        if enlace.kind_of(sf.shape_type) == "other":
            echo(f"El tipo {shpio.SHAPE_NAMES.get(sf.shape_type)} todavía no se puede "
                 "editar (sólo puntos, líneas y polígonos).")
            return None
        candidates = range(len(sf)) if fids is None else \
            sorted({int(f) for f in fids if 0 <= int(f) < len(sf)})
        features, skipped = [], 0
        for fid in candidates:
            if sf.is_deleted(fid):
                skipped += 1
                continue
            if bbox is not None and not shpio.bbox_overlaps(shpio.record_bounds(sf.contents[fid]), bbox):
                continue
            geom = sf.geometry(fid)
            if geom.is_null:
                skipped += 1
                continue
            features.append((fid, sf.hash(fid), geom.parts, geom.z))
        resolved = str(Path(sf.shp_path).resolve())
        info = {"fmt": "shp", "path": resolved, "table": "", "schema": sf.schema_hash,
                "kind_code": sf.shape_type, "crs": fuentes.shp_crs(sf.shp_path),
                "fields": [f.name for f in sf.fields], "type": shpio.SHAPE_NAMES[sf.shape_type],
                "name": Path(path).name, "lock": sf.shp_path, "key_prefix": "SHP",
                "key_name": "", "encoding": sf.encoding}
        return info, features, len(sf), skipped

    # -- conectar o ampliar ------------------------------------------------------------
    def _connect(self, path, table, gpkg, fids=None, bbox=None, origin=None,
                 pres_qgis=None) -> None:
        echo = self.ctx.echo
        document = _document(self.ctx)
        got = self._read_gpkg(path, table, fids, bbox) if gpkg else self._read_shp(path, fids, bbox)
        if got is None:
            return
        info, features, total, skipped = got
        scope = ("los objetos seleccionados en QGIS" if fids is not None else
                 "lo que está en pantalla" if bbox is not None else "toda la capa")
        existing = None
        for link in enlace.read_links(document.doc).values():
            if link.fmt == info["fmt"] and link.path == info["path"] and \
                    (link.table or "").lower() == info["table"].lower():
                existing = link
        if existing is not None:
            self._extend(document, existing, info, features, scope, pres_qgis)
            return
        if not features:
            echo(f"{info['name']}: no hay objetos en {scope}; no se conectó nada.")
            return
        key = enlace.layer_key(document.doc, info["path"], prefix=info["key_prefix"],
                               name=info["key_name"])
        link = enlace.Link(key, info["path"], info["kind_code"], info["schema"], total,
                           fmt=info["fmt"], table=info["table"])
        pres = estilo.presentacion(document, link, pres_qgis, [f[0] for f in features])
        command, n, _ = enlace.build_connect(link, features, skipped, pres)
        partial = len(features) < total - skipped
        lines = [f"Conectada {info['name']} -> capa {key}: {len(features)} de {total} "
                 f"registros ({scope}), {n} entidades ({info['type']})."]
        if partial:
            lines.append("Conexión parcial: sólo esos registros se editan y se guardan; "
                         "para sumar más, vuelva a conectar (amplía la conexión).")
        if skipped:
            lines.append(f"{skipped} registro(s) sin geometría o borrados no se dibujaron.")
        lines += _pres_lines(link, pres)
        lines.append("Campos: " + (", ".join(info["fields"]) or "(sin campos)")
                     + (f"  (codificación {info['encoding']})" if info["encoding"] else ""))
        xs = [p[0] for _f, _h, parts, _z in features for part in parts for p in part]
        self._finish_connect(document, command, info["crs"], info["lock"], key, lines,
                             (min(xs), max(xs)) if xs else None, zoom=bbox is None)

    def _extend(self, document, link, info, features, scope, pres_qgis=None) -> None:
        echo = self.ctx.echo
        if link.schema != info["schema"]:
            echo(f"{link.key}: la estructura de la tabla cambió desde que se conectó; "
                 "guarde, desconecte y vuelva a conectar.")
            return
        import copy

        link = copy.deepcopy(link)
        pres = estilo.presentacion(document, link, pres_qgis,
                                   [f[0] for f in features if f[0] not in link.hashes])
        command, n_rec, n_ent = enlace.extend_connect(link, features, pres)
        if not n_rec:
            echo(f"{link.key} ya tenía conectado todo lo de {scope}.")
            return
        self.ctx.execute(command)
        puente.notify("conectado", [enlace.read_links(document.doc)[link.key]])
        puente.table_refresh()
        echo(f"{link.key}: se sumaron {n_rec} registro(s) ({scope}), {n_ent} entidades. "
             f"Ahora hay {len(link.hashes) + n_rec} conectados.")

    def _finish_connect(self, document, command, layer, target, key, lines, x_range, zoom=True):
        """Georreferencia, bloqueo y ejecución, comunes a los dos formatos."""
        echo = self.ctx.echo
        problem = _georef_conflict(document, layer)
        if problem:
            echo("No se conectó: " + problem + ".")
            return False
        ok, other = bloqueo.acquire(target, _drawing_name(document))
        if not ok:
            echo(f"No se conectó: la capa está tomada por {other.get('owner')} "
                 f"desde {other.get('since')} (dibujo {other.get('drawing')}).")
            return False
        try:
            from core.georef import Georef, SetGeorefCommand, read_georef

            georef_note = ""
            if layer.epsg and not layer.geographic and read_georef(document.doc) is None:
                from core.commands import CompositeCommand

                command = CompositeCommand(command.name, command.commands + [
                    SetGeorefCommand(Georef(crs=layer.code))])
                georef_note = f"El dibujo queda georreferenciado en {layer.code}."
            self.ctx.execute(command)
        except Exception:
            bloqueo.release(target)
            raise
        link = enlace.read_links(document.doc).get(key)
        if link is not None:
            puente.notify("conectado", [link])
        puente.table_refresh()
        for line in lines:
            echo(line)
        echo(f"Sistema de coordenadas: {layer.label}. {georef_note}".rstrip())
        warn = crs_mod.faja_check(layer, *x_range) if x_range else None
        if warn:
            echo("Aviso: " + warn + ".")
        if layer.geographic:
            echo("Aviso: la capa está en coordenadas geográficas (grados), no en metros.")
        window = _window(self.ctx)
        if zoom and window is not None and hasattr(window, "viewport"):
            window.viewport.zoom_extents()
        return True


def _screen_bbox(window):
    """(xmin, ymin, xmax, ymax) de lo que se ve en el espacio modelo, o None."""
    try:
        view = window.viewport.view
        x0, y0 = view.screen_to_world(0, view.height)
        x1, y1 = view.screen_to_world(view.width, 0)
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    except Exception:
        return None


def _gpkg_bbox_fids(conn, layer, bbox):
    """FIDs cuya envolvente toca ``bbox``: con el índice espacial si existe."""
    from . import gpkgio as G

    rtree = f"rtree_{layer.table}_{layer.geom_col}"
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (rtree,)).fetchone():
        rows = conn.execute(f"SELECT id FROM {G.q(rtree)} WHERE maxx >= ? AND minx <= ? "
                            "AND maxy >= ? AND miny <= ?",
                            (bbox[0], bbox[2], bbox[1], bbox[3])).fetchall()
        return sorted(r[0] for r in rows)
    out = []
    for fid, (blob, _v) in G.read_rows(conn, layer).items():
        b = G.blob_bounds(blob) if blob is not None else None
        if b is not None and shpio.bbox_overlaps((b[0], b[2], b[1], b[3]), bbox):
            out.append(fid)
    return sorted(out)


def _x_range(sf):
    import struct

    xmin, _ymin, xmax, _ymax = struct.unpack_from("<4d", sf.shp_header, 36)
    return xmin, xmax


def _pres_lines(link, pres) -> list:
    """Lo que llegó de la presentación de QGIS, para el mensaje de conexión."""
    lines = []
    capas = sorted(n for n, c in link.capas.items() if c)
    if capas:
        lines.append(f"Capas por {link.campo_capa}: " + ", ".join(capas[:12])
                     + (f" y {len(capas) - 12} más" if len(capas) > 12 else ""))
    if any(c is not None for _l, c in pres["objetos"].values()):
        lines.append("Con los colores de QGIS.")
    if pres.get("simbolos"):
        lines.append(f"{len(pres['simbolos'])} punto(s) con su símbolo de QGIS (bloques "
                     f"{estilo.SYMBOL_BLOCK}...).")
    n = sum(1 for c in pres["despues"] if getattr(c, "name", "") == "SHP label")
    if n:
        nb = sum(1 for c in pres["despues"] if getattr(c, "name", "") == "SHP label background")
        lines.append(f"{n} rótulo(s) de QGIS en la capa {link.key}-ROTULOS"
                     + (f", {nb} con su fondo." if nb else "."))
    return lines


def _prepare_style(ctx, document, key, scope=None) -> None:
    """Antes de guardar: los cambios de capa y color pasan a LAYER_CODE /
    CAD_COLOR (un paso de deshacer)."""
    command = estilo.prepare_save(document, key, scope)
    if command is not None:
        ctx.execute(command)


class StatusTool(Tool):
    """SHPSTATUS: qué se guardaría, sin escribir nada."""

    def start(self) -> None:
        self.name = "SHPSTATUS"
        document = _document(self.ctx)
        links = enlace.read_links(document.doc)
        if not links:
            self.ctx.echo("No hay capas SHP conectadas en este dibujo.")
        for key in sorted(links):
            plan = checkin.make_plan(document, key)
            self.ctx.echo(f"[{key}] {plan.link.path}")
            self.ctx.echo(f"  Sistema: {_link_crs(plan.link).label}")
            for line in plan.summary():
                self.ctx.echo("  " + line)
            edits, news = estilo.differences(document, key)
            if edits or news:
                self.ctx.echo(f"  capa/color: {len({f for f, _n, _v in edits})} objeto(s) "
                              f"cambiados y {len(news)} nuevo(s) en capas de LAYER_CODE "
                              "(se suman al guardar)")
        self.ctx.finish()


class CheckinTool(Tool):
    """SHPCHECKIN: devuelve los cambios al shapefile, con respaldo."""

    def start(self) -> None:
        self.name = "SHPCHECKIN"
        puente.ensure_started(_window(self.ctx))
        document = _document(self.ctx)
        key = _choose_link(self.ctx, document)
        if key:
            self._checkin(document, key)
        self.ctx.finish()

    def _checkin(self, document, key) -> None:
        echo = self.ctx.echo
        _prepare_style(self.ctx, document, key)
        plan = checkin.make_plan(document, key)
        for line in plan.summary():
            echo(line)
        if not plan.ok:
            echo("No se guardó nada. Resuelva lo indicado y vuelva a intentar.")
            return
        if plan.empty:
            echo("Sin cambios para guardar.")
            return
        n = len(plan.changes) + len(plan.new)
        if config.get("confirmar_guardado") and not _confirm(
                self.ctx, f"¿Guardar {n} cambio(s) en {plan.link.name}?"):
            echo("Cancelado: no se escribió nada.")
            return
        try:
            result = checkin.commit(plan, _drawing_name(document))
        except checkin.CommitError as exc:
            echo(f"No se guardó: {exc}")
            return
        checkin.refresh_after_commit(document, plan, result)
        puente.notify("guardado", [plan.link])
        puente.table_refresh()
        echo(f"Guardado en {plan.link.name}. Respaldo: {result.backup}")


def _tagged(entities):
    out = []
    for e in entities:
        tag = enlace.feat_tag(e)
        if tag is not None:
            out.append((tag, e))
    return out


class InfoTool(Tool):
    """SHPINFO: los atributos del objeto seleccionado."""

    wants_selection = True

    def start(self) -> None:
        self.name = "SHPINFO"

    def selection_prompt(self) -> str:
        return "Seleccione un objeto de una capa SHP:"

    def on_selection(self, entities: list) -> None:
        document = _document(self.ctx)
        echo = self.ctx.echo
        tagged = _tagged(entities)
        if not tagged:
            echo("El objeto no pertenece a una capa SHP conectada.")
            self.ctx.finish()
            return
        tag, _e = tagged[0]
        link = enlace.read_links(document.doc).get(tag.key)
        if link is None:
            echo("La conexión de este objeto ya no existe.")
            self.ctx.finish()
            return
        try:
            src = fuentes.source_for(link)
            attrs = src.attributes(tag.fid)
        except Exception as exc:
            echo(f"No se pueden leer los atributos: {exc}")
            self.ctx.finish()
            return
        pending = link.pending.get(tag.fid, {})
        echo(f"{link.name}  FID {tag.fid}  parte {tag.part}")
        for f in src.fields():
            if f.name in pending:
                echo(f"  {f.name} = {pending[f.name]}   (sin guardar; antes: {attrs[f.name]})")
            else:
                echo(f"  {f.name} = {attrs[f.name]}")
        if len(tagged) > 1:
            echo(f"({len(tagged) - 1} objeto(s) más seleccionados; se muestra el primero)")
        self.ctx.finish()


class AttrTool(Tool):
    """SHPATTR: cambia un atributo de uno o varios objetos seleccionados."""

    wants_selection = True

    def start(self) -> None:
        self.name = "SHPATTR"

    def selection_prompt(self) -> str:
        return "Seleccione objetos de una capa SHP:"

    def on_selection(self, entities: list) -> None:
        self._edit(entities)
        self.ctx.finish()

    def _edit(self, entities) -> None:
        echo = self.ctx.echo
        document = _document(self.ctx)
        tagged = _tagged(entities)
        if not tagged:
            echo("Nada seleccionado pertenece a una capa SHP conectada.")
            return
        keys = {t.key for t, _e in tagged}
        if len(keys) > 1:
            echo("Seleccione objetos de una sola capa SHP.")
            return
        key = keys.pop()
        link = enlace.read_links(document.doc).get(key)
        if link is None:
            echo("La conexión de estos objetos ya no existe.")
            return
        src = fuentes.source_for(link)
        fields = [f for f in src.fields() if f.editable]
        if not fields:
            echo("Esta capa no tiene campos editables.")
            return
        labels = [f.label for f in fields]
        choice = self.ctx.ask_choice("Campo:", labels, labels[0])
        if choice is None:
            return
        fld = fields[labels.index(choice)]
        fids = sorted({t.fid for t, _e in tagged})
        first = fids[0]
        current = link.pending.get(first, {}).get(fld.name, src.attributes(first)[fld.name])
        value = self.ctx.ask_text(f"Nuevo valor de {fld.name}:", current)
        if value is None:
            return
        try:
            src.validate(fld.name, value)
        except shpio.ShapefileError as exc:
            echo(f"Valor no válido: {exc}")
            return
        if len(fids) > 1 and not _confirm(
                self.ctx, f"¿Poner {fld.name} = «{value}» en {len(fids)} registros?"):
            echo("Cancelado.")
            return
        from core.commands import CompositeCommand

        self.ctx.execute(CompositeCommand("SHP attribute", [
            enlace.AttrEditCommand(key, fid, fld.name, value) for fid in fids]))
        puente.table_refresh()
        echo(f"{fld.name} = «{value}» en {len(fids)} registro(s). "
             "Se escribe en el archivo al guardar (GUARDARSHP).")


class ReleaseTool(Tool):
    """SHPRELEASE: desconecta una capa (quita sus objetos y libera el bloqueo)."""

    def start(self) -> None:
        self.name = "SHPRELEASE"
        document = _document(self.ctx)
        key = _choose_link(self.ctx, document)
        if key:
            self._release(document, key)
        self.ctx.finish()

    def _release(self, document, key) -> None:
        plan = checkin.make_plan(document, key)
        if not plan.empty or plan.conflicts or any(estilo.differences(document, key)):
            if not _confirm(self.ctx, "Hay cambios sin guardar en esta capa y se perderán. "
                                      "¿Desconectar igual?"):
                self.ctx.echo("Cancelado.")
                return
        from core.actions import EraseCommand
        from core.commands import CompositeCommand

        tagged, _untagged = enlace.linked_entities(document, key)
        path = plan.link.lock_target
        self.ctx.execute(CompositeCommand("SHP release", [
            EraseCommand([e for _t, e in tagged]), enlace.LinkCommand(key, None)]))
        bloqueo.release(path)
        puente.notify("liberado", [plan.link])
        puente.table_refresh()
        self.ctx.echo(f"{plan.link.name} desconectado; el archivo quedó como estaba "
                      "en el último guardado.")


class QgisSaveTool(Tool):
    """QGISSAVE: devuelve a QGIS TODO lo modificado, con una sola
    confirmación. Las capas con conflictos o errores no se tocan y se
    informan; las demás se guardan."""

    def start(self) -> None:
        self.name = "QGISSAVE"
        puente.ensure_started(_window(self.ctx))
        self._run(None)
        self.ctx.finish()

    def _run(self, scope) -> None:
        """``scope``: handles de las entidades elegidas, o None para todo."""
        echo = self.ctx.echo
        document = _document(self.ctx)
        links = enlace.read_links(document.doc)
        if not links:
            echo("No hay capas conectadas: no hay nada para devolver a QGIS.")
            return
        keys = sorted(links)
        if scope is not None:
            touched = set()
            for e in document.doc.modelspace():
                if e.dxf.handle in scope:
                    tag = enlace.feat_tag(e)
                    if tag is not None:
                        touched.add(tag.key)
                    elif enlace.owner_of_layer(links, e.dxf.get("layer")) is not None:
                        touched.add(enlace.owner_of_layer(links, e.dxf.get("layer")))
            keys = [k for k in keys if k in touched]
            if not keys:
                echo("Nada de lo seleccionado pertenece a una capa SIG conectada.")
                return
        for key in keys:
            _prepare_style(self.ctx, document, key, scope)
        plans = [checkin.make_plan(document, key, scope) for key in keys]
        ready = [p for p in plans if p.ok and not p.empty]
        blocked = [p for p in plans if not p.ok]
        for p in plans:
            if p.ok and p.empty:
                continue
            for line in p.summary():
                echo(line)
        what = "lo seleccionado" if scope is not None else "todo"
        if not ready:
            echo(f"Sin cambios en {what} para devolver." if not blocked else
                 "No se guardó nada: resuelva lo indicado.")
            return
        total = sum(len(p.changes) + len(p.new) for p in ready)
        question = (f"¿Devolver a QGIS {total} cambio(s) de {what} en {len(ready)} capa(s)?"
                    + (f" ({len(blocked)} capa(s) con problemas quedan sin tocar)" if blocked else ""))
        if config.get("confirmar_guardado") and not _confirm(self.ctx, question):
            echo("Cancelado: no se escribió nada.")
            return
        saved, fids = [], {}
        for plan in ready:
            try:
                result = checkin.commit(plan, _drawing_name(document))
            except checkin.CommitError as exc:
                echo(f"{plan.link.name}: no se guardó: {exc}")
                continue
            checkin.refresh_after_commit(document, plan, result)
            saved.append(plan.link)
            fids[plan.link.key] = ({f for f in plan.changes if f not in plan.deleted}
                                   | set(result.new_fids))
            echo(f"{plan.link.name}: guardado (respaldo {result.backup.name})")
        if saved:
            puente.notify("guardado", saved, fids if scope is not None else None)
            puente.table_refresh()
            echo(f"Listo: {len(saved)} capa(s) devueltas a QGIS"
                 + (" (sólo lo seleccionado)." if scope is not None else "."))


class QgisSaveSelectionTool(QgisSaveTool):
    """QGISSAVESEL: devuelve a QGIS sólo los cambios de los objetos
    seleccionados (los demás cambios quedan pendientes en el dibujo)."""

    wants_selection = True

    def start(self) -> None:
        self.name = "QGISSAVESEL"
        puente.ensure_started(_window(self.ctx))

    def selection_prompt(self) -> str:
        return "Seleccione los objetos cuyos cambios quiere devolver a QGIS:"

    def on_selection(self, entities: list) -> None:
        if not entities:
            self.ctx.echo("No se seleccionó nada.")
        else:
            self._run({e.dxf.handle for e in entities})
        self.ctx.finish()


class ConfigTool(Tool):
    """SHPCONFIG: la configuración común de GeoCAD."""

    def start(self) -> None:
        self.name = "SHPCONFIG"
        window = _window(self.ctx)
        if window is not None:
            from .opciones import open_dialog

            open_dialog(window)
            self.ctx.finish()
            return
        self._command_line()
        self.ctx.finish()

    def _command_line(self) -> None:
        """Sin ventana: lista los ajustes y permite cambiar uno."""
        echo = self.ctx.echo
        values = config.load()
        echo(f"Configuración común de GeoCAD Yaguareté ({config.config_path()}):")
        for s in config.SETTINGS:
            echo(f"  {s.label}: {config.display(s.key, values[s.key])}")
        labels = [s.label for s in config.SETTINGS]
        choice = self.ctx.ask_choice("¿Cambiar cuál?", labels, "")
        if choice is None:
            return
        setting = config.SETTINGS[labels.index(choice)]
        if setting.kind == "choice":
            names = [c[1] for c in setting.choices]
            picked = self.ctx.ask_choice(setting.label, names,
                                         config.display(setting.key, values[setting.key]))
            if picked is None:
                return
            raw = setting.choices[names.index(picked)][0]
        else:
            raw = self.ctx.ask_text(setting.label + ":", config.display(setting.key, values[setting.key]))
            if raw is None:
                return
        try:
            new = config.save({setting.key: raw}, "IngeCAD")
        except ValueError as exc:
            echo(f"No se guardó: {exc}")
            return
        echo(f"{setting.label}: {config.display(setting.key, new[setting.key])} "
             "(también lo verá QGIS)")


TOOL_CLASSES = {
    "QGISSAVE": QgisSaveTool,
    "QGISSAVESEL": QgisSaveSelectionTool,
    "SHPCONFIG": ConfigTool,
    "SHPCONNECT": ConnectTool,
    "SHPSTATUS": StatusTool,
    "SHPCHECKIN": CheckinTool,
    "SHPINFO": InfoTool,
    "SHPATTR": AttrTool,
    "SHPRELEASE": ReleaseTool,
}


from .herramientas_datos import DATA_TOOLS  # noqa: E402  (la barra Datos)

TOOL_CLASSES.update(DATA_TOOLS)
