# -*- coding: utf-8 -*-
"""INSERTARGEO y EXPORTARGEO en QGIS (3.90.0), barra «Yaguá Imagenes».

    INSERTARGEO: ventana de abrir; la imagen georreferenciada entra en su lugar.
    EXPORTARGEO: Designe la imagen a exportar (clic en la imagen):

Con una capa ráster activa (de un archivo), EXPORTARGEO la toma enseguida,
como la imagen elegida antes en IngeCAD. La imagen bajo el cursor se resalta
con su marco (_ElegirImagen, que usan también ASPECTOIMAGEN, LIMPIARPLANO y
GEORREF). GEORREF: desde la 3.93.0 es el de IngeCAD (georref_qgis.py); acá
queda abrir_georreferenciador(), que usa su botón «Abrir en el
Georreferenciador de QGIS»: le entrega la imagen como si se la soltaran
encima y se abre ahí con sus puntos («<imagen>.points»). Las cuentas:
imagen_geo.py.
"""

import os

from qgis.core import QgsCoordinateTransform, QgsPointXY, QgsProject, QgsRasterLayer

from . import imagen_geo as IG
from .commands import _DrawCommand

VENTANA_GEORREF = 'QgsGeorefPluginGuiBase'
ACCION_GEORREF = 'mActionShowGeoreferencer'


# ------------------------------------------------------------------ ventanas de archivo
def pedir_archivo(parent, titulo, filtro, inicio=''):
    """La ventana de abrir de QGIS (las pruebas la reemplazan)."""
    from qgis.PyQt.QtWidgets import QFileDialog
    ruta, _f = QFileDialog.getOpenFileName(parent, titulo, inicio, filtro)
    return ruta or ''


def pedir_guardar(parent, titulo, sugerido, filtro):
    from qgis.PyQt.QtWidgets import QFileDialog
    ruta, _f = QFileDialog.getSaveFileName(parent, titulo, sugerido, filtro)
    return ruta or ''


def _carpeta_inicial():
    from qgis.core import QgsSettings
    return QgsSettings().value('geocad/imagenes_carpeta', '') or os.path.dirname(
        QgsProject.instance().fileName() or '') or os.path.expanduser('~')


def _recordar_carpeta(ruta):
    try:
        from qgis.core import QgsSettings
        QgsSettings().setValue('geocad/imagenes_carpeta', os.path.dirname(str(ruta)))
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ las imágenes
def leer(ruta):
    """(geotransformación, ancho, alto, archivos leídos, PCT) con GDAL, o None."""
    try:
        from osgeo import gdal
        ds = gdal.Open(str(ruta))
        if ds is None:
            return None
        gt = ds.GetGeoTransform(can_return_null=True)
        return gt, ds.RasterXSize, ds.RasterYSize, list(ds.GetFileList() or ()), ds.GetGCPCount()
    except Exception:  # noqa: BLE001
        return None


def archivo_de_capa(capa):
    """El archivo de una capa ráster de GDAL, o None (WMS, XYZ, memoria)."""
    if not isinstance(capa, QgsRasterLayer) or capa.providerType() != 'gdal':
        return None
    ruta = capa.source().split('|')[0]
    return ruta if os.path.isfile(ruta) else None


def esquinas_en_mapa(capa, canvas):
    """Las 4 esquinas de la imagen de ``capa`` en el sistema del mapa, o []."""
    ruta = archivo_de_capa(capa)
    datos = leer(ruta) if ruta else None
    if datos is None or datos[0] is None:
        return []
    esq = IG.esquinas_gt(datos[0], datos[1], datos[2])
    destino = canvas.mapSettings().destinationCrs()
    if capa.crs().isValid() and destino.isValid() and capa.crs() != destino:
        try:
            ct = QgsCoordinateTransform(capa.crs(), destino, QgsProject.instance())
            esq = [(q.x(), q.y()) for q in (ct.transform(QgsPointXY(*p)) for p in esq)]
        except Exception:  # noqa: BLE001
            return []
    return esq


