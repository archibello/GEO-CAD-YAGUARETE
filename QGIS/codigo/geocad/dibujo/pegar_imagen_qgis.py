# -*- coding: utf-8 -*-
"""PEGARIMAGEN en QGIS: la imagen del portapapeles con dos clics (3.89.0).

    Esquina inferior izquierda de la imagen:
    Esquina inferior derecha (da la escala) o escriba el ancho:

El procedimiento de GEOPASTEIMAGE de IngeCAD (barra «Yaguá Imagenes»): se
captura la pantalla (o se copia una imagen, o un archivo de imagen en el
explorador), Ctrl+V en el mapa (o PEGARIMAGEN) y dos clics. La imagen se ve
semitransparente y sigue al cursor; el 2º clic le da la escala y la
dirección del borde de abajo (con ORTO queda derecha). Queda como capa
ráster arriba de todo: la captura como PNG, el archivo copiado como copia,
los dos con su archivo de mundo en «<proyecto>_imagenes». El original no se
toca. Esc no deja nada. Un archivo copiado que ya está georreferenciado
(GeoTIFF, con archivo de mundo) entra en su lugar, como lo abre QGIS.

Ctrl+V (en el mapa, o con la línea de comandos vacía): con una imagen en el
portapapeles arranca PEGARIMAGEN; con objetos copiados, QGIS los pega como
siempre. Las cuentas: pegar_imagen.py (y soltar_imagen.py).
"""

import os

from qgis.core import QgsPointXY, QgsProject, QgsRasterLayer

from . import pegar_imagen as PI
from . import soltar_imagen as SI
from .commands import _DrawCommand
from .soltar_imagen_qgis import VistaImagen, georreferenciada, medida

PRIMERO = 'Esquina inferior izquierda de la imagen'
SEGUNDO = 'Esquina inferior derecha (da la escala) o escriba el ancho'
SIN_IMAGEN = ('PEGARIMAGEN: el portapapeles no tiene una imagen. Haga una captura de '
              'pantalla (Impr Pant, o Mayús+Impr Pant para una zona) o copie una imagen, '
              'y vuelva a PEGARIMAGEN.')
LINEA_COMANDOS = 'CadCmdInput'


# ------------------------------------------------------------------ el portapapeles
class Copiada:
    """Lo que hay en el portapapeles: un archivo de imagen o una imagen suelta."""

    def __init__(self, ancho, alto, archivo=None, imagen=None):
        self.ancho, self.alto = int(ancho), int(alto)
        self.archivo = archivo
        self.imagen = imagen

    def guardar(self, ruta):
        return bool(self.imagen is not None and self.imagen.save(str(ruta), 'PNG'))


def archivo_copiado(data):
    """Un archivo de imagen copiado en el explorador (sus urls, o su ruta como texto)."""
    if data is None:
        return None
    try:
        if data.hasUrls():
            for url in data.urls():
                r = url.toLocalFile() if url.isLocalFile() else ''
                if r and SI.es_imagen(r) and os.path.isfile(r):
                    return r
        if data.hasText():
            return PI.ruta_de_texto(data.text())
    except Exception:  # noqa: BLE001
        pass
    return None


def hay_imagen(data):
    try:
        return data is not None and (data.hasImage() or archivo_copiado(data) is not None)
    except Exception:  # noqa: BLE001
        return False


def del_portapapeles():
    """La imagen del portapapeles del sistema, o None."""
    from qgis.PyQt.QtWidgets import QApplication
    board = QApplication.clipboard()
    if board is None:
        return None
    data = board.mimeData()
    archivo = archivo_copiado(data)
    if archivo is not None:
        tam = medida(archivo)
        if tam:
            return Copiada(tam[0], tam[1], archivo=archivo)
    if data is None or not data.hasImage():
        return None
    imagen = board.image()
    if imagen is None or imagen.isNull():
        return None
    imagen = imagen.copy()                      # que no cambie si se copia otra cosa
    return Copiada(imagen.width(), imagen.height(), imagen=imagen)


