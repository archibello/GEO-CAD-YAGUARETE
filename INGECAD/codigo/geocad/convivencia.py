"""Qué versión de IngeCAD corre, para que GeoCAD se aparte de lo que IngeCAD ya resuelve
(regla de convivencia de Fernando: si IngeCAD lo trae, GeoCAD le deja el lugar y conserva lo
suyo para las versiones anteriores).

- 0.8.0: el marco de las imágenes engancha (``marco_imagen``) y los agarres toman lo escrito,
  muestran la marca de la referencia, estiran juntos a los que comparten lugar y abren el menú
  de referencias con Mayús + botón derecho (``agarres_ingecad``).
"""
from __future__ import annotations

import re

#: IngeCAD que ya trae el marco de imágenes y los cuatro de los agarres
NATIVO_08 = (0, 8)


def version_ingecad() -> tuple:
    """(0, 8, 0) de la que corre; () si no se sabe (pruebas sin IngeCAD)."""
    try:
        from core.version import __version__
    except Exception:  # noqa: BLE001 -- IngeCAD viejo o sin IngeCAD
        return ()
    return tuple(int(n) for n in re.findall(r"\d+", str(__version__))[:4])


def ingecad_desde(minima: tuple) -> bool:
    """¿IngeCAD es ``minima`` o más nuevo? Sin saberlo, no: GeoCAD pone lo suyo."""
    actual = version_ingecad()
    return bool(actual) and actual >= tuple(minima)
