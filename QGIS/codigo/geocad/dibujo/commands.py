# -*- coding: utf-8 -*-
"""Gestor de comandos y comandos de dibujo LÍNEA y POLILÍNEA."""

import math

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import (QgsCoordinateTransform, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer, QgsVectorLayerUtils, QgsWkbTypes)

from .compat import geometry_kind
from .maptool import CadMapTool
from .settings import get_setting, load_units, set_setting
from .units import InputError, format_angle, format_rel, rel_zero, format_length, format_point, parse_distance, parse_point

# Comandos incorporados: nombre -> alias (como el archivo acad.pgp)
BUILTIN_ALIASES = {
    'LINE': ('LINEA', 'LÍNEA', 'LINE', 'L'),
    'PLINE': ('POLILINEA', 'POLILÍNEA', 'PLINE', 'PL'),
    'UNITS': ('UNIDADES', 'UNITS', 'UN', 'UNI'),
    'ORTHO': ('ORTO', 'ORTHO'),
}


class CommandSpec:
    """
    Definición de un comando registrado en la línea de comandos.

    kind='action'      -> handler() se ejecuta al instante (p. ej. AISLARCAPA, CAPA).
    kind='interactive' -> handler(manager, layer, geomkind) devuelve un objeto comando
                          con start/prompt/on_point/on_text/on_enter/escape/preview/base.
    layer_types        -> tipos de capa admitidos ('line', 'polygon', 'point') o None si no requiere capa.
    edit               -> True si necesita la capa en modo edición.
    """

    def __init__(self, name, aliases, handler, kind='action', title=None,
                 layer_types=None, edit=False, group='', description=''):
        self.name = name.upper()
        self.aliases = tuple(a.upper() for a in aliases) + (self.name,)
        self.handler = handler
        self.kind = kind
        self.title = title or self.name
        self.layer_types = layer_types
        self.edit = edit
        self.group = group
        self.description = description


OPT_UNDO = ('H', 'U', 'DESHACER', 'UNDO')
OPT_CLOSE = ('C', 'CERRAR', 'CLOSE')
OPT_LENGTH = ('L', 'LONGITUD', 'LENGTH')


def _key(text):
    return text.strip().upper().lstrip('_')


def _xy(p):
    return (p.x(), p.y())


