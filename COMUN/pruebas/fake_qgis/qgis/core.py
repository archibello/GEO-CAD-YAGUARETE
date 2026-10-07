"""Imitación mínima de qgis.core para probar el complemento sin QGIS."""
import enum
class Qgis:
    class MessageLevel(enum.Enum):
        Info = 0; Warning = 1; Critical = 2; Success = 3
class _Rect:
    def __init__(self, a, b, c, d): self.v = (a, b, c, d)
    def xMinimum(self): return self.v[0]
    def yMinimum(self): return self.v[1]
    def xMaximum(self): return self.v[2]
    def yMaximum(self): return self.v[3]
class _Crs:
    def __init__(self, a="EPSG:5347"): self.a = a
    def authid(self): return self.a
class QgsCoordinateTransform:
    def __init__(self, *a): pass
    def transformBoundingBox(self, e): return e
class _Provider:
    def __init__(self, layer): self.layer = layer
    def reloadData(self): self.layer.reloads += 1
class QgsVectorLayer:
    def __init__(self, source, name):
        self._source, self._name = source, name
        self._ro = False; self.editable = False; self.modified = False; self.reloads = 0
        self._id = name + "_id"; self.commit_ok = True; self.selected = []
    def id(self): return self._id
    def name(self): return self._name
    def source(self): return self._source
    def providerType(self): return "ogr"
    def isSpatial(self): return True
    def readOnly(self): return self._ro
    def setReadOnly(self, f): self._ro = f; return True
    def isEditable(self): return self.editable
    def isModified(self): return self.modified
    def commitChanges(self):
        if self.commit_ok: self.editable = False; self.modified = False
        return self.commit_ok
    def dataProvider(self): return _Provider(self)
    def reload(self): pass
    def triggerRepaint(self): pass
    def crs(self): return _Crs()
    def selectedFeatureIds(self): return list(self.selected)
    def selectedFeatureCount(self): return len(self.selected)
    def selectByIds(self, ids): self.selected = list(ids)
class _Root:
    def __init__(self, p): self.p = p
    def checkedLayers(self): return [l for l in self.p.layers.values() if getattr(l, "visible", True)]
class QgsProject:
    _inst = None
    def __init__(self): self.layers = {}
    @classmethod
    def instance(cls):
        if cls._inst is None: cls._inst = QgsProject()
        return cls._inst
    def mapLayers(self): return dict(self.layers)
    def mapLayer(self, i): return self.layers.get(i)
    def layerTreeRoot(self): return _Root(self)
    def crs(self): return _Crs()
class QgsProviderRegistry:
    @classmethod
    def instance(cls): return cls()
    def decodeUri(self, prov, src):
        path, _, rest = src.partition("|")
        out = {"path": path}
        if rest.startswith("layername="): out["layerName"] = rest.split("=", 1)[1]
        return out
class QgsApplication:
    @staticmethod
    def appIconPath(): return ""