def capa_en(canvas, p):
    """La capa ráster (de un archivo) de más arriba que tiene ``p`` adentro."""
    for capa in canvas.layers():
        if archivo_de_capa(capa) is None:
            continue
        if IG.dentro((p.x(), p.y()), esquinas_en_mapa(capa, canvas)):
            return capa
    return None


def _crs_txt(crs):
    return crs.authid() or crs.description() or 'sin código'


# ------------------------------------------------------------------ INSERTARGEO
def insertar(plugin, ruta):
    """La imagen georreferenciada en su lugar (el archivo tal cual); la capa o None."""
    cl = plugin.cmdline
    nombre = os.path.basename(str(ruta))
    datos = leer(ruta)
    if datos is None:
        cl.echo('INSERTARGEO: no se puede leer %s como imagen.' % nombre)
        return None
    gt, ancho, alto, archivos, pct = datos
    if not IG.georreferenciada(gt, pct):
        cl.echo('INSERTARGEO: %s no tiene georreferencia (ni archivo de mundo .pgw / .jgw / .tfw '
                '/ .wld, ni GeoTIFF). Ubíquela con PEGARIMAGEN o arrastrándola (SOLTARIMAGEN), o '
                'ajústela con GEORREF (Georreferenciador).' % nombre)
        return None
    capa = QgsRasterLayer(str(ruta), os.path.splitext(nombre)[0])
    if not capa.isValid():
        cl.echo('INSERTARGEO: QGIS no pudo abrir %s.' % nombre)
        return None
    canvas = plugin.iface.mapCanvas()
    destino = canvas.mapSettings().destinationCrs()
    sin_crs = not capa.crs().isValid()
    if sin_crs:
        capa.setCrs(destino)
    QgsProject.instance().addMapLayer(capa)
    con_gt = IG.georreferenciada(gt)
    cl.echo('Imagen %s insertada en su lugar (%s): %s.' % (
        nombre, IG.fuente(archivos) if con_gt else 'puntos de control',
        IG.describir(gt, ancho, alto) if con_gt else '%d × %d píxeles' % (ancho, alto)))
    if sin_crs:
        cl.echo('La imagen no dice su sistema de coordenadas: se toma el del mapa (%s).'
                % _crs_txt(destino))
    elif destino.isValid() and capa.crs() != destino:
        cl.echo('Atención: la imagen está en %s y el mapa en %s; QGIS la reproyecta al vuelo.'
                % (_crs_txt(capa.crs()), _crs_txt(destino)))
    try:
        canvas.setExtent(canvas.mapSettings().layerExtentToOutputExtent(capa, capa.extent()))
        canvas.refresh()
    except Exception:  # noqa: BLE001 -- sin zoom, igual quedó
        pass
    return capa


def insertar_geo(plugin):
    """INSERTARGEO: la ventana de abrir y la imagen en su lugar."""
    ruta = pedir_archivo(plugin.iface.mainWindow(), 'Insertar imagen georreferenciada',
                         IG.FILTRO_IMAGENES, _carpeta_inicial())
    if not ruta:
        return None
    _recordar_carpeta(ruta)
    return insertar(plugin, ruta)


# ------------------------------------------------------------------ elegir una imagen del mapa
class _ElegirImagen(_DrawCommand):
    """Una capa ráster: la activa, o un clic en el mapa (la de más arriba)."""

    PEDIDO = ''

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.terminada = False

    def start(self):
        activa = self.mgr.iface.activeLayer()
        if archivo_de_capa(activa) is not None:
            self.con_capa(activa)
            return
        self.prompt()

    def prompt(self):
        self.cl.set_prompt(self.PEDIDO)

    def base(self):
        return None

    def preview(self, cur):
        capa = capa_en(self.mgr.canvas, cur) if cur is not None else None
        esq = esquinas_en_mapa(capa, self.mgr.canvas) if capa is not None else []
        if not esq:
            return [], False, [], []
        return [QgsPointXY(*p) for p in esq], True, [], []

    def on_point(self, p):
        capa = capa_en(self.mgr.canvas, p)
        if capa is None:
            self.cl.echo('Ahí no hay una imagen (una capa ráster de un archivo).')
            self.prompt()
            return
        self.con_capa(capa)

    def on_text(self, text):
        self._resolve_and_apply(text)

    def on_enter(self):
        self.escape()

    def escape(self):
        self.end()

    def con_capa(self, capa):
        raise NotImplementedError


