"""Quadrupeds with a real skeleton: four two-bone legs solved by inverse kinematics, driven by gaits.

Gaits follow the real footfall patterns:
  walk   — four beats, left hind → left fore → right hind → right fore, always three feet down
  trot   — diagonal pairs move together
  gallop — rotary: hinds then fores in quick succession, with a moment of suspension
Hind legs fold at the hock (the joint points backward), fore legs at the knee (points forward); the
body rocks and bobs with the gait, the neck nods against it, the tail swings with the wind.
Everything is painted at twice the size and shrunk smoothly: smooth bodies with shaded muscles over shoulder
and haunch, fur strokes along the lie of the coat, flowing manes and tails; the far legs are darker.
"""
import math

import pygame

from . import paint

# species: body length, withers height, hip height, chest depth, leg length, neck (len, angle), head len, shape
SPEC = {
    "horse": dict(L=44, wh=36, hh=35, depth=15, leg=22, neck=(20, 0.95), head=15, muzzle=6, tail=18, ears=4,
                  mane=True, hoof=True, coat=(120, 82, 52), belly=(150, 112, 76), dark=(52, 36, 26)),
    "cow": dict(L=40, wh=27, hh=28, depth=15, leg=14, neck=(10, 0.35), head=12, muzzle=6, tail=16, ears=3,
                horns=True, udder=True, patches=True, coat=(226, 220, 206), belly=(236, 230, 218), dark=(60, 50, 44)),
    "sheep": dict(L=26, wh=19, hh=19, depth=11, leg=10, neck=(6, 0.55), head=8, muzzle=3, tail=5, ears=3,
                  wool=True, coat=(232, 228, 214), belly=(220, 214, 200), dark=(56, 52, 48)),
    "pig": dict(L=28, wh=16, hh=17, depth=11, leg=7, neck=(4, 0.15), head=10, muzzle=4, tail=4, ears=4,
                snout=True, coat=(232, 168, 156), belly=(242, 190, 180), dark=(150, 96, 90)),
    "deer": dict(L=32, wh=28, hh=29, depth=11, leg=19, neck=(15, 1.05), head=10, muzzle=4, tail=4, ears=5,
                 antlers=True, hoof=True, coat=(156, 104, 62), belly=(214, 190, 160), dark=(70, 46, 30)),
    "boar": dict(L=30, wh=20, hh=17, depth=13, leg=8, neck=(5, 0.25), head=12, muzzle=5, tail=4, ears=3,
                 tusks=True, bristle=True, coat=(84, 68, 54), belly=(104, 86, 70), dark=(40, 32, 26)),
    "wolf": dict(L=30, wh=20, hh=19, depth=10, leg=13, neck=(8, 0.6), head=11, muzzle=5, tail=14, ears=5,
                 pointy=True, bushy=True, coat=(118, 116, 120), belly=(176, 172, 168), dark=(54, 52, 56)),
    "bear": dict(L=40, wh=27, hh=24, depth=19, leg=11, neck=(6, 0.3), head=13, muzzle=5, tail=3, ears=4,
                 round=True, coat=(92, 66, 46), belly=(110, 82, 58), dark=(46, 32, 22)),
}
GAITS = {
    # phase offsets (0..1) for LH, LF, RH, RF and the stance fraction
    "walk": ((0.0, 0.25, 0.5, 0.75), 0.68),
    "trot": ((0.0, 0.5, 0.5, 0.0), 0.5),
    "gallop": ((0.0, 0.62, 0.1, 0.72), 0.38),
}
LIGHT = (-0.45, -0.89)


