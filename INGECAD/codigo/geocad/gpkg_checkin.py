# SPDX-License-Identifier: GPL-3.0-or-later
"""Check-in para capas de GeoPackage.

Mismas reglas que para SHP, pero apoyadas en SQLite:

* ``make_plan`` sólo lee (base abierta en sólo lectura).
* ``commit`` toma el bloqueo de escritura (``BEGIN IMMEDIATE``: ningún
  otro programa puede escribir mientras tanto), vuelve a comprobar los
  conflictos YA con el bloqueo tomado, hace el respaldo .zip con una
  conexión de lectura (la foto exacta de antes de escribir), aplica los
  cambios, verifica fila por fila y recién entonces confirma. Cualquier
  falla -> ROLLBACK: la base queda exactamente como estaba.
* Los FID de GeoPackage son estables: un borrado es un DELETE real y lo
  nuevo recibe FID nuevos; nada se renumera.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from . import gpkgio as G
from .checkin import (CommitError, CommitResult, GeometryError, Plan, backup_dir,
                      carry_values, orient_ring, part_from_entity, prune_backups,
                      scope_filter)
from .enlace import linked_entities, read_links, set_feat_tag, write_link
from . import shpio


def _simple_base(kind: str) -> int:
    return {"point": G.POINT, "line": G.LINESTRING, "polygon": G.POLYGON}[kind]


def open_for_link(link):
    conn = G.connect(link.path)
    layer = G.open_layer(conn, link.path, link.table)
    return conn, layer


def _pending_values(layer, pending: dict) -> dict:
    out = {}
    for name, text in pending.items():
        col = layer.column(name)
        out[col.name] = G.to_value(col, text)
    return out


def _rebuild(orig: G.GGeom, chosen: dict, kind: str):
    """Geometría nueva con las partes que siguen dibujadas. ``chosen``:
    parte -> (puntos, z). Devuelve GGeom o None si no queda nada."""
    keep = sorted(chosen)
    g = G.GGeom(orig.base, orig.has_z, orig.has_m, [], [] if orig.has_z else None,
                [] if orig.has_m else None, [] if orig.structure is not None else None,
                orig.srs_id, orig.env_code)
    flat_pts = [p for part in orig.parts for p in part]
    flat_z = [v for part in orig.z for v in part] if orig.z else None
    flat_m = [v for part in orig.m for v in part] if orig.m else None

    if kind == "polygon":
        polys = {}
        for i, (p, ring) in enumerate(orig.structure):
            polys.setdefault(p, []).append((ring, i))
        new_poly = 0
        for p in sorted(polys):
            rings = polys[p]
            present = [(ring, i) for ring, i in rings if i in chosen]
            if not present:
                continue
            if rings[0][1] not in chosen:
                raise GeometryError(f"se borró el contorno del polígono {p + 1} pero no sus huecos")
            for new_ring, (_ring, i) in enumerate(present):
                _append(g, chosen[i], flat_pts, flat_z, flat_m, i, orig)
                g.structure.append((new_poly, new_ring))
            new_poly += 1
    else:
        for i in keep:
            _append(g, chosen[i], flat_pts, flat_z, flat_m, i, orig)
    if g.is_empty:
        return None
    if g.base in (G.POINT, G.LINESTRING) and len(g.parts) > 1:
        raise GeometryError("un registro simple no puede tener varias partes")
    if g.base == G.POLYGON and g.structure and max(p for p, _r in g.structure) > 0:
        raise GeometryError("un POLYGON no puede tener varios contornos")
    return g


def _append(g, item, flat_pts, flat_z, flat_m, i, orig):
    pts, z = item
    g.parts.append(pts)
    if g.has_z:
        if orig.kind == "point":
            g.z.append([z])
        else:
            g.z.append(carry_values(flat_pts, flat_z, pts) if flat_z else [z] * len(pts))
    if g.has_m:
        g.m.append(carry_values(flat_pts, flat_m, pts) if flat_m else [-1e39] * len(pts))


def _new_geom(layer, kind, pts, z, source: G.GGeom | None) -> G.GGeom:
    col_base = G.NAME_TO_BASE.get(layer.geom_type, 0)
    single = _simple_base(kind)
    if col_base:
        base = col_base
    elif source is not None:
        base = source.base
    else:
        base = single
    has_z = layer.z_flag == 1 or (layer.z_flag == 2 and source is not None and source.has_z)
    has_m = layer.m_flag == 1 or (layer.m_flag == 2 and source is not None and source.has_m)
    g = G.GGeom(base, has_z, has_m, [pts], [[z] * len(pts)] if has_z else None,
                [[-1e39] * len(pts)] if has_m else None,
                [(0, 0)] if kind == "polygon" else None, layer.srs_id, 1)
    if source is not None and not source.is_empty:
        flat_pts = [p for part in source.parts for p in part]
        if has_z and source.z and kind != "point":
            g.z = [carry_values(flat_pts, [v for q in source.z for v in q], pts)]
        if has_m and source.m:
            g.m = [carry_values(flat_pts, [v for q in source.m for v in q], pts)]
    return g


def make_plan(document, key: str, scope=None) -> Plan:
    link = read_links(document.doc)[key]
    plan = Plan(link)
    kind = link.kind
    try:
        conn, layer = open_for_link(link)
    except (OSError, sqlite3.Error, shpio.ShapefileError) as exc:
        plan.errors.append(f"no se puede leer {link.name}: {exc}")
        return plan
    try:
        plan.sf = layer
        if layer.schema != link.schema:
            plan.errors.append("la estructura de la tabla cambió en el GeoPackage; "
                               "desconectá y volvé a conectar")
            return plan
        tagged, untagged = linked_entities(document, key)
        tagged, untagged, scope_fids = scope_filter(tagged, untagged, scope)
        by_fid: dict = {}
        form_new = []
        for tag, e in tagged:
            if tag.fid < 0:
                form_new.append((tag.fid, e))
                continue
            by_fid.setdefault(tag.fid, {}).setdefault(tag.part, []).append(e)
        fids = {f for f in set(link.hashes) | set(by_fid) | set(link.pending) if f >= 0}
        if scope_fids is not None:
            fids &= scope_fids
        for fid in sorted(fids):
            if fid not in link.hashes and not by_fid.get(fid) and fid in link.pending:
                plan.errors.append(f"FID {fid}: tiene atributos pendientes pero no está "
                                   "conectado; conéctelo para poder guardarlos")
        fids = {f for f in fids if f in link.hashes or by_fid.get(f)}
        rows = G.read_rows(conn, layer, fids)
        names = [c.name for c in layer.columns]
        copies = []
        for fid in sorted(fids):
            row = rows.get(fid)
            ents_by_part = by_fid.get(fid, {})
            if row is None:
                if ents_by_part or fid in link.pending:
                    plan.conflicts.append(f"FID {fid}: se borró fuera de IngeCAD")
                else:
                    plan.warnings.append(f"FID {fid} se borró fuera de IngeCAD")
                continue
            blob, values = row
            orig = G.parse_blob(blob) if blob is not None else None
            disk_changed = fid in link.hashes and G.row_hash(blob, values) != link.hashes[fid]
            orig_parts = orig.parts if orig is not None else []

            chosen_ent = {}
            for part_no in sorted(ents_by_part):
                ents = sorted(ents_by_part[part_no], key=lambda x: int(x.dxf.handle, 16))
                keep = ents[0]
                if part_no < len(orig_parts):
                    for e in ents:
                        try:
                            pts, _z, _a = part_from_entity(e, kind)
                        except GeometryError:
                            continue
                        if pts == orig_parts[part_no]:
                            keep = e
                            break
                chosen_ent[part_no] = keep
                copies += [(fid, e) for e in ents if e is not keep]

            chosen, bad, had_arcs = {}, False, False
            for part_no, e in chosen_ent.items():
                try:
                    pts, z, arcs = part_from_entity(e, kind)
                except GeometryError as exc:
                    plan.errors.append(f"FID {fid}, parte {part_no}: {exc}")
                    bad = True
                    continue
                if kind == "polygon" and part_no < len(orig_parts):
                    pts = orient_ring(pts, shpio.signed_area(orig_parts[part_no][:-1]) < 0)
                chosen[part_no] = (pts, z)
                had_arcs = had_arcs or arcs
            if bad:
                continue

            drawn = fid in link.hashes
            if not drawn and not ents_by_part:
                geom_changed = False
            elif kind == "point":
                same = (orig is not None and len(chosen) == len(orig_parts)
                        and all(chosen[i][0] == orig_parts[i] for i in chosen)
                        and (not orig.has_z or all(chosen[i][1] == orig.z[i][0] for i in chosen)))
                geom_changed = not same
            else:
                geom_changed = (orig is None or sorted(chosen) != list(range(len(orig_parts)))
                                or any(chosen[i][0] != orig_parts[i] for i in chosen))

            pending = link.pending.get(fid, {})
            try:
                new_vals = _pending_values(layer, pending) if pending else {}
            except (shpio.ShapefileError, KeyError) as exc:
                plan.errors.append(f"FID {fid}: {exc}")
                continue
            attr_changed = any(values[names.index(n)] != v for n, v in new_vals.items())

            if not geom_changed and not attr_changed:
                if disk_changed:
                    plan.warnings.append(f"FID {fid} cambió fuera de IngeCAD; la vista del "
                                         "dibujo no está al día (no se toca)")
                continue
            if disk_changed:
                plan.conflicts.append(f"FID {fid}: se editó en el dibujo y también en el archivo")
                continue
            if not drawn and geom_changed:
                plan.errors.append(f"FID {fid}: no estaba dibujado y no se puede editar su geometría")
                continue

            new_blob = None
            if geom_changed:
                try:
                    g = _rebuild(orig, chosen, kind) if orig is not None else None
                except GeometryError as exc:
                    plan.errors.append(f"FID {fid}: {exc}")
                    continue
                if g is None:
                    plan.deleted.add(fid)
                    plan.changes[fid] = (None, None)
                    plan.geom_changed.add(fid)
                    continue
                new_blob = G.encode_blob(g)
                plan.geom_changed.add(fid)
                if had_arcs:
                    plan.warnings.append(f"FID {fid}: los arcos se guardaron como tramos rectos")
            if attr_changed:
                plan.attr_changed.add(fid)
            plan.changes[fid] = (new_blob, new_vals if attr_changed else None)
            order = sorted(chosen_ent)
            if kind == "polygon" and new_blob is not None:
                order = [i for i in order if i in chosen]
            for new_no, part_no in enumerate(order):
                plan.retag.append((chosen_ent[part_no], fid, new_no))

        # copias -> filas nuevas con los atributos del original
        for fid, e in copies:
            try:
                pts, z, arcs = part_from_entity(e, kind)
            except GeometryError as exc:
                plan.errors.append(f"copia de FID {fid}: {exc}")
                continue
            if kind == "polygon":
                pts = orient_ring(pts, clockwise=False)
            blob, values = rows[fid]
            source = G.parse_blob(blob) if blob is not None else None
            g = _new_geom(layer, kind, pts, z, source)
            vals = dict(zip(names, values))
            try:
                vals.update(_pending_values(layer, link.pending.get(fid, {})))
            except (shpio.ShapefileError, KeyError) as exc:
                plan.errors.append(f"copia de FID {fid}: {exc}")
                continue
            plan.new.append((G.encode_blob(g), vals, e))

        required = [c.name for c in layer.columns if c.notnull and c.default is None]
        # nuevos con formulario -> filas nuevas con sus atributos
        for tmp_id, e in form_new:
            try:
                pts, z, arcs = part_from_entity(e, kind)
            except GeometryError as exc:
                plan.errors.append(f"objeto nuevo {e.dxf.handle}: {exc}")
                continue
            try:
                vals = _pending_values(layer, link.pending.get(tmp_id, {}))
            except (shpio.ShapefileError, KeyError) as exc:
                plan.errors.append(f"objeto nuevo {e.dxf.handle}: {exc}")
                continue
            missing = [n for n in required if vals.get(n) is None]
            if missing:
                plan.errors.append(f"objeto nuevo {e.dxf.handle}: falta {', '.join(missing)} "
                                   "(obligatorio)")
                continue
            if kind == "polygon":
                pts = orient_ring(pts, clockwise=False)
            plan.new.append((G.encode_blob(_new_geom(layer, kind, pts, z, None)), vals, e))
            plan.form_ids.add(tmp_id)

        # dibujadas a mano sobre la capa -> filas nuevas con valores por defecto
        for e in untagged:
            try:
                pts, z, arcs = part_from_entity(e, kind)
            except GeometryError as exc:
                plan.warnings.append(f"{e.dxftype()} {e.dxf.handle} en la capa se ignora: {exc}")
                continue
            if required:
                plan.errors.append(f"entidad nueva {e.dxf.handle}: los campos "
                                   f"{', '.join(required)} son obligatorios; copie un objeto "
                                   "existente (COPY) en lugar de dibujarlo desde cero")
                continue
            if kind == "polygon":
                pts = orient_ring(pts, clockwise=False)
            plan.new.append((G.encode_blob(_new_geom(layer, kind, pts, z, None)), {}, e))
        if any(v == {} and e in untagged for _b, v, e in plan.new):
            plan.warnings.append("los objetos nuevos dibujados a mano quedan con atributos vacíos")
    finally:
        conn.close()
    return plan


# -- escribir -----------------------------------------------------------------------------

def _backup(path: Path, stem: str) -> Path:
    """Foto de la base con una conexión de lectura (el escritor ya tiene el
    bloqueo, así que nadie más puede cambiarla), verificada y comprimida."""
    bdir = backup_dir(path.parent)
    bdir.mkdir(exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup = bdir / f"{stem}_{stamp}.zip"
    n = 2
    while backup.exists():
        backup = bdir / f"{stem}_{stamp}_{n}.zip"
        n += 1
    fd, tmp = tempfile.mkstemp(suffix=".gpkg", dir=bdir)
    os.close(fd)
    try:
        reader = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        dest = sqlite3.connect(tmp)
        try:
            reader.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CommitError("el respaldo no pasó la verificación de integridad")
        finally:
            dest.close()
            reader.close()
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp, path.name)
        with zipfile.ZipFile(backup) as zf:
            if zf.testzip() is not None or zf.read(path.name) != Path(tmp).read_bytes():
                raise CommitError("el respaldo .zip quedó dañado")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return backup


def commit(plan: Plan, drawing: str = "") -> CommitResult:
    if not plan.ok:
        raise CommitError("el plan tiene errores o conflictos")
    if plan.empty:
        raise CommitError("no hay cambios para guardar")
    link = plan.link
    path = Path(link.path)
    conn = G.connect(path, readonly=False)
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise CommitError(f"el GeoPackage está ocupado (¿QGIS guardando?): {exc}") from exc
        try:
            layer = G.open_layer(conn, path, link.table)
            if layer.schema != link.schema:
                raise CommitError("la estructura de la tabla cambió")
            names = [c.name for c in layer.columns]
            before = G.read_rows(conn, layer)
            # conflictos, otra vez, ya con el bloqueo tomado
            for fid in plan.changes:
                if fid not in before:
                    raise CommitError(f"FID {fid} se borró fuera de IngeCAD; no se escribió nada")
                if G.row_hash(*before[fid]) != link.hashes.get(fid):
                    raise CommitError(f"FID {fid} cambió fuera de IngeCAD; no se escribió nada")
            backup = _backup(path, f"{path.stem}_{layer.table}")

            t, pk, gc = G.q(layer.table), G.q(layer.pk), G.q(layer.geom_col)
            for fid, (blob, vals) in plan.changes.items():
                if fid in plan.deleted:
                    conn.execute(f"DELETE FROM {t} WHERE {pk} = ?", (fid,))
                    continue
                sets, args = [], []
                if blob is not None:
                    sets.append(f"{gc} = ?")
                    args.append(blob)
                for n, v in (vals or {}).items():
                    sets.append(f"{G.q(n)} = ?")
                    args.append(v)
                conn.execute(f"UPDATE {t} SET {', '.join(sets)} WHERE {pk} = ?", args + [fid])
            new_fids = []
            for blob, vals, _e in plan.new:
                cols = [layer.geom_col] + list(vals)
                marks = ", ".join("?" * len(cols))
                cur = conn.execute(f"INSERT INTO {t} ({', '.join(G.q(c) for c in cols)}) "
                                   f"VALUES ({marks})", [blob] + list(vals.values()))
                new_fids.append(cur.lastrowid)

            # verificar fila por fila
            after = G.read_rows(conn, layer)
            expected_keys = (set(before) - plan.deleted) | set(new_fids)
            if set(after) != expected_keys:
                raise CommitError("validación: el conjunto de registros no es el esperado")
            for fid, row in before.items():
                if fid in plan.changes:
                    continue
                if after[fid] != row:
                    raise CommitError(f"validación: el registro {fid} no debía cambiar")
            for fid, (blob, vals) in plan.changes.items():
                if fid in plan.deleted:
                    continue
                got_blob, got_vals = after[fid]
                want_blob = blob if blob is not None else before[fid][0]
                if bytes(got_blob) != bytes(want_blob):
                    raise CommitError(f"validación: la geometría de {fid} no quedó bien")
                for n, v in (vals or {}).items():
                    if got_vals[names.index(n)] != v:
                        raise CommitError(f"validación: el atributo {n} de {fid} no quedó bien")
            for fid, (blob, _v, _e) in zip(new_fids, plan.new):
                if bytes(after[fid][0]) != blob:
                    raise CommitError("validación: un registro nuevo no quedó bien")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise CommitError("validación: claves foráneas rotas")
            _check_rtree(conn, layer, [f for f in plan.changes if f not in plan.deleted] + new_fids)
            _touch_contents(conn, layer, after)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    except sqlite3.Error as exc:
        raise CommitError(f"SQLite: {exc}; no se escribió nada") from exc
    finally:
        conn.close()

    entry = {
        "fecha": _dt.datetime.now().isoformat(timespec="seconds"),
        "archivo": str(path), "capa": link.table, "dibujo": drawing,
        "respaldo": backup.name,
        "geometria": sorted(plan.geom_changed - plan.deleted),
        "atributos": {str(f): link.pending.get(f, {}) for f in sorted(plan.attr_changed)},
        "borrados": sorted(plan.deleted), "nuevos": new_fids,
        "nuevos_con_formulario": len(plan.form_ids),
    }
    prune_backups(backup.parent, f"{path.stem}_{link.table}", backup)
    with open(backup.parent / "registro.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return CommitResult(backup, len(plan.changes) + len(plan.new), new_fids)


def _check_rtree(conn, layer, fids) -> None:
    rtree = f"rtree_{layer.table}_{layer.geom_col}"
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (rtree,)).fetchone()
    if not exists or not fids:
        return
    rows = G.read_rows(conn, layer, fids)
    for fid in fids:
        want = G.blob_bounds(rows[fid][0]) if rows[fid][0] is not None else None
        got = conn.execute(f"SELECT minx, maxx, miny, maxy FROM {G.q(rtree)} WHERE id = ?",
                           (fid,)).fetchone()
        if want is None:
            continue
        # el R-tree guarda float32 redondeado hacia afuera
        if got is None or not (got[0] <= want[0] + 1e-6 * max(1, abs(want[0]))
                               and got[1] >= want[1] - 1e-6 * max(1, abs(want[1]))):
            raise CommitError("validación: el índice espacial no se actualizó")


def _touch_contents(conn, layer, rows) -> None:
    """Fecha de modificación y extensión de la capa en gpkg_contents."""
    xs0, xs1, ys0, ys1 = [], [], [], []
    for blob, _v in rows.values():
        if blob is None:
            continue
        b = G.blob_bounds(blob)
        if b:
            xs0.append(b[0]); xs1.append(b[1]); ys0.append(b[2]); ys1.append(b[3])
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    if xs0:
        conn.execute("UPDATE gpkg_contents SET last_change = ?, min_x = ?, min_y = ?, "
                     "max_x = ?, max_y = ? WHERE lower(table_name) = lower(?)",
                     (now, min(xs0), min(ys0), max(xs1), max(ys1), layer.table))
    else:
        conn.execute("UPDATE gpkg_contents SET last_change = ? WHERE lower(table_name) = lower(?)",
                     (now, layer.table))


def refresh_after_commit(document, plan: Plan, result: CommitResult) -> None:
    link = plan.link
    conn, layer = open_for_link(link)
    try:
        rows = G.read_rows(conn, layer, list(plan.changes) + list(result.new_fids))
    finally:
        conn.close()
    for fid in plan.changes:
        link.pending.pop(fid, None)
        if fid in plan.deleted:
            link.hashes.pop(fid, None)
        else:
            link.hashes[fid] = G.row_hash(*rows[fid])
    for e, fid, part in plan.retag:
        set_feat_tag(e, link.key, fid, part)
    for fid, (_b, _v, e) in zip(result.new_fids, plan.new):
        link.hashes[fid] = G.row_hash(*rows[fid])
        set_feat_tag(e, link.key, fid, 0)
    for tmp_id in plan.form_ids:
        link.pending.pop(tmp_id, None)
    link.count = max([link.count] + list(result.new_fids))
    write_link(document.doc, link)
    document.dirty = True
