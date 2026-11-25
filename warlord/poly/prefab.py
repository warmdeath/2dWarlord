"""Architecture made of real pieces.

A building is a set of polygon pieces — posts, wall panels, ashlar blocks, floor boards, roof slabs, doors —
each with a material, hit points and a place in a support graph (what it rests on, what it is bonded to at
the sides). Pieces stand still as static collision shapes until they are disturbed: when one breaks, the
graph is re-checked and every piece that has lost its support becomes a dynamic rigid body, so the physics
engine decides how a wall or a roof comes down.

Builders keep the old signatures (tile columns, ground row `g`) and return the same building records the
society code uses: kind, x0, x1, g, door, beds, work, style, top.
"""
import math
import random

import pymunk

from ..settings import TILE
from .materials import MATS, MASONRY, TIMBER
from .world import F_STRUCT, F_PLATFORM, CT_PLATFORM, CT_BLOCK

DOOR_H = 50


# ====================================================================== the parts
class Piece:
    def __init__(self, pid, pts, mat, role, solid=True, platform=False, layer="mid", bld=None):
        self.id = pid
        self.pts = [(float(x), float(y)) for x, y in pts]
        self.mat = mat
        self.role = role
        self.solid = solid
        self.platform = platform
        self.layer = layer
        self.bld = bld
        self.state = "static"
        self.shape = None
        self.below = []
        self.side = []
        self.anchors = []
        self.grounded = False
        self.burn = 0.0
        self.open = False
        self.locked = False
        self.detail = None
        self.tint = None
        self.crack = 0.0
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        self.bb = (min(xs), min(ys), max(xs), max(ys))
        self.cx = (self.bb[0] + self.bb[2]) / 2
        self.cy = (self.bb[1] + self.bb[3]) / 2
        self.area = max(4.0, _area(self.pts))
        m = MATS[mat]
        self.max_hp = self.hp = max(4.0, m.hp * self.area / 100.0)

    def __getstate__(self):
        d = self.__dict__.copy()
        d["shape"] = None
        return d

    @property
    def w(self):
        return self.bb[2] - self.bb[0]

    @property
    def h(self):
        return self.bb[3] - self.bb[1]

    def make_shape(self, sb):
        sh = pymunk.Poly(sb, self.pts)
        m = MATS[self.mat]
        sh.friction = 0.9 if self.mat not in ("slate", "rooftile", "ice") else 0.5
        sh.elasticity = 0.02
        if self.platform:
            sh.filter = F_PLATFORM
            sh.collision_type = CT_PLATFORM
        else:
            sh.filter = F_STRUCT
            sh.collision_type = CT_BLOCK
        sh.sensor = self.role == "door" and self.open
        sh.owner = self
        sh.mat = m.key
        self.shape = sh
        return sh

    def contains(self, x, y, pad=0.0):
        x0, y0, x1, y1 = self.bb
        if not (x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad):
            return False
        return _point_in(self.pts, x, y) or pad > 0


class Decor:
    """Furniture and fittings: beds, chests, hearths, anvils, workbenches, signs, torches, windows…"""

    def __init__(self, kind, x, y, w=16, h=16, bld=None, **data):
        self.kind = kind
        self.x, self.y = float(x), float(y)       # x centre, y = the floor it stands on
        self.w, self.h = w, h
        self.bld = bld
        self.data = data
        self.gone = False

    def rect(self):
        return (self.x - self.w / 2, self.y - self.h, self.w, self.h)


