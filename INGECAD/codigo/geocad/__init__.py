# SPDX-License-Identifier: GPL-3.0-or-later
"""GeoCAD para IngeCAD: GIS to CAD y CAD to GIS, en ida y vuelta con QGIS.

Un solo plugin con un solo menú («GeoCAD»). Adentro, módulos que se eligen
al instalar y se cambian en GeoCAD > Módulos... (ver modulos.py):

    Puente     conectar capas GPKG/SHP que manda QGIS y devolverlas con
               respaldo, validación y control de conflictos
    Datos      tabla de atributos, consultas, temático, rótulos, formulario
    Botón derecho = Enter / Ángulos relativos   (dibujo.py)
    Empalme (empalme.py) / Chaflán (chaflan.py) / Partir en punto (partir.py)
    Igualar propiedades (igualar.py): MATCHPROP con el origen resaltado
    Ajustar imagen (georref.py): GEORREF / RUBBERSHEET con puntos de control
    Imágenes geo (imagengeo.py): INSERTARGEO en su lugar, EXPORTARGEO copia geo
    Pegar imagen (pegarimagen.py): Ctrl+V o PEGARIMAGEN, la captura del portapapeles en dos clics
    Intercambio (intercambio.py): SISTEMAGEO, REPROYECTAR, IMPORTARSHP, EXPORTARSHP

Un módulo apagado no deja rastro: ni menú, ni barra, ni comandos, ni
cambios en el comportamiento de IngeCAD. El menú se rearma solo al
cambiar la elección (sin reiniciar).
"""
from __future__ import annotations

from pathlib import Path

from core.plugins import SEPARATOR, MenuItem, PluginSpec, Submenu, ToolbarItem

from . import actualizacion, buzon, config, dibujo, modulos, nombre, ventanas
from . import barra, bloques, capas, intercambio, legibles, pegarimagen, pegartabla, cotas, editor_texto, filtro, georref, igualar, imagengeo, impresion, orden, papel, propiedades, seleccion, texto, tipografias, uniones
from .chaflan import ChaflanTool
from .empalme import EmpalmeTool
from .estirar import EstirarTool
from .texto import TextoTool
from .partir import PartirTool
from .pegartabla import PegarTablaTool
from .herramientas_datos import DATA_TOOLS
from .tools import TOOL_CLASSES

PLUGIN_ID = "geocad"
PROGRAMA = "ingecad"
VERSION = "3.28.0"
ICONS = Path(__file__).parent / "iconos"


def _icon(name: str):
    path = ICONS / f"{name}.png"
    return path if path.exists() else None


def _qgis_icon():
    """El ícono de QGIS (lo publica el complemento de QGIS al abrirse) o una flecha."""
    path = buzon.icon_path("qgis")
    return path if path.exists() else _icon("devolver")


