# -*- coding: utf-8 -*-
"""Enviar lo seleccionado de copias filtradas de un mismo archivo (3.66.5), con QGIS real.

Hoja de ruta: «si varias capas vienen del mismo archivo (p. ej. PC_2_DE_MAYO y sus copias
filtradas), sólo va la primera; las otras se saltean sin avisar». Con GeoPackage y con
shapefile: dos capas del mismo archivo con filtros distintos y un color cada una; se mira
el mensaje que sale para IngeCAD. Sin pantalla, en un perfil aparte:

    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen
        --env=BANCO_SALIDA=<carpeta>/f.txt --env=BANCO_CODIGO=<carpeta con geocad>
        org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <perfil>
        --code banco_enviar_copias_qgis_real.py
"""
import os, sys, tempfile, traceback
from qgis.core import (QgsCoordinateTransformContext, QgsFeature, QgsFillSymbol, QgsGeometry,
                       QgsProject, QgsSingleSymbolRenderer, QgsVectorFileWriter, QgsVectorLayer)
from qgis.utils import iface

os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")   # no pisar la copia de Fernando
sys.path.insert(0, os.environ["BANCO_CODIGO"])
lineas, fallas = [], []


def check(nombre, ok, extra=""):
    lineas.append("%s  %s %s" % ("ok" if ok else "MAL", nombre, extra))
    if not ok:
        fallas.append(nombre)


def archivo(ruta, driver):
    """Seis parcelas, con el campo «z» de 1 a 6."""
    mem = QgsVectorLayer("Polygon?crs=EPSG:32721&field=z:integer", "m", "memory")
    feats = []
    for z in range(1, 7):
        f = QgsFeature(mem.fields())
        f.setAttribute("z", z)
        f.setGeometry(QgsGeometry.fromWkt(
            "POLYGON((%d 0,%d 0,%d 10,%d 10,%d 0))" % (z * 20, z * 20 + 10, z * 20 + 10, z * 20, z * 20)))
        feats.append(f)
    mem.dataProvider().addFeatures(feats)
    op = QgsVectorFileWriter.SaveVectorOptions()
    op.driverName, op.layerName = driver, "parcelas"
    res = QgsVectorFileWriter.writeAsVectorFormatV3(mem, ruta, QgsCoordinateTransformContext(), op)
    assert res[0] == QgsVectorFileWriter.WriterError.NoError, res


def copia(uri, nombre, filtro, color):
    lay = QgsVectorLayer(uri, nombre, "ogr")
    assert lay.isValid(), uri
    assert lay.setSubsetString(filtro), filtro
    lay.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": color})))
    return lay


def caso(plug, buzon, uri, titulo):
    proyecto = QgsProject.instance()
    a = copia(uri, "Norte", '"z" <= 3', "#ff0000")
    b = copia(uri, "Sur", '"z" >= 3', "#0000ff")      # el 3 está en las dos
    entera = QgsVectorLayer(uri, "Entera", "ogr")
    proyecto.addMapLayers([a, b])
    por_z = lambda lay, zs: [f.id() for f in lay.getFeatures() if f["z"] in zs]
    a.selectByIds(por_z(a, {1, 3}))
    b.selectByIds(por_z(b, {3, 5}))
    plug.send(plug._selected_layers(), "seleccion",
              {"capas_colores": True, "rotulos": "ninguno", "altura": 3.0})
    capas = buzon.receive("ingecad")[0]["capas"]
    check(titulo + ": una sola conexión", len(capas) == 1, str(len(capas)))
    fids = capas[0]["fids"]
    # los fids de las copias son los del archivo: son los objetos elegidos en cada copia
    zs = sorted(entera.getFeature(i)["z"] for i in fids)
    check(titulo + ": llegan los elegidos en las dos", zs == [1, 3, 5], str(zs))
    colores = {entera.getFeature(int(k))["z"]: str(v[1]).lower()
               for k, v in capas[0]["estilo"]["objetos"].items()}
    check(titulo + ": cada uno con el color de su capa",
          colores == {1: "#ff0000", 3: "#ff0000", 5: "#0000ff"}, str(colores))
    aviso = bar_ultimo()
    check(titulo + ": el aviso cuenta y nombra la copia",
          "3 objeto(s)" in aviso and "mismo archivo: Sur" in aviso, aviso)
    proyecto.removeMapLayers([a.id(), b.id()])


avisos = []


def bar_ultimo():
    return avisos[-1] if avisos else ""


def correr():
    from geocad import buzon, modulos
    from geocad.plugin import VERSION
    modulos.guardar("qgis", {c.clave: False for c in modulos.catalogo("qgis")})
    import geocad
    plug = geocad.classFactory(iface)
    plug.initGui()
    plug._bar = lambda texto, *a, **k: avisos.append(texto)
    buzon.heartbeat("ingecad", {"version": VERSION})     # no abrir IngeCAD
    carpeta = tempfile.mkdtemp(prefix="banco-copias-")
    gpkg = os.path.join(carpeta, "catastro.gpkg")
    archivo(gpkg, "GPKG")
    caso(plug, buzon, gpkg + "|layername=parcelas", "GeoPackage")
    shp = os.path.join(carpeta, "catastro.shp")
    archivo(shp, "ESRI Shapefile")
    caso(plug, buzon, shp, "Shapefile")


try:
    correr()
except Exception:  # noqa: BLE001
    fallas.append("excepción")
    lineas.append(traceback.format_exc())
lineas.append("TODO OK" if not fallas else "FALLAS: %s" % fallas)
with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
    fh.write("\n".join(lineas) + "\n")
os._exit(0)
