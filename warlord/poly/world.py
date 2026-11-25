"""PolyWorld — a world made of polygons and real rigid-body physics (pymunk / Chipmunk2D).

Terrain   : a smooth surface polyline over a solid crust, with caves cut out as polygon passages
            (shapely), floating stones over the Abyss, a crust that breaks off at both world ends.
Water     : ocean, lakes, moats and the Fire Sea as level-based regions with buoyancy.
Physics   : one pymunk Space. Terrain near the player is streamed in as static segments; buildings
            are made of breakable polygon blocks; logs, debris, crafted pieces and stones are dynamic
            bodies; people and animals are capsule bodies with a hand-animated skeleton on top.
Coordinates are pixels, y grows downward (gravity is +y). TILE (16 px) remains the unit for
'columns' so the geography, society and story code keep their numbers.
"""
import math

import numpy as np
import pymunk
from shapely import contains_xy
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from ..settings import TILE, SEA_LEVEL

GRAVITY = 1500.0
CHUNK_PX = 512

# collision categories
CAT_TERRAIN = 1
CAT_STRUCT = 2
CAT_OBJECT = 4
CAT_CHAR = 8
CAT_DEBRIS = 16
CAT_PLATFORM = 32
ALL = 0xFFFF

F_TERRAIN = pymunk.ShapeFilter(categories=CAT_TERRAIN)
F_STRUCT = pymunk.ShapeFilter(categories=CAT_STRUCT)
F_PLATFORM = pymunk.ShapeFilter(categories=CAT_PLATFORM)
F_OBJECT = pymunk.ShapeFilter(categories=CAT_OBJECT, mask=CAT_TERRAIN | CAT_STRUCT | CAT_OBJECT | CAT_CHAR |
                              CAT_PLATFORM)
F_DEBRIS = pymunk.ShapeFilter(categories=CAT_DEBRIS, mask=CAT_TERRAIN | CAT_STRUCT | CAT_OBJECT | CAT_PLATFORM)
F_CHAR = pymunk.ShapeFilter(categories=CAT_CHAR, mask=CAT_TERRAIN | CAT_STRUCT | CAT_OBJECT | CAT_PLATFORM)
Q_SOLID = pymunk.ShapeFilter(mask=CAT_TERRAIN | CAT_STRUCT)
Q_WALK = pymunk.ShapeFilter(mask=CAT_TERRAIN | CAT_STRUCT | CAT_PLATFORM | CAT_OBJECT)

CT_CHAR = 1
CT_PLATFORM = 2
CT_BLOCK = 3
CT_OBJECT = 4
CT_MISSILE = 5


def body_velocity(body, gravity, damping, dt):
    """Per-body gravity scale (climbing, swimming, the weak gravity at the Abyss) and buoyancy."""
    gs = getattr(body, "g_scale", 1.0)
    gx, gy = gravity
    buoy = getattr(body, "buoy", 0.0)
    drag = getattr(body, "drag", 0.0)
    pymunk.Body.update_velocity(body, (gx * gs, gy * gs - buoy), damping * (1.0 - drag), dt)


class Water:
    __slots__ = ("x0", "x1", "level", "lava")

    def __init__(self, x0, x1, level, lava=False):
        self.x0, self.x1, self.level, self.lava = x0, x1, level, lava


