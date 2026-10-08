# SPDX-License-Identifier: GPL-3.0-or-later
"""Bloques de GeoCAD para IngeCAD: BLOQUE mejorado y edición EN EL LUGAR.

BLOQUE (BLOCK) de IngeCAD es rudimentario: pide el nombre en una ventana de
texto de varias líneas, el bloque guarda la geometría en coordenadas del
dibujo, la referencia nace en la capa 0 y no hay forma cómoda de elegir el
punto base. Este BLOQUE, como el de AutoCAD:

  - objetos (los ya elegidos o «Designe objetos»), nombre en la línea de
    comandos (? lista los que hay; si ya existe, ofrece redefinirlo y todas
    sus referencias se actualizan);
  - punto base con referencias a objetos (se suman Final, Medio, Centro,
    Intersección) y una marca en el cursor; o Centro / abajo-Izquierda de los
    objetos;
  - Convertir (por defecto: quedan reemplazados por el bloque), Retener (quedan
    como están) o Borrar;
  - el bloque guarda la geometría relativa al punto base (como cualquier CAD)
    y la referencia va en la capa actual.

EDICIÓN EN EL LUGAR (doble clic sobre un bloque, o EDITARENSITIO): como
REFEDIT de AutoCAD. El contenido del bloque aparece en su lugar, en el dibujo,
y se edita con cualquier herramienta. Lo que se dibuje mientras tanto se suma
al bloque (AGREGARABLOQUE / QUITARDEBLOQUE para elegir a mano). GUARDARBLOQUE
actualiza la definición —y con ella todas las referencias— en un solo paso
que se puede deshacer; DESCARTARBLOQUE deja todo como estaba.
"""
from __future__ import annotations

import math
import re

from core.commands import Command
from tools.base import Tool

NOMBRE_INVALIDO = re.compile(r'[<>/\\":;?*|=`]')


# -- geometría pura ------------------------------------------------------------------------
def caja(entidades):
    """(xmin, ymin, xmax, ymax) de las entidades, o None."""
    try:
        from ezdxf import bbox

        ext = bbox.extents(entidades, fast=True)
        if not ext.has_data:
            return None
        return ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y
    except Exception:  # noqa: BLE001
        return None


def _layout(entidad):
    try:
        return entidad.get_layout()
    except Exception:  # noqa: BLE001
        return None


def _bloque_recursivo(doc, nombre: str, entidades) -> bool:
    """¿Alguna de las entidades es (o contiene) una referencia al bloque nombre?"""
    vistos = set()

    def contiene(bloque: str) -> bool:
        if bloque == nombre:
            return True
        if bloque in vistos:
            return False
        vistos.add(bloque)
        blk = doc.blocks.get(bloque)
        if blk is None:
            return False
        return any(e.dxftype() == "INSERT" and contiene(e.dxf.name) for e in blk)

    return any(e.dxftype() == "INSERT" and contiene(e.dxf.name) for e in entidades)


# -- crear / redefinir -------------------------------------------------------------------
class CrearBloque(Command):
    """Crea (o redefine) el bloque con las entidades, relativo a ``base``.
    modo: "C" convertir, "R" retener, "B" borrar los objetos originales."""

    needs_regen = True

    def __init__(self, nombre, base, fuentes, modo="C", capa=None):
        self.name = "BLOCK"
        self.nombre = nombre
        self.base = (float(base[0]), float(base[1]))
        self.fuentes = list(fuentes)
        self.modo = modo
        self.capa = capa
        self.insert = None
        self._creado = False
        self._viejas = []
        self._nuevas = []

    def do(self, document) -> None:
        from ezdxf.math import Matrix44

        doc = document.doc
        space = self.space(document)
        blk = doc.blocks.get(self.nombre)
        if blk is None:
            blk = doc.blocks.new(name=self.nombre, base_point=(0, 0, 0))
            self._creado = True
        else:
            self._viejas = list(blk)
            for e in self._viejas:
                blk.unlink_entity(e)
        m = Matrix44.translate(-self.base[0], -self.base[1], 0)
        self._nuevas = []
        for e in self.fuentes:
            c = e.copy()
            c.transform(m)
            blk.add_entity(c)
            self._nuevas.append(c)
        if self.modo in ("C", "B"):
            for e in self.fuentes:
                space.unlink_entity(e)
        if self.modo == "C":
            attribs = {"layer": self.capa} if self.capa else {}
            self.insert = space.add_blockref(self.nombre, self.base, dxfattribs=attribs)
        document.dirty = True

    def undo(self, document) -> None:
        doc = document.doc
        space = self.space(document)
        self.removed_handles = []
        if self.insert is not None:
            self.removed_handles.append(self.insert.dxf.handle)
            space.delete_entity(self.insert)
            self.insert = None
        if self.modo in ("C", "B"):
            for e in self.fuentes:
                space.add_entity(e)
        blk = doc.blocks.get(self.nombre)
        if self._creado:
            doc.blocks.delete_block(self.nombre, safe=False)
            self._creado = False
        elif blk is not None:
            for e in self._nuevas:
                blk.delete_entity(e)
            for e in self._viejas:
                blk.add_entity(e)
        self._nuevas = []
        document.dirty = True


def segmentos(entidades, limite=8000):
    """Los objetos como segmentos ((x1, y1), (x2, y2)): curvas aproximadas,
    bloques anidados desarmados, textos y otros como su recuadro. Para
    resaltar, para la vista previa y para el «fantasma» de INSERTAR."""
    from ezdxf import path as epath

    ents = list(entidades)
    c = caja([e for e in ents if e.dxftype() != "INSERT"] or ents)
    tam = max(c[2] - c[0], c[3] - c[1]) if c else 1.0
    paso = max(tam / 400.0, 1e-6)
    out = []

    def agregar(e, nivel=0):
        if len(out) >= limite:
            return
        tipo = e.dxftype()
        if tipo == "INSERT" and nivel < 4:
            try:
                for v in e.virtual_entities():
                    agregar(v, nivel + 1)
            except Exception:  # noqa: BLE001
                pass
            return
        if tipo == "ATTDEF":
            return
        try:
            pts = [(v.x, v.y) for v in epath.make_path(e).flattening(paso)]
            out.extend(zip(pts[:-1], pts[1:]))
            return
        except Exception:  # noqa: BLE001 -- textos, imágenes...: el recuadro
            pass
        k = caja([e])
        if k:
            x0, y0, x1, y1 = k
            out.extend([((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                        ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))])

    for e in ents:
        agregar(e)
    return out[:limite]