# ------------------------------------------------------------------ la orden
class PegarImagenCommand(_DrawCommand):
    title = 'PEGARIMAGEN'

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.copiada = None
        self.vista = None
        self.hecha = None

    def start(self):
        self.copiada = del_portapapeles()
        c = self.copiada
        if c is None or c.ancho <= 0 or c.alto <= 0:
            self.copiada = None
            self.cl.echo(SIN_IMAGEN)
            self.end()
            return
        if c.archivo is not None and georreferenciada(c.archivo):
            self.en_su_lugar(c.archivo)
            return
        try:
            self.vista = VistaImagen(self.mgr.canvas, c.imagen if c.archivo is None else c.archivo)
            self.vista.hide()
        except Exception:  # noqa: BLE001 -- sin vista previa: queda el contorno
            self.vista = None
        self.prompt()

    def prompt(self):
        self.cl.set_prompt(SEGUNDO if self.pts else PRIMERO)

    def base(self):
        return self.pts[0] if self.pts else None

    def ref_direction(self):
        return None

    # -- lo que se ve
    def esquinas_con(self, cur):
        if self.copiada is None or not self.pts or cur is None:
            return []
        p1 = (self.pts[0].x(), self.pts[0].y())
        col = PI.colocacion(p1, (cur.x(), cur.y()))
        if col is None:
            return []
        return SI.esquinas(p1, col[0], col[1], self.copiada.ancho, self.copiada.alto)

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
        if self.copiada is None:
            return
        if not self.pts:
            self.pts.append(p)
            self._set_last(p)
            self.prompt()
            return
        p1 = (self.pts[0].x(), self.pts[0].y())
        col = PI.colocacion(p1, (p.x(), p.y()))
        if col is None:
            self.cl.echo('El segundo punto tiene que ser distinto del primero.')
            return
        self.pegar(*col)

    def on_text(self, text):
        if self.copiada is None:
            return
        if self.pts:
            ancho = PI.ancho_escrito(text)
            if ancho is not None:
                if ancho <= 0:
                    self.cl.echo('El ancho tiene que ser mayor que cero.')
                    return
                self.pegar(ancho, 0.0)
                return
        self._resolve_and_apply(text)

    def on_enter(self):
        self.escape()

    def escape(self):
        if self.hecha is None and self.copiada is not None:
            self.cl.echo('Imagen sin pegar.')
        self.end()

    def cleanup(self):
        v, self.vista = self.vista, None
        if v is not None:
            try:
                v.hide()
                self.mgr.canvas.scene().removeItem(v)
            except Exception:  # noqa: BLE001
                pass

    # -- el final
    def _agregar_capa(self, ruta, crs=None):
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        capa = QgsRasterLayer(ruta, nombre)
        if not capa.isValid():
            self.cl.echo('PEGARIMAGEN: QGIS no pudo abrir %s.' % ruta)
            return None
        if crs is not None:
            capa.setCrs(crs)
        QgsProject.instance().addMapLayer(capa)
        self.hecha = capa
        return capa

    def en_su_lugar(self, ruta):
        """Un archivo copiado que ya sabe dónde va: entra como lo abre QGIS."""
        if self._agregar_capa(ruta) is not None:
            self.cl.echo('PEGARIMAGEN: «%s» ya está georreferenciada: entró en su lugar, '
                         'sin copia.' % os.path.basename(ruta))
        self.end()

    def pegar(self, ancho, giro):
        c = self.copiada
        px, py = c.ancho, c.alto
        p1 = (self.pts[0].x(), self.pts[0].y())
        proyecto = QgsProject.instance()
        crs = self.mgr.canvas.mapSettings().destinationCrs()
        carpeta = SI.carpeta_destino(proyecto.fileName())
        try:
            if c.archivo is not None:
                ruta = SI.copiar(c.archivo, carpeta, p1, ancho, giro, px, py, crs.toWkt())
            else:
                ruta = PI.guardar_captura(c.guardar, carpeta, p1, ancho, giro, px, py, crs.toWkt())
        except Exception as e:  # noqa: BLE001 -- carpeta sin permiso, disco lleno
            self.cl.echo('PEGARIMAGEN: no se pudo guardar la imagen (%s).' % e)
            self.end()
            return
        capa = self._agregar_capa(ruta, crs)
        if capa is not None:
            origen = ('copia del archivo copiado' if c.archivo is not None else 'captura guardada')
            self.cl.echo('Imagen pegada: capa "%s", %s (%s con su archivo de mundo en %s; '
                         'el original no se tocó).' % (capa.name(), PI.resumen(px, py, ancho, giro),
                                                       origen, carpeta))
            if not proyecto.fileName():
                self.cl.echo('El proyecto no está guardado: la imagen quedó fuera de su carpeta. '
                             'Si lleva el proyecto a otra computadora, lleve también esa imagen.')
        self.end()


