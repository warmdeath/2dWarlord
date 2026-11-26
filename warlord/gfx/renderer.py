"""Sky, sun and moon, clouds, painterly parallax mountains and the camera (the polygon world is drawn by
poly.render, which builds on this)."""
import math
import random
from collections import OrderedDict

import numpy as np
import pygame

from ..settings import TILE, CHUNK, SCREEN_W, SCREEN_H, SEA_LEVEL
from ..world.noise import fbm1, smooth_array

CPX = CHUNK * TILE


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_col(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Camera:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.shake = 0.0
        self.zoom = 1.0

    def follow(self, tx, ty, dt, world, lead=0.0, view=(SCREEN_W, SCREEN_H)):
        SW, SH = view
        gx = tx - SW / 2 + lead
        gy = ty - SH * 0.58
        k = min(1.0, dt * 6.0)
        self.x = float(self.x + (gx - self.x) * k)
        self.y = float(self.y + (gy - self.y) * k)
        self.y = max(-200, min(world.pixel_h() - SH + 120, self.y))
        self.x = max(-SW * 0.5, min(world.pixel_w() - SW * 0.5, self.x))
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 20)

    def snap(self, tx, ty, view=(SCREEN_W, SCREEN_H)):
        self.x = float(tx - view[0] / 2)
        self.y = float(ty - view[1] * 0.58)

    def offset(self):
        if self.shake > 0:
            return (int(self.x + random.uniform(-self.shake, self.shake)),
                    int(self.y + random.uniform(-self.shake, self.shake)))
        return int(self.x), int(self.y)


