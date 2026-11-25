"""Ambient life: birds crossing the sky, butterflies over meadows, fireflies at night, autumn leaves
drifting on the wind, and smoke rising from chimneys and charcoal kilns."""
import math
import random

import pygame

from ..settings import TILE


class Ambient:
    def __init__(self):
        self.birds = []        # [x, y, vx, phase, flock_offset]
        self.bugs = []         # [x, y, vx, vy, kind, t]
        self.t = 0.0
        self.rng = random.Random(5)

    def update(self, game, dt, view):
        rng = self.rng
        env = game.env
        self.t += dt
        ox, oy = game.camera.offset()
        vw, vh = view
        day = not env.is_night()
        season = env.season()
        # birds: a flock now and then, in fair weather
        if day and env.rain() < 0.5 and rng.random() < dt * 0.05 and len(self.birds) < 14:
            d = rng.choice((-1, 1))
            x0 = ox - 60 if d > 0 else ox + vw + 60
            y0 = oy + rng.uniform(40, vh * 0.35)
            n = rng.randint(3, 7)
            for i in range(n):
                self.birds.append([x0 - d * i * 14, y0 + abs(i - n // 2) * 7, d * rng.uniform(70, 95),
                                   rng.uniform(0, 6), 0])
        for b in self.birds:
            b[0] += (b[2] + env.wind * 20) * dt
            b[3] += dt * 9
            b[1] += math.sin(self.t + b[0] * 0.01) * dt * 6
        self.birds = [b for b in self.birds if ox - 200 < b[0] < ox + vw + 200]
        # butterflies by day in spring/summer, fireflies on summer nights
        want = 0
        kind = None
        if season in (0, 1) and day and env.rain() < 0.3:
            want, kind = 8, "butterfly"
        elif season == 1 and not day:
            want, kind = 22, "firefly"
        self.bugs = [b for b in self.bugs if b[4] == kind and ox - 100 < b[0] < ox + vw + 100 and b[5] < 30]
        if kind and len(self.bugs) < want and rng.random() < dt * 4:
            x = ox + rng.uniform(0, vw)
            tx = int(x // TILE)
            if game.world.inside(tx, 0):
                gy = game.world.surface_y(x)
                if game.world.biome_at(tx) in ("plains", "hills", "forest", "vineyard", "edge", "moor", "coast"):
                    self.bugs.append([x, gy - rng.uniform(10, 50), 0.0, 0.0, kind, 0.0])
        for b in self.bugs:
            b[5] += dt
            b[2] += rng.uniform(-60, 60) * dt
            b[3] += rng.uniform(-60, 60) * dt
            b[2] *= 0.98
            b[3] *= 0.98
            b[0] += b[2] * dt
            b[1] += b[3] * dt
        # autumn leaves drift from the crowns in view
        if season == 2 and rng.random() < dt * 6:
            trees = [t for t in game.world.near("tree_chunks", ox, ox + vw)
                     if t.state == "stand" and t.kind not in ("pine", "fir", "dead")]
            if trees:
                t = rng.choice(trees)
                col = rng.choice([(196, 120, 40), (214, 160, 50), (170, 70, 40)])
                game.fx._p(t.x + rng.uniform(-t.h * 0.25, t.h * 0.25), t.y - t.h * rng.uniform(0.5, 0.9),
                           env.wind * 40 + rng.uniform(-10, 10), 10, rng.uniform(3, 6), col, 2, 12)
        # smoke from chimneys and kilns in view (more in the evening and in winter)
        hour = env.hour()
        rate = 0.25 + (0.6 if hour > 17 or hour < 8 else 0) + (0.6 if season == 3 else 0)
        for (sx, sy) in game.world.smokers:
            px = sx * TILE + 8
            if ox - 40 < px < ox + vw + 40 and rng.random() < dt * rate:
                game.fx.smoke(px, sy * TILE - 6, 1)

    def draw(self, surf, ox, oy, env):
        """Sky layer: birds."""
        night = env.is_night()
        col = (40, 40, 48) if not night else (20, 20, 28)
        for x, y, vx, ph, _ in self.birds:
            sx, sy = x - ox, y - oy
            flap = math.sin(ph) * 3
            pygame.draw.lines(surf, col, False, [(sx - 5, sy - flap), (sx, sy), (sx + 5, sy - flap)], 1)

    def draw_front(self, surf, ox, oy):
        """In front of the world (after lighting, so fireflies glow)."""
        t = pygame.time.get_ticks() * 0.01
        for x, y, vx, vy, kind, age in self.bugs:
            sx, sy = int(x - ox), int(y - oy)
            if kind == "butterfly":
                w = 2 + int(abs(math.sin(t + x)) * 2)
                c = (240, 220, 90) if int(x) % 3 else (230, 120, 160)
                pygame.draw.ellipse(surf, c, (sx - w, sy - 2, w, 3))
                pygame.draw.ellipse(surf, c, (sx, sy - 2, w, 3))
            else:
                if math.sin(t * 0.5 + x * 0.1) > 0.2:
                    pygame.draw.circle(surf, (220, 255, 120), (sx, sy), 2)
                    surf.set_at((sx, sy), (255, 255, 220))
