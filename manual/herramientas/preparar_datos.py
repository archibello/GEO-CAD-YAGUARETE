"""Arma manual/datos_ejemplo/parcelas desde una capa catastral (sólo lectura):
geometría real, POSGAR 2007 faja 6, números de manzana, lote y partida inventados.
Uso: python preparar_datos.py <capa de origen .shp> <destino sin extensión>
Necesita pyshp y pyproj."""
import sys, random, math, shapefile
from pyproj import CRS, Transformer
ORIG, DEST = sys.argv[1], sys.argv[2]
r=shapefile.Reader(ORIG)
srs=CRS.from_wkt(open(ORIG[:-4]+'.prj').read())
dst=CRS.from_epsg(5348)          # POSGAR 2007 / Argentina 6
print('origen:',srs.name,'-> destino:',dst.name)
tr=Transformer.from_crs(srs,dst,always_xy=True)
sr=r.shapeRecords()
c=[s for s in sr if s.record['MZ']=='074']
x0=min(p[0] for s in c for p in s.shape.points)-160; x1=max(p[0] for s in c for p in s.shape.points)+160
y0=min(p[1] for s in c for p in s.shape.points)-160; y1=max(p[1] for s in c for p in s.shape.points)+160
def dentro(s):
    b=s.shape.bbox; return b[0]>=x0 and b[2]<=x1 and b[1]>=y0 and b[3]<=y1
elegidas=[s for s in sr if dentro(s) and s.record['MZ']!='000']
random.seed(2026)
mzs=sorted({s.record['MZ'] for s in elegidas}, key=lambda m:(m!='074',m))
nuevo_mz={m:str(12+i) for i,m in enumerate(mzs)}   # la 074 pasa a ser la 12
usos=['Residencial']*6+['Comercial','Baldío','Mixto']
def area(pts):
    return abs(sum(pts[i][0]*pts[i+1][1]-pts[i+1][0]*pts[i][1] for i in range(len(pts)-1)))/2
w=shapefile.Writer(DEST, shapeType=shapefile.POLYGON)
for f,t,s,d in (('MANZANA','C',4,0),('LOTE','C',4,0),('PARTIDA','C',10,0),('USO','C',12,0),('SUP_M2','N',10,1)):
    w.field(f,t,s,d)
porm={}
for s in sorted(elegidas,key=lambda s:(nuevo_mz[s.record['MZ']],s.record['PARC'])):
    m=s.record['MZ']; porm[m]=porm.get(m,0)+1
    pts=[tr.transform(*p) for p in s.shape.points]
    partes=list(s.shape.parts)+[len(pts)]
    anillos=[pts[partes[i]:partes[i+1]] for i in range(len(partes)-1)]
    w.poly(anillos)
    sup=area(anillos[0])
    uso='Baldío' if sup<250 and random.random()<.3 else random.choice(usos)
    w.record(nuevo_mz[m], f'{porm[m]:03d}', f'45-{random.randint(10000,99999)}', uso, round(sup,1))
w.close()
open(DEST+'.prj','w').write(dst.to_wkt(version='WKT1_ESRI'))
open(DEST+'.cpg','w').write('UTF-8')
print(len(elegidas),'parcelas en',len(mzs),'manzanas; la 074 es la',nuevo_mz['074'])
