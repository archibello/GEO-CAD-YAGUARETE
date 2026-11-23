# -*- coding: utf-8 -*-
"""UNIR (JOIN, J): las cuentas, sin QGIS (3.87.0).

Pedido de Fernando (23/11/2026): «agregar a QGIS la herramienta Join (J)
considerando que el polígono mayor en longitud o el polígono con más tramos va
a otorgar la base de datos al más corto o de menos tramos». Decidido: líneas y
polilíneas (como el JOIN de AutoCAD); criterio Longitud de fábrica, con la
opción Tramos.

Las piezas que comparten un extremo se encadenan en una sola polilínea. Cada
cadena arranca en la pieza MAYOR que queda (la del objeto más largo, o con
más tramos) y ese objeto conserva su fila de la tabla: los demás de la cadena
desaparecen. En un cruce de tres o más, la cadena sigue por la mayor de las
que llegan y las otras forman su propia cadena (o quedan como estaban).
"""

import math

LONGITUD, TRAMOS = 'longitud', 'tramos'


def largo(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def tramos(pts):
    return max(0, len(pts) - 1)


def medida(partes, criterio):
    """El valor que decide quién manda: (principal, desempate)."""
    lg = sum(largo(p) for p in partes)
    tr = sum(tramos(p) for p in partes)
    return (tr, lg) if criterio == TRAMOS else (lg, tr)


def tolerancia(piezas):
    """Extremos «iguales»: 1e-10 de la coordenada más grande (UTM: ~0,6 mm;
    grados: ~2 mm), nunca menos de 1e-12."""
    m = max((abs(c) for _f, _k, pts in piezas for p in pts for c in p), default=0.0)
    return max(1e-12, 1e-10 * m)


def _igual(a, b, tol):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _cerrada(pts, tol):
    return len(pts) > 2 and _igual(pts[0], pts[-1], tol)


def unir(objetos, criterio=LONGITUD, tol=None):
    """``objetos``: {fid: [partes]} (cada parte, lista de (x, y)).

    Devuelve (resultado, cadenas):
      resultado: {fid: [partes]} — lo que queda de cada objeto (lista vacía =
                 el objeto se borra); sólo figuran los que cambian.
      cadenas:   [(fid que manda, [fids unidos])] — una por unión hecha.
    """
    clave = {fid: medida(ps, criterio) for fid, ps in objetos.items()}
    piezas = [(fid, k, list(p)) for fid, ps in objetos.items() for k, p in enumerate(ps) if len(p) >= 2]
    if tol is None:
        tol = tolerancia(piezas)
    # orden: el objeto mayor primero; dentro de él, su parte mayor
    orden = sorted(range(len(piezas)),
                   key=lambda i: (clave[piezas[i][0]], medida([piezas[i][2]], criterio), -i),
                   reverse=True)
    quedan = [i for i in orden if not _cerrada(piezas[i][2], tol)]
    usadas = set()
    unidas = set()                 # las piezas que entraron en una unión
    salida = {}                    # fid -> partes nuevas
    cadenas = []
    for semilla in quedan:
        if semilla in usadas:
            continue
        usadas.add(semilla)
        cadena = list(piezas[semilla][2])
        miembros = [semilla]
        while not _cerrada(cadena, tol):
            pegada = False
            for i in quedan:                     # de mayor a menor: la mayor que toque
                if i in usadas:
                    continue
                p = piezas[i][2]
                if _igual(cadena[-1], p[0], tol):
                    cadena = cadena + p[1:]
                elif _igual(cadena[-1], p[-1], tol):
                    cadena = cadena + p[-2::-1]
                elif _igual(cadena[0], p[-1], tol):
                    cadena = p[:-1] + cadena
                elif _igual(cadena[0], p[0], tol):
                    cadena = p[:0:-1] + cadena
                else:
                    continue
                usadas.add(i)
                miembros.append(i)
                pegada = True
                break
            if not pegada:
                break
        if len(miembros) < 2:
            continue
        if _cerrada(cadena, tol):
            cadena[-1] = cadena[0]             # cierra exacto
        unidas.update(miembros)
        jefe = piezas[semilla][0]
        salida.setdefault(jefe, []).append(cadena)
        fids = []
        for i in miembros:
            if piezas[i][0] not in fids:
                fids.append(piezas[i][0])
        cadenas.append((jefe, fids))
    # cada objeto tocado: sus cadenas nuevas y las partes que no entraron
    tocados = {f for _j, fs in cadenas for f in fs}
    resultado = {}
    for fid in tocados:
        sueltas = [p for i, (f, _k, p) in enumerate(piezas) if f == fid and i not in unidas]
        resultado[fid] = salida.get(fid, []) + sueltas
    return resultado, cadenas
