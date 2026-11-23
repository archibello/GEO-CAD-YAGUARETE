# -*- coding: utf-8 -*-
"""SOLTARIMAGEN en QGIS: una imagen arrastrada desde el explorador (3.88.0).

    Imagen soltada. Precise la esquina inferior izquierda:
    Precise el segundo punto (la distancia da el ancho y la escala) o escriba el ancho:
    Giro alrededor de la esquina (señale o escriba los grados; Intro = 0°):

Al soltar sobre QGIS un archivo de imagen SIN georreferencia (PNG, JPG, TIF,
BMP, GIF) arranca esta orden en vez de la carga de siempre (que la dejaría en
coordenadas de píxel). La imagen se ve semitransparente mientras se estira y
gira con el cursor; recién al dar el giro queda: una copia con su archivo de
mundo en «<proyecto>_imagenes», cargada como capa ráster arriba de todo.
Esc no deja nada. Una imagen ya georreferenciada (GeoTIFF, con su archivo de
mundo) entra como siempre. Las cuentas: soltar_imagen.py.
"""

import os

from qgis.core import QgsPointXY, QgsProject, QgsRasterLayer, QgsRectangle
from qgis.gui import QgsCustomDropHandler, QgsMapCanvasItem

from . import soltar_imagen as SI
from .commands import _DrawCommand

#: el archivo soltado, para la orden que arranca enseguida
_pendiente = []

PRIMERO = 'Imagen soltada. Precise la esquina inferior izquierda'
SEGUNDO = 'Precise el segundo punto (la distancia da el ancho y la escala) o escriba el ancho'
TERCERO = 'Giro alrededor de la esquina (señale o escriba los grados; Intro = 0°)'
SIN_IMAGEN = ('SOLTARIMAGEN: arrastre un archivo de imagen (PNG, JPG, TIF, BMP, GIF) '
              'desde el explorador y suéltelo sobre el mapa.')


def medida(ruta):
    """(ancho, alto) en píxeles, o None."""
    try:
        from qgis.PyQt.QtGui import QImageReader
        t = QImageReader(str(ruta)).size()
        if t.width() > 0 and t.height() > 0:
            return t.width(), t.height()
    except Exception:  # noqa: BLE001
        pass
    try:
        from osgeo import gdal
        ds = gdal.Open(str(ruta))
        if ds is not None:
            return ds.RasterXSize, ds.RasterYSize
    except Exception:  # noqa: BLE001
        pass
    return None


def georreferenciada(ruta):
    """¿Ya sabe dónde va? (GeoTIFF, archivo de mundo, puntos de control)."""
    try:
        from osgeo import gdal
        ds = gdal.Open(str(ruta))
        if ds is None:
            return False
        gt = ds.GetGeoTransform(can_return_null=True)
        if gt is not None and tuple(gt) != (0.0, 1.0, 0.0, 0.0, 0.0, 1.0):
            return True
        return bool(ds.GetGCPCount())
    except Exception:  # noqa: BLE001 -- sin GDAL: se ofrece ubicarla
        return False


