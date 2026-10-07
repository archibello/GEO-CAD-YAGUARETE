# SPDX-License-Identifier: GPL-3.0-or-later
"""Devolver los cambios al shapefile (check-in) sin poner en riesgo el original.

Dos etapas separadas a propósito:

1. :func:`make_plan` sólo LEE: compara el dibujo con el archivo y arma la
   lista de cambios, conflictos y errores. No escribe nada; SHPSTATUS la
   muestra tal cual.
2. :func:`commit` escribe, y sólo si el plan no tiene errores ni
   conflictos: archivos temporales -> validación -> respaldo .zip
   verificado -> reemplazo -> registro. Si algo falla en el reemplazo,
   restaura el respaldo.

Reglas:
* Un registro que no se editó se escribe byte por byte igual.
* Si un registro cambió en el disco (QGIS) Y en el dibujo, es conflicto:
  no se escribe nada y se informa.
* Borrar una entidad no renumera: el registro queda marcado como borrado
  (geometría nula + marca ``*`` en la .dbf), así los FID de QGIS no se
  mueven. QGIS lo oculta; "Empaquetar" en QGIS lo elimina del todo.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import shpio
from .enlace import Link, read_links, set_feat_tag, write_link, linked_entities

BACKUP_DIR = "_respaldos_ingecad"      # valor por defecto; manda la configuración común


def backup_dir(folder: Path) -> Path:
    from . import config

    try:
        name = config.get("carpeta_respaldos")
    except Exception:
        name = BACKUP_DIR
    return Path(folder) / (name or BACKUP_DIR)


def prune_backups(bdir: Path, stem: str, keep_new: Path) -> list:
    """Si la configuración común limita la cantidad de respaldos, borra los
    más viejos de ESA capa (nunca el que se acaba de hacer)."""
    from . import config

    try:
        limit = int(config.get("respaldos_a_conservar"))
    except Exception:
        return []
    if limit <= 0:
        return []
    pattern = re.compile(re.escape(stem) + r"_\d{4}-\d{2}-\d{2}_\d{6}(_\d+)?\.zip$")
    mine = sorted((p for p in bdir.iterdir() if pattern.match(p.name)),
                  key=lambda p: p.stat().st_mtime)
    removed = []
    for p in mine[:-limit] if len(mine) > limit else []:
        if p != keep_new:
            p.unlink()
            removed.append(p.name)
    return removed


def arc_step() -> float:
    """Ángulo máximo por tramo al convertir arcos (configuración común)."""
    from . import config

    try:
        return math.radians(float(config.get("tolerancia_arcos")))
    except Exception:
        return math.radians(5.0)


class GeometryError(Exception):
    pass


def scope_filter(tagged, untagged, scope):
    """Con ``scope`` (handles de las entidades elegidas) el guardado se limita
    a esos objetos: todos los registros que tocan, con TODAS sus partes, y
    los nuevos elegidos. Sin ``scope``, todo."""
    if scope is None:
        return tagged, untagged, None
    scope = set(scope)
    fids = {t.fid for t, e in tagged if e.dxf.handle in scope and t.fid >= 0}
    tagged = [(t, e) for t, e in tagged
              if (t.fid >= 0 and t.fid in fids) or (t.fid < 0 and e.dxf.handle in scope)]
    untagged = [e for e in untagged if e.dxf.handle in scope]
    return tagged, untagged, fids


# -- de entidad CAD a coordenadas ----------------------------------------------------

def _arc_points(p1, p2, bulge, step=None):
    """Puntos intermedios del arco de p1 a p2 (sin incluir los extremos)."""
    theta = 4.0 * math.atan(bulge)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    d = math.hypot(dx, dy)
    if d == 0 or theta == 0:
        return []
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    off = (d / 2) / math.tan(theta / 2)
    cx, cy = mx - dy / d * off, my + dx / d * off
    r = math.hypot(p1[0] - cx, p1[1] - cy)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    n = max(2, math.ceil(abs(theta) / (step or math.radians(5.0))))
    return [(cx + r * math.cos(a1 + theta * k / n), cy + r * math.sin(a1 + theta * k / n))
            for k in range(1, n)]


def entity_vertices(e):
    """(vértices xy, cerrada, z, tenía arcos) de una entidad dibujable."""
    t = e.dxftype()
    if t == "POINT":
        loc = e.dxf.location
        return [(float(loc.x), float(loc.y))], False, float(loc.z), False
    if t == "INSERT":                    # símbolo de QGIS (3.1.0): vale su punto de inserción
        loc = e.dxf.insert
        return [(float(loc.x), float(loc.y))], False, float(loc.z), False
    if t == "LINE":
        s, f = e.dxf.start, e.dxf.end
        return [(float(s.x), float(s.y)), (float(f.x), float(f.y))], False, float(s.z), False
    if t == "LWPOLYLINE":
        raw = [(float(x), float(y), float(b)) for x, y, b in e.get_points("xyb")]
        closed = bool(e.closed)
        had_arcs = any(b != 0 for _x, _y, b in raw)
        pts = []
        n = len(raw)
        step = arc_step() if had_arcs else None
        for i, (x, y, b) in enumerate(raw):
            pts.append((x, y))
            if b != 0 and (i + 1 < n or closed):
                nx, ny, _ = raw[(i + 1) % n]
                pts.extend(_arc_points((x, y), (nx, ny), b, step))
        return pts, closed, float(e.dxf.get("elevation", 0.0) or 0.0), had_arcs
    if t == "POLYLINE" and not (e.is_polygon_mesh or e.is_poly_face_mesh):
        pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in e.vertices]
        return pts, bool(e.is_closed), 0.0, False
    raise GeometryError(f"{t} no se puede guardar en un shapefile")


def _close(ring):
    return ring + [ring[0]] if ring[0] != ring[-1] else ring


def _segments_intersect(a, b, c, d) -> bool:
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 0) - (v < 0)

    def on_seg(p, q, r):
        return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
                and min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and on_seg(a, c, b)) or (o2 == 0 and on_seg(a, d, b))
            or (o3 == 0 and on_seg(c, a, d)) or (o4 == 0 and on_seg(c, b, d)))


def check_ring(ring) -> None:
    """Anillo cerrado, con 3 vértices distintos, área y sin autocruces."""
    distinct = list(dict.fromkeys(ring))
    if len(distinct) < 3:
        raise GeometryError("el polígono tiene menos de 3 vértices distintos")
    if abs(shpio.signed_area(ring[:-1])) == 0:
        raise GeometryError("el polígono no tiene área")
    segs = list(zip(ring, ring[1:]))
    n = len(segs)
    if n > 4000:
        return                       # demasiado grande para el chequeo O(n²)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue             # primer y último tramo comparten el cierre
            if _segments_intersect(*segs[i], *segs[j]):
                raise GeometryError("el polígono se cruza a sí mismo")


def part_from_entity(e, kind: str):
    """Coordenadas de una parte lista para el shapefile. Devuelve
    (puntos, z de la entidad, tenía arcos)."""
    pts, closed, z, had_arcs = entity_vertices(e)
    if kind == "point":
        if e.dxftype() not in ("POINT", "INSERT"):
            raise GeometryError(f"en una capa de puntos sólo van POINT o símbolos, no {e.dxftype()}")
        return pts, z, False
    if e.dxftype() in ("POINT", "INSERT"):
        raise GeometryError(f"un {e.dxftype()} no puede ir en una capa de líneas o polígonos")
    if kind == "line":
        if closed:
            pts = _close(pts)
        if len(pts) < 2:
            raise GeometryError("la línea tiene menos de 2 vértices")
        return pts, z, had_arcs
    # polígono
    if not closed and pts[0] != pts[-1]:
        raise GeometryError("la polilínea no está cerrada")
    ring = _close(pts)
    check_ring(ring)
    return ring, z, had_arcs


def orient_ring(ring, clockwise: bool):
    area = shpio.signed_area(ring[:-1])
    if (area < 0) != clockwise:
        return list(reversed(ring))
    return ring


def carry_values(orig_pts, orig_vals, new_pts):
    """Z (o M) para los vértices nuevos: el mismo valor donde el vértice
    no se movió, interpolado a lo largo de la línea donde es nuevo."""
    lookup = {}
    for p, v in zip(orig_pts, orig_vals):
        lookup.setdefault(p, v)
    vals = [lookup.get(p) for p in new_pts]
    known = [i for i, v in enumerate(vals) if v is not None]
    if not known:
        def nearest(p):
            i = min(range(len(orig_pts)),
                    key=lambda k: (orig_pts[k][0] - p[0]) ** 2 + (orig_pts[k][1] - p[1]) ** 2)
            return orig_vals[i]
        return [nearest(p) for p in new_pts]
    cum = [0.0]
    for a, b in zip(new_pts, new_pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    out = list(vals)
    for i, v in enumerate(vals):
        if v is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is None:
            out[i] = vals[nxt]
        elif nxt is None:
            out[i] = vals[prev]
        else:
            a, b = vals[prev], vals[nxt]
            if a <= shpio.M_NODATA or b <= shpio.M_NODATA:
                out[i] = -1e39
            else:
                span = cum[nxt] - cum[prev]
                t = (cum[i] - cum[prev]) / span if span else 0.0
                out[i] = a + (b - a) * t
    return out


# -- el plan ----------------------------------------------------------------------------

@dataclass
class Plan:
    link: Link
    sf: shpio.Shapefile = None
    file_hashes: dict = field(default_factory=dict)
    changes: dict = field(default_factory=dict)       # fid -> (contenido, fila dbf)
    geom_changed: set = field(default_factory=set)
    attr_changed: set = field(default_factory=set)
    deleted: set = field(default_factory=set)
    new: list = field(default_factory=list)           # (contenido, fila, entidad)
    retag: list = field(default_factory=list)         # (entidad, fid, parte)
    form_ids: set = field(default_factory=set)        # nuevos con formulario (fid < 0)
    conflicts: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.conflicts

    @property
    def empty(self) -> bool:
        return not self.changes and not self.new

    def summary(self) -> list[str]:
        name = self.link.name
        lines = []
        if self.errors:
            lines.append(f"{name}: {len(self.errors)} error(es), no se puede guardar")
            lines += ["  - " + e for e in self.errors[:20]]
        if self.conflicts:
            lines.append(f"{name}: {len(self.conflicts)} conflicto(s) con cambios hechos fuera de IngeCAD")
            lines += ["  - " + c for c in self.conflicts[:20]]
        modified = len(set(self.changes) - self.deleted)
        lines.append(f"{name}: {modified} modificado(s) "
                     f"[{len(self.geom_changed - self.deleted)} geometría, {len(self.attr_changed)} atributos], "
                     f"{len(self.new)} nuevo(s), {len(self.deleted)} borrado(s)")
        lines += ["  aviso: " + w for w in self.warnings[:20]]
        return lines


def _with_m(sf) -> bool:
    return sf.has_m


def _build_geometry(sf, kind, parts_pts, zs, orig: shpio.Geometry | None, link_z_from_entity):
    """Geometry con Z/M para un tipo con Z o M."""
    st = sf.shape_type
    geom = shpio.Geometry(st, [list(p) for p in parts_pts])
    has_z = st in shpio.Z_TYPES
    has_m = sf.has_m
    if kind == "point":
        if has_z:
            geom.z = [[zs[0]]]
        if has_m:
            geom.m = [[orig.m[0][0]]] if (orig and orig.m and orig.parts[0] == parts_pts[0]) else [[-1e39]]
        return geom
    if has_z or has_m:
        flat_pts = [p for part in orig.parts for p in part] if orig and not orig.is_null else []
        zz, mm = [], []
        for i, part in enumerate(parts_pts):
            if has_z:
                if flat_pts and orig.z:
                    zz.append(carry_values(flat_pts, [v for q in orig.z for v in q], part))
                else:
                    zz.append([link_z_from_entity[i]] * len(part))
            if has_m:
                if flat_pts and orig.m:
                    mm.append(carry_values(flat_pts, [v for q in orig.m for v in q], part))
                else:
                    mm.append([-1e39] * len(part))
        geom.z = zz if has_z else None
        geom.m = mm if has_m else None
    return geom


def make_plan(document, key: str, scope=None) -> Plan:
    links = read_links(document.doc)
    if key not in links:
        raise KeyError(key)
    link = links[key]
    if link.fmt == "gpkg":
        from . import gpkg_checkin

        return gpkg_checkin.make_plan(document, key, scope)
    plan = Plan(link)
    kind = link.kind
    try:
        sf = shpio.Shapefile(link.path)
    except (OSError, shpio.ShapefileError) as exc:
        plan.errors.append(f"no se puede leer {link.path}: {exc}")
        return plan
    plan.sf = sf
    plan.file_hashes = {ext: shpio.file_hash(sf.paths[ext]) for ext in ("shp", "shx", "dbf")}
    if sf.shape_type != link.shape_type:
        plan.errors.append("el tipo de geometría del archivo cambió desde que se conectó")
    if sf.schema_hash != link.schema:
        plan.errors.append("la estructura de la tabla (campos) cambió en el disco; "
                           "desconectá y volvé a conectar")
    if len(sf) < link.count:
        plan.errors.append(f"el archivo tiene {len(sf)} registros y al conectar tenía "
                           f"{link.count} (¿se empaquetó en QGIS?)")
    if kind == "other":
        plan.errors.append(f"el tipo {shpio.SHAPE_NAMES.get(sf.shape_type)} no se puede editar")
    if plan.errors:
        return plan

    tagged, untagged = linked_entities(document, key)
    tagged, untagged, scope_fids = scope_filter(tagged, untagged, scope)
    by_fid: dict[int, dict[int, list]] = {}
    form_new = []    # (id provisorio, entidad): objetos nuevos cargados con formulario
    for tag, e in tagged:
        if tag.fid < 0:
            form_new.append((tag.fid, e))
            continue
        by_fid.setdefault(tag.fid, {}).setdefault(tag.part, []).append(e)

    copies = []      # (fid origen, parte, entidad)
    fids = {f for f in set(link.hashes) | set(by_fid) | set(link.pending) if f >= 0}
    if scope_fids is not None:
        fids &= scope_fids
    for fid in sorted(fids):
        if fid not in link.hashes and not by_fid.get(fid):
            if fid in link.pending:
                plan.errors.append(f"FID {fid}: tiene atributos pendientes pero no está "
                                   "conectado; conéctelo para poder guardarlos")
            continue
        if fid >= len(sf):
            plan.errors.append(f"FID {fid} no existe en el archivo")
            continue
        orig = sf.geometry(fid)
        orig_rec = sf.dbf_records[fid]
        disk_changed = fid in link.hashes and sf.hash(fid) != link.hashes[fid]
        parts = by_fid.get(fid, {})

        # duplicados (COPY copia también la etiqueta): el que coincide con el
        # original se queda; los demás pasan a ser registros nuevos.
        chosen: dict[int, object] = {}
        for part_no in sorted(parts):
            ents = sorted(parts[part_no], key=lambda x: int(x.dxf.handle, 16))
            keep = ents[0]
            if part_no < len(orig.parts):
                for e in ents:
                    try:
                        pts, _z, _a = part_from_entity(e, kind)
                    except GeometryError:
                        continue
                    if pts == orig.parts[part_no]:
                        keep = e
                        break
            chosen[part_no] = keep
            copies += [(fid, part_no, e) for e in ents if e is not keep]

        # geometría actual en el dibujo
        new_parts, new_z, ents_order, had_arcs, bad = [], [], [], False, False
        for part_no in sorted(chosen):
            e = chosen[part_no]
            try:
                pts, z, arcs = part_from_entity(e, kind)
            except GeometryError as exc:
                plan.errors.append(f"FID {fid}, parte {part_no}: {exc}")
                bad = True
                continue
            if kind == "polygon" and part_no < len(orig.parts) and not orig.is_null:
                clockwise = shpio.signed_area(orig.parts[part_no][:-1]) < 0
                pts = orient_ring(pts, clockwise)
            new_parts.append(pts)
            new_z.append(z)
            ents_order.append(e)
            had_arcs = had_arcs or arcs
        if bad:
            continue

        drawn = fid in link.hashes
        if not drawn and not parts:
            geom_changed = False         # nunca se dibujó (nulo o borrado)
        elif kind == "point":
            same_xy = bool(new_parts) and not orig.is_null and new_parts[0] == orig.parts[0]
            same_z = (not orig.z) or (new_z and orig.z[0][0] == new_z[0])
            geom_changed = not (same_xy and same_z) or len(new_parts) != len(orig.parts)
        else:
            geom_changed = orig.is_null or new_parts != orig.parts

        pending = link.pending.get(fid, {})
        new_rec = orig_rec
        if pending:
            try:
                new_rec = sf.patch_record(orig_rec, pending)
            except (shpio.ShapefileError, KeyError) as exc:
                plan.errors.append(f"FID {fid}: {exc}")
                continue
        attr_changed = new_rec != orig_rec

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

        if not new_parts:                       # se borraron todas sus partes
            plan.deleted.add(fid)
            plan.changes[fid] = (shpio.encode_geometry(shpio.Geometry(shpio.NULL)),
                                 b"*" + orig_rec[1:])
            plan.geom_changed.add(fid)
            continue
        if kind == "point" and len(new_parts) > 1:
            plan.errors.append(f"FID {fid}: un registro de punto no puede tener varias partes")
            continue
        content = orig_rec_content = sf.contents[fid]
        if geom_changed:
            geom = _build_geometry(sf, kind, new_parts, new_z, orig, new_z)
            content = shpio.encode_geometry(geom, sf.has_m)
            plan.geom_changed.add(fid)
            if had_arcs:
                plan.warnings.append(f"FID {fid}: los arcos se guardaron como tramos rectos")
        if attr_changed:
            plan.attr_changed.add(fid)
        plan.changes[fid] = (content, new_rec)
        del orig_rec_content
        for new_part_no, e in enumerate(ents_order):
            plan.retag.append((e, fid, new_part_no))

    # copias -> registros nuevos con los atributos del original
    for fid, part_no, e in copies:
        try:
            pts, z, arcs = part_from_entity(e, kind)
        except GeometryError as exc:
            plan.errors.append(f"copia de FID {fid}: {exc}")
            continue
        if kind == "polygon":
            pts = orient_ring(pts, clockwise=True)
        orig = sf.geometry(fid)
        geom = _build_geometry(sf, kind, [pts], [z], orig, [z])
        rec = sf.dbf_records[fid]
        if fid in link.pending:
            try:
                rec = sf.patch_record(rec, link.pending[fid])
            except (shpio.ShapefileError, KeyError) as exc:
                plan.errors.append(f"copia de FID {fid}: {exc}")
                continue
        plan.new.append((shpio.encode_geometry(geom, sf.has_m), b" " + rec[1:], e))
        if arcs:
            plan.warnings.append(f"copia de FID {fid}: arcos guardados como tramos rectos")

    # nuevos con formulario -> registros nuevos con sus atributos
    for tmp_id, e in form_new:
        try:
            pts, z, arcs = part_from_entity(e, kind)
        except GeometryError as exc:
            plan.errors.append(f"objeto nuevo {e.dxf.handle}: {exc}")
            continue
        if kind == "polygon":
            pts = orient_ring(pts, clockwise=True)
        try:
            rec = sf.patch_record(sf.blank_record(), link.pending.get(tmp_id, {}))
        except (shpio.ShapefileError, KeyError) as exc:
            plan.errors.append(f"objeto nuevo {e.dxf.handle}: {exc}")
            continue
        geom = _build_geometry(sf, kind, [pts], [z], None, [z])
        plan.new.append((shpio.encode_geometry(geom, sf.has_m), rec, e))
        plan.form_ids.add(tmp_id)
        if arcs:
            plan.warnings.append(f"objeto nuevo {e.dxf.handle}: arcos guardados como tramos rectos")

    # entidades dibujadas sobre la capa sin etiqueta -> registros nuevos vacíos
    for e in untagged:
        try:
            pts, z, arcs = part_from_entity(e, kind)
        except GeometryError as exc:
            plan.warnings.append(f"{e.dxftype()} {e.dxf.handle} en la capa se ignora: {exc}")
            continue
        if kind == "polygon":
            pts = orient_ring(pts, clockwise=True)
        geom = _build_geometry(sf, kind, [pts], [z], None, [z])
        plan.new.append((shpio.encode_geometry(geom, sf.has_m), sf.blank_record(), e))
        if arcs:
            plan.warnings.append(f"entidad nueva {e.dxf.handle}: arcos guardados como tramos rectos")
    if untagged and any(rec == sf.blank_record() for _c, rec, e in plan.new if e in untagged):
        plan.warnings.append("los registros nuevos dibujados a mano quedan con atributos vacíos")
    return plan


# -- escribir ----------------------------------------------------------------------------

class CommitError(Exception):
    pass


@dataclass
class CommitResult:
    backup: Path
    written: int
    new_fids: list


def _fsync_write(path: Path, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


def commit(plan: Plan, drawing: str = "") -> CommitResult:
    if plan.link.fmt == "gpkg":
        from . import gpkg_checkin

        return gpkg_checkin.commit(plan, drawing)
    if not plan.ok:
        raise CommitError("el plan tiene errores o conflictos")
    if plan.empty:
        raise CommitError("no hay cambios para guardar")
    sf = plan.sf
    paths = sf.paths
    # 0. ¿alguien escribió el archivo después de armar el plan?
    for ext, h in plan.file_hashes.items():
        if shpio.file_hash(paths[ext]) != h:
            raise CommitError(f"el .{ext} cambió en el disco mientras se preparaba "
                              "el guardado; no se escribió nada")
    # 1. filas finales
    rows = list(zip(sf.contents, sf.dbf_records))
    for fid, row in plan.changes.items():
        rows[fid] = row
    first_new = len(rows)
    rows += [(c, r) for c, r, _e in plan.new]
    shp, shx, dbf = shpio.build_files(sf, rows)

    # 2. temporales en la misma carpeta (mismo disco: el reemplazo es atómico)
    folder = paths["shp"].parent
    stem = paths["shp"].stem
    tmp = {ext: folder / f".{stem}.ingecad-tmp.{ext}" for ext in ("shp", "shx", "dbf")}
    try:
        _fsync_write(tmp["shp"], shp)
        _fsync_write(tmp["shx"], shx)
        _fsync_write(tmp["dbf"], dbf)

        # 3. validar leyendo de nuevo lo escrito
        check = shpio.Shapefile(tmp["shp"])
        if len(check) != len(rows):
            raise CommitError("validación: cantidad de registros incorrecta")
        if check.dbf_header[32:] != sf.dbf_header[32:]:
            raise CommitError("validación: la estructura de la tabla cambió")
        if check.shape_type != sf.shape_type:
            raise CommitError("validación: el tipo de geometría cambió")
        for i, (c, r) in enumerate(rows):
            if check.contents[i] != c or check.dbf_records[i] != r:
                raise CommitError(f"validación: el registro {i} no quedó como se esperaba")
            if i < first_new and i not in plan.changes:
                if c != sf.contents[i] or r != sf.dbf_records[i]:
                    raise CommitError(f"validación: el registro {i} no debía cambiar")
            shpio.parse_geometry(c)

        # 4. respaldo .zip de TODO el conjunto, verificado
        bdir = backup_dir(folder)
        bdir.mkdir(exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup = bdir / f"{stem}_{stamp}.zip"
        n = 2
        while backup.exists():            # nunca pisar un respaldo anterior
            backup = bdir / f"{stem}_{stamp}_{n}.zip"
            n += 1
        members = [p for p in paths.values() if p.exists()]
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in members:
                zf.write(p, p.name)
        with zipfile.ZipFile(backup) as zf:
            if zf.testzip() is not None:
                raise CommitError("el respaldo .zip quedó dañado; no se escribió nada")
            for p in members:
                if zf.read(p.name) != p.read_bytes():
                    raise CommitError("el respaldo no coincide con el original; no se escribió nada")

        # 5. reemplazo; ante cualquier falla, restaurar desde el respaldo
        try:
            for ext in ("dbf", "shx", "shp"):
                os.replace(tmp[ext], paths[ext])
        except Exception as exc:
            with zipfile.ZipFile(backup) as zf:
                for p in members:
                    p.write_bytes(zf.read(p.name))
            raise CommitError(f"falló el reemplazo ({exc}); se restauró el original") from exc
        # los índices espaciales (.qix .sbn .sbx) quedan viejos: QGIS los rehace
        if plan.geom_changed or plan.new:
            for ext in ("qix", "sbn", "sbx"):
                if paths[ext].exists():
                    paths[ext].unlink()
    finally:
        for p in tmp.values():
            if p.exists():
                p.unlink()

    prune_backups(bdir, stem, backup)
    # 6. registro de cambios
    entry = {
        "fecha": _dt.datetime.now().isoformat(timespec="seconds"),
        "archivo": str(paths["shp"]),
        "dibujo": drawing,
        "respaldo": backup.name,
        "geometria": sorted(plan.geom_changed - plan.deleted),
        "atributos": {str(fid): plan.link.pending.get(fid, {}) for fid in sorted(plan.attr_changed)},
        "borrados": sorted(plan.deleted),
        "nuevos": list(range(first_new, len(rows))),
    }
    with open(bdir / "registro.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return CommitResult(backup, len(plan.changes) + len(plan.new),
                        list(range(first_new, len(rows))))


def refresh_after_commit(document, plan: Plan, result: CommitResult) -> None:
    """El manifiesto y las etiquetas pasan a describir el archivo nuevo.
    (No es un paso de deshacer: el archivo ya cambió en el disco.)"""
    from . import estilo

    if plan.link.fmt == "gpkg":
        from . import gpkg_checkin

        gpkg_checkin.refresh_after_commit(document, plan, result)
    else:
        _refresh_shp(document, plan, result)
    estilo.remember_saved(document, plan.link.key, set(plan.changes) | set(result.new_fids))


def _refresh_shp(document, plan: Plan, result: CommitResult) -> None:
    sf = shpio.Shapefile(plan.link.path)
    link = plan.link
    for fid in plan.changes:
        link.pending.pop(fid, None)
        if fid in plan.deleted:
            link.hashes.pop(fid, None)
        else:
            link.hashes[fid] = sf.hash(fid)
    for e, fid, part in plan.retag:
        set_feat_tag(e, link.key, fid, part)
    for fid, (_c, _r, e) in zip(result.new_fids, plan.new):
        link.hashes[fid] = sf.hash(fid)
        set_feat_tag(e, link.key, fid, 0)
    for tmp_id in plan.form_ids:
        link.pending.pop(tmp_id, None)
    link.count = len(sf)
    write_link(document.doc, link)
    document.dirty = True
