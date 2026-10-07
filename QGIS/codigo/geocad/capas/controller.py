# -*- coding: utf-8 -*-
"""
Modelo y lógica de "capas CAD" dentro de una capa vectorial de QGIS.

Cada capa CAD es un valor del campo LAYER_CODE. La configuración (orden,
propiedades, capa actual y estados de capa) se guarda como propiedad
personalizada de la capa QGIS, por lo que viaja con el proyecto (.qgz).
"""

import copy
import fnmatch
import json
import os
import time

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis, QgsCategorizedSymbolRenderer, QgsDefaultValue, QgsEditorWidgetSetup,
    QgsExpression, QgsFeatureRequest, QgsFillSymbol, QgsLineSymbol,
    QgsMarkerSymbol, QgsProperty, QgsRendererCategory, QgsSettings,
    QgsSimpleLineSymbolLayer, QgsSimpleMarkerSymbolLayer, QgsVectorLayer,
)

from .aci import aci_to_hex, color_hex
from .compat import geometry_kind, qt, render_mm, string_field, symbol_property, enum
from .linetypes import (LEGACY_LINETYPES, LINETYPES, LW_DEFAULT, has_dots,
                        lineweight_mm)

FIELD = 'LAYER_CODE'
PROP_KEY = 'cad_layer_manager/config'
SETTINGS = 'cad_layer_manager/'
NAME_EXPR = 'if(coalesce("%s", \'\') = \'\', \'0\', "%s")' % (FIELD, FIELD)
INVALID_CHARS = '<>/\\":;?*|=`,'
STATE_PROPS = ('on', 'frozen', 'locked', 'plot', 'color', 'linetype',
               'lineweight', 'transparency')


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------
DEBUG_LOG = os.path.join(os.path.dirname(__file__), 'lp_debug.log')


DEBUG = False      # True: registro de diagnóstico en lp_debug.log y en la pestaña 'Capas CAD'


def dlog(msg):
    if not DEBUG:
        return
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + str(msg)
    try:
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:  # noqa: BLE001
        pass
    try:
        from qgis.core import QgsMessageLog
        QgsMessageLog.logMessage(str(msg), 'Capas CAD')
    except Exception:  # noqa: BLE001
        pass


def _remove_old_log():
    try:
        if os.path.exists(DEBUG_LOG):
            os.remove(DEBUG_LOG)
    except OSError:
        pass


if not DEBUG:
    _remove_old_log()


def is_null(v):
    if v is None:
        return True
    try:
        if hasattr(v, 'isNull') and v.isNull():
            return True
    except Exception:
        pass
    return str(v) in ('', 'NULL')


def norm_name(v):
    return '0' if is_null(v) else str(v)


def new_layer(name, **kw):
    lay = {
        'name': name, 'description': '', 'on': True, 'frozen': False,
        'locked': False, 'plot': True, 'color': {'aci': 7, 'rgb': None},
        'linetype': 'Continuous', 'lineweight': LW_DEFAULT, 'transparency': 0,
    }
    lay.update(kw)
    return lay


def _legacy_layer(code, p):
    return new_layer(
        code,
        description=p.get('label', ''),
        color={'aci': None, 'rgb': p.get('color', '#000000').lower()},
        linetype=LEGACY_LINETYPES.get(p.get('tipo', 'solid'), 'Continuous'),
        lineweight=float(p.get('espesor', LW_DEFAULT)),
    )


def normalize_config(data, ensure_zero=True):
    """Convierte cualquier formato conocido (v1, v2, lista) en config v2."""
    cfg = {'version': 2, 'current': '0', 'layers': [], 'states': {}}
    if isinstance(data, dict) and 'layers' in data:
        cfg['current'] = str(data.get('current', '0'))
        cfg['states'] = data.get('states', {}) or {}
        layers = data.get('layers', [])
    elif isinstance(data, list):
        layers = data
    elif isinstance(data, dict):  # formato v1 {codigo: {label, color, espesor, tipo}}
        layers = [_legacy_layer(c, p) for c, p in data.items()
                  if c != 'NULL' and isinstance(p, dict)]
    else:
        layers = []
    seen = set()
    for raw in layers:
        if not isinstance(raw, dict) or not raw.get('name'):
            continue
        lay = new_layer(str(raw['name']))
        for k in lay:
            if k in raw:
                lay[k] = raw[k]
        if lay['linetype'] not in LINETYPES:
            lay['linetype'] = LEGACY_LINETYPES.get(lay['linetype'], 'Continuous')
        if not isinstance(lay['color'], dict):
            lay['color'] = {'aci': 7, 'rgb': None}
        if lay['name'].lower() in seen:
            continue
        seen.add(lay['name'].lower())
        cfg['layers'].append(lay)
    if ensure_zero and '0' not in [l['name'] for l in cfg['layers']]:
        cfg['layers'].append(new_layer('0'))
    if cfg['current'] not in [l['name'] for l in cfg['layers']]:
        cfg['current'] = '0'  # se valida al usarla
    return cfg


def _no_geometry_flag():
    try:
        return Qgis.FeatureRequestFlag.NoGeometry
    except AttributeError:
        return enum(QgsFeatureRequest, 'Flag', 'NoGeometry')


def _level(name):
    ml = getattr(Qgis, 'MessageLevel', None)
    if ml is not None and hasattr(ml, name):
        return getattr(ml, name)
    return getattr(Qgis, name)


# --------------------------------------------------------------------------
# controlador
# --------------------------------------------------------------------------
def override_color_expression(field, bylayer_expr, dark):
    """Color propio del objeto ('#rrggbb') o, si está vacío, el de su capa CAD.
    El negro se comporta como el color 7 (blanco sobre fondo oscuro, negro en papel)."""
    bw = '255,255,255,255' if dark else '0,0,0,255'
    f = '"%s"' % field
    return ("CASE WHEN coalesce(%s, '') = '' THEN %s "
            "WHEN @layout_name IS NOT NULL AND @cad_ctb = 'monochrome' THEN '0,0,0,255' "
            "WHEN lower(%s) = '#000000' THEN CASE WHEN @layout_name IS NULL THEN '%s' ELSE '0,0,0,255' END "
            "WHEN @layout_name IS NOT NULL AND @cad_ctb = 'grayscale' THEN color_grayscale_average(%s) "
            "ELSE %s END" % (f, bylayer_expr, f, bw, f, f))


