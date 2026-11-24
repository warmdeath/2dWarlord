"""Procedural tile art. Every tile gets 4 noise variants x 16 corner-rounding masks.

Natural tiles whose two orthogonal neighbours are open get a rounded corner, which is what
makes the tile world read as soft hills instead of Minecraft cubes.
"""
import math
import random

import pygame

from ..settings import TILE
from ..world import tiles as T

VARIANTS = 4
_cache = {}
_bg_cache = {}
_cap_cache = {}


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _noise_fill(s, base, rng, amt=0.12, dots=36):
    s.fill(base)
    for _ in range(dots):
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        f = 1 + rng.uniform(-amt, amt)
        s.set_at((x, y), _shade(base, f))


def _draw_base(t, rng, var):
    s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    c = t.color
    st = t.style
    if st in ("noise", "grass"):
        _noise_fill(s, c, rng)
        for _ in range(3):
            x, y = rng.randrange(1, TILE - 2), rng.randrange(1, TILE - 2)
            pygame.draw.rect(s, _shade(c, 0.85), (x, y, 2, 1))
    elif st == "gravel":
        _noise_fill(s, c, rng, 0.2, 60)
        for _ in range(6):
            pygame.draw.circle(s, _shade(c, rng.uniform(0.8, 1.2)), (rng.randrange(TILE), rng.randrange(TILE)), 2)
    elif st == "ore":
        _noise_fill(s, c, rng)
        for _ in range(4 + var):
            x, y = rng.randrange(2, TILE - 3), rng.randrange(2, TILE - 3)
            pygame.draw.rect(s, t.color2, (x, y, 3, 2))
            s.set_at((x, y), _shade(t.color2, 1.3))
    elif st == "crystal":
        _noise_fill(s, c, rng, 0.08)
        for _ in range(3):
            x, y = rng.randrange(2, TILE - 3), rng.randrange(2, TILE - 3)
            pygame.draw.polygon(s, _shade(c, 1.15), [(x, y - 3), (x + 2, y), (x, y + 3), (x - 2, y)])
    elif st == "ice":
        s.fill(c)
        pygame.draw.line(s, _shade(c, 1.15), (2, 12), (12, 2), 1)
        pygame.draw.line(s, _shade(c, 1.1), (6, 15), (15, 6), 1)
    elif st == "bark":
        s.fill((0, 0, 0, 0))
        pygame.draw.rect(s, c, (4, 0, 8, TILE))
        pygame.draw.line(s, _shade(c, 0.7), (6, 0), (6, TILE), 1)
        pygame.draw.line(s, _shade(c, 0.75), (9, 0), (9 + rng.choice((-1, 0, 1)), TILE), 1)
        pygame.draw.line(s, _shade(c, 1.2), (4, 0), (4, TILE), 1)
    elif st == "leaves":
        s.fill((0, 0, 0, 0))
        for _ in range(9):
            x, y = rng.randrange(TILE), rng.randrange(TILE)
            pygame.draw.circle(s, _shade(c, rng.uniform(0.8, 1.2)), (x, y), rng.randint(3, 5))
    elif st == "planks":
        s.fill(c)
        for y in (0, 5, 10, 15):
            pygame.draw.line(s, _shade(c, 0.7), (0, y), (TILE, y), 1)
        for y, x in ((1, 3 + var), (6, 10 - var), (11, 6)):
            pygame.draw.line(s, _shade(c, 0.75), (x, y), (x, y + 3), 1)
    elif st == "brick":
        s.fill(_shade(c, 0.7))
        for row in range(4):
            off = 4 if row % 2 else 0
            for bx in range(-8 + off, TILE, 8):
                pygame.draw.rect(s, _shade(c, rng.uniform(0.92, 1.08)), (bx + 1, row * 4 + 1, 7, 3))
    elif st == "cobble":
        s.fill(_shade(c, 0.6))
        for _ in range(7):
            pygame.draw.circle(s, _shade(c, rng.uniform(0.85, 1.15)), (rng.randrange(TILE), rng.randrange(TILE)), 3)
    elif st == "fachwerk":
        s.fill(c)
        _noise_fill(s, c, rng, 0.04, 20)
        beam = t.color2
        pygame.draw.rect(s, beam, (0, 0, 3, TILE))
        if var % 2 == 0:
            pygame.draw.line(s, beam, (3, TILE - 1), (TILE - 1, 2), 3)
        else:
            pygame.draw.line(s, beam, (3, 1), (TILE - 1, TILE - 2), 3)
        pygame.draw.rect(s, beam, (0, TILE - 2, TILE, 2))
    elif st == "thatch":
        s.fill(c)
        for i in range(10):
            x = rng.randrange(TILE)
            pygame.draw.line(s, _shade(c, rng.uniform(0.75, 1.2)), (x, 0), (x - 3, TILE), 1)
    elif st == "scales":
        s.fill(_shade(c, 0.75))
        for row in range(4):
            off = 4 if row % 2 else 0
            for bx in range(-8 + off, TILE + 8, 8):
                pygame.draw.circle(s, _shade(c, rng.uniform(0.9, 1.1)), (bx + 4, row * 4 + 4), 4,
                                   draw_top_left=False, draw_top_right=False, draw_bottom_left=True,
                                   draw_bottom_right=True)
    elif st == "palisade":
        s.fill((0, 0, 0, 0))
        for x0 in (0, 8):
            pygame.draw.rect(s, _shade(c, rng.uniform(0.9, 1.1)), (x0 + 1, 0, 6, TILE))
            pygame.draw.line(s, _shade(c, 0.7), (x0 + 6, 0), (x0 + 6, TILE))
    elif st in ("door", "gate"):
        s.fill(c)
        for x in (0, 5, 10, 15):
            pygame.draw.line(s, _shade(c, 0.65), (x, 0), (x, TILE))
        pygame.draw.rect(s, (60, 60, 64), (0, 4, TILE, 2))
        pygame.draw.rect(s, (60, 60, 64), (0, 11, TILE, 2))
        if st == "door":
            pygame.draw.circle(s, (200, 170, 70), (12, 8), 1)
    elif st in ("door_open", "gate_open"):
        s.fill((0, 0, 0, 0))
        pygame.draw.rect(s, _shade(c, 0.7), (0, 0, 3, TILE))
    elif st == "ladder":
        s.fill((0, 0, 0, 0))
        pygame.draw.line(s, c, (3, 0), (3, TILE), 2)
        pygame.draw.line(s, c, (12, 0), (12, TILE), 2)
        for y in (3, 9, 15):
            pygame.draw.line(s, _shade(c, 0.9), (3, y), (12, y), 2)
    elif st == "platform":
        s.fill((0, 0, 0, 0))
        pygame.draw.rect(s, c, (0, 0, TILE, 4))
        pygame.draw.line(s, _shade(c, 0.6), (0, 4), (TILE, 4))
        pygame.draw.line(s, _shade(c, 0.7), (3, 4), (6, 10), 2)
    elif st == "farmland":
        s.fill(c)
        for y in (3, 8, 13):
            pygame.draw.line(s, _shade(c, 0.7), (0, y), (TILE, y), 2)
    else:
        s = _deco(t, rng, var)
    return s


