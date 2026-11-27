"""Íconos de QgsRubberBand con QGIS 4.4 (3.102.2).

Fernando, 27/11/2026, con QGIS 4.4.0: «no estoy viendo la barra de comandos».
QGIS 4.4 quitó QgsRubberBand.ICON_FULL_BOX (ahora Qgis.RubberBandIconType.BoxFilled)
y los agarres lo pedían al iniciar Dibujo: el módulo entero no arrancaba (sin línea
de comandos). compat.icono_banda prueba el nombre viejo y, si no está, el nuevo.
Con QGIS de verdad: COMUN/pruebas/ventana/banco_agarres_qgis_real.py.
"""
import tmp_pruebas  # noqa: F401  lo temporal de la prueba se borra al salir
import os, re, sys
from enum import Enum
from pathlib import Path

import types
RAIZ = Path(__file__).resolve().parents[2]
# compat.py sólo necesita qgis.PyQt para importarse: una qgis mínima, sin Qt
for nombre in ("qgis", "qgis.PyQt", "qgis.PyQt.QtCore", "qgis.PyQt.QtGui"):
    sys.modules[nombre] = types.ModuleType(nombre)
sys.modules["qgis.PyQt.QtCore"].Qt = type("Qt", (), {})
sys.modules["qgis.PyQt.QtCore"].QT_VERSION_STR = "6.11.2"
sys.modules["qgis.PyQt"].QtCore = sys.modules["qgis.PyQt.QtCore"]
for n in ("QAction", "QActionGroup", "QShortcut"):
    setattr(sys.modules["qgis.PyQt.QtGui"], n, type(n, (), {}))
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "compat_dibujo", RAIZ / "QGIS" / "codigo" / "geocad" / "dibujo" / "compat.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


class Nuevo(Enum):           # Qgis.RubberBandIconType (QGIS 3.40+)
    NoIcon = 0
    CrossPlus = 1
    CrossX = 2
    Box = 3
    Circle = 4
    BoxFilled = 5
    Diamond = 6
    DiamondFilled = 7
    SVG = 8


class QgisNs:
    RubberBandIconType = Nuevo


class Banda44:               # QGIS 4.4: IconType sin ICON_FULL_BOX
    class IconType:
        ICON_BOX = "viejo-box"
        ICON_CIRCLE = "viejo-circle"


class Banda42:               # QGIS 4.2 y antes: los dos
    class IconType:
        ICON_BOX = "viejo-box"
        ICON_FULL_BOX = "viejo-full"


class Banda3:                # QGIS 3 (PyQt5): en la clase
    ICON_FULL_BOX = "qt5-full"


# QGIS 4.4: lo que falta se toma del nombre nuevo; lo que está, del viejo
assert C.icono_banda("ICON_FULL_BOX", Banda44, QgisNs) is Nuevo.BoxFilled
assert C.icono_banda("ICON_BOX", Banda44, QgisNs) == "viejo-box"
# antes: como siempre, sin mirar Qgis
assert C.icono_banda("ICON_FULL_BOX", Banda42, None) == "viejo-full"
assert C.icono_banda("ICON_FULL_BOX", Banda3, None) == "qt5-full"
# todos los nombres viejos tienen su nuevo
for viejo, nuevo in C._ICONOS_BANDA.items():
    assert C.icono_banda(viejo, Banda44, QgisNs) in (getattr(Nuevo, nuevo), "viejo-box", "viejo-circle"), viejo

# los agarres ya no piden el ícono directo a QgsRubberBand
fuente = (RAIZ / "QGIS" / "codigo" / "geocad" / "dibujo" / "agarres.py").read_text(encoding="utf-8")
assert "icono_banda(icono" in fuente and "enum(QgsRubberBand" not in fuente
# en ningún lado se pide ICON_FULL_BOX directo
for f in (RAIZ / "QGIS" / "codigo" / "geocad").rglob("*.py"):
    t = f.read_text(encoding="utf-8")
    for linea in t.splitlines():
        if re.search(r"QgsRubberBand\.(IconType\.)?ICON_FULL_BOX|enum\(QgsRubberBand,\s*'IconType',\s*'ICON_FULL_BOX'", linea):
            raise AssertionError("%s: %s" % (f, linea.strip()))

print("TODO OK test_icono_banda_qgis")
