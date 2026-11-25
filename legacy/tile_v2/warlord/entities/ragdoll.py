"""Verlet ragdoll: when a fighter falls, the same skeleton that animated them becomes a chain of
physical points with stick constraints that tumbles, slides and settles on the tile world."""
import math

from ..settings import TILE
from ..world import tiles as T
from ..gfx.rig import STICKS

GRAVITY = 1500.0


class Ragdoll:
    def __init__(self, joints, vel=(0.0, 0.0), spin=0.0, dt=1 / 60):
        vx, vy = vel
        self.points = {}
        for k, (x, y) in joints.items():
            # the upper body gets more of the blow so bodies topple instead of sliding
            boost = 1.0 + (0.6 if k in ("head", "sh", "eb", "ef", "hb", "hf") else 0.0)
            ex = spin if k in ("head", "sh") else 0.0
            self.points[k] = [x, y, x - (vx * boost + ex) * dt, y - vy * dt]
        self.sticks = []
        for a, b in STICKS:
            pa, pb = self.points[a], self.points[b]
            self.sticks.append((a, b, max(1.0, math.hypot(pa[0] - pb[0], pa[1] - pb[1]))))
        self.t = 0.0
        self.asleep = False

    def _collide(self, world, p):
        tx, ty = int(p[0] // TILE), int(p[1] // TILE)
        if world.inside(tx, ty) and (T.SOLID[world.fg[tx, ty]]):
            top = ty * TILE - 0.2
            if p[3] <= top + 0.5:          # came from above: rest on the surface with friction
                p[1] = top
                p[2] = p[0] - (p[0] - p[2]) * 0.6
                p[3] = p[1] + (p[1] - p[3]) * 0.2
            else:                          # from the side: push back out
                p[0] = p[2]

    def update(self, world, dt):
        if self.asleep:
            return
        dt = min(dt, 1 / 30)
        moved = 0.0
        for p in self.points.values():
            x, y, ox, oy = p
            vx = (x - ox) * 0.992
            vy = (y - oy) * 0.992
            tx, ty = int(x // TILE), int(y // TILE)
            if world.inside(tx, ty) and world.liq[tx, ty] > 3:
                vx *= 0.9
                vy = vy * 0.9 - 6 * dt * dt * GRAVITY * 0.05
            p[2], p[3] = x, y
            p[0] = x + vx
            p[1] = y + vy + GRAVITY * dt * dt
            moved += abs(vx) + abs(vy)
            self._collide(world, p)
        for _ in range(4):
            for a, b, length in self.sticks:
                pa, pb = self.points[a], self.points[b]
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                d = math.hypot(dx, dy) or 0.001
                diff = (d - length) / d * 0.5
                pa[0] += dx * diff
                pa[1] += dy * diff
                pb[0] -= dx * diff
                pb[1] -= dy * diff
            for p in self.points.values():
                self._collide(world, p)
        self.t += dt
        if self.t > 6 or (self.t > 1.2 and moved < 0.4):
            self.asleep = True

    def anchor(self):
        h = self.points["hip"]
        return h[0], h[1]
