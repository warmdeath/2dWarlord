"""Modular skeletal animation for humanoids.

A character = skeleton (bones with lengths) + layered poses + modular parts.
  * locomotion layer  -> legs, hip height, torso lean (walk/run/crouch/swim/climb/ride/...)
  * action layer      -> arms + weapon angle (combo swings, thrusts, blocks, bow draw, work...)
  * parts             -> body, clothes by social rank, armour, helmet, tabard heraldry, weapon, shield
Angles: 0 = limb hanging down, +pi/2 = pointing forward (toward facing), pi = up.
"""
import math

import pygame

from ..combat.weapons import HELMETS
from . import paint

THIGH, SHIN = 9.5, 9.5
TORSO = 15.0
UPPER, FORE = 8.0, 8.0
HEAD_R = 5.0


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def vec(a, length):
    return math.sin(a) * length, math.cos(a) * length


def dark(c, f=0.72):
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f))


class Pose:
    __slots__ = ("hip_y", "lean", "thf", "shf", "thb", "shb", "uaf", "faf", "uab", "fab", "wa", "bob", "rot",
                 "draw", "shield_up", "weapon_mode", "head_tilt")

    def __init__(self):
        self.hip_y = -(THIGH + SHIN)
        self.lean = 0.0
        self.thf = self.shf = self.thb = self.shb = 0.0
        self.uaf, self.faf = 0.35, 0.25
        self.uab, self.fab = -0.2, 0.1
        self.wa = None          # weapon angle override (local, 0=forward, -pi/2=up)
        self.bob = 0.0
        self.rot = 0.0          # whole-body rotation (lying/dead)
        self.draw = 0.0         # bow draw
        self.shield_up = False
        self.weapon_mode = "hand"  # hand / sheathed / shoulder
        self.head_tilt = 0.0


def legs_walk(p, phase, amp, knee):
    s = math.sin(phase)
    p.thf = s * amp
    p.thb = -s * amp
    p.shf = -max(0.0, -math.cos(phase)) * knee - 0.1
    p.shb = -max(0.0, math.cos(phase)) * knee - 0.1


