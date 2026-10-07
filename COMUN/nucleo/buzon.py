# SPDX-License-Identifier: GPL-3.0-or-later
"""Mensajes entre IngeCAD y QGIS por archivos, sin red.

    ~/.config/geocad/buzon/ingecad/   pedidos para IngeCAD
    ~/.config/geocad/buzon/qgis/      avisos para QGIS
    ~/.config/geocad/estado/<programa>.json   "estoy abierto"
    ~/.config/geocad/iconos/<programa>.png    el ícono de cada uno

Por qué archivos: los dos programas son Flatpak y comparten la carpeta
personal, pero no necesariamente la red; además, un pedido hecho con
IngeCAD cerrado queda esperando y se atiende al abrirlo.

Cada mensaje es un JSON escrito en un temporal y renombrado (atómico):
el lector nunca ve un archivo a medio escribir. Python puro: el
complemento de QGIS usa una copia idéntica de este archivo.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path

PROGRAMS = ("ingecad", "qgis")
#: un programa que no actualizó su estado en este tiempo se da por cerrado
ALIVE_SECONDS = 12


def base_dir() -> Path:
    return Path.home() / ".config" / "geocad"


def inbox(program: str) -> Path:
    return base_dir() / "buzon" / program


def icon_path(program: str) -> Path:
    return base_dir() / "iconos" / f"{program}.png"


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def send(to: str, message: dict, sender: str) -> Path:
    """Deja un mensaje en el buzón de ``to``."""
    msg = dict(message)
    msg.setdefault("origen", sender)
    msg.setdefault("fecha", time.time())
    name = f"{time.time():.6f}-{uuid.uuid4().hex[:8]}.json"
    path = inbox(to) / name
    _atomic_write(path, msg)
    return path


def receive(program: str, max_age: float = 24 * 3600) -> list[dict]:
    """Los mensajes pendientes, en orden de llegada; se borran al leerlos.
    Los muy viejos (de otro día) se descartan sin ejecutarlos."""
    box = inbox(program)
    if not box.is_dir():
        return []
    out = []
    for path in sorted(box.glob("*.json")):
        if path.name.startswith(".tmp-"):
            continue
        try:
            msg = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            msg = None
        try:
            path.unlink()
        except OSError:
            continue                    # otro lector se lo llevó
        if isinstance(msg, dict) and time.time() - float(msg.get("fecha", 0)) <= max_age:
            out.append(msg)
    return out


def heartbeat(program: str, extra: dict | None = None) -> None:
    data = {"pid": os.getpid(), "fecha": time.time()}
    if extra:
        data.update(extra)
    _atomic_write(base_dir() / "estado" / f"{program}.json", data)


def clear_heartbeat(program: str) -> None:
    try:
        (base_dir() / "estado" / f"{program}.json").unlink()
    except OSError:
        pass


def version_of(program: str) -> str:
    """La versión de GeoCAD que anunció ``program`` ("" si no la anuncia:
    anterior a 3.1.1, o no está abierto)."""
    try:
        data = json.loads((base_dir() / "estado" / f"{program}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("version") or "")


def is_alive(program: str) -> bool:
    try:
        data = json.loads((base_dir() / "estado" / f"{program}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return time.time() - float(data.get("fecha", 0)) <= ALIVE_SECONDS


def layer_ref(fmt: str, path: str, table: str = "") -> dict:
    return {"formato": fmt, "ruta": str(Path(path).resolve()), "tabla": table or ""}
