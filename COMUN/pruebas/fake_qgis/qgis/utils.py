"""Imitación de qgis.utils: el registro de complementos cargados."""
plugins = {}
descargados = []


def unloadPlugin(name):
    descargados.append(name)
    plugins.pop(name, None)
    return True
