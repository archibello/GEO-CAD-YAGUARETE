# SPDX-License-Identifier: GPL-3.0-or-later
"""Vista previa y plumas como AutoCAD (módulo «Impresión», 3.7.0).

IngeCAD imprime con tablas de plumas .ctb (color -> color de impresión,
grosor, tramado, grises) que guarda en su carpeta PlotStyles, pero no traía
cómo editarlas ni cómo ver el resultado antes de imprimir. GeoCAD suma:

1. PLUMAS (GEOPLOTSTYLES): editor de la tabla de plumas como el de AutoCAD
   (STYLESMANAGER). Una pluma por color de AutoCAD (ACI): 1 Rojo,
   2 Amarillo, 3 Verde, 4 Cian, 5 Azul, 6 Magenta, 7 Blanco/Negro, 8 a 255
   por número. Guarda .ctb compatibles con AutoCAD (con respaldo .bak).
2. VISTAPREVIA (GEOPREVIEW): la presentación tal como sale impresa (hoja,
   escala de cada ventana, plumas), con zoom; Imprimir... / Cerrar.
3. En Page Setup, junto a «Plot style table», los botones Editar... y
   Vista previa... (la vista previa usa lo elegido en la ventana, todavía
   sin aplicar).

Este archivo tiene las cuentas, sin Qt (se prueban solas); las ventanas
están en impresion_ui.py.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import modulos

PROGRAMA = "ingecad"

#: Nombres de los colores de AutoCAD 1 a 7 (los demás van por número).
NOMBRES_ACI = {1: "Rojo", 2: "Amarillo", 3: "Verde", 4: "Cian", 5: "Azul",
               6: "Magenta", 7: "Blanco/Negro"}

#: Grosores de AutoCAD en mm (0 = «usar el grosor del objeto»).
GROSORES = (0.0, 0.05, 0.09, 0.10, 0.13, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35,
            0.40, 0.45, 0.50, 0.53, 0.60, 0.65, 0.70, 0.80, 0.90, 1.00, 1.06,
            1.20, 1.40, 1.58, 2.00, 2.11)

#: Valor que no cambia una propiedad en :func:`cambiar`.
IGUAL = object()


def activo() -> bool:
    return modulos.activo(PROGRAMA, "impresion")


def nombre_color(aci: int) -> str:
    """«1 · Rojo», «8 · Color 8»: como la lista de plumas de AutoCAD."""
    return f"{aci} · {NOMBRES_ACI.get(aci, f'Color {aci}')}"


def carpeta() -> Path:
    from core import plotstyles
    return plotstyles.ensure_builtin()


def leer(ruta) -> "object":
    """La tabla .ctb de ``ruta`` (ezdxf), lista para editar."""
    from ezdxf.addons import acadctb

    ruta = Path(ruta)
    if ruta.suffix.lower() != ".ctb":
        raise ValueError("Sólo se editan tablas por color (.ctb); "
                         "las tablas con nombre (.stb) todavía no.")
    return acadctb.load(str(ruta))


def nueva() -> "object":
    """Tabla nueva: todas las plumas con el color y el grosor del objeto."""
    from ezdxf.addons import acadctb

    tabla = acadctb.new_ctb()
    tabla.description = "GeoCAD"
    return tabla


def pluma(tabla, aci: int) -> dict:
    """Lo que la tabla dice del color ``aci``."""
    estilo = tabla[aci]
    return {
        "color": None if estilo.has_object_color() else tuple(estilo.color),
        "grises": bool(estilo.grayscale),
        "tramado": int(estilo.screen),
        "grosor": round(float(estilo.get_lineweight()), 3),
        "descripcion": str(estilo.description or ""),
    }


def indice_grosor(tabla, mm: float) -> int:
    """El índice del grosor ``mm`` en la tabla (los de la tabla son float32:
    0,13 no es exactamente 0.13); si no está, se agrega."""
    for i, valor in enumerate(tabla.lineweights):
        if abs(float(valor) - mm) < 1e-4:
            return i
    tabla.lineweights.append(mm)
    return len(tabla.lineweights) - 1


def cambiar(tabla, acis, *, color=IGUAL, grises=IGUAL, tramado=IGUAL,
            grosor=IGUAL, descripcion=IGUAL) -> int:
    """Cambia las plumas ``acis`` (varias a la vez, como en AutoCAD).

    ``color``: None = usar el color del objeto, o (r, g, b).
    ``grosor``: mm; 0 = usar el grosor del objeto. ``tramado``: 0 a 100.
    Devuelve cuántas plumas cambió.
    """
    n = 0
    for aci in acis:
        if not 1 <= int(aci) <= 255:
            continue
        estilo = tabla[int(aci)]
        if color is not IGUAL:
            if color is None:
                estilo.set_object_color()
            else:
                estilo.color = tuple(int(c) for c in color)
        if grises is not IGUAL:
            estilo.grayscale = bool(grises)
        if tramado is not IGUAL:
            estilo.screen = max(0, min(100, int(tramado)))
        if grosor is not IGUAL:
            estilo.lineweight = indice_grosor(tabla, float(grosor))
        if descripcion is not IGUAL:
            estilo.description = str(descripcion)
        n += 1
    return n


def nombre_archivo(nombre: str) -> str:
    """El nombre de archivo de una tabla nueva: sin carpetas y con .ctb."""
    nombre = os.path.basename(str(nombre).strip()).strip()
    if not nombre or nombre in (".", ".."):
        raise ValueError("Falta el nombre de la tabla.")
    if not nombre.lower().endswith(".ctb"):
        nombre += ".ctb"
    return nombre


def guardar(tabla, ruta) -> Path | None:
    """Guarda la tabla en ``ruta`` sin arriesgar la que había: la anterior
    queda como <nombre>.ctb.bak y el archivo nuevo se escribe aparte y se
    cambia de una vez. Devuelve el respaldo (o None si no había archivo)."""
    from core import plotstyles

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    respaldo = None
    if ruta.exists():
        respaldo = ruta.with_name(ruta.name + ".bak")
        shutil.copy2(ruta, respaldo)
    temporal = ruta.with_name(ruta.stem + ".geocad-tmp.ctb")
    from ezdxf.addons import acadctb
    try:
        plotstyles._save(tabla, temporal)
        acadctb.load(str(temporal))    # que se pueda volver a abrir
        os.replace(temporal, ruta)
    finally:
        if temporal.exists():
            temporal.unlink()
    return respaldo


# ---------------------------------------------------------------- página sin aplicar
def foto_pagina(layout) -> dict:
    """Los datos de página de la presentación, para volver atrás exacto."""
    return dict(layout.dxf.all_existing_dxf_attribs())


def restaurar_pagina(layout, foto: dict) -> None:
    actual = dict(layout.dxf.all_existing_dxf_attribs())
    for clave in actual:
        if clave not in foto:
            layout.dxf.discard(clave)
    for clave, valor in foto.items():
        if actual.get(clave) != valor:
            layout.dxf.set(clave, valor)


def con_pagina_provisoria(document, layout, comando, hacer):
    """Aplica ``comando`` (un PageSetupCommand), llama a ``hacer()`` y deja la
    presentación y la marca de «modificado» exactamente como estaban."""
    foto = foto_pagina(layout)
    sucio = getattr(document, "dirty", False)
    try:
        comando.do(document)
        return hacer()
    finally:
        restaurar_pagina(layout, foto)
        document.dirty = sucio


# ---------------------------------------------------------------- órdenes y Page Setup
def cmd_vistaprevia(ctx, *args) -> None:
    """VISTAPREVIA (GEOPREVIEW): la presentación como sale impresa."""
    from . import impresion_ui
    impresion_ui.vista_previa(ctx.host, ctx.echo)


def cmd_plumas(ctx, *args) -> None:
    """PLUMAS (GEOPLOTSTYLES): editor de la tabla de plumas .ctb."""
    from . import impresion_ui
    impresion_ui.plumas(ctx.host, ctx.echo)


def instalar() -> None:
    """Botones Editar plumas... y Vista previa... en Page Setup. El envoltorio
    mira ``activo()`` al abrir la ventana: apagado, Page Setup queda como venía."""
    try:
        from views.page_setup_dialog import PageSetupDialog   # usa Qt
        from . import impresion_ui
    except Exception:  # noqa: BLE001
        return
    from .dibujo import envolver
    actual = getattr(PageSetupDialog.__init__, "_puente_fabrica", None)
    if actual is not impresion_ui._envolver_init:
        envolver(PageSetupDialog, "__init__", impresion_ui._envolver_init, reemplazar=True)
