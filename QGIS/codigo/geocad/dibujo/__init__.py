# -*- coding: utf-8 -*-


def classFactory(iface):
    from .plugin import DibujoCADPlugin
    return DibujoCADPlugin(iface)
