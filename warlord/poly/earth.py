"""Loose earth: what a shovel throws, a pick breaks loose or a shot tears out of the ground.

Digging takes an irregular bite out of the solid terrain and throws the earth out as clods: small rigid bodies
that tumble, roll, pile up beside the hole and can be walked on. Digging into loose clods scoops them into the
bag; emptying earth from the bag drops clods that fall and settle. Loose earth is only temporary: when you move
away (about a screen and a half), or before a save, the clods set into solid ground again — they fill the
holes they lie in and raise the surface where they are heaped, keeping the amount of earth.
"""
import math
import random

import pymunk

from .world import CAT_TERRAIN, CAT_STRUCT, CAT_OBJECT, CAT_CHAR, CAT_PLATFORM, CHUNK_PX
from ..settings import TILE

CAT_EARTH = 64
F_EARTH = pymunk.ShapeFilter(categories=CAT_EARTH,
                             mask=CAT_TERRAIN | CAT_STRUCT | CAT_OBJECT | CAT_CHAR | CAT_PLATFORM | CAT_EARTH)
SOIL_COLS = [(112, 80, 54), (124, 90, 60), (102, 72, 50), (132, 98, 66)]
ROCK_COLS = [(128, 122, 116), (112, 106, 100), (142, 136, 128)]
SAND_COLS = [(200, 180, 128), (186, 166, 116), (210, 192, 140)]


class Grain:
    __slots__ = ("body", "shape", "r", "col", "kind", "age")


