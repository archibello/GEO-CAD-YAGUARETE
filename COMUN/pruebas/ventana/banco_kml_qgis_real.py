"""Banco con la APLICACIÓN QGIS real (sin pantalla): Exportar a Google Earth (3.74.0).

Repite los casos que rompían al complemento KML Tools (propuesta_kml/INFORME_KML_TOOLS.md).
Corre dentro de QGIS con --code (el código de geocad, en una carpeta sin espacios):
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=BANCO_SALIDA=<carpeta>/real.txt --env=BANCO_CODIGO=<carpeta con geocad> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
Deja el resultado en BANCO_SALIDA; termina en «TODO OK».
"""
import math, os, re, sys, tempfile, traceback, zipfile
from qgis.core import (QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsFeature, QgsFillSymbol, QgsGeometry, QgsGraduatedSymbolRenderer,
                       QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings, QgsPointXY, QgsProject,
                       QgsRendererCategory, QgsRendererRange, QgsSimpleLineSymbolLayer, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QMessageBox, QPushButton
from qgis.utils import iface

sys.path.insert(0, os.environ["BANCO_CODIGO"])
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
DATOS = tempfile.mkdtemp(prefix="banco-datos-")
fallas, lineas = [], []


def check(nombre, ok, detalle=""):
    lineas.append("%s %s %s" % ("ok   " if ok else "FALLA", nombre, detalle if not ok else ""))
    if not ok:
        fallas.append(nombre)
    with open(os.environ["BANCO_SALIDA"] + ".parcial", "w", encoding="utf-8") as sal:
        sal.write("\n".join(str(x) for x in lineas) + "\n")


def capa(tipo, crs, campos, filas, nombre="prueba"):
    uri = tipo + "?" + ("crs=%s" % crs if crs else "crs=")
    for n, t in campos:
        uri += "&field=%s:%s" % (n, t)
    lyr = QgsVectorLayer(uri, nombre, "memory")
    assert lyr.isValid(), uri
    fs = []
    for wkt, vals in filas:
        f = QgsFeature(lyr.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes(vals)
        fs.append(f)
    lyr.dataProvider().addFeatures(fs)
    lyr.updateExtents()
    return lyr


def doc(ruta):
    with zipfile.ZipFile(str(ruta)) as z:
        return z.read("doc.kml").decode("utf-8")


def coords(t):
    return re.findall(r"<coordinates>\s*(.*?)\s*</coordinates>", t, re.S)


def lonlat(t):
    c = coords(t)[0].split()[0].split(",")
    return float(c[0]), float(c[1])


def dist(a, b):
    la = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(la), (a[1] - b[1]) * 110900)


def correr():
    from geocad import classFactory, modulos
    from geocad import kml_qgis as KQ

    modulos.guardar("qgis", {m.clave: (m.clave == "googleearth") for m in modulos.catalogo("qgis")})
    plug = classFactory(iface)
    plug.initGui()
    QTest.qWait(300)

    # el banco y el menú
    def menu_textos(m):
        salida = []
        for a in m.actions():
            salida.append(a.text())
            if a.menu():
                salida += menu_textos(a.menu())
        return salida
    textos = menu_textos(plug.menu)
    check("nada de KML en el menú GeoCAD", not [t for t in textos if "KML" in t or "Ver en Google" in t], str(textos))
    ids = {a.property("geocad_id") for _n, fila in plug._bancos() for a in fila}
    check("exportar y ver en el banco", {"geocad:ge_exportar", "geocad:ge_ver"} <= ids)
    check("con ícono", not plug.actions["ge_exportar"].icon().isNull())

    ct = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateReferenceSystem("EPSG:5348"),
                                QgsProject.instance())
    P = ct.transform(QgsPointXY(-55.9, -27.4))
    X, Y = P.x(), P.y()
    PT, LIN = "Point(%r %r)" % (X, Y), "LineString(%r %r, %r %r)" % (X, Y, X + 100, Y + 100)
    POL = "Polygon((%r %r, %r %r, %r %r, %r %r))" % (X, Y, X + 100, Y, X + 100, Y + 100, X, Y)
    n = [0]

    def sal(capas, responder=None, ext=".kmz", **kw):
        n[0] += 1
        ruta = os.path.join(DATOS, "s%d%s" % (n[0], ext))
        for c in capas:
            if not QgsProject.instance().mapLayer(c.id()):
                QgsProject.instance().addMapLayer(c)
        res = KQ.exportar(capas, ruta, responder=responder or (lambda r: KQ.preguntar(None, r)), **kw)
        return res

    # precisión y atributos
    c = capa("Point", "EPSG:5348", [("nombre", "string"), ("cota", "integer"), ("nivel", "double"), ("nada", "string")],
             [(PT, ["Ñandú", 0, 0.0, None])])
    r = sal([c])
    t = doc(r.ruta)
    check("POSGAR 2007 faja 6 sin error", dist(lonlat(t), (-55.9, -27.4)) < 0.001, str(lonlat(t)))
    check("nombre con ñ desde el campo", "<name>Ñandú</name>" in t, t[:400])
    check("el valor 0 se exporta", '<Data name="cota"><value>0</value>' in t and '<Data name="nivel"><value>0.0</value>' in t, t)
    check("NULL queda vacío, sin caerse", '<Data name="nada"><value /></Data>' in t or '<Data name="nada"><value></value>' in t, t)

    # sin sistema: pregunta; propone la faja de las X; la capa no se toca
    c = capa("Point", "", [], [(PT, [])])
    vistas = []

    def usar_sugerido(rev):
        vistas.append(rev)
        return QgsCoordinateReferenceSystem(rev.sugerido)
    r = sal([c], usar_sugerido)
    check("sin sistema: se pregunta", len(vistas) == 1 and vistas[0].codigo == "")
    check("propone POSGAR 2007 faja 6", vistas[0].sugerido == "EPSG:5348", vistas[0].sugerido)
    check("cae en su lugar", dist(lonlat(doc(r.ruta)), (-55.9, -27.4)) < 0.001)
    check("la capa sigue sin sistema", not c.crs().isValid())
    r = sal([capa("Point", "", [], [(PT, [])])], lambda rev: None)
    check("saltear: no se escribe ni inventa", r.ruta is None and len(r.saltadas) == 1)

    # faja equivocada
    vistas.clear()
    c = capa("Point", "EPSG:5349", [], [(PT, [])])
    r = sal([c], usar_sugerido)
    check("faja 7 con X de faja 6: avisa", vistas and vistas[0].sugerido == "EPSG:5348")
    check("corregida, cae en su lugar", dist(lonlat(doc(r.ruta)), (-55.9, -27.4)) < 0.001)
    check("la capa conserva su sistema", c.crs().authid() == "EPSG:5349")
    r = sal([capa("Point", "EPSG:5349", [], [(PT, [])])], lambda rev: False)
    check("cancelar: nada", r.cancelado and r.ruta is None)
    vistas.clear()
    sal([capa("Point", "EPSG:5348", [], [(PT, [])])], lambda rev: vistas.append(rev) or rev.capa.crs())
    check("faja correcta: sin sugerencia", vistas[0].sugerido == "")

    # los carteles de verdad
    caja = capa("Point", "EPSG:5349", [], [(PT, [])], "Parcelas")
    vio = {}

    def apretar():
        w = QApplication.activeModalWidget()
        if isinstance(w, QMessageBox):
            vio["texto"] = w.text()
            b = [x for x in w.findChildren(QPushButton) if "Usar faja" in x.text()]
            vio["boton"] = bool(b)
            if b:
                b[0].click()
    QTimer.singleShot(200, apretar)
    r = sal([caja])
    check("cartel real de faja", vio.get("boton") and "faja 6" in vio.get("texto", ""), str(vio))
    check("el cartel corrige", r.ruta is not None and dist(lonlat(doc(r.ruta)), (-55.9, -27.4)) < 0.001)

    # Campo Inchauspe: la conversión y el aviso de precisión
    r = sal([capa("Point", "EPSG:22196", [], [(PT, [])])])
    ll = lonlat(doc(r.ruta))
    check("Campo Inchauspe con su datum", dist(ll, (-55.900488938, -27.401941997)) < 0.01, str(ll))
    check("avisa la precisión", any("9" in a and "precisi" in a for a in r.avisos), str(r.avisos))

    # graduado con opacidad, los cuatro tipos
    for tipo, wkt, Sim in (("LineString", LIN, QgsLineSymbol), ("Point", PT, QgsMarkerSymbol), ("Polygon", POL, QgsFillSymbol)):
        s = Sim()
        s.setOpacity(0.5)
        c = capa(tipo, "EPSG:5348", [("v", "double")], [(wkt, [5.0]), (wkt, [15.0])])
        c.setRenderer(QgsGraduatedSymbolRenderer("v", [QgsRendererRange(0, 10, s, "a"), QgsRendererRange(10, 20, s.clone(), "b")]))
        r = sal([c])
        check("graduado con opacidad: " + tipo, doc(r.ruta).count("<Placemark") == 2)

    # categorizado por expresión
    c = capa("Point", "EPSG:5348", [("a", "string"), ("b", "string")], [(PT, ["x", "1"]), (PT, ["y", "2"])])
    s1, s2 = QgsMarkerSymbol(), QgsMarkerSymbol()
    s1.setColor(QColor("#ff0000"))
    s2.setColor(QColor("#00ff00"))
    c.setRenderer(QgsCategorizedSymbolRenderer('"a" || "b"', [QgsRendererCategory("x1", s1, "r"), QgsRendererCategory("y2", s2, "v")]))
    t = doc(sal([c]).ruta)
    usados = re.findall(r"<styleUrl>#(.*?)</styleUrl>", t)
    check("categorizado por expresión: colores distintos", len(set(usados)) == 2 and "ff0000" in usados[0], str(usados))

    # polígono sólo contorno, categorizado
    c = capa("Polygon", "EPSG:5348", [("c", "string")], [(POL, ["a"])])
    s = QgsFillSymbol()
    linea = QgsSimpleLineSymbolLayer(QColor("#123456"))
    s.changeSymbolLayer(0, linea)
    c.setRenderer(QgsCategorizedSymbolRenderer("c", [QgsRendererCategory("a", s, "a")]))
    t = doc(sal([c]).ruta)
    check("contorno categorizado no se cae, sin relleno", "<fill>0</fill>" in t and "ff563412" in t, t[:600])

    # relleno y borde separados
    c = capa("Polygon", "EPSG:5348", [], [(POL, [])])
    s = QgsFillSymbol.createSimple({"color": "255,0,0,128", "outline_color": "0,0,255", "outline_width": "0.5"})
    c.renderer().setSymbol(s)
    t = doc(sal([c]).ruta)
    check("borde azul", "ffff0000" in t, t[:600])
    check("relleno rojo semitransparente", re.search(r"<PolyStyle><color>[0-9a-f]{2}0000ff</color>", t) is not None, t[:600])
    check("área y perímetro en el globo", "Área" in t and "perímetro 341" in t.replace(".", ","), t[:900])

    # curvas
    c = capa("CompoundCurve", "EPSG:5348", [], [("CompoundCurve(CircularString(%r %r, %r %r, %r %r))" % (X, Y, X + 50, Y + 50, X + 100, Y), [])])
    t = doc(sal([c]).ruta)
    check("curva a tramos", len(coords(t)[0].split()) > 5, t[:300])
    c = capa("CurvePolygon", "EPSG:5348", [], [("CurvePolygon(CircularString(%r %r, %r %r, %r %r))" % (X, Y, X + 100, Y, X, Y), [])])
    check("polígono curvo a tramos", len(coords(doc(sal([c]).ruta))[0].split()) > 5)

    # .kml de verdad, y sin pisar si falla
    r = sal([capa("Point", "EPSG:5348", [], [(PT, [])])], ext=".kml")
    with open(str(r.ruta), "rb") as f:
        check(".kml es texto, no ZIP", f.read(5) == b"<?xml")

    # multiparte, huecos, selección, geometría nula
    c = capa("MultiPolygon", "EPSG:5348", [], [("MultiPolygon(((%r %r, %r %r, %r %r, %r %r),(%r %r, %r %r, %r %r, %r %r)),((%r %r, %r %r, %r %r, %r %r)))" % (
        X, Y, X + 100, Y, X + 100, Y + 100, X, Y, X + 50, Y + 10, X + 60, Y + 10, X + 60, Y + 20, X + 50, Y + 10,
        X + 500, Y, X + 600, Y, X + 600, Y + 100, X + 500, Y), [])])
    t = doc(sal([c]).ruta)
    check("multipolígono con hueco", t.count("<Polygon>") == 2 and t.count("innerBoundaryIs>") == 2, t[:500])
    c = capa("Point", "EPSG:5348", [("nombre", "string")], [(PT, ["A"]), (PT, ["B"]), ("Point EMPTY", ["C"])])
    r = sal([c])
    check("sin geometría: se informa", r.salteados["sin geometría"] == 1 and "sin geometría 1" in KQ.resumen(r), str(r.salteados))
    c.selectByIds([sorted(c.allFeatureIds())[1]])
    t = doc(sal([c], solo_seleccion=True).ruta)
    check("sólo seleccionados", t.count("<Placemark") == 1 and "<name>B</name>" in t, t[:300])

    # varias capas, una carpeta por capa, grupos y nombres repetidos
    raiz = QgsProject.instance().layerTreeRoot()
    a, b, d = (capa("Point", "EPSG:5348", [], [(PT, [])], nombre) for nombre in ("Lotes", "Lotes", "Calles"))
    for x in (a, b, d):
        QgsProject.instance().addMapLayer(x)
    g = raiz.addGroup("Obra")
    nodo = raiz.findLayer(d.id())
    g.addChildNode(nodo.clone())
    raiz.removeChildNode(nodo)
    r = sal([a, b, d])
    carpetas = re.findall(r"<Folder><name>(.*?)</name>", doc(r.ruta))
    check("una carpeta por capa", sorted(carpetas) == ["Lotes", "Lotes (2)", "Obra - Calles"], str(carpetas))

    # rótulo de la capa como nombre
    c = capa("Point", "EPSG:5348", [("otro", "string")], [(PT, ["desde el rótulo"])])
    pal = QgsPalLayerSettings()
    pal.fieldName = "otro"
    pal.isExpression = False
    c.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    c.setLabelsEnabled(True)
    check("nombre desde el rótulo", "<name>desde el rótulo</name>" in doc(sal([c]).ruta))

    # nada que exportar
    r = sal([capa("Point", "EPSG:5348", [], [])])
    check("capa vacía: sin archivo", r.ruta is None)

    # la ventana
    capas = KQ.capas_del_proyecto()
    iface.layerTreeView().layerTreeModel()
    dlg = KQ.ExportarDialog(capas, os.path.join(DATOS, "v.kmz"))
    tildadas = dlg.ids_elegidos()
    check("la ventana abre con las visibles", tildadas and set(tildadas) == {c.id() for c, v in capas if v})
    check("abrir en Google Earth, de entrada", dlg.abrir.isChecked())
    check("agrega .kmz", KQ.con_extension("/x/obra").suffix == ".kmz" and KQ.con_extension("/x/o.KML").suffix == ".KML")
    dlg.deleteLater()

    # Ver en Google Earth, sin abrir nada de verdad: sólo las visibles, sin carteles
    QgsProject.instance().removeAllMapLayers()
    prendida = capa("Point", "EPSG:5348", [("nombre", "string")], [(PT, ["Prendida"])], "Prendida")
    apagada = capa("Point", "EPSG:5348", [("nombre", "string")], [(PT, ["Apagada"])], "Apagada")
    QgsProject.instance().addMapLayer(prendida)
    QgsProject.instance().addMapLayer(apagada)
    QgsProject.instance().layerTreeRoot().findLayer(apagada.id()).setItemVisibilityChecked(False)
    from qgis.PyQt.QtGui import QDesktopServices
    abiertos = []
    original = KQ.QDesktopServices
    class Falso:
        @staticmethod
        def openUrl(url):
            abiertos.append(url.toLocalFile())
            return True
    KQ.QDesktopServices = Falso
    plug._kml("ver")
    KQ.QDesktopServices = original
    check("Ver: abre un KMZ", abiertos and abiertos[0].endswith("GeoCAD desde QGIS.kmz") and os.path.exists(abiertos[0]), str(abiertos))
    t = doc(abiertos[0])
    check("Ver: sólo las capas visibles", "Prendida" in t and "Apagada" not in t, t[:400])


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
