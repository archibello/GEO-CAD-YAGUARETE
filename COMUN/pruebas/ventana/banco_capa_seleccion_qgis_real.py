"""Banco con la APLICACIÓN QGIS real (sin pantalla): Crear capa a partir de elementos
seleccionados (3.73.0) sobre memoria, GeoPackage, shapefile y texto delimitado.

Corre dentro de QGIS con --code (el código de geocad, en una carpeta sin espacios):
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=BANCO_SALIDA=<carpeta>/real.txt --env=BANCO_CODIGO=<carpeta con geocad> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
Deja el resultado en BANCO_SALIDA; termina en «TODO OK».
"""
import hashlib, os, sys, tempfile, traceback
from qgis.core import (QgsApplication, QgsFeature, QgsField, QgsFields, QgsGeometry, QgsPointXY, QgsProject,
                       QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsSymbol, QgsVectorFileWriter,
                       QgsVectorLayer, QgsWkbTypes)
from qgis.PyQt.QtCore import QCoreApplication, QItemSelectionModel, QTimer, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtTest import QTest
from qgis.utils import iface

sys.path.insert(0, os.environ["BANCO_CODIGO"])
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")   # no pisar la copia de Fernando
DATOS = tempfile.mkdtemp(prefix="banco-datos-")
EXTERNO = "create_layer_from_selected_features"
fallas, lineas = [], []


def check(nombre, ok, detalle=""):
    lineas.append("%s %s %s" % ("ok   " if ok else "FALLA", nombre, detalle if not ok else ""))
    if not ok:
        fallas.append(nombre)
    with open(os.environ["BANCO_SALIDA"] + ".parcial", "w", encoding="utf-8") as sal:    # si QGIS se cae
        sal.write("\n".join(str(x) for x in lineas) + "\n")


def eventos(n=30):
    for _ in range(n):
        QCoreApplication.processEvents()


def poner(capa, n, inicio=0):
    prov = capa.dataProvider()
    objs = []
    for i in range(inicio, inicio + n):
        f = QgsFeature(prov.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i, i)))
        f.setAttribute("nombre", "n%d" % i)
        objs.append(f)
    assert prov.addFeatures(objs)[0]
    capa.updateExtents()


def memoria(nombre, n=5):
    capa = QgsVectorLayer("Point?crs=EPSG:4326&field=nombre:string(20)", nombre, "memory")
    poner(capa, n)
    QgsProject.instance().addMapLayer(capa)
    return capa


def archivo(nombre, driver, extension, extra=None, n=5):
    fuente = QgsVectorLayer("Point?crs=EPSG:4326&field=nombre:string(20)" + (extra or ""), "x", "memory")
    poner(fuente, n)
    op = QgsVectorFileWriter.SaveVectorOptions()
    op.driverName = driver
    ruta = os.path.join(DATOS, nombre + extension)
    res = QgsVectorFileWriter.writeAsVectorFormatV3(fuente, ruta, QgsCoordinateTransformContext(), op)
    assert res[0] == QgsVectorFileWriter.WriterError.NoError, res
    capa = QgsVectorLayer(ruta, nombre, "ogr")
    assert capa.isValid(), ruta
    QgsProject.instance().addMapLayer(capa)
    return capa


def elegir_panel(*capas):
    vista = iface.layerTreeView()
    vista.selectionModel().clearSelection()
    iface.setActiveLayer(capas[0])
    raiz = QgsProject.instance().layerTreeRoot()
    for capa in capas:
        idx = vista.node2index(raiz.findLayer(capa.id()))
        vista.selectionModel().select(idx, QItemSelectionModel.SelectionFlag.Select
                                      | QItemSelectionModel.SelectionFlag.Rows)
    eventos()


def por_nombre(nombre):
    lista = QgsProject.instance().mapLayersByName(nombre)
    return lista[0] if lista else None


def huella(*rutas):
    return [hashlib.sha256(open(r, "rb").read()).hexdigest() for r in rutas]


def nombres_de(capa):
    return sorted(f["nombre"] for f in capa.getFeatures())


def menu_capas():
    menu = iface.layerTreeView().menuProvider().createContextMenu()
    iface.layerTreeView().contextMenuAboutToShow.emit(menu)
    return menu