# ------------------------------------------------------------------ EXPORTARGEO
class ExportarGeoCommand(_ElegirImagen):
    title = 'EXPORTARGEO'
    PEDIDO = 'Designe la imagen a exportar con su georreferencia (clic en la imagen)'

    def con_capa(self, capa):
        original = archivo_de_capa(capa)
        datos = leer(original)
        if datos is None or not IG.georreferenciada(datos[0]):
            self.cl.echo('EXPORTARGEO: %s no tiene georreferencia que exportar.' % capa.name())
            self.end()
            return
        try:
            sugerido = IG.nombre_copia(original)
        except OSError:
            sugerido = original
        ext = os.path.splitext(original)[1]
        ruta = pedir_guardar(self.mgr.iface.mainWindow(), 'Guardar copia geo como', sugerido,
                             'Imagen (*%s);;Todos los archivos (*)' % ext)
        if not ruta:
            self.cl.echo('EXPORTARGEO cancelado.')
            self.end()
            return
        crs = capa.crs()
        try:
            hechos = IG.exportar(original, ruta, datos[0], crs.toWkt() if crs.isValid() else '')
        except OSError as e:
            self.cl.echo('EXPORTARGEO: no se pudo exportar (%s).' % e)
            self.end()
            return
        self.cl.echo('Copia geo: %s (%s). Se abre en su lugar en QGIS e IngeCAD (INSERTARGEO); '
                     'el mapa no cambia.' % (hechos[0], ' y '.join(os.path.basename(h) for h in hechos[1:])))
        self.end()


# ------------------------------------------------------------------ GEORREF
def ventana_georref():
    from qgis.PyQt.QtWidgets import QApplication
    for w in QApplication.topLevelWidgets():
        if w.objectName() == VENTANA_GEORREF:
            return w
    return None


def abrir_georreferenciador(iface, ruta):
    """Abre el Georreferenciador de QGIS y le suelta ``ruta`` encima (se abre ahí con sus
    puntos). '' si anduvo; si no, por qué."""
    from qgis.PyQt.QtCore import QMimeData, QPointF, Qt, QUrl
    from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent
    from qgis.PyQt.QtWidgets import QAction, QApplication
    accion = iface.mainWindow().findChild(QAction, ACCION_GEORREF)
    if accion is None:
        return 'esta QGIS no tiene el Georreferenciador (Capa > Georreferenciador)'
    accion.trigger()
    QApplication.processEvents()
    w = ventana_georref()
    if w is None or not w.acceptDrops():
        return 'no se encontró la ventana del Georreferenciador'
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(ruta))])
    centro = w.rect().center()
    entra = QDragEnterEvent(centro, Qt.DropAction.CopyAction, datos, Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, entra)
    if not entra.isAccepted():
        return 'el Georreferenciador no aceptó la imagen'
    suelta = QDropEvent(QPointF(centro), Qt.DropAction.CopyAction, datos, Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, suelta)
    w.raise_()
    w.activateWindow()
    return ''


# ------------------------------------------------------------------ registrar
def instalar(plugin):
    from .commands import CommandSpec
    mgr = plugin.mgr
    mgr.register(CommandSpec('INSERTARGEO', ('INSERTARGEO', 'GEOINSERTARIMAGEN'),
                             lambda: insertar_geo(plugin), title='INSERTARGEO', group='dibujo',
                             description='Imagen georreferenciada (archivo de mundo o GeoTIFF) '
                                         'en su lugar'))
    mgr.register(CommandSpec('EXPORTARGEO', ('EXPORTARGEO',), ExportarGeoCommand, 'interactive',
                             'EXPORTARGEO', None, False, 'dibujo',
                             'Copia de una imagen con su archivo de mundo, donde está hoy'))
    # GEORREF: el de IngeCAD desde la 3.93.0 (georref_qgis.py)
