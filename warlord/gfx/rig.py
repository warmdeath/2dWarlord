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
        p.thf, p.shf = 1.35, -1.45
        p.thb, p.shb = 1.2, -1.45
        p.hip_y = -(THIGH + SHIN) * 0.25
        p.bob = math.sin(h.walk_phase * 2) * 1.5
        p.lean = 0.1
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


# ================================================================== drawing
def _pt(ox, oy, f, lx, ly, rot):
    if rot:
        c, s = math.cos(rot), math.sin(rot)
        lx, ly = lx * c - ly * s, lx * s + ly * c
    return ox + lx * f, oy + ly


def draw_humanoid(surf, h, sx, sy, scale=1.0, tint=None):
    """sx, sy = screen position of the feet centre."""
    p = h.pose
    f = h.facing
    L = h.look
    rot = p.rot
    # pivot for lying poses
    if rot:
        oy0 = sy - 4
    else:
        oy0 = sy
    hip = (0.0, p.hip_y + p.bob)
    if rot:
        hip = (0.0, -6.0)
    lean = p.lean
    sh = (hip[0] + math.sin(lean) * TORSO, hip[1] - math.cos(lean) * TORSO)
    neck = (sh[0] + math.sin(lean + p.head_tilt) * 2.5, sh[1] - math.cos(lean + p.head_tilt) * 2.5)
    head = (neck[0] + math.sin(lean + p.head_tilt) * HEAD_R, neck[1] - math.cos(lean + p.head_tilt) * HEAD_R)

    def P(pt):
        x, y = _pt(sx, oy0, f, pt[0] * scale, pt[1] * scale, rot * f if rot else 0)
        return (x, y)

    def limb(a1, l1, a2, l2, start):
        dx, dy = vec(a1, l1)
        j = (start[0] + dx, start[1] + dy)
        dx2, dy2 = vec(a1 + a2 if a2 is not None else a1, l2)
        e = (j[0] + dx2, j[1] + dy2)
        return j, e

    skin = L["skin"]
    tunic = L["tunic"]
    hose = L["hose"]
    boots = L.get("boots", (60, 44, 32))
    if tint:
        skin, tunic, hose, boots = tint, tint, tint, tint
    armor = h.armor
    if armor is not None and armor.style in ("mail", "plate") and not tint:
        tunic_draw = armor.color
    else:
        tunic_draw = tunic
    w_limb = max(2, int(4 * scale))
    # back leg / back arm
    kb, fb = limb(p.thb, THIGH, p.shb, SHIN, hip)
    kf, ff = limb(p.thf, THIGH, p.shf, SHIN, hip)
    eb, hb = limb(p.uab, UPPER, p.fab, FORE, sh)
    ef, hf = limb(p.uaf, UPPER, p.faf, FORE, sh)

    def line(c, a, b, w):
        pygame.draw.line(surf, c, P(a), P(b), w)

    # weapon on the back (sheathed)
    wd = h.weapon_def
    if wd is not None and p.weapon_mode == "sheathed" and wd.key != "fists" and not tint:
        bx0 = (hip[0] - 3, hip[1] - 2)
        bx1 = (hip[0] - 3 - math.cos(-0.9) * wd.length * 0.6, hip[1] - 2 - math.sin(0.9) * wd.length * 0.6)
        _draw_weapon(surf, wd, P(bx0), P((hip[0] - 3 - wd.length * 0.5, hip[1] + 8)), f, scale, sheathed=True)
    # back arm (+shield when not raised)
    line(dark(skin if armor is None or armor.style == "cloth" else tunic_draw), sh, eb, w_limb)
    line(dark(skin), eb, hb, w_limb)
    line(dark(hose), hip, kb, w_limb + 1)
    line(dark(hose), kb, fb, w_limb)
    line(dark(boots), fb, (fb[0] + 3, fb[1]), w_limb)
    if h.shield is not None and not p.shield_up and not tint:
        _draw_shield(surf, h, P((hb[0] - 1, hb[1] - 3)), f, scale, raised=False)
    # torso
    long_robe = L.get("robe", False)
    tw = 5.0
    perp = (math.cos(lean), math.sin(lean))
    hem = 5.5 if not long_robe else 17
    body = [
        (sh[0] - perp[0] * tw, sh[1] - perp[1] * tw * 0.3),
        (sh[0] + perp[0] * (tw - 1), sh[1]),
        (hip[0] + perp[0] * (tw + 1.5), hip[1] + hem),
        (hip[0] - perp[0] * (tw + 1.5), hip[1] + hem),
    ]
    pygame.draw.polygon(surf, tunic_draw, [P(q) for q in body])
    if not tint:
        if armor is not None and armor.style == "mail":
            for k in range(3):
                a = (body[0][0] + 1, body[0][1] + 4 + k * 4)
                b = (body[1][0], body[1][1] + 4 + k * 4)
                line(dark(tunic_draw, 0.8), a, b, 1)
        tab = L.get("tabard")
        if tab:
            c1, c2 = tab
            tb = [(sh[0] - perp[0] * 3, sh[1] + 1), (sh[0] + perp[0] * 3, sh[1] + 1),
                  (hip[0] + perp[0] * 4, hip[1] + hem - 1), (hip[0] - perp[0] * 4, hip[1] + hem - 1)]
            pygame.draw.polygon(surf, c1, [P(q) for q in tb])
            mid = ((sh[0] + hip[0]) / 2, (sh[1] + hip[1]) / 2 + 1)
            pygame.draw.circle(surf, c2, P(mid), max(1, int(2 * scale)))
        trim = L.get("trim")
        if trim:
            line(trim, (hip[0] - perp[0] * (tw + 1.5), hip[1] + hem), (hip[0] + perp[0] * (tw + 1.5), hip[1] + hem), 2)
            line(trim, (sh[0] - perp[0] * tw, sh[1]), (sh[0] + perp[0] * tw, sh[1]), 2)
        belt = L.get("belt", (70, 50, 30))
        line(belt, (hip[0] - perp[0] * (tw + 0.5), hip[1] - 1), (hip[0] + perp[0] * (tw + 0.5), hip[1] - 1), 2)
    # front leg
    line(hose, hip, kf, w_limb + 1)
    line(hose, kf, ff, w_limb)
    line(boots, ff, (ff[0] + 3, ff[1]), w_limb)
    # head
    hc = P(head)
    hr = max(2, int(HEAD_R * scale))
    pygame.draw.circle(surf, skin, hc, hr)
    if not tint:
        _draw_head(surf, h, hc, hr, f, lean, scale)
    # front arm + weapon
    arm_c = skin if armor is None or armor.style == "cloth" else tunic_draw
    sleeve = tunic_draw if not tint else tint
    line(sleeve, sh, ef, w_limb)
    line(arm_c if armor is not None and armor.style != "cloth" else skin, ef, hf, w_limb)
    pygame.draw.circle(surf, skin, P(hf), max(1, int(2 * scale)))
    if wd is not None and wd.key != "fists" and p.weapon_mode == "hand" and not tint:
        if p.wa is None:
            ang = math.atan2(hf[1] - ef[1], hf[0] - ef[0])
        else:
            ang = p.wa
        if rot:
            ang += rot
        tip = (hf[0] + math.cos(ang) * wd.length, hf[1] + math.sin(ang) * wd.length)
        _draw_weapon(surf, wd, P(hf), P(tip), f, scale, draw=p.draw, h=h, hand2=P(hb))
    if p.shield_up and h.shield is not None and not tint:
        _draw_shield(surf, h, P((hf[0] + 2, hf[1] - 3)), f, scale, raised=True)
    if h.hurt_flash > 0:
        pygame.draw.circle(surf, (255, 255, 255), hc, hr, 1)


