"""Arma una versión de GeoCAD a partir del código del proyecto.

    python3 COMUN/build.py 2.0.0          arma la versión
    python3 COMUN/build.py --sincronizar  sólo copia el núcleo a los dos lados

    VERSIONES/GeoCAD <v>/
        GeoCad Tool/instalar_geocad_<v>.py   INSTALADOR ÚNICO: IngeCAD y QGIS
                                             (Consola: python3 ..., o AP en IngeCAD)
        GeoCad Tool/INSTALAR_GeoCAD.sh       lo mismo, con doble clic
        GeoCad Tool/geocad_qgis_<v>.zip      sólo QGIS (Instalar a partir de ZIP)
        CAMBIOS_<v>.txt, LEEME.txt
        GeoCAD_<v>.zip                       todo junto, para llevar a otra computadora

Las versiones entregadas no se pisan: si ya existe, hay que usar otro número
(o --forzar, sólo para rehacer una versión que todavía no se entregó).
El núcleo (COMUN/nucleo/*.py) es el ÚNICO lugar donde se editan los módulos
compartidos: se copian a QGIS/codigo/geocad e INGECAD/codigo/geocad.
"""
import base64
import hashlib
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ING = ROOT / "INGECAD" / "codigo" / "geocad"
QG = ROOT / "QGIS" / "codigo" / "geocad"
COMUN = ROOT / "COMUN"
NUCLEO = COMUN / "nucleo"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
VERSION = ARGS[0] if ARGS else None
FORCE = "--forzar" in sys.argv


def shared():
    return sorted(p.name for p in NUCLEO.glob("*.py"))


def sincronizar():
    for name in shared():
        for dst in (ING, QG):
            shutil.copy2(NUCLEO / name, dst / name)


def files_of(folder: Path):
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")


def zip_folder(folder: Path, arcroot: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files_of(folder):
            info = zipfile.ZipInfo(f"{arcroot}/{p.relative_to(folder).as_posix()}",
                                   date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())
    return buf.getvalue()


PLANTILLA = COMUN / "plantilla_instalador.py.txt"     # el instalador único (IngeCAD + QGIS)


def _b64(raw: bytes) -> str:
    b64 = base64.b64encode(raw).decode()
    return "\n".join(b64[i:i + 100] for i in range(0, len(b64), 100))


def instalador(src: Path, version: str, qgis_src: Path = None) -> str:
    """El instalador único: el plugin de IngeCAD y el complemento de QGIS en un
    solo archivo .py (sirve con AP en IngeCAD y desde la Consola)."""
    raw = zip_folder(src, "geocad")
    qraw = zip_folder(qgis_src or QG, "geocad")
    files_sha = {p.relative_to(src).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in files_of(src)}
    return (PLANTILLA.read_text(encoding="utf-8")
            .replace("@VERSION@", version)
            .replace("@ZIP_SHA@", hashlib.sha256(raw).hexdigest())
            .replace("@FILES_SHA@", repr(files_sha))
            .replace("@QGIS_SHA@", hashlib.sha256(qraw).hexdigest())
            .replace("@QGIS_DATA@", _b64(qraw))
            .replace("@DATA@", _b64(raw)))


def poner_version(version: str) -> None:
    init = (ING / "__init__.py").read_text()
    init = re.sub(r'version="[^"]+"', f'version="{version}"', init, count=1)
    init = re.sub(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', init, count=1, flags=re.M)
    (ING / "__init__.py").write_text(init)
    meta = re.sub(r"^version=.*$", f"version={version}", (QG / "metadata.txt").read_text(), flags=re.M)
    (QG / "metadata.txt").write_text(meta)
    plug = re.sub(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', (QG / "plugin.py").read_text(), flags=re.M)
    (QG / "plugin.py").write_text(plug)


def main():
    if "--sincronizar" in sys.argv and VERSION is None:
        sincronizar()
        print("Núcleo copiado a los dos lados.")
        return
    if VERSION is None:
        sys.exit("Uso: python3 COMUN/build.py <versión>   (p. ej. 2.0.0)")
    changes = COMUN / f"CAMBIOS_{VERSION}.txt"
    if not changes.exists():
        sys.exit(f"Falta COMUN/{changes.name}: escribí los cambios de la versión antes de armarla.")
    carpeta = ROOT / "VERSIONES" / f"GeoCAD {VERSION}"
    tool = carpeta / "GeoCad Tool"
    qgis_zip = tool / f"geocad_qgis_{VERSION}.zip"
    installer_py = tool / f"instalar_geocad_{VERSION}.py"
    bundle = carpeta / f"GeoCAD_{VERSION}.zip"
    if not FORCE and any(p.exists() for p in (qgis_zip, installer_py, bundle)):
        sys.exit(f"La versión {VERSION} ya fue entregada: usá el número siguiente.")
    sincronizar()
    poner_version(VERSION)
    tool.mkdir(parents=True, exist_ok=True)
    qgis_zip.write_bytes(zip_folder(QG, "geocad"))
    installer_py.write_text(instalador(ING, VERSION), encoding="utf-8")
    script = (f"#!/bin/sh\n# GeoCAD {VERSION}: instala y activa GeoCAD en IngeCAD y en QGIS.\n"
              f'cd "$(dirname "$0")" && python3 instalar_geocad_{VERSION}.py\n'
              "printf '\\nPulse Enter para cerrar. '; read _\n")
    sh = tool / "INSTALAR_GeoCAD.sh"
    sh.write_text(script, encoding="utf-8")
    sh.chmod(0o755)
    shutil.copy2(changes, carpeta / changes.name)
    shutil.copy2(COMUN / "LEEME.txt", carpeta / "LEEME.txt")
    top = f"GeoCAD_{VERSION}"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(installer_py, f"{top}/instalar_geocad_{VERSION}.py")
        info = zipfile.ZipInfo(f"{top}/INSTALAR_GeoCAD.sh", date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o755 << 16
        zf.writestr(info, script)
        zf.write(qgis_zip, f"{top}/opcional_QGIS_geocad_qgis_{VERSION}.zip")
        zf.write(COMUN / "LEEME.txt", f"{top}/LEEME.txt")
        zf.write(changes, f"{top}/{changes.name}")
    for p in (qgis_zip, installer_py, bundle):
        print(f"  {p.relative_to(ROOT)}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
