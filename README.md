# GEO-CAD-YAGUARETÉ

**GIS to CAD y CAD to GIS: QGIS e IngeCAD trabajando como un mismo sistema.**

Ida y vuelta sobre GeoPackage (.gpkg) y shapefile (.shp) conservando
atributos, con respaldo .zip, control de conflictos y validación antes de
escribir; y herramientas de dibujo, capas, bloques y espacio papel al estilo
AutoCAD, en los dos programas.

> Antes se llamaba **GeoCAD**. Desde la 3.8.0, en el programa: menú y
> barra «GeoCAD Yaguareté» y **Acerca de GEO-CAD-YAGUARETÉ...**

## Módulos (nada invasivo)

Cada parte es un módulo que se elige al instalar y se cambia cuando se quiera
en **GeoCAD Yaguareté > Módulos...** Lo que no se elige no aparece en ningún menú ni
cambia nada del programa.

- **IngeCAD:** Puente con QGIS · Datos · Botón derecho = Enter · Empalme y
  Chaflán estilo AutoCAD · Bloques · Partir en punto · Selección estilo
  AutoCAD · Ángulos relativos al tramo anterior
- **QGIS:** Puente con IngeCAD · Dibujo CAD · Bloques CAD · Espacio papel ·
  Capas CAD (Layer Properties)

## Antes de instalar

GEO-CAD-YAGUARETÉ se instala **dentro** de IngeCAD y de QGIS: primero tienen
que estar los dos programas.

1. **Linux.** Por ahora funciona sólo en Linux.
2. **Instalar IngeCAD y QGIS.** Versiones probadas:
   - IngeCAD 0.6.5 (Flatpak, desde [ingecad.org](https://ingecad.org)).
   - QGIS 4.2.2 (Flatpak de [Flathub](https://flathub.org/apps/org.qgis.qgis)),
     3.40.5 (Debian) o 3.28.9 LTS.
3. **Abrir cada programa una vez y cerrarlo.** Al abrirse por primera vez
   crean su carpeta de configuración, y el instalador sólo instala donde
   la encuentra: si un programa nunca se abrió, queda sin GEO-CAD-YAGUARETÉ.
4. **Python 3** (viene con casi todas las distribuciones de Linux).
5. **Capas en un disco externo** (con IngeCAD en Flatpak): darle permiso una
   vez, en una terminal:

   ```bash
   flatpak override --user --filesystem=/media org.ingecad.IngeCAD
   ```

## Instalación

1. Descargar la última versión desde
   [Releases](../../releases/latest).
2. Con IngeCAD y QGIS cerrados, en una terminal:

   ```bash
   python3 instalar_geocad_<versión>.py
   ```

   (o doble clic en `INSTALAR_GeoCAD.sh`, que hace lo mismo).

Para QGIS solo: *Complementos > Instalar a partir de ZIP* con
`geocad_qgis_<versión>.zip`.

Después, para actualizar: **GeoCAD Yaguareté > Actualizar GeoCAD Yaguareté...** en cualquiera de
los dos programas.

## Estructura del código

```
COMUN/      núcleo compartido, pruebas automáticas, build.py y CAMBIOS_<versión>.txt
QGIS/       el complemento de QGIS (codigo/geocad)
INGECAD/    el plugin de IngeCAD (codigo/geocad)
```

Cada versión se arma con `python3 COMUN/build.py` y trae su
`COMUN/CAMBIOS_<versión>.txt`.

## Autor

**Arq. Fernando Pablo Bellocchio** · Posadas, Misiones, Argentina.

Desarrollado con la ayuda de [Claude](https://claude.com/claude-code) (Anthropic).

## Contacto

Ideas, problemas y propuestas: en [Issues](../../issues).
¿Trabajás en algo parecido o afín (QGIS, CAD, catastro, agrimensura,
urbanismo)? Escribí: la idea es conectar con otros usuarios y proyectos.

## Licencia

© 2026 Fernando Pablo Bellocchio.
[GPL-3.0-or-later](LICENSE): libre para usar, estudiar, modificar y compartir.
