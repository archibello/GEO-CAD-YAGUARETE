# SPDX-License-Identifier: GPL-3.0-or-later
"""TEXTO (TEXT) como en AutoCAD, para IngeCAD.

El TEXT de IngeCAD ya tiene las preguntas de AutoCAD (punto inicial,
altura, ángulo, escribir en el lugar), pero en «Altura» y en «Ángulo» sólo
acepta números: un clic ahí no hace nada y no se ve ninguna línea elástica.

Acá, como en AutoCAD:
  1er punto  el punto inicial del texto;
  2º punto   la altura: la distancia desde el primero (o se escribe);
  3er punto  la dirección: el ángulo desde el primero (o se escribe).
Mientras se elige cada punto, una línea elástica desde el primero y, junto
al cursor, la altura o el ángulo que va a quedar. Y en el lugar, una «Ɪ»
de muestra dibujada por IngeCAD como texto de verdad (estilo, fuente y capa
actuales): al elegir la altura crece con el cursor; al elegir la dirección,
con esa altura, gira con el cursor. Si la fuente del estilo no tiene la «Ɪ»
(DejaVu Sans, la de siempre, no la tiene: salía un rectángulo vacío), la
muestra es una «I». La muestra se crea, se dibuja y se borra acá mismo:
nunca queda en el plano ni en el historial.

Al terminar (Esc), los textos escritos quedan elegidos: la paleta
Properties los muestra y ahí se retocan (altura, estilo, giro, capa...).
Un TEXT elegido se resalta con su recuadro girado y del largo del texto,
como en AutoCAD (IngeCAD dibuja la caja derecha que lo envuelve, que en un
texto inclinado queda mucho más grande). Y con un clic, un TEXT se elige
sólo desde adentro de ese recuadro girado, nunca desde afuera: IngeCAD lo
elegía desde cualquier punto de la caja derecha (más la tolerancia), y en
un texto a 45° eso es un cuadrado enorme alrededor.

Al editar un TEXT en el lugar (doble clic), la caja mide lo escrito y crece
letra a letra, como en AutoCAD (3.15.3). IngeCAD le daba el ancho de su
barra de formato, que en un TEXT está oculta, y al menos 8 letras: con una
«C» quedaba una franja de punta a punta.
La edición concluye con Enter (guarda) o con Esc (descarta), como en
IngeCAD; al concluir, el recuadro girado se rehace con el texto que quedó.

Se apaga con el módulo «texto»: IngeCAD queda como venía.
"""
from __future__ import annotations

import math

from core import actions
from tools.draw import TextTool

from . import modulos

PROGRAMA = "ingecad"


def activo() -> bool:
    return modulos.activo(PROGRAMA, "texto")


def altura(p1, p2) -> float:
    return math.dist(p1, p2)


def angulo(p1, p2) -> float:
    """Grados, antihorario desde el este, en [0, 360)."""
    return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])) % 360.0


def _fmt(valor: float) -> str:
    return f"{valor:.4f}".rstrip("0").rstrip(".")


#: el carácter de muestra mientras se eligen la altura y la dirección, y el
#: de reemplazo cuando la fuente del estilo no lo tiene
MUESTRA = "Ɪ"
MUESTRA_SIMPLE = "I"


def caracter_muestra(doc, estilo=None) -> str:
    """«Ɪ» si la fuente (TrueType) del estilo la tiene; si no, «I»."""
    try:
        from ezdxf.fonts import fonts

        nombre = estilo if estilo and estilo in doc.styles \
            else doc.header.get("$TEXTSTYLE", "Standard")
        fuente = doc.styles.get(nombre).dxf.get("font", "") or "txt"
        cmap = getattr(fonts.make_font(fuente, 1.0).glyph_cache, "cmap", None)
        if cmap and ord(MUESTRA) in cmap:
            return MUESTRA
    except Exception:  # noqa: BLE001 -- sin fuente que consultar: la segura
        pass
    return MUESTRA_SIMPLE


