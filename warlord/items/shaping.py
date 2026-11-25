"""Procedural shaping: you don't pick "door" from a menu, you cut one out of a piece of wood.

A Werkstück (workpiece) is a polygon. Tools change it:
  * Säge / Axt  — a straight cut: the polygon is split along a line, the larger part stays on the bench
  * Beitel      — a chisel stroke: a groove is carved away (notches, the rungs of a ladder, a hollow)
  * Bohrer      — a round hole
  * Raspel      — rounds off sharp corners
After every change the shape is compared with a library of known forms (Tür, Brett, Pfahl, Spitzpfahl,
Keil, Rad, Leiter, Schemel, Schale, Schild…). The best fit, its accuracy and the size decide what you made
and how good it is. Anything that matches nothing is still a real object you can place: a Rohling.

In the field you make a few rough axe cuts along guide lines (your stroke wobbles with speed); at a
Werkbank you work with the mouse, slowly and exactly.
"""
import math
import random

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import split, unary_union


def _rect(w, h):
    return [(0, 0), (w, 0), (w, h), (0, h)]


def _ladder():
    outer = box(0, 0, 1.0, 0.28)
    holes = [box(0.06 + i * 0.125, 0.06, 0.06 + i * 0.125 + 0.085, 0.22) for i in range(7)]
    return outer.difference(unary_union(holes))


def _stool():
    return Polygon([(0, 0), (1, 0), (1, 0.2), (0.85, 0.2), (0.85, 0.7), (0.7, 0.7), (0.7, 0.2), (0.3, 0.2),
                    (0.3, 0.7), (0.15, 0.7), (0.15, 0.2), (0, 0.2)])


def _bowl():
    outer = Point(0.5, 0).buffer(0.5, quad_segs=8).intersection(box(0, 0, 1, 0.5))
    inner = Point(0.5, 0).buffer(0.36, quad_segs=8)
    return outer.difference(inner)


def _trough():
    return box(0, 0, 1, 0.3).difference(box(0.08, 0, 0.92, 0.2))


# key: (item, de, en, shape (normalised, long axis = x, length 1), size range of the long side in px, needs_lab)
TEMPLATES = {
    "planks": ("planks", "Brett", "plank", Polygon(_rect(1, 0.11)), (50, 220), False),
    "beam": ("beam", "Balken", "beam", Polygon(_rect(1, 0.25)), (60, 240), False),
    "stake": ("stake", "Pfahl", "stake", Polygon([(0, 0), (0.86, 0), (1, 0.08), (0.86, 0.16), (0, 0.16)]), (40, 140),
              False),
    "spike": ("spike", "Spitzpfahl", "sharpened stake", Polygon([(0, 0), (0.62, 0), (1, 0.08), (0.62, 0.16),
                                                                (0, 0.16)]), (40, 160), False),
    "door": ("door", "Tür", "door", Polygon(_rect(1, 0.48)), (60, 110), False),
    "wedge": ("wedge", "Keil", "wedge", Polygon([(0, 0), (1, 0.18), (0, 0.36)]), (10, 40), False),
    "handle": ("handle", "Stiel", "tool handle", Polygon(_rect(1, 0.12)), (24, 50), False),
    "shaft": ("shaft", "Schaft", "spear shaft", Polygon(_rect(1, 0.05)), (70, 200), False),
    "sign_board": ("sign_board", "Schild", "sign board", Polygon(_rect(1, 0.5)), (20, 50), False),
    "club": ("knueppel", "Knüppel", "club", Polygon([(0, 0.04), (0.6, 0.02), (1, 0), (1, 0.2), (0.6, 0.16),
                                                     (0, 0.12)]), (30, 70), False),
    "wheel": ("wheel", "Rad", "wheel", Point(0.5, 0.5).buffer(0.5, quad_segs=10), (24, 70), True),
    "shield": ("holzschild", "Rundschild", "round shield", Point(0.5, 0.5).buffer(0.5, quad_segs=10), (28, 60), True),
    "ladder": ("ladder", "Leiter", "ladder", _ladder(), (90, 220), True),
    "stool": ("stool", "Schemel", "stool", _stool(), (20, 50), True),
    "bowl": ("bowl", "Schale", "bowl", _bowl(), (12, 40), True),
    "trough": ("trough", "Trog", "trough", _trough(), (50, 120), True),
}
FIELD_TARGETS = [k for k, t in TEMPLATES.items() if not t[5]]


