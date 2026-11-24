# -*- coding: utf-8 -*-
"""ASPECTOIMAGEN en QGIS (3.91.0), barra «Yaguá Imagenes».

    Designe la imagen para cambiar su aspecto (clic en la imagen):

El procedimiento de IngeCAD (aspecto.py, 3.31.0 a 3.84.0): con la imagen
activa (o un clic en ella; el cursor encima la resalta) se abre la ventana
«Aspecto de la imagen» (aspecto_ui_qgis.py, la misma de IngeCAD): fondo
transparente y blanco que se borra, líneas como están / en negativo / de un
color, opacidad, contraste, limpiar manchas, la vista previa con zoom, y
«Volver al original», «Valores iniciales», «Entregar imagen final...».
La cuenta es la misma de IngeCAD (nucleo/aspecto_cuentas.py, sólo numpy); en
QGIS las imágenes se abren y se guardan con QImage (su Python no trae PIL).

En QGIS una imagen es una capa ráster: se guarda una COPIA PNG con su archivo
de mundo y su .aux.xml en «<proyecto>_imagenes» y la capa pasa a usarla (el
mismo nombre y lugar en el panel). El original NUNCA se toca. Los valores y el
original quedan en la capa (propiedad «geocad/aspecto», se guarda con el
proyecto): la ventana vuelve a abrir con ellos y se rehace siempre desde el
original. Decidido con Fernando (23/11/2026): sin «Fondo blanco» en QGIS
(la imagen final ya trae el papel blanco) y sin U: «Volver al original».

Marca vieja (3.94.1, Fernando, 24/11/2026): GEORREF hace su propia copia con
otro archivo de mundo (y, si la rehace, otro tamaño), pero la marca seguía en
la capa; «Entregar imagen final» rehacía el original de antes de ajustarla y
la imagen volvía a su lugar viejo. Si el archivo de la capa no tiene el tamaño
y la georreferencia del original marcado, no es una copia de ASPECTOIMAGEN: la
marca se descarta y la imagen de hoy pasa a ser el original (marca_vigente).
"""

import json
import os

from .. import aspecto_cuentas as A
from . import soltar_imagen as SI
from .imagen_geo_qgis import _ElegirImagen, archivo_de_capa, leer as leer_gdal

PROPIEDAD = 'geocad/aspecto'
SUFIJO = '_aspecto'
#: los últimos usados en la sesión, para una imagen que todavía no tiene aspecto
_ultimos = [dict(A.DEFECTO)]


# ------------------------------------------------------------------ imágenes <-> numpy
def _qimage():
    from qgis.PyQt.QtGui import QImage, QImageReader
    try:
        QImageReader.setAllocationLimit(0)      # los escaneos grandes son nuestros (Qt 6)
    except Exception:  # noqa: BLE001
        pass
    return QImage, QImageReader


def a_arreglo(qimg):
    """QImage -> arreglo RGBA (alto x ancho x 4, uint8)."""
    import numpy as np
    QImage, _r = _qimage()
    im = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = im.width(), im.height()
    ptr = im.constBits()
    ptr.setsize(im.sizeInBytes())
    fila = im.bytesPerLine()
    return np.frombuffer(ptr, np.uint8).reshape(h, fila)[:, :w * 4].reshape(h, w, 4).copy()


