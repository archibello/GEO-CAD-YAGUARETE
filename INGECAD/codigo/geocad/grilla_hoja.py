# SPDX-License-Identifier: GPL-3.0-or-later
"""Grilla de hoja (GRILLAHOJA, módulo «Papel», 3.85.0).

Como la grilla de referencia de Vectorworks: una grilla milimetrada celeste
sobre la hoja de una presentación, que se ve en pantalla y NO se imprime
(Fernando, 19/11/2026).

- Vale sólo con la hoja en milímetros: papel en mm y la escala de la página
  en «1 mm = 1 unidad» (dibujo en mm) o «1 mm = 0,001 unidades» (dibujo en
  metros). Si la hoja no está así, el botón la pasa a mm (dibujo en metros
  -> 0,001; en mm -> 1; si no se sabe, pregunta) y escala lo dibujado en la
  hoja para que quede igual sobre el papel. Todo en un solo U.
- Líneas cada 1 mm, más marcadas cada 5 y cada 10 mm, medidas en el papel y
  desde la esquina de la hoja. Al alejarse quedan sólo las de 5 o de 10, y
  si no entran se apaga: nunca una trama gris.
- Casi imperceptible (Fernando: «para que no interfiera con la visibilidad
  de los objetos a imprimir»): celeste muy transparente, 1 píxel, debajo del
  dibujo, sólo dentro de la hoja.
- No se imprime: se pinta con el lienzo de IngeCAD, al lado de su grilla
  (GRID, F7), que tampoco va al PDF ni a la impresora.

Se pinta envolviendo ``Viewport.paintGL`` y ``Viewport._draw_grid``: IngeCAD
pinta la hoja, después la grilla y después el dibujo. Mientras la grilla de
hoja se ve, ``grid_on`` vale True sólo durante el pintado y la grilla de
IngeCAD se dibuja únicamente si el usuario la tenía prendida.
"""
from __future__ import annotations

import math
from importlib import import_module

from . import config, modulos

PROGRAMA = "ingecad"

#: Pasos de la grilla, en milímetros de papel.
PASOS_MM = (1, 5, 10)
#: Separación mínima en pantalla para que un paso se dibuje (3.85.2: 3 px,
#: con la de 1 mm de medio píxel; más junta sería un tinte, no líneas).
MIN_PX = 3.0
#: Celeste de la grilla.
CELESTE = (70, 160, 230)
#: Opacidad (0-255) de las líneas de 1, 5 y 10 mm por intensidad. 3.85.1:
#: Fernando eligió la Media entre tres hojas de muestra («la 3.85.0 quedó
#: muy clarito»). 3.85.2: el módulo de 1 cm se lee a simple vista, como en
#: el papel milimetrado impreso (la de 10 mm casi no se distinguía de la de
#: 5 mm y se contaban celdas de 5 mm como módulos): cada medida con su
#: grosor (Fernando: «cada una con su espesor»; eligió la muestra C).
INTENSIDADES = {
    "suave": (25, 42, 70),
    "media": (35, 60, 100),
    "marcada": (45, 78, 130),
}
#: Grosor en píxeles de pantalla de las líneas de 1, 5 y 10 mm (muestra C).
#: Se pinta en píxeles físicos: con la escala ×2 de la pantalla, 1½ px son
#: 3 físicos; con ×1, ½ px es 1 px con la mitad de opacidad y 1½ px es 1 px
#: más uno al lado con la mitad.
GROSOR = (0.5, 1.0, 1.5)
ETIQUETAS = (("suave", "Suave"), ("media", "Media"), ("marcada", "Marcada"))
#: La de fábrica.
DE_FABRICA = "media"

#: Milímetros por unidad del dibujo, según $INSUNITS (4 mm, 6 m).
_MM_DESTINO = {4: 1.0, 6: 1000.0}
#: Bit «usar escala estándar» de plot_layout_flags.
_BIT_ESCALA_ESTANDAR = 16

#: Lo elegido, leído una vez (paintGL no lee archivos en cada cuadro).
_estado = {"prendida": None, "intensidad": None}