class LooseEarth:
    MAX = 360               # loose clods at once; past this the oldest, farthest ones set first
    RANGE = 1500            # clods farther than this from you set into the ground

    def __init__(self, world):
        self.w = world
        self.grains = []
        self.rng = random.Random(5)
        self._t = 0.0

    # ------------------------------------------------------------------ making and taking clods
    def spawn(self, x, y, area, kind="soil", throw=0.0, spread=8.0, lift=1.0):
        """Throw `area` worth of earth out as clods around (x, y); throw = sideways direction (-1..1)."""
        rng = self.rng
        cols = ROCK_COLS if kind == "rock" else SAND_COLS if kind == "sand" else SOIL_COLS
        made = 0.0
        out = []
        while made < area * 0.8 and len(out) < 16:
            r = rng.uniform(2.2, 4.8) if kind != "rock" else rng.uniform(2.2, 4.0)
            g = self._make(x + rng.uniform(-spread, spread), y + rng.uniform(-spread, spread * 0.5), r,
                           rng.choice(cols), kind)
            g.body.velocity = (throw * rng.uniform(60, 150) + rng.uniform(-30, 30), -rng.uniform(70, 170) * lift)
            g.body.angular_velocity = rng.uniform(-6, 6)
            made += math.pi * r * r
            out.append(g)
        self.grains.extend(out)
        return out

    def _make(self, x, y, r, col, kind):
        g = Grain()
        mass = math.pi * r * r * 0.03
        body = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, r))
        body.position = (x, y)
        if kind == "rock":
            # broken rock is angular
            pts = [(math.cos(a) * r * self.rng.uniform(0.8, 1.15), math.sin(a) * r * self.rng.uniform(0.8, 1.15))
                   for a in [i * math.tau / 5 + self.rng.uniform(-0.2, 0.2) for i in range(5)]]
            shape = pymunk.Poly(body, pts)
        else:
            shape = pymunk.Circle(body, r)
        shape.friction = 1.1
        shape.elasticity = 0.0
        shape.filter = F_EARTH
        shape.earth = g
        self.w.space.add(body, shape)
        g.body, g.shape, g.r, g.col, g.kind, g.age = body, shape, r, col, kind, 0.0
        return g

    def take(self, x, y, r):
        """Scoop up the loose clods near (x, y); returns the earth's area and its kind."""
        got, kinds = 0.0, {}
        keep = []
        for g in self.grains:
            px, py = g.body.position
            if (px - x) ** 2 + (py - y) ** 2 < (r + g.r) ** 2:
                a = math.pi * g.r * g.r / 0.8
                got += a
                kinds[g.kind] = kinds.get(g.kind, 0) + a
                self._remove(g)
            else:
                keep.append(g)
        self.grains = keep
        kind = max(kinds, key=kinds.get) if kinds else "soil"
        return got, kind

    def near(self, x, y, r):
        return any((g.body.position.x - x) ** 2 + (g.body.position.y - y) ** 2 < (r + g.r) ** 2 for g in self.grains)

    def _remove(self, g):
        try:
            self.w.space.remove(g.body, g.shape)
        except Exception:
            pass

    # ------------------------------------------------------------------ setting into the ground
    def update(self, dt, focus_x):
        self._t -= dt
        for g in self.grains:
            g.age += dt
        if self._t > 0:
            return
        self._t = 0.5
        far, keep = [], []
        bottom = self.w.pixel_h() + 200
        for g in self.grains:
            x, y = g.body.position
            if y > bottom:
                self._remove(g)          # fell into the Abyss
            elif abs(x - focus_x) > self.RANGE:
                far.append(g)
            else:
                keep.append(g)
        if len(keep) > self.MAX:
            # too many loose clods: the oldest settled ones set first
            keep.sort(key=lambda g: (g.body.velocity.length > 20, -g.age))
            far += keep[:len(keep) - self.MAX + 40]
            keep = keep[len(keep) - self.MAX + 40:]
        self.grains = keep
        if far:
            self.solidify(far)

    def solidify_all(self):
        gs, self.grains = self.grains, []
        if gs:
            self.solidify(gs)

    def solidify(self, grains):
        """Clods become ground: fill the hollows they lie in, raise the surface where they are heaped."""
        from shapely.geometry import Point, box
        from shapely.ops import unary_union
        w = self.w
        blobs = []
        for g in grains:
            x, y = g.body.position
            blobs.append(Point(x, y).buffer(g.r * 1.2, quad_segs=3))
            self._remove(g)
        if not blobs:
            return
        # packed clods leave no gaps once they set: close the spaces between them
        geom = unary_union(blobs).buffer(4.0, quad_segs=3).buffer(-4.0, quad_segs=3)
        if geom.is_empty:
            return
        snug = geom.buffer(3.5, quad_segs=3)        # in a hole, earth presses out to the walls
        x0, y0, x1, y1 = geom.bounds
        touched = set(range(int(x0 // CHUNK_PX), int(x1 // CHUNK_PX) + 1))
        # 1. into holes you dug and into natural hollows
        d = getattr(w, "dug", None) or {}
        for cx in touched:
            g = d.get(cx)
            if g is not None and not g.is_empty:
                d[cx] = g.difference(snug)
        for ci, cave in enumerate(w.caves):
            b = w.cave_bounds[ci]
            if b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1:
                continue
            nc = cave.difference(snug)
            w.caves[ci] = nc
            if not nc.is_empty:
                w.cave_bounds[ci] = nc.bounds
        # 2. heaps on the surface raise it, column by column, keeping the amount of earth
        i0 = max(0, int(x0 // TILE) - 1)
        i1 = min(w.w, int(x1 // TILE) + 2)
        raise_ = []
        for i in range(i0, i1 + 1):
            x = i * TILE
            top = float(w.top[i])
            cell = box(x - TILE / 2, top - 400, x + TILE / 2, top + 1)
            a = geom.intersection(cell).area
            if a > 1.0:
                raise_.append((i, a / TILE))
        for i, h in raise_:
            w.top[i] -= h
        for cx in touched | {int((i * TILE) // CHUNK_PX) for i, _ in raise_}:
            w._invalidate(cx)

    # ------------------------------------------------------------------ drawing
    def draw(self, surf, ox, oy):
        import pygame
        W, H = surf.get_size()
        for g in self.grains:
            x, y = g.body.position
            sx, sy = x - ox, y - oy
            if -10 < sx < W + 10 and -10 < sy < H + 10:
                c = g.col
                dark = (c[0] * 6 // 10, c[1] * 6 // 10, c[2] * 6 // 10)
                lite = (min(255, c[0] + 26), min(255, c[1] + 22), min(255, c[2] + 16))
                if g.kind == "rock":
                    pts = [g.body.local_to_world(v) for v in g.shape.get_vertices()]
                    pts = [(px - ox, py - oy) for px, py in pts]
                    pygame.draw.polygon(surf, c, pts)
                    pygame.draw.polygon(surf, dark, pts, 1)
                    pygame.draw.line(surf, lite, pts[0], pts[1], 1)
                else:
                    pygame.draw.circle(surf, dark, (sx, sy), g.r)
                    pygame.draw.circle(surf, c, (sx - 0.4, sy - 0.5), g.r - 0.7)
                    pygame.draw.circle(surf, lite, (sx - g.r * 0.35, sy - g.r * 0.4), max(1.0, g.r * 0.35))
