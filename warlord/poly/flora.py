"""Trees and plants, painted.

A tree is a trunk with flaring roots and textured bark, a branching skeleton and a crown painted from
hundreds of leaf dabs in clumps (shadow, mid tone, sunlit leaves), generated from its seed when it first
comes into view and cached as sprites: the back of the crown, the wood, and the front of the crown, which
sway by different amounts so the crown seems to rustle. Crowns sway with the wind (more at the top), change with the
seasons, and when a tree is felled its trunk becomes a real rigid body that topples on a hinge at the stump.
"""
import math
import random
from collections import OrderedDict

import pygame

from ..gfx import paint
from ..gfx.paint import SS, warm, jitter

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

    def __getstate__(self):
        d = self.__dict__.copy()
        d.pop("_geo", None)
        return d

    def bbox(self):
        r = self.h * 0.45
        return (self.x - r, self.y - self.h - 20, self.x + r, self.y)



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


# ====================================================================== painted trees
SHAPE = {   # crown half-width, half-height (fractions of the height), centre height, clump size, leafiness
    "oak": (0.40, 0.25, 0.68, 0.30, 1.0),
    "beech": (0.32, 0.30, 0.66, 0.27, 1.0),
    "lime": (0.28, 0.34, 0.64, 0.25, 1.0),
    "birch": (0.19, 0.30, 0.64, 0.17, 0.75),
    "willow": (0.34, 0.22, 0.70, 0.24, 0.9),
}
_SPR = OrderedDict()
SPR_CAP = 260


def _key(t, season):
    return (id(t), season, t.burn > 0, round(t.h), t.state)


def has_sprites(t, season):
    s = _SPR.get(_key(t, season))
    return s is not None and s["tree"] is t


def sprites(t, season):
    """The tree's painted sprites, built on first sight and kept in a small LRU cache."""
    k = _key(t, season)
    s = _SPR.get(k)
    if s is not None and s["tree"] is t:
        _SPR.move_to_end(k)
        return s
    s = paint_tree(t, season)
    s["tree"] = t
    _SPR[k] = s
    while len(_SPR) > SPR_CAP:
        _SPR.popitem(last=False)
    return s


def _branch(rng, x, y, ang, ln, wd, depth, out, tips, spread=0.55, droop=0.0):
    """Recursive limbs: (x0, y0, x1, y1, w0, w1)."""
    ex = x + math.sin(ang) * ln
    ey = y - math.cos(ang) * ln + droop * ln * 0.3
    w1 = max(0.8, wd * 0.62)
    out.append((x, y, ex, ey, wd, w1))
    if depth <= 0 or ln < 6:
        tips.append((ex, ey))
        return
    n = 2 if rng.random() < 0.75 else 3
    for i in range(n):
        a = ang + (i - (n - 1) / 2) * spread * rng.uniform(0.7, 1.3) + rng.uniform(-0.15, 0.15)
        _branch(rng, ex, ey, a, ln * rng.uniform(0.58, 0.78), w1, depth - 1, out, tips, spread, droop)


