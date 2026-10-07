# SPDX-License-Identifier: GPL-3.0-or-later
"""GeoCAD: menú «GeoCAD» en QGIS (GIS to CAD y CAD to GIS con IngeCAD)."""


def classFactory(iface):
    from .plugin import GeoCAD

    return GeoCAD(iface)