# ---------------------------------------------------------------- ajustes
def activo() -> bool:
    return modulos.activo(PROGRAMA, "papel")


def _cargar() -> None:
    if _estado["prendida"] is None:
        try:
            valores = config.load()
        except Exception:  # noqa: BLE001
            valores = {}
        _al_guardar(valores)


def _al_guardar(valores: dict) -> None:
    _estado["prendida"] = bool(valores.get("grilla_hoja", False))
    intensidad = valores.get("grilla_hoja_intensidad", DE_FABRICA)
    _estado["intensidad"] = intensidad if intensidad in INTENSIDADES else DE_FABRICA


def prendida() -> bool:
    _cargar()
    return bool(_estado["prendida"])


def intensidad() -> str:
    _cargar()
    return _estado["intensidad"]


def guardar(prender: bool | None = None, nivel: str | None = None) -> None:
    cambios = {}
    if prender is not None:
        cambios["grilla_hoja"] = bool(prender)
    if nivel is not None:
        cambios["grilla_hoja_intensidad"] = nivel
    if not cambios:
        return
    try:
        _al_guardar(config.save(cambios, PROGRAMA))
    except Exception:  # noqa: BLE001 -- sin archivo, vale para esta sesión
        if prender is not None:
            _estado["prendida"] = bool(prender)
        if nivel in INTENSIDADES:
            _estado["intensidad"] = nivel


def alfas(nivel: str | None = None) -> tuple:
    return INTENSIDADES.get(nivel or intensidad(), INTENSIDADES[DE_FABRICA])


# ---------------------------------------------------------------- la hoja en mm
def _num(dxf, campo, defecto):
    try:
        v = float(dxf.get(campo, defecto))
    except (TypeError, ValueError):
        return defecto
    return v if math.isfinite(v) else defecto


def papel_en_pulgadas(layout) -> bool:
    return int(_num(layout.dxf, "plot_paper_units", 1)) == 0


def mm_por_unidad(layout) -> float:
    """Milímetros de papel por unidad de la hoja, como la dibuja IngeCAD:
    0.7.0 en adelante lo sabe solo (paper_mm_per_unit); antes, la hoja la
    escala el módulo Papel (unidades_por_mm)."""
    try:
        from core import layouts
        propia = getattr(layouts, "paper_mm_per_unit", None)
    except Exception:  # noqa: BLE001
        propia = None
    if propia is not None:
        try:
            return float(propia(layout))
        except Exception:  # noqa: BLE001
            return 1.0
    from . import papel
    k = papel.unidades_por_mm(layout)
    return 1.0 / k if k > 0 else 1.0


def _cerca(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))


def en_mm(layout) -> bool:
    """La hoja está en milímetros: papel en mm y 1 mm = 1 o 0,001 unidades."""
    if layout is None or papel_en_pulgadas(layout):
        return False
    mm = mm_por_unidad(layout)
    return _cerca(mm, 1.0) or _cerca(mm, 1000.0)


def mm_destino(document) -> float | None:
    """A qué escala pasar la hoja: dibujo en metros -> 1 mm = 0,001 (1000 mm
    por unidad); en mm -> 1. Otras unidades o sin declarar: None (se pregunta)."""
    try:
        insunits = int(document.doc.header.get("$INSUNITS", 0))
    except Exception:  # noqa: BLE001
        return None
    return _MM_DESTINO.get(insunits)


def campos_mm(layout, mm_nuevo: float, factor: float) -> dict:
    """Los campos de la configuración de página con la hoja en mm. El tamaño
    del papel y los márgenes ya se guardan siempre en mm: no cambian."""
    try:
        flags = int(layout.dxf.get("plot_layout_flags", 0) or 0)
    except (TypeError, ValueError):
        flags = 0
    campos = {
        "plot_paper_units": 1,
        "scale_numerator": 1.0,
        "scale_denominator": 1.0 / mm_nuevo,
        "standard_scale_type": 16,
        "plot_layout_flags": flags & ~_BIT_ESCALA_ESTANDAR,
    }
    for nombre in ("limmin", "limmax"):
        try:
            v = layout.dxf.get(nombre, None)
        except Exception:  # noqa: BLE001
            v = None
        if v is not None:
            campos[nombre] = (float(v[0]) * factor, float(v[1]) * factor)
    return campos