class Renderer:
    def __init__(self, world):
        self.world = world
        self.terrain = OrderedDict()   # LRU: most recently used at the end
        self.liquid = {}
        self.max_chunks = 120
        self._build_parallax()
        self.stars = [(random.random(), random.random() * 0.6, random.random()) for _ in range(140)]
        self.clouds = [[random.uniform(0, 4000), random.uniform(20, 240), random.uniform(80, 220),
                        random.uniform(0.6, 1.0)] for _ in range(14)]
        self.light_cache = None
        self.storm = 0.0






    # ------------------------------------------------------------------ parallax
    def _build_parallax(self):
        w = self.world
        n = w.w // 8 + 2
        xs = np.arange(n, dtype=np.float32)
        biome = [w.biome_at(i * 8) for i in range(n)]
        amp = {"abyss": 0, "edge": 30, "plains": 40, "forest": 60, "moor": 25, "hills": 90, "mountains": 230,
               "vineyard": 80, "coast": 30, "ocean": 0, "islet": 20, "snow": 160, "ashland": 50, "volcanic": 200,
               "lavasea": 10}
        a = smooth_array(np.array([amp.get(b, 40) for b in biome], dtype=np.float32), 61)
        jag = smooth_array(np.array([{"mountains": 1.0, "snow": 0.7, "volcanic": 0.8, "hills": 0.35}.get(b, 0.12)
                                     for b in biome], dtype=np.float32), 31)
        ridge = 1.0 - np.abs(fbm1(xs, 1 / 7.0, 29, 3) * 2 - 1)
        self.far = (a * (0.55 + 0.6 * fbm1(xs, 1 / 37.0, 9, 4)) + jag * ridge * 70 * (a / 230 + 0.2)).astype(float)
        self.mid = smooth_array(a, 21).astype(float) * 0.55 * (0.4 + 0.8 * fbm1(xs, 1 / 17.0, 19, 4))
        trees = {"forest": 1.0, "snow": 0.8, "moor": 0.4, "plains": 0.25, "hills": 0.35, "mountains": 0.45,
                 "vineyard": 0.15, "coast": 0.1}
        self.treeline = smooth_array(np.array([trees.get(b, 0.0) for b in biome], dtype=np.float32), 31)
        self.volcanic = smooth_array(np.array([1.0 if b in ("volcanic", "lavasea") else 0.0 for b in biome],
                                              dtype=np.float32), 61)
        ab = max(0, (w.abyss_w + 6) // 8)
        if ab > 0:
            # distant land sinks away into the abyss instead of ending in a wall
            ramp_n = 90
            ramp = np.clip((np.arange(n) - ab) / ramp_n, 0.0, 1.0) ** 0.7
            self.far = self.far * ramp - (1 - ramp) * 420
            self.mid = self.mid * ramp - (1 - ramp) * 420
            self.treeline = self.treeline * ramp
        # the same at the burning east end
        le = (w.w - w.lava_w) // 8
        if 0 < le < n:
            ramp = np.clip((le + 40 - np.arange(n)) / 60.0, 0.0, 1.0)
            self.mid = self.mid * ramp - (1 - ramp) * 300
        self.snowy = smooth_array(np.array([1.0 if b in ("snow", "mountains") else 0.0 for b in biome],
                                           dtype=np.float32), 61)

    def sky_colors(self, env):
        sun = env.sun_height()  # -1..1
        night_t, night_b = (8, 10, 26), (24, 28, 52)
        day_t, day_b = (70, 130, 205), (176, 206, 232)
        dusk_t, dusk_b = (60, 56, 110), (236, 132, 84)
        if sun > 0.25:
            top, bot = day_t, day_b
        elif sun > 0.0:
            t = sun / 0.25
            top, bot = lerp_col(dusk_t, day_t, t), lerp_col(dusk_b, day_b, t)
        elif sun > -0.2:
            t = (sun + 0.2) / 0.2
            top, bot = lerp_col(night_t, dusk_t, t), lerp_col(night_b, dusk_b, t)
        else:
            top, bot = night_t, night_b
        g = env.gloom()
        grey = (90, 94, 100)
        top = lerp_col(top, lerp_col(grey, night_t, max(0, -sun)), g * 0.8)
        bot = lerp_col(bot, lerp_col((120, 124, 128), night_b, max(0, -sun)), g * 0.8)
        if env.biome_hint in ("volcanic", "lavasea"):
            bot = lerp_col(bot, (150, 60, 30), 0.45)
        if env.biome_hint == "abyss" or env.biome_hint == "edge":
            top = lerp_col(top, (40, 20, 60), 0.35)
        return top, bot

    # ------------------------------------------------------------------ painted sky
    def _cloud_masks(self):
        """A handful of cloud shapes, each as two alpha masks: the shaded underside and the sunlit top."""
        cm = getattr(self, "_cmasks", None)
        if cm is not None:
            return cm
        from . import paint
        rng = random.Random(77)
        out = []
        for i in range(9):
            W, H = rng.randint(220, 380), rng.randint(90, 140)
            shadow = pygame.Surface((W, H), pygame.SRCALPHA)
            light = pygame.Surface((W, H), pygame.SRCALPHA)
            puffs = []
            n = rng.randint(16, 26)
            for k in range(n):
                u = rng.random()
                bulge = math.sin(u * math.pi)
                r = H * (0.14 + 0.2 * bulge) * rng.uniform(0.75, 1.2)
                x = W * (0.12 + 0.76 * u)
                y = H * 0.74 - r * 0.6 - bulge * H * 0.22 * rng.uniform(0.3, 1.0)
                puffs.append((x, y, r))
            for x, y, r in puffs:
                g = paint.glow(int(r * 1.1), (255, 255, 255), 255, 0.35)
                shadow.blit(g, (x - g.get_width() / 2, y - g.get_height() / 2), special_flags=pygame.BLEND_RGBA_MAX)
            for x, y, r in puffs:
                g = paint.glow(int(r * 0.9), (255, 255, 255), 255, 0.5)
                light.blit(g, (x - g.get_width() / 2 - r * 0.15, y - g.get_height() / 2 - r * 0.28),
                           special_flags=pygame.BLEND_RGBA_MAX)
            # flat-ish bottoms
            cut = pygame.Surface((W, H), pygame.SRCALPHA)
            cut.fill((255, 255, 255, 255))
            for yy in range(int(H * 0.72), H):
                a = max(0, min(255, 255 - int((yy - H * 0.72) * 22)))
                pygame.draw.line(cut, (255, 255, 255, a), (0, yy), (W, yy))
            shadow.blit(cut, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            light.blit(cut, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            out.append((shadow, light))
        self._cmasks = out
        self._ccache = {}
        return out

    def _cloud(self, i, lit, dark, alpha):
        self._cloud_masks()
        key = (i, lit, dark, alpha)
        c = self._ccache.get(key)
        if c is None:
            sh, li = self._cloud_masks()[i]
            c = pygame.Surface(sh.get_size(), pygame.SRCALPHA)
            a = sh.copy()
            a.fill((*dark, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            c.blit(a, (0, 0))
            b = li.copy()
            b.fill((*lit, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            c.blit(b, (0, 0))
            if len(self._ccache) > 160:
                self._ccache.clear()
            self._ccache[key] = c
        return c

    def draw_sky(self, surf, env, cam):
        from . import paint
        SW, SH = surf.get_size()
        top, bot = self.sky_colors(env)
        sun = env.sun_height()
        ang = env.day_fraction() * math.tau - math.pi / 2
        cx, cy = SW / 2, SH * 0.95
        rx, ry = SW * 0.48, SH * 0.85
        sx, sy = cx - math.cos(ang) * rx, cy - math.sin(ang) * ry
        midc = lerp_col(top, bot, 0.55)
        key = (top, bot, SW, SH)
        if self.light_cache is None or self.light_cache[0] != key:
            g = pygame.Surface((1, 96))
            for i in range(96):
                t = i / 95
                c = lerp_col(top, midc, min(1, t / 0.6)) if t < 0.6 else lerp_col(midc, bot, (t - 0.6) / 0.4)
                g.set_at((0, i), c)
            self.light_cache = (key, pygame.transform.smoothscale(g, (SW, SH)))
        surf.blit(self.light_cache[1], (0, 0))
        # stars
        if sun < 0.05:
            a = min(1.0, (0.05 - sun) * 4) * (1 - env.gloom())
            for sx_, sy_, tw in self.stars:
                b = int(160 * a * (0.6 + 0.4 * math.sin(env.time * 2 + tw * 20)))
                if b > 10:
                    surf.set_at((int(sx_ * SW), int(sy_ * SH)), (b, b, min(255, b + 30)))
        # the sun: a wide warm haze, a bright halo, the disc
        warmth = max(0.0, 1.0 - abs(sun) * 3.2)             # low sun = warm
        if sy < SH + 120:
            gl = 1 - env.gloom() * 0.8
            hc = lerp_col((255, 246, 220), (255, 170, 90), warmth)
            haze = paint.add_glow(380, tuple((v // 16) * 16 for v in hc), round(0.2 * gl, 1), 2.2)
            surf.blit(haze, (sx - 380, sy - 380), special_flags=pygame.BLEND_RGB_ADD)
            halo = paint.add_glow(70, (255, 236, 196), round(0.3 * gl, 1), 2.6)
            surf.blit(halo, (sx - 90, sy - 90), special_flags=pygame.BLEND_RGB_ADD)
            if gl > 0.5:
                pygame.draw.circle(surf, lerp_col((255, 248, 226), (255, 196, 120), warmth), (sx, sy), 13)
        mx, my = cx + math.cos(ang) * rx, cy + math.sin(ang) * ry
        if my < SH:
            mg = paint.add_glow(60, (180, 190, 230), 0.25, 2.0)
            surf.blit(mg, (mx - 60, my - 60), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(surf, (230, 230, 238), (mx, my), 12)
            pygame.draw.circle(surf, (200, 200, 212), (mx - 3, my + 2), 3)
            pygame.draw.circle(surf, (206, 206, 218), (mx + 4, my - 3), 2)
        # clouds: shaded undersides, tops lit by the sun (golden when it is low)
        cover = env.cloud_cover()
        night = max(0.0, -sun)
        lit = lerp_col((255, 252, 246), (255, 196, 140), warmth * 0.9)
        lit = lerp_col(lit, (150, 152, 160), env.gloom() * 0.7)
        lit = lerp_col(lit, (70, 76, 100), min(1, night * 2.5))
        dark = lerp_col(lerp_col(bot, (150, 156, 176), 0.5), (196, 120, 120), warmth * 0.4)
        dark = lerp_col(dark, (90, 92, 100), env.gloom() * 0.8)
        dark = lerp_col(dark, (24, 28, 44), min(1, night * 2.5))
        q = lambda c: tuple((v // 8) * 8 for v in c)
        alpha = int(150 + 100 * min(1.0, cover + 0.3))
        self._cloud_masks()
        for k, c in enumerate(self.clouds):
            c[0] += env.wind * 18 * env.dt_hint * (0.6 + c[3] * 0.6)
            x = (c[0] - cam.x * 0.04 * c[3]) % 4200 - 400
            if x > SW + 300 or (k > 3 + cover * 10):
                continue
            img = self._cloud(k % 9, q(lit), q(dark), (alpha // 16) * 16)
            sc = c[2] / 160 * (0.7 + cover * 0.6)
            if abs(sc - 1) > 0.05:
                key = ("s", k, round(sc, 1), q(lit), q(dark), (alpha // 16) * 16)
                im2 = self._ccache.get(key)
                if im2 is None:
                    im2 = pygame.transform.smoothscale_by(img, round(sc, 1))
                    self._ccache[key] = im2
                img = im2
            surf.blit(img, (x, c[1] - img.get_height() * 0.5))

    def draw_parallax(self, surf, env, cam):
        """Distance painted in layers of haze: far blue mountains, rolling hills, forested ridges and a near
        line of tree crowns, each paler and bluer the farther it is, with mist pooling at their feet."""
        from . import paint
        SW, SH = surf.get_size()
        top, bot = self.sky_colors(env)
        sun = env.sun_height()
        night = max(0.0, min(1.0, -sun * 3 + 0.3)) if sun < 0.1 else 0.0
        horizon = SH * 0.50 - (cam.y - (SEA_LEVEL * TILE - SH * 0.6)) * 0.08
        haze = lerp_col(bot, (200, 210, 225), 0.2)
        cz = cam.y - SEA_LEVEL * TILE

        def layer_pts(prof, f, base_y, hscale, step=6, jag=0.0, seed=0):
            pts = [(0, SH)]
            for sx in range(0, SW + step, step):
                wx = (cam.x + SW / 2 + (sx - SW / 2) / f) / TILE / 8
                i = int(max(0, min(len(prof) - 2, wx)))
                fr = wx - int(wx)
                h = prof[i] * (1 - fr) + prof[i + 1] * fr
                if jag:
                    h += jag * math.sin(wx * 3.1 + seed) * math.sin(wx * 7.3 + seed * 2)
                pts.append((sx, float(base_y - h * hscale)))
            pts.append((SW, SH))
            return pts

        def mist(base_y, depth, col, a):
            if base_y > SH:
                return
            g = paint.vgrad(SW, int(depth), col, col, 0, a)
            surf.blit(g, (0, int(base_y - depth)))
            if base_y < SH:
                pygame.draw.rect(surf, col, (0, int(base_y), SW, SH - int(base_y))) if a >= 250 else None
        layers = [
            # f, profile, colour, y offset, height scale, ridge jaggedness
            (0.08, self.far, lerp_col(lerp_col(bot, (96, 112, 150), 0.38), haze, 0.15), -6, 1.15, 2.5),
            (0.16, self.mid, lerp_col(bot, (84, 104, 118), 0.5), 12, 1.0, 1.5),
            (0.26, self.mid * 0.7 + self.far * 0.15, lerp_col(bot, (60, 86, 82), 0.62), 30, 0.9, 1.0),
        ]
        for li, (f, prof, col, yoff, hscale, jag) in enumerate(layers):
            col = lerp_col(col, (14, 16, 26), night * 0.85)
            base_y = horizon + yoff + cz * (0.05 * f)
            pts = layer_pts(prof, f, base_y, hscale, jag=jag, seed=li * 5)
            pygame.draw.polygon(surf, col, pts)
            # a sunlit rim along the ridge, toward the sun's side
            rim = lerp_col(col, lerp_col(bot, (255, 236, 200), 0.5), 0.12 * (1 - night))
            pygame.draw.aalines(surf, rim, False, pts[1:-1])
            if li == 0:
                snowc = lerp_col((236, 240, 248), col, 0.25 + night * 0.7)
                for k in range(1, len(pts) - 2):
                    sx, sy = pts[k]
                    sx2, sy2 = pts[k + 1]
                    i = int(max(0, min(len(prof) - 1, (cam.x + SW / 2 + (sx - SW / 2) / f) / TILE / 8)))
                    hgt = base_y - sy
                    if self.snowy[i] > 0.5 and hgt > 150:
                        dd = min(26, (hgt - 150) * 0.4 + 4)
                        pygame.draw.polygon(surf, snowc, [(sx, sy), (sx2, sy2), (sx2, sy2 + dd * 0.8), (sx, sy + dd)])
                    if self.volcanic[i] > 0.5 and hgt > 170 and k % 7 == 0:
                        pygame.draw.circle(surf, (255, 110, 40), (int(sx), int(sy) + 2), 3)
            if li == 2:
                self._ridge_trees(surf, cam, f, prof, base_y, hscale, col, 0.55, 14)
            hz = lerp_col(haze, (14, 16, 26), night * 0.85)
            mist(base_y + 30, 70 + li * 20, hz, 150 - li * 25)
        # settlement silhouettes on the mid layer
        f = 0.26
        for s in self.world.settlements:
            if s["type"] not in ("castle", "capital", "city", "robber", "town", "monastery"):
                continue
            wxp = (s["x0"] + s["x1"]) / 2 * TILE
            sx = SW / 2 + (wxp - cam.x - SW / 2) * f
            if -200 < sx < SW + 200 and abs(wxp - cam.x - SW / 2) > SW * 0.6:
                base_y = horizon + 30 + cz * (0.05 * f)
                i = int(max(0, min(len(self.mid) - 1, s["x0"] / 8)))
                by = base_y - (self.mid[i] * 0.7 + self.far[i] * 0.15) * 0.9
                c = lerp_col(lerp_col(bot, (52, 66, 74), 0.66), (14, 16, 26), night * 0.85)
                self._castle_silhouette(surf, sx, by, c, s["type"])
        # the near line of tree crowns
        f = 0.5
        col = lerp_col(lerp_col(bot, (34, 56, 46), 0.78), (10, 12, 20), night * 0.85)
        base_y = horizon + 44 + cz * 0.03
        band = [(-40, SH)]
        for sx in range(-40, SW + 60, 20):
            i = int(max(0, min(len(self.treeline) - 1, (cam.x + SW / 2 + (sx - SW / 2) / f) / TILE / 8)))
            tl = float(self.treeline[i])
            band.append((sx, base_y - 6 + max(0.0, (0.16 - tl) / 0.16) * 90))
        band.append((SW + 60, SH))
        pygame.draw.polygon(surf, col, band)
        self._ridge_trees(surf, cam, f, None, base_y, 1.0, col, 1.0, 22)
        hz = lerp_col(haze, (14, 16, 26), night * 0.85)
        mist(base_y + 40, 60, hz, 90)

    def _ridge_trees(self, surf, cam, f, prof, base_y, hscale, col, size, spacing):
        """Painted tree silhouettes standing on a ridge: round broadleaf crowns and pointed firs, lit a little on
        the sun's side."""
        SW, SH = surf.get_size()
        shift = (cam.x + SW / 2) * f - SW / 2
        lit = lerp_col(col, (200, 210, 190), 0.12)
        for k in range(int((shift - 40) // spacing), int((shift + SW + 40) // spacing) + 1):
            sxx = k * spacing - shift + ((k * 7919) % 9 - 4)
            wx = (k * spacing / f) / TILE / 8
            i = int(max(0, min(len(self.treeline) - 1, wx)))
            if self.treeline[i] < 0.08 or self.treeline[i] < ((k * 2654435761) % 100) / 100.0:
                continue
            if prof is not None:
                j = int(max(0, min(len(prof) - 1, wx)))
                gy = base_y - prof[j] * hscale + 4
            else:
                gy = base_y
            hh = (36 + (k * 7919) % 46) * size
            if (k * 31) % 3 == 0:
                # a fir: stacked drooping tiers
                for t in range(4):
                    u = t / 4
                    wdt = hh * 0.3 * (1 - u * 0.7)
                    yb = gy - hh * (0.15 + 0.7 * u)
                    pygame.draw.polygon(surf, col, [(sxx - wdt, yb + 3), (sxx, yb - hh * 0.3), (sxx + wdt, yb + 3)])
                    pygame.draw.line(surf, lit, (sxx - wdt * 0.9, yb + 2), (sxx, yb - hh * 0.28), 1)
                pygame.draw.rect(surf, col, (sxx - 1, gy - hh * 0.2, 3, hh * 0.2 + 4))
            else:
                r = hh * 0.36
                cy = gy - hh * 0.6
                rng = random.Random(k)
                pygame.draw.rect(surf, col, (sxx - 2, cy, 4, gy - cy + 4))
                for q in range(5):
                    a = rng.uniform(0, math.tau)
                    d = rng.uniform(0, r * 0.6)
                    pygame.draw.circle(surf, col, (sxx + math.cos(a) * d, cy + math.sin(a) * d * 0.7),
                                       r * rng.uniform(0.55, 0.8))
                pygame.draw.circle(surf, lit, (sxx - r * 0.35, cy - r * 0.45), r * 0.35)
                pygame.draw.circle(surf, col, (sxx - r * 0.2, cy - r * 0.3), r * 0.36)

    @staticmethod
    def _castle_silhouette(surf, x, y, c, kind):
        if kind == "monastery":
            pygame.draw.rect(surf, c, (x - 30, y - 20, 60, 20))
            pygame.draw.rect(surf, c, (x - 30, y - 50, 12, 30))
            pygame.draw.polygon(surf, c, [(x - 32, y - 50), (x - 24, y - 70), (x - 16, y - 50)])
            return
        w = 120 if kind in ("capital", "city") else 80
        pygame.draw.rect(surf, c, (x - w / 2, y - 26, w, 26))
        for i in range(-2, 3):
            tx = x + i * w / 5
            th = 50 + (abs(i) % 2) * 18 + (30 if i == 0 else 0)
            pygame.draw.rect(surf, c, (tx - 8, y - th, 16, th))
            pygame.draw.polygon(surf, c, [(tx - 10, y - th), (tx, y - th - 18), (tx + 10, y - th)])
        for k in range(int(w / 8)):
            pygame.draw.rect(surf, c, (x - w / 2 + k * 8, y - 30, 4, 4))