def compute_pose(h):
    p = Pose()
    st = h.state
    t = h.anim_t
    wd = h.weapon_def
    pole = wd is not None and "polearm" in wd.flags
    # ---------------------------------------------------------------- locomotion layer
    if st in ("idle", "work", "talk"):
        p.bob = math.sin(t * 2.2) * 0.6
        p.thf, p.thb = 0.08, -0.08
    elif st == "walk":
        legs_walk(p, h.walk_phase, 0.55, 0.9)
        p.bob = abs(math.sin(h.walk_phase)) * -1.2
        p.uaf, p.uab = -math.sin(h.walk_phase) * 0.45 + 0.1, math.sin(h.walk_phase) * 0.45
        p.lean = 0.05
    elif st == "run":
        legs_walk(p, h.walk_phase, 0.85, 1.6)
        p.bob = abs(math.sin(h.walk_phase)) * -2.5
        p.lean = 0.28
        p.uaf, p.faf = -math.sin(h.walk_phase) * 0.9 + 0.2, 1.2
        p.uab, p.fab = math.sin(h.walk_phase) * 0.9, 1.2
    elif st in ("crouch", "sneak"):
        k = 1.25
        ph = h.walk_phase
        p.thf, p.shf = 1.25 + math.sin(ph) * 0.25, -1.25 * k
        p.thb, p.shb = 0.6 - math.sin(ph) * 0.25, -1.4 * k
        p.hip_y = -(THIGH + SHIN) * 0.62
        p.lean = 0.42
        p.uaf, p.uab = 0.6, 0.3
    elif st == "slide":
        p.rot = -0.9
        p.thf, p.shf = 1.4, -0.2
        p.thb, p.shb = 0.6, -1.8
        p.uaf, p.uab = 2.6, 2.2
    elif st == "jump":
        p.thf, p.shf = 0.9, -1.4
        p.thb, p.shb = -0.2, -0.6
        p.uaf, p.uab = 2.2, 1.6
    elif st == "fall":
        p.thf, p.shf = 0.4, -0.4
        p.thb, p.shb = -0.3, -0.2
        p.uaf, p.uab = 2.6 + math.sin(t * 14) * 0.3, 2.3 - math.sin(t * 14) * 0.3
    elif st == "swim":
        p.rot = 1.15
        ph = t * 6
        p.thf, p.thb = math.sin(ph) * 0.4, -math.sin(ph) * 0.4
        p.shf = p.shb = -0.2
        a = (t * 3.5) % math.tau
        p.uaf = math.pi - a * 0.5 if a < math.pi else (a - math.pi) * 0.5 + math.pi / 2
        p.uab = p.uaf + math.pi
        p.faf = p.fab = 0.3
        p.weapon_mode = "sheathed"
    elif st == "climb":
        ph = h.walk_phase * 1.4
        p.thf, p.shf = 0.7 + math.sin(ph) * 0.5, -1.2
        p.thb, p.shb = 0.7 - math.sin(ph) * 0.5, -1.2
        p.uaf, p.uab = 2.7 + math.sin(ph) * 0.3, 2.7 - math.sin(ph) * 0.3
        p.faf = p.fab = 0.2
        p.weapon_mode = "sheathed"
    elif st == "ride":
        # astride: thighs down and forward around the barrel, lower legs back to the stirrups
        gallop = abs(h.vx) > 150
        p.thf, p.shf = 0.85, -1.05
        p.thb, p.shb = 0.7, -1.0
        p.hip_y = -(THIGH + SHIN) * 0.8
        p.bob = 0.0
        p.lean = 0.32 if gallop else 0.12
        # both hands on the reins, low over the withers
        p.uaf, p.faf = 0.95, 0.75
        p.uab, p.fab = 0.8, 0.85
    elif st in ("sit",):
        p.thf, p.shf = 1.5, -1.5
        p.thb, p.shb = 1.4, -1.5
        p.hip_y = -SHIN * 0.9
    elif st == "kneel":
        p.thf, p.shf = 1.4, -1.5
        p.thb, p.shb = -0.1, -1.55
        p.hip_y = -(THIGH + SHIN) * 0.55
        p.lean = 0.25
        p.uaf, p.faf = 0.6, 0.8
        p.head_tilt = 0.4
    elif st in ("sleep", "dead"):
        p.rot = -math.pi / 2 if st == "dead" else -math.pi / 2
        p.uaf, p.uab = 0.3, -0.2
        p.weapon_mode = "sheathed" if st == "sleep" else "hand"
    elif st == "stagger":
        p.lean = -0.35
        p.thf, p.shf = 0.4, -0.3
        p.uaf, p.uab = 1.8 + math.sin(t * 20) * 0.2, 1.4
    elif st == "cheer":
        p.uaf, p.faf = 2.9 + math.sin(t * 10) * 0.15, 0.1
        p.uab, p.fab = 2.6, 0.3
        p.bob = -abs(math.sin(t * 8)) * 3

    # ---------------------------------------------------------------- action layer (arms + weapon)
    act = h.action
    if wd is not None and wd.key != "fists" and p.weapon_mode == "hand":
        if pole:
            p.uaf, p.faf = 0.9, 0.85
            p.uab, p.fab = 0.7, 1.2
            p.wa = -0.25 if st not in ("run",) else -0.05
            if getattr(h, "formation_stance", None) == "igel":
                p.wa = -0.18
                p.uaf, p.faf = 0.7, 1.0
        elif wd.kind == "bow":
            p.uaf, p.faf = 0.5, 0.3
            p.wa = -1.3
        elif wd.kind == "crossbow":
            p.uaf, p.faf = 0.9, 1.3
            p.wa = 0.0
        elif not h.weapon_drawn:
            p.weapon_mode = "sheathed"
        else:
            p.uaf, p.faf = 0.55 if st != "run" else p.uaf, 1.1
            p.wa = -0.95
    if act is not None:
        kind = act["kind"]
        if kind == "attack":
            mv = act["move"]
            el = act["t"]
            wu, ac, rc = mv.windup, mv.active, mv.recover
            if el < wu:
                ph, k = 0, ease(el / wu)
            elif el < wu + ac:
                ph, k = 1, ease((el - wu) / ac)
            else:
                ph, k = 2, ease((el - wu - ac) / rc)
            arc = mv.arc
            if pole and arc in ("swing", "backswing"):
                arc = "thrust"
            p.weapon_mode = "hand"
            if arc == "swing":
                keys = [(0.6, 1.0, -0.9), (2.7, 0.4, -2.3), (0.9, 0.3, 0.45), (0.6, 1.0, -0.9)]
            elif arc == "backswing":
                keys = [(0.9, 0.3, 0.45), (1.9, 1.6, 0.8), (1.4, 0.2, -1.6), (0.6, 1.0, -0.9)]
            elif arc == "overhead":
                keys = [(0.6, 1.0, -0.9), (3.0, 0.0, -2.8), (0.8, 0.3, 0.6), (0.6, 1.0, -0.9)]
            elif arc in ("thrust", "stab"):
                pull = -0.5 if pole else 0.6
                keys = [(1.0, 0.8, -0.25), (pull, 1.6, -0.1), (1.55, 0.05, -0.02), (1.0, 0.8, -0.25)]
                if pole:
                    p.uab, p.fab = lerp(0.4, 1.4, k if ph == 1 else (1 - k if ph == 2 else 0)), 0.8
            elif arc == "low":
                keys = [(0.6, 1.0, -0.9), (1.8, 0.3, -1.9), (0.5, 0.4, 0.9), (0.6, 1.0, -0.9)]
            else:  # plunge
                keys = [(2.8, 0.1, -2.6), (2.8, 0.1, -2.6), (0.6, 0.6, 1.4), (0.8, 0.6, 0.8)]
            a, b = keys[ph], keys[ph + 1]
            p.uaf = lerp(a[0], b[0], k)
            p.faf = lerp(a[1], b[1], k)
            p.wa = lerp(a[2], b[2], k)
            if arc in ("thrust", "stab") and ph == 1:
                p.lean = max(p.lean, 0.3)
            if arc == "overhead" and ph == 1:
                p.lean = max(p.lean, 0.25)
            if wd is None or wd.key == "fists":
                p.wa = None
        elif kind == "block":
            p.weapon_mode = "hand"
            if h.shield is not None:
                p.shield_up = True
                p.uab, p.fab = 1.5, 0.6
                p.uaf, p.faf, p.wa = 0.8, 0.9, -1.1
            elif pole:
                p.uaf, p.faf, p.wa = 1.2, 1.0, -0.9
                if h.state == "crouch":
                    p.wa = -0.12  # braced
            else:
                p.uaf, p.faf, p.wa = 1.1, 1.4, -1.45
                p.uab, p.fab = 1.0, 1.4
        elif kind == "bow":
            d = act.get("draw", 0.0)
            aim = act.get("aim", 0.0)
            p.uaf, p.faf = math.pi / 2 - aim, 0.0
            p.uab, p.fab = math.pi / 2 - aim - 0.1, math.pi * 0.95 * ease(d) * 0.9
            p.wa = -math.pi / 2
            p.draw = d
            p.weapon_mode = "hand"
            act["_aim"] = aim
        elif kind == "crossbow":
            aim = act.get("aim", 0.0)
            p.uaf, p.faf = math.pi / 2 - aim, 0.2
            p.uab, p.fab = math.pi / 2 - aim - 0.2, 0.5
            p.wa = aim
            if act.get("reload", 0) > 0:
                r = act["reload"]
                p.uaf, p.faf = 0.6, 1.2
                p.uab, p.fab = 0.4 + math.sin(r * 10) * 0.5, 1.5
                p.wa = 1.2
        elif kind == "work":
            ph = (h.anim_t * act.get("speed", 3.0)) % 1.0
            style = act.get("style", "hammer")
            if style == "hammer":
                p.uaf = lerp(2.5, 0.9, ease(ph * 2) if ph < 0.5 else 1 - ease((ph - 0.5) * 2))
                p.faf, p.wa = 0.6, -1.2
            elif style == "harvest":
                p.lean = 0.7
                p.uaf, p.faf = lerp(0.3, 1.2, math.sin(ph * math.tau) * 0.5 + 0.5), 0.6
                p.uab = p.uaf - 0.4
                p.wa = 0.6
            elif style == "chop":
                p.uaf = lerp(2.4, 1.0, ph)
                p.uab = p.uaf - 0.2
                p.faf, p.wa = 0.5, -1.0
            elif style == "pray":
                p.uaf, p.faf = 0.9, 2.0
                p.uab, p.fab = 0.9, 2.0
                p.head_tilt = 0.3
            elif style == "fish":
                p.uaf, p.faf, p.wa = 1.6, 0.3, -0.7
            elif style == "stir":
                p.uaf = 1.0 + math.sin(ph * math.tau) * 0.3
                p.faf, p.wa = 0.8, 1.2
        elif kind == "use":
            ph = act["t"] / max(0.01, act["dur"])
            p.uaf = lerp(2.4, 0.7, ease(ph))
            p.faf, p.wa = 0.5, lerp(-2.0, 0.3, ease(ph))
            p.weapon_mode = "hand"
    if h.stagger > 0 and st != "dead":
        p.lean -= 0.3
    return p


# ================================================================== pose blending
ANGLES = ("hip_y", "lean", "thf", "shf", "thb", "shb", "uaf", "faf", "uab", "fab", "bob", "rot", "head_tilt")


def blend_pose(prev, new, k):
    """Ease the new pose toward from the previous one: no more snapping between states."""
    if prev is None:
        return new
    for a in ANGLES:
        pv = getattr(prev, a)
        setattr(new, a, pv + (getattr(new, a) - pv) * k)
    if prev.wa is not None and new.wa is not None:
        d = (new.wa - prev.wa + math.pi) % math.tau - math.pi
        new.wa = prev.wa + d * k
    return new


