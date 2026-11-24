# -*- coding: utf-8 -*-
"""INSERTARGEO, EXPORTARGEO y GEORREF en QGIS: las cuentas, sin QGIS (3.90.0).

Las órdenes de imágenes georreferenciadas de IngeCAD (imagengeo.py), en la
barra «Yaguá Imagenes» de QGIS (Fernando, 23/11/2026):

INSERTARGEO   elegir una imagen georreferenciada (archivo de mundo o GeoTIFF)
              y que entre EN SU LUGAR, como capa ráster (el archivo tal cual,
              como en IngeCAD); sin georreferencia, avisa.
EXPORTARGEO   clic en una imagen del mapa y «Guardar como»: una COPIA con su
              archivo de mundo y el sistema de coordenadas (.aux.xml), donde
              está hoy. El original nunca se pisa.
GEORREF       en QGIS no se repite (decidido con Fernando): abre el
              Georreferenciador de QGIS con la imagen elegida (y sus puntos,
              «<imagen>.points», el mismo archivo que usa GEORREF de IngeCAD).

La geotransformación es la de GDAL: x = g0 + g1·col + g2·fila,
y = g3 + g4·col + g5·fila, desde la ESQUINA de arriba a la izquierda.
Las órdenes: imagen_geo_qgis.py.
"""

import os
import shutil

from . import soltar_imagen as SI

FILTRO_IMAGENES = ('Imágenes (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif);;'
                   'Todos los archivos (*)')