class CadLayerController(QObject):
    changed = pyqtSignal()            # cambió la configuración de capas
    attachedChanged = pyqtSignal()    # cambió la capa QGIS gestionada
    selectionChanged = pyqtSignal()   # cambió la selección de objetos

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.layer = None
        self.cfg = None
        self._history = {}
        self._iso_backup = {}
        self._applying = False
        self._sel_guard = False
        self._undo_pending = False
        self._reconcile_pending = False
        self.settings = QgsSettings()
        iface.currentLayerChanged.connect(self.attach)
        # selección en cualquier capa (no sólo la activa): actualiza la lista desplegable
        try:
            iface.mapCanvas().selectionChanged.connect(self._on_any_selection)
        except Exception:  # noqa: BLE001
            pass
        # Fondo del mapa: el color 7 (y el negro, si se trata como 7) se adapta solo
        self._bg_timer = QTimer()
        self._bg_timer.setSingleShot(True)
        self._bg_timer.setInterval(200)
        self._bg_timer.timeout.connect(self._background_changed)
        self._last_dark = self._canvas_is_dark()
        # al abrir un proyecto: textos y bloques toman el color de su capa CAD
        try:
            iface.projectRead.connect(self._apply_all_later)
        except Exception:  # noqa: BLE001
            pass
        QTimer.singleShot(0, self._apply_all)
        for sig in self._background_signals():
            try:
                sig.connect(self._bg_timer.start)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ ajustes
    def setting(self, key, default, typ):
        try:
            return self.settings.value(SETTINGS + key, default, type=typ)
        except TypeError:
            v = self.settings.value(SETTINGS + key, default)
            return typ(v) if v is not None else default

    def set_setting(self, key, value):
        self.settings.setValue(SETTINGS + key, value)

    @property
    def lwdisplay(self):
        return self.setting('lwdisplay', True, bool)

    @property
    def ltscale(self):
        return self.setting('ltscale', 1.0, float)

    @property
    def lockfade(self):
        return self.setting('lockfade', 50, int)

    def set_global(self, key, value):
        self.set_setting(key, value)
        for lyr in self._managed_layers():
            self._apply_to(lyr, self._load(lyr))
        self.changed.emit()

    def _managed_layers(self):
        from qgis.core import QgsProject
        out = []
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.customProperty(PROP_KEY):
                out.append(lyr)
        return out

    # ------------------------------------------------------------ mensajes
    def msg(self, text, level='Info', duration=4):
        self.iface.messageBar().pushMessage('Capas CAD', text, _level(level), duration)

    def warn(self, text):
        self.msg(text, 'Warning', 5)

    # ------------------------------------------------------------ enlace
    def attach(self, layer=None):
        self._disconnect()
        self.layer, self.cfg = None, None
        if (isinstance(layer, QgsVectorLayer) and layer.isSpatial()
                and geometry_kind(layer) in ('line', 'polygon', 'point')):
            self.layer = layer
            self.cfg = self._load(layer)
            self._reconcile()
            layer.selectionChanged.connect(self._on_selection)
            layer.geometryChanged.connect(self._on_geometry_changed)
            layer.attributeValueChanged.connect(self._on_attr_changed)
            layer.styleChanged.connect(self._on_style_changed)
            layer.willBeDeleted.connect(self._on_deleted)
        self.attachedChanged.emit()
        self.changed.emit()
        self.selectionChanged.emit()

    def _disconnect(self):
        if self.layer is None:
            return
        try:
            pairs = ((self.layer.selectionChanged, self._on_selection),
                     (self.layer.geometryChanged, self._on_geometry_changed),
                     (self.layer.attributeValueChanged, self._on_attr_changed),
                     (self.layer.styleChanged, self._on_style_changed),
                     (self.layer.willBeDeleted, self._on_deleted))
        except RuntimeError:        # la capa ya fue destruida por QGIS (proyecto cerrado o capa quitada)
            return
        for sig, slot in pairs:
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _on_deleted(self):
        self._disconnect()
        self.layer, self.cfg = None, None
        self.attachedChanged.emit()
        self.changed.emit()

    def shutdown(self):
        self._shut = True
        try:
            self.iface.currentLayerChanged.disconnect(self.attach)
        except (TypeError, RuntimeError):
            pass
        try:
            self.iface.mapCanvas().selectionChanged.disconnect(self._on_any_selection)
        except (TypeError, RuntimeError):
            pass
        try:
            self.iface.projectRead.disconnect(self._apply_all_later)
        except (TypeError, RuntimeError):
            pass
        for sig in self._background_signals():
            try:
                sig.disconnect(self._bg_timer.start)
            except (TypeError, RuntimeError):
                pass
        self._bg_timer.stop()

    def _background_signals(self):
        out = []
        canvas = self.iface.mapCanvas()
        for obj, name in ((canvas, 'canvasColorChanged'), (None, 'backgroundColorChanged')):
            if obj is None:
                from qgis.core import QgsProject
                obj = QgsProject.instance()
            sig = getattr(obj, name, None)
            if sig is not None:
                out.append(sig)
        return out

    def _apply_all_later(self, *args):
        QTimer.singleShot(0, self._apply_all)

    def _apply_all(self):
        if getattr(self, '_shut', False):
            return
        self._last_dark = self._canvas_is_dark()
        for lyr in self._managed_layers():
            try:
                self._apply_to(lyr, self.cfg if lyr is self.layer else self._load(lyr))
            except Exception:  # noqa: BLE001
                pass

    def _background_changed(self):
        if getattr(self, '_shut', False):
            return
        """Redibuja las capas gestionadas si el fondo pasó de claro a oscuro o al revés."""
        dark = self._canvas_is_dark()
        if dark == self._last_dark:
            return
        self._last_dark = dark
        for lyr in self._managed_layers():
            self._apply_to(lyr, self.cfg if lyr is self.layer else self._load(lyr))
        self.changed.emit()

    @property
    def black_as_7(self):
        return self.setting('black_as_7', True, bool)

    def is_bw(self, color):
        """Color 7 de AutoCAD (blanco/negro según el fondo); opcionalmente también el negro RGB."""
        if color.get('aci') == 7:
            return True
        if self.black_as_7 and not color.get('aci'):
            rgb = str(color.get('rgb') or '').strip().lower()
            return rgb in ('#000000', '#000', '0,0,0', 'black')
        return False
        self._disconnect()

    @property
    def active(self):
        if self.layer is None or self.cfg is None:
            return False
        try:
            from qgis.PyQt import sip
        except ImportError:
            import sip
        try:
            if sip.isdeleted(self.layer):
                self.layer, self.cfg = None, None
                return False
        except Exception:  # noqa: BLE001
            pass
        return True

    @property
    def initialized(self):
        return self.active and self.field_index() != -1 and bool(self.layer.customProperty(PROP_KEY))

    # ------------------------------------------------------------ persistencia
    def template(self):
        raw = self.setting('template', '', str)
        if raw:
            try:
                return normalize_config(json.loads(raw))
            except (ValueError, TypeError):
                pass
        return normalize_config({'layers': [new_layer('0')]})

    def save_template(self):
        if self.active:
            data = {'layers': self.cfg['layers'], 'current': '0'}
            self.set_setting('template', json.dumps(data))
            self.msg('Configuración guardada como plantilla para capas nuevas.')

    def _load(self, layer):
        raw = layer.customProperty(PROP_KEY)
        if raw:
            try:
                return normalize_config(json.loads(raw))
            except (ValueError, TypeError):
                pass
        cfg = self.template()
        cfg['states'] = {}
        return cfg

    def _save(self):
        if self.active:
            self.layer.setCustomProperty(PROP_KEY, json.dumps(self.cfg, ensure_ascii=False))

    def field_index(self):
        return self.layer.fields().indexOf(FIELD) if self.layer else -1

    def max_name_length(self):
        idx = self.field_index()
        if idx == -1:
            return 50
        ln = self.layer.fields().field(idx).length()
        return ln if ln and ln > 0 else 255

    def ensure_initialized(self):
        """Crea el campo LAYER_CODE si falta y aplica la simbología."""
        if not self.active:
            self.warn('Selecciona una capa vectorial (línea, polígono o punto) en el panel de capas.')
            return False
        if self.field_index() == -1:
            ok = False
            prov = self.layer.dataProvider()
            try:
                ok = prov.addAttributes([string_field(FIELD, 50)])
                self.layer.updateFields()
            except Exception:
                ok = False
            if not ok and self.layer.isEditable():
                ok = self.layer.addAttribute(string_field(FIELD, 50))
            if not ok or self.field_index() == -1:
                self.warn('No se pudo crear el campo %s en "%s".' % (FIELD, self.layer.name()))
                return False
            self.msg('Campo %s creado en "%s".' % (FIELD, self.layer.name()))
        if not self.layer.customProperty(PROP_KEY):
            self._save()
            self.apply()
        return True

    # ------------------------------------------------------------ consultas
    def layers(self):
        return self.cfg['layers'] if self.active else []

    def names(self):
        return [l['name'] for l in self.layers()]

    def find(self, name, exact=False):
        for l in self.layers():
            if l['name'] == name or (not exact and l['name'].lower() == str(name).lower()):
                return l
        return None

    def index_of(self, name):
        names = self.names()
        return names.index(name) if name in names else -1

    @property
    def current(self):
        return self.cfg['current'] if self.active else None

    def used_names(self):
        idx = self.field_index()
        if idx == -1:
            return {'0'} if self.active and self.layer.featureCount() else set()
        try:
            values = self.layer.uniqueValues(idx)
        except Exception:
            values = []
        return {norm_name(v) for v in values}

    def filter_names(self, text):
        """Filtro de búsqueda con comodines estilo AutoCAD (* ?)."""
        text = (text or '').strip()
        if not text:
            return self.names()
        pats = [p.strip().lower() for p in text.split(',') if p.strip()]
        out = []
        for n in self.names():
            ln = n.lower()
            for p in pats:
                if ('*' in p or '?' in p) and fnmatch.fnmatchcase(ln, p):
                    out.append(n)
                    break
                if '*' not in p and '?' not in p and p in ln:
                    out.append(n)
                    break
        return out

    def _iter_selected(self, limit=None):
        idx = self.field_index()
        if idx == -1 or not self.layer.selectedFeatureCount():
            return
        req = QgsFeatureRequest().setFilterFids(list(self.layer.selectedFeatureIds()))
        req.setFlags(_no_geometry_flag())
        req.setSubsetOfAttributes([idx])
        if limit:
            req.setLimit(limit)
        for f in self.layer.getFeatures(req):
            yield f.id(), norm_name(f.attribute(idx))

    def selection_sources(self):
        """[(capa QGIS, [fids])] con objetos seleccionados: la capa activa y las demás capas
        gestionadas (con LAYER_CODE), p. ej. la de inserciones de bloque de Dibujo CAD."""
        out, seen = [], set()
        for lyr in [self.layer] + self._managed_layers():
            if lyr is None or lyr.id() in seen:
                continue
            seen.add(lyr.id())
            try:
                if not isinstance(lyr, QgsVectorLayer) or not lyr.selectedFeatureCount():
                    continue
            except RuntimeError:
                continue
            if lyr is not self.layer and lyr.fields().indexOf(FIELD) == -1:
                continue
            out.append((lyr, list(lyr.selectedFeatureIds())))
        return out

    def describe_selection(self):
        parts = []
        for lyr in [self.layer] + self._managed_layers():
            if lyr is None:
                continue
            try:
                parts.append('%s[sel=%d, LAYER_CODE=%s, edit=%s, gestionada=%s]' % (
                    lyr.name(), lyr.selectedFeatureCount(), lyr.fields().indexOf(FIELD),
                    lyr.isEditable(), bool(lyr.customProperty(PROP_KEY))))
            except RuntimeError:
                pass
        return 'activa=%s | %s' % (self.layer.name() if self.layer else None, '; '.join(parts))

    def has_selection(self):
        return bool(self.selection_sources())

    def selected_layer_names(self, limit=20000):
        """Conjunto de capas CAD de los objetos seleccionados (en todas las capas QGIS
        gestionadas), o None si no hay selección."""
        if not self.active:
            return None
        sources = self.selection_sources()
        if not sources:
            return None
        names = set()
        for lyr, fids in sources:
            idx = lyr.fields().indexOf(FIELD)
            if idx == -1:
                names.add('0')
                continue
            req = QgsFeatureRequest().setFilterFids(fids)
            req.setFlags(_no_geometry_flag())
            req.setSubsetOfAttributes([idx])
            if limit:
                req.setLimit(limit)
            for f in lyr.getFeatures(req):
                names.add(norm_name(f.attribute(idx)))
        return names

    def feature_layer(self, feature):
        idx = self.field_index()
        if idx == -1:
            return '0'
        try:
            return norm_name(feature.attribute(idx))
        except Exception:
            return '0'

    # ------------------------------------------------------------ cambios
    def _snapshot(self):
        return copy.deepcopy({'layers': self.cfg['layers'], 'current': self.cfg['current']})

    def _commit(self, snap=None, history=True):
        if history and snap is not None:
            hist = self._history.setdefault(self.layer.id(), [])
            hist.append(snap)
            del hist[:-50]
        self._save()
        self.apply()
        self.changed.emit()

    def modify(self, fn, history=True):
        """Ejecuta fn() sobre la configuración; si devuelve False no se guarda."""
        if not self.ensure_initialized():
            return False
        self.sync_from_renderer()
        snap = self._snapshot()
        if fn() is False:
            return False
        if snap == self._snapshot():
            return True
        self._commit(snap, history)
        return True

    def can_previous(self):
        return self.active and bool(self._history.get(self.layer.id()))

    def layer_previous(self):
        """CAPAP / LAYERP: deshace el último cambio de propiedades de capa."""
        if not self.can_previous():
            self.msg('No hay estados de capa previos.')
            return
        snap = self._history[self.layer.id()].pop()
        self.cfg['layers'] = snap['layers']
        self.cfg['current'] = snap['current']
        self._commit(history=False)
        self.msg('Estado de capa previo restablecido.')

    # -- propiedades
    def set_current(self, name):
        lay = self.find(name)
        if not lay:
            return False

        def fn():
            if lay['frozen']:
                self.warn('No se puede establecer como actual una capa inutilizada ("%s").' % lay['name'])
                return False
            self.cfg['current'] = lay['name']
            if not lay['on']:
                self.warn('La capa actual "%s" está desactivada.' % lay['name'])
        return self.modify(fn)

    def set_props(self, names, **props):
        names = [n for n in names if self.find(n, True)]

        def fn():
            for n in names:
                lay = self.find(n, True)
                for k, v in props.items():
                    if k == 'frozen' and v and n == self.cfg['current']:
                        self.warn('No se puede inutilizar la capa actual ("%s").' % n)
                        continue
                    if k == 'on' and not v and n == self.cfg['current']:
                        self.warn('La capa actual "%s" está desactivada.' % n)
                    lay[k] = copy.deepcopy(v)
        return self.modify(fn)

    def toggle(self, names, key, reference=None):
        ref = self.find(reference or names[0], True)
        if not ref:
            return False
        return self.set_props(names, **{key: not ref[key]})

    # -- crear / suprimir / renombrar
    def unique_name(self, base='Capa'):
        existing = {n.lower() for n in self.names()}
        i = 1
        while ('%s%d' % (base, i)).lower() in existing:
            i += 1
        return '%s%d' % (base, i)

    def validate_name(self, name, old=None):
        name = (name or '').strip()
        if not name:
            return 'El nombre de capa no puede estar vacío.'
        bad = [c for c in name if c in INVALID_CHARS]
        if bad:
            return 'El nombre contiene caracteres no válidos: %s' % ' '.join(sorted(set(bad)))
        if len(name) > self.max_name_length():
            return 'El nombre supera los %d caracteres del campo %s.' % (self.max_name_length(), FIELD)
        other = self.find(name)
        if other and other['name'] != old:
            return 'Ya existe la capa "%s".' % other['name']
        return None

    def add_layer(self, based_on=None, name=None):
        base = self.find(based_on, True) if based_on else None
        name = name or self.unique_name()
        holder = {}

        def fn():
            lay = copy.deepcopy(base) if base else new_layer(name)
            lay.update(name=name, description='' if base is None else base.get('description', ''))
            lay['frozen'] = False
            pos = self.index_of(base['name']) + 1 if base else 0
            self.cfg['layers'].insert(pos, lay)
            holder['name'] = name
        self.modify(fn)
        return holder.get('name')

    def delete_layers(self, names):
        used = self.used_names()
        errors, todel = [], []
        for n in names:
            if n == '0':
                errors.append('No se puede suprimir la capa 0.')
            elif n == self.current:
                errors.append('No se puede suprimir la capa actual ("%s").' % n)
            elif n in used:
                errors.append('La capa "%s" contiene objetos y no se puede suprimir.' % n)
            else:
                todel.append(n)

        def fn():
            if not todel:
                return False
            self.cfg['layers'] = [l for l in self.cfg['layers'] if l['name'] not in todel]
            for st in self.cfg['states'].values():
                for n in todel:
                    st.get('layers', {}).pop(n, None)
        if todel:
            self.modify(fn)
        return todel, errors

    def _set_feature_values(self, fids, value, text='Cambiar capa CAD', layer=None):
        layer = layer or self.layer
        idx = layer.fields().indexOf(FIELD) if layer is not None else -1
        dlog('set_values capa=%s idx=%s fids=%s valor=%r' % (layer.name() if layer else None, idx,
                                                             list(fids)[:10], value))
        if idx == -1 or not fids:
            return 0
        fld = layer.fields().field(idx)
        dlog('  campo %s tipo=%s longitud=%s editable_capa=%s' % (fld.name(), fld.typeName(), fld.length(),
                                                                  layer.isEditable()))
        if fld.typeName().lower() not in ('string', 'text', 'varchar', 'char', 'character', 'str', 'qstring') \
                and 'char' not in fld.typeName().lower() and 'str' not in fld.typeName().lower():
            self.warn('El campo %s de "%s" es de tipo %s: debe ser texto para guardar el nombre de la capa.'
                      % (FIELD, layer.name(), fld.typeName()))
        if fld.length() and 0 < fld.length() < len(str(value)):
            self.warn('El campo %s de "%s" admite %d caracteres: "%s" se recortará.'
                      % (FIELD, layer.name(), fld.length(), value))
        was_editing = layer.isEditable()
        if not was_editing and not layer.startEditing():
            self.warn('La capa "%s" no se puede editar.' % layer.name())
            return 0
        layer.beginEditCommand(text)
        n = 0
        for fid in fids:
            ok = layer.changeAttributeValue(fid, idx, value)
            if ok:
                n += 1
            else:
                dlog('  changeAttributeValue FALLÓ fid=%s' % fid)
        if n:
            layer.endEditCommand()
        else:
            layer.destroyEditCommand()
        if not was_editing:
            if not layer.commitChanges():
                self.warn('Error al guardar: %s' % '; '.join(layer.commitErrors()))
                layer.rollBack()
                return 0
        layer.triggerRepaint()     # el cambio de capa se ve al instante (también en modo edición)
        try:
            chk = layer.getFeature(list(fids)[0]).attribute(idx)
        except Exception as e:  # noqa: BLE001
            chk = 'error: %s' % e
        dlog('  cambiados=%d de %d; valor leído después=%r' % (n, len(fids), chk))
        return n

    def _fids_of(self, names):
        idx = self.field_index()
        if idx == -1:
            return []
        quoted = ','.join(QgsExpression.quotedString(n) for n in names)
        req = QgsFeatureRequest().setFilterExpression('%s IN (%s)' % (NAME_EXPR, quoted))
        req.setFlags(_no_geometry_flag())
        req.setSubsetOfAttributes([idx])
        return [f.id() for f in self.layer.getFeatures(req)]

    def rename(self, old, new):
        new = (new or '').strip()
        if old == new:
            return True
        if old == '0':
            self.warn('No se puede cambiar el nombre de la capa 0.')
            return False
        err = self.validate_name(new, old)
        if err:
            self.warn(err)
            return False
        lay = self.find(old, True)

        def fn():
            fids = self._fids_of([old])
            if fids and self._set_feature_values(fids, new, 'Renombrar capa CAD') != len(fids):
                return False
            lay['name'] = new
            if self.cfg['current'] == old:
                self.cfg['current'] = new
            for st in self.cfg['states'].values():
                ls = st.get('layers', {})
                if old in ls:
                    ls[new] = ls.pop(old)
                if st.get('current') == old:
                    st['current'] = new
        return self.modify(fn)

    def merge(self, sources, target):
        """LAYMRG: mueve los objetos de 'sources' a 'target' y suprime 'sources'."""
        sources = [s for s in sources if s != target and s != '0']
        if not sources:
            return False

        def fn():
            fids = self._fids_of(sources)
            if fids and self._set_feature_values(fids, target, 'Fusionar capas CAD') != len(fids):
                return False
            if self.cfg['current'] in sources:
                self.cfg['current'] = target
            self.cfg['layers'] = [l for l in self.cfg['layers'] if l['name'] not in sources]
        ok = self.modify(fn)
        if ok:
            self.msg('%d capa(s) fusionada(s) en "%s".' % (len(sources), target))
        return ok

    # -- orden de dibujo
    def move(self, names, delta):
        def fn():
            lst = self.cfg['layers']
            idxs = sorted(self.index_of(n) for n in names)
            if delta < 0:
                for i in idxs:
                    if i > 0 and lst[i - 1]['name'] not in names:
                        lst[i - 1], lst[i] = lst[i], lst[i - 1]
            else:
                for i in reversed(idxs):
                    if i < len(lst) - 1 and lst[i + 1]['name'] not in names:
                        lst[i + 1], lst[i] = lst[i], lst[i + 1]
        return self.modify(fn)

    def move_to(self, names, top=True):
        def fn():
            sel = [l for l in self.cfg['layers'] if l['name'] in names]
            rest = [l for l in self.cfg['layers'] if l['name'] not in names]
            self.cfg['layers'] = sel + rest if top else rest + sel
        return self.modify(fn)

    # -- objetos
    def assign_selection(self, name):
        """Cambia a la capa CAD 'name' los objetos seleccionados (como la lista de capas de AutoCAD).

        Actúa sobre la selección de la capa activa y de las demás capas gestionadas.
        Si la capa de destino no existe en alguna de ellas, se crea con las mismas propiedades.
        """
        lay = self.find(name)
        if not lay:
            self.warn('La capa "%s" no existe.' % name)
            return 0
        sources = self.selection_sources()
        dlog('assign_selection destino=%r | %s' % (name, self.describe_selection()))
        if not sources:
            self.warn('No hay objetos seleccionados.')
            return 0
        if any(lyr is self.layer for lyr, _ in sources) and not self.ensure_initialized():
            return 0
        target = lay['name']
        total, skipped = 0, 0
        for lyr, fids in sources:
            if lyr is not self.layer:
                cfg = self._load(lyr)
                if not any(l['name'] == target for l in cfg['layers']):
                    cfg['layers'].append(copy.deepcopy(lay))
                    lyr.setCustomProperty(PROP_KEY, json.dumps(cfg, ensure_ascii=False))
                    self._apply_to(lyr, cfg)
            n = self._set_feature_values(fids, target, layer=lyr)
            total += n
            skipped += len(fids) - n
        if total:
            self.msg('%d objeto(s) cambiado(s) a la capa "%s".' % (total, target))
        if skipped:
            self.warn('%d objeto(s) no se pudieron cambiar de capa.' % skipped)
        self.selectionChanged.emit()
        self.changed.emit()
        return total

    def select_objects(self, names):
        if self.field_index() == -1:
            return
        quoted = ','.join(QgsExpression.quotedString(n) for n in names)
        self.layer.selectByExpression('%s IN (%s)' % (NAME_EXPR, quoted))

    # -- herramientas de la barra Capas (LAYOFF, LAYISO...)
    def layoff(self, names):
        return self.set_props(names, on=False)

    def layfrz(self, names):
        return self.set_props(names, frozen=True)

    def laylck(self, names):
        return self.set_props(names, locked=True)

    def layulk(self, names):
        return self.set_props(names, locked=False)

    def layon_all(self):
        return self.set_props(self.names(), on=True)

    def laythw_all(self):
        return self.set_props(self.names(), frozen=False)

    def isolate(self, names):
        names = [n for n in names if self.find(n, True)]
        if not names:
            return False
        self._iso_backup[self.layer.id()] = {l['name']: l['on'] for l in self.layers()}

        def fn():
            for l in self.cfg['layers']:
                l['on'] = l['name'] in names
                if l['name'] in names:
                    l['frozen'] = False
            if self.cfg['current'] not in names:
                self.cfg['current'] = names[0]
        ok = self.modify(fn)
        if ok:
            self.msg('Capas aisladas: %s' % ', '.join(names))
        return ok

    def unisolate(self):
        backup = self._iso_backup.pop(self.layer.id(), None) if self.active else None
        if not backup:
            self.msg('No hay capas aisladas con AISLARCAPA.')
            return False

        def fn():
            for l in self.cfg['layers']:
                if l['name'] in backup:
                    l['on'] = backup[l['name']]
        return self.modify(fn)

    # -- estados de capa
    def save_state(self, state_name, description=''):
        def fn():
            self.cfg['states'][state_name] = {
                'description': description,
                'current': self.cfg['current'],
                'layers': {l['name']: {k: copy.deepcopy(l[k]) for k in STATE_PROPS}
                           for l in self.cfg['layers']},
            }
        return self.modify(fn, history=False)

    def restore_state(self, state_name, props=STATE_PROPS, off_missing=False):
        st = self.cfg['states'].get(state_name)
        if not st:
            return False

        def fn():
            saved = st.get('layers', {})
            for l in self.cfg['layers']:
                if l['name'] in saved:
                    for k in props:
                        if k in saved[l['name']]:
                            l[k] = copy.deepcopy(saved[l['name']][k])
                elif off_missing:
                    l['on'] = False
            cur = st.get('current')
            if cur and self.find(cur, True) and not self.find(cur, True)['frozen']:
                self.cfg['current'] = cur
            elif self.find(self.cfg['current'], True)['frozen']:
                self.find(self.cfg['current'], True)['frozen'] = False
        return self.modify(fn)

    def delete_state(self, state_name):
        def fn():
            self.cfg['states'].pop(state_name, None)
        return self.modify(fn, history=False)

    # -- importar / exportar
    def export_config(self, path):
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(self.cfg, fh, ensure_ascii=False, indent=2)

    def import_config(self, path, replace_props=True):
        with open(path, 'r', encoding='utf-8') as fh:
            data = normalize_config(json.load(fh), ensure_zero=False)
        counts = {'new': 0, 'upd': 0}

        def fn():
            for lay in data['layers']:
                mine = self.find(lay['name'], True)
                if mine is None:
                    err = self.validate_name(lay['name'])
                    if err:
                        continue
                    self.cfg['layers'].append(lay)
                    counts['new'] += 1
                elif replace_props:
                    for k, v in lay.items():
                        if k != 'name':
                            mine[k] = v
                    counts['upd'] += 1
            # reordenar según el archivo importado (las capas propias no listadas quedan al final)
            order = {l['name']: i for i, l in enumerate(data['layers'])}
            self.cfg['layers'].sort(key=lambda l: order.get(l['name'], len(order)))
            self.cfg['states'].update(data.get('states', {}))
            cur = self.find(self.cfg['current'], True)
            if cur and cur['frozen']:
                cur['frozen'] = False
        self.modify(fn)
        return counts

    # ------------------------------------------------------------ sincronía
    def _reconcile(self):
        """Agrega como capas los valores de LAYER_CODE que no estén definidos."""
        if not self.active:
            return False
        known = set(self.names())
        missing = sorted(n for n in self.used_names() if n not in known)
        if not missing:
            return False
        for n in missing:
            self.cfg['layers'].append(new_layer(n))
        if self.layer.customProperty(PROP_KEY):
            self._save()
            self.apply()
        return True

    def refresh(self):
        if self.active:
            self.sync_from_renderer()
            self._reconcile()
            self.changed.emit()

    def sync_from_renderer(self):
        """Respeta los cambios de visibilidad hechos desde la leyenda de QGIS."""
        if not self.active:
            return
        r = self.layer.renderer()
        if not isinstance(r, QgsCategorizedSymbolRenderer) or r.classAttribute() != NAME_EXPR:
            return
        for cat in r.categories():
            lay = self.find(str(cat.value()), True)
            if not lay or lay['frozen']:
                continue
            lay['on'] = bool(cat.renderState())

    def _on_style_changed(self):
        if self._applying or not self.active:
            return
        before = self._snapshot()
        self.sync_from_renderer()
        if before != self._snapshot():
            self._save()
            self.changed.emit()

    def _on_attr_changed(self, fid, idx, value):
        if self._applying or idx != self.field_index() or self._reconcile_pending:
            return
        if norm_name(value) not in self.names():
            self._reconcile_pending = True
            QTimer.singleShot(0, self._deferred_reconcile)

    def _deferred_reconcile(self):
        self._reconcile_pending = False
        if self._reconcile():
            self.changed.emit()

    def _blocked_names(self):
        return {l['name'] for l in self.layers() if l['locked'] or l['frozen']}

    def _on_selection(self, *args):
        if self._sel_guard or not self.active:
            return
        blocked = self._blocked_names()
        if blocked and self.field_index() != -1 and self.layer.selectedFeatureCount():
            bad = [fid for fid, n in self._iter_selected() if n in blocked]
            if bad:
                self._sel_guard = True
                try:
                    self.layer.deselect(bad)
                finally:
                    self._sel_guard = False
                self.msg('%d objeto(s) en capas bloqueadas o inutilizadas excluido(s) de la selección.' % len(bad), 'Warning', 3)
        self.selectionChanged.emit()

    def _on_any_selection(self, layer=None):
        if layer is not None and layer is self.layer:
            return              # la capa activa ya la atiende _on_selection
        self.selectionChanged.emit()

    def _on_geometry_changed(self, fid, geom):
        if self._undo_pending or not self.active:
            return
        locked = {l['name'] for l in self.layers() if l['locked']}
        if not locked or self.field_index() == -1:
            return
        f = self.layer.getFeature(fid)
        if self.feature_layer(f) in locked:
            self._undo_pending = True
            QTimer.singleShot(0, self._undo_locked)

    def _undo_locked(self):
        self._undo_pending = False
        if not self.active:
            return
        stack = self.layer.undoStack()
        if stack and stack.canUndo():
            stack.undo()
            self.layer.triggerRepaint()
        self.warn('El objeto está en una capa bloqueada: la modificación se revirtió.')

    # ------------------------------------------------------------ simbología
    def _canvas_is_dark(self):
        try:
            return self.iface.mapCanvas().canvasColor().lightness() < 128
        except Exception:
            return False

    def build_symbol(self, lay, kind):
        dark = self._canvas_is_dark()
        bw = self.is_bw(lay['color'])
        aci = 7 if bw else lay['color'].get('aci')
        if bw:
            base = QColor('#ffffff' if dark else '#000000')
        else:
            base = QColor(color_hex(lay['color']))
        width = lineweight_mm(lay['lineweight'])
        mm = render_mm()
        pattern = [v * self.ltscale for v in LINETYPES.get(lay['linetype'], LINETYPES['Continuous'])['pattern']]

        block_expr = None
        lyr = getattr(self, '_apply_layer', None)
        if kind == 'point' and lyr is not None:
            try:
                block_expr = lyr.customProperty('dibujo_cad/block_expr') or None
            except RuntimeError:
                block_expr = None
        if kind == 'point' and lyr is not None:
            try:
                is_text = lyr.customProperty('dibujo_cad/text_layer') == '1'
            except RuntimeError:
                is_text = False
            if is_text:
                sl = QgsSimpleMarkerSymbolLayer()
                sl.setColor(QColor(0, 0, 0, 0))
                sl.setStrokeColor(QColor(0, 0, 0, 0))
                sl.setSize(0.01)
                return QgsMarkerSymbol([sl])
        if block_expr:
            kind = 'block'               # inserciones de bloque (Dibujo y Edición CAD)
        if kind == 'point':
            sl = QgsSimpleMarkerSymbolLayer()
            sl.setColor(base)
            sl.setStrokeColor(base)
            sl.setSize(1.6)
            sl.setSizeUnit(mm)
            sl.setStrokeWidth(width)
            sl.setStrokeWidthUnit(mm)
        else:
            sl = QgsSimpleLineSymbolLayer(base, width)
            sl.setWidthUnit(mm)
            sl.setPenJoinStyle(qt('PenJoinStyle', 'RoundJoin'))
            if pattern:
                sl.setUseCustomDashPattern(True)
                sl.setCustomDashVector(pattern)
                sl.setCustomDashPatternUnit(mm)
                sl.setPenCapStyle(qt('PenCapStyle', 'RoundCap' if has_dots(pattern) else 'FlatCap'))
            else:
                sl.setPenCapStyle(qt('PenCapStyle', 'RoundCap'))

        # Color en pantalla y en papel, según la tabla de estilos de trazado del diseño
        # (@cad_ctb = 'monochrome' | 'grayscale' | otro = según pantalla). Color 7 se traza negro.
        paper = QColor('#000000') if aci == 7 else QColor(base)
        gray = int(round(0.299 * paper.red() + 0.587 * paper.green() + 0.114 * paper.blue()))
        rgba = lambda c: '%d,%d,%d,255' % (c.red(), c.green(), c.blue())  # noqa: E731
        color_str = ("CASE WHEN @layout_name IS NULL THEN '%s' WHEN @cad_ctb = 'monochrome' THEN '0,0,0,255' "
                     "WHEN @cad_ctb = 'grayscale' THEN '%d,%d,%d,255' ELSE '%s' END"
                     % (rgba(base), gray, gray, gray, rgba(paper)))
        # Propiedades propias del objeto (panel Propiedades de Dibujo CAD): vacías = PorCapa
        try:
            flds = lyr.fields() if lyr is not None else None
        except RuntimeError:
            flds = None
        has = lambda n: flds is not None and flds.indexOf(n) != -1  # noqa: E731
        if has('CAD_COLOR'):
            color_str = override_color_expression('CAD_COLOR', color_str, dark)
        cexpr = QgsProperty.fromExpression(color_str)
        sl.setDataDefinedProperty(symbol_property('StrokeColor'), cexpr)
        if kind == 'point':
            sl.setDataDefinedProperty(symbol_property('FillColor'), cexpr)
        # Grosor: LWDISPLAY en pantalla; en papel según @cad_lw (0 = no trazar grosores)
        lw = repr(width)
        if has('CAD_LW'):
            lw = ('(CASE WHEN "CAD_LW" IS NULL THEN %s WHEN "CAD_LW" < 0 THEN %s ELSE "CAD_LW" END)'
                  % (repr(width), repr(lineweight_mm(-1))))
        screen_w = lw if self.lwdisplay else '0'
        sl.setDataDefinedProperty(
            symbol_property('StrokeWidth'),
            QgsProperty.fromExpression('CASE WHEN @layout_name IS NULL THEN %s WHEN @cad_lw = 0 THEN 0 '
                                       'ELSE %s END' % (screen_w, lw)))
        # Tipo de línea propio
        if has('CAD_LTYPE') and kind != 'point':
            fmt = lambda pat: ';'.join('%g' % v for v in pat) if pat else '10;0'  # noqa: E731
            whens = ' '.join("WHEN \"CAD_LTYPE\" = %s THEN '%s'" % (
                QgsExpression.quotedString(name), fmt([v * self.ltscale for v in lt['pattern']]))
                for name, lt in LINETYPES.items())
            sl.setUseCustomDashPattern(True)
            if not pattern:
                sl.setCustomDashVector([10.0, 0.0])
                sl.setCustomDashPatternUnit(mm)
            sl.setDataDefinedProperty(symbol_property('CustomDash'), QgsProperty.fromExpression(
                "CASE WHEN coalesce(\"CAD_LTYPE\", '') = '' THEN '%s' %s ELSE '10;0' END" % (fmt(pattern), whens)))
        # Trazar desactivado: se ve en pantalla pero no en composiciones
        if not lay.get('plot', True):
            sl.setDataDefinedProperty(symbol_property('LayerEnabled'),
                                      QgsProperty.fromExpression('@layout_name IS NULL'))

        if kind == 'block':
            from qgis.core import QgsGeometryGeneratorSymbolLayer
            gen = QgsGeometryGeneratorSymbolLayer.create({'geometryModifier': block_expr})
            try:
                gen.setSymbolType(Qgis.SymbolType.Line)
            except AttributeError:
                from qgis.core import QgsSymbol
                gen.setSymbolType(QgsSymbol.Line)
            gen.setSubSymbol(QgsLineSymbol([sl]))
            sym = QgsMarkerSymbol()
            sym.changeSymbolLayer(0, gen)
        elif kind == 'point':
            sym = QgsMarkerSymbol([sl])
        elif kind == 'polygon':
            sym = QgsFillSymbol([sl])
        else:
            sym = QgsLineSymbol([sl])
        opacity = (100 - int(lay.get('transparency', 0))) / 100.0
        if lay.get('locked'):
            opacity *= max(0.0, 1.0 - self.lockfade / 100.0)
        sym.setOpacity(max(0.0, min(1.0, opacity)))
        return sym

    def apply(self):
        if self.active:
            self._apply_to(self.layer, self.cfg)

    def _apply_to(self, layer, cfg):
        idx = layer.fields().indexOf(FIELD)
        if idx == -1:
            return
        kind = geometry_kind(layer)
        self._applying = True
        self._apply_layer = layer
        try:
            cats = []
            for lay in cfg['layers']:
                visible = lay['on'] and not lay['frozen']
                cats.append(QgsRendererCategory(lay['name'], self.build_symbol(lay, kind),
                                                lay['name'], visible))
            renderer = QgsCategorizedSymbolRenderer(NAME_EXPR, cats)

            # Orden de dibujo: las capas superiores de la lista se dibujan encima
            n = len(cfg['layers'])
            whens = ' '.join('WHEN %s THEN %d' % (QgsExpression.quotedString(l['name']), i)
                             for i, l in enumerate(reversed(cfg['layers'])))
            expr = 'CASE %s %s ELSE -1 END' % (NAME_EXPR, whens) if n else '0'
            try:
                clause = QgsFeatureRequest.OrderByClause(expr, True)
            except TypeError:
                clause = QgsFeatureRequest.OrderByClause(QgsExpression(expr), True)
            renderer.setOrderBy(QgsFeatureRequest.OrderBy([clause]))
            renderer.setOrderByEnabled(True)
            layer.setRenderer(renderer)

            # Formulario: lista de capas + capa actual como valor por defecto
            vm = [{l['name']: l['name']} for l in cfg['layers']]
            layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup('ValueMap', {'map': vm}))
            layer.setDefaultValueDefinition(idx, QgsDefaultValue(QgsExpression.quotedString(cfg['current'])))
            self._apply_text_colors(layer, cfg)
            layer.triggerRepaint()
            try:
                self.iface.layerTreeView().refreshLayerSymbology(layer.id())
            except Exception:
                pass
        finally:
            self._applying = False
            self._apply_layer = None

    def _apply_text_colors(self, layer, cfg):
        """Textos de Dibujo CAD: el color de la etiqueta sigue el color de su capa CAD.
        Color 7 (y negro, si se trata como 7): blanco sobre fondo oscuro, negro sobre claro;
        en papel se trazan negros y respetan @cad_ctb (monocromo / escala de grises)."""
        try:
            if layer.customProperty('dibujo_cad/text_layer') != '1' or not layer.labelsEnabled():
                return
            from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
            lab = layer.labeling()
            if not isinstance(lab, QgsVectorLayerSimpleLabeling):
                return
            st = QgsPalLayerSettings(lab.settings())
        except Exception:  # noqa: BLE001
            return
        dark = self._canvas_is_dark()
        rgba = lambda c: '%d,%d,%d,255' % (c.red(), c.green(), c.blue())  # noqa: E731
        scr, pap, gry = [], [], []
        for lay in cfg['layers']:
            q = QgsExpression.quotedString(lay['name'])
            if self.is_bw(lay['color']):
                screen = QColor('#ffffff' if dark else '#000000')
                paper = QColor('#000000')
            else:
                screen = paper = QColor(color_hex(lay['color']))
            g = int(round(0.299 * paper.red() + 0.587 * paper.green() + 0.114 * paper.blue()))
            scr.append("WHEN %s = %s THEN '%s'" % (NAME_EXPR, q, rgba(screen)))
            pap.append("WHEN %s = %s THEN '%s'" % (NAME_EXPR, q, rgba(paper)))
            gry.append("WHEN %s = %s THEN '%d,%d,%d,255'" % (NAME_EXPR, q, g, g, g))
        default_screen = '255,255,255,255' if dark else '0,0,0,255'
        case = lambda parts, dflt: 'CASE %s ELSE \'%s\' END' % (' '.join(parts), dflt) if parts else "'%s'" % dflt  # noqa: E731
        expr = ("CASE WHEN @layout_name IS NULL THEN %s "
                "WHEN @cad_ctb = 'monochrome' THEN '0,0,0,255' "
                "WHEN @cad_ctb = 'grayscale' THEN %s ELSE %s END"
                % (case(scr, default_screen), case(gry, '0,0,0,255'), case(pap, '0,0,0,255')))
        if layer.fields().indexOf('COLOR') != -1:
            # color propio del texto (barra Texto CAD de Dibujo CAD); vacío = PorCapa
            bw = '255,255,255,255' if dark else '0,0,0,255'
            expr = ("CASE WHEN coalesce(\"COLOR\", '') = '' THEN %s "
                    "WHEN @layout_name IS NOT NULL AND @cad_ctb = 'monochrome' THEN '0,0,0,255' "
                    "WHEN lower(\"COLOR\") = '#000000' THEN "
                    "CASE WHEN @layout_name IS NULL THEN '%s' ELSE '0,0,0,255' END "
                    "WHEN @layout_name IS NOT NULL AND @cad_ctb = 'grayscale' "
                    "THEN color_grayscale_average(\"COLOR\") ELSE \"COLOR\" END" % (expr, bw))
        try:
            prop = getattr(QgsPalLayerSettings, 'Property', None)
            key = getattr(prop, 'Color') if prop is not None and hasattr(prop, 'Color') else QgsPalLayerSettings.Color
            dd = st.dataDefinedProperties()
            dd.setProperty(key, QgsProperty.fromExpression(expr))
            st.setDataDefinedProperties(dd)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(st))
        except Exception:  # noqa: BLE001
            pass

    def preview_color(self, lay):
        if self.is_bw(lay['color']):
            return QColor('#ffffff' if self._canvas_is_dark() else '#000000')
        return QColor(color_hex(lay['color']))


__all__ = ['CadLayerController', 'FIELD', 'aci_to_hex']
