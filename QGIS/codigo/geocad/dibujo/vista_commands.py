# -*- coding: utf-8 -*-
"""ZOOM (Z), ENCUADRE / PAN (P), REGEN (RE) y REDIBUJA (R) de IngeCAD en Dibujo de QGIS (3.61.0).

Las cuentas están en vista.py (sin Qt). Acá, el mapa de QGIS:
  - Extensión = lo que ocupan las capas vectoriales visibles (el dibujo; un
    mapa de fondo de todo el mundo no cuenta); Todo = todas las capas (el
    «Zoom general» de QGIS);
  - Previo / Siguiente = las vistas anteriores de QGIS;
  - Objeto = los objetos seleccionados en cualquier capa, o los que se designen;
  - 'Z y 'P se escriben dentro de otro comando sin cortarlo, como en IngeCAD.
"""

import time

from qgis.core import QgsPointXY, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsMapTool, QgsMapToolPan

from . import vista
from .commands import _DrawCommand
from .compat import enum, qt
from .editkit import GeomIO, pick_feature
from .units import format_length


# ------------------------------------------------------------ el mapa
def _rect(r):
    return (r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum())


class Vistas:
    """El historial de vistas del mapa (vista.Historial) para ZOOM Previo y Siguiente."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.h = vista.Historial()
        self._navegando = False
        self.h.anotar(_rect(canvas.extent()), time.monotonic())
        canvas.extentsChanged.connect(self._cambio)

    def _cambio(self):
        if not self._navegando:
            self.h.anotar(_rect(self.canvas.extent()), time.monotonic())

    def cambiar(self, fn):
        """Un cambio de vista de un comando: una vista propia, aparte de la rueda."""
        self.h.cortar()
        fn()
        self.h.cortar()

    def ir(self, r):
        self._navegando = True
        try:
            self.canvas.setExtent(QgsRectangle(*r))
            self.canvas.refresh()
        finally:
            self._navegando = False

    def remove(self):
        try:
            self.canvas.extentsChanged.disconnect(self._cambio)
        except (TypeError, RuntimeError):
            pass


def _vistas(mgr):
    v = getattr(mgr, 'vistas', None)
    if v is None:
        v = mgr.vistas = Vistas(mgr.canvas)
    return v


def _cambiar(mgr, fn):
    _vistas(mgr).cambiar(fn)
    mgr.canvas.refresh()


def _poner(mgr, r):
    _cambiar(mgr, lambda: mgr.canvas.setExtent(QgsRectangle(*r)))


def _capas(canvas):
    return [l for l in canvas.layers() if isinstance(l, QgsVectorLayer) and l.isSpatial()]


def extension_dibujo(canvas):
    """(xmin, ymin, xmax, ymax) de las capas vectoriales visibles, en el SRC del mapa."""
    ms = canvas.mapSettings()
    rects = []
    for lyr in _capas(canvas):
        try:
            lyr.updateExtents()
        except Exception:  # noqa: BLE001
            pass
        e = lyr.extent()
        if e.isNull() or not lyr.featureCount():
            continue
        rects.append(_rect(ms.layerExtentToOutputExtent(lyr, e)))
    return vista.union(rects, minimo=max(canvas.extent().height() / 10.0, 1e-9)) if rects else None


def extension_seleccion(canvas):
    """Lo que ocupan los objetos seleccionados de todas las capas visibles (o None)."""
    ms = canvas.mapSettings()
    rects = [_rect(ms.layerExtentToOutputExtent(l, l.boundingBoxOfSelected()))
             for l in _capas(canvas) if l.selectedFeatureCount()]
    return vista.union(rects, minimo=max(canvas.extent().height() / 10.0, 1e-9)) if rects else None


def zoom_extension(mgr):
    r = extension_dibujo(mgr.canvas)
    if r is None:
        _cambiar(mgr, mgr.canvas.zoomToFullExtent)
        return
    _poner(mgr, r)


def zoom_opcion(mgr, opt):
    """Las opciones que no piden puntos. True si quedó hecho."""
    canvas, echo = mgr.canvas, mgr.cmdline.echo
    if opt == 'E':
        zoom_extension(mgr)
    elif opt == 'T':
        _cambiar(mgr, canvas.zoomToFullExtent)
    elif opt in ('P', 'SI'):
        v = _vistas(mgr)
        r = v.h.previo() if opt == 'P' else v.h.siguiente()
        if r is None:
            echo('No hay vista previa.' if opt == 'P' else 'No hay vista siguiente.')
        else:
            v.ir(r)
    elif opt == 'AM':
        _cambiar(mgr, lambda: canvas.zoomByFactor(1.0 / vista.PASO))
    elif opt == 'R':
        _cambiar(mgr, lambda: canvas.zoomByFactor(vista.PASO))
    elif opt == 'O':
        r = extension_seleccion(canvas)
        if r is None:
            return False
        _poner(mgr, r)
    else:
        return False
    return True


def zoom_factor(mgr, f):
    """nX (de la vista), n (de todo el dibujo), 1:n (escala del mapa) o nXP."""
    canvas = mgr.canvas
    tipo, k = f
    if tipo == 'veces':
        _cambiar(mgr, lambda: canvas.zoomByFactor(1.0 / k))
    elif tipo == 'todo':
        r = extension_dibujo(canvas) or _rect(canvas.fullExtent())
        _poner(mgr, vista.rect_escalado(r, k))
    elif tipo == 'escala':
        _cambiar(mgr, lambda: canvas.zoomScale(k))
    else:
        mgr.cmdline.echo('nXP es para las ventanas gráficas de IngeCAD: en QGIS indique la escala 1:n.')


def zoom_transparente(mgr, args):
    """'ZOOM dentro de otro comando: sólo lo que no pide puntos (como en IngeCAD)."""
    t = args.strip()
    if not t:
        mgr.cmdline.echo("'ZOOM: indique una opción (Extensión, Previo, 2X, 1:500...); "
                         'la rueda hace zoom en cualquier momento.')
        return
    f = vista.factor(t)
    if f is not None:
        zoom_factor(mgr, f)
        return
    opt = vista.opcion(t)
    if opt is not None and zoom_opcion(mgr, opt):
        return
    mgr.cmdline.echo('ZOOM %s no se puede usar de forma transparente.' % t)


