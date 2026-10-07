# -*- coding: utf-8 -*-
"""Persistencia: UNIDADES en el proyecto y ORTO en la configuración de QGIS."""

from qgis.core import QgsProject, QgsSettings

from .units import Units

SCOPE = 'DibujoCAD'


def _read(proj, key, default, kind):
    try:
        if kind is bool:
            v, ok = proj.readBoolEntry(SCOPE, key, default)
        elif kind is int:
            v, ok = proj.readNumEntry(SCOPE, key, default)
        elif kind is float:
            v, ok = proj.readDoubleEntry(SCOPE, key, default)
        else:
            v, ok = proj.readEntry(SCOPE, key, default)
        return v if ok else default
    except Exception:
        return default


def load_units():
    p = QgsProject.instance()
    d = Units()
    return Units(
        luprec=_read(p, 'luprec', d.luprec, int),
        aunits=_read(p, 'aunits', d.aunits, int),
        auprec=_read(p, 'auprec', d.auprec, int),
        angbase=_read(p, 'angbase', d.angbase, float),
        angdir_cw=_read(p, 'angdir_cw', d.angdir_cw, bool),
        relmode=_read(p, 'relmode', d.relmode, str),
    )


def save_units(units):
    p = QgsProject.instance()
    for k, v in units.as_dict().items():
        if isinstance(v, bool) and hasattr(p, 'writeEntryBool'):
            p.writeEntryBool(SCOPE, k, v)
        elif isinstance(v, float) and hasattr(p, 'writeEntryDouble'):
            p.writeEntryDouble(SCOPE, k, v)
        else:
            p.writeEntry(SCOPE, k, v)
    p.setDirty(True)


def get_setting(key, default, typ):
    s = QgsSettings()
    try:
        return s.value('dibujo_cad/' + key, default, type=typ)
    except TypeError:
        return s.value('dibujo_cad/' + key, default)


def set_setting(key, value):
    QgsSettings().setValue('dibujo_cad/' + key, value)
