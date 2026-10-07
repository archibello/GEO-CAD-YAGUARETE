# SPDX-License-Identifier: GPL-3.0-or-later
"""Archivo de bloqueo ``<capa>.shp.ingecad.lock`` al lado del shapefile.

Avisa (a otra sesión de IngeCAD, y al complemento de QGIS) que la capa
está tomada para edición. Es un JSON aparte: nunca toca los datos.
"""
from __future__ import annotations

import datetime as _dt
import getpass
import json
import socket
from pathlib import Path


def lock_path(shp_path) -> Path:
    p = Path(shp_path)
    return p.with_name(p.name + ".ingecad.lock")


def owner() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "?"
    return f"{user}@{socket.gethostname()}"


def read(shp_path):
    path = lock_path(shp_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"owner": "?", "since": "?", "drawing": "?"}


def acquire(shp_path, drawing: str) -> tuple[bool, dict | None]:
    """Toma el bloqueo. Devuelve (ok, bloqueo ajeno si lo hay)."""
    current = read(shp_path)
    if current is not None and current.get("owner") != owner():
        return False, current
    data = {"owner": owner(), "drawing": drawing,
            "since": _dt.datetime.now().isoformat(timespec="seconds"),
            "app": "IngeCAD GeoCAD"}
    lock_path(shp_path).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return True, current


def release(shp_path) -> None:
    current = read(shp_path)
    if current is not None and current.get("owner") in (owner(), "?"):
        try:
            lock_path(shp_path).unlink()
        except FileNotFoundError:
            pass