def pan_transparente(mgr, args=''):
    mgr.cmdline.echo('Encuadre con el botón central del ratón: funciona durante cualquier comando.')


def regen(mgr):
    mgr.canvas.refreshAllLayers()
    mgr.cmdline.echo('Regenerando el dibujo.')


def redibuja(mgr):
    mgr.canvas.refresh()


# ------------------------------------------------------------ ZOOM
class ZoomCommand(_DrawCommand):
    """ZOOM con las opciones de IngeCAD y más (ver vista.py)."""
    title = 'ZOOM'
    no_ortho = True

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.canvas = mgr.canvas
        self.state = 'opcion'
        self.esquina = None
        self.punto_centro = None
        self.objetos = []           # (capa, fid, geometría en el SRC del mapa) de ZOOM Objeto

    def start(self):
        self.prompt()

    def base(self):
        return self.esquina if self.state == 'esquina2' else None

    def prompt(self):
        st, cl = self.state, self.cl
        if st == 'opcion':
            cl.set_prompt(vista.PEDIDO, vista.OPCIONES, vista.DEFECTO)
        elif st == 'esquina1':
            cl.set_prompt('Precise primera esquina')
        elif st == 'esquina2':
            cl.set_prompt('Precise esquina opuesta')
        elif st == 'centro':
            cl.set_prompt('Precise punto central')
        elif st == 'altura':
            cl.set_prompt('Indique magnificación o altura', None,
                          format_length(self.canvas.extent().height(), self.mgr.units))
        elif st == 'escala':
            cl.set_prompt('Indique un factor de escala (nX o 1:n)')
        elif st == 'objeto':
            cl.set_prompt('Designe objetos (Intro termina)')

    def _fin(self):
        self.end()

    # ---------------------------------------------------- entrada
    def on_point(self, p):
        st = self.state
        if st in ('opcion', 'esquina1'):
            self.esquina = p
            self.state = 'esquina2'
        elif st == 'esquina2':
            r = vista.rect_ventana((self.esquina.x(), self.esquina.y()), (p.x(), p.y()))
            if r is None:
                self.cl.echo('La ventana no tiene tamaño: precise otra esquina.')
                return self.prompt()
            _poner(self.mgr, r)
            return self._fin()
        elif st == 'centro':
            self.punto_centro = p
            self.state = 'altura'
        elif st == 'objeto':
            self._designar(p)
        else:
            self.cl.echo('Indique un valor.')
        self.prompt()

    def on_text(self, text):
        st = self.state
        if st == 'opcion':
            f = vista.factor(text)
            if f is not None:
                zoom_factor(self.mgr, f)
                return self._fin()
            opt = vista.opcion(text)
            if opt is None:
                if any(c in text for c in ',;@#<'):
                    return self._resolve_and_apply(text)      # una esquina tecleada
                self.cl.echo('Opción de ZOOM desconocida "%s".' % text.strip())
                return self.prompt()
            return self._elegir(opt)
        if st == 'altura':
            h = vista.altura(text, self.canvas.extent().height())
            return self._centro(h)
        if st == 'escala':
            f = vista.factor(text)
            if f is None or f[0] == 'xp':
                self.cl.echo('Indique un factor de escala: 2X, 0.5X o 1:500.')
                return self.prompt()
            zoom_factor(self.mgr, f)
            return self._fin()
        self._resolve_and_apply(text)

    def on_enter(self):
        st = self.state
        if st == 'opcion':
            zoom_extension(self.mgr)                     # Intro = Extensión, como IngeCAD
            return self._fin()
        if st == 'altura':
            return self._centro(self.canvas.extent().height())
        if st == 'objeto':
            r = vista.union([_rect(g.boundingBox()) for _l, _f, g in self.objetos],
                            minimo=max(self.canvas.extent().height() / 10.0, 1e-9))
            if r is not None:
                _poner(self.mgr, r)
            return self._fin()
        self._fin()

    def escape(self):
        self.end()

    # ---------------------------------------------------- opciones
    def _elegir(self, opt):
        if opt == 'V':
            self.state = 'esquina1'
        elif opt == 'C':
            self.state = 'centro'
        elif opt == 'S':
            self.state = 'escala'
        elif opt == 'O' and extension_seleccion(self.canvas) is None:
            self.state = 'objeto'
        else:
            zoom_opcion(self.mgr, opt)
            return self._fin()
        self.prompt()

    def _centro(self, alto):
        size = self.canvas.size()
        aspecto = size.width() / float(max(1, size.height()))
        c = self.punto_centro
        _poner(self.mgr, vista.rect_centro((c.x(), c.y()), alto, aspecto))
        self._fin()

    def _designar(self, p):
        """ZOOM Objeto sin selección: el objeto más cercano al clic, en cualquier capa visible."""
        for lyr in _capas(self.canvas):
            io = GeomIO(self.canvas, lyr)
            fid, f = pick_feature(self.canvas, io, lyr, p,
                                  exclude=[x for l, x, _g in self.objetos if l is lyr])
            if fid is not None:
                self.objetos.append((lyr, fid, io.to_canvas(f.geometry())))
                self.cl.echo('%d encontrado(s)' % len(self.objetos))
                return
        self.cl.echo('No hay ningún objeto ahí.')

    # ---------------------------------------------------- vista previa
    def preview(self, cur):
        if self.state == 'esquina2' and cur is not None and self.esquina is not None:
            a = self.esquina
            rect = [a, QgsPointXY(cur.x(), a.y()), cur, QgsPointXY(a.x(), cur.y()), a]
            return [], False, rect, []
        return [], False, [], []

    def preview_geoms(self, cur):
        return [g for _l, _f, g in self.objetos] or None


