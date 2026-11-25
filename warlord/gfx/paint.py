"""Painterly helpers shared by every renderer: tileable noise, soft shadows and glows, leaf-dab foliage,
tapered limbs with soft shading, and supersampled (anti-aliased) drawing.

The look aims at a hand-painted picture book: shapes are built from many small overlapping dabs, light comes
from the upper left, colours get cooler and lighter with distance, and nothing has a hard black outline:
edges are drawn in a darker shade of the colour they bound.
"""
import math
import random
from collections import OrderedDict

import numpy as np
import pygame

LIGHT = (-0.55, -0.83)        # unit vector toward the sun (upper left)
SS = 2                        # supersampling factor for cached sprites and figures


def clamp8(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def shade(c, f):
    return (clamp8(c[0] * f), clamp8(c[1] * f), clamp8(c[2] * f))


def mix(a, b, t):
    return (clamp8(a[0] + (b[0] - a[0]) * t), clamp8(a[1] + (b[1] - a[1]) * t), clamp8(a[2] + (b[2] - a[2]) * t))


def warm(c, f):
    """Lighten toward a warm sunlit tint (f > 0) or darken toward a cool shadow (f < 0)."""
    if f >= 0:
        return mix(c, (255, 244, 200), f)
    return mix(c, (24, 30, 52), -f)


def jitter(c, rng, amt=10):
    return (clamp8(c[0] + rng.uniform(-amt, amt)), clamp8(c[1] + rng.uniform(-amt, amt)),
            clamp8(c[2] + rng.uniform(-amt, amt)))


# ====================================================================== noise
_NOISE = {}


def _value_noise(P, cells, rng):
    g = rng.random((cells, cells)).astype(np.float32)
    x = np.arange(P, dtype=np.float32) * cells / P
    i0 = np.floor(x).astype(int)
    f = x - i0
    f = f * f * (3 - 2 * f)
    i0 %= cells
    i1 = (i0 + 1) % cells
    a = g[i0][:, i0] * (1 - f)[None, :] + g[i0][:, i1] * f[None, :]
    b = g[i1][:, i0] * (1 - f)[None, :] + g[i1][:, i1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def noise(P=512, seed=1, octaves=(4, 8, 16, 32, 64, 128)):
    """Tileable fBm noise in 0..1, shape (P, P) indexed [y, x]."""
    key = (P, seed, octaves)
    n = _NOISE.get(key)
    if n is None:
        rng = np.random.default_rng(seed)
        n = np.zeros((P, P), dtype=np.float32)
        amp, tot = 1.0, 0.0
        for c in octaves:
            if c > P:
                break
            n += _value_noise(P, c, rng) * amp
            tot += amp
            amp *= 0.55
        n /= tot
        n = (n - n.min()) / max(1e-6, n.max() - n.min())
        _NOISE[key] = n
    return n


def noise_window(n, x0, y0, w, h):
    """A w*h window of the tileable noise n starting at world (x0, y0), wrapping around."""
    P = n.shape[0]
    ys = (np.arange(h) + int(y0)) % P
    xs = (np.arange(w) + int(x0)) % P
    return n[ys][:, xs]


_MUL = {}


def texture_mul(w, h, seed=3, lo=200, hi=255, scale=1):
    """A grey multiply-texture (for BLEND_RGB_MULT) of noise between lo and hi."""
    key = (w, h, seed, lo, hi, scale)
    s = _MUL.get(key)
    if s is None:
        n = noise(256, seed, (8, 16, 32, 64, 128))
        P = 256
        ys = (np.arange(h) // scale) % P
        xs = (np.arange(w) // scale) % P
        v = lo + n[ys][:, xs] * (hi - lo)
        a = np.repeat(v.T[:, :, None], 3, axis=2).astype(np.uint8)
        s = pygame.surfarray.make_surface(a)
        if len(_MUL) > 64:
            _MUL.clear()
        _MUL[key] = s
    return s


# ====================================================================== soft sprites
_SOFT = OrderedDict()


def _cache(key, make, cap=300):
    s = _SOFT.get(key)
    if s is None:
        s = make()
        _SOFT[key] = s
        while len(_SOFT) > cap:
            _SOFT.popitem(last=False)
    else:
        _SOFT.move_to_end(key)
    return s


def soft_ellipse(w, h, color=(0, 0, 0), alpha=110, power=1.6):
    """An ellipse that fades out toward its rim (contact shadows, mist, glows)."""
    w, h = max(2, int(w)), max(2, int(h))

    def make():
        xs = (np.arange(w, dtype=np.float32) + 0.5) / w * 2 - 1
        ys = (np.arange(h, dtype=np.float32) + 0.5) / h * 2 - 1
        d = np.sqrt(xs[:, None] ** 2 + ys[None, :] ** 2)
        a = np.clip(1 - d, 0, 1) ** power * alpha
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((*color, 0))
        pa = pygame.surfarray.pixels_alpha(s)
        pa[:] = a.astype(np.uint8)
        del pa
        return s
    return _cache(("el", w, h, color, alpha, power), make)


def glow(r, color, alpha=120, power=2.0):
    return soft_ellipse(r * 2, r * 2, color, alpha, power)


def add_glow(r, color, strength=0.5, power=2.0):
    """An opaque black surface with a radial glow of colour: blit it with BLEND_RGB_ADD to brighten."""
    r = max(2, int(r))

    def make():
        xs = (np.arange(2 * r, dtype=np.float32) + 0.5) / r - 1
        d = np.sqrt(xs[:, None] ** 2 + xs[None, :] ** 2)
        k = np.clip(1 - d, 0, 1) ** power * strength
        a = (k[..., None] * np.array(color, dtype=np.float32)[None, None, :]).clip(0, 255).astype(np.uint8)
        return pygame.surfarray.make_surface(a)
    return _cache(("ag", r, color, round(strength, 2), power), make)


def contact_shadow(surf, x, y, w, alpha=90):
    """A soft dark ellipse on the ground under something standing at (x, y)."""
    w = max(6, int(w))
    s = soft_ellipse(w, max(4, int(w * 0.28)), (12, 14, 20), alpha, 1.2)
    surf.blit(s, (int(x - w / 2), int(y - s.get_height() / 2)))


def vgrad(w, h, top, bottom, alpha_top=255, alpha_bottom=255):
    """A vertical gradient strip (cached)."""
    def make():
        s = pygame.Surface((1, max(2, h)), pygame.SRCALPHA)
        for i in range(max(2, h)):
            t = i / max(1, h - 1)
            c = mix(top, bottom, t)
            s.set_at((0, i), (*c, clamp8(alpha_top + (alpha_bottom - alpha_top) * t)))
        return pygame.transform.scale(s, (max(1, w), max(2, h)))
    return _cache(("vg", w, h, top, bottom, alpha_top, alpha_bottom), make, cap=200)


# ====================================================================== dabs and limbs
def dab(surf, color, x, y, r, rng, n=5, squash=0.8, rot=None):
    """One irregular paint dab: a little polygon with a ragged rim."""
    if r < 1.2:
        pygame.draw.circle(surf, color, (x, y), max(1.0, r))
        return
    a0 = rng.uniform(0, math.tau) if rot is None else rot
    ca, sa = math.cos(a0), math.sin(a0)
    pts = []
    for i in range(n):
        a = math.tau * i / n
        rr = r * (0.7 + 0.4 * rng.random())
        lx, ly = math.cos(a) * rr, math.sin(a) * rr * squash
        pts.append((x + lx * ca - ly * sa, y + lx * sa + ly * ca))
    pygame.draw.polygon(surf, color, pts)


def leaf(surf, color, x, y, ln, ang, wd=0.38):
    """A single pointed leaf / needle shape."""
    c, s = math.cos(ang), math.sin(ang)
    px, py = -s, c
    w = ln * wd
    pts = [(x, y), (x + c * ln * 0.5 + px * w, y + s * ln * 0.5 + py * w), (x + c * ln, y + s * ln),
           (x + c * ln * 0.5 - px * w, y + s * ln * 0.5 - py * w)]
    pygame.draw.polygon(surf, color, pts)


def capsule(surf, a, b, wa, wb, color):
    """A tapered limb with round ends."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d
    pygame.draw.polygon(surf, color, ((a[0] + nx * wa, a[1] + ny * wa), (b[0] + nx * wb, b[1] + ny * wb),
                                      (b[0] - nx * wb, b[1] - ny * wb), (a[0] - nx * wa, a[1] - ny * wa)))
    if wa >= 0.8:
        pygame.draw.circle(surf, color, a, wa)
    if wb >= 0.8:
        pygame.draw.circle(surf, color, b, wb)


def soft_limb(surf, a, b, wa, wb, color, edge=1.0, lit=True):
    """A painted limb: a darker rim, the body colour, a cool shadow on the far side and a warm highlight
    along the side facing the light."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d
    if (nx * LIGHT[0] + ny * LIGHT[1]) < 0:
        nx, ny = -nx, -ny                        # n now points toward the light
    if edge > 0:
        capsule(surf, a, b, wa + edge, wb + edge, shade(color, 0.5))
    capsule(surf, a, b, wa, wb, color)
    # shadow side
    capsule(surf, (a[0] - nx * wa * 0.45, a[1] - ny * wa * 0.45), (b[0] - nx * wb * 0.45, b[1] - ny * wb * 0.45),
            wa * 0.55, wb * 0.55, warm(color, -0.22))
    capsule(surf, (a[0] + nx * wa * 0.1, a[1] + ny * wa * 0.1), (b[0] + nx * wb * 0.1, b[1] + ny * wb * 0.1),
            wa * 0.62, wb * 0.62, color)
    if lit:
        capsule(surf, (a[0] + nx * wa * 0.45, a[1] + ny * wa * 0.45), (b[0] + nx * wb * 0.45, b[1] + ny * wb * 0.45),
                wa * 0.3, wb * 0.3, warm(color, 0.2))


# ====================================================================== supersampled drawing
class SSCanvas:
    """Draw at SS times the size into a scratch surface, then shrink with smoothing: anti-aliased figures."""

    def __init__(self):
        self.pool = {}

    def get(self, w, h):
        key = (w, h)
        s = self.pool.get(key)
        if s is None:
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            if len(self.pool) > 24:
                self.pool.clear()
            self.pool[key] = s
        s.fill((0, 0, 0, 0))
        return s


CANVAS = SSCanvas()


def shrink(big, f=SS):
    w, h = big.get_size()
    return pygame.transform.smoothscale(big, (max(1, w // f), max(1, h // f)))


# ====================================================================== foliage
def paint_crown(surf, clumps, pal, rng, edge_leaves=True, leafy=1.0, ao=0.0, sun=1.0, stage="all", needles=False,
                squash=0.88, blur=0, blur_rim=False):
    """Paint a broadleaf crown from overlapping clumps of leaf dabs.

    clumps: [(cx, cy, r)] in surface coordinates, drawn back (first) to front (last).
    pal: (shadow, mid, light) colours. Each clump is shaded like a ball lit from the upper left (dark mass,
    a mid-tone cap shifted toward the sun, a small bright cap of single leaves), so the crown reads as a pile
    of leafy masses; lower clumps are darker because the crown shades itself.
    blur > 0 paints the masses, softens them (like wet paint), then lays the sunlit leaves on crisply."""
    if not clumps:
        return
    if blur:
        seed = rng.randint(0, 1 << 30)
        paint_crown(surf, clumps, pal, random.Random(seed), edge_leaves, leafy, ao, sun, "mass", needles, squash)
        soft = pygame.transform.gaussian_blur(surf, blur)
        surf.fill((0, 0, 0, 0))
        surf.blit(soft, (0, 0))
        paint_crown(surf, clumps, pal, random.Random(seed), edge_leaves, leafy, ao, sun, "light", needles, squash,
                    blur_rim=True)
        return
    base_seed = rng.randint(0, 1 << 30)
    dark, mid, lite = pal
    ys = [c[1] for c in clumps]
    ytop, ybot = min(ys), max(ys)
    span = max(1.0, ybot - ytop)
    for ci, (cx, cy, r) in enumerate(clumps):
        rng = random.Random(base_seed + ci * 7919 + (1 if stage == "light" else 0))
        depth = (cy - ytop) / span                 # 0 top .. 1 bottom of the crown
        k = 1.0 - 0.2 * depth - ao
        cd = warm(shade(dark, k * 0.82), -0.12)
        cm = shade(mid, k)
        cl = warm(shade(lite, min(1.15, (k + 0.1) * 1.08)), 0.16 * sun)
        rd = max(2.0, r * 0.3)
        lx, ly = LIGHT

        def fill(col, ccx, ccy, rad, size, count, amt, leaves=0.0):
            for _ in range(count):
                a = rng.uniform(0, math.tau)
                d = rad * math.sqrt(rng.random())
                x, y = ccx + math.cos(a) * d, ccy + math.sin(a) * d * squash
                if needles and leaves:
                    ln = size * rng.uniform(1.2, 2.0)
                    an = rng.uniform(-2.6, -0.5)
                    pygame.draw.line(surf, jitter(col, rng, amt), (x, y), (x + math.cos(an) * ln, y + math.sin(an) * ln),
                                     max(1, int(size * 0.25)))
                elif leaves and rng.random() < leaves:
                    leaf(surf, jitter(col, rng, amt), x, y, size * rng.uniform(1.0, 1.6), rng.uniform(0, math.tau))
                else:
                    dab(surf, jitter(col, rng, amt), x, y, size * rng.uniform(0.75, 1.2), rng)
        n = int((8 + (r / rd) ** 2 * 1.5) * leafy)
        mass = stage in ("all", "mass")
        light = stage in ("all", "light")
        # 1. the dark mass with a ragged rim of single leaves
        if mass:
            fill(cd, cx, cy, r * 0.8, rd, n, 5)
        if edge_leaves and mass:
            for _ in range(int(r * 0.7 * leafy)):
                a = rng.uniform(0, math.tau)
                x, y = cx + math.cos(a) * r * 0.9, cy + math.sin(a) * r * 0.8 * squash / 0.88
                if needles:
                    pygame.draw.line(surf, jitter(cd, rng, 8), (x, y), (x + math.cos(a) * rd * 1.4,
                                                                         y + math.sin(a) * rd * 1.4), 2)
                else:
                    leaf(surf, jitter(cd if math.sin(a) > -0.3 else cm, rng, 8), x, y, rd * rng.uniform(0.6, 1.0),
                         a + rng.uniform(-0.7, 0.7))
        # 2. the mid-tone cap, shifted toward the sun
        if mass:
            fill(cm, cx + lx * r * 0.16, cy + ly * r * 0.16, r * 0.66, rd * 0.9, int(n * 0.75), 7)
            # a few dark gaps where the light falls through to the branches (softened with the mass)
            for _ in range(int(r * 0.04 * leafy)):
                a = rng.uniform(0, math.tau)
                d = r * rng.uniform(0.25, 0.6)
                dab(surf, shade(cd, 0.8), cx + math.cos(a) * d - lx * r * 0.2, cy + math.sin(a) * d - ly * r * 0.2,
                    rd * 0.4, rng)
        if not light:
            continue
        # 3. the bright cap: single sunlit leaves, lighter toward the centre of the cap
        hx, hy = cx + lx * r * 0.32, cy + ly * r * 0.32
        for _ in range(int(n * 1.1)):
            a = rng.uniform(0, math.tau)
            u = rng.random() ** 0.8
            d = r * 0.55 * u
            x, y = hx + math.cos(a) * d, hy + math.sin(a) * d * squash
            col = jitter(mix(cl, cm, u * 0.9), rng, 7)
            if needles:
                an = rng.uniform(-2.6, -0.5)
                ln = rd * rng.uniform(0.8, 1.4)
                pygame.draw.line(surf, col, (x, y), (x + math.cos(an) * ln, y + math.sin(an) * ln), max(1, int(rd * 0.2)))
            else:
                leaf(surf, col, x, y, rd * rng.uniform(0.55, 0.9), rng.uniform(0, math.tau), 0.42)
        # a crisp leafy rim over the softened mass
        if blur_rim:
            for _ in range(int(r * 0.8 * leafy)):
                a = rng.uniform(0, math.tau)
                x, y = cx + math.cos(a) * r * 0.86, cy + math.sin(a) * r * 0.76 * squash / 0.88
                lit_side = math.cos(a) * lx + math.sin(a) * ly
                col = mix(cd, cl, max(0.0, lit_side) * 0.7)
                if needles:
                    an = a * 0.5 + (math.pi / 2 if math.sin(a) > 0 else -math.pi / 2) * 0.5 * 0 + rng.uniform(-0.4, 0.4)
                    ln = rd * 0.55
                    pygame.draw.line(surf, jitter(col, rng, 6), (x, y), (x + math.cos(an) * ln, y + abs(math.sin(an)) * ln * 0.6), 2)
                else:
                    leaf(surf, jitter(col, rng, 6), x, y, rd * rng.uniform(0.5, 0.85), a + rng.uniform(-0.8, 0.8))
        # 5. sparkles of light at the rim
        for _ in range(int(r * 0.18)):
            a = math.atan2(ly, lx) + rng.uniform(-0.8, 0.8)
            d = r * rng.uniform(0.5, 0.8)
            leaf(surf, warm(cl, 0.3), cx + math.cos(a) * d, cy + math.sin(a) * d * 0.88, rd * 0.5,
                 rng.uniform(0, math.tau))


def paint_needles(surf, tier, pal, rng, snow=False):
    """Paint one drooping tier of a conifer. tier = (apex, left tip, right tip, base y)."""
    (ax, ay), (lx, ly), (rx, ry), sag = tier
    dark, mid, lite = pal
    # body
    body = [(ax, ay), (lx, ly), ((lx + ax) / 2, ly - sag * 0.6), (ax, ly - sag * 0.2),
            ((rx + ax) / 2, ry - sag * 0.6), (rx, ry)]
    pygame.draw.polygon(surf, shade(dark, 0.8), body)
    # a mid-tone mass on the upper (lit) half of the tier
    pygame.draw.polygon(surf, mid, [(ax, ay + 2), ((lx * 2 + ax) / 3, (ly * 2 + ay) / 3 - sag * 0.2),
                                    ((rx * 0.4 + ax * 0.6), (ry * 0.4 + ay * 0.6))])
    # needle sprays hanging along both flanks
    for side, (tx, ty) in ((-1, (lx, ly)), (1, (rx, ry))):
        n = int(abs(tx - ax) * 0.9) + 6
        for i in range(n):
            t = rng.random()
            x = ax + (tx - ax) * t
            y = ay + (ty - ay) * t
            y += rng.uniform(-3, 4)
            ln = (4 + 9 * t) * rng.uniform(0.7, 1.2)
            ang = math.pi / 2 + side * rng.uniform(-0.1, 0.9)
            lit = side < 0 or t < 0.35
            col = jitter(lite if (lit and rng.random() < 0.6) else (mid if rng.random() < 0.7 else dark), rng, 8)
            pygame.draw.line(surf, col, (x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln),
                             2 if ln > 6 else 1)
    # hanging fringe along the lower edge
    x = lx
    while x < rx:
        t = (x - lx) / max(1.0, rx - lx)
        yb = ly + (ry - ly) * t - math.sin(t * math.pi) * sag * 0.6
        ln = rng.uniform(3, 8)
        col = jitter(dark if t > 0.5 else mid, rng, 6)
        pygame.draw.line(surf, col, (x, yb - 2), (x + rng.uniform(-1.5, 1.5), yb + ln), 2)
        x += rng.uniform(2, 4)
    # light along the upper left flank
    for i in range(int(abs(lx - ax) * 0.5) + 3):
        t = rng.uniform(0.05, 0.8)
        x = ax + (lx - ax) * t + rng.uniform(0, 4)
        y = ay + (ly - ay) * t + rng.uniform(1, 5)
        pygame.draw.line(surf, warm(lite, 0.12), (x, y), (x - rng.uniform(2, 5), y + rng.uniform(2, 6)), 1)
    if snow:
        # snow lies in clumps on the upper sides of the branch tips
        for side, (tx, ty) in ((-1, (lx, ly)), (1, (rx, ry))):
            for i in range(int(abs(tx - ax) * 0.18) + 2):
                t = rng.uniform(0.15, 0.95)
                x = ax + (tx - ax) * t
                y = ay + (ty - ay) * t - 1
                rr = (2 + 4 * t) * rng.uniform(0.7, 1.1)
                pygame.draw.ellipse(surf, (210, 220, 236), (x - rr, y - rr * 0.3, rr * 2, rr * 0.9))
                pygame.draw.ellipse(surf, (244, 247, 252), (x - rr * 0.9, y - rr * 0.45, rr * 1.6, rr * 0.7))


def bark_strokes(surf, poly, base, rng, kind="oak"):
    """Vertical bark texture inside a trunk polygon (fissures, lit ridges)."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    mask = pygame.Surface((int(x1 - x0) + 2, int(y1 - y0) + 2), pygame.SRCALPHA)
    pts = [(x - x0, y - y0) for x, y in poly]
    pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
    tex = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
    W, H = mask.get_size()
    if kind == "birch":
        for _ in range(int(H / 5)):
            y = rng.uniform(0, H)
            x = rng.uniform(0, W * 0.6)
            ln = rng.uniform(W * 0.2, W * 0.6)
            pygame.draw.line(tex, (40, 38, 36, 220), (x, y), (x + ln, y + rng.uniform(-1, 1)), 2 if rng.random() < 0.4
                             else 1)
        for _ in range(int(H / 14)):
            y = rng.uniform(0, H)
            pygame.draw.ellipse(tex, (60, 56, 52, 200), (rng.uniform(0, W * 0.5), y, rng.uniform(3, 8), 3))
    else:
        nfiss = max(2, int(W / 5))
        for i in range(nfiss):
            x = (i + 0.5) / nfiss * W + rng.uniform(-2, 2)
            y = rng.uniform(-10, H * 0.3)
            col = (*shade(base, 0.55), 200)
            while y < H:
                ln = rng.uniform(6, 22)
                nx = x + rng.uniform(-1.5, 1.5)
                pygame.draw.line(tex, col, (x, y), (nx, y + ln), 2 if kind in ("oak", "pine") else 1)
                x, y = nx, y + ln + rng.uniform(0, 5)
        for _ in range(int(W * H / 60)):
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            pygame.draw.line(tex, (*warm(base, 0.2), 150), (x, y), (x, y + rng.uniform(2, 7)), 1)
    tex.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(tex, (x0, y0))