def shade(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def ik(hip, foot, l1, l2, bend):
    """Two-bone IK; bend +1 bends the joint forward (+x local), -1 backward."""
    dx, dy = foot[0] - hip[0], foot[1] - hip[1]
    d = max(1e-3, min(l1 + l2 - 0.01, math.hypot(dx, dy)))
    a = math.atan2(dy, dx)
    c = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    c = max(-1.0, min(1.0, c))
    off = math.acos(c) * bend
    jx = hip[0] + math.cos(a - off) * l1
    jy = hip[1] + math.sin(a - off) * l1
    return (jx, jy)


_EW = [1.0]


def limb(surf, a, b, wa, wb, col):
    paint.soft_limb(surf, a, b, wa, wb, col, edge=_EW[0], lit=wa > 1.5 * _EW[0])


def upper(surf, root, knee, wa, wb, col):
    """The upper leg grows out of the body: start it below the root so its rounded top stays hidden."""
    dx, dy = knee[0] - root[0], knee[1] - root[1]
    d = math.hypot(dx, dy) or 1.0
    k = min(0.45, wa * 1.1 / d)
    limb(surf, (root[0] + dx * k, root[1] + dy * k), knee, wa, wb, col)


def smooth_closed(pts, n=4):
    """Catmull-Rom through a closed polygon: a smooth outline from a few control points."""
    out = []
    m = len(pts)
    for i in range(m):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % m], pts[(i + 2) % m]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append((0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                               (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                        0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                               (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
    return out


def toward(pts, c, k, dx=0.0, dy=0.0):
    return [(c[0] + (x - c[0]) * k + dx, c[1] + (y - c[1]) * k + dy) for x, y in pts]


def gait_of(speed, sp):
    if speed < 3:
        return None, 0.0
    if speed > sp["L"] * 3.2:
        return "gallop", speed / (sp["L"] * 2.4)
    if speed > sp["L"] * 1.9:
        return "trot", speed / (sp["L"] * 1.6)
    return "walk", speed / (sp["L"] * 1.1)


def body_bob(a, sp, gait, t, S=1.0):
    if gait == "gallop":
        return math.sin(t * math.tau) * 2.5 * S
    if gait == "trot":
        return abs(math.sin(t * math.tau * 2)) * 1.6 * S
    if gait == "walk":
        return math.sin(t * math.tau * 2) * 0.6 * S
    return math.sin(a.anim_t * 1.4) * 0.4 * S


def saddle_offset(a):
    """Where the rider's seat is, relative to the feet centre (x forward-signed, y up negative)."""
    sp = SPEC.get(a.species, SPEC["horse"])
    gait, _ = gait_of(abs(a.vx), sp)
    bob = body_bob(a, sp, gait, a.walk_phase)
    return a.facing * 3.0, -(sp["wh"] + sp["hh"]) / 2 - 3.0 + bob


def draw_quadruped(surf, a, cx, fy, scale=1.0):
    """a: an Animal. cx, fy: screen position of the feet centre. Painted at twice the size, then shrunk."""
    sp = SPEC.get(a.species)
    if sp is None:
        return False
    k = paint.SS
    hw = int((sp["L"] * 0.5 + sp["head"] + sp["neck"][0] + sp["tail"] + 14) * scale)
    up = int((sp["wh"] + sp["neck"][0] + sp["head"] + 16) * scale)
    dn = int(8 * scale)
    canvas = paint.CANVAS.get(hw * 2 * k, (up + dn) * k)
    _EW[0] = 0.55 * scale * k
    ok = _draw_quadruped(canvas, a, hw * k, up * k, scale * k)
    surf.blit(paint.shrink(canvas, k), (int(cx) - hw, int(fy) - up))
    bit = getattr(a, "_bit", None)
    if bit is not None:
        a._bit = (int(cx) - hw + bit[0] / k, int(fy) - up + bit[1] / k)
    return ok


def _draw_quadruped(surf, a, cx, fy, scale=1.0):
    sp = SPEC.get(a.species)
    f = a.facing
    S = scale
    speed = abs(a.vx)
    if a.rider is not None:
        speed = abs(a.vx)
    gait, rate = gait_of(speed, sp)
    t = a.walk_phase
    coat = sp["coat"] if not a.hurt_flash else (255, 255, 255)
    col_override = getattr(a, "color", None)
    if a.species == "horse" and col_override is not None and not a.hurt_flash:
        coat = col_override
    belly = sp["belly"]
    dark = sp["dark"]
    if a.dead:
        draw_dead(surf, a, sp, cx, fy, S, coat, dark)
        return True
    L = sp["L"] * S
    wh, hh = sp["wh"] * S, sp["hh"] * S
    leg = sp["leg"] * S
    # body rocking with the gait
    bob = body_bob(a, sp, gait, t, S)
    pitch = math.sin(t * math.tau + 0.8) * 0.09 if gait == "gallop" else 0.0
    if a.species == "horse" and getattr(a, "rearing", 0) > 0:
        pitch = -0.5
    shoulder = (cx + f * L * 0.36, fy - wh + bob + f * pitch * L * 0.36 * 0)
    hip = (cx - f * L * 0.36, fy - hh + bob)
    sy_off = math.sin(pitch) * L * 0.36
    shoulder = (shoulder[0], shoulder[1] - sy_off)
    hip = (hip[0], hip[1] + sy_off)
    # ---------------------------------------------------------------- legs
    offs, stance = GAITS.get(gait, ((0, 0, 0, 0), 1.0))
    stride = (L * (0.34 if gait == "walk" else 0.42 if gait == "trot" else 0.62)) if gait else 0.0
    lift = leg * (0.22 if gait == "walk" else 0.3 if gait == "trot" else 0.38)
    legs = {}
    for i, name in enumerate(("LH", "LF", "RH", "RF")):
        root = hip if name[1] == "H" else shoulder
        ph = (t + offs[i]) % 1.0 if gait else 0.0
        if gait is None:
            fx = 0.0
            ly = 0.0
        elif ph < stance:
            k = ph / stance
            fx = stride * (0.5 - k)
            ly = 0.0
        else:
            k = (ph - stance) / (1 - stance)
            fx = stride * (-0.5 + k)
            ly = math.sin(k * math.pi) * lift
        near = name[0] == ("L" if f > 0 else "R")
        foot = (root[0] + f * (fx + (2 if name[1] == "F" else -1) * S), fy - ly)
        l1 = (root[1] - fy) * (0.5 if name[1] == "F" else 0.55)
        l2 = (root[1] - fy) * (0.56 if name[1] == "F" else 0.55)
        bend = (1 if name[1] == "F" else -1) * f * -1
        knee = ik(root, foot, max(2, l1), max(2, l2), bend)
        legs[name] = (root, knee, foot, near)
    leg_w = {"horse": 3.0, "cow": 3.2, "bear": 4.4, "pig": 2.6, "boar": 2.8, "sheep": 2.0, "deer": 2.0,
             "wolf": 2.2}.get(a.species, 2.5) * S
    # far legs first, darker
    for name in ("LH", "LF", "RH", "RF"):
        root, knee, foot, near = legs[name]
        if near:
            continue
        c = shade(coat, 0.68)
        limb(surf, root, knee, leg_w * 1.5, leg_w * 0.72, c)
        limb(surf, knee, foot, leg_w * 0.72, leg_w * 0.55, c)
        if sp.get("hoof"):
            pygame.draw.polygon(surf, shade(dark, 0.8), [(foot[0] - 2.5 * S, foot[1]), (foot[0] + 2.5 * S, foot[1]),
                                                         (foot[0] + 2 * S, foot[1] - 3 * S),
                                                         (foot[0] - 2 * S, foot[1] - 3 * S)])
    # ---------------------------------------------------------------- tail (behind the body)
    tb = (hip[0] - f * 3 * S, hip[1] - 2 * S)
    sw = math.sin(a.anim_t * 2.2) * 0.25 + (0.3 if gait == "gallop" else 0.0)
    tl = sp["tail"] * S
    if sp.get("bushy"):
        te = (tb[0] - f * tl * math.cos(0.5 - sw), tb[1] + tl * math.sin(0.5 - sw) * 0.8)
        limb(surf, tb, te, 3 * S, 2 * S, shade(coat, 0.9))
        pygame.draw.circle(surf, shade(dark, 1.4), (int(te[0]), int(te[1])), int(2 * S))
    elif a.species == "horse":
        # a flowing tail of many strands, lighter where the light catches it
        for j in range(7):
            o = (j - 3) * 0.6
            pts = [(tb[0], tb[1] + o * 0.3 * S)]
            for k in range(1, 7):
                u = k / 6
                wave = math.sin(a.anim_t * 2 + u * 2.4 + j * 0.4) * 2.2 * u
                pts.append((tb[0] - f * (tl * (0.42 + 0.04 * o) * u + wave * S) - f * o * u * S,
                            tb[1] + tl * u * (0.95 - (0.5 if gait == "gallop" else 0.0) * u) + o * u * S))
            c = paint.warm(dark, 0.25) if j in (1, 2) else (dark if j % 2 else paint.shade(dark, 0.8))
            pygame.draw.lines(surf, c, False, pts, max(1, int(S * (1.4 if j in (2, 3, 4) else 0.9))))
    else:
        te = (tb[0] - f * tl * 0.4, tb[1] + tl * 0.9)
        pygame.draw.line(surf, shade(coat, 0.8), tb, te, max(1, int(2 * S)))
    # ---------------------------------------------------------------- near legs (the body overlaps their tops)
    for name in ("LH", "LF", "RH", "RF"):
        root, knee, foot, near = legs[name]
        if not near:
            continue
        c = coat
        limb(surf, root, knee, leg_w * 1.7, leg_w * 0.8, c)
        limb(surf, knee, foot, leg_w * 0.78, leg_w * 0.6, shade(c, 0.94))
        if sp.get("hoof"):
            hp = [(foot[0] - 2.6 * S, foot[1]), (foot[0] + 2.6 * S, foot[1]), (foot[0] + 2.1 * S, foot[1] - 3.2 * S),
                  (foot[0] - 2.1 * S, foot[1] - 3.2 * S)]
            pygame.draw.polygon(surf, dark, hp)
            pygame.draw.line(surf, paint.warm(dark, 0.3), hp[3], (foot[0] - 2.4 * S, foot[1] - 0.5 * S),
                             max(1, int(S * 0.6)))
            pygame.draw.polygon(surf, paint.shade(dark, 0.6), hp, max(1, int(_EW[0])))
            if a.species == "horse":
                # a little feathering over the hoof
                for k in range(3):
                    pygame.draw.line(surf, paint.warm(coat, -0.2), (foot[0] - (1.5 - k * 1.5) * S, foot[1] - 4.5 * S),
                                     (foot[0] - (2.0 - k * 1.5) * S - f * S, foot[1] - 2.8 * S), max(1, int(S * 0.5)))
        elif a.species in ("wolf", "bear"):
            pygame.draw.ellipse(surf, shade(dark, 1.2), (foot[0] - 3 * S + f * S, foot[1] - 2.5 * S, 6 * S, 3 * S))
    # ---------------------------------------------------------------- neck & head (the chest overlaps the neck)
    d = sp["depth"] * S
    nl, na = sp["neck"]
    nl *= S
    nod = 0.0
    if gait == "walk":
        nod = math.sin(t * math.tau * 2) * 0.06
    elif gait == "gallop":
        nod = math.sin(t * math.tau + 2.2) * 0.12
    grazing = getattr(a, "graze", 0.0)
    na2 = na + nod - grazing * 1.6
    nb = (shoulder[0] + f * 2 * S, shoulder[1] + 2 * S)
    ne = (nb[0] + f * math.cos(na2) * nl, nb[1] - math.sin(na2) * nl)
    if nl > 2:
        limb(surf, nb, ne, d * 0.4, d * 0.26, coat)
        # the crest of the neck catches the light
        paint.capsule(surf, (nb[0] + paint.LIGHT[0] * d * 0.12, nb[1] - d * 0.2),
                      (ne[0] + paint.LIGHT[0] * d * 0.06, ne[1] - d * 0.1), d * 0.14, d * 0.08, paint.warm(coat, 0.18))
    if sp.get("mane"):
        # the mane falls along the crest in locks that lift in the gallop; a forelock over the brow
        for k in range(10):
            u = k / 9
            px = nb[0] + (ne[0] - nb[0]) * u
            py = nb[1] + (ne[1] - nb[1]) * u - d * 0.32
            fl = math.sin(a.anim_t * 3 + k * 0.8) * 1.2 + (2.5 if gait == "gallop" else 0)
            ang = math.atan2((2.6 - fl * 0.4) * S, -f * (3 + fl) * S)
            ln = (5.0 + 1.5 * math.sin(k * 1.7)) * S
            paint.leaf(surf, dark, px, py, ln, ang, 0.32)
            if k % 3 == 1:
                paint.leaf(surf, paint.warm(dark, 0.3), px, py, ln * 0.7, ang - 0.15, 0.15)
    # ---------------------------------------------------------------- body
    d = sp["depth"] * S
    top_mid = ((hip[0] + shoulder[0]) / 2, (hip[1] + shoulder[1]) / 2 - (2 * S if a.species != "pig" else 3 * S))
    ctrl = [
        (hip[0] - f * 6 * S, hip[1] + 3 * S),                     # rump
        (hip[0] - f * 3 * S, hip[1] - 3 * S),
        top_mid,                                                    # back
        (shoulder[0] + f * 1 * S, shoulder[1] - 3.5 * S),         # withers
        (shoulder[0] + f * 6 * S, shoulder[1] + d * 0.35),        # chest front
        (shoulder[0] + f * 3 * S, shoulder[1] + d * 0.85),
        (top_mid[0], top_mid[1] + d * (1.12 if not sp.get("round") else 1.25)),   # belly
        (hip[0] + f * 2 * S, hip[1] + d * 0.8),
        (hip[0] - f * 4 * S, hip[1] + d * 0.55),                  # the thigh's back edge
    ]
    body = smooth_closed(ctrl, 5)
    bc = (top_mid[0], top_mid[1] + d * 0.5)
    lx, ly = paint.LIGHT
    if sp.get("wool"):
        pygame.draw.polygon(surf, paint.shade(coat, 0.55), body)
        pygame.draw.polygon(surf, paint.warm(coat, -0.18), toward(body, bc, 0.94))
        rng = __import__("random").Random(7)
        for k in range(46):
            u = rng.random()
            v = rng.random()
            px = hip[0] + (shoulder[0] - hip[0]) * u
            py = top_mid[1] + d * (0.1 + 0.8 * v)
            c = paint.warm(coat, 0.18) if v < 0.4 else (coat if v < 0.75 else paint.warm(coat, -0.12))
            pygame.draw.circle(surf, c, (px, py), d * 0.2 * rng.uniform(0.8, 1.2))
            pygame.draw.circle(surf, paint.shade(c, 0.86), (px, py), d * 0.2 * rng.uniform(0.8, 1.2), max(1, int(S * 0.3)))
    else:
        pygame.draw.polygon(surf, paint.shade(coat, 0.5), body)
        inner = toward(body, bc, 0.95)
        pygame.draw.polygon(surf, paint.warm(paint.shade(belly, 0.92), -0.12), inner)        # shaded belly
        pygame.draw.polygon(surf, coat, toward(body, bc, 0.9, lx * 0.6 * S, ly * 1.6 * S))  # lit flank
        # muscles: shoulder and haunch catch the light
        for c_, r_ in ((shoulder, 0.42), (hip, 0.48)):
            mc = (c_[0], c_[1] + d * 0.38)
            pygame.draw.polygon(surf, paint.warm(coat, 0.1), toward(body, mc, r_, lx * S, ly * S))
        pygame.draw.polygon(surf, paint.warm(coat, 0.22), toward(body, (top_mid[0], top_mid[1] + d * 0.15), 0.42,
                                                                 lx * S, ly * 2.2 * S))      # sunlit back
        if sp.get("patches"):
            for (px, py, r) in ((top_mid[0] - f * 2 * S, top_mid[1] + 5 * S, 5.5), (hip[0] + f * 2 * S, hip[1] + 4 * S, 3.5),
                                (shoulder[0] - f * 1 * S, shoulder[1] + 6 * S, 3.0)):
                pts = smooth_closed([(px + math.cos(k) * r * S * (1.0 + 0.3 * math.sin(k * 3)),
                                      py + math.sin(k) * r * S * 0.8) for k in [i * math.tau / 6 for i in range(6)]], 3)
                pygame.draw.polygon(surf, dark, pts)
        # fur strokes along the lie of the coat
        rng = __import__("random").Random(int(sp["L"]))
        fur = paint.warm(coat, -0.15)
        fur2 = paint.warm(coat, 0.15)
        for k in range(18):
            u = rng.uniform(0.05, 0.95)
            px = hip[0] + (shoulder[0] - hip[0]) * u
            py = top_mid[1] + d * rng.uniform(0.25, 0.85)
            pygame.draw.line(surf, fur if k % 2 else fur2, (px, py), (px - f * 2.5 * S, py + 1.2 * S), max(1, int(S * 0.4)))
        if sp.get("bristle"):
            for k in range(9):
                u = k / 8
                px = hip[0] + (shoulder[0] - hip[0]) * u
                py = hip[1] + (shoulder[1] - hip[1]) * u - 3 * S
                pygame.draw.line(surf, dark, (px, py + S), (px - f * 1.5 * S, py - 3 * S), max(1, int(S * 0.5)))
        if sp.get("udder"):
            ux = hip[0] + f * 5 * S
            pygame.draw.ellipse(surf, (236, 186, 180), (ux - 3 * S, top_mid[1] + d * 1.02, 6 * S, 4 * S))
    pygame.draw.polygon(surf, paint.shade(coat, 0.42), body, max(1, int(_EW[0] * 1.2)))
    # ---------------------------------------------------------------- head (over the chest)
    hl = sp["head"] * S
    ha = -0.9 + nod * 2 - grazing * 0.6 if a.species in ("horse", "deer") else -0.25 - grazing * 0.8
    if sp.get("round"):
        ha = -0.1
    he = (ne[0] + f * math.cos(ha) * hl, ne[1] - math.sin(ha) * hl)
    hw = d * (0.3 if a.species != "bear" else 0.42)
    mz = sp["muzzle"] * S * 0.5
    limb(surf, ne, he, hw, mz, coat)
    # the cheek (jowl) below the eye
    jc = (ne[0] + (he[0] - ne[0]) * 0.22, ne[1] + (he[1] - ne[1]) * 0.22 + hw * 0.15)
    pygame.draw.circle(surf, paint.warm(coat, -0.12), jc, hw * 0.8)
    pygame.draw.circle(surf, coat, (jc[0] + paint.LIGHT[0] * hw * 0.15, jc[1] + paint.LIGHT[1] * hw * 0.15), hw * 0.62)
    if a.species == "horse" and getattr(a, "blaze", (int(sp["L"]) + id(a)) % 3 == 0):
        paint.capsule(surf, (ne[0] + (he[0] - ne[0]) * 0.35, ne[1] + (he[1] - ne[1]) * 0.35 - hw * 0.5),
                      (he[0] - f * S, he[1] - mz * 0.4), S * 0.9, S * 0.6, (236, 230, 220))
    a._bit = (he[0] - f * 2 * S, he[1] + 1 * S)
    # eye, nostril, ears
    ex = ne[0] + (he[0] - ne[0]) * 0.3
    ey = ne[1] + (he[1] - ne[1]) * 0.3 - hw * 0.35
    pygame.draw.circle(surf, (20, 18, 16), (ex, ey), max(1.0, 1.0 * S))
    pygame.draw.circle(surf, (200, 200, 196), (ex - f * 0.3 * S, ey - 0.35 * S), max(0.5, 0.28 * S))
    if sp.get("snout"):
        pygame.draw.ellipse(surf, paint.shade(coat, 0.85), (he[0] - 2.5 * S, he[1] - 2.5 * S, 5 * S, 5 * S))
        pygame.draw.circle(surf, dark, (he[0] + f * S, he[1]), max(1.0, 0.8 * S))
    else:
        pygame.draw.circle(surf, paint.shade(dark, 1.1), (he[0] - f * 1 * S, he[1] - 0.5 * S), max(1.0, S * 0.9))
        pygame.draw.line(surf, paint.shade(coat, 0.55), (he[0] - f * 2.5 * S, he[1] + mz * 0.7),
                         (he[0] + f * 0.3 * S, he[1] + mz * 0.6), max(1, int(S * 0.5)))      # the mouth
    ear_l = sp["ears"] * S
    eb = (ne[0] + f * 1 * S, ne[1] - hw * 0.8)
    if sp.get("pointy") or a.species in ("horse", "deer"):
        paint.leaf(surf, paint.shade(coat, 0.5), eb[0] + f * 0.3 * S, eb[1] + S * 0.5, ear_l + _EW[0] * 1.5,
                   -math.pi / 2 - f * 0.25, 0.42)
        paint.leaf(surf, paint.shade(coat, 0.92), eb[0] + f * 0.3 * S, eb[1], ear_l, -math.pi / 2 - f * 0.25, 0.38)
        paint.leaf(surf, paint.shade(dark, 1.2), eb[0] + f * 0.3 * S, eb[1] - S * 0.3, ear_l * 0.7,
                   -math.pi / 2 - f * 0.25, 0.2)
    else:
        pygame.draw.polygon(surf, paint.shade(coat, 0.85), [eb, (eb[0] - f * ear_l, eb[1] - ear_l * 0.4),
                                                            (eb[0] - f * 1 * S, eb[1] + 1.5 * S)])
        pygame.draw.polygon(surf, paint.shade(coat, 0.5), [eb, (eb[0] - f * ear_l, eb[1] - ear_l * 0.4),
                                                           (eb[0] - f * 1 * S, eb[1] + 1.5 * S)], max(1, int(_EW[0])))
    if sp.get("horns"):
        paint.capsule(surf, eb, (eb[0] + f * 3 * S, eb[1] - 4 * S), 0.9 * S, 0.4 * S, (230, 220, 196))
    if sp.get("antlers") and getattr(a, "stag", True):
        b0 = (eb[0], eb[1] - 1 * S)
        b1 = (b0[0] - f * 3 * S, b0[1] - 10 * S)
        paint.capsule(surf, b0, b1, 0.9 * S, 0.5 * S, (208, 186, 150))
        for k in (0.35, 0.65, 0.95):
            px = b0[0] + (b1[0] - b0[0]) * k
            py = b0[1] + (b1[1] - b0[1]) * k
            paint.capsule(surf, (px, py), (px + f * 4 * S, py - 3 * S), 0.5 * S, 0.3 * S, (214, 194, 160))
    if sp.get("tusks"):
        paint.capsule(surf, (he[0] - f * 2 * S, he[1] + 1 * S), (he[0] + f * 0.5 * S, he[1] - 3 * S), 0.8 * S, 0.3 * S,
                      (244, 238, 224))
    if sp.get("mane"):
        paint.leaf(surf, dark, ne[0] + f * 0.5 * S, ne[1] - hw * 0.9, 3.6 * S, math.atan2(1.0, f * 0.8), 0.35)
    # ---------------------------------------------------------------- tack
    if a.species == "horse" and (a.owner is not None or a.rider is not None or getattr(a, "tethered", False)):
        tack = getattr(a, "tack", None) or ((110, 40, 30), (190, 160, 90))
        blanket, trim = tack
        sx = top_mid[0] + f * 3 * S
        sy = top_mid[1]
        bl = [(sx - 9 * S, sy - 1 * S), (sx + 8 * S, sy - 1 * S), (sx + 7 * S, sy + d * 0.62), (sx - 8 * S, sy + d * 0.62)]
        pygame.draw.polygon(surf, blanket, bl)
        pygame.draw.polygon(surf, paint.warm(blanket, 0.15), [bl[0], bl[1], (bl[1][0], bl[1][1] + d * 0.2),
                                                              (bl[0][0], bl[0][1] + d * 0.2)])
        pygame.draw.polygon(surf, paint.shade(blanket, 0.5), bl, max(1, int(_EW[0])))
        pygame.draw.line(surf, trim, (sx - 8 * S, sy + d * 0.62), (sx + 7 * S, sy + d * 0.62), max(1, int(1.5 * S)))
        sd = [(sx - 6 * S, sy - 4 * S), (sx + 6 * S, sy - 3 * S), (sx + 5 * S, sy + 1 * S), (sx - 5 * S, sy + 1 * S)]
        pygame.draw.polygon(surf, (86, 56, 34), sd)
        pygame.draw.line(surf, (128, 88, 56), sd[0], sd[1], max(1, int(S * 0.7)))
        pygame.draw.polygon(surf, (50, 32, 20), sd, max(1, int(_EW[0])))
        pygame.draw.line(surf, (86, 56, 34), (sx - 7 * S, sy - 6 * S), (sx - 5 * S, sy - 3 * S), max(1, int(2 * S)))
        # girth, stirrup, bridle, reins
        lw = max(1, int(S * 0.6))
        pygame.draw.line(surf, (70, 46, 30), (sx, sy), (sx - f * S, sy + d * 0.95), lw)
        stx = sx - f * 1 * S
        pygame.draw.line(surf, (60, 60, 64), (stx, sy + 1 * S), (stx, sy + d * 0.9), lw)
        pygame.draw.rect(surf, (90, 90, 96), (stx - 2 * S, sy + d * 0.9, 4 * S, 2 * S))
        pygame.draw.line(surf, (60, 40, 26), ne, he, lw)
        pygame.draw.line(surf, (60, 40, 26), (ne[0] + f * 1.5 * S, ne[1] - hw * 0.6), (he[0] - f * 2 * S, he[1] + S), lw)
        if a.rider is None or a.rider is True:
            pygame.draw.line(surf, (60, 40, 26), (he[0] - f * 2 * S, he[1]), (sx + f * 4 * S, sy - 4 * S), lw)
    return True


def draw_dead(surf, a, sp, cx, fy, S, coat, dark):
    L = sp["L"] * S
    d = sp["depth"] * S
    f = a.facing
    by = fy - d * 0.55
    body = [(cx - L * 0.5, fy), (cx - L * 0.45, by), (cx + L * 0.3, by - 2 * S), (cx + L * 0.5, fy - d * 0.2),
            (cx + L * 0.45, fy)]
    pygame.draw.polygon(surf, shade(coat, 0.85), body)
    pygame.draw.polygon(surf, shade(coat, 0.6), body, 1)
    for k, lx in enumerate((-0.35, -0.2, 0.2, 0.34)):
        x0 = cx + L * lx
        pygame.draw.line(surf, shade(coat, 0.7), (x0, by + d * 0.2), (x0 + f * (6 + k) * S, by - 6 * S),
                         max(1, int(2.4 * S)))
    hx = cx + f * L * 0.55
    pygame.draw.ellipse(surf, shade(coat, 0.85), (hx - 5 * S, fy - 6 * S, 10 * S, 6 * S))


def draw_horse_at(surf, cx, fy, f, phase, moving, gallop, coat=(120, 82, 52), tack=None, scale=1.0):
    """For formation sprites: a horse without an Animal object."""
    class _A:
        pass
    a = _A()
    a.species = "horse"
    a.facing = f
    a.vx = (215 if gallop else 80) if moving else 0
    a.walk_phase = phase
    a.anim_t = phase * 3
    a.hurt_flash = 0
    a.dead = False
    a.rider = True
    a.owner = True
    a.color = coat
    a.tack = tack
    draw_quadruped(surf, a, cx, fy, scale)
