# SPDX-License-Identifier: GPL-3.0-or-later
"""GeoCAD: menú «GeoCAD» en QGIS (GIS to CAD y CAD to GIS con IngeCAD)."""
import sys as _sys

# Al actualizar en caliente (GeoCAD > Actualizar: qgis.utils.reloadPlugin),
# QGIS sólo saca de la memoria los módulos que vio importar con «import»; los
# submódulos que se cargan con importlib (Dibujo, Capas) quedaban con el
# código viejo hasta reiniciar QGIS (Fernando, 24/10/2026: las categorías de
# Administrar botones en 0/0). Si este paquete se está importando de nuevo,
# lo que haya de él en la memoria es de antes: afuera (3.40.1).
for _viejo in [m for m in _sys.modules if m.startswith(__name__ + ".")]:
    _sys.modules.pop(_viejo, None)


def classFactory(iface):
    from .plugin import GeoCAD

    return GeoCAD(iface)
