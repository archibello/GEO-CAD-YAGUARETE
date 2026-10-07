# -*- coding: utf-8 -*-
"""Registro de diagnóstico: si QGIS se cierra de golpe, dibujo_crash.log (en la carpeta
del complemento) guarda los últimos comandos y la pila de Python en el momento del cierre."""

import os
import time

PATH = os.path.join(os.path.dirname(__file__), 'dibujo_crash.log')
_FILE = None


def enable():
    global _FILE
    try:
        if os.path.exists(PATH) and os.path.getsize(PATH) > 512 * 1024:
            os.remove(PATH)
        _FILE = open(PATH, 'a', encoding='utf-8')
        _FILE.write('\n===== QGIS iniciado %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
        _FILE.flush()
        import faulthandler
        faulthandler.enable(file=_FILE, all_threads=True)
    except Exception:  # noqa: BLE001
        _FILE = None


def trail(msg):
    if _FILE is None:
        return
    try:
        _FILE.write('%s %s\n' % (time.strftime('%H:%M:%S'), msg))
        _FILE.flush()
    except Exception:  # noqa: BLE001
        pass