class _Muestra:
    """La muestra que devuelve ``preview_command``. La vista previa de IngeCAD
    está hecha para cotas: con un TEXT fallaba antes de borrarlo y la «Ɪ»
    quedaba en el plano. Por eso no tiene ``_factory`` (sin GeoCAD, IngeCAD
    no dibuja nada) y la escena la arma ``escena`` (ver ``instalar``)."""

    def __init__(self, pos, altura, giro, alineacion, estilo) -> None:
        self.datos = (pos, altura, giro, alineacion, estilo)

    def comando(self, doc):
        pos, altura, giro, alineacion, estilo = self.datos
        return actions.add_text(pos, caracter_muestra(doc, estilo), altura, giro,
                                align=alineacion, style=estilo)

    def escena(self, controlador):
        """Crea la «Ɪ», arma su dibujo y la borra, pase lo que pase."""
        from render.backend import build_scene_for_entities

        document = controlador.window.document
        comando = self.comando(document.doc)
        espacio = comando.space(document)
        entidad = comando._factory(espacio)
        try:
            capa = document.doc.header.get("$CLAYER", "0")
            if capa in document.doc.layers:
                entidad.dxf.layer = capa
            return build_scene_for_entities(document, [entidad], controlador._flatten,
                                            controlador.canvas_space())
        finally:
            espacio.delete_entity(entidad)


def recuadro(e):
    """Las 4 esquinas del recuadro de un TEXT, giradas con él (o None):
    la caja del texto sin girar, girada después alrededor de su punto."""
    from ezdxf import bbox

    if e.dxftype() != "TEXT" or e.dxf.get("halign", 0) in (3, 5):   # ALIGNED / FIT
        return None
    copia = e.copy()
    copia.dxf.rotation = 0.0
    caja = bbox.extents([copia], fast=False)
    if not caja.has_data:
        return None
    justificado = e.dxf.get("halign", 0) or e.dxf.get("valign", 0)
    centro = e.dxf.align_point if justificado and e.dxf.hasattr("align_point") \
        else e.dxf.insert
    r = math.radians(e.dxf.get("rotation", 0.0))
    c, s = math.cos(r), math.sin(r)
    x0, y0, x1, y1 = caja.extmin.x, caja.extmin.y, caja.extmax.x, caja.extmax.y
    out = []
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        dx, dy = x - centro.x, y - centro.y
        out.append((centro.x + dx * c - dy * s, centro.y + dx * s + dy * c))
    return out


class TextoTool(TextTool):
    """TEXT de IngeCAD + altura y dirección con el ratón + elegidos al final."""

    def start(self) -> None:
        super().start()
        self._hechos: list = []

    def _pide(self) -> str | None:
        """Qué pregunta está esperando un punto: «altura», «angulo» o None."""
        if self.typing or self._pos is None or getattr(self, "_await", None):
            return None
        if self._height is None:
            return "altura"
        if self._rotation is None and self._align != "FIT":
            return "angulo"
        return None

    def on_point(self, point) -> None:
        pide = self._pide()
        if pide == "altura":
            h = altura(self._pos, point)
            if h > 0:
                self.on_option(_fmt(h))       # como si se escribiera
            return
        if pide == "angulo":
            if altura(self._pos, point) > 0:
                self.on_option(_fmt(angulo(self._pos, point)))
            return
        super().on_point(point)
        if self._pos is not None and not self.typing:
            self.last_point = self._pos       # ORTO y la línea elástica, desde el 1er punto

    def preview_segments(self, cursor):
        if self._pide() and cursor is not None:
            return [(self._pos, cursor)]
        return []

    def muestra(self, cursor):
        """(altura, giro) de la «Ɪ» de muestra con el cursor ahí, o None.
        Al elegir la altura: la distancia, con el giro ya escrito o 0; al
        elegir la dirección: la altura elegida, girada hacia el cursor."""
        pide = self._pide()
        if pide is None or cursor is None or altura(self._pos, cursor) <= 0:
            return None
        if pide == "altura":
            return altura(self._pos, cursor), self._rotation or 0.0
        return self._height, angulo(self._pos, cursor)

    def preview_command(self, cursor):
        """La «Ɪ» de muestra: IngeCAD la dibuja como el texto que va a quedar."""
        medida = self.muestra(cursor)
        if medida is None:
            return None
        alineacion = "LEFT" if self._align in ("ALIGNED", "FIT") else self._align
        return _Muestra(self._pos, medida[0], medida[1], alineacion, self._style)

    def resaltado(self, cursor) -> dict:
        """Junto al cursor, la altura o el ángulo que va a quedar."""
        out = {"textos": []}
        pide = self._pide()
        if pide is None or cursor is None:
            return out
        if pide == "altura":
            out["textos"] = [(tuple(cursor), f"Altura {_fmt(altura(self._pos, cursor))}")]
        else:
            out["textos"] = [(tuple(cursor), f"Ángulo {_fmt(angulo(self._pos, cursor))}°")]
        return out

    def _commit_line(self) -> None:
        if self._buffer.strip():
            comando = actions.add_text(
                self._pos, self._buffer, self._height, self._rotation,
                align=self._align, p2=self._p2, style=self._style)
            self.ctx.execute(comando)
            type(self)._last_final = (self._pos, self._height, self._rotation)
            if getattr(comando, "entity", None) is not None:
                self._hechos.append(comando.entity)

    def finish_typing(self) -> None:
        self._commit_line()
        self.typing = False
        servicios = self.ctx.services
        hechos = [e for e in self._hechos if e.is_alive]
        self.ctx.finish()
        if hechos and servicios is not None:
            elegir(servicios, hechos)