def _deco(t, rng, var):
    """Furniture and plants. May be taller than a tile (anchored bottom)."""
    tall = t.style in ("stall", "sign", "banner", "throne", "well", "bell", "vine", "oven", "forge", "altar",
                       "loom", "sapling")
    h = TILE * 2 if tall else TILE
    s = pygame.Surface((TILE, h), pygame.SRCALPHA)
    b = h  # bottom
    c = t.color
    st = t.style
    if st == "torch":
        pygame.draw.line(s, (90, 60, 30), (8, 15), (8, 7), 2)
        pygame.draw.circle(s, (255, 200, 80), (8, 5), 3)
        pygame.draw.circle(s, (255, 250, 200), (8, 5), 1)
    elif st == "campfire":
        pygame.draw.line(s, (90, 60, 30), (2, 15), (14, 12), 3)
        pygame.draw.line(s, (90, 60, 30), (2, 12), (14, 15), 3)
        pygame.draw.polygon(s, (255, 140, 40), [(4, 13), (8, 2), (12, 13)])
        pygame.draw.polygon(s, (255, 230, 120), [(6, 13), (8, 7), (10, 13)])
    elif st == "crop":
        stage = t.extra["stage"]
        for i in range(4):
            x = 2 + i * 4
            top = 16 - stage * 3 - rng.randint(0, 2)
            pygame.draw.line(s, (100, 150, 60) if stage < 4 else (180, 150, 70), (x, 16), (x, top), 1)
            if stage >= 3:
                pygame.draw.ellipse(s, c, (x - 1, top - 2, 3, 5))
    elif st == "tallgrass":
        for i in range(5):
            x = rng.randrange(2, 14)
            pygame.draw.line(s, _shade(c, rng.uniform(0.8, 1.2)), (x, 16), (x + rng.randint(-2, 2), 6 + rng.randint(0, 5)))
    elif st == "flower":
        pygame.draw.line(s, (70, 120, 50), (8, 16), (8, 8))
        col = rng.choice([(220, 80, 90), (240, 220, 90), (150, 120, 220), (240, 240, 240)])
        for a in range(5):
            ang = a * 1.256
            pygame.draw.circle(s, col, (8 + int(math.cos(ang) * 2), 7 + int(math.sin(ang) * 2)), 2)
        pygame.draw.circle(s, (250, 210, 60), (8, 7), 1)
    elif st == "bush":
        for _ in range(6):
            pygame.draw.circle(s, _shade(c, rng.uniform(0.8, 1.2)), (rng.randrange(3, 13), rng.randrange(8, 14)), 4)
        for _ in range(4):
            s.set_at((rng.randrange(3, 13), rng.randrange(7, 14)), (170, 30, 50))
    elif st == "mushroom":
        pygame.draw.rect(s, (230, 220, 200), (7, 10, 3, 6))
        pygame.draw.ellipse(s, c, (3, 6, 11, 6))
        s.set_at((6, 8), (255, 255, 255))
        s.set_at((10, 7), (255, 255, 255))
    elif st == "seaweed":
        for i in range(3):
            x = 4 + i * 4
            pts = [(x + int(math.sin(k * 0.9 + i) * 2), 16 - k * 2) for k in range(9)]
            pygame.draw.lines(s, _shade(c, 0.9 + i * 0.1), False, pts, 2)
    elif st == "shell":
        pygame.draw.polygon(s, c, [(4, 16), (8, 10), (12, 16)])
        pygame.draw.line(s, _shade(c, 0.8), (8, 10), (8, 16))
    elif st == "vine":
        pygame.draw.line(s, (100, 76, 50), (8, b), (8, b - 26), 2)
        pygame.draw.line(s, (100, 76, 50), (2, b - 20), (14, b - 20), 1)
        for _ in range(5):
            pygame.draw.circle(s, (70, 120, 60), (rng.randrange(3, 13), b - rng.randrange(14, 28)), 3)
        for _ in range(3):
            x, y = rng.randrange(4, 12), b - rng.randrange(10, 18)
            for k in range(3):
                pygame.draw.circle(s, (110, 40, 110), (x + k % 2 * 2, y + k * 2), 1)
    elif st == "sapling":
        pygame.draw.line(s, (90, 64, 40), (8, b), (8, b - 10), 2)
        pygame.draw.circle(s, (80, 140, 60), (8, b - 12), 4)
    elif st == "workbench":
        pygame.draw.rect(s, c, (0, 6, 16, 3))
        pygame.draw.rect(s, _shade(c, 0.7), (1, 9, 2, 7))
        pygame.draw.rect(s, _shade(c, 0.7), (13, 9, 2, 7))
        pygame.draw.line(s, (150, 150, 160), (4, 5), (9, 5), 2)
    elif st == "anvil":
        pygame.draw.polygon(s, c, [(1, 7), (15, 7), (12, 10), (4, 10)])
        pygame.draw.rect(s, _shade(c, 0.8), (6, 10, 4, 4))
        pygame.draw.rect(s, _shade(c, 0.9), (3, 14, 10, 2))
    elif st == "forge":
        pygame.draw.rect(s, c, (1, b - 16, 14, 16))
        pygame.draw.rect(s, (40, 30, 30), (4, b - 12, 8, 7))
        pygame.draw.rect(s, (255, 120, 30), (5, b - 9, 6, 4))
        pygame.draw.rect(s, _shade(c, 0.8), (5, b - 30, 6, 14))
    elif st == "oven":
        pygame.draw.ellipse(s, c, (0, b - 18, 16, 20))
        pygame.draw.rect(s, c, (0, b - 8, 16, 8))
        pygame.draw.ellipse(s, (40, 26, 20), (4, b - 10, 8, 8))
        pygame.draw.ellipse(s, (255, 140, 40), (5, b - 7, 6, 4))
    elif st == "bed":
        pygame.draw.rect(s, (110, 80, 50), (0, 9, 16, 5))
        pygame.draw.rect(s, c, (0, 7, 16, 4))
        pygame.draw.rect(s, (236, 230, 216), (0, 6, 5, 4))
        pygame.draw.rect(s, (110, 80, 50), (0, 4, 2, 12))
    elif st == "chest":
        pygame.draw.rect(s, c, (2, 6, 12, 10))
        pygame.draw.rect(s, _shade(c, 1.2), (2, 6, 12, 3))
        pygame.draw.rect(s, (200, 170, 70), (7, 9, 2, 3))
    elif st == "table":
        pygame.draw.rect(s, c, (0, 6, 16, 2))
        pygame.draw.rect(s, _shade(c, 0.7), (2, 8, 2, 8))
        pygame.draw.rect(s, _shade(c, 0.7), (12, 8, 2, 8))
        if var % 2:
            pygame.draw.rect(s, (200, 200, 190), (6, 4, 3, 2))
    elif st == "barrel":
        pygame.draw.ellipse(s, c, (2, 2, 12, 14))
        pygame.draw.line(s, (60, 60, 60), (3, 6), (13, 6), 1)
        pygame.draw.line(s, (60, 60, 60), (3, 12), (13, 12), 1)
    elif st == "throne":
        pygame.draw.rect(s, (120, 20, 30), (3, b - 26, 10, 18))
        pygame.draw.rect(s, c, (1, b - 30, 14, 4))
        pygame.draw.rect(s, c, (1, b - 9, 14, 3))
        pygame.draw.rect(s, c, (2, b - 6, 2, 6))
        pygame.draw.rect(s, c, (12, b - 6, 2, 6))
    elif st == "banner":
        pygame.draw.line(s, (90, 70, 40), (2, 2), (14, 2), 2)
        pygame.draw.polygon(s, c, [(3, 3), (13, 3), (13, 26), (8, 21), (3, 26)])
        pygame.draw.circle(s, GOLDC, (8, 11), 3)
    elif st == "altar":
        pygame.draw.rect(s, c, (1, b - 10, 14, 10))
        pygame.draw.rect(s, (170, 30, 40), (1, b - 10, 14, 2))
        pygame.draw.line(s, GOLDC, (8, b - 24), (8, b - 12), 2)
        pygame.draw.line(s, GOLDC, (4, b - 20), (12, b - 20), 2)
    elif st == "stall":
        for i in range(4):
            pygame.draw.rect(s, (200, 50, 50) if i % 2 == 0 else (236, 226, 210), (i * 4, 0, 4, 7))
        pygame.draw.line(s, (100, 70, 40), (1, 7), (1, b), 2)
        pygame.draw.line(s, (100, 70, 40), (14, 7), (14, b), 2)
        pygame.draw.rect(s, (140, 100, 60), (0, b - 8, 16, 3))
        pygame.draw.circle(s, (220, 60, 40), (5, b - 10), 2)
        pygame.draw.circle(s, (240, 200, 60), (10, b - 10), 2)
    elif st == "sign":
        pygame.draw.line(s, c, (8, b), (8, b - 22), 2)
        pygame.draw.polygon(s, _shade(c, 1.2), [(1, b - 24), (13, b - 24), (16, b - 21), (13, b - 18), (1, b - 18)])
    elif st == "well":
        pygame.draw.rect(s, c, (0, b - 8, 16, 8))
        pygame.draw.line(s, (100, 70, 40), (1, b - 8), (1, b - 26), 2)
        pygame.draw.line(s, (100, 70, 40), (14, b - 8), (14, b - 26), 2)
        pygame.draw.polygon(s, (150, 70, 50), [(-1, b - 24), (8, b - 31), (17, b - 24)])
        pygame.draw.line(s, (60, 60, 60), (8, b - 24), (8, b - 14), 1)
    elif st == "bell":
        pygame.draw.polygon(s, c, [(4, b - 6), (6, b - 16), (10, b - 16), (12, b - 6)])
        pygame.draw.circle(s, _shade(c, 0.7), (8, b - 5), 2)
    elif st == "loom":
        pygame.draw.rect(s, c, (1, b - 22, 2, 22))
        pygame.draw.rect(s, c, (13, b - 22, 2, 22))
        for x in range(3, 13, 2):
            pygame.draw.line(s, (220, 210, 190), (x, b - 20), (x, b - 6))
    else:
        s.fill(c)
    return s


