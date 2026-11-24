# -*- coding: utf-8 -*-
"""LIMPIARPLANO en QGIS (3.92.0), barra «Yaguá Imagenes».

    Designe la imagen del plano a limpiar (clic en la imagen):
    Zona de sello (tinta tenue): primera esquina, D deshace la última, Intro limpia:
    Esquina opuesta de la zona de sello:

El procedimiento de IngeCAD (limpiar_plano.py, 3.86.0): con la imagen activa
(o un clic en ella) se marcan, si hace falta, zonas de sello con dos esquinas
(ahí van umbrales suaves para la tinta tenue: sellos, lápiz, firmas); D
deshace la última; Intro limpia. Se hace la copia limpia en gris y al DOBLE
de resolución (así se leen los rumbos chicos), PNG con su archivo de mundo en
«<proyecto>_imagenes», y la capa pasa a usarla en el mismo lugar. El original
NUNCA se toca. Queda anotado en la capa (propiedad «geocad/limpieza», con las
zonas): al volver a limpiarla se parte otra vez del original y aparecen las
zonas de antes; O (Original) devuelve la capa a su archivo (en QGIS no hay U,
como en ASPECTOIMAGEN). Si la capa tenía aspecto (ASPECTOIMAGEN) se limpia el archivo
que usa ahora y esa marca se suelta, como en IngeCAD.

La receta es la de IngeCAD (nucleo/limpieza.py, sin scipy), en su versión sin
PIL (limpiar_arreglo: el Python de QGIS no trae PIL; medido contra la
referencia aprobada por Fernando).
"""

import json
import os
import time

from qgis.core import QgsCoordinateTransform, QgsGeometry, QgsPointXY, QgsProject

from .. import limpieza as L
from . import aspecto_qgis as AQ
from . import imagen_geo as IG
from . import soltar_imagen as SI
from .imagen_geo_qgis import _ElegirImagen, archivo_de_capa, esquinas_en_mapa, leer as leer_gdal

PROPIEDAD = 'geocad/limpieza'
SUFIJO = '_limpio'
PEDIDO = 'Designe la imagen del plano a limpiar (clic en la imagen)'
PEDIDO_ZONA = 'Zona de sello (tinta tenue): primera esquina, D deshace la última, Intro limpia'
PEDIDO_ZONA_LIMPIA = ('Zona de sello (tinta tenue): primera esquina, D deshace la última, O vuelve al '
                      'original, Intro limpia')
PEDIDO_ESQUINA = 'Esquina opuesta de la zona de sello'


# ------------------------------------------------------------------ la marca en la capa
def leer(capa):
    """(original, zonas) si la capa está limpia, o None."""
    try:
        d = json.loads(capa.customProperty(PROPIEDAD, '') or '')
        return str(d['original']), [tuple(int(c) for c in z) for z in d.get('zonas') or ()]
    except Exception:  # noqa: BLE001
        return None


def marcar(capa, original, zonas):
    capa.setCustomProperty(PROPIEDAD, json.dumps({'original': str(original),
                                                  'zonas': [list(z) for z in zonas]}))


# ------------------------------------------------------------------ los archivos
def limpiar_archivo(original, zonas=(), avance=None):
    """(gris limpio ×2, alfa ×2 o None) de un archivo; L.LimpiezaError si no se lee."""
    try:
        rgba = AQ.abrir(original)
    except Exception as e:  # noqa: BLE001
        raise L.LimpiezaError(str(e)) from e
    return L.limpiar_arreglo(rgba, zonas, avance=avance)


def guardar(gris, alfa, ruta):
    """La copia limpia como PNG: en gris, o gris con transparencia si el original la tenía."""
    from qgis.PyQt.QtGui import QImage
    import numpy as np
    h, w = gris.shape
    if alfa is None:
        im = QImage(np.ascontiguousarray(gris).tobytes(), w, h, w, QImage.Format.Format_Grayscale8).copy()
    else:
        rgba = np.empty((h, w, 4), np.uint8)
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = gris
        rgba[..., 3] = alfa
        im = AQ.a_qimage(rgba)
    if not im.save(str(ruta), 'PNG', 70):
        raise OSError('no se pudo escribir %s' % ruta)


def usar_copia(capa, ruta):
    """La capa pasa a la copia limpia, con el gris tal cual (sin estirar)."""
    from qgis.core import QgsSingleBandGrayRenderer
    AQ.usar_archivo(capa, ruta)
    dp = capa.dataProvider()
    if dp is not None and dp.bandCount() == 1:
        capa.setRenderer(QgsSingleBandGrayRenderer(dp, 1))      # sin contraste: 0 negro, 255 blanco
        capa.triggerRepaint()