def elegir(servicios, entidades) -> None:
    """Deja elegidos los textos recién hechos: la paleta Properties los muestra."""
    from . import seleccion
    try:
        servicios.selection = {e.dxf.handle for e in entidades}
        seleccion._cambio(servicios)
    except Exception:  # noqa: BLE001 -- sin elegir: los textos ya están hechos
        pass


# ---------------------------------------------------------------- en IngeCAD
def _envolver_escena(original):
    def _preview_scene_for(self, command):
        if isinstance(command, _Muestra):
            self._geocad_muestra = True
            return command.escena(self)
        return original(self, command)
    _preview_scene_for._puente_original = original
    _preview_scene_for._puente_fabrica = _envolver_escena
    return _preview_scene_for


def _envolver_limpiar(original):
    """IngeCAD, al pasar a escribir o al terminar, a veces no saca la vista
    previa (``_preview_now`` olvida la clave antes de limpiar): la última «I»
    quedaba dibujada. La muestra se saca siempre."""
    def _clear_preview(self):
        original(self)
        if getattr(self, "_geocad_muestra", False):
            self._geocad_muestra = False
            self.window.viewport.set_preview_scene(None)
    _clear_preview._puente_original = original
    _clear_preview._puente_fabrica = _envolver_limpiar
    return _clear_preview


def resaltar_girados(index, seleccion, boxes):
    """De los TEXT elegidos: (los 4 lados de su recuadro girado, las filas de
    ``boxes`` que esos lados reemplazan: la caja derecha de IngeCAD)."""
    from core.select import GeometryIndex

    lados, fuera = [], set()
    for h in seleccion:
        e = index.entity(h) if hasattr(index, "entity") else None
        if e is None or not e.is_alive or e.dxftype() != "TEXT":
            continue
        try:
            esquinas = recuadro(e)
            cajas = index.boxes_of({h}) if hasattr(index, "boxes_of") else []
            if not len(cajas):
                cajas = [GeometryIndex._text_extents(e)]
        except Exception:  # noqa: BLE001 -- sin recuadro: queda la caja de IngeCAD
            continue
        if not esquinas or cajas[0] is None:
            continue
        for caja in cajas:                       # la que IngeCAD tiene guardada
            for i, fila in enumerate(boxes):
                if i not in fuera and all(abs(a - b) <= 1e-9 * max(1.0, abs(b))
                                          for a, b in zip(fila, caja)):
                    fuera.add(i)
                    break
        lados += [(*a, *b) for a, b in zip(esquinas, esquinas[1:] + esquinas[:1])]
    return lados, fuera


def adentro(punto, esquinas) -> bool:
    """¿El punto está dentro del recuadro (o sobre su borde)?"""
    x, y = punto
    signos = set()
    for (ax, ay), (bx, by) in zip(esquinas, esquinas[1:] + esquinas[:1]):
        cruz = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if abs(cruz) > 1e-12 * max(1.0, abs(bx - ax) + abs(by - ay)) ** 2:
            signos.add(cruz > 0)
    return len(signos) <= 1