class CommandManager(QObject):
    orthoChanged = pyqtSignal(bool)
    relativeChanged = pyqtSignal(bool)
    osnapChanged = pyqtSignal(bool)
    textStyleChanged = pyqtSignal()
    unitsRequested = pyqtSignal()

    def __init__(self, iface, cmdline):
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.cmdline = cmdline
        self.units = load_units()
        self.ortho = get_setting('ortho', False, bool)
        self.relative = get_setting('relangle', False, bool)
        self.lastpoint = None        # LASTPOINT (SRC del mapa)
        self.last_line_end = None    # para continuar LÍNEA con Intro
        self.command = None
        self.last_cmd = None
        self.prev_tool = None
        self._switching = False
        self._deactivating = False
        self.idle_win = None
        self.last_plot_window = None   # ventana de TRAZAR / PRESENTACION
        self.plot_preset = None
        self.last_added = {}         # último objeto creado por capa (designación 'Último')
        self._watched = set()
        self.prev_selection = {}     # selección Previa por capa
        self.text_style = None       # lo asigna el complemento (texto_tool.TextStyle)
        self.cursor = None
        self.cursor_snapped = False
        self.shift = False
        self.tool = CadMapTool(self.canvas, self)
        self.specs = {}
        self.alias_map = {}
        self._register_builtins()
        cmdline.submitted.connect(self.submit)
        cmdline.cancelled.connect(self.cancel)
        cmdline.orthoToggled.connect(self.toggle_ortho)
        cmdline.osnapToggled.connect(self.toggle_osnap)

    def reload_units(self, *args):
        self.units = load_units()
        self.refresh()

    # ------------------------------------------------------------ registro
    def register(self, spec):
        """Registra (o reemplaza) un comando. Lo usan también otros complementos."""
        old = self.specs.get(spec.name)
        if old is not None:
            for a in old.aliases:
                if self.alias_map.get(a) == spec.name:
                    del self.alias_map[a]
        self.specs[spec.name] = spec
        for a in spec.aliases:
            self.alias_map[a] = spec.name
        return spec

    def unregister(self, name=None, group=None):
        for n in [n for n, sp in self.specs.items()
                  if (name and n == name.upper()) or (group and sp.group == group)]:
            sp = self.specs.pop(n)
            for a in sp.aliases:
                if self.alias_map.get(a) == n:
                    del self.alias_map[a]

    def _register_builtins(self):
        self.register(CommandSpec('LINE', BUILTIN_ALIASES['LINE'], LineCommand, 'interactive',
                                  'LÍNEA', ('line',), True, 'dibujo', 'Segmentos de línea independientes'))
        self.register(CommandSpec('PLINE', BUILTIN_ALIASES['PLINE'], PlineCommand, 'interactive',
                                  'POLILÍNEA', ('line', 'polygon'), True, 'dibujo',
                                  'Polilínea (o polígono en capas de polígonos)'))
        self.register(CommandSpec('UNITS', BUILTIN_ALIASES['UNITS'], self.unitsRequested.emit,
                                  title='UNIDADES', group='dibujo', description='Unidades de dibujo'))
        self.register(CommandSpec('RELANGLE', ('REL', 'RELATIVO', 'ANGREL'), self.toggle_relative,
                                  title='REL', group='dibujo',
                                  description='Ángulos relativos al último tramo (activar/desactivar)'))
        self.register(CommandSpec('OSNAP', ('REFENT', 'OSNAP', 'RF'), self.toggle_osnap,
                                  title='REFENT', group='dibujo',
                                  description='Referencia a objetos activada/desactivada (F3)'))
        self.register(CommandSpec('ORTHO', BUILTIN_ALIASES['ORTHO'], self.toggle_ortho,
                                  title='ORTO', group='dibujo', description='Activa/desactiva ORTO (F8)'))
        self.register(CommandSpec('HELP', ('AYUDA', '?', 'COMANDOS'), self.list_commands,
                                  title='AYUDA', group='dibujo', description='Lista de comandos'))

    def list_commands(self):
        groups = {}
        for sp in self.specs.values():
            groups.setdefault(sp.group or 'otros', []).append(sp)
        for g in sorted(groups):
            self.cmdline.echo('— %s —' % g.upper())
            for sp in sorted(groups[g], key=lambda x: x.title):
                al = [a for a in sp.aliases if a not in (sp.name, sp.title)]
                self.cmdline.echo('  %-14s %-28s %s' % (sp.title, ', '.join(al[:4]), sp.description))

    # ------------------------------------------------------------ comandos
    def run(self, text):
        transparent = text.strip().startswith("'") and self.command is not None
        key = _key(text).lstrip("'")
        name = self.alias_map.get(key)
        spec = self.specs.get(name) if name else None
        if spec is None:
            self.cmdline.echo('Comando desconocido "%s". Escriba AYUDA para ver la lista.' % key)
            return
        if transparent:
            if spec.kind == 'interactive':
                self.cmdline.echo('%s no se puede usar de forma transparente.' % spec.title)
            else:
                spec.handler()
                self.command.prompt()
            return
        if self.command is not None:
            self.cancel()
        self.last_cmd = spec.name
        if spec.kind != 'interactive':
            try:
                spec.handler()
            except Exception as e:  # noqa: BLE001
                self.cmdline.echo('Error en %s: %s' % (spec.title, e))
            return
        layer = self.iface.activeLayer()
        try:
            from . import crashlog
            crashlog.trail('comando %s capa=%s sel=%s edit=%s' % (
                spec.name, layer.name() if layer is not None else None,
                layer.selectedFeatureCount() if isinstance(layer, QgsVectorLayer) else '-',
                layer.isEditable() if isinstance(layer, QgsVectorLayer) else '-'))
        except Exception:  # noqa: BLE001
            pass
        layer = self._redirect_block_reference(layer)
        kind = geometry_kind(layer) if isinstance(layer, QgsVectorLayer) else None
        if spec.layer_types is not None and kind not in spec.layer_types:
            tipos = {'line': 'líneas', 'polygon': 'polígonos', 'point': 'puntos'}
            self.cmdline.echo('%s: la capa activa debe ser una capa vectorial de %s.'
                              % (spec.title, ' o '.join(tipos[t] for t in spec.layer_types)))
            return
        if spec.edit and layer is not None and not layer.isEditable():
            if not layer.startEditing():
                self.cmdline.echo('No se puede editar la capa "%s".' % layer.name())
                return
            self.cmdline.echo('Capa "%s" en modo edición (guarde con "Guardar cambios de la capa").'
                              % layer.name())
        if isinstance(layer, QgsVectorLayer) and layer.id() not in self._watched:
            lid = layer.id()
            try:
                layer.featureAdded.connect(lambda fid, lid=lid: self.last_added.__setitem__(lid, fid))
                self._watched.add(lid)
            except Exception:  # noqa: BLE001
                pass
        self.command = spec.handler(self, layer, kind)
        if self.canvas.mapTool() is not self.tool:
            self.prev_tool = self.canvas.mapTool()
            self._switching = True
            self.canvas.setMapTool(self.tool)
            self._switching = False
        if self.canvas.mapSettings().destinationCrs().isGeographic():
            self.cmdline.echo('Atención: el mapa está en coordenadas geográficas; '
                              'las distancias se interpretan en grados.')
        if not self.osnap_enabled():
            self.cmdline.echo('Referencia a objetos desactivada: pulse F3 o escriba REFENT para activarla.')
        self.command.start()
        try:
            self.cmdline.input.setFocus()   # el teclado va a la línea de comandos (como AutoCAD)
        except Exception:  # noqa: BLE001
            pass
        self.refresh()

    def _redirect_block_reference(self, layer):
        """La capa 'Bloques CAD (referencia)' es solo para el snapping: los comandos
        trabajan sobre las inserciones de bloque (y su selección pasa a ellas)."""
        try:
            if not (isinstance(layer, QgsVectorLayer) and layer.customProperty('dibujo_cad/block_geom') == '1'):
                return layer
            from .blocks import BLOCK_FLAG, find_flagged
            bl = find_flagged(BLOCK_FLAG)
            if bl is None:
                return layer
            fids = []
            i = layer.fields().indexOf('INST_FID')
            if i != -1 and layer.selectedFeatureCount():
                from qgis.core import QgsFeatureRequest
                req = QgsFeatureRequest().setFilterFids(list(layer.selectedFeatureIds()))
                for f in layer.getFeatures(req):
                    v = f.attribute(i)
                    if v not in (None, ''):
                        fids.append(int(v))
                layer.removeSelection()
            self.iface.setActiveLayer(bl)
            if fids:
                bl.selectByIds(fids)
            self.cmdline.echo('"%s" es solo de referencia: se trabaja sobre "%s".' % (layer.name(), bl.name()))
            return bl
        except Exception:  # noqa: BLE001
            return layer

    def end_command(self):
        cmd = self.command
        self.command = None
        self.cmdline.raw_mode = False
        if cmd is not None and hasattr(cmd, 'cleanup'):
            try:
                cmd.cleanup()
            except Exception:  # noqa: BLE001
                pass
        self.tool.clear()
        self.idle_win = None
        self.cmdline.set_prompt('Comando')
        self.cmdline.set_info('')
        # El mapa queda en reposo CAD (como el área de dibujo de AutoCAD):
        # Intro / Espacio / clic derecho repiten el último comando y el clic
        # izquierdo designa objetos. Elegir otra herramienta de QGIS sale del modo CAD.

    def tool_deactivated(self):
        self.idle_win = None
        if self._switching or self.command is None:
            return
        cmd = self.command
        self._deactivating = True
        try:
            cmd.escape()       # el usuario eligió otra herramienta: se conserva lo dibujado
        finally:
            self._deactivating = False
        if self.command is cmd:
            self.command = None
        self.cmdline.raw_mode = False
        self.cmdline.set_prompt('Comando')
        self.cmdline.set_info('')

    def cancel(self):
        if self.command is None:
            self.idle_win = None
            layer = self.iface.activeLayer()
            if isinstance(layer, QgsVectorLayer) and layer.selectedFeatureCount():
                layer.removeSelection()
                self.cmdline.echo('*Cancelar*')
            self.refresh()
            return
        self.cmdline.echo('*Cancelar*')
        self.command.escape()
        if self.command is not None:
            self.end_command()

    def submit(self, text):
        if self.command is None:
            if not text:
                if self.last_cmd:
                    spec = self.specs.get(self.last_cmd)
                    self.cmdline.echo('Comando: %s' % (spec.title if spec else self.last_cmd))
                    self.run(self.last_cmd)
                return
            self.cmdline.echo('Comando: %s' % text)
            self.run(text)
            return
        self.cmdline.echo_input(text)
        if text.startswith("'") and not getattr(self.command, 'text_mode', False):
            self.run(text)       # comando transparente: 'ORTO, 'UNIDADES...
            self.refresh()
            return
        try:
            if text:
                self.command.on_text(text)
            else:
                self.command.on_enter()
        except (InputError, ValueError) as e:
            self.cmdline.echo(str(e))
        except Exception as e:  # noqa: BLE001
            self.cmdline.echo('Error: %s' % e)
        self.refresh()

    def enter(self):
        """Clic derecho = Intro: confirma lo que esté escrito en la línea de comandos."""
        try:
            self.cmdline.submit()
        except Exception:  # noqa: BLE001
            self.submit('')

    def toggle_ortho(self):
        self.set_ortho(not self.ortho)

    # -- referencia a objetos = snapping del proyecto QGIS
    def osnap_enabled(self):
        try:
            return QgsProject.instance().snappingConfig().enabled()
        except Exception:
            return True

    def toggle_osnap(self):
        self.set_osnap(not self.osnap_enabled())

    def set_osnap(self, on):
        proj = QgsProject.instance()
        cfg = proj.snappingConfig()
        cfg.setEnabled(bool(on))
        proj.setSnappingConfig(cfg)
        self.cmdline.echo('<Referencia a objetos %s>' % ('activada' if on else 'desactivada'))
        self.osnapChanged.emit(bool(on))

    def toggle_relative(self):
        self.set_relative(not self.relative)

    def set_relative(self, on):
        self.relative = bool(on)
        set_setting('relangle', self.relative)
        self.cmdline.echo('<Ángulos relativos al último tramo %s>' % ('activado' if self.relative else 'desactivado'))
        self.relativeChanged.emit(self.relative)
        self.refresh()

    def ref_direction(self):
        return self.command.ref_direction() if self.command is not None else None

    def set_ortho(self, on):
        self.ortho = bool(on)
        set_setting('ortho', self.ortho)
        self.cmdline.echo('<Orto %s>' % ('activado' if self.ortho else 'desactivado'))
        self.orthoChanged.emit(self.ortho)
        self.refresh()

    # ------------------------------------------------------------ ratón
    def mouse_moved(self, pt, snapped, shift):
        self.cursor, self.cursor_snapped, self.shift = pt, snapped, shift
        self.refresh()

    def idle_click(self, pt, shift):
        """Designación en reposo (preselección para DESPLAZA, COPIA, GIRA...)."""
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.isSpatial():
            return
        from .editkit import GeomIO, pick_feature, query_rect
        io = GeomIO(self.canvas, layer)
        if self.idle_win is None:
            fid, _f = pick_feature(self.canvas, io, layer, pt)
            if fid is not None:
                if shift:
                    layer.deselect(fid)
                else:
                    layer.select(fid)
                self.cmdline.set_info('%d objeto(s) designado(s)' % layer.selectedFeatureCount())
                return
            self.idle_win = pt
            return
        a, self.idle_win = self.idle_win, None
        fids = query_rect(io, layer, a, pt, pt.x() < a.x())
        if shift:
            layer.deselect(fids)
        else:
            layer.select(fids)
        self.cmdline.set_info('%d objeto(s) designado(s)' % layer.selectedFeatureCount())

    def point_clicked(self, pt, snapped, shift):
        if self.command is None:
            try:
                self.idle_click(pt, shift)
            except Exception as e:  # noqa: BLE001
                self.cmdline.echo('Error: %s' % e)
            self.refresh()
            return
        self.cursor, self.cursor_snapped, self.shift = pt, snapped, shift
        p = self.effective_cursor()
        self.cmdline.echo_input('')
        try:
            self.command.on_point(p)
        except (InputError, ValueError) as e:
            self.cmdline.echo(str(e))
        except Exception as e:  # noqa: BLE001
            self.cmdline.echo('Error: %s' % e)
        self.refresh()

    def effective_cursor(self):
        """Cursor con modificación de ángulo, ORTO (Mayús lo invierte) y referencia a objetos."""
        pt = self.cursor
        if pt is None or self.command is None:
            return pt
        base = self.command.base()
        lock = self.command.angle_lock
        if base is not None and lock is not None:
            ux, uy = math.cos(lock), math.sin(lock)
            d = (pt.x() - base.x()) * ux + (pt.y() - base.y()) * uy
            return QgsPointXY(base.x() + d * ux, base.y() + d * uy)
        if self.cursor_snapped:
            return pt
        if base is not None and (self.ortho != self.shift) and not getattr(self.command, 'no_ortho', False):
            dx, dy = pt.x() - base.x(), pt.y() - base.y()
            return QgsPointXY(pt.x(), base.y()) if abs(dx) >= abs(dy) else QgsPointXY(base.x(), pt.y())
        return pt

    def resolve(self, text):
        """Texto -> ('point', QgsPointXY) o ('lock', ángulo)."""
        last = _xy(self.lastpoint) if self.lastpoint is not None else None
        pi = parse_point(text, self.units, last, self.ref_direction(), self.relative)
        if pi.kind == 'point':
            return 'point', QgsPointXY(pi.point[0], pi.point[1])
        if pi.kind == 'anglelock':
            return 'lock', pi.angle
        base = self.command.base() if self.command else None
        cur = self.effective_cursor()
        if base is None:
            raise InputError('Precise primero un punto: una distancia sola necesita un punto base.')
        if cur is None or (abs(cur.x() - base.x()) < 1e-12 and abs(cur.y() - base.y()) < 1e-12):
            raise InputError('Mueva el cursor para indicar la dirección de la distancia.')
        a = math.atan2(cur.y() - base.y(), cur.x() - base.x())
        return 'point', QgsPointXY(base.x() + pi.distance * math.cos(a), base.y() + pi.distance * math.sin(a))

    # ------------------------------------------------------------ vista previa
    def refresh(self):
        u = self.units
        cur = self.effective_cursor() if self.command else self.cursor
        if self.command is None:
            self.tool.clear()
            win = getattr(self, 'idle_win', None)
            if win is not None and cur is not None:
                rect = [win, QgsPointXY(cur.x(), win.y()), cur, QgsPointXY(win.x(), cur.y()), win]
                if cur.x() < win.x():
                    self.tool.show_temp(rect)       # captura: discontinua
                else:
                    self.tool.show_path(rect)       # ventana: continua
            self.cmdline.set_info(format_point(cur.x(), cur.y(), u) if cur is not None else '')
            return
        path, closed, temp, guide = self.command.preview(cur)
        self.tool.show_path(path, closed)
        self.tool.show_temp(temp)
        self.tool.show_guide(guide)
        ghost = getattr(self.command, 'preview_geoms', None)
        try:
            self.tool.show_ghost(ghost(cur) if ghost is not None and cur is not None else None)
        except Exception:  # noqa: BLE001 - la vista previa nunca debe interrumpir el comando
            self.tool.show_ghost(None)
        info = []
        base = self.command.base()
        if cur is not None:
            info.append(format_point(cur.x(), cur.y(), u))
            if base is not None:
                dx, dy = cur.x() - base.x(), cur.y() - base.y()
                info.append('Longitud: %s' % format_length(math.hypot(dx, dy), u))
                if dx or dy:
                    ang = math.atan2(dy, dx)
                    info.append('Ángulo: %s' % format_angle(ang, u))
                    ref = self.ref_direction()
                    if ref is not None:
                        rel = math.degrees(ang - rel_zero(ref, u))
                        if u.angdir_cw:
                            rel = -rel
                        if u.relmode == 'interior':
                            rel %= 360.0
                        else:
                            rel = (rel + 180.0) % 360.0 - 180.0
                        info.append('Rel: %s' % format_rel(rel, u))
        extra = getattr(self.command, 'info', None)
        if extra is not None:
            try:
                txt = extra(cur)
                if txt:
                    info.append(txt)
            except Exception:  # noqa: BLE001
                pass
        tags = []
        if self.ortho != self.shift:
            tags.append('ORTO')
        if self.relative:
            tags.append('REL')
        if self.command.angle_lock is not None:
            tags.append('<%s' % format_angle(self.command.angle_lock, u))
        self.cmdline.set_info('   '.join(info + (['[%s]' % ' '.join(tags)] if tags else [])))

    # ------------------------------------------------------------ geometría
    def add_feature(self, layer, pts, polygon=False, title='Dibujo CAD'):
        if polygon:
            ring = list(pts) + [pts[0]]
            geom = QgsGeometry.fromPolygonXY([ring])
        else:
            geom = QgsGeometry.fromPolylineXY(list(pts))
        return self.add_geometry(layer, geom, title)

    def add_geometries(self, layer, geoms, title='Dibujo CAD'):
        """Agrega varias geometrías (SRC del mapa) en una sola operación de deshacer."""
        if not layer.isEditable():
            layer.startEditing()
        layer.beginEditCommand(title)
        n = 0
        for g in geoms:
            g = self._conform_new(layer, g)
            if layer.addFeature(QgsVectorLayerUtils.createFeature(layer, g, {}, layer.createExpressionContext())):
                n += 1
        layer.endEditCommand()
        layer.triggerRepaint()
        return n

    def _conform_new(self, layer, geom):
        src = self.canvas.mapSettings().destinationCrs()
        if src != layer.crs():
            geom.transform(QgsCoordinateTransform(src, layer.crs(), QgsProject.instance()))
        wkb = layer.wkbType()
        if QgsWkbTypes.isMultiType(wkb) and not geom.isMultipart():
            geom.convertToMultiType()
        if QgsWkbTypes.hasZ(wkb) and not QgsWkbTypes.hasZ(geom.wkbType()):
            geom.get().addZValue(0.0)
        if QgsWkbTypes.hasM(wkb) and not QgsWkbTypes.hasM(geom.wkbType()):
            geom.get().addMValue(0.0)
        return geom

    def add_geometry(self, layer, geom, title='Dibujo CAD'):
        """Agrega una geometría (en el SRC del mapa) a la capa, adaptando SRC, multi, Z y M."""
        src = self.canvas.mapSettings().destinationCrs()
        if src != layer.crs():
            geom.transform(QgsCoordinateTransform(src, layer.crs(), QgsProject.instance()))
        wkb = layer.wkbType()
        if QgsWkbTypes.isMultiType(wkb) and not geom.isMultipart():
            geom.convertToMultiType()
        if QgsWkbTypes.hasZ(wkb) and not QgsWkbTypes.hasZ(geom.wkbType()):
            geom.get().addZValue(0.0)
        if QgsWkbTypes.hasM(wkb) and not QgsWkbTypes.hasM(geom.wkbType()):
            geom.get().addMValue(0.0)
        feat = QgsVectorLayerUtils.createFeature(layer, geom, {}, layer.createExpressionContext())
        layer.beginEditCommand(title)
        if layer.addFeature(feat):
            layer.endEditCommand()
            layer.triggerRepaint()
            return True
        layer.destroyEditCommand()
        self.cmdline.echo('No se pudo agregar el objeto a "%s".' % layer.name())
        return False