def mover(segs, dx, dy, escala=1.0, rotacion=0.0):
    """Segmentos escalados y girados (grados) alrededor de (0, 0), y movidos."""
    co, si = math.cos(math.radians(rotacion)), math.sin(math.radians(rotacion))

    def t(p):
        x, y = p[0] * escala, p[1] * escala
        return (x * co - y * si + dx, x * si + y * co + dy)

    return [(t(a), t(b)) for a, b in segs]


def _ventana(services):
    return getattr(services, "window", None)


class BloqueTool(Tool):
    """BLOQUE: objetos (resaltados) -> punto base con referencias -> ventana
    con la vista previa, el nombre y «Crear bloque»."""

    wants_selection = True
    REFERENCIAS = frozenset({"END", "MID", "CEN", "INT", "NOD", "QUA"})
    REFERENCIAS_SIEMPRE = True       # aunque las referencias estén apagadas (F3)
    MODOS = {"C": "Convertir en bloque", "R": "Retener los objetos", "B": "Borrar los objetos"}
    modo = "C"                     # recuerda la última elección, como AutoCAD

    def start(self) -> None:
        self.name = "BLOCK"
        self._ents = []
        self._segs = []
        self._nombre = None
        self._base = None
        self._paso = None           # "base", "nombre", "redefinir", "confirmar"

    def selection_prompt(self) -> str:
        return "Designe los objetos del bloque (Enter para terminar):"

    def on_selection(self, entities) -> None:
        entities = [e for e in entities if e is not None and e.is_alive]
        if not entities:
            self.ctx.echo("*Cancelar* (no hay objetos)")
            self.ctx.finish()
            return
        self._ents = entities
        try:
            self._segs = segmentos(entities)
        except Exception:  # noqa: BLE001
            self._segs = []
        self._pedir_base()

    def _pedir_base(self) -> None:
        self._paso = "base"
        self.prompt(f"{len(self._ents)} objeto(s). Precise punto base (con referencias) "
                    "o [Centro/abajo-Izquierda]:")

    def wants_raw_text(self) -> bool:
        return self._paso == "nombre"

    def referencias_extra(self) -> frozenset:
        return self.REFERENCIAS if self._paso == "base" else frozenset()

    def _doc(self):
        return getattr(self.ctx.services, "document", None)

    def validar(self, nombre: str):
        """None si se puede; "~texto" si es un aviso (redefinir); si no, el error."""
        if not nombre:
            return "Escriba un nombre."
        if NOMBRE_INVALIDO.search(nombre) or len(nombre) > 255:
            return 'Nombre no válido (sin < > / \\ " : ; ? * | = `).'
        doc = self._doc()
        if doc is not None and nombre in doc.doc.blocks:
            if _bloque_recursivo(doc.doc, nombre, self._ents):
                return f"«{nombre}» no puede contenerse a sí mismo."
            n = sum(1 for e in doc.doc.modelspace() if e.dxftype() == "INSERT" and e.dxf.name == nombre)
            return f"~«{nombre}» ya existe: se va a REDEFINIR y se actualizan sus {n} referencia(s)."
        return None

    def _nombres(self):
        from core.blockedit import editable_blocks

        doc = self._doc()
        return editable_blocks(doc) if doc is not None else []

    def _tomar_base(self, punto) -> None:
        self._base = (float(punto[0]), float(punto[1]))
        from . import bloques_ui

        segs = mover(self._segs, -self._base[0], -self._base[1])
        try:
            r = bloques_ui.crear(_ventana(self.ctx.services), segs, self._nombres(),
                                 len(self._ents), type(self).modo, self.validar)
        except Exception as exc:  # noqa: BLE001 -- la ventana falló: por la línea de comandos
            self.ctx.echo(f"(sin ventana: {exc})")
            r = bloques_ui.SIN_QT
        if r is bloques_ui.SIN_QT:
            self._paso = "nombre"
            self.prompt("Nombre del bloque o [?]:")
            return
        if r is None:                      # Cancelar: se vuelve a elegir el punto base
            self.ctx.echo("Creación cancelada: elija otro punto base o Esc para salir.")
            self._pedir_base()
            return
        type(self).modo = r["modo"]
        self._nombre = r["nombre"]
        self._crear()

    def on_option(self, text: str) -> bool:
        t = text.strip()
        T = t.upper().lstrip("_")
        if self._paso == "base":
            if T in ("C", "CENTRO", "CENTER"):
                self._tomar_base(self._punto_caja("centro"))
                return True
            if T in ("I", "ABAJO-IZQUIERDA", "IZQUIERDA", "INFERIOR"):
                self._tomar_base(self._punto_caja("abajo"))
                return True
            return False
        if self._paso == "nombre":
            if not t:
                self.ctx.echo("*Cancelar*")
                self.ctx.finish()
                return True
            if t == "?":
                nombres = self._nombres()
                self.ctx.echo("Bloques: " + (", ".join(nombres) if nombres else "(ninguno)"))
                return True
            problema = self.validar(t)
            if problema and not problema.startswith("~"):
                self.ctx.echo(problema)
                return True
            self._nombre = t
            if problema:
                self._paso = "redefinir"
                self.prompt(problema[1:] + " ¿Seguir? [Sí/No] <No>:")
                return True
            self._pedir_confirmacion()
            return True
        if self._paso == "redefinir":
            if T[:1] in ("S", "Y"):
                self._pedir_confirmacion()
            else:
                self._paso = "nombre"
                self.prompt("Nombre del bloque o [?]:")
            return True
        if self._paso == "confirmar":
            if T in ("", "S", "SI", "SÍ", "Y", "CREAR"):
                self._crear()
            elif T[:2] == "CO":
                type(self).modo = "C"; self._pedir_confirmacion()
            elif T[:1] == "R":
                type(self).modo = "R"; self._pedir_confirmacion()
            elif T[:1] == "B":
                type(self).modo = "B"; self._pedir_confirmacion()
            else:
                self.ctx.echo("*Cancelar*")
                self.ctx.finish()
            return True
        return False

    def _pedir_confirmacion(self) -> None:
        self._paso = "confirmar"
        self.ctx.echo(f"Bloque «{self._nombre}»: {len(self._ents)} objeto(s), punto base "
                      f"({self._base[0]:.4g}, {self._base[1]:.4g}), {self.MODOS[type(self).modo]}.")
        self.prompt("¿Crear el bloque? [Sí/No/COnvertir/Retener/Borrar] <Sí>:")

    def _punto_caja(self, cual):
        c = caja(self._ents)
        if c is None:
            return (0.0, 0.0)
        if cual == "centro":
            return ((c[0] + c[2]) / 2.0, (c[1] + c[3]) / 2.0)
        return (c[0], c[1])

    def on_point(self, point) -> None:
        if self._paso == "base":
            self._tomar_base(point)

    def on_enter(self) -> None:
        if self._paso in ("nombre", "confirmar"):
            self.on_option("")
            return
        if self._paso == "redefinir":
            self.on_option("N")
            return
        self.ctx.finish()

    def _crear(self) -> None:
        from core.layers import current_layer_name

        doc = self._doc()
        capa = current_layer_name(doc) if doc is not None else None
        modo = type(self).modo
        self.ctx.execute(CrearBloque(self._nombre, self._base, self._ents, modo, capa))
        accion = {"C": "y los objetos quedaron convertidos en él",
                  "R": "y los objetos quedaron como estaban",
                  "B": "y los objetos se borraron"}[modo]
        self.ctx.echo(f"Bloque «{self._nombre}» creado con {len(self._ents)} objeto(s), punto base "
                      f"({self._base[0]:.4g}, {self._base[1]:.4g}), {accion}.")
        self.ctx.finish()

    def resaltado(self, cursor) -> dict:
        """Los objetos elegidos, iluminados mientras se elige el punto base, y
        la marca del punto base en el cursor (ya con la referencia)."""
        out = {"elegido": [], "puntos": [], "textos": []}
        if self._paso == "base":
            out["elegido"] = self._segs
            if cursor is not None:
                out["puntos"] = [tuple(cursor)]
                out["textos"] = [(tuple(cursor), "punto base")]
        return out


