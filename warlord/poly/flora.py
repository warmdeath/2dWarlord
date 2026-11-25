"""Trees and plants as faceted low-poly shapes.

A tree is a trunk, a few branches and a crown built from overlapping facetted clumps, all generated from
its seed when it first comes into view. Crowns sway with the wind (more at the top), change with the
seasons, and when a tree is felled its trunk becomes a real rigid body that topples on a hinge at the stump.
"""
import math
import random

import pygame

# hit points for a tree of 180 px with a 13 px trunk; they grow with height and with the trunk's cross-section,
# so a slim birch falls in a few strokes and an old oak takes a good while (hard, dense wood on top)
TREE_HP = {"oak": 260, "beech": 200, "pine": 110, "fir": 120, "birch": 60, "dead": 40, "willow": 80, "lime": 150}
LEAF = {
    "oak": [(64, 104, 46), (82, 126, 54), (104, 146, 62)],
    "beech": [(76, 116, 48), (98, 140, 58), (124, 162, 70)],
    "lime": [(70, 118, 52), (92, 140, 62), (118, 160, 74)],
    "birch": [(92, 136, 58), (118, 158, 70), (146, 180, 86)],
    "willow": [(86, 120, 60), (108, 140, 70), (132, 160, 84)],
    "pine": [(36, 70, 46), (48, 88, 54), (62, 106, 62)],
    "fir": [(30, 62, 48), (40, 78, 56), (54, 96, 64)],
}
AUTUMN = {"oak": [(140, 88, 34), (176, 112, 40), (200, 146, 56)],
          "beech": [(160, 76, 30), (196, 104, 38), (218, 140, 54)],
          "lime": [(170, 140, 46), (200, 170, 60), (224, 196, 84)],
          "birch": [(186, 150, 48), (214, 182, 64), (236, 206, 92)],
          "willow": [(150, 140, 60), (176, 164, 76), (198, 186, 96)]}
SPRING = {"oak": [(92, 140, 56), (118, 164, 66), (146, 186, 82)],
          "beech": [(110, 158, 60), (138, 182, 70), (166, 202, 92)],
          "lime": [(100, 152, 60), (128, 176, 72), (156, 196, 90)],
          "birch": [(124, 170, 70), (152, 192, 84), (180, 210, 104)],
          "willow": [(118, 160, 76), (142, 180, 90), (168, 200, 110)]}
BARK = {"oak": (78, 58, 42), "beech": (120, 116, 106), "lime": (92, 76, 60), "pine": (104, 66, 46),
        "fir": (86, 62, 48), "birch": (226, 222, 210), "dead": (96, 84, 72), "willow": (98, 82, 64)}
EVERGREEN = {"pine", "fir"}


class Tree:
    def __init__(self, kind, x, y, height, trunk, seed):
        self.kind = kind
        self.x, self.y = float(x), float(y)
        self.h = float(height)
        self.tw = float(trunk)
        self.seed = seed
        hp = TREE_HP.get(kind, 60) * (height / 180.0) * (trunk / 13.0) ** 2
        self.hp = self.max_hp = max(30.0 if kind == "dead" else 60.0, hp)
        self.state = "stand"     # stand | stump
        self.regrow = 0.0
        self.burn = 0.0
        self.lean = random.Random(seed).uniform(-0.05, 0.05)
        self.shake = 0.0
        self._geo = None

    def __getstate__(self):
        d = self.__dict__.copy()
        d["_geo"] = None
        return d

    def bbox(self):
        r = self.h * 0.45
        return (self.x - r, self.y - self.h - 20, self.x + r, self.y)

    def geo(self):
        if self._geo is None:
            self._geo = build(self)
        return self._geo


def blob(rng, cx, cy, r, n=7, squash=0.82):
    pts = []
    a0 = rng.uniform(0, math.pi * 2)
    for i in range(n):
        a = a0 + math.pi * 2 * i / n
        rr = r * rng.uniform(0.78, 1.08)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * squash))
    return pts


