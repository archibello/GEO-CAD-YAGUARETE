# SPDX-License-Identifier: GPL-3.0-or-later
"""La ventana «Administrar botones» (3.38.0), desde el menú GeoCAD.

Sirve a los dos programas: IngeCAD le pasa PySide6.QtWidgets y QGIS
qgis.PyQt.QtWidgets (misma forma de uso). A la izquierda las categorías
(cada una, una barra); a la derecha sus botones: la casilla los muestra u
oculta, las flechas los ordenan y «Pasar a» los lleva a otra categoría.
Aceptar va arriba, como en Módulos.
"""
from __future__ import annotations

from . import botones


def _exec(dialog):
    run = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    return run()


class Ventana:
    """El estado de la ventana, aparte de los widgets (se prueba sin Qt)."""

    def __init__(self, modelo):
        self.modelo = [[n, [list(x) for x in fila]] for n, fila in modelo]

    def nombres(self) -> list:
        return [n for n, _f in self.modelo]

    def nueva(self, nombre: str) -> str | None:
        nombre = (nombre or "").strip()
        if not nombre or nombre in self.nombres():
            return "Ya hay una categoría con ese nombre." if nombre else "Falta el nombre."
        self.modelo.append([nombre, []])
        return None

    def renombrar(self, i: int, nombre: str) -> str | None:
        nombre = (nombre or "").strip()
        if not nombre:
            return "Falta el nombre."
        if nombre != self.modelo[i][0] and nombre in self.nombres():
            return "Ya hay una categoría con ese nombre."
        self.modelo[i][0] = nombre
        return None

    def borrar(self, i: int) -> str | None:
        """Sus botones pasan a la categoría anterior (o a la siguiente)."""
        if len(self.modelo) < 2:
            return "Tiene que quedar al menos una categoría."
        _n, fila = self.modelo.pop(i)
        self.modelo[max(i - 1, 0)][1].extend(fila)
        return None

    def mover_categoria(self, i: int, paso: int) -> int:
        j = i + paso
        if 0 <= j < len(self.modelo):
            self.modelo[i], self.modelo[j] = self.modelo[j], self.modelo[i]
            return j
        return i

    def mover_boton(self, i: int, k: int, paso: int) -> int:
        fila = self.modelo[i][1]
        j = k + paso
        if 0 <= j < len(fila):
            fila[k], fila[j] = fila[j], fila[k]
            return j
        return k

    def pasar(self, i: int, k: int, destino: int) -> None:
        if destino != i:
            self.modelo[destino][1].append(self.modelo[i][1].pop(k))

    def mostrar(self, i: int, k: int, visible: bool) -> None:
        self.modelo[i][1][k][1] = bool(visible)

    def resultado(self) -> list:
        return [(n, [tuple(x) for x in fila]) for n, fila in self.modelo]


