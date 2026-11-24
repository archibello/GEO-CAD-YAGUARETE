# -*- coding: utf-8 -*-
"""SOLTARIMAGEN en QGIS: las cuentas, sin QGIS (3.88.0).

Pedido de Fernando (23/11/2026), el mismo procedimiento que en IngeCAD: una
imagen arrastrada desde el explorador se ubica con la esquina inferior
izquierda, un 2º punto que da el ancho (la escala) y el giro al final.

En QGIS una imagen es una capa ráster: se hace una COPIA de la imagen con su
archivo de mundo (con el giro) y su .aux.xml (el sistema de coordenadas) en
«<nombre del proyecto>_imagenes», junto al proyecto (o en Imágenes/GeoCAD si
el proyecto no está guardado). El original no se toca (decidido con Fernando).

La orden, el arrastre y la vista previa: soltar_imagen_qgis.py.
"""

import math
import os

EXTENSIONES = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.gif')

#: el archivo de mundo de cada formato (el que GDAL busca primero)
MUNDO = {'.png': '.pgw', '.jpg': '.jgw', '.jpeg': '.jgw', '.bmp': '.bpw',
         '.tif': '.tfw', '.tiff': '.tfw', '.gif': '.gfw'}


def es_imagen(ruta):
    return os.path.splitext(str(ruta))[1].lower() in EXTENSIONES


def ancho_de(p1, p2):
    """El ancho que da el 2º punto: la distancia del 1º al 2º."""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def angulo_de(p1, p):
    """La dirección (grados, antihoraria desde el este) del 1er punto a ``p``."""
    return math.degrees(math.atan2(p[1] - p1[1], p[0] - p1[0]))


def ejes(ancho, giro, px):
    """(u, v): un píxel hacia la derecha y uno hacia arriba, en el mapa."""
    a = math.radians(giro)
    lado = ancho / float(px)
    u = (lado * math.cos(a), lado * math.sin(a))
    return u, (-u[1], u[0])


def esquinas(p1, ancho, giro, px, py):
    """Las 4 esquinas (inf. izq., inf. der., sup. der., sup. izq.); [] sin ancho."""
    if ancho <= 0 or px <= 0 or py <= 0:
        return []
    (ux, uy), (vx, vy) = ejes(ancho, giro, px)
    x0, y0 = p1
    bx, by = ux * px, uy * px
    hx, hy = vx * py, vy * py
    return [(x0, y0), (x0 + bx, y0 + by), (x0 + bx + hx, y0 + by + hy), (x0 + hx, y0 + hy)]


def archivo_mundo(p1, ancho, giro, px, py):
    """Los 6 valores del archivo de mundo (A, D, B, E, C, F): x = A·col + B·fila + C,
    y = D·col + E·fila + F, con C, F en el CENTRO del píxel de arriba a la izquierda."""
    (ux, uy), (vx, vy) = ejes(ancho, giro, px)
    sx, sy = p1[0] + vx * py, p1[1] + vy * py          # esquina superior izquierda
    cx = sx + 0.5 * ux - 0.5 * vx
    cy = sy + 0.5 * uy - 0.5 * vy
    return (ux, uy, -vx, -vy, cx, cy)


def texto_mundo(valores):
    return ''.join('%.12f\n' % v for v in valores)


def leer_giro(texto):
    """Grados escritos («30», «-12,5», «30°»), o None."""
    t = texto.strip().replace(',', '.').rstrip('°dD').strip()
    try:
        return float(t)
    except ValueError:
        return None


def leer_ancho(texto):
    try:
        return float(texto.strip().replace(',', '.'))
    except ValueError:
        return None


def carpeta_destino(ruta_proyecto, casa=None):
    """Junto al proyecto, en «<nombre>_imagenes»; sin proyecto guardado, en
    Imágenes/GeoCAD (o Pictures/GeoCAD, o ~/GeoCAD)."""
    if ruta_proyecto:
        base, _ext = os.path.splitext(str(ruta_proyecto))
        return base + '_imagenes'
    casa = casa or os.path.expanduser('~')
    for nombre in ('Imágenes', 'Pictures'):
        if os.path.isdir(os.path.join(casa, nombre)):
            return os.path.join(casa, nombre, 'GeoCAD')
    return os.path.join(casa, 'GeoCAD')


def nombre_libre(carpeta, original):
    """El nombre del original en la carpeta, sin pisar otro (…_2, …_3)."""
    stem, ext = os.path.splitext(os.path.basename(str(original)))
    ruta = os.path.join(carpeta, stem + ext)
    n = 2
    while os.path.exists(ruta) or os.path.exists(ruta_mundo(ruta)):
        ruta = os.path.join(carpeta, '%s_%d%s' % (stem, n, ext))
        n += 1
    return ruta


def ruta_mundo(ruta):
    base, ext = os.path.splitext(str(ruta))
    return base + MUNDO.get(ext.lower(), '.wld')


def aux_xml(wkt):
    """El .aux.xml de GDAL con el sistema de coordenadas."""
    from xml.sax.saxutils import escape
    return '<PAMDataset>\n  <SRS>%s</SRS>\n</PAMDataset>\n' % escape(wkt or '')


def copiar(original, carpeta, p1, ancho, giro, px, py, wkt=''):
    """Copia la imagen con su archivo de mundo y su .aux.xml; devuelve la ruta
    de la copia. El original no se toca."""
    import shutil
    os.makedirs(carpeta, exist_ok=True)
    destino = nombre_libre(carpeta, original)
    shutil.copyfile(str(original), destino)
    georreferenciar(destino, p1, ancho, giro, px, py, wkt)
    return destino


def georreferenciar(destino, p1, ancho, giro, px, py, wkt=''):
    """Escribe junto a ``destino`` su archivo de mundo y, con ``wkt``, su .aux.xml
    (también lo usa PEGARIMAGEN, 3.89.0)."""
    with open(ruta_mundo(destino), 'w', encoding='ascii') as f:
        f.write(texto_mundo(archivo_mundo(p1, ancho, giro, px, py)))
    if wkt:
        with open(str(destino) + '.aux.xml', 'w', encoding='utf-8') as f:
            f.write(aux_xml(wkt))