class InsertarTool(Tool):
    """INSERTAR: ventana con la lista y la vista previa; después el bloque
    sigue al cursor («fantasma») y el punto de inserción se toma con
    referencias (se suman Final, Medio, Centro, Intersección, Nodo,
    Inserción y Cuadrante, aunque estén apagadas)."""

    REFERENCIAS = frozenset({"END", "MID", "CEN", "INT", "NOD", "INS", "QUA"})
    REFERENCIAS_SIEMPRE = True
    escala = 1.0
    rotacion = 0.0
    ultimo = None
    PROMPT = "Precise punto de inserción (con referencias) o [Escala/Rotación/Bloque]:"

    def start(self) -> None:
        self.name = "INSERT"
        self._nombre = None
        self._await = None
        self._segs = []
        self._elegir()

    def _doc(self):
        return getattr(self.ctx.services, "document", None)

    def _segs_de(self, nombre):
        doc = self._doc()
        blk = doc.doc.blocks.get(nombre) if doc is not None else None
        if blk is None:
            return []
        try:
            return segmentos(list(blk))
        except Exception:  # noqa: BLE001
            return []

    def _elegir(self) -> None:
        from core.blockedit import editable_blocks

        from . import bloques_ui

        doc = self._doc()
        nombres = editable_blocks(doc) if doc is not None else []
        if not nombres:
            self.ctx.echo("No hay bloques definidos en el dibujo.")
            self.ctx.finish()
            return
        cls = type(self)
        try:
            r = bloques_ui.insertar(_ventana(self.ctx.services), nombres, self._segs_de,
                                    cls.escala, cls.rotacion, cls.ultimo)
        except Exception as exc:  # noqa: BLE001
            self.ctx.echo(f"(sin ventana: {exc})")
            r = bloques_ui.SIN_QT
        if r is bloques_ui.SIN_QT:
            elegido = self.ctx.ask_choice("Insertar bloque:", nombres,
                                          cls.ultimo if cls.ultimo in nombres else nombres[0])
            if not elegido:
                self.ctx.finish()
                return
            r = {"nombre": elegido, "escala": cls.escala, "rotacion": cls.rotacion}
        if r is None:
            self.ctx.finish()
            return
        self._nombre = r["nombre"]
        cls.ultimo, cls.escala, cls.rotacion = r["nombre"], r["escala"], r["rotacion"]
        self._segs = self._segs_de(self._nombre)
        self.prompt(self.PROMPT)

    def referencias_extra(self) -> frozenset:
        return self.REFERENCIAS if self._nombre and self._await is None else frozenset()

    def on_option(self, text: str) -> bool:
        T = text.strip().upper().lstrip("_")
        cls = type(self)
        if self._await in ("escala", "rotacion"):
            try:
                v = float(text.replace(",", "."))
            except ValueError:
                self.ctx.echo("Requiere un número.")
                return True
            if self._await == "escala":
                if v <= 0:
                    self.ctx.echo("La escala tiene que ser mayor que 0.")
                    return True
                cls.escala = v
            else:
                cls.rotacion = v
            self._await = None
            self.prompt(self.PROMPT)
            return True
        if T in ("E", "ESCALA", "S", "SCALE"):
            self._await = "escala"
            self.prompt(f"Factor de escala <{cls.escala:g}>:")
            return True
        if T in ("R", "ROTACION", "ROTACIÓN", "ROTATE"):
            self._await = "rotacion"
            self.prompt(f"Ángulo de rotación <{cls.rotacion:g}>:")
            return True
        if T in ("B", "BLOQUE", "BLOCK"):
            self._elegir()
            return True
        return False

    def on_enter(self) -> None:
        if self._await is not None:
            self._await = None
            self.prompt(self.PROMPT)
            return
        self.ctx.finish()

    def on_point(self, point) -> None:
        if not self._nombre or self._await is not None:
            return
        from core import actions
        from core.layers import current_layer_name

        doc = self._doc()
        cls = type(self)
        capa = current_layer_name(doc) if doc is not None else "0"
        nombre, esc, rot = self._nombre, cls.escala, cls.rotacion
        x, y = float(point[0]), float(point[1])

        def fabrica(msp):
            ref = msp.add_blockref(nombre, (x, y), dxfattribs={
                "layer": capa, "xscale": esc, "yscale": esc, "zscale": esc, "rotation": rot})
            try:
                if any(e.dxftype() == "ATTDEF" for e in msp.doc.blocks.get(nombre)):
                    ref.add_auto_attribs({})
            except Exception:  # noqa: BLE001
                pass
            return ref

        self.ctx.execute(actions.AddEntityCommand("INSERT", fabrica))
        self.ctx.echo(f"«{nombre}» insertado en ({x:.4g}, {y:.4g}), escala {esc:g}, rotación {rot:g}°.")
        self.ctx.finish()

    def resaltado(self, cursor) -> dict:
        out = {"fantasma": [], "puntos": [], "textos": []}
        if self._nombre and self._await is None and cursor is not None:
            cls = type(self)
            out["fantasma"] = mover(self._segs, cursor[0], cursor[1], cls.escala, cls.rotacion)
            out["puntos"] = [tuple(cursor)]
            out["textos"] = [(tuple(cursor), self._nombre)]
        return out


