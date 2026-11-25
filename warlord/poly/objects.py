"""Loose things with real physics: felled trunks, split logs, planks, debris from broken walls, stones,
and every piece you shape yourself. They tumble, stack, roll down slopes, float, burn and can be picked up,
carried in your arms, or anchored in place to become part of what you build."""
import math

import pymunk

from .materials import MATS
from .world import F_OBJECT, F_DEBRIS, CT_OBJECT, F_STRUCT, CT_BLOCK


def centroid(pts):
    a = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a) < 1e-6:
        return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


class PhysObject:
    uid = 0

    def __init__(self, pts_local, pos, angle=0.0, mat="log", kind="debris", item=None, quality=1.0, name=None,
                 debris=False, n=1, shape_key=None):
        PhysObject.uid += 1
        self.id = PhysObject.uid
        self.pts = [(float(x), float(y)) for x, y in pts_local]
        self.pos = (float(pos[0]), float(pos[1]))
        self.angle = float(angle)
        self.vel = (0.0, 0.0)
        self.avel = 0.0
        self.mat = mat
        self.kind = kind            # log, plank, debris, stone, crafted, piece
        self.item = item            # bag item it turns into when picked up
        self.n = n
        self.quality = quality
        self.name = name
        self.shape_key = shape_key  # template it matched (door, spike, …)
        self.debris = debris
        self.anchored = False
        self.burn = 0.0
        self.age = 0.0
        self.hp = max(5.0, MATS[mat].hp * area(self.pts) / 100.0)
        self.body = None
        self.shape = None
        self.world = None
        self.crown = None           # a falling tree's crown, drawn with the trunk
        self.hinge = None
        self.removed = False
        self.tint = None
        self.sleep_t = 0.0
        r = max(math.hypot(x, y) for x, y in self.pts)
        self.radius = r

    # -------------------------------------------------------------- pickling
    def __getstate__(self):
        self.sync()
        d = self.__dict__.copy()
        d["body"] = None
        d["shape"] = None
        d["world"] = None
        d["hinge"] = None
        return d

    def sync(self):
        if self.body is not None:
            self.pos = tuple(self.body.position)
            self.angle = self.body.angle
            self.vel = tuple(self.body.velocity)
            self.avel = self.body.angular_velocity

    # -------------------------------------------------------------- physics
    def mass(self):
        return max(0.5, MATS[self.mat].density * area(self.pts))

    def attach(self, world):
        if self.removed:
            return
        self.world = world
        if self.anchored:
            b = pymunk.Body(body_type=pymunk.Body.STATIC)
        else:
            m = self.mass()
            b = pymunk.Body(m, pymunk.moment_for_poly(m, self.pts))
        b.position = self.pos
        b.angle = self.angle
        if not self.anchored:
            b.velocity = self.vel
            b.angular_velocity = self.avel
        s = pymunk.Poly(b, self.pts)
        s.friction = 0.85
        s.elasticity = 0.08
        if self.anchored:
            s.filter = F_STRUCT
            s.collision_type = CT_BLOCK
        else:
            s.filter = F_DEBRIS if self.debris else F_OBJECT
            s.collision_type = CT_OBJECT
        s.owner = self
        s.mat = self.mat
        world.space.add(b, s)
        self.body, self.shape = b, s

    def detach(self):
        if self.body is not None and self.world is not None:
            self.sync()
            if self.hinge is not None:
                try:
                    self.world.space.remove(self.hinge)
                except Exception:
                    pass
                self.hinge = None
            try:
                self.world.space.remove(self.body, self.shape)
            except Exception:
                pass
        self.body = self.shape = None

    def remove(self):
        self.detach()
        self.removed = True
        if self.world is not None and self in self.world.objects:
            self.world.objects.remove(self)

    def anchor(self, on=True):
        w = self.world
        self.detach()
        self.anchored = on
        self.vel, self.avel = (0.0, 0.0), 0.0
        if w is not None:
            self.attach(w)

    def world_pts(self):
        if self.body is not None:
            p, a = self.body.position, self.body.angle
        else:
            p, a = self.pos, self.angle
        c, s = math.cos(a), math.sin(a)
        return [(p[0] + x * c - y * s, p[1] + x * s + y * c) for x, y in self.pts]

    @property
    def x(self):
        return self.body.position.x if self.body is not None else self.pos[0]

    @property
    def y(self):
        return self.body.position.y if self.body is not None else self.pos[1]

    def update(self, game, dt):
        self.age += dt
        b = self.body
        if b is None:
            return
        w = game.world
        # water: wood floats, stone sinks slowly
        wr = w.water_at(b.position.x)
        if wr is not None and b.position.y > wr.level and b.position.y < w.surface_y(b.position.x) + 4:
            if not self.anchored:
                dens = MATS[self.mat].density
                lift = 1.0 if dens < 0.012 else 0.4
                depth = min(1.0, (b.position.y - wr.level) / 20.0)
                b.apply_force_at_local_point((0, -b.mass * 1500 * lift * (0.6 + 0.6 * depth)), (0, 0))
                b.velocity = b.velocity * 0.98
                b.angular_velocity *= 0.97
                if wr.lava:
                    self.burn = max(self.burn, 1.0)
        # a felled trunk swings on its stump until it passes the tipping point
        if self.hinge is not None and abs(b.angle) > 1.1:
            w.space.remove(self.hinge)
            self.hinge = None
        if self.crown is not None and self.hinge is None and (b.is_sleeping or (
                abs(b.angular_velocity) < 0.3 and b.velocity.length < 40 and abs(b.angle) > 1.2)):
            game.tree_landed(self)
        if self.burn > 0:
            self.burn += dt * 0.25
            self.hp -= dt * 2.5
            if self.hp <= 0:
                game.fx.smoke(b.position.x, b.position.y, 6)
                self.remove()
                return
        if self.debris and not self.anchored:
            if b.is_sleeping:
                self.sleep_t += dt
            if self.age > 40 or (self.sleep_t > 8 and area(self.pts) < 500):
                self.remove()
                return
        if b.position.y > w.pixel_h() + 600:
            self.remove()

    # -------------------------------------------------------------- factories
    @classmethod
    def from_piece(cls, world, pc, debris=False):
        from .prefab import remove_piece
        cx, cy = centroid(pc.pts)
        local = [(x - cx, y - cy) for x, y in pc.pts]
        if area(local) < 3:
            remove_piece(world, pc)
            return None
        o = cls(local, (cx, cy), 0.0, pc.mat, "debris" if (debris or not pc.solid) else "piece",
                item=MATS[pc.mat].drop, debris=debris or not pc.solid)
        o.tint = pc.tint
        o.detail = pc.detail
        o.burn = pc.burn
        remove_piece(world, pc)
        world.objects.append(o)
        o.attach(world)
        return o

    @classmethod
    def log(cls, world, x, y, length, thick, angle=0.0, mat="log", item="wood"):
        hl, ht = length / 2, thick / 2
        pts = [(-hl, -ht), (hl, -ht * 0.9), (hl, ht * 0.9), (-hl, ht)]
        o = cls(pts, (x, y), angle, mat, "log", item=item, n=max(1, int(length // 40)))
        world.objects.append(o)
        o.attach(world)
        return o

    @classmethod
    def spawn(cls, world, pts_local, x, y, mat, kind, **kw):
        o = cls(pts_local, (x, y), kw.pop("angle", 0.0), mat, kind, **kw)
        world.objects.append(o)
        o.attach(world)
        return o


def objects_near(world, x, y, r):
    out = []
    for o in world.objects:
        if abs(o.x - x) < r + o.radius and abs(o.y - y) < r + o.radius:
            out.append(o)
    return out
