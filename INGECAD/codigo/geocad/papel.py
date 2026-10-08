# SPDX-License-Identifier: GPL-3.0-or-later
"""Espacio papel como AutoCAD (módulo «Papel», 3.5.0).

En AutoCAD, la escala de la configuración de página de una presentación dice
cuántas unidades del dibujo es un milímetro de hoja. Con el dibujo en metros:

    1 mm = 0,001 unidades (m)

Entonces la hoja A3 mide 0,420 × 0,297 en el espacio papel, y la escala de
cada ventana gráfica se pone tal cual: 1:100 = ZOOM 1/100XP (1 m del papel
muestra 100 m del modelo; impreso, 1 m del modelo = 10 mm).

IngeCAD guardaba esa escala pero la ignoraba: dibujaba la hoja siempre en
milímetros (420 × 297) e imprimía la presentación siempre a 1 mm = 1 unidad.
Con el modelo en metros, una ventana a 1:100 mostraba todo 1000 veces chico
(una grilla de 100 m quedaba de 1 mm en vez de 1000 mm).

GeoCAD hace que IngeCAD respete esa escala, como AutoCAD:
1. La hoja, los márgenes y el área imprimible se dibujan en unidades del
   dibujo según la escala de la página (paper_frame).
2. La configuración de página sigue mostrando la hoja en mm.
3. Al imprimir o publicar la presentación, 1 mm de papel = la escala de la
   página (y el PDF sale del tamaño real de la hoja).
4. Las presentaciones nuevas de un dibujo en metros nacen con 1 mm = 0,001.
5. (3.6.0) En el desplegable de escala de la ventana gráfica se escribe la
   escala como en AutoCAD (1/100, 1:100, 1/250, 2:1...) y Enter la aplica.

Con escala 1:1 (dibujos en mm, presentaciones de siempre) nada cambia.
Apagado el módulo, IngeCAD queda como venía. Las cuentas no usan Qt.
"""
from __future__ import annotations

import math

from . import modulos

PROGRAMA = "ingecad"
PLUGIN_ID = "geocad"

#: Milímetros por unidad del dibujo, según $INSUNITS (4 mm, 5 cm, 6 m, 7 km).
MM_POR_UNIDAD = {4: 1.0, 5: 10.0, 6: 1000.0, 7: 1e6}

#: Bit «usar escala estándar» de plot_layout_flags (AutoCAD, grupo 70).
_BIT_ESCALA_ESTANDAR = 16


def activo() -> bool:
    return modulos.activo(PROGRAMA, "papel")


# ---------------------------------------------------------------- cuentas
def _num(dxf, campo, defecto):
    try:
        v = float(dxf.get(campo, defecto))
    except (TypeError, ValueError):
        return defecto
    return v if math.isfinite(v) else defecto


def unidades_por_mm(layout, campos: dict | None = None) -> float:
    """Unidades del dibujo por milímetro de hoja (o por pulgada, si la página
    está en pulgadas): «1 mm = 0,001 unidades» -> 0.001. ``campos`` son los
    valores nuevos de una configuración de página que todavía no se aplicó.
    Ajustar al papel o una escala rota -> 1 (como IngeCAD)."""
    campos = campos or {}
    dxf = layout.dxf
    tipo = campos.get("standard_scale_type")
    if tipo is None:
        try:
            tipo = int(dxf.get("standard_scale_type", 16))
        except (TypeError, ValueError):
            tipo = 16
    if int(tipo) == 0:                       # ajustar al papel
        return 1.0
    num = campos.get("scale_numerator")
    den = campos.get("scale_denominator")
    num = float(num) if num is not None else _num(dxf, "scale_numerator", 1.0)
    den = float(den) if den is not None else _num(dxf, "scale_denominator", 1.0)
    if not (num > 0.0 and den > 0.0):
        return 1.0
    k = den / num
    return k if math.isfinite(k) and k > 0.0 else 1.0


def _escala(rect, k):
    return None if rect is None else tuple(v * k for v in rect)