GOLDC = (214, 178, 74)


def _apply_mask(src, mask):
    """mask bits: 1=TL 2=TR 4=BL 8=BR rounded off."""
    if mask == 0:
        return src
    s = src.copy()
    r = TILE // 2
    for bit, (cx, cy) in ((1, (r, r)), (2, (TILE - r - 1, r)), (4, (r, TILE - r - 1)), (8, (TILE - r - 1, TILE - r - 1))):
        if not mask & bit:
            continue
        xs = range(0, r) if bit in (1, 4) else range(TILE - r, TILE)
        ys = range(0, r) if bit in (1, 2) else range(TILE - r, TILE)
        for x in xs:
            for y in ys:
                if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                    s.set_at((x, y), (0, 0, 0, 0))
    return s


def tile_surface(tid, var, mask):
    key = (tid, var, mask)
    s = _cache.get(key)
    if s is None:
        base_key = (tid, var, 0)
        base = _cache.get(base_key)
        if base is None:
            rng = random.Random(tid * 7919 + var * 104729)
            base = _draw_base(T.TILES[tid], rng, var)
            _cache[base_key] = base
        s = _apply_mask(base, mask) if T.TILES[tid].natural else base
        _cache[key] = s
    return s


def grass_cap(tid, var):
    key = (tid, var)
    s = _cap_cache.get(key)
    if s is None:
        t = T.TILES[tid]
        rng = random.Random(tid * 31 + var)
        s = pygame.Surface((TILE, 8), pygame.SRCALPHA)
        c = t.color2 or (90, 140, 60)
        pygame.draw.rect(s, c, (0, 3, TILE, 4))
        for x in range(0, TILE, 2):
            hgt = rng.randint(1, 3)
            pygame.draw.line(s, _shade(c, rng.uniform(0.9, 1.25)), (x, 4), (x, 4 - hgt))
        _cap_cache[key] = s
    return s


