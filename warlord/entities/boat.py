"""Die Kogge — a sailing boat. Wind from behind fills the sail; against the wind you crawl or row.
Storms make the hull pitch, and a full sail in a gale can capsize her."""
import math
import random

import pygame

from ..settings import TILE, SEA_LEVEL
from ..world import tiles as T


class Boat:
    kind = "boat"

    def __init__(self, x, y=None, colors=((176, 34, 36), (236, 232, 222)), name="Kogge"):
        self.w = 112
        self.h = 22
        self.x = float(x)
        self.y = float(y if y is not None else SEA_LEVEL * TILE - 12)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1
        self.sail = 0.0
        self.sail_target = 0.0
        self.colors = colors
        self.name = name
        self.pilot = None
        self.passengers = []
        self.tilt = 0.0
        self.capsized = False
        self.capsize_t = 0.0
        self.removed = False
        self.uid = id(self)
        self.dead = False
        self.anim_t = random.uniform(0, 10)
        self.rowing = False
        self.owner = None
        self.grounded = False

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def feet(self):
        return self.y + self.h

    def deck_y(self):
        return self.y + 2

    def update(self, game, dt):
        w = game.world
        env = game.env
        self.anim_t += dt
        tx = int(self.cx // TILE)
        surf = w.water_surface(tx, int(self.feet // TILE)) if 0 <= tx < w.w else None
        storm = env.rain() * (1.0 if env.current()[0] == "sturm" else 0.4)
        if surf is None:
            # on land or falling
            self.vy += 900 * dt
            self.y += self.vy * dt
            g = w.ground_at(tx, max(0, int(self.y // TILE)))
            if self.feet >= g * TILE:
                self.y = g * TILE - self.h
                self.vy = 0
                self.vx *= 0.8
                self.grounded = True
        else:
            self.grounded = False
            wave = math.sin(self.anim_t * 1.6 + self.x * 0.01) * (2 + storm * 7)
            target_y = surf * TILE - self.h * 0.55 + wave
            self.vy += (target_y - self.y) * 6 * dt
            self.vy *= 0.9
            self.y += self.vy * dt
            self.tilt = math.sin(self.anim_t * 1.3) * (0.03 + storm * 0.12)
        # sail physics
        self.sail += (self.sail_target - self.sail) * min(1.0, dt * 1.5)
        along = env.wind * self.facing
        if self.capsized:
            self.capsize_t += dt
            self.vx *= 0.97
            target = 0.0
        else:
            if along > 0:
                target = self.facing * (30 + 260 * along * self.sail)
            else:
                target = self.facing * (35 * self.sail * (1 + along))   # beating against the wind
            if self.rowing:
                target += self.facing * 60
            if surf is None:
                target = 0.0
            # gale + full sail = danger
            if storm > 0.6 and self.sail > 0.75 and abs(env.wind) > 0.7 and random.random() < dt * 0.04:
                self.capsize(game)
        self.vx += (target - self.vx) * min(1.0, dt * 0.6)
        nx = self.x + self.vx * dt
        # collide with land at the waterline
        lead = nx + (self.w if self.vx > 0 else 0)
        ltx = int(lead // TILE)
        lty = int((self.y + self.h * 0.7) // TILE)
        if w.inside(ltx, lty) and T.SOLID[w.fg[ltx, lty]]:
            self.vx = 0.0
        else:
            self.x = nx
        for p in [self.pilot] + self.passengers:
            if p is not None and not p.dead:
                off = getattr(p, "deck_off", self.w / 2)
                p.x = self.x + off - p.w / 2
                p.y = self.deck_y() - p.h
                p.vx = self.vx
                p.vy = 0
                p.on_ground = True

    def capsize(self, game):
        self.capsized = True
        self.capsize_t = 0.0
        self.sail = self.sail_target = 0.0
        game.fx.splash(self.cx, self.y, 30)
        game.fx.text(self.cx, self.y - 40, "Gekentert!", (180, 220, 255), gloss="capsized!")
        for p in [self.pilot] + list(self.passengers):
            if p is not None:
                game.leave_boat(p, self)

    def right(self):
        if self.capsized and self.capsize_t > 4:
            self.capsized = False
            return True
        return False

    def draw(self, surf, ox, oy):
        x, y = self.x - ox, self.y - oy
        if not (-200 < x < surf.get_width() + 200 and -200 < y < surf.get_height() + 200):
            return
        f = self.facing
        cx = x + self.w / 2

        def R(px, py):
            dx, dy = px - cx, py - (y + self.h / 2)
            c, s = math.cos(self.tilt), math.sin(self.tilt)
            return (cx + dx * c - dy * s, y + self.h / 2 + dx * s + dy * c)

        hull = (110, 74, 44)
        if self.capsized:
            pts = [R(x, y + 8), R(x + self.w, y + 8), R(x + self.w - 14, y - 6), R(x + 14, y - 6)]
            pygame.draw.polygon(surf, hull, pts)
            return
        bow = x + self.w if f > 0 else x
        stern = x if f > 0 else x + self.w
        pts = [R(stern, y), R(bow, y - 4), R(bow - f * 16, y + self.h), R(stern + f * 12, y + self.h)]
        pygame.draw.polygon(surf, hull, pts)
        for k in range(1, 4):
            yy = y + k * self.h / 4
            pygame.draw.line(surf, (80, 52, 30), R(stern + f * 4, yy), R(bow - f * 6, yy - 2), 1)
        # stern castle
        sc = [R(stern, y), R(stern + f * 26, y), R(stern + f * 26, y - 12), R(stern, y - 12)]
        pygame.draw.polygon(surf, (126, 88, 52), sc)
        # mast and sail
        mx = cx + f * 6
        top = y - 92
        pygame.draw.line(surf, (90, 64, 40), R(mx, y), R(mx, top), 4)
        if self.sail > 0.05:
            env_w = getattr(self, "_wind", 0.5)
            billow = 14 * self.sail * (1 if env_w * f >= 0 else -0.6) * f
            sh = 70 * self.sail
            c1, c2 = self.colors
            sail_pts = [R(mx - 30, top + 8), R(mx + 30, top + 8), R(mx + 30 + billow, top + 8 + sh / 2),
                        R(mx + 30, top + 8 + sh), R(mx - 30, top + 8 + sh), R(mx - 30 + billow, top + 8 + sh / 2)]
            pygame.draw.polygon(surf, (236, 228, 210), sail_pts)
            for k in range(3):
                a = mx - 30 + k * 20 + 7
                pygame.draw.line(surf, c1, R(a, top + 10), R(a + billow * 0.6, top + 6 + sh), 6)
            pygame.draw.line(surf, (90, 64, 40), R(mx - 32, top + 8), R(mx + 32, top + 8), 3)
        else:
            pygame.draw.line(surf, (220, 210, 190), R(mx - 30, top + 10), R(mx + 30, top + 10), 5)
        pygame.draw.polygon(surf, self.colors[0], [R(mx, top), R(mx - f * -18, top + 5), R(mx, top + 10)])
