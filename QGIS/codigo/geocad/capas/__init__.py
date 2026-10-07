# -*- coding: utf-8 -*-

def classFactory(iface):
    """Carga y retorna la clase principal del complemento."""
    from .plugin import LayerPropertiesPlugin
    return LayerPropertiesPlugin(iface)
