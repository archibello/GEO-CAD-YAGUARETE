# -*- coding: utf-8 -*-
"""Lectura de los bloques de Bloques GMS de Fernando (archivos .json en la
carpeta 'bloques' de cada proyecto, formato 2). Python puro: sólo lee, nunca
escribe ni borra esos archivos (3.45.0)."""

import json
import os

INVALIDOS = '<>/\\":;?*|=`'


def leer(path):
    """-> dict(nombre, wkts, p2, crs, capa) o None si no es un bloque GMS."""
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get('geometries_wkt'), list):
        return None
    try:
        p2 = (float(data['p2'][0]), float(data['p2'][1]))
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    nombre = str(data.get('name') or os.path.splitext(os.path.basename(path))[0]).strip()
    nombre = ''.join('_' if c in INVALIDOS else c for c in nombre)[:80] or 'bloque_gms'
    wkts = [w for w in data['geometries_wkt'] if isinstance(w, str) and w.strip()]
    return {'nombre': nombre, 'wkts': wkts, 'p2': p2, 'crs': str(data.get('project_crs') or ''),
            'capa': str(data.get('source_layer_name') or '')}


def archivos(carpeta):
    """Los .json de una carpeta, ordenados."""
    try:
        return sorted(os.path.join(carpeta, f) for f in os.listdir(carpeta) if f.lower().endswith('.json'))
    except OSError:
        return []
