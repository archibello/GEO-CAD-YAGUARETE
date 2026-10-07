# -*- coding: utf-8 -*-
"""
Texto CAD: TEXTO (DTEXT) y EDITTEXTO al estilo AutoCAD.

Los textos son puntos de una capa con los campos TEXTO, FUENTE, ALTURA,
ROTACION, NEGRITA y JUST; QGIS los dibuja con etiquetas cuya altura está en
unidades del mapa (como la altura de texto de AutoCAD).
"""

import math
import os

from qgis.PyQt.QtCore import QPointF, QRectF
from qgis.PyQt.QtGui import QColor, QFont, QFontMetricsF
from qgis.core import (QgsCoordinateTransform, QgsFeature, QgsField, QgsFields, QgsGeometry,
                       QgsPalLayerSettings, QgsPointXY, QgsProject, QgsProperty, QgsTextFormat,
                       QgsVectorFileWriter, QgsVectorLayer, QgsVectorLayerSimpleLabeling,
                       QgsVectorLayerUtils)
from qgis.gui import QgsMapCanvasItem

from .commands import _DrawCommand, _key
from .compat import enum, geometry_kind, qt
from .settings import SCOPE
from .units import InputError, format_angle, format_length, parse_angle, parse_distance

TEXT_FIELDS = [('TEXTO', 'string', 254), ('FUENTE', 'string', 80), ('ALTURA', 'double', 0),
               ('ROTACION', 'double', 0), ('NEGRITA', 'integer', 0), ('JUST', 'string', 4),
               ('COLOR', 'string', 20)]      # '' = PorCapa; '#rrggbb' = color propio del texto
TEXT_FLAG = 'dibujo_cad/text_layer'
CAP_FACTOR = 1.43          # altura de mayúscula (AutoCAD) -> tamaño de fuente
LINE_SPACING = 1.6667      # interlineado de AutoCAD
SIZES = ['0.10', '0.18', '0.25', '0.35', '0.50', '0.70', '1.00', '1.50', '2.00', '2.50',
         '3.00', '3.50', '5.00', '7.00', '10.00', '15.00', '20.00', '25.00', '50.00']

# justificación AutoCAD -> (horizontal, vertical)
JUST = {
    'I': ('Left', 'Base'), 'C': ('Center', 'Base'), 'D': ('Right', 'Base'), 'M': ('Center', 'Half'),
    'SI': ('Left', 'Cap'), 'SC': ('Center', 'Cap'), 'SD': ('Right', 'Cap'),
    'MI': ('Left', 'Half'), 'MC': ('Center', 'Half'), 'MD': ('Right', 'Half'),
    'II': ('Left', 'Bottom'), 'IC': ('Center', 'Bottom'), 'ID': ('Right', 'Bottom'),
}
JUST_NAMES = {'I': 'Izquierda', 'C': 'Centro', 'D': 'Derecha', 'M': 'Medio',
              'SI': 'Superior izquierda', 'SC': 'Superior centro', 'SD': 'Superior derecha',
              'MI': 'Medio izquierda', 'MC': 'Medio centro', 'MD': 'Medio derecha',
              'II': 'Inferior izquierda', 'IC': 'Inferior centro', 'ID': 'Inferior derecha'}
JUST_ALIASES = {'IZQUIERDA': 'I', 'L': 'I', 'LEFT': 'I', 'CENTRO': 'C', 'CENTER': 'C',
                'DERECHA': 'D', 'R': 'D', 'RIGHT': 'D', 'MEDIO': 'M', 'MIDDLE': 'M',
                'TL': 'SI', 'TC': 'SC', 'TR': 'SD', 'ML': 'MI', 'MR': 'MD',
                'BL': 'II', 'BC': 'IC', 'BR': 'ID'}


