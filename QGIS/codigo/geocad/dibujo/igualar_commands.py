# -*- coding: utf-8 -*-
"""IGUALARPROP (MATCHPROP / MA) en Dibujo de QGIS (3.61.0); qué se copia, en igualar.py.

El origen puede estar en cualquier capa visible; los destinos son de la capa
activa, como en los demás comandos de edición. Cada paso de la designación se
aplica al momento (sin el resaltado de selección, que taparía el color nuevo) y
queda en Deshacer de QGIS por separado.
"""

import json

from qgis.core import QgsVectorLayer
from qgis.gui import QgsHighlight
from qgis.PyQt.QtGui import QColor

from . import igualar
from .commands import _key
from .editkit import EditCommand, GeomIO, pick_feature
from .properties_panel import CFG_KEY, TEXT_FLAG, add_cad_layer_def, ensure_field, restyle

#: el origen se dibuja con su color y este ancho (px), como en IngeCAD
ANCHO_ORIGEN = 5


def _valor(v):
    """NULL de QGIS -> None."""
    try:
        from qgis.core import NULL
        if v is None or v == NULL:
            return None
    except Exception:  # noqa: BLE001
        if v is None:
            return None
    return v


def _es_texto(lyr):
    return lyr.customProperty(TEXT_FLAG) == '1'


def _attrs(lyr, f):
    names = lyr.fields().names()
    return {c: _valor(f.attribute(c)) for c in igualar.CAMPOS if c in names}


def _hex_capa_cad(lyr, nombre):
    try:
        for l in json.loads(lyr.customProperty(CFG_KEY) or '{}').get('layers', []):
            if l.get('name') == nombre:
                c = l.get('color') or {}
                if c.get('rgb'):
                    return c['rgb']
                from ..capas.aci import aci_to_hex
                return aci_to_hex(c.get('aci', 7))
    except Exception:  # noqa: BLE001
        pass
    return None


def color_origen(lyr, attrs):
    """El color con que se ve el origen: el propio, el de su capa CAD o magenta."""
    v = attrs.get(igualar.color_campo(_es_texto(lyr)))
    if not (isinstance(v, str) and v.startswith('#')):
        v = _hex_capa_cad(lyr, attrs.get('LAYER_CODE') or '0')
    c = QColor(v) if v else QColor()
    return c if c.isValid() else QColor(255, 0, 255)


def _texto_valor(v):
    return 'PorCapa' if v in (None, '') else str(v)


