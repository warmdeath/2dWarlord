"""The World: dense numpy tile layers plus sparse metadata.

Layers are indexed [x, y] (column-major) so vertical slices are contiguous and
pygame.surfarray can consume them directly.
"""
import numpy as np

from ..settings import TILE, CHUNK, WORLD_H, SEA_LEVEL
from . import tiles as T


class World:
    def __init__(self, width, height=WORLD_H, seed=1300):
        self.w = width
        self.h = height
        self.seed = seed
        self.fg = np.zeros((width, height), dtype=np.uint8)
        self.bg = np.zeros((width, height), dtype=np.uint8)
        self.liq = np.zeros((width, height), dtype=np.uint8)    # 0..8 water/lava amount
        self.lava = np.zeros((width, height), dtype=bool)       # liquid is lava instead of water
        self.surface = np.full(width, SEA_LEVEL, dtype=np.int16)  # generated surface row per column
        self.abyss_w = 250
        self.lava_w = 450
        self.regions = []        # (x0, x1, biome)
        self.kingdom_spans = []  # (x0, x1, kingdom_key)
        self.settlements = []    # filled by generator (dicts)
        self.signs = {}          # (x,y) -> text
        self.chests = {}         # (x,y) -> {item: n}
        self.damage = {}         # (x,y) -> accumulated mining damage (seconds)
        self.fires = {}          # (x,y) -> seconds burning
        self.active_liquid = set()
        self.dirty = set()       # chunk coords needing re-render
        self.liquid_dirty = set()
        self.changes = 0

    # ------------------------------------------------------------------ access
    def inside(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return int(self.fg[x, y])
        return 0

    def solid(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return bool(T.SOLID[self.fg[x, y]])
        return y >= self.h and False

    def mark(self, x, y):
        cx, cy = x // CHUNK, y // CHUNK
        self.dirty.add((cx, cy))
        # neighbours matter for smoothed corners
        lx, ly = x % CHUNK, y % CHUNK
        if lx == 0:
            self.dirty.add((cx - 1, cy))
        elif lx == CHUNK - 1:
            self.dirty.add((cx + 1, cy))
        if ly == 0:
            self.dirty.add((cx, cy - 1))
        elif ly == CHUNK - 1:
            self.dirty.add((cx, cy + 1))
        self.changes += 1

    def set(self, x, y, tid, wake=True):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        self.fg[x, y] = tid
        self.damage.pop((x, y), None)
        self.mark(x, y)
        if wake:
            self.wake_liquid(x, y)

    def set_bg(self, x, y, bid):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.bg[x, y] = bid
            self.mark(x, y)

    def wake_liquid(self, x, y):
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.w and 0 <= ny < self.h and self.liq[nx, ny]:
                self.active_liquid.add((nx, ny))

    def mark_liquid(self, x, y):
        self.liquid_dirty.add((x // CHUNK, y // CHUNK))

    # ------------------------------------------------------------------ queries
    def ground_at(self, x, start_y=0):
        """First solid/platform row at or below start_y in column x."""
        if not (0 <= x < self.w):
            return self.h + 50
        col = self.fg[x]
        ys = np.nonzero(T.SOLID[col[start_y:]] | T.PLATFORM_T[col[start_y:]])[0]
        if len(ys) == 0:
            return self.h + 50
        return start_y + int(ys[0])

    def water_surface(self, x, near_y):
        """Top row of the liquid body in column x around near_y, or None."""
        if not (0 <= x < self.w):
            return None
        y = max(0, min(self.h - 1, near_y))
        col = self.liq[x]
        if col[y] == 0:
            # search a little up/down
            for d in range(1, 6):
                if y + d < self.h and col[y + d]:
                    y = y + d
                    break
            else:
                return None
        while y > 0 and col[y - 1] > 0:
            y -= 1
        return y

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
        """Near the abyss gravity weakens (the land 'forgets' to hold you)."""
        tx = px / TILE
        edge = self.abyss_w + 1100
        if tx < edge:
            f = max(0.0, (tx - self.abyss_w * 0.2)) / edge
            return 0.55 + 0.45 * min(1.0, f)
        return 1.0

    def pixel_w(self):
        return self.w * TILE

    def pixel_h(self):
        return self.h * TILE