def objetos_de_la_hoja(layout) -> list:
    """Lo dibujado en la hoja, sin la ventana propia del espacio papel (id 1)."""
    objetos = []
    for e in layout:
        if e.dxftype() == "VIEWPORT":
            try:
                if int(e.dxf.get("id", 0)) == 1:
                    continue
            except (TypeError, ValueError):
                pass
        objetos.append(e)
    return objetos


def comando_a_mm(layout, mm_nuevo: float):
    """Un solo paso de deshacer: la configuración de página en mm y lo de la
    hoja escalado desde (0, 0), el origen del papel, para que quede igual
    impreso (una ventana gráfica conserva su vista: su escala impresa
    también). Devuelve (comando, factor, objetos)."""
    from core.commands import CompositeCommand
    from core.layouts import PageSetupCommand

    mm_viejo = mm_por_unidad(layout)
    factor = mm_viejo / mm_nuevo
    pasos = [PageSetupCommand(layout, campos_mm(layout, mm_nuevo, factor))]
    objetos = objetos_de_la_hoja(layout)
    if objetos and not _cerca(factor, 1.0):
        from core.actions import TransformCommand
        from ezdxf.math import Matrix44
        pasos.append(TransformCommand("SCALE", objetos, Matrix44.scale(factor, factor, factor)))
    comando = CompositeCommand("GRILLAHOJA", pasos)
    return comando, factor, objetos


# ---------------------------------------------------------------- las líneas
def pasos_visibles(px_por_mm: float) -> tuple:
    return tuple(p for p in PASOS_MM if p * px_por_mm >= MIN_PX)


def nivel_de(mm: int) -> int:
    """0 la línea de 1 mm, 1 la de 5, 2 la de 10."""
    if mm % 10 == 0:
        return 2
    if mm % 5 == 0:
        return 1
    return 0


def _indices(a0, a1, v0, v1, paso_u):
    """Índices de las líneas de un eje que caen en la vista (y en la hoja).
    Sin las que caen sobre el borde de la hoja: ahí ya está el borde de
    IngeCAD y la grilla lo aclaraba."""
    c0, c1 = max(a0, v0), min(a1, v1)
    if c0 > c1:
        return None
    i0 = max(1, int(math.ceil((c0 - a0) / paso_u - 1e-9)))
    i1 = min(int(math.ceil((a1 - a0) / paso_u - 1e-6)) - 1,
             int(math.floor((c1 - a0) / paso_u + 1e-9)))
    return (i0, i1) if i0 <= i1 else None


def lineas(hoja, mm_u: float, vista, px_por_unidad: float):
    """Las líneas de la grilla que se ven: (paso_mm, segmentos) con cada
    segmento (x0, y0, x1, y1, nivel) en unidades de la hoja, a lo largo de
    toda la hoja (así no se rehace al desplazar dentro de las mismas celdas).
    ``hoja`` y ``vista``: (x0, y0, x1, y1); ``mm_u``: mm de papel por unidad.
    Sin nada que dibujar: (None, [])."""
    if not (mm_u > 0 and px_por_unidad > 0):
        return None, []
    hx0, hy0, hx1, hy1 = hoja
    pasos = pasos_visibles(px_por_unidad / mm_u)        # píxeles por mm de papel
    if not pasos:
        return None, []
    paso = pasos[0]
    paso_u = paso / mm_u
    vx0, vy0, vx1, vy1 = vista
    # las puntas no tocan el borde de la hoja (lo aclaraban): 2 px adentro
    m = min(2.0 / px_por_unidad, paso_u * 0.25)
    segs = []
    ix = _indices(hx0, hx1, vx0, vx1, paso_u)
    iy = _indices(hy0, hy1, vy0, vy1, paso_u)
    if ix is None or iy is None:
        return paso, []
    for i in range(ix[0], ix[1] + 1):
        x = hx0 + i * paso_u
        segs.append((x, hy0 + m, x, hy1 - m, nivel_de(i * paso)))
    for j in range(iy[0], iy[1] + 1):
        y = hy0 + j * paso_u
        segs.append((hx0 + m, y, hx1 - m, y, nivel_de(j * paso)))
    # de la más suave a la más fuerte: en los cruces gana la de 10 mm
    segs.sort(key=lambda s: s[4])
    return paso, segs


