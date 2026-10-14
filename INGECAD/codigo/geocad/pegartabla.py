# SPDX-License-Identifier: GPL-3.0-or-later
"""PEGARTABLA (GEOPASTETABLE): pegar una tabla copiada en GenOffice, QGIS,
Calc o Excel (3.22.0, módulo «Tablas»).

Un solo botón que mira el portapapeles y reconoce de dónde viene lo copiado
(tablas.detectar). Dos maneras de pegar:

* COMO TABLA: líneas, sombreados y textos, respetando el formato de la
  planilla si lo trae (GenOffice: anchos de columna, alto de fila,
  combinadas, fuente, tamaño, negrita, cursiva, subrayado, color, fondo,
  alineación y el espesor de cada borde, que va al grosor de línea más
  cercano: 0,5 pt -> 0,18 mm, 1 pt -> 0,35 mm). Los textos son MTEXT con el
  formato escrito adentro, como los del editor de texto. Se ubica con DOS
  PUNTOS: el primero es la esquina superior izquierda y el segundo la esquina
  inferior derecha, que acompaña al cursor hasta el clic: la tabla llena ese
  rectángulo, como el TABLE de AutoCAD por ventana (columnas y filas se
  estiran; los textos no se deforman, toman la escala menor); Enter en el segundo punto deja el tamaño natural: en el
  papel, los mm de la planilla en mm de hoja; en el modelo, a la escala
  elegida. Mientras se eligen los puntos se ven las líneas de la tabla,
  ancladas a la referencia a objetos, y una marca en cada punto de
  inserción. Todo queda en un grupo (se elige entera) y se deshace de una vez;
  X (DESCOMPONER) la separa: quedan sólo sus líneas y textos sueltos, sin
  los fondos.
* COMO DIBUJO Y TEXTOS: lo copiado de la tabla de atributos de QGIS trae la
  geometría (wkt_geom): cada objeto se dibuja en su lugar, con los rótulos
  de las columnas elegidas. Una planilla con columnas X / Y (Este / Norte)
  da puntos con su rótulo.

La ventana arranca siempre COMO TABLA, también con lo de QGIS (3.24.0: lo
de QGIS se pega como lo de una planilla; el dibujo, si se elige).
PEGARDESDEQGIS (GEOPASTEQGIS, 3.24.0) es el mismo PEGARTABLA con su propio
botón (una tablita que viene de QGIS): filas de la tabla de atributos o una
tabla de una composición («Copiar tabla» en QGIS, con su formato).

Sin Qt sólo quedan las cuentas (comando_tabla, comando_dibujo): las pruebas
las usan sin abrir ventanas.
"""
from __future__ import annotations

from core import actions
from core.commands import Command, CompositeCommand
from tools.base import Tool

from . import config, modulos, tablas

CAPA_TABLA = "GEOCAD-TABLAS"
CAPA_DIBUJO = "GEOCAD-PEGADO"
DESCRIPCION = "GeoCAD Yaguaret\u00e9: tabla pegada"
PROGRAMA = "ingecad"
_ATTACH = {("arriba", "izquierda"): 1, ("arriba", "centro"): 2, ("arriba", "derecha"): 3,
           ("medio", "izquierda"): 4, ("medio", "centro"): 5, ("medio", "derecha"): 6,
           ("abajo", "izquierda"): 7, ("abajo", "centro"): 8, ("abajo", "derecha"): 9}