def apply_body_state(p, h):
    """Injuries and impacts bend the pose: limping legs, a hanging arm, a landing squash."""
    inj = getattr(h, "injury", None)
    if inj:
        if inj.get("arm_w", 0) >= 2 and p.weapon_mode != "sheathed":
            p.uaf, p.faf, p.wa = 0.15, 0.1, 1.3
        if inj.get("arm_s", 0) >= 2:
            p.uab, p.fab = 0.1, 0.05
            p.shield_up = False
        leg = inj.get("legs", 0)
        if leg >= 1 and h.state in ("walk", "run"):
            ph = h.walk_phase
            p.thb *= 0.35
            p.shb = -0.3
            p.bob += abs(math.sin(ph)) * 2.2 * leg
            p.lean += 0.12 * leg
        if inj.get("head", 0) >= 2:
            p.head_tilt += math.sin(h.anim_t * 3) * 0.12
    lt = getattr(h, "land_t", 0.0)
    if lt > 0:
        k = lt / 0.18
        p.hip_y += 5 * k
        p.thf += 0.6 * k
        p.shf -= 0.9 * k
        p.thb += 0.5 * k
        p.shb -= 0.9 * k
        p.lean += 0.15 * k
    return p


# ================================================================== skeleton (shared by animation and ragdoll physics)
JOINTS = ("hip", "sh", "head", "kb", "fb", "kf", "ff", "eb", "hb", "ef", "hf")
NECK = 2.5 + HEAD_R
STICKS = (("hip", "sh"), ("sh", "head"), ("hip", "kb"), ("kb", "fb"), ("hip", "kf"), ("kf", "ff"),
          ("sh", "eb"), ("eb", "hb"), ("sh", "ef"), ("ef", "hf"), ("hip", "head"), ("kb", "kf"))


def skeleton(p):
    """Local joint positions (x = forward, y = down) relative to the feet centre."""
    hip = (0.0, p.hip_y + p.bob) if not p.rot else (0.0, -6.0)
    lean = p.lean
    sh = (hip[0] + math.sin(lean) * TORSO, hip[1] - math.cos(lean) * TORSO)
    ht = lean + p.head_tilt
    head = (sh[0] + math.sin(ht) * NECK, sh[1] - math.cos(ht) * NECK)

    def limb(a1, l1, a2, l2, start):
        dx, dy = vec(a1, l1)
        j = (start[0] + dx, start[1] + dy)
        dx2, dy2 = vec(a1 + a2, l2)
        return j, (j[0] + dx2, j[1] + dy2)

    kb, fb = limb(p.thb, THIGH, p.shb, SHIN, hip)
    kf, ff = limb(p.thf, THIGH, p.shf, SHIN, hip)
    eb, hb = limb(p.uab, UPPER, p.fab, FORE, sh)
    ef, hf = limb(p.uaf, UPPER, p.faf, FORE, sh)
    return {"hip": hip, "sh": sh, "head": head, "kb": kb, "fb": fb, "kf": kf, "ff": ff, "eb": eb, "hb": hb,
            "ef": ef, "hf": hf}


def place(J, sx, sy, f, rot, scale=1.0):
    """Local skeleton -> screen/world points."""
    out = {}
    c, s = math.cos(rot * f), math.sin(rot * f)
    oy = sy - (4 if rot else 0)
    for k, (lx, ly) in J.items():
        lx, ly = lx * scale, ly * scale
        if rot:
            lx, ly = lx * c - ly * s, lx * s + ly * c
        out[k] = (sx + lx * f, oy + ly)
    return out


def world_joints(h):
    return place(skeleton(h.pose), h.cx, h.feet, h.facing, h.pose.rot)


# ================================================================== painted primitives
LIGHT = paint.LIGHT      # light comes from the upper left
_EDGE = [1.0]            # current outline width (scaled with the supersampling)


