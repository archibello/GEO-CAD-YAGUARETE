"""Banco con la APLICACIÓN QGIS real (sin pantalla): Imagen base en las presentaciones.

Con teselas XYZ locales de ruido (cada píxel se reconoce), una composición abierta y
el mouse de verdad sobre la vista: separa el mapa, corre sólo la imagen, sigue al mapa,
bloquea, deshace, guarda el recorte y mide píxel por píxel que la georreferencia es la
lograda. Corre dentro de QGIS con --code (el código de geocad, en una carpeta sin espacios):
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=BANCO_SALIDA=<carpeta>/real.txt --env=BANCO_CODIGO=<carpeta con geocad> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
Deja el resultado en BANCO_SALIDA; termina en «TODO OK».
"""
import os, random, sys, tempfile, traceback
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsLayoutExporter,
                       QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize, QgsPointXY, QgsPrintLayout,
                       QgsProject, QgsRasterLayer, QgsRectangle, QgsVectorLayer)
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPointF, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QImage, QMouseEvent
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QToolBar
from qgis.utils import iface

sys.path.insert(0, os.environ["BANCO_CODIGO"])
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")   # no pisar la copia de Fernando
CARPETA = tempfile.mkdtemp(prefix="banco-imgbase-")
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


def cerca(a, b, tol=1e-6):
    return abs(a - b) <= tol


def teselas(z, xs, ys):
    """Bloques de 4 píxeles de color al azar: un corrimiento se detecta sin dudas."""
    aleatorio = random.Random(7)
    for x in xs:
        os.makedirs(os.path.join(CARPETA, "t", str(z), str(x)), exist_ok=True)
        for y in ys:
            img = QImage(256, 256, QImage.Format.Format_RGB32)
            for j in range(0, 256, 4):
                for i in range(0, 256, 4):
                    c = QColor(aleatorio.randint(0, 255), aleatorio.randint(0, 255), aleatorio.randint(0, 255))
                    for jj in range(4):
                        for ii in range(4):
                            img.setPixelColor(i + ii, j + jj, c)
            img.save(os.path.join(CARPETA, "t", str(z), str(x), "%d.png" % y))


def mouse(view, tipo, pos, boton, botones):
    QApplication.sendEvent(view.viewport(), QMouseEvent(tipo, QPointF(pos), boton, botones,
                                                        Qt.KeyboardModifier.NoModifier))
    eventos(5)


def arrastrar(view, p1, p2, partes=4):
    izq = Qt.MouseButton.LeftButton
    mouse(view, QEvent.Type.MouseButtonPress, p1, izq, izq)
    for k in range(1, partes + 1):
        x = p1.x() + (p2.x() - p1.x()) * k // partes
        y = p1.y() + (p2.y() - p1.y()) * k // partes
        mouse(view, QEvent.Type.MouseMove, type(p1)(x, y), Qt.MouseButton.NoButton, izq)
    mouse(view, QEvent.Type.MouseButtonRelease, p2, izq, Qt.MouseButton.NoButton)


