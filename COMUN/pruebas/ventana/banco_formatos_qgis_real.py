# -*- coding: utf-8 -*-
"""Lo copiado llega con los formatos de origen (3.66.4), con la aplicación QGIS real.

Fernando, 04/11/2026: «estaria bueno que las copias lleguen con los formatos de origen».
Con GeoCAD y Yaguá Capas de verdad, una capa de líneas ya abierta y sin campos CAD: pega
objetos con color, tipo y grosor propios y uno PorCapa, y DIBUJA la capa para contar lo
que se ve (los campos solos no lo prueban: estaban bien y se veía todo negro). Sin
pantalla, en un perfil aparte:

    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen
        --env=BANCO_SALIDA=<carpeta>/f.txt --env=BANCO_CODIGO=<carpeta con geocad>
        org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <perfil>
        --code banco_formatos_qgis_real.py
"""
import os, sys, tempfile, traceback
from qgis.core import (QgsCoordinateReferenceSystem, QgsMapRendererSequentialJob, QgsMapSettings,
                       QgsProject, QgsRectangle, QgsVectorLayer)
from qgis.PyQt.QtCore import QCoreApplication, QSize
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface, plugins

os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")   # no pisar la copia de Fernando
sys.path.insert(0, os.environ["BANCO_CODIGO"])
lineas, fallas = [], []


def check(nombre, ok, extra=""):
    lineas.append("%s  %s %s" % ("ok" if ok else "MAL", nombre, extra))
    if not ok:
        fallas.append(nombre)


def eventos(n=50):
    for _ in range(n):
        QCoreApplication.processEvents()


def dibujar(lay):
    ms = QgsMapSettings()
    ms.setLayers([lay])
    ms.setExtent(QgsRectangle(-30, -30, 120, 70))
    ms.setOutputSize(QSize(600, 400))
    ms.setBackgroundColor(QColor("white"))
    ms.setDestinationCrs(lay.crs())
    job = QgsMapRendererSequentialJob(ms)
    job.start()
    job.waitForFinished()
    return job.renderedImage()


def correr():
    from geocad import modulos, pegar_lugar
    claves = {c.clave: False for c in modulos.catalogo("qgis")}
    claves.update(capas=True, pegar_lugar=True, dibujo=True)
    modulos.guardar("qgis", claves)
    import geocad
    plug = geocad.classFactory(iface)
    plug.initGui()
    plugins["geocad"] = plug
    eventos(20)
    ctrl = plugins["Layer_Properties"].ctrl
    QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:5349"))
    lay = QgsVectorLayer("LineString?crs=EPSG:5349&field=LAYER_CODE:string", "obra", "memory")
    QgsProject.instance().addMapLayer(lay)
    iface.setActiveLayer(lay)
    eventos()
    ctrl.attach(lay)
    ctrl.ensure_initialized()
    base = {"capa": "0", "color": None, "aci": None, "tipo_linea": None, "grosor": None}
    objetos = [
        dict(base, wkt="POLYGON ((0 0, 100 0, 100 50, 0 50, 0 0))", color="#ff0000", aci=1,
             tipo_linea="DASHED", grosor=1.0),
        dict(base, wkt="LINESTRING (-15 -15, -15 15, 15 15, 15 -15, -15 -15)", color="#00ff00", aci=3, grosor=1.0),
        dict(base, wkt="LINESTRING (10 40, 90 10)"),                      # PorCapa
    ]
    capas = {"0": {"color": "#ffffff", "aci": 7, "tipo_linea": "Continuous", "grosor": -1.0}}
    from geocad.pegar_lugar_qgis import pegar
    texto = pegar(iface, pegar_lugar.desempaquetar(pegar_lugar.empaquetar("ingecad", "EPSG:5349", objetos, capas)), lay)
    check("pegado", texto.startswith("Pegado"), texto)
    eventos()
    img = dibujar(lay)
    rojo = verde = 0
    for x in range(600):
        for y in range(400):
            c = img.pixelColor(x, y)
            if c.red() > 180 and c.green() < 90 and c.blue() < 90:
                rojo += 1
            elif c.green() > 140 and c.red() < 90:
                verde += 1
    check("se ve el rojo propio", rojo > 500, str(rojo))
    check("se ve el verde propio", verde > 500, str(verde))
    # la línea PorCapa, continua: de (10,40) a (90,10), a 4 px por unidad y con y=70 arriba
    huecos = 0
    for i in range(10, 310):
        x, y = 160 + i, 120 + i * 120 / 320
        vecinos = [img.pixelColor(int(x), int(y) + d) for d in (-1, 0, 1)]
        if not any(c.red() < 170 and c.green() < 170 and c.blue() < 170 for c in vecinos):
            huecos += 1
    check("lo PorCapa, sin cortes", huecos == 0, "%d de 300 sin línea" % huecos)
    lay.rollBack()


try:
    correr()
except Exception:  # noqa: BLE001
    fallas.append("excepción")
    lineas.append(traceback.format_exc())
lineas.append("TODO OK" if not fallas else "FALLAS: %s" % fallas)
with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
    fh.write("\n".join(lineas) + "\n")
os._exit(0)
