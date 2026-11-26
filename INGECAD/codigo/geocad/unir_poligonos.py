# SPDX-License-Identifier: GPL-3.0-or-later
"""UNIR (JOIN, J) con polígonos, para IngeCAD (3.96.0).

Pedido de Fernando (26/11/2026): que UNIR, con polígonos, actúe como
«Combinar objetos espaciales» de QGIS, igual en IngeCAD y en QGIS:
  - los polígonos (polilíneas cerradas, círculos) que se tocan quedan en uno,
    con los datos del de MAYOR superficie;
  - se rellenan los huecos encerrados entre ellos (las ranuras que quedan
    cuando se tocan en los vértices y se separan en algún trayecto); los
    huecos que ya tenía cada uno se respetan;
  - los grupos aislados quedan aparte, cada uno con los datos de su mayor;
  - al terminar pregunta «¿Quiere crear una capa nueva con el resultado?
    [Sí/No] <No>» (3.97.2): No o Enter, en la misma capa (3.96.1); Sí, en la
    capa «combinados de <capa>» (la original no se toca). Las siguientes UNIR
    con Sí sobre la misma capa van a esa misma capa combinada (y a su misma
    tabla), no a otra.

Con líneas (o un solo polígono) es el UNIR de IngeCAD, sin cambios.

Los datos:
  - polígono vinculado a QGIS (SHP/GPKG conectado): al modificar la original
    el mayor conserva su registro; los demás se borran al devolver la capa; una
    isla más del mismo objeto pasa a ser un registro nuevo con sus datos (como
    una copia). En la capa nueva, los datos viajan en cada objeto (como los de
    IMPORTARSHP, tabla «combinados de <capa>»), sin vínculo: la capa conectada
    y su archivo no se tocan.
  - importado con base de datos (IMPORTARSHP): igual, en su tabla o en la
    tabla nueva.
  - sin datos: sólo la geometría.

La cuenta está en el núcleo (combinar.py), la misma que usa QGIS. Los arcos
de las polilíneas pasan a tramos rectos (cada 7,5°), como en QGIS.
"""
from __future__ import annotations

from core.commands import CompositeCommand
from core.layers import NewLayerCommand

from core import actions
from tools.modify import JoinTool

from . import combinar as C
from .modelo import AddToModelCommand

ROJO = 1                    # color ACI de la capa nueva


# -- geometría de las entidades ---------------------------------------------------------
def es_poligono(e) -> bool:
    t = e.dxftype()
    if t == "CIRCLE":
        return True
    if t == "LWPOLYLINE":
        if e.closed:
            return len(e) >= 3
        pts = [tuple(p[:2]) for p in e.get_points("xy")]
        return len(pts) >= 4 and pts[0] == pts[-1]
    return False


def anillo(e):
    """La entidad como anillo de (x, y), con los arcos en tramos."""
    from .empalme import arco_en_tramos, tramo_en_segmentos
    import math

    if e.dxftype() == "CIRCLE":
        c, r = e.dxf.center, e.dxf.radius
        return [a for a, _b in arco_en_tramos((c.x, c.y), r, 0.0, 2 * math.pi)]
    filas = [tuple(f) for f in e.get_points("xyseb")]
    if len(filas) > 1 and filas[0][:2] == filas[-1][:2]:
        filas = filas[:-1]
    pts = []
    n = len(filas)
    for i in range(n):
        for a, _b in tramo_en_segmentos(filas[i], filas[(i + 1) % n], filas[i][4]):
            pts.append((float(a[0]), float(a[1])))
    return pts


# -- a qué objeto (registro) pertenece cada entidad ---------------------------------------
def _clave(document, e):
    """('sig', capa, fid), ('imp', tabla, fid) o ('ent', handle)."""
    from . import enlace

    tag = enlace.feat_tag(e)
    if tag is not None:
        return ("sig", tag.key, tag.fid)
    try:
        from . import importados

        leido = importados._leer(e)
    except Exception:  # noqa: BLE001
        leido = None
    if leido is not None and leido[1] is not None:
        return ("imp", leido[0], leido[1])
    return ("ent", e.dxf.handle)