def correr():
    from geocad import botones as BOT, imagen_base as IB, modulos, nombre  # noqa: F401
    from osgeo import gdal
    import numpy as np
    QTimerSeguro = QTimer  # noqa: F841

    prj = QgsProject.instance()
    crs = QgsCoordinateReferenceSystem("EPSG:3857")
    prj.setCrs(crs)
    Z = 16
    N = 2 ** Z
    x0 = 21000
    y0 = 37800
    teselas(Z, range(x0, x0 + 6), range(y0, y0 + 6))
    url = "file://%s/t/{z}/{x}/{y}.png" % CARPETA
    base_uri = "type=xyz&url=%s&zmin=%d&zmax=%d&crs=EPSG3857" % (url.replace("{", "%7B").replace("}", "%7D"), Z, Z)
    xyz = QgsRasterLayer(base_uri, "Google", "wms")
    check("capa XYZ local válida", xyz.isValid(), xyz.error().summary())
    check("las teselas cuentan como imagen", IB.capa_es_imagen(xyz), xyz.source())

    # el centro de las 6x6 teselas
    MUNDO = 20037508.342789244
    tam_t = 2 * MUNDO / N
    cx = -MUNDO + (x0 + 3) * tam_t
    cy = MUNDO - (y0 + 3) * tam_t

    lin = QgsVectorLayer("LineString?crs=EPSG:3857", "manzanas", "memory")
    f = QgsFeature()
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(cx - 200, cy), QgsPointXY(cx + 200, cy)]))
    lin.dataProvider().addFeature(f)
    lin.updateExtents()
    from qgis.core import QgsLineSymbol, QgsSingleSymbolRenderer
    lin.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(
        {"line_color": "255,0,255", "line_width": "1.5"})))
    prj.addMapLayers([xyz, lin])
    root = prj.layerTreeRoot()
    root.setCustomLayerOrder([lin, xyz])
    root.setHasCustomLayerOrder(True)
    eventos()

    lay = QgsPrintLayout(prj)
    lay.initializeDefaults()
    lay.setName("banco")
    prj.layoutManager().addLayout(lay)
    mapa = QgsLayoutItemMap(lay)
    mapa.attemptMove(QgsLayoutPoint(40, 30))
    mapa.attemptResize(QgsLayoutSize(150, 100))
    lay.addLayoutItem(mapa)
    mapa.setId("Mapa 1")
    mapa.zoomToExtent(QgsRectangle(cx - 300, cy - 200, cx + 300, cy + 200))
    mapa.setFrameEnabled(True)
    ext0 = IB._tupla(mapa.extent())
    orig_capas = IB.capas_visibles(mapa)
    check("capas de partida (línea arriba)", [c.name() for c in orig_capas] == ["manzanas", "Google"],
          [c.name() for c in orig_capas])

    # ---- la barra, sólo en la composición
    mod = IB.ImagenBaseComposicion(iface)
    d = iface.openLayoutDesigner(lay)
    d.window().resize(1400, 1000)
    d.window().show()
    eventos(60)
    barra = d.window().findChild(QToolBar, IB.OBJETO_BARRA)
    check("barra en la composición", barra is not None)
    check("tres botones", barra is not None and len(barra.actions()) == 3)
    check("la barra no está en la ventana principal",
          iface.mainWindow().findChild(QToolBar, IB.OBJETO_BARRA) is None)

    view = d.view()
    view.zoomFull()
    eventos(60)

    def pos(xmm, ymm):
        return view.mapFromScene(QPointF(xmm, ymm))

    # ---- desplazar
    mod.desplazar(d)
    tool = mod.barras[id(d)]["tool"]
    check("herramienta activa", view.tool() is tool)
    check("botón Desplazar apretado", barra.actions()[0].isChecked())
    p1, p2 = pos(90, 70), pos(100, 75)
    delta_mm = view.mapToScene(p2) - view.mapToScene(p1)

    # lo que se ve sin regenerar debe ser lo mismo que después de regenerar (Fernando, 08/11/2026)
    def pantalla():
        for _ in range(4):
            view.viewport().repaint()
            QTest.qWait(700)
        arriba = view.mapFromScene(QPointF(45, 35))
        abajo = view.mapFromScene(QPointF(185, 125))
        return view.viewport().grab().toImage(), arriba, abajo

    antes_de_mover, a0, a1 = pantalla()       # como en el uso real: el mapa ya está dibujado
    arrastrar(view, p1, p2)
    eventos(60)
    sin_regenerar, a0, a1 = pantalla()
    lay.refresh()
    regenerada, _a, _b = pantalla()
    distintos = total = 0
    for j in range(a0.y(), a1.y(), 3):
        for i in range(a0.x(), a1.x(), 3):
            c1, c2 = sin_regenerar.pixelColor(i, j), regenerada.pixelColor(i, j)
            total += 1
            if abs(c1.red() - c2.red()) + abs(c1.green() - c2.green()) + abs(c1.blue() - c2.blue()) > 45:
                distintos += 1
    check("primer arrastre: se ve igual que regenerando", total > 500 and distintos / total < 0.02, "%d de %d" % (distintos, total))
    lineas.append("     pantalla: %d de %d puntos distintos al regenerar" % (distintos, total))
    movidos = sum(1 for j in range(a0.y(), a1.y(), 3) for i in range(a0.x(), a1.x(), 3)
                  if antes_de_mover.pixelColor(i, j) != sin_regenerar.pixelColor(i, j))
    check("primer arrastre: la imagen se ve corrida enseguida", movidos / total > 0.5, "%d de %d" % (movidos, total))
    check("dos mapas", len(IB.mapas(lay)) == 2)
    base = IB.base_de(mapa)
    check("hay imagen base", base is not None)
    check("el mapa vectorial no se corrió", max(abs(a - b) for a, b in zip(IB._tupla(mapa.extent()), ext0)) < 1e-6)
    check("mapa vectorial sin imagen", [c.name() for c in mapa.layers()] == ["manzanas"])
    check("mapa vectorial sin fondo", not mapa.hasBackground())
    check("mapa vectorial conserva su marco", mapa.frameEnabled())
    check("imagen base sólo teselas", [c.name() for c in base.layers()] == ["Google"])
    check("imagen base trabada contra clics", base.isLocked())
    check("imagen debajo del mapa", base.zValue() < mapa.zValue())
    mup = (ext0[2] - ext0[0]) / mapa.rect().width()
    dx, dy = IB.corrimiento(IB._tupla(mapa.extent()), IB._tupla(base.extent()))
    check("corre X según el arrastre (a la derecha: extensión a la izquierda)",
          cerca(dx, -delta_mm.x() * mup, 1e-3), (dx, -delta_mm.x() * mup))
    check("corre Y según el arrastre", cerca(dy, delta_mm.y() * mup, 1e-3), (dy, delta_mm.y() * mup))
    check("corrimiento guardado", cerca(float(base.customProperty(IB.P_DX)), dx))
    check("sin vista previa pendiente", True)

    # ---- la imagen sigue al mapa con el mismo corrimiento
    mapa.zoomToExtent(QgsRectangle(cx - 150, cy - 100, cx + 150, cy + 100))
    eventos()
    d2x, d2y = IB.corrimiento(IB._tupla(mapa.extent()), IB._tupla(base.extent()))
    check("sigue la extensión", cerca(d2x, dx, 1e-3) and cerca(d2y, dy, 1e-3), (d2x, d2y))
    check("misma escala", cerca(mapa.scale(), base.scale(), 1e-3))
    mapa.attemptMove(QgsLayoutPoint(45, 35))
    eventos()
    check("sigue la posición", cerca(base.pos().x(), mapa.pos().x()) and cerca(base.pos().y(), mapa.pos().y()))
    mapa.attemptResize(QgsLayoutSize(120, 90))
    eventos()
    check("sigue el tamaño", cerca(base.rect().width(), 120) and cerca(base.rect().height(), 90))
    mapa.setMapRotation(12)
    eventos()
    check("sigue el giro", cerca(base.mapRotation(), 12))
    mapa.setMapRotation(0)
    mapa.attemptResize(QgsLayoutSize(150, 100))
    mapa.attemptMove(QgsLayoutPoint(40, 30))
    mapa.zoomToExtent(QgsRectangle(cx - 300, cy - 200, cx + 300, cy + 200))
    eventos()

    # ---- bloquear
    lay.setSelectedItem(mapa)
    eventos()
    previo = IB._tupla(base.extent())
    mod.bloquear(d)
    eventos()
    check("queda bloqueada", IB.bloqueada(base))
    check("candado apretado", barra.actions()[1].isChecked())
    check("al bloquear vuelve a seleccionar", view.tool() is not tool)
    mod.desplazar(d)
    arrastrar(view, pos(90, 70), pos(110, 80))
    eventos()
    check("bloqueada no se mueve", max(abs(a - b) for a, b in zip(IB._tupla(base.extent()), previo)) < 1e-6)
    # sigue al mapa aunque esté bloqueada
    dxb, dyb = IB.corrimiento(IB._tupla(mapa.extent()), IB._tupla(base.extent()))
    check("bloqueada conserva el corrimiento", cerca(dxb, dx, 1e-3) and cerca(dyb, dy, 1e-3))
    mod.bloquear(d)
    eventos()
    check("se destraba", not IB.bloqueada(base) and not barra.actions()[1].isChecked())

    # ---- botón derecho durante el arrastre cancela
    izq, der = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton
    mod.desplazar(d)
    mouse(view, QEvent.Type.MouseButtonPress, pos(90, 70), izq, izq)
    mouse(view, QEvent.Type.MouseMove, pos(120, 90), Qt.MouseButton.NoButton, izq)
    mouse(view, QEvent.Type.MouseButtonPress, pos(120, 90), der, izq | der)
    mouse(view, QEvent.Type.MouseButtonRelease, pos(120, 90), der, izq)
    mouse(view, QEvent.Type.MouseButtonRelease, pos(120, 90), izq, Qt.MouseButton.NoButton)
    check("el derecho cancela", max(abs(a - b) for a, b in zip(IB._tupla(base.extent()), previo)) < 1e-6)

    # ---- recorte y georreferencia: medido píxel por píxel
    def leer(ruta):
        ds = gdal.Open(ruta)
        return ds.ReadAsArray(), ds.GetGeoTransform(), ds.GetProjection()

    lay.renderContext().setDpi(96)
    ruta_a = os.path.join(CARPETA, "sin_correr.tif")
    ruta_b = os.path.join(CARPETA, "corrido.tif")
    plan_a = IB.exportar_recorte(mapa, xyz, ruta_a)
    plan_b = IB.exportar_recorte(mapa, xyz, ruta_b, dx, dy)
    a, gta, _pa = leer(ruta_a)
    b, gtb, prj_b = leer(ruta_b)
    check("GeoTIFF sin errores", not plan_b["errores"], plan_b["errores"])
    check("opaco: tres bandas", b.shape[0] == 3, b.shape)
    check("tamaño según la composición", b.shape[2] == plan_b["ancho"] and b.shape[1] == plan_b["alto"])
    ampliado = IB.ampliar(ext0)
    check("recorte centrado en el mapa vectorial, con el excedente",
          cerca(gtb[0], ampliado[0], 1e-3) and cerca(gtb[3], ampliado[3], 1e-3), (gtb, ampliado))
    area = b.shape[2] * b.shape[1] * gtb[1] ** 2
    area_mapa = (ext0[2] - ext0[0]) * (ext0[3] - ext0[1])
    check("25 % más de área que el recorte", abs(area / area_mapa - 1.25) < 0.005, area / area_mapa)
    check("con el sistema del mapa", QgsCoordinateReferenceSystem.fromWkt(prj_b).authid() == "EPSG:3857", prj_b)
    pasos_x = -dx / gtb[1]
    pasos_y = dy / gtb[1]
    kx, ky = int(round(pasos_x)), int(round(pasos_y))
    mitad_h, mitad_w = b.shape[1] // 2, b.shape[2] // 2
    ventana = 150
    def recorte(arr, ox, oy):
        return arr[:, mitad_h - ventana + oy:mitad_h + ventana + oy, mitad_w - ventana + ox:mitad_w + ventana + ox].astype(int)
    # lo que en A está en (i, j), en B aparece corrido según el arrastre
    dif = np.abs(recorte(b, kx, ky) - recorte(a, 0, 0)).mean()
    otro = np.abs(recorte(b, 0, 0) - recorte(a, 0, 0)).mean()
    check("la imagen está donde se la dejó (píxel a píxel)", dif < 12, "dif=%.2f, sin correr=%.2f, k=(%d,%d)" % (dif, otro, kx, ky))
    check("y no donde estaba", otro > 40, otro)
    lineas.append("     medido: dif %.2f contra %.2f sin corrimiento; k=(%d,%d)" % (dif, otro, kx, ky))

    # archivo anterior intacto si la imagen viene vacía
    with open(ruta_b, "rb") as fh:
        antes = fh.read()
    vacia = QImage(10, 10, QImage.Format.Format_RGBA8888)
    vacia.fill(QColor(0, 0, 0, 0))
    try:
        IB._escribir_geotiff(vacia, {"destino": (0, 0, 10, 10), "tam": 1.0}, crs, ruta_b)
        check("una imagen vacía no se escribe", False)
    except ValueError:
        with open(ruta_b, "rb") as fh:
            check("una imagen vacía no pisa el archivo", fh.read() == antes)
    check("sin temporales", not [n for n in os.listdir(CARPETA) if "geocad-tmp" in n])

    # ---- la composición impresa: vector arriba, imagen corrida abajo
    img = QgsLayoutExporter(lay).renderPageToImage(0, dpi=96)
    fila = int(round((30 + 50) * 96 / 25.4))
    magenta = 0
    for col in range(int(50 * 96 / 25.4), int(180 * 96 / 25.4)):
        for j in range(-4, 5):
            c = img.pixelColor(col, fila + j)
            if c.red() > 200 and c.blue() > 200 and c.green() < 80:
                magenta += 1
                break
    check("la línea vectorial sale encima de la imagen", magenta > 200, magenta)

    # ---- el proyecto guarda y recupera
    ruta_q = os.path.join(CARPETA, "banco.qgs")
    check("proyecto guardado", prj.write(ruta_q))
    d.window().close()
    eventos(30)
    prj.read(ruta_q)
    eventos(30)
    lay3 = prj.layoutManager().layoutByName("banco")
    fr3 = [m for m in IB.mapas(lay3) if m.customProperty(IB.P_BASE)][0]
    ba3 = IB.base_de(fr3)
    check("al abrir sigue la pareja", ba3 is not None and [c.name() for c in fr3.layers()] == ["manzanas"])
    d3x, d3y = IB.corrimiento(IB._tupla(fr3.extent()), IB._tupla(ba3.extent()))
    check("al abrir conserva el corrimiento", cerca(d3x, float(ba3.customProperty(IB.P_DX)), 1e-3))
    d3 = iface.openLayoutDesigner(lay3)
    eventos(30)
    fr3.zoomToExtent(QgsRectangle(cx - 100, cy - 60, cx + 100, cy + 60))
    eventos()
    d4x, _d4y = IB.corrimiento(IB._tupla(fr3.extent()), IB._tupla(ba3.extent()))
    check("al abrir sigue enganchada", cerca(d4x, d3x, 1e-3), (d4x, d3x))

    # ---- deshacer y rehacer, al final: QGIS 4.2.2 se cae por su cuenta al abrir otro proyecto
    # después de Rehacer el agregado de un mapa (medido sin GeoCAD, 08/11/2026)
    mapa4 = QgsLayoutItemMap(lay3)
    mapa4.attemptMove(QgsLayoutPoint(10, 140))
    mapa4.attemptResize(QgsLayoutSize(80, 50))
    lay3.addLayoutItem(mapa4)
    mapa4.zoomToExtent(QgsRectangle(cx - 100, cy - 60, cx + 100, cy + 60))
    eventos()
    pila = lay3.undoStack().stack()
    marca = pila.index()
    base4 = IB.separar(mapa4)
    mod._actualizar(d3)
    eventos()
    check("separar es un solo paso de Deshacer", pila.index() == marca + 1, pila.index() - marca)
    previo = IB._tupla(base4.extent())
    mod.aplicar_arrastre(d3, mapa4, base4, 5, 3)
    eventos()
    check("otro arrastre corre", abs(IB._tupla(IB.base_de(mapa4).extent())[0] - previo[0]) > 1e-3)
    pila.undo()
    eventos()
    check("Deshacer vuelve el arrastre", cerca(IB._tupla(IB.base_de(mapa4).extent())[0], previo[0], 1e-3))
    while pila.index() > marca:
        pila.undo()
        eventos(5)
    check("Deshacer la separación deja el mapa solo", IB.base_de(mapa4) is None and len(IB.mapas(lay3)) == 3,
          len(IB.mapas(lay3)))
    check("vuelven todas las capas y el fondo",
          [c.name() for c in IB.capas_visibles(mapa4)] == ["manzanas", "Google"] and mapa4.hasBackground(),
          [c.name() for c in IB.capas_visibles(mapa4)])
    while pila.canRedo():
        pila.redo()
        eventos(5)
    eventos(30)
    base4 = IB.base_de(mapa4)
    check("Rehacer vuelve los dos mapas", base4 is not None and len(IB.mapas(lay3)) == 4)
    check("Rehacer recupera el arrastre", abs(IB.corrimiento(IB._tupla(mapa4.extent()), IB._tupla(base4.extent()))[0]) > 1e-3
          and pila.index() == pila.count(), (pila.index(), pila.count()))
    lay3.setSelectedItem(mapa4)
    eventos()
    check("Rehacer: imagen debajo", base4 is not None and base4.zValue() < mapa4.zValue())
    d4b = IB.corrimiento(IB._tupla(mapa4.extent()), IB._tupla(base4.extent()))
    mapa4.zoomToExtent(QgsRectangle(cx - 80, cy - 50, cx + 80, cy + 50))
    eventos()
    d4c = IB.corrimiento(IB._tupla(mapa4.extent()), IB._tupla(base4.extent()))
    check("Rehacer: sigue enganchada", cerca(d4b[0], d4c[0], 1e-3) and cerca(d4b[1], d4c[1], 1e-3), (d4b, d4c))

    # ---- Esc: la imagen vuelve a sus coordenadas originales (con la tecla de verdad)
    vista3 = d3.view()
    vista3.zoomFull()
    eventos(30)

    def corrida():
        return IB.corrimiento(IB._tupla(mapa4.extent()), IB._tupla(IB.base_de(mapa4).extent()))

    def esc():
        QTest.keyClick(vista3, Qt.Key.Key_Escape)
        eventos(10)

    mod.desplazar(d3)
    eventos()
    inicial = corrida()
    check("Esc: hay corrimiento para volver", abs(inicial[0]) > 1e-3 and abs(inicial[1]) > 1e-3, inicial)
    mod.bloquear(d3)
    eventos()
    mod.desplazar(d3)
    esc()
    check("Esc: bloqueada no se mueve", cerca(corrida()[0], inicial[0], 1e-3) and cerca(corrida()[1], inicial[1], 1e-3), corrida())
    mod.bloquear(d3)
    eventos()
    ext4 = IB._tupla(mapa4.extent())
    esc()
    check("Esc: vuelve a las coordenadas originales", cerca(corrida()[0], 0, 1e-3) and cerca(corrida()[1], 0, 1e-3), corrida())
    check("Esc: propiedades en cero", cerca(float(IB.base_de(mapa4).customProperty(IB.P_DX)), 0))
    check("Esc: las capas no se movieron", max(abs(a - b) for a, b in zip(IB._tupla(mapa4.extent()), ext4)) < 1e-6)
    check("Esc: sigue la herramienta activa", vista3.tool() is mod.barras[id(d3)]["tool"])
    lay3.undoStack().stack().undo()
    eventos()
    check("Esc: Ctrl+Z recupera el corrimiento", cerca(corrida()[0], inicial[0], 1e-3) and cerca(corrida()[1], inicial[1], 1e-3), corrida())
    izq = Qt.MouseButton.LeftButton
    p_a, p_b = vista3.mapFromScene(QPointF(50, 165)), vista3.mapFromScene(QPointF(60, 170))
    mouse(vista3, QEvent.Type.MouseButtonPress, p_a, izq, izq)
    mouse(vista3, QEvent.Type.MouseMove, p_b, Qt.MouseButton.NoButton, izq)
    esc()
    mouse(vista3, QEvent.Type.MouseButtonRelease, p_b, izq, Qt.MouseButton.NoButton)
    check("Esc en pleno arrastre: vuelve y soltar no corre", cerca(corrida()[0], 0, 1e-3) and cerca(corrida()[1], 0, 1e-3), corrida())

    # ---- primer arrastre con teselas lentas, como Google por internet, sin esperar el dibujo
    import http.server, threading, time

    class Teselas(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(0.25)
            try:
                with open(os.path.join(CARPETA, "t") + self.path.split("?")[0], "rb") as fh:
                    datos = fh.read()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def log_message(self, *_a):
            pass

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Teselas)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    lenta = QgsRasterLayer("type=xyz&url=http://127.0.0.1:%d/%%7Bz%%7D/%%7Bx%%7D/%%7By%%7D.png&zmin=%d&zmax=%d&crs=EPSG3857"
                           % (servidor.server_address[1], Z, Z), "Lenta", "wms")
    check("capa lenta válida", lenta.isValid(), lenta.error().summary())
    prj.addMapLayer(lenta, False)
    lay6 = QgsPrintLayout(prj)
    lay6.initializeDefaults()
    lay6.setName("lenta")
    prj.layoutManager().addLayout(lay6)
    mapa6 = QgsLayoutItemMap(lay6)
    mapa6.attemptMove(QgsLayoutPoint(40, 30))
    mapa6.attemptResize(QgsLayoutSize(150, 100))
    lay6.addLayoutItem(mapa6)
    mapa6.setKeepLayerSet(True)
    mapa6.setLayers([prj.mapLayersByName("manzanas")[0], lenta])
    mapa6.zoomToExtent(QgsRectangle(cx - 300, cy - 200, cx + 300, cy + 200))
    d6 = iface.openLayoutDesigner(lay6)
    d6.window().resize(1400, 1000)
    d6.window().show()
    vista6 = d6.view()
    vista6.zoomFull()

    def foto6(segundos):
        fin = time.time() + segundos
        while time.time() < fin:
            vista6.viewport().repaint()
            QTest.qWait(300)
        return vista6.viewport().grab().toImage()

    def puntos6():
        return vista6.mapFromScene(QPointF(45, 35)), vista6.mapFromScene(QPointF(185, 125))

    antes6 = foto6(9)                      # el mapa ya dibujado, con sus teselas
    mod.desplazar(d6)
    a6, b6 = vista6.mapFromScene(QPointF(90, 70)), vista6.mapFromScene(QPointF(100, 75))
    arrastrar(vista6, a6, b6, partes=2)    # enseguida: la imagen todavía no terminó de dibujarse abajo
    sin6 = foto6(10)
    lay6.refresh()
    con6 = foto6(10)
    v0, v1 = puntos6()
    t6 = c6_dif = c6_mov = 0
    for j in range(v0.y(), v1.y(), 3):
        for i in range(v0.x(), v1.x(), 3):
            p_sin, p_con, p_ant = sin6.pixelColor(i, j), con6.pixelColor(i, j), antes6.pixelColor(i, j)
            t6 += 1
            c6_dif += abs(p_sin.red() - p_con.red()) + abs(p_sin.green() - p_con.green()) + abs(p_sin.blue() - p_con.blue()) > 45
            c6_mov += p_sin != p_ant
    check("lentas: se ve igual que regenerando", t6 > 500 and c6_dif / t6 < 0.02, "%d de %d" % (c6_dif, t6))
    check("lentas: la imagen se ve corrida", c6_mov / t6 > 0.5, "%d de %d" % (c6_mov, t6))
    lineas.append("     lentas: %d distintos al regenerar, %d movidos, de %d" % (c6_dif, c6_mov, t6))
    d6.window().close()
    eventos(30)
    servidor.shutdown()

    # ---- una imagen que no es XYZ (el recorte guardado) también se corre
    ras = QgsRasterLayer(ruta_b, "recorte", "gdal")
    check("recorte como capa", ras.isValid())
    prj.addMapLayer(ras)
    arbol = prj.layerTreeRoot()
    google = prj.mapLayersByName("Google")[0]
    arbol.findLayer(google.id()).setItemVisibilityChecked(False)
    arbol.setHasCustomLayerOrder(True)
    arbol.setCustomLayerOrder([prj.mapLayersByName("manzanas")[0], ras, google])
    eventos()
    mapa5 = QgsLayoutItemMap(lay3)
    mapa5.attemptMove(QgsLayoutPoint(100, 140))
    mapa5.attemptResize(QgsLayoutSize(80, 50))
    lay3.addLayoutItem(mapa5)
    mapa5.zoomToExtent(QgsRectangle(cx - 100, cy - 60, cx + 100, cy + 60))
    eventos()
    check("el ráster se ve en el mapa", [c.name() for c in IB.capas_visibles(mapa5)] == ["manzanas", "recorte"],
          [c.name() for c in IB.capas_visibles(mapa5)])
    base5 = IB.separar(mapa5)
    mod._actualizar(d3)
    eventos()
    check("un ráster también se separa", base5 is not None and [c.name() for c in base5.layers()] == ["recorte"])
    mod.aplicar_arrastre(d3, mapa5, base5, 4, 2)
    eventos()
    check("un ráster también se corre", abs(IB.corrimiento(IB._tupla(mapa5.extent()), IB._tupla(base5.extent()))[0]) > 1e-3)

    # ---- borrar el mapa se lleva su imagen; un solo Ctrl+Z recupera los dos
    uuid5, uuid_b5 = mapa5.uuid(), base5.uuid()
    corrido5 = IB.corrimiento(IB._tupla(mapa5.extent()), IB._tupla(base5.extent()))
    pila5 = lay3.undoStack().stack()
    antes5 = pila5.count()
    cuantos = len(IB.mapas(lay3))
    lay3.setSelectedItem(mapa5)
    eventos()
    vista3.deleteSelectedItems()
    eventos(30)
    check("borrar el mapa borra su imagen", lay3.itemByUuid(uuid5) is None and lay3.itemByUuid(uuid_b5) is None
          and len(IB.mapas(lay3)) == cuantos - 2, len(IB.mapas(lay3)))
    check("borrar es un solo paso de Deshacer", pila5.count() == antes5 + 1, pila5.count() - antes5)
    pila5.undo()
    eventos(30)
    m5 = lay3.itemByUuid(uuid5)
    check("Ctrl+Z recupera el mapa y la imagen", m5 is not None and lay3.itemByUuid(uuid_b5) is not None)
    b5 = IB.base_de(m5)
    c5 = IB.corrimiento(IB._tupla(m5.extent()), IB._tupla(b5.extent()))
    check("recupera el corrimiento", cerca(c5[0], corrido5[0], 1e-3) and cerca(c5[1], corrido5[1], 1e-3), c5)
    check("recupera el orden", b5.zValue() < m5.zValue())
    m5.zoomToExtent(QgsRectangle(cx - 80, cy - 50, cx + 80, cy + 50))
    eventos()
    c6 = IB.corrimiento(IB._tupla(m5.extent()), IB._tupla(b5.extent()))
    check("recuperada sigue al mapa", cerca(c6[0], corrido5[0], 1e-3), c6)

    # ---- la huérfana que dejó la 3.71.0 se va al abrir la composición
    pila5.redo()
    eventos(30)
    huerfana = QgsLayoutItemMap(lay3)
    huerfana.setCustomProperty(IB.P_FRENTE, "{no-existe}")
    huerfana.setLocked(True)
    lay3.addLayoutItem(huerfana)
    eventos()
    check("hay huérfana", len(IB.huerfanas(lay3)) == 1)
    uuid_h = huerfana.uuid()
    d3.window().close()
    eventos(30)
    d3 = iface.openLayoutDesigner(lay3)
    eventos(30)
    check("al abrir se limpia", lay3.itemByUuid(uuid_h) is None and not IB.huerfanas(lay3))

    # ---- un mapa copiado no se queda con la imagen del original
    copia = QgsLayoutItemMap(lay3)
    copia.setCustomProperty(IB.P_BASE, IB.base_de(mapa4).uuid())
    lay3.addLayoutItem(copia)
    check("la copia no tiene la imagen del original", IB.base_de(copia) is None)

    # ---- apagado no deja la barra
    mod.unload()
    eventos()
    check("apagado saca la barra", d3.window().findChild(QToolBar, IB.OBJETO_BARRA) is None or
          not d3.window().findChild(QToolBar, IB.OBJETO_BARRA).isVisible())

    # ---- el banco de Administrar Herramientas y el menú GeoCAD, con el complemento real
    modulos.guardar("qgis", {m.clave: m.defecto for m in modulos.catalogo("qgis")})
    from geocad import classFactory
    plug = classFactory(iface)
    plug.initGui()
    eventos(20)
    plug._cargar_subs()
    eventos(20)
    check("complemento: módulo activo", plug.imagen_base is not None)
    claves = {a.property("geocad_id") for _b, fila in plug._bancos() for a in fila}
    check("en el banco los tres", {"geocad:imgbase_mover", "geocad:imgbase_bloquear", "geocad:imgbase_guardar"} <= claves)
    edicion = [fila for b, fila in plug._bancos() if b == BOT.BANCO + "Edición"][0]
    check("banco Edición", "geocad:imgbase_mover" in [a.property("geocad_id") for a in edicion])
    en_menu = [a.property("geocad_id") for a in plug.menu.actions()]
    check("no están en el menú GeoCAD", not [i for i in en_menu if i and "imgbase" in str(i)], en_menu)
    plug.actions["imgbase_mover"].trigger()
    eventos(10)
    check("la barra aparece también con el complemento",
          d3.window().findChild(QToolBar, IB.OBJETO_BARRA) is not None)
    plug.unload()


def salir():
    try:
        correr()
    except Exception:  # noqa: BLE001
        fallas.append("excepción")
        lineas.append(traceback.format_exc())
    lineas.append("TODO OK" if not fallas else "FALLAS: " + ", ".join(fallas))
    with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as sal:
        sal.write("\n".join(str(x) for x in lineas) + "\n")
    os._exit(0)


QTimer.singleShot(1500, salir)