def a_qimage(a):
    """Arreglo RGBA -> QImage (con sus propios datos)."""
    import numpy as np
    QImage, _r = _qimage()
    a = np.ascontiguousarray(a, dtype=np.uint8)
    h, w = a.shape[:2]
    return QImage(a.tobytes(), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


def abrir(ruta):
    """El arreglo RGBA de una imagen; A.AspectoError si no se puede leer."""
    _q, QImageReader = _qimage()
    lector = QImageReader(str(ruta))
    lector.setAutoTransform(False)
    im = lector.read()
    if im.isNull():
        raise A.AspectoError('no se puede leer %s (%s)' % (os.path.basename(str(ruta)),
                                                            lector.errorString()))
    return a_arreglo(im)


def tamano(ruta):
    """(ancho, alto) sin leer la imagen, o None."""
    _q, QImageReader = _qimage()
    t = QImageReader(str(ruta)).size()
    return (t.width(), t.height()) if t.width() > 0 and t.height() > 0 else None


def redimensionar(a, ancho, alto):
    from qgis.PyQt.QtCore import Qt
    im = a_qimage(a).scaled(int(ancho), int(alto), Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    return a_arreglo(im)


def reducida(a, lado=420):
    """Una copia chica para la vista previa (la cuenta es la misma)."""
    h, w = a.shape[:2]
    if max(w, h) <= lado:
        return a.copy()
    t = lado / float(max(w, h))
    return redimensionar(a, max(1, round(w * t)), max(1, round(h * t)))


def invisible(a):
    """¿No queda ningún píxel visible?"""
    return int(a[..., 3].max()) == 0 if a.size else True


def guardar_png(a, ruta, opaca=False):
    """La copia como PNG (la imagen final, sin canal alfa)."""
    QImage, _r = _qimage()
    im = a_qimage(a)
    if opaca:
        im = im.convertToFormat(QImage.Format.Format_RGB888)
    if not im.save(str(ruta), 'PNG', 70):        # 70: compresión liviana, como IngeCAD
        raise OSError('no se pudo escribir %s' % ruta)


# ------------------------------------------------------------------ la marca en la capa
def leer(capa):
    """(valores, original) si la capa tiene aspecto de GeoCAD, o None."""
    try:
        d = json.loads(capa.customProperty(PROPIEDAD, '') or '')
        return A.normalizar(d['valores']), str(d['original'])
    except Exception:  # noqa: BLE001
        return None


def marcar(capa, valores, original):
    if valores is None:
        capa.removeCustomProperty(PROPIEDAD)
    else:
        capa.setCustomProperty(PROPIEDAD, json.dumps(
            {'valores': A.normalizar(valores), 'original': str(original)}, sort_keys=True))


def _mismo_lugar(a, b):
    """¿Dos lecturas de GDAL con el mismo tamaño y la misma geotransformación?"""
    if a[1:3] != b[1:3] or (a[0] is None) != (b[0] is None):
        return False
    if a[0] is None:
        return True
    return all(abs(float(x) - float(y)) <= 1e-9 * max(1.0, abs(float(x)), abs(float(y)))
               for x, y in zip(a[0], b[0]))


def marca_vigente(capa, original):
    """¿La capa sigue usando una copia de ASPECTOIMAGEN hecha desde ``original``?
    No, si otra orden (GEORREF) le cambió el archivo por uno de otro tamaño o en
    otro lugar. Si GDAL no lee alguno de los dos, se deja la marca como está."""
    actual = archivo_de_capa(capa)
    if not actual or os.path.abspath(actual) == os.path.abspath(str(original)):
        return True
    a, b = leer_gdal(actual), leer_gdal(original)
    if a is None or b is None:
        return True
    return _mismo_lugar(a, b)


def nombre_copia(carpeta, original, sufijo=SUFIJO):
    """<original>_aspecto.png en ``carpeta``, sin pisar otra (…_2, …_3) ni su archivo de mundo."""
    base = os.path.splitext(os.path.basename(str(original)))[0]
    ruta = os.path.join(str(carpeta), '%s%s.png' % (base, sufijo))
    n = 2
    while os.path.exists(ruta) or os.path.exists(SI.ruta_mundo(ruta)):
        ruta = os.path.join(str(carpeta), '%s%s_%d.png' % (base, sufijo, n))
        n += 1
    return ruta


def georreferenciar_copia(copia, original, crs):
    """El archivo de mundo de la copia (donde está hoy el original) y su .aux.xml."""
    from .imagen_geo import georreferenciada, mundo_de_gt
    datos = leer_gdal(original)
    if datos is None or not georreferenciada(datos[0]):
        return
    with open(SI.ruta_mundo(copia), 'w', encoding='ascii') as f:
        f.write(SI.texto_mundo(mundo_de_gt(datos[0])))
    if crs is not None and crs.isValid():
        with open(copia + '.aux.xml', 'w', encoding='utf-8') as f:
            f.write(SI.aux_xml(crs.toWkt()))


def usar_archivo(capa, ruta):
    """La capa pasa a usar ``ruta`` (mismo nombre y lugar en el panel), dibujada como
    QGIS dibuja ese archivo recién abierto (una copia RGBA, con su transparencia)."""
    from qgis.core import QgsDataProvider, QgsRasterLayer
    crs = capa.crs()
    capa.setDataSource(str(ruta), capa.name(), 'gdal', QgsDataProvider.ProviderOptions())
    if crs.isValid() and not capa.crs().isValid():
        capa.setCrs(crs)
    nueva = QgsRasterLayer(str(ruta), 'tmp')
    if nueva.isValid() and nueva.renderer() is not None:
        capa.setRenderer(nueva.renderer().clone())
    capa.triggerRepaint()


# ------------------------------------------------------------------ la ventana
def ventana(parent, original, valores, con_aspecto):
    """{"accion": "aceptar" | "final" | "original", "valores"} o None (Cancelar). Las
    pruebas la reemplazan."""
    from . import aspecto_ui_qgis
    return aspecto_ui_qgis.ventana(parent, original, valores, con_aspecto)


class Progreso:
    """La barra de avance de ASPECTOIMAGEN y LIMPIARPLANO (3.92.1).

    Fernando (23/11/2026), con un plano grande: el sistema mostraba «QGIS no
    responde» y no se entendía si la orden andaba o QGIS se había colgado. La
    barra aparece desde el primer momento y la cuenta corre en OTRO hilo
    (numpy suelta el intérprete mientras cuenta): QGIS sigue atendiendo la
    pantalla, la barra avanza con el porcentaje, la etapa y los segundos.
    Lo que toca capas o la ventana se hace después, en el hilo de QGIS.
    El porcentaje sale de lo que la cuenta dice que lleva (``hecho``) o, entre
    un aviso y otro, del tiempo estimado por megapíxel (se ajusta con lo medido)."""

    #: segundos por megapíxel de cada etapa (se ajustan con lo medido en la sesión)
    ritmo = {'abrir': 0.05, 'aspecto': 0.25, 'limpiar': 2.0, 'guardar': 0.15}

    def __init__(self, parent, titulo, megapixeles=0.0):
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtWidgets import QApplication, QProgressDialog
        self.titulo, self.mp = titulo, float(megapixeles)
        self.d = QProgressDialog(titulo, None, 0, 1000, parent)
        self.d.setWindowTitle(titulo)
        self.d.setWindowModality(Qt.WindowModality.WindowModal)
        self.d.setMinimumDuration(0)              # desde el primer momento
        self.d.setAutoClose(False)
        self.d.setAutoReset(False)
        self.d.setMinimumWidth(460)
        self.d.setValue(0)
        self.d.show()
        QApplication.processEvents()
        import time
        self.t0 = time.monotonic()
        self.valores = []                         # lo que mostró la barra (las pruebas lo miran)

    def _mostrar(self, fraccion, texto):
        import time
        v = int(round(1000 * max(0.0, min(1.0, fraccion))))
        if self.valores and v < self.valores[-1]:
            v = self.valores[-1]                  # nunca para atrás
        self.valores.append(v)
        self.d.setValue(v)
        self.d.setLabelText('%s\n%d %%  ·  %d s' % (texto, v // 10, time.monotonic() - self.t0))

    def trabajo(self, texto, funcion, desde, hasta, etapa=None, hecho=None):
        """Corre ``funcion()`` en otro hilo mientras la barra va de ``desde`` a ``hasta``
        (0 a 1); devuelve lo que devuelve (o levanta lo que levanta)."""
        import threading
        import time
        from qgis.PyQt.QtCore import QEventLoop
        from qgis.PyQt.QtWidgets import QApplication
        estimado = max(1.0, self.ritmo.get(etapa, 0.5) * self.mp)
        salida = {}

        def correr():
            try:
                salida['r'] = funcion()
            except BaseException as e:  # noqa: BLE001 -- se levanta en el hilo de QGIS
                salida['e'] = e

        hilo = threading.Thread(target=correr, name='geocad-' + self.titulo, daemon=True)
        t0 = time.monotonic()
        hilo.start()
        while hilo.is_alive():
            pasado = time.monotonic() - t0
            f = min(0.97, pasado / estimado)
            if hecho is not None and hecho[0] > 0:
                f = max(float(hecho[0]), min(f, 0.97))
            self._mostrar(desde + (hasta - desde) * f, texto)
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            hilo.join(0.05)
        if etapa and self.mp > 0.5:
            self.ritmo[etapa] = (time.monotonic() - t0) / self.mp
        self._mostrar(hasta, texto)
        if 'e' in salida:
            raise salida['e']
        return salida.get('r')

    def etapa(self, fraccion, texto):
        """Un paso corto en el hilo de QGIS (actualizar el mapa)."""
        from qgis.PyQt.QtWidgets import QApplication
        self._mostrar(fraccion, texto)
        QApplication.processEvents()

    def cerrar(self):
        if self.d is not None:
            self.d.close()
            self.d.deleteLater()
            self.d = None


def megapixeles(ruta):
    t = tamano(ruta)
    return t[0] * t[1] / 1e6 if t else 0.0


# ------------------------------------------------------------------ la orden
class AspectoImagenCommand(_ElegirImagen):
    title = 'ASPECTOIMAGEN'
    PEDIDO = 'Designe la imagen para cambiar su aspecto (clic en la imagen)'

    def con_capa(self, capa):
        self.end()                               # la ventana es modal: la orden ya no espera clics
        self.aspecto(capa)

    def aspecto(self, capa):
        from qgis.core import QgsProject
        cl = self.cl
        guardado = leer(capa)
        if guardado is not None and not marca_vigente(capa, guardado[1]):
            cl.echo('ASPECTOIMAGEN: la imagen cambió después del aspecto (GEORREF u otra orden); '
                    'se toma como está ahora y su aspecto anterior se olvida.')
            marcar(capa, None, None)
            guardado = None
        if guardado is not None:
            valores, original = guardado
        else:
            valores, original = dict(_ultimos[0]), archivo_de_capa(capa)
        if not original or not os.path.isfile(original):
            cl.echo('ASPECTOIMAGEN: no se encuentra el archivo original de la imagen (%s).' % original)
            return None
        parent = self.mgr.iface.mainWindow()
        r = ventana(parent, original, valores, guardado is not None)
        if not r:
            cl.echo('ASPECTOIMAGEN cancelado.')
            return None
        if r.get('accion') == 'original':
            if guardado is None:
                cl.echo('La imagen ya usa su archivo original.')
                return None
            usar_archivo(capa, original)
            marcar(capa, None, None)
            cl.echo('La imagen vuelve a su original: %s (las copias quedan en el disco).' % original)
            return capa
        valores = A.normalizar(r.get('valores'))
        final = r.get('accion') == 'final'
        valores['final'] = final
        _ultimos[0] = dict(valores, final=False)
        proyecto = QgsProject.instance()
        carpeta = SI.carpeta_destino(proyecto.fileName())
        prog = Progreso(parent, 'ASPECTOIMAGEN', megapixeles(original))
        try:
            fuente = prog.trabajo('1/4  Abriendo la imagen', lambda: abrir(original), 0.0, 0.15, 'abrir')
            hecho = [0.0]
            hecha = prog.trabajo('2/4  Aplicando el aspecto',
                                 lambda: A.procesar_arreglo(fuente, valores, hecho), 0.15, 0.55, 'aspecto', hecho)
            del fuente
            os.makedirs(carpeta, exist_ok=True)
            copia = nombre_copia(carpeta, original, A.SUFIJO_FINAL if final else SUFIJO)
            crs = capa.crs()
            prog.trabajo('3/4  Guardando la copia', lambda: (guardar_png(hecha, copia, final),
                                                             georreferenciar_copia(copia, original, crs)),
                         0.55, 0.85, 'guardar')
            vacia = invisible(hecha)
            del hecha
            prog.etapa(0.9, '4/4  Actualizando el mapa')
            usar_archivo(capa, copia)
            marcar(capa, valores, original)
        except (A.AspectoError, OSError, MemoryError) as e:
            prog.cerrar()
            cl.echo('ASPECTOIMAGEN: no se pudo hacer la copia (%s).' % e)
            return None
        prog.cerrar()
        if final:
            cl.echo('Imagen final, con fondo blanco y opaca: %s. Es la que se entrega; la capa '
                    'pasa a usarla (el original no se toca). «Volver al original» la devuelve.' % copia)
        else:
            cl.echo('Aspecto de la imagen: %s. Copia: %s (el original no se toca; «Volver al '
                    'original» la devuelve).' % (A.describir(valores), copia))
        if vacia:
            cl.echo('Atención: la imagen quedó invisible (todo lo claro se borra). Si es un negativo '
                    'ya hecho, use «Volver al original» o quite «Fondo transparente».')
        if not proyecto.fileName():
            cl.echo('El proyecto no está guardado: la copia quedó fuera de su carpeta. Si lleva el '
                    'proyecto a otra computadora, lleve también esa imagen.')
        return capa


def instalar(plugin):
    from .commands import CommandSpec
    plugin.mgr.register(CommandSpec('ASPECTOIMAGEN', ('ASPECTOIMAGEN', 'IMAGEASPECT', 'ASPECTO'),
                                    AspectoImagenCommand, 'interactive', 'ASPECTOIMAGEN', None, False,
                                    'dibujo', 'El aspecto de una imagen (fondo transparente, líneas, '
                                    'opacidad, contraste, manchas) en una copia'))