# ------------------------------------------------------------------ la imagen en el mapa
class VistaImagen(QgsMapCanvasItem):
    """La imagen semitransparente en su lugar provisorio."""

    def __init__(self, canvas, ruta):
        super().__init__(canvas)
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtGui import QImage
        im = QImage(str(ruta))
        if not im.isNull() and max(im.width(), im.height()) > 1600:
            im = im.scaled(1600, 1600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.imagen = None if im.isNull() else im
        self.esq = []
        self.setZValue(5)

    def poner(self, esq):
        self.esq = list(esq or [])
        if len(self.esq) == 4:
            xs, ys = [p[0] for p in self.esq], [p[1] for p in self.esq]
            self.setRect(QgsRectangle(min(xs), min(ys), max(xs), max(ys)))
            self.show()
        else:
            self.hide()
        self.update()

    def paint(self, painter, option=None, widget=None):  # noqa: ARG002 -- Qt
        if self.imagen is None or len(self.esq) != 4:
            return
        from qgis.PyQt.QtGui import QPainter, QTransform
        o = self.pos()

        def pant(p):
            q = self.toCanvasCoordinates(QgsPointXY(p[0], p[1]))
            return q.x() - o.x(), q.y() - o.y()

        si, sd, ii = pant(self.esq[3]), pant(self.esq[2]), pant(self.esq[0])
        w, h = self.imagen.width(), self.imagen.height()
        t = QTransform((sd[0] - si[0]) / w, (sd[1] - si[1]) / w,
                       (ii[0] - si[0]) / h, (ii[1] - si[1]) / h, si[0], si[1])
        painter.save()
        try:
            painter.setOpacity(0.6)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.setTransform(t, True)
            painter.drawImage(0, 0, self.imagen)
        finally:
            painter.restore()


# ------------------------------------------------------------------ la orden
class SoltarImagenCommand(_DrawCommand):
    title = 'SOLTARIMAGEN'

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.ruta = _pendiente.pop() if _pendiente else None
        del _pendiente[:]
        self.tam = None
        self.ancho = None
        self.vista = None
        self.hecha = None

    def start(self):
        if self.ruta is None:
            self.cl.echo(SIN_IMAGEN)
            self.end()
            return
        self.tam = medida(self.ruta)
        if not self.tam:
            self.cl.echo('SOLTARIMAGEN: no se pudo leer la imagen %s.' % os.path.basename(self.ruta))
            self.end()
            return
        try:
            self.vista = VistaImagen(self.mgr.canvas, self.ruta)
            self.vista.hide()
        except Exception:  # noqa: BLE001 -- sin vista previa: queda el contorno
            self.vista = None
        self.prompt()

    def prompt(self):
        if not self.pts:
            self.cl.set_prompt(PRIMERO)
        elif self.ancho is None:
            self.cl.set_prompt(SEGUNDO)
        else:
            self.cl.set_prompt(TERCERO)

    def base(self):
        return self.pts[0] if self.pts else None

    def ref_direction(self):
        return None

    # -- lo que se ve
    def esquinas_con(self, cur):
        if self.tam is None or not self.pts or cur is None:
            return []
        p1 = (self.pts[0].x(), self.pts[0].y())
        c = (cur.x(), cur.y())
        if self.ancho is None:
            return SI.esquinas(p1, SI.ancho_de(p1, c), 0.0, *self.tam)
        giro = SI.angulo_de(p1, c) if SI.ancho_de(p1, c) > 1e-12 else 0.0
        return SI.esquinas(p1, self.ancho, giro, *self.tam)

    def preview(self, cur):
        e = self.esquinas_con(cur)
        if self.vista is not None:
            try:
                self.vista.poner(e)
            except Exception:  # noqa: BLE001
                pass
        if not e:
            return [], False, [], []
        return [QgsPointXY(*p) for p in e], True, [self.pts[0], cur], []

    # -- los pasos
    def on_point(self, p):
        if self.tam is None:
            return
        if not self.pts:
            self.pts.append(p)
            self._set_last(p)
            self.prompt()
            return
        p1 = (self.pts[0].x(), self.pts[0].y())
        d = SI.ancho_de(p1, (p.x(), p.y()))
        if self.ancho is None:
            if d <= 1e-12:
                self.cl.echo('El segundo punto tiene que ser distinto del primero.')
                return
            self.ancho = d
            self.prompt()
            return
        self.agregar(SI.angulo_de(p1, (p.x(), p.y())) if d > 1e-12 else 0.0)

    def on_text(self, text):
        if self.tam is None:
            return
        if self.pts and self.ancho is None:
            ancho = SI.leer_ancho(text)
            if ancho is not None:
                if ancho <= 0:
                    self.cl.echo('El ancho tiene que ser mayor que cero.')
                    return
                self.ancho = ancho
                self.prompt()
                return
        elif self.ancho is not None:
            giro = SI.leer_giro(text)
            if giro is not None:
                self.agregar(giro)
                return
        self._resolve_and_apply(text)

    def on_enter(self):
        if self.ancho is not None:
            self.agregar(0.0)
            return
        self.escape()

    def escape(self):
        if self.hecha is None and self.tam is not None:
            self.cl.echo('Imagen sin agregar.')
        self.end()

    def cleanup(self):
        v, self.vista = self.vista, None
        if v is not None:
            try:
                v.hide()
                self.mgr.canvas.scene().removeItem(v)
            except Exception:  # noqa: BLE001
                pass

    def agregar(self, giro):
        px, py = self.tam
        p1 = (self.pts[0].x(), self.pts[0].y())
        proyecto = QgsProject.instance()
        crs = self.mgr.canvas.mapSettings().destinationCrs()
        carpeta = SI.carpeta_destino(proyecto.fileName())
        try:
            copia = SI.copiar(self.ruta, carpeta, p1, self.ancho, giro, px, py, crs.toWkt())
        except Exception as e:  # noqa: BLE001 -- carpeta sin permiso, disco lleno
            self.cl.echo('SOLTARIMAGEN: no se pudo copiar la imagen (%s).' % e)
            self.end()
            return
        nombre = os.path.splitext(os.path.basename(copia))[0]
        capa = QgsRasterLayer(copia, nombre)
        if not capa.isValid():
            self.cl.echo('SOLTARIMAGEN: QGIS no pudo abrir la copia %s.' % copia)
            self.end()
            return
        capa.setCrs(crs)
        proyecto.addMapLayer(capa)
        self.hecha = capa
        giro_txt = ', girada %.4g°' % giro if abs(giro) > 1e-9 else ''
        self.cl.echo('Imagen agregada: capa "%s", %d × %d píxeles, %.4g × %.4g unidades%s '
                     '(copia con su archivo de mundo en %s; el original no se tocó).'
                     % (nombre, px, py, self.ancho, self.ancho * py / px, giro_txt, carpeta))
        if not proyecto.fileName():
            self.cl.echo('El proyecto no está guardado: la copia quedó fuera de su carpeta. '
                         'Si lleva el proyecto a otra computadora, lleve también esa imagen.')
        self.end()


# ------------------------------------------------------------------ el arrastre
class ManejadorSoltar(QgsCustomDropHandler):
    """Lo soltado sobre QGIS: una imagen sin georreferencia arranca SOLTARIMAGEN."""

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin

    def customUriProviderKey(self):  # noqa: N802 -- QGIS
        return 'geocad_soltar_imagen'

    def handleFileDrop(self, file):  # noqa: N802 -- QGIS
        try:
            if not SI.es_imagen(file) or not os.path.isfile(file) or georreferenciada(file):
                return False
            if self.plugin.mgr is None:
                return False
            _pendiente[:] = [file]
            self.plugin.run_command('SOLTARIMAGEN')
            return True
        except Exception:  # noqa: BLE001 -- ante la duda, QGIS la carga como siempre
            return False


_manejadores = []


def instalar(plugin):
    """Registra la orden y el manejador del arrastre."""
    from .commands import CommandSpec
    plugin.mgr.register(CommandSpec('SOLTARIMAGEN', ('SOLTARIMAGEN', 'DROPIMAGE', 'GEODROPIMAGE'),
                                    SoltarImagenCommand, 'interactive', 'SOLTARIMAGEN', None, False,
                                    'dibujo', 'Imagen arrastrada desde el explorador: esquina, '
                                    'ancho y giro'))
    quitar(plugin)
    h = ManejadorSoltar(plugin)
    try:
        plugin.iface.registerCustomDropHandler(h)
    except Exception:  # noqa: BLE001
        return
    _manejadores.append((plugin.iface, h))


def quitar(plugin=None):  # noqa: ARG001
    while _manejadores:
        iface, h = _manejadores.pop()
        try:
            iface.unregisterCustomDropHandler(h)
        except Exception:  # noqa: BLE001
            pass