def shade(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def quad(surf, a, b, wa, wb, color, facet=True):
    """A tapered limb segment, painted: a darker rim, the colour, a cool shadow away from the light and a warm
    highlight toward it."""
    if facet:
        paint.soft_limb(surf, a, b, wa, wb, color, edge=_EDGE[0], lit=wa > 1.2 * _EDGE[0])
    else:
        paint.capsule(surf, a, b, wa + _EDGE[0], wb + _EDGE[0], shade(color, 0.5))
        paint.capsule(surf, a, b, wa, wb, color)


def frame(origin, fwd, down):
    def T(x, y):
        return (origin[0] + fwd[0] * x + down[0] * y, origin[1] + fwd[1] * x + down[1] * y)
    return T


def poly(surf, T, pts, color, width=0):
    if width:
        pygame.draw.polygon(surf, color, [T(x, y) for x, y in pts], max(1, int(_EDGE[0] * 1.2)))
    else:
        pygame.draw.polygon(surf, color, [T(x, y) for x, y in pts])


def edge(surf, T, pts, color):
    """Outline a shape in a dark shade of its own colour (never plain black)."""
    pygame.draw.polygon(surf, shade(color, 0.45), [T(x, y) for x, y in pts], max(1, int(_EDGE[0] * 1.2)))


def painted(surf, T, pts, color, light_shift=0.9, S=1.0):
    """A filled shape with soft painted shading in its own frame: shadowed body, lit inset toward the light."""
    W = [T(x, y) for x, y in pts]
    pygame.draw.polygon(surf, paint.warm(color, -0.2), W)
    cx = sum(p[0] for p in W) / len(W)
    cy = sum(p[1] for p in W) / len(W)
    sh = light_shift * S
    pygame.draw.polygon(surf, color, [(cx + (x - cx) * 0.86 + LIGHT[0] * sh, cy + (y - cy) * 0.9 + LIGHT[1] * sh)
                                      for x, y in W])
    pygame.draw.polygon(surf, paint.warm(color, 0.16), [(cx + (x - cx) * 0.45 + LIGHT[0] * sh * 2.2,
                                                         cy + (y - cy) * 0.5 + LIGHT[1] * sh * 2.2) for x, y in W])
    pygame.draw.polygon(surf, shade(color, 0.45), W, max(1, int(_EDGE[0] * 1.2)))


OUTLINE = (26, 22, 22)


# ================================================================== the humanoid renderer
def draw_humanoid(surf, h, sx, sy, scale=1.0, tint=None):
    """sx, sy = screen position of the feet centre. Dead humanoids are drawn from their ragdoll.

    The figure is painted at twice the size into a scratch canvas and shrunk with smoothing, which gives
    clean anti-aliased edges and lets details (eyes, buckles, folds) survive at the small size."""
    SSf = paint.SS
    wd = h.weapon_def
    reach = max(26.0, (wd.length if wd is not None else 10) + 14) * scale
    R = int(max(30 * scale, reach) + 8)
    top = int(R + 30 * scale)
    bot = int(R * 0.6 + 8)
    canvas = paint.CANVAS.get(2 * R * SSf, (top + bot) * SSf)
    _draw_humanoid(canvas, h, R * SSf, top * SSf, scale * SSf, tint, SSf, sx, sy)
    small = paint.shrink(canvas, SSf)
    surf.blit(small, (int(sx) - R, int(sy) - top))


def _draw_humanoid(surf, h, sx, sy, scale, tint, ss, osx, osy):
    f = h.facing
    L = h.look
    _EDGE[0] = 0.55 * scale
    rd = getattr(h, "ragdoll", None)
    if rd is not None and rd.points:
        J = {k: (sx + (v[0] - h.cx) * ss, sy + (v[1] - h.feet) * ss) for k, v in rd.points.items()}
        p = h.pose
    else:
        p = h.pose
        J = place(skeleton(p), sx, sy, f, p.rot, scale)
    hip, sh, head = J["hip"], J["sh"], J["head"]
    ux, uy = sh[0] - hip[0], sh[1] - hip[1]
    ul = math.hypot(ux, uy) or 1.0
    ux, uy = ux / ul, uy / ul                       # up the spine
    fwd = (-uy * f, ux * f)                         # towards facing, perpendicular to the spine
    down = (-ux, -uy)
    S = scale
    skin = L["skin"]
    tunic = L["tunic"]
    hose = L["hose"]
    boots = L.get("boots", (60, 44, 32))
    armor = h.armor
    plated = armor is not None and armor.style in ("mail", "plate")
    body_c = armor.color if plated else tunic
    if tint:
        skin = tunic = hose = boots = body_c = tint
    inj = getattr(h, "injury", None) or {}
    wd = h.weapon_def
    # -------------------------------------------------- back layer: sheathed weapon, back arm, back leg
    if wd is not None and p.weapon_mode == "sheathed" and wd.key != "fists" and not tint:
        Tb = frame(hip, fwd, down)
        _draw_weapon(surf, wd, Tb(-3 * S, -2 * S), Tb(-3 * S - wd.length * 0.45 * S, 8 * S), f, S, sheathed=True)
    back = 0.72
    quad(surf, J["sh"], J["eb"], 2.4 * S, 2.0 * S, shade(body_c if plated else tunic, back))
    quad(surf, J["eb"], J["hb"], 1.9 * S, 1.5 * S, shade(body_c if plated else skin, back))
    pygame.draw.circle(surf, shade(skin, back * 0.9), J["hb"], 1.9 * S)
    quad(surf, hip, J["kb"], 2.9 * S, 2.2 * S, shade(hose, back))
    quad(surf, J["kb"], J["fb"], 2.2 * S, 1.7 * S, shade(hose, back))
    _foot(surf, J["kb"], J["fb"], f, shade(boots, back), S)
    if h.shield is not None and not p.shield_up and not tint:
        if getattr(h, "mount", None) is not None:
            # riding: the shield hangs from the saddle by its strap, behind the rider's leg
            _draw_shield(surf, h, (hip[0] - f * 11 * S, hip[1] + 10 * S), f, S * 0.9, raised=False)
            pygame.draw.line(surf, (70, 46, 28), (hip[0] - f * 6 * S, hip[1] + 1 * S),
                             (hip[0] - f * 11 * S, hip[1] + 5 * S), max(1, int(S * 0.6)))
        else:
            _draw_shield(surf, h, J["hb"], f, S, raised=False)
    # -------------------------------------------------- torso
    Tt = frame(hip, fwd, down)
    tl = ul / S
    robe = L.get("robe", False)
    hem = 17 if robe else 6.0
    hw = 6.4 if robe else 5.8
    torso = [(-4.4, -tl - 0.4), (-1.0, -tl - 1.0), (3.0, -tl - 0.6), (4.6, -tl * 0.8), (5.1, -tl * 0.5),
             (4.4, -tl * 0.15), (4.6, 0), (hw * 0.95, hem * 0.6), (hw + 0.2, hem), (0, hem + 0.6),
             (-(hw + 0.4), hem), (-hw * 0.95, hem * 0.6), (-4.8, 0), (-4.9, -tl * 0.45), (-4.9, -tl * 0.8)]
    torso = [(x * S, y * S) for x, y in torso]
    if tint:
        poly(surf, Tt, torso, body_c)
    else:
        painted(surf, Tt, torso, body_c, 0.9, S)
        if armor is not None and armor.style == "mail":
            for k in range(1, 6):
                y = -tl * S * k / 6
                pygame.draw.line(surf, shade(body_c, 0.8), Tt(-4.4 * S, y), Tt(4.4 * S, y), max(1, int(S * 0.5)))
            for k in range(-2, 3):
                pygame.draw.line(surf, shade(body_c, 1.12), Tt(k * 1.8 * S, -tl * S * 0.9), Tt(k * 1.8 * S, -tl * S * 0.1),
                                 max(1, int(S * 0.3)))
        if armor is not None and armor.style == "plate":
            painted(surf, Tt, [(-3.6 * S, -tl * 0.88 * S), (3.8 * S, -tl * 0.88 * S), (4.4 * S, -tl * 0.4 * S),
                               (3.4 * S, -tl * 0.12 * S), (-3.8 * S, -tl * 0.15 * S)], shade(body_c, 1.08), 0.6, S)
            pygame.draw.line(surf, paint.warm(body_c, 0.5), Tt(1.6 * S, -tl * 0.8 * S), Tt(2.6 * S, -tl * 0.35 * S),
                             max(1, int(S * 0.7)))
        tab = L.get("tabard")
        if tab:
            c1, c2 = tab
            tb = [(-3.4 * S, -tl * 0.95 * S), (3.4 * S, -tl * 0.95 * S), (4.0 * S, hem * 0.9 * S),
                  (-4.2 * S, hem * 0.9 * S)]
            painted(surf, Tt, tb, c1, 0.7, S)
            poly(surf, Tt, [(0, -tl * 0.74 * S), (1.7 * S, -tl * 0.52 * S), (0, -tl * 0.3 * S),
                            (-1.7 * S, -tl * 0.52 * S)], c2)
        elif not plated:
            # cloth folds: soft creases falling from the belt and across the chest
            fc = paint.warm(body_c, -0.28)
            w_ = max(1, int(S * 0.6))
            for fx_ in (-2.2, 0.8, 3.4):
                pygame.draw.line(surf, fc, Tt(fx_ * S, 1.0 * S), Tt((fx_ + 0.6) * S, (hem - 0.8) * S), w_)
            pygame.draw.line(surf, fc, Tt(-3.4 * S, -tl * 0.62 * S), Tt(1.0 * S, -tl * 0.5 * S), w_)
            # the neckline
            pygame.draw.line(surf, shade(body_c, 0.6), Tt(0.4 * S, -tl * S), Tt(2.6 * S, -tl * 0.82 * S),
                             max(1, int(S * 0.7)))
        trim = L.get("trim")
        if trim:
            pygame.draw.line(surf, trim, Tt(-hw * S, hem * S), Tt(hw * S, hem * S), max(1, int(S)))
            pygame.draw.line(surf, trim, Tt(-4.4 * S, -tl * S), Tt(3.0 * S, -tl * S), max(1, int(S)))
        belt = L.get("belt", (70, 50, 30))
        pygame.draw.line(surf, belt, Tt(-4.9 * S, -0.5 * S), Tt(4.7 * S, -0.5 * S), max(2, int(S * 1.2)))
        bk = Tt(3.0 * S, -0.5 * S)
        pygame.draw.rect(surf, (186, 160, 90), (bk[0] - S * 0.8, bk[1] - S * 0.8, S * 1.6, S * 1.6),
                         max(1, int(S * 0.4)))
        if L.get("purse", True) and not plated:
            pp = Tt(-2.0 * S, 1.6 * S)
            pygame.draw.ellipse(surf, shade(belt, 1.25), (pp[0] - S * 1.2, pp[1] - S, S * 2.4, S * 2.8))
        if inj.get("torso", 0) >= 1:
            pygame.draw.circle(surf, (130, 20, 20), Tt(1.0 * S, -tl * 0.45 * S), max(1, int((1 + inj["torso"]) * S * 0.8)))
    # -------------------------------------------------- front leg
    quad(surf, hip, J["kf"], 3.0 * S, 2.3 * S, hose)
    quad(surf, J["kf"], J["ff"], 2.3 * S, 1.8 * S, hose)
    mid = ((J["kf"][0] + J["ff"][0] * 2) / 3, (J["kf"][1] + J["ff"][1] * 2) / 3)
    quad(surf, mid, J["ff"], 2.1 * S, 1.9 * S, boots)
    _foot(surf, J["kf"], J["ff"], f, boots, S)
    if inj.get("legs", 0) >= 1 and not tint:
        pygame.draw.circle(surf, (130, 20, 20), J["kf"], (1 + inj["legs"]) * S * 0.7)
    # -------------------------------------------------- head
    hu = (head[0] - sh[0], head[1] - sh[1])
    hl = math.hypot(*hu) or 1.0
    hdown = (-hu[0] / hl, -hu[1] / hl)
    hfwd = (f * hdown[1], -f * hdown[0])      # perpendicular to the neck, towards facing
    Th = frame(head, hfwd, hdown)
    # neck
    quad(surf, sh, (head[0] - hu[0] * 0.35, head[1] - hu[1] * 0.35), 1.6 * S, 1.5 * S, shade(skin, 0.9), facet=False)
    _draw_head(surf, h, Th, S, tint)
    # -------------------------------------------------- front arm, weapon, shield
    arm_c = body_c if plated else skin
    quad(surf, J["sh"], J["ef"], 2.5 * S, 2.1 * S, tunic if not plated else body_c)
    quad(surf, J["ef"], J["hf"], 2.0 * S, 1.6 * S, arm_c)
    if not tint:
        # the sleeve's cuff at the wrist, the shoulder rounded over the arm
        sc = tunic if not plated else body_c
        cuff = (J["ef"][0] + (J["hf"][0] - J["ef"][0]) * 0.25, J["ef"][1] + (J["hf"][1] - J["ef"][1]) * 0.25)
        if not plated:
            paint.capsule(surf, J["ef"], cuff, 2.2 * S, 2.0 * S, sc)
        pygame.draw.circle(surf, paint.warm(sc, 0.1), (J["sh"][0] + LIGHT[0] * S * 0.5, J["sh"][1] + LIGHT[1] * S * 0.3),
                           2.4 * S)
    hfp = J["hf"]
    if inj.get("arm_w", 0) >= 1 and not tint:
        pygame.draw.circle(surf, (130, 20, 20), J["ef"], (1 + inj["arm_w"]) * S * 0.7)
    if wd is not None and wd.key != "fists" and p.weapon_mode == "hand" and not tint:
        if p.wa is None or rd is not None:
            ang = math.atan2(J["hf"][1] - J["ef"][1], (J["hf"][0] - J["ef"][0]) * f)
        else:
            ang = p.wa + (p.rot if p.rot else 0)
        tip = (hfp[0] + math.cos(ang) * wd.length * S * f, hfp[1] + math.sin(ang) * wd.length * S)
        act = h.action
        trail = getattr(h, "trail", None)
        # the trail is kept in world coordinates
        def to_w(q):
            return (h.cx + (q[0] - sx) / ss, h.feet + (q[1] - sy) / ss)

        def to_s(q):
            return (sx + (q[0] - h.cx) * ss, sy + (q[1] - h.feet) * ss)
        if act is not None and act.get("kind") == "attack" and rd is None:
            mv = act["move"]
            if mv.windup <= act["t"] <= mv.windup + mv.active + 0.05:
                if trail is None:
                    h.trail = trail = []
                trail.append((*to_w(tip), *to_w(hfp)))
                if len(trail) > 7:
                    trail.pop(0)
            elif trail:
                trail.pop(0)
        elif trail:
            trail.pop(0)
        if trail and len(trail) > 1:
            for i in range(len(trail) - 1):
                a, b = trail[i], trail[i + 1]
                k = (i + 1) / len(trail)
                c = (235, 238, 250, int(60 + 120 * k))
                pts = [to_s(a[:2]), to_s(b[:2]), to_s(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)),
                       to_s(((a[0] + a[2]) / 2, (a[1] + a[3]) / 2))]
                pygame.draw.polygon(surf, c, pts)
        _draw_weapon(surf, wd, hfp, tip, f, S, draw=p.draw, h=h, hand2=J["hb"])
    # the hand over the grip
    pygame.draw.circle(surf, shade(skin, 0.5), hfp, 1.9 * S)
    pygame.draw.circle(surf, skin, hfp, 1.9 * S - _EDGE[0])
    pygame.draw.circle(surf, paint.warm(skin, 0.15), (hfp[0] + LIGHT[0] * S * 0.6, hfp[1] + LIGHT[1] * S * 0.6), S * 0.8)
    if p.shield_up and h.shield is not None and not tint:
        _draw_shield(surf, h, (hfp[0] + 2 * f * S, hfp[1] - 3 * S), f, S, raised=True)
    if h.hurt_flash > 0:
        pygame.draw.circle(surf, (255, 255, 255), head, HEAD_R * S + S, max(1, int(S)))


