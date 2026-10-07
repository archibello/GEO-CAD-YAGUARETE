# SPDX-License-Identifier: GPL-3.0-or-later
"""Actualizar el puente desde una carpeta, sin APPLOAD ni «Instalar a partir de ZIP».

Busca en la carpeta de actualizaciones (configuración común; normalmente la
carpeta del proyecto o una copia de COMUN/entregas) la versión más nueva:

    instalar_geocad_<v>.py  /  2_IngeCAD_instalar_geocad_<v>.py   (IngeCAD)
    geocad_qgis_<v>.zip     /  1_QGIS_geocad_qgis_<v>.zip         (QGIS)
    GeoCAD_<v>.zip          (la entrega completa: trae los dos)

Python puro (sin Qt): el complemento de QGIS usa una copia idéntica.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_V = r"(\d+\.\d+\.\d+)"
PATRONES = {
    "ingecad": re.compile(rf"^(?:\d+_IngeCAD_)?instalar_geocad_{_V}\.py$"),
    "qgis": re.compile(rf"^(?:\d+_QGIS_)?geocad_qgis_{_V}\.zip$"),
}
ENTREGA = re.compile(rf"^GeoCAD_{_V}\.zip$")
PROFUNDIDAD = 3


def version_tuple(text: str) -> tuple:
    try:
        return tuple(int(x) for x in str(text).strip().split("."))
    except ValueError:
        return (0,)


@dataclass(frozen=True)
class Candidato:
    version: str
    ruta: Path                    # el archivo, o la entrega que lo contiene
    dentro: Optional[str] = None  # nombre dentro de la entrega (zip)

    @property
    def nombre(self) -> str:
        return Path(self.dentro).name if self.dentro else self.ruta.name


def _recorrer(carpeta: Path):
    carpeta = Path(carpeta)
    base = len(carpeta.parts)
    for raiz, dirs, archivos in os.walk(carpeta):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_", "__")))
        if len(Path(raiz).parts) - base >= PROFUNDIDAD:
            dirs[:] = []
        for nombre in archivos:
            yield Path(raiz) / nombre


def buscar(carpeta, lado: str) -> list:
    """Todas las versiones de ``lado`` ("ingecad" o "qgis") en la carpeta,
    de la más nueva a la más vieja."""
    patron = PATRONES[lado]
    out = {}
    if not carpeta or not Path(carpeta).is_dir():
        return []
    for ruta in _recorrer(Path(carpeta)):
        m = patron.match(ruta.name)
        if m:
            out.setdefault(m.group(1), Candidato(m.group(1), ruta))
            continue
        if ENTREGA.match(ruta.name):
            try:
                with zipfile.ZipFile(ruta) as zf:
                    for miembro in zf.namelist():
                        mm = patron.match(Path(miembro).name)
                        if mm and mm.group(1) not in out:
                            out[mm.group(1)] = Candidato(mm.group(1), ruta, miembro)
            except (OSError, zipfile.BadZipFile):
                continue
    return sorted(out.values(), key=lambda c: version_tuple(c.version), reverse=True)


def mas_nueva(carpeta, lado: str, actual: str) -> Optional[Candidato]:
    """La versión más nueva que la instalada, o None."""
    for cand in buscar(carpeta, lado):
        if version_tuple(cand.version) > version_tuple(actual):
            return cand
        return None
    return None


def extraer(cand: Candidato, destino=None) -> Path:
    """El archivo listo para usar (si venía dentro de la entrega, se saca a
    una carpeta temporal)."""
    if cand.dentro is None:
        return cand.ruta
    destino = Path(destino or tempfile.mkdtemp(prefix="puente-actualizar-"))
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / Path(cand.dentro).name
    with zipfile.ZipFile(cand.ruta) as zf:
        salida.write_bytes(zf.read(cand.dentro))
    return salida


def cambios(cand: Candidato, limite: int = 1500) -> str:
    """El CAMBIOS_<v>.txt de esa versión, si se encuentra (para mostrarlo)."""
    nombre = f"CAMBIOS_{cand.version}.txt"
    texto = ""
    if cand.dentro is not None:
        try:
            with zipfile.ZipFile(cand.ruta) as zf:
                for miembro in zf.namelist():
                    if Path(miembro).name == nombre:
                        texto = zf.read(miembro).decode("utf-8", "replace")
                        break
        except (OSError, zipfile.BadZipFile):
            pass
    else:
        for carpeta in (cand.ruta.parent, cand.ruta.parent.parent / "COMUN",
                        cand.ruta.parent.parent.parent / "COMUN"):
            if (carpeta / nombre).is_file():
                texto = (carpeta / nombre).read_text(encoding="utf-8", errors="replace")
                break
    texto = texto.strip()
    return texto if len(texto) <= limite else texto[:limite].rstrip() + "\n..."


def instalar_zip(zip_path, plugins_dir, plugin_id: str) -> Path:
    """Instala un complemento de QGIS desde su .zip, limpio: verifica el
    zip, lo descomprime aparte y recién entonces reemplaza la versión
    instalada (que queda como .anterior-<id>). Si algo falla, no toca nada."""
    zip_path, plugins_dir = Path(zip_path), Path(plugins_dir)
    with zipfile.ZipFile(zip_path) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("el .zip está dañado; no se instaló nada")
        nombres = zf.namelist()
        if f"{plugin_id}/metadata.txt" not in nombres:
            raise RuntimeError(f"el .zip no trae el complemento «{plugin_id}»")
        for n in nombres:
            if n.startswith("/") or ".." in Path(n).parts:
                raise RuntimeError("el .zip trae rutas no válidas; no se instaló nada")
        staging = plugins_dir / f".instalando-{plugin_id}"
        shutil.rmtree(staging, ignore_errors=True)
        zf.extractall(staging)
    nuevo = staging / plugin_id
    destino = plugins_dir / plugin_id
    anterior = plugins_dir / f".anterior-{plugin_id}"
    if destino.exists():
        shutil.rmtree(anterior, ignore_errors=True)
        destino.rename(anterior)
    nuevo.rename(destino)
    shutil.rmtree(staging, ignore_errors=True)
    return destino