# -- edición en el lugar -------------------------------------------------------------------
class CambiarDefinicion(Command):
    """Reemplaza el contenido del bloque (un paso, se puede deshacer)."""

    needs_regen = True

    def __init__(self, nombre, nuevas):
        self.name = "REFEDIT"
        self.nombre = nombre
        self._nuevas = list(nuevas)
        self._viejas = None

    def do(self, document) -> None:
        blk = document.doc.blocks.get(self.nombre)
        if self._viejas is None:
            self._viejas = list(blk)
        for e in self._viejas:
            blk.unlink_entity(e)
        for e in self._nuevas:
            blk.add_entity(e)
        document.dirty = True

    def undo(self, document) -> None:
        blk = document.doc.blocks.get(self.nombre)
        for e in self._nuevas:
            blk.unlink_entity(e)
        for e in self._viejas:
            blk.add_entity(e)
        document.dirty = True


# -- cambiar el punto base -----------------------------------------------------------------
def referencias(doc, nombre):
    """Todas las referencias al bloque: en el modelo, en las presentaciones y
    dentro de otros bloques (anidadas)."""
    return [e for blk in doc.blocks if blk.name != nombre
            for e in blk if e.dxftype() == "INSERT" and e.dxf.name == nombre]


def punto_en_bloque(insert, punto):
    """El punto del dibujo, en las coordenadas de la definición del bloque."""
    from ezdxf.math import Vec3

    inversa = insert.matrix44().copy()
    inversa.inverse()
    v = inversa.transform(Vec3(punto[0], punto[1], 0))
    return (v.x, v.y)


class CambiarPuntoBase(Command):
    """El punto ``nuevo`` (coordenadas del bloque) pasa a ser el punto base.

    La geometría del bloque se corre para que ``nuevo`` caiga en el punto base
    de la definición (sirve igual para los bloques de GeoCAD, con base 0,0, y
    para los nativos de IngeCAD, con base en coordenadas del dibujo).
    mantener=True: cada referencia se corre lo justo para que el dibujo no
    cambie (los atributos ya están en coordenadas del dibujo: no se tocan).
    mantener=False: las referencias quedan donde están y el bloque se ve
    desplazado; sus atributos acompañan."""

    needs_regen = True

    def __init__(self, nombre, nuevo, mantener=True):
        self.name = "BLOCKBASE"
        self.nombre = nombre
        self.nuevo = (float(nuevo[0]), float(nuevo[1]))
        self.mantener = mantener
        self.cambios = []                 # (referencia, inserción anterior, corrimiento de atributos)

    def do(self, document) -> None:
        from ezdxf.math import Matrix44, Vec3

        doc = document.doc
        blk = doc.blocks.get(self.nombre)
        b = Vec3(blk.block.dxf.get("base_point", (0, 0, 0)))
        q = Vec3(self.nuevo[0], self.nuevo[1], b.z)
        d = b - q
        self._d = d
        refs = referencias(doc, self.nombre)
        destinos = [r.matrix44().transform(q) for r in refs]     # antes de tocar nada
        m = Matrix44.translate(d.x, d.y, 0)
        for e in blk:
            e.transform(m)
        self.cambios = []
        for r, destino in zip(refs, destinos):
            anterior = Vec3(r.dxf.insert)
            corrimiento = None
            if self.mantener:
                r.dxf.insert = r.ocs().from_wcs(destino)
            else:
                corrimiento = r.ocs().to_wcs(anterior) - destino
                for a in getattr(r, "attribs", ()):
                    a.translate(corrimiento.x, corrimiento.y, corrimiento.z)
            self.cambios.append((r, anterior, corrimiento))
        document.dirty = True

    def undo(self, document) -> None:
        from ezdxf.math import Matrix44

        blk = document.doc.blocks.get(self.nombre)
        d = self._d
        m = Matrix44.translate(-d.x, -d.y, 0)
        for e in blk:
            e.transform(m)
        for r, anterior, corrimiento in self.cambios:
            r.dxf.insert = anterior
            if corrimiento is not None:
                for a in getattr(r, "attribs", ()):
                    a.translate(-corrimiento.x, -corrimiento.y, -corrimiento.z)
        self.cambios = []
        document.dirty = True


ATRIBUTO = "_geocad_edicion_bloque"


def sesion(window):
    return getattr(window, ATRIBUTO, None)


def _refrescar(window, removidos=()):
    import types

    tools = getattr(window, "tools", None)
    try:
        if tools is not None and hasattr(tools, "after_history_change"):
            tools.after_history_change(types.SimpleNamespace(needs_regen=True,
                                                             removed_handles=list(removidos)))
        elif hasattr(window, "regen_in_memory"):
            window.regen_in_memory()
    except Exception:  # noqa: BLE001 -- sin vista (pruebas)
        pass


def _echo(window, texto):
    cl = getattr(window, "command_line", None)
    if cl is not None:
        cl.echo(texto)