# --------------------------------------------------------------------------
class _DrawCommand:
    title = ''

    def __init__(self, mgr, layer, kind):
        self.mgr = mgr
        self.cl = mgr.cmdline
        self.layer = layer
        self.kind = kind
        self.pts = []
        self.angle_lock = None

    def base(self):
        return self.pts[-1] if self.pts else None

    def snap_points(self):
        """Vértices del dibujo en curso disponibles para la referencia a objetos."""
        return list(self.pts)

    def ref_direction(self):
        """Dirección del último tramo (para ángulos relativos y deflexiones)."""
        if len(self.pts) < 2:
            return None
        a, b = self.pts[-2], self.pts[-1]
        return math.atan2(b.y() - a.y(), b.x() - a.x())

    def end(self):
        if self.mgr.command is self:
            self.mgr.end_command()

    def _resolve_and_apply(self, text):
        kind, val = self.mgr.resolve(text)
        if kind == 'lock':
            self.angle_lock = val
            self.cl.echo('Modificación de ángulo: %s' % format_angle(val, self.mgr.units))
            self.prompt()
            return
        self.on_point(val)

    def _set_last(self, p):
        self.mgr.lastpoint = p
        self.angle_lock = None


class LineCommand(_DrawCommand):
    """LÍNEA: cada tramo es un objeto independiente, como en AutoCAD."""
    title = 'LÍNEA'

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.marks = []   # índice de la pila de deshacer tras cada tramo

    def start(self):
        if self.kind == 'polygon':
            self.cl.echo('LÍNEA dibuja en capas de líneas. Para polígonos use POLILÍNEA.')
            self.end()
            return
        self.prompt()

    def prompt(self):
        if not self.pts:
            self.cl.set_prompt('Precise primer punto')
        elif len(self.pts) < 3:
            self.cl.set_prompt('Precise punto siguiente o', [('H', 'desHacer')])
        else:
            self.cl.set_prompt('Precise punto siguiente o', [('C', 'Cerrar'), ('H', 'desHacer')])

    def on_point(self, p):
        if self.pts:
            if not self.mgr.add_feature(self.layer, [self.pts[-1], p], title='LÍNEA'):
                return
            self.marks.append(self.layer.undoStack().index())
        self.pts.append(p)
        self._set_last(p)
        self.prompt()

    def on_text(self, text):
        k = _key(text)
        if self.pts and k in OPT_UNDO:
            self.undo()
        elif len(self.pts) >= 3 and k in OPT_CLOSE:
            self.on_point(self.pts[0])
            self.mgr.last_line_end = self.pts[-1]
            self.end()
        else:
            self._resolve_and_apply(text)

    def on_enter(self):
        if not self.pts:
            if self.mgr.last_line_end is not None:
                self.on_point(self.mgr.last_line_end)   # continúa desde el último extremo
            else:
                self.end()
            return
        self.escape()

    def undo(self):
        if len(self.pts) >= 2:
            stack = self.layer.undoStack()
            if self.marks and stack.index() == self.marks[-1]:
                stack.undo()
                self.marks.pop()
                self.pts.pop()
                self._set_last(self.pts[-1])
            else:
                self.cl.echo('No se puede deshacer: la capa se modificó por otro medio.')
        else:
            self.pts = []
        self.prompt()

    def escape(self):
        if len(self.pts) >= 2:
            self.mgr.last_line_end = self.pts[-1]
        self.end()

    def preview(self, cur):
        temp = [self.pts[-1], cur] if self.pts and cur is not None else []
        return list(self.pts), False, temp, []