SUFIJO_COPIA = '_georref'                      # el de IngeCAD
IDENTIDAD = (0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def georreferenciada(gt, puntos_control=0):
    """¿GDAL sabe dónde va? (geotransformación distinta de la de píxeles, o PCT)."""
    return (gt is not None and tuple(float(v) for v in gt) != IDENTIDAD) or bool(puntos_control)


def mundo_de_gt(gt):
    """Los 6 valores del archivo de mundo (A, D, B, E, C, F; C y F en el CENTRO del
    píxel de arriba a la izquierda) de una geotransformación de GDAL."""
    g0, g1, g2, g3, g4, g5 = (float(v) for v in gt)
    return (g1, g4, g2, g5, g0 + 0.5 * g1 + 0.5 * g2, g3 + 0.5 * g4 + 0.5 * g5)


def a_mapa(gt, col, fila):
    return (gt[0] + gt[1] * col + gt[2] * fila, gt[3] + gt[4] * col + gt[5] * fila)


def esquinas_gt(gt, ancho, alto):
    """Las 4 esquinas (inf. izq., inf. der., sup. der., sup. izq.) en el mapa."""
    return [a_mapa(gt, 0, alto), a_mapa(gt, ancho, alto), a_mapa(gt, ancho, 0), a_mapa(gt, 0, 0)]


def dentro(p, esq):
    """¿El punto cae en el cuadrilátero (convexo) de ``esq``? El borde cuenta."""
    if len(esq) < 3:
        return False
    signo = 0
    for i, a in enumerate(esq):
        b = esq[(i + 1) % len(esq)]
        c = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(c) <= 1e-12:
            continue
        s = 1 if c > 0 else -1
        if signo and s != signo:
            return False
        signo = s
    return True


def caja(esq):
    xs, ys = [p[0] for p in esq], [p[1] for p in esq]
    return min(xs), min(ys), max(xs), max(ys)


def _fmt(v, dec=2):
    return ('%.*f' % (dec, v)).rstrip('0').rstrip('.') if abs(v) < 1e15 else '%g' % v


def describir(gt, ancho, alto):
    """«X 10 a 90, Y 20 a 60; píxel 0,2 × 0,2, girada 30°»."""
    import math
    x0, y0, x1, y1 = caja(esquinas_gt(gt, ancho, alto))
    lado_x = math.hypot(gt[1], gt[4])
    lado_y = math.hypot(gt[2], gt[5])
    giro = math.degrees(math.atan2(gt[4], gt[1]))
    texto = 'X %s a %s, Y %s a %s; píxel %s × %s' % (_fmt(x0), _fmt(x1), _fmt(y0), _fmt(y1),
                                                       _fmt(lado_x, 4), _fmt(lado_y, 4))
    if abs(giro) > 1e-9:
        texto += ', girada %.4g°' % giro
    return texto


def fuente(archivos):
    """De dónde sale la georreferencia, entre los archivos que GDAL leyó."""
    for a in archivos or ():
        ext = os.path.splitext(str(a))[1].lower()
        if ext == '.wld' or (len(ext) >= 3 and ext.endswith('w') and ext != '.raw'):
            return 'archivo de mundo %s' % os.path.basename(str(a))
    return 'georreferencia del archivo'


# ------------------------------------------------------------------ la copia geo
def nombre_copia(ruta):
    """«plano_georref.png» (o _georref2, 3…): nunca pisa nada, ni la imagen ni su
    archivo de mundo, puntos o .aux.xml (como IngeCAD)."""
    base, ext = os.path.splitext(str(ruta))
    for i in range(1, 1000):
        nueva = '%s%s%s%s' % (base, SUFIJO_COPIA, i if i > 1 else '', ext)
        vecinos = (nueva, SI.ruta_mundo(nueva), nueva + '.points', nueva + '.aux.xml')
        if not any(os.path.exists(v) for v in vecinos):
            return nueva
    raise OSError('demasiadas copias de esta imagen')


def destino_copia(elegida, original):
    """La ruta elegida en «Guardar como», con la extensión de la original (los mismos
    bytes con otra extensión confundirían a QGIS). Nunca la original misma."""
    elegida = os.path.expanduser(str(elegida))
    ext = os.path.splitext(str(original))[1]
    if os.path.splitext(elegida)[1].lower() != ext.lower():
        elegida += ext
    if os.path.realpath(elegida) == os.path.realpath(str(original)):
        raise OSError('la copia no puede ser la imagen original')
    if not os.path.isdir(os.path.dirname(os.path.abspath(elegida))):
        raise OSError('no existe la carpeta %s' % os.path.dirname(elegida))
    return elegida


def exportar(original, elegida, gt, wkt=''):
    """Copia ``original`` a ``elegida`` con su archivo de mundo (donde está hoy) y, con
    ``wkt``, su .aux.xml si no había uno. Devuelve lo escrito."""
    destino = destino_copia(elegida, original)
    shutil.copy2(str(original), destino)
    mundo = SI.ruta_mundo(destino)
    with open(mundo, 'w', encoding='ascii') as f:
        f.write(SI.texto_mundo(mundo_de_gt(gt)))
    hechos = [destino, mundo]
    aux = destino + '.aux.xml'
    if wkt and not os.path.exists(aux):
        with open(aux, 'w', encoding='utf-8') as f:
            f.write(SI.aux_xml(wkt))
        hechos.append(aux)
    return hechos


# ------------------------------------------------------------------ píxel <-> mapa (LIMPIARPLANO, 3.92.0)
def gt_como_qgis(gt):
    """La geotransformación con que QGIS dibuja la imagen: sin georreferencia, la
    de píxeles con la Y hacia abajo (0, 1, 0, 0, 0, -1), como su proveedor GDAL."""
    return (0.0, 1.0, 0.0, 0.0, 0.0, -1.0) if not georreferenciada(gt) else tuple(float(v) for v in gt)


def a_pixel(gt, x, y):
    """Punto del mapa -> (columna, fila) de la imagen (arriba a la izquierda = 0, 0)."""
    det = gt[1] * gt[5] - gt[2] * gt[4]
    dx, dy = x - gt[0], y - gt[3]
    return ((gt[5] * dx - gt[2] * dy) / det, (-gt[4] * dx + gt[1] * dy) / det)


def gt_ampliada(gt, esc):
    """La de una copia ×esc en el mismo lugar (píxeles esc veces más chicos)."""
    return (gt[0], gt[1] / esc, gt[2] / esc, gt[3], gt[4] / esc, gt[5] / esc)