class EdicionEnSitio:
    """Una edición en el lugar abierta (una por ventana)."""

    def __init__(self, window, insert, nombre, matriz, space, trabajo, inicio, piso):
        self.window, self.insert, self.nombre = window, insert, nombre
        self.matriz, self.space = matriz, space
        self.trabajo = set(trabajo)       # handles de las copias del contenido
        self.inicio = set(inicio)         # handles que había al empezar
        self.excluidos = set()            # sacados a mano del conjunto
        self.piso = piso                  # el deshacer no cruza este punto
        self.nueva_base = None            # punto del dibujo elegido con PUNTOBASEBLOQUE
        self.mantener = True              # al guardar: las otras referencias no se mueven
        self.barra = None

    # -- abrir -----------------------------------------------------------------------
    @classmethod
    def abrir(cls, window, insert):
        """Abre la edición o devuelve un texto con el motivo."""
        if sesion(window) is not None:
            return "Ya hay un bloque en edición: GUARDARBLOQUE o DESCARTARBLOQUE primero."
        document = getattr(window, "document", None)
        if document is None or insert is None or insert.dxftype() != "INSERT":
            return "Elija una referencia a bloque."
        doc = document.doc
        nombre = insert.dxf.name
        blk = doc.blocks.get(nombre)
        if blk is None or nombre.startswith("*"):
            return f"«{nombre}» no se puede editar en el lugar."
        try:
            if blk.block.is_xref:
                return f"«{nombre}» es una referencia externa: se edita en su propio archivo."
        except Exception:  # noqa: BLE001
            pass
        sx, sy = insert.dxf.get("xscale", 1), insert.dxf.get("yscale", 1)
        if abs(abs(sx) - abs(sy)) > 1e-9 * max(1.0, abs(sx)):
            return "Esta referencia tiene escala distinta en X e Y: use BEDIT para editar el bloque."
        if insert.dxf.get("column_count", 1) > 1 or insert.dxf.get("row_count", 1) > 1:
            return "Una referencia múltiple (MINSERT) no se edita en el lugar."
        space = _layout(insert) or document.current_space()
        m = insert.matrix44()
        copias = []
        try:
            for e in blk:
                c = e.copy()
                c.transform(m)
                space.add_entity(c)
                copias.append(c)
        except Exception as exc:  # noqa: BLE001
            for c in copias:
                space.delete_entity(c)
            return f"No se pudo abrir el bloque en el lugar ({type(exc).__name__}: {exc})."
        space.unlink_entity(insert)
        history = window.history
        history._redo.clear()
        s = cls(window, insert, nombre, m, space, [c.dxf.handle for c in copias],
                [e.dxf.handle for e in space], len(history._undo))
        setattr(window, ATRIBUTO, s)
        s._mostrar_barra()
        _refrescar(window, [insert.dxf.handle])
        n = sum(1 for e in space if e.dxftype() == "INSERT" and e.dxf.name == nombre)
        _echo(window, f"Editando «{nombre}» en el lugar ({len(copias)} objeto(s)). Lo que dibuje "
                      "se suma al bloque. GUARDARBLOQUE actualiza "
                      f"{'sus ' + str(n + 1) + ' referencias' if n else 'la referencia'}; "
                      "DESCARTARBLOQUE deja todo como estaba.")
        return s

    # -- conjunto de trabajo ---------------------------------------------------------
    def conjunto(self):
        """Las entidades que van a formar el bloque al guardar."""
        actuales = {e.dxf.handle: e for e in self.space if e.is_alive}
        handles = (self.trabajo | (set(actuales) - self.inicio)) - self.excluidos
        return [actuales[h] for h in actuales if h in handles]

    def agregar(self, entidades) -> int:
        n = 0
        for e in entidades:
            if e.dxftype() == "INSERT" and _bloque_recursivo(self.window.document.doc,
                                                             self.nombre, [e]):
                continue
            self.trabajo.add(e.dxf.handle)
            self.excluidos.discard(e.dxf.handle)
            n += 1
        return n

    def quitar(self, entidades) -> int:
        n = 0
        for e in entidades:
            h = e.dxf.handle
            if h in self.trabajo or h not in self.inicio:
                self.excluidos.add(h)
                self.trabajo.discard(h)
                n += 1
        return n

    def deshacer_permitido(self) -> bool:
        return len(self.window.history._undo) > self.piso

    # -- cerrar ----------------------------------------------------------------------
    def guardar(self) -> str:
        window, doc = self.window, self.window.document
        ents = self.conjunto()
        ents = [e for e in ents if not (e.dxftype() == "INSERT"
                                        and _bloque_recursivo(doc.doc, self.nombre, [e]))]
        inversa = self.matriz.copy()
        inversa.inverse()
        nuevas = []
        for e in ents:
            c = e.copy()
            c.transform(inversa)
            nuevas.append(c)
        removidos = [e.dxf.handle for e in ents]
        for e in ents:
            self.space.delete_entity(e)
        self.space.add_entity(self.insert)
        history = window.history
        del history._undo[self.piso:]
        history._redo.clear()
        self._cerrar()
        cambio = CambiarDefinicion(self.nombre, nuevas)
        extra = ""
        if self.nueva_base is not None:     # el nuevo punto base va en el mismo paso
            from core.commands import CompositeCommand
            from ezdxf.math import Vec3

            q = inversa.transform(Vec3(self.nueva_base[0], self.nueva_base[1], 0))
            cambio = CompositeCommand("REFEDIT", [
                cambio, CambiarPuntoBase(self.nombre, (q.x, q.y), self.mantener)])
            extra = (" y el punto base nuevo" + (", sin mover las referencias" if self.mantener
                                                 else "; las referencias se desplazaron"))
        history.execute(cambio)
        _refrescar(window, removidos)
        msg = (f"Bloque «{self.nombre}» guardado con {len(nuevas)} objeto(s){extra}; "
               "sus referencias se actualizaron.")
        _echo(window, msg)
        return msg

    def descartar(self) -> str:
        window = self.window
        history = window.history
        while len(history._undo) > self.piso:
            history.undo()
        history._redo.clear()
        actuales = {e.dxf.handle: e for e in self.space}
        removidos = []
        for h in self.trabajo | (set(actuales) - self.inicio):
            e = actuales.get(h)
            if e is not None and e.is_alive:
                removidos.append(h)
                self.space.delete_entity(e)
        self.space.add_entity(self.insert)
        self._cerrar()
        _refrescar(window, removidos)
        msg = f"Edición de «{self.nombre}» descartada: el dibujo quedó como estaba."
        _echo(window, msg)
        return msg

    def _cerrar(self):
        setattr(self.window, ATRIBUTO, None)
        self._quitar_barra()

    # -- la barra «Editando bloque» -----------------------------------------------------
    def _mostrar_barra(self):
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QAction
            from PySide6.QtWidgets import QLabel, QToolBar
        except Exception:  # noqa: BLE001 -- sin Qt (pruebas)
            return
        w = self.window
        bar = QToolBar("Edición de bloque", w)
        bar.setObjectName("geocad_edicion_bloque")
        etiqueta = QLabel(f"  Editando el bloque «{self.nombre}» en el lugar   ")
        etiqueta.setStyleSheet("color: #ffd75e; font-weight: bold;")
        bar.addWidget(etiqueta)
        for texto, comando in (("Guardar bloque", "GEOREFSAVE"), ("Descartar", "GEOREFDISCARD"),
                               ("Agregar objetos", "GEOREFADD"), ("Quitar objetos", "GEOREFREMOVE"),
                               ("Punto base", "GEOBLOCKBASE")):
            act = QAction(texto, w)
            act.triggered.connect(lambda _=False, c=comando: w._invoke_command(c))
            bar.addAction(act)
        w.addToolBarBreak(Qt.TopToolBarArea)
        w.addToolBar(Qt.TopToolBarArea, bar)
        self.barra = bar

    def _quitar_barra(self):
        bar, self.barra = self.barra, None
        if bar is not None:
            try:
                self.window.removeToolBar(bar)
                bar.setParent(None)
                bar.deleteLater()
            except Exception:  # noqa: BLE001
                pass