class MatchPropCommand(EditCommand):
    """IGUALARPROP: origen resaltado, Intro confirma, destinos con todas las designaciones."""
    title = 'IGUALARPROP'
    select_prompt = igualar.PEDIDO_DESTINO

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.origen = None          # (capa, objeto)
        self.hl = None
        self.antes = {}             # fid -> {campo: valor que tenía}

    # ---------------------------------------------------- origen
    def start(self):
        pre = list(self.layer.selectedFeatureIds())
        self.layer.removeSelection()
        self.selecting = False
        if len(pre) == 1:            # un objeto ya elegido: es el origen (como IngeCAD)
            self._poner_origen(self.layer, self.layer.getFeature(pre[0]))
            self._confirmar()
            return
        self.prompt()

    def step_prompt(self):
        self.cl.set_prompt(igualar.PEDIDO_CONFIRMAR if self.origen else igualar.PEDIDO_ORIGEN)

    def step_point(self, p):
        hit = self._buscar(p)
        if hit is None:
            self.cl.echo('No hay ningún objeto ahí.')
        else:
            self._poner_origen(*hit)
        self.prompt()

    def step_text(self, text):
        self._resolve_and_apply(text)

    def step_enter(self):
        if self.origen is None:
            self.end()
            return
        self._confirmar()

    def _capas(self):
        canvas_layers = [l for l in self.canvas.layers() if isinstance(l, QgsVectorLayer) and l.isSpatial()]
        orden = [self.layer] + [l for l in canvas_layers if l is not self.layer]
        return [l for l in orden if l.customProperty('dibujo_cad/block_geom') != '1']

    def _buscar(self, p):
        for lyr in self._capas():
            fid, f = pick_feature(self.canvas, GeomIO(self.canvas, lyr), lyr, p)
            if fid is not None:
                return lyr, f
        return None

    def _poner_origen(self, lyr, f):
        self._quitar_resaltado()
        self.origen = (lyr, f)
        try:
            self.hl = QgsHighlight(self.canvas, f.geometry(), lyr)
            c = color_origen(lyr, _attrs(lyr, f))
            self.hl.setColor(c)
            fill = QColor(c)
            fill.setAlpha(40)
            self.hl.setFillColor(fill)
            self.hl.setWidth(ANCHO_ORIGEN)
            self.hl.show()
        except Exception:  # noqa: BLE001 - sin resaltado, la orden sigue
            self.hl = None

    def _quitar_resaltado(self):
        if self.hl is not None:
            try:
                self.hl.hide()
                self.canvas.scene().removeItem(self.hl)
            except Exception:  # noqa: BLE001
                pass
            self.hl = None

    def _confirmar(self):
        lyr, f = self.origen
        a = _attrs(lyr, f)
        partes = ['capa CAD %s' % (a.get('LAYER_CODE') or '0') if 'LAYER_CODE' in a else 'sin capa CAD',
                  'color %s' % _texto_valor(a.get(igualar.color_campo(_es_texto(lyr))))]
        if not _es_texto(lyr):
            partes += ['tipo %s' % _texto_valor(a.get('CAD_LTYPE')), 'grosor %s' % _texto_valor(a.get('CAD_LW'))]
        self.cl.echo('Origen: %s (capa "%s").' % (', '.join(partes), lyr.name()))
        self.selecting = True
        self._sel_init()
        self.prompt()

    # ---------------------------------------------------- destinos
    def _add(self, fids, remove=False):
        src_lyr, src_f = self.origen
        if src_lyr is self.layer:
            fids = [x for x in fids if x != src_f.id()]
        antes = list(self.sel)
        super()._add(fids, remove)
        self.layer.removeSelection()            # que se vea ya con lo nuevo
        ya = set(antes)
        ahora = set(self.sel)
        self._devolver([x for x in antes if x not in ahora])
        self._aplicar([x for x in self.sel if x not in ya])

    def on_text(self, text):
        if self.selecting:
            self._sel_init()
            k = _key(text)
            en_poligono = self.sel_mode in ('wpoly', 'cpoly', 'fence') and self.poly
            if k in ('H', 'DESHACER', 'UNDO') and not en_poligono:
                if self.sel_undo:
                    prev, actual = self.sel_undo.pop(), list(self.sel)
                    self._devolver([x for x in actual if x not in set(prev)])
                    self._aplicar([x for x in prev if x not in set(actual)])
                    self.sel = prev
                    self.cl.echo('%d en total' % len(self.sel))
                else:
                    self.cl.echo('Todas las designaciones ya se han deshecho.')
                self.prompt()
                return
        super().on_text(text)

    def _aplicar(self, fids):
        if not fids:
            return
        src_lyr, src_f = self.origen
        lyr = self.layer
        valores = igualar.a_copiar(_attrs(src_lyr, src_f), _es_texto(src_lyr), _es_texto(lyr),
                                   lyr.fields().names(), self.kind == 'point')
        if not valores:
            self.cl.echo('El origen no tiene propiedades CAD para copiar.')
            return
        cambio_estilo = False
        if 'LAYER_CODE' in valores:
            add_cad_layer_def([lyr], valores['LAYER_CODE'], sources=[src_lyr])
            cambio_estilo = True
        for campo in list(valores):
            if lyr.fields().indexOf(campo) == -1:
                tipo, largo = igualar.CAMPOS[campo]
                if not ensure_field(lyr, campo, tipo, largo or 20, self.cl.echo):
                    del valores[campo]
        names = lyr.fields().names()
        lyr.beginEditCommand('Igualar propiedades')
        for fid in fids:
            f = lyr.getFeature(fid)
            guardado = self.antes.setdefault(fid, {})
            for campo, v in valores.items():
                if campo not in guardado:
                    guardado[campo] = _valor(f.attribute(campo)) if campo in names else None
                lyr.changeAttributeValue(fid, lyr.fields().indexOf(campo), v)
        lyr.endEditCommand()
        self._repintar(cambio_estilo)

    def _devolver(self, fids):
        """E (quitar) y H (deshacer): esos objetos vuelven a como estaban."""
        fids = [x for x in fids if x in self.antes]
        if not fids:
            return
        lyr = self.layer
        lyr.beginEditCommand('Igualar propiedades (devolver)')
        for fid in fids:
            for campo, v in self.antes.pop(fid).items():
                i = lyr.fields().indexOf(campo)
                if i != -1:
                    lyr.changeAttributeValue(fid, i, v)
        lyr.endEditCommand()
        self._repintar(True)

    def _repintar(self, estilo):
        lyr = self.layer
        if estilo:
            restyle(lyr)
        if _es_texto(lyr):
            try:
                from .text_tool import refresh_text_colors
                refresh_text_colors(lyr)
            except Exception:  # noqa: BLE001
                pass
        lyr.triggerRepaint()

    def after_selection(self):
        self.cl.echo('%d objeto(s) igualado(s).' % len(self.antes))
        self.end()

    def cleanup(self):
        self._quitar_resaltado()

    def end(self):
        self._quitar_resaltado()
        super().end()


__all__ = ['MatchPropCommand', 'color_origen']