# ------------------------------------------------------------------ el portapapeles
def leer_portapapeles() -> tuple:
    """(html, texto, url) de lo que hay en el portapapeles del sistema."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # noqa: BLE001
        return "", "", ""
    board = QApplication.clipboard()
    data = board.mimeData() if board is not None else None
    if data is None:
        return "", "", ""
    html = data.html() if data.hasHtml() else ""
    texto = data.text() if data.hasText() else ""
    url = ""
    if data.hasFormat("chromium/x-source-url"):
        try:
            url = bytes(data.data("chromium/x-source-url")).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            url = ""
    return html, texto, url


def tabla_del_portapapeles():
    html, texto, url = leer_portapapeles()
    return tablas.leer(html, texto, url)


# ------------------------------------------------------------------ texto MTEXT
def _escapar(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def contenido_mtext(tx: tablas.Texto) -> str:
    """El texto de la celda con su fuente, negrita, cursiva y subrayado
    escritos adentro, como los escribe el editor de texto de IngeCAD."""
    cuerpo = "\\P".join(_escapar(r) for r in tx.texto.split("\n"))
    if tx.subrayado:
        cuerpo = "\\L" + cuerpo + "\\l"
    if tx.fuente or tx.negrita or tx.cursiva:
        fuente = (tx.fuente or "Arial").replace(";", "").replace("|", "")
        cuerpo = "{\\f%s|b%d|i%d;%s}" % (fuente, int(tx.negrita), int(tx.cursiva), cuerpo)
    return cuerpo


# ------------------------------------------------------------------ medir con la fuente real
def _fuente_estilo(document) -> str:
    """El archivo de fuente del estilo Standard del dibujo ("" si no se sabe)."""
    try:
        doc = getattr(document, "doc", document)
        return str(doc.styles.get("Standard").dxf.get("font", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def medidor(document=None):
    """medir(texto, alto, negrita, cursiva, fuente) -> mm para tablas.armar,
    con la fuente con que IngeCAD dibuja el MTEXT (3.23.0): la misma búsqueda
    que el dibujo de ezdxf (find_best_match con los parches de IngeCAD, que
    ponen Liberation Sans por Arial, etc.). Sin \\f en el texto (estilo
    GeoCAD sin negrita) manda la fuente del estilo Standard. None si ezdxf no
    tiene fuentes: queda la cuenta aproximada."""
    try:
        from ezdxf.fonts import fonts
    except Exception:  # noqa: BLE001
        return None
    try:
        from core import ezdxf_patches
        ezdxf_patches.apply()
    except Exception:  # noqa: BLE001 -- otra versión de IngeCAD: ezdxf tal cual
        pass
    estilo = _fuente_estilo(document)
    archivos = {}

    def archivo(fuente: str, negrita: bool, cursiva: bool) -> str:
        clave = (fuente, negrita, cursiva)
        if clave not in archivos:
            nombre = ""
            if fuente or negrita or cursiva:     # contenido_mtext escribe \f
                cara = fonts.find_best_match(family=fuente or "Arial",
                                             weight=700 if negrita else 400, italic=cursiva)
                nombre = cara.filename if cara is not None else ""
            elif estilo:
                try:
                    nombre = fonts.resolve_font_face(estilo).filename
                except Exception:  # noqa: BLE001
                    nombre = ""
            if not nombre:                  # como el dibujo: la fuente de reserva de ezdxf
                try:
                    nombre = fonts.font_manager.fallback_font_name()
                except Exception:  # noqa: BLE001
                    nombre = ""
            archivos[clave] = nombre
        return archivos[clave]

    def medir(texto: str, alto: float, negrita: bool = False, cursiva: bool = False,
              fuente: str = ""):
        nombre = archivo(fuente, negrita, cursiva)
        if not nombre:
            return None
        return fonts.make_font(nombre, alto).text_width(texto)

    return medir


# ------------------------------------------------------------------ fábricas de objetos
def _color_dxf(entity, hexa: str) -> None:
    """Negro -> color 7 (blanco/negro según el fondo, como AutoCAD); otro ->
    color verdadero; vacío -> PorCapa."""
    if not hexa:
        return
    if hexa == "#000000":
        entity.dxf.color = 7
        return
    entity.rgb = tablas.rgb(hexa)


def objetos_tabla(armado: tablas.Armado, origen, k: float, ky: float | None = None) -> list:
    """Fábricas factory(msp) -> entidad de la tabla con la esquina superior
    izquierda en ``origen`` y ``k`` unidades del dibujo por mm (``ky`` a lo
    alto si es otra: la tabla llena una ventana; los textos no se deforman,
    toman la menor). Primero los fondos (quedan debajo), después las líneas
    y los textos."""
    ox, oy = float(origen[0]), float(origen[1])
    kx = float(k)
    ky = kx if ky is None else float(ky)
    kt = min(kx, ky)

    def P(x, y):
        return (ox + x * kx, oy + y * ky)

    fabricas = []
    for f in armado.fondos:
        def fondo(msp, f=f):
            h = msp.add_hatch()
            h.set_solid_fill(rgb=tablas.rgb(f.color))
            h.paths.add_polyline_path([P(f.x0, f.y0), P(f.x1, f.y0), P(f.x1, f.y1),
                                       P(f.x0, f.y1)], is_closed=True)
            return h
        fabricas.append(fondo)
    for ln in armado.lineas:
        def linea(msp, ln=ln):
            e = msp.add_line(P(ln.x0, ln.y0), P(ln.x1, ln.y1),
                             dxfattribs={"lineweight": tablas.grosor_dxf(ln.grosor_mm)})
            _color_dxf(e, ln.color)
            return e
        fabricas.append(linea)
    for tx in armado.textos:
        def texto(msp, tx=tx):
            e = msp.add_mtext(contenido_mtext(tx), dxfattribs={
                "char_height": max(tx.alto_mm * kt, 1e-9),
                "attachment_point": _ATTACH[(tx.alin_v, tx.alin_h)],
                "insert": P(tx.x, tx.y)})
            _color_dxf(e, tx.color)
            return e
        fabricas.append(texto)
    return fabricas


class CapaCommand(Command):
    """Crea la capa si no existe (y la quita al deshacer si la creó)."""

    name = "capa"

    def __init__(self, nombre: str, color: int = 7) -> None:
        self.nombre, self.color, self._creada = nombre, color, False

    def do(self, document) -> None:
        if self.nombre not in document.doc.layers:
            document.doc.layers.add(self.nombre, color=self.color)
            self._creada = True

    def undo(self, document) -> None:
        if self._creada:
            try:
                document.doc.layers.remove(self.nombre)
            except Exception:  # noqa: BLE001
                pass
            self._creada = False


class AgruparCommand(Command):
    """Junta en un grupo lo que crearon los comandos anteriores (seleccionar
    una línea de la tabla elige la tabla entera)."""

    name = "grupo"

    def __init__(self, base: str, comandos) -> None:
        self.base, self.comandos, self.nombre = base, list(comandos), ""

    def do(self, document) -> None:
        grupos = document.doc.groups
        n = 1
        while f"{self.base}{n}" in grupos:
            n += 1
        self.nombre = f"{self.base}{n}"
        entidades = [c.entity for c in self.comandos if getattr(c, "entity", None) is not None]
        grupo = grupos.new(self.nombre, description="GeoCAD Yaguareté: tabla pegada")
        with grupo.edit_data() as data:
            data.extend(entidades)

    def undo(self, document) -> None:
        try:
            document.doc.groups.delete(self.nombre)
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ descomponer (X)
def grupos_tabla(entidades) -> list:
    """Los nombres de las tablas pegadas (grupos de GeoCAD) que tienen alguno
    de estos objetos."""
    handles = {e.dxf.handle for e in entidades}
    docs = {id(e.doc): e.doc for e in entidades if getattr(e, "doc", None) is not None}
    nombres = []
    for doc in docs.values():
        for nombre, grupo in doc.groups:
            if grupo.dxf.get("description", "") != DESCRIPCION:
                continue
            if any(m.dxf.handle in handles for m in grupo):
                nombres.append(nombre)
    return nombres


class DesagruparCommand(Command):
    """Saca el grupo de las tablas y borra sus fondos (sombreados): quedan
    SÓLO sus líneas y textos sueltos, cada uno con su capa, grosor, fuente y
    color (pedido de Fernando: «nada de sombreados y fondos al explotar»).
    Deshacer vuelve a poner los fondos y a armar el grupo."""

    name = "descomponer tabla"

    def __init__(self, nombres) -> None:
        self.nombres, self._quitados = list(nombres), []

    def do(self, document) -> None:
        self._quitados = []
        espacio = self.space(document)
        grupos = document.doc.groups
        borrados = []
        for nombre in self.nombres:
            if nombre not in grupos:
                continue
            miembros = list(grupos.get(nombre))
            grupos.delete(nombre)
            fondos = [m for m in miembros if m.dxftype() == "HATCH"]
            for f in fondos:
                espacio.unlink_entity(f)          # se guarda para deshacer
            borrados += [f.dxf.handle for f in fondos]
            self._quitados.append((nombre, miembros, fondos))
        self.removed_handles = borrados
        document.dirty = True

    def undo(self, document) -> None:
        espacio = self.space(document)
        for nombre, miembros, fondos in self._quitados:
            for f in fondos:
                espacio.add_entity(f)
            grupo = document.doc.groups.new(nombre, description=DESCRIPCION)
            with grupo.edit_data() as data:
                data.extend(miembros)
        self._quitados = []
        document.dirty = True


def descomponer(entidades) -> tuple:
    """(comando, tablas, otros objetos que X descompone como siempre) o
    (None, 0, ...) si entre lo elegido no hay ninguna tabla pegada."""
    nombres = grupos_tabla(entidades)
    if not nombres:
        return None, 0, list(entidades)
    miembros = set()
    for e in entidades:
        doc = getattr(e, "doc", None)
        if doc is not None:
            for nombre in nombres:
                if nombre in doc.groups:
                    miembros |= {m.dxf.handle for m in doc.groups.get(nombre)}
            break
    resto = [e for e in entidades if e.dxf.handle not in miembros
             and e.dxftype() in ("INSERT", "LWPOLYLINE", "POLYLINE")]
    comandos = [DesagruparCommand(nombres)]
    if resto:
        comandos.append(actions.explode_entities(resto))
    return CompositeCommand("EXPLODE", comandos), len(nombres), resto


def _envolver_explode(original):
    def on_selection(self, entities):
        if not modulos.activo(PROGRAMA, "tablas"):
            return original(self, entities)
        try:
            cmd, n, resto = descomponer(entities)
        except Exception:  # noqa: BLE001 -- ante cualquier duda, X como venía
            cmd = None
        if cmd is None:
            return original(self, entities)
        self.ctx.execute(cmd)
        otros = f"; además {len(resto)} objeto(s) descompuesto(s)" if resto else ""
        self.ctx.echo(f"{n} tabla(s) descompuesta(s): quedan sólo sus líneas y textos sueltos, "
                      f"sin fondos{otros}. U la vuelve a armar.")
        self.ctx.finish()
    on_selection._puente_original = original
    on_selection._puente_fabrica = _envolver_explode
    return on_selection


def instalar() -> None:
    """X (DESCOMPONER) sobre una tabla pegada la separa en líneas y textos."""
    try:
        from tools.blocks import ExplodeTool
    except Exception:  # noqa: BLE001
        return
    from .dibujo import envolver
    if getattr(ExplodeTool.on_selection, "_puente_fabrica", None) is not _envolver_explode:
        envolver(ExplodeTool, "on_selection", _envolver_explode, reemplazar=True)


def comando_tabla(armado: tablas.Armado, origen, k: float, capa: str = CAPA_TABLA,
                  agrupar: bool = True, ky: float | None = None) -> CompositeCommand:
    """La tabla entera como UN paso de deshacer."""
    agregar = [actions.AddEntityCommand("GEOPASTETABLE", f, layer=capa)
               for f in objetos_tabla(armado, origen, k, ky)]
    comandos = [CapaCommand(capa)] + agregar
    if agrupar and agregar:
        comandos.append(AgruparCommand("TABLA", agregar))
    return CompositeCommand("pegar tabla", comandos)


# ------------------------------------------------------------------ como dibujo y textos
def _rotulo(fila, columnas) -> str:
    partes = [fila[i].strip() for i in columnas if 0 <= i < len(fila) and fila[i].strip()]
    return "\n".join(partes)


def comando_dibujo(tabla: tablas.Tabla, rotulos=(), alto: float = 2.5, capa: str = CAPA_DIBUJO,
                   col_x: int = -1, col_y: int = -1) -> tuple:
    """(comando, objetos dibujados, filas sin geometría): cada fila de la
    tabla en su lugar, con el rótulo de las columnas ``rotulos`` (índices).
    La geometría sale de wkt_geom (QGIS) o de las columnas X / Y."""
    grilla = tabla.grilla()
    col_geo = tabla.columna("wkt_geom")
    fabricas, sin_geo = [], 0
    for fila in grilla[1:]:
        partes = []
        if col_geo >= 0:
            partes = tablas.wkt_partes(fila[col_geo] if col_geo < len(fila) else "")
        elif col_x >= 0 and col_y >= 0:
            x = tablas.numero(fila[col_x]) if col_x < len(fila) else None
            y = tablas.numero(fila[col_y]) if col_y < len(fila) else None
            if x is not None and y is not None:
                partes = [("punto", [(x, y)])]
        if not partes:
            sin_geo += 1
            continue
        for tipo, datos in partes:
            if tipo == "punto":
                fabricas.append(lambda msp, p=datos[0]: msp.add_point(p))
            elif tipo == "linea" and len(datos) >= 2:
                fabricas.append(lambda msp, pts=datos: msp.add_lwpolyline(pts))
            elif tipo == "poligono":
                for anillo in datos:
                    pts = anillo[:-1] if len(anillo) > 1 and anillo[0] == anillo[-1] else anillo
                    if len(pts) >= 2:
                        fabricas.append(lambda msp, pts=pts: msp.add_lwpolyline(pts, close=True))
        texto = _rotulo(fila, rotulos)
        lugar = tablas.punto_rotulo(partes)
        if texto and lugar is not None:
            solo_punto = all(t == "punto" for t, _ in partes)
            tx = tablas.Texto(lugar[0] + (alto * 0.6 if solo_punto else 0.0), lugar[1],
                              "izquierda" if solo_punto else "centro", "medio", alto, texto)

            def rot(msp, tx=tx):
                return msp.add_mtext(contenido_mtext(tx), dxfattribs={
                    "char_height": tx.alto_mm,
                    "attachment_point": _ATTACH[(tx.alin_v, tx.alin_h)],
                    "insert": (tx.x, tx.y)})
            fabricas.append(rot)
    agregar = [actions.AddEntityCommand("GEOPASTETABLE", f, layer=capa) for f in fabricas]
    return CompositeCommand("pegar como dibujo", [CapaCommand(capa)] + agregar), len(agregar), sin_geo


# ------------------------------------------------------------------ escala
def unidades_por_mm(document, escala_modelo: float) -> float:
    """Unidades del dibujo por mm de la tabla con el tamaño natural: en el
    papel, la escala de su configuración de página; en el modelo, 1 mm de
    hoja a la escala 1:``escala_modelo`` en las unidades del dibujo."""
    from . import papel

    nombre = getattr(document, "active_layout", None)
    if nombre is not None:
        try:
            return papel.unidades_por_mm(document.doc.layouts.get(nombre))
        except Exception:  # noqa: BLE001
            return 1.0
    mm = papel.mm_por_unidad(document) or 1.0          # sin unidades: mm
    return max(escala_modelo, 1e-9) / mm


def escala_predeterminada() -> float:
    try:
        e = float(config.get("escala_rotulos") or 0)
    except Exception:  # noqa: BLE001
        e = 0.0
    return e if e > 0 else 100.0


# ------------------------------------------------------------------ la orden
class PegarTablaTool(Tool):
    """PEGARTABLA: lo que hay en el portapapeles, como tabla o como dibujo."""

    PRIMERO = "Esquina superior izquierda de la tabla:"
    SEGUNDO = "Esquina inferior derecha (la tabla llena el rectángulo) o Enter para el tamaño natural:"

    NOMBRE = "GEOPASTETABLE"
    SIN_TABLA = ("GeoCAD Yaguareté: el portapapeles no tiene una tabla. Copie celdas en "
                 "GenOffice, Calc o Excel, o filas de la tabla de atributos de QGIS (Ctrl+C).")

    def start(self) -> None:
        self.name = self.NOMBRE
        self._p1 = None
        tabla = tabla_del_portapapeles()
        if tabla is None:
            self.ctx.echo(self.SIN_TABLA)
            self.ctx.finish()
            return
        self.avisar_origen(tabla)
        window = getattr(self.ctx.services, "window", None)
        opciones = pedir_opciones(window, tabla)
        if not opciones:
            self.ctx.finish()
            return
        self.empezar(tabla, opciones, getattr(window, "document", None))

    def avisar_origen(self, tabla) -> None:
        pass

    def empezar(self, tabla, opciones: dict, document) -> None:
        """Después de la ventana (las pruebas llaman acá directamente)."""
        self._opciones = opciones
        nombre = tablas.ORIGENES.get(tabla.origen, tabla.origen)
        if opciones["modo"] == "dibujo":
            cmd, n, sin_geo = comando_dibujo(tabla, opciones.get("rotulos", ()),
                                             opciones.get("alto_rotulo", 2.5),
                                             opciones.get("capa") or CAPA_DIBUJO,
                                             opciones.get("col_x", -1), opciones.get("col_y", -1))
            if not n:
                self.ctx.echo("GeoCAD Yaguareté: ninguna fila trae geometría ni coordenadas X / Y.")
                self.ctx.finish()
                return
            self.ctx.execute(cmd)
            extra = f"; {sin_geo} fila(s) sin geometría quedaron afuera" if sin_geo else ""
            self.ctx.echo(f"Tabla de {nombre} pegada como dibujo: {n} objeto(s) en la capa "
                          f"{opciones.get('capa') or CAPA_DIBUJO}{extra}. U la quita.")
            self.ctx.finish()
            return
        quitar = opciones.get("quitar", ())
        t = tablas.sin_columnas(tabla, quitar) if quitar else tabla
        self._armado = tablas.armar(t, opciones.get("respetar", True), opciones.get("alto", 2.5),
                                    opciones.get("encabezado", True), medir=medidor(document))
        self._k0 = unidades_por_mm(document, opciones.get("escala", 100.0)) if document is not None \
            else 1.0
        self._nombre = nombre
        self.prompt(self.PRIMERO)

    # -- la vista previa: sólo las líneas de la tabla (pedido de Fernando,
    # 14/10/2026), ancladas al punto que da la referencia a objetos
    def ortho_applies(self) -> bool:
        return self._p1 is None

    def ventana(self, punto) -> tuple:
        """(esquina superior izquierda, k a lo ancho, k a lo alto) de la tabla
        que llena el rectángulo entre el primer punto y ``punto``: la esquina
        opuesta queda EN el punto, como el TABLE de AutoCAD por ventana
        (pedido de Fernando: el segundo punto acompaña la esquina inferior
        derecha hasta el clic). Un rectángulo sin ancho o sin alto toma la
        escala del otro lado; sin ninguno, el tamaño natural."""
        a = self._armado
        (x0, y0), (x1, y1) = self._p1, (float(punto[0]), float(punto[1]))
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        kx = dx / a.ancho_mm if a.ancho_mm > 0 and dx > 1e-12 else None
        ky = dy / a.alto_mm if a.alto_mm > 0 and dy > 1e-12 else None
        if kx is None and ky is None:
            return self._p1, self._k0, self._k0
        kx = kx if kx is not None else ky
        ky = ky if ky is not None else kx
        origen = (min(x0, x1) if dx > 1e-12 else x0, max(y0, y1) if dy > 1e-12 else y0)
        return origen, kx, ky

    def preview_segments(self, cursor) -> list:
        """Las líneas de la tabla donde quedaría: antes del primer punto, con
        la esquina superior izquierda en el cursor y el tamaño natural;
        después, llenando el rectángulo del primer punto al cursor, con la
        esquina inferior derecha en el cursor. Una marca cuadrada en cada
        punto de inserción."""
        a = getattr(self, "_armado", None)
        if a is None or cursor is None:
            return []
        if self._p1 is None:
            (ox, oy), kx, ky = (float(cursor[0]), float(cursor[1])), self._k0, self._k0
        else:
            (ox, oy), kx, ky = self.ventana(cursor)
        segs = [((ox + l.x0 * kx, oy + l.y0 * ky), (ox + l.x1 * kx, oy + l.y1 * ky))
                for l in a.lineas]
        x1, y1 = ox + a.ancho_mm * kx, oy - a.alto_mm * ky
        if not segs:                                   # una tabla sin bordes: su contorno
            segs = [((ox, oy), (x1, oy)), ((x1, oy), (x1, y1)), ((x1, y1), (ox, y1)),
                    ((ox, y1), (ox, oy))]
        lado = max(min(a.ancho_mm * kx, a.alto_mm * ky) * 0.04, 1e-9)
        esquinas = [(ox, oy)] if self._p1 is None else [self._p1, (float(cursor[0]), float(cursor[1]))]
        for cx, cy in esquinas:
            segs += [((cx - lado, cy - lado), (cx + lado, cy - lado)),
                     ((cx + lado, cy - lado), (cx + lado, cy + lado)),
                     ((cx + lado, cy + lado), (cx - lado, cy + lado)),
                     ((cx - lado, cy + lado), (cx - lado, cy - lado))]
        return segs

    def on_point(self, point) -> None:
        if getattr(self, "_armado", None) is None:
            return
        if self._p1 is None:
            self._p1 = (float(point[0]), float(point[1]))
            self.last_point = self._p1
            self.prompt(self.SEGUNDO)
            return
        self._pegar(*self.ventana(point))

    def on_enter(self) -> None:
        if getattr(self, "_armado", None) is not None and self._p1 is not None:
            self._pegar(self._p1, self._k0, self._k0)
            return
        self.ctx.finish()

    def _pegar(self, origen, kx: float, ky: float) -> None:
        capa = self._opciones.get("capa") or CAPA_TABLA
        self.ctx.execute(comando_tabla(self._armado, origen, kx, capa, ky=ky))
        a = self._armado
        self.ctx.echo(f"Tabla de {self._nombre} pegada: {a.ancho_mm * kx:.3g} × {a.alto_mm * ky:.3g} "
                      f"unidades, {len(a.textos)} texto(s), en la capa {capa} (un grupo). U la quita.")
        self.ctx.finish()


class PegarDesdeQgisTool(PegarTablaTool):
    """PEGARDESDEQGIS (3.24.0): el mismo PEGARTABLA, con el botón de la tablita
    que viene de QGIS. Filas de la tabla de atributos (Ctrl+C) o una tabla de
    una composición («Copiar tabla» en su barra GeoCAD Yaguareté)."""

    NOMBRE = "GEOPASTEQGIS"
    SIN_TABLA = ("GeoCAD Yaguareté: el portapapeles no tiene una tabla. En QGIS, copie filas "
                 "de la tabla de atributos (Ctrl+C) o use «Copiar tabla» en la barra GeoCAD "
                 "Yaguareté de la composición.")

    def avisar_origen(self, tabla) -> None:
        if not tabla.origen.startswith("qgis"):
            nombre = tablas.ORIGENES.get(tabla.origen, tabla.origen)
            self.ctx.echo(f"GeoCAD Yaguareté: lo copiado no viene de QGIS (viene de {nombre}); "
                          "se pega igual.")


def pedir_opciones(window, tabla):
    """La ventana de Pegar tabla. None = cancelado."""
    from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
                                   QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                                   QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                                   QListWidgetItem, QRadioButton, QVBoxLayout)
    from PySide6.QtCore import Qt

    dlg = QDialog(window)
    dlg.setWindowTitle("Pegar tabla - GeoCAD Yaguareté")
    caja = QVBoxLayout(dlg)
    nombre = tablas.ORIGENES.get(tabla.origen, tabla.origen)
    encabezados = [h or f"Columna {i + 1}" for i, h in enumerate(tabla.encabezados())]
    col_geo = tabla.columna("wkt_geom")
    cx, cy = tablas.columnas_xy(tabla)
    puede_dibujo = col_geo >= 0 or cx >= 0
    detalle = f"{tabla.n_filas} fila(s) × {tabla.n_cols} columna(s)"
    if tabla.con_formato:
        detalle += ", con formato"
    if col_geo >= 0:
        detalle += ", con geometría (wkt_geom)"
    caja.addWidget(QLabel(f"<b>Copiado de {nombre}</b>: {detalle}."))

    modo_tabla = QRadioButton("Como tabla (líneas y textos; se ubica con dos puntos)")
    modo_dibujo = QRadioButton("Como dibujo y textos (cada objeto en su lugar, con rótulos)")
    grupo_modo = QButtonGroup(dlg)
    grupo_modo.addButton(modo_tabla)
    grupo_modo.addButton(modo_dibujo)
    modo_dibujo.setEnabled(puede_dibujo)
    modo_tabla.setChecked(True)          # como una planilla (3.24.0); el dibujo, si se elige
    caja.addWidget(modo_tabla)
    caja.addWidget(modo_dibujo)

    # -- columnas (las dos maneras)
    caja.addWidget(QLabel("Columnas (las marcadas van a la tabla / al rótulo):"))
    lista = QListWidget()
    lista.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    for i, h in enumerate(encabezados):
        it = QListWidgetItem(h)
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Unchecked if i == col_geo else Qt.CheckState.Checked)
        lista.addItem(it)
    lista.setMaximumHeight(150)
    caja.addWidget(lista)

    # -- como tabla
    g_tabla = QGroupBox("Como tabla")
    f1 = QFormLayout(g_tabla)
    respetar = QCheckBox("Respetar el formato de la planilla (anchos, letras, colores, bordes)")
    respetar.setChecked(tabla.con_formato)
    respetar.setEnabled(tabla.con_formato)
    encabezado = QCheckBox("Primera fila como encabezado (en negrita)")
    encabezado.setChecked(True)
    alto = QDoubleSpinBox()
    alto.setRange(0.5, 50.0)
    alto.setDecimals(2)
    alto.setValue(2.5)
    alto.setSuffix(" mm")
    escala = QDoubleSpinBox()
    escala.setRange(1.0, 1e7)
    escala.setDecimals(0)
    escala.setValue(escala_predeterminada())
    escala.setPrefix("1:")
    capa_t = QLineEdit(CAPA_TABLA)
    f1.addRow(respetar)
    f1.addRow(encabezado)
    f1.addRow("Altura de texto (sin el formato):", alto)
    f1.addRow("Escala en el modelo (para Enter):", escala)
    f1.addRow("Capa:", capa_t)
    caja.addWidget(g_tabla)

    # -- como dibujo
    g_dib = QGroupBox("Como dibujo y textos")
    f2 = QFormLayout(g_dib)
    combo_x, combo_y = QComboBox(), QComboBox()
    for cb in (combo_x, combo_y):
        cb.addItems(encabezados)
    if cx >= 0:
        combo_x.setCurrentIndex(cx)
        combo_y.setCurrentIndex(cy)
    alto_r = QDoubleSpinBox()
    alto_r.setRange(0.001, 1e6)
    alto_r.setDecimals(3)
    alto_r.setValue(2.5)
    capa_d = QLineEdit(CAPA_DIBUJO)
    if col_geo < 0:
        f2.addRow("Columna X (Este):", combo_x)
        f2.addRow("Columna Y (Norte):", combo_y)
    f2.addRow("Altura del rótulo (unidades del dibujo):", alto_r)
    f2.addRow("Capa:", capa_d)
    caja.addWidget(g_dib)

    def marcar(es_tabla):
        """Como tabla van todas las columnas (menos la geometría); como
        rótulo, de entrada sólo la primera que no es geometría."""
        primera = next((i for i in range(len(encabezados)) if i != col_geo), -1)
        for i in range(lista.count()):
            si = (i != col_geo) if es_tabla else (i == primera)
            lista.item(i).setCheckState(Qt.CheckState.Checked if si else Qt.CheckState.Unchecked)

    def actualizar():
        es_tabla = modo_tabla.isChecked()
        g_tabla.setVisible(es_tabla)
        g_dib.setVisible(not es_tabla)
        alto.setEnabled(not respetar.isChecked())
        encabezado.setEnabled(not respetar.isChecked())

    marcar(modo_tabla.isChecked())
    modo_tabla.toggled.connect(marcar)
    modo_tabla.toggled.connect(actualizar)
    respetar.toggled.connect(actualizar)
    actualizar()
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    caja.addWidget(botones)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    marcadas = [i for i in range(lista.count())
                if lista.item(i).checkState() == Qt.CheckState.Checked]
    if modo_dibujo.isChecked():
        return {"modo": "dibujo", "rotulos": [i for i in marcadas if i != col_geo],
                "alto_rotulo": alto_r.value(), "capa": capa_d.text().strip() or CAPA_DIBUJO,
                "col_x": combo_x.currentIndex() if col_geo < 0 else -1,
                "col_y": combo_y.currentIndex() if col_geo < 0 else -1}
    return {"modo": "tabla", "quitar": [i for i in range(tabla.n_cols) if i not in marcadas],
            "respetar": respetar.isChecked(), "encabezado": encabezado.isChecked(),
            "alto": alto.value(), "escala": escala.value(),
            "capa": capa_t.text().strip() or CAPA_TABLA}