def bg_surface(bid, var):
    key = (bid, var)
    s = _bg_cache.get(key)
    if s is None:
        name, col = T.BG[bid]
        rng = random.Random(bid * 13 + var)
        s = pygame.Surface((TILE, TILE))
        dark = _shade(col, 0.8)
        if name in ("dirt", "stone", "ash", "snowstone"):
            _noise_fill(s, dark, rng, 0.1, 30)
        elif name == "planks":
            s.fill(dark)
            for y in (0, 8):
                pygame.draw.line(s, _shade(dark, 0.75), (0, y), (TILE, y))
        elif name == "fachwerk":
            s.fill(dark)
            if var % 2 == 0:
                pygame.draw.rect(s, (70, 48, 32), (0, 0, 2, TILE))
            pygame.draw.rect(s, (70, 48, 32), (0, TILE - 2, TILE, 2))
        elif name == "brick":
            s.fill(_shade(dark, 0.75))
            for row in range(4):
                off = 4 if row % 2 else 0
                for bx in range(-8 + off, TILE, 8):
                    pygame.draw.rect(s, dark, (bx + 1, row * 4 + 1, 7, 3))
        elif name == "window":
            s.fill((70, 54, 40))
            pygame.draw.rect(s, (120, 170, 200), (3, 2, 10, 12))
            pygame.draw.line(s, (70, 54, 40), (8, 2), (8, 14))
            pygame.draw.line(s, (70, 54, 40), (3, 8), (13, 8))
        elif name == "tapestry":
            s.fill(dark)
            pygame.draw.line(s, (170, 140, 60), (0, 3), (TILE, 3))
            pygame.draw.circle(s, (170, 140, 60), (8, 10), 2)
        else:
            s.fill(dark)
        _bg_cache[key] = s
    return s
