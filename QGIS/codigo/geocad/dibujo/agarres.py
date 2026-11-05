# -*- coding: utf-8 -*-
"""Agarres de vértices en el cursor de GeoCAD (módulo «Agarres de vértices», 3.69).

Lo designado, con la capa en edición, muestra agarres. Un clic arranca un comando normal, así que mover un vértice
tiene las referencias, F3, F8, los ángulos relativos y lo escrito (@dx,dy, @d<ángulo, una
distancia) de todos los comandos. Los cambios van a la edición de la capa, con deshacer.
"""

import math

from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeatureRequest, QgsGeometry, QgsPointXY,
                       QgsProject, QgsRectangle, QgsVectorLayer, QgsWkbTypes)
from qgis.gui import QgsRubberBand

from ..agarres import (LIMITE_AGARRES, LIMITE_OBJETOS, accion_clic, conserva_forma,
                       indices_para_borrar, mas_cercano)
from .commands import CommandSpec, _DrawCommand
from .compat import enum, point_geometry_type
from .editkit import GeomIO, search_radius

#: dos vértices a menos que esto, en unidades de la capa, son el mismo
_EPS = 1e-7


class _Agarre:
    __slots__ = ('x', 'y', 'refs', 'medio', 'a', 'b')

    def __init__(self, x, y, medio=False, a=None, b=None):
        self.x, self.y = x, y
        self.refs = []              # (fid, índice del vértice; en el medio, el de después)
        self.medio = medio
        self.a, self.b = a, b       # en el medio: los extremos del tramo, en el SRC del mapa


class _Entrada:
    """Un objeto que cambia: su geometría, en el SRC de su capa, y qué le pasa."""

    def __init__(self, layer, io, fid, geom):
        self.layer, self.io, self.fid, self.geom = layer, io, fid, geom
        self.indices = {}           # índice -> (x, y) en el SRC del mapa
        self.insercion = None       # (índice de después, x, y)

    def _a_capa(self, x, y):
        return self.io.point_to_layer(QgsPointXY(x, y))

    def nueva(self, dx, dy):
        """La geometría con el desplazamiento dx, dy (en el SRC del mapa)."""
        g = QgsGeometry(self.geom)
        if self.insercion is not None:
            antes, x, y = self.insercion
            p = self._a_capa(x + dx, y + dy)
            a, b = g.vertexAt(antes - 1), g.vertexAt(antes)
            v = a.clone()
            v.setX(p.x())
            v.setY(p.y())
            if a.is3D():
                v.setZ((a.z() + b.z()) / 2.0)
            g.insertVertex(v, antes)
            return g
        for i, (x, y) in self.indices.items():
            p = self._a_capa(x + dx, y + dy)
            v = g.vertexAt(i)
            v.setX(p.x())
            v.setY(p.y())
            g.moveVertex(v, i)
        return g


def _forma(g):
    """Anillos por parte: lo que borrar un vértice no debe cambiar."""
    a = g.constGet()
    if a is None or g.isEmpty():
        return []
    return [a.ringCount(i) for i in range(a.partCount())]


def _tramos(g):
    """Índices (i, siguiente) de los tramos: la vuelta de un anillo no es un tramo nuevo."""
    for i in range(g.constGet().nCoordinates()):
        siguiente = g.adjacentVertices(i)[1]
        if siguiente == i + 1:
            yield i, siguiente


def _igual(v, p):
    return abs(v.x() - p.x()) <= _EPS and abs(v.y() - p.y()) <= _EPS


