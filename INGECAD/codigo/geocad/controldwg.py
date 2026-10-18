# SPDX-License-Identifier: GPL-3.0-or-later
"""Control de los DWG al guardar (3.28.1, módulo «dwg»).

IngeCAD 0.6.7 revisa cada DWG que guarda (formats/dwg_bridge.verify_dwg):
si LibreDWG (dxf2dwg) escribió alguna línea «ERROR» mientras armaba el
archivo, avisa «the DWG writer reported internal errors while packing the
file», sin decir cuál.

Fernando lo vio el 18/10/2026 con un plano viejo de AutoCAD: 59 × «ERROR: Unknown DXF code 21 for HATCH». Es un error de
LibreDWG, no del plano: su lector DXF (in_dxf.c, add_HATCH) sólo acepta el
código 21 de un borde de sombreado (la Y del punto final de una recta, del
eje mayor de una elipse o de un punto de ajuste de una spline) si NO vale 0
(«pair->value.d != 0.0»). Con Y = 0 lo da por desconocido, pero ese valor ya
era 0: el sombreado sale igual (verificado: los 122 sombreados del plano
quedan idénticos en la ida y vuelta DWG -> DXF -> DWG).

Ahora esas quejas se descartan SÓLO si el DXF que se convirtió tiene al menos
tantos códigos 21 = 0 en sus sombreados como quejas hubo; si hay más quejas
que ceros, se dejan todas. El resto de los avisos se muestra en español y con
el texto de los errores. Con el módulo apagado, como viene.

3.28.2: con el dibujo abierto desde el original de AutoCAD (AC1018) quedaban
9 × «ERROR: DETAILVIEWSTYLE / SECTIONVIEWSTYLE: Unexpected DXF code ...».
Otra vez LibreDWG: no vuelve a leer esos objetos tal como él mismo los
escribe (el DXF de IngeCAD los trae idénticos a los que dio dwg2dxf). Son los
estilos que AutoCAD 2013+ crea en todo dibujo («Imperial24», «Metric50») para
las vistas de detalle y de corte de modelos 3D (VIEWBASE); el DWG r2000 no
los tiene y LibreDWG los descarta siempre: no se pierde nada del dibujo.
"""
from __future__ import annotations

import re
from collections import Counter

from . import modulos
from .dibujo import envolver

PROGRAMA = "ingecad"
FALSA_21 = "Unknown DXF code 21 for HATCH"
FALSA_ESTILOS = ("ERROR: DETAILVIEWSTYLE: ", "ERROR: SECTIONVIEWSTYLE: ")   # 3.28.2
MAX_DETALLE = 3                 # errores distintos que se nombran en el aviso

AVISO_ERRORES = "the DWG writer reported internal errors while packing the file"
AVISO_REABRIR = "could not re-open the saved DWG to verify it"
_PERDIDOS = re.compile(r"some drawing objects did not survive the save \((\d+) \S+ (\d+)\)")


def activo() -> bool:
    try:
        return modulos.activo(PROGRAMA, "dwg")
    except Exception:  # noqa: BLE001
        return False


def ceros_21(dxf_path) -> int:
    """Cuántos códigos 21 que valen 0 hay en los HATCH del DXF (en el modelo,
    el papel y los bloques)."""
    n = 0
    en_hatch = False
    with open(dxf_path, "rb") as fh:
        lineas = iter(fh)
        for codigo in lineas:
            codigo = codigo.strip()
            valor = next(lineas, b"").strip()
            if codigo == b"0":
                en_hatch = valor == b"HATCH"
            elif en_hatch and codigo == b"21":
                try:
                    n += float(valor) == 0.0
                except ValueError:
                    pass
    return n


def es_estilo_de_vista(linea: str) -> bool:
    return linea.strip().startswith(FALSA_ESTILOS)


def filtrar(stderr: str, dxf_path) -> tuple:
    """(stderr sin las falsas alarmas que el DXF explica, cuántas se sacaron)."""
    lineas = (stderr or "").splitlines()
    quitar = {i for i, linea in enumerate(lineas) if es_estilo_de_vista(linea)}
    falsas = [i for i, linea in enumerate(lineas) if FALSA_21 in linea]
    if falsas:
        try:
            ceros = ceros_21(dxf_path)
        except OSError:
            ceros = -1
        if len(falsas) <= ceros:    # más quejas que ceros: hay algo más, se dejan
            quitar.update(falsas)
    if not quitar:
        return stderr or "", 0
    return "\n".join(l for i, l in enumerate(lineas) if i not in quitar), len(quitar)


def detalle(errores) -> str:
    """«ERROR: x» (3 veces); «ERROR: y»; y 2 más."""
    cuenta = Counter(errores)
    partes = [f"«{e}»" + (f" ({n} veces)" if n > 1 else "")
              for e, n in cuenta.most_common(MAX_DETALLE)]
    resto = len(cuenta) - MAX_DETALLE
    if resto > 0:
        partes.append(f"y {resto} más")
    return "; ".join(partes)


def traducir(aviso: str, errores) -> str:
    """El aviso de IngeCAD en español (y con los errores, si los hay)."""
    if aviso == AVISO_ERRORES:
        texto = "LibreDWG informó errores al armar el DWG"
        return f"{texto}: {detalle(errores)}" if errores else texto
    if aviso == AVISO_REABRIR:
        return "no se pudo volver a abrir el DWG guardado para controlarlo"
    m = _PERDIDOS.fullmatch(aviso)
    if m:
        return (f"se perdieron objetos del dibujo al guardar ({m.group(1)} → "
                f"{m.group(2)}); guarde también en DXF")
    return aviso


def _envolver_verify_dwg(original):
    def verify_dwg(source_dxf, dwg_path, stderr: str = ""):
        if not activo():
            return original(source_dxf, dwg_path, stderr)
        limpio, _ = filtrar(stderr, source_dxf)
        avisos = original(source_dxf, dwg_path, limpio)
        try:
            from formats.dwg_bridge import _converter_errors
            errores = _converter_errors(limpio)
        except Exception:  # noqa: BLE001
            errores = []
        return [traducir(a, errores) for a in avisos]
    verify_dwg._puente_original = original
    verify_dwg._puente_fabrica = _envolver_verify_dwg
    return verify_dwg


def instalar() -> None:
    """Se llama al cargar el plugin."""
    try:
        from formats import dwg_bridge
    except Exception:  # noqa: BLE001
        return
    if getattr(dwg_bridge.verify_dwg, "_puente_fabrica", None) is not _envolver_verify_dwg:
        envolver(dwg_bridge, "verify_dwg", _envolver_verify_dwg, reemplazar=True)