def paint_tree(t, season):
    rng = random.Random(t.seed * 7 + 3)
    H, tw = t.h, t.tw
    kind = t.kind
    evergreen = kind in EVERGREEN
    winter_bare = season == "winter" and not evergreen
    pal = season_palette(kind, season)
    if t.burn > 0:
        pal = [(46, 34, 28), (70, 44, 30), (96, 58, 34)]
    bark = BARK.get(kind, BARK["oak"])
    if t.burn > 0:
        bark = (40, 32, 28)
    # sprite box in local coordinates (x right, y up negative), with a margin
    if evergreen:
        hw = H * (0.34 if kind == "fir" else 0.42) + 12
    elif kind == "dead":
        hw = H * 0.4 + 10
    else:
        hw = H * SHAPE.get(kind, SHAPE["oak"])[0] * 1.35 + 14
    top = H * 1.08 + 16
    W = int(hw * 2)
    Ht = int(top + 14)
    ox, oy = W / 2, top                      # local (0, 0) = trunk base -> sprite (ox, oy)

    def L(x, y):
        return ((ox + x) * SS, (oy + y) * SS)

    S = SS
    wood = pygame.Surface((W * S, Ht * S), pygame.SRCALPHA)
    back = pygame.Surface((W * S, Ht * S), pygame.SRCALPHA)
    front = pygame.Surface((W * S, Ht * S), pygame.SRCALPHA)
    # ------------------------------------------------------------ trunk with root flare
    bend = rng.uniform(-0.05, 0.05) * H
    if evergreen:
        trunk_top = H * (0.98 if kind == "fir" else 0.9)
    elif kind == "dead":
        trunk_top = H * 0.82
    else:
        trunk_top = H * rng.uniform(0.46, 0.56)
    n = 9
    left, right = [], []
    for i in range(n + 1):
        u = i / n
        y = -trunk_top * u
        x = bend * u * u
        w = tw * (0.5 - 0.32 * u) if not evergreen else tw * (0.5 - 0.44 * u)
        if u < 0.12:
            w += tw * 0.45 * (1 - u / 0.12) ** 2           # roots flare into the ground
        left.append((x - w, y))
        right.append((x + w, y))
    poly = [L(*p) for p in left] + [L(*p) for p in right[::-1]]
    dark_b = warm(bark, -0.35)
    pygame.draw.polygon(wood, paint.shade(bark, 0.5), poly)
    pygame.draw.polygon(wood, paint.shade(bark, 0.86), [L(x + 0.6, y) for x, y in left] +
                        [L(x - 0.6, y) for x, y in right[::-1]])
    # lit left half, shadowed right edge
    mid = [((a[0] + b[0]) / 2, a[1]) for a, b in zip(left, right)]
    pygame.draw.polygon(wood, warm(bark, 0.12) if kind != "birch" else bark,
                        [L(*p) for p in left] + [L(x - tw * 0.05, y) for x, y in mid[::-1]])
    pygame.draw.polygon(wood, dark_b, [L(x - (x - m[0]) * 0.35, y) for (x, y), m in zip(right, mid)] +
                        [L(x - 0.3, y) for x, y in right[::-1]])
    paint.bark_strokes(wood, poly, bark, rng, kind)
    # roots dipping into the soil
    for side in (-1, 1):
        rx = side * tw * 0.7
        pygame.draw.polygon(wood, paint.shade(bark, 0.7), [L(side * tw * 0.3, -3), L(rx + side * tw * 0.5, 1.5),
                                                           L(rx, 2.5), L(side * tw * 0.2, 1)])
    # ------------------------------------------------------------ conifers
    if kind == "fir" or (kind == "pine" and t.seed % 3 == 0):
        tiers = rng.randint(7, 9) if kind == "fir" else rng.randint(5, 7)
        snow = season == "winter"
        lower = pygame.Surface((W * S, Ht * S), pygame.SRCALPHA)
        npal = [pal[0], paint.shade(pal[1], 1.12), warm(paint.shade(pal[2], 1.3), 0.12)]
        for i in range(tiers):
            f = i / tiers
            yb = -H * (0.16 + 0.8 * f)
            wdt = H * (0.30 if kind == "fir" else 0.22) * (1 - f * 0.85) * rng.uniform(0.88, 1.1)
            ht = H * (0.2 if kind == "fir" else 0.18) * (1 - f * 0.25)
            sag = ht * 0.4
            sk = rng.uniform(-2, 2)
            apex = L(sk * 0.3, yb - ht)
            tl = L(-wdt + sk, yb + rng.uniform(-1, 2))
            tr = L(wdt + sk, yb + rng.uniform(-1, 2))
            tgt = lower if i < tiers // 2 else front
            k = 0.8 + 0.25 * f
            tp = [paint.shade(c, k) for c in npal]
            paint.paint_needles(tgt, (apex, tl, tr, sag * S), tp, rng, snow)
        for tgt in (lower, front):
            soft = pygame.transform.gaussian_blur(tgt, 1)
            tgt.fill((0, 0, 0, 0))
            tgt.blit(soft, (0, 0))
        return _finish(wood, [(lower, 0.6), (front, 1.0)], ox, oy, W, Ht, back_first=False)
    if kind == "pine":
        # a Scots pine: a tall bare trunk, foxy-red above, and flat clouds of needles at the top
        limbs, tips = [], []
        fork = (bend, -trunk_top * 0.62)
        for i in range(rng.randint(4, 6)):
            y0 = -H * rng.uniform(0.58, 0.85)
            side = -1 if i % 2 == 0 else 1
            _branch(rng, bend * (y0 / -trunk_top) ** 2, y0, side * rng.uniform(0.7, 1.3), H * rng.uniform(0.08, 0.13),
                    tw * 0.2, 1, limbs, tips, 0.6)
        _draw_limbs(wood, limbs, (150, 86, 56), L)
        npal = [paint.shade(pal[0], 0.95), paint.shade(pal[1], 1.15), warm(paint.shade(pal[2], 1.35), 0.15)]
        clumps = [(x, y - 3, H * rng.uniform(0.1, 0.14)) for x, y in tips]
        clumps += [(bend + rng.uniform(-H * 0.1, H * 0.1), -H * rng.uniform(0.78, 0.96), H * rng.uniform(0.09, 0.12))
                   for _ in range(5)]
        clumps.sort(key=lambda c: c[1], reverse=True)
        cl = [(L(x, y)[0], L(x, y)[1], r * S) for x, y, r in clumps]
        paint.paint_crown(front, cl, npal, rng, leafy=0.9, needles=True, squash=0.55, blur=2)
        if season == "winter":
            for (x, y, r) in cl:
                pygame.draw.ellipse(front, (238, 242, 250), (x - r * 0.7, y - r * 0.75, r * 1.3, r * 0.4))
        return _finish(wood, [(front, 1.0)], ox, oy, W, Ht)
    # ------------------------------------------------------------ dead trees: gnarled limbs only
    limbs, tips = [], []
    if kind == "dead":
        for i in range(rng.randint(3, 5)):
            yy = -H * rng.uniform(0.45, 0.8)
            a = rng.choice((-1, 1)) * rng.uniform(0.5, 1.1)
            _branch(rng, bend * (yy / -trunk_top) ** 2, yy, a, H * rng.uniform(0.14, 0.22), tw * 0.22, 2, limbs, tips,
                    0.7)
        _draw_limbs(wood, limbs, bark, L)
        return _finish(wood, [], ox, oy, W, Ht)
    # ------------------------------------------------------------ broadleaves
    rx_, ry_, cyf, csz, leafy = SHAPE.get(kind, SHAPE["oak"])
    ccx, ccy = bend, -H * cyf
    crx, cry = H * rx_, H * ry_
    fork = (bend, -trunk_top)
    nmain = rng.randint(3, 4) if kind != "birch" else 2
    for i in range(nmain):
        a = (i - (nmain - 1) / 2) * (1.1 if kind == "oak" else 0.7) + rng.uniform(-0.2, 0.2)
        ln = (H - trunk_top) * (0.42 if kind != "birch" else 0.5) * rng.uniform(0.85, 1.15)
        _branch(rng, fork[0], fork[1], a, ln, tw * 0.3, 3 if not winter_bare else 4, limbs, tips,
                0.6 if kind != "birch" else 0.4, droop=0.4 if kind in ("birch", "willow") else 0.0)
    if kind == "birch":
        # birch keeps its leader to the top
        _branch(rng, fork[0], fork[1], 0.0, (H - trunk_top) * 0.7, tw * 0.28, 2, limbs, tips, 0.4, 0.5)
    if not winter_bare:
        # keep the limbs inside the crown: shrink them toward the fork until every tip is within the ellipse
        worst = max([math.hypot((x - ccx) / crx, (y - ccy) / cry) for x, y in tips] + [0.0])
        if worst > 0.92:
            k = 0.92 / worst
            fx, fy = fork

            def sc(x, y):
                # pull toward the crown centre rather than the fork, so the crown stays filled
                return (ccx + (x - ccx) * k, ccy + (y - ccy) * k)
            limbs = [(*((x0, y0) if (x0, y0) == fork else sc(x0, y0)), *sc(x1, y1), w0, w1)
                     for (x0, y0, x1, y1, w0, w1) in limbs]
            tips = [sc(x, y) for x, y in tips]
    _draw_limbs(wood, limbs, bark, L, birch=(kind == "birch"))
    if winter_bare:
        # fine twigs and a dusting of snow on the upper sides
        for (x, y) in tips:
            for _ in range(3):
                a = rng.uniform(-1.2, 1.2)
                ln = rng.uniform(4, 10)
                pygame.draw.line(wood, paint.shade(bark, 0.8), L(x, y), L(x + math.sin(a) * ln, y - math.cos(a) * ln), 1)
        for (x0, y0, x1, y1, w0, w1) in limbs:
            if w0 > 1.5 and rng.random() < 0.7:
                pygame.draw.line(wood, (236, 240, 248), L(x0, y0 - w0 * 0.6), L(x1, y1 - w1 * 0.6), max(1, int(w1 * S * 0.6)))
        return _finish(wood, [], ox, oy, W, Ht)
    # clumps: one at each outer tip, filling the crown's ellipse, plus the body of the crown
    clumps = []
    for (x, y) in tips:
        dx, dy = (x - ccx) / crx, (y - ccy) / cry
        d = math.hypot(dx, dy)
        if d > 1.0:
            x, y = ccx + dx / d * crx * 0.95, ccy + dy / d * cry * 0.95
        clumps.append((x, y, H * csz * rng.uniform(0.32, 0.5)))
    for _ in range(int(8 + 6 * leafy)):
        a = rng.uniform(0, math.tau)
        d = math.sqrt(rng.random()) * 0.75
        clumps.append((ccx + math.cos(a) * crx * d, ccy + math.sin(a) * cry * d, H * csz * rng.uniform(0.4, 0.62)))
    # thin out clumps that sit almost on top of each other
    kept = []
    for c in sorted(clumps, key=lambda c: -c[2]):
        if all(math.hypot(c[0] - k[0], c[1] - k[1]) > (c[2] + k[2]) * 0.38 for k in kept):
            kept.append(c)
    kept.sort(key=lambda c: c[1], reverse=True)          # lowest first, sunlit tops in front
    in_back = [c for c in kept if rng.random() < 0.45]
    in_front = [c for c in kept if c not in in_back]
    bk = [(L(x, y)[0], L(x, y)[1], r * S) for x, y, r in in_back]
    fr = [(L(x, y)[0], L(x, y)[1], r * S) for x, y, r in in_front]
    bpal = [warm(paint.shade(c, 0.86), -0.06) for c in pal]
    paint.paint_crown(back, bk, bpal, rng, leafy=leafy, ao=0.06, blur=3)
    paint.paint_crown(front, fr, pal, rng, leafy=leafy, blur=2)
    if kind == "willow":
        # curtains of hanging twigs, dense, swaying with the front of the crown
        for _ in range(60):
            sx = ccx + rng.uniform(-crx * 1.05, crx * 1.05)
            sy = ccy + rng.uniform(-cry * 0.1, cry * 0.7) - abs(sx - ccx) / crx * cry * 0.3
            ln = rng.uniform(H * 0.22, H * 0.42)
            col = jitter(pal[rng.choice((0, 1, 1, 2))], rng, 8)
            bow = rng.uniform(-3, 3)
            pts = [L(sx + bow * (k / 8) ** 2, sy + ln * k / 8) for k in range(9)]
            pygame.draw.lines(front, paint.shade(col, 0.8), False, pts, S)
            for k in range(1, 9):
                for side in (-1, 1):
                    paint.leaf(front, col, pts[k][0], pts[k][1] - 2, 3.2 * S,
                               math.pi / 2 + side * rng.uniform(0.15, 0.6), 0.3)
    return _finish(wood, [(back, 0.75), (front, 1.0)], ox, oy, W, Ht)