def firma(e):
    """Lo que hace al recuadro de un TEXT. Editar el texto en el lugar no
    cambia la versión del índice de IngeCAD: el recuadro guardado quedaba
    con el largo viejo."""
    try:
        d = e.dxf
        return (d.text, d.get("height"), d.get("rotation"), d.get("width"),
                d.get("style"), d.get("halign"), d.get("valign"),
                tuple(d.insert), tuple(d.get("align_point") or ()))
    except Exception:  # noqa: BLE001
        return None


def refrescar(index, handles) -> None:
    """Pone al día en el índice de IngeCAD los TEXT editados en el lugar: su
    edición no lo toca y quedaban su caja derecha vieja (el rectángulo
    «fantasma» del resaltado) y el clic de antes. Como IngeCAD en sus otras
    ediciones: sacar y volver a poner sólo esos objetos."""
    vivos = [index.entity(h) for h in handles]
    vivos = [e for e in vivos if e is not None and e.is_alive]
    try:
        index.remove_handles(list(handles))
        if vivos:
            index.add_entities(vivos)
    except Exception:  # noqa: BLE001 -- índice sin edición quirúrgica
        index.invalidate()


def _recuadro_de(index, handle):
    """El recuadro girado del TEXT ``handle`` (guardado mientras el texto no
    cambie), o None si no es un TEXT con recuadro."""
    memo = getattr(index, "_geocad_recuadros", None)
    if not isinstance(memo, dict):     # vacío, o el de 3.15.1-3.15.4 (una tupla)
        memo = index._geocad_recuadros = {}
    e = index.entity(handle)
    if e is None or not e.is_alive or e.dxftype() != "TEXT":
        return None
    f = firma(e)
    guardado = memo.get(handle)
    if guardado is not None and guardado[0] != f:
        refrescar(index, [handle])             # editado: su caja vieja, afuera
    if guardado is None or guardado[0] != f:
        try:
            esquinas = recuadro(e)
        except Exception:  # noqa: BLE001 -- sin recuadro: como IngeCAD
            esquinas = None
        guardado = memo[handle] = (f, esquinas)
    return guardado[1]


def fuera_del_texto(index, handle, cursor) -> bool:
    """¿``handle`` es un TEXT y el cursor queda fuera de su recuadro girado?
    Ante cualquier error, no: el clic queda como en IngeCAD."""
    try:
        esquinas = _recuadro_de(index, handle)
        return bool(esquinas) and not adentro(cursor, esquinas)
    except Exception:  # noqa: BLE001 -- nunca romper el clic
        return False


def _envolver_pick_all(original):
    def pick_all(self, cursor, tolerance):
        hechos = original(self, cursor, tolerance)
        if not activo():
            return hechos
        return [h for h in hechos if not fuera_del_texto(self, h, cursor)]
    pick_all._puente_original = original
    pick_all._puente_fabrica = _envolver_pick_all
    return pick_all


def _envolver_pick(original):
    def pick(self, cursor, tolerance):
        h = original(self, cursor, tolerance)
        if h is None or not activo() or not fuera_del_texto(self, h, cursor):
            return h
        # el TEXT ganó por su caja derecha, desde afuera: el siguiente
        # (pick_all ordena igual que pick y ya saca esos textos)
        quedan = type(self).pick_all(self, cursor, tolerance)
        return quedan[0] if quedan else None
    pick._puente_original = original
    pick._puente_fabrica = _envolver_pick
    return pick


def ancho_caja(ideal_px: float, cursor_px: float, letra_px: float) -> int:
    """Ancho (px) de la caja de un TEXT en edición: lo escrito, el cursor y
    un margen; vacía, el lugar de una letra."""
    return int(math.ceil(max(ideal_px, 0.6 * letra_px))) + int(cursor_px) + 10


def _envolver_geometria(original):
    def _sync_geometry(self):
        original(self)
        if not getattr(self, "_single_line", False) or getattr(self, "_closed", False) \
                or not activo():
            return
        try:
            g = self.geometry()
            ancho = ancho_caja(self.edit.document().idealWidth(),
                               self.edit.cursorWidth(), self._base_px())
            if ancho < g.width():
                self.edit.document().setTextWidth(ancho - 6)
                self.setGeometry(g.x(), g.y(), ancho, g.height())
        except Exception:  # noqa: BLE001 -- queda la caja de IngeCAD
            pass
    _sync_geometry._puente_original = original
    _sync_geometry._puente_fabrica = _envolver_geometria
    return _sync_geometry