def objetos_de(document, entidades):
    """Los objetos de los polígonos designados: [(clave, [entidades])]. Un
    registro con varias partes (o con huecos dibujados) es UN objeto, con todas
    sus polilíneas cerradas del dibujo, aunque se haya designado sólo una."""
    claves, orden = {}, []
    for e in entidades:
        if not es_poligono(e):
            continue
        k = _clave(document, e)
        if k not in claves:
            claves[k] = []
            orden.append(k)
        claves[k].append(e)
    faltan = {k for k in orden if k[0] in ("sig", "imp")}
    if faltan:
        vistos = {e.dxf.handle for es in claves.values() for e in es}
        for e in document.doc.modelspace():
            if e.dxf.handle in vistos or not es_poligono(e):
                continue
            k = _clave(document, e)
            if k in faltan:
                claves[k].append(e)
    return [(k, claves[k]) for k in orden]


# -- las entidades nuevas ---------------------------------------------------------------
def _copiar_xdata(origen, destino) -> None:
    from . import enlace

    try:
        from .importados import APPID_ATRIB
    except Exception:  # noqa: BLE001
        APPID_ATRIB = None
    for appid in (enlace.APPID, APPID_ATRIB):
        if appid and origen.has_xdata(appid):
            destino.set_xdata(appid, list(origen.get_xdata(appid)))


def _polilinea(msp, modelo, pts, capa=None):
    """Una polilínea cerrada con ``pts``, con las propiedades (y datos) de ``modelo``."""
    if modelo.dxftype() == "LWPOLYLINE":
        e = modelo.copy()
        e.set_points([(x, y) for x, y in pts], format="xy")
        e.closed = True
        msp.add_entity(e)
    else:
        attribs = {k: modelo.dxf.get(k) for k in ("layer", "color", "linetype", "lineweight",
                                                   "true_color", "ltscale")
                   if modelo.dxf.hasattr(k)}
        e = msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs=attribs)
        _copiar_xdata(modelo, e)
    if capa is not None:
        e.dxf.layer = capa
        e.dxf.color = 256                   # PorCapa: el rojo de la capa nueva (3.96.1)
        if e.dxf.hasattr("true_color"):
            e.dxf.discard("true_color")
    return e


def fabrica(modelo, pts, parte=None, capa=None, datos=None):
    """factory(msp) para ReplaceEntitiesCommand / AddToModelCommand.
    ``parte``: número de parte del vínculo con QGIS (huecos). ``datos``:
    (tabla, campos, valores, fid) para la capa nueva (sin vínculo)."""
    def make(msp):
        from . import enlace

        e = _polilinea(msp, modelo, pts, capa)
        tag = enlace.feat_tag(e)
        if datos is not None or capa is not None:
            enlace.clear_feat_tag(e)           # la capa nueva no queda vinculada
            try:
                from .importados import APPID_ATRIB
                e.discard_xdata(APPID_ATRIB)
            except Exception:  # noqa: BLE001
                pass
            if datos is not None:
                from .importados import poner_atributos
                tabla, campos, valores, fid = datos
                poner_atributos(e, tabla, campos, valores, fid)
        elif parte is not None and tag is not None:
            enlace.set_feat_tag(e, tag.key, tag.fid, parte)
        return e
    return make