def _draw_limbs(surf, limbs, bark, L, birch=False):
    for (x0, y0, x1, y1, w0, w1) in sorted(limbs, key=lambda l: -l[4]):
        a, b = L(x0, y0), L(x1, y1)
        col = bark if not birch or w0 < 1.6 else (222, 218, 206)
        if birch and w0 < 1.6:
            col = (70, 54, 46)
        paint.soft_limb(surf, a, b, w0 * SS * 0.5, w1 * SS * 0.5, col, edge=0.6 * SS if w0 > 2 else 0,
                        lit=w0 > 2)


def _finish(wood, layers, ox, oy, W, Ht, back_first=True):
    out = {"wood": paint.shrink(wood), "layers": [], "origin": (ox, oy), "size": (W, Ht)}
    for surf, k in layers:
        out["layers"].append((paint.shrink(surf), k))
    out["back_first"] = back_first
    return out


def draw_tree(surf, t, ox, oy, time, wind, season, light=1.0, zoom=1.0):
    bx, by = t.x - ox, t.y - oy
    H = t.h
    if t.state == "stump":
        _draw_stump(surf, t, bx, by)
        return
    sp = sprites(t, season)
    sway_amp = (1.5 + abs(wind) * 4.0) * (H / 120.0)
    ph = time * (1.3 + abs(wind) * 0.6) + t.seed * 0.37
    sway = math.sin(ph) * sway_amp * 0.6 + wind * 3.0 * (H / 120) + t.shake * math.sin(time * 40) * 3
    rustle = math.sin(time * 2.7 + t.seed) * (0.6 + abs(wind)) * (H / 160)
    o0, o1 = sp["origin"]
    W, Ht = sp["size"]
    paint.contact_shadow(surf, bx, by + 1, max(t.tw * 4, W * 0.55), 70)
    x0, y0 = bx - o0 + t.lean * 0, by - o1
    layers = sp["layers"]
    if sp["back_first"] and layers:
        surf.blit(layers[0][0], (x0 + sway * layers[0][1], y0))
        rest = layers[1:]
    else:
        rest = layers
    surf.blit(sp["wood"], (x0 + sway * 0.15, y0))
    for i, (img, k) in enumerate(rest):
        surf.blit(img, (x0 + sway * k + rustle * (1 if i == len(rest) - 1 else 0), y0 + abs(rustle) * 0.3))