def _w(n):
    """A line width of n pixels at the figure's final size."""
    return max(1, int(n * _EDGE[0] / 0.55 * 0.8 + 0.5))


def _foot(surf, knee, foot, f, color, S):
    x, y = foot
    pts = [(x - 2.4 * S * f, y - 2.8 * S), (x + 0.6 * S * f, y - 2.8 * S), (x + 2.6 * S * f, y - 1.4 * S),
           (x + 4.6 * S * f, y - 0.2 * S), (x + 4.4 * S * f, y + 0.5 * S), (x - 2.6 * S * f, y + 0.5 * S)]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.line(surf, paint.warm(color, 0.18), (x - 1.8 * S * f, y - 2.4 * S), (x + 2.4 * S * f, y - 1.0 * S),
                     _w(0.8))
    pygame.draw.line(surf, shade(color, 0.6), (x - 2.6 * S * f, y + 0.4 * S), (x + 4.4 * S * f, y + 0.4 * S), _w(1))
    pygame.draw.polygon(surf, shade(color, 0.45), pts, _w(0.7))


def _head_shape(r):
    pts = []
    for i in range(16):
        a = i / 16 * math.tau
        x, y = math.cos(a) * 4.8, math.sin(a) * 5.1
        if 0.2 < a < 1.6:                      # the jaw and chin come forward and down
            x += 0.5 * math.sin((a - 0.2) / 1.4 * math.pi)
            y += 0.3 * math.sin((a - 0.2) / 1.4 * math.pi)
        pts.append((x * r, y * r))
    return pts


