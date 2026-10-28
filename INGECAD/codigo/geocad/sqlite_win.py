# SPDX-License-Identifier: GPL-3.0-or-later
"""sqlite3 en el IngeCAD de Windows.

El IngeCAD de Windows viene empaquetado (PyInstaller) y sólo trae los
módulos de Python que usa él: sqlite3 no está, y sin sqlite3 GeoCAD no
puede leer ni guardar GeoPackage. GeoCAD trae su propia copia para
Python 3.12 de 64 bits (carpeta win/py312) y la usa SÓLO si falta.

En Linux (Flatpak) y con un Python completo no hace nada.

La copia se carga desde %LOCALAPPDATA%\\GeoCAD\\sqlite\\<versión>, no desde la
carpeta del plugin: Windows no deja renombrar una carpeta con un .pyd en
uso, y así GeoCAD se puede actualizar con IngeCAD abierto.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

_estado = {"ok": None, "origen": "", "error": ""}


def carpeta_propia() -> Path:
    return Path(__file__).parent / "win" / f"py{sys.version_info[0]}{sys.version_info[1]}"


def _copia_fuera(propia: Path, env=None) -> Path:
    """La copia de trabajo en %LOCALAPPDATA%\\GeoCAD\\sqlite (una por contenido)."""
    env = os.environ if env is None else env
    h = hashlib.sha256()
    for f in sorted(propia.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(propia).as_posix().encode())
            h.update(f.read_bytes())
    base = Path(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    destino = base / "GeoCAD" / "sqlite" / f"{propia.name}-{h.hexdigest()[:12]}"
    if not (destino / "_sqlite3.pyd").is_file():
        tmp = destino.with_name(destino.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(propia, tmp)
        try:
            tmp.rename(destino)
        except OSError:                      # otra ventana la copió recién
            shutil.rmtree(tmp, ignore_errors=True)
    return destino


def asegurar(es_windows: bool | None = None) -> bool:
    """¿Hay sqlite3? Si falta y estamos en Windows, prueba la copia propia.
    El resultado queda en estado() (para el diagnóstico y para QGIS)."""
    if _estado["ok"] is not None:
        return _estado["ok"]
    try:
        import sqlite3  # noqa: F401
        _estado.update(ok=True, origen="IngeCAD")
        return True
    except ImportError as exc:
        _estado["error"] = str(exc)
    es_windows = (os.name == "nt") if es_windows is None else es_windows
    propia = carpeta_propia()
    if not es_windows or not (propia / "_sqlite3.pyd").is_file():
        _estado["ok"] = False
        if es_windows:
            _estado["error"] = (f"falta sqlite3 y GeoCAD no trae copia para Python "
                                f"{sys.version_info[0]}.{sys.version_info[1]}")
        return False
    sys.modules.pop("sqlite3", None)
    try:
        propia = _copia_fuera(propia)
    except OSError:
        pass                                 # se usa la del plugin
    sys.path.insert(0, str(propia))
    try:
        if hasattr(os, "add_dll_directory"):
            _estado["dll"] = os.add_dll_directory(str(propia))   # sqlite3.dll
        import sqlite3  # noqa: F401,F811
        _estado.update(ok=True, origen="GeoCAD (" + str(propia) + ")", error="")
    except Exception as exc:                 # ImportError, OSError (DLL)
        try:
            sys.path.remove(str(propia))
        except ValueError:
            pass
        _estado.update(ok=False, error=f"la copia de GeoCAD no cargó: {exc}")
    return _estado["ok"]


def estado() -> dict:
    return {k: v for k, v in _estado.items() if k != "dll"}


def disponible() -> bool:
    return bool(asegurar())
