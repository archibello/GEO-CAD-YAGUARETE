"""Referencias en el marco de las imágenes (3.33.7, pedido de Fernando).

IngeCAD no le da referencias a una imagen (IMAGE): una vez insertada no se la
puede tomar de una esquina para ubicarla ni escalarla desde los extremos. En
AutoCAD el marco de la imagen se engancha como un rectángulo: Final en las
esquinas, Medio, Intersección, Cercano, Perpendicular, y Inserción en su
punto de inserción. GeoCAD se lo agrega envolviendo SnapEngine._extract; una
imagen recortada se engancha por su recorte. Va con el módulo «georref»
(Imágenes georreferenciadas): apagado, IngeCAD queda como venía.
"""
from __future__ import annotations

import time

_activo_cache = [0.0, False]


def _activo() -> bool:
    """Módulo georref prendido (se relee el archivo cada 2 s como mucho)."""
    ahora = time.monotonic()
    if ahora - _activo_cache[0] > 2.0:
        _activo_cache[0] = ahora
        from . import modulos
        _activo_cache[1] = modulos.activo("ingecad", "georref")
    return _activo_cache[1]


def marco(imagen) -> list:
    """Los vértices del marco (o del recorte) de la imagen en el dibujo,
    cerrado: el último repite el primero."""
    puntos = [(p.x, p.y) for p in imagen.boundary_path_wcs()]
    if len(puntos) > 2 and puntos[0] != puntos[-1]:
        puntos.append(puntos[0])
    return puntos


def _agregar(e, oid, segs, seg_o, targets, target_o) -> None:
    puntos = marco(e)
    for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]):
        if (x1, y1) != (x2, y2):
            segs.append((x1, y1, x2, y2)); seg_o.append(oid)
    if targets is not None:
        from core.snap import _TARGET_CODE
        p = e.dxf.insert
        targets.append((p.x, p.y, _TARGET_CODE["INS"])); target_o.append(oid)


def _envolver_extract(original):
    def _extract(e, oid, segs, seg_o, circles, circle_o, arcs, arc_o, points, point_o,
                 curves=None, curve_o=None, targets=None, target_o=None):
        try:
            if e.dxftype() == "IMAGE" and _activo():
                _agregar(e, oid, segs, seg_o, targets, target_o)
        except Exception:  # noqa: BLE001 -- una imagen rara no rompe las referencias
            pass
        return original(e, oid, segs, seg_o, circles, circle_o, arcs, arc_o,
                        points, point_o, curves, curve_o, targets, target_o)

    _extract._marco_original = original
    _extract._marco_fabrica = _envolver_extract
    return _extract


def _instalado(funcion) -> bool:
    """¿Está el nuestro en la cadena de envoltorios (el de bloques puede
    quedar por fuera o por dentro)?"""
    vistos = 0
    while funcion is not None and vistos < 10:
        if getattr(funcion, "_marco_fabrica", None) is _envolver_extract:
            return True
        funcion = getattr(funcion, "_marco_original", None) or getattr(funcion, "_puente_original", None)
        vistos += 1
    return False


def instalar() -> None:
    """Se llama al cargar el plugin, después de bloques.instalar_referencias.
    Sin IngeCAD (pruebas sin interfaz) se instala igual sobre core.snap."""
    try:
        from core.snap import SnapEngine
    except Exception:  # noqa: BLE001
        return
    actual = SnapEngine.__dict__.get("_extract")
    funcion = getattr(actual, "__func__", actual)
    if funcion is None or _instalado(funcion):
        return
    if getattr(funcion, "_marco_fabrica", None) is not None:   # de una versión anterior
        funcion = funcion._marco_original
    SnapEngine._extract = staticmethod(_envolver_extract(funcion))