def _draw_head(surf, h, T, S, tint):
    L = h.look
    skin = L["skin"] if not tint else tint
    r = S
    head = _head_shape(r)
    if tint:
        poly(surf, T, head, skin)
        return
    painted(surf, T, head, skin, 0.7, S)
    # ear, nose, cheek, eye, brow, mouth
    e = T(-0.7 * r, 0.5 * r)
    pygame.draw.circle(surf, shade(skin, 0.82), e, 1.3 * r)
    pygame.draw.circle(surf, shade(skin, 0.62), e, 1.3 * r, _w(0.5))
    poly(surf, T, [(4.6 * r, -0.8 * r), (6.3 * r, 1.4 * r), (4.7 * r, 1.9 * r)], shade(skin, 0.95))
    pygame.draw.line(surf, shade(skin, 0.7), T(6.3 * r, 1.4 * r), T(4.8 * r, 1.9 * r), _w(0.6))
    pygame.draw.circle(surf, paint.mix(skin, (210, 90, 80), 0.22), T(3.0 * r, 1.4 * r), 1.1 * r)
    eye = T(2.8 * r, -0.7 * r)
    pygame.draw.circle(surf, (30, 24, 22), eye, 0.85 * r)
    pygame.draw.circle(surf, (230, 230, 226), T(3.1 * r, -0.95 * r), 0.3 * r)
    hair = L["hair"]
    pygame.draw.line(surf, shade(hair, 0.8), T(1.6 * r, -2.1 * r), T(3.9 * r, -1.9 * r), _w(0.7))
    pygame.draw.line(surf, shade(skin, 0.62), T(3.6 * r, 3.0 * r), T(4.7 * r, 2.8 * r), _w(0.6))
    if L.get("beard"):
        bd = [(0.6 * r, 1.6 * r), (2.2 * r, 2.6 * r), (5.0 * r, 2.5 * r), (5.2 * r, 4.2 * r), (3.4 * r, 6.6 * r),
              (0.6 * r, 6.0 * r), (-1.4 * r, 3.4 * r)]
        painted(surf, T, bd, hair, 0.4, S)
        for k in range(4):
            pygame.draw.line(surf, paint.warm(hair, 0.2), T((1.0 + k) * r, 3.0 * r), T((0.8 + k) * r, 5.4 * r), _w(0.4))
    hel = h.helmet
    if hel:
        _helmet(surf, T, r, HELMETS[hel][1], L)
    else:
        hp = [(-5.3 * r, 3.0 * r), (-5.6 * r, -1.0 * r), (-4.2 * r, -4.6 * r), (-1.6 * r, -6.2 * r),
              (1.8 * r, -6.0 * r), (4.2 * r, -4.2 * r), (4.8 * r, -2.6 * r), (2.4 * r, -3.4 * r), (0.4 * r, -3.0 * r),
              (-1.6 * r, -1.6 * r), (-2.6 * r, 0.8 * r), (-3.2 * r, 3.4 * r)]
        painted(surf, T, hp, hair, 0.5, S)
        for k in range(5):
            a = T((-3.6 + k * 1.4) * r, -5.0 * r + abs(k - 2) * 0.4 * r)
            b = T((-4.6 + k * 1.2) * r, -2.0 * r + k * 0.2 * r)
            pygame.draw.line(surf, paint.warm(hair, 0.22), a, b, _w(0.4))
        _hat(surf, T, r, L)


def ppoly(surf, T, pts, color):
    painted(surf, T, pts, color, 0.5, _EDGE[0] / 0.55)


def _I(x, y):
    return (x, y)


def _helmet(surf, T, r, style, L):
    steel = (178, 184, 194)
    hi = shade(steel, 1.15)
    lo = shade(steel, 0.75)
    if style == "coif":
        ppoly(surf, T, [(-5.8 * r, 5.5 * r), (-5.6 * r, -3.0 * r), (-1.8 * r, -6.4 * r), (3.4 * r, -5.8 * r),
                       (4.6 * r, -2.6 * r), (1.6 * r, -2.8 * r), (1.0 * r, 3.6 * r), (3.0 * r, 6.4 * r),
                       (-3.0 * r, 7.0 * r)], (150, 154, 162))
        pygame.draw.line(surf, lo, T(-5.0 * r, 0), T(0.8 * r, 0), _w(1))
    elif style == "kettle":
        ppoly(surf, T, [(-4.8 * r, -2.2 * r), (-3.8 * r, -5.8 * r), (0, -7.0 * r), (3.8 * r, -5.8 * r),
                       (4.8 * r, -2.2 * r)], steel)
        ppoly(surf, T, [(-8.0 * r, -1.2 * r), (8.0 * r, -1.2 * r), (6.0 * r, -2.6 * r), (-6.0 * r, -2.6 * r)], hi)
        pygame.draw.line(surf, lo, T(0, -7.0 * r), T(0, -2.4 * r), _w(1))
    elif style == "bascinet":
        ppoly(surf, T, [(-5.2 * r, 4.0 * r), (-5.4 * r, -2.4 * r), (-2.8 * r, -8.6 * r), (2.6 * r, -5.6 * r),
                       (5.6 * r, -1.0 * r), (6.4 * r, 3.0 * r), (3.0 * r, 5.4 * r)], steel)
        ppoly(surf, T, [(-2.8 * r, -8.6 * r), (2.6 * r, -5.6 * r), (0.6 * r, -2.6 * r)], hi)
        pygame.draw.line(surf, (30, 30, 34), T(2.0 * r, -0.8 * r), T(6.0 * r, -0.4 * r), _w(1))
    elif style == "greathelm":
        ppoly(surf, T, [(-5.4 * r, 5.6 * r), (-5.6 * r, -4.0 * r), (-3.6 * r, -6.4 * r), (3.6 * r, -6.4 * r),
                       (5.8 * r, -4.0 * r), (5.8 * r, 5.6 * r)], steel)
        ppoly(surf, T, [(0.4 * r, -6.4 * r), (3.6 * r, -6.4 * r), (5.8 * r, -4.0 * r), (5.8 * r, 5.6 * r),
                       (2.0 * r, 5.6 * r)], hi)
        pygame.draw.line(surf, (24, 24, 28), T(-1.0 * r, -1.2 * r), T(5.8 * r, -1.2 * r), _w(2))
        pygame.draw.line(surf, (24, 24, 28), T(3.0 * r, 0.4 * r), T(3.0 * r, 4.4 * r), _w(1))
        if L.get("crest"):
            ppoly(surf, T, [(-3.0 * r, -6.4 * r), (0, -11.0 * r), (3.0 * r, -6.4 * r)], L["crest"])