def _campos_y_valores(document, clave, modelo):
    """(campos, valores) del objeto que da los datos, o None si no tiene."""
    from . import shpio

    if clave[0] == "imp":
        from .importados import _leer
        leido = _leer(modelo)
        if leido is None:
            return None
        campos = [shpio.DbfField(n, t[0], int(t[1]), int(t[2]), 0) for n, t, _v in leido[2]]
        return campos, {n: v for n, _t, v in leido[2]}
    if clave[0] == "sig":
        from . import datos

        try:
            capa = datos.layer_data(document, clave[1])
        except Exception:  # noqa: BLE001
            return None
        fila = capa.row(clave[2])
        tipos = {}
        if capa.link.fmt != "gpkg":
            try:
                tipos = {f.name: f for f in shpio.Shapefile(capa.link.path).fields}
            except Exception:  # noqa: BLE001
                tipos = {}
        campos, valores = [], {}
        for f in capa.fields:
            if f.name in tipos:
                d = tipos[f.name]
                campos.append(shpio.DbfField(d.name, d.type, d.size, d.decimals, 0))
            else:
                t, s, dec = {"int": ("N", 18, 0), "real": ("N", 24, 8), "date": ("D", 8, 0),
                             "bool": ("L", 1, 0)}.get(f.family, ("C", 254, 0))
                campos.append(shpio.DbfField(f.name, t, s, dec, 0))
            v = fila.values.get(f.name) if fila is not None else None
            valores[f.name] = "" if v is None else shpio.display_value(v)
        return campos, valores
    return None


# -- los dos destinos -------------------------------------------------------------------
def comando_original(objetos, islas):
    """ReplaceEntitiesCommand que deja el resultado en la capa original
    (un solo U). Devuelve (comando, cambiados, nuevos, borrados)."""
    cambiar, crear, borrar = C.plan_original(islas)
    viejas, fabricas = [], []
    for oid, isla in cambiar + crear:
        modelo = objetos[oid][1][0]
        fabricas.append(fabrica(modelo, isla["anillos"][0], parte=0))
        for k, h in enumerate(isla["anillos"][1:], start=1):
            fabricas.append(fabrica(modelo, h, parte=k))
    for oid in [o for o, _i in cambiar] + list(borrar):
        viejas += objetos[oid][1]
    cmd = actions.ReplaceEntitiesCommand("JOIN", viejas, fabricas)
    return cmd, len(cambiar), len(crear), len(borrar)


def comando_capa_nueva(document, objetos, islas, capa_origen: str):
    """Un objeto por isla en la capa «combinados de <capa>», sin tocar la
    original. 3.96.1 (Fernando): si la capa ya existe (de una UNIR anterior
    sobre la misma capa), se agregan ahí, y los datos a la misma tabla.
    Devuelve (comando, nombre de la capa, creada)."""
    doc = document.doc
    nombre = C.nombre_combinados(capa_origen)
    creada = nombre not in doc.layers
    cmds = []
    if creada:                     # sólo si falta: el U de NewLayerCommand borra la capa
        try:
            tipo = doc.layers.get(capa_origen).dxf.linetype
        except Exception:  # noqa: BLE001
            tipo = "Continuous"
        # 3.96.1 (Fernando): en rojo, para diferenciarla de la original
        cmds.append(NewLayerCommand(nombre, color=ROJO, linetype=tipo))
    tabla, siguiente = None, 0
    for isla in islas:
        clave, ents = objetos[isla["jefe"]]
        modelo = ents[0]
        cv = _campos_y_valores(document, clave, modelo)
        datos = None
        if cv is not None:
            if tabla is None:
                from . import importados
                tabla = C.nombre_combinados(clave[1])
                usados = [fid for _o, fid, _e in importados.objetos(doc, tabla)]
                siguiente = max(usados) + 1 if usados else 0
            datos = (tabla, cv[0], cv[1], siguiente)
            siguiente += 1
        for h in isla["anillos"]:
            cmds.append(AddToModelCommand("JOIN", fabrica(modelo, h, capa=nombre, datos=datos),
                                          layer=nombre))
    return CompositeCommand("JOIN", cmds), nombre, creada