def build(t):
    """Local geometry: (x right, y up is negative) relative to the trunk base."""
    rng = random.Random(t.seed)
    H, tw = t.h, t.tw
    k = t.kind
    g = {"trunk": None, "branches": [], "clumps": [], "tiers": [], "strands": []}
    top = -H
    if k in ("pine", "fir"):
        g["trunk"] = [(-tw / 2, 0), (tw / 2, 0), (tw * 0.12, top), (-tw * 0.12, top)]
        tiers = rng.randint(4, 6)
        for i in range(tiers):
            f = i / tiers
            yb = -H * (0.22 + 0.74 * f)
            wdt = H * (0.30 if k == "fir" else 0.24) * (1 - f * 0.78)
            ht = H * 0.26 * (1 - f * 0.3)
            sk = rng.uniform(-3, 3)
            g["tiers"].append([(-wdt + sk, yb), (sk * 0.3, yb - ht), (wdt + sk, yb), (sk * 0.5, yb - ht * 0.25)])
        return g
    if k == "dead":
        g["trunk"] = [(-tw / 2, 0), (tw / 2, 0), (tw * 0.2, top * 0.85), (-tw * 0.2, top * 0.85)]
        for i in range(rng.randint(3, 5)):
            yy = -H * rng.uniform(0.4, 0.8)
            d = rng.choice((-1, 1))
            ln = H * rng.uniform(0.18, 0.32)
            ex = d * ln
            ey = yy - ln * rng.uniform(0.3, 0.8)
            g["branches"].append(((0, yy), (ex, ey), max(1.5, tw * 0.18)))
            g["branches"].append(((ex * 0.6, yy + (ey - yy) * 0.6), (ex * 0.6 + d * ln * 0.3, ey - ln * 0.3), 1.2))
        return g
    # broadleaves
    bend = rng.uniform(-0.06, 0.06) * H
    g["trunk"] = [(-tw / 2, 0), (tw / 2, 0), (tw * 0.22 + bend, -H * 0.62), (-tw * 0.22 + bend, -H * 0.62)]
    for i in range(rng.randint(3, 4)):
        d = -1 if i % 2 == 0 else 1
        yy = -H * rng.uniform(0.45, 0.62)
        ln = H * rng.uniform(0.18, 0.28)
        g["branches"].append(((bend * 0.8, yy), (bend + d * ln, yy - ln * 0.7), max(1.5, tw * 0.2)))
    cr = H * (0.31 if k != "birch" else 0.21)
    ccy = -H * 0.70
    n = rng.randint(9, 13)
    for i in range(n):
        a = rng.uniform(0, math.pi * 2)
        dist = rng.uniform(0, cr * 0.75)
        cx = bend + math.cos(a) * dist * (1.15 if k != "birch" else 0.7)
        cy = ccy + math.sin(a) * dist * 0.75
        r = cr * rng.uniform(0.38, 0.58)
        g["clumps"].append((blob(rng, cx, cy, r, rng.randint(6, 8)), cy - ccy, cx - bend))
    g["clumps"].sort(key=lambda c: -c[1])   # lower ones first so the lit top sits in front
    if k == "willow":
        for i in range(14):
            sx = bend + rng.uniform(-cr, cr)
            sy = ccy + rng.uniform(-cr * 0.4, cr * 0.3)
            g["strands"].append((sx, sy, rng.uniform(H * 0.25, H * 0.45)))
    return g


