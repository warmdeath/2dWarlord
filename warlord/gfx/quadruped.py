"""Quadrupeds with a real skeleton: four two-bone legs solved by inverse kinematics, driven by gaits.

Gaits follow the real footfall patterns:
  walk   — four beats, left hind → left fore → right hind → right fore, always three feet down
  trot   — diagonal pairs move together
  gallop — rotary: hinds then fores in quick succession, with a moment of suspension
Hind legs fold at the hock (the joint points backward), fore legs at the knee (points forward); the
body rocks and bobs with the gait, the neck nods against it, the tail swings with the wind.
Everything is drawn as faceted low-poly shapes with a lit and a shaded side, far legs darker.
"""
import math

import pygame

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


def limb(surf, a, b, wa, wb, col):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1
    nx, ny = -dy / d, dx / d
    p = [(a[0] + nx * wa, a[1] + ny * wa), (b[0] + nx * wb, b[1] + ny * wb), (b[0] - nx * wb, b[1] - ny * wb),
         (a[0] - nx * wa, a[1] - ny * wa)]
    pygame.draw.polygon(surf, col, p)
    lit = (nx * LIGHT[0] + ny * LIGHT[1]) > 0
    pygame.draw.polygon(surf, shade(col, 1.12), [p[0], p[1], b, a] if lit else [a, b, p[2], p[3]])


def gait_of(speed, sp):
    if speed < 3:
        return None, 0.0
    if speed > sp["L"] * 3.2:
        return "gallop", speed / (sp["L"] * 2.4)
    if speed > sp["L"] * 1.9:
        return "trot", speed / (sp["L"] * 1.6)
    return "walk", speed / (sp["L"] * 1.1)