def _qgis_table_icon():
    """El ícono de Pegar tabla (3.24.1): una tablita que viene de QGIS. Lleva
    el ícono de QGIS que publica su complemento al abrirse; sin él, el dibujo
    de reserva."""
    base = _icon("pegar_qgis")
    logo = buzon.icon_path("qgis")
    if base is None or not logo.exists():
        return base
    destino = logo.parent / "pegar_qgis.png"
    try:
        if destino.exists() and destino.stat().st_mtime >= max(logo.stat().st_mtime,
                                                                base.stat().st_mtime):
            return destino
        from PIL import Image

        im = Image.open(base).convert("RGBA")
        im.paste((0, 0, 0, 0), (0, 0, 16, 14))
        im.alpha_composite(Image.open(logo).convert("RGBA").resize((14, 14), Image.LANCZOS), (0, 0))
        im.save(destino)
        return destino
    except Exception:  # noqa: BLE001 -- sin PIL o sin permiso: el dibujo de reserva
        return base


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
    texto.instalar()
    bloques.instalar_referencias()
    orden.instalar()
    uniones.instalar()
    barra.instalar()
    capas.instalar()
    legibles.instalar()
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
    if est["estirar"]:
        tools["GEOSTRETCH"] = EstirarTool
    if est["igualar"]:
        tools["GEOMATCHPROP"] = igualar.IgualarTool
    if est["texto"]:
        tools["GEOTEXT"] = TextoTool
    if est["tablas"]:
        tools["GEOPASTETABLE"] = PegarTablaTool
        aliases.update({"PASTETABLE": "GEOPASTETABLE", "PT": "GEOPASTETABLE",
                        "PASTEQGIS": "GEOPASTETABLE"})
    if est["georref"]:
        tools["GEORREF"] = georref.GeorrefTool
        tools["INSERTARGEO"] = imagengeo.InsertarGeoTool
        tools["EXPORTARGEO"] = imagengeo.ExportarGeoTool
        tools["GEOPASTEIMAGE"] = pegarimagen.PegarImagenTool
        aliases.update({"PASTEIMAGE": "GEOPASTEIMAGE", "PASTECLIP": "GEOPASTEIMAGE"})
        aliases.update({"RUBBERSHEET": "GEORREF", "AJUSTEIMAGEN": "GEORREF"})
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
    # Empalme, Chaflán, Partir en punto (y Estirar, Rectángulo) van en la
    # barra «Yaguareté Tools» (yaguarete.py), no en ésta
    if est["bloques"]:
        toolbar.append(ToolbarItem("Create block (BLOCK)", "BLOCK"))
        toolbar.append(ToolbarItem("Insert block (INSERT)", "INSERT"))
        toolbar.append(ToolbarItem("Edit block in place (double-click)", "GEOREFEDIT", _icon("editar_bloque")))
        toolbar.append(ToolbarItem("Change block base point", "GEOBLOCKBASE", _icon("punto_base")))
    if est["seleccion"] and "SELECT" in tools:
        toolbar.append(ToolbarItem("Select objects (SEL)", "SELECT", _icon("seleccionar")))
    if est["seleccion"] and "GEOFILTER" in tools:
        toolbar.append(ToolbarItem("Selection filters (FILTER)", "GEOFILTER", _icon("filtro")))
    if est["tablas"]:
        toolbar.append(ToolbarItem("Paste table (PASTETABLE)", "GEOPASTETABLE", _qgis_table_icon()))
    if est["georref"]:
        toolbar.append(ToolbarItem("Paste clipboard image (PASTEIMAGE)", "GEOPASTEIMAGE",
                                   _icon("pegar_imagen")))
    if est["intercambio"]:
        commands.update(intercambio.COMMANDS)
        aliases.update({"MAPCSASSIGN": "GEOCRS", "MAPIMPORT": "GEOIMPORTSHP",
                        "MAPEXPORT": "GEOEXPORTSHP"})
        toolbar += [
            ToolbarItem("Coordinate system of the drawing (GEOCRS)", "GEOCRS", _icon("sistema")),
            ToolbarItem("Reproject drawing (REPROJECT)", "GEOREPROJECT", _icon("reproyectar")),
            ToolbarItem("Import SHP (IMPORTSHP)", "GEOIMPORTSHP", _icon("importar_shp")),
            ToolbarItem("Export SHP (EXPORTSHP)", "GEOEXPORTSHP", _icon("exportar_shp")),
        ]
    if est["orden"]:
        commands.update(orden.COMMANDS)
        toolbar.append(ToolbarItem("Bring to front (DRAWORDER)", "GEODRAWFRONT", _icon("al_frente")))
        toolbar.append(ToolbarItem("Send to back (DRAWORDER)", "GEODRAWBACK", _icon("al_fondo")))
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
            MenuItem("Send selection to QGIS as new layers", "QGISEXPORT", _qgis_icon()),
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
            ToolbarItem("Send selection to QGIS as new layers", "QGISEXPORT", _qgis_icon()),
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
    if est["intercambio"]:
        menu += [
            Submenu("Coordinate system", (
                MenuItem("Define or redefine coordinate system... (GEOCRS)", "GEOCRS", _icon("sistema")),
                MenuItem("Reproject drawing... (REPROJECT)", "GEOREPROJECT", _icon("reproyectar")),
            )),
            Submenu("Import", (
                MenuItem("Import SHP... (IMPORTSHP)", "GEOIMPORTSHP", _icon("importar_shp")),
            )),
            Submenu("Export", (
                MenuItem("Export SHP... (EXPORTSHP)", "GEOEXPORTSHP", _icon("exportar_shp")),
            )),
            SEPARATOR,
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
          + ((MenuItem("Match properties (MATCHPROP)", "MATCHPROP"),) if est["igualar"] else ())
          + ((MenuItem("Adjust image with control points (GEORREF)", "GEORREF", _icon("georref")),
              MenuItem("Insert georeferenced image (INSERTARGEO)", "INSERTARGEO", _icon("insertar_geo")),
              MenuItem("Export georeferenced copy (EXPORTARGEO)", "EXPORTARGEO", _icon("exportar_geo")),
              MenuItem("Paste clipboard image (PASTEIMAGE)", "GEOPASTEIMAGE", _icon("pegar_imagen")))
             if est["georref"] else ())
          + ((MenuItem("Paste table (PASTETABLE)", "GEOPASTETABLE", _qgis_table_icon()),)
             if est["tablas"] else ())
          + ((MenuItem("Bring to front (DRAWORDER)", "GEODRAWFRONT", _icon("al_frente")),
              MenuItem("Send to back (DRAWORDER)", "GEODRAWBACK", _icon("al_fondo")))
             if est["orden"] else ())
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
        version="3.28.0",
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
texto.instalar()
bloques.instalar_referencias()
orden.instalar()
uniones.instalar()
pegartabla.instalar()
pegarimagen.instalar()
barra.instalar()
PLUGIN = construir_spec()
# los textos se esconden según su tamaño (3.26.4): antes de abrir un dibujo,
# y al actualizar sin reiniciar IngeCAD, con una regeneración (3.26.5)
try:
    legibles.aplicar_ya()
except Exception:  # noqa: BLE001 -- la pantalla queda como la arma IngeCAD
    pass
