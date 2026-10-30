"""Teclado siempre a la línea de comandos (módulo «Teclado», 3.59): pedido de
Fernando del 30/10/2026. Sin Qt: las reglas acordadas (teclado.decidir), qué
widgets no se tocan (teclado.protegido) y el filtro (Teclado.filtrar) con
widgets de mentira; y que los dos programas lo conectan. La ventana real:
COMUN/pruebas/ventana/banco_teclado_ventana.py (IngeCAD) y
banco_teclado_qgis.py (QGIS)."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, filecmp
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ / "QGIS" / "codigo")]
from geocad import teclado as T, modulos

# ================================================================ el módulo
for prog in ("ingecad", "qgis"):
    m = [x for x in modulos.catalogo(prog) if x.clave == "teclado"]
    assert m and m[0].defecto and m[0].cambia_programa, prog      # prendido por defecto
    assert modulos.activo(prog, "teclado"), prog
assert [x for x in modulos.catalogo("qgis") if x.clave == "teclado"][0].requiere == "dibujo"
modulos.guardar("qgis", {"dibujo": False})
assert not modulos.activo("qgis", "teclado")          # sin Dibujo no hay línea de comandos
modulos.guardar("qgis", {"dibujo": True, "teclado": False})
assert not modulos.activo("qgis", "teclado")
modulos.guardar("qgis", {"teclado": True})

# el núcleo es el mismo en los dos lados
for lado in ("QGIS/codigo/geocad", "INGECAD/codigo/geocad"):
    assert filecmp.cmp(RAIZ / "COMUN/nucleo/teclado.py", RAIZ / lado / "teclado.py", shallow=False), lado

# ================================================================ las reglas
d = T.decidir
assert d("", "L", False, False, False)                 # letras
assert d("", "7", False, False, False) and d("", "@", False, False, False)
assert d("", "<", False, False, False) and d("", ",", False, False, False)
assert d("", ";", False, False, False) and d("", "-", False, False, False)
assert d("", "ñ", False, False, False)
assert not d("", "L", True, False, False)              # Ctrl/Alt: atajos
assert not d("", "", False, False, False)              # flechas, Supr, F...: sin texto
assert not d("", "\t", False, False, False) and not d("", "\x7f", False, False, False)
for k in ("Key_Return", "Key_Enter", "Key_Backspace", "Key_Space"):
    txt = {"Key_Space": " ", "Key_Backspace": "\b"}.get(k, "\r")
    assert not d(k, txt, False, False, False), k       # línea vacía: cada lugar lo usa
    assert not d(k, txt, False, False, True), k
    assert d(k, txt, False, True, False), k            # con algo escrito: a la línea
assert not d("Key_Escape", "\x1b", False, False, False)
assert d("Key_Escape", "\x1b", False, True, False)     # borra lo escrito
assert d("Key_Escape", "\x1b", False, False, True)     # cancela el comando
assert not d("Key_Escape", "\x1b", True, True, True)


# ================================================================ Qt de mentira
class Enum:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Qt:
    Key = Enum(Key_Return=0x01000004, Key_Enter=0x01000005, Key_Backspace=0x01000003,
               Key_Space=0x20, Key_Escape=0x01000000, Key_A=0x41, Key_Left=0x01000012)
    KeyboardModifier = Enum(ControlModifier=0x04000000, AltModifier=0x08000000,
                            MetaModifier=0x10000000, ShiftModifier=0x02000000)


class _QEvent:
    Type = Enum(KeyPress=6, ShortcutOverride=51)


class _QObject:
    pass


QtCore = Enum(Qt=_Qt, QEvent=_QEvent, QObject=_QObject)


class Meta:
    def __init__(self, nombres):
        self.n = list(nombres)

    def className(self):
        return self.n[0]

    def superClass(self):
        return Meta(self.n[1:]) if len(self.n) > 1 else None


class W:
    """Widget: clases (de la propia a QWidget), padre, ventana."""
    def __init__(self, clases, padre=None, ventana=False, editable=None, triggers=None):
        self.clases = clases + ["QWidget", "QObject"]
        self.padre = padre
        self.es_ventana = ventana
        self.editable = editable
        self.triggers = triggers
        self.texto = ""
        self.visible = True

    def metaObject(self):
        return Meta(self.clases)

    def isWindow(self):
        return self.es_ventana

    def parentWidget(self):
        return self.padre

    def window(self):
        w = self
        while not w.es_ventana and w.padre is not None:
            w = w.padre
        return w

    def isEditable(self):
        return self.editable

    def editTriggers(self):
        return self.triggers

    def text(self):
        return self.texto

    def isVisible(self):
        return self.visible


class QDockWidget(W):
    pass


class App:
    foco = None
    modal = None
    popup = None

    @staticmethod
    def focusWidget():
        return App.foco

    @staticmethod
    def activeModalWidget():
        return App.modal

    @staticmethod
    def activePopupWidget():
        return App.popup


QtWidgets = Enum(QApplication=App, QDockWidget=QDockWidget)


class Ev:
    def __init__(self, key, text="", mods=0, tipo=6):
        self.k, self.t, self.m, self.tipo = key, text, mods, tipo
        self.aceptado = False

    def key(self):
        return self.k

    def text(self):
        return self.t

    def modifiers(self):
        return self.m

    def type(self):
        return self.tipo

    def accept(self):
        self.aceptado = True


main = W(["QMainWindow"], ventana=True)
linea = W(["QLineEdit"], padre=main)
lienzo = W(["QgsMapCanvas", "QGraphicsView", "QAbstractScrollArea"], padre=main)
capas = W(["QgsLayerTreeView", "QTreeView", "QAbstractItemView"], padre=main, triggers=2 | 8)
capas_ingecad = W(["QTableWidget", "QTableView", "QAbstractItemView"], padre=main, triggers=2)
tabla_atr = W(["QgsAttributeTableView", "QTableView", "QAbstractItemView"], padre=main, triggers=2)
tabla_edita = W(["QTableWidget", "QTableView", "QAbstractItemView"], padre=main, triggers=2 | 16)
celda = W(["QLineEdit"], padre=tabla_atr)
boton = W(["QToolButton", "QAbstractButton"], padre=main)
campo = W(["QLineEdit"], padre=main)
numero = W(["QDoubleSpinBox", "QAbstractSpinBox"], padre=main)
combo_edit = W(["QComboBox"], padre=main, editable=True)
combo = W(["QComboBox"], padre=main, editable=False)
consola = W(["QgsCodeEditorPython", "QgsCodeEditor", "QsciScintilla", "QsciScintillaBase"], padre=main)
texto = W(["QPlainTextEdit"], padre=main)
dock_suelto = QDockWidget(["QDockWidget"], padre=main, ventana=True)
en_suelto = W(["QTreeView", "QAbstractItemView"], padre=dock_suelto, triggers=2)
dialogo = W(["QDialog"], padre=main, ventana=True)
en_dialogo = W(["QPushButton", "QAbstractButton"], padre=dialogo)

# ================================================================ protegido
for w in (campo, numero, combo_edit, consola, texto, tabla_atr, celda, tabla_edita):
    assert T.protegido(w, QtCore), w.clases
for w in (lienzo, capas, capas_ingecad, boton, combo, main, en_suelto):
    assert not T.protegido(w, QtCore), w.clases

# ================================================================ el filtro
entregadas = []
estado = {"comando": False, "propio": set()}
tec = T.Teclado(QtCore, QtWidgets, lambda: main, lambda: linea,
                lambda: estado["comando"], lambda w: w in estado["propio"],
                lambda ev: entregadas.append(ev.text()))
K, M = _Qt.Key, _Qt.KeyboardModifier


def tecla(foco, key=K.Key_A, text="L", mods=0, receptor=None, tipo=6):
    App.foco = foco
    ev = Ev(key, text, mods, tipo)
    antes = len(entregadas)
    r = tec.filtrar(foco if receptor is None else receptor, ev)
    return r, len(entregadas) > antes, ev


# a la línea desde el panel de capas (QGIS e IngeCAD), una barra, el mapa
# con una herramienta de QGIS, una lista no editable, un panel suelto
for w in (capas, capas_ingecad, boton, lienzo, combo, en_suelto):
    r, ent, _ = tecla(w)
    assert r and ent, w.clases
# sin foco (recién cerrado un diálogo): la tecla llega a la ventana
r, ent, _ = tecla(None, receptor=main)
assert r and ent
# la tecla que sube a los padres no se toma dos veces
r, ent, _ = tecla(boton, receptor=main)
assert not r and not ent
# donde se escribe, no se toca
for w in (campo, numero, combo_edit, consola, texto, tabla_atr, celda, tabla_edita, linea):
    r, ent, _ = tecla(w)
    assert not r and not ent, w.clases
# diálogos y ventanas aparte, menús abiertos
r, ent, _ = tecla(en_dialogo)
assert not r and not ent
App.modal = dialogo
r, ent, _ = tecla(boton)
assert not r and not ent
App.modal = None
App.popup = W(["QMenu"], ventana=True)
r, ent, _ = tecla(boton)
assert not r and not ent
App.popup = None
# lo que el programa ya maneja (mapa con herramienta de GeoCAD, dibujo de IngeCAD)
estado["propio"] = {lienzo}
r, ent, _ = tecla(lienzo)
assert not r and not ent
estado["propio"] = set()
# Ctrl / Alt: los atajos siguen
for mod in (M.ControlModifier, M.AltModifier):
    r, ent, _ = tecla(capas, mods=mod)
    assert not r and not ent
r, ent, _ = tecla(capas, mods=M.ShiftModifier, text="@")       # Mayús sí escribe
assert r and ent
# flechas: no
r, ent, _ = tecla(capas, key=K.Key_Left, text="")
assert not r and not ent
# Intro y Espacio: sólo con algo escrito; Esc también con un comando en marcha
r, ent, _ = tecla(capas, key=K.Key_Return, text="\r")
assert not r
r, ent, _ = tecla(boton, key=K.Key_Space, text=" ")
assert not r
linea.texto = "LIN"
r, ent, _ = tecla(boton, key=K.Key_Return, text="\r")
assert r and ent
r, ent, _ = tecla(boton, key=K.Key_Space, text=" ")
assert r and ent
r, ent, _ = tecla(capas, key=K.Key_Escape, text="\x1b")
assert r and ent
linea.texto = ""
r, ent, _ = tecla(capas, key=K.Key_Escape, text="\x1b")
assert not r
estado["comando"] = True
r, ent, _ = tecla(capas, key=K.Key_Escape, text="\x1b")
assert r and ent
estado["comando"] = False
# ShortcutOverride: se acepta (no dispara atajos) y no se entrega dos veces
r, ent, ev = tecla(capas, tipo=51)
assert r and not ent and ev.aceptado
# línea de comandos oculta o sin Dibujo: nada
linea.visible = False
r, ent, _ = tecla(capas)
assert not r and not ent
linea.visible = True
tec.linea = lambda: None
r, ent, _ = tecla(capas)
assert not r and not ent

# ================================================================ conectado
qp = (RAIZ / "QGIS/codigo/geocad/dibujo/plugin.py").read_text(encoding="utf-8")
assert "_modulo('teclado')" in qp and "from ..teclado import Teclado" in qp
assert "self.teclado.instalar()" in qp and "tec.quitar()" in qp
assert "cadDockWidget().cadEnabled()" in qp                 # Digitalización avanzada
ip = (RAIZ / "INGECAD/codigo/geocad/__init__.py").read_text(encoding="utf-8")
assert ip.count("teclado_ingecad.aplicar(") == 2            # al abrir y al cambiar módulos
ti = (RAIZ / "INGECAD/codigo/geocad/teclado_ingecad.py").read_text(encoding="utf-8")
assert "type_ahead(ev)" in ti and '"teclado"' in ti

# ================================================================ botón derecho (3.59.0)
# «boton derecho del maus equivale a enter y a ultimo comando» (Fernando, 30/10/2026).
# IngeCAD: ya lo hace su módulo (dibujo.py, sin depender del foco). QGIS: módulo nuevo
# para las herramientas de QGIS que no dibujan; las de GeoCAD ya lo hacían (CadMapTool).
m = [x for x in modulos.catalogo("qgis") if x.clave == "boton_derecho"]
assert m and m[0].defecto and m[0].requiere == "dibujo" and m[0].cambia_programa
assert modulos.activo("qgis", "boton_derecho")
modulos.guardar("qgis", {"dibujo": False})
assert not modulos.activo("qgis", "boton_derecho")
modulos.guardar("qgis", {"dibujo": True})
assert "_modulo('boton_derecho')" in qp and "ClicDerecho(" in qp and "cd.remove()" in qp
mt = (RAIZ / "QGIS/codigo/geocad/dibujo/maptool.py").read_text(encoding="utf-8")
assert "class ClicDerecho" in mt and "self.mgr.enter()" in mt
assert "'Flag', 'EditTool'" in mt                         # QGIS 4 ya no tiene isEditTool()
cm = (RAIZ / "QGIS/codigo/geocad/dibujo/commands.py").read_text(encoding="utf-8")
assert "if self.last_cmd:" in cm                          # Intro vacío repite el último
dib = (RAIZ / "INGECAD/codigo/geocad/dibujo.py").read_text(encoding="utf-8")
assert 'self.dispatcher.submit("")       # repite la última orden' in dib
assert "_apretar_enter_en_linea(self)" in dib

print("TODO OK test_teclado")
