# -*- coding: utf-8 -*-
"""Compatibilidad QGIS 3 (PyQt5) / QGIS 4 (PyQt6)."""

from qgis.PyQt import QtCore
from qgis.PyQt.QtCore import Qt

try:  # Qt6
    from qgis.PyQt.QtGui import QAction, QActionGroup, QShortcut  # noqa: F401
except ImportError:  # Qt5
    from qgis.PyQt.QtWidgets import QAction, QActionGroup, QShortcut  # noqa: F401


def enum(owner, scope, member):
    """Devuelve owner.scope.member (Qt6) o owner.member (Qt5)."""
    sc = getattr(owner, scope, None)
    if sc is not None and hasattr(sc, member):
        return getattr(sc, member)
    return getattr(owner, member)


def qt(scope, member):
    return enum(Qt, scope, member)


def exec_dialog(dlg):
    fn = getattr(dlg, 'exec', None) or getattr(dlg, 'exec_')
    return fn()


def exec_menu(menu, pos):
    fn = getattr(menu, 'exec', None) or getattr(menu, 'exec_')
    return fn(pos)


def string_field(name, length=50):
    """Crea un QgsField de texto con la API disponible."""
    from qgis.core import QgsField
    try:
        from qgis.PyQt.QtCore import QMetaType
        return QgsField(name, QMetaType.Type.QString, len=length)
    except (ImportError, AttributeError, TypeError):
        from qgis.PyQt.QtCore import QVariant
        return QgsField(name, QVariant.String, len=length)


def accepted_code():
    from qgis.PyQt.QtWidgets import QDialog
    return enum(QDialog, 'DialogCode', 'Accepted')


def symbol_property(member):
    """QgsSymbolLayer.Property.X (nuevo) o QgsSymbolLayer.PropertyX (antiguo)."""
    from qgis.core import QgsSymbolLayer
    prop = getattr(QgsSymbolLayer, 'Property', None)
    if prop is not None and hasattr(prop, member):
        return getattr(prop, member)
    return getattr(QgsSymbolLayer, 'Property' + member)


def render_mm():
    from qgis.core import Qgis, QgsUnitTypes
    ru = getattr(Qgis, 'RenderUnit', None)
    if ru is not None and hasattr(ru, 'Millimeters'):
        return ru.Millimeters
    return QgsUnitTypes.RenderMillimeters


def geometry_kind(layer):
    """'line', 'polygon', 'point' o None."""
    try:
        gt = layer.geometryType()
    except Exception:
        return None
    from qgis.core import QgsWkbTypes
    try:
        from qgis.core import Qgis
        GT = Qgis.GeometryType
        table = {GT.Point: 'point', GT.Line: 'line', GT.Polygon: 'polygon'}
    except AttributeError:
        table = {QgsWkbTypes.PointGeometry: 'point',
                 QgsWkbTypes.LineGeometry: 'line',
                 QgsWkbTypes.PolygonGeometry: 'polygon'}
    # Comparación tolerante (enum o int)
    for k, v in table.items():
        try:
            if gt == k or int(gt) == int(k):
                return v
        except Exception:
            if gt == k:
                return v
    return None


QT_VERSION = int(QtCore.QT_VERSION_STR.split('.')[0])


def line_geometry_type():
    try:
        from qgis.core import Qgis
        return Qgis.GeometryType.Line
    except AttributeError:
        from qgis.core import QgsWkbTypes
        return QgsWkbTypes.LineGeometry


def point_geometry_type():
    try:
        from qgis.core import Qgis
        return Qgis.GeometryType.Point
    except AttributeError:
        from qgis.core import QgsWkbTypes
        return QgsWkbTypes.PointGeometry


def polygon_geometry_type():
    try:
        from qgis.core import Qgis
        return Qgis.GeometryType.Polygon
    except AttributeError:
        from qgis.core import QgsWkbTypes
        return QgsWkbTypes.PolygonGeometry