# ---------------------------------------------------------------- estilo actual
class TextStyle:
    """Estilo de texto actual (fuente, altura, negrita, justificación), guardado en el proyecto."""

    def __init__(self):
        p = QgsProject.instance()
        self.font = p.readEntry(SCOPE, 'textfont', 'Arial')[0] or 'Arial'
        self.height = p.readDoubleEntry(SCOPE, 'textsize', 2.5)[0] or 2.5
        self.bold = bool(p.readBoolEntry(SCOPE, 'textbold', False)[0])
        self.just = p.readEntry(SCOPE, 'textjust', 'I')[0] or 'I'
        self.color = p.readEntry(SCOPE, 'textcolor', '')[0] or ''     # '' = PorCapa

    def save(self):
        p = QgsProject.instance()
        p.writeEntry(SCOPE, 'textfont', self.font)
        if hasattr(p, 'writeEntryDouble'):
            p.writeEntryDouble(SCOPE, 'textsize', float(self.height))
        else:
            p.writeEntry(SCOPE, 'textsize', float(self.height))
        if hasattr(p, 'writeEntryBool'):
            p.writeEntryBool(SCOPE, 'textbold', bool(self.bold))
        else:
            p.writeEntry(SCOPE, 'textbold', bool(self.bold))
        p.writeEntry(SCOPE, 'textjust', self.just)
        p.writeEntry(SCOPE, 'textcolor', self.color or '')


# ---------------------------------------------------------------- capa de textos
def _label_prop(name):
    prop = getattr(QgsPalLayerSettings, 'Property', None)
    if prop is not None and hasattr(prop, name):
        return getattr(prop, name)
    return getattr(QgsPalLayerSettings, name)


def _map_units():
    try:
        from qgis.core import Qgis
        return Qgis.RenderUnit.MapUnits
    except AttributeError:
        from qgis.core import QgsUnitTypes
        return QgsUnitTypes.RenderMapUnits


def _field(name, typ, length):
    try:
        from qgis.PyQt.QtCore import QMetaType
        t = {'string': QMetaType.Type.QString, 'double': QMetaType.Type.Double,
             'integer': QMetaType.Type.Int}[typ]
        return QgsField(name, t, len=length)
    except (ImportError, AttributeError, TypeError):
        from qgis.PyQt.QtCore import QVariant
        t = {'string': QVariant.String, 'double': QVariant.Double, 'integer': QVariant.Int}[typ]
        return QgsField(name, t, len=length)


def is_text_layer(layer):
    return (isinstance(layer, QgsVectorLayer) and geometry_kind(layer) == 'point'
            and layer.fields().indexOf('TEXTO') != -1)


def text_color_expression(bylayer_expr, dark, has_color_field=True):
    """Color de etiqueta: el COLOR propio del texto si lo tiene; si no, el de su capa (bylayer_expr).
    El negro (#000000) se comporta como el color 7 de AutoCAD: blanco sobre fondo oscuro."""
    if not has_color_field:
        return bylayer_expr
    bw_screen = '255,255,255,255' if dark else '0,0,0,255'
    return ("CASE WHEN coalesce(\"COLOR\", '') = '' THEN %s "
            "WHEN @layout_name IS NOT NULL AND @cad_ctb = 'monochrome' THEN '0,0,0,255' "
            "WHEN lower(\"COLOR\") = '#000000' THEN "
            "CASE WHEN @layout_name IS NULL THEN '%s' ELSE '0,0,0,255' END "
            "WHEN @layout_name IS NOT NULL AND @cad_ctb = 'grayscale' THEN color_grayscale_average(\"COLOR\") "
            "ELSE \"COLOR\" END" % (bylayer_expr, bw_screen))