def _draw_head(surf, h, hc, hr, f, lean, scale):
    L = h.look
    x, y = hc
    hat = L.get("hat")
    hel = h.helmet
    # face details
    ex = x + f * hr * 0.45
    pygame.draw.circle(surf, (30, 24, 20), (int(ex), int(y - 1)), 1)
    if L.get("beard"):
        pygame.draw.polygon(surf, L["hair"], [(x - f * 1, y + 1), (x + f * hr, y + 1), (x + f * (hr - 1), y + hr + 2),
                                              (x, y + hr)])
    if hel:
        style = HELMETS[hel][1]
        steel = (176, 180, 188)
        if style == "coif":
            pygame.draw.circle(surf, (150, 154, 160), (x, y), hr + 1, 0, draw_top_left=True, draw_top_right=True,
                               draw_bottom_left=f < 0, draw_bottom_right=f > 0)
            pygame.draw.circle(surf, L["skin"], (int(x + f * 2), int(y + 1)), max(1, hr - 2))
            pygame.draw.circle(surf, (30, 24, 20), (int(ex), int(y - 1)), 1)
        elif style == "kettle":
            pygame.draw.ellipse(surf, steel, (x - hr - 3, y - 2, hr * 2 + 6, 3))
            pygame.draw.circle(surf, steel, (x, y - 1), hr, draw_top_left=True, draw_top_right=True)
        elif style == "bascinet":
            pygame.draw.polygon(surf, steel, [(x - f * hr, y + 2), (x - f * hr, y - 2), (x - f * 1, y - hr - 4),
                                              (x + f * hr, y - 2), (x + f * (hr + 1), y + 3)])
            pygame.draw.line(surf, (40, 40, 44), (x, y - 1), (x + f * hr, y - 1), 1)
        elif style == "greathelm":
            pygame.draw.rect(surf, steel, (x - hr - 1, y - hr - 1, hr * 2 + 2, hr * 2 + 3), border_radius=2)
            pygame.draw.line(surf, (30, 30, 34), (x - hr + 1, y - 1), (x + hr - 1, y - 1), 2)
            pygame.draw.line(surf, (30, 30, 34), (x, y - 1), (x, y + hr), 1)
            if L.get("crest"):
                pygame.draw.polygon(surf, L["crest"], [(x - 3, y - hr - 1), (x, y - hr - 8), (x + 3, y - hr - 1)])
        return
    # hair
    pygame.draw.circle(surf, L["hair"], (x - f * 1, y - 1), hr, draw_top_left=True, draw_top_right=True,
                       draw_bottom_left=f > 0, draw_bottom_right=f < 0)
    if hat == "gugel":     # the medieval hood with its long tail (Zipfel)
        c = L.get("hat_color", (110, 90, 60))
        pygame.draw.circle(surf, c, (x, y), hr + 1, draw_top_left=True, draw_top_right=True,
                           draw_bottom_left=f > 0, draw_bottom_right=f < 0)
        pygame.draw.polygon(surf, c, [(x - f * hr, y), (x - f * (hr + 7), y + 5), (x - f * (hr - 1), y + 4)])
        pygame.draw.polygon(surf, c, [(x - hr - 2, y + hr), (x + hr + 2, y + hr), (x + hr, y + 3), (x - hr, y + 3)])
        pygame.draw.circle(surf, L["skin"], (int(x + f * 2), int(y + 1)), max(1, hr - 2))
        pygame.draw.circle(surf, (30, 24, 20), (int(ex), int(y - 1)), 1)
    elif hat == "cap":
        c = L.get("hat_color", (60, 60, 120))
        pygame.draw.ellipse(surf, c, (x - hr - 1, y - hr - 2, hr * 2 + 3, hr + 1))
    elif hat == "straw":
        pygame.draw.ellipse(surf, (220, 190, 110), (x - hr - 4, y - hr + 1, hr * 2 + 8, 4))
        pygame.draw.ellipse(surf, (210, 180, 100), (x - hr + 1, y - hr - 3, hr * 2 - 2, 6))
    elif hat == "crown":
        g = (230, 190, 70)
        pygame.draw.rect(surf, g, (x - hr, y - hr - 2, hr * 2, 3))
        for k in (-hr, 0, hr - 1):
            pygame.draw.polygon(surf, g, [(x + k - 1, y - hr - 2), (x + k + 1, y - hr - 6), (x + k + 2, y - hr - 2)])
    elif hat == "coronet":
        pygame.draw.rect(surf, (230, 190, 70), (x - hr, y - hr - 1, hr * 2, 2))
    elif hat == "mitre":
        pygame.draw.polygon(surf, (240, 236, 226), [(x - hr + 1, y - hr + 1), (x, y - hr - 9), (x + hr - 1, y - hr + 1)])
        pygame.draw.line(surf, (200, 160, 60), (x, y - hr - 8), (x, y - hr + 1), 1)
    elif hat == "veil":
        c = L.get("hat_color", (236, 232, 222))
        pygame.draw.circle(surf, c, (x - f, y), hr + 1, draw_top_left=True, draw_top_right=True,
                           draw_bottom_left=f > 0, draw_bottom_right=f < 0)
        pygame.draw.polygon(surf, c, [(x - f * hr, y), (x - f * (hr + 3), y + hr + 4), (x - f * (hr - 3), y + hr + 3)])
    elif hat == "tonsure":
        pygame.draw.circle(surf, L["skin"], (x, y - hr + 2), 2)