def _hat(surf, T, r, L):
    hat = L.get("hat")
    c = L.get("hat_color", (110, 90, 60))
    if hat == "gugel":       # the hood with its long tail (Zipfel)
        ppoly(surf, T, [(-5.8 * r, 6.0 * r), (-6.0 * r, -2.4 * r), (-2.0 * r, -6.6 * r), (3.2 * r, -6.2 * r),
                       (5.2 * r, -2.6 * r), (2.0 * r, -3.0 * r), (1.0 * r, 3.0 * r), (4.0 * r, 6.6 * r)], c)
        ppoly(surf, T, [(-5.8 * r, -1.0 * r), (-11.0 * r, 2.2 * r), (-12.4 * r, 6.0 * r), (-5.4 * r, 1.4 * r)],
             shade(c, 0.85))
        ppoly(surf, T, [(-2.0 * r, -6.6 * r), (3.2 * r, -6.2 * r), (0.6 * r, -4.2 * r)], shade(c, 1.15))
    elif hat == "cap":
        ppoly(surf, T, [(-5.4 * r, -2.6 * r), (-3.4 * r, -6.6 * r), (3.0 * r, -6.8 * r), (5.4 * r, -3.0 * r)], c)
    elif hat == "straw":
        ppoly(surf, T, [(-8.0 * r, -2.6 * r), (8.0 * r, -2.6 * r), (5.0 * r, -3.8 * r), (-5.0 * r, -3.8 * r)],
             (222, 192, 112))
        ppoly(surf, T, [(-4.0 * r, -3.8 * r), (-2.6 * r, -7.4 * r), (2.6 * r, -7.4 * r), (4.0 * r, -3.8 * r)],
             (206, 176, 98))
    elif hat in ("crown", "coronet"):
        g = (232, 192, 72)
        ppoly(surf, T, [(-4.6 * r, -3.6 * r), (4.6 * r, -3.6 * r), (4.6 * r, -5.6 * r), (-4.6 * r, -5.6 * r)], g)
        if hat == "crown":
            for k in (-4.0, 0.0, 4.0):
                ppoly(surf, T, [((k - 1.4) * r, -5.6 * r), (k * r, -9.2 * r), ((k + 1.4) * r, -5.6 * r)], g)
    elif hat == "mitre":
        ppoly(surf, T, [(-4.4 * r, -3.4 * r), (-2.0 * r, -12.0 * r), (2.0 * r, -12.0 * r), (4.4 * r, -3.4 * r)],
             (240, 236, 226))
        pygame.draw.line(surf, (200, 160, 60), T(0, -12.0 * r), T(0, -3.6 * r), _w(1))
    elif hat == "veil":
        ppoly(surf, T, [(-6.0 * r, 7.0 * r), (-6.0 * r, -2.6 * r), (-2.0 * r, -6.6 * r), (3.2 * r, -6.2 * r),
                       (4.8 * r, -3.0 * r), (1.0 * r, -3.4 * r), (-1.2 * r, 6.6 * r)], c)
    elif hat == "tonsure":
        pygame.draw.circle(surf, L["skin"], T(-0.4 * r, -4.6 * r), max(1, int(2 * r)))


def _draw_shield(surf, h, pos, f, S, raised):
    sd = h.shield
    x, y = pos
    tab = h.look.get("tabard")
    c1 = tab[0] if tab else (150, 110, 70)
    c2 = tab[1] if tab else (110, 80, 50)
    s = sd.size * S
    if sd.style == "round":
        pts = [(x + math.cos(a) * s * 0.55, y + math.sin(a) * s * 0.55) for a in
               [i * math.tau / 8 + math.pi / 8 for i in range(8)]]
        painted(surf, _I, pts, c1, 0.8, S)
        pygame.draw.circle(surf, shade(c1, 0.6), (x, y), s * 0.42, _w(0.8))
        pygame.draw.polygon(surf, shade(c1, 0.45), pts, _w(1))
        pygame.draw.circle(surf, (170, 170, 180), (x, y), max(1, int(2 * S)))
    elif sd.style == "heater":
        pts = [(x - s * 0.4, y - s * 0.45), (x + s * 0.4, y - s * 0.45), (x + s * 0.38, y + s * 0.05),
               (x, y + s * 0.6), (x - s * 0.38, y + s * 0.05)]
        painted(surf, _I, pts, c1, 0.8, S)
        pygame.draw.polygon(surf, c2, [(x, y - s * 0.45 + _EDGE[0]), (x + s * 0.4 - _EDGE[0], y - s * 0.45 + _EDGE[0]),
                                       (x + s * 0.38 - _EDGE[0], y + s * 0.05), (x, y + s * 0.6 - _EDGE[0])])
        pygame.draw.line(surf, paint.warm(c1, 0.3), (x - s * 0.36, y - s * 0.4), (x - s * 0.05, y - s * 0.4), _w(1))
        pygame.draw.polygon(surf, shade(c1, 0.45), pts, _w(1))
    else:
        pts = [(x - s * 0.35, y - s * 0.62), (x + s * 0.35, y - s * 0.62), (x + s * 0.38, y + s * 0.66),
               (x - s * 0.38, y + s * 0.66)]
        painted(surf, _I, pts, c1, 0.8, S)
        pygame.draw.line(surf, c2, (x, y - s * 0.62), (x, y + s * 0.66), _w(3))
        pygame.draw.polygon(surf, shade(c1, 0.45), pts, _w(1))


STEEL = (214, 218, 228)
STEEL_HI = (246, 248, 252)
WOOD = (120, 86, 52)