# ------------------------------------------------------------------ Ctrl+V
class CtrlV:
    """Ctrl+V con una imagen en el portapapeles: PEGARIMAGEN. El Ctrl+V del mapa de
    QGIS es un QShortcut (no pasa por el menú): se le engancha; con la línea de
    comandos vacía lo atiende un filtro. Con objetos copiados, QGIS los pega."""

    def __init__(self, plugin):
        self.plugin = plugin
        self.atajos = []
        self.filtro = None

    def al_ctrl_v(self, *_a):
        """True si arrancó PEGARIMAGEN."""
        try:
            from qgis.PyQt.QtWidgets import QApplication
            if self.plugin.mgr is None or not hay_imagen(QApplication.clipboard().mimeData()):
                return False
            self.plugin.run_command('PEGARIMAGEN')
            return True
        except Exception:  # noqa: BLE001 -- ante la duda, Ctrl+V como venía
            return False

    def instalar(self):
        from qgis.PyQt.QtCore import QEvent, QObject, Qt
        from qgis.PyQt.QtGui import QKeySequence
        from qgis.PyQt.QtWidgets import QApplication, QLineEdit
        try:
            from qgis.PyQt.QtGui import QShortcut
        except ImportError:  # Qt5
            from qgis.PyQt.QtWidgets import QShortcut
        canvas = self.plugin.iface.mapCanvas()
        tecla = QKeySequence('Ctrl+V')
        for atajo in self.plugin.iface.mainWindow().findChildren(QShortcut):
            if atajo.parent() is canvas and atajo.key() == tecla:
                atajo.activated.connect(self.al_ctrl_v)
                self.atajos.append(atajo)
        dueño = self

        class Filtro(QObject):
            def eventFilter(self, obj, ev):  # noqa: N802 -- Qt
                try:
                    if (ev.type() == QEvent.Type.KeyPress
                            and ev.modifiers() == Qt.KeyboardModifier.ControlModifier
                            and ev.key() == Qt.Key.Key_V and isinstance(obj, QLineEdit)
                            and obj.objectName() == LINEA_COMANDOS and not obj.text()
                            and obj is QApplication.focusWidget()):
                        return dueño.al_ctrl_v()
                except Exception:  # noqa: BLE001 -- nunca romper el teclado
                    pass
                return False

        self.filtro = Filtro()
        QApplication.instance().installEventFilter(self.filtro)

    def quitar(self):
        for atajo in self.atajos:
            try:
                atajo.activated.disconnect(self.al_ctrl_v)
            except Exception:  # noqa: BLE001
                pass
        self.atajos = []
        if self.filtro is not None:
            try:
                from qgis.PyQt.QtWidgets import QApplication
                QApplication.instance().removeEventFilter(self.filtro)
            except Exception:  # noqa: BLE001
                pass
            self.filtro = None


_ctrl_v = []


def instalar(plugin):
    """Registra la orden y engancha Ctrl+V."""
    from .commands import CommandSpec
    plugin.mgr.register(CommandSpec('PEGARIMAGEN', ('PEGARIMAGEN', 'PASTEIMAGE', 'GEOPASTEIMAGE'),
                                    PegarImagenCommand, 'interactive', 'PEGARIMAGEN', None, False,
                                    'dibujo', 'Imagen del portapapeles (captura de pantalla) '
                                    'con dos clics: esquinas inferior izquierda y derecha'))
    quitar(plugin)
    c = CtrlV(plugin)
    try:
        c.instalar()
    except Exception:  # noqa: BLE001 -- sin Ctrl+V: queda la orden y el botón
        c.quitar()
        return
    _ctrl_v.append(c)


def quitar(plugin=None):  # noqa: ARG001
    while _ctrl_v:
        _ctrl_v.pop().quitar()