# ------------------------------------------------------------------ la orden
class LimpiarPlanoCommand(_ElegirImagen):
    title = 'LIMPIARPLANO'
    PEDIDO = PEDIDO

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.capa = None
        self.zonas = []            # en píxeles del ORIGINAL (arriba a la izquierda = 0, 0)
        self.limpia = False
        self.esquina = None        # primera esquina de la zona en curso (mapa)

    def prompt(self):
        if self.capa is None:
            self.cl.set_prompt(PEDIDO)
        else:
            self.cl.set_prompt(PEDIDO_ESQUINA if self.esquina is not None
                               else PEDIDO_ZONA_LIMPIA if self.limpia else PEDIDO_ZONA)

    def base(self):
        return self.esquina

    # -- elegir la imagen
    def con_capa(self, capa):
        marca = leer(capa)
        original = marca[0] if marca else archivo_de_capa(capa)
        if not original or not os.path.isfile(original):
            self.cl.echo('LIMPIARPLANO: no se encuentra el archivo de la imagen (%s).' % original)
            self.end()
            return
        datos = leer_gdal(original)
        tam = AQ.tamano(original) or (datos[1:3] if datos else None)
        if not tam:
            self.cl.echo('LIMPIARPLANO: no se puede leer %s.' % os.path.basename(original))
            self.end()
            return
        self.capa, self.original, self.tam = capa, original, tuple(tam)
        self.limpia = marca is not None
        self.gt = IG.gt_como_qgis(datos[0] if datos else None)
        self.zonas = list(marca[1]) if marca else []
        if marca:
            self.cl.echo('La imagen ya está limpia: se rehace desde el original (%s)%s'
                         % (os.path.basename(original), ' con sus %d zonas de sello.' % len(self.zonas)
                            if self.zonas else '.'))
        self.prompt()

    # -- píxeles <-> mapa
    def _a_capa(self, p):
        destino = self.mgr.canvas.mapSettings().destinationCrs()
        crs = self.capa.crs()
        if crs.isValid() and destino.isValid() and crs != destino:
            p = QgsCoordinateTransform(destino, crs, QgsProject.instance()).transform(p)
        return p

    def _a_mapa(self, x, y):
        destino = self.mgr.canvas.mapSettings().destinationCrs()
        p = QgsPointXY(*IG.a_mapa(self.gt, x, y))
        crs = self.capa.crs()
        if crs.isValid() and destino.isValid() and crs != destino:
            p = QgsCoordinateTransform(crs, destino, QgsProject.instance()).transform(p)
        return p

    def _zona(self, a, b):
        pa, pb = self._a_capa(a), self._a_capa(b)
        x0, y0 = IG.a_pixel(self.gt, pa.x(), pa.y())
        x1, y1 = IG.a_pixel(self.gt, pb.x(), pb.y())
        return L._zona((x0, y0, x1, y1), self.tam)

    def _marco(self, z):
        x0, y0, x1, y1 = z
        return [self._a_mapa(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    # -- lo que se ve
    def preview(self, cur):
        if self.capa is None:
            return super().preview(cur)
        if self.esquina is None or cur is None:
            return [], False, [], []
        z = self._zona(self.esquina, cur)
        return (self._marco(z), True, [], []) if z else ([], False, [], [])

    def preview_geoms(self, cur):  # noqa: ARG002
        if self.capa is None:
            return None
        geoms = [QgsGeometry.fromPolylineXY(m + m[:1]) for m in (self._marco(z) for z in self.zonas)]
        esq = esquinas_en_mapa(self.capa, self.mgr.canvas)
        if esq:
            pts = [QgsPointXY(*p) for p in esq]
            geoms.append(QgsGeometry.fromPolylineXY(pts + pts[:1]))
        return geoms

    # -- los pasos
    def on_point(self, p):
        if self.capa is None:
            super().on_point(p)
            return
        if self.esquina is None:
            self.esquina = p
            self.prompt()
            return
        zona = self._zona(self.esquina, p)
        self.esquina = None
        if zona is None:
            self.cl.echo('La zona queda fuera de la imagen: no se agrega.')
        else:
            self.zonas.append(zona)
            self.cl.echo('Zona de sello %d: %d × %d píxeles.' % (len(self.zonas), zona[2] - zona[0],
                                                                 zona[3] - zona[1]))
        self.prompt()

    def on_text(self, text):
        t = text.strip().upper().lstrip('_')
        if self.capa is not None and self.limpia and t in ('O', 'ORIGINAL'):
            # en QGIS no hay U: la capa vuelve a su archivo original (decidido con Fernando
            # para ASPECTOIMAGEN, 23/11/2026; las copias quedan en el disco)
            capa = self.capa
            AQ.usar_archivo(capa, self.original)
            capa.removeCustomProperty(PROPIEDAD)
            self.cl.echo('La imagen vuelve a su original: %s (las copias quedan en el disco).'
                         % self.original)
            self.end()
            return
        if self.capa is not None and t in ('D', 'U', 'DESHACER', 'UNDO'):
            if self.esquina is not None:
                self.esquina = None
            elif self.zonas:
                self.zonas.pop()
                self.cl.echo('Zona de sello quitada; quedan %d.' % len(self.zonas))
            else:
                self.cl.echo('No hay zonas de sello.')
            self.prompt()
            return
        self._resolve_and_apply(text)

    def on_enter(self):
        if self.capa is None:
            self.cl.echo('LIMPIARPLANO cancelado.')
            self.end()
            return
        self.esquina = None                       # Intro a mitad de una zona: se descarta
        capa = self.capa
        self.end()
        self.limpiar(capa)

    def escape(self):
        self.cl.echo('LIMPIARPLANO cancelado.')
        self.end()

    # -- limpiar
    def limpiar(self, capa):
        original, zonas = self.original, list(self.zonas)
        proyecto = QgsProject.instance()
        carpeta = SI.carpeta_destino(proyecto.fileName())
        prog = AQ.Progreso(self.mgr.iface.mainWindow(), 'LIMPIARPLANO', self.tam[0] * self.tam[1] / 1e6)
        t0 = time.monotonic()
        gt = self.gt
        wkt = capa.crs().toWkt() if capa.crs().isValid() else ''
        try:
            hecho = [0.0]
            gris, alfa = prog.trabajo('1/3  Limpiando el plano',
                                      lambda: limpiar_archivo(original, zonas, lambda f: hecho.__setitem__(0, f)),
                                      0.0, 0.8, 'limpiar', hecho)
            os.makedirs(carpeta, exist_ok=True)
            copia = AQ.nombre_copia(carpeta, original, SUFIJO)

            def escribir():
                guardar(gris, alfa, copia)
                with open(SI.ruta_mundo(copia), 'w', encoding='ascii') as f:
                    f.write(SI.texto_mundo(IG.mundo_de_gt(IG.gt_ampliada(gt, L.ESCALA))))
                if wkt:
                    with open(copia + '.aux.xml', 'w', encoding='utf-8') as f:
                        f.write(SI.aux_xml(wkt))
            prog.trabajo('2/3  Guardando la copia limpia', escribir, 0.8, 0.95, 'guardar')
            tam = (gris.shape[1], gris.shape[0])
            del gris, alfa
            prog.etapa(0.97, '3/3  Actualizando el mapa')
            usar_copia(capa, copia)
            capa.removeCustomProperty(AQ.PROPIEDAD)       # el aspecto ya no vale sobre la copia limpia
            marcar(capa, original, zonas)
        except (L.LimpiezaError, AQ.A.AspectoError, OSError, MemoryError) as e:
            prog.cerrar()
            self.cl.echo('LIMPIARPLANO: no se pudo limpiar la imagen (%s).' % e)
            return None
        prog.cerrar()
        self.cl.echo('Plano limpio (%d × %d píxeles, %s%.0f s): %s. El original no se toca: '
                     'LIMPIARPLANO y O lo devuelve.'
                     % (tam[0], tam[1], '%d zonas de sello, ' % len(zonas) if zonas else '',
                        time.monotonic() - t0, copia))
        if not proyecto.fileName():
            self.cl.echo('El proyecto no está guardado: la copia quedó fuera de su carpeta. Si lleva '
                         'el proyecto a otra computadora, lleve también esa imagen.')
        return capa


def instalar(plugin):
    from .commands import CommandSpec
    plugin.mgr.register(CommandSpec('LIMPIARPLANO', ('LIMPIARPLANO', 'GEOLIMPIARPLANO', 'CLEANSCAN'),
                                    LimpiarPlanoCommand, 'interactive', 'LIMPIARPLANO', None, False,
                                    'dibujo', 'Limpiar un plano antiguo escaneado (manchas, pliegues) '
                                    'en una copia al doble de resolución'))