# -- herramientas y comandos -----------------------------------------------------------------
class EditarEnSitioTool(Tool):
    """EDITARENSITIO: elegir la referencia a editar en el lugar."""

    entity_picker = True

    def start(self) -> None:
        self.name = "GEOREFEDIT"
        self.prompt("Designe la referencia a bloque a editar en el lugar:")

    def on_point(self, point) -> None:
        s = self.ctx.services
        e = s.pick_entity(point) if s else None
        if e is None or e.dxftype() != "INSERT":
            self.ctx.echo("Eso no es una referencia a bloque.")
            return
        window = getattr(s, "window", None)
        r = EdicionEnSitio.abrir(window, e)
        if isinstance(r, str):
            self.ctx.echo(r)
        self.ctx.finish()


class PuntoBaseTool(Tool):
    """PUNTOBASEBLOQUE: volver a elegir el punto base de un bloque ya creado.
    Referencia -> nuevo punto base con referencias -> qué hacer con las
    referencias existentes (Mantener en su lugar, por defecto, o Desplazar).
    Con un bloque en edición en el lugar, el punto se aplica al GUARDARBLOQUE."""

    entity_picker = True
    REFERENCIAS = BloqueTool.REFERENCIAS | {"INS"}
    REFERENCIAS_SIEMPRE = True
    MODOS = {True: "quedan en su lugar", False: "se desplazan con el punto base"}
    mantener = True                  # recuerda la última elección

    def start(self) -> None:
        self.name = "BLOCKBASE"
        self._ref = None
        self._segs = []
        self._q = None
        self._paso = "referencia"   # "referencia", "punto", "modo"
        self.entity_picker = True
        s = self._sesion()
        if s is not None:            # en la edición en el lugar ya se sabe qué bloque es
            self.entity_picker = False
            self._paso = "punto"
            self._segs = segmentos(s.conjunto())
            self.prompt(f"Precise el nuevo punto base de «{s.nombre}» (con referencias):")
            return
        self.prompt("Designe la referencia al bloque:")

    def _sesion(self):
        return sesion(_ventana(self.ctx.services))

    def _doc(self):
        return getattr(self.ctx.services, "document", None)

    def referencias_extra(self) -> frozenset:
        return self.REFERENCIAS if self._paso == "punto" else frozenset()

    def on_point(self, point) -> None:
        if self._paso == "referencia":
            s = self.ctx.services
            e = s.pick_entity(point) if s else None
            if e is None or e.dxftype() != "INSERT":
                self.ctx.echo("Eso no es una referencia a bloque.")
                return
            blk = self._doc().doc.blocks.get(e.dxf.name)
            if blk is None or e.dxf.name.startswith("*") or getattr(blk.block, "is_xref", False):
                self.ctx.echo(f"«{e.dxf.name}» no admite cambiar el punto base.")
                return
            self._ref = e
            self._segs = segmentos([e])
            self.entity_picker = False       # ahora un punto de verdad, con referencias
            self._paso = "punto"
            self.prompt(f"Precise el nuevo punto base de «{e.dxf.name}» (con referencias):")
            return
        if self._paso == "punto":
            s = self._sesion()
            if s is not None:
                s.nueva_base = (float(point[0]), float(point[1]))
                self._q = point
            else:
                self._q = punto_en_bloque(self._ref, point)
            self._pedir_modo()

    def _pedir_modo(self) -> None:
        self._paso = "modo"
        s = self._sesion()
        doc = self._doc().doc
        nombre = s.nombre if s is not None else self._ref.dxf.name
        n = len(referencias(doc, nombre)) + (1 if s is not None else 0)
        defecto = "Mantener" if type(self).mantener else "Desplazar"
        self.prompt(f"«{nombre}» tiene {n} referencia(s). Las referencias: "
                    f"[Mantener en su lugar/Desplazar] <{defecto}>:")

    def on_option(self, text: str) -> bool:
        if self._paso != "modo":
            return False
        T = text.strip().upper().lstrip("_")
        if T[:1] == "M":
            type(self).mantener = True
        elif T[:1] == "D":
            type(self).mantener = False
        elif T:
            self.ctx.echo("Responda M (Mantener) o D (Desplazar).")
            return True
        self._aplicar()
        return True

    def on_enter(self) -> None:
        if self._paso == "modo":
            self._aplicar()
            return
        self.ctx.finish()

    def _aplicar(self) -> None:
        mantener = type(self).mantener
        s = self._sesion()
        if s is not None:
            s.mantener = mantener
            self.ctx.echo(f"Nuevo punto base de «{s.nombre}» anotado: se aplica al GUARDARBLOQUE "
                          f"(las referencias {self.MODOS[mantener]}).")
        else:
            nombre = self._ref.dxf.name
            cmd = CambiarPuntoBase(nombre, self._q, mantener)
            self.ctx.execute(cmd)
            self.ctx.echo(f"Punto base de «{nombre}» cambiado; {len(cmd.cambios)} referencia(s) "
                          f"{self.MODOS[mantener]}.")
        self.ctx.finish()

    def resaltado(self, cursor) -> dict:
        """El bloque iluminado y la marca del nuevo punto base en el cursor."""
        out = {"elegido": [], "puntos": [], "textos": []}
        if self._paso == "punto":
            out["elegido"] = self._segs
            if cursor is not None:
                out["puntos"] = [tuple(cursor)]
                out["textos"] = [(tuple(cursor), "nuevo punto base")]
        return out


