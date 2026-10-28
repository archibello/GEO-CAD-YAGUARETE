# SPDX-License-Identifier: GPL-3.0-or-later
"""Cómo abrir IngeCAD desde QGIS, en Linux (Flatpak o común) y en Windows.

Windows: el instalador de IngeCAD (Inno Setup) lo deja en
``C:\\Program Files\\IngeCAD\\ingecad.exe`` (o, instalado sólo para el
usuario, en ``%LOCALAPPDATA%\\Programs\\IngeCAD``) y anota la carpeta en el
Registro (clave de desinstalación con su AppId fijo). Si está en otro
lado, la ruta se elige en la Configuración común («IngeCAD en Windows»).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path, PureWindowsPath

INGECAD_FLATPAK = "org.ingecad.IngeCAD"
#: AppId de IngeCAD en Inno Setup (packaging/windows/ingecad.iss): no cambia entre versiones
INGECAD_APPID = "{7CB5D165-180B-4865-8D0B-832281FBCE36}_is1"
EXE = "ingecad.exe"


def _registro_windows() -> list[Path]:
    """Las carpetas de IngeCAD que anotó su instalador en el Registro."""
    try:
        import winreg
    except ImportError:
        return []
    out = []
    clave = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + INGECAD_APPID
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for vista in (0, getattr(winreg, "KEY_WOW64_64KEY", 0)):
            try:
                with winreg.OpenKey(raiz, clave, 0, winreg.KEY_READ | vista) as k:
                    valor, _ = winreg.QueryValueEx(k, "InstallLocation")
            except OSError:
                continue
            if valor:
                out.append(Path(valor))
    return out


def exes_windows(env=None, registro=None, existe=None) -> list[PureWindowsPath]:
    """ingecad.exe posibles, en orden y sin repetir (los que existen).

    Rutas de Windows aunque se simule en Linux (las pruebas): PureWindowsPath.
    """
    env = os.environ if env is None else env
    existe = existe or (lambda p: Path(p).is_file())
    carpetas = [PureWindowsPath(c) for c in (_registro_windows() if registro is None else registro)]
    for var in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        if env.get(var):
            carpetas.append(PureWindowsPath(env[var]) / "IngeCAD")
    if env.get("LOCALAPPDATA"):
        carpetas.append(PureWindowsPath(env["LOCALAPPDATA"]) / "Programs" / "IngeCAD")
    out = []
    for c in carpetas:
        exe = c / EXE
        if exe not in out and existe(str(exe)):
            out.append(exe)
    return out


def comandos(es_windows=None, ruta_elegida: str = "", env=None, registro=None,
             existe=None, flatpak_info=None, which=None) -> list[list[str]]:
    """Las formas de abrir IngeCAD en este equipo, de la mejor a la peor."""
    es_windows = (os.name == "nt") if es_windows is None else es_windows
    which = which or shutil.which
    existe = existe or (lambda p: Path(p).is_file())
    out = []
    if ruta_elegida and existe(ruta_elegida):
        out.append([str(ruta_elegida)])
    if es_windows:
        out += [[str(p)] for p in exes_windows(env, registro, existe) if [str(p)] not in out]
        if which("ingecad"):
            out.append(["ingecad"])
        return out
    if os.path.exists("/.flatpak-info") if flatpak_info is None else flatpak_info:
        out.append(["flatpak-spawn", "--host", "flatpak", "run", INGECAD_FLATPAK])
    if which("flatpak"):
        out.append(["flatpak", "run", INGECAD_FLATPAK])
    if which("ingecad"):
        out.append(["ingecad"])
    return out


def popen_kwargs(es_windows=None) -> dict:
    """Que IngeCAD quede abierto aunque se cierre QGIS, sin ventana de consola."""
    import subprocess

    es_windows = (os.name == "nt") if es_windows is None else es_windows
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
          "stdin": subprocess.DEVNULL}
    if es_windows:
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
        kw["close_fds"] = True
    else:
        kw["start_new_session"] = True
    return kw


def ayuda_si_falla(es_windows=None) -> str:
    es_windows = (os.name == "nt") if es_windows is None else es_windows
    if es_windows:
        return ("No pude abrir IngeCAD desde QGIS. Ábralo a mano: el pedido lo está "
                "esperando y se carga solo.\n\nSi IngeCAD no está en C:\\Program Files\\"
                "IngeCAD, elija dónde está ingecad.exe en GeoCAD Yaguareté > Configuración "
                "común («IngeCAD en Windows»).")
    return ("No pude abrir IngeCAD desde QGIS. Ábralo a mano: el pedido lo está "
            "esperando y se carga solo.\n\nPara que QGIS (Flatpak) pueda abrirlo, "
            "ejecute una vez en una terminal:\n\n"
            "flatpak override --user --talk-name=org.freedesktop.Flatpak org.qgis.qgis")