def _draw_shield(surf, h, pos, f, scale, raised):
    sd = h.shield
    x, y = pos
    c1 = h.look.get("tabard", ((140, 100, 60), (200, 170, 70)))[0] if h.look.get("tabard") else (150, 110, 70)
    c2 = h.look.get("tabard", (None, (200, 170, 70)))[1] if h.look.get("tabard") else (110, 80, 50)
    s = sd.size * scale
    if sd.style == "round":
        pygame.draw.circle(surf, c1, (x, y), s * 0.55)
        pygame.draw.circle(surf, (70, 60, 50), (x, y), s * 0.55, 1)
        pygame.draw.circle(surf, (160, 160, 170), (x, y), 2)
    elif sd.style == "heater":
        pts = [(x - s * 0.4, y - s * 0.45), (x + s * 0.4, y - s * 0.45), (x + s * 0.4, y), (x, y + s * 0.6),
               (x - s * 0.4, y)]
        pygame.draw.polygon(surf, c1, pts)
        pygame.draw.line(surf, c2, (x, y - s * 0.45), (x, y + s * 0.5), 2)
        pygame.draw.polygon(surf, (60, 50, 40), pts, 1)
    else:  # pavise
        pygame.draw.rect(surf, c1, (x - s * 0.35, y - s * 0.6, s * 0.7, s * 1.3), border_radius=3)
        pygame.draw.rect(surf, c2, (x - 2, y - s * 0.6, 4, s * 1.3))
        pygame.draw.rect(surf, (60, 50, 40), (x - s * 0.35, y - s * 0.6, s * 0.7, s * 1.3), 1, border_radius=3)