class _ConjuntoTool(Tool):
    wants_selection = True
    QUITAR = False

    def start(self) -> None:
        self.name = "GEOREFSET"

    def on_selection(self, entities) -> None:
        window = getattr(self.ctx.services, "window", None)
        s = sesion(window)
        if s is None:
            self.ctx.echo("No hay un bloque en edición (doble clic sobre un bloque para empezar).")
        elif self.QUITAR:
            self.ctx.echo(f"{s.quitar(entities)} objeto(s) quedan fuera del bloque.")
        else:
            self.ctx.echo(f"{s.agregar(entities)} objeto(s) se suman al bloque.")
        self.ctx.finish()


class AgregarTool(_ConjuntoTool):
    def selection_prompt(self) -> str:
        return "Designe objetos para sumar al bloque:"


class QuitarTool(_ConjuntoTool):
    QUITAR = True

    def selection_prompt(self) -> str:
        return "Designe objetos para dejar fuera del bloque:"


def cmd_guardar(ctx, *args) -> None:
    s = sesion(ctx.host)
    if s is None:
        ctx.echo("No hay un bloque en edición.")
        return
    s.guardar()


def cmd_descartar(ctx, *args) -> None:
    s = sesion(ctx.host)
    if s is None:
        ctx.echo("No hay un bloque en edición.")
        return
    s.descartar()


# -- enganches con la ventana de IngeCAD (los instala dibujo.instalar) ------------------------
def _activo(window) -> bool:
    from . import modulos

    mgr = getattr(window, "plugins", None)
    try:
        if mgr is not None and not mgr.is_active("geocad"):
            return False
    except Exception:  # noqa: BLE001
        pass
    return modulos.activo("ingecad", "bloques")


def _envolver_doble_clic(original):
    def on_canvas_double_click(self, wx, wy):
        try:
            if _activo(self) and getattr(self, "_active_vp", None) is None \
                    and self.document is not None:
                e = self.tools.pick_entity((wx, wy))
                if e is not None and e.dxftype() == "INSERT":
                    s = sesion(self)
                    if s is not None:
                        _echo(self, "Ya hay un bloque en edición: GUARDARBLOQUE o DESCARTARBLOQUE.")
                        return None
                    tiene_atributos = bool(getattr(e, "attribs", None))
                    if not tiene_atributos:          # con atributos: el editor de atributos
                        r = EdicionEnSitio.abrir(self, e)
                        if isinstance(r, str):
                            _echo(self, r)
                        return None
        except Exception as exc:  # noqa: BLE001
            _echo(self, f"GeoCAD Yaguareté: no se pudo abrir el bloque ({exc}).")
        return original(self, wx, wy)

    on_canvas_double_click._puente_original = original
    return on_canvas_double_click


def _envolver_deshacer(original):
    def _cmd_undo(self, *args):
        s = sesion(self)
        if s is not None and not s.deshacer_permitido():
            _echo(self, "Nada para deshacer dentro de la edición del bloque "
                        "(GUARDARBLOQUE o DESCARTARBLOQUE).")
            return None
        return original(self, *args)

    _cmd_undo._puente_original = original
    return _cmd_undo


def _envolver_escribir(original):
    def _write_document(self, *args, **kwargs):
        if sesion(self) is not None:
            _echo(self, "Hay un bloque en edición: GUARDARBLOQUE o DESCARTARBLOQUE antes de "
                        "guardar el dibujo.")
            return False
        return original(self, *args, **kwargs)

    _write_document._puente_original = original
    return _write_document


def _envolver_cerrar(original):
    def maybe_save_changes(self, *args, **kwargs):
        s = sesion(self)
        if s is not None:
            s.descartar()            # nunca se guarda un dibujo a medio editar
        return original(self, *args, **kwargs)

    maybe_save_changes._puente_original = original
    return maybe_save_changes


# ------------------------------------------------- referencias sobre bloques
#: más objetos que esto adentro de un bloque (contando los anidados): sólo el
#: punto de inserción, como venía (un bloque así haría lento cada cambio)
MAX_OBJETOS_REFERENCIAS = 5000
_tamanos: dict = {}
_activo_cache = [0.0, False]


def _bloques_activo() -> bool:
    """Módulo Bloques prendido (se relee el archivo cada 2 s como mucho)."""
    import time
    ahora = time.monotonic()
    if ahora - _activo_cache[0] > 2.0:
        _activo_cache[0] = ahora
        from . import modulos
        _activo_cache[1] = modulos.activo("ingecad", "bloques")
    return _activo_cache[1]


def tamano_bloque(doc, nombre: str, _vistos=()) -> int:
    """Cuántos objetos dibuja un bloque, contando los bloques anidados."""
    blk = doc.blocks.get(nombre) if doc is not None else None
    if blk is None or nombre in _vistos:
        return 0
    clave = (id(doc), nombre, len(blk))
    if clave in _tamanos:
        return _tamanos[clave]
    total = 0
    for e in blk:
        total += 1
        if e.dxftype() == "INSERT":
            total += tamano_bloque(doc, e.dxf.name, (*_vistos, nombre))
        if total > MAX_OBJETOS_REFERENCIAS:
            break
    _tamanos[clave] = total
    return total


def con_referencias(insert) -> bool:
    """¿Este bloque ofrece referencias sobre su contenido?"""
    try:
        from core import xrefs
        if xrefs.is_xref_insert(insert):
            return False                 # las referencias externas ya las tiene IngeCAD
    except Exception:  # noqa: BLE001
        pass
    return 0 < tamano_bloque(insert.doc, insert.dxf.name) <= MAX_OBJETOS_REFERENCIAS