def shade(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def season_palette(kind, season):
    if kind in EVERGREEN:
        return LEAF[kind]
    if season == "herbst":
        return AUTUMN.get(kind, LEAF.get(kind, LEAF["oak"]))
    if season == "fruehling":
        return SPRING.get(kind, LEAF.get(kind, LEAF["oak"]))
    return LEAF.get(kind, LEAF["oak"])


def draw_tree(surf, t, ox, oy, time, wind, season, light=1.0, zoom=1.0):
    g = t.geo()
    bx, by = t.x - ox, t.y - oy
    H = t.h
    sway_amp = (1.5 + abs(wind) * 4.0) * (H / 120.0)
    ph = time * (1.3 + abs(wind) * 0.6) + t.seed * 0.37
    sway = math.sin(ph) * sway_amp * 0.6 + wind * 3.0 * (H / 120) + t.shake * math.sin(time * 40) * 3

    def P(x, y):
        f = max(0.0, -y / H) ** 1.6
        return (bx + (x + t.lean * -y + sway * f) * zoom, by + y * zoom)

    bark = BARK.get(t.kind, BARK["oak"])
    if t.state == "stump":
        tw = t.tw
        pts = [P(-tw / 2 - 1, 0), P(tw / 2 + 1, 0), P(tw / 2, -9), P(-tw / 2, -7)]
        pygame.draw.polygon(surf, shade(bark, 0.85 * light), pts)
        pygame.draw.polygon(surf, shade((196, 164, 112), light), [P(-tw / 2, -7), P(tw / 2, -9), P(0, -10)])
        if t.regrow > 0.3:
            s = (t.regrow - 0.3) * 30
            pygame.draw.line(surf, shade((70, 120, 50), light), P(tw / 2 + 3, 0), P(tw / 2 + 5, -s), 2)
            pygame.draw.circle(surf, shade((90, 140, 60), light), P(tw / 2 + 5, -s), max(2, int(s * 0.3)))
        return
    winter_bare = season == "winter" and t.kind not in EVERGREEN
    pal = season_palette(t.kind, season)
    burn = t.burn > 0
    if burn:
        pal = [(60, 40, 30), (90, 50, 30), (120, 60, 30)]
    # trunk with a lit and a shaded half
    tr = [P(x, y) for x, y in g["trunk"]]
    pygame.draw.polygon(surf, shade(bark, 0.78 * light), tr)
    mid_b = ((tr[0][0] + tr[1][0]) / 2, tr[0][1])
    mid_t = ((tr[2][0] + tr[3][0]) / 2, tr[2][1])
    pygame.draw.polygon(surf, shade(bark, 1.0 * light), [tr[0], mid_b, mid_t, tr[3]])
    if t.kind == "birch":
        rng = random.Random(t.seed)
        for i in range(7):
            yy = -H * rng.uniform(0.05, 0.6)
            ww = t.tw * rng.uniform(0.3, 0.6)
            a, b = P(-ww / 2, yy), P(ww / 2, yy - 1)
            pygame.draw.line(surf, (40, 40, 40), a, b, 2)
    for a, b, wdt in g["branches"]:
        pygame.draw.line(surf, shade(bark, 0.85 * light), P(*a), P(*b), max(1, int(wdt * zoom)))
    if g["tiers"]:
        for i, tier in enumerate(g["tiers"]):
            pts = [P(x, y) for x, y in tier]
            base = pal[min(2, i * 3 // len(g["tiers"]))]
            pygame.draw.polygon(surf, shade(base, 0.8 * light), pts)
            pygame.draw.polygon(surf, shade(base, 1.06 * light), [pts[0], pts[1], pts[3]])
            if season == "winter":
                pygame.draw.polygon(surf, shade((236, 240, 246), light), [
                    pts[1], ((pts[1][0] + pts[2][0]) / 2, (pts[1][1] * 0.6 + pts[2][1] * 0.4)),
                    ((pts[1][0] + pts[0][0]) / 2, (pts[1][1] * 0.6 + pts[0][1] * 0.4))])
        return
    if winter_bare:
        for (pts, dy, dx) in g["clumps"][:4]:
            c = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            pygame.draw.line(surf, shade(bark, 0.8 * light), P(0, -H * 0.55), P(*c), max(1, int(t.tw * 0.18)))
            for p in pts[::2]:
                pygame.draw.line(surf, shade(bark, 0.9 * light), P(*c), P((p[0] + c[0]) / 2, (p[1] + c[1]) / 2), 1)
        return
    for (pts, dy, dx) in g["clumps"]:
        sp = [P(x, y) for x, y in pts]
        lvl = 0 if dy > 0 else (2 if dy < -H * 0.08 else 1)
        base = pal[lvl]
        pygame.draw.polygon(surf, shade(base, 0.86 * light), sp)
        # a lit facet toward the upper left
        n = len(sp)
        cxs = sum(p[0] for p in sp) / n
        cys = sum(p[1] for p in sp) / n
        best = min(range(n), key=lambda i: sp[i][0] + sp[i][1])
        pygame.draw.polygon(surf, shade(base, 1.08 * light),
                            [sp[(best - 1) % n], sp[best], sp[(best + 1) % n], (cxs, cys)])
        pygame.draw.polygon(surf, shade(base, 0.7 * light),
                            [sp[(best + n // 2) % n], sp[(best + n // 2 + 1) % n], (cxs, cys)])
    for sx, sy, ln in g["strands"]:
        pygame.draw.line(surf, shade(pal[1], 0.9 * light), P(sx, sy), P(sx + sway * 0.3, sy + ln), 2)