STEEL = (214, 218, 226)
WOOD = (120, 86, 52)


def _draw_weapon(surf, wd, a, b, f, scale, sheathed=False, draw=0.0, h=None, hand2=None):
    st = wd.style
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy) or 1
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux

    def at(t, off=0.0):
        return (ax + dx * t + px * off, ay + dy * t + py * off)

    if sheathed:
        pygame.draw.line(surf, (70, 50, 34), a, b, 3)
        return
    if st in ("sword", "longsword", "dagger"):
        grip = 0.16 if st != "longsword" else 0.2
        pygame.draw.line(surf, (70, 50, 30), at(-0.08), at(grip * 0.6), 3)
        pygame.draw.line(surf, (190, 160, 70), at(grip * 0.55, -4), at(grip * 0.55, 4), 2)
        pygame.draw.line(surf, (40, 40, 46), at(grip * 0.6), at(1.0), 4)
        pygame.draw.line(surf, STEEL, at(grip * 0.6), at(1.0), 2)
        pygame.draw.circle(surf, (190, 160, 70), at(-0.1), 2)
    elif st == "axe":
        pygame.draw.line(surf, WOOD, at(-0.1), at(1.0), 3)
        pts = [at(0.72, -1), at(0.62, -8), at(0.98, -9), at(0.96, -1)]
        pygame.draw.polygon(surf, STEEL, pts)
        pygame.draw.polygon(surf, (60, 60, 66), pts, 1)
    elif st == "mace":
        pygame.draw.line(surf, WOOD, at(-0.1), at(0.8), 3)
        c = at(0.9)
        pygame.draw.circle(surf, (150, 150, 160), c, 5)
        for k in range(6):
            ang = k * math.pi / 3
            pygame.draw.line(surf, (110, 110, 120), c, (c[0] + math.cos(ang) * 7, c[1] + math.sin(ang) * 7), 2)
    elif st == "club":
        pygame.draw.line(surf, WOOD, at(-0.1), at(1.0), 4)
        pygame.draw.circle(surf, (110, 76, 46), at(0.92), 4)
    elif st == "flail":
        pygame.draw.line(surf, WOOD, at(-0.1), at(0.6), 3)
        sw = math.sin(pygame.time.get_ticks() * 0.01) * 4
        pygame.draw.line(surf, (110, 80, 50), at(0.62), at(1.0, sw), 3)
    elif st in ("spear", "pike", "lance", "fork", "halberd"):
        pygame.draw.line(surf, WOOD, at(-0.25), at(0.92), 3 if st != "lance" else 4)
        if st == "fork":
            for off in (-3, 0, 3):
                pygame.draw.line(surf, (150, 150, 150), at(0.88, off), at(1.0, off), 1)
            pygame.draw.line(surf, (150, 150, 150), at(0.88, -3), at(0.88, 3), 1)
        elif st == "halberd":
            pygame.draw.polygon(surf, STEEL, [at(0.82, 0), at(0.78, -8), at(0.92, -9), at(0.9, 0)])
            pygame.draw.polygon(surf, STEEL, [at(0.85, 0), at(0.86, 4), at(0.9, 0)])
            pygame.draw.line(surf, STEEL, at(0.9), at(1.04), 2)
        elif st == "lance":
            pygame.draw.polygon(surf, STEEL, [at(0.9, -2), at(1.05), at(0.9, 2)])
            pygame.draw.polygon(surf, (200, 200, 210), [at(0.12, -4), at(0.18, 0), at(0.12, 4)])
        else:
            pygame.draw.polygon(surf, STEEL, [at(0.9, -2), at(1.04), at(0.9, 2)])
            if st == "pike" and h is not None and h.look.get("tabard"):
                pygame.draw.polygon(surf, h.look["tabard"][0], [at(0.84, 0), at(0.8, 6), at(0.76, 0)])
    elif st == "bow":
        mid = a
        top = (ax + px * 0 - ux * 0 + 0, ay - 15 * scale)
        bot = (ax, ay + 15 * scale)
        cx_ = ax + f * 5 * scale
        pygame.draw.arc(surf, WOOD, (ax - 6 * scale if f > 0 else ax - 4 * scale, ay - 16 * scale, 10 * scale,
                                     32 * scale), -math.pi / 2 if f > 0 else math.pi / 2,
                        math.pi / 2 if f > 0 else 3 * math.pi / 2, 3)
        pull = ax - f * draw * 12 * scale
        pygame.draw.line(surf, (230, 230, 220), (ax, ay - 15 * scale), (pull, ay), 1)
        pygame.draw.line(surf, (230, 230, 220), (pull, ay), (ax, ay + 15 * scale), 1)
        if draw > 0.05:
            pygame.draw.line(surf, (200, 190, 170), (pull, ay), (ax + f * 10 * scale, ay), 1)
    elif st == "crossbow":
        pygame.draw.line(surf, WOOD, at(-0.3), at(0.9), 4)
        pygame.draw.line(surf, (90, 90, 96), at(0.85, -9), at(0.85, 9), 2)
        pygame.draw.line(surf, (220, 220, 210), at(0.85, -9), at(0.5), 1)
        pygame.draw.line(surf, (220, 220, 210), at(0.85, 9), at(0.5), 1)
    elif st in ("pick", "hammer", "sickle"):
        pygame.draw.line(surf, WOOD, at(-0.1), at(1.0), 3)
        if st == "pick":
            pygame.draw.line(surf, STEEL, at(0.95, -9), at(0.95, 9), 3)
        elif st == "hammer":
            pygame.draw.rect(surf, (120, 120, 130), (*at(0.92, -4), 6, 6))
        else:
            pygame.draw.arc(surf, STEEL, (bx - 6, by - 6, 12, 12), 0, math.pi, 2)
    elif st == "torch":
        pygame.draw.line(surf, WOOD, at(-0.1), at(0.9), 3)
        t = pygame.time.get_ticks() * 0.02
        c = at(1.0)
        pygame.draw.circle(surf, (255, 150, 40), c, 4 + int(math.sin(t) * 1))
        pygame.draw.circle(surf, (255, 230, 140), c, 2)