def setup_labels(layer):
    """Etiquetas: texto con altura en unidades de mapa, fuente, negrita, giro y justificación."""
    s = QgsPalLayerSettings()
    s.fieldName = 'TEXTO'
    s.isExpression = False
    fmt = QgsTextFormat()
    fmt.setFont(QFont('Arial'))
    fmt.setSize(2.5)
    fmt.setSizeUnit(_map_units())
    fmt.setColor(QColor(0, 0, 0))
    s.setFormat(fmt)
    # Sin Administrador de capas: blanco sobre fondo oscuro, negro sobre claro; negro en papel
    try:
        from qgis.utils import iface as _iface
        dark = _iface.mapCanvas().canvasColor().lightness() < 128
    except Exception:  # noqa: BLE001
        dark = False
    color_expr = text_color_expression(
        "CASE WHEN @layout_name IS NULL THEN '%s' ELSE '0,0,0,255' END"
        % ('255,255,255,255' if dark else '0,0,0,255'), dark, layer.fields().indexOf('COLOR') != -1)
    try:
        from qgis.core import Qgis
        s.placement = Qgis.LabelPlacement.OverPoint
    except AttributeError:
        s.placement = QgsPalLayerSettings.OverPoint
    hali = "CASE " + " ".join("WHEN \"JUST\" = '%s' THEN '%s'" % (k, v[0]) for k, v in JUST.items()) + " ELSE 'Left' END"
    vali = "CASE " + " ".join("WHEN \"JUST\" = '%s' THEN '%s'" % (k, v[1]) for k, v in JUST.items()) + " ELSE 'Base' END"
    dd = s.dataDefinedProperties()
    dd.setProperty(_label_prop('Size'), QgsProperty.fromExpression('coalesce("ALTURA", 2.5) * %s' % CAP_FACTOR))
    dd.setProperty(_label_prop('Family'), QgsProperty.fromExpression("coalesce(\"FUENTE\", 'Arial')"))
    dd.setProperty(_label_prop('Bold'), QgsProperty.fromExpression('coalesce("NEGRITA", 0) = 1'))
    dd.setProperty(_label_prop('PositionX'), QgsProperty.fromExpression('x($geometry)'))
    dd.setProperty(_label_prop('PositionY'), QgsProperty.fromExpression('y($geometry)'))
    dd.setProperty(_label_prop('Hali'), QgsProperty.fromExpression(hali))
    dd.setProperty(_label_prop('Vali'), QgsProperty.fromExpression(vali))
    dd.setProperty(_label_prop('LabelRotation'), QgsProperty.fromExpression('-coalesce("ROTACION", 0)'))
    try:
        dd.setProperty(_label_prop('Color'), QgsProperty.fromExpression(color_expr))
    except Exception:  # noqa: BLE001
        pass
    s.setDataDefinedProperties(dd)
    try:
        from qgis.core import Qgis
        s.placementSettings().setOverlapHandling(Qgis.LabelOverlapHandling.AllowOverlapAtNoCost)
    except AttributeError:
        s.displayAll = True
    try:
        s.obstacleSettings().setIsObstacle(False)
    except AttributeError:
        pass
    layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
    layer.setLabelsEnabled(True)
    try:
        from qgis.core import QgsNullSymbolRenderer
        if layer.customProperty('cad_layer_manager/config') is None:
            layer.setRenderer(QgsNullSymbolRenderer())   # sin marcador de punto (como AutoCAD)
    except ImportError:
        pass
    layer.setCustomProperty(TEXT_FLAG, '1')
    layer.triggerRepaint()


def ensure_fields(layer):
    missing = [_field(n, t, l) for n, t, l in TEXT_FIELDS if layer.fields().indexOf(n) == -1]
    if missing:
        layer.dataProvider().addAttributes(missing)
        layer.updateFields()


def adopt_layer_manager(iface, layer):
    """Si está instalado Layer Properties, la capa de textos pasa a tener capas CAD
    (campo LAYER_CODE): cada texto toma el color de su capa y se adapta al fondo."""
    try:
        if layer is None or layer.customProperty('cad_layer_manager/config'):
            return
        from qgis.utils import plugins
        ctrl = getattr(plugins.get('Layer_Properties'), 'ctrl', None)
    except Exception:  # noqa: BLE001
        return
    if ctrl is None:
        return
    prev = iface.activeLayer()
    try:
        ctrl.attach(layer)
        ctrl.ensure_initialized()
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            ctrl.attach(prev)
        except Exception:  # noqa: BLE001
            pass


