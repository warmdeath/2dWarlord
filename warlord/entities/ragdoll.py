"""Ragdolls with real joints: when a fighter falls, every bone of the skeleton that animated them becomes a
rigid capsule in the physics world, pinned to its neighbours at the joints. They tumble down slopes, drape
over walls and logs, and settle. After a while a ragdoll is frozen into a still pose to keep battles cheap."""
import math

import pymunk

from ..gfx.rig import STICKS
from ..poly.world import F_DEBRIS

BONES = (("hip", "sh", 4.5), ("sh", "head", 3.5), ("hip", "kb", 3.0), ("kb", "fb", 2.6), ("hip", "kf", 3.0),
         ("kf", "ff", 2.6), ("sh", "eb", 2.4), ("eb", "hb", 2.1), ("sh", "ef", 2.4), ("ef", "hf", 2.1))
LIMITS = {("sh", "head"): 0.9, ("kb", "fb"): 2.2, ("kf", "ff"): 2.2, ("eb", "hb"): 2.4, ("ef", "hf"): 2.4}
MAX_ACTIVE = 36
_active = []


class Ragdoll:
    def __init__(self, joints, vel=(0.0, 0.0), spin=0.0, dt=1 / 60):
        self.points = {k: [x, y, x, y] for k, (x, y) in joints.items()}
        self.vel = vel
        self.spin = spin
        self.t = 0.0
        self.asleep = False
        self.bodies = None
        self.world = None
        self.sticks = [(a, b, 1.0) for a, b in STICKS]

    def __getstate__(self):
        d = self.__dict__.copy()
        d["bodies"] = None
        d["world"] = None
        d["asleep"] = True
        return d

    def _build(self, world):
        sp = world.space
        P = {k: (v[0], v[1]) for k, v in self.points.items()}
        vx, vy = self.vel
        self.bodies = []
        self.bone_of = {}
        owner_of = {}
        for a, b, r in BONES:
            (ax, ay), (bx, by) = P[a], P[b]
            L = max(2.0, math.hypot(bx - ax, by - ay))
            mass = 1.0 + L * 0.08
            body = pymunk.Body(mass, pymunk.moment_for_segment(mass, (-L / 2, 0), (L / 2, 0), r))
            body.position = ((ax + bx) / 2, (ay + by) / 2)
            body.angle = math.atan2(by - ay, bx - ax)
            boost = 1.6 if a in ("sh", "eb", "ef") or b == "head" else 1.0
            body.velocity = (vx * boost + (self.spin if b == "head" else 0), vy)
            sh = pymunk.Segment(body, (-L / 2, 0), (L / 2, 0), r)
            sh.friction = 0.9
            sh.elasticity = 0.05
            sh.filter = pymunk.ShapeFilter(group=id(self) & 0x7FFFFFFF, categories=F_DEBRIS.categories,
                                           mask=F_DEBRIS.mask)
            sp.add(body, sh)
            self.bodies.append((a, b, body, L))
            self.bone_of[(a, b)] = body
            owner_of.setdefault(a, (body, -L / 2))
            owner_of.setdefault(b, (body, L / 2))
        # pin every bone to the bone that owns its start joint
        self.joints = []
        for a, b, body, L in self.bodies:
            for k, end in ((a, -L / 2), (b, L / 2)):
                ob, oe = owner_of[k]
                if ob is body:
                    continue
                j = pymunk.PivotJoint(ob, body, (oe, 0), (end, 0))
                j.collide_bodies = False
                sp.add(j)
                self.joints.append(j)
                lim = LIMITS.get((a, b))
                if lim and k == a:
                    rl = pymunk.RotaryLimitJoint(ob, body, -lim, lim)
                    sp.add(rl)
                    self.joints.append(rl)
        self.world = world
        _active.append(self)
        while len(_active) > MAX_ACTIVE:
            _active[0].freeze()

    def freeze(self):
        if self in _active:
            _active.remove(self)
        if self.bodies is not None and self.world is not None:
            self._sync()
            sp = self.world.space
            present = set(sp.constraints)
            for j in self.joints:
                if j in present:
                    sp.remove(j)
            bodies = set(sp.bodies)
            for a, b, body, L in self.bodies:
                if body in bodies:
                    sp.remove(body, *list(body.shapes))
        self.bodies = []
        self.asleep = True

    def _sync(self):
        for a, b, body, L in self.bodies:
            pa = body.local_to_world((-L / 2, 0))
            pb = body.local_to_world((L / 2, 0))
            if a in ("hip",) or (a == "sh" and b == "head") or a not in self.points or True:
                self.points[a][0], self.points[a][1] = pa.x, pa.y
            self.points[b][0], self.points[b][1] = pb.x, pb.y

    def update(self, world, dt):
        if self.asleep:
            return
        if self.bodies is None:
            self._build(world)
        if not self.bodies:
            return
        self._sync()
        self.t += dt
        moving = sum(body.velocity.length for _, _, body, _ in self.bodies)
        if self.t > 12 or (self.t > 2.0 and moving < 25):
            self.freeze()

    def anchor(self):
        h = self.points["hip"]
        return h[0], h[1]
