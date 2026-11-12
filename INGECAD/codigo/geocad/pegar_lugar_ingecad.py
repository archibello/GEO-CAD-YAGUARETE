# SPDX-License-Identifier: GPL-3.0-or-later
"""PEGAR EN EL LUGAR en IngeCAD (3.66.0, GEOPASTEORIG: PASTEORIG / PEGARORIG, Ctrl+Alt+V).

Fernando, 04/11/2026: «crear en IngeCAD la herramienta PEGAR EN COORDENADAS
ORIGINALES en el menú EDIT debajo de PASTE y lo mismo en QGIS»; «ESO ES PEGAR
EN EL LUGAR»; atajo Ctrl+Alt+V.

* Lo copiado en IngeCAD (Ctrl+C, en esta ventana o en otra) se pega en sus
  mismas coordenadas: el Paste de IngeCAD con desplazamiento cero.
* Lo copiado en QGIS (Ctrl+C de objetos) se pega en sus coordenadas, con su
  capa CAD (LAYER_CODE o el nombre de la capa de QGIS), color, tipo y grosor,
  y las capas nuevas con el aspecto de Yaguá Capas, como el Puente.
* Si el dibujo no tiene sistema de coordenadas toma el de QGIS (Fernando:
  «va a crear el mismo de forma automática»); si tiene otro, se reproyecta.
* Al copiar en IngeCAD, GeoCAD agrega al portapapeles el mensaje de
  pegar_lugar.py para que QGIS lo pegue en el lugar.

Las cuentas sin IngeCAD (qué sale de cada objeto, cómo se arma el DXF) se
prueban en test_pegar_lugar.py.
"""
from __future__ import annotations

from tools.base import Tool

from . import modulos, pegar_lugar

PROGRAMA = "ingecad"
NOMBRE = "GEOPASTEORIG"
LIMITE_COPIA = 50000          # más objetos: la copia no se ofrece a QGIS (sería lenta)
_ACCION = "_geocad_pegar_lugar"


# ------------------------------------------------------------------ IngeCAD -> mensaje
def _hex_aci(aci: int) -> str:
    from ezdxf.colors import aci2rgb
    r, g, b = aci2rgb(int(aci))
    return "#%02x%02x%02x" % (r, g, b)


def _color_propio(e):
    """(color, aci) del objeto; (None, None) si es PorCapa."""
    tc = e.dxf.get("true_color")
    if tc is not None:
        from ezdxf.colors import int2rgb
        r, g, b = int2rgb(tc)
        return "#%02x%02x%02x" % (r, g, b), None
    aci = int(e.dxf.get("color", 256))
    if aci in (0, 256):
        return None, None
    return _hex_aci(aci), aci


def _tipo_propio(e):
    lt = e.dxf.get("linetype", "BYLAYER") or "BYLAYER"
    return None if lt.upper() in ("BYLAYER", "BYBLOCK") else lt


def capa_de(doc, nombre: str) -> dict:
    """Color, tipo y grosor de una capa del dibujo, para el mensaje."""
    try:
        lay = doc.layers.get(nombre)
    except Exception:  # noqa: BLE001
        lay = None
    if lay is None:
        return {"color": "#ffffff", "aci": 7, "tipo_linea": "Continuous", "grosor": -1.0}
    tc = lay.dxf.get("true_color")
    if tc is not None:
        from ezdxf.colors import int2rgb
        color, aci = "#%02x%02x%02x" % int2rgb(tc), None
    else:
        aci = abs(int(lay.dxf.get("color", 7))) or 7
        color = _hex_aci(aci)
    grosor = pegar_lugar.mm_de_dxf(lay.dxf.get("lineweight", -3))
    return {"color": color, "aci": aci, "tipo_linea": lay.dxf.get("linetype", "Continuous"),
            "grosor": -1.0 if grosor is None else grosor}