def correr():
    from geocad import capa_seleccion as CS, classFactory, modulos
    from geocad import capa_seleccion_qgis as CQ

    base = os.environ["BANCO_CODIGO"]
    os.makedirs(os.path.join(base, EXTERNO), exist_ok=True)
    with open(os.path.join(base, EXTERNO, "metadata.txt"), "w", encoding="utf-8") as sal:
        sal.write("[general]\nname=copia de prueba\n")

    modulos.guardar("qgis", {m.clave: (m.clave == "capa_seleccion") for m in modulos.catalogo("qgis")})
    plug = classFactory(iface)
    plug.initGui()
    QTest.qWait(300)
    plug._cargar_subs()
    eventos()

    check("el complemento externo se retiró", not os.path.exists(os.path.join(base, EXTERNO)))
    check("queda una copia .anterior-", os.path.exists(os.path.join(base, ".anterior-" + EXTERNO, "metadata.txt")))
    herr = plug.capa_seleccion
    check("el módulo arrancó", herr is not None)
    check("está en el menú Vectorial", herr.accion in iface.vectorMenu().actions())
    check("no está en el menú GeoCAD", CS.TITULO not in [a.text() for a in plug.menu.actions()])
    check("Administrar Herramientas: banco Edición",
          any("Edici" in n and any(a.property("geocad_id") == "geocad:capaseleccion" for a in fila)
              for n, fila in plug._bancos()), str([n for n, _f in plug._bancos()]))

    # memoria, con un hueco en la numeración: la capa clonada conserva los ids
    capa = memoria("mem")
    capa.dataProvider().deleteFeatures([2])
    ids = sorted(capa.allFeatureIds())
    capa.selectByIds([ids[1], ids[3]])
    esperados = sorted(f["nombre"] for f in capa.getSelectedFeatures())
    sim = QgsSymbol.defaultSymbol(capa.geometryType())
    sim.setColor(QColor("#ff0000"))
    capa.renderer().setSymbol(sim)
    elegir_panel(capa)
    herr.accion.trigger()
    nueva = por_nombre("mem_filtered")
    check("memoria: capa nueva", nueva is not None)
    if nueva is not None:
        check("memoria: sólo lo elegido", nombres_de(nueva) == esperados, str(nombres_de(nueva)))
        check("memoria: conserva el estilo", nueva.renderer().symbol().color().name() == "#ff0000")
    check("memoria: la original sigue igual", capa.featureCount() == 4 and capa.subsetString() == ""
          and sorted(capa.selectedFeatureIds()) == [ids[1], ids[3]])

    # un solo elemento, y nombre libre si se repite
    capa.selectByIds([ids[0]])
    elegir_panel(capa)
    herr.crear()
    otra = por_nombre("mem_filtered_1")
    check("nombre libre: _filtered_1", otra is not None and otra.featureCount() == 1)

    # GeoPackage: el archivo no cambia de contenido
    gpkg = archivo("geo", "GPKG", ".gpkg")
    gids = sorted(gpkg.allFeatureIds())
    gpkg.selectByIds(gids[:3])
    esperados = sorted(f["nombre"] for f in gpkg.getSelectedFeatures())
    elegir_panel(gpkg)
    herr.crear()
    nueva = por_nombre("geo_filtered")
    check("GeoPackage: capa nueva", nueva is not None)
    if nueva is not None:
        check("GeoPackage: sólo lo elegido", nombres_de(nueva) == esperados and nueva.featureCount() == 3)
        check("GeoPackage: filtra por su clave", '"fid" IN' in nueva.subsetString(), nueva.subsetString())
        check("GeoPackage: misma fuente", nueva.source().split("|")[0] == gpkg.source().split("|")[0])
    independiente = QgsVectorLayer(gpkg.source(), "control", "ogr")
    check("GeoPackage: nada se escribió", independiente.featureCount() == 5 and gpkg.subsetString() == "")

    # shapefile: FID desde cero y archivos intactos
    shp = archivo("forma", "ESRI Shapefile", ".shp")
    rutas = [os.path.join(DATOS, "forma" + e) for e in (".shp", ".dbf", ".shx")]
    antes = huella(*rutas)
    sids = sorted(shp.allFeatureIds())
    shp.selectByIds([sids[0], sids[4]])
    esperados = sorted(f["nombre"] for f in shp.getSelectedFeatures())
    elegir_panel(shp)
    herr.crear()
    nueva = por_nombre("forma_filtered")
    check("shapefile: capa nueva", nueva is not None)
    if nueva is not None:
        check("shapefile: sólo lo elegido", nombres_de(nueva) == esperados and nueva.featureCount() == 2)
    check("shapefile: archivos intactos", huella(*rutas) == antes)

    # shapefile con un campo propio llamado FID: o acierta o no crea nada, nunca otros
    shp2 = archivo("confid", "ESRI Shapefile", ".shp", "&field=FID:integer")
    prov = shp2.dataProvider()
    idx = prov.fields().indexOf("FID")
    check("campo FID: existe en el archivo", idx >= 0)
    prov.changeAttributeValues({i: {idx: 100 + i} for i in shp2.allFeatureIds()})
    fids = sorted(shp2.allFeatureIds())
    shp2.selectByIds(fids[:2])
    esperados = sorted(f["nombre"] for f in shp2.getSelectedFeatures())
    elegir_panel(shp2)
    herr.crear()
    nueva = por_nombre("confid_filtered")
    check("campo FID: nunca elementos ajenos", nueva is None or nombres_de(nueva) == esperados)
    lineas.append("     campo FID: %s" % ("capa creada" if nueva is not None else "rechazada con aviso"))

    # filtro previo: la capa nueva muestra lo elegido
    gpkg2 = archivo("previo", "GPKG", ".gpkg")
    gpkg2.setSubsetString("\"nombre\" <> 'n0'")
    pids = sorted(gpkg2.allFeatureIds())
    gpkg2.selectByIds(pids[:1])
    esperados = sorted(f["nombre"] for f in gpkg2.getSelectedFeatures())
    elegir_panel(gpkg2)
    herr.crear()
    nueva = por_nombre("previo_filtered")
    check("con filtro previo", nueva is not None and nombres_de(nueva) == esperados)
    check("con filtro previo: la original lo conserva", gpkg2.subsetString() == "\"nombre\" <> 'n0'")

    # texto delimitado
    csv = os.path.join(DATOS, "puntos.csv")
    with open(csv, "w", encoding="utf-8") as sal:
        sal.write("nombre,x,y\na,1,1\nb,2,2\nc,3,3\n")
    texto = QgsVectorLayer("file://%s?type=csv&xField=x&yField=y&crs=EPSG:4326" % csv, "texto", "delimitedtext")
    check("texto: válida", texto.isValid())
    QgsProject.instance().addMapLayer(texto)
    tids = sorted(texto.allFeatureIds())
    texto.selectByIds(tids[1:])
    elegir_panel(texto)
    herr.crear()
    nueva = por_nombre("texto_filtered")
    check("texto delimitado: sólo lo elegido", nueva is not None and nombres_de(nueva) == ["b", "c"])

    # dos capas del mismo nombre a la vez: cada una con lo suyo
    a, b = memoria("igual", 3), memoria("igual", 4)
    a.selectByIds(sorted(a.allFeatureIds())[:1])
    b.selectByIds(sorted(b.allFeatureIds())[:2])
    elegir_panel(a, b)
    nuevas = herr.crear()
    check("dos capas: dos nuevas", len(nuevas) == 2, str(len(nuevas)))
    check("dos capas de igual nombre: cada una lo suyo",
          sorted(c.featureCount() for c in nuevas) == [1, 2]
          and len({c.name() for c in nuevas}) == 2, str([(c.name(), c.featureCount()) for c in nuevas]))

    # lo que se agregó sin guardar no entra
    ed = memoria("edicion", 2)
    ed.startEditing()
    f = QgsFeature(ed.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(9, 9)))
    f.setAttribute("nombre", "singuardar")
    ed.addFeature(f)
    todos = ed.allFeatureIds()
    negativos = [i for i in todos if i < 0]
    check("edición: hay un id negativo", len(negativos) == 1, str(todos))
    ed.selectByIds([negativos[0], max(todos)])
    elegir_panel(ed)
    herr.crear()
    nueva = por_nombre("edicion_filtered")
    check("edición: sólo lo guardado", nueva is not None and nueva.featureCount() == 1)
    check("edición: la original sigue editándose", ed.isEditable() and ed.editBuffer().addedFeatures())
    cuantas = len(QgsProject.instance().mapLayers())
    ed.selectByIds(negativos)
    elegir_panel(ed)
    check("edición: sólo sin guardar, nada", herr.crear() == [] and len(QgsProject.instance().mapLayers()) == cuantas)
    ed.rollBack()

    # sin selección: avisa y no crea nada
    ed.removeSelection()
    elegir_panel(ed)
    cuantas = len(QgsProject.instance().mapLayers())
    herr.accion.trigger()
    check("sin selección: nada", len(QgsProject.instance().mapLayers()) == cuantas)

    # si QGIS no acepta el filtro la capa no entra al proyecto
    capa.selectByIds([ids[0]])
    copia = CQ._condicion
    CQ._condicion = lambda _c, _i: ("$id IN (424242)", "")
    res = CQ.crear_capa(capa)
    CQ._condicion = copia
    check("filtro que no coincide: no entra al proyecto", res[0] is None and "exactamente" in res[2], str(res))
    check("filtro que no coincide: sin capa suelta", len(QgsProject.instance().mapLayers()) == cuantas)

    # clic derecho: antes de Duplicar capa; apagada sin selección; la capa de ráster no la ve
    elegir_panel(ed)
    menu = menu_capas()
    textos = [a.text().replace("&", "") for a in menu.actions()]
    check("clic derecho: está", CS.TITULO in textos, str(textos))
    if CS.TITULO in textos:
        duplicar = next((i for i, t in enumerate(textos) if t.startswith("Dupli")), -1)
        check("clic derecho: antes de Duplicar capa", textos.index(CS.TITULO) == duplicar - 1, str(textos))
        lineas.append("     idioma de QGIS: «%s»" % textos[duplicar])
    check("clic derecho: gris sin selección", not herr.accion_capas.isEnabled())
    capa.selectByIds([ids[0]])
    elegir_panel(capa)
    menu_capas()
    check("clic derecho: activa con selección", herr.accion_capas.isEnabled())

    # apagado no deja rastro y se puede volver a prender
    modulos.guardar("qgis", {"capa_seleccion": False})
    plug.aplicar_modulos()
    eventos()
    check("apagado: sin módulo", plug.capa_seleccion is None)
    check("apagado: fuera del menú Vectorial", CS.TITULO not in [a.text() for a in iface.vectorMenu().actions()])
    check("apagado: fuera del banco", "capaseleccion" not in plug.actions)
    elegir_panel(capa)
    menu = menu_capas()     # con su variable: si no, Qt borra el menú y sus acciones
    check("apagado: fuera del clic derecho", CS.TITULO not in [a.text().replace("&", "") for a in menu.actions()])
    os.makedirs(os.path.join(base, EXTERNO))
    modulos.guardar("qgis", {"capa_seleccion": False})
    plug.aplicar_modulos()
    check("apagado: el complemento suelto no se toca", os.path.isdir(os.path.join(base, EXTERNO)))
    modulos.guardar("qgis", {"capa_seleccion": True})
    plug.aplicar_modulos()
    eventos()
    check("prendido otra vez", plug.capa_seleccion is not None
          and CS.TITULO in [a.text() for a in iface.vectorMenu().actions()])
    check("prendido otra vez: una sola entrada",
          [a.text() for a in iface.vectorMenu().actions()].count(CS.TITULO) == 1)
    plug.unload()
    eventos()
    check("descargado: sin rastro", CS.TITULO not in [a.text() for a in iface.vectorMenu().actions()])


def fin():
    try:
        correr()
    except Exception:
        lineas.append(traceback.format_exc())
        fallas.append("excepción")
    lineas.append("TODO OK" if not fallas else "FALLAS: %s" % ", ".join(fallas))
    with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as sal:
        sal.write("\n".join(str(x) for x in lineas) + "\n")
    os._exit(0)


QTimer.singleShot(1500, fin)
