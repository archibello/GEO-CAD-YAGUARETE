# SPDX-License-Identifier: GPL-3.0-or-later
"""GeoCAD para IngeCAD: GIS to CAD y CAD to GIS, en ida y vuelta con QGIS.

Un solo plugin con un solo menú («GeoCAD»). Adentro, módulos que se eligen
al instalar y se cambian en GeoCAD > Módulos... (ver modulos.py):

    Puente     conectar capas GPKG/SHP que manda QGIS y devolverlas con
               respaldo, validación y control de conflictos
    Datos      tabla de atributos, consultas, temático, rótulos, formulario
    Botón derecho = Enter / Ángulos relativos   (dibujo.py)
    Empalme (empalme.py) / Chaflán (chaflan.py) / Partir en punto (partir.py)

Un módulo apagado no deja rastro: ni menú, ni barra, ni comandos, ni
cambios en el comportamiento de IngeCAD. El menú se rearma solo al
cambiar la elección (sin reiniciar).
"""
from __future__ import annotations

from pathlib import Path

from core.plugins import SEPARATOR, MenuItem, PluginSpec, Submenu, ToolbarItem

from . import actualizacion, buzon, config, dibujo, modulos, nombre, ventanas
from . import barra, bloques, cotas, editor_texto, filtro, impresion, papel, propiedades, seleccion, tipografias
from .chaflan import ChaflanTool
from .empalme import EmpalmeTool
from .partir import PartirTool
from .herramientas_datos import DATA_TOOLS
from .tools import TOOL_CLASSES

PLUGIN_ID = "geocad"
PROGRAMA = "ingecad"
VERSION = "3.11.2"
ICONS = Path(__file__).parent / "iconos"


def _icon(name: str):
    path = ICONS / f"{name}.png"
    return path if path.exists() else None


def _qgis_icon():
    """El ícono de QGIS (lo publica el complemento de QGIS al abrirse) o una flecha."""
    path = buzon.icon_path("qgis")
    return path if path.exists() else _icon("devolver")


def _options_page(dialog, window):
    """Pestaña en Herramientas > Opciones: la misma configuración común."""
    from .opciones import SharedOptionsPage

    return SharedOptionsPage(dialog, window)


def _document_open(ctx, document):
    """Al crear o abrir un dibujo: el puente con QGIS empieza a escuchar
    (si el módulo está activo)."""
    from . import puente

    dibujo.instalar()
    seleccion.instalar()
    propiedades.instalar()
    editor_texto.instalar()
    tipografias.instalar()
    papel.instalar()
    impresion.instalar()
    cotas.instalar()
    bloques.instalar_referencias()
    barra.instalar()
    seleccion.aplicar_autocompletar(ctx.host)
    papel.preparar_combo(ctx.host)
    if modulos.activo(PROGRAMA, "puente"):
        puente.ensure_started(ctx.host)
    if not modulos.elegido(PROGRAMA) or modulos.nuevos(PROGRAMA):
        # instalado desde la Consola: la primera vez que se abre, se eligen los módulos
        try:
            from PySide6.QtCore import QTimer
            from . import ventanas
            QTimer.singleShot(0, lambda: ventanas.primera_eleccion(
                ctx.host, getattr(ctx, "echo", print)))
        except ImportError:
            pass


# -- comandos de GeoCAD (siempre presentes) --------------------------------------------
def cmd_modulos(ctx, *args) -> None:
    """GEOCADMODULES: elegir los módulos (ventana; sin ventana, por texto)."""
    from . import ventanas

    ventanas.elegir_modulos(ctx.host, ctx.echo)


def cmd_acerca(ctx, *args) -> None:
    """GEOCADABOUT: «Acerca de...»: versión, módulos activos, autor, licencia y enlaces."""
    resumen = modulos.resumen(PROGRAMA)
    for linea in nombre.texto_acerca(PROGRAMA, VERSION, resumen).split("\n"):
        ctx.echo(linea)
    ctx.echo("Configuración común: " + str(config.config_path()))
    QtWidgets = ventanas._qtwidgets()
    window = getattr(ctx, "host", None)
    if QtWidgets is not None and window is not None:
        nombre.mostrar_acerca(QtWidgets, window, PROGRAMA, VERSION, resumen)