class Agarres:
    def __init__(self, iface, mgr):
        self.iface, self.mgr = iface, mgr
        self.canvas = iface.mapCanvas()
        self.vivo = False
        self.lista = []
        self.marcas = set()         # (x, y) de los marcados
        self.pendiente = None       # lo que va a mover el comando AGARRE
        self._luego = False
        self._conectada = None
        self.band = self._banda(QColor(0, 90, 255), 'ICON_FULL_BOX', 8)
        self.band_medios = self._banda(QColor(0, 90, 255), 'ICON_BOX', 7)
        self.band_marcas = self._banda(QColor(255, 0, 0), 'ICON_FULL_BOX', 10)

    def _banda(self, color, icono, tam):
        rb = QgsRubberBand(self.canvas, point_geometry_type())
        rb.setColor(color)
        rb.setIcon(enum(QgsRubberBand, 'IconType', icono))
        rb.setIconSize(tam)
        return rb

    # ---------------------------------------------------------------- instalar
    def instalar(self):
        self.vivo = True
        self.mgr.agarres = self
        self.mgr.register(CommandSpec('AGARRE', [], self._comando, 'interactive', 'AGARRE', None, True,
                                      'agarres', 'Mueve un vértice: se usa con un clic en su agarre.'))
        self.canvas.selectionChanged.connect(self.luego)
        self.canvas.mapToolSet.connect(self.luego)
        self.iface.currentLayerChanged.connect(self.luego)
        self.luego()

    def quitar(self):
        self.vivo = False
        self.mgr.agarres = None
        self.mgr.unregister(group='agarres')
        self._seguir(None)
        for senal in (self.canvas.selectionChanged, self.canvas.mapToolSet,
                      self.iface.currentLayerChanged):
            try:
                senal.disconnect(self.luego)
            except (TypeError, RuntimeError):
                pass
        scene = self.canvas.scene()
        for rb in (self.band, self.band_medios, self.band_marcas):
            try:
                scene.removeItem(rb)
            except RuntimeError:
                pass

    def _seguir(self, layer):
        """Los agarres siguen a la capa activa: Deshacer los mueve, y sólo se ven con la capa en
        edición (Fernando, 05/11/2026)."""
        if self._conectada is layer:
            return
        for capa, accion in ((self._conectada, 'disconnect'), (layer, 'connect')):
            if capa is None:
                continue
            for senal in (capa.geometryChanged, capa.editingStarted, capa.editingStopped):
                try:
                    getattr(senal, accion)(self.luego)
                except (TypeError, RuntimeError):
                    pass
        self._conectada = layer

    # ---------------------------------------------------------------- calcular y dibujar
    def luego(self, *_args):
        if self.vivo and not self._luego:
            self._luego = True
            QTimer.singleShot(0, self.actualizar)

    def _capa_visible(self):
        layer = self.iface.activeLayer()
        if (self.canvas.mapTool() is not self.mgr.tool or self.mgr.command is not None
                or not isinstance(layer, QgsVectorLayer) or not layer.isSpatial()
                or not layer.isEditable()
                or layer.customProperty('dibujo_cad/block_geom') == '1'):
            return None
        return layer

    def actualizar(self):
        self._luego = False
        if not self.vivo:
            return
        layer = self.iface.activeLayer()
        self._seguir(layer if isinstance(layer, QgsVectorLayer) else None)
        layer = self._capa_visible()
        self.lista = []
        if layer is not None and 0 < layer.selectedFeatureCount() <= LIMITE_OBJETOS:
            self.lista = self._calcular(layer)
        hay = {(a.x, a.y) for a in self.lista}
        self.marcas &= hay
        self._dibujar()

    def _calcular(self, layer):
        io = GeomIO(self.canvas, layer)
        vert, medios = {}, {}
        req = QgsFeatureRequest().setFilterFids(list(layer.selectedFeatureIds()))
        for f in layer.getFeatures(req):
            if not f.hasGeometry():
                continue
            g = f.geometry()
            n = g.constGet().nCoordinates()
            if len(vert) + n > LIMITE_AGARRES:
                return []
            pos = {}
            for i in range(n):
                v = g.vertexAt(i)
                p = pos[i] = io.point_to_canvas(QgsPointXY(v.x(), v.y()))
                vert.setdefault((p.x(), p.y()), _Agarre(p.x(), p.y())).refs.append((f.id(), i))
            if QgsWkbTypes.geometryType(g.wkbType()) == point_geometry_type() \
                    or QgsWkbTypes.isCurvedType(g.wkbType()):
                continue
            for i, j in _tramos(g):
                a, b = pos[i], pos[j]
                x, y = (a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0
                medios.setdefault((x, y), _Agarre(x, y, True, a, b)).refs.append((f.id(), j))
        return list(vert.values()) + list(medios.values())

    def _poner(self, rb, puntos):
        rb.reset(point_geometry_type())
        if puntos:
            rb.setToGeometry(QgsGeometry.fromMultiPointXY([QgsPointXY(x, y) for x, y in puntos]),
                             QgsCoordinateReferenceSystem())

    def _dibujar(self):
        marcados = [(a.x, a.y) for a in self.lista if not a.medio and (a.x, a.y) in self.marcas]
        libres = [(a.x, a.y) for a in self.lista if not a.medio and (a.x, a.y) not in self.marcas]
        self._poner(self.band, libres)
        self._poner(self.band_medios, [(a.x, a.y) for a in self.lista if a.medio])
        self._poner(self.band_marcas, marcados)

    # ---------------------------------------------------------------- clics
    def clic(self, pt, mayus):
        """Clic con el cursor en reposo: True si fue sobre un agarre."""
        if not self.lista:
            return False
        i = mas_cercano([(a.x, a.y) for a in self.lista], pt.x(), pt.y(), search_radius(self.canvas))
        if i is None:
            return False
        ag = self.lista[i]
        lugar = (ag.x, ag.y)
        accion = accion_clic(ag.medio, lugar in self.marcas, mayus)
        if accion == 'marcar':
            self.marcas.add(lugar)
        elif accion == 'desmarcar':
            self.marcas.discard(lugar)
        elif accion == 'mover_marcados':
            self._arrancar(ag, [a for a in self.lista if (a.x, a.y) in self.marcas])
            return True
        elif accion != 'nada':
            self.marcas.clear()
            self._arrancar(ag, [ag])
            return True
        self._dibujar()
        self.canvas.setFocus()      # Supr va al mapa, no a la línea de comandos
        return True

    def _arrancar(self, base, agarres):
        self.pendiente = (base, agarres)
        ultimo = self.mgr.last_cmd
        try:
            self.mgr.run('AGARRE')
        finally:
            self.mgr.last_cmd = ultimo  # Intro repite el último comando de verdad
            self.pendiente = None

    def _comando(self, mgr, layer, kind):
        return _ComandoAgarre(mgr, layer, kind, self.pendiente, self)

    # ---------------------------------------------------------------- qué cambia
    def _capas_vecinas(self):
        if not QgsProject.instance().topologicalEditing():
            return []
        return [c for c in QgsProject.instance().mapLayers().values()
                if isinstance(c, QgsVectorLayer) and c.isEditable() and c.isSpatial()]

    def entradas(self, layer, agarres):
        """Los objetos que cambian; con la edición topológica de QGIS, también los que comparten
        el vértice o el tramo, en las capas que están en edición."""
        io = GeomIO(self.canvas, layer)
        out = {}

        def entrada(capa, cio, fid, g=None):
            clave = (capa.id(), fid)
            if clave not in out:
                out[clave] = _Entrada(capa, cio, fid, g if g is not None else capa.getFeature(fid).geometry())
            return out[clave]

        for ag in agarres:
            for fid, i in ag.refs:
                e = entrada(layer, io, fid)
                if ag.medio:
                    e.insercion = (i, ag.x, ag.y)
                else:
                    e.indices[i] = (ag.x, ag.y)
        for capa in self._capas_vecinas():
            cio = GeomIO(self.canvas, capa)
            for ag in agarres:
                self._vecinos(capa, cio, ag, entrada, out)
        return list(out.values())

    def _vecinos(self, capa, cio, ag, entrada, out):
        p = cio.point_to_layer(QgsPointXY(ag.x, ag.y))
        d = max(_EPS, search_radius(self.canvas) / 1000.0)
        rect = QgsRectangle(p.x() - d, p.y() - d, p.x() + d, p.y() + d)
        for f in capa.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
            if not f.hasGeometry():
                continue
            g = f.geometry()
            if ag.medio:
                if (capa.id(), f.id()) in out and out[(capa.id(), f.id())].insercion is not None:
                    continue
                a, b = cio.point_to_layer(ag.a), cio.point_to_layer(ag.b)
                for i, j in _tramos(g):
                    vi, vj = g.vertexAt(i), g.vertexAt(j)
                    if (_igual(vi, a) and _igual(vj, b)) or (_igual(vi, b) and _igual(vj, a)):
                        entrada(capa, cio, f.id(), g).insercion = (j, ag.x, ag.y)
                        break
                continue
            for i in range(g.constGet().nCoordinates()):
                if _igual(g.vertexAt(i), p):
                    entrada(capa, cio, f.id(), g).indices[i] = (ag.x, ag.y)

    @staticmethod
    def aplicar(entradas, nueva, titulo):
        """Una sola orden de deshacer por capa. Devuelve cuántos objetos cambiaron."""
        por_capa = {}
        for e in entradas:
            por_capa.setdefault(e.layer.id(), []).append(e)
        n = 0
        for grupo in por_capa.values():
            capa = grupo[0].layer
            capa.beginEditCommand(titulo)
            try:
                for e in grupo:
                    g = nueva(e)
                    if g is not None and capa.changeGeometry(e.fid, g):
                        n += 1
            except Exception:
                capa.destroyEditCommand()
                raise
            capa.endEditCommand()
            capa.triggerRepaint()
        return n

    # ---------------------------------------------------------------- Supr
    def borrar_marcados(self):
        """Supr con agarres marcados: True si la tecla era para ellos."""
        if not self.marcas:
            return False
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            return False
        cl = self.mgr.cmdline
        agarres = [a for a in self.lista if (a.x, a.y) in self.marcas]
        rechazados = []

        def nueva(e):
            por_posicion = {}
            for i, lugar in e.indices.items():
                por_posicion.setdefault(lugar, []).append(i)
            if not self._es_poligono(e.geom) and any(len(v) > 1 for v in por_posicion.values()):
                rechazados.append(e.fid)    # el cierre de una línea cerrada: abriría el objeto
                return None
            g = QgsGeometry(e.geom)
            for i in indices_para_borrar(por_posicion):
                if not g.deleteVertex(i):
                    rechazados.append(e.fid)
                    return None
            if not conserva_forma(_forma(e.geom), _forma(g)):
                rechazados.append(e.fid)    # quedaría sin parte o sin anillo
                return None
            return g

        n = self.aplicar(self.entradas(layer, agarres), nueva, 'BORRAR VÉRTICE')
        self.marcas.clear()
        cl.echo('%d objeto(s) con vértices borrados.' % n)
        if rechazados:
            cl.echo('%d objeto(s) sin cambios: quedarían sin forma o se abrirían.' % len(set(rechazados)))
        self.luego()
        return True

    @staticmethod
    def _es_poligono(g):
        return g.constGet().dimension() == 2


class _ComandoAgarre(_DrawCommand):
    title = 'AGARRE'

    def __init__(self, mgr, layer, kind, pendiente, agarres):
        super().__init__(mgr, layer, kind)
        self.pendiente = pendiente
        self.agarres = agarres
        self.base_pt = None
        self.lista = []
        self.previas_max = 300

    def start(self):
        if self.pendiente is None:
            self.cl.echo('AGARRE se usa con un clic en un agarre de lo designado.')
            self.end()
            return
        base, agarres = self.pendiente
        self.base_pt = QgsPointXY(base.x, base.y)
        self.lista = self.agarres.entradas(self.layer, agarres)
        self.insertando = base.medio
        self._set_last(self.base_pt)
        self.prompt()

    def prompt(self):
        self.cl.set_prompt('Precise el punto nuevo del vértice', None, 'cancelar')

    def base(self):
        return self.base_pt

    def snap_points(self):
        return []

    def ref_direction(self):
        """Dirección del tramo que llega al vértice, para los ángulos relativos."""
        if self.base_pt is None or not self.lista or len(self.lista[0].indices) != 1:
            return None
        e = self.lista[0]
        i, (x, y) = next(iter(e.indices.items()))
        anterior = e.geom.adjacentVertices(i)[0]
        if anterior < 0:
            return None
        v = e.geom.vertexAt(anterior)
        p = e.io.point_to_canvas(QgsPointXY(v.x(), v.y()))
        return math.atan2(y - p.y(), x - p.x())

    def preview(self, cur):
        return [], False, ([self.base_pt, cur] if cur is not None and self.base_pt is not None else []), []

    def preview_geoms(self, cur):
        if cur is None or self.base_pt is None:
            return None
        dx, dy = cur.x() - self.base_pt.x(), cur.y() - self.base_pt.y()
        return [e.io.to_canvas(e.nueva(dx, dy)) for e in self.lista[:self.previas_max]]

    def on_point(self, p):
        dx, dy = p.x() - self.base_pt.x(), p.y() - self.base_pt.y()
        if dx or dy or self.insertando:
            n = self.agarres.aplicar(self.lista, lambda e: e.nueva(dx, dy),
                                     'AGREGAR VÉRTICE' if self.insertando else 'MOVER VÉRTICE')
            self.cl.echo('%d objeto(s) cambiado(s). Guarde con "Guardar cambios de la capa".' % n)
        self.agarres.marcas.clear()
        self.end()

    def on_text(self, text):
        self._resolve_and_apply(text)

    def on_enter(self):
        self.end()

    def escape(self):
        self.end()
