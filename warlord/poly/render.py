"""Renderer for the polygon world.

Terrain is drawn in faceted low-poly bands (turf, soil, rock strata) into cached 512 px tiles; cave passages
are cut into it as dark hollows with lit rims. Buildings are drawn piece by piece with material detailing
(timber frames, brick courses, ashlar joints, thatch, slates, boards) into per-building caches that are
rebuilt only when a piece changes. Water is a translucent body with moving waves; light is a coarse grid
of sunlight by depth and warm point lights, multiplied over the scene.
"""
import math
import random
from collections import OrderedDict

import numpy as np
import pygame

from ..settings import TILE, SEA_LEVEL
from ..gfx.renderer import Renderer as SkyRenderer, Camera, lerp_col  # noqa: F401  (sky, parallax, camera)
from .materials import MATS
from .world import CHUNK_PX
from . import flora

TILE_PX = 512


def shade(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def hsh(*a):
    h = 2166136261
    for v in a:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return h


def hf(*a):
    return (hsh(*a) % 10000) / 10000.0


TOP = {"abyss": (120, 110, 84), "edge": (150, 140, 90), "plains": (96, 150, 62), "forest": (70, 124, 54),
       "moor": (98, 96, 58), "hills": (104, 148, 66), "mountains": (112, 136, 80), "vineyard": (112, 150, 64),
       "coast": (196, 184, 132), "ocean": (194, 180, 130), "islet": (204, 190, 136), "snow": (236, 240, 246),
       "ashland": (124, 118, 112), "volcanic": (82, 76, 76), "lavasea": (60, 56, 58)}
SOIL = {"abyss": (100, 84, 66), "edge": (112, 88, 64), "plains": (118, 86, 58), "forest": (104, 76, 52),
        "moor": (86, 70, 52), "hills": (122, 92, 62), "mountains": (118, 98, 76), "vineyard": (150, 98, 70),
        "coast": (196, 176, 122), "ocean": (186, 166, 116), "islet": (198, 180, 126), "snow": (116, 92, 70),
        "ashland": (166, 140, 106), "volcanic": (70, 64, 66), "lavasea": (58, 52, 54)}
ROCK = {"abyss": (110, 102, 98), "ashland": (150, 128, 100), "volcanic": (64, 60, 66), "lavasea": (54, 50, 56)}
ROCK_DEFAULT = (118, 114, 110)
SEASON_TOP = {"herbst": {"plains": (150, 146, 66), "forest": (124, 120, 56), "hills": (140, 140, 70)},
              "fruehling": {"plains": (110, 170, 70), "forest": (86, 146, 60), "hills": (118, 168, 74)}}
ORE = {"coal": (34, 32, 34), "iron": (160, 98, 74), "silver": (210, 214, 224), "gold": (236, 196, 70),
       "salt": (236, 232, 226), "glutstein": (255, 120, 50), "stone": (150, 146, 140)}
CROP_COL = {"wheat": (214, 186, 92), "rye": (190, 170, 104), "oat": (204, 196, 130), "flax": (110, 140, 200),
            "turnip": (90, 140, 70), "barley": (210, 190, 110)}


def soil_depth(x, bio):
    if bio in ("ocean", "coast", "islet"):
        return 30
    return 70 + 26 * math.sin(x * 0.0061) + 14 * math.sin(x * 0.023 + 1.3) + 6 * math.sin(x * 0.071)


class PolyRenderer(SkyRenderer):
    def __init__(self, world):
        self.world = world
        self.terrain = OrderedDict()
        self.liquid = {}
        self.max_chunks = 160
        self._build_parallax()
        self.stars = [(random.random(), random.random() * 0.6, random.random()) for _ in range(140)]
        self.clouds = [[random.uniform(0, 4000), random.uniform(20, 240), random.uniform(80, 220),
                        random.uniform(0.6, 1.0)] for _ in range(14)]
        self.light_cache = None
        self.storm = 0.0
        self.season = "sommer"
        self.bcache = OrderedDict()
        self._overlay = None
        self._chunk_full = {}
        self.time = 0.0
        self.wind = 0.0

    # ------------------------------------------------------------------ caches
    def set_season(self, season):
        s = {"Frühling": "fruehling", "Sommer": "sommer", "Herbst": "herbst", "Winter": "winter"}.get(season, season)
        s = {"spring": "fruehling", "summer": "sommer", "autumn": "herbst"}.get(s, s)
        if s != self.season:
            self.season = s
            self.terrain.clear()

    def invalidate(self):
        w = self.world
        if w.dirty:
            for key in list(self.terrain):
                if key[0] in w.dirty or key[0] - 1 in w.dirty or key[0] + 1 in w.dirty:
                    self.terrain.pop(key, None)
            for c in w.dirty:
                self._chunk_full.pop(c, None)
            w.dirty.clear()

    def biome(self, px):
        return self.world.biome_at(int(px // TILE))

    def top_col(self, b, px):
        if self.season == "winter" and b in ("plains", "forest", "hills", "mountains", "vineyard", "moor", "edge"):
            return (232, 236, 242)
        st = SEASON_TOP.get(self.season, {})
        return st.get(b, TOP.get(b, TOP["plains"]))

    # ------------------------------------------------------------------ terrain tiles
    def _render_tile(self, tx, ty):
        w = self.world
        X, Y = tx * TILE_PX, ty * TILE_PX
        i0 = max(0, int(X // TILE) - 1)
        i1 = min(w.w, int((X + TILE_PX) // TILE) + 2)
        if i1 <= i0:
            return None
        top = w.top[i0:i1 + 1]
        bot = w.bottom[i0:i1 + 1]
        if float(top.min()) > Y + TILE_PX + 2 or float(bot.max()) < Y - 2:
            return None
        surf = pygame.Surface((TILE_PX, TILE_PX), pygame.SRCALPHA)
        xs = [i * TILE - X for i in range(i0, i1 + 1)]
        ts = [float(t) - Y for t in top]
        bs = [float(b) - Y for b in bot]
        n = len(xs)
        # split into runs where the crust exists
        runs, run = [], []
        for k in range(n):
            if bs[k] - ts[k] > 2:
                run.append(k)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        for r in runs:
            if len(r) < 2:
                continue
            for a, b in zip(r, r[1:]):
                px = (xs[a] + xs[b]) / 2 + X
                bio = self.biome(px)
                rock = ROCK.get(bio, ROCK_DEFAULT)
                soil = SOIL.get(bio, SOIL["plains"])
                topc = self.top_col(bio, px)
                xa, xb = xs[a], xs[b]
                ta, tb = ts[a], ts[b]
                ba, bb = bs[a], bs[b]
                sd_a = soil_depth((a + i0) * TILE, bio)
                sd_b = soil_depth((b + i0) * TILE, bio)
                # rock column
                pygame.draw.polygon(surf, rock, [(xa, ta), (xb, tb), (xb, bb), (xa, ba)])
                # soil band (faceted: two triangles per column with slightly different shades)
                sa, sb = min(ba, ta + sd_a), min(bb, tb + sd_b)
                f1 = 0.94 + hf(a + i0, 7) * 0.1
                pygame.draw.polygon(surf, shade(soil, f1), [(xa, ta), (xb, tb), (xb, sb)])
                pygame.draw.polygon(surf, shade(soil, f1 * 0.94), [(xa, ta), (xb, sb), (xa, sa)])
                # turf
                gd = 7 if bio != "snow" else 9
                pygame.draw.polygon(surf, topc, [(xa, ta), (xb, tb), (xb, tb + gd), (xa, ta + gd)])
                pygame.draw.line(surf, shade(topc, 1.15), (xa, ta), (xb, tb), 2)
                pygame.draw.line(surf, shade(topc, 0.78), (xa, ta + gd), (xb, tb + gd), 1)
                # pebbles in the soil
                if hf(a + i0, 11) < 0.35:
                    px_ = xa + hf(a + i0, 12) * 16
                    py_ = ta + 14 + hf(a + i0, 13) * (sd_a - 18)
                    pygame.draw.ellipse(surf, shade(rock, 0.95), (px_, py_, 5, 3))
            # crust underside seen from the void
            under = [(xs[k], bs[k]) for k in r]
            if len(under) > 1:
                pygame.draw.lines(surf, (40, 32, 30), False, under, 3)
        # rock facets and strata (a jittered triangle mesh, a few shades)
        step = 48
        gx0 = int(X // step) - 1
        gy0 = int(Y // step) - 1
        pts = {}
        for gi in range(gx0, gx0 + TILE_PX // step + 3):
            for gj in range(gy0, gy0 + TILE_PX // step + 3):
                pts[gi, gj] = (gi * step + (hf(gi, gj, 1) - 0.5) * 30 - X, gj * step + (hf(gi, gj, 2) - 0.5) * 30 - Y)
        for gi in range(gx0, gx0 + TILE_PX // step + 2):
            for gj in range(gy0, gy0 + TILE_PX // step + 2):
                a, b, c, d = pts[gi, gj], pts[gi + 1, gj], pts[gi + 1, gj + 1], pts[gi, gj + 1]
                for tri, k in (((a, b, c), 0), ((a, c, d), 1)):
                    ok = True
                    for (vx, vy) in tri:
                        col = int((vx + X) // TILE)
                        if not (0 <= col < w.w) or vy + Y < w.top[col] + 90 or vy + Y > w.bottom[col] - 4:
                            ok = False
                            break
                    if not ok:
                        continue
                    bio = self.biome(tri[0][0] + X)
                    rock = ROCK.get(bio, ROCK_DEFAULT)
                    depth = (tri[0][1] + Y - w.top[int((tri[0][0] + X) // TILE)]) / 800.0
                    f = (0.88 + hf(gi, gj, k, 5) * 0.16) * (1.0 - min(0.25, depth * 0.12))
                    pygame.draw.polygon(surf, shade(rock, f), tri)
        # cave hollows
        self._draw_caves(surf, tx, ty)
        return surf

    def _cave_bg(self, cx):
        """The cave interiors within one x-chunk: ground-without-caves minus ground-with-caves."""
        g = self._chunk_full.get(cx, False)
        if g is not False:
            return g
        w = self.world
        ids = w.cave_chunks.get(cx, ())
        if not ids:
            self._chunk_full[cx] = None
            return None
        from shapely.ops import unary_union
        from shapely.geometry import box
        x0 = cx * CHUNK_PX
        clip = box(x0 - 1, -10000, x0 + CHUNK_PX + 1, 100000)
        caves = unary_union([w.caves[i] for i in ids]).intersection(clip)
        # only the part that is underground
        i0 = max(0, int(x0 // TILE))
        i1 = min(w.w, int((x0 + CHUNK_PX) // TILE) + 1)
        from shapely.geometry import Polygon
        pts = [(i * TILE, float(w.top[i])) for i in range(i0, i1 + 1)] + \
              [(i * TILE, float(w.bottom[i])) for i in range(i1, i0 - 1, -1)]
        try:
            ground = Polygon(pts).buffer(0)
            g = caves.intersection(ground)
        except Exception:
            g = None
        self._chunk_full[cx] = g
        return g

    def _draw_caves(self, surf, tx, ty):
        X, Y = tx * TILE_PX, ty * TILE_PX
        for cx in range(int(X // CHUNK_PX), int((X + TILE_PX) // CHUNK_PX) + 1):
            g = self._cave_bg(cx)
            if g is None or g.is_empty:
                continue
            geoms = getattr(g, "geoms", [g])
            for p in geoms:
                if p.geom_type != "Polygon":
                    continue
                bx0, by0, bx1, by1 = p.bounds
                if bx1 < X or bx0 > X + TILE_PX or by1 < Y or by0 > Y + TILE_PX:
                    continue
                bio = self.biome((bx0 + bx1) / 2)
                rock = ROCK.get(bio, ROCK_DEFAULT)
                back = shade(rock, 0.36)
                ext = [(x - X, y - Y) for x, y in p.exterior.coords]
                if len(ext) >= 3:
                    pygame.draw.polygon(surf, back, ext)
                    # a lit rim where the rock wall meets the hollow
                    pygame.draw.lines(surf, shade(rock, 0.72), True, ext, 5)
                    pygame.draw.lines(surf, shade(rock, 0.95), True, ext, 2)
                for hole in p.interiors:
                    hp = [(x - X, y - Y) for x, y in hole.coords]
                    if len(hp) >= 3:
                        pygame.draw.polygon(surf, rock, hp)
                        pygame.draw.lines(surf, shade(rock, 0.95), True, hp, 2)
                # back-wall texture: a few dim facets
                rng = random.Random(int(bx0 * 7 + by0))
                for _ in range(int((bx1 - bx0) * (by1 - by0) / 6000) + 1):
                    qx = rng.uniform(bx0, bx1)
                    qy = rng.uniform(by0, by1)
                    from shapely import contains_xy
                    if contains_xy(p, qx, qy):
                        r = rng.uniform(8, 22)
                        tri = [(qx - X, qy - Y), (qx + r - X, qy + r * 0.4 - Y), (qx + r * 0.2 - X, qy + r - Y)]
                        pygame.draw.polygon(surf, shade(rock, 0.42 + rng.random() * 0.06), tri)

    def get_tile(self, tx, ty):
        key = (tx, ty)
        t = self.terrain.get(key, False)
        if t is False:
            t = self._render_tile(tx, ty)
            self.terrain[key] = t
            while len(self.terrain) > self.max_chunks:
                self.terrain.popitem(last=False)
        else:
            self.terrain.move_to_end(key)
        return t

    def draw_terrain(self, surf, cam):
        SW, SH = surf.get_size()
        self.invalidate()
        ox, oy = cam.offset()
        for ty in range(int(oy // TILE_PX), int((oy + SH) // TILE_PX) + 1):
            for tx in range(int(ox // TILE_PX), int((ox + SW) // TILE_PX) + 1):
                t = self.get_tile(tx, ty)
                if t is not None:
                    surf.blit(t, (tx * TILE_PX - ox, ty * TILE_PX - oy))
        w = self.world
        # floating stones
        for pts in w.rocks:
            if ox - 300 < pts[0][0] < ox + SW + 300:
                sp = [(x - ox, y - oy) for x, y in pts]
                if -100 < sp[0][1] < SH + 100:
                    pygame.draw.polygon(surf, (112, 104, 100), sp)
                    pygame.draw.polygon(surf, (136, 128, 120), [sp[0], sp[1], sp[2], sp[3]])
                    pygame.draw.lines(surf, (150, 140, 96), False, sp[:4], 3)
                    pygame.draw.polygon(surf, (70, 64, 62), sp, 1)
        # ore veins in the cave walls
        t = self.time
        for o in w.ores:
            if o["left"] <= 0:
                continue
            x, y = o["x"] - ox, o["y"] - oy
            if -20 < x < SW + 20 and -20 < y < SH + 20:
                col = ORE.get(o["kind"], (150, 140, 130))
                rng = random.Random(int(o["x"]))
                for k in range(3 + o["left"] // 2):
                    a = rng.uniform(0, math.tau)
                    r = rng.uniform(2, 9)
                    s = rng.uniform(2.5, 4.5)
                    px, py = x + math.cos(a) * r, y + math.sin(a) * r * 0.6
                    tri = [(px, py - s), (px + s, py), (px, py + s * 0.8), (px - s, py)]
                    c = col if o["kind"] != "glutstein" else shade(col, 0.8 + 0.2 * math.sin(t * 3 + k))
                    pygame.draw.polygon(surf, c, tri)
                    pygame.draw.line(surf, shade(c, 1.3), tri[0], tri[1], 1)

    # ------------------------------------------------------------------ ground cover (live, sways)
    def draw_grass(self, surf, cam, time, wind):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        w = self.world
        x = int(ox // 6) * 6
        while x < ox + SW:
            col = int(x // TILE)
            if 0 <= col < w.w:
                bio = w.biome_at(col)
                if bio in ("plains", "forest", "hills", "vineyard", "moor", "mountains", "coast", "edge") and \
                        self.season != "winter":
                    y = w.surface_y(x) - oy
                    if -30 < y < SH + 10 and w.water_level(x) is None and w.settlement_at(col) is None:
                        hh = 4 + hf(x, 17) * (9 if bio in ("plains", "moor", "hills") else 6)
                        c = shade(self.top_col(bio, x), 0.85 + hf(x, 18) * 0.35)
                        sw = math.sin(time * 2.0 + x * 0.05) * (1.0 + abs(wind) * 2.5) + wind * 2
                        pygame.draw.line(surf, c, (x - ox, y + 2), (x - ox + sw, y - hh), 1)
                        if hf(x, 19) < 0.5:
                            pygame.draw.line(surf, shade(c, 0.9), (x - ox + 2, y + 2), (x - ox + 3 + sw * 0.8,
                                                                                         y - hh * 0.7), 1)
            x += 6

    # ------------------------------------------------------------------ water
    def draw_water(self, surf, cam, time):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        w = self.world
        if self._overlay is None or self._overlay.get_size() != (SW, SH):
            self._overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        ov = self._overlay
        ov.fill((0, 0, 0, 0))
        drew = False
        storm = self.storm
        for wr in w.water:
            if wr.x1 < ox or wr.x0 > ox + SW:
                continue
            ly = wr.level - oy
            if ly > SH + 20:
                continue
            x0 = max(wr.x0, ox - 16)
            x1 = min(wr.x1, ox + SW + 16)
            top, bottom = [], []
            x = x0
            while x <= x1 + 15:
                xx = min(x, x1)
                wave = math.sin(time * 2.2 + xx * 0.034) * (1.5 + 5 * storm) + math.sin(time * 1.3 + xx * 0.011) * 5 * \
                    storm if not wr.lava else math.sin(time * 0.8 + xx * 0.02) * 1.5
                top.append((xx - ox, ly + wave))
                bottom.append((xx - ox, max(ly, w.surface_y(xx) - oy + 3)))
                if xx >= x1:
                    break
                x += 16
            if len(top) < 2:
                continue
            poly = top + bottom[::-1]
            if wr.lava:
                pygame.draw.polygon(surf, (214, 84, 30), poly)
                pygame.draw.lines(surf, (255, 200, 90), False, top, 3)
                for k in range(0, len(top) - 1, 3):
                    gx, gy = top[k]
                    pygame.draw.circle(surf, (255, 150, 60), (int(gx), int(gy + 6 + math.sin(time + k) * 3)), 3)
                continue
            drew = True
            pygame.draw.polygon(ov, (44, 96, 136, 128), poly)
            deep = [(x, y + 90) for x, y in top]
            dpoly = []
            for (xa, ya), (xb, yb) in zip(deep, bottom):
                dpoly.append((xa, min(ya, yb)))
            if len(dpoly) > 1:
                pygame.draw.polygon(ov, (20, 50, 84, 90), dpoly + bottom[::-1])
            pygame.draw.lines(ov, (190, 220, 236, 200), False, top, 2)
            # glints
            for k in range(0, len(top) - 1, 2):
                gx, gy = top[k]
                if hf(k + int(time * 2), int(gx)) < 0.25:
                    pygame.draw.line(ov, (236, 246, 250, 160), (gx, gy + 4), (gx + 7, gy + 4), 1)
        if drew:
            surf.blit(ov, (0, 0))

    # ------------------------------------------------------------------ buildings
    def building_surface(self, b):
        key = b.id
        c = self.bcache.get(key)
        if c is not None and c[0] == b.version:
            self.bcache.move_to_end(key)
            return c[1], c[2]
        w = self.world
        pcs = [w.pieces[i] for i in b.pieces if i in w.pieces]
        if not pcs:
            self.bcache[key] = (b.version, None, (0, 0))
            return None, (0, 0)
        x0 = min(p.bb[0] for p in pcs) - 4
        y0 = min(p.bb[1] for p in pcs) - 4
        x1 = max(p.bb[2] for p in pcs) + 4
        y1 = max(p.bb[3] for p in pcs) + 4
        s = pygame.Surface((int(x1 - x0) + 1, int(y1 - y0) + 1), pygame.SRCALPHA)
        order = {"back": 0, "mid": 1}
        for p in sorted(pcs, key=lambda p: (order.get(p.layer, 1), p.role in ("roof", "step"), p.role == "door")):
            pts = [(x - x0, y - y0) for x, y in p.pts]
            draw_piece(s, pts, p.mat, p.detail, p.tint, p.role, p.open, p.hp / max(1, p.max_hp), p.id)
        self.bcache[key] = (b.version, s, (x0, y0))
        while len(self.bcache) > 260:
            self.bcache.popitem(last=False)
        return s, (x0, y0)

    def draw_buildings(self, surf, cam):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        for b in self.world.buildings:
            if b.x1 < ox - 40 or b.x0 > ox + SW + 40:
                continue
            s, (bx, by) = self.building_surface(b)
            if s is not None:
                surf.blit(s, (bx - ox, by - oy))

    def draw_gatehouses(self, surf, cam):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        for gh in self.world.gatehouses:
            if not hasattr(gh, "bridge_points") or not (ox - 300 < gh.hinge[0] < ox + SW + 300):
                continue
            pp = gh.port_points()
            if pp:
                sp = [(x - ox, y - oy) for x, y in pp]
                xs = [p[0] for p in sp]
                ys = [p[1] for p in sp]
                x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
                for x in (x0 + 1, (x0 + x1) / 2, x1 - 1):
                    pygame.draw.line(surf, (60, 62, 68), (x, y0), (x, y1), 2)
                y = y0 + 4
                while y < y1:
                    pygame.draw.line(surf, (74, 76, 84), (x0, y), (x1, y), 2)
                    y += 8
                for x in (x0 + 1, (x0 + x1) / 2, x1 - 1):
                    pygame.draw.polygon(surf, (90, 92, 100), [(x - 2, y1), (x + 2, y1), (x, y1 + 4)])
            bp = gh.bridge_points()
            if bp:
                sp = [(x - ox, y - oy) for x, y in bp]
                pygame.draw.polygon(surf, (128, 92, 58), sp)
                # planks across, iron bands along
                a, b = sp[0], sp[1]
                c, d = sp[3], sp[2]
                n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) // 10))
                for k in range(1, n):
                    t = k / n
                    pygame.draw.line(surf, (92, 64, 40), (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t),
                                     (c[0] + (d[0] - c[0]) * t, c[1] + (d[1] - c[1]) * t), 1)
                pygame.draw.polygon(surf, (70, 50, 32), sp, 1)
                # chains from the tower to the tip of the bridge
                tip = max(sp, key=lambda p: abs(p[0] - (gh.hinge[0] - ox)) - p[1] * 0.001)
                top = (gh.hinge[0] - ox - gh.side * 2, gh.hinge[1] - oy - 7 * TILE)
                pygame.draw.line(surf, (70, 70, 76), top, tip, 1)
                pygame.draw.circle(surf, (60, 60, 66), (int(top[0]), int(top[1])), 3)

    # ------------------------------------------------------------------ trees, decor, objects
    def draw_trees(self, surf, cam, time, wind, light=1.0):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        for t in self.world.near("tree_chunks", ox - 200, ox + SW + 200):
            if ox - 160 < t.x < ox + SW + 160 and oy - 40 < t.y < oy + SH + t.h + 40:
                flora.draw_tree(surf, t, ox, oy, time, wind, self.season, light)

    def draw_decor(self, surf, cam, time, wind, night):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        w = self.world
        for d in w.near("decor_chunks", ox - 300, ox + SW + 300):
            if d.gone or not (ox - d.w - 60 < d.x < ox + SW + d.w + 60):
                continue
            draw_decor(surf, d, d.x - ox, d.y - oy, time, wind, night, w, self.season)

    def draw_objects(self, surf, cam):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        for o in self.world.objects:
            if not (ox - 200 < o.x < ox + SW + 200 and oy - 200 < o.y < oy + SH + 200):
                continue
            draw_object(surf, o, ox, oy, self)

    # ------------------------------------------------------------------ light
    def draw_lighting(self, surf, cam, env, dyn_lights):
        SW, SH = surf.get_size()
        w = self.world
        ox, oy = cam.offset()
        cs = 8
        gw, gh = SW // cs + 2, SH // cs + 2
        xs = ox + np.arange(gw, dtype=np.float32) * cs
        ys = oy + np.arange(gh, dtype=np.float32) * cs
        cols = np.clip((xs / TILE), 0, w.w).astype(np.float32)
        surf_y = np.interp(cols, np.arange(w.w + 1, dtype=np.float32), w.top)
        depth = ys[None, :] - surf_y[:, None]
        day = env.daylight()
        sun = np.clip(1.0 - (depth - 40.0) / 260.0, 0.0, 1.0) * day
        sun = np.maximum(sun, 0.0)
        # under the waves the light fades with depth
        for wr in w.water:
            if wr.x1 < ox or wr.x0 > ox + SW or wr.lava:
                continue
            i0 = int(max(0, (wr.x0 - ox) // cs))
            i1 = int(min(gw, (wr.x1 - ox) // cs + 1))
            if i1 > i0:
                d = np.clip((ys[None, :] - wr.level) / 500.0, 0, 0.75)
                sun[i0:i1] *= (1.0 - d)
        fire = np.zeros_like(sun)
        gx = xs[:, None]
        gy = ys[None, :]
        for (lx, ly, s) in dyn_lights:
            if s <= 0 or not (ox - 300 < lx < ox + SW + 300 and oy - 300 < ly < oy + SH + 300):
                continue
            r = 60 + 190 * s
            d = np.sqrt((gx - lx) ** 2 + (gy - ly) ** 2)
            fire = np.maximum(fire, np.clip(1.0 - d / r, 0, 1) ** 1.4 * min(1.0, s + 0.2))
        skyc = np.array(env.ambient_color(), dtype=np.float32) / 255.0
        firec = np.array((1.0, 0.76, 0.48), dtype=np.float32)
        rgb = sun[..., None] * skyc[None, None, :] + fire[..., None] * firec[None, None, :]
        rgb = np.clip(rgb + 0.05, 0, 1) * 255
        small = pygame.surfarray.make_surface(rgb.astype(np.uint8))
        big = pygame.transform.smoothscale(small, (gw * cs, gh * cs))
        surf.blit(big, (0, 0), special_flags=pygame.BLEND_MULT)

    def lights_in_view(self, cam, SW, SH, night):
        """Static light sources of buildings, decor, ores and lava near the screen."""
        ox, oy = cam.offset()
        w = self.world
        out = []
        for b in w.buildings:
            if b.x1 < ox - 300 or b.x0 > ox + SW + 300:
                continue
            for (x, y, s) in b.lights:
                if s >= 0.6 or night > 0.3:
                    out.append((x, y, s * (0.6 + 0.4 * night) if s < 0.6 else s))
        for d in w.near("decor_chunks", ox - 300, ox + SW + 300):
            if d.kind in ("torchpost", "torch", "lantern") and not d.gone:
                out.append((d.x, d.y - d.h, 0.85))
            elif d.kind == "mushroom":
                out.append((d.x, d.y - 4, 0.25))
            elif d.kind == "forge":
                out.append((d.x, d.y - 10, 0.9))
        for o in w.ores:
            if o["kind"] == "glutstein" and o["left"] > 0 and ox - 200 < o["x"] < ox + SW + 200:
                out.append((o["x"], o["y"], 0.45))
        for wr in w.water:
            if wr.lava and wr.x1 > ox and wr.x0 < ox + SW:
                for x in range(int(max(wr.x0, ox)), int(min(wr.x1, ox + SW)), 120):
                    out.append((x, wr.level, 1.0))
        return out


# ====================================================================== piece & object drawing
def draw_piece(s, pts, mat, detail, tint, role, open_, hpf, seed):
    m = MATS[mat]
    base = tint or m.color
    v = 0.93 + (hsh(seed, 3) % 100) / 100.0 * 0.12
    col = shade(base, v)
    edge = m.edge
    if role == "door" and open_:
        # an open door swings toward you: drawn as a narrow leaf against its frame
        x0 = min(p[0] for p in pts)
        x1 = max(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        y1 = max(p[1] for p in pts)
        pygame.draw.rect(s, (40, 30, 26), (x0, y0, x1 - x0, y1 - y0))
        pygame.draw.polygon(s, shade(col, 0.8), [(x0, y0), (x0 + 3, y0 - 2), (x0 + 3, y1 + 1), (x0, y1)])
        return
    if len(pts) < 3:
        return
    if role == "ladder":
        xs_ = [p[0] for p in pts]
        ys_ = [p[1] for p in pts]
        lx0, lx1, ly0, ly1 = min(xs_), max(xs_), min(ys_), max(ys_)
        pygame.draw.line(s, col, (lx0 + 1, ly0), (lx0 + 1, ly1), 2)
        pygame.draw.line(s, col, (lx1 - 1, ly0), (lx1 - 1, ly1), 2)
        y = ly1 - 5
        while y > ly0:
            pygame.draw.line(s, shade(col, 1.15), (lx0 + 1, y), (lx1 - 1, y), 2)
            y -= 9
        return
    pygame.draw.polygon(s, col, pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    wdt, hgt = x1 - x0, y1 - y0
    d = detail[0] if isinstance(detail, tuple) else detail
    var = detail[1] if isinstance(detail, tuple) else 0
    dark = shade(col, 0.78)
    light = shade(col, 1.14)
    if d == "block":
        pygame.draw.line(s, light, pts[0], pts[1], 1)
        pygame.draw.line(s, dark, pts[-1], pts[-2], 1)
    elif d == "grain":
        if wdt > hgt:
            for k in range(1, 3):
                y = y0 + hgt * k / 3
                pygame.draw.line(s, dark, (x0 + 2, y), (x1 - 2, y), 1)
        else:
            for k in range(1, 3):
                x = x0 + wdt * k / 3
                pygame.draw.line(s, dark, (x, y0 + 2), (x, y1 - 2), 1)
    elif d in ("boards", "boards_v"):
        if d == "boards" and wdt >= hgt:
            n = max(1, int(wdt // 22))
            for k in range(1, n):
                x = x0 + wdt * k / n
                pygame.draw.line(s, dark, (x, y0 + 1), (x, y1 - 1), 1)
            pygame.draw.line(s, light, (x0, y0), (x1, y0), 1)
        else:
            n = max(1, int(wdt // 7))
            for k in range(1, n):
                x = x0 + wdt * k / n
                pygame.draw.line(s, dark, (x, y0 + 1), (x, y1 - 1), 1)
    elif d == "fachwerk":
        # plaster panels in a frame of oak posts, rails and braces (Mann, Andreaskreuz)
        tim = (82, 56, 38)
        pygame.draw.rect(s, tim, (x0, y0, wdt, 4))
        pygame.draw.rect(s, tim, (x0, y1 - 4, wdt, 4))
        bays = max(2, int(wdt // 26))
        bw = wdt / bays
        for k in range(bays + 1):
            x = x0 + k * bw
            pygame.draw.line(s, tim, (x, y0), (x, y1), 4)
        rail = y0 + hgt * 0.45
        pygame.draw.line(s, tim, (x0, rail), (x1, rail), 3)
        for k in range(bays):
            xa, xb = x0 + k * bw, x0 + (k + 1) * bw
            if var == 1 and k % 2 == 0:
                pygame.draw.line(s, tim, (xa, rail), (xb, y1 - 3), 3)
                pygame.draw.line(s, tim, (xb, rail), (xa, y1 - 3), 3)
            elif k == 0:
                pygame.draw.line(s, tim, (xa, y1 - 3), (xb, rail), 3)
            elif k == bays - 1:
                pygame.draw.line(s, tim, (xb, y1 - 3), (xa, rail), 3)
            elif var == 2:
                pygame.draw.line(s, tim, (xa, y0 + 3), (xb, rail), 3)
    elif d == "gable_frame":
        tim = (82, 56, 38)
        pygame.draw.lines(s, tim, True, pts, 3)
        mx = (x0 + x1) / 2
        pygame.draw.line(s, tim, (mx, y0 + 4), (mx, y1), 3)
        pygame.draw.line(s, tim, (x0 + wdt * 0.2, y1 - hgt * 0.35), (x1 - wdt * 0.2, y1 - hgt * 0.35), 3)
        pygame.draw.rect(s, (40, 46, 60), (mx - 5, y1 - hgt * 0.32, 10, 9))
    elif d in ("thatch", "tiles", "slates", "turf"):
        # courses parallel to the slab's long top edge
        a, b = pts[0], pts[1]
        ex, ey = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ex, ey) or 1
        nx, ny = -ey / L, ex / L
        if ny < 0:
            nx, ny = -nx, -ny
        thick = abs((pts[-1][0] - a[0]) * nx + (pts[-1][1] - a[1]) * ny) if len(pts) == 4 else hgt
        if len(pts) == 3:
            # a pyramid / spire: horizontal courses, clipped to the triangle
            apex = min(pts, key=lambda p: p[1])
            for k in range(1, int(hgt // 6)):
                y = y0 + k * 6
                f = (y - apex[1]) / max(1.0, hgt)
                pygame.draw.line(s, dark, (apex[0] - wdt / 2 * f + 1, y), (apex[0] + wdt / 2 * f - 1, y), 1)
            pygame.draw.line(s, light, pts[0], pts[1], 2)
        else:
            if d == "thatch":
                for k in range(int(L // 4)):
                    t = (k + 0.5) / max(1, int(L // 4))
                    px, py = a[0] + ex * t, a[1] + ey * t
                    c = dark if (hsh(seed, k) % 3) == 0 else light
                    pygame.draw.line(s, c, (px, py), (px + nx * thick * 0.9, py + ny * thick * 0.9), 1)
                pygame.draw.line(s, shade(col, 1.25), a, b, 2)
            else:
                rows = max(1, int(thick // 4))
                for r in range(1, rows):
                    o = thick * r / rows
                    pygame.draw.line(s, dark, (a[0] + nx * o, a[1] + ny * o), (b[0] + nx * o, b[1] + ny * o), 1)
                step = 7 if d == "tiles" else 9
                for k in range(1, int(L // step)):
                    t = k * step / L
                    px, py = a[0] + ex * t, a[1] + ey * t
                    sh_ = (k % 2) * 0.5
                    pygame.draw.line(s, dark, (px + nx * thick * sh_, py + ny * thick * sh_),
                                     (px + nx * thick * (sh_ + 0.5), py + ny * thick * (sh_ + 0.5)), 1)
                pygame.draw.line(s, light, a, b, 2)
                if d == "turf":
                    for k in range(int(L // 5)):
                        t = k * 5 / L
                        px, py = a[0] + ex * t, a[1] + ey * t
                        pygame.draw.line(s, (120, 150, 70), (px, py), (px - nx * 4, py - ny * 4), 1)
    elif d == "bricks":
        for k, y in enumerate(range(int(y0) + 5, int(y1), 5)):
            pygame.draw.line(s, dark, (x0, y), (x1, y), 1)
            off = 6 if k % 2 else 0
            for x in range(int(x0) + off, int(x1), 12):
                pygame.draw.line(s, dark, (x, y - 5), (x, y), 1)
    elif d == "ashlar":
        for k, y in enumerate(range(int(y0) + 16, int(y1) + 1, 16)):
            pygame.draw.line(s, dark, (x0, y), (x1, y), 1)
            pygame.draw.line(s, light, (x0, y - 15), (x1, y - 15), 1)
            off = 14 if k % 2 else 0
            for x in range(int(x0) + off, int(x1), 28):
                pygame.draw.line(s, dark, (x, y - 16), (x, y), 1)
    elif d == "logs":
        for y in range(int(y0) + 2, int(y1), 9):
            pygame.draw.line(s, dark, (x0, y + 8), (x1, y + 8), 2)
            pygame.draw.line(s, light, (x0, y + 2), (x1, y + 2), 1)
            pygame.draw.circle(s, shade(col, 1.1), (int(x0) + 3, y + 4), 4)
            pygame.draw.circle(s, shade(col, 1.1), (int(x1) - 3, y + 4), 4)
    elif d == "rough":
        rng = random.Random(seed)
        for _ in range(max(1, int(wdt * hgt // 140))):
            px, py = rng.uniform(x0, x1), rng.uniform(y0, y1)
            pygame.draw.ellipse(s, dark, (px - 4, py - 2, 8, 5), 1)
    elif d in ("window", "arch_window", "lancet", "slit", "belfry"):
        glass = (36, 44, 58)
        if d == "window":
            pygame.draw.rect(s, (70, 50, 36), (x0 - 2, y0 - 2, wdt + 4, hgt + 4))
            pygame.draw.rect(s, glass, (x0, y0, wdt, hgt))
            pygame.draw.line(s, (70, 50, 36), ((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1), 2)
            pygame.draw.line(s, (70, 50, 36), (x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2), 2)
            pygame.draw.rect(s, (66, 92, 60), (x0 - 6, y0 - 1, 4, hgt + 2))
            pygame.draw.rect(s, (66, 92, 60), (x1 + 2, y0 - 1, 4, hgt + 2))
        else:
            pygame.draw.rect(s, glass, (x0, y0 + wdt / 2, wdt, hgt - wdt / 2))
            pygame.draw.ellipse(s, glass, (x0, y0, wdt, wdt))
            if d == "lancet":
                pygame.draw.line(s, (90, 86, 80), ((x0 + x1) / 2, y0 + 3), ((x0 + x1) / 2, y1), 1)
                pygame.draw.circle(s, (120, 90, 140), (int((x0 + x1) / 2), int(y0 + wdt / 2)), 3)
    elif d == "gate":
        n = max(2, int(wdt // 8))
        for k in range(1, n):
            x = x0 + wdt * k / n
            pygame.draw.line(s, dark, (x, y0), (x, y1), 1)
        for y in (y0 + hgt * 0.2, y0 + hgt * 0.75):
            pygame.draw.rect(s, (60, 60, 66), (x0, y - 2, wdt, 4))
            for x in range(int(x0) + 3, int(x1), 8):
                pygame.draw.circle(s, (120, 120, 126), (x, int(y)), 1)
    elif d == "stripes":
        n = 6
        for k in range(0, n, 2):
            ta, tb = k / n, (k + 1) / n
            a = (pts[0][0] + (pts[1][0] - pts[0][0]) * ta, pts[0][1] + (pts[1][1] - pts[0][1]) * ta)
            b = (pts[0][0] + (pts[1][0] - pts[0][0]) * tb, pts[0][1] + (pts[1][1] - pts[0][1]) * tb)
            c = (pts[3][0] + (pts[2][0] - pts[3][0]) * tb, pts[3][1] + (pts[2][1] - pts[3][1]) * tb)
            dd = (pts[3][0] + (pts[2][0] - pts[3][0]) * ta, pts[3][1] + (pts[2][1] - pts[3][1]) * ta)
            pygame.draw.polygon(s, (236, 228, 210), [a, b, c, dd])
    elif d == "arch_shadow":
        pygame.draw.rect(s, (30, 26, 26), (x0 + 4, y0 + 8, wdt - 8, hgt - 8))
        pygame.draw.ellipse(s, (30, 26, 26), (x0 + 4, y0, wdt - 8, 18))
    elif d == "ladder":
        pass
    elif d == "rivets":
        for x in range(int(x0) + 3, int(x1), 6):
            pygame.draw.line(s, dark, (x, y0), (x, y1), 1)
    if role not in ("backwall", "back", "window") and d not in ("window", "arch_window", "lancet", "slit"):
        pygame.draw.polygon(s, edge, pts, 1)
    if role == "door" and d != "gate":
        pygame.draw.circle(s, (40, 36, 34), (int(x1 - 2), int((y0 + y1) / 2)), 1)
    if hpf < 0.75:
        rng = random.Random(seed * 3)
        n = int((1 - hpf) * 5) + 1
        for _ in range(n):
            px, py = rng.uniform(x0, x1), rng.uniform(y0, y1)
            pygame.draw.line(s, (30, 26, 24), (px, py), (px + rng.uniform(-6, 6), py + rng.uniform(2, 8)), 1)


def draw_object(surf, o, ox, oy, r):
    pts = [(x - ox, y - oy) for x, y in o.world_pts()]
    if o.kind == "log":
        m = MATS[o.mat]
        pygame.draw.polygon(surf, m.color, pts)
        pygame.draw.line(surf, shade(m.color, 1.18), pts[0], pts[1], 2)
        pygame.draw.line(surf, shade(m.color, 0.75), pts[3], pts[2], 2)
        # cut ends show the rings
        for a, b in ((pts[0], pts[3]), (pts[1], pts[2])):
            cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            rr = max(2, int(math.hypot(a[0] - b[0], a[1] - b[1]) / 2))
            pygame.draw.circle(surf, (196, 160, 108), (int(cx), int(cy)), rr)
            pygame.draw.circle(surf, (150, 112, 70), (int(cx), int(cy)), max(1, rr // 2), 1)
        if o.crown is not None:
            t = o.crown
            # the crown rides on the falling trunk: draw the tree rotated about its base
            draw_falling_crown(surf, o, t, ox, oy, r)
    else:
        draw_piece(surf, pts, o.mat, getattr(o, "detail", MATS[o.mat].detail), o.tint, o.kind, False,
                   max(0.0, o.hp) / max(1.0, getattr(o, "max_hp", o.hp) or 1), o.id)
        if o.kind == "crafted" and o.quality < 0.999:
            pass
    if o.burn > 0:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = min(p[1] for p in pts)
        h = 10 + math.sin(r.time * 13 + o.id) * 4
        pygame.draw.polygon(surf, (240, 110, 30), [(cx - 7, cy + 4), (cx, cy - h), (cx + 7, cy + 4)])
        pygame.draw.polygon(surf, (255, 210, 90), [(cx - 3, cy + 4), (cx, cy - h * 0.5), (cx + 3, cy + 4)])


def draw_falling_crown(surf, o, t, ox, oy, r):
    """A felled trunk is a log whose local +x points up the tree; draw the crown riding on it."""
    g = t.geo()
    a = o.body.angle if o.body is not None else o.angle
    c, s = math.cos(a), math.sin(a)
    hl = o.pts[1][0]
    px, py = o.x, o.y

    def P(x, y):
        lx, ly = -hl - y, x
        return (px + lx * c - ly * s - ox, py + lx * s + ly * c - oy)
    pal = flora.season_palette(t.kind, r.season)
    for a_, b_, wdt in g["branches"]:
        pygame.draw.line(surf, flora.BARK.get(t.kind, (80, 60, 40)), P(*a_), P(*b_), max(1, int(wdt)))
    if g["tiers"]:
        for i, tier in enumerate(g["tiers"]):
            pygame.draw.polygon(surf, shade(pal[min(2, i)], 0.9), [P(x, y) for x, y in tier])
    if r.season == "winter" and t.kind not in flora.EVERGREEN:
        return
    for (pts, dy, dx) in g["clumps"]:
        pygame.draw.polygon(surf, shade(pal[1], 0.9), [P(x, y) for x, y in pts])


# ====================================================================== decor
def draw_decor(s, d, x, y, time, wind, night, world, season):
    k = d.kind
    if k == "bed":
        pygame.draw.rect(s, (110, 76, 50), (x - 11, y - 8, 22, 8))
        pygame.draw.rect(s, (190, 176, 150), (x - 10, y - 11, 20, 4))
        pygame.draw.rect(s, (150, 60, 50), (x - 4, y - 11, 14, 4))
        pygame.draw.rect(s, (90, 62, 40), (x - 11, y - 14, 3, 14))
    elif k == "chest":
        pygame.draw.rect(s, (120, 80, 46), (x - 7, y - 10, 14, 10))
        pygame.draw.rect(s, (90, 60, 36), (x - 7, y - 10, 14, 3))
        pygame.draw.rect(s, (180, 160, 80), (x - 1, y - 7, 2, 3))
        pygame.draw.rect(s, (60, 40, 26), (x - 7, y - 10, 14, 10), 1)
    elif k == "table":
        pygame.draw.rect(s, (120, 84, 52), (x - d.w / 2, y - 12, d.w, 3))
        pygame.draw.line(s, (90, 62, 40), (x - d.w / 2 + 2, y - 9), (x - d.w / 2 + 2, y), 2)
        pygame.draw.line(s, (90, 62, 40), (x + d.w / 2 - 2, y - 9), (x + d.w / 2 - 2, y), 2)
        pygame.draw.rect(s, (200, 196, 180), (x - 3, y - 15, 5, 3))
    elif k == "bench":
        pygame.draw.rect(s, (110, 76, 48), (x - d.w / 2, y - 8, d.w, 3))
        pygame.draw.line(s, (80, 56, 36), (x - d.w / 2 + 3, y - 5), (x - d.w / 2 + 3, y), 2)
        pygame.draw.line(s, (80, 56, 36), (x + d.w / 2 - 3, y - 5), (x + d.w / 2 - 3, y), 2)
    elif k == "hearth":
        pygame.draw.polygon(s, (120, 116, 108), [(x - 10, y), (x - 8, y - 6), (x + 8, y - 6), (x + 10, y)])
        f = 6 + math.sin(time * 11 + x) * 2
        pygame.draw.polygon(s, (240, 120, 40), [(x - 6, y - 5), (x, y - 5 - f * 1.4), (x + 6, y - 5)])
        pygame.draw.polygon(s, (255, 214, 100), [(x - 3, y - 5), (x, y - 5 - f * 0.7), (x + 3, y - 5)])
    elif k == "anvil":
        pygame.draw.polygon(s, (60, 62, 68), [(x - 9, y - 10), (x + 9, y - 10), (x + 6, y - 7), (x - 4, y - 7)])
        pygame.draw.rect(s, (60, 62, 68), (x - 3, y - 7, 6, 5))
        pygame.draw.rect(s, (90, 70, 50), (x - 6, y - 3, 12, 3))
    elif k == "forge":
        pygame.draw.rect(s, (110, 70, 56), (x - 12, y - 16, 24, 16))
        pygame.draw.rect(s, (60, 36, 30), (x - 8, y - 12, 16, 7))
        g = int(200 + 55 * math.sin(time * 6))
        pygame.draw.rect(s, (g, 90, 30), (x - 7, y - 10, 14, 4))
        pygame.draw.rect(s, (90, 60, 50), (x - 12, y - 28, 8, 12))
    elif k == "workbench":
        pygame.draw.rect(s, (138, 98, 60), (x - 17, y - 16, 34, 5))
        for xx in (x - 14, x + 13):
            pygame.draw.line(s, (100, 70, 44), (xx, y - 11), (xx, y), 3)
        pygame.draw.line(s, (100, 70, 44), (x - 14, y - 5), (x + 13, y - 5), 2)
        pygame.draw.line(s, (170, 170, 176), (x - 10, y - 20), (x - 2, y - 17), 2)    # a saw
        pygame.draw.rect(s, (120, 90, 60), (x + 4, y - 20, 8, 4))                       # a plane
    elif k == "altar":
        pygame.draw.rect(s, (200, 194, 180), (x - 11, y - 14, 22, 14))
        pygame.draw.rect(s, (230, 226, 216), (x - 12, y - 16, 24, 3))
        pygame.draw.line(s, (210, 180, 80), (x, y - 26), (x, y - 16), 2)
        pygame.draw.line(s, (210, 180, 80), (x - 4, y - 22), (x + 4, y - 22), 2)
    elif k == "throne":
        pygame.draw.rect(s, (120, 40, 40), (x - 8, y - 14, 16, 4))
        pygame.draw.rect(s, (130, 96, 50), (x - 8, y - 26, 3, 26))
        pygame.draw.rect(s, (130, 96, 50), (x + 5, y - 14, 3, 14))
        pygame.draw.rect(s, (210, 180, 70), (x - 9, y - 28, 5, 3))
    elif k in ("banner", "flag"):
        sw = math.sin(time * 3 + x * 0.1) * (2 + abs(wind) * 3)
        if k == "flag":
            pygame.draw.line(s, (60, 50, 40), (x, y), (x, y - d.h), 2)
            top = y - d.h
            pygame.draw.polygon(s, (170, 40, 36), [(x, top), (x + 16 + sw, top + 3 + sw * 0.3), (x + 14 + sw * 0.8,
                                                                                                top + 7),
                                                   (x, top + 9)])
        else:
            pygame.draw.polygon(s, (150, 36, 36), [(x - 6, y), (x + 6, y), (x + 6, y + d.h), (x, y + d.h - 6),
                                                   (x - 6, y + d.h)])
            pygame.draw.circle(s, (220, 190, 80), (int(x), int(y + 10)), 3)
    elif k == "cross":
        pygame.draw.line(s, (200, 180, 90), (x, y), (x, y - 14), 2)
        pygame.draw.line(s, (200, 180, 90), (x - 4, y - 10), (x + 4, y - 10), 2)
    elif k == "bell":
        pygame.draw.polygon(s, (190, 150, 70), [(x - 6, y), (x - 4, y - 10), (x + 4, y - 10), (x + 6, y)])
    elif k == "sails":
        cx, cy = x, y
        a0 = time * (0.6 + abs(wind) * 0.8)
        for i in range(4):
            a = a0 + i * math.pi / 2
            ex, ey = cx + math.cos(a) * 56, cy + math.sin(a) * 56
            pygame.draw.line(s, (90, 64, 42), (cx, cy), (ex, ey), 3)
            px, py = -math.sin(a), math.cos(a)
            p1 = (cx + math.cos(a) * 14, cy + math.sin(a) * 14)
            pygame.draw.polygon(s, (226, 216, 190), [p1, (ex, ey), (ex + px * 11, ey + py * 11),
                                                     (p1[0] + px * 11, p1[1] + py * 11)])
            pygame.draw.line(s, (150, 130, 100), p1, (ex + px * 11, ey + py * 11), 1)
        pygame.draw.circle(s, (70, 50, 36), (int(cx), int(cy)), 4)
    elif k in ("torch", "torchpost", "lantern"):
        if k == "torchpost":
            pygame.draw.line(s, (80, 56, 36), (x, y), (x, y - d.h + 6), 3)
        top = y - d.h + (6 if k == "torchpost" else 0)
        if k == "lantern":
            pygame.draw.rect(s, (60, 56, 50), (x - 3, top, 6, 9), 1)
            pygame.draw.rect(s, (255, 200, 110), (x - 2, top + 2, 4, 5))
        else:
            f = 6 + math.sin(time * 14 + x) * 2
            pygame.draw.polygon(s, (240, 120, 40), [(x - 3, top), (x, top - f), (x + 3, top)])
            pygame.draw.polygon(s, (255, 220, 120), [(x - 1, top), (x, top - f * 0.5), (x + 1, top)])
    elif k == "chain":
        tx, ty = d.data.get("to", (x, y - d.h))
        sx = d.x - x
        pygame.draw.line(s, (80, 80, 86), (x, y), (tx - sx, ty - (d.y - y)), 1)
        pygame.draw.rect(s, (70, 56, 40), (x - 2, y - 6, 4, 6))
    elif k == "gablehead":
        pygame.draw.polygon(s, (100, 70, 46), [(x - 3, y), (x - 9, y - 12), (x - 4, y - 9), (x, y - 4)])
        pygame.draw.polygon(s, (100, 70, 46), [(x + 3, y), (x + 9, y - 12), (x + 4, y - 9), (x, y - 4)])
    elif k == "goods":
        ware = d.data.get("ware", "bread")
        col = {"bread": (190, 140, 80), "cloth": (120, 60, 120), "pots": (170, 100, 70), "fish": (160, 170, 180),
               "veg": (110, 150, 60)}.get(ware, (180, 160, 120))
        for i in range(5):
            pygame.draw.ellipse(s, shade(col, 0.9 + 0.05 * i), (x - 18 + i * 7, y - 6, 8, 6))
    elif k == "barrel":
        pygame.draw.rect(s, (120, 80, 48), (x - 6, y - 15, 12, 15), border_radius=3)
        pygame.draw.line(s, (70, 70, 74), (x - 6, y - 11), (x + 6, y - 11), 1)
        pygame.draw.line(s, (70, 70, 74), (x - 6, y - 4), (x + 6, y - 4), 1)
    elif k == "bollard":
        pygame.draw.rect(s, (80, 60, 40), (x - 3, y - 8, 6, 8))
    elif k == "winch":
        pygame.draw.circle(s, (100, 72, 46), (int(x), int(y)), 6, 2)
    elif k == "bucket":
        pygame.draw.polygon(s, (110, 80, 50), [(x - 3, y - 6), (x + 3, y - 6), (x + 2, y), (x - 2, y)])
        pygame.draw.line(s, (80, 80, 80), (x, y - 6), (x, y - 16), 1)
    elif k == "sign":
        pygame.draw.line(s, (96, 70, 46), (x, y), (x, y - 30), 3)
        pygame.draw.polygon(s, (150, 112, 70), [(x - 14, y - 30), (x + 12, y - 30), (x + 16, y - 26), (x + 12, y - 22),
                                                (x - 14, y - 22)])
        pygame.draw.line(s, (90, 64, 40), (x - 10, y - 26), (x + 8, y - 26), 1)
    elif k == "plot":
        draw_plot(s, d, x, y, world, time, wind, season)
    elif k == "bush":
        rng = random.Random(d.data.get("seed", 1))
        base = (60, 110, 50) if season != "herbst" else (130, 100, 40)
        if season == "winter":
            base = (90, 80, 70)
        for i in range(4):
            r = rng.uniform(5, 9)
            cx = x + rng.uniform(-8, 8)
            cy = y - r * 0.8 - rng.uniform(0, 4)
            pygame.draw.polygon(s, shade(base, 0.85 + i * 0.08), [(cx - r, cy + r * 0.4), (cx - r * 0.4, cy - r),
                                                                  (cx + r * 0.6, cy - r * 0.8), (cx + r, cy + r * 0.3),
                                                                  (cx, cy + r * 0.7)])
        if rng.random() < 0.5 and season == "sommer":
            pygame.draw.circle(s, (170, 40, 60), (int(x + 3), int(y - 8)), 2)
    elif k in ("flowers", "heather"):
        rng = random.Random(d.data.get("seed", 1))
        cols = [(230, 220, 90), (220, 90, 90), (150, 120, 220), (240, 240, 240)] if k == "flowers" else [
            (170, 100, 170), (190, 120, 190)]
        if season == "winter":
            return
        for i in range(5):
            fx = x + rng.uniform(-7, 7)
            hh = rng.uniform(5, 11)
            sw = math.sin(time * 2 + fx * 0.1) * 1.5
            pygame.draw.line(s, (70, 120, 50), (fx, y), (fx + sw, y - hh), 1)
            pygame.draw.circle(s, rng.choice(cols), (int(fx + sw), int(y - hh)), 2)
    elif k == "fern":
        sw = math.sin(time * 1.6 + x * 0.1) * 1.5
        col = (60, 110, 50) if season not in ("herbst", "winter") else (140, 100, 50)
        for a in (-0.9, -0.4, 0.1, 0.6, 1.0):
            ex, ey = x + math.sin(a) * 12 + sw, y - math.cos(a) * 10
            pygame.draw.line(s, col, (x, y), (ex, ey), 2)
    elif k == "vine":
        pygame.draw.line(s, (100, 76, 50), (x, y), (x, y - 20), 2)
        pygame.draw.line(s, (100, 76, 50), (x - 6, y - 16), (x + 6, y - 16), 1)
        if season != "winter":
            for i in range(4):
                pygame.draw.circle(s, (80, 130, 60), (int(x - 5 + i * 3), int(y - 18 + (i % 2) * 3)), 3)
            if season == "herbst":
                pygame.draw.circle(s, (90, 40, 90), (int(x + 2), int(y - 12)), 3)
    elif k == "reeds":
        rng = random.Random(d.data.get("seed", 1))
        for i in range(6):
            fx = x + rng.uniform(-6, 6)
            hh = rng.uniform(14, 26)
            sw = math.sin(time * 1.7 + fx * 0.2) * 2 + wind * 2
            pygame.draw.line(s, (120, 130, 70), (fx, y), (fx + sw, y - hh), 1)
            if i % 2 == 0:
                pygame.draw.ellipse(s, (110, 76, 46), (fx + sw - 1, y - hh, 3, 7))
    elif k == "seaweed":
        hh = d.h
        prev = (x, y)
        for i in range(1, 6):
            t = i / 5
            px = x + math.sin(time * 1.2 + x * 0.05 + t * 3) * 6 * t
            py = y - hh * t
            pygame.draw.line(s, (50, 110, 70), prev, (px, py), 3)
            prev = (px, py)
    elif k == "shell":
        pygame.draw.ellipse(s, (226, 200, 186), (x - 3, y - 3, 6, 4))
    elif k == "mushroom":
        pygame.draw.line(s, (220, 214, 200), (x, y), (x, y - 5), 2)
        pygame.draw.ellipse(s, (180, 60, 50) if int(x) % 2 else (200, 170, 120), (x - 4, y - 8, 8, 4))
    elif k == "post":
        pygame.draw.rect(s, (90, 64, 40), (x - 2, y - d.h, 4, d.h))


def draw_plot(s, d, x, y, world, time, wind, season):
    plot = world.plots[d.data["plot"]]
    x0 = x - d.w / 2
    for i, st in enumerate(plot.strips):
        crop, growth, tilled, fert, trampled = st
        sx = x0 + i * TILE
        # furrows
        pygame.draw.polygon(s, (96, 66, 44), [(sx, y + 1), (sx + 8, y - 2), (sx + 16, y + 1)])
        if crop is None or growth <= 0.02:
            continue
        col = CROP_COL.get(crop, (200, 180, 100))
        green = (90, 140, 60)
        ripe = growth >= 0.99
        c = col if ripe else lerp_col(green, col, max(0.0, growth - 0.6) / 0.4)
        hh = (6 + 22 * growth) * (0.4 if trampled > 0.3 else 1.0)
        for k in range(3):
            px = sx + 3 + k * 5
            sw = (math.sin(time * 2.1 + px * 0.07) * (1 + abs(wind) * 2) + wind * 2) * growth
            if trampled > 0.3:
                pygame.draw.line(s, shade(c, 0.8), (px, y), (px + 8, y - 3), 2)
                continue
            if crop == "turnip":
                pygame.draw.circle(s, (220, 200, 210), (int(px), int(y - 2)), int(2 + growth * 2))
                pygame.draw.line(s, green, (px, y - 3), (px + sw * 0.5, y - 3 - hh * 0.5), 3)
            else:
                pygame.draw.line(s, shade(c, 0.9), (px, y), (px + sw, y - hh), 1)
                if growth > 0.6:
                    pygame.draw.ellipse(s, c, (px + sw - 1.5, y - hh - 3, 3, 6))
                    if crop == "flax" and not ripe:
                        pygame.draw.circle(s, (120, 150, 220), (int(px + sw), int(y - hh - 2)), 2)
