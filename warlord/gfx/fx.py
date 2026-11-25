"""Particles and floating combat text."""
import math
import random

import pygame


class FX:
    def __init__(self):
        self.parts = []    # [x, y, vx, vy, life, max_life, color, size, grav]
        self.texts = []    # [x, y, text, color, life, gloss]
        self.flash = 0.0
        self.fonts = None

    def _p(self, x, y, vx, vy, life, color, size=2, grav=600):
        if len(self.parts) < 1500:
            self.parts.append([x, y, vx, vy, life, life, color, size, grav])

    def blood(self, x, y, n, d=1):
        for _ in range(n):
            self._p(x, y, d * random.uniform(20, 160), random.uniform(-160, 20), random.uniform(0.3, 0.8),
                    (150 + random.randint(-20, 30), 20, 20), random.choice((1, 2, 2)))

    def sparks(self, x, y, n):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(60, 260)
            self._p(x, y, math.cos(a) * s, math.sin(a) * s, random.uniform(0.15, 0.4),
                    (255, random.randint(200, 255), 120), 1, 300)

    def dust(self, x, y, n, color=(150, 130, 100)):
        for _ in range(n):
            self._p(x, y, random.uniform(-60, 60), random.uniform(-60, -10), random.uniform(0.3, 0.7), color, 2, 200)

    def debris(self, x, y, color, n=6):
        for _ in range(n):
            self._p(x, y, random.uniform(-90, 90), random.uniform(-200, -40), random.uniform(0.4, 0.9), color, 2, 900)

    def fire(self, x, y, n):
        for _ in range(n):
            self._p(x + random.uniform(-6, 6), y, random.uniform(-15, 15), random.uniform(-90, -30),
                    random.uniform(0.3, 0.7), random.choice([(255, 160, 40), (255, 220, 90), (240, 90, 30)]), 2, -80)

    def smoke(self, x, y, n=1):
        for _ in range(n):
            g = random.randint(70, 110)
            self._p(x + random.uniform(-4, 4), y, random.uniform(-10, 10), random.uniform(-40, -20),
                    random.uniform(1.0, 2.0), (g, g, g), 3, -20)

    def splash(self, x, y, n=8):
        for _ in range(n):
            self._p(x, y, random.uniform(-80, 80), random.uniform(-220, -60), random.uniform(0.3, 0.6),
                    (170, 210, 235), 2, 900)

    def bubbles(self, x, y):
        self._p(x, y, random.uniform(-8, 8), -40, 0.8, (190, 220, 240), 1, -30)

    def text(self, x, y, text, color=(255, 255, 255), gloss=None, life=1.4):
        self.texts.append([x, y, text, color, life, gloss])

    def number(self, x, y, n, color=(255, 230, 200)):
        if n > 0:
            self.texts.append([x + random.uniform(-6, 6), y, str(n), color, 0.8, None])

    def update(self, dt):
        keep = []
        for p in self.parts:
            p[4] -= dt
            if p[4] <= 0:
                continue
            p[3] += p[8] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            keep.append(p)
        self.parts = keep
        for t in self.texts:
            t[1] -= 28 * dt
            t[4] -= dt
        self.texts = [t for t in self.texts if t[4] > 0]
        self.flash = max(0.0, self.flash - dt * 2)

    def draw(self, surf, ox, oy, font_small, font_tiny):
        from . import paint
        W, H = surf.get_width(), surf.get_height()
        for p in self.parts:
            x, y = p[0] - ox, p[1] - oy
            if -20 < x < W + 20 and -20 < y < H + 20:
                s = p[7]
                if p[8] < 0 and s >= 3:
                    # smoke and steam: soft puffs that swell and thin out as they rise
                    age = 1 - p[4] / max(1e-3, p[5])
                    r = int(4 + 10 * age)
                    a = int(110 * (1 - age))
                    if a > 6:
                        g = paint.glow(r, tuple((v // 24) * 24 for v in p[6]), (a // 20) * 20, 1.2)
                        surf.blit(g, (x - r, y - r))
                elif s <= 1:
                    surf.set_at((int(x), int(y)), p[6])
                else:
                    pygame.draw.circle(surf, p[6], (x, y), s * 0.75)
        for x, y, text, color, life, gloss in self.texts:
            a = min(1.0, life * 2)
            img = font_small.render(text, True, color)
            img.set_alpha(int(255 * a))
            sx, sy = int(x - ox - img.get_width() / 2), int(y - oy)
            sh = font_small.render(text, True, (0, 0, 0))
            sh.set_alpha(int(180 * a))
            surf.blit(sh, (sx + 1, sy + 1))
            surf.blit(img, (sx, sy))
            if gloss:
                g = font_tiny.render(f"({gloss})", True, (190, 205, 215))
                g.set_alpha(int(220 * a))
                surf.blit(g, (int(x - ox - g.get_width() / 2), sy + img.get_height() - 2))