class Plot:
    """An Acker: a strip of furrows, one entry per 16 px: [crop, growth 0..1, tilled, fertility, trampled]."""

    def __init__(self, x0, x1, y, crop):
        self.x0, self.x1, self.y = x0, x1, y
        n = max(1, int((x1 - x0) // TILE))
        self.strips = [[crop, random.uniform(0.2, 1.0), True, 1.0, 0.0] for _ in range(n)]
        self.crop = crop

    def strip_at(self, px):
        i = int((px - self.x0) // TILE)
        if 0 <= i < len(self.strips):
            return self.strips[i]
        return None


class Building:
    def __init__(self, bid, kind, style):
        self.id = bid
        self.kind = kind
        self.style = style
        self.pieces = []
        self.decor = []
        self.ladders = []
        self.rec = None
        self.x0 = self.x1 = self.top = 0.0
        self.version = 0          # bumps when a piece changes; the renderer re-caches
        self.owner = None
        self.lights = []          # (x, y, strength)
        self.smoke = []

    def alive_pieces(self, world):
        return [world.pieces[i] for i in self.pieces if i in world.pieces]


# ====================================================================== the builder
class Builder:
    def __init__(self, world, kind, style, rng=None):
        self.w = world
        self.rng = rng or random.Random(1)
        world.next_bid = getattr(world, "next_bid", 1)
        self.b = Building(world.next_bid, kind, style)
        world.next_bid += 1
        self.list = []

    def poly(self, pts, mat, role="wall", solid=True, platform=False, layer=None, detail=None, tint=None):
        w = self.w
        pc = Piece(w.next_piece, pts, mat, role, solid, platform, layer or ("mid" if solid else "back"), self.b.id)
        pc.detail = detail
        pc.tint = tint
        w.next_piece += 1
        self.list.append(pc)
        return pc

    def rect(self, x0, y0, x1, y1, mat, role="wall", **kw):
        return self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], mat, role, **kw)

    def back(self, x0, y0, x1, y1, mat, role="back", **kw):
        return self.rect(x0, y0, x1, y1, mat, role, solid=False, **kw)

    def slab(self, a, b, thick, mat, role="roof", **kw):
        """A thick band along the line a→b (roof slopes, braces, ramps), offset downward."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1
        nx, ny = -dy / d, dx / d
        if ny < 0:
            nx, ny = -nx, -ny
        return self.poly([a, b, (b[0] + nx * thick, b[1] + ny * thick), (a[0] + nx * thick, a[1] + ny * thick)],
                         mat, role, **kw)

    def door(self, x0, floor_y, width=8, mat="plank", height=DOOR_H):
        pc = self.rect(x0, floor_y - height, x0 + width, floor_y, mat, "door")
        return pc

    def ladder(self, x, y0, y1):
        r = (x - 7, y0 - 4, x + 7, y1)
        self.b.ladders.append(r)
        self.back(x - 6, y0, x + 6, y1, "timber", "ladder")
        return r

    def decor(self, kind, x, y, w=16, h=16, **data):
        d = Decor(kind, x, y, w, h, self.b.id, **data)
        self.b.decor.append(d)
        return d

    def light(self, x, y, s=0.8):
        self.b.lights.append((x, y, s))

    def masonry(self, x0, x1, ybot, ytop, mat, course=14, bw=(16, 28), role="wall", skip=None, jitter=1.0):
        """Coursed masonry in staggered blocks; `skip(x0, y0, x1, y1)` leaves openings."""
        rng = self.rng
        y = ybot
        row = 0
        out = []
        while y > ytop + 0.5:
            ch = min(course, y - ytop)
            if ch < 5:
                ch = y - ytop
            x = x0 - (rng.uniform(0, bw[0]) if row % 2 else 0)
            while x < x1 - 0.5:
                bwid = rng.uniform(*bw)
                a, b = max(x0, x), min(x1, x + bwid)
                if b - a < 5 and b < x1:
                    x += bwid
                    continue
                if x1 - b < 6:
                    b = x1
                if skip is None or not skip(a, y - ch, b, y):
                    j = jitter
                    pts = [(a + rng.uniform(0, j), y - ch + rng.uniform(0, j)),
                           (b - rng.uniform(0, j), y - ch + rng.uniform(0, j)),
                           (b, y), (a, y)]
                    out.append(self.poly(pts, mat, role, detail="block"))
                x = b
            y -= ch
            row += 1
        return out

    def battlements(self, x0, x1, ytop, mat, mw=12, gap=9, mh=12):
        x = x0
        while x < x1 - 2:
            b = min(x1, x + mw)
            self.rect(x, ytop - mh, b, ytop, mat, "merlon", detail="block")
            x = b + gap

    def finish(self, rec=None):
        """Register the pieces, compute the support graph, return the building record."""
        w = self.w
        b = self.b
        for pc in self.list:
            w.pieces[pc.id] = pc
            b.pieces.append(pc.id)
            w.index_add("piece_chunks", pc.cx, pc.id)
        for d in b.decor:
            w.index_add("decor_chunks", d.x, d)
        for r in b.ladders:
            w.add_ladder(r)
        if self.list:
            b.x0 = min(p.bb[0] for p in self.list)
            b.x1 = max(p.bb[2] for p in self.list)
            b.top = min(p.bb[1] for p in self.list)
        link(w, [p for p in self.list])
        w.buildings.append(b)
        if rec is not None:
            rec["bid"] = b.id
            b.rec = rec
        return rec


def link(w, pieces):
    solid = [p for p in pieces if p.solid]
    for p in solid:
        p.below, p.side = [], []
        x0, y0, x1, y1 = p.bb
        gy = min(w.surface_y(x) for x in (x0 + 1, (x0 + x1) / 2, x1 - 1))
        p.grounded = y1 >= gy - 3 or p.role in ("pier", "found")
    for p in solid:
        x0, y0, x1, y1 = p.bb
        for q in solid:
            if q is p:
                continue
            qx0, qy0, qx1, qy1 = q.bb
            xo = min(x1, qx1) - max(x0, qx0)
            yo = min(y1, qy1) - max(y0, qy0)
            if xo > 1.5 and abs(qy0 - y1) < 3.5:
                p.below.append(q.id)
            elif xo > 1.5 and yo > 1.5 and qy0 > p.cy:     # overlapping, q is lower: also a support
                p.below.append(q.id)
            elif yo > 3 and (abs(qx0 - x1) < 3 or abs(qx1 - x0) < 3):
                p.side.append(q.id)
    for p in pieces:
        if p.solid:
            continue
        x0, y0, x1, y1 = p.bb
        p.anchors = [q.id for q in solid if q.bb[0] <= x1 + 3 and q.bb[2] >= x0 - 3 and q.bb[1] <= y1 + 3
                     and q.bb[3] >= y0 - 3]


# ====================================================================== structural failure
def stable_set(w, b):
    pcs = [w.pieces[i] for i in b.pieces if i in w.pieces and w.pieces[i].state == "static"]
    solid = [p for p in pcs if p.solid]
    alive = {p.id for p in solid}
    stable = {p.id for p in solid if p.grounded}
    changed = True
    while changed:
        changed = False
        for p in solid:
            if p.id in stable:
                continue
            ok = any(q in stable for q in p.below)
            if not ok and p.side:
                sides = [q for q in p.side if q in stable]
                if sides:
                    left = any(w.pieces[q].cx < p.cx for q in sides)
                    right = any(w.pieces[q].cx > p.cx for q in sides)
                    m = p.mat
                    if left and right and (m in MASONRY or m in TIMBER or p.role in ("roof", "floor", "lintel")):
                        ok = True       # an arch, a lintel, a floor between two walls
                    elif p.w <= 26 and (m in TIMBER or m in MASONRY):
                        ok = True       # a short cantilever bonded into a wall
            if ok:
                stable.add(p.id)
                changed = True
    return pcs, alive, stable


def settle(w, b, fx=None):
    """Re-check a building after damage; whatever lost its support falls as rigid bodies."""
    from .objects import PhysObject
    pcs, alive, stable = stable_set(w, b)
    fallen = 0
    for p in pcs:
        if p.solid and p.id not in stable:
            PhysObject.from_piece(w, p)
            fallen += 1
    # back walls, windows and ladders hang on what is left
    for p in pcs:
        if not p.solid and p.anchors and not any(a in w.pieces and w.pieces[a].state == "static" and
                                                 w.pieces[a].id in stable for a in p.anchors):
            PhysObject.from_piece(w, p, debris=True)
            fallen += 1
    if fallen:
        b.version += 1
        # ladders that have lost their walls
        for r in list(b.ladders):
            x0, y0, x1, y1 = r
            if not any(w.pieces[i].bb[0] < x1 + 14 and w.pieces[i].bb[2] > x0 - 14 and w.pieces[i].solid
                       for i in b.pieces if i in w.pieces):
                b.ladders.remove(r)
                w.remove_ladder(r)
    return fallen


def remove_piece(w, pc):
    """Take a piece out of the world (broken, burnt, taken apart)."""
    w.piece_shape_removed(pc)
    pc.state = "gone"
    w.pieces.pop(pc.id, None)
    w.index_remove("piece_chunks", pc.cx, pc.id)
    b = building(w, pc.bld)
    if b is not None:
        b.version += 1
    return b


def building(w, bid):
    idx = getattr(w, "_bindex", None)
    if idx is None or len(idx) != len(w.buildings):
        w._bindex = idx = {b.id: b for b in w.buildings}
    return idx.get(bid)


def piece_at(w, x, y, pad=0.0, solid_only=False):
    best = None
    for pid in w.near("piece_chunks", x - 80, x + 80):
        p = w.pieces.get(pid)
        if p is None or (solid_only and not p.solid):
            continue
        if p.contains(x, y, pad):
            if best is None or (p.solid and not best.solid):
                best = p
    return best


def toggle_door(w, pc, open_=None):
    if pc.role != "door" or pc.locked and open_:
        return False
    pc.open = (not pc.open) if open_ is None else open_
    if pc.shape is not None:
        pc.shape.sensor = pc.open
    b = building(w, pc.bld)
    if b:
        b.version += 1
    return True


# ====================================================================== helpers
def _area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


def _point_in(pts, x, y):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


def gable(B, x0, x1, base, rise, mat, over=10, thick=9, gable_mat="plaster", frame=True, chimney=None):
    """A pitched roof: two slabs on a triangular gable wall. Returns the ridge y."""
    mid = (x0 + x1) / 2
    ridge = base - rise
    a = (x0 - over, base + over * rise / ((x1 - x0) / 2 + 0.01) * 0.0 + 2)
    B.back(x0 + 1, base - 0.5, x1 - 1, base + 0.5, gable_mat)   # anchor line (keeps gable attached)
    # the gable triangle behind the roof slabs
    B.poly([(x0 + 2, base), (mid, ridge + thick * 0.8), (x1 - 2, base)], gable_mat, "gable", solid=False,
           detail="gable_frame" if frame else None)
    left = B.slab((x0 - over, base + 3), (mid + 1, ridge), thick, mat, "roof", detail=MATS[mat].detail)
    right = B.slab((mid - 1, ridge), (x1 + over, base + 3), thick, mat, "roof", detail=MATS[mat].detail)
    if chimney is not None:
        cxp = chimney
        t = abs(cxp - mid) / ((x1 - x0) / 2 + over)
        yb = ridge + (base - ridge) * t
        B.rect(cxp - 5, yb - 18, cxp + 5, yb + 4, "brick", "chimney", detail="bricks")
        B.b.smoke.append((cxp, yb - 20))
    return ridge, left, right


def timber_back(B, x0, x1, ybot, ytop, rng, infill="plaster", window=True):
    """The back wall of a Fachwerk room: plaster panels in a frame of posts, rails and braces."""
    p = B.back(x0, ytop, x1, ybot, infill, "backwall", detail="fachwerk")
    p.detail = ("fachwerk", rng.randint(0, 3))
    if window:
        n = max(1, int((x1 - x0) // 44))
        for i in range(n):
            wx = x0 + (i + 0.5) * (x1 - x0) / n
            wy = ytop + (ybot - ytop) * 0.32
            B.back(wx - 7, wy, wx + 7, wy + 14, "glass", "window", detail="window")
            B.light(wx, wy + 7, 0.35)
    return p


def interior(B, x0, x1, floor_y, rng, kind="house", beds=1, hearth=True):
    out = []
    if hearth and x1 - x0 > 60:
        hx = x0 + (x1 - x0) * 0.5
        B.decor("hearth", hx, floor_y, 20, 14)
        B.light(hx, floor_y - 8, 0.9)
    for i in range(beds):
        bx = x0 + 14 + i * 26
        if bx + 10 < x1:
            B.decor("bed", bx, floor_y, 22, 10)
            out.append(int(bx // TILE))
    if rng.random() < 0.7 and x1 - x0 > 50:
        B.decor("chest", x1 - 14, floor_y, 14, 10, items={})
    if rng.random() < 0.5 and x1 - x0 > 80:
        B.decor("table", x0 + (x1 - x0) * 0.72, floor_y, 22, 12)
    return out


# ====================================================================== buildings
WALLMAT = {"peasant": "plaster", "burgher": "plaster", "stone": "stone", "wood": "plank", "snow": "plank",
           "ash": "stone", "brick": "brick", "tower": "ashlar", "log": "log", "longhouse": "plank",
           "basalt": "basalt", "chained": "plaster"}
ROOFMAT = {"peasant": "thatch", "burgher": "rooftile", "stone": "slate", "wood": "thatch", "snow": "slate",
           "ash": "slate", "brick": "rooftile", "tower": "slate", "log": "shingle", "longhouse": "turf",
           "basalt": "basalt", "chained": "thatch"}
PITCH = {"thatch": 1.05, "rooftile": 0.85, "slate": 0.95, "shingle": 1.0, "turf": 0.45, "basalt": 0.0}


def house(w, x0, g, width=9, height=4, style="peasant", door_side=1, rng=None, kind="house", floors=None):
    rng = rng or random.Random(x0)
    B = Builder(w, kind, style, rng)
    X0, X1, G = x0 * TILE, (x0 + width) * TILE, g * TILE
    if floors is None:
        floors = 2 if style == "burgher" and width >= 9 else 3 if style == "brick" and width >= 8 else 1
    FH = height * TILE
    wm, rm = WALLMAT[style], ROOFMAT[style]
    masonry_walls = wm in MASONRY
    wt = 12 if masonry_walls else 8
    post = "timber" if not masonry_walls else wm
    if style == "log":
        post = "log"
    ladder_x = X0 + wt + 8 if door_side == 1 else X1 - wt - 8
    beds = []
    floor_rows = []
    yb = G
    jet = 0
    for f in range(floors):
        yt = yb - FH
        ax0, ax1 = X0 - jet, X1 + jet
        # side walls: doors at street level, solid walls above
        for side in (0, 1):
            wx = ax0 if side == 0 else ax1 - wt
            if f == 0:
                d = B.door(wx + (wt - 8) / 2, yb, 8, "plank")
                d.tint = None
                B.rect(wx, yt, wx + wt, yb - DOOR_H, post if not masonry_walls else wm, "lintel",
                       detail="grain" if not masonry_walls else "block")
                B.back(wx - 1, yb - DOOR_H - 2, wx + wt + 1, yb, "timber", "doorframe")
            else:
                if masonry_walls:
                    B.masonry(wx, wx + wt, yb, yt, wm, course=16, bw=(wt, wt + 1), jitter=0.5)
                else:
                    B.rect(wx, yt, wx + wt, yb, post, "wall", detail="grain")
        # the room behind
        if style == "log":
            p = B.back(ax0 + wt, yt, ax1 - wt, yb, "log", "backwall", detail="logs")
        elif masonry_walls:
            p = B.back(ax0 + wt, yt, ax1 - wt, yb, wm, "backwall", detail=MATS[wm].detail)
            for i in range(max(1, int((ax1 - ax0) // 48))):
                wx = ax0 + (i + 0.5) * (ax1 - ax0) / max(1, int((ax1 - ax0) // 48))
                B.back(wx - 6, yt + FH * 0.28, wx + 6, yt + FH * 0.28 + 16, "glass", "window", detail="arch_window")
                B.light(wx, yt + FH * 0.36, 0.35)
        elif style in ("longhouse", "wood", "snow"):
            B.back(ax0 + wt, yt, ax1 - wt, yb, "plank", "backwall", detail="boards_v")
        else:
            timber_back(B, ax0 + wt, ax1 - wt, yb, yt, rng)
        if f == 0:
            beds += interior(B, ax0 + wt, ax1 - wt, yb, rng, kind, beds=1 if floors == 1 else 0,
                             hearth=style not in ("tower",))
        elif f == floors - 1 or rng.random() < 0.6:
            beds += interior(B, ax0 + wt, ax1 - wt, yb, rng, kind, beds=1, hearth=False)
        # floor / ceiling
        if f < floors - 1:
            nj = jet + (6 if style == "burgher" else 0)
            B.rect(X0 - nj, yt - 6, X1 + nj, yt, "plank", "floor", platform=True, detail="boards")
            floor_rows.append(int((yt - 6) // TILE))
            B.ladder(ladder_x, yt - 6, yb)
            jet = nj
            yb = yt - 6
        else:
            B.rect(ax0 - 2, yt - 6, ax1 + 2, yt, "timber" if not masonry_walls else wm, "plate", detail="grain")
            yb = yt - 6
    top = yb
    ax0, ax1 = X0 - jet, X1 + jet
    # roofs, each culture its own
    if style == "brick":
        # Treppengiebel: a stepped gable of brick before a tiled roof
        mid = (ax0 + ax1) / 2
        rise = (ax1 - ax0) * 0.62
        gable(B, ax0, ax1, top, rise, "rooftile", over=4, frame=False, gable_mat="brick")
        steps = 5
        for i in range(steps):
            sw = (ax1 - ax0) / 2 * (1 - i / steps)
            sy = top - rise * i / steps
            B.rect(mid - sw - 3, sy - rise / steps, mid - sw + 7, sy, "brick", "step", detail="bricks")
            B.rect(mid + sw - 7, sy - rise / steps, mid + sw + 3, sy, "brick", "step", detail="bricks")
        B.rect(mid - 4, top - rise - 10, mid + 4, top - rise + 1, "brick", "step", detail="bricks")
        ridge = top - rise - 10
    elif style == "basalt":
        B.rect(ax0 - 4, top - 10, ax1 + 4, top, "basalt", "roof", detail="ashlar")
        B.rect(ax0 + 10, top - 26, ax0 + 22, top - 10, "basalt", "chimney", detail="ashlar")
        B.b.smoke.append((ax0 + 16, top - 28))
        # earth heaped against the walls against the heat
        for k, (dx, hh) in enumerate(((10, 30), (22, 16))):
            B.poly([(ax0 - dx, G), (ax0, G - hh), (ax0, G)], "earth", "berm")
            B.poly([(ax1, G - hh), (ax1 + dx, G), (ax1, G)], "earth", "berm")
        ridge = top - 26
    elif style == "tower":
        mid = (ax0 + ax1) / 2
        B.battlements(ax0 - 3, ax1 + 3, top, "ashlar", mw=10, gap=7, mh=10)
        rise = (ax1 - ax0) * 0.9
        B.poly([(ax0 + 4, top - 10), (mid, top - 10 - rise), (ax1 - 4, top - 10)], "slate", "roof",
               detail="slates")
        ridge = top - 10 - rise
        B.decor("flag", mid, ridge, 4, 18)
    else:
        rise = (ax1 - ax0) / 2 * PITCH.get(rm, 0.9)
        chim = (ax0 + (ax1 - ax0) * 0.72) if rm != "thatch" or rng.random() < 0.5 else None
        ridge, _, _ = gable(B, ax0, ax1, top, rise, rm, over=12 if rm == "thatch" else 9,
                            thick=11 if rm == "thatch" else 8, frame=style in ("peasant", "burgher", "chained"),
                            chimney=chim)
        if style == "longhouse":
            # dragon-head gable ends
            B.decor("gablehead", (ax0 + ax1) / 2, ridge + 2, 12, 12)
    if style == "chained":
        # at the Rand, where the ground pulls weakly, houses are chained down against the gusts
        for x in (ax0 - 18, ax1 + 18):
            B.decor("chain", x, G, 4, int(G - (top + 4)), to=(ax0 if x < ax0 else ax1, top + 4))
    B.light(ax0 - 6, G - 30, 0.0)
    dx = x0 if door_side == -1 else x0 + width - 1
    rec = dict(kind=kind, x0=x0, x1=x0 + width - 1, g=g, door=dx, beds=beds or [x0 + 2], work=x0 + width // 2,
               style=style, top=int(ridge // TILE), floors=floor_rows)
    return B.finish(rec)


def church(w, x0, g, width=13, rng=None):
    rng = rng or random.Random(x0)
    B = Builder(w, "church", "stone", rng)
    X0, X1, G = x0 * TILE, (x0 + width) * TILE, g * TILE
    tw = 4 * TILE
    T0, T1 = X1 - tw, X1
    nave_h = 6 * TILE
    # nave
    B.door(X0 + 2, G, 10, "plank")
    B.masonry(X0, X0 + 14, G - DOOR_H, G - nave_h, "ashlar", course=16, bw=(14, 15))
    B.back(X0 + 14, G - nave_h, T0, G, "ashlar", "backwall", detail="ashlar")
    for i in range(2):
        wx = X0 + 40 + i * ((T0 - X0 - 60) / 2)
        B.back(wx - 7, G - nave_h + 20, wx + 7, G - nave_h + 56, "glass", "window", detail="lancet")
        B.light(wx, G - nave_h + 38, 0.4)
    B.decor("altar", T0 - 26, G, 22, 16)
    B.decor("bench", X0 + 50, G, 30, 9)
    B.decor("bench", X0 + 90, G, 30, 9)
    B.rect(X0 - 2, G - nave_h - 6, T0, G - nave_h, "timber", "plate", detail="grain")
    gable(B, X0 - 2, T0, G - nave_h - 6, (T0 - X0) * 0.45, "slate", over=8, gable_mat="ashlar", frame=False)
    # tower with a spire
    th = 13 * TILE
    B.masonry(T0, T0 + 14, G, G - th, "ashlar", course=16, bw=(14, 15))
    B.masonry(T1 - 14, T1, G - DOOR_H, G - th, "ashlar", course=16, bw=(14, 15))
    B.door(T1 - 11, G, 8, "plank")
    B.back(T0 + 14, G - th, T1 - 14, G, "ashlar", "backwall", detail="ashlar")
    for f in range(1, 4):
        fy = G - f * 3 * TILE - 6
        B.rect(T0 + 14, fy, T1 - 14, fy + 6, "plank", "floor", platform=True, detail="boards")
    B.ladder(T0 + 24, G - 9 * TILE - 6, G)
    B.back(T0 + 20, G - th + 14, T1 - 20, G - th + 40, "glass", "belfry", detail="belfry")
    B.decor("bell", (T0 + T1) / 2, G - th + 34, 14, 14)
    B.rect(T0 - 3, G - th - 6, T1 + 3, G - th, "ashlar", "plate", detail="block")
    mid = (T0 + T1) / 2
    B.poly([(T0 - 2, G - th - 6), (mid, G - th - 6 - 6 * TILE), (T1 + 2, G - th - 6)], "slate", "roof",
           detail="slates")
    B.decor("cross", mid, G - th - 6 - 6 * TILE, 8, 14)
    top = G - th - 6 - 6 * TILE - 14
    return B.finish(dict(kind="church", x0=x0, x1=x0 + width - 1, g=g, door=x0 + width - 1, beds=[],
                         work=x0 + 2, style="stone", top=int(top // TILE)))


def windmill(w, x0, g, rng=None):
    rng = rng or random.Random(x0)
    B = Builder(w, "mill", "wood", rng)
    X0, G = x0 * TILE, g * TILE
    # Bockwindmühle: a post mill, the whole body turns on one post
    B.rect(X0 + 50, G - 70, X0 + 62, G, "timber", "pier", solid=False, detail="grain")
    B.poly([(X0 + 20, G), (X0 + 56, G - 50), (X0 + 60, G - 46), (X0 + 28, G)], "timber", "brace", solid=False)
    B.poly([(X0 + 92, G), (X0 + 56, G - 50), (X0 + 52, G - 46), (X0 + 84, G)], "timber", "brace", solid=False)
    B.rect(X0 + 26, G - 140, X0 + 86, G - 70, "plank", "found", detail="boards_v")
    B.poly([(X0 + 22, G - 140), (X0 + 56, G - 168), (X0 + 90, G - 140)], "shingle", "roof", detail="slates")
    B.slab((X0 + 86, G - 72), (X0 + 120, G - 40), 5, "timber", "stair", detail="grain")
    B.decor("sails", X0 + 24, G - 118, 120, 120)
    B.ladder(X0 + 100, G - 70, G)
    return B.finish(dict(kind="mill", x0=x0, x1=x0 + 7, g=g, door=x0 + 7, beds=[], work=x0 + 2, style="wood",
                         top=(G - 180) // TILE))


def well(w, x, g, rng=None):
    B = Builder(w, "well", "stone", rng)
    X, G = x * TILE, g * TILE
    B.masonry(X - 14, X + 14, G, G - 16, "stone", course=8, bw=(8, 12), role="rim")
    B.rect(X - 14, G - 42, X - 11, G - 16, "timber", "post", solid=False)
    B.rect(X + 11, G - 42, X + 14, G - 16, "timber", "post", solid=False)
    B.poly([(X - 20, G - 40), (X, G - 54), (X + 20, G - 40)], "shingle", "roof", solid=False, detail="slates")
    B.decor("bucket", X, G - 26, 6, 7)
    return B.finish(dict(kind="well", x0=x, x1=x, g=g, door=x, beds=[], work=x, style="stone", top=g - 3))


def field(w, x0, x1, g, rng, crop="wheat"):
    plot = Plot(x0 * TILE, (x1 + 1) * TILE, g * TILE, crop)
    w.plots.append(plot)
    w.index_add("decor_chunks", (x0 + x1) / 2 * TILE, Decor("plot", (x0 + x1 + 1) / 2 * TILE, g * TILE,
                                                             (x1 - x0 + 1) * TILE, 8, plot=len(w.plots) - 1))
    # a fence post at each end
    B = Builder(w, "field", "field", rng)
    B.rect(x0 * TILE - 3, g * TILE - 22, x0 * TILE + 1, g * TILE, "timber", "post", solid=False)
    B.rect((x1 + 1) * TILE - 1, g * TILE - 22, (x1 + 1) * TILE + 3, g * TILE, "timber", "post", solid=False)
    B.back(x0 * TILE - 3, g * TILE - 16, (x1 + 1) * TILE + 3, g * TILE - 14, "timber", "rail")
    return B.finish(dict(kind="field", x0=x0, x1=x1, g=g, door=x0, beds=[], work=(x0 + x1) // 2, style="field",
                         top=g - 2, crop=crop, plot=len(w.plots) - 1))


def ramp(B, x_low, y_low, x_high, y_high, mat="plank", thick=6, flat=14):
    """A sloped plank ramp that runs flush onto a deck (its top overlaps the deck so nothing catches)."""
    d = 1 if x_high > x_low else -1
    pts = [(x_low, y_low + 2), (x_high, y_high), (x_high + d * flat, y_high), (x_high + d * flat, y_high + thick),
           (x_high, y_high + thick), (x_low + d * thick * 1.5, y_low + 2)]
    pts = sorted(pts, key=lambda p: p[0]) if False else pts
    return B.poly(pts, mat, "ramp", detail="boards")


def walkway(w, x0, x1, g, rng=None):
    """A raised boardwalk over a field, so nobody tramples the crop on the way through the village."""
    B = Builder(w, "walkway", "wood", rng)
    X0, X1, G = x0 * TILE - 30, (x1 + 1) * TILE + 30, g * TILE
    deck = G - 50
    ramp(B, X0 - 62, G, X0, deck)
    ramp(B, X1 + 62, G, X1, deck)
    B.rect(X0, deck, X1, deck + 6, "plank", "deck", detail="boards")
    x = X0 + 4
    while x < X1:
        B.rect(x - 2, deck + 6, x + 2, G + 4, "timber", "pier", solid=False, detail="grain")
        x += 44
    B.back(X0, deck - 18, X1, deck - 16, "timber", "rail")
    return B.finish(None)


def bridge(w, x0, x1, deck_row, rng, stone=True):
    B = Builder(w, "bridge", "stone" if stone else "wood", rng)
    X0, X1 = x0 * TILE, (x1 + 1) * TILE
    bank_l, bank_r = w.surface_y(X0 - 8), w.surface_y(X1 + 8)
    top = min(bank_l, bank_r) - 1
    D = top + (12 if stone else 8)
    for xb, yb, d in ((X0 - 8, bank_l, -1), (X1 + 8, bank_r, 1)):
        if yb > top + 3:
            ramp(B, xb + d * (yb - top) * 1.6, w.surface_y(xb + d * (yb - top) * 1.6), xb - d * 4, top,
                 "cobble" if stone else "plank", thick=8)
    span = X1 - X0
    if stone:
        n = max(1, int(span // 120))
        bay = span / n
        B.rect(X0 - 16, D - 12, X1 + 16, D, "cobble", "deck", detail="rough").grounded_hint = True
        B.battlements(X0, X1, D - 12, "stone", mw=8, gap=16, mh=8)
        for i in range(n + 1):
            px = X0 + i * bay
            bot = max(w.surface_y(px - 10), w.surface_y(px + 10)) + 10
            if bot > D + 4:
                B.masonry(px - 10, px + 10, bot, D, "stone", course=14, bw=(20, 21), role="pier")
        for i in range(n):
            a, b_ = X0 + i * bay + 10, X0 + (i + 1) * bay - 10
            cxm = (a + b_) / 2
            r = (b_ - a) / 2
            k = 9
            for j in range(k):
                t0, t1 = math.pi * j / k, math.pi * (j + 1) / k
                ri, ro = r, r + 12
                pts = [(cxm - math.cos(t0) * ri, D + 12 + r - math.sin(t0) * ri * 0.75 - r * 0.25),
                       (cxm - math.cos(t1) * ri, D + 12 + r - math.sin(t1) * ri * 0.75 - r * 0.25),
                       (cxm - math.cos(t1) * ro, D + 12 + r - math.sin(t1) * ro * 0.75 - r * 0.25),
                       (cxm - math.cos(t0) * ro, D + 12 + r - math.sin(t0) * ro * 0.75 - r * 0.25)]
                ys = [p[1] for p in pts]
                pts = [(x, max(D, y)) for x, y in pts]
                if max(ys) > D + 1:
                    B.poly(pts, "stone", "arch", detail="block")
            B.back(a, D, b_, D + 12, "stone", "spandrel", detail="rough")
    else:
        B.rect(X0 - 10, D - 8, X1 + 10, D, "plank", "deck", detail="boards")
        x = X0
        while x <= X1:
            bot = w.surface_y(x) + 6
            if bot > D + 8:
                B.rect(x - 3, D, x + 3, bot, "log", "pier", detail="grain")
                if x + 40 <= X1:
                    B.poly([(x, D + 4), (x + 40, min(bot, D + 60)), (x + 36, min(bot, D + 60) + 4),
                            (x - 2, D + 8)], "timber", "brace", solid=False)
            x += 40
        B.back(X0, D - 22, X1, D - 20, "timber", "rail")
        x = X0
        while x <= X1:
            B.back(x - 1, D - 22, x + 1, D - 8, "timber", "rail")
            x += 20
    return B.finish(None)


def stall(w, x0, g, rng):
    B = Builder(w, "stall", "market", rng)
    X0, G = x0 * TILE, g * TILE
    col = rng.choice([(170, 50, 40), (60, 90, 150), (200, 170, 60), (80, 130, 70)])
    B.rect(X0 + 2, G - 48, X0 + 5, G, "timber", "post", solid=False)
    B.rect(X0 + 55, G - 48, X0 + 58, G, "timber", "post", solid=False)
    p = B.slab((X0 - 6, G - 44), (X0 + 66, G - 50), 6, "cloth", "awning", solid=False, detail="stripes")
    p.tint = col
    B.rect(X0 + 4, G - 18, X0 + 56, G - 14, "plank", "counter", platform=True, detail="boards")
    B.decor("goods", X0 + 30, G - 18, 40, 10, ware=rng.choice(["bread", "cloth", "pots", "fish", "veg"]))
    return B.finish(dict(kind="stall", x0=x0, x1=x0 + 3, g=g, door=x0, beds=[], work=x0 + 1, style="market",
                         top=g - 5))


def palisade(w, x, g, height=5, rng=None):
    B = Builder(w, "palisade", "wood", rng)
    X, G = x * TILE, g * TILE
    H = height * TILE
    for i in range(3):
        sx = X + i * 6 - 6
        h = H + (i % 2) * 6
        if i == 1:
            # the stakes stop above head height; below is a wicket gate
            B.poly([(sx, G - 46), (sx, G - h + 8), (sx + 3, G - h), (sx + 6, G - h + 8), (sx + 6, G - 46)], "log",
                   "stake", detail="grain")
            d = B.door(sx - 1, G, 8, "plank", height=44)
            continue
        B.poly([(sx, G - 46), (sx, G - h + 8), (sx + 3, G - h), (sx + 6, G - h + 8), (sx + 6, G - 46)], "log",
               "stake", detail="grain")
        B.rect(sx, G - 46, sx + 6, G, "log", "stake", solid=False, detail="grain")
    return B.finish(None)


def wall_tower(w, x0, g, height=8, thick=2, gate=True, battlement=True, mat="stone", rng=None):
    """A stretch of town wall with a gate passage and a fighting platform on top."""
    rng = rng or random.Random(x0)
    B = Builder(w, "wall", "stone", rng)
    X0, G = x0 * TILE, g * TILE
    X1 = X0 + thick * TILE + 8
    H = height * TILE
    gate_h = 3 * TILE + 4

    def opening(a, y0, b, y1):
        return gate and y0 >= G - gate_h - 1

    B.masonry(X0, X1, G, G - H, mat, course=15, bw=(16, 26), skip=opening)
    if gate:
        B.rect(X0, G - gate_h - 8, X1, G - gate_h, "timber", "lintel", detail="grain")
        d = B.door(X0 + 8, G, X1 - X0 - 16, "plank", height=gate_h)
        d.role = "door"
        d.detail = "gate"
        d.max_hp = d.hp = d.hp * 4
        B.back(X0 - 2, G - gate_h - 10, X1 + 2, G, "stone", "gate_back", detail="arch_shadow")
    if battlement:
        B.battlements(X0 - 4, X1 + 4, G - H, mat, mw=10, gap=8)
    B.ladder(X1 + 8, G - H, G)
    B.decor("torch", X0 - 4, G - 50, 4, 10)
    B.light(X0 - 4, G - 54, 0.8)
    return B.finish(dict(kind="wall", x0=x0, x1=x0 + thick, g=g, door=x0, beds=[], work=x0, style="stone",
                         top=g - height - 1, gate=gate))


def tower(w, x0, g, width=7, height=16, mat="ashlar", roofmat="slate", rng=None):
    """Bergfried: the keep, the last refuge."""
    rng = rng or random.Random(x0)
    B = Builder(w, "tower", "stone", rng)
    X0, X1, G = x0 * TILE, (x0 + width) * TILE, g * TILE
    H = height * TILE
    th = 16
    B.masonry(X0, X0 + th, G - DOOR_H - 4, G - H, mat, course=16, bw=(th, th + 1))
    B.masonry(X1 - th, X1, G - DOOR_H - 4, G - H, mat, course=16, bw=(th, th + 1))
    B.rect(X0, G - DOOR_H - 4, X0 + th, G - DOOR_H, "timber", "lintel")
    B.rect(X1 - th, G - DOOR_H - 4, X1, G - DOOR_H, "timber", "lintel")
    B.door(X0 + 4, G, 8, "plank")
    B.door(X1 - 12, G, 8, "plank")
    B.back(X0 + th, G - H, X1 - th, G, mat, "backwall", detail=MATS[mat].detail)
    floors = []
    fh = 4 * TILE
    y = G - fh
    while y > G - H + 20:
        B.rect(X0 + th, y - 6, X1 - th, y, "plank", "floor", platform=True, detail="boards")
        floors.append(int((y - 6) // TILE))
        B.back(X0 + th + 10, y - fh + 16, X0 + th + 20, y - fh + 36, "glass", "window", detail="slit")
        B.back(X1 - th - 20, y - fh + 16, X1 - th - 10, y - fh + 36, "glass", "window", detail="slit")
        y -= fh + 6
    B.ladder(X0 + th + 8, G - H, G)
    B.rect(X0 - 4, G - H - 6, X1 + 4, G - H, mat, "plate", detail="block")
    B.battlements(X0 - 4, X1 + 4, G - H - 6, mat, mw=11, gap=8)
    mid = (X0 + X1) / 2
    if roofmat:
        B.poly([(X0 + 6, G - H - 6), (mid, G - H - 6 - width * TILE * 0.9), (X1 - 6, G - H - 6)], roofmat, "roof",
               detail=MATS[roofmat].detail)
        B.decor("flag", mid, G - H - 6 - width * TILE * 0.9, 4, 20)
    else:
        B.decor("flag", mid, G - H - 18, 4, 26)     # an open fighting top
    B.decor("bed", X0 + th + 30, floors[0] * TILE + TILE if floors else G, 22, 10)
    return B.finish(dict(kind="tower", x0=x0, x1=x0 + width - 1, g=g, door=x0 + width - 1, beds=[x0 + 2],
                         work=x0 + width // 2, style="stone", top=int((G - H) // TILE) - 6, floors=floors))


def great_hall(w, x0, g, width=17, height=6, rng=None):
    """Palas: the lord's hall."""
    rng = rng or random.Random(x0)
    B = Builder(w, "hall", "stone", rng)
    X0, X1, G = x0 * TILE, (x0 + width) * TILE, g * TILE
    H = height * TILE
    for wx in (X0, X1 - 14):
        B.door(wx + 3, G, 8, "plank")
        B.masonry(wx, wx + 14, G - DOOR_H, G - H, "ashlar", course=16, bw=(14, 15))
    B.back(X0 + 14, G - H, X1 - 14, G, "ashlar", "backwall", detail="ashlar")
    for i in range(3):
        wx = X0 + (i + 1) * (X1 - X0) / 4
        B.back(wx - 8, G - H + 18, wx + 8, G - H + 48, "glass", "window", detail="arch_window")
        B.light(wx, G - H + 32, 0.4)
    B.decor("throne", X1 - 40, G, 18, 26)
    B.decor("table", (X0 + X1) / 2, G, 60, 12)
    B.decor("hearth", X0 + 40, G, 24, 18)
    B.decor("banner", X0 + 70, G - H + 10, 12, 30)
    B.light(X0 + 40, G - 10, 1.0)
    B.rect(X0 - 2, G - H - 6, X1 + 2, G - H, "timber", "plate", detail="grain")
    gable(B, X0 - 2, X1 + 2, G - H - 6, (X1 - X0) * 0.4, "slate", over=8, gable_mat="ashlar", frame=False,
          chimney=X0 + 40)
    return B.finish(dict(kind="hall", x0=x0, x1=x0 + width - 1, g=g, door=x0, beds=[x0 + 2], work=x1t(x0, width),
                         style="stone", top=int((G - H) // TILE) - 8))


def x1t(x0, width):
    return x0 + width - 3


def castle(w, x0, g, rng, size="castle"):
    """Curtain towers, gatehouses, the keep (Bergfried), the hall (Palas), a smithy. Returns (records, x1)."""
    recs = []
    x = x0
    recs.append(tower(w, x, g, width=6, height=14, rng=rng, roofmat=None if size == "castle" else "slate"))
    x += 6
    gate_w = wall_tower(w, x, g, height=10, thick=2, gate=True, mat="ashlar", rng=rng)
    gate_w["kind"] = "gatehouse"
    recs.append(gate_w)
    x += 3
    keep_x = x + 3
    recs.append(tower(w, keep_x, g, width=9, height=22 if size != "castle" else 19, rng=rng))
    recs[-1]["kind"] = "keep"
    hall_x = keep_x + 12
    hw = 17 if size == "capital" else 13
    recs.append(great_hall(w, hall_x, g, width=hw, rng=rng))
    cur = hall_x + hw + 3
    if size != "castle":
        recs.append(house(w, cur, g, width=9, height=4, style="stone", rng=rng, kind="barracks"))
        cur += 11
    smith = house(w, cur, g, width=8, height=4, style="stone", rng=rng, kind="smithy")
    from .gen import smithy_fittings
    smithy_fittings(w, smith)
    recs.append(smith)
    end = max(x + 46, cur + 10)
    gate_e = wall_tower(w, end, g, height=10, thick=2, gate=True, mat="ashlar", rng=rng)
    gate_e["kind"] = "gatehouse"
    recs.append(gate_e)
    recs.append(tower(w, end + 3, g, width=6, height=14, rng=rng, roofmat=None if size == "castle" else "slate"))
    if size == "castle":
        fortify(w, gate_w, -1, rng, outer=recs[0])
        fortify(w, gate_e, 1, rng, outer=recs[-1])
    return recs, end + 10


class Gatehouse:
    """Moat, drawbridge, portcullis, machicolation and winch of one gate."""

    def __init__(self, w, hinge_x, ground_y, side, gate_rec, moat):
        self.hinge = (hinge_x, ground_y)
        self.side = side
        self.gate = gate_rec
        self.moat = moat
        self.x = int((moat[0] + moat[1]) / 2 // TILE)
        self.g = int(ground_y // TILE)
        self.length = abs(moat[1] - moat[0]) + 26
        self.closed = False
        self.auto = True
        self.calm = 0.0
        self.pitch_t = 3.0
        self.pitch = 6
        self.held = 0.0
        self.forced = False
        self.angle = 0.0                   # 0 = down, raised = -side * pi/2
        self.port = 0.0                    # 0 = up (open), 1 = down (closed)
        X0, X1 = gate_rec["x0"] * TILE, (gate_rec["x1"] + 1) * TILE + 8
        self.port_x = X0 + 6 if side < 0 else X1 - 12
        self.gate_x = (X0, X1)
        self.gate_h = 3 * TILE + 4
        self.pechnase = (hinge_x - side * 2, ground_y - 10 * TILE)
        self.winch = (X1 + 10 if side < 0 else X0 - 10, ground_y)
        self.bridge = self.bshape = self.pbody = self.pshape = None
        self.owner = None

    def __getstate__(self):
        d = self.__dict__.copy()
        for k in ("bridge", "bshape", "pbody", "pshape"):
            d[k] = None
        return d

    def get(self, k, default=None):
        """Old dict-style access used by story and battle code."""
        return getattr(self, k, default)

    def __getitem__(self, k):
        return getattr(self, k)

    def __setitem__(self, k, v):
        setattr(self, k, v)

    def attach(self, w):
        hx, hy = self.hinge
        L = self.length * self.side
        b = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        b.position = (hx, hy)
        b.angle = self.angle
        pts = [(0, 0), (L, 0), (L, 8), (0, 8)] if self.side > 0 else [(L, 0), (0, 0), (0, 8), (L, 8)]
        sh = pymunk.Poly(b, pts)
        sh.friction = 0.9
        sh.filter = F_STRUCT
        sh.collision_type = CT_BLOCK
        sh.owner = None
        b2 = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        b2.position = (self.port_x, hy - self.gate_h * (1 - self.port))
        sh2 = pymunk.Poly(b2, [(0, 0), (8, 0), (8, self.gate_h - 2), (0, self.gate_h - 2)])
        sh2.filter = F_STRUCT
        sh2.collision_type = CT_BLOCK
        sh2.sensor = self.port < 0.9
        sh2.owner = _PortTag()
        w.space.add(b, sh, b2, sh2)
        self.bridge, self.bshape, self.pbody, self.pshape = b, sh, b2, sh2
        if self not in w.kinematics:
            w.kinematics.append(self)

    def update(self, w, dt):
        if self.bridge is None:
            self.attach(w)
        want_a = -self.side * math.pi / 2 * 0.98 if self.closed else 0.0
        d = want_a - self.bridge.angle
        self.bridge.angular_velocity = max(-0.9, min(0.9, d / max(dt, 1e-3))) if abs(d) > 0.002 else 0.0
        self.angle = self.bridge.angle
        want_p = 1.0 if self.closed else 0.0
        dp = want_p - self.port
        self.port += max(-dt * 0.6, min(dt * 1.4, dp))     # it drops faster than it is winched up
        hx, hy = self.hinge
        target_y = hy - self.gate_h * (1 - self.port)
        self.pbody.velocity = (0, (target_y - self.pbody.position.y) / max(dt, 1e-3))
        self.pshape.sensor = self.port < 0.9

    def bridge_points(self):
        if self.bridge is None:
            return []
        return [self.bridge.local_to_world(v) for v in self.bshape.get_vertices()]

    def port_points(self):
        if self.pbody is None:
            return []
        return [self.pbody.local_to_world(v) for v in self.pshape.get_vertices()]


class _PortTag:
    role = "portcullis"
    mat = "iron"


def fortify(w, gate_rec, side, rng, outer=None):
    """Dig a moat outside the gate (and its flanking tower), lay a drawbridge over it, hang a portcullis."""
    ref = outer or gate_rec
    X0, X1 = ref["x0"] * TILE, (ref["x1"] + 1) * TILE
    G = gate_rec["g"] * TILE
    hinge_x = X0 - 2 if side < 0 else X1 + 2
    m0 = hinge_x + side * 6
    m1 = hinge_x + side * 6 + side * 7 * TILE
    a, b = sorted((m0, m1))
    i0, i1 = int(a // TILE), int(b // TILE) + 1
    depth = 4 * TILE
    ys = []
    for i in range(i0, i1 + 1):
        x = i * TILE
        t = (x - a) / max(1, b - a)
        bank = min(1.0, min(t, 1 - t) * 5)
        ys.append(G + depth * bank)
    w.set_surface(i0, i1 + 1, ys)
    from .world import Water
    w.water.append(Water(a + 4, b - 4, G + 14, False))
    w.water.sort(key=lambda r_: r_.x0)
    gh = Gatehouse(w, hinge_x, G, side, gate_rec, (a, b))
    w.gatehouses.append(gh)
    B = Builder(w, "pechnase", "stone", rng)
    px, py = gh.pechnase
    B.rect(px - 10 if side < 0 else px - 4, py - 4, px + 4 if side < 0 else px + 10, py + 12, "ashlar", "merlon",
           detail="block")
    B.decor("pechnase", px, py + 12, 12, 16)
    B.decor("winch", gh.winch[0], G - 12, 12, 12)
    B.finish(None)
    return gh


def dock(w, shore_x, g_water, length, direction, rng):
    B = Builder(w, "dock", "wood", rng)
    xs = [shore_x + direction * i for i in range(length)]
    X0, X1 = min(xs) * TILE, (max(xs) + 1) * TILE
    D = g_water * TILE - 10
    B.rect(X0, D - 6, X1, D, "plank", "deck", detail="boards")
    x = X0 + 6
    while x < X1:
        bot = w.surface_y(x) + 8
        B.rect(x - 3, D, x + 3, bot, "log", "pier", detail="grain")
        x += 48
    B.decor("bollard", X0 + 20 if direction > 0 else X1 - 20, D - 6, 6, 8)
    end = xs[-1]
    return B.finish(dict(kind="dock", x0=min(xs), x1=max(xs), g=int((D - 6) // TILE), door=xs[2], beds=[],
                         work=end, style="wood", top=int((D - 30) // TILE), berth=end + direction * 4))


def shipwreck(w, x0, g, rng):
    B = Builder(w, "wreck", "wood", rng)
    X, G = x0 * TILE, w.surface_y(x0 * TILE)
    B.poly([(X - 60, G - 30), (X + 70, G - 12), (X + 60, G + 4), (X - 50, G)], "plank", "hull", detail="boards")
    B.poly([(X - 10, G - 24), (X - 2, G - 24), (X + 30, G - 120), (X + 24, G - 122)], "timber", "mast",
           solid=False)
    B.decor("chest", X + 20, G - 14, 16, 12, items={"silver_coin": rng.randint(20, 80)}, sunken=True)
    return B.finish(None)


def mine_shaft(w, x, g, depth, rng):
    from shapely.geometry import box as sbox
    B = Builder(w, "mine", "wood", rng)
    X, G = x * TILE, g * TILE
    bottom = G + depth * TILE
    w.add_cave(sbox(X - 14, G - 4, X + 14, bottom))
    # a gallery at the bottom running into the hill
    w.add_cave(sbox(X - 14, bottom - 46, X + 260, bottom).union(sbox(X + 200, bottom - 80, X + 330, bottom)))
    B.ladder(X, G - 4, bottom)
    y = G + 40
    while y < bottom:
        B.back(X - 14, y - 4, X + 14, y, "timber", "frame")
        B.back(X - 14, y - 40, X - 10, y, "timber", "frame")
        B.back(X + 10, y - 40, X + 14, y, "timber", "frame")
        y += 48
    # headframe with a winch
    B.rect(X - 20, G - 60, X - 16, G, "timber", "post", solid=False)
    B.rect(X + 16, G - 60, X + 20, G, "timber", "post", solid=False)
    B.rect(X - 22, G - 64, X + 22, G - 58, "timber", "beam", solid=False)
    B.decor("winch", X, G - 58, 10, 10)
    B.decor("lantern", X + 100, bottom - 20, 6, 10)
    B.light(X + 100, bottom - 24, 0.9)
    for i in range(6):
        w.ores.append(dict(x=X + 60 + i * 44, y=bottom - 46 + rng.choice((0, 46)), kind=rng.choice(
            ["iron", "iron", "coal", "silver"]), hp=40, left=5))
    return B.finish(None)


def charcoal_kiln(w, x, g, rng):
    """Kohlenmeiler: a smoking earth mound where wood becomes charcoal."""
    B = Builder(w, "kiln", "earth", rng)
    X, G = x * TILE, g * TILE
    pts = [(X - 64 + i * 8, G - 40 * math.sin(math.pi * i / 16) ** 0.8) for i in range(17)]
    B.poly(pts, "earth", "mound", solid=False, detail="turf")
    B.b.smoke.append((X, G - 42))
    w.smokers.append((x, g - 4))
    return B.finish(None)