def construir_spec() -> PluginSpec:
    """El plugin tal como lo piden los módulos activos en este momento."""
    est = modulos.estado(PROGRAMA)
    tools, menu, toolbar, aliases = {}, [], [], {}
    commands = {
        **dibujo.COMMANDS,
        "QGISUPDATE": actualizacion.cmd_actualizar,
        "GEOCADMODULES": cmd_modulos,
        "GEOCADABOUT": cmd_acerca,
    }
    tools["SHPCONFIG"] = TOOL_CLASSES["SHPCONFIG"]
    if est["empalme"]:
        tools["GEOFILLET"] = EmpalmeTool
    if est["chaflan"]:
        tools["GEOCHAMFER"] = ChaflanTool
    if est["partir"]:
        tools["BREAKATPOINT"] = PartirTool
    if est["bloques"]:
        tools.update({"GEOBLOCK": bloques.BloqueTool, "GEOINSERT": bloques.InsertarTool,
                      "GEOREFEDIT": bloques.EditarEnSitioTool, "GEOBLOCKBASE": bloques.PuntoBaseTool,
                      "GEOREFADD": bloques.AgregarTool, "GEOREFREMOVE": bloques.QuitarTool})
        commands.update({"GEOREFSAVE": bloques.cmd_guardar, "GEOREFDISCARD": bloques.cmd_descartar})
    if est["seleccion"] and seleccion.SelTool is not None:
        tools["SELECT"] = seleccion.SelTool
        aliases["SEL"] = "SELECT"           # en español la orden se llama SELECCIONA
    if est["seleccion"] and filtro.FiltroTool is not None:
        tools["GEOFILTER"] = filtro.FiltroTool  # en español FILTRO
        aliases.update({"FI": "GEOFILTER", "FILTER": "GEOFILTER"})
    # la barra GeoCAD: el orden por temas lo pone barra.ordenar()
    if est["empalme"]:
        toolbar.append(ToolbarItem("AutoCAD-style fillet (FILLET)", "FILLET"))
    if est["chaflan"]:
        toolbar.append(ToolbarItem("AutoCAD-style chamfer (CHAMFER)", "CHAMFER"))
    if est["partir"]:
        toolbar.append(ToolbarItem("Break at point (BREAKATPOINT)", "BREAKATPOINT", _icon("partir")))
    if est["bloques"]:
        toolbar.append(ToolbarItem("Create block (BLOCK)", "BLOCK"))
        toolbar.append(ToolbarItem("Insert block (INSERT)", "INSERT"))
        toolbar.append(ToolbarItem("Edit block in place (double-click)", "GEOREFEDIT", _icon("editar_bloque")))
        toolbar.append(ToolbarItem("Change block base point", "GEOBLOCKBASE", _icon("punto_base")))
    if est["seleccion"] and "SELECT" in tools:
        toolbar.append(ToolbarItem("Select objects (SEL)", "SELECT", _icon("seleccionar")))
    if est["seleccion"] and "GEOFILTER" in tools:
        toolbar.append(ToolbarItem("Selection filters (FILTER)", "GEOFILTER", _icon("filtro")))
    if est["impresion"]:
        commands.update({"GEOPREVIEW": impresion.cmd_vistaprevia,
                         "GEOPLOTSTYLES": impresion.cmd_plumas})
        toolbar.append(ToolbarItem("Print preview (PREVIEW)", "GEOPREVIEW", _icon("vista_previa")))
        toolbar.append(ToolbarItem("Plot style table editor (pens)", "GEOPLOTSTYLES", _icon("plumas")))
    if est["cotas"]:
        commands["GEODIMSETUP"] = cotas.cmd_crear
        toolbar += [
            ToolbarItem("Create dimension style (DIMSETUP)", "GEODIMSETUP", _icon("crear_cota")),
            ToolbarItem("Linear dimension (DIMLINEAR)", "DIMLINEAR", _icon("cota_lineal")),
            ToolbarItem("Aligned dimension (DIMALIGNED)", "DIMALIGNED", _icon("cota_alineada")),
            ToolbarItem("Angular dimension (DIMANGULAR)", "DIMANGULAR", _icon("cota_angular")),
        ]
    if est["puente"]:
        tools.update({k: v for k, v in TOOL_CLASSES.items()
                      if k != "SHPCONFIG" and k not in DATA_TOOLS})
        menu += [
            MenuItem("Send everything back to QGIS", "QGISSAVE", _qgis_icon()),
            MenuItem("Send selection back to QGIS", "QGISSAVESEL", _icon("devolver_seleccion")),
            SEPARATOR,
        ]
    if est["datos"]:
        tools.update(DATA_TOOLS)
        menu += [
            Submenu("Data", (
                MenuItem("Attribute table", "SHPTABLE", _icon("tabla")),
                MenuItem("Query by attributes...", "SHPQUERY", _icon("consulta")),
                MenuItem("Query by location...", "SHPSPATIAL", _icon("ubicacion")),
                SEPARATOR,
                MenuItem("Thematic map...", "SHPTHEME", _icon("tematico")),
                MenuItem("Remove thematic map", "SHPTHEMEOFF"),
                MenuItem("Labels from a field...", "SHPLABEL", _icon("rotulos")),
                MenuItem("Remove labels", "SHPLABELOFF"),
                SEPARATOR,
                MenuItem("New feature with form...", "SHPNEW", _icon("nuevo")),
                MenuItem("Feature attributes", "SHPINFO"),
                MenuItem("Edit attribute...", "SHPATTR"),
            )),
        ]
        toolbar += [
            ToolbarItem("Attribute table", "SHPTABLE", _icon("tabla")),
            ToolbarItem("Query by attributes...", "SHPQUERY", _icon("consulta")),
            ToolbarItem("Query by location...", "SHPSPATIAL", _icon("ubicacion")),
            ToolbarItem("Thematic map...", "SHPTHEME", _icon("tematico")),
            ToolbarItem("Labels from a field...", "SHPLABEL", _icon("rotulos")),
            ToolbarItem("New feature with form...", "SHPNEW", _icon("nuevo")),
            ToolbarItem("Send selection back to QGIS", "QGISSAVESEL", _icon("devolver_seleccion")),
            ToolbarItem("Send everything back to QGIS", "QGISSAVE", _qgis_icon()),
        ]
    if est["puente"]:
        menu += [
            Submenu("Bridge", (
                MenuItem("Connect GIS data (GPKG / SHP)...", "SHPCONNECT"),
                MenuItem("Pending changes", "SHPSTATUS"),
                MenuItem("Save changes of one layer...", "SHPCHECKIN"),
                MenuItem("Disconnect GIS layer", "SHPRELEASE"),
            )),
        ]
    menu += [
        Submenu("Drawing", (
            MenuItem("Relative angles on/off (ANGREL)", "ANGREL"),
            MenuItem("Right button = Enter on/off", "RIGHTCLICK"),
            SEPARATOR,
        ) + ((MenuItem("AutoCAD-style fillet (FILLET)", "FILLET"),) if est["empalme"] else ())
          + ((MenuItem("AutoCAD-style chamfer (CHAMFER)", "CHAMFER"),) if est["chaflan"] else ())
          + ((MenuItem("Break at point (BREAKATPOINT)", "BREAKATPOINT", _icon("partir")),)
             if est["partir"] else ())
          + ((MenuItem("Select objects (SEL)", "SELECT", _icon("seleccionar")),)
             if est["seleccion"] and "SELECT" in tools else ())
          + ((MenuItem("Selection filters (FILTER)", "GEOFILTER", _icon("filtro")),)
             if est["seleccion"] and "GEOFILTER" in tools else ())),
        SEPARATOR,
    ]
    if est["bloques"]:
        menu += [
            Submenu("Blocks", (
                MenuItem("Create block (BLOCK)", "BLOCK"),
                MenuItem("Insert block (INSERT)", "INSERT"),
                MenuItem("Edit block in place (double-click)", "GEOREFEDIT", _icon("editar_bloque")),
                MenuItem("Change block base point", "GEOBLOCKBASE", _icon("punto_base")),
                SEPARATOR,
                MenuItem("Add objects to the block being edited", "GEOREFADD"),
                MenuItem("Leave objects out of the block being edited", "GEOREFREMOVE"),
                MenuItem("Save block edit", "GEOREFSAVE"),
                MenuItem("Discard block edit", "GEOREFDISCARD"),
            )),
            SEPARATOR,
        ]
    if est["impresion"]:
        menu += [
            Submenu("Printing", (
                MenuItem("Print preview (PREVIEW)", "GEOPREVIEW", _icon("vista_previa")),
                MenuItem("Plot style table editor (pens)", "GEOPLOTSTYLES", _icon("plumas")),
            )),
            SEPARATOR,
        ]
    if est["cotas"]:
        menu += [
            Submenu("Dimensions", (
                MenuItem("Create dimension style (DIMSETUP)", "GEODIMSETUP", _icon("crear_cota")),
                SEPARATOR,
                MenuItem("Linear dimension (DIMLINEAR)", "DIMLINEAR", _icon("cota_lineal")),
                MenuItem("Aligned dimension (DIMALIGNED)", "DIMALIGNED", _icon("cota_alineada")),
                MenuItem("Angular dimension (DIMANGULAR)", "DIMANGULAR", _icon("cota_angular")),
            )),
            SEPARATOR,
        ]
    menu += [
        MenuItem("Modules...", "GEOCADMODULES"),
        MenuItem("Shared settings...", "SHPCONFIG"),
        MenuItem("Update GeoCAD Yaguareté (IngeCAD and QGIS)...", "QGISUPDATE"),
        MenuItem("About GEO-CAD-YAGUARETÉ...", "GEOCADABOUT"),
    ]
    return PluginSpec(
        id=PLUGIN_ID,
        name="GeoCAD Yaguareté",
        version="3.11.2",
        description="GIS to CAD and CAD to GIS with QGIS: edit GeoPackage and shapefile layers with CAD tools, with backup and conflict checks. Modules are chosen at install time.",
        tools=tools,
        commands=commands,
        aliases=aliases,
        menu=tuple(menu),
        toolbar=tuple(barra.ordenar(toolbar)),
        options_page=_options_page,
        on_document_open=_document_open,
        i18n_dir=Path(__file__).parent / "i18n",
    )


def aplicar_modulos(window) -> None:
    """Después de cambiar la elección: el plugin se rearma (menú, barra,
    comandos) y el puente arranca o se apaga, sin reiniciar IngeCAD."""
    from . import puente

    mgr = getattr(window, "plugins", None)
    loaded = getattr(mgr, "loaded", {}).get(PLUGIN_ID) if mgr is not None else None
    nuevo = construir_spec()
    global PLUGIN
    PLUGIN = nuevo
    if loaded is not None:
        activo = mgr.is_active(PLUGIN_ID)
        if activo:
            mgr.deactivate(PLUGIN_ID)
        loaded.spec = nuevo
        if activo:
            mgr.activate(PLUGIN_ID)
    seleccion.aplicar_autocompletar(window)
    propiedades.refrescar(window)
    papel.preparar_combo(window)
    if modulos.activo(PROGRAMA, "puente"):
        puente.ensure_started(window)
    else:
        puente.shutdown()


config.migrar()
dibujo.instalar()
seleccion.instalar()
propiedades.instalar()
editor_texto.instalar()
tipografias.instalar()
papel.instalar()
impresion.instalar()
cotas.instalar()
bloques.instalar_referencias()
barra.instalar()
PLUGIN = construir_spec()
