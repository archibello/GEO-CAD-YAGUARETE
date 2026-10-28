# SPDX-License-Identifier: GPL-3.0-or-later
"""DIAGNOSTICOGEOCAD (GEOCADDIAG): qué tiene este equipo para GeoCAD.

Pensado para el IngeCAD de Windows, que viene empaquetado y puede no traer
algún módulo de Python que GeoCAD usa. No toca el dibujo ni los datos:
sólo mira e informa en la línea de comandos.
"""
from __future__ import annotations

import importlib
import os
import platform
import sys
from pathlib import Path

#: módulos de Python que GeoCAD usa (los de la biblioteca estándar pueden faltar
#: en un IngeCAD empaquetado; sqlite3 lo resuelve sqlite_win.py)
MODULOS_PYTHON = ("sqlite3", "socket", "getpass", "uuid", "fnmatch", "ast", "codecs",
                  "struct", "tempfile", "zipfile", "hashlib", "shutil", "json",
                  "numpy", "ezdxf")


def _faltan() -> list[str]:
    out = []
    for name in MODULOS_PYTHON:
        try:
            importlib.import_module(name)
        except Exception as exc:
            out.append(f"{name} ({exc.__class__.__name__})")
    return out


def informe(host=None) -> list[str]:
    from . import VERSION, buzon, config, modulos, sqlite_win

    congelado = bool(getattr(sys, "frozen", False))
    lineas = [
        f"GeoCAD Yaguareté {VERSION} — diagnóstico",
        f"  Sistema: {platform.system()} {platform.release()} ({platform.machine()})",
        f"  Python: {sys.version.split()[0]}"
        + (" (IngeCAD empaquetado)" if congelado else ""),
        f"  Plugin: {Path(__file__).parent}",
    ]
    sq = sqlite_win.estado()
    if sq.get("ok"):
        lineas.append(f"  GeoPackage (sqlite3): sí, de {sq.get('origen')}")
    else:
        lineas.append(f"  GeoPackage (sqlite3): NO — {sq.get('error') or 'no disponible'}. "
                      "Use Shapefile o avise a quien mantiene GeoCAD.")
    faltan = [m for m in _faltan() if not m.startswith("sqlite3")]
    lineas.append("  Módulos de Python: " + ("todos" if not faltan
                                             else "FALTAN " + ", ".join(faltan)))
    base = buzon.base_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
        prueba = base / ".diagnostico"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        escribe = "sí"
    except OSError as exc:
        escribe = f"NO ({exc})"
    lineas.append(f"  Carpeta común con QGIS: {base} (se puede escribir: {escribe})")
    lineas.append(f"  Configuración: {config.config_path()}")
    lineas.append("  QGIS: " + ("abierto, GeoCAD " + (buzon.version_of("qgis") or "?")
                                if buzon.is_alive("qgis") else "cerrado"))
    lineas.append(f"  Módulos activos: {modulos.resumen('ingecad')}")
    mgr = getattr(host, "plugins", None)
    if mgr is not None:
        try:
            lineas.append(f"  Plugin activo en IngeCAD: {'sí' if mgr.is_active('geocad') else 'no'}")
        except Exception:
            pass
    if os.name == "nt":
        lineas.append(f"  APPDATA: {os.environ.get('APPDATA', '?')}")
    return lineas
