"""El cursor de GeoCAD por defecto en QGIS (módulo «Cursor de GeoCAD», 3.67): pedido de
Fernando del 05/11/2026. Sin Qt: el módulo, cuándo se activa, qué hace Esc y el filtro,
con objetos de mentira; y que Dibujo lo conecta. Con QGIS de verdad:
COMUN/pruebas/ventana/banco_cursor_qgis_real.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import filecmp, os, sys, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ / "QGIS" / "codigo")]
from geocad import cursor_defecto as C, modulos

# ================================================================ el módulo
m = [x for x in modulos.catalogo("qgis") if x.clave == "cursor_geocad"]
assert m and m[0].defecto and m[0].cambia_programa and m[0].requiere == "dibujo"
assert not [x for x in modulos.catalogo("ingecad") if x.clave == "cursor_geocad"]   # sólo QGIS
assert modulos.activo("qgis", "cursor_geocad")
modulos.guardar("qgis", {"dibujo": False})
assert not modulos.activo("qgis", "cursor_geocad")     # sin Dibujo no hay cursor
modulos.guardar("qgis", {"dibujo": True, "cursor_geocad": False})
assert not modulos.activo("qgis", "cursor_geocad")
modulos.guardar("qgis", {"cursor_geocad": True})
for lado in ("QGIS/codigo/geocad", "INGECAD/codigo/geocad"):
    assert filecmp.cmp(RAIZ / "COMUN/nucleo/modulos.py", RAIZ / lado / "modulos.py", shallow=False), lado


# ================================================================ Qt y QGIS de mentira
class Enum:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Qt:
    Key = Enum(Key_Return=0x01000004, Key_Enter=0x01000005, Key_Backspace=0x01000003,
               Key_Space=0x20, Key_Escape=0x01000000, Key_A=0x41)
    KeyboardModifier = Enum(ControlModifier=0x04000000, AltModifier=0x08000000,
                            MetaModifier=0x10000000)


class _QEvent:
    Type = Enum(KeyPress=6, ShortcutOverride=51)


class _QTimer:
    pendientes = []

    @staticmethod
    def singleShot(_ms, fn):
        _QTimer.pendientes.append(fn)


class _QObject:
    pass


QtCore = Enum(Qt=_Qt, QEvent=_QEvent, QObject=_QObject, QTimer=_QTimer)


def correr_timers():
    while _QTimer.pendientes:
        _QTimer.pendientes.pop(0)()


class Senal:
    def __init__(self):
        self.fns = []

    def connect(self, fn):
        self.fns.append(fn)

    def disconnect(self, fn):
        self.fns.remove(fn)

    def emit(self, *a):
        for fn in list(self.fns):
            fn(*a)


class Meta:
    def __init__(self, nombres):
        self.n = list(nombres)

    def className(self):
        return self.n[0]

    def superClass(self):
        return Meta(self.n[1:]) if len(self.n) > 1 else None


class W:
    def __init__(self, clase, padre=None):
        self.clases = [clase, "QWidget", "QObject"]
        self.padre = padre

    def metaObject(self):
        return Meta(self.clases)

    def isWindow(self):
        return self.padre is None

    def parentWidget(self):
        return self.padre

    def window(self):
        return self if self.padre is None else self.padre.window()

    def viewport(self):
        return self.vp


class App:
    foco = None
    modal = None
    popup = None

    @staticmethod
    def instance():
        return App

    @staticmethod
    def installEventFilter(_f):
        pass

    @staticmethod
    def removeEventFilter(_f):
        pass

    @staticmethod
    def focusWidget():
        return App.foco

    @staticmethod
    def activeModalWidget():
        return App.modal

    @staticmethod
    def activePopupWidget():
        return App.popup


class QDockWidget:
    pass


QtWidgets = Enum(QApplication=App, QDockWidget=QDockWidget)


class Accion:
    def __init__(self):
        self.disparos = 0

    def trigger(self):
        self.disparos += 1
        canvas.setMapTool(tools[self])


class Tool:
    def __init__(self, accion=None):
        self._accion = accion

    def action(self):
        return self._accion


class Canvas(W):
    def __init__(self, padre):
        super().__init__("QgsMapCanvas", padre)
        self.vp = W("QWidget", self)
        self.mapToolSet = Senal()
        self.tool = None
        self.dibujando = False
        self.parados = 0

    def mapTool(self):
        return self.tool

    def setMapTool(self, t):
        vieja, self.tool = self.tool, t
        self.mapToolSet.emit(t, vieja)

    def isDrawing(self):
        return self.dibujando

    def stopRendering(self):
        self.parados += 1


class Capa:
    def __init__(self, n):
        self.n = n

    def selectedFeatureCount(self):
        return self.n

    def removeSelection(self):
        self.n = 0


ventana = W("QMainWindow")
canvas = Canvas(ventana)
panel = W("QgsLayerTreeView", ventana)
linea = W("QLineEdit", ventana)
campo = W("QLineEdit", ventana)
otra = W("QDialog")

a_pan, a_ident, a_sel, a_add, a_medir = Accion(), Accion(), Accion(), Accion(), Accion()
tools = {a: Tool(a) for a in (a_pan, a_ident, a_sel, a_add, a_medir)}
cad, texto = Tool(), Tool()


class Iface:
    initializationCompleted = Senal()
    newProjectCreated = Senal()
    projectRead = Senal()

    def mapCanvas(self):
        return canvas

    def mainWindow(self):
        return ventana

    def actionPan(self):
        return a_pan

    def actionIdentify(self):
        return a_ident

    def actionSelect(self):
        return a_sel


class Mgr:
    command = None
    tool = cad
    _switching = False
    esc_en_reposo = None


class CmdLine:
    input = linea

    def __init__(self):
        self.ecos = []
        self.feeds = []

    def echo(self, t):
        self.ecos.append(t)

    def feed_key(self, ev):
        self.feeds.append(ev)


class Ev:
    def __init__(self, key=_Qt.Key.Key_Escape, tipo=6, mods=0):
        self.k, self.t, self.m, self.aceptado = key, tipo, mods, False

    def key(self):
        return self.k

    def type(self):
        return self.t

    def modifiers(self):
        return self.m

    def text(self):
        return "\x1b"

    def accept(self):
        self.aceptado = True


iface, mgr, cl = Iface(), Mgr(), CmdLine()
capas = [Capa(3), Capa(2), Capa(0)]
canvas.tool = tools[a_pan]
c = C.CursorDefecto(iface, mgr, cl, [cad, texto], lambda: capas, QtCore, QtWidgets)

# ================================================================ cuándo se activa
c.instalar()
assert canvas.mapTool() is cad and mgr.esc_en_reposo == c.esc_reposo     # al abrir QGIS
assert not mgr._switching

canvas.setMapTool(tools[a_ident])                      # la elegida se respeta
correr_timers()
assert canvas.mapTool() is tools[a_ident]
for senal in (iface.newProjectCreated, iface.projectRead, iface.initializationCompleted):
    canvas.setMapTool(tools[a_pan])
    senal.emit()
    assert canvas.mapTool() is tools[a_pan]            # todavía no: QGIS pone Desplazar después
    correr_timers()
    assert canvas.mapTool() is cad
iface.projectRead.emit(); correr_timers()
assert canvas.mapTool() is cad
canvas.setMapTool(None)                                # el mapa sin herramienta
correr_timers()
assert canvas.mapTool() is cad
canvas.setMapTool(texto)                               # otra herramienta de GeoCAD: no se pisa
iface.projectRead.emit(); correr_timers()
assert canvas.mapTool() is texto
canvas.setMapTool(tools[a_pan])                        # un comando en marcha: no se pisa
mgr.command = object()
iface.newProjectCreated.emit(); correr_timers()
assert canvas.mapTool() is tools[a_pan]
mgr.command = None

# ================================================================ Esc en reposo
capas[:] = [Capa(3), Capa(2), Capa(0)]
c.esc_reposo()                                         # con Desplazar: limpia todas y vuelve
assert [x.n for x in capas] == [0, 0, 0] and canvas.mapTool() is cad
assert cl.ecos == ["*Cancelar*"]
c.esc_reposo()
assert cl.ecos == ["*Cancelar*"]                       # sin selección no dice nada
capas[0].n = 3
canvas.setMapTool(tools[a_add])                        # Agregar entidad: no está en la lista
c.esc_reposo()
assert capas[0].n == 0 and canvas.mapTool() is tools[a_add]
canvas.dibujando = True                                # lo que Esc hace en QGIS sigue andando
c.esc_reposo()
assert canvas.parados == 1
canvas.dibujando = False


# ================================================================ el filtro
def apretar(receptor, foco=None, **kw):
    App.foco = receptor if foco is None else foco
    cl.feeds.clear()
    ev = Ev(**kw)
    return c.esc.filtrar(receptor, ev), ev


for herramienta in (a_pan, a_ident, a_sel):
    canvas.setMapTool(tools[herramienta])
    for w in (canvas, canvas.vp, panel):
        tomada, ev = apretar(w)
        assert tomada and cl.feeds == [ev], (herramienta, w)
canvas.setMapTool(tools[a_add])                        # Agregar entidad / Medir: el mapa es de QGIS
assert not apretar(canvas)[0] and apretar(panel)[0]
canvas.setMapTool(tools[a_medir])
assert not apretar(canvas)[0] and apretar(panel)[0]
canvas.setMapTool(cad)                                 # GeoCAD: ya lo maneja KeyGuard
assert not apretar(canvas)[0] and apretar(panel)[0]
canvas.setMapTool(tools[a_pan])
assert not apretar(linea)[0]                           # la línea de comandos lo maneja sola
assert not apretar(campo)[0]                           # un campo de texto, no
assert not apretar(W("QTextEdit", ventana))[0]         # donde se escribe, no
assert not apretar(W("QAbstractSpinBox", ventana))[0]
assert not apretar(otra)[0]                            # otra ventana, no
assert not apretar(panel, mods=_Qt.KeyboardModifier.ControlModifier)[0]
assert not apretar(panel, key=_Qt.Key.Key_A)[0]
assert not apretar(panel, foco=canvas)[0]              # sólo la primera entrega
App.modal = otra
assert not apretar(panel)[0]
App.modal = None
App.popup = otra
assert not apretar(panel)[0]
App.popup = None
tomada, ev = apretar(panel, tipo=51)                   # ShortcutOverride: es nuestra, sin entregar
assert tomada and ev.aceptado and not cl.feeds

# ================================================================ apagado, como venía
canvas.setMapTool(cad)
c.quitar()
assert a_pan.disparos == 1 and canvas.mapTool() is tools[a_pan] and mgr.esc_en_reposo is None
assert not canvas.mapToolSet.fns and not iface.projectRead.fns and not iface.newProjectCreated.fns
assert not iface.initializationCompleted.fns
canvas.setMapTool(None); correr_timers()
assert canvas.mapTool() is None                        # ya no se activa
c.activar()
assert canvas.mapTool() is None

# ================================================================ Dibujo lo conecta
qp = (RAIZ / "QGIS/codigo/geocad/dibujo/plugin.py").read_text(encoding="utf-8")
assert "_modulo('cursor_geocad')" in qp and "cur.quitar()" in qp
cm = (RAIZ / "QGIS/codigo/geocad/dibujo/commands.py").read_text(encoding="utf-8")
assert "self.esc_en_reposo()" in cm

print("TODO OK test_cursor_qgis")
