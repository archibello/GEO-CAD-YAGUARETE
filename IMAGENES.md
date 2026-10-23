# Imágenes en el dibujo: tomarlas del marco — guía de uso

Con **GeoCAD Yaguareté** el **marco de una imagen** se engancha con las
referencias a objetos de IngeCAD, como en AutoCAD. Una vez insertada, la
imagen se puede **tomar de una esquina** para ubicarla y **escalar desde sus
extremos**, también si está girada o recortada.

IngeCAD solo no le da referencias a las imágenes: sin GeoCAD, una imagen
insertada no ofrece ningún punto donde engancharse (desde la versión
**3.33.7** de GeoCAD).

![Referencia «Punto medio» sobre el marco de un plano escaneado y girado](imagenes/imagen_marco_referencias.webp)

*Un plano de mensura escaneado, girado con GEORREF para que coincida con las
parcelas. El marco de la imagen es el rectángulo gris. El triángulo amarillo
es la referencia **Punto medio** en su lado izquierdo.*

## Qué se engancha

| Referencia (REFENT) | Dónde, en la imagen |
|---|---|
| **Punto final** | Las cuatro esquinas del marco |
| **Punto medio** | El medio de cada lado |
| **Inserción** | El punto de inserción (la esquina inferior izquierda de la imagen) |
| **Intersección** | Donde el marco cruza una línea, una polilínea u otra imagen |
| **Cercano** | Cualquier punto del borde |
| **Perpendicular** | El pie de la perpendicular al borde |

Una imagen **recortada** se engancha por su recorte, que es el mismo borde
con que IngeCAD la elige.

## Antes de empezar (una sola vez)

1. Tener activo el módulo **GeoCAD Yaguareté > Módulos… > Imágenes
   georreferenciadas**. Apagado, IngeCAD queda como venía y el marco deja de
   engancharse.
2. Tener encendidas las referencias a objetos (**REFENT**) que se van a usar:
   por lo menos *Punto final*, *Punto medio* e *Inserción*.

Sirve para cualquier imagen del dibujo, entre por donde entre: **INSERTARGEO**
(con archivo de mundo o GeoTIFF), **Ctrl+V** o **PEGARIMAGEN** (una captura de
pantalla), **IMAGEATTACH**, la captura de Google Earth
([guía](GOOGLE_EARTH.md)), o una imagen rehecha por **GEORREF** o
**ASPECTOIMAGEN**.

## Cómo se usa

### Ubicar una imagen tomándola de una esquina

1. **DESPLAZA** (M), elegir la imagen y Enter.
2. Punto base: acercar el cursor a una esquina del marco hasta ver
   *Punto final* y hacer clic.
3. Segundo punto: el lugar del dibujo donde va esa esquina (el final de una
   línea, un vértice de parcela, una intersección...).

La esquina queda **exactamente** en ese punto.

### Escalar desde los extremos

Cuando un plano escaneado entra con cualquier tamaño y se conoce cuánto mide
algo en el dibujo:

1. **ESCALA** (SC), elegir la imagen y Enter.
2. Punto base: una esquina del marco (*Punto final*), o un punto del plano que
   ya está en su lugar.
3. Opción **Referencia (R)**: longitud de referencia de esquina a esquina del
   marco (*Punto final* en las dos), y como nueva longitud la medida real o
   dos puntos del dibujo.

### Girarla o alinearla

- **GIRA** (RO) con el punto base en una esquina del marco.
- **ALIGN** (AL): dos pares de puntos, de las esquinas del marco a los puntos
  del dibujo. La mueve, la gira y, si se contesta que sí, la escala en un
  solo paso.

Para ajustar un plano escaneado **con varios puntos de control** (como el
Georreferenciador de QGIS) está **GEORREF** ([guía](GEORREF.md)): el marco
sirve para llevarlo cerca primero, y sus esquinas, como puntos de la imagen.

## Imagen girada o rehecha

Una imagen girada con **GIRA** o **ALIGN** tiene el marco girado con ella, y
las esquinas siguen enganchando.

Cuando **GEORREF** rehace la imagen (Thin Plate Spline, Proyectiva,
Polinómica 2 o 3), el resultado es una imagen nueva sin girar, con el
contenido torcido adentro y el fondo transparente. Su marco es el **rectángulo
que la contiene**, no el borde del dibujo escaneado (es el caso de la
captura de arriba).

## Si algo no anda

- **El marco no se engancha**: revisar que esté activo el módulo **Imágenes
  georreferenciadas** y que esa referencia esté encendida en **REFENT**.
  GeoCAD tiene que ser la 3.33.7 o posterior (**Acerca de
  GEO-CAD-YAGUARETÉ...**).
- **Engancha en otro lugar del borde que el que se ve**: la imagen está
  recortada, o fue rehecha por GEORREF (ver arriba).
- Los problemas se reportan en
  [Issues](https://github.com/archibello/GEO-CAD-YAGUARETE/issues).