def marco(frame: dict, k: float) -> dict:
    """La hoja y el área imprimible de paper_frame, de mm a unidades."""
    if k == 1.0:
        return frame
    nuevo = dict(frame)
    nuevo["sheet"] = _escala(frame.get("sheet"), k)
    nuevo["printable"] = _escala(frame.get("printable"), k)
    return nuevo


def pagina_mm(pagina: dict, k: float) -> dict:
    """effective_page en mm aunque la hoja esté dibujada en unidades."""
    if k == 1.0:
        return pagina
    nuevo = dict(pagina)
    nuevo["width"] = pagina["width"] / k
    nuevo["height"] = pagina["height"] / k
    nuevo["margins"] = tuple(m / k for m in pagina["margins"])
    return nuevo


def mm_por_unidad(document) -> float:
    try:
        return MM_POR_UNIDAD.get(int(document.doc.header.get("$INSUNITS", 0)), 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def escala_hoja_metros(layout) -> bool:
    """Una presentación nueva de un dibujo en metros: 1 mm = 0,001 unidades
    (sólo si todavía está en 1:1, para no pisar lo que eligió el usuario)."""
    if abs(unidades_por_mm(layout) - 1.0) > 1e-12:
        return False
    dxf = layout.dxf
    dxf.scale_numerator = 1.0
    dxf.scale_denominator = 0.001
    dxf.standard_scale_type = 16             # personalizada
    try:
        flags = int(dxf.get("plot_layout_flags", 0) or 0)
    except (TypeError, ValueError):
        flags = 0
    dxf.plot_layout_flags = flags & ~_BIT_ESCALA_ESTANDAR
    return True


# ---------------------------------------------------------------- envoltorios
def _envolver_paper_frame(original):
    def paper_frame(layout):
        frame = original(layout)
        if not activo():
            return frame
        return marco(frame, unidades_por_mm(layout))
    paper_frame._puente_original = original
    paper_frame._puente_fabrica = _envolver_paper_frame
    return paper_frame


def _envolver_effective_page(original):
    def effective_page(layout):
        pagina = original(layout)            # usa paper_frame (en unidades)
        if not activo():
            return pagina
        return pagina_mm(pagina, unidades_por_mm(layout))
    effective_page._puente_original = original
    effective_page._puente_fabrica = _envolver_effective_page
    return effective_page


def _envolver_page_setup_command(original):
    def page_setup_command(layout, *args, **kwargs):
        cmd = original(layout, *args, **kwargs)
        campos = getattr(cmd, "_fields", None)
        if not activo() or not isinstance(campos, dict):
            return cmd
        # AutoCAD guarda los límites del papel en unidades del dibujo
        k = unidades_por_mm(layout, campos)
        if k != 1.0:
            for clave in ("limmin", "limmax"):
                if clave in campos:
                    campos[clave] = tuple(v * k for v in campos[clave])
        return cmd
    page_setup_command._puente_original = original
    page_setup_command._puente_fabrica = _envolver_page_setup_command
    return page_setup_command


def _envolver_layout_sheet(original):
    def layout_sheet(document, layout_name):
        (ancho, alto), hoja = original(document, layout_name)
        if not activo():
            return (ancho, alto), hoja
        k = unidades_por_mm(document.doc.layouts.get(layout_name))
        return (ancho / k, alto / k), hoja    # el tamaño del PDF, en mm
    layout_sheet._puente_original = original
    layout_sheet._puente_fabrica = _envolver_layout_sheet
    return layout_sheet


def _envolver_plot_layout(original):
    def plot_layout(document, printer, layout_name, ctb=None, painter=None):
        k = (unidades_por_mm(document.doc.layouts.get(layout_name))
             if activo() else 1.0)
        if k == 1.0:
            return original(document, printer, layout_name, ctb=ctb, painter=painter)
        from formats import pdf_out
        _tam, hoja = pdf_out.layout_sheet(document, layout_name)
        printer.setFullPage(True)
        # IngeCAD pasa el grosor de las plumas a mm de la escena; con la
        # hoja en metros, 0,25 mm tiene que ser 0,00025 unidades.
        plumas = pdf_out._use_physical_pens

        def plumas_en_unidades(scene):
            plumas(scene)
            for item in scene.items():
                if hasattr(item, "pen"):
                    pen = item.pen()
                    if not pen.isCosmetic():
                        pen.setWidthF(pen.widthF() * k)
                        item.setPen(pen)

        pdf_out._use_physical_pens = plumas_en_unidades
        try:
            pdf_out.plot(document, printer, layout_name, area=hoja,
                         mm_per_unit=1.0 / k, physical_pens=True, ctb=ctb,
                         painter=painter)
        finally:
            pdf_out._use_physical_pens = plumas
    plot_layout._puente_original = original
    plot_layout._puente_fabrica = _envolver_plot_layout
    return plot_layout


def _envolver_nueva_do(original):
    def do(self, document):
        original(self, document)
        if not activo() or mm_por_unidad(document) != 1000.0:
            return
        try:
            layout = document.doc.layouts.get(self.layout_name)
            escala_hoja_metros(layout)
        except Exception:  # noqa: BLE001
            pass
    do._puente_original = original
    do._puente_fabrica = _envolver_nueva_do
    return do


# ---------------------------------------------------------------- escala escrita (3.6.0)
def parse_escala(texto: str):
    """La escala escrita como en AutoCAD -> papel/modelo, o None.
    1/100, 1:100, 1/100XP -> 0.01; 2:1 -> 2; 1:2,5 -> 0.4; 100 -> 0.01 (1:100)."""
    t = (texto or "").strip().upper().replace(" ", "").replace(",", ".")
    if t.endswith("XP"):
        t = t[:-2]
    if not t:
        return None
    try:
        for sep in ("/", ":"):
            if sep in t:
                num, den = t.split(sep, 1)
                factor = float(num) / float(den)
                break
        else:
            factor = 1.0 / float(t)              # «100» = 1:100
    except (ValueError, ZeroDivisionError):
        return None
    return factor if math.isfinite(factor) and factor > 0.0 else None


def _refrescar(window) -> None:
    """El desplegable vuelve a mostrar la escala de la ventana (y borra lo
    escrito, aunque el renglón elegido no haya cambiado)."""
    window._refresh_vp_scale_combo()
    combo = getattr(window, "_vp_scale_combo", None)
    if combo is not None and combo.isEditable():
        combo.setEditText(combo.currentText())


def aplicar_escala(window, texto: str) -> bool:
    """Enter en el desplegable de escala: la ventana gráfica toma esa escala
    (como elegirla de la lista; se deshace con U)."""
    from core import layouts as L

    echo = window.command_line.echo
    factor = parse_escala(texto)
    if factor is None:
        echo(f"Escala no válida: «{texto}». Escriba 1/100, 1:100 o 2:1.")
        _refrescar(window)
        return False
    vp = window._scale_target_vp()
    if vp is None:
        echo("Elija una ventana (su borde) o entre con MSPACE primero.")
        _refrescar(window)
        return False
    if L.is_viewport_locked(vp):
        echo("La ventana está bloqueada: VPLOCK para desbloquearla.")
        _refrescar(window)
        return False
    window._vp_gesture_commit()
    window.history.execute(L.xp_zoom_command(vp, factor))
    echo(f"Escala de la ventana: {L.scale_label(factor)}.")
    window.regen_in_memory()
    _refrescar(window)
    return True


def _enter_del_texto(window, combo) -> None:
    """Enter visto por la señal del texto. Si lo escrito es un renglón de la
    lista, el desplegable de IngeCAD ya lo aplicó: no se aplica dos veces."""
    if getattr(combo, "_geocad_filtro", None) is None:
        return                                   # módulo apagado
    from core import layouts as L

    factor = parse_escala(combo.lineEdit().text())
    vp = window._scale_target_vp()
    if factor is not None and vp is not None:
        actual = L.viewport_scale(vp)
        if abs(actual - factor) <= 1e-9 * max(1.0, factor):
            _refrescar(window)
            return
    aplicar_escala(window, combo.lineEdit().text())


def preparar_combo(window) -> None:
    """Con el módulo prendido, en el desplegable de escala de IngeCAD se puede
    escribir la escala; apagado, vuelve a ser sólo la lista."""
    combo = getattr(window, "_vp_scale_combo", None)
    if combo is None:
        return
    try:
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QComboBox
    except Exception:  # noqa: BLE001
        return
    filtro = getattr(combo, "_geocad_filtro", None)
    if not activo():
        if filtro is not None:
            combo.removeEventFilter(filtro)
            combo.setEditable(False)
            combo._geocad_filtro = None
            combo.setToolTip(getattr(combo, "_geocad_tooltip", combo.toolTip()))
            window._refresh_vp_scale_combo()
        return
    if filtro is not None:
        return

    class _Enter(QObject):
        """Enter: se aplica la escala escrita. Se consume la tecla para que el
        desplegable no elija además un renglón parecido.

        Va en el desplegable Y en su texto: el foco lo tiene el desplegable
        (es el «focus proxy» del texto) y él le pasa las teclas al texto por
        dentro, sin pasar por los filtros del texto."""

        def eventFilter(self, obj, event):  # noqa: N802
            tipo = event.type()
            if tipo not in (QEvent.KeyPress, QEvent.ShortcutOverride):
                return False
            if event.key() not in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                return False
            if tipo == QEvent.ShortcutOverride:
                event.accept()          # la tecla es nuestra, no de un atajo
                return True
            if event.key() == Qt.Key_Escape:
                _refrescar(window)
            else:
                aplicar_escala(window, combo.lineEdit().text())
            return True

    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setCompleter(None)          # sin autocompletar: «1:2» no se vuelve «1:20»
    filtro = _Enter(combo)
    combo.installEventFilter(filtro)
    combo.lineEdit().installEventFilter(filtro)
    # Con un método de entrada (IBus en GNOME/Wayland) el Enter llega al texto
    # por otro camino y no pasa por los filtros: la señal del propio texto lo
    # ve siempre. Si el filtro ya lo tomó, la señal no se emite.
    combo.lineEdit().returnPressed.connect(lambda: _enter_del_texto(window, combo))
    combo._geocad_filtro = filtro
    combo._geocad_tooltip = combo.toolTip()
    combo.setToolTip("Escala de la ventana: elegir de la lista o escribir "
                     "1/100, 1:100, 1/250, 2:1... y Enter (GeoCAD Yaguareté)")
    _refrescar(window)


LAYOUTS = {"paper_frame": _envolver_paper_frame,
           "effective_page": _envolver_effective_page,
           "page_setup_command": _envolver_page_setup_command}
PDF_OUT = {"layout_sheet": _envolver_layout_sheet,
           "plot_layout": _envolver_plot_layout}


def _aplicar(objeto, envoltorios: dict, envolver) -> None:
    for nombre, fabrica in envoltorios.items():
        if getattr(getattr(objeto, nombre, None), "_puente_fabrica", None) is not fabrica:
            envolver(objeto, nombre, fabrica, reemplazar=True)


def instalar() -> None:
    """Se llama al cargar el plugin. Los envoltorios miran ``activo()`` en
    cada llamada: prender o apagar el módulo no necesita reinstalarlos."""
    from .dibujo import envolver
    try:
        from core import layouts
    except Exception:  # noqa: BLE001
        return
    _aplicar(layouts, LAYOUTS, envolver)
    nueva = getattr(layouts, "NewLayoutCommand", None)
    if nueva is not None:
        _aplicar(nueva, {"do": _envolver_nueva_do}, envolver)
    try:
        from formats import pdf_out              # usa Qt: no está en las pruebas
    except Exception:  # noqa: BLE001
        return
    _aplicar(pdf_out, PDF_OUT, envolver)
