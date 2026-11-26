"""Arrows, bolts and fire arrows. Wind pushes them, rain weakens bowstrings, they stick where they land."""
import math

import pygame

from ..settings import TILE
import pymunk

from ..poly.world import CAT_STRUCT, CAT_OBJECT, CAT_TERRAIN

Q_HIT = pymunk.ShapeFilter(mask=CAT_STRUCT | CAT_OBJECT | CAT_TERRAIN)


class Projectile:
    def __init__(self, x, y, vx, vy, owner, kind="arrow", dmg=16, flags=()):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.owner = owner
        self.kind = kind
        self.dmg = dmg
        self.flags = flags
        self.stuck = False
        self.stuck_t = 0.0
        self.life = 8.0
        self.removed = False
        self.fire = kind == "fire_arrow"
        self.angle = math.atan2(vy, vx)
        self.faction = getattr(owner, "faction", None)

    def update(self, game, dt):
        if self.stuck:
            self.stuck_t += dt
            if self.stuck_t > 12:
                self.removed = True
            return
        self.life -= dt
        if self.life <= 0:
            self.removed = True
            return
        env = game.env
        g, wind = {"bolt": (300, 30), "stone": (600, 8), "ball": (300, 0)}.get(self.kind, (520, 70))
        self.vy += g * dt
        self.vx += env.wind * wind * dt
        steps = max(1, int(math.hypot(self.vx, self.vy) * dt / 6))
        sdt = dt / steps
        w = game.world
        for _ in range(steps):
            px, py = self.x, self.y
            self.px, self.py = px, py
            self.x += self.vx * sdt
            self.y += self.vy * sdt
            hit = None
            q = w.space.segment_query_first((px, py), (self.x, self.y), 0.5, Q_HIT)
            if q is not None and not q.shape.sensor:
                pc = getattr(q.shape, "owner", None)
                if not (getattr(pc, "role", "") == "portcullis" and self.kind in ("arrow", "bolt", "fire_arrow")):
                    hit = (q.point.x, q.point.y, pc, q.shape)
            if hit is None and w.terrain_solid(self.x, self.y):
                hit = (self.x, self.y, None, None)
            if hit is not None:
                hx, hy, pc, shape = hit
                self.x, self.y = hx, hy
                if self.kind in ("stone", "ball"):
                    from ..combat import siege
                    if shape is not None and shape.body.body_type == pymunk.Body.DYNAMIC:
                        shape.body.apply_impulse_at_world_point((self.vx * 6, self.vy * 6), (hx, hy))
                    siege.impact(game, hx, hy, self.kind)
                    self.removed = True
                    return
                self.stuck = True
                if self.fire:
                    game.ignite_at(hx + math.cos(self.angle) * 4, hy + math.sin(self.angle) * 4, 6)
                game.fx.dust(self.x, self.y, 2)
                if shape is not None and shape.body.body_type == pymunk.Body.DYNAMIC:
                    shape.body.apply_impulse_at_world_point((self.vx * 0.3, self.vy * 0.3), (hx, hy))
                return
            wl = w.water_level(self.x)
            if wl is not None and self.y > wl:
                wr = w.water_at(self.x)
                if wr is not None and wr.lava:
                    self.removed = True
                    return
                self.vx *= 0.9
                self.vy *= 0.9
                self.fire = False
            if self.y >= w.pixel_h() + 400:
                self.removed = True
                return
            if game.combat.projectile_hit(self):
                return
        self.angle = math.atan2(self.vy, self.vx)
        if self.fire:
            game.fx.fire(self.x, self.y, 1) if game.rng.random() < 0.4 else None

    def draw(self, surf, ox, oy):
        x, y = self.x - ox, self.y - oy
        if not (-30 < x < surf.get_width() + 30 and -30 < y < surf.get_height() + 30):
            return
        if self.kind == "stone":
            pygame.draw.polygon(surf, (140, 136, 128), [(x - 6, y - 2), (x - 2, y - 6), (x + 5, y - 4), (x + 6, y + 3),
                                                        (x, y + 6), (x - 5, y + 4)])
            return
        if self.kind == "ball":
            pygame.draw.circle(surf, (40, 40, 44), (int(x), int(y)), 4)
            pygame.draw.line(surf, (200, 200, 200), (x - self.vx * 0.02, y - self.vy * 0.02), (x, y), 1)
            return
        ln = 16 if self.kind != "bolt" else 11
        dx, dy = math.cos(self.angle) * ln, math.sin(self.angle) * ln
        pygame.draw.line(surf, (110, 80, 50), (x - dx, y - dy), (x, y), 2)
        pygame.draw.line(surf, (220, 220, 225), (x - dx * 0.15, y - dy * 0.15), (x, y), 2)
        pygame.draw.line(surf, (230, 230, 230), (x - dx, y - dy), (x - dx * 0.8, y - dy * 0.8 - 2), 1)
        if self.fire:
            pygame.draw.circle(surf, (255, 170, 50), (int(x), int(y)), 3)