def adopt_all_text_layers(iface):
    for lyr in list(QgsProject.instance().mapLayers().values()):
        if isinstance(lyr, QgsVectorLayer) and lyr.customProperty(TEXT_FLAG) == '1':
            adopt_layer_manager(iface, lyr)


def find_or_create_text_layer(iface, echo):
    """Capa de textos: la activa si sirve, una ya marcada en el proyecto o una nueva."""
    from .auxlayers import find_or_create
    active = iface.activeLayer()
    if isinstance(active, QgsVectorLayer) and geometry_kind(active) == 'point' \
            and active.customProperty('dibujo_cad/point_layer') != '1':
        if not is_text_layer(active):
            ensure_fields(active)
            echo('Campos de texto agregados a "%s".' % active.name())
        if active.customProperty(TEXT_FLAG) != '1':
            setup_labels(active)
        ensure_fields(active)
        adopt_layer_manager(iface, active)
        return active
    lyr = find_or_create(iface, 'Textos CAD', 'textos_cad', TEXT_FLAG, TEXT_FIELDS, echo,
                         setup=setup_labels)
    if lyr.fields().indexOf('COLOR') == -1:
        ensure_fields(lyr)
        refresh_text_colors(lyr)
    adopt_layer_manager(iface, lyr)
    return lyr