def administrar(QtWidgets, parent, programa: str, fabrica, etiquetas, iconos=None,
                tema_de=None, nombres_tema=None) -> bool:
    """Muestra la ventana. ``fabrica``: [(barra, [botones])]; ``etiquetas`` e
    ``iconos``: {botón: texto / QIcon}. Con ``tema_de`` aparece «Una
    categoría por tema». True si se aceptó (lo elegido ya quedó guardado)."""
    iconos = iconos or {}
    nombre_prog = "IngeCAD" if programa == "ingecad" else "QGIS"
    estado = Ventana(botones.distribuir(fabrica, botones.leer(programa), programa))

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(f"Administrar botones de GeoCAD Yaguareté en {nombre_prog}")
    lay = QtWidgets.QVBoxLayout(dlg)
    intro = QtWidgets.QLabel(
        "Cada categoría es una barra. Agrupá los botones de la misma familia, "
        "ordenalos con las flechas y destildá los que no uses (siguen en el menú). "
        "«Como de fábrica» vuelve a las categorías con que viene GeoCAD.", dlg)
    intro.setWordWrap(True)
    lay.addWidget(intro)
    caja = QtWidgets.QDialogButtonBox(dlg)
    std = getattr(QtWidgets.QDialogButtonBox, "StandardButton", QtWidgets.QDialogButtonBox)
    caja.setStandardButtons(std.Ok | std.Cancel)
    caja.accepted.connect(dlg.accept)
    caja.rejected.connect(dlg.reject)
    lay.addWidget(caja)                       # Aceptar arriba (Fernando, 16/10/2026)
    aviso = QtWidgets.QLabel("", dlg)
    lay.addWidget(aviso)

    cuerpo = QtWidgets.QHBoxLayout()
    lay.addLayout(cuerpo, 1)
    izq, der = QtWidgets.QVBoxLayout(), QtWidgets.QVBoxLayout()
    cuerpo.addLayout(izq, 2)
    cuerpo.addLayout(der, 3)
    izq.addWidget(QtWidgets.QLabel("Categorías (barras)", dlg))
    lista_cat = QtWidgets.QListWidget(dlg)
    izq.addWidget(lista_cat, 1)
    der.addWidget(QtWidgets.QLabel("Botones de la categoría", dlg))
    lista_bot = QtWidgets.QListWidget(dlg)
    der.addWidget(lista_bot, 1)

    def boton(texto, layout):
        b = QtWidgets.QPushButton(texto, dlg)
        layout.addWidget(b)
        return b

    fila_c1, fila_c2 = QtWidgets.QHBoxLayout(), QtWidgets.QHBoxLayout()
    izq.addLayout(fila_c1)
    izq.addLayout(fila_c2)
    b_nueva, b_renombrar, b_borrar = (boton(t, fila_c1) for t in ("Nueva...", "Renombrar...", "Borrar"))
    b_csube, b_cbaja = boton("▲", fila_c2), boton("▼", fila_c2)
    b_temas = boton("Una por tema", fila_c2) if tema_de else None
    b_fabrica = boton("Como de fábrica", fila_c2)
    fila_b = QtWidgets.QHBoxLayout()
    der.addLayout(fila_b)
    b_bsube, b_bbaja = boton("▲", fila_b), boton("▼", fila_b)
    fila_b.addWidget(QtWidgets.QLabel("Pasar a:", dlg))
    combo = QtWidgets.QComboBox(dlg)
    fila_b.addWidget(combo, 1)
    b_pasar = boton("Pasar", fila_b)

    armando = [False]

    import importlib                          # QtCore del mismo Qt que QtWidgets
    Qt = importlib.import_module(QtWidgets.__name__.rsplit(".", 1)[0] + ".QtCore").Qt
    marcado = getattr(getattr(Qt, "CheckState", Qt), "Checked")
    sin_marcar = getattr(getattr(Qt, "CheckState", Qt), "Unchecked")
    usuario = getattr(getattr(Qt, "ItemFlag", Qt), "ItemIsUserCheckable")

    def pintar_categorias(sel=0):
        armando[0] = True
        lista_cat.clear()
        combo.clear()
        for n, fila in estado.modelo:
            vis = sum(1 for _b, v in fila if v)
            lista_cat.addItem(f"{n}  ({vis}/{len(fila)})")
            combo.addItem(n)
        armando[0] = False
        lista_cat.setCurrentRow(max(0, min(sel, len(estado.modelo) - 1)))
        pintar_botones()

    def pintar_botones(sel=None):
        armando[0] = True
        lista_bot.clear()
        i = lista_cat.currentRow()
        if 0 <= i < len(estado.modelo):
            for b, v in estado.modelo[i][1]:
                item = QtWidgets.QListWidgetItem(etiquetas.get(b, b))
                if b in iconos:
                    item.setIcon(iconos[b])
                item.setToolTip(b)
                item.setFlags(item.flags() | usuario)
                item.setCheckState(marcado if v else sin_marcar)
                lista_bot.addItem(item)
        armando[0] = False
        if sel is not None:
            lista_bot.setCurrentRow(sel)

    def avisar(texto):
        aviso.setText(texto or "")

    def preguntar(titulo, actual=""):
        texto, ok = QtWidgets.QInputDialog.getText(dlg, titulo, "Nombre de la categoría:", text=actual)
        return texto if ok else None

    def nueva():
        n = preguntar("Nueva categoría")
        if n is not None:
            err = estado.nueva(n)
            avisar(err)
            if not err:
                pintar_categorias(len(estado.modelo) - 1)

    def renombrar():
        i = lista_cat.currentRow()
        if i < 0:
            return
        n = preguntar("Renombrar categoría", estado.modelo[i][0])
        if n is not None:
            err = estado.renombrar(i, n)
            avisar(err)
            pintar_categorias(i)

    def borrar():
        i = lista_cat.currentRow()
        if i >= 0:
            err = estado.borrar(i)
            avisar(err)
            pintar_categorias(max(i - 1, 0))

    def mover_cat(paso):
        i = lista_cat.currentRow()
        if i >= 0:
            pintar_categorias(estado.mover_categoria(i, paso))

    def mover_bot(paso):
        i, k = lista_cat.currentRow(), lista_bot.currentRow()
        if i >= 0 and k >= 0:
            pintar_botones(estado.mover_boton(i, k, paso))

    def pasar():
        i, k, d = lista_cat.currentRow(), lista_bot.currentRow(), combo.currentIndex()
        if i >= 0 and k >= 0 and d >= 0:
            estado.pasar(i, k, d)
            pintar_categorias(i)

    def tildado(item):
        if armando[0]:
            return
        i = lista_cat.currentRow()
        estado.mostrar(i, lista_bot.row(item), item.checkState() == marcado)
        k = lista_bot.row(item)
        pintar_categorias(i)
        lista_bot.setCurrentRow(k)

    def por_temas():
        estado.modelo = Ventana(botones.por_temas(estado.resultado(), tema_de, nombres_tema)).modelo
        pintar_categorias(0)

    def de_fabrica():
        estado.modelo = Ventana(botones.distribuir(fabrica, programa=programa)).modelo
        avisar("Como de fábrica: al aceptar quedan las categorías de fábrica.")
        pintar_categorias(0)

    b_nueva.clicked.connect(nueva)
    b_renombrar.clicked.connect(renombrar)
    b_borrar.clicked.connect(borrar)
    b_csube.clicked.connect(lambda: mover_cat(-1))
    b_cbaja.clicked.connect(lambda: mover_cat(1))
    b_bsube.clicked.connect(lambda: mover_bot(-1))
    b_bbaja.clicked.connect(lambda: mover_bot(1))
    b_pasar.clicked.connect(pasar)
    b_fabrica.clicked.connect(de_fabrica)
    if b_temas is not None:
        b_temas.clicked.connect(por_temas)
    lista_cat.currentRowChanged.connect(lambda _r: None if armando[0] else pintar_botones())
    lista_bot.itemChanged.connect(tildado)
    pintar_categorias(0)
    dlg.resize(820, 560)

    if not _exec(dlg):
        return False
    botones.guardar(programa, estado.resultado(), fabrica)
    return True
