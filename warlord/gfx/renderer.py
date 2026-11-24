"""World renderer: cached terrain/liquid chunks, painterly parallax sky, soft tile lighting."""
import math
import random
from collections import OrderedDict

import numpy as np
import pygame

from ..settings import TILE, CHUNK, SCREEN_W, SCREEN_H, SEA_LEVEL
from ..world import tiles as T
from ..world.noise import fbm1, smooth_array
from . import tileart

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
        self.x += (gx - self.x) * k
        self.y += (gy - self.y) * k
        self.y = max(-200, min(world.pixel_h() - SH + 120, self.y))
        self.x = max(-SW * 0.5, min(world.pixel_w() - SW * 0.5, self.x))
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 20)

    def snap(self, tx, ty, view=(SCREEN_W, SCREEN_H)):
        self.x = tx - view[0] / 2
        self.y = ty - view[1] * 0.58

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

    # ------------------------------------------------------------------ chunk caches
    def invalidate(self):
        w = self.world
        for c in w.dirty:
            self.terrain.pop(c, None)
            self.liquid.pop(c, None)
        w.dirty.clear()
        for c in w.liquid_dirty:
            self.liquid.pop(c, None)
        w.liquid_dirty.clear()

    def _evict(self):
        while len(self.terrain) > self.max_chunks:
            c, _ = self.terrain.popitem(last=False)
            self.liquid.pop(c, None)

    def _render_terrain(self, cx, cy):
        w = self.world
        surf = pygame.Surface((CPX, CPX), pygame.SRCALPHA)
        x0, y0 = cx * CHUNK, cy * CHUNK
        if x0 >= w.w or y0 >= w.h or x0 + CHUNK <= 0 or y0 + CHUNK <= 0:
            return surf
        # padded window for neighbour lookups
        px0, py0 = max(0, x0 - 1), max(0, y0 - 1)
        px1, py1 = min(w.w, x0 + CHUNK + 1), min(w.h, y0 + CHUNK + 1)
        fgp = np.zeros((CHUNK + 2, CHUNK + 2), dtype=np.uint8)
        fgp[px0 - (x0 - 1):px1 - (x0 - 1), py0 - (y0 - 1):py1 - (y0 - 1)] = w.fg[px0:px1, py0:py1]
        solid = T.SOLID[fgp]
        bgw = np.zeros((CHUNK, CHUNK), dtype=np.uint8)
        ex, ey = min(w.w, x0 + CHUNK), min(w.h, y0 + CHUNK)
        bgw[:ex - x0, :ey - y0] = w.bg[x0:ex, y0:ey]
        fg = fgp[1:-1, 1:-1]
        s = solid
        up = ~s[1:-1, :-2]
        dn = ~s[1:-1, 2:]
        lf = ~s[:-2, 1:-1]
        rt = ~s[2:, 1:-1]
        mask = (up & lf) * 1 + (up & rt) * 2 + (dn & lf) * 4 + (dn & rt) * 8
        blit = surf.blit
        # background walls
        nz = np.argwhere(bgw > 0)
        for lx, ly in nz:
            if not s[lx + 1, ly + 1] or T.TILES[fg[lx, ly]].deco:
                b = int(bgw[lx, ly])
                blit(tileart.bg_surface(b, int(lx * 7 + ly * 3 + x0) % 2), (lx * TILE, ly * TILE))
        nz = np.argwhere(fg > 0)
        for lx, ly in nz:
            tid = int(fg[lx, ly])
            t = T.TILES[tid]
            var = int(((lx + x0) * 73856093 ^ (ly + y0) * 19349663) & 3)
            px, py = lx * TILE, ly * TILE
            if t.deco or t.style in ("vine", "sapling"):
                img = tileart.tile_surface(tid, var, 0)
                blit(img, (px, py + TILE - img.get_height()))
                continue
            if tid == T.LOG.id and fgp[lx + 1, ly] != tid and fgp[lx + 1, ly + 2] != tid:
                blit(tileart.branch_surface(var), (px, py))   # a horizontal limb, not a trunk
                continue
            m = int(mask[lx, ly]) if t.natural else 0
            blit(tileart.tile_surface(tid, var, m), (px, py))
            if t.style == "grass" and up[lx, ly]:
                blit(tileart.grass_cap(tid, var), (px, py - 3))
        if len(nz) and cy * CHUNK > 0:
            pass
        return surf

    def _render_liquid(self, cx, cy):
        w = self.world
        x0, y0 = cx * CHUNK, cy * CHUNK
        if x0 >= w.w or y0 >= w.h or x0 + CHUNK <= 0 or y0 + CHUNK <= 0:
            return None
        ex, ey = min(w.w, x0 + CHUNK), min(w.h, y0 + CHUNK)
        liq = w.liq[x0:ex, y0:ey]
        if not liq.any():
            return None
        lava = w.lava[x0:ex, y0:ey]
        above = np.zeros_like(liq)
        if y0 > 0:
            above[:, 0] = w.liq[x0:ex, y0 - 1]
        above[:, 1:] = liq[:, :-1]
        surf = pygame.Surface((CPX, CPX), pygame.SRCALPHA)
        for lx, ly in np.argwhere(liq > 0):
            amt = int(liq[lx, ly])
            full = above[lx, ly] > 0
            h = TILE if full else max(2, amt * TILE // 8)
            px, py = lx * TILE, ly * TILE + TILE - h
            if lava[lx, ly]:
                col = (255, 96 + (ly * 7 + lx * 3) % 30, 24, 235)
            else:
                depth = ly + y0 - SEA_LEVEL
                d = max(0.0, min(1.0, depth / 70.0))
                col = (int(48 - 30 * d), int(104 - 60 * d), int(150 - 70 * d), int(120 + 90 * d))
            surf.fill(col, (px, py, TILE, h))
        return surf

    def get_chunk(self, cx, cy):
        key = (cx, cy)
        t = self.terrain.get(key)
        if t is None:
            t = self._render_terrain(cx, cy)
            self.terrain[key] = t
            self._evict()
        else:
            self.terrain.move_to_end(key)
        if key not in self.liquid:
            self.liquid[key] = self._render_liquid(cx, cy)
        return t, self.liquid.get(key)

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

    def draw_sky(self, surf, env, cam):
        SW, SH = surf.get_size()
        top, bot = self.sky_colors(env)
        key = (top, bot, SW, SH)
        if self.light_cache is None or self.light_cache[0] != key:
            g = pygame.Surface((1, 64))
            for i in range(64):
                g.set_at((0, i), lerp_col(top, bot, i / 63))
            self.light_cache = (key, pygame.transform.smoothscale(g, (SW, SH)))
        surf.blit(self.light_cache[1], (0, 0))
        sun = env.sun_height()
        # stars
        if sun < 0.05:
            a = min(1.0, (0.05 - sun) * 4) * (1 - env.gloom())
            for sx, sy, tw in self.stars:
                b = int(160 * a * (0.6 + 0.4 * math.sin(env.time * 2 + tw * 20)))
                if b > 10:
                    surf.set_at((int(sx * SW), int(sy * SH)), (b, b, min(255, b + 30)))
        # sun & moon on an arc
        ang = env.day_fraction() * math.tau - math.pi / 2
        cx, cy = SW / 2, SH * 0.95
        rx, ry = SW * 0.48, SH * 0.85
        sx, sy = cx - math.cos(ang) * rx, cy - math.sin(ang) * ry
        if sy < SH:
            glow = pygame.Surface((160, 160), pygame.SRCALPHA)
            for r in range(70, 10, -10):
                pygame.draw.circle(glow, (255, 230, 170, 12), (80, 80), r)
            surf.blit(glow, (sx - 80, sy - 80))
            pygame.draw.circle(surf, (255, 238, 190), (int(sx), int(sy)), 18)
        mx, my = cx + math.cos(ang) * rx, cy + math.sin(ang) * ry
        if my < SH:
            pygame.draw.circle(surf, (226, 226, 236), (int(mx), int(my)), 13)
            pygame.draw.circle(surf, top, (int(mx) + 5, int(my) - 3), 11)
        # clouds
        cover = env.cloud_cover()
        ccol = lerp_col((250, 248, 244), (110, 112, 118), env.gloom())
        ccol = lerp_col(ccol, (40, 44, 60), max(0.0, -sun) * 0.9)
        for c in self.clouds:
            c[0] += env.wind * 18 * env.dt_hint
            x = (c[0] - cam.x * 0.05) % 4200 - 400
            if x > SW + 300:
                continue
            n = 1 + int(cover * 5)
            for k in range(n):
                r = c[2] * (0.35 + 0.12 * k) * (0.6 + cover * 0.6)
                pygame.draw.ellipse(surf, ccol, (x + k * c[2] * 0.33, c[1] + (k % 2) * 10 - r * 0.3, r * 1.6, r * 0.7))

    def draw_parallax(self, surf, env, cam):
        SW, SH = surf.get_size()
        top, bot = self.sky_colors(env)
        sun = env.sun_height()
        night = max(0.0, min(1.0, -sun * 3 + 0.3)) if sun < 0.1 else 0.0
        horizon = SH * 0.50 - (cam.y - (SEA_LEVEL * TILE - SH * 0.6)) * 0.08
        layers = [
            (0.12, self.far, lerp_col(bot, (70, 80, 110), 0.45), 0.0, 1.0),
            (0.30, self.mid, lerp_col(bot, (46, 60, 70), 0.65), 22, 0.8),
        ]
        for f, prof, col, yoff, hscale in layers:
            col = lerp_col(col, (14, 16, 26), night * 0.85)
            pts = [(0, SH)]
            step = 8
            base_y = horizon + yoff + (cam.y - SEA_LEVEL * TILE) * (0.05 * f)
            for sx in range(0, SW + step, step):
                wx = (cam.x + SW / 2 + (sx - SW / 2) / f) / TILE / 8
                i = int(max(0, min(len(prof) - 2, wx)))
                fr = wx - int(wx)
                h = prof[i] * (1 - fr) + prof[i + 1] * fr
                pts.append((sx, float(base_y - h * hscale)))
            pts.append((SW, SH))
            pygame.draw.polygon(surf, col, pts)
            if f == 0.12:
                # snow caps & volcano glow on the far range
                snowc = lerp_col((232, 236, 244), col, 0.15 + night * 0.8)
                for k in range(1, len(pts) - 2):
                    sx, sy = pts[k]
                    sx2, sy2 = pts[k + 1]
                    i = int(max(0, min(len(prof) - 1, (cam.x + SW / 2 + (sx - SW / 2) / f) / TILE / 8)))
                    hgt = base_y - sy
                    if self.snowy[i] > 0.5 and hgt > 150:
                        d = min(22, (hgt - 150) * 0.4 + 4)
                        pygame.draw.polygon(surf, snowc, [(sx, sy), (sx2, sy2), (sx2, sy2 + d), (sx, sy + d)])
                    if self.volcanic[i] > 0.5 and hgt > 170 and k % 7 == 0:
                        pygame.draw.circle(surf, (255, 110, 40), (int(sx), int(sy) + 2), 3)
        # settlement silhouettes on the mid layer
        f = 0.30
        for s in self.world.settlements:
            if s["type"] not in ("castle", "capital", "city", "robber", "town", "monastery"):
                continue
            wxp = (s["x0"] + s["x1"]) / 2 * TILE
            sx = SW / 2 + (wxp - cam.x - SW / 2) * f
            if -200 < sx < SW + 200 and abs(wxp - cam.x - SW / 2) > SW * 0.6:
                base_y = horizon + 22 + (cam.y - SEA_LEVEL * TILE) * (0.05 * f)
                i = int(max(0, min(len(self.mid) - 1, s["x0"] / 8)))
                by = base_y - self.mid[i] * 0.8
                c = lerp_col(lerp_col(bot, (40, 52, 62), 0.7), (14, 16, 26), night * 0.85)
                self._castle_silhouette(surf, sx, by, c, s["type"])
        # near treeline
        f = 0.5
        col = lerp_col(lerp_col(bot, (30, 46, 44), 0.8), (10, 12, 20), night * 0.85)
        base_y = horizon + 44 + (cam.y - SEA_LEVEL * TILE) * 0.03
        band = [(-40, SH)]
        for sx in range(-40, SW + 60, 20):
            i = int(max(0, min(len(self.treeline) - 1, (cam.x + SW / 2 + (sx - SW / 2) / f) / TILE / 8)))
            band.append((sx, base_y - 4 if self.treeline[i] > 0.08 else base_y + 400))
        band.append((SW + 60, SH))
        pygame.draw.polygon(surf, col, band)
        shift = (cam.x + SW / 2) * f - SW / 2
        for k in range(int((shift - 40) // 22), int((shift + SW + 40) // 22) + 1):
            sxx = k * 22 - shift
            wx = (k * 22 / f) / TILE / 8
            i = int(max(0, min(len(self.treeline) - 1, wx)))
            if self.treeline[i] < 0.08 or self.treeline[i] < ((k * 2654435761) % 100) / 100.0:
                continue
            hh = 40 + (k * 7919) % 50
            if (k * 31) % 3 == 0:
                pygame.draw.polygon(surf, col, [(sxx - 12, base_y), (sxx, base_y - hh), (sxx + 12, base_y)])
            else:
                pygame.draw.circle(surf, col, (int(sxx), int(base_y - hh * 0.6)), int(hh * 0.4))
                pygame.draw.rect(surf, col, (sxx - 2, base_y - hh * 0.5, 4, hh * 0.5))

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

    # ------------------------------------------------------------------ world layers
    def draw_terrain(self, surf, cam):
        SW, SH = surf.get_size()
        self.invalidate()
        ox, oy = cam.offset()
        cx0, cy0 = ox // CPX, oy // CPX
        cx1, cy1 = (ox + SW) // CPX, (oy + SH) // CPX
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                t, _ = self.get_chunk(cx, cy)
                surf.blit(t, (cx * CPX - ox, cy * CPX - oy))

    def draw_liquids(self, surf, cam, time):
        SW, SH = surf.get_size()
        ox, oy = cam.offset()
        cx0, cy0 = ox // CPX, oy // CPX
        cx1, cy1 = (ox + SW) // CPX, (oy + SH) // CPX
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                _, l = self.get_chunk(cx, cy)
                if l is not None:
                    surf.blit(l, (cx * CPX - ox, cy * CPX - oy))
        # animated surface highlights
        w = self.world
        tx0 = max(0, ox // TILE)
        tx1 = min(w.w, (ox + SW) // TILE + 1)
        ty0 = max(1, oy // TILE)
        ty1 = min(w.h, (oy + SH) // TILE + 1)
        if tx1 <= tx0 or ty1 <= ty0:
            return
        liq = w.liq[tx0:tx1, ty0 - 1:ty1]
        top = (liq[:, 1:] > 0) & (liq[:, :-1] == 0)
        for lx, ly in np.argwhere(top):
            x = tx0 + lx
            y = ty0 + ly
            amt = int(w.liq[x, y])
            py = y * TILE + TILE - amt * TILE // 8 - oy
            px = x * TILE - ox
            wave = math.sin(time * 2.2 + x * 0.55) * (1.5 + 5 * self.storm) + \
                math.sin(time * 1.3 + x * 0.17) * 6 * self.storm
            if w.lava[x, y]:
                pygame.draw.line(surf, (255, 200, 90), (px, py + wave), (px + TILE, py - wave), 2)
            else:
                pygame.draw.line(surf, (170, 210, 230), (px, py + wave), (px + TILE, py - wave), 1)

    # ------------------------------------------------------------------ lighting
    def draw_lighting(self, surf, cam, env, dyn_lights):
        SW, SH = surf.get_size()
        w = self.world
        ox, oy = cam.offset()
        m = 10
        tx0 = ox // TILE - m
        ty0 = oy // TILE - m
        tw = SW // TILE + 2 * m + 2
        th = SH // TILE + 2 * m + 2
        fg = np.zeros((tw, th), dtype=np.uint8)
        bg = np.zeros((tw, th), dtype=np.uint8)
        liq = np.zeros((tw, th), dtype=np.uint8)
        lava = np.zeros((tw, th), dtype=bool)
        ax0, ay0 = max(0, tx0), max(0, ty0)
        ax1, ay1 = min(w.w, tx0 + tw), min(w.h, ty0 + th)
        if ax1 > ax0 and ay1 > ay0:
            sl = (slice(ax0 - tx0, ax1 - tx0), slice(ay0 - ty0, ay1 - ty0))
            fg[sl] = w.fg[ax0:ax1, ay0:ay1]
            bg[sl] = w.bg[ax0:ax1, ay0:ay1]
            liq[sl] = w.liq[ax0:ax1, ay0:ay1]
            lava[sl] = w.lava[ax0:ax1, ay0:ay1]
        # outside the world below = dark, above = sky
        if ty0 + th > w.h:
            fg[:, max(0, w.h - ty0):] = T.STONE.id
        solid = T.OPAQUE[fg]
        sky_open = (~solid) & ((bg == 0) | (bg == T.BG_WINDOW))
        day = env.daylight()
        sun = np.where(sky_open, day, 0.0).astype(np.float32)
        # soft daylight that seeps a few metres into the earth (no harsh black line under the grass)
        cols = np.arange(tx0, tx0 + tw).clip(0, w.w - 1)
        surf_rows = w.surface[cols].astype(np.float32)[:, None]
        depth = (np.arange(ty0, ty0 + th, dtype=np.float32)[None, :] - surf_rows)
        seep = np.clip(1.0 - depth / 22.0, 0.0, 1.0) * 0.42 * day
        sun = np.maximum(sun, np.where(depth > 0, seep, 0.0).astype(np.float32))
        # water absorbs sunlight with depth
        sun = np.where(liq > 0, sun * 0.8, sun)
        fire = T.LIGHT[fg].copy()
        fire = np.maximum(fire, np.where(lava & (liq > 0), 1.0, 0.0).astype(np.float32))
        for (lx, ly, s) in dyn_lights:
            i, j = int(lx // TILE) - tx0, int(ly // TILE) - ty0
            if 0 <= i < tw and 0 <= j < th:
                fire[i, j] = max(fire[i, j], s)
        fall_air = np.where(solid, np.where(T.BUILT[fg], 0.05, 0.17), 0.05).astype(np.float32)
        fall_air = np.where((liq > 0) & ~solid, 0.085, fall_air)
        fall_fire = np.where(solid, 0.25, 0.075).astype(np.float32)
        for arr, fall in ((sun, fall_air), (fire, fall_fire)):
            for _ in range(11):
                n = arr.copy()
                n[1:, :] = np.maximum(n[1:, :], arr[:-1, :] - fall[1:, :])
                n[:-1, :] = np.maximum(n[:-1, :], arr[1:, :] - fall[:-1, :])
                n[:, 1:] = np.maximum(n[:, 1:], arr[:, :-1] - fall[:, 1:])
                n[:, :-1] = np.maximum(n[:, :-1], arr[:, 1:] - fall[:, :-1])
                arr[:] = n
        # let the first solid layer catch the light of its open neighbour (lit roofs and ground faces)
        for arr in (sun, fire):
            d = arr.copy()
            d[1:, :] = np.maximum(d[1:, :], arr[:-1, :] * 0.92)
            d[:-1, :] = np.maximum(d[:-1, :], arr[1:, :] * 0.92)
            d[:, 1:] = np.maximum(d[:, 1:], arr[:, :-1] * 0.92)
            d[:, :-1] = np.maximum(d[:, :-1], arr[:, 1:] * 0.92)
            arr[:] = np.where(solid, d, arr)
        skyc = np.array(env.ambient_color(), dtype=np.float32) / 255.0
        firec = np.array((1.0, 0.78, 0.5), dtype=np.float32)
        rgb = sun[..., None] * skyc[None, None, :] + fire[..., None] * firec[None, None, :]
        rgb = np.clip(rgb + 0.035, 0, 1) * 255
        small = pygame.surfarray.make_surface(rgb.astype(np.uint8))
        big = pygame.transform.smoothscale(small, (tw * TILE, th * TILE))
        surf.blit(big, (tx0 * TILE - ox + TILE // 2, ty0 * TILE - oy + TILE // 2), special_flags=pygame.BLEND_MULT)
