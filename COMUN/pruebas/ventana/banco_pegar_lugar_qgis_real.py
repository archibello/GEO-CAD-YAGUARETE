"""Banco con la APLICACIÓN QGIS real (sin pantalla): el Pegar de QGIS con «Pegar en el lugar».

banco_pegar_lugar_qgis.py usa un iface simulado y no ve el portapapeles propio de
QGIS (QgsClipboard). Prueba de 3.66.0: al agregar el mensaje para IngeCAD, QGIS
creía que otro programa había copiado y su Ctrl+V leía el texto: 7 y 1.5 llegaban
como '7' y '1.5'. Comprueba que Ctrl+C / Ctrl+V de QGIS da lo mismo con el módulo
y sin él, que el mensaje queda en el portapapeles, el ítem debajo de Pegar y que
una curva viaja como línea (IngeCAD no lee CircularString).

Corre dentro de QGIS con --code (el código de geocad, en una carpeta sin espacios):
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=BANCO_SALIDA=<carpeta>/real.txt --env=BANCO_CODIGO=<carpeta con geocad> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
Deja el resultado en BANCO_SALIDA; termina en «TODO OK».
"""
import json, os, sys, tempfile, traceback
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication, QTimer
from qgis.PyQt.QtWidgets import QApplication
from qgis.utils import iface

sys.path.insert(0, os.environ["BANCO_CODIGO"])
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")   # no pisar la copia de Fernando
fallas, lineas = [], []


def check(nombre, ok, detalle=""):
    lineas.append("%s %s %s" % ("ok   " if ok else "FALLA", nombre, detalle if not ok else ""))
    if not ok:
        fallas.append(nombre)


def eventos():
    for _ in range(20):
        QCoreApplication.processEvents()


def capa(nombre, crs, tipo="LineString"):
    uri = "%s?crs=%s&field=nombre:string(20)&field=cant:integer&field=valor:double" % (tipo, crs)
    lay = QgsVectorLayer(uri, nombre, "memory")
    QgsProject.instance().addMapLayer(lay)
    return lay


def copiar_y_pegar(con_modulo):
    """Ctrl+C en una capa y Ctrl+V en otra, por las acciones de QGIS."""
    from geocad import pegar_lugar
    from geocad.pegar_lugar_qgis import PegarLugarQgis
    a, b = capa("origen", "EPSG:22185"), capa("destino", "EPSG:4326")
    a.startEditing()
    f = QgsFeature(a.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5500000, 6100000), QgsPointXY(5500100, 6100100)]))
    f.setAttributes(["uno", 7, 1.5])
    a.addFeature(f)
    a.commitChanges()
    a.selectAll()
    iface.setActiveLayer(a)
    mod = PegarLugarQgis(iface) if con_modulo else None
    if mod is not None:
        menu = iface.editMenu().actions()
        check("debajo de Pegar", menu[menu.index(mod.accion) - 1] is iface.actionPasteFeatures())
    iface.actionCopyFeatures().trigger()
    eventos()
    tiene = pegar_lugar.leer_copia(QApplication.clipboard().mimeData()) is not None
    check("mensaje en el portapapeles" if con_modulo else "sin módulo, sin mensaje", tiene == con_modulo)
    iface.setActiveLayer(b)
    b.startEditing()
    iface.actionPasteFeatures().trigger()
    eventos()
    pegados = [(x.geometry().asWkt(3), [repr(v) for v in x.attributes()]) for x in b.getFeatures()]
    if mod is not None:
        mod.unload()
    b.rollBack()
    QgsProject.instance().removeMapLayer(a.id())
    QgsProject.instance().removeMapLayer(b.id())
    return pegados


