class QColor:
    def __init__(self, *a): pass
class QFont:
    def setBold(self, b): pass
    def setPixelSize(self, n): pass
class _Pix:
    def save(self, *a): return True
class QIcon:
    def __init__(self, *a): self.a = a
    def isNull(self): return not self.a or self.a == ("",)
    def pixmap(self, *a): return _Pix()
class QPixmap:
    def __init__(self, *a): pass
    def fill(self, c): pass
    def rect(self): return None
class QPainter:
    class RenderHint: Antialiasing = 1
    def __init__(self, *a): pass
    def __getattr__(self, n): return lambda *a, **k: None
class _Sig:
    def __init__(self): self.f = []
    def connect(self, f): self.f.append(f)
class QAction:
    def __init__(self, *a): self.text = a[-2] if len(a) > 2 else a[0]; self.triggered = _Sig()
    def setIcon(self, i): pass