class PolyWorld:
    def __init__(self, width_tiles, height_tiles=256, seed=1300):
        self.w = width_tiles
        self.h = height_tiles
        self.seed = seed
        self.top = np.zeros(width_tiles + 1, dtype=np.float32)       # surface y (px) per column edge
        self.bottom = np.full(width_tiles + 1, height_tiles * TILE, dtype=np.float32)
        self.surface = np.zeros(width_tiles, dtype=np.int32)         # rows, for biome/legacy lookups
        self.caves = []          # shapely polygons
        self.cave_bounds = []
        self.rocks = []          # floating stone polygons (lists of points)
        self.water = []          # Water regions
        self.regions = []
        self.kingdom_spans = []
        self.settlements = []
        self.abyss_w = 250
        self.lava_w = 450
        self.trees = []          # Tree objects
        self.buildings = []      # Building objects (blocks live in them)
        self.decor = []          # signs, chests, furniture, stations…
        self.plots = []          # crop fields
        self.ladders = []        # climbable rects (x0, y0, x1, y1)
        self.smokers = []
        self.gatehouses = []
        self.fires = {}          # unused legacy dict (kept for old callers)
        self.dirty = set()
        self.liquid_dirty = set()
        self.signs = {}
        self.pieces = {}         # id -> Piece (building parts)
        self.piece_chunks = {}   # chunk -> [piece ids]
        self.tree_chunks = {}    # chunk -> [Tree]
        self.decor_chunks = {}   # chunk -> [Decor]
        self.ladder_chunks = {}  # chunk -> [(x0, y0, x1, y1)]
        self.cave_chunks = {}    # chunk -> [cave index]
        self.ores = []           # ore veins in cave walls
        self.objects = []        # dynamic PhysObjects (logs, debris, crafted pieces, stones)
        self.next_piece = 1
        self.time = 0.0
        self.wind = 0.0
        self.setup_physics()

    # ------------------------------------------------------------------ physics setup / pickling
    def setup_physics(self):
        self.space = pymunk.Space()
        self.space.gravity = (0, GRAVITY)
        self.space.iterations = 12
        self.space.sleep_time_threshold = 0.8
        self.space.idle_speed_threshold = 6.0
        self.space.collision_slop = 0.4
        self.loaded = {}         # chunk -> list of static shapes
        self._chunk_geom = {}
        self.bodies = set()      # attached character bodies (post_step after each space step)
        self.kinematics = []     # drawbridges, portcullises
        self.space.on_collision(CT_CHAR, CT_PLATFORM, pre_solve=_platform_presolve)
        self.space.on_collision(CT_OBJECT, CT_PLATFORM, pre_solve=_platform_presolve_obj)
        self.space.on_collision(CT_OBJECT, None, post_solve=_impact_post)

    def __getstate__(self):
        d = self.__dict__.copy()
        for k in ("space", "loaded", "_chunk_geom", "bodies", "kinematics"):
            d.pop(k, None)
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self.setup_physics()
        for o in self.objects:
            o.attach(self)
        for gh in self.gatehouses:
            if hasattr(gh, "bridge"):
                gh.bridge = None

    def step(self, dt, substeps=2):
        for gh in self.gatehouses:
            if hasattr(gh, "update") and (gh.bridge is not None or self.is_loaded(gh.hinge[0])):
                gh.update(self, dt)
        h = dt / substeps
        for _ in range(substeps):
            self.space.step(h)
        for b in list(self.bodies):
            b.post_step(self, dt)
        self.time += dt

    def is_loaded(self, px):
        return int(px // CHUNK_PX) in self.loaded

    def wave_at(self, px):
        return 0.0

    # ------------------------------------------------------------------ spatial index
    @staticmethod
    def chunk_of(px):
        return int(px // CHUNK_PX)

    def index_add(self, table, px, item):
        getattr(self, table).setdefault(int(px // CHUNK_PX), []).append(item)

    def index_remove(self, table, px, item):
        lst = getattr(self, table).get(int(px // CHUNK_PX))
        if lst and item in lst:
            lst.remove(item)

    def near(self, table, x0, x1):
        t = getattr(self, table)
        for cx in range(int(x0 // CHUNK_PX), int(x1 // CHUNK_PX) + 1):
            for it in t.get(cx, ()):
                yield it

    def ladder_at(self, px, py):
        for (x0, y0, x1, y1) in self.ladder_chunks.get(int(px // CHUNK_PX), ()):
            if x0 <= px <= x1 and y0 <= py <= y1:
                return True
        return False

    def add_ladder(self, rect):
        x0, y0, x1, y1 = rect
        for cx in range(int(x0 // CHUNK_PX), int(x1 // CHUNK_PX) + 1):
            self.ladder_chunks.setdefault(cx, []).append(rect)

    def remove_ladder(self, rect):
        for lst in self.ladder_chunks.values():
            if rect in lst:
                lst.remove(rect)

    def solid_point(self, px, py):
        """Terrain, standing structures or solid objects at a point (one-way platforms count from above)."""
        if self.terrain_solid(px, py):
            return True
        for h in self.space.point_query((px, py), 0, Q_WALK):
            if not h.shape.sensor and h.shape.collision_type != CT_CHAR:
                return True
        return False

    # ------------------------------------------------------------------ queries
    def pixel_w(self):
        return self.w * TILE

    def pixel_h(self):
        return self.h * TILE

    def inside(self, tx, ty):
        return 0 <= tx < self.w and 0 <= ty < self.h

    def surface_y(self, px):
        f = px / TILE
        i = int(math.floor(f))
        if i < 0:
            return float(self.top[0])
        if i >= self.w:
            return float(self.top[-1])
        t = f - i
        return float(self.top[i] * (1 - t) + self.top[i + 1] * t)

    def bottom_y(self, px):
        i = max(0, min(self.w, int(px // TILE)))
        return float(self.bottom[i])

    def dug_at(self, cx):
        d = getattr(self, "dug", None)
        if d is None:
            self.dug = d = {}
        return d.get(cx)

    def dig(self, x, y, r):
        """Take a round bite out of the ground (a pick, a shovel, a sapper). Returns the area removed."""
        from shapely.geometry import Point
        from shapely.ops import unary_union
        if getattr(self, "dug", None) is None:
            self.dug = {}
        hole = Point(x, y).buffer(r, quad_segs=4)
        removed = 0.0
        for cx in range(int((x - r) // CHUNK_PX), int((x + r) // CHUNK_PX) + 1):
            part = hole.intersection(box(cx * CHUNK_PX, -10000, (cx + 1) * CHUNK_PX, 100000))
            if part.is_empty:
                continue
            ground = self.chunk_geometry(cx)
            if ground is not None:
                removed += ground.intersection(part).area
            old = self.dug.get(cx)
            self.dug[cx] = part if old is None else unary_union([old, part]).simplify(0.4)
            self._invalidate(cx)
        return removed

    def fill(self, x, y, r):
        """Put earth back into a dug hole."""
        from shapely.geometry import Point
        d = getattr(self, "dug", None) or {}
        hole = Point(x, y).buffer(r, quad_segs=4)
        filled = 0.0
        for cx in range(int((x - r) // CHUNK_PX), int((x + r) // CHUNK_PX) + 1):
            g = d.get(cx)
            if g is None:
                continue
            filled += g.intersection(hole).area
            d[cx] = g.difference(hole)
            self._invalidate(cx)
        return filled

    def in_cave(self, px, py):
        d = getattr(self, "dug", None)
        if d:
            g = d.get(int(px // CHUNK_PX))
            if g is not None and not g.is_empty and contains_xy(g, px, py):
                return True
        for ci in self.cave_chunks.get(int(px // CHUNK_PX), ()):
            x0, y0, x1, y1 = self.cave_bounds[ci]
            if x0 <= px <= x1 and y0 <= py <= y1 and contains_xy(self.caves[ci], px, py):
                return True
        return False

    def add_cave(self, poly):
        """Cut a passage into the ground (generation, sapping tunnels, mine shafts)."""
        if poly.is_empty:
            return
        self.caves.append(poly)
        b = poly.bounds
        self.cave_bounds.append(b)
        ci = len(self.caves) - 1
        for cx in range(int(b[0] // CHUNK_PX), int(b[2] // CHUNK_PX) + 1):
            self.cave_chunks.setdefault(cx, []).append(ci)
            self._invalidate(cx)

    def _invalidate(self, cx):
        if hasattr(self, "_chunk_geom"):
            self._chunk_geom.pop(cx, None)
            if cx in self.loaded:
                for sh in self.loaded.pop(cx):
                    self.space.remove(sh)
        self.dirty.add(cx)

    def terrain_solid(self, px, py):
        if not (0 <= px < self.pixel_w()):
            return False
        if py < self.surface_y(px) or py > self.bottom_y(px):
            return False
        return not self.in_cave(px, py)

    def solid_at(self, px, py):
        """Terrain or a standing building block (used by ragdolls, missiles, fire…)."""
        if self.terrain_solid(px, py):
            return True
        hits = self.space.point_query((px, py), 0, Q_SOLID)
        return any(h.shape.sensor is False for h in hits)

    def ground_y(self, px, from_y=None, depth=600):
        """First walkable surface straight below (from_y downward): terrain, floors, platforms, objects."""
        if from_y is None:
            from_y = self.surface_y(px) - 400
        q = self.space.segment_query_first((px, from_y), (px, from_y + depth), 0.5, Q_WALK)
        sy = self.surface_y(px)
        best = sy if sy >= from_y else None
        if q is not None and (best is None or q.point.y < best):
            best = q.point.y
        if best is None:
            # below the surface: are we in a cave? walk down to the cave floor
            y = from_y
            while y < from_y + depth:
                if self.terrain_solid(px, y):
                    return y
                y += 4
            return self.pixel_h() + 200
        return best

    def ground_at(self, tx, start_row=0):
        """Legacy tile API: row of the first walkable surface at or below start_row."""
        px = tx * TILE + 8
        y = self.ground_y(px, start_row * TILE - 1)
        return int(y // TILE)

    def water_at(self, px):
        for wr in self.water:
            if wr.x0 <= px <= wr.x1:
                return wr
        return None

    def water_level(self, px):
        wr = self.water_at(px)
        if wr is None:
            return None
        if self.surface_y(px) <= wr.level:
            return None
        return wr.level

    def kingdom_at(self, x):
        for x0, x1, key in self.kingdom_spans:
            if x0 <= x < x1:
                return key
        return None

    def biome_at(self, x):
        for x0, x1, b in self.regions:
            if x0 <= x < x1:
                return b
        return "ocean"

    def settlement_at(self, x, margin=0):
        for s in self.settlements:
            if s["x0"] - margin <= x <= s["x1"] + margin:
                return s
        return None

    def gravity_scale(self, px):
        tx = px / TILE
        edge = self.abyss_w + 1100
        if tx < edge:
            f = max(0.0, (tx - self.abyss_w * 0.2)) / edge
            return 0.55 + 0.45 * min(1.0, f)
        return 1.0

    # ------------------------------------------------------------------ terrain geometry
    def chunk_geometry(self, cx):
        """Shapely ground polygon for one chunk (surface down to the crust bottom, caves removed)."""
        g = self._chunk_geom.get(cx)
        if g is not None:
            return g
        x0 = cx * CHUNK_PX
        x1 = x0 + CHUNK_PX
        i0 = max(0, int(x0 // TILE))
        i1 = min(self.w, int(x1 // TILE))
        if i1 <= i0 or i0 >= self.w:
            self._chunk_geom[cx] = None
            return None
        xs = np.arange(i0, i1 + 1) * TILE
        top = self.top[i0:i1 + 1]
        bot = self.bottom[i0:i1 + 1]
        solid = bot - top > 2
        pieces = []
        # split where the crust is missing (the Abyss)
        run = []
        for k in range(len(xs)):
            if solid[k]:
                run.append(k)
            elif run:
                pieces.append(run)
                run = []
        if run:
            pieces.append(run)
        polys = []
        for r in pieces:
            if len(r) < 2:
                continue
            pts = [(float(xs[k]), float(top[k])) for k in r] + [(float(xs[k]), float(bot[k])) for k in reversed(r)]
            p = Polygon(pts)
            if not p.is_valid:
                p = p.buffer(0)
            polys.append(p)
        if not polys:
            self._chunk_geom[cx] = None
            return None
        geom = unary_union(polys)
        clip = box(x0 - 1, -10000, x1 + 1, 100000)
        for ci in self.cave_chunks.get(cx, ()):
            geom = geom.difference(self.caves[ci].intersection(clip))
        d = getattr(self, "dug", None)
        if d and d.get(cx) is not None:
            geom = geom.difference(d[cx])
        self._chunk_geom[cx] = geom
        return geom

    def _segments_of(self, geom, x0, x1):
        segs = []
        if geom is None or geom.is_empty:
            return segs
        geoms = getattr(geom, "geoms", [geom])
        for p in geoms:
            if p.geom_type != "Polygon":
                continue
            for ring in [p.exterior] + list(p.interiors):
                c = list(ring.coords)
                for a, b in zip(c, c[1:]):
                    # drop the artificial vertical cuts at the chunk borders
                    if (abs(a[0] - x0) < 0.01 and abs(b[0] - x0) < 0.01) or (abs(a[0] - x1) < 0.01 and
                                                                               abs(b[0] - x1) < 0.01):
                        continue
                    segs.append((a, b))
        return segs

    def stream(self, px, radius=2600):
        """Keep static terrain near px in the physics space."""
        want = set(range(int((px - radius) // CHUNK_PX), int((px + radius) // CHUNK_PX) + 1))
        for cx in list(self.loaded):
            if cx not in want:
                for sh in self.loaded.pop(cx):
                    self.space.remove(sh)
        sb = self.space.static_body
        for cx in want:
            if cx in self.loaded:
                continue
            shapes = []
            geom = self.chunk_geometry(cx)
            for a, b in self._segments_of(geom, cx * CHUNK_PX, (cx + 1) * CHUNK_PX):
                sh = pymunk.Segment(sb, a, b, 1.5)
                sh.friction = 0.9
                sh.elasticity = 0.05
                sh.filter = F_TERRAIN
                shapes.append(sh)
            for pts in self.rocks:
                if cx * CHUNK_PX <= pts[0][0] < (cx + 1) * CHUNK_PX:
                    sh = pymunk.Poly(sb, pts)
                    sh.friction = 0.9
                    sh.filter = F_TERRAIN
                    shapes.append(sh)
            for pid in self.piece_chunks.get(cx, ()):
                pc = self.pieces.get(pid)
                if pc is not None and pc.solid and pc.state == "static":
                    sh = pc.make_shape(sb)
                    shapes.append(sh)
            if shapes:
                self.space.add(*shapes)
            self.loaded[cx] = shapes

    # ------------------------------------------------------------------ editing terrain
    def set_surface(self, i0, i1, ys):
        self.top[i0:i1] = ys
        for cx in range(int(i0 * TILE // CHUNK_PX) - 1, int(i1 * TILE // CHUNK_PX) + 2):
            self._invalidate(cx)

    def piece_shape_added(self, pc):
        """A piece placed or rebuilt after its chunk was streamed: add its shape now."""
        cx = int(pc.cx // CHUNK_PX)
        if cx in self.loaded and pc.solid and pc.state == "static" and pc.shape is None:
            sh = pc.make_shape(self.space.static_body)
            self.space.add(sh)
            self.loaded[cx].append(sh)

    def piece_shape_removed(self, pc):
        sh = pc.shape
        if sh is None:
            return
        cx = int(pc.cx // CHUNK_PX)
        lst = self.loaded.get(cx)
        if lst is not None and sh in lst:
            lst.remove(sh)
            self.space.remove(sh)
        elif sh.space is not None:
            self.space.remove(sh)
        pc.shape = None


def _platform_presolve(arb, space, data):
    """One-way floors: you land on them from above, jump up through them, drop through with down+jump."""
    a, b = arb.shapes
    ch = a if a.collision_type == CT_CHAR else b
    pl = b if ch is a else a
    o = getattr(ch, "owner", None)
    if o is None:
        return
    top = pl.bb.bottom      # pymunk's bb "bottom" is the smallest y = the walking surface in our y-down world
    if o.drop_through > 0 or o.climbing or o.vy < -5 or o.feet > top + 6:
        arb.process_collision = False


def _platform_presolve_obj(arb, space, data):
    a, b = arb.shapes
    ob = a if a.collision_type == CT_OBJECT else b
    pl = b if ob is a else a
    if ob.body.velocity.y < -5 or ob.bb.top > pl.bb.bottom + 10:
        arb.process_collision = False


def _impact_post(arb, space, data):
    """Heavy things that hit people hurt them (a felled trunk, a falling beam, a boulder)."""
    if not arb.is_first_contact:
        return
    ke = arb.total_ke
    if ke < 2.0e6:
        return
    for sh in arb.shapes:
        o = getattr(sh, "owner", None)
        if o is not None and sh.collision_type == CT_CHAR:
            hits = getattr(space, "impacts", None)
            if hits is None:
                space.impacts = hits = []
            hits.append((o, ke))


def poly_area(pts):
    a = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        a += x0 * y1 - x1 * y0
    return abs(a) / 2