def crown_sprite(t, season):
    """The whole tree (wood and crown) as one sprite, for a falling trunk; origin = trunk base."""
    sp = sprites(t, season)
    s = sp.get("_whole")
    if s is None:
        W, Ht = sp["size"]
        s = pygame.Surface((W, Ht), pygame.SRCALPHA)
        layers = sp["layers"]
        if sp["back_first"] and layers:
            s.blit(layers[0][0], (0, 0))
            layers = layers[1:]
        s.blit(sp["wood"], (0, 0))
        for img, k in layers:
            s.blit(img, (0, 0))
        sp["_whole"] = s
    return s, sp["origin"]


def _draw_stump(surf, t, bx, by):
    tw = t.tw
    bark = BARK.get(t.kind, BARK["oak"])
    paint.contact_shadow(surf, bx, by + 1, tw * 2.6, 60)
    body = [(bx - tw / 2 - 2, by + 1), (bx - tw / 2, by - 8), (bx + tw / 2, by - 10), (bx + tw / 2 + 2, by + 1)]
    pygame.draw.polygon(surf, paint.shade(bark, 0.55), body)
    pygame.draw.polygon(surf, bark, [(bx - tw / 2 - 1, by), (bx - tw / 2 + 1, by - 8), (bx, by - 9), (bx, by)])
    top = pygame.Rect(0, 0, tw + 1, 5)
    top.center = (bx, by - 9)
    pygame.draw.ellipse(surf, (206, 172, 120), top)
    pygame.draw.ellipse(surf, (170, 132, 86), top, 1)
    pygame.draw.ellipse(surf, (176, 140, 92), top.inflate(-tw * 0.5, -2), 1)
    if t.regrow > 0.3:
        s = (t.regrow - 0.3) * 30
        pygame.draw.line(surf, (70, 120, 50), (bx + tw / 2 + 3, by), (bx + tw / 2 + 5, by - s), 2)
        rng = random.Random(t.seed)
        for i in range(max(2, int(s / 3))):
            paint.leaf(surf, (90, 146, 60) if i % 2 else (70, 124, 52), bx + tw / 2 + 5, by - s * (0.4 + 0.6 * i / max(1, s / 3)),
                       5, -math.pi / 2 + rng.uniform(-1.2, 1.2))
