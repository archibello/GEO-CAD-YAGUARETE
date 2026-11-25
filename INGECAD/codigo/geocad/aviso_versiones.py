# SPDX-License-Identifier: GPL-3.0-or-later
"""Aviso de versiones nuevas publicadas en GitHub (3.95.0).

Al abrir IngeCAD o QGIS, a lo sumo una vez por día y por programa, se le
pregunta a GitHub cuál es la última versión publicada en Releases. Si es
más nueva que la instalada (y no se pidió «No avisar de esta versión»), se
baja la entrega completa ``GeoCAD_<v>.zip`` a ~/.config/geocad/descargas.
Esa carpeta se usa después igual que la carpeta de actualizaciones: el
mismo ``actualizar.mas_nueva`` encuentra ahí el instalador de cada
programa y su CAMBIOS_<v>.txt.

No se manda ningún dato del usuario: sólo se pide la página pública de la
última versión. Sin internet, o con cualquier error, no pasa nada.

Python puro (sin Qt). ``urllib`` se importa recién al consultar: el
Python de algunas IngeCAD (PyInstaller) no trae todo y GeoCAD tiene que
cargar igual.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import config
from .actualizar import ENTREGA, version_tuple
from .nombre import REPOSITORIO

API = REPOSITORIO.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"
AGENTE = "GeoCAD-Yaguarete"            # GitHub pide un User-Agent; nada del usuario
LIMITE = 50 * 1024 * 1024              # la entrega pesa unos 4 MB
ESPERA = 10                            # segundos, por pedido
SIN_AVISO = "GEOCAD_SIN_AVISO"         # las pruebas lo ponen: nada de red


@dataclass(frozen=True)
class Publicada:
    version: str
    pagina: str          # la página de la versión en GitHub
    entrega: str         # dirección de GeoCAD_<v>.zip ("" si no está)
    tamano: int = 0


def carpeta_descargas() -> Path:
    return config.config_path().parent / "descargas"


def _hoy() -> str:
    return datetime.date.today().isoformat()


def _clave(programa: str) -> str:
    return "aviso_consultado_" + ("qgis" if programa.lower() == "qgis" else "ingecad")


def toca_consultar(programa: str, hoy: Optional[str] = None) -> bool:
    """Prendido, y hoy todavía no se le preguntó a GitHub desde este programa."""
    if os.environ.get(SIN_AVISO) or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False                    # pruebas y bancos sin pantalla: nada de red
    try:
        valores = config.load()
    except Exception:  # noqa: BLE001
        return False
    if not valores.get("avisar_versiones", True):
        return False
    return valores.get(_clave(programa), "") != (hoy or _hoy())


def marcar_consultado(programa: str, hoy: Optional[str] = None) -> None:
    config.save({_clave(programa): hoy or _hoy()}, "QGIS" if programa.lower() == "qgis" else "IngeCAD")


def saltear(version: str, programa: str = "IngeCAD") -> None:
    """«No avisar de esta versión»: vale para los dos programas; una más nueva
    vuelve a avisar."""
    config.save({"aviso_saltear": version}, programa)


def _abrir(url: str, timeout: float):
    import urllib.request

    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE,
                                                  "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(pedido, timeout=timeout)


def leer_publicada(datos: dict) -> Optional[Publicada]:
    """La respuesta de GitHub (releases/latest) convertida, o None si no sirve."""
    if not isinstance(datos, dict) or datos.get("draft") or datos.get("prerelease"):
        return None
    hallado = re.fullmatch(r"v?(\d+\.\d+\.\d+)", str(datos.get("tag_name", "")).strip())
    if not hallado:
        return None
    version = hallado.group(1)
    entrega, tamano = "", 0
    for archivo in datos.get("assets") or ():
        if not isinstance(archivo, dict):
            continue
        m = ENTREGA.match(str(archivo.get("name", "")))
        if m and m.group(1) == version:
            entrega = str(archivo.get("browser_download_url", ""))
            tamano = int(archivo.get("size") or 0)
            break
    if not entrega.startswith("https://"):
        entrega = ""
    pagina = str(datos.get("html_url") or f"{REPOSITORIO}/releases/tag/v{version}")
    return Publicada(version, pagina, entrega, tamano)


def consultar(abrir: Optional[Callable] = None, timeout: float = ESPERA) -> Optional[Publicada]:
    """La última versión publicada, o None (sin internet, GitHub no responde...)."""
    try:
        with (abrir or _abrir)(API, timeout) as respuesta:
            datos = json.loads(respuesta.read(1024 * 1024).decode("utf-8"))
    except Exception:  # noqa: BLE001 -- sin red o sin urllib: no se avisa y listo
        return None
    return leer_publicada(datos)


def para_avisar(publicada: Optional[Publicada], instalada: str) -> bool:
    if publicada is None or not publicada.entrega:
        return False
    if version_tuple(publicada.version) <= version_tuple(instalada):
        return False
    try:
        return config.get("aviso_saltear") != publicada.version
    except Exception:  # noqa: BLE001
        return True


def _entrega_sana(ruta: Path, version: str) -> bool:
    try:
        with zipfile.ZipFile(ruta) as zf:
            nombres = [Path(n).name for n in zf.namelist()]
            return zf.testzip() is None and f"instalar_geocad_{version}.py" in nombres
    except (OSError, zipfile.BadZipFile):
        return False


def descargar(publicada: Publicada, carpeta=None, abrir: Optional[Callable] = None,
              timeout: float = 60) -> Optional[Path]:
    """Baja GeoCAD_<v>.zip a la carpeta de descargas (si ya estaba sana, no la
    vuelve a bajar) y borra las entregas viejas. Devuelve la carpeta, o None."""
    carpeta = Path(carpeta or carpeta_descargas())
    destino = carpeta / f"GeoCAD_{publicada.version}.zip"
    if destino.is_file() and _entrega_sana(destino, publicada.version):
        return carpeta
    if not publicada.entrega or publicada.tamano > LIMITE:
        return None
    parcial = carpeta / f".GeoCAD_{publicada.version}.zip.parcial"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        leido = 0
        with (abrir or _abrir)(publicada.entrega, timeout) as respuesta, open(parcial, "wb") as fh:
            while True:
                trozo = respuesta.read(256 * 1024)
                if not trozo:
                    break
                leido += len(trozo)
                if leido > LIMITE:
                    raise OSError("la descarga es demasiado grande")
                fh.write(trozo)
        if not _entrega_sana(parcial, publicada.version):
            raise OSError("la entrega bajada no sirve")
        os.replace(parcial, destino)
    except Exception:  # noqa: BLE001
        try:
            parcial.unlink()
        except OSError:
            pass
        return None
    for vieja in carpeta.glob("GeoCAD_*.zip"):
        m = ENTREGA.match(vieja.name)
        if m and m.group(1) != publicada.version:
            try:
                vieja.unlink()
            except OSError:
                pass
    return carpeta


def revisar(programa: str, instalada: str, abrir: Optional[Callable] = None,
            hoy: Optional[str] = None):
    """Todo el trabajo de fondo (se corre en otro hilo): ``(publicada, carpeta)``
    si hay que avisar, o None. Sólo cuenta como consultado si GitHub respondió."""
    if not toca_consultar(programa, hoy):
        return None
    publicada = consultar(abrir)
    if publicada is None:
        return None
    try:
        marcar_consultado(programa, hoy)
    except Exception:  # noqa: BLE001
        pass
    if not para_avisar(publicada, instalada):
        return None
    carpeta = descargar(publicada, abrir=abrir)
    return (publicada, carpeta) if carpeta else None


def texto_aviso(programa: str, instalada: str, publicada: Publicada, cambios: str = "") -> str:
    texto = (f"Hay una versión nueva de GeoCAD Yaguareté publicada en GitHub:\n\n"
             f"    instalada en {programa}: {instalada}\n"
             f"    nueva:                 {publicada.version}\n")
    if cambios:
        texto += "\n" + cambios + "\n"
    return texto


#: los tres botones del aviso
ACTUALIZAR, MAS_TARDE, NO_AVISAR = "actualizar", "mas_tarde", "no_avisar"


def preguntar(widgets, parent, titulo: str, texto: str, pagina: str = "") -> str:
    """El aviso con sus tres botones. ``widgets`` es PySide6.QtWidgets (IngeCAD)
    o qgis.PyQt.QtWidgets (QGIS)."""
    caja = widgets.QMessageBox(parent)
    caja.setWindowTitle(titulo)
    caja.setIcon(widgets.QMessageBox.Icon.Information)
    caja.setText(texto)
    if pagina:
        caja.setInformativeText(f'<a href="{pagina}">Ver la versión en GitHub</a>')
        for etiqueta in caja.findChildren(widgets.QLabel):
            if "href" in etiqueta.text():
                etiqueta.setOpenExternalLinks(True)
    rol = widgets.QMessageBox.ButtonRole
    si = caja.addButton("Actualizar ahora", rol.AcceptRole)
    caja.addButton("Más tarde", rol.RejectRole)
    no = caja.addButton("No avisar de esta versión", rol.DestructiveRole)
    caja.setDefaultButton(si)
    caja.exec()
    elegido = caja.clickedButton()
    if elegido is si:
        return ACTUALIZAR
    if elegido is no:
        return NO_AVISAR
    return MAS_TARDE