def mensaje_de(entidades, doc, crs: str) -> bytes:
    """El mensaje de pegar_lugar.py con lo copiado en IngeCAD (las cuentas del
    Puente: aqgis.elemento). Los textos no viajan (se cuentan)."""
    from collections import Counter

    from . import aqgis

    objetos, capas, salteados = [], {}, Counter()
    for e in entidades:
        t = e.dxftype()
        if t in ("TEXT", "MTEXT"):
            salteados["texto(s)"] += 1
            continue
        try:
            tipo, dato = aqgis.elemento(e, doc)
        except Exception:  # noqa: BLE001
            tipo, dato = None, t
        if tipo is None or not dato.get("wkt"):
            salteados[str(dato)] += 1
            continue
        color, aci = _color_propio(e)
        nombre = dato.get("capa") or "0"
        objetos.append({"wkt": dato["wkt"], "capa": nombre, "color": color, "aci": aci,
                        "tipo_linea": _tipo_propio(e),
                        "grosor": pegar_lugar.mm_de_dxf(e.dxf.get("lineweight", -1))})
        if nombre not in capas:
            capas[nombre] = capa_de(doc, nombre)
    return pegar_lugar.empaquetar("ingecad", crs, objetos, capas, salteados)


# ------------------------------------------------------------------ mensaje -> IngeCAD
def documento_de(msg: dict, proyectar=None):
    """Un dibujo de ezdxf con los objetos del mensaje en sus coordenadas (o
    llevados por ``proyectar(x, y)``), con las capas y su aspecto."""
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)        # con los tipos de línea estándar
    msp = doc.modelspace()

    def xy(p):
        return proyectar(p[0], p[1]) if proyectar else (p[0], p[1])

    def tipo_ok(nombre):
        return bool(nombre) and nombre in doc.linetypes

    for nombre, props in (msg.get("capas") or {}).items():
        if not nombre or nombre in doc.layers:
            continue
        lay = doc.layers.add(nombre)
        _aplicar_color(lay, props.get("color"), props.get("aci"), defecto=7)
        if tipo_ok(props.get("tipo_linea")):
            lay.dxf.linetype = props["tipo_linea"]
        lay.dxf.lineweight = pegar_lugar.grosor_dxf(props.get("grosor", -1))
    for obj in msg.get("objetos", []):
        capa = obj.get("capa") or "0"
        if capa not in doc.layers:
            doc.layers.add(capa)
        attribs = {"layer": capa}
        tipo, partes = pegar_lugar.partes_wkt(obj.get("wkt", ""))
        nuevos = []
        if tipo == "punto":
            nuevos = [msp.add_point(xy(p), dxfattribs=attribs) for p in partes]
        elif tipo == "linea":
            nuevos = [msp.add_lwpolyline([xy(p) for p in pts], dxfattribs=attribs) for pts in partes]
        elif tipo == "poligono":
            for anillos in partes:
                for anillo in anillos:
                    pts = [xy(p) for p in anillo]
                    if len(pts) > 3 and pts[0] == pts[-1]:
                        pts = pts[:-1]
                    nuevos.append(msp.add_lwpolyline(pts, close=True, dxfattribs=attribs))
        for e in nuevos:
            _aplicar_color(e, obj.get("color"), obj.get("aci"))
            if tipo_ok(obj.get("tipo_linea")):
                e.dxf.linetype = obj["tipo_linea"]
            if obj.get("grosor") is not None:
                e.dxf.lineweight = pegar_lugar.grosor_dxf(obj["grosor"])
    return doc