class PlineCommand(_DrawCommand):
    """POLILÍNEA: un único objeto (línea o polígono según la capa)."""
    title = 'POLILÍNEA'

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.length_mode = False

    def start(self):
        self.prompt()

    def prompt(self):
        if not self.pts:
            self.cl.set_prompt('Precise punto inicial')
        elif self.length_mode:
            self.cl.set_prompt('Precise longitud de línea')
        else:
            opts = [('L', 'Longitud'), ('H', 'desHacer')]
            if len(self.pts) >= 3:
                opts.insert(0, ('C', 'Cerrar'))
            self.cl.set_prompt('Precise punto siguiente o', opts)

    def on_point(self, p):
        if self.pts and abs(p.x() - self.pts[-1].x()) < 1e-12 and abs(p.y() - self.pts[-1].y()) < 1e-12:
            self.cl.echo('Punto repetido: se ignora.')
            return
        if self.length_mode:
            self.length_mode = False
        self.pts.append(p)
        self._set_last(p)
        if len(self.pts) == 1 and self.kind == 'line':
            self.cl.echo('Se dibujará en "%s".' % self.layer.name())
        self.prompt()

    def on_text(self, text):
        k = _key(text)
        if self.length_mode:
            d = parse_distance(text)
            a = self._last_direction()
            self.on_point(QgsPointXY(self.pts[-1].x() + d * math.cos(a), self.pts[-1].y() + d * math.sin(a)))
            return
        if self.pts and k in OPT_LENGTH:
            if self._last_direction() is None:
                self.cl.echo('No hay un segmento anterior que indique la dirección.')
            else:
                self.length_mode = True
            self.prompt()
        elif self.pts and k in OPT_UNDO:
            if len(self.pts) > 1:
                self.pts.pop()
                self._set_last(self.pts[-1])
            else:
                self.cl.echo('Todos los segmentos ya se han deshecho.')
            self.prompt()
        elif len(self.pts) >= 3 and k in OPT_CLOSE:
            self.finish(closed=True)
        else:
            self._resolve_and_apply(text)

    def _last_direction(self):
        if len(self.pts) < 2:
            return None
        a, b = self.pts[-2], self.pts[-1]
        return math.atan2(b.y() - a.y(), b.x() - a.x())

    def on_enter(self):
        if self.length_mode:
            self.length_mode = False
            self.prompt()
            return
        self.finish(closed=False)

    def finish(self, closed=False):
        n = len(self.pts)
        if self.kind == 'polygon':
            if n >= 3:
                self.mgr.add_feature(self.layer, self.pts, polygon=True, title='POLILÍNEA')
            elif n:
                self.cl.echo('Un polígono necesita al menos 3 vértices: no se creó el objeto.')
        elif n >= 2:
            pts = self.pts + [self.pts[0]] if closed else self.pts
            self.mgr.add_feature(self.layer, pts, title='POLILÍNEA')
        if n:
            self.mgr.last_line_end = self.pts[0] if closed else self.pts[-1]
            self.mgr.lastpoint = self.mgr.last_line_end
        self.end()

    def escape(self):
        self.finish(closed=False)

    def preview(self, cur):
        temp = [self.pts[-1], cur] if self.pts and cur is not None and not self.length_mode else []
        guide = [cur, self.pts[0]] if self.kind == 'polygon' and len(self.pts) >= 2 and cur is not None else []
        return list(self.pts), False, temp, guide