def curva():
    from geocad import pegar_lugar
    from geocad.pegar_lugar_qgis import mensaje_de
    lay = capa("curvas", "EPSG:22185", "CircularString")
    f = QgsFeature(lay.fields())
    f.setGeometry(QgsGeometry.fromWkt("CircularString (0 0, 1 1, 2 0)"))
    msg = pegar_lugar.desempaquetar(mensaje_de(lay, [f]))
    wkt = msg["objetos"][0]["wkt"]
    check("la curva viaja como línea", pegar_lugar.tipo_wkt(wkt) == "linea", wkt[:40])
    QgsProject.instance().removeMapLayer(lay.id())


def de_ingecad():
    """Pegar en el lugar con la barra de mensajes real (3.66.0: level=int daba TypeError)."""
    from geocad import pegar_lugar
    from geocad.pegar_lugar_qgis import PegarLugarQgis
    from qgis.PyQt.QtCore import QMimeData
    lay = capa("destino", "EPSG:22185")
    iface.setActiveLayer(lay)
    mod = PegarLugarQgis(iface)
    QApplication.clipboard().clear()
    eventos()
    check("sin nada copiado: lo avisa", "no tiene objetos" in mod.pegar())
    objetos = [{"wkt": "LINESTRING (5500000 6100000, 5500100 6100100)", "capa": "Muros", "color": None,
                "aci": None, "tipo_linea": None, "grosor": None}]
    capas = {"Muros": {"color": "#ff0000", "aci": 1, "tipo_linea": "DASHED", "grosor": 0.35}}
    datos = QMimeData()
    datos.setData("application/x-ingecad-clip-id", b"banco:1")
    QApplication.clipboard().setMimeData(datos)
    pegar_lugar.dejar_copia(pegar_lugar.empaquetar("ingecad", "EPSG:22185", objetos, capas),
                            datos, "application/x-ingecad-clip-id")
    eventos()
    texto = mod.pegar()
    check("pega y avisa", texto.startswith("Pegado"), texto)
    pegados = list(lay.getFeatures())
    check("en sus coordenadas", len(pegados) == 1 and pegados[0].geometry().asWkt(0).startswith("LineString (5500000 6100000"))
    check("con su capa CAD", len(pegados) == 1 and pegados[0]["LAYER_CODE"] == "Muros")
    # lo cerrado de IngeCAD en una capa de líneas (3.66.3): su contorno, también con agujero
    objetos = [{"wkt": "POLYGON ((0 0, 10 0, 10 10, 0 0), (2 1, 4 1, 4 3, 2 1))", "capa": "Pisos", "color": None,
                "aci": None, "tipo_linea": None, "grosor": None}]
    datos = QMimeData()
    datos.setData("application/x-ingecad-clip-id", b"banco:2")
    QApplication.clipboard().setMimeData(datos)
    pegar_lugar.dejar_copia(pegar_lugar.empaquetar("ingecad", "EPSG:22185", objetos, {}),
                            datos, "application/x-ingecad-clip-id")
    eventos()
    texto = mod.pegar()
    check("lo cerrado va como contorno", "como contorno" in texto, texto)
    pisos = [x for x in lay.getFeatures() if x["LAYER_CODE"] == "Pisos"]
    check("anillo y agujero, dos líneas", len(pisos) == 2 and all(x.geometry().type() == 1 for x in pisos))
    iface.setActiveLayer(capa("puntos", "EPSG:22185", "Point"))
    check("otro tipo: lo avisa", "nada para pegar" in mod.pegar())
    mod.unload()
    lay.rollBack()


def correr():
    try:
        sin = copiar_y_pegar(False)
        QApplication.clipboard().clear()
        eventos()
        con = copiar_y_pegar(True)
        check("se pegó", len(sin) == 1, json.dumps(sin))
        check("Pegar de QGIS igual con el módulo", con == sin, "%s != %s" % (con, sin))
        curva()
        de_ingecad()
    except Exception:  # noqa: BLE001
        fallas.append("excepción")
        lineas.append(traceback.format_exc())
    lineas.append("TODO OK" if not fallas else "FALLAS: %s" % fallas)
    with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
    os._exit(0)


QTimer.singleShot(3000, correr)
