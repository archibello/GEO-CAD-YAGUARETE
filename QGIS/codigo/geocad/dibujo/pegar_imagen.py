# -*- coding: utf-8 -*-
"""PEGARIMAGEN en QGIS: las cuentas, sin QGIS (3.89.0).

El mismo procedimiento que GEOPASTEIMAGE de IngeCAD (3.28.0): la imagen del
portapapeles (una captura de pantalla, una imagen copiada en el navegador o
en GIMP, o un archivo de imagen copiado en el explorador) entra con dos clics:

  1. la esquina INFERIOR IZQUIERDA de la imagen;
  2. la esquina INFERIOR DERECHA: da la escala, y la dirección del 1º al 2º
     punto es el borde de abajo (con ORTO, F8, queda derecha). También se
     puede escribir el ancho (queda derecha).

En QGIS una imagen es una capa ráster: una captura se guarda como PNG
(captura_AAAAMMDD_HHMMSS.png) y un archivo copiado se COPIA, los dos con su
archivo de mundo y su .aux.xml, en «<proyecto>_imagenes» (las cuentas y la
carpeta, las de SOLTARIMAGEN: soltar_imagen.py). El original no se toca.

La orden, el portapapeles, Ctrl+V y la vista previa: pegar_imagen_qgis.py.
"""

import os
import re
import time

from . import soltar_imagen as SI

_NUMERO = re.compile(r'^[+-]?(\d+(\.\d*)?|\.\d+)$')


def colocacion(p1, p2):
    """(ancho, giro en grados) del borde de abajo que va de ``p1`` a ``p2``;
    None si los dos puntos coinciden."""
    ancho = SI.ancho_de(p1, p2)
    if ancho <= 1e-12:
        return None
    return ancho, SI.angulo_de(p1, p2)


def ancho_escrito(texto):
    """Un número solo («12.5») es el ancho; «x,y», «@…» o «d<a» son puntos."""
    t = str(texto).strip()
    return float(t) if _NUMERO.match(t) else None


def nombre_captura(carpeta, ahora=None):
    """captura_AAAAMMDD_HHMMSS.png, sin pisar otra (…_2, …_3) ni su archivo de mundo."""
    base = 'captura_' + time.strftime('%Y%m%d_%H%M%S', time.localtime(ahora))
    ruta = os.path.join(str(carpeta), base + '.png')
    n = 2
    while os.path.exists(ruta) or os.path.exists(SI.ruta_mundo(ruta)):
        ruta = os.path.join(str(carpeta), '%s_%d.png' % (base, n))
        n += 1
    return ruta


def ruta_de_texto(texto):
    """Un archivo de imagen escrito en el portapapeles como texto (una ruta o
    «file://…» por renglón, como deja el explorador); None si no hay."""
    from urllib.parse import unquote, urlparse
    for renglon in str(texto or '').splitlines():
        r = renglon.strip()
        if r.startswith('file://'):
            r = unquote(urlparse(r).path)
        if r and SI.es_imagen(r) and os.path.isfile(r):
            return r
    return None


def guardar_captura(guardar, carpeta, p1, ancho, giro, px, py, wkt='', ahora=None):
    """Escribe la captura con ``guardar(ruta) -> bool`` como PNG en ``carpeta``,
    con su archivo de mundo y su .aux.xml; devuelve la ruta."""
    os.makedirs(str(carpeta), exist_ok=True)
    ruta = nombre_captura(carpeta, ahora)
    if not guardar(ruta) or not os.path.isfile(ruta):
        raise OSError('no se pudo escribir %s' % ruta)
    SI.georreferenciar(ruta, p1, ancho, giro, px, py, wkt)
    return ruta


def resumen(px, py, ancho, giro):
    """«400 × 200 píxeles, 80 × 40 unidades, girada 30°»."""
    giro_txt = ', girada %.4g°' % giro if abs(giro) > 1e-9 else ''
    return '%d × %d píxeles, %.4g × %.4g unidades%s' % (px, py, ancho, ancho * py / px, giro_txt)