def _draw_weapon(surf, wd, a, b, f, S, sheathed=False, draw=0.0, h=None, hand2=None):
    st = wd.style
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy) or 1
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux

    def at(t, off=0.0):
        return (ax + dx * t + px * off * S, ay + dy * t + py * off * S)

    if sheathed:
        quad(surf, a, b, 1.6 * S, 1.3 * S, (70, 50, 34))
        return
    if st in ("sword", "longsword", "dagger"):
        g = 0.18 if st != "longsword" else 0.22
        quad(surf, at(-0.1), at(g), 1.2 * S, 1.2 * S, (70, 50, 30), facet=False)
        blade = [at(g, 1.7), at(0.86, 1.3), at(1.0, 0), at(0.86, -1.3), at(g, -1.7)]
        pygame.draw.polygon(surf, STEEL, blade)
        pygame.draw.polygon(surf, STEEL_HI, [at(g, 1.7), at(0.86, 1.3), at(1.0, 0), at(g, 0)])
        pygame.draw.polygon(surf, (60, 62, 70), blade, _w(1))
        quad(surf, at(g, -4.5), at(g, 4.5), 1.0 * S, 1.0 * S, (196, 164, 72), facet=False)
        pm = at(-0.13)
        pygame.draw.polygon(surf, (196, 164, 72), [(pm[0] - 2, pm[1]), (pm[0], pm[1] - 2), (pm[0] + 2, pm[1]),
                                                   (pm[0], pm[1] + 2)])
    elif st == "axe":
        quad(surf, at(-0.1), at(1.0), 1.4 * S, 1.2 * S, WOOD)
        head = [at(0.70, -1.0), at(0.60, -8.5), at(0.98, -10.0), at(1.0, -1.0)]
        pygame.draw.polygon(surf, STEEL, head)
        pygame.draw.polygon(surf, STEEL_HI, [at(0.60, -8.5), at(0.98, -10.0), at(0.82, -6.0)])
        pygame.draw.polygon(surf, (60, 62, 70), head, _w(1))
    elif st == "mace":
        quad(surf, at(-0.1), at(0.78), 1.4 * S, 1.2 * S, WOOD)
        c = at(0.9)
        pts = [(c[0] + math.cos(k * math.pi / 3) * 6 * S, c[1] + math.sin(k * math.pi / 3) * 6 * S) for k in range(6)]
        pygame.draw.polygon(surf, (150, 152, 162), pts)
        pygame.draw.polygon(surf, (196, 198, 208), [pts[3], pts[4], c])
        pygame.draw.polygon(surf, (60, 62, 70), pts, _w(1))
    elif st == "club":
        quad(surf, at(-0.1), at(1.0), 1.4 * S, 3.0 * S, (124, 88, 52))
    elif st == "flail":
        quad(surf, at(-0.1), at(0.6), 1.4 * S, 1.2 * S, WOOD)
        sw = math.sin(pygame.time.get_ticks() * 0.01) * 4
        quad(surf, at(0.62), at(1.0, sw), 1.6 * S, 1.6 * S, (110, 80, 50))
    elif st in ("spear", "pike", "lance", "fork", "halberd"):
        quad(surf, at(-0.25), at(0.9), (1.6 if st == "lance" else 1.2) * S, (1.2 if st == "lance" else 1.1) * S, WOOD)
        if st == "fork":
            for off in (-3, 0, 3):
                quad(surf, at(0.88, off), at(1.0, off), 0.6, 0.4, (160, 160, 160), facet=False)
            quad(surf, at(0.88, -3), at(0.88, 3), 0.7, 0.7, (160, 160, 160), facet=False)
        elif st == "halberd":
            blade = [at(0.80, 0), at(0.76, -9), at(0.93, -10), at(0.92, 0)]
            pygame.draw.polygon(surf, STEEL, blade)
            pygame.draw.polygon(surf, STEEL_HI, [at(0.76, -9), at(0.93, -10), at(0.85, -5)])
            pygame.draw.polygon(surf, STEEL, [at(0.85, 0), at(0.86, 4.5), at(0.9, 0)])
            pygame.draw.polygon(surf, STEEL, [at(0.9, -1.2), at(1.06, 0), at(0.9, 1.2)])
        elif st == "lance":
            pygame.draw.polygon(surf, STEEL, [at(0.9, -2), at(1.05), at(0.9, 2)])
            pygame.draw.polygon(surf, (200, 200, 210), [at(0.1, -4.5), at(0.2, 0), at(0.1, 4.5)])
        else:
            pygame.draw.polygon(surf, STEEL, [at(0.9, -2.2), at(0.96, -1.6), at(1.05), at(0.96, 1.6), at(0.9, 2.2)])
            pygame.draw.polygon(surf, STEEL_HI, [at(0.9, -2.2), at(0.96, -1.6), at(1.05), at(0.9, 0)])
            if st == "pike" and h is not None and h.look.get("tabard"):
                pygame.draw.polygon(surf, h.look["tabard"][0], [at(0.84, 0), at(0.8, 6), at(0.76, 0)])
    elif st == "bow":
        # the bow stands across the line of the shot: it tilts with the aim
        act = getattr(h, "action", None) if h is not None else None
        aim = act.get("aim", 0.0) if act and act.get("kind") == "bow" else 0.35
        fx, fy_ = f * math.cos(aim), math.sin(aim)          # direction of the arrow
        ux, uy = fy_, -fx                                   # along the stave
        if uy > 0:
            ux, uy = -ux, -uy

        def B(along, fwd):
            return (ax + ux * along * S + fx * fwd * S, ay + uy * along * S + fy_ * fwd * S)
        top, bot = B(15, 0), B(-15, 0)
        pygame.draw.lines(surf, WOOD, False, [top, B(9, 4), B(0, 6), B(-9, 4), bot], _w(3))
        pull = B(0, -draw * 12)
        pygame.draw.line(surf, (230, 230, 220), top, pull, _w(1))
        pygame.draw.line(surf, (230, 230, 220), pull, bot, _w(1))
        if draw > 0.05:
            pygame.draw.line(surf, (200, 190, 170), pull, B(0, 12), _w(1))
            tip = B(0, 12)
            pygame.draw.polygon(surf, (200, 200, 206), [tip, B(1.5, 9), B(-1.5, 9)])
    elif st == "crossbow":
        quad(surf, at(-0.3), at(0.9), 1.8 * S, 1.6 * S, WOOD)
        pygame.draw.lines(surf, (90, 90, 96), False, [at(0.8, -9), at(0.88, 0), at(0.8, 9)], _w(2))
        pygame.draw.line(surf, (220, 220, 210), at(0.8, -9), at(0.5), _w(1))
        pygame.draw.line(surf, (220, 220, 210), at(0.8, 9), at(0.5), _w(1))
    elif st == "shovel":
        quad(surf, at(-0.1), at(0.8), 1.2 * S, 1.1 * S, WOOD)
        pygame.draw.polygon(surf, STEEL, [at(0.78, -3.5), at(1.04, -3), at(1.1, 0), at(1.04, 3), at(0.78, 3.5)])
        pygame.draw.polygon(surf, STEEL_HI, [at(0.78, -3.5), at(1.04, -3), at(1.1, 0), at(0.78, 0)])
    elif st in ("pick", "hammer", "sickle", "hoe", "scythe"):
        quad(surf, at(-0.1), at(1.0), 1.2 * S, 1.1 * S, WOOD)
        if st == "pick":
            pygame.draw.polygon(surf, STEEL, [at(0.95, -9), at(1.0, 0), at(0.95, 9), at(0.9, 0)])
        elif st == "hammer":
            quad(surf, at(0.92, -4), at(0.92, 4), 3 * S, 3 * S, (120, 120, 130))
        elif st == "hoe":
            pygame.draw.polygon(surf, STEEL, [at(0.96, 0), at(0.9, 7), at(1.0, 7), at(1.02, 0)])
        elif st == "scythe":
            pygame.draw.polygon(surf, STEEL, [at(1.0, 0), at(0.7, 9), at(0.74, 10.5), at(1.02, 1.5)])
        else:
            pygame.draw.polygon(surf, STEEL, [at(0.75, 0), at(0.9, 5), at(1.05, 2), at(1.0, 0)])
    elif st == "torch":
        quad(surf, at(-0.1), at(0.9), 1.3 * S, 1.3 * S, WOOD)
        t = pygame.time.get_ticks() * 0.02
        c = at(1.0)
        fl = 5 + math.sin(t) * 1.5
        pygame.draw.polygon(surf, (255, 140, 40), [(c[0] - 3, c[1] + 2), (c[0] + math.sin(t * 1.3) * 2, c[1] - fl - 3),
                                                   (c[0] + 3, c[1] + 2)])
        pygame.draw.polygon(surf, (255, 228, 140), [(c[0] - 1.5, c[1] + 2), (c[0], c[1] - fl * 0.5), (c[0] + 1.5, c[1] + 2)])
    elif st == "gun":
        quad(surf, at(-0.4), at(0.15), 1.6 * S, 1.6 * S, WOOD)
        quad(surf, at(0.1), at(1.0), 2.6 * S, 2.2 * S, (70, 72, 78))
        pygame.draw.circle(surf, (30, 30, 32), at(1.0), max(1, int(1.6 * S)))