# -- la herramienta ---------------------------------------------------------------------
class UnirTool(JoinTool):
    """JOIN de IngeCAD; con dos o más polígonos, el de GeoCAD."""

    def start(self) -> None:
        super().start()
        self._islas = None

    def on_selection(self, entities: list) -> None:
        polis = [e for e in entities if es_poligono(e)]
        if len(polis) < 2:
            super().on_selection(entities)
            return
        document = self._documento(polis[0])
        self._document = document
        objetos = objetos_de(document, polis)
        if len(objetos) < 2:
            self.ctx.echo("UNIR: hacen falta al menos dos polígonos distintos.")
            self.ctx.finish()
            return
        ids = {i: [anillo(e) for e in ents] for i, (_k, ents) in enumerate(objetos)}
        islas = C.combinar(ids)
        otros = len(entities) - len(polis)
        if otros:
            self.ctx.echo(f"{otros} objeto(s) que no son polígonos: quedan como estaban.")
        if all(i["sin_cambio"] for i in islas):
            self.ctx.echo("UNIR: los polígonos designados no se tocan; no se unió nada.")
            self.ctx.finish()
            return
        self._objetos, self._islas = objetos, islas
        self._capa = polis[0].dxf.get("layer", "0")
        rellenos = sum(i["rellenos"] for i in islas)
        unidas = sum(1 for i in islas if len(i["miembros"]) > 1)
        self.ctx.echo(f"{len(objetos)} polígono(s) en {len(islas)} isla(s)"
                      + (f", {rellenos} hueco(s) encerrado(s) relleno(s)" if rellenos else "")
                      + "; datos del polígono de mayor superficie de cada una.")
        if len(islas) > unidas:
            self.ctx.echo(f"{len(islas) - unidas} isla(s) no tocan a las demás: quedan aparte.")
        self._preguntar()

    def _documento(self, entidad):
        """El documento de la ventana; en las pruebas, el del dibujo de la entidad."""
        doc = getattr(getattr(self.ctx.services, "window", None), "document", None)
        if doc is not None:
            return doc
        import types
        return types.SimpleNamespace(doc=entidad.doc)

    def _preguntar(self) -> None:
        # 3.97.2 (Fernando): «¿Quiere crear una capa nueva con el resultado?», No de fábrica
        self.prompt(f"{C.PREGUNTA} [Sí/No] <No>:")

    def on_option(self, text: str) -> bool:
        if self._islas is None:
            return False
        destino = C.respuesta(text)
        if destino is None:
            nombre = C.nombre_combinados(self._capa)
            self.ctx.echo(f"Sí: capa nueva «{nombre}». No (o Intro): en la misma capa.")
            self._preguntar()
        else:
            self._terminar(destino)
        return True

    def on_enter(self) -> None:
        if self._islas is None:
            super().on_enter()
            return
        self._terminar("original")

    def on_cancel(self) -> None:
        self._islas = None
        self.ctx.finish()

    def _terminar(self, destino: str) -> None:
        objetos, islas, self._islas = self._objetos, self._islas, None
        if destino == "original":
            cmd, cambiados, nuevos, borrados = comando_original(objetos, islas)
            self.ctx.execute(cmd)
            self.ctx.echo(f"Capa modificada: {cambiados} polígono(s) cambiado(s), "
                          f"{nuevos} nuevo(s), {borrados} borrado(s). (U para deshacer)")
            if any(k[0] == "sig" for k, _e in objetos):
                self.ctx.echo("Capa de QGIS: al devolverla, los registros de los polígonos "
                              "unidos se borran y queda el del mayor.")
        else:
            cmd, nombre, creada = comando_capa_nueva(self._document, objetos, islas, self._capa)
            self.ctx.execute(cmd)
            self.ctx.echo(f"{'Capa nueva' if creada else 'Agregado a la capa'} «{nombre}»: "
                          f"{len(islas)} polígono(s). La capa original no se tocó.")
        self.ctx.finish()