_geometria_local: dict = {}


def _transformacion(insert):
    """(origen, eje x, eje y) del bloque en el dibujo, o None si la escala no
    es pareja (X distinta de Y) o es un MINSERT: esos van por el camino lento."""
    try:
        if insert.dxf.get("row_count", 1) > 1 or insert.dxf.get("column_count", 1) > 1:
            return None
        m = insert.matrix44()
        o = m.transform((0, 0, 0))
        ex = m.transform((1, 0, 0)) - o
        ey = m.transform((0, 1, 0)) - o
    except Exception:  # noqa: BLE001
        return None
    sx, sy = math.hypot(ex.x, ex.y), math.hypot(ey.x, ey.y)
    if sx < 1e-12 or abs(sx - sy) > 1e-9 * max(sx, 1.0) or abs(ex.x * ey.x + ex.y * ey.y) > 1e-9 * sx * sy:
        return None
    return (o.x, o.y), (ex.x, ex.y), (ey.x, ey.y)


def _local(original, insert):
    """La geometría del bloque en sus propias coordenadas (matrix44 ya
    descuenta el punto base), calculada una vez por definición. Se borra cada
    vez que IngeCAD rearma las referencias (después de editar)."""
    doc, nombre = insert.doc, insert.dxf.name
    blk = doc.blocks.get(nombre)
    clave = (id(doc), nombre, len(blk), tuple(blk.block.dxf.base_point)[:2])
    geo = _geometria_local.get(clave)
    if geo is None:
        geo = {k: [] for k in ("segs", "circles", "arcs", "points", "curves", "targets")}
        tiradas = [[] for _ in range(6)]
        for e in blk:
            _extract_geocad(original, e, 0, geo["segs"], tiradas[0], geo["circles"], tiradas[1],
                            geo["arcs"], tiradas[2], geo["points"], tiradas[3],
                            geo["curves"], tiradas[4], geo["targets"], tiradas[5])
        _geometria_local[clave] = geo
    return geo


def _colocar(geo, tr, oid, segs, seg_o, circles, circle_o, arcs, arc_o,
             points, point_o, curves, curve_o, targets, target_o) -> None:
    (ox, oy), (ax, ay), (bx, by) = tr
    s = math.hypot(ax, ay)
    giro = math.atan2(ay, ax)
    espejo = ax * by - ay * bx < 0

    def p(x, y):
        return ox + x * ax + y * bx, oy + x * ay + y * by

    for x1, y1, x2, y2 in geo["segs"]:
        segs.append((*p(x1, y1), *p(x2, y2))); seg_o.append(oid)
    for cx, cy, r in geo["circles"]:
        circles.append((*p(cx, cy), r * s)); circle_o.append(oid)
    for cx, cy, r, a0, a1 in geo["arcs"]:
        if espejo:
            a0, a1 = giro - a1, giro - a0
        else:
            a0, a1 = a0 + giro, a1 + giro
        arcs.append((*p(cx, cy), r * s, a0, a1)); arc_o.append(oid)
    for x, y in geo["points"]:
        points.append(p(x, y)); point_o.append(oid)
    if curves is not None:
        for x1, y1, x2, y2 in geo["curves"]:
            curves.append((*p(x1, y1), *p(x2, y2))); curve_o.append(oid)
    if targets is not None:
        for x, y, k in geo["targets"]:
            targets.append((*p(x, y), k)); target_o.append(oid)


def _extract_geocad(original, e, oid, segs, seg_o, circles, circle_o, arcs, arc_o,
                    points, point_o, curves=None, curve_o=None, targets=None, target_o=None):
    try:
        if e.dxftype() == "INSERT" and _bloques_activo() and con_referencias(e):
            tr = _transformacion(e)
            if tr is not None:             # el camino rápido: el bloque calculado una vez
                _colocar(_local(original, e), tr, oid, segs, seg_o, circles, circle_o,
                         arcs, arc_o, points, point_o, curves, curve_o, targets, target_o)
            else:                          # escala X distinta de Y: objeto por objeto
                for hijo in e.virtual_entities():
                    _extract_geocad(original, hijo, oid, segs, seg_o, circles, circle_o,
                                    arcs, arc_o, points, point_o, curves, curve_o,
                                    targets, target_o)
    except Exception:  # noqa: BLE001 -- un bloque raro no rompe las referencias
        pass
    return original(e, oid, segs, seg_o, circles, circle_o, arcs, arc_o,
                    points, point_o, curves, curve_o, targets, target_o)


def _envolver_extract(original):
    """SnapEngine._extract: un bloque (INSERT) aporta, además de su punto de
    inserción, la geometría de su contenido, ya colocada (posición, escala,
    giro, simetría; bloques anidados incluidos). Todo queda a nombre del
    bloque, el único objeto que se elige."""
    def _extract(e, oid, segs, seg_o, circles, circle_o, arcs, arc_o, points, point_o,
                 curves=None, curve_o=None, targets=None, target_o=None):
        return _extract_geocad(original, e, oid, segs, seg_o, circles, circle_o,
                               arcs, arc_o, points, point_o, curves, curve_o,
                               targets, target_o)

    _extract._puente_original = original
    _extract._puente_fabrica = _envolver_extract
    return _extract


def instalar_referencias() -> None:
    """Se llama al cargar el plugin. Sin IngeCAD (pruebas sin interfaz) se
    instala igual sobre core.snap, que no usa Qt."""
    try:
        from core.snap import SnapEngine
    except Exception:  # noqa: BLE001
        return
    actual = SnapEngine.__dict__.get("_extract")
    funcion = getattr(actual, "__func__", actual)
    if getattr(funcion, "_puente_fabrica", None) is _envolver_extract:
        return
    funcion = getattr(funcion, "_puente_original", funcion)
    SnapEngine._extract = staticmethod(_envolver_extract(funcion))
    from .dibujo import envolver
    envolver(SnapEngine, "_build", _envolver_build, reemplazar=True)


def _envolver_build(original):
    def _build(self, *args, **kwargs):
        _geometria_local.clear()          # un bloque editado se vuelve a calcular
        _tamanos.clear()
        return original(self, *args, **kwargs)

    _build._puente_original = original
    _build._puente_fabrica = _envolver_build
    return _build