# ---------------------------------------------------------------- el lienzo
def _layout_de(window):
    """La presentación activa de la ventana, o None en Model."""
    try:
        nombre = getattr(window, "_active_layout", "Model")
        if nombre in (None, "", "Model"):
            return None
        return window.document.doc.layouts.get(nombre)
    except Exception:  # noqa: BLE001
        return None


def _a_dibujar(vp):
    """(hoja, mm por unidad) si la grilla de hoja va en este cuadro; si no, None."""
    if not (prendida() and activo()):
        return None
    scene = getattr(vp, "_scene", None)
    paper = getattr(scene, "paper", None) if scene is not None else None
    if not paper or paper.get("sheet") is None:
        return None
    try:
        window = vp.window()
    except Exception:  # noqa: BLE001
        return None
    layout = _layout_de(window)
    if layout is None or papel_en_pulgadas(layout):
        return None
    # 3.85.3: la escala de la hoja COMO SE VE (la de la escena), no la de la
    # configuración de página. En una presentación nueva de un dibujo en
    # metros la página dice 1 mm = 0,001 pero la hoja todavía se ve en mm
    # (Fernando, 19/11/2026: «no se activa»): con la de la página, las
    # líneas quedaban a 0,001 en una hoja de 420 y la grilla se apagaba.
    mm_u = mm_de_la_escena(paper)
    if mm_u is None:
        mm_u = mm_por_unidad(layout)
    if not (_cerca(mm_u, 1.0) or _cerca(mm_u, 1000.0)):
        return None
    return tuple(float(c) for c in paper["sheet"]), mm_u


