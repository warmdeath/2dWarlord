"""Tile-world rigid body: AABB vs tiles with auto step-up (smooth hills), platforms, ladders, swimming,
buoyancy, fall damage and the abyss."""
import math

from ..settings import TILE, GRAVITY, MAX_FALL
from ..world import tiles as T

SOLID = T.SOLID
PLAT = T.PLATFORM_T
CLIMB = T.CLIMB


class Body:
    w = 14
    h = 42
    weight = 1.0          # >1 sinks (armour), <1 floats
    step_up = 1           # tiles we auto-climb when walking
    max_fall = MAX_FALL
    uid_counter = 0

    def __init__(self, x, y):
        Body.uid_counter += 1
        self.uid = Body.uid_counter
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1
        self.on_ground = False
        self.in_water = 0.0       # fraction of the body submerged
        self.head_under = False
        self.in_lava = False
        self.on_ladder = False
        self.climbing = False
        self.drop_through = 0.0
        self.fall_peak = y
        self.removed = False
        self.void_fall = 0.0      # seconds spent below the world
        self.landed_speed = 0.0
        self.pushed_by_wind = 0.0
        self.step_smooth = 0.0    # visual offset so stepping up a tile looks like walking up a slope
        self.blocked = False

    # ------------------------------------------------------------- geometry
    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    @property
    def feet(self):
        return self.y + self.h

    def rect(self):
        return (self.x, self.y, self.w, self.h)

    def overlaps(self, other):
        return (self.x < other.x + other.w and self.x + self.w > other.x and
                self.y < other.y + other.h and self.y + self.h > other.y)

    def tile_pos(self):
        return int(self.cx // TILE), int((self.feet - 1) // TILE)

    # ------------------------------------------------------------- collision helpers
    @staticmethod
    def _solid(world, tx, ty):
        if tx < 0 or tx >= world.w:
            return False
        if ty < 0 or ty >= world.h:
            return False
        return SOLID[world.fg[tx, ty]]

    def _box_hits(self, world, x, y):
        x0, x1 = int(x // TILE), int((x + self.w - 0.01) // TILE)
        y0, y1 = int(y // TILE), int((y + self.h - 0.01) // TILE)
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                if self._solid(world, tx, ty):
                    return True
        return False

    def sense_liquid(self, world):
        tx = int(self.cx // TILE)
        if not (0 <= tx < world.w):
            self.in_water = 0.0
            self.head_under = False
            self.in_lava = False
            return
        top = int(self.y // TILE)
        bot = int((self.feet - 1) // TILE)
        n = 0
        lava = False
        for ty in range(max(0, top), min(world.h, bot + 1)):
            if world.liq[tx, ty] >= 3:
                n += 1
                lava = lava or bool(world.lava[tx, ty])
        total = max(1, bot - top + 1)
        self.in_water = n / total
        hy = int((self.y + 6) // TILE)
        self.head_under = 0 <= hy < world.h and world.liq[tx, hy] >= 5
        self.in_lava = lava

    def sense_ladder(self, world):
        tx = int(self.cx // TILE)
        ty = int(self.cy // TILE)
        ty2 = int((self.feet - 2) // TILE)
        self.on_ladder = (0 <= tx < world.w and ((0 <= ty < world.h and CLIMB[world.fg[tx, ty]]) or
                                                  (0 <= ty2 < world.h and CLIMB[world.fg[tx, ty2]])))

    # ------------------------------------------------------------- integration
    def physics(self, world, dt, gravity_scale=1.0):
        self.step_smooth = max(0.0, self.step_smooth - dt * 260.0)
        self.blocked = False
        self.sense_liquid(world)
        self.sense_ladder(world)
        g = GRAVITY * gravity_scale * world.gravity_scale(self.cx)
        if self.climbing and self.on_ladder:
            g = 0
        elif not self.on_ladder:
            self.climbing = False
        if self.in_water > 0.05:
            # buoyancy: light bodies float up, heavy armour sinks
            g *= (self.weight - 0.98 * self.in_water * 1.0)
            self.vy *= (1.0 - min(0.9, 3.5 * dt * self.in_water))
            self.vx *= (1.0 - min(0.9, 2.0 * dt * self.in_water))
        cap = self.max_fall if self.in_water < 0.3 else 220
        if getattr(self, "skyfall", False):
            cap = 520   # the void lets go of you gently
        self.vy = min(self.vy + g * dt, cap)
        if self.drop_through > 0:
            self.drop_through -= dt
        was_ground = self.on_ground
        self._move_x(world, self.vx * dt)
        self._move_y(world, self.vy * dt)
        if not self.on_ground:
            if was_ground or self.in_water > 0.3 or self.climbing:
                self.fall_peak = self.y
            self.fall_peak = min(self.fall_peak, self.y)
        elif self.landed_speed <= 0:
            self.fall_peak = self.y
        # below the world: the void
        if self.y > world.pixel_h() + 200:
            self.void_fall += dt

    def _move_x(self, world, dx):
        if dx == 0:
            return
        nx = self.x + dx
        if not self._box_hits(world, nx, self.y):
            self.x = nx
            return
        # auto step-up for smooth slopes
        if (self.on_ground or self.in_water > 0.3) and self.step_up:
            feet = self.y + self.h
            for k in range(1, self.step_up + 1):
                ny = (math.floor((feet - 0.01) / TILE) - k + 1) * TILE - self.h
                if ny >= self.y or self.y - ny > TILE * k + 0.5:
                    continue
                if not self._box_hits(world, nx, ny) and not self._box_hits(world, self.x, ny):
                    self.step_smooth = min(TILE * 2.0, self.step_smooth + (self.y - ny))
                    self.x = nx
                    self.y = ny
                    return
        # slide to contact
        step = 1 if dx > 0 else -1
        moved = 0.0
        while abs(moved) < abs(dx):
            inc = step if abs(dx - moved) >= 1 else (dx - moved)
            if self._box_hits(world, self.x + inc, self.y):
                break
            self.x += inc
            moved += inc
        self.vx = 0.0
        self.blocked = True

    def _move_y(self, world, dy):
        self.on_ground = False
        if dy == 0:
            # still check ground contact
            if self._box_hits(world, self.x, self.y + 1) or self._on_platform(world, self.y, self.y + 1):
                self.on_ground = True
            return
        ny = self.y + dy
        if dy > 0:
            if self._box_hits(world, self.x, ny) or self._on_platform(world, self.y, ny):
                # land on the top of the tile row
                feet_row = int((ny + self.h) // TILE)
                self.y = feet_row * TILE - self.h
                while self._box_hits(world, self.x, self.y) and self.y > ny - TILE * 2:
                    self.y -= TILE
                self.landed_speed = self.vy
                self.vy = 0.0
                self.on_ground = True
                return
            self.y = ny
        else:
            if self._box_hits(world, self.x, ny):
                row = int(ny // TILE)
                self.y = (row + 1) * TILE
                self.vy = 0.0
                return
            self.y = ny

    def _on_platform(self, world, y_old, y_new):
        if self.drop_through > 0 or self.climbing:
            return False
        old_feet = y_old + self.h
        new_feet = y_new + self.h
        row = int(new_feet // TILE)
        if int(old_feet // TILE) == row and old_feet % TILE != 0:
            return False
        if old_feet > row * TILE + 0.5:
            return False
        x0, x1 = int(self.x // TILE), int((self.x + self.w - 0.01) // TILE)
        for tx in range(x0, x1 + 1):
            if 0 <= tx < world.w and 0 <= row < world.h and PLAT[world.fg[tx, row]]:
                return True
        return False