# ---------------------------------------------------------------- vista previa
class TextPreview(QgsMapCanvasItem):
    """Dibuja en vivo el texto que se está escribiendo, con su altura real."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas_ = canvas
        self.pt = None
        self.text = ''
        self.height = 2.5
        self.angle = 0.0
        self.font = 'Arial'
        self.bold = False
        self.just = 'I'
        self.cursor_box = True
        self.setZValue(1000)

    def set(self, pt, text, height, angle, font, bold, just):
        self.pt, self.text, self.height, self.angle = pt, text, height, angle
        self.font, self.bold, self.just = font, bold, just
        self.updatePosition()
        self.update()

    def clear(self):
        self.pt = None
        self.update()

    def updatePosition(self):
        if self.pt is not None:
            self.setPos(self.toCanvasCoordinates(self.pt))

    def boundingRect(self):
        return QRectF(-4000, -4000, 8000, 8000)

    def paint(self, painter, option=None, widget=None):
        if self.pt is None:
            return
        mupp = self.canvas_.mapUnitsPerPixel() or 1.0
        px = max(1.0, self.height * CAP_FACTOR / mupp)
        f = QFont(self.font)
        f.setPixelSize(int(max(1, min(px, 3000))))
        f.setBold(self.bold)
        fm = QFontMetricsF(f)
        txt = self.text or ''
        w = fm.horizontalAdvance(txt) if hasattr(fm, 'horizontalAdvance') else fm.width(txt)
        h, v = JUST.get(self.just, ('Left', 'Base'))
        x = {'Left': 0.0, 'Center': -w / 2.0, 'Right': -w}[h]
        cap = fm.capHeight() if hasattr(fm, 'capHeight') else fm.ascent() * 0.7
        y = {'Base': 0.0, 'Bottom': -fm.descent(), 'Half': cap / 2.0, 'Cap': cap, 'Top': fm.ascent()}[v]
        painter.save()
        painter.rotate(-math.degrees(self.angle))
        painter.setFont(f)
        color = QColor(255, 255, 255) if self.canvas_.canvasColor().lightness() < 128 else QColor(0, 0, 0)
        painter.setPen(color)
        painter.drawText(QPointF(x, y), txt)
        # cursor de texto (como el cuadro de AutoCAD)
        painter.setPen(QColor(0, 160, 255))
        painter.drawRect(QRectF(x + w + 1, y - cap, max(2.0, cap * 0.5), cap))
        painter.restore()


# ---------------------------------------------------------------- comandos
class DTextCommand(_DrawCommand):
    """TEXTO (DTEXT): texto en una línea, varias líneas sucesivas."""
    title = 'TEXTO'

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.style = mgr.text_style
        self.state = 'start'
        self.start_pt = None
        self.height = self.style.height
        self.rot = 0.0
        self.preview_item = None
        self.created = 0
        self.text_mode = False

    def start(self):
        iface = self.mgr.iface
        prev = iface.activeLayer()
        try:
            self.layer = find_or_create_text_layer(iface, self.cl.echo)
            # al crear la capa de textos QGIS la deja activa: se vuelve a la capa de trabajo
            if prev is not None and prev is not self.layer and iface.activeLayer() is not prev:
                iface.setActiveLayer(prev)
        except Exception as e:  # noqa: BLE001
            self.cl.echo('No se pudo preparar la capa de textos: %s' % e)
            self.end()
            return
        if not self.layer.isEditable():
            self.layer.startEditing()
        self.io_ct = None
        ccrs = self.mgr.canvas.mapSettings().destinationCrs()
        if ccrs != self.layer.crs():
            self.io_ct = QgsCoordinateTransform(ccrs, self.layer.crs(), QgsProject.instance())
        u = self.mgr.units
        self.cl.echo('Estilo de texto actual: "%s%s"  Altura de texto: %s  Justificar: %s'
                     % (self.style.font, ' Negrita' if self.style.bold else '',
                        format_length(self.style.height, u), JUST_NAMES.get(self.style.just, 'Izquierda')))
        self.preview_item = TextPreview(self.mgr.canvas)
        self.cl.input.textChanged.connect(self._typed)
        self.prompt()

    def cleanup(self):
        try:
            self.cl.input.textChanged.disconnect(self._typed)
        except (TypeError, RuntimeError):
            pass
        if self.preview_item is not None:
            self.preview_item.clear()
            try:
                self.mgr.canvas.scene().removeItem(self.preview_item)
            except Exception:  # noqa: BLE001
                pass
            self.preview_item = None
        self.cl.raw_mode = False

    def prompt(self):
        u, st = self.mgr.units, self.state
        self.text_mode = st == 'text'
        self.cl.raw_mode = self.text_mode
        if st == 'start':
            self.cl.set_prompt('Precise punto inicial de texto o', [('J', 'Justificar')])
        elif st == 'just':
            self.cl.set_prompt('Indique una opción', [(k, k if len(k) == 2 else JUST_NAMES[k]) for k in
                                                     ('I', 'C', 'D', 'M', 'SI', 'SC', 'SD', 'MI', 'MC',
                                                      'MD', 'II', 'IC', 'ID')])
        elif st == 'height':
            self.cl.set_prompt('Precise altura', None, format_length(self.height, u))
        elif st == 'rot':
            self.cl.set_prompt('Precise ángulo de rotación de texto', None, format_angle(self.rot, u))
        elif st == 'text':
            self.cl.set_prompt('Escriba texto (Intro en línea vacía para terminar)')
            try:
                self.cl.input.setFocus()      # la escritura no pasa por los atajos de QGIS
            except Exception:  # noqa: BLE001
                pass
        self._update_preview(self.mgr.effective_cursor())

    def base(self):
        return self.start_pt if self.state in ('height', 'rot') else None

    def snap_points(self):
        return [self.start_pt] if self.start_pt is not None else []

    # -- entrada
    def on_point(self, p):
        st = self.state
        if st == 'start':
            self.start_pt = p
            self._set_last(p)
            self.state = 'height'
        elif st == 'height':
            h = math.hypot(p.x() - self.start_pt.x(), p.y() - self.start_pt.y())
            if h <= 0:
                raise InputError('La altura debe ser mayor que cero.')
            self._set_height(h)
            self.state = 'rot'
        elif st == 'rot':
            self.rot = math.atan2(p.y() - self.start_pt.y(), p.x() - self.start_pt.x())
            self.state = 'text'
        elif st == 'text':
            # clic durante la escritura: la próxima línea empieza en ese punto (como AutoCAD)
            pending = self.cl.input.text()
            if pending.strip():
                self.cl.input.clear()
                self._create(pending)
            self.start_pt = p
        self.prompt()

    def on_text(self, text):
        st, k = self.state, _key(text)
        if st == 'text':
            self._create(text)
            self._next_line()
        elif st == 'start' and k in ('J', 'JUSTIFICAR', 'JUSTIFY'):
            self.state = 'just'
        elif st == 'just':
            code = JUST_ALIASES.get(k, k)
            if code not in JUST:
                raise InputError('Opción de justificación no válida.')
            self.style.just = code
            self.style.save()
            self.state = 'start'
        elif st == 'height':
            h = parse_distance(text)
            if h <= 0:
                raise InputError('La altura debe ser mayor que cero.')
            self._set_height(h)
            self.state = 'rot'
        elif st == 'rot':
            self.rot = parse_angle(text, self.mgr.units)
            self.state = 'text'
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def on_enter(self):
        st = self.state
        if st == 'height':
            self.state = 'rot'
        elif st == 'rot':
            self.state = 'text'
        elif st == 'just':
            self.state = 'start'
        elif st == 'start':
            self.end()
            return
        elif st == 'text':
            self.end()           # Intro en línea vacía termina
            return
        self.prompt()

    def escape(self):
        self.end()

    def end(self):
        if self.created:
            self.cl.echo('%d texto(s) creado(s) en "%s".' % (self.created, self.layer.name()))
        super().end()

    # -- utilidades
    def _set_height(self, h):
        self.height = h
        self.style.height = h
        self.style.save()
        self.mgr.textStyleChanged.emit()

    def _next_line(self):
        d = self.height * LINE_SPACING
        a = self.rot - math.pi / 2.0
        self.start_pt = QgsPointXY(self.start_pt.x() + d * math.cos(a), self.start_pt.y() + d * math.sin(a))

    def _create(self, text):
        if not text.strip():
            return
        p = self.start_pt
        if self.io_ct is not None:
            p = self.io_ct.transform(p)
        f = QgsVectorLayerUtils.createFeature(self.layer, QgsGeometry.fromPointXY(p), {},
                                             self.layer.createExpressionContext())
        rot_deg = math.degrees(self.rot) % 360.0
        vals = {'TEXTO': text, 'FUENTE': self.style.font, 'ALTURA': float(self.height),
                'ROTACION': round(rot_deg, 8), 'NEGRITA': 1 if self.style.bold else 0,
                'JUST': self.style.just, 'COLOR': self.style.color or None}
        for name, v in vals.items():
            idx = self.layer.fields().indexOf(name)
            if idx != -1:
                f.setAttribute(idx, v)
        self.layer.beginEditCommand('TEXTO')
        ok = self.layer.addFeature(f)
        self.layer.endEditCommand()
        if ok:
            self.created += 1
            self.layer.triggerRepaint()

    def _typed(self, text):
        if self.state == 'text':
            self._update_preview(None)

    def _update_preview(self, cur):
        item = self.preview_item
        if item is None:
            return
        st = self.state
        if st == 'text' and self.start_pt is not None:
            item.set(self.start_pt, self.cl.input.text(), self.height, self.rot,
                     self.style.font, self.style.bold, self.style.just)
        elif st == 'height' and cur is not None:
            h = math.hypot(cur.x() - self.start_pt.x(), cur.y() - self.start_pt.y()) or self.height
            item.set(self.start_pt, 'AaBb', h, self.rot, self.style.font, self.style.bold, self.style.just)
        elif st == 'rot' and cur is not None:
            a = math.atan2(cur.y() - self.start_pt.y(), cur.x() - self.start_pt.x())
            item.set(self.start_pt, 'AaBb', self.height, a, self.style.font, self.style.bold, self.style.just)
        else:
            item.clear()

    def preview(self, cur):
        self._update_preview(cur)
        if self.state in ('height', 'rot') and cur is not None:
            return [], False, [self.start_pt, cur], []
        return [], False, [], []


class EditTextCommand(_DrawCommand):
    """EDITTEXTO (DDEDIT): designar un texto y modificarlo."""
    title = 'EDITTEXTO'

    def start(self):
        self.text_mode = False
        self.target = None
        self.prompt()

    def prompt(self):
        if self.target is None:
            self.text_mode = False
            self.cl.raw_mode = False
            self.cl.set_prompt('Designe un texto o', [('H', 'desHacer')])
        else:
            self.text_mode = True
            self.cl.raw_mode = True
            self.cl.set_prompt('Nuevo texto', None, self.target[2])
            self.cl.input.setText(self.target[2])
            self.cl.input.selectAll()

    def on_point(self, p):
        from .editkit import GeomIO, pick_feature
        layers = [l for l in self.mgr.canvas.layers() if is_text_layer(l)]
        best = None
        for lyr in layers:
            fid, f = pick_feature(self.mgr.canvas, GeomIO(self.mgr.canvas, lyr), lyr, p)
            if fid is not None:
                best = (lyr, fid, str(f['TEXTO'] or ''))
                break
        if best is None:
            self.cl.echo('No se ha encontrado ningún texto.')
            return
        self.target = best
        self.prompt()

    def on_text(self, text):
        if self.target is None:
            if _key(text) in ('H', 'U'):
                self.cl.echo('Use Ctrl+Z para deshacer la última edición.')
                return
            self._resolve_and_apply(text)
            return
        lyr, fid, old = self.target
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.beginEditCommand('EDITTEXTO')
        lyr.changeAttributeValue(fid, lyr.fields().indexOf('TEXTO'), text)
        lyr.endEditCommand()
        lyr.triggerRepaint()
        self.target = None
        self.cl.input.clear()
        self.prompt()

    def on_enter(self):
        if self.target is not None:
            self.target = None
            self.cl.input.clear()
            self.prompt()
            return
        self.end()

    def escape(self):
        self.end()

    def preview(self, cur):
        return [], False, [], []


def apply_style_to_selection(iface, style, what):
    """Aplica fuente / altura / negrita a los textos seleccionados (como la paleta Propiedades)."""
    n = 0
    for lyr in QgsProject.instance().mapLayers().values():
        if not is_text_layer(lyr) or not lyr.selectedFeatureCount():
            continue
        values = {'font': ('FUENTE', style.font), 'height': ('ALTURA', float(style.height)),
                  'bold': ('NEGRITA', 1 if style.bold else 0),
                  'color': ('COLOR', style.color or None)}[what]
        if what == 'color' and lyr.fields().indexOf('COLOR') == -1:
            ensure_fields(lyr)
            refresh_text_colors(lyr)
        idx = lyr.fields().indexOf(values[0])
        if idx == -1:
            continue
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.beginEditCommand('Estilo de texto')
        for fid in lyr.selectedFeatureIds():
            lyr.changeAttributeValue(fid, idx, values[1])
            n += 1
        lyr.endEditCommand()
        lyr.triggerRepaint()
    return n


def refresh_text_colors(layer):
    """Vuelve a armar el color de las etiquetas (p. ej. tras agregar el campo COLOR)."""
    try:
        from qgis.utils import plugins
        ctrl = getattr(plugins.get('Layer_Properties'), 'ctrl', None)
    except Exception:  # noqa: BLE001
        ctrl = None
    if ctrl is not None and layer.customProperty('cad_layer_manager/config'):
        try:
            ctrl._apply_to(layer, ctrl._load(layer))
            return
        except Exception:  # noqa: BLE001
            pass
    setup_labels(layer)


__all__ = ['DTextCommand', 'EditTextCommand', 'TextStyle', 'SIZES', 'apply_style_to_selection',
           'QgsFeature', 'QgsFields', 'enum', 'qt']