def normalise(poly):
    """Rotate so the long side lies along x, move to the origin. Returns (poly, length, angle)."""
    mrr = poly.minimum_rotated_rectangle
    c = list(mrr.exterior.coords)
    best = None
    for a, b in zip(c, c[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if best is None or L > best[0]:
            best = (L, math.atan2(b[1] - a[1], b[0] - a[0]))
    L, ang = best
    p = affinity.rotate(poly, -ang, origin=(0, 0), use_radians=True)
    x0, y0, x1, y1 = p.bounds
    p = affinity.translate(p, -x0, -y0)
    return p, max(1e-6, x1 - x0), ang


def score(poly, key):
    """How well a polygon matches one template: (score 0..1, iou, size_ok)."""
    tmpl = TEMPLATES[key][3]
    lo, hi = TEMPLATES[key][4]
    p, L, _ = normalise(poly)
    x0, y0, x1, y1 = p.bounds
    w, h = x1 - x0, y1 - y0
    tx0, ty0, tx1, ty1 = tmpl.bounds
    tw, th = tx1 - tx0, ty1 - ty0
    a_c = h / max(1e-6, w)
    a_t = th / max(1e-6, tw)
    a_fac = math.exp(-((math.log(max(1e-3, a_c) / max(1e-3, a_t))) / 0.28) ** 2)
    best = 0.0
    for fx, fy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        t = affinity.scale(tmpl, fx * w / tw, fy * h / th, origin=(0, 0))
        tb = t.bounds
        t = affinity.translate(t, -tb[0], -tb[1])
        inter = p.intersection(t).area
        uni = p.union(t).area
        if uni > 0:
            best = max(best, inter / uni)
    size_ok = lo <= L <= hi
    s_fac = 1.0 if size_ok else max(0.0, 1.0 - min(abs(L - lo), abs(L - hi)) / max(lo, 1) * 1.5)
    return best * a_fac * (0.35 + 0.65 * s_fac), best, size_ok


def identify(poly, lab=True):
    """The best matching template: (key or None, quality 0..1, ranking list)."""
    ranking = []
    for k, t in TEMPLATES.items():
        if t[5] and not lab:
            continue
        s, iou, ok = score(poly, k)
        ranking.append((s, k, iou, ok))
    ranking.sort(reverse=True)
    s, k, iou, ok = ranking[0]
    if s < 0.6:
        return None, s, ranking
    q = max(0.0, min(1.0, (s - 0.6) / 0.35))
    return k, q, ranking


class Workpiece:
    """A piece of wood (or stone) on the bench, in local pixel coordinates."""

    def __init__(self, poly, mat="log", source="log"):
        self.poly = poly
        self.mat = mat
        self.source = source
        self.history = []
        self.offcuts = []
        self.cuts = 0

    @classmethod
    def from_points(cls, pts, mat="log"):
        return cls(Polygon(pts).buffer(0), mat)

    @classmethod
    def log(cls, length=120, thick=30, mat="log"):
        return cls(Polygon(_rect(length, thick)), mat)

    def points(self):
        p = self.poly
        if p.geom_type == "MultiPolygon":
            p = max(p.geoms, key=lambda g: g.area)
        return list(p.exterior.coords)[:-1]

    def holes(self):
        p = self.poly
        if p.geom_type == "MultiPolygon":
            p = max(p.geoms, key=lambda g: g.area)
        return [list(h.coords)[:-1] for h in p.interiors]

    def _keep_largest(self, geom):
        parts = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and g.area > 1]
        if not parts:
            return False
        parts.sort(key=lambda g: g.area, reverse=True)
        self.history.append(self.poly)
        self.poly = parts[0]
        for g in parts[1:]:
            self.offcuts.append(g)
        return True

    # ------------------------------------------------------------------ tools
    def saw(self, a, b):
        """A straight cut along the infinite line through a and b."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 2:
            return False
        ux, uy = dx / L, dy / L
        big = 10000
        line = LineString([(a[0] - ux * big, a[1] - uy * big), (a[0] + ux * big, a[1] + uy * big)])
        try:
            parts = split(self.poly, line)
        except Exception:
            return False
        if len(parts.geoms) < 2:
            return False
        self.cuts += 1
        return self._keep_largest(parts)

    def saw_segment(self, a, b):
        """A cut only as long as the stroke: it can notch without severing."""
        groove = LineString([a, b]).buffer(1.2, cap_style=2)
        return self._keep_largest(self.poly.difference(groove))

    def carve(self, pts, width=6):
        if len(pts) < 2:
            pts = [pts[0], (pts[0][0] + 0.5, pts[0][1] + 0.5)]
        groove = LineString(pts).buffer(width / 2, quad_segs=3)
        new = self.poly.difference(groove)
        if new.area >= self.poly.area - 0.5:
            return False
        self.cuts += 1
        return self._keep_largest(new)

    def drill(self, c, r=4):
        new = self.poly.difference(Point(c).buffer(r, quad_segs=6))
        if new.area >= self.poly.area - 0.5:
            return False
        self.cuts += 1
        return self._keep_largest(new)

    def rasp(self):
        p = self.poly.buffer(-1.5, join_style=1).buffer(1.5, join_style=1)
        if p.is_empty:
            return False
        return self._keep_largest(p.simplify(0.6))

    def undo(self):
        if self.history:
            self.poly = self.history.pop()
            if self.offcuts:
                self.offcuts.pop()
            return True
        return False

    # ------------------------------------------------------------------ guidance
    def identify(self, lab=True):
        return identify(self.poly, lab)

    def guide(self, key):
        """The target outline placed inside the workpiece (local coords), for the dashed guide lines."""
        tmpl = TEMPLATES[key][3]
        lo, hi = TEMPLATES[key][4]
        p, L, ang = normalise(self.poly)
        x0, y0, x1, y1 = self.poly.bounds
        W, H = x1 - x0, y1 - y0
        tx0, ty0, tx1, ty1 = tmpl.bounds
        tw, th = tx1 - tx0, ty1 - ty0
        horizontal = W >= H
        long_side, short_side = (W, H) if horizontal else (H, W)
        target_L = min(long_side * 0.96, hi)
        sc = target_L / tw
        if th * sc > short_side * 0.98:
            sc = short_side * 0.98 / th
        t = affinity.scale(tmpl, sc, sc, origin=(0, 0))
        if not horizontal:
            t = affinity.rotate(t, 90, origin=(0, 0))
        b = t.bounds
        t = affinity.translate(t, x0 - b[0] + (W - (b[2] - b[0])) * 0.03, y0 - b[1] + (H - (b[3] - b[1])) / 2)
        return t

    def guide_cuts(self, key):
        """Straight cut lines that would turn the workpiece into the target (field mode)."""
        g = self.guide(key)
        out = []
        c = list(g.exterior.coords)
        for a, b in zip(c, c[1:]):
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if self.poly.boundary.distance(Point(mid)) > 2.0:
                out.append((a, b))
        return out, g


def wobble(a, b, speed, skill, rng=None):
    """An axe stroke in the field is not a saw cut: it wanders with speed and lack of practice."""
    rng = rng or random
    err = (0.6 + speed / 300.0) * (1.4 - skill)
    ang = rng.gauss(0, 0.035 * err)
    off = rng.gauss(0, 1.6 * err)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    c, s = math.cos(ang), math.sin(ang)
    rdx, rdy = dx * c - dy * s, dx * s + dy * c
    return ((mx - rdx / 2 + nx * off, my - rdy / 2 + ny * off), (mx + rdx / 2 + nx * off, my + rdy / 2 + ny * off))


def describe(key):
    t = TEMPLATES[key]
    return t[1], t[2]