#: más elegidos que esto: sin firmas (con miles, el cuadro se haría lento)
MAX_FIRMAS = 2000


def _firmas(index, seleccion):
    """Las firmas de los TEXT elegidos: el resaltado se rehace si cambian."""
    if len(seleccion) > MAX_FIRMAS or not hasattr(index, "entity"):
        return None
    out = []
    for h in seleccion:
        e = index.entity(h)
        if e is not None and e.is_alive and e.dxftype() == "TEXT":
            out.append((h, firma(e)))
    return tuple(sorted(out))


def _envolver_resaltado(original):
    def highlight_geometry(self):
        segs, circles, boxes = original(self)
        if not activo() or not self.selection or self.index is None:
            return segs, circles, boxes
        firmas = _firmas(self.index, self.selection)
        vistas = getattr(self, "_geocad_firmas_vistas", None)
        self._geocad_firmas_vistas = (id(self.index), dict(firmas or ()))
        try:
            if firmas and isinstance(vistas, tuple) and len(vistas) == 2 \
                    and vistas[0] == id(self.index) and isinstance(vistas[1], dict):
                editados = [h for h, f in firmas if h in vistas[1] and vistas[1][h] != f]
                if editados:
                    refrescar(self.index, editados)
                    segs, circles, boxes = original(self)
        except Exception:  # noqa: BLE001 -- queda el resaltado de IngeCAD
            pass
        if not len(boxes):
            return segs, circles, boxes
        clave = (self.index.version, frozenset(self.selection), id(boxes), firmas)
        guardado = getattr(self, "_geocad_texto_resaltado", None)
        if guardado is not None and guardado[0] == clave:
            return guardado[1]
        import numpy as np
        try:
            lados, fuera = resaltar_girados(self.index, self.selection, boxes)
        except Exception:  # noqa: BLE001
            lados, fuera = [], set()
        if lados:
            quedan = [i for i in range(len(boxes)) if i not in fuera]
            boxes = np.asarray(boxes)[quedan] if quedan else np.empty((0, 4))
            segs = np.vstack([np.asarray(segs).reshape(-1, 4), np.asarray(lados, dtype=float)])
        self._geocad_texto_resaltado = (clave, (segs, circles, boxes))
        return segs, circles, boxes
    highlight_geometry._puente_original = original
    highlight_geometry._puente_fabrica = _envolver_resaltado
    return highlight_geometry


def instalar() -> None:
    """Se llama al cargar el plugin. La escena de la muestra se arma siempre
    (sólo nuestra herramienta la pide); el recuadro girado y el clic dentro
    de él miran ``activo()``."""
    from .dibujo import envolver
    try:
        from core.select import GeometryIndex
    except Exception:  # noqa: BLE001
        GeometryIndex = None
    if GeometryIndex is not None:
        for nombre, fabrica in (("pick_all", _envolver_pick_all), ("pick", _envolver_pick)):
            actual = getattr(GeometryIndex, nombre, None)
            if actual is not None and getattr(actual, "_puente_fabrica", None) is not fabrica:
                envolver(GeometryIndex, nombre, fabrica, reemplazar=True)
    try:
        from views.mtext_editor import MTextInPlaceEditor
    except Exception:  # noqa: BLE001 -- sin Qt (pruebas)
        MTextInPlaceEditor = None
    if MTextInPlaceEditor is not None:
        actual = getattr(MTextInPlaceEditor, "_sync_geometry", None)
        if actual is not None and getattr(actual, "_puente_fabrica", None) is not _envolver_geometria:
            envolver(MTextInPlaceEditor, "_sync_geometry", _envolver_geometria, reemplazar=True)
    try:
        from views.tool_controller import ToolController
    except Exception:  # noqa: BLE001 -- sin la ventana de IngeCAD (pruebas)
        return
    for nombre, fabrica in (("_preview_scene_for", _envolver_escena),
                            ("_clear_preview", _envolver_limpiar),
                            ("highlight_geometry", _envolver_resaltado)):
        actual = getattr(ToolController, nombre, None)
        if actual is not None and getattr(actual, "_puente_fabrica", None) is not fabrica:
            envolver(ToolController, nombre, fabrica, reemplazar=True)
