import enum
class Qt:
    class AlignmentFlag(enum.Enum):
        AlignCenter = 0x84
class _Sig:
    def __init__(self): self.f = []
    def connect(self, f): self.f.append(f)
class QTimer:
    shots = []
    def __init__(self, *a): self.timeout = _Sig()
    def setInterval(self, ms): pass
    def start(self): pass
    def stop(self): pass
    @staticmethod
    def singleShot(ms, f): QTimer.shots.append(f)