def mm_de_la_escena(paper) -> float | None:
    """Milímetros de papel por unidad de la hoja que IngeCAD dibujó
    (paper_frame de 0.7.0 en adelante), o None si no lo dice."""
    try:
        v = float(paper.get("mm_per_unit"))
    except (TypeError, ValueError, AttributeError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _envolver_paint(original):
    def paintGL(self, *args, **kwargs):  # noqa: N802
        try:
            datos = _a_dibujar(self)
        except Exception:  # noqa: BLE001 -- ante la duda, IngeCAD como venía
            datos = None
        if datos is None:
            return original(self, *args, **kwargs)
        real = self.grid_on
        self._geocad_grilla_hoja = (datos, real)
        self.grid_on = True
        try:
            return original(self, *args, **kwargs)
        finally:
            self.grid_on = real
            self._geocad_grilla_hoja = None
    paintGL._puente_original = original
    paintGL._puente_fabrica = _envolver_paint
    return paintGL


def _envolver_draw_grid(original):
    def _draw_grid(self, gl, *args, **kwargs):
        pedido = getattr(self, "_geocad_grilla_hoja", None)
        if pedido is None:
            return original(self, gl, *args, **kwargs)
        datos, real = pedido
        try:
            dibujar(self, gl, *datos)
        except Exception:  # noqa: BLE001 -- la grilla de hoja nunca rompe el pintado
            pass
        if real:
            return original(self, gl, *args, **kwargs)
        return None
    _draw_grid._puente_original = original
    _draw_grid._puente_fabrica = _envolver_draw_grid
    return _draw_grid


#: El color de la hoja de IngeCAD (blanca), si el lienzo no dice otro.
HOJA = (255, 255, 255)


def color_sobre_hoja(alfa: int, hoja=HOJA) -> tuple:
    """El celeste con esa opacidad, ya mezclado con el color de la hoja, y
    opaco. Una línea semitransparente bajaba también la opacidad del lienzo
    de IngeCAD (su imagen se compone con la ventana) y en pantalla se veía
    lo de atrás en vez del celeste (banco, 19/11/2026). La grilla va siempre
    sobre la hoja y debajo del dibujo: mezclarla antes da lo mismo."""
    a = max(0, min(255, int(alfa))) / 255.0
    return tuple(int(round(h * (1.0 - a) + c * a)) for c, h in zip(CELESTE, hoja)) + (255,)


def trazos(segs, alfa, px_por_unidad: float, dpr: float = 1.0) -> list:
    """Cada línea con su grosor (GROSOR, en píxeles de pantalla; ``dpr``
    píxeles físicos por cada uno) hecha de líneas de 1 píxel físico, una al
    lado de la otra: (x0, y0, x1, y1, opacidad). Las enteras con toda la
    opacidad y la fracción que sobra con la parte proporcional (menos de
    1 píxel físico: una sola, más suave)."""
    d = 1.0 / (px_por_unidad * dpr)          # 1 píxel físico, en unidades
    salida = []
    for x0, y0, x1, y1, nivel in segs:
        a = alfa[nivel]
        w = GROSOR[nivel] * dpr
        enteras = int(math.floor(w + 1e-9))
        partes = [a] * enteras
        resto = w - enteras
        if resto > 1e-9:
            partes.append(int(round(a * resto)))
        for k, op in enumerate(partes):
            if x0 == x1:
                salida.append((x0 + k * d, y0, x1 + k * d, y1, op))
            else:
                salida.append((x0, y0 + k * d, x1, y1 + k * d, op))
    return salida


def _dpr(vp) -> float:
    try:
        v = float(vp.devicePixelRatioF())
        return v if v > 0 else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def vertices(trazos_, origen, dtype, hoja=HOJA):
    """Los trazos en el formato de vértices de IngeCAD, relativos a
    ``origen`` (float32 chico aunque la hoja esté lejos)."""
    import numpy as np

    ox, oy = origen
    datos = np.zeros(2 * len(trazos_), dtype=dtype)
    colores = {}
    for k, (x0, y0, x1, y1, a) in enumerate(trazos_):
        color = colores.get(a)
        if color is None:
            color = colores[a] = color_sobre_hoja(a, hoja)
        datos["pos"][2 * k] = (x0 - ox, y0 - oy)
        datos["pos"][2 * k + 1] = (x1 - ox, y1 - oy)
        datos["rgba"][2 * k] = datos["rgba"][2 * k + 1] = color
    return datos


def dibujar(vp, gl, hoja, mm_u) -> None:
    """La grilla de hoja en el lienzo: un VBO chico, rehecho sólo cuando
    cambian las celdas a la vista, el paso o la intensidad."""
    vista = vp._view_world_rect()
    paso, segs = lineas(hoja, mm_u, vista, float(vp.view.scale))
    if not segs:
        return
    alfa = alfas()
    zoom = round(math.log2(float(vp.view.scale)) * 8)      # el margen y el grosor en px
    dpr = _dpr(vp)
    clave = (hoja, mm_u, paso, len(segs), segs[0][:2], segs[-1][:2], alfa, zoom, dpr)
    buf = getattr(vp, "_geocad_grilla_buf", None)
    if buf is None or buf[3] != clave:
        if buf is not None:
            buf[0].destroy()
            buf[1].destroy()
        mod = import_module(type(vp).__module__)
        origen = (hoja[0], hoja[1])
        papel = getattr(mod, "PAPER_SHEET_RGBA", None)
        hoja_rgb = tuple(int(c) for c in papel[:3]) if papel is not None else HOJA
        trz = trazos(segs, alfa, float(vp.view.scale), dpr)
        vao, vbo, cuenta = vp._make_vao(vertices(trz, origen, mod.VERTEX_DTYPE, hoja_rgb))
        buf = (vao, vbo, cuenta, clave, origen)
        vp._geocad_grilla_buf = buf
    else:
        mod = import_module(type(vp).__module__)
    vao, _vbo, cuenta, _clave, origen = buf
    vp._program.bind()                      # _make_vao lo suelta
    vp._program.setUniformValue(vp._loc_mvp, vp._mvp(*origen))
    vao.bind()
    gl.glDrawArrays(getattr(mod, "GL_LINES", 0x0001), 0, cuenta)
    vao.release()


def instalar() -> None:
    """Envuelve el pintado del lienzo de IngeCAD (una sola vez). Los
    envoltorios miran el módulo y el botón en cada cuadro."""
    from .dibujo import envolver
    try:
        viewport = import_module("views.viewport")
        Viewport = viewport.Viewport
    except Exception:  # noqa: BLE001 -- sin Qt (pruebas) o sin lienzo
        return
    if not (hasattr(Viewport, "paintGL") and hasattr(Viewport, "_draw_grid")):
        return
    for nombre, fabrica in (("paintGL", _envolver_paint), ("_draw_grid", _envolver_draw_grid)):
        if getattr(getattr(Viewport, nombre), "_puente_fabrica", None) is not fabrica:
            envolver(Viewport, nombre, fabrica, reemplazar=True)
    if _al_guardar not in config.AL_GUARDAR:
        config.AL_GUARDAR.append(_al_guardar)


# ---------------------------------------------------------------- prender y apagar
def _pedir_escala(window):
    """Dibujo sin unidades conocidas: ¿la hoja en 0,001 o en 1? (None = cancelar)."""
    try:
        from PySide6.QtWidgets import QMessageBox
    except Exception:  # noqa: BLE001
        return None
    caja = QMessageBox(window)
    caja.setWindowTitle("Grilla de hoja")
    caja.setText("La hoja no está en milímetros y el dibujo no dice en qué unidades está.\n"
                 "¿En qué unidades está dibujado el modelo?")
    metros = caja.addButton("Metros (1 mm = 0,001)", QMessageBox.AcceptRole)
    milimetros = caja.addButton("Milímetros (1 mm = 1)", QMessageBox.AcceptRole)
    caja.addButton("Cancelar", QMessageBox.RejectRole)
    caja.exec()
    if caja.clickedButton() is metros:
        return 1000.0
    if caja.clickedButton() is milimetros:
        return 1.0
    return None


def _confirmar(window, texto: str) -> bool:
    try:
        from PySide6.QtWidgets import QMessageBox
    except Exception:  # noqa: BLE001
        return True
    r = QMessageBox.question(window, "Grilla de hoja", texto,
                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    return r == QMessageBox.Yes


def _texto_escala(mm: float) -> str:
    return "1 mm = 0,001 unidades" if _cerca(mm, 1000.0) else "1 mm = 1 unidad"


def pasar_a_mm(window, layout, echo, preguntar=None, confirmar=None) -> bool:
    """La hoja a milímetros (un solo U). False si el usuario cancela."""
    preguntar = preguntar or _pedir_escala
    confirmar = confirmar or _confirmar
    mm = mm_destino(window.document)
    if mm is None:
        mm = preguntar(window)
        if mm is None:
            echo("Grilla de hoja: cancelado, la hoja queda como estaba.")
            return False
    comando, factor, objetos = comando_a_mm(layout, mm)
    if objetos and not _cerca(factor, 1.0):
        texto = (f"La hoja no está en milímetros. Se pasa a «{_texto_escala(mm)}» y "
                 f"{len(objetos)} objeto(s) de la hoja se escalan para que queden "
                 "iguales en el papel.\nSe deshace con U. ¿Seguir?")
        if not confirmar(window, texto):
            echo("Grilla de hoja: cancelado, la hoja queda como estaba.")
            return False
    tools = getattr(window, "tools", None)
    if tools is not None and hasattr(tools, "_execute_command"):
        tools._execute_command(comando)          # índice de selección al día
    else:
        window.history.execute(comando)
    try:
        window.regen_in_memory()
    except Exception:  # noqa: BLE001
        pass
    echo(f"Hoja en milímetros: «{_texto_escala(mm)}» (se deshace con U).")
    return True


def alternar(window, echo, preguntar=None, confirmar=None) -> bool:
    """GRILLAHOJA: prende o apaga la grilla de hoja. Al prender en una
    presentación que no está en mm, la pasa a mm. Devuelve si quedó prendida."""
    if prendida():
        guardar(prender=False)
        echo("Grilla de hoja apagada.")
    else:
        layout = _layout_de(window)
        if layout is not None and not en_mm(layout):
            if not pasar_a_mm(window, layout, echo, preguntar, confirmar):
                refrescar_boton(window)
                return False
        guardar(prender=True)
        if layout is None:
            echo("Grilla de hoja prendida: se ve en las presentaciones (no se imprime).")
        else:
            echo("Grilla de hoja prendida: cada 1, 5 y 10 mm de papel (no se imprime).")
    refrescar_boton(window)
    _repintar(window)
    return prendida()


def elegir_intensidad(window, nivel: str) -> None:
    guardar(nivel=nivel)
    refrescar_boton(window)
    _repintar(window)


def _repintar(window) -> None:
    vp = getattr(window, "viewport", None)
    if vp is not None:
        try:
            vp.update()
        except Exception:  # noqa: BLE001
            pass


def cmd_grillahoja(ctx, *args) -> None:
    """GRILLAHOJA (GEOSHEETGRID): grilla milimetrada de la hoja, no se imprime."""
    alternar(ctx.host, ctx.echo)


# ---------------------------------------------------------------- el botón
#: Botones puestos, por ventana (la ventana de IngeCAD es de Python).
_BOTON = "_geocad_grilla_hoja_boton"


def _icono():
    from pathlib import Path
    ruta = Path(__file__).parent / "iconos" / "grilla_hoja.png"
    try:
        from PySide6.QtGui import QIcon
        return QIcon(str(ruta)) if ruta.exists() else QIcon()
    except Exception:  # noqa: BLE001
        return None


def preparar_boton(window) -> None:
    """Con el módulo Papel prendido, el botón va en la barra Ventanas
    gráficas de IngeCAD, después del desplegable de escala; apagado, se saca."""
    try:
        from PySide6.QtWidgets import QToolBar
    except Exception:  # noqa: BLE001
        return
    try:
        barra = window.findChild(QToolBar, "viewports_toolbar")
    except Exception:  # noqa: BLE001
        return
    puesto = getattr(window, _BOTON, None)
    if not activo():
        if puesto is not None:
            try:
                barra_vieja, accion_widget = puesto[0], puesto[2]
                barra_vieja.removeAction(accion_widget)
                puesto[1].deleteLater()
            except Exception:  # noqa: BLE001
                pass
            setattr(window, _BOTON, None)
        return
    if barra is None or puesto is not None:
        refrescar_boton(window)
        return
    from PySide6.QtGui import QAction, QActionGroup
    from PySide6.QtWidgets import QMenu, QToolButton

    accion = QAction(_icono(), "Grilla de hoja (GRILLAHOJA)", window)
    accion.setCheckable(True)
    accion.setToolTip("Grilla de hoja: milimetrada, casi invisible, no se imprime (GRILLAHOJA).\n"
                      "Si la hoja no está en mm, la pasa a mm.")
    accion.triggered.connect(lambda _=False: alternar(window, window.command_line.echo))
    menu = QMenu(window)
    grupo = QActionGroup(menu)
    grupo.setExclusive(True)
    niveles = {}
    for clave, etiqueta in ETIQUETAS:
        a = menu.addAction(etiqueta)
        a.setCheckable(True)
        grupo.addAction(a)
        a.triggered.connect(lambda _=False, c=clave: elegir_intensidad(window, c))
        niveles[clave] = a
    boton = QToolButton(barra)
    boton.setDefaultAction(accion)
    boton.setMenu(menu)
    boton.setPopupMode(QToolButton.MenuButtonPopup)
    boton.setObjectName("geocad_grilla_hoja")
    accion_widget = barra.addWidget(boton)
    setattr(window, _BOTON, (barra, boton, accion_widget, accion, niveles, menu))
    refrescar_boton(window)


def refrescar_boton(window) -> None:
    puesto = getattr(window, _BOTON, None)
    if puesto is None:
        return
    try:
        accion, niveles = puesto[3], puesto[4]
        accion.setChecked(prendida())
        actual = intensidad()
        for clave, a in niveles.items():
            a.setChecked(clave == actual)
    except Exception:  # noqa: BLE001
        pass
