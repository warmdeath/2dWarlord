"""Characters as pymunk capsules (Chipmunk2D) in the polygon world.

The controllers (humanoid, animal, NPC brains) still speak the old language: they read and write
x, y, vx, vy, on_ground, in_water, on_ladder, climbing... This class turns that into a real rigid body:
`physics()` hands the wanted velocity to pymunk, the session steps the space once for everybody, and
`post_step()` reads back position, contacts and landings. Gravity, buoyancy, the weak pull near the Abyss
and ladders are per-body gravity scales.
"""
import math

import pymunk

from ..settings import TILE, MAX_FALL
from ..poly.world import F_CHAR, CT_CHAR, Q_SOLID, Q_WALK, body_velocity


class Body:
    w = 14
    h = 42
    weight = 1.0          # >1 sinks (armour), <1 floats
    mass = 60.0
    max_fall = MAX_FALL
    uid_counter = 0
    friction = 0.0

    def __init__(self, x, y):
        Body.uid_counter += 1
        self.uid = Body.uid_counter
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1
        self.on_ground = False
        self.in_water = 0.0
        self.head_under = False
        self.in_lava = False
        self.on_ladder = False
        self.climbing = False
        self.drop_through = 0.0
        self.fall_peak = y
        self.removed = False
        self.void_fall = 0.0
        self.landed_speed = 0.0
        self.pushed_by_wind = 0.0
        self.step_smooth = 0.0
        self.blocked = False
        self.ground_normal = (0.0, -1.0)
        self.standing_on = None
        self.contacts = []
        self.blocked_by = None
        self._pb = None
        self._shape = None
        self._world = None
        self._driven = False
        self._sx = self._sy = None
        self._prev_vy = 0.0
        self._shape_h = None
        self.frozen = False

    # ------------------------------------------------------------- pickling
    def __getstate__(self):
        d = self.__dict__.copy()
        d["_pb"] = None
        d["_shape"] = None
        d["_world"] = None
        d["_shape_h"] = None
        d["contacts"] = []
        d.pop("_fig_cache", None)      # a cached drawing (a pygame Surface) does not pickle
        return d

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

    # ------------------------------------------------------------- pymunk plumbing
    def _capsule(self):
        w, h = self.w, self.h
        if w > h:      # animals: a lying capsule
            r = h / 2
            return (-w / 2 + r, -r), (w / 2 - r, -r), r
        r = w / 2
        return (0, -h + r), (0, -r), r

    def attach(self, world):
        if self._pb is not None and self._world is world:
            return
        self._world = world
        b = pymunk.Body(self.mass, float("inf"))
        b.position = (self.cx, self.feet)
        b.velocity = (self.vx, self.vy)
        b.velocity_func = body_velocity
        b.g_scale = 1.0
        b.owner = self
        a, c, r = self._capsule()
        s = pymunk.Segment(b, a, c, r)
        s.friction = self.friction
        s.elasticity = 0.0
        s.filter = F_CHAR
        s.collision_type = CT_CHAR
        s.owner = self
        world.space.add(b, s)
        world.bodies.add(self)
        self._pb, self._shape = b, s
        self._shape_h = (self.w, self.h)
        self._sx, self._sy = self.x, self.y

    def detach(self):
        w = self._world
        if self._pb is not None and w is not None:
            try:
                w.space.remove(self._pb, self._shape)
            except Exception:
                pass
            w.bodies.discard(self)
        self._pb = self._shape = None
        self._world = None

    def _box_hits(self, world, x, y):
        """Is a box of our size at (x, y) blocked by terrain or structures?"""
        if world.terrain_solid(x + 2, y + 2) or world.terrain_solid(x + self.w - 2, y + 2):
            return True
        hits = world.space.bb_query(pymunk.BB(x + 1, y + 1, x + self.w - 1, y + self.h - 3), Q_SOLID)
        return any(not h.sensor for h in hits)

    def sense_liquid(self, world):
        self.in_lava = False
        lvl = None
        wr = world.water_at(self.cx)
        if wr is not None and self.y < world.surface_y(self.cx) + 6:
            lvl = wr.level
        if lvl is None or self.feet <= lvl:
            self.in_water = 0.0
            self.head_under = False
            return
        self.in_water = max(0.0, min(1.0, (self.feet - lvl) / self.h))
        self.head_under = self.y + 6 > lvl + world.wave_at(self.cx)
        self.in_lava = wr.lava

    def sense_ladder(self, world):
        self.on_ladder = world.ladder_at(self.cx, self.cy) or world.ladder_at(self.cx, self.feet - 3)

    # ------------------------------------------------------------- control (before the space steps)
    def physics(self, world, dt, gravity_scale=1.0):
        if self._pb is None or self._world is not world:
            self.attach(world)
        b = self._pb
        if self._sx is not None and (abs(self.x - self._sx) > 0.01 or abs(self.y - self._sy) > 0.01):
            b.position = (self.cx, self.feet)        # moved by game logic (spawn, mount, teleport…)
            world.space.reindex_shapes_for_body(b)
        if self._shape_h != (self.w, self.h):
            a, c, r = self._capsule()
            self._shape.unsafe_set_endpoints(a, c)
            self._shape.unsafe_set_radius(r)
            self._shape_h = (self.w, self.h)
        self.step_smooth = 0.0
        self.sense_liquid(world)
        self.sense_ladder(world)
        if not world.is_loaded(self.cx):
            # beyond the streamed terrain: hold still until the ground arrives
            self.frozen = True
            b.velocity = (0, 0)
            b.g_scale = 0.0
            self._driven = True
            return
        self.frozen = False
        g = gravity_scale * world.gravity_scale(self.cx)
        if self.climbing and self.on_ladder:
            g = 0.0
        elif not self.on_ladder:
            self.climbing = False
        if self.in_water > 0.05:
            g *= (self.weight - 0.98 * self.in_water)
            self.vy *= (1.0 - min(0.9, 3.5 * dt * self.in_water))
            self.vx *= (1.0 - min(0.9, 2.0 * dt * self.in_water))
        cap = self.max_fall if self.in_water < 0.3 else 220
        if getattr(self, "skyfall", False):
            cap = 520
        if self.drop_through > 0:
            self.drop_through -= dt
        vy = min(self.vy, cap)
        # stick to the ground when walking down a slope instead of hopping off it
        if self.on_ground and vy >= -1 and self.in_water < 0.3 and not self.climbing:
            gy = world.ground_y(self.cx, self.feet - 2, 22)
            gap = gy - self.feet
            if 0.5 < gap < 20:
                vy = max(vy, min(500.0, gap / dt * 0.8))
            # small steps (a threshold, a root, a plank) are walked up
            if abs(self.vx) > 10:
                fx = self.cx + math.copysign(self.w / 2 + 3, self.vx)
                if world.solid_point(fx, self.feet - 3) and not world.solid_point(fx, self.feet - 13) and \
                        not world.solid_point(fx, self.feet - self.h + 2):
                    vy = min(vy, -150.0)
        vx = self.vx
        # never push into what we touched last step: slide along it instead (walls stop you, slopes guide you)
        for nx, ny in self.contacts:
            d = vx * nx + vy * ny
            if d < 0:
                vx -= d * nx
                vy -= d * ny
        if self.on_ground and abs(self.vx) < 1 and vy >= -1 and self.in_water < 0.3 and not self.climbing:
            g = 0.0          # stand firm on a slope instead of creeping down it
            vy = 0.0
            vx = 0.0
        b.g_scale = g
        b.velocity = (vx, vy)
        self._cmd_vx = vx
        self._prev_vy = vy
        self._driven = True

    # ------------------------------------------------------------- read back (after the space stepped)
    def post_step(self, world, dt):
        b = self._pb
        if b is None:
            return
        if not self._driven:
            # controlled by something else this frame (horse, boat, ragdoll): follow it, don't simulate
            b.position = (self.cx, self.feet)
            b.velocity = (0, 0)
            b.g_scale = 0.0
            self._sx, self._sy = self.x, self.y
            return
        self._driven = False
        if self.frozen:
            self._sx, self._sy = self.x, self.y
            return
        was_ground = self.on_ground
        px, py = b.position
        self.x = px - self.w / 2
        self.y = py - self.h
        vx, vy = b.velocity
        self.blocked = False
        self.blocked_by = None
        ground = False
        normal = None
        standing = None
        me = self._shape

        contacts = []

        def scan(arb):
            nonlocal ground, normal, standing
            if not arb.process_collision or arb.shapes[0].sensor or arb.shapes[1].sensor:
                return
            n = arb.normal
            if arb.shapes[0] is me:        # outward normal of what we touch, pointing at us
                nx, ny = -n.x, -n.y
                other = arb.shapes[1]
            else:
                nx, ny = n.x, n.y
                other = arb.shapes[0]
            if len(arb.contact_point_set.points) == 0:
                return
            contacts.append((nx, ny))
            if ny < -0.55:
                ground = True
                normal = (nx, ny)
                standing = other
            elif abs(nx) > 0.75 and ny < 0.3:
                if (nx < 0) == (self.vx > 0) and abs(self.vx) > 1:
                    self.blocked = True
                    self.blocked_by = getattr(other, "owner", None)
        b.each_arbiter(scan)
        self.contacts = contacts
        self.on_ground = ground
        self.standing_on = standing
        if normal:
            self.ground_normal = normal
        if ground and not was_ground:
            self.landed_speed = max(0.0, self._prev_vy)
        if ground and vy > 0:
            vy = 0.0
        if self.blocked:
            vx = 0.0
        elif abs(vx - getattr(self, "_cmd_vx", vx)) < 60:
            vx = self.vx      # keep the commanded speed; contact friction is not the controller's business
        self.vx, self.vy = vx, vy
        if not self.on_ground:
            if was_ground or self.in_water > 0.3 or self.climbing:
                self.fall_peak = self.y
            self.fall_peak = min(self.fall_peak, self.y)
        elif self.landed_speed <= 0:
            self.fall_peak = self.y
        if self.y > world.pixel_h() + 200:
            self.void_fall += dt
        self._sx, self._sy = self.x, self.y
