"""Banco con la APLICACIÓN QGIS real (sin pantalla): Ver > Herramientas GeoCAD y el
formulario de espacios de Administrar Herramientas, con el complemento de verdad.

Corre dentro de QGIS con --code (el código de geocad, en una carpeta sin espacios):
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=BANCO_SALIDA=<carpeta>/real.txt --env=BANCO_CODIGO=<carpeta con geocad> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
Deja el resultado en BANCO_SALIDA; termina en «TODO OK».
"""
import os, sys, tempfile, traceback
from qgis.core import QgsPrintLayout, QgsProject
from qgis.PyQt.QtCore import QCoreApplication, QPoint, QTimer
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QComboBox, QListWidget, QPushButton, QScrollArea, QToolBar, QWidgetAction
from qgis.utils import iface

sys.path.insert(0, os.environ["BANCO_CODIGO"])
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")   # no pisar la copia de Fernando
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


def composicion(nombre):
    lay = QgsPrintLayout(QgsProject.instance())
    lay.initializeDefaults()
    lay.setName(nombre)
    QgsProject.instance().layoutManager().addLayout(lay)
    d = iface.openLayoutDesigner(lay)
    d.window().show()
    QTest.qWait(300)
    eventos()
    return d


def correr():
    from geocad import botones as botones_mod, botones_ui, classFactory, espacios as E, imagen_base as IB, modulos

    modulos.guardar("qgis", {m.clave: m.defecto for m in modulos.catalogo("qgis")})
    plug = classFactory(iface)
    plug.initGui()
    QTest.qWait(300)
    plug._cargar_subs()
    eventos()
    d = composicion("uno")
    win = d.window()

    # 3.72.3 (Fernando): Pegar y Copiar tabla, fuera del menú y a mano en la composición
    menu_geocad = [a.text() for a in plug.menu.actions()]
    check("módulo Tablas activo", plug.tablas is not None)
    check("sin Pegar ni Copiar tabla en el menú GeoCAD",
          not any(t.startswith(("Pegar tabla", "Copiar la tabla")) for t in menu_geocad), menu_geocad)
    ids_bancos = [a.property("geocad_id") for _n, fila in plug._bancos() for a in fila]
    check("Pegar y Copiar tabla de respaldo en los bancos",
          "geocad:pegartabla" in ids_bancos and "geocad:copiartabla" in ids_bancos)
    check("Pegar tabla sigue en la composición",
          any(a.text().startswith("Pegar tabla") for b in win.findChildren(QToolBar) for a in b.actions()))

    def boton(clave):
        return plug.espacios._botones(win)["geocad:" + clave]

    def submenu():
        return plug.espacios.menus[id(d)][2]

    def titulos():
        plug.espacios._pintar(d)
        return [a.text() for a in submenu().actions()]

    def barra_modelo():
        return iface.mainWindow().findChild(QToolBar, E.OBJETO_BARRA_MODELO)

    def en_principal(b):
        accion = plug._acciones_por_boton()[b]
        return [x.windowTitle() for x in iface.mainWindow().findChildren(QToolBar)
                if accion in x.actions() and x.objectName() != E.OBJETO_BARRA_MODELO]

    # ---- el menú, justo debajo de Barras de herramientas
    ver = plug.espacios.menus[id(d)][1]
    lista = ver.actions()
    i = next(n for n, a in enumerate(lista) if a.menu() is not None and a.menu().objectName() == E.OBJETO_MENU_BARRAS)
    check("Herramientas GeoCAD debajo de Barras de herramientas", lista[i + 1].menu() is submenu())
    nativas = E.IDS_NATIVAS
    check("de fábrica las cinco, con casilla", len(titulos()) == 5, titulos())
    check("todas tildadas", all(a.isChecked() and a.isCheckable() for a in submenu().actions()))

    # ---- la casilla muestra y oculta, sin cambiar de espacio
    submenu().actions()[0].setChecked(False)
    eventos()
    check("destildar oculta el botón", not boton("imgbase_mover").isVisible())
    check("queda guardado", nativas[0] in E.leer()["ocultas"] and E.leer()["espacios"] == {})
    for n in (1, 2):
        titulos()
        submenu().actions()[n].setChecked(False)
    eventos()
    barra_img = win.findChild(QToolBar, IB.OBJETO_BARRA)
    check("sin botones, la barra se esconde", not barra_img.isVisible())
    for n in (0, 1, 2):
        titulos()
        submenu().actions()[n].setChecked(True)
    eventos()
    check("al volver, la barra vuelve", barra_img.isVisible() and boton("imgbase_mover").isVisible())

    # ---- el formulario sigue a la categoría elegida (con los botones de verdad)
    respuesta = {"cambios": {}, "toda": None, "acepta": True}
    vistos = {}

    def contestar(dlg):
        combos = {c.objectName(): c for c in dlg.findChildren(QComboBox)}
        vistos.clear()
        vistos.update({n: c for n, c in combos.items() if n != "toda"})
        vistos["__titulo"] = dlg.windowTitle()
        vistos["__opciones"] = [combos["toda"].itemText(k) for k in range(combos["toda"].count())]
        if respuesta.get("medir"):              # Fernando: los selectores quedaban fuera de la ventana
            dlg.show()
            QTest.qWait(150)
            area = dlg.findChild(QScrollArea)
            puerto = area.viewport()
            medidos = [c for n, c in combos.items() if n != "toda"]
            vistos["__fuera"] = [c.objectName() for c in medidos
                                 if c.mapTo(puerto, QPoint(c.width(), 0)).x() > puerto.width()]
            vistos["__scroll"] = area.horizontalScrollBar().isVisible()
            vistos["__cuantos"] = len(medidos)
            respuesta["medido"] = dict(vistos)
            dlg.hide()
        if respuesta["toda"]:
            combos["toda"].setCurrentIndex(combos["toda"].findData(respuesta["toda"]))
        for nombre, valor in respuesta["cambios"].items():
            combos[nombre].setCurrentIndex(combos[nombre].findData(valor))
        return 1 if respuesta["acepta"] else 0

    E._exec = contestar
    cats = plug._categorias_barras()
    linea = "dibujo:line"
    cat_linea = next(n for n, f in cats if linea in f)
    ids_linea = next(f for n, f in cats if n == cat_linea)
    check("hay una categoría con la línea", len(ids_linea) > 1, cats)

    def por_administrar(fila, acepta=True, cambios=None, toda=None, banco=False, medir=False):
        """Administrar Herramientas: elegir la categoría o el banco y apretar el botón."""
        respuesta.update(cambios=cambios or {}, toda=toda, acepta=acepta, medir=medir)

        def mirar(dlg):
            listas = [l for l in dlg.findChildren(QListWidget) if l.count()]
            lista_c = next(l for l in listas if l.toolTip().startswith("Bancos") == banco)
            lista_c.setCurrentRow(fila)
            eventos(3)
            next(b for b in dlg.findChildren(QPushButton) if b.text() == "Espacio de cada herramienta...").click()
            return 0

        botones_ui._exec = mirar
        plug.administrar_botones()
        eventos()

    fila_linea = [n for n, _f in cats].index(cat_linea)
    por_administrar(fila_linea, acepta=False)
    check("el formulario es de la categoría elegida", cat_linea in str(vistos["__titulo"]), vistos["__titulo"])
    check("lista sus herramientas, no las cinco fijas",
          set(k for k in vistos if not k.startswith("__")) == set(ids_linea), sorted(k for k in vistos if not k.startswith("__")))
    check("en cada una los dos espacios y «toda la categoría»",
          vistos["__opciones"][1:] == ["Espacio Presentaciones", "Espacio Modelo"])
    check("una de dibujo arranca en Modelo", vistos[linea].currentData() == E.MODELO)
    check("Cancelar no cambia nada", E.leer()["espacios"] == {})

    # ---- con los nombres largos del banco Edición, cada selector se ve
    bancos = [n for n, _f in plug._bancos()]
    por_administrar(bancos.index("banco:Edición"), acepta=False, banco=True, medir=True)
    m = respuesta["medido"]
    lineas.append("     banco Edición: %d herramientas, fuera de la vista %d, barra horizontal %s"
                  % (m["__cuantos"], len(m["__fuera"]), m["__scroll"]))
    check("banco Edición: es del banco elegido", "Edición" in str(m["__titulo"]) and m["__cuantos"] > 10, m["__titulo"])
    check("cada selector queda a la vista", m["__fuera"] == [], m["__fuera"][:5])
    check("sin barra horizontal", m["__scroll"] is False)

    # ---- una herramienta común a Espacio Presentaciones
    check("antes está en la ventana principal o en su banco", True)
    por_administrar(fila_linea, cambios={linea: E.PRESENTACION})
    QTest.qWait(50)
    eventos()
    propias = [b for b in win.findChildren(QToolBar) if b.objectName() == E.PREFIJO_BARRA + cat_linea]
    check("barra en la presentación con el nombre de la categoría", len(propias) == 1 and propias[0].windowTitle() == cat_linea,
          [b.objectName() for b in win.findChildren(QToolBar)])
    check("con su botón", linea in plug.espacios._botones(win) and plug.espacios._botones(win)[linea].isVisible())
    check("sale de la ventana principal", en_principal(linea) == [], en_principal(linea))
    check("aparece en el menú Ver", any("ine" in t or "ínea" in t for t in titulos()) and len(titulos()) == 6, titulos())
    disparos = []
    plug._acciones_por_boton()[linea].triggered.connect(lambda *_: disparos.append(1))
    plug.espacios._botones(win)[linea].trigger()
    eventos()
    check("desde la presentación lanza la herramienta", disparos == [1], disparos)
    try:
        from geocad.dibujo import plugin as _dp  # noqa: F401
        iface.mapCanvas().unsetMapTool(iface.mapCanvas().mapTool())
    except Exception:  # noqa: BLE001
        pass

    # un botón de la casilla Ver la oculta también
    ultimo = len(titulos()) - 1
    submenu().actions()[ultimo].setChecked(False)
    eventos()
    check("Ver oculta también las de la categoría", not plug.espacios._botones(win)[linea].isVisible())
    titulos()
    submenu().actions()[ultimo].setChecked(True)
    eventos()

    # y una presentación nueva la trae
    d2 = composicion("dos")
    QTest.qWait(100)
    eventos()
    check("la presentación nueva la trae", linea in plug.espacios._botones(d2.window()))
    d2.window().close()
    eventos()

    # toda la categoría de una vez, y de vuelta a Modelo
    por_administrar(fila_linea, toda=E.PRESENTACION)
    QTest.qWait(50)
    eventos()
    propios = E.leer()["espacios"]
    combos_sueltos = [b for b, a in plug._acciones_por_boton().items() if isinstance(a, QWidgetAction)]
    check("toda la categoría pasa junta", all(propios.get(b) == E.PRESENTACION for b in ids_linea if b not in combos_sueltos), propios)
    por_administrar(fila_linea, toda=E.MODELO)
    QTest.qWait(50)
    eventos()
    check("de vuelta en Modelo sale de la presentación",
          [b for b in win.findChildren(QToolBar) if b.objectName() == E.PREFIJO_BARRA + cat_linea] == [])
    check("y vuelve a la ventana principal o a su categoría", linea not in plug.espacios._botones(win))
    ahora = plug._categorias_barras()
    check("la categoría sigue igual", next(f for n, f in ahora if n == cat_linea) == ids_linea)

    # ---- una lista desplegable sólo puede estar en Modelo
    if combos_sueltos:
        lista_d = combos_sueltos[0]
        fila_d = next((k for k, (_n, f) in enumerate(ahora) if lista_d in f), None)
        if fila_d is not None:
            por_administrar(fila_d, acepta=False)
            check("una lista desplegable queda fija en Modelo",
                  vistos[lista_d].currentData() == E.MODELO and not vistos[lista_d].isEnabled())

    # ---- una nativa: puesta en una categoría propia del usuario, como Fernando
    nuevo_modelo = plug._categorias_barras()
    mi = [[n, [[b, True] for b in f]] for n, f in nuevo_modelo] + [["Presentaciones Imagenes", [["geocad:imgbase_mover", True]]]]
    fabrica = plug._fabrica_botones()
    botones_mod.guardar("qgis", [(n, [tuple(x) for x in f]) for n, f in mi], fabrica, ())
    plug._aplicar_botones(mostrar=True)
    eventos()
    check("sin elección explícita sigue en su barra principal", "Presentaciones Imagenes" in en_principal(nativas[0]), en_principal(nativas[0]))
    check("y en la presentación", boton("imgbase_mover").isVisible())
    fila_mi = [n for n, _f in plug._categorias_barras()].index("Presentaciones Imagenes")
    por_administrar(fila_mi, cambios={nativas[0]: E.PRESENTACION})
    QTest.qWait(50)
    eventos()
    check("elegida Presentaciones sale de la principal", en_principal(nativas[0]) == [], en_principal(nativas[0]))
    por_administrar(fila_mi, cambios={nativas[0]: E.MODELO})
    QTest.qWait(50)
    eventos()
    check("elegida Modelo vuelve a su categoría", "Presentaciones Imagenes" in en_principal(nativas[0]), en_principal(nativas[0]))
    check("sale de la presentación", not boton("imgbase_mover").isVisible())
    check("en su categoría no usa la barra suelta", barra_modelo() is None or not barra_modelo().isVisible())
    plug.actions["imgbase_mover"].trigger()
    eventos()
    check("desde Modelo activa la herramienta", d.view().tool() is plug.imagen_base.barras[id(d)]["tool"])

    # sin categoría, una nativa en Modelo usa la barra suelta
    botones_mod.restablecer("qgis")
    plug._aplicar_botones(mostrar=True)
    eventos()
    check("sin categoría usa la barra suelta", barra_modelo() is not None and barra_modelo().isVisible()
          and nativas[0] in [a.property("geocad_id") for a in barra_modelo().actions()],
          barra_modelo() and [a.property("geocad_id") for a in barra_modelo().actions()])

    # ---- módulo apagado: su herramienta no se ofrece y los archivos siguen
    E.archivo().unlink()
    modulos.guardar("qgis", {"imagen_base": False})
    plug.aplicar_modulos()
    QTest.qWait(100)
    eventos()
    check("módulo apagado: sale del menú", len(titulos()) == 2, titulos())
    modulos.guardar("qgis", {"imagen_base": True})
    plug.aplicar_modulos()
    QTest.qWait(100)
    eventos()
    check("módulo prendido: vuelve", len(titulos()) == 5, titulos())

    # ---- apagado no deja rastro
    plug.unload()
    eventos()
    check("descargado: sale el submenú", [a for a in ver.actions() if a.text() == "Herramientas GeoCAD"] == [])
    check("descargado: sin barra principal", barra_modelo() is None or not barra_modelo().isVisible())


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