def draw_quadruped(surf, a, cx, fy, scale=1.0):
    """a: an Animal. cx, fy: screen position of the feet centre."""
    sp = SPEC.get(a.species)
    if sp is None:
        return False
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
    bob = 0.0
    pitch = 0.0
    if gait == "gallop":
        bob = math.sin(t * math.tau) * 2.5 * S
        pitch = math.sin(t * math.tau + 0.8) * 0.09
    elif gait == "trot":
        bob = abs(math.sin(t * math.tau * 2)) * 1.6 * S
    elif gait == "walk":
        bob = math.sin(t * math.tau * 2) * 0.6 * S
    else:
        bob = math.sin(a.anim_t * 1.4) * 0.4 * S         # breathing
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
        limb(surf, root, knee, leg_w * 1.4, leg_w, c)
        limb(surf, knee, foot, leg_w, leg_w * 0.8, c)
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
        pts = [tb]
        for k in range(1, 6):
            u = k / 5
            pts.append((tb[0] - f * (tl * 0.45 * u + math.sin(a.anim_t * 2 + u * 2) * 2 * u),
                        tb[1] + tl * u * (0.9 - (0.5 if gait == "gallop" else 0.0) * u)))
        pygame.draw.lines(surf, dark, False, pts, int(4 * S))
        pygame.draw.lines(surf, shade(dark, 1.3), False, pts[:4], int(2 * S))
    else:
        te = (tb[0] - f * tl * 0.4, tb[1] + tl * 0.9)
        pygame.draw.line(surf, shade(coat, 0.8), tb, te, max(1, int(2 * S)))
    # ---------------------------------------------------------------- body
    d = sp["depth"] * S
    top_mid = ((hip[0] + shoulder[0]) / 2, (hip[1] + shoulder[1]) / 2 - (2 * S if a.species != "pig" else 3 * S))
    body = [
        (hip[0] - f * 5 * S, hip[1] + 2 * S),                     # rump
        (hip[0] - f * 2 * S, hip[1] - 3 * S),
        top_mid,                                                    # back
        (shoulder[0] + f * 1 * S, shoulder[1] - 3 * S),           # withers
        (shoulder[0] + f * 6 * S, shoulder[1] + d * 0.35),        # chest front
        (shoulder[0] + f * 3 * S, shoulder[1] + d * 0.85),
        (top_mid[0], top_mid[1] + d * (1.15 if not sp.get("round") else 1.25)),   # belly
        (hip[0] + f * 2 * S, hip[1] + d * 0.8),
    ]
    if sp.get("wool"):
        pygame.draw.polygon(surf, coat, body)
        for k in range(9):
            u = k / 8
            px = hip[0] + (shoulder[0] - hip[0]) * u
            py = (hip[1] + (shoulder[1] - hip[1]) * u) + d * 0.3
            pygame.draw.circle(surf, shade(coat, 1.05 if k % 2 else 0.96), (int(px), int(py - d * 0.2)),
                               int(d * 0.42))
            pygame.draw.circle(surf, shade(coat, 0.93), (int(px), int(py + d * 0.3)), int(d * 0.36))
    else:
        pygame.draw.polygon(surf, coat, body)
        # lit back, shaded belly: low-poly facets
        pygame.draw.polygon(surf, shade(coat, 1.12), [body[1], body[2], body[3], (top_mid[0], top_mid[1] + d * 0.4)])
        pygame.draw.polygon(surf, shade(belly, 0.96), [body[5], body[6], body[7], (top_mid[0], top_mid[1] + d * 0.6)])
        pygame.draw.polygon(surf, shade(coat, 0.86), [body[0], body[1], (top_mid[0], top_mid[1] + d * 0.4),
                                                      body[7]])
        if sp.get("patches"):
            pygame.draw.polygon(surf, dark, [(top_mid[0] - f * 4 * S, top_mid[1] + 2 * S),
                                             (top_mid[0] + f * 5 * S, top_mid[1] + 1 * S),
                                             (top_mid[0] + f * 6 * S, top_mid[1] + 7 * S),
                                             (top_mid[0] - f * 2 * S, top_mid[1] + 9 * S)])
            pygame.draw.circle(surf, dark, (int(hip[0] + f * 2 * S), int(hip[1] + 4 * S)), int(3 * S))
        if sp.get("bristle"):
            for k in range(6):
                u = k / 5
                px = hip[0] + (shoulder[0] - hip[0]) * u
                py = hip[1] + (shoulder[1] - hip[1]) * u - 3 * S
                pygame.draw.line(surf, dark, (px, py), (px - f * 1.5 * S, py - 3 * S), 1)
        if sp.get("udder"):
            ux = hip[0] + f * 5 * S
            pygame.draw.ellipse(surf, (236, 186, 180), (ux - 3 * S, top_mid[1] + d * 1.05, 6 * S, 4 * S))
    pygame.draw.polygon(surf, shade(coat, 0.55), body, 1)
    # ---------------------------------------------------------------- near legs
    for name in ("LH", "LF", "RH", "RF"):
        root, knee, foot, near = legs[name]
        if not near:
            continue
        c = coat
        limb(surf, root, knee, leg_w * 1.5, leg_w * 1.05, c)
        limb(surf, knee, foot, leg_w * 1.05, leg_w * 0.85, shade(c, 0.94))
        if sp.get("hoof"):
            pygame.draw.polygon(surf, dark, [(foot[0] - 2.6 * S, foot[1]), (foot[0] + 2.6 * S, foot[1]),
                                             (foot[0] + 2.1 * S, foot[1] - 3.2 * S),
                                             (foot[0] - 2.1 * S, foot[1] - 3.2 * S)])
        elif a.species in ("wolf", "bear"):
            pygame.draw.ellipse(surf, shade(dark, 1.2), (foot[0] - 3 * S + f * S, foot[1] - 2.5 * S, 6 * S, 3 * S))
    # ---------------------------------------------------------------- neck & head
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
        limb(surf, nb, ne, d * 0.38, d * 0.24, coat)
    hl = sp["head"] * S
    ha = -0.9 + nod * 2 - grazing * 0.6 if a.species in ("horse", "deer") else -0.25 - grazing * 0.8
    if sp.get("round"):
        ha = -0.1
    he = (ne[0] + f * math.cos(ha) * hl, ne[1] - math.sin(ha) * hl)
    hw = d * (0.3 if a.species != "bear" else 0.42)
    mz = sp["muzzle"] * S * 0.5
    limb(surf, ne, he, hw, mz, coat)
    # eye, nostril, ears
    ex = ne[0] + (he[0] - ne[0]) * 0.3
    ey = ne[1] + (he[1] - ne[1]) * 0.3 - hw * 0.35
    pygame.draw.circle(surf, (20, 18, 16), (int(ex), int(ey)), max(1, int(1.2 * S)))
    if sp.get("snout"):
        pygame.draw.ellipse(surf, shade(coat, 0.85), (he[0] - 2.5 * S, he[1] - 2.5 * S, 5 * S, 5 * S))
        pygame.draw.circle(surf, dark, (int(he[0] + f * S), int(he[1])), max(1, int(0.8 * S)))
    else:
        pygame.draw.circle(surf, shade(dark, 1.1), (int(he[0] - f * 1 * S), int(he[1] - 0.5 * S)), max(1, int(S)))
    ear_l = sp["ears"] * S
    eb = (ne[0] + f * 1 * S, ne[1] - hw * 0.8)
    if sp.get("pointy") or a.species in ("horse", "deer"):
        pygame.draw.polygon(surf, shade(coat, 0.9), [eb, (eb[0] - f * 1.5 * S, eb[1] - ear_l),
                                                     (eb[0] + f * 1.8 * S, eb[1] - 0.5 * S)])
    else:
        pygame.draw.polygon(surf, shade(coat, 0.85), [eb, (eb[0] - f * ear_l, eb[1] - ear_l * 0.4),
                                                      (eb[0] - f * 1 * S, eb[1] + 1.5 * S)])
    if sp.get("horns"):
        pygame.draw.line(surf, (230, 220, 196), eb, (eb[0] + f * 3 * S, eb[1] - 4 * S), max(1, int(1.6 * S)))
    if sp.get("antlers") and getattr(a, "stag", True):
        b0 = (eb[0], eb[1] - 1 * S)
        b1 = (b0[0] - f * 3 * S, b0[1] - 10 * S)
        pygame.draw.line(surf, (208, 186, 150), b0, b1, max(1, int(1.6 * S)))
        for k in (0.35, 0.65, 0.95):
            px = b0[0] + (b1[0] - b0[0]) * k
            py = b0[1] + (b1[1] - b0[1]) * k
            pygame.draw.line(surf, (208, 186, 150), (px, py), (px + f * 4 * S, py - 3 * S), 1)
    if sp.get("tusks"):
        pygame.draw.line(surf, (244, 238, 224), (he[0] - f * 2 * S, he[1] + 1 * S), (he[0] + f * 0.5 * S,
                                                                                      he[1] - 3 * S), 2)
    if sp.get("mane"):
        for k in range(6):
            u = k / 5
            px = nb[0] + (ne[0] - nb[0]) * u
            py = nb[1] + (ne[1] - nb[1]) * u - d * 0.26
            fl = math.sin(a.anim_t * 3 + k) * 1.2 + (2.5 if gait == "gallop" else 0)
            pygame.draw.line(surf, dark, (px, py), (px - f * (3 + fl) * S, py + (2 - fl * 0.3) * S),
                             max(1, int(2 * S)))
    # ---------------------------------------------------------------- tack
    if a.species == "horse" and (a.owner is not None or a.rider is not None or getattr(a, "tethered", False)):
        tack = getattr(a, "tack", None) or ((110, 40, 30), (190, 160, 90))
        blanket, trim = tack
        sx = top_mid[0] + f * 3 * S
        sy = top_mid[1]
        pygame.draw.polygon(surf, blanket, [(sx - 9 * S, sy - 1 * S), (sx + 8 * S, sy - 1 * S),
                                            (sx + 7 * S, sy + d * 0.62), (sx - 8 * S, sy + d * 0.62)])
        pygame.draw.line(surf, trim, (sx - 8 * S, sy + d * 0.62), (sx + 7 * S, sy + d * 0.62), max(1, int(1.5 * S)))
        pygame.draw.polygon(surf, (86, 56, 34), [(sx - 6 * S, sy - 4 * S), (sx + 6 * S, sy - 3 * S),
                                                 (sx + 5 * S, sy + 1 * S), (sx - 5 * S, sy + 1 * S)])
        pygame.draw.line(surf, (86, 56, 34), (sx - 7 * S, sy - 6 * S), (sx - 5 * S, sy - 3 * S), max(1, int(2 * S)))
        # girth, stirrup, bridle, reins
        pygame.draw.line(surf, (70, 46, 30), (sx, sy), (sx - f * S, sy + d * 0.95), 1)
        stx = sx - f * 1 * S
        pygame.draw.line(surf, (60, 60, 64), (stx, sy + 1 * S), (stx, sy + d * 0.9), 1)
        pygame.draw.rect(surf, (90, 90, 96), (stx - 2 * S, sy + d * 0.9, 4 * S, 2 * S))
        pygame.draw.line(surf, (60, 40, 26), ne, he, 1)
        pygame.draw.line(surf, (60, 40, 26), (he[0] - f * 2 * S, he[1]), (sx + f * 4 * S, sy - 4 * S), 1)
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