def _aplicar_color(ent, color, aci, defecto=None):
    if aci:
        ent.dxf.color = int(aci)
        return
    if color:
        from ezdxf.colors import rgb2int
        texto = str(color).lstrip("#")
        try:
            rgb = tuple(int(texto[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            rgb = None
        if rgb is not None:
            if defecto is not None:
                ent.dxf.color = defecto
            ent.dxf.true_color = rgb2int(rgb)
            return
    if defecto is not None:
        ent.dxf.color = defecto


# ------------------------------------------------------------------ el portapapeles
def _portapapeles():
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # noqa: BLE001 -- sin Qt (pruebas)
        return None
    return QApplication.clipboard() if QApplication.instance() is not None else None


def mensaje_en_portapapeles():
    board = _portapapeles()
    return pegar_lugar.leer_copia(board.mimeData() if board is not None else None)


def _hay_copia_ingecad() -> bool:
    try:
        from views import clipboard
    except Exception:  # noqa: BLE001
        return False
    board = _portapapeles()
    data = board.mimeData() if board is not None else None
    return data is not None and data.hasFormat(clipboard.MIME)


def ctrl_v_de_qgis(msg, hay_copia_ingecad: bool, copia_propia_en_curso: bool) -> bool:
    """¿Ctrl+V pega en el lugar lo copiado en QGIS? (3.70.6; Fernando: en los dos sentidos.)
    La copia de esta ventana que todavía se escribe es la última: el portapapeles aún no la muestra."""
    return (msg is not None and msg.get("origen") == "qgis" and not hay_copia_ingecad
            and not copia_propia_en_curso)


# ------------------------------------------------------------------ PEGARORIG
class PegarLugarTool(Tool):
    """PEGARORIG: lo copiado, en sus coordenadas originales."""

    def start(self) -> None:
        self.name = NOMBRE
        msg = mensaje_en_portapapeles()
        if ctrl_v_de_qgis(msg, _hay_copia_ingecad(), False):
            self._de_qgis(msg)
        else:
            self._de_ingecad()
        self.ctx.finish()

    def _documento(self):
        window = getattr(self.ctx.services, "window", None)
        return getattr(window, "document", None)

    def _de_ingecad(self) -> None:
        from core import actions

        services = self.ctx.services
        sources, _base = services.clipboard_data() if services else (None, None)
        if not sources:
            self.ctx.echo("Portapapeles vacío: copie objetos (Ctrl+C) en IngeCAD o en QGIS.")
            return
        originals = getattr(services, "clipboard_originals", None)
        originals = originals() if callable(originals) else None
        comando = actions.PasteCommand(sources, 0.0, 0.0, originals=originals)
        self.ctx.execute(comando)
        self.ctx.echo("Pegado en el lugar: %d objeto(s)." % len(getattr(comando, "copies", sources)))

    def _de_qgis(self, msg: dict) -> None:
        from core import actions

        from . import intercambio

        documento = self._documento()
        doc = getattr(documento, "doc", None)
        destino = intercambio.sistema_del_dibujo(doc) if doc is not None else ""
        definir, reproyectar = pegar_lugar.sistema(destino, msg.get("crs", ""))
        proyectar = None
        if reproyectar:
            try:
                proyectar = intercambio.Proyeccion(msg["crs"], destino).xy
            except Exception as exc:  # noqa: BLE001
                self.ctx.echo("GeoCAD Yaguareté: no se pudo llevar de %s a %s (%s); se pega sin "
                              "reproyectar." % (msg["crs"], destino, exc))
        clip = documento_de(msg, proyectar)
        sources = list(clip.modelspace())
        if not sources:
            self.ctx.echo("Lo copiado en QGIS no tiene objetos que IngeCAD pueda dibujar.")
            return
        comandos = []
        if definir:
            comandos.append(intercambio.DefinirSistemaCommand(definir))
        comandos.append(actions.PasteCommand(sources, 0.0, 0.0, originals=sources))
        if len(comandos) == 1:
            self.ctx.execute(comandos[0])
        else:
            from core.commands import CompositeCommand
            self.ctx.execute(CompositeCommand("PEGARORIG", comandos))
        texto = "Pegado en el lugar: " + pegar_lugar.resumen(msg) + "."
        if definir:
            texto += " El dibujo no tenía sistema de coordenadas: ahora es %s (el de QGIS)." % definir
        elif proyectar is not None:
            texto += " Reproyectado de %s a %s." % (msg["crs"], destino)
        self.ctx.echo(texto)


# ------------------------------------------------------------------ el menú Edit y Ctrl+C
def _menu_editar(window):
    """(menú Edit, acción Paste) de la ventana de IngeCAD, o (None, None)."""
    from PySide6.QtGui import QKeySequence

    pegar = QKeySequence(QKeySequence.StandardKey.Paste)
    # IngeCAD tiene su propia barra de menús (_menu_bar), no la de QMainWindow
    barra = getattr(window, "_menu_bar", None)
    if barra is None and hasattr(window, "menuBar"):
        barra = window.menuBar()
    if barra is None:
        return None, None
    for accion_menu in barra.actions():
        menu = accion_menu.menu()
        if menu is None:
            continue
        for a in menu.actions():
            if a.shortcut() == pegar:
                return menu, a
    return None, None


def _siguiente(menu, accion):
    acciones = menu.actions()
    i = acciones.index(accion)
    return acciones[i + 1] if i + 1 < len(acciones) else None


def _poner_en_menu(window) -> None:
    """El ítem en Edit, debajo de Paste (si no está ya)."""
    accion = getattr(window, _ACCION, None)
    if accion is None:
        return
    menu, pegar = _menu_editar(window)
    if menu is not None and accion not in menu.actions():
        menu.insertAction(_siguiente(menu, pegar), accion)


def _envolver_menus(original):
    def _build_menus(self, *args, **kwargs):
        resultado = original(self, *args, **kwargs)
        try:
            _poner_en_menu(self)        # IngeCAD rearma los menús al prender o apagar un plugin
        except Exception:  # noqa: BLE001
            pass
        try:
            from . import color_menu     # el menú GeoCAD, con su color (también se rearma)
            color_menu.aplicar(self)
        except Exception:  # noqa: BLE001
            pass
        return resultado
    _build_menus._puente_original = original
    _build_menus._puente_fabrica = _envolver_menus
    return _build_menus


def instalar() -> None:
    """Cada vez que IngeCAD rearma sus menús, «Pegar en el lugar» vuelve a Edit."""
    try:
        from views.main_window import MainWindow
    except Exception:  # noqa: BLE001 -- sin la vista de IngeCAD (pruebas)
        return
    from .dibujo import envolver
    if getattr(MainWindow._build_menus, "_puente_fabrica", None) is not _envolver_menus:
        envolver(MainWindow, "_build_menus", _envolver_menus, reemplazar=True)


def _al_copiar(window) -> None:
    """Cuando IngeCAD deja una copia suya en el portapapeles, agrega el mensaje
    para QGIS (sin tocar lo de IngeCAD: su Paste sigue igual)."""
    try:
        from views import clipboard
    except Exception:  # noqa: BLE001
        return
    board = _portapapeles()
    data = board.mimeData() if board is not None else None
    if data is None or not data.hasFormat(clipboard.MIME):
        return
    clip_id = bytes(data.data(clipboard.ID_MIME)).decode("ascii", "replace")
    if not clip_id.startswith(getattr(clipboard, "_PROCESS", "")):
        return                                  # la copia es de otra ventana: la completa ella
    try:
        sources, _base = clipboard.read_dxf(bytes(data.data(clipboard.MIME)))
        if not sources or len(sources) > LIMITE_COPIA:
            return
        from . import aqgis
        crs = aqgis.crs_del_dibujo(window.document)
        extra = mensaje_de(sources, sources[0].doc, crs)
    except Exception:  # noqa: BLE001 -- ante cualquier duda, la copia queda como la dejó IngeCAD
        return
    # el portapapeles no se vuelve a escribir: ver nucleo/pegar_lugar.py
    pegar_lugar.dejar_copia(extra, data, clipboard.ID_MIME)


def _soltar_copia(window, board) -> None:
    conexion = getattr(window, _ACCION + "_copia", None)
    if conexion is not None and board is not None:
        try:
            board.dataChanged.disconnect(conexion)
        except Exception:  # noqa: BLE001
            pass
        setattr(window, _ACCION + "_copia", None)


def aplicar(window) -> None:
    """Pone o quita «Pegar en el lugar» en el menú Edit (debajo de Paste, Ctrl+Alt+V)
    y la copia para QGIS, según el módulo (al abrir y al cambiar los módulos)."""
    if window is None:
        return
    try:
        from PySide6.QtGui import QAction, QKeySequence
    except Exception:  # noqa: BLE001
        return
    quiere = modulos.activo(PROGRAMA, "pegar_lugar")
    accion = getattr(window, _ACCION, None)
    board = _portapapeles()
    if not quiere:
        if accion is not None:
            for w in accion.associatedObjects() if hasattr(accion, "associatedObjects") else ():
                try:
                    w.removeAction(accion)
                except Exception:  # noqa: BLE001
                    pass
            accion.deleteLater()
            setattr(window, _ACCION, None)
        _soltar_copia(window, board)
        pegar_lugar.borrar_copia()
        return
    if accion is None:
        try:
            from core.i18n import tr
        except Exception:  # noqa: BLE001
            tr = str
        accion = QAction(tr("Paste in Place"), window)
        accion.setObjectName("geocad_pegar_lugar")
        accion.setShortcut(QKeySequence(pegar_lugar.ATAJO))
        accion.setToolTip(tr("Paste in Place (PASTEORIG)"))
        accion.triggered.connect(lambda _=False: window._invoke_command(NOMBRE))
        setattr(window, _ACCION, accion)
        _poner_en_menu(window)
        viewport = getattr(window, "viewport", None)
        if viewport is not None:
            viewport.addAction(accion)
        window.addAction(accion)
    if board is not None:
        # siempre de nuevo: al actualizar sin reiniciar, la ventana conserva la de la versión anterior
        _soltar_copia(window, board)

        def conexion(w=window):
            _al_copiar(w)
        board.dataChanged.connect(conexion)
        setattr(window, _ACCION + "_copia", conexion)