# ------------------------------------------------------------ PAN
class _PanTool(QgsMapToolPan):
    """El desplazar de QGIS para ENCUADRE: Esc, Intro o clic derecho terminan."""

    def __init__(self, canvas, cmd):
        super().__init__(canvas)
        self.cmd = cmd

    def flags(self):
        """Sin el menú de QGIS, para que el clic derecho termine. Del mismo tipo que lo de
        QGIS: en QGIS 4 (PyQt6) Flag & ~Flag da un int y QGIS lo rechaza (3.61.1)."""
        f = super().flags()
        try:
            return type(f)(int(f) & ~int(enum(QgsMapTool, 'Flag', 'ShowContextMenu')))
        except Exception:  # noqa: BLE001
            return f

    def canvasReleaseEvent(self, ev):
        if ev.button() == qt('MouseButton', 'RightButton'):
            self.cmd.end()
            return
        super().canvasReleaseEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() in (qt('Key', 'Key_Escape'), qt('Key', 'Key_Return'), qt('Key', 'Key_Enter')):
            self.cmd.end()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def deactivate(self):
        super().deactivate()
        self.cmd.tool_cambiada(self)


class PanCommand(_DrawCommand):
    """ENCUADRE (PAN / P) como en IngeCAD: la mano, arrastrar con el izquierdo;
    Esc, Intro o clic derecho terminan y vuelve el modo CAD."""
    title = 'ENCUADRE'
    AVISO = 'Pulse Esc, Intro o clic derecho para salir del encuadre'

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.canvas = mgr.canvas
        self.pan = None
        self._saliendo = False

    def start(self):
        self.pan = _PanTool(self.canvas, self)
        self.mgr._switching = True
        try:
            self.canvas.setMapTool(self.pan)
        finally:
            self.mgr._switching = False
        self.cl.echo(self.AVISO + '.')
        self.prompt()

    def prompt(self):
        self.cl.set_prompt(self.AVISO)

    def base(self):
        return None

    def preview(self, cur):
        return [], False, [], []

    def on_point(self, p):
        pass

    def on_text(self, text):
        self.prompt()

    def on_enter(self):
        self.end()

    def escape(self):
        self.end()

    def tool_cambiada(self, tool):
        """La mano dejó de ser la herramienta: si no fue por terminar, el usuario
        eligió otra de QGIS y el encuadre termina sin volver al modo CAD."""
        if not self._saliendo and self.mgr.command is self:
            self._saliendo = True
            self.mgr.end_command()

    def end(self):
        if self._saliendo:
            return
        self._saliendo = True
        if self.canvas.mapTool() is self.pan:
            self.mgr._switching = True
            try:
                self.canvas.setMapTool(self.mgr.tool)
            finally:
                self.mgr._switching = False
        super().end()


__all__ = ['Vistas', 'ZoomCommand', 'PanCommand', 'zoom_transparente', 'pan_transparente', 'regen', 'redibuja',
           'zoom_opcion', 'zoom_factor', 'extension_dibujo']
